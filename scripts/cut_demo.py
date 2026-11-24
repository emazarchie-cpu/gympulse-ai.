"""Join the kept parts of the recorded demo into one MP4.

  python scripts/cut_demo.py demo_out/take.webm demo_out/keep.json GymPulse-AI-Demo.mp4

record_demo.js shows a small magenta square in the bottom-right corner while a
page loads. Every frame that shows it is dropped (plus a few frames either side),
so the video goes straight from page to page. keep.json (seconds from the start
of the take) only sets where the video starts: the browser's clock and the
video's own timestamps drift apart, so it isn't used for the cuts in between.
"""
import json
import os
import subprocess
import sys
import tempfile

FPS = 30
MARGIN = 3      # frames dropped either side of a loading stretch
MIN_PART = 10   # parts shorter than this (frames) are dropped as flicker


def marked_frames(path):
    """True for each frame whose bottom-right corner shows the magenta marker."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "crop=12:12:iw-22:ih-22,scale=1:1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    return [raw[i] > 190 and raw[i + 1] < 80 and raw[i + 2] > 190 for i in range(0, len(raw) - 2, 3)]


def main(src, keep_file, out):
    keep = json.load(open(keep_file))
    start = keep[0][0] if keep else 0
    with tempfile.TemporaryDirectory() as tmp:
        cfr = os.path.join(tmp, "cfr.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"fps={FPS},format=yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-an", cfr], check=True)
        marks = marked_frames(cfr)
        n = len(marks)
        drop = [False] * n
        for i, m in enumerate(marks):
            if m:
                for j in range(max(0, i - MARGIN), min(n, i + MARGIN + 1)):
                    drop[j] = True
        ranges, run = [], None
        for i in range(int(start * FPS), n):
            if not drop[i] and run is None:
                run = i
            elif drop[i] and run is not None:
                ranges.append((run, i - 1))
                run = None
        if run is not None:
            ranges.append((run, n - 1))
        ranges = [r for r in ranges if r[1] - r[0] + 1 >= MIN_PART]
        expr = "+".join(f"between(n,{x},{y})" for x, y in ranges)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", cfr, "-vf",
                        f"select='{expr}',setpts=N/{FPS}/TB,format=yuv420p", "-r", str(FPS),
                        "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-movflags", "+faststart", "-an", out],
                       check=True)
    kept = sum(y - x + 1 for x, y in ranges)
    print(f"{sum(marks)} loading frames marked, {len(ranges)} parts, {kept / FPS:.0f} seconds")


if __name__ == "__main__":
    main(*sys.argv[1:4])
