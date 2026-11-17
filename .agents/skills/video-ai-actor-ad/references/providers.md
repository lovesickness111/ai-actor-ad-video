# Video providers

Set in `ad.json` → `video.provider` (+ optional `video.model`). Providers live in `tools/video_chain.py`; a new model
is a class with `start()` (and `extend()` if it chains), `video_bytes()`, `usd_per_second`, ranges, then an entry in
`PROVIDERS`, a branch in `tools/ai_actor_ad/generate.py` and a prompt builder in `prompts.py`.

| | `grok` — grok-imagine-video-1.5 (default) | `gemini` — gemini-omni-1.2-flash |
|---|---|---|
| Key | `GROK_API_KEY` (or `XAI_API_KEY`) | `GEMINI_API_KEY` (paid tier) |
| Mode | `shots`: every shot its own clip (reference-to-video) | `chain`: one continuous scene, shot 1 start + extensions (`previous_interaction_id`) |
| Length | 1-15 s per shot; no extension on 1.5 | first clip 3-15 s, extensions 3-10 s, 30 s per chain |
| Voice | up to 3 preset `voice_id`s (`reference_audios`), the same voices as xAI TTS → off-screen lines match | no voice input at all: describe the voice identically in every prompt; chaining keeps it fairly stable |
| References | up to 14 images (`<IMAGE_n>` in the prompt); keyframe pinned as first frame | up to 6 images on the first clip; extensions carry the scene |
| Resolution / aspect | 720p max with voices; 9:16, 16:9, 1:1, 4:3, 3:4 … | up to 4K; 9:16 or 16:9 (other aspects cropped at build) |
| Price (720p) | ~$0.14/s (480p $0.08) | ~$0.07/s output **plus** the whole earlier clip re-read as input on every extension (~$0.022 per earlier second; a 29 s chain of 6 shots cost $3.55) |
| Burned-in text | none seen | **always** burns small white subtitles (y ≈ 70-77 % of the frame) when someone speaks, whatever the prompt says → `burned_subtitles.remove: true` (delogo + our captions on top) |
| Language | Vietnamese worked; Northern accent not guaranteed — listen | "only English evaluated"; Vietnamese worked in practice |
| Watermark | provider marks kept | invisible SynthID, keep it |

Async/polling, interaction ids and usage are recorded in `state.json` per shot. Usage on Gemini is tokens
(5,792 video tokens per second at 720p); on Grok `cost_in_usd_ticks` (1e-10 USD).

Cost check before approval: `CLI check` sums the plan; add re-takes (count ~1 in 3 shots) when telling the user.
