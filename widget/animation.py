"""界面动画的基础积木：帧调度、临界阻尼弹簧、连续颜色进度。"""
from __future__ import annotations

import math
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget
import config
from widget.geometry import frame_period
from widget.capture_ui import ui_frozen

class FrameClock:
    """一个窗口的动画节拍：有东西在动就挂到狗窗口的每一帧上（host.request_frames：卡片一个计时器、Qt 自带的动画一个、狗一个，
    互相挤，帧间隔 5～50 毫秒乱跳），狗看不见、没有狗窗口时用自己的精确单次计时器，按窗口所在屏幕的刷新率一格格排，卡了就从现在重排、不补帧。
    每帧推进的时间最多 1.5 帧：卡一下只慢一点，不跳一大截。step(dt) 返回下一帧还要不要接着算，不动就停。
    狗窗口要问它三样：isVisible / frame_step / own_clock。"""
    default_host = None                           # 狗的窗口（window.attach_panels 设）：卡片、菜单、提示都挂它

    def __init__(self, widget: QWidget, step):
        self.widget, self.step = widget, step
        self.host = None                          # 不设就用 default_host
        self._timer = QTimer(widget)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._frame)
        self.running = self._own = False
        self._period = 1.0 / config.ANIM_FPS
        self._next = self._last = 0.0
        widget.destroyed.connect(self._gone)

    def isVisible(self) -> bool:
        try:
            return self.widget.isVisible()
        except RuntimeError:                      # 窗口已经删了（换语言 / 外观时卡片整张重建）
            return False

    def _gone(self, *_) -> None:
        """窗口删掉了：狗别再推它（换语言时旧卡片还挂在狗的帧上，狗的下一帧一问它就出错，帧循环断了，整个小组件像卡死）。"""
        self.running = self._own = False
        host = self.host or FrameClock.default_host
        try:
            if host is not None:
                host.release_frames(self)
        except (RuntimeError, AttributeError):
            pass

    def start(self) -> None:
        """有东西要动了。已经在走就不管（0.25 秒没走过一帧的算断了——窗口藏起来时狗把它扔了——重新挂）。"""
        now = time.perf_counter()
        if not self.isVisible() or (self.running and now - self._last < 0.25):
            return
        self.running, self._own = True, False
        self._timer.stop()
        screen = self.widget.screen()
        self._period = frame_period(screen.refreshRate() if screen is not None else 0.0, config.ANIM_FPS, config.ANIM_MAX_FPS)
        self._next = self._last = now
        host = self.host or FrameClock.default_host
        if host is not None and host.can_drive_frames():
            host.request_frames(self)
        else:
            self.own_clock()

    def own_clock(self) -> None:
        """狗不推了（看不见了）：接着用自己的节拍走完。"""
        if self.running and not self._own:
            self._own = True
            self._next = time.perf_counter()
            self._timer.start(0)

    def frame_step(self, now: float, period: float) -> bool:
        """往前走一帧；返回还要不要下一帧。狗的窗口每帧调它，或者自己的节拍调。"""
        if not self.running:
            return False
        dt, self._last = min(max(0.0, now - self._last), 1.5 * period), now
        if ui_frozen():
            return True                        # 只暂停UI；保留running，不让狗的主时钟停掉
        if not self.step(dt):
            self.running = False
        return self.running

    def _frame(self) -> None:
        now = time.perf_counter()
        if not self.frame_step(now, self._period):
            self._own = False
            return
        self._next += self._period
        if self._next < now:
            self._next = now + self._period
        self._timer.start(max(0, round((self._next - now) * 1000)))

    def stop(self) -> None:
        self._timer.stop()
        self.running = self._own = False


class Spring:
    """临界阻尼弹簧（不回弹）：改目标时保留当前速度，所以连续改（打字）是匀匀地变，不会每改一次就从快到慢重新冲一下。
    response 秒基本到位（和苹果系统里不回弹的平滑动画同一类）；step 用解析解，帧间隔不均匀也稳。
    eps：离目标不到 eps、又比每秒 50 × eps 慢就算停稳、直接到位。默认 0.02 是按像素定的；0..1 的进度用 1e-3、对数用 1e-4，
    不然最后那一截一下跳过去，看得出来（放大两倍时 2% 是 5～10 像素）。
    set_target 是跟手连续改（保留速度）；retarget 是换一个新去处（离开一页、按开关）：不过头、不先往反方向冲一段再回来。"""

    def __init__(self, value: float = 0.0, response: float = 0.3, eps: float = 0.02):
        self.value = self.target = float(value)
        self.velocity = 0.0
        self.omega = 2.0 * math.pi / response
        self.eps = eps

    def set_target(self, target: float, instant: bool = False) -> None:
        self.target = float(target)
        if instant:
            self.value, self.velocity = self.target, 0.0

    def retarget(self, target: float, response: Optional[float] = None, instant: bool = False) -> None:
        """换个去处，一路单调地过去：正往反方向跑的先停住；朝着它但冲得太快（会冲过头）的压到刚好停在它上面（c = 0，见 step）。
        response 给了就换快慢。"""
        if response is not None:
            self.omega = 2.0 * math.pi / response
        self.target = float(target)
        if instant:
            self.value, self.velocity = self.target, 0.0
            return
        d, v = self.value - self.target, self.velocity
        if d * v > 0.0:
            self.velocity = 0.0                       # 往远处跑着：先停住，不再往外冲一段
        elif abs(v) > self.omega * abs(d):
            self.velocity = -self.omega * d           # 冲得太快：c = v + ω·d = 0，正好停在目标上

    def step(self, dt: float) -> None:
        d0, v0, w = self.value - self.target, self.velocity, self.omega
        c = v0 + w * d0
        e = math.exp(-w * dt)
        self.value = self.target + (d0 + c * dt) * e
        self.velocity = (v0 - w * c * dt) * e
        if abs(self.value - self.target) < self.eps and abs(self.velocity) < 50.0 * self.eps:
            self.value, self.velocity = self.target, 0.0

    @property
    def settled(self) -> bool:
        return self.value == self.target and self.velocity == 0.0


class Tween:
    """单个0..1进度的平滑过渡；改目标从当前值接续。"""
    def __init__(self, value: float = 0.0, duration: float = 0.12):
        self.value = self.target = self.origin = float(value)
        self.duration = duration
        self.elapsed = duration

    def set_target(self, value: float, instant: bool = False) -> None:
        if value == self.target and not instant:
            return
        self.origin, self.target, self.elapsed = self.value, float(value), 0.0
        if instant:
            self.value, self.elapsed = self.target, self.duration

    def step(self, dt: float) -> None:
        self.elapsed = min(self.duration, self.elapsed + dt)
        u = self.elapsed / self.duration
        self.value = self.origin + (self.target - self.origin) * u * u * (3 - 2 * u)

    @property
    def settled(self) -> bool:
        return self.elapsed >= self.duration
