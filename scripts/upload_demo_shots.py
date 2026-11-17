"""Upload the demo screenshots to Supabase Storage (public email-assets bucket,
demo-video/shots/) and print each link. Runs from .github/workflows/demo-shots.yml.

  python scripts/upload_demo_shots.py shots
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(folder):
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import gympulse_admin as gadm
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    store = sc.storage.from_("email-assets")
    for f in sorted(glob.glob(os.path.join(folder, "*.png"))):
        path = "demo-video/shots/" + os.path.basename(f)
        data = open(f, "rb").read()
        opts = {"content-type": "image/png", "upsert": "true", "cache-control": "60"}
        try:
            store.upload(path, data, opts)
        except Exception:
            store.update(path, data, opts)
        url = store.get_public_url(path)
        if isinstance(url, dict):
            url = url.get("publicURL") or url.get("publicUrl") or ""
        print(str(url).split("?")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
