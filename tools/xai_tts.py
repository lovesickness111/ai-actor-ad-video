"""Speak a line with xAI TTS in one of the preset voices that grok-imagine-video-1.5 also uses, so
off-screen narration matches an on-screen character. Paid (~$15 per million characters, user's key).

    .venv/Scripts/python.exe tools/run_tool.py tools/xai_tts.py --voice eve --text "..." --out x.wav [--lang vi] [--speed 1.3]

Delivery is steered only by --speed (0.7-1.5), punctuation (?! adds energy) and inline tags such as
[pause], [laugh], <soft>...</soft>; there is no style prompt. Model voices in generated video run ~1.3x
faster than this TTS at speed 1.0, so 1.3 is the usual match.
"""
import argparse
import base64
import os
import sys

import requests


def speak(text, voice, out, lang="vi", speed=None, sample_rate=48000):
    key = os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY")
    if not key:
        sys.exit("GROK_API_KEY missing: ask the user to add it with 2-Nhap-key.cmd")
    body = {"text": text, "language": lang, "voice_id": voice,
            "output_format": {"codec": "wav", "sample_rate": sample_rate}}
    if speed:
        body["speed"] = max(0.7, min(1.5, float(speed)))
    r = requests.post("https://api.x.ai/v1/tts", json=body, timeout=300,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if r.status_code != 200:
        sys.exit(f"xAI TTS HTTP {r.status_code}: {r.text[:600]}")
    data = r.content
    if r.headers.get("content-type", "").startswith("application/json"):
        j = r.json()
        data = base64.b64decode(j.get("audio") or j.get("data") or "")
    with open(out, "wb") as f:
        f.write(data)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--voice", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--speed", type=float)
    a = ap.parse_args()
    speak(a.text, a.voice, a.out, a.lang, a.speed)
    print("saved", a.out, os.path.getsize(a.out) // 1024, "KB")


if __name__ == "__main__":
    main()
