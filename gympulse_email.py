"""One branded email template for everything GymPulse AI sends.

The header is a single image (navy background, logo, lime-to-cyan line) so it
looks the same in light and dark mode in every inbox. Change the brand once
here and every email follows: demo bookings, and the Supabase account emails
built by scripts/build_email_templates.py.
"""
import html as _html
import os

SITE = os.environ.get("APP_URL", "https://usegympulseai.com").rstrip("/")
BRAND = {
    "name": "GymPulse AI",
    "header_img": f"{SITE}/app/static/gympulse-email-header.png",
    "site": SITE,
    "address_line": "GymPulse AI · Smarter insights. Stronger member retention.",
    "support": "emmanuel@usegympulseai.com",
    "ink": "#111827", "muted": "#5B6678", "line": "#E5E9F0", "page": "#F3F5F9",
    "lime": "#B7F34A", "cyan": "#35D6ED", "navy": "#0B1020",
}


def esc(v):
    return _html.escape("" if v is None else str(v))


def button(label, url, primary=True):
    """A button that renders in Gmail, Outlook and Apple Mail."""
    bg = BRAND["lime"] if primary else "#EEF1F6"
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" style="display:inline-table;margin:6px 8px 0 0">'
            f'<tr><td style="border-radius:10px;background:{bg}">'
            f'<a href="{url}" style="display:inline-block;padding:13px 22px;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:15px;font-weight:700;color:#0A0F1E;text-decoration:none;border-radius:10px">{esc(label)}</a>'
            f'</td></tr></table>')


def details(rows):
    """Label / value rows. Values may contain HTML (already escaped)."""
    cells = "".join(
        f'<tr><td style="padding:7px 0;color:{BRAND["muted"]};width:130px;vertical-align:top;font-size:14px">{esc(k)}</td>'
        f'<td style="padding:7px 0;color:{BRAND["ink"]};font-weight:600;font-size:14px">{v}</td></tr>' for k, v in rows)
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" width="100%" '
            f'style="border-top:1px solid {BRAND["line"]};border-bottom:1px solid {BRAND["line"]};margin:14px 0">{cells}</table>')


def code_box(code):
    """A big one-time code, for password resets and sign-in codes."""
    return (f'<div style="margin:16px 0;padding:16px;border-radius:12px;background:#F1F4F8;text-align:center;'
            f'font-family:Menlo,Consolas,monospace;font-size:30px;letter-spacing:8px;font-weight:700;color:{BRAND["ink"]}">'
            f'{code}</div>')


def layout(title, body_html, preheader="", footer_html=""):
    """The full email: header image, title, body, footer."""
    b = BRAND
    pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(preheader)}</div>'
           if preheader else "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light">
<title>{esc(title)}</title></head>
<body style="margin:0;padding:0;background:{b['page']}">{pre}
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{b['page']}">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="max-width:600px;background:#FFFFFF;border-radius:16px;overflow:hidden;border:1px solid {b['line']}">
<tr><td style="padding:0;line-height:0;background:{b['navy']}">
  <a href="{b['site']}"><img src="{b['header_img']}" width="600" alt="{esc(b['name'])}"
     style="display:block;width:100%;max-width:600px;height:auto;border:0"></a></td></tr>
<tr><td style="padding:28px 28px 8px;font-family:Arial,Helvetica,sans-serif;color:{b['ink']}">
  <h1 style="margin:0 0 10px;font-size:22px;line-height:1.3;color:{b['ink']}">{esc(title)}</h1>
  <div style="font-size:15px;line-height:1.6;color:#2B3445">{body_html}</div>
</td></tr>
<tr><td style="padding:18px 28px 26px;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:{b['muted']}">
  {footer_html}{'<br><br>' if footer_html else ''}{esc(b['address_line'])}<br>
  Questions? Reply to this email or write to <a href="mailto:{b['support']}" style="color:{b['muted']}">{b['support']}</a>.
</td></tr>
</table></td></tr></table></body></html>"""
