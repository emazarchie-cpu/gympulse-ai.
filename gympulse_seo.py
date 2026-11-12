"""GymPulse AI · Search engines (SEO).

The app itself is drawn in the browser, so a search engine reading usegympulseai.com used to see an
almost empty page. This module, run at start-up by hide_streamlit_chrome.apply(), fixes that:

* head_tags()      title, description, canonical link, social preview tags and structured data
                   (who the company is, what the software does, its price) in the page <head>.
* prerender()      the landing page text inside <div id="root">, so search engines read real words.
                   The app replaces it the moment it loads (and it's hidden at once on app links
                   such as ?hmo= or ?guide=, so members never see it).
* write_static()   robots.txt, sitemap.xml and one plain, fast page per topic gym owners search for
* IndexNow         when a page changes on a deploy, Bing (and the other IndexNow engines) are told at once
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
# IndexNow key: public by design (search engines read it from SITE/<key>.txt to confirm the site is ours).
INDEXNOW_KEY = os.environ.get("INDEXNOW_KEY") or "f848cdbe83c604ffcb8a19b72cf7f5f3"
INDEXNOW_URL = "https://api.indexnow.org/indexnow"
GOOGLE_VERIFY = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
NAME = "GymPulse AI"
TITLE = "GymPulse AI · Member retention platform for Nigerian gyms"
DESCRIPTION = ("GymPulse AI is a member retention platform for Nigerian gyms. It works alongside GymMaster or "
               "the gym software you already use, shows which members are about to stop coming, and brings "
               "them back with WhatsApp and email renewals and follow-up calls. 30-day free trial.")

# Plain answers to what gym owners (and search engines' AI answers) ask most. Shown in the homepage text and on
# the GymMaster page, and sent as FAQ structured data.
FAQ = [
    ("Does GymPulse AI work alongside GymMaster?",
     "Yes. GymPulse AI is built to run side by side with GymMaster. You keep GymMaster for your doors, front "
     "desk and billing. Paste your GymPulse AI link into GymMaster's Webhook Manager (Settings → Integrations) "
     "and every check-in in GymMaster comes across to GymPulse AI as it happens, with no double entry. Your member "
     "list comes from a GymMaster export: upload a fresh one now and then (weekly is enough) and new members and "
     "renewals are added without duplicates."),
    ("Is GymPulse AI a replacement for GymMaster?",
     "No. GymPulse AI is a member retention platform, not gym management software. It doesn't replace GymMaster, "
     "your door access or your billing. It adds what they don't do: a daily list of members who are about to "
     "stop coming, the reason, and WhatsApp and email follow-ups to bring them back. It also includes class "
     "timetables and bookings, a member app and QR check-in, for gyms that want them."),
    ("Do my staff have to enter anything twice?",
     "No. Check-ins come from GymMaster automatically and members come from your export. Your staff keep working "
     "in GymMaster exactly as they do today."),
    ("What if my gym uses other software, or Excel?",
     "GymPulse AI works with any software that can export a spreadsheet, such as Mindbody, Glofox, Excel or Google "
     "Sheets. Gyms with no software can use GymPulse AI's own QR check-in."),
    ("Is GymPulse AI available now?",
     "Yes. GymPulse AI launched in 2026 and is open to gyms across Nigeria. Sign up at usegympulseai.com for a "
     "30-day free trial; paid plans are billed through Paystack. It is made by GYMPULSE AI LTD (RC 9996401) in "
     "Calabar, and is not connected to other products with \"GymPulse\" in their name."),
    ("What does GymPulse AI cost?",
     "Plans are priced by gym size, in naira, with every feature on every plan and a 30-day free trial. Chains get "
     "up to 20% off each branch."),
]


def _faq_ld(faq):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                            "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}


def _faq_html(faq):
    items = "".join(f"<h3>{html.escape(q)}</h3><p>{html.escape(a)}</p>" for q, a in faq)
    return f'<div class="card"><h2>Questions gym owners ask</h2>{items}</div>'
COMPANY = {"legal": "GYMPULSE AI LTD", "rc": "RC 9996401",
           "city": "Calabar", "state": "Cross River State",
           "email": "hello@usegympulseai.com", "founder_email": "emmanuel@usegympulseai.com"}
# Official accounts, so search engines can tell this GymPulse AI apart from other products with a similar name
SOCIAL = ["https://www.instagram.com/usegympulseai", "https://x.com/usegympulseai"]
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
        "title": "Gym management software for Nigeria, built to keep members · GymPulse AI",
        "description": "Looking for gym management software in Nigeria? GymPulse AI is a member retention "
                       "platform: members, check-ins, renewals in naira, WhatsApp reminders and a warning "
                       "before members stop coming.",
        "h1": "More than gym management software: a member retention platform for Nigerian gyms",
        "lead": "Most gym management software records who paid. GymPulse AI also tells you who is about to "
                "leave, and helps you keep them. Members, check-ins and renewals in one place. Made in "
                "Nigeria, priced in naira, works on any phone.",
        "sections": [
            ("Everything you need to keep members", [
                "Member records with photos, plans and renewal dates",
                "QR check-in at the front desk, with HMO and corporate members",
                "Payments and renewals in naira, with receipts that carry your gym's name",
                "Staff logins, so coaches and front desk only see what they need",
                "A member app with workouts, progress, classes and how busy the gym is now",
            ]),
            ("Why retention, not just management", [
                "Spreadsheets, paper registers and most gym software don't tell you who is drifting away",
                "Most members who cancel stop coming weeks before they say anything",
                "GymPulse AI scores every member daily and tells you who to call first",
                "Already use GymMaster or other gym software? Keep it: GymPulse AI works alongside it",
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
        "faq": FAQ[:4],
        "title": "Works with GymMaster: member retention for Nigerian gyms · GymPulse AI",
        "description": "Use GymMaster? Keep it. GymPulse AI connects to GymMaster and adds member "
                       "retention on top. On Excel? Bring members, visits and photos across in minutes.",
        "h1": "Works with GymMaster, Excel or the software you already use",
        "lead": "Keep running your gym in GymMaster. GymPulse AI connects to it, or to your spreadsheet "
                "export, and starts finding the members you're about to lose the same day.",
        "sections": [
            ("Runs side by side with GymMaster: not a replacement", [
                "Keep GymMaster for your doors, front desk and billing: nothing changes for your staff",
                "Paste your GymPulse AI link into GymMaster's Webhook Manager (Settings → Integrations), and "
                "every check-in comes across as it happens, with no double entry",
                "Upload a fresh GymMaster export now and then (weekly is enough) to add new members and renewals",
                "GymPulse AI adds what GymMaster doesn't: a daily list of members at risk, WhatsApp "
                "follow-ups and win-backs",
            ]),
            ("Bring your members in, step by step", [
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
            ("Side by side, with no gap", [
                "Run GymMaster and GymPulse AI side by side for as long as you like",
                "Import a fresh export any time: members already in GymPulse AI are updated, not added twice",
                "No new door hardware: members check in with a QR code at the front desk or in the member app",
                "Members get a private link to their own page: no app store download needed",
                "Payments are recorded in naira, by cash, transfer or POS, so your records continue as before",
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
            ("Claims that get paid", [
                "Each plan's weekly gym sessions are kept to at check-in, so you don't train visits the HMO won't pay for",
                "HMOs that need a code for each visit get it at check-in, saved with the visit",
                "Each month's claim worked out per HMO, per visit or per member, ready to send",
                "See which claims are paid, part paid or queried, and which are still owed",
            ]),
        ],
    },
]


def _ld_json():
    org = {
        "@context": "https://schema.org", "@type": "Organization", "name": NAME,
        "legalName": COMPANY["legal"], "url": SITE + "/", "logo": SITE + "/apple-touch-icon.png",
        "email": COMPANY["email"], "identifier": COMPANY["rc"],
        "sameAs": SOCIAL,
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
                   for x in (org, app, _faq_ld(FAQ)))


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
    faq = _faq_html(p["faq"]) if p.get("faq") else ""
    ld = (f'<script type="application/ld+json">{json.dumps(_faq_ld(p["faq"]), ensure_ascii=False)}</script>'
          if p.get("faq") else "")
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(p['title'])}</title><meta name="description" content="{e(p['description'])}">
<link rel="canonical" href="{url}"><meta name="robots" content="index, follow">
<meta property="og:type" content="article"><meta property="og:title" content="{e(p['title'])}">
<meta property="og:description" content="{e(p['description'])}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/apple-touch-icon.png"><meta name="theme-color" content="#0B1020">
<link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" type="image/png" sizes="192x192" href="/gympulse-icon-v4-192.png"><link rel="apple-touch-icon" sizes="180x180" href="/gympulse-touch-v4.png">
<style>{CSS}</style>{ld}</head><body><div class="w">{_nav()}
<h1>{e(p['h1'])}</h1><p class="lead">{e(p['lead'])}</p>{_sections(p['sections'])}{faq}{_cta()}{_foot()}
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
        ("Works alongside GymMaster and the software you already use", [
            "Keep GymMaster for your doors, front desk and billing: GymPulse AI runs side by side with it",
            "Every GymMaster check-in comes across to GymPulse AI as it happens, through GymMaster's Webhook "
            "Manager: no double entry",
            "Members come from a GymMaster, Mindbody, Glofox or Excel export; re-upload weekly to add new members",
            "No software yet? Use GymPulse AI's own QR check-in, including HMO and corporate members",
        ]),
    ])
    # the style sits inside #root too, so it disappears with the text when the app takes over
    body = (f'<div id="gp-pre"><style>{CSS}</style>'
            f'<div class="w">{_nav()}<h1>Keep more gym members. Keep more revenue.</h1>'
            f'<p class="lead">{html.escape(DESCRIPTION)}</p>{feats}{_faq_html(FAQ)}{_cta()}{_foot()}</div></div>'
            # app links (member portal, HMO check-in, machine guides…) never show this
            # People never see it: the app's own landing page (same words) loads a moment later, so it
            # stays hidden for browsers and is only read by search engines and link previews.
            '<script>if(location.search||!/bot|crawl|spider|slurp|preview|facebookexternalhit|lighthouse/i'
            '.test(navigator.userAgent))document.getElementById("gp-pre").style.display="none"</script>')
    return ROOT_START + body + ROOT_END


def llms_txt():
    """A plain summary for AI assistants and answer engines (llmstxt.org format)."""
    lines = [f"# {NAME}", "", f"> {DESCRIPTION}", "",
             f"{NAME} ({COMPANY['legal']}, {COMPANY['rc']}, {COMPANY['city']}, {COMPANY['state']}, Nigeria) is a "
             "member retention platform for gyms. It is not gym management software and does not replace "
             "GymMaster or other gym software: it runs alongside them.", "", "## Questions", ""]
    lines += [f"- **{q}** {a}" for q, a in FAQ]
    lines += ["", "## Pages", "", f"- [Home]({SITE}/)"]
    lines += [f"- [{p['h1']}]({SITE}/{p['slug']}.html): {p['description']}" for p in PAGES]
    return "\n".join(lines) + "\n"


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


def write_static(static_dir, ping=True):
    """robots.txt, sitemap.xml, the IndexNow key file and the topic pages, served from the app's own web root.
    Topic pages that changed are sent to IndexNow (on the live server only)."""
    files = {"robots.txt": robots_txt(), "sitemap.xml": sitemap_xml(), f"{INDEXNOW_KEY}.txt": INDEXNOW_KEY,
             "llms.txt": llms_txt()}
    for p in PAGES:
        files[p["slug"] + ".html"] = page_html(p)
    n, changed = 0, []
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
        if rel.endswith(".html"):
            changed.append(f"{SITE}/{rel}")
    if changed and ping:
        indexnow([SITE + "/"] + changed)
    return n


def indexnow(urls, wait=False):
    """Tell IndexNow (Bing, Yandex, Seznam, Naver…) these pages changed. Only from the live server (Render),
    in the background, so a slow reply never holds up the app starting. Returns the HTTP status when wait=True."""
    if not urls or not (os.environ.get("RENDER") or wait):
        return None
    host = SITE.split("://", 1)[-1].split("/", 1)[0]
    body = {"host": host, "key": INDEXNOW_KEY, "keyLocation": f"{SITE}/{INDEXNOW_KEY}.txt",
            "urlList": list(dict.fromkeys(urls))[:10000]}

    def send():
        try:
            import requests
            r = requests.post(INDEXNOW_URL, json=body, timeout=15,
                              headers={"Content-Type": "application/json; charset=utf-8"})
            print(f"[seo] IndexNow: {len(body['urlList'])} page(s), status {r.status_code}")
            return r.status_code
        except Exception as error:
            print(f"[seo] IndexNow skipped: {error}")
            return None
    if wait:
        return send()
    import threading
    threading.Thread(target=send, daemon=True).start()
    return None
