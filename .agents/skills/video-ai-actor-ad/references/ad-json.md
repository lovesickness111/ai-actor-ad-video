# ad.json

Created by `CLI init` from a template; edit it with the user. Times are seconds. Paths are inside the project.
Full working example: [../examples/ad.example.json](../examples/ad.example.json) (car skit → screen demo → price → CTA).

```jsonc
{
  "title": "…",
  "aspect": "9:16",                 // asked at the start: 9:16 | 16:9 | 3:4 | 1:1 | 4:3
  "resolution": "720p", "fps": 30,  // generation resolution; delivery is 1080 on the short side
  "language": "vi",
  "video": {"provider": "grok", "model": null, "mode": "shots"},   // gemini: "chain" or "shots"
  "voice": {"mode": "native", "tts": "xai", "tts_speed": 1.3},     // dub + gemini for the Hanoi remixes
  "scene": "Inside a modern car on a sunny day …",
  "characters": {
    "a": {"portrait": "characters/a-v1.png",
          "describe": "fictional Vietnamese man about 32, navy polo shirt",   // used in prompts
          "voice_prompt": "Northern Vietnamese (Hanoi) male voice, about 32 …", // Omni + Gemini TTS style
          "voices": {"grok": "leo", "xai": "leo", "gemini": "Riko"},
          "caption": "yellow"}      // caption colour: yellow | red | white | blue
  },
  "shots": [
    {"id": "s1", "keyframe": "keyframes/s1-v1.png", "seconds": 6, "pin_first_frame": true,
     "action": "He answers the phone, worried; she looks up.",
     "lines": [{"who": "a", "text": "Bên anh cần hóa đơn gấp à?",   // shown in captions
                "say": "",                                          // spoken form when different (Mi-sa)
                "tone": "worried, hurried"}]}
  ],
  "timeline": [                     // the edit, in order
    {"shot": "s1", "trim": [1.0, 6.0]},
    {"insert": "input/demo.mp4", "from": 12.77, "to": 24.93, "mute": true,
     "vo": [{"who": "b", "text": "Mở HoaDonGo lên…", "say": "Mở Hóa Đơn Gô lên…", "at": 0.0, "until": 4.1}]},
    {"card": "price", "title": "86K/THÁNG", "sub": "XỬ LÝ HÓA ĐƠN NHANH GỌN", "seconds": 3.1,
     "background": {"shot": "s5", "at": 4.1},          // or {"image": "input/bg.png"}
     "vo": [{"who": "b", "text": "Có từ 86 nghìn một tháng…", "say": "Có từ tám mươi sáu nghìn…"}]}
  ],
  "overlays": [                     // images over a shot, e.g. the product card
    {"shot": "s4", "image": "input/brand/card.png", "from_word": "combo", "until": "end",
     "width": 0.667, "y": 0.615,    // fractions of the frame (top edge)
     "caption_y": 0.52,             // captions move here while it shows
     "title": "NHẬN ƯU ĐÃI NGAY"}   // optional: replaces the line captions while it shows
  ],
  "captions": {"font": "BarlowCondensed-Black", "size": 0.096, "y": 0.70, "max_chars": 22, "upper": true},
  "burned_subtitles": {"remove": true, "box": [0.02, 0.698, 0.96, 0.076]}   // Omni: x, y, w, h fractions
}
```

- Captions come from `lines[].text`, split at punctuation into ≤ 2-line chunks, timed by Whisper words
  (`shots/*.words.json`); brand names Whisper mishears are interpolated. Trailing `, . ; :` are dropped.
- `vo.at`/`until` place a line inside its insert/card (default: one after another from 0); a line longer than
  its window is sped up to 1.25x at most — shorten the text instead when that is not enough.
- In `chain` mode the shots are cut from the newest chain file (`state.json` holds each shot's start/end).
- Approvals hash: script = aspect, video, voice, scene, characters (without portrait files), shots, timeline;
  cast = the portrait and keyframe files. Captions, overlays and burned-subtitle settings can change freely.
