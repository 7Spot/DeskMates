"""加宽不缩回：灵动交互开着时主窗口铺满狗那块屏的宽、和拎着一样高，之后只长不缩、在这块屏上不挪；
狗跑、被拖、被扔都只改画在窗口里哪。还有大小的上限跟着屏走（window.scale_range）、特别大的狗画布按 1.5 倍画（render.supersample）。
两块假屏（左 1000 × 900、右 2000 × 900），每块屏的窗口换成假的；QSettings 换成假的不碰真设置；offscreen 平台不开真窗口。"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import config
from tests.test_window import QUIET, FakeSettings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class WideWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        from widget import gltf
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.model = gltf.load(config.MODEL_PATH)

    def setUp(self):
        from types import SimpleNamespace
        from PySide6.QtCore import QRect
        import widget.window as window

        class Screen:
            def __init__(self, x, y, w, h, name):
                self.g = QRect(x, y, w, h)
                self.n = name

            def geometry(self):
                return self.g

            availableGeometry = geometry

            def name(self):
                return self.n

        self.left, self.right = Screen(-1000, 0, 1000, 900, "left"), Screen(0, 0, 2000, 900, "right")
        screens = [self.left, self.right]
        real = window.QApplication

        def screen_at(p):
            return next((s for s in screens if s.g.contains(p)), None)
        fake = SimpleNamespace(screens=lambda: screens, screenAt=screen_at, primaryScreen=lambda: self.right, instance=real.instance)

        def settings(*args):
            f = FakeSettings()
            f.values["dynamic"] = False
            return f
        with mock.patch.object(window, "QSettings", settings):
            self.win = window.CompanionWindow(self.model)
        self.win._anim_timer.stop()
        p = mock.patch.object(window, "QApplication", fake)
        p.start()
        self.addCleanup(p.stop)
        self.ghosts = {}

        def make_ghost(model, owner, home):
            ghost = mock.Mock()
            ghost.home, ghost.drawing, ghost.pressed = home, False, False
            ghost.isVisible.return_value = True
            ghost.sync.side_effect = lambda *a: setattr(ghost, "drawing", True)
            ghost.clear.side_effect = lambda: setattr(ghost, "drawing", False)
            self.ghosts[home.n] = ghost
            return ghost
        g = mock.patch.object(window, "GhostWindow", make_ghost)
        g.start()
        self.addCleanup(g.stop)
        w = self.win
        w.dog.update(1 / 60)
        w._pose = w.dog.frame()
        w._scene_screen = self.right
        w.isVisible = lambda: True
        self.addCleanup(w.hide)
        w.place_scene(1000.0, 800.0)
        w.dynamic = True                                           # 只开窗口这一半：灵动交互的空间不起（playground 不 start）

    def widen(self):
        """铺宽，分两步的第二步也走完。"""
        import time
        w = self.win
        w._enter_wide()
        w._step_reshape(time.perf_counter() + 10.0)
        return w.geometry()

    def calls(self):
        p = mock.patch.object(self.win, "setGeometry", wraps=self.win.setGeometry)
        c = p.start()
        self.addCleanup(p.stop)
        return c

    def test_the_wide_window_fills_the_dogs_screen_and_keeps_the_dog_where_it_was(self):
        w = self.win
        before = w.scene_world()
        calls = self.calls()
        geo = self.widen()
        self.assertEqual((geo.left(), geo.width()), (0, 2000), "铺满狗那块屏的宽（不骑到左边那块）")
        self.assertEqual(geo.height(), min(round(config.WINDOW_MAX_HEIGHT * w.scale), 900), "和拎着、飞着一样高")
        self.assertLessEqual(geo.y() + geo.height(), 900)
        self.assertEqual(calls.call_count, 2, "看得见时四条边都动：分两步")
        self.assertLess(abs(w.scene_world()[0] - before[0]) + abs(w.scene_world()[1] - before[1]), 0.05, "狗没动")

    def test_two_steps_each_keep_a_corner_still(self):
        """四条边都要动时分两步：第一步只动右边和上边（左下角不动），第二步只动左边和下边（右上角不动）——每一步旧画面都钉在不动的那个角。"""
        w = self.win
        g0 = w.geometry()
        calls = self.calls()
        self.widen()
        a, b = calls.call_args_list[0][0][0], calls.call_args_list[1][0][0]
        self.assertEqual((a.left(), a.bottom()), (g0.left(), g0.bottom()), "第一步：左下角不动")
        self.assertEqual((b.right(), b.top()), (a.right(), a.top()), "第二步：右上角不动")
        pins = []
        with mock.patch.object(w, "_pin_corner", side_effect=lambda left, bottom: pins.append((left, bottom))):
            w._leave_wide()
            import time
            w._step_reshape(time.perf_counter() + 10.0)
        self.assertEqual(pins, [(True, True), (False, True)], "缩回去也一样：先动右边、上边（钉左下），再只动左边（钉右下）")

    def test_running_and_dragging_inside_the_wide_window_never_moves_it(self):
        from PySide6.QtCore import QPoint
        w = self.win
        geo = self.widen()
        calls = self.calls()
        w._drag = QPoint(0, 0)                                     # 拖着、跑着都是 place_scene
        for x in [300.0 + 30.0 * i for i in range(50)] + [1700.0 - 40.0 * i for i in range(35)]:
            w.place_scene(x, 800.0 - (x % 60.0))
            self.assertAlmostEqual(w.scene_world()[0], x, delta=0.01)
            self.assertAlmostEqual(w.scene_world()[1], 800.0 - (x % 60.0), delta=0.01)
        w._drag = None
        self.assertEqual(calls.call_count, 0, "窗口一下都不挪")
        self.assertEqual(w.geometry(), geo)

    def test_jumping_above_the_window_grows_it_upward_once_and_never_shrinks(self):
        w = self.win
        geo = self.widen()
        calls = self.calls()
        pins = []
        real_pin = w._pin_corner
        w._pin_corner = lambda left, bottom: (pins.append((left, bottom)), real_pin(left, bottom))
        top = geo.top()
        w.place_scene(900.0, top + 60.0)                           # 站到很高的窗口上：头顶和「···」出了窗口
        self.assertEqual(calls.call_count, 1, "长一次")
        g = w.geometry()
        self.assertEqual((g.left(), g.width(), g.bottom()), (geo.left(), geo.width(), geo.bottom()), "只往上长，左右、底边不动")
        self.assertEqual(g.top(), 0, "一直长到屏幕最上沿（以后再跳也不用再长）")
        self.assertEqual(pins[-1], (True, True), "钉在不动的左下角")
        w.place_scene(900.0, 800.0)                                # 跳回地上：不缩
        w._keep_held_fit()
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(w.geometry(), g, "只长不缩")

    def test_the_ghost_windows_keep_the_dogs_own_width(self):
        """每块屏的窗口按平时贴着狗的宽建、摆（照主窗口的宽，主窗口宽着时会比左边那块屏还宽、骑在两块屏上）。"""
        w = self.win
        self.widen()
        w.place_scene(30.0, 800.0)
        w._sync_ghost()
        ghost = self.ghosts["left"]
        create = ghost.setGeometry.call_args[0][0]
        self.assertEqual(create.width(), w._window_size(w.scale)[0])
        rect, frame, _ = ghost.sync.call_args[0]
        self.assertEqual(rect.width(), w._window_size(w.scale)[0], "跟着狗摆的时候也是狗的宽")
        self.assertTrue(self.left.g.contains(rect))
        self.assertAlmostEqual(rect.x() + rect.width() / 2.0 + frame.offset[0], 30.0, delta=0.01, msg="两边按同一个根画")

    def test_the_card_and_the_saved_position_follow_the_dog_not_the_window(self):
        w = self.win
        self.widen()
        w.place_scene(1500.0, 800.0)
        r = w.dog_rect()
        self.assertAlmostEqual(r.center().x(), 1500.0, delta=1.0, msg="卡片按狗摆（Card.place_near）")
        self.assertEqual(r.width(), round(config.WINDOW_WIDTH * w.world_scale))
        self.assertEqual(r.bottom() + 1, round(800.0 + config.GROUND_Y * w.world_scale), "底边在脚下留影子的那条")
        self.assertLess(r.height(), w.height(), "不是宽着的窗口那么高")
        w._save_pos()
        self.assertAlmostEqual(w.prefs.get("pos_fx"), 1500.0 / 2000.0, places=4, msg="记的是狗在屏上哪")
        self.assertAlmostEqual(w.prefs.get("pos_fb"), (800.0 + config.GROUND_Y * w.world_scale) / 900.0, places=4)
        self.assertEqual(w.prefs.get("pos_screen"), "right")

    def test_only_the_part_around_the_dog_is_drawn(self):
        """宽着只画贴着狗的那一块（render.Frame.region，平时那个窗口那么大）：离屏画布、显卡每帧画的不跟着窗口变大；那一块里狗的根和窗口里的是同一个点，
        读回像素（点击范围）也按那一块算。"""
        from widget.render import hit_rect, supersample
        w = self.win
        self.widen()
        w.place_scene(1500.25, 800.5)
        w._refresh_frame()
        f = w.view.frame
        self.assertIsNotNone(f.region)
        rx, rb, rw, rh = f.region
        self.assertLessEqual(abs(rw - w._window_size(w.scale)[0]), 1)
        self.assertLess(rw * rh * 4, w.width() * w.height(), "比整个窗口小得多")
        root_x, root_b = rx + rw / 2.0 + f.offset[0], rb + f.ground_px - f.offset[1]
        self.assertAlmostEqual(w.x() + root_x, 1500.25, delta=0.01)
        self.assertAlmostEqual(w.y() + w.height() - root_b, 800.5, delta=0.01)
        x, y = 1500.25 - w.x(), 800.5 - 60 - w.y()
        w.view.resize(w.size())                                     # 没显示出来时布局还没把画布撑满窗口
        self.assertEqual(w.view._hit_rect((x, y, 3)), hit_rect(x - rx, y - (w.height() - rb - rh), 3, rw, rh, w.view.devicePixelRatioF(),
                                                               supersample(f.ppm)))
        w.dynamic = False
        w._leave_wide()
        w._refresh_frame()
        self.assertIsNone(w.view.frame.region, "平时整个窗口就是贴着狗的那一块")

    def test_once_still_for_a_while_it_goes_back_to_the_normal_window_and_moving_widens_it_again(self):
        """狗停够 WIDE_REST_S 回到平时贴着狗的大小（一直宽着时悬停卡得多）；有人按着、放大着不缩；一动起来又铺宽。"""
        import time
        import widget.window as window
        w = self.win
        self.widen()
        w.place_scene(1500.0, 800.0)
        t = time.perf_counter()
        w._drag = object()
        w._rest_wide(t)
        w._rest_wide(t + window.WIDE_REST_S + 1.0)
        self.assertTrue(w._wide, "按着狗：不缩")
        w._drag = None
        w._rest_wide(t + 2.0)
        w._rest_wide(t + 2.0 + window.WIDE_REST_S - 0.1)
        self.assertTrue(w._wide, "还没停够")
        w._rest_wide(t + 2.0 + window.WIDE_REST_S + 0.1)
        w._step_reshape(t + 20.0)
        self.assertFalse(w._wide)
        g = w.geometry()
        self.assertEqual(g.width(), w._window_size(w.scale)[0], "回到贴着狗的宽")
        self.assertAlmostEqual(w.scene_world()[0], 1500.0, delta=0.6, msg="狗没动")
        with mock.patch.object(w, "_wants_wide", lambda: True):
            w.place_scene(1520.0, 800.0)                           # 跑起来了
        self.assertTrue(w._wide)
        self.assertAlmostEqual(w.scene_world()[0], 1520.0, delta=0.6)

    def test_turning_dynamic_off_brings_back_the_normal_window_around_the_dog(self):
        import time
        w = self.win
        self.widen()
        w.place_scene(1500.0, 800.0)
        w.dynamic = False
        w._leave_wide()
        w._step_reshape(time.perf_counter() + 10.0)
        g = w.geometry()
        self.assertFalse(w._wide)
        self.assertEqual(g.width(), w._window_size(w.scale)[0])
        self.assertAlmostEqual(g.x() + g.width() / 2.0, w.scene_world()[0], delta=0.6, msg="又贴着狗")
        self.assertAlmostEqual(w.scene_world()[0], 1500.0, delta=0.6)

    def test_changing_the_size_while_wide_moves_no_window_and_keeps_the_dog_center(self):
        w = self.win
        geo = self.widen()
        calls = self.calls()
        w.begin_scale_adjustment()
        cx = w._anchor[0]
        for k in (1.05, 1.1, 1.05, 1.0, 0.9, 0.8):
            w.set_scale(k)
            self.assertAlmostEqual(w._dog_center()[0], cx, delta=0.6, msg="狗的中心不动")
        w.end_scale_adjustment()
        self.assertTrue(w._wide)
        self.assertEqual(w.geometry().width(), geo.width())
        self.assertLessEqual(calls.call_count, 1, "宽着改大小只在比窗口高了时往上长一次")


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class ScaleRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        from widget import gltf
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.model = gltf.load(config.MODEL_PATH)

    def setUp(self):
        import widget.window as window

        def settings(*args):
            f = FakeSettings()
            f.values["dynamic"] = False
            return f
        with mock.patch.object(window, "QSettings", settings):
            self.win = window.CompanionWindow(self.model)
        self.win._anim_timer.stop()
        self.addCleanup(self.win.hide)

    def screen(self, h):
        from types import SimpleNamespace
        from PySide6.QtCore import QRect
        return SimpleNamespace(geometry=lambda: QRect(0, 0, 3440, h))

    def test_the_top_follows_the_screen_height_and_never_drops_below_400(self):
        from widget.clips import POSTURE_PLANS
        w = self.win
        stand = max(w.dog.clip_top(c) for c in POSTURE_PLANS["standing"].loop)
        lo, hi = w.scale_range(self.screen(1440))
        self.assertEqual(lo, 30)
        self.assertAlmostEqual(hi / 100.0 * stand * config.PIXELS_PER_METER / 1440, 2 / 3, delta=0.02, msg="狗站着约占屏高三分之二")
        self.assertGreater(hi, 400, "带鱼屏：上限超过 400%")
        self.assertGreater(w.scale_range(self.screen(2160))[1], 700, "4K 电视按 1 倍用")
        self.assertEqual(w.scale_range(self.screen(982))[1], 400, "MacBook：不低于 400%")
        self.assertEqual(hi % 10, 0, "取到 10%")

    def test_set_scale_and_the_pinch_stay_inside_the_range_without_shrinking_a_big_dog(self):
        w = self.win
        w.isVisible = lambda: True
        with mock.patch.object(w, "scale_range", lambda screen=None: (30, 500)):
            w.set_scale(9.0)
            self.assertAlmostEqual(w.world_scale, 5.0)
            w.set_scale(0.1)
            self.assertAlmostEqual(w.world_scale, 0.3)
            w.set_scale(5.0)
        with mock.patch.object(w, "scale_range", lambda screen=None: (30, 400)):    # 挪到了小屏上：已经比上限大
            w.zoom(1.1)
            self.assertAlmostEqual(w.world_scale, 5.0, msg="往大调不动，也不会一下缩到 400%")
            w.zoom(1 / 1.1)
            self.assertAlmostEqual(w.world_scale, 5.0 / 1.1, places=4, msg="往小调照常")

    def test_before_showing_the_saved_size_is_clamped_to_the_biggest_screen(self):
        """启动时第一次定大小（还没显示）：按最大的那块屏的上限，电视上调的大小不被笔记本的上限截掉。"""
        w = self.win
        screens = [self.screen(982), self.screen(2160)]
        import widget.window as window
        from types import SimpleNamespace
        fake = SimpleNamespace(screens=lambda: screens, screenAt=lambda p: None, primaryScreen=lambda: screens[0], instance=window.QApplication.instance)
        with mock.patch.object(window, "QApplication", fake):
            lo, hi = w._scale_limits()
        self.assertEqual(lo, 0.3)
        self.assertGreater(hi, 7.0)


class SupersampleTests(unittest.TestCase):
    def test_up_to_four_times_the_canvas_is_twice_as_big_and_beyond_that_one_and_a_half(self):
        from widget.render import supersample, hit_rect
        self.assertEqual(supersample(config.PIXELS_PER_METER * 1.0), 2)
        self.assertEqual(supersample(config.PIXELS_PER_METER * 4.0), 2, "4 倍以内样子不变")
        self.assertEqual(supersample(config.PIXELS_PER_METER * 4.01), 1.5)
        self.assertEqual(hit_rect(10, 20, 3, 100, 80, 1.0, 1.5), (10, 85, 10, 10), "读回像素的那一块按同一个倍数算")


if __name__ == "__main__":
    unittest.main()
