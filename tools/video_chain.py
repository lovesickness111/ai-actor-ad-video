"""Generate one continuous AI video scene as a chain: a first clip, then extensions that keep the same
people, place and (as far as the model allows) the same voices. Paid: billed to the user's own key.

    .venv/Scripts/python.exe tools/run_tool.py tools/video_chain.py start  --chain projects/<p>/clips/chain.json \
        --seconds 6 --prompt "..." [--ref a.png ...] [--aspect 9:16] [--res 720p]
    .venv/Scripts/python.exe tools/run_tool.py tools/video_chain.py extend --chain projects/<p>/clips/chain.json \
        --seconds 4 --prompt "..."
    .venv/Scripts/python.exe tools/video_chain.py status --chain projects/<p>/clips/chain.json

Each step saves the full stitched video returned by the model as <chain-dir>/<name>-stepNN.mp4 and
records the interaction id, durations and reported usage in the chain JSON, so a chain can be resumed
and the real billing can be read from `usage`.

Providers: `gemini` (gemini-omni-1.2-flash via the Interactions API, GEMINI_API_KEY; first clip 3-15 s,
each extension 3-10 s, 30 s total; no audio reference input, so describe each voice in every prompt).
`grok` (grok-imagine-video-1.5 reference-to-video, GROK_API_KEY or XAI_API_KEY; 1-15 s per shot, no extension,
720p max with voices; --voice picks up to 3 preset voices shared with xAI TTS, tagged <AUDIO_0..2> in the
prompt, reference images are <IMAGE_0..n>; pair with tools/xai_tts.py for off-screen lines in the same voice).
State the estimated price and get the user's go-ahead in the conversation before each paid run.
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests


class GeminiOmni:
    name = "gemini"
    base = "https://generativelanguage.googleapis.com/v1beta"
    usd_per_second = {"360p": 0.035, "720p": 0.07, "1080p": 0.14}
    first_range, extend_range, total_cap = (3, 15), (3, 10), 30

    def __init__(self, model):
        self.model = model or "gemini-omni-1.2-flash"
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            sys.exit("GEMINI_API_KEY missing: ask the user to double-click 2-Nhap-key.cmd, then run via tools/run_tool.py")
        self.headers = {"x-goog-api-key": key, "Content-Type": "application/json"}

    def _post(self, body):
        r = requests.post(f"{self.base}/interactions", json=body, headers=self.headers, timeout=1200)
        if r.status_code != 200:
            sys.exit(f"HTTP {r.status_code}: {r.text[:800]}")
        return r.json()

    def start(self, prompt, refs, seconds, aspect, res):
        content = [{"type": "image", "data": d, "mime_type": m} for d, m in refs]
        content.append({"type": "text", "text": prompt})
        return self._post({"model": self.model, "input": content if refs else prompt,
                           "response_format": {"type": "video", "aspect_ratio": aspect, "resolution": res,
                                               "duration": f"{seconds}s"},
                           "store": True, "background": False, "stream": False})

    def extend(self, previous_id, prompt, seconds, aspect, res):
        return self._post({"model": self.model, "previous_interaction_id": previous_id, "input": prompt,
                           "response_format": {"type": "video", "aspect_ratio": aspect, "resolution": res,
                                               "duration": f"{seconds}s"},
                           "store": True, "background": False, "stream": False})

    def video_bytes(self, response):
        clips = list(find_videos(response))
        if not clips:
            sys.exit("No video in the response: " + json.dumps(redact(response))[:800])
        clip = clips[-1]
        if clip.get("data"):
            return base64.b64decode(clip["data"])
        r = requests.get(clip["uri"], headers=self.headers, timeout=600)
        r.raise_for_status()
        return r.content


class GrokImagine:
    """xAI grok-imagine-video-1.5 reference-to-video: up to 14 reference images and up to 3 preset voices
    (`voice_id`s shared with xAI TTS, so off-screen lines can be read in the same voice). Async: submit,
    poll, download the temporary URL. No extension on 1.5: every step is a separate shot (`start`)."""
    name = "grok"
    base = "https://api.x.ai/v1"
    usd_per_second = {"480p": 0.08, "720p": 0.14, "1080p": 0.25}
    first_range, extend_range, total_cap = (1, 15), (0, 0), 15

    def __init__(self, model):
        self.model = model or "grok-imagine-video-1.5"
        key = os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY")
        if not key:
            sys.exit("GROK_API_KEY missing: ask the user to add it with 2-Nhap-key.cmd, then run via tools/run_tool.py")
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def start(self, prompt, refs, seconds, aspect, res, voices=(), first_frame=None):
        body = {"model": self.model, "prompt": prompt, "duration": seconds, "aspect_ratio": aspect,
                "resolution": res}
        if refs:
            body["reference_images"] = [{"url": f"data:{m};base64,{d}"} for d, m in refs]
        if voices:
            body["reference_audios"] = [{"voice_id": v} for v in voices]
        if first_frame:
            d, m = first_frame
            body["image"] = {"url": f"data:{m};base64,{d}"}
        r = requests.post(f"{self.base}/videos/generations", json=body, headers=self.headers, timeout=120)
        if r.status_code != 200:
            sys.exit(f"HTTP {r.status_code}: {r.text[:800]}")
        request_id = r.json()["request_id"]
        print("submitted", request_id)
        deadline = time.time() + 1800
        while time.time() < deadline:
            time.sleep(10)
            p = requests.get(f"{self.base}/videos/{request_id}", headers=self.headers, timeout=60)
            if p.status_code != 200:
                continue
            j = p.json()
            if j.get("status") == "done":
                j["id"] = request_id
                return j
            if j.get("status") == "failed":
                sys.exit("generation failed: " + json.dumps(j.get("error"), ensure_ascii=False))
        sys.exit(f"still pending after 30 min; poll {request_id} later")

    def extend(self, *a, **k):
        sys.exit("grok-imagine-video-1.5 has no extension: generate each shot with start and a new --chain file")

    def video_bytes(self, response):
        url = (response.get("video") or {}).get("url") or response.get("url")
        r = requests.get(url, timeout=600)
        r.raise_for_status()
        return r.content


PROVIDERS = {"gemini": GeminiOmni, "grok": GrokImagine}


def find_videos(node):
    if isinstance(node, dict):
        if node.get("type") == "video" and ("data" in node or "uri" in node):
            yield node
        for value in node.values():
            yield from find_videos(value)
    elif isinstance(node, list):
        for item in node:
            yield from find_videos(item)


def redact(node):
    if isinstance(node, dict):
        return {k: ("<%d bytes>" % len(v) if k == "data" and isinstance(v, str) else redact(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [redact(v) for v in node]
    return node


def read_refs(paths):
    refs = []
    for p in paths:
        data = Path(p).read_bytes()
        refs.append((base64.b64encode(data).decode(), "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"))
    if len(refs) > 6:
        sys.exit("At most 6 reference images")
    return refs


def probe_seconds(path):
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    try:
        return round(float(out.stdout.strip()), 2)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=["start", "extend", "status"])
    parser.add_argument("--chain", required=True)
    parser.add_argument("--prompt")
    parser.add_argument("--seconds", type=int, default=6)
    parser.add_argument("--ref", action="append", default=[])
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    parser.add_argument("--res", default="720p", choices=["360p", "480p", "720p", "1080p"])
    parser.add_argument("--voice", action="append", default=[], help="grok: preset voice_id, tag <AUDIO_n> in the prompt")
    parser.add_argument("--first-frame", help="grok: image pinned as the first frame")
    parser.add_argument("--provider", default="gemini", choices=sorted(PROVIDERS))
    parser.add_argument("--model")
    args = parser.parse_args()

    chain_path = Path(args.chain)
    chain = json.loads(chain_path.read_text(encoding="utf-8")) if chain_path.exists() else None
    if args.mode == "status":
        print(json.dumps(chain, ensure_ascii=False, indent=2) if chain else "no chain yet")
        return
    if not args.prompt:
        sys.exit("--prompt is required")

    if args.mode == "start":
        if chain and chain.get("steps"):
            sys.exit(f"{chain_path} already has steps; use extend, or pick a new --chain file")
        provider = PROVIDERS[args.provider](args.model)
        lo, hi = provider.first_range
        if not lo <= args.seconds <= hi:
            sys.exit(f"first clip must be {lo}-{hi} s")
        chain = {"provider": provider.name, "model": provider.model, "aspect": args.aspect, "res": args.res,
                 "refs": args.ref, "steps": []}
        total = args.seconds
    else:
        if not chain or not chain.get("steps"):
            sys.exit("no chain to extend: run start first")
        provider = PROVIDERS[chain["provider"]](chain["model"])
        lo, hi = provider.extend_range
        if not lo <= args.seconds <= hi:
            sys.exit(f"an extension must be {lo}-{hi} s")
        total = (chain["steps"][-1].get("seconds_total") or 0) + args.seconds
        if total > provider.total_cap + 0.5:
            sys.exit(f"chain would reach {total} s, over the {provider.total_cap} s cap")

    rate = provider.usd_per_second.get(chain["res"], 0.07)
    print(f"{provider.model}: +{args.seconds}s (chain ~{total}s) {chain['aspect']} {chain['res']}; "
          f"~${args.seconds * rate:.2f} if only new seconds are billed, ~${total * rate:.2f} if the whole returned clip is")

    started = time.time()
    if args.mode == "start":
        if provider.name == "grok":
            first = read_refs([args.first_frame])[0] if args.first_frame else None
            response = provider.start(args.prompt, read_refs(args.ref), args.seconds, chain["aspect"], chain["res"],
                                      voices=args.voice, first_frame=first)
            chain["voices"] = args.voice
        else:
            response = provider.start(args.prompt, read_refs(args.ref), args.seconds, chain["aspect"], chain["res"])
    else:
        response = provider.extend(chain["steps"][-1]["interaction_id"], args.prompt, args.seconds,
                                   chain["aspect"], chain["res"])
    data = provider.video_bytes(response)
    step_no = len(chain["steps"]) + 1
    out = chain_path.parent / f"{chain_path.stem}-step{step_no:02d}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    chain["steps"].append({"step": step_no, "mode": args.mode, "prompt": args.prompt, "seconds_requested": args.seconds,
                           "interaction_id": response.get("id"), "file": out.name,
                           "seconds_total": probe_seconds(out), "usage": response.get("usage"),
                           "elapsed_s": round(time.time() - started)})
    chain_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out, f"{len(data) // 1024} KB, {chain['steps'][-1]['seconds_total']} s")
    print("usage", json.dumps(response.get("usage"), ensure_ascii=False))


if __name__ == "__main__":
    main()
