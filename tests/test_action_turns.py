"""外部转向切断动作；动作自己的转向不切断，旧姿势、道具淡出和落地保持连续；跟鼠标的转身一开始就动、不过头（曲线不用模型也测）。"""
import math
import unittest
from pathlib import Path

import config
from widget import gltf
from widget.clips import ACTIONS, FADE_CLIP, SLEEP_PLANS, TURN_180, TURN_90
from widget.dogctl import DogController
from widget.play import (ActionStep, BODY_FLIP_LENGTHS, BODY_TURN_COOLDOWN, BODY_TURN_DEBOUNCE, CUT_SECONDS, FOLLOW_TURN_FADE, TURN_SPEED, TurnState,
                         _ease, _ease_quick_start, _wrap)


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class ActionTurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = gltf.load(config.MODEL_PATH)

    @staticmethod
    def tick(c, seconds=1 / 60):
        for _ in range(round(seconds * 60)):
            c.action_at = math.inf
            c._rare_next = {name: math.inf for name in c._rare_next}
            c.update(1 / 60)
            c.frame()

    def until(self, c, pred, seconds=10):
        for _ in range(round(seconds * 60)):
            if pred():
                return
            self.tick(c)
        self.fail(f"状态未在 {seconds} 秒内到达：{c.phase}, {c.player.name}")

    def dog(self):
        c = DogController(self.model, seed=1)
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self.tick(c, 6)
        return c

    def assert_yaw(self, c, expected):
        self.assertAlmostEqual((c.yaw - expected + 180) % 360 - 180, 0, places=5)

    def test_home_turn_cuts_every_action_and_never_resumes_old_steps(self):
        for action in ACTIONS:
            with self.subTest(action=action.id):
                c = self.dog()
                c.do_action(action.id)
                self.until(c, lambda: c.run is not None)
                self.tick(c, 0.15)
                yaw = c.yaw
                c.set_home_yaw(210.0)
                self.assertIsNone(c.run)
                self.assertIsNone(c.manual)
                self.assertIsNone(c.jump)
                self.assertFalse(any(isinstance(s, ActionStep) for s in c.steps))
                self.assertEqual(c.yaw, yaw, "收到转身时从实际朝向开始，不能先跳回动作起点")
                self.until(c, lambda: not c.steps and c.turn is None and not c.transition)
                self.assert_yaw(c, 210)
                self.assertEqual(c.posture, "standing", "动作所需的临时姿势不能变成最终姿势")
                self.tick(c, 0.5)
                self.assertIsNone(c.run)
                self.assertEqual(c.frame().props, ())

    def test_mouse_turn_cuts_food_and_water_bowls_at_their_world_position(self):
        for action in ("eating", "drinking"):
            with self.subTest(action=action):
                c = self.dog()
                c.do_action(action)
                self.until(c, lambda: c.props.bowl is not None and c.props.bowl["alpha"] == 1)
                bowl = c.props.bowl
                at = (bowl["x"], bowl["z"])
                c.set_look_target((c.x - 3, 0.5, c.z))
                self.tick(c)
                self.assertIsNone(c.run, "过线的那一帧就切（turn_delay 0，不等）")
                self.assertIsNotNone(c.turn)
                self.assertIsNone(c.manual_progress())
                self.assertTrue(bowl["out"])
                self.assertEqual((bowl["x"], bowl["z"]), at)
                self.tick(c, CUT_SECONDS + 0.05)
                self.assertIsNone(c.props.bowl)

    def test_home_turn_fades_ground_held_and_put_down_items_without_respawning(self):
        for action in ("carrying", "fetching"):
            for phase in ("ground", "held", "put_down"):
                with self.subTest(action=action, phase=phase):
                    c = self.dog()
                    c.do_action(action)
                    self.until(c, lambda: c.props.item is not None and (
                        c.player.name == "Put_down" if phase == "put_down" else c.props.item["mode"] == phase))
                    item = c.props.item
                    mode, at = item["mode"], (item["x"], item["z"])
                    c.set_home_yaw(210)
                    self.assertIsNone(c.props.active)
                    self.assertTrue(item["out"])
                    self.tick(c, 0.1)
                    if c.props.item is not None:
                        self.assertEqual(item["mode"], mode)
                        if mode == "held":
                            draw = next(p for p in c.frame().props if p.mesh in ("bone", "ball"))
                            self.assertLess(math.dist(draw.matrix[12:15], c.head_position()), 0.2)
                        else:
                            self.assertEqual((item["x"], item["z"]), at)
                    self.tick(c, 0.4)
                    self.assertIsNone(c.props.item)
                    self.tick(c, 2)
                    self.assertIsNone(c.props.item)

    def test_fixed_mouse_does_not_cancel_internal_fetch_turns_or_spin(self):
        for action in ("fetching", "spin"):
            with self.subTest(action=action):
                c = self.dog()
                c.set_look_target((c.x + 3, 0.5, c.z))
                c.do_action(action)
                seen = set()
                for _ in range(20 * 60):
                    self.tick(c)
                    seen.add(c.player.name)
                    if c.run is not None:
                        self.assertIsNotNone(c.manual)
                        self.assertIsNone(c.settle.yaw)
                        if c.props.item is not None:
                            self.assertFalse(c.props.item["out"])
                    elif not c.steps:
                        break
                self.assertIsNone(c.run)
                self.assert_yaw(c, 330)
                if action == "fetching":
                    self.assertIn("Put_down", seen, "内部转身后继续跑回、放球")
                    self.assertEqual(c.props.item["mode"], "linger")
                else:
                    self.assertIn("Turn_L_IP", seen)

    def test_mouse_can_interrupt_internal_turn_from_current_yaw_without_overshoot(self):
        c = self.dog()
        c.do_action("fetching")
        self.until(c, lambda: c.turn is not None)
        self.tick(c, 0.2)
        c.set_look_target((c.x - 3, 0.5, c.z))
        self.until(c, lambda: c.run is None, 0.6)
        self.assertIsNotNone(c.turn)
        self.assertEqual(c.turn.start, c.yaw)
        self.assertEqual(c.turn.target, 210)
        self.assertIsNone(c.settle.yaw)
        self.until(c, lambda: c.turn is None)
        self.assert_yaw(c, 210)
        self.assertAlmostEqual(c._cooldown_until - c.t, BODY_TURN_COOLDOWN)
        c.set_look_target((c.x + 3, 0.5, c.z))
        self.tick(c, BODY_TURN_COOLDOWN / 2)
        self.assertIsNone(c.turn, "转完还有 BODY_TURN_COOLDOWN 的冷却才能再转（0.1 秒）")
        self.until(c, lambda: c.turn is not None, BODY_TURN_COOLDOWN + 0.1)

    def test_a_quarter_turn_keeps_the_long_fade_and_so_does_a_quick_reverse_after_it(self):
        """90° 的片段（Turn_L_IP / Turn_R_IP）首尾的前爪离待机、离 180° 片段 18～20 厘米：跟鼠标转也淡入长的；
        刚转完 90° 马上往回转，腿还是 90° 片段末尾的样子，也淡入长的。只有 180° 的、从待机或刚转完 180° 起步才用短的。"""
        c = self.dog()
        self.until(c, lambda: c.player.prev is None and c.turn is None)
        c._start_turn(60.0)
        self.assertIn(c.player.name, TURN_90.values())
        self.assertTrue(c.turn.follow)
        self.assertAlmostEqual(c.player.fade_total, FADE_CLIP / TURN_SPEED, msg="90° 从待机起步：淡入长的")
        while c.turn is not None:
            self.tick(c)
        self.assertIsNotNone(c.player.prev, "刚转完：正淡回待机")
        c._start_turn(-120.0)
        self.assertIn(c.player.name, TURN_180.values())
        self.assertAlmostEqual(c.player.fade_total, FADE_CLIP / TURN_SPEED, msg="腿还是 90° 片段末尾的样子：照旧淡入长的")

    def test_follow_turn_starts_at_once_and_settles_without_overshoot(self):
        """跟鼠标转身更跟手——过线就转（turn_delay 0）、放快（TURN_SPEED）、一开始就动（TurnState.follow），转完停稳、不过头。
        腿是待机或刚转完的样子时只淡入 FOLLOW_TURN_FADE（腿跟上身子，脚少滑），马上往回转也是；从别的姿势淡过来（切掉的动作、roam 刚交回）照旧淡入 FADE_CLIP / 速度；
        动作里的转身（捡回、转身动作）原速、两头慢。"""
        c = self.dog()
        self.until(c, lambda: c.player.prev is None and c.turn is None)
        c.set_look_target((c.x - 3, 0.5, c.z))
        self.tick(c)
        t = c.turn
        self.assertIsNotNone(t, "过线的那一帧就开始转")
        self.assertTrue(t.follow)
        self.assertAlmostEqual(c.player.fade_total, FOLLOW_TURN_FADE)
        self.assertAlmostEqual(c.player.speed, TURN_SPEED)
        self.assertAlmostEqual(t.duration, self.model.clips[c.player.name].duration / TURN_SPEED)
        yaws = [c.yaw]
        while c.turn is not None:
            self.tick(c)
            yaws.append(c.yaw)
        steps = [_wrap(b - a) for a, b in zip(yaws, yaws[1:])]
        self.assertGreater(-steps[0], 2.0, "转身的第一帧就转了好几度（两头慢的不到 0.5°）")
        self.assertTrue(all(d <= 1e-9 for d in steps), "一路朝一个方向转：不回头、不过头")
        self.assertLess(-steps[-1], -steps[0], "末尾比起步慢：停稳，不是一下刹住")
        self.assertLess(-steps[-2], 0.25 * max(-s for s in steps), "倒数第二帧（整帧）已经慢下来：线性的转到最后一帧还是全速")
        self.assert_yaw(c, 210)
        self.assertIsNotNone(c.player.prev, "刚转完：正淡回待机")
        c.set_look_target((c.x + 3, 0.5, c.z))
        self.until(c, lambda: c.turn is not None, BODY_TURN_COOLDOWN + 0.1)
        self.assertTrue(c.turn.follow)
        self.assertAlmostEqual(c.player.fade_total, FOLLOW_TURN_FADE, msg="马上往回转（还在淡回待机）：腿就是转身片段末尾的样子，淡入照样短")

        c = self.dog()
        c.do_action("bow")
        self.until(c, lambda: c.run is not None)
        self.tick(c, 0.3)
        c.set_look_target((c.x - 3, 0.5, c.z))
        self.tick(c)
        self.assertIsNone(c.run)
        self.assertTrue(c.turn.follow, "切掉动作再转也是跟鼠标的转身：一样快、一开始就动")
        self.assertAlmostEqual(c.player.fade_total, FADE_CLIP / TURN_SPEED, msg="刚切掉动作：淡入照旧，不从伏地的姿势一下弹到转身")

        c = self.dog()
        c.puppet_begin()
        c.puppet_play("Run_F_IP", loop=True)
        self.tick(c, 0.5)
        c.puppet_end()
        c.set_look_target((c.x - 3, 0.5, c.z))
        self.tick(c)
        self.assertTrue(c.turn.follow)
        self.assertAlmostEqual(c.player.fade_total, FADE_CLIP / TURN_SPEED, msg="roam 刚交回（还在从跑的姿势淡回待机）：不是待机、也不是刚转完，淡入照旧长")

        c = self.dog()
        c.do_action("turning")
        self.until(c, lambda: c.turn is not None)
        self.assertFalse(c.turn.follow, "动作里的转身不是跟鼠标的：两头慢")
        self.assertEqual(c.player.speed, 1.0, "原速")
        self.assertAlmostEqual(c.player.fade_total, FADE_CLIP)

    def test_external_turn_lands_airborne_action_and_standalone_jump_smoothly(self):
        for manual in (False, True):
            with self.subTest(manual=manual):
                c = self.dog()
                if manual:
                    c.do_action("jumping")
                else:
                    c.set_dynamic(True)
                    c._start_jump()
                self.until(c, lambda: c.y_offset > 0.1)
                before = c.y_offset
                c.set_home_yaw(210)
                self.assertIsNone(c.jump)
                self.assertEqual(c.jump_queue, 0)
                self.assertEqual(c.y_offset, before)
                self.assertIsNotNone(c.settle.drop)
                self.tick(c, CUT_SECONDS / 2)
                self.assertGreater(c.y_offset, 0)
                self.assertLess(c.y_offset, before)
                self.tick(c, CUT_SECONDS / 2 + 0.05)
                self.assertEqual(c.y_offset, 0)
                self.assertEqual(c.pitch, 0)
                self.assertIsNone(c.settle.drop)

    def test_interrupted_action_returns_to_original_posture_and_sleep_style(self):
        for posture, style in (("lying", None), ("sitting", None), *(("sleeping", s) for s in SLEEP_PLANS)):
            with self.subTest(posture=posture, style=style):
                c = self.dog()
                if style:
                    c.sleep_styles = (style,)
                c.set_rest_posture(posture)
                self.until(c, lambda: not c.steps and not c.transition)
                c.do_action("carrying")
                self.until(c, lambda: c.props.item is not None and c.props.item["mode"] == "held")
                c.set_home_yaw(210)
                self.until(c, lambda: not c.steps and c.turn is None and not c.transition)
                self.assertEqual(c.posture, posture)
                self.assertEqual(c.sleep_style, style)
                self.assert_yaw(c, 210)
                self.assertIsNone(c.manual)

    def test_home_turn_discards_action_waiting_for_posture(self):
        c = self.dog()
        c.do_action("yawn")
        self.tick(c)
        self.assertTrue(any(isinstance(s, ActionStep) for s in c.steps))
        c.set_home_yaw(210)
        self.assertFalse(any(isinstance(s, ActionStep) for s in c.steps))
        self.until(c, lambda: not c.steps and c.turn is None and not c.transition)
        self.assertEqual(c.posture, "standing")
        self.assert_yaw(c, 210)

    def test_mouse_near_disabled_or_nonstanding_does_not_interrupt(self):
        for gate in ("near", "disabled", "nonstanding"):
            with self.subTest(gate=gate):
                c = self.dog()
                if gate == "disabled":
                    c.set_auto_turn(False)
                c.do_action("yawn" if gate == "nonstanding" else "carrying")
                self.until(c, lambda: c.run is not None)
                run = c.run
                distance = 0.5 * c.body_length if gate == "near" else 3
                c.set_look_target((c.x - distance, 0.5, c.z))
                self.tick(c, 0.7)
                self.assertIs(c.run, run)
                self.assertIsNone(c.turn)

    def test_reversing_home_mid_turn_uses_current_yaw_and_latest_target(self):
        c = self.dog()
        c.do_action("spin")
        self.tick(c, 0.6)
        c.set_home_yaw(210)
        self.tick(c, 0.2)
        yaw = c.yaw
        c.set_home_yaw(330)
        self.assertEqual(c.yaw, yaw)
        self.assertEqual(c.turn.start, yaw)
        self.assertIsNone(c.settle.yaw)
        self.until(c, lambda: c.turn is None)
        self.assert_yaw(c, 330)



class FollowTurnCurveTests(unittest.TestCase):
    """不用模型：跟鼠标转身的曲线和默认值。"""

    def test_quick_start_moves_at_once_and_ends_at_rest_without_overshoot(self):
        f, h = _ease_quick_start, 1e-4
        self.assertEqual((f(0.0), f(1.0)), (0.0, 1.0))
        self.assertEqual((f(-1.0), f(2.0)), (0.0, 1.0), "超出范围夹住")
        self.assertAlmostEqual(f(h) / h, 1.0, places=3, msg="起步就是平均速度")
        self.assertLess(_ease(h) / h, 0.01, "两头慢的起步几乎不动（别的转身照旧用它）")
        samples = [f(i / 400) for i in range(401)]
        self.assertEqual(samples, sorted(samples), "一路单调")
        self.assertLessEqual(max(samples), 1.0, "不过头")
        self.assertLess((1.0 - f(1.0 - h)) / h, 0.01, "停的时候速度到 0：不是一下刹住")
        self.assertAlmostEqual(max((samples[i + 1] - samples[i]) * 400 for i in range(400)), 4 / 3, places=2, msg="最快是平均的 4/3 倍")

    def test_turn_state_picks_the_curve(self):
        t = TurnState(330.0, -120.0, 0.5, elapsed=0.05, follow=True)
        self.assertAlmostEqual(t.yaw_now(), 330.0 - 120.0 * _ease_quick_start(0.1))
        t.follow = False
        self.assertAlmostEqual(t.yaw_now(), 330.0 - 120.0 * _ease(0.1))
        t.elapsed = 0.6
        self.assertAlmostEqual(t.yaw_now(), t.target, msg="过了时长停在终点")

    def test_tuning_defaults_are_the_play_constants(self):
        """默认值只写在 play.py 一处（没接调参时控制器直接用），开发者设置页读它。"""
        from widget.tuning import PET_PARAMS
        d = {p.key: p for p in PET_PARAMS}
        self.assertEqual((d["turn_reach"].default, d["turn_delay"].default, d["turn_speed"].default, d["turn_rest"].default),
                         (BODY_FLIP_LENGTHS, BODY_TURN_DEBOUNCE, TURN_SPEED, BODY_TURN_COOLDOWN))
        self.assertEqual((BODY_FLIP_LENGTHS, BODY_TURN_DEBOUNCE, TURN_SPEED, BODY_TURN_COOLDOWN), (0.6, 0.0, 1.35, 0.1),
                         "过线的位置不动，不等、歇得短；转身片段放慢到 1.35 倍，反应不变")
        for p in d.values():
            self.assertLessEqual(p.lo, p.default)
            self.assertLessEqual(p.default, p.hi)


if __name__ == "__main__":
    unittest.main()
