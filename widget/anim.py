"""动画采样与混合：把 GLB 里的动画片段变成每一帧的关节矩阵。

- Player.play(clip, loop, fade)：切到一个片段，和上一个片段在 fade 秒内交叉淡入。
- Player.update(dt) → 每个节点的局部 TRS；Player.joint_matrices() → 送给 GPU 的 57 个矩阵。
- 可以叠加程序控制：override[节点] 整个替换局部变换；rot_offset[节点] 在采样结果上再乘一个旋转（比如抬头、低头）；
  base_blend[节点] = 权重，先把采样出来的旋转往绑定姿势的旋转上拉（1 = 完全不要片段的这根骨头动作），再叠 rot_offset。
纯 Python；57 根骨头在 60 fps 下够用。
"""
from __future__ import annotations

import bisect
import random
from dataclasses import dataclass
from typing import Optional

from widget.gltf import IDENTITY, Clip, Mat4, Model, Quat, Vec3, mat_mul, slerp, trs


@dataclass
class Local:
    t: Vec3
    r: Quat
    s: Vec3


def _lerp3(a, b, u):
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


def sample(clip: Clip, t: float, base: list[Local]) -> list[Local]:
    """在 t 秒处采样片段，没有通道的节点保持 base（绑定姿势）。"""
    out = list(base)
    for ch in clip.channels:
        times = ch.times
        if not times:
            continue
        if t <= times[0]:
            v = ch.key(0)
        elif t >= times[-1]:
            v = ch.key(len(times) - 1)
        else:
            i = bisect.bisect_right(times, t) - 1
            t0, t1 = times[i], times[i + 1]
            u = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            a, b = ch.key(i), ch.key(i + 1)
            if ch.interpolation == "STEP":
                v = a
            elif ch.path == "rotation":
                v = slerp(a, b, u)
            else:
                v = _lerp3(a, b, u)
        loc = out[ch.node]
        if ch.path == "translation":
            out[ch.node] = Local(v, loc.r, loc.s)
        elif ch.path == "rotation":
            out[ch.node] = Local(loc.t, v, loc.s)
        else:
            out[ch.node] = Local(loc.t, loc.r, v)
    return out


def blend(a: list[Local], b: list[Local], u: float) -> list[Local]:
    return [Local(_lerp3(x.t, y.t, u), slerp(x.r, y.r, u), _lerp3(x.s, y.s, u)) for x, y in zip(a, b)]


class Player:
    def __init__(self, model: Model, seed: Optional[int] = None):
        self.model = model
        self.rng = random.Random(seed)
        self.base = [Local(n.translation, n.rotation, n.scale) for n in model.nodes]
        self.clip: Optional[Clip] = None
        self.time = 0.0
        self.loop = True
        self.speed = 1.0
        self.prev: Optional[list[Local]] = None     # 淡出中的上一帧
        self.fade_left = 0.0
        self.fade_total = 0.0
        self.locals: list[Local] = list(self.base)
        self.raw: list[Local] = list(self.base)       # 采样 + 交叉淡入之后、叠 base_blend / override / rot_offset 之前的姿势
        self.override: dict[int, Local] = {}        # 节点索引 → 程序控制的局部变换
        self.rot_offset: dict[int, Quat] = {}       # 节点索引 → 叠加在采样结果上的局部旋转
        self.base_blend: dict[int, float] = {}      # 节点索引 → 往绑定姿势旋转拉多少（0..1），在 rot_offset 之前
        self.finished = False

    # ---- 控制 ----
    def play(self, name: str, loop: bool = True, fade: float = 0.25, speed: float = 1.0, restart: bool = True) -> None:
        clip = self.model.clips[name]
        if self.clip is clip and not restart:
            self.loop = loop
            return
        if self.clip is not None and fade > 0:
            # 淡入的起点要用叠旋转之前的姿势：用 locals 的话，淡入期间 rot_offset 会被叠两次，每次换片段头都会弹一下
            self.prev, self.fade_left, self.fade_total = list(self.raw), fade, fade
        self.clip, self.time, self.loop, self.speed, self.finished = clip, 0.0, loop, speed, False

    @property
    def name(self) -> Optional[str]:
        return self.clip.name if self.clip else None

    @property
    def progress(self) -> float:
        return self.time / self.clip.duration if self.clip and self.clip.duration > 0 else 1.0

    # ---- 每帧 ----
    def update(self, dt: float) -> list[Local]:
        if self.clip is None:
            self.locals = list(self.base)
            return self.locals
        self.time += dt * self.speed
        d = self.clip.duration
        if d > 0:
            if self.loop:
                self.time %= d
            elif self.time >= d:
                self.time, self.finished = d, True
        cur = sample(self.clip, self.time, self.base)
        if self.prev is not None:
            self.fade_left -= dt
            if self.fade_left <= 0:
                self.prev = None
            else:
                u = 1.0 - self.fade_left / self.fade_total
                cur = blend(self.prev, cur, u * u * (3 - 2 * u))
        self.raw = list(cur)
        for idx, w in self.base_blend.items():
            loc = cur[idx]
            cur[idx] = Local(loc.t, slerp(loc.r, self.base[idx].r, w), loc.s)
        for idx, loc in self.override.items():
            cur[idx] = loc
        for idx, q in self.rot_offset.items():
            loc = cur[idx]
            cur[idx] = Local(loc.t, qmul(loc.r, q), loc.s)
        self.locals = cur
        return cur

    def globals(self, root_matrix: Mat4 = IDENTITY) -> list[Mat4]:
        """每个节点的世界矩阵（列主序）。"""
        nodes = self.model.nodes
        out: list[Optional[Mat4]] = [None] * len(nodes)
        order = list(self.model.roots)
        while order:
            i = order.pop(0)
            loc = self.locals[i]
            local = trs(loc.t, loc.r, loc.s)
            parent = nodes[i].parent
            out[i] = mat_mul(out[parent] if parent is not None else root_matrix, local)
            order.extend(nodes[i].children)
        return out  # type: ignore[return-value]

    def joint_matrices(self, root_matrix: Mat4 = IDENTITY) -> list[Mat4]:
        """蒙皮矩阵：世界(关节) · 逆绑定，按 skin 的关节顺序。网格节点自身的变换在它的父链里，这里按 glTF 规范处理。"""
        return self.joint_matrices_from(self.globals(root_matrix))

    def joint_matrices_from(self, g: list[Mat4]) -> list[Mat4]:
        """同上，但用已经算好的 globals()。"""
        mesh_world = g[self.model.mesh_node]
        inv_mesh = _invert_rigid(mesh_world)
        return [mat_mul(inv_mesh, mat_mul(g[j], ibm)) for j, ibm in zip(self.model.skin_joints, self.model.inverse_bind)]

    def node_world(self, name: str, root_matrix: Mat4 = IDENTITY) -> Mat4:
        return self.globals(root_matrix)[self.model.node_by_name(name).index]


def qmul(a: Quat, b: Quat) -> Quat:
    """四元数乘法 a·b（先 b 后 a 的旋转），glTF 顺序 (x, y, z, w)。"""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def axis_angle(axis: Vec3, deg: float) -> Quat:
    import math
    h = math.radians(deg) / 2
    s = math.sin(h)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(h))


def _invert_rigid(m: Mat4) -> Mat4:
    """刚体（旋转 + 平移，可能带均匀缩放）矩阵的逆，列主序。"""
    r = [[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]]   # 行主序 3x3
    # 允许均匀缩放：先除以缩放的平方
    sx2 = m[0] * m[0] + m[1] * m[1] + m[2] * m[2]
    if sx2 == 0:
        return IDENTITY
    inv = [[r[c][rr] / sx2 for c in range(3)] for rr in range(3)]   # 转置 / s²
    t = (m[12], m[13], m[14])
    it = [-(inv[rr][0] * t[0] + inv[rr][1] * t[1] + inv[rr][2] * t[2]) for rr in range(3)]
    return (inv[0][0], inv[1][0], inv[2][0], 0.0,
            inv[0][1], inv[1][1], inv[2][1], 0.0,
            inv[0][2], inv[1][2], inv[2][2], 0.0,
            it[0], it[1], it[2], 1.0)
