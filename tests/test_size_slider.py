"""大小滑杆的输入契约：绝对跟手、保留抓取偏移和小数，不依赖狗模型或真正的桌面窗口。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from widget.widgets import FineSlider


class FineSliderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.slider = FineSlider(30, 400)
        self.events = []
        self.slider.adjustmentStarted.connect(lambda: self.events.append("start"))
        self.slider.valueChanged.connect(lambda value: self.events.append(("value", value)))
        self.slider.adjustmentFinished.connect(lambda: self.events.append("finish"))

    def tearDown(self):
        self.slider.close()
        self.slider.deleteLater()
        self.app.processEvents()

    def mouse(self, kind, x, *, button=Qt.LeftButton):
        p = QPointF(x, self.slider.height() / 2)
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
        event = QMouseEvent(kind, p, QPointF(self.slider.mapToGlobal(p.toPoint())), button, buttons, Qt.NoModifier)
        {QEvent.MouseButtonPress: self.slider.mousePressEvent,
         QEvent.MouseMove: self.slider.mouseMoveEvent,
         QEvent.MouseButtonRelease: self.slider.mouseReleaseEvent}[kind](event)

    def wheel(self, steps):
        p = QPointF(self.slider.rect().center())
        self.slider.wheelEvent(QWheelEvent(p, QPointF(self.slider.mapToGlobal(p.toPoint())), QPoint(),
                                          QPoint(0, steps * 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))

    def test_external_sync_preserves_precision_and_does_not_emit_user_changes(self):
        self.slider.set_value(123.4567)
        self.assertAlmostEqual(self.slider.value, 123.4567)
        self.slider.set_value(-20.0)
        self.assertEqual(self.slider.value, 30.0)
        self.slider.set_value(500.0)
        self.assertEqual(self.slider.value, 400.0)
        self.assertEqual(self.events, [], "同步和范围截取不是用户操作，不重进缩放回调")

    def test_clicking_the_track_sets_an_absolute_value_with_a_complete_adjustment(self):
        self.slider.set_value(30.0)
        mid = self.slider.width() / 2
        self.mouse(QEvent.MouseButtonPress, mid)
        self.assertAlmostEqual(self.slider.value, 215.0, msg="点轨道中央直接到范围中点")
        self.assertEqual(self.events[0], "start", "先固定缩放中心，再发送值")
        self.assertEqual(self.events[1], ("value", 215.0))
        self.assertIsInstance(self.events[1][1], float)
        self.mouse(QEvent.MouseButtonRelease, mid)
        self.assertEqual(self.events[-1], "finish")
        self.assertEqual(self.events.count("start"), 1)
        self.assertEqual(self.events.count("finish"), 1)

    def test_grabbing_off_centre_does_not_jump_and_preserves_the_pointer_offset(self):
        mid = self.slider.width() / 2
        self.slider.set_value(215.0)
        self.mouse(QEvent.MouseButtonPress, mid + 4)
        self.assertEqual(self.slider.value, 215.0, "按住钮的边缘不跳到鼠标坐标")
        self.mouse(QEvent.MouseMove, mid + 14)
        offset_value = self.slider.value
        self.mouse(QEvent.MouseButtonRelease, mid + 14)
        self.slider.set_value(215.0)
        self.mouse(QEvent.MouseButtonPress, mid)
        self.mouse(QEvent.MouseMove, mid + 10)
        self.mouse(QEvent.MouseButtonRelease, mid + 10)
        self.assertAlmostEqual(self.slider.value, offset_value, msg="抓取点不同，同样移动10像素仍得到同一个值")
        self.assertGreater(offset_value, 215.0)

    def test_drag_result_depends_on_position_not_drag_speed(self):
        mid = self.slider.width() / 2
        results = []
        for duration in (1.0, 0.001):
            self.slider.set_value(215.0)
            with mock.patch("widget.widgets.time.perf_counter", side_effect=[0.0, duration]):
                self.mouse(QEvent.MouseButtonPress, mid)
                self.mouse(QEvent.MouseMove, mid + 12)
                self.mouse(QEvent.MouseButtonRelease, mid + 12)
            results.append(self.slider.value)
        self.assertAlmostEqual(results[0], results[1], msg="同一位置不因拖得快而额外加速")

    def test_release_keeps_fractional_values_and_does_not_emit_a_rounding_jump(self):
        self.slider.set_value(215.0)
        mid = self.slider.width() / 2
        self.mouse(QEvent.MouseButtonPress, mid)
        self.mouse(QEvent.MouseMove, mid + 0.375)
        value = self.slider.value
        self.assertNotAlmostEqual(value, round(value), msg="拖动可停在小数百分比")
        changes = [event for event in self.events if isinstance(event, tuple)]
        self.mouse(QEvent.MouseButtonRelease, mid + 0.375)
        self.assertEqual(self.slider.value, value, "松手不取整")
        self.assertEqual([event for event in self.events if isinstance(event, tuple)], changes)

    def test_wheel_and_arrow_keys_step_one_percentage_point_without_losing_fraction(self):
        self.slider.set_value(100.25)
        self.wheel(1)
        self.assertAlmostEqual(self.slider.value, 101.25)
        self.wheel(-1)
        self.assertAlmostEqual(self.slider.value, 100.25)
        for key, expected in ((Qt.Key_Right, 101.25), (Qt.Key_Up, 102.25),
                              (Qt.Key_Left, 101.25), (Qt.Key_Down, 100.25)):
            self.slider.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
            self.assertAlmostEqual(self.slider.value, expected)
        self.assertNotEqual(self.slider.focusPolicy(), Qt.NoFocus, "方向键调整需要能取得键盘焦点")

    def test_drag_and_discrete_steps_stay_within_both_limits(self):
        self.slider.set_value(215.0)
        self.mouse(QEvent.MouseButtonPress, self.slider.width() / 2)
        self.mouse(QEvent.MouseMove, -100)
        self.assertEqual(self.slider.value, 30.0)
        self.mouse(QEvent.MouseMove, self.slider.width() + 100)
        self.assertEqual(self.slider.value, 400.0)
        self.mouse(QEvent.MouseButtonRelease, self.slider.width() + 100)
        self.wheel(1)
        self.assertEqual(self.slider.value, 400.0)
        self.slider.set_value(30.0)
        self.slider.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
        self.assertEqual(self.slider.value, 30.0)

    def test_right_click_does_not_start_or_change_an_adjustment(self):
        self.slider.set_value(100.25)
        self.mouse(QEvent.MouseButtonPress, self.slider.width() / 2, button=Qt.RightButton)
        self.mouse(QEvent.MouseButtonRelease, self.slider.width() / 2, button=Qt.RightButton)
        self.assertEqual(self.slider.value, 100.25)
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
