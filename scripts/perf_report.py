"""Joins perf_walk.js steps with perf_server.py timings and prints a report (slowest first).

  python scripts/perf_report.py walk.jsonl perf.jsonl
"""
import collections
import json
import sys


def load(path):
    out = []
    for line in open(path):
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def main(walk_file, perf_file):
    steps = [s for s in load(walk_file) if s.get("start")]
    runs = load(perf_file)
    print(f"{len(steps)} steps, {len(runs)} page runs on the server\n")
    print("PROBLEMS")
    for s in steps:
        bad = {k: s[k] for k in ("err", "exc", "errors", "pytext", "wide") if s.get(k)}
        if bad:
            print(f"  {s['name']}: {json.dumps(bad)[:600]}")
    print("\nSTEPS (browser wait, then each server run: ms, database calls, database ms)")
    rows = []
    for i, s in enumerate(steps):
        end = steps[i + 1]["start"] if i + 1 < len(steps) else 1e12
        mine = [r for r in runs if s["start"] - 0.2 <= r["start"] < end]
        rows.append((s, mine))
        srv = " + ".join(f"{r['ms']}ms/{r['db_n']}q/{r['db_ms']}ms" for r in mine)
        print(f"  {s['name']:<34} browser {s.get('ms')}ms | server {srv}")
    print("\nSLOWEST SERVER RUNS")
    allruns = sorted(((r, s["name"]) for s, mine in rows for r in mine), key=lambda x: -x[0]["ms"])
    for r, name in allruns[:12]:
        print(f"\n== {name}: {r['ms']} ms, {r['db_n']} database calls, {r['db_ms']} ms in the database")
        by = collections.defaultdict(lambda: [0, 0])
        for m, p, ms, q in r["calls"]:
            by[f"{m} {p}"][0] += 1
            by[f"{m} {p}"][1] += ms
        for k, (n, ms) in sorted(by.items(), key=lambda x: -x[1][1])[:12]:
            print(f"   db  {ms:>6} ms  x{n:<3} {k}")
        for ct, tt, nc, where in r["top"][:18]:
            print(f"   fn  {ct:>6} ms cum {tt:>6} ms own x{nc:<5} {where}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
