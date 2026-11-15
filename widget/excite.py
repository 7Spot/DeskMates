"""兴奋度：狗此刻有多兴奋，0～1。先有狗的状态，再有这个值：只从狗这一刻在干什么、刚发生了什么算出来，
再让尾巴这类小动作跟着它走（window._feel）。狗去哪、追不追、坐不坐都不看它（tests/test_excite.py 查着）。
性子（活跃度、聪明程度，widget/temper.py）不进这里：萨摩耶坐着、趴着的时候多，算出来自然就平静些。

两种来源：
- 持续的状态：每种状态一个「该有多兴奋」的数（TARGETS），兴奋度往它靠，往上快（RISE_S）、往下慢（FALL_S）：来得快、退得慢。
- 一下子的事：在当前值上加一点（KICK_*）或一下子提到某个值（lift_to），再按 FALL_S 慢慢落回状态的数。
  点它一下、很久没理它鼠标又过来了（打招呼）、球撞墙弹回来、圈满以后扔出去。睡着的狗点它、跟它打招呼都不加。
- 被拎着、飞着不算（target 返回 None）：兴奋度停在原处。
表现：尾巴摇多欢（expression.Expression.wag：快慢、幅度、翘多高）= wag(兴奋度)。WAG_FROM 以下尾巴不多摇：
站着待着、坐着、趴着、睡着和没有兴奋度时一样，有事了才看得出来。纯数学，不碰 Qt。"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

RISE_S, FALL_S = 0.5, 10.0      # 往上追的时间常数（秒，快）、往下落的（慢）
WAG_FROM = 0.2                  # 兴奋度到这以上尾巴才多摇（站着待着是 0.2）
TARGETS = {                     # 狗在干什么 → 兴奋度往哪靠
    "sleeping": 0.0,
    "lying": 0.1,
    "sitting": 0.15,
    "standing": 0.2,
    "wandering": 0.3,           # 自己溜达、走回窝
    "near_you": 0.35,           # 鼠标在狗身边动
    "eating": 0.5,              # 吃喝
    "carrying": 0.7,            # 叼着球回来
    "chasing": 0.9,             # 追球
    "bowing": 0.95,             # 圈满、俯身等你扔
}
BALL_FROM, BALL_TO = 0.4, 0.85  # 拿着球给它看：随圈从这么多涨到这么多
KICK_TAP = 0.15                 # 点它一下
KICK_GREET = 0.3                # 很久没理它、鼠标又过来了（打招呼）
KICK_BOUNCE = 0.1               # 球撞到窗口边上弹回来
GREET_AFTER_S = 60.0            # 鼠标离开狗身边（或停着）这么久再过来，才算「很久没理它」


@dataclass
class Scene:
    """这一刻狗在干什么（window._feel 每帧问一次；灵动交互开着时 playground.excite_scene 填球和跑的那几项）。"""
    posture: str = "standing"           # standing / sitting / lying / sleeping
    near_you: bool = False              # 鼠标在狗身边动
    task: Optional[str] = None          # 灵动交互里狗在做的事（roam.task）：wander、nest、eat、fetch……
    ball_shown: Optional[float] = None  # 你拿着球给它看：圈满了几成（0～1）；没拿着是 None
    bowing: bool = False                # 圈满了，俯身等你扔
    carrying: bool = False              # 球叼在嘴里
    held: bool = False                  # 被拎着、飞着


def target(s: Scene) -> Optional[float]:
    """这一刻的状态该有多兴奋；被拎着、飞着不算（None：兴奋度停在原处）。"""
    if s.held:
        return None
    if s.bowing:
        return TARGETS["bowing"]
    if s.ball_shown is not None:
        return BALL_FROM + (BALL_TO - BALL_FROM) * min(1.0, max(0.0, s.ball_shown))
    if s.carrying:
        return TARGETS["carrying"]
    if s.task == "fetch":
        return TARGETS["chasing"]
    if s.task == "eat":
        return TARGETS["eating"]
    if s.posture == "sleeping":
        return TARGETS["sleeping"]
    goal = TARGETS.get(s.posture, TARGETS["standing"])
    if s.task in ("wander", "nest"):
        goal = max(goal, TARGETS["wandering"])
    if s.near_you:
        goal = max(goal, TARGETS["near_you"])
    return goal


def wag(value: float) -> float:
    """兴奋度 → 尾巴摇多欢（0～1）：WAG_FROM 以下不多摇，往上照比例摇快、摇大、翘起来。"""
    return max(0.0, min(1.0, (value - WAG_FROM) / (1.0 - WAG_FROM)))


class Excite:
    """一只狗的兴奋度（狗的控制器上一份：换模型就是新的一份，从 0 算起）。"""

    def __init__(self) -> None:
        self.value = 0.0

    def step(self, dt: float, goal: Optional[float]) -> None:
        """往这一刻状态的数靠一帧：往上按 RISE_S，往下按 FALL_S；goal 是 None（被拎着、飞着）不动。"""
        if goal is None or dt <= 0.0:
            return
        tau = RISE_S if goal > self.value else FALL_S
        self.value += (goal - self.value) * (1.0 - math.exp(-dt / tau))

    def kick(self, amount: float) -> None:
        """一下子的事：加一点（不超过 1）。"""
        self.value = min(1.0, self.value + amount)

    def lift_to(self, value: float) -> None:
        """一下子提到这么多（本来更高就不动）。"""
        self.value = max(self.value, min(1.0, value))
