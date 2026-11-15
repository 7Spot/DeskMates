import math
import unittest
from pathlib import Path

import config
from widget.clips import ACTIONS, POSTURE_PLANS, SLEEP_PLANS, TURN_180, TURN_90
from widget.states import BANNED_WORDS, GROUPS


class CatalogTests(unittest.TestCase):
    def test_every_posture_has_a_loop(self):
        for pid, plan in {**POSTURE_PLANS, **SLEEP_PLANS}.items():
            self.assertTrue(plan.loop, pid)

    def test_every_action_has_a_group(self):
        for a in ACTIONS:
            self.assertIn(a.group, GROUPS, a.id)

    def test_labels_are_actions_not_emotions(self):
        for a in ACTIONS:
            for word in BANNED_WORDS:
                self.assertNotIn(word, a.label.lower().split(), a.id)


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class ActionPoolTests(unittest.TestCase):
    def test_random_pool_is_fixed_and_the_action_card_has_twenty_eight(self):
        """随机动作是黑箱，池固定。动作卡片 28 个，按五组排；坐着的甩毛和站着的是同一段动画，只列一次。"""
        from widget.clips import ACTIONS, DEFAULT_ACTIONS, LIST_ACTIONS
        from widget.states import GROUPS
        self.assertEqual(set(DEFAULT_ACTIONS), {"stretch_front", "stretch_back", "shake", "scratch", "look_up", "look_around", "bow", "dig",
                                                "sit_shake", "yawn"})
        ids = [a.id for a in LIST_ACTIONS]
        self.assertEqual(len(ids), 28, "加过跳远、高跳又删了")
        self.assertNotIn("long_jump", ids); self.assertNotIn("high_jump", ids)
        self.assertEqual(ids[:5], ["look_up", "look_around", "bow_bark", "yawn", "side_lie"], "先是休息那组（伏地伸展的位置是犬吠）")
        for sid in ("walking", "active", "trotting", "running", "pacing", "backing_up", "turning", "hopping", "jumping", "fetching",
                    "carrying", "sniffing", "drinking", "eating", "creeping", "picking_up"):
            self.assertIn(sid, ids)
        self.assertNotIn("sit_shake", ids, "坐着的甩毛不重复列")
        self.assertTrue(all(a.group in GROUPS and a.group != "core" for a in ACTIONS))


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from widget import gltf
        cls.model = gltf.load(config.MODEL_PATH)

    def test_every_clip_in_the_plans_exists(self):
        for pid, plan in {**POSTURE_PLANS, **SLEEP_PLANS}.items():
            for c in plan.enter + plan.loop + plan.exit:
                self.assertIn(c, self.model.clips, (pid, c))
        for a in ACTIONS:
            for item in a.program:
                clip = item if isinstance(item, str) else (item[1] if item[0] == "loop" else None)
                if clip:
                    self.assertIn(clip, self.model.clips, (a.id, clip))
        for c in list(TURN_180.values()) + list(TURN_90.values()):
            self.assertIn(c, self.model.clips)

    def test_controller_runs_every_action_in_place(self):
        """每个动作都能做完；狗永远在窗口正中（走动类是原地踏步）。"""
        from widget.dogctl import DogController
        for a in ACTIONS:
            c = DogController(self.model, seed=1)
            c.set_play(True, home_yaw=210.0)
            c.do_action(a.id)
            for _ in range(12 * 60):
                c.update(1 / 60)
                c.frame()
            self.assertEqual((c.x, c.z), (0.0, 0.0), a.id)
            self.assertEqual(len(c.joint_matrices()), 57, a.id)

    def test_what_is_measured_once_lives_on_the_model(self):
        """量一次的东西记在模型上（gltf.Model.measured）：同一个模型的第二只控制器不重量，换上来的狗当场就能用；
        别的模型（另一个 Model 对象）各记各的。"""
        import dataclasses
        from unittest import mock
        from widget import dogctl, lift, locomotion, props, roam
        first = dogctl.DogController(self.model, seed=1)
        first.set_play(True, home_yaw=210.0)
        top = first.rest_top()
        first.lift.prepare()
        spot = first.props.spot("Eat_loop")
        leap = roam.leap_measures(first)
        span = first.lie_span()
        second = dogctl.DogController(self.model, seed=2)
        second.set_play(True, home_yaw=210.0)
        made = []
        real = dogctl.Player

        def counting(*args, **kw):
            made.append(args)
            return real(*args, **kw)
        with mock.patch.object(dogctl, "Player", counting), mock.patch.object(locomotion, "Player", counting), \
                mock.patch.object(lift, "Player", counting), mock.patch.object(props, "Player", counting):
            self.assertEqual(second.rest_top(), top)
            second.lift.prepare()
            self.assertEqual(second.props.spot("Eat_loop"), spot)
            self.assertIs(roam.leap_measures(second), leap)
            self.assertIs(second.lie_span(), span)
        self.assertEqual(made, [], "第二只不重量：片段最高点、拎起来的姿势、鼻子最低那一刻、跳法的数、趴着的身长都是第一只量好的")
        self.assertIs(second.lift.rig, first.lift.rig)
        self.assertIs(second._clip_tops, first._clip_tops)
        self.assertIs(second._feet, first._feet)
        other = dataclasses.replace(self.model, measured={})
        third = dogctl.DogController(other, seed=3)
        third.set_play(True, home_yaw=210.0)
        self.assertIsNot(third._clip_tops, first._clip_tops, "别的模型各记各的")
        self.assertEqual(third.rest_top(), top, "同一套骨架量出来一样")
        self.assertIn("clip_tops", other.measured)

    def test_leaving_lying_plays_its_exit_clip_before_the_next_posture(self):
        from widget.dogctl import DogController
        c = DogController(self.model, seed=1)
        c.set_rest_posture("lying")
        c.set_play(True, home_yaw=210.0)
        for _ in range(6 * 60):
            c.update(1 / 60)
        self.assertTrue(c.player.name.startswith("Lie_belly_loop"))
        c.set_rest_posture("standing")
        for _ in range(2):
            c.update(1 / 60)
        self.assertEqual(c.player.name, "Lie_belly_end", "趴着换站：先起身")
        self.assertTrue(c.transition)
        for _ in range(3 * 60):
            c.update(1 / 60)
        self.assertFalse(c.transition)
        self.assertIn(c.player.name, ("Idle_1", "Idle_2"))


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class PlayModeTests(unittest.TestCase):
    """互动模式的状态机：进入趴下、点哪都行（趴着起身、站着跳）、排队、坐下趴下、甩毛插播、头带身体、屏幕半区朝向。"""

    @classmethod
    def setUpClass(cls):
        from widget import gltf
        cls.model = gltf.load(config.MODEL_PATH)

    def _dog(self, seed=1):
        from widget.dogctl import DogController
        return DogController(self.model, seed=seed)

    @staticmethod
    def _run(c, seconds, target=None):
        for _ in range(int(seconds * 60)):
            if target is not None:
                head = c.head_position()
                c.set_look_target((head[0] + target[0], head[1] + target[1], head[2] + target[2]) if head else None)
            c.update(1 / 60)
            c.frame()

    def test_entering_play_settles_facing_home_then_lies_down(self):
        c = self._dog()
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "lying")
        self.assertTrue(c.player.name.startswith("Lie_belly_loop"))
        self.assertLess(abs((c.yaw - 330.0 + 180) % 360 - 180), 6.0, "趴下前先转到 home 朝向")
        self.assertEqual(c.y_offset, 0.0)

    def test_dynamic_dog_stays_standing_when_nobody_clicks(self):
        c = self._dog()
        c.set_dynamic(True)
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        seen = set()
        for _ in range(35 * 60):                    # 灵动交互只站着
            c.update(1 / 60)
            c.frame()
            seen.add(c.posture)
        self.assertEqual(seen, {"standing"}, "灵动交互里没人点也一直站着")

    def test_random_action_plays_when_standing_idle(self):
        c = self._dog()
        c.set_dynamic(True)
        c.set_play(True, home_yaw=330.0)
        self._run(c, 11.0)
        c.action_at = c.t                   # 不等随机间隔
        c.update(1 / 60)
        self.assertIsNotNone(c.action)
        self.assertEqual(c.action.posture, "standing")
        self.assertIn(c.player.name, c.action.program)

    def test_body_follows_head_towards_a_target_behind(self):
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)      # 朝右
        self._run(c, 8.0)
        self._run(c, 3.0, target=(0.0, 0.0, 0.45))
        c.action_at = float("inf")                    # 量的这 6 秒不要随机动作：正在播的也取消（池里有刨土这种好几秒的）
        c._interrupt_action()
        self._run(c, 6.0, target=(-2.0, 0.0, 0.45))   # 鼠标在狗左边远处：身体换成头朝左 210°
        self.assertLess(abs((c.yaw - 210.0 + 180) % 360 - 180), 3.0, f"身体应换到头朝左的朝向，现在 {c.yaw:.0f}")
        twists = []
        for _ in range(60):                           # 看一段时间的平均：待机动作自己也会摆头，只看一帧是碰运气
            self._run(c, 1 / 30, target=(-2.0, 0.0, 0.45))
            twists.append(abs(c.head_twist()))
        self.assertLess(sum(twists) / len(twists), 35.0, "转过去之后头不再大幅扭着")

    def test_body_flips_only_beyond_the_reach_and_turns_through_the_front(self):
        """固定两个朝向：鼠标在 BODY_FLIP_LENGTHS 个身长以内只转头；过了就用转身片段换到另一个四分之三朝向，中途经过正前方 270°；
        回来也要过另一边这么远。"""
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        c._interrupt_action()
        self.assertAlmostEqual(c.body_length, 0.75, delta=0.15, msg=f"身长按模型量：{c.body_length:.2f} 米")
        from widget.play import BODY_FLIP_LENGTHS
        reach = BODY_FLIP_LENGTHS * c.body_length
        near = reach - 0.1 + 0.3                              # 目标是相对头给的，头在中心右边约 0.3 米（朝右时）：离狗中心差 0.1 米才到门槛
        self._run(c, 4.0, target=(-near, 0.0, 0.45))
        self.assertTrue(c.facing_right(), "鼠标没过门槛：身体不动")
        self.assertGreater(abs(c.head_twist()), 10.0, "头跟着")
        far = reach + 0.2 + 0.3
        yaws = []
        for _ in range(4 * 60):
            head = c.head_position()
            c.set_look_target((head[0] - far, head[1], head[2] + 0.45))
            c.update(1 / 60)
            c.frame()
            yaws.append(c.yaw)
        self.assertFalse(c.facing_right(), "过了门槛：换成头朝左")
        self.assertLess(abs((c.yaw - 210.0 + 180) % 360 - 180), 3.0, f"停在 210°，现在 {c.yaw:.0f}")
        self.assertTrue(any(abs(y - 270.0) < 8.0 for y in yaws), "从镜头这边转过去，中途经过正前方")
        self.assertFalse(any(abs(y - 90.0) < 30.0 for y in yaws), "不从背后转")
        self._run(c, 4.0, target=(near, 0.0, 0.45))           # 头朝左时头在中心左边：往右 near 还在带里
        self.assertFalse(c.facing_right(), "回到带里不转回来")
        self._run(c, 4.0, target=(far, 0.0, 0.45))
        self.assertTrue(c.facing_right(), "过了右边的门槛才转回来")
        self.assertLess(abs((c.yaw - 330.0 + 180) % 360 - 180), 3.0)

    def test_loop_restart_does_not_jump_while_tracking(self):
        """趴着盯鼠标，循环片段每 3.3 秒重播一次：淡入起点如果带着跟随旋转，脖子的角度会被叠两次，头每次弹 4 厘米。"""
        names = [n.name for n in self.model.nodes]
        body = [i for i, n in enumerate(names)                          # 尾巴自己甩得快，不算
                if n not in ("Root_bone", "Cartoon_BorderCollie", "Arm_Collie") and not n.startswith("Tail")]
        c = self._dog()
        c.set_play(True, home_yaw=330.0)
        self._run(c, 10.0, target=(0.3, 0.1, 0.45))
        self.assertEqual(c.posture, "lying")
        prev, restarts, typical = None, [], []
        for _ in range(12 * 60):                      # 覆盖三四次重播
            head = c.head_position()
            c.set_look_target((head[0] + 0.3, head[1] + 0.1, head[2] + 0.45))
            c.update(1 / 60)
            pose = c.frame()
            pts = {j: (pose.world[j][12], pose.world[j][13], pose.world[j][14]) for j in body}
            if prev is not None:
                d = max(math.dist(pts[j], prev[j]) for j in body)
                typical.append(d)
                if c.player.time < 0.05:                  # 片段刚重播的那一帧
                    restarts.append(d)
            prev = pts
        median = sorted(typical)[len(typical) // 2]
        self.assertGreaterEqual(len(restarts), 3)
        self.assertLess(max(restarts), max(0.012, 2 * median), f"重播那一帧位移 {max(restarts) * 1000:.1f} mm，典型 {median * 1000:.1f} mm：不该弹")

    def test_head_keeps_tracking_the_target_through_a_body_turn(self):
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self._run(c, 3.0, target=(0.0, 0.0, 0.45))
        c.action_at = float("inf")
        rel = (-2.0, 0.0, 0.45)
        worst, turned, frames_in_turn = 0.0, False, 0
        for _ in range(6 * 60):
            head = c.head_position()
            target = (head[0] + rel[0], head[1] + rel[1], head[2] + rel[2])
            c.set_look_target(target)
            c.update(1 / 60)
            c.frame()
            if c.turn is not None:
                turned = True
                frames_in_turn += 1
                if frames_in_turn > 12:                                   # 淡入 0.2 秒之后
                    head_world = (c.head_twist() + c.yaw) % 360.0
                    aim = math.degrees(math.atan2(-rel[2], rel[0])) % 360.0   # 从头到目标的方向
                    needed = abs((aim - c.yaw + 180) % 360 - 180)            # 相对身体要扭多少
                    if needed <= 80.0:                                        # 扭得过去的范围内才算（头最多扭 90°）
                        worst = max(worst, abs((head_world - aim + 180) % 360 - 180))
        self.assertTrue(turned, "这个目标该触发一次转身片段")
        self.assertLess(worst, 25.0, f"转身期间头应该一直盯着目标，最大偏差 {worst:.0f}°")
        self._run(c, 1.0, target=rel)
        self.assertLess(c._head_free, 0.55, "转完头回到片段动作（有目标时压一半）")

    def test_auto_turn_off_keeps_the_body_still(self):
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self._run(c, 3.0, target=(0.0, 0.0, 0.45))
        c.set_auto_turn(False)
        c.set_rest_posture("sitting")                     # 关了之后再换姿势（换片段会重置一批状态，别把开关也重置了）
        self._run(c, 5.0, target=(0.0, 0.0, 0.45))
        c.set_rest_posture("standing")
        self._run(c, 5.0, target=(0.0, 0.0, 0.45))
        self.assertEqual(c.posture, "standing")
        self.assertFalse(c.auto_turn, "换姿势不能把自动转身重新打开")
        c.action_at = float("inf")
        yaw0 = c.yaw
        for _ in range(6 * 60):                           # 和上面转身测试同一个目标：正常会触发转身片段
            head = c.head_position()
            c.set_look_target((head[0] - 2.0, head[1], head[2] + 0.45))
            c.update(1 / 60)
            c.frame()
            self.assertIsNone(c.turn, "自动转身关着不播转身片段")
        self.assertLess(abs((c.yaw - yaw0 + 180) % 360 - 180), 1.0, "身体固定不动")
        self.assertGreater(abs(c.head_twist()), 10.0, "头还是跟着")

    def test_mouse_near_the_dog_does_not_turn_the_body(self):
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        yaw0 = c.yaw
        for sign in (1, -1, 1, -1):                      # 鼠标在狗身边晃
            self._run(c, 1.0, target=(sign * 0.2, 0.1, 0.45))
        self.assertLess(abs((c.yaw - yaw0 + 180) % 360 - 180), 2.0, "鼠标离狗太近，身体不转")
        self.assertGreater(abs(c.head_twist()), 10.0, "头还是跟着")

    def test_head_work_actions_ignore_the_mouse_but_others_keep_looking(self):
        """吃东西、低头嗅这类头有自己的戏的动作不跟鼠标，挠痒这类照样看着鼠标。"""
        from widget.clips import ACTIONS_BY_ID
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        c._interrupt_action()
        side = (-0.45, 0.1, 0.45)                                      # 鼠标在狗头左前方（离转身的线还有约 10 厘米，身体不转）：头明显扭过去
        self._run(c, 3.0, target=side)
        self.assertGreater(abs(c.head_twist()), 10.0, "平时跟着鼠标")
        self.assertFalse(ACTIONS_BY_ID["eating"].gaze)
        self.assertTrue(ACTIONS_BY_ID["scratch"].gaze and ACTIONS_BY_ID["shake"].gaze and ACTIONS_BY_ID["yawn"].gaze, "挠痒 / 甩毛 / 哈欠照样看")
        c.do_action("eating")
        self._run(c, 2.5, target=side)
        self.assertEqual(c.player.name, "Eat_loop")
        self.assertLess(abs(c.head_twist()), 6.0, f"吃的时候头不跟鼠标，现在扭了 {c.head_twist():.0f}°")
        self.assertEqual(c.player.base_blend, {}, "片段的头部动作也不再被压")
        self._run(c, 8.0, target=side)
        self.assertIsNone(c.action)
        self.assertGreater(abs(c.head_twist()), 10.0, "做完看回鼠标")
        c.do_action("scratch")
        self._run(c, 2.0, target=side)
        self.assertEqual(c.player.name, "Scratching")
        self.assertGreater(abs(c.head_twist()), 10.0, "挠痒照样盯着你")

    def test_sleep_is_a_posture_built_on_lying_and_wakes_on_request(self):
        """第四个姿势"睡"。站着点睡 = 趴下 → 入睡 → 睡着循环；睡着不做随机动作、不看鼠标；醒来 = 醒来片段 → 趴着（不再趴一次），放完才算醒。"""
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        c._interrupt_action()
        c.sleep_styles = ("belly",)
        self.assertEqual(c.sleep_state(), "awake")
        c.set_rest_posture("sleeping")
        self.assertEqual(c.sleep_state(), "falling")
        seq = []
        self.assertIsNotNone(self._until(c, lambda: (seq.append(c.player.name), c.sleep_state() == "asleep")[1], 10.0), "睡着了")
        names = [n for i, n in enumerate(seq) if i == 0 or n != seq[i - 1]]
        self.assertLess(names.index("Lie_belly_start"), names.index("Lie_belly_sleep_start"), f"先趴下再入睡：{names}")
        self.assertEqual(names[-1], "Lie_belly_sleep")
        self.assertNotIn("Lie_belly_end", names, "趴下之后不起身")
        self.assertEqual(c.posture, "sleeping")
        c.action_at = c.t
        self._run(c, 20.0, target=(-1.0, 0.1, 0.45))
        self.assertIsNone(c.action, "睡着不做随机动作")
        self.assertEqual(c.player.name, "Lie_belly_sleep")
        self.assertTrue(c.gaze.idle, "睡着不看鼠标")
        c.set_rest_posture("lying")
        self.assertEqual(c.sleep_state(), "waking")
        seq = []
        self.assertIsNotNone(self._until(c, lambda: (seq.append(c.player.name), c.sleep_state() == "awake")[1], 5.0), "醒来动画放完才算醒")
        names = [n for i, n in enumerate(seq) if i == 0 or n != seq[i - 1]]
        self.assertLess(names.index("Lie_belly_sleep_end"), names.index("Lie_belly_loop_1"), f"先播醒来再趴着：{names}")
        self.assertNotIn("Lie_belly_start", names, "醒来直接是趴着，不再趴一次")
        self.assertEqual(c.posture, "lying")
        self._run(c, 0.5)
        self.assertTrue(c.player.name.startswith("Lie_belly_loop"))

    def test_side_sleep_lies_on_the_side_and_wakes_up_standing(self):
        """侧睡（随机一种睡法）：侧躺下去 → 入睡 → 睡着循环；醒来片段末尾是侧躺，接着 Lie_end 起身，所以醒来后站着。"""
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        c._interrupt_action()
        c.sleep_styles = ("side",)
        c.set_rest_posture("sleeping")
        seq = []
        self.assertIsNotNone(self._until(c, lambda: (seq.append(c.player.name), c.sleep_state() == "asleep")[1], 10.0), "睡着了")
        names = [n for i, n in enumerate(seq) if i == 0 or n != seq[i - 1]]
        self.assertLess(names.index("Lie_start"), names.index("Lie_Sleep_start"), f"先侧躺再入睡：{names}")
        self.assertEqual(names[-1], "Lie_Sleep_loop")
        self.assertNotIn("Lie_belly_start", names, "侧睡不经过趴")
        self.assertEqual((c.posture, c.sleep_style), ("sleeping", "side"))
        c.set_rest_posture("standing")                        # 窗口的「醒来」对侧睡就是回站着
        seq = []
        self.assertIsNotNone(self._until(c, lambda: (seq.append(c.player.name), c.sleep_state() == "awake")[1], 6.0))
        names = [n for i, n in enumerate(seq) if i == 0 or n != seq[i - 1]]
        self.assertLess(names.index("Lie_Sleep_end"), names.index("Lie_end"), f"先醒来再起身：{names}")
        self.assertEqual(c.posture, "standing")

    def test_sleep_styles_alternate(self):
        """睡姿轮着来（纯随机会连着出同一种）：第一次随机，之后每次「睡」用上次没用的那种。"""
        c = self._dog()
        self.assertIsNone(c.sleep_style, "还没睡过")
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        styles = []
        for _ in range(4):
            c.set_rest_posture("sleeping")
            self.assertIsNotNone(self._until(c, lambda: c.sleep_state() == "asleep", 12.0))
            styles.append(c.sleep_style)
            c.set_rest_posture("standing")
            self.assertIsNotNone(self._until(c, lambda: c.sleep_state() == "awake" and c.posture == "standing" and not c.transition, 8.0))
        self.assertEqual(set(styles[:2]), {"belly", "side"}, "连点两次两种都见到")
        self.assertTrue(all(a != b for a, b in zip(styles, styles[1:])), f"轮着来：{styles}")

    def test_turning_on_dynamic_while_asleep_wakes_then_stands(self):
        c = self._dog()
        c.sleep_styles = ("belly",)
        c.set_rest_posture("sleeping")
        c.set_play(True, home_yaw=330.0)
        self.assertIsNotNone(self._until(c, lambda: c.sleep_state() == "asleep", 12.0), "进互动模式按记着的姿势直接睡")
        c.set_dynamic(True)
        seq = []
        self.assertIsNotNone(self._until(c, lambda: (seq.append(c.player.name), c.posture == "standing" and not c.transition and not c.steps)[1], 8.0))
        names = [n for i, n in enumerate(seq) if i == 0 or n != seq[i - 1]]
        self.assertLess(names.index("Lie_belly_sleep_end"), names.index("Lie_belly_end"), f"先醒来再起身：{names}")
        self.assertEqual(c.sleep_state(), "awake")

    def test_required_height_grows_for_a_jump_and_whole_clip_jumps_never_sink(self):
        from widget.clips import JUMPS
        for name in ("up", "hop"):
            c = self._dog()
            c.set_dynamic(True)
            c.set_play(True, home_yaw=330.0)
            self._run(c, 11.0)
            c.action_at = float("inf")
            c._interrupt_action()
            self._run(c, 0.5)
            standing = c.required
            self.assertLess(standing, 0.9)
            j = next(j for j in JUMPS if j.name == name)
            c._start_jump(jump=j)
            peak, lowest, highest_required = 0.0, 1.0, 0.0
            while c.jump is not None:
                c.update(1 / 60)
                lift = c.frame().lift
                peak, lowest = max(peak, lift), min(lowest, lift)
                highest_required = max(highest_required, c.required)
            self.assertGreaterEqual(lowest, -1e-6, f"{name}：脚不许钻到地下")
            self.assertGreater(peak, 0.15, f"{name}：要跳得起来")
            self.assertGreater(highest_required, standing + 0.3, f"{name}：跳的时候窗口要长高")
            self._run(c, 0.5)
            self.assertLess(c.required, 0.9, "落地后要求的高度回落")

    def test_pitch_follows_the_arc_on_a_flat_jump(self):
        from widget.clips import JUMPS
        c = self._dog()
        c.set_dynamic(True)
        c.set_play(True, home_yaw=330.0)
        self._run(c, 11.0)
        j = next(j for j in JUMPS if j.name == "medium")
        c._start_jump(jump=j)
        early, late = [], []
        while c.jump is not None:
            c.update(1 / 60)
            c.frame()
            if c.jump and c.jump.phase == "air":
                (early if c.jump.u < 0.4 else late).append(c.pitch)
        self.assertGreater(max(early), 8.0, "起跳抬头")
        self.assertLess(min(late), -8.0, "下落低头")
        self.assertEqual(c.pitch, 0.0, "落地后回平")

    def test_rare_clips_keep_their_gaps(self):
        from widget.clips import RARE
        c = self._dog()
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        def starts(seconds, clip):
            out, last = [], None
            for _ in range(int(seconds * 60)):
                c.update(1 / 60)
                c.frame()
                if c.player.name == clip and last != clip:
                    out.append(c.t)
                last = c.player.name
            return out
        yawns = starts(300.0, "Lie_belly_loop_2")                     # 趴着 300 秒
        self.assertEqual(c.posture, "lying")
        self.assertTrue(3 <= len(yawns) <= 7, f"平均 60 秒一次哈欠，300 秒里 {len(yawns)} 次")
        self.assertTrue(all(b - a >= RARE["Lie_belly_loop_2"][0] - 1e-6 for a, b in zip(yawns, yawns[1:])), "最短 40 秒")
        c.set_rest_posture("standing")          # 站着，灵动交互关着不会坐下
        self._run(c, 3.0)
        shakes = starts(400.0, "Idle_7")
        self.assertTrue(4 <= len(shakes) <= 12, f"平均 50 秒一次甩毛，400 秒里 {len(shakes)} 次")
        self.assertTrue(all(b - a >= RARE["Idle_7"][0] - 1e-6 for a, b in zip(shakes, shakes[1:])), "最短 30 秒")

    def test_dynamic_off_posture_is_selectable(self):
        c = self._dog()
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "lying")
        c.set_rest_posture("sitting")
        self._run(c, 5.0)
        self.assertEqual(c.posture, "sitting")
        c.set_rest_posture("standing")
        self._run(c, 5.0)
        self.assertEqual(c.posture, "standing")
        self._run(c, 40.0)
        self.assertEqual(c.posture, "standing", "灵动交互关着没人点也不坐下")
        c.set_dynamic(True)
        self._run(c, 5.0)
        self.assertEqual(c.posture, "standing", "打开灵动交互就站起来")
        c.set_rest_posture("sitting")
        self._run(c, 5.0)
        self.assertEqual(c.posture, "standing", "灵动交互里只站着：选的姿势先记下，不过去")
        c.set_dynamic(False)
        self._run(c, 5.0)
        self.assertEqual(c.posture, "sitting", "关掉灵动交互回到选的姿势")

    def test_settle_into_puts_a_new_dog_straight_into_the_posture(self):
        """换模型换上来的新狗（dogctl.settle_into）：看不见的时候就已经是选的姿势——不先站着再趴下、不和站着的那段交叉淡入；睡就直接睡着。"""
        for posture, clips in (("lying", ("Lie_belly_loop_1", "Lie_belly_loop_2")), ("sitting", ("Sitting_loop_1", "Sitting_loop_2")),
                               ("standing", ("Idle_1", "Idle_2"))):
            c = self._dog()
            c.set_rest_posture(posture)
            c.set_play(True, home_yaw=330.0)
            c.snap_home(330.0)
            c.settle_into(posture)
            c.update(0.0)
            self.assertEqual((c.posture, c.transition, c.steps, c.queue), (posture, False, [], []), posture)
            self.assertIn(c.player.name, clips, posture)
            self.assertIsNone(c.player.prev, f"{posture}：不从站着淡过去")
            self._run(c, 3.0)
            self.assertEqual((c.posture, c.phase), (posture, "idle"), f"{posture}：一直待着，不起身再坐下")
        c = self._dog()
        c.set_rest_posture("sleeping")
        c.set_play(True, home_yaw=330.0)
        c.settle_into("sleeping")
        c.update(0.0)
        self.assertEqual((c.posture, c.sleep_state(), c.transition), ("sleeping", "asleep", False))
        self.assertIn(c.player.name, (*SLEEP_PLANS["belly"].loop, *SLEEP_PLANS["side"].loop))

    def test_do_action_switches_posture_does_it_once_and_comes_back(self):
        """动作列表：趴着点前伸 → 起身、前伸、趴回去；站着点打哈欠 → 趴下、哈欠、站起来；姿势行选的不变。"""
        c = self._dog()
        c.set_rest_posture("lying")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "lying")
        c.do_action("stretch_front")
        seen, back = False, False
        for _ in range(15 * 60):
            c.update(1 / 60)
            c.frame()
            if c.player.name == "Idle_3":
                seen = True
                self.assertEqual(c.posture, "standing", "前伸是站着做的")
            if seen and c.posture == "lying" and c.player.name.startswith("Lie_belly_loop"):
                back = True
                break
        self.assertTrue(seen and back, "趴着点前伸：起身 → 前伸 → 趴回去")
        self.assertEqual(c.rest_posture, "lying", "姿势行选的不变")
        c.set_rest_posture("standing")
        self._run(c, 5.0)
        c.do_action("yawn")
        seen, back = False, False
        for _ in range(15 * 60):
            c.update(1 / 60)
            c.frame()
            if c.player.name == "Lie_belly_loop_2":
                seen = True
                self.assertEqual(c.posture, "lying", "打哈欠是趴着做的")
            if seen and c.posture == "standing" and c.player.name.startswith("Idle"):
                back = True
                break
        self.assertTrue(seen and back, "站着点打哈欠：趴下 → 哈欠 → 站起来")

    def _standing(self):
        """站着待机、随机动作停掉，专门试动作卡片的 program。"""
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.action_at = float("inf")
        c._interrupt_action()
        self._run(c, 0.5)
        return c

    def _do(self, c, action_id, seconds):
        """做一个动作直到做完，返回片段名序列（相邻去重）和最高离地。"""
        c.do_action(action_id)
        seq, peak = [], 0.0
        for _ in range(int(seconds * 60)):
            c.update(1 / 60)
            peak = max(peak, c.frame().lift)
            if not seq or seq[-1] != c.player.name:
                seq.append(c.player.name)
            if c.action is None and c.jump is None and c.turn is None and not c.steps:
                break
        self.assertIsNone(c.action, f"{action_id} 应在 {seconds} 秒内做完")
        return seq, peak

    def test_timed_loop_action_plays_start_loop_end_and_comes_back(self):
        """吃：EatDrink_start → Eat_loop 循环约 5 秒 → EatDrink_end → 回站着待机。"""
        c = self._standing()
        c.do_action("eating")
        loop_frames, seq = 0, []
        for _ in range(12 * 60):
            c.update(1 / 60)
            c.frame()
            loop_frames += c.player.name == "Eat_loop"
            if not seq or seq[-1] != c.player.name:
                seq.append(c.player.name)
            if c.action is None:
                break
        self.assertIsNone(c.action)
        i = seq.index("EatDrink_start")
        self.assertEqual(seq[i:i + 3], ["EatDrink_start", "Eat_loop", "EatDrink_end"])
        self.assertAlmostEqual(loop_frames / 60, 5.0, delta=0.6, msg="循环约 5 秒")
        self._run(c, 0.5)
        self.assertTrue(c.player.name.startswith("Idle"), "做完回站着待机")

    def test_turning_action_turns_away_and_back(self):
        c = self._standing()
        yaw0 = c.yaw
        c.do_action("turning")
        away, clips = False, set()
        for _ in range(10 * 60):
            c.update(1 / 60)
            c.frame()
            clips.add(c.player.name)
            away = away or abs((c.yaw - yaw0 + 180) % 360 - 180) > 150
            if c.action is None:
                break
        self.assertIsNone(c.action)
        self.assertTrue(away, "转过去了")
        self.assertLess(abs((c.yaw - yaw0 + 180) % 360 - 180), 6.0, "又转回来了")
        self.assertTrue(clips & {"Turn_L180_IP", "Turn_R180_IP"}, "用的是转身片段")

    def test_jump_action_jumps_once_then_finishes(self):
        c = self._standing()
        seq, peak = self._do(c, "hopping", 6.0)
        self.assertIsNone(c.jump)
        self.assertGreater(peak, 0.1, "跳起来了")
        self.assertEqual(c.last_jump, "hop")
        self.assertIn("Jump_Place_IP", seq)

    def test_fetching_action_runs_picks_turns_and_puts_down(self):
        c = self._standing()
        yaw0 = c.yaw
        seq, _ = self._do(c, "fetching", 20.0)
        self.assertEqual([n for n in seq if n in ("Run_F_IP", "Pick_up", "Put_down")], ["Run_F_IP", "Pick_up", "Run_F_IP", "Put_down"], "跑去捡、跑回放下")
        self.assertEqual(sum(n.startswith("Turn_") for n in seq), 2, "转过去、转回来")
        self.assertLess(abs((c.yaw - yaw0 + 180) % 360 - 180), 6.0, "最后朝向不变")

    def test_sniffing_lowers_the_head_and_restores_it(self):
        c = self._standing()
        c.do_action("sniffing")
        targets, applied = [], []
        for _ in range(8 * 60):
            c.update(1 / 60)
            c.frame()
            if c.player.name == "Walk_F_IP":
                targets.append(c.head_pitch_target)
                applied.append(c.head_pitch)
            if c.action is None:
                break
        self.assertIsNone(c.action)
        self.assertTrue(targets and all(p == -30.0 for p in targets), "嗅的时候低头 30°")
        self.assertLess(min(applied), -29.0, "头真的低下去了（平滑过去，不是瞬间）")
        self.assertEqual(c.head_pitch_target, 0.0, "做完抬回来")
        self._run(c, 0.5)
        self.assertLess(abs(c.head_pitch), 1.0, "0.5 秒内抬回到位")

    def test_do_action_cuts_a_jump_and_the_dog_drops_back_in_0_3_s(self):
        """一刀切：半空被表盘打断也切，高度 0.3 秒落回地面，新动作立刻开始。"""
        c = self._dog()
        c.set_dynamic(True)
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c._start_jump()
        self.assertIsNotNone(self._until(c, lambda: c.jump is not None and c.y_offset > 0.05, 2.0), "在空中（起跳片段长短看跳法）")
        self.assertIsNotNone(c.jump)
        self.assertGreater(c.y_offset, 0.05, "在空中")
        c.do_action("shake")
        self.assertIsNone(c.jump, "半空也切")
        heights, shook_at = [], None
        for i in range(60):
            c.update(1 / 60)
            c.frame()
            heights.append(c.y_offset)
            if shook_at is None and c.player.name == "Idle_7":
                shook_at = i
        self.assertIsNotNone(shook_at)
        self.assertLessEqual(shook_at, 2, "甩毛立刻开始")
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(heights, heights[1:])), "高度单调落回")
        self.assertEqual(heights[20], 0.0, "0.3 秒内落到地面")

    def test_via_standing_action_from_sitting_returns_to_sitting(self):
        c = self._dog()
        c.set_rest_posture("sitting")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "sitting")
        c._rare_next["Idle_7"] = 0.0                  # 坐着的池只有甩毛（稀有）：不等它的间隔
        seen_shake, back = False, False
        for _ in range(15 * 60):
            c.update(1 / 60)
            c.frame()
            if c.player.name == "Idle_7":
                seen_shake = True
            if seen_shake and c.posture == "sitting" and c.player.name.startswith("Sitting_loop"):
                back = True
                break
        self.assertTrue(seen_shake, "坐着先站起来甩毛")
        self.assertTrue(back, "甩完坐回去")

    def test_spin_action_turns_a_full_circle_and_actions_outside_the_pool_never_play(self):
        c = self._dog()
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        c.do_action("spin")                           # 转圈不在随机池里，只能从动作列表点
        c.update(1 / 60)
        self.assertEqual(c.action.id, "spin")
        total = 0.0
        prev = c.yaw
        while c.action is not None:
            c.update(1 / 60)
            c.frame()
            total += (c.yaw - prev + 180) % 360 - 180
            prev = c.yaw
        self.assertAlmostEqual(total, 360.0, delta=15.0)
        played = set()
        for _ in range(60 * 60):
            c.update(1 / 60)
            played.add(c.player.name)
        self.assertNotIn("Bark", played, "不在池里的动作狗不会自己做")
        self.assertNotIn("Turn_L_IP", played, "转圈也不会自己来")

    def _played_until(self, c, pred, seconds):
        """跑到条件成立为止，返回播过的片段（连着重复的只记一次）；超时 fail。"""
        seq = []
        self.assertIsNotNone(self._until(c, lambda: (seq.append(c.player.name), pred())[1], seconds), f"超时：{seq[-1:]}")
        return [n for i, n in enumerate(seq) if i == 0 or n != seq[i - 1]]

    @staticmethod
    def _off(yaw, target):
        return abs((yaw - target + 180) % 360 - 180)

    def test_crossing_the_midline_gets_a_lying_dog_up_to_turn_and_lie_back(self):
        """换了半边一律转（"不为转向起立"只管开关来回切和鼠标跟随）：趴着的起身、转、趴回去；没换边什么都不做。"""
        c = self._dog()
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "lying")
        c.action_at = float("inf")
        c.set_home_yaw(210.0)                                   # 拖过中线
        names = self._played_until(c, lambda: not c.steps and not c.transition and c.turn is None and c.posture == "lying", 10.0)
        turn = next(n for n in names if n.startswith("Turn_"))
        self.assertLess(names.index("Lie_belly_end"), names.index(turn), f"先起身再转：{names}")
        self.assertLess(names.index(turn), names.index("Lie_belly_start"), f"转完趴回去：{names}")
        self.assertLess(self._off(c.yaw, 210.0), 6.0)
        c.set_home_yaw(210.0)                                   # 拖了一下没过中线
        self.assertEqual(c.steps, [], "没换边：不起身")

    def test_crossing_while_sitting_or_asleep_turns_and_returns_to_the_same_posture(self):
        """坐着的起身、转、坐回去；睡着的醒来、起身、转，再用同一种睡法睡回去（不轮换），睡着期间姿势条只有「醒来」。"""
        c = self._dog()
        c.set_rest_posture("sitting")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "sitting")
        c.action_at = float("inf")
        c.set_home_yaw(210.0)
        names = self._played_until(c, lambda: not c.steps and not c.transition and c.turn is None and c.posture == "sitting", 10.0)
        turn = next(n for n in names if n.startswith("Turn_"))
        self.assertLess(names.index("Sitting_end"), names.index(turn), f"先起身再转：{names}")
        self.assertLess(names.index(turn), names.index("Sitting_start"), f"转完坐回去：{names}")
        self.assertLess(self._off(c.yaw, 210.0), 6.0)
        for _ in range(2):                                      # 两种睡法各一次：第一次随机，之后轮着来
            c.set_rest_posture("sleeping")
            self._played_until(c, lambda: c.sleep_state() == "asleep", 12.0)
            style, home = c.sleep_style, (330.0 if self._off(c.yaw, 210.0) < 6.0 else 210.0)
            c.set_home_yaw(home)
            self.assertEqual(c.sleep_state(), "waking", "换边转身期间只有「醒来」")
            names = self._played_until(c, lambda: c.sleep_state() == "asleep", 15.0)
            self.assertTrue(any(n.startswith("Turn_") for n in names), f"起来转了：{names}")
            self.assertEqual(c.sleep_style, style, "用同一种睡法睡回去")
            self.assertLess(self._off(c.yaw, home), 6.0)
            c.set_rest_posture("standing")
            self._played_until(c, lambda: c.posture == "standing" and not c.transition and not c.steps, 8.0)

    def test_crossing_turns_the_body_with_follow_on_and_turning_off_turn_with_mouse_brings_it_home(self):
        """鼠标跟随开、随鼠标转身关：站起来也换边就转；随鼠标转身开着时身子跟鼠标，关掉就转回 home。"""
        c = self._dog()
        c.set_auto_turn(False)
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 6.0, target=(-0.3, 0.1, 0.45))
        c.action_at = float("inf")
        c.set_home_yaw(210.0)
        self._run(c, 4.0, target=(-0.3, 0.1, 0.45))
        self.assertLess(self._off(c.yaw, 210.0), 6.0, "跟随开、随鼠标转身关：换边照样转")
        c.set_auto_turn(True)
        self._run(c, 4.0, target=(2.0, 0.1, 0.45))
        self.assertLess(self._off(c.yaw, 330.0), 6.0, "随鼠标转身：鼠标远远在右边，身子转过去")
        c.set_auto_turn(False)
        self._run(c, 4.0, target=(2.0, 0.1, 0.45))
        self.assertLess(self._off(c.yaw, 210.0), 6.0, "关掉随鼠标转身：转回 home 那边")

    def _until(self, c, pred, seconds):
        """跑到条件成立为止，返回用了几秒；超时返回 None。"""
        for i in range(int(seconds * 60)):
            if pred():
                return i / 60
            c.update(1 / 60)
            c.frame()
        return None

    def test_any_action_is_cut_at_once_and_the_heading_slides_back(self):
        """一刀切：表盘点的转圈转到一半再点别的，转圈立刻停、新动作立刻开始，朝向 0.3 秒滑回转圈前的角度，不播转身片段。
        随机动作同样直接切。"""
        c = self._standing()
        yaw0 = c.yaw
        c.do_action("spin")
        self._run(c, 0.6)
        self.assertEqual(c.action.id, "spin")
        self.assertGreater(abs((c.yaw - yaw0 + 180) % 360 - 180), 60.0, "转到一半")
        c.do_action("bark")
        c.update(1 / 60)
        c.frame()
        self.assertEqual(c.action.id, "bark", "立刻换成新动作")
        self.assertIsNone(c.run.spin if c.run is not None else None)
        played = set()
        for _ in range(24):
            c.update(1 / 60)
            c.frame()
            played.add(c.player.name)
        self.assertLess(abs((c.yaw - yaw0 + 180) % 360 - 180), 3.0, f"0.4 秒内朝向滑回 {yaw0:.0f}，现在 {c.yaw:.0f}")
        self.assertFalse({n for n in played if n.startswith("Turn_")}, "滑回不用转身片段")
        self.assertIn("Bark", played)
        while c.action is not None:
            c.update(1 / 60)
        c.action_at = c.t                             # 随机动作来了
        c.update(1 / 60)
        self.assertIsNotNone(c.action)
        self.assertTrue(c.action.default)
        c.do_action("bark")
        c.update(1 / 60)
        self.assertEqual(c.action.id, "bark", "随机动作直接打断")

    def test_a_loop_action_is_cut_at_once_and_the_progress_bar_moves_to_the_new_one(self):
        c = self._standing()
        c.do_action("eating")
        self._run(c, 2.0)
        self.assertEqual(c.player.name, "Eat_loop")
        c.do_action("bark")
        took = self._until(c, lambda: c.player.name == "Bark", 1.0)
        self.assertIsNotNone(took)
        self.assertLessEqual(took, 0.05, "吃到一半点叫：不播 EatDrink_end，立刻叫")
        aid, frac = c.manual_progress()
        self.assertEqual(aid, "bark", "进度条马上换到新的那根")
        self.assertGreater(frac, 0.9)

    def test_side_lie_is_a_standing_action_that_cuts_straight_to_the_next(self):
        c = self._standing()
        c.do_action("side_lie")
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Lie_loop_1", 6.0), "站着点侧躺：直接 Lie_start 侧躺下去")
        self.assertEqual(c.posture, "standing", "侧躺算站姿动作")
        self._run(c, 1.0)
        c.do_action("walking")
        played = []
        took = self._until(c, lambda: (played.append(c.player.name), c.player.name == "Walk_F_IP")[1], 1.0)
        self.assertIsNotNone(took)
        self.assertLessEqual(took, 0.05, "侧躺着点走路：直接切到走，不先趴一次再起来")
        self.assertFalse({n for n in played if n.startswith("Lie_belly")}, f"中间没有趴下 / 起身的片段：{played}")

    def test_interrupting_mid_turn_slides_the_heading_back_without_a_turn_clip(self):
        c = self._standing()
        yaw0 = c.yaw
        c.do_action("turning")
        self.assertIsNotNone(self._until(c, lambda: c.turn is not None and abs((c.yaw - yaw0 + 180) % 360 - 180) > 40.0, 3.0), "转到一半")
        c.do_action("stretch_front")
        self.assertIsNone(c.turn, "转身片段也切")
        played = set()
        for _ in range(24):
            c.update(1 / 60)
            c.frame()
            played.add(c.player.name)
        self.assertLess(abs((c.yaw - yaw0 + 180) % 360 - 180), 3.0, "0.4 秒内滑回原来的朝向")
        self.assertIn("Idle_3", played, "前伸立刻开始")
        self.assertFalse({n for n in played if n.startswith("Turn_")})

    def test_same_action_again_restarts_without_replaying_the_loop(self):
        c = self._standing()
        c.do_action("walking")
        self._run(c, 2.0)
        self.assertEqual(c.player.name, "Walk_F_IP")
        c.do_action("walking")
        c.update(1 / 60)
        self.assertEqual(c.player.name, "Walk_F_IP")
        self.assertIsNone(c.player.prev, "片段接着播，没有重新淡入（没重播）")
        aid, frac = c.manual_progress()
        self.assertEqual(aid, "walking")
        self.assertGreater(frac, 0.95, "进度条重置")
        t0 = c.manual.t0
        self.assertIsNotNone(self._until(c, lambda: c.action is None, 7.0))
        self.assertGreater(c.t - t0, 4.5, "从再点那一刻起又走了整段 5 秒")

    def test_posture_change_cuts_a_random_action_and_a_cut_during_a_transition_goes_straight_on(self):
        from widget.clips import ACTIONS_BY_ID
        c = self._standing()
        c._start_action(ACTIONS_BY_ID["dig"])
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Digging_loop", 3.0))
        c.set_rest_posture("sitting")
        took = self._until(c, lambda: c.player.name == "Sitting_start", 1.0)
        self.assertIsNotNone(took)
        self.assertLessEqual(took, 0.05, "刨到一半换姿势：不播 Digging_end，直接开始坐下")
        self.assertIsNotNone(self._until(c, lambda: c.posture == "sitting" and c.player.name.startswith("Sitting_loop"), 4.0))
        c.set_rest_posture("standing")
        self._run(c, 3.0)
        c.do_action("yawn")                                   # 站着点打哈欠：趴下的过渡片段播到一半再点叫
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Lie_belly_start" and c.player.progress > 0.3, 3.0))
        c.do_action("bark")
        self.assertFalse(c.transition, "换姿势的过渡片段也切")
        played = []
        took = self._until(c, lambda: (played.append(c.player.name), c.player.name == "Bark")[1], 2.5)
        self.assertIsNotNone(took, f"趴到一半点叫：起身就叫，{played}")
        self.assertNotIn("Lie_belly_loop_2", played, "没去打哈欠")
        self.assertEqual(c.posture, "standing")

    def test_manual_progress_runs_from_full_to_empty_over_the_whole_sequence(self):
        """表盘的进度条：点一根指针后 manual_progress 从 1 往 0 走，整段（换姿势过去 + 动作 + 换回来）做完变 None。"""
        c = self._standing()
        self.assertIsNone(c.manual_progress())
        c.do_action("yawn")                                   # 站着点打哈欠：趴下 → 哈欠 → 站起来
        aid, frac = c.manual_progress()
        self.assertEqual(aid, "yawn")
        self.assertGreater(frac, 0.95)
        estimated = c.manual.total
        self._run(c, 1.0)
        aid, frac2 = c.manual_progress()
        self.assertLess(frac2, frac, "在走")
        seconds = 0.0
        while c.manual_progress() is not None and seconds < 15.0:
            c.update(1 / 60)
            c.frame()
            seconds += 1 / 60
        self.assertIsNone(c.manual_progress(), "整段做完就没了")
        self.assertEqual(c.posture, "standing")
        self.assertGreater(seconds, 3.0, "趴下 + 哈欠 + 站起来总得几秒")
        self.assertLess(abs(seconds - estimated), 2.5, f"估的总时长 {estimated:.1f} 和实际 {seconds:.1f} 差不多")

    def test_posture_change_is_quick(self):
        c = self._dog()
        c.set_rest_posture("sitting")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 8.0)
        self.assertEqual(c.posture, "sitting")
        c.set_rest_posture("lying")
        frames = 0
        while not (c.posture == "lying" and c.player.name.startswith("Lie_belly_loop")) and frames < 5 * 60:
            c.update(1 / 60)
            c.frame()
            frames += 1
        self.assertLess(frames / 60, 1.7, f"坐→趴 {frames / 60:.2f} 秒")



@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class SittingLookTests(unittest.TestCase):
    """萨摩耶坐下以后头左右晃——Sitting_loop_2 里头自己左右张望，又叠着看鼠标。头在看东西时坐着只播 Sitting_loop_1。"""

    @classmethod
    def setUpClass(cls):
        from widget import gltf
        cls.model = gltf.load(config.MODEL_PATH)

    def seen_while_sitting(self, target, seconds=120.0):
        from widget.dogctl import DogController
        dog = DogController(self.model, seed=7)
        dog.set_play(True, home_yaw=210.0)
        dog.set_rest_posture("sitting")
        names = set()
        for _ in range(int(seconds * 60)):
            dog.set_look_target(target)
            dog.update(1 / 60)
            if dog.posture == "sitting" and not dog.transition:
                names.add(dog.player.name)
        return names

    def test_looking_at_something_it_only_plays_the_still_sitting_loop(self):
        from widget.clips import LOOKS_AROUND
        self.assertEqual(LOOKS_AROUND, frozenset({"Sitting_loop_2"}))
        looking = self.seen_while_sitting((0.6, 0.4, 0.8))
        self.assertIn("Sitting_loop_1", looking)
        self.assertNotIn("Sitting_loop_2", looking, "头在看东西：不播自己张望的那段")
        free = self.seen_while_sitting(None)
        self.assertTrue({"Sitting_loop_1", "Sitting_loop_2"} <= free, "不看东西照旧两段轮着")

    def test_a_target_showing_up_mid_glance_cuts_over(self):
        from widget.dogctl import DogController
        dog = DogController(self.model, seed=7)
        dog.set_play(True, home_yaw=210.0)
        dog.set_rest_posture("sitting")
        for _ in range(int(200 * 60)):
            dog.update(1 / 60)
            if dog.player.name == "Sitting_loop_2" and not dog.transition:
                break
        self.assertEqual(dog.player.name, "Sitting_loop_2", "等到它自己张望")
        dog.set_look_target((0.6, 0.4, 0.8))
        self.assertEqual(dog.player.name, "Sitting_loop_1", "头要看东西：当场淡到不张望的那段")
