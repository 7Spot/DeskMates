import math
import unittest

from widget.anim import axis_angle, qmul
from widget.gaze import EYE_LIMIT, HEAD_YAW, NECK_YAW, Gaze, Joint, residual, rotate, world_up_in_local
from widget.gltf import IDENTITY


def mat_from_quat(q, pos=(0.0, 0.0, 0.0)):
    """四元数 → 列主序世界矩阵（局部轴 = 旋转后的 X/Y/Z）。"""
    X, Y, Z = (rotate(q, e) for e in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
    return (X[0], X[1], X[2], 0.0, Y[0], Y[1], Y[2], 0.0, Z[0], Z[1], Z[2], 0.0, pos[0], pos[1], pos[2], 1.0)


class ResidualTests(unittest.TestCase):
    def test_straight_ahead_is_zero(self):
        self.assertEqual(residual(IDENTITY, (0.0, 2.0, 0.0)), (0.0, 0.0))

    def test_residual_angles_rotate_forward_onto_the_target(self):
        """量出来的 (yaw, pitch) 做成四元数去转 +Y，应该正好指向目标。这保证了残差和叠加旋转的符号一致。"""
        for target in ((-1.0, 1.0, 0.0), (1.0, 2.0, 0.0), (0.0, 1.0, 1.0), (0.5, 1.0, -0.7), (-0.3, 0.4, 0.2)):
            yaw, pitch = residual(IDENTITY, target)
            fwd = rotate(Joint(yaw, pitch).quat(), (0.0, 1.0, 0.0))
            n = math.sqrt(sum(c * c for c in target))
            for a, b in zip(fwd, target):
                self.assertAlmostEqual(a, b / n, places=6, msg=str(target))

    def test_residual_is_measured_in_the_bone_frame(self):
        bone = mat_from_quat(axis_angle((0.0, 0.0, 1.0), 90.0), pos=(1.0, 1.0, 0.0))   # 骨头朝 -X，在 (1,1,0)
        yaw, pitch = residual(bone, (-1.0, 1.0, 0.0))                                   # 目标正前方
        self.assertAlmostEqual(yaw, 0.0, places=6)
        self.assertAlmostEqual(pitch, 0.0, places=6)

    def test_world_up_in_a_tilted_bone(self):
        bone = mat_from_quat(axis_angle((1.0, 0.0, 0.0), -45.0))   # 骨头绕 X 转了 45°
        up = world_up_in_local(bone)
        self.assertAlmostEqual(sum(c * c for c in up), 1.0, places=6)
        back = rotate(axis_angle((1.0, 0.0, 0.0), -45.0), up)
        self.assertAlmostEqual(back[1], 1.0, places=6, msg="转回世界坐标应是 +Y")


class FeedForwardTests(unittest.TestCase):
    """前馈：传进来的是绑定姿势的朝向（这里用单位矩阵代表身体朝向），目标固定，角度平滑逼近，不量实际朝向。"""

    # 绑定姿势里骨头的局部轴：+Y 朝前（世界 +X），+Z 朝上（世界 +Y），+X 朝侧（世界 +Z）。和模型量出来的一致。
    BONE = (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)

    def _run(self, target, seconds=2.0):
        g = Gaze()
        for _ in range(int(seconds * 60)):
            g.update(1 / 60, target, head=self.BONE, neck=self.BONE, eye_l=self.BONE, eye_r=self.BONE)
        return g

    def test_head_and_neck_share_the_turn_and_land_on_the_target(self):
        target = (1.0, 0.3, -0.5)        # 世界坐标：前方偏左偏上
        g = self._run(target)
        local = rotate(g.neck.quat((0.0, 0.0, 1.0)), rotate(g.head.quat(), (0.0, 1.0, 0.0)))   # 局部：先头后脖子
        world = (local[1], local[2], local[0])    # 局部 (x, y, z) → 世界：Y→X、Z→Y、X→Z
        n = math.sqrt(sum(c * c for c in target))
        for a, b in zip(world, target):
            self.assertAlmostEqual(a, b / n, delta=0.03, msg="两段旋转拆开再合成，差一两度正常")
        self.assertAlmostEqual(g.neck.yaw / (g.head.yaw + g.neck.yaw), 0.35, places=2, msg="脖子分担 35%")

    def test_target_behind_pins_at_the_limits(self):
        g = self._run((-1.0, 0.0, 0.0))     # 世界 -X = 骨头正后方
        self.assertAlmostEqual(abs(g.head.yaw), HEAD_YAW, delta=0.5)
        self.assertAlmostEqual(abs(g.neck.yaw), NECK_YAW, delta=0.5)
        self.assertLessEqual(abs(g.eye_l.yaw), EYE_LIMIT + 1e-6)

    def test_no_target_relaxes_to_zero_and_reports_nothing(self):
        g = self._run((1.0, 0.3, -0.5))
        for _ in range(4 * 60):
            out = g.update(1 / 60, None)
        self.assertTrue(g.idle)
        self.assertEqual(out, {})

    def test_eyes_settle_before_the_head(self):
        g = Gaze()
        for _ in range(6):                      # 0.1 秒
            g.update(1 / 60, (1.0, 0.0, -1.0), head=self.BONE, neck=self.BONE, eye_l=self.BONE, eye_r=self.BONE)
        self.assertGreater(abs(g.eye_l.yaw) / EYE_LIMIT, 0.75, "眼睛 0.1 秒内基本到位")
        self.assertLess(abs(g.head.yaw) / (0.65 * 45.0), 0.6, "头还在路上")

    def test_during_a_body_turn_the_head_catches_up_within_a_tenth_of_a_second(self):
        """身体在转（quick）：头、脖子、眼睛的平滑时间常数都乘 QUICK。跟鼠标的转身最快每秒约 300°（量的是 turn_speed 1.9、一开始就动；晚上放慢到 1.6，更慢更好追），
        头的平滑要在 0.1 秒里追上九成五才盯得住（QUICK 0.3 时只有八成九，转身时头最多偏 27～30°）。"""
        from widget.gaze import QUICK, TAU_HEAD
        target = (1.0, 0.0, -1.0)
        settled = self._run(target, seconds=3.0)
        slow, quick = Gaze(), Gaze()
        for _ in range(6):                      # 0.1 秒
            slow.update(1 / 60, target, head=self.BONE, neck=self.BONE, eye_l=self.BONE, eye_r=self.BONE)
            quick.update(1 / 60, target, head=self.BONE, neck=self.BONE, eye_l=self.BONE, eye_r=self.BONE, quick=True)
        share = quick.head.yaw / settled.head.yaw
        self.assertAlmostEqual(share, 1.0 - math.exp(-0.1 / (TAU_HEAD * QUICK)), places=6, msg="时间常数乘 QUICK")
        self.assertGreater(share, 0.95, "0.1 秒追上九成五")
        self.assertLess(slow.head.yaw / settled.head.yaw, 0.6, "身体不转时照旧慢慢跟（不抖）")

    def test_eye_with_flipped_axes_gets_flipped_signs(self):
        flipped = mat_from_quat(axis_angle((1.0, 0.0, 0.0), 180.0))   # 绕 X 转 180°：Z 反、X 同向（相对单位矩阵的头）
        g = Gaze()
        g.update(1 / 60, (-1.0, 1.0, 0.0), head=IDENTITY, neck=IDENTITY, eye_l=flipped, eye_r=IDENTITY)
        self.assertGreater(g.eye_r.yaw, 0.0)
        self.assertLess(g.eye_l.yaw, 0.0, "眼睛的偏航轴和头反着，角度符号也要反")
        self.assertAlmostEqual(g.eye_l.yaw, -g.eye_r.yaw, places=6)
