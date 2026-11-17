# Lessons from the first productions

Each line cost money or a re-do once. The CLI already handles the ones marked (auto).

## Characters and keyframes
- Generate one plain portrait per character (chest up, light background, "fictional", "not a celebrity"), then the
  keyframe with the portraits as references. Passing a too-wide keyframe as a reference makes the model copy its
  framing: for a tighter shot, regenerate from the portraits only and describe the framing ("close medium two-shot,
  no rear-view mirror, faces large").
- Look at every image before using it. Keep versions (`-v2`), never overwrite.

## Generation
- Omni burns its own subtitles whenever someone speaks, even with "no subtitles" and "audio only, never displayed":
  remove them (delogo over the band, merged across short pauses) and cover the band with our captions (auto). Short
  one-word captions do not cover it; short chunks are merged (auto).
- Omni extension bills the earlier clip again as input on every step: a 6-step 29 s chain cost $3.55, not the
  $2 the output seconds suggest (auto in `check`). An extension cannot add dialogue to an uploaded video, and a clip
  made with `store: false` cannot be extended: chain from the start.
- Re-taking a chain link drops the links after it (auto).
- Grok 1.5 has no extension; consistency comes from the pinned keyframe, the same portraits and the same voice ids.
- Write brand names as pronounced in `say` (HoaDonGo → "Hóa Đơn Gô", SignGo → "Sai Gô", eSign → "I-sai",
  USB token → "U-Ét-Bê tô-ken"); captions keep the real spelling.
- Clip length is chosen per request (Omni 3-15 s, Grok 1-15 s): size each shot to its line (about 3 Vietnamese
  syllables per second plus 1 s of acting), not a default.

## Voices
- Omni has no voice selection and no audio input; Gemini TTS takes no voice sample. Different engines never sound
  like one person: either keep the model voice and match TTS voices (Grok ↔ xAI), or dub everything.
- The in-video voice is faster and louder than TTS: speed 1.3 and loudness matching (auto).
- Phrase-level stretching left visible lip lag; syllable-level DTW alignment fixed most of it (auto in dub mode).

## Editing
- A reference ad teaches structure: hook skit (problem) → product card → screen demo with its own captions → reaction
  → price card → CTA with the card. Cut nothing from it unless it is the user's own material.
- Mute the demo's original narration when the voice would differ from the character's; lay the TTS lines on the
  timings of the demo's burned-in captions.
- Captions: heavy condensed font, upper case, thick stroke, one colour per speaker, no trailing commas, never wider
  than the frame (they shrink to fit; long chunks split evenly, no orphan words).
- Normalize the delivery to -14 LUFS (auto).

## Machine
- Drive C was full: the Whisper model and caches go to `local/hf-cache` (auto); faster-whisper `medium` on CPU takes
  about a minute per 30 s of audio after the first download.
- Print Vietnamese with `PYTHONIOENCODING=utf-8` (the console is cp1252).
