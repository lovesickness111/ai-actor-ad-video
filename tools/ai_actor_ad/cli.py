"""CLI of the video-ai-actor-ad skill. Paid commands (gen, voice) run through tools/run_tool.py so keys load."""
import argparse
import json
import sys
import time

from . import spec as S


def _log(pdir, text):
    path = pdir / "edit" / "project.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Project record\n\nDecisions, approvals and paid runs (newest last).\n\n", encoding="utf-8")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {time.strftime('%Y-%m-%d %H:%M')} {text}\n")


def _open(args):
    pdir = S.PROJECTS / args.project
    if not (pdir / "ad.json").exists():
        sys.exit(f"{pdir / 'ad.json'} not found: run init first")
    return pdir, S.load(pdir), S.load_state(pdir)


def cmd_init(args):
    pdir = S.PROJECTS / args.project
    if (pdir / "ad.json").exists():
        sys.exit(f"{pdir / 'ad.json'} exists: resume it (status) instead of starting over")
    for f in S.FOLDERS:
        (pdir / f).mkdir(parents=True, exist_ok=True)
    S.save(pdir, S.template(args.aspect, args.provider, args.voice_mode))
    S.save_state(pdir, {"gates": {}, "shots": {}, "spend": []})
    _log(pdir, f"init: aspect {args.aspect}, provider {args.provider}, voice mode {args.voice_mode}")
    print(f"created {pdir}: edit ad.json with the user (aspect, script, shots), then `check` and `approve --gate script`")


def cmd_status(args):
    pdir, spec, state = _open(args)
    print(f"project {pdir}  aspect {spec['aspect']}  provider {spec['video']['provider']}/{spec['video'].get('mode')}  "
          f"voice {spec['voice']['mode']}/{spec['voice']['tts']}")
    for g in S.GATES:
        rec = state["gates"].get(g)
        ok = S.gate_ok(pdir, spec, state, g)
        print(f"  gate {g:6s}: {'approved' if ok else ('CHANGED since approval' if rec else 'open')}"
              + (f" ({rec['at']}: {rec['note']})" if rec else ""))
    for s in spec["shots"]:
        rec = state["shots"].get(s["id"])
        print(f"  shot {s['id']:4s} {s['seconds']:>2}s  " + (f"{rec['file']} {rec['start']:.2f}-{rec['end']:.2f}" if rec else "-"))
    nxt = next((g for g in ("script", "cast") if not S.gate_ok(pdir, spec, state, g)), None)
    missing = [s["id"] for s in spec["shots"] if s["id"] not in state["shots"]]
    final = pdir / "edit" / "final.mp4"
    print("next:", f"approve --gate {nxt}" if nxt else (f"gen --shot {missing[0]}" if missing else
          ("build, then review edit/final.mp4" if not final.exists() else "review edit/final.mp4 / approve --gate final")))


def cmd_check(args):
    pdir, spec, state = _open(args)
    errs = S.validate(pdir, spec)
    for e in errs:
        print("ERROR", e)
    est = S.estimate(spec)
    print(json.dumps(est, indent=2))
    print("Tell the user this estimate (video re-takes cost extra) before asking for the script approval.")
    sys.exit(1 if errs else 0)


def cmd_approve(args):
    pdir, spec, state = _open(args)
    if args.gate == "cast":
        missing = [f for f in [c["portrait"] for c in spec["characters"].values()] +
                   [s["keyframe"] for s in spec["shots"] if s.get("keyframe")] if not (pdir / f).exists()]
        if missing:
            sys.exit("cast images missing: " + ", ".join(missing))
    if args.gate == "final" and not (pdir / "edit" / "final.mp4").exists():
        sys.exit("no edit/final.mp4 yet")
    S.save_state(pdir, S.approve(pdir, spec, state, args.gate, args.note))
    _log(pdir, f"approved {args.gate}: {args.note}")
    print(f"{args.gate} approved")


def cmd_gen(args):
    pdir, spec, state = _open(args)
    errs = S.validate(pdir, spec)
    if errs:
        sys.exit("fix ad.json first: " + "; ".join(errs))
    for g in ("script", "cast"):
        if not S.gate_ok(pdir, spec, state, g):
            sys.exit(f"gate {g} is not approved for the current ad.json/images: show it to the user and approve it")
    from .generate import generate
    ids = [s["id"] for s in spec["shots"]] if args.shot == "all" else args.shot.split(",")
    for sid in ids:
        if sid in state["shots"] and not args.retake:
            print(f"{sid}: already generated (use --retake to make a new take; the old one is kept)")
            continue
        generate(pdir, spec, state, sid)
        S.save_state(pdir, state)
        _log(pdir, f"generated {sid} ({spec['video']['provider']}, {next(s['seconds'] for s in spec['shots'] if s['id'] == sid)} s)")


def cmd_words(args):
    pdir, spec, state = _open(args)
    from .generate import resolve, words_for
    files = {resolve(pdir, spec, state, s["id"])[0] for s in spec["shots"] if s["id"] in state["shots"]}
    for f in sorted(files):
        w = words_for(pdir, f)
        print(f"{f.name}: {len(w)} words -> shots/{f.stem}.words.json")
        print("   ", " ".join(x["w"] for x in w))


def cmd_voice(args):
    pdir, spec, state = _open(args)
    from .generate import resolve, words_for
    from .voice import dub_shot, make_vo, shots_lufs
    files = sorted({resolve(pdir, spec, state, s["id"])[0] for s in spec["shots"] if s["id"] in state["shots"]})
    if spec["voice"]["mode"] == "dub":
        for s in spec["shots"]:
            if s["id"] in state["shots"] and s.get("lines"):
                clip, t0, t1 = resolve(pdir, spec, state, s["id"])
                out = dub_shot(pdir, spec, s, clip, t0, t1, words_for(pdir, clip))
                print(f"dub {s['id']}: {out}")
        target = None
    else:
        target = shots_lufs(pdir, files) if files else None
        print(f"shots speech level {target:.1f} LUFS: off-screen lines are matched to it" if target else "")
    made = make_vo(pdir, spec, target_lufs=target, force=args.force)
    print(f"off-screen lines: {len(made)} new" + (f" ({', '.join(made)})" if made else ""))


def cmd_build(args):
    pdir, spec, state = _open(args)
    from .build import build
    final = build(pdir, spec, state)
    _log(pdir, f"built {final.relative_to(pdir)}")
    from .media import contact_sheet, seconds
    d = seconds(final)
    sheet = contact_sheet(final, pdir / "analysis" / "final-sheet.jpg", [round(d * k / 12, 2) for k in range(12)], 180)
    print("review sheet:", sheet)


def cmd_sheet(args):
    pdir, spec, state = _open(args)
    from .media import contact_sheet, seconds
    src = pdir / args.file
    d = seconds(src)
    n = args.frames
    out = pdir / "analysis" / f"{src.stem}-sheet.jpg"
    print(contact_sheet(src, out, [round(d * (k + 0.5) / n, 2) for k in range(n)], args.width))


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="ai_actor_ad.py", description="AI-actor promo video pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("init")
    a.add_argument("--project", required=True)
    a.add_argument("--aspect", required=True, choices=list(S.ASPECTS))
    a.add_argument("--provider", default="grok", choices=list(S.USD_PER_SECOND))
    a.add_argument("--voice-mode", default="native", choices=["native", "dub"])
    for name in ("status", "check", "words", "build"):
        sub.add_parser(name).add_argument("--project", required=True)
    a = sub.add_parser("approve")
    a.add_argument("--project", required=True)
    a.add_argument("--gate", required=True, choices=S.GATES)
    a.add_argument("--note", required=True, help="what the user approved, in their words")
    a = sub.add_parser("gen")
    a.add_argument("--project", required=True)
    a.add_argument("--shot", required=True, help="shot id, comma list or all")
    a.add_argument("--retake", action="store_true")
    a = sub.add_parser("voice")
    a.add_argument("--project", required=True)
    a.add_argument("--force", action="store_true", help="re-speak lines that already exist")
    a = sub.add_parser("sheet")
    a.add_argument("--project", required=True)
    a.add_argument("--file", required=True, help="path inside the project, e.g. shots/s1.mp4")
    a.add_argument("--frames", type=int, default=7)
    a.add_argument("--width", type=int, default=240)
    args = p.parse_args(argv)
    {"init": cmd_init, "status": cmd_status, "check": cmd_check, "approve": cmd_approve, "gen": cmd_gen,
     "words": cmd_words, "voice": cmd_voice, "build": cmd_build, "sheet": cmd_sheet}[args.cmd](args)
    return 0
