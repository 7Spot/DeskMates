"""自己溜达（灵动交互开着时加随机的游走，边牧比萨摩耶活跃、两只都不要太活跃，摆着的窝和盆也要考虑进去）。
真窗口（offscreen）+ 假设置 + 假的款表（tests/test_nest.py 的底子）；时间按帧推，快进几分钟。"""
import math
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF

from tests.room_base import COLLIE, SAMOYED
from tests.test_bowl import FOOD, BowlCase
from tests.test_nest import BED, FLAT
from widget import playground as pg_mod, sounds, temper

DT = 1 / 30


class WanderTests(BowlCase):
    WANDER = True
    RESTS = "standing"

    def setUp(self):
        super().setUp()
        self.pg._rng.seed(11)
        self.win.dog.rng.seed(5)
        self.sounds = []
        then = sounds.play_file
        p = mock.patch.object(sounds, "play_file", lambda f, *a, **k: (self.sounds.append(str(f)), then(f, *a, **k))[1])
        p.start()
        self.addCleanup(p.stop)
        self.cursor = (self.ag.x() + self.ag.width() - 40.0, self.ag.y() + 40.0)   # 鼠标在远处：不挡着它走

    def run_for(self, seconds, watch=None):
        """快进 seconds 秒（每帧 1/30 秒），记下每一趟溜达：开始 / 结束的时刻、从哪到哪、走的那条线、拴的那一点。"""
        roam, pg = self.pg.roam, self.pg
        trips, cur = [], [None]
        t = [0.0]

        def each():
            t[0] += DT
            if roam.task == "wander" and cur[0] is None:
                cur[0] = {"start": t[0], "from": roam.wx, "line": (roam.support.kind, roam.support.key), "anchor": pg._wander_anchor}
            elif roam.task != "wander" and cur[0] is not None:
                cur[0].update(end=t[0], to=roam.wx, line_after=(roam.support.kind, roam.support.key) if roam.support else None)
                trips.append(cur[0])
                cur[0] = None
            if watch is not None:
                watch()
            return False
        self.step(seconds, each)
        return trips

    def step(self, seconds, until=None, win=None):
        """按 1/30 秒一帧推（快进）：和 RoomCase.step 一样走窗口的每一帧，只是帧大一点。"""
        from tests import room_base
        with mock.patch.object(room_base, "DT", DT):
            return room_base.RoomCase.step(self, seconds, until, win)

    def test_it_strolls_now_and_then_at_its_own_pace_and_stays_near(self):
        """多久一趟按性子（边牧 60～150 秒、萨摩耶 120～300 秒），只在脚下这条线上走、只走路，不离拴的那一点 1.5 米以外，一声不出。"""
        roam = self.pg.roam
        self.start_on_floor(x=self.ag.x() + self.ag.width() / 2)
        lo, hi = temper.wander_every(self.win.tuning)
        gaits = set()

        def watch():
            if roam.task == "wander" and roam.leg is not None and roam.leg.get("kind") == "run" and "clip" in roam.leg:
                gaits.add(roam.leg["clip"])
        trips = self.run_for(12 * 60.0, watch)
        self.assertGreaterEqual(len(trips), int(12 * 60 / hi) - 1, trips)
        self.assertLessEqual(len(trips), int(12 * 60 / lo) + 1, trips)
        starts = [tr["start"] for tr in trips]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertTrue(all(g >= lo - 1.0 for g in gaps), gaps)
        ppm = self.pg.ppm
        for tr in trips:
            self.assertEqual(tr["line"], tr["line_after"], "不换线")
            ax = tr["anchor"][2]
            self.assertLessEqual(abs(tr["to"] - ax), (pg_mod.WANDER_LEASH_M + 0.01) * ppm, "拴着：不越逛越远")
            self.assertGreaterEqual(abs(tr["to"] - tr["from"]), pg_mod.WANDER_MIN_M * ppm - 1.0)
        self.assertTrue(gaits <= {"Walk_F_IP", "Walk_B_IP"}, f"只走路（{gaits}）")
        self.assertEqual(self.sounds, [], "一声不出")

    def test_the_collie_strolls_more_often_than_the_samoyed(self):
        collie, sam = temper.wander_every({"energy": 1.0}), temper.wander_every({"energy": 0.5, "smarts": 0.4})
        self.assertEqual(collie, (60.0, 150.0))
        self.assertEqual(sam, (120.0, 300.0))
        self.assertEqual(temper.wander_reach({"energy": 1.0}), (0.6, 1.8))
        self.assertAlmostEqual(temper.wander_reach({"energy": 0.5})[1], 1.15)

    def test_it_never_stops_on_a_thing(self):
        roam, pg, ppm = self.pg.roam, self.pg, self.pg.ppm
        self.start_on_floor(x=self.ag.x() + self.ag.width() / 2)
        bed = self.put(BED, settle=1.0)
        house = self.put(FLAT, settle=1.0)
        trips = []
        for _ in range(8):                                        # 催它走八趟（每趟到点就走），看停在哪
            pg._wander_in = 0.0
            if self.step(10.0, lambda: roam.task == "wander") is None:
                continue
            x0 = roam.wx
            self.assertIsNotNone(self.step(20.0, lambda: roam.task != "wander"))
            trips.append({"from": x0, "to": roam.wx})
            pg._nest_wait = 1e9                                  # 这一组只看溜达：不让它回窝
        self.assertGreaterEqual(len(trips), 5)
        for tr in trips:
            for t in (bed, house):
                a, b = t.span()
                clear = pg_mod.WANDER_CLEAR_M * ppm
                self.assertFalse(a - clear < tr["to"] < b + clear, f"停在 {t.key} 上")

    def test_a_pointer_near_the_dog_or_an_open_card_holds_it_and_stops_it(self):
        roam, pg = self.pg.roam, self.pg
        self.start_on_floor(x=self.ag.x() + self.ag.width() / 2)
        near, tick = (roam.wx + 20.0, roam.wy - 60.0), [0]

        def fidget():                                             # 鼠标就在狗跟前，一直在动（狗看着你，当你要伸手）
            tick[0] += 1
            self.cursor = (near[0] + (4.0 if tick[0] % 2 else 0.0), near[1])
        trips = self.run_for(6 * 60.0, fidget)
        self.assertEqual(trips, [], "你在跟前：不走")
        self.cursor = (self.ag.x() + self.ag.width() - 40.0, self.ag.y() + 40.0)
        pg._wander_in = 0.0
        self.step(8.0, lambda: roam.task == "wander")             # 正做着随机动作、正换姿势的等它做完
        self.assertEqual(roam.task, "wander")
        self.cursor = (roam.wx, roam.wy - 40.0)                   # 你伸手过来
        self.step(DT * 2)
        self.assertIsNone(roam.task, "就地站住")

    def test_a_pointer_left_beside_it_holds_it_only_while_it_still_watches_you(self):
        """鼠标停着一阵狗就不看你了，自己做自己的事——停在旁边的鼠标不再挡着它溜达。"""
        roam, pg = self.pg.roam, self.pg
        self.start_on_floor(x=self.ag.x() + self.ag.width() / 2)
        self.cursor = (roam.wx + 20.0, roam.wy - 60.0)            # 鼠标停在狗跟前，一直不动
        self.step(0.5)
        pg._wander_in = 0.0
        self.step(pg.tune["look_idle_s"] - 1.5)
        self.assertNotEqual(roam.task, "wander", "刚停下：狗还看着你，当你要伸手")
        self.step(10.0, lambda: roam.task == "wander")            # 正做着随机动作、正换姿势的等它做完
        self.assertEqual(roam.task, "wander", "停够了：狗不看你了，自己走")

    def test_lying_in_a_bed_it_gets_up_strolls_out_and_comes_back_later(self):
        roam, pg = self.pg.roam, self.pg
        t, spot = self.home(BED)
        self.assertIsNotNone(pg._nest)
        pg._wander_in = 0.0
        self.step(0.5, lambda: roam.task == "wander")
        self.assertEqual(roam.task, "wander", "到点从窝里起来走")
        self.assertIsNone(pg._nest, "根、前沿收掉")
        self.assertIsNotNone(self.step(20.0, lambda: roam.task is None))
        a, b = t.span()
        self.assertFalse(a <= roam.wx <= b, "走出窝")
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(30.0, self.nested), "之后照回窝的规矩回去趴下")

    def test_it_sometimes_has_a_quiet_sip_and_the_bowl_stays_full(self):
        roam, pg = self.pg.roam, self.pg
        self.start_on_floor(x=self.ag.x() + self.ag.width() / 2)
        bowl = self.put(FOOD, settle=1.0)
        with mock.patch.object(pg_mod, "WANDER_SIP_P", 1.0):
            pg._wander_in = 0.0
            self.step(0.5, lambda: roam.task is not None)
            self.assertEqual((roam.task, pg._sipping), ("eat", True), "去吃两口")
            loops = []
            self.assertIsNotNone(self.step(20.0, lambda: (loops.append(roam.phase == "loop"), roam.task is None)[1]))
        self.assertTrue(bowl.full, "吃两口：盆不变空")
        from widget import roam as roam_mod
        self.assertAlmostEqual(sum(loops) * DT, roam_mod.EAT_S * roam_mod.SIP_SHARE, delta=0.3, msg="低头一半的时间")
        self.assertEqual([s for s in self.sounds if "eat" in s or "lick" in s or "bite" in s], [], "不出声")
        self.assertFalse(pg._sipping)


class SamoyedWanderTests(WanderTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None
    HOME_WAY = ["sitting", "standing", "lying"]


if __name__ == "__main__":
    unittest.main()
