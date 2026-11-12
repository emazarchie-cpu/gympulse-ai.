"""Make Word copies of docs/legal/*.md in docs/legal/word/ (for printing, sending to a lawyer or signing on paper).

  python scripts/legal_to_word.py
"""
import os
import re

from docx import Document
from docx.shared import Pt, RGBColor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "docs", "legal")
OUT = os.path.join(SRC, "word")
FILES = {
    "TERMS_OF_SERVICE.md": "GymPulse-AI-Terms-of-Service.docx",
    "PRIVACY_POLICY.md": "GymPulse-AI-Privacy-Policy.docx",
    "DATA_PROCESSING_AGREEMENT.md": "GymPulse-AI-Data-Processing-Agreement.docx",
    "SUBSCRIPTION_AGREEMENT.md": "GymPulse-AI-Subscription-Agreement.docx",
    "MEMBER_AGREEMENT.md": "GymPulse-AI-Member-Agreement-and-Waiver-Template.docx",
    "README.md": "GymPulse-AI-Brief-for-Lawyer.docx",
}


def runs(par, text):
    """**bold** and `code` inside a line."""
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`") and part.endswith("`"):
            r = par.add_run(part[1:-1])
            r.font.name = "Courier New"
        else:
            par.add_run(part)


def convert(md_path, out_path):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    lines = open(md_path, encoding="utf-8").read().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.strip() == "---":
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            t = doc.add_table(rows=len(rows), cols=len(rows[0]))
            t.style = "Table Grid"
            for r, cells in enumerate(rows):
                for c, txt in enumerate(cells):
                    p = t.cell(r, c).paragraphs[0]
                    runs(p, txt)
                    if r == 0:
                        for run in p.runs:
                            run.bold = True
            doc.add_paragraph()
            continue
        m = re.match(r"^(#{1,3}) (.*)", line)
        if m:
            h = doc.add_heading(m.group(2), level=len(m.group(1)) - 1 if len(m.group(1)) > 1 else 0)
            for run in h.runs:
                run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)
        elif re.match(r"^\s*[-*] ", line):
            runs(doc.add_paragraph(style="List Bullet"), re.sub(r"^\s*[-*] ", "", line))
        elif re.match(r"^\d+\. ", line):
            runs(doc.add_paragraph(style="List Number"), re.sub(r"^\d+\. ", "", line))
        else:
            runs(doc.add_paragraph(), line)
        i += 1
    doc.save(out_path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for src, dst in FILES.items():
        convert(os.path.join(SRC, src), os.path.join(OUT, dst))
        print("wrote", dst)
