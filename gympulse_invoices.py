"""GymPulse AI · Invoices and receipts for gym subscriptions.

Every checkout creates an invoice (billing_invoices, sql/phase12_invoices.sql)
with the gym's billing details. When the payment is confirmed (Paystack, a bank
transfer the founder confirms, or Admin → Mark as paid) the invoice is marked
paid and a receipt is emailed from GymPulse AI to the gym owner, with a PDF.

All writes go through the server key; gym owners can only read their own
invoices. If the table doesn't exist yet, checkout still works and the receipt
email is still sent, just without a receipt number.
"""
import io
import os
from datetime import datetime, timezone

import streamlit as st

import gympulse_workspaces as gw

NG_STATES = ["Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River",
             "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT (Abuja)", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano",
             "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo",
             "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara"]
METHOD_LABEL = {"paystack": "Card, transfer or USSD (Paystack)", "transfer": "Bank transfer", "admin": "Bank transfer"}
FIELDS = ("billing_name", "billing_email", "billing_phone", "business_name", "address", "city", "state")


def number(inv):
    n = (inv or {}).get("number")
    return f"GP-{int(n):06d}" if n else (inv or {}).get("reference") or "–"


def money(x):
    return f"₦{float(x or 0):,.0f}"


def _service():
    import gympulse_admin as gadm
    return gadm.service_client()


def _now():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ data
def create(sc, gym_id, plan, period, amount, details, method, reference=None, months=None):
    """A pending invoice. Returns the row (or a plain dict if the table isn't there yet)."""
    row = {"gym_id": gym_id, "plan": plan, "period": period, "amount": float(amount),
           "months": int(months or (12 if period == "yearly" else 1)), "method": method,
           "reference": reference, "status": "pending",
           **{k: (gw._text(details.get(k)).strip() or None) for k in FIELDS}}
    try:
        return (sc.table("billing_invoices").insert(row).execute().data or [row])[0]
    except Exception:
        return {**row, "id": None, "number": None, "created_at": _now()}


def update(sc, inv, **fields):
    if not inv.get("id"):
        inv.update(fields)
        return inv
    try:
        rows = sc.table("billing_invoices").update(fields).eq("id", inv["id"]).execute().data
        return rows[0] if rows else {**inv, **fields}
    except Exception:
        return {**inv, **fields}


def by_reference(sc, reference):
    try:
        rows = sc.table("billing_invoices").select("*").eq("reference", reference).limit(1).execute().data
        return rows[0] if rows else None
    except Exception:
        return None


def by_id(sc, invoice_id):
    try:
        rows = sc.table("billing_invoices").select("*").eq("id", invoice_id).limit(1).execute().data
        return rows[0] if rows else None
    except Exception:
        return None


def for_gym(client, gym_id):
    """All of a gym's invoices, newest first, or None before the SQL is run."""
    try:
        return client.table("billing_invoices").select("*").eq("gym_id", gym_id) \
            .order("created_at", desc=True).execute().data or []
    except Exception:
        return None


def pending_transfers(sc):
    try:
        return sc.table("billing_invoices").select("*").eq("status", "pending").eq("method", "transfer") \
            .order("created_at", desc=True).execute().data or []
    except Exception:
        return []


def last_details(client, gym_id):
    """Billing details from the gym's last checkout, to fill the form in."""
    rows = for_gym(client, gym_id) or []
    return {k: rows[0].get(k) for k in FIELDS} if rows else {}


# ------------------------------------------------------------------ receipt PDF
def receipt_pdf(inv, paid=True):
    """A clean GymPulse AI receipt (or invoice, while unpaid)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    W, H = A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def money(x):                      # the PDF font has no naira sign
        return f"NGN {float(x or 0):,.0f}"
    c.setTitle(f"GymPulse AI {'receipt' if paid else 'invoice'} {number(inv)}")
    navy, ink, muted, line = colors.HexColor("#0B1020"), colors.HexColor("#111827"), \
        colors.HexColor("#5B6678"), colors.HexColor("#E5E9F0")
    # header band
    c.setFillColor(navy)
    c.rect(0, H - 36 * mm, W, 36 * mm, fill=1, stroke=0)
    logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gympulse-email-logo.png")
    try:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(logo)
        iw, ih = img.getSize()
        h = 12 * mm
        c.drawImage(img, 18 * mm, H - 24 * mm, width=h * iw / ih, height=h, mask="auto")
    except Exception:
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(18 * mm, H - 21 * mm, "GymPulse AI")
    c.setFillColor(colors.HexColor("#B7F34A"))
    c.rect(0, H - 37 * mm, W, 1 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(W - 18 * mm, H - 19 * mm, "Receipt" if paid else "Invoice")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#C9D3E3"))
    c.drawRightString(W - 18 * mm, H - 26 * mm, number(inv))

    y = H - 52 * mm
    def label_value(x, y, label, value, bold=False):
        c.setFont("Helvetica", 8.5)
        c.setFillColor(muted)
        c.drawString(x, y, label.upper())
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.setFillColor(ink)
        c.drawString(x, y - 5.5 * mm, gw._text(value, "–"))

    when = gw._text(inv.get("paid_at") if paid else inv.get("created_at"))[:10]
    try:
        when = datetime.fromisoformat(when).strftime("%d %B %Y")
    except Exception:
        pass
    label_value(18 * mm, y, "Date paid" if paid else "Date", when, True)
    label_value(78 * mm, y, "Paid with" if paid else "Status", METHOD_LABEL.get(inv.get("method"), "–")
                if paid else "Awaiting payment")
    label_value(150 * mm, y, "Amount", money(inv.get("amount")), True)

    y -= 22 * mm
    c.setFont("Helvetica", 8.5)
    c.setFillColor(muted)
    c.drawString(18 * mm, y, "BILLED TO")
    c.drawString(110 * mm, y, "FROM")
    c.setFillColor(ink)
    lines_to = [inv.get("business_name"), inv.get("billing_name"), inv.get("billing_email"), inv.get("billing_phone"),
                ", ".join(x for x in (inv.get("address"), inv.get("city"), inv.get("state")) if x) or None]
    lines_from = ["GymPulse AI", "usegympulseai.com", "emmanuel@usegympulseai.com", "Lagos, Nigeria"]
    for i, t in enumerate([x for x in lines_to if x]):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 10.5 if i == 0 else 9.5)
        c.drawString(18 * mm, y - (6 + i * 5) * mm, gw._text(t)[:60])
    for i, t in enumerate(lines_from):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 10.5 if i == 0 else 9.5)
        c.drawString(110 * mm, y - (6 + i * 5) * mm, t)

    # line items
    y -= 42 * mm
    c.setStrokeColor(line)
    c.setFillColor(colors.HexColor("#F6F8FB"))
    c.rect(18 * mm, y - 2 * mm, W - 36 * mm, 9 * mm, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(muted)
    c.drawString(21 * mm, y + 1 * mm, "DESCRIPTION")
    c.drawString(120 * mm, y + 1 * mm, "PERIOD")
    c.drawRightString(W - 21 * mm, y + 1 * mm, "AMOUNT")
    y -= 10 * mm
    cycle = "Yearly" if inv.get("period") == "yearly" else f"{inv.get('months') or 1} month" + \
        ("s" if (inv.get("months") or 1) != 1 else "")
    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(ink)
    c.drawString(21 * mm, y, f"GymPulse AI {gw._text(inv.get('plan'), 'subscription')} plan")
    c.setFont("Helvetica", 9)
    c.setFillColor(muted)
    c.drawString(21 * mm, y - 5 * mm, f"{cycle} subscription")
    period = "–"
    if inv.get("period_start") and inv.get("period_end"):
        try:
            a = datetime.fromisoformat(str(inv["period_start"])[:10])
            b = datetime.fromisoformat(str(inv["period_end"])[:10])
            period = f"{a:%d %b %Y} – {b:%d %b %Y}"
        except Exception:
            pass
    c.setFont("Helvetica", 9.5)
    c.setFillColor(ink)
    c.drawString(120 * mm, y, period)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawRightString(W - 21 * mm, y, money(inv.get("amount")))
    y -= 12 * mm
    c.line(18 * mm, y, W - 18 * mm, y)
    y -= 8 * mm
    for label, value, bold in (("Subtotal", money(inv.get("amount")), False), ("VAT", "NGN 0", False),
                               ("Total paid" if paid else "Total due", money(inv.get("amount")), True)):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 9.5)
        c.setFillColor(ink if bold else muted)
        c.drawString(120 * mm, y, label)
        c.drawRightString(W - 21 * mm, y, value)
        y -= 7 * mm
    if inv.get("reference"):
        c.setFont("Helvetica", 8.5)
        c.setFillColor(muted)
        c.drawString(18 * mm, y - 4 * mm, f"Payment reference: {inv['reference']}")

    # footer
    c.setFillColor(muted)
    c.setFont("Helvetica", 8.5)
    c.drawString(18 * mm, 20 * mm, "Thank you for choosing GymPulse AI. Questions about this "
                                   + ("receipt" if paid else "invoice") + ": emmanuel@usegympulseai.com")
    c.drawString(18 * mm, 15 * mm, "GymPulse AI · Smarter insights. Stronger member retention. · usegympulseai.com")
    c.showPage()
    c.save()
    return buf.getvalue()


# ------------------------------------------------------------------ receipt email
def send_receipt(sc, inv, extra_to=None):
    """Email the receipt (with PDF) from GymPulse AI. Sends once per invoice."""
    import base64
    import requests
    import gympulse_admin as gadm
    import gympulse_email as ge
    if inv.get("receipt_sent_at"):
        return True
    key = gadm._env("RESEND_API_KEY")
    to = [e for e in {gw._text(inv.get("billing_email")).lower(), gw._text(extra_to).lower()} if "@" in e]
    if not (key and to):
        return False
    first = gw._text(inv.get("billing_name")).split(" ")[0] or "there"
    until = ""
    try:
        until = datetime.fromisoformat(str(inv.get("period_end"))[:10]).strftime("%d %B %Y")
    except Exception:
        pass
    body = (f'<p style="margin:0 0 10px">Hi {ge.esc(first)},</p>'
            f'<p style="margin:0 0 6px">Thank you for your payment. Your GymPulse AI '
            f'<b>{ge.esc(inv.get("plan"))}</b> plan is active' + (f" until <b>{ge.esc(until)}</b>" if until else "")
            + '. Your receipt is attached.</p>'
            + ge.details([("Receipt", ge.esc(number(inv))), ("Plan", ge.esc(f"{inv.get('plan')} · "
                          + ("Yearly" if inv.get("period") == "yearly" else "Monthly"))),
                          ("Amount paid", ge.esc(money(inv.get("amount")))),
                          ("Paid with", ge.esc(METHOD_LABEL.get(inv.get("method"), "–"))),
                          ("Business", ge.esc(inv.get("business_name") or "–"))])
            + ge.button("Open GymPulse AI", ge.SITE))
    try:
        r = requests.post("https://api.resend.com/emails", timeout=25, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("BILLING_FROM", "GymPulse AI <billing@usegympulseai.com>"),
                                "to": to, "reply_to": "emmanuel@usegympulseai.com",
                                "subject": f"Your GymPulse AI receipt {number(inv)}",
                                "html": ge.layout("Payment received", body,
                                                  preheader=f"Receipt {number(inv)} · {money(inv.get('amount'))}"),
                                "text": (f"Hi {first},\n\nThank you for your payment of {money(inv.get('amount'))} for "
                                         f"GymPulse AI {inv.get('plan')}. Receipt {number(inv)} is attached.\n\n{ge.SITE}"),
                                "attachments": [{"filename": f"GymPulse-AI-receipt-{number(inv)}.pdf",
                                                 "content": base64.b64encode(receipt_pdf(inv)).decode()}]})
        if r.status_code < 300:
            update(sc, inv, receipt_sent_at=_now())
            return True
    except Exception as error:
        try:
            import gympulse_monitoring as gmon
            gmon.capture(error, "receipt email")
        except Exception:
            pass
    return False
