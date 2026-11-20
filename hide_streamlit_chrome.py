"""White-label the web page shell, so visitors only ever see GymPulse AI.

Runs at start-up (before the app server starts) and again from app.py, so it applies even if the start
command doesn't run it. Safe to run any number of times.

* Hides the framework's toolbar (running figure, Stop, three-dot menu) and paints the page dark from the
  first moment, so nothing flashes before the app loads.
* Renames the page title and replaces the framework's own messages (connecting, "server is not
  responding", "cannot load frontend code"…) with GymPulse AI wording.
* Installs the GymPulse favicon and phone icon.
* Search engines: page description, structured data, readable homepage text, robots.txt, sitemap.xml
  and topic pages (gympulse_seo.py).
"""
import glob
import os
import sys

import streamlit

MARK = "gp-early-style"
CSS = (
    '<style id="gp-early-style">'
    "html,body,#root,.stApp{background:#0E0F12 !important;}"
    '[data-testid="stToolbar"],[data-testid="stStatusWidget"],'
    '[data-testid="stMainMenu"],[data-testid="stHeader"],'
    '[data-testid="stDecoration"],[data-testid="stAppDeployButton"],'
    "header{display:none !important;}"
    # the framework's grey placeholder bars look broken: hidden, the GymPulse loading screen shows instead
    '[data-testid="stAppSkeleton"],[data-testid="stSkeleton"]{display:none !important;}'
    "#gp-splash{position:fixed;inset:0;z-index:999999;background:#0E0F12;display:flex;align-items:center;"
    "justify-content:center;transition:opacity .25s}"
    "#gp-splash img{width:56px;height:56px;border-radius:14px;animation:gp-beat 1.4s ease-in-out infinite}"
    "#gp-splash.plain img{display:none}"
    "@keyframes gp-beat{0%,100%{transform:scale(1);opacity:.9}50%{transform:scale(1.06);opacity:1}}"
    "@media (prefers-reduced-motion:reduce){#gp-splash img{animation:none}}"
    # the page stays hidden behind the loading screen until its styles have arrived (no unstyled flash)
    'html:not(.gp-ready) [data-testid="stMain"]{visibility:hidden}'
    "html.gp-ready #gp-splash{opacity:0;pointer-events:none;visibility:hidden}"
    "</style>"
    '<meta name="theme-color" content="#0E0F12">'
)
BRAND = "GymPulse AI"
# Loading screen shown from the first moment until the app draws: the GymPulse mark on the dark page.
# On gym links (anything with ?…, e.g. member portals) it stays plain, without our logo; search
# engines never see it; and it removes itself after 30 seconds whatever happens.
SPLASH_MARK = 'id="gp-splash"'
SPLASH = (
    '<div id="gp-splash" aria-hidden="true"><img src="/gympulse-icon-v4-192.png" alt=""></div>'
    "<script>(function(){var d=document,h=d.documentElement,s=d.getElementById('gp-splash'),t=0;"
    "function ready(){if(h.classList.contains('gp-ready'))return;h.classList.add('gp-ready');"
    "setTimeout(function(){if(s)s.remove()},400)}"
    "if(location.search&&s)s.className='plain';"
    "if(/bot|crawl|spider|slurp|preview|facebookexternalhit|lighthouse/i.test(navigator.userAgent)){ready();return}"
    # ready when the app's styles are on the page (gympulse_design marks them), or 1.5 s after the
    # first real content on pages without them; 30 s at most whatever happens
    "function check(){if(d.querySelector('.gp-css-ready')){ready();return}"
    "if(!t&&d.querySelector('[data-testid=\"stMain\"] :is(h1,h2,h3,button,input,img)'))t=setTimeout(ready,1500)}"
    "new MutationObserver(check).observe(h,{childList:true,subtree:true});setTimeout(ready,30000)})()</script>"
)
# Site ownership tags read by crawlers in the page <head> (raw HTML, before any script runs).
# Meta domain verification for usegympulseai.com (Business settings -> Brand safety -> Domains).
# Can be overridden without a code change with the env var FB_DOMAIN_VERIFICATION.
FB_DOMAIN_VERIFICATION = os.environ.get("FB_DOMAIN_VERIFICATION", "").strip() or "ihoguxqqe8vfas2adyy06brasy5ffq"
HEAD_MARK = "gp-site-verification"
TEXT = [  # (framework wording, GymPulse wording) in the page and its script files
    ("Streamlit server is not responding. Are you connected to the internet?",
     "GymPulse AI isn't responding. Check your internet connection, then refresh the page."),
    ("Is Streamlit still running? If you accidentally stopped Streamlit, just restart it in your terminal:",
     "GymPulse AI is restarting. Please wait a moment, then refresh the page."),
    ("streamlit run yourscript.py", "Pull down or tap refresh to try again"),
    ("Unable to connect to Streamlit server", "Can't connect to GymPulse AI"),
    ("Connecting to Streamlit server", "Connecting to GymPulse AI"),
    ("Cannot load Streamlit frontend code. This can happen when you update Streamlit while a Streamlit app is running.",
     "GymPulse AI was just updated. Please refresh the page."),
    ("Made with Streamlit v", "GymPulse AI v"),
    ("Streamlit logo", "GymPulse AI logo"),
    ("Streamlit Community Cloud", "GymPulse AI"),
    ("You need to enable JavaScript to run this app.", "Please turn on JavaScript to use GymPulse AI."),
]


def apply(quiet=False):
    static = os.path.join(os.path.dirname(streamlit.__file__), "static")
    path = os.path.join(static, "index.html")
    changed = 0
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
        new = html
        import re as _re
        if CSS not in new:                                   # missing or an older version: put in the latest
            new = _re.sub(r'<style id="gp-early-style">.*?</style><meta name="theme-color" content="#0E0F12">', "",
                          new, flags=_re.S)
            new = new.replace("</head>", CSS + "</head>", 1)
        if SPLASH not in new:                                # missing or an older version: put in the latest
            new = _re.sub(r'<div id="gp-splash".*?</script>', "", new, count=1, flags=_re.S)
            new = _re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + SPLASH, new, count=1)
        new = new.replace("<title>Streamlit</title>", f"<title>{BRAND}</title>")
        new = _re.sub(r'<meta name="facebook-domain-verification"[^>]*>\s*', "", new)   # replace an old code
        if FB_DOMAIN_VERIFICATION and not FB_DOMAIN_VERIFICATION.startswith("__"):
            new = new.replace("<head>", '<head>\n    <meta name="facebook-domain-verification" '
                                        f'content="{FB_DOMAIN_VERIFICATION}" />', 1)
        for old, rep in TEXT:
            new = new.replace(old, rep)
        try:                                       # search engines: description, structured data,
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # readable homepage
            import gympulse_seo
            new = gympulse_seo.apply_index(new)
            changed += gympulse_seo.write_static(static)
        except Exception as error:
            if not quiet:
                print(f"[white-label] SEO skipped: {error}")
        if new != html:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            changed += 1
        for js in glob.glob(os.path.join(static, "static", "js", "*.js")):
            with open(js, encoding="utf-8") as f:
                code = f.read()
            out = code
            for old, rep in TEXT:
                out = out.replace(old, rep)
            if out != code:
                with open(js, "w", encoding="utf-8") as f:
                    f.write(out)
                changed += 1
    except OSError as error:                       # read-only install: the app still works
        if not quiet:
            print(f"[white-label] skipped: {error}")
        return 0
    if not quiet:
        print(f"[white-label] {'updated ' + str(changed) + ' file(s)' if changed else 'already applied'}")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gympulse_icons
        gympulse_icons.install(static)
    except Exception:
        pass
    return changed


if __name__ == "__main__":
    apply()
