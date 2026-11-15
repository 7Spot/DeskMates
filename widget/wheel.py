"""滚轮、触摸板的滚动事件 → 一步一步翻（两种设备都是「一次动作换一只」）。只看 QWheelEvent，不碰界面、不认识狗：
「我的同桌」滑动条用 WheelSteps；以后别的按格走的东西（比如看细节的转盘尺）先用 is_notch 分出带格的滚轮。

macOS 上 Qt 给的滚动事件（照 Qt 源码 qnsview_mouse.mm 推断）：
- 带格的普通滚轮：没有滚动阶段，angleDelta 每格 ±120。它也带 pixelDelta（Qt 按一行 20 像素估），所以不能拿 pixelDelta 空不空来分。
- 精确位移（触摸板、Magic Mouse、开着平滑滚动的鼠标，比如 MX Master 3S + Logi Options+）：source() 是 MouseEventSynthesizedBySystem，
  angleDelta = 2 × pixelDelta；触摸板还带阶段（ScrollBegin / ScrollUpdate / ScrollEnd，松手后系统补的 ScrollMomentum）。
  有惯性跟着时，手指抬起那一下的 ScrollEnd 常被吞掉，惯性的第一个事件又报成 ScrollUpdate，所以不靠 ScrollEnd 分一次一次的动作。
方向：往下 / 往左（负的）= 往后一步（正数）。位移照系统给的用，「自然滚动」系统已经算进去了，不看 inverted()，和别的滚动一个方向。"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt

NOTCH = 120              # 带格的滚轮一格（angleDelta）；整数：要取余、整除
SWIPE_PX = 20.0          # 精确位移：一次动作攒到这么多像素就翻一步，这一次剩下的（连惯性）全不要
SWIPE_GAP_MS = 150       # 停这么久没有位移才算下一次动作（手指重新放上去 ScrollBegin 不用等）


def _major(x: float, y: float) -> float:
    """横竖哪边大取哪边（一样大取竖的）。"""
    return x if abs(x) > abs(y) else y


def is_notch(event) -> bool:
    """这一下是带格的普通滚轮（一格一格转的）：没有滚动阶段、不是系统合成的精确位移、angleDelta 是整格。"""
    if event.phase() != Qt.NoScrollPhase or event.source() == Qt.MouseEventSynthesizedBySystem:
        return False
    a = event.angleDelta()
    d = _major(a.x(), a.y())
    return d != 0 and d % NOTCH == 0


def notches(event) -> int:
    """带格的滚轮这一下转了几格（is_notch 为真时才有意义）：往下 / 往左是正数（往后）。"""
    a = event.angleDelta()
    return -_major(a.x(), a.y()) // NOTCH


class WheelSteps:
    """一串滚动事件 → 这一下翻几步（feed 返回 0 不动，正数往后，负数往前）。
    - 带格的滚轮：一格一步，转快了也是一格一步。
    - 精确位移：一串连续的是一次动作，横竖分开攒，攒到 SWIPE_PX 就朝那边翻一步，这一串剩下的全不要。停 SWIPE_GAP_MS 没有位移、
      或手指重新放上去（ScrollBegin）才算下一次；惯性（ScrollMomentum）永远是上一次的尾巴，开不了新的一次（还没翻过的那一次可以由它补满）。
    - 时间用事件自己的时间戳（毫秒），不用计时器：主线程卡一下、几个事件挤在一起到，也不会把一次拆成两次。时间戳是 0（代码里造的事件）才看现在的钟。
    - 手指放上去、按着不动、抬起（位移是 0 的事件）不算在动：不续这一次的命。"""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """从头算（滑动条进详情页、藏起来时）。"""
        self._x = self._y = 0.0                 # 这一次攒着的位移（像素）
        self._spent = False                     # 这一次已经翻过一步了
        self._last: Optional[int] = None        # 上一个有位移的事件的时间（毫秒）

    def feed(self, event) -> int:
        """喂一个 QWheelEvent，返回要翻几步。"""
        if is_notch(event):
            return notches(event)
        phase = event.phase()
        px, ang = event.pixelDelta(), event.angleDelta()
        dx, dy = (px.x(), px.y()) if not px.isNull() else (ang.x() / 2.0, ang.y() / 2.0)   # 只给了角度：精确位移的角度是像素的 2 倍
        t = event.timestamp() or round(time.monotonic() * 1000.0)
        if phase == Qt.ScrollBegin or self._last is None or not 0 <= t - self._last < SWIPE_GAP_MS:
            self._x = self._y = 0.0                                # 新的一次
            self._spent = phase == Qt.ScrollMomentum               # 停了一会儿才到的惯性：还是上一次的，不翻
        if not (dx or dy):
            return 0
        self._last = t
        if self._spent:
            return 0
        self._x += dx
        self._y += dy
        d = _major(self._x, self._y)
        if abs(d) < SWIPE_PX:
            return 0
        self._spent = True
        return 1 if d < 0 else -1
