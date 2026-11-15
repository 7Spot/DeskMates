"""滚轮、触摸板 → 一步一步翻（widget/wheel.py：两种设备都是「一次动作换一只」）。拿造出来的 QWheelEvent 喂状态机，不开界面。
事件的样子照 macOS 上 Qt 给的写（见 wheel.py 开头）：带格的滚轮也带 pixelDelta；精确位移标 MouseEventSynthesizedBySystem、角度是像素的 2 倍；
有惯性时手指抬起那一下的 ScrollEnd 常被吞掉。时间戳从 1000 起（0 = 没有时间戳，状态机改看现在的钟）。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

from widget import wheel
from widget.wheel import WheelSteps, is_notch, notches


def event(pixel=(0, 0), angle=None, phase=Qt.NoScrollPhase, t=0, precise=True) -> QWheelEvent:
    """一个滚动事件。precise：精确位移（触摸板、平滑滚动的鼠标），角度默认 = 2 × 像素；带格的滚轮传 precise=False 和 angle。"""
    px = QPoint(*pixel)
    ang = QPoint(*angle) if angle is not None else px * 2
    e = QWheelEvent(QPointF(10, 10), QPointF(10, 10), px, ang, Qt.NoButton, Qt.NoModifier, phase, False,
                    Qt.MouseEventSynthesizedBySystem if precise else Qt.MouseEventNotSynthesized)
    e.setTimestamp(t)
    return e


class WheelStepsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.steps = WheelSteps()

    def feed(self, *args, **kwargs) -> int:
        return self.steps.feed(event(*args, **kwargs))

    def test_a_notched_wheel_is_one_step_per_notch_even_though_it_carries_pixels(self):
        notch = event(angle=(0, -120), precise=False)
        self.assertTrue(is_notch(notch))
        self.assertEqual(notches(notch), 1, "往下一格：往后一步")
        self.assertTrue(is_notch(event(pixel=(0, -20), angle=(0, -120), precise=False)), "macOS 上带格的也带 pixelDelta（一行 20 像素）：不能拿它来分")
        self.assertFalse(is_notch(event(pixel=(0, -60))), "精确位移的角度正好 -120 也不是一格")
        self.assertFalse(is_notch(event(angle=(0, -40), precise=False)), "不是整格（别的平台的细格滚轮）：当精确位移攒")
        self.assertFalse(is_notch(event(pixel=(0, -10), phase=Qt.ScrollUpdate, precise=False)), "带滚动阶段的是触摸板")
        self.assertEqual(self.feed(angle=(0, -120), precise=False), 1)
        self.assertEqual(self.feed(pixel=(0, -20), angle=(0, -120), precise=False, t=1008), 1, "转快了也是一格一步，不并成一次")
        self.assertEqual(self.feed(angle=(0, 120), precise=False, t=1016), -1, "往上：往前")
        self.assertEqual(self.feed(angle=(120, 0), precise=False, t=1024), -1, "往右（横着的滚轮）：往前")
        self.assertEqual(self.feed(angle=(0, 240), precise=False, t=1032), -2, "一个事件里两格")

    def test_a_smooth_scrolling_mouse_turns_one_step_per_burst(self):
        """MX Master 3S + Logi Options+：一格给的是一串连续的小位移（没有滚动阶段）。一串攒到 20 像素翻一步，剩下的不要；停 0.15 秒才算下一格。"""
        burst = (-3, -6, -9, -8, -6, -4, -2, -1)                       # 一格 39 像素，8 毫秒一个

        def spin(t0: int) -> list:
            return [self.feed(pixel=(0, d), t=t0 + 8 * i) for i, d in enumerate(burst)]
        one = [0, 0, 0, 1, 0, 0, 0, 0]
        self.assertEqual(spin(1000), one, "攒到第 4 个（26 像素）翻一步，这一串剩下的不算")
        self.assertEqual(spin(1056 + 140), [0] * 8, "离上一串只停了 0.14 秒：还是同一次")
        self.assertEqual(spin(1252 + 160), one, "停够 0.15 秒：下一格")

    def test_one_long_spin_is_one_step_and_tiny_ones_never_add_up(self):
        got = [self.feed(pixel=(0, -10), t=1000 + 10 * i) for i in range(40)]
        self.assertEqual(sum(got), 1, "一直转（中间没停够 0.15 秒）：一次动作，一步")
        self.assertEqual(self.feed(pixel=(0, -60), t=2000) + self.feed(pixel=(0, -60), t=2008), 1, "精确位移 60 像素（角度 -120）：一步，不是两格")
        self.assertEqual(self.feed(pixel=(0, -15), t=3000), 0)
        self.assertEqual(self.feed(pixel=(0, -10), t=3160), 0, "两次各不到 20 像素：攒的不带到下一次")
        self.assertEqual(self.feed(pixel=(25, 0), t=3600), -1, "横着也算：往右是往前")
        self.assertEqual(self.feed(pixel=(-14, -15), t=4000), 0)
        self.assertEqual(self.feed(pixel=(-14, 0), t=4008), 1, "横竖分开攒，大的那边说了算（横 -28、竖 -15）")

    def test_one_trackpad_swipe_is_one_step_and_its_momentum_never_adds_one(self):
        t = 1000
        self.assertEqual(self.feed(phase=Qt.ScrollBegin, t=t), 0, "手指放上去：不算在动")
        self.assertEqual(self.feed(pixel=(-8, 1), phase=Qt.ScrollUpdate, t=t + 8), 0)
        self.assertEqual(self.feed(pixel=(-10, 0), phase=Qt.ScrollUpdate, t=t + 16), 0, "不跟着手指走：不到 20 像素不动")
        self.assertEqual(self.feed(pixel=(-12, -2), phase=Qt.ScrollUpdate, t=t + 24), 1, "攒到 30：翻一步")
        later = [self.feed(pixel=(d, 0), phase=Qt.ScrollUpdate, t=t + 32 + 8 * i) for i, d in enumerate((-40, -60, -70))]
        later.append(self.feed(pixel=(-60, 0), phase=Qt.ScrollUpdate, t=t + 64))   # 惯性的第一个报成 ScrollUpdate，前面的 ScrollEnd 被吞了
        for i, d in enumerate((-50, -30, -18, -9, -4, -1, 0, 0)):
            later.append(self.feed(pixel=(d, 0), phase=Qt.ScrollMomentum, t=t + 80 + 16 * i))
        later.append(self.feed(phase=Qt.ScrollEnd, t=t + 220))
        self.assertEqual(later, [0] * len(later), "这一下剩下的、松手后的惯性都不再翻")
        self.assertEqual(self.feed(pixel=(-40, 0), phase=Qt.ScrollMomentum, t=t + 620), 0, "停了一会儿才到的惯性：开不了新的一次")
        t = 3000
        self.feed(phase=Qt.ScrollBegin, t=t)
        self.assertEqual(self.feed(pixel=(30, 0), phase=Qt.ScrollUpdate, t=t + 8), -1, "往右：往前")
        tail = [self.feed(phase=Qt.ScrollEnd, t=t + 16), self.feed(pixel=(40, 0), phase=Qt.ScrollUpdate, t=t + 24),
                self.feed(pixel=(30, 0), phase=Qt.ScrollMomentum, t=t + 40), self.feed(phase=Qt.ScrollEnd, t=t + 56)]
        self.assertEqual(tail, [0, 0, 0, 0], "早到的 ScrollEnd 后面跟着的惯性：还是这一次的")
        self.feed(phase=Qt.ScrollBegin, t=t + 80)
        self.assertEqual(self.feed(pixel=(0, -30), phase=Qt.ScrollUpdate, t=t + 88), 1, "手指重新放上去（只隔 24 毫秒）：新的一次；竖着也算")
        self.assertEqual(self.feed(pixel=(0, -5), phase=Qt.ScrollUpdate, t=t + 96), 0)
        self.assertEqual(self.feed(phase=Qt.ScrollUpdate, t=t + 200), 0, "手指按着不动（位移 0）：不续这一次的命")
        self.assertEqual(self.feed(pixel=(0, -25), phase=Qt.ScrollUpdate, t=t + 256), 1, "停了 0.16 秒没有位移：慢慢滑的下一次")

    def test_momentum_can_finish_a_swipe_that_had_not_stepped_yet(self):
        self.feed(phase=Qt.ScrollBegin, t=1000)
        self.assertEqual(self.feed(pixel=(-12, 0), phase=Qt.ScrollUpdate, t=1008), 0)
        self.assertEqual(self.feed(pixel=(-12, 0), phase=Qt.ScrollMomentum, t=1024), 1, "轻轻一甩、大半靠惯性：还是一次有意的动作")
        self.assertEqual(self.feed(pixel=(-30, 0), phase=Qt.ScrollMomentum, t=1040), 0)

    def test_gestures_are_split_by_the_events_own_time_not_by_when_they_arrive(self):
        """主线程卡了一下（量到过 270 毫秒）、事件挤在一起到：按事件自己的时间戳，还是一次。时间戳是 0 才看现在的钟。"""
        self.assertEqual(self.feed(pixel=(0, -15), t=1000), 0)
        with mock.patch.object(wheel.time, "monotonic", return_value=99.0):    # 钟走了很久，时间戳没有
            self.assertEqual(self.feed(pixel=(0, -15), t=1010), 1, "按时间戳只隔 10 毫秒：同一次，攒满 30 翻一步")
        clock = [5.0]
        with mock.patch.object(wheel.time, "monotonic", side_effect=lambda: clock[0]):
            fresh = WheelSteps()
            self.assertEqual(fresh.feed(event(pixel=(0, -15))), 0)
            clock[0] += 0.01
            self.assertEqual(fresh.feed(event(pixel=(0, -15))), 1, "没有时间戳：看现在的钟，10 毫秒以内同一次")
            clock[0] += 0.2
            self.assertEqual(fresh.feed(event(pixel=(0, -25))), 1, "停了 0.2 秒：下一次")

    def test_reset_forgets_the_swipe_in_progress(self):
        self.assertEqual(self.feed(pixel=(0, -30), t=1000), 1)
        self.steps.reset()
        self.assertEqual(self.feed(pixel=(0, -30), t=1010), 1, "从头算（进详情页、藏起来）：剩下的惯性不再挡着下一次")


if __name__ == "__main__":
    unittest.main()
