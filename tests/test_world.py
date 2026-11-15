"""灵动交互的空间（widget/world.py）：几块屏拼成的房间、球的物理、狗的路线。纯几何，不用 Qt、不用模型。"""
import unittest

from widget.world import Area, Ball, BallPhysics, Leaper, LeapSpec, Support, World, WindowFrame, blocks_from, plan_route, step_ball, support_below, support_under

PPM = 240.0
LAPTOP = Area(-1512, 491, 0, 1440, "laptop")          # 以前的桌面：笔记本在左，底边和宽屏对齐
WIDE = Area(0, 30, 3440, 1359, "wide")                # 宽屏：菜单栏 30、Dock 81
MAC = Area(745, -949, 2257, 0, "mac")                 # 现在的桌面：MacBook 摆在宽屏正上方
MAC_SCREEN, WIDE_SCREEN = Area(745, -982, 2257, 0), Area(0, 0, 3440, 1440)


def run(world, b, seconds, platforms=(), edges=()):
    events = []
    for _ in range(int(seconds * 120)):
        events += step_ball(world, b, 1 / 120, PPM, platforms, edges)
    return events


class StackedScreensTests(unittest.TestCase):
    """上下摆的两块屏（球扔到上面那块屏，该掉到下面那块，不该停在上面那块的底边）。"""

    def setUp(self):
        self.w = World([MAC, WIDE], floor_margin=20, screens=[MAC_SCREEN, WIDE_SCREEN])

    def test_the_upper_screen_has_no_floor_where_the_lower_one_is_below(self):
        self.assertEqual([(f.key, f.y) for f in self.w.floors], [(1, 1339)], "MacBook 整个摆在宽屏上面：它的底边不是地面")
        self.assertEqual(len(self.w.passages), 1)
        p = self.w.passages[0]
        self.assertEqual((p.left, p.top, p.right, p.bottom), (745, 0, 2257, 30), "中间隔着宽屏的菜单栏：是过道")
        self.assertTrue(self.w.is_open(1500, 15))
        self.assertFalse(self.w.is_open(300, 15), "过道外面的菜单栏还是墙")
        wider = World([Area(0, -900, 3000, 0), WIDE], floor_margin=20, screens=[Area(0, -930, 3000, 0), WIDE_SCREEN])
        self.assertEqual(sorted((f.key, f.x0, f.x1) for f in wider.floors), [(1, 0, 3440)], "上面那块比下面窄或一样宽：没有地面")
        side = World([Area(0, -900, 3600, 0), WIDE], floor_margin=20, screens=[Area(0, -930, 3600, 0), WIDE_SCREEN])
        self.assertIn((0, 3440, 3600), [(f.key, f.x0, f.x1) for f in side.floors], "上面那块伸出去、底下没屏的那段还是地面")

    def test_a_ball_dropped_on_the_upper_screen_falls_through_to_the_lower_floor(self):
        b = Ball(1500, -600, 11, resting=False)
        run(self.w, b, 6.0)
        self.assertTrue(b.resting)
        self.assertAlmostEqual(b.y, 1339 - 11, delta=0.6, msg="穿过宽屏的菜单栏，落在宽屏的地面上")

    def test_a_ball_thrown_up_flies_into_the_upper_screen_and_comes_back(self):
        b = Ball(1500, 1300, 11)
        b.throw(0, -5000, PPM)
        top = b.y
        for _ in range(int(6.0 * 120)):
            step_ball(self.w, b, 1 / 120, PPM)
            top = min(top, b.y)
        self.assertLess(top, -100, "飞进了上面那块屏")
        self.assertAlmostEqual(b.y, 1339 - 11, delta=0.6, msg="再掉回下面的地面")
        side = Ball(300, 1300, 11)
        side.throw(0, -5000, PPM)
        events = run(self.w, side, 0.6)
        self.assertIn("ceiling", events, "上面没有屏的地方：菜单栏照旧是天花板")

    def test_the_dog_can_jump_down_from_a_window_on_the_upper_screen(self):
        top = Support(900, 1600, -500, "window", 5)
        floor = self.w.floors[0]
        r = plan_route([floor, top], top, 1200, floor, 1300, 600, 240, 50, Leaper(self.w, PPM))
        self.assertTrue(r.reachable)
        self.assertEqual([(l.kind, l.support) for l in r.legs if l.kind == "jump"], [("jump", floor)], "从上面那块屏的窗口一下跳到下面的地面")


class WindowEdgeTests(unittest.TestCase):
    """窗口从外面撞是实心的（球碰到别的软件的左右边、下边也要弹回来）。"""

    def setUp(self):
        self.w = World([WIDE], floor_margin=20)
        self.frames = [WindowFrame(1, 9, 1500, 500, 600, 400)]
        self.edges = self.w.window_edges(self.frames)

    def test_visible_edges_of_a_window(self):
        self.assertEqual(sorted((e.side, e.at, e.lo, e.hi) for e in self.edges),
                         [("bottom", 900, 1500, 2100), ("left", 1500, 500, 900), ("right", 2100, 500, 900)])
        front = [WindowFrame(2, 9, 1400, 600, 200, 150)] + self.frames      # 前面一个小窗口挡住左边的一截
        left = sorted((e.lo, e.hi) for e in self.w.window_edges(front) if e.key == 1 and e.side == "left")
        self.assertEqual(left, [(500, 600), (750, 900)], "被前面的窗口挡住的那段不算")
        full = self.w.window_edges([WindowFrame(3, 9, 0, 30, 3440, 1329)])
        self.assertEqual(full, [], "最大化的窗口不算")
        tall = self.w.window_edges([WindowFrame(4, 9, 400, 300, 500, 2000)])
        self.assertEqual({(e.side, e.hi) for e in tall}, {("left", 1339), ("right", 1339)}, "竖边最多到地面；下边在地面以下的不要")

    def test_a_ball_from_outside_bounces_off_the_sides_and_the_bottom(self):
        b = Ball(1300, 700, 11, resting=False)
        b.throw(2500, 0, PPM)
        events = run(self.w, b, 0.25, (), self.edges)
        self.assertIn("window", events)
        self.assertLess(b.x, 1500, "撞到左边弹回来")
        r = Ball(2300, 700, 11, resting=False)
        r.throw(-2500, 0, PPM)
        run(self.w, r, 0.25, (), self.edges)
        self.assertGreater(r.x, 2100, "撞到右边弹回来")
        up = Ball(1800, 1200, 11, resting=False)
        up.throw(0, -3000, PPM)
        highest = up.y
        for _ in range(60):
            step_ball(self.w, up, 1 / 120, PPM, (), self.edges)
            highest = min(highest, up.y)
        self.assertGreaterEqual(highest, 900 + 11 - 1, "从下面往上撞到窗口下边：弹下去")

    def test_a_ball_in_front_of_a_window_gets_out_freely(self):
        b = Ball(1800, 700, 11, resting=False)
        b.throw(2500, 0, PPM)
        events = run(self.w, b, 0.3, (), self.edges)
        self.assertNotIn("window", events, "本来就在窗口前面：往外走不挡")
        self.assertGreater(b.x, 2100)

    def test_a_ball_rolling_on_the_floor_bounces_off_a_window_standing_on_it(self):
        frames = [WindowFrame(1, 9, 1500, 900, 600, 600)]                  # 窗口下边在地面以下：竖边一直到地面
        edges = self.w.window_edges(frames)
        b = Ball(1000, 1339 - 11, 11)
        b.throw(1800, 0, PPM)
        run(self.w, b, 3.0, (), edges)
        self.assertLess(b.x, 1500, "滚过去撞到窗口的左边，弹回来停在外面")


class WorldGeometryTests(unittest.TestCase):
    def test_floors_sit_above_each_screens_usable_bottom_and_join_when_level(self):
        w = World([LAPTOP, WIDE], floor_margin=20)
        self.assertEqual(len(w.floors), 2, "两块屏底边不一样高：两条地面")
        self.assertEqual({f.y for f in w.floors}, {1420, 1339})
        level = World([Area(0, 0, 1000, 500), Area(1000, 0, 3000, 500)], floor_margin=10)
        self.assertEqual(len(level.floors), 2, "一样高也各是各的：狗过交界时跳过去（窗口骑在两块屏中间只显示一半）")
        a, b = level.floors
        r = plan_route(level.floors, a, 200, b, 2500, 500, 240, 50, Leaper(level, PPM))
        self.assertEqual([l.kind for l in r.legs], ["run", "jump", "run"], "跑到交界、跳过去、接着跑")

    def test_window_tops_skip_covered_parts_menu_bar_and_maximised_windows(self):
        w = World([WIDE], floor_margin=20)
        frames = [WindowFrame(2, 9, 500, 700, 400, 300),     # 最前面，盖住后面那个上沿的中间一段
                  WindowFrame(1, 9, 300, 800, 900, 400),
                  WindowFrame(3, 9, 0, 30, 3440, 1329),      # 最大化：不算
                  WindowFrame(4, 9, 2000, 60, 600, 400)]     # 上沿离菜单栏太近，站不下狗
        tops = w.window_tops(frames, min_width=80, headroom=200)
        spans = sorted((t.key, t.x0, t.x1) for t in tops)
        self.assertEqual(spans, [(1, 300, 500), (1, 900, 1200), (2, 500, 900)])


    def test_dog_platforms_can_be_measured_from_the_very_top_of_the_screen(self):
        """狗要能站到紧贴屏幕顶的窗口上（头伸进菜单栏那条，画在菜单栏上面）：从整块屏的最上沿量，不从菜单栏下沿量。"""
        w = World([WIDE], floor_margin=20, screens=[WIDE_SCREEN])
        frames = [WindowFrame(1, 9, 500, 200, 600, 400)]
        self.assertEqual(w.window_tops(frames, 80, 0.82 * PPM), [], "从菜单栏下沿量：只有 170 像素，站不下")
        self.assertEqual([t.key for t in w.window_tops(frames, 80, 0.82 * PPM, from_screen_top=True)], [1], "从屏幕最上沿量：200 像素，站得下")


class BallPhysicsTests(unittest.TestCase):
    def test_ball_bounces_rolls_and_comes_to_rest_on_the_floor(self):
        w = World([WIDE], floor_margin=20)
        b = Ball(1000, 600, 11)
        b.throw(1500, -900, PPM)
        events = run(w, b, 8.0)
        self.assertTrue(b.resting)
        self.assertAlmostEqual(b.y, 1339 - 11, delta=0.6, msg="停在地面上")
        self.assertIn("floor", events)
        self.assertGreater(b.x, 1000, "往右扔，停在右边")

    def test_walls_keep_the_ball_inside_and_it_never_escapes(self):
        w = World([WIDE], floor_margin=20)
        for vx, vy in ((9000, -3000), (-9000, -6000), (0, -9000), (4000, 4000)):
            b = Ball(1700, 700, 11)
            b.throw(vx, vy, PPM)
            events = run(w, b, 10.0)
            self.assertTrue(WIDE.contains(b.x, b.y), (vx, vy, b.x, b.y))
            self.assertTrue(b.resting)
            self.assertTrue(any(e in ("wall", "ceiling") for e in events), (vx, vy))

    def test_ball_flies_into_the_next_screen_and_lands_on_its_lower_floor(self):
        w = World([LAPTOP, WIDE], floor_margin=20)
        b = Ball(300, 1000, 11)
        b.throw(-2600, -600, PPM)
        run(w, b, 8.0)
        self.assertLess(b.x, 0, "飞过交界，落在笔记本上")
        self.assertAlmostEqual(b.y, 1420 - 11, delta=0.6)
        back = Ball(-200, 1300, 11)
        back.throw(3500, -100, PPM)
        run(w, back, 8.0)
        self.assertTrue(w.is_open(back.x, back.y))
        self.assertAlmostEqual(back.y + back.r, 1339 if back.x >= 0 else 1420, delta=0.6, msg="不管落在哪块屏，都在那块屏的地面上")

    def test_rolling_off_the_higher_floor_drops_onto_the_lower_one(self):
        w = World([LAPTOP, WIDE], floor_margin=20)
        b = Ball(200, 1339 - 11, 11)
        b.throw(-1400, 0, PPM)
        run(w, b, 6.0)
        self.assertLess(b.x, 0)
        self.assertAlmostEqual(b.y, 1420 - 11, delta=0.6, msg="宽屏的地面比笔记本高：滚过去掉下来")

    def test_ball_lands_on_a_window_top_and_rolls_off_its_end(self):
        w = World([WIDE], floor_margin=20)
        top = Support(1000, 1400, 900, "window", 7)
        b = Ball(1100, 600, 11)
        run(w, b, 3.0, [top])
        self.assertTrue(b.resting)
        self.assertEqual(b.on, ("window", 7))
        self.assertAlmostEqual(b.y, 900 - 11, delta=0.6)
        b.throw(700, 0, PPM)
        run(w, b, 4.0, [top])
        self.assertEqual(b.on, ("floor", 0), "滚到窗口边上掉下去，落在地面")
        gone = Ball(1100, 889, 11, on=("window", 7))
        run(w, gone, 3.0, [])
        self.assertAlmostEqual(gone.y, 1339 - 11, delta=0.6, msg="窗口没了：球掉下去")

    def test_a_ball_left_outside_every_screen_comes_back_to_a_floor(self):
        w = World([WIDE], floor_margin=20)
        b = Ball(5000, 5000, 11, resting=False)
        run(w, b, 0.1)
        self.assertTrue(WIDE.contains(b.x, b.y))
        self.assertTrue(b.resting)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.w = World([LAPTOP, WIDE], floor_margin=20)
        self.wide = next(f for f in self.w.floors if f.key == 1)
        self.lap = next(f for f in self.w.floors if f.key == 0)
        self.leaper = Leaper(self.w, PPM)

    def route(self, sups, start, x, goal, gx, max_up=500, **kw):
        return plan_route(sups, start, x, goal, gx, max_up, 240, 50, self.leaper, **kw)

    def test_same_floor_is_a_single_run(self):
        r = self.route(self.w.floors, self.wide, 2000, self.wide, 600)
        self.assertEqual([(l.kind, l.x) for l in r.legs], [("run", 600)])

    def test_crossing_screens_jumps_down_at_the_border_and_back_up(self):
        r = self.route(self.w.floors, self.wide, 2000, self.lap, -600)
        self.assertTrue(r.reachable)
        self.assertEqual([l.kind for l in r.legs], ["run", "jump", "run"])
        self.assertEqual(r.legs[1].support, self.lap)
        self.assertGreater(r.legs[0].x, 0, "在宽屏这边起跳")
        self.assertLess(r.legs[1].x, 0, "落在笔记本那边")
        back = self.route(self.w.floors, self.lap, -600, self.wide, 2000)
        self.assertTrue(back.reachable, "笔记本地面低 81 像素：跳得上去")
        tall = self.route(self.w.floors, self.lap, -600, self.wide, 2000, max_up=50)
        self.assertFalse(tall.reachable, "跳不了那么高：够不着")

    def test_a_window_is_a_box_jump_up_from_outside_its_end_and_land_just_inside(self):
        """跳上方盒子是从盒子边上跳上去的，不是穿上去。"""
        top = Support(1000, 1600, 1000, "window", 3)
        sups = list(self.w.floors) + [top]
        up = self.route(sups, self.wide, 2400, top, 1300)
        self.assertTrue(up.reachable)
        self.assertEqual([l.kind for l in up.legs][-2:], ["jump", "run"])
        jump = next(l for l in up.legs if l.kind == "jump")
        self.assertEqual(jump.mode, "up")
        self.assertGreater(jump.x0, 1600, "从右边过来：在窗口右边外面起跳")
        self.assertLess(jump.x0, 1600 + 0.7 * PPM, "离窗口边半个身长")
        self.assertTrue(1600 - 0.5 * PPM <= jump.x <= 1600, "落在窗口右头里面一点")
        left = self.route(sups, self.wide, 300, top, 1300)
        jump = next(l for l in left.legs if l.kind == "jump")
        self.assertLess(jump.x0, 1000, "从左边过来：在窗口左边外面起跳")
        self.assertGreater(jump.x, 1000)

    def test_a_window_is_a_box_jump_down_from_an_end_and_land_outside(self):
        top = Support(1000, 1600, 1000, "window", 3)
        sups = list(self.w.floors) + [top]
        down = self.route(sups, top, 1300, self.wide, 2400)
        self.assertEqual([l.kind for l in down.legs][:2], ["run", "jump"])
        self.assertGreater(down.legs[0].x, 1600 - 0.4 * PPM, "先走到右头")
        self.assertGreater(down.legs[1].x, 1600, "落在窗口外面")
        self.assertEqual(down.legs[1].mode, "push", "空地够：往前蹬")
        self.assertLess(self.route(sups, top, 1100, self.wide, 300).legs[1].x, 1000, "目标在左边：走左头")

    def test_not_enough_room_drops_straight_down_from_the_edge(self):
        """空地不够不跳高，走到边上，后脚踩在边上直接落。"""
        w = World([Area(0, 0, 1400, 1000)], floor_margin=20)
        floor = w.floors[0]
        full = 1400 - 300                                            # 右边留 300 像素（1.25 米）
        top = Support(100, full, 500, "window", 3)
        r = plan_route([floor, top], top, 400, floor, 1300, 600, 240, 50, Leaper(w, PPM))
        jump = next(l for l in r.legs if l.kind == "jump")
        self.assertEqual(jump.mode, "edge", "1.25 米不够飞出去")
        self.assertGreater(jump.x, full, "落在窗口外面")
        self.assertLess(jump.x + 0.55 * PPM, 1400, "鼻子在屏幕里")
        self.assertGreater(jump.x0, full - 0.2 * PPM, "站在线头上")

    def test_no_room_on_either_side_means_no_way_up_or_down(self):
        """窗口铺满：上不去、下不来（符合直觉）。一边够就走那边。"""
        w = World([Area(0, 0, 1000, 1000)], floor_margin=20)
        floor = w.floors[0]
        wide = Support(100, 900, 500, "window", 3)
        leap = Leaper(w, PPM)
        self.assertFalse(plan_route([floor, wide], floor, 50, wide, 500, 600, 240, 50, leap).reachable, "上不去")
        self.assertFalse(plan_route([floor, wide], wide, 500, floor, 50, 600, 240, 50, leap).reachable, "下不来")
        one = Support(100, 600, 500, "window", 4)
        r = plan_route([floor, one], one, 300, floor, 50, 600, 240, 50, leap)
        self.assertTrue(r.reachable)
        self.assertGreater(next(l for l in r.legs if l.kind == "jump").x, 600, "只有右边够：走右边")
        up = plan_route([floor, one], floor, 900, one, 300, 600, 240, 50, leap)
        self.assertTrue(up.reachable, "下得来才上得去，同一个门槛")

    def test_the_room_counts_the_next_screen_only_where_it_really_is(self):
        """两块屏连着：这边没空地、那边够跳就跳过去；屏幕高低不齐时，高出去的那段还是墙。"""
        lap = Area(-1512, 491, 0, 1440, "laptop")
        lg = Area(0, 30, 3440, 1359, "lg")
        w = World([lap, lg], floor_margin=20, screens=[Area(-1512, 458, 0, 1440), Area(0, 0, 3440, 1440)])
        leap = Leaper(w, PPM)
        floors = {f.key: f for f in w.floors}
        low = Support(40, 3400, 900, "window", 5)                    # 上沿比笔记本的顶低：往左能飞进笔记本
        r = plan_route([*floors.values(), low], low, 200, floors[0], -700, 600, 240, 50, leap)
        self.assertTrue(r.reachable)
        self.assertLess(next(l for l in r.legs if l.kind == "jump").x, 0, "飞进笔记本那块屏，落在它的地面上")
        high = Support(40, 3400, 200, "window", 6)                   # 上沿比笔记本的顶还高：往左是墙
        self.assertIsNone(leap.fit(high, -1, floors[0]), "刚出窗口边就撞到屏幕边（那个高度那边没有屏）")

    def test_climbing_a_window_too_high_stays_on_the_floor(self):
        top = Support(1000, 1600, 300, "window", 4)
        far = self.route(list(self.w.floors) + [top], self.wide, 2400, top, 1300)
        self.assertFalse(far.reachable, "太高：够不着，停在离它最近的地方")
        self.assertEqual(far.legs[-1].support, self.wide)

    def test_big_drops_prefer_steps_when_there_are_some(self):
        high = Support(1000, 1600, 200, "window", 4)
        step = Support(1100, 2000, 800, "window", 5)
        sups = list(self.w.floors) + [high, step]
        direct = self.route(sups, high, 1300, self.wide, 2400, max_up=700)
        self.assertEqual([l.support for l in direct.legs if l.kind == "jump"], [self.wide], "不加代价：一下跳到底")
        stairs = self.route(sups, high, 1300, self.wide, 2400, max_up=700, soft_drop=4 * 0.8 * PPM * 0.5)
        self.assertEqual([l.support for l in stairs.legs if l.kind == "jump"], [step, self.wide], "大落差：先跳到中间那个窗口")

    def test_support_lookups(self):
        top = Support(1000, 1600, 1000, "window", 3)
        sups = list(self.w.floors) + [top]
        self.assertEqual(support_under(sups, 1200, 1004, 10), top)
        self.assertEqual(support_below(sups, 1200, 500), top)
        self.assertEqual(support_below(sups, 1200, 1100), self.wide)
        self.assertIsNone(support_under(sups, 1200, 1200, 10))


class RouteOrderTests(unittest.TestCase):
    """从人眼看，飞的路线不能穿过挡在前面的窗口。中间低洼的窗口夹在左右两个更高的窗口之间，球在它顶上。"""
    PPM = 240.0

    def world(self):
        return World([Area(0, 30, 3000, 1400)], 18.0, [Area(0, 0, 3000, 1400)])

    def plan(self, frames, start, x, goal, gx, max_up=3 * 0.8 * 240.0):
        w = self.world()
        lines = list(w.floors) + w.window_tops(frames, 100.0, 100.0)
        leaper = Leaper(w, self.PPM, LeapSpec(), blocks_from(frames))
        s = next(l for l in lines if (l.kind, l.key) == start)
        g = next(l for l in lines if (l.kind, l.key) == goal)
        return plan_route(lines, s, x, g, gx, max_up, 240.0, 0.22 * self.PPM, leaper), lines

    def frames(self):
        return [WindowFrame(1, 9, 1000.0, 850.0, 500.0, 530.0),   # 左边，高，在前面
                WindowFrame(2, 9, 1900.0, 850.0, 500.0, 530.0),   # 右边，高，在前面
                WindowFrame(3, 9, 1400.0, 1100.0, 600.0, 280.0)]  # 中间，低，在后面，左右两头被盖着

    def test_the_low_window_between_two_front_windows_cannot_be_reached_straight_from_the_floor(self):
        route, _ = self.plan(self.frames(), ("floor", 0), 2700.0, ("window", 3), 1700.0)
        self.assertTrue(route.reachable, "绕着能到")
        jumps = [l for l in route.legs if l.kind == "jump"]
        self.assertGreaterEqual(len(jumps), 2, "先跳上旁边的窗口，再下去")
        self.assertEqual(jumps[0].support.key, 2, "先上最右边那个")
        self.assertEqual(jumps[-1].support.key, 3)

    def test_with_no_room_beside_the_outer_window_the_low_window_is_out_of_reach(self):
        frames = [WindowFrame(1, 9, 20.0, 850.0, 1480.0, 530.0), WindowFrame(2, 9, 1900.0, 850.0, 1080.0, 530.0), WindowFrame(3, 9, 1400.0, 1100.0, 600.0, 280.0)]
        route, _ = self.plan(frames, ("floor", 0), 1700.0, ("window", 3), 1700.0)
        jumps = [l for l in route.legs if l.kind == "jump"]
        self.assertFalse(route.reachable, "最右边的窗口旁边没空地，左边也上不去：够不着")
        self.assertFalse(any(l.support.key == 3 for l in jumps), "不能隔着前面的窗口直接跳上去")

    def test_a_window_behind_both_ends_does_not_block(self):
        """两个窗口之间飞，路上有个比它们都靠后的窗口：不挡。"""
        frames = [WindowFrame(1, 9, 1000.0, 700.0, 400.0, 300.0),
                  WindowFrame(2, 9, 1500.0, 800.0, 400.0, 300.0),
                  WindowFrame(3, 9, 800.0, 500.0, 1500.0, 900.0)]    # 最后面，很大
        route, _ = self.plan(frames, ("window", 1), 1200.0, ("window", 2), 1700.0)
        self.assertTrue(route.reachable)
        self.assertEqual([l.support.key for l in route.legs if l.kind == "jump"], [2], "直接跳过去")

    def test_a_window_in_front_blocks_a_flight_between_two_windows(self):
        """中间夹着一个在最前面的窗口：穿不过去。"""
        frames = [WindowFrame(9, 9, 1450.0, 500.0, 100.0, 880.0),    # 最前面，竖在中间
                  WindowFrame(1, 9, 1000.0, 700.0, 450.0, 300.0),
                  WindowFrame(2, 9, 1550.0, 800.0, 400.0, 300.0)]
        w = self.world()
        lines = list(w.floors) + w.window_tops(frames, 100.0, 100.0)
        a = next(l for l in lines if l.key == 1)
        b = next(l for l in lines if l.key == 2)
        leaper = Leaper(w, self.PPM, LeapSpec(), blocks_from(frames))
        self.assertIsNone(leaper.fit(a, 1, b), "挡着")
        self.assertIsNotNone(Leaper(w, self.PPM, LeapSpec()).fit(a, 1, b), "没这个窗口就能跳")

    def test_the_two_end_windows_themselves_do_not_block(self):
        frames = [WindowFrame(1, 9, 1000.0, 900.0, 400.0, 300.0)]
        route, _ = self.plan(frames, ("floor", 0), 800.0, ("window", 1), 1200.0)
        self.assertTrue(route.reachable)
        self.assertEqual(route.legs[-2 if route.legs[-1].kind == "run" else -1].support.key, 1)

    def test_walking_on_a_line_is_not_blocked(self):
        frames = [WindowFrame(1, 9, 1000.0, 900.0, 400.0, 480.0)]
        route, _ = self.plan(frames, ("floor", 0), 800.0, ("floor", 0), 1800.0)
        self.assertTrue(route.reachable)
        self.assertEqual([l.kind for l in route.legs], ["run"], "地上跑从窗口前面过只是画面重叠")

    def test_a_big_window_behind_the_target_does_not_block_a_jump_from_the_floor(self):
        """真机：后面开着一个大窗口，狗从地面哪都跳不上去。背景窗口不挡：狗在地上本来就画在所有窗口前面。"""
        w = self.world()
        frames = [WindowFrame(1, 9, 1200.0, 950.0, 500.0, 300.0), WindowFrame(2, 9, 100.0, 100.0, 2800.0, 1250.0)]
        route, _ = self.plan(frames, ("floor", 0), 800.0, ("window", 1), 1400.0)
        self.assertTrue(route.reachable)
        self.assertEqual([l.support.key for l in route.legs if l.kind == "jump"], [1], "直接跳上去")

    def test_a_maximized_window_is_only_background(self):
        """真机：MacBook 上开着一个铺满的窗口，狗在那块屏上哪都跳不了。铺满的窗口不算挡路。"""
        w = self.world()
        frames = [WindowFrame(9, 9, 0.0, 30.0, 3000.0, 1370.0), WindowFrame(1, 9, 1000.0, 900.0, 400.0, 300.0)]
        self.assertEqual([b.key for b in blocks_from(frames, w)], [1])
        lines = list(w.floors) + w.window_tops(frames[1:], 100.0, 100.0)
        s = next(l for l in lines if l.kind == "floor")
        g = next(l for l in lines if l.key == 1)
        route = plan_route(lines, s, 800.0, g, 1200.0, 576.0, 240.0, 52.0, Leaper(w, self.PPM, LeapSpec(), blocks_from(frames, w)))
        self.assertTrue(route.reachable)

    def test_jumping_between_two_screens_floors_is_never_blocked(self):
        w = World([Area(0, 30, 1500, 1400), Area(1500, 30, 3000, 1400)], 18.0, [Area(0, 0, 1500, 1400), Area(1500, 0, 3000, 1400)])
        frames = [WindowFrame(1, 9, 1300.0, 500.0, 400.0, 899.0)]    # 一个窗口骑在交界上，一直盖到地面
        a, b = w.floors
        route = plan_route(list(w.floors), a, 800.0, b, 2200.0, 576.0, 240.0, 52.0, Leaper(w, self.PPM, LeapSpec(), blocks_from(frames, w)))
        self.assertTrue(route.reachable, "过屏幕交界和在地上跑一样，只是画面重叠")


class BallTuningTests(unittest.TestCase):
    def test_bounce_and_roll_come_from_the_physics_argument(self):
        w = World([Area(0, 0, 3000, 1000)], 18.0)
        peaks = {}
        for e in (0.2, 0.8):
            b = Ball(500.0, 500.0, 10.0, 0.0, 800.0, resting=False)
            top = None
            seen_floor = False
            for _ in range(240):
                ev = step_ball(w, b, 1 / 60, 240.0, (), (), BallPhysics(e_floor=e))
                seen_floor = seen_floor or "floor" in ev
                if seen_floor:
                    top = b.y if top is None else min(top, b.y)
            peaks[e] = top
        self.assertLess(peaks[0.8], peaks[0.2], "弹得更高")

    def test_rolls_further_with_a_higher_roll_setting(self):
        w = World([Area(0, 0, 9000, 1000)], 18.0)
        ends = {}
        for roll in (0.5, 2.0):
            b = Ball(500.0, w.floors[0].y - 10.0, 10.0, 600.0, 0.0, rolling=True, resting=False)
            for _ in range(600):
                step_ball(w, b, 1 / 60, 240.0, (), (), BallPhysics(roll_gain=roll))
            ends[roll] = b.x
        self.assertGreater(ends[2.0], ends[0.5])

    def test_impact_records_how_hard_it_hit(self):
        w = World([Area(0, 0, 3000, 1000)], 18.0)
        b = Ball(500.0, w.floors[0].y - 30.0, 10.0, 0.0, 900.0, resting=False)
        for _ in range(10):
            step_ball(w, b, 1 / 60, 240.0)
            if b.impact:
                break
        self.assertGreater(b.impact, 800.0)


if __name__ == "__main__":
    unittest.main()
