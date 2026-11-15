"""粗调轨道沿用原生浮点输入；紧凑图标仍共用居中几何和动效。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from widget import pointer
from widget.sizecontrol import SizeScrubber
from widget.widgets import FineSlider, MotionButton


class SliderPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.slider = FineSlider(30, 400)
        self.slider.setFixedWidth(160)
        self.slider.set_value(137.123456789)
        self.slider.show()
        self.app.processEvents()
        self.events = []
        self.slider.adjustmentStarted.connect(lambda: self.events.append("start"))
        self.slider.valueChanged.connect(lambda value: self.events.append(value))
        self.slider.adjustmentFinished.connect(lambda: self.events.append("finish"))
        self.start_x = self.slider._thumb_x() + 4.75
        self.origin = QPointF(4096.125, 712.5)

    def tearDown(self):
        self.slider.hide()
        self.slider.deleteLater()
        self.app.processEvents()

    def event(self, kind, dx=0.0, timestamp=12000):
        point = QPointF(self.start_x + dx, 15)
        event = QMouseEvent(kind, point, self.origin + QPointF(dx, 0), Qt.LeftButton,
                            Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton, Qt.NoModifier)
        event.setTimestamp(timestamp)
        return event

    def test_qt_fractional_drag_keeps_grab_offset_and_does_not_round_on_release(self):
        value = self.slider.value
        self.slider.mousePressEvent(self.event(QEvent.MouseButtonPress))
        self.assertAlmostEqual(self.slider.value, value, places=11, msg="抓圆钮偏右处不跳到鼠标中心")
        for n in range(1, 11):
            self.slider.mouseMoveEvent(self.event(QEvent.MouseMove, n * 0.000125))
            self.assertAlmostEqual(self.slider.value, value + n * 0.000125 * 370 / 138, places=9)
        before_release = self.slider.value
        self.slider.mouseReleaseEvent(self.event(QEvent.MouseButtonRelease, 0.00125))
        self.assertEqual(self.slider.value, before_release)
        values = [value for value in self.events if isinstance(value, float)]
        self.assertTrue(all(b > a for a, b in zip(values, values[1:])), "每个细小输入都直接更新，没有固定步长")
        self.assertEqual(self.events.count("start"), 1)
        self.assertEqual(self.events.count("finish"), 1)

    def test_native_small_moves_and_native_release_preserve_the_final_fraction(self):
        drag = self.slider._pointer_drag
        press = self.event(QEvent.MouseButtonPress)
        sample = pointer._Sample(1, 77, 12.0, 1, 1690.125, 739.25)
        with mock.patch.object(pointer.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(pointer.native, "_nsapp", return_value=1), \
                mock.patch.object(pointer.native, "_msg_send", return_value=77), \
                mock.patch.object(pointer, "_sample", return_value=sample):
            self.slider.mousePressEvent(press)
        self.assertTrue(drag._active)
        value = self.slider.value
        for n in range(1, 11):
            move = pointer._Sample(6, 77, 12 + n * .002, n + 1, sample.x + n * .000125, sample.y)
            with mock.patch.object(pointer, "_sample", return_value=move):
                drag.nativeEventFilter(b"mac_generic_NSEvent", 99)
            self.assertAlmostEqual(self.slider.value, value + n * .000125 * 370 / 138, places=9)
        final = pointer._Sample(2, 77, 12.04, 20, sample.x + .001375, sample.y)
        # 故意让Qt松手位置停在旧点，验证真正的原生MouseUp小数不会被抹掉。
        with mock.patch.object(pointer.native, "_nsapp", return_value=1), \
                mock.patch.object(pointer.native, "_msg_send", return_value=77), \
                mock.patch.object(pointer, "_sample", return_value=final):
            self.slider.mouseReleaseEvent(self.event(QEvent.MouseButtonRelease, 0, timestamp=12040))
        self.assertAlmostEqual(self.slider.value, value + .001375 * 370 / 138, places=9)
        self.assertFalse(drag._active)
        self.assertFalse(self.slider.adjusting)
        self.assertEqual(self.events.count("finish"), 1)

    def test_cancel_stops_drag_once_and_later_moves_cannot_change_value(self):
        for cancel in (lambda: self.slider.hide(), lambda: self.slider.setEnabled(False),
                       lambda: self.app.sendEvent(self.slider, QEvent(QEvent.UngrabMouse))):
            self.slider.setEnabled(True)
            self.slider.show()
            self.slider.mousePressEvent(self.event(QEvent.MouseButtonPress))
            self.slider.mouseMoveEvent(self.event(QEvent.MouseMove, .25))
            value, before = self.slider.value, self.events.count("finish")
            cancel()
            self.assertFalse(self.slider._pointer_drag._active)
            self.slider.mouseMoveEvent(self.event(QEvent.MouseMove, 15))
            self.slider.mouseReleaseEvent(self.event(QEvent.MouseButtonRelease, 15))
            self.assertEqual(self.slider.value, value)
            self.assertEqual(self.events.count("finish"), before + 1)

    def test_arrow_ink_is_centered_and_shares_the_capsules_transform(self):
        button = MotionButton(symbol="forward")
        button.setFixedSize(30, 30)
        try:
            with mock.patch("widget.motion.native.reduce_motion", return_value=False):
                for hover, press, x, y in ((0, 0, 0, 0), (1, 0, 1, -1), (1, 1, -1, 1)):
                    for spring, value in ((button.motion.hover, hover), (button.motion.press, press),
                                          (button.motion.direction_x, x), (button.motion.direction_y, y)):
                        spring.set_target(value, instant=True)
                    image = QImage(120, 120, QImage.Format_ARGB32_Premultiplied)
                    image.setDevicePixelRatio(4)
                    image.fill(Qt.transparent)
                    painter = QPainter(image)
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setTransform(button.motion.transform())
                    button.paint_content(painter, button.motion.content_rect(), QColor("black"))
                    painter.end()
                    pixels = [(px, py) for py in range(120) for px in range(120) if image.pixelColor(px, py).alpha()]
                    ink = QRectF(min(px for px, _ in pixels) / 4, min(py for _, py in pixels) / 4,
                                 (max(px for px, _ in pixels) - min(px for px, _ in pixels) + 1) / 4,
                                 (max(py for _, py in pixels) - min(py for _, py in pixels) + 1) / 4)
                    center = button.motion.transform().map(button.motion.content_rect().center())
                    self.assertAlmostEqual(ink.center().x(), center.x(), delta=.26)
                    self.assertAlmostEqual(ink.center().y(), center.y(), delta=.26)
        finally:
            button.deleteLater()

    def test_number_width_reserves_arrows_for_wider_ranges_without_changing_precision(self):
        control = SizeScrubber(lo=0, hi=100000)
        try:
            control.ensurePolished()
            self.assertGreater(control.width(), 56)
            control.set_value(99999.875)
            self.assertEqual(control.value, 99999.875)
            self.assertEqual(control.text(), "100000%")
            self.assertGreater(control.editor.width(), 40)
        finally:
            control.deleteLater()


if __name__ == "__main__":
    unittest.main()
