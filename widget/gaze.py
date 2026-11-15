"""鼠标跟随：狗的头、脖子、眼睛看向世界坐标里的一个目标点。纯数学，不碰 Qt。

前馈，不是伺服：以每根骨头的**绑定姿势**（相对身体的朝向）为基准，算出"要看到目标得转多少度"，限幅、按时间常数平滑，
再叠在动画采样结果上。不去量动画后头的实际朝向，所以片段自己的低头、打哈欠、甩头照常播，只是整体朝着鼠标；也没有一帧延迟。
骨骼局部轴（模型量出来的）：head / neck / eye.* 的 +Y 沿骨头朝前，+X 是左右（俯仰轴），+Z 是上下（偏航轴）。眼睛的局部轴和头的
方向相反，符号在 update 里按传进来的绑定矩阵算，不写死。
目标为 None（功能关着；灵动交互里鼠标停着一阵了，window._look_target）时所有角度按 TAU_RELAX 慢慢回零；看不看由给目标的那边定。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from widget.anim import axis_angle, qmul
from widget.gltf import Mat4, Quat, Vec3

Z_FRONT = 0.45          # 把鼠标当成在狗前方（朝镜头）这么多米处的一个点：鼠标在狗脸上时狗正看镜头
NECK_SHARE = 0.35       # 转头的角度里脖子分担多少
HEAD_YAW, HEAD_UP, HEAD_DOWN = 65.0, 30.0, 25.0   # 头的限幅（度）
NECK_YAW, NECK_PITCH = 25.0, 12.0
EYE_LIMIT = 12.0
TAU_HEAD, TAU_NECK, TAU_EYE, TAU_RELAX = 0.15, 0.22, 0.06, 0.5   # 平滑时间常数（秒）
QUICK = 0.15            # 身体转身时时间常数乘这个：跟鼠标的转身每秒转二三百度（turn_speed 1.9、一开始就动），平滑再慢头就落后近 30°
                        # （离线按 tests/test_clips 的转身测试量：0.3 时最多偏 27～30°，0.15 时 18～20°）


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _unit(x: float, y: float, z: float) -> Vec3:
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / n, y / n, z / n)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def axes(m: Mat4) -> tuple[Vec3, Vec3, Vec3, Vec3]:
    """列主序世界矩阵 → 归一化的局部 X / Y / Z 轴（世界坐标）和位置。"""
    return _unit(m[0], m[1], m[2]), _unit(m[4], m[5], m[6]), _unit(m[8], m[9], m[10]), (m[12], m[13], m[14])


def residual(world: Mat4, target: Vec3) -> tuple[float, float]:
    """骨头矩阵（朝向 + 位置）→ 它的 +Y 要指向目标点得转多少 (yaw, pitch)，度，骨头局部坐标。"""
    X, Y, Z, P = axes(world)
    d = (target[0] - P[0], target[1] - P[1], target[2] - P[2])
    dx, dy, dz = _dot(d, X), _dot(d, Y), _dot(d, Z)
    return math.degrees(math.atan2(-dx, dy)), math.degrees(math.atan2(dz, math.hypot(dx, dy)))


def world_up_in_local(world: Mat4) -> Vec3:
    """世界 +Y 在这根骨头局部坐标里的方向（脖子绕它偏航，才是真正的左右转头，不带歪头）。"""
    X, Y, Z, _ = axes(world)
    return _unit(X[1], Y[1], Z[1])


def rotate(q: Quat, v: Vec3) -> Vec3:
    """四元数转一个向量：v' = v + 2w(q×v) + 2q×(q×v)。"""
    x, y, z, w = q
    cx, cy, cz = y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0]
    ccx, ccy, ccz = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (v[0] + 2 * (w * cx + ccx), v[1] + 2 * (w * cy + ccy), v[2] + 2 * (w * cz + ccz))


@dataclass
class Joint:
    yaw: float = 0.0
    pitch: float = 0.0

    def approach(self, yaw: float, pitch: float, dt: float, tau: float) -> None:
        k = 1.0 - math.exp(-dt / tau) if tau > 0 else 1.0
        self.yaw += (yaw - self.yaw) * k
        self.pitch += (pitch - self.pitch) * k

    def quat(self, yaw_axis: Vec3 = (0.0, 0.0, 1.0)) -> Quat:
        """先俯仰（绕局部 X）再偏航（绕 yaw_axis，默认局部 Z）。"""
        return qmul(axis_angle(yaw_axis, self.yaw), axis_angle((1.0, 0.0, 0.0), self.pitch))

    @property
    def idle(self) -> bool:
        return abs(self.yaw) < 0.05 and abs(self.pitch) < 0.05


class Gaze:
    def __init__(self):
        self.head, self.neck, self.eye_l, self.eye_r = Joint(), Joint(), Joint(), Joint()

    @property
    def idle(self) -> bool:
        return all(j.idle for j in (self.head, self.neck, self.eye_l, self.eye_r))

    def update(self, dt: float, target: Optional[Vec3], head: Optional[Mat4] = None, neck: Optional[Mat4] = None,
               eye_l: Optional[Mat4] = None, eye_r: Optional[Mat4] = None, quick: bool = False) -> dict[str, Quat]:
        """推进一帧。矩阵：各骨头**绑定姿势**的朝向（以胸椎的实时朝向为基准，也就是相对身体的朝向）+ 当前动画后的位置。
        quick：身体正在转，平滑加快。返回要叠加到各骨头局部旋转上的四元数，按骨头名。"""
        k = QUICK if quick else 1.0
        if target is None or head is None:
            for j in (self.head, self.neck, self.eye_l, self.eye_r):
                j.approach(0.0, 0.0, dt, TAU_RELAX)
        else:
            ty, tp = residual(head, target)                 # 相对身体一共要转多少
            self.head.approach(_clamp((1 - NECK_SHARE) * ty, -HEAD_YAW, HEAD_YAW),
                               _clamp((1 - NECK_SHARE) * tp, -HEAD_DOWN, HEAD_UP), dt, TAU_HEAD * k)
            self.neck.approach(_clamp(NECK_SHARE * ty, -NECK_YAW, NECK_YAW), _clamp(NECK_SHARE * tp, -NECK_PITCH, NECK_PITCH), dt, TAU_NECK * k)
            rest_y = ty - (self.head.yaw + self.neck.yaw)   # 头和脖子还没给到的，眼睛补，限 ±12°
            rest_p = tp - (self.head.pitch + self.neck.pitch)
            hX, _, hZ, _ = axes(head)
            for eye, m in ((self.eye_l, eye_l), (self.eye_r, eye_r)):
                if m is None:
                    continue
                eX, _, eZ, _ = axes(m)                      # 眼睛的轴可能和头反着，符号按矩阵算
                sy = 1.0 if _dot(eZ, hZ) >= 0 else -1.0
                sp = 1.0 if _dot(eX, hX) >= 0 else -1.0
                eye.approach(sy * _clamp(rest_y, -EYE_LIMIT, EYE_LIMIT), sp * _clamp(rest_p, -EYE_LIMIT, EYE_LIMIT), dt, TAU_EYE * k)
        out: dict[str, Quat] = {}
        if not self.head.idle:
            out["head"] = self.head.quat()
        if not self.neck.idle:
            out["neck"] = self.neck.quat(world_up_in_local(neck) if neck is not None else (0.0, 0.0, 1.0))
        if not self.eye_l.idle:
            out["eye.L"] = self.eye_l.quat()
        if not self.eye_r.idle:
            out["eye.R"] = self.eye_r.quat()
        return out
