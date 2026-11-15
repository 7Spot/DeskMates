"""兴奋度（widget/excite.py）：先有狗的状态，再有这个值；尾巴跟着它，狗的行为不看它。"""
import math
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.room_base import DT, RoomCase
from widget import excite
from widget.excite import Excite, Scene, target, wag

ROOT = Path(__file__).resolve().parents[1]


class ExcitePureTests(unittest.TestCase):
    def test_each_state_has_its_level(self):
        self.assertEqual(target(Scene(posture="sleeping", near_you=True)), 0.0, "睡着：鼠标在旁边也不算")
        self.assertEqual(target(Scene(posture="lying")), 0.1)
        self.assertEqual(target(Scene(posture="sitting")), 0.15)
        self.assertEqual(target(Scene(posture="standing")), 0.2)
        self.assertEqual(target(Scene(task="wander")), 0.3)
        self.assertEqual(target(Scene(near_you=True)), 0.35)
        self.assertEqual(target(Scene(task="eat")), 0.5)
        self.assertAlmostEqual(target(Scene(ball_shown=0.0)), 0.4)
        self.assertAlmostEqual(target(Scene(ball_shown=1.0)), 0.85, msg="拿着球：随圈涨")
        self.assertEqual(target(Scene(task="fetch", carrying=True)), 0.7, "叼着回来")
        self.assertEqual(target(Scene(task="fetch")), 0.9, "追球")
        self.assertEqual(target(Scene(bowing=True, ball_shown=1.0)), 0.95, "俯身等扔")
        self.assertIsNone(target(Scene(held=True, task="fetch")), "被拎着、飞着不算")

    def test_it_rises_fast_and_settles_slowly(self):
        x = Excite()
        x.value = 0.2
        for _ in range(60):
            x.step(1 / 60, 0.9)
        self.assertGreater(x.value, 0.8, "一秒就上去了")
        for _ in range(180):
            x.step(1 / 60, 0.2)
        self.assertGreater(x.value, 0.6, "三秒才落了一小截")
        before = x.value
        x.step(1.0, None)
        self.assertEqual(x.value, before, "被拎着：停在原处")

    def test_kicks_and_the_tail(self):
        x = Excite()
        x.value = 0.95
        x.kick(excite.KICK_GREET)
        self.assertEqual(x.value, 1.0, "不超过 1")
        x.value = 0.3
        x.lift_to(0.2)
        self.assertEqual(x.value, 0.3, "本来更高就不动")
        self.assertEqual((wag(0.0), wag(0.2)), (0.0, 0.0), "站着待着以下尾巴不多摇")
        self.assertAlmostEqual(wag(0.6), 0.5)
        self.assertEqual(wag(1.0), 1.0)

    def test_behaviour_never_reads_it(self):
        """狗去哪、追不追、坐不坐的代码不读兴奋度（单向：状态 → 兴奋度 → 小动作）。playground 只往上加、只报状态，不读它的值。"""
        for name in ("roam", "temper", "locomotion", "world", "play", "clips", "states", "lift", "gaze", "things", "nest" ):
            path = ROOT / "widget" / f"{name}.py"
            if path.is_file():
                self.assertNotIn("excite", path.read_text(encoding="utf-8"), f"{name}.py 不该碰兴奋度")
        for name in ("playground", "dogctl"):
            text = (ROOT / "widget" / f"{name}.py").read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"excite\.value", text), f"{name}.py 不该读兴奋度的值")


class ExciteRoomTests(RoomCase):
    def far(self):
        return (self.ag.x() + 200.0, self.ag.y() + self.ag.height() - 168.0)   # 屏幕左边，离狗远

    def beside(self):
        roam = self.pg.roam
        return (roam.wx + 0.5 * self.win.ppm, roam.wy - 0.4 * self.win.ppm)      # 离身子正中 0.5 米（0.9 个身高以内）

    def test_holding_the_ball_raises_it_and_the_tail_follows(self):
        win, pg = self.win, self.pg
        self.start_on_floor()
        self.step(1.0)
        calm = win.dog.excite.value
        self.assertLessEqual(calm, 0.2 + 1e-6)
        self.assertEqual(win.dog.expr.wag, 0.0, "站着待着：尾巴不多摇")
        self.pick_up_ball()
        self.step(0.6)
        self.assertGreater(win.dog.excite.value, calm + 0.15, "拿着球给它看：涨上去")
        self.assertEqual(win.dog.expr.wag, wag(win.dog.excite.value), "尾巴照兴奋度摇")
        self.assertIsNotNone(self.step(4.0, lambda: pg.ring.ready), "圈满了")
        self.step(1.0)
        self.assertGreater(win.dog.excite.value, 0.8, "圈满：0.85（边牧俯身等扔时 0.95）")

    def test_after_the_fetch_it_settles_slowly(self):
        win, pg, roam = self.win, self.pg, self.pg.roam
        self.start_on_floor()
        self.step(0.3)
        self.throw_and_fetch(-900.0)
        self.assertIsNotNone(self.step(20.0, lambda: pg.carried), "叼上了")
        self.assertGreater(win.dog.excite.value, 0.6)
        self.assertIsNotNone(self.step(40.0, lambda: not pg.carried and roam.task is None), "放下了")
        put = win.dog.excite.value
        self.step(3.0)
        self.assertLess(win.dog.excite.value, put, "往下落")
        self.assertGreater(win.dog.excite.value, 0.35, "落得慢：玩完还高兴一阵")

    def test_the_pointer_beside_it(self):
        win = self.win
        self.cursor = self.far()
        self.start_on_floor()
        self.step(2.0)
        self.assertEqual(win.dog.expr.wag, 0.0)
        self.cursor = self.beside()
        self.step(1.5)
        self.assertGreater(win.dog.excite.value, 0.3, "鼠标在它旁边动")
        self.assertGreater(win.dog.expr.wag, 0.0)

    def test_a_long_while_then_the_pointer_comes_back(self):
        win = self.win
        self.cursor = self.far()
        self.start_on_floor()
        self.step(1.0)
        before = win.dog.excite.value
        win._feel_away = excite.GREET_AFTER_S
        self.cursor = self.beside()
        self.step(DT * 2)
        self.assertGreater(win.dog.excite.value, before + excite.KICK_GREET - 0.02, "打招呼：一下子涨一截")
        self.assertGreater(win.dog.expr._pulse("ears"), 0.0, "耳朵一抖")

    def test_a_tap_but_not_while_asleep(self):
        win = self.win
        self.start_on_floor()
        self.step(1.0)
        v = win.dog.excite.value
        win.dog_tapped()
        self.assertAlmostEqual(win.dog.excite.value, v + excite.KICK_TAP, places=6)
        with mock.patch.object(win.dog, "posture", "sleeping"):
            v = win.dog.excite.value
            win.dog_tapped()
            self.assertEqual(win.dog.excite.value, v, "睡着的不加")

    def test_without_dynamic_interaction_it_still_runs(self):
        win = self.win
        self.start_on_floor()
        win.set_dynamic(False)
        self.assertFalse(win.playground.active)
        win.dog.excite.value = 0.8
        for _ in range(int(3.0 / DT)):
            win._feel(DT)
        self.assertLess(win.dog.excite.value, 0.8, "关着灵动交互也照状态往回落")
        self.assertEqual(win.dog.expr.wag, wag(win.dog.excite.value))


if __name__ == "__main__":
    unittest.main()
