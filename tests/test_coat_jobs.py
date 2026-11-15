"""换同桌时的毛色贴图在后台线程出（look._CoatJobs）：2048 的 PNG 解码一次 30～90 毫秒、自定义的现算 40～160 毫秒，
放在主线程上「我的同桌」滑到位那一下整张卡片停住。这里验：主线程不解码、后来的作数、和身上一样的不重出、当场选的不被后到的盖掉、
第一套传完不留、坏文件换回第一套；后台解码不会和别的线程卡死。"""
import os
import subprocess
import sys
import textwrap
import threading
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtGui import QImage

import config
from tests.panel_base import PanelCase
from widget import look as look_mod


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class DecodeDeadlockTests(unittest.TestCase):
    def test_decoding_in_the_background_never_deadlocks_with_a_decode_holding_the_gil(self):
        """后台的 look.decode_png 读 Python 建的 QBuffer 会卡死：Qt 认格式时在 QImageReader 的全局锁里调它的虚函数要拿 GIL，
        这时别的线程拿着 GIL 用 QImage.fromData 等这把锁，两边一直等。在子进程里来回撞 1.5 秒，30 秒还没完就是卡死了。"""
        code = textwrap.dedent("""
            import threading, time
            from PySide6.QtCore import QBuffer, QIODevice
            from PySide6.QtGui import QGuiApplication, QImage
            import config
            from widget import gltf, look
            app = QGuiApplication([])
            png = gltf.load(config.MODEL_PATH).texture_png
            small = QImage(64, 64, QImage.Format_RGBA8888)
            small.fill(0xff336699)
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            small.save(buf, "PNG")
            tiny = bytes(buf.data())
            stop = time.perf_counter() + 1.5
            count = []
            def background():
                while time.perf_counter() < stop:
                    assert not look.decode_png(png).isNull()
                    count.append(1)
            t = threading.Thread(target=background)
            t.start()
            while time.perf_counter() < stop:
                QImage.fromData(tiny)
            t.join()
            assert count
        """)
        done = subprocess.run([sys.executable, "-c", code], cwd=str(config.ROOT), capture_output=True, text=True, timeout=30,
                              env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])


class CoatJobTests(PanelCase):
    def setUp(self):
        super().setUp()
        self.look = self.win.look
        self.renderer = self.win.view.renderer
        self.main = threading.current_thread()
        self.threads = []
        real_png, real_file = look_mod.decode_png, look_mod.read_image

        def png(data):
            self.threads.append(threading.current_thread())
            return real_png(data)

        def file(path):
            self.threads.append(threading.current_thread())
            return real_file(path)
        for name, fake in (("decode_png", png), ("read_image", file)):
            patch = mock.patch.object(look_mod, name, side_effect=fake)
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.look.settle)

    def _need_coat(self, i):
        if not self.win.coat_available()[i - 1]:
            self.skipTest(f"models/texture 里没有第 {i} 套")

    def _switch_to(self, coat, custom=None):
        """当这只同桌记的毛色是 coat（自定义参数 custom），走一次换同桌：返回 then 被调了几次的计数。"""
        self.win.prefs.set("coat", coat)
        if custom is not None:
            self.win.prefs.set("coat_custom", custom)
        calls = []
        self.look.reload(lambda: calls.append(1))
        return calls

    def test_switching_decodes_off_the_main_thread_and_lands_with_then(self):
        self._need_coat(2)
        self.look._coat_dark.clear()                               # 深浅两色记在模型上（同一类的用例共用一个模型）：从没算过的算起
        calls = self._switch_to(2)
        self.assertEqual(self.win.coat, 2, "号马上就是新的（卡片、贴纸按它算）")
        self.assertEqual(calls, [], "贴图还在后台出：先不淡入、卡片先不跟")
        with mock.patch.object(look_mod.Look, "coat_image", side_effect=AssertionError("主线程不该解码")):
            self.look.settle()
        self.assertEqual(calls, [1])
        self.assertTrue(self.threads and all(t is not self.main for t in self.threads), self.threads)
        self.assertIsNotNone(self.renderer.coat_image)
        self.assertIn(2, self.look._coat_dark, "强调色要的深浅两色也在后台算好了")

    def test_a_newer_switch_wins_and_the_older_then_is_dropped(self):
        self._need_coat(2)
        first = self._switch_to(2)
        second = self._switch_to(1)
        self.look.settle()
        self.assertEqual((first, second), ([], [1]))
        self.assertIsNone(self.renderer.coat_image, "最后换到的是第一套（模型自带的）")
        self.assertEqual(self.win.coat, 1)

    def test_two_jobs_in_flight_only_the_newer_one_lands(self):
        """两件都真的在后台出（都和身上那张不一样）：旧的那件出完了也不用，它的 then 不调，不往新那只的设置里写东西。"""
        self._need_coat(2)
        self._need_coat(3)
        first = self._switch_to(2)
        second = self._switch_to(3)
        self.look.settle()
        self.app.processEvents()                              # 旧那件的结果要是晚到，也在这里送到
        self.assertEqual((first, second), ([], [1]))
        self.assertEqual((self.win.coat, self.win.prefs.get("coat")), (3, 3))
        self.assertEqual(self.look._wearing, ("coat", 3))
        self.assertIsNotNone(self.renderer.coat_image)

    def test_switching_pets_fades_in_only_once_the_new_coat_is_on(self):
        """window._enter_pet：卡片当场跟上，狗等贴图换上（_coat_on）才淡入。滑动条到位时叫的淡入（fade_dog(True)）这时不算，
        不然先带着上一只的毛色淡回来、半路换毛色；保险（_fade_guard）响了照样淡回来。现在这只的贴纸也等贴图换上再画。"""
        self._need_coat(2)
        win = self.win
        win.show()
        self.addCleanup(win.hide)
        other = win.roster.add(win.pack.id)
        win.prefs.of(other.id, win.pack.id).set("coat", 2)
        shot = []
        real_shots = win.pet_shots
        with mock.patch.object(win, "pet_shots", side_effect=lambda pets, *a: (shot.append([p.id for p in pets]), real_shots(pets, *a))[1]), \
                mock.patch.object(win, "_fade_to") as fade_to:
            win.switch_pet(other.id)
            self.assertTrue(win.coat_pending())
            self.assertEqual(self.settings.strip.pets[-1].id, other.id, "名单当场跟上")
            self.assertEqual([c.args[0] for c in fade_to.call_args_list], [0.0], "先收起")
            win.fade_dog(True)                                # 滑动条到位
            self.assertEqual([c.args[0] for c in fade_to.call_args_list], [0.0], "贴图没换上：不淡入")
            self.settings.strip._ensure_stickers()
            self.assertFalse(any(other.id in ids for ids in shot), "贴图没换上：不画现在这只的贴纸")
            self.look.settle()
            self.assertFalse(win.coat_pending())
            self.assertTrue(win._fade_soon.isActive() or fade_to.call_args_list[-1].args[0] == 1.0, "换上了：淡入（或等新的画出来再淡入）")
            self.assertTrue(any(other.id in ids for ids in shot), "换上了：现在这只的贴纸照身上这张画")
            win._fade_soon.stop()
            win.prefs.of(win.roster.pets()[0].id, win.pack.id).set("coat", 3 if win.coat_available()[2] else 1)
            win.switch_pet(win.roster.pets()[0].id)
            fade_to.reset_mock()
            win._fade_guard.stop()                            # 保险已经响过（单发计时器响的时候已经不在计时）
            win.fade_dog(True)
            self.assertEqual([c.args[0] for c in fade_to.call_args_list], [1.0], "保险响了：贴图还没换上也淡回来")

    def test_the_same_coat_needs_no_job(self):
        self._need_coat(2)
        self._switch_to(2)
        self.look.settle()
        self.threads.clear()
        calls = self._switch_to(2)
        self.assertEqual(calls, [1], "和身上这张一样：当场收尾")
        self.assertFalse(self.look._jobs.pending())
        self.assertEqual(self.threads, [], "不重出")

    def test_a_coat_chosen_meanwhile_is_not_overwritten_by_the_late_one(self):
        self._need_coat(2)
        calls = self._switch_to(2)
        self.win.set_coat(1)                                   # 详情页里当场点了第一套
        self.assertEqual(calls, [1], "换同桌那件先收尾（卡片跟上、淡入）")
        self.look.settle()
        self.assertEqual(self.win.coat, 1)
        self.assertIsNone(self.renderer.coat_image, "点的那套留着，没被后到的盖掉")
        self.assertEqual(self.win.prefs.get("coat"), 1)

    def test_the_first_coat_is_uploaded_once_and_not_kept(self):
        self._need_coat(2)
        self._switch_to(2)
        self.look.settle()
        self._switch_to(1)
        self.look.settle()
        self.assertIsNone(self.renderer.coat_image, "第一套还是「模型自带的」：每屏窗口、出图照旧按模型自带的来")
        once = self.renderer._coat_once
        self.assertTrue(once is not None and not once.isNull(), "后台解好的那张交给渲染器")
        self.assertIs(self.renderer._image(), once)
        self.assertIsNone(self.renderer._coat_once, "传完就丢")

    def test_a_custom_coat_is_painted_off_the_main_thread(self):
        painted = []
        real = look_mod.CoatPainter.paint

        def paint(painter, spec, size=2048):
            painted.append((threading.current_thread(), size))
            return real(painter, spec, size)
        with mock.patch.object(look_mod.CoatPainter, "paint", paint):
            calls = self._switch_to(0, '{"pattern": 1, "main": "#5E3B26", "secondary": "#F3EADC"}')
            self.look.settle()
        self.assertEqual(calls, [1])
        self.assertEqual(self.win.coat, 0)
        self.assertEqual([(t is self.main, size) for t, size in painted], [(False, 2048)])
        self.assertEqual(self.renderer.coat_image.size().width(), 2048)
        self.assertEqual(self.win.coat_spec.main, "#5E3B26")

    def test_the_coat_thread_keeps_its_masks_but_not_the_decoded_texture(self):
        """后台线程自己的 CoatPainter：第二次换到自定义毛色的同桌不再现算遮罩（现算要多 100 毫秒、大半拿着 GIL）；解出来的原贴图出完就丢。"""
        from widget import coat as coat_mod
        look_mod._worker_painters.clear()
        self.addCleanup(look_mod._worker_painters.clear)
        real = coat_mod._uv_mask
        with mock.patch.object(coat_mod, "_uv_mask", side_effect=real) as masks:
            self._switch_to(0, '{"pattern": 1, "main": "#5E3B26", "secondary": "#F3EADC"}')
            self.look.settle()
            first = masks.call_count
            self._need_coat(2)
            self._switch_to(2)
            self.look.settle()
            self._switch_to(0, '{"pattern": 1, "main": "#224466", "secondary": "#FFFFFF"}')
            self.look.settle()
        self.assertGreater(first, 0)
        self.assertEqual(masks.call_count, first, "遮罩只算一次")
        painter = look_mod._worker_painters[id(self.model)][1]
        self.assertIsNone(painter.albedos._last, "原贴图没留着")
        self.assertIsNot(painter, self.look._coat_painter, "不和主线程的那份共用")

    def test_another_model_gets_its_own_coat_even_when_both_wear_the_first(self):
        """换模型（look.use_model）：两只都是第 1 套也得重出（不然当成「和身上一样」，新身子一直贴着上一只的贴图），渲染器拿到的是新模型自带的那张；
        四套的深浅两色各是各的、不串，换回来还是原来那份。正画着另一半狗的每块屏的窗口一起带上解好的这张，没在画的不动（等它第一次画时自己解）。"""
        import dataclasses
        from types import SimpleNamespace
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor
        from widget.render import DogRenderer
        win, look = self.win, self.look
        self._switch_to(1)
        look.settle()
        self.assertEqual(look._wearing, ("coat", 1))
        mine = look._coat_dark
        red = QImage(2, 2, QImage.Format_RGBA8888)
        red.fill(QColor("#cc2222"))
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        red.save(buf, "PNG")
        other = dataclasses.replace(self.model, measured={}, texture_png=bytes(data))
        drawing = SimpleNamespace(drawing=True, view=SimpleNamespace(renderer=DogRenderer(other)))
        idle = SimpleNamespace(drawing=False, view=SimpleNamespace(renderer=DogRenderer(other)))
        with mock.patch.dict(win._ghosts, {"a": drawing, "b": idle}, clear=True):
            look.use_model(other)
            self.assertEqual(look._coat_dark, {}, "深浅两色是这个模型自己的那份")
            self.assertIsNot(look._coat_dark, mine)
            calls = self._switch_to(1)
            self.assertEqual(calls, [], "两只都是第 1 套也重出")
            self.assertTrue(win.coat_pending())
            look.settle()
        self.assertEqual(calls, [1])
        once = self.renderer._coat_once
        self.assertEqual((once.width(), once.height()), (2, 2), "新模型自带的那张")
        self.assertIs(drawing.view.renderer._coat_once, once, "正在画的每块屏的窗口：同一张，不在主线程上再解")
        self.assertTrue(drawing.view.renderer._coat_dirty)
        self.assertFalse(idle.view.renderer._coat_dirty, "没在画的不动")
        look.use_model(self.model)
        self.assertIs(look._coat_dark, mine, "换回来：原来那份")

    def test_a_broken_coat_file_falls_back_to_the_first_coat(self):
        self._need_coat(2)
        with mock.patch.object(look_mod, "read_image", return_value=QImage()):
            calls = self._switch_to(2)
            self.look.settle()
        self.assertEqual(calls, [1], "照常收尾：狗要淡回来")
        self.assertEqual((self.win.coat, self.win.prefs.get("coat")), (1, 1))
        self.assertIsNone(self.renderer.coat_image)
