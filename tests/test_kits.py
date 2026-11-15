"""别的模型在后台先备好（widget/kits.py）：后台读、量好记在模型上，get 会等，读不出来给 None，同一个包只读一次，
forget 丢掉，做完线程切换间隔改回去；窗口启动时把自己那只记成现成的。假的「另一个模型」指着边牧的模型文件（不用买来的萨摩耶也能跑）。"""
import dataclasses
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

import config
from tests.panel_base import QUIET, FakeSettings, PanelCase
from widget import packs

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
MEASURED = {"clip_tops", "feet", "lift_rig", "lie_span", "leap", "nose_spots", "bound_vertices", "outline_weights"}


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class KitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.collie = packs.discover()[packs.DEFAULT_PET]

    def setUp(self):
        from widget.kits import Kits
        self.store = FakeSettings()
        self.kits = Kits(self.store)
        self.other = dataclasses.replace(self.collie, id="other", default_name="Bo", height_m=0.9)
        self.reads = []
        real = packs.load_model

        def counting(pack):
            self.reads.append((pack.id, threading.current_thread() is threading.main_thread(), sys.getswitchinterval()))
            return real(pack)
        p = mock.patch.object(packs, "load_model", counting)
        p.start()
        self.addCleanup(p.stop)

    def land(self, pack_id):
        """等后台那件做完、信号回到主线程。"""
        self.kits._jobs[pack_id].result()
        self.app.processEvents()

    def test_another_model_is_prepared_in_the_background_and_measured_on_the_model(self):
        self.kits.want(self.other)
        self.assertFalse(self.kits.ready("other"), "要等后台做完")
        self.land("other")
        self.assertTrue(self.kits.ready("other"), "做完自己回到主线程记好，不用谁来 get")
        kit = self.kits.get(self.other)
        self.assertEqual([(pid, main) for pid, main, _ in self.reads], [("other", False)], "在后台线程读的")
        self.assertLessEqual(MEASURED, set(kit.model.measured), "换上来马上要用的都量好了，记在模型上")
        self.assertIs(kit.pack, self.other)
        self.assertIs(kit.tuning.pack, self.other)
        self.assertIs(kit.bank.pack, self.other)
        self.assertIs(kit.bank.tuning, kit.tuning, "声音的音量跟它自己的调参")
        self.assertIs(kit.tuning.store, self.store, "调参存在窗口的设置里，按包分开")

    def test_get_waits_and_a_pack_is_read_once(self):
        self.kits.want(self.other)
        self.kits.want(self.other)
        kit = self.kits.get(self.other)                           # 还在做：等它
        self.assertIsNotNone(kit)
        self.assertIs(self.kits.get(self.other), kit)
        self.kits.want(self.other)
        self.app.processEvents()                                  # 后来到的信号：已经记好了，不再建一份
        self.assertIs(self.kits.get(self.other), kit)
        self.assertEqual(len(self.reads), 1, "同一个包只读一次")
        fresh = dataclasses.replace(self.collie, id="fresh")
        self.assertIsNotNone(self.kits.get(fresh), "没人叫过 want 的：现在开始，等它")
        self.assertEqual(len(self.reads), 2)

    def test_a_model_that_cannot_be_read_gives_none_and_is_not_tried_again(self):
        gone = dataclasses.replace(self.collie, id="gone", model=Path("/nonexistent/dog.glb"))
        broken = dataclasses.replace(self.collie, id="broken", bones={"not_a_head": "head"})   # 头骨被改了名：缺头（packs.problems）
        with self.assertLogs("kits", "ERROR"):
            self.assertIsNone(self.kits.get(gone))
            self.assertIsNone(self.kits.get(broken))
        self.assertTrue(self.kits.failed("gone") and self.kits.failed("broken"))
        reads = len(self.reads)
        self.assertIsNone(self.kits.get(gone))
        self.kits.want(broken)
        self.assertEqual(len(self.reads), reads, "这次运行不再试")
        self.assertFalse(self.kits.ready("gone"))

    def test_the_switch_interval_is_short_only_while_preparing_and_forget_drops_it(self):
        from widget import look
        before = sys.getswitchinterval()
        kit = self.kits.get(self.other)
        self.assertEqual(self.reads[0][2], 0.0005, "备的时候 0.5 毫秒：主线程每帧早点拿回 GIL")
        self.assertEqual(sys.getswitchinterval(), before, "做完改回去")
        look._worker_painters[id(kit.model)] = (kit.model, object())
        self.kits.forget("other")
        self.assertFalse(self.kits.ready("other"))
        self.assertNotIn(id(kit.model), look._worker_painters, "出贴图那条线程给它留的遮罩一起丢")
        self.assertIsNotNone(self.kits.get(self.other), "丢了还能再备")

    def test_adopt_keeps_the_running_one_as_it_is(self):
        from widget.tuning import Tuning
        from widget.voice import SoundBank
        from widget import gltf
        model = gltf.load(config.MODEL_PATH)
        tuning = Tuning(self.collie, self.store)
        bank = SoundBank(self.collie, tuning)
        kit = self.kits.adopt(self.collie, model, tuning, bank)
        self.assertIs(self.kits.get(self.collie), kit)
        self.kits.want(self.collie)
        self.assertEqual(self.reads, [], "现成的不再读")
        self.assertEqual((kit.model, kit.tuning, kit.bank), (model, tuning, bank))


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class ApartTests(unittest.TestCase):
    """别的模型在单独的子进程里备（kits.PROCESS，spawn），分块送回来、一块一块解。真起子进程（每次约 0.5 秒）。"""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.collie = packs.discover()[packs.DEFAULT_PET]

    def test_the_model_from_the_child_is_the_same_as_one_prepared_here(self):
        from widget import kits
        here = kits._prepare(self.collie)
        apart = kits._prepare_apart(self.collie)
        self.assertIsInstance(apart.clips, packs.ClipTable, "片段表还是会往下找的那种")
        self.assertEqual(list(dict.keys(apart.clips)), list(dict.keys(here.clips)), "片段一段不少、先后不变")
        name = next(iter(dict.keys(here.clips)))
        self.assertEqual(apart.clips[name].duration, here.clips[name].duration)
        self.assertIs(apart.clips["NoSuchClip"], dict.__getitem__(apart.clips, packs.IDLE), "没有的片段照旧落到站着待机")
        self.assertEqual(apart.mesh.vertex_count, here.mesh.vertex_count)
        self.assertEqual(bytes(apart.mesh.positions), bytes(here.mesh.positions))
        self.assertEqual(apart.texture_png, here.texture_png)
        self.assertLessEqual(MEASURED, set(apart.measured), "量好的表跟着回来，换上来不用再量")
        self.assertEqual(apart.measured["clip_tops"], here.measured["clip_tops"])
        self.assertIs(apart.measured["lift_rig"].model, apart, "拎起来的姿势指着收回来的这个模型，不是另一份")

    def test_a_model_the_child_cannot_read_raises_here(self):
        from widget import kits
        gone = dataclasses.replace(self.collie, id="gone", model=Path("/nonexistent/dog.glb"))
        with self.assertRaises(RuntimeError) as caught:
            kits._prepare_apart(gone)
        self.assertIn("nonexistent", str(caught.exception), "子进程里出错的经过带回来记日志")

    def test_when_ready_calls_back_on_the_main_thread_without_waiting(self):
        from widget import kits
        store = FakeSettings()
        got = []
        other = dataclasses.replace(self.collie, id="other")
        with mock.patch.object(kits, "PROCESS", True):
            k = kits.Kits(store)
            k.when_ready(other, lambda kit: got.append((kit, threading.current_thread() is threading.main_thread())))
            self.assertEqual(got, [], "不在这里等：备好了再叫")
            k._jobs["other"].result()
            self.app.processEvents()
        self.assertEqual(len(got), 1)
        kit, on_main = got[0]
        self.assertIsNotNone(kit)
        self.assertTrue(on_main, "回到主线程叫")
        self.assertIs(k.ready_kit("other"), kit)
        later = []
        k.when_ready(other, later.append)
        self.assertEqual(later, [kit], "已经备好的当场叫")


class WindowKitsTests(PanelCase):
    def test_the_window_adopts_its_own_model_at_start(self):
        win = self.win
        kit = win.kits.get(win.pack)
        self.assertIsNotNone(kit)
        self.assertEqual((kit.model, kit.tuning, kit.bank), (win.model, win.tuning, win.sound_bank))


if __name__ == "__main__":
    unittest.main()
