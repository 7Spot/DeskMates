"""更新行的展示回归：原生焦点框、版本字体、右对齐和换字时的稳定布局。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

from widget import native, sticker
from widget.animation import FrameClock
from widget.updatestatus import UpdateStatus


class PresentationHost(QWidget):
    def __init__(self):
        super().__init__()
        self.animators = set()

    def run_animator(self, animator):
        self.animators.add(animator)
        return True


class UpdateStatusPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host_patch = mock.patch.object(FrameClock, "default_host", None)
        self.host_patch.start()
        self.reduce_patch = mock.patch.object(native, "reduce_motion", return_value=False)
        self.reduce_patch.start()
        self.host = PresentationHost()
        self.host.setStyleSheet(sticker.stylesheet(sticker.theme()))
        self.host.setFixedSize(300, 50)
        row = QHBoxLayout(self.host)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(6)
        self.version = QLabel("Version 0.5.5 (38)")
        self.version.setProperty("muted", True)
        row.addWidget(self.version)
        self.button = UpdateStatus()
        self.button.set_status("Check for updates", True, animated=False)
        row.addWidget(self.button, 1)
        self.host.show()
        self.app.processEvents()
        self.host.setFocus()
        QTest.mouseMove(self.host, QPoint(1, 1))
        self.button.motion.cancel(instant=True)

    def tearDown(self):
        self.host.hide()
        self.button.motion.clock.stop()
        self.host.deleteLater()
        self.app.processEvents()
        self.reduce_patch.stop()
        self.host_patch.stop()

    def test_version_and_status_keep_the_same_font_after_style_and_state_changes(self):
        for text, clickable in (("Check for updates", True), ("正在检查…", False), ("检查失败 · 重试", True)):
            self.host.setStyleSheet(sticker.stylesheet(sticker.theme()))
            self.button.set_status(text, clickable, animated=False)
            self.app.processEvents()
            with self.subTest(text=text):
                self.assertEqual(self.button.font().pixelSize(), 12)
                self.assertEqual(self.button.font().weight(), 400)
                self.assertEqual(self.button.font(), self.version.font())

    def test_mouse_focus_does_not_restore_native_rectangle_when_checking_starts(self):
        clicks = []

        def check():
            clicks.append(True)
            self.button.set_status("Checking…", False)

        self.button.clicked.connect(check)
        QTest.mouseClick(self.button, Qt.LeftButton)
        self.assertEqual(clicks, [True])
        self.assertFalse(self.button.testAttribute(Qt.WA_MacShowFocusRect))
        self.assertFalse(self.button._keyboard_focus)
        self.assertEqual(self.button.focusPolicy(), Qt.NoFocus)
        self.button.click()
        QTest.keyClick(self.button, Qt.Key_Space)
        self.assertEqual(clicks, [True], "检查中不能再次派发旧按钮动作")
        self.button.set_status("Offline · retry", True)
        self.assertEqual(self.button.focusPolicy(), Qt.StrongFocus)
        self.assertFalse(self.button.testAttribute(Qt.WA_MacShowFocusRect))

    def test_keyboard_focus_reuses_the_capsule_border_and_keeps_space_activation(self):
        clicks = []
        self.button.clicked.connect(lambda: clicks.append(True))
        self.button.setFocus(Qt.TabFocusReason)
        self.app.processEvents()
        self.assertTrue(self.button.hasFocus())
        self.assertTrue(self.button._keyboard_focus)
        self.assertEqual(self.button.surface_colors()[1], QColor(sticker.blue()))
        self.assertFalse(self.button.testAttribute(Qt.WA_MacShowFocusRect))
        QTest.keyClick(self.button, Qt.Key_Space)
        self.assertEqual(clicks, [True])
        QTest.mouseClick(self.button, Qt.LeftButton)
        self.assertFalse(self.button._keyboard_focus, "鼠标点击不保留键盘专用描边")
        self.assertEqual(clicks, [True, True])

    def test_text_pixels_match_a_right_aligned_version_label_in_both_languages(self):
        """逐像素比较QLabel，防止绘字中心/基线和左侧版本号又走两套公式。"""
        reference = QLabel(self.host)
        reference.setProperty("muted", True)
        reference.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        reference.setContentsMargins(self.button.TEXT_INSET, 0, self.button.TEXT_INSET, 0)
        reference.setStyleSheet("color: #345678; background: transparent;")
        reference.resize(self.button.size())
        reference.ensurePolished()
        for text in ("Check for updates", "检查更新"):
            self.button.set_status(text, True, animated=False)
            reference.setText(text)
            expected = QImage(reference.size(), QImage.Format_ARGB32_Premultiplied)
            expected.fill(Qt.transparent)
            reference.render(expected, QPoint(), QRegion(), QWidget.DrawChildren)
            actual = QImage(self.button.size(), QImage.Format_ARGB32_Premultiplied)
            actual.fill(Qt.transparent)
            painter = QPainter(actual)
            self.button.paint_content(painter, QRectF(self.button.rect()), QColor("#345678"))
            painter.end()
            with self.subTest(text=text):
                self.assertEqual(actual, expected, "更新字的字号、基线和右侧留白须与QLabel一致")

    def test_retargeting_text_preserves_layout_and_continuous_fade(self):
        geometry = self.button.geometry()
        version_geometry = self.version.geometry()
        self.button.set_status("Checking…", False)
        self.button.tick(.04)
        opacity = self.button._text_opacity
        self.assertGreater(opacity, 0)
        self.assertLess(opacity, 1)
        self.button.set_status("Connection unavailable · retry", True)
        self.assertEqual(self.button._text_opacity, opacity, "换字不能将已有淡出重置为不透明")
        self.button.tick(.3)
        self.app.processEvents()
        self.assertEqual(self.button.geometry(), geometry)
        self.assertEqual(self.version.geometry(), version_geometry)
        self.assertEqual(self.button._display_text, "Connection unavailable · retry")
        self.assertEqual(self.button._text_opacity, 1)
        self.assertIsNone(self.button.graphicsEffect())

    def test_capsule_wraps_visible_text_while_the_status_area_stays_fixed(self):
        geometry = self.button.geometry()
        for text in ("检查更新", "Check for updates", "很长的连接失败原因" * 20 + " · 重试"):
            self.button.set_status(text, True, animated=False)
            self.app.processEvents()
            rect = self.button.capsule_rect()
            width = QFontMetricsF(self.button.font()).horizontalAdvance(self.button._visible_text())
            with self.subTest(text=text[:20]):
                self.assertEqual(self.button.geometry(), geometry)
                self.assertEqual(rect.right(), self.button.width() - 2)
                self.assertEqual(rect.height(), 26)
                self.assertGreaterEqual(rect.width() - width, 16)
                self.assertLess(rect.width() - width, 17)
                self.assertLessEqual(rect.width(), self.button.width() - 4)
        self.assertIn("…", self.button._visible_text())
        self.assertEqual(self.button.text(), text, "只省略绘制内容，完整状态语义保留")

    def test_blank_status_area_does_not_hover_press_or_click(self):
        self.button.set_status("检查更新", True, animated=False)
        clicks = []
        self.button.clicked.connect(lambda: clicks.append(True))
        blank = QPoint(10, self.button.height() // 2)
        capsule = self.button.capsule_rect().center().toPoint()
        self.assertFalse(self.button.hitButton(blank))
        QTest.mouseMove(self.button, blank)
        self.assertEqual(self.button.motion.hover.target, 0)
        self.assertEqual(self.button.cursor().shape(), Qt.ArrowCursor)
        QTest.mouseClick(self.button, Qt.LeftButton, pos=blank)
        self.assertEqual(clicks, [])
        self.assertEqual(self.button.motion.press.target, 0)
        self.assertEqual(self.button.motion.direction_x.target, 0, "空白也不能带动磁吸方向")
        QTest.mouseMove(self.button, capsule)
        self.assertEqual(self.button.motion.hover.target, 1)
        self.assertEqual(self.button.cursor().shape(), Qt.PointingHandCursor)
        QTest.mouseClick(self.button, Qt.LeftButton, pos=capsule)
        self.assertEqual(clicks, [True])
        QTest.mouseMove(self.button, blank)
        self.assertEqual(self.button.motion.hover.target, 0)
        self.assertEqual(self.button.cursor().shape(), Qt.ArrowCursor)

    def test_hover_pixels_and_scaling_stay_around_the_small_capsule(self):
        self.button.set_status("检查更新", True, animated=False)
        rect = self.button.capsule_rect()
        self.button.motion.cancel(instant=True)
        before = self.host.grab().toImage()
        QTest.mouseMove(self.button, rect.center().toPoint())
        for _ in range(35):
            self.button.motion.tick(.01)
        after = self.host.grab().toImage()
        visual = self.button.motion.visual_rect()
        self.assertAlmostEqual(self.button.motion.scale, .975, places=4)
        self.assertAlmostEqual(visual.center().x(), rect.center().x(), delta=.1)
        self.assertAlmostEqual(visual.center().y(), rect.center().y(), delta=.1)
        changed = [(x, y) for y in range(after.height()) for x in range(after.width())
                   if before.pixel(x, y) != after.pixel(x, y)]
        self.assertTrue(changed)
        self.assertGreaterEqual(min(x for x, _ in changed), self.button.x() + int(rect.left()) - 1,
                                "版本号之后的空白区不应画出长胶囊")
        QTest.mousePress(self.button, Qt.LeftButton, pos=rect.center().toPoint())
        for _ in range(20):
            self.button.motion.tick(.01)
        self.assertAlmostEqual(self.button.motion.scale, .95, places=4)
        self.assertAlmostEqual(self.button.motion.visual_rect().center().x(), rect.center().x(), delta=.1)
        QTest.mouseRelease(self.button, Qt.LeftButton, pos=rect.center().toPoint())

    def test_capsule_tracks_displayed_text_and_keeps_right_edge_on_fast_retarget(self):
        self.button.set_status("检查更新", True, animated=False)
        initial = self.button.capsule_rect()
        geometry = self.button.geometry()
        self.button.set_status("Checking for updates…", False)
        self.button.tick(.04)
        self.assertEqual(self.button.capsule_rect(), initial, "旧字淡出时不能先套上新字的长胶囊")
        self.button.set_status("Update ready", True)
        self.button.tick(.3)
        self.assertEqual(self.button._display_text, "Update ready")
        self.assertEqual(self.button.capsule_rect().right(), initial.right())
        self.assertEqual(self.button.geometry(), geometry)
        self.assertEqual(self.button._text_opacity, 1)
        self.assertIsNone(self.button.graphicsEffect())


if __name__ == "__main__":
    unittest.main()
