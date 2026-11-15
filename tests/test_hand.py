"""手有多快（widget/hand.py）：按系统给事件打的时间算，程序卡了也算得准。数字来自 真实录制。"""
import time
import unittest
from types import SimpleNamespace

from widget import hand


def line(*points):
    return [(t / 1000.0, x, 0.0) for t, x in points]


class VelocityTests(unittest.TestCase):
    def test_steady_motion(self):
        samples = line(*[(t, t * 10.0) for t in range(0, 200, 8)])      # 每毫秒 10 像素 = 每秒 1 万像素
        vx, vy = hand.velocity(samples, 0.192, 0.08)
        self.assertAlmostEqual(vx, 10000.0, delta=1100.0)
        self.assertEqual(vy, 0.0)

    def test_a_late_release_still_counts_as_moving(self):
        """卡了 400 毫秒才处理到松手：只要事件时间连着，手就没停（算成 0 的话狗当场掉）。"""
        samples = line((0, 0.0), (15, 150.0), (30, 300.0), (45, 450.0), (60, 600.0))
        vx, _ = hand.velocity(samples, 0.088, 0.08)                      # 松手比最后一次移动晚 28 毫秒
        self.assertGreater(vx, 5000.0)

    def test_merged_events_do_not_read_as_an_absurd_speed(self):
        """系统把排队的移动合并：位置是这批最后的，时间戳是这批最早的。录到 820 像素隔 15 毫秒，按单个事件算每秒 5 万多像素。"""
        samples = line((0, 0.0), (15, 41.0), (30, 155.0), (46, 240.0), (54, 423.0), (69, 1243.0), (121, 1820.0))
        vx, _ = hand.velocity(samples, 0.160, 0.08)                      # 真实手速约每秒 1.5 万
        self.assertLess(vx, 25000.0)
        self.assertGreater(vx, 10000.0)

    def test_a_burst_of_late_events_is_not_a_huge_speed(self):
        """卡完事件一口气进来：程序看到的间隔只有几微秒（算出过每秒 49 万像素），系统的时间戳还是分开的。"""
        samples = line((0, 0.0), (16, 250.0), (32, 500.0), (48, 750.0))
        vx, _ = hand.velocity(samples, 0.056, 0.08)
        self.assertLess(vx, 20000.0)

    def test_a_hand_that_stopped_before_letting_go_is_not_a_throw(self):
        samples = line((0, 0.0), (8, 80.0), (16, 160.0), (24, 161.0))
        vx, _ = hand.velocity(samples, 0.400, 0.08)
        self.assertLess(abs(vx), 100.0)

    def test_not_enough_samples(self):
        self.assertEqual(hand.velocity([], 1.0, 0.08), (0.0, 0.0))
        self.assertEqual(hand.velocity(line((0, 5.0)), 1.0, 0.08), (0.0, 0.0))

    def test_a_short_drag_counts_from_the_press(self):
        """按下到松手不到一个取样窗口：从按下算起。"""
        vx, _ = hand.velocity(line((0, 0.0), (10, 100.0)), 0.020, 0.08)
        self.assertAlmostEqual(vx, 5000.0, delta=1.0)

    def test_the_release_event_itself_adds_no_distance(self):
        """松手事件也记一个样本（位置和最后一次移动一样），时间就是 end：速度不变。"""
        vx, _ = hand.velocity([(0.0, 0.0, 0.0), (0.05, 75.0, 0.0), (0.05, 75.0, 0.0)], 0.05, 0.08)
        self.assertAlmostEqual(vx, 1500.0, delta=1.0)

    def test_samples_read_once_a_frame_are_not_overcounted(self):
        """粘在光标上的球每帧读一次鼠标，end 就是最后一个样本：一帧 40 像素、16 毫秒 = 每秒 2500 像素。"""
        samples = [(i * 0.016, i * 40.0, 0.0) for i in range(8)]
        vx, _ = hand.velocity(samples, 7 * 0.016, 0.05)
        self.assertAlmostEqual(vx, 2500.0, delta=100.0)


class PeakTests(unittest.TestCase):
    def test_a_stop_just_before_letting_go_is_forgiven_a_little(self):
        samples = line(*[(t, t * 10.0) for t in range(0, 120, 8)]) + line((130, 1120.0))
        vx, _ = hand.peak_velocity(samples, 0.180, 0.08, 0.25, 0.12)
        self.assertGreater(vx, 2000.0)

    def test_setting_it_down_gently_is_almost_nothing(self):
        samples = line(*[(t, 1.0 * t / 8) for t in range(0, 800, 8)])
        vx, _ = hand.peak_velocity(samples, 0.800, 0.08, 0.25, 0.12)
        self.assertLess(abs(vx), 200.0)


class EventTimeTests(unittest.TestCase):
    def test_the_system_stamp_is_used_when_it_is_on_the_same_clock(self):
        now = time.perf_counter()
        ev = SimpleNamespace(timestamp=lambda: int((now - 0.4) * 1000))
        self.assertAlmostEqual(hand.event_time(ev), now - 0.4, delta=0.01)

    def test_made_up_events_use_now(self):
        for stamp in (0, 500, int((time.perf_counter() + 100.0) * 1000)):
            ev = SimpleNamespace(timestamp=lambda s=stamp: s)
            before = time.perf_counter()
            self.assertGreaterEqual(hand.event_time(ev), before)


if __name__ == "__main__":
    unittest.main()
