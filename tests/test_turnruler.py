"""没有头的转盘刻度尺（widget/turnruler.py，看细节那一行左边那条）的输入契约：拖跟手、滚轮一格一步、触摸板跟着位移走、松手后的惯性不要、
方向键一格、Esc 交给卡片、每过一根刻度 tick 一声（和大小滑杆共用上限）。不用狗的模型、不开真窗口。
滚动事件的样子照 macOS 上 Qt 给的写（见 widget/wheel.py 开头）：带格的滚轮也带 pixelDelta；精确位移标 MouseEventSynthesizedBySystem。"""
import math
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication

from widget import native, sounds
from widget.turnruler import DEG_PER_PX, STEP_DEG, SWIPE_DEG_PER_PX, TurnRuler


def wheel(pixel=(0, 0), angle=None, phase=Qt.NoScrollPhase, precise=True) -> QWheelEvent:
    px = QPoint(*pixel)
    ang = QPoint(*angle) if angle is not None else px * 2
    return QWheelEvent(QPointF(10, 10), QPointF(10, 10), px, ang, Qt.NoButton, Qt.NoModifier, phase, False,
                       Qt.MouseEventSynthesizedBySystem if precise else Qt.MouseEventNotSynthesized)


class TurnRulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.enterContext(mock.patch.object(sounds, "_enabled", False))   # 声音单独测（最后一条）
        self.ruler = TurnRuler()
        self.ruler.resize(240, self.ruler.height())
        self.turns = []
        self.ruler.turned.connect(self.turns.append)

    def tearDown(self):
        self.ruler.close()
        self.ruler.deleteLater()
        self.app.processEvents()

    def mouse(self, kind, x, button=Qt.LeftButton):
        p = QPointF(x, self.ruler.height() / 2)
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else button
        event = QMouseEvent(kind, p, QPointF(self.ruler.mapToGlobal(p.toPoint())), button, buttons, Qt.NoModifier)
        {QEvent.MouseButtonPress: self.ruler.mousePressEvent,
         QEvent.MouseButtonDblClick: self.ruler.mouseDoubleClickEvent,
         QEvent.MouseMove: self.ruler.mouseMoveEvent,
         QEvent.MouseButtonRelease: self.ruler.mouseReleaseEvent}[kind](event)
        return event

    def test_dragging_follows_the_pointer_at_one_and_a_half_degrees_a_pixel(self):
        """刻度跟着手走：往右拖 10 像素转 15°（刻度往右，狗靠近你的那面往右），再往左拖 20 像素转回 30°。松手就停，后面不再转。"""
        self.assertEqual(DEG_PER_PX, 1.5)
        self.mouse(QEvent.MouseButtonPress, 50)
        self.assertTrue(self.ruler.adjusting)
        self.mouse(QEvent.MouseMove, 60)
        self.mouse(QEvent.MouseMove, 40)
        self.mouse(QEvent.MouseButtonRelease, 40)
        self.assertEqual(self.turns, [15.0, -30.0])
        self.assertAlmostEqual(self.ruler.angle, -15.0)
        self.assertFalse(self.ruler.adjusting)
        self.mouse(QEvent.MouseMove, 90)
        self.assertEqual(len(self.turns), 2, "松手了：鼠标再动不转（没有惯性，也不跟着悬停转）")

    def test_a_click_without_moving_does_not_turn(self):
        """拖是相对的：点哪都不转（不是点哪转到哪）；连点的第二下 Qt 报成双击，也当一次按下。"""
        self.mouse(QEvent.MouseButtonPress, 30)
        self.mouse(QEvent.MouseButtonRelease, 30)
        self.mouse(QEvent.MouseButtonDblClick, 200)
        self.assertTrue(self.ruler.adjusting, "双击那一下也开始拖")
        self.mouse(QEvent.MouseButtonRelease, 200)
        self.assertEqual(self.turns, [])
        self.mouse(QEvent.MouseButtonPress, 30, button=Qt.RightButton)
        self.assertFalse(self.ruler.adjusting, "右键不拖")

    def test_a_notched_wheel_turns_one_step_and_a_continuous_stream_follows_the_pixels(self):
        """带格的滚轮一格 15°（macOS 上它也带 pixelDelta，不能拿这个分，wheel.is_notch）；往下 = 刻度往左，和「我的同桌」滑动条一个方向。
        连续的位移（触摸板、开着平滑滚动的鼠标）按位移走：平滑滚动的鼠标一格约 39 像素 ≈ 一格刻度。松手后系统补的惯性不要。"""
        r = self.ruler
        r.wheelEvent(wheel(pixel=(0, -20), angle=(0, -120), precise=False))
        r.wheelEvent(wheel(angle=(0, 120), precise=False))
        r.wheelEvent(wheel(angle=(120, 0), precise=False))
        self.assertEqual(self.turns, [-STEP_DEG, STEP_DEG, STEP_DEG], "往下一格往左、往上一格往右、横着往右一格往右")
        self.turns.clear()
        r.wheelEvent(wheel(pixel=(8, 0), phase=Qt.ScrollUpdate))
        r.wheelEvent(wheel(pixel=(0, -39)))
        self.assertEqual([round(d, 6) for d in self.turns], [round(8 * SWIPE_DEG_PER_PX, 6), round(-39 * SWIPE_DEG_PER_PX, 6)])
        self.assertLess(abs(-39 * SWIPE_DEG_PER_PX + STEP_DEG), 2.0, "平滑滚动的一格和带格的一格差不多")
        self.turns.clear()
        r.wheelEvent(wheel(pixel=(-40, 0), phase=Qt.ScrollMomentum))
        r.wheelEvent(wheel(pixel=(0, 0), phase=Qt.ScrollEnd))
        self.assertEqual(self.turns, [], "惯性、手指抬起都不转")
        event = wheel(pixel=(5, 0), phase=Qt.ScrollUpdate)
        r.wheelEvent(event)
        self.assertTrue(event.isAccepted(), "滚动不漏到卡片上")

    def test_arrow_keys_turn_one_step_and_other_keys_go_to_the_card(self):
        r = self.ruler
        for key in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            r.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
        self.assertEqual(self.turns, [-STEP_DEG, -STEP_DEG, STEP_DEG, STEP_DEG])
        esc = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        r.keyPressEvent(esc)
        self.assertFalse(esc.isAccepted(), "Esc 交给卡片（关卡片）")

    def test_set_angle_does_not_emit_and_a_drag_ends_when_hidden_or_disabled(self):
        r = self.ruler
        r.set_angle(123.0)
        r.set_angle(float("nan"))
        self.assertEqual((r.angle, self.turns), (123.0, []))
        r.show()
        self.mouse(QEvent.MouseButtonPress, 50)
        r.hide()
        self.assertFalse(r.adjusting, "藏起来（换页）就松开")
        r.show()
        self.mouse(QEvent.MouseButtonPress, 50)
        r.setEnabled(False)
        self.assertFalse(r.adjusting, "按不了了也松开")
        self.mouse(QEvent.MouseButtonPress, 50)
        self.assertFalse(r.adjusting)
        self.assertEqual(r.cursor().shape(), Qt.PointingHandCursor, "和大小滑杆一样的手（左右双箭头是「拉宽」）")

    def test_it_paints_at_any_angle_and_the_ticks_move_with_the_angle(self):
        """没有头：转多少圈都画得出来；角度变了刻度跟着挪（往右）。"""
        r = self.ruler
        r.resize(240, r.height())

        def ink_columns(angle):
            """槽里比底色明显深的那些列（刻度），正中那根线不算。"""
            r.set_angle(angle)
            img = QImage(r.size(), QImage.Format_ARGB32)
            img.fill(0)
            r.render(img)
            cy = r.height() // 2 + 2
            reds = [img.pixelColor(x, cy).red() for x in range(r.width())]
            fill = sorted(reds[30:-30])[len(reds[30:-30]) // 2]          # 大多数列是槽的底色
            return [x for x in range(30, r.width() - 30) if abs(x - r.width() / 2) > 4 and reds[x] < fill - 25]
        for angle in (0.0, 1e6, -1e6):
            self.assertTrue(ink_columns(angle), f"{angle}° 也画得出刻度")
        a, b = ink_columns(0.0), ink_columns(STEP_DEG / 3)
        shift = STEP_DEG / 3 / DEG_PER_PX
        self.assertTrue(any(abs((x + shift) - y) <= 1.0 for x in a for y in b), "转了 5°，刻度往右挪 3.3 像素")

    def test_one_tick_per_step_sharing_the_size_slider_limit(self):
        """每过一根刻度（15° 的整数倍）tick 一声；和大小滑杆共用 20 次 / 秒的上限：太密的直接不响，不叠音、不补播。"""
        now = [10.0]
        played = []
        with mock.patch.object(sounds, "_enabled", True), mock.patch.object(sounds, "_last_size_tick", -math.inf), \
                mock.patch("widget.capture_ui._frozen", False), mock.patch.object(sounds.time, "monotonic", side_effect=lambda: now[0]), \
                mock.patch.object(native, "play_sound", side_effect=lambda f, g=1: played.append(Path(f).stem) or True):
            r = self.ruler
            r._turn(14.0)
            self.assertEqual(played, [], "没过刻度")
            r._turn(2.0)
            self.assertEqual(played, ["tick"], "过了 15°")
            now[0] += 0.02
            r._turn(15.0)
            self.assertEqual(played, ["tick"], "50 毫秒内又过一根：不响")
            now[0] += 0.05
            r._turn(-20.0)
            self.assertEqual(played, ["tick", "tick"], "往回转过刻度也响")
            sounds.size_changed(100.2, 101.4)
            self.assertEqual(len(played), 2, "大小滑杆紧跟着也被同一个上限挡住")


if __name__ == "__main__":
    unittest.main()
