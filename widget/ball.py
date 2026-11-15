"""灵动交互的球：一个只比球大一点的透明小窗口，跟着球在屏幕上飞（widget/playground.py 每帧摆）。

画法和狗嘴里的 3D 球（widget/props.py，render.py 的三渲二）一样：同一个红、两档明暗（光照方向、0.35 的分界、暗面 0.88 倍）、
同样粗的深色描边，所以狗叼起来 / 放下时两个换手看不出来。一直有一条浅色的缝线跟着滚过的角度转（花纹不要只在飞的时候有），
狗嘴里的 3D 球也有一样的花纹（props.ball_seam_mesh）。脚下的影子离地越高越小越淡，离地太高不画。
点击范围就是球（加一圈好点的余量）：每帧按鼠标在不在球上切窗口接不接鼠标（和狗一样，native.set_ignores_mouse），
别的地方点下去穿到后面。飞着的球点击范围跟着速度放大（飞着的球抓不住——一帧挪几十像素，点下去它已经过去了），
窗口也跟着放大装得下这一圈。按住拖、松手扔出去；只是点一下 duang 一下（squash，和狗一样，鼠标、触摸板都一样）。右键（触摸板两指点）：捡球开关。"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from widget import native
from widget.expression import PRESS_OMEGA, PRESS_ZETA, RELEASE_OMEGA, RELEASE_ZETA
from widget.hand import event_time
from widget.props import COLORS, SEAM_COLOR
from widget.render import ELEVATION, OUTLINE

INK = (0.16, 0.13, 0.11)            # 描边色（render.py 的 uMode == 1）
LIGHT = (-0.5, 1.0, 0.9)            # 光照方向（世界坐标，render.py 的 uLight）
BAND, DARK = 0.35, 0.88             # 两档明暗的分界和暗面倍数
PAD = 5                              # 球四周留的透明边（像素）
HIT_PAD = 7                          # 点击范围比球大这么多（像素）
CATCH_SECONDS = 0.06                 # 飞着的球：点击范围再放大它这么久飞过的距离
CATCH_MAX_R = 5.0                    # …最多放大到球半径的这么多倍再加 20 像素
SHADOW_ROOM_M = 0.45                 # 窗口往下留多高给影子（米）：球离地比这高就不画影子


class Squash:
    """球的 duang：按下压扁、松手弹回，和狗同一套弹簧（widget/expression.py）。物件落地压扁另调弹回来的快慢（things._impact）：
    omega_scale 弹簧的倍数（小了慢慢鼓回来），zeta_min 阻尼至少多少（1 = 不弹过头：软的垫子）。"""
    DEPTH = 0.18

    def __init__(self) -> None:
        self.value = self.v = 0.0
        self.pressing = False
        self.omega_scale, self.zeta_min = 1.0, 0.0

    def press(self) -> None:
        self.pressing = True

    def release(self) -> None:
        self.pressing = False

    def step(self, dt: float) -> None:
        if not self.pressing and abs(self.value) < 1e-4 and abs(self.v) < 1e-3:
            self.value = self.v = 0.0
            return
        if self.pressing:
            w, z, target = PRESS_OMEGA, PRESS_ZETA, self.DEPTH
        else:
            w, z, target = RELEASE_OMEGA * self.omega_scale, max(RELEASE_ZETA, self.zeta_min), 0.0
        n = max(1, math.ceil(dt * w / 0.25))
        h = dt / n
        for _ in range(n):
            self.v += (w * w * (target - self.value) - 2.0 * z * w * self.v) * h
            self.value += self.v * h


def catch_radius(r: float, speed: float) -> float:
    """点击范围的半径：静止时比球大 HIT_PAD，飞得越快越大（像素；speed 像素 / 秒）。"""
    return r + HIT_PAD + min(CATCH_SECONDS * speed, CATCH_MAX_R * r + 20.0)


@lru_cache(maxsize=8)
def ball_image(r: float, outline: float, dpr: float) -> QImage:
    """红球（含描边）的图，中心在图正中，2 × 2 超采样抗锯齿。只跟大小有关，算一次存着。"""
    e = math.radians(ELEVATION)
    lx, ly, lz = LIGHT
    ly, lz = ly * math.cos(e) - lz * math.sin(e), ly * math.sin(e) + lz * math.cos(e)   # 世界 → 相机（和 view_proj 一样绕 x 转俯视角）
    n = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / n, ly / n, lz / n
    R = r + outline
    size = int(math.ceil(2 * R * dpr)) + 2
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    base = COLORS["ball"]
    c = size / 2.0
    ss = 2
    for py in range(size):
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + 0.5) / ss - c) / dpr
                    y = (py + (sy + 0.5) / ss - c) / dpr
                    d2 = x * x + y * y
                    if d2 > R * R:
                        continue
                    if d2 > r * r:
                        col = INK
                    else:
                        nx, ny = x / r, -y / r
                        nz = math.sqrt(max(0.0, 1.0 - nx * nx - ny * ny))
                        band = 1.0 if nx * lx + ny * ly + nz * lz > BAND else DARK
                        col = (base[0] * band, base[1] * band, base[2] * band)
                    acc[0] += col[0]
                    acc[1] += col[1]
                    acc[2] += col[2]
                    acc[3] += 1.0
            a = acc[3] / (ss * ss)
            if a > 0:
                k = 1.0 / (ss * ss)
                img.setPixelColor(px, py, QColor.fromRgbF(min(1.0, acc[0] * k), min(1.0, acc[1] * k), min(1.0, acc[2] * k), a))
    img.setDevicePixelRatio(dpr)
    return img


class BallWindow(QWidget):
    """只管画和收鼠标；球在哪、怎么动由 playground 管（sync 每帧给位置）。"""

    def __init__(self, host):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.host = host
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("Ball")
        native.apply(self)
        self.r = 10.0
        self.ppm = 240.0
        self.center = QPointF(0, 0)          # 球心在窗口里的位置（含亚像素）
        self.floor: Optional[float] = None   # 地面在窗口里的 y（画影子）；None = 太远不画
        self.spin = 0.0
        self.squash = 0.0                    # duang：压扁多少（负的是弹过头拉长）
        self.alpha = 1.0
        self.catch = self.r + HIT_PAD        # 点击范围的半径（飞着时放大）
        self._accepting: Optional[bool] = None
        self._pressed = False
        self._painted: Optional[tuple] = None   # 上次画的时候长什么样（sync：没变就不重画）

    # ---- 摆放 ----
    def sync(self, x: float, y: float, r: float, ppm: float, floor_y: Optional[float], spin: float,
             speed: float = 0.0) -> None:
        """球心在全局 (x, y)、半径 r；floor_y 是球正下方那条线（画影子）；speed 是球现在多快（像素 / 秒，点击范围跟着放大）。"""
        self.r, self.ppm, self.spin = r, ppm, spin
        self.catch = catch_radius(r, speed)
        side = max(r + OUTLINE * ppm + PAD, self.catch + 2)
        room = SHADOW_ROOM_M * ppm
        w = int(math.ceil(2 * side)) + 2
        h = int(math.ceil(side + max(side, room))) + 2
        left, top = int(math.floor(x - side)), int(math.floor(y - side))
        self.center = QPointF(x - left, y - top)
        self.floor = (floor_y - top) if (floor_y is not None and 0 <= floor_y - top <= h) else None
        if (self.width(), self.height()) != (w, h):
            self.setGeometry(left, top, w, h)
        elif (self.x(), self.y()) != (left, top):
            self.move(left, top)
        look = (w, h, self.center.x(), self.center.y(), self.floor, r, ppm, spin, self.squash, self.alpha)
        if look != self._painted:                # 球不动就不重画；窗口挪了、长相没变也不用
            self._painted = look
            self.update()

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)
        native.set_no_activate(self)         # 点球不把程序切到前台（native.set_no_activate）
        native.set_level(self, native.LEVEL_BALL)   # 在狗、窝沿前面（地上的、飞着的球都盖在狗上面）
        self._accepting = None
        super().showEvent(event)

    # ---- 点击范围就是球 ----
    def update_hit(self, cursor_global) -> bool:
        """每帧：鼠标在球上（加 HIT_PAD，飞着时更大）才接鼠标；按着的时候一直接（拖到一半别脱手）。返回鼠标在不在球上。"""
        local = self.mapFromGlobal(cursor_global)
        over = math.hypot(local.x() - self.center.x(), local.y() - self.center.y()) <= self.catch
        accept = (over or self._pressed) and self.isVisible() and self.alpha > 0.5
        if accept != self._accepting and native.set_ignores_mouse(self, not accept):
            self._accepting = accept
        if over and accept:
            self.setCursor(Qt.ClosedHandCursor if self._pressed else Qt.OpenHandCursor)
        return over

    # ---- 鼠标 ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.setCursor(Qt.ClosedHandCursor)
            self.host.ball_press(event.globalPosition(), event_time(event))
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._pressed:
            self.host.ball_drag(event.globalPosition(), event_time(event))
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._pressed and event.button() == Qt.LeftButton:
            self._pressed = False
            self.setCursor(Qt.OpenHandCursor)
            self.host.ball_release(event.globalPosition(), event_time(event))
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.mousePressEvent(event)          # 连点：第二下照样当按下（扔完马上又抓）

    def contextMenuEvent(self, event) -> None:
        self.host.w.show_ball_menu(event.globalPos())   # 右键球：捡球开关
        event.accept()

    # ---- 画 ----
    def paintEvent(self, event) -> None:
        if self.alpha <= 0.0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self.alpha)
        c, r = self.center, self.r
        if self.floor is not None:
            lift = max(0.0, (self.floor - (c.y() + r)) / self.ppm)
            k = 1.0 / (1.0 + 3.0 * lift)
            a = 0.30 / (1.0 + 5.0 * lift)
            rx, ry = r * 1.05 * k, max(1.5, r * 0.34 * k)
            g = QRadialGradient(QPointF(c.x(), self.floor), rx)
            g.setColorAt(0.0, QColor(28, 24, 22, int(255 * a)))
            g.setColorAt(1.0, QColor(28, 24, 22, 0))
            p.save()
            p.translate(c.x(), self.floor)
            p.scale(1.0, ry / rx)
            p.translate(-c.x(), -self.floor)
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(c.x(), self.floor), rx, rx)
            p.restore()
        if abs(self.squash) > 1e-3:                            # duang：贴着底边竖直压扁，横向鼓一点
            p.translate(c.x(), c.y() + r)
            p.scale(1.0 + self.squash * 0.5, 1.0 - self.squash)
            p.translate(-c.x(), -(c.y() + r))
        img = ball_image(round(r, 1), round(OUTLINE * self.ppm, 2), self.devicePixelRatioF())
        s = img.width() / img.devicePixelRatio()
        p.drawImage(QRectF(c.x() - s / 2, c.y() - s / 2, s, s), img)
        clip = QPainterPath()                                  # 缝线：一道 S 形的浅色弧，跟着滚过的角度转
        clip.addEllipse(c, r * 0.97, r * 0.97)
        p.setClipPath(clip)
        p.translate(c)
        p.rotate(math.degrees(self.spin))
        path = QPainterPath(QPointF(-r * 1.1, -r * 0.25))
        path.cubicTo(QPointF(-r * 0.35, r * 0.95), QPointF(r * 0.35, -r * 0.95), QPointF(r * 1.1, r * 0.25))
        pen = QPen(QColor.fromRgbF(*SEAM_COLOR, 0.86), max(1.2, r * 0.13))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()
