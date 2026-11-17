"""Generate a paid source asset (image or video clip) with the user's Gemini key, for AI-actor ads (portraits, keyframes).

    .venv/Scripts/python.exe tools/run_tool.py tools/gen_asset.py image --prompt "..." --out projects/<p>/input/x.png
        [--ref anh.png ...] [--aspect 1:1|3:4|9:16|16:9] [--model gemini-3.1-flash-image]
    .venv/Scripts/python.exe tools/run_tool.py tools/gen_asset.py video --prompt "..." --out projects/<p>/input/x.mp4
        [--ref anh.png ...] [--seconds 3..15] [--aspect 9:16|16:9] [--res 360p|720p|1080p] [--model gemini-omni-1.2-flash]

Both calls are billed to GEMINI_API_KEY (run through tools/run_tool.py so the key is loaded for this
process only). Video is ~$0.07 per second at 720p; an image is a few cents. State the price and get the
user's go-ahead in the conversation before running; the tool prints its estimate but cannot ask.
References (up to 6) keep a character consistent between assets. Generated media carries Google's
invisible SynthID watermark: check the Gemini API terms before monetising.

Typical uses in video-ai-actor-ad:
- a character portrait: `image --aspect 3:4 --out projects/<p>/characters/a-v1.png` (fictional person, plain
  light background, chest up, "not a celebrity");
- a scene keyframe: `image --aspect 9:16 --ref characters/a-v1.png --ref characters/b-v1.png --out
  projects/<p>/keyframes/s1-v1.png` (describe the framing; do not pass a too-wide keyframe as a reference).
"""
import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
VIDEO_USD_PER_SECOND = {"360p": 0.035, "720p": 0.07, "1080p": 0.14}  # 720p from Google's launch pricing


def headers():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY missing: ask the user to double-click 2-Nhap-key.cmd, then run via tools/run_tool.py")
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def read_refs(paths):
    refs = []
    for p in paths:
        data = Path(p).read_bytes()
        mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
        refs.append((base64.b64encode(data).decode(), mime))
    if len(refs) > 6:
        sys.exit("At most 6 reference images")
    return refs


def gen_image(args):
    parts = [{"inlineData": {"mimeType": m, "data": d}} for d, m in read_refs(args.ref)]
    parts.append({"text": args.prompt})
    payload = {"contents": [{"parts": parts}],
               "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": args.aspect, "imageSize": "1K"}}}
    print(f"model {args.model}, {len(args.ref)} reference(s); a 1K image costs a few cents on the user's key")
    r = requests.post(f"{BASE}/models/{args.model}:generateContent", json=payload, headers=headers(), timeout=300)
    if r.status_code != 200:
        sys.exit(f"HTTP {r.status_code}: {r.text[:400]}")
    for part in r.json()["candidates"][0]["content"]["parts"]:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline:
            return base64.b64decode(inline["data"])
    sys.exit("No image in the response: " + json.dumps(r.json())[:400])


def find_videos(node):
    if isinstance(node, dict):
        if node.get("type") == "video" and "data" in node:
            yield node
        for value in node.values():
            yield from find_videos(value)
    elif isinstance(node, list):
        for item in node:
            yield from find_videos(item)


def gen_video(args):
    cost = args.seconds * VIDEO_USD_PER_SECOND.get(args.res, 0.07)
    print(f"model {args.model}, {args.seconds}s {args.aspect} {args.res} ~= ${cost:.2f} on the user's key")
    content = [{"type": "image", "data": d, "mime_type": m} for d, m in read_refs(args.ref)]
    content.append({"type": "text", "text": args.prompt})
    body = {"model": args.model, "input": content if args.ref else args.prompt,
            "response_format": {"type": "video", "aspect_ratio": args.aspect, "resolution": args.res, "duration": f"{args.seconds}s"},
            "background": False, "store": False, "stream": False}
    r = requests.post(f"{BASE}/interactions", json=body, headers=headers(), timeout=900)
    if r.status_code != 200:
        sys.exit(f"HTTP {r.status_code}: {r.text[:400]}")
    clips = list(find_videos(r.json()))
    if not clips:
        sys.exit("No video in the response: " + json.dumps(r.json())[:400])
    return base64.b64decode(clips[0]["data"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    image = sub.add_parser("image")
    image.add_argument("--prompt", required=True)
    image.add_argument("--out", required=True)
    image.add_argument("--ref", action="append", default=[])
    image.add_argument("--aspect", default="1:1", choices=["1:1", "3:4", "4:3", "9:16", "16:9"])
    image.add_argument("--model", default="gemini-3.1-flash-image")
    video = sub.add_parser("video")
    video.add_argument("--prompt", required=True)
    video.add_argument("--out", required=True)
    video.add_argument("--ref", action="append", default=[])
    video.add_argument("--seconds", type=int, default=6, choices=range(3, 16), metavar="3..15")
    video.add_argument("--aspect", default="9:16", choices=["9:16", "16:9"])
    video.add_argument("--res", default="720p", choices=["360p", "720p", "1080p"])
    video.add_argument("--model", default="gemini-omni-1.2-flash")
    args = parser.parse_args()
    data = gen_image(args) if args.mode == "image" else gen_video(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print("saved", out, f"{len(data) // 1024} KB")


if __name__ == "__main__":
    main()
