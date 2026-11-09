import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch
import os

OUT = "figures/"
OR = "#D9611A"
PEACH = "#FBE9DC"
plt.rcParams["font.family"] = "Carlito"


def box(ax, x, y, w, h, text, fc="white", ec="#444", bold=False, fs=8.5, color="#222"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.0))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", color=color, linespacing=1.15)


def arrow(ax, p, q, color="#555"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, lw=1.0, color=color,
                                 shrinkA=0, shrinkB=0))


# ---------- Cover banner ----------
fig = plt.figure(figsize=(8.27, 3.1), dpi=200)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 8.27); ax.set_ylim(0, 3.1); ax.axis("off")
ax.add_patch(Circle((6.4, 2.3), 1.9, fc=PEACH, ec="none"))
for r in (1.25, 1.5, 1.75, 2.0):
    ax.add_patch(Circle((8.3, 0.7), r, fc="none", ec=OR, lw=0.5, alpha=0.7))
fig.savefig(OUT + "cover.png", facecolor="white", transparent=False)
plt.close(fig)

# ---------- Figure: AI pipeline ----------
fig = plt.figure(figsize=(7.2, 2.7), dpi=220)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 10); ax.set_ylim(0, 3.7); ax.axis("off")
row1 = ["CV file\n(PDF, DOCX, scan,\nphoto)", "Antivirus", "Parsing\nor OCR", "Hidden-text and\ninjection check", "Personal-data\nredaction"]
row2 = ["LLM profile\nextraction", "Skill matching\nto ESCO", "Embedding\n(bge-m3)", "7 sub-scores\n+ evidence check", "Weighted\nscore", "Shortlist +\nexplanations"]
w1, g1 = 1.62, 0.43
for i, t in enumerate(row1):
    x = 0.1 + i * (w1 + g1)
    box(ax, x, 2.45, w1, 0.95, t, fc="#F5F5F5" if i else "white", bold=(i == 0))
    if i: arrow(ax, (x - g1 + 0.02, 2.925), (x - 0.02, 2.925))
w2, g2 = 1.3, 0.34
for i, t in enumerate(row2):
    x = 0.1 + i * (w2 + g2)
    hi = i >= 3
    box(ax, x, 0.55, w2, 0.95, t, fc=PEACH if hi else "#F5F5F5", ec=OR if hi else "#444", bold=(i == 5))
    if i: arrow(ax, (x - g2 + 0.02, 1.025), (x - 0.02, 1.025))
# row1 end -> row2 start
ax.plot([9.3, 9.3], [2.45, 2.0], color="#555", lw=1.0)
ax.plot([9.3, 0.8], [2.0, 2.0], color="#555", lw=1.0)
arrow(ax, (0.8, 2.0), (0.8, 1.52))
# job offer
box(ax, 4.2, 0.0, 3.0, 0.38, "Versioned job offer (requirements, weights)", fc="white", ec=OR, fs=7.5, color=OR)
arrow(ax, (5.7, 0.38), (5.7, 0.55), color=OR)
fig.savefig(OUT + "pipeline.png", facecolor="white")
plt.close(fig)

# ---------- Figure: architecture ----------
fig = plt.figure(figsize=(7.2, 3.9), dpi=220)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 10); ax.set_ylim(0, 5.4); ax.axis("off")
box(ax, 0.1, 2.35, 1.5, 0.8, "Browser\nrecruiter, candidate,\nvisitor", fc="white", fs=8)
box(ax, 2.0, 2.35, 1.3, 0.8, "Caddy\nTLS, size limit", fc="#F5F5F5", fs=8)
arrow(ax, (1.6, 2.75), (2.0, 2.75))
box(ax, 3.8, 3.55, 1.9, 0.8, "Next.js frontend\nSSR / ISR, 3 languages", fc=PEACH, ec=OR, fs=8, bold=True)
box(ax, 3.8, 2.05, 1.9, 1.1, "FastAPI\nmodular monolith\n(one code base)", fc=PEACH, ec=OR, fs=8, bold=True)
arrow(ax, (3.3, 2.75), (3.8, 3.8)); arrow(ax, (3.3, 2.65), (3.8, 2.6))
arrow(ax, (4.75, 3.55), (4.75, 3.15))
box(ax, 7.0, 4.25, 2.8, 0.7, "PostgreSQL 16 + pgvector\n(data and vectors)", fc="white", fs=8)
box(ax, 7.0, 3.35, 2.8, 0.7, "Redis\n(task queue, rate limits, cache)", fc="white", fs=8)
box(ax, 7.0, 2.45, 2.8, 0.7, "Object storage, EU (S3)\nencrypted CVs", fc="white", fs=8)
arrow(ax, (5.7, 2.9), (7.0, 4.5)); arrow(ax, (5.7, 2.75), (7.0, 3.7)); arrow(ax, (5.7, 2.5), (7.0, 2.8))
box(ax, 3.8, 0.7, 1.9, 1.0, "Celery worker\n(same image as API)", fc=PEACH, ec=OR, fs=8, bold=True)
arrow(ax, (7.5, 3.35), (5.7, 1.45))
box(ax, 7.0, 1.45, 2.8, 0.5, "Mistral API (EU): LLM, OCR, voice", fc="white", fs=8)
box(ax, 7.0, 0.85, 2.8, 0.5, "bge-m3 embeddings (local)", fc="white", fs=8)
box(ax, 7.0, 0.25, 2.8, 0.5, "ClamAV antivirus", fc="white", fs=8)
arrow(ax, (5.7, 1.3), (7.0, 1.65)); arrow(ax, (5.7, 1.15), (7.0, 1.1)); arrow(ax, (5.7, 0.95), (7.0, 0.5))
box(ax, 0.1, 0.7, 3.2, 0.9, "Observability: Sentry, Grafana Cloud, Langfuse\nBackups: WAL-G to Backblaze B2 (EU)\nE-mail: Brevo", fc="#F5F5F5", ec="#999", fs=7.5)
fig.savefig(OUT + "architecture.png", facecolor="white")
plt.close(fig)
print("figures ok")
