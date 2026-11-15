"""捡球的圈（进圈才追）：你拿起球，狗站好看着它，身边出一个圈；球在圈里停够了圈满，狗叫一声、俯身，这之后松手才去追。
没满就松手狗只看着。什么时候算、狗怎么接着做在 widget/playground.py（_step_ring）和 widget/roam.py（只看「满没满」），这里是圈本身。

- 圈在哪（ring_shape、in_ring）：圆心在狗身子正中（根往上 CENTER_UP 个身高），半径调参 ring_size 个身高（默认 0.9）；狗脚踩的那条线以下
  不画、不算，贴着线那 FADE_M 米渐渐淡掉（两头融进地面）。在不在里面按球心算；看得见的墨环比它小一点（INK_R1），手不用放得很准。
- 怎么算（Ring）：球心在圈里进度就涨，停够调参 ring_hold_s 秒满；从拿起那一刻算，拿起时球本来就在圈里也一样，不设特例。
  没满就出了圈往回退（满的 DRAIN_S 秒退空），回来接着涨。满了一直算到球离手（再拿出圈也不作废）；松手、关「捡球」、狗被打断才作废（stop）。
- 样子（《降临》里那种墨色的圆形文字，晕开、迷幻、发散）：墨从狗身后涌出来，往外聚成一圈烟一样的墨环——粗细、浓淡绕一圈都不匀，
  两层反着慢慢转、叠出层次，一缕缕烟从墨环上往外飘、越飘越大越淡（由内向外）；涨得越满，环越大、越浓、越宽（半径、宽、浓淡各跟一根不过头的弹簧，
  INK_TAU）。满了墨环往外散开（BURST_GROW）、变宽、BURST_S 秒淡掉，烟飘得更远；没满就不算了原地淡掉。开了「减少动态效果」散开时不变大。
  浅色外观（sticker.is_dark 为假）是墨烟、墨带正中一缕亮；深色外观是亮烟加一圈淡淡的光晕，边上都是软的。圈不出声（充能的声音在 playground 放）。
- 画法：整圈每帧都在动，不能再只重画一小截。两层墨带按圆心一圈 1° 一片扇形、各填一条从里到外的高斯渐变，在 prepare 里预先画好（约 30 毫秒，
  换了大小、换了外观才重画；开灵动交互时分十来份、一帧画一点，prepare_soon）；每帧只把两层反着转一转、按现在的半径缩放、按浓淡画上去，再画几十团飘出去的烟（同一张软烟贴图），
  最后把贴地那截擦淡、地面以下擦掉——先画在一张 1 倍的图上，再整张贴到窗口（烟本来就是软的），每帧约 0.7 毫秒。
- 窗口（RingWindow）：狗的窗口只有 352 × 大小宽，装不下圈，为它改大小要重建画布、闪，所以圈是单独的透明窗口：
  点不到（鼠标直接落到后面），和狗同一层（菜单栏上面）、压在狗和球后面。每块屏一个，只画落在那块屏上的那一截（一个窗口只显示在一块屏上，
  也不骑在两块屏中间），画的时候按全局坐标，两截正好接上。灵动交互一开就建好原生窗口（playground._ensure_ring_windows），第一次拿球时不现建。
  挪窗口要等窗口系统，所以出来那一下按整个圈（连散开、飘出去的烟）的大小摆好，之后圈挪了（狗骑在挪动的窗口上）才挪；淡入淡出改窗口的不透明度。"""
from __future__ import annotations

import math
import time
import random
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from widget import native, sticker
from widget.ball import INK

CENTER_UP = 0.5                      # 圆心在根上面几个身高：狗身子正中
MIN_HOLD_S = 0.05                    # 调参再小，满也至少要这么久（秒）
DRAIN_S = 0.6                        # 没满就出了圈：满的退空要这么久（秒）
RETRACT_S = 0.06                     # 往回退时画出来的进度跟真进度的时间常数（秒）：顺着退，不一下子跳回去
APPEAR_S, FADE_S = 0.22, 0.25        # 淡入、不算了淡掉各多久（秒）
BURST_S, BURST_GROW = 0.9, 0.24      # 满了往外散开：多久淡没（秒）、墨环最后大多少（半径的几成）
BURST_WIDEN = 2.0                    # 散开时墨带变宽几成
FADE_M = 0.12                        # 贴地这么高（米）里渐渐淡掉
PAPER = (1.0, 0.985, 0.955)          # 亮烟、墨里那一缕亮：暖一点的纸白
# 墨环（都按圈的半径算，跟着 ring_size 一起缩放）
INK_R0, INK_R1 = 0.21, 0.70          # 墨环从狗身后多大涨到多大（看得见的那一圈比算不算进圈的那一圈小；算不算进圈按整个圈半径，手不用放得很准）
INK_W0, INK_W1 = 0.048, 0.095        # 墨带多宽（跟着环一起按比例收：0.056 / 0.111 × 0.70 ÷ 0.82，不然环小了带显得粗）
INK_MAX = 0.80                       # 满的时候多浓
INK_TAU = 0.11                       # 半径、宽、浓淡跟着进度走的弹簧（秒，不过头）
SPIN_A, SPIN_B = 0.22, -0.15         # 两层墨带各自慢慢转（弧度 / 秒，反着转叠出层次）
EXTENT = 1.5                         # 窗口按圈半径的几倍摆（散开、飘出去的烟都在里面；飘到边上之前淡没）
BAND_STEP, PREP_BUDGET_S, PREP_GAP_MS = 3, 0.003, 16   # 预先画墨带时一次画几片（每片 1°）、画够多久停一下、隔多久接着画：按时间停，不按片数
                                                       # （预先画墨带按时间停：一次 45 片的话，1 倍时约 3 毫秒，2 倍大的屏上一次 20～40 毫秒，换了模型那几帧会跟着卡）
N_WISP, WISP_PUFFS = 44, 4           # 飘出去的烟：几缕、每缕几团
_rng = random.Random(7)
WISPS = [(_rng.uniform(0.0, 2.0 * math.pi), _rng.random(), _rng.uniform(0.7, 1.3)) for _ in range(N_WISP)]   # 角度、相位、快慢


def _ease_out(u: float) -> float:
    """先快后慢，到头速度为 0：不过头。"""
    u = min(1.0, max(0.0, u))
    return 1.0 - (1.0 - u) * (1.0 - u)


def _smooth(u: float) -> float:
    """两头慢（smoothstep）。"""
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _wave(theta: float, seed: float) -> float:
    """绕一圈连续的起伏（-1..1）：墨带的粗细、偏移、浓淡。"""
    return (0.5 * math.sin(3 * theta + 1.7 * seed) + 0.3 * math.sin(5 * theta - 2.3 * seed)
            + 0.2 * math.sin(8 * theta + 0.7 * seed))


# ---------- 圈在哪（纯几何，全局坐标，像素） ----------
@dataclass(frozen=True)
class RingShape:
    """圆心 (cx, cy)、半径 r、狗脚踩的那条线 floor（线下面不画、不算）。"""
    cx: float
    cy: float
    r: float
    floor: float


def ring_shape(wx: float, wy: float, height_px: float, size: float) -> RingShape:
    """狗的根在 (wx, wy)（wy = 脚踩的线）、站着 height_px 高：圈在哪。size：半径是几个身高（调参 ring_size）。"""
    return RingShape(wx, wy - CENTER_UP * height_px, size * height_px, wy)


def in_ring(s: RingShape, x: float, y: float) -> bool:
    """球心 (x, y) 在不在圈里：圆里面、地面那条线上面。"""
    return y <= s.floor and math.hypot(x - s.cx, y - s.cy) <= s.r


def ring_extent(s: RingShape) -> QRect:
    """整个圈（连散开、飘出去的烟）占的地方（全局坐标）：圈的窗口按它摆，散开的时候不用再改窗口大小。地面那条线下面不要。"""
    reach = s.r * EXTENT
    left, top = math.floor(s.cx - reach), math.floor(s.cy - reach)
    right = math.ceil(s.cx + reach)
    bottom = math.ceil(min(s.floor, s.cy + reach)) + 1
    return QRect(left, top, max(0, right - left), max(0, bottom - top))


@dataclass(frozen=True)
class RingLook:
    """这一帧画成什么样（全局坐标，像素）：圆心、圈的半径、地面那条线、贴地多高渐渐淡掉；墨环现在多大（vr）、多宽（w）、多浓（a），
    转了多久（t）、散开到哪（rel）、深色外观（dark）、整个圈出来了几成（shown，窗口的不透明度）。"""
    cx: float
    cy: float
    r: float
    floor: float
    fade: float
    vr: float
    w: float
    a: float
    t: float
    rel: float
    dark: bool
    shown: float


# ---------- 圈的状态（纯逻辑，不碰窗口） ----------
class Ring:
    """进度、满没满、出没、散开，还有墨环的大小、宽、浓淡（各一根不过头的弹簧）。playground 每帧 step 一次；roam 只看 ready（playground.fetch_ready）。"""

    def __init__(self) -> None:
        self.still = False           # 开了「减少动态效果」：散开时不变大，只淡掉（拿起球时 playground 问一次系统）
        self.clear()

    def clear(self) -> None:
        """全收掉（关灵动交互、出错兜底）。"""
        self.progress = 0.0          # 真进度（0～1）：按球在圈里待了多久算
        self.drawn = 0.0             # 画出来的进度：涨的时候就是真进度（满的那一下和狗叫对上），退的时候顺着退
        self.shown = 0.0             # 出没（0～1，按时间匀着走；alpha 再缓一下）
        self.burst = 0.0             # 满了以后散开到哪（0～1）
        self.ready = False           # 满过了：一直算到球离手（stop）
        self.counting = False        # 这一帧在算（球在手上、狗站好看着它）
        self._ink()

    def _ink(self) -> None:
        self.vr, self.vw, self.va = INK_R0, INK_W0, 0.0   # 墨环（按圈的半径算）：多大、多宽、多浓
        self.t = 0.0                                       # 转了多久

    def restart(self, still: bool = False) -> None:
        """重新开始一圈（拿起球、捡球开关打开、狗忙完又看球）：从空的算，涨上去的那段顺着退回去。
        上一圈正在散开的话从看不见重新淡入，墨环也从狗身后重新涌出来，不会散开到一半又变回浓的。"""
        if self.burst > 0.0:
            self.shown = 0.0
            self._ink()
        self.progress, self.burst, self.ready = 0.0, 0.0, False
        self.still = still

    def stop(self) -> None:
        """不算了（松手、关「捡球」、狗被打断）：满了也作废；圈停在原地淡掉，正在散开的接着散开。"""
        self.counting = self.ready = False

    @property
    def alpha(self) -> float:
        """整个圈多浓（0～1）：淡入淡出 × 散开。"""
        return _ease_out(self.shown) * (1.0 - _smooth(self.burst))

    @property
    def grow(self) -> float:
        """散开时墨环半径乘多少：只往外，不回弹。"""
        return 1.0 if self.still else 1.0 + BURST_GROW * _ease_out(self.burst)

    def step(self, dt: float, inside: Optional[bool], hold_s: float) -> bool:
        """推一帧。inside：球心在不在圈里；None = 这一帧不算（球不在手上、狗没站好）。hold_s：停多久满（调参 ring_hold_s）。
        返回 True = 这一帧刚满。"""
        self.counting = inside is not None
        filled = False
        if self.counting and not self.ready:
            rate = 1.0 / max(MIN_HOLD_S, hold_s) if inside else -1.0 / DRAIN_S
            self.progress = min(1.0, max(0.0, self.progress + rate * dt))
            if self.progress >= 1.0:
                self.ready = filled = True
        if self.ready or self.burst > 0.0:
            self.burst = min(1.0, self.burst + dt / BURST_S)
        if not self.counting:
            self.shown = max(0.0, self.shown - dt / FADE_S)
        elif not self.ready:
            self.shown = min(1.0, self.shown + dt / APPEAR_S)
        if self.progress >= self.drawn:
            self.drawn = self.progress
        else:
            self.drawn += (self.progress - self.drawn) * (1.0 - math.exp(-dt / RETRACT_S))
        p = 1.0 if (self.ready or self.burst > 0.0) else self.drawn
        k = 1.0 - math.exp(-dt / INK_TAU)
        self.vr += (INK_R0 + (INK_R1 - INK_R0) * _ease_out(p) - self.vr) * k
        self.vw += (INK_W0 + (INK_W1 - INK_W0) * p - self.vw) * k
        self.va += (INK_MAX * p ** 0.7 - self.va) * k
        self.t += dt
        if not self.counting and self.shown <= 0.0:
            self.progress = self.drawn = self.burst = 0.0       # 看不见了：下一圈从头来
            self._ink()
        return filled

    def look(self, s: RingShape, ppm: float) -> RingLook:
        """这一帧画成什么样（s：圈在哪；ppm：比例尺，定贴地淡掉多高）。"""
        rel = 0.0 if self.still else _ease_out(self.burst)
        return RingLook(s.cx, s.cy, s.r, s.floor, FADE_M * ppm, self.vr * s.r * self.grow, self.vw * s.r * (1.0 + BURST_WIDEN * rel),
                        self.va * (1.0 - _smooth(self.burst)), self.t, _ease_out(self.burst), sticker.is_dark(), _ease_out(self.shown))


# ---------- 预先画好的墨带、烟 ----------
@dataclass
class _Tex:
    r1: float                        # 画的时候墨环多大（像素）：用的时候按现在的半径缩放
    size: int                        # 两层图的边长
    a: QImage                        # 主墨带（浅色：墨 + 正中一缕亮；深色：亮烟）
    b: QImage                        # 反着转的那层（更软、往外一点；深色还带一圈淡淡的光晕）
    puff: QImage                     # 一团烟（飘出去的那些都是它）


_TEX: dict[tuple, _Tex] = {}


def _band(p: QPainter, c: QPointF, r: float, w: float, seed: float, rgb: tuple, amp: float, spread: float,
          first: int = 0, last: int = 360) -> None:
    """一圈墨带（的第 first～last 片）：每 1° 一片扇形，按这个角度的偏移、粗细、浓淡填一条从里到外的高斯渐变（片和片挨着、不开抗锯齿，没有缝）；
    spread 越大边越软越宽。"""
    xs = (-2.4, -1.8, -1.2, -0.7, -0.3, 0.0, 0.3, 0.7, 1.2, 1.8, 2.4)
    n = 360
    for i in range(first, last):
        th0, th1 = 2.0 * math.pi * i / n, 2.0 * math.pi * (i + 1) / n
        q = (th0 + th1) / 2.0
        off = 0.28 * w * _wave(q, 1.0 + seed)
        blob = max(0.0, _wave(q, 5.0 + seed)) ** 3
        hw = 0.5 * w * (0.62 + 0.30 * (_wave(q, 2.0 + seed) + 1.0) / 2.0 + 0.9 * blob) * spread
        d = 0.45 + 0.55 * ((_wave(q, 3.0 + seed) + 1.0) / 2.0) ** 1.3
        rc = r + off
        outer = rc + 2.6 * hw + 2.0
        g = QRadialGradient(c, outer)
        g.setColorAt(0.0, QColor.fromRgbF(*rgb, 0.0))
        for x in xs:
            pos = (rc + x * hw) / outer
            if 0.0 < pos < 1.0:
                g.setColorAt(pos, QColor.fromRgbF(*rgb, min(1.0, amp * d * math.exp(-1.15 * x * x)) if abs(x) < 2.4 else 0.0))
        g.setColorAt(1.0, QColor.fromRgbF(*rgb, 0.0))
        p.setBrush(g)
        p.drawPolygon(QPolygonF([c, QPointF(c.x() + outer * math.cos(th0), c.y() - outer * math.sin(th0)),
                                 QPointF(c.x() + outer * math.cos(th1), c.y() - outer * math.sin(th1))]))


def _render(r: float, dark: bool):
    """画两层墨带和一团烟：一片片地画（每次 BAND_STEP 片），画够 PREP_BUDGET_S 停一下（yield），可以分好几帧画完；每片只看它是第几片，
    怎么切都画得一样。画完把 _Tex 放进 _TEX、作为最后一个值交出来。"""
    r1, w1 = round(INK_R1 * r), round(INK_W1 * r)
    size = int(2.0 * (r1 + 3.6 * w1)) + 4
    c = QPointF(size / 2.0, size / 2.0)
    if dark:
        parts_a = [(r1, w1, 0.0, PAPER, 0.42, 1.25)]
        parts_b = [(r1, w1 * 1.4, 30.0, PAPER, 0.07, 3.2), (r1 + 0.22 * w1, w1, 10.0, PAPER, 0.20, 1.9)]
    else:
        parts_a = [(r1, w1, 0.0, INK, 1.0, 1.0), (r1, w1, 20.0, PAPER, 0.30, 0.42)]
        parts_b = [(r1 + 0.22 * w1, w1, 10.0, INK, 0.32, 1.7)]
    layers = []
    for parts in (parts_a, parts_b):
        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setPen(Qt.NoPen)
        since = time.perf_counter()
        for rr, ww, seed, rgb, amp, spread in parts:
            for start in range(0, 360, BAND_STEP):
                _band(p, c, rr, ww, seed, rgb, amp, spread, start, min(360, start + BAND_STEP))
                if time.perf_counter() - since >= PREP_BUDGET_S:
                    yield None
                    since = time.perf_counter()
        p.end()
        layers.append(img)
    puff = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
    puff.fill(Qt.transparent)
    p = QPainter(puff)
    g = QRadialGradient(QPointF(32.0, 32.0), 32.0)
    rgb = PAPER if dark else INK
    g.setColorAt(0.0, QColor.fromRgbF(*rgb, 1.0))
    g.setColorAt(0.5, QColor.fromRgbF(*rgb, 0.45))
    g.setColorAt(1.0, QColor.fromRgbF(*rgb, 0.0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(32.0, 32.0), 32.0, 32.0)
    p.end()
    tex = _TEX[(r1, w1, dark)] = _Tex(float(r1), size, layers[0], layers[1], puff)
    if len(_TEX) > 6:
        _TEX.pop(next(iter(_TEX)))                           # 换过几次大小：旧的扔掉
    yield tex


def _key(r: float, dark: bool) -> tuple:
    return (round(INK_R1 * r), round(INK_W1 * r), dark)


def prepare(r: float, dark: bool) -> _Tex:
    """圈半径 r（像素）、深浅色外观对应的两层墨带和一团烟：画过的直接拿；正在一帧帧画的当场画完；没画过的当场画（约 30 毫秒）。"""
    key = _key(r, dark)
    tex = _TEX.get(key)
    if tex is not None:
        return tex
    job = _PENDING.pop(key, None) or _render(r, dark)
    for out in job:
        if out is not None:
            tex = out
    return tex


def prepare_soon(r: float, dark: bool) -> None:
    """先在空的时候一帧画一点（每次画够 PREP_BUDGET_S 就停），不一口气占着主线程：开灵动交互、换大小、换模型时用，第一次拿球不现画。"""
    key = _key(r, dark)
    if key in _TEX or key in _PENDING:
        return
    _PENDING[key] = _render(r, dark)
    _PREP_TIMER.start()


def _prep_tick() -> None:
    if not _PENDING:
        return
    key = next(iter(_PENDING))
    try:
        next(_PENDING[key])
    except StopIteration:
        _PENDING.pop(key, None)
    if key in _TEX:
        _PENDING.pop(key, None)
    if _PENDING:
        _PREP_TIMER.start()


class _PrepTimer:
    """一帧画一点的那个计时器：要用时才建（模块载入时可能还没有 QApplication）。"""

    def __init__(self) -> None:
        self._timer = None

    def start(self) -> None:
        if self._timer is None:
            from PySide6.QtCore import QTimer
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.setInterval(PREP_GAP_MS)
            self._timer.timeout.connect(_prep_tick)
        self._timer.start()


_PENDING: dict[tuple, object] = {}
_PREP_TIMER = _PrepTimer()


def paint_ink(p: QPainter, look: RingLook, area: QRectF) -> None:
    """按 look 画墨环（p 按全局坐标；area：这一块要画的地方，用来擦贴地那截和地面以下）。整个圈的出没在窗口的不透明度上（RingWindow）。"""
    if look.a <= 0.003 or look.vr <= 1.0:
        return
    tex = prepare(look.r, look.dark)
    c = QPointF(look.cx, look.cy)
    k = look.vr / tex.r1
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    for img, spin in ((tex.b, SPIN_B), (tex.a, SPIN_A)):
        p.save()
        p.translate(c)
        p.rotate(-math.degrees(spin * look.t))
        p.scale(k, k)
        p.setOpacity(look.a)
        p.drawImage(QPointF(-tex.size / 2.0, -tex.size / 2.0), img)
        p.restore()
    # 一缕缕往外飘的烟：从墨带上出去，越飘越大、越淡、卷一点；散开的时候飘得更远；快到窗口边上之前淡没
    amp = look.a * (0.75 if look.dark else 1.0)
    edge = look.r * EXTENT
    for th0, ph, sp in WISPS:
        age = (look.t * 0.42 * sp + ph) % 1.0
        strength = 0.35 + 0.65 * max(0.0, _wave(th0 + 0.3 * look.t, 4.0)) ** 1.1
        fade = math.sin(math.pi * age) ** 1.3 * strength * amp
        if fade <= 0.004:
            continue
        th = th0 + SPIN_A * look.t
        reach = look.w * (0.4 + 2.1 * age) * (1.0 + 1.3 * look.rel)
        curl = (0.12 + 0.45 * age) * (1.0 if sp > 1.0 else -1.0)
        grow = 0.8 + 1.7 * age
        for j in range(WISP_PUFFS):
            u = (j + 1) / WISP_PUFFS
            rr = look.vr + reach * u
            ang = th + curl * u * u
            rad = look.w * (0.30 + 0.60 * u) * grow
            alpha = fade * 0.21 * (1.0 - 0.4 * u) * _smooth((edge - rr - rad) / (0.2 * look.r))
            if alpha <= 0.003:
                continue
            p.setOpacity(min(1.0, alpha))
            p.drawImage(QRectF(c.x() + rr * math.cos(ang) - rad, c.y() - rr * math.sin(ang) - rad, 2.0 * rad, 2.0 * rad), tex.puff)
    p.setOpacity(1.0)
    # 贴地那截渐渐擦淡，地面以下擦掉
    p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    g = QLinearGradient(0.0, look.floor - look.fade, 0.0, look.floor)
    g.setColorAt(0.0, QColor(0, 0, 0, 0))
    g.setColorAt(1.0, QColor(0, 0, 0, 255))
    p.fillRect(QRectF(area.left(), look.floor - look.fade, area.width(), look.fade), g)
    if area.bottom() > look.floor:
        p.fillRect(QRectF(area.left(), look.floor, area.width(), area.bottom() - look.floor), QColor(0, 0, 0, 255))
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)


# ---------- 窗口 ----------
class RingWindow(QWidget):
    """圈落在一块屏上的那一截：透明、点不到、压在狗后面的小窗口。只管摆和画；圈在哪、画成什么样由 playground 每帧给（sync）。"""

    def __init__(self, home):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                         | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
        self.home = home                         # 这个窗口待在哪块屏（QScreen，只用它的 geometry()）：从不搬到别的屏
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle("Ring")
        native.apply(self)
        self.look: Optional[RingLook] = None     # 现在画的（全局坐标）
        self._alpha = -1.0                       # 窗口现在的不透明度
        self._buffer: Optional[QImage] = None    # 先画在这张 1 倍的图上，再整张贴到窗口（烟是软的，不用按屏幕的倍数画）

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)        # 所有桌面、全屏 App 上都在（和狗一样）
        native.set_level(self, native.LEVEL_RING)   # 最后面那一层：物件、狗、另一半狗、球都在它前面
        native.set_ignores_mouse(self, True)     # 点不到：窗口标志说过了，Qt 改过标志会按它重设，这里再说一次
        super().showEvent(event)

    def sync(self, look: Optional[RingLook], extent: Optional[QRect], alpha: float) -> None:
        """这一帧：圈画成 look（全局坐标）；extent 是整个圈（连散开、飘出去的烟）占的地方（ring_extent，圈不挪它就不变）；alpha 是整个圈多浓，
        0 就收起来。窗口的不透明度只管出没（look.shown），散开时变淡画在墨环自己的浓淡里。烟每帧都在动：看得见就每帧重画。"""
        part = QRect()
        if look is not None and extent is not None and alpha > 0.0:
            part = extent.intersected(self.home.geometry())
        if part.isEmpty():
            self.put_away()
            return
        if self.geometry() != part:
            self.setGeometry(part)               # 圈出来那一下摆一次；之后只有圈挪了才挪（每挪一次都要等窗口系统）
        opacity = look.shown
        if abs(opacity - self._alpha) > 1.0 / 255.0 or (opacity == 1.0 and self._alpha != 1.0):
            self._alpha = opacity
            self.setWindowOpacity(opacity)
        self.look = look
        if not self.isVisible():
            self.show()
        self.update()

    def put_away(self) -> None:
        """收起来（圈淡没了、关灵动交互）。"""
        if self.isVisible():
            self.hide()
        self.look = None

    def paintEvent(self, event) -> None:
        look = self.look
        if look is None:
            return
        g = self.geometry()
        size = QSize(max(1, g.width()), max(1, g.height()))
        if self._buffer is None or self._buffer.size() != size:
            self._buffer = QImage(size, QImage.Format_ARGB32_Premultiplied)
        buf = self._buffer
        buf.fill(Qt.transparent)
        p = QPainter(buf)
        p.translate(-g.x(), -g.y())              # 按全局坐标画：两块屏上的两截正好接上
        paint_ink(p, look, QRectF(g))
        p.end()
        w = QPainter(self)
        w.setRenderHint(QPainter.SmoothPixmapTransform)
        w.drawImage(QRectF(self.rect()), buf)
        w.end()
