"""One branded email template for everything GymPulse AI sends.

The header is a single image (navy background, logo, lime-to-cyan line) so it
looks the same in light and dark mode in every inbox. The rest is a white card in light mode and switches to
GymPulse navy in dark mode, in the apps that support it (Apple Mail, Outlook, most phone mail apps); Gmail
keeps its own handling. Change the brand once
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

# Dark mode: the same email in GymPulse navy. [data-ogsc] is Outlook.com's dark mode.
_DARK = {"page": "#0A0F1E", "card": "#10172A", "line": "#24314F", "ink": "#EEF2FA", "body": "#C9D3E3",
         "muted": "#9AA6BF", "soft": "#141D33"}


def _dark_css():
    d = _DARK
    rules = (f".gp-page{{background:{d['page']}!important}}"
             f".gp-card{{background:{d['card']}!important;border-color:{d['line']}!important}}"
             f".gp-ink{{color:{d['ink']}!important}}"
             f".gp-body,.gp-body p,.gp-body div,.gp-body td,.gp-body li,.gp-body span{{color:{d['body']}!important}}"
             f".gp-body b,.gp-body strong{{color:{d['ink']}!important}}"
             f".gp-body a{{color:{BRAND['cyan']}!important}}"
             f".gp-body a.gp-btn,.gp-body a.gp-btn span{{color:#0A0F1E!important}}"
             f".gp-body a.gp-btn2{{color:{d['ink']}!important}}"
             f".gp-btn2-bg{{background:{d['soft']}!important}}"
             f".gp-muted,.gp-muted a{{color:{d['muted']}!important}}"
             f".gp-line{{border-color:{d['line']}!important}}"
             f".gp-dk,.gp-body .gp-dk{{color:{d['muted']}!important}}"
             f".gp-dv,.gp-body .gp-dv{{color:{d['ink']}!important}}"
             f".gp-code,.gp-body .gp-code{{background:{d['soft']}!important;color:{d['ink']}!important}}")
    outlook = rules.replace(".gp-", "[data-ogsc] .gp-")
    return f"@media (prefers-color-scheme: dark){{{rules}}}{outlook}"


def esc(v):
    return _html.escape("" if v is None else str(v))


def button(label, url, primary=True):
    """A button that renders in Gmail, Outlook and Apple Mail."""
    bg = BRAND["lime"] if primary else "#EEF1F6"
    cls = "gp-btn" if primary else "gp-btn2"
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" style="display:inline-table;margin:6px 8px 0 0">'
            f'<tr><td class="{"" if primary else "gp-btn2-bg"}" style="border-radius:10px;background:{bg}">'
            f'<a href="{url}" class="{cls}" style="display:inline-block;padding:13px 22px;font-family:Arial,Helvetica,sans-serif;'
            f'font-size:15px;font-weight:700;color:#0A0F1E;text-decoration:none;border-radius:10px">{esc(label)}</a>'
            f'</td></tr></table>')


def details(rows):
    """Label / value rows. Values may contain HTML (already escaped)."""
    cells = "".join(
        f'<tr><td class="gp-dk" style="padding:7px 0;color:{BRAND["muted"]};width:130px;vertical-align:top;font-size:14px">{esc(k)}</td>'
        f'<td class="gp-dv" style="padding:7px 0;color:{BRAND["ink"]};font-weight:600;font-size:14px">{v}</td></tr>' for k, v in rows)
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" width="100%" class="gp-line" '
            f'style="border-top:1px solid {BRAND["line"]};border-bottom:1px solid {BRAND["line"]};margin:14px 0">{cells}</table>')


def code_box(code):
    """A big one-time code, for password resets and sign-in codes."""
    return (f'<div class="gp-code" style="margin:16px 0;padding:16px;border-radius:12px;background:#F1F4F8;text-align:center;'
            f'font-family:Menlo,Consolas,monospace;font-size:30px;letter-spacing:8px;font-weight:700;color:{BRAND["ink"]}">'
            f'{code}</div>')


def gym_header(name, logo_url="", color="#B7F34A", dark="#0B1020", light_bg=False):
    """The gym's own header for emails to its members: logo and name side by side,
    on the gym's colour, with an accent line. Members see at a glance who wrote."""
    bg = "#FFFFFF" if light_bg else dark
    ink = "#0A0F1E" if light_bg else "#FFFFFF"
    name_html = (f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:19px;line-height:1.25;'
                 f'font-weight:700;color:{ink}">{esc(name)}</div>')
    if logo_url:
        brand = (f'<table role="presentation" cellspacing="0" cellpadding="0"><tr>'
                 f'<td valign="middle" style="padding-right:14px"><img src="{esc(logo_url)}" alt="{esc(name)}" height="56" '
                 f'style="display:block;height:56px;max-width:180px;width:auto;border:0"></td>'
                 f'<td valign="middle">{name_html}</td></tr></table>')
    else:
        brand = name_html.replace("font-size:19px", "font-size:22px")
    return (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="{bg}" '
            f'style="background-color:{bg};background-image:linear-gradient({bg},{bg})"><tr>'
            f'<td style="padding:20px 28px">{brand}</td></tr>'
            f'<tr><td height="4" bgcolor="{color}" style="height:4px;line-height:4px;font-size:0;'
            f'background-color:{color};background-image:linear-gradient({color},{color})">&nbsp;</td></tr></table>')


def layout(title, body_html, preheader="", footer_html="", gym=None):
    """The full email: header image, title, body, footer. With gym={"gym", "logo_url",
    "color", "dark"} it's a letter from that gym to its member: the gym's header,
    the gym named in the footer, and a small "Sent with GymPulse AI" line."""
    b = BRAND
    if gym:
        header = gym_header(gym.get("gym") or "Your gym", gym.get("logo_url"), gym.get("color") or b["lime"],
                            gym.get("dark") or b["navy"], gym.get("light_bg", False))
        foot = (f'{footer_html}{"<br><br>" if footer_html else ""}Sent by {esc(gym.get("gym") or "your gym")}. '
                'Questions? Reply to this email.')
        after = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#8A94A6;padding:12px">'
                 'Sent with GymPulse AI</div>')
    else:
        header = (f'<a href="{b["site"]}"><img src="{b["header_img"]}" width="600" alt="{esc(b["name"])}" '
                  'style="display:block;width:100%;max-width:600px;height:auto;border:0"></a>')
        foot = (f'{footer_html}{"<br><br>" if footer_html else ""}{esc(b["address_line"])}<br>'
                f'Questions? Reply to this email or write to <a href="mailto:{b["support"]}" '
                f'style="color:{b["muted"]}">{b["support"]}</a>.')
        after = ""
    pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(preheader)}</div>'
           if preheader else "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<style>:root{{color-scheme:light dark}}{_dark_css()}</style>
<title>{esc(title)}</title></head>
<body class="gp-page" style="margin:0;padding:0;background:{b['page']}">{pre}
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="gp-page" style="background:{b['page']}">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" class="gp-card"
       style="max-width:600px;background:#FFFFFF;border-radius:16px;overflow:hidden;border:1px solid {b['line']}">
<tr><td style="padding:0;line-height:0;background:{b['navy']}">{header}</td></tr>
<tr><td style="padding:28px 28px 8px;font-family:Arial,Helvetica,sans-serif;color:{b['ink']}">
  <h1 class="gp-ink" style="margin:0 0 10px;font-size:22px;line-height:1.3;color:{b['ink']}">{esc(title)}</h1>
  <div class="gp-body" style="font-size:15px;line-height:1.6;color:#2B3445">{body_html}</div>
</td></tr>
<tr><td class="gp-muted" style="padding:18px 28px 26px;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:{b['muted']}">
  {foot}
</td></tr>
</table>{after}</td></tr></table></body></html>"""
