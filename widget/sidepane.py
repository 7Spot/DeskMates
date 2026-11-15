"""卡片右边的侧边面板（现在只有设置卡片的表盘 widget/dial.py 用：动作不单开窗口，从姿势行右边弹出来）。
open 时窗口先撑出面板的地方，面板再从贴着卡片的那一点放大出来（OutBack 小回弹），收回干脆（InCubic）；永远在右边：
右边出屏幕就整张卡片左移补齐；面板比主叶顶高出去的部分窗口往上长、主叶往下挪（卡片在屏幕上不动）；收完窗口缩回主叶、挪回原位。
面板自己要有：固定大小、set_progress(0..1)（自己画放大动画）、可选 overlap（和卡片叠多少）、centered（竖直对着卡片的 side_anchor_y）、
fit_to(主叶高度)（按卡片定自己的大小）。和卡片一个窗口，拖哪儿都是拖一张卡。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPoint, QVariantAnimation
from PySide6.QtWidgets import QApplication, QWidget

from widget.sticker import SHADOW

SIDE_OVERLAP, DROP_MS, FOLD_MS = 10, 450, 300   # 面板默认和主叶叠多少、弹出来要多久、收回去要多久


class SideDock:
    def __init__(self, card):
        self.card = card
        self.pane: Optional[QWidget] = None
        self.active = False                      # 从开始长到完全收起之间都算
        self.t = 0.0                             # 0 收着 … 1 全开
        self.dy = 0                              # 面板比主叶顶高出去多少：窗口往上长这么多、主叶往下挪这么多（卡片在屏幕上不动）
        self.shift = QPoint(0, 0)                # 打开时窗口挪了多少（右边放不下左移、顶出屏幕下移、顶上长出去上移），收回时挪回来
        self.main_w = 0                          # 主叶自己的宽（窗口撑宽时量高度用它）
        self.anim = QVariantAnimation(card)
        self.anim.setDuration(DROP_MS)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(lambda v: self._set_t(float(v)))
        self.anim.finished.connect(self._settled)

    def attach(self, pane: QWidget) -> None:
        self.pane = pane
        pane.setParent(self.card)
        pane.hide()

    def overlap(self) -> int:
        return int(getattr(self.pane, "overlap", SIDE_OVERLAP))

    def extent(self) -> tuple[int, int]:
        """面板要多少地方：(往右伸出主叶多少, 高)。没开着时先按主叶现在的高度定面板的大小（表盘直径按主页面高度）。"""
        if self.pane is None:
            return 0, 0
        if hasattr(self.pane, "fit_to") and not self.active:
            self.pane.fit_to(self.card._main.height(), self.card.side_room())
        return self.pane.width() - self.overlap(), self.pane.height()

    def toggle(self, animated: bool = True) -> bool:
        """弹出 / 收回；返回这次是不是在弹出（正在收的途中再点就是弹出）。"""
        if self.active and (self.anim.state() != QVariantAnimation.Running or self.anim.endValue() == 1.0):
            self.close(animated)
            return False
        self.open(animated)
        return True

    def open(self, animated: bool = True) -> None:
        """面板弹出来（永远往右）：先把窗口撑到放得下它，再播放大动画。
        圆心对着锚点那一行：面板比主叶顶高出去的部分，窗口往上长、主叶往下挪，卡片在屏幕上不动；
        右边出屏幕就整张卡片左移补齐、顶出屏幕就下移；收回时挪回来（_settled）。"""
        card = self.card
        if self.pane is None:
            return
        if not self.active:
            extra, side_h = self.extent()                                          # 先按主叶现在的高度定面板大小
            self.active = True
            self.main_w = card.width() - 2 * SHADOW
            g = card.frameGeometry()
            screen = QApplication.screenAt(g.center()) or QApplication.primaryScreen()
            ag = screen.availableGeometry()
            self.dy = 0
            over_top = max(0, round(side_h / 2 - card.side_anchor_y()))            # 面板顶会高出窗口顶多少
            self.dy = over_top
            dx = -max(0, g.right() + extra - ag.right())                           # 右边放不下：左移
            dy = -over_top + max(0, ag.top() - (g.top() - over_top))               # 顶上长出去：上移（主叶不动）；顶出屏幕：再下移
            self.shift = QPoint(dx, dy)
            card.move(card.pos() + self.shift)
            self.apply_margins()
            card.setFixedWidth(2 * SHADOW + self.main_w + extra)
            card.fit_height()
            self.pane.raise_()
            self.t = 0.0
            self.pane.set_progress(0.0)
            self.pane.show()
        self._run(1.0, animated)

    def close(self, animated: bool = True) -> None:
        if self.pane is None or not self.active:
            return
        self._run(0.0, animated)

    def finish_now(self) -> None:
        """正在播的弹出 / 收回动画立刻走到头（单测用）。"""
        if self.anim.state() == QVariantAnimation.Running:
            end = float(self.anim.endValue())
            self.anim.stop()
            self._set_t(end)
            self._settled()

    def _run(self, target: float, animated: bool) -> None:
        self.anim.stop()
        if not animated:
            self._set_t(target)
            self._settled()
            return
        if target > self.t:                                # 弹出带一点回弹（回弹幅度小，别冲出面板留的边）
            curve = QEasingCurve(QEasingCurve.OutBack)
            curve.setOvershoot(0.8)
            self.anim.setDuration(DROP_MS)
        else:                                              # 收回干脆
            curve = QEasingCurve(QEasingCurve.InCubic)
            self.anim.setDuration(FOLD_MS)
        self.anim.setEasingCurve(curve)
        self.anim.setStartValue(self.t)
        self.anim.setEndValue(target)
        self.anim.start()

    def apply_margins(self) -> None:
        extra = (self.pane.width() - self.overlap()) if self.active else 0
        self.card._outer.setContentsMargins(SHADOW, SHADOW + self.dy, SHADOW + extra, SHADOW)

    def place(self) -> int:
        """把面板摆到主叶右边、圆心对着锚点那一行；返回它在窗口里的 y。"""
        x = SHADOW + self.main_w - self.overlap()
        y = max(0, round(self.card.side_anchor_y() - self.pane.height() / 2)) if getattr(self.pane, "centered", False) else SHADOW
        self.pane.move(x, y)
        return y

    def window_height(self, main_h: int, side_growth: int = 0) -> int:
        """主叶和侧叶共用窗口的占位高度；展开时可先给侧叶下移留空间，不改变主叶动画的目标。"""
        return max(main_h + self.dy, self.pane.y() + self.pane.height() + side_growth)

    def _set_t(self, t: float) -> None:
        self.t = t
        if self.pane is not None:
            self.pane.set_progress(max(0.0, t))
        self.card.update()

    def _settled(self) -> None:
        """动画走完：全收就把窗口缩回主叶、挪回打开前的位置（卡片在屏幕上还是原来那个地方）。"""
        card = self.card
        if self.pane is None or self.t > 0.0 or not self.active:
            return
        self.pane.hide()
        self.active = False
        self.dy = 0
        screen = QApplication.screenAt(card.frameGeometry().center()) or QApplication.primaryScreen()
        ag = screen.availableGeometry()
        back = card.pos() - self.shift
        self.shift = QPoint(0, 0)
        self.apply_margins()
        card.setFixedWidth(2 * SHADOW + self.main_w)
        card.move(min(back.x(), ag.right() - card.width() + SHADOW), back.y())   # 开着时被拖到右边去了：别挪出屏幕
        card.fit_height()
