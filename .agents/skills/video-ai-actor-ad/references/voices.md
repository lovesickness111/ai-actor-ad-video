# Voices

Two modes in `ad.json` → `voice.mode`; the TTS engine in `voice.tts` (`xai` or `gemini`); each character keeps its
voice ids in `characters.<id>.voices` (`grok`, `xai`, `gemini`), so the same people sound the same in every video.

## native (default)

The video model's own voice stays on the shots (lip-sync built in). Off-screen lines (`timeline[].vo`: the demo
narration, the price card) are spoken by TTS in the same character's voice and matched to the shots' loudness.

- Grok + xAI TTS share preset voices (`eve`, `ara`, `rex`, `sal`, `leo` and ~20 flagship voices; `language: vi`),
  so this is the closest match without generating extra video. It is close, not identical: at speed 1.0 the TTS is
  slower, quieter and flatter than the in-video voice. Use `voice.tts_speed: 1.3`, `?!`/`!` punctuation for energy;
  loudness is matched automatically. There is no style prompt in xAI TTS (only speed, punctuation, `[pause]`,
  `[laugh]`, `<soft>…</soft>` tags).
- With Gemini Omni there is no TTS of the same voice: prefer `dub` mode, or accept a different off-screen voice.
- Generating a video only to take its audio matches perfectly but costs video seconds; the user found it too
  expensive — offer it only for a key line.

## dub

Every line, on screen too, is spoken by fixed TTS voices; the model's voices are dropped. Custom Gemini voices live in
the Google project of the user's key, so every user makes their own once:
`tools/run_tool.py tools/voice_remix.py en-us-riko "Keep the same speaker identity, pitch and timbre, but make him a native
Vietnamese speaker from Hanoi ..." --preview projects/<p>/audio/riko-hanoi.wav` (same for `Kore` → a woman), then put the
printed `voice_...` ids in `characters.<id>.voices.gemini`; `--list` shows them. The template and example use the
prebuilt `Riko`/`Kore`, whose accent drifts between North and South: make the Hanoi remixes before a real video. Accent can still drift on a
line; re-speak that line (`voice --force` after changing its text, or delete its WAV in `audio/dub/`).

Lip-sync: the actor said the same words, so each TTS phrase is warped syllable by syllable onto the actor's own
take (`tools/ai_actor_ad/align.py`: MFCC + DTW → smooth time map, local rate 0.55-1.8x → phase vocoder). Measured
timing error went from 157 ms (one stretch per phrase) to 102 ms; phrases where the actor paused or said
something else stay off — fix the script or re-take. A room-tone bed from the quietest second of the shot is mixed
under the dub. Stronger options when it is still not enough: a paid lip-sync model (re-renders the mouth; two
faces in frame need speaker selection), or speech-to-speech of the actor's own audio (ElevenLabs; needs a key with
`speech_to_speech`/`voices_write`).

## Never

Clone a real person's voice, or use the creator profile's cloned voice for these fictional characters.
