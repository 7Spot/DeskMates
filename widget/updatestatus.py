"""更新行的持久控件：一层背景、原位换字，不截图或替换子控件。"""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QFontMetricsF, QPainterPath, QTransform
from PySide6.QtWidgets import QSizePolicy

from widget import native, sticker
from widget.capture_ui import ui_frozen
from widget.widgets import MotionButton, PILL_H, drive
from widget.motion import ButtonMotion, MOTION_PAD


class _StatusMotion(ButtonMotion):
    """状态区域占满行，只有贴着 ALIGN 那边的文字胶囊参与通用按钮动效。"""
    def content_rect(self) -> QRectF:
        return self.widget.capsule_rect()

    def transform(self) -> QTransform:
        center = self.content_rect().center()
        transform = QTransform()
        transform.translate(center.x() + self.offset.x(), center.y() + self.offset.y())
        transform.scale(self.paint_scale, self.paint_scale)
        transform.translate(-center.x(), -center.y())
        return transform

    def _point(self, pos) -> None:
        if self._held:
            return
        rect = self.content_rect()
        self._target(self.direction_x, max(-1.0, min(1.0, (pos.x() - rect.center().x()) / max(1, rect.width() / 2))))
        self._target(self.direction_y, max(-1.0, min(1.0, (pos.y() - rect.center().y()) / max(1, rect.height() / 2))))

    def hit(self, point) -> bool:
        rect = self._press_rect if self._press_rect is not None else self.visual_rect()
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        return path.contains(QPointF(point))

    def hover_at(self, point) -> None:
        inside = self.widget.clickable and self.widget.isEnabled() and self.hit(point)
        self.widget.setCursor(Qt.PointingHandCursor if inside else Qt.ArrowCursor)
        self._target(self.hover, float(inside))
        if inside:
            self._point(point)
        elif self._held:
            self.cancel()

    def sync_hover(self) -> None:
        if not ui_frozen():
            point = self.widget.mapFromGlobal(QCursor.pos()) if self.widget.underMouse() else QPointF(-1, -1)
            self.hover_at(point)

    def eventFilter(self, obj, event) -> bool:
        if ui_frozen():
            return super().eventFilter(obj, event)
        if event.type() in (QEvent.Enter, QEvent.MouseMove):
            self.hover_at(event.position())
            return False
        if event.type() == QEvent.MouseButtonPress and not self.hit(event.position()):
            return False
        return super().eventFilter(obj, event)


class UpdateStatus(MotionButton):
    MOTION_CLASS = _StatusMotion
    FADE_HALF = 0.12
    TEXT_INSET = 10
    ALIGN = Qt.AlignRight      # 字和胶囊贴哪边：高级设置那一行贴右；关于页的贴左（版本号在它左边，换字时版本号不挪）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clickable = False
        self._display_text = ""
        self._pending_text = ""
        self._text_opacity = 1.0
        self._text_phase = 0
        self._keyboard_focus = False
        self.setProperty("quiet", True)
        # 和左边版本号共用12px常规字；这里仅定义字体，不让QSS接管手绘底板。
        self.setStyleSheet("QPushButton { font-size: 12px; font-weight: 400; }")
        self.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 排版按控件自己的大小：macOS 的样式给按钮留了原生按钮的外边距，布局按它排会把同一行的灰字（版本号）往上挤 2 像素，
        # 字一高一低（真字体量的：字的中线 13 对 15）；这里的底板、字都是自己画的，用不着那圈外边距
        self.setAttribute(Qt.WA_LayoutUsesWidgetRect)
        self.setCursor(Qt.ArrowCursor)

    @property
    def clickable(self) -> bool:
        return self._clickable

    @property
    def text_animating(self) -> bool:
        return self._text_phase != 0

    def sizeHint(self) -> QSize:
        return QSize(170, PILL_H + 2 * MOTION_PAD)

    def minimumSizeHint(self) -> QSize:
        # 版本号占左边；右边始终拿剩余宽度，不随状态文案重新分配布局。
        return QSize(0, self.sizeHint().height())

    def _text_rect(self):
        return self.rect().adjusted(self.TEXT_INSET, 0, -self.TEXT_INSET, 0)

    def _visible_text(self) -> str:
        return QFontMetricsF(self.font()).elidedText(self._display_text, Qt.ElideMiddle, max(0, self._text_rect().width()))

    def capsule_rect(self) -> QRectF:
        rect = QRectF(self.rect()).adjusted(MOTION_PAD, MOTION_PAD, -MOTION_PAD, -MOTION_PAD)
        text_width = QFontMetricsF(self.font()).horizontalAdvance(self._visible_text())
        width = min(rect.width(), max(rect.height(), math.ceil(text_width) + 2 * (self.TEXT_INSET - MOTION_PAD)))
        if self.ALIGN == Qt.AlignLeft:
            rect.setRight(rect.left() + width)
        else:
            rect.setLeft(rect.right() - width)
        return rect

    def set_status(self, text: str, clickable: bool, tone: str | None = None, animated: bool = True) -> None:
        self._clickable = bool(clickable)
        self.setFocusPolicy(Qt.StrongFocus if clickable else Qt.NoFocus)
        self.setProperty("tone", tone)
        if not clickable:
            self._keyboard_focus = False
            held = self.isDown() or self.motion._held
            self.setDown(False)
            if held:
                self.motion.cancel()
            self.motion._target(self.motion.hover, 0.0)
        self.motion.sync_hover()
        if text == self._pending_text:
            self.update()
            return
        self._pending_text = text
        self.setText(text)                       # 语义、辅助功能与点击状态立刻更新，绘制的旧字稍后淡出
        if not self._display_text or not animated or not drive(self, self):
            self.finish_now()
        else:
            self._text_phase = -1
        self.update()

    def finish_now(self) -> None:
        self._display_text = self._pending_text
        self._text_opacity, self._text_phase = 1.0, 0
        self.motion.sync_hover()
        self.update()

    def tick(self, dt: float) -> bool:
        if native.reduce_motion() or not self.isVisible():
            self.finish_now()
            return False
        while dt > 0 and self._text_phase:
            goal = 0.0 if self._text_phase < 0 else 1.0
            travel = abs(goal - self._text_opacity) * self.FADE_HALF
            if dt < travel:
                self._text_opacity += self._text_phase * dt / self.FADE_HALF
                break
            dt -= travel
            self._text_opacity = goal
            if self._text_phase < 0:
                self._display_text = self._pending_text
                self.motion.sync_hover()
                self._text_phase = 1
            else:
                self._text_phase = 0
        self.update()
        return self.text_animating

    def paint_content(self, painter, rect, foreground) -> None:
        painter.save()
        painter.setOpacity(painter.opacity() * self._text_opacity)
        painter.setFont(self.font())
        painter.setPen(foreground)
        # 整行和QLabel使用相同的垂直排字；状态文案贴齐 ALIGN 那边，宽度变化不挪布局。
        # 长提示保留两端：原因与末尾的“重试”都能看到；完整语义仍由text()提供。
        painter.drawText(self._text_rect(), self.ALIGN | Qt.AlignVCenter, self._visible_text())
        painter.restore()

    def surface_colors(self):
        bg, border, fg, width = super().surface_colors()
        if self._keyboard_focus and self.hasFocus() and self._clickable:
            # 键盘仍有焦点提示，复用同一条胶囊轮廓，不叠加原生矩形或第二层底板。
            border = QColor(sticker.blue())
        return bg, border, fg, width

    def focusInEvent(self, event) -> None:
        self._keyboard_focus = event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def mousePressEvent(self, event) -> None:
        self._keyboard_focus = False
        super().mousePressEvent(event)
        self.update()

    def hitButton(self, point) -> bool:
        return self._clickable and super().hitButton(point)

    def click(self) -> None:
        if self._clickable:
            super().click()

    def animateClick(self) -> None:
        if self._clickable:
            super().animateClick()

    def keyPressEvent(self, event) -> None:
        if self._clickable:
            super().keyPressEvent(event)
        else:
            event.accept()

    def event(self, event) -> bool:
        result = super().event(event)
        if hasattr(self, "_display_text") and event.type() in (QEvent.Resize, QEvent.FontChange):
            self.motion.sync_hover()
        return result

    def hideEvent(self, event) -> None:
        self.finish_now()
        super().hideEvent(event)
