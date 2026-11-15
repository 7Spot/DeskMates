"""拎起来（只在灵动交互里）：肚子被提起来、四条腿垂着。模型没有这种片段，按骨头手工调（放在待机片段上）；
上下轻轻浮、跟手摆（绕抓的地方转）、腿跟着手晃，松手很快融回去。纯数学，不碰 Qt。

姿势（DEG）从模型量：脊柱拱起来（中间高、头尾低）；腿一节一节按"这一节该朝哪"转到位（朝下 180°，小一点脚尖往前、大一点往后）；
尾巴垂着的再翘起来，本来就卷在背上的不动。
都绕狗的左右轴转（每根骨头算一次这根轴在它自己里的方向，叠在片段姿势上）。缺骨头的模型那一部分不动。"""
from __future__ import annotations

import math
from typing import Optional

from widget.anim import Player, axis_angle
from widget.gltf import IDENTITY, Mat4, Model, Quat, mat_mul, measured

ARCH_DEG, HEAD_DEG = 22.0, 6.0
TAIL_UP_DEG = 40.0                    # 尾巴翘多少度（拎起来尾巴应该还翘着，不荡下来）；尾巴本来就卷在背上的（萨摩耶）不加，见 LiftRig.tail_curled
TAIL_SWING = 0.25                     # 尾巴跟着腿甩，幅度打几折：甩的时候也不垂下来
LEG_TARGETS = {"hind": (168.0, 200.0, 172.0, 150.0), "front": (195.0, 176.0, 170.0, 150.0)}   # 大腿、小腿、胫、脚每节朝哪（度，朝下 180）
SPINE = ("Spine_02", "Spine_03", "Spine_04", "Spine_05")
TAILS = ("Tail_02", "Tail_03", "Tail_04", "Tail_05")
FADE_IN, FADE_OUT = 0.09, 0.07        # 姿势融进来、融回去的时间常数（秒）
BOB_HZ = 0.7                          # 上下浮多快
SWAY_OMEGA, SWAY_ZETA, SWAY_GAIN = 6.8, 0.16, 0.11   # 摆：像单摆，手的加速度推它
LEG_OMEGA, LEG_ZETA, LEG_GAIN = 9.0, 0.7, 14.0       # 腿晃：手快一米 / 秒腿甩这么多度；阻尼够大，甩完不再来回抡
LEG_MAX = 30.0                        # 腿最多甩这么多度（手快的时候腿会转一整圈，不正常），越接近上限越难动
ACCEL_CAP = 40.0                      # 手的加速度最多算这么大（米 / 秒²）：鼠标事件不匀，一下子很大的是假的
GRAB_POINT = (-0.04, 0.60)            # 绕哪转（肚子 / 背中间，相对根，米）


def _trans(x: float, y: float) -> Mat4:
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, 0.0, 1)


def _rot_z(a: float) -> Mat4:
    c, s = math.cos(a), math.sin(a)
    return (c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


class LiftRig:
    """量好的姿势：每根骨头转多少度、绕哪根轴（这个模型第一次拎、或开灵动交互时量，约 3 毫秒；量完不再变，记在模型上，同一个模型的控制器共用）。"""

    def __init__(self, model: Model, clip: str = "Idle_1"):
        self.model = model
        self.clip = clip
        self.idx = {n.name: i for i, n in enumerate(model.nodes)}
        base = self._globals({})
        self.axis = {i: self._lateral(base, i) for i in range(len(model.nodes))}
        root, tip = self.idx.get("Tail_01"), self.idx.get("Tail_05")
        self.tail_curled = root is not None and tip is not None and base[tip][13] > base[root][13]   # 站着时尾尖比尾根高：尾巴本来就卷在背上，再翘会压扁在背上
        self.deg = self._solve()
        self.thighs = [self.idx[n] for n in ("thigh_b.L", "thigh_b.R", "thigh_f.L", "thigh_f.R") if n in self.idx]
        self.tail = self.idx.get("Tail_01")

    def _globals(self, offsets: dict[int, Quat]) -> list[Mat4]:
        p = Player(self.model)
        p.play(self.clip, loop=False, fade=0.0)
        p.rot_offset = offsets
        p.update(0.0)
        return p.globals(IDENTITY)

    @staticmethod
    def _lateral(g: list[Mat4], i: int) -> tuple[float, float, float]:
        m = g[i]
        a = (m[0], m[4], m[8])
        n = math.sqrt(sum(c * c for c in a)) or 1.0
        return (a[0] / n, a[1] / n, a[2] / n)

    def _quats(self, deg: dict[int, float]) -> dict[int, Quat]:
        return {i: axis_angle(self.axis[i], d) for i, d in deg.items()}

    def _solve(self) -> dict[int, float]:
        idx = self.idx
        named = {"Spine_base": -ARCH_DEG, "neck": -ARCH_DEG * 0.35 + HEAD_DEG * 0.5, "head": -ARCH_DEG * 0.30 + HEAD_DEG * 0.5, "Tail_01": TAIL_UP_DEG * 0.5}
        named.update({n: ARCH_DEG * 0.5 for n in SPINE})
        named.update({n: TAIL_UP_DEG * 0.2 for n in TAILS})
        if self.tail_curled:                                      # 卷尾巴：尾巴那几项不加（照样跟着腿甩，offsets）
            for n in ("Tail_01",) + TAILS:
                del named[n]
        deg = {idx[n]: d for n, d in named.items() if n in idx}
        for side in ("L", "R"):
            for kind, tag in (("hind", "b"), ("front", "f")):
                chain = [idx.get(f"{part}_{tag}.{side}") for part in ("thigh", "leg", "shin", "foot", "claws")]
                if any(i is None for i in chain):
                    continue
                for k, target in enumerate(LEG_TARGETS[kind]):
                    g = self._globals(self._quats(deg))
                    a, b = g[chain[k]], g[chain[k + 1]]
                    now = math.degrees(math.atan2(b[14] - a[14], b[13] - a[13])) % 360.0
                    deg[chain[k]] = deg.get(chain[k], 0.0) + ((target - now + 180.0) % 360.0 - 180.0)
        return deg

    def offsets(self, w: float, swing: float) -> dict[int, Quat]:
        """w：姿势融进来几成；swing：腿甩多少度。"""
        extra = {i: swing for i in self.thighs}
        if self.tail is not None:
            extra[self.tail] = swing * TAIL_SWING
        out: dict[int, Quat] = {}
        for i in set(self.deg) | set(extra):
            total = self.deg.get(i, 0.0) * w + extra.get(i, 0.0)
            if abs(total) > 1e-3:
                out[i] = axis_angle(self.axis[i], total)
        return out


class Lift:
    """拎着的状态。roam 调 begin / end，playground 每帧 feed 手的速度，控制器每帧 update，取 offsets（叠在骨头上）、matrix（叠在根上）。"""

    def __init__(self, model: Model):
        self.model = model
        self.rig: Optional[LiftRig] = None
        self.active = False
        self.w = 0.0
        self.t = 0.0
        self.th = self.thv = 0.0             # 摆的角度（弧度）、角速度
        self.leg = self.legv = 0.0           # 腿甩的角度（度）、角速度
        self.hand_vx = 0.0                   # 手横着多快（米 / 秒）
        self._prev_vx = 0.0
        self.bob = 0.02                      # 上下浮多大（米，调参）
        self.sway = 1.0                      # 摆和腿晃的倍数（调参）

    def prepare(self) -> None:
        """提前量好姿势（灵动交互一开就调，第一次拎不卡一下）。这个模型量过就直接拿（gltf.Model.measured）。"""
        if self.rig is None:
            self.rig = measured(self.model, "lift_rig", lambda: LiftRig(self.model))

    def begin(self) -> None:
        self.prepare()
        self.active = True
        self.t = 0.0
        self._prev_vx = self.hand_vx = 0.0

    def end(self) -> None:
        self.active = False
        self.hand_vx = 0.0

    def cut(self) -> None:
        """马上收掉（关灵动交互、出错）。"""
        self.active = False
        self.w = self.th = self.thv = self.leg = self.legv = 0.0

    def feed(self, vx: float) -> None:
        self.hand_vx = vx

    @property
    def on(self) -> bool:
        return self.w > 0.002 or self.active or abs(self.th) > 1e-3

    def update(self, dt: float, forward: float) -> None:
        """forward：狗朝右 +1、朝左 -1（腿往手的反方向甩）。"""
        if not self.on or dt <= 0.0:
            return
        self.t += dt
        tau = FADE_IN if self.active else FADE_OUT
        self.w += ((1.0 if self.active else 0.0) - self.w) * (1.0 - math.exp(-dt / tau))
        ax = max(-ACCEL_CAP, min(ACCEL_CAP, (self.hand_vx - self._prev_vx) / dt)) * self.sway
        self._prev_vx = self.hand_vx
        self.thv += (-SWAY_OMEGA * SWAY_OMEGA * self.th - 2.0 * SWAY_ZETA * SWAY_OMEGA * self.thv + SWAY_GAIN * ax) * dt
        self.th += self.thv * dt
        target = LEG_MAX * math.tanh(LEG_GAIN * self.hand_vx * forward * self.sway / LEG_MAX) if self.active else 0.0
        self.legv += (LEG_OMEGA * LEG_OMEGA * (target - self.leg) - 2.0 * LEG_ZETA * LEG_OMEGA * self.legv) * dt
        self.leg += self.legv * dt
        if abs(self.leg) > LEG_MAX:
            self.leg, self.legv = math.copysign(LEG_MAX, self.leg), 0.0
        if not self.active:                  # 松手：摆很快收住（掉下去的时候不再晃）
            self.th *= math.exp(-dt / 0.12)
            self.thv *= math.exp(-dt / 0.12)
            if self.w < 0.002 and abs(self.th) < 1e-3:
                self.w = self.th = self.thv = self.leg = self.legv = 0.0

    def offsets(self) -> dict[int, Quat]:
        if self.rig is None or self.w <= 0.002:
            return {}
        return self.rig.offsets(self.w, self.leg * self.w)

    def matrix(self) -> Optional[Mat4]:
        """叠在根矩阵外面：上下浮、绕抓的地方摆；没拎着 None。"""
        if not self.on:
            return None
        y = self.bob * math.sin(self.t * 2.0 * math.pi * BOB_HZ) * self.w
        gx, gy = GRAB_POINT
        return mat_mul(_trans(gx, gy + y), mat_mul(_rot_z(self.th), _trans(-gx, -gy)))
