"""台子：摆着的台子（现在列出来的只有平顶狗屋；薄板的写法还认）是混进窗口表的假窗口框（窗口号是负的），狗和球「窗口上沿」那一套原样生效。
前一半是空间里的纯几何（widget/world.py，不碰 Qt）；后一半真窗口（offscreen）+ 假设置（卸载器挡住）+ 假的款表（tests/test_nest.py 的底子）；
真平顶狗屋的那一类买来的模型不在就跳过。边牧、萨摩耶各跑一遍（跳多高、起跳落地的数按模型量）。"""
import math
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF

from tests.room_base import COLLIE, DT, SAMOYED, RoomCase
from tests.test_nest import HAS_PROPS, NestCase
from tests.test_thing_art import glb
from tests.test_things import box
from widget import native, packs
from widget.render import ELEVATION
from widget.world import Area, Ball, Support, World, WindowFrame, step_ball

BENCH, HOUSE, BOWL = "bench/bench", "doghouse/flat", "bowl/food"
CE = math.cos(math.radians(ELEVATION))


class BoardGeometryTests(unittest.TestCase):
    """一块薄板、一个实心盒子当窗口框放进空间：台面、三条边、球。"""

    def setUp(self):
        self.world = World([Area(0, 0, 1000, 800)], 18.0)
        self.floor = self.world.floor_y(0)
        self.board = WindowFrame(-1, 0, 400.0, 600.0, 300.0, 20.0)                      # 薄板：离地 182，厚 20
        self.block = WindowFrame(-2, 0, 400.0, 600.0, 300.0, self.floor - 600.0)        # 实心盒子：厚到地

    def roll(self, frame, ball, seconds=4.0):
        tops = self.world.window_tops([frame], 30.0, 10.0)
        edges = self.world.window_edges([frame])
        events, xs = [], []
        for _ in range(int(seconds * 120)):
            events += step_ball(self.world, ball, 1 / 120, 240.0, tops, edges)
            xs.append(ball.x)
        return events, xs

    def test_a_board_gives_a_top_and_three_edges(self):
        tops = self.world.window_tops([self.board], 30.0, 10.0)
        self.assertEqual(tops, [Support(400.0, 700.0, 600.0, "window", -1)], "台面是一条能站的线，窗口号是负的")
        edges = {(e.side, e.at, e.lo, e.hi) for e in self.world.window_edges([self.board])}
        self.assertEqual(edges, {("left", 400.0, 600.0, 620.0), ("right", 700.0, 600.0, 620.0), ("bottom", 620.0, 400.0, 700.0)})
        solid = {(e.side, e.at, e.lo, e.hi) for e in self.world.window_edges([self.block])}
        self.assertEqual(solid, {("left", 400.0, 600.0, self.floor), ("right", 700.0, 600.0, self.floor)}, "厚到地的没有下边")

    def test_a_ball_dropped_on_the_board_stays_there(self):
        b = Ball(550.0, 300.0, 11.0, resting=False)
        events, _ = self.roll(self.board, b)
        self.assertTrue(b.resting)
        self.assertEqual((b.on, round(b.y + b.r, 3)), (("window", -1), 600.0))
        self.assertIn("floor", events, "在台面上弹过")

    def test_a_ball_hitting_the_side_of_the_board_bounces_back(self):
        b = Ball(370.0, 610.0, 8.0, vx=1500.0, vy=0.0, resting=False)
        events, xs = self.roll(self.board, b, 0.1)
        self.assertIn("window", events)
        self.assertLess(max(xs), 400.0, "没穿过去")
        self.assertLess(b.vx, 0.0)

    def test_a_ball_rolls_under_the_board_but_not_through_the_block(self):
        b = Ball(250.0, self.floor - 11.0, 11.0, on=("floor", 0))
        b.throw(700.0, 0.0, 240.0)
        events, xs = self.roll(self.board, b)
        self.assertNotIn("window", events, "薄板：球从底下滚过去")
        self.assertGreater(max(xs), 450.0)
        b = Ball(250.0, self.floor - 11.0, 11.0, on=("floor", 0))
        b.throw(700.0, 0.0, 240.0)
        events, xs = self.roll(self.block, b)
        self.assertIn("window", events, "实心的：弹回来")
        self.assertLessEqual(max(xs), 400.0 - 11.0 + 1.0)


def platform_styles(folder: Path) -> list:
    """假的款表里的两个台子：一块薄板（座面 0.44 米，照长椅写的——薄板的写法还认，这里挂在列得出来的角色下面验）、
    一个平顶狗屋（实心盒子，也是窝）。"""
    def style(key, role, size, **spec):
        path = folder / (key.replace("/", "_") + ".glb")
        path.write_bytes(glb(box(*size)))
        return packs.ThingStyle(key=key, pack=key.split("/")[0], names={"en": key}, model=path, thumb=folder / "none.png",
                                spec={"group": "park", "role": role, "order": 10, "scale": 1.0, "yaw": 0, "shadow": True, **spec})
    return [style(BENCH, "house", (1.6, 0.9, 0.5), platform={"y": 0.44, "x0": -0.8, "x1": 0.8, "thick": 0.08}),
            style(HOUSE, "house", (1.2, 0.7, 0.9), rest={"x": 0.25, "rise": 0.0, "side": 0}, platform={"y": 0.7, "x0": -0.6, "x1": 0.6, "thick": 0.75})]


class PlatformCase(NestCase):
    def setUp(self):
        super().setUp()
        self.fakes[:] = [f for f in self.fakes if f.key != HOUSE] + platform_styles(self.fakes[0].model.parent)
        self.things.use(packs.things())

    def stage(self, key=BENCH, x=None, dog_x=120.0):
        """狗站在地面左边，台子摆在屏幕中间偏右（两头都留着起跳的空地）。返回 (物件, 台面那条线)。"""
        pg = self.pg
        if not pg.active:
            self.start_on_floor(x=dog_x)
            self.step(0.3)
        t = self.put(key)
        t.x = self.ag.x() + 0.6 * self.ag.width() if x is None else x
        self.things._seat(t, self.things._floor(0, t.x))
        self.things._settle(t)
        top = next((s for s in pg.supports() if s.kind == "window" and s.key == t.number), None)
        return t, top

    def climb(self, t, top):
        roam = self.pg.roam
        self.assertTrue(roam.go_to(top, t.x), "够得着")
        self.assertIsNotNone(self.step(12.0, lambda: roam.task is None), "跳上去了")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", t.number))
        self.assertAlmostEqual(roam.wy, top.y, delta=0.5)


class PlatformTests(PlatformCase):
    def test_nothing_staged_means_the_window_table_is_just_the_real_windows(self):
        pg = self.pg
        self.start_on_floor()
        self.put("bed/blue")
        self.add_window(7, 300.0, self.floor_y - 300.0, 300.0)
        self.assertIs(pg.frames, pg._native_frames, "没有台子：窗口表就是问系统得到的那份")
        self.assertEqual([f.number for f in pg.frames], [7])
        self.assertEqual(self.things.frames(), [])

    def test_a_bench_is_a_fake_window_frame_with_a_negative_number(self):
        pg = self.pg
        t, top = self.stage()
        f = self.things.frame_of(t)
        self.assertLess(t.number, 0)
        self.assertEqual((f.number, pg.frames[0]), (t.number, f), "排在窗口表最前面")
        ppm = pg.ppm
        self.assertAlmostEqual(f.y, t.y - (t.lay.low_m + 0.44 * CE) * ppm, places=6, msg="台面 = 踩的线 −（low_m + 台面高 × cos 俯视角）")
        self.assertAlmostEqual(f.x, t.x - 0.8 * ppm, places=6)
        self.assertAlmostEqual(f.w, 1.6 * ppm, places=6)
        self.assertAlmostEqual(f.h, 0.08 * CE * ppm, places=6, msg="薄板")
        self.assertIsNotNone(top, "狗站得上去")
        self.assertEqual((top.x0, top.x1, top.y), (f.x, f.x + f.w, f.y))
        self.assertEqual(pg._frame(t.number), (f.x, f.y, f.w, f.h))
        self.assertTrue(pg.window_listed(t.number))
        self.assertEqual(pg._native_frames, [], "真窗口那一份里没有它")
        self.assertIn(t.number, [s.key for s in pg.ball_platforms()], "球也能停")
        self.assertEqual({e.side for e in pg.ball_edges() if e.key == t.number}, {"left", "right", "bottom"})
        house, _ = self.stage(HOUSE, x=self.ag.x() + 150.0)
        self.assertNotEqual(house.number, t.number)
        hf = self.things.frame_of(house)
        self.assertAlmostEqual(hf.y + hf.h, house.y, places=6, msg="厚到地：实心盒子，到它踩的线为止")
        self.assertEqual({e.side for e in pg.ball_edges() if e.key == house.number}, {"left", "right"})

    def test_the_dog_jumps_onto_the_bench_and_stays(self):
        pg, roam = self.pg, self.pg.roam
        t, top = self.stage()
        with mock.patch.object(native, "window_frame", side_effect=AssertionError("台子不问系统")), \
                mock.patch.object(native, "window_covered", side_effect=AssertionError("台子不会被盖住，不问")):
            self.climb(t, top)
            self.step(3.0)
        self.assertEqual((roam.task, roam.support.key, roam.home.kind, roam.home.key), (None, t.number, "window", t.number))

    def test_picking_the_bench_up_drops_the_dog(self):
        pg, roam = self.pg, self.pg.roam
        t, top = self.stage()
        self.climb(t, top)
        self.grab(t, (t.x, t.y - 150.0))
        self.assertEqual(self.things.frames(), [], "拿着的不算台子")
        self.assertFalse(pg.window_listed(t.number))
        self.assertIsNotNone(self.step(1.0, lambda: roam.task == "fall"), "照窗口没了：原地掉")
        self.assertIsNotNone(self.step(5.0, lambda: roam.task is None))
        self.assertEqual(roam.support.kind, "floor")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.5)
        self.things.thing_release(t, QPointF(*t.pointer))
        self.step(1.5)
        self.assertEqual([f.number for f in pg.frames], [t.number], "落定了又是台子")

    def test_putting_it_away_takes_the_platform_with_it(self):
        pg, roam = self.pg, self.pg.roam
        t, top = self.stage()
        self.climb(t, top)
        self.win.set_thing(BENCH, False)
        self.assertEqual(pg.frames, [])
        self.assertIsNotNone(self.step(5.0, lambda: roam.task is None and roam.support is not None and roam.support.kind == "floor"), "收起：狗落到地面")

    def test_a_ball_thrown_onto_the_bench_stays_and_the_dog_goes_up_for_it(self):
        pg, roam = self.pg, self.pg.roam
        t, top = self.stage()
        b = pg.ball
        b.x, b.y, b.vx, b.vy, b.resting, b.rolling, b.on = t.x, top.y - 200.0, 0.0, 0.0, False, False, None
        pg.throw_id += 1
        self.assertIsNotNone(self.step(4.0, lambda: b.resting), "球停住了")
        self.assertEqual(b.on, ("window", t.number), "停在台面上")
        self.assertAlmostEqual(b.y + b.r, top.y, delta=0.5)
        self.cursor = (160.0, self.floor_y - 150.0)
        roam.fetch()
        self.assertIsNotNone(self.step(15.0, lambda: roam.carrying), "狗跳上去叼到了")
        self.assertIsNotNone(self.step(20.0, lambda: roam.task is None), "叼下来放在鼠标旁边")
        self.assertAlmostEqual(b.x, self.cursor[0], delta=0.6 * pg.ppm)
        self.assertEqual(b.on, ("floor", 0))

    def test_taking_the_bench_from_under_the_ball_drops_it(self):
        pg = self.pg
        t, top = self.stage()
        b = pg.ball
        b.x, b.y, b.vx, b.vy, b.resting, b.rolling, b.on = t.x + 40.0, top.y - 60.0, 0.0, 0.0, False, False, None
        pg.throw_id += 1
        self.assertIsNotNone(self.step(4.0, lambda: b.resting))
        self.assertEqual(b.on, ("window", t.number))
        self.grab(t, (t.x - 300.0, t.y - 100.0))
        self.assertIsNotNone(self.step(3.0, lambda: b.resting and b.on == ("floor", 0)), "台子拿走：球掉到地面")

    def test_a_ball_rolls_under_the_bench_but_bounces_off_the_house(self):
        pg = self.pg
        t, _ = self.stage()
        b = pg.ball
        f = self.things.frame_of(t)
        b.x, b.y, b.on, b.resting = f.x - 80.0, self.floor_y - b.r, ("floor", 0), False
        b.throw(2.5 * pg.ppm, 0.0, pg.ppm)
        pg.throw_id += 1
        seen = []
        self.step(3.0, lambda: seen.append(b.x) and False)
        self.assertGreater(max(seen), f.x + 40.0, "长椅是薄板：球从底下滚过去")
        self.win.set_thing(BENCH, False)
        self.step(0.5)
        house, _ = self.stage(HOUSE)
        hf = self.things.frame_of(house)
        b.x, b.y, b.on, b.resting, b.rolling = hf.x - 80.0, self.floor_y - b.r, ("floor", 0), False, False
        b.throw(2.5 * pg.ppm, 0.0, pg.ppm)
        pg.throw_id += 1
        seen = []
        self.step(3.0, lambda: seen.append(b.x) and False)
        self.assertLessEqual(max(seen), hf.x - b.r + 1.0, "平顶狗屋是实心的：弹回来")

    def test_with_hop_windows_off_the_platform_is_still_there(self):
        """「窗口当台子」关着：别的 App 的窗口不算，你摆的台子照留，也不去问系统。"""
        pg, roam = self.pg, self.pg.roam
        t, top = self.stage()
        self.add_window(7, 40.0, self.floor_y - 330.0, 260.0)
        self.assertEqual([f.number for f in pg.frames], [t.number, 7])
        self.win.set_play_option("hop_windows", False)
        with mock.patch.object(native, "window_frames", side_effect=AssertionError("关着不问窗口表")), \
                mock.patch.object(native, "window_frame", side_effect=AssertionError("关着不问窗口")):
            pg._frames_at = -math.inf
            pg.supports()
            self.assertEqual([f.number for f in pg.frames], [t.number], "只剩台子")
            top = next(s for s in pg.supports() if s.kind == "window")
            self.climb(t, top)
            self.step(2.0)
            self.assertEqual(roam.support.key, t.number, "站得住（不当它没了）")

    def test_things_do_not_stack_on_things(self):
        pg = self.pg
        t, top = self.stage()
        bowl = self.put("bowl/food")
        self.grab(bowl, (t.x, top.y - 120.0))
        self.things.thing_release(bowl, QPointF(t.x, top.y - 130.0))
        self.assertIsNotNone(self.step(2.0, lambda: bowl.state == "rest"))
        self.assertEqual(bowl.on, ("floor", 0), "盆在长椅上方松手：落到地面，不停在长椅上")
        self.assertAlmostEqual(bowl.y, self.floor_y, delta=0.5)

    def test_a_bench_on_a_real_window_moves_with_it_and_so_does_the_dog(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=120.0)
        self.step(0.3)
        t = self.put(BENCH)
        base = self.add_window(7, 150.0, self.floor_y - 120.0, 640.0, 60.0)
        self.grab(t, (480.0, base.y - 150.0))
        self.things.thing_release(t, QPointF(480.0, base.y - 160.0))
        self.assertIsNotNone(self.step(2.0, lambda: t.state == "rest"))
        self.assertEqual(t.on, ("window", 7), "长椅落在真窗口上")
        top = next(s for s in pg.supports() if s.key == t.number)
        self.win.place_scene(t.x, top.y)                                  # 狗直接放到长椅上（从地面要先上那个窗口，这块假屏太窄排不出路）
        roam.place(t.x, top.y)
        roam.drop_to_support()
        self.step(0.5)
        self.assertEqual((roam.task, roam.support.key), (None, t.number))
        x, wx = self.things.frame_of(t).x, roam.wx
        self.frames[7] = (120.0, self.floor_y - 120.0, 640.0, 60.0)        # 窗口往左挪了 30
        self.step(1.0)
        self.assertAlmostEqual(self.things.frame_of(t).x, x - 30.0, delta=0.5)
        self.assertEqual(pg.frames[0], self.things.frame_of(t), "窗口表里的台子跟着挪")
        self.assertAlmostEqual(roam.wx, wx - 30.0, delta=1.0, msg="站在长椅上的狗也跟着")
        self.assertEqual(roam.support.key, t.number)
        del self.frames[7]                                                # 窗口关了：长椅落下去，狗也掉下去
        pg._sups = None
        self.assertIsNotNone(self.step(4.0, lambda: t.state == "rest" and t.on == ("floor", 0)))
        self.assertIsNotNone(self.step(5.0, lambda: roam.task is None and roam.support is not None), "狗落定了")
        self.assertIn((roam.support.kind, roam.support.key), {("floor", 0), ("window", t.number)})

    def test_the_flat_house_is_a_nest_and_a_platform_at_once(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        t, top = self.stage(HOUSE)
        self.assertIsNotNone(top)
        spot = self.things.spot_of(t)
        self.assertEqual((spot.support.kind, spot.perch_m), ("floor", 0.0), "歇在门前的地上")
        self.climb(t, top)
        self.assertAlmostEqual(roam.wy, t.y - (t.lay.low_m + 0.7 * CE) * pg.ppm, delta=0.5, msg="站在屋顶上")
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(25.0, lambda: pg._nest is not None and dog.posture == "lying" and not dog.transition), "该歇了：跳下来趴在门前")
        self.assertEqual(roam.support.kind, "floor")


class SamoyedPlatformTests(PlatformTests):
    PACK = SAMOYED
    AFTER = 20.0


@unittest.skipUnless(HAS_PROPS, "买来的物件模型不在（models/props/，不入 git）")
class RealPlatformTests(RoomCase):
    """真的平顶狗屋（买来的模型）：屋顶在包里写的那么高、那么宽，狗跳得上去。"""
    PACK = COLLIE

    def make_window(self, settings=None, pack_id=None):
        win = super().make_window(settings, pack_id)
        self.addCleanup(lambda: [t.win.hide() for t in win.playground.things.items.values()])
        return win

    def test_the_tops_are_where_the_packs_say_and_the_dog_gets_up(self):
        from widget import thing_art
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=120.0)
        self.step(0.3)
        self.win.set_thing("bench/bench", True)
        self.assertEqual((list(pg.things.items), self.win.thing_on("bench/bench")), ([], False), "长椅摆不出来了")
        for key, y, half, solid in (("doghouse/flat", 0.655, 0.58, True),):
            with self.subTest(key):
                self.win.set_thing(key, True)
                things = pg.things
                t = things.items[key]
                t.fresh = False                                   # 这里看屋顶：不叫狗过来趴（落定就过来趴的那条路在 tests/test_nest.py）
                self.step(1.5)
                t.x = self.ag.x() + 0.62 * self.ag.width()
                things._seat(t, things._floor(0, t.x))
                things._settle(t)
                k, ppm = t.geo[1], pg.ppm
                f = things.frame_of(t)
                self.assertAlmostEqual(t.y - f.y, (t.lay.low_m + y * k * CE) * ppm, places=6)
                self.assertAlmostEqual(f.w, 2 * half * k * ppm, places=6)
                self.assertEqual(abs(f.y + f.h - t.y) < 1e-6, solid, "平顶狗屋厚到地")
                raw = thing_art.load_static(t.style.model).mesh.positions
                near = [raw[i] for i in range(0, len(raw), 3) if abs(raw[i + 1] - y) < 0.03]
                self.assertTrue(near, "模型在包里写的那个高度真有一层面")
                self.assertGreater(max(near) - min(near), 1.2 * half, "而且有台面那么宽")
                top = next(s for s in pg.supports() if s.kind == "window" and s.key == t.number)
                self.assertTrue(roam.go_to(top, t.x))
                self.assertIsNotNone(self.step(12.0, lambda: roam.task is None), "跳上去了")
                self.assertEqual(roam.support.key, t.number)
                self.assertAlmostEqual(roam.wy, f.y, delta=0.5)
                self.win.set_thing(key, False)
                self.assertIsNotNone(self.step(5.0, lambda: roam.task is None and roam.support is not None and roam.support.kind == "floor"))
                self.win.place_scene(120.0, self.floor_y)
                roam.place(120.0, self.floor_y)
                roam.drop_to_support()
                self.step(0.5)


@unittest.skipUnless(HAS_PROPS, "买来的物件模型不在（models/props/，不入 git）")
class RealPlatformSamoyedTests(RealPlatformTests):
    PACK = SAMOYED
