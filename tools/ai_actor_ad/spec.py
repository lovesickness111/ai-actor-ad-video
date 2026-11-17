"""Project layout, the ad.json script/shot plan, approval gates bound to digests, and cost estimates."""
import hashlib
import json
import time
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
PROJECTS = KIT / "projects"
FOLDERS = ["input", "characters", "keyframes", "shots", "audio", "analysis", "edit"]
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "3:4": (1080, 1440), "1:1": (1080, 1080), "4:3": (1440, 1080)}
# what each provider can generate natively; other aspects are generated at the nearest one and cropped
PROVIDER_ASPECTS = {"gemini": ["9:16", "16:9"], "grok": ["9:16", "16:9", "1:1", "4:3", "3:4"]}
USD_PER_SECOND = {"gemini": {"360p": 0.035, "720p": 0.07, "1080p": 0.14},
                  "grok": {"480p": 0.08, "720p": 0.14, "1080p": 0.25}}
# Omni extensions re-read the whole earlier clip as input: measured ~2.5 x 5792 tokens per earlier second at $1.50/M
GEMINI_CHAIN_INPUT_USD_PER_PRIOR_SECOND = 0.0217
TTS_USD_PER_CHAR = {"xai": 15e-6, "gemini": 20e-6}
GATES = ("script", "cast", "final")


def template(aspect, provider, voice_mode):
    return {
        "title": "",
        "aspect": aspect,
        "resolution": "720p",
        "fps": 30,
        "video": {"provider": provider, "model": None,
                  "mode": "chain" if provider == "gemini" else "shots"},
        "voice": {"mode": voice_mode, "tts": "xai" if provider == "grok" else "gemini", "tts_speed": 1.3},
        "scene": "Inside a modern car on a sunny day, light beige leather seats, glass sunroof, green trees outside",
        "characters": {
            "a": {"portrait": "characters/a-v1.png", "describe": "fictional Vietnamese man about 32, navy polo shirt",
                  "voice_prompt": "Northern Vietnamese (Hanoi) male voice, about 32, mid-low pitch, clear",
                  "voices": {"grok": "leo", "xai": "leo", "gemini": "Riko"}, "caption": "yellow"},  # Gemini: prebuilt name or your voice_remix id
            "b": {"portrait": "characters/b-v1.png", "describe": "fictional Vietnamese woman about 28, cream knit top",
                  "voice_prompt": "Northern Vietnamese (Hanoi) female voice, about 28, clear and light, slightly playful",
                  "voices": {"grok": "eve", "xai": "eve", "gemini": "Kore"}, "caption": "red"},
        },
        "shots": [
            {"id": "s1", "keyframe": "keyframes/s1-v1.png", "seconds": 6,
             "action": "The man on the right answers his phone, worried; the woman on the left looks up at him.",
             "lines": [{"who": "a", "text": "Alo… Bên anh cần hóa đơn gấp à?", "say": ""}]},
        ],
        "timeline": [
            {"shot": "s1"},
            {"insert": "input/demo.mp4", "from": 0.0, "to": 10.0, "mute": True,
             "vo": [{"who": "b", "text": "Câu thuyết minh cho đoạn demo.", "at": 0.0, "until": 4.0}]},
            {"card": "price", "title": "86K/THÁNG", "sub": "XỬ LÝ HÓA ĐƠN NHANH GỌN", "seconds": 3.0,
             "background": {"shot": "s1", "at": 2.0}, "vo": [{"who": "b", "text": "Chỉ từ tám mươi sáu nghìn một tháng."}]},
        ],
        "overlays": [{"shot": "s1", "image": "input/brand/card.png", "from_word": "combo", "until": "end",
                      "width": 0.67, "y": 0.61, "caption_y": 0.41}],
        "captions": {"font": "BarlowCondensed-Black", "size": 0.096, "y": 0.70, "max_chars": 22, "upper": True},
        "burned_subtitles": {"remove": provider == "gemini", "box": [0.02, 0.698, 0.96, 0.076]},
    }


def load(pdir):
    return json.loads((pdir / "ad.json").read_text(encoding="utf-8"))


def save(pdir, spec):
    (pdir / "ad.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_state(pdir):
    path = pdir / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"gates": {}, "shots": {}, "spend": []}


def save_state(pdir, state):
    (pdir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "missing"


def gate_digest(pdir, spec, gate):
    """What an approval covers: script = format + words + plan; cast = the reference images; final = the MP4."""
    if gate == "script":
        return _digest({k: spec.get(k) for k in ("aspect", "video", "voice", "scene", "shots", "timeline")} |
                       {"characters": {c: {k: v for k, v in d.items() if k != "portrait"}
                                       for c, d in spec.get("characters", {}).items()}})
    if gate == "cast":
        files = [d["portrait"] for d in spec["characters"].values()] + [s["keyframe"] for s in spec["shots"] if s.get("keyframe")]
        return _digest({f: _file_digest(pdir / f) for f in sorted(set(files))})
    return _file_digest(pdir / "edit" / "final.mp4")


def gate_ok(pdir, spec, state, gate):
    g = state["gates"].get(gate)
    return bool(g) and g["digest"] == gate_digest(pdir, spec, gate)


def approve(pdir, spec, state, gate, note):
    state["gates"][gate] = {"digest": gate_digest(pdir, spec, gate), "note": note, "at": time.strftime("%Y-%m-%d %H:%M")}
    return state


def validate(pdir, spec):
    """Problems that block generation (list of strings)."""
    errs = []
    if spec.get("aspect") not in ASPECTS:
        errs.append(f"aspect must be one of {', '.join(ASPECTS)} (ask the user)")
    prov = spec.get("video", {}).get("provider")
    if prov not in USD_PER_SECOND:
        errs.append(f"video.provider must be one of {', '.join(USD_PER_SECOND)}")
    if spec.get("voice", {}).get("mode") not in ("native", "dub"):
        errs.append("voice.mode must be native (model voices + same-voice TTS off screen) or dub (TTS for every line)")
    chars = spec.get("characters", {})
    ids = set()
    for s in spec.get("shots", []):
        if s.get("id") in ids:
            errs.append(f"duplicate shot id {s.get('id')}")
        ids.add(s.get("id"))
        lo, hi = (3, 15) if prov == "gemini" else (1, 15)
        if not lo <= int(s.get("seconds", 0)) <= hi:
            errs.append(f"shot {s.get('id')}: seconds must be {lo}-{hi}")
        for line in s.get("lines", []):
            if line.get("who") not in chars:
                errs.append(f"shot {s.get('id')}: unknown speaker {line.get('who')}")
    if prov == "gemini" and spec.get("video", {}).get("mode") == "chain":
        total = sum(int(s.get("seconds", 0)) for s in spec.get("shots", []))
        if total > 30:
            errs.append(f"an Omni chain is capped at 30 s (plan has {total} s): split into two chains or shorten")
    if prov == "grok":
        if len(chars) > 3:
            errs.append("Grok takes at most 3 preset voices: use at most 3 speaking characters")
        for c, d in chars.items():
            if not d.get("voices", {}).get("grok"):
                errs.append(f"character {c}: voices.grok (preset voice_id) is required for Grok")
    for item in spec.get("timeline", []):
        if "shot" in item and item["shot"] not in ids:
            errs.append(f"timeline: unknown shot {item['shot']}")
        if "insert" in item and not (pdir / item["insert"]).exists():
            errs.append(f"timeline: insert file not found {item['insert']}")
        for vo in item.get("vo", []):
            if vo.get("who") not in chars:
                errs.append(f"timeline vo: unknown speaker {vo.get('who')}")
    return errs


def estimate(spec):
    """Paid calls of one full pass, in USD, for the approval message."""
    prov = spec["video"]["provider"]
    rate = USD_PER_SECOND[prov].get(spec.get("resolution", "720p"), 0.14)
    secs = [int(s["seconds"]) for s in spec["shots"]]
    video = sum(secs) * rate
    if prov == "gemini" and spec["video"].get("mode") == "chain":
        prior = sum(sum(secs[:i]) for i in range(1, len(secs)))
        video += prior * GEMINI_CHAIN_INPUT_USD_PER_PRIOR_SECOND
    tts_chars = sum(len(v.get("say") or v["text"]) for item in spec["timeline"] for v in item.get("vo", []))
    if spec["voice"]["mode"] == "dub":
        tts_chars += sum(len(l.get("say") or l["text"]) for s in spec["shots"] for l in s.get("lines", []))
    tts = tts_chars * TTS_USD_PER_CHAR.get(spec["voice"].get("tts", "gemini"), 20e-6)
    images = 0.04 * (len(spec["characters"]) + len(spec["shots"]))
    return {"video_seconds": sum(secs), "video_usd": round(video, 2), "tts_usd": round(tts, 3),
            "images_usd_max": round(images, 2), "total_usd": round(video + tts + images, 2)}
