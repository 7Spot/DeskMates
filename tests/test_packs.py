"""模型包：读包、名字对照、缺东西的模型不崩（用一个假的第二模型跑一遍捡球）、每个模型各记一份设置、调参、声音绑在模型上、设置里的开发者设置页和选模型页。"""
import json
import math
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from PySide6.QtGui import QColor
from tests.panel_base import QUIET, FakeSettings, PanelCase
from widget import packs, sounds
from widget.prefs import DEFAULT_PACK, Prefs
from widget.tuning import BALL_PARAMS, PET_PARAMS, Param, Tuning
from widget.voice import ClipSounds, SoundBank

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DT = 1 / 60
HAS_MODEL = Path(config.MODEL_PATH).is_file()
SAMOYED = "samoyed"
HAS_SAMOYED = (config.ROOT / "models" / "samoyed.glb").is_file()


class PackFileTests(unittest.TestCase):
    def test_every_toy_charges_with_the_same_sound(self):
        """捡球的圈充能：三个玩具（球、骨头、大球）的 charge 是同一段（文件逐字节一样），音量都是自己的 vol_charge，不借碰撞声的。"""
        found = packs.discover()
        ball = found[packs.BALL].sounds["charge"]
        for pid in ("ball", "bone", "big_ball"):
            spec = found[pid].sounds["charge"]
            self.assertEqual([f.name for f in spec.files], ["charge.wav"], pid)
            self.assertEqual(spec.files[0].read_bytes(), ball.files[0].read_bytes(), f"{pid} 和球的是同一段")
            self.assertEqual(spec.volume, "", f"{pid} 的音量跟 vol_charge")

    def test_the_two_shipped_packs_can_be_read(self):
        found = packs.discover()
        self.assertEqual(found[packs.DEFAULT_PET].kind, "pet")
        self.assertEqual(found[packs.BALL].kind, "prop")
        dog = found[packs.DEFAULT_PET]
        self.assertEqual(dog.display_name("zh"), "边牧")
        self.assertEqual(dog.display_name("en"), "Border Collie")
        self.assertEqual(dog.mass_kg, 18.0)
        self.assertIn("bark", dog.sounds, "狗的声音在狗的包里")
        self.assertIn("bounce", found[packs.BALL].sounds, "球的声音在球的包里")
        self.assertNotIn("bark", found[packs.BALL].sounds)
        self.assertEqual(dog.clip_sounds["Bark"].sound, "bark")
        self.assertNotIn("Idle_4", dog.clip_sounds, "嗅地没有声音")
        self.assertNotIn("sniffing", dog.action_sounds, "低头走没有声音")
        for s in dog.sounds.values():
            for f in s.files:
                self.assertTrue(f.is_file(), f)

    def test_every_sound_listed_in_a_pack_exists(self):
        for pack_dir in sorted(packs.PACKS_DIR.glob("*/pack.json")):
            data = json.loads(pack_dir.read_text(encoding="utf-8"))
            for spec in data.get("sounds", {}).values():
                for rel in spec["files"]:
                    self.assertTrue((pack_dir.parent / rel).is_file(), rel)

    def test_a_broken_pack_is_skipped_and_the_rest_still_load(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "good").mkdir()
            (root / "good" / "pack.json").write_text(json.dumps({"id": "good", "kind": "prop"}), encoding="utf-8")
            (root / "bad").mkdir()
            (root / "bad" / "pack.json").write_text("{ not json", encoding="utf-8")
            found = packs.discover(root)
        self.assertEqual(list(found), ["good"])

    def test_a_missing_sound_file_is_just_no_sound(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "x"
            root.mkdir()
            (root / "sounds").mkdir()
            (root / "sounds" / "a.wav").write_bytes(b"x")
            (root / "pack.json").write_text(json.dumps({"id": "x", "sounds": {"bark": {"files": ["sounds/a.wav", "sounds/gone.wav"]},
                                                                               "whine": {"files": ["sounds/gone.wav"]}}}), encoding="utf-8")
            pack = packs.read_pack(root)
        self.assertEqual(len(pack.sounds["bark"].files), 1)
        self.assertNotIn("whine", pack.sounds)

    def test_the_samoyed_pack_reads_without_its_model_file(self):
        """pack.json 入 git、模型文件不入：读包不看模型在不在。声音各包自带一份，绑定照边牧的写。"""
        found = packs.discover()
        dog, sam = found[packs.DEFAULT_PET], found[SAMOYED]
        self.assertEqual((sam.kind, sam.species, sam.icon), ("pet", "dog", "bone"))
        self.assertEqual((sam.display_name("zh"), sam.display_name("en"), sam.default_name), ("萨摩耶", "Samoyed", "Mochi"))
        self.assertEqual(sam.model, config.ROOT / "models" / "samoyed.glb")
        self.assertEqual(sam.mass_kg, 23.0)
        self.assertEqual((dog.brightness, sam.brightness), (1.0, 1.4), "萨摩耶的贴图在三渲二下偏灰，按模型提亮；边牧原样")
        self.assertTrue(sam.custom_coat, "第 13 条：萨摩耶能自定义毛色（整身一个色 + 可选背上一片）")
        self.assertEqual(sam.coat_custom["mode"], "tint")
        self.assertEqual(len(sam.coat_custom["patterns"]), 2)
        for main, second in sam.coat_custom["common_colors"]:
            for c in (main, second):
                hue, sat = QColor(c).hsvHueF() * 360.0, QColor(c).hsvSaturationF()
                self.assertTrue(sat < 0.15 or (20.0 <= hue <= 50.0 and sat < 0.6),
                                f"常用颜色只给自然的毛色：白、灰或者暖黄棕（跳的颜色从取色器选）：{c} 色相 {hue:.0f} 饱和度 {sat:.2f}")
        self.assertFalse(dog.coat_custom, "边牧不写：按深浅分两色")
        self.assertEqual(len(sam.coats), 4)
        self.assertEqual(len(sam.coat_notes), len(sam.coats))
        for note in sam.coat_notes:
            for part in ("name", "pattern"):
                self.assertTrue(note[part]["zh"] and note[part]["en"], note)
        self.assertFalse(set(sam.coats) & set(dog.coats), "两只的贴图放同一个文件夹，名字不能撞")
        self.assertEqual(set(sam.sounds), set(dog.sounds))
        self.assertEqual(dict(sam.clip_sounds), dict(dog.clip_sounds), "骨架和 Bark 片段里嘴的动作一样，时间点也一样")
        for f in sam.sound_files():
            self.assertEqual(f.parent, sam.root / "sounds", "声音绑在模型上，不借边牧的")
        self.assertLess(dog.height_m, sam.height_m)
        self.assertLess(sam.height_m, sam.fit_m)
        g = sam.gaits
        self.assertTrue(0 < g["walk"] < g["trot"] < g["run"] < g["fast"], g)
        for k, v in g.items():
            self.assertTrue(dog.gaits[k] <= v <= dog.gaits[k] * 1.25, f"{k}: 同一套动作、腿长一点，只该快一点")

    def test_a_pack_whose_model_file_is_missing_is_not_offered(self):
        """购买的模型不入 git：新 clone 下来没有 models/samoyed.glb，这个包照样读得出来，但不在能选的里面，记着它的也回到默认那只。"""
        from dataclasses import replace
        real = packs.discover()
        with tempfile.TemporaryDirectory() as d:
            here = Path(d) / "here.glb"
            here.write_bytes(b"x")
            found = {packs.DEFAULT_PET: replace(real[packs.DEFAULT_PET], model=here), SAMOYED: replace(real[SAMOYED], model=Path(d) / "gone.glb"),
                     packs.BALL: real[packs.BALL]}
            self.assertFalse(found[SAMOYED].available)
            self.assertEqual([p.id for p in packs.pets(found)], [packs.DEFAULT_PET])
            self.assertEqual(packs.choose_pet(SAMOYED, found).id, packs.DEFAULT_PET)
            found[SAMOYED] = replace(found[SAMOYED], model=here)
            self.assertEqual([p.id for p in packs.pets(found)], [packs.DEFAULT_PET, SAMOYED], "文件在就能选，默认那只排第一")
            self.assertEqual(packs.choose_pet(SAMOYED, found).id, SAMOYED)

    def test_choosing_falls_back_to_the_default_pet(self):
        found = packs.discover()
        self.assertEqual(packs.choose_pet("nope", found).id, packs.DEFAULT_PET)
        self.assertEqual(packs.choose_pet(None, found).id, packs.DEFAULT_PET)
        self.assertEqual(packs.choose_pet("", {}).id, packs.DEFAULT_PET, "packs/ 不在也有一只")


class PrefsPerPackTests(unittest.TestCase):
    def test_the_default_dog_keeps_the_old_keys_so_upgrades_lose_nothing(self):
        store = FakeSettings()
        store.setValue("scale", 1.98)
        store.setValue("dog_name", "Bobo")
        prefs = Prefs(store)
        self.assertEqual(prefs.pack_id, DEFAULT_PACK)
        self.assertEqual(prefs.get("scale"), 1.98)
        self.assertEqual(prefs.get("dog_name"), "Bobo")

    def test_another_model_has_its_own_name_and_coat_and_the_size_is_shared(self):
        store = FakeSettings()
        dog, cat = Prefs(store), Prefs(store, "cat", "Mimi")
        dog.set("scale", 2.0)
        dog.set("coat", 3)
        self.assertEqual(cat.get("coat"), 1)
        self.assertEqual(cat.get("dog_name"), "Mimi", "没起过名字用包里的")
        self.assertEqual(cat.get("scale"), 2.0, "大小是全局的一个")
        cat.set("scale", 0.7)
        self.assertEqual(dog.get("scale"), 0.7)
        self.assertEqual(store.values, {"scale": 0.7, "coat": 3})

    def test_language_and_sounds_are_shared(self):
        store = FakeSettings()
        dog, cat = Prefs(store), Prefs(store, "cat")
        dog.set("language", "zh")
        dog.set("interface_muted", True)
        dog.set("media_volume", 3)
        dog.set("follow_cursor", True)
        dog.set("appearance", "dark")
        self.assertEqual(cat.get("language"), "zh")
        self.assertTrue(cat.get("interface_muted"))
        self.assertEqual(cat.get("media_volume"), 3)
        self.assertTrue(cat.get("follow_cursor"))
        self.assertEqual(cat.get("appearance"), "dark")


class TuningTests(unittest.TestCase):
    def pack(self, **kw):
        return packs.Pack(id="p", kind="pet", root=Path("."), **kw)

    def test_values_are_remembered_per_pack_and_clamped(self):
        store = FakeSettings()
        a = Tuning(self.pack(), store)
        self.assertEqual(a["max_up"], 3.0, "一次最多跳几个身高默认 3")
        a.set("max_up", 4.0)
        self.assertEqual(Tuning(self.pack(), store)["max_up"], 4.0, "记住了")
        a.set("max_up", 99.0)
        self.assertEqual(a["max_up"], 6.0, "不超过范围")
        other = Tuning(packs.Pack(id="q", kind="pet", root=Path(".")), store)
        self.assertEqual(other["max_up"], 3.0, "每个模型一份")

    def test_defaults_come_from_the_pack(self):
        t = Tuning(self.pack(mass_kg=4.0, tuning={"max_up": 2.0}))
        self.assertEqual(t["mass_kg"], 4.0)
        self.assertEqual(t["max_up"], 2.0)

    def test_reset_goes_back_and_forgets(self):
        store = FakeSettings()
        t = Tuning(self.pack(), store)
        t.set("throw_gain", 2.0)
        t.reset()
        self.assertEqual(t["throw_gain"], 1.0)
        self.assertFalse(any(k.endswith("throw_gain") for k in store.values))

    def test_heavier_things_fly_less_far(self):
        dog = Tuning(self.pack(mass_kg=18.0))
        ball = Tuning(packs.Pack(id="b", kind="prop", root=Path("."), mass_kg=0.06))
        self.assertAlmostEqual(dog.throw_factor, 15.0 / 33.0)
        self.assertGreater(ball.throw_factor, 0.99)
        self.assertLess(dog.throw_factor ** 2, ball.throw_factor ** 2 * 0.25, "飞的距离约为球的五分之一")
        dog.set("throw_gain", 2.0)
        self.assertAlmostEqual(dog.throw_factor, 2.0 * 15.0 / 33.0)

    def test_copy_lists_what_changed(self):
        t = Tuning(self.pack())
        t.set("max_up", 4.0)
        text = t.copy_text()
        self.assertIn('"max_up": 4.0', text)
        self.assertNotIn("throw_gain", text)
        self.assertIn("throw_gain", Tuning(self.pack()).copy_text(), "一个都没动就全列")

    def test_param_tables_have_labels_for_both_languages(self):
        from widget import i18n
        for p in PET_PARAMS + BALL_PARAMS:
            self.assertIn(p.label, i18n.ZH, p.label)
            self.assertLessEqual(p.lo, p.default)
            self.assertLessEqual(p.default, p.hi)


class VoiceTests(unittest.TestCase):
    def bank(self, sound_map, clip_sounds=None, action_sounds=None, tuning=None):
        pack = packs.Pack(id="p", kind="pet", root=Path("."), sounds=sound_map, clip_sounds=clip_sounds or {}, action_sounds=action_sounds or {})
        with mock.patch.object(sounds, "register"):
            return SoundBank(pack, tuning, random.Random(1))

    def test_no_such_sound_is_silent(self):
        b = self.bank({})
        with mock.patch.object(sounds, "play_file") as play:
            self.assertFalse(b.play("bark"))
        play.assert_not_called()

    def test_picks_without_repeating_and_uses_the_volume_from_tuning(self):
        a, c = Path("a.wav"), Path("c.wav")
        t = mock.Mock()
        t.get = lambda key, default=1.0: 0.5 if key == "vol_bark" else default
        b = self.bank({"bark": packs.SoundSet((a, c))}, tuning=t)
        hits = []
        with mock.patch.object(sounds, "play_file", lambda f, g: hits.append((f, g)) or True):
            for _ in range(6):
                b.play("bark", 0.8)
        files = [h[0] for h in hits]
        self.assertTrue(all(x != y for x, y in zip(files, files[1:])), "不连着放同一段")
        self.assertAlmostEqual(hits[0][1], 0.4)

    def test_min_gap_skips_instead_of_queueing(self):
        b = self.bank({"bounce": packs.SoundSet((Path("a.wav"),), 0.06)})
        with mock.patch.object(sounds, "play_file", return_value=True) as play, mock.patch("widget.voice.time.monotonic", side_effect=[1.0, 1.01, 1.2]):
            b.play("bounce")
            b.play("bounce")
            b.play("bounce")
        self.assertEqual(play.call_count, 2)

    def test_sound_follows_the_mouth_in_the_clip(self):
        b = self.bank({"bark": packs.SoundSet((Path("a.wav"),))}, {"Bark": packs.ClipSound("bark", (0.62, 1.22))})
        cs = ClipSounds(b)
        with mock.patch.object(b, "play") as play:
            cs.update("Bark", 0.5, None, DT)                    # 从 0.5 秒开始播（只放中间一段）
            self.assertEqual(play.call_count, 0)
            t = 0.5
            while t < 1.0:
                t += DT
                cs.update("Bark", t, None, DT)
            self.assertEqual(play.call_count, 1, "过了 0.62")
            while t < 1.6:
                t += DT
                cs.update("Bark", t, None, DT)
            self.assertEqual(play.call_count, 2, "过了 1.22")

    def test_bow_and_bark_only_barks_as_that_action(self):
        """犬吠（表盘里点的 bow_bark）借伏地伸展的片段叫：包里写「bow_bark:Idle_5_loop」的只在做这个动作时响；
        狗自己随机做的伏地伸展（bow）、灵动交互里俯身等扔（没在做动作）播同一段都不响。"""
        b = self.bank({"bark": packs.SoundSet((Path("a.wav"),))}, {"bow_bark:Idle_5_loop": packs.ClipSound("bark", (1.0,))})
        for action, want in (("bow_bark", 1), ("bow", 0), (None, 0)):
            cs = ClipSounds(b)
            with mock.patch.object(b, "play") as play:
                t = 0.0
                cs.update("Idle_5_loop", t, action, DT)
                while t < 1.25:
                    t += DT
                    cs.update("Idle_5_loop", t, action, DT)
                self.assertEqual(play.call_count, want, f"动作 {action}")

    def test_the_dial_has_bow_and_bark_and_the_dog_alone_still_bows_silently(self):
        from widget.clips import ACTIONS_BY_ID, DEFAULT_ACTIONS, LIST_ACTIONS
        listed = [a.id for a in LIST_ACTIONS]
        self.assertIn("bow_bark", listed)
        self.assertNotIn("bow", listed, "表盘里没有伏地伸展了")
        self.assertIn("bow", DEFAULT_ACTIONS, "狗自己还会随机伏地伸展")
        self.assertNotIn("bow_bark", DEFAULT_ACTIONS, "狗自己不会犬吠：自己待着没声音")
        self.assertFalse(ACTIONS_BY_ID["bow"].mouth, "伏地伸展压住嘴")
        self.assertTrue(ACTIONS_BY_ID["bow_bark"].mouth, "犬吠照片段张嘴")
        for pid in ("border_collie", "samoyed"):
            pack = packs.discover()[pid]
            self.assertEqual(set(k for k in pack.clip_sounds if k.startswith("bow_bark:")), {"bow_bark:Idle_5_loop", "bow_bark:Idle_5_end"}, pid)

    def test_a_long_sound_stops_when_the_clip_changes(self):
        b = self.bank({"eat": packs.SoundSet((Path("a.wav"),))}, {"Eat_loop": packs.ClipSound("eat", hold=True)})
        cs = ClipSounds(b)
        with mock.patch.object(b, "play") as play, mock.patch.object(b, "stop") as stop:
            cs.update("Eat_loop", 0.0, None, DT)
            cs.update("Eat_loop", 0.1, None, DT)
            self.assertEqual(play.call_count, 1)
            cs.update("Idle_1", 0.0, None, DT)
            stop.assert_called_once_with("eat", 0.0)

    def test_eating_and_drinking_fade_in_and_eating_fades_out(self):
        """吃饭、喝水的声音出来得太突然——嚼的长声音 0.4 秒淡入、停的时候 0.5 秒淡出；舔水每一下 0.08 秒淡入；默认音量 0.35，咬的那几下跟着 vol_eat。"""
        from widget.tuning import PET_PARAMS
        defaults = {p.key: p.default for p in PET_PARAMS}
        self.assertEqual((defaults["vol_eat"], defaults["vol_lick"]), (0.35, 0.35))
        for pack_id in ("border_collie", "samoyed"):
            pk = packs.discover()[pack_id]
            eat, drink = pk.clip_sounds["Eat_loop"], pk.clip_sounds["Drink_loop"]
            self.assertEqual((eat.hold, eat.fade_in, eat.fade_out), (True, 0.4, 0.5), pack_id)
            self.assertEqual((drink.every, drink.fade_in, drink.fade_out), (1.2, 0.08, 0.0), pack_id)
            self.assertEqual(pk.sounds["bite"].volume, "eat", "咬的那几下跟着吃的音量")
        b = self.bank({"eat": packs.SoundSet((Path("e.wav"),)), "lick": packs.SoundSet((Path("l.wav"),))},
                      {"Eat_loop": packs.ClipSound("eat", hold=True, fade_in=0.4, fade_out=0.5),
                       "Drink_loop": packs.ClipSound("lick", every=1.2, fade_in=0.08)})
        cs = ClipSounds(b)
        with mock.patch.object(sounds, "play_file", return_value=True) as play, mock.patch.object(sounds, "fade_file") as fade, \
                mock.patch.object(sounds, "stop_file") as stop:
            cs.update("Eat_loop", 0.0, None, DT)
            self.assertEqual(play.call_args.kwargs.get("fade_in"), 0.4)
            cs.update("Drink_loop", 0.0, None, DT)
            fade.assert_called_once_with(Path("e.wav"), 0.5)
            stop.assert_not_called()
            for _ in range(int(1.3 / DT)):
                cs.update("Drink_loop", 0.0, None, DT)
            self.assertEqual(play.call_args.kwargs.get("fade_in"), 0.08, "舔水每一下淡入")

    def test_repeating_sound_on_an_action(self):
        b = self.bank({"sniff": packs.SoundSet((Path("a.wav"),))}, action_sounds={"sniffing": packs.ClipSound("sniff", every=1.0, first=0.2)})
        cs = ClipSounds(b)
        with mock.patch.object(b, "play") as play:
            for _ in range(int(2.5 / DT)):
                cs.update("Walk_F_IP", 0.0, "sniffing", DT)
            self.assertEqual(play.call_count, 3, "0.2、1.2、2.2 秒")
            cs.update("Idle_1", 0.0, None, DT)
            for _ in range(int(1.5 / DT)):
                cs.update("Idle_1", 0.0, None, DT)
            self.assertEqual(play.call_count, 3)

    def test_the_two_sound_switches_are_separate(self):
        """同桌音效和界面音效分开，关一个不影响另一个。"""
        with mock.patch.object(sounds, "_pack_enabled", False), mock.patch("widget.native.play_sound") as play:
            self.assertFalse(sounds.play_file(Path("a.wav")), "同桌音效关了：狗不响")
            play.assert_not_called()
            sounds.play("tap")
            play.assert_called_once()                         # 按钮照样响
        with mock.patch.object(sounds, "_enabled", False), mock.patch("widget.native.play_sound") as play:
            sounds.play("tap")
            play.assert_not_called()                          # 界面音效关了：按钮不响
            self.assertTrue(sounds.play_file(Path("a.wav")), "狗照样响")


def _rename_all(model, drop_clips=(), drop_bones=()):
    """把一个模型改头换面：所有片段、骨头名字都加前缀，有些片段、骨头没有：当作另一个模型。"""
    for n in model.nodes:
        n.name = ("gone_" if n.name in drop_bones else "x_") + n.name
    clips = {}
    for name, c in model.clips.items():
        if name not in drop_clips:
            c.name = "x_" + name
            clips[c.name] = c
    model.clips = clips
    return model


@unittest.skipUnless(HAS_MODEL, "models/collie.glb not present (purchased asset)")
class SecondModelTests(unittest.TestCase):
    """假的第二模型：片段名、骨头名全不一样，缺叫、快跑、叼东西、坐的片段，缺嘴和尾巴的骨头。加模型不用改代码，缺的动作跳过。"""

    DROP = ("Bark", "RunFast_F_IP", "Pick_up", "Put_down", "Pick_up_idle", "Sitting_start", "Sitting_loop_1", "Sitting_loop_2", "Sitting_end", "Idle_5_start")
    NO_BONES = ("mouth", "Mouth.L", "Mouth.R", "tongue_1", "tongue_2", "tongue_3", "tongue_4", "Tail_01", "Tail_02", "Tail_03", "Tail_04", "Tail_05")

    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])

    def make(self):
        from widget import gltf, native
        import widget.window as window
        model = gltf.load(config.MODEL_PATH)
        role_names = [n.name for n in model.nodes]
        clip_names = list(model.clips)
        _rename_all(model, self.DROP, self.NO_BONES)
        pack = packs.Pack(id="other", kind="pet", root=Path("."), names={"en": "Other"}, default_name="Pal", model=None,
                          clips={c: "x_" + c for c in clip_names if c not in self.DROP},
                          bones={n: "x_" + n for n in role_names if n not in self.NO_BONES},
                          mass_kg=5.0, height_m=0.8)
        packs.apply_names(model, pack)
        self.assertEqual(packs.problems(model), [])
        for p in (mock.patch.object(window, "QSettings", FakeSettings), mock.patch.object(native, "window_frames", lambda pid: []),
                  mock.patch.object(native, "window_frame", lambda n: None), mock.patch.object(native, "window_covered", lambda n, x, y, pid: None)):
            p.start()
            self.addCleanup(p.stop)
        win = window.CompanionWindow(model, pack=pack)
        win._anim_timer.stop()
        self.addCleanup(win.hide)
        return win, model

    def step(self, win, seconds, until=None):
        pg = win.playground
        for i in range(int(seconds / DT)):
            pg._frames_at = -math.inf if i % 15 == 0 else pg._frames_at
            win._feel(DT)                                        # 兴奋度：和窗口每帧一样排在游乐场前面
            pg.update(DT)
            win.dog.set_look_target(win._look_target(DT))
            win.dog.update(DT)
            win._pose = win.dog.frame()
            pg.after_pose()
            if pg.roam.moved:
                win.place_scene(pg.roam.wx, pg.roam.wy)
            if until is not None and until():
                return i * DT
        return None

    def test_missing_clips_fall_back_and_missing_bones_are_skipped(self):
        win, model = self.make()
        self.assertEqual(model.clips["Run_F_IP"].name, "Run_F_IP", "名字换回代码认的了")
        self.assertEqual(model.clips["RunFast_F_IP"].name, "Run_F_IP", "没有快跑：用跑")
        self.assertEqual(model.clips["Bark"].name, "Idle_1", "没有叫：站着")
        self.assertNotIn("Bark", model.clips, "in 还是说没有")
        self.assertEqual(win.dog.mouth_bones, [], "没有嘴：闭嘴什么也不做")

    def test_settings_are_its_own(self):
        win, _ = self.make()
        self.assertEqual(win.prefs.pack_id, "other")
        self.assertEqual(win.dog_name, "Pal")
        win.set_scale(1.3)
        self.assertEqual(win.settings.value("scale"), 1.3, "大小是全局的，不跟着模型记")
        self.assertIsNone(win.settings.value("pack/other/scale"))
        win.set_dog_name("Rex")
        self.assertEqual(win.settings.value("pack/other/dog_name"), "Rex", "名字还是它自己的")
        self.assertIsNone(win.settings.value("dog_name"))
        self.assertEqual(win.tuning["mass_kg"], 5.0)

    def test_it_can_play_fetch_and_lift_without_crashing(self):
        from PySide6.QtCore import QPointF
        win, _ = self.make()
        win.show()
        ag = self.app.primaryScreen().availableGeometry()
        floor = ag.y() + ag.height() - 18.0 * win.scale
        win.place_scene(560.0, floor)
        win.dog.snap_home(210.0)
        pg = win.playground
        pg.start()
        self.step(win, 0.3)
        b = pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        self.step(win, 4.0)                                     # 球就在狗前面（捡球的圈里）：停够了圈满；叫、俯身的片段都没有，站着等
        self.assertTrue(pg.ring.ready, "圈满了：这一扔会去追")
        self.assertTrue(pg.roam.bowing, "叫的片段没有就直接到「俯身」这一步（片段是站着的替代）")
        pg.ball_release(QPointF(b.x - 100.0, b.y))
        self.assertIsNotNone(self.step(win, 20.0, lambda: pg.roam.task is None), "跑到球旁边就算了（没有叼的片段）")
        self.assertFalse(pg.roam.carrying)
        pg.dog_grabbed()
        self.step(win, 0.3)
        pg.dog_dropped()
        self.assertIsNotNone(self.step(win, 5.0, lambda: pg.roam.task is None), "落回去了")
        win.place_scene(560.0, floor)
        pg.roam.go_to(pg.world.floors[0], 100.0)
        self.assertIsNotNone(self.step(win, 8.0, lambda: pg.roam.task is None), "跑得动")
        self.assertTrue(pg.active, "没出错")


@unittest.skipUnless(HAS_SAMOYED, "models/samoyed.glb not present (purchased asset)")
class SamoyedModelTests(unittest.TestCase):
    """真的第二个模型：和边牧同一个作者、同一套骨架和动作，包里 clips / bones 不用写对照。"""

    @classmethod
    def setUpClass(cls):
        cls.pack = packs.discover()[SAMOYED]
        cls.model = packs.load_model(cls.pack)

    def test_it_loads_and_has_nothing_missing(self):
        self.assertIn(self.pack, packs.pets())
        self.assertEqual(packs.problems(self.model), [])
        self.assertEqual(len(self.model.clips), 89)
        self.assertEqual(len(self.model.skin_joints), 57)
        self.assertTrue(self.model.texture_png, "第一套毛色嵌在模型里")
        self.assertEqual(self.model.gain, self.pack.brightness, "提亮的倍数写在模型上，渲染器从那读（render.DogRenderer.init）")

    def test_every_clip_and_bone_the_code_asks_for_is_really_there(self):
        """要的片段都是它自己的，没有一段是靠 CLIP_FALLBACK 顶上的；嘴、尾巴、眼睛、爪子的骨头都在。"""
        from widget import clips, coat, roam
        wanted = {packs.IDLE, roam.BACK_CLIP, "Bark", "Pick_up", "Put_down", "Pick_up_idle", *roam.GAIT_CLIPS.values(), *packs.CLIP_FALLBACK, *packs.CLIP_FALLBACK.values(),
                  *(k.split(":")[-1] for k in self.pack.clip_sounds)}         # 「动作:片段」只按片段查（动作那半在 clips.ACTIONS 里）
        for jump in roam.JUMPS.values():
            wanted.update(c for c in (jump.start, jump.air, jump.land) if c)
        for action in clips.ACTIONS:
            wanted.update(step if isinstance(step, str) else step[1] for step in action.program if isinstance(step, str) or step[0] == "loop")
        missing = sorted(c for c in wanted if not dict.__contains__(self.model.clips, c))
        self.assertEqual(missing, [])
        names = {n.name for n in self.model.nodes}
        bones = {*packs.REQUIRED_BONES, *packs.BONE_FALLBACK, *coat.PROTECTED_BONES, "foot_f.L", "foot_f.R", "foot_b.L", "foot_b.R", "Tail_05", "Ear_02.L", "Ear_02.R"}
        self.assertEqual(sorted(bones - names), [])

    @unittest.skipUnless(HAS_MODEL, "models/collie.glb not present (purchased asset)")
    def test_same_skeleton_and_clips_as_the_collie(self):
        from widget import gltf
        collie = gltf.load(config.MODEL_PATH)
        self.assertEqual(set(self.model.clips), set(collie.clips))
        joints = lambda m: [m.nodes[j].name for j in m.skin_joints]      # noqa: E731
        self.assertEqual(joints(self.model), joints(collie))

    def test_sounds_land_inside_their_clips(self):
        for name, bound in self.pack.clip_sounds.items():
            for t in bound.at:
                self.assertLess(t, self.model.clips[name].duration, name)

    def test_coat_files_are_next_to_the_model(self):
        for name in self.pack.coats:
            self.assertTrue((self.pack.coat_dir / name).is_file(), name)

    def test_it_runs_and_gets_lifted_in_a_real_window(self):
        """整只放进窗口：名字、质量是它自己的；灵动交互里跑一段、拎起来放下不出错（行为还是边牧那一套，没按它调）。"""
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        from widget import native
        import widget.window as window
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(q in msg for q in QUIET) else sys.stderr.write(msg + "\n"))
        app = QApplication.instance() or QApplication([])
        for patch in (mock.patch.object(window, "QSettings", FakeSettings), mock.patch.object(native, "window_frames", lambda pid: []),
                      mock.patch.object(native, "window_frame", lambda n: None), mock.patch.object(native, "window_covered", lambda n, x, y, pid: None)):
            patch.start()
            self.addCleanup(patch.stop)
        win = window.CompanionWindow(packs.load_model(self.pack), pack=self.pack)
        win._anim_timer.stop()
        self.addCleanup(win.hide)
        self.assertEqual((win.prefs.pack_id, win.dog_name, win.tuning["mass_kg"]), (SAMOYED, "Mochi", 23.0))
        win.show()
        ag = app.primaryScreen().availableGeometry()
        floor = ag.y() + ag.height() - 18.0 * win.scale
        win.place_scene(560.0, floor)
        win.dog.snap_home(210.0)
        pg = win.playground
        pg.start()
        step = SecondModelTests.step
        step(self, win, 0.3)
        pg.roam.go_to(pg.world.floors[0], 100.0)
        self.assertIsNotNone(step(self, win, 8.0, lambda: pg.roam.task is None), "跑得动")
        pg.dog_grabbed()
        step(self, win, 0.3)
        pg.dog_dropped()
        self.assertIsNotNone(step(self, win, 5.0, lambda: pg.roam.task is None), "落回去了")
        self.assertTrue(pg.active, "没出错")


class TuningPageTests(PanelCase):
    DYNAMIC = True

    def open_tuning(self):
        s = self.settings
        for _ in range(5):
            s._version_clicked()
        s.finish_page_anim()
        return s.tuning_page

    def test_five_quick_clicks_on_the_version_open_it(self):
        s = self.settings
        s.show_advanced(True, animated=False)
        for _ in range(4):
            s._version_clicked()
        self.assertEqual(s.page, "advanced", "四下不够")
        s._version_clicked()
        self.assertEqual(s.page, "tuning")
        self.assertEqual(s._back_target(), "advanced")

    def test_real_clicks_on_the_version_label_count(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        s = self.settings
        s.show_advanced(True, animated=False)
        s.show()
        p = QPointF(3, 3)
        for k in range(5):
            kind = QEvent.MouseButtonDblClick if k % 2 else QEvent.MouseButtonPress    # 连点时 Qt 把第二下报成双击
            QApplication.sendEvent(s.version_label, QMouseEvent(kind, p, s.version_label.mapToGlobal(p), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(s.page, "tuning")
        s.hide()

    def test_slow_clicks_do_not_count(self):
        s = self.settings
        s.show_advanced(True, animated=False)
        with mock.patch("widget.settings.time.monotonic", side_effect=[0.0, 2.0, 4.0, 6.0, 8.0]):
            for _ in range(5):
                s._version_clicked()
        self.assertEqual(s.page, "advanced")

    def test_pills_pick_the_model_and_rows_list_its_params(self):
        """所有的狗、小球、所有物件都能调——狗一行，小球和「物件」页能摆的那几类一行；进来默认选现在这只。"""
        from widget.things import BALL_KEY, page_styles
        from widget.tuning import THING_PARAMS
        page, win = self.open_tuning(), self.win
        pets = packs.pets()
        kinds = {s.pack for s in page_styles() if s.key != BALL_KEY}
        self.assertEqual(len(page.pills), len(pets) + 1 + len(kinds))
        self.assertEqual([page.targets[k][1].pack.id for k in range(len(pets))], [p.id for p in pets])
        cur = page.current
        self.assertIs(page.targets[cur][1], win.tuning, "进来默认选现在这只")
        self.assertEqual([r.param.key for r in page.rows[cur]], [p.key for p in PET_PARAMS])
        self.assertEqual(sum(box is not None for box in page.lists), 1, "别的那几样用到才建")
        ball = len(pets)
        page.select(ball)
        self.assertIs(page.targets[ball][1], win.ball_tuning)
        self.assertEqual([r.param.key for r in page.rows[ball]], [p.key for p in BALL_PARAMS])
        self.assertFalse(page.lists[cur].isVisibleTo(page))
        self.assertTrue(page.lists[ball].isVisibleTo(page))
        for k in range(ball + 1, len(page.targets)):
            page.select(k)
            self.assertEqual([r.param.key for r in page.rows[k]], [p.key for p in THING_PARAMS], page.targets[k][0])
            self.assertIs(page.targets[k][1], win.kits.tuning(packs.discover()[page.targets[k][1].pack.id]), "每个包一份")
        from widget.tuning_page import PILLS_W
        self.assertEqual([len(f.pills) for f in page.flows], [len(pets), 1 + len(kinds)], "狗一行，小球和物件另起一行")
        for flow in page.flows:
            flow.place()
            for pill in flow.pills:
                self.assertLessEqual(pill.geometry().right(), PILLS_W, f"{pill.text()} 排得下（排不下的换到下一行）")
                self.assertGreaterEqual(pill.geometry().width(), pill.sizeHint().width(), "按排的时候的字体量")

    def test_moving_a_slider_applies_at_once_and_snaps_to_the_step(self):
        page = self.open_tuning()
        win = self.win
        row = next(r for r in page.rows[0] if r.param.key == "max_up")
        row.slider._apply(4.04)
        self.assertAlmostEqual(win.tuning["max_up"], 4.0, msg="一格 0.1")
        self.assertEqual(row.value_label.text(), "4.0")
        self.assertAlmostEqual(win.playground.roam.max_up(), 4.0 * win.pack.height_m * win.ppm, delta=0.5, msg="狗马上按新的算")

    def test_the_wheel_scrolls_the_page_instead_of_changing_values(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        page = self.open_tuning()
        row = page.rows[0][0]
        before = row.slider.value
        ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        row.slider.wheelEvent(ev)
        self.assertEqual(row.slider.value, before)
        self.assertFalse(ev.isAccepted())

    def test_restore_defaults_and_copy(self):
        from PySide6.QtGui import QGuiApplication
        page = self.open_tuning()
        win = self.win
        win.tuning.set("throw_gain", 2.5)
        page.on_show()
        row = next(r for r in page.rows[0] if r.param.key == "throw_gain")
        self.assertEqual(row.slider.value, 2.5)
        page.copy()
        self.assertIn('"throw_gain": 2.5', QGuiApplication.clipboard().text())
        page.reset()
        self.assertEqual(win.tuning["throw_gain"], 1.0)
        self.assertEqual(row.slider.value, 1.0)

    def test_it_fits_on_a_small_screen_because_the_list_scrolls(self):
        page = self.open_tuning()
        self.assertLess(page.sizeHint().height(), 500, "笔记本屏幕放得下（英文的物件那一行排成两行）")
        self.win.set_language("zh")
        self.settings = self.win.settings_panel
        page = self.open_tuning()
        self.assertEqual(page.pills[0].text(), "边牧")
        self.assertLess(page.sizeHint().height(), 500, "中文也放得下")

    def test_it_is_called_developer_settings(self):
        """开发者设置页的名字。"""
        from widget import i18n
        self.assertEqual(i18n.ZH["Developer"], "开发者设置")
        self.assertNotIn("Tuning", i18n.ZH)
        self.assertEqual(self.settings.pages["tuning"].title, "Developer")


class BuildNumberTests(PanelCase):
    """开发版版本号右边带构建号；发布版（--release、--stable 打的包，config.DEV_BUILD 是 False）不带，只在开发者设置页最底下有。"""

    def card(self, dev: bool):
        from widget.settings import SettingsPanel
        with mock.patch.object(config, "DEV_BUILD", dev):
            card = SettingsPanel(self.win)
        self.addCleanup(card.hide)
        return card

    def test_a_dev_build_shows_the_build_next_to_the_version(self):
        card = self.card(True)
        self.assertEqual(card.version_label.text(), f"Version {config.VERSION} ({config.BUILD})")
        self.assertEqual(card.build_label.text(), f"Version {config.VERSION} ({config.BUILD})")

    def test_a_release_hides_it_except_in_developer_settings(self):
        card = self.card(False)
        self.assertEqual(card.version_label.text(), f"Version {config.VERSION}")
        self.assertEqual(card.build_label.text(), f"Version {config.VERSION} ({config.BUILD})", "开发者设置里一直有")
        self.assertTrue(card.tuning_page.isAncestorOf(card.build_label))

    def test_new_versions_follow_the_same_rule(self):
        from widget import updater
        with mock.patch.object(config, "DEV_BUILD", True):
            self.assertEqual(updater.version_text("0.6.1", 70), "0.6.1 (70)")
            self.assertEqual(updater.version_text("1.0.0", 0), "1.0.0", "正式版没有构建号")
        with mock.patch.object(config, "DEV_BUILD", False):
            self.assertEqual(updater.version_text("0.6.1", 70), "0.6.1")

    def test_the_committed_config_is_a_dev_build(self):
        """打包脚本 --release / --stable 才临时改成 False，打完改回 True；提交的 config.py 一直是 True（脚本找不到这一行就不打）。"""
        text = (config.ROOT / "config.py").read_text(encoding="utf-8")
        self.assertIn("\nDEV_BUILD = True\n", text)
        script = (config.ROOT / "tools" / "build_app.sh").read_text(encoding="utf-8")
        self.assertIn("s/^DEV_BUILD = True$/DEV_BUILD = False/", script)
        self.assertIn("s/^DEV_BUILD = False$/DEV_BUILD = True/", script, "打完（失败、中断也算）改回去")


class BallMenuAndPetRowTests(PanelCase):
    DYNAMIC = True

    def test_sounds_row_is_renamed(self):
        """音效分「媒体音效 / 界面音效」两个（不叫「同桌音效」：分不清「同桌」是狗还是软件）。"""
        from widget import i18n
        self.assertEqual(i18n.ZH["Media sounds"], "媒体音效")
        self.assertEqual(i18n.ZH["Interface sounds"], "界面音效")
        self.assertNotIn("Deskmate sounds", i18n.ZH)
        self.assertNotIn("Sounds", i18n.ZH)

    def test_the_ball_menu_says_no_more_ball_and_puts_it_away(self):
        """右键道具通通是「我不要……了」——不带开关，点一下这一件收起来、胶囊跟着收；球的名字叫「小球」。"""
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import i18n
        from widget.things import BALL_KEY
        w = self.win
        menu = w._build_ball_menu()
        self.assertEqual(menu.text, "No more ball")
        self.assertTrue(menu.action, "不带开关")
        i18n.set_language("zh")
        self.assertEqual(w._build_ball_menu().text, "我不要小球了")
        i18n.set_language("en")
        menu = w._build_ball_menu()
        menu.popup_at(QPoint(100, 100))
        self.assertTrue(menu.isVisible())
        c = menu.pill_rect().center()
        menu.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, c, QPointF(menu.mapToGlobal(c.toPoint())), Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        self.assertFalse(menu.isVisible(), "点了胶囊跟着收")
        self.assertFalse(w.ball_out, "小球收起来了")
        self.assertIs(w.settings.values["ball_out"], False, "记住了")
        self.assertFalse(w.thing_on(BALL_KEY), "「物件」页那一格、道具栏读的是同一个")
        w.set_thing(BALL_KEY, True)
        self.assertTrue(w.ball_out)

    def test_the_ball_menu_grows_with_the_dog_like_the_other_pills(self):
        w = self.win
        from widget.hovermenu import menu_scale
        from widget.overlay import MENU_BASE_H
        self.assertAlmostEqual(w._build_ball_menu().pill_rect().height(), MENU_BASE_H * menu_scale(w.scale), delta=1.0, msg="和悬浮栏的胶囊一样高")
        small = w._ball_menu.pill_rect().height()
        w.set_scale(1.6)
        self.assertGreater(w._build_ball_menu().pill_rect().height(), small + 3.0, "狗大了胶囊也大")


class SingleModelTests(PanelCase):
    """只有一个模型（新 clone 下来、没放萨摩耶的模型文件时就是这样）。"""
    DYNAMIC = True

    def setUp(self):
        real = packs.discover()
        p = mock.patch("widget.window.packs.pets", lambda found=None: [real[packs.DEFAULT_PET]])
        p.start()
        self.addCleanup(p.stop)
        super().setUp()

    def test_a_single_model_says_more_are_coming_on_the_add_page(self):
        """只有一个模型也写一句还会有。这句话在添加页的模型格子下面。"""
        from widget.i18n import tr
        s = self.settings
        self.assertEqual(len(self.win.available_pets()), 1)
        self.assertFalse(hasattr(s, "pet_button"))
        s.open_add_pet()
        s.finish_page_anim()
        self.assertEqual(s.page, "add")
        self.assertEqual(s._back_target(), "main")
        self.assertEqual(len(s.add_tiles), 1)
        self.assertEqual(s.more_note.text(), tr("More deskmates on the way"))


class PetRowTests(PanelCase):
    def setUp(self):
        other = packs.Pack(id="other", kind="pet", root=Path("."), names={"en": "Other", "zh": "另一个"}, model=config.MODEL_PATH)   # 读得出来：指着边牧的模型文件
        real = packs.discover()
        p = mock.patch("widget.window.packs.pets", lambda found=None: [real[packs.DEFAULT_PET], other])
        p.start()
        self.addCleanup(p.stop)
        super().setUp()

    def test_with_two_models_the_add_page_offers_both_and_an_existing_one_keeps_its_model(self):
        """高级设置里选模型那一层没有意义了。一只同桌的模型在添加时定；想要别的模型就添一只（当场换过去，不重启）。"""
        s, w = self.settings, self.win
        self.assertFalse(hasattr(s, "pet_button"))
        self.assertFalse(hasattr(w, "set_pack"), "已有的同桌不能换模型")
        s.open_add_pet()
        s.finish_page_anim()
        self.assertEqual(s.page, "add")
        self.assertIsNone(s.more_note)
        tiles = s.add_tiles
        self.assertEqual([t.pack.id for t in tiles], [packs.DEFAULT_PET, "other"])
        self.assertTrue(tiles[0].selected)
        self.assertFalse(tiles[1].selected)
        tiles[1].click()
        self.assertTrue(tiles[1].selected)
        w.kits.get(tiles[1].pack)                                     # 选了那一格就在后台备（_pick_add）；这里等它备好，没备好时备好了再添见 test_pets.PendingSwitchTests
        with mock.patch.object(w, "restart") as restart:
            s.add_button.click()
        restart.assert_not_called()
        s.finish_page_anim()
        self.assertEqual(w.settings.values["pack"], "other", "记下来：下次启动按它载入")
        self.assertEqual([p.pack for p in w.pets()], [packs.DEFAULT_PET, "other"], "原来那只还是原来的模型")
        self.assertEqual((w.pack.id, w.prefs.pet_id), ("other", w.pets()[1].id), "当场换过去了")
        self.assertEqual(s.strip.center(), 1, "滑动条正中是新的那只")


if __name__ == "__main__":
    unittest.main()
