"""狗的行为（set_play 启动时进一次）：DogController 的 mixin（class DogController(PlayMixin)），控制器本体在 widget/dogctl.py。
狗按姿势和随机动作过日子，鼠标跟随 / 灵动交互 / 表盘动作都在这里：
- 进入：朝向不是 home（window._home_yaw）就转过去（_face_home）；再进该待的形态。
- 换边（拖过所有屏合起来那块的中线、被系统挪到另一半）一律转身：站着直接转；趴着、坐着起身、转、回原姿势；睡着的醒来、起身、转、
  用同一种睡法睡回去。"不为转向起立"只管开关来回切和鼠标跟随（头带身体：趴着坐着睡着只转头）。
- 灵动交互（set_dynamic）：开着一直站着（不坐不趴），只做站着的随机动作；关掉回到用户选的姿势
  （set_rest_posture：灵动交互关着时立刻生效、一直待着，开着时只记下）。例外（活跃度低的狗，widget/temper.py）：没人理一阵子
  自己坐下、趴下（lounge、set_lounge；什么时候歇、歇成什么由 playground._lounge 定，边牧的 lounge 一直是 None）。歇着时鼠标换了边不起立转身，
  只转头；不做要先站起来的随机动作（坐着不抬爪），趴着的哈欠照旧。点狗（duang）、扔球、拎起来、跳窗口由 widget/playground.py 管
- 姿势 站 / 坐 / 趴 / 睡（睡 = 趴睡或侧睡叠在趴 / 侧躺上，两种轮着来；sleep_state 报 awake / falling / asleep / waking）。
- 五种跳法随机不连重复，速度随机；平跳随抛物线抬头、低头（绕身体中心）。整段片段从腾空前一点开始播。
- 随机动作（clips.ACTIONS 里 default 的，池固定、用户不能选）：每个形态一池，普通的每 8 到 20 秒一个，抬前爪 / 哈欠按 RARE 的间隔；
  坐着趴着的有些要先站起来做、做完回去（via_standing）；转圈那个播片段时身体转一圈。被点击立刻打断去跳。
- 动作表盘（do_action，28 个）：停到哪根做哪个，做完回点之前的姿势，姿势不对先换过去（趴着点前伸：起身 → 前伸 → 趴回去；
  站着点打哈欠：趴下 → 哈欠 → 站起来）。动作的 program（clips.Action）逐项做：片段播一遍、循环几秒、转身、跳一下、头俯仰；
  跳和转身借用跳 / 转身机制，做完接下一项（_advance_program）。
- 打断一刀切（_interrupt_action）：换一根、换姿势、点击起跳，正在做的不管是什么（表盘的、随机的、半空、转到一半、
  换姿势换到一半）都立刻停，下一段 0.3 秒交叉淡入（会融就融）；动作把朝向转走了的，朝向在同样 0.3 秒里滑回动作开始前的角度，
  不播转身片段；半空的高度和俯仰 0.3 秒落回。同一根再点立刻重来（单段循环的不重播片段，只延长、重置进度条）。
- 头带身体（固定两个朝向）：站着跟随鼠标时身体只在头朝左 210° / 头朝右 330° 之间切，鼠标过到另一边、离狗中心
  超过 turn_reach 个身长、持续 turn_delay 秒、不在 turn_rest 冷却里（开发者设置页；没接调参时用下面的 BODY_* / TURN_SPEED），就中断当前动作并转过去，
  一开始就动、末尾停稳（TurnState.follow → _ease_quick_start）；中间那段只转头；趴着坐着不转身。
  捡回 / 转圈等动作自己的转向不改变鼠标换侧的判断基准，内部转身也不触发中断。换屏幕半区同样立即中断，再转向新 home。
- 看细节（set_turntable，只有 widget/closeup.py 开关）：详情页、自定义毛色页开着时狗站在转台上，先站起来（不管在做什么），
  自己的事都停——随机动作、身子跟鼠标 / 球转、换边转身、头看鼠标（dogctl._apply_gaze）；朝向只听转盘（turntable_turn / turntable_return，不播转身片段，
  不过头的弹簧 Turntable），姿势听那一页的站 / 坐 / 趴（set_turntable_pose，turntable_pose），表盘点的动作照做；下来回到该待的姿势（_home_posture）。
  灵动交互那边也看这个开关（Playground.fetch_on：不捡球、不俯身、不出圈；不跳下被盖住的窗口）。

状态是几个有名字的小对象：
- steps：排队要做的事，PostureStep / TurnStep / ActionStep；
- run：正在做的动作（ActionRun：剩下的 program、表盘点的还是随机的、循环到什么时候、转圈、开始前的朝向）；
- jump：半空（JumpState）；turn：转身片段（TurnState，控制器本体也用）；
- manual：表盘点的那整段的进度条（ManualProgress）；settle：一刀切之后 0.3 秒的滑回 / 落回（Settle）；
- _turntable：站在转台上时的朝向弹簧（Turntable；None = 不在转台上）。
每帧的流程（_update_play）：先推进 settle、转台、检查鼠标外部转向；半空 → 推进跳；转身中 → 推进转身；转圈动作转身体；
正在做动作 → 当前项做完开下一项；换姿势的过渡片段播完再说；然后 steps 一步一步做；都闲着：站着的接排着的跳，
再到点来个随机动作。phase 报现在在哪一步。"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Union

from widget.clips import (ACTIONS, ACTIONS_BY_ID, FADE_CLIP, POSTURE_PLANS, QUARTER_POSES, RARE, SLEEP_PLANS, TURN_180,
                          TURN_90, Action, Jump, Plan)
from widget import temper
from widget.geometry import FOOT_REST

# 跟鼠标转身的四个数是开发者设置页 turn_reach / turn_delay / turn_speed / turn_rest 的默认值（widget/tuning.py 读这里，只写这一处），没接调参时直接用
BODY_FLIP_LENGTHS = 0.6                            # 头带身体：鼠标过到另一边、离狗中心超过这么多个身长才转（差不多刚离开狗身：刚好）
BODY_TURN_DEBOUNCE, BODY_TURN_COOLDOWN = 0.0, 0.1  # 要持续这么久才转（0：过线就转）；转完这么久内不再转
TURN_SPEED = 1.35                                  # 跟鼠标转身时片段放快多少：两个朝向之间（120°，用 1 秒的 180° 片段）约 0.77 秒转完
FOLLOW_TURN_FADE = 0.08                            # 跟鼠标转身淡入转身片段多久（秒；别的转身是 FADE_CLIP / 速度，1.35 倍时约 0.22）：淡入期间腿还是原来的样子、
                                                   # 身子已经在转，着地的脚在地上滑。只在 180° 的片段、腿是待机
                                                   # 或刚转完 180° 的样子时用（和 180° 片段第一帧只差 0～5 厘米，短了不会跳）；从别的姿势淡过来（切掉的动作、roam 交回、
                                                   # 起身）、90° 的片段照旧淡入长的：伏地、刨土、跑这些和转身片段第一帧差 18～34 厘米，90° 片段首尾离待机 18～20（dogctl._start_turn）
CHAIN_SPEED, CHAIN_WHOLE_SPEED = 1.5, 1.2          # 连跳时起跳片段 / 整段片段的加速
WHOLE_LEAD = 0.10                                  # 整段片段从腾空前这么多进度开始播，省掉助跑
JUMP_SPEED, JUMP_HEIGHT_VARY = (0.9, 1.1), (0.85, 1.15)
POSTURE_CHANGE, JUMP_SECONDS = 1.3, 1.3            # 估时长用：换一次姿势、跳一下大约多久（表盘的进度条）
CUT_SECONDS = 0.3                                  # 一刀切：下一段的交叉淡入、朝向滑回、半空落回都是这么久
TURNTABLE_FOLLOW_S = 0.12                          # 看细节：转盘尺转了，狗跟上去的弹簧（秒基本到位，不过头）
TURNTABLE_RETURN_S = 0.5                           # 离开那两页：转回该朝的方向
TURNTABLE_DONE_DEG = 1.0                           # 转回来差这么多度以内就下转台，剩下的交给一刀切的滑回（0.3 秒，看不出来；
                                                   # 临界阻尼弹簧的最后 1° 要拖 0.2 秒多，这期间随机动作、捡球都还停着）


def _ease(u: float) -> float:
    """两头慢（余弦）：不跟鼠标的转身（动作里的、灵动交互关着时转向 home）、一刀切之后的滑回、roam 的平滑转身用它。"""
    u = 0.0 if u < 0 else 1.0 if u > 1 else u
    return 0.5 - 0.5 * math.cos(math.pi * u)


def _ease_quick_start(u: float) -> float:
    """一开始就动、末尾停稳（跟鼠标的转身：两头慢的过线后 0.27 秒才转过一成）：三次 Hermite u + u² − u³。
    起步就是平均速度，三分之一处最快（平均的 4/3 倍），停的时候速度到 0；一路单调，不过头、不回弹。"""
    u = 0.0 if u < 0 else 1.0 if u > 1 else u
    return u + u * u - u * u * u


def _wrap(deg: float) -> float:
    """折到 (-180, 180]。"""
    return (deg + 180.0) % 360.0 - 180.0


# ---------- 状态对象 ----------
@dataclass
class TurnState:
    """转身片段进行中：从 start 转 delta 度（正 = 向左），片段多长转多久（duration 已按片段放快的倍数算好）。
    follow：跟鼠标的转身，一开始就动（_ease_quick_start）；别的（动作里的转身、灵动交互关着时转向 home）两头慢（_ease）。
    朝向只按 yaw_now 算：控制器自己转（dogctl._advance_turn）和被 roam 牵着时（locomotion._update_puppet）是同一条曲线。"""
    start: float
    delta: float
    duration: float
    elapsed: float = 0.0
    follow: bool = False

    @property
    def target(self) -> float:
        return (self.start + self.delta) % 360.0

    def yaw_now(self) -> float:
        """按已经过的时间，现在该朝哪（度，0～360）。"""
        ease = _ease_quick_start if self.follow else _ease
        return (self.start + self.delta * ease(self.elapsed / self.duration)) % 360.0


@dataclass
class JumpState:
    """半空：哪种跳法、在哪一段（whole 整段片段 / start 起跳 / air 腾空 / land 落地）、速度、这一跳的高度、腾空进度。"""
    j: Jump
    phase: str
    speed: float
    h: float
    u: float = 0.0


@dataclass
class Spin:
    """转圈动作：片段播多久身体转多久。"""
    start: float
    total: float
    elapsed: float = 0.0


@dataclass
class ActionRun:
    """正在做的一个动作：剩下的 program、是表盘点的还是随机的、开始前的朝向（被切时滑回）、("loop") 这一项循环到什么时候、转圈。"""
    action: Action
    program: list
    manual: bool
    yaw_before: float
    loop_until: Optional[float] = None
    spin: Optional[Spin] = None


@dataclass
class ManualProgress:
    """表盘点的那整段（换姿势过去 + 动作 + 换回来）：哪个动作、什么时候开始、估计多长（表盘的进度条）；整段做完清掉。"""
    id: str
    t0: float
    total: float


@dataclass
class Settle:
    """一刀切之后 0.3 秒里的两件事：朝向滑回 (起始, 目标, 已过秒数)，半空落回 (当时高度, 当时俯仰, 已过秒数)。"""
    yaw: Optional[tuple[float, float, float]] = None
    drop: Optional[tuple[float, float, float]] = None


@dataclass
class Turntable:
    """站在转台上时的朝向（看细节）：临界阻尼弹簧，和 animation.Spring 同一个解析解（这里要不折回的角度、要能让别人先带着转，单写一个）。
    角度不折回 0～360：转盘转了几圈就是几圈，dog.yaw 取它的余数。aim：要转到哪；None = 就停在现在的朝向（刚上去、还没碰过转盘）。
    free：上一帧是它在管朝向（不是 roam、你点的动作、一刀切的滑回在带着转）；别人带着转时它只跟着实际朝向（follow），接手时不跳，
    这期间记下的去处接手时走近的那边、按转回去的快慢过去（_step_turntable）。"""
    value: float
    velocity: float = 0.0
    aim: Optional[float] = None
    omega: float = 2.0 * math.pi / TURNTABLE_FOLLOW_S
    free: bool = True

    @property
    def target(self) -> float:
        return self.value if self.aim is None else self.aim

    @property
    def settled(self) -> bool:
        return self.velocity == 0.0 and self.value == self.target

    def near(self, yaw: float) -> float:
        """yaw（0～360）换成离现在最近的那个不折回的角度：走近的那边。"""
        return self.value + _wrap(yaw - self.value)

    def follow(self, yaw: float) -> None:
        """别人在带着转：跟着实际朝向，速度清零（接手时从这里接着转，不跳）。"""
        self.value, self.velocity, self.free = self.near(yaw), 0.0, False

    def set_speed(self, response: float) -> None:
        self.omega = 2.0 * math.pi / response

    def aim_at(self, aim: float, instant: bool = False) -> None:
        """跟着转盘连续地改要去的地方：保留速度（拖着来回转是匀的，不会每动一下就重新起步）。"""
        self.aim = aim
        if instant:
            self.value, self.velocity = aim, 0.0

    def go_to(self, aim: float, instant: bool = False) -> None:
        """换个去处（离开那两页、转回来）：一路单调地过去，不过头——往反方向转着的先停住，冲得太快的压到刚好停在那（c = 0）。"""
        self.aim_at(aim, instant)
        d, v = self.value - aim, self.velocity
        if d * v > 0.0:
            self.velocity = 0.0
        elif abs(v) > self.omega * abs(d):
            self.velocity = -self.omega * d

    def stop(self) -> None:
        """就近停住（转回去的路上又回到那两页）：停在 现在 + 速度 / ω，c = 0，不倒回来。"""
        self.aim = self.value + self.velocity / self.omega

    def step(self, dt: float) -> None:
        target = self.target
        d0, v0, w = self.value - target, self.velocity, self.omega
        c = v0 + w * d0
        e = math.exp(-w * dt)
        self.value = target + (d0 + c * dt) * e
        self.velocity = (v0 - w * c * dt) * e
        if abs(self.value - target) < 0.01 and abs(self.velocity) < 0.5:
            self.value, self.velocity = target, 0.0


@dataclass(frozen=True)
class PostureStep:
    posture: str
    keep_sleep_style: bool = False   # 回到"睡"时用刚才那种睡法、不轮换（换边转身后睡回去、做完动作回去）


@dataclass(frozen=True)
class TurnStep:
    yaw: float


@dataclass(frozen=True)
class ActionStep:
    action: Action
    manual: bool = False     # 表盘点的（同一根再点算"重来"，进度条跟着）还是随机的


Step = Union[PostureStep, TurnStep, ActionStep]


class PlayMixin:
    def _init_play(self) -> None:
        """互动模式的状态（DogController.__init__ 调）。"""
        self.play = False
        self.posture = "standing"            # lying / sitting / standing / sleeping（睡：趴睡或侧睡，叠在趴 / 侧躺上）
        self.waking = False                  # 从睡着切出来、醒来动画还没放完
        self.sleep_styles = tuple(SLEEP_PLANS)   # 点"睡"从这里挑（两种轮着来）；测试可以收窄
        self.sleep_style: Optional[str] = None   # 这次睡的是哪种（None = 还没睡过）：侧睡的醒来片段是起身，窗口据此决定醒来后站着还是趴着
        self.home_yaw = QUARTER_POSES[0]
        self.dynamic = False                 # 灵动交互
        self.lounge: Optional[str] = None    # 灵动交互里自己歇成什么（None 站着 / "sitting" / "lying"；set_lounge，playground._lounge 定）
        self._turntable: Optional[Turntable] = None   # 看细节：站在转台上（set_turntable；灵动交互那边也看它：Playground.fetch_on）
        self.turntable_pose: Optional[str] = None     # 站在转台上摆的姿势（那一页的站 / 坐 / 趴亮哪颗，set_turntable_pose）；不在转台上 None
        self.rest_posture = "lying"          # 用户选的姿势：灵动交互关着一直待着，开着是没人点时回去的
        self.steps: list[Step] = []          # 排队要做的事
        self.run: Optional[ActionRun] = None # 正在做的动作
        self.manual: Optional[ManualProgress] = None   # 表盘点的那整段的进度条
        self.jump: Optional[JumpState] = None
        self.jump_queue = 0
        self.last_jump: Optional[str] = None
        self.settle = Settle()
        self.last_action: Optional[str] = None
        self.action_at = math.inf            # 下一个随机动作什么时候来
        self._aim_since: Optional[float] = None   # 头带身体：鼠标在另一边多久了
        self._cooldown_until = 0.0
        self.y_offset = 0.0                  # 跳跃的抛物线高度，加在根矩阵上
        self.pitch = 0.0                     # 跳跃时的俯仰（度，正 = 抬头），加在根矩阵上

    @property
    def action(self) -> Optional[Action]:
        """正在做的动作（没有就 None）。"""
        return self.run.action if self.run is not None else None

    @property
    def phase(self) -> str:
        """现在在哪一步（给看、给测试，逻辑不靠它）：jump / turn / action / transition / idle。"""
        if self.jump is not None:
            return "jump"
        if self.turn is not None:
            return "turn"
        if self.run is not None:
            return "action"
        if self.transition:
            return "transition"
        return "idle"

    # ---------- 进出、姿势 ----------
    def set_play(self, on: bool = True, home_yaw: Optional[float] = None) -> None:
        """启动：按现在的姿势进（还没有姿势就是站着）、转到 home 朝向、再进该待的形态（灵动交互开着就是站着；否则是用户选的姿势）。
        已经进过了就只更新 home 朝向（朝向不对就转一次）。on=False 不再支持（镜像模式拿掉了），留着参数只为调用处好读。"""
        if not on:
            return
        if self.play:
            if home_yaw is not None:
                self.home_yaw = home_yaw
                self._face_home()
            return
        self.play = True
        self.props.cut()
        self._clear_activity()
        self.action_at, self.waking, self.steps = math.inf, False, []
        if home_yaw is not None:
            self.home_yaw = home_yaw
        self.posture = self._posture_of(self.plan)            # 按现在的姿势进，不强制起立
        self._switch_plan(self._posture_plan(self.posture))
        self._arm_actions(self.posture)
        home = self._home_posture()
        self.steps = [PostureStep(home)] if home != self.posture else []
        self._face_home()

    def _clear_activity(self) -> None:
        """半空、动作、进度条、滑回 / 落回全部清掉（换模式、一刀切）。"""
        self.jump, self.jump_queue, self.y_offset, self.pitch = None, 0, 0.0, 0.0
        self.run, self.manual, self.settle, self._aim_since = None, None, Settle(), None

    @staticmethod
    def _posture_of(plan: Optional[Plan]) -> str:
        """一个片段计划对应哪个待机姿势：进入片段是 Lie_belly_start 的算趴着、Sitting_start 的算坐着，其余（还没有计划）算站着。"""
        if plan is not None:
            for posture, p in POSTURE_PLANS.items():
                if p.enter and p.enter == plan.enter:
                    return posture
            if any(p.enter == plan.enter for p in SLEEP_PLANS.values()):
                return "sleeping"
        return "standing"

    def _arm_actions(self, posture: str) -> None:
        """这个姿势的随机动作什么时候开始来：普通的 8 到 20 秒后（活跃度低的隔得久，temper.action_every），稀有的按 RARE 的间隔。"""
        self.action_at = self.t + self.rng.uniform(*temper.action_every(self.tune))
        self._reset_rare([a.rare for a in ACTIONS if a.posture == posture and a.rare])

    def _home_posture(self) -> str:
        """该待的姿势：灵动交互开着一直站着，否则是用户选的。
        灵动交互里自己歇着的（lounge，活跃度低的狗）是歇成的那个姿势。"""
        return (self.lounge or "standing") if self.dynamic else self.rest_posture

    def set_lounge(self, posture: Optional[str], face: Optional[float] = None) -> None:
        """灵动交互里自己歇成什么：None（站着）/ "sitting" / "lying"。和现在的一样什么都不做；变了就换过去（正在做的一刀切）。
        face：歇下来朝哪（playground 给靠边的狗，window._edge_yaw）：先转过去再坐、趴（_face_home）；None 就朝着现在这边歇。
        被 roam 牵着时只记下：roam 接管时自己会让它站起来（puppet_stand），交回来是站着的。站在转台上也只记下：姿势听转台的，下来再回去。"""
        if posture == self.lounge:
            return
        self.lounge = posture
        turn = face is not None and posture is not None
        if turn:
            self.home_yaw = face
        if self.play and self.dynamic and not self.puppet and not self.on_turntable:
            self._go_posture(self._home_posture())
            if turn:
                self._face_home()

    def set_dynamic(self, on: bool) -> None:
        """灵动交互：打开就站起来、一直站着；关掉回到用户选的姿势。站在转台上只记下，下来再回去。"""
        self.lounge = None
        self.dynamic = bool(on)
        self.jump, self.jump_queue, self.y_offset, self.pitch = None, 0, 0.0, 0.0
        if self.play and not self.on_turntable:
            self._go_posture(self._home_posture())

    def set_rest_posture(self, posture: str) -> None:
        """用户选的姿势：站 / 坐 / 趴 / 睡。灵动交互关着时立刻生效、一直待着；开着时只记下，关掉灵动交互再过去。
        站在转台上（看细节）从「···」旁边的姿势条选的：转台上也换过去（set_turntable_pose），下来就待在这个姿势。"""
        if posture not in POSTURE_PLANS:
            return
        self.rest_posture = posture
        if self.on_turntable:
            if not self.dynamic:
                self.set_turntable_pose(posture)
            return
        if self.play and not self.dynamic:
            self._go_posture(posture)

    def _go_posture(self, posture: str, keep_sleep_style: bool = False) -> None:
        """排一步换形态；正在做的（随机动作、表盘动作、半空的跳）一刀切。keep_sleep_style：回到睡时用上次那种睡法（下转台回去）。"""
        self._interrupt_action()
        self.steps = [s for s in self.steps if not isinstance(s, PostureStep)] + [PostureStep(posture, keep_sleep_style)]

    def _posture_ahead(self) -> str:
        """手上的事做完以后待在哪个姿势：排着的最后一个，没排就是现在这个。"""
        return next((s.posture for s in reversed(self.steps) if isinstance(s, PostureStep)), self.posture)

    def set_auto_turn(self, on: bool) -> None:
        """身体要不要跟着鼠标转（灵动交互开着就转，window._apply_modes）。关了只转头，身子中断当前动作并转回 home 那边（站在转台上不转：朝向听转盘）。"""
        self.auto_turn = bool(on)
        if not self.auto_turn:
            self._aim_since = None
            if self.play and not self.on_turntable:
                self._face_home(interrupt=True)

    def set_home_yaw(self, yaw: float) -> None:
        """灵动交互关着时小组件在所有屏合起来那块的右半边朝左、左半边朝右（window._home_yaw）；换了半边（拖过中线、被系统挪过去）窗口调它，没换边什么都不做（鼠标跟随转过去的身子不被拽回来）。
        一律转：站着直接转；趴着、坐着先起身、转、再回原姿势；睡着的醒来、起身、转、再用同一种睡法睡回去（_face_home）。
        被 roam 牵着、站在转台上（看细节）的时候只记下：roam 做完自己转到 home；转台下来时 window.closeup 再叫一次。
        灵动交互里自己歇着（lounge）的时候也只记下：坐着趴着只转头，不为鼠标换了边起立转身再趴回去（窗口每次停稳都会来问一次）。"""
        changed = abs(_wrap(yaw - self.home_yaw)) > 1.0
        self.home_yaw = yaw
        if changed and self.play and not self.puppet and not self.on_turntable and self.lounge is None:
            self._face_home(interrupt=True)

    def snap_home(self, yaw: float) -> None:
        """狗直接朝 home，不播转身（排着的转身、一刀切还没滑完的作废）：启动时窗口刚放好、还没显示出来；换同桌时（看不见）收掉转台。"""
        self.home_yaw = self.yaw = yaw
        self.settle.yaw = None
        self.steps = [s for s in self.steps if not isinstance(s, TurnStep)]

    def settle_into(self, posture: str) -> None:
        """直接待在这个姿势里，不播起身、趴下（换模型换上来的新狗：看不见的时候就已经是该待的样子；window._use_kit 在 set_play 之后调）。
        排着的（换姿势、转身）、正在做的都作废，循环片段从头放、不交叉淡入；睡：挑一种睡法，直接睡着。朝哪由调的人接着定（snap_home）。"""
        if posture not in POSTURE_PLANS:
            return
        self._clear_activity()
        self.steps = []
        self.waking = False
        if posture == "sleeping" and self.sleep_style is None:
            self.sleep_style = self.rng.choice(list(self.sleep_styles))
        self.posture = posture
        self._aim_since = None
        self._arm_actions(posture)
        plan = self.plan = self._posture_plan(posture)
        self.queue, self.transition, self.turn = [], False, None
        self.head_pitch_target = 0.0
        self._reset_rare(plan.loop)
        self.player.prev = None                                   # 不和刚才那段（set_play 起的站着）交叉淡入
        loops = self._loop_choices(plan)
        self.player.play(loops[0] if len(loops) == 1 else self._pick(loops), loop=len(loops) == 1, fade=0.0)

    def _rest_yaw(self) -> float:
        """手上的事做完之后狗朝哪：正在做的动作滑回开始前的朝向，转身转到目标，一刀切的滑回滑到终点。"""
        if self.run is not None:
            return self.run.yaw_before
        if self.turn is not None:
            return self.turn.target
        if self.settle.yaw is not None:
            return self.settle.yaw[1]
        return self.yaw

    def _face_home(self, interrupt: bool = False) -> None:
        """朝向不是 home 就把转身排进 steps，在狗站着的那一段里转：现在就站着排最前面；后面排着"站"就排在它后面；
        都没有就先起身、转，再回到它本来要待的姿势（排着别的姿势就交给它；睡着的接着用同一种睡法）。
        外部换边用 interrupt：旧动作立即作废；模式初始化保留原来的过渡队列。"""
        self.steps = [s for s in self.steps if not isinstance(s, TurnStep)]
        if abs(_wrap(self.home_yaw - self._rest_yaw())) < 20.0:
            return
        if interrupt:
            self._request_turn(self.home_yaw)
            return
        turn = TurnStep(self.home_yaw)
        if self.posture == "standing":
            self.steps.insert(0, turn)
            return
        for k, s in enumerate(self.steps):
            if isinstance(s, PostureStep) and s.posture == "standing":
                self.steps.insert(k + 1, turn)
                return
        back = [] if any(isinstance(s, PostureStep) for s in self.steps) else [PostureStep(self.posture, keep_sleep_style=True)]
        self.steps[0:0] = [PostureStep("standing"), turn] + back

    def _request_turn(self, target: float) -> None:
        """外部转向：动作 / 跳跃及道具一起中断，旧任务只保留最终姿势，从当前朝向转到绝对目标。
        动作 program 的内部转身直接走 _start_turn，不能经过这里，否则捡回会把自己取消。"""
        back = next((s.posture for s in reversed(self.steps) if isinstance(s, PostureStep)), self.posture)
        self._interrupt_action()
        self.settle.yaw = None                                   # 新目标取代旧动作的回正，不能叠到转身角度上
        self._aim_since = None
        if math.isfinite(self.action_at):
            self.action_at = max(self.action_at, self.t + self.rng.uniform(*temper.action_every(self.tune)))
        self.steps = [PostureStep(back, keep_sleep_style=True)] if back != "standing" else []
        turn = TurnStep(target)
        if self.posture != "standing":
            self.steps[0:0] = [PostureStep("standing"), turn]
        else:
            self._run_step(turn)

    def sleep_state(self) -> str:
        """睡觉的阶段（设置的动作行和「···」的姿势条据此只显示「醒来」）：awake / falling（正在趴下、入睡）/ asleep / waking（醒来动画没放完）。"""
        if not self.play:
            return "awake"
        pending = [s.posture for s in self.steps if isinstance(s, PostureStep)]
        if self.posture == "sleeping":
            if any(p != "sleeping" for p in pending):
                return "waking"                                    # 点了醒来、还没轮到那一步
            return "falling" if self.transition else "asleep"
        if "sleeping" in pending:
            return "falling"
        return "waking" if self.waking else "awake"

    def _posture_plan(self, posture: str) -> Plan:
        """姿势对应的计划；睡觉按这次挑中的睡法（趴睡 / 侧睡）。"""
        return SLEEP_PLANS[self.sleep_style or self.sleep_styles[0]] if posture == "sleeping" else POSTURE_PLANS[posture]

    def _set_posture(self, posture: str, keep_sleep_style: bool = False) -> None:
        self.waking = self.posture == "sleeping" and posture != "sleeping"   # 醒来动画放完（transition 结束）才算醒
        if posture == "sleeping" and self.posture != "sleeping" and not (keep_sleep_style and self.sleep_style):
            others = [s for s in self.sleep_styles if s != self.sleep_style] or list(self.sleep_styles)
            self.sleep_style = self.rng.choice(others)                        # 两种睡法轮着来：第一次随机，之后用上次没用的（纯随机会连着出同一种）
        self.posture = posture
        self._aim_since = None
        if posture != "standing":
            self.jump_queue = 0
        self._arm_actions(posture)
        self._switch_plan(self._posture_plan(posture))

    # ---------- 看细节：站在转台上（widget/closeup.py 开关） ----------
    @property
    def on_turntable(self) -> bool:
        return self._turntable is not None

    def set_turntable(self, on: bool, instant: bool = False) -> None:
        """上 / 下转台（详情页、自定义毛色页开着的时候；只有 window.closeup 调）。
        上去：先站起来（不管在做什么、趴着坐着睡着，进那一页就站着），自己的事都停——正在做的动作、半空的跳、转身、换到别的姿势的一半
        一刀切（会融就融，朝向滑到它本来要去的地方），排着的都作废；正站起来的让它站完（本来就是往站着去）。之后姿势听那一页的站 / 坐 / 趴
        （set_turntable_pose），不来随机动作、身子不跟鼠标 / 球转、换边不转身、头不看鼠标；朝向只听转盘。被 roam 牵着（在跑、在跳、被拎着）的照旧让它做完
        （交回来就是站着），转台这期间跟着实际朝向，交回来再接着管。
        下来：回到该待的姿势（_home_posture：灵动交互关着是选的姿势，开着是站着 / 自己歇成的样子；睡的接着用原来那种睡法）——看细节和放大一样是临时看的，
        离开那一页就回到进来前的样子；instant：当场待在那个姿势里、不播（换同桌时狗看不见）。随机动作重新计时；转盘还差的一点（不到 TURNTABLE_DONE_DEG）
        交给一刀切的滑回。"""
        on = bool(on)
        if on == self.on_turntable:
            return
        self._aim_since = None
        if on:
            self._turntable = Turntable(self.yaw)
            self.turntable_pose = "standing"
            self.jump_queue = 0
            if not self.puppet:                                   # roam 牵着：它的事做完再说（puppet_begin 已经清过 steps，交回来是站着的）
                self._pose_on_table("standing")
            return
        table, self._turntable = self._turntable, None
        self.turntable_pose = None
        if self._turntable_free():
            rest = table.target % 360.0
            if abs(_wrap(rest - self.yaw)) > 0.01:
                self.settle.yaw = (self.yaw, rest, 0.0)          # 剩下的那一点 0.3 秒滑完（_settle_cut）
        self.action_at = self.t + self.rng.uniform(*temper.action_every(self.tune))
        if not self.play or self.puppet:
            return                                                # roam 牵着：交回来是站着，该歇的游乐场再叫（set_lounge）
        home = self._home_posture()
        if instant:
            if self.posture != home or self.transition or self.steps:
                self.settle_into(home)
        elif self._posture_ahead() != home:
            self._go_posture(home, keep_sleep_style=True)

    def set_turntable_pose(self, posture: str) -> None:
        """站在转台上摆什么姿势（看细节那一页的站 / 坐 / 趴；「···」旁边姿势条选的也走这）：换过去，正做的、正换到别的姿势一半的一刀切。
        被 roam 牵着的只记下，交回来再换（locomotion.puppet_end）。不在转台上不理。"""
        if self._turntable is None or posture not in POSTURE_PLANS:
            return
        self.turntable_pose = posture
        if self.play and not self.puppet:
            self._pose_on_table(posture)

    def _pose_on_table(self, posture: str) -> None:
        """转台上换到 posture：正做的动作、半空的跳、转身都切掉（会融就融），排着的都作废（表盘的进度条也收）；已经是这个姿势、
        或者正往这个姿势换（过渡片段播着）就让它换完，正往别的姿势换的一刀切。"""
        if self.run is not None or self.jump is not None or self.turn is not None or (self.transition and self.posture != posture):
            self._interrupt_action()
        self.manual = None
        self.steps = [] if self.posture == posture else [PostureStep(posture)]

    def turntable_turn(self, degrees: float, instant: bool = False) -> None:
        """转盘尺转了这么多度（正 = 狗靠近你的那一面往右，和尺上的刻度一个方向）：要转到的地方跟着挪，0.12 秒跟上（不过头）。
        还没碰过转盘时从它现在要朝的方向算起（刚切掉的转身滑到哪、roam 把它转到哪）。"""
        table = self._turntable
        if table is None or not math.isfinite(degrees):
            return
        table.set_speed(TURNTABLE_FOLLOW_S)
        base = table.aim if table.aim is not None else table.near(self._heading())
        table.aim_at(base + degrees, instant)

    def turntable_return(self, yaw: float, instant: bool = False) -> None:
        """离开那两页：走近的那边转回 yaw（0.5 秒，不过头；往别处转着的先停住），差 TURNTABLE_DONE_DEG 以内 turntable_back 就是真。"""
        table = self._turntable
        if table is not None:
            table.set_speed(TURNTABLE_RETURN_S)
            table.go_to(table.near(yaw), instant)

    def turntable_stop(self) -> None:
        """转回去的路上又回到那两页：就近停住，不倒回来；转盘尺从停的地方接着转。"""
        if self._turntable is not None:
            self._turntable.stop()

    @property
    def turntable_angle(self) -> float:
        """转盘现在要转到哪（度，不折回）：转盘尺照着画。不在转台上就是现在的朝向。"""
        return self._turntable.target if self._turntable is not None else self.yaw

    @property
    def turntable_back(self) -> bool:
        """转台在管朝向，而且离它要去的地方不到 TURNTABLE_DONE_DEG（window.closeup 看它决定什么时候放狗下来）。"""
        table = self._turntable
        return table is not None and table.free and abs(_wrap(table.target - self.yaw)) < TURNTABLE_DONE_DEG

    @property
    def turntable_moving(self) -> bool:
        """转台还在转（窗口按它算有动静，省电模式不降帧）。"""
        table = self._turntable
        return table is not None and not (table.free and table.settled)

    def _turntable_free(self) -> bool:
        """朝向这时归转台管：没被 roam 牵着、没在做动作、没在转身、没在跳、一刀切的滑回滑完了。"""
        return not self.puppet and self.run is None and self.turn is None and self.jump is None and self.settle.yaw is None

    def _heading(self) -> float:
        """手上的事做完之后狗朝哪（_rest_yaw），被 roam 牵着平滑转身时是它要转到的地方。"""
        if self.puppet and self._spin is not None:
            return (self._spin[0] + self._spin[1]) % 360.0
        return self._rest_yaw()

    def _step_turntable(self, dt: float) -> None:
        """转台每帧：朝向归它管就按弹簧转（dog.yaw 只在这写，一个写的地方）；别人在带着转就跟着实际朝向。"""
        table = self._turntable
        if not self._turntable_free():
            table.follow(self.yaw)
            return
        if not table.free:
            table.follow(self.yaw)                                # 刚接手：从这一帧的实际朝向接着转（滑回的最后一步、roam 交回、动作做完）
            table.free = True
            if table.aim is not None:                             # 别人带着转的时候转盘记下的去处：从现在的朝向走近的那边过去，
                table.aim = table.near(table.aim % 360.0)         # 慢一点（不是正拖着转盘；roam 可能早把它转过半圈了）
                table.set_speed(TURNTABLE_RETURN_S)
        table.step(dt)
        self.yaw = table.value % 360.0

    # ---------- 表盘 ----------
    def do_action(self, action_id: str) -> None:
        """表盘停到一根 / 点了一根：立刻做（一刀切，见 _interrupt_action），做完回到点之前的姿势。
        狗现在的姿势和动作要的不一样就先换过去、做完换回来；正在做的就是同一个动作 → 重来（单段循环的只延长、不重播片段）。
        姿势行选的（rest_posture）不变。"""
        a = ACTIONS_BY_ID.get(action_id)
        if a is None or not self.play:
            return
        back = next((s.posture for s in reversed(self.steps) if isinstance(s, PostureStep)), self.posture)   # 正在做的那段要回的姿势就是最开始那个
        run = self.run
        if run is not None and run.action is a and run.manual and run.loop_until is not None and len(a.program) == 1:
            run.loop_until = self.t + a.program[0][2]             # 同一根再点、正循环着：从现在再走整段，片段不跳帧
            self.manual = ManualProgress(a.id, self.t, float(a.program[0][2]))
            return
        self._interrupt_action()
        turns = [s for s in self.steps if isinstance(s, TurnStep)]       # 排着的换边转身不丢：站起来先转过去
        steps: list[Step] = []
        at = self.posture
        if turns and at != "standing":
            steps.append(PostureStep("standing"))
            at = "standing"
        steps += turns
        if at != a.posture:
            steps.append(PostureStep(a.posture))
        steps.append(ActionStep(a, manual=True))
        if back != a.posture:
            steps.append(PostureStep(back, keep_sleep_style=True))
        self.steps = steps
        self.manual = ManualProgress(a.id, self.t, self.action_duration(a) + POSTURE_CHANGE * sum(isinstance(s, PostureStep) for s in steps))

    def action_duration(self, a: Action) -> float:
        """一个动作的 program 大约要播多久（秒）：片段按时长、循环按秒数、转身按转身片段、跳按一跳。"""
        total = 0.0
        for item in a.program:
            if isinstance(item, str):
                total += self.model.clips[item].duration
            elif item[0] == "loop":
                total += item[2]
            elif item[0] == "turn":
                total += self.model.clips[TURN_180["L"] if abs(item[1]) > 100.0 else TURN_90["L"]].duration
            elif item[0] == "jump":
                total += JUMP_SECONDS
        return total

    def manual_progress(self) -> Optional[tuple[str, float]]:
        """表盘点的那段动画还剩多少：(动作 id, 剩余比例 1 → 0)；没在做就 None。"""
        m = self.manual
        if m is None:
            return None
        return m.id, max(0.0, min(1.0, 1.0 - (self.t - m.t0) / max(0.1, m.total)))

    # ---------- 一刀切 ----------
    def _interrupt_action(self) -> None:
        """一刀切（所有动作都能打断，会融就融）：正在做的动作、半空的跳、转身片段、换姿势的过渡片段全部立刻停，
        回到当前形态的循环并让下一段 0.3 秒交叉淡入进来（接着做什么由调用方排 steps）。动作把朝向转走了的，朝向在同样 0.3 秒里
        滑回动作开始前的角度（yaw_before），不播转身片段；转到 home 的转身被切就滑到它要去的朝向；半空的高度和俯仰 0.3 秒落回。"""
        cut = self.run is not None or self.jump is not None or self.turn is not None or self.transition
        self.props.cut()                                          # 道具跟着一刀切：0.3 秒淡出，不在地上停
        target: Optional[float] = None
        if self.run is not None:
            target = self.run.yaw_before
        elif self.turn is not None:
            target = self.turn.target
        if self.jump is not None:
            self.settle.drop = (self.y_offset, self.pitch, 0.0)
        if target is not None and abs(_wrap(target - self.yaw)) > 1.0:
            self.settle.yaw = (self.yaw, target, 0.0)
        self.jump, self.jump_queue, self.turn = None, 0, None
        self.run, self.manual = None, None
        self.head_pitch_target = 0.0
        self.queue, self.transition, self._cut_at = [], False, 1.0
        if cut:
            self._play_next(fade=CUT_SECONDS)

    def _settle_cut(self, dt: float) -> None:
        """一刀切之后的 0.3 秒：朝向滑回、半空落回。"""
        if self.settle.yaw is not None:
            start, target, elapsed = self.settle.yaw
            elapsed += dt
            u = min(1.0, elapsed / CUT_SECONDS)
            self.yaw = (start + _wrap(target - start) * _ease(u)) % 360.0
            self.settle.yaw = None if u >= 1.0 else (start, target, elapsed)
        if self.settle.drop is not None:
            y0, p0, elapsed = self.settle.drop
            elapsed += dt
            u = min(1.0, elapsed / CUT_SECONDS)
            self.y_offset, self.pitch = y0 * (1.0 - u), p0 * (1.0 - u)
            self.settle.drop = None if u >= 1.0 else (y0, p0, elapsed)

    # ---------- 排队的事、动作 ----------
    def _run_step(self, step: Step) -> None:
        if self.on_turntable and (isinstance(step, TurnStep) or (isinstance(step, ActionStep) and not step.manual)):
            return                                                # 转台上：自己要转的、自己来的动作作废；你点的姿势、表盘点的动作照做
        if isinstance(step, PostureStep):
            self._set_posture(step.posture, step.keep_sleep_style)
        elif isinstance(step, TurnStep):
            if self.posture != "standing":                        # 转身片段是站着的：先起身（排它的地方会接着排回原姿势）
                self.steps[0:0] = [PostureStep("standing"), step]
                return
            d = _wrap(step.yaw - self.yaw)
            self.settle.yaw = None                               # TurnStep 是绝对朝向；内部 program 转身才是相对角度
            if abs(d) > 5.0:
                self._start_turn(d)
        else:
            self._start_action(step.action, manual=step.manual)

    def _start_action(self, a: Action, manual: bool = False) -> None:
        if a.spin and self.settle.yaw is not None:
            self.yaw, self.settle.yaw = self.settle.yaw[1], None      # 转圈要从一个定点转整圈：上一刀切的滑回直接到位
        yaw_before = self.settle.yaw[1] if self.settle.yaw is not None else self.yaw   # 这个动作被切时朝向滑回这里
        self.run = ActionRun(a, list(a.program), manual, yaw_before)
        self.last_action = a.id
        if a.prop:
            self.props.begin(a.prop, self.root_matrix())         # 带道具的动作：盆现在就出，骨头 / 球等 Pick_up
        if a.spin:
            self.run.spin = Spin(self.yaw, sum(self.model.clips[c].duration for c in a.program if isinstance(c, str)))
        self._advance_program()

    def _advance_program(self) -> None:
        """做动作的下一项：片段名播一遍；("loop", 片段, 秒) 循环这么久；("turn", 度) 转身片段；("jump", 跳法) 跳一下；
        ("pitch", 度) 头的俯仰（不占时间）。跳和转身由 _advance_jump / _advance_turn 推进，结束时再回到这里。都做完就回形态的循环。"""
        run = self.run
        while run.program:
            item = run.program.pop(0)
            if isinstance(item, str):
                self.queue, self.transition = [(item, 1.0, 1.0)], True
                self._play_next(fade=FADE_CLIP)
                return
            kind = item[0]
            if kind == "loop":
                self.player.play(item[1], loop=True, fade=FADE_CLIP, restart=self.player.name != item[1])
                self.transition, run.loop_until = True, self.t + item[2]
                return
            if kind == "turn":
                self._start_turn(item[1])
                return
            if kind == "jump":
                self._start_jump(jump=next(j for j in self.jumps if j.name == item[1]))
                return
            if kind == "pitch":
                self.head_pitch_target = item[1]
        self.run = None
        self.head_pitch_target = 0.0
        self.queue, self.transition = [], False
        self.action_at = self.t + self.rng.uniform(*temper.action_every(self.tune))
        self.props.finish()                                       # 动作做完：盆淡出，放下的骨头 / 球在地上停几秒
        self._play_next()

    def _schedule_action(self) -> None:
        """没人点、什么都没在做：到点就来一个随机动作。稀有的（抬前爪、哈欠）按自己的间隔，其余共用 8 到 20 秒一个的节拍。
        灵动交互里自己歇着的（lounge）不做要先站起来的：坐下没一会儿又起身抬爪、再坐回去，太忙。"""
        pool = [a for a in ACTIONS if a.posture == self.posture and a.default and not (self.lounge and a.via_standing)]
        due = [a for a in pool if a.rare and self.t >= self._rare_next.get(a.rare, 0.0)]
        if due:
            a = due[0]
            self._rare_next[a.rare] = self.t + self.rng.uniform(*RARE[a.rare])
        elif self.t >= self.action_at:
            self.action_at = self.t + self.rng.uniform(*temper.action_every(self.tune))
            common = [x for x in pool if not x.rare and x.id != self.last_action] or [x for x in pool if not x.rare]
            if not common:
                return
            a = self.rng.choice(common)
        else:
            return
        if a.via_standing and self.posture != "standing":
            self.steps += [PostureStep("standing"), ActionStep(a), PostureStep(self.posture)]
        else:
            self._start_action(a)

    # ---------- 跳 ----------
    def _start_jump(self, chained: bool = False, jump: Optional[Jump] = None) -> None:
        """开始一跳。chained：上一跳刚落地接着来的，起跳更快、不淡入那么久。jump：动作 program 指定的跳法，不给就随机（不连重复）。"""
        j: Jump = jump or self.rng.choice([j for j in self.jumps if j.name != self.last_jump])
        self.last_jump = j.name
        speed = self.rng.uniform(*JUMP_SPEED)
        if self.run is not None:
            self.run.spin = None
        self.settle.drop = None
        self.queue, self.transition = [], False
        self._aim_since = None
        self.jump = JumpState(j, "whole" if j.whole else "start", speed, j.height * self.rng.uniform(*JUMP_HEIGHT_VARY))
        if j.whole:
            self.player.play(j.whole, loop=False, fade=0.15 if chained else FADE_CLIP, speed=speed * (CHAIN_WHOLE_SPEED if chained else 1.0))
            self.player.time = max(0.0, j.arc[0] - WHOLE_LEAD) * self.model.clips[j.whole].duration   # 跳过助跑
        else:
            self.player.play(j.start, loop=False, fade=0.15 if chained else FADE_CLIP, speed=speed * (CHAIN_SPEED if chained else 1.0))

    def _advance_jump(self, dt: float) -> None:
        st = self.jump
        j = st.j
        if st.phase == "whole":
            u0, u1 = j.arc
            s = (self.player.progress - u0) / max(1e-6, u1 - u0)
            arc = st.h * 4.0 * s * (1.0 - s) if 0.0 < s < 1.0 else 0.0
            clip_foot = (self._last_min_foot - self.y_offset) if self._last_min_foot is not None else 0.0
            self.y_offset = max(arc, FOOT_REST - clip_foot, 0.0)     # 片段自己有一段脚钻地的下蹲，把根抬住
            if self.jump_queue > 0 and s >= 1.0:                      # 排着下一跳：腾空段一完就接
                self._end_jump(chain=True)
            elif self.player.finished:
                self._end_jump()
            return
        if st.phase == "start":
            if self.player.finished:
                st.phase, st.u = "air", 0.0
                self.player.play(j.air, loop=True, fade=0.1, speed=st.speed)
            return
        st.u = min(1.0, st.u + dt * st.speed / j.air_time)
        u = st.u
        arc = st.h * 4.0 * u * (1.0 - u)
        if st.phase == "air":
            self.y_offset = arc
            self.pitch = j.pitch * (1.0 - 2.0 * u) * min(1.0, u / 0.15)   # 起跳抬头、顶点水平、下落低头
            trigger = max(0.0, -self._land_foot0.get(j.land, 0.0))   # 落地片段开头脚在地下多少，抛物线降到那就接
            if u >= 0.5 and (arc <= trigger + 1e-9 or u >= 1.0):
                st.phase = "land"
                self.player.play(j.land, loop=False, fade=0.1, speed=st.speed)
        else:
            # 落地：抛物线继续降，但脚不许钻到地下（落地片段开头脚可能在 0 以下，是给还在空中时用的）
            clip_foot = (self._last_min_foot - self.y_offset) if self._last_min_foot is not None else 0.0
            self.y_offset = max(arc, FOOT_REST - clip_foot, 0.0)
            self.pitch += (0.0 - self.pitch) * (1.0 - math.exp(-dt / 0.12))
            touched = self.y_offset <= 1e-6 and self._last_min_foot is not None and self._last_min_foot <= FOOT_REST + 0.02
            if self.jump_queue > 0 and touched:                      # 排着下一跳：脚一沾地就接，落地片段不播完
                self._end_jump(chain=True)
            elif self.player.finished:
                self._end_jump()

    def _end_jump(self, chain: bool = False) -> None:
        self.jump = None
        self.y_offset = 0.0
        self.pitch = 0.0
        if self.jump_queue > 0 and self.run is None:        # 排着下一跳：落地片段播完（或脚一沾地）直接接，中间不回待机帧
            self.jump_queue -= 1
            self._start_jump(chained=True)
            return
        self.action_at = self.t + self.rng.uniform(*temper.action_every(self.tune))
        if self.run is not None:
            self._advance_program()               # 动作里的一跳：落地接着做下一项
        else:
            self._play_next()

    # ---------- 头带身体 ----------
    def facing_right(self) -> bool:
        """身体现在更接近头朝右（330°）还是头朝左（210°）。"""
        return abs(_wrap(self.yaw - QUARTER_POSES[1])) < abs(_wrap(self.yaw - QUARTER_POSES[0]))

    def _front_delta(self, target: float) -> float:
        """从现在的朝向转到 target 要转多少度，走经过镜头正前方（270°）的那条路：两个四分之三朝向之间是 120°，中途正脸朝你一下。"""
        d = _wrap(target - self.yaw)
        if d == 0.0:
            return 0.0
        through = _wrap(270.0 - self.yaw)                      # 正前方在这条短路上吗
        if not (0.0 <= through <= d if d > 0 else d <= through <= 0.0):
            d -= math.copysign(360.0, d)
        return d

    def _follow_body(self, dt: float) -> bool:
        """头带身体（固定两个朝向）：站着跟随鼠标时身体只在头朝左 210° / 头朝右 330° 之间切。
        鼠标过到另一边、离狗中心超过 BODY_FLIP_LENGTHS 个身长、持续 BODY_TURN_DEBOUNCE 秒、不在冷却里，就中断动作、从实际朝向转过去；
        普通换边经过镜头前方，中间距离只转头。灵动交互里要歇了（lounge 定了、还没来得及坐下趴下的那一两帧）也不转：走到狗屋门口转好头朝外的不被鼠标拽回去。"""
        target = self.body_target if self.body_target is not None else self.look_target
        if (self.on_turntable or not self.auto_turn or target is None or self.posture != "standing" or self.lounge is not None
                or (self.run is None and (self.transition or self.turn is not None))):
            self._aim_since = None
            return False
        dx = target[0] - self.x
        tune = self.tune
        reach = (tune["turn_reach"] if tune is not None else BODY_FLIP_LENGTHS) * self.body_length
        delay = (tune["turn_delay"] if tune is not None else BODY_TURN_DEBOUNCE) + temper.turn_lag(tune)   # 活跃度低的慢半拍（边牧 + 0）
        want_right, want_left = dx > reach, dx < -reach
        # 捡回 / 转圈会自己转动身体；固定鼠标不能仅因动画转到了另一侧就把动作打断。
        reference = self._rest_yaw()
        right = abs(_wrap(reference - QUARTER_POSES[1])) < abs(_wrap(reference - QUARTER_POSES[0]))
        if not ((want_right and not right) or (want_left and right)):
            self._aim_since = None
            return False
        if self._aim_since is None:
            self._aim_since = self.t
        if self.t - self._aim_since < delay or self.t < self._cooldown_until:
            return False
        self._request_turn(QUARTER_POSES[1] if want_right else QUARTER_POSES[0])
        return True

    # ---------- 每帧 ----------
    def _update_play(self, dt: float) -> None:
        if self.puppet:                                         # 灵动交互里被 roam 牵着走（跑去捡球、跳窗口）：自己的事都停
            self._update_puppet(dt)
            if self._turntable is not None:
                self._step_turntable(dt)                        # 转台跟着 roam 转到的朝向
            return
        self._settle_cut(dt)
        if self._turntable is not None:
            self._step_turntable(dt)                            # 看细节：朝向听转盘（在 props.update 之前：道具这一帧就跟着转到的角度）
        if self._follow_body(dt):
            return
        if self.jump is not None:
            self._advance_jump(dt)
            return
        if self.turn is not None:
            self._advance_turn(dt)
            return
        run = self.run
        if run is not None and run.spin is not None:            # 转圈动作：片段播多久身体转多久
            run.spin.elapsed += dt
            self.yaw = (run.spin.start + 360.0 * min(1.0, run.spin.elapsed / run.spin.total)) % 360.0
        if run is not None:                                     # 正在做动作：当前项做完就开下一项
            if run.loop_until is not None:
                if self.t < run.loop_until:
                    return
                run.loop_until = None
            elif not self.player.finished:
                return
            self._advance_program()
            if self.run is not None:
                return
        elif self.transition:                                   # 换姿势的退出 / 进入片段：播完（或到提前切的点）再说
            self._advance_transition()
            if self.transition:
                return
        self.waking = False                                     # 过渡片段播完了：醒来算醒了
        if self.steps:
            self._run_step(self.steps.pop(0))
            return
        self.manual = None                                      # 表盘点的那整段（含换姿势）做完了
        if self.player.finished:
            self._play_next()
        if self.posture == "standing":
            if self.jump_queue > 0:
                self.jump_queue -= 1
                self._start_jump()
                return
        if self.turn is None and not self.on_turntable:
            self._schedule_action()
