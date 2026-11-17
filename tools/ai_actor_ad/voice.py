"""Voices. Two modes (ad.json voice.mode), any TTS provider (voice.tts):

- native: the video model's own voices stay on the shots (lip-sync is built in); every off-screen line
  (timeline vo) is spoken by the TTS voice of the same character and matched to the shots' loudness.
  Exact match needs a TTS that shares the video model's voices (Grok video <-> xAI TTS voice_id).
- dub: every line, on screen too, is spoken by fixed TTS voices (e.g. the Gemini Hanoi remixes) and each
  phrase is warped syllable by syllable (align.py, DTW) onto the actor's own take, over a room-tone bed.

TTS providers: xai (tools/xai_tts.py, GROK_API_KEY) and gemini (tools/gemini_tts.py,
GEMINI_API_KEY + GEMINI_TTS_MODEL). Add another by extending speak().
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from .media import ff, loudness, seconds, time_tokens, tokens
from .prompts import spoken
from .spec import KIT

sys.path.insert(0, str(KIT / "tools"))


def voice_id(spec, who):
    return spec["characters"][who]["voices"][spec["voice"]["tts"]]


def speak(spec, who, text, out, style=""):
    """One TTS line -> 48 kHz mono WAV with leading/trailing silence trimmed."""
    tts = spec["voice"]["tts"]
    raw = Path(out).with_suffix(".engine.wav")
    if tts == "xai":
        import xai_tts
        xai_tts.speak(text, voice_id(spec, who), raw, lang=spec.get("language", "vi"),
                      speed=spec["voice"].get("tts_speed"))
        tempo = None
    elif tts == "gemini":
        import gemini_tts as gtts
        gtts.load_env()
        c = spec["characters"][who]
        gtts.speak_gemini(text, {"voice": voice_id(spec, who), "pitch": 1.0,
                                 "style": "; ".join(x for x in (c.get("voice_prompt", ""), style) if x)}, raw)
        tempo = spec["voice"].get("tts_speed")
    else:
        sys.exit(f"unknown voice.tts {tts}: add it to tools/ai_actor_ad/voice.py speak()")
    af = ("silenceremove=start_periods=1:start_threshold=-42dB,areverse,"
          "silenceremove=start_periods=1:start_threshold=-42dB,areverse")
    if tempo and abs(tempo - 1) > 0.01:
        af += f",atempo={tempo}"
    ff("-i", raw, "-af", af, "-ar", "48000", "-ac", "1", out)
    raw.unlink()
    return out


def line_key(spec, who, text, extra=""):
    v = spec["voice"]
    h = hashlib.sha1(json.dumps([v["tts"], voice_id(spec, who), v.get("tts_speed"), text, extra],
                                ensure_ascii=False).encode()).hexdigest()[:12]
    return f"{who}-{h}"


def vo_lines(spec):
    """Every off-screen line of the timeline, with a stable cache name."""
    for i, item in enumerate(spec["timeline"]):
        for k, vo in enumerate(item.get("vo", [])):
            yield i, k, vo, line_key(spec, vo["who"], spoken(vo))


def make_vo(pdir, spec, target_lufs=None, force=False):
    out_dir = pdir / "audio" / "vo"
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for i, k, vo, key in vo_lines(spec):
        path = out_dir / f"{key}.wav"
        if force or not path.exists():
            speak(spec, vo["who"], spoken(vo), path, style=vo.get("tone", ""))
            if target_lufs is not None:
                level = loudness(path)
                if level is not None:
                    tmp = path.with_suffix(".tmp.wav")
                    ff("-i", path, "-af", f"volume={target_lufs - level:.2f}dB", tmp)
                    tmp.replace(path)
            made.append(path.name)
    return made


def shots_lufs(pdir, files):
    levels = [loudness(f) for f in files]
    levels = [x for x in levels if x is not None]
    return sum(levels) / len(levels) if levels else -16.0


# ---------------------------------------------------------------- dub mode

def _room_tone(clip, out):
    """The quietest 1.2 s of the clip, looped later under the dub."""
    import numpy as np
    import librosa
    y, sr = librosa.load(str(clip), sr=48000, mono=True)
    win = int(1.2 * sr)
    if len(y) <= win:
        ff("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "1.2", out)
        return out
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=480)[0]
    span = int(1.2 * sr / 480)
    sums = np.convolve(rms, np.ones(span), mode="valid")
    start = int(np.argmin(sums)) * 480 / sr
    ff("-ss", f"{start:.3f}", "-t", "1.2", "-i", clip, "-vn", "-af", "afade=t=in:d=0.1,afade=t=out:st=1.1:d=0.1",
       "-ar", "48000", "-ac", "1", out)
    return out


def dub_shot(pdir, spec, shot, clip, t0, t1, words):
    """audio/dub/<shot>.wav covering [t0, t1) of clip: each line warped onto the actor's take."""
    from .align import align_phrase
    out_dir = pdir / "audio" / "dub"
    out_dir.mkdir(parents=True, exist_ok=True)
    actor = out_dir / f"{shot['id']}-actor.wav"
    ff("-ss", f"{t0}", "-to", f"{t1}", "-i", clip, "-vn", "-ac", "1", "-ar", "48000", actor)
    local = [{**w, "s": w["s"] - t0, "e": w["e"] - t0} for w in words if t0 - 0.05 <= w["s"] < t1]
    all_tokens, owners = [], []
    for li, line in enumerate(shot.get("lines", [])):
        toks = tokens(line["text"])
        all_tokens += toks
        owners += [li] * len(toks)
    times = time_tokens(all_tokens, local, 0.0, t1 - t0)
    spans = []
    for li in range(len(shot.get("lines", []))):
        idx = [i for i, o in enumerate(owners) if o == li]
        spans.append((times[idx[0]][0], times[idx[-1]][1]) if idx else (0.0, 0.5))
    placed = []
    for li, (line, (s, e)) in enumerate(zip(shot["lines"], spans)):
        key = line_key(spec, line["who"], spoken(line), "dub")
        raw = out_dir / f"{key}-raw.wav"
        if not raw.exists():
            speak(spec, line["who"], spoken(line), raw, style=line.get("tone", ""))
        prev_end = spans[li - 1][1] if li else 0.0
        next_start = spans[li + 1][0] if li + 1 < len(spans) else t1 - t0
        pad = max(0.05, min(0.3, (s - prev_end) / 2, (next_start - e) / 2))
        fit = out_dir / f"{shot['id']}-l{li:02d}.wav"
        onset, _ = align_phrase(actor, s, e, raw, fit, pad=pad)
        placed.append((fit, onset))
    tone = _room_tone(actor, out_dir / f"{shot['id']}-tone.wav")
    length = t1 - t0
    inputs, mix = ["-stream_loop", "-1", "-i", tone], [f"[0:a]volume=0.35,atrim=0:{length:.3f}[bed]"]
    for i, (fit, at) in enumerate(placed, start=1):
        inputs += ["-i", fit]
        ms = int(at * 1000)
        mix.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[d{i}]")
    mix.append("[bed]" + "".join(f"[d{i}]" for i in range(1, len(placed) + 1)) +
               f"amix=inputs={len(placed) + 1}:normalize=0,atrim=0:{length:.3f},aformat=channel_layouts=stereo[out]")
    out = out_dir / f"{shot['id']}.wav"
    ff(*inputs, "-filter_complex", ";".join(mix), "-map", "[out]", "-ar", "48000", out)
    actor.unlink()
    return out


def fit_into(src, window, out, max_tempo=1.25):
    """Speed a line up (pitch kept) only when it is longer than its window."""
    dur = seconds(src)
    tempo = min(max_tempo, dur / window) if window and dur > window else 1.0
    ff("-i", src, "-af", f"atempo={tempo:.4f}", "-ar", "48000", "-ac", "2", out)
    return tempo


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()
