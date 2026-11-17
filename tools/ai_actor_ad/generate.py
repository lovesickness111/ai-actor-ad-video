"""Paid shot generation through the providers of tools/video_chain.py, and where each shot lives.

Modes (ad.json video.mode):
- chain (gemini): one continuous Omni scene, shot 1 = start, every next shot = extension of the previous
  interaction, so faces, place and voices carry over; the returned file is the whole scene so far.
  Re-taking shot k drops the shots after it (they were extensions of the old take).
- shots (grok, or gemini without chaining): every shot is its own clip, kept consistent by the same
  keyframe/portrait references (and, on Grok, the same preset voice_ids).
"""
import base64
import json
import sys
import time
from pathlib import Path

from .media import seconds
from .prompts import gemini_prompt, grok_prompt, grok_voices, refs_for
from .spec import KIT, PROVIDER_ASPECTS

sys.path.insert(0, str(KIT / "tools"))


def _refs(pdir, files):
    out = []
    for f in files:
        data = (pdir / f).read_bytes()
        out.append((base64.b64encode(data).decode(), "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"))
    return out


def gen_aspect(spec):
    """Aspect to request: the delivery aspect when the provider has it, else the closest (cropped at build)."""
    prov = spec["video"]["provider"]
    ok = PROVIDER_ASPECTS.get(prov, [])
    if spec["aspect"] in ok:
        return spec["aspect"]
    w, h = (int(x) for x in spec["aspect"].split(":"))
    return min(ok, key=lambda a: abs(int(a.split(":")[0]) / int(a.split(":")[1]) - w / h))


def shot_index(spec, shot_id):
    for i, s in enumerate(spec["shots"]):
        if s["id"] == shot_id:
            return i, s
    sys.exit(f"no shot {shot_id} in ad.json")


def _keep_take(path):
    if path.exists():
        n = 1
        while path.with_name(f"{path.stem}-take{n}{path.suffix}").exists():
            n += 1
        path.rename(path.with_name(f"{path.stem}-take{n}{path.suffix}"))


def generate(pdir, spec, state, shot_id, log=print):
    import video_chain
    prov = spec["video"]["provider"]
    provider = video_chain.PROVIDERS[prov](spec["video"].get("model"))
    i, shot = shot_index(spec, shot_id)
    aspect, res = gen_aspect(spec), spec.get("resolution", "720p")
    chain = prov == "gemini" and spec["video"].get("mode") == "chain"
    out = pdir / "shots" / (f"chain-{shot_id}.mp4" if chain else f"{shot_id}.mp4")
    started = time.time()
    if prov == "grok":
        prompt = grok_prompt(spec, shot)
        first = _refs(pdir, [shot["keyframe"]])[0] if shot.get("keyframe") and shot.get("pin_first_frame", True) else None
        resp = provider.start(prompt, _refs(pdir, refs_for(spec, shot)), int(shot["seconds"]), aspect, res,
                              voices=grok_voices(spec), first_frame=first)
    elif chain and i > 0:
        prev = state["shots"].get(spec["shots"][i - 1]["id"])
        if not prev or not prev.get("interaction_id"):
            sys.exit(f"chain: generate {spec['shots'][i - 1]['id']} first (shots extend the previous one in order)")
        prompt = gemini_prompt(spec, shot, first=False)
        resp = provider.extend(prev["interaction_id"], prompt, int(shot["seconds"]), aspect, res)
    else:
        prompt = gemini_prompt(spec, shot, first=True)
        resp = provider.start(prompt, _refs(pdir, refs_for(spec, shot)), int(shot["seconds"]), aspect, res)
    data = provider.video_bytes(resp)
    _keep_take(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    total = seconds(out)
    start = 0.0
    if chain and i > 0:
        start = state["shots"][spec["shots"][i - 1]["id"]]["end"]
    if chain:  # later links were extensions of the previous take of this one
        for later in spec["shots"][i + 1:]:
            if state["shots"].pop(later["id"], None):
                log(f"dropped {later['id']}: it extended the old take of {shot_id}, generate it again")
    state["shots"][shot_id] = {"file": str(out.relative_to(pdir)).replace("\\", "/"), "start": round(start, 3),
                               "end": round(total, 3), "interaction_id": resp.get("id"), "provider": prov,
                               "model": provider.model, "prompt": prompt, "usage": resp.get("usage"),
                               "elapsed_s": round(time.time() - started), "at": time.strftime("%Y-%m-%d %H:%M")}
    state["spend"].append({"shot": shot_id, "provider": prov, "seconds": int(shot["seconds"]), "usage": resp.get("usage")})
    log(f"{shot_id}: {out} ({start:.2f}-{total:.2f} s)")
    return out


def resolve(pdir, spec, state, shot_id):
    """(file, t0, t1) of a shot. In a chain every shot reads from the newest file, which holds the whole scene."""
    rec = state["shots"].get(shot_id)
    if not rec:
        sys.exit(f"shot {shot_id} not generated yet")
    if spec["video"]["provider"] == "gemini" and spec["video"].get("mode") == "chain":
        newest = max((state["shots"][s["id"]] for s in spec["shots"] if s["id"] in state["shots"]), key=lambda r: r["end"])
        return pdir / newest["file"], rec["start"], rec["end"]
    return pdir / rec["file"], 0.0, rec["end"]


def words_for(pdir, clip):
    path = pdir / "shots" / f"{Path(clip).stem}.words.json"
    if not path.exists():
        from .media import transcribe_words
        transcribe_words(clip, path)
    return json.loads(path.read_text(encoding="utf-8"))
