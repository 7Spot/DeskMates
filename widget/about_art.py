"""「关于」页的那张图：没有图标的方底、无边界——正中猫狗（app 图标的 DM，dm_shapes.pieces），
左边是水（两只鸭子沉在水里只露水上那截、朝右游；水下一条鱼朝右），右边是沙滩（卡皮巴拉、乌龟朝左；几粒沙），天上一只海鸥；地面一条线，左半是水波、
右半是平平微微往上的沙滩，两头淡掉。

动物怎么出来（进关于页那段动画里，猫狗画完以后，widget/about.py 的 Hero 每帧按进度画）：
- 和下面的字同时出来，一起从模糊里变清楚（和字同一种糊法，card._blurred）。
- 只往里走（左边的朝右、右边的朝左），从到位的地方往外几像素那儿出来，慢慢起步、慢慢停到位，不往后退、不停顿。
- 各有性子：鸭妈妈慢悠悠、小鸭急着跟、鱼一冲一滑、卡皮巴拉懒懒地慢慢迈腿、乌龟慢吞吞爬脑袋一探一探、海鸥滑一会儿才慢慢扇两下（幅度小）。
  动作的快慢跟着身子的劲走（起步时由慢变快，快到位时一步比一步慢、一步比一步小），所以不会突然动起来、突然停。
- 鱼尾左右摆：侧面看就是尾巴一会儿变短、一会儿变长（绕尾巴根上下转是海豚的摆法）。

坐标是图自己的逻辑像素（宽 W）。形状全是布尔运算拼的：拼一次（scene()）存着，每帧只做变换、画。"""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QTransform

from widget import dm_shapes as S
from widget import marks

W, H = 280.0, 160.0                 # 图的坐标范围（逻辑像素）；关于页里只露 SHOW 那一截（上面空的那条不占地方）
SHOW = QRectF(0.0, 16.0, W, 140.0)
WATER_Y = 112.0                     # 地面（水面）高度
SHORE = 128.0                       # 水变成沙滩的地方（猫狗脚下）
X0, X1, FADE = 0.0, W, 34.0         # 地面两头、两头淡掉多长
DM_W, DM_CX = 98.0, 140.0           # 猫狗多宽、正中在哪；脚离地面 5 像素
K = 100.0                           # 小动物按 100 大小拼（按 1 拼、放大以后布尔运算拆出来的折线看得出棱角）
DUCK_WL = 232.0                     # 鸭子（参考图坐标）沉到这一道：身子中下部贴着水面，水下的不画


def clamp(u: float) -> float:
    return max(0.0, min(1.0, u))


def smooth(u: float) -> float:
    u = clamp(u)
    return u * u * (3.0 - 2.0 * u)


def span(t: float, a: float, b: float) -> float:
    return clamp((t - a) / (b - a)) if b > a else float(t >= b)


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def bez(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """三次贝塞尔缓动（和 CSS cubic-bezier 一样）。"""
    def f(x: float) -> float:
        x = clamp(x)
        t = x
        for _ in range(12):
            bx = 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3 - x
            dbx = 3 * (1 - t) ** 2 * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t ** 2 * (1 - x2)
            if abs(dbx) < 1e-7:
                break
            t = clamp(t - bx / dbx)
        return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3
    return f


def bursts(parts: tuple) -> Callable[[float], float]:
    """一冲一滑：parts 是几段（从哪、到哪、这一段走多少），每段顺地走，段和段之间几乎停着滑。"""
    def f(x: float) -> float:
        x = clamp(x)
        s = 0.0
        for a, b, share in parts:
            s += share * (smooth((x - a) / (b - a)) ** 0.85 if x > a else 0.0)
        return min(1.0, s)
    return f


# ---- 按 100 大小拼的小形状 ----
def _p(x: float, y: float) -> QPointF:
    return QPointF(x * K, y * K)


def kdots(pts, r: float) -> QPainterPath:
    return S.dots([(x * K, y * K) for x, y in pts], r * K)


def kblob(c, rx: float, ry: float, deg: float) -> QPainterPath:
    return S.blob((c[0] * K, c[1] * K), rx * K, ry * K, deg)


def krr(x, y, w, h, tl, tr, br, bl) -> QPainterPath:
    return S.rrect(x * K, y * K, w * K, h * K, tl * K, tr * K, br * K, bl * K)


def krect(x, y, w, h) -> QPainterPath:
    p = QPainterPath()
    p.addRect(QRectF(x * K, y * K, w * K, h * K))
    return p


def placer(whole: QPainterPath, cx: float, bottom: float, width: float, flip: bool = False) -> QTransform:
    """把 whole 缩到 width 宽，正中横坐标 cx、底边落在 bottom（flip：左右翻过来，脸朝另一边）。"""
    b = whole.boundingRect()
    k = width / b.width()
    return QTransform().translate(cx, bottom).scale(-k if flip else k, k).translate(-b.center().x(), -b.bottom())


def rot(pivot: QPointF, deg: float) -> QTransform:
    return QTransform().translate(pivot.x(), pivot.y()).rotate(deg).translate(-pivot.x(), -pivot.y())


# ---- 地面 ----
def ground_y(x: float) -> float:
    """地面的高度：左半水波（往右慢慢平了），猫狗脚下往右是沙滩，往右微微高一点。"""
    amp = 1.5 * (1 - smooth((x - (SHORE - 30)) / 50))
    rise = -3.0 * smooth((x - (SHORE + 10)) / 130)
    return WATER_Y + amp * math.sin(2 * math.pi * (x - X0) / 56.0) + rise


def ground_path() -> QPainterPath:
    p = QPainterPath(QPointF(X0, ground_y(X0)))
    x = X0
    while x < X1:
        x = min(X1, x + 1.0)
        p.lineTo(x, ground_y(x))
    return p


# ---- 动物（参考图坐标或 100 大小拼，朝右） ----
def duck_parts() -> tuple:
    """鸭子（圆胸、弯脖子、又长又扁微微上翘的鸭嘴、尖尾巴；浮在水里不画腿）：身子、尾巴（甩的时候绕尾巴根转）、尾巴根、整个。
"""
    p = QPainterPath(QPointF(14, 182))
    p.cubicTo(40, 168, 70, 160, 110, 150)
    p.cubicTo(160, 138, 210, 140, 246, 146)
    p.cubicTo(262, 140, 262, 124, 258, 108)
    p.cubicTo(250, 80, 262, 44, 296, 40)
    p.cubicTo(322, 36, 338, 52, 342, 72)
    p.cubicTo(356, 78, 372, 84, 390, 86)
    p.cubicTo(400, 88, 400, 100, 388, 102)
    p.cubicTo(370, 105, 352, 107, 338, 107)
    p.cubicTo(328, 118, 324, 136, 334, 156)
    p.cubicTo(356, 186, 350, 230, 312, 256)
    p.cubicTo(282, 276, 240, 290, 198, 290)
    p.cubicTo(138, 290, 80, 262, 44, 224)
    p.cubicTo(30, 210, 20, 196, 14, 182)
    p.closeSubpath()
    body = p.united(S.soft([(40, 172), (12, 160), (34, 186)], 3))
    eye = QPainterPath()
    eye.addEllipse(QPointF(312, 66), 8, 8)
    body = body.subtracted(eye)
    cut_t = QPainterPath()
    cut_t.addRect(QRectF(-50, -50, 50 + 96, 400))
    cut_m = QPainterPath()
    cut_m.addRect(QRectF(-50, -50, 50 + 80, 400))
    return body.subtracted(cut_m), body.intersected(cut_t), QPointF(88, 196), body


def capy_parts() -> tuple:
    """卡皮巴拉（桶一样的大身子、背在后半截最高、圆屁股，方方的大脑袋、钝圆鼻头，头顶两只小圆耳朵，四条直直的圆头小短腿）：
    身子、四条腿（各自绕腿根转，相位）、整个。腿底下不带往前伸的脚掌（像穿了鞋）。"""
    p = QPainterPath(QPointF(38, 236))
    p.cubicTo(28, 150, 92, 92, 170, 76)
    p.cubicTo(236, 62, 290, 60, 322, 70)
    p.cubicTo(336, 74, 342, 62, 356, 58)
    p.lineTo(440, 58)
    p.cubicTo(474, 60, 490, 80, 491, 108)
    p.cubicTo(492, 134, 488, 152, 472, 157)
    p.cubicTo(458, 162, 446, 166, 432, 170)
    p.cubicTo(408, 176, 392, 190, 384, 214)
    p.cubicTo(376, 236, 372, 252, 362, 268)
    p.cubicTo(310, 284, 200, 290, 150, 282)
    p.cubicTo(100, 292, 50, 290, 38, 236)
    p.closeSubpath()
    ears = QPainterPath()
    ears.addEllipse(QPointF(360, 54), 13, 13)
    ears.addEllipse(QPointF(386, 50), 13, 13)
    eye = QPainterPath()
    eye.addEllipse(QPointF(438, 94), 8.5, 8.5)
    body = p.united(ears).subtracted(eye)
    legs = []
    for x, top, w, bottom, phase in ((66, 232, 40, 336, 0.0), (126, 250, 30, 330, math.pi), (322, 236, 36, 336, math.pi), (282, 256, 28, 330, 0.0)):
        leg = QPainterPath()
        leg.addRoundedRect(QRectF(x, top, w, bottom - top), w * 0.5, w * 0.5)
        legs.append((leg, QPointF(x + w / 2, top + 18), phase))
    whole = body
    for leg, _pivot, _phase in legs:
        whole = whole.united(leg)
    return body, legs, whole


def turtle_parts() -> tuple:
    """乌龟：圆背壳（两道米白的弧像龟甲纹）、壳下一圈裙边、往前探的圆脑袋（爬的时候一探一探）、两条短腿、一点小尾巴。
    返回（壳带尾巴、脑袋、腿、整个）。"""
    dome = kblob((0, 0.1), 0.5, 0.44, 0).intersected(krect(-2, -2, 4, 2.06))
    for a, b, c in (((-0.3, 0.04), (-0.18, -0.24), (0.0, -0.3)), ((0.0, -0.3), (0.18, -0.24), (0.3, 0.04))):
        arc = QPainterPath(_p(*a))
        arc.quadTo(_p(*b), _p(*c))
        dome = dome.subtracted(S.stroke(arc, 0.045 * K))
    rim = krr(-0.58, 0.07, 1.16, 0.11, 0.055, 0.055, 0.055, 0.055)
    seam = QPainterPath(_p(-0.56, 0.062))
    seam.lineTo(_p(0.56, 0.062))
    cut = S.stroke(seam, 0.045 * K)
    tail = S.soft([(-0.56 * K, 0.08 * K), (-0.7 * K, 0.13 * K), (-0.56 * K, 0.15 * K)], 0.02 * K)
    shell = dome.subtracted(cut).united(rim.subtracted(cut)).united(tail)
    head = kblob((0.68, -0.02), 0.16, 0.13, -8).united(
        S.soft([(0.5 * K, 0.02 * K), (0.6 * K, -0.06 * K), (0.62 * K, 0.12 * K), (0.52 * K, 0.14 * K)], 0.02 * K))
    head = head.subtracted(kdots([(0.73, -0.06)], 0.035))
    legs = []
    for i, x in enumerate((-0.38, 0.22)):
        legs.append((krr(x, 0.12, 0.17, 0.2, 0.04, 0.04, 0.085, 0.085), _p(x + 0.085, 0.14), i * math.pi))
    whole = shell.united(head)
    for leg, _pivot, _phase in legs:
        whole = whole.united(leg)
    return shell, head, legs, whole


class Walk:
    """一只动物怎么出来：at 画完猫狗以后多久开始出来（和字一起）；delay 再过多久自己开始走；end 画完猫狗以后多久走到位；
    push 从到位的地方往外多远出来；ease 这一段怎么走（各有性子）。"""

    def __init__(self, at: float, delay: float, end: float, push: float, ease: Callable[[float], float]):
        self.at, self.delay, self.end, self.push, self.ease = at, delay, end, push, ease
        self.peak = max((ease(min(1.0, u / 200 + 0.005)) - ease(max(0.0, u / 200 - 0.005))) / 0.01 for u in range(1, 200))


class Scene:
    """拼好的整张（scene() 拼一次）：地面、沙粒、猫狗、五只动物，摆在图自己的坐标里。paint(p, t) 按进关于页那段的第 t 秒画（tf：猫狗画完的时刻），
    paint_static 是到位以后的样子（关于页自己画的就是它，过渡动画最后一帧和它一个像素不差）。"""

    END = 1.62                         # 猫狗画完以后多久都到位（最晚的卡皮巴拉）

    def __init__(self):
        pieces = marks.app_pieces()
        wb = pieces["whole"].boundingRect()
        k = DM_W / wb.width()
        self.dm_t = QTransform().translate(DM_CX, WATER_Y - 5.0).scale(k, k).translate(-wb.center().x(), -S.BASE)
        self.dog = self.dm_t.map(pieces["dog"].subtracted(pieces["dog_face"]))      # 猫狗（填黑的两块，洞已挖好）
        self.cat = self.dm_t.map(pieces["cat"].subtracted(pieces["cat_face"]))
        self.ground = S.stroke(ground_path(), 2.6)
        above = QPainterPath(QPointF(X0 - 60, -80))
        above.lineTo(X1 + 60, -80)
        x = X1 + 60
        while x > X0 - 60:
            above.lineTo(x, ground_y(min(X1, max(X0, x))))
            x -= 1.0
        above.closeSubpath()
        self.above_water = above                                     # 水面以上：鸭子只画这一块（水下那截看不见）
        main, tail, pivot, whole = duck_parts()
        db = whole.boundingRect()
        self.ducks = []
        for cx, w, walk, bob_f, bob_a, flicks, wag in (
                (64.0, 37.0, Walk(0.05, 0.0, 1.45, 8.0, bez(0.4, 0.0, 0.45, 1.0)), 1.15, 0.5, (0.32, 0.5), 13.0),     # 鸭妈妈：慢悠悠
                (28.0, 24.0, Walk(0.12, 0.02, 1.6, 10.0, bez(0.3, 0.0, 0.35, 1.0)), 1.9, 0.65, (0.26, 0.42), 16.0)):   # 小鸭：急着跟上
            kd = w / db.width()
            M = QTransform().translate(cx, WATER_Y).scale(kd, kd).translate(-db.center().x(), -DUCK_WL)
            self.ducks.append(dict(main=M.map(main), tail=M.map(tail), pivot=M.map(pivot), walk=walk, bob_f=bob_f, bob_a=bob_a,
                                   flicks=flicks, wag=wag))
        fb, ft, fe, root = S.fish_parts((0, 0), 140)
        M = placer(fb.united(ft).subtracted(fe), 50.0, 146.0, 28.0)
        self.fish = dict(body=M.map(fb.subtracted(fe)), tail=M.map(ft), root=M.map(root),
                         walk=Walk(0.1, 0.0, 1.4, 8.0, bursts(((0.0, 0.45, 0.6), (0.52, 0.97, 0.4)))))
        cb, legs, cw = capy_parts()
        M = placer(cw, 234.0, ground_y(234.0) - 1.0, 54.0, flip=True)
        self.capy = dict(body=M.map(cb), legs=[(M.map(l), M.map(pv), ph) for l, pv, ph in legs],
                         walk=Walk(0.06, 0.1, 1.6, 6.5, bez(0.45, 0.0, 0.5, 1.0)))
        ts, th, tl, tw = turtle_parts()
        M = placer(tw, 216.0, 152.0, 37.0, flip=True)
        self.turtle = dict(shell=M.map(ts), head=M.map(th), legs=[(M.map(l), M.map(pv), ph) for l, pv, ph in tl],
                           walk=Walk(0.14, 0.04, 1.58, 5.5, bez(0.45, 0.0, 0.5, 1.0)))
        self.gull_t = QTransform().translate(226, 24).scale(0.2, 0.2)
        self.gull_walk = Walk(0.12, 0.05, 1.55, 6.5, bez(0.3, 0.0, 0.4, 1.0))
        keep_out = self.turtle["shell"].boundingRect().united(self.turtle["head"].boundingRect()).adjusted(-5, -5, 5, 5)
        dots = ((158, 121, 1.1), (171, 129, 0.9), (186, 119, 1.0), (199, 134, 1.0), (212, 124, 0.9), (227, 131, 1.0), (242, 120, 1.1),
                (256, 128, 0.9), (270, 118, 1.0), (275, 126, 0.8), (166, 141, 0.8), (192, 147, 0.9), (246, 143, 0.8), (266, 139, 0.9),
                (180, 136, 0.8), (258, 150, 0.8))
        self.dots = [(x, y, r) for x, y, r in dots if not keep_out.contains(QPointF(x, y))]
        self.outline_dog = pieces["dog"]                             # 两根线描的轮廓（拼好的坐标；用的人自己乘 dm_t）
        self.outline_cat = pieces["cat"]

    # ---- 动 ----
    def _motion(self, t: float, tf: float, walk: Walk) -> tuple[float, float, float]:
        """只往里走：从到位的地方往外 push 那儿慢慢出来，自己往里游、往里走，慢慢起步、慢慢停到位。返回（离到位往外多远、出来多少 0..1、走到哪 0..1）。"""
        a0 = tf + walk.at
        tau = span(t, a0 + walk.delay, tf + walk.end)
        off = walk.push * (1.0 - walk.ease(tau))
        shown = 1.0 - (1.0 - span(t, a0, a0 + 0.6)) ** 2.2
        return off, shown, tau

    def _vigor(self, t: float, tf: float, walk: Walk) -> float:
        """自己使劲的程度 0..1：刚出来时慢慢有劲，快到位时慢慢没劲。"""
        a0 = tf + walk.at
        tau = span(t, a0 + walk.delay, tf + walk.end)
        if 0.0 < tau < 1.0:
            v = (walk.ease(min(1.0, tau + 0.01)) - walk.ease(max(0.0, tau - 0.01))) / 0.02 / walk.peak
        else:
            v = 0.0
        return clamp((0.35 + 0.8 * v) * smooth(span(t, a0, a0 + 0.5)) * (1.0 - smooth(span(tau, 0.6, 1.0))))

    def _cycles(self, t: float, tf: float, walk: Walk, f: float) -> float:
        """动作走了几圈：按使劲的程度累加（有劲时快、没劲时慢），起步和停下都不突然。"""
        a0 = tf + walk.at
        if t <= a0:
            return 0.0
        n = 32
        dt = (t - a0) / n
        return f * dt * sum(self._vigor(a0 + (i + 0.5) * dt, tf, walk) for i in range(n))

    # ---- 画 ----
    def paint_ground(self, p: QPainter, reach: float, ink: QColor) -> None:
        """地面从猫狗脚下往两头长到 reach（0..1），两头淡掉；沙粒跟着地面长出来。"""
        if reach <= 0.0:
            return
        cx = DM_CX
        half = reach * max(cx - X0, X1 - cx) + 0.001

        def alpha(x: float) -> float:
            ends = min(smooth((x - X0) / FADE), smooth((X1 - x) / FADE))
            return clamp(ends * (1.0 - smooth((abs(x - cx) - (half - 14.0)) / 14.0)))

        g = QLinearGradient(X0, 0.0, X1, 0.0)
        for i in range(61):
            x = lerp(X0, X1, i / 60)
            c = QColor(ink)
            c.setAlphaF(alpha(x))
            g.setColorAt(i / 60, c)
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawPath(self.ground)
        for x, y, r in self.dots:
            a = alpha(x)
            if a > 0.01:
                c = QColor(ink)
                c.setAlphaF(a)
                p.setBrush(c)
                p.drawEllipse(QPointF(x, y), r, r)
        p.restore()

    def paint_animals(self, p: QPainter, t: float, tf: float, ink: QColor, gone: float = 0.0, act: float = 1.0) -> None:
        """五只动物在第 t 秒的样子。gone：一起糊开淡掉了多少（中途回主页面）；act：动作的幅度（倒着走时不迈腿，0..1）。"""
        from widget.card import _blurred

        def show(walk: Walk, paint: Callable[[QPainter], None], box: QRectF, shown: float) -> None:
            e = shown * (1.0 - gone)
            if e > 0.0:
                _blurred(p, paint, box.adjusted(-14, -12, 14, 12), (1.0 - e) * 5.0, e)

        for d in self.ducks:          # 鸭子（左边，朝右）：身子轻轻起伏，中间甩两下尾巴；水下那截不画
            w = d["walk"]
            off, shown, tau = self._motion(t, tf, w)
            vig = self._vigor(t, tf, w) * act
            dy = -d["bob_a"] * math.sin(2 * math.pi * self._cycles(t, tf, w, d["bob_f"])) * vig
            wag = 0.0
            for at in d["flicks"]:
                u = (tau - at) / 0.14
                if 0.0 < u < 1.0:
                    wag += d["wag"] * math.sin(math.pi * u) ** 2 * act

            def paint(q, d=d, off=off, dy=dy, wag=wag):
                q.save()
                q.setPen(Qt.NoPen)
                q.setBrush(ink)
                q.setClipPath(self.above_water, Qt.IntersectClip)
                q.translate(-off, dy)
                q.drawPath(d["main"])
                q.drawPath(rot(d["pivot"], -wag).map(d["tail"]))
                q.restore()
            show(w, paint, d["main"].boundingRect().united(d["tail"].boundingRect()).adjusted(-w.push, 0, 0, 0), shown)
        f = self.fish                 # 鱼（左边水下，朝右）：一冲一滑，冲的时候尾巴左右摆（侧面看一会儿变短、一会儿变长）
        w = f["walk"]
        off, shown, tau = self._motion(t, tf, w)
        vig = self._vigor(t, tf, w) * act
        dy = 0.4 * math.sin(2 * math.pi * self._cycles(t, tf, w, 1.2)) * vig
        sx = math.cos(math.radians(55.0) * math.sin(2 * math.pi * self._cycles(t, tf, w, 3.0)) * vig)
        r = f["root"]
        flap = QTransform().translate(r.x(), r.y()).scale(sx, 1.0).translate(-r.x(), -r.y())

        def paint(q, off=off, dy=dy, flap=flap):
            q.save()
            q.setPen(Qt.NoPen)
            q.setBrush(ink)
            q.translate(-off, dy)
            q.drawPath(f["body"])
            q.drawPath(flap.map(f["tail"]))
            q.restore()
        show(w, paint, f["body"].boundingRect().united(f["tail"].boundingRect()).adjusted(-w.push, 0, 0, 0), shown)
        c = self.capy                 # 卡皮巴拉（右边沙滩，朝左）：懒懒的，慢慢迈腿，身子一沉一沉
        w = c["walk"]
        off, shown, tau = self._motion(t, tf, w)
        vig = self._vigor(t, tf, w) * act
        phase = 2 * math.pi * self._cycles(t, tf, w, 1.3)
        dy = -0.5 * abs(math.sin(phase)) * vig

        def paint(q, off=off, dy=dy, phase=phase, vig=vig):
            q.save()
            q.setPen(Qt.NoPen)
            q.setBrush(ink)
            q.translate(off, dy)
            for leg, pivot, ph in c["legs"]:
                q.drawPath(rot(pivot, 11.0 * math.sin(phase + ph) * vig).map(leg))
            q.drawPath(c["body"])
            q.restore()
        box = c["body"].boundingRect()
        for leg, _pivot, _ph in c["legs"]:
            box = box.united(leg.boundingRect())
        show(w, paint, box.adjusted(0, 0, w.push, 0), shown)
        tt = self.turtle              # 乌龟（右边沙地，朝左）：慢吞吞地爬，两条短腿交替迈，脑袋往前一探一探
        w = tt["walk"]
        off, shown, tau = self._motion(t, tf, w)
        vig = self._vigor(t, tf, w) * act
        phase = 2 * math.pi * self._cycles(t, tf, w, 1.1)
        dy = -0.3 * abs(math.sin(phase)) * vig
        reach = 0.8 * math.sin(phase) * vig

        def paint(q, off=off, dy=dy, phase=phase, vig=vig, reach=reach):
            q.save()
            q.setPen(Qt.NoPen)
            q.setBrush(ink)
            q.translate(off * 0.8, dy)
            for leg, pivot, ph in tt["legs"]:
                q.drawPath(rot(pivot, 14.0 * math.sin(phase + ph) * vig).map(leg))
            q.drawPath(tt["shell"])
            q.translate(-reach, 0.0)
            q.drawPath(tt["head"])
            q.restore()
        show(w, paint, tt["shell"].boundingRect().united(tt["head"].boundingRect()).adjusted(-3, 0, w.push, 6), shown)
        w = self.gull_walk            # 海鸥：滑进来，中间慢慢扇两下翅膀，幅度小
        off, shown, tau = self._motion(t, tf, w)
        u = span(tau, 0.08, 0.92)
        flap = 0.45 * math.sin(2 * math.pi * 2.0 * u) * math.sin(math.pi * u) * act if 0.0 < u < 1.0 else 0.0
        line = self.gull_t.map(S.gull_line((0, 0), 132, flap))

        def paint(q, off=off, line=line):
            q.save()
            q.translate(off * 0.45, -off * 0.15)
            q.setPen(QPen(ink, 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            q.setBrush(Qt.NoBrush)
            q.drawPath(line)
            q.restore()
        show(w, paint, line.boundingRect().adjusted(-4, -8, 8, 8), shown)

    def paint_dm(self, p: QPainter, ink: QColor, dog: float = 1.0, cat: float = 1.0) -> None:
        """猫狗（填黑的两块）：dog、cat 各自多浓。"""
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        for path, a in ((self.dog, dog), (self.cat, cat)):
            if a > 0.0:
                p.setOpacity(a)
                p.drawPath(path)
        p.restore()

    def paint_static(self, p: QPainter, ink: QColor) -> None:
        """到位以后的样子（关于页自己画的就是它）。"""
        self.paint_ground(p, 1.0, ink)
        self.paint_dm(p, ink)
        self.paint_animals(p, 1e6, 0.0, ink)


_scene: Optional[Scene] = None


def scene() -> Scene:
    """拼好的整张（第一次用到时拼，约几十毫秒；设置卡片打开后先备着）。"""
    global _scene
    if _scene is None:
        _scene = Scene()
    return _scene


def ready() -> bool:
    return _scene is not None
