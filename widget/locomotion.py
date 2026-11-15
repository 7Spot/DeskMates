"""灵动交互里狗离开原地（跑去捡球、跳上窗口、掉下来）时，控制器交给 widget/roam.py 牵着走：DogController 的 mixin。

puppet_begin() 之后，狗自己的事（随机动作、头带身体、排队的姿势）都停，只听 roam 的：
- puppet_play(片段)：播一段（循环或一次），roam 看 player.finished / progress 决定下一步；
- puppet_face(朝向)：平滑地转过去，转多少度都不播转身片段（转身太慢、非得转完才走）：180° 约 0.36 秒，
  差得多的走经过镜头正前方那条路；puppet_turning 看转完没。roam 起跑时不等它转完，边转边跑；
- pelvis_metrics(片段, 进度)：骨盆多高、往前多少；foot_metrics(片段, 进度)：后脚、前脚的高和往前（米，模型量的，1/60 进度取样、中间插值）。
  roam 拿它们让脚踩在平面上（起跳时按后脚反算根）、落地时骨盆跟着落地片段走；planted_hind：站着时后脚骨离地多高。
puppet_end() 交回来：站着，随机动作重新计时。位置（窗口在屏幕上的哪）由 roam 管，控制器里的 x / z 一直是 0（狗永远在窗口正中）。"""
from __future__ import annotations

import math
from typing import Optional

from widget.anim import Player
from widget import temper
from widget.clips import FADE_CLIP, POSTURE_PLANS
from widget.gltf import IDENTITY, measured, table
from widget.play import PostureStep, _ease, _wrap

TURN_BASE, TURN_PER_180 = 0.14, 0.22   # 平滑转身用时：0.14 秒起，每 180° 再加 0.22 秒（180° ≈ 0.36 秒）
CURL_WORTH_M = 0.05                    # 尾巴卷到底也够不着窝的内沿时：卷了至少能收回来这么多（米）才卷
TAIL_SAMPLES = 10                      # 找趴着时尾巴甩得最远的那一刻：每段循环看这么多帧
FEET_STEPS = 60                        # foot_metrics 按 1/60 进度取样


class LocomotionMixin:
    def _init_locomotion(self) -> None:
        self.puppet = False
        self._feet: dict[tuple[str, int], tuple[float, float, float, float, float, float]] = table(self.model, "feet")   # (片段, 第几格) → 脚和骨盆：记在模型上（gltf.Model.measured）
        self._spin: Optional[tuple[float, float, float, float]] = None   # 平滑转身：(起始朝向, 转多少度, 已过秒数, 总秒数)
        names = [n.name for n in self.model.nodes]
        self._hind_feet = [i for i, n in enumerate(names) if n.startswith("foot_b")]
        self._front_feet = [i for i, n in enumerate(names) if n.startswith("foot_f")]
        self._pelvis = self.model.node_by_name("Spine_base").index

    # ---- 量姿势 ----
    def _metrics_at(self, clip: str, u: float) -> tuple[float, float, float, float, float, float]:
        x = max(0.0, min(1.0, u)) * FEET_STEPS
        k = min(FEET_STEPS - 1, int(x))
        a, b = self._feet_at(clip, k), self._feet_at(clip, k + 1)
        f = x - k
        return tuple(p + (q - p) * f for p, q in zip(a, b))

    def foot_metrics(self, clip: str, u: float) -> tuple[float, float, float, float]:
        """片段在进度 u 时：(后脚的高, 后脚往前, 前脚的高, 前脚往前)，两只取平均，米，模型局部（狗朝 +Z）。"""
        return self._metrics_at(clip, u)[:4]

    def pelvis_metrics(self, clip: str, u: float) -> tuple[float, float]:
        """片段在进度 u 时：(骨盆离地多高, 骨盆往前多少)，米，模型局部。"""
        return self._metrics_at(clip, u)[4:]

    def lie_span(self) -> tuple[float, float]:
        """趴着（Lie_belly_loop_1 第一帧）身子往后、往前各占多长（米，从根量，连皮毛和尾巴）：歇在狗屋门口留多远按它算（widget/things.py）。
        按蒙皮后的网格量（每 7 个顶点取一个，几毫秒），这个模型量一次记着（记在模型上）；没有这个片段按站着的身长对半。"""
        return measured(self.model, "lie_span", self._measure_lie_span)

    def _measure_lie_span(self) -> tuple[float, float]:
        clip = "Lie_belly_loop_1"
        if clip not in self.model.clips:
            return (0.5 * self.body_length + 0.1, 0.5 * self.body_length + 0.1)
        p = Player(self.model)
        p.play(clip, loop=False, fade=0.0)
        p.update(0.0)
        J = p.joint_matrices_from(p.globals(IDENTITY))
        mesh = self.model.mesh
        P, Jn, W = mesh.positions, mesh.joints, mesh.weights
        lo, hi = 0.0, 0.0
        for v in range(0, mesh.vertex_count, 7):
            x, y, z = P[3 * v], P[3 * v + 1], P[3 * v + 2]
            pz = 0.0
            for q in range(4):
                w = W[4 * v + q]
                if w:
                    m = J[int(Jn[4 * v + q])]
                    pz += w * (m[2] * x + m[6] * y + m[10] * z + m[14])
            lo, hi = min(lo, pz), max(hi, pz)
        return (-lo, hi)

    def tail_curl(self, behind_m: float, toward_camera: bool = True) -> float:
        """趴在窝里（四分之三朝右）尾巴要往身子这边卷多少（expr.curl，0 … 1），尾巴尖才在根后面 behind_m 米以内（画面上横着量：窝的内沿）。
        量的是趴着的循环里尾巴甩得最远的那一帧（tail_worst，按模型量一次；第一帧最短，边牧甩开以后能到 0.64 米）。
        toward_camera：往靠镜头那一侧卷（绕在近处的后腿边上），否则往远的那一侧。不卷就够的 0；卷到底也不够、卷了也收不回多少的 0，收得回的 1。
        按模型、behind_m、哪一侧记着（gltf.measured），一个窝一种狗只量一次（二分 6 步，几毫秒）。"""
        side = -1.0 if toward_camera else 1.0                    # 朝右歇着：模型的 −X 那一侧靠镜头
        return measured(self.model, ("tail_curl", round(behind_m, 3), side), lambda: self._measure_tail_curl(behind_m, side))

    def tail_worst(self) -> tuple[str, float]:
        """趴着的那几段循环（Lie_belly_loop_1、哈欠的 _2）里尾巴往身后甩得最远的那一刻：(片段, 进度)。按模型量一次（kits.warm 后台先量好）。"""
        def worst() -> tuple[str, float]:
            best = ("Lie_belly_loop_1", 0.0, -1.0)
            for clip in ("Lie_belly_loop_1", "Lie_belly_loop_2"):
                if not dict.__contains__(self.model.clips, clip):
                    continue
                for k in range(TAIL_SAMPLES):
                    u = k / TAIL_SAMPLES
                    d = self._tail_behind_at(clip, u, 0.0, -1.0)
                    if d > best[2]:
                        best = (clip, u, d)
            return best[:2]
        return measured(self.model, "tail_worst", worst)

    def tail_behind(self, curl: float, side: float) -> float:
        """趴着、尾巴往模型的 side（±X）那一侧卷 curl 时，尾巴（蒙皮后主要跟着尾巴骨头的那些顶点）在根后面伸出多远（米，朝右歇着、画面上横着量）：
        趴着的循环里甩得最远的那一刻（tail_worst）。"""
        clip, u = self.tail_worst()
        return self._tail_behind_at(clip, u, curl, side)

    def _tail_behind_at(self, clip: str, u: float, curl: float, side: float) -> float:
        verts = measured(self.model, "tail_verts", self._tail_verts)
        if not verts or not dict.__contains__(self.model.clips, clip):
            return 0.0
        from widget.expression import Expression
        e = Expression()
        e.cur["curl"], e.curl_side = curl, side
        p = Player(self.model)
        p.play(clip, loop=False, fade=0.0)
        p.time = u * self.model.clips[clip].duration
        p.rot_offset = self.expr_rig.offsets(e)
        p.update(0.0)
        J = p.joint_matrices_from(p.globals(IDENTITY))          # 蒙皮矩阵是相对网格节点的：根的旋转在这里抵掉，朝向自己转（下面 ca、sa）
        a = math.radians(90.0 + 330.0)                            # 朝右歇着（四分之三）：模型的 +Z 转到画面的右前方
        ca, sa = math.cos(a), math.sin(a)
        mesh = self.model.mesh
        P, Jn, W = mesh.positions, mesh.joints, mesh.weights
        low = 0.0
        for v in verts:
            x, y, z = P[3 * v], P[3 * v + 1], P[3 * v + 2]
            px = pz = 0.0
            for q in range(4):
                w = W[4 * v + q]
                if w:
                    m = J[int(Jn[4 * v + q])]
                    px += w * (m[0] * x + m[4] * y + m[8] * z + m[12])
                    pz += w * (m[2] * x + m[6] * y + m[10] * z + m[14])
            low = min(low, px * ca + pz * sa)
        return -low

    def _tail_verts(self) -> list[int]:
        """网格里主要跟着尾巴骨头（Tail_01～05）的那些顶点（每 5 个取一个：尾巴尖那一圈照样取得到，量一个姿势约 1 毫秒）。"""
        names = [n.name for n in self.model.nodes]
        tail_nodes = {i for i, n in enumerate(names) if n.startswith("Tail_")}
        tail_joints = {j for j, node in enumerate(self.model.skin_joints) if node in tail_nodes}
        mesh = self.model.mesh
        out = []
        for v in range(0, mesh.vertex_count, 5):
            weights = [mesh.weights[4 * v + q] for q in range(4)]
            q = max(range(4), key=lambda k: weights[k])
            if int(mesh.joints[4 * v + q]) in tail_joints:
                out.append(v)
        return out

    def _measure_tail_curl(self, behind_m: float, side: float) -> float:
        straight = self.tail_behind(0.0, side)
        if straight <= behind_m:
            return 0.0
        full = self.tail_behind(1.0, side)
        if full > behind_m:
            return 1.0 if straight - full >= CURL_WORTH_M else 0.0   # 卷到底也不够：卷了能收回来一截才卷（萨摩耶卷在背上的尾巴卷了也只收 1 厘米，不动它）
        lo, hi = 0.0, 1.0
        for _ in range(6):                                       # 二分：够用就再少卷一点
            mid = (lo + hi) / 2
            if self.tail_behind(mid, side) <= behind_m:
                hi = mid
            else:
                lo = mid
        return round(hi, 3)

    @property
    def planted_hind(self) -> float:
        """站着时后脚骨离地多高（米）：后脚踩在平面上就是这个高度。"""
        return self.foot_metrics("Idle_1", 0.0)[0]

    def _feet_at(self, clip: str, k: int) -> tuple[float, float, float, float, float, float]:
        key = (clip, k)
        if key not in self._feet:
            p = Player(self.model)
            p.play(clip, loop=False, fade=0.0)
            p.time = self.model.clips[clip].duration * k / FEET_STEPS
            p.update(0.0)
            g = p.globals(IDENTITY)

            def avg(ids, col):
                return sum(g[i][col] for i in ids) / max(1, len(ids))
            pelvis = g[self._pelvis]
            self._feet[key] = (avg(self._hind_feet, 13), avg(self._hind_feet, 14), avg(self._front_feet, 13), avg(self._front_feet, 14),
                               pelvis[13], pelvis[14])
        return self._feet[key]

    # ---- 接管 / 交回 ----
    def puppet_begin(self) -> None:
        """roam 接管：正在做的一刀切（会融就融），排着的都不要了；不站着就先由 roam 等站起来（puppet_stand）。
        站在转台上（看细节）的转台姿势也变成站着（那一页的站 / 坐 / 趴跟着亮「站」）：被拎、被扔、掉下去都是站着的。"""
        if self.puppet:
            return
        self._interrupt_action()
        self.steps, self.jump_queue, self.waking = [], 0, False
        self.puppet = True
        self.action_at = math.inf
        if self.on_turntable:
            self.turntable_pose = "standing"

    def puppet_stand_needed(self) -> bool:
        """接管时狗不是站着（坐着、趴着）：roam 先让它站起来再跑。"""
        return self.posture != "standing" or self.transition

    def puppet_stand(self) -> None:
        """站起来（播退出片段）。puppet 期间 _update_play 只推进过渡片段和转身。"""
        if self.posture != "standing":
            self.posture = "standing"
            self._switch_plan(POSTURE_PLANS["standing"])

    def puppet_end(self) -> None:
        """交回：站着待机，随机动作重新计时；朝向由 roam 先转好（home 朝向）。还没转完的平滑转身交给一刀切的滑回接着转。"""
        if not self.puppet:
            return
        self.puppet = False
        if self._spin is not None:
            start, delta, _, _ = self._spin
            self.settle.yaw = (self.yaw, (start + delta) % 360.0, 0.0)
            self._spin = None
        self.queue, self.transition = [], False
        self.turn = None
        self.head_pitch_target = 0.0
        self.posture = "standing"
        self.lounge = None                   # 交回来是站着的：牵走之前记着的歇法作废，playground._lounge 下一帧照现在的钟重新定（萨摩耶坐着走去窝、半路被叫停的）
        if self.plan is not POSTURE_PLANS["standing"]:
            self.plan = POSTURE_PLANS["standing"]
        self.action_at = self.t + self.rng.uniform(*temper.action_every(self.tune))
        self._play_next(fade=FADE_CLIP)
        if self.on_turntable and self.turntable_pose not in (None, "standing"):
            self.steps = [PostureStep(self.turntable_pose)]         # 牵着的时候点了坐 / 趴（看细节那一页）：交回来再换过去

    # ---- 动作 ----
    def puppet_play(self, clip: str, loop: bool = False, speed: float = 1.0, fade: float = FADE_CLIP, restart: bool = True,
                    at: float = 0.0) -> None:
        self.queue, self.transition = [], False
        self.player.play(clip, loop=loop, fade=fade, speed=speed, restart=restart)
        if at > 0.0 and (restart or self.player.name != clip):
            self.player.time = at * self.model.clips[clip].duration

    def puppet_speed(self, speed: float) -> None:
        self.player.speed = speed

    def puppet_face(self, yaw: float, seconds: Optional[float] = None) -> None:
        """平滑地转到 yaw（不播转身片段）：差得多（超过 100°）走经过镜头正前方的那条路，不背对你转；seconds 不给按角度定。"""
        d = _wrap(yaw - self.yaw)
        if abs(d) < 0.5:
            return
        if abs(d) > 100.0:
            d = self._front_delta(yaw % 360.0)
        self.settle.yaw = None
        self.turn = None
        self._spin = (self.yaw, d, 0.0, seconds if seconds is not None else TURN_BASE + TURN_PER_180 * abs(d) / 180.0)

    @property
    def puppet_turning(self) -> bool:
        return self.turn is not None or self.settle.yaw is not None or self._spin is not None

    def _update_puppet(self, dt: float) -> None:
        """puppet 期间每帧：平滑转身（两头慢）、滑回、转身片段（朝向和控制器自己转时同一条曲线，TurnState.yaw_now）、站起来的过渡片段；别的都不做。"""
        self._settle_cut(dt)
        if self._spin is not None:
            start, delta, elapsed, total = self._spin
            elapsed += dt
            u = min(1.0, elapsed / total)
            self.yaw = (start + delta * _ease(u)) % 360.0
            self._spin = None if u >= 1.0 else (start, delta, elapsed, total)
        if self.turn is not None:
            t = self.turn
            t.elapsed += dt
            self.yaw = t.yaw_now()
            if t.elapsed >= t.duration:
                self.yaw = t.target
                self.turn = None
            return
        if self.transition:
            self._advance_transition()
