"""Join the kept parts of the recorded demo (keep.json from record_demo.js) into one MP4.

  python scripts/cut_demo.py demo_out/take.webm demo_out/keep.json GymPulse-AI-Demo.mp4

Loading screens are left out, so the video goes straight from page to page.
"""
import json
import subprocess
import sys


def main(src, keep_file, out):
    keep = json.load(open(keep_file))
    parts, labels = [], []
    for i, (a, b) in enumerate(keep):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0,fps=30,format=yuv420p[out]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", graph, "-map", "[out]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-movflags", "+faststart", "-an", out],
                   check=True)
    print(f"{len(keep)} parts, {sum(b - a for a, b in keep):.0f} seconds")


if __name__ == "__main__":
    main(*sys.argv[1:4])
