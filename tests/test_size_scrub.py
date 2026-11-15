"""百分比数字的精调契约：浮点输入、非线性拖动、整数显示和原位编辑。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from widget.sizecontrol import SizeScrubber


class SizeScrubberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.control = SizeScrubber()
        self.control.show()
        self.app.processEvents()
        self.events = []
        self.control.adjustmentStarted.connect(lambda: self.events.append("start"))
        self.control.valueChanged.connect(lambda value: self.events.append(("value", value)))
        self.control.adjustmentFinished.connect(lambda: self.events.append("finish"))
        self.now = 0.0

    def tearDown(self):
        self.control.hide()
        self.control.deleteLater()
        self.app.processEvents()

    def mouse(self, kind, x, dt=0.02, button=Qt.LeftButton):
        self.now += dt
        local = QPointF(32 + x, 13.25)
        point = QPointF(1032.125 + x, 813.375)
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
        event = QMouseEvent(kind, local, point, button, buttons, Qt.NoModifier)
        with mock.patch("widget.sizecontrol.time.perf_counter", return_value=self.now):
            {QEvent.MouseButtonPress: self.control.mousePressEvent,
             QEvent.MouseMove: self.control.mouseMoveEvent,
             QEvent.MouseButtonRelease: self.control.mouseReleaseEvent}[kind](event)

    def start_drag(self, value=100.25):
        self.control.set_value(value)
        self.mouse(QEvent.MouseButtonPress, 0)
        self.mouse(QEvent.MouseMove, 4, dt=0.1)
        self.assertTrue(self.control.adjusting)

    def edit(self, text):
        self.control.start_edit()
        self.control.editor.setText(text)
        self.control.editor.setModified(True)

    def test_sync_preserves_float_and_integer_display_without_signals(self):
        self.control.set_value(100.499999)
        self.assertEqual(self.control.text(), "100%")
        self.control.set_value(100.5)
        self.assertEqual(self.control.text(), "101%")
        self.control.set_value(123.4567890123)
        self.assertEqual(self.control.value, 123.4567890123)
        self.assertEqual(self.control.text(), "123%")
        self.assertEqual(self.events, [])

    def test_subpixel_deltas_accumulate_without_quantization_or_release_rounding(self):
        self.start_drag()
        initial = self.control.value
        for n in range(1, 11):
            self.mouse(QEvent.MouseMove, 4 + n * 0.000125, dt=0.02)
        value = self.control.value
        self.assertAlmostEqual(value - initial, 0.000125, places=10)
        changes = list(self.events)
        self.mouse(QEvent.MouseButtonRelease, 4.00125)
        self.assertEqual(self.control.value, value)
        self.assertEqual(self.events[:-1], changes)
        self.assertEqual(self.events.count("start"), 1)
        self.assertEqual(self.events.count("finish"), 1)
        self.assertFalse(self.control.editor.isVisible())

    def test_fast_drag_accelerates_smoothly_with_a_bounded_gain(self):
        results = []
        gains = []
        for dt in (0.1, 0.005):
            self.control.set_value(100)
            self.mouse(QEvent.MouseButtonPress, 0)
            for x in range(4, 45, 4):
                self.mouse(QEvent.MouseMove, x, dt=dt)
                gains.append(self.control._gain)
            results.append(self.control.value)
            self.mouse(QEvent.MouseButtonRelease, 44)
        self.assertGreater(results[1], results[0])
        self.assertTrue(all(1 <= gain <= self.control.MAX_GAIN for gain in gains))
        stopped = self.control.value
        self.control._animate(0.5)
        self.assertEqual(self.control.value, stopped, "动画只改变反馈，数值没有惯性")

    def test_reverse_at_upper_and_lower_bounds_has_no_overshoot_dead_zone(self):
        for start, end, reverse, limit in ((399.9, 3000, 2999.875, 400.0),
                                          (30.1, -3000, -2999.875, 30.0)):
            with self.subTest(limit=limit):
                self.control.set_value(start)
                self.mouse(QEvent.MouseButtonPress, 0)
                self.mouse(QEvent.MouseMove, end)
                self.assertEqual(self.control.value, limit)
                self.mouse(QEvent.MouseMove, reverse, dt=0.1)
                self.assertNotEqual(self.control.value, limit)
                self.assertLess(abs(self.control.value - limit), 0.1)
                self.mouse(QEvent.MouseButtonRelease, reverse)

    def test_click_or_tiny_motion_opens_editor_without_adjusting(self):
        self.control.set_value(100.375)
        self.mouse(QEvent.MouseButtonPress, 0)
        self.mouse(QEvent.MouseMove, 0.75)
        self.mouse(QEvent.MouseButtonRelease, 0.75)
        self.assertTrue(self.control.editor.isVisible())
        self.assertEqual(self.control.editor.text(), "100")
        self.assertEqual(self.control.value, 100.375)
        self.assertEqual(self.events, [])

    def test_release_can_recognize_drag_even_without_an_intermediate_move(self):
        self.mouse(QEvent.MouseButtonPress, 0)
        self.mouse(QEvent.MouseButtonRelease, 4.25, dt=0.1)
        self.assertFalse(self.control.editor.isVisible())
        self.assertGreater(self.control.value, 100)
        self.assertEqual(self.events[0], "start")
        self.assertEqual(self.events[-1], "finish")

    def test_unchanged_integer_editor_does_not_round_full_precision(self):
        self.control.set_value(100.375)
        self.control.start_edit()
        QTest.keyClick(self.control.editor, Qt.Key_Return)
        self.assertEqual(self.control.value, 100.375)
        self.assertFalse(self.control.editor.isVisible())
        self.assertEqual(self.events, [])

    def test_edit_return_commits_once_and_escape_discards(self):
        self.edit("134.375")
        QTest.keyClick(self.control.editor, Qt.Key_Return)
        self.control._commit_text()
        self.assertEqual(self.events, ["start", ("value", 134.375), "finish"])
        self.assertEqual(self.control.text(), "134%")
        self.events.clear()
        self.edit("210")
        QTest.keyClick(self.control.editor, Qt.Key_Escape)
        self.assertEqual(self.control.value, 134.375)
        self.assertEqual(self.events, [])

    def test_invalid_or_out_of_range_edit_leaves_value_unchanged(self):
        self.control.set_value(150.625)
        for text in ("", "nan", "inf", "no", "29.99", "400.01"):
            with self.subTest(text=text):
                self.edit(text)
                self.control._commit_text()
                self.assertEqual(self.control.value, 150.625)
                self.assertFalse(self.control.editor.isVisible())
        self.assertEqual(self.events, [])

    def test_external_sync_does_not_overwrite_editor_or_selection(self):
        self.control.set_value(100.375)
        self.control.start_edit()
        self.assertEqual(self.control.editor.selectedText(), "100")
        self.control.set_value(120.125)
        self.assertEqual(self.control.editor.selectedText(), "100")
        self.control._commit_text()
        self.assertEqual(self.control.value, 120.125, "未编辑的整数不会覆盖外部新值")
        self.edit("125")
        self.control.set_value(130.625)
        self.assertEqual(self.control.editor.text(), "125")
        self.control._commit_text()
        self.assertEqual(self.control.value, 125)

    def test_drag_escape_restores_start_value_before_finishing_once(self):
        self.start_drag(100.375)
        self.mouse(QEvent.MouseMove, 10.25)
        self.control.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        self.assertEqual(self.control.value, 100.375)
        self.assertFalse(self.control.adjusting)
        self.mouse(QEvent.MouseButtonRelease, 10.25)
        self.assertEqual(self.events[-2:], [("value", 100.375), "finish"])
        self.assertEqual(self.events.count("start"), 1)
        self.assertEqual(self.events.count("finish"), 1)
        self.assertFalse(self.control.editor.isVisible())

    def test_hide_disable_or_lost_capture_finishes_once_without_reverting(self):
        for action in ("hide", "disable", "ungrab", "deactivate"):
            with self.subTest(action=action):
                self.control.setEnabled(True)
                self.control.show()
                self.events.clear()
                self.start_drag()
                value = self.control.value
                if action == "hide":
                    self.control.hide()
                elif action == "disable":
                    self.control.setEnabled(False)
                else:
                    self.app.sendEvent(self.control, QEvent(QEvent.UngrabMouse if action == "ungrab" else QEvent.WindowDeactivate))
                self.control._finish()
                self.assertEqual(self.control.value, value)
                self.assertFalse(self.control.adjusting)
                self.assertEqual(self.events.count("start"), 1)
                self.assertEqual(self.events.count("finish"), 1)

    def test_keyboard_step_brackets_each_adjustment_and_keeps_existing_fraction(self):
        self.control.set_value(100.375)
        for key, expected in ((Qt.Key_Right, 101.375), (Qt.Key_Left, 100.375)):
            self.events.clear()
            self.control.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
            self.assertEqual(self.events, ["start", ("value", expected), "finish"])

    def test_native_bridge_deduplicates_moves_and_ends_with_the_gesture(self):
        bridge = self.control._pointer_drag
        with mock.patch.object(bridge, "begin") as begin:
            self.mouse(QEvent.MouseButtonPress, 0)
            begin.assert_called_once()
        self.control._drag_to(QPointF(1036.125, 813.375), self.now + 0.1)
        initial = self.control.value
        self.control._drag_to(QPointF(1036.125125, 813.375), self.now + 0.12)
        self.assertGreater(self.control.value, initial)
        with mock.patch.object(bridge, "move", return_value=True), mock.patch.object(self.control, "_drag_to") as drag:
            self.mouse(QEvent.MouseMove, 4.000125)
            drag.assert_not_called()
        with mock.patch.object(bridge, "end", wraps=bridge.end) as end:
            self.mouse(QEvent.MouseButtonRelease, 4.000125)
            end.assert_called_once()
        self.assertFalse(self.control.adjusting)
        self.assertEqual(self.events.count("start"), 1)
        self.assertEqual(self.events.count("finish"), 1)

    @mock.patch("widget.sizecontrol.native.reduce_motion", return_value=False)
    def test_hover_and_drag_remain_transparent_in_both_appearances(self, _reduce_motion):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QImage, QPainter, QRegion
        from PySide6.QtWidgets import QWidget
        from widget import sticker
        old_dark = sticker.is_dark()
        try:
            for dark in (False, True):
                sticker.set_dark(dark)
                for pressed in (False, True):
                    with self.subTest(dark=dark, pressed=pressed):
                        self.control._hovered = True
                        self.control._retarget()
                        if pressed:
                            self.mouse(QEvent.MouseButtonPress, 0)
                            self.mouse(QEvent.MouseMove, 6.25, dt=0.1)
                        for _ in range(45):
                            self.control._animate(1 / 60)
                        image = QImage(self.control.size(), QImage.Format_ARGB32_Premultiplied)
                        image.fill(Qt.transparent)
                        painter = QPainter(image)
                        self.control.render(painter, QPoint(), QRegion(), QWidget.DrawChildren)
                        painter.end()
                        self.assertEqual(image.pixelColor(32, 5).alpha(), 0, "数字上方不能出现悬停 / 按压底板")
                        # 按实际墨迹列找左箭头和首个数字的空隙，不把旧64px控件上的x=12当作永久空白。
                        columns = [x for x in range(image.width())
                                   if any(image.pixelColor(x, y).alpha() for y in range(image.height()))]
                        groups = []
                        for x in columns:
                            if not groups or x > groups[-1][-1] + 1:
                                groups.append([])
                            groups[-1].append(x)
                        self.assertGreaterEqual(len(groups), 2)
                        self.assertLessEqual(len(groups[0]), 7, "左箭头应独立，不能与数字粘成一块")
                        gap_x = (groups[0][-1] + groups[1][0]) // 2
                        self.assertTrue(all(image.pixelColor(gap_x, y).alpha() == 0 for y in range(image.height())),
                                        "箭头与数字之间整列保持透明")
                        self.assertTrue(any(image.pixelColor(x, y).alpha() for x in range(16, 49) for y in range(8, 20)))
                        self.control._finish()
        finally:
            sticker.set_dark(old_dark)

    @mock.patch("widget.sizecontrol.native.reduce_motion", return_value=False)
    def test_group_bias_is_smooth_bounded_and_independent_of_numeric_input(self, _reduce_motion):
        self.control._hovered = True
        self.mouse(QEvent.MouseMove, 28)
        self.assertEqual(self.control._offset_x.value, 0, "悬停位置只改目标，不瞬移")
        for _ in range(60):
            self.control._animate(1 / 60)
        self.assertGreater(self.control._offset_x.value, 1)
        self.assertLessEqual(self.control._offset_x.value, 2)
        self.start_drag(100.375)
        for _ in range(60):
            self.control._animate(1 / 60)
        right = self.control._offset_x.value
        value = self.control.value
        self.mouse(QEvent.MouseMove, 3.999875, dt=0.1)
        self.assertEqual(self.control._offset_x.value, right, "反向从当前绘制位置连续接上")
        self.assertAlmostEqual(self.control.value, value - 0.0000125, places=9, msg="视觉位移不能混进真实输入增量")
        for _ in range(60):
            self.control._animate(1 / 60)
        self.assertLess(self.control._offset_x.value, -1)
        self.assertGreaterEqual(self.control._offset_x.value, -2)
        self.mouse(QEvent.MouseButtonRelease, 3.999875)
        for _ in range(60):
            self.control._animate(1 / 60)
        self.assertGreater(self.control._offset_x.value, 0, "松开回到指针位置对应的悬停偏向")
        self.control.leaveEvent(QEvent(QEvent.Leave))
        for _ in range(60):
            self.control._animate(1 / 60)
        self.assertAlmostEqual(self.control._offset_x.value, 0)
        self.assertAlmostEqual(self.control._offset_y.value, 0)
        self.assertAlmostEqual(self.control._hover.value, 0)

    @mock.patch("widget.sizecontrol.native.reduce_motion", return_value=True)
    def test_reduced_motion_retains_arrows_without_group_translation(self, _reduce_motion):
        self.control._hovered = True
        self.mouse(QEvent.MouseMove, 28)
        self.assertEqual(self.control._hover.value, 1)
        self.assertEqual(self.control._offset_x.value, 0)
        self.start_drag()
        self.assertEqual(self.control._offset_x.value, 0)
        self.assertEqual(self.control._offset_y.value, 0)

    def test_right_click_does_not_edit_or_adjust(self):
        self.mouse(QEvent.MouseButtonPress, 0, button=Qt.RightButton)
        self.mouse(QEvent.MouseButtonRelease, 10, button=Qt.RightButton)
        self.assertEqual(self.events, [])
        self.assertFalse(self.control.editor.isVisible())


if __name__ == "__main__":
    unittest.main()
