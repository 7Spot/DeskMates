"""落地扬起的灰（狗屋这种重的扔下去，落地时脚下扬起一圈灰）。

一个只在落地那一刻出现的透明小窗口：点得穿、不接焦点、不切前台，和物件同一层（菜单栏上面，widget/things.py 摆）；不进空间（不挡狗、球）。
十几团软的灰贴着地往两边、往上散开，越散越大、越淡，约 0.7 秒没了就收起来。一帧一步（things.Things.update 叫 step），停着的时候什么都不做。
灰的颜色按深浅色外观各一份（浅色界面上偏暖的灰褐，深色界面上淡一点的灰）。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from widget import native, sticker

LIFE_S = (0.45, 0.8)       # 一团灰活多久（秒，随机）
SPEED_M = (0.5, 1.5)       # 往两边散开多快（米 / 秒，再乘落地多重）
RISE_M = (0.15, 0.6)       # 往上飘多快（米 / 秒）
SIZE_M = (0.035, 0.075)    # 一团多大（半径，米），散开时长到 GROW 倍
GROW = 2.6
DRAG = 3.2                 # 空气阻力（每秒速度剩 e^-DRAG）
ALPHA = 0.42               # 刚扬起来最浓多少
COUNT = (10, 22)           # 落地多重 0 → 1：几团


@dataclass
class _Puff:
    x: float
    y: float
    vx: float
    vy: float
    r0: float
    life: float
    age: float = 0.0


class DustCloud(QWidget):
    """扬起来的那一圈灰。burst 摆好、扬起来；step 每帧往前走，散完了自己收起来（返回 False）。"""

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
                         | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle("Dust")
        native.apply(self)
        self.puffs: list[_Puff] = []
        self.ppm = 1.0
        self._rng = random.Random(11)

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)
        native.set_level(self, native.LEVEL_THING[-1])   # 物件前一档那一层：盖在落地的物件前面、狗后面
        native.set_ignores_mouse(self, True)
        super().showEvent(event)

    def burst(self, x: float, floor: float, width: float, strength: float, ppm: float) -> None:
        """物件正中 x、落在 floor 这条线上（全局坐标）、物件宽 width（像素）、落地多重 strength（0～1）：扬起来。窗口按这一圈散得开的地方摆。"""
        strength = max(0.0, min(1.0, strength))
        rng, self.ppm = self._rng, ppm
        n = round(COUNT[0] + (COUNT[1] - COUNT[0]) * strength)
        reach = 0.5 * width + (SPEED_M[1] / DRAG + SIZE_M[1] * GROW) * ppm * (0.6 + 0.4 * strength)
        up = (RISE_M[1] / DRAG + SIZE_M[1] * GROW) * ppm + 6.0
        rect = QRect(math.floor(x - reach), math.floor(floor - up), math.ceil(2.0 * reach), math.ceil(up + SIZE_M[1] * ppm + 4.0))
        self.puffs = []
        for _ in range(n):
            u = rng.uniform(-1.0, 1.0)                              # 从物件底下哪一截冒出来（-1 左头，1 右头）
            side = 1.0 if u >= 0.0 else -1.0
            self.puffs.append(_Puff(x=x + u * 0.5 * width - rect.left(), y=floor - rect.top() - rng.uniform(0.0, 3.0),
                                    vx=side * rng.uniform(*SPEED_M) * ppm * (0.5 + 0.5 * strength) * (0.4 + 0.6 * abs(u)),
                                    vy=-rng.uniform(*RISE_M) * ppm * (0.5 + 0.5 * strength), r0=rng.uniform(*SIZE_M) * ppm,
                                    life=rng.uniform(*LIFE_S)))
        self.setGeometry(rect)
        if not self.isVisible():
            self.show()
        self.update()

    def step(self, dt: float) -> bool:
        """往前走 dt 秒；散完了收起来，返回还在不在。"""
        if not self.puffs:
            return False
        keep = math.exp(-DRAG * dt)
        for p in self.puffs:
            p.age += dt
            p.vx *= keep
            p.vy = p.vy * keep + 0.25 * self.ppm * dt               # 飘到顶慢慢往下沉一点
            p.x += p.vx * dt
            p.y += p.vy * dt
        self.puffs = [p for p in self.puffs if p.age < p.life]
        if not self.puffs:
            self.hide()
            return False
        self.update()
        return True

    def paintEvent(self, event) -> None:
        if not self.puffs:
            return
        dark = sticker.is_dark()
        base = QColor(200, 196, 188) if dark else QColor(150, 128, 102)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for puff in self.puffs:
            u = puff.age / puff.life
            r = puff.r0 * (1.0 + (GROW - 1.0) * (1.0 - (1.0 - u) ** 2))
            a = ALPHA * (1.0 - u) ** 1.6 * min(1.0, puff.age / 0.06)  # 一下扬起来，越散越淡
            if a <= 0.004:
                continue
            g = QRadialGradient(QPointF(puff.x, puff.y), r)
            c0, c1 = QColor(base), QColor(base)
            c0.setAlphaF(a)
            c1.setAlphaF(0.0)
            g.setColorAt(0.0, c0)
            g.setColorAt(1.0, c1)
            p.setBrush(g)
            p.drawEllipse(QPointF(puff.x, puff.y), r, r)
        p.end()
