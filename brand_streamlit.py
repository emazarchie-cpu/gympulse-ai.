"""Replace Streamlit's default tab title and icon with GymPulse AI's.

Streamlit serves a static starting page (index.html) before your app code runs.
That page says "Streamlit" and shows the Streamlit icon. This script edits it
once, so visitors see GymPulse AI from the first moment the tab opens.

Run it AFTER Streamlit is installed and BEFORE the app starts:
    python brand_streamlit.py
It is safe to run every time the server starts (it can be repeated).
"""
import os
import re
import shutil
import sys

TITLE = "GymPulse AI"
HERE = os.path.dirname(os.path.abspath(__file__))
FAVICON_SOURCE = os.path.join(HERE, "GymPulse_AI_favicon.png")


def find_static_dir():
    # Optional override, mainly for testing: python brand_streamlit.py /path/to/static
    if len(sys.argv) > 1:
        return sys.argv[1]
    import streamlit
    return os.path.join(os.path.dirname(streamlit.__file__), "static")


def main():
    static_dir = find_static_dir()
    index_path = os.path.join(static_dir, "index.html")

    if not os.path.isfile(index_path):
        print(f"[brand_streamlit] index.html not found in {static_dir}")
        return 1

    # 1. Title
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    new_html, count = re.subn(
        r"<title>.*?</title>",
        f"<title>{TITLE}</title>",
        html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if count == 0:
        print("[brand_streamlit] WARNING: no <title> tag found, title not changed")
    elif new_html != html:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(new_html)
        print(f"[brand_streamlit] title set to '{TITLE}'")
    else:
        print("[brand_streamlit] title already set")

    # 2. Icon: overwrite the file the starting page already points to
    if not os.path.isfile(FAVICON_SOURCE):
        print(f"[brand_streamlit] WARNING: {FAVICON_SOURCE} not found, icon not changed")
        return 0

    targets = ["favicon.png", "favicon.ico"]
    replaced = []
    for name in targets:
        path = os.path.join(static_dir, name)
        if os.path.isfile(path):
            shutil.copyfile(FAVICON_SOURCE, path)
            replaced.append(name)

    # Make sure the page links to a PNG we just wrote
    if not replaced:
        shutil.copyfile(FAVICON_SOURCE, os.path.join(static_dir, "favicon.png"))
        replaced.append("favicon.png")
        print("[brand_streamlit] favicon.png was missing, created it")

    print(f"[brand_streamlit] icon replaced: {', '.join(replaced)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
