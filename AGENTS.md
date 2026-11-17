# AI-actor ad video

Windows workspace for making short promo/ad videos acted by realistic AI-generated people (UGC-style skits:
problem → product → screen demo → price → call to action) with any local coding agent (Claude Code, Codex, Trae
and others). The one skill is `.agents/skills/video-ai-actor-ad/SKILL.md`; read it before acting
(`.claude/skills/` only holds a pointer to it). Installation for people: `README.md`.

## Rules

- Run Python as `.venv/Scripts/python.exe ...` from the repository root; paid commands through
  `tools/run_tool.py <script> ...`, which loads `local/secrets.env` into that process only.
- Keys (`GROK_API_KEY`, `GEMINI_API_KEY`, `GEMINI_TTS_MODEL`) are entered by the user with `2-Nhap-key.cmd`. Never type,
  paste, print, store or read a key; check presence with `.venv/Scripts/python.exe tools/doctor.py`, never by opening the file.
- Keep each video in `projects/<project>/` (layout in the skill); keys, caches and runtimes in ignored `local/`.
- Ask the frame size and lock the script with the user before any paid call. State the cost and duration of paid
  calls (`tools/ai_actor_ad.py check`) and run them only after the user agrees; an approval covers only the exact
  revision shown. Never approve on the user's behalf.
- On-screen people are fictional and generated. Never use a real person's face or voice, celebrity look-alikes,
  or someone else's branding, footage or account; a reference video teaches structure only, unless the user owns it.
- The agent cannot hear audio: say so, and record listening checks only from the user's feedback. Give the absolute
  path of every video, image or sheet the user should review.
- Keep provider watermarks (SynthID and others). Remind the user that platforms require an AI-generated label for
  realistic people when they publish.
- Resume existing projects (`tools/ai_actor_ad.py status`) instead of starting new ones; keep old takes.
- Do not commit or push unless the user asks.

## Commands

- Checks: `.venv/Scripts/python.exe tools/doctor.py`; tests (offline, providers simulated, need ffmpeg):
  `.venv/Scripts/python.exe -m unittest discover -s tests`.
- Pipeline: `.venv/Scripts/python.exe tools/ai_actor_ad.py <init|status|check|approve|words|build|sheet> --project <p>`,
  paid: `.venv/Scripts/python.exe tools/run_tool.py tools/ai_actor_ad.py <gen|voice> --project <p>`.
- Images: `tools/run_tool.py tools/gen_asset.py image ...`; custom Gemini voices: `tools/run_tool.py tools/voice_remix.py ...`;
  one xAI TTS line: `tools/run_tool.py tools/xai_tts.py ...`; raw provider chains: `tools/run_tool.py tools/video_chain.py ...`.

## Architecture

- `tools/ai_actor_ad/`: `spec.py` (ad.json template, validation, digest-bound gates, cost estimate), `prompts.py`
  (shot prompts per provider), `generate.py` (paid shots, chain bookkeeping, where each shot lives), `voice.py`
  (native: model voice + same-voice TTS off screen, loudness-matched; dub: fixed TTS voices aligned by `align.py`
  syllable-level DTW), `media.py` (ffmpeg, Whisper words with the cache in `local/hf-cache`, caption timing and
  images), `build.py` (timeline of shots/inserts/cards → `edit/final.mp4`), `cli.py`.
- `tools/video_chain.py`: video providers (`GeminiOmni` chain with `previous_interaction_id`, `GrokImagine`
  reference-to-video with preset voices). A new model is a new provider class plus its prompt builder.
- `tools/xai_tts.py` (xAI TTS, same voice ids as Grok video), `tools/gemini_tts.py` (Gemini TTS + key loader),
  `tools/gen_asset.py` (Gemini images), `tools/voice_remix.py` (custom Gemini voices in the key's project).
- Fonts in `assets/fonts/` (SIL OFL 1.1, licences beside them).
