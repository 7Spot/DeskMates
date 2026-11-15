"""手有多快：拿着东西（狗、球）时记下鼠标每个事件的位置和时间，松手时算手的速度。纯数学，不碰 Qt。
松手事件丢了怎么办（LostRelease：键松开多久还没等到松手，球和物件共用）也在这。

时间用系统给事件打的时间戳（event_time），不用程序处理到它的时刻（甩狗"卡在半空、惯性没了"）：
主线程卡住时事件在排队，松手和最后一次移动明明只差 28 毫秒，程序却隔了 400 毫秒才处理到。按处理时刻算，手就"早停了"（速度 0，狗当场掉）；
卡完事件一口气进来又间隔极短（速度算出每秒几十万像素）。真实录制的 43 次松手里 15 次算错，按系统时间戳全部恢复。

系统把排队的移动事件合并时，位置是这一批最后的，时间戳却是这一批最早的。所以每个位置算在下一个事件的时间上（_timeline），
再取一段时间里的总位移除以时间，不看单个事件，个别事件间隔很小也不会算出离谱的速度。"""
from __future__ import annotations

import math
import time
from typing import Iterable, Sequence

Sample = tuple[float, float, float]         # (时间, x, y)

EVENT_CLOCK_SLACK = 30.0                    # 事件的时间戳和现在差这么多（秒）就不是同一个钟（测试、自己造的事件）


def event_time(event) -> float:
    """这个鼠标事件发生的时刻（秒，macOS 上和 time.perf_counter 是同一个钟）。没有时间戳或钟对不上就用现在。"""
    now = time.perf_counter()
    stamp = event.timestamp() / 1000.0
    return stamp if 0.0 <= now - stamp < EVENT_CLOCK_SLACK else now


class LostRelease:
    """按着东西（球、物件）时鼠标键其实已经松开、松手事件却一直没来（按着的时候切走了、系统弹窗）：数它松开了多久。
    只在这次按着的时候真看到过键按着才算：自测脚本、离屏测试里的「按着」是假的，没有真按键。每次开始按着 reset()，之后每帧 gone()。"""

    def __init__(self) -> None:
        self.seen, self.up_for = False, 0.0

    def reset(self) -> None:
        self.seen, self.up_for = False, 0.0

    def gone(self, down, dt: float, after: float) -> bool:
        """down：鼠标键现在按没按着（None = 问不到）。键松开满 after 秒还没等到松手事件：返回 True（当松了手）。"""
        if down:
            self.seen, self.up_for = True, 0.0
            return False
        if down is None or not self.seen:
            return False
        self.up_for += dt                         # 按帧加（一帧最多算 0.1 秒）：程序卡住时排着的松手事件先到
        return self.up_for >= after


def _timeline(samples: Sequence[Sample], end: float) -> list[Sample]:
    """每个位置算在下一个事件的时间上，最后一个算在 end（一般是松手的时刻）。end 就是最后一个样本的时刻（松手那个事件本身、每帧读一次鼠标）：
    这一个样本后面没有时间了，不算它（不然一下子多出一段位移，速度偏大）。"""
    out = [samples[0]]
    for (t, _, _), (_, x, y) in zip(samples[1:], samples):
        out.append((t, x, y))
    if end > samples[-1][0]:
        out.append((end, samples[-1][1], samples[-1][2]))
    return out


def _position(line: Sequence[Sample], t: float) -> tuple[float, float]:
    """t 时刻手在哪（两个点之间按直线）。"""
    if t <= line[0][0]:
        return line[0][1], line[0][2]
    for (t0, x0, y0), (t1, x1, y1) in zip(line, line[1:]):
        if t < t1:
            k = (t - t0) / (t1 - t0)
            return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
    return line[-1][1], line[-1][2]


def velocity(samples: Iterable[Sample], end: float, window: float) -> tuple[float, float]:
    """end 之前 window 秒的平均速度（像素 / 秒）：总位移 ÷ 时间。不够两个样本是 0。"""
    points = list(samples)
    if len(points) < 2:
        return 0.0, 0.0
    return _velocity(_timeline(points, end), end, window)


def _velocity(line: Sequence[Sample], end: float, window: float) -> tuple[float, float]:
    start = max(end - window, line[0][0])
    span = end - start
    if span < 1e-3:
        return 0.0, 0.0
    x0, y0 = _position(line, start)
    x1, y1 = _position(line, end)
    return (x1 - x0) / span, (y1 - y0) / span


def peak_velocity(samples: Iterable[Sample], end: float, sample: float, window: float, fade: float, step: float = 0.008) -> tuple[float, float]:
    """松手前 window 秒里最快的那一段（每段长 sample 秒），越早的越打折（时间常数 fade）：
    边甩边松的就是松手那一下；先停一下再松的也扔得出去；放稳了才松的接近 0。"""
    points = list(samples)
    if len(points) < 2:
        return 0.0, 0.0
    line = _timeline(points, end)
    best, out = 0.0, (0.0, 0.0)
    back = 0.0
    while back <= window:
        vx, vy = _velocity(line, end - back, sample)
        k = math.exp(-back / fade)
        speed = math.hypot(vx, vy) * k
        if speed > best:
            best, out = speed, (vx * k, vy * k)
        back += step
    return out
