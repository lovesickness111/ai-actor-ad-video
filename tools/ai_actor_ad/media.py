"""ffmpeg/ffprobe helpers, loudness, Whisper word timings, script-to-words timing and caption images."""
import difflib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from .spec import KIT

FONT_DIRS = [KIT / "assets" / "fonts", Path("C:/Windows/Fonts")]
COLORS = {"yellow": ((255, 214, 0), (20, 20, 20)), "red": ((235, 30, 40), (255, 255, 255)),
          "white": ((255, 255, 255), (20, 20, 20)), "blue": ((40, 120, 255), (255, 255, 255)),
          "cta": ((255, 214, 0), (25, 45, 140))}


def run(cmd, quiet=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        sys.exit(f"command failed: {' '.join(map(str, cmd[:8]))} ...\n{r.stderr[-2500:]}")
    return r


def ff(*args):
    return run(["ffmpeg", "-y", "-loglevel", "error", *args])


def seconds(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    return float(r.stdout.strip())


def loudness(path, start=None, end=None):
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if start is not None:
        cmd += ["-ss", f"{start}"]
    if end is not None:
        cmd += ["-to", f"{end}"]
    cmd += ["-i", path, "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", "-"]
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    found = re.findall(r"^\s+I:\s+(-?[\d.]+) LUFS", r.stderr, re.M)
    return float(found[-1]) if found else None


def font(name, size):
    from PIL import ImageFont
    for d in FONT_DIRS:
        for ext in (".ttf", ".otf"):
            if (d / f"{name}{ext}").exists():
                return ImageFont.truetype(str(d / f"{name}{ext}"), size)
    return ImageFont.truetype(str(FONT_DIRS[0] / "BeVietnamPro-Black.ttf"), size)


# ---------------------------------------------------------------- Whisper words

def transcribe_words(media, out_json, language="vi"):
    """Word timestamps of a clip with local faster-whisper (model cache in local/hf-cache, not drive C)."""
    os.environ.setdefault("HF_HOME", str(KIT / "local" / "hf-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel
    wav = Path(out_json).with_suffix(".16k.wav")
    ff("-i", media, "-vn", "-ac", "1", "-ar", "16000", wav)
    model = WhisperModel(os.environ.get("AI_ACTOR_WHISPER", "medium"), device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(wav), language=language, word_timestamps=True, vad_filter=False)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in s.words]
    Path(out_json).write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    wav.unlink()
    return words


def norm(token):
    t = unicodedata.normalize("NFD", token.lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9]", "", t)


def tokens(text):
    return [t for t in re.split(r"\s+", text.strip()) if t]


def time_tokens(script_tokens, words, t0=0.0, t1=None):
    """(start, end) for every script token from Whisper words inside [t0, t1): matched tokens take the word's
    time, unmatched ones are interpolated between neighbours. Brand names that Whisper hears differently
    (SignGo -> Sai Gô) are handled by the interpolation."""
    ws = [w for w in words if w["s"] >= t0 - 0.05 and (t1 is None or w["s"] < t1)]
    if not script_tokens:
        return []
    if not ws:
        end = t1 if t1 is not None else t0 + 0.3 * len(script_tokens)
        step = (end - t0) / len(script_tokens)
        return [(t0 + i * step, t0 + (i + 1) * step) for i in range(len(script_tokens))]
    a = [norm(t) for t in script_tokens]
    b = [norm(w["w"]) for w in ws]
    times = [None] * len(a)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            w = ws[blk.b + k]
            times[blk.a + k] = (w["s"], w["e"])
    first, last = ws[0]["s"], ws[-1]["e"]
    known = [i for i, t in enumerate(times) if t]
    for i in range(len(times)):
        if times[i]:
            continue
        prev = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        lo = times[prev][1] if prev is not None else first
        hi = times[nxt][0] if nxt is not None else last
        lo_i = prev if prev is not None else -1
        hi_i = nxt if nxt is not None else len(times)
        frac0 = (i - lo_i - 0.5) / (hi_i - lo_i)
        mid = lo + (hi - lo) * max(0.0, frac0)
        times[i] = (mid, mid + max(0.1, (hi - lo) / max(1, hi_i - lo_i)))
    return times


def chunks(text, max_chars):
    """Caption chunks: split at sentence/comma punctuation, then wrap to <= 2 lines of max_chars."""
    out = []
    parts = []
    for part in re.split(r"(?<=[.!?,;…])\s+", text.strip()):
        # "Vâng," / "Ừm," alone make one-word captions that cannot cover a burned-in subtitle: join them on
        if parts and len(parts[-1]) < 10:
            parts[-1] = f"{parts[-1]} {part}"
        else:
            parts.append(part)
    for part in parts:
        words = tokens(part)
        groups = max(1, -(-len(part) // int(2.3 * max_chars)))  # chunks of two lines (captions shrink to fit)
        for g in _balanced(words, groups):
            text_g = " ".join(g)
            out.append("\n".join(" ".join(x) for x in _balanced(g, 2)) if len(text_g) > max_chars else text_g)
    return [c for c in out if c.strip()]


def _balanced(words, n):
    """Split words into n consecutive groups of similar character length (no orphan words)."""
    if n <= 1 or len(words) <= 1:
        return [words]
    total = sum(len(w) + 1 for w in words)
    groups, cur, acc, k = [], [], 0, 1
    for i, w in enumerate(words):
        cur.append(w)
        acc += len(w) + 1
        left = len(words) - i - 1
        if k < n and acc >= total * k / n and left >= n - k:
            groups.append(cur)
            cur, k = [], k + 1
    if cur:
        groups.append(cur)
    return groups


def caption_png(text, color, path, width, size_px, font_name, stroke=None):
    from PIL import Image, ImageDraw
    f = font(font_name, size_px)
    fill, edge = COLORS.get(color, COLORS["yellow"])
    sw = stroke or max(6, size_px // 10)
    h = int(size_px * 4.2)
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # shrink until the widest line fits (long Vietnamese words with diacritics)
    while True:
        box = d.multiline_textbbox((width / 2, h / 2), text, font=f, anchor="mm", align="center", spacing=6,
                                   stroke_width=sw)
        if box[2] - box[0] <= width * 0.94 or f.size <= 40:
            break
        f = font(font_name, int(f.size * 0.92))
    d.multiline_text((width / 2 + 6, h / 2 + 6), text, font=f, anchor="mm", align="center", spacing=6,
                     fill=(0, 0, 0, 150), stroke_width=sw, stroke_fill=(0, 0, 0, 150))
    d.multiline_text((width / 2, h / 2), text, font=f, anchor="mm", align="center", spacing=6,
                     fill=fill, stroke_width=sw, stroke_fill=edge)
    img.save(path)
    return h


def contact_sheet(media, out, times, width=240):
    tmp = Path(out).with_suffix("")
    tmp.mkdir(parents=True, exist_ok=True)
    inputs = []
    for i, t in enumerate(times):
        f = tmp / f"f{i:02d}.jpg"
        ff("-ss", f"{t}", "-i", media, "-frames:v", "1", "-vf", f"scale={width}:-2", f)
        inputs += ["-i", f]
    ff(*inputs, "-filter_complex", f"hstack=inputs={len(times)}", out)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return out
