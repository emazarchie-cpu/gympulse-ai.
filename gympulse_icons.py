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

try:
    from PIL import Image
except Exception:          # Pillow missing: the PNG icons still work
    Image = None

ICON_VERSION = 4
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
    sized = _write_sizes(static_dir)
    with open(index, encoding="utf-8") as f:
        html = f.read()
    # drop every earlier icon link, then add the versioned ones
    html = re.sub(r'\s*<link[^>]+rel="(?:shortcut icon|icon|apple-touch-icon)"[^>]*>', "", html)
    links = (('<link rel="icon" href="/favicon.ico" sizes="48x48">' if sized else "")
             + "".join(f'<link rel="icon" type="image/png" sizes="{n}x{n}" href="/gympulse-icon-v{ICON_VERSION}-{n}.png">'
                       for n in (sized or ()))
             + f'<link rel="icon" type="image/png" sizes="256x256" href="./{icon_name}">'
             f'<link rel="shortcut icon" href="./{icon_name}">'
             f'<link rel="apple-touch-icon" sizes="180x180" href="./{touch_name}">')
    html = html.replace("</head>", links + "</head>", 1)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[gympulse_icons] icon v{ICON_VERSION} installed")
    return True


def _write_sizes(static_dir):
    """favicon.ico (what Google and old browsers ask for first) and PNGs at the sizes Google
    shows in search results (multiples of 48). Returns the PNG sizes written."""
    if Image is None or not os.path.exists(FAVICON):
        return ()
    try:
        img = Image.open(FAVICON).convert("RGBA")
        img.save(os.path.join(static_dir, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
        sizes = (48, 96, 192)
        for n in sizes:
            img.resize((n, n), Image.LANCZOS).save(
                os.path.join(static_dir, f"gympulse-icon-v{ICON_VERSION}-{n}.png"))
        return sizes
    except Exception as error:
        print(f"[gympulse_icons] extra sizes skipped: {error}")
        return ()
