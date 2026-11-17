"""Edit: timeline items (shot / insert / card) -> edit/parts/*.mp4 -> edit/final.mp4 (loudness -14 LUFS).

shot   : {"shot": id, "trim": [a, b]?}  generated shot; burned-in subtitles removed when configured; captions
         from the script text timed by Whisper words; overlays (ad.json overlays) appear from a word.
insert : {"insert": path, "from": s, "to": s, "mute": true, "vo": [...]}  footage the user supplied
         (e.g. a screen demo with its own captions); its sound is muted and the vo lines are laid in.
card   : {"card": name, "title": "...", "sub": "...", "seconds": 3, "background": {"shot": id, "at": s}, "vo": [...]}
         big title over a blurred, slowly zooming frame of a shot.
vo     : {"who": id, "text": "...", "say"?: "...", "at"?: s, "until"?: s}  off-screen line in the character's voice.
"""
import re
import sys
from pathlib import Path

from .generate import resolve, words_for
from .media import caption_png, chunks, ff, font, norm, seconds, time_tokens, tokens
from .prompts import spoken
from .spec import ASPECTS
from .voice import fit_into, line_key

ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


class Ctx:
    def __init__(self, pdir, spec, state, log):
        self.pdir, self.spec, self.state, self.log = pdir, spec, state, log
        self.W, self.H = ASPECTS[spec["aspect"]]
        self.fps = int(spec.get("fps", 30))
        self.parts = pdir / "edit" / "parts"
        self.caps = pdir / "edit" / "captions"
        for d in (self.parts, self.caps):
            d.mkdir(parents=True, exist_ok=True)
        c = spec.get("captions", {})
        self.font = c.get("font", "BarlowCondensed-Black")
        self.size = int(self.W * c.get("size", 0.096))
        self.cap_y = c.get("y", 0.70)
        self.max_chars = int(c.get("max_chars", 22))
        self.upper = c.get("upper", True)

    def fill(self):
        """Scale and centre-crop any source to the delivery frame."""
        return (f"scale={self.W}:{self.H}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={self.W}:{self.H},setsar=1,fps={self.fps}")


def shot_captions(ctx, shot, words, t0, t1):
    """[(start, end, text, colour)] relative to t0, from the script lines timed by the words."""
    all_tokens, owners = [], []
    for li, line in enumerate(shot.get("lines", [])):
        toks = tokens(line["text"])
        all_tokens += toks
        owners += [li] * len(toks)
    times = time_tokens(all_tokens, words, t0, t1)
    out, pos = [], 0
    for li, line in enumerate(shot.get("lines", [])):
        colour = ctx.spec["characters"][line["who"]].get("caption", "yellow")
        for ch in chunks(line["text"], ctx.max_chars):
            n = len(tokens(ch.replace("\n", " ")))
            seg = times[pos:pos + n]
            pos += n
            if seg:
                text = re.sub(r"[,.;:]+(?=\n|$)", "", ch, flags=re.M)  # keep ? ! … only
                out.append([seg[0][0] - t0, seg[-1][1] - t0, text.upper() if ctx.upper else text, colour, li])
    for k in range(len(out)):
        # inside a line a chunk stays until the next one starts; between lines only across short gaps
        nxt = out[k + 1][0] if k + 1 < len(out) else min(out[k][1] + 0.35, t1 - t0)
        same_line = k + 1 < len(out) and out[k + 1][4] == out[k][4]
        if same_line or nxt - out[k][1] < 0.6:
            out[k][1] = nxt
    return [tuple(c[:4]) for c in out]


def merged(windows, gap=1.5, pad=0.25):
    """Speech windows joined across short pauses: burned-in model subtitles linger through them."""
    res = []
    for a, b in sorted(windows):
        if res and a - pad <= res[-1][1] + gap:
            res[-1][1] = max(res[-1][1], b + pad)
        else:
            res.append([a - pad, b + pad])
    return res


def overlay_windows(ctx, shot_id, words, t0, t1):
    """Overlay start: `from` seconds, or the moment a word of the script (`from_word`) is spoken."""
    shot = next(s for s in ctx.spec["shots"] if s["id"] == shot_id)
    toks = [t for line in shot.get("lines", []) for t in tokens(line["text"])]
    times = time_tokens(toks, words, t0, t1)
    res = []
    for ov in ctx.spec.get("overlays", []):
        if ov.get("shot") != shot_id:
            continue
        start = ov.get("from", 0.0)
        if ov.get("from_word"):
            key = norm(ov["from_word"])
            hit = [times[i][0] for i, t in enumerate(toks) if key and key in norm(t)]
            start = hit[0] - t0 if hit else start
        end = (t1 - t0) if ov.get("until", "end") == "end" else float(ov["until"])
        res.append((ov, start, end))
    return res


def part_shot(ctx, item, n):
    spec, shot = ctx.spec, next(s for s in ctx.spec["shots"] if s["id"] == item["shot"])
    clip, t0, t1 = resolve(ctx.pdir, spec, ctx.state, shot["id"])
    if item.get("trim"):
        a, b = item["trim"]
        t0, t1 = t0 + a, min(t1, t0 + b)
    words = words_for(ctx.pdir, clip)
    caps = shot_captions(ctx, shot, words, t0, t1)
    ovs = overlay_windows(ctx, shot["id"], words, t0, t1)
    inputs = ["-ss", f"{t0}", "-to", f"{t1}", "-i", clip]
    graph, last = [], "0:v"
    burn = spec.get("burned_subtitles", {})
    if burn.get("remove") and caps:
        import json as _j
        from .media import run
        info = _j.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                             "-of", "json", clip]).stdout)["streams"][0]
        sw, sh = info["width"], info["height"]
        bx, by, bw, bh = burn.get("box", [0.02, 0.698, 0.96, 0.076])
        x, y = max(1, int(bx * sw)), max(1, int(by * sh))
        w, h = min(sw - x - 1, int(bw * sw)), min(sh - y - 1, int(bh * sh))
        enable = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in merged([(c[0], c[1]) for c in caps]))
        graph.append(f"[0:v]delogo=x={x}:y={y}:w={w}:h={h}:enable='{enable}'[dl]")
        last = "dl"
    graph.append(f"[{last}]{ctx.fill()}[v0]")
    last, idx = "v0", 1
    for k, (ov, a, b) in enumerate(ovs):
        inputs += ["-loop", "1", "-i", ctx.pdir / ov["image"]]
        width = int(ctx.W * ov.get("width", 0.67))
        y = int(ctx.H * ov.get("y", 0.61))
        graph.append(f"[{idx}:v]scale={width}:-1,format=rgba,fade=in:st={a:.2f}:d=0.25:alpha=1[ov{k}]")
        graph.append(f"[{last}][ov{k}]overlay=x=(W-w)/2:y={y}:shortest=1:enable='gte(t,{a:.2f})'[vo{k}]")
        last, idx = f"vo{k}", idx + 1
    titled = [(oa, ob, ov) for ov, oa, ob in ovs if ov.get("title")]
    if titled:  # an overlay with a title (e.g. "NHẬN ƯU ĐÃI NGAY") replaces the line captions while it shows
        kept = []
        for a, b, text, colour in caps:
            for oa, _, _ in titled:
                if a >= oa:
                    a = None
                    break
                b = min(b, oa)
            if a is not None and b > a:
                kept.append((a, b, text, colour))
        caps = kept + [(oa, ob, ov["title"], "cta") for oa, ob, ov in titled]
    for k, (a, b, text, colour) in enumerate(caps):
        png = ctx.caps / f"p{n:02d}-c{k:02d}.png"
        h = caption_png(text, colour, png, ctx.W, ctx.size, ctx.font)
        cy = ctx.cap_y
        for ov, oa, ob in ovs:  # a card on screen pushes the caption above it
            if oa < b and ob > a and ov.get("caption_y") is not None:
                cy = ov["caption_y"]
        inputs += ["-i", png]
        graph.append(f"[{last}][{idx}:v]overlay=x=0:y={int(ctx.H * cy - h / 2)}:"
                     f"enable='between(t,{a:.2f},{b:.2f})'[c{k}]")
        last, idx = f"c{k}", idx + 1
    if spec["voice"]["mode"] == "dub":
        dub = ctx.pdir / "audio" / "dub" / f"{shot['id']}.wav"
        if not dub.exists():
            sys.exit(f"no dub for {shot['id']}: run `voice` first")
        off = (t0 - resolve(ctx.pdir, spec, ctx.state, shot["id"])[1])
        inputs += ["-ss", f"{off}", "-to", f"{off + (t1 - t0)}", "-i", dub]
        amap = f"{idx}:a"
    else:
        amap = "0:a"
    out = ctx.parts / f"{n:02d}-shot-{shot['id']}.mp4"
    ff(*inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-map", amap, "-shortest",
       "-r", str(ctx.fps), *ENC, out)
    return out


def _vo_audio(ctx, item, dur, inputs, first_index):
    """adelay'd vo streams for a part of length dur; returns filter lines and labels."""
    lines, labels, cursor = [], [], 0.0
    for k, vo in enumerate(item.get("vo", [])):
        src = ctx.pdir / "audio" / "vo" / f"{line_key(ctx.spec, vo['who'], spoken(vo))}.wav"
        if not src.exists():
            sys.exit(f"missing voice line {src.name}: run `voice` first")
        at = float(vo.get("at", cursor))
        until = float(vo.get("until", dur - 0.1))
        fit = ctx.parts / f"vo-{src.stem}.wav"
        fit_into(src, max(0.3, until - at), fit)
        cursor = at + seconds(fit) + 0.15
        inputs += ["-i", fit]
        ms = int(at * 1000)
        lines.append(f"[{first_index + k}:a]adelay={ms}|{ms}[v{k}]")
        labels.append(f"[v{k}]")
    return lines, labels


def part_insert(ctx, item, n):
    src = ctx.pdir / item["insert"]
    a = float(item.get("from", 0.0))
    b = float(item.get("to", seconds(src)))
    dur = b - a
    inputs = ["-ss", f"{a}", "-to", f"{b}", "-i", src]
    graph = [f"[0:v]{ctx.fill()}[v]"]
    lines, labels = _vo_audio(ctx, item, dur, inputs, 1)
    graph += lines
    mixin = labels if item.get("mute", True) else ["[0:a]"] + labels
    if mixin:
        graph.append("".join(mixin) + f"amix=inputs={len(mixin)}:normalize=0,apad,atrim=0:{dur:.3f}[a]")
    else:
        graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[a]")
    out = ctx.parts / f"{n:02d}-insert.mp4"
    ff(*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-r", str(ctx.fps), *ENC, out)
    return out


def _title_png(ctx, title, sub, path):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (ctx.W, int(ctx.H * 0.35)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    size = int(ctx.W * 0.19)
    f = font(ctx.font, size)
    while d.textlength(title, font=f) > ctx.W * 0.9 and f.size > 40:
        f = font(ctx.font, int(f.size * 0.92))
    cx, cy = ctx.W / 2, img.height * 0.42
    edge = (25, 45, 140)
    d.text((cx + 8, cy + 8), title, font=f, anchor="mm", fill=(0, 0, 0, 160), stroke_width=18, stroke_fill=(0, 0, 0, 160))
    d.text((cx, cy), title, font=f, anchor="mm", fill=(255, 214, 0), stroke_width=18, stroke_fill=edge)
    if sub:
        fs = font(ctx.font, int(size * 0.4))
        while d.textlength(sub, font=fs) > ctx.W * 0.9 and fs.size > 30:
            fs = font(ctx.font, int(fs.size * 0.92))
        d.text((cx, img.height * 0.85), sub, font=fs, anchor="mm", fill=(255, 255, 255), stroke_width=10, stroke_fill=edge)
    img.save(path)


def part_card(ctx, item, n):
    dur = float(item.get("seconds", 3.0))
    bg = item.get("background", {})
    still = ctx.parts / f"{n:02d}-card-bg.png"
    if bg.get("shot"):
        clip, t0, _ = resolve(ctx.pdir, ctx.spec, ctx.state, bg["shot"])
        ff("-ss", f"{t0 + float(bg.get('at', 0.5))}", "-i", clip, "-frames:v", "1",
           "-vf", f"scale={ctx.W}:{ctx.H}:force_original_aspect_ratio=increase,crop={ctx.W}:{ctx.H}", still)
    elif bg.get("image"):
        ff("-i", ctx.pdir / bg["image"], "-vf", f"scale={ctx.W}:{ctx.H}:force_original_aspect_ratio=increase,"
           f"crop={ctx.W}:{ctx.H}", still)
    else:
        ff("-f", "lavfi", "-i", f"color=c=0x1a2a6c:s={ctx.W}x{ctx.H}", "-frames:v", "1", still)
    title = ctx.caps / f"p{n:02d}-title.png"
    _title_png(ctx, item.get("title", ""), item.get("sub", ""), title)
    inputs = ["-i", still, "-loop", "1", "-t", f"{dur}", "-i", title]
    graph = [f"[0:v]scale={ctx.W}:{ctx.H},zoompan=z='1+0.0008*on':d={int(dur * ctx.fps)}:s={ctx.W}x{ctx.H}:"
             f"fps={ctx.fps},gblur=sigma=18,eq=brightness=-0.08[bg]",
             "[1:v]format=rgba[t]", "[bg][t]overlay=x=0:y=(H-h)/2-H*0.04[v]"]
    lines, labels = _vo_audio(ctx, item, dur, inputs, 2)
    graph += lines
    if labels:
        graph.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,apad,atrim=0:{dur:.3f}[a]")
    else:
        graph.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[a]")
    out = ctx.parts / f"{n:02d}-card.mp4"
    ff(*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-t", f"{dur}",
       "-r", str(ctx.fps), *ENC, out)
    return out


def build(pdir, spec, state, log=print):
    ctx = Ctx(pdir, spec, state, log)
    parts = []
    for n, item in enumerate(spec["timeline"]):
        if "shot" in item:
            parts.append(part_shot(ctx, item, n))
        elif "insert" in item:
            parts.append(part_insert(ctx, item, n))
        elif "card" in item:
            parts.append(part_card(ctx, item, n))
        else:
            sys.exit(f"timeline item {n}: expected shot, insert or card")
        log(f"  part {n}: {parts[-1].name} ({seconds(parts[-1]):.2f}s)")
    listing = ctx.parts / "concat.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = ctx.parts / "joined.mp4"
    ff("-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", joined)
    final = pdir / "edit" / "final.mp4"
    ff("-i", joined, "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k",
       "-ar", "48000", final)
    log(f"final: {final} ({seconds(final):.2f}s, {ctx.W}x{ctx.H})")
    return final
