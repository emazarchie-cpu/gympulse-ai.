"""Run once at start-up, before `streamlit run`.

Streamlit's own page shell shows its toolbar (the running figure, Stop and the
three-dot menu) before your app has loaded. This hides them in the shell itself
so nothing flashes, and paints the page dark from the first moment.
"""
import os
import shutil

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

path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
with open(path, encoding="utf-8") as f:
    html = f.read()

if MARK in html:
    print("[hide_streamlit_chrome] already applied")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html.replace("</head>", CSS + "</head>", 1))
    print("[hide_streamlit_chrome] applied")

# Install the GymPulse favicon and touch icon in Streamlit's own static folder
here = os.path.dirname(os.path.abspath(__file__))
static = os.path.dirname(path)
for src, dst in (("GymPulse_AI_favicon.png", "favicon.png"),
                 ("apple-touch-icon.png", "apple-touch-icon.png")):
    source = os.path.join(here, src)
    if os.path.exists(source):
        shutil.copyfile(source, os.path.join(static, dst))
        print(f"[hide_streamlit_chrome] {dst} installed")
    else:
        print(f"[hide_streamlit_chrome] {src} not found, skipped")

with open(path, encoding="utf-8") as f:
    html = f.read()
if "apple-touch-icon" not in html:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html.replace("</head>",
                '<link rel="apple-touch-icon" href="./apple-touch-icon.png"></head>', 1))
