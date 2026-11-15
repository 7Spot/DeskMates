"""按钮共用的轻反馈：独立推进悬停 / 按压，不接管控件的选中、滑钮或长按状态。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QPainter, QTransform

from widget import native, sounds
from widget.animation import FrameClock, Spring, Tween
from widget.capture_ui import ui_frozen


MOTION_PAD = 2


class ButtonMotion(QObject):
    def __init__(self, widget, margin: float = MOTION_PAD, colors: str = "none"):
        super().__init__(widget)
        self.widget = widget
        self.margin, self.colors = margin, colors
        self.hover = Spring(0.0, 0.16)
        self.press = Spring(0.0, 0.075)
        self._press_elapsed = 0.0
        self._release_pending = False
        self.direction_x = Spring(0.0, 0.16)
        self.direction_y = Spring(0.0, 0.16)
        self.selection = Spring(float(widget.isChecked()), 0.15) if colors == "button" else None
        self.tint = Tween() if colors in ("button", "press") else None
        self.clock = FrameClock(widget, self.tick)
        self._held = False
        self._press_rect = None
        self._sound_ready = False
        self._committing = False
        widget.installEventFilter(self)
        widget.setMouseTracking(True)
        widget.pressed.connect(self._pressed)
        widget.released.connect(self._released)
        widget.toggled.connect(self._selection_changed)
        widget.toggled.connect(self._toggle_sound)
        widget.clicked.connect(self._click_sound)

    def _toggle_sound(self, checked: bool) -> None:
        # nextCheckState 只包住 Qt 接受的点击；setChecked / 状态同步不在这里。
        # 在外部 toggled 回调隐藏或重建控件之前播放，不等后面的 clicked。
        if self._committing and self._sound_ready:
            self._sound_ready = False
            if self.widget.SOUND_KIND == "switch":
                sounds.play("switch-on" if checked else "switch-off")
            elif checked or self.widget.SOUND_KIND in ("toggle", "action"):
                sounds.play("tap")

    def _click_sound(self, *_args) -> None:
        ready, self._sound_ready = self._sound_ready, False
        actionable = not self.widget.isCheckable() or self.widget.SOUND_KIND == "action"
        if ready and actionable and getattr(self.widget, "driver", None) is None:
            sounds.play("tap")

    def _selection_changed(self, *_args) -> None:
        if self.selection is None or not self.widget.isCheckable():
            return
        preview = self._held and self.widget.isCheckable()
        target = float(self.widget.isChecked() or preview)
        instant = (not self.widget.isVisible() or native.reduce_motion()
                   or getattr(self.widget.window(), "_still", False))
        self.selection.set_target(target, instant=instant)
        if not self.selection.settled:
            self.clock.start()
        self.widget.update()

    def sync_selection(self) -> None:
        if self.selection is not None:
            self.selection.set_target(float(self.widget.isChecked()), instant=True)

    def _target(self, state, target: float) -> None:
        state.set_target(target, instant=native.reduce_motion())
        self.widget.update()
        if not state.settled:
            self.clock.start()

    def _pressed(self) -> None:
        if not self.widget.isEnabled() or ui_frozen():
            return
        self._held = True
        self._sound_ready = True
        self._press_elapsed, self._release_pending = 0.0, False
        # 按下后锁住当时的可点区域，视觉收缩不能把边缘的手指 / 鼠标赶出去。
        self._press_rect = self.visual_rect()
        self._target(self.press, 1.0)
        self._color_to(1.0)
        self._selection_changed()

    def _released(self) -> None:
        self._held, self._press_rect = False, None
        # 操作照常立即执行；只让快速点按的视觉收缩完成一个短促脉冲。
        self._release_pending = self.widget.isVisible() and not native.reduce_motion() and self._press_elapsed < 0.08
        if not self._release_pending:
            self._target(self.press, 0.0)
        self._color_to(0.0)
        self._selection_changed()

    def _color_to(self, value: float, instant: bool = False) -> None:
        if self.tint is None or (self.colors == "button" and self.widget.isCheckable()):
            return
        self.tint.set_target(value, instant=instant or native.reduce_motion())
        if not self.tint.settled:
            self.clock.start()

    def _point(self, pos) -> None:
        if self._held:
            return
        r = QRectF(self.widget.rect())
        self._target(self.direction_x, max(-1.0, min(1.0, (pos.x() - r.center().x()) / max(1, r.width() / 2))))
        self._target(self.direction_y, max(-1.0, min(1.0, (pos.y() - r.center().y()) / max(1, r.height() / 2))))

    def cancel(self, instant: bool = False) -> None:
        self._sound_ready = False
        self._release_pending = False
        self._held, self._press_rect = False, None
        driver = getattr(self.widget, "driver", None)
        if driver is not None:
            driver.cancel() if instant else driver.release()
        self.press.set_target(0.0, instant=instant)
        self._color_to(0.0, instant)
        self._selection_changed()
        if instant:
            self.hover.set_target(0.0, instant=True)
            self.direction_x.set_target(0.0, instant=True)
            self.direction_y.set_target(0.0, instant=True)
            self.sync_selection()
            self.clock.stop()
        elif not self.press.settled:
            self.clock.start()
        self.widget.update()

    @property
    def hover_amount(self) -> float:
        return min(1.0, max(0.0, self.hover.value))

    @property
    def press_amount(self) -> float:
        return self.tint.value if self.tint is not None else 0.0

    @property
    def scale(self) -> float:
        if native.reduce_motion():
            return 1.0
        hover = min(1.0, max(0.0, self.hover.value))
        pressed = min(1.0, max(0.0, self.press.value))
        return (1.0 - 0.025 * hover) * (1.0 - pressed) + 0.95 * pressed

    @property
    def paint_scale(self) -> float:
        return self.scale

    def content_rect(self) -> QRectF:
        m = self.margin
        return QRectF(self.widget.rect()).adjusted(m, m, -m, -m)

    @property
    def offset(self) -> QPointF:
        if native.reduce_motion():
            return QPointF()
        r, k = self.content_rect(), self.paint_scale
        mx = max(0.0, min(2.0, self.margin + r.width() * (1 - k) / 2 - 1.0))
        my = max(0.0, min(2.0, self.margin + r.height() * (1 - k) / 2 - 1.0))
        amount = max(self.hover_amount, min(1.0, max(0.0, self.press.value)))
        return QPointF(self.direction_x.value * mx * amount, self.direction_y.value * my * amount)

    def visual_rect(self) -> QRectF:
        return self.transform().mapRect(self.content_rect())

    def hit(self, point) -> bool:
        r = self._press_rect if self._press_rect is not None else self.visual_rect()
        return r.contains(point)

    def transform(self) -> QTransform:
        c = QRectF(self.widget.rect()).center()
        tr = QTransform()
        tr.translate(c.x() + self.offset.x(), c.y() + self.offset.y())
        tr.scale(self.paint_scale, self.paint_scale)
        tr.translate(-c.x(), -c.y())
        return tr

    def painter(self) -> QPainter:
        p = QPainter(self.widget)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setTransform(self.transform())
        return p

    def text_anchor(self, font=None, rect=None) -> QPointF:
        r = self.content_rect() if rect is None else QRectF(rect)
        fm = QFontMetricsF(font or self.widget.font(), self.widget)
        return QPointF(r.center().x(), r.center().y() + (fm.ascent() - fm.descent()) / 2)

    @property
    def text_scale(self) -> float:
        return self.scale

    def draw_text(self, p, text, color, rect=None, font=None) -> None:
        """和底板共用 painter 的缩放 / 位移，内部基线与留白比例固定。"""
        font = QFont(font or self.widget.font())
        anchor = self.text_anchor(font, rect)
        p.save()
        p.setFont(font)
        p.setPen(color)
        width = QFontMetricsF(font, self.widget).horizontalAdvance(text)
        p.drawText(QPointF(anchor.x() - width / 2.0, anchor.y()), text)
        p.restore()

    def tick(self, dt: float) -> bool:
        if ui_frozen():
            return True
        self._press_elapsed += dt
        if self._release_pending and self._press_elapsed >= 0.08:
            self._release_pending = False
            self.press.set_target(0.0)
        springs = [self.hover, self.press, self.direction_x, self.direction_y]
        if self.selection is not None and self.widget.isCheckable():
            springs.append(self.selection)
        tint = self.tint if self.tint is not None and not (self.colors == "button" and self.widget.isCheckable()) else None
        if native.reduce_motion():
            for spring in springs:
                spring.set_target(spring.target, instant=True)
            if tint is not None:
                tint.set_target(tint.target, instant=True)
        else:
            for spring in springs:
                spring.step(dt)
            if tint is not None:
                tint.step(dt)
        self.widget.update()
        return self._release_pending or not all(s.settled for s in springs) or (tint is not None and not tint.settled)

    def eventFilter(self, obj, event) -> bool:
        kind = event.type()
        if ui_frozen() and kind in (QEvent.Enter, QEvent.Leave, QEvent.MouseMove, QEvent.MouseButtonPress,
                                   QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.KeyPress,
                                   QEvent.KeyRelease, QEvent.Wheel, QEvent.WindowDeactivate, QEvent.UngrabMouse):
            # 截图服务接管界面时只保留视觉，不把这段输入送进按钮/长按逻辑。
            event.accept()
            return True
        if kind == QEvent.Show:
            self.sync_selection()
        elif kind == QEvent.Enter and obj.isEnabled():
            if hasattr(event, "position"):
                self._point(event.position())
            self._target(self.hover, 1.0)
        elif kind == QEvent.Leave:
            self._target(self.hover, 0.0)
            if self._held:
                self.cancel()
        elif kind == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._point(event.position())
        elif kind == QEvent.MouseMove:
            if self._held and not self.hit(event.position()):
                self.cancel()
            else:
                self._point(event.position())
        elif kind in (QEvent.Hide, QEvent.EnabledChange, QEvent.UngrabMouse, QEvent.WindowDeactivate):
            if kind != QEvent.EnabledChange or not obj.isEnabled():
                self.cancel(instant=True)
        return False


class MotionMixin:
    MOTION_MARGIN = MOTION_PAD
    MOTION_COLOR = "none"
    MOTION_CLASS = ButtonMotion
    SOUND_KIND = "tap"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.motion = self.MOTION_CLASS(self, self.MOTION_MARGIN, self.MOTION_COLOR)

    def hitButton(self, point) -> bool:
        return self.motion.hit(point)

    def nextCheckState(self) -> None:
        motion = self.motion
        motion._committing = True
        try:
            super().nextCheckState()
        finally:
            motion._committing = False

    def motion_painter(self) -> QPainter:
        return self.motion.painter()
