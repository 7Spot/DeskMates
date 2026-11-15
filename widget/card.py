"""悬浮卡片的底子：无边框、透明、置顶。Settings 用它（自定义毛色、高级设置是设置卡片里的页）；拖卡片空白处可以移动；Esc 或右上角 ✕ 关闭。
贴纸风的画法和颜色在 widget/sticker.py，控件在 widget/widgets.py，右边弹出的侧边面板（表盘）在 widget/sidepane.py。
标题行是顶部栏（TitleBar）：左边的圆（app 图标或返回 ‹）、米白底黑描边的名字胶囊带一个小图标（写同桌名字时是它的物种图标，别的是 app 图标，
widget/marks.py；点它就地改名或打开什么，set_renamable / set_title_click）、新版本胶囊、×；换页时这一条不动，只换字、宽度和圆里的图案。分组标题前一根小骨头（header）；行下面的说明不占一行，
鼠标在那一行停下不动 0.5 秒才浮出来（tip_for）；强调色跟当前毛色（window.accent_color，set_accent 换）。卡片打开 0.14 秒淡入。

高度：按内容的 heightForWidth 量（换行的说明文字量得准），超过屏幕可用高度就封顶，多出来的在卡片里滚动，标题行不动。
不用 adjustSize()：Qt 会把窗口限制在屏幕高的 2/3，还量不准换行文字；982 点高的屏幕上英文设置卡片被挤得说明文字重叠，
演示模式下手机二维码下半截被裁、扫不出来。
放在狗旁边（place_near）：狗的斜对面、朝屏幕中心那一边，表盘往右弹会碰到狗就再往左让。"""
from __future__ import annotations

import dataclasses
import logging
import math
from contextlib import contextmanager
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPalette, QPen, QRegion
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

import config
from widget import marks, native, sounds, sticker
from widget.i18n import tr
from widget.nameedit import NameEdit
from widget.sidepane import SideDock
from widget.sticker import SHADOW
from widget.widgets import (NAME_MAX, PILL_H, Collapse, FineSlider, FrameClock, HoldButton, HoldPill, IconButton, Marquee, MotionButton,
                            Spring, Switch, bone_pixmap, clip_graphemes, draw_icon, draw_strip, ease_in, ease_out, grapheme_count, hairline,
                            hide_tip, sticker_tip)

log = logging.getLogger("card")

PAD = 16               # 卡片内容离描边多远
PAD_QUIET = 10         # 最底下一行是灰字（高级设置… / 退出、版本号、重置）时的底边距：字所在的胶囊比字高，字下面本来就空着一截，这样字离底边看着和离两边一样
EDGE = 8               # 卡片离屏幕可用区域上下边至少这么远（阴影可以伸出去）
MIN_HEIGHT = 100       # 只防内容空的时候缩成一条（多出来的全堆在按钮下面）
POP_S = 0.14           # 卡片打开淡入
RISE, RISE_S = 6, 0.2  # 打开时同时往上浮 6 像素
CLOSE_S = 0.12         # ×、Esc、再点一次打开它的按钮：淡出这么久再藏起来
SWAP_S = 0.24          # 换页：旧内容前一半淡出、新内容后一半淡入（和标题的字一样长）
ACCENT_S = 0.24        # 强调色（跟毛色）换的时候淡过去多久：和换同桌时狗淡入一样长（window.PET_FADE_IN_S）
TIP_DELAY_MS = 500     # 悬浮说明：鼠标在那一行里停下不动这么久才出（要停下不动，动一下重来）
NEAR_GAP = 6           # 卡片放在狗旁边时离狗多远
TYPE_ACTIVATES = False # 开始打字（输入框拿到焦点）时把同桌切到前台：卡片本身点了不切（set_no_activate）；真机上不切就打不了字再改成 True
DIAL_CLEAR = 10       # 摆卡片时表盘离狗至少留这么多（打开表盘那一下卡片变宽、姿势行会重排挪几个像素）


def _smooth(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def _metaball(c1: QPointF, r1: float, c2: QPointF, r2: float, v: float, handle: float = 2.4) -> Optional[QPainterPath]:
    """两个圆之间的那段「水桥」（两滴水快要碰上 / 刚分开时中间连着的那一截）：v 越小桥越细，0 就没了。两个圆一个套着另一个时没有桥。"""
    d = math.hypot(c2.x() - c1.x(), c2.y() - c1.y())
    if v <= 0.01 or d <= abs(r1 - r2) + 0.01 or r1 <= 0.0 or r2 <= 0.0:
        return None
    clamp = lambda x: max(-1.0, min(1.0, x))
    if d < r1 + r2:
        u1 = math.acos(clamp((r1 * r1 + d * d - r2 * r2) / (2 * r1 * d)))
        u2 = math.acos(clamp((r2 * r2 + d * d - r1 * r1) / (2 * r2 * d)))
    else:
        u1 = u2 = 0.0
    ang = math.atan2(c2.y() - c1.y(), c2.x() - c1.x())
    spread = math.acos(clamp((r1 - r2) / d))
    a1a, a1b = ang + u1 + (spread - u1) * v, ang - u1 - (spread - u1) * v
    a2a, a2b = ang + math.pi - u2 - (math.pi - u2 - spread) * v, ang - math.pi + u2 + (math.pi - u2 - spread) * v
    pt = lambda c, a, r: QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a))
    p1a, p1b, p2a, p2b = pt(c1, a1a, r1), pt(c1, a1b, r1), pt(c2, a2a, r2), pt(c2, a2b, r2)
    total = r1 + r2
    d2 = min(v * handle, math.hypot(p1a.x() - p2a.x(), p1a.y() - p2a.y()) / total) * min(1.0, d * 2.0 / total)
    h1, h2 = r1 * d2, r2 * d2
    path = QPainterPath()
    path.moveTo(p1a)
    path.cubicTo(pt(p1a, a1a - math.pi / 2, h1), pt(p2a, a2a + math.pi / 2, h2), p2a)
    path.lineTo(p2b)
    path.cubicTo(pt(p2b, a2b - math.pi / 2, h2), pt(p1b, a1b + math.pi / 2, h1), p1b)
    path.closeSubpath()
    return path


class _Lead(IconButton):
    """顶部栏左边的圆：和右上角 × 同一个圆（IconButton 26，同一段画圆的代码，像素一样），顶齐平、离边一样 16。
    'mark'：app 图标（widget/marks.py，猫狗拼的 DM）。设置卡片上点了进「关于」页（TitleBar.mark_clickable → mark_clicked）；
    别的卡片上点了没反应，鼠标穿过它、按下照旧拖卡片。
    'back'：返回 ‹。换的时候圆不动，里面的图案先淡出再淡入（mix：0 图案、1 返回；和标题的字同一个节拍，TitleBar.tick 推），描边一直全浓。
    app 图标正流进 / 流出名字胶囊的时候（进出高级设置，TitleBar 的 _Flow）它自己不画（flow_hidden）：圆会鼓、会吞，里面的图案糊开糊进，
    连圆带图案都画在上面一层（_FlowLayer），按它现在的悬停、按下样子画，交接时一个像素不差。进出「关于」页时（widget/about.py 的 Hero）也一样（hero_hidden）：
    圆一分为二、分出去的那一个长成关于页的大图标，回来时返回键连圆缩没、大图标缩回来当这个圆，都画在那一段自己的一层里。
    浓淡是自己画的时候带的，不挂 QGraphicsOpacityEffect：换页时下面整块内容挂着一层在淡，嵌套的那层 Qt 会画偏。"""

    def __init__(self, parent: QWidget):
        super().__init__("back", tr("Back"), parent, size=PILL_H)
        self.mix = 0.0
        self.flow_hidden = False
        self.hero_hidden = False

    def paintEvent(self, event) -> None:
        if not (self.flow_hidden or self.hero_hidden):
            super().paintEvent(event)

    def fill_color(self) -> QColor:
        """圆的底色（和 IconButton.paintEvent 一样）：悬停深一点，按下往墨色变。"""
        return sticker.mix(QColor(sticker.PAPER_3 if self._hover else sticker.PAPER_2), QColor(sticker.INK), self.motion.press_amount)

    def glyph_size(self) -> float:
        return 19.0 * (self.motion.content_rect().width() / self.SIZE)

    def paint_glyph(self, p: QPainter, r: QRectF, ink: QColor, fill: QColor) -> None:
        base = p.opacity()
        mark, back = max(0.0, 1.0 - 2.0 * self.mix), max(0.0, 2.0 * self.mix - 1.0)   # 一个淡没了另一个才出来，两个不叠
        if mark > 0.0:
            p.setOpacity(base * mark)
            marks.draw_app(p, r.center(), ink)
        if back > 0.0:
            p.setOpacity(base * back)
            super().paint_glyph(p, r, ink, fill)
        p.setOpacity(base)


class _FlowLayer(QWidget):
    """顶部栏最上面一层：流的时候整块（左边的圆、名字胶囊、那一滴、里面的图案和字）都画在这（TitleBar._paint_flow → _Flow.paint）。
    挂在卡片上、盖住顶部栏，往左多出 FLOW_PAD（回来冲过头时画到圆左边外面；挂在顶部栏上画不出它左边）；鼠标穿过它；只在流的时候显示，平时藏着、不画。"""

    def __init__(self, bar: "TitleBar"):
        super().__init__(bar.card)
        self.bar = bar
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def place(self) -> None:
        """跟着顶部栏摆（它在卡片里挪了、变宽了）。"""
        at = self.bar.mapTo(self.parentWidget(), QPoint(0, 0))
        self.setGeometry(at.x() - FLOW_PAD, at.y(), self.bar.width() + FLOW_PAD, self.bar.height())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(FLOW_PAD, 0.0)
        self.bar._paint_flow(p)
        p.end()


FLOW_DROP_R = 11.5            # 那一滴多大：比胶囊（13）小一点，流进去以后整个在胶囊里
FLOW_RING_R = 12.5            # 左上角那个圆的描边外沿半径（_Lead：26 的圆，描边 2；悬停、按下时按它现在的样子算）
FLOW_REACH = 7.0              # 隔这么远以内有水桥：靠近时伸出细桥一下连上，离开时拉到这么远断开（灵动岛约 7 点）
FLOW_NECK = 0.55              # 水桥最粗多少（_metaball 的 v）
FLOW_GULP, FLOW_GULP_S = 0.80, 0.15   # 连上 / 分出去那一下胶囊先缩到几成、缩着多久，再舒展（灵动岛缩到最终的 75% 左右）
FLOW_BLUR = 4.0               # 图案、字换的时候最糊多少（像素）
FLOW_TRAVEL_S = 0.36          # 那一滴走一趟：目标点两头慢地挪这么久，墨滴用会回弹的弹簧追
FLOW_BACK_S, FLOW_BACK_OMEGA = 0.28, 24.0   # 回来那一趟：目标点两头慢地挪这么久，墨滴用欠阻尼的弹簧追
FLOW_OVERSHOOT = 5.0          # 回来时冲过头多远（像素）：按这一趟多远挑阻尼（_back_zeta），远近都差不多冲过这么多，近的冲不了那么多就尽量
FLOW_VANISH_S = 0.14          # 回来时返回键连圆缩到 35%、淡没要多久：不等那一滴，那一滴回去自己当这个圆
FLOW_PAD = 14                 # 流动那一层比顶部栏往左多出这么多：回来冲过头时画到圆左边外面，不被切（_FlowLayer 挂在卡片上）


class _Elastic:
    """会回弹的二阶弹簧（zeta < 1 过头一点再回来）：顶部栏那一滴的位置、拉长，圆的鼓和吞，胶囊的吞和舒展。按 1/480 秒细分着推，帧间隔不匀也稳。"""

    def __init__(self, value: float, omega: float, zeta: float):
        self.value, self.velocity, self.omega, self.zeta = float(value), 0.0, omega, zeta

    def step(self, dt: float, target: float) -> float:
        n = max(1, math.ceil(dt * 480.0))
        h = dt / n
        for _ in range(n):
            a = self.omega * self.omega * (target - self.value) - 2.0 * self.zeta * self.omega * self.velocity
            self.velocity += a * h
            self.value += self.velocity * h
        return self.value

    def settled(self, target: float, eps: float) -> bool:
        return abs(self.value - target) < eps and abs(self.velocity) < 20.0 * eps


def _smoother(u: float) -> float:
    """smootherstep：两头的速度、加速度都是 0。"""
    u = max(0.0, min(1.0, u))
    return u * u * u * (u * (6.0 * u - 15.0) + 10.0)


_BACK_ZETAS = [0.30 + 0.02 * i for i in range(26)]
_back_unit: dict[float, list[float]] = {}     # 先停多久 → 每个阻尼走 1 像素冲过头多少（弹簧是线性的：冲过头和走多远成正比，算一次约 1 毫秒）


def _back_zeta(dist: float, delay: float) -> float:
    """回来那一趟走 dist 像素（先停 delay 秒）：挑阻尼，让墨滴到位时冲过头 FLOW_OVERSHOOT 左右。照 _Elastic 一样的推法（1/480 秒）算。"""
    unit = _back_unit.get(delay)
    if unit is None:
        unit = _back_unit[delay] = []
        w2, h = FLOW_BACK_OMEGA * FLOW_BACK_OMEGA, 1.0 / 480.0
        for zeta in _BACK_ZETAS:
            x, v, t, low, c = 1.0, 0.0, 0.0, 1.0, 2.0 * zeta * FLOW_BACK_OMEGA
            while t < delay + FLOW_BACK_S + 0.35:
                t += h
                v += (w2 * ((1.0 - _smooth((t - delay) / FLOW_BACK_S)) - x) - c * v) * h
                x += v * h
                low = min(low, x)
            unit.append(-low)
    return min(zip(_BACK_ZETAS, unit), key=lambda zu: abs(zu[1] * dist - FLOW_OVERSHOOT))[0]


def _blurred(p: QPainter, paint: Callable[[QPainter], None], box: QRectF, blur: float, alpha: float,
             clip: Optional[QPainterPath] = None) -> None:
    """在 box 里画 paint：糊 blur 像素、浓淡 alpha（苹果换内容的那种：先糊开淡掉，再从模糊里出来）。clip：只画在这里面。
    糊 = 同一个东西在两圈小圆上错开画十几遍取平均（逐层按 1/n 插进去；Qt 的 Plus 带透明度时不是相加，叠完只有六成浓）。几乎不糊就直接画。"""
    if alpha <= 0.003 or box.isEmpty():
        return
    p.save()
    if clip is not None:
        p.setClipPath(clip, Qt.IntersectClip)
    if blur < 0.2:
        p.setOpacity(p.opacity() * alpha)
        paint(p)
        p.restore()
        return
    dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
    w, h = max(1, math.ceil(box.width() * dpr)), max(1, math.ceil(box.height() * dpr))
    acc = QImage(w, h, QImage.Format_RGBA64_Premultiplied)
    acc.fill(Qt.transparent)
    one = QImage(w, h, QImage.Format_RGBA64_Premultiplied)
    taps = [(0.0, 0.0)]
    for ring, n in ((1.0, 10), (0.55, 6)):
        taps += [(math.cos(2.0 * math.pi * (k + 0.3 * ring) / n) * blur * ring, math.sin(2.0 * math.pi * (k + 0.3 * ring) / n) * blur * ring)
                 for k in range(n)]
    for i, (dx, dy) in enumerate(taps):
        one.fill(Qt.transparent)
        q = QPainter(one)
        q.setRenderHint(QPainter.Antialiasing)
        q.setRenderHint(QPainter.TextAntialiasing)
        q.scale(dpr, dpr)
        q.translate(-box.left() + dx, -box.top() + dy)
        paint(q)
        q.end()
        a = QPainter(acc)
        a.setCompositionMode(QPainter.CompositionMode_Source)
        a.setOpacity(1.0 / (i + 1))
        a.drawImage(0, 0, one)
        a.end()
    acc.setDevicePixelRatio(dpr)
    p.setOpacity(p.opacity() * alpha)
    p.drawImage(box.topLeft(), acc)
    p.restore()


class _Flow:
    """进 / 出高级设置时，app 图标在左上角的圆和名字胶囊之间流过去（TitleBar.set_look）。
    要那种回弹，节奏照录屏逐帧量的（60 帧/秒）；形状的边一直清楚、不拖影，
    「动态模糊」在内容上：字、种类图标换的时候先糊开淡掉，形状停稳了再从模糊里出来。
    进（into）：左上角白底黑框的圆像细胞分裂一样一分为二（两个连成一整块、黑框一笔连着，中间收细再断开，断开后弹回圆），
    分出去的那一个带着 app 图标走到胶囊，隔 FLOW_REACH 伸出细桥一下连上（胶囊也是白底黑框；连上了黑框也是一笔），
    落在胶囊里图标的位置；胶囊先吞一下（缩到两个宽里窄的那个的 FLOW_GULP）再舒展到新宽度，新的字从模糊里出来；圆里 ‹ 糊进来。
    出：返回键连圆 FLOW_VANISH_S 缩没、淡掉，不等那一滴；
    那一个带着图标从胶囊左头分出去（黑框一笔连着、拉细再断开），自己当那个圆：像有惯性，到位时冲过头 FLOW_OVERSHOOT 再回来（位置回弹，大小不吞）。
    名字比「高级设置」长：进的时候要变窄的胶囊先往新宽度收，那一滴追上去再连；回来时等那一滴让开了胶囊再往左长，那一滴回到圆那儿就不等了。
    流到一半又反过来：新的一趟从现在的样子接着走（位置、速度、浓淡、圆缩到哪都接上），不跳。只管算和画：TitleBar 每帧 step，画在 _FlowLayer。"""

    def __init__(self, bar: "TitleBar", into: bool, prev: Optional["_Flow"]):
        self.into = into
        self.t = 0.0
        self.delay = 0.0 if prev is not None else (0.06 if into else 0.08)   # 先粘着一下再被拉出去；反过来接着走不用
        if prev is not None:
            self.x, self.hw, self.sx, self.cs = prev.x, prev.hw, prev.sx, prev.cs
            self.drop_r = prev.drop_r
            self.circle_back = prev.circle_back
            self.layers = [[key, text, outlined, width, presence, 0.0] for key, text, outlined, width, presence, _ in prev.layers]
            self.gulp = prev.contact is not None or not prev.into                # 那一滴进过胶囊才有「分出去」的那一下吞
            self.circle_size = prev.circle_size
        else:
            c0, ring, _ = self.circle(bar)
            self.hw = _Elastic(bar.tag.value / 2.0, 17.0, 0.80)                 # 胶囊半宽：吞一下再舒展，几乎不过头（灵动岛就是这样）
            self.sx = _Elastic(1.0, 34.0, 0.42)                                 # 分出去的那一个横着拉长：被拉着时变长，断开后弹回圆
            self.cs = _Elastic(1.0, 30.0, 0.38)                                 # 圆：被拉时鼓一点、合进来时缩一点，回弹
            if into:
                self.x = _Elastic(c0.x(), 34.0, 0.85)                           # 和圆叠在一起：一开始就是圆本身
                self.drop_r = ring + sticker.OUTLINE / 2.0
            else:
                self.x = _Elastic(self.slot(bar, (bar.left.value, bar.tag.value / 2.0)), 34.0, 0.85)
                self.drop_r = FLOW_DROP_R
            self.circle_back = 0.0 if into else 1.0
            icon = bar._drawn_icon if into else None                           # app 图标是带着走的：回来时旧的那层只剩字
            self.layers = [[icon, bar._drawn_text, bar._drawn_outlined, bar.tag.value, bar._drawn_alpha, 0.0]]
            self.gulp = True
            self.circle_size = 1.0                                              # 左边那个圆还在多少（1 整个，0 没了）：回来时返回键连圆缩没
        if into:
            self.x.omega, self.x.zeta = 34.0, 0.85
        else:                                                                   # 回来：欠阻尼，按这一趟多远挑，到位时冲过头一点
            self.x.omega, self.x.zeta = FLOW_BACK_OMEGA, _back_zeta(abs(self.x.value - self.circle(bar)[0].x()), self.delay)
        self.x_from = self.x.value
        self.w_from = 2.0 * self.hw.value
        self.contact = self.parted = self.touch = None   # 碰上胶囊、从源头断开、（出）碰到圆的时刻
        self.new_added = False

    # ---- 在哪 ----
    @staticmethod
    def circle(bar: "TitleBar") -> tuple[QPointF, float, float]:
        """左边的圆现在画在哪（按 _Lead 现在的悬停、按下样子）：圆心、描边中线的半径、放大了多少。"""
        lead = bar.lead
        if lead is None:
            return QPointF(bar.H / 2.0, bar.ROOM + bar.H / 2.0), FLOW_RING_R - sticker.OUTLINE / 2.0, 1.0
        tr = lead.motion.transform()
        r = lead.motion.content_rect().adjusted(1.5, 1.5, -1.5, -1.5)
        return tr.map(r.center()) + QPointF(lead.pos()), r.width() / 2.0 * tr.m11(), tr.m11()

    def cap(self, bar: "TitleBar") -> tuple[float, float, float, float]:
        """名字胶囊现在画在哪：左边、半宽、半高、竖直中心。居中时正中不动、两边一起变；靠左（有新版本胶囊）时左边不动。
        被吞得窄的时候稍微变高（灵动岛：缩到 75% 时高 3%）。"""
        hw = max(bar.H / 2.0, self.hw.value)
        left = bar.left.value + (bar.tag.value - 2.0 * hw) * bar._grow_share()   # 居中时两头一起变；有新版本胶囊时左边挪 1/3（三段等宽）
        narrow = min(self.w_from, bar.tag.target) / 2.0
        squeeze = max(0.0, 1.0 - hw / narrow) if narrow > 0.0 else 0.0
        return left, hw, bar.H / 2.0 * (1.0 + 0.12 * squeeze), bar.ROOM - bar._lift + bar.H / 2.0

    @staticmethod
    def slot(bar: "TitleBar", cap: tuple) -> float:
        """胶囊里小图标的横坐标（和 TitleBar.icon_center 一个算法）：带着走的 app 图标落在这。"""
        left, hw = cap[0], cap[1]
        g = max(0.0, min(1.0, (2.0 * hw - bar.H) / 24.0))
        return left + (bar.H - bar.MARK_W) / 2 * (1.0 - g) + bar.TAG_L * g + bar.MARK_W / 2

    def progress(self, bar: "TitleBar", cap: Optional[tuple] = None) -> float:
        """走到哪了（0 圆心，1 胶囊里图标的位置）。"""
        cap = cap or self.cap(bar)
        c0 = self.circle(bar)[0]
        span = self.slot(bar, cap) - c0.x()
        return max(0.0, min(1.0, (self.x.value - c0.x()) / span)) if abs(span) > 1e-6 else 0.0

    def head(self, bar: "TitleBar", cap: tuple) -> QPointF:
        """分出去的那一个的中心：横着是弹簧，竖着从圆的高度过渡到胶囊的高度（胶囊被抬起来时）。"""
        c0 = self.circle(bar)[0]
        return QPointF(self.x.value, c0.y() + (cap[3] - c0.y()) * self.progress(bar, cap))

    def share(self, bar: "TitleBar", cap: tuple) -> float:
        """分出去的那一个算胶囊的几成：在圆边上还是圆的（底色跟着圆的悬停、按下），走到四分之三就是胶囊的（底色换成胶囊的，够得着胶囊才伸出水桥）。"""
        return _smooth((self.progress(bar, cap) - 0.22) / 0.55)

    # ---- 推 ----
    def step(self, dt: float, bar: "TitleBar") -> bool:
        """推一帧；返回 False = 走完了（TitleBar 收起这一层，自己画）。"""
        t = self.t = self.t + dt
        c0, ring, _ = self.circle(bar)
        cap = self.cap(bar)
        left, hw, hh, cy = cap
        rim = ring + sticker.OUTLINE / 2.0
        new_w = bar.tag.target
        goal = self.slot(bar, cap) if self.into else c0.x()
        before = self.x.value
        travel, ease = (FLOW_TRAVEL_S, _smoother) if self.into else (FLOW_BACK_S, _smooth)
        self.x.step(dt, self.x_from + (goal - self.x_from) * ease((t - self.delay) / travel))
        speed = abs(self.x.value - before) / dt if dt > 0.0 else 0.0
        m = self.progress(bar, cap)
        self.drop_r = rim + (FLOW_DROP_R - rim) * _smooth(m / 0.5)              # 圆那么大 → 走到一半时缩成放得进胶囊的大小
        head = self.head(bar, cap)
        r = self.drop_r
        gap_c = math.hypot(head.x() - c0.x(), head.y() - c0.y()) - (rim * self.cs.value + r)
        gap_k = math.hypot(head.x() - (left + hh), head.y() - cy) - (hh + r)
        if self.into:
            if self.parted is None and gap_c > FLOW_REACH:
                self.parted = t
            if self.contact is None and gap_k < FLOW_REACH:
                self.contact = t
        else:
            if self.parted is None and gap_k > FLOW_REACH:
                self.parted = t
            if self.touch is None and gap_c < 0.0:
                self.touch = t
        attached = self.parted is None and t > self.delay
        pull = 0.25 * _smooth((gap_c if self.into else gap_k) / FLOW_REACH + 0.3) if attached else 0.0
        self.sx.step(dt, 1.0 + pull + min(0.10, speed / 2600.0))               # 被拉着时拉长，断开后弹回来；跑得快时也略长一点
        if self.into:
            cs_goal = 1.0 + (0.06 * _smooth(gap_c / FLOW_REACH + 0.8) if attached else 0.0)
            self.circle_size = min(1.0, self.circle_size + dt / FLOW_VANISH_S)    # 回来到一半又进去：缩下去的圆长回来
        else:
            cs_goal = 1.0                                                      # 回来到位时大小不吞（回弹在左右，不在大小）
            self.circle_size = max(0.0, self.circle_size - dt / FLOW_VANISH_S)
        self.cs.step(dt, cs_goal)
        # 胶囊：吞一律按两个宽里窄的那个算；进的时候要变窄就先往新宽度收；回来要变宽，等那一滴让开了再长
        narrow = min(self.w_from, new_w) / 2.0
        if self.into:
            if self.contact is None:
                hw_goal = new_w / 2.0 if new_w < self.w_from else self.w_from / 2.0
            elif t - self.contact < FLOW_GULP_S:
                hw_goal = FLOW_GULP * narrow
            else:
                hw_goal = new_w / 2.0
        else:
            new_left = bar.left.value + (bar.tag.value - new_w) * bar._grow_share()
            clear = head.x() + r * self.sx.value < new_left - FLOW_REACH - 2.0
            if t < self.delay:
                hw_goal = self.w_from / 2.0
            elif self.gulp and (self.parted is None or t - self.parted < 0.06 or (new_w > self.w_from and not clear and self.touch is None)):
                # 那一滴回到圆那儿（touch）就不再等它让开：有新版本胶囊时名字靠左，左头离圆只有 INSET，那一滴停稳了也「让不开」
                hw_goal = FLOW_GULP * narrow
            else:
                hw_goal = new_w / 2.0
        self.hw.step(dt, hw_goal)
        # 内容：旧的字（和种类图标）糊开淡掉；新的等胶囊差不多停了再糊进来；app 图标是带着走的，不在新的那层里
        if self.into:
            if self.parted is not None:
                self.circle_back = min(1.0, self.circle_back + dt / 0.22)
            new_at = None if self.contact is None else self.contact + 0.12
            new_key = None
        else:
            if self.circle_size == 0.0:
                self.circle_back = 0.0                                         # 圆里的 ‹ 跟着圆一起缩没（paint），不另外淡
            if new_w > self.w_from:
                new_at = t if self.hw.value > self.w_from / 2.0 else None       # 长名字：胶囊开始往外长了再出来
            else:
                new_at = 0.30
            new_key = bar._icon
        if not self.new_added and new_at is not None and t >= new_at:
            self.layers.append([new_key, bar._text, bar._outlined, new_w, 0.0, 1.0])
            self.new_added = True
        for layer in self.layers:
            if layer[5] > layer[4]:
                layer[4] = min(layer[5], layer[4] + dt / 0.26)
            elif layer[5] < layer[4]:
                layer[4] = max(layer[5], layer[4] - dt / 0.14)
        self.layers = [layer for layer in self.layers if layer[4] > 0.0 or layer[5] > 0.0]
        return not self._done(bar)

    def _done(self, bar: "TitleBar") -> bool:
        if self.t > 3.0:
            return True                                                      # 兜底：怎么都该走完了
        if self.into and (self.contact is None or self.t < self.contact + 0.3):
            return False
        if not self.into and (self.touch is None or self.t < self.touch + 0.25 or self.circle_size > 0.0
                              or not self.x.settled(self.circle(bar)[0].x(), 0.05)):
            return False                                                     # 回来：冲过头再回来、停稳在圆心，换回真的圆时不跳
        if self.into and self.circle_size < 1.0:
            return False
        return (self.new_added and self.hw.settled(bar.tag.target / 2.0, 0.05) and self.cs.settled(1.0, 0.002)
                and self.sx.settled(1.0, 0.004) and abs(self.x.velocity) < 1.0
                and all(layer[4] == layer[5] for layer in self.layers) and self.circle_back in (0.0, 1.0))

    # ---- 画 ----
    def paint(self, p: QPainter, bar: "TitleBar") -> None:
        cap = self.cap(bar)
        left, hw, hh, cy = cap
        cs = self.cs.value
        c0, ring, scale = self.circle(bar)
        squash = 1.0 - (cs - 1.0) * 0.5
        lead = bar.lead
        fill = lead.fill_color() if lead is not None else QColor(sticker.PAPER_2)
        paper = QColor(sticker.PAPER_2)                                        # 胶囊的底（和 TitleBar 自己画的一样）
        ink = QColor(sticker.INK)
        ink_c = sticker.contrast_color(fill)
        pen_w = sticker.OUTLINE * scale
        m = self.progress(bar, cap)
        k = self.share(bar, cap)
        head = self.head(bar, cap)
        sx = self.sx.value
        sy = 1.0 / math.sqrt(sx)
        rp = max(0.5, self.drop_r - pen_w / 2.0)                              # 描边中线的半径（和圆一样按中线画）
        grow = 0.35 + 0.65 * _smooth(self.circle_size)                         # 左边的圆缩到哪（回来时缩没；回来到一半又进去时长回来）
        drop = QPainterPath()
        drop.addEllipse(head, rp * sx, rp * sy)
        capsule = QPainterPath()                                               # 胶囊：底按整颗填，描边按中线（往里半根线宽），和 TitleBar 自己画的一样
        capsule.addRoundedRect(QRectF(left, cy - hh, 2.0 * hw, 2.0 * hh), hh, hh)
        po = sticker.OUTLINE / 2.0
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(left + po, cy - hh + po, 2.0 * (hw - po), 2.0 * (hh - po)), hh - po, hh - po)
        cap_c = QPointF(left + hh, cy)
        gap = math.hypot(head.x() - cap_c.x(), head.y() - cap_c.y()) - (hh + self.drop_r * sy)
        v = FLOW_NECK * (1.0 if gap <= 0.0 else _smooth(1.0 - gap / FLOW_REACH)) * k
        bridge = _metaball(head, rp * sy, cap_c, hh - po, v) if v > 0.01 else None   # 那一个和胶囊之间的水桥（走过一大半了才连）
        outline = outline.united(drop)
        if bridge is not None:
            outline = outline.united(bridge)
        # 1) 都是白底黑框，连着的几块合成一整块、黑框一笔连着（不在交界处画线）：
        #    进：圆 + 分出去的那一个 + 胶囊，加上中间连着的那截；回来：返回键连圆往圆心缩、淡掉（‹ 跟着缩）自己画，分出去的那一个回去当这个圆
        if self.into:
            body = QPainterPath()
            body.addEllipse(c0, ring * cs * grow, ring * squash * grow)
            gap = math.hypot(head.x() - c0.x(), head.y() - c0.y()) - (ring * cs * grow + rp * sy)
            v = FLOW_NECK * (1.0 if gap <= 0.0 else _smooth(1.0 - gap / FLOW_REACH))
            neck = _metaball(c0, ring * cs * grow, head, rp * sy, v) if v > 0.01 else None
            if neck is not None:
                body = body.united(neck)
            p.fillPath(body, fill)
            outline = outline.united(body)
        elif self.circle_size > 0.0:
            sv = _smooth(self.circle_size)
            p.save()
            p.setOpacity(p.opacity() * sv)
            p.setPen(QPen(ink, pen_w * max(0.3, sv)))
            p.setBrush(fill)
            p.drawEllipse(c0, ring * grow, ring * grow)
            if self.circle_back > 0.0:
                p.setOpacity(p.opacity() * self.circle_back)
                draw_icon(p, "back", c0, (lead.glyph_size() * scale if lead is not None else 13.7) * grow, ink_c, fill)
            p.restore()
        p.fillPath(drop, sticker.mix(fill, paper, k))                          # 分出去的那一个：底从圆的（悬停、按下的样子）慢慢换成胶囊的
        p.fillPath(capsule, paper)
        if bridge is not None:
            p.fillPath(bridge, paper)
        p.strokePath(outline, QPen(ink, pen_w))
        # 3) 进：圆里的返回 ‹ 糊进来（回来时它跟着圆缩没，在 1) 里画）
        if self.into:
            box = QRectF(c0.x() - 15.0, c0.y() - 15.0, 30.0, 30.0)
            a = _smooth(self.circle_back)
            size = lead.glyph_size() * scale * grow if lead is not None else 13.7
            _blurred(p, lambda q: draw_icon(q, "back", c0, size, ink_c, fill), box, FLOW_BLUR * (1.0 - a), a)
        # 4) 胶囊里的字（和种类图标）：每层按它自己的宽排好（不跟着吞的那一下换省略号），贴着胶囊现在的左边，剪在胶囊里
        widest = max([2.0 * hw] + [layer[3] for layer in self.layers])
        box = QRectF(left - 8.0, cy - hh - 6.0, widest + 16.0, 2.0 * hh + 12.0)
        for key, text, outlined, width, presence, _ in self.layers:
            a = _smooth(presence)
            _blurred(p, lambda q, key=key, text=text, outlined=outlined, width=width: bar._paint_content(q, key, text, outlined, left, width, cy),
                     box, FLOW_BLUR * (1.0 - a), a, capsule)
        # 5) 带着走的 app 图标：圆里的字色（按下时圆变深、图标是浅的）慢慢换成胶囊里的黑，慢慢放大成胶囊里的大小；跑得快时稍微糊一点
        color = sticker.mix(ink_c, ink, k)
        width = marks.APP_W * scale + (marks.SPECIES_W - marks.APP_W * scale) * m
        box = QRectF(head.x() - 15.0, head.y() - 15.0, 30.0, 30.0)
        _blurred(p, lambda q: marks.draw_app(q, head, color, width), box, min(2.0, abs(self.x.velocity) / 450.0), 1.0)


def _pill(rect: QRectF, rl: float, rr: float) -> QPainterPath:
    """左头横半径 rl、右头横半径 rr 的胶囊（被挤的那头扁一点）。"""
    h = rect.height() / 2.0
    rl, rr = max(0.5, min(rl, rect.width() / 2.0)), max(0.5, min(rr, rect.width() / 2.0))
    x0, x1, y0, y1 = rect.left(), rect.right(), rect.top(), rect.bottom()
    path = QPainterPath()
    path.moveTo(x0 + rl, y0)
    path.lineTo(x1 - rr, y0)
    path.arcTo(QRectF(x1 - 2.0 * rr, y0, 2.0 * rr, 2.0 * h), 90.0, -180.0)
    path.lineTo(x0 + rl, y1)
    path.arcTo(QRectF(x0, y0, 2.0 * rl, 2.0 * h), 270.0, -180.0)
    path.closeSubpath()
    return path


class _ChipIn:
    """新版本胶囊挤进来。
    胶囊在最后的位置从右往左长出来：右头钉在最后的位置，左头一根会过头一点再回来的弹簧（灵动岛那样）。碰到名字以后名字才开始走，
    从碰上那一刻起只朝它最后的位置走（TitleBar 的 left、tag 两根不回弹的弹簧 retarget：一路往左、速度不掉到 0、不往回走）；它比胶囊慢一点（不太情愿），
    右头被压扁一点（name_box：压扁多少看两个叠了多少，高多 10%、右头扁到 45%）。两个之间的空从碰上起拉开到最后那个（OPEN_S），不按时刻分段。
    只管胶囊的左头、名字什么时候走、压扁多少；挤完交还给 TitleBar 平常的排法（chip_rect），那时两个正好在最后的位置。"""
    OMEGA, ZETA = 13.0, 0.6        # 胶囊的左头
    NUB = 6.0                      # 一开始露出来多少（从 × 那边冒出来）
    OPEN_S = 0.25                  # 碰上以后两个之间的空拉开要多久

    def __init__(self, bar: "TitleBar"):
        self.t = 0.0
        self.contact: Optional[float] = None
        self.lo = _Elastic(0.0, self.OMEGA, self.ZETA)
        self.aim(bar)
        self.lo.value = self.chip_r - self.NUB

    def aim(self, bar: "TitleBar") -> None:
        """最后的位置（TitleBar.retarget 时重算）：名字的左边和宽、三段空，胶囊的左右头。"""
        name, chip, _ = bar._plan(bar._peek)
        self.left_f, self.name_f = bar._left_target(name), name
        self.gap_f = max(float(bar.GAP), (bar._end() - self.left_f - name - chip) / 2.0)   # 和 chip_rect 平时的算法一样：交接时不跳
        self.chip_l = self.left_f + name + self.gap_f
        self.chip_r = self.chip_l + chip

    def gap(self) -> float:
        """名字和胶囊之间现在空多少：碰上之前贴着，碰上以后拉开到最后那个。"""
        return 0.0 if self.contact is None else self.gap_f * _smooth((self.t - self.contact) / self.OPEN_S)

    def step(self, dt: float, bar: "TitleBar") -> bool:
        """推一帧；返回 False = 挤完了。"""
        self.t += dt
        self.lo.step(dt, self.chip_l)
        if self.contact is None and (self.lo.value <= bar.left.value + bar.tag.value + 0.5 or self.lo.settled(self.chip_l, 0.05)):
            self.contact = self.t
            bar.left.retarget(self.left_f)                                  # 从这一刻起朝最后的位置走：一根弹簧一路过去
            bar.tag.retarget(self.name_f)
        return not (self.contact is not None and self.t - self.contact >= self.OPEN_S and self.lo.settled(self.chip_l, 0.05)
                    and bar.left.settled and bar.tag.settled)

    def name_box(self, bar: "TitleBar") -> tuple[float, float]:
        """名字胶囊现在画多宽、右头压扁多少（0..1）：胶囊的左头（减去正在拉开的空）压过它的右头就压扁，最窄一个正圆。"""
        w = max(float(bar.H), bar.tag.value)
        drawn = max(float(bar.H), min(w, self.lo.value - self.gap() - bar.left.value))
        return drawn, 1.0 - drawn / w


class TitleBar(QWidget):
    """顶部栏：卡片的标题行。设置卡片每一页都是这同一条，换页不重建、不挪走，只有里面的字、宽度和左边圆里的图案在变。
    从左到右：左边的圆（set_lead：None 没有 / 'mark' app 图标 / 'back' 返回 ‹，见 _Lead）、名字胶囊（米白底、黑描边、黑字，小图标 + 名字或页名；
    都和「添加同桌」一个颜色；outlined 是不是名字的标签，比如「添加同桌」，字不加粗）、新版本胶囊（set_chip，见下面）；× 是卡片的，和这一条并排（Card._head），不在里面。
    名字胶囊里的小图标（set_icon）：写的是同桌的名字时是它的物种图标（狗 = 骨头，模型包里写），别的是 app 图标（marks.APP）；换的时候和字同一个节拍先出后进。
    app 图标从左上角的圆流进胶囊（set_look：圆从 app 图标换成返回、胶囊同时换成 app 图标，就是进高级设置）：照灵动岛的节奏、带回弹（_Flow），
    回来反过来流回圆里；流的时候圆、胶囊、那一滴连同里面的图案和字整块画在上面一层（_FlowLayer），这一条自己不画名字胶囊。
    位置：centered 时名字胶囊整颗在这一条的左头到 × 右边的正中（设置卡片里就是内容区正中，和下面的狗一条线），最宽是两头各让出圆（或 ×）再空 INSET；
    有新版本胶囊时圆 → 名字 → 新版本胶囊 → × 三段空一样宽（_even_gap，撑满时每段 GAP）。不 centered（普通卡片）一直靠左。
    所以换页时胶囊不跑：只有字和宽度在变，新版本胶囊出现 / 消失时才往左让 / 回正中。
    所有位置都是小数（Qt 控件的位置和宽只能是整数，拿它们做动画会一格一格地走）：胶囊的左边和宽各一根不回弹的弹簧（Spring 0.3），两根一样快，居中时正中不动；
    停下时左边是整数，1 倍屏上字不糊。
    换字（字不跳、不闪）：旧字先淡出、淡没了再换新字淡入（各 TEXT_FADE_S 的一半），任何时候只画一行；来回快换时从现在的浓淡接着淡，不会忽然全浓。
    名字 ↔ 标签只是字的粗细不同，照上面的规矩先出后进。左边圆里的图案也是先出后进。
    放不下的字只有一种画法（widgets.draw_strip）：省略号钉在字窗两头，浓淡跟着位置连续变，所以缩放、开始滚、滚到头都不跳。名字为空：只剩小图标，胶囊是 26 的正圆。
    新版本胶囊（一直在，直到点它）：几种说法从长到短（i18n.says），
    按名字剩下的地方挑放得下的最长那句，换说法时旧的淡出、新的淡入，不滚、不出省略号（_plan）；平常最少留最短的那句，名字还放不下才省略。
    出现时从 × 那边长出来、把名字往左挤，名字从碰上起一路走到位、中间不停，右头被压扁一点（_ChipIn）；收走时往右缩、淡掉，名字回正中。
    两个互相挤（set_peek）：鼠标在被省略的名字上停 0.5 秒（和悬浮说明同一个计时，不出「点击改名」），名字最多拉到只给胶囊留一个圆，
    胶囊再挑放得下的说法，最短的也放不下才缩成只剩下载图标的圆，名字还放不下就滚；鼠标放到被换短了的新版本胶囊上，它立刻往左展开成整句，
    名字让开（最窄是只剩小图标的正圆），整句还放不下就在胶囊里滚；移开马上恢复。
    点名字胶囊做什么看 click_action：'rename' 就地改名（Card.start_rename：Qt 的输入框放进胶囊里：胶囊一直居中、两边一起长，前面的字每打一个往左挪半个字宽，
    输入框跟着胶囊的弹簧走；长到最宽就不长了，输入框里自己滚，左边是省略号、最后打的字一直看得见（NameEdit 画省略号）；底还没到的地方字是米白落在米白卡片上，
    看不见，底长过来字才露出来）、'open' 发 name_clicked（松开时还在胶囊上才算）、None 不理（按下照旧拖卡片）。
    鼠标进出名字胶囊发 name_hovered；set_lift 把胶囊往上抬几像素（设置主页面：和正中那只狗同一根弹簧一起抬，ROOM 是给它留的空）。
    动画节拍跟屏幕刷新率（和狗同一套），不动就停。系统开了「减少动态效果」、卡片正在打开那一下对齐设置（Card.still）：直接到位，字不滚。"""
    H = 26
    ROOM = 4                                          # 胶囊上面多留的空：名字胶囊被抬起来（set_lift，设置主页面最多 3）时不被裁；圆、×、胶囊平时的顶都在它下面（离卡片上边还是 16）
    TAG_L, TAG_SP, TAG_R = 10, 6, 12                  # 名字胶囊：左边距、小图标和字的空、右边距（描边标签也一样）
    CHIP_L, CHIP_ICON, CHIP_SP, CHIP_R = 10, 14, 6, 12
    GAP = 8                                           # 有新版本胶囊时三段空（圆 → 名字 → 胶囊 → ×）最少多宽
    INSET = 8                                         # 名字胶囊离左边的圆多远：靠左时贴在这儿，居中时两头（圆、×）各让出这么多。只有这一个数：新版本胶囊出现时长名字的左边不往右跳
                                                      # （和 GAP 一样，居中的名字最宽 280 − 2 ×（26 + 8）= 212）
    FADE_S = 0.2                                      # 新版本胶囊出现 / 消失的淡入淡出；换说法时旧的淡出、新的淡入也是这么长
    TEXT_FADE_S = 0.24                                # 换字：旧字先淡出（前一半），新字再淡入（后一半），两行不叠在一起；左边圆里的图案、胶囊的底也是这么长
    MARK_W, MARK_H = marks.BOX_W, marks.BOX_H        # 小图标占的格子
    chip_clicked = Signal()
    name_clicked = Signal()                           # click_action 是 'open' 时点了名字胶囊
    name_hovered = Signal(bool)                       # 鼠标进 / 出名字胶囊
    back_clicked = Signal()                           # 左边的圆是返回（'back'）时点了它
    mark_clicked = Signal()                           # 左边的圆是 app 图标（'mark'）、mark_clickable 时点了它（设置卡片：进「关于」页）

    def __init__(self, card: "Card"):
        super().__init__()
        self.card = card
        self.setFixedHeight(self.H + self.ROOM)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self._text, self._outlined = "", False        # 要显示的字、是不是标签（不是名字，字不加粗；setText）
        self._drawn_text, self._drawn_outlined = "", False   # 正在画的那一行：换字时它先淡出，淡没了才换成要显示的
        self._drawn_alpha = 1.0
        self._icon = marks.APP                        # 胶囊里要显示的小图标（set_icon）：marks.APP 或物种图标；正在画的那个先淡出、再换成它淡入
        self._drawn_icon, self._icon_alpha = marks.APP, 1.0
        self._flow: Optional[_Flow] = None            # app 图标正在圆和胶囊之间流（set_look）：整块画在 _FlowLayer
        self._flow_layer: Optional[_FlowLayer] = None
        self.chip_text = ""                           # 新版本胶囊最长的那句（空 = 没有）
        self.chip_says: tuple[str, ...] = ()          # 它的几种说法，从长到短（set_chip）
        self._shown_says: tuple[str, ...] = ()        # 正在画的那只胶囊的说法（收走淡出时 chip_says 已经空了，它还留着）
        self._say: Optional[str] = None               # 胶囊上现在写哪句（None = 只剩下载图标的圆）
        self._say_prev: Optional[str] = None          # 换说法时正淡出的那句
        self.mark_clickable = False                   # 'mark' 时左边的圆点得了（设置卡片：点 app 图标进「关于」页）；别的卡片鼠标穿过它
        self._say_k = 1.0                             # 换说法淡到哪（0 刚换，1 换完）
        self._chip_in: Optional[_ChipIn] = None       # 新版本胶囊正挤进来（set_chip）
        self._chip_out_right: Optional[float] = None  # 正收走的胶囊：右头钉在这，往右缩
        self.name_font = QFont()
        self.name_font.setPixelSize(13)
        self.name_font.setBold(True)
        self.label_font = QFont()                     # 描边标签的字：不加粗
        self.label_font.setPixelSize(13)
        self.chip_font = QFont()
        self.chip_font.setPixelSize(12)
        self.chip_font.setBold(True)
        self.edit = NameEdit(self)                   # 点胶囊改名（Card.start_rename）：输入框就长在胶囊里
        self.edit.setProperty("titleedit", True)
        self.edit.setTextMargins(0, 0, 0, 0)
        self.edit.setMaxLength(NAME_MAX * 12)         # 真正的上限按看得见的字数算（Card._limit_name）
        self.edit.setVisible(False)
        self.edit.textChanged.connect(lambda _t: self.retarget())
        self.edit.preeditEdited.connect(lambda _t: self.retarget())   # 拼音还没选字时显示的字母也算宽度
        self.edit.compositionFinished.connect(self.retarget)
        self.left = Spring(0.0, 0.3)                  # 名字胶囊的左边
        self.tag = Spring(self.H, 0.3)                # 名字胶囊的宽
        self.chip_w = Spring(0.0, 0.3)                # 新版本胶囊的宽（_plan 挑的那句的宽，或 26 的正圆；收走时缩回 0）
        self.marquee = Marquee()                      # 新版本胶囊上的字（整句比整条还长、又展开着时才滚）
        self.name_marquee = Marquee()                 # 名字（正在画的那一行）：展开了还放不下才滚
        self._peek: Optional[str] = None              # "name" / "chip"：哪一个展开、往对面挤（set_peek）
        self._watch = QTimer(self)                    # 展开期间、鼠标在名字上期间每 50 毫秒看一眼鼠标还在不在上面（鼠标一下子甩出卡片时 Qt 不一定发 Leave）
        self._watch.setInterval(50)
        self._watch.timeout.connect(self._check_watch)
        self.lead: Optional[_Lead] = None             # 左边的圆（set_lead 要了才建）
        self.lead_mode: Optional[str] = None          # None / "mark" / "back"
        self._lead_to = 0.0                           # 圆里的图案要淡到哪：0 app 图案，1 返回
        self.centered = False                         # 名字胶囊整颗居中（没有新版本胶囊时；set_centered）
        self.click_action: Optional[str] = None       # 点名字胶囊："rename" / "open" / None（Card.set_renamable、set_title_click）
        self._name_hover = False                      # 鼠标在名字胶囊上
        self._name_press = False                      # "open"：在名字胶囊上按下了，松开时还在上面才算点
        self._lift = 0.0                              # 名字胶囊往上抬了几像素（set_lift）
        self._chip_shown, self._chip_alpha = "", 0.0  # 正在画的新版本胶囊（淡出时 chip_text 已经空了，它还留着）
        self._chip_hover = False
        self._shown = False                           # 显示过了（打开之前改的都直接到位）
        self.name_shown = True                        # 中间有没有名字胶囊（关于页没有，set_name_shown）
        self._name_vis = 1.0                          # 名字胶囊现在露出来多少（收起时变淡、稍微缩小）

    def _can_animate(self) -> bool:
        return (self.isVisible() and self._shown and not native.reduce_motion()
                and not getattr(self.card, "_still", False))

    # ---- 内容 ----
    def text(self) -> str:
        return self._text

    @property
    def outlined(self) -> bool:
        return self._outlined

    def setText(self, text: str, animated: bool = True, outlined: bool = False) -> None:
        """换胶囊上的字（outlined：不是名字的标签，比如「添加同桌」，字不加粗）。显示着就先淡出旧的、再淡入新的，胶囊的宽同时用弹簧变过去。
        animated=False：直接换好；字没变也把还在走的淡入淡出走完（换页时滑动条可能已经带动画地报过同一个字）。"""
        content = (text, bool(outlined))
        if content == (self._text, self._outlined):
            if not animated:
                self._finish_text()
            return
        self._text, self._outlined = content
        if not (animated and self._can_animate()) or self.editing:
            self._finish_text()
        elif not self._drawn_text:
            self._drawn_text, self._drawn_outlined, self._drawn_alpha = content[0], content[1], 0.0   # 原来是空的：没有要淡出的，直接淡入
        self.retarget(animated)
        self.update()

    def _finish_text(self) -> None:
        self._drawn_text, self._drawn_outlined, self._drawn_alpha = self._text, self._outlined, 1.0
        self._drawn_icon, self._icon_alpha = self._icon, 1.0
        self.update()

    @property
    def editing(self) -> bool:
        return self.edit.isVisible()

    def set_editing(self, on: bool, text: str = "") -> None:
        if on:
            self.edit.setText(text)
            self._finish_text()
            self._end_peek()                          # 改名时按平常的排法（居中的一直居中），放不下就在输入框里自己滚
            self.edit.elide_colors = (QColor(sticker.PAPER_2), QColor(sticker.INK))   # 滚出去的那头盖一个省略号：胶囊的底色、字的颜色
        self.edit.setVisible(on)
        self.retarget()
        self.update()

    def set_name_shown(self, on: bool, animated: bool = True) -> None:
        """中间的名字胶囊要不要（关于页不要：只留 ‹ 和 ×）。收起时变淡、稍微缩小，长回来反过来；和换字同一个节拍。"""
        if on == self.name_shown and (self._name_vis == (1.0 if on else 0.0)):
            return
        self.name_shown = on
        if not (animated and self._can_animate()):
            self._name_vis = 1.0 if on else 0.0
            self.update()
            return
        self._run()

    def set_chip(self, text, animated: bool = True) -> None:
        """新版本胶囊：一句话，或几种说法从长到短（i18n.says）；空 = 没有。出现时从 × 那边长出来、把名字往左挤（_ChipIn），
        收走时往右缩、淡掉，名字回正中。"""
        says = tuple(s for s in ((text,) if isinstance(text, str) else tuple(text)) if s)
        if says == self.chip_says:
            return
        fresh = not self.chip_says and self._chip_alpha <= 0.0          # 原来一点都没有（不是收到一半又回来）
        self.chip_says, self.chip_text = says, (says[0] if says else "")
        if says:
            if says != self._shown_says:
                self.marquee = Marquee()
            self._shown_says, self._chip_shown = says, says[0]
            self._chip_out_right = None
        else:
            if self._peek == "chip":
                self._end_peek()
            self._chip_in = None
            if self._chip_shown:
                self._chip_out_right = self.chip_rect().right()          # 往右缩：右头钉住
        if not (animated and self._can_animate()):
            self._chip_in = None
            self._chip_alpha = 1.0 if says else 0.0
            if not says:
                self._chip_shown, self._shown_says, self._chip_out_right = "", (), None
        elif says and fresh:
            self._chip_in = _ChipIn(self)
        self.retarget(animated)
        self.update()

    def set_lead(self, mode: Optional[str], animated: bool = True) -> Optional[_Lead]:
        """左边的圆：None 没有；'mark' app 图标（mark_clickable 时点了发 mark_clicked，不然点了没反应、按下照旧拖卡片）；'back' 返回（点了发 back_clicked）。
        换的时候圆不动，里面的图案先淡出再淡入。返回那个圆（要了才建，从来没要过就是 None）。"""
        return self.set_look(mode, self._icon, animated)

    def set_icon(self, icon: str, animated: bool = True) -> None:
        """名字胶囊里的小图标：marks.APP（app 图标）或物种图标（"bone"、模型包里的图）。换的时候和字同一个节拍先淡出再淡入。"""
        self.set_look(self.lead_mode, icon, animated)

    def _home(self, mode: Optional[str], icon: str) -> Optional[str]:
        """app 图标只在一处的时候在哪："circle" 左上角的圆（胶囊里是物种图标），"capsule" 名字胶囊（圆里是返回）；两处都有、都没有是 None。"""
        if mode == "mark" and icon != marks.APP:
            return "circle"
        if mode == "back" and icon == marks.APP:
            return "capsule"
        return None

    def set_look(self, mode: Optional[str], icon: str, animated: bool = True, flow: bool = True) -> Optional[_Lead]:
        """左边的圆和名字胶囊里的小图标一起换（设置卡片换页时，settings._seat_title）。app 图标从圆换到胶囊（进高级设置）或者反过来：
        它流过去（_Flow）；别的换法圆里、胶囊里各自先淡出再淡入。flow=False：不流（进出「关于」页，app 图标走的是关于页自己那一段，
        widget/about.py 的 Hero），胶囊里照别的换法淡。返回左边那个圆。"""
        before = self._home(self.lead_mode, self._icon)
        after = self._home(mode, icon)
        if icon != self._icon:
            self._icon = icon
            if not (animated and self._can_animate()):
                self._drawn_icon, self._icon_alpha = icon, 1.0
        lead = self._set_lead(mode, animated)
        flowing = flow and ((before, after) in (("circle", "capsule"), ("capsule", "circle")) or (self._flow is not None and after is not None))
        if flowing and animated and self._can_animate() and lead is not None:
            into = after == "capsule"
            if self._flow is None or self._flow.into != into:
                self._start_flow(into)                 # 流到一半又反过来：新的一趟从现在的样子接着走
        else:
            self._end_flow()
        self.update()
        return lead

    def _start_flow(self, into: bool) -> None:
        self._flow = _Flow(self, into, self._flow)
        if self._flow_layer is None:
            self._flow_layer = _FlowLayer(self)
        self._flow_layer.place()
        self._flow_layer.show()
        self._flow_layer.raise_()
        if self.lead is not None:
            self.lead.flow_hidden = True               # 圆连图案都画在上面一层（会鼓、会吞）
            self.lead.update()
        self._run()

    def _end_flow(self) -> None:
        """流完了（或者不流了）：收起上面那一层，圆和胶囊自己画；画出来的字、图标直接是现在要显示的。"""
        if self._flow is None:
            return
        self._flow = None
        if self._flow_layer is not None:
            self._flow_layer.hide()
        if self.lead is not None:
            self.lead.flow_hidden = False
            self.lead.mix = self._lead_to
            self.lead.update()
        self._finish_text()
        self.update()

    @property
    def _flow_on(self) -> bool:
        return self._flow is not None

    def _set_lead(self, mode: Optional[str], animated: bool) -> Optional[_Lead]:
        if mode is not None and self.lead is None:
            self.lead = _Lead(self)
            self.lead.move(0, self.ROOM)
            self.lead.clicked.connect(self._lead_clicked)
            if self._flow_layer is not None:
                self._flow_layer.raise_()
        self.lead_mode = mode
        lead = self.lead
        if lead is not None:
            back = mode == "back"
            live = back or (mode == "mark" and self.mark_clickable)    # 点得了：返回；设置卡片上的 app 图标（进「关于」页）
            lead.setVisible(mode is not None)
            lead.setAttribute(Qt.WA_TransparentForMouseEvents, not live)
            lead.setCursor(Qt.PointingHandCursor if live else Qt.ArrowCursor)
            lead.setAccessibleName(tr("Back") if back else tr("About") if live else config.APP_NAME)
            if not live and (lead._hover or lead.underMouse()):
                QApplication.sendEvent(lead, QEvent(QEvent.Leave))   # 刚点了返回、鼠标还停在圆上：鼠标穿过它以后不会再有 Leave，照离开算（悬停的深底、放大退回去）
            self._lead_to = 1.0 if back else 0.0
            if not (animated and self._can_animate()):
                lead.mix = self._lead_to
                lead.update()
        self.retarget(animated)
        return lead

    def _lead_clicked(self, _=False) -> None:
        if self.lead_mode == "back":
            self.back_clicked.emit()
        elif self.lead_mode == "mark" and self.mark_clickable:
            self.mark_clicked.emit()

    def set_centered(self, on: bool, animated: bool = True) -> None:
        """名字胶囊整颗居中（没有新版本胶囊时）。设置卡片每一页都开着：换页时胶囊不跑，只变字和宽。"""
        if on != self.centered:
            self.centered = on
            self._end_peek()
            self.retarget(animated)

    def set_lift(self, px: float) -> None:
        """名字胶囊往上抬 px 像素（设置主页面：和正中那只狗同一根弹簧，petstrip.PetStrip.lift_changed）。只抬胶囊（不放大：放大了 1 倍屏上字发糊），
        圆、新版本胶囊、× 不动；点和悬停还按没抬的位置算（不然在边上来回跳）。"""
        px = max(0.0, min(float(self.ROOM), float(px)))
        if px != self._lift:
            self._lift = px
            self.update()

    def finish_now(self) -> None:
        """所有过渡立刻走到头（单测、关卡片时用）。"""
        if self._chip_in is not None:
            self.retarget(animated=False)                                   # 挤进来还没碰上名字时名字的目标还没给（_ChipIn）
        for spring in self._springs():
            spring.set_target(spring.target, instant=True)
        self._end_flow()
        self._finish_text()
        if self.lead is not None:
            self.lead.mix = self._lead_to
            self.lead.update()
        self._name_vis = 1.0 if self.name_shown else 0.0
        self._chip_alpha = 1.0 if self.chip_text else 0.0
        if not self.chip_text:
            self._chip_shown, self._shown_says, self._chip_out_right = "", (), None
        self._say, self._say_prev, self._say_k = self._plan(self._peek)[2], None, 1.0
        self._place_edit()
        self.update()

    # ---- 尺寸（小数） ----
    def text_x(self, outlined: Optional[bool] = None) -> float:
        """字离胶囊左边多远：先是小图标（名字、标签都有）。outlined 留着给老的调用。"""
        return float(self.TAG_L + self.MARK_W + self.TAG_SP)

    def _text_r(self, outlined: bool) -> float:
        return float(self.TAG_R)

    def icon_center(self) -> QPointF:
        """胶囊里小图标的中心（现在画出来的位置，抬起来的也算）：胶囊是正圆时在正中，长成胶囊的路上滑到左边。"""
        x0, w = self.left.value, self.tag.value
        g = max(0.0, min(1.0, (w - self.H) / 24.0))
        mx = x0 + (self.H - self.MARK_W) / 2 * (1.0 - g) + self.TAG_L * g
        return QPointF(mx + self.MARK_W / 2, self.ROOM - self._lift + self.H / 2)

    def _font(self, outlined: bool) -> QFont:
        return self.label_font if outlined else self.name_font

    def natural_tag(self) -> float:
        if self.editing:
            fm = QFontMetricsF(self.name_font)
            return self.text_x(False) + fm.horizontalAdvance(self.edit.shown_text()) + 3.0 + self.TAG_R    # + 光标
        if not self._text:
            return float(self.H)                                                           # 名字为空：正圆
        fm = QFontMetricsF(self._font(self._outlined))
        return self.text_x() + fm.horizontalAdvance(self._text) + self._text_r(self._outlined)

    def chip_natural(self, text: Optional[str] = None) -> float:
        """新版本胶囊写 text 要多宽（不给就是最长那句）。"""
        text = self._chip_shown if text is None else text
        return self.CHIP_L + self.CHIP_ICON + self.CHIP_SP + QFontMetricsF(self.chip_font).horizontalAdvance(text) + self.CHIP_R

    def _close_box(self) -> Optional[tuple[float, float]]:
        """卡片的 ×（和这一条并排）在这一条的坐标里：(左边, 宽)；没有 × 就 None。"""
        close = getattr(self.card, "_close", None)
        try:
            if close is None or close.isHidden() or close.parentWidget() is not self.parentWidget() or close.x() <= self.x():
                return None
            return float(close.x() - self.x()), float(close.width())
        except RuntimeError:                         # 程序退出时 × 可能已经先删了（这一条收起时还会来问）
            return None

    def _end(self) -> float:
        """× 的左边（这一条的坐标）。布局里这一条和 × 之间还隔着一段间距，位置要按 × 本身算，不然新版本胶囊离 × 比离名字胶囊远。
        没有 ×：这一条的右头。"""
        box = self._close_box()
        if box is not None:
            return box[0]
        return float(self.width() if self.width() > 0 else 10_000)

    def _right(self) -> float:
        """新版本胶囊最靠右到哪（离 × GAP）；没有它时靠左的名字胶囊最长也到这。"""
        return self._end() - self.GAP

    def _span(self) -> float:
        """居中按哪一段的正中：这一条的左头到 × 的右边（设置卡片里就是内容区，和下面「我的同桌」的狗一条线）。"""
        box = self._close_box()
        return box[0] + box[1] if box is not None else float(max(1, self.width()))

    def _start(self) -> float:
        """靠左时名字胶囊的左边：左边有圆就在圆右边 INSET，没有就是 0。"""
        if self.lead is None or self.lead_mode is None:
            return 0.0
        return float(self.lead.width() + self.INSET)

    def _edge(self) -> float:
        """左边那个圆的右头（三段等宽从这算起）。"""
        return self._start() - self.INSET

    def _cap(self) -> float:
        """居中时名字胶囊最宽多少：两头都不压到圆和 ×（各再让出 INSET）。设置卡片里是 280 − 2 ×（26 + 8）= 212，约十二三个字。"""
        c = self._span() / 2.0
        return max(float(self.H), 2.0 * min(c - self._start(), self._end() - self.INSET - c))

    def _centered_now(self) -> bool:
        """现在是不是整颗居中排：要居中，而且没有新版本胶囊（有它时三段等宽，_even_gap）。"""
        return self.centered and not self.chip_text

    def _even_gap(self, name_w: float, chip_w: float) -> float:
        """圆 → 名字 → 新版本胶囊 → × 三段一样宽的那个空；撑满时最少 GAP。"""
        return max(float(self.GAP), (self._end() - self._edge() - name_w - chip_w) / 3.0)

    def _grow_share(self) -> float:
        """名字胶囊变宽 1 像素，左边往左挪多少：整颗居中 1/2；有新版本胶囊、三段空还宽于 GAP 时 1/3（三段一起变窄）；靠左、空已经到最少时 0。
        _Flow 算流动时胶囊画在哪用（那一滴进出高级设置时胶囊会吞、会舒展）。"""
        if self._centered_now():
            return 0.5
        if self.centered and self.chip_text and (self._end() - self._edge() - self.tag.target - self.chip_w.target) / 3.0 > self.GAP:
            return 1.0 / 3.0
        return 0.0

    def tag_max(self, peek: Optional[str] = None) -> float:
        """名字胶囊最宽多少。没有新版本胶囊：居中 _cap，靠左到 _right。有的话名字优先（_plan）：平常给胶囊留出最短那句的宽；
        peek "name"：只给它留一个正圆；"chip"：胶囊写整句（整句比整条还长时名字只剩正圆），名字让出来（最窄的正圆由 target_tag 兜着）。"""
        if not self.chip_text:
            return self._cap() if self.centered else self._right() - self._start()
        room, gap = self._right() - self._start(), float(self.GAP)
        if peek == "chip":
            return room - gap - min(self.chip_natural(self.chip_says[0]), room - gap - self.H)
        return room - gap - (float(self.H) if peek == "name" else self.chip_natural(self.chip_says[-1]))

    def target_tag(self) -> float:
        """名字优先：名字胶囊原长，再长名字就省略（改名时在输入框里滚）；最窄是正圆（名字为空，或被新版本胶囊挤的时候）。
        改名时和平常一样宽法（居中的最宽 _cap，有新版本胶囊时给它留出最短那句），长到头输入框里自己滚。"""
        return max(float(self.H), min(self.natural_tag(), self.tag_max(None if self.editing else self._peek)))

    def _plan(self, peek: Optional[str] = None) -> tuple[float, float, Optional[str]]:
        """有新版本胶囊时怎么分：(名字胶囊宽, 新版本胶囊宽, 胶囊上写哪句；None = 只剩下载图标的圆)。名字先按 tag_max 定，
        胶囊在剩下的地方挑放得下的最长那句；peek "name" 时最短那句都放不下才缩成圆，平常放不下也留最短那句（名字已经给它让过了）；
        "chip" 写整句，整句比剩下的还长就压窄、在胶囊里滚。没有新版本胶囊：(名字胶囊宽, 0, None)。"""
        if not self.chip_says:
            return self.target_tag(), 0.0, None
        peek = None if self.editing else peek
        name = max(float(self.H), min(self.natural_tag(), self.tag_max(peek)))
        room = self._right() - self._start() - self.GAP - name
        says = self.chip_says
        if peek == "chip":
            return name, max(float(self.H), min(self.chip_natural(says[0]), room)), says[0]
        for say in says:
            width = self.chip_natural(say)
            if width <= room + 0.5:
                return name, width, say
        if peek == "name":
            return name, float(self.H), None
        return name, max(float(self.H), min(self.chip_natural(says[-1]), room)), says[-1]

    def edit_capped(self) -> bool:
        """改名时字已经比胶囊最宽还宽：胶囊不再长，输入框里滚（左边是省略号）。"""
        return self.editing and self.natural_tag() > self.tag_max() + 0.5

    def _left_target(self, width: float) -> float:
        """名字胶囊宽 width 时左边该在哪。取整：停下时字落在整像素上，1 倍屏不糊。"""
        if self._centered_now():
            return float(round((self._span() - width) / 2.0))
        if self.centered and self.chip_text:
            return float(round(self._edge() + self._even_gap(width, self._plan(self._peek)[1])))
        return self._start()

    def name_truncated(self) -> bool:
        """名字在平常的排法里放不下、被省略了：鼠标停上去不出「点击改名」，改成展开（set_peek）。"""
        return bool(self._text) and not self.editing and self.natural_tag() > self.tag_max() + 0.5

    def chip_truncated(self) -> bool:
        """新版本胶囊在平常的排法里没写整句（换成了短的说法）：鼠标放上去立刻往左展开。"""
        return bool(self.chip_says) and self._plan()[2] != self.chip_says[0]

    def tag_rect(self) -> QRectF:
        """名字胶囊（没抬起来的位置：点、悬停、提示都按它）。"""
        return QRectF(self.left.value, float(self.ROOM), self.tag.value, float(self.H))

    def chip_rect(self) -> QRectF:
        """新版本胶囊现在在哪：挤进来的时候按 _ChipIn（右头钉在最后的位置，左头往左长）；收走时右头钉住往右缩；
        平时在名字胶囊和 × 正中间（名字左边那段是 _even_gap 取整的，三段最多差 1 像素），宽是 chip_w。"""
        if not self._chip_shown:
            return QRectF()
        if self._chip_in is not None:
            fx = self._chip_in
            return QRectF(fx.lo.value, float(self.ROOM), max(0.0, fx.chip_r - fx.lo.value), float(self.H))
        w = max(0.0, self.chip_w.value)
        if self._chip_out_right is not None:
            return QRectF(self._chip_out_right - w, float(self.ROOM), w, float(self.H))
        right = self.left.value + self.tag.value
        gap = max(float(self.GAP), (self._end() - right - w) / 2.0)        # 名字和 × 正中间：名字左边那段取整了，余下的两段平分，三段最多差 1 像素
        return QRectF(right + gap, float(self.ROOM), w, float(self.H))

    def _chip_window(self, r: QRectF) -> QRectF:
        x0 = r.left() + self.CHIP_L + self.CHIP_ICON + self.CHIP_SP
        return QRectF(x0, r.top(), max(0.0, r.right() - self.CHIP_R - x0), r.height())

    def sizeHint(self) -> QSize:
        return QSize(math.ceil(self.left.target + self.tag.target), self.H + self.ROOM)

    def retarget(self, animated: bool = True) -> None:
        instant = not (animated and self._can_animate())
        w = self.target_tag()
        self.chip_w.set_target(self._plan(self._peek)[1], instant)
        fx = None if instant else self._chip_in
        if fx is not None:
            fx.aim(self)                                                    # 挤进来到一半排法变了（换了名字、停到哪上面）：朝新的最后位置接着走
        if fx is None or fx.contact is not None:                            # 还没碰上名字：名字先待着不动
            self.tag.set_target(w, instant)
            self.left.set_target(self._left_target(w), instant)
        if instant:
            self._chip_in = None
            self._say, self._say_prev, self._say_k = self._plan(self._peek)[2], None, 1.0
        self._place_edit()
        if instant:
            self.update()
        else:
            self._run()

    def _place_edit(self) -> None:
        """改名的输入框：左边跟着胶囊的弹簧走（居中时两边一起长，前面的字跟着胶囊平平地往左挪，不一下跳半个字）；右边到胶囊最后的右头。
        胶囊还在长的时候右边先多留够字的宽：输入框比字窄 QLineEdit 会自己滚一下。长到最宽了就按胶囊的宽，字在输入框里滚。"""
        if not self.edit.isVisible():
            return
        x = round(self.left.value + self.text_x(False) - 2.0)              # QLineEdit 的字离它左边 2 像素：和胶囊上画的字对齐
        right = self.left.target + self.tag.target - 4.0
        if not self.edit_capped():
            right = max(right, x + 2.0 + QFontMetricsF(self.name_font).horizontalAdvance(self.edit.shown_text()) + 4.0)
        self.edit.setGeometry(x, self.ROOM, max(8, math.ceil(right - x)), self.H)

    # ---- 互相挤 ----
    def set_peek(self, which: Optional[str]) -> None:
        """which = "name"：名字展开（Card 的悬浮计时到点、名字被省略时调）；"chip"：新版本胶囊往左挤（鼠标放上去立刻）；None：马上恢复。
        被挤的一方最多挤成正圆。都用弹簧，和换页同一种手感。"""
        if which == self._peek:
            return
        self._peek = which
        m = self.name_marquee
        if which == "name":
            m.rounds = 0                                                    # 每次停上去：等 1.2 秒再滚，滚 3 遍
            if m.phase in ("wait", "rest"):
                m.phase, m.t = "wait", 0.0
        elif m.phase in ("scroll", "pause"):
            m.interrupt()                                                   # 移开了：滚到一半的平滑滑回开头
        if which is not None:
            self._watch.start()
        elif not self._name_hover:
            self._watch.stop()
        self.retarget()

    def _end_peek(self) -> None:
        if self._peek is not None:
            self.set_peek(None)

    def _set_name_hover(self, on: bool) -> None:
        if on != self._name_hover:
            self._name_hover = on
            if on:
                self._watch.start()
            self.name_hovered.emit(on)

    @property
    def name_hovering(self) -> bool:
        return self._name_hover

    def _check_watch(self) -> None:
        """展开期间、鼠标在名字上期间：鼠标其实已经不在那上面（或这一条看不见了）就收，Qt 漏发 Leave 也不会一直挤着、一直抬着。"""
        here = QPointF(self.mapFromGlobal(QCursor.pos()))
        if self._peek is not None:
            rect = self.tag_rect() if self._peek == "name" else self.chip_rect()
            if not self.isVisible() or not rect.contains(here):
                self.set_peek(None)
        if self._name_hover and (not self.isVisible() or not self.tag_rect().contains(here)):
            self._set_name_hover(False)
        if self._peek is None and not self._name_hover:
            self._watch.stop()

    def _text_window(self) -> float:
        """胶囊里现在的字窗多宽（按正在画的那一种）。"""
        return max(0.0, self.tag.value - self.text_x(self._drawn_outlined) - self._text_r(self._drawn_outlined))

    def _name_distance(self) -> float:
        """正在画的那一行要滚多远：字宽 − 现在胶囊里的字窗宽（≤ 0 就是放得下）。"""
        return QFontMetricsF(self._font(self._drawn_outlined)).horizontalAdvance(self._drawn_text) - self._text_window()

    def _step_name(self, dt: float) -> bool:
        """名字的跑马灯：只在展开时滚；收回时滚到一半的滑回开头、淡到一半的淡完，然后停在开头等下一次。"""
        m = self.name_marquee
        if not self._drawn_text or self.editing:
            return False
        if self._peek == "name":
            return m.step(dt, self._name_distance(), enabled=not native.reduce_motion())
        if m.phase in ("scroll", "pause"):
            m.interrupt()
        if m.phase in ("back", "fade"):
            return m.step(dt, self._name_distance())
        m.t = 0.0
        return False

    def _step_text(self, dt: float) -> bool:
        """换字：正在画的那一行和要显示的不一样就淡出，淡没了换成要显示的再淡入；胶囊的底（名字胶囊 ↔ 描边标签）跟着连续变；
        小图标自己也是这样先出后进（字没变、只换图标也一样）。返回还要不要接着算。"""
        busy = False
        step = 2.0 * dt / self.TEXT_FADE_S
        if self._drawn_icon != self._icon:
            self._icon_alpha = max(0.0, self._icon_alpha - step)
            if self._icon_alpha <= 0.0:
                self._drawn_icon = self._icon
            busy = True
        elif self._icon_alpha < 1.0:
            self._icon_alpha = min(1.0, self._icon_alpha + step)
            busy = True
        if (self._drawn_text, self._drawn_outlined) != (self._text, self._outlined):
            self._drawn_alpha = max(0.0, self._drawn_alpha - step)          # 中途又换了别的字：从现在的浓淡接着淡出，不会先跳回全浓
            if self._drawn_alpha <= 0.0:
                self._drawn_text, self._drawn_outlined = self._text, self._outlined
                self.name_marquee = Marquee()
            busy = True
        elif self._drawn_alpha < 1.0:
            self._drawn_alpha = min(1.0, self._drawn_alpha + step)
            busy = True
        return busy

    def _step_say(self, dt: float) -> bool:
        """新版本胶囊换说法（_plan 挑的那句变了）：旧的淡出、新的同时淡入（FADE_S），不滚、不出省略号。返回还要不要接着算。"""
        if self.chip_says:
            want = self._plan(self._peek)[2]
            if want != self._say:
                self._say_prev, self._say, self._say_k = self._say, want, 0.0
        if self._say_k < 1.0:
            self._say_k = min(1.0, self._say_k + dt / self.FADE_S)
            if self._say_k >= 1.0:
                self._say_prev = None
            return True
        return False

    # ---- 动画 ----
    def _springs(self) -> tuple:
        return self.left, self.tag, self.chip_w

    def _run(self) -> None:
        self.card.animate()                                                 # 卡片的节拍（和卡片高度的动画同一个，跟屏幕刷新率）

    @staticmethod
    def _toward(value: float, target: float, step: float) -> float:
        return min(target, value + step) if target > value else max(target, value - step)

    def tick(self, dt: float) -> bool:
        """推进 dt 秒；返回下一帧还要不要接着算。单测直接调它（不真等）。"""
        before = self.chip_rect().width()
        for spring in self._springs():
            spring.step(dt)
        busy = not all(spring.settled for spring in self._springs())
        busy = self._step_text(dt) or busy
        busy = self._step_name(dt) or busy
        vis_to = 1.0 if self.name_shown else 0.0
        if self._name_vis != vis_to:
            self._name_vis = self._toward(self._name_vis, vis_to, dt / self.TEXT_FADE_S)
            busy = True
        if self.lead is not None and self.lead.mix != self._lead_to:
            self.lead.mix = self._toward(self.lead.mix, self._lead_to, dt / self.TEXT_FADE_S)
            self.lead.update()
            busy = True
        if self._flow is not None:
            busy = self._step_flow(dt) or busy
        if self.editing:
            self._place_edit()                                              # 输入框跟着胶囊的弹簧走
        if self._chip_in is not None:
            if not self._chip_in.step(dt, self):
                self._chip_in = None
                self.chip_w.set_target(self.chip_w.target, instant=True)    # 交给平常的排法：这时名字、胶囊正好在最后的位置
            busy = True
        target = 1.0 if self.chip_text else 0.0
        if self._chip_alpha != target:
            self._chip_alpha = self._toward(self._chip_alpha, target, dt / self.FADE_S)
            if self._chip_alpha <= 0.0 and not self.chip_text:
                self._chip_shown, self._shown_says, self._chip_out_right = "", (), None
                self._say = self._say_prev = None
            busy = True
        busy = self._step_say(dt) or busy
        if self.chip_text:
            r = self.chip_rect()
            if abs(r.width() - before) > 0.01:
                self.marquee.interrupt()                                    # 字窗变了：滚到一半的平滑滑回开头，停稳再等 1.2 秒
            room = self._chip_window(QRectF(r.left(), r.top(), self.chip_w.target, r.height())).width()
            distance = QFontMetricsF(self.chip_font).horizontalAdvance(self._say or "") - room   # 只有整句比留给它的还长（展开着）才大于 0、才滚
            busy = self.marquee.step(dt, distance, enabled=not native.reduce_motion()) or busy
        self.update()
        return busy

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._shown = True
        self.retarget(animated=False)                                       # 打开时直接到位，不从小长大
        self.finish_now()
        if self.chip_text:
            self._run()

    def hideEvent(self, event) -> None:
        self.marquee, self.name_marquee = Marquee(), Marquee()              # 下次打开从头来
        self._peek = None
        self._name_press = False
        self._set_name_hover(False)
        self._watch.stop()
        self.retarget(animated=False)
        self.finish_now()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._flow_layer is not None:
            self._flow_layer.place()
        self.retarget(animated=event.oldSize().width() > 0)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._flow_layer is not None:
            self._flow_layer.place()

    # ---- 鼠标 ----
    def _renamable(self) -> bool:
        return self.click_action == "rename" and self.card._rename is not None and not self.editing

    def _clickable(self) -> bool:
        """点名字胶囊有反应（改名、打开）：鼠标放上去是手指。"""
        return not self.editing and (self._renamable() or self.click_action == "open")

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        on_chip = bool(self.chip_text) and self.chip_rect().contains(pos)
        if on_chip != self._chip_hover:
            self._chip_hover = on_chip
            if on_chip:
                self.marquee.replay()                                       # 鼠标移上去：再滚 3 遍
                self._run()
            self.update()
        if on_chip and self._peek != "chip" and self.chip_truncated():
            self.set_peek("chip")                                           # 被压窄的新版本胶囊：鼠标一放上去就往左挤（不等）
        elif (self._peek == "chip" and not on_chip) or (self._peek == "name" and not self.tag_rect().contains(pos)):
            self.set_peek(None)                                             # 移开马上恢复
        on_tag = self.tag_rect().contains(pos) and not self.editing
        self._set_name_hover(on_tag)
        self.setCursor(Qt.PointingHandCursor if (on_chip or (on_tag and self._clickable())) else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._chip_hover:
            self._chip_hover = False
            self.update()
        self._end_peek()
        self._set_name_hover(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        if event.button() == Qt.LeftButton:
            if self.chip_text and self.chip_rect().contains(pos):
                self.chip_clicked.emit()
                event.accept()
                return
            if self.tag_rect().contains(pos) and self._clickable():
                if self._renamable():
                    self.card.start_rename()                                # 改名：按下就开（输入框就长在按的地方）；这一下不算拖卡片
                else:
                    self._name_press = True                                 # 打开：松开时还在胶囊上才算（和点狗一样，按着移开就不算）
                event.accept()
                return
        event.ignore()                                                      # 空白处、左边的 app 图案：交给卡片（拖卡片）

    def mouseReleaseEvent(self, event) -> None:
        pressed, self._name_press = self._name_press, False
        if pressed and event.button() == Qt.LeftButton and self.click_action == "open" and self.tag_rect().contains(event.position()):
            self.name_clicked.emit()
        if pressed:
            event.accept()
        else:
            event.ignore()

    # ---- app 图标在圆和胶囊之间流过去（set_look，_Flow） ----
    @property
    def flow(self) -> float:
        """那一滴走到哪（0 圆心 … 1 胶囊左头里；会回弹，可能稍微出界）。没在流：app 图标在哪就是哪。"""
        if self._flow is None:
            return 1.0 if self._home(self.lead_mode, self._icon) == "capsule" else 0.0
        return self._flow.progress(self)

    def _step_flow(self, dt: float) -> bool:
        if self._flow.step(dt, self):
            if self._flow_layer is not None:
                self._flow_layer.update()
            return True
        self._end_flow()                                                    # 走完了：圆、胶囊自己画，和最后一帧一模一样
        return False

    def _paint_flow(self, p: QPainter) -> None:
        if self._flow is not None:
            self._flow.paint(p, self)

    def _paint_content(self, p: QPainter, key: Optional[str], text: str, outlined: bool, x0: float, w: float, cy: float) -> None:
        """名字胶囊里的小图标（key 为 None 不画）和字，按左边 x0、宽 w、竖直中心 cy 的胶囊排（流的时候 _Flow 每层各画一遍再糊）。"""
        g = max(0.0, min(1.0, (w - self.H) / 24.0))
        mx = x0 + (self.H - self.MARK_W) / 2 * (1.0 - g) + self.TAG_L * g
        if key is not None:
            marks.draw(p, key, QPointF(mx + self.MARK_W / 2, cy), QColor(sticker.INK))
        if text:
            tx = self.text_x(outlined)
            area = QRectF(x0 + tx, cy - self.H / 2.0, max(0.0, w - tx - self._text_r(outlined)), float(self.H))
            fit = max(0.0, min(1.0, (area.width() - 10.0) / 14.0))
            if fit > 0.0:
                draw_strip(p, area, text, self._font(outlined), QColor(sticker.INK), 0.0, fit)

    # ---- 画 ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._flow is None and self._name_vis > 0.0:                    # 正在流：名字胶囊连字整块画在上面一层（_Flow）；收没了不画
            x0, w = self.left.value, self.tag.value
            top = self.ROOM - self._lift                                         # 抬起来的只有名字胶囊
            vis = _smooth(self._name_vis)                                        # 关于页没有名字胶囊：收起时变淡、稍微缩小（set_name_shown）
            p.save()
            if vis < 1.0:
                p.setOpacity(vis)
                cx, cy, kv = x0 + w / 2.0, top + self.H / 2.0, 0.86 + 0.14 * vis
                p.translate(cx, cy)
                p.scale(kv, kv)
                p.translate(-cx, -cy)
            drawn, squish = self._chip_in.name_box(self) if self._chip_in is not None else (w, 0.0)
            capsule = QPainterPath()
            if squish > 0.0:                                                     # 新版本胶囊正挤进来：右头压扁、稍微变高（_ChipIn）
                hh = self.H / 2.0 * (1.0 + 0.10 * squish)
                rect = QRectF(x0, top + self.H / 2.0 - hh, drawn, 2.0 * hh)
                capsule = _pill(rect, hh, hh * (1.0 - 0.55 * squish))
            else:
                rect = QRectF(x0, top, w, float(self.H))
                capsule.addRoundedRect(rect, self.H / 2, self.H / 2)
            p.fillPath(capsule, QColor(sticker.PAPER_2))                         # 米白底、黑描边、黑字（和「添加同桌」一个颜色）
            box = rect.adjusted(1.0, 1.0, -1.0, -1.0)
            p.save()
            p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
            p.setBrush(Qt.NoBrush)
            if squish > 0.0:
                p.drawPath(_pill(box, box.height() / 2, box.height() / 2 * (1.0 - 0.55 * squish)))
            else:
                p.drawRoundedRect(box, box.height() / 2, box.height() / 2)
            p.restore()
            alpha = self._icon_alpha
            if alpha > 0.0:                                                     # 小图标：胶囊是正圆时在正中，长成胶囊的路上滑到左边（icon_center）
                p.setOpacity(alpha * vis)
                marks.draw(p, self._drawn_icon, self.icon_center(), QColor(sticker.INK))
                p.setOpacity(vis)
            if not self.editing and self._drawn_text:
                outlined = self._drawn_outlined
                tx = self.text_x(outlined)
                area = QRectF(x0 + tx, top, max(0.0, w - tx - self._text_r(outlined)), float(self.H))
                fit = max(0.0, min(1.0, (area.width() - 10.0) / 14.0))         # 挤成正圆的路上字先淡掉（字窗太窄时不画半个省略号）
                if fit > 0.0:
                    p.save()
                    p.setClipPath(capsule)
                    color = QColor(sticker.INK)
                    draw_strip(p, area, self._drawn_text, self._font(outlined), color, self.name_marquee.offset,
                               self._drawn_alpha * fit * self.name_marquee.alpha)
                    p.restore()
            p.restore()
        if self._chip_shown and self._chip_alpha > 0.0 and self.chip_rect().width() > 0.5:
            r = self.chip_rect()
            p.save()
            p.setOpacity(self._chip_alpha)
            if r.width() < self.H:                                          # 刚长出来 / 快缩没了：一个从小变大的圆（连图标一起缩放），靠右：从 × 那边冒出来、往右缩回去
                s = r.width() / self.H
                p.translate(r.right() - self.H * s, r.top() + self.H / 2 * (1.0 - s))
                p.scale(s, s)
                r = QRectF(0.0, 0.0, float(self.H), float(self.H))
            box = r.adjusted(1.0, 1.0, -1.0, -1.0)
            shape = QPainterPath()
            shape.addRoundedRect(box, box.height() / 2, box.height() / 2)
            p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
            p.setBrush(QColor(sticker.PAPER_3 if self._chip_hover else sticker.PAPER_2))
            p.drawPath(shape)
            ink = QColor(sticker.INK)
            g = max(0.0, min(1.0, (r.width() - self.H) / 24.0))             # 正圆 → 胶囊：下载图标从正中滑到左边（和名字胶囊的骨头一样）
            cx, cy = r.left() + self.H / 2 * (1.0 - g) + (self.CHIP_L + self.CHIP_ICON / 2) * g, r.center().y()
            p.setPen(QPen(ink, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))       # 下载图标：箭头 + 底线
            p.drawLine(QPointF(cx, cy - 6.0), QPointF(cx, cy + 2.0))
            p.drawPolyline([QPointF(cx - 3.5, cy - 1.5), QPointF(cx, cy + 2.0), QPointF(cx + 3.5, cy - 1.5)])
            p.drawLine(QPointF(cx - 5.0, cy + 5.5), QPointF(cx + 5.0, cy + 5.5))
            fit = max(0.0, min(1.0, (self._chip_window(r).width() - 10.0) / 14.0))   # 挤成正圆的路上字先淡掉
            if fit > 0.0:
                p.setClipPath(shape, Qt.IntersectClip)
                for say, a in ((self._say_prev, 1.0 - self._say_k), (self._say, self._say_k)):   # 换说法：旧的淡出、新的淡入
                    if not say or a <= 0.0:
                        continue
                    need = self.chip_natural(say)
                    scroll = bool(self.chip_says) and need > self.chip_w.target + 0.5    # 整句比留给它的还长（展开着）：在胶囊里滚
                    # 字窗按这句放得下的宽排（胶囊还在长、在缩时字不跟着换省略号，被胶囊的边剪掉）；要滚的按留给它的宽
                    win = self._chip_window(QRectF(r.left(), r.top(), self.chip_w.target if scroll else max(r.width(), need), r.height()))
                    draw_strip(p, win, say, self.chip_font, ink, self.marquee.offset if scroll else 0.0,
                               a * fit * (self.marquee.alpha if scroll else 1.0))
            p.restore()


class Card(QWidget):
    def __init__(self, title: str, accent: Optional[str] = None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)   # 投影自己画，不要系统的
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setWindowTitle(title)
        self.setFocusPolicy(Qt.StrongFocus)      # 卡片自己拿焦点：Esc 能关，打开时焦点不落进输入框
        self.setAttribute(Qt.WA_ShowWithoutActivating)   # 打开时不激活程序（激活会让 macOS 跳桌面）；点它也不激活（showEvent 里 set_no_activate）
        native.apply(self)
        self.theme = sticker.theme(accent)
        self.setStyleSheet(sticker.stylesheet(self.theme))
        self._tips: dict[QWidget, str] = {}      # 哪个控件（整行）悬浮时显示什么说明（eventFilter 在建标题行时就会被调到，先建好）
        self._tip_target: Optional[QWidget] = None   # 鼠标现在在哪一行里（计时中）
        self._tip_shown: Optional[QWidget] = None    # 提示现在是给哪一行显示的
        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.setInterval(TIP_DELAY_MS)
        self._tip_timer.timeout.connect(self._show_tip)
        self._tip_watch = QTimer(self)             # 提示显示期间每 50 毫秒看一眼鼠标真实位置，不在那一行里就收（快速甩出卡片时靠 Leave 会漏）
        self._tip_watch.setInterval(50)
        self._tip_watch.timeout.connect(self._check_tip)
        self._rename: Optional[Callable[[str], None]] = None
        self._rename_finishing = False
        self._rename_pending = False
        self._long_name = QTimer(self)             # 「名字太长啦！」停 2 秒自己收
        self._long_name.setSingleShot(True)
        self._long_name.setInterval(2000)
        self._long_name.timeout.connect(lambda: self._unwarn_long_name())
        self._tag: Optional[QWidget] = None
        self._accent_final = self.theme            # 强调色要淡到的那一套（set_accent）；淡的路上 self.theme 是中间色
        self._focus_hooked = False
        self._outer = QHBoxLayout(self)          # 主叶（标题 + 内容）；侧叶不进布局，attach_side 后手动摆
        self._outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        self._outer.setSpacing(0)
        self._main = QWidget()
        column = QVBoxLayout(self._main)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._outer.addWidget(self._main, 0, Qt.AlignTop)
        head = QHBoxLayout()                     # 标题行（顶部栏）：不跟着内容滚
        head.setContentsMargins(PAD, PAD - TitleBar.ROOM, PAD, 0)   # 胶囊、×、左边的圆的顶离卡片上边 = 左边距；
                                                                    # 顶部栏比它们高出 ROOM，多出来的在上面，给抬起来的名字胶囊留地方，这一行还是 42 高
        self._tag = TitleBar(self)               # 标题：名字胶囊 + 小图标（写同桌名字时是它的物种图标，狗 = 骨头；别的页是 app 图标；见 TitleBar）
        self._title_label = self._tag            # 胶囊上的字：text() / setText()
        self._title_edit = self._tag.edit        # 点胶囊改名（set_renamable 打开）：输入框就长在胶囊里
        self._title_edit.editingFinished.connect(self._commit_rename)
        self._title_edit.textEdited.connect(self._limit_name)
        self._title_edit.preeditEdited.connect(self._preedit_name)
        self._title_edit.compositionFinished.connect(self._finish_pending_rename)
        self._title_edit.hidden.connect(self._rename_hidden)
        self._title_edit.installEventFilter(self)
        self._tag.setText(title)
        head.addWidget(self._tag, 1)
        head.setSpacing(0)                       # 标题行直接挨着 ×：和 × 之间空多少由它自己留（GAP），新版本胶囊才能离 × 和离名字胶囊一样远、不被裁
        close = IconButton("close", "Close", size=26)   # 右上角关闭：和左上角的圆一样的 26 像素描边圆
        close.clicked.connect(lambda _=False: self.dismiss())
        head.addWidget(close, 0, Qt.AlignBottom)  # 顶和胶囊齐平（顶部栏多出来的 ROOM 在上面）。× 故意和顶部栏并排、不放进去：
                                                 # TitleBar._close_box 按它排新版本胶囊和居中，悬浮说明（StickerTip._beside）放到它前面为止
        self._close = close
        column.addLayout(head)
        self._head = head
        self.scroll = QScrollArea()              # 内容放这里；放得下就没有滚动条
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)    # 子类照旧往 self.body 里加行
        self.body.setContentsMargins(PAD, 10, PAD, PAD)
        self.body.setSpacing(10)
        self.scroll.setWidget(self.content)
        self.scroll.viewport().setAutoFillBackground(False)   # 透出卡片自己画的底色
        self.content.setAutoFillBackground(False)             # setWidget 会把它改成 True，放在后面
        column.addWidget(self.scroll, 1)
        self._drag: Optional[QPoint] = None
        self.dock = SideDock(self)               # 侧边面板（表盘）：不进布局，attach_side 后由它摆
        self.clock = FrameClock(self, self._tick)   # 卡片的动画节拍：标题行、高度过渡、开关、展开的行、打开 / 关上都挂这一个，跟着狗的每一帧走
        self._animators: set = set()             # 卡片里正在动的小东西（开关、Collapse、Fader……），每帧 tick
        self._still = False                      # 打开那一下对齐设置：变化直接到位（still）
        self._pop_t: Optional[float] = None      # 打开：淡入 + 上浮走了多久
        self._rising = False
        self._close_t: Optional[float] = None    # 关上：淡出走了多久
        self._swap = None                        # 换页的淡入淡出（swap_content）
        self._in_place = False                   # 下一次显示原地出现、不淡入上浮（show_in_place：换语言 / 外观时重建的卡片）
        self._tail = False                       # 内容最后有没有一段弹性空白（_ensure_tail）
        self._leaf = Spring(0.0, 0.3)            # 换页 / 子行展开时卡片画出来的高度（主叶，不含阴影边距）
        self._leaf_anim = False
        self._leaf_final = 0                     # 过渡走完后窗口的高度
        self._main_final = 0                     # 过渡走完后主叶的高度

    def set_title(self, text: str, animated: bool = True, outlined: bool = False) -> None:
        """改标题：胶囊上的字和窗口标题一起换（改狗的名字时用；名字可以为空，胶囊只剩骨头）。显示着就先淡出旧字、再淡入新字。
        outlined：标题不是名字（比如设置主页面停在「+」上的「添加同桌」），字不加粗。"""
        self._tag.setText(text, animated, outlined)
        self.setWindowTitle(text or config.APP_NAME)

    # ---- 点标签改名（Settings 没有名字行了，标题胶囊就是名字） ----
    def set_renamable(self, callback: Callable[[str], None], tip: str) -> None:
        """点标题胶囊就地改名：胶囊里换成输入框，回车或点别处生效（callback 收新名字），Esc 取消。
        之后点胶囊做什么可以用 set_title_click 换（设置卡片只有详情页能改名）。"""
        self._rename = callback
        self.tip_for(self._tag, tip)
        self._tag.click_action = "rename"

    def set_title_click(self, action: Optional[str]) -> None:
        """点标题胶囊做什么（子类换页时设）：'rename' 就地改名（要先 set_renamable，只有这时浮「点击改名」）、'open' 发 TitleBar.name_clicked
        （设置主页面：进正中那只的详情页）、None 不理（按下照旧拖卡片，比如标题是页名的时候）。"""
        if action != "rename":
            self.end_rename_now()
        self._tag.click_action = action

    @property
    def renaming(self) -> bool:
        return self._tag.editing

    def end_rename_now(self) -> None:
        """正在改名就马上收尾（照回车算）：名字胶囊要挪走、要换成别的名字之前调。"""
        if self.renaming:
            self._commit_rename()
        if self.renaming:                            # 输入法还没交字：不等了
            self._end_rename()

    def start_rename(self) -> None:
        if self._rename is None or self._tag.click_action != "rename" or self.renaming:
            return
        self._tip_timer.stop()                       # 输入框开着时不出「点击改名」
        self._tip_target = None
        self._hide_tip()
        self._tag.set_editing(True, self._tag.text())
        self.ensure_typing()
        self._title_edit.setFocus()
        self._title_edit.selectAll()
        self._rename_pending = False
        sounds.rename_feedback("enter")

    def _end_rename(self) -> None:
        self._rename_finishing = True
        self._rename_pending = False
        try:
            self._unwarn_long_name()
            self._tag.set_editing(False)
            self.setFocus()
        finally:
            self._rename_finishing = False

    def _rename_hidden(self) -> None:
        self._rename_pending = False
        sounds.stop_rename()

    def _preedit_name(self, _text: str) -> None:
        if self.renaming and not self._rename_finishing:
            sounds.rename_feedback("type")

    def _finish_pending_rename(self) -> None:
        if self._rename_pending:
            self._commit_rename()

    def _limit_name(self, text: str) -> None:
        """名字最多 NAME_MAX（32）个看得见的字，一个表情算一个。再打就不进去，名字胶囊下面冒个气泡「名字太长啦！」，
        停 2 秒自己收，接着打重新计时。"""
        if not self.renaming or self._rename_finishing:
            return
        if grapheme_count(text) > NAME_MAX:
            cursor = self._title_edit.cursorPosition()
            clipped = clip_graphemes(text, NAME_MAX)
            self._title_edit.setText(clipped)
            self._title_edit.setCursorPosition(min(cursor, len(clipped)))
            self._warn_long_name()
            sounds.rename_feedback("limit")
        elif not self._title_edit.handling_preedit:
            sounds.rename_feedback("type")

    def _warn_long_name(self) -> None:
        self._hide_tip()                             # 别的行的说明正开着：先收，它的看门计时器不然会把这个气泡也收了
        sticker_tip().show_for(self._tag, tr("Name is too long!"), spot=self._tip_spot(self._tag))   # 放在名字胶囊下面，尾巴朝上指着它
        self._long_name.start()

    def _unwarn_long_name(self) -> None:
        self._long_name.stop()
        tip = sticker_tip()
        if tip.isVisible() and tip.text == tr("Name is too long!"):
            hide_tip()

    def _commit_rename(self) -> None:
        if not self.renaming or self._rename_finishing:  # 回车和失焦各来一次 editingFinished，只算第一次
            return
        if self._title_edit.composing:
            self._rename_pending = True              # 有的输入法在失焦之后才交付最终选字
            return
        text = clip_graphemes(self._title_edit.text().strip(), NAME_MAX)
        old = self._tag.text()
        self._tag.setText(text, animated=False)       # 输入框收起来时胶囊上直接是新名字（不先露一下旧名字再淡过去）
        self._end_rename()
        if self._rename is not None and text != old:
            sounds.rename_feedback("done")          # 回调可能销毁卡片，先发一次完成声
            self._rename(text)                       # 可以是空的（名字可以为空，胶囊只剩骨头）

    def set_accent(self, color: str, animated: bool = True) -> None:
        """强调色跟毛色换（look.apply_accent 调）：卡片显示着就从现在的颜色淡过去（换同桌时按钮、开关和狗一样淡过去，ACCENT_S），
        没显示、减少动态效果时一下换好。样式表只在开始时按新颜色套一次（里面只有输入框选中的底色用强调色；每帧重套太费），
        每帧只改各控件手里的颜色（_show_accent）、重画用到它的那几个。"""
        final = sticker.theme(color)
        shown = QColor(self.theme.accent)
        self._accent_final = final
        css = sticker.stylesheet(final)
        if css != self.styleSheet():                     # 一样的就不重套（重套要把整张卡片的控件重新排一遍样式）
            self.setStyleSheet(css)
        for a in [a for a in self._animators if isinstance(a, _AccentFade)]:
            a.done = True
            self._animators.discard(a)
        if animated and shown != QColor(final.accent):
            fade = _AccentFade(self, shown, QColor(final.accent), QColor(self.theme.accent_text), QColor(final.accent_text))
            if self.run_animator(fade):
                fade.tick(0.0)
                return
        self._show_accent(QColor(final.accent), QColor(final.accent_text))

    def _input_accent(self, accent: QColor, text: QColor) -> None:
        """输入框选中文字的底色、字色 = 强调色（样式表里不放强调色，sticker.stylesheet）：设在卡片的调色板上，里面的输入框（以后新建的也是）跟着它。
        淡到头才设（选中文字的时候少），一样的不重设。"""
        pal = self.palette()
        if pal.color(QPalette.Highlight) == accent and pal.color(QPalette.HighlightedText) == text:
            return
        pal = QPalette(pal)
        pal.setColor(QPalette.Highlight, accent)
        pal.setColor(QPalette.HighlightedText, text)
        self.setPalette(pal)

    def _accent_widgets(self) -> tuple[list, list]:
        """手里拿着强调色的控件（开关、长按按钮、滑杆、主按钮、图标按钮、大小数字……，有 accent 的），和画的时候读卡片 theme 的
        （主按钮、选中的胶囊、刻度尺、表盘）。"""
        own = [w for w in self.findChildren(QWidget) if isinstance(getattr(w, "accent", None), (QColor, str))]
        reads = [w for w in self.findChildren(QWidget)
                 if (isinstance(w, MotionButton) and (w.isCheckable() or w.property("kind") == "primary")) or getattr(w, "READS_ACCENT", False)]
        return own, reads

    def _show_accent(self, accent: QColor, text: QColor, widgets: Optional[tuple[list, list]] = None) -> None:
        """这一刻的强调色：卡片的 theme（主按钮、选中的胶囊、刻度尺画的时候读它）和各控件手里的那一份都换成它，看得见的重画。"""
        final = self._accent_final
        done = accent.name() == QColor(final.accent).name() and text.name() == QColor(final.accent_text).name()
        self.theme = final if done else dataclasses.replace(final, accent=accent.name(), accent_text=text.name())   # 到了就用原样的那一套
        if done:
            self._input_accent(accent, text)
        own, reads = widgets if widgets is not None else self._accent_widgets()
        for w in own:
            try:
                w.accent = QColor(accent) if isinstance(w.accent, QColor) else accent.name()
                if w.isVisible():
                    w.update()
            except RuntimeError:                         # 控件已经删了（换页时重建的行）
                pass
        for w in reads:
            try:
                if w.isVisible():
                    w.update()
            except RuntimeError:
                pass                                     # 卡片自己的底不用强调色：不整张重画（那样每帧连滑动条的贴纸一起重画）

    # ---- 布局小工具 ----
    def row(self, text: str, widget: QWidget, hint: str = "") -> QWidget:
        """一行：左边标题，右边控件。hint 不再占一行灰字，鼠标在这一行停 0.3 秒才浮出来（tip_for）。"""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(text), 1)
        lay.addWidget(widget, 0, Qt.AlignVCenter)
        if hint:
            self.tip_for(row, hint)
        return row

    def tip_for(self, widget: QWidget, text: str) -> None:
        """鼠标在 widget 这一行的**文字**上停下不动 0.5 秒，文字右边浮出说明（放不下才在下面，见 StickerTip）；动一下计时重来；
        移到这一行的开关 / 按钮上、离开这一行、按下鼠标都收（可悬停的区域不要按钮和按钮旁边，要点开关时别弹说明）。
        本身就是按钮的（二维码、两色圆点、动作控制的按钮）整个就是触发区。
        行里的子控件也要盯着：没按键时的鼠标移动只发给开了 mouseTracking 的那个控件。"""
        self._tips[widget] = text
        for w in [widget] + widget.findChildren(QWidget):
            w.setMouseTracking(True)
            w.installEventFilter(self)

    def _tip_owner(self, obj) -> Optional[QWidget]:
        w = obj if isinstance(obj, QWidget) else None
        while w is not None and w not in self._tips:
            w = w.parentWidget()
        return w

    def _tip_zone(self, owner: QWidget) -> QRect:
        """这一行里能触发说明的范围（屏幕坐标）：Card.row 的行只有标题文字那一段（到文字右边 6 像素，整行高）；
        标题胶囊只算胶囊本身（不算旁边的圆、新版本胶囊和空白）；本身就是按钮的，整个控件。"""
        if owner is self._tag:
            return self._tip_spot(owner)
        beside = self._tip_beside(owner)
        rect = QRect(owner.mapToGlobal(QPoint(0, 0)), owner.size())
        if beside is not owner:
            text_w = min(beside.width(), beside.sizeHint().width())
            right = beside.mapToGlobal(QPoint(text_w + 6, 0)).x()
            rect.setRight(min(rect.right(), right))
        return rect

    def _tip_hover(self, owner: QWidget, pos: QPoint) -> None:
        """鼠标在这一行里动了：在文字上就（重新）计时，不在文字上就停表、已经出来的收掉。"""
        if self._tip_zone(owner).contains(pos):
            if self._tip_shown is not owner:
                self._tip_target = owner
                self._tip_timer.start()              # 还在动：重新计时
        else:
            self._tip_timer.stop()
            if self._tip_target is owner:
                self._tip_target = None
            if self._tip_shown is owner:
                self._hide_tip()

    def eventFilter(self, obj, event) -> bool:
        owner = self._tip_owner(obj) if self._tips else None
        if owner is not None:
            t = event.type()
            if t == QEvent.Enter:
                self._tip_hover(owner, QCursor.pos())
            elif t == QEvent.MouseMove:
                self._tip_hover(owner, event.globalPosition().toPoint())
            elif (t in (QEvent.Leave, QEvent.Hide) and obj is owner) or t == QEvent.MouseButtonPress:
                self._tip_timer.stop()
                if self._tip_target is owner:
                    self._tip_target = None
                if self._tip_shown is owner:
                    self._hide_tip()
        if event.type() == QEvent.MouseButtonPress and isinstance(obj, QLineEdit):
            self.ensure_typing()
        if (obj is self._title_edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape
                and not self._title_edit.composing):
            self._end_rename()                       # Esc：不改
            return True
        return super().eventFilter(obj, event)

    def _show_tip(self, force: bool = False) -> None:
        """计时器到点：鼠标还在那一行的文字上才显示（force 给单测和出图用，不看鼠标）。
        标题胶囊：名字被省略了就展开它（set_peek，每一页都这样，能不能改名都一样）；能改名才浮「点击改名」；输入框开着时都不出。"""
        if self._tip_target is self._tag:
            if self.renaming:
                return
            if self._tag.name_truncated():
                if force or self._tip_zone(self._tag).contains(QCursor.pos()):
                    self._tag.set_peek("name")       # 名字胶囊展开、把新版本胶囊挤成正圆，还放不下就滚
                return
            if self._tag.click_action != "rename" or self._rename is None:
                return                               # 点了不改名（主页面点了进详情页、别的页标题是页名）：不提示「点击改名」
        if not force and self._tip_target is not None and not self._tip_zone(self._tip_target).contains(QCursor.pos()):
            self._tip_target = None
            return
        if self._tip_target is not None and self._tip_target.isVisible() and self.isVisible():
            self._tip_shown = self._tip_target
            sticker_tip().show_for(self._tip_target, self._tips[self._tip_target], beside=self._tip_beside(self._tip_target),
                                   spot=self._tip_spot(self._tip_target))
            self._tip_watch.start()

    def _tip_spot(self, owner: QWidget) -> Optional[QRect]:
        """说明要指着的那一块（屏幕坐标）：标题胶囊就是胶囊本身（顶部栏比胶囊高、胶囊也不一定靠左）；别的行 None，整行。"""
        if owner is not self._tag:
            return None
        r = self._tag.tag_rect()
        return QRect(owner.mapToGlobal(QPoint(math.floor(r.left()), math.floor(r.top()))), QSize(math.ceil(r.width()), math.ceil(r.height())))

    def _tip_beside(self, owner: QWidget) -> QWidget:
        """提示放在谁的右边：Card.row 的行是它的标题文字；标题胶囊是整个胶囊（"点击改名"浮在名字旁边；旁边有新版本胶囊时放在下面）；
        别的（按钮、二维码）是控件本身。"""
        if owner is self._tag:
            return None if self._tag.chip_text else owner
        for child in owner.children():
            if isinstance(child, QLabel) and child.isVisible():
                return child
        return owner

    def _hide_tip(self) -> None:
        self._tip_watch.stop()
        self._tip_shown = None
        hide_tip()

    def _check_tip(self) -> None:
        """提示显示期间：鼠标不在那一行的范围里（或者那一行、卡片已经看不见了）就收。靠 Leave 事件不够：鼠标一下子甩出窗口时 Qt 的进出记账会漏。"""
        owner = self._tip_shown
        if owner is None or not owner.isVisible() or not self.isVisible():
            self._hide_tip()
            return
        if not self._tip_zone(owner).contains(QCursor.pos()):   # 出了文字那一段（移到开关上、甩出卡片）就收
            self._tip_target = None
            self._hide_tip()

    def separator(self) -> None:
        self.body.addWidget(hairline(self.theme))

    def hairline_widget(self) -> QFrame:
        """给卡片里自己排版的页用的分隔线。"""
        return hairline(self.theme)

    def header_row(self, text: str) -> QHBoxLayout:
        """分组标题：前面一根小骨头。"""
        lay = QHBoxLayout()
        lay.setSpacing(6)
        icon = QLabel()
        icon.setFixedSize(16, 8)
        icon.setPixmap(bone_pixmap(16, self.devicePixelRatioF()))
        label = QLabel(text)
        label.setProperty("muted", True)
        lay.addWidget(icon, 0, Qt.AlignVCenter)
        lay.addWidget(label)
        lay.addStretch(1)
        return lay

    def header(self, text: str) -> None:
        self.body.addLayout(self.header_row(text))

    # ---- 高度 ----
    def content_height(self) -> int:
        """按现在的宽度排版，整张卡（含标题行和阴影边距）要多高。换行的说明文字用 heightForWidth 量。"""
        inner = max(1, (self.dock.main_w if self.dock.active else self.width() - 2 * SHADOW))   # 侧边面板开着时窗口更宽，按主叶自己的宽量，不然说明文字少换行、底部被裁
        for w in self.content.findChildren(QWidget):
            if w.layout() is not None or isinstance(w, Collapse):
                w.updateGeometry()    # 容器里刚 hide / show 过一段（动作列表）：外层布局缓存着容器的旧尺寸，不作废量出来的还是收起前的高度
        lay = self.body
        lay.activate()
        body_h = lay.totalHeightForWidth(inner) if lay.hasHeightForWidth() else lay.totalSizeHint().height()
        pending = sum(c.pending() for c in self.content.findChildren(Collapse))   # 正在展开 / 收起的行：按走完以后的高度量
        return 2 * SHADOW + self._head.totalSizeHint().height() + body_h + round(pending)

    def _ensure_tail(self) -> None:
        """内容最后放一段弹性空白：高度过渡中主叶比内容高（收起的行还在慢慢收），多出来的地方给它，别把各行拉开。"""
        if not self._tail:
            self.body.addStretch(1)
            self._tail = True

    def fit_height(self, available: Optional[int] = None) -> int:
        """高度 = 内容要的高度；超过屏幕可用高度就封顶，多出来的在卡片里滚动。available 不给就看卡片所在的屏幕。返回窗口最后的高度。
        高度过渡中（animate_height）：只改过渡的终点，窗口不缩到比画出来的还矮。"""
        self._ensure_tail()
        if available is None:
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            available = screen.availableGeometry().height() if screen is not None else 10_000
        cap = available + 2 * SHADOW - 2 * EDGE
        need = self.content_height()
        fits = need <= cap
        # 放得下就彻底不要滚动条：占宽度的滚动条（接了鼠标的 Mac、测试平台）会把文字挤窄、变高，
        # 于是"有滚动条"自己也成立，卡在那里不消失
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff if fits else Qt.ScrollBarAsNeeded)
        main_h = max(MIN_HEIGHT, need if fits else cap)
        self._main_final = main_h - 2 * SHADOW               # 主叶自己的高度；窗口可能更高（侧叶更高、或比主叶顶高出去时）
        if not (self._leaf_anim and self._main.height() > self._main_final):
            self._main.setFixedHeight(self._main_final)      # 过渡中先不缩：中间每一帧的内容都要放得下，走完（finish_height）再缩
        if self.dock.active:
            self._outer.activate()
            self.dock.place()
            final = self.dock.window_height(main_h)
        else:
            final = main_h
        if self._leaf_anim:
            self._leaf_final = final
            self._leaf.set_target(float(main_h - 2 * SHADOW))
            self._apply_height()                             # 先裁好再改窗口大小：改大小那一下画出来的要和上一帧一样
            reserve = final
            if self.dock.active:
                growth = math.ceil(max(0.0, self._main_final - self._leaf.value))
                reserve = self.dock.window_height(main_h, growth)  # 侧叶跟着上方展开的行往下走：一次留足，中间不反复改窗口大小
            self.setFixedHeight(max(reserve, self.height()))
        else:
            self.setFixedHeight(final)
        return final

    # ---- 侧边面板（表盘，widget/sidepane.py 的 SideDock 管） ----
    def attach_side(self, pane: QWidget) -> None:
        """挂一个侧边面板（表盘 widget/dial.py）。平时藏着，open_side 时窗口先撑出它的地方，再从贴着卡片的那一点放大出来。永远在右边。"""
        self.dock.attach(pane)

    def side_anchor_y(self) -> float:
        """面板对着窗口里哪个高度弹出来；子类覆盖（Settings 用姿势行的 › 那一行）。"""
        return SHADOW + self.dock.dy + self._main.height() / 2

    def side_room(self) -> Optional[float]:
        """面板的中心到主叶上下边，近的那边还有多少地方；None 是不限（面板没对着某一行）。子类覆盖。"""
        return None

    def side_extent(self) -> tuple[int, int]:
        """侧边面板要多少地方：(往右伸出主叶多少, 高)。"""
        return self.dock.extent()

    @property
    def side_open(self) -> bool:
        return self.dock.active

    def toggle_side(self, animated: bool = True) -> bool:
        """弹出 / 收回；返回这次是不是在弹出。"""
        return self.dock.toggle(animated)

    def open_side(self, animated: bool = True) -> None:
        self.dock.open(animated)

    def close_side(self, animated: bool = True) -> None:
        self.dock.close(animated)

    # ---- 显示 ----
    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)        # 跟狗一样，所有普通桌面上都看得见
        native.set_no_activate(self)             # 点卡片不把同桌切到前台（从别的 App 过来第一下点卡片卡半秒，就是切前台在等；和狗、球一样）
        if not self._focus_hooked:
            self._focus_hooked = True
            QApplication.instance().focusChanged.connect(self._focus_changed)
            for edit in self.findChildren(QLineEdit):    # 点输入框：程序不在前台时 Qt 可能连焦点都不给（窗口没激活），按下那一下先看能不能打字
                edit.installEventFilter(self)
        self.fit_height()
        super().showEvent(event)
        self._close_t = None
        if native.reduce_motion() or self._in_place:
            self._in_place = False
            self._pop_t = None
            self.setWindowOpacity(1.0)
            return
        self._pop_t = 0.0                        # 淡入，同时往上浮 6 像素
        self._rising = True
        self.setWindowOpacity(0.0)
        self._set_rise(RISE)
        self.animate()

    def hideEvent(self, event) -> None:
        self._tip_timer.stop()
        self._tip_watch.stop()
        self._tip_target = None
        hide_tip()
        self.finish_animations()
        self.finish_height()
        if self._pop_t is not None or self._close_t is not None:
            self._pop_t = self._close_t = None
            self._set_rise(0)
            self.setWindowOpacity(1.0)
        self.clock.stop()
        super().hideEvent(event)

    def show_in_place(self) -> None:
        """原地出现（换语言 / 外观时重建的卡片顶替旧的）：不淡入、不上浮，接着用 fade_from 让旧的样子淡出。"""
        self._in_place = True
        self.show()

    def snapshot(self):
        """卡片里的内容现在的样子（不含底子），给顶替它的新卡片淡出用。"""
        return picture(self._main, self._main.rect())

    def fade_from(self, snap) -> None:
        """把旧卡片的样子盖在内容上，前一半淡出、新内容后一半淡入（和换页同一个节奏）。"""
        if snap is None or snap.isNull():
            return
        self._swap = _Swap(self, self, snap, QRect(self._main.geometry().topLeft(), snap.deviceIndependentSize().toSize()), [self._main])
        self._swap.tick(0.0)
        if not self.run_animator(self._swap):
            self._swap.tick(10.0)

    def dismiss(self) -> None:
        """关卡片：0.12 秒淡出再藏起来（×、Esc、再点一次打开它的按钮）。别处直接 hide() 的照旧立刻藏。"""
        if not self.isVisible() or self._close_t is not None:
            return
        if native.reduce_motion():
            self.hide()
            return
        hide_tip()
        self._pop_t = None
        self._set_rise(0)
        self._close_t = (1.0 - self.windowOpacity()) * CLOSE_S      # 淡入到一半就关：从现在的浓淡接着淡
        self.animate()

    @property
    def closing(self) -> bool:
        return self._close_t is not None

    def setVisible(self, visible: bool) -> None:
        if visible and self._close_t is not None and self.isVisible():
            o = self.windowOpacity()                 # 正在淡出又要显示（又点了打开）：停下，从现在的浓淡淡回来，不再上浮
            self._close_t = None
            self._rising = False
            self._pop_t = (1.0 - (1.0 - o) ** (1.0 / 3.0)) * POP_S
            self.animate()
            return
        super().setVisible(visible)

    def _set_rise(self, dy: float) -> None:
        """打开时往上浮：主叶连画的底子一起往下挪 dy（窗口不动，上下边距此消彼长）。表盘开着时它在管边距，不动。"""
        if self.dock.active:
            return
        dy = round(dy)
        m = self._outer.contentsMargins()
        if m.top() != SHADOW + dy:
            self._outer.setContentsMargins(SHADOW, SHADOW + dy, SHADOW, SHADOW - dy)
            self._outer.activate()
            self.update()                        # 整张重画：描边和纸片影画在主叶外面一两像素，只重画挪动的主叶，旧位置的影子会留在底下、顶上的描边被裁

    def _step_pop(self, dt: float) -> bool:
        if self._pop_t is not None:
            self._pop_t += dt
            self.setWindowOpacity(ease_out(self._pop_t / POP_S))
            if self._rising:
                self._set_rise(RISE * (1.0 - ease_out(self._pop_t / RISE_S)))
            if self._pop_t >= max(POP_S, RISE_S if self._rising else 0.0):
                self._pop_t = None
            return True
        if self._close_t is not None:
            self._close_t += dt
            self.setWindowOpacity(1.0 - ease_in(self._close_t / CLOSE_S))
            if self._close_t >= CLOSE_S:
                self.hide()                          # hideEvent 把浓淡改回 1
                return False
            return True
        return False

    # ---- 动画节拍 ----
    def animate(self) -> None:
        """有东西要动：跟着狗的每一帧一起走（frame_host），全程序一个节拍（widgets.FrameClock）。
        别各用各的计时器：标题行一个计时器、卡片高度用 Qt 自带的动画（16 毫秒一步、每步都改窗口大小）、狗又一个，狗渲染完要等屏幕，
        卡片的帧被挤到后面，帧间隔 5～50 毫秒乱跳；狗停掉就一帧不卡。"""
        self.clock.start()

    @property
    def frame_host(self):
        return self.clock.host

    @frame_host.setter
    def frame_host(self, host) -> None:
        self.clock.host = host

    def own_clock(self) -> None:
        self.clock.own_clock()

    def frame_step(self, now: float, period: float) -> bool:
        """往前走一帧（单测、录屏直接调）。"""
        if not self.clock.running:
            self.clock.running, self.clock._last = True, now - period
        return self.clock.frame_step(now, period)

    def _tick(self, dt: float) -> bool:
        busy = self._tag.tick(dt)
        layout_changed = self._leaf_anim
        if self._animators:
            rows = [a for a in self._animators if isinstance(a, Collapse)]
            for a in list(self._animators):
                try:
                    keep = a.tick(dt)
                except RuntimeError:                 # 它动的控件 / 效果已经不在了：只扔掉这一个，整张卡片接着动（卡死在高级设置）
                    log.exception("card animator failed")
                    keep = False
                if not keep:
                    self._animators.discard(a)
            busy = busy or bool(self._animators)
            if rows:
                self._relayout(rows)
                layout_changed = True
            QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        if self._leaf_anim:
            busy = self._step_height(dt) or busy
        busy = self._step_pop(dt) or busy
        if layout_changed:
            self._sync_side_geometry()
        return busy

    def _sync_side_geometry(self) -> None:
        """这一帧的内容排好后再对齐侧叶；主叶高度和整个窗口的占位高度分开。"""
        if not self.dock.active:
            return
        self._outer.activate()
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        self.dock.place()
        if not self._leaf_anim:
            self._leaf_final = self.dock.window_height(self._main.height() + 2 * SHADOW)
            if self.height() != self._leaf_final:
                self.setFixedHeight(self._leaf_final)

    def _relayout(self, rows: list) -> None:
        """展开 / 收起的行这一帧改了高度：从外往里马上排好，这一帧画出来就是新位置。Qt 自己的排版请求一层层往外传，
        一帧里传不到卡片这一层，下面的行会隔一帧才跟上、一下走两帧的量（单测量出来的）。"""
        self.body.invalidate()
        self.body.activate()
        done = set()
        for row in rows:
            chain, w = [], row.parentWidget()
            while w is not None and w is not self.content:
                chain.append(w)
                w = w.parentWidget()
            for w in reversed(chain):
                lay = w.layout()
                if lay is not None and id(lay) not in done:
                    done.add(id(lay))
                    lay.invalidate()
                    lay.activate()

    def run_animator(self, animator) -> bool:
        """卡片里的一个小动画（开关、展开的行、淡入淡出……，有 tick(dt)）挂到卡片的节拍上。卡片没显示、正在打开那一下（still）、
        系统开了「减少动态效果」：返回 False，调用的直接到位。"""
        if self._still or not self.isVisible() or native.reduce_motion():
            return False
        self._animators.add(animator)
        self.clock.start()
        return True

    @contextmanager
    def still(self):
        """这一段里的变化直接到位、不播动画（卡片打开那一下对齐设置：开关、动作行不该在淡入时才滑过去）。"""
        old, self._still = self._still, True
        try:
            yield
        finally:
            self._still = old

    def finish_animations(self) -> None:
        """卡片里正在动的小东西、打开的淡入上浮、关上的淡出立刻走到头（单测、关卡片时用）。"""
        if self._close_t is not None:
            self.hide()
            return
        if self._pop_t is not None:
            self._pop_t = None
            self._set_rise(0)
            self.setWindowOpacity(1.0)
        for _ in range(3):
            if not self._animators:
                break
            for a in list(self._animators):
                try:
                    keep = a.tick(10.0)
                except RuntimeError:
                    keep = False
                if not keep:
                    self._animators.discard(a)
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)

    # ---- 换内容：旧的淡出、新的淡入 ----
    def swap_content(self, change: Callable[[], None], animated: bool = True) -> None:
        """换一页：旧画面前一半淡出、新内容后一半淡入（和标题的字同一个节奏，两层不叠）；
        高度照旧用弹簧过渡。"""
        if self._swap is not None:
            self._swap.tick(10.0)
        view = self.scroll.viewport()
        self._swap = self.crossfade(self._main, QRect(view.mapTo(self._main, QPoint(0, 0)), view.size()), change, [self.content], animated)

    def crossfade(self, holder: QWidget, rect: QRect, change: Callable[[], None], fresh: list, animated: bool = True):
        """换掉 holder 里 rect 那一块的样子（换页、睡着时四个胶囊换成「醒来」、检查更新那一行换字）：换之前拍一张图盖在上面，
        前一半淡出；fresh 里的控件（换上来的）后一半淡入。两层不叠，点不到那张图。不能动画时直接换。"""
        if not (animated and self.isVisible() and not self._still and not native.reduce_motion()):
            change()
            return None
        snap = picture(holder, rect)                 # 屏幕上现在的样子（上一个还没淡完的也算在里面），新的从这里接着淡
        for a in [a for a in self._animators if isinstance(a, _Swap) and a.touches(holder, fresh)]:
            a.finish()                               # 同一处的上一个先收尾：不然新的换上效果时 Qt 把旧的删了，旧的每帧去改它就出错
            self._animators.discard(a)               # （检查更新回来得快，「正在检查」还没淡完就换「已是最新」，卡死在高级设置）
        change()
        fade = _Swap(self, holder, snap, rect, [w for w in fresh if w is not None])
        fade.tick(0.0)
        self.run_animator(fade)
        return fade

    # ---- 高度过渡：窗口只改一次大小，中间的高度只在画面上变 ----
    @property
    def height_animating(self) -> bool:
        return self._leaf_anim

    @property
    def height_target(self) -> int:
        return self._leaf_final if self._leaf_anim else self.height()

    def painted_height(self) -> int:
        """主叶现在画出来的高度（含阴影边距）；侧叶可能撑大窗口，但不参与主叶的高度过渡。"""
        return (round(self._leaf.value) if self._leaf_anim else self._main.height()) + 2 * SHADOW

    def animate_height(self, h0: int, h1: int) -> None:
        """主叶过渡到 fit_height 量好的目标；h0 是旧主叶高度，h1 是整个窗口占位，两者都含阴影边距。"""
        target = self._main_final
        if h0 == target + 2 * SHADOW or not self.isVisible() or native.reduce_motion():
            self.finish_height()
            if not self.dock.active:
                self.setFixedHeight(h1)
            return
        if not self._leaf_anim:
            self._leaf.value, self._leaf.velocity = float(h0 - 2 * SHADOW), 0.0
        self._leaf.set_target(float(target))
        self._leaf_anim, self._leaf_final = True, h1
        self._main.setFixedHeight(max(self._main.height(), h0 - 2 * SHADOW, target))   # 收起的行还在慢慢收：主叶先放得下，走完再缩
        self._apply_height()
        self.setFixedHeight(max(h0, h1, self.height()))
        self.animate()

    def hold_height(self) -> None:
        """高度要过渡之前先调：按现在画出来的高度进入过渡（窗口、主叶都不动），再量新高度。
        别先用 fit_height 把窗口改成新高度、再用 animate_height 改回来：变矮的换页窗口先缩再长，白改两次大小；
        变高的那一下主叶还没裁，新内容露在卡片底边外面。"""
        if self._leaf_anim or not self.isVisible():
            return
        self._leaf.value, self._leaf.velocity = float(self._main.height()), 0.0
        self._leaf.set_target(self._leaf.value)
        self._leaf_anim, self._leaf_final = True, self.height()
        self._apply_height()

    def _step_height(self, dt: float) -> bool:
        self._leaf.step(dt)
        if self._leaf.settled:
            self.finish_height(sync_side=False)  # _tick 最后统一对齐，避免同一帧按中途布局摆两次
            return False
        self._apply_height()
        return True

    def _apply_height(self) -> None:
        clip = math.ceil(self._leaf.value)
        if clip < self._main.height():
            self._main.setMask(QRegion(0, 0, self._main.width(), max(0, clip)))   # 内容按画出来的高度裁（变高时下面还没"长"出来的部分不露）
        else:
            self._main.clearMask()
        self.update()

    def finish_height(self, *, sync_side: bool = True) -> None:
        """高度过渡立刻走完：去掉裁剪，主叶和窗口改成最后的高度。"""
        if not self._leaf_anim:
            return
        self._leaf_anim = False
        self._leaf.set_target(self._leaf.target, instant=True)
        self._main.clearMask()
        if self._main_final:
            self._main.setFixedHeight(self._main_final)
        if not self.dock.active:
            self.setFixedHeight(self._leaf_final)
        elif sync_side:
            self._sync_side_geometry()  # 直接结束动画（换页、隐藏）时也按最终锚点收拢窗口
        self.update()

    def toggle_near(self, anchor: QWidget) -> None:
        if self.isVisible() and not self.closing:
            self.dismiss()
            return
        if self.closing:
            self.show()                          # 正在淡出又点了：停下，从现在的浓淡淡回来（setVisible），不重新摆
            return
        self.place_near(anchor)
        self.show()
        if self.dock.pane is not None:
            self.place_near(anchor)      # 滚动区里的内容显示时才摆好，侧边面板的锚点这时才量得准；还在淡入的第一帧（不透明度 0），看不出挪
        self.raise_()                    # 不 activateWindow：程序一被激活，macOS 会切到程序有窗口的那个桌面；点卡片时才激活，那时卡片就在眼前，不跳
        self.setFocus()

    def place_near(self, anchor: QWidget) -> None:
        """放在狗的斜对面、朝屏幕中心那一边：狗在右上就往左下伸（卡片的右上角贴狗的左下角），左上往右下、
        左下往右上、右下往左上。放不下就往屏幕里挪；挪完侧边面板（表盘，永远往右弹）还会碰到狗，就再往左让出它的宽度。
        狗占的地方用狗窗口的 dog_rect（窗口缩小时比狗宽，给姿势条留的，透明、点不到，不算狗）。"""
        g = anchor.dog_rect() if hasattr(anchor, "dog_rect") else anchor.frameGeometry()
        screen = QApplication.screenAt(g.center()) or QApplication.primaryScreen()
        ag = screen.availableGeometry()
        self.fit_height(ag.height())
        self._outer.activate()
        w, h = self.width() - 2 * SHADOW, self.height() - 2 * SHADOW        # 卡片本身（不含阴影边距）
        dog_right = g.center().x() >= ag.center().x()
        dog_top = g.center().y() < ag.center().y()
        x = g.left() - NEAR_GAP - w if dog_right else g.right() + NEAR_GAP
        y = g.bottom() + NEAR_GAP if dog_top else g.top() - NEAR_GAP - h
        x = max(ag.left(), min(ag.right() - w, x))
        y = max(ag.top(), min(ag.bottom() - h, y))
        extra, side_h = self.side_extent()
        if extra and dog_right:                                              # 表盘往右弹会盖到狗：卡片再往左让出表盘；左边也到头了就上下再挪开
            anchor = round(self.side_anchor_y()) - SHADOW                     # 锚点离卡片顶多远
            def dial_rect(margin: int = 0) -> QRect:
                return QRect(x + w - self.dock.overlap(), y + anchor - side_h // 2 - margin, extra + self.dock.overlap(), side_h + 2 * margin)
            if dial_rect().intersects(g):
                x = max(ag.left(), g.left() - NEAR_GAP - w - extra)
            if dial_rect(DIAL_CLEAR).intersects(g):                          # 弹出时卡片变宽、内容会重排几个像素：上下各多留 DIAL_CLEAR，只往离开狗的方向挪
                if dog_top:
                    y = min(ag.bottom() - h, max(y, g.bottom() + 1 + DIAL_CLEAR - (anchor - side_h // 2)))
                else:
                    y = max(ag.top(), min(y, g.top() - (anchor + side_h // 2) - 1 - DIAL_CLEAR))
        self.move(x - SHADOW, y - SHADOW)

    # ---- 画卡片 ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self._main.geometry())                     # 主叶（侧边的表盘自己画）
        if self._leaf_anim:
            r.setHeight(self._leaf.value)                     # 高度过渡中：底边按弹簧的值画（窗口不跟着每帧改大小）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 28, 33, sticker.SHADOW_ALPHA))          # 纸片影：实心、往右下偏一点、不模糊
        p.drawRoundedRect(r.translated(sticker.SHADOW_OFFSET), sticker.RADIUS, sticker.RADIUS)
        p.setBrush(self.theme.bg)
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))                  # 描边：和狗的轮廓线一样
        p.drawRoundedRect(r, sticker.RADIUS, sticker.RADIUS)

    # ---- 交互 ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(event)

    def _focus_changed(self, _old, now) -> None:
        """卡片里的输入框拿到焦点（改名、添加页起名字、点数字输入大小）：要能打字（ensure_typing）。"""
        try:
            mine = isinstance(now, QLineEdit) and now.window() is self
        except RuntimeError:
            return
        if mine:
            self.ensure_typing()

    def ensure_typing(self) -> None:
        """要开始打字了（输入框拿到焦点、按在输入框上、点名字改名、点数字输入大小）。卡片点了不切前台（set_no_activate），要让它接键盘：
        先只让它成为 key window（不切前台，别的 App 还在前台）；成不了、或者 TYPE_ACTIVATES 开着，才把同桌切到前台（只在开始打字这一下）。"""
        if native.app_active():
            return
        if TYPE_ACTIVATES or native.make_key(self) is False:
            native.activate_app()


class _AccentFade:
    """强调色从 a 淡到 b（Card.set_accent）：两头慢的曲线，ACCENT_S 走完；中途又换就从现在的颜色接着淡。控件名单开始时取一次，走完再全部对一遍。"""

    def __init__(self, card: "Card", a: QColor, b: QColor, ta: QColor, tb: QColor):
        self.card, self.a, self.b, self.ta, self.tb = card, a, b, ta, tb
        self.t, self.done = 0.0, False
        self.widgets = card._accent_widgets()

    def tick(self, dt: float) -> bool:
        if self.done:
            return False
        self.t += dt
        u = _smooth(self.t / ACCENT_S)
        if self.t >= ACCENT_S:
            self.done = True
            self.card._show_accent(self.b, self.tb)              # 最后按全部控件对一遍：淡的路上新建的也换上
            return False
        self.card._show_accent(sticker.mix(self.a, self.b, u), sticker.mix(self.ta, self.tb, u), self.widgets)
        return True


def picture(widget: QWidget, rect: QRect):
    """widget 里 rect 那一块现在的样子：只画它自己和子控件，透明的地方留透明。不用 grab：grab 会先铺一层窗口底色（调色板的浅色），
    盖在卡片上就是一块浅色方框——深色模式下点检查更新、换页时闪一下白框，换语言时盖住圆角描边。"""
    from PySide6.QtGui import QPixmap
    dpr = widget.devicePixelRatioF()
    pm = QPixmap(max(1, round(rect.width() * dpr)), max(1, round(rect.height() * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    widget.render(pm, QPoint(), QRegion(rect), QWidget.RenderFlag.DrawChildren)
    return pm


class _Swap:
    """一块内容换样子（Card.crossfade）：换之前拍的旧样子盖在上面，前一半淡出；换上来的控件后一半淡入。"""

    def __init__(self, card: Card, holder: QWidget, snap, rect: QRect, fresh: list):
        self.card, self.holder, self.t, self.done = card, holder, 0.0, False
        self.label = QLabel(holder)
        self.label.setStyleSheet("background: transparent;")
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.label.setPixmap(snap)
        self.label.setGeometry(rect)
        self.old_fx = QGraphicsOpacityEffect(self.label)
        self.label.setGraphicsEffect(self.old_fx)
        self.fresh = []
        for w in fresh:
            fx = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(fx)
            self.fresh.append((w, fx))
        self.label.show()
        self.label.raise_()

    def touches(self, holder: QWidget, fresh: list) -> bool:
        """还在淡、而且和这一处有关（同一个底下、或换上来的是同一个控件）。"""
        return not self.done and (self.holder is holder or any(w is f for w, _fx in self.fresh for f in fresh))

    def finish(self) -> None:
        self.tick(10.0)

    def tick(self, dt: float) -> bool:
        if self.done:
            return False
        self.t += dt
        u = self.t / SWAP_S
        if u >= 1.0:
            self._end()
            return False
        try:
            self.old_fx.setOpacity(max(0.0, 1.0 - 2.0 * u))
            for _w, fx in self.fresh:
                fx.setOpacity(max(0.0, 2.0 * u - 1.0))
        except RuntimeError:                         # 效果被换掉了 / 控件删了：这一个就算走完
            self._end()
            return False
        return True

    def _end(self) -> None:
        self.done = True
        for step in (self.label.hide, self.label.deleteLater):
            try:
                step()
            except RuntimeError:
                pass
        for w, fx in self.fresh:
            try:
                if w.graphicsEffect() is fx:
                    w.setGraphicsEffect(None)
            except RuntimeError:
                pass
        if self.card._swap is self:
            self.card._swap = None
