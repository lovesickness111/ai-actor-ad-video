---
name: video-ai-actor-ad
description: Make a short promo or ad video acted by realistic AI-generated people (a UGC-style skit - e.g. two characters in a car hit a problem, one suggests the product, reaction, price, call to action), mixed with the user's own screen demo, product cards and big bold captions. Characters and keyframes are generated once and reused, talking shots come from a video model (Grok grok-imagine-video-1.5 by default, Gemini Omni 1.2 Flash, or another provider), voices stay the same across shots and videos. Use when the user wants an AI actor/UGC ad, a skit "like this promo" with people talking, or to replace filmed actors with generated ones. Not for editing their own filmed footage (video-edit-footage), narrated explainers without actors (video-explainer), or 2D/3D cartoon styles (video-style-clone, video-3d-*).
---

# AI-actor ad (video-ai-actor-ad)

Work from the repository root; read `AGENTS.md`. Everything for one video lives in `projects/<p>/`; the plan is one file,
`projects/<p>/ad.json`, and the CLI is `tools/ai_actor_ad.py` (paid commands through `tools/run_tool.py` so the
keys in `local/secrets.env` load). Talk to the user in their language, one step at a time.

Read before planning: [references/providers.md](references/providers.md) (video models, costs, quirks),
[references/voices.md](references/voices.md) (the two voice modes), [references/ad-json.md](references/ad-json.md)
(every field) and [references/lessons.md](references/lessons.md) (what went wrong in the first productions).

## Project folders

| Folder / file | Holds |
|---|---|
| `input/` | what the user gives: reference video, screen recordings/screenshots of the product, logo, product cards |
| `ad.json` | format, characters, shot list with the exact lines, timeline, overlays, captions (single source of truth) |
| `state.json` | approvals (digest-bound), generated shots, interaction ids, spend; written by the CLI only |
| `characters/` | one portrait per character (`<id>-vN.png`) |
| `keyframes/` | first-frame images of the scenes (`<shot>-vN.png`) |
| `shots/` | generated clips (`<shot>.mp4`, chain files `chain-<shot>.mp4`, older takes `-takeN`), Whisper words `*.words.json` |
| `audio/` | `vo/` off-screen lines, `dub/` re-voiced shots |
| `analysis/` | reference breakdown, transcripts, contact sheets for review |
| `edit/` | `final.mp4` (the delivery), `parts/`, `captions/`, `project.md` (decisions, approvals, paid runs) |

If `projects/<p>/.studio/brief.md` exists (a hand-over from a companion UI), read it and do not edit `.studio/`.

## Workflow

1. **Clarify first, before any paid call.** Ask, and wait for answers:
   - **Frame size**: 9:16, 16:9, 3:4, 1:1 or 4:3 (do not assume; a reference video's format is only a suggestion);
   - the product, the problem it solves, 2-3 selling points, price/offer and call to action;
   - what the user supplies (screen demo, screenshots, logo, product card) and their rights to it — a
     reference ad teaches structure only and is never cut into the new video unless it is the user's own material;
   - video model (default Grok) and voice mode (default `native`), see the references; length target.
   If they gave a reference video, break it down first (scene cuts with ffmpeg `select='gt(scene,0.12)'`,
   frames into `analysis/`, its speech with Whisper) and propose the same structure.
2. **Script gate.** `CLI init --project <p> --aspect <a> [--provider grok|gemini] [--voice-mode native|dub]`,
   then fill `ad.json` with the user: characters (fictional people only, never a real or famous face), shots with
   the exact spoken lines (`say` = how a brand name is pronounced), timeline (shots, inserts, cards), overlays.
   Show the full script as a table (shot, seconds, who says what, what is on screen) and `CLI check` (it prints
   errors and the cost estimate). State the cost and get an explicit yes, then
   `CLI approve --gate script --note "<their words>"`. Any later edit of the script reopens the gate.
3. **Cast gate.** Generate the portraits and keyframes (`.venv/Scripts/python.exe tools/run_tool.py tools/gen_asset.py image --prompt ... --aspect 3:4 --out
   projects/<p>/characters/a-v1.png`, Gemini, a few cents each; or the agent's own image tool; keyframes with the portraits as `--ref`). Look at every image, regenerate with one targeted change
   when needed, give the user the absolute paths, then `CLI approve --gate cast --note ...`.
4. **Shots.** `tools/run_tool.py tools/ai_actor_ad.py gen --project <p> --shot <id>` one at a time (chain mode must go
   in order). After each: `CLI sheet --project <p> --file shots/<id>.mp4`, look at it (faces, framing, burned-in text,
   morphing), and ask the user to listen — the agent cannot hear: say so. Re-take only with their agreement
   (`--retake`, old takes are kept). Start with one shot when the provider/voice is new to the user.
5. **Words and voices.** `CLI words` (local Whisper, free) checks that every line was said; fix the script or
   re-take when a line is wrong. Then `tools/run_tool.py tools/ai_actor_ad.py voice --project <p>`: off-screen lines in
   the characters' TTS voices, loudness-matched to the shots; in `dub` mode every line re-voiced and lip-aligned.
6. **Edit.** `CLI build --project <p>` → `edit/final.mp4` plus `analysis/final-sheet.jpg`. Check the sheet
   (captions inside the frame, no smear of removed subtitles, cards readable), give the absolute path, and ask
   about lip-sync, voices and levels. Fix in `ad.json` (captions, trims, overlay timing) and rebuild — free.
7. **Final gate and publishing.** `CLI approve --gate final --note ...` when the user accepts this exact file. When they
   publish (their own tool or account; this repo does not post), remind them that TikTok, YouTube and Facebook require the AI-generated label for
   realistic people. Never remove or hide the providers' watermarks (SynthID etc.).

`CLI` = `.venv/Scripts/python.exe tools/ai_actor_ad.py`. `CLI status --project <p>` says where a project stands and
what comes next; resume from it instead of starting over.

## Rules

- Paid calls: video seconds, images, TTS. Give the estimate (from `check`, plus re-takes) before each paid step;
  the user's approval covers the shown revision only. After paid runs, report what was spent (state.json `spend`).
- Keys: `GROK_API_KEY` (Grok video + xAI TTS), `GEMINI_API_KEY` (Omni, images, Gemini TTS). Missing → ask the user to
  double-click `2-Nhap-key.cmd`; never handle keys, never print or read `local/secrets.env`.
- People on screen are fictional and generated; no real person's face or voice, no celebrity look-alikes. The
  voices are provider presets or the user's own Gemini remixes (`tools/voice_remix.py`), not clones of real people.
- Keep Whisper's model cache inside the repository (`local/hf-cache`, set by the CLI); drive C may be full.
- Code: `tools/ai_actor_ad/` (spec, prompts, generate, voice, align, build, media), providers in
  `tools/video_chain.py` (add a model as a provider class), xAI TTS in `tools/xai_tts.py`.
