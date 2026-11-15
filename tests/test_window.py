"""窗口缩放的几何。需要 PySide6 和模型文件；用 offscreen 平台不开真窗口，QSettings 换成假的不碰真设置。"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import config

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# offscreen 平台没有 RHI（画不了 QRhiWidget）、不支持 raise()，Qt 每次都警告；这里不需要，过滤掉
QUIET = ("QRhiWidget", "This plugin does not support")


class FakeSettings:
    def __init__(self, *args):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class ZoomGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication

        from widget import gltf
        # offscreen 平台画不了狗的画布，Qt 每建一个窗口就警告一次；这里不需要画，过滤掉
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.model = gltf.load(config.MODEL_PATH)

    def _window(self):
        import widget.window as window

        def settings(*args):
            fake = FakeSettings()
            fake.values["dynamic"] = False                    # 这些用例按"狗自己待着、趴着"写的（灵动交互新装默认开）
            return fake
        with mock.patch.object(window, "QSettings", settings):
            win = window.CompanionWindow(self.model)
        win.keep_scene_inside = lambda x, y: (x, y)          # 这些用例量缩放的固定点；单测的屏幕只有 800 宽，放大了就顶到边。边界单独测（KeepBodyOnScreenTests）
        return win

    @staticmethod
    def _center(win):
        """缩放的固定点：狗的中心（窗口中心的话，站着时窗口给「···」长高一截，中心跟着偏，拖滑块时狗一路往上跑）。"""
        return win._dog_center()[:2]

    def _assert_same_center(self, a, b):
        for p, q in zip(a, b):
            self.assertAlmostEqual(p, q, delta=0.5)   # 取整最多差半个像素

    def test_first_zoom_after_launch_keeps_the_window_where_app_put_it(self):
        win = self._window()
        win.move(1000, 100)          # app.py 启动后把窗口放到屏幕右上角，之后用户第一次按 +
        before = self._center(win)
        win.zoom(1.15)
        self._assert_same_center(self._center(win), before)
        self.assertEqual(win.width(), round(config.WINDOW_WIDTH * 1.15))

    def test_zoom_after_a_move_centers_on_the_new_position(self):
        win = self._window()
        win.zoom(1.25)
        win.move(300, 300)           # 拖动
        before = self._center(win)
        win.zoom(0.8)
        self._assert_same_center(self._center(win), before)

    def test_dragging_the_size_slider_keeps_the_dog_center_while_the_window_grows(self):
        """站着、坐着时拖大小滑块，小组件一直往上跑。那时窗口给狗头顶的「···」往上多长了一截（_fit_height，底边不动），
        下一格缩放从长高的窗口重新量中心，中心每格往上偏几像素。现在固定点是狗的中心，窗口自己长高不作废它。"""
        win = self._window()
        win.move(640, 400)
        before = self._center(win)
        for _ in range(30):
            win.set_scale(win.scale + 0.01)              # 拖滑块：一格 1%
            win._set_height(win.height() + 6)            # 这一帧窗口给「···」往上长了一截
            self._assert_same_center(self._center(win), before)

    def test_repeated_zoom_in_and_out_does_not_drift(self):
        win = self._window()
        win.move(640, 400)
        win._fit_height(now=0.0)                         # 第一帧：窗口长到要的高度（给最高的姿势和「···」留够，趴着也留站着、坐着的）
        start = win.pos()
        for _ in range(6):
            win.zoom(1.15)
        for _ in range(6):
            win.zoom(1 / 1.15)
        self.assertEqual(win.pos(), start)

    @staticmethod
    def _screen_point(win, point):
        from widget.geometry import project
        from widget.render import ELEVATION
        x, bottom = project(point, win.ppm, win.ground_px, ELEVATION, win.width(), win.draw_offset)
        return win.x() + x, win.y() + win.height() - bottom

    def test_fractional_zoom_keeps_the_rendered_pivot_without_pixel_jitter(self):
        """测实际投影而不是取整后的窗口：任意模型点必须严格围绕同一支点缩放，阴影使用同一残差。"""
        from widget.geometry import shadow_ellipse
        from widget.render import ELEVATION
        win = self._window()
        win.move(503, 317)
        win.begin_scale_adjustment()
        anchor = win._anchor[:2]
        point = (0.31, 0.27, -0.11)
        before = self._screen_point(win, point)
        old_scale = win.scale
        for k in (1.003, 1.0175, 0.731, 2.1234, 0.3, 4.0, 1.0):
            win.set_scale(k)
            actual = self._screen_point(win, point)
            for axis in range(2):
                self.assertAlmostEqual(actual[axis], anchor[axis] + (before[axis] - anchor[axis]) * k / old_scale, places=8)
            for actual_center, fixed in zip(win._dog_center()[:2], anchor):
                self.assertAlmostEqual(actual_center, fixed, places=8)
            frame = win.view.frame
            self.assertEqual(frame.offset, win.draw_offset)
            shadow = shadow_ellipse(win._pose.footprint, win._pose.lift, win.ppm, win.ground_px,
                                    ELEVATION, win.width(), win.draw_offset)
            self.assertEqual(frame.shadow, shadow)

    def test_scale_gesture_locks_pivot_and_release_does_not_move_the_scene(self):
        win = self._window()
        win.move(503, 317)
        win.begin_scale_adjustment()
        anchor = win._anchor
        point = (0.1, 0.3, 0.2)
        before = self._screen_point(win, point)
        with mock.patch.object(win.dog, "rest_top", return_value=win.dog.rest_top() * 1.5):
            win.begin_scale_adjustment()                  # 面板重复收到 begin 不能换支点
            win.set_scale(1.1837)
            self.assertEqual(win._anchor, anchor, "姿势改变也不打断这次拖动的固定点")
            expected = tuple(anchor[i] + (before[i] - anchor[i]) * 1.1837 for i in range(2))
            for actual, want in zip(self._screen_point(win, point), expected):
                self.assertAlmostEqual(actual, want, places=8)
            at_release = self._screen_point(win, point)
            geometry, offset = win.geometry(), win.draw_offset
            win.end_scale_adjustment()
            win.end_scale_adjustment()
            self.assertEqual(win.geometry(), geometry)
            self.assertEqual(win.draw_offset, offset)
            win.set_scale(win.scale)                      # 新姿势下开始下一次调节，仍不能跳
            for actual, want in zip(self._screen_point(win, point), at_release):
                self.assertAlmostEqual(actual, want, places=8)

    def test_scale_commits_ready_frame_and_full_height_once(self):
        """画布一改大小就会当场画一帧；进入窗口几何提交前，Frame 必须已有新缩放和新宽度的阴影。"""
        from widget.geometry import shadow_ellipse
        from widget.render import ELEVATION
        win = self._window()
        win.move(400, 300)
        win.dog.required = 1.1
        win.begin_scale_adjustment()
        committed = []
        original = win.setGeometry

        def commit(rect):
            frame = win.view.frame
            self.assertEqual(frame.ppm, config.PIXELS_PER_METER * 1.237)
            self.assertEqual(frame.ground_px, config.GROUND_Y * 1.237)
            self.assertEqual(frame.offset, win.draw_offset)
            self.assertEqual(frame.shadow, shadow_ellipse(win._pose.footprint, win._pose.lift, frame.ppm,
                                                        frame.ground_px, ELEVATION, rect.width(), frame.offset))
            committed.append(rect.height())
            original(rect)

        with mock.patch.object(win, "setGeometry", side_effect=commit):
            win.set_scale(1.237)
            win._fit_height(now=1.0, dt=1 / 60)
        self.assertEqual(committed, [win._height_needed()], "一次就留足高度，下一帧不再把基础窗口拉高")
        self.assertGreater(committed[0], round(config.WINDOW_HEIGHT * win.scale))

    def test_container_height_changes_do_not_change_rendered_points(self):
        win = self._window()
        win.move(500, 400)
        win.set_scale(1.137)
        before = self._screen_point(win, (0.17, 0.4, -0.1))
        win._set_height(win.height() + 27)
        after = self._screen_point(win, (0.17, 0.4, -0.1))
        for actual, want in zip(after, before):
            self.assertAlmostEqual(actual, want, places=8)
        self.assertEqual(win.view.frame.offset, win.draw_offset)

    def test_gesture_samples_the_mesh_center_once_and_locks_both_axes(self):
        win = self._window()
        win.move(503, 317)
        renderer = win.view.renderer
        with mock.patch.object(renderer, "visual_center", wraps=renderer.visual_center) as center:
            win.begin_scale_adjustment()
            anchor = win._anchor
            self.assertNotEqual(anchor[2], 0.0, "实际模型不是以窗口横向中线为包围框中心")
            for k in (0.71, 1.133, 2.0, 1.0):
                win.begin_scale_adjustment()
                win.set_scale(k)
                actual = (win.x() + win.scene_x + anchor[2] * win.ppm,
                          win.y() + win.scene_ground - anchor[3] * win.ppm)
                for point, fixed in zip(actual, anchor[:2]):
                    self.assertAlmostEqual(point, fixed, places=8)
            win.end_scale_adjustment()
            self.assertEqual(center.call_count, 1, "拖动、缩放和结束均不能再次扫描网格")
            win.begin_scale_adjustment()
            self.assertEqual(center.call_count, 2, "下一次手势才取那一刻的新姿态中心")

    def test_center_falls_back_without_a_frame_then_uses_the_mesh(self):
        win = self._window()
        win.view.frame = None
        win.begin_scale_adjustment()
        self.assertEqual(win._anchor[2:], (0.0, win.dog.rest_top() / 2))
        win.set_scale(0.8317)                  # 更新几何后会准备 Frame，但这次手势继续使用原来的支点
        self.assertFalse(win._anchor_frame_ready)
        win.end_scale_adjustment()
        renderer = win.view.renderer
        with mock.patch.object(renderer, "visual_center", wraps=renderer.visual_center) as center:
            win.set_scale(win.scale)
            self.assertEqual(center.call_count, 1)
        self.assertTrue(win._anchor_frame_ready)

    def test_animation_follows_the_screen_refresh_rate(self):
        """固定 17 毫秒一帧在 85 赫兹的宽屏上一帧停一次刷新、一帧停两次，快速转头时一跛一跛。
        现在节拍跟窗口所在屏幕的刷新率：计时器只能按整毫秒，就按理想时刻一格格排，平均正好跟上；屏幕改了刷新率重新算。"""
        import widget.window as window
        from PySide6.QtCore import Qt
        win = self._window()
        win._anim_timer.stop()
        self.assertAlmostEqual(win._frame_period, 1 / 60, msg="离屏的屏幕 60 赫兹 → 60 帧")
        self.assertTrue(win._anim_timer.isSingleShot())
        self.assertEqual(win._anim_timer.timerType(), Qt.PreciseTimer)
        screen = mock.MagicMock()
        screen.refreshRate.return_value = 85.0
        with mock.patch.object(win, "screen", return_value=screen):
            win._sync_frame_rate()                       # 挪到 85 赫兹的宽屏上停稳了
        self.assertAlmostEqual(win._frame_period, 1 / 85)
        screen.refreshRateChanged.connect.assert_called_once()
        clock = [100.0]
        delays = []
        with mock.patch.object(window.time, "perf_counter", lambda: clock[0]):
            win._next_frame = win._last_tick = clock[0]
            for _ in range(85):                          # 计时器准时触发：一秒 85 帧
                win._frame()
                delays.append(win._anim_timer.interval())
                clock[0] += delays[-1] / 1000
        win._anim_timer.stop()
        self.assertEqual(set(delays), {11, 12}, "交替 11 / 12 毫秒")
        self.assertAlmostEqual(sum(delays), 1000, delta=1, msg="平均正好是 85 帧")



@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class KeepBodyOnScreenTests(unittest.TestCase):
    """灵动交互关着时，狗的身子不能出屏幕边界。"""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        from widget import gltf
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.model = gltf.load(config.MODEL_PATH)

    def _window(self, dynamic=False):
        import widget.window as window

        def settings(*args):
            fake = FakeSettings()
            fake.values["dynamic"] = dynamic
            return fake
        with mock.patch.object(window, "QSettings", settings):
            win = window.CompanionWindow(self.model)
        win._anim_timer.stop()
        self.addCleanup(win.hide)
        return win

    def _resting(self, win):
        """狗什么都没在做、鼠标离得远、窗口没在变：只剩待机动作。"""
        import widget.window as window
        from PySide6.QtCore import QPoint
        p = mock.patch.object(window.QCursor, "pos", return_value=QPoint(-5000, -5000))
        p.start()
        self.addCleanup(p.stop)
        dog = win.dog
        dog.steps, dog.turn, dog.jump, dog.manual, dog.run, dog.transition, dog.queue = [], None, None, None, None, False, []
        win.power_saving = True                          # 少画帧、收窗口都只在省电模式里
        win._lively()                                    # 记下窗口现在在哪、多大

    def test_resting_draws_fewer_frames_and_anything_happening_brings_them_all_back(self):
        """待着不动也按满帧画，白占显卡和 CPU。没动静 IDLE_AFTER_S 以后每 idle_skip 帧画一帧
        （85 赫兹上每 3 帧：每秒干的活少六成）；再少也不低于 24 帧；有动静马上回满帧。"""
        import time
        import widget.window as window
        from PySide6.QtCore import QPoint
        win = self._window()
        self._resting(win)
        self.assertFalse(win._lively())
        now = time.perf_counter()
        win._lively_at = now
        win._pace(now)
        self.assertAlmostEqual(win._pace_period, win._frame_period, msg="刚有过动静：满帧")
        later = now + window.IDLE_AFTER_S + 0.1
        win._pace(later)
        self.assertAlmostEqual(win._pace_period, 2 / 60, msg="60 帧的屏：每 3 帧就低于 24 帧了，只隔一帧画")
        win._frame_period = 1 / 85
        win._pace(later)
        self.assertAlmostEqual(win._pace_period, 3 / 85, msg="85 赫兹：每 3 帧画一帧")
        win.tuning.set("idle_skip", 2)
        win._pace(later)
        self.assertAlmostEqual(win._pace_period, 2 / 85)
        win.tuning.set("idle_skip", 1)
        win._pace(later)
        self.assertAlmostEqual(win._pace_period, 1 / 85, msg="调成 1 就是不少画")
        win.tuning.set("idle_skip", 3)
        win._pace(later)
        win._drag = QPoint(0, 0)                         # 按在狗身上
        win._pace(later + 0.01)
        self.assertAlmostEqual(win._pace_period, 1 / 85, msg="有动静马上回满帧")
        win._drag = None
        win._pace(later + 0.02)
        self.assertAlmostEqual(win._pace_period, 1 / 85, msg="刚松手：还要再安静一会儿才降")
        win.set_power_saving(False)                      # 28 帧看着卡，默认不降帧率
        win._lively_at = now
        win._pace(later + 5.0)
        self.assertAlmostEqual(win._pace_period, 1 / 85, msg="省电模式关着（默认）：待多久都是满帧")
        self.assertFalse(win.prefs.get("power_saving"))

    def test_what_counts_as_something_happening(self):
        import widget.window as window
        from PySide6.QtCore import QPoint
        from widget.play import ACTIONS_BY_ID, ActionRun
        win = self._window()
        self._resting(win)
        dog = win.dog
        dog.run, dog.transition = ActionRun(ACTIONS_BY_ID["bow"], [], False, 0.0), True
        self.assertFalse(win._lively(), "狗自己随机做的动作（伸懒腰、嗅地）也算待着")
        dog.run = None
        self.assertTrue(win._lively(), "换姿势的过渡片段算有动静")
        dog.transition = False
        dog.turn = object()
        self.assertTrue(win._lively(), "转身")
        dog.turn = None
        dog.manual = object()
        self.assertTrue(win._lively(), "表盘点的动作")
        dog.manual = None
        self.assertFalse(win._lively())
        win._frame_clients.add(object())
        self.assertTrue(win._lively(), "卡片在动")
        win._frame_clients.clear()
        near = win.geometry().topLeft() - QPoint(window.IDLE_NEAR_PX - 10, 0)
        with mock.patch.object(window.QCursor, "pos", return_value=near):
            self.assertTrue(win._lively(), "鼠标在狗旁边：点击范围每帧才切一次，要跟得上")
        win.move(win.x() + 5, win.y())
        self.assertTrue(win._lively(), "窗口挪了")
        self.assertFalse(win._lively())

    def test_wake_draws_the_next_frame_right_away(self):
        import time
        import widget.window as window
        win = self._window()
        self._resting(win)
        now = time.perf_counter()
        win._lively_at = now - 10.0
        win._pace(now)
        self.assertGreater(win._pace_period, win._frame_period)
        win._next_frame = now + win._pace_period
        win._anim_timer.start(1000)
        card = object()
        win.request_frames(card)                         # 卡片要动了
        self.assertAlmostEqual(win._pace_period, win._frame_period)
        self.assertLessEqual(win._anim_timer.remainingTime(), 1, "不等降档的那一格")
        win._anim_timer.stop()
        win.release_frames(card)

    def _assert_inside(self, win, x, y):
        from PySide6.QtWidgets import QApplication
        from widget.window import BODY_HALF_M
        g = QApplication.primaryScreen().geometry()
        half = BODY_HALF_M * win.ppm
        self.assertGreaterEqual(x - half, g.left() - 0.5)
        self.assertLessEqual(x + half, g.left() + g.width() + 0.5)
        self.assertGreaterEqual(y - win.dog.rest_top() * win.ppm, g.top() - 0.5)
        self.assertLessEqual(y, g.top() + g.height() + 0.5)

    def test_dragging_cannot_take_the_body_off_any_edge(self):
        win = self._window()
        for x, y in ((-500.0, 400.0), (5000.0, 400.0), (400.0, -500.0), (400.0, 5000.0), (-500.0, 5000.0)):
            self._assert_inside(win, *win._dragged_to(x, y))

    def test_with_dynamic_on_dragging_keeps_the_old_rules(self):
        win = self._window(dynamic=True)
        x, _ = win._dragged_to(-500.0, 400.0)
        self.assertEqual(x, -500.0, "灵动交互里横着不夹，这条只管关着的时候")

    def test_turning_dynamic_off_near_the_edge_brings_the_body_back(self):
        win = self._window(dynamic=True)
        win.show()
        win.place_scene(5.0, 400.0)
        win.set_dynamic(False)
        self._assert_inside(win, *win.scene_world())

    def test_making_the_dog_bigger_at_the_edge_keeps_the_body_on_screen(self):
        win = self._window()
        win.show()
        win.set_scale(1.0)
        win.place_scene(*win.keep_scene_inside(0.0, 400.0))
        win.set_scale(1.5)
        self._assert_inside(win, *win.scene_world())


class TwoScreenTests(unittest.TestCase):
    """跨屏（切换的时候不连贯；拖到 LG 左边一闪一闪）：窗口不骑在两块屏中间，狗的身子全离开才换屏，跨着的时候另一块屏上的窗口画另一半。"""

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
        self.win.dog.update(1 / 60)
        self.win._pose = self.win.dog.frame()
        self.win._scene_screen = self.right
        self.win.isVisible = lambda: True
        self.addCleanup(self.win.hide)

    def real_right(self, root_x):
        """根在 root_x 时，狗真实的右边到哪（全局）。"""
        win = self.win
        return win._real_body_rect(root_x, 800.0).right()

    def test_the_window_stays_inside_its_screen_while_part_of_the_dog_is_there(self):
        win = self.win
        win.place_scene(400.0, 800.0)
        self.assertIs(win._scene_screen, self.right)
        win.place_scene(-40.0, 800.0)
        self.assertIs(win._scene_screen, self.right, "根过了交界，还有身子在这边：不换屏")
        self.assertGreaterEqual(win.x(), 0, "窗口不骑在交界上")
        self.assertAlmostEqual(win.scene_world()[0], -40.0, delta=0.6, msg="狗还在它该在的地方（窗口里偏一点画）")

    def test_the_window_never_changes_screen_while_the_dog_is_being_moved(self):
        """快速甩的时候卡：动着的时候主窗口不换屏，画布不用重建。"""
        from PySide6.QtCore import QPoint
        win = self.win
        win.place_scene(400.0, 800.0)
        win._drag = QPoint(0, 0)
        for x in (-900.0, 300.0, -900.0, 300.0, -900.0):
            win.place_scene(x, 800.0)
            self.assertIs(win._scene_screen, self.right, "拖着：不换屏")
            self.assertGreaterEqual(win.x(), 0)
            self.assertAlmostEqual(win.scene_world()[0], x, delta=0.6)
        win._drag = None
        win._settle_screen()
        self.assertIs(win._scene_screen, self.left, "松手、停下来才换")
        self.assertLessEqual(win.x() + win.width(), 0)
        self.assertAlmostEqual(win.scene_world()[0], -900.0, delta=0.6)

    def test_a_dog_parked_just_past_the_edge_gets_the_main_window(self):
        """甩到另一块屏、停在交界旁边：估算的身子还碰着这块屏，主窗口留在这边，狗全由只显示的窗口画，两边都点不到。"""
        win = self.win
        half = 0.62 * win.ppm
        x = -half + 4.0                                     # 估算的身子还差一点点才离开
        self.assertGreater(win._body_rect(x, 800.0).right(), 0, "估算还碰着这块屏")
        self.assertLess(self.real_right(x), 0, "狗真实已经全过去了")
        win.place_scene(x, 800.0)
        win._settle_screen()
        self.assertIs(win._scene_screen, self.left, "主窗口跟过去")
        self.assertLessEqual(win.x() + win.width(), 0)

    def test_the_other_screen_draws_the_other_half_and_the_two_line_up(self):
        win = self.win
        win.place_scene(30.0, 800.0)
        win._sync_ghost()
        ghost = self.ghosts["left"]
        ghost.sync.assert_called_once()
        rect, frame, _ = ghost.sync.call_args[0]
        self.assertTrue(self.left.g.contains(rect), "另一个窗口整个在另一块屏里")
        self.assertAlmostEqual(rect.x() + rect.width() / 2.0 + frame.offset[0], 30.0, delta=0.01, msg="两边按同一个根画：接得上")
        self.assertAlmostEqual(rect.y() + rect.height() - win.ground_px + frame.offset[1], 800.0, delta=0.01)
        self.ghosts["right"].sync.assert_not_called()

    def test_every_screen_has_its_window_ready_and_they_never_move_to_another_screen(self):
        win = self.win
        win.place_scene(1200.0, 800.0)
        win._sync_ghost()
        self.assertEqual(set(self.ghosts), {"left", "right"}, "每块屏一个，提前建好")
        self.assertIs(self.ghosts["left"].home, self.left)
        for g in self.ghosts.values():
            g.sync.assert_not_called()                      # 离交界远：都不画
        win.place_scene(30.0, 800.0)
        win._sync_ghost()
        win.place_scene(-30.0, 800.0)
        win._sync_ghost()
        for call in self.ghosts["left"].sync.call_args_list:
            self.assertTrue(self.left.g.contains(call[0][0]), "只待在自己那块屏上")
        win.place_scene(1200.0, 800.0)
        win._sync_ghost()
        self.ghosts["left"].clear.assert_called()
        self.assertFalse(self.ghosts["left"].drawing, "走远了就画空的，窗口不收")
        self.ghosts["left"].hide.assert_not_called()

    def test_while_zoomed_the_other_screens_window_stays_put_and_still_lines_up(self):
        """看细节放大（widget/closeup.py）：主窗口开始时摆一次（hold_scaled）、之后每帧只改画多大画在哪（show_scaled）；另一块屏上的窗口也一样，
        一路同一个位置、同一个大小（改一次大小画布要重建），两边还是按同一个根画；收完（end_scaled）回到平时的摆法。"""
        win = self.win
        win.place_scene(30.0, 800.0)
        base, plan = (1.0, 30.0, 800.0), (2.0, 130.0, 800.0)
        win.hold_scaled(win.scaled_window([base, plan]), *base)
        geo = win.geometry()
        moves = mock.patch.object(win, "setGeometry", wraps=win.setGeometry)
        calls = moves.start()
        self.addCleanup(moves.stop)
        for i in range(11):
            u = i / 10.0
            x = 30.0 + 100.0 * u
            win.show_scaled(1.0 + u, x, 800.0)
            win._pose = win.dog.frame()
            win._sync_ghost()
            ghost = self.ghosts["left"]
            rect, frame, _ = ghost.sync.call_args[0]
            self.assertAlmostEqual(rect.x() + rect.width() / 2.0 + frame.offset[0], x, delta=0.01, msg="两边按同一个根画")
            self.assertAlmostEqual(rect.y() + rect.height() - win.ground_px + frame.offset[1], 800.0, delta=0.01)
            self.assertAlmostEqual(win.scene_world()[0], x, delta=0.01)
        rects = [c[0][0] for c in ghost.sync.call_args_list[-11:]]
        self.assertTrue(all(r == rects[0] for r in rects), "另一块屏上的窗口放大一路不挪、不改大小")
        self.assertTrue(self.left.g.contains(rects[0]))
        self.assertEqual(calls.call_count, 0, "主窗口也不挪")
        self.assertEqual(win.geometry(), geo)
        win.end_scaled(30.0, 800.0)
        win._pose = win.dog.frame()
        win._sync_ghost()
        rect, frame, _ = ghost.sync.call_args[0]
        self.assertEqual(rect.height(), min(round(config.WINDOW_MAX_HEIGHT * win.scale), 900), "收完：回到平时的高度")
        self.assertAlmostEqual(rect.x() + rect.width() / 2.0 + frame.offset[0], 30.0, delta=0.01)

    def test_quiet_for_a_while_puts_away_the_windows_nobody_needs(self):
        """空的透明窗口一直摆着，系统每帧都要把它和底下的东西叠一遍（量过：WindowServer 的显卡占用多 4～6 个点）。
        安静 GHOST_REST_S 以后收起主窗口那块屏上的、身子离得远的那块屏上的；身子挨着交界的那块一直摆着；一有动静全摆回去。"""
        import time
        import widget.window as window
        win = self.win
        win.place_scene(1200.0, 800.0)
        win._sync_ghost()
        for g in self.ghosts.values():
            g.hide.assert_not_called()                      # 刚有过动静：都摆着
            g.show.reset_mock()
        win._lively_at = time.perf_counter() - window.GHOST_REST_S - 1.0
        win._sync_ghost()
        for g in self.ghosts.values():
            g.hide.assert_not_called()                      # 省电模式关着（默认）：安静多久都不收（摆回去那一下会卡）
        win.power_saving = True
        win._sync_ghost()
        for g in self.ghosts.values():
            g.hide.assert_called_once()
            g.isVisible.return_value = False
        win.place_scene(30.0, 800.0)                        # 挨着左边那块屏
        win._sync_ghost()
        self.ghosts["left"].show.assert_called_once()
        self.assertTrue(self.ghosts["left"].drawing, "挨着交界：那块屏上的窗口摆着，照样画另一半")
        self.ghosts["right"].show.assert_not_called()
        self.ghosts["left"].isVisible.return_value = True
        win.place_scene(1200.0, 800.0)                      # 又走远了，还安静着
        win._sync_ghost()
        self.assertFalse(self.ghosts["left"].drawing)
        self.assertEqual(self.ghosts["left"].hide.call_count, 1, "先画一帧空的，这一帧还不收（收起来的窗口里不留狗的画面）")
        win._sync_ghost()
        self.assertEqual(self.ghosts["left"].hide.call_count, 2)
        self.ghosts["left"].isVisible.return_value = False
        win._lively_at = time.perf_counter()                # 有动静了
        win._sync_ghost()
        self.ghosts["right"].show.assert_called_once()
        self.assertEqual(self.ghosts["left"].show.call_count, 2)

    def test_the_second_window_keeps_drawing_until_the_new_frame_after_switching(self):
        win = self.win
        win.place_scene(-300.0, 800.0)
        win._sync_ghost()
        self.assertTrue(self.ghosts["left"].drawing)
        win.place_scene(-900.0, 800.0)                      # 走远了，换屏
        self.assertIs(win._scene_screen, self.left)
        self.assertGreater(win._ghost_swaps, 0)
        win._sync_ghost()
        self.assertTrue(self.ghosts["left"].drawing, "主窗口的新一帧还没画好：这边还画着")
        self.finish_flip()
        win._frame_swapped()
        win._frame_swapped()
        win._sync_ghost()
        self.assertFalse(self.ghosts["left"].drawing)

    def finish_flip(self):
        """主窗口换屏的等待走完：画够帧、时间到。"""
        import time
        win = self.win
        for _ in range(3):
            win._frame_swapped()
        win._update_flip(time.perf_counter() + 1.0)
        self.assertIsNone(win._flip_until)

    def test_the_main_window_draws_nothing_on_the_old_screen_until_it_has_really_arrived(self):
        """换屏时旧屏上闪一两帧。窗口还没真挪过去，画面已经按新屏的像素密度画了（LG 上放大一倍被切掉的半只狗，MacBook 上缩小一半的狗）。"""
        import time
        win = self.win
        painted = []
        win.view.set_frame = lambda frame: painted.append(frame)
        win.place_scene(-900.0, 800.0)
        self.assertIs(win._scene_screen, self.left)
        self.assertIsNotNone(win._flip_until, "刚换屏")
        self.assertIsNone(painted[-1], "挪窗口之前就换成空的了")
        win._refresh_frame()
        self.assertIsNone(painted[-1], "没到位一直是空的")
        win._sync_ghost()
        self.assertTrue(self.ghosts["left"].drawing, "狗由新屏上的窗口画")
        drawn = []
        win.hover.draw = lambda p: drawn.append(p)
        win._overlay(object())
        self.assertEqual(drawn, [], "「···」也不画（不然会冒出一个缩小一半的）")
        for _ in range(3):
            win._frame_swapped()
        win._update_flip(time.perf_counter())
        self.assertIsNotNone(win._flip_until, "画够帧了，时间没到")
        win._update_flip(time.perf_counter() + 0.2)
        self.assertIsNone(win._flip_until)
        win._refresh_frame()
        self.assertIsNotNone(painted[-1], "到位了，主窗口接手")
        win._sync_ghost()
        self.assertTrue(self.ghosts["left"].drawing, "新的一帧画好之前这边还画着")
        win._frame_swapped()
        win._frame_swapped()
        win._sync_ghost()
        self.assertFalse(self.ghosts["left"].drawing)

    def test_events_forwarded_from_the_other_window_keep_their_time(self):
        """另一块屏上的窗口转交的事件也带着系统打的时间（算手速用）。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget.ghost import GhostWindow
        got = []
        ev = QMouseEvent(QEvent.MouseMove, QPointF(1, 1), QPointF(1, 1), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        ev.setTimestamp(123456)
        fake = mock.Mock()
        fake.owner.mapFromGlobal.side_effect = lambda g: g
        GhostWindow._forward(fake, ev, lambda e: got.append(e.timestamp()))
        self.assertEqual(got, [123456])

    def test_the_wait_ends_even_if_the_window_never_draws(self):
        import time
        win = self.win
        win.place_scene(-900.0, 800.0)
        win._update_flip(time.perf_counter() + 0.2)
        self.assertIsNotNone(win._flip_until, "还在等它画")
        win._update_flip(time.perf_counter() + 1.0)
        self.assertIsNone(win._flip_until, "画不出来（被挡住了）也不一直等")

    def busy(self):
        """狗动着（拖着）。"""
        from PySide6.QtCore import QPoint
        self.win._drag, self.win._dragged = QPoint(0, 0), True
        self.addCleanup(lambda: setattr(self.win, "_drag", None))

    def test_the_main_window_rests_while_the_dog_is_away_on_the_other_screen(self):
        """狗动着、身子不在主窗口那块屏上：主窗口不挪、不改大小、不画（挪一次、交一帧都要等系统回话）。"""
        win = self.win
        self.busy()
        win.place_scene(100.0, 800.0)
        self.assertFalse(win._parked)
        win.place_scene(-900.0, 800.0)
        self.assertTrue(win._parked)
        where = win.geometry()
        with mock.patch.object(win, "setGeometry") as moved:
            for x in (-950.0, -700.0, -600.0):
                win.place_scene(x, 500.0)
                self.assertAlmostEqual(win.scene_world()[0], x, delta=0.01, msg="狗在哪照样记着")
                self.assertAlmostEqual(win.scene_world()[1], 500.0, delta=0.01)
            moved.assert_not_called()
        self.assertEqual(win.geometry(), where)
        win._sync_ghost()
        self.assertTrue(self.ghosts["left"].drawing, "狗由那块屏上的窗口画")
        painted = []
        win.view.set_frame = lambda frame: painted.append(frame)
        win._refresh_frame()
        self.assertIsNone(painted[-1], "主窗口是空的")
        win.place_scene(-60.0, 800.0)
        self.assertFalse(win._parked, "身子快回来了：接着干")
        self.assertIs(win._scene_screen, self.right)

    def test_a_resting_main_window_stops_drawing_after_two_empty_frames(self):
        win = self.win
        self.busy()
        win._anim_timer.stop()
        with mock.patch.object(win.dog, "update"), mock.patch.object(win.view, "update") as update:
            win.place_scene(-900.0, 800.0)
            update.reset_mock()
            win._tick()
            win._frame_swapped()
            win._tick()
            win._frame_swapped()
            self.assertEqual(update.call_count, 2, "再画两帧空的")
            win._tick()
            win._tick()
            self.assertEqual(update.call_count, 2, "不画了")

    def test_the_main_window_comes_over_when_the_dog_lands(self):
        win = self.win
        self.busy()
        win.place_scene(-900.0, 800.0)
        self.assertTrue(win._parked)
        self.assertIs(win._scene_screen, self.right, "飞着不换屏")
        win._drag = None
        win._settle_screen()
        self.assertFalse(win._parked)
        self.assertIs(win._scene_screen, self.left, "停下来才换")
        self.assertIsNotNone(win._flip_until)

    def test_the_window_keeps_its_size_while_the_dog_is_flung(self):
        """改一次大小画布要重建，下一帧要等的时间是平时的两倍（录到的）：第一下长到最高，之后不变。"""
        win = self.win
        import config as cfg
        win.place_scene(600.0, 800.0)
        rest = win.height()
        self.busy()
        win.place_scene(600.0, 700.0)
        tall = win.height()
        self.assertEqual(tall, min(round(cfg.WINDOW_MAX_HEIGHT * win.scale), 900))
        self.assertGreater(tall, rest)
        for y in (650.0, 400.0, 200.0, 60.0, 30.0, 500.0):
            win.place_scene(600.0, y)
            self.assertEqual(win.height(), tall, "靠近屏幕顶也不截短")
            self.assertAlmostEqual(win.scene_world()[1], y, delta=0.01)
            self.assertGreaterEqual(win.y(), 0, "窗口出不了屏幕顶")
        win._fit_height(now=0.0, dt=1.0)
        self.assertEqual(win.height(), tall, "每帧的长高缩回也不动")

    def test_dragging_moves_the_window_once_a_frame(self):
        """鼠标事件比帧勤（8 毫秒一个），每挪一次窗口都要等系统回话：事件只记下来，窗口每帧挪一次。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        win = self.win
        win.place_scene(600.0, 800.0)

        def ev(kind, x, buttons):
            g = QPointF(x, 500.0)
            return QMouseEvent(kind, QPointF(win.mapFromGlobal(g)), g, Qt.LeftButton, buttons, Qt.NoModifier)
        win.mousePressEvent(ev(QEvent.MouseButtonPress, 600.0, Qt.LeftButton))
        with mock.patch.object(win, "place_scene") as placed:
            for x in (620.0, 640.0, 660.0):
                win.mouseMoveEvent(ev(QEvent.MouseMove, x, Qt.LeftButton))
            placed.assert_not_called()
            win._apply_drag()
            placed.assert_called_once()
            self.assertAlmostEqual(placed.call_args[0][0], 660.0, delta=0.01, msg="挪到最新的位置")
            win._apply_drag()
            placed.assert_called_once()
        win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, 680.0, Qt.NoButton))
        self.assertAlmostEqual(win.scene_world()[0], 680.0, delta=0.6, msg="松手那一下的位置马上算数")
        win.place_scene(600.0, 800.0)

    def test_the_dog_on_the_other_window_can_be_clicked(self):
        """鼠标在另一块屏画的狗身上：那个窗口接鼠标；别处不接。"""
        win = self.win
        from PySide6.QtCore import QPoint
        from widget import input as input_module
        win.place_scene(-30.0, 800.0)
        win._sync_ghost()
        ghost = self.ghosts["left"]
        ghost.rect.return_value.contains.return_value = True
        ghost.mapFromGlobal.return_value = QPoint(10, 10)
        with mock.patch.object(input_module.QCursor, "pos", lambda *a: QPoint(-20, 700)):
            ghost.view.probe.return_value = True
            self.assertTrue(win._update_ghost_hit(False))
            ghost.set_accepting.assert_called_with(True)
            ghost.view.probe.return_value = False
            self.assertFalse(win._update_ghost_hit(False))
            ghost.set_accepting.assert_called_with(False)
            ghost.view.probe.return_value = True
            ghost.pressed = True
            self.assertFalse(win._update_ghost_hit(True), "按着的时候别的不算")
            ghost.set_accepting.assert_called_with(True)
            ghost.pressed = False
            win.isVisible = lambda: False
            self.assertFalse(win._update_ghost_hit(False), "主窗口没显示：另一块屏上画的也不接")
            ghost.set_accepting.assert_called_with(False)
            win.isVisible = lambda: True

