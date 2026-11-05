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
def receipt_number(inv):
    n = (inv or {}).get("number")
    return f"{int(n):04d}-{str((inv or {}).get('paid_at') or '')[:4] or 'GP'}" if n else number(inv)


def pay_label(inv):
    """'Card · Visa ending 4081', 'Bank transfer', ... for the receipt."""
    d = (inv or {}).get("pay_detail") or ""
    if d:
        return d
    return {"paystack": "Paystack", "transfer": "Bank transfer", "admin": "Bank transfer"}.get((inv or {}).get("method"), "–")


def _fmt_date(value, fmt="%d %B %Y"):
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime(fmt).lstrip("0")
    except Exception:
        return "–"


def receipt_pdf(inv, paid=True):
    """A clean, white GymPulse AI receipt (or invoice while unpaid): title and logo, numbers, from and
    bill-to, the amount paid, line items, totals and payment history."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    W, H = A4
    L, R = 18 * mm, W - 18 * mm
    ink, muted, rule, soft = (colors.HexColor("#111827"), colors.HexColor("#6B7280"),
                              colors.HexColor("#111827"), colors.HexColor("#E5E7EB"))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    kind = "Receipt" if paid else "Invoice"
    c.setTitle(f"GymPulse AI {kind.lower()} {number(inv)}")
    c.setAuthor("GymPulse AI")

    def money(x):                                   # the PDF font has no naira sign
        return f"NGN {float(x or 0):,.2f}"

    def text(x, y, s, size=9.5, bold=False, color=ink, right=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.setFillColor(color)
        (c.drawRightString if right else c.drawString)(x, y, gw._text(s))

    # title and logo
    y = H - 24 * mm
    text(L, y, kind, 22, True)
    logo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gympulse-logo-dark.png")
    try:
        img = ImageReader(logo)
        iw, ih = img.getSize()
        h = 16 * mm
        c.drawImage(img, R - h * iw / ih, y - 6 * mm, width=h * iw / ih, height=h, mask="auto")
    except Exception:
        text(R, y, "GymPulse AI", 14, True, right=True)

    # numbers
    y -= 13 * mm
    paid_on = _fmt_date(inv.get("paid_at")) if paid else None
    meta = [("Invoice number", number(inv))]
    if paid:
        meta += [("Receipt number", receipt_number(inv)), ("Date paid", paid_on)]
    else:
        meta += [("Date issued", _fmt_date(inv.get("created_at"))), ("Status", "Awaiting payment")]
    for label, value in meta:
        text(L, y, label, 9.5, True)
        text(L + 33 * mm, y, value, 9.5)
        y -= 5.2 * mm

    # from / bill to
    y -= 6 * mm
    text(L, y, "GymPulse AI", 10, True)
    text(L + 88 * mm, y, "Bill to", 10, True)
    seller = ["Lagos", "Nigeria", "usegympulseai.com", "emmanuel@usegympulseai.com"]
    buyer = [inv.get("business_name"), inv.get("billing_name"), inv.get("address"),
             " ".join(x for x in (inv.get("city"), inv.get("state")) if x) or None, "Nigeria",
             inv.get("billing_email"), inv.get("billing_phone")]
    buyer = [b for b in buyer if b]
    for i in range(max(len(seller), len(buyer))):
        y -= 5 * mm
        if i < len(seller):
            text(L, y, seller[i])
        if i < len(buyer):
            text(L + 88 * mm, y, gw._text(buyer[i])[:48])

    # headline
    y -= 14 * mm
    amount = float(inv.get("amount") or 0)
    text(L, y, f"{money(amount)} paid on {paid_on}" if paid else f"{money(amount)} due", 15, True)

    # line items
    y -= 13 * mm
    cols = [(L, "Description", False), (R - 84 * mm, "Qty", True), (R - 46 * mm, "Unit price", True),
            (R - 28 * mm, "Tax", True), (R, "Amount", True)]
    for x, label, right in cols:
        text(x, y, label, 8.5, color=ink, right=right)
    y -= 3 * mm
    c.setStrokeColor(rule)
    c.setLineWidth(1)
    c.line(L, y, R, y)
    y -= 6 * mm
    cycle = "Yearly" if inv.get("period") == "yearly" else (
        "Monthly" if int(inv.get("months") or 1) == 1 else f"{inv.get('months')} months")
    text(L, y, f"GymPulse AI {gw._text(inv.get('plan'), 'subscription')} plan · {cycle}")
    text(R - 84 * mm, y, "1", right=True)
    text(R - 46 * mm, y, money(amount), right=True)
    text(R - 28 * mm, y, "0%", right=True)
    text(R, y, money(amount), right=True)
    if inv.get("period_start") and inv.get("period_end"):
        y -= 4.6 * mm
        text(L, y, f"{_fmt_date(inv['period_start'], '%d %b %Y')} – {_fmt_date(inv['period_end'], '%d %b %Y')}",
             8.5, color=muted)

    # totals
    y -= 11 * mm
    x0 = L + 88 * mm
    rows = [("Subtotal", money(amount), False), ("Total excluding tax", money(amount), False),
            ("VAT (0%)", money(0), False), ("Total", money(amount), False),
            ("Amount paid" if paid else "Amount due", money(amount), True)]
    c.setLineWidth(0.6)
    for label, value, bold in rows:
        c.setStrokeColor(soft)
        c.line(x0, y + 4.2 * mm, R, y + 4.2 * mm)
        text(x0, y, label, 9.5, bold)
        text(R, y, value, 9.5, bold, right=True)
        y -= 6 * mm

    # payment history
    if paid:
        y -= 10 * mm
        text(L, y, "Payment history", 15, True)
        y -= 11 * mm
        hist = [(L, "Payment method", False), (R - 100 * mm, "Date", False), (R - 36 * mm, "Amount paid", True),
                (R, "Receipt number", True)]
        for x, label, right in hist:
            text(x, y, label, 8.5, right=right)
        y -= 3 * mm
        c.setStrokeColor(rule)
        c.setLineWidth(1)
        c.line(L, y, R, y)
        y -= 6 * mm
        text(L, y, pay_label(inv))
        text(R - 100 * mm, y, paid_on)
        text(R - 36 * mm, y, money(amount), right=True)
        text(R, y, receipt_number(inv), right=True)
        if inv.get("reference"):
            y -= 4.6 * mm
            text(L, y, f"Reference {inv['reference']}", 8.5, color=muted)
    else:
        y -= 10 * mm
        text(L, y, "How to pay", 15, True)
        y -= 8 * mm
        text(L, y, f"Pay online from your GymPulse AI Subscription page, or transfer the exact amount using "
                   f"{number(inv)} as the reference.", 9.5)

    # footer
    c.setStrokeColor(soft)
    c.setLineWidth(0.6)
    c.line(L, 22 * mm, R, 22 * mm)
    text(L, 16 * mm, "GymPulse AI · usegympulseai.com · Questions: emmanuel@usegympulseai.com", 8.5, color=muted)
    text(R, 16 * mm, "Page 1 of 1", 8.5, color=muted, right=True)
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
    copy_to = gadm._env("BILLING_COPY_TO")
    if not copy_to:
        try:
            rows = sc.table("platform_settings").select("value").eq("key", "pricing").limit(1).execute().data
            copy_to = ((rows[0]["value"] if rows else {}) or {}).get("contact_email") or ""
        except Exception:
            copy_to = ""
    copy_to = copy_to or "emmanuel@usegympulseai.com"
    bcc = [copy_to] if "@" in copy_to and copy_to.lower() not in to else []
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
            + ge.details([("Receipt", ge.esc(receipt_number(inv))), ("Invoice", ge.esc(number(inv))), ("Plan", ge.esc(f"{inv.get('plan')} · "
                          + ("Yearly" if inv.get("period") == "yearly" else "Monthly"))),
                          ("Amount paid", ge.esc(money(inv.get("amount")))),
                          ("Paid with", ge.esc(pay_label(inv))),
                          ("Business", ge.esc(inv.get("business_name") or "–"))])
            + ge.button("Open GymPulse AI", ge.SITE))
    try:
        r = requests.post("https://api.resend.com/emails", timeout=25, headers={"Authorization": f"Bearer {key}"},
                          json={"from": gadm._env("BILLING_FROM", "GymPulse AI <billing@usegympulseai.com>"),
                                "to": to, **({"bcc": bcc} if bcc else {}), "reply_to": "emmanuel@usegympulseai.com",
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
