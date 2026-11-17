"""Offline tests for tools/ai_actor_ad (skill video-ai-actor-ad): providers and TTS are simulated."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from ai_actor_ad import spec as S  # noqa: E402
from ai_actor_ad import prompts as P  # noqa: E402
from ai_actor_ad.media import chunks, time_tokens  # noqa: E402

FFMPEG = shutil.which("ffmpeg") is not None


def make_clip(path, seconds, w=360, h=640, tone=True):
    audio = ["-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}"] if tone else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc=size={w}x{h}:rate=24:duration={seconds}", *audio,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)], check=True)


def plan(provider="grok", voice_mode="native"):
    sp = S.template("9:16", provider, voice_mode)
    sp["shots"] = [
        {"id": "s1", "keyframe": "keyframes/s1-v1.png", "seconds": 4, "action": "He answers the phone.",
         "lines": [{"who": "a", "text": "Bên anh cần hóa đơn gấp à?"}]},
        {"id": "s2", "seconds": 3, "action": "She suggests the app.",
         "lines": [{"who": "b", "text": "Mình có app HoaDonGo cơ mà.", "say": "Mình có áp Hóa Đơn Gô cơ mà."}]},
    ]
    sp["timeline"] = [{"shot": "s1"}, {"shot": "s2"},
                      {"card": "price", "title": "86K/THÁNG", "sub": "NHANH GỌN", "seconds": 2.0,
                       "background": {"shot": "s1", "at": 1.0}, "vo": [{"who": "b", "text": "Chỉ tám mươi sáu nghìn."}]}]
    sp["overlays"] = []
    return sp


class Project(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = S.PROJECTS
        S.PROJECTS = self.tmp
        self.p = self.tmp / "demo"
        for f in S.FOLDERS:
            (self.p / f).mkdir(parents=True)
        from PIL import Image
        for f in ("characters/a-v1.png", "characters/b-v1.png", "keyframes/s1-v1.png"):
            Image.new("RGB", (64, 112), (120, 90, 60)).save(self.p / f)

    def tearDown(self):
        S.PROJECTS = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)


class SpecTests(Project):
    def test_template_and_validation(self):
        sp = plan()
        self.assertEqual(S.validate(self.p, sp), [])
        sp["aspect"] = "2:1"
        sp["shots"][0]["lines"][0]["who"] = "zz"
        errs = " ".join(S.validate(self.p, sp))
        self.assertIn("aspect", errs)
        self.assertIn("unknown speaker zz", errs)

    def test_grok_needs_voice_ids_and_max_three(self):
        sp = plan()
        sp["characters"]["a"]["voices"].pop("grok")
        self.assertTrue(any("voices.grok" in e for e in S.validate(self.p, sp)))
        for k in ("c", "d"):
            sp["characters"][k] = dict(sp["characters"]["b"])
        self.assertTrue(any("at most 3" in e for e in S.validate(self.p, sp)))

    def test_omni_chain_cap_and_estimate(self):
        sp = plan("gemini", "dub")
        sp["shots"] = [dict(sp["shots"][0], id=f"s{i}", seconds=n) for i, n in enumerate([6, 4, 4, 5, 4, 6])]
        sp["timeline"] = [{"shot": "s0"}]
        est = S.estimate(sp)
        # measured on the first production: 29 s chain at 720p cost about $3.55
        self.assertAlmostEqual(est["video_usd"], 3.59, delta=0.05)
        sp["shots"].append(dict(sp["shots"][0], id="s9", seconds=6))
        self.assertTrue(any("30 s" in e for e in S.validate(self.p, sp)))

    def test_gates_follow_the_approved_revision(self):
        sp = plan()
        st = S.approve(self.p, sp, {"gates": {}, "shots": {}, "spend": []}, "script", "ok")
        self.assertTrue(S.gate_ok(self.p, sp, st, "script"))
        sp["captions"]["y"] = 0.5  # layout changes do not reopen the script gate
        self.assertTrue(S.gate_ok(self.p, sp, st, "script"))
        sp["shots"][0]["lines"][0]["text"] = "Khác rồi"
        self.assertFalse(S.gate_ok(self.p, sp, st, "script"))
        st = S.approve(self.p, sp, st, "cast", "faces ok")
        from PIL import Image
        Image.new("RGB", (64, 112), (0, 0, 0)).save(self.p / "characters/a-v1.png")
        self.assertFalse(S.gate_ok(self.p, sp, st, "cast"))


class PromptAndCaptionTests(unittest.TestCase):
    def test_grok_prompt_tags_and_spoken_form(self):
        sp = plan()
        text = P.grok_prompt(sp, sp["shots"][1])
        self.assertIn("<IMAGE_1>", text)
        self.assertIn("<AUDIO_1>", text)
        self.assertIn("Hóa Đơn Gô", text)
        self.assertNotIn("HoaDonGo", text)
        self.assertIn("no subtitles", text)
        self.assertEqual(P.grok_voices(sp), ["leo", "eve"])

    def test_gemini_prompts_repeat_voices(self):
        sp = plan("gemini")
        first = P.gemini_prompt(sp, sp["shots"][0], True)
        later = P.gemini_prompt(sp, sp["shots"][1], False)
        self.assertIn("Animate the first reference image", first)
        self.assertIn("Continue the same shot", later)
        for t in (first, later):
            self.assertIn(sp["characters"]["b"]["voice_prompt"], t)

    def test_chunks_two_lines_no_orphans(self):
        out = chunks("Anh chị đang cần xuất hóa đơn và ký số linh hoạt, tham khảo ngay combo HoaDonGo và SignGo nhé!", 22)
        self.assertEqual(len(out), 2)
        for c in out:
            self.assertLessEqual(len(c.split("\n")), 2)
            self.assertGreater(len(c.split()), 2)
        self.assertEqual(chunks("Ừm, anh quên mất đấy, mà công nhận tiện thật.", 22)[0].split(",")[0], "Ừm")
        self.assertTrue(chunks("Vâng, vâng…", 22)[0].startswith("Vâng, vâng"))

    def test_time_tokens_interpolates_misheard_brand(self):
        words = [{"w": "mình", "s": 1.0, "e": 1.2}, {"w": "có", "s": 1.2, "e": 1.4},
                 {"w": "Sai", "s": 1.4, "e": 1.8}, {"w": "cơ", "s": 1.8, "e": 2.0}, {"w": "mà", "s": 2.0, "e": 2.2}]
        t = time_tokens(["Mình", "có", "SignGo", "cơ", "mà."], words)
        self.assertEqual(t[0], (1.0, 1.2))
        self.assertTrue(1.3 <= t[2][0] <= 1.8)
        self.assertEqual(t[4], (2.0, 2.2))


class FakeProvider:
    """Stands in for tools/video_chain.py providers: writes a short test clip, counts calls."""
    calls = []
    name = "fake"

    def __init__(self, model):
        self.model = model or "fake-1"

    def _clip(self, seconds):
        out = Path(tempfile.mkdtemp()) / "c.mp4"
        make_clip(out, seconds)
        return out.read_bytes()

    def start(self, prompt, refs, seconds, aspect, res, voices=(), first_frame=None):
        FakeProvider.calls.append(("start", seconds, tuple(voices), bool(first_frame)))
        self.total = seconds
        return {"id": f"i{len(FakeProvider.calls)}", "data": self._clip(seconds)}

    def extend(self, previous_id, prompt, seconds, aspect, res):
        FakeProvider.calls.append(("extend", previous_id, seconds))
        prior = sum(c[-1] for c in FakeProvider.calls[:-1] if c[0] == "extend") + FakeProvider.calls[0][1]
        return {"id": f"i{len(FakeProvider.calls)}", "data": self._clip(prior + seconds)}

    def video_bytes(self, resp):
        return resp["data"]


@unittest.skipUnless(FFMPEG, "ffmpeg needed")
class GenerateAndBuildTests(Project):
    def setUp(self):
        super().setUp()
        import video_chain
        self.saved = dict(video_chain.PROVIDERS)
        video_chain.PROVIDERS["grok"] = FakeProvider
        video_chain.PROVIDERS["gemini"] = FakeProvider
        FakeProvider.calls = []

    def tearDown(self):
        import video_chain
        video_chain.PROVIDERS.clear()
        video_chain.PROVIDERS.update(self.saved)
        super().tearDown()

    def test_gen_refuses_without_gates(self):
        from ai_actor_ad.cli import main
        S.save(self.p, plan())
        S.save_state(self.p, {"gates": {}, "shots": {}, "spend": []})
        with self.assertRaises(SystemExit) as cm:
            main(["gen", "--project", "demo", "--shot", "s1"])
        self.assertIn("script", str(cm.exception))
        self.assertEqual(FakeProvider.calls, [])

    def test_grok_shots_use_voices_and_first_frame(self):
        from ai_actor_ad.generate import generate, resolve
        sp, st = plan(), {"gates": {}, "shots": {}, "spend": []}
        generate(self.p, sp, st, "s1", log=lambda *_: None)
        generate(self.p, sp, st, "s2", log=lambda *_: None)
        self.assertEqual(FakeProvider.calls[0], ("start", 4, ("leo", "eve"), True))
        self.assertEqual(FakeProvider.calls[1][3], False)  # s2 has no keyframe
        f, a, b = resolve(self.p, sp, st, "s2")
        self.assertEqual(f.name, "s2.mp4")
        self.assertAlmostEqual(b, 3.0, delta=0.15)

    def test_chain_extends_in_order_and_retake_drops_later_links(self):
        from ai_actor_ad.generate import generate, resolve
        sp, st = plan("gemini"), {"gates": {}, "shots": {}, "spend": []}
        with self.assertRaises(SystemExit):
            generate(self.p, sp, st, "s2", log=lambda *_: None)
        generate(self.p, sp, st, "s1", log=lambda *_: None)
        generate(self.p, sp, st, "s2", log=lambda *_: None)
        self.assertEqual(FakeProvider.calls[1][:2], ("extend", "i1"))
        f, a, b = resolve(self.p, sp, st, "s1")
        self.assertEqual(f.name, "chain-s2.mp4")  # every shot reads from the newest file
        self.assertAlmostEqual(st["shots"]["s2"]["start"], 4.0, delta=0.15)
        generate(self.p, sp, st, "s1", log=lambda *_: None)
        self.assertNotIn("s2", st["shots"])
        self.assertTrue((self.p / "shots" / "chain-s1-take1.mp4").exists())

    def test_build_native_with_card_and_removed_subtitles(self):
        from ai_actor_ad.build import build
        from ai_actor_ad.media import seconds
        from ai_actor_ad.voice import line_key
        sp = plan("gemini")
        sp["video"]["mode"] = "shots"
        sp["voice"]["tts"] = "gemini"
        sp["overlays"] = [{"shot": "s2", "image": "keyframes/s1-v1.png", "from_word": "app", "until": "end",
                           "width": 0.5, "y": 0.6, "caption_y": 0.4, "title": "NHẬN ƯU ĐÃI NGAY"}]
        st = {"gates": {}, "shots": {}, "spend": []}
        for sid, n in (("s1", 4), ("s2", 3)):
            make_clip(self.p / "shots" / f"{sid}.mp4", n)
            st["shots"][sid] = {"file": f"shots/{sid}.mp4", "start": 0.0, "end": float(n)}
        (self.p / "shots" / "s1.words.json").write_text(json.dumps(
            [{"w": w, "s": 0.5 + 0.3 * i, "e": 0.75 + 0.3 * i} for i, w in enumerate("Bên anh cần hóa đơn gấp à?".split())]),
            encoding="utf-8")
        (self.p / "shots" / "s2.words.json").write_text(json.dumps(
            [{"w": w, "s": 0.3 + 0.3 * i, "e": 0.55 + 0.3 * i} for i, w in enumerate("Mình có áp Missa cơ mà".split())]),
            encoding="utf-8")
        vo = sp["timeline"][2]["vo"][0]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2",
                        "-ar", "48000", "-ac", "1", str(self.p / "audio" / "vo" / f"{line_key(sp, 'b', vo['text'])}.wav")],
                       check=True) if (self.p / "audio" / "vo").mkdir(parents=True, exist_ok=True) is None else None
        final = build(self.p, sp, st, log=lambda *_: None)
        self.assertTrue(final.exists())
        self.assertAlmostEqual(seconds(final), 9.0, delta=0.4)
        info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                          "stream=width,height", "-of", "json", str(final)],
                                         capture_output=True, text=True).stdout)["streams"][0]
        self.assertEqual((info["width"], info["height"]), (1080, 1920))
        self.assertTrue(any(self.p.joinpath("edit", "captions").glob("p01-c*.png")))


if __name__ == "__main__":
    unittest.main()
