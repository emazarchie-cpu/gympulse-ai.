"""Upload the recorded demo video to Supabase Storage and print its public link.

  python scripts/upload_demo_video.py path/to/video.mp4

Runs from .github/workflows/demo-video.yml. The file goes to the public
email-assets bucket at demo-video/gympulse-ai-demo.mp4 (replaced each run).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import gympulse_admin as gadm
    sc = gadm.service_client()
    if sc is None:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    src = sys.argv[1]
    data = open(src, "rb").read()
    path = "demo-video/gympulse-ai-demo.mp4"
    store = sc.storage.from_("email-assets")
    opts = {"content-type": "video/mp4", "upsert": "true", "cache-control": "60"}
    try:
        store.upload(path, data, opts)
    except Exception:
        store.update(path, data, opts)
    url = store.get_public_url(path)
    if isinstance(url, dict):
        url = url.get("publicURL") or url.get("publicUrl") or ""
    print(f"Video ({len(data) / 1e6:.1f} MB): {str(url).split('?')[0]}?v={int(time.time())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
