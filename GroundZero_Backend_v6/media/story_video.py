"""Turns a day's journal photos into a short vertical (9:16) story video.

Intro card, each photo with a slow Ken Burns zoom and its caption, and an
outro card listing the places visited. Photos are the traveller's own;
nothing is invented. Encoding uses the ffmpeg binary that ships with the
`imageio-ffmpeg` package, so no separate install is needed.
"""
from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 720, 1280
SECONDS = 3.2
FPS = 25
BG_TOP = (36, 0, 2)       # #240002
BG_BOTTOM = (111, 1, 0)   # #6F0100
GOLD = (255, 193, 54)     # #FFC136
CREAM = (247, 244, 238)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
]
_BODY_CANDIDATES = [
    "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf",
]


def _font(cands: list[str], size: int) -> ImageFont.ImageFont:
    for c in cands:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _gradient() -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = c
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _card(title: str, lines: list[str], footer: str) -> Image.Image:
    img = _gradient()
    d = ImageDraw.Draw(img)
    # sun + water lines: a nod to the app's illustration
    d.ellipse((W // 2 - 110, 330, W // 2 + 110, 550), fill=GOLD)
    for i, y in enumerate(range(560, 640, 18)):
        d.line((90 + i * 12, y, W - 90 - i * 12, y), fill=(217, 126, 12), width=3)
    f1, f2, f3 = _font(_FONT_CANDIDATES, 64), _font(_BODY_CANDIDATES, 34), _font(_BODY_CANDIDATES, 26)
    y = 700
    for ln in _wrap(d, title, f1, W - 120):
        d.text((W // 2, y), ln, font=f1, fill=CREAM, anchor="mt")
        y += 78
    y += 14
    for ln in lines[:7]:
        for sub in _wrap(d, ln, f2, W - 140)[:2]:
            d.text((W // 2, y), sub, font=f2, fill=GOLD, anchor="mt")
            y += 46
    d.text((W // 2, H - 90), footer, font=f3, fill=CREAM, anchor="mm")
    return img


def _photo_frame(src: Path, caption: str | None, stamp: str) -> Image.Image:
    base = _gradient()
    try:
        im = Image.open(src)
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        return _card("A moment", [], "GroundZero")
    # blurred-free fill: fit the photo inside a framed area on the gradient
    fit = ImageOps.contain(im, (W - 60, H - 380))
    x, y = (W - fit.width) // 2, 120 + (H - 380 - fit.height) // 2
    d = ImageDraw.Draw(base)
    d.rectangle((x - 8, y - 8, x + fit.width + 8, y + fit.height + 8), fill=CREAM)
    base.paste(fit, (x, y))
    f_cap, f_small = _font(_BODY_CANDIDATES, 34), _font(_BODY_CANDIDATES, 24)
    cy = y + fit.height + 40
    if caption:
        for ln in _wrap(d, caption.strip(), f_cap, W - 110)[:4]:
            d.text((W // 2, cy), ln, font=f_cap, fill=CREAM, anchor="mt")
            cy += 46
    d.text((W // 2, H - 70), stamp, font=f_small, fill=GOLD, anchor="mm")
    return base


def _clip(ffmpeg: str, img_path: Path, out: Path, seconds: float, zoom: bool) -> None:
    frames = int(seconds * FPS)
    if zoom:
        vf = (f"scale=2160:-1,zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
              f"fade=t=in:st=0:d=0.4,fade=t=out:st={seconds - 0.4:.2f}:d=0.4,format=yuv420p")
    else:
        vf = f"scale={W}:{H},fade=t=in:st=0:d=0.4,fade=t=out:st={seconds - 0.4:.2f}:d=0.4,fps={FPS},format=yuv420p"
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-i", str(img_path), "-t", f"{seconds}", "-vf", vf,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an", str(out)]
    subprocess.run(cmd, check=True, timeout=120)


def build_story_video(title: str, subtitle: str, places: list[str], items: list[tuple[Path, str | None, str]], out_dir: Path) -> Path:
    """items: (photo path, caption, time label). Returns the mp4 path."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{uuid.uuid4().hex}.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        cards: list[tuple[Image.Image, bool, float]] = [(_card(title, [subtitle], "made with GroundZero"), False, 2.6)]
        for src, cap, stamp in items[:30]:
            cards.append((_photo_frame(src, cap, stamp), True, SECONDS))
        outro_lines = places[:6] if places else ["Thanks for exploring Mangaluru"]
        cards.append((_card("Where the day went", outro_lines, "GroundZero · Mangaluru"), False, 3.2))
        clips = []
        for i, (img, zoom, secs) in enumerate(cards):
            p = t / f"s{i:02d}.png"
            img.save(p)
            c = t / f"c{i:02d}.mp4"
            _clip(ffmpeg, p, c, secs, zoom)
            clips.append(c)
        lst = t / "list.txt"
        lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(out)], check=True, timeout=120)
    return out
