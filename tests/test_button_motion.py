"""按钮反馈的交互回归：真实 Qt 输入语义、固定布局、长按取消和已有状态动画共存。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from widget import native, sticker
from widget.widgets import FlatIcon, FrameClock, HoldButton, HoldPill, IconButton, MotionButton, SelectPill, Swatch, Switch


class AnimationHost(QWidget):
    """让 Switch 原有动画像在卡片里一样登记，用可控节拍检查和 hover 的独立性。"""
    def __init__(self):
        super().__init__()
        self.animators = set()

    def run_animator(self, animator):
        self.animators.add(animator)
        return True

    def step(self, dt):
        for animator in list(self.animators):
            if not animator.tick(dt):
                self.animators.discard(animator)


class ButtonMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host_patch = mock.patch.object(FrameClock, "default_host", None)
        self.host_patch.start()
        self.reduce_patch = mock.patch.object(native, "reduce_motion", return_value=False)
        self.reduce_patch.start()
        self.host = AnimationHost()
        self.host.setGeometry(100, 100, 350, 180)
        self.host.setStyleSheet(sticker.stylesheet(sticker.theme()))
        self.buttons = []
        self.host.show()
        self.app.processEvents()
        QTest.mouseMove(self.host, QPoint(3, 3))

    def tearDown(self):
        self.host.hide()
        for button in self.buttons:
            button.motion.clock.stop()
            driver = getattr(button, "driver", None)
            if driver is not None:
                driver._timer.stop()
        self.host.deleteLater()
        self.app.processEvents()
        self.reduce_patch.stop()
        self.host_patch.stop()

    def add(self, button, size=None):
        button.setParent(self.host)
        if size is not None:
            button.setFixedSize(*size)
        button.move(80, 65)
        self.buttons.append(button)
        button.show()
        self.app.processEvents()
        return button

    @staticmethod
    def advance(button, seconds=0.35):
        button.motion.clock.stop()
        for _ in range(round(seconds / 0.01)):
            button.motion.tick(0.01)

    def hover(self, button):
        QTest.mouseMove(self.host, QPoint(3, 3))
        QTest.mouseMove(button, button.rect().center())
        self.app.processEvents()

    def test_mouse_hover_press_release_and_keyboard_keep_single_click_semantics(self):
        button = self.add(MotionButton("Button"), (104, 30))
        clicked = []
        button.clicked.connect(lambda checked=False: clicked.append(checked))
        geometry = button.geometry()
        self.hover(button)
        self.assertEqual(button.motion.hover.target, 1.0)
        self.advance(button)
        self.assertAlmostEqual(button.motion.scale, 0.975, places=4)
        QTest.mousePress(button, Qt.LeftButton)
        self.advance(button)
        self.assertTrue(button.isDown())
        self.assertAlmostEqual(button.motion.scale, 0.95, places=4)
        self.assertEqual(clicked, [])
        QTest.mouseRelease(button, Qt.LeftButton)
        self.assertEqual(clicked, [False])
        self.advance(button)
        self.assertFalse(button.motion._held)
        self.assertEqual(button.geometry(), geometry)
        QTest.keyClick(button, Qt.Key_Space)
        self.assertEqual(clicked, [False, False], "公共动画不重复派发鼠标或键盘点击")

    def test_quick_click_has_a_visible_press_pulse_without_delaying_the_action(self):
        for factory in (Switch, lambda: FlatIcon("tune"), lambda: MotionButton("Check")):
            for duration in (0.02, 0.05):
                button = self.add(factory())
                button.resize(button.sizeHint().expandedTo(button.minimumSize()))
                self.hover(button)
                self.advance(button)
                clicked = []
                button.clicked.connect(lambda *_: clicked.append(True))
                QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
                self.advance(button, duration)
                before_release = button.motion.scale
                QTest.mouseRelease(button, Qt.LeftButton, pos=button.rect().center())
                self.assertEqual(clicked, [True], "短点击动作在松手时立即发生，不等视觉脉冲")
                self.assertEqual(button.motion.scale, before_release, "松手时视觉不能跳变")
                scales = [before_release]
                for _ in range(35):
                    self.advance(button, .01)
                    scales.append(button.motion.scale)
                with self.subTest(button=type(button).__name__, duration=duration):
                    self.assertLessEqual(min(scales), .955, "20/50ms点击也有可见的完整按压")
                    minimum = scales.index(min(scales))
                    self.assertTrue(all(b >= a - 1e-9 for a,b in zip(scales[minimum:],scales[minimum+1:])),
                                    "短按完成后连续恢复，不出现第二次下沉")
                    self.assertAlmostEqual(scales[-1], .975, places=4)
                    self.assertFalse(button.motion._release_pending)
                button.hide()

    def test_custom_state_controls_do_not_run_duplicate_color_animations(self):
        for factory in (Switch, lambda: FlatIcon("tune"), lambda: Swatch("#f00")):
            button = self.add(factory())
            self.assertIsNone(button.motion.selection)
            self.assertIsNone(button.motion.tint)
            self.hover(button)
            QTest.mousePress(button, Qt.LeftButton)
            self.advance(button, .06)
            self.assertEqual(button.motion.press_amount, 0)
            self.assertLess(button.motion.scale, .96)
            QTest.mouseRelease(button, Qt.LeftButton)
            button.hide()

    def test_capture_freeze_preserves_visuals_and_blocks_button_input(self):
        from widget import motion
        button = self.add(HoldPill("Delete", "danger"), (104,30))
        self.hover(button)
        self.advance(button)
        before = (button.motion.hover.value, button.motion.direction_x.value, button.motion.scale)
        clicked, held = [], []
        button.clicked.connect(lambda *_: clicked.append(True))
        button.held.connect(lambda: held.append(True))
        with mock.patch.object(motion, "ui_frozen", return_value=True), mock.patch("widget.widgets.ui_frozen", return_value=True):
            self.app.sendEvent(button, QEvent(QEvent.Leave))
            QTest.mouseClick(button, Qt.LeftButton)
            self.advance(button)
            button.driver.press()
            button.driver._tick()
        self.assertEqual(clicked, [])
        self.assertEqual(held, [])
        self.assertFalse(button.driver._down)
        self.assertEqual((button.motion.hover.value, button.motion.direction_x.value, button.motion.scale), before)

    def test_capture_freeze_pauses_only_ui_clock_steps_and_resumes_without_time_jump(self):
        from widget import animation
        button = self.add(MotionButton("Clock"), (104,30))
        steps = []
        clock = FrameClock(button, lambda dt: steps.append(dt) or True)
        clock.start()
        clock._timer.stop()
        clock.running = True
        now = clock._last
        with mock.patch.object(animation, "ui_frozen", return_value=True):
            self.assertTrue(clock.frame_step(now + 3, 1/60))
        self.assertEqual(steps, [])
        self.assertTrue(clock.running)
        clock.frame_step(now + 3 + 1/60, 1/60)
        self.assertAlmostEqual(steps[0], 1/60, places=6)
        clock.stop()


    def test_hover_can_reverse_mid_animation_without_jumping_to_an_endpoint(self):
        button = self.add(MotionButton("Button"), (104, 30))
        self.hover(button)
        self.advance(button, 0.02)
        before = button.motion.hover.value
        self.assertGreater(before, 0.0)
        self.assertLess(before, 1.0)
        # 只发送离开事件，避免测试用真实等待让帧时机左右重定向断言。
        self.app.sendEvent(button, QEvent(QEvent.Leave))
        self.assertEqual(button.motion.hover.value, before, "改目标时保留当下视觉位置")
        self.assertEqual(button.motion.hover.target, 0.0)
        self.advance(button)
        self.assertAlmostEqual(button.motion.hover.value, 0.0)
        self.assertFalse(button.motion.tick(0.1), "反馈停稳后不继续占用帧")

    def test_pressed_edge_stays_clickable_while_the_visual_contracts(self):
        button = self.add(MotionButton("Button"), (104, 30))
        clicked = []
        button.clicked.connect(lambda checked=False: clicked.append(checked))
        # 直接按常态的视觉边缘；按下后的轻缩不能缩掉已经锁住的命中区域。
        edge = QPoint(int(button.motion.visual_rect().right()) - 1, button.height() // 2)
        self.assertTrue(button.hitButton(edge))
        QTest.mousePress(button, Qt.LeftButton, pos=edge)
        self.advance(button)
        self.assertLess(button.motion.visual_rect().width(), button.motion.content_rect().width(),
                        "按压后整体视觉确实缩小，偏移仍可朝向指针")
        self.assertTrue(button.hitButton(edge), "按下时锁定命中区，不能因为视觉收缩丢失点击")
        QTest.mouseRelease(button, Qt.LeftButton, pos=edge)
        self.assertEqual(clicked, [False])

    def test_button_families_keep_geometry_and_reserved_visuals_inside_the_widget(self):
        factories = (
            (lambda: MotionButton("Button"), (104, 30)),
            (lambda: SelectPill("Stand"), (60, 30)),
            (lambda: HoldPill("Delete", "danger"), (94, 30)),
            (lambda: HoldButton("Reset"), (74, 30)),
            (lambda: IconButton("close", size=26), None),
            (lambda: IconButton("gear", size=36), None),
            (Switch, None),
            (lambda: Swatch("#ff0000"), None),
        )
        for factory, size in factories:
            button = self.add(factory(), size)
            with self.subTest(button=type(button).__name__, size=button.size()):
                geometry = button.geometry()
                self.hover(button)
                self.advance(button)
                for down in (False, True, False):
                    if down:
                        QTest.mousePress(button, Qt.LeftButton)
                    else:
                        QTest.mouseRelease(button, Qt.LeftButton)
                    self.advance(button, 0.15)
                    rect = button.motion.visual_rect()
                    bounds = QRectF(button.rect()).adjusted(-1e-8, -1e-8, 1e-8, 1e-8)
                    self.assertTrue(bounds.contains(rect), (rect, bounds))
                    offset = rect.center() - QRectF(button.rect()).center()
                    self.assertLessEqual(abs(offset.x()), 2.0)
                    self.assertLessEqual(abs(offset.y()), 2.0)
                    self.assertEqual(button.geometry(), geometry)
            button.hide()

    def test_switch_knob_animation_continues_independently_of_hover_and_press(self):
        switch = self.add(Switch())
        toggles = []
        switch.toggled.connect(toggles.append)
        self.hover(switch)
        QTest.mouseClick(switch, Qt.LeftButton)
        self.assertEqual(toggles, [True])
        self.assertIn(switch, self.host.animators)
        self.assertLess(switch._pos, 1.0, "开关原来的0.18秒滑钮动画仍然登记运行")
        self.host.step(0.06)
        self.advance(switch, 0.06)
        middle = switch._pos
        self.assertGreater(middle, 0.0)
        self.assertLess(middle, 1.0)
        self.app.sendEvent(switch, QEvent(QEvent.Leave))
        self.host.step(0.12)
        self.advance(switch)
        self.assertEqual(switch._pos, 1.0)
        self.assertTrue(switch.isChecked())
        self.assertEqual(toggles, [True], "反馈没有重复切换状态")
        self.assertAlmostEqual(switch.motion.hover.value, 0.0)

    def test_flat_icon_uses_existing_padding_without_clipping_or_changing_geometry(self):
        self.host.setStyleSheet("background: white;")
        button = self.add(FlatIcon("tune"))
        geometry = button.geometry()
        self.hover(button)
        self.advance(button)
        image = self.host.grab().toImage()
        # 整体缩小/偏移也不能把图形画到控件的最外圈。
        corners = [QPoint(x, y) for x in range(button.width()) for y in (0, button.height() - 1)]
        corners += [QPoint(x, y) for y in range(button.height()) for x in (0, button.width() - 1)]
        self.assertTrue(all(image.pixelColor(button.pos() + p).lightness() > 240 for p in corners))
        QTest.mouseClick(button, Qt.LeftButton)
        self.assertTrue(button.isChecked())
        self.assertEqual(button.geometry(), geometry)

    def test_long_press_cancels_when_leaving_hiding_or_disabling(self):
        factories = (lambda: HoldButton("Reset"), lambda: HoldPill("Delete", "danger"),
                     lambda: IconButton("power", hold=True))
        for factory in factories:
            for cancel in ("leave", "hide", "disable"):
                button = self.add(factory())
                fired = []
                button.held.connect(lambda: fired.append(True))
                with self.subTest(button=type(button).__name__, cancel=cancel):
                    self.hover(button)
                    QTest.mousePress(button, Qt.LeftButton)
                    self.assertTrue(button.driver._down)
                    if cancel == "leave":
                        # Qt实际按住时由mouse grab把控件外的拖动继续送给按钮。
                        # QTest.mouseMove(QWidget)没有保留buttons，故显式发送这一真实事件形状。
                        point = QPointF(-5, button.height() / 2)
                        self.app.sendEvent(button, QMouseEvent(QEvent.MouseMove, point,
                                           QPointF(button.mapToGlobal(point.toPoint())), Qt.NoButton,
                                           Qt.LeftButton, Qt.NoModifier))
                    elif cancel == "hide":
                        button.hide()
                    else:
                        button.setEnabled(False)
                    # 推到长按截止之后，确认危险动作没有因隐藏/失效的按住状态误触发。
                    with mock.patch("widget.widgets.time.perf_counter", return_value=button.driver._t0 + 2.0):
                        button.driver._tick()
                    self.assertFalse(button.driver._down)
                    self.assertEqual(fired, [])
                    self.assertFalse(button.motion._held)
                    QTest.mouseRelease(button, Qt.LeftButton)
                button.hide()

    def test_long_press_fires_once_and_short_click_does_not_fire(self):
        button = self.add(HoldPill("Delete", "danger"), (94, 30))
        fired = []
        button.held.connect(lambda: fired.append(True))
        QTest.mouseClick(button, Qt.LeftButton)
        self.assertEqual(fired, [])
        QTest.mousePress(button, Qt.LeftButton)
        with mock.patch("widget.widgets.time.perf_counter", return_value=button.driver._t0 + 2.0):
            button.driver._tick()
            button.driver._tick()
        self.assertEqual(fired, [True])
        QTest.mouseRelease(button, Qt.LeftButton)
        self.assertEqual(fired, [True])

    def test_reduced_motion_avoids_scaling_and_keeps_clicks_and_toggle_working(self):
        with mock.patch.object(native, "reduce_motion", return_value=True):
            switch = self.add(Switch())
            normal = switch.motion.visual_rect()
            self.hover(switch)
            QTest.mousePress(switch, Qt.LeftButton)
            self.assertEqual(switch.motion.visual_rect(), normal)
            self.assertFalse(switch.motion.clock.running)
            QTest.mouseRelease(switch, Qt.LeftButton)
            self.assertTrue(switch.isChecked())
            self.assertEqual(switch._pos, 1.0)
            self.assertEqual(switch.motion.visual_rect(), normal)

    def test_pill_keeps_26_point_body_and_transparent_parent_edges_through_motion(self):
        """从父级整图检查可见26px轮廓和真实2px外侧余量，不能用抓子控件的背景假象验收。"""
        self.host.setStyleSheet("background: white;")
        for factory in (lambda: MotionButton("Test"), lambda: SelectPill("Stand"),
                        lambda: HoldPill("Delete", "danger"), lambda: HoldButton("Reset")):
            button = self.add(factory(), (104, 30))
            self.assertEqual(button.motion.content_rect().height(), 26)
            self.assertEqual(button.motion.content_rect().width(), 100)
            for x, y, down in ((52, 15, False), (3, 3, False), (100, 26, False), (52, 3, True)):
                self.hover(button)
                QTest.mouseMove(button, QPoint(x, y))
                if down:
                    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(x, y))
                self.advance(button)
                image = self.host.grab().toImage()
                border = [QPoint(px, py) for px in range(button.width()) for py in (0, button.height() - 1)]
                border += [QPoint(px, py) for py in range(button.height()) for px in (0, button.width() - 1)]
                with self.subTest(button=type(button).__name__, pointer=(x, y), down=down):
                    self.assertTrue(all(image.pixelColor(button.pos() + p) == QColor("white") for p in border),
                                    "上下外缘必须留白，不能让完整胶囊在widget边界被截平")
                    self.assertEqual(button.height(), 30)
                QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(x, y))
            button.hide()

    def test_direction_moves_the_whole_button_and_locks_while_pressed(self):
        button = self.add(MotionButton("Stable"), (104, 30))
        def text_center():
            image = self.host.grab().toImage()
            bg, _border, fg, _width = button.surface_colors()
            start, ink = bg.getRgb()[:3], fg.getRgb()[:3]
            direction = [b-a for a,b in zip(start,ink)]
            norm = sum(v*v for v in direction)
            total = horizontal = 0.0
            # 仅中间文字区域，避开单一路径画出的胶囊描边。
            for y in range(7, 24):
                for x in range(25, 79):
                    color = image.pixelColor(button.pos() + QPoint(x,y)).getRgb()[:3]
                    amount = max(0.0, sum((c-a)*d for c,a,d in zip(color,start,direction)) / norm)
                    total += amount
                    horizontal += x * amount
            self.assertGreater(total, 1.0)
            return horizontal / total
        self.hover(button)
        QTest.mouseMove(button, QPoint(20, 8))
        self.advance(button)
        self.assertLess(button.motion.offset.x(), 0)
        center = button.motion.content_rect().center()
        left = button.motion.transform().map(center)
        left_ink = text_center()
        self.assertEqual(left, button.motion.visual_rect().center())
        QTest.mouseMove(button, QPoint(80, 18))
        self.advance(button)
        right = button.motion.transform().map(center)
        right_ink = text_center()
        self.assertGreater(button.motion.offset.x(), 0)
        self.assertGreater(right.x(), left.x(), "文字和轮廓共用的transform应整体向指针偏移")
        self.assertAlmostEqual(right_ink-left_ink, right.x()-left.x(), delta=.4,
                               msg="父图里的字形必须跟轮廓一起位移，不能只移动背景")
        QTest.mousePress(button, Qt.LeftButton, pos=QPoint(80, 18))
        target = button.motion.direction_x.target
        point = QPointF(30, 13)
        self.app.sendEvent(button, QMouseEvent(QEvent.MouseMove, point,
                           QPointF(button.mapToGlobal(point.toPoint())), Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(button.motion.direction_x.target, target)
        self.advance(button)
        self.assertTrue(QRectF(button.rect()).contains(button.motion.visual_rect()))
        QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(30, 13))

    def test_pressed_background_fades_and_retargets_from_visible_color_in_both_themes(self):
        previous_dark = sticker.is_dark()
        try:
            for dark in (False, True):
                sticker.set_dark(dark)
                self.host.setStyleSheet(sticker.stylesheet(sticker.theme()))
                button = self.add(MotionButton(""), (104, 30))
                self.hover(button)
                self.advance(button)
                def color():
                    return self.host.grab().toImage().pixelColor(button.pos() + QPoint(52, 15))
                before = color()
                QTest.mousePress(button, Qt.LeftButton)
                self.assertEqual(button.motion.press_amount, 0)
                self.assertEqual(color(), before, "按下瞬间不能闪入反色")
                self.advance(button, 0.06)
                mid = color()
                self.assertGreater(button.motion.press_amount, 0)
                self.assertLess(button.motion.press_amount, 1)
                self.assertNotEqual(mid, before)
                progress = button.motion.press_amount
                QTest.mouseRelease(button, Qt.LeftButton)
                self.assertEqual(button.motion.press_amount, progress)
                self.assertEqual(color(), mid, "快速松开从当前颜色衔接")
                self.advance(button)
                self.assertEqual(button.motion.press_amount, 0)
                button.hide()
        finally:
            sticker.set_dark(previous_dark)

    def test_quiet_hover_fades_the_final_fill_without_a_dark_middle_flash(self):
        previous = sticker.is_dark()
        try:
            for dark in (False, True):
                sticker.set_dark(dark)
                button = self.add(MotionButton(""), (104,30))
                button.setProperty("quiet", True)
                paper, fill = QColor(sticker.PAPER), QColor(sticker.PAPER_2)
                colors = []
                for amount in (0, .25, .5, .75, 1):
                    button.motion.hover.set_target(amount, instant=True)
                    bg, *_ = button.surface_colors()
                    # 与卡片底色合成后的可见RGB应处于起点和终点之间。
                    rgb = [round(a*(1-bg.alphaF())+b*bg.alphaF()) for a,b in zip(paper.getRgb()[:3],bg.getRgb()[:3])]
                    colors.append(rgb)
                    self.assertTrue(all(min(a,b) <= c <= max(a,b) for a,b,c in zip(paper.getRgb()[:3],fill.getRgb()[:3],rgb)))
                self.assertEqual(colors[0], list(paper.getRgb()[:3]))
                self.assertEqual(colors[-1], list(fill.getRgb()[:3]))
                button.hide()
        finally:
            sticker.set_dark(previous)

    def test_hidden_initial_selection_is_ready_before_first_paint(self):
        for factory in (lambda: MotionButton("Choice"), lambda: SelectPill("Stand")):
            button = factory()
            button.setCheckable(True)
            button.setChecked(True)
            self.assertEqual(button.motion.selection.value, 1.0)
            self.assertEqual(button.motion.selection.target, 1.0)
            self.assertFalse(button.motion.clock.running)
            self.add(button, (104, 30))
            self.assertEqual(button.motion.selection.value, 1.0, "显示后无需悬停唤醒时钟才显示选中")
            button.hide()
            button.setChecked(False)
            self.assertEqual(button.motion.selection.value, 0.0)

    def test_checkable_preview_to_checked_color_never_reverses_on_release(self):
        previous_dark = sticker.is_dark()
        try:
            for dark in (False, True):
                for hold_frames in (3, 30):
                    sticker.set_dark(dark)
                    self.host.setStyleSheet(sticker.stylesheet(sticker.theme()))
                    button = self.add(MotionButton(""), (104, 30))
                    button.setCheckable(True)
                    self.hover(button)
                    self.advance(button)
                    point = button.pos() + QPoint(52, 15)
                    colors = []
                    def sample():
                        colors.append(self.host.grab().toImage().pixelColor(point))
                    sample()
                    QTest.mousePress(button, Qt.LeftButton)
                    for _ in range(hold_frames):
                        self.advance(button, .01)
                        sample()
                    release_color = colors[-1]
                    QTest.mouseRelease(button, Qt.LeftButton)
                    self.assertTrue(button.isChecked())
                    self.assertEqual(self.host.grab().toImage().pixelColor(point), release_color)
                    for _ in range(35):
                        self.advance(button, .01)
                        sample()
                    target = colors[-1]
                    distances = [sum(abs(a-b) for a,b in zip(c.getRgb()[:3],target.getRgb()[:3])) for c in colors]
                    with self.subTest(dark=dark, hold_frames=hold_frames):
                        self.assertTrue(all(b <= a for a,b in zip(distances,distances[1:])), distances)
                        self.assertEqual(button.motion.selection.value, 1.0)
                    button.hide()
        finally:
            sticker.set_dark(previous_dark)


if __name__ == "__main__":
    unittest.main()
