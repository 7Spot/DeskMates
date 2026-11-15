"""app 图标的形状：猫狗拼成的 DM（这里只搬用得到的）。
左边 D 是狗：左边一只耷拉的耳朵（缝只开在里侧）、实心白点眼睛、扁三角鼻子（藏在猫后面那只耳朵不要：鼓出头顶像包，藏在 D 里多一道缝也不要）；
右边 M 是歪过来靠在它身上的猫：两只尖耳朵、眼睛、小三角鼻子。两个合起来的轮廓是 DM，中间留一道米白的缝；眼睛、鼻子是挖空的洞。
整张（128 像素以上）再加天上一只海鸥、脚下一道水线、水下一条鱼。所有尺寸狗的眼睛都是实心白点（看着猫的眼珠那版没要）。
坐标按 1024 的画布（图标方底是 TILE）。全是布尔运算拼的、很费：拼一次存着、按要的大小缩放（widget/marks.py；关于页的图 widget/about_art.py 用 pieces 那几块）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPolygonF, QTransform

TILE, RADIUS = QRectF(100, 100, 824, 824), 186   # 图标的米白圆角方底
TILE_LINE = 26                                    # 方底的黑边：描在方底的边上、一半在外；没有影子
BASE = 742                                        # 狗和猫都站在这条线上
GAP = 22                                          # 猫压在狗身上，中间留的米白缝
DOG_EYES, DOG_EYE_R = ((378, 478), (452, 478)), 24          # 狗的两只眼睛（挖空的洞；64 以下是实心白点）
DOG_NOSE = ((396, 524), (432, 524), (414, 544))
CAT_LEAN, CAT_OVERLAP = 13.0, 30                             # 猫往狗身上歪多少度、压住狗多少
SMALL_FIT = ((600, 470), (512, 532))                         # 只有猫狗那张：缩进多大的框、摆在哪
SCENE_FIT = ((500, 350), (512, 500))                         # 整张里的猫狗
GULL_AT, GULL_W, GULL_LW = (716, 236), 132, 20               # 整张里的海鸥：中心、宽、线粗
FISH_AT, FISH_W = (372, 806), 140                            # 水下的鱼
WAVE_Y, WAVE_X, WAVE_LW = 706, (196, 828), 16                # 脚下的水线：高度、两头、线粗


def rrect(x, y, w, h, tl, tr, br, bl) -> QPainterPath:
    """四个角各自圆角的方块。"""
    p = QPainterPath()
    p.moveTo(x + tl, y)
    p.lineTo(x + w - tr, y)
    p.arcTo(QRectF(x + w - 2 * tr, y, 2 * tr, 2 * tr), 90, -90)
    p.lineTo(x + w, y + h - br)
    p.arcTo(QRectF(x + w - 2 * br, y + h - 2 * br, 2 * br, 2 * br), 0, -90)
    p.lineTo(x + bl, y + h)
    p.arcTo(QRectF(x, y + h - 2 * bl, 2 * bl, 2 * bl), 270, -90)
    p.lineTo(x, y + tl)
    p.arcTo(QRectF(x, y, 2 * tl, 2 * tl), 180, -90)
    p.closeSubpath()
    return p


def stroke(path, w) -> QPainterPath:
    """一条线描成 w 粗的实心形状（圆头、圆角）。"""
    s = QPainterPathStroker()
    s.setWidth(w)
    s.setCapStyle(Qt.RoundCap)
    s.setJoinStyle(Qt.RoundJoin)
    return s.createStroke(path).united(QPainterPath())


def soft(pts, r) -> QPainterPath:
    """多边形往外胀 r、凸角变圆（耳朵、鼻子这种小三角）。"""
    poly = QPainterPath()
    poly.addPolygon(QPolygonF([QPointF(*q) for q in pts]))
    poly.closeSubpath()
    return stroke(poly, 2 * r).united(poly)


def dots(pts, r) -> QPainterPath:
    p = QPainterPath()
    for c in pts:
        p.addEllipse(QPointF(*c), r, r)
    return p


def blob(c, rx, ry, deg) -> QPainterPath:
    """以 c 为中心、转了 deg 度的椭圆。"""
    p = QPainterPath()
    p.addEllipse(QPointF(0, 0), rx, ry)
    return QTransform().translate(*c).rotate(deg).map(p)


def d_round() -> QPainterPath:
    """D：直的左边、圆的右边。"""
    return rrect(240, 330, 300, BASE - 330, 56, 196, 196, 56)


def m_round() -> tuple[QPainterPath, QPainterPath]:
    """M 的身子（两只尖耳朵就是 M 的两个尖、底下中间一道缺口）和一双眼睛。"""
    x0, w, top, ear, r, tip, wide = 566, 250, 402, 80, 30, 10, 104
    c = x0 + w / 2
    pts = [(x0 + r, BASE - r), (x0 + r, top + 40), (x0 + r + tip, top - ear), (x0 + wide, top + 6), (c, top + 30),
           (x0 + w - wide, top + 6), (x0 + w - r - tip, top - ear), (x0 + w - r, top + 40), (x0 + w - r, BASE - r),
           (c + 66, BASE - r), (c, BASE - 92), (c - 66, BASE - r)]
    return soft(pts, r), dots([(c - 38, top + 126), (c + 38, top + 126)], 22)


def _lean(L, parts, deg, overlap) -> tuple[list, QPointF]:
    """lean，外加它绕的那个点挪过去以后在哪（猫的右下角）。"""
    b = parts[0].boundingRect()
    t = QTransform().translate(b.right(), b.bottom()).rotate(-deg).translate(-b.right(), -b.bottom())
    clip = QPainterPath()
    clip.addRect(QRectF(0, 0, 1024, BASE))
    moved = [t.map(p) for p in parts]
    moved[0] = moved[0].intersected(clip)
    dx = 200.0
    while dx > -400 and not moved[0].translated(dx, 0).intersects(L):
        dx -= 2
    dx -= overlap
    return [p.translated(dx, 0) for p in moved], QPointF(b.right() + dx, b.bottom())


def lean(L, parts, deg, overlap) -> list:
    """parts[0] 是右边那个的身子：绕右下角往左倒 deg 度、底切平在 BASE，往左挪到压住 L 再多压 overlap；parts 里别的（眼睛、鼻子）跟着一起挪。"""
    return _lean(L, parts, deg, overlap)[0]


def assemble(L, R, holes) -> QPainterPath:
    """右边那个压在左边身上（中间留 GAP 宽的米白缝），再挖掉眼睛、鼻子。"""
    halo = stroke(R, 2 * GAP).united(R)
    return L.subtracted(halo).united(R).subtracted(holes)


def fitting(b: QRectF, box=SMALL_FIT[0], center=SMALL_FIT[1]) -> QTransform:
    """把包围盒 b 那么大的东西整个缩放进 box、摆在 center 的变换（fit 用的就是它）。"""
    k = min(box[0] / b.width(), box[1] / b.height())
    return QTransform().translate(*center).scale(k, k).translate(-b.center().x(), -b.center().y())


def fit(path, box=SMALL_FIT[0], center=SMALL_FIT[1]) -> QPainterPath:
    """整个缩放进 box 那么大、摆在 center。"""
    return fitting(path.boundingRect(), box, center).map(path)


def dog_body() -> QPainterPath:
    """狗（D）的身子，眼睛、鼻子还没挖。左上一只耷拉的耳朵贴着左边垂下来（缝只在里侧，左上角不留细尖角）。"""
    D = d_round()
    top = QPainterPath()
    top.addRect(QRectF(150, 330, 400, 500))
    ear = blob((290, 450), 56, 124, 12).intersected(top)        # 耳朵尖只往外垂出一点点（垂多了 D 左边不直，像 O）
    fill = QPainterPath()
    fill.addRect(QRectF(150, 330, 140, 161))
    ear = ear.united(fill.intersected(D))                         # 耳朵上半截的外沿就是 D 的左边
    keep = QPainterPath()
    keep.addRect(QRectF(150, 352, 400, 500))                      # 缝只开在头顶以下（开到顶上，左上角会被切出一个小缺口）
    return D.subtracted(stroke(ear, 28).united(ear).intersected(keep)).united(ear)


def dog_face() -> QPainterPath:
    """狗脸上要挖的洞：两只实心白点眼睛、扁的倒三角鼻子（挨着眼睛，离远了像张着嘴）。"""
    return dots(DOG_EYES, DOG_EYE_R).united(soft(DOG_NOSE, 8))


def cat_m() -> tuple[QPainterPath, QPainterPath, QPainterPath]:
    """猫（M）：身子、眼睛、小三角鼻子。"""
    body, eyes = m_round()
    c = 566 + 125
    return body, eyes, soft([(c - 14, 574), (c + 14, 574), (c, 589)], 6)


def dog_cat() -> QPainterPath:
    R, eyes, nose = lean(d_round(), list(cat_m()), CAT_LEAN, overlap=CAT_OVERLAP)
    return assemble(dog_body(), R, dog_face().united(eyes).united(nose))


def pieces() -> dict:
    """拼好的猫狗拆成几块（1024 画布的坐标，还没 fit）：dog 狗露在外面的那块（猫和它外面那圈缝已经剪掉）、dog_face 狗脸上的洞、
    cat 猫、cat_face 猫脸上的洞、whole 拼好的整个（和 dog_cat 一样）。关于页的图、过渡动画里两根线描的轮廓都用这几块（widget/about_art.py）。"""
    body = dog_body()
    R, eyes, nose = lean(d_round(), list(cat_m()), CAT_LEAN, overlap=CAT_OVERLAP)
    halo = stroke(R, 2 * GAP).united(R)
    cat_face = eyes.united(nose)
    return dict(dog=body.subtracted(halo), dog_face=dog_face(), cat=R, cat_face=cat_face,
                whole=assemble(body, R, dog_face().united(cat_face)))


def gull_line(c, w=GULL_W, flap=0.0) -> QPainterPath:
    """海鸥的中线：小孩画的那种两道弯。flap：翅膀扇到哪（0 是图标上的样子；正的翅膀尖往上抬、弯变浅，负的往下压、弯变深）。"""
    x, y = c
    h = w / 2
    tip, bow = 14 - 30 * flap, -28 + 10 * flap
    p = QPainterPath(QPointF(x - h, y + tip))
    p.quadTo(x - h / 2, y + bow, x, y + 8)
    p.quadTo(x + h / 2, y + bow, x + h, y + tip)
    return p


def gull(c, w=GULL_W, lw=GULL_LW) -> QPainterPath:
    """天上飞的海鸥。"""
    return stroke(gull_line(c, w), lw)


def fish_parts(c, w=FISH_W) -> tuple[QPainterPath, QPainterPath, QPainterPath, QPointF]:
    """鱼拆开：身子、尾巴、眼睛（洞）、尾巴根（尾巴摆的时候绕它）。"""
    x, y = c
    body = blob((x, y), w * 0.34, w * 0.2, 0)
    tx = x - w * 0.28
    tail = soft([(tx, y), (tx - w * 0.26, y - w * 0.18), (tx - w * 0.26, y + w * 0.18)], 7)
    return body, tail, dots([(x + w * 0.16, y - w * 0.04)], w * 0.045), QPointF(tx, y)


def fish(c, w=FISH_W) -> QPainterPath:
    """水下游的鱼，头朝右；眼睛是个洞。"""
    body, tail, eye, _ = fish_parts(c, w)
    return body.united(tail).subtracted(eye)


def _quad_part(p0, p1, p2, u0, u1) -> tuple:
    """二次曲线 p0 p1 p2 上 u0 到 u1 那一截（还是一段二次曲线）：起点、控制点、终点。"""
    def at(u):
        a, b, c = (1 - u) * (1 - u), 2 * u * (1 - u), u * u
        return QPointF(a * p0.x() + b * p1.x() + c * p2.x(), a * p0.y() + b * p1.y() + c * p2.y())
    q0 = at(u0)
    d = (u1 - u0) * (1 - u0), (u1 - u0) * u0                      # 半个导数：(1-u)(p1-p0) + u(p2-p1)，乘 u1-u0
    q1 = QPointF(q0.x() + d[0] * (p1.x() - p0.x()) + d[1] * (p2.x() - p1.x()),
                 q0.y() + d[0] * (p1.y() - p0.y()) + d[1] * (p2.y() - p1.y()))
    return q0, q1, at(u1)


def wave_line(y=WAVE_Y, x0=WAVE_X[0], x1=WAVE_X[1], reach=1.0) -> QPainterPath:
    """水线的中线：六段缓缓的弯。reach < 1 只要正中那一截（从中间往两头长出来，弯的样子不变）。"""
    n, a = 6, 9
    step = (x1 - x0) / n
    if reach >= 1.0:
        p = QPainterPath(QPointF(x0, y))
        for i in range(n):
            xa = x0 + step * i
            p.quadTo(xa + step / 2, y + (a if i % 2 else -a), xa + step, y)
        return p
    half = (x1 - x0) / 2 * max(0.0, reach)
    lo, hi = (x0 + x1) / 2 - half, (x0 + x1) / 2 + half
    p = QPainterPath()
    for i in range(n):
        xa = x0 + step * i
        u0, u1 = max(0.0, (lo - xa) / step), min(1.0, (hi - xa) / step)
        if u1 <= u0:
            continue
        q0, q1, q2 = _quad_part(QPointF(xa, y), QPointF(xa + step / 2, y + (a if i % 2 else -a)), QPointF(xa + step, y), u0, u1)
        if p.elementCount() == 0:
            p.moveTo(q0)
        p.quadTo(q1, q2)
    return p


def wave(y=WAVE_Y, x0=WAVE_X[0], x1=WAVE_X[1], lw=WAVE_LW) -> QPainterPath:
    """猫狗脚下的一道水线。"""
    return stroke(wave_line(y, x0, x1), lw)


def small() -> QPainterPath:
    """只有猫狗（64 像素以下、菜单栏、设置卡片左上角的圆、名字胶囊）：小动物缩到这么小只剩一串点。"""
    return fit(dog_cat())


def scene() -> QPainterPath:
    """整张（128 像素以上：访达、Dock）：猫狗站在水边，天上一只海鸥、水下一条鱼。"""
    dm = fit(dog_cat(), box=SCENE_FIT[0], center=SCENE_FIT[1])
    return dm.united(gull(GULL_AT)).united(fish(FISH_AT)).united(wave(WAVE_Y))
