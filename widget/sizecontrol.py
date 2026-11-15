"""大小精调：悬停显示左右箭头，拖动数字慢细快粗，单击原位输入。"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

from widget import native, sounds, sticker
from widget.i18n import tr
from widget.pointer import PointerDrag
from widget.widgets import FrameClock, Spring


class SizeScrubber(QWidget):
    valueChanged = Signal(float)
    adjustmentStarted = Signal()
    adjustmentFinished = Signal()
    DRAG_THRESHOLD = 3.0
    POINTS_PER_PIXEL = 0.1
    MAX_GAIN = 5.0

    def __init__(self, parent=None, lo: float = 30, hi: float = 400, accent=None):
        super().__init__(parent)
        self.lo, self.hi, self._value = float(lo), float(hi), 100.0
        self.accent = accent
        self._press = self._last = None
        self._last_time = 0.0
        self._gain, self._direction = 1.0, 0.0
        self._adjusting = self._editing = self._hovered = False
        self._origin = self._value
        self._pointer = QPointF(32, 13)
        self._hover = Spring(0.0, 0.16)
        self._offset_x = Spring(0.0, 0.16)
        self._offset_y = Spring(0.0, 0.16)
        self._clock = FrameClock(self, self._animate)
        self._pointer_drag = PointerDrag(self, self._drag_to)
        self.setFixedSize(56, 26)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.SizeHorCursor)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("Fine adjustment"))
        self.editor = QLineEdit(self)
        self.editor.setAccessibleName(tr("Size"))
        self.editor.setAlignment(Qt.AlignCenter)
        self.editor.setMaxLength(8)
        self.editor.installEventFilter(self)
        self.editor.editingFinished.connect(self._commit_text)
        self.editor.hide()
        self._style_editor()
        self._update_metrics()
        self._pointer = QPointF(self.width() / 2, self.height() / 2)

    def _number_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        return font

    def _update_metrics(self) -> None:
        fm = QFontMetricsF(self._number_font())
        label_width = max(fm.horizontalAdvance(self._integer(value) + "%") for value in (self.lo, self.hi, 100))
        self.setFixedWidth(max(56, math.ceil(label_width * 1.02 + 20)))  # 两边各7px箭头区 + 3px文字间隙
        self.editor.setGeometry(8, 1, self.width() - 16, self.height() - 2)

    @staticmethod
    def _integer(value: float) -> str:
        return str(math.floor(value + 0.5 + 1e-9))

    @property
    def value(self) -> float:
        return self._value

    @property
    def adjusting(self) -> bool:
        return self._adjusting

    def text(self) -> str:
        return self._integer(self._value) + "%"

    def set_value(self, value: float) -> None:
        if math.isfinite(value):
            self._value = max(self.lo, min(self.hi, float(value)))
            self.update()                       # 输入框的文字 / 选区不受后台同步影响

    def set_range(self, lo: float, hi: float) -> None:
        """范围跟着狗在的那块屏变（settings._sync_size_range）：数字最多几位也跟着量宽。"""
        self.lo, self.hi = float(lo), float(hi)
        self._update_metrics()
        self.set_value(self._value)

    def _apply(self, value: float, *, feedback: bool = True) -> None:
        previous = self._value
        self.set_value(value)
        if self._value != previous:
            if feedback:
                sounds.size_changed(previous, self._value, fine=True)
            self.valueChanged.emit(self._value)

    def _begin(self) -> None:
        if not self._adjusting:
            self._origin = self._value
            self._adjusting = True
            self.adjustmentStarted.emit()

    def _finish(self, restore: bool = False) -> None:
        self._pointer_drag.end()
        self._press = self._last = None
        self._gain, self._direction = 1.0, 0.0
        if self._adjusting:
            if restore:
                self._apply(self._origin, feedback=False)
            self._adjusting = False
            self.adjustmentFinished.emit()
        self._retarget()

    def cancel_interaction(self) -> None:
        self._finish()
        self._finish_edit(False)

    def _style_editor(self) -> None:
        t = sticker.theme(self.accent)
        self.editor.setStyleSheet(f"QLineEdit {{ color: {t.text}; background: {t.btn}; border: 1px solid {t.accent}; border-radius: 6px; padding: 0; font-size: 12px; }}")

    def start_edit(self) -> None:
        if not self.isEnabled():
            return
        typing = getattr(self.window(), "ensure_typing", None)   # 卡片点了不切前台：要打字先让它接键盘（card.Card.ensure_typing）
        if typing is not None:
            typing()
        self._finish()
        self._editing = True
        self._style_editor()
        self.editor.setText(self._integer(self._value))
        self.editor.setModified(False)
        self.editor.show()
        self.editor.setFocus(Qt.MouseFocusReason)
        self.editor.selectAll()
        self._retarget()

    def _finish_edit(self, commit: bool) -> None:
        if not self._editing:
            return
        self._editing = False                    # hide/focusOut 会再次发 editingFinished
        modified = self.editor.isModified()
        text = self.editor.text().strip().rstrip("%")
        self.editor.hide()
        if commit and modified:
            try:
                value = float(text)
            except ValueError:
                value = float("nan")
            if math.isfinite(value) and self.lo <= value <= self.hi and value != self._value:
                self._begin()
                self._apply(value)
                self._finish()
        self._retarget()

    def _commit_text(self) -> None:
        self._finish_edit(True)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.editor and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
                self._finish_edit(event.key() != Qt.Key_Escape)
                self.setFocus(Qt.OtherFocusReason)
                return True
        return super().eventFilter(obj, event)

    def _retarget(self) -> None:
        instant = native.reduce_motion()
        active = self.isEnabled() and (self._hovered or self._press is not None)
        self._hover.set_target(float(active), instant=instant)
        if instant or not active or self._editing:
            x = y = 0.0
        elif self._adjusting and self._direction:
            x, y = 2.0 * self._direction, 0.0
        else:
            x = max(-2.0, min(2.0, (self._pointer.x() / self.width() * 2 - 1) * 2))
            y = max(-1.0, min(1.0, self._pointer.y() / self.height() * 2 - 1))
        self._offset_x.set_target(x, instant=instant)
        self._offset_y.set_target(y, instant=instant)
        if not all(s.settled for s in (self._hover, self._offset_x, self._offset_y)):
            self._clock.start()
        self.update()

    def _animate(self, dt: float) -> bool:
        for spring in (self._hover, self._offset_x, self._offset_y):
            spring.step(dt)
        self.update()
        return not all(s.settled for s in (self._hover, self._offset_x, self._offset_y))

    def enterEvent(self, event) -> None:
        if hasattr(event, "position"):
            self._pointer = QPointF(event.position())
        self._hovered = True
        self._retarget()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._retarget()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self.isEnabled():
            return
        self._finish_edit(True)
        self.setFocus(Qt.MouseFocusReason)
        self._press = self._last = QPointF(event.globalPosition())
        self._pointer = QPointF(event.position())
        self._last_time = time.perf_counter()
        self._gain, self._direction = 1.0, 0.0
        self._retarget()
        self._pointer_drag.begin(event)
        event.accept()

    def _drag_to(self, point: QPointF, now: float) -> None:
        if self._press is None:
            return
        if not self._adjusting:
            if abs(point.x() - self._press.x()) <= self.DRAG_THRESHOLD:
                return
            self._begin()
        dx = point.x() - self._last.x()
        elapsed = max(1e-4, now - self._last_time)
        self._last, self._last_time = QPointF(point), now
        if not dx:
            return
        direction = math.copysign(1.0, dx)
        if elapsed > 0.12 or direction != self._direction:
            self._gain = 1.0                    # 停后微调 / 反向无需抵消旧加速或越界余量
        speed = abs(dx) / elapsed
        u = max(0.0, min(1.0, (speed - 80.0) / 520.0))
        target = 1.0 + (self.MAX_GAIN - 1.0) * u * u * (3.0 - 2.0 * u)
        self._gain += (target - self._gain) * (1.0 - math.exp(-min(elapsed, 0.05) / 0.055))
        self._direction = direction
        self._retarget()                         # 只推动绘制偏移，真实输入始终使用屏幕浮点坐标
        self._apply(self._value + dx * self.POINTS_PER_PIXEL * self._gain)

    def mouseMoveEvent(self, event) -> None:
        if self._press is not None:
            if not self._pointer_drag.move(event):
                self._drag_to(QPointF(event.globalPosition()), time.perf_counter())
        else:
            self._pointer = QPointF(event.position())
            self._retarget()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._press is None:
            return
        self._drag_to(self._pointer_drag.release_position(event), time.perf_counter())
        was_dragging = self._adjusting
        self._pointer = QPointF(event.position())
        self._finish()
        if not was_dragging:
            self.start_edit()
        event.accept()

    def _nudge(self, amount: float) -> None:
        self._begin()
        self._apply(self._value + amount)
        self._finish()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self._press is not None:
            self._finish(restore=True)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.start_edit()
        elif event.key() in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            self._nudge(-1.0 if event.key() in (Qt.Key_Left, Qt.Key_Down) else 1.0)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def event(self, event) -> bool:
        if hasattr(self, "_press") and event.type() in (QEvent.UngrabMouse, QEvent.WindowDeactivate):
            self._finish()
        elif hasattr(self, "_press") and event.type() == QEvent.EnabledChange and not self.isEnabled():
            self.cancel_interaction()
        elif hasattr(self, "editor") and event.type() in (QEvent.FontChange, QEvent.ApplicationFontChange):
            self._update_metrics()
        return super().event(event)

    def hideEvent(self, event) -> None:
        self.cancel_interaction()
        self._hovered = False
        self._hover.set_target(0.0, instant=True)
        self._offset_x.set_target(0.0, instant=True)
        self._offset_y.set_target(0.0, instant=True)
        self._clock.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        t = sticker.theme(self.accent)
        hover = min(1.0, max(0.0, self._hover.value))
        motion = 0.0 if native.reduce_motion() else hover
        ink = QColor(t.text if self.isEnabled() else t.muted)
        if not native.reduce_motion():
            p.translate(max(-2.0, min(2.0, self._offset_x.value)), max(-1.0, min(1.0, self._offset_y.value)))
        p.setPen(ink)
        font = self._number_font()
        p.setFont(font)
        if not self._editing:
            fm = QFontMetricsF(font)
            text = self.text()
            baseline = (self.height() - fm.height()) / 2 + fm.ascent()
            p.save()
            p.translate(self.width() / 2, baseline)
            p.scale(1.0 + 0.02 * motion, 1.0 + 0.02 * motion)
            p.drawText(QPointF(-fm.horizontalAdvance(text) / 2, 0), text)
            p.restore()
        p.setOpacity(hover)
        p.setPen(QPen(ink, 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        cy = self.height() / 2
        for x, direction in ((5.0, -1), (self.width() - 5.0, 1)):
            p.drawLine(QPointF(x - direction * 2, cy - 2.5), QPointF(x + direction * 0.5, cy))
            p.drawLine(QPointF(x + direction * 0.5, cy), QPointF(x - direction * 2, cy + 2.5))
