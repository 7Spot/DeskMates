"""性子：每个模型两项，开发者设置页最上面两根滑杆——活跃度 energy、聪明程度 smarts，0～1。边牧都是 1（一直以来的样子），
萨摩耶 0.5 / 0.4（packs/samoyed/pack.json 的 tuning）。纯函数，不碰 Qt；谁用谁每次带着调参来问，不抄进常量（改了马上生效）。

规矩：**两项都是 1 时每个函数直接 return 原来的那个数**（同一个浮点数，不经过乘加；元组就是原来那个元组）、不碰随机数——边牧的随机数序列、
每帧的数一个都不变（现有测试给 dog.rng 定了种子，多抽一个数后面全变；2.1 + (0.9 − 2.1) × 1 是 0.8999999999999999，门槛上那一下就挑了另一种步子）。
开发者设置页里别的数（max_up、ring_hold_s、turn_*）是「满分的狗」的数，性子在它上面打折，不改它们的默认值。
tune 可以是 Tuning、字典、None（没接调参）：没有这一项当 1。

活跃度低：不冲刺，远一点才肯跑；球扔出去多看一会儿、松手后还愣一下才冲；转身慢半拍；随机动作少一半；跳得矮一点；没人理一阵子自己坐下、趴下。
聪明程度低：不预判球的落点，一直追球本身；被弹回来的球晃到；圈满得慢；球放得没那么准；叼回来的路上偶尔愣一下。
下面的系数是照「萨摩耶 0.5 / 0.4 时手感对」定的（离屏模拟过，真机没试过）。

招牌时刻（Mood、express；都不出声，只用 widget/expression.py 现成的量）：憨 = 1 − 聪明程度，懒 = 1 − 活跃度。放下球眯眼笑一下（两只狗待机时嘴本来就张着、
舌头搭在外面，所以笑不动嘴：眯眼 + 耳朵往后 + 抬一点头 + 摇尾巴）；被弹回来的球晃到、够不着叫完、叼回来路上愣住时歪头；鼠标从远处挪到跟前轻轻摇尾巴；
趴着眼睛放松。两项都是 1 时 express 一个数都不碰。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from widget.clips import ACTION_EVERY

# ---- 两项都是 1 时的数：roam.py 里同名的常量是同一个数（那边的注释说来历；tests/test_temper.py 守着两边一样）----
GAIT_FAST_M, GAIT_RUN_M, GAIT_TROT_M = 3.0, 0.9, 0.3   # 离目标多远（米）以上快跑 / 跑 / 小跑，再近就走
FETCH_LOOK = 0.15           # 球扔出去先看多久再追
WATCH_TURN_S = 0.2          # 站着看球：球到了身后多久才转身
CHASE_LEAD = 0.4            # 追球本身时瞄它前面多久的位置

# ---- 活跃度每低一整格（1 → 0）加多少 ----
NO_SPRINT_BELOW = 0.75      # 活跃度比这低：没有快跑这一档
FAST_FAR_M = 4.0            # 快跑的门槛多远这么多米（0.75 时 4 米才冲刺）
RUN_FAR_M, TROT_FAR_M = 1.2, 0.4   # 跑、小跑的门槛（萨摩耶：1.5 米以上才跑、0.5 米以上小跑）
LOOK_SLOW_S = 0.5           # 球扔出去多看这么久（萨摩耶 0.40 秒）
RELEASE_BEAT_S = 0.6        # 俯身等着时你松手，还愣这么久才冲（萨摩耶 0.30 秒；「松手立刻冲出去」的例外）
WATCH_SLOW_S = 0.4          # 球到身后多等这么久才转身（萨摩耶 0.40 秒）
TURN_LAG_S = 0.4            # 跟鼠标转身多等这么久（萨摩耶 +0.20 秒）
TURN_PACE_CUT = 0.25        # 转身片段放快的倍数打掉这么多（萨摩耶 ×0.875：1.6 → 1.4 倍，一次约 0.71 秒）
TURN_REST_S = 0.5           # 转完多歇这么久（萨摩耶 +0.25 秒）
ACTION_GAP_GROW = 1.0       # 随机动作的间隔长这么多倍（萨摩耶 ×1.5：12～30 秒）。哈欠、抬爪（clips.RARE）不乘：哈欠要留着
MAX_UP_CUT = 0.3            # 一次最多跳的高度打掉这么多（萨摩耶 ×0.85：2.55 个身高）
REST_ABOVE = 0.85           # 活跃度到这以上：一直站着，不自己歇
SIT_AFTER_S, LIE_AFTER_S = 40.0, 120.0   # 没人理多久坐下、坐下后再多久趴下：这个数 × 活跃度（萨摩耶 20 / 60 秒）
SIT_MIN_S, LIE_MIN_S = 8.0, 30.0         # …最短也要这么久
NEST_AFTER_S = 90.0         # 摆了狗窝、狗屋（widget/things.py）：不自己歇的狗（边牧）没人理这么久走回窝趴下；自己歇的狗用它计划的第一段（萨摩耶 20 秒）。没摆窝不看它

# ---- 聪明程度 ----
READS_FROM = 0.6            # 聪明程度到这以上才看得出球停哪（直接去落点）；以下一直追球本身，球停了才去叼
LEAD_MIN_S, LEAD_GAIN_S = 0.1, 0.3       # 追球时瞄它前面多久：0.1 + 0.3 × 聪明程度（萨摩耶 0.22 秒）
FOOLED_S = 0.25             # 追着的球掉头了，愣多久才刹车：这个数 × (1 − 聪明程度)（萨摩耶 0.15 秒）
RING_SLOW = 0.6             # 圈满得慢这么多倍（萨摩耶 ×1.36）
DROP_SHORT_M = 0.5          # 球最多放得比边牧离鼠标远这么多米 × (1 − 聪明程度)（萨摩耶 0～0.30 米，每趟随机）
DAZE_CHANCE, DAZE_S = 0.35, 0.5          # 叼回来的路上愣一下：概率 × (1 − 聪明程度)（萨摩耶约五趟里一趟），愣这么久

# ---- 招牌时刻：强度 × 憨 / 懒 ----
SMILE_EYES, SMILE_EARS, SMILE_LIFT_DEG = 0.75, 0.6, 8.0   # 放下球笑一下：眯眼、耳朵往后、抬一点头 × 憨（萨摩耶 0.45 / 0.36 / 4.8°）
SMILE_WAG, SMILE_S = 0.6, 2.2            # …尾巴至少摇这么欢；笑这么久
TILT_DEG, TILT_S = 24.0, 1.6             # 歪头 × 憨（萨摩耶 14.4°）、歪这么久：被晃到、够不着叫完（路上愣住的歪 DAZE_S）
TILT_AGAIN_S = 25.0                      # 被晃到、路上愣住的歪头演过一次，这么久内不再演（60 次随机扔里一半会被晃到，次次歪头就成了毛病）；够不着叫完的不限
GLANCE = (("ball", 0.5), ("you", 0.6), ("ball", 0.5), ("you", 0.6))   # 呆萌时刻：狗只看着的球停了，看球—看你—看球—看你（秒），之后照常
GLANCE_P = 0.6                           # …触发的概率 × 憨（萨摩耶 0.36，边牧 0）
GLANCE_AGAIN_S = 25.0                    # …演过一次这么久内不再演（和歪头一样，免得成了毛病）
WANDER_EVERY = (60.0, 150.0)             # 自己溜达：没人理多久走一趟（秒，活跃度 1 的边牧；越懒隔得越久）
WANDER_GAP_GROW = 2.0                    # …活跃度每少 1，间隔长这么多倍（萨摩耶 0.5：×2 → 120～300 秒）
WANDER_LYING_GROW = 1.5                  # …趴着（窝里、地上）的间隔再长这么多倍：歇着的狗起得少
GREET_WAG, GREET_S = 0.5, 2.5            # 鼠标靠近：尾巴至少摇这么多 × 憨（萨摩耶 0.30，比拿着球时还小）、摇这么久
GREET_NEAR_DOGS = 0.9                    # …靠近 = 离狗身子正中这么多个身高以内（从外面进来才算一次；敲定方案时从 1.2 收到 0.9）
GREET_AGAIN_S = 20.0                     # …这么久内不重来
LYING_EYES = 0.5                         # 趴着眼睛放松：至少闭这么多 × 懒（萨摩耶 0.25）
CUES = {"put": ("smile", SMILE_S), "fooled": ("tilt", TILT_S), "stumped": ("tilt", TILT_S), "daze": ("tilt", DAZE_S)}   # roam 报的时刻（roam.on_cue）→ 演什么、多久


def _level(tune, key: str) -> float:
    if tune is None:
        return 1.0
    v = tune.get(key, 1.0)
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else float(v)


def energy(tune) -> float:
    """活跃度，夹在 0～1；没接调参、没有这一项是 1。"""
    return _level(tune, "energy")


def smarts(tune) -> float:
    """聪明程度，夹在 0～1；没接调参、没有这一项是 1。"""
    return _level(tune, "smarts")


# ---------- 活跃度 ----------
def gait(d_m: float, tune) -> str:
    """离目标 d_m 米，用哪种步子：fast / run / trot / walk（roam._gait；叼着不快跑是它那边的事）。"""
    e = energy(tune)
    if e >= 1.0:
        return "fast" if d_m > GAIT_FAST_M else "run" if d_m > GAIT_RUN_M else "trot" if d_m > GAIT_TROT_M else "walk"
    slow = 1.0 - e
    if e >= NO_SPRINT_BELOW and d_m > GAIT_FAST_M + FAST_FAR_M * slow:
        return "fast"
    return "run" if d_m > GAIT_RUN_M + RUN_FAR_M * slow else "trot" if d_m > GAIT_TROT_M + TROT_FAR_M * slow else "walk"


def fetch_look(tune) -> float:
    """球扔出去先看多久再追（从没在等的状态起步时；roam.fetch）。"""
    e = energy(tune)
    return FETCH_LOOK if e >= 1.0 else FETCH_LOOK + LOOK_SLOW_S * (1.0 - e)


def release_beat(tune) -> float:
    """俯身等着（或圈满正叫着、正跑着）时你松手，还愣多久才冲（roam.fetch、_bow_step）。"""
    e = energy(tune)
    return 0.0 if e >= 1.0 else RELEASE_BEAT_S * (1.0 - e)


def watch_turn(tune) -> float:
    """站着看球，球到了身后多久才转身（roam._watch）。"""
    e = energy(tune)
    return WATCH_TURN_S if e >= 1.0 else WATCH_TURN_S + WATCH_SLOW_S * (1.0 - e)


def turn_lag(tune) -> float:
    """跟鼠标转身：在调参 turn_delay 上再多等多久（play._follow_body）。"""
    e = energy(tune)
    return 0.0 if e >= 1.0 else TURN_LAG_S * (1.0 - e)


def turn_pace(tune) -> float:
    """跟鼠标转身：调参 turn_speed 再乘多少（dogctl._start_turn）。"""
    e = energy(tune)
    return 1.0 if e >= 1.0 else 1.0 - TURN_PACE_CUT * (1.0 - e)


def turn_rest(tune) -> float:
    """跟鼠标转身：转完在调参 turn_rest 上再多歇多久（dogctl._advance_turn）。"""
    e = energy(tune)
    return 0.0 if e >= 1.0 else TURN_REST_S * (1.0 - e)


def action_every(tune) -> tuple[float, float]:
    """普通随机动作隔多久来一个（秒，最短、最长）。"""
    e = energy(tune)
    if e >= 1.0:
        return ACTION_EVERY
    k = 1.0 + ACTION_GAP_GROW * (1.0 - e)
    return (ACTION_EVERY[0] * k, ACTION_EVERY[1] * k)


def max_up(tune) -> float:
    """一次最多往上跳几个身高：调参 max_up 打折（roam.max_up、window.recommended_scale 两处都读它，推荐大小才跟着对）。"""
    e = energy(tune)
    return tune["max_up"] if e >= 1.0 else tune["max_up"] * (1.0 - MAX_UP_CUT * (1.0 - e))


def sits_by_default(tune) -> bool:
    """灵动交互里默认坐着（萨摩耶，活跃度 REST_ABOVE 以下的）：只有要走的事（追球、叼球、回窝、去吃、被拉去别处）才站起来，
    做完坐回去；拿起球坐着转头看、圈满坐着叫一声、坐着等，松手才站起来追（playground._watch_held_ball、_seated_bark）。边牧照旧站着。"""
    return energy(tune) < REST_ABOVE


def rest_plan(tune) -> Optional[tuple[float, float]]:
    """没人理多久坐下、坐下后再多久趴下（秒）；None = 一直站着（边牧）。playground._lounge 读。默认坐着的狗（萨摩耶）一闲下来就坐（0 秒）。"""
    e = energy(tune)
    if e >= REST_ABOVE:
        return None
    return (0.0, max(LIE_MIN_S, LIE_AFTER_S * e))


def nest_after(tune) -> float:
    """摆了窝：没人理多久走回窝趴下（秒）。自己歇的狗是原来该坐下的那一刻（萨摩耶 20 秒：默认坐着以后也不一闲下来就走开），边牧 NEST_AFTER_S。"""
    e = energy(tune)
    return NEST_AFTER_S if e >= REST_ABOVE else max(SIT_MIN_S, SIT_AFTER_S * e)


def lazy(tune) -> float:
    """懒 = 1 − 活跃度（表情用）。"""
    e = energy(tune)
    return 0.0 if e >= 1.0 else 1.0 - e


# ---------- 聪明程度 ----------
def reads_landing(tune) -> bool:
    """看不看得出球停哪（roam._plan_pickup、_chase_update）：看不出的一直追球本身，球停了才去叼。"""
    return smarts(tune) >= READS_FROM


def chase_lead(tune) -> float:
    """追球本身时瞄它前面多久的位置（roam._chase_point）。"""
    s = smarts(tune)
    return CHASE_LEAD if s >= 1.0 else LEAD_MIN_S + LEAD_GAIN_S * s


def fooled(tune) -> float:
    """追着的球掉头了，愣多久才反应过来刹车（roam._chase_update）。"""
    s = smarts(tune)
    return 0.0 if s >= 1.0 else FOOLED_S * (1.0 - s)


def ring_hold(tune) -> float:
    """球在圈里停多久圈满：调参 ring_hold_s 放长（playground._step_ring；充能的声音跟进度走，自动对上）。"""
    s = smarts(tune)
    return tune["ring_hold_s"] if s >= 1.0 else tune["ring_hold_s"] * (1.0 + RING_SLOW * (1.0 - s))


def drop_short(tune, rng) -> float:
    """这一趟球放得比该放的地方离鼠标远多少米（叼到那一刻定一次，roam._watch_pickup）。聪明程度是 1：0，不碰 rng。"""
    s = smarts(tune)
    return 0.0 if s >= 1.0 else rng.uniform(0.0, DROP_SHORT_M * (1.0 - s))


def daze(tune, rng) -> Optional[float]:
    """这一趟叼回来的路上愣不愣：愣多少秒，不愣 None（叼到那一刻定一次）。聪明程度是 1：None，不碰 rng。"""
    s = smarts(tune)
    if s >= 1.0:
        return None
    return DAZE_S if rng.random() < DAZE_CHANCE * (1.0 - s) else None


def goof(tune) -> float:
    """憨 = 1 − 聪明程度（表情用）。"""
    s = smarts(tune)
    return 0.0 if s >= 1.0 else 1.0 - s


def wander_every(tune) -> tuple[float, float]:
    """自己溜达隔多久一趟（秒，最短、最长；playground._wander）：边牧 60～150，萨摩耶 120～300。两只都不太活跃。"""
    k = 1.0 + WANDER_GAP_GROW * (1.0 - energy(tune))
    return (WANDER_EVERY[0] * k, WANDER_EVERY[1] * k)


def wander_reach(tune) -> tuple[float, float]:
    """自己溜达一趟走多远（米，最近、最远）：0.5 + 0.1 × 活跃度 … 0.5 + 1.3 × 活跃度（边牧 0.6～1.8，萨摩耶 0.55～1.15）。"""
    e = energy(tune)
    return (0.5 + 0.1 * e, 0.5 + 1.3 * e)


def glance_chance(tune) -> float:
    """狗只看着的球停下那一刻，演「看球—看你—看球—看你」的概率（GLANCE_P × 憨）；边牧 0。"""
    return GLANCE_P * goof(tune)


# ---------- 招牌时刻 ----------
@dataclass
class Mood:
    """哪个表情演到什么时候（秒，playground 用 roam.t 当钟）：cue、pointer 记，express 读。"""
    smile_until: float = 0.0
    tilt_until: float = 0.0
    greet_until: float = 0.0
    greet_again_at: float = 0.0         # 打过招呼以后，这之前不再打
    tilt_again_at: float = 0.0          # 被晃到、路上愣住歪过一次头以后，这之前不再歪（够不着叫完的不看它）
    near: bool = True                   # 上一帧鼠标在不在跟前：从远处进来才算一次（一开始当它在：启动时鼠标就在旁边的不算）

    def cue(self, name: str, now: float) -> bool:
        """roam 报了一个时刻（CUES）：笑 / 歪头从现在演起，返回演没演。不认识的不理。
        被晃到、路上愣住来得勤，歪过一次 TILT_AGAIN_S 秒内不再歪；够不着叫完少见，每次都歪。"""
        kind, seconds = CUES.get(name, ("", 0.0))
        if kind == "smile":
            self.smile_until = now + seconds
            return True
        if kind == "tilt":
            if name != "stumped":
                if now < self.tilt_again_at:
                    return False
                self.tilt_again_at = now + TILT_AGAIN_S
            self.tilt_until = now + seconds
            return True
        return False

    def pointer(self, near: bool, now: float, free: bool) -> None:
        """每帧：鼠标这会儿在不在狗跟前。从远处进来、狗闲着（free）、离上次打招呼够久，就打个招呼（尾巴轻轻摇一阵）。"""
        came = near and not self.near
        self.near = near
        if came and free and now >= self.greet_again_at:
            self.greet_until = now + GREET_S
            self.greet_again_at = now + GREET_AGAIN_S


def express(expr, mood: Mood, now: float, goof: float, lazy: float, lying: bool, facing: float) -> None:
    """把招牌时刻叠到表情的目标值上（playground._express 定完尾巴那些以后调；expr 是 widget/expression.py 的 Expression）。
    goof 憨、lazy 懒都是 0（边牧）：直接返回，一个数都不碰。lying：自己歇着、已经趴好。facing：狗朝右 +1 / 朝左 −1（歪头两边看着一样）。"""
    if goof <= 0.0 and lazy <= 0.0:
        return
    if goof > 0.0:
        if now < mood.smile_until:
            expr.eyes, expr.ears, expr.lift = SMILE_EYES * goof, SMILE_EARS * goof, SMILE_LIFT_DEG * goof
            expr.wag = max(expr.wag, SMILE_WAG)
        if now < mood.tilt_until:
            expr.tilt = TILT_DEG * goof * (1.0 if facing < 0.0 else -1.0)
        if now < mood.greet_until:
            expr.wag = max(expr.wag, GREET_WAG * goof)
    if lazy > 0.0 and lying:
        expr.eyes = max(expr.eyes, LYING_EYES * lazy)
