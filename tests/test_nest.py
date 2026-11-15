"""窝：摆了狗窝、狗屋，狗到第一次该歇的时候自己走回去趴下；拿起球、拎它、窝被拿走就起来。
摆下去马上有反应（PutDown…：刚摆出来 / 拖完松手落定，闲着的狗马上过去趴进去）、踩着窝过去（Tread…：狗不从狗窝里穿过去，根抬到垫子上）也在这。
真窗口（offscreen）+ 假设置（卸载器挡住，tests/room_base.py 的底子）+ 一张假的款表（模型是现写的盒子，不要求买来的物件模型在）；
看真模型量出来的数的那一类（RealNest…）买来的模型不在就跳过。边牧、萨摩耶各跑一遍（萨摩耶的模型不在跳过）。"""
import math
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage

import config
from tests.room_base import COLLIE, DT, SAMOYED, RoomCase
from tests.test_thing_art import glb
from tests.test_things import box
from widget import packs, temper, things as things_mod
from widget.playground import NEST_RETRY_S, PERCH_S
from widget.render import ELEVATION
from widget.things import PAD_SHARE, QUARTER_COS, NestSpot

HAS_PROPS = (config.ROOT / "models" / "props" / "bed_1.glb").is_file()
BED, GABLE, FLAT, BOWL = "bed/blue", "doghouse/gable", "doghouse/flat", "bowl/food"


def nest_styles(folder: Path) -> list:
    """假的款表：一个带前沿的狗窝、一个斜着摆的尖顶狗屋（歇在门外）、一个平顶狗屋（歇在门前）、一个没写 rest 的窝、一个盆。"""
    def style(key, role, size, **spec):
        path = folder / (key.replace("/", "_") + ".glb")
        path.write_bytes(glb(box(*size)))
        return packs.ThingStyle(key=key, pack=key.split("/")[0], names={"en": key}, model=path, thumb=folder / "none.png",
                                spec={"group": "rest", "role": role, "order": 10, "scale": 1.0, "yaw": 0, "shadow": True, **spec})
    return [style(BED, "bed", (0.8, 0.25, 0.5), scale=1.6, fit_pet=True, rest={"x": 0.0, "rise": 0.075, "side": 0}, front_z=0.14),
            style(GABLE, "house", (0.8, 1.0, 1.2), yaw=35, mirror=True, rest={"x": 0.0, "rise": 0.0, "side": 1}),
            style(FLAT, "house", (1.2, 0.7, 0.9), rest={"x": 0.25, "rise": 0.0, "side": 0}),
            style("bed/plain", "bed", (0.8, 0.25, 0.5)), style(BOWL, "bowl", (0.3, 0.1, 0.3), group="food")]


class NestCase(RoomCase):
    PACK = COLLIE
    AFTER = temper.NEST_AFTER_S                               # 这只狗没人理多久回窝
    RESTS = "standing"                                        # 闲下来待的姿势（萨摩耶默认坐着：sitting）
    REST_LOUNGE = None                                        # …那时的 dog.lounge（萨摩耶 "sitting"）
    HELD_TASK = "fetch"                                       # 你拿着球时 roam 在做的事（萨摩耶坐着看，不交给 roam：None）
    HOME_WAY = ["standing", "lying"]                          # 没人理到点走回窝：一路上的姿势（萨摩耶先坐着，起来走过去再趴下）

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.fakes = nest_styles(Path(folder.name))
        p = mock.patch.object(packs, "things", lambda found=None: list(self.fakes))
        p.start()
        self.addCleanup(p.stop)
        super().setUp()
        self.things = self.pg.things
        self.sounds = []                                      # 响过的声音
        for bank in (self.pg.bank, self.pg.ball_bank):
            p = mock.patch.object(bank, "play", lambda name, *a, **k: self.sounds.append(name))
            p.start()
            self.addCleanup(p.stop)

    def make_window(self, settings=None, pack_id=None):
        win = super().make_window(settings, pack_id)

        def hide():
            for t in win.playground.things.items.values():
                t.win.hide()
                if t.front_win is not None:
                    t.front_win.hide()
        self.addCleanup(hide)
        return win

    def put(self, key=BED, settle=1.5, call=False):
        """从「物件」页摆出来，推到落定。call=False：落定那一下不叫狗（当它不是刚摆下来的，像重开以后回到原处那样）——到点回窝、敲盆那两条路的测试用这个；
        摆下去马上有反应（狗闲着就过来）的那条路 call=True。拖完松手（grab → thing_release）走的是真的那条路，照样叫。"""
        self.win.set_thing(key, True)
        t = self.things.items[key]
        if not call:
            t.fresh = False
        if settle:
            self.step(settle)
        return t

    def grab(self, t, to=None):
        """按在物件上拖到 to：这一拖就是拿起。按、拖都算在一秒前：之后马上松手是手停着放下，不是扔出去。"""
        ago = time.perf_counter() - 1.0
        self.things.thing_press(t, QPointF(t.x, t.y - 10.0), ago)
        to = to or (t.x, t.y - 200.0)
        self.things.thing_drag(t, QPointF(to[0], to[1] - 10.0), ago + 0.02)
        self.assertEqual(t.state, "held", "挪了算拿起")
        self.step(2 * DT)
        return to

    def move_to(self, t, x):
        """把停着的物件直接挪到地面上的 x（像拖过去落定了一样重新量：换了半边的反过来画；不叫狗）。返回狗歇在哪（不是窝 None）。"""
        t.x = x
        self.things._seat(t, self.things._floor(0, x))
        self.things._settle(t)
        return self.things.spot_of(t)

    def nested(self) -> bool:
        """狗在窝里趴好了（根也缓到位了）。"""
        dog, pg = self.win.dog, self.pg
        return pg._nest is not None and dog.posture == "lying" and not dog.transition and dog.perch == pg._perch_to

    def home(self, key=BED, x=140.0):
        """摆一个窝，把没人理的钟拨到该回窝的时候，推到狗在窝里趴好。返回 (物件, 该歇的那一处)。"""
        dog, pg = self.win.dog, self.pg
        self.start_on_floor(x=x)
        self.step(0.3)
        t = self.put(key)
        spot = self.things.spot_of(t)
        self.assertIsNotNone(spot)
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(20.0, lambda: pg._nest is not None and dog.posture == "lying" and not dog.transition
                                       and dog.perch == pg._perch_to), "走回窝、趴好了")
        self.step(0.3)
        return t, spot


class GoingHomeTests(NestCase):
    def test_no_nest_means_the_collie_stands_for_ever(self):
        """没摆窝（摆了别的物件也一样）：边牧照旧一直站着，那几行一行都不走。"""
        dog, pg = self.win.dog, self.pg
        self.start_on_floor()
        self.put(BOWL)
        self.put("bed/plain")                                 # 包里没写 rest 的窝：只是摆设
        seen = set()
        self.step(200.0, lambda: seen.add((dog.posture, dog.lounge, pg.roam.task)) and False)
        self.assertEqual(seen, {("standing", None, None)})
        self.assertEqual((pg._idle_for, dog.perch, self.things.has_nests()), (0.0, 0.0, False))

    def test_left_alone_it_walks_back_to_the_bed_and_lies_down_without_a_sound(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(BED)
        spot = self.things.spot_of(t)
        self.assertGreater(abs(spot.x - roam.wx), 1.0 * pg.ppm, "窝摆在一米多以外")
        self.sounds.clear()
        seen = set()
        self.step(self.AFTER - 3.0, lambda: seen.add((dog.posture, roam.task)) and False)
        self.assertLessEqual(seen, {("standing", None), (self.RESTS, None)}, "还没到该歇的时候：待着不动")
        self.assertIn((self.RESTS, None), seen)
        seen, gaits = [], set()

        def watch():
            if not seen or seen[-1] != dog.posture:
                seen.append(dog.posture)
            if roam.task == "nest" and roam.leg is not None and roam.leg.get("kind") == "run" and "clip" in roam.leg:
                gaits.add(roam.leg["clip"])
            return pg._nest is not None and dog.posture == "lying" and not dog.transition
        self.assertIsNotNone(self.step(30.0, watch), "到了第一次该歇的时候走回窝趴下")
        self.assertEqual(seen, self.HOME_WAY[1:] if self.HOME_WAY[0] == "sitting" and seen[:1] != ["sitting"] else self.HOME_WAY, "到了直接趴下，不先坐")
        self.assertTrue(gaits and gaits <= {"Walk_F_IP", "Trot_F_IP"}, f"不急：最快小跑（{gaits}）")
        self.assertEqual(self.sounds, [], "走回窝、趴下不出声")
        self.step(0.5)
        self.assertAlmostEqual(roam.wx, spot.x, delta=1.0)
        self.assertAlmostEqual(roam.wy, t.y, delta=0.5, msg="脚踩的还是窝踩的那条线")
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6, msg="根抬到垫子那么高")
        self.assertAlmostEqual(spot.perch_m, (t.lay.low_m + 0.075 * t.geo[1]) / math.cos(math.radians(ELEVATION)), places=6)
        self.assertGreater(dog.perch, 0.1)
        self.assertTrue(dog.hide_shadow, "歇在垫子上：不画影子")
        self.assertEqual((dog.lounge, roam.task, roam.home.kind), ("lying", None, "floor"))
        self.assertAlmostEqual(roam.home.dx, spot.x, delta=1.0, msg="家改到窝")
        self.assertAlmostEqual(dog.rest_top(), dog.clip_top("Lie_belly_loop_1") + dog.perch, places=6, msg="「···」跟着垫子高")
        self.assertTrue(self.things.front_shown(BED), "窝的前沿盖上了")
        self.assertIn(t.front_win, pg.live_windows(), "前沿那一层截图时也照常画")
        self.step(1.0)
        self.assertTrue(self.things.quiet() and dog.perch == pg._perch_to and not roam.moved, "趴好以后什么都不动")
        seen = set()
        self.step(60.0, lambda: seen.add((dog.posture, dog.lounge, roam.task)) and False)
        self.assertEqual(seen, {("lying", "lying", None)}, "一直趴着")

    def test_resting_in_the_bed_costs_no_window_calls(self):
        """卡顿的规矩：狗歇好以后，物件和前沿那两个窗口一帧一次系统调用都没有。"""
        t, _ = self.home()
        self.step(1.0)
        with mock.patch.object(t.win, "setGeometry") as a, mock.patch.object(t.win, "move") as b, mock.patch.object(t.win, "update") as c, \
                mock.patch.object(t.front_win, "setGeometry") as d, mock.patch.object(t.front_win, "move") as e, \
                mock.patch.object(t.front_win, "update") as f, mock.patch.object(t.front_win, "raise_") as g:
            self.step(1.0)
        self.assertEqual([m.call_count for m in (a, b, c, d, e, f, g)], [0] * 7)

    def test_picking_up_the_ball_gets_it_up_and_ready(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, spot = self.home()
        self.pick_up_ball()
        self.assertIsNotNone(self.step(1.5, lambda: dog.posture == "standing" and not dog.transition), "起来了")
        self.assertEqual((dog.lounge, pg._nest), (None, None))
        self.step(0.3)
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6, msg="起来了还站在垫子上：根还抬着，不沉到窝里去")
        self.assertTrue(self.things.front_shown(BED), "前沿还盖在脚前面")
        self.assertEqual((pg._pad, self.win._pose.footprint), (BED, []), "踩在垫子上：影子不画")
        self.assertIsNotNone(self.step(3.0, lambda: roam.bowing), "圈从拿起那一刻算、起身也算在里面：照样俯身等着")
        self.assertAlmostEqual(pg._ring_at.cy, roam.wy - 0.5 * roam.height_m * pg.ppm - spot.perch_m * math.cos(math.radians(ELEVATION)) * pg.ppm,
                               delta=0.5, msg="圈的圆心跟着身子抬到垫子上")
        self.assertEqual(pg._ring_at.floor, roam.wy, "地面那条线不变")
        self.cursor = (t.x + 2.2 * pg.ppm, roam.wy - 150.0)       # 鼠标在窝外面：叼回来放到那边
        self.put_ball_down()
        self.assertIsNotNone(self.step(30.0, lambda: roam.task is None and pg.ball.resting), "玩完了")
        self.step(0.3)
        self.assertEqual((dog.perch, dog.hide_shadow, pg._pad), (0.0, False, None), "走出垫子：根落回线上、影子回来")
        self.assertFalse(self.things.front_shown(BED), "前沿收掉了")
        self.assertFalse(t.front_win.isVisible())
        pg._idle_for = self.AFTER - 1.0
        self.assertIsNotNone(self.step(20.0, lambda: pg._nest is not None and dog.posture == "lying" and not dog.transition), "没人理了又回窝")

    def test_being_lifted_gets_it_up(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, spot = self.home()
        pg.dog_grabbed((roam.wx, roam.wy))
        self.step(0.5)
        self.assertTrue(roam.lifted)
        self.assertEqual((dog.lounge, dog.perch, pg._nest), (None, 0.0, None))
        self.assertFalse(self.things.front_shown(BED))
        self.win.place_scene(t.x + 2.0 * pg.ppm, roam.wy - 120.0)    # 拎到窝外面放下
        pg.dog_dropped()
        self.assertIsNotNone(self.step(4.0, lambda: roam.task is None and not roam.lifted), "落回去了")
        self.step(0.3)
        self.assertEqual((dog.posture, dog.perch, dog.hide_shadow, pg._pad), (self.RESTS, 0.0, False, None))

    def test_a_click_on_the_dog_only_squashes_it(self):
        dog, pg = self.win.dog, self.pg
        self.home()
        idle = pg._idle_for
        pg.dog_press()
        self.step(0.1)
        pg.dog_unpress()
        self.step(1.0)
        self.assertEqual((dog.posture, dog.lounge, pg._nest is not None), ("lying", "lying", True), "点狗只 duang，不起来")
        self.assertGreater(pg._idle_for, idle + 1.0)

    def test_taking_the_bed_away_gets_it_up_where_it_is(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, spot = self.home()
        self.things.thing_press(t, QPointF(t.x, t.y - 10.0))
        self.step(0.05)
        self.things.thing_release(t, QPointF(t.x, t.y - 10.0))
        self.step(0.5)
        self.assertEqual((dog.posture, pg._nest is not None), ("lying", True), "点一下窝：只 duang，狗不起来")
        self.grab(t, (t.x + 300.0, t.y - 200.0))
        self.assertEqual((dog.lounge, pg._nest), (None, None), "窝被拿走：该起来了")
        self.assertLess(pg._idle_for, 0.1, "钟归零")
        self.assertIsNotNone(self.step(2.0, lambda: dog.posture == "standing" and not dog.transition))
        self.step(0.3)
        self.assertEqual((dog.perch, dog.hide_shadow, roam.task), (0.0, False, None))
        self.assertAlmostEqual(roam.wx, spot.x, delta=1.0, msg="原地站起来")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.5, msg="落回那条线")
        self.assertFalse(t.front_win.isVisible())

    def test_putting_the_bed_away_gets_it_up_too(self):
        dog, pg = self.win.dog, self.pg
        self.home()
        self.win.set_thing(BED, False)
        self.assertEqual((dog.lounge, pg._nest), (None, None))
        self.step(1.5)
        self.assertEqual((dog.posture, dog.perch, self.things.has_nests()), (self.RESTS, 0.0, False))

    def test_the_bed_taken_while_it_is_on_its_way_stops_it(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(BED)
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(5.0, lambda: roam.task == "nest" and roam.v != 0.0), "上路了")
        self.grab(t)
        self.assertEqual((roam.task, pg._nest_going), (None, None), "正往这个窝走：站住")
        self.step(2.0)
        self.assertEqual((dog.posture, dog.lounge, pg._nest), (self.RESTS, self.REST_LOUNGE, None))
        self.assertEqual(self.sounds, [])

    def test_the_ball_picked_up_on_its_way_wins(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.put(BED)
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(5.0, lambda: roam.task == "nest" and roam.v != 0.0), "上路了")
        self.pick_up_ball((roam.wx + 60.0, roam.wy - 150.0))
        self.assertEqual(roam.task, self.HELD_TASK, "球的优先级最大：不去窝了，看球（萨摩耶坐着看）")
        self.step(1.0)
        self.assertEqual((pg._nest, pg._nest_going, pg._idle_for), (None, None, 0.0))

    def test_a_bed_it_cannot_reach_is_left_alone_without_a_bark(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(BED)
        full = roam.max_up
        with mock.patch.object(roam, "max_up", lambda: full() * 0.2):
            top = self.add_window(7, 300.0, self.floor_y - 420.0, 420.0)
            self.assertIsNotNone(top)
            self.grab(t, (500.0, top.y - 60.0))
            self.things.thing_release(t, QPointF(500.0, top.y - 70.0))
            self.step(1.5)
            self.assertEqual(t.on, ("window", 7), "窝落在窗口上")
            self.assertIsNotNone(self.things.spot_of(t), "线站得下狗")
            self.assertIsNone(pg.nest_spot(), "可是跳不上去：这个窝不算")
            self.sounds.clear()
            pg._idle_for = self.AFTER - 1.0
            seen = set()
            self.step(3 * NEST_RETRY_S + 2.0, lambda: seen.add((roam.task, dog.player.name == "Bark")) and False)
            self.assertEqual(seen, {(None, False)}, "够不着：不去也不叫")
            self.assertEqual(self.sounds, [])
            self.assertEqual(dog.posture, "standing" if self.PACK == COLLIE else "sitting", "和没摆窝一样")

    def test_a_bed_put_out_after_it_already_rested_in_place_is_for_next_time(self):
        """已经在原地歇着的狗，之后摆了窝：不马上起来挪过去。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        if self.PACK == COLLIE:
            self.skipTest("边牧不在原地歇")
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(10.0, lambda: dog.posture == "sitting" and not dog.transition), "没窝：原地坐下")
        self.put(BED, settle=3.0)
        seen = set()
        self.step(20.0, lambda: seen.add((roam.task, dog.lounge)) and False)
        self.assertEqual(seen, {(None, "sitting")}, "坐着的不为了新摆的窝起来")

    def test_turning_play_off_puts_everything_back(self):
        dog, pg = self.win.dog, self.pg
        t, spot = self.home()
        self.win.set_dynamic(False)
        self.assertEqual((dog.perch, dog.hide_shadow, dog.lounge, pg._nest, pg._pad), (0.0, False, None, None, None))
        self.assertFalse(t.front_win.isVisible(), "前沿当场收")
        self.win.set_dynamic(True)
        self.step(1.0)
        self.assertEqual((pg._nest, pg._pad), (None, BED), "再开回来：狗还站在原处，窝也回来了——踩在垫子上，不算歇进去")
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6)
        self.assertTrue(self.things.front_shown(BED))

    def test_a_bed_near_the_right_edge_means_lying_toward_the_middle(self):
        """窝在右边四分之一里（离屏这块屏 600 以外）、鼠标也在右边：往右走过去，到了转过来朝左趴（window._edge_yaw），不朝着鼠标那边。"""
        from tests.test_rest_facing import Pointer
        import widget.window as window_mod
        dog, pg = self.win.dog, self.pg
        self.cursor = (self.ag.right() - 4.0, self.floor_y - 60.0)
        p = mock.patch.object(window_mod, "QCursor", Pointer(self))
        p.start()
        self.addCleanup(p.stop)
        self.start_on_floor(x=400.0)
        self.step(0.3)
        t = self.put(BED)
        spot = self.move_to(t, self.ag.x() + 0.85 * self.ag.width())
        self.assertGreater(spot.x, self.ag.x() + 0.75 * self.ag.width())
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(20.0, self.nested), "走回窝、趴好了")
        self.step(0.5)
        self.assertLess(abs((dog.yaw - 210.0 + 180.0) % 360.0 - 180.0), 1.0, "朝左：朝着中间趴")


class PutDownTests(NestCase):
    """摆下去马上有反应：窝刚从「物件」页摆出来落定、刚被你拖完松手落定，
    闲着的狗马上走过去趴进去，不等该歇的时候；忙着就算了，照旧到点再回。"""

    def test_a_bed_just_put_out_calls_it_over_at_once(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        self.sounds.clear()
        self.win.set_thing(BED, True)
        t = self.things.items[BED]
        self.assertEqual((t.state, roam.task), ("fall", None), "还在落：先不动")
        self.assertIsNotNone(self.step(1.0, lambda: t.state == "rest"))
        self.assertEqual((roam.task, pg._nest_going.key), ("nest", BED), "落定那一下就上路")
        gaits = set()

        def watch():
            if roam.leg is not None and roam.leg.get("kind") == "run" and "clip" in roam.leg:
                gaits.add(roam.leg["clip"])
            return self.nested()
        took = self.step(15.0, watch)
        self.assertIsNotNone(took, "走过去趴进去了")
        self.assertLess(took, 8.0)
        self.assertLess(pg._idle_for, 5.0, "没等到该歇的时候（边牧 90 秒、萨摩耶 20 秒）")
        self.assertTrue(gaits and gaits <= {"Walk_F_IP", "Trot_F_IP"}, f"走的是回窝那条路：最快小跑（{gaits}）")
        self.assertEqual(self.sounds, [], "走过去、趴下不出声")
        spot = self.things.spot_of(t)
        self.assertAlmostEqual(roam.wx, spot.x, delta=1.0)
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6)
        self.assertEqual((dog.lounge, pg._nest.key, self.things.front_shown(BED)), ("lying", BED, True))

    def test_a_bed_dragged_and_let_go_calls_it_over_again(self):
        """歇在窝里时把窝拖走：狗站起来；松手落定，狗又走过去趴进去。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, _ = self.home()
        self.sounds.clear()
        self.grab(t, (self.ag.x() + 180.0, t.y - 200.0))
        self.assertEqual((pg._nest, dog.lounge, roam.task), (None, None, None), "窝拿走了：起来，先不走")
        self.things.thing_release(t, QPointF(*t.pointer))
        self.assertIsNotNone(self.step(2.0, lambda: t.state == "rest"), "落定了")
        self.assertEqual((roam.task, pg._nest_going.key), ("nest", BED))
        self.assertIsNotNone(self.step(15.0, self.nested), "又走过去趴进去")
        spot = self.things.spot_of(t)
        self.assertAlmostEqual(roam.wx, spot.x, delta=1.0)
        self.assertLess(spot.x, self.ag.x() + 400.0, "去的是窝现在在的地方")
        self.assertEqual(self.sounds, [])

    def test_it_goes_to_the_one_just_put_down_not_the_nearest(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=520.0)
        self.step(0.3)
        flat = self.put(FLAT)
        self.move_to(flat, self.ag.x() + 620.0)
        bed = self.put(BED)
        self.assertEqual(pg.nest_spot().key, FLAT, "离狗最近的是平顶狗屋")
        self.grab(bed, (self.ag.x() + 170.0, self.floor_y - 150.0))
        self.things.thing_release(bed, QPointF(*bed.pointer))
        self.assertIsNotNone(self.step(2.0, lambda: bed.state == "rest"))
        self.assertEqual((roam.task, pg._nest_going.key), ("nest", BED), "去的是刚放下的这一个")
        self.assertIsNotNone(self.step(15.0, self.nested))
        self.assertEqual(pg._nest.key, BED)

    def test_a_busy_dog_is_left_alone_and_goes_home_later_the_old_way(self):
        """忙着就算了：球在你手上、球在动、被拎着、站在转台上、手上有别的事，窝落定都不叫它；之后照旧等到该歇的时候再回。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        self.put(BED)                                           # 先摆好位置（不叫），下面每次收起再摆出来都落回这
        b = pg.ball

        def put_again(why, first=None):
            self.win.set_thing(BED, False)
            self.step(0.4)
            self.win.set_thing(BED, True)
            bed = self.things.items[BED]
            self.assertTrue(bed.fresh)
            if first is not None:
                first()                                         # 窝还在落的时候狗有了别的事
            self.assertIsNotNone(self.step(0.8, lambda: bed.state == "rest"), why)
            self.step(0.2)
            self.assertIsNone(pg._nest_going, why)
            self.assertNotEqual(roam.task, "nest", why)
            return bed

        self.pick_up_ball((roam.wx, roam.wy - 2.2 * pg.ppm))    # 球拿在圈外面：狗站好看着
        put_again("球在你手上")
        self.put_ball_down()
        self.assertIsNotNone(self.step(8.0, lambda: roam.task is None and b.resting))
        b.x, b.y, b.on, b.resting = 300.0, self.floor_y - 300.0, None, False
        b.throw(120.0, -900.0, pg.ppm)                           # 球在飞（没叫狗去追）
        pg.throw_id += 1
        put_again("球在动")
        self.assertFalse(b.resting, "窝落定的时候球还没停")
        self.assertIsNotNone(self.step(8.0, lambda: b.resting))
        pg.dog_grabbed((roam.wx, roam.wy))
        put_again("被拎着")
        pg.dog_dropped()
        self.assertIsNotNone(self.step(4.0, lambda: roam.task is None and not roam.lifted))
        dog.set_turntable(True)
        put_again("站在转台上（看细节）")
        dog.set_turntable(False)
        put_again("手上有别的事（被叫去别处）", first=lambda: self.assertTrue(roam.go_to(roam.support, self.ag.x() + self.ag.width() - 60.0)))
        self.assertEqual(roam.task, "go", "窝落定的时候它还在路上")
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None))
        seen = set()
        pg._idle_for = 0.0
        self.step(5.0, lambda: seen.add((roam.task, dog.lounge)) and False)
        self.assertLessEqual(seen, {(None, None), (None, self.REST_LOUNGE)}, "闲下来也不补叫：等到该歇的时候")
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(20.0, self.nested), "到点照旧回窝")

    def test_resting_on_the_floor_it_gets_up_for_a_bed_just_put_down(self):
        """已经在原地坐着的狗（萨摩耶）：窝摆下来，它起来走过去趴进去（没叫到它的，照旧不为窝起来：GoingHomeTests 里那一条）。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        if self.PACK == COLLIE:
            self.skipTest("边牧不在原地歇")
        self.start_on_floor(x=140.0)
        self.step(0.3)
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(10.0, lambda: dog.posture == "sitting" and not dog.transition), "没窝：原地坐下")
        t = self.put(BED, settle=0, call=True)
        self.assertIsNotNone(self.step(1.0, lambda: t.state == "rest"))
        self.assertEqual(roam.task, "nest", "坐着的也起来过去")
        self.assertIsNotNone(self.step(15.0, self.nested))
        self.assertEqual((dog.lounge, pg._nest.key), ("lying", BED))
        self.assertEqual(self.sounds, [])

    def test_lying_in_one_nest_it_moves_to_the_one_just_put_down(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        bed, spot = self.home()
        self.assertGreater(dog.perch, 0.1)
        flat = self.put(FLAT, settle=0, call=True)
        self.assertIsNotNone(self.step(1.0, lambda: flat.state == "rest"))
        self.assertEqual((roam.task, pg._nest_going.key, pg._nest), ("nest", FLAT, None), "从狗窝里起来，去刚摆下来的狗屋")
        self.assertIsNotNone(self.step(15.0, self.nested))
        self.assertEqual(pg._nest.key, FLAT)
        self.assertAlmostEqual(roam.wx, self.things.spot_of(flat).x, delta=1.0)
        self.assertEqual((dog.perch, dog.hide_shadow, pg._pad), (0.0, False, None), "趴在门前的地上：垫子的高度没留在身上")
        self.assertFalse(self.things.front_shown(BED), "狗窝的前沿收掉了")
        self.assertEqual(self.sounds, [])

    def test_things_coming_back_in_place_or_falling_on_their_own_call_nothing(self):
        """不算刚摆下来的：关了灵动交互再开、重开回到原处的，脚下的窗口没了自己落下去的。狗不动，照旧等到该歇的时候。"""
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        t = self.put(BED)
        seen = set()
        self.win.set_dynamic(False)
        self.win.set_dynamic(True)
        self.step(3.0, lambda: seen.add((roam.task, pg._nest_going)) and False)
        top = self.add_window(7, 430.0, self.floor_y - 220.0, 340.0)
        t = self.things.items[BED]
        t.x = 600.0
        self.things._seat(t, top)                               # 窝站在别的窗口上
        self.things._settle(t)
        self.step(0.5, lambda: seen.add((roam.task, pg._nest_going)) and False)
        self.assertEqual(t.on, ("window", 7))
        del self.frames[7]                                      # 窗口关了：窝自己落下去
        pg._sups = None
        self.assertIsNotNone(self.step(3.0, lambda: seen.add((roam.task, pg._nest_going)) or (t.state == "rest" and t.on == ("floor", 0))))
        self.step(2.0, lambda: seen.add((roam.task, pg._nest_going)) and False)
        self.assertEqual(seen, {(None, None)}, "都不叫狗")
        saved = dict(self.win.settings.values)
        pg.stop()
        again = self.make_window(saved)
        self.start_on_floor(x=140.0, win=again)
        seen = set()
        self.step(3.0, lambda: seen.add(again.playground.roam.task) and False, win=again)
        self.assertEqual((seen, list(again.playground.things.items)), ({None}, [BED]), "重开：窝在原处，狗不动")


class SamoyedPutDownTests(PutDownTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None
    HOME_WAY = ["sitting", "standing", "lying"]


class TreadTests(NestCase):
    """踩着窝过去：狗在线上跑、走、站，身子正中进了狗窝垫子的范围，根抬到垫子上、
    窝的前沿盖在脚前面；出了范围落回线上。跳、掉、被拎、被扔，低头叼球时不抬。和歇在窝里共用 dog.perch、前沿那一层。"""

    def bed_in_the_middle(self, dog_x=110.0, key=BED, at=0.5):
        """狗站在左边，窝摆在屏幕中间（at：屏宽的几成；不叫狗）。返回 (物件, 垫子的左、右, 根该抬多高)。"""
        self.start_on_floor(x=dog_x)
        self.step(0.3)
        t = self.put(key)
        spot = self.move_to(t, self.ag.x() + at * self.ag.width())
        half = PAD_SHARE * 0.5 * t.width                        # 假款表没写 rest.half：画出来宽度的七成
        return t, t.x - half, t.x + half, spot.perch_m

    def run_to(self, x, rows=None):
        """叫狗跑到地面上的 x，一帧记一行：(根的 x, 根抬多高, 要抬到多高, 踩着哪个垫子, 前沿显示着没有, 画不画影子, 大事)。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        rows = [] if rows is None else rows
        self.assertTrue(roam.go_to(roam.support, x))

        def watch():
            rows.append((roam.wx, dog.perch, pg._perch_to, pg._pad, self.things.front_shown(BED), bool(self.win._pose.footprint), roam.task))
            return roam.task is None
        self.assertIsNotNone(self.step(12.0, watch), "跑到了")
        return rows

    def test_running_across_the_bed_it_steps_onto_the_cushion_and_off_again(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, lo, hi, perch = self.bed_in_the_middle()
        self.assertGreater(perch, 0.1)
        self.assertEqual((dog.perch, pg._pad, t.front_win), (0.0, None, None), "还没踩上去")
        self.sounds.clear()
        rows = self.run_to(self.ag.x() + self.ag.width() - 80.0)
        inside = [r for r in rows if lo <= r[0] <= hi]
        outside = [r for r in rows if r[0] < lo - 1.0 or r[0] > hi + 1.0]
        self.assertGreater(len(inside), 6, "从垫子上跑过去了")
        self.assertTrue(all(r[2] == perch and r[3] == BED and r[4] for r in inside), "身子正中在垫子的范围里：根往垫子上抬，前沿盖着")
        self.assertTrue(all(r[2] == 0.0 and r[3] is None for r in outside), "出了范围：落回线上")
        self.assertAlmostEqual(max(r[1] for r in rows), perch, places=6, msg="真抬到了垫子那么高")
        steps = [abs(b[1] - a[1]) for a, b in zip(rows, rows[1:])]
        self.assertLessEqual(max(steps), perch * DT / PERCH_S + 1e-9, "缓上去、缓下来（0.12 秒），不是一下跳上去")
        self.assertTrue(all(not r[5] for r in rows if r[1] > 0.0), "根抬着的时候不画影子（影子会落在窝后面的地上）")
        self.assertTrue(any(r[5] for r in outside))
        self.assertEqual(self.sounds, [], "踩着窝过去不出声")
        self.step(0.5)
        self.assertEqual((dog.perch, pg._pad, self.things.front_shown(BED), t.front_win.isVisible()), (0.0, None, False, False), "过去以后前沿淡掉、藏起来")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.5, msg="脚踩的还是那条线（抬的是画出来的根）")
        from widget import native
        with mock.patch.object(t.front_win, "show", wraps=t.front_win.show) as show, mock.patch.object(t.front_win, "hide", wraps=t.front_win.hide) as hide, \
                mock.patch.object(native, "set_level", wraps=native.set_level) as level, mock.patch.object(t.win, "setGeometry") as a, \
                mock.patch.object(t.win, "move") as b, mock.patch.object(t.win, "update") as c:
            self.run_to(self.ag.x() + 110.0)                     # 再跑回来
            self.step(0.5)
            self.assertEqual((show.call_count, hide.call_count), (1, 1), "前沿的窗口只在踩上、离开那一下显示 / 收掉")
            self.assertEqual([call.args[1] for call in level.call_args_list if call.args[0] is self.win], [native.LEVEL_DOG_IN[0], native.LEVEL_DOG],
                             "狗只在踩上（换到窝和窝沿之间）、前沿收掉（回到物件前面）那两下换层")
            self.assertEqual((a.call_count, b.call_count, c.call_count), (0, 0, 0), "窝自己的窗口一下都不碰")

    def test_standing_on_the_cushion_it_stays_up_and_costs_no_window_calls(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, lo, hi, perch = self.bed_in_the_middle()
        top = dog.rest_top()
        self.run_to(t.x)
        self.step(1.0)
        self.assertEqual((dog.posture, pg._nest, pg._pad, roam.task), (self.RESTS, None, BED, None), "站（萨摩耶坐）在窝上，不算歇进去")
        self.assertAlmostEqual(dog.perch, perch, places=6)
        self.assertTrue(self.things.front_shown(BED))
        self.assertAlmostEqual(dog.rest_top(), top + perch, places=6, msg="「···」、窗口的高度跟着")
        self.assertTrue(self.things.quiet() and dog.perch == pg._perch_to and not roam.moved, "站稳了什么都不动")
        with mock.patch.object(t.win, "setGeometry") as a, mock.patch.object(t.win, "move") as b, mock.patch.object(t.win, "update") as c, \
                mock.patch.object(t.front_win, "setGeometry") as d, mock.patch.object(t.front_win, "move") as e, mock.patch.object(t.front_win, "update") as f, \
                mock.patch.object(t.front_win, "raise_") as g, mock.patch.object(t.front_win, "show") as h, mock.patch.object(t.front_win, "hide") as i:
            self.step(1.0)
        self.assertEqual([m.call_count for m in (a, b, c, d, e, f, g, h, i)], [0] * 9, "卡顿的规矩：停着每帧零次系统调用")
        self.grab(t, (t.x, t.y - 220.0))                         # 把窝从脚下拿走
        self.step(0.4)
        self.assertEqual((dog.perch, pg._pad, self.things.front_shown(BED)), (0.0, None, False), "窝拿走：落回线上")
        self.assertEqual(roam.task, None)

    def test_lifted_falling_or_thrown_it_is_not_on_the_cushion(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, lo, hi, perch = self.bed_in_the_middle()
        self.run_to(t.x)
        self.step(0.5)
        self.assertAlmostEqual(dog.perch, perch, places=6)
        pg.dog_grabbed((roam.wx, roam.wy))
        self.step(0.4)
        self.assertEqual((roam.lifted, dog.perch, pg._pad, self.things.front_shown(BED)), (True, 0.0, None, False), "拎起来：不算踩着")
        self.win.place_scene(t.x, roam.wy - 160.0)               # 拎到窝正上方松手：直着掉在窝上
        pg.dog_dropped()
        falling = []
        self.assertIsNotNone(self.step(5.0, lambda: falling.append((roam.leg is not None, pg._perch_to, dog.perch)) or roam.task is None))
        self.assertGreater(sum(1 for r in falling if r[0]), 10)
        self.assertTrue(all(r[1:] == (0.0, 0.0) for r in falling if r[0]), "掉着、落地那几下不抬")
        self.step(0.4)
        self.assertEqual(pg._pad, BED, "落稳了站在窝上：踩到垫子上")
        self.assertAlmostEqual(dog.perch, perch, places=6)
        self.win.place_scene(self.ag.x() + 110.0, self.floor_y)  # 回到左边，朝右扔过去：从窝上面飞过
        roam.place(self.ag.x() + 110.0, self.floor_y)
        roam.drop_to_support()
        self.step(0.5)
        self.assertEqual(dog.perch, 0.0)
        roam.throw(3.9 * pg.ppm, -3.0 * pg.ppm)
        flying = []
        self.assertIsNotNone(self.step(6.0, lambda: flying.append((roam.wx, roam.leg is not None, pg._perch_to, dog.perch)) or roam.task is None))
        over = [r for r in flying if r[1] and lo <= r[0] <= hi]
        self.assertTrue(over, "从垫子上面飞过去了")
        self.assertTrue(all(r[2:] == (0.0, 0.0) for r in flying if r[1]), "被扔着、落地滑着的时候不抬")

    def test_a_doghouse_is_walked_past_not_stepped_on(self):
        t, _, _, perch = self.bed_in_the_middle(key=FLAT)
        self.assertEqual(perch, 0.0)
        rows = self.run_to(self.ag.x() + self.ag.width() - 80.0)
        self.assertEqual({(r[1], r[2], r[3]) for r in rows}, {(0.0, 0.0, None)}, "狗屋：狗从屋前面过，不抬")
        self.assertIsNone(t.front_win)
        self.assertIsNone(self.things.pad_at("floor", 0, t.x))

    def test_the_pack_can_say_how_wide_the_cushion_is(self):
        """垫子横着的范围：包里的 rest.half（米，模型单位 × 倍数）；不写按画出来宽度的七成。拿着、在落、在收的窝不算，别的线上的不算。"""
        pg = self.pg
        t, lo, hi, perch = self.bed_in_the_middle()
        at = self.things.pad_at
        self.assertEqual(at("floor", 0, t.x), (BED, perch))
        self.assertIsNotNone(at("floor", 0, hi - 1.0))
        self.assertIsNone(at("floor", 0, hi + 1.0))
        self.assertIsNone(at("window", 7, t.x), "不是同一条线")
        spec = dict(t.style.spec)
        spec["rest"] = {**spec["rest"], "half": 0.2, "x": 0.1}
        with mock.patch.object(t, "style", packs.ThingStyle(key=BED, pack="bed", model=t.style.model, spec=spec)):
            k, ppm = t.geo[1], pg.ppm
            mid = t.x + 0.1 * k * ppm
            self.assertIsNotNone(at("floor", 0, mid + 0.2 * k * ppm - 1.0))
            self.assertIsNone(at("floor", 0, mid + 0.2 * k * ppm + 1.0))
            self.assertIsNone(at("floor", 0, mid - 0.2 * k * ppm - 1.0), "偏着 rest.x")
        self.grab(t)
        self.assertIsNone(at("floor", 0, t.x), "拿着的不算")

    def test_it_steps_down_to_pick_up_a_ball_lying_in_front_of_the_bed(self):
        """球停在窝前面（垫子的范围里）：跑过去时踩在垫子上，低头叼的那几步落回线上（鼻子要够着线上的球），叼到那一刻根在线上；叼着走开又踩上去。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, lo, hi, perch = self.bed_in_the_middle(at=0.66)       # 窝靠右一点：叼回左边放下的地方在垫子外面
        b = pg.ball
        b.x, b.y, b.vx, b.vy, b.resting, b.rolling, b.on = t.x + 40.0, self.floor_y - b.r, 0.0, 0.0, True, False, ("floor", 0)
        pg.throw_id += 1
        self.cursor = (self.ag.x() + 90.0, self.floor_y - 150.0)  # 叼回左边放下
        roam.fetch()
        rows = []

        def watch():
            rows.append((roam.phase, pg._perch_to, dog.perch, roam.carrying, roam.wx))
            return roam.task is None
        self.assertIsNotNone(self.step(25.0, watch), "叼回来放下了")
        self.assertTrue(any(r[0] == "approach" and r[1] == perch for r in rows), "跑到球跟前的路上踩着垫子")
        low = [r for r in rows if r[0] in ("face_ball", "pickup")]
        self.assertTrue(low and all(r[1] == 0.0 for r in low), "低头叼的那几步：落回线上")
        got = next(i for i, r in enumerate(rows) if r[3])
        self.assertTrue(lo <= rows[got][4] <= hi, "叼的时候身子正中在垫子的范围里")
        self.assertEqual(rows[got][2], 0.0, "鼻子碰到球那一刻根在线上")
        self.assertTrue(any(r[0] == "carry" and r[1] == perch for r in rows[got:]), "叼着走开：又踩在垫子上")
        self.assertTrue(all(r[1] == 0.0 for r in rows if r[0] in ("hold", "hold_done", "turn_put", "putdown")), "放球的那几步也在线上")
        self.step(0.3)
        self.assertLess(roam.wx, lo, "放下的地方在垫子外面")
        self.assertEqual((dog.perch, pg._pad), (0.0, None))


class SamoyedTreadTests(TreadTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None
    HOME_WAY = ["sitting", "standing", "lying"]


class HouseTests(NestCase):
    def gable(self, door: float):
        """尖顶狗屋斜着摆、门朝屏幕中间：狗歇在门那一侧的外面，头朝外，身后留出趴着的那一截（按模型量）。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        mid = self.ag.x() + self.ag.width() / 2
        self.start_on_floor(x=mid)
        self.step(0.3)
        t = self.put(GABLE)
        spot = self.move_to(t, mid - door * 0.6 * self.ag.width() / 2)
        self.assertEqual(t.right_half, door < 0, "屋在左半屏门朝右、在右半屏门朝左（朝屏幕中间）")
        self.assertEqual(t.geo[2], 35.0 * door)
        rear, fore = (v * QUARTER_COS * pg.ppm for v in dog.lie_span())
        lo, hi = t.span()
        edge = hi if door > 0 else lo
        self.assertAlmostEqual(spot.x, edge + door * rear, delta=0.5, msg="离屋那条边正好是趴着身后那一截")
        self.assertEqual((spot.perch_m, spot.yaw), (0.0, 330.0 if door > 0 else 210.0))
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(20.0, lambda: pg._nest is not None and dog.posture == "lying" and not dog.transition), "走到门口趴下")
        self.step(1.0)
        self.assertAlmostEqual(roam.wx, spot.x, delta=1.0)
        self.assertEqual((dog.perch, dog.hide_shadow), (0.0, False), "趴在地上：影子照画")
        self.assertAlmostEqual(dog.yaw % 360.0, spot.yaw, delta=1.0, msg="头朝外")
        self.assertFalse(self.things.front_shown(GABLE), "没有前沿那一层")
        self.assertIsNone(t.front_win)

    def test_at_the_gable_house_on_the_left_it_lies_outside_the_door_head_right(self):
        self.gable(1.0)

    def test_at_the_gable_house_on_the_right_it_lies_outside_the_door_head_left(self):
        self.gable(-1.0)

    def test_no_room_beside_the_door_means_in_front_of_the_house(self):
        self.start_on_floor(x=400.0)
        t = self.put(GABLE)
        a = self.pg.world.areas[0]
        t.x, t.right_half = a.left + t.lay.cx + 2.0, False       # 贴着屏幕左边、门还朝右：正常
        t.geo = None
        self.things._fit(t)
        self.assertGreater(self.things.spot_of(t).x, t.span()[1])
        t.x, t.right_half = a.right - (t.lay.w - t.lay.cx) - 2.0, False   # 贴着右边、门却朝右（刚拖过去还没换边的那种）：门外放不下
        t.geo = None
        self.things._fit(t)
        spot = self.things.spot_of(t)
        self.assertAlmostEqual(spot.x, t.x, delta=0.5, msg="换到屋的正前面")
        self.assertEqual(spot.yaw, 330.0)

    def test_at_the_flat_house_it_lies_in_front_of_the_door(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, spot = self.home(FLAT)
        self.assertAlmostEqual(spot.x, t.x + 0.25 * pg.ppm, delta=0.5, msg="门前偏右，门露出一半")
        self.assertEqual((spot.perch_m, spot.yaw), (0.0, None))
        self.assertAlmostEqual(roam.wx, spot.x, delta=1.0)
        self.assertEqual((dog.posture, dog.perch, dog.hide_shadow), ("lying", 0.0, False))

    def test_the_nearest_reachable_nest_is_the_one(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.put(FLAT)
        bed = self.put(BED)
        spots = {s.key: s for s in self.things.nest_spots()}
        self.assertEqual(set(spots), {FLAT, BED})
        near = min(spots.values(), key=lambda s: abs(s.x - roam.wx))
        self.assertEqual(pg.nest_spot().key, near.key)
        self.grab(bed)
        self.assertEqual([s.key for s in self.things.nest_spots()], [FLAT], "拿着的窝不算")


class FrontLayerTests(NestCase):
    def fake_canvas(self):
        made = []

        def shoot(view, model, lay, dpr):
            img = QImage(max(1, round(lay.w * dpr)), max(1, round(lay.h * dpr)), QImage.Format_ARGB32_Premultiplied)
            img.fill(0xFF336699)
            made.append(model)
            return img
        for p in (mock.patch.object(self.win.view, "ready", lambda: True), mock.patch.object(things_mod.thing_art, "shoot", shoot)):
            p.start()
            self.addCleanup(p.stop)
        return made

    def test_the_front_rim_is_drawn_once_and_only_while_the_dog_is_in(self):
        """前沿那一层：图和窗口摆出来以后闲着的时候就备好（狗跑过窝踩上垫子只有一眨眼，那时现出来不及），只出一次；
        窗口只在狗踩在垫子上、歇在里面时显示，狗走出垫子就淡掉藏起来。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        made = self.fake_canvas()
        self.start_on_floor(x=140.0)
        self.step(0.3)
        t = self.put(BED)
        self.assertEqual(len(made), 2, "物件一张、前沿一张：狗还没来就备好了")
        self.assertIsNotNone(t.front_win, "窗口也先建好")
        self.assertFalse(t.front_win.isVisible(), "狗没踩上来：不显示")
        self.assertNotIn(t.front_win, pg.live_windows())
        self.step(1.5)
        self.assertTrue(self.things.quiet(), "备好以后什么都不动")
        gable = self.put(GABLE)
        self.step(0.5)
        self.assertEqual(len(made), 3, "没写 front_z 的款（狗屋）没有这一层")
        self.assertIsNone(gable.front_win)
        self.win.set_thing(GABLE, False)
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(20.0, lambda: pg._nest is not None and dog.posture == "lying" and not dog.transition), "回窝趴好")
        self.step(0.5)
        self.assertEqual(len(made), 3, "歇进来不用再出")
        whole, front = made[0], made[1]
        self.assertIs(whole, t.model)
        self.assertLess(front.mesh.vertex_count, whole.mesh.vertex_count, "前沿只有靠镜头的那些面")
        self.assertGreater(front.mesh.vertex_count, 0)
        self.assertGreater(min(front.mesh.positions[2::3]), 0.14 * t.geo[1] - 1e-6, "比包里的 front_z（× 倍数）更靠镜头")
        self.assertIs(t.front_win.shot, t.front_shot)
        self.assertEqual((t.front_win.geometry(), t.front_win.alpha), (t.win.geometry(), 1.0), "和物件的窗口摆在同一处")
        self.assertTrue(t.front_win.front)
        self.step(3.0)
        self.assertEqual(len(made), 3, "出过的不再出")
        self.pick_up_ball()
        self.step(1.5)
        self.assertTrue(t.front_win.isVisible(), "狗起来了还站在垫子上：前沿留着")
        self.cursor = (t.x + 2.2 * pg.ppm, roam.wy - 150.0)
        self.put_ball_down()
        self.assertIsNotNone(self.step(30.0, lambda: roam.task is None and not t.front_win.isVisible()), "狗走出垫子：前沿淡掉、藏起来")
        self.assertEqual((t.front_alpha, len(made)), (0.0, 3))

    def test_in_the_bed_the_dog_sits_between_the_bed_and_its_rim(self):
        """狗歇在窝里（窝沿显示着）：狗换到窝和窝沿之间、盆后面那一层（LEVEL_DOG_IN[0]）。点狗、狗的窗口重新显示都不动层
        （点趴在窝里的狗它浮到窝上面）；窝沿淡完藏起来才回到所有物件前面。"""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import native
        t, _ = self.home()
        w = self.win
        self.assertEqual((t.win.level, w.level, t.front_win.level), (native.LEVEL_THING[0], native.LEVEL_DOG_IN[0], native.LEVEL_RIM[0]))
        at = QPointF(w.width() / 2.0, w.height() / 2.0)

        def mouse(kind, buttons):
            return QMouseEvent(kind, at, QPointF(w.mapToGlobal(at)), Qt.LeftButton, buttons, Qt.NoModifier)
        with mock.patch.object(native, "set_level") as level:
            w.mousePressEvent(mouse(QEvent.MouseButtonPress, Qt.LeftButton))
            w.mouseReleaseEvent(mouse(QEvent.MouseButtonRelease, Qt.NoButton))
            w.fade_in(0.0)
            level.assert_not_called()
        self.assertTrue(self.things.front_shown(BED), "点狗只 duang，不起来：前沿还盖着")
        self.things.hide_front()
        self.assertTrue(t.front_win.isVisible())
        self.assertEqual(w.level, native.LEVEL_DOG_IN[0], "窝沿淡出的时候狗还在窝里那一层")
        self.step(0.5)
        self.assertFalse(t.front_win.isVisible())
        self.assertEqual(w.level, native.LEVEL_DOG, "窝沿藏起来了：回到所有物件前面")

    def test_the_dog_and_every_screen_window_change_level_together(self):
        """狗换层：主窗口和显示着的每块屏的另一半一起换，变了才跟系统说；没显示的下次显示时照 window.level 设。"""
        from widget import native
        w = self.win
        shown, hidden = mock.Mock(), mock.Mock()
        shown.isVisible.return_value, hidden.isVisible.return_value = True, False
        with mock.patch.object(native, "set_level") as level, mock.patch.dict(w._ghosts, {"a": shown, "b": hidden}, clear=True), \
                mock.patch.object(w, "isVisible", return_value=True):
            w.set_dog_level(native.LEVEL_DOG_IN[0])
            self.assertEqual(level.call_args_list, [mock.call(w, native.LEVEL_DOG_IN[0]), mock.call(shown, native.LEVEL_DOG_IN[0])])
            w.set_dog_level(native.LEVEL_DOG_IN[0])
            self.assertEqual(level.call_count, 2, "没变不说")
            w.set_dog_level(native.LEVEL_DOG)
        self.assertEqual(w.level, native.LEVEL_DOG)

    def test_where_the_rim_shows_the_mouse_is_on_the_bed_not_the_dog(self):
        """狗趴在窝里右键窝，弹的是设置卡片、不是「我不要……了」——前沿点得穿，点在窝沿上落到被它挡住的狗身上。
        盖在狗前面的物件看得见的地方（图上那一点够不透明）算物件：things.covers_dog 是真，狗的窗口不接（input._covered），点击落到窝本身的窗口；
        透明的地方、窗口外面、淡得快看不见、图还没出好、前沿收了都不算。狗在窝里那一层时盆也在它前面，平时不是。"""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor, QImage
        from widget import input as input_mod
        from widget import native
        t, _ = self.home()
        win = t.front_win
        self.assertTrue(win.isVisible())
        img = QImage(40, 20, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))
        for y in range(10, 20):                                          # 下半截是窝沿
            for x in range(40):
                img.setPixelColor(x, y, QColor(90, 140, 200, 255))
        win.shot, win.pic, win.origin, win.alpha = img, (40.0, 20.0), QPointF(0.0, 0.0), 1.0
        g = win.geometry()
        rim, clear = g.topLeft() + QPoint(10, 15), g.topLeft() + QPoint(10, 5)
        self.assertTrue(self.things.covers_dog(rim))
        self.assertFalse(self.things.covers_dog(clear), "前沿透明的地方：底下的狗照旧是狗")
        self.assertFalse(self.things.covers_dog(g.topLeft() - QPoint(5, 5)), "窗口外面")
        with mock.patch.object(input_mod.QCursor, "pos", lambda *a: rim):
            self.assertTrue(self.win._covered(), "狗的窗口这一点不接，点击落到窝的窗口")
        with mock.patch.object(input_mod.QCursor, "pos", lambda *a: clear):
            self.assertFalse(self.win._covered())
        win.alpha = 0.2
        self.assertFalse(self.things.covers_dog(rim), "淡得快看不见：不算")
        win.alpha, win.shot = 1.0, None
        self.assertFalse(self.things.covers_dog(rim), "图还没出好：前沿是空的，不算")
        win.shot = img
        self.win.set_thing(BED, False)                                   # 窝收起来：前沿跟着收
        self.step(1.0)
        self.assertFalse(self.things.covers_dog(rim), "前沿收了：不算")
        bowl = self.put(BOWL)
        bw = bowl.win
        bw.shot, bw.pic, bw.origin, bw.alpha = img, (40.0, 20.0), QPointF(0.0, 0.0), 1.0
        on_bowl = bw.geometry().topLeft() + QPoint(10, 15)
        self.win.set_dog_level(native.LEVEL_DOG_IN[0])
        self.assertTrue(self.things.covers_dog(on_bowl), "狗在窝里那一层：盆在它前面，盆看得见的地方也不算狗")
        self.win.set_dog_level(native.LEVEL_DOG)
        self.assertFalse(self.things.covers_dog(on_bowl), "平时狗在盆前面：不扣")


class SamoyedNestTests(GoingHomeTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None
    HOME_WAY = ["sitting", "standing", "lying"]

    def test_picking_up_the_ball_gets_it_up_and_ready(self):
        """萨摩耶默认坐着——趴在窝里的拿起球在窝里坐起来看（根还抬在垫子上、前沿还盖着），圈照样满、坐着等不俯身；放下才站起来去叼。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, spot = self.home()
        self.pick_up_ball()
        self.assertIsNotNone(self.step(2.5, lambda: dog.posture == "sitting" and not dog.transition), "在窝里坐起来")
        self.assertEqual((dog.lounge, pg._nest is not None, roam.task), ("sitting", True, None))
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6, msg="坐在垫子上：根还抬着")
        self.assertTrue(self.things.front_shown(BED), "前沿还盖在脚前面")
        self.assertIsNotNone(self.step(3.0, lambda: pg.ring.ready), "圈照样满")
        self.assertFalse(roam.bowing, "坐着等，不俯身")
        self.assertAlmostEqual(pg._ring_at.cy, roam.wy - 0.5 * roam.height_m * pg.ppm - spot.perch_m * math.cos(math.radians(ELEVATION)) * pg.ppm,
                               delta=0.5, msg="圈的圆心跟着身子抬到垫子上")
        self.cursor = (t.x + 2.2 * pg.ppm, roam.wy - 150.0)       # 鼠标在窝外面：叼回来放到那边
        self.put_ball_down()
        self.assertEqual(roam.task, "fetch", "满过的圈：放下也去叼")
        self.assertIsNotNone(self.step(30.0, lambda: roam.task is None and pg.ball.resting), "玩完了")
        self.step(0.3)
        self.assertEqual((dog.perch, dog.hide_shadow, pg._pad), (0.0, False, None), "走出垫子：根落回线上、影子回来")

    def test_a_bed_put_out_after_it_already_rested_in_place_is_for_next_time(self):
        """已经在原地趴下的萨摩耶，之后（不是刚摆下的那一下）有了窝：不为它起来，下次歇再去。坐着的（默认坐着）到点照样会去，见上面那几条。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        pg._idle_for = 70.0
        self.assertIsNotNone(self.step(10.0, lambda: dog.posture == "lying" and not dog.transition), "没窝：原地趴下")
        self.put(BED, settle=3.0)
        seen = set()
        self.step(20.0, lambda: seen.add((roam.task, dog.lounge)) and False)
        self.assertEqual(seen, {(None, "lying")}, "趴着的不为了新摆的窝起来")

    def test_no_nest_means_the_collie_stands_for_ever(self):
        """没摆窝：萨摩耶照旧原地坐下再趴下（tests/test_temper.py 守着），这里只看摆了不是窝的物件也一样。"""
        dog, pg = self.win.dog, self.pg
        self.start_on_floor()
        self.put(BOWL)
        self.put("bed/plain")
        self.assertIsNotNone(self.step(45.0, lambda: dog.posture == "sitting" and not dog.transition), "20 秒原地坐下")
        self.assertEqual((pg.roam.task, pg._nest, dog.perch), (None, None, 0.0))

    def test_its_first_rest_is_the_plan(self):
        self.assertEqual(self.pg._nest_after(), 20.0, "萨摩耶：计划的第一段")
        collie = self.make_window(pack_id=COLLIE)
        self.assertEqual(collie.playground._nest_after(), temper.NEST_AFTER_S)


class SamoyedHouseTests(HouseTests):
    PACK = SAMOYED
    AFTER = 20.0


class LieSpanTests(unittest.TestCase):
    """趴着占多长按模型量（狗屋门口留多远用）：两只狗各验一遍，和方案阶段量的对得上（边牧身后 0.62、身前 0.41；萨摩耶 0.49 / 0.40 米）。"""

    def test_each_dog_is_measured_from_its_own_model(self):
        from tests.room_base import HAS, load
        from widget.dogctl import DogController
        for pack_id, rear, fore in ((COLLIE, 0.62, 0.41), (SAMOYED, 0.49, 0.40)):
            with self.subTest(pack_id):
                if not HAS.get(pack_id):
                    self.skipTest(f"{pack_id} 的模型文件不在")
                dog = DogController(load(pack_id)[1], seed=1)
                got = dog.lie_span()
                self.assertAlmostEqual(got[0], rear, delta=0.02)
                self.assertAlmostEqual(got[1], fore, delta=0.02)
                self.assertIs(dog.lie_span(), got, "量一次记着")


@unittest.skipUnless(HAS_PROPS, "买来的物件模型不在（models/props/，不入 git）")
class RealNestTests(RoomCase):
    """真的狗窝、狗屋（买来的模型）：狗歇的地方按真模型、真包里的数对不对。"""
    PACK = COLLIE

    def make_window(self, settings=None, pack_id=None):
        win = super().make_window(settings, pack_id)
        self.addCleanup(lambda: [w.hide() for t in win.playground.things.items.values() for w in (t.win, t.front_win) if w is not None])
        return win

    def spot(self, key, x=140.0):
        if not self.pg.active:
            self.start_on_floor(x=x)
            self.step(0.3)
        self.win.set_thing(key, True)
        self.step(1.5)
        t = self.pg.things.items[key]
        return t, self.pg.things.spot_of(t)

    def test_the_bed_is_long_enough_and_the_dog_sits_on_the_cushion(self):
        dog, pg = self.win.dog, self.pg
        for key, rise in (("bed/blue", 0.075), ("bed/grey", 0.075), ("bed/paws", 0.06), ("bed/orange", 0.06)):
            with self.subTest(key):
                t, spot = self.spot(key)
                k = t.geo[1]
                self.assertAlmostEqual(k, 1.6 * self.pack.height_m / 0.8, places=3, msg="窝按狗的身高放大")
                self.assertAlmostEqual(spot.x, t.x, delta=0.5)
                self.assertAlmostEqual(spot.perch_m, (t.lay.low_m + rise * k) / math.cos(math.radians(ELEVATION)), places=6)
                self.assertTrue(0.12 < spot.perch_m < 0.3, spot.perch_m)
                rear, fore = (v * QUARTER_COS for v in dog.lie_span())
                wide = (t.lay.left_m + t.lay.right_m)
                self.assertLess(rear + fore, wide + 0.12, "趴着的身长（四分之三朝向）窝里放得下（尾巴尖最多伸出一点）")
                front = pg.things._front_model(t)
                self.assertTrue(0 < front.mesh.vertex_count < t.model.mesh.vertex_count, "切得出前沿")
                self.win.set_thing(key, False)
                self.step(0.5)

    def test_the_gable_house_leaves_the_door_clear_and_the_flat_one_half(self):
        dog, pg = self.win.dog, self.pg
        t, _ = self.spot("doghouse/gable")
        t.x = self.ag.x() + 0.3 * self.ag.width()
        pg.things._seat(t, pg.things._floor(0, t.x))
        pg.things._settle(t)
        spot = pg.things.spot_of(t)
        self.assertFalse(t.right_half)
        rear = dog.lie_span()[0] * QUARTER_COS * pg.ppm
        self.assertAlmostEqual(spot.x - rear, t.span()[1], delta=0.5, msg="尾巴尖正好到屋边：不压进屋里")
        self.assertEqual(spot.yaw, 330.0)
        self.win.set_thing("doghouse/gable", False)
        t, spot = self.spot("doghouse/flat")
        self.assertAlmostEqual(spot.x, t.x + 0.25 * 1.3 * pg.ppm, delta=0.5)
        self.assertEqual(spot.perch_m, 0.0)

    def test_the_real_cushions_are_stepped_on_when_it_runs_across(self):
        """真狗窝的垫子（包里的 rest.half）：在两边的边沿里面；狗从上面跑过去，根抬到垫子那么高。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        left = self.ag.x() + 100.0
        self.start_on_floor(x=left)
        self.step(0.3)
        for key, half in (("bed/blue", 0.28), ("bed/grey", 0.28), ("bed/paws", 0.25), ("bed/orange", 0.25)):
            with self.subTest(key):
                self.win.set_thing(key, True)
                things = pg.things
                t = things.items[key]
                t.fresh = False                                   # 不叫狗过来趴：这里看踩着过去
                self.step(1.5)
                t.x = self.ag.x() + 0.5 * self.ag.width()
                things._seat(t, things._floor(0, t.x))
                things._settle(t)
                spot = things.spot_of(t)
                k, ppm = t.geo[1], pg.ppm
                self.assertEqual(t.style.spec["rest"]["half"], half)
                self.assertLess(half * k * ppm, 0.5 * t.width - 0.05 * k * ppm, "垫子在窝两边的边沿里面")
                self.assertEqual(things.pad_at("floor", 0, t.x + half * k * ppm - 1.0), (key, spot.perch_m))
                self.assertIsNone(things.pad_at("floor", 0, t.x + half * k * ppm + 1.0))
                top = [0.0]
                self.assertTrue(roam.go_to(roam.support, self.ag.x() + self.ag.width() - 90.0))
                self.assertIsNotNone(self.step(10.0, lambda: top.__setitem__(0, max(top[0], dog.perch)) or roam.task is None))
                self.assertAlmostEqual(top[0], spot.perch_m, places=6, msg="跑过去的时候踩上了垫子")
                self.step(0.5)
                self.assertEqual((dog.perch, pg._pad), (0.0, None))
                self.win.set_thing(key, False)
                self.step(0.5)
                self.win.place_scene(left, self.floor_y)
                roam.place(left, self.floor_y)
                roam.drop_to_support()
                self.step(0.5)

    def test_it_goes_home_to_the_real_bed(self):
        dog, pg = self.win.dog, self.pg
        t, spot = self.spot("bed/blue")
        pg._idle_for = pg._nest_after()
        self.assertIsNotNone(self.step(20.0, lambda: pg._nest is not None and dog.posture == "lying" and not dog.transition
                                       and dog.perch == pg._perch_to), "走回窝趴好")
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6)
        self.assertTrue(pg.things.front_shown("bed/blue"))


@unittest.skipUnless(HAS_PROPS, "买来的物件模型不在（models/props/，不入 git）")
class RealNestSamoyedTests(RealNestTests):
    PACK = SAMOYED


class TapNestTests(NestCase):
    """点哪个窝（狗窝、狗屋），狗就走过去在那里歇；点盆那一套不动（tests/test_bowl.py）。物件点完、拖完压回狗后面。"""

    def tap(self, t):
        at = QPointF(t.x, t.y - 5.0)
        self.things.thing_press(t, at)
        self.step(2 * DT)
        self.things.thing_release(t, at)

    def test_tapping_a_bed_brings_it_over_and_tapping_another_moves_it(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        bed = self.put(BED)
        flat = self.put(FLAT)
        self.assertIsNone(pg._nest, "摆的时候没叫它（不是刚摆下来的那一下）")
        self.tap(bed)
        self.assertEqual((roam.task, pg._nest_going.key), ("nest", BED), "点了：走过去")
        self.assertIsNotNone(self.step(20.0, self.nested), "趴进这一个")
        self.assertEqual(pg._nest.key, BED)
        self.tap(bed)
        self.assertEqual((roam.task, pg._nest.key), (None, BED), "已经趴在这一个里：不动")
        self.tap(flat)
        self.assertEqual(roam.task, "nest", "点另一个：起来过去")
        self.assertIsNone(pg._nest, "根、前沿收掉了")
        self.assertIsNotNone(self.step(20.0, self.nested))
        self.assertEqual(pg._nest.key, FLAT)

    def test_with_the_ball_in_hand_or_mid_fetch_it_does_not_come(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        bed = self.put(BED)
        self.pick_up_ball()
        self.tap(bed)
        self.assertIsNone(pg._nest_going, "球在你手上：不来")
        self.assertNotEqual(roam.task, "nest")
        self.put_ball_down()
        self.step(0.5)
        pg.ball.throw(-600.0, -300.0, self.win.ppm)
        pg.throw_id += 1
        roam.fetch()
        self.step(0.3)
        self.tap(bed)
        self.assertEqual((roam.task, pg._nest_going), ("fetch", None), "在捡球：不来，窝只 duang")


class SamoyedTapNestTests(TapNestTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None
    HOME_WAY = ["sitting", "standing", "lying"]


class TailCurlTests(NestCase):
    """边牧趴在窝里，尾巴从窝壁穿出去——歇进狗窝时尾巴往身子这边卷（绕在近处的后腿边上），卷多少按模型和窝量，
    尾巴尖落在窝的内沿里面；起来时缓回去。萨摩耶的尾巴卷在背上，量出来不卷。狗屋（趴在门口，狗画在屋前面）不卷。"""

    def test_lying_in_a_bed_the_tail_tip_ends_inside_the_inner_edge(self):
        from widget.playground import CURL_MARGIN_M
        dog, pg = self.win.dog, self.pg
        t, spot = self.home()
        half = self.things.pad_half_m(BED)
        self.assertIsNotNone(half)
        straight = dog.tail_behind(0.0, -1.0)
        if self.PACK == COLLIE:
            self.assertGreater(straight, half - CURL_MARGIN_M, "边牧伸直的尾巴比窝的内沿长（不卷就穿出去）")
            self.assertGreater(dog.expr.curl, 0.0, "卷")
        else:
            self.assertEqual(dog.expr.curl, 0.0, "萨摩耶的尾巴卷在背上：不卷")
        if self.PACK == COLLIE:
            self.assertLessEqual(dog.tail_behind(dog.expr.curl, -1.0), half - CURL_MARGIN_M + 1e-3, "尾巴尖在窝的内沿里面")
        right = math.cos(math.radians(dog.home_yaw)) >= 0.0
        self.assertEqual(dog.expr.curl_side, -1.0 if right else 1.0, "往靠镜头那一侧卷")
        self.step(0.6)
        self.assertAlmostEqual(dog.expr.cur["curl"], dog.expr.curl, delta=0.02, msg="0.4 秒左右卷好")
        self.pick_up_ball()
        self.step(0.2)
        if self.PACK == COLLIE:
            self.assertEqual(dog.expr.curl, 0.0, "起来：缓回去")

    def test_a_doghouse_never_curls_the_tail(self):
        dog = self.win.dog
        self.home(FLAT)
        self.assertEqual(dog.expr.curl, 0.0)
        self.assertIsNone(self.things.pad_half_m(FLAT))

    @unittest.skipUnless(HAS_PROPS, "买来的狗窝模型不在")
    def test_the_real_beds_are_measured_per_model(self):
        """真的四款狗窝：边牧要卷（方垫子少一点、圆窝多一点），萨摩耶都不卷；卷完尾巴尖都在内沿里面。"""
        import json
        from widget import thing_art
        from widget.playground import CURL_MARGIN_M
        dog = self.win.dog
        raw = json.loads((config.ROOT / "packs" / "bed" / "pack.json").read_text(encoding="utf-8"))["thing"]
        k = thing_art.scale_of(raw, self.win.pack.height_m)
        curls = {}
        for style in raw["styles"]:
            rest = {**raw.get("rest", {}), **style.get("rest", {})}
            inner = float(rest["half"]) * k - CURL_MARGIN_M
            c = curls[style["id"]] = dog.tail_curl(inner, True)
            if self.PACK == COLLIE:
                self.assertLessEqual(dog.tail_behind(c, -1.0), inner + 1e-3, style["id"])
        if self.PACK == COLLIE:
            self.assertTrue(all(c > 0.0 for c in curls.values()), curls)
            self.assertLess(curls["blue"], curls["paws"], "圆窝小：卷得多")
        else:
            self.assertEqual(set(curls.values()), {0.0}, curls)


class SamoyedTailCurlTests(TailCurlTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None
    HOME_WAY = ["sitting", "standing", "lying"]
