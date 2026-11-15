"""保留 Cocoa 已提供的细小拖动，其他平台仍使用普通 Qt 鼠标事件。

Qt 6.12 的 lastCursorPosition 用 float fuzzyCompare 去噪，过滤阈值随全局
坐标而变，较远的屏幕位置可能合并很细的移动。公开 native event filter 在
这一层之前观察同一应用的 NSEvent；
这里只补正在拖动的控件，使用屏幕位置而不是另有语义的 deltaX。
"""
from __future__ import annotations

from collections import deque
import ctypes
from dataclasses import dataclass
import math
import time
import weakref

from PySide6.QtCore import QAbstractNativeEventFilter, QPointF
from PySide6.QtGui import QGuiApplication

from widget import native


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


@dataclass(frozen=True)
class _Sample:
    kind: int
    window: int
    timestamp: float
    number: int
    x: float
    y: float


def _sample(event: int) -> _Sample | None:
    """读取公开 NSEvent / NSWindow 属性，不保留 Objective-C 对象。"""
    if not event:
        return None
    msg = native._msg_send
    kind = msg(event, "type", restype=ctypes.c_ulong)
    if kind not in (1, 2, 6):             # leftMouseDown / leftMouseUp / leftMouseDragged
        return None
    window = msg(event, "window")
    if not window:
        return None
    location = msg(event, "locationInWindow", restype=_Point)
    screen = msg(window, "convertPointToScreen:", location,
                 argtypes=(_Point,), restype=_Point)
    stamp = msg(event, "timestamp", restype=ctypes.c_double)
    if not all(math.isfinite(v) for v in (screen.x, screen.y, stamp)):
        return None
    return _Sample(kind, window, stamp,
                   msg(event, "eventNumber", restype=ctypes.c_long), screen.x, screen.y)


class PointerDrag(QAbstractNativeEventFilter):
    """begin/end 随一次拖动；move 返回 True 表示原生路径已处理同一事件。

    on_move(QPointF, monotonic_seconds) 接收与 Qt globalPosition 相同的坐标系。
    Qt 测试事件、无匹配原生按下事件和非 Cocoa 平台自动走调用方的 Qt 回退。
    """

    def __init__(self, owner, on_move):
        super().__init__()
        self._owner = weakref.ref(owner)
        try:
            self._callback = weakref.WeakMethod(on_move)
        except TypeError:
            self._callback = lambda: on_move
        self._active = False
        self._native_origin = None
        self._qt_origin = QPointF()
        self._last_native = None
        self._delivered = deque(maxlen=128)
        owner.destroyed.connect(self.end)

    def begin(self, event) -> None:
        self.end()
        if QGuiApplication.platformName() != "cocoa":
            return
        owner = self._owner()
        if owner is None:
            return
        try:
            app = native._nsapp()
            current = _sample(native._msg_send(app, "currentEvent")) if app else None
            if (current is None or current.kind != 1
                    or int(current.timestamp * 1000) != event.timestamp()):
                return
            window = native._msg_send(int(owner.window().winId()), "window")
            if current.window != window:
                return
        except (OSError, AttributeError, ValueError, RuntimeError):
            return
        self._native_origin = current
        self._qt_origin = QPointF(event.globalPosition())
        self._active = True
        QGuiApplication.instance().installNativeEventFilter(self)

    def end(self, *_args) -> None:
        if self._active:
            app = QGuiApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self)
        self._active = False
        self._native_origin = self._last_native = None
        self._delivered.clear()

    def move(self, event) -> bool:
        if not self._active:
            return False
        point = event.globalPosition()
        stamp = event.timestamp()
        return any(stamp == timestamp and abs(point.x() - x) < 1e-7
                   and abs(point.y() - y) < 1e-7
                   for timestamp, x, y in self._delivered)

    def release_position(self, event) -> QPointF:
        """松手仍取同一次原生拖动的浮点位置；不匹配时保留Qt正常回退。"""
        point = self.native_release_position(event)
        return point if point is not None else QPointF(event.globalPosition())

    def native_release_position(self, event) -> QPointF | None:
        """有匹配的原生MouseUp才返回屏幕浮点坐标；调用方可选择自己的Qt坐标回退。"""
        if self._active:
            try:
                app = native._nsapp()
                current = _sample(native._msg_send(app, "currentEvent")) if app else None
                if (current is not None and current.kind == 2
                        and current.window == self._native_origin.window
                        and int(current.timestamp * 1000) == event.timestamp()):
                    return self._position(current)
            except (OSError, AttributeError, ValueError, RuntimeError):
                pass
        return None

    def _position(self, sample: _Sample) -> QPointF:
        origin = self._native_origin
        return self._qt_origin + QPointF(sample.x - origin.x, origin.y - sample.y)

    def nativeEventFilter(self, event_type, message):
        if not self._active or bytes(event_type) != b"mac_generic_NSEvent":
            return False, 0
        try:
            current = _sample(int(message))
        except (OSError, AttributeError, ValueError, RuntimeError):
            self.end()                   # 无法读取时，后续 Qt 事件照常回退
            return False, 0
        owner = self._owner()
        if owner is None or not owner.isVisible() or not owner.isEnabled():
            self.end()
            return False, 0
        origin = self._native_origin
        if (current is None or current.kind != 6 or current.window != origin.window
                or current.timestamp < origin.timestamp or current == self._last_native):
            return False, 0
        self._last_native = current
        point = self._position(current)
        self._delivered.append((int(current.timestamp * 1000), point.x(), point.y()))
        callback = self._callback()
        if callback is not None:
            callback(point, time.perf_counter())
        else:
            self.end()
        return False, 0                  # 保留 Qt/AppKit 原有捕获、焦点和释放语义
