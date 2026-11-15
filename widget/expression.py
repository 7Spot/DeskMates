"""程序叠在任何动画上的小表情：眯眼、耳朵往后贴、摇尾巴、歪头、头往手上顶、被戳一下身子一缩、点一下 duang。纯数学，不碰 Qt。

轴都是从模型量出来的，不写死：
- 眼皮：侧睡（Lie_Sleep_loop）闭眼时，眼皮骨相对绑定姿势转了多少（边牧绕自己的 -X 转 60°，萨摩耶 53.5°）。闭多少 = 这个旋转的几成。
- 耳朵：空中平跳（JumpAir_Horiz）时耳朵被风吹得整个往后贴（约 97°）；"耳朵往后"取它的 EAR_GAIN 成。
- 尾巴：每节尾巴骨按绑定姿势算出"世界的上方"在它自己里是哪根轴，绕它（往狗的左右轴偏一点，四分之三视角下看得出尖在上下甩）摆，
  越往尾巴尖摆得越大、越晚（像鞭子）；摇得欢时尾巴整体翘起来一点。
- 身子一缩：根矩阵在地面上竖直压扁几个百分点（脚不离地、不陷进地里），dogctl.root_matrix 用 squash。
- 头：歪头绕头骨自己的 +Y（朝前），往上顶绕 +X（正 = 抬头，和 dogctl 的 head_pitch 一致）。
- duang（点狗只这一下）：按下压扁（弹簧，临界阻尼，很快到底），松手用一根软弹簧弹回来，弹过头时身子微微拉长（squash 变负）。
- 尾巴卷（边牧趴在窝里尾巴穿过窝壁）：curl 0..1，每节尾巴绕摇尾巴的那根轴多转一点、越往尖转得越多（CURL_DEG），往 curl_side 那一侧
  （模型的 ±X；正负按模型量过，curl_sign）；摇尾巴照样叠在上面，幅度小一点（CURL_WAG_CUT）。要卷多少按模型和窝量（dogctl.tail_curl）。
- 坐着叫一声（默认坐着的萨摩耶圈满时）：模型里没有坐着叫的片段——嘴和舌头照 Bark 片段里嘴张得最大的那一下（第一声，BARK_PEAK_S 附近量的），
  头往上抬一点（BARK_LIFT_DEG），一个脉冲（BARK_S）。
每个量都有目标值和实际值，实际值按时间常数追目标值；"一下子"的动作（眨眼、耳朵一抖、身子一缩、尾巴一甩）是脉冲，叠在上面。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from widget.anim import Player, axis_angle, qmul
from widget.gltf import IDENTITY, Model, Quat, slerp, table

EYE_CLOSE_DEG = 60.0        # 眼皮全闭转多少：模型没有侧睡片段时用这个（有的按模型量，ExpressionRig.eye_close）
EAR_GAIN = 0.42             # "耳朵往后贴"取空中平跳那个姿势的几成（全贴约 40°）
TAIL_AMP = (7.0, 10.0, 13.0, 16.0, 19.0)   # 摇得最欢时每节尾巴左右各摆多少度（根 → 尖）
TAIL_TILT = 0.5             # 摆动轴往狗的左右轴偏多少（0 = 纯水平摆，四分之三视角下只看得出尾巴变长变短）
TAIL_RAISE_DEG = 14.0       # 摇得最欢时尾巴整体翘起多少（五节加起来）
TAIL_LAG = 0.55             # 每节比上一节晚多少相位（弧度）
TAIL_FREQ = (2.6, 5.2)      # 摇尾巴频率：轻轻摇 → 摇得欢
TAU = {"eyes": 0.10, "ears": 0.12, "wag": 0.30, "tilt": 0.22, "lift": 0.18, "crouch": 0.15, "curl": 0.13}   # curl：0.4 秒基本卷好
CURL_DEG = (14.0, 22.0, 30.0, 38.0, 46.0)  # 卷到底时每节尾巴多转多少度（根 → 尖，越往尖越多：绕在后腿边上）
CURL_WAG_CUT = 0.5                        # 卷着的时候摇尾巴的幅度打这么多折
_ID: Quat = (0.0, 0.0, 0.0, 1.0)
PRESS_OMEGA, PRESS_ZETA = 42.0, 1.0     # duang 按下：很快压到底，不弹
RELEASE_OMEGA, RELEASE_ZETA = 24.0, 0.2 # 松手：软弹簧，约 0.45 秒停
RELEASE_SECONDS = 0.45                  # 上面这根弹簧大约弹这么久（调参改的是这个，弹簧按比例变）
KICK_GAIN = 1.3                         # kick 给多大的速度才压到要的深度
BARK_S = 0.32                           # 坐着叫一声：嘴张开再合上多久
BARK_LIFT_DEG = 7.0                     # …头往上抬多少
BARK_PEAK_S = (0.40, 0.75)              # Bark 片段里第一声在这一段（秒）：嘴张得最大的那一下从这里找
MOUTH_BONES = ("mouth", "Mouth.L", "Mouth.R", "tongue_1", "tongue_2", "tongue_3", "tongue_4")


def _qinv(q: Quat) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / n for c in v)


@dataclass
class Pulse:
    """一下子的动作：start 秒开始、持续 dur 秒、峰值 peak，形状是先快后慢的鼓包（sin 半周期）。"""
    start: float
    dur: float
    peak: float

    def value(self, t: float) -> float:
        """前 30% 快速升到峰值，后 70% 慢慢落回 0。"""
        u = (t - self.start) / self.dur
        if u <= 0.0 or u >= 1.0:
            return 0.0
        if u < 0.3:
            return self.peak * math.sin(u / 0.3 * math.pi / 2)
        return self.peak * math.cos((u - 0.3) / 0.7 * math.pi / 2)


@dataclass
class Expression:
    """目标值（行为层每帧设）：eyes 0 睁 … 1 闭；ears 0 … 1 往后贴；wag 0 … 1 摇尾巴；tilt 歪头（度，正 = 往左歪）；lift 头往上顶（度）；
    crouch 身子一直压低多少（0.10 = 10%，按住狗准备拉时）；curl 尾巴往身子这边卷多少（0 … 1，歇在窝里），curl_side 往模型的 +X（1）还是 −X（−1）卷。"""
    eyes: float = 0.0
    ears: float = 0.0
    wag: float = 0.0
    tilt: float = 0.0
    lift: float = 0.0
    crouch: float = 0.0
    curl: float = 0.0
    curl_side: float = 1.0
    cur: dict = field(default_factory=lambda: {"eyes": 0.0, "ears": 0.0, "wag": 0.0, "tilt": 0.0, "lift": 0.0, "crouch": 0.0, "curl": 0.0})
    pulses: dict = field(default_factory=lambda: {"blink": [], "ears": [], "bob": [], "flick": [], "bark": []})
    phase: float = 0.0
    t: float = 0.0
    duang: float = 0.0                  # 现在压扁多少（负的是拉长）
    duang_v: float = 0.0
    pressing: bool = False
    press_depth: float = 0.15
    release_omega: float = RELEASE_OMEGA

    def reset(self) -> None:
        self.eyes = self.ears = self.wag = self.tilt = self.lift = self.crouch = self.curl = 0.0
        self.pressing = False

    # ---- duang ----
    def press(self, depth: float = 0.15) -> None:
        """按下去：压扁到 depth（0.15 = 15%），按多久压多久。"""
        self.pressing = True
        self.press_depth = depth

    def release(self, seconds: float = RELEASE_SECONDS) -> None:
        """松手：弹回来，弹 seconds 秒左右。"""
        self.pressing = False
        self.release_omega = RELEASE_OMEGA * RELEASE_SECONDS / max(0.05, seconds)

    def kick(self, depth: float) -> None:
        """落地那一下：不用按，直接压一下弹回来（depth 差不多是压到的深度）。"""
        self.pressing = False
        self.duang_v += depth * self.release_omega * KICK_GAIN

    def _step_duang(self, dt: float) -> None:
        if not self.pressing and abs(self.duang) < 1e-4 and abs(self.duang_v) < 1e-3:
            self.duang = self.duang_v = 0.0
            return
        w, z, target = (PRESS_OMEGA, PRESS_ZETA, self.press_depth) if self.pressing else (self.release_omega, RELEASE_ZETA, 0.0)
        n = max(1, math.ceil(dt * w / 0.25))     # 帧慢的时候分几步，弹簧不炸
        h = dt / n
        for _ in range(n):
            self.duang_v += (w * w * (target - self.duang) - 2.0 * z * w * self.duang_v) * h
            self.duang += self.duang_v * h

    # ---- 一下子的动作 ----
    def blink(self, dur: float = 0.18, peak: float = 1.0, delay: float = 0.0) -> None:
        self.pulses["blink"].append(Pulse(self.t + delay, dur, peak))

    def ear_flick(self, dur: float = 0.35, peak: float = 1.0) -> None:
        self.pulses["ears"].append(Pulse(self.t, dur, peak))

    def bob(self, amount: float = 0.05, dur: float = 0.22) -> None:
        """身子往下一缩（被戳了一下）：竖直压扁 amount（0.05 = 5%），脚不动。"""
        self.pulses["bob"].append(Pulse(self.t, dur, amount))

    def tail_flick(self, dur: float = 0.6, peak: float = 1.0) -> None:
        self.pulses["flick"].append(Pulse(self.t, dur, peak))

    def bark(self, dur: float = BARK_S) -> None:
        """坐着叫一声：张一下嘴、头抬一点（声音由叫它的人放）。"""
        self.pulses["bark"].append(Pulse(self.t, dur, 1.0))

    def _pulse(self, kind: str) -> float:
        alive = [p for p in self.pulses[kind] if self.t < p.start + p.dur]
        self.pulses[kind] = alive
        return max((p.value(self.t) for p in alive), default=0.0)

    # ---- 每帧 ----
    def update(self, dt: float) -> None:
        self.t += dt
        for k, tau in TAU.items():
            target = getattr(self, k)
            self.cur[k] += (target - self.cur[k]) * (1.0 - math.exp(-dt / tau))
        wag = max(self.cur["wag"], 0.8 * self._pulse("flick"))
        self.phase += dt * 2.0 * math.pi * (TAIL_FREQ[0] + (TAIL_FREQ[1] - TAIL_FREQ[0]) * min(1.0, wag))
        self._step_duang(dt)

    @property
    def squash(self) -> float:
        """身子竖直压扁多少（负的是拉长）：被戳的那一缩、一直压低的那点、duang 压下去的，取大的；duang 弹过头时拉长。"""
        base = max(self._pulse("bob"), self.cur["crouch"])
        return max(base, self.duang) if self.duang >= 0.0 else base + self.duang

    @property
    def active(self) -> bool:
        return any(abs(v) > 1e-3 for v in self.cur.values()) or any(self.pulses.values()) or any(
            abs(getattr(self, k)) > 1e-3 for k in TAU) or self.pressing or abs(self.duang) > 1e-4


class ExpressionRig:
    """量好的轴：把 Expression 的数变成各骨头的局部旋转（Player.rot_offset 的格式，右乘在片段姿势上）。
    量的那几样（眼皮、耳朵、叫的嘴、尾巴的轴）按模型量一次记在模型上（gltf.Model.measured）、各只控制器共用，量完只读：
    以前每建一只控制器都现采样片段约 15 毫秒，换同桌那一下主线程跟着卡；后台备料时就量好（kits.warm 建控制器）。"""

    def __init__(self, model: Model):
        measured = table(model, "expression_rig")
        if not measured:
            measured.update(self._measure(model))
        self.__dict__.update(measured)

    def _measure(self, model: Model) -> dict:
        self._measure_into(model)
        return dict(self.__dict__)

    def _measure_into(self, model: Model) -> None:
        idx = {n.name: i for i, n in enumerate(model.nodes)}
        self.idx = idx
        self.eyelids = [idx[n] for n in ("eyelid.L", "eyelid.R") if n in idx]
        self.head = idx["head"]
        self.eye_close: dict[int, Quat] = {}                       # 眼皮全闭时相对绑定姿势的旋转：侧睡片段中点量的；没有这段片段就按 EYE_CLOSE_DEG
        if self.eyelids and dict.__contains__(model.clips, "Lie_Sleep_loop"):
            p = Player(model)
            p.play("Lie_Sleep_loop", loop=False, fade=0.0)
            p.time = model.clips["Lie_Sleep_loop"].duration / 2
            p.update(0.0)
            self.eye_close = {i: qmul(_qinv(model.nodes[i].rotation), p.locals[i].r) for i in self.eyelids}
        self.ears: dict[int, Quat] = {}
        p = Player(model)
        p.play("JumpAir_Horiz", loop=False, fade=0.0)
        p.time = model.clips["JumpAir_Horiz"].duration / 8
        p.update(0.0)
        for n in ("Ear_01.L", "Ear_02.L", "Ear_01.R", "Ear_02.R"):
            if n in idx:
                i = idx[n]
                self.ears[i] = qmul(_qinv(model.nodes[i].rotation), p.locals[i].r)   # 绑定 → 贴后的那一下
        self.mouth_open: dict[int, Quat] = {}                     # 嘴张得最大时嘴和舌头相对绑定姿势的旋转（Bark 片段第一声）；没有这段片段就不张
        mouth = [idx[n] for n in MOUTH_BONES if n in idx]
        if mouth and dict.__contains__(model.clips, "Bark"):
            p = Player(model)
            p.play("Bark", loop=False, fade=0.0)
            best, best_t = -1.0, BARK_PEAK_S[0]
            for k in range(25):
                t = BARK_PEAK_S[0] + (BARK_PEAK_S[1] - BARK_PEAK_S[0]) * k / 24
                p.time = t
                p.update(0.0)
                q = qmul(_qinv(model.nodes[mouth[0]].rotation), p.locals[mouth[0]].r)
                open_by = abs(math.acos(max(-1.0, min(1.0, abs(q[3]))))) * 2.0
                if open_by > best:
                    best, best_t = open_by, t
            p.time = best_t
            p.update(0.0)
            self.mouth_open = {i: qmul(_qinv(model.nodes[i].rotation), p.locals[i].r) for i in mouth}
        bind = Player(model)
        bind.update(0.0)
        g = bind.globals(IDENTITY)
        self.curl_sign = 1.0                                     # 绕摇尾巴的轴正着转，尾巴尖往模型的 +X 去还是 −X 去（按模型量，下面）
        self.tail: list[tuple[int, tuple[float, float, float], tuple[float, float, float]]] = []
        for k in range(1, 6):
            n = f"Tail_0{k}"
            if n in idx:
                i = idx[n]
                m = g[i]
                cols = [(m[0], m[1], m[2]), (m[4], m[5], m[6]), (m[8], m[9], m[10])]
                up = _norm(tuple(c[1] for c in cols))            # 世界 +Y 在这根骨头里的方向（R^T · (0,1,0)）
                side = _norm(tuple(c[0] for c in cols))          # 世界 +X（狗的左右轴）
                axis = _norm(tuple(u + TAIL_TILT * sd for u, sd in zip(up, side)))
                self.tail.append((i, axis, side))
        if self.tail:
            tip = self.tail[-1][0]
            bent = Player(model)
            bent.rot_offset = {i: axis_angle(axis, 20.0) for i, axis, _ in self.tail}
            bent.update(0.0)
            self.curl_sign = 1.0 if bent.globals(IDENTITY)[tip][12] >= g[tip][12] else -1.0

    def offsets(self, e: Expression) -> dict[int, Quat]:
        out: dict[int, Quat] = {}
        eyes = min(1.0, max(e.cur["eyes"], e._pulse("blink")))
        if eyes > 1e-3:
            q = axis_angle((-1.0, 0.0, 0.0), EYE_CLOSE_DEG * eyes)
            for i in self.eyelids:
                out[i] = slerp(_ID, self.eye_close[i], eyes) if i in self.eye_close else q
        ears = min(1.4, max(e.cur["ears"], e._pulse("ears")))
        if ears > 1e-3:
            for i, q in self.ears.items():
                out[i] = slerp(_ID, q, EAR_GAIN * ears)
        wag = min(1.0, max(e.cur["wag"], e._pulse("flick")))
        curl = min(1.0, max(0.0, e.cur["curl"]))
        if wag > 1e-3 or curl > 1e-3:
            n = max(1, len(self.tail))
            sway = wag * (1.0 - CURL_WAG_CUT * curl)
            for k, (i, axis, side) in enumerate(self.tail):
                ang = TAIL_AMP[min(k, len(TAIL_AMP) - 1)] * sway * math.sin(e.phase - k * TAIL_LAG)
                ang += CURL_DEG[min(k, len(CURL_DEG) - 1)] * curl * e.curl_side * self.curl_sign
                out[i] = qmul(axis_angle(side, TAIL_RAISE_DEG / n * sway), axis_angle(axis, ang))
        bark = e._pulse("bark")
        if bark > 1e-3:
            for i, q in self.mouth_open.items():
                out[i] = slerp(_ID, q, bark)
        head: Optional[Quat] = None
        if abs(e.cur["tilt"]) > 1e-2:
            head = axis_angle((0.0, 1.0, 0.0), e.cur["tilt"])
        lift_deg = e.cur["lift"] + BARK_LIFT_DEG * bark
        if abs(lift_deg) > 1e-2:
            lift = axis_angle((1.0, 0.0, 0.0), lift_deg)
            head = qmul(head, lift) if head else lift
        if head is not None:
            out[self.head] = head
        return out


def merge(base: dict[int, Quat], extra: dict[int, Quat]) -> dict[int, Quat]:
    """把表情叠到鼠标跟随算出来的旋转上（都是右乘在片段姿势上的局部旋转：先跟随、再表情）。"""
    out = dict(base)
    for i, q in extra.items():
        out[i] = qmul(out[i], q) if i in out else q
    return out
