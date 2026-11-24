"""Run the app with timing switched on, for finding slow pages.

  PERF_LOG=perf.jsonl python scripts/perf_server.py   (then open http://localhost:8501)

Each time a page runs (every click), one JSON line goes to PERF_LOG: when it started,
how long it took, every database call it made (path and milliseconds), and the app's
own functions that took the most time. Used by .github/workflows/perf-check.yml.
Nothing in the app changes; this only wraps it.
"""
import cProfile
import json
import os
import pstats
import sys
import threading
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = open(os.environ.get("PERF_LOG", "perf.jsonl"), "a", buffering=1)
_local = threading.local()

_send = httpx.Client.send


def _timed_send(self, request, *args, **kwargs):
    t = time.perf_counter()
    try:
        return _send(self, request, *args, **kwargs)
    finally:
        calls = getattr(_local, "calls", None)
        if calls is not None:
            q = request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)
            calls.append([request.method, request.url.path, round((time.perf_counter() - t) * 1000), q[:160]])


httpx.Client.send = _timed_send

from streamlit.runtime.scriptrunner import script_runner as _sr  # noqa: E402

_run = _sr.ScriptRunner._run_script


def _timed_run(self, rerun_data):
    _local.calls = []
    prof = cProfile.Profile()
    start_wall, t = time.time(), time.perf_counter()
    prof.enable()
    try:
        return _run(self, rerun_data)
    finally:
        prof.disable()
        ms = round((time.perf_counter() - t) * 1000)
        calls, _local.calls = _local.calls, None
        top = []
        try:
            stats = pstats.Stats(prof)
            rows = []
            for (fn, line, name), (cc, nc, tt, ct, callers) in stats.stats.items():
                if fn.startswith(ROOT) and "scripts/perf_server" not in fn:
                    rows.append((ct, tt, nc, f"{os.path.relpath(fn, ROOT)}:{line} {name}"))
            rows.sort(reverse=True)
            top = [[round(ct * 1000), round(tt * 1000), nc, where] for ct, tt, nc, where in rows[:25]]
        except Exception:
            pass
        LOG.write(json.dumps({"start": start_wall, "ms": ms, "db_n": len(calls),
                              "db_ms": sum(c[2] for c in calls), "calls": calls, "top": top}) + "\n")


_sr.ScriptRunner._run_script = _timed_run

if __name__ == "__main__":
    from streamlit.web import cli
    sys.argv = ["streamlit", "run", os.path.join(ROOT, "app.py"), "--server.headless=true",
                "--server.port=8501", "--browser.gatherUsageStats=false"]
    sys.exit(cli.main())
