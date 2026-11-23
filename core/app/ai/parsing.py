"""Document ingestion: type check, text extraction, OCR, hidden-text removal, quality score."""
import base64
import io
import logging
import re
import shutil
import zipfile
from dataclasses import dataclass, field

import httpx

from ..config import get_settings
from .guard import scan_injection
from .textutil import detect_lang, fold

log = logging.getLogger("tm.parsing")

ALLOWED = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "rtf": "application/rtf",
    "txt": "text/plain",
    "png": "image/png",
    "jpg": "image/jpeg",
}
_SECTIONS = {
    "experience": ["experience", "experiences", "parcours professionnel", "emploi", "employment", "work history", "الخبرة", "الخبرات"],
    "education": ["formation", "formations", "education", "diplome", "diplomes", "etudes", "التعليم", "الدراسة", "المؤهلات"],
    "skills": ["competences", "skills", "technologies", "outils", "المهارات"],
}


class UnsupportedFile(ValueError):
    pass


@dataclass
class Parsed:
    text: str = ""
    lang: str = ""
    method: str = "native"
    quality: float = 0.0
    flags: dict = field(default_factory=dict)


def sniff(data: bytes, filename: str = "") -> str:
    """Return the real file kind from magic bytes (never trust the extension)."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:5] == b"{\\rtf":
        return "rtf"
    if data[:4] == b"PK\x03\x04":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile as exc:
            raise UnsupportedFile("corrupted archive") from exc
        if "word/document.xml" in names:
            return "docx"
        if "content.xml" in names:
            return "odt"
        raise UnsupportedFile("unsupported archive")
    if b"\x00" not in data[:4096]:
        try:
            data[:4096].decode("utf-8")
            return "txt"
        except UnicodeDecodeError:
            try:
                data[:4096].decode("cp1252")
                return "txt"
            except UnicodeDecodeError:
                pass
    raise UnsupportedFile("unsupported file type")


def _pdf(data: bytes) -> tuple[str, list[str], list]:
    import pymupdf as fitz
    doc = fitz.open(stream=data, filetype="pdf")
    if doc.page_count > 15:
        raise UnsupportedFile("document longer than 15 pages")
    lines, hidden, pages = [], [], []
    for page in doc:
        pages.append(page)
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                visible = []
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    if not txt.strip():
                        continue
                    # white or near-invisible text is a classic way to smuggle keywords or instructions
                    if span.get("color", 0) >= 0xFAFAFA or span.get("size", 10) < 3:
                        hidden.append(txt.strip())
                    else:
                        visible.append(txt)
                if visible:
                    lines.append(" ".join(visible))
            lines.append("")
    return "\n".join(lines), hidden, (doc, pages)


def _docx(data: bytes) -> str:
    import docx
    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            parts.append(" | ".join(dict.fromkeys(c.text.strip() for c in row.cells if c.text.strip())))
    return "\n".join(parts)


def _odt(data: bytes) -> str:
    xml = zipfile.ZipFile(io.BytesIO(data)).read("content.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</text:(p|h)>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _rtf(data: bytes) -> str:
    txt = data.decode("cp1252", "ignore")
    txt = re.sub(r"\\par[d]?", "\n", txt)
    txt = re.sub(r"\\'[0-9a-f]{2}", lambda m: bytes.fromhex(m.group(0)[2:]).decode("cp1252", "ignore"), txt)
    txt = re.sub(r"\\[a-z]+-?\d* ?", "", txt)
    return re.sub(r"[{}]", "", txt)


def _ocr_mistral(data: bytes, mime: str) -> tuple[str, float] | None:
    s = get_settings()
    if not s.mistral_api_key:
        return None
    kind = "image_url" if mime.startswith("image/") else "document_url"
    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    try:
        r = httpx.post(f"{s.mistral_base_url}/ocr", timeout=120,
                       headers={"Authorization": f"Bearer {s.mistral_api_key}"},
                       json={"model": s.ocr_model, "document": {"type": kind, kind: url}})
        r.raise_for_status()
        return "\n\n".join(p.get("markdown", "") for p in r.json().get("pages", [])), 0.9
    except Exception as exc:
        log.warning("Mistral OCR failed, falling back: %s", exc)
        return None


def _ocr_tesseract(images: list) -> tuple[str, float] | None:
    if not shutil.which("tesseract"):
        return None
    try:
        import pytesseract
    except ImportError:
        return None
    langs = "+".join(lang for lang in ("fra", "eng", "ara") if lang in pytesseract.get_languages(config="")) or "eng"
    texts, confs = [], []
    for img in images:
        d = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)
        confs += [float(c) for c, t in zip(d["conf"], d["text"], strict=False) if t.strip() and float(c) >= 0]
        texts.append(pytesseract.image_to_string(img, lang=langs))
    conf = (sum(confs) / len(confs) / 100) if confs else 0.3
    return "\n".join(texts), conf


def _images_from(kind: str, data: bytes, pdf_ctx=None) -> list:
    try:
        from PIL import Image
    except ImportError:
        return []
    if kind in ("png", "jpg"):
        return [Image.open(io.BytesIO(data))]
    if pdf_ctx:
        _, pages = pdf_ctx
        return [Image.open(io.BytesIO(p.get_pixmap(dpi=200).tobytes("png"))) for p in pages]
    return []


def quality_score(text: str, ocr_conf: float) -> float:
    """q = 0.4*OCR confidence (1 if native) + 0.3*share of expected sections + 0.3*(1 - abnormal chars)."""
    if len(text.strip()) < 80:
        return 0.0
    f = fold(text)
    found = sum(1 for kws in _SECTIONS.values() if any(k in f for k in kws))
    printable = [c for c in text if not c.isspace()]
    odd = sum(1 for c in printable if not (c.isalnum() or c in ".,;:!?'\"()[]{}-–—_/\\@+#&%*|•·▪●°€$<>=’“”«»،؛؟"))
    return round(0.4 * ocr_conf + 0.3 * found / len(_SECTIONS) + 0.3 * (1 - odd / max(1, len(printable))), 3)


def parse_document(data: bytes, filename: str = "") -> Parsed:
    kind = sniff(data, filename)
    out = Parsed()
    ocr_conf, pdf_ctx, text = 1.0, None, ""
    if kind == "pdf":
        text, hidden, pdf_ctx = _pdf(data)
        if hidden:
            out.flags["hidden_text"] = hidden[:20]
    elif kind == "docx":
        text = _docx(data)
    elif kind == "odt":
        text = _odt(data)
    elif kind == "rtf":
        text = _rtf(data)
    elif kind == "txt":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252", "ignore")
    if kind in ("png", "jpg") or (kind == "pdf" and len(text.strip()) < 120):
        res = _ocr_mistral(data, ALLOWED[kind])
        out.method = "ocr-mistral"
        if res is None:
            res = _ocr_tesseract(_images_from(kind, data, pdf_ctx))
            out.method = "ocr-tesseract"
        if res is None:
            out.method = "ocr-unavailable"
            out.flags["ocr_unavailable"] = True
            text, ocr_conf = "", 0.0
        else:
            text, ocr_conf = res
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text, removed = scan_injection(text)
    if removed:
        out.flags["injection"] = removed[:10]
    out.text = text[:60000]
    out.lang = detect_lang(text)
    out.quality = quality_score(text, ocr_conf)
    return out
