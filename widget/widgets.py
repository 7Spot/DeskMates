"""贴纸风的控件（和狗、「···」同一套画法，见 widget/sticker.py）：开关、圆形图标按钮、行里的小图标、长按按钮、大小滑块、毛色色块、
悬浮提示、缝线分隔线，和画爪印 / 骨头 / 图标的函数。颜色都在画的时候从 sticker 读，深色模式下一帧就换。"""
from __future__ import annotations

import math
import time
from typing import Optional

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTextBoundaryFinder, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QAbstractButton, QApplication, QFrame, QGraphicsOpacityEffect, QPushButton, QSizePolicy, QWidget

from widget import native, sounds, sticker
from widget.animation import FrameClock, Spring
from widget.capture_ui import ui_frozen
from widget.motion import MOTION_PAD, MotionMixin
from widget.pointer import PointerDrag

HOLD_MS, HOLD_UNWIND_MS = 600, 150            # 长按触发（重置 / 退出 / 关机键，防误触；到点就触发、圈同时退回不等松手）；提前松开进度线多快退回


def draw_paw(p: QPainter, center: QPointF, size: float, color: QColor) -> None:
    """一个爪印（肉垫 + 四个趾），size 是整体边长。开关钮上用。"""
    k = size / 22.0
    p.save()
    p.translate(center.x() - 11.0 * k, center.y() - 11.0 * k)
    p.scale(k, k)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(5.5, 10.0, 11.0, 9.0))
    for cx, cy, r in ((4.0, 7.4, 2.3), (8.4, 3.9, 2.5), (13.6, 3.9, 2.5), (18.0, 7.4, 2.3)):
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
    p.restore()


def draw_icon(p: QPainter, kind: str, center: QPointF, size: float, ink: QColor, fill: QColor) -> None:
    """菜单里的图标（菜单不要文字）：gear 齿轮 = 设置，controller 手柄 = 动作控制，power 关机键 = 退出。
    都是描边线稿，size 是整体边长。"""
    k = size / 20.0
    cx, cy = center.x(), center.y()
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if kind == "gear":
        path = QPainterPath()
        path.addEllipse(center, 6.0 * k, 6.0 * k)
        for i in range(8):
            tooth = QPainterPath()
            tooth.addRoundedRect(QRectF(-1.6 * k, -8.4 * k, 3.2 * k, 3.6 * k), 0.8 * k, 0.8 * k)
            tr = QTransform().translate(cx, cy).rotate(i * 45.0)
            path.addPath(tr.map(tooth))
        p.setPen(QPen(ink, 1.6))
        p.setBrush(fill)
        p.drawPath(path.simplified())
        p.drawEllipse(center, 2.3 * k, 2.3 * k)
    elif kind == "controller":
        p.setPen(QPen(ink, 1.6))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(cx - 9.0 * k, cy - 5.5 * k, 18.0 * k, 11.0 * k), 4.0 * k, 4.0 * k)
        p.setPen(QPen(ink, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx - 6.6 * k, cy), QPointF(cx - 2.6 * k, cy))             # 十字键
        p.drawLine(QPointF(cx - 4.6 * k, cy - 2.0 * k), QPointF(cx - 4.6 * k, cy + 2.0 * k))
        p.setPen(Qt.NoPen)
        p.setBrush(ink)
        p.drawEllipse(QPointF(cx + 3.4 * k, cy - 1.3 * k), 1.2 * k, 1.2 * k)       # 两个键
        p.drawEllipse(QPointF(cx + 6.0 * k, cy + 0.9 * k), 1.2 * k, 1.2 * k)
    elif kind == "power":
        p.setPen(QPen(ink, 2.0, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - 6.5 * k, cy - 6.0 * k, 13.0 * k, 13.0 * k), 125 * 16, 290 * 16)
        p.drawLine(QPointF(cx, cy - 8.0 * k), QPointF(cx, cy - 1.0 * k))
    elif kind == "tune":                                           # 调节：三根横线各带一个小圆点（行里"这一项还能调"的入口）
        p.setPen(QPen(ink, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(ink)
        for dy, kx in ((-5.5, -2.5), (0.0, 3.0), (5.5, -4.0)):
            p.drawLine(QPointF(cx - 8.0 * k, cy + dy * k), QPointF(cx + 8.0 * k, cy + dy * k))
            p.drawEllipse(QPointF(cx + kx * k, cy + dy * k), 2.2 * k, 2.2 * k)
    elif kind in ("back", "forward"):                              # 几何居中的左右chevron，不依赖字体字面框
        p.setPen(QPen(ink, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        direction = 1.0 if kind == "forward" else -1.0
        path = QPainterPath(QPointF(cx - direction * 3.0 * k, cy - 6.0 * k))
        path.lineTo(QPointF(cx + direction * 3.0 * k, cy))
        path.lineTo(QPointF(cx - direction * 3.0 * k, cy + 6.0 * k))
        p.drawPath(path)
    elif kind == "reset":
        p.setPen(QPen(ink, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        # 正角沿逆时针走到左上方；箭头接在终点，沿切线朝左下方。
        p.drawArc(QRectF(cx - 6 * k, cy - 6 * k, 12 * k, 12 * k), 210 * 16, 285 * 16)
        tip = QPointF(cx - math.sqrt(18) * k, cy - math.sqrt(18) * k)
        path = QPainterPath(tip + QPointF(0, -3 * k))
        path.lineTo(tip)
        path.lineTo(tip + QPointF(3 * k, 0))
        p.drawPath(path)
    elif kind == "close":                                          # × 关闭（卡片右上角：和返回一样的描边圆，同一支笔）
        p.setPen(QPen(ink, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        d = 4.6 * k
        p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
        p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))
    p.restore()


class HoldDriver(QObject):
    """长按驱动（防误触）：按下开始计时、进度 0 → 1 走 HOLD_MS 毫秒，满了发 held 并立刻退回（不等松手）；提前松开进度快速退回。
    HoldButton / IconButton 用它，自己只管画进度线。"""
    held = Signal()
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self._t0 = 0.0
        self._down = False
        self._fired = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        if isinstance(parent, QAbstractButton):
            parent.pressed.connect(self.press)
            parent.released.connect(self.release)

    def press(self) -> None:
        if ui_frozen():
            return
        self._down, self._fired, self._t0 = True, False, time.perf_counter()
        self._timer.start()

    def release(self) -> None:
        self._down = False
        if not self._timer.isActive():
            self._timer.start()

    def cancel(self) -> None:
        """隐藏 / 禁用 / 失去抓取时立即停下，隐藏的按钮不能继续计时或触发动作。"""
        self._down = self._fired = False
        self.progress = 0.0
        self._timer.stop()
        self.changed.emit()

    def _tick(self) -> None:
        if ui_frozen():
            self._down = False
            self._timer.stop()
            return
        if self._down:
            self.progress = min(1.0, (time.perf_counter() - self._t0) * 1000.0 / HOLD_MS)
            self.changed.emit()
            if self.progress >= 1.0 and not self._fired:
                self._fired, self._down = True, False         # 到点就触发，圈同时退回、不等松手；按着不放不会再触发
                sounds.play("complete")
                self.held.emit()
        else:
            self.progress = max(0.0, self.progress - 16.0 / HOLD_UNWIND_MS)
            if self.progress <= 0.0:
                self._timer.stop()
            self.changed.emit()


PILL_H = 26                                    # 所有胶囊按钮的高 = 开关的高；圆角 13 正好是一半，两头整圆
TIGHT_CSS = "QPushButton { font-size: 11px; }"  # 一行挤的小胶囊（主页面动作行、看细节那一块的站 / 坐 / 趴）：英文 Stand / Sit / Lie / Sleep 用普通胶囊会溢出卡片
NAME_MAX = 32                                  # 狗的名字最多 32 个字（一个表情算一个字；别按 Qt 的码元数算：一个表情占 2 到 11 个）


# ---------------- 动画节拍和弹出 / 收起的零件（开关、弹出来的行、菜单、提示） ----------------

def drive(widget: QWidget, animator) -> bool:
    """把 animator（有 tick(dt)，返回下一帧还要不要接着算）挂到 widget 所在卡片的节拍上（Card.run_animator）。挂不上——不在卡片里、
    卡片或这一块没显示、卡片正在打开那一下对齐设置（Card.still）、系统开了「减少动态效果」——返回 False，调用的直接到位。"""
    top = widget.window()
    run = getattr(top, "run_animator", None)
    parent = widget.parentWidget()
    shown = widget.isVisible() or (parent is not None and parent.isVisible())
    if run is None or not shown or native.reduce_motion():
        return False
    return run(animator)


def ease_out(u: float) -> float:
    """三次方缓出：起步快、到头慢（0..1）。"""
    u = max(0.0, min(1.0, u))
    return 1.0 - (1.0 - u) ** 3


def ease_in(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * u


def bounce(t: float, response: float = 0.25, damping: float = 0.55) -> float:
    """带回弹的弹簧从 0 走向 1（欠阻尼，解析解）：damping 0.55 冲过头约 13%、回来一次就停（菜单弹出来用：带回弹）。"""
    w = 2.0 * math.pi / response
    wd = w * math.sqrt(1.0 - damping * damping)
    return 1.0 - math.exp(-damping * w * t) * (math.cos(wd * t) + damping * w / wd * math.sin(wd * t))


class Fader:
    """行里一个小控件的出现 / 消失（鼠标跟随的调节图标、眼睛的「默认」）：0.15 秒淡入淡出，淡完才真的藏起来。
    它在行里挨着别的控件、旁边的字左对齐，出现消失不挪别人，所以只淡不挪。"""
    S = 0.15

    def __init__(self, widget: QWidget):
        self.widget = widget
        self.on = not widget.isHidden()
        self.alpha = 1.0 if self.on else 0.0
        self._fx: Optional[QGraphicsOpacityEffect] = None

    def set(self, on: bool, animated: bool = True) -> None:
        if on == self.on:
            return
        self.on = on
        if on:
            self.widget.setVisible(True)
        if animated and drive(self.widget, self):
            self._effect().setOpacity(self.alpha)
        else:
            self.alpha = 1.0 if on else 0.0
            self._done()

    def tick(self, dt: float) -> bool:
        target = 1.0 if self.on else 0.0
        step = dt / self.S
        self.alpha = min(target, self.alpha + step) if target > self.alpha else max(target, self.alpha - step)
        if self.alpha == target:
            self._done()
            return False
        self._effect().setOpacity(self.alpha)
        return True

    def _effect(self) -> QGraphicsOpacityEffect:
        if self._fx is None:
            self._fx = QGraphicsOpacityEffect(self.widget)
            self.widget.setGraphicsEffect(self._fx)
        return self._fx

    def _done(self) -> None:
        if self._fx is not None:
            self.widget.setGraphicsEffect(None)   # 淡完去掉（开着效果时整块先画进一张图再贴，平时用不着）
            self._fx = None
        self.widget.setVisible(self.on)


class Collapse(QWidget):
    """能展开 / 收起的一块（动作行、鼠标跟随的子行、演示那一段）。展开：高度从 0 用弹簧长到原高，下面的行跟着往下滑，卡片底边跟着
    （卡片的高度过渡是同一种弹簧、同一个节拍，同时开始，所以对得上），高度过了一半才淡入；收起反过来：前一半就淡没了，高度收到 0 再藏起来。
    它上面那条行间距（pad）算在它自己里面，所以从 0 长起不会先跳一下：放进页里用 stack()，行间距由 stack 加，碰到 Collapse 不加。
    里面的内容按原高排好、顶部对齐，露出多少裁多少。卡片没显示、系统开了「减少动态效果」：直接到位。"""

    def __init__(self, content: QWidget, open: bool = True, pad: int = 10):
        super().__init__()
        self.content, self.pad = content, pad
        content.setParent(self)
        content.move(0, pad)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._open = bool(open)
        self._h = Spring(0.0, 0.3)
        self._anim = False
        self._fx: Optional[QGraphicsOpacityEffect] = None
        content.setVisible(self._open)
        self.setVisible(self._open)

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def animating(self) -> bool:
        return self._anim

    def _width(self) -> int:
        parent = self.parentWidget()
        return max(1, parent.width() if parent is not None and parent.width() > 0 else self.width())

    def natural(self, width: Optional[int] = None) -> int:
        """展开时多高：上面的行间距 + 内容按这个宽排出来的高（英文的子行会折两行）。"""
        w = width or self._width()
        c = self.content
        h = c.heightForWidth(w) if c.hasHeightForWidth() else -1
        return self.pad + (h if h >= 0 else c.sizeHint().height())

    def pending(self) -> float:
        """还差多少到最后的高度（卡片量最后的高度时加上它）。"""
        return (self._h.target - self._h.value) if self._anim else 0.0

    def sizeHint(self) -> QSize:
        h = round(self._h.value) if self._anim else (self.natural() if self._open else 0)
        return QSize(self.content.sizeHint().width(), h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hasHeightForWidth(self) -> bool:
        return self._open and not self._anim

    def heightForWidth(self, width: int) -> int:
        return self.natural(width) if self._open else 0

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def _place(self) -> None:
        w = max(1, self.width())
        self.content.setGeometry(0, self.pad, w, self.natural(w) - self.pad)

    def event(self, event) -> bool:
        if event.type() == QEvent.LayoutRequest:          # 里面的内容变了尺寸（胶囊统一成 26 高、换行）：它自己没有布局，要自己往外报，不然外面那页按旧高度排
            self._place()
            self.updateGeometry()
        return super().event(event)

    def set_open(self, on: bool, animated: bool = True) -> None:
        if on == self._open:
            return
        self._open = on
        if not self._anim:
            self._h.value, self._h.velocity = (0.0 if on else float(self.natural())), 0.0
        self._h.set_target(float(self.natural()) if on else 0.0)
        self._anim = bool(animated and drive(self, self))    # 先立起「动画中、现在 0 高」再显示：第一次排版就是 0 高，下面的行不先按原高跳一下
        if on:
            self.content.setVisible(True)
            self.setVisible(True)
        if self._anim:
            self._apply()
        else:
            self._h.set_target(self._h.target, instant=True)
            self._finish()

    def tick(self, dt: float) -> bool:
        self._h.step(dt)
        if self._h.settled:
            self._finish()
            return False
        self._apply()
        return True

    def finish_now(self) -> None:
        if self._anim:
            self._h.set_target(self._h.target, instant=True)
            self._finish()

    def _apply(self) -> None:
        full = max(1.0, float(self.natural()))
        alpha = max(0.0, min(1.0, (self._h.value / full - 0.5) / 0.5))     # 高度过了一半才显出来；收起时前一半就淡没了
        if self._fx is None:
            self._fx = QGraphicsOpacityEffect(self.content)
            self.content.setGraphicsEffect(self._fx)
        self._fx.setOpacity(alpha)
        self.updateGeometry()

    def _finish(self) -> None:
        self._anim = False
        if self._fx is not None:
            self.content.setGraphicsEffect(None)
            self._fx = None
        if not self._open:
            self.setVisible(False)
            self.content.setVisible(False)
        self.updateGeometry()


def stack(layout, items: list, spacing: int = 10, gap: Optional[int] = None) -> None:
    """一页的行从上往下排，行和行之间空 gap（不给就是 spacing），分隔线上下空 spacing（线本身就把两块隔开了）；
    Collapse 自己带着它上面那条间距（从 0 长起不跳），碰到它不加。
    layout 的 spacing 要是 0；items 里可以是控件或布局。没自己设间距的那几行（语言、大小、最后一行）本来继承页面的间距，
    页面改成 0 以后它们里面的胶囊会贴在一起，这里给它们补回 spacing。"""
    gap = spacing if gap is None else gap
    prev = None
    for item in items:
        if prev is not None and not isinstance(item, Collapse):
            layout.addSpacing(spacing if is_hairline(item) or is_hairline(prev) else gap)
        if isinstance(item, QWidget):
            layout.addWidget(item)
        else:
            if item.spacing() < 0:
                item.setSpacing(spacing)
            layout.addLayout(item)
        prev = item


def is_hairline(item) -> bool:
    return isinstance(item, QFrame) and bool(item.property("hairline"))


class MotionButton(MotionMixin, QPushButton):
    """单路径手绘；字体由QSS定义，尺寸和外观各有唯一来源。"""
    MOTION_COLOR = "button"

    def __init__(self, *args, symbol: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbol = symbol
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        self.ensurePolished()
        body_height = 42 if self.property("big") else PILL_H
        padding = self.property("horizontalPadding")
        padding = int(padding) if padding is not None else (8 if self.property("quiet") else 12)
        width = QFontMetrics(self.font()).horizontalAdvance(self.text())
        if not self.icon().isNull():
            width = max(width, self.iconSize().width())
        body_width = max(body_height, width + 2 * padding + 4)
        return QSize(body_width + 2 * MOTION_PAD, body_height + 2 * MOTION_PAD)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def surface_colors(self):
        t = getattr(self.window(), "theme", None) or sticker.theme()
        border, fg = QColor(sticker.INK), QColor(t.text)
        width = float(sticker.OUTLINE)
        hover = self.motion.hover_amount
        bg = sticker.mix(QColor(t.btn), QColor(t.btn_hover), hover)
        selected_bg, selected_fg = QColor(t.accent), QColor(t.accent_text)
        if self.property("quiet"):
            bg = QColor(t.btn)
            bg.setAlphaF(hover)
            border.setAlphaF(hover)
            fg = sticker.mix(QColor(t.muted), fg, hover)
        if self.property("kind") == "primary":
            bg, fg = QColor(t.accent), QColor(t.accent_text)
        elif self.property("kind") == "danger":
            border = fg = QColor(sticker.DANGER)
        if self.property("tone") == "blue":
            fg = QColor(sticker.blue())
            border = sticker.mix(border, fg, hover)
        if self.property("surfaceColor"):
            color = QColor(self.property("surfaceColor"))
            bg = sticker.mix(color, color.lighter(112), hover)
            fg = QColor("white")
            selected_bg, selected_fg = QColor(sticker.INK), QColor(sticker.PAPER)
        selected = min(1.0, max(0.0, self.motion.selection.value)) if self.motion.selection is not None else 0.0
        semantic_color = getattr(self, "color", "")
        if self.property("tile"):
            bg, width = QColor(sticker.PAPER), 2.0 + 2.0 * selected
        elif semantic_color:
            bg = QColor(semantic_color)
        elif self.isCheckable():
            # 预览、提交只走这一条颜色进度，不再叠加按压反色。
            bg, fg = sticker.mix(bg, selected_bg, selected), sticker.mix(fg, selected_fg, selected)
        elif self.motion.press_amount > 0:
            bg = sticker.mix(bg, sticker.contrast_color(bg), self.motion.press_amount)
            fg = sticker.contrast_color(bg)
            border = QColor(sticker.INK)
        if not self.isEnabled():
            bg, border, fg = QColor(Qt.transparent), QColor(t.muted), QColor(t.muted)
        return bg, border, fg, width

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        bg, border, fg, width = self.surface_colors()
        r = self.motion.content_rect().adjusted(width / 2, width / 2, -width / 2, -width / 2)
        radius = 8.0 if self.property("tile") else r.height() / 2
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        p.setPen(QPen(border, width))
        p.setBrush(bg)
        p.drawPath(path)
        self.paint_content(p, r, fg)

    def paint_content(self, p, r, fg) -> None:
        """内容可独立换字；外框和填色始终由paintEvent画一次。"""
        if self.symbol is not None:
            draw_icon(p, self.symbol, self.motion.content_rect().center(), 14.0, fg, fg)
        elif self.icon().isNull():
            self.motion.draw_text(p, self.text(), fg)
        else:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            size = self.iconSize()
            pm = self.icon().pixmap(size, self.devicePixelRatioF(), QIcon.Normal if self.isEnabled() else QIcon.Disabled)
            target = QRectF(0, 0, size.width(), size.height())
            target.moveCenter(r.center())
            p.drawPixmap(target, pm, QRectF(pm.rect()))


class SelectPill(MotionButton):
    """可选胶囊与普通按钮共用唯一选中进度，按压预览与提交连续。"""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)

    @property
    def _sel(self):
        return self.motion.selection.value


# ---------------- 会动的字（标题行的名字胶囊、新版本胶囊） ----------------

def _glide(t: float, distance: float, speed: float, ease: float) -> tuple[float, bool]:
    """匀速滚 distance 像素，起步和停下各用 ease 秒加速、减速（梯形速度曲线；太短就是三角形）。返回 (位置, 到头没有)。"""
    if distance <= speed * ease:
        ease = math.sqrt(distance * ease / speed)
        top = distance / ease
    else:
        top = speed
    acc = top / ease
    total = distance / top + ease
    if t >= total:
        return distance, True
    if t < ease:
        return 0.5 * acc * t * t, False
    if t > total - ease:
        r = total - t
        return distance - 0.5 * acc * r * r, False
    return 0.5 * acc * ease * ease + top * (t - ease), False


class Marquee:
    """放不下的一行字自己往左滚，参数取 Android 系统跑马灯的默认值：停 1.2 秒 → 每秒 30 像素往左（起步、停下各 0.25 秒缓冲）→
    到头停 1.2 秒 → 0.3 秒淡出、回到开头、淡入；一共 3 遍，停在开头；replay() 再来 3 遍（鼠标移上去）。
    这里只算一个数（offset，往左滚了多少像素）和整体浓淡 alpha，画法交给 draw_strip：两头的省略号跟着位置连续变深浅，所以不跳。
    被打断（字窗变宽变窄、字变了）不跳回开头：interrupt() 用弹簧滑回去，停稳了再重新等 1.2 秒。"""
    DELAY, SPEED, EASE, PAUSE, FADE, ROUNDS = 1.2, 30.0, 0.25, 1.2, 0.3, 3

    def __init__(self):
        self.offset, self.alpha = 0.0, 1.0
        self.phase, self.t, self.rounds = "wait", 0.0, 0
        self._back = Spring(0.0, 0.3)

    def replay(self) -> None:
        self.rounds = 0
        if self.phase == "rest":
            self.phase, self.t = "wait", 0.0

    def interrupt(self) -> None:
        """字窗变了：正在滚的平滑滑回开头；没在滚的重新等 1.2 秒（3 遍重新算）。正在淡出淡入（一遍滚完回开头那 0.3 秒）的让它淡完：
        它本来就是回开头、淡回全浓，半路把浓淡改回 1 字会闪一下（新版本胶囊被名字挤窄时碰上过）。"""
        self.rounds = 0
        if self.phase in ("back", "fade"):
            return
        self.alpha = 1.0
        if self.offset > 0.5:
            self._back.value, self._back.velocity = self.offset, 0.0
            self._back.set_target(0.0)
            self.phase, self.t = "back", 0.0
        else:
            self.offset = 0.0
            self.phase, self.t = "wait", 0.0

    def step(self, dt: float, distance: float, enabled: bool = True) -> bool:
        """推进 dt 秒。distance = 要滚多远（字宽 − 字窗宽，≤ 0 就是放得下）。返回下一帧还要不要接着算。"""
        distance = max(0.0, distance)
        if self.phase == "back":
            self._back.step(dt)
            self.offset = max(0.0, min(self._back.value, distance))
            if self._back.settled or self.offset <= 0.0:
                self.offset, self.phase, self.t = 0.0, "wait", 0.0
            return True
        if distance <= 0.5 or not enabled:
            self.offset, self.alpha = 0.0, 1.0
            if self.phase != "rest":
                self.phase, self.t = "wait", 0.0
            return False
        self.t += dt
        if self.phase == "wait":
            if self.rounds >= self.ROUNDS:
                self.phase = "rest"
                return False
            if self.t >= self.DELAY:
                self.phase, self.t = "scroll", 0.0
            return True
        if self.phase == "scroll":
            self.offset, done = _glide(self.t, distance, self.SPEED, self.EASE)
            if done:
                self.phase, self.t = "pause", 0.0
            return True
        if self.phase == "pause":
            self.offset = distance
            if self.t >= self.PAUSE:
                self.phase, self.t = "fade", 0.0
            return True
        if self.phase == "fade":
            u = self.t / self.FADE
            if u < 0.5:
                self.offset, self.alpha = distance, 1.0 - 2.0 * u
            else:
                self.offset, self.alpha = 0.0, min(1.0, 2.0 * u - 1.0)
            if u >= 1.0:
                self.alpha, self.rounds = 1.0, self.rounds + 1
                self.phase, self.t = "wait", 0.0
            return True
        return False


ELLIPSIS_RAMP = 12.0                             # 省略号从没有到全有要走多少像素（约一个字宽）：开始滚时左边的、快到头时右边的都在这段里连续变
ELLIPSIS_FADE = 6.0                              # 字在省略号前面淡出的那一小段


def ellipsis_strength(offset: float, distance: float) -> tuple[float, float]:
    """左、右两个省略号的浓淡（0..1），只跟位置有关：左边 = 滚了多远，右边 = 还剩多远；放得下（distance ≤ 0）两边都没有。"""
    distance = max(0.0, distance)
    s = max(0.0, min(offset, distance))
    return min(1.0, s / ELLIPSIS_RAMP), min(1.0, (distance - s) / ELLIPSIS_RAMP)


_strip_cache: dict = {}


def _text_image(text: str, font: QFont, color: QColor, dpr: float) -> QImage:
    """整句字先画成一张图（按设备像素），滚动时只是平移这张图，小数位置用平滑采样，1 倍屏上也不一格一格地跳。只留最近几张。"""
    key = (text, font.toString(), color.rgba(), round(dpr * 100))
    img = _strip_cache.get(key)
    if img is None:
        fm = QFontMetricsF(font)
        w, h = fm.horizontalAdvance(text) + 2.0, fm.ascent() + fm.descent()
        img = QImage(max(1, math.ceil(w * dpr)), max(1, math.ceil(h * dpr)), QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(0.0, fm.ascent()), text)
        p.end()
        if len(_strip_cache) > 16:
            _strip_cache.clear()
        _strip_cache[key] = img
    return img


def draw_strip(p: QPainter, rect: QRectF, text: str, font: QFont, color: QColor, offset: float = 0.0, alpha: float = 1.0) -> float:
    """在 rect 里画一行字：放得下就原样；放不下就只露字窗里那一段，往左滚 offset 像素。两头的省略号钉在字窗两头，
    浓淡按 ellipsis_strength 连续变（不切换、不按整字减），字在省略号前面淡出。返回要滚多远（distance，给 Marquee 用）。"""
    fm = QFontMetricsF(font)
    win = rect.width()
    if win <= 1.0 or not text:
        return 0.0
    distance = fm.horizontalAdvance(text) - win
    left, right = ellipsis_strength(offset, distance)
    s = max(0.0, min(offset, max(0.0, distance)))
    dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
    img = _text_image(text, font, color, dpr)
    th = img.height() / dpr
    top = rect.top() + (rect.height() - th) / 2
    layer = QImage(max(1, math.ceil(win * dpr)), max(1, math.ceil(rect.height() * dpr)), QImage.Format_ARGB32_Premultiplied)
    layer.setDevicePixelRatio(dpr)
    lw, lh = layer.width() / dpr, layer.height() / dpr          # 按设备像素取整后比字窗多出的不到一个像素：也要盖住，原样画（不压缩）
    layer.fill(Qt.transparent)
    lp = QPainter(layer)
    lp.setRenderHint(QPainter.SmoothPixmapTransform)
    lp.drawImage(QRectF(-s, top - rect.top(), img.width() / dpr, th), img)
    if left > 0.0 or right > 0.0:
        ell = fm.horizontalAdvance("…")
        lp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        g = QLinearGradient(0.0, 0.0, win, 0.0)
        a, b = min(0.45, (ell) / win), min(0.48, (ell + ELLIPSIS_FADE) / win)
        g.setColorAt(0.0, QColor(0, 0, 0, round(255 * (1.0 - left))))
        g.setColorAt(a, QColor(0, 0, 0, round(255 * (1.0 - left))))
        g.setColorAt(b, QColor(0, 0, 0, 255))
        g.setColorAt(1.0 - b, QColor(0, 0, 0, 255))
        g.setColorAt(1.0 - a, QColor(0, 0, 0, round(255 * (1.0 - right))))
        g.setColorAt(1.0, QColor(0, 0, 0, round(255 * (1.0 - right))))
        lp.fillRect(QRectF(0.0, 0.0, lw, lh), g)               # 渐变出了字窗按最后一档延伸：只盖到 win 的话，最后一列会露出半个字（动的时候一闪一闪的细竖线）
    lp.end()
    p.save()
    p.setOpacity(p.opacity() * alpha)
    p.drawImage(QRectF(rect.left(), rect.top(), lw, lh), layer)
    p.setFont(font)
    base = top + fm.ascent()
    for strength, x in ((left, rect.left()), (right, rect.right() - fm.horizontalAdvance("…"))):
        if strength > 0.0:
            c = QColor(color)
            c.setAlphaF(c.alphaF() * strength)
            p.setPen(c)
            p.drawText(QPointF(x, base), "…")
    p.restore()
    return distance


def grapheme_count(text: str) -> int:
    """看得见的字数：一个表情（哪怕是好几个码位拼的）算一个字。"""
    f = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, text)
    n = 0
    while f.toNextBoundary() != -1:
        n += 1
    return n


def clip_graphemes(text: str, limit: int) -> str:
    """最多留 limit 个看得见的字（表情算一个，不会切在半个表情里）。Qt 的位置按 UTF-16 数，Python 按码位，要换算。"""
    f = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, text)
    bounds = []
    while (b := f.toNextBoundary()) != -1:
        bounds.append(b)
    if len(bounds) <= limit:
        return text
    cut, units = bounds[limit - 1], 0
    for i, ch in enumerate(text):
        if units >= cut:
            return text[:i]
        units += 2 if ord(ch) > 0xFFFF else 1
    return text


def rounded_polygon(points: list, radius: float) -> QPainterPath:
    """多边形，每个角按 radius 倒成圆角（角两边各让出 radius，用二次曲线连起来；边太短就按边长的一半）。"""
    path = QPainterPath()
    n = len(points)
    for i in range(n):
        prev, cur, nxt = points[i - 1], points[i], points[(i + 1) % n]

        def toward(a: QPointF, b: QPointF) -> QPointF:
            dx, dy = b.x() - a.x(), b.y() - a.y()
            length = math.hypot(dx, dy) or 1.0
            k = min(radius, length / 2) / length
            return QPointF(a.x() + dx * k, a.y() + dy * k)

        p1, p2 = toward(cur, prev), toward(cur, nxt)
        if i == 0:
            path.moveTo(p1)
        else:
            path.lineTo(p1)
        path.quadTo(cur, p2)
    path.closeSubpath()
    return path


def flat_arrow(x0: float, x1: float, cy: float, shaft: float = 18.0, head_w: float = 44.0, head_l: float = 32.0,
               radius: float = 6.0) -> QPainterPath:
    """平的箭头：箭杆 + 三角箭头，所有角都是圆角（DMG 窗口和卸载引导用；"圆圆的"是说圆角）。"""
    hx = x1 - head_l
    pts = [QPointF(x0, cy - shaft / 2), QPointF(hx, cy - shaft / 2), QPointF(hx, cy - head_w / 2), QPointF(x1, cy),
           QPointF(hx, cy + head_w / 2), QPointF(hx, cy + shaft / 2), QPointF(x0, cy + shaft / 2)]
    return rounded_polygon(pts, radius)


def draw_sticker_shape(p: QPainter, path: QPainterPath, fill: QColor, outline: float = 2.5) -> None:
    """贴纸画法画一个形状：纸片影（实心、右下偏）+ 浅色底 + 深色描边。"""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(28, 28, 33, sticker.SHADOW_ALPHA))
    p.drawPath(path.translated(sticker.SHADOW_OFFSET))
    p.setBrush(fill)
    p.setPen(QPen(QColor(sticker.INK), outline, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    p.restore()


def draw_trash(p: QPainter, c: QPointF, size: float) -> None:
    """贴纸风的废纸篓：盖子 + 提手 + 往下收的桶身 + 三道竖纹（卸载引导用）。"""
    s = size / 44.0
    body = rounded_polygon([QPointF(c.x() - 15 * s, c.y() - 9 * s), QPointF(c.x() + 15 * s, c.y() - 9 * s),
                            QPointF(c.x() + 12 * s, c.y() + 20 * s), QPointF(c.x() - 12 * s, c.y() + 20 * s)], 4 * s)
    lid = QPainterPath()
    lid.addRoundedRect(QRectF(c.x() - 19 * s, c.y() - 17 * s, 38 * s, 7 * s), 3.5 * s, 3.5 * s)
    handle = QPainterPath()
    handle.addRoundedRect(QRectF(c.x() - 6 * s, c.y() - 22 * s, 12 * s, 7 * s), 3 * s, 3 * s)
    fill = QColor(sticker.PAPER_2)
    draw_sticker_shape(p, handle, fill, 2.2)
    draw_sticker_shape(p, body, fill, 2.2)
    draw_sticker_shape(p, lid, fill, 2.2)
    p.save()
    p.setPen(QPen(QColor(sticker.INK), 2.0, Qt.SolidLine, Qt.RoundCap))
    for dx in (-6, 0, 6):
        p.drawLine(QPointF(c.x() + dx * s, c.y() - 3 * s), QPointF(c.x() + dx * s * 0.85, c.y() + 14 * s))
    p.restore()


def pill_path(r: QRectF) -> QPainterPath:
    """胶囊的描边路径，从顶上正中开始顺时针一圈：长按的进度线沿它走。"""
    rad = r.height() / 2
    p = QPainterPath(QPointF(r.center().x(), r.top()))
    p.lineTo(r.right() - rad, r.top())
    p.arcTo(QRectF(r.right() - 2 * rad, r.top(), 2 * rad, 2 * rad), 90.0, -180.0)
    p.lineTo(r.left() + rad, r.bottom())
    p.arcTo(QRectF(r.left(), r.top(), 2 * rad, 2 * rad), 270.0, -180.0)
    p.closeSubpath()
    return p


def hold_ring_color(kind: str, accent: Optional[str] = None) -> QColor:
    """进度线的颜色：和它压着的描边分得开——删除（红描边）用墨色，实心的主按钮用它上面字的颜色。"""
    if kind == "primary":
        return QColor(sticker.theme(accent).accent_text)
    if kind == "danger":
        return QColor(sticker.INK)
    return QColor(sticker.blue())


DANGER = sticker.DANGER


class HoldPill(MotionButton):
    """要按住 0.6 秒才触发的胶囊按钮（删除、删除安装包、安装、更新）：和别的胶囊同一种样子（同高、同圆角、同字号），只是颜色不同——
    kind："primary"（强调色实心）/ "danger"（红描边红字）。按住时一圈进度线沿描边走（和退出、重置、关机键一样是一圈），
    满了发 held；点一下没反应。线就压在描边上、从顶上正中顺时针走，离字三像素以上，挡不到字（别画在描边里面：会把「更新」的字挡住）。
    自己画，不用样式表的按下态（按下态会把整个按钮变深）。"""
    MOTION_COLOR = "press"
    held = Signal()

    def __init__(self, text: str, kind: str = "", accent: Optional[str] = None, parent=None):
        super().__init__(text, parent)
        self.kind = kind
        self.accent = accent
        if kind:
            self.setProperty("kind", kind)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(PILL_H + 2 * MOTION_PAD)
        self.driver = HoldDriver(self)
        self.driver.changed.connect(self.update)
        self.driver.held.connect(self.held)

    def set_accent(self, color: str) -> None:
        self.accent = color
        self.update()

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = self.motion.content_rect().adjusted(1.0, 1.0, -1.0, -1.0)
        t = sticker.theme(self.accent)
        if not self.isEnabled():
            bg, border, fg = QColor(Qt.transparent), QColor(t.muted), QColor(t.muted)
        elif self.kind == "primary":
            bg, border, fg = QColor(t.accent), QColor(sticker.INK), QColor(t.accent_text)
        else:
            bg = QColor(sticker.PAPER_3 if self.underMouse() else sticker.PAPER_2)
            border = fg = QColor(DANGER) if self.kind == "danger" else QColor(sticker.INK)
        if self.isEnabled() and self.motion.press_amount > 0:
            bg = sticker.mix(bg, sticker.contrast_color(bg), self.motion.press_amount)
            fg = sticker.contrast_color(bg)
        p.setPen(QPen(border, sticker.OUTLINE))
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        self.motion.draw_text(p, self.text(), fg)
        if self.driver.progress > 0.0:
            draw_hold_ring(p, pill_path(r), self.driver.progress,
                           fg if self.motion.press_amount > 0 else hold_ring_color(self.kind, self.accent), 2.5)


def fur_icon(dark: str, light: str, px: int = 22) -> QIcon:
    """原装毛色的色块：圆点上 55% 深色毛、下面浅色毛。"""
    pm = QPixmap(px * 2, px * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    circle = QPainterPath()
    circle.addEllipse(0.5, 0.5, px - 1, px - 1)
    p.setClipPath(circle)
    p.fillRect(QRectF(0, 0, px, px), QColor(light))
    p.fillRect(QRectF(0, 0, px, px * 0.55), QColor(dark))
    p.end()
    return QIcon(pm)


def round_icon(image: QImage, px: int) -> QIcon:
    """一张图裁成圆的（毛色头像用）：图铺满圆，多出来的裁掉。"""
    pm = QPixmap(px * 2, px * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    circle = QPainterPath()
    circle.addEllipse(0.5, 0.5, px - 1, px - 1)
    p.setClipPath(circle)
    p.fillRect(QRectF(0, 0, px, px), QColor(sticker.PAPER_2))
    side = min(image.width(), image.height())
    p.drawImage(QRectF(0, 0, px, px), image, QRectF((image.width() - side) / 2, (image.height() - side) / 2, side, side))
    p.end()
    return QIcon(pm)


def draw_hold_ring(p: QPainter, path: QPainterPath, progress: float, color: QColor, width: float = 2.5) -> None:
    """沿 path 画走了 progress 的一段进度线（按钮描边内侧绕一圈）：用虚线的第一段当进度，后面留一个巨大的空。"""
    if progress <= 0.0:
        return
    length = path.length()
    pen = QPen(color, width, Qt.CustomDashLine, Qt.FlatCap)
    pen.setDashPattern([max(0.01, length * min(1.0, progress) / width), 1e6])
    p.save()
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.restore()


class FlatIcon(MotionMixin, QAbstractButton):
    """行里的小图标按钮，没有圆底：灰色线稿，悬停、按下、勾着（展开着）变黑。"""
    SIZE = 22
    SOUND_KIND = "toggle"

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self._hover = False

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        ink = QColor(sticker.INK if (self.isChecked() or self._hover or self.isDown()) else sticker.MUTED)
        draw_icon(p, self.kind, QPointF(self.rect().center()) + QPointF(0.5, 0.5), 15.0, ink, ink)


class IconButton(MotionMixin, QAbstractButton):
    """圆形贴纸按钮：描边 + 米白，里面一个 draw_icon 画的图标；悬停底色变深，按下反色。
    没有悬浮文字（菜单里的图标不要提示），label 只给测试和菜单记名字用。
    hold=True 时要按住 0.6 秒才发 held（关机键）：按住时一圈强调色进度线沿描边内侧绕，clicked 不接动作。"""
    SIZE = 36
    MOTION_COLOR = "press"
    held = Signal()

    def __init__(self, kind: str, label: str = "", parent=None, hold: bool = False, size: int = SIZE, accent: Optional[str] = None):
        super().__init__(parent)
        self.kind = kind
        self.label = label
        self.hold = hold
        self.accent = QColor(accent or sticker.INK)   # 默认色建的时候再取（深色模式下是米白）
        self.motion.margin = 0 if size == PILL_H else MOTION_PAD
        outer = size + 2 * int(self.motion.margin)
        self.setFixedSize(outer, outer)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self.driver = HoldDriver(self) if hold else None
        if self.driver is not None:
            self.driver.changed.connect(self.update)
            self.driver.held.connect(self.held)

    def set_body_size(self, size: int) -> None:
        outer = size + 2 * int(self.motion.margin)
        self.setFixedSize(outer, outer)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        p.setRenderHint(QPainter.Antialiasing)
        r = self.motion.content_rect().adjusted(1.5, 1.5, -1.5, -1.5)
        fill = sticker.mix(QColor(sticker.PAPER_3 if self._hover else sticker.PAPER_2),
                           QColor(sticker.INK), self.motion.press_amount)
        ink = sticker.contrast_color(fill)
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
        p.setBrush(fill)
        p.drawEllipse(r)
        self.paint_glyph(p, r, ink, fill)
        if self.driver is not None and self.driver.progress > 0.0:
            ring = QPainterPath()
            ring.addEllipse(r.adjusted(2.5, 2.5, -2.5, -2.5))
            c = r.center()
            tr = QTransform().translate(c.x(), c.y()).rotate(-90.0).translate(-c.x(), -c.y())   # 从 12 点开始绕
            draw_hold_ring(p, tr.map(ring), self.driver.progress, ink if self.motion.press_amount > 0 else self.accent)

    def paint_glyph(self, p: QPainter, r: QRectF, ink: QColor, fill: QColor) -> None:
        """圆里的图案（r：描边那个圆）。子类可以换成别的、或者在同一个圆里淡入淡出两个图案（card._Lead：app 图标 ↔ 返回）。"""
        draw_icon(p, self.kind, r.center(), 19.0 * (self.motion.content_rect().width() / self.SIZE), ink, fill)


class HoldButton(MotionMixin, QAbstractButton):
    """要按住 0.6 秒才触发的灰字按钮（重置、退出）：平时和 quiet 按钮一样是灰字、没底，悬停出描边；按住时一圈强调色进度线沿描边内侧绕一圈，
    满了发 held；点一下没反应（防误触）。"""
    MOTION_COLOR = "press"
    held = Signal()

    def __init__(self, text: str, accent: Optional[str] = None, parent=None, *, symbol: Optional[str] = None):
        super().__init__(parent)
        self.setText(text)
        self.symbol = symbol
        self.accent = QColor(accent or sticker.INK)   # 默认色建的时候再取（深色模式下是米白）
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self._font = QFont()
        self._font.setPixelSize(13)
        self._font.setBold(True)
        if symbol is None:
            self.setFixedHeight(PILL_H + 2 * MOTION_PAD)
            self.setMinimumWidth(QFontMetrics(self._font).horizontalAdvance(text) + 28 + 2 * MOTION_PAD)
        else:
            self.setFixedSize(PILL_H, PILL_H)
        self.driver = HoldDriver(self)
        self.driver.changed.connect(self.update)
        self.driver.held.connect(self.held)

    def set_accent(self, color: str) -> None:
        self.accent = QColor(color)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = self.motion.content_rect().adjusted(1.0, 1.0, -1.0, -1.0)
        active = self._hover or self.motion.press_amount > 0 or self.driver.progress > 0.0
        fill = sticker.mix(QColor(sticker.PAPER_2), QColor(sticker.INK), self.motion.press_amount)
        fg = sticker.contrast_color(fill) if active else QColor(sticker.MUTED)
        if active:
            p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
            p.setBrush(fill)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.symbol is None:
            self.motion.draw_text(p, self.text(), fg, font=self._font)
        else:
            draw_icon(p, self.symbol, self.motion.content_rect().center(), 14.0, fg, fg)
        if self.driver.progress > 0.0:
            ring = QPainterPath()
            inner = r.adjusted(2.5, 2.5, -2.5, -2.5)
            ring.addRoundedRect(inner, inner.height() / 2, inner.height() / 2)
            draw_hold_ring(p, ring, self.driver.progress, fg if self.motion.press_amount > 0 else self.accent)


class FineSlider(QWidget):
    """连续、直接跟手的大小滑块。数值始终保留小数，圆钮的反馈动画不延迟数值。
    点击轨道定位；抓住圆钮时保留抓取偏移。滚轮 / 方向键每次 1 个百分点。
    主行用它粗调；百分比精调由 sizecontrol.SizeScrubber 处理。"""
    valueChanged = Signal(float)
    adjustmentStarted = Signal()
    adjustmentFinished = Signal()
    EDGE = 11.0
    MARK_SNAP_PX = 3.0

    def __init__(self, lo: int, hi: int, accent: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.lo, self.hi = lo, hi
        self.accent = QColor(accent or sticker.INK)   # 默认色建的时候再取（深色模式下是米白）
        self._value = float(lo)
        self._mark: Optional[float] = None        # 轨道上的小刻度（灵动交互：最适合跳窗口的大小）；拖到附近轻轻吸一下
        self._press: Optional[float] = None       # 抓取位置相对圆钮中心的偏移
        self._drag_global: Optional[QPointF] = None
        self._drag_local_x = 0.0
        self._pointer_drag = PointerDrag(self, self._drag_from_global)
        self._hovered = False
        self._feedback = Spring(0.0, 0.16)
        self._clock = FrameClock(self, self._animate)
        self.setMinimumWidth(112)
        self.setFixedHeight(PILL_H + 2 * MOTION_PAD)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, v: float) -> None:
        """从外面同步进来（不发信号）。"""
        if not math.isfinite(v):
            return
        self._value = float(max(self.lo, min(self.hi, v)))
        self.update()

    def set_range(self, lo: float, hi: float) -> None:
        self.lo, self.hi = lo, hi
        self.set_value(self._value)

    def set_mark(self, v: Optional[float]) -> None:
        """轨道上的小刻度；None 不画。"""
        if v != self._mark:
            self._mark = v
            self.update()

    @property
    def adjusting(self) -> bool:
        return self._press is not None

    def set_accent(self, color: str) -> None:
        self.accent = QColor(color)
        self.update()

    def _apply(self, v: float) -> None:
        old = self.value
        self._value = max(float(self.lo), min(float(self.hi), v))
        self.update()
        if self.value != old:
            sounds.size_changed(old, self.value, mark=self._mark)          # 吸到小刻度上那一下是另一种声音（size-snap）
            self.valueChanged.emit(self.value)

    def _thumb_x(self) -> float:
        t = (self.value - self.lo) / max(1e-9, self.hi - self.lo)
        return self.EDGE + t * max(1.0, self.width() - 2 * self.EDGE)

    def _drag_to(self, x: float) -> None:
        span = max(1.0, self.width() - 2 * self.EDGE)
        t = (x - self._press - self.EDGE) / span
        v = self.lo + t * (self.hi - self.lo)
        if self._mark is not None and abs(self._mark - v) * span / max(1e-9, self.hi - self.lo) <= self.MARK_SNAP_PX:
            v = self._mark
        self._apply(v)

    def _drag_from_global(self, point: QPointF, _now: float) -> None:
        if self._press is not None and self._drag_global is not None:
            self._drag_to(self._drag_local_x + point.x() - self._drag_global.x())

    def _finish_drag(self) -> None:
        self._pointer_drag.end()
        if self._press is not None:
            self._press, self._drag_global = None, None
            self.adjustmentFinished.emit()
            self._retarget()

    def cancel_interaction(self) -> None:
        """截图、隐藏等取消操作保留最后数值，并结束原生输入抓取。"""
        self._finish_drag()

    def _retarget(self) -> None:
        self._feedback.set_target(1.0 if self.adjusting else (0.45 if self._hovered else 0.0),
                                  instant=native.reduce_motion())
        self.update()
        if not self._feedback.settled:
            self._clock.start()

    def _animate(self, dt: float) -> bool:
        self._feedback.step(dt)
        self.update()
        return not self._feedback.settled

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._retarget()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._retarget()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled() and not ui_frozen():
            x = event.position().x()
            offset = x - self._thumb_x()
            self._press = offset if abs(offset) <= 11.0 else 0.0
            self._drag_global, self._drag_local_x = QPointF(event.globalPosition()), x
            self.setFocus(Qt.MouseFocusReason)
            self.adjustmentStarted.emit()
            self._drag_to(x)
            self._retarget()
            self._pointer_drag.begin(event)
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            return
        if not self._pointer_drag.move(event):
            self._drag_to(event.position().x())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._press is None:
            return
        if event.button() != Qt.LeftButton:
            return
        point = self._pointer_drag.native_release_position(event)
        if point is None:
            self._drag_to(event.position().x())
        else:
            self._drag_from_global(point, 0.0)
        self._finish_drag()
        event.accept()

    def hideEvent(self, event) -> None:
        self._finish_drag()
        self._hovered = False
        self._feedback.set_target(0.0, instant=True)
        self._clock.stop()
        super().hideEvent(event)

    def event(self, event) -> bool:
        if hasattr(self, "_pointer_drag") and (event.type() in (QEvent.UngrabMouse, QEvent.WindowDeactivate)
                or (event.type() == QEvent.EnabledChange and not self.isEnabled())):
            self._finish_drag()
        return super().event(event)

    def _nudge(self, delta: float) -> None:
        if not self.adjusting:
            self.adjustmentStarted.emit()
        self._apply(self.value + delta)
        if not self.adjusting:
            self.adjustmentFinished.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            self._nudge(-1.0 if event.key() in (Qt.Key_Left, Qt.Key_Down) else 1.0)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def wheelEvent(self, event) -> None:
        pd = event.pixelDelta()
        if not pd.isNull():
            d = (pd.x() if pd.x() else -pd.y()) / 4.0
        else:
            ad = event.angleDelta()
            d = (ad.y() if ad.y() else ad.x()) / 120.0
        if d:
            self._nudge(d)
        event.accept()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy, hx = h / 2.0, self._thumb_x()
        track = QColor(sticker.INK)
        track.setAlphaF(0.13)
        p.setPen(QPen(track, 6.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(self.EDGE, cy), QPointF(w - self.EDGE, cy))
        p.setPen(QPen(self.accent, 6.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(self.EDGE, cy), QPointF(hx, cy))
        if self._mark is not None and self.lo <= self._mark <= self.hi:
            mx = self.EDGE + (self._mark - self.lo) / max(1e-9, self.hi - self.lo) * max(1.0, w - 2 * self.EDGE)
            tick = QColor(sticker.INK)
            tick.setAlphaF(0.55)
            p.setPen(QPen(tick, 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(mx, cy - 6.0), QPointF(mx, cy + 6.0))
        radius = 8.0 + 1.5 * self._feedback.value
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            ring = QColor(self.accent)
            ring.setAlphaF(0.3)
            p.setPen(QPen(ring, 2.0))
            p.drawEllipse(QPointF(hx, cy), radius + 2, radius + 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 28))
        p.drawEllipse(QPointF(hx, cy + 1.5), radius + 0.5, radius + 0.5)
        border = QColor(sticker.INK)
        border.setAlphaF(0.16)
        p.setPen(QPen(border, 0.7))
        p.setBrush(QColor("#f2f2f5" if sticker.is_dark() else "#ffffff"))
        p.drawEllipse(QPointF(hx, cy), radius, radius)


class StepSlider(FineSlider):
    """只有几档的滑块（音量：10 档）：拖着跟手、落在最近的一档上，点轨道直接跳过去；方向键一下一档，滚轮 / 触摸板攒够一档的量才动一档。
    自己不出声：调的人按新的音量放一声听听（settings 的音量行）。"""

    def __init__(self, steps: int = 10, accent: Optional[str] = None, parent=None):
        super().__init__(0, steps, accent, parent)
        self.setMinimumWidth(72)
        self._wheel_acc = 0.0

    def _apply(self, v: float) -> None:
        old = self.value
        self._value = float(round(max(float(self.lo), min(float(self.hi), v))))
        self.update()
        if self.value != old:
            self.valueChanged.emit(self.value)

    def wheelEvent(self, event) -> None:
        pd = event.pixelDelta()
        d = ((pd.x() if pd.x() else -pd.y()) / 20.0) if not pd.isNull() else ((event.angleDelta().y() or event.angleDelta().x()) / 120.0)
        self._wheel_acc += d
        steps = int(self._wheel_acc)                  # 往零取整：攒够一档才动
        if steps:
            self._wheel_acc -= steps
            self._nudge(float(steps))
        event.accept()


def draw_speaker(p: QPainter, center: QPointF, ink: QColor, level: float, muted: bool) -> None:
    """喇叭（静音键）：喇叭本身 + 一两道声波（level 0..1，大于一半两道）；静音时声波换成一个小 ×。"""
    cx, cy = center.x() - 2.0, center.y()
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    body = QPainterPath()
    body.moveTo(cx - 5.5, cy - 2.4)
    body.lineTo(cx - 2.6, cy - 2.4)
    body.lineTo(cx + 1.2, cy - 5.6)
    body.lineTo(cx + 1.2, cy + 5.6)
    body.lineTo(cx - 2.6, cy + 2.4)
    body.lineTo(cx - 5.5, cy + 2.4)
    body.closeSubpath()
    p.setPen(QPen(ink, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(ink)
    p.drawPath(body)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(ink, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if muted or level <= 0.0:
        d = 2.4
        x0 = cx + 6.2
        p.drawLine(QPointF(x0 - d, cy - d), QPointF(x0 + d, cy + d))
        p.drawLine(QPointF(x0 + d, cy - d), QPointF(x0 - d, cy + d))
    else:
        for r in ((3.6,) if level <= 0.5 else (3.6, 6.8)):
            p.drawArc(QRectF(cx + 1.2 - r, cy - r, 2 * r, 2 * r), -50 * 16, 100 * 16)
    p.restore()


class MuteButton(MotionMixin, QAbstractButton):
    """音量滑块右边的静音键（照苹果的逻辑，静音变 0、取消静音回到原来那一档）：和「重置」一样的灰色小图标，悬停出描边、按下反色。
    level（0..1）决定画几道声波；muted 画 ×。按下的声音不归它放（静音前 / 取消静音后由调的人按那时的音量放）。"""
    MOTION_COLOR = "press"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(PILL_H, PILL_H)
        self.setCursor(Qt.PointingHandCursor)
        self.level, self.muted = 1.0, False
        self._hover = False
        try:
            self.clicked.disconnect(self.motion._click_sound)
        except (RuntimeError, TypeError):
            pass

    def set_state(self, level: float, muted: bool) -> None:
        if (level, muted) != (self.level, self.muted):
            self.level, self.muted = level, muted
            self.setAccessibleDescription("muted" if muted or level <= 0.0 else "")
            self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        p.setRenderHint(QPainter.Antialiasing)
        r = self.motion.content_rect().adjusted(1.0, 1.0, -1.0, -1.0)
        active = self._hover or self.motion.press_amount > 0
        fill = sticker.mix(QColor(sticker.PAPER_2), QColor(sticker.INK), self.motion.press_amount)
        fg = sticker.contrast_color(fill) if active else QColor(sticker.MUTED)
        if active:
            p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
            p.setBrush(fill)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        draw_speaker(p, self.motion.content_rect().center(), fg, self.level, self.muted)


def bone_path(center: QPointF, width: float, tilt: float = 0.0) -> QPainterPath:
    """一根骨头：杆 500×120 圆角 60、两头各两个半径 105 的球，按 width 缩放、绕中心转 tilt 度。
    狗的物种图标是它（marks.species_path，名字胶囊里狗的名字左边那个；app 图标 是猫狗拼的 DM，不是它）；
    屏幕正中的 HUD（StickerHud，斜 28°、描边）直接用它。"""
    s = width / 710.0
    path = QPainterPath()
    path.addRoundedRect(QRectF(-250 * s, -60 * s, 500 * s, 120 * s), 60 * s, 60 * s)
    for kx, ky in ((-250, -70), (-250, 70), (250, -70), (250, 70)):
        knob = QPainterPath()
        knob.addEllipse(QPointF(kx * s, ky * s), 105 * s, 105 * s)
        path = path.united(knob)
    return QTransform().translate(center.x(), center.y()).rotate(tilt).map(path)


def paw_pixmap(size: int, color: str, dpr: float) -> QPixmap:
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw_paw(p, QPointF(size / 2, size / 2), size, QColor(color))
    p.end()
    return pm


def bone_pixmap(width: int, dpr: float, ink: Optional[str] = None, fill: Optional[str] = None) -> QPixmap:
    """一根横着的小骨头：描边 + 米白，分组标题前用；表盘的分组胶囊里是米白描边米白填（深底上）。颜色不给就用当前模式的。"""
    ink, fill = ink or sticker.INK, fill or sticker.PAPER
    height = round(width * 0.5)
    pm = QPixmap(round(width * dpr), round(height * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    k = width / 22.0
    p.scale(k, k)
    path = QPainterPath()
    path.addRoundedRect(QRectF(4.5, 3.6, 13.0, 3.8), 1.9, 1.9)
    for cx, cy in ((4.5, 3.4), (4.5, 7.6), (17.5, 3.4), (17.5, 7.6)):
        path.addEllipse(QPointF(cx, cy), 2.6, 2.6)
    p.setPen(QPen(QColor(ink), 1.4 / k))
    p.setBrush(QColor(fill))
    p.drawPath(path.simplified())
    p.end()
    return pm


class Switch(MotionMixin, QAbstractButton):
    """开关：描边胶囊里一个圆钮滑过去。关着米白底；开着底色是强调色（跟毛色），钮上一个小爪印。
    钮滑、底色渐变、爪印淡入一起 0.18 秒（缓出），和卡片同一个节拍；别的开关把它互斥关掉时也一样滑过去，只有卡片打开那一下对齐设置时直接到位。"""
    SLIDE_S = 0.18
    SOUND_KIND = "switch"

    def __init__(self, parent=None, accent: Optional[str] = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44 + 2 * MOTION_PAD, PILL_H + 2 * MOTION_PAD)
        self.accent = QColor(accent or sticker.INK)      # 默认色建的时候再取（深色模式下是米白）：写在参数默认值里会是 import 时的浅色黑
        self._pos = self._from = self._to = 0.0
        self._t = 1.0
        self.toggled.connect(self._animate)

    def set_accent(self, color: str) -> None:
        self.accent = QColor(color)
        self.update()

    def set_silently(self, on: bool) -> None:
        """同步状态但不发信号（模式互斥、面板打开时对齐设置用）：卡片显示着就滑过去，打开那一下（Card.still）直接到位。"""
        if self.isChecked() == on and self._to == (1.0 if on else 0.0):
            return
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._animate(on)

    def _animate(self, on: bool) -> None:
        self._from, self._to, self._t = self._pos, (1.0 if on else 0.0), 0.0
        if not drive(self, self):
            self._pos, self._t = self._to, 1.0
        self.update()

    def tick(self, dt: float) -> bool:
        self._t = min(1.0, self._t + dt / self.SLIDE_S)
        self._pos = self._from + (self._to - self._from) * ease_out(self._t)
        self.update()
        return self._t < 1.0

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        p.setRenderHint(QPainter.Antialiasing)
        r = self.motion.content_rect().adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
        track = sticker.blend(QColor(sticker.PAPER_2 if sticker.is_dark() else sticker.PAPER), self.accent, self._pos)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 7
        knob = QRectF(r.left() + 3.5 + (r.width() - 7 - d) * self._pos, r.top() + 3.5, d, d)
        knob_color = QColor(sticker.PAPER_3 if sticker.is_dark() else sticker.PAPER)
        p.setBrush(knob_color)
        p.drawEllipse(knob)
        if self._pos > 0.5:                                   # 开着：钮上一个小爪印
            ink = sticker.contrast_color(knob_color)
            ink.setAlphaF(min(1.0, (self._pos - 0.5) * 2.0))
            draw_paw(p, knob.center(), d * 0.62, ink)

class Swatch(MotionButton):
    """毛色色块：描边圆点，选中描边加粗。里面画的图标（原装毛色上深下浅、自定义斜着两色）选中时缩一圈，加粗的描边才露得出来
    （图标 22 一直不变会盖住加粗描边的里面一半，自定义那个选中了也看不出来）。选中 / 取消时描边 2 → 4、图标 22 → 18 用 0.15 秒渐变。
    自己画（样式表变不了中间值）。"""
    MOTION_COLOR = "none"
    SIDE = PILL_H                              # 圆点多大（描边外沿）；ICON、ICON_CHECKED 是它减两倍描边
    ICON, ICON_CHECKED = 22, 18
    S = 0.15

    def __init__(self, color: str):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(self.SIDE + 2 * MOTION_PAD, self.SIDE + 2 * MOTION_PAD)
        self.setCursor(Qt.PointingHandCursor)
        self._color = color
        self._sel = self._from = self._to = 0.0
        self._t = 1.0
        self.toggled.connect(self._animate)
        self.setIconSize(QSize(self.ICON, self.ICON))

    def _animate(self, on: bool) -> None:
        self._from, self._to, self._t = self._sel, (1.0 if on else 0.0), 0.0
        if not drive(self, self):
            self._sel, self._t = self._to, 1.0
        self.update()

    def tick(self, dt: float) -> bool:
        self._t = min(1.0, self._t + dt / self.S)
        self._sel = self._from + (self._to - self._from) * ease_out(self._t)
        self.update()
        return self._t < 1.0

    def set_fur(self, dark: str, light: str) -> None:
        """原装毛色：上半深色毛、下半浅色毛（像狗的背和肚子），和狗身上的颜色一样。"""
        self.set_color("transparent")
        self.setIcon(fur_icon(dark, light, self.ICON))

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def inner_px(self) -> float:
        """里面的图标现在画多大（描边 2 → 4 时 22 → 18）。"""
        return self.motion.content_rect().width() - 2 * (2.0 + 2.0 * self._sel)

    def paintEvent(self, event) -> None:
        p = self.motion_painter()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        c = QRectF(self.rect()).center()
        ring = 2.0 + 2.0 * self._sel                                    # 描边 2 → 4
        inner = (self.motion.content_rect().width() - 2 * ring) / 2                           # 图标 22 → 18
        enabled = self.isEnabled()
        fill = QColor(self._color) if enabled else QColor(128, 128, 128, 64)
        if fill.isValid() and fill.alpha() > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawEllipse(c, inner, inner)
        if not self.icon().isNull():
            dpr = self.devicePixelRatioF()
            pm = self.icon().pixmap(QSize(self.ICON, self.ICON), dpr, QIcon.Normal if enabled else QIcon.Disabled)
            p.drawPixmap(QRectF(c.x() - inner, c.y() - inner, 2 * inner, 2 * inner), pm, QRectF(pm.rect()))
        p.setPen(QPen(QColor(sticker.INK if enabled else sticker.MUTED), ring))
        p.setBrush(Qt.NoBrush)
        r = self.motion.content_rect().width() / 2 - ring / 2
        p.drawEllipse(c, r, r)


class Avatar(Swatch):
    """毛色头像（两色圆点看不出是哪一套）：大一号的圆点，里面是这套毛色的小狗头像；头像画出来之前是上深下浅的两色。"""
    SIDE = 44
    ICON, ICON_CHECKED = 40, 36

    def set_portrait(self, image: QImage) -> None:
        self.set_color("transparent")
        self.setIcon(round_icon(image, self.ICON))


class StickerTip(QWidget):
    """悬浮说明：鼠标在某一行里停下不动 0.5 秒，这一行文字的右边浮出一个米白描边的小胶囊写说明文字、和行垂直居中
    （灰字描述都改成悬浮才显示：要停下不动才出，动一下计时重来，出来后在这一行里小幅移动不收；
    放在文字右边，不放下面 —— 右边放不下、会盖到这一行右边的开关 / 按钮或出屏幕，才放在行下面；
    **对话气泡**：字 13、内边距 12 / 9、圆角 8（sticker.RADIUS_TIP），
    描边 2、阴影和卡片同款，一条小尾巴指着它解释的那行字（放右边尾巴朝左、放下面尾巴朝上、翻到上面尾巴朝下），整张歪 2°；
    理由：整圆胶囊和 12 的圆角都像按钮，尾巴和歪斜是"注解"的记号，界面里没有按钮长这样）。整个程序一个，谁要显示就 show_for。"""
    WRAP, PAD_X, PAD_Y, M = 240, 12, 9, 10     # 文字换行宽、内边距、给描边、阴影、尾巴和歪斜留的边
    GAP = 12                                   # 放在文字右边时：身体离文字多远（尾巴尖离文字 GAP - TAIL）、离右边的控件多远
    GAP_BELOW = 8                              # 放在行下面时：身体离行底多远，尾巴尖刚好落在行底
    TAIL, TILT = 7.0, -2.0                     # 尾巴长、整张歪的角度
    POP_S, POP_FROM = 0.16, 0.88               # 出来时从尾巴尖那一点放大（0.88 → 1）、淡入

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.text = ""
        self._font = QFont()
        self._font.setPixelSize(13)
        self._placed = "below"                 # beside / below / above：尾巴朝哪边
        self._pop = 1.0
        self._clock = FrameClock(self, self._tick)

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)      # 只待在某个桌面上的窗口会让程序一激活就跳过去，提示也放到所有桌面
        super().showEvent(event)

    def show_for(self, anchor: QWidget, text: str, beside: Optional[QWidget] = None, spot: Optional[QRect] = None) -> None:
        """显示 anchor（一行）的说明。beside 是这一行的文字（或控件本身）：先试放在它右边、和这一行垂直居中；放不下就放在这一行下面。
        spot：anchor 里真正被解释的那一块（屏幕坐标），不给就是整个 anchor —— 比如卡片顶部栏里的名字胶囊：这一条比胶囊高、胶囊也不一定靠左，
        气泡按胶囊的右边、上下正中放，放下面时尾巴指着胶囊的开头。"""
        self.text = text
        fm = QFontMetrics(self._font)
        box = fm.boundingRect(QRectF(0, 0, self.WRAP, 1000).toRect(), Qt.TextWordWrap, text)
        w, h = box.width() + 2 * self.PAD_X + 2 * self.M, box.height() + 2 * self.PAD_Y + 2 * self.M
        self.setFixedSize(w, h)
        at = self._beside(anchor, beside, w, h, spot) if beside is not None else None
        self.move(at if at is not None else self._below(w, h, spot or QRect(anchor.mapToGlobal(QPoint(0, 0)), anchor.size())))
        self._pop = 1.0 if native.reduce_motion() else 0.0
        self.show()
        self.update()
        if self._pop < 1.0:
            self._clock.start()

    def _tick(self, dt: float) -> bool:
        self._pop = min(1.0, self._pop + dt / self.POP_S)
        self.update()
        return self._pop < 1.0

    def hideEvent(self, event) -> None:
        self._clock.stop()
        self._pop = 1.0
        super().hideEvent(event)

    def tail_tip(self, r: QRectF) -> QPointF:
        """尾巴尖在哪（气泡从这一点放大出来）。"""
        if self._placed == "beside":
            return QPointF(r.left() - self.TAIL, r.center().y())
        if self._placed == "below":
            return QPointF(r.left() + 28, r.top() - self.TAIL)
        return QPointF(r.left() + 28, r.bottom() + self.TAIL)

    def _beside(self, anchor: QWidget, beside: QWidget, w: int, h: int, spot: Optional[QRect] = None) -> Optional[QPoint]:
        """文字右边的位置：从文字的右边空 GAP 起，到这一行里右边最近的控件（没有就到行尾）为止，整条放得下、不出屏幕才用，否则 None。
        Card.row 的标题 QLabel 是撑满剩余宽度的，所以文字的右边按 sizeHint（文字本身的宽）算，不按控件的宽；给了 spot 就按 spot 的右边、上下正中。"""
        holder = anchor if beside is not anchor else anchor.parentWidget()
        if holder is None:
            return None
        if spot is not None:
            right = holder.mapFromGlobal(QPoint(spot.left() + spot.width(), spot.top())).x()
        else:
            text_w = min(beside.width(), beside.sizeHint().width())
            right = beside.mapTo(holder, QPoint(text_w, 0)).x()
        limit = holder.width()
        for child in holder.children():
            if isinstance(child, QWidget) and child is not beside and child.isVisible() and child.geometry().left() >= right:
                limit = min(limit, child.geometry().left())          # 这一行里文字右边最近的控件：提示不能盖到它
        if right + self.GAP + (w - 2 * self.M) + self.GAP > limit:
            return None
        x = holder.mapToGlobal(QPoint(right + self.GAP - self.M, 0)).x()
        cy = spot.top() + spot.height() // 2 if spot is not None else anchor.mapToGlobal(QPoint(0, anchor.height() // 2)).y()
        y = cy - h // 2
        screen = QApplication.screenAt(QPoint(x, y)) or QApplication.primaryScreen()
        if x + w > screen.availableGeometry().right():
            return None
        self._placed = "beside"
        return QPoint(x, y)

    def _below(self, w: int, h: int, spot: QRect) -> QPoint:
        """spot（这一行，或行里被解释的那一块）下面：身体离它的底 GAP_BELOW，尾巴尖落在它的底、指着它的开头（屏幕底放不下就放它上面，尾巴朝下）。"""
        pos = QPoint(spot.left(), spot.top() + spot.height() + self.GAP_BELOW)
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        ag = screen.availableGeometry()
        x = min(max(pos.x() - self.M, ag.left()), ag.right() - w)
        y = pos.y() - self.M
        self._placed = "below"
        if y + h > ag.bottom():
            y = spot.top() - h - self.GAP_BELOW + self.M
            self._placed = "above"
        return QPoint(x, y)

    def shape(self, r: QRectF) -> QPainterPath:
        """气泡的形状：圆角矩形并上一个小三角尾巴（朝左 / 朝上 / 朝下，按放在哪边）。"""
        path = QPainterPath()
        path.addRoundedRect(r, sticker.RADIUS_TIP, sticker.RADIUS_TIP)
        tail = QPainterPath()
        if self._placed == "beside":                                 # 放在文字右边：尾巴朝左指着文字
            cy = r.center().y()
            tail.moveTo(QPointF(r.left() + 1, cy - 7))
            tail.lineTo(QPointF(r.left() - self.TAIL, cy))
            tail.lineTo(QPointF(r.left() + 1, cy + 7))
        elif self._placed == "below":                                # 放在行下面：尾巴朝上指着那行字的开头
            cx = r.left() + 28
            tail.moveTo(QPointF(cx - 7, r.top() + 1))
            tail.lineTo(QPointF(cx, r.top() - self.TAIL))
            tail.lineTo(QPointF(cx + 7, r.top() + 1))
        else:                                                        # 翻到行上面：尾巴朝下
            cx = r.left() + 28
            tail.moveTo(QPointF(cx - 7, r.bottom() - 1))
            tail.lineTo(QPointF(cx, r.bottom() + self.TAIL))
            tail.lineTo(QPointF(cx + 7, r.bottom() - 1))
        tail.closeSubpath()
        return path.united(tail)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)
        c = r.center()
        tr = QTransform()
        if self._pop < 1.0:                                          # 刚出来：从尾巴尖那一点放大、淡入
            k = ease_out(self._pop)
            tip, scale = self.tail_tip(r), self.POP_FROM + (1.0 - self.POP_FROM) * k
            tr.translate(tip.x(), tip.y())
            tr.scale(scale, scale)
            tr.translate(-tip.x(), -tip.y())
            p.setOpacity(k)
        tr.translate(c.x(), c.y())
        tr.rotate(self.TILT)
        tr.translate(-c.x(), -c.y())
        p.setTransform(tr)                                           # 整张歪 2°（字一起歪）
        shape = self.shape(r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 28, 33, sticker.SHADOW_ALPHA))
        p.drawPath(shape.translated(sticker.SHADOW_OFFSET))
        p.setBrush(QColor(sticker.PAPER))
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(shape)
        p.setFont(self._font)
        p.setPen(QColor(sticker.INK))
        p.drawText(r.adjusted(self.PAD_X, self.PAD_Y, -self.PAD_X, -self.PAD_Y), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.text)


_tip: Optional[StickerTip] = None


def sticker_tip() -> StickerTip:
    global _tip
    if _tip is None:
        _tip = StickerTip()
    return _tip


def hide_tip() -> None:
    """有提示就收起来（卡片关掉、换外观时）。"""
    if _tip is not None:
        _tip.hide()


class StickerHud(QWidget):
    """屏幕正中的一次性提示（像音量、按住 ⌘Q 退出那种）：一张贴纸卡，上面一根斜着的骨头、下面两行字。
    淡入 0.2 秒、停 4 秒（2 秒来不及读完）、淡出 0.5 秒；不用点、也点不到（鼠标穿过去），不抢焦点。
    排版：骨头 32 宽在上、两行字，上下各留 20，整块正好在卡片正中。
    已卸载那张也不按行高算：字下面那截留白会算进去（量出来笔画上面空 15、下面空 21）；
    现在按笔画实际的上下边算（g、p 往下那一截不算），骨头的上边到描边、字的下边到描边一样远。
    整个程序一个（sticker_hud）。用在：装新版本时提示拖进应用程序（window.install_update）、卸载没成时说原因（window._uninstall_failed）。"""
    FADE_IN_MS, HOLD_MS, FADE_OUT_MS = 200, 4000, 500
    PAD_X, PAD_Y, M, BONE_W, GAP, MIN_W = 24, 20, 8, 32, 12, 220   # 左右内边距、笔画到描边的上下距离、描边和阴影的边、骨头宽、骨头和字（笔画之间）的空、卡片最窄
    NO_DESCENT = str.maketrans("gjpqy", "xxxxx")             # 量字的下边时不算这些字母往下那一截

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint | Qt.WindowTransparentForInput
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.text = ""
        self._font = QFont()
        self._font.setPixelSize(13)
        self._lines: list[str] = []
        self._ink = (0.0, 0.0)                                    # 字的笔画上下边，相对第一行的基线
        self._bone = QRectF()                                     # 斜着的骨头（连描边）占的范围，相对骨头中心
        self._fade = QVariantAnimation(self)
        self._fade.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self._fade.finished.connect(self._faded)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(self.HOLD_MS)
        self._hold.timeout.connect(self._fade_out)

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)      # 同 StickerTip（跳桌面）
        super().showEvent(event)

    def show_text(self, text: str, screen=None) -> None:
        """在 screen（不给就主屏）正中偏上 20 像素弹出来；正在显示就重来。text 里用 \n 分行。"""
        self.text = text
        fm = QFontMetricsF(self._font)
        self._lines = text.split("\n")
        step = fm.lineSpacing()
        tops, bottoms = [], []
        for i, line in enumerate(self._lines):
            ink = fm.tightBoundingRect(line.translate(self.NO_DESCENT) or " ")
            tops.append(i * step + ink.top())
            bottoms.append(i * step + ink.bottom())
        self._ink = (min(tops), max(bottoms))
        self._bone = bone_path(QPointF(0.0, 0.0), self.BONE_W, tilt=-28.0).boundingRect().adjusted(-1, -1, 1, 1)   # 描边 2，各多 1
        text_w = max(fm.horizontalAdvance(line) for line in self._lines)
        inner = self.PAD_Y + self._bone.height() + self.GAP + (self._ink[1] - self._ink[0]) + self.PAD_Y
        w = round(max(text_w + 2 * self.PAD_X, self.MIN_W)) + 2 * self.M
        h = round(inner) + 2 + 2 * self.M                                    # + 2：上下描边各 1 像素在卡片里面
        self.setFixedSize(w, h)
        screen = screen or QApplication.primaryScreen()
        ag = screen.availableGeometry()
        self.move(ag.center().x() - w // 2, ag.center().y() - h // 2 - 20)
        self._hold.stop()
        self._fade.stop()
        self.setWindowOpacity(0.0)
        self.show()
        self.update()
        self._run_fade(0.0, 1.0, self.FADE_IN_MS)

    def _run_fade(self, start: float, end: float, ms: int) -> None:
        self._fade.setStartValue(start)
        self._fade.setEndValue(end)
        self._fade.setDuration(ms)
        self._fade.setEasingCurve(QEasingCurve.OutCubic if end > start else QEasingCurve.InCubic)
        self._fade.start()

    def _faded(self) -> None:
        if float(self._fade.endValue()) >= 1.0:
            self._hold.start()                                       # 淡入完：停 HOLD_MS 再淡出
        else:
            self.hide()

    def _fade_out(self) -> None:
        self._run_fade(self.windowOpacity(), 0.0, self.FADE_OUT_MS)

    def finish_now(self) -> None:
        """立刻走完收起（单测用，不真等 4.7 秒）。"""
        self._hold.stop()
        self._fade.stop()
        self.hide()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 28, 33, sticker.SHADOW_ALPHA))
        p.drawRoundedRect(r.translated(sticker.SHADOW_OFFSET), sticker.RADIUS, sticker.RADIUS)
        p.setBrush(QColor(sticker.PAPER))
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
        p.drawRoundedRect(r, sticker.RADIUS, sticker.RADIUS)
        p.setBrush(QColor(sticker.PAPER_2))
        top = r.top() + 1 + self.PAD_Y                                       # 骨头笔画的上边
        p.drawPath(bone_path(QPointF(r.center().x(), top - self._bone.top()), self.BONE_W, tilt=-28.0))   # 和 App 图标一样斜 28°
        p.setFont(self._font)
        p.setPen(QColor(sticker.INK))
        fm = QFontMetricsF(self._font)
        base = top + self._bone.height() + self.GAP - self._ink[0]           # 第一行的基线：字的笔画上边离骨头 GAP
        for i, line in enumerate(self._lines):
            p.drawText(QPointF(r.center().x() - fm.horizontalAdvance(line) / 2, base + i * fm.lineSpacing()), line)


_hud: Optional[StickerHud] = None


def sticker_hud() -> StickerHud:
    global _hud
    if _hud is None:
        _hud = StickerHud()
    return _hud


def hairline(t: sticker.Theme) -> QFrame:
    """分隔线：虚线，像贴纸的缝线。"""
    line = QFrame()
    line.setProperty("hairline", True)       # stack() 认它：线上下的间距不跟着行距放大
    line.setFixedHeight(2)
    line.setStyleSheet(f"QFrame {{ border-top: 2px dotted {sticker.rgba(sticker.INK, 0.35)}; background: transparent; }}")
    return line
