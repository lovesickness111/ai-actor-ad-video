"""Gemini TTS (Interactions API) and the local key loader shared by the tools.

Keys come from local/secrets.env (entered with 2-Nhap-key.cmd); variables already set in the
environment win. Needs GEMINI_API_KEY and GEMINI_TTS_MODEL (optional GEMINI_BASE_URL).
Voices: a prebuilt name (Kore, Puck, ...) or a custom `voice_...` id made with tools/voice_remix.py.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=ROOT / "local" / "secrets.env"):
    """KEY=VALUE lines into os.environ; variables already set in the real environment win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"([A-Za-z_]\w*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            os.environ.setdefault(m.group(1), m.group(2).strip("\"'"))


def speak_gemini(text, cfg, raw_path):
    """cfg = {"voice": ..., "style": ...}. The text is read verbatim, so delivery direction goes in the
    speech_metadata annotation (written into the text it would be spoken aloud)."""
    for key in ("GEMINI_API_KEY", "GEMINI_TTS_MODEL"):
        if not os.environ.get(key):
            raise SystemExit(f"{key} missing: double-click 2-Nhap-key.cmd")
    base = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/").rstrip("/")
    body = {"model": os.environ["GEMINI_TTS_MODEL"],
            "input": [{"type": "user_input", "content": [{
                "type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": cfg.get("style", "")}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": cfg["voice"]}]}}
    request = urllib.request.Request(
        f"{base}/v1beta/interactions", json.dumps(body).encode(),
        {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Gemini HTTP {e.code}: {e.read().decode(errors='replace')[:800]}")
    audio = [c for step in reply["steps"] if step["type"] == "model_output"
             for c in step["content"] if c["type"] == "audio"]
    Path(raw_path).write_bytes(base64.b64decode(audio[-1]["data"]))  # a complete WAV file


def seconds(wav_path):
    with wave.open(str(wav_path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()
