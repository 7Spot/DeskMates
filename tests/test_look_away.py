"""鼠标停着就不看：灵动交互里鼠标停够调参 look_idle_s（边牧 10 秒、萨摩耶 7 秒）狗就不看你了——头回正、身子不跟着鼠标换边、
停下来朝哪就朝哪；鼠标一动马上回来看，手抖的一两像素不算；拿着球、球在动、它在捡球算你在跟它玩，钟不走。
灵动交互里头跟着鼠标，不看鼠标跟随开没开（那个开关在灵动交互开着时藏起来）。停着的鼠标不挡它溜达在 tests/test_wander.py。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint

from tests.room_base import COLLIE, SAMOYED, RoomCase


class LookAwayTests(RoomCase):
    PACK = SAMOYED
    WAIT = 7.0                    # 这只停多久就不看了（包里写的）
    TURNS = False                 # 闲着会不会起身转过去（萨摩耶默认坐着：鼠标换边只转头）

    def setUp(self):
        super().setUp()
        from widget import window as window_module
        p = mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(round(self.cursor[0]), round(self.cursor[1])))   # 窗口读的鼠标也是假的这一个
        p.start()
        self.addCleanup(p.stop)
        self.start_on_floor(x=self.ag.x() + self.ag.width() / 2)
        self.step(0.5)

    def park(self, x, y):
        """鼠标停在 (x, y)，而且已经停了很久：狗早就不看了。"""
        self.cursor = (x, y)
        self.pg._cursor_seen, self.pg._still_for = self.cursor, 1e6

    def test_each_dog_has_its_own_attention_span(self):
        self.assertEqual(self.win.tuning["look_idle_s"], self.WAIT)

    def test_it_watches_the_pointer_then_looks_away_once_it_stays_still(self):
        win, pg, roam = self.win, self.pg, self.pg.roam
        self.assertFalse(win.follow_cursor, "鼠标跟随关着（新装默认）：灵动交互里照样看鼠标")
        self.cursor = (roam.wx - 120.0, roam.wy - 80.0)
        self.step(0.5)
        self.assertTrue(pg.watching_you)
        self.assertIsNotNone(win.dog.look_target, "鼠标刚动过：看着你")
        self.assertIsNotNone(win.dog.body_target)
        self.step(self.WAIT - 1.0)
        self.assertIsNotNone(win.dog.look_target, "还没停够")
        self.step(1.5)
        self.assertFalse(pg.watching_you)
        self.assertIsNone(win.dog.look_target, "停够了：不看了，头回正")
        self.assertIsNone(win.dog.body_target, "身子也不跟着鼠标")
        self.cursor = (self.cursor[0] + 1.0, self.cursor[1])     # 手抖一像素不算动
        self.step(0.2)
        self.assertIsNone(win.dog.look_target)
        self.cursor = (self.cursor[0] + 10.0, self.cursor[1])    # 一动马上回来看
        self.step(1 / 60)
        self.assertTrue(pg.watching_you)
        self.assertIsNotNone(win.dog.look_target)

    def test_a_parked_pointer_behind_it_does_not_turn_it_round(self):
        win, pg, roam = self.win, self.pg, self.pg.roam
        right = win.dog.facing_right()
        side = -1.0 if right else 1.0                            # 狗背后那一边
        self.park(roam.wx + side * 400.0, roam.wy - 60.0)
        self.step(2.0)
        self.assertEqual(win.dog.facing_right(), right, "停着的鼠标在背后：不转身")
        self.assertEqual(win._home_yaw() == 330.0, right, "停下来朝哪就朝哪，不转回去对着鼠标")
        self.cursor = (self.cursor[0] + side * 10.0, self.cursor[1])   # 鼠标一动：又看你了
        self.step(2.0)
        self.assertIsNotNone(win.dog.look_target)
        self.assertEqual(win._home_yaw() == 330.0, not right, "该朝的又是鼠标那边")
        if self.TURNS:
            self.assertNotEqual(win.dog.facing_right(), right, "站着的转过去")

    def test_playing_with_it_keeps_its_eyes_on_you(self):
        pg = self.pg
        self.park(*self.cursor)
        self.step(0.1)
        self.assertFalse(pg.watching_you)
        self.pick_up_ball()
        self.step(0.1)
        self.assertTrue(pg.watching_you, "拿起球：算你在跟它玩")
        self.step(self.WAIT + 1.0)
        self.assertTrue(pg.watching_you, "一直拿着：钟不走")

    def test_with_dynamic_interaction_off_the_switch_decides_as_before(self):
        win = self.win
        win.set_dynamic(False)
        win.set_follow_cursor(False)
        self.assertIsNone(win._look_target(1 / 60), "都关着：不看")
        win.set_follow_cursor(True)
        self.park(*self.cursor)
        self.assertIsNotNone(win._look_target(1 / 60), "只开鼠标跟随：鼠标不动也一直看")


class CollieLookAwayTests(LookAwayTests):
    PACK = COLLIE
    WAIT = 10.0
    TURNS = True


if __name__ == "__main__":
    unittest.main()
