"""Branded downloads: PDF reports and Excel exports with the GymPulse AI header.

Every file a gym owner downloads carries the same header: the GymPulse AI logo
on a navy band, the gym's name, the document title and the date, a lime accent
line, and a footer with page numbers.

Downloads are delivered as data links built into the page, so they can't expire
on the server before a phone fetches them (the cause of "Not found").
"""
import base64
import io
import os
from datetime import datetime

import pandas as pd
import streamlit as st

import gympulse_workspaces as gw

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "gympulse-email-logo.png")      # full lockup, light lettering
NAVY, NAVY_2, LIME, CYAN = "#0B1020", "#151D30", "#B7F34A", "#35D6ED"
INK, MUTED, LINE, ZEBRA = "#111827", "#5B6678", "#E3E8EF", "#F5F7FA"


# ------------------------------------------------------------------ download links
def download_link(label, data, filename, mime, key, primary=False):
    """A download button that carries the file inside the page itself."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    b64 = base64.b64encode(data).decode()
    cls = "gp-dl gp-dl-primary" if primary else "gp-dl"
    gw._md(f'<a class="{cls}" id="dl_{key}" download="{gw._esc(filename)}" '
           f'href="data:{mime};base64,{b64}">'
           f'<span class="gp-dl-ic">⬇</span>{gw._esc(label)}</a>')


DOWNLOAD_CSS = """
.gp-dl { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%;
    min-height: 42px; padding: 9px 14px; border-radius: 12px; box-sizing: border-box;
    border: 1px solid rgba(255,255,255,0.22); background: rgba(255,255,255,0.04);
    color: #F4F7FB !important; font-weight: 700; font-size: 14px; text-decoration: none !important; }
.gp-dl:hover { border-color: rgba(183,243,74,0.6); background: rgba(183,243,74,0.08); }
.gp-dl-primary { background: linear-gradient(100deg, #B7F34A, #35D6ED); border: 0; color: #0A0F1E !important; }
.gp-dl-primary:hover { filter: brightness(1.06); }
.gp-dl-ic { font-size: 15px; }
"""


def apply_css():
    st.markdown("<style>" + DOWNLOAD_CSS + "</style>", unsafe_allow_html=True)


def _gym_name():
    return gw._text((st.session_state.get("user_profile") or {}).get("business_name"), "Your gym")


# ------------------------------------------------------------------ PDF
LOGO_DARK = os.path.join(HERE, "gympulse-logo-dark.png")   # navy lettering, for white backgrounds
_PDF_MAP = {"₦": "NGN ", "→": " to ", "←": "", "✓": "", "✔": "", "•": "-", "…": "...",
            "“": '"', "”": '"', "‘": "'", "’": "'"}


def clean(text):
    """Professional PDF text: no emoji or symbols the fonts can't print; naira as NGN."""
    import re
    t = str(text if text is not None else "")
    for k, v in _PDF_MAP.items():
        t = t.replace(k, v)
    t = t.encode("cp1252", "ignore").decode("cp1252")
    t = re.sub(r"\*\*?([^*\n]+)\*\*?", r"\1", t)
    return re.sub(r"[ \t]{2,}", " ", t).replace("NGN  ", "NGN ").strip()


def _pdf_brand():
    """The gym's colours and logo for document headers (cached for the session)."""
    try:
        import gympulse_campaigns as gcamp
        b = gcamp.brand()
    except Exception:
        b = None
    sig = (b or {}).get("logo_url"), (b or {}).get("color"), (b or {}).get("dark"), (b or {}).get("gym")
    cache = st.session_state.get("_pdf_brand")
    if cache and cache.get("sig") == sig:
        return cache
    try:
        logo = gcamp._fetch_image(b.get("logo_url")) if b.get("logo_url") else None
        out = {"gym": b["gym"], "dark": b["dark"] or NAVY, "accent": b["color"] or LIME, "logo": logo, "sig": sig}
    except Exception:
        out = {"gym": _gym_name(), "dark": NAVY, "accent": LIME, "logo": None, "sig": sig}
    st.session_state["_pdf_brand"] = out
    return out


def _lum(hex_colour):
    try:
        h = hex_colour.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 0


def build_pdf(title, subtitle, blocks, gym=None):
    """blocks: list of ("h", text) | ("p", text) | ("kpis", [(label, value, hint)])
    | ("table", columns, rows) | ("note", text) | ("space", points)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
                                    KeepTogether)

    from reportlab.lib.utils import ImageReader

    brand = _pdf_brand()
    gym = clean(gym or brand["gym"] or _gym_name())
    title, subtitle = clean(title), clean(subtitle)
    head = brand["dark"] if _lum(brand["dark"]) < 0.45 else NAVY
    light_head = False
    if brand.get("logo"):
        try:
            import gympulse_campaigns as gcamp
            light_head = gcamp.logo_is_dark(brand["logo"])
        except Exception:
            light_head = False
    band_fill = "#FFFFFF" if light_head else head
    band_text = INK if light_head else "#FFFFFF"
    band_sub = MUTED if light_head else "#C9D3E3"
    accent = brand["accent"] or LIME
    W, H = A4
    band = 30 * mm
    buf = io.BytesIO()
    made = datetime.now(gw.APP_TZ)
    gym_logo = None
    if brand.get("logo"):
        try:
            gym_logo = ImageReader(io.BytesIO(brand["logo"]))
        except Exception:
            gym_logo = None

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(band_fill))
        canvas.rect(0, H - band, W, band, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor(accent))
        canvas.rect(0, H - band - 1.6 * mm, W, 1.6 * mm, stroke=0, fill=1)
        x0 = 14 * mm
        if gym_logo is not None:                      # the gym's own logo, scaled to fit the band
            iw, ih = gym_logo.getSize()
            lh = 15 * mm
            lw = min(lh * iw / max(ih, 1), 70 * mm)
            lh = lw * ih / max(iw, 1)
            canvas.drawImage(gym_logo, x0, H - band + (band - lh) / 2, width=lw, height=lh, mask="auto")
        else:                                          # no logo yet: the gym's name as a wordmark
            canvas.setFillColor(colors.HexColor(band_text))
            canvas.setFont("Helvetica-Bold", 17)
            canvas.drawString(x0, H - band / 2 - 2, gym)
        canvas.setFillColor(colors.HexColor(band_text))
        canvas.setFont("Helvetica-Bold", 11.5)
        canvas.drawRightString(W - 14 * mm, H - 12.5 * mm, title)
        canvas.setFillColor(colors.HexColor(band_sub))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(W - 14 * mm, H - 18.5 * mm, gym if gym_logo is not None else "")
        canvas.drawRightString(W - 14 * mm, H - 23.5 * mm, made.strftime("Generated %d %b %Y, %H:%M"))
        canvas.setStrokeColor(colors.HexColor(LINE))
        canvas.setLineWidth(0.6)
        canvas.line(14 * mm, 15 * mm, W - 14 * mm, 15 * mm)
        fx = 14 * mm
        if os.path.exists(LOGO_DARK):                  # small GymPulse AI mark in the footer
            fh = 4.2 * mm
            canvas.drawImage(LOGO_DARK, fx, 8 * mm, width=fh * 560 / 200, height=fh, mask="auto",
                             preserveAspectRatio=True)
            fx += fh * 560 / 200 + 3 * mm
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(fx, 9.3 * mm, f"Prepared for {gym} with GymPulse AI  |  Confidential: contains member data")
        canvas.drawRightString(W - 14 * mm, 9.3 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=band + 10 * mm, bottomMargin=20 * mm,
                            title=f"{gym} · {title}", author="GymPulse AI")
    st_title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=20, leading=24,
                              textColor=colors.HexColor(INK), spaceAfter=2)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=10, leading=14,
                            textColor=colors.HexColor(MUTED), spaceAfter=10)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                          textColor=colors.HexColor(INK), spaceBefore=12, spaceAfter=6)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13.5,
                          textColor=colors.HexColor(INK), alignment=TA_LEFT)
    st_note = ParagraphStyle("n", parent=st_p, fontSize=8, leading=11, textColor=colors.HexColor(MUTED))
    st_cell = ParagraphStyle("c", parent=st_p, fontSize=8.5, leading=11)
    st_head = ParagraphStyle("hc", parent=st_cell, fontName="Helvetica-Bold", textColor=colors.white)
    st_lab = ParagraphStyle("kl", parent=st_cell, fontSize=7.5, leading=10, textColor=colors.HexColor(MUTED))
    st_val = ParagraphStyle("kv", parent=st_cell, fontName="Helvetica-Bold", fontSize=16, leading=21,
                            textColor=colors.HexColor(INK), spaceBefore=2, spaceAfter=1)

    usable = W - 28 * mm
    story = [Paragraph(gw._esc(title), st_title)]
    if subtitle:
        story.append(Paragraph(gw._esc(subtitle), st_sub))
    for b in blocks:
        kind = b[0]
        if kind == "h":
            story.append(Paragraph(gw._esc(clean(b[1])), st_h))
        elif kind == "p":
            story.append(Paragraph(clean(b[1]), st_p))
        elif kind == "note":
            story.append(Spacer(1, 4))
            story.append(Paragraph(gw._esc(clean(b[1])), st_note))
        elif kind == "space":
            story.append(Spacer(1, b[1]))
        elif kind == "kpis":
            items = b[1]
            n = max(1, min(4, len(items)))
            cells, row = [], []
            for label, value, hint in items:
                row.append([Paragraph(gw._esc(clean(label).upper()), st_lab),
                            Paragraph(gw._esc(clean(value)), st_val),
                            Paragraph(gw._esc(clean(hint)), st_lab)])
                if len(row) == n:
                    cells.append(row)
                    row = []
            if row:
                cells.append(row + [""] * (n - len(row)))
            t = Table(cells, colWidths=[usable / n] * n)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ZEBRA)),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(LINE)),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEABOVE", (0, 0), (-1, 0), 2, colors.HexColor(accent)),
            ]))
            story.append(t)
        elif kind == "table":
            cols, rows = b[1], b[2]
            widths = b[3] if len(b) > 3 and b[3] else None
            if not rows:
                story.append(Paragraph("Nothing to show yet.", st_note))
                continue
            data = [[Paragraph(gw._esc(clean(c)), st_head) for c in cols]]
            data += [[Paragraph(gw._esc(clean(v)), st_cell) for v in r] for r in rows]
            if widths:
                total = sum(widths)
                widths = [usable * w / total for w in widths]
            t = Table(data, colWidths=widths or [usable / len(cols)] * len(cols), repeatRows=1)
            style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(head)),
                     ("VALIGN", (0, 0), (-1, -1), "TOP"),
                     ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                     ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE))]
            for i in range(1, len(data)):
                if i % 2 == 0:
                    style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(ZEBRA)))
            t.setStyle(TableStyle(style))
            story.append(t)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()


# ------------------------------------------------------------------ Excel
def build_xlsx(sheets, title, gym=None):
    """sheets: list of (sheet name, DataFrame, {column: 'money'|'pct'|'date'}).
    Each sheet gets the branded header, a styled table, filters and frozen headings."""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    gym = gym or _gym_name()
    wb = Workbook()
    wb.remove(wb.active)
    navy = PatternFill("solid", fgColor=NAVY[1:])
    lime = PatternFill("solid", fgColor=LIME[1:])
    head = PatternFill("solid", fgColor=NAVY_2[1:])
    zebra = PatternFill("solid", fgColor=ZEBRA[1:])
    thin = Side(style="thin", color=LINE[1:])
    made = datetime.now(gw.APP_TZ)
    for name, df, formats in sheets:
        ws = wb.create_sheet(name[:31])
        ncols = max(1, len(df.columns))
        last = get_column_letter(max(ncols, 6))
        for r in range(1, 5):
            for c in range(1, max(ncols, 6) + 1):
                ws.cell(row=r, column=c).fill = navy
        for c in range(1, max(ncols, 6) + 1):
            ws.cell(row=5, column=c).fill = lime
        ws.row_dimensions[5].height = 4
        for r in (1, 2, 3, 4):
            ws.row_dimensions[r].height = 18
        if os.path.exists(LOGO):
            img = XLImage(LOGO)
            img.height, img.width = 58, int(58 * 560 / 200)
            ws.add_image(img, "A1")
        ws.merge_cells(f"D1:{last}2")
        ws["D1"] = gym
        ws["D1"].font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
        ws["D1"].alignment = Alignment(horizontal="right", vertical="center")
        ws.merge_cells(f"D3:{last}3")
        ws["D3"] = f"{title} · {name}"
        ws["D3"].font = Font(name="Calibri", size=11, color="C9D3E3")
        ws["D3"].alignment = Alignment(horizontal="right")
        ws.merge_cells(f"D4:{last}4")
        ws["D4"] = made.strftime("Generated %d %b %Y, %H:%M · Prepared with GymPulse AI · Confidential")
        ws["D4"].font = Font(name="Calibri", size=9, color="93A1B8")
        ws["D4"].alignment = Alignment(horizontal="right")

        top = 7
        for j, col in enumerate(df.columns, 1):
            cell = ws.cell(row=top, column=j, value=str(col))
            cell.fill = head
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = Border(bottom=thin)
        ws.row_dimensions[top].height = 24
        for i, row in enumerate(df.itertuples(index=False), 1):
            for j, v in enumerate(row, 1):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    v = ""
                elif isinstance(v, pd.Timestamp):
                    v = v.to_pydatetime().replace(tzinfo=None)
                cell = ws.cell(row=top + i, column=j, value=v)
                cell.border = Border(bottom=thin)
                if i % 2 == 0:
                    cell.fill = zebra
                fmt = formats.get(df.columns[j - 1])
                if fmt == "money":
                    cell.number_format = "#,##0"
                elif fmt == "pct":
                    cell.number_format = "0%"
                elif fmt == "date":
                    cell.number_format = "dd mmm yyyy"
        for j, col in enumerate(df.columns, 1):
            values = [len(str(col))] + [len(str(v)) for v in df.iloc[:200, j - 1].tolist()]
            ws.column_dimensions[get_column_letter(j)].width = max(10, min(48, max(values) + 3))
        ws.freeze_panes = ws.cell(row=top + 1, column=1)
        if len(df):
            ws.auto_filter.ref = f"A{top}:{get_column_letter(ncols)}{top + len(df)}"
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.print_title_rows = f"{top}:{top}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
