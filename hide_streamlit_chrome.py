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

# Install the current GymPulse favicon and touch icon under versioned names,
# so browsers and phones stop showing a cached old icon
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gympulse_icons
gympulse_icons.install(os.path.dirname(path))
