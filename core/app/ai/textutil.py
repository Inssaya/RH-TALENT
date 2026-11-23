"""Small text helpers shared by the AI pipeline."""
import re
import unicodedata

_WORD = r"A-Za-z0-9À-ɏ؀-ۿ"


def fold(text: str) -> str:
    """Case-fold and strip diacritics (Latin accents, Arabic hamza forms)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def bounded(pattern: str) -> re.Pattern:
    """Compile an alternation with word boundaries that also work for C++, C#, .NET, Arabic."""
    return re.compile(rf"(?<![{_WORD}])(?:{pattern})(?![{_WORD}+#])")


def tokens(text: str) -> list[str]:
    return re.findall(rf"[{_WORD}][{_WORD}+#.]*", fold(text))


def detect_lang(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return ""
    arabic = sum(1 for c in letters if "؀" <= c <= "ۿ")
    if arabic / len(letters) > 0.3:
        return "ar"
    toks = set(tokens(text[:6000]))
    fr = len(toks & {"le", "la", "les", "des", "et", "de", "en", "pour", "avec", "dans", "une", "sur", "du", "au"})
    en = len(toks & {"the", "and", "of", "to", "in", "for", "with", "on", "a", "at", "from", "by", "an", "as"})
    return "fr" if fr >= en else "en"


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?؟])\s+|\n+", text)
    return [p.strip(" \t-•*·▪●") for p in parts if len(p.strip()) >= 15]
