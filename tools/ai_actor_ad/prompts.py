"""Shot prompts for the video providers, with the lessons of the first productions built in:
- voices are described identically in every prompt (Omni has no voice input) or tagged <AUDIO_n> (Grok);
- the line is "spoken audio only, never displayed" (Omni burns subtitles otherwise, and still may);
- brand names are written as they are pronounced (`say`), the on-screen captions keep `text`;
- only the listed people, no morphing, no music unless asked."""

NEGATIVE = ("Natural ambient sound, no music. The frame must stay free of any written words: no captions, no subtitles, "
            "no lettering, no logos. Realistic motion, no morphing, no extra people.")


def spoken(line):
    return (line.get("say") or line["text"]).strip()


def speakers(shot):
    seen = []
    for line in shot.get("lines", []):
        if line["who"] not in seen:
            seen.append(line["who"])
    return seen


def refs_for(spec, shot):
    """Reference images in prompt order: keyframe first, then every character portrait."""
    files = [shot["keyframe"]] if shot.get("keyframe") else []
    return files + [c["portrait"] for c in spec["characters"].values()]


def _dialogue(spec, shot, voice_tag):
    parts = []
    for line in shot.get("lines", []):
        c = spec["characters"][line["who"]]
        tone = f" ({line['tone']})" if line.get("tone") else ""
        parts.append(f"{c['describe']}{tone} says, {voice_tag(line['who'])}: {spoken(line)}")
    if not parts:
        return "Nobody speaks in this shot."
    quiet = [cid for cid in spec["characters"] if cid not in speakers(shot)]
    tail = "" if not quiet else " " + " ".join(f"The {spec['characters'][c]['describe']} stays silent." for c in quiet)
    return ("Spoken Vietnamese dialogue with natural lip-sync (audio only, heard and never displayed): " +
            " Then ".join(parts) + "." + tail)


def gemini_prompt(spec, shot, first):
    chars = spec["characters"]
    voices = "; ".join(f"the {c['describe']} speaks with a {c['voice_prompt']}" for c in chars.values())
    if first:
        head = ("Animate the first reference image as a realistic handheld phone video, keeping its exact framing, place, "
                "lighting, faces and clothes; faces must match the character reference images. "
                f"Scene: {spec['scene']}.")
    else:
        head = "Continue the same shot seamlessly: same camera, same place, same people, same clothes, same lighting."
    return (f"{head} VOICES (identical in every clip): {voices}. {shot.get('action', '')} "
            f"{_dialogue(spec, shot, lambda who: 'in exactly the same voice as before')} {NEGATIVE}")


def grok_prompt(spec, shot):
    """<IMAGE_0> keyframe (if any), then <IMAGE_n> per character; <AUDIO_n> per character voice."""
    chars = list(spec["characters"])
    offset = 1 if shot.get("keyframe") else 0
    who_img = {cid: f"<IMAGE_{i + offset}>" for i, cid in enumerate(chars)}
    who_audio = {cid: f"<AUDIO_{i}>" for i, cid in enumerate(chars)}
    place = "the place from <IMAGE_0>, same framing and lighting" if offset else spec["scene"]
    cast = "; ".join(f"the person from {who_img[c]} is the {spec['characters'][c]['describe']}" for c in chars)
    return (f"Realistic handheld phone video in {place}. Scene: {spec['scene']}. {cast}. {shot.get('action', '')} "
            f"{_dialogue(spec, shot, lambda who: 'using the voice from ' + who_audio[who])} {NEGATIVE}")


def grok_voices(spec):
    return [c["voices"]["grok"] for c in spec["characters"].values()]
