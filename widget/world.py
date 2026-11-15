"""灵动交互的"空间"：纯几何和物理，不碰 Qt，能单测。

坐标：全局逻辑像素（和 Qt 的屏幕坐标一样，原点在主屏左上，y 向下）。
- 每块屏的可用区域（去掉菜单栏和 Dock）是一个"房间"（Area）。几块屏拼起来就是整个空间：两块屏挨着的那条边是通的，
  别的边是墙。每个房间的地面是可用区域底边往上 floor_margin（给狗的影子留地方），地面只挡往下掉的（从下面那块屏往上扔的球能穿上来）。
- 上下摆的两块屏（球扔到上面那块屏该掉到下面那块）：上面那块的底边、正下方挨着另一块屏的那一段不是地面，是通的；
  中间隔着的那条（下面那块屏的菜单栏、上面那块屏的 Dock）是"过道"（passage），球和狗都穿得过去。只有底下没有屏的那段底边才是地面。
- 球（Ball）：重力、撞墙反弹、落地弹几下、滚、停。窗口从外面撞是实心的：上沿接住往下掉的球，左右两边、下边把球弹回去；
  球本来就在窗口前面（和它重叠）时不挡，等它出来。只算看得见的那段边。不撞狗（狗是去叼它的）。
- 能站的地方（Support）：每块屏的地面，和窗口的上边沿（看得见的那几段）。狗在这些横线之间跑、跳上去、跳下来（plan_route）。
- 窗口是方盒子：往上跳先跑到窗口左边或右边的外面，越过窗口边落到顶上；往下跳先走到顶边的一端，往外跳（Leaper）。
  起跳前量那一头有没有空地：够就往前蹬、飞出去；不够就走到边上，后脚踩在边上，身子往下探，直接落下去（不往上蹦）；
  再不够这段路就不通（狗叫两声）。上和下用同一个门槛，狗不会自己跳上去就下不来。空地可以算到连着的另一块屏：
  只看狗飞过的那个高度那边真有没有屏。
  路线按人眼看到的前后算（球放在中间低洼的窗口顶上，狗不能隔着前面的窗口直接跳上去，只能从最右边上）：飞的这一路穿过一个窗口（两头的窗口不算），
  而那个窗口在两头的窗口里靠后那个的前面，这条路就不通。从地面跳上一个窗口：挡在它前面的挡；在它后面但比它矮的也挡（窗口是方盒子，矮盒子得先站上去）；
  在它后面又比它高的不挡，那是背景（真机：后面开着一个大窗口，狗从地面哪都跳不上去）。在线上跑、在两块屏的地面之间跳不算，盖满整块屏的窗口也不算。
  往上跳有高度上限，往下跳不限（落差太大的多绕台阶）；屏和屏之间地面不一样高时，在交界处跳上 / 跳下。"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

GRAVITY_M = 9.8            # 米 / 秒²：按狗的比例尺换成像素（ppm）
BALL_E_FLOOR = 0.52        # 落地反弹系数
BALL_E_WALL = 0.62         # 撞墙
BALL_E_CEIL = 0.45         # 撞天花板（菜单栏下沿）
BALL_FLOOR_KEEP = 0.86     # 每次落地横向剩多少速度
BALL_ROLL_DECEL_M = 2.2    # 在地上滚的减速度（米 / 秒²）
BALL_REST_BOUNCE_M = 0.55  # 落地时竖直速度小于这个（米 / 秒）就不再弹，贴地滚
BALL_STOP_M = 0.05         # 滚得比这个慢（米 / 秒）就停
BALL_MAX_SPEED_M = 22.0    # 扔出去最快多快（米 / 秒）
EPS = 0.5


@dataclass(frozen=True)
class Area:
    """一块屏的可用区域（逻辑像素）：right / bottom 是开区间的边（left + width）。"""
    left: float
    top: float
    right: float
    bottom: float
    name: str = ""

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class Support:
    """一条能站的横线：x0..x1 在 y 高度。kind = floor（屏的地面）/ window（窗口上沿）；key = 屏的序号 / 窗口号。"""
    x0: float
    x1: float
    y: float
    kind: str
    key: int

    def covers(self, x: float, margin: float = 0.0) -> bool:
        return self.x0 + margin <= x <= self.x1 - margin

    def clamp(self, x: float, margin: float = 0.0) -> float:
        lo, hi = self.x0 + margin, self.x1 - margin
        if lo > hi:
            return (self.x0 + self.x1) / 2
        return min(max(x, lo), hi)


@dataclass(frozen=True)
class WindowFrame:
    """屏幕上一个普通窗口（native.window_frames 读出来的）：窗口号、进程、矩形。列表从最前面到最后面。"""
    number: int
    pid: int
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class Edge:
    """窗口的一条边里看得见的一段，只从窗口外面撞才挡球：side = left / right（竖的：at 是 x，lo..hi 是 y）
    / bottom（横的：at 是 y，lo..hi 是 x）。key = 窗口号。上沿不在这里（它是 Support，能接住球、能站狗）。"""
    side: str
    at: float
    lo: float
    hi: float
    key: int


PASSAGE_MAX = 160.0        # 上下两块屏的可用区域之间隔着多高以内算挨着（下面那块的菜单栏 + 上面那块的 Dock）


class World:
    """几块屏拼成的空间。floor_margin：地面离可用区域底边多少像素（狗的影子画在脚下这一条里）。
    screens：每块屏的整块区域（含菜单栏、Dock），和 areas 一一对应，用来认出上下挨着的两块屏；不给就按可用区域算（只认正好贴着的）。"""

    def __init__(self, areas: Sequence[Area], floor_margin: float, screens: Optional[Sequence[Area]] = None):
        self.areas = list(areas)
        self.screens = list(screens) if screens is not None else None
        self.floor_margin = floor_margin
        self.passages, below = self._passages(self.screens)
        self.floors = self._floors(below)

    # ---- 房间、墙 ----
    def area_index(self, x: float, y: float) -> Optional[int]:
        for i, a in enumerate(self.areas):
            if a.contains(x, y):
                return i
        return None

    def room_at(self, x: float, y: float) -> Optional[Area]:
        """(x, y) 所在的房间：某块屏的可用区域，或上下两块屏之间的过道；都不在 None（墙里）。"""
        i = self.area_index(x, y)
        if i is not None:
            return self.areas[i]
        return next((p for p in self.passages if p.contains(x, y)), None)

    def is_open(self, x: float, y: float) -> bool:
        return self.room_at(x, y) is not None

    def floor_y(self, i: int) -> float:
        return self.areas[i].bottom - self.floor_margin

    def screen_top(self, i: int) -> float:
        """那块屏的最上沿（含菜单栏）；没给整块屏的区域就是可用区域的顶。"""
        return self.screens[i].top if self.screens is not None else self.areas[i].top

    def dog_open(self, x: float, y: float) -> bool:
        """这一点在不在某块屏里（狗画在菜单栏上面，整块屏都能飞；球只在可用区域里）。"""
        return any(a.contains(x, y) for a in (self.screens if self.screens is not None else self.areas))

    def _passages(self, screens: Optional[list[Area]]) -> tuple[list[Area], dict[int, list[tuple[float, float]]]]:
        """上下挨着的两块屏：中间那条过道（两块的可用区域横向重叠的那一段，从上面那块可用区域的底到下面那块可用区域的顶），
        和每块屏底边下面挨着别的屏的那几段 x（这几段不是地面）。"""
        passages: list[Area] = []
        below: dict[int, list[tuple[float, float]]] = {}
        for i, a in enumerate(self.areas):
            for j, b in enumerate(self.areas):
                if i == j:
                    continue
                if screens is not None:
                    touching = abs(screens[i].bottom - screens[j].top) <= 2.0
                else:
                    touching = abs(a.bottom - b.top) <= 0.5
                gap = b.top - a.bottom
                x0, x1 = max(a.left, b.left), min(a.right, b.right)
                if not touching or x1 - x0 < 1.0 or gap < -0.5 or gap > PASSAGE_MAX:
                    continue
                below.setdefault(i, []).append((x0, x1))
                if gap > 0.5:
                    passages.append(Area(x0, a.bottom, x1, b.top, f"passage {a.name}→{b.name}"))
        return passages, below

    def _floors(self, below: dict[int, list[tuple[float, float]]]) -> list[Support]:
        """每块屏一条地面（底下挨着别的屏的那几段去掉，可能断成几截）。两块屏底边一样高也不连成一条：狗过屏幕交界时纵身一跃
        （macOS 默认每块屏是单独的空间，窗口骑在两块屏中间时只显示在一块上；一跃而过只是一瞬间，看着像跳过屏幕边框，不会慢慢少半个身子）。"""
        floors = []
        for i, a in enumerate(self.areas):
            spans = [(a.left, a.right)]
            for x0, x1 in below.get(i, ()):
                spans = _subtract(spans, x0, x1)
            floors += [Support(x0, x1, a.bottom - self.floor_margin, "floor", i) for x0, x1 in spans if x1 - x0 >= 2.0]
        return floors

    def floor_at(self, x: float, y: float) -> Optional[Support]:
        """(x, y) 正下方最近的地面（同一列里比 y 低或一样高的那条）。"""
        best = None
        for s in self.floors:
            if s.covers(x) and s.y >= y - EPS and (best is None or s.y < best.y):
                best = s
        return best

    def floor_above(self, x: float, y: float) -> Optional[Support]:
        """(x, y) 上面最近的那条地面（盖得住 x、比 y 高）：程序坞出来以后，站在它那一带的狗、球该上到哪（playground.floor_changed）。"""
        best = None
        for s in self.floors:
            if s.covers(x) and s.y < y - EPS and (best is None or s.y > best.y):
                best = s
        return best

    def nearest_floor(self, x: float, y: float) -> Support:
        """离 (x, y) 最近的地面（屏幕拔掉、窗口挪到空白处时兜底）。"""
        def d(s: Support) -> float:
            cx = s.clamp(x)
            return math.hypot(cx - x, s.y - y)
        return min(self.floors, key=d)

    # ---- 能站的地方 ----
    def window_tops(self, frames: Sequence[WindowFrame], min_width: float, headroom: float,
                    from_screen_top: bool = False) -> list[Support]:
        """窗口上沿里看得见、站得下的那几段。frames 从最前到最后；被前面的窗口盖住的部分去掉；
        上沿离那块屏的顶不到 headroom 的不算（from_screen_top：从整块屏的最上沿量，狗用——它画在菜单栏上面，头能伸进菜单栏那条；
        不然从可用区域的顶、也就是菜单栏下沿量，球用）；窄于 min_width 的不算；盖满整块屏的（全屏、最大化）也不算。"""
        out: list[Support] = []
        for k, f in enumerate(frames):
            y = f.y
            i = None
            for px in (f.x + f.w / 2, f.x + 12, f.x + f.w - 12):        # 上沿中点不在屏上（窗口一半拖出屏外）就看两头
                i = self.area_index(px, y + 1)
                if i is not None:
                    break
            if i is None:
                continue
            a = self.areas[i]
            if y - (self.screen_top(i) if from_screen_top else a.top) < headroom or y >= self.floor_y(i) - 4:
                continue
            if f.w >= (a.right - a.left) - 2 and f.h >= (a.bottom - a.top) - 2:
                continue
            spans = [(max(f.x, a.left), min(f.x + f.w, a.right))]
            for g in frames[:k]:                                      # 前面的窗口盖住上沿的部分去掉
                if g.y <= y <= g.y + g.h:
                    spans = _subtract(spans, g.x, g.x + g.w)
            for x0, x1 in spans:
                if x1 - x0 >= min_width:
                    out.append(Support(x0, x1, y, "window", f.number))
        return out

    def _area_of(self, f: WindowFrame) -> Optional[int]:
        for px, py in ((f.x + f.w / 2, f.y + 1), (f.x + 12, f.y + 1), (f.x + f.w - 12, f.y + 1), (f.x + f.w / 2, f.y + f.h / 2)):
            i = self.area_index(px, py)
            if i is not None:
                return i
        return None

    def window_edges(self, frames: Sequence[WindowFrame]) -> list[Edge]:
        """窗口的左、右、下边里看得见的那几段（球从外面撞上来会弹回去）。frames 从最前到最后；被前面的窗口盖住的部分去掉；
        盖满整块屏的（全屏、最大化）不算；贴着屏幕左右边的那条边不要（那里本来就是墙）；竖边最多到地面，下边在地面以下的不要。"""
        out: list[Edge] = []
        for k, f in enumerate(frames):
            i = self._area_of(f)
            if i is None:
                continue
            a = self.areas[i]
            if f.w >= (a.right - a.left) - 2 and f.h >= (a.bottom - a.top) - 2:
                continue
            front = frames[:k]
            top, bottom = max(f.y, a.top), min(f.y + f.h, self.floor_y(i))
            for side, x in (("left", f.x), ("right", f.x + f.w)):
                if not (a.left + 2 < x < a.right - 2) or bottom - top < 2:
                    continue
                spans = [(top, bottom)]
                for g in front:
                    if g.x <= x <= g.x + g.w:
                        spans = _subtract(spans, g.y, g.y + g.h)
                out += [Edge(side, x, lo, hi, f.number) for lo, hi in spans if hi - lo >= 2]
            y = f.y + f.h
            if a.top + 2 < y < self.floor_y(i) - 2:
                spans = [(max(f.x, a.left), min(f.x + f.w, a.right))]
                for g in front:
                    if g.y <= y <= g.y + g.h:
                        spans = _subtract(spans, g.x, g.x + g.w)
                out += [Edge("bottom", y, lo, hi, f.number) for lo, hi in spans if hi - lo >= 2]
        return out


def _subtract(spans: list[tuple[float, float]], c0: float, c1: float) -> list[tuple[float, float]]:
    out = []
    for a, b in spans:
        if c1 <= a or c0 >= b:
            out.append((a, b))
            continue
        if c0 > a:
            out.append((a, c0))
        if c1 < b:
            out.append((c1, b))
    return out


# ---------------- 球 ----------------
@dataclass(frozen=True)
class BallPhysics:
    """球的物理能调的那几个（开发者设置页）：落地、撞墙反弹系数，滚多远（1 = 默认，大了减速慢）。"""
    e_floor: float = BALL_E_FLOOR
    e_wall: float = BALL_E_WALL
    roll_gain: float = 1.0


DEFAULT_PHYSICS = BallPhysics()


@dataclass
class Ball:
    """球的状态：中心 (x, y)、速度、半径（像素）；rolling = 贴着地面滚；resting = 停在地上。spin 是滚过的角度（画缝线用）。"""
    x: float
    y: float
    r: float
    vx: float = 0.0
    vy: float = 0.0
    rolling: bool = False
    resting: bool = True
    spin: float = 0.0
    bounces: int = 0
    on: Optional[tuple[str, int]] = None     # 停 / 滚在哪条线上：(kind, key)；窗口上沿的，窗口挪了球跟着挪
    impact: float = 0.0                      # 这一步撞得最重的那下（像素 / 秒，垂直于撞的面）：声音按它，外面用完清零

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def throw(self, vx: float, vy: float, ppm: float) -> None:
        cap = BALL_MAX_SPEED_M * ppm
        s = math.hypot(vx, vy)
        if s > cap:
            vx, vy = vx * cap / s, vy * cap / s
        self.vx, self.vy = vx, vy
        self.rolling = self.resting = False
        self.bounces = 0
        self.on = None


def _ground(world: World, platforms: Sequence[Support], x: float, bottom: float, tol: float = 1.0) -> Optional[Support]:
    """球底下贴着的那条线（地面或窗口上沿），容差 tol 像素。"""
    best = None
    for s in list(world.floors) + list(platforms):
        if s.covers(x) and abs(s.y - bottom) <= tol and (best is None or s.y < best.y):
            best = s
    return best


def step_ball(world: World, b: Ball, dt: float, ppm: float, platforms: Sequence[Support] = (), edges: Sequence[Edge] = (),
              phys: BallPhysics = DEFAULT_PHYSICS) -> list[str]:
    """推进 dt 秒；返回这一步发生的事（"floor" / "wall" / "ceiling" / "window" / "rest"），给狗的反应用。
    platforms：窗口上沿（只挡往下掉的，和地面一样）；edges：窗口的左右边、下边（只挡从窗口外面撞上来的）。
    不管球现在在哪，结束时一定在某块屏里或过道里（拔了屏、改分辨率时兜底放回最近的地面）。"""
    events: list[str] = []
    if b.resting:
        f = _ground(world, platforms, b.x, b.y + b.r)
        if f is not None:
            b.on = (f.kind, f.key)
            return events
        b.resting, b.on = False, None                              # 底下的线没了（窗口关了、屏幕变了）：掉下去
    g = GRAVITY_M * ppm
    n = max(1, min(64, math.ceil(max(abs(b.vx), abs(b.vy), g * dt) * dt / max(1.0, 0.45 * b.r))))
    h = dt / n
    for _ in range(n):
        _substep(world, b, h, g, ppm, events, platforms, edges, phys)
        if b.resting:
            break
    if world.room_at(b.x, b.y) is None:                           # 兜底：不在任何一块屏里
        f = world.nearest_floor(b.x, b.y)
        b.x, b.y = f.clamp(b.x, b.r), f.y - b.r
        b.vx = b.vy = 0.0
        b.rolling, b.resting = False, True
        b.on = (f.kind, f.key)
    return events


def _hit_edges(b: Ball, nx: float, ny: float, edges: Sequence[Edge], events: list[str], phys: BallPhysics = DEFAULT_PHYSICS) -> tuple[float, float]:
    """窗口的左右边、下边：这一小步从外面撞上了就弹回去（和墙、天花板一样的反弹系数）。球本来就和窗口重叠（在它前面）时，
    它在边的里侧，往外走不算撞。"""
    for e in edges:
        if e.side == "left":
            if b.vx > 0 and b.x + b.r <= e.at + EPS and nx + b.r > e.at and e.lo <= ny <= e.hi:
                nx = e.at - b.r - (nx + b.r - e.at)
                b.impact = max(b.impact, abs(b.vx))
                b.vx = -b.vx * phys.e_wall
                events.append("window")
        elif e.side == "right":
            if b.vx < 0 and b.x - b.r >= e.at - EPS and nx - b.r < e.at and e.lo <= ny <= e.hi:
                nx = e.at + b.r + (e.at - (nx - b.r))
                b.impact = max(b.impact, abs(b.vx))
                b.vx = -b.vx * phys.e_wall
                events.append("window")
        elif b.vy < 0 and b.y - b.r >= e.at - EPS and ny - b.r < e.at and e.lo <= nx <= e.hi:
            ny = e.at + b.r + (e.at - (ny - b.r))
            b.impact = max(b.impact, abs(b.vy))
            b.vy = -b.vy * BALL_E_CEIL
            events.append("window")
    return nx, ny


def _substep(world: World, b: Ball, h: float, g: float, ppm: float, events: list[str], platforms: Sequence[Support] = (),
             edges: Sequence[Edge] = (), phys: BallPhysics = DEFAULT_PHYSICS) -> None:
    a = world.room_at(b.x, b.y)
    if a is None:
        return
    if b.rolling:
        f = _ground(world, platforms, b.x, b.y + b.r)
        if f is None:
            b.rolling, b.on = False, None                         # 滚出了线头（滚到更低的那块屏、滚下窗口）：往下掉
        else:
            b.on = (f.kind, f.key)
            decel = BALL_ROLL_DECEL_M / max(0.05, phys.roll_gain) * ppm * h
            b.vx = 0.0 if abs(b.vx) <= decel else b.vx - math.copysign(decel, b.vx)
            b.y = f.y - b.r
            if abs(b.vx) < BALL_STOP_M * ppm:
                b.vx, b.vy = 0.0, 0.0
                b.rolling, b.resting = False, True
                events.append("rest")
                return
    if not b.rolling:
        b.vy += g * h
    nx, ny = b.x + b.vx * h, b.y + b.vy * h
    # 左右：前沿出了这块屏，外面又不是别的屏 → 墙
    if b.vx > 0 and nx + b.r > a.right and not world.is_open(nx + b.r, ny):
        nx = a.right - b.r - (nx + b.r - a.right)
        b.impact = max(b.impact, abs(b.vx))
        b.vx = -b.vx * phys.e_wall
        events.append("wall")
    elif b.vx < 0 and nx - b.r < a.left and not world.is_open(nx - b.r, ny):
        nx = a.left + b.r + (a.left - (nx - b.r))
        b.impact = max(b.impact, abs(b.vx))
        b.vx = -b.vx * phys.e_wall
        events.append("wall")
    # 天花板
    if b.vy < 0 and ny - b.r < a.top and not world.is_open(nx, ny - b.r):
        ny = a.top + b.r
        b.impact = max(b.impact, abs(b.vy))
        b.vy = -b.vy * BALL_E_CEIL
        events.append("ceiling")
    # 窗口的左右边、下边：从外面撞上来弹回去
    if edges:
        nx, ny = _hit_edges(b, nx, ny, edges, events, phys)
    # 地面 / 窗口上沿：只挡往下掉的，而且上一步还在线以上；同时碰到几条取最高的
    if b.vy > 0:
        room = world.room_at(nx, min(ny, b.y)) or a
        hit: Optional[Support] = None
        for s in [f for f in world.floors if f.covers(nx)] + [p for p in platforms if p.covers(nx)]:
            if b.y + b.r <= s.y + EPS and ny + b.r > s.y and (hit is None or s.y < hit.y):
                hit = s
        if hit is not None:
            ny = hit.y - b.r
            b.impact = max(b.impact, abs(b.vy))
            if b.vy < BALL_REST_BOUNCE_M * ppm:
                b.vy = 0.0
                b.rolling = True
                b.on = (hit.kind, hit.key)
            else:
                b.vy = -b.vy * phys.e_floor
                b.bounces += 1
            b.vx *= BALL_FLOOR_KEEP
            events.append("floor")
        elif ny + b.r > room.bottom and not world.is_open(nx, ny + b.r):
            ny = room.bottom - b.r                                 # 地面下面那一条（从下面的屏上来的）底下也是墙
            b.vy = -b.vy * phys.e_floor
    if world.room_at(nx, ny) is None:                             # 拐角缝：退回去，速度反向
        b.vx, b.vy = -b.vx * phys.e_wall, -b.vy * phys.e_wall
        return
    b.spin += (nx - b.x) / max(1.0, b.r)
    b.x, b.y = nx, ny


# ---------------- 狗的路线 ----------------
@dataclass(frozen=True)
class Leg:
    """路线的一段：run（在 support 上跑到 x）/ jump（从 (x0, y0) 跳到 support 上的 x）。
    mode（跳的时候）：up 往上、push 往前蹬飞出去、edge 走到边上直接落、across 同一层跳过去（屏和屏的交界）。"""
    kind: str
    support: Support
    x: float
    x0: float = 0.0
    y0: float = 0.0
    mode: str = ""


@dataclass
class Route:
    legs: list[Leg] = field(default_factory=list)
    reachable: bool = True      # False：够不着，legs 只到离目标最近的地方


@dataclass(frozen=True)
class LeapSpec:
    """狗跳上跳下用到的数（米；默认值是量现在这个模型得到的，roam 开动时按模型重新量一遍）。距离都从线头算。"""
    near: float = 0.22             # 高度差小于这个算同一层：跳过去，不算往上 / 往下
    floor_edge: float = 0.6        # 地面的线头多是屏幕交界：离它这么远起跳、落地（半个身长：蹲着起跳时鼻子还在这块屏里，不被边框切掉）
    window_margin: float = 0.30    # 落在窗口上沿：根离线头至少这么远
    push_stand: float = 0.22       # 往前蹬：站的地方（根）离线头往里这么远
    push_x: float = 0.04           # …蹬完骨盆比站的地方往前多少
    push_h: float = 0.368          # …蹬完骨盆比台面高多少（屏幕上的高度）
    push_vup: float = 1.5          # …飞出去往上多快（米 / 秒，一点点）
    push_vx: float = 1.9           # …平常横着多快
    push_vx_min: float = 1.2       # …再慢后脚就蹭到窗口角了
    push_vx_max: float = 4.5       # …两条线隔得远时最快多快
    land_big: tuple[float, float] = (-0.390, 0.772)    # 落差大（JumpLand）第一帧的骨盆：(比根往前多少, 屏幕上多高)
    land_small: tuple[float, float] = (-0.212, 0.538)  # 落差小（JumpLand_F_IP）
    big_drop: float = 1.0          # 落差这么大以上算大
    edge_stand: float = 0.105      # 直接落：站的地方（根）离线头往里这么远（前爪刚伸出线头一点）
    edge_land: float = 0.53        # …不横着飞的话，落地时根离线头往外这么远
    edge_h: float = -0.246         # …探到底时骨盆比台面高多少（负的：已经低于台面）
    edge_v: float = 0.14           # …放手时已经在往下的速度（米 / 秒）
    edge_vx: float = 0.25          # …落的时候横着漂多快（离开窗口边一点）
    edge_land_h: float = 0.581     # …落地片段（JumpLand_Place）第一帧骨盆在屏幕上多高
    up_inside: float = 0.40        # 往上跳：落在线头里面这么远
    up_outside: tuple[float, ...] = (0.60, 0.55, 0.50, 0.45)   # …从线头外面这么远起跳（后面放不下就近一点）
    up_floor_inside: float = 0.60  # …落在地面上（屏幕交界）时离线头这么远
    nose: float = 0.55             # 根往前这么远算鼻子（量空地用）
    rear: float = 0.50             # 根往后这么远算尾巴
    body_h: float = 0.4            # 身子离脚多高（量路线有没有被挡用）


@dataclass(frozen=True)
class Block:
    """一个窗口占的地方和它的前后（depth 小的在前面，0 是最前面）：路线不能穿过挡在前面的窗口。"""
    x0: float
    y0: float
    x1: float
    y1: float
    depth: int
    key: int

    def contains(self, x: float, y: float) -> bool:
        return self.x0 < x < self.x1 and self.y0 < y < self.y1


def blocks_from(frames: Sequence[WindowFrame], world: Optional["World"] = None) -> list[Block]:
    """frames 从最前到最后。盖满整块屏的（全屏、最大化）不算：和上沿、左右边一样，它只是背景（真机：MacBook 上开着一个铺满的窗口，狗在那块屏上哪都跳不了）。"""
    out = []
    for k, f in enumerate(frames):
        if world is not None:
            i = world._area_of(f)
            if i is not None:
                a = world.areas[i]
                if f.w >= (a.right - a.left) - 2 and f.h >= (a.bottom - a.top) - 2:
                    continue
        out.append(Block(f.x, f.y, f.x + f.w, f.y + f.h, k, f.number))
    return out


@dataclass(frozen=True)
class Fit:
    """从线头跳下去怎么跳：mode（push 蹬出去 / edge 直接落）、在哪起跳、落在哪（x 都是全局像素）。"""
    mode: str
    takeoff: float
    land: float


class Leaper:
    """量"从这条线的这一头跳到那条线上"跳不跳得过去：往外飞的这一路（骨盆、鼻子）都要在屏幕里，落点要在那条线上。
    纯几何，比例尺、屏幕布局从外面给；两头怎么挑、往上跳怎么走在 plan_route 里。"""

    def __init__(self, world: "World", ppm: float, spec: Optional[LeapSpec] = None, blocks: Sequence[Block] = ()):
        self.world = world
        self.ppm = ppm
        self.spec = spec or LeapSpec()
        self.blocks = list(blocks)
        self._depths = {b.key: b.depth for b in self.blocks}

    # ---- 挡在前面的窗口 ----
    def _depth(self, s: Support) -> float:
        """这个窗口有多靠后（0 最前）。"""
        return self._depths.get(s.key, -1)

    def blocked(self, a: Support, b: Support, points: Iterable[tuple[float, float]]) -> bool:
        """从 a 飞到 b，身子走过 points，有没有被窗口挡着（两头的窗口不算）。
        两个窗口之间：挡路的是在靠后那个前面的。地面和窗口之间：挡路的是在那个窗口前面的，和比那个窗口矮的。两头都是地面（过屏幕交界）：不挡，和在地上跑一样。"""
        if not self.blocks or (a.kind == "floor" and b.kind == "floor"):
            return False
        windows = [s for s in (a, b) if s.kind == "window"]
        far = max(self._depth(s) for s in windows)
        ends = {s.key for s in windows}
        if len(windows) == 2:
            ahead = [k for k in self.blocks if k.depth < far and k.key not in ends]
        else:
            top = windows[0].y
            ahead = [k for k in self.blocks if k.key not in ends and (k.depth < far or k.y0 > top)]
        if not ahead:
            return False
        for x, y in points:
            if any(k.contains(x, y) for k in ahead):
                return True
        return False

    def _body_y(self, line_y: float) -> float:
        return line_y - self.spec.body_h * self.ppm

    def _push_time(self, drop: float, land_h: float) -> float:
        s = self.spec
        fall = drop + s.push_h - land_h
        return (s.push_vup + math.sqrt(max(0.0, s.push_vup * s.push_vup + 2.0 * GRAVITY_M * fall))) / GRAVITY_M

    def _edge_time(self, drop: float) -> float:
        s = self.spec
        fall = drop + s.edge_h - s.edge_land_h
        if fall <= 0.0:
            return 0.0
        return (-s.edge_v + math.sqrt(s.edge_v * s.edge_v + 2.0 * GRAVITY_M * fall)) / GRAVITY_M

    def _landing_range(self, x_e: float, o: int, line: Support) -> tuple[float, float]:
        """落点（根）可以离线头多远：(最近, 最远)，像素。"""
        m = (self.spec.floor_edge if line.kind == "floor" else self.spec.window_margin) * self.ppm
        m = min(m, (line.x1 - line.x0) / 2.0)
        if o > 0:
            return line.x0 + m - x_e, line.x1 - m - x_e
        return x_e - (line.x1 - m), x_e - (line.x0 + m)

    def _open_at_landing(self, x_e: float, o: int, d: float, line: Support) -> bool:
        tip = x_e + o * (d + self.spec.nose * self.ppm)
        return self.world.dog_open(tip, line.y - 2.0) and self.world.dog_open(tip, line.y - 0.5 * self.ppm)

    def _push_clear(self, a: Support, x_e: float, o: int, y_a: float, stand: float, vx: float, T: float, d: float, line: Support) -> bool:
        s, ppm = self.spec, self.ppm
        body = []
        for k in range(1, 9):
            t = T * k / 8.0
            x = x_e + o * (-stand + (s.push_x + vx * t + s.nose) * ppm)
            y = y_a - (s.push_h + s.push_vup * t - 0.5 * GRAVITY_M * t * t) * ppm
            if not self.world.dog_open(x, y):
                return False
            body.append((x_e + o * (-stand + (s.push_x + vx * t) * ppm), y))
        return self._open_at_landing(x_e, o, d, line) and not self.blocked(a, line, body)

    def _edge_clear(self, a: Support, x_e: float, o: int, y_a: float, d: float, line: Support) -> bool:
        s, ppm = self.spec, self.ppm
        tip = x_e + o * s.nose * ppm
        body = []
        for k in range(0, 7):
            y = y_a + (line.y - y_a) * k / 6.0
            if not self.world.dog_open(tip, y - 2.0):
                return False
            body.append((x_e + o * d * k / 6.0, self._body_y(y)))
        return self._open_at_landing(x_e, o, d, line) and not self.blocked(a, line, body)

    def up_clear(self, a: Support, b: Support, tx: float, lx: float) -> bool:
        """往上跳：从 a 的 tx 起跳，先往上再越过窗口边落到 b 的 lx：这一路没被挡在前面的窗口挡着。"""
        y0, y1 = self._body_y(a.y), self._body_y(b.y)
        rise = [(tx, y0 + (y1 - y0) * k / 6.0) for k in range(0, 7)]
        over = [(tx + (lx - tx) * k / 4.0, y1) for k in range(1, 5)]
        return not self.blocked(a, b, rise + over)

    def across_clear(self, a: Support, b: Support, tx: float, lx: float) -> bool:
        """同一层跳过去：这一路没被挡在前面的窗口挡着。"""
        y = self._body_y(min(a.y, b.y))
        return not self.blocked(a, b, [(tx + (lx - tx) * k / 6.0, y) for k in range(0, 7)])

    def fit(self, a: Support, o: int, b: Support) -> Optional[Fit]:
        """从 a 的这一头（o = +1 右头、-1 左头）往外跳到更低的 b 上：空地够就往前蹬（push），不够就走到边上直接落（edge），再不够 None。"""
        s, ppm = self.spec, self.ppm
        drop = (b.y - a.y) / ppm
        if drop <= 0.0:
            return None
        x_e = a.x1 if o > 0 else a.x0
        lo, hi = self._landing_range(x_e, o, b)
        if hi < 0.0 or hi < lo:
            return None                                           # 那条线整个在这头里面（被盖在盒子底下）
        half = (a.x1 - a.x0) / 2.0
        stand = min(s.floor_edge * ppm if a.kind == "floor" else s.push_stand * ppm, half)
        land_z, land_h = s.land_big if drop >= s.big_drop else s.land_small
        T = self._push_time(drop, land_h)
        base = -stand + (s.push_x - land_z) * ppm
        vlo = max(s.push_vx_min, (lo - base) / (T * ppm))
        vhi = min(s.push_vx_max, (hi - base) / (T * ppm))
        if vlo <= vhi:
            top = min(max(s.push_vx, vlo), vhi)
            for k in range(5):
                vx = top + (vlo - top) * k / 4.0                  # 平常那么快先试；前面有墙就飞近一点（不飞高）
                d = base + vx * T * ppm
                if self._push_clear(a, x_e, o, a.y, stand, vx, T, d, b):
                    return Fit("push", x_e - o * stand, x_e + o * d)
        T = self._edge_time(drop)
        for vx in (s.edge_vx, 0.0):
            d = (s.edge_land + vx * T) * ppm
            if lo <= d <= hi and self._edge_clear(a, x_e, o, a.y, d, b):
                return Fit("edge", x_e - o * min(s.edge_stand * ppm, half), x_e + o * d)
        return None

    def up_takeoff(self, a: Support, x_e: float, o: int, margin: float) -> Optional[float]:
        """往上跳：在 a 上、上面那条线的这一头外面哪里起跳（根）；身后放不下 None。"""
        for c in self.spec.up_outside:
            tx = x_e + o * c * self.ppm
            if a.covers(tx, margin) and self.world.dog_open(tx + o * self.spec.rear * self.ppm, a.y - 2.0):
                return tx
        return None

    def up_landing(self, b: Support, x_e: float, o: int) -> float:
        """往上跳：落在 b 的这一头里面哪里（根）。"""
        inside = (self.spec.up_floor_inside if b.kind == "floor" else self.spec.up_inside) * self.ppm
        return x_e - o * min(inside, (b.x1 - b.x0) / 2.0)


def plan_route(supports: Sequence[Support], start: Support, x: float, goal: Support, gx: float,
               max_up: float, reach: float, margin: float, leaper: Leaper, soft_drop: Optional[float] = None) -> Route:
    """从 start 上的 x 走到 goal 上的 gx。supports 是所有能站的线（地面 + 窗口上沿），start / goal 也在里面。
    max_up：一次最多往上跳多高（像素）；reach：同一层的两条线之间横着最多跳多远（像素，缝隙）；margin：站的地方离线头至少这么远；
    leaper：量跳上跳下够不够空地；soft_drop：往下跳超过这么高就加代价（有中间的窗口当台阶就一级一级下，没有照样一下跳下去）。
    在同一条线上就是跑过去；不同的线之间用最短路（Dijkstra）。够不着就去离目标最近的、够得着的地方（reachable = False）。"""
    nodes = list(supports)
    if start not in nodes:
        nodes.append(start)
    if goal not in nodes:
        nodes.append(goal)
    gx = goal.clamp(gx, margin)
    if start == goal or (start.kind == goal.kind and start.key == goal.key and abs(start.y - goal.y) < 1.0 and start.covers(gx)):
        return Route([Leg("run", start, gx)])                     # 同一条线（窗口上沿被盖住一段也还是那个窗口）：跑过去

    near = leaper.spec.near * leaper.ppm

    def across(a: Support, b: Support, at: float) -> Optional[tuple[float, float, str]]:
        """差不多一样高的两条线：挨着（屏和屏的交界）就跳过去；横向重叠（一个窗口比另一个高一丁点）就地小跳。"""
        lo, hi = max(a.x0, b.x0) + margin, min(a.x1, b.x1) - margin
        if lo <= hi:
            tx = min(max(at, lo), hi)
            return tx, tx, "across"
        e = leaper.spec.floor_edge * leaper.ppm
        if b.x0 >= a.x1 - margin and b.x0 - a.x1 <= reach:        # b 在右边
            return a.x1 - min(e, (a.x1 - a.x0) / 2), b.x0 + min(e, (b.x1 - b.x0) / 2), "across"
        if b.x1 <= a.x0 + margin and a.x0 - b.x1 <= reach:        # b 在左边
            return a.x0 + min(e, (a.x1 - a.x0) / 2), b.x1 - min(e, (b.x1 - b.x0) / 2), "across"
        return None

    def link(a: Support, b: Support, at: float) -> Optional[tuple[float, float, float, str]]:
        """从 a 跳到 b：(起跳 x, 落地 x, 代价, 怎么跳)；跳不过去 None。at 是在 a 上现在 / 预计的位置。"""
        if b.y < a.y - max_up:
            return None
        opts: list[tuple[float, float, str]] = []
        if abs(b.y - a.y) < near:
            one = across(a, b, at)
            if one is not None and leaper.across_clear(a, b, one[0], one[1]):
                opts.append(one)
        elif b.y > a.y:                                           # 往下：走到这条线的一头，往外跳
            for o in (1, -1):
                f = leaper.fit(a, o, b)
                if f is not None:
                    opts.append((f.takeoff, f.land, f.mode))
        else:                                                     # 往上：从上面那条线的一头外面起跳，越过窗口边落在里面
            for o in (1, -1):
                if leaper.fit(b, o, a) is None:                   # 这头跳不下来，就不从这头上去（狗不会自己上去就下不来）
                    continue
                x_e = b.x1 if o > 0 else b.x0
                tx = leaper.up_takeoff(a, x_e, o, margin)
                if tx is None:
                    continue
                lx = leaper.up_landing(b, x_e, o)
                if leaper.up_clear(a, b, tx, lx):
                    opts.append((tx, lx, "up"))
        if not opts:
            return None

        def walk(opt: tuple[float, float, str]) -> float:         # 两头挑路程短的
            return abs(opt[0] - at) + abs(opt[1] - opt[0]) + (abs(gx - opt[1]) if b == goal else 0.0)
        tx, lx, mode = min(opts, key=walk)
        steep = 2.0 * max(0.0, (b.y - a.y) - soft_drop) if soft_drop is not None else 0.0
        return tx, lx, abs(b.y - a.y) * 0.6 + abs(lx - tx) + 60.0 + steep, mode

    best = {start: (0.0, x)}
    prev: dict[Support, tuple[Support, float, float, str]] = {}
    heap = [(0.0, id(start), start, x)]
    seen = set()
    while heap:
        cost, _, cur, cx = heapq.heappop(heap)
        if cur in seen:
            continue
        seen.add(cur)
        if cur == goal:
            break
        for nxt in nodes:
            if nxt == cur or nxt in seen:
                continue
            l = link(cur, nxt, cx)
            if l is None:
                continue
            tx, lx, jump_cost, mode = l
            c = cost + abs(tx - cx) + jump_cost
            if nxt not in best or c < best[nxt][0]:
                best[nxt] = (c, lx)
                prev[nxt] = (cur, tx, lx, mode)
                heapq.heappush(heap, (c, id(nxt), nxt, lx))
    target = goal
    reachable = goal in seen or goal in prev
    if not reachable:                                             # 够不着：去离目标最近的、够得着的那条线上最近的点
        def miss(s: Support) -> float:
            return math.hypot(s.clamp(gx, margin) - gx, s.y - goal.y)
        target = min((s for s in best), key=miss)
        gx = target.clamp(gx, margin)
    chain = []
    node = target
    while node != start:
        p, tx, lx, mode = prev[node]
        chain.append((p, node, tx, lx, mode))
        node = p
    chain.reverse()
    legs: list[Leg] = []
    for a, b, tx, lx, mode in chain:
        if abs(tx - (legs[-1].x if legs else x)) > 0.5 or not legs:
            legs.append(Leg("run", a, tx))
        legs.append(Leg("jump", b, lx, tx, a.y, mode))
    legs.append(Leg("run", target, gx))
    legs = [l for k, l in enumerate(legs) if not (l.kind == "run" and k > 0 and legs[k - 1].kind == "run" and abs(legs[k - 1].x - l.x) < 0.5)]
    return Route(legs, reachable)


def supports_from(world: World, frames: Iterable[WindowFrame], min_width: float, headroom: float) -> list[Support]:
    return list(world.floors) + world.window_tops(list(frames), min_width, headroom)


def support_under(supports: Sequence[Support], x: float, y: float, tolerance: float) -> Optional[Support]:
    """脚下（y 附近 tolerance 以内）的那条线；有好几条取最上面的。"""
    best = None
    for s in supports:
        if s.covers(x) and abs(s.y - y) <= tolerance and (best is None or s.y < best.y):
            best = s
    return best


def support_below(supports: Sequence[Support], x: float, y: float) -> Optional[Support]:
    """(x, y) 正下方（不高于 y）最近的那条线：掉下去落在哪。"""
    best = None
    for s in supports:
        if s.covers(x) and s.y >= y - EPS and (best is None or s.y < best.y):
            best = s
    return best
