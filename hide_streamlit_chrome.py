"""White-label the web page shell, so visitors only ever see GymPulse AI.

Runs at start-up (before the app server starts) and again from app.py, so it applies even if the start
command doesn't run it. Safe to run any number of times.

* Hides the framework's toolbar (running figure, Stop, three-dot menu) and paints the page dark from the
  first moment, so nothing flashes before the app loads.
* Renames the page title and replaces the framework's own messages (connecting, "server is not
  responding", "cannot load frontend code"…) with GymPulse AI wording.
* Installs the GymPulse favicon and phone icon.
"""
import glob
import os
import sys

import streamlit

MARK = "gp-early-style"
CSS = (
    '<style id="gp-early-style">'
    "html,body,#root,.stApp{background:#0B1020 !important;}"
    '[data-testid="stToolbar"],[data-testid="stStatusWidget"],'
    '[data-testid="stMainMenu"],[data-testid="stHeader"],'
    '[data-testid="stDecoration"],[data-testid="stAppDeployButton"],'
    "header{display:none !important;}"
    "</style>"
    '<meta name="theme-color" content="#0B1020">'
)
BRAND = "GymPulse AI"
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
        if MARK not in new:
            new = new.replace("</head>", CSS + "</head>", 1)
        new = new.replace("<title>Streamlit</title>", f"<title>{BRAND}</title>")
        for old, rep in TEXT:
            new = new.replace(old, rep)
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
