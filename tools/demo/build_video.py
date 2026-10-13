#!/usr/bin/env python3
"""Join the demo pieces from record_demo.py into docs/demo.mp4 and docs/demo.gif.

  tools/demo/build_video.py OUTDIR [DOCSDIR]

Order: title, admin intro, admin capture, user intro, user capture, phone (capture inside the
phone slide), end. 0.5 s cross-fades. GIF: the user and phone parts at 2x speed, 800 px, 8 fps.
"""
import json
import pathlib
import subprocess
import sys

out = pathlib.Path(sys.argv[1])
docs = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else pathlib.Path(__file__).resolve().parents[2] / "docs")
docs.mkdir(exist_ok=True)
FADE = 0.5
V = "fps=30,scale=1920:1080,setsar=1,format=yuv420p"


def dur(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(f)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


# Phone: 1 s of the slide, then the capture (976x2110 -> 444x960) at (1158, 60), last frame held.
phone = out / "phone-composite.mp4"
pd = dur(out / "phone.mp4")
ff("-loop", "1", "-t", pd + 1.5, "-i", out / "slide-phone.png", "-i", out / "phone.mp4", "-filter_complex",
   f"[1:v]scale=444:960,tpad=start_duration=1:start_mode=clone:stop_duration=0.5:stop_mode=clone[p];"
   f"[0:v][p]overlay=1158:60:eof_action=repeat,{V}", "-t", pd + 1.5, "-c:v", "libx264", "-crf", "18", phone)

pieces = [("slide-title.png", 4.0), ("slide-admin.png", 3.5), ("admin.mp4", None), ("slide-user.png", 4.5),
          ("user.mp4", None), (phone.name, None), ("slide-end.png", 6.5)]
inputs, durs = [], []
for name, d in pieces:
    f = out / name
    if d is None:
        inputs += ["-i", f]
        durs.append(dur(f))
    else:
        inputs += ["-loop", "1", "-t", d, "-i", f]
        durs.append(d)
chain, offset, last = [], 0.0, "[v0]"
chain.append(f"[0:v]{V}[v0]")
for i in range(1, len(pieces)):
    chain.append(f"[{i}:v]{V}[s{i}]")
    offset += durs[i - 1] - FADE
    chain.append(f"{last}[s{i}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[v{i}]")
    last = f"[v{i}]"
mp4 = docs / "demo.mp4"
ff(*inputs, "-filter_complex", ";".join(chain), "-map", last, "-t", sum(durs) - FADE * (len(durs) - 1), "-c:v", "libx264", "-crf", "22",
   "-movflags", "+faststart", "-pix_fmt", "yuv420p", mp4)
print(f"{mp4}: {dur(mp4):.1f} s, {mp4.stat().st_size / 1e6:.1f} MB")

# GIF: user + phone parts, 2x speed.
start = sum(durs[:4]) - 3 * FADE
length = durs[4] + durs[5] - FADE
gif = docs / "demo.gif"
ff("-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", mp4, "-filter_complex",
   "setpts=PTS/2,fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
   "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", gif)
print(f"{gif}: {dur(gif):.1f} s, {gif.stat().st_size / 1e6:.1f} MB")
