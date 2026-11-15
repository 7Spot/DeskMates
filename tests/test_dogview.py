"""画布（widget/dogview.py）和渲染器里不碰显卡的那部分：点击范围读回哪一块、probe() 怎么答、上面那层什么时候重画、着色器文件读不读得进来、
没有 RHI 时出图返回空、贴纸和头像出图各贴哪套毛色。offscreen 平台没有 RHI，真画出来的样子靠新旧逐像素对比。"""
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage, QShader, QShaderKey, QShaderVersion

from tests.panel_base import QUIET, PanelCase
from widget import dogview, render
from widget.gltf import IDENTITY
from widget.render import Frame, hit_rect

SHADERS = ("dog.vert", "dog.frag", "prop.vert", "prop.frag", "prop_tex.vert", "prop_tex.frag", "quad.vert", "shadow.frag", "composite.frag")


def tiny_model():
    """渲染器只在建的时候看一眼网格：两个顶点就够。"""
    return SimpleNamespace(mesh=SimpleNamespace(positions=[-1, 0, 0, 1, 2, 0], joints=[0, 0, 0, 0] * 2, weights=[1, 0, 0, 0] * 2))


class HitRectTests(unittest.TestCase):
    def test_block_around_the_point_counted_from_the_bottom_edge(self):
        """画布边长是窗口的 2 倍（dpr 1），底边对着窗口底边：窗口里从上往下第 20 行 = 画布上从底往上 (80 − 20) × 2。"""
        self.assertEqual(hit_rect(10, 20, 3, 100, 80, 1.0), (14, 114, 13, 13))
        self.assertEqual(hit_rect(10, 20, 3, 100, 80, 2.0), (28, 228, 25, 25), "2 倍屏：一个逻辑像素在画布上 4 个像素")

    def test_block_is_clipped_to_the_canvas_and_none_outside(self):
        self.assertEqual(hit_rect(0, 80, 3, 100, 80, 1.0), (0, 0, 7, 7), "左下角：只剩画面里的那一块")
        self.assertEqual(hit_rect(100, 0, 3, 100, 80, 1.0), (194, 154, 6, 6), "右上角")
        self.assertIsNone(hit_rect(-50, 20, 3, 100, 80, 1.0))
        self.assertIsNone(hit_rect(10, 200, 3, 100, 80, 1.0))


class ShaderFileTests(unittest.TestCase):
    def test_every_shader_has_a_compiled_file_with_a_metal_version(self):
        """着色器源码改了要跑 tools/build_shaders.sh；.qsb 入 git、进安装包（packaging/Deskmate.spec），少一个真机上就画不出来。"""
        sources = sorted(p.name for p in render.SHADER_DIR.iterdir() if p.suffix in (".vert", ".frag"))
        self.assertEqual(sources, sorted(SHADERS))
        metal = QShaderKey(QShader.MslShader, QShaderVersion(12))
        for name in SHADERS:
            shader = render._shader(name)
            self.assertTrue(shader.isValid(), name)
            self.assertIn(metal, shader.availableShaders(), f"{name}.qsb 里没有 Metal 的那一份")

    def test_packaging_takes_the_compiled_shaders(self):
        import config
        spec = (config.ROOT / "packaging" / "Deskmate.spec").read_text(encoding="utf-8")
        self.assertIn('"widget" / "shaders").glob("*.qsb")', spec)
        self.assertIn('"widget/shaders"', spec)


class DogViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])

    def _view(self, **kw):
        view = dogview.DogView(tiny_model(), **kw)
        self.addCleanup(view.deleteLater)
        return view

    def test_without_rhi_it_is_not_ready_and_answers_nothing(self):
        """offscreen 平台没有 RHI（真机上是还没画过第一帧）：probe 返回 None（调用方当整个窗口都算狗），出图返回空图。"""
        view = self._view()
        frame = Frame(IDENTITY, [IDENTITY], None, 0.0, 1.0, 240.0, 46.0)
        self.assertFalse(view.ready())
        self.assertIsNone(view.probe(10, 10, 3))
        self.assertTrue(view.shoot(frame, 64, 64).isNull())
        room = dogview.Darkroom(tiny_model())
        self.addCleanup(room.deleteLater)
        self.assertTrue(room.shoot(frame, 64, 64).isNull())
        room.close()

    def test_probe_answers_from_the_last_frame_and_asks_for_the_next(self):
        """读回是跟着画的那一帧走的：这一次问的点记下来等下一帧画完读，答的是上一帧读回来的。
        鼠标刚进窗口（还没读回过）、读回来的太旧都算不是狗：不然鼠标划过窗口的空白处「···」会闪一下。"""
        view = self._view()
        view.renderer.rhi = object()                      # 假装画过第一帧了
        self.addCleanup(setattr, view.renderer, "rhi", None)
        self.assertIs(view.probe(10, 20, 3), False, "还没读回过")
        self.assertEqual(view._ask, (10, 20, 3))
        view._ask, view._reading = None, True             # 这一帧画完、读回排上了（render() 做的）
        with mock.patch.object(view.renderer, "hit", return_value=True):
            self.assertIs(view.probe(11, 20, 3), True)
        self.assertEqual(view._ask, (11, 20, 3))
        self.assertIs(view.probe(12, 20, 3), True, "这一帧没读回新的：刚才那个还新鲜，照用")
        view._answer = (True, time.perf_counter() - 2 * dogview.HIT_FRESH_S)
        self.assertIs(view.probe(12, 20, 3), False, "很久以前读的不作数")
        view._reading = True
        with mock.patch.object(view.renderer, "hit", return_value=False):
            self.assertIs(view.probe(12, 20, 3), False)
        view.release()
        self.assertIsNone(view._answer)

    def test_the_layer_above_repaints_only_when_it_has_something(self):
        """「···」那一层是盖在画布上的普通控件：有东西要画才跟着狗每帧重画；东西没了再重画一次把它擦掉，之后不再画。"""
        state = {"on": False}
        drawn = []
        view = self._view(overlay=drawn.append, overlay_needed=lambda: state["on"])
        view.resize(120, 90)
        view.show()                                       # 显示出来才收得到改大小的事件
        self.addCleanup(view.hide)
        cover = view.cover
        self.assertEqual(cover.size(), view.size(), "盖满整块画布")
        with mock.patch.object(cover, "update") as update:
            view.refresh()
            self.assertEqual(update.call_count, 0, "没东西：不重画")
            state["on"] = True
            view.refresh()
            self.assertEqual(update.call_count, 1)
        cover.grab()                                      # 真画一次
        self.assertEqual(len(drawn), 1)
        self.assertTrue(cover.shown)
        state["on"] = False
        with mock.patch.object(cover, "update") as update:
            view.refresh()
            self.assertEqual(update.call_count, 1, "上一帧画着东西：再画一次擦掉")
        cover.grab()
        self.assertEqual(len(drawn), 1, "没东西要画时不调画的函数")
        self.assertFalse(cover.shown)
        with mock.patch.object(cover, "update") as update:
            view.refresh()
            self.assertEqual(update.call_count, 0)
        self.assertIsNone(self._view().cover, "每块屏的窗口不叠「···」：没有这一层")


class ShotCoatTests(PanelCase):
    """贴纸、头像借画布离屏出图（look.py → dogview.shoot）：每张贴哪套毛色、出完放掉出图那一套。"""

    def _fake_view(self):
        view = self.win.view
        shots = []

        def shoot(frame, width, height, dpr=1.0, coat=None):
            shots.append((width, height, coat))
            img = QImage(4, 4, QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            return img
        for name, fake in (("ready", lambda: True), ("shoot", shoot), ("shoot_done", mock.Mock())):
            patch = mock.patch.object(view, name, fake)
            patch.start()
            self.addCleanup(patch.stop)
        return view, shots

    def test_nothing_is_drawn_before_the_canvas_is_ready(self):
        look = self.win.look
        self.assertEqual(look.coat_thumbnails(64, 64), {})
        self.assertEqual(look.pet_shots([("a", None, False)], 64, 100.0, 4.0), {})

    def test_head_shots_use_each_coat_and_release_the_shooter(self):
        view, shots = self._fake_view()
        look = self.win.look
        got = look.coat_thumbnails(88, 66)
        have = [i for i, ok in enumerate(look.coat_available(), start=1) if ok]
        self.assertEqual(sorted(got), have)
        self.assertEqual([(w, h) for w, h, _ in shots], [(88, 66)] * len(have))
        self.assertIsNone(shots[0][2], "第一套 = 模型自带的贴图")
        for _, _, coat in shots[1:]:
            self.assertFalse(coat.isNull())
        view.shoot_done.assert_called_once_with()

    def test_pet_shots_wear_what_the_dog_wears_unless_told(self):
        view, shots = self._fake_view()
        look = self.win.look
        wearing = QImage(2, 2, QImage.Format_RGBA8888)
        view.renderer.set_coat(wearing)
        other = QImage(2, 2, QImage.Format_RGBA8888)
        with mock.patch.object(look, "_coat_for", return_value=other) as coat_for:
            got = look.pet_shots([("now", None, False), ("other", (3, ""), True), ("again", None, True)], 64, 100.0, 4.0)
        self.assertEqual(list(got), ["now", "other", "again"])
        coat_for.assert_called_once_with(3, "")
        self.assertIs(shots[0][2], wearing, "现在这只：身上这套")
        self.assertIs(shots[1][2], other)
        self.assertIs(shots[2][2], wearing, "别的那只画完，再画现在这只还是身上这套")
        self.assertIs(view.renderer.coat_image, wearing, "窗口里那只的贴图没被动过")
        view.shoot_done.assert_called_once_with()

    def test_failed_shots_are_left_out(self):
        view, _ = self._fake_view()
        with mock.patch.object(view, "shoot", return_value=QImage()):
            self.assertEqual(self.win.look.pet_shots([("a", None, False)], 64, 100.0, 4.0), {})
        view.shoot_done.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
