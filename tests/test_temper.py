"""性子：每个模型两项，活跃度和聪明程度（widget/temper.py）。两项都是 1 的边牧一个数都不变；萨摩耶 0.5 / 0.4 不冲刺、反应慢半拍、
一直追着球本身跑、没人理自己歇着、有几个招牌时刻。纯函数在前，放进真窗口的在后（tests/room_base.py 的架子；模型文件不在就跳过）。"""
import math
import os
import random
import unittest
from unittest import mock

from tests.room_base import COLLIE, DT, SAMOYED, RoomCase
from widget import clips, packs, roam, temper
from widget.tuning import PET_PARAMS, Tuning

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
SAM = {"energy": 0.5, "smarts": 0.4, "max_up": 3.0, "ring_hold_s": 1.0}


def collie_tuning() -> Tuning:
    return Tuning(packs.discover()[COLLIE])


def samoyed_tuning() -> Tuning:
    return Tuning(packs.discover()[SAMOYED])



def set_fetch(win, on: bool) -> None:
    """捡球的总闸（window.fetch_on 一直开着）：单测拨它让狗只看着、叼着的放下。"""
    win.fetch_on = bool(on)
    win.playground.fetch_changed()

class TemperAtOneTests(unittest.TestCase):
    """两项都是 1（没接调参、空的、边牧的调参三种）：每个函数就是原来的那个常量，随机数一个都不抽。"""

    def tunes(self):
        full = {"max_up": 3.0, "ring_hold_s": 1.0}
        return {"None": None, "空字典": {}, "边牧的调参": collie_tuning(), "写明是 1": dict(full, energy=1.0, smarts=1.0)}

    def test_the_two_params_lead_the_tuning_page_and_default_to_one(self):
        self.assertEqual([p.key for p in PET_PARAMS[:2]], ["energy", "smarts"], "开发者设置页一打开就是它俩")
        for p in PET_PARAMS[:2]:
            self.assertEqual((p.default, p.lo, p.hi), (1.0, 0.0, 1.0))
        t = collie_tuning()
        self.assertEqual((t["energy"], t["smarts"]), (1.0, 1.0))
        self.assertEqual(dict(packs.discover()[COLLIE].tuning), {}, "边牧的包不写：默认就是 1")

    def test_gait_is_the_old_expression(self):
        for name, tune in self.tunes().items():
            for d in (0.1, 0.3, 0.31, 0.9, 0.91, 3.0, 3.01, 10.0, 0.8999999999999999, 0.9000000000000001):
                old = "fast" if d > 3.0 else "run" if d > 0.9 else "trot" if d > 0.3 else "walk"
                self.assertEqual(temper.gait(d, tune), old, f"{name} {d}")

    def test_every_number_is_the_old_constant_itself(self):
        self.assertEqual((temper.FETCH_LOOK, temper.WATCH_TURN_S, temper.CHASE_LEAD), (roam.FETCH_LOOK, roam.WATCH_TURN_S, roam.CHASE_LEAD),
                         "temper.py 里记的边牧的数和 roam.py 的是同一个")
        for name, tune in self.tunes().items():
            self.assertEqual((temper.energy(tune), temper.smarts(tune)), (1.0, 1.0), name)
            self.assertEqual(temper.fetch_look(tune), roam.FETCH_LOOK, name)
            self.assertEqual(temper.watch_turn(tune), roam.WATCH_TURN_S, name)
            self.assertEqual(temper.chase_lead(tune), roam.CHASE_LEAD, name)
            self.assertIs(temper.action_every(tune), clips.ACTION_EVERY, name)
            self.assertEqual((temper.release_beat(tune), temper.fooled(tune), temper.turn_lag(tune), temper.turn_rest(tune)), (0.0, 0.0, 0.0, 0.0), name)
            self.assertEqual(temper.turn_pace(tune), 1.0, name)
            self.assertIsNone(temper.rest_plan(tune), name)
            self.assertTrue(temper.reads_landing(tune), name)
            self.assertEqual((temper.goof(tune), temper.lazy(tune)), (0.0, 0.0), name)
        for value in (3.0, 2.7, 4.1):                            # 调参里的那个数本身，不经过乘加
            for tune in ({"max_up": value, "ring_hold_s": value}, {"max_up": value, "ring_hold_s": value, "energy": 1.0, "smarts": 1.0}):
                self.assertIs(temper.max_up(tune), tune["max_up"])
                self.assertIs(temper.ring_hold(tune), tune["ring_hold_s"])
        t = collie_tuning()
        self.assertEqual((temper.max_up(t), temper.ring_hold(t)), (t["max_up"], t["ring_hold_s"]))

    def test_no_random_number_is_drawn(self):
        """现有测试给 dog.rng 定了种子：聪明程度是 1 时多抽一个数，后面的随机动作、跳法全变。"""
        for name, tune in self.tunes().items():
            rng = random.Random(5)
            before = rng.getstate()
            self.assertEqual(temper.drop_short(tune, rng), 0.0, name)
            self.assertIsNone(temper.daze(tune, rng), name)
            self.assertEqual(rng.getstate(), before, name)

    def test_out_of_range_values_are_clamped(self):
        self.assertEqual((temper.energy({"energy": 1.7}), temper.smarts({"smarts": -0.2})), (1.0, 0.0))
        self.assertEqual(temper.gait(10.0, {"energy": 1.7}), "fast")


class TemperScaleTests(unittest.TestCase):
    def test_less_energy_is_never_quicker(self):
        """活跃度从 1 降到 0：每个门槛只升不降、时间只长不短、跳得只矮不高。"""
        steps = [1.0 - k / 20 for k in range(21)]
        rank = {"walk": 0, "trot": 1, "run": 2, "fast": 3}
        for d in (0.2, 0.5, 1.0, 1.4, 2.5, 3.5, 5.0, 9.0):
            gaits = [rank[temper.gait(d, {"energy": e})] for e in steps]
            self.assertEqual(gaits, sorted(gaits, reverse=True), f"{d} 米：步子只降档")
        for fn in (temper.fetch_look, temper.release_beat, temper.watch_turn, temper.turn_lag, temper.turn_rest,
                   lambda t: temper.action_every(t)[0], lambda t: temper.action_every(t)[1], lambda t: -temper.turn_pace(t),
                   lambda t: -temper.max_up(dict(t, max_up=3.0)), temper.lazy):
            values = [fn({"energy": e}) for e in steps]
            self.assertEqual(values, sorted(values))
        self.assertEqual(temper.gait(100.0, {"energy": 0.74}), "run", "活跃度低于 0.75：没有快跑")
        self.assertEqual(temper.gait(4.01, {"energy": 0.75}), "fast")
        plans = [temper.rest_plan({"energy": e}) for e in steps]
        self.assertIsNone(temper.rest_plan({"energy": 0.85}))
        rested = [p for p in plans if p is not None]
        self.assertEqual(plans.index(rested[0]), 4, "活跃度 0.8 起才自己歇")
        self.assertTrue(all(p[0] == 0.0 and p[1] >= 30.0 for p in rested), "自己歇的狗默认坐着：一闲下来就坐，坐够了趴")
        self.assertEqual([temper.sits_by_default({"energy": e}) for e in steps], [p is not None for p in plans], "自己歇的就是默认坐着的")
        homes = [temper.nest_after({"energy": e}) for e in steps]
        self.assertEqual(homes, sorted(homes, reverse=True), "越懒越早回窝")
        self.assertTrue(all(h >= 8.0 for h in homes))

    def test_less_smarts_is_never_sharper(self):
        steps = [1.0 - k / 20 for k in range(21)]
        for fn in (temper.fooled, lambda t: temper.ring_hold(dict(t, ring_hold_s=1.0)), lambda t: -temper.chase_lead(t), temper.goof,
                   lambda t: not temper.reads_landing(t)):
            values = [fn({"smarts": s}) for s in steps]
            self.assertEqual(values, sorted(values))
        self.assertTrue(temper.reads_landing({"smarts": 0.6}))
        self.assertFalse(temper.reads_landing({"smarts": 0.59}))
        rng = random.Random(1)
        shorts = [temper.drop_short({"smarts": 0.4}, rng) for _ in range(400)]
        self.assertTrue(all(0.0 <= v <= 0.30 for v in shorts))
        self.assertAlmostEqual(sum(shorts) / len(shorts), 0.15, delta=0.02)
        dazes = [temper.daze({"smarts": 0.4}, rng) for _ in range(2000)]
        self.assertEqual(set(dazes), {None, 0.5})
        self.assertAlmostEqual(sum(1 for v in dazes if v) / len(dazes), 0.21, delta=0.03, msg="约五趟里一趟")

    def test_the_samoyed_numbers(self):
        """萨摩耶 0.5 / 0.4 算出来的那一组。"""
        t = samoyed_tuning()
        self.assertEqual((t["energy"], t["smarts"]), (0.5, 0.4))
        self.assertEqual(dict(packs.discover()[SAMOYED].tuning), {"energy": 0.5, "smarts": 0.4, "look_idle_s": 7.0}, "走神快：鼠标停 7 秒就不看")
        for tune in (t, SAM):
            self.assertEqual([temper.gait(d, tune) for d in (0.4, 0.51, 1.5, 1.51, 3.5, 50.0)], ["walk", "trot", "trot", "run", "run", "run"], "不冲刺")
            for got, want in ((temper.fetch_look(tune), 0.40), (temper.release_beat(tune), 0.30), (temper.watch_turn(tune), 0.40), (temper.turn_lag(tune), 0.20),
                              (temper.turn_pace(tune), 0.875), (temper.turn_rest(tune), 0.25), (temper.max_up(tune), 2.55), (temper.chase_lead(tune), 0.22),
                              (temper.fooled(tune), 0.15), (temper.ring_hold(tune), 1.36), (temper.goof(tune), 0.6), (temper.lazy(tune), 0.5)):
                self.assertAlmostEqual(got, want, places=9)
            self.assertEqual(temper.action_every(tune), (12.0, 30.0))
            self.assertEqual(temper.rest_plan(tune), (0.0, 60.0), "默认坐着，坐 60 秒趴下")
            self.assertEqual(temper.nest_after(tune), 20.0, "摆了窝：20 秒走回去（不一闲下来就走开）")
            self.assertTrue(temper.sits_by_default(tune))
            self.assertFalse(temper.reads_landing(tune))


class SamoyedNumbersInTheWindowTests(RoomCase):
    def test_it_jumps_lower_and_the_recommended_size_follows(self):
        win, roam_ = self.win, self.pg.roam
        self.assertAlmostEqual(roam_.max_up(), 2.55 * 0.86 * win.ppm, delta=1e-6, msg="一次最多 2.55 个身高 = 2.19 米（边牧 2.40）")
        from widget.playground import recommended_scale
        for screen_h, want in ((982, 1.30), (1080, 1.45), (1440, 1.95)):
            got = recommended_scale(screen_h, temper.max_up(win.tuning), win.pack.height_m, win.pack.fit_m)
            self.assertAlmostEqual(got, want, places=6, msg=f"屏高 {screen_h}")
        screen = win.screen() or self.app.primaryScreen()
        self.assertAlmostEqual(win.recommended_scale(screen), recommended_scale(screen.geometry().height(), 2.55, 0.86, 0.92), places=6, msg="窗口读的是打过折的")

    def test_it_never_sprints(self):
        win, pg = self.win, self.pg
        win.set_scale(0.6, keep_center=False)                    # 0.6 倍：房间宽 5.6 米，够边牧冲刺的
        self.floor_y = self.ag.y() + self.ag.height() - 18.0 * win.scale
        self.start_on_floor(x=700.0)
        self.step(0.5)
        top, clips_seen = [0.0], set()

        def watch():
            top[0] = max(top[0], abs(pg.roam.v) / win.ppm)
            clips_seen.add(win.dog.player.name)
            return pg.roam.task is None
        floor = pg.world.floors[0]
        self.assertTrue(pg.roam.go_to(floor, floor.x0 + 40.0))
        self.assertIsNotNone(self.step(12.0, watch), "跑到了")
        self.assertIn("Run_F_IP", clips_seen)
        self.assertNotIn("RunFast_F_IP", clips_seen)
        self.assertLessEqual(top[0], win.pack.gaits["run"] + 1e-6, "最快就是跑的那一档（3.42 米 / 秒）")
        self.assertGreater(top[0], win.pack.gaits["trot"])

    def test_the_ring_takes_longer_to_fill(self):
        self.start_on_floor()
        pg = self.pg
        self.step(0.3)
        self.pick_up_ball()
        took = self.step(4.0, lambda: pg.ring.ready)
        self.assertIsNotNone(took)
        counting = 1.36
        self.assertGreater(took, counting - 0.05, "圈 1.36 秒满（边牧 1 秒）")
        self.assertLess(took, counting + 0.8, "起身、站好看球的那一下也在里面")

    def test_the_charge_sound_waits_and_still_lands_on_the_full_ring(self):
        """圈满得慢（1.36 秒），充能的声音只有 1 秒：晚一点才开始放，圈满那一下照样正好放到「满」。"""
        from widget.playground import CHARGE_FULL_AT, CHARGE_LATE_S
        self.start_on_floor()
        pg = self.pg
        self.step(0.3)
        started = []
        clock = [0.0]

        def tick():
            clock[0] += DT
            return pg.ring.ready
        with mock.patch.object(pg.ball_bank, "start", side_effect=lambda event, offset=0.0, gain=1.0: started.append((clock[0], event, offset)) or True), \
                mock.patch.object(pg.ball_bank, "fade") as fade:
            self.pick_up_ball()
            self.assertIsNotNone(self.step(4.0, tick))
        self.assertEqual(len(started), 1)
        at, event, offset = started[0]
        self.assertEqual(event, "charge")
        self.assertLess(offset, 0.06, "从头放")
        self.assertAlmostEqual((clock[0] - at) + offset - CHARGE_LATE_S, CHARGE_FULL_AT, delta=2.5 * DT, msg="从开始放到圈满正好是那段声音到「满」的那么久")
        fade.assert_not_called()


class CollieNumbersInTheWindowTests(RoomCase):
    PACK = COLLIE

    def test_the_collie_reads_the_tuning_as_it_always_did(self):
        win, roam_ = self.win, self.pg.roam
        self.assertEqual(roam_.max_up(), win.tuning["max_up"] * roam_.m(roam_.height_m))
        self.assertEqual(win.dog.tune, win.tuning)
        self.assertIs(temper.action_every(win.dog.tune), clips.ACTION_EVERY)


class SamoyedFetchTests(RoomCase):
    """追球那条线（聪明程度 0.4、活跃度 0.5）：不预判落点、被晃到、松手慢半拍、放得没那么准、路上愣一下。"""

    def watch_fetch(self, seconds=20.0, until=None):
        """推到叼起来（或 until 说停）。回来：用了多久、走过的阶段、进 approach 那一刻球停了没有、起跳那一刻是 on_jump() 的什么。"""
        pg, roam_ = self.pg, self.pg.roam
        seen = {"phases": [], "rest_at_approach": None}

        def watch():
            if roam_.phase and (not seen["phases"] or seen["phases"][-1] != roam_.phase):
                seen["phases"].append(roam_.phase)
                if roam_.phase == "approach" and seen["rest_at_approach"] is None:
                    seen["rest_at_approach"] = pg.ball.resting
            return until() if until is not None else roam_.carrying
        return self.step(seconds, watch), seen

    def cues(self):
        """记下 roam 报的时刻（原来接着的照样叫到）。"""
        roam_, got = self.pg.roam, []
        then = roam_.on_cue
        roam_.on_cue = lambda name: (got.append(name), then(name) if then is not None else None)
        return got

    def test_it_chases_the_ball_itself_until_the_ball_stops(self):
        """边牧看得出不撞墙的球停哪、直接去落点；萨摩耶哪种扔法都先追球本身，球停了才去叼。"""
        for vx, why in ((-420.0, "不撞墙：弧线落地、滚到停"), (-1900.0, "撞左墙弹回来")):
            self.start_on_floor()
            self.step(0.3)
            cues = self.cues()
            self.throw_and_fetch(vx)
            took, seen = self.watch_fetch()
            self.assertIsNotNone(took, f"{why}：叼到了 {seen}")
            self.assertEqual("fooled" in cues, vx < -1000.0, f"{why}：球掉头朝身后去才算被晃到，追上同一个方向滚着的球不算")
            phases = seen["phases"]
            self.assertIn("chase", phases, why)
            self.assertLess(phases.index("chase"), phases.index("approach"), why)
            self.assertTrue(seen["rest_at_approach"], f"{why}：球停之前不去落点")
            self.step(25.0, lambda: self.pg.roam.task is None)
            self.pg.stop()

    def test_the_collie_still_goes_straight_to_where_the_ball_will_stop(self):
        collie = self.make_window(pack_id=COLLIE)
        self.start_on_floor(win=collie)
        pg = collie.playground
        self.step(0.3, win=collie)
        pg.ball.throw(-420.0, -300.0, collie.ppm)
        pg.throw_id += 1
        pg.roam.fetch()
        phases = []
        self.assertIsNotNone(self.step(20.0, lambda: (phases.append(pg.roam.phase), pg.roam.carrying)[1], win=collie))
        self.assertNotIn("chase", phases)

    def test_a_ball_thrown_onto_a_window_is_fetched_after_it_lands_there(self):
        self.start_on_floor(x=250.0)
        pg, roam_ = self.pg, self.pg.roam
        self.step(0.3)
        top = self.floor_y - 260.0
        goal = self.add_window(7, 380.0, top, 360.0)
        b = pg.ball
        b.x, b.y = 560.0, top - b.r - 20.0
        self.throw_and_fetch(30.0, -1200.0)
        jumped = []

        def until():
            leg = roam_.leg
            if leg is not None and leg.get("kind") == "jump" and not jumped:
                jumped.append((pg.ball_down_on(goal), b.resting))
            return roam_.carrying
        took, seen = self.watch_fetch(20.0, until)
        self.assertIsNotNone(took, f"20 秒内叼到 {seen}")
        self.assertEqual(jumped, [(True, True)], "球落到那一层、停了才跳")
        self.assertEqual(roam_.support.key, 7)

    def test_it_barks_at_a_ball_it_cannot_reach_only_after_the_ball_stops(self):
        self.start_on_floor()
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        self.step(0.3)
        top = self.floor_y - 300.0
        self.add_window(7, self.ag.x() + 20.0, top, self.ag.width() - 40.0)      # 窗口铺满：上不去
        b = pg.ball
        b.x, b.y = self.ag.x() + 300.0, top - b.r - 20.0
        cues = self.cues()
        self.throw_and_fetch(60.0, -1000.0)
        barks = []

        def until():
            if dog.player.name == "Bark":
                barks.append(b.resting)
            return roam_.task is None
        took, seen = self.watch_fetch(20.0, until)
        self.assertIsNotNone(took, seen)
        self.assertTrue(barks and all(barks), "叫了，而且球停了才叫")
        self.assertFalse(roam_.carrying)
        self.assertEqual(cues, ["stumped"], "够不着、叫完：报一次（接歪头）")

    def sit_then_release(self):
        """坐着（萨摩耶默认坐着）拿起球放进圈里等圈满（坐着等、不俯身），再甩出去。"""
        import time as _t
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        self.start_on_floor()
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "一闲下来就坐下")
        self.pick_up_ball()
        seen = set()
        self.assertIsNotNone(self.step(6.0, lambda: (seen.add((dog.posture, roam_.task, roam_.bowing)), pg.ring.ready)[1]), "圈满了")
        self.assertEqual(seen, {("sitting", None, False)}, "坐着看你手里的球、坐着等：不交给 roam、不俯身")
        pg._let_go(-900.0, -500.0, _t.perf_counter())
        self.assertFalse(pg.ball_held)

    def test_letting_go_it_stands_up_first_and_that_is_its_half_beat(self):
        """萨摩耶默认坐着，松手才站起来去追；起身那半拍就是它的「慢半拍」（temper.release_beat 不另加）。"""
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        self.sit_then_release()
        self.assertEqual((roam_.task, roam_.leg["kind"]), ("fetch", "stand"), "先站起来")
        x0 = roam_.wx
        self.step(0.25)
        self.assertEqual(roam_.wx, x0, "起身的时候没挪")
        self.assertIsNotNone(self.step(2.0, lambda: abs(roam_.v) > 0.0), "站起来就跑")
        self.assertEqual(dog.posture, "standing")
        self.assertIsNotNone(self.step(20.0, lambda: roam_.carrying), "照样叼到")
        self.assertIsNotNone(self.step(30.0, lambda: roam_.task is None), "送回来放下")
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "放下球坐回去")

    def test_grabbing_the_ball_again_while_it_stands_up_sits_it_back_down(self):
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        self.sit_then_release()
        self.step(0.1)
        self.pick_up_ball()                                      # 飞着的球一按就抓住，又放回圈里
        self.assertFalse(pg.ring.ready, "圈从空的重新算")
        self.assertIsNone(roam_.task, "不追了")
        x0 = roam_.wx
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "坐回去接着看")
        self.assertEqual(roam_.wx, x0, "没挪")
        self.assertTrue(pg._seat_watch, "坐着看你手里的球，圈接着算")

    def test_a_full_ring_gets_one_seated_woof(self):
        """圈满了坐着叫一声（没有坐着叫的片段：只张一下嘴、放一声狗叫），坐着等。"""
        pg, dog = self.pg, self.win.dog
        self.start_on_floor()
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition))
        played = []
        then = pg.bank.play
        pg.bank.play = lambda name, *a, **k: (played.append(name), then(name, *a, **k))[1]
        self.addCleanup(setattr, pg.bank, "play", then)
        self.pick_up_ball()
        self.assertIsNotNone(self.step(6.0, lambda: pg.ring.ready))
        self.assertEqual(played.count("bark"), 1, "叫一声")
        self.assertTrue(dog.expr.pulses["bark"], "张一下嘴")
        self.assertTrue(dog.expr_rig.mouth_open, "嘴张多大是从 Bark 片段量的")
        self.step(2.0)
        self.assertEqual((dog.posture, played.count("bark")), ("sitting", 1), "坐着等，不再叫")

    def test_the_ball_is_put_down_a_bit_short_of_the_pointer(self):
        """放得没那么准：球比边牧多离鼠标一点，只往狗这一侧让（点击范围照样碰不到鼠标），不会被当成「鼠标挪远了，收回来接着跟」。"""
        from widget.ball import HIT_PAD
        pg, roam_ = self.pg, self.pg.roam
        self.start_on_floor()
        self.step(0.3)
        with mock.patch.object(temper, "drop_short", lambda tune, rng: 0.3), mock.patch.object(temper, "daze", lambda tune, rng: None):
            self.throw_and_fetch(-900.0)
            took, seen = self.watch_fetch(40.0, lambda: roam_.task is None)
        self.assertIsNotNone(took, seen)
        b, cx = pg.ball, self.cursor[0]
        gap = abs(b.x - cx)
        self.assertGreater(gap, b.r + HIT_PAD)
        self.assertGreater(gap, 0.3 * self.win.ppm, "比该放的地方远 0.3 米")
        self.assertLess(gap, 0.75 * self.win.ppm)
        self.assertEqual((b.x - cx > 0), (roam_.wx - cx > 0), "球在鼠标和狗之间：往狗这一侧让的")
        self.assertEqual(seen["phases"].count("putdown"), 1, f"放一次就放下了 {seen['phases']}")

    def test_it_stops_and_stares_once_on_the_way_back(self):
        """叼回来的路上愣一下：站住 0.5 秒、球一直在嘴里，再接着走，最后照样放下。一趟一次。"""
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        self.cursor = (self.ag.x() + 700.0, self.cursor[1])       # 鼠标在右边：叼回来要走两米多
        self.start_on_floor()
        self.step(0.3)
        cues = self.cues()
        with mock.patch.object(temper, "drop_short", lambda tune, rng: 0.0), mock.patch.object(temper, "daze", lambda tune, rng: 0.5):
            self.throw_and_fetch(-900.0)
            self.assertIsNotNone(self.step(20.0, lambda: roam_.carrying))
        self.assertEqual((roam_._daze, roam_._carry_from), (0.5, roam_.wx))
        stops, dropped = [], []

        def watch():
            dazed = roam_.leg is not None and roam_.leg.get("kind") == "wait" and roam_.phase == "deliver"
            if dazed:
                stops.append((roam_.wx, roam_.v, dog.player.name, pg.carried, dog.props.item is not None and dog.props.item["mode"] == "held"))
            if roam_.phase not in ("putdown", "") and not roam_.carrying:
                dropped.append(roam_.phase)
            return roam_.task is None
        self.assertIsNotNone(self.step(25.0, watch), "照样放下了")
        self.assertEqual(cues, ["daze", "put"])
        self.assertAlmostEqual(len(stops) / 60, 0.5, delta=0.05)
        self.assertEqual(len(set(stops)), 1, "站住不动、叼着：Pick_up_idle")
        x, v, clip, carried, held = stops[0]
        self.assertEqual((v, clip, carried, held), (0.0, "Pick_up_idle", True, True))
        self.assertGreaterEqual(abs(x - roam_._carry_from), 0.6 * self.win.ppm, "走出一段才愣")
        self.assertEqual(dropped, [], "放下之前球一直在嘴里")
        self.assertLess(abs(pg.ball.x - self.cursor[0]), 0.45 * self.win.ppm, "还是放到鼠标旁边")


class SixtyThrowsTests(RoomCase):
    """方案量数时用的那 60 次随机扔（测试房间宽 3.3 米）：两只狗都不卡住；萨摩耶每次都追球本身、慢一点、多跑一点、不冲刺。
    不比掉头次数：窄房间里萨摩耶反而少（它慢，球弹回来时还没跑远）。"""

    def test_both_dogs_get_every_ball_and_the_samoyed_is_the_slower_one(self):
        from tests.room_base import throws
        plan = throws()
        stats = {}
        for key in (COLLIE, SAMOYED):
            win = self.win if key == SAMOYED else self.make_window(pack_id=COLLIE)
            self.start_on_floor(win=win)
            rows = self.run_throws(win, plan, limit=8.0)
            win.playground.stop()
            self.assertEqual([i for i, r in enumerate(rows) if r["took"] is None], [], f"{key}：8 秒内都叼到或叫完")
            self.assertEqual([i for i, r in enumerate(rows) if r["bark_moving"]], [], f"{key}：球还在动没叫过")
            self.assertEqual([i for i, r in enumerate(rows) if r["got"] and not r["put"]], [], f"{key}：叼到的都放下了")
            got = [r for r in rows if r["got"]]
            self.assertEqual(len(got), 60, f"{key}：这一组都够得着")
            stats[key] = {"took": sum(r["took"] for r in got) / len(got), "dist": sum(r["dist_m"] for r in got) / len(got),
                          "top": max(r["top"] for r in got), "chased": sum(1 for r in got if "chase" in r["phases"])}
        dog, sam = stats[COLLIE], stats[SAMOYED]
        self.assertGreater(sam["took"], dog["took"] + 0.2, "萨摩耶慢一点")
        self.assertGreater(sam["dist"], dog["dist"] * 1.1, "多跑一点路")
        self.assertEqual(sam["chased"], 60, "每次都追球本身")
        self.assertLess(dog["chased"], 60)
        self.assertLessEqual(sam["top"], self.pack.gaits["run"] + 1e-6, "最快不超过跑的速度")


class SamoyedLoungeTests(RoomCase):
    """自己歇着（活跃度 0.5：默认坐着）：一闲下来就坐下，没人理 60 秒趴下；拿起球、球在动回到坐着，拎它站起来、落地坐回去。"""

    def rest(self, posture="lying", start=True):
        """让它歇好：没人理的钟直接拨到该坐下 / 该趴下的时候（真等那么久的是 test_left_alone_it_sits_then_lies_down）。"""
        dog = self.win.dog
        if start:
            self.start_on_floor()
            self.step(0.5)
        self.pg._idle_for = {"sitting": 0.0, "lying": 60.0}[posture]
        self.assertIsNotNone(self.step(10.0, lambda: (dog.posture, dog.lounge, dog.transition) == (posture, posture, False)), f"歇成 {posture}")
        self.step(0.5)

    def test_left_alone_it_sits_then_lies_down(self):
        """萨摩耶默认坐着——开灵动交互一闲下来就坐下，坐久了（没人理 60 秒）趴下。"""
        dog, pg = self.win.dog, self.pg
        self.start_on_floor()
        took = self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition)
        self.assertIsNotNone(took, "一闲下来就坐下")
        self.assertEqual(dog.lounge, "sitting")
        self.assertFalse(pg.roam.busy, "自己坐下的，不是 roam 牵着")
        self.step(55.0 - took)
        self.assertEqual((dog.posture, dog.transition), ("sitting", False), "55 秒还坐着")
        took = self.step(12.0, lambda: dog.posture == "lying" and not dog.transition)
        self.assertIsNotNone(took, "60 秒趴下")
        self.assertGreater(took, 4.9)
        self.assertEqual((dog.lounge, dog._home_posture()), ("lying", "lying"))

    def test_the_collie_never_rests_on_its_own(self):
        collie = self.make_window(pack_id=COLLIE)
        self.start_on_floor(win=collie)
        seen = set()
        self.step(100.0, lambda: seen.add((collie.dog.posture, collie.dog.lounge)) and False, win=collie)
        self.assertEqual(seen, {("standing", None)}, "边牧灵动交互里一直站着")
        self.assertEqual(collie.playground._idle_for, 0.0, "那几行一行都没走")

    def test_sitting_it_does_not_get_up_for_a_random_action_and_lying_it_only_yawns(self):
        dog = self.win.dog
        self.rest("sitting")
        seen = []
        self.step(55.0, lambda: seen.append((dog.posture, dog.action.id if dog.action else None)) and False)
        self.assertEqual(set(seen), {("sitting", None)}, "坐着：不为了抬爪站起来又坐回去（抬爪最晚 70 秒来一次，这时离上次已经 75 秒）")
        self.step(8.0)
        seen.clear()
        self.assertEqual(dog.posture, "lying")
        self.step(100.0, lambda: seen.append((dog.posture, dog.action.id if dog.action else None)) and False)
        self.assertEqual(set(seen), {("lying", None), ("lying", "yawn")}, "趴着打哈欠")

    def test_picking_up_the_ball_sits_it_up_and_it_waits_seated(self):
        """趴着的拿起球先坐起来再看（不站起来），圈从拿起那一刻算、坐起来也算在里面；满了坐着等，不俯身；放下就去叼，叼回来坐回去。"""
        dog, pg, roam_ = self.win.dog, self.pg, self.pg.roam
        self.rest()
        self.pick_up_ball()
        took = self.step(2.5, lambda: dog.posture == "sitting" and not dog.transition)
        self.assertIsNotNone(took, "坐起来（模型里没有趴着直接坐起来的片段：先起身再坐下，约 1.6 秒）")
        self.assertEqual((dog.lounge, roam_.task), ("sitting", None))
        self.assertIsNotNone(self.step(2.5, lambda: pg.ring.ready), "圈从拿起那一刻算")
        self.assertFalse(roam_.bowing)
        self.put_ball_down()
        self.assertEqual(roam_.task, "fetch", "满过的圈：放下也去叼")
        self.assertIsNotNone(self.step(30.0, lambda: roam_.task is None and pg.ball.resting), "玩完了")
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "放下球坐回去")
        self.assertLess(pg._idle_for, 4.5, "钟是从零重新走的")

    def test_with_fetch_off_it_still_sits_up_to_look_at_the_ball_in_your_hand(self):
        dog, roam_ = self.win.dog, self.pg.roam
        self.rest()
        set_fetch(self.win, False)
        self.pick_up_ball()
        self.assertIsNotNone(self.step(2.5, lambda: dog.posture == "sitting" and not dog.transition), "你拿起球它就坐起来看")
        self.assertEqual((dog.lounge, roam_.task), ("sitting", None))

    def test_being_lifted_gets_it_up_and_it_lands_standing(self):
        dog, pg, roam_ = self.win.dog, self.pg, self.pg.roam
        self.rest()
        pg.dog_grabbed((roam_.wx, roam_.wy))
        self.step(0.5)
        self.assertTrue(roam_.lifted)
        self.win.place_scene(roam_.wx, roam_.wy - 120.0)
        pg.dog_dropped()
        self.assertIsNotNone(self.step(4.0, lambda: roam_.task is None and not roam_.lifted), "落回去了")
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "落地站着，接着坐下（默认坐着）")
        self.assertEqual(dog.lounge, "sitting")
        self.assertLess(pg._idle_for, 4.5, "钟从零走")

    def test_a_click_only_squashes_it(self):
        """点狗只 duang。趴着点一下还趴着，钟也不归零。"""
        dog, pg = self.win.dog, self.pg
        self.rest()
        idle = pg._idle_for
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        w = self.win
        local = QPointF(w.width() / 2.0, w.height() - 40.0)       # 真走一遍鼠标事件：按在狗身上、不挪、松开
        w.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, local, w.mapToGlobal(local), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.step(0.1)
        self.assertGreater(dog.expr.squash, 0.05, "压下去了")
        w.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, local, w.mapToGlobal(local), Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        self.assertFalse(dog.expr.pressing)
        self.step(1.0)
        self.assertEqual((dog.posture, dog.lounge, dog.transition), ("lying", "lying", False))
        self.assertGreater(pg._idle_for, idle + 1.0)

    def test_the_pointer_crossing_sides_does_not_get_it_up_to_turn(self):
        """趴着、坐着只转头（「不为转向起立」）：鼠标换到另一边、窗口又停稳了一次（每次停稳都会问该朝哪），不起立转身。"""
        from PySide6.QtCore import QPoint
        import widget.window as window
        dog, roam_ = self.win.dog, self.pg.roam
        at = {"p": QPoint(round(roam_.wx) - 250, round(self.floor_y) - 100)}
        p = mock.patch.object(window.QCursor, "pos", lambda: at["p"])
        p.start()
        self.addCleanup(p.stop)
        self.rest()
        yaw = dog.yaw
        seen = set()
        for dx in (300, -300):
            at["p"] = QPoint(round(roam_.wx) + dx, round(self.floor_y) - 100)
            self.step(3.0, lambda: seen.add((dog.posture, dog.turn is None, bool(dog.steps))) and False)
            self.win._after_move()
            self.step(3.0, lambda: seen.add((dog.posture, dog.turn is None, bool(dog.steps))) and False)
        self.assertEqual(seen, {("lying", True, False)})
        self.assertEqual(dog.yaw, yaw, "身子没转")
        self.assertEqual(dog.home_yaw, self.win._home_yaw(), "该朝哪记下了")

    def test_on_the_turntable_it_stands_up_the_clock_stops_and_it_lies_back_down_after(self):
        """看细节（进那一页狗就站着）：歇着的上转台先站起来，钟停着、歇成的样子记着；下来回到趴着（进来前的样子），钟接着走。"""
        dog, pg = self.win.dog, self.pg
        self.rest()
        idle = pg._idle_for
        dog.set_turntable(True)
        pg.fetch_changed()
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "standing" and not dog.transition), "站起来")
        seen = set()
        self.step(30.0, lambda: seen.add((dog.posture, dog.lounge, dog.transition)) and False)
        self.assertEqual(seen, {("standing", "lying", False)}, "站着转，歇成的样子记着")
        self.assertEqual(pg._idle_for, idle, "钟停着")
        dog.set_turntable(False)
        pg.fetch_changed()
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "lying" and not dog.transition), "下来回到趴着")
        self.assertEqual(dog.lounge, "lying")
        self.step(1.0)
        self.assertGreater(pg._idle_for, idle, "钟接着走")

    def test_on_the_turntable_it_stands_and_sits_back_down_after(self):
        dog, pg = self.win.dog, self.pg
        self.start_on_floor()
        self.step(5.0)
        self.assertEqual(dog.posture, "sitting")
        idle = pg._idle_for
        dog.set_turntable(True)
        pg.fetch_changed()
        self.step(40.0)
        self.assertEqual((dog.posture, dog.lounge), ("standing", "sitting"), "转台上站着，坐着记着")
        self.assertEqual(pg._idle_for, idle, "转台上那 40 秒没算")
        dog.set_turntable(False)
        pg.fetch_changed()
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "下来坐回去")

    def test_near_the_end_of_a_window_it_sits_but_does_not_lie_down(self):
        dog, pg, roam_ = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor()
        self.step(0.3)
        s = self.climb_window(self.floor_y - 260.0, at=380.0 + 0.4 * self.win.ppm)
        self.assertLess(roam_.wx - s.x0, 0.55 * self.win.ppm)
        self.step(1.0)
        pg._idle_for = 80.0                                       # 该趴下了
        self.step(12.0)
        self.assertEqual((dog.posture, dog.lounge, dog.transition), ("sitting", "sitting", False), "贴着窗口边：趴下有一截悬空，只坐着")
        self.assertEqual((roam_.support.kind, roam_.support.key), ("window", 7))

    def test_it_lies_down_in_the_middle_of_a_window_and_falls_standing_when_the_window_goes(self):
        dog, pg, roam_ = self.win.dog, self.pg, self.pg.roam
        self.start_on_floor()
        self.step(0.3)
        self.climb_window(self.floor_y - 260.0)
        self.step(1.0)
        self.rest(start=False)
        self.assertEqual(roam_.support.key, 7)
        self.frames[7] = (380.0 + 60.0, self.floor_y - 260.0, 360.0, 200.0)      # 窗口挪了：带着走，还趴着
        self.step(1.0)
        self.assertEqual((dog.posture, roam_.support.key), ("lying", 7))
        del self.frames[7]                                                   # 窗口没了：站起来掉下去
        pg._sups = None
        self.assertIsNotNone(self.step(8.0, lambda: roam_.task is None and roam_.support is not None and roam_.support.kind == "floor"), "掉到地面")
        self.assertIsNotNone(self.step(4.0, lambda: dog.posture == "sitting" and not dog.transition), "站着落地，接着坐下")
        self.assertEqual(dog.lounge, "sitting")
        self.assertAlmostEqual(roam_.wy, self.floor_y, delta=1.0)

    def test_turning_the_playground_off_goes_back_to_the_posture_you_picked(self):
        dog = self.win.dog
        self.rest()
        dog.set_rest_posture("sitting")                           # 灵动交互开着：只记下
        self.assertEqual(dog.posture, "lying")
        self.win.set_dynamic(False)
        self.assertIsNone(dog.lounge)
        for _ in range(int(6.0 * 60)):
            dog.update(1 / 60)
        self.assertEqual((dog.posture, dog.transition), ("sitting", False), "回到选的姿势")

    def test_raising_the_energy_gets_a_resting_dog_back_up(self):
        """开发者设置页把活跃度拉回 1：不再自己歇，趴着的站起来。"""
        dog = self.win.dog
        self.rest()
        self.win.tuning.set("energy", 1.0)
        self.assertIsNotNone(self.step(3.0, lambda: dog.posture == "standing" and not dog.transition))
        self.assertIsNone(dog.lounge)


class MomentsPureTests(unittest.TestCase):
    """招牌时刻的纯函数（temper.Mood、express）。"""

    def test_a_dog_with_both_at_one_is_never_touched(self):
        from widget.expression import Expression
        e = Expression(eyes=0.11, ears=0.22, wag=0.33, tilt=4.0, lift=5.0, crouch=0.06)
        before = dict(vars(e), cur=dict(e.cur), pulses={k: list(v) for k, v in e.pulses.items()})
        mood = temper.Mood(smile_until=99.0, tilt_until=99.0, greet_until=99.0)
        temper.express(e, mood, 1.0, 0.0, 0.0, True, -1.0)
        self.assertEqual(dict(vars(e), cur=dict(e.cur), pulses={k: list(v) for k, v in e.pulses.items()}), before)

    def test_smile_tilt_greet_and_relaxed_eyes(self):
        from widget.expression import Expression
        mood = temper.Mood()
        mood.cue("put", 10.0)
        e = Expression(wag=0.2)
        temper.express(e, mood, 10.5, 0.6, 0.5, False, -1.0)
        self.assertEqual((round(e.eyes, 6), round(e.ears, 6), round(e.lift, 6), e.wag, e.tilt), (0.45, 0.36, 4.8, 0.6, 0.0), "笑：眯眼、耳朵往后、抬一点头、摇尾巴")
        e = Expression(wag=0.95)
        temper.express(e, mood, 10.5, 0.6, 0.5, False, -1.0)
        self.assertEqual(e.wag, 0.95, "尾巴本来摇得更欢就不压它")
        e = Expression()
        temper.express(e, mood, 12.3, 0.6, 0.5, False, -1.0)
        self.assertEqual((e.eyes, e.ears, e.lift, e.wag), (0.0, 0.0, 0.0, 0.0), "2.2 秒就收")
        for cue, seconds in (("fooled", 1.6), ("stumped", 1.6), ("daze", 0.5)):
            mood = temper.Mood()
            mood.cue(cue, 0.0)
            left, right, late = Expression(), Expression(), Expression()
            temper.express(left, mood, seconds - 0.01, 0.6, 0.5, False, -1.0)
            temper.express(right, mood, seconds - 0.01, 0.6, 0.5, False, 1.0)
            temper.express(late, mood, seconds + 0.01, 0.6, 0.5, False, 1.0)
            self.assertAlmostEqual(left.tilt, 14.4, places=9, msg=cue)
            self.assertAlmostEqual(right.tilt, -14.4, places=9, msg="朝右时反过来：两边看着一样")
            self.assertEqual((late.tilt, left.eyes), (0.0, 0.0))
        mood = temper.Mood()
        mood.cue("nothing", 0.0)                                 # 不认识的时刻：不理
        self.assertEqual((mood.smile_until, mood.tilt_until), (0.0, 0.0))
        mood = temper.Mood()                                     # 被晃到、路上愣住来得勤：歪过一次，TILT_AGAIN_S 秒内不再歪；够不着叫完每次都歪
        self.assertTrue(mood.cue("fooled", 100.0))
        self.assertFalse(mood.cue("fooled", 110.0))
        self.assertFalse(mood.cue("daze", 100.0 + temper.TILT_AGAIN_S - 0.1))
        self.assertEqual(mood.tilt_until, 100.0 + temper.TILT_S, "没演的那几次不延长")
        self.assertTrue(mood.cue("stumped", 112.0))
        self.assertEqual(mood.tilt_until, 112.0 + temper.TILT_S)
        self.assertTrue(mood.cue("fooled", 100.0 + temper.TILT_AGAIN_S))
        self.assertTrue(mood.cue("put", 101.0), "笑不受这个间隔管")
        e = Expression()
        temper.express(e, temper.Mood(), 5.0, 0.6, 0.5, True, 1.0)
        self.assertEqual((e.eyes, e.wag, e.tilt), (0.25, 0.0, 0.0), "趴着眼睛放松")
        e = Expression()
        temper.express(e, temper.Mood(), 5.0, 0.6, 0.0, True, 1.0)
        self.assertEqual(e.eyes, 0.0, "只憨不懒：不眯")

    def test_the_pointer_greeting_needs_an_arrival_a_free_dog_and_a_pause(self):
        mood = temper.Mood()
        mood.pointer(True, 0.0, True)
        self.assertEqual(mood.greet_until, 0.0, "一开始鼠标就在旁边：不算")
        mood.pointer(False, 1.0, True)
        mood.pointer(True, 2.0, False)
        self.assertEqual(mood.greet_until, 0.0, "狗在忙：不打招呼")
        mood.pointer(True, 3.0, True)
        self.assertEqual(mood.greet_until, 0.0, "已经在跟前了：要从远处进来才算")
        mood.pointer(False, 4.0, True)
        mood.pointer(True, 5.0, True)
        self.assertEqual((mood.greet_until, mood.greet_again_at), (7.5, 25.0), "摇 2.5 秒；20 秒内不重来")
        mood.pointer(False, 10.0, True)
        mood.pointer(True, 24.9, True)
        self.assertEqual(mood.greet_until, 7.5)
        mood.pointer(False, 25.5, True)
        mood.pointer(True, 26.0, True)
        self.assertEqual(mood.greet_until, 28.5)
        e_far, e_near = (__import__("widget.expression", fromlist=["Expression"]).Expression() for _ in range(2))
        temper.express(e_near, mood, 27.0, 0.6, 0.5, False, 1.0)
        temper.express(e_far, mood, 29.0, 0.6, 0.5, False, 1.0)
        self.assertEqual((e_near.wag, e_far.wag), (0.3, 0.0), "轻轻摇：0.30")


class SamoyedMomentsTests(RoomCase):
    def far(self):
        return (self.ag.x() + 200.0, self.floor_y - 150.0)

    def watch_glances(self, seconds, vx=500.0):
        """不去追地甩一个球（狗只看着），推 seconds 秒：记下呆萌来回看演了哪几段、各多久（看球 / 看你）。"""
        pg = self.pg
        b = pg.ball
        b.throw(vx, -300.0, self.win.ppm)
        pg.throw_id += 1
        seq = []

        def watch():
            if pg.glancing:
                p = pg.look_point()
                who = "ball" if p == (b.x, b.y) else "you" if p == self.cursor else "?"
                if not seq or seq[-1][0] != who:
                    seq.append([who, 0.0])
                seq[-1][1] += DT
            return False
        self.step(seconds, watch)
        return seq

    def test_the_glance_chance_is_point_six_times_goofy(self):
        """球停下那一刻按 0.6 × 憨 触发（萨摩耶 0.36），边牧一次都没有。"""
        self.assertAlmostEqual(temper.glance_chance(SAM), 0.36, places=9)
        self.assertEqual(temper.glance_chance({"energy": 1.0, "smarts": 1.0}), 0.0)
        self.assertEqual([s for _, s in temper.GLANCE], [0.5, 0.6, 0.5, 0.6])
        self.assertEqual(temper.GLANCE_AGAIN_S, temper.TILT_AGAIN_S)

    def test_a_ball_it_only_watched_stops_and_it_glances_ball_you_ball_you(self):
        """球停下：看球 0.5 秒—看你 0.6—看球 0.5—看你 0.6，之后照常；只动头，身子不转；狗不去追。"""
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        self.start_on_floor(x=600.0)
        self.step(2.0)
        self.cursor = self.far()
        yaw = dog.yaw
        with mock.patch.object(temper, "glance_chance", lambda tune: 1.0):
            seq = self.watch_glances(12.0)
        self.assertEqual([w for w, _ in seq], ["ball", "you", "ball", "you"])
        for (_, got), (_, want) in zip(seq, temper.GLANCE):
            self.assertAlmostEqual(got, want, delta=2.5 * DT)
        self.assertIsNone(roam_.task, "只看着，不去追")
        self.assertFalse(pg.glancing, "演完了")
        self.assertAlmostEqual(dog.yaw, yaw, delta=1.0, msg="身子没跟着转")

    def test_not_again_within_25_seconds_and_a_pickup_stops_it(self):
        pg = self.pg
        self.start_on_floor(x=600.0)
        self.step(2.0)
        self.cursor = self.far()
        with mock.patch.object(temper, "glance_chance", lambda tune: 1.0):
            self.assertTrue(self.watch_glances(8.0), "第一次演了")
            self.assertEqual(self.watch_glances(8.0, vx=-500.0), [], "25 秒内不再演")
            self.step(10.0)
            b = pg.ball
            b.throw(500.0, -300.0, self.win.ppm)
            pg.throw_id += 1
            self.assertIsNotNone(self.step(8.0, lambda: pg.glancing), "过了 25 秒又演")
            self.pick_up_ball()
            self.assertFalse(pg.glancing, "拿起球就停")

    def test_the_collie_never_glances(self):
        collie = self.make_window(pack_id=COLLIE)
        self.start_on_floor(win=collie)
        pg = collie.playground
        seen = []
        for k in range(6):
            pg.ball.throw((-1) ** k * 500.0, -300.0, collie.ppm)
            pg.throw_id += 1
            self.step(30.0, lambda: seen.append(pg.glancing) and False, win=collie)
        self.assertFalse(any(seen))

    def beside(self):
        roam_ = self.pg.roam
        return (roam_.wx + 0.5 * self.win.ppm, roam_.wy - 0.4 * self.win.ppm)       # 离身子正中 0.5 米（0.9 个身高 = 0.77 米以内）

    def test_it_smiles_after_putting_the_ball_down(self):
        pg, roam_, e = self.pg, self.pg.roam, self.win.dog.expr
        self.start_on_floor()
        self.step(0.3)
        with mock.patch.object(temper, "daze", lambda tune, rng: None):
            self.throw_and_fetch(-900.0)
            self.assertIsNotNone(self.step(40.0, lambda: not pg.carried and roam_.task is None and roam_.t > 1.0), "叼回来放下了")
        self.step(0.5)
        self.assertAlmostEqual(e.eyes, 0.45, places=6)
        self.assertAlmostEqual(e.ears, 0.36, places=6)
        self.assertAlmostEqual(e.lift, 4.8, places=6)
        self.assertGreaterEqual(e.wag, 0.6)
        self.assertGreater(e.cur["eyes"], 0.4, "真眯上了")
        self.assertEqual(e.tilt, 0.0)
        self.step(2.5)
        self.assertEqual((e.eyes, e.ears, e.lift), (0.0, 0.0, 0.0), "笑 2.2 秒")
        self.assertLess(e.cur["eyes"], 0.01)

    def test_it_tilts_its_head_when_fooled_and_when_stumped(self):
        pg, roam_, dog = self.pg, self.pg.roam, self.win.dog
        e = dog.expr
        self.start_on_floor()
        self.step(0.3)
        pg._cue("fooled")
        self.assertTrue(e.pulses["ears"], "被晃到：耳朵一抖")
        self.step(0.5)
        sign = 1.0 if math.cos(math.radians(dog.yaw)) < 0.0 else -1.0
        self.assertAlmostEqual(e.tilt, 14.4 * sign, places=6)
        self.assertAlmostEqual(e.cur["tilt"], 14.4 * sign, delta=2.5)
        self.step(1.5)
        self.assertEqual(e.tilt, 0.0, "歪 1.6 秒")
        top = self.floor_y - 300.0                               # 够不着：窗口铺满，球在上面
        self.add_window(7, self.ag.x() + 20.0, top, self.ag.width() - 40.0)
        b = pg.ball
        b.x, b.y = self.ag.x() + 300.0, top - b.r - 20.0
        self.throw_and_fetch(60.0, -1000.0)
        tilted = []
        self.assertIsNotNone(self.step(20.0, lambda: (tilted.append(e.tilt), roam_.task is None)[1]))
        self.assertEqual(set(tilted[:-1]), {0.0}, "叫完之前不歪")
        self.step(0.3)
        self.assertAlmostEqual(abs(e.tilt), 14.4, places=6, msg="够不着，叫完歪头")

    def test_a_bounced_ball_fools_it_in_a_real_chase(self):
        pg, roam_, e = self.pg, self.pg.roam, self.win.dog.expr
        self.start_on_floor(x=600.0)
        self.step(0.3)
        cues = []
        then = roam_.on_cue
        fooled, aim = [], []                                     # 被晃到那一刻：在哪、多快、往哪边、球多快；这之后要跑到哪

        def on_cue(name):
            cues.append((name, roam_.phase, abs(roam_.v) > 0.0))
            if name == "fooled" and not fooled:
                fooled.append((roam_.wx, roam_.v, roam_.leg["dir"], pg.ball.vx))
            then(name)
        roam_.on_cue = on_cue

        def watch():
            if fooled and not aim:
                aim.append(roam_.leg["to"])
            return roam_.carrying
        b = pg.ball
        b.x, b.y = 300.0, self.floor_y - 200.0
        b.resting = False
        b.on = None
        self.win.dog.set_lounge(None)
        self.win.dog.settle_into("standing")                     # 从站着开始追（萨摩耶默认坐着；这里只看被晃到的那一下）
        self.throw_and_fetch(-1500.0, -200.0)                    # 朝左墙甩：狗追过去，球弹回来从它身边过
        self.assertIsNotNone(self.step(20.0, watch))
        self.assertIn(("fooled", "chase", True), cues, "追着跑的时候被晃到")
        (x, v, d, ball_vx), to = fooled[0], aim[0]
        self.assertLess(ball_vx * d, -self.win.ppm, "球朝身后去了")
        self.assertGreater(abs(v), self.win.ppm, "正跑着")
        stop = v * v / (2.0 * roam.ACCEL_M * self.win.ppm)
        self.assertAlmostEqual((to - x) * d, stop + abs(v) * 0.15, delta=0.01, msg="还照原样往前冲 0.15 秒，再刹住（不急停）")
        self.assertEqual([c for c in cues if c[0] == "fooled" and not c[2]], [], "只在跑着的时候")

    def test_the_pointer_coming_close_gets_a_gentle_wag_but_not_again_right_away(self):
        pg, roam_, e = self.pg, self.pg.roam, self.win.dog.expr
        self.cursor = self.far()
        self.start_on_floor()
        self.step(1.0)
        self.assertEqual(e.wag, 0.0)
        self.cursor = self.beside()
        self.step(0.2)
        self.assertAlmostEqual(e.wag, 0.3, places=6, msg="轻轻摇")
        self.assertEqual((e.eyes, e.tilt), (0.0, 0.0))
        self.step(2.5)
        self.assertEqual(e.wag, 0.0, "摇 2.5 秒")
        self.cursor = self.far()
        self.step(5.0)
        self.cursor = self.beside()
        self.step(0.5)
        self.assertEqual(e.wag, 0.0, "20 秒内再来一次：不重演")
        self.cursor = self.far()
        self.step(13.0)
        self.cursor = self.beside()
        self.step(0.2)
        self.assertAlmostEqual(e.wag, 0.3, places=6, msg="过了 20 秒：又摇")

    def test_no_greeting_while_it_is_busy_or_you_hold_the_ball(self):
        pg, roam_, e = self.pg, self.pg.roam, self.win.dog.expr
        self.cursor = self.far()
        self.start_on_floor()
        self.step(1.0)
        floor = pg.world.floors[0]
        roam_.go_to(floor, floor.x0 + 60.0)                       # 在跑
        self.step(0.4)
        self.assertTrue(roam_.busy)
        self.cursor = (roam_.wx - 0.3 * self.win.ppm, roam_.wy - 0.4 * self.win.ppm)
        self.step(0.2)
        self.assertEqual(pg.mood.greet_until, 0.0, "在跑：不打招呼")
        self.assertIsNotNone(self.step(10.0, lambda: roam_.task is None))
        self.cursor = (self.ag.x() + 700.0, self.floor_y - 150.0)   # 狗跑到左边去了：鼠标挪到右边远处
        self.step(1.0)
        self.assertFalse(pg.mood.near)
        pg.ball_held = True                                      # 球在你手上（捡球关着，狗只看着）
        self.win.fetch_on = False
        self.cursor = self.beside()
        self.step(0.2)
        self.assertEqual(pg.mood.greet_until, 0.0, "球在手上：不打招呼")

    def test_lying_down_its_eyes_relax(self):
        dog, pg = self.win.dog, self.pg
        self.start_on_floor()
        self.step(0.5)
        pg._idle_for = 80.0
        self.assertIsNotNone(self.step(10.0, lambda: dog.posture == "lying" and not dog.transition))
        self.step(0.5)
        self.assertEqual(dog.expr.eyes, 0.25)
        self.assertAlmostEqual(dog.expr.cur["eyes"], 0.25, delta=0.02)

    def test_the_collie_through_the_same_moments_shows_none_of_them(self):
        collie = self.make_window(pack_id=COLLIE)
        pg, roam_, e = collie.playground, collie.playground.roam, collie.dog.expr
        self.cursor = self.far()
        self.start_on_floor(win=collie)
        seen = set()
        watch = lambda: seen.add((e.eyes, e.ears, e.tilt, e.lift)) and False      # noqa: E731
        self.step(1.0, watch, win=collie)
        self.cursor = (roam_.wx + 0.5 * collie.ppm, roam_.wy - 0.4 * collie.ppm)   # 鼠标靠近
        self.step(1.0, watch, win=collie)
        self.assertEqual(e.wag, 0.0, "边牧：鼠标靠近尾巴不摇")
        for name in ("put", "fooled", "stumped", "daze"):
            pg._cue(name)
        self.step(0.5, watch, win=collie)
        self.cursor = self.far()
        pg.ball.throw(-900.0, -300.0, collie.ppm)
        pg.throw_id += 1
        roam_.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: (watch(), roam_.task is None and not pg.carried and roam_.t > 3.0)[1], win=collie))
        self.step(3.0, watch, win=collie)
        self.assertEqual(seen, {(0.0, 0.0, 0.0, 0.0)})
        self.assertEqual(vars(pg.mood), vars(temper.Mood()), "什么都没记")
        self.assertFalse(e.pulses["ears"])


if __name__ == "__main__":
    unittest.main()
