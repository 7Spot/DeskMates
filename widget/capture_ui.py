"""截图选区只锁界面图层，狗的实时场景继续绘制。

识别 macOS 截图服务的可见选区窗口，不读取全局按键或其他窗口内容。
失焦/移出前留一份短时候选画面，系统选区真正出现才启用；日常悬停没有延迟。
狗那一层的窗口（每块屏一个的另一半狗、球、捡球的圈：owner.live_windows()）不抓、不换成快照：它们照常画，
抓一次要把它们整个重画一遍读回来（开着卡片时一次 6～11 毫秒，每秒六次）。
"""
from __future__ import annotations

from dataclasses import dataclass
import time
import weakref

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from widget import native

_frozen = False


def ui_frozen() -> bool:
    return _frozen


@dataclass
class _Snapshot:
    rect: QRect
    image: QPixmap
    opacity: float = 1.0
    source: weakref.ReferenceType[QWidget] | None = None  # 狗的overlay没有source，不能让狗一起透明
    tooltip: bool = False


class _FrozenLayer(QWidget):
    def __init__(self, shot: _Snapshot):
        kind = Qt.ToolTip if shot.tooltip else Qt.Tool
        super().__init__(None, kind | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.NoDropShadowWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.image = shot.image
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        native.apply(self)
        self.setGeometry(shot.rect)
        self.setWindowOpacity(shot.opacity)
        self.show()
        native.set_all_spaces(self)
        native.set_ignores_mouse(self, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(QPoint(), self.image)


class CaptureUI(QObject):
    """一个应用一个控制器。begin/end 可直接测试，不依赖系统截图权限。"""
    CANDIDATE_SECONDS = 1.0

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.layers = []
        self.active = False
        self._cached = []
        self._cached_at = 0.0
        self._capturing = False
        self._absent_at = None
        self._muted = []
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.poll)
        app = QApplication.instance()
        self.enabled = app.platformName() == "cocoa"
        self._listening = False
        if self.enabled:
            self._listen(True)
            app.aboutToQuit.connect(self.end)
            self.timer.start()

    def _listen(self, enabled):
        if enabled == self._listening:
            return
        app = QApplication.instance()
        if enabled:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
        self._listening = enabled

    def _live(self) -> set:
        """狗那一层的窗口：截图时照常画（见文件开头）。"""
        return set(self.owner.live_windows())

    def _snapshots(self, disappearing=None):
        self._capturing = True
        shots = []
        try:
            live = self._live()
            if self.owner.isVisible() and self.owner._overlay_needed():
                pm = QPixmap(self.owner.size() * self.owner.devicePixelRatioF())
                pm.setDevicePixelRatio(self.owner.devicePixelRatioF())
                pm.fill(Qt.transparent)
                painter = QPainter(pm)
                self.owner._overlay(painter)
                painter.end()
                shots.append(_Snapshot(QRect(self.owner.mapToGlobal(QPoint()), self.owner.size()), pm))
            for w in QApplication.topLevelWidgets():
                if w is self.owner or w in live or isinstance(w, _FrozenLayer) or (not w.isVisible() and w is not disappearing):
                    continue
                shots.append(_Snapshot(QRect(w.mapToGlobal(QPoint()), w.size()), w.grab(), w.windowOpacity(), weakref.ref(w),
                                       w.windowType() == Qt.ToolTip))
        finally:
            self._capturing = False
        return shots

    def _has_candidate(self):
        return bool(self._cached) and time.monotonic() - self._cached_at < self.CANDIDATE_SECONDS

    def _owner_flinging(self) -> bool:
        """狗被拎着、在空中：不问系统、不抓画面（问一次要等系统回话，抓画面要读显卡，真甩的时候一次能卡一百多毫秒）。"""
        flinging = getattr(self.owner, "_flinging", None)
        return flinging is not None and flinging()

    def remember(self, disappearing=None):
        if not self.active and not self._capturing and not self._has_candidate() and not self._owner_flinging():
            # 同一串 Leave/Deactivate/气泡 Hide 只留第一张；后续事件不能
            # 用已失去悬停或气泡的画面覆盖它。真实输入到来后再重新取样。
            self._cached = self._snapshots(disappearing)
            self._cached_at = time.monotonic()

    def _clear_candidate(self):
        self._cached.clear()
        self._cached_at = 0.0

    def _mute(self, window):
        """只藏原窗口的视觉，保留页面/焦点/下载状态；销毁的Qt对象不再操作。"""
        if window is self.owner or isinstance(window, _FrozenLayer):
            return
        if any(source() is window for source, _opacity in self._muted):
            return
        try:
            self._muted.append((weakref.ref(window), window.windowOpacity()))
            window.setWindowOpacity(0.0)
        except RuntimeError:
            pass

    def begin(self):
        global _frozen
        if self.active:
            return
        shots = self._cached if self._has_candidate() else self._snapshots()
        self._listen(True)
        self.active = _frozen = True
        # 先保存视觉，再取消真实操作；截图拖选不能触发退出/缩放/跳跃。
        for w in QApplication.allWidgets():
            driver = getattr(w, "driver", None)
            if driver is not None and hasattr(driver, "cancel"):
                driver.cancel()
            if isinstance(w, QAbstractButton):
                w.setDown(False)
            cancel = getattr(w, "cancel_interaction", None)
            if cancel is not None:
                cancel()
        self.owner._drag = self.owner._global_press = None
        self.owner.hover.press, self.owner.hover.post_press = False, None
        # topLevelWidgets不是叠放顺序。气泡必须留在卡片之上，不能统一降为Tool。
        shots = sorted(shots, key=lambda shot: shot.tooltip)
        self.layers = [_FrozenLayer(shot) for shot in shots]
        for shot, layer in zip(shots, self.layers):
            if shot.tooltip:
                layer.raise_()
        for shot in shots:
            source = shot.source() if shot.source is not None else None
            if source is not None:
                self._mute(source)          # 不能让半透明阴影/淡入窗口在快照下面再叠画一次
        self.owner.view.refresh()
        self._absent_at = None
        self.timer.setInterval(40)

    def end(self):
        global _frozen
        if not self.active:
            return
        self.active = _frozen = False
        if not self.enabled:
            self._listen(False)
        for source, opacity in self._muted:
            window = source()
            if window is not None:
                try:
                    window.setWindowOpacity(opacity)
                except RuntimeError:       # 冻结期间可能关闭、deleteLater或重建了这张卡片
                    pass
        self._muted.clear()
        for layer in self.layers:
            layer.hide()
            layer.deleteLater()
        self.layers.clear()
        self._clear_candidate()
        self.timer.setInterval(80)
        # 恢复后按真实指针位置重新对齐，不补放截图期间积累的动画时间。
        for w in QApplication.allWidgets():
            motion = getattr(w, "motion", None)
            if motion is not None:
                motion.cancel(instant=True)
                sync_hover = getattr(motion, "sync_hover", None)
                if sync_hover is not None:
                    sync_hover()  # 有局部命中区域的控件（更新胶囊）自行恢复悬停
                elif w.isVisible() and w.isEnabled() and motion.hit(w.mapFromGlobal(QCursor.pos())):
                    motion._point(w.mapFromGlobal(QCursor.pos()))
                    motion._target(motion.hover, 1.0)
        self.owner._cursor_at = None
        self.owner._last_tick = time.perf_counter()
        self.owner._dirty = True
        self.owner.view.refresh()

    def poll(self):
        if self._capturing or (not self.active and self._owner_flinging()):
            return
        if native.screenshot_selection_active():
            self._absent_at = None
            self.begin()
        elif self.active:
            # 完成/取消后保留最后两三帧，让系统完成截图合成。
            now = time.monotonic()
            if self._absent_at is None:
                self._absent_at = now
            elif now - self._absent_at >= .12:
                self.end()

    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.owner and kind in (QEvent.Hide, QEvent.Close):
            self.end()
        if self._capturing or isinstance(obj, _FrozenLayer):
            return False
        if self.enabled and not self.active and isinstance(obj, QWidget):
            if kind == QEvent.Hide and obj.windowType() == Qt.ToolTip:
                # 气泡的50ms鼠标看门定时器可能先于80ms选区检测把它藏掉。
                # Hide派发时visible已是False，但自身hideEvent尚未重置绘制状态。
                self.remember(disappearing=obj)
                self.poll()
            elif obj.isVisible() and kind in (QEvent.WindowDeactivate, QEvent.Leave):
                self.remember()
                self.poll()
            elif self._cached and kind in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress):
                self.poll()
                if not self.active:
                    self._clear_candidate()  # 正常移到别处或继续操作，不能带回旧气泡
        if self.active and kind in (QEvent.Enter, QEvent.Leave, QEvent.MouseMove, QEvent.MouseButtonPress,
                                    QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.Wheel,
                                    QEvent.KeyPress, QEvent.KeyRelease, QEvent.ContextMenu, QEvent.NativeGesture):
            return True
        return False
