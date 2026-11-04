"""Install the current GymPulse AI icon into Streamlit's starting page.

Browsers and phones cache a site's icon by its file name, so an old icon can
keep showing long after it was replaced. The icon is installed under a
versioned name (gympulse-icon-v<N>.png); bump ICON_VERSION whenever the icon
file changes and every browser fetches the new one.

Used by hide_streamlit_chrome.py and brand_streamlit.py, so whichever start
script Render runs, the new icon is served.
"""
import os
import re
import shutil

ICON_VERSION = 3
HERE = os.path.dirname(os.path.abspath(__file__))
FAVICON = os.path.join(HERE, "GymPulse_AI_favicon.png")
TOUCH = os.path.join(HERE, "apple-touch-icon.png")


def install(static_dir):
    index = os.path.join(static_dir, "index.html")
    if not os.path.isfile(index):
        print(f"[gympulse_icons] index.html not found in {static_dir}")
        return False
    icon_name = f"gympulse-icon-v{ICON_VERSION}.png"
    touch_name = f"gympulse-touch-v{ICON_VERSION}.png"
    if os.path.exists(FAVICON):
        for name in (icon_name, "favicon.png"):
            shutil.copyfile(FAVICON, os.path.join(static_dir, name))
    if os.path.exists(TOUCH):
        for name in (touch_name, "apple-touch-icon.png"):
            shutil.copyfile(TOUCH, os.path.join(static_dir, name))
    with open(index, encoding="utf-8") as f:
        html = f.read()
    # drop every earlier icon link, then add the versioned ones
    html = re.sub(r'\s*<link[^>]+rel="(?:shortcut icon|icon|apple-touch-icon)"[^>]*>', "", html)
    links = (f'<link rel="icon" type="image/png" sizes="256x256" href="./{icon_name}">'
             f'<link rel="shortcut icon" href="./{icon_name}">'
             f'<link rel="apple-touch-icon" sizes="180x180" href="./{touch_name}">')
    html = html.replace("</head>", links + "</head>", 1)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[gympulse_icons] icon v{ICON_VERSION} installed")
    return True
