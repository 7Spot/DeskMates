"""狗的控制器：姿势 / 动作 → 片段计划 → 每一帧的根节点矩阵和关节矩阵。

狗永远在窗口正中（走动类动作都是原地踏步）；姿势、跳、随机动作、表盘动作、一刀切、头带身体在 widget/play.py（PlayMixin）。
这里是两边共用的底子：
- 换计划（_switch_plan）：先播上一个计划的 exit 片段（提速、播到七成就让下一段淡入），再按顺序播 enter 片段，再在 loop 里随机挑着循环播；
  进入片段相同的两个计划是同一个基础姿势，直接淡入；趴睡 / 侧睡叠在趴 / 侧躺上（Plan.base）。
- 转身（_start_turn / _advance_turn）：用模型的转身片段，片段多长转多久；180° 挑中途背对镜头的那边。跟鼠标的转身放快（turn_speed）、
  一开始就动（TurnState.follow），腿是待机或刚转完的样子时只淡入 FOLLOW_TURN_FADE（脚少在地上滑）；动作里的转身原速、两头慢。
- 鼠标跟随：set_look_target() 给一个世界坐标点，头、脖子、眼睛的旋转由 widget/gaze.py 算，每帧叠到采样结果上（站在转台上看细节时不看，头摆正）。
- 小表情（widget/expression.py）：眯眼、耳朵、摇尾巴、歪头、身子一缩 / 压低，叠在鼠标跟随之后；灵动交互在用（摇尾巴、等你扔球时压低身子）。
- 灵动交互里跑去捡球、跳窗口时由 widget/roam.py 牵着走（puppet，widget/locomotion.py）：这期间自己的事都停。
- 转身片段自带很大的甩头（90° 片段头偏 60°，180° 片段最多 114°），有鼠标目标时转身期间把头和脖子的动画旋转淡成绑定姿势
  （Player.base_blend），头完全由跟随决定，转身时也实时盯着鼠标。
- 窗口要多高：每段片段的最高关节预先算好（懒加载），加耳朵的余量，起跳再加抛物线高度；window.py 按 posture_tops()（站、坐、趴、睡和它们的过渡片段里
  最高的：换姿势时窗口不改大小）和 stance_top()（再算上正在播、排着的）临时长高缩回。悬停菜单按钮的高度用 rest_top()：当前姿势的循环片段的最高点，
  跳、随机动作、呼吸都不动它；看细节放大时按 stance_top() 看头顶放不放得下、挡不挡卡片。
坐标：米。模型里狗朝 +Z，根节点矩阵把它转成朝 +X 再加 yaw。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

from widget import temper
from widget.anim import Player, axis_angle, qmul
from widget.excite import Excite
from widget.expression import Expression, ExpressionRig, merge as merge_offsets
from widget.clips import FADE_CLIP, FADE_STATE, LOOKS_AROUND, POSTURE_PLANS, QUARTER_POSES, RARE, SLEEP_PLANS, TURN_180, TURN_90, Jump, Plan, jumps_for
from widget.gaze import Gaze
from widget.geometry import FOOT_REST
from widget.gltf import IDENTITY, Mat4, Model, Quat, Vec3, mat_mul, rot_x_mat, rot_y_mat, table, transform_point, trs
from widget.lift import Lift
from widget.locomotion import LocomotionMixin
from widget.play import BODY_TURN_COOLDOWN, FOLLOW_TURN_FADE, TURN_SPEED, PlayMixin, TurnState, _wrap
from widget.props import Props

MESH_MARGIN = 0.11                                 # 最高关节到耳朵尖（米）
HEAD_FREE_IN, HEAD_FREE_OUT = 0.08, 0.20           # 头脱离片段动作的淡入 / 淡出时间常数（秒）
HEAD_FREE_TRACKING = 0.5                           # 有鼠标目标时头脖子的片段动作压到一半；转身时压到零
BODY_CENTER = 0.40                                 # 俯仰绕身体中心转：离地面这么高（米）
EXIT_SPEED, ENTER_SPEED, EXIT_CUT, CUT_FADE = 1.4, 1.2, 0.7, 0.4   # 姿势切换提速：退出片段 1.4 倍速、播到七成就让进入片段（1.2 倍速）淡入 0.4 秒
HEAD_PITCH_TAU = 0.07                                              # 头的附加俯仰（嗅）往目标值走的时间常数：切掉时 0.2 秒抬回，不弹


@dataclass(frozen=True)
class Pose:
    root: Mat4                            # 根矩阵（位置 + 朝向），着色器的 uModel
    joints: list[Mat4]                    # 蒙皮矩阵，按 skin 顺序
    world: list[Mat4]                     # 每个节点的世界矩阵（不含根矩阵，和 joints 一致）
    footprint: list[tuple[float, float]]  # 身体各关节投到地面的 (x, z)（米，含根矩阵），画阴影用
    lift: float                           # 四脚离地高度（米），跳起来时 > 0
    props: tuple = ()                     # 这一帧要画的道具零件（widget/props.py 的 PropDraw：盆 / 骨头 / 球）


def _translate(x: float, y: float, z: float) -> Mat4:
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


class DogController(PlayMixin, LocomotionMixin):
    def __init__(self, model: Model, seed: Optional[int] = None):
        self.model = model
        self.rng = random.Random(seed)
        self.tune = None             # 调参（window 接上）：转身的那几个数、性子（widget/temper.py）每次读，改了马上生效
        self.auto_turn = True        # 身体跟不跟着鼠标转：绑在灵动交互上，没有开关（window._apply_modes）；放 __init__ 里，换片段 / 换姿势的重置不碰它
        self.player = Player(model, seed=seed)
        self.x, self.z, self.yaw = 0.0, 0.0, QUARTER_POSES[0]
        self.plan: Optional[Plan] = None
        self.queue: list[tuple[str, float, float]] = []   # 排着的过渡片段：(片段, 速度, 播到几成就接下一段)
        self._cut_at = 1.0           # 当前过渡片段播到几成算完
        self.transition = False      # 正在播退出 / 进入片段
        self.turn: Optional[TurnState] = None   # 转身片段进行中
        self._fade_after_turn: Optional[list] = None   # 转完淡回待机的那一段交叉淡入（player.prev 那份快照）：认得出它，马上往回转也能淡入短的
        self.head = model.node_by_name("head").index
        self.neck = model.node_by_name("neck").index
        self.chest = model.nodes[self.neck].parent      # 脖子的父骨（胸椎）：跟随以它的实时朝向为基准
        self.eyes = {n: model.node_by_name(n).index for n in ("eye.L", "eye.R")}
        self.mouth_bones = [i for i in (model.node_index(n) for n in ("mouth", "Mouth.L", "Mouth.R", "tongue_1", "tongue_2", "tongue_3", "tongue_4")) if i is not None]   # 闭嘴用：拉回绑定姿势（clips 的 mouth=False）
        self.shut_mouth = False      # 灵动交互：俯身时闭嘴（Idle_5 自带叫）
        self.hide_shadow = False     # 灵动交互：被扔在空中时没有影子（拎着的时候 lift 管）
        self.perch = 0.0             # 灵动交互：根再抬多高（米）——歇在狗窝里、踩着狗窝走过时是垫子的高度（playground 缓过去、缓回来），平时 0；抬着的时候不画影子（frame）
        names = [n.name for n in model.nodes]
        self.feet = [i for i, n in enumerate(names) if n.startswith(("foot_", "claws_"))]
        joints = set(model.skin_joints)
        self.body = [i for i in range(len(model.nodes)) if i in joints and model.nodes[i].parent in joints]   # 身子的骨头（最高点、影子用）：蒙皮的关节、父节点也是蒙皮的关节——网格节点、骨架节点、根骨都不算；按蒙皮认，不按节点名（每个模型的名字不一样）
        self.gaze = Gaze()
        self.look_target: Optional[Vec3] = None
        self.body_target: Optional[Vec3] = None   # 灵动交互：身子跟着这个点转（头看着球时是球，不然是鼠标；window._look_target）；None 就按 look_target
        self.head_pitch = 0.0                # 实际叠在头上的俯仰（度），每帧往 head_pitch_target 走
        self.head_pitch_target = 0.0
        self._last: Optional[tuple[Mat4, list[Mat4]]] = None   # 上一帧的 (根矩阵, 世界矩阵)，鼠标跟随用
        self._last_min_foot: Optional[float] = None             # 上一帧最低的脚（世界坐标），落地时贴地用
        self.t = 0.0
        self._init_play()                    # 互动模式的状态（widget/play.py）
        self._init_locomotion()              # 灵动交互里被 roam 牵着走（widget/locomotion.py）
        self._rare_next: dict[str, float] = {}   # 稀有片段下次允许播的时间
        self._head_free = 0.0                # 头脱离片段动作的程度（转身时 → 1）
        self.jumps = jumps_for(model)        # 五种跳法；模型包改过腾空区间的（pack.json 的 jumps）用它自己的
        self._land_foot0 = {j.land: self._foot_at_start(j.land) for j in self.jumps if j.land}
        self.bind = self.player.globals(IDENTITY)   # 绑定姿势的世界矩阵（不含根矩阵）
        nose, tail = model.node_by_name("nose").index, model.node_by_name("Tail_01").index
        self.body_length = abs(self.bind[nose][14] - self.bind[tail][14])   # 鼻尖到尾根（米）：头带身体的换向距离按它算
        self.bind_local = {i: trs(n.translation, n.rotation, n.scale) for i, n in enumerate(model.nodes)}   # 绑定姿势的局部矩阵
        self._clip_tops: dict[str, float] = table(model, "clip_tops")   # 片段 → 最高点：记在模型上，同一个模型的控制器共用（gltf.Model.measured）
        self.required = 0.75                  # 当前要画到地面以上多高（米），窗口按它长高缩回
        self.props = Props(model)             # 盆 / 骨头 / 球：按正在播的片段出现（widget/props.py）
        self.excite = Excite()                # 此刻有多兴奋（widget/excite.py：窗口每帧按状态推，尾巴跟着它）
        self.expr = Expression()              # 程序叠的小表情：眯眼、耳朵、摇尾巴、歪头、压低、duang（widget/expression.py；灵动交互在用）
        self.expr_rig = ExpressionRig(model)
        self.lift = Lift(model)               # 被拎起来：肚子提起来、四腿垂着（widget/lift.py；灵动交互在用）

    def clip_top(self, clip: str) -> float:
        """这段片段里身体最高的关节（米）加耳朵余量。这个模型第一次问到时算，之后记着（记在模型上）。"""
        if clip not in self._clip_tops:
            c = self.model.clips[clip]
            p = Player(self.model)
            p.play(clip, loop=False, fade=0.0)
            top = 0.0
            n = max(6, int(c.duration * 12))
            for i in range(n + 1):
                p.time = c.duration * i / n
                p.update(0.0)
                g = p.globals(IDENTITY)
                top = max(top, max(g[j][13] for j in self.body))
            self._clip_tops[clip] = top + MESH_MARGIN
        return self._clip_tops[clip]

    def _update_required(self) -> None:
        name = self.player.name
        if self.jump is not None:
            j: Jump = self.jump.j
            parts = [j.whole] if j.whole else [j.start, j.air, j.land]
            self.required = max(self.clip_top(c) for c in parts if c) + self.jump.h
        elif name:
            self.required = self.clip_top(name) + self.y_offset + self.perch

    def rest_top(self) -> float:
        """现在这个姿势 / 状态的循环片段里身体最高点（米，含耳朵余量），取循环里最高的那段。悬停菜单按钮按它定高度：
        跳、随机动作、呼吸都不动它，换姿势、换状态才变。"""
        if self.plan is None:
            return self.required
        return max(self.clip_top(c) for c in self.plan.loop) + self.perch

    def posture_tops(self) -> tuple[float, float]:
        """站、坐、趴、睡这几个姿势里最高到哪（米，垫子抬着的也算上）：(循环片段里最高的, 再算上起身、坐下、趴下这些过渡片段里最高的)。
        窗口按它留高度（window._needed_height、hover.min_height）：换姿势时窗口不用改大小（真机上 Metal 窗口改一次大小，
        主线程要等 40～95 毫秒，起身一开头就卡一下）。按模型量一次记着（片段的最高点本来就记着）。"""
        tops = table(self.model, "posture_tops")
        if "rest" not in tops:
            plans = list(POSTURE_PLANS.values()) + list(SLEEP_PLANS.values())
            have = self.model.clips
            tops["rest"] = max(self.clip_top(c) for p in plans for c in p.loop if c in have)
            tops["all"] = max([tops["rest"]] + [self.clip_top(c) for p in plans for c in p.enter + p.exit if c in have])
        return tops["rest"] + self.perch, tops["all"] + self.perch

    def stance_top(self) -> float:
        """这一阵最高到哪（米）：这个姿势的循环片段、正在播的、排着的过渡片段里最高的（垫子抬着的也算上）。换姿势时过渡片段一开始就全排好了，
        所以站起来的那一段也算在里面：窗口按它长高（window._needed_height，起身前一次长够），看细节放大着拖狗时按它算头顶出不出屏幕。"""
        return max([self.rest_top(), self.required] + [self.clip_top(c) + self.perch for c, _, _ in self.queue])

    def _foot_at_start(self, clip: str) -> float:
        p = Player(self.model)
        p.play(clip, loop=False, fade=0.0)
        p.update(0.0)
        g = p.globals(IDENTITY)
        return min(g[i][13] for i in self.feet)

    # ---------- 换计划 ----------
    def _switch_plan(self, plan: Plan, fade: float = FADE_STATE) -> None:
        """换计划：先播旧计划的 exit 片段（提速、播到七成），再播新计划的 enter 片段，再循环。
        进入片段相同的两个计划是同一个基础姿势：直接淡入，不起身再趴下。"""
        old = self.plan
        self.plan = plan
        if old is not None and old.enter == plan.enter:
            self.queue = []                                       # 同一个基础姿势：不起身
        else:
            outs = list(old.exit) if old is not None else []
            ins = list(plan.enter)
            nb = POSTURE_PLANS[plan.base] if plan.base else None           # 要去的是叠在某个姿势上的一层（睡叠在趴上）
            ob = POSTURE_PLANS[old.base] if (old is not None and old.base) else None   # 从叠着的那层离开
            if nb is not None:
                if old is not None and old.enter == nb.enter:
                    outs = []                                             # 已经趴着：直接入睡
                else:
                    ins = list(nb.enter) + ins                            # 站着 / 坐着：退出它、趴下、入睡
            if ob is not None:
                if plan.enter == ob.enter:
                    ins = []                                              # 睡 → 趴：只播醒来
                else:
                    outs = outs + list(ob.exit)                           # 睡 → 站 / 坐：醒来 + 起身 + 新的进入
            self.queue = [(c, EXIT_SPEED, EXIT_CUT) for c in outs] + [(c, ENTER_SPEED, 1.0) for c in ins]
        self.turn = None
        self.head_pitch_target = 0.0
        self._reset_rare(plan.loop)
        self._play_next(fade=fade)

    def set_look_target(self, target: Optional[Vec3]) -> None:
        """狗看向世界坐标里的这个点；None 就慢慢看回前方。正播着头自己张望的那段（坐着的 Sitting_loop_2）、头又要看东西：交叉淡到不张望的那段。"""
        self.look_target = target
        if (target is not None and self.player.name in LOOKS_AROUND and not self.transition and not self.puppet
                and self.action is None and not self.queue):
            self._play_next()

    def head_twist(self) -> float:
        """头实际朝向和身体朝向的夹角（度，正 = 头往左扭）。用上一帧头骨的世界矩阵算，和待机片段自带的转头、跟随伺服的补偿都无关，
        看的就是画面上头歪了多少。"""
        if self._last is None:
            return 0.0
        root, g = self._last
        m = mat_mul(root, g[self.head])
        fx, fz = m[4], m[6]                      # 头骨局部 +Y 是朝前，取它在世界里的 x、z 分量
        if abs(fx) < 1e-6 and abs(fz) < 1e-6:
            return 0.0
        head_yaw = math.degrees(math.atan2(-fz, fx))   # 和身体 yaw 同一套约定：朝向 = (cos yaw, 0, -sin yaw)
        return _wrap(head_yaw - self.yaw)

    def head_position(self) -> Optional[Vec3]:
        """上一帧头骨的世界位置（米）。"""
        if self._last is None:
            return None
        root, g = self._last
        m = g[self.head]
        return transform_point(root, (m[12], m[13], m[14]))

    def _apply_gaze(self, dt: float) -> None:
        """把鼠标跟随的旋转叠到头、脖子、眼睛上，再加上状态自带的头部俯仰。
        给 gaze 的基准是：胸椎的实时朝向（上一帧动画后的，脊椎怎么扭都算进去）· 绑定脖子 · 绑定头，位置用动画后的。
        前馈，不和片段的头部动作打架。有目标时头脖子自己的片段动作压到一半，转身片段期间压到零，头完全由跟随决定。
        头有自己的戏的动作（clips.Action.gaze = False：低头嗅、吃喝、刨土……）做的时候不喂目标，头 0.3 秒看回前方，做完再看回鼠标。"""
        target = self.look_target if (self.action is None or self.action.gaze) else None
        if self.posture == "sleeping" or self.on_turntable:
            target = None                                               # 睡着不看鼠标；站在转台上（看细节）头摆正，头和脖子的毛色看得清
        if target is None:
            free = 0.0
        elif self.turn is not None:
            free = 1.0
        else:
            free = HEAD_FREE_TRACKING
        tau = HEAD_FREE_IN if free > self._head_free else HEAD_FREE_OUT
        self._head_free += (free - self._head_free) * (1.0 - math.exp(-dt / tau))
        blend = {self.head: self._head_free, self.neck: self._head_free} if self._head_free > 1e-3 else {}
        shut = self.shut_mouth or (self.action is not None and not self.action.mouth)
        if shut:                                                        # 闭嘴：模型的伏地 / 伏低片段自带叫（伏地伸展不该叫）
            blend.update({i: 1.0 for i in self.mouth_bones})
        self.player.base_blend = blend
        if self._last is None:
            quats = self.gaze.update(dt, None)
        else:
            root, g = self._last

            chest = mat_mul(root, g[self.chest])
            neck_m = mat_mul(chest, self.bind_local[self.neck])
            head_m = mat_mul(neck_m, self.bind_local[self.head])

            def frame(m: Mat4, i: int) -> Mat4:
                p = transform_point(root, (g[i][12], g[i][13], g[i][14]))
                return m[:12] + (p[0], p[1], p[2], 1.0)
            quats = self.gaze.update(dt, target, frame(head_m, self.head), frame(neck_m, self.neck),
                                     frame(mat_mul(head_m, self.bind_local[self.eyes["eye.L"]]), self.eyes["eye.L"]),
                                     frame(mat_mul(head_m, self.bind_local[self.eyes["eye.R"]]), self.eyes["eye.R"]),
                                     quick=self.turn is not None)
        offsets: dict[int, Quat] = {}
        head_q = quats.get("head")
        if self.head_pitch:
            pitch_q = axis_angle((1, 0, 0), self.head_pitch)
            head_q = qmul(pitch_q, head_q) if head_q else pitch_q
        if head_q:
            offsets[self.head] = head_q
        if "neck" in quats:
            offsets[self.neck] = quats["neck"]
        for name, idx in self.eyes.items():
            if name in quats and idx != self.head:                      # idx 是头：这个模型没有眼睛骨头（widget/packs.py 的 BONE_FALLBACK）
                offsets[idx] = quats[name]
        out = merge_offsets(offsets, self.expr_rig.offsets(self.expr))
        if self.lift.on:
            out = merge_offsets(out, self.lift.offsets())
        self.player.rot_offset = out

    def _play_next(self, fade: float = FADE_CLIP) -> None:
        plan = self.plan
        self._cut_at = 1.0
        if self.queue:
            clip, speed, cut = self.queue.pop(0)
            self.transition = True
            self._cut_at = cut
            self.player.play(clip, loop=False, fade=fade, speed=speed)
            return
        self.transition = False
        loops = self._loop_choices(plan)
        if len(loops) == 1:
            self.player.play(loops[0], loop=True, fade=fade, restart=self.player.name != loops[0])
        else:
            self.player.play(self._pick(loops), loop=False, fade=FADE_CLIP)

    def _advance_transition(self) -> None:
        """过渡片段播完、或退出片段到了提前切的点，就接下一段（提前切时交叉淡入长一点）。"""
        if self.player.finished:
            self._play_next()
        elif self._cut_at < 1.0 and self.player.progress >= self._cut_at:
            self._play_next(fade=CUT_FADE)

    def _reset_rare(self, clips) -> None:
        for c in clips:
            if c in RARE:
                self._rare_next[c] = self.t + self.rng.uniform(*RARE[c])

    def _loop_choices(self, plan: Plan) -> tuple[str, ...]:
        """这个姿势这会儿能挑哪几段循环：头在看东西（鼠标跟随、灵动交互里看球）时不挑头自己张望的那段（clips.LOOKS_AROUND，坐着的 Sitting_loop_2）。"""
        loops = plan.loop
        if self.look_target is not None and len(loops) > 1:
            loops = tuple(c for c in loops if c not in LOOKS_AROUND) or loops
        return loops

    def _pick(self, clips) -> str:
        """随机挑一段，但 RARE 里的只在到点时播（播了就重排下次），其余时候只在普通片段里挑。"""
        due = [c for c in clips if c in RARE and self.t >= self._rare_next.get(c, 0.0)]
        if due:
            name = due[0]
            self._rare_next[name] = self.t + self.rng.uniform(*RARE[name])
            return name
        common = [c for c in clips if c not in RARE] or list(clips)
        return self.rng.choice(common)

    # ---------- 每帧 ----------
    def update(self, dt: float) -> None:
        if self.plan is None:
            return
        self.t += dt
        if self.head_pitch != self.head_pitch_target:              # 嗅的低头 / 切掉后抬回：平滑过去，不弹
            d = self.head_pitch_target - self.head_pitch
            self.head_pitch = self.head_pitch_target if abs(d) < 0.05 else self.head_pitch + d * (1.0 - math.exp(-dt / HEAD_PITCH_TAU))
        self.expr.update(dt)
        self.lift.update(dt, 1.0 if math.cos(math.radians(self.yaw)) >= 0.0 else -1.0)
        self._apply_gaze(dt)
        self.player.update(dt)
        self._update_play(dt)
        self._update_required()
        self.props.update(dt, self.player.name, self.player.progress, self.root_matrix(),      # 道具看这一帧定下来的片段，不滞后
                          self._last[1][self.head] if self._last is not None else None, self.yaw)

    def _start_turn(self, delta: float) -> None:
        """转 delta 度：正 = 向左（朝远离镜头的方向转），用模型的转身片段，片段多长就转多久。
        180° 时挑让中途朝向远离镜头的那边，不会正脸怼着屏幕转。
        跟鼠标的转身（auto_turn 开着、不在动作里；灵动交互里转向 home 也算）：片段放快 turn_speed 倍，朝向一开始就动（TurnState.follow），
        腿是待机的样子（没在淡入别的）或刚转完 180° 正淡回待机（马上往回转）、这次也是 180° 时只淡入 FOLLOW_TURN_FADE：这两种和 180° 片段第一帧只差 0～5 厘米；
        90° 的片段（Turn_L_IP / Turn_R_IP）首尾的前爪离待机、离 180° 片段 18～20 厘米，跟鼠标转也照旧淡入长的。
        正从别的姿势淡过来（这次转身就是切掉动作转的、roam 刚交回、起身起到七成就接了待机）照旧淡入 FADE_CLIP / 速度：
        从伏地、刨土、跑这些姿势 0.08 秒弹到转身会跳一下。只认这两种、别的都算「别的姿势」，以后加了新的淡入也不会误用短的。
        动作里的转身（捡回）原速、两头慢。"""
        if abs(delta) == 180.0:
            mid_left = math.sin(math.radians(self.yaw + 90))     # 向左转中途的朝向：sin>0 表示背对镜头
            delta = 180.0 if mid_left >= 0 else -180.0
        if self.settle.yaw is not None:                           # 刚被切、朝向还在滑回：剩下的角度并进这次转身，不跳变
            delta += _wrap(self.settle.yaw[1] - self.yaw)
            self.settle.yaw = None
        side = "L" if delta > 0 else "R"
        clip = (TURN_180 if abs(delta) > 100.0 else TURN_90)[side]
        follow = self.auto_turn and self.action is None           # 跟鼠标的转身；动作里的转身（捡回）不变
        speed = (self.tune["turn_speed"] if self.tune is not None else TURN_SPEED) * temper.turn_pace(self.tune) if follow else 1.0   # 活跃度低的转得慢一点（边牧 × 1）
        from_rest = clip in TURN_180.values() and (self.player.prev is None or self.player.prev is self._fade_after_turn)
        fade = FOLLOW_TURN_FADE if follow and from_rest else FADE_CLIP / speed
        self.player.play(clip, loop=False, fade=fade, speed=speed)
        self.turn = TurnState(self.yaw, delta, self.model.clips[clip].duration / speed, follow=follow)

    def _advance_turn(self, dt: float) -> None:
        t = self.turn
        t.elapsed += dt
        self.yaw = t.yaw_now()
        if t.elapsed >= t.duration:
            self.yaw = t.target
            self.turn = None
            if self.run is None:
                self._cooldown_until = self.t + ((self.tune["turn_rest"] if self.tune is not None else BODY_TURN_COOLDOWN) + temper.turn_rest(self.tune))
            if self.action is not None:
                self._advance_program()           # 动作里的转身：转完接着做下一项
            else:
                finished = self.player.name
                self._play_next(fade=FADE_CLIP)
                # 这段淡回待机是从 180° 片段末尾淡出来的（_start_turn 认它）；90° 的末尾离 180° 片段第一帧太远，不认
                self._fade_after_turn = self.player.prev if finished in TURN_180.values() else None

    # ---------- 输出 ----------
    def root_matrix(self) -> Mat4:
        m = mat_mul(_translate(self.x, self.y_offset + self.perch, self.z), rot_y_mat(90.0 + self.yaw))
        squash = self.expr.squash
        if abs(squash) > 1e-4:                                   # 身子一缩 / 压低 / duang：在地面上竖直压扁（负的是拉长），脚不动
            m = mat_mul(m, (1 + squash * 0.5, 0, 0, 0, 0, 1 - squash, 0, 0, 0, 0, 1 + squash * 0.5, 0, 0, 0, 0, 1))
        if self.pitch:
            # 绕身体中心（离地 BODY_CENTER）转：模型局部 X 是左右轴，正角度鼻子朝下，所以取负
            tilt = mat_mul(_translate(0.0, BODY_CENTER, 0.0), mat_mul(rot_x_mat(-self.pitch), _translate(0.0, -BODY_CENTER, 0.0)))
            m = mat_mul(m, tilt)
        hang = self.lift.matrix()
        if hang is not None:                                     # 拎着：上下浮、绕抓的地方摆
            m = mat_mul(hang, m)
        return m

    def joint_matrices(self) -> list[Mat4]:
        return self.player.joint_matrices()

    def frame(self) -> Pose:
        """这一帧要画的东西，globals 只算一遍。"""
        g = self.player.globals(IDENTITY)
        root = self.root_matrix()
        pts = {i: transform_point(root, (g[i][12], g[i][13], g[i][14])) for i in self.body}
        min_foot = min(pts[i][1] for i in self.feet)
        lift = max(0.0, min_foot - FOOT_REST)
        self._last = (root, g)
        self._last_min_foot = min_foot
        footprint = [] if self.hide_shadow or self.perch > 0.0 or self.lift.w > 0.02 else [(p[0], p[2]) for p in pts.values()]   # 空中没有影子（没有地面）；踩在狗窝的垫子上也不画（影子会落在窝后面的地上）
        return Pose(root, self.player.joint_matrices_from(g), g, footprint, lift, self.props.draw_list(root, g[self.head]))
