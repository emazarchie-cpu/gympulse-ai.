"""GymPulse AI · Search engines (SEO).

The app itself is drawn in the browser, so a search engine reading usegympulseai.com used to see an
almost empty page. This module, run at start-up by hide_streamlit_chrome.apply(), fixes that:

* head_tags()      title, description, canonical link, social preview tags and structured data
                   (who the company is, what the software does, its price) in the page <head>.
* prerender()      the landing page text inside <div id="root">, so search engines read real words.
                   The app replaces it the moment it loads (and it's hidden at once on app links
                   such as ?hmo= or ?guide=, so members never see it).
* write_static()   robots.txt, sitemap.xml and one plain, fast page per topic gym owners search for
                   (served at /gym-management-software-nigeria.html and so on; the web server
                   redirects folder-style URLs, so plain .html files are used).

Google Search Console: set the env var GOOGLE_SITE_VERIFICATION to the code Google gives
(the content="…" part of its meta tag) and redeploy.
"""
import html
import json
import os
import re
from datetime import date

SITE = (os.environ.get("APP_URL") or "https://usegympulseai.com").rstrip("/")
GOOGLE_VERIFY = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
NAME = "GymPulse AI"
TITLE = "GymPulse AI · Gym member retention software for Nigeria"
DESCRIPTION = ("GymPulse AI shows Nigerian gym owners which members are about to stop coming, then "
               "brings them back with WhatsApp and email renewals, follow-up calls and referrals. "
               "Check-ins, payments and a member app included. 30-day free trial.")
COMPANY = {"legal": "GYMPULSE AI LTD", "rc": "RC 9996401",
           "city": "Calabar", "state": "Cross River State",
           "email": "hello@usegympulseai.com", "founder_email": "emmanuel@usegympulseai.com"}
START = "<!--gp-seo-start-->"
END = "<!--gp-seo-end-->"
ROOT_START = "<!--gp-pre-start-->"
ROOT_END = "<!--gp-pre-end-->"


def _lowest_price():
    try:
        import gympulse_billing
        return min(int(p["monthly"]) for p in gympulse_billing.DEFAULT_PLANS if p.get("monthly"))
    except Exception:
        return 20000


def _naira(n):
    return f"₦{n:,}"


# ---------------------------------------------------------------- topic pages
# Each page answers one thing gym owners search for, in our own words.
PAGES = [
    {
        "slug": "gym-management-software-nigeria",
        "title": "Gym management software for Nigeria · GymPulse AI",
        "description": "Gym software built for Nigerian gyms: members, check-ins, payments in naira, "
                       "renewal reminders on WhatsApp and a warning before members stop coming.",
        "h1": "Gym management software built for Nigerian gyms",
        "lead": "Run your members, check-ins, payments and renewals in one place, and see who is about "
                "to leave before they do. Made in Nigeria, priced in naira, works on any phone.",
        "sections": [
            ("Everything a Nigerian gym needs", [
                "Member records with photos, plans and renewal dates",
                "QR check-in at the front desk, with HMO and corporate members",
                "Payments and renewals in naira, with receipts that carry your gym's name",
                "Staff logins, so coaches and front desk only see what they need",
                "A member app with workouts, progress, classes and how busy the gym is now",
            ]),
            ("Why owners switch", [
                "Spreadsheets and paper registers don't tell you who is drifting away",
                "Most members who cancel stop coming weeks before they say anything",
                "GymPulse AI scores every member daily and tells you who to call first",
            ]),
        ],
    },
    {
        "slug": "gym-member-retention",
        "title": "Gym member retention: keep members from cancelling · GymPulse AI",
        "description": "See which gym members are likely to cancel, why, and what to do about it. "
                       "Automatic WhatsApp check-ins, follow-up calls and renewal offers.",
        "h1": "Keep gym members from cancelling",
        "lead": "Members rarely quit out of the blue. Visits slow down, renewals get close, and nobody "
                "notices in time. GymPulse AI notices for you.",
        "sections": [
            ("How it works", [
                "Every member gets a risk score from their visits, plan and renewal date",
                "Each flag comes with the reason, e.g. visits down 60% in the last month",
                "A suggested next step for each member: a check-in message, a call or a renewal offer",
                "Send all suggested messages in one tap, or share them out between your staff",
                "If a member doesn't reply, a follow-up call is set up automatically",
            ]),
            ("Check the predictions yourself", [
                "Prediction check saves every score at the start of the month",
                "At the end it shows who actually left, and how many GymPulse flagged in advance",
                "So you can see how accurate it is for your own gym, with your own members",
            ]),
        ],
    },
    {
        "slug": "gym-whatsapp-renewal-reminders",
        "title": "WhatsApp renewal reminders for gyms · GymPulse AI",
        "description": "Automatic WhatsApp and email reminders before a gym membership ends, plus "
                       "missed-visit check-ins and welcome-back messages.",
        "h1": "Automatic WhatsApp renewal reminders for your gym",
        "lead": "Remind members before their plan ends, check in when they miss a few visits, and "
                "welcome them back, without typing the same message a hundred times.",
        "sections": [
            ("Messages that go out by themselves", [
                "Renewal reminders before a membership ends",
                "A friendly check-in when a regular stops coming",
                "Welcome-back notes, milestone shout-outs and birthday wishes",
                "Bring-a-friend invites with automatic rewards",
            ]),
            ("Personal, not spam", [
                "Each message uses the member's name, goal and your gym's name",
                "Members can reply, and replies land in your follow-ups",
                "You choose what goes out automatically and what you approve first",
            ]),
        ],
    },
    {
        "slug": "switch-from-gymmaster-or-excel",
        "title": "Moving from GymMaster or Excel · GymPulse AI",
        "description": "Bring your gym members, visit history and photos into GymPulse AI from "
                       "GymMaster, Excel or any gym software in minutes.",
        "h1": "Moving your gym from GymMaster, Excel or other software",
        "lead": "Export your members and visits as a spreadsheet, upload them, and GymPulse AI starts "
                "scoring your members the same day.",
        "sections": [
            ("How to move, step by step", [
                "1. Export your members from GymMaster, Mindbody, Glofox or your spreadsheet as CSV or Excel",
                "2. Upload the file on the Import screen in GymPulse AI, from 10 members up to 20,000",
                "3. Check the columns: GymPulse AI guesses which column is the name, phone, plan and expiry "
                "date, and you can correct any guess",
                "4. Check the plans: each membership name becomes a GymPulse plan you can rename",
                "5. Press Import. Members already in GymPulse AI are matched by email, phone or name, so "
                "nobody is added twice",
                "6. Changed your mind? Every import can be undone in one click",
            ]),
            ("What comes across", [
                "Members, plans, prices, join and expiry dates",
                "Visit history, so risk scores are accurate from day one",
                "Member photos, matched by member ID from a ZIP file",
                "Thousands of members at once",
            ]),
            ("What you get on top", [
                "A daily list of members at risk of leaving, with the reason",
                "Automatic renewal and check-in messages",
                "A member app with workouts, classes and gym busyness",
            ]),
        ],
    },
    {
        "slug": "gym-hmo-members",
        "title": "HMO and corporate members at your gym · GymPulse AI",
        "description": "Check in HMO enrollees and company-paid members with a QR code and get a monthly "
                       "visits report per HMO for your claims, with no paper register.",
        "h1": "HMO and corporate members at your gym",
        "lead": "Health plans like Reliance, Hygeia, AXA Mansard and Leadway pay you for their members' gym "
                "visits. GymPulse AI records every HMO visit for you, so claiming is a download, not a paper "
                "register.",
        "sections": [
            ("How HMO members check in", [
                "Put your gym's HMO QR code at the front desk",
                "The first time, the member scans it and types their HMO ID or phone number",
                "After that they get a personal link to save on their phone and check in with one tap",
                "Each visit is saved as an HMO visit, kept apart from your regular members' visits",
            ]),
            ("What the owner gets", [
                "A monthly visits report for each HMO, ready to download for claims",
                "Import an HMO's member list from CSV or Excel, or add one member at a time",
                "Each member's HMO, HMO ID, employer and cover end date in one place",
                "A warning when covers end in the next 30 days, so you can follow up in time",
            ]),
        ],
    },
]


def _ld_json():
    org = {
        "@context": "https://schema.org", "@type": "Organization", "name": NAME,
        "legalName": COMPANY["legal"], "url": SITE + "/", "logo": SITE + "/apple-touch-icon.png",
        "email": COMPANY["email"], "identifier": COMPANY["rc"],
        "founder": {"@type": "Person", "name": "Emmanuel Archibong", "email": COMPANY["founder_email"]},
        "contactPoint": [{"@type": "ContactPoint", "contactType": "customer support", "email": COMPANY["email"],
                          "areaServed": "NG", "availableLanguage": "English"},
                         {"@type": "ContactPoint", "contactType": "sales", "email": COMPANY["founder_email"],
                          "areaServed": "NG", "availableLanguage": "English"}],
        "address": {"@type": "PostalAddress", "addressLocality": COMPANY["city"],     # city only: no street
                    "addressRegion": COMPANY["state"], "addressCountry": "NG"},
    }
    app = {
        "@context": "https://schema.org", "@type": "SoftwareApplication", "name": NAME,
        "applicationCategory": "BusinessApplication", "operatingSystem": "Web, iOS, Android",
        "url": SITE + "/", "description": DESCRIPTION, "areaServed": "NG",
        "offers": {"@type": "Offer", "price": str(_lowest_price()), "priceCurrency": "NGN",
                   "description": "Monthly plan by gym size, 30-day free trial"},
        "publisher": {"@type": "Organization", "name": COMPANY["legal"]},
    }
    return "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>'
                   for x in (org, app))


def head_tags():
    e = html.escape
    tags = [
        f'<meta name="description" content="{e(DESCRIPTION)}">',
        f'<link rel="canonical" href="{SITE}/">',
        '<meta name="robots" content="index, follow">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{NAME}">',
        f'<meta property="og:title" content="{e(TITLE)}">',
        f'<meta property="og:description" content="{e(DESCRIPTION)}">',
        f'<meta property="og:url" content="{SITE}/">',
        f'<meta property="og:image" content="{SITE}/apple-touch-icon.png">',
        '<meta property="og:locale" content="en_NG">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{e(TITLE)}">',
        f'<meta name="twitter:description" content="{e(DESCRIPTION)}">',
    ]
    if GOOGLE_VERIFY:
        tags.append(f'<meta name="google-site-verification" content="{e(GOOGLE_VERIFY)}">')
    return START + "".join(tags) + _ld_json() + END


# ---------------------------------------------------------------- shared look
CSS = """
*{box-sizing:border-box}body{margin:0;background:#0B1020;color:#E8ECF5;font:16px/1.6 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}a{color:#B6F23A}.w{max-width:880px;margin:0 auto;padding:0 18px}
.nav{display:flex;justify-content:space-between;align-items:center;padding:18px 0;gap:12px;flex-wrap:wrap}
.logo{font-weight:800;letter-spacing:.06em;color:#fff;text-decoration:none}.logo span{color:#B6F23A}
.btn{display:inline-block;padding:11px 18px;border-radius:999px;font-weight:700;text-decoration:none;
border:1px solid #2A3350;color:#E8ECF5;margin:4px 8px 4px 0}.btn.p{background:#B6F23A;color:#0B1020;border:0}
h1{font-size:clamp(28px,5vw,44px);line-height:1.15;margin:34px 0 14px}h2{font-size:22px;margin:34px 0 8px}
.lead{font-size:18px;color:#B7C0D6}ul,ol{padding-left:20px}li{margin:6px 0}.card{background:#121A30;
border:1px solid #1F2945;border-radius:16px;padding:6px 22px 14px;margin:18px 0}
.foot{color:#7F8AA6;font-size:13px;padding:34px 0 40px;border-top:1px solid #1F2945;margin-top:40px}
.links a{margin-right:14px;display:inline-block}
"""


def _nav():
    return (f'<div class="nav"><a class="logo" href="/">GYM<span>PULSE</span> AI</a>'
            f'<div><a class="btn" href="/?demo=book">Book a demo</a>'
            f'<a class="btn p" href="/">Start free trial</a></div></div>')


def _links(skip=None):
    items = [f'<a href="/{p["slug"]}.html">{html.escape(p["h1"])}</a>' for p in PAGES if p["slug"] != skip]
    return '<div class="links">' + "".join(items) + "</div>"


def _foot():
    c = COMPANY
    return (f'<div class="foot">{_links()}<p>© {date.today().year} {c["legal"]} · {c["rc"]} · Registered in '
            f'Nigeria · {c["city"]}, {c["state"]} · '
            f'<a href="mailto:{c["email"]}">{c["email"]}</a> · Founder: '
            f'<a href="mailto:{c["founder_email"]}">{c["founder_email"]}</a></p></div>')


def _sections(sections):
    out = []
    for heading, items in sections:
        steps = all(re.match(r"\d+\. ", i) for i in items)      # "1. …" items become a numbered list
        tag = "ol" if steps else "ul"
        texts = [re.sub(r"^\d+\. ", "", i) for i in items] if steps else items
        lis = "".join(f"<li>{html.escape(t)}</li>" for t in texts)
        out.append(f'<div class="card"><h2>{html.escape(heading)}</h2><{tag}>{lis}</{tag}></div>')
    return "".join(out)


def _cta():
    return (f'<h2>Try it free for 30 days</h2><p>Every feature on every plan, from '
            f'{_naira(_lowest_price())} a month by gym size. Setting up takes about a minute.</p>'
            f'<a class="btn p" href="/">Start your free trial</a>'
            f'<a class="btn" href="/?demo=book">Book a 15-minute demo</a>')


def page_html(p):
    e = html.escape
    url = f"{SITE}/{p['slug']}.html"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(p['title'])}</title><meta name="description" content="{e(p['description'])}">
<link rel="canonical" href="{url}"><meta name="robots" content="index, follow">
<meta property="og:type" content="article"><meta property="og:title" content="{e(p['title'])}">
<meta property="og:description" content="{e(p['description'])}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/apple-touch-icon.png"><meta name="theme-color" content="#0B1020">
<link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" type="image/png" sizes="192x192" href="/gympulse-icon-v4-192.png"><link rel="apple-touch-icon" sizes="180x180" href="/gympulse-touch-v4.png">
<style>{CSS}</style></head><body><div class="w">{_nav()}
<h1>{e(p['h1'])}</h1><p class="lead">{e(p['lead'])}</p>{_sections(p['sections'])}{_cta()}{_foot()}
</div></body></html>"""


def prerender():
    """The homepage words for search engines, shown until the app loads."""
    feats = _sections([
        ("Know who's about to leave", [
            "Every member scored daily from their visits, plan and renewal date, with the reason",
            "Revenue at risk in naira, and a short list of who to call first",
            "Prediction check: see for yourself how many leavers GymPulse flagged in advance",
        ]),
        ("Bring them back automatically", [
            "WhatsApp and email renewal reminders and missed-visit check-ins",
            "Follow-up calls when a member doesn't reply",
            "Bring-a-friend referrals with automatic rewards",
        ]),
        ("Run the gym", [
            "QR check-in, including HMO and corporate members",
            "Payments, renewals and receipts in naira; staff logins",
            "A member app: workouts, progress, classes and how busy the gym is now",
            "Import from GymMaster, Excel or any software",
        ]),
    ])
    # the style sits inside #root too, so it disappears with the text when the app takes over
    body = (f'<div id="gp-pre"><style>{CSS}</style>'
            f'<div class="w">{_nav()}<h1>Keep more gym members. Keep more revenue.</h1>'
            f'<p class="lead">{html.escape(DESCRIPTION)}</p>{feats}{_cta()}{_foot()}</div></div>'
            # app links (member portal, HMO check-in, machine guides…) never show this
            # People never see it: the app's own landing page (same words) loads a moment later, so it
            # stays hidden for browsers and is only read by search engines and link previews.
            '<script>if(location.search||!/bot|crawl|spider|slurp|preview|facebookexternalhit|lighthouse/i'
            '.test(navigator.userAgent))document.getElementById("gp-pre").style.display="none"</script>')
    return ROOT_START + body + ROOT_END


def robots_txt():
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n"


def sitemap_xml():
    today = date.today().isoformat()
    urls = [(SITE + "/", "1.0")] + [(f"{SITE}/{p['slug']}.html", "0.8") for p in PAGES]
    rows = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod><priority>{pr}</priority></url>"
                   for u, pr in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n')


def _strip(text, a, b):
    while a in text and b in text.split(a, 1)[1]:
        before, rest = text.split(a, 1)
        text = before + rest.split(b, 1)[1]
    return text


def apply_index(index_html):
    """Return index.html with the SEO head tags and the prerendered homepage (replacing older copies)."""
    out = _strip(_strip(index_html, START, END), ROOT_START, ROOT_END)
    out = out.replace("<head>", "<head>" + head_tags(), 1)       # at the top: stable order, read first
    out = out.replace('<div id="root"></div>', f'<div id="root">{prerender()}</div>', 1)
    if f'<title>{NAME}</title>' in out:
        out = out.replace(f'<title>{NAME}</title>', f'<title>{html.escape(TITLE)}</title>', 1)
    return out


def write_static(static_dir):
    """robots.txt, sitemap.xml and the topic pages, served from the app's own web root."""
    files = {"robots.txt": robots_txt(), "sitemap.xml": sitemap_xml()}
    for p in PAGES:
        files[p["slug"] + ".html"] = page_html(p)
    n = 0
    for rel, text in files.items():
        path = os.path.join(static_dir, rel)
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    continue
        except OSError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        n += 1
    return n
