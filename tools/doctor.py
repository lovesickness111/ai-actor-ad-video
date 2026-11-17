"""Local readiness checks: Python packages, ffmpeg/ffprobe, fonts, which keys are present (names only).
No API call: a present key is not proof that the account, billing or model access works.

    .venv/Scripts/python.exe tools/doctor.py [--json]
"""
import importlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = [("GROK_API_KEY", "Grok video + xAI voices (default provider)"),
        ("GEMINI_API_KEY", "images, Gemini Omni video, Gemini voices"),
        ("GEMINI_TTS_MODEL", "Gemini voices (dub mode / voice.tts gemini)")]
MODULES = ["requests", "PIL", "numpy", "scipy", "librosa", "soundfile", "faster_whisper"]


def key_names():
    import os
    names = {k for k, v in os.environ.items() if v}
    env = ROOT / "local" / "secrets.env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#") and line.split("=", 1)[1].strip().strip("\"'"):
                names.add(line.split("=", 1)[0].strip())
    return names


def checks():
    out = []
    for m in MODULES:
        try:
            importlib.import_module(m)
            out.append(("python." + m, "OK", "installed"))
        except Exception:
            out.append(("python." + m, "ACTION", "missing: double-click 1-Cai-dat.cmd"))
    for tool in ("ffmpeg", "ffprobe"):
        out.append((tool, "OK" if shutil.which(tool) else "ACTION",
                    "found" if shutil.which(tool) else "missing: double-click 1-Cai-dat.cmd, then open a new window"))
    fonts = ROOT / "assets" / "fonts"
    for f in ("BarlowCondensed-Black.ttf", "BeVietnamPro-Black.ttf"):
        out.append(("font." + f, "OK" if (fonts / f).exists() else "ACTION", "present" if (fonts / f).exists() else "missing"))
    have = key_names()
    for k, why in KEYS:
        out.append(("keys." + k, "OK" if k in have else "ACTION",
                    "present locally; not remotely validated" if k in have else f"missing: double-click 2-Nhap-key.cmd (needed for {why})"))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    res = checks()
    if "--json" in sys.argv:
        print(json.dumps([{"id": i, "status": s, "detail": d} for i, s, d in res], ensure_ascii=False, indent=1))
    else:
        for i, s, d in res:
            print(f"{s:6s} | {i} | {d}")
    return 0 if all(s == "OK" for i, s, _ in res if not i.startswith("keys.")) else 1


if __name__ == "__main__":
    sys.exit(main())
