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
    return f'<section class="sec"><h2>Questions gym owners ask</h2><div class="body">{items}</div></section>'
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
            ("Built on the research", [
                "Most members who quit do so in their first few months, and their visits slow down first",
                "Days without a visit are one of the strongest signs a member will leave",
                "Personal contact from staff and a good start keep more members coming",
                "Read the full summary, with sources: usegympulseai.com/why-gym-members-leave-research.html",
            ]),
        ],
    },
    {
        "slug": "why-gym-members-leave-research",
        "title": "Why gym members leave, and what keeps them: the research · GymPulse AI",
        "description": "What studies and gym data say about when members quit, the warning signs, and what "
                       "keeps them coming, with the numbers for Nigerian gyms and the sources.",
        "h1": "Why gym members leave, and what keeps them",
        "lead": "A summary of the research on gym member retention: when members are most likely to quit, "
                "the signs that show up first, and what actually keeps them. Each point lists its source, and "
                "we say where a figure comes from industry surveys rather than published studies.",
        "sections": [
            ("When members leave", [
                "The first weeks are the riskiest. UK operator The Gym Group reports its highest rate of "
                "leaving is in the first 45 days, before a habit has formed",
                "Industry reports put roughly half of the members who quit inside their first 90 days, so the "
                "first three months decide most of a gym's retention",
                "New habits take time to become automatic: a University College London study found a median of "
                "66 days, ranging from 18 to over 200, and exercise tends to sit at the slower end",
            ]),
            ("The warning signs come first", [
                "A study of 5,209 members of a fitness centre in Lisbon used machine learning to predict who "
                "would drop out. The strongest signals were days without a visit, how long the member had "
                "been with the gym, and how much they had paid",
                "In other words, members show they are leaving through their visits weeks before they cancel. "
                "Comparing each member with their own normal pattern catches that slide early",
                "Industry studies consistently find that members who visit more often in their first month "
                "are far more likely to still be members a year later",
            ]),
            ("Why members say they cancel", [
                "Industry surveys most often list cost, and not using the membership enough to justify the "
                "cost, followed by moving away",
                "The two are linked: a member who stops coming starts to feel the fee isn't worth it. Getting "
                "them back in the door early also protects the renewal",
            ]),
            ("What keeps members coming", [
                "A proper start: industry research links an orientation plus a few follow-ups in the first "
                "weeks to much higher retention at six months",
                "Personal contact from staff: industry studies suggest that regular, genuine check-ins from "
                "staff lead to more visits and fewer cancellations",
                "Classes and people: members who join group classes or have friends at the gym are reported "
                "to cancel less often than those who train alone",
                "These figures come from gym-industry research and software companies, not peer-reviewed "
                "studies, so treat the exact percentages as a guide. The direction is consistent across all of them",
            ]),
            ("The picture in Nigeria", [
                "Nigerians spent about ₦32.8 billion on gym subscriptions in 2025, roughly ₦90 million a day, "
                "according to Moniepoint transaction data",
                "Monthly plans are becoming the norm rather than yearly ones, which means a member can leave "
                "every month, and every renewal counts",
                "A 2026 market review found that most Nigerian gyms still can't say how many of their members "
                "are actually still coming",
                "Large chains are growing fast, which makes keeping members, not just signing them up, the "
                "difference for independent gyms",
            ]),
            ("How GymPulse AI uses this", [
                "Days since the last visit, compared with each member's own habits, drive the daily risk score, "
                "the strongest signal in the research",
                "New members get extra attention in their first weeks, with check-ins while the habit is forming",
                "Each flagged member comes with a suggested personal step (a trainer call, a WhatsApp message, a "
                "class invite) because personal contact is what keeps people",
                "Members who renew soon and are coming less are flagged before the renewal date",
                "Every outcome is recorded, so each gym sees what actually works for its own members",
            ]),
        ],
        "sources": [
            ("Predicting Fitness Centre Dropout (study of 5,209 members, PMC)",
             "https://pmc.ncbi.nlm.nih.gov/articles/PMC8508547/"),
            ("How long does it take to form a habit? (University College London, Lally et al.)",
             "https://www.ucl.ac.uk/news/2009/aug/how-long-does-it-take-form-habit"),
            ("Gym retention statistics and benchmarks (includes The Gym Group's annual report)",
             "https://blog.jericommerce.com/resources/gyms-fitness-studios-retention-statistics"),
            ("Gym member engagement and staff interactions (Glofox)",
             "https://www.glofox.com/blog/gym-member-engagement/"),
            ("Nigerians spent ₦32.8 billion on gym subscriptions in 2025 (Moniepoint data)",
             "https://thenotesphere.com/nigerians-spent-%E2%82%A632-8-billion-annually-on-gym-subscriptions-in-2025/"),
            ("FirstRep H1 2026 Market Pulse: the state of Nigeria's gym industry",
             "https://www.firstrep.xyz/blog/firstrep-h1-2026-market-pulse-the-state-of-nigeria-s-gym-industry"),
            ("From one Lagos gym to 30 locations (Forbes Africa)",
             "https://www.forbesafrica.com/current-affairs/2026/10/03/from-one-lagos-gym-to-30-locations-in-nigeria-how-verod-backed-fitness-firm-is-now-eyeing-accra-and-abidjan"),
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
    # short link: usegympulseai.com/case-study opens the case study page (the server only serves .html files)
    tags.append('<script>if(/^\\/case-study\\/?$/.test(location.pathname))'
                'location.replace("/case-study.html"+location.search)</script>')
    return START + "".join(tags) + _ld_json() + END


# ---------------------------------------------------------------- shared look
CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0A0F1E;color:#E6EAF2;font:17px/1.65 'Instrument Sans',-apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
a{color:#B7F34A;text-underline-offset:3px}
.w{max-width:1040px;margin:0 auto;padding:0 20px}
.nav{display:flex;justify-content:space-between;align-items:center;padding:20px 0;gap:12px;flex-wrap:wrap;
border-bottom:1px solid #1B2338}
.logo{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;font-size:19px;color:#fff;text-decoration:none}
.logo span{color:#B7F34A}
.btn{display:inline-block;padding:11px 18px;border-radius:10px;font-weight:600;font-size:15px;text-decoration:none;
border:1px solid #2A3350;color:#E6EAF2;margin:4px 8px 4px 0}.btn:hover{border-color:#4A5675}
.btn.p{background:#B7F34A;color:#0A0F1E;border-color:#B7F34A}.btn.p:hover{background:#C6F76A}
.nav .btn{padding:9px 14px;font-size:14px;margin:0 0 0 8px}
.eyebrow{color:#8C99B2;font-size:15px;margin:56px 0 0}
h1,h2,h3{font-family:'Bricolage Grotesque',sans-serif;font-weight:700;color:#F4F6FB}
h1{font-size:clamp(34px,5.4vw,58px);line-height:1.04;letter-spacing:-.02em;margin:10px 0 18px;max-width:20ch}
.lead{font-size:clamp(18px,2vw,21px);line-height:1.55;color:#B4BED2;max-width:62ch;margin:0 0 48px}
h2{font-size:24px;line-height:1.2;margin:0}
h3{font-size:18px;margin:22px 0 4px}
.sec{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px 48px;padding:34px 0;border-top:1px solid #1B2338}
.sec ul,.sec ol{margin:0;padding:0;list-style:none;counter-reset:n}
.sec li{padding:12px 0 12px 28px;border-bottom:1px solid #151C2E;position:relative;color:#D3DAE7}
.sec li:first-child{padding-top:2px}.sec li:last-child{border-bottom:0}
.sec ul li:before{content:"";position:absolute;left:2px;top:23px;width:12px;height:2px;background:#B7F34A}
.sec ul li:first-child:before{top:13px}
.sec ol li{counter-increment:n}
.sec ol li:before{content:counter(n);position:absolute;left:0;top:12px;font-family:'Bricolage Grotesque',sans-serif;
font-weight:700;color:#B7F34A;font-size:16px}.sec ol li:first-child:before{top:2px}
.sec .body > h3:first-child{margin-top:0}
.sec .body p{margin:0 0 6px;color:#C3CCDC}
.cta{margin:40px 0 0;padding:40px;background:#121A2E;border-radius:16px;border:1px solid #1F2945}
.cta h2{font-size:clamp(26px,3.4vw,34px);margin:0 0 8px}.cta p{color:#B4BED2;margin:0 0 20px;max-width:56ch}
.foot{color:#7F8AA6;font-size:14px;padding:40px 0 48px;margin-top:48px;border-top:1px solid #1B2338}
.foot h2{font-size:17px;margin:0 0 12px;color:#E6EAF2}
.links{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 32px;margin-bottom:28px}
.links a{color:#C3CCDC;text-decoration:none;font-size:15px}.links a:hover{color:#B7F34A;text-decoration:underline}
.foot p a{color:#C3CCDC}
.card{margin:18px 0}
@media(max-width:760px){
 body{font-size:16px}.eyebrow{margin-top:36px}.lead{margin-bottom:32px}
 .sec{grid-template-columns:1fr;gap:14px;padding:28px 0}
 .cta{padding:26px 20px}.links{grid-template-columns:1fr}
 .nav .btn{margin:0 0 0 6px}
}
"""
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" '
         'href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/'
         'css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&family=Instrument+Sans:wght@400;600&display=swap">')


def _nav():
    return (f'<div class="nav"><a class="logo" href="/">GYM<span>PULSE</span> AI</a>'
            f'<div><a class="btn" href="/?demo=book">Book a demo</a>'
            f'<a class="btn p" href="/">Start free trial</a></div></div>')


def _links(skip=None):
    items = [f'<a href="/{p["slug"]}.html">{html.escape(p["h1"])}</a>' for p in PAGES if p["slug"] != skip]
    return '<div class="links">' + "".join(items) + "</div>"


def _foot():
    c = COMPANY
    return (f'<div class="foot"><h2>More guides for gym owners</h2>{_links()}<p>© {date.today().year} {c["legal"]} · {c["rc"]} · Registered in '
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
        out.append(f'<section class="sec"><h2>{html.escape(heading)}</h2><div class="body"><{tag}>{lis}</{tag}></div>'
                   f'</section>')
    return "".join(out)


def _cta():
    return (f'<div class="cta"><h2>Try it free for 30 days</h2><p>Every feature on every plan, from '
            f'{_naira(_lowest_price())} a month by gym size. Setting up takes about a minute.</p>'
            f'<a class="btn p" href="/">Start your free trial</a>'
            f'<a class="btn" href="/?demo=book">Book a 15-minute demo</a></div>')


def page_html(p):
    e = html.escape
    url = f"{SITE}/{p['slug']}.html"
    faq = _faq_html(p["faq"]) if p.get("faq") else ""
    if p.get("sources"):
        items = "".join(f'<li><a href="{html.escape(u)}" rel="noopener" target="_blank">{html.escape(t)}</a></li>'
                        for t, u in p["sources"])
        faq += f'<section class="sec"><h2>Sources</h2><div class="body"><ul>{items}</ul></div></section>'
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
{FONTS}<style>{CSS}</style>{ld}</head><body><div class="w">{_nav()}
<p class="eyebrow">Guide for gym owners</p><h1>{e(p['h1'])}</h1><p class="lead">{e(p['lead'])}</p>{_sections(p['sections'])}{faq}{_cta()}{_foot()}
</div></body></html>"""


# ---------------------------------------------------------------- case study (usegympulseai.com/case-study)
CASE = {
    "slug": "case-study",
    "title": "Case study: bringing back a member who went quiet for 33 days · GymPulse AI",
    "description": "Noah, a personal training client at a gym in Lagos, stopped coming for 33 days without "
                   "cancelling. Five weeks of check-ins later he walked back in. What happened and what it "
                   "means for gym owners.",
    "h1": "Bringing back a member who went quiet for 33 days",
    "lead": "Noah didn't cancel. He didn't complain. He just stopped coming. This is how he came back.",
    "facts": [("Member", "Noah"), ("Where", "A gym in Lagos"), ("Days away", "33"),
              ("Follow-ups", "Calls, voice notes and messages")],
    "member": "Noah trained on a one-month personal training package, 16 September to 16 October 2026. He was "
              "one of the most consistent clients and barely missed a session.",
    "drift": "On 16 October his package ended. Work pressure took over, then life got in the way, and he "
             "stopped coming. He never cancelled and never complained. He simply drifted, the way most members "
             "leave a gym: not loudly, just slowly, until the habit is gone.",
    "timeline": [
        ("Late Oct", "He said work would leave him too exhausted for sessions for two weeks. His trainer offered "
                     "to move sessions to the evening and sent his month 1 progress report to keep his results "
                     "in view."),
        ("28 Oct", "A call and a voice note. He replied that he was all good, just stressed out."),
        ("3 to 4 Nov", "He needed more time. His trainer switched him to a lighter plan and told him there was "
                       "no pressure to rush back."),
        ("12 to 13 Nov", "Another check-in. He said he could slowly begin his sessions the next week."),
        ("15 Nov", "A call asking for a specific day. He committed to Wednesday: “Thanks for checking in "
                   "bro.”"),
        ("18 Nov", "A call and a voice note: “I will be at the gym today.” He came in and trained."),
    ],
    "result": "After 33 days away, Noah walked back in on 18 November and trained.",
    "lessons": [
        "Most members who leave never cancel. They fade, and the warning signs show weeks before they're gone.",
        "One general message isn't enough. Regular, personal check-ins kept the door open.",
        "A specific day (“See you Wednesday?”) works better than “come back soon”.",
        "With check-ins recorded live, GymPulse AI flags a drop like this within days, with the reason and the "
        "next step, while one call is still enough. It works alongside GymMaster, Excel or whatever you use.",
    ],
    "note": "A note on the data: this happened while GymPulse AI was still being built. Noah's visits come from "
            "his trainer's own session records, not live check-ins, and the follow-ups come from the trainer's "
            "WhatsApp chat with him. It is one member's story, not a statistic. It is shared with his "
            "first name only.",
}

CASE_CSS = """
.facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;border-top:1px solid #1B2338;padding:22px 0 30px;margin:0}.facts div{padding:0}
.facts span{display:block;color:#8C99B2;font-size:14px}.facts b{font-family:'Bricolage Grotesque',sans-serif;font-size:20px;line-height:1.3}
.sec .tl{list-style:none;padding:0;margin:0;border-left:2px solid #2A3350}
.sec .tl li{position:relative;padding:4px 0 16px 24px;margin:0;border:0}
.sec .tl li:before,.sec .tl li:first-child:before{content:"";position:absolute;left:-7px;top:10px;width:12px;height:12px;border-radius:50%;
background:#0A0F1E;border:2px solid #4A5675}.sec .tl li:last-child:before{background:#B7F34A;border-color:#B7F34A}
.tl time{display:block;font-weight:700;color:#E8ECF5}.tl p{margin:2px 0 0;color:#B7C0D6}
.result{font-family:'Bricolage Grotesque',sans-serif;font-size:clamp(22px,2.6vw,28px);line-height:1.25;font-weight:700;color:#F4F6FB;margin:0}
.note{color:#7F8AA6;font-size:14px;border-top:1px solid #1B2338;padding-top:20px;margin:0;max-width:72ch}
@media(max-width:640px){.facts{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""


def case_html():
    e = html.escape
    c = CASE
    url = f"{SITE}/{c['slug']}"
    facts = "".join(f"<div><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in c["facts"])
    tl = "".join(f"<li><time>{e(d)}</time><p>{e(t)}</p></li>" for d, t in c["timeline"])
    lessons = "".join(f"<li>{e(t)}</li>" for t in c["lessons"])
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": c["h1"],
          "description": c["description"], "url": url, "datePublished": "2026-11-19",
          "author": {"@type": "Person", "name": "Emmanuel Archibong"},
          "publisher": {"@type": "Organization", "name": NAME, "url": SITE + "/"}}
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(c['title'])}</title><meta name="description" content="{e(c['description'])}">
<link rel="canonical" href="{url}"><meta name="robots" content="index, follow">
<meta property="og:type" content="article"><meta property="og:title" content="{e(c['h1'])}">
<meta property="og:description" content="{e(c['description'])}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/apple-touch-icon.png"><meta name="theme-color" content="#0B1020">
<link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" type="image/png" sizes="192x192" href="/gympulse-icon-v4-192.png"><link rel="apple-touch-icon" sizes="180x180" href="/gympulse-touch-v4.png">
{FONTS}<style>{CSS}{CASE_CSS}</style><script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>
</head><body><div class="w">{_nav()}
<p class="eyebrow">Case study</p>
<h1>{e(c['h1'])}</h1><p class="lead">{e(c['lead'])}</p>
<div class="facts">{facts}</div>
<section class="sec"><h2>The member</h2><div class="body"><p>{e(c['member'])}</p></div></section>
<section class="sec"><h2>What happened</h2><div class="body"><p>{e(c['drift'])}</p></div></section>
<section class="sec"><h2>Five weeks of check-ins</h2><div class="body"><ol class="tl">{tl}</ol></div></section>
<section class="sec"><h2>The result</h2><div class="body"><div class="result">{e(c['result'])}</div></div></section>
<section class="sec"><h2>What this means for gym owners</h2><div class="body"><ul>{lessons}</ul></div></section>
<p class="note">{e(c['note'])}</p>
{_cta()}{_foot()}
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
    lines += [f"- [Case study: {CASE['h1']}]({SITE}/{CASE['slug']}.html): {CASE['description']}"]
    return "\n".join(lines) + "\n"


def robots_txt():
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n"


def sitemap_xml():
    today = date.today().isoformat()
    urls = ([(SITE + "/", "1.0")] + [(f"{SITE}/{p['slug']}.html", "0.8") for p in PAGES]
            + [(f"{SITE}/{CASE['slug']}.html", "0.7")])
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
    files[CASE["slug"] + ".html"] = case_html()
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
