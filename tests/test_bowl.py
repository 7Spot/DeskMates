"""吃喝：点一下摆着的饭盆、水盆，狗过去吃 / 喝，吃完盆变空；再点一下添满、再来。
摆下去马上有反应（PutDownBowl…）：满着的盆刚摆出来 / 拖完松手落定，闲着的狗自己过来吃一次。
真窗口（offscreen）+ 假设置（卸载器挡住）+ 假的款表（tests/test_nest.py 的底子，盆的模型是现写的盒子）；真盆的那一类买来的模型不在就跳过。
边牧、萨摩耶各跑一遍：鼻子到盆的那一截是按模型量的。"""
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage

from tests.room_base import COLLIE, DT, SAMOYED, RoomCase
from tests.test_nest import BED, HAS_PROPS, NestCase
from tests.test_thing_art import glb
from tests.test_things import box
from widget import packs, things as things_mod
from widget.gltf import mat_mul, transform_point
from widget.roam import EAT_S

FOOD, WATER, PLAIN = "food_bowl/bowl", "water_bowl/bowl", "bowl/food"


def bowl_styles(folder: Path) -> list:
    """假的款表里的两个盆：饭盆、水盆，各有满的、空的两个模型（空的矮一点）。"""
    out = []
    for key, serves in ((FOOD, "food"), (WATER, "water")):
        full, empty = folder / f"{serves}.glb", folder / f"{serves}_empty.glb"
        full.write_bytes(glb(box(0.3, 0.12, 0.3)))
        empty.write_bytes(glb(box(0.3, 0.1, 0.3)))
        out.append(packs.ThingStyle(key=key, pack=key.split("/")[0], names={"en": key}, model=full, model_empty=empty, thumb=folder / "none.png",
                                    spec={"group": "food", "role": "bowl", "serves": serves, "order": 10, "scale": 1.0, "yaw": 0, "shadow": True,
                                          "front_rim": {"r": 0.15, "y": 0.12}}))
    return out


class BowlCase(NestCase):
    def setUp(self):
        super().setUp()
        self.fakes += bowl_styles(self.fakes[0].model.parent)
        self.things.use(packs.things())

    def tap(self, t):
        """点一下：按下、没挪、没按够就松手。"""
        at = QPointF(t.x, t.y - 5.0)
        self.things.thing_press(t, at)
        self.step(2 * DT)
        self.things.thing_release(t, at)

    def nose(self):
        """鼻子这一帧在屏幕上哪（全局坐标）。"""
        dog, roam = self.win.dog, self.pg.roam
        root, g = dog._last
        return roam.scene_point(*transform_point(mat_mul(root, g[dog.props.nose]), (0.0, 0.0, 0.0)))

    def watch_meal(self, t, limit=25.0):
        """推到这一顿吃完。返回 (依次播过的片段, 鼻子最低那一刻的 x, 盆是在播哪一段时变空的, 循环那一段多久)。片段绑的声音照窗口每帧那样放。"""
        dog, roam, win = self.win.dog, self.pg.roam, self.win
        clips, low, emptied, loop = [], [None, 1e9], [], [0.0]

        def watch():
            name = dog.player.name
            win.clip_sounds.update(name, dog.player.time, dog.action.id if dog.action is not None else None, DT)
            if roam.task == "eat":
                if not clips or clips[-1] != name:
                    clips.append(name)
                if roam.head_busy:
                    x, y = self.nose()
                    if y > low[1] or low[0] is None:
                        low[:] = [x, y]
                if roam.phase == "loop":
                    loop[0] += DT
            if not t.full and not emptied:
                emptied.append(name)
            self.assertIsNone(dog.props.bowl, "程序画的那只盆不出来")
            return roam.task is None
        self.assertIsNotNone(self.step(limit, watch), "吃完了")
        return clips, low[0], (emptied or [None])[0], loop[0]


class EatingTests(BowlCase):
    def test_a_tap_on_the_bowl_calls_it_over_to_eat_and_the_bowl_ends_up_empty(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.assertTrue(t.full and t.serves == "food")
        self.assertEqual(Path(t.geo[0]).name, "food.glb")
        self.sounds.clear()
        self.tap(t)
        self.assertEqual((roam.task, pg._eating, t.state), ("eat", FOOD, "rest"))
        self.assertEqual((t.x, t.on), (t.x, ("floor", 0)), "盆不动")
        clips, nose_x, emptied_in, loop_s = self.watch_meal(t)
        seq = [c for c in clips if c in ("EatDrink_start", "Eat_loop", "Drink_loop", "EatDrink_end")]
        self.assertEqual(seq, ["EatDrink_start", "Eat_loop", "EatDrink_end"])
        self.assertAlmostEqual(nose_x, t.x, delta=0.05 * pg.ppm, msg="鼻子最低那一刻正对盆心（差不超过 5 厘米）")
        self.assertAlmostEqual(loop_s, EAT_S, delta=0.1)
        self.assertEqual(emptied_in, "EatDrink_end", "抬头那一段一开始盆空了")
        self.assertFalse(t.full)
        self.assertEqual(Path(t.geo[0]).name, "food_empty.glb", "换成空盆的模型")
        self.assertEqual((roam.task, dog.posture, pg._eating), (None, "standing", None))
        self.assertAlmostEqual(roam.home.dx, roam.wx, delta=1.0, msg="就待在盆旁边")
        self.assertTrue({"eat", "bite"} <= set(self.sounds), f"嚼、咬一下是片段在包里绑的（{self.sounds}）")
        self.assertNotIn("bark", self.sounds)

    def test_the_water_bowl_is_drunk_from(self):
        pg = self.pg
        self.start_on_floor(x=140.0)
        t = self.put(WATER)
        self.sounds.clear()
        self.tap(t)
        clips, nose_x, emptied_in, _ = self.watch_meal(t)
        self.assertEqual([c for c in clips if c.endswith("_loop")], ["Drink_loop"])
        self.assertAlmostEqual(nose_x, t.x, delta=0.05 * pg.ppm)
        self.assertEqual((emptied_in, Path(t.geo[0]).name), ("EatDrink_end", "water_empty.glb"))
        self.assertIn("lick", self.sounds)
        self.assertNotIn("eat", self.sounds)

    def test_a_bowl_on_the_other_side_is_eaten_from_the_other_side(self):
        """盆在狗哪边就从哪边过去；那一边放不下狗（盆贴着屏幕边）就绕到另一边。"""
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=self.ag.width() - 140.0)
        t = self.put(FOOD)
        self.assertLess(t.x, roam.wx)
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.assertGreater(roam.wx, t.x, "盆在左边：狗站在盆右边、朝左")
        self.assertEqual(roam.facing, -1.0)
        self.step(EAT_S + 3.0, lambda: roam.task is None)
        t.x = self.ag.x() + t.lay.cx + 1.0                       # 盆贴着屏幕左边：左边站不下狗
        self.things._seat(t, self.things._floor(0, t.x))
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.assertGreater(roam.wx, t.x)

    def test_an_empty_bowl_is_filled_first_and_it_comes_every_time(self):
        roam = self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        for _ in range(2):
            self.tap(t)
            self.assertTrue(t.full, "点一下：空的先添满")
            self.assertEqual(roam.task, "eat", "每点一次都来")
            self.assertIsNotNone(self.step(25.0, lambda: roam.task is None))
            self.assertFalse(t.full)

    def test_dragging_the_bowl_is_not_a_tap(self):
        roam = self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.things.set_full(t, False)
        self.grab(t, (t.x + 80.0, t.y - 120.0))
        self.things.thing_release(t, QPointF(t.x, t.y - 10.0))
        self.step(1.5)
        self.assertEqual((roam.task, t.state, t.full), (None, "rest", False), "拖着盆不算点：空盆不添满，落定了也不叫狗")
        plain = self.put(PLAIN)
        self.tap(plain)
        self.step(0.5)
        self.assertIsNone(roam.task, "包里没写 serves 的盆只是摆设")

    def test_tapping_again_while_it_eats_only_squashes_the_bowl(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        at = roam.t
        self.step(1.0)
        with mock.patch.object(roam, "eat", side_effect=AssertionError("已经在吃这个盆")):
            self.assertFalse(pg.bowl_tapped(FOOD))
            self.tap(t)
        self.assertEqual((roam.task, roam.phase, t.full), ("eat", "loop", True))
        self.assertIsNotNone(self.step(EAT_S + 3.0, lambda: roam.task is None))
        self.assertAlmostEqual(roam.t - at, EAT_S + 1.67, delta=1.0, msg="这一顿没有重来")

    def test_picking_up_the_ball_mid_meal_wins_and_the_bowl_stays_full(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.step(1.0)
        self.pick_up_ball((roam.wx + 60.0, roam.wy - 150.0))
        self.assertEqual(roam.task, self.HELD_TASK, "球的优先级最大：停下看球（萨摩耶坐着看）")
        self.step(1.0)
        self.assertTrue(t.full, "没吃完：盆还是满的")
        self.assertNotIn(dog.player.name, ("Eat_loop", "EatDrink_start", "EatDrink_end"))
        self.assertFalse(roam.head_busy)

    def test_taking_the_bowl_away_mid_meal_stops_it(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.grab(t)
        self.assertEqual((roam.task, pg._eating), (None, None), "盆被拿走：抬头站住")
        self.step(1.0)
        self.assertEqual((dog.posture, t.full), (self.RESTS, True))
        self.things.thing_release(t, QPointF(*t.pointer))
        self.step(1.5)
        self.assertEqual((roam.task, t.full), ("eat", True), "盆还满着：落定了它自己又过来")
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"), "路上再敲一下：照样来吃")
        self.win.set_thing(FOOD, False)
        self.assertIsNone(roam.task, "收起盆：也站住")

    def test_busy_with_the_ball_it_does_not_come(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.cursor = (roam.wx + 30.0, roam.wy - 150.0)
        self.throw_and_fetch(500.0)
        self.assertIsNotNone(self.step(10.0, lambda: roam.carrying), "叼着球")
        t.full = False
        self.tap(t)
        self.assertEqual(roam.task, "fetch", "叼着球：不来")
        self.assertTrue(t.full, "盆照样添满")
        self.step(0.5)
        self.assertEqual(t.duang.pressing, False)
        self.pg.roam.cancel()
        self.pick_up_ball()
        self.assertFalse(pg.bowl_tapped(FOOD), "球在你手上：不来")
        self.put_ball_down()
        self.step(3.0, lambda: roam.task is None)
        pg.dog_grabbed((roam.wx, roam.wy))
        self.assertFalse(pg.bowl_tapped(FOOD), "被拎着：不来")

    def test_a_bowl_it_cannot_reach_gets_two_barks_and_stays_full(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        full = roam.max_up
        with mock.patch.object(roam, "max_up", lambda: full() * 0.2):
            top = self.add_window(7, 300.0, self.floor_y - 420.0, 420.0)
            self.grab(t, (500.0, top.y - 60.0))
            self.things.thing_release(t, QPointF(500.0, top.y - 70.0))
            self.step(1.5)
            self.assertEqual(t.on, ("window", 7))
            self.tap(t)
            self.assertEqual((roam.task, roam.phase), ("eat", "bark_go"))
            seen = set()
            self.assertIsNotNone(self.step(15.0, lambda: seen.add(dog.player.name) or roam.task is None))
            self.assertIn("Bark", seen, "够不着：叫两声")
            self.assertFalse(seen & {"Eat_loop", "EatDrink_start"})
            self.assertTrue(t.full, "盆不变空")
            self.assertIsNone(pg._eating)

    def test_from_the_bed_it_gets_up_and_goes(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.home(BED)
        t = self.put(FOOD)
        self.assertEqual((dog.posture, pg._nest is not None), ("lying", True), "摆个盆不算跟它玩")
        self.tap(t)
        self.assertEqual(roam.task, "eat")
        self.assertIsNotNone(self.step(15.0, lambda: roam.phase == "loop"), "从窝里起来过去吃")
        self.assertEqual((dog.perch, pg._nest, dog.hide_shadow, self.things.front_shown(BED)), (0.0, None, False, False))
        self.assertIsNotNone(self.step(EAT_S + 3.0, lambda: roam.task is None))
        self.assertFalse(t.full)

    def test_on_its_way_to_the_bed_a_tap_turns_it_round(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.put(BED)
        t = self.put(FOOD)
        pg._idle_for = self.AFTER
        self.assertIsNotNone(self.step(5.0, lambda: roam.task == "nest" and roam.v != 0.0))
        self.tap(t)
        self.assertEqual((roam.task, pg._nest_going), ("eat", None))
        self.assertIsNotNone(self.step(25.0, lambda: roam.task is None))
        self.assertEqual((t.full, pg._nest), (False, None))

    def test_its_head_stays_in_the_bowl_whatever_the_pointer_does(self):
        win, roam = self.win, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        win.follow_cursor = True
        self.step(0.2)
        self.assertIsNotNone(win._look_target(DT), "平时看鼠标")
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.assertTrue(roam.head_busy)
        self.assertIsNone(win._look_target(DT), "吃的时候头不看鼠标")
        self.step(EAT_S + 3.0, lambda: roam.task is None)
        self.cursor = (self.cursor[0] + 10.0, self.cursor[1])     # 鼠标一动（一直停着的话狗早就不看了）
        self.step(DT)
        self.assertIsNotNone(win._look_target(DT), "吃完了：又看鼠标")


class PutDownBowlTests(BowlCase):
    """摆下去马上有反应：满着的盆刚从「物件」页摆出来落定、刚拖完松手落定，闲着的狗过来吃 / 喝一次（和敲盆同一条路）。
    空盆落定不叫它；忙着就算了，等你敲；够不着不过去也不叫。"""

    def test_a_full_bowl_just_put_out_is_eaten_from_at_once(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        self.sounds.clear()
        self.win.set_thing(FOOD, True)
        t = self.things.items[FOOD]
        self.assertEqual((t.state, roam.task), ("fall", None), "还在落：先不动")
        self.assertIsNotNone(self.step(1.0, lambda: t.state == "rest"))
        self.assertEqual((roam.task, pg._eating, t.full), ("eat", FOOD, True), "落定那一下就过来")
        clips, nose_x, emptied_in, loop_s = self.watch_meal(t)
        self.assertEqual([c for c in clips if c in ("EatDrink_start", "Eat_loop", "Drink_loop", "EatDrink_end")], ["EatDrink_start", "Eat_loop", "EatDrink_end"])
        self.assertAlmostEqual(nose_x, t.x, delta=0.05 * pg.ppm, msg="鼻子对着盆心")
        self.assertAlmostEqual(loop_s, EAT_S, delta=0.1)
        self.assertEqual((emptied_in, t.full, roam.task), ("EatDrink_end", False, None), "吃一次，吃完盆空了")
        self.assertNotIn("bark", self.sounds)
        seen = set()
        self.step(4.0, lambda: seen.add(roam.task) and False)
        self.assertEqual(seen, {None}, "空盆摆着不再叫它")

    def test_the_water_bowl_just_put_out_is_drunk_from(self):
        roam = self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        t = self.put(WATER, settle=0, call=True)
        self.assertIsNotNone(self.step(1.0, lambda: t.state == "rest"))
        self.assertEqual(roam.task, "eat")
        clips, _, _, _ = self.watch_meal(t)
        self.assertEqual([c for c in clips if c.endswith("_loop")], ["Drink_loop"])
        self.assertFalse(t.full)

    def test_dragged_and_let_go_a_full_bowl_calls_it_and_an_empty_one_does_not(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        t = self.put(FOOD)                                       # 摆着一个满盆（没叫狗）
        self.assertEqual((roam.task, t.full), (None, True))
        self.grab(t, (t.x + 60.0, t.y - 150.0))
        self.assertIsNone(roam.task, "拿着的时候不来")
        self.things.thing_release(t, QPointF(*t.pointer))
        self.assertIsNotNone(self.step(2.0, lambda: t.state == "rest"))
        self.assertEqual((roam.task, pg._eating), ("eat", FOOD), "满盆拖完松手落定：过来吃")
        self.assertIsNotNone(self.step(25.0, lambda: roam.task is None))
        self.assertFalse(t.full)
        self.grab(t, (t.x - 60.0, t.y - 150.0))
        self.things.thing_release(t, QPointF(*t.pointer))
        self.assertIsNotNone(self.step(2.0, lambda: t.state == "rest"))
        seen = set()
        self.step(3.0, lambda: seen.add(roam.task) and False)
        self.assertEqual((seen, t.full), ({None}, False), "空盆落定：不叫它，也不添满")
        self.tap(t)
        self.assertEqual((roam.task, t.full), ("eat", True), "点一下照旧是添满并叫它")

    def test_put_down_right_on_the_line_counts_too(self):
        """松手时脚下就是线（不落）：也算落定。"""
        roam = self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        t = self.put(FOOD)
        self.grab(t, (t.x + 90.0, self.floor_y))
        self.things.thing_release(t, QPointF(*t.pointer))
        self.assertEqual((t.state, roam.task), ("rest", "eat"), "原地放下的那一下就叫")

    def test_busy_it_does_not_come_and_waits_for_a_tap(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        self.pick_up_ball((roam.wx, roam.wy - 2.2 * pg.ppm))     # 球拿在圈外面：狗站好看着
        t = self.put(FOOD, settle=0, call=True)
        self.assertIsNotNone(self.step(1.0, lambda: t.state == "rest"))
        self.step(0.3)
        self.assertEqual((roam.task, pg._eating, t.full), (self.HELD_TASK, None, True), "球在你手上：盆落定不叫它")
        self.put_ball_down()
        self.assertIsNotNone(self.step(8.0, lambda: roam.task is None and pg.ball.resting))
        seen = set()
        self.step(4.0, lambda: seen.add(roam.task) and False)
        self.assertEqual(seen, {None}, "闲下来也不补叫：等你敲")
        self.tap(t)
        self.assertEqual(roam.task, "eat")

    def test_out_of_reach_it_neither_comes_nor_barks(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        t = self.put(FOOD)
        full = roam.max_up
        with mock.patch.object(roam, "max_up", lambda: full() * 0.2):
            top = self.add_window(7, 300.0, self.floor_y - 420.0, 420.0)
            self.sounds.clear()
            self.grab(t, (500.0, top.y - 60.0))
            self.things.thing_release(t, QPointF(500.0, top.y - 70.0))
            seen = set()
            self.step(4.0, lambda: seen.add((roam.task, dog.player.name == "Bark")) and False)
            self.assertEqual((t.on, t.full), (("window", 7), True), "满盆落在够不着的窗口上")
            self.assertEqual(seen, {(None, False)}, "没人叫它：够不着就算了，不过去、不叫")
            self.assertEqual((self.sounds, pg._eating), ([], None))
            self.tap(t)
            self.assertEqual((roam.task, roam.phase), ("eat", "bark_go"), "敲盆叫它才走到最近的地方叫两声")

    def test_from_its_bed_it_gets_up_for_a_bowl_just_put_down(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.home(BED)
        t = self.put(FOOD, settle=0, call=True)
        self.assertIsNotNone(self.step(1.0, lambda: t.state == "rest"))
        self.assertEqual(roam.task, "eat", "歇在窝里也算闲着：起来过去吃")
        self.assertIsNotNone(self.step(15.0, lambda: roam.phase == "loop"))
        self.assertEqual((dog.perch, pg._nest, pg._pad, self.things.front_shown(BED)), (0.0, None, None, False))

    def test_eating_from_a_bowl_in_front_of_the_bed_it_stands_on_the_floor(self):
        """盆摆在狗窝前面（吃的那个位置在垫子的范围里）：走过去时踩着垫子，低头吃的那几步落回线上——鼻子照样对着盆心、够得着线上的盆。"""
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=110.0)
        self.step(0.3)
        bed = self.put(BED)
        spot = self.move_to(bed, self.ag.x() + 0.6 * self.ag.width())
        t = self.put(FOOD)
        self.move_to(t, bed.x + 0.25 * pg.ppm)
        self.tap(t)
        rows = []

        def watch():
            rows.append((roam.phase, pg._perch_to, dog.perch, roam.wx))
            return roam.phase == "loop"
        self.assertIsNotNone(self.step(12.0, watch))
        self.assertIsNotNone(self.things.pad_at("floor", 0, roam.wx), "吃的那个位置在垫子的范围里")
        self.assertTrue(any(r[0] == "go" and r[1] == spot.perch_m for r in rows), "走过去的路上踩着垫子")
        self.assertTrue(all(r[1] == 0.0 for r in rows if r[0] in ("face", "start", "loop")), "转正、低头、吃：落回线上")
        self.step(0.5)
        self.assertEqual((dog.perch, pg._pad), (0.0, None))
        low = [None, -1e9]

        def lowest():
            x, y = self.nose()
            if y > low[1]:
                low[:] = [x, y]
            return roam.phase != "loop"
        self.step(EAT_S + 1.0, lowest)
        self.assertAlmostEqual(low[0], t.x, delta=0.05 * pg.ppm, msg="鼻子对着盆心")
        self.assertGreater(low[1], self.floor_y - 0.2 * pg.ppm, "鼻子低到盆那么低（盆在线上，没被垫子抬走）")
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None))
        self.step(0.5)
        self.assertEqual(pg._pad, BED, "吃完站在那：又踩回垫子上")
        self.assertAlmostEqual(dog.perch, spot.perch_m, places=6)


class SamoyedPutDownBowlTests(PutDownBowlTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None


class BowlPictureTests(BowlCase):
    def test_both_looks_are_drawn_ahead_and_swapping_costs_nothing(self):
        made = []

        def shoot(view, model, lay, dpr):
            img = QImage(max(1, round(lay.w * dpr)), max(1, round(lay.h * dpr)), QImage.Format_ARGB32_Premultiplied)
            img.fill(0xFF336699)
            front = any(x.front_model is not None and model is x.front_model[1] for x in self.things.items.values())
            made.append("front" if front else "look")              # 盆沿近的那半圈（吃的时候盖在狗前面）另算
            return img
        for p in (mock.patch.object(self.win.view, "ready", lambda: True), mock.patch.object(things_mod.thing_art, "shoot", shoot)):
            p.start()
            self.addCleanup(p.stop)
        roam = self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.step(0.5)
        self.assertEqual(made.count("look"), 2, "满的、空的两张摆出来以后都出好")
        self.assertEqual(made.count("front"), 0, "盆沿那一层不另画：拿整件的图只留近处盆沿以下（front_rim）")
        self.assertTrue(any(k[-1] == "front" for k in self.things._shots), "盆沿那一层也先备好（吃的时候不用现出）")
        full_shot = t.shot
        self.assertEqual(len([k for k in self.things._shots if k[-1] != "front"]), 2, "闲着的那张留着，不当没人用的丢掉")
        self.tap(t)
        self.assertIsNotNone(self.step(25.0, lambda: roam.task is None))
        self.assertFalse(t.need_shot)
        self.assertIsNot(t.shot, full_shot)
        self.assertEqual(made.count("look"), 2, "换成空盆不用现出图")
        self.assertIs(t.win.shot, t.shot)
        self.tap(t)
        self.assertIs(t.shot, full_shot, "添满：换回满的那张")
        self.assertEqual(made.count("look"), 2)
        self.win.set_thing(FOOD, False)
        self.step(0.5)
        self.assertEqual(self.things._shots, {}, "收起来两张都丢掉")

    def test_without_an_empty_model_it_keeps_the_full_look(self):
        self.start_on_floor(x=140.0)
        self.fakes[-2].model_empty.unlink()
        t = self.put(FOOD)
        self.assertIsNone(t.empty_model)
        geo = t.geo
        self.things.set_full(t, False)
        self.assertEqual((t.full, t.geo), (False, geo), "空盆的模型不在：记着空了，画的还是满的那张")


class BowlRimTests(BowlCase):
    """吃饭、喝水像在盆外面吃——狗在这个盆吃 / 喝、头低着的时候，近处的盆沿、盆壁盖在狗前面。
    按包里的 front_rim 切：整件的图只留近处盆沿那道弧线以下（thing_art.rim_front）。"""

    def test_the_near_rim_covers_the_dog_while_its_head_is_in_the_bowl(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        import json
        import config
        for pack in ("food_bowl", "water_bowl"):
            thing = json.loads((config.ROOT / "packs" / pack / "pack.json").read_text(encoding="utf-8"))["thing"]
            self.assertNotIn("front_z", thing, "不再按模型切（切在盆中心近的半堆粮也盖着，鼻子埋进去）")
            self.assertEqual(thing["front_rim"], {"r": 0.1, "y": 0.07}, "近处盆沿：半径 0.1、高 0.07 米（量的模型）")
        self.tap(t)
        seen = []
        self.assertIsNotNone(self.step(25.0, lambda: (seen.append((roam.phase, self.things.front_shown(FOOD))), roam.task is None)[1]), "吃完了")
        shown = {ph for ph, on in seen if on}
        self.assertTrue({"start", "loop"} <= shown, "低头吃的时候盖着")
        self.assertNotIn("go", shown, "走过去的路上不盖")
        self.assertFalse(self.things.front_shown(FOOD), "抬头、吃完就淡掉")
        self.assertIsNone(pg._bowl_front_key)

    def test_taking_the_bowl_away_mid_meal_takes_the_rim_too(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(WATER)
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.step(0.3)
        self.assertTrue(self.things.front_shown(WATER))
        self.grab(t)
        self.step(0.5)
        self.assertFalse(self.things.front_shown(WATER), "盆被拿走：前沿跟着收")


class SamoyedBowlRimTests(BowlRimTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None

class SamoyedEatingTests(EatingTests):
    PACK = SAMOYED
    AFTER = 20.0
    RESTS, REST_LOUNGE, HELD_TASK = "sitting", "sitting", None


@unittest.skipUnless(HAS_PROPS, "买来的物件模型不在（models/props/，不入 git）")
class RealBowlTests(RoomCase):
    """真的饭盆、水盆（买来的模型）：鼻子进不进盆。"""
    PACK = COLLIE

    def make_window(self, settings=None, pack_id=None):
        win = super().make_window(settings, pack_id)
        self.addCleanup(lambda: [t.win.hide() for t in win.playground.things.items.values()])
        return win

    def test_the_nose_goes_into_the_real_bowls(self):
        dog, pg, roam = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor(x=140.0)
        self.step(0.3)
        for key, empty in (("food_bowl/bowl", "bowl_food_empty.glb"), ("water_bowl/bowl", "bowl_water_empty.glb")):
            with self.subTest(key):
                self.win.set_thing(key, True)
                t = pg.things.items[key]
                self.assertIsNotNone(self.step(1.5, lambda: t.state == "rest"))
                self.assertIsNotNone(t.empty_model)
                self.assertEqual((roam.task, pg._eating), ("eat", key), "满着的盆摆出来落定：闲着的狗自己过来")
                low = [None, -1e9]

                def watch():
                    if roam.phase == "loop":
                        root, g = dog._last
                        x, y = roam.scene_point(*transform_point(mat_mul(root, g[dog.props.nose]), (0.0, 0.0, 0.0)))
                        if y > low[1]:
                            low[:] = [x, y]
                    return roam.task is None
                self.assertIsNotNone(self.step(25.0, watch))
                lo, hi = t.span()
                self.assertTrue(lo < low[0] < hi, "鼻子最低那一刻在盆口里面")
                self.assertAlmostEqual(low[0], t.x, delta=0.05 * pg.ppm)
                self.assertLess(t.y - low[1], 0.14 * pg.ppm, "鼻子低到盆沿以下（盆高 0.11 米）")
                self.assertEqual((t.full, Path(t.geo[0]).name), (False, empty))
                self.win.set_thing(key, False)
                self.step(0.5)


@unittest.skipUnless(HAS_PROPS, "买来的物件模型不在（models/props/，不入 git）")
class RealBowlSamoyedTests(RealBowlTests):
    PACK = SAMOYED


class RimFrontTests(unittest.TestCase):
    """thing_art.rim_front：整件的图只留近处盆沿那道弧线以下（盆壁、盆底），粮、水面那些在弧线上面的变透明。"""

    def test_only_what_is_below_the_near_rim_stays(self):
        import math
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtWidgets import QApplication
        from widget import thing_art
        from widget.render import ELEVATION, make_frame
        from widget.dogctl import Pose
        from widget.gltf import IDENTITY
        QApplication.instance() or QApplication([])
        w, h, ppm, ground = 200, 120, 400.0, 20.0
        frame = make_frame(Pose(IDENTITY, [], [], [], 0.0), 0.0, ppm, ground, w, (0.0, 0.0))
        lay = thing_art.Layout(frame, w, h, 100.0, ground, 0.0, 0.15, 0.15, 0.1)
        whole = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        whole.fill(QColor(200, 60, 60))
        out = thing_art.rim_front(whole, lay, 0.1, 0.07)
        e = math.radians(ELEVATION)
        near = h - (ground + (0.07 * math.cos(e) - 0.1 * math.sin(e)) * ppm)   # 近处盆沿正中在图上的 y
        self.assertEqual(out.pixelColor(100, round(near) + 6).alpha(), 255, "盆沿以下（盆壁）留着")
        self.assertEqual(out.pixelColor(100, round(near) - 8).alpha(), 0, "盆沿以上（粮堆、水面）不留：鼻子露出来")
        self.assertEqual(out.pixelColor(100 + round(0.12 * ppm), h - 2).alpha(), 0, "盆沿外面左右两边也不留")
