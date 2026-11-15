"""平台专属调整。全项目只有这里按 sys.platform 分支，不引入 PyObjC。

macOS：Qt.Tool 窗口在应用失焦时会自动隐藏，加 WA_MacAlwaysShowToolWindow 让它常驻。
      mouse_left_down()：用 ctypes 问 CoreGraphics 全局鼠标左键是否按着（焦点不在本程序也算），不需要辅助功能权限，一次 17 微秒。
      现在没人调，留着备用。
      set_all_spaces(window, on)：用 ctypes 调 objc_msgSend 给 NSWindow 的 collectionBehavior 加（或去掉）CanJoinAllSpaces，加上 FullScreenAuxiliary，
      狗和卡片在所有普通桌面（Spaces）都看得见（默认就这样，不可关）。
      set_activation_policy(accessory)：切程序的激活策略。macOS 10.14 起只有 accessory（没有 Dock 图标）的程序，窗口才能盖在别的 App 的全屏空间上；
      Settings 的「小组件全局可见」开着就切成 accessory，关了切回普通（有 Dock 图标）。同时清掉 NSPanel 默认的 MoveToActiveSpace
      （和 CanJoinAllSpaces 互斥，不清 AppKit 直接抛异常崩溃）和 Qt 设的 FullScreenPrimary。Qt 改窗口标志时只动全屏那两位、其余保留，
      所以每次 show 之后再设一次（window.showEvent）。只在 cocoa 平台做，offscreen 测试里是空操作。
      window_occluded(window)：窗口整个看不见（屏幕关了、锁屏、被完全挡住）时窗口暂停动画，省电。
      set_ignores_mouse(window, on)：窗口接不接鼠标（NSWindow.ignoresMouseEvents）。狗窗口每帧按鼠标底下是不是狗来切：点击范围就是狗。
      window_frames / window_frame / window_covered：别的 App 的窗口在哪（CGWindowList，只读位置和大小，不需要录屏权限）：狗跳上窗口用。
      ignore_safe_area(window)：窗口里的东西铺满整个窗口，不躲屏幕顶上那一条（自己建的窗口一建好就调）。
      screen_safe_top(screen)：这块屏顶上被刘海占着、画了也看不全的那一条有多高（NSScreen.safeAreaInsets）。
Windows：留空。以后适配时在 win32 分支里补，并在 Windows 上实测。
"""
import ctypes
import math
import os
import platform
import queue
import sys
import threading
import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

# Qt 的 raise_() 在 Mac 上默认顺手 [NSApp activateIgnoringOtherApps:YES]（环境变量 QT_MAC_SET_RAISE_PROCESS，默认开）：球、窝的前沿每抬到狗前面一次，
# 同桌就被切到前台一次，你在别的 App 里打着的字就断了（真机读回过）。Qt 第一次 raise 时才读它，导入这里时关掉就够；要切前台只走 activate_app。
if sys.platform == "darwin":
    os.environ["QT_MAC_SET_RAISE_PROCESS"] = "0"

_cg = None
_objc = None
# NSWindowCollectionBehavior 的位。NSPanel 默认带 MoveToActiveSpace，它和 CanJoinAllSpaces 互斥，AppKit 校验不过会直接抛异常把进程杀掉，
# 所以加前必须清掉；FullScreenPrimary 和 FullScreenAuxiliary 也互斥（Qt 给普通窗口设的是 Primary）。
CAN_JOIN_ALL_SPACES, MOVE_TO_ACTIVE_SPACE = 1 << 0, 1 << 1
FULL_SCREEN_PRIMARY, FULL_SCREEN_AUXILIARY = 1 << 7, 1 << 8
OCCLUSION_VISIBLE = 1 << 1   # NSWindowOcclusionStateVisible：窗口至少有一部分看得见
TOUCH_SUBTYPE = 3            # NSEventSubtypeTouch：鼠标事件是触摸板发的
MOUSE_EVENT_TYPES = frozenset({1, 2, 5, 6})   # 左键按下、松开、移动、拖动
_PROTOS: dict = {}           # objc_msgSend 按签名铸好的函数，铸一次反复用（窗口每帧都要问一次看不看得见）


_sounds: dict[str, list[int] | None] = {}  # 每种原音三个已载入内存的NSSound；失败记None，避免每次点击重试
_sound_index: dict[str, int] = {}
_sound_queue = None                        # 声音线的队列（start_sound_thread 之后才有）；没有就在调用的地方当场放（单测）
SOUND_LATE_S = 0.15                        # 排队排了这么久还没轮到的不放了：迟到的 tick 比没有更怪
FADE_SOUND_S = 0.08                        # fade_sound：淡掉要多久（秒）
RAMP_STEP_S = 0.015                        # 淡入淡出的音量每隔这么久调一步（声音线上；不睡在那一件事里，后面排着的声音照放）
_ramps: list = []                          # 声音线上正在淡的：[snd, 开始时刻, 多久, 从多少, 到多少, 到了停不停]（只有声音线碰它）


def ramp_volume(v0: float, v1: float, elapsed: float, seconds: float) -> float:
    """淡入淡出走到 elapsed 秒时的音量：从 v0 到 v1，两头缓（smoothstep），seconds 秒走完。"""
    if seconds <= 0.0 or elapsed >= seconds:
        return v1
    u = max(0.0, elapsed / seconds)
    return v0 + (v1 - v0) * u * u * (3.0 - 2.0 * u)


def prepare_sound(path: str) -> bool:
    """预载原音；仅真实cocoa界面使用NSSound，offscreen测试不初始化音频。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    if path not in _sounds:
        pool = []
        try:
            ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
            cls, name = _class(b"NSSound"), _nsstring(path)
            for _ in range(3):
                snd = _msg_send(_msg_send(cls, "alloc"), "initWithContentsOfFile:byReference:", name, False,
                                argtypes=(ctypes.c_void_p, ctypes.c_bool))
                if not snd:
                    raise OSError("NSSound init failed")
                pool.append(snd)
            _sounds[path], _sound_index[path] = pool, 0
        except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
            for snd in pool:
                try:
                    _msg_send(snd, "release", restype=None)
                except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
                    pass
            _sounds[path] = None
    return bool(_sounds[path])


def play_sound(path: str, gain: float = 1.0, offset: float = 0.0, fade_in: float = 0.0) -> bool:
    """音量由原音资源确定；gain供轮盘密集时减轻声音，系统无输出设备不影响界面。offset：从第几秒开始放（充能声音回到圈里接着响）。
    fade_in：从 0 开始、这么多秒拉到 gain（吃喝的声音出来得太突然）。
    有声音线（start_sound_thread）时只是排个队，马上回来（True = 排上了）；没有就当场放，返回放没放成。"""
    if not prepare_sound(path):
        return False
    pool = _sounds[path]
    snd = pool[_sound_index[path] % len(pool)]
    _sound_index[path] += 1
    if _sound_queue is not None:
        _sound_queue.put(("play", snd, gain, time.monotonic(), offset, fade_in))
        return True
    return _play_now(snd, gain, offset)


def _play_now(snd: int, gain: float, offset: float = 0.0, fade_in: float = 0.0) -> bool:
    try:
        _ramps[:] = [r for r in _ramps if r[0] != snd]   # 这一个刚才还在淡：从头放，不接着淡
        _msg_send(snd, "stop", restype=ctypes.c_bool)
        gain = max(0.0, min(1.0, gain))
        _msg_send(snd, "setVolume:", ctypes.c_float(0.0 if fade_in > 0.0 else gain), argtypes=(ctypes.c_float,), restype=None)
        if offset > 0.0:
            _msg_send(snd, "setCurrentTime:", ctypes.c_double(offset), argtypes=(ctypes.c_double,), restype=None)
        ok = bool(_msg_send(snd, "play", restype=ctypes.c_bool))
        if ok and fade_in > 0.0:
            _ramps.append([snd, time.monotonic(), fade_in, 0.0, gain, False])
        return ok
    except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
        return False


def fade_sound(path: str, seconds: float = FADE_SOUND_S) -> None:
    """正在响的这个声音淡掉再停（球出了圈，充能声音不能「咔」一下断；吃完了嚼的声音 0.5 秒淡出）。没有声音线就当场停。"""
    for snd in _sounds.get(path) or ():
        if _sound_queue is not None:
            _sound_queue.put(("fade", snd, seconds, 0.0, 0.0))
        else:
            _stop_now(snd)


def _fade_now(snd: int, seconds: float) -> None:
    """在声音线上：从现在的音量往 0 淡（_step_ramps 一步步走，不睡在这里：后面排着的声音照放），到了停。"""
    try:
        if not _msg_send(snd, "isPlaying", restype=ctypes.c_bool):
            return
        v = float(_msg_send(snd, "volume", restype=ctypes.c_float))
        _ramps[:] = [r for r in _ramps if r[0] != snd]
        _ramps.append([snd, time.monotonic(), seconds, v, 0.0, True])
    except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
        pass


def _step_ramps() -> None:
    """声音线上每 RAMP_STEP_S 秒走一步：正在淡的各调一次音量，淡完的（淡出的顺手停掉）拿走。"""
    now = time.monotonic()
    for r in list(_ramps):
        snd, t0, seconds, v0, v1, stop = r
        elapsed = now - t0
        try:
            _msg_send(snd, "setVolume:", ctypes.c_float(ramp_volume(v0, v1, elapsed, seconds)), argtypes=(ctypes.c_float,), restype=None)
            if elapsed >= seconds:
                _ramps.remove(r)
                if stop:
                    _msg_send(snd, "stop", restype=ctypes.c_bool)
        except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
            if r in _ramps:
                _ramps.remove(r)


def stop_sound(path: str) -> None:
    """只停止已载入的声音；取消反馈不会为此初始化音频后端。"""
    for snd in _sounds.get(path) or ():
        if _sound_queue is not None:
            _sound_queue.put(("stop", snd, 0.0, 0.0))     # 和 play 排同一条队：先后不乱
        else:
            _stop_now(snd)


def _stop_now(snd: int) -> None:
    _ramps[:] = [r for r in _ramps if r[0] != snd]
    try:
        _msg_send(snd, "stop", restype=ctypes.c_bool)
    except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
        pass


def _sound_job(op: str, snd: int, gain: float, at: float, offset: float = 0.0, fade_in: float = 0.0) -> None:
    """声音线上的一件事：停、淡掉再停（gain 这时是淡多久），或者放（排队排太久的不放了）。"""
    if op == "stop":
        _stop_now(snd)
    elif op == "fade":
        _fade_now(snd, gain)
    elif time.monotonic() - at <= SOUND_LATE_S:
        _play_now(snd, gain, offset, fade_in)


def start_sound_thread() -> bool:
    """声音挪到一条后台线上放：NSSound 的 stop + play 每次占 9～15 毫秒（实测，第一次 45），在主线程上放的话滑动条每过一只、
    狗每叫一声都掉一帧。ctypes 调用期间不占着解释器，主线程照常画。只在真的 cocoa 界面开；单测不开，声音照旧当场放。"""
    global _sound_queue
    if _sound_queue is not None:
        return True
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        _load_objc()
        push, pop = _objc.objc_autoreleasePoolPush, _objc.objc_autoreleasePoolPop
        push.restype, push.argtypes, pop.restype, pop.argtypes = ctypes.c_void_p, (), None, (ctypes.c_void_p,)
    except (OSError, AttributeError):
        return False
    jobs = queue.SimpleQueue()

    def run() -> None:
        while True:
            try:
                job = jobs.get(timeout=RAMP_STEP_S if _ramps else None)   # 有在淡的：最多等一步就回来调音量
            except queue.Empty:
                job = None
            mark = push()                                 # 这条线没有自动释放池：每次自己开一个，不然 AppKit 临时建的对象一直攒着
            try:
                if job is not None:
                    _sound_job(*job)
                if _ramps:
                    _step_ramps()
            finally:
                pop(mark)
    threading.Thread(target=run, name="sounds", daemon=True).start()
    _sound_queue = jobs
    return True


def mouse_left_down() -> Optional[bool]:
    """全局鼠标左键现在是否按着；不支持的平台返回 None。"""
    global _cg
    if sys.platform != "darwin":
        return None
    if _cg is None:
        try:
            _cg = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            _cg.CGEventSourceButtonState.restype = ctypes.c_bool
            _cg.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        except (OSError, AttributeError):
            _cg = False
    if not _cg:
        return None
    return bool(_cg.CGEventSourceButtonState(0, 0))   # kCGEventSourceStateCombinedSessionState, kCGMouseButtonLeft


def mouse_any_down() -> Optional[bool]:
    """全局鼠标左键或右键现在是否按着；不支持的平台返回 None。"""
    left = mouse_left_down()
    return None if left is None else bool(left or _cg.CGEventSourceButtonState(0, 1))


_libproc_dll = None
SCREENCAPTURE_SCAN_S = 0.3     # 命令行截图进程多久数一次：要远短于 capture_ui 候选画面留的 1 秒，不然选区出来了才认出来、候选已经过期
_screencapture_cli: dict = {"at": float("-inf"), "pids": frozenset()}


def _libproc():
    global _libproc_dll
    if _libproc_dll is None:
        proc = ctypes.CDLL("/usr/lib/libproc.dylib")
        proc.proc_listpids.argtypes = (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int)
        proc.proc_listpids.restype = ctypes.c_int
        proc.proc_name.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        proc.proc_name.restype = ctypes.c_int
        proc.proc_pidpath.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        proc.proc_pidpath.restype = ctypes.c_int
        _libproc_dll = proc
    return _libproc_dll


def _screencapture_cli_pids() -> Optional[frozenset]:
    """正在跑的命令行截图（进程名 screencapture）；SCREENCAPTURE_SCAN_S 内数过就用上次的。只数本机进程表（七八百个，约 0.7 毫秒），
    不问窗口系统。数不了返回 None（当它可能在）。"""
    now = time.monotonic()
    if now - _screencapture_cli["at"] < SCREENCAPTURE_SCAN_S:
        return _screencapture_cli["pids"]
    try:
        proc = _libproc()
        n = proc.proc_listpids(1, 0, None, 0)                    # PROC_ALL_PIDS：先问要多大；出错返回 0
        if n <= 0:
            return None
        buf = (ctypes.c_int * (n // 4 + 64))()
        n = proc.proc_listpids(1, 0, buf, ctypes.sizeof(buf))
        if n <= 0:
            return None
        name = ctypes.create_string_buffer(64)
        pids = frozenset(p for p in buf[:n // 4] if p > 0 and proc.proc_name(p, name, 64) > 0 and name.value == b"screencapture")
    except (OSError, AttributeError, ValueError, ctypes.ArgumentError):
        return None
    _screencapture_cli.update(at=now, pids=pids)
    return pids


def screenshot_selection_active() -> bool:
    """系统截图选区是否在屏幕上；只读进程ID和窗口尺寸，不读标题、图像或全局按键。
    先看有没有截图的进程（截图服务 com.apple.screencaptureui、命令行的 screencapture），都没有就不问窗口列表：
    问一次要等窗口系统把挂着的窗口改动做完，狗在跑时一次平均 6.5 毫秒、最长 95，开着卡片每秒 36～42 毫秒（量的）。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    windows = None
    try:
        apps = _msg_send(_class(b"NSRunningApplication"), "runningApplicationsWithBundleIdentifier:",
                         _nsstring("com.apple.screencaptureui"), argtypes=(ctypes.c_void_p,))
        count = _msg_send(apps, "count", restype=ctypes.c_ulong)
        pids = {_msg_send(_msg_send(apps, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,)),
                          "processIdentifier", restype=ctypes.c_int) for i in range(count)}
        if not pids and _screencapture_cli_pids() == frozenset():
            return False
        cg = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
        cg.CGWindowListCopyWindowInfo.argtypes = (ctypes.c_uint32, ctypes.c_uint32)
        windows = cg.CGWindowListCopyWindowInfo(17, 0)  # on-screen, excluding desktop
        def value(obj, key):
            return _msg_send(obj, "objectForKey:", _nsstring(key), argtypes=(ctypes.c_void_p,))
        for i in range(_msg_send(windows, "count", restype=ctypes.c_ulong)):
            item = _msg_send(windows, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,))
            layer = _msg_send(value(item, "kCGWindowLayer"), "intValue", restype=ctypes.c_int)
            # 系统选区处于屏幕遮罩层。普通截图编辑窗、缩略图都不锁界面。
            if layer < 1000:
                continue
            pid = _msg_send(value(item, "kCGWindowOwnerPID"), "intValue", restype=ctypes.c_int)
            if pid not in pids:
                # 系统截图也可能由无 bundle 的命令行进程建立选区。
                # 只认系统可执行文件路径，不按可冒充的窗口名称判断。
                path = ctypes.create_string_buffer(4096)
                if _libproc().proc_pidpath(pid, path, len(path)) <= 0 or path.value != b"/usr/sbin/screencapture":
                    continue
            bounds = value(item, "kCGWindowBounds")
            width = _msg_send(value(bounds, "Width"), "doubleValue", restype=ctypes.c_double)
            height = _msg_send(value(bounds, "Height"), "doubleValue", restype=ctypes.c_double)
            # 选区覆盖层覆盖屏幕；排除截图后角落的小缩略图与截图工具条。
            if width >= 300 and height >= 300:
                return True
    except (OSError, AttributeError, ValueError):
        return False
    finally:
        if windows:
            _msg_send(windows, "release", restype=None)
    return False


_cgw = None


SYSTEM_OWNERS = {"WindowManager", "Dock", "Window Server", "Control Center", "Notification Center", "SystemUIServer", "Spotlight"}


def _window_info(option: int, relative: int, owners: bool = False, onscreen: bool = False) -> list[tuple]:
    """CGWindowListCopyWindowInfo 的结果：(窗口号, 进程号, 层, 不透明度, x, y, 宽, 高[, 进程名][, 在不在屏幕上])，从最前到最后。
    只读这几项，不读标题和内容。进程名（owners=True）用来认出台前调度左边那排缩略图（WindowManager 的）。
    在不在屏幕上（onscreen=True）：只按窗口号查一个窗口时，别的桌面上的、最小化的窗口照样查得到、照样报位置
    要看 kCGWindowIsOnscreen 才分得出来（看不见的窗口没有这一项）。"""
    global _cgw
    if _cgw is None:
        _cgw = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        _cgw.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
        _cgw.CGWindowListCopyWindowInfo.argtypes = (ctypes.c_uint32, ctypes.c_uint32)
    out = []
    windows = _cgw.CGWindowListCopyWindowInfo(option, relative)
    if not windows:
        return out
    try:
        keys = {k: _nsstring(k) for k in ("kCGWindowNumber", "kCGWindowOwnerPID", "kCGWindowLayer", "kCGWindowAlpha", "kCGWindowBounds",
                                          "kCGWindowOwnerName", "kCGWindowIsOnscreen", "X", "Y", "Width", "Height")}

        def value(obj, key):
            return _msg_send(obj, "objectForKey:", keys[key], argtypes=(ctypes.c_void_p,))

        def num(obj, key, kind=ctypes.c_double, sel="doubleValue"):
            v = value(obj, key)
            return _msg_send(v, sel, restype=kind) if v else 0
        for i in range(_msg_send(windows, "count", restype=ctypes.c_ulong)):
            item = _msg_send(windows, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,))
            b = value(item, "kCGWindowBounds")
            if not b:
                continue
            row = (num(item, "kCGWindowNumber", ctypes.c_int, "intValue"), num(item, "kCGWindowOwnerPID", ctypes.c_int, "intValue"),
                   num(item, "kCGWindowLayer", ctypes.c_int, "intValue"), num(item, "kCGWindowAlpha"),
                   num(b, "X"), num(b, "Y"), num(b, "Width"), num(b, "Height"))
            if owners:
                name = value(item, "kCGWindowOwnerName")
                text = _msg_send(name, "UTF8String", restype=ctypes.c_char_p) if name else None
                row += ((text or b"").decode("utf-8", "replace"),)
            if onscreen:
                flag = value(item, "kCGWindowIsOnscreen")
                row += (bool(flag) and bool(_msg_send(flag, "boolValue", restype=ctypes.c_bool)),)
            out.append(row)
    finally:
        _msg_send(windows, "release", restype=None)
    return out


def window_frames(exclude_pid: int) -> list[tuple[int, int, float, float, float, float]]:
    """屏幕上看得见的普通窗口（第 0 层、不透明度大于 0、不是自己的）：(窗口号, 进程号, x, y, 宽, 高)，从最前到最后。
    坐标和 Qt 的全局坐标一样（主屏左上角为原点、y 向下、逻辑像素）。只读位置和大小，不需要录屏权限（实测：没有录屏权限的进程读得到，标题读不到）。
    非 cocoa 平台返回空。灵动交互里狗跳上窗口用（widget/roam.py）。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return []
    try:
        rows = _window_info(1 | 16, 0, owners=True)   # kCGWindowListOptionOnScreenOnly | ExcludeDesktopElements
    except (OSError, AttributeError, ValueError):
        return []
    # 台前调度：左边那排缩略图是 WindowManager 的窗口，被缩进去的 App 窗口报的位置大小就是缩略图那一块，和它重合：都不算
    thumbs = {(round(x), round(y), round(w), round(h)) for n, pid, layer, alpha, x, y, w, h, owner in rows if owner == "WindowManager"}
    return [(n, pid, x, y, w, h) for n, pid, layer, alpha, x, y, w, h, owner in rows
            if layer == 0 and alpha > 0.05 and pid != exclude_pid and w > 1 and h > 1 and owner not in SYSTEM_OWNERS
            and (round(x), round(y), round(w), round(h)) not in thumbs]


def window_frame(number: int) -> Optional[tuple[float, float, float, float]]:
    """一个窗口现在的 (x, y, 宽, 高)；不在屏幕上了（关了、最小化、切到别的桌面、藏起来）返回 None。狗站在窗口上时每帧问一次。
    只按窗口号查时看不见的窗口也会报位置，所以要看"在不在屏幕上"那一项（切桌面后狗站在看不见的窗口上、悬在半空）。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    try:
        rows = _window_info(8, number, onscreen=True)   # kCGWindowListOptionIncludingWindow：只要这一个
    except (OSError, AttributeError, ValueError):
        return None
    for n, pid, layer, alpha, x, y, w, h, on in rows:
        if n == number:
            return None if alpha <= 0.05 or not on else (x, y, w, h)
    return None


def window_covered(number: int, x: float, y: float, exclude_pid: int) -> Optional[bool]:
    """这个窗口在 (x, y) 那一点上面有没有别的窗口盖着（狗站的那一截上沿被挡住了）；窗口不在屏幕上了返回 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    try:
        rows = _window_info(2 | 8 | 16, number)  # 这个窗口以上的（OnScreenAboveWindow | IncludingWindow | ExcludeDesktopElements）
    except (OSError, AttributeError, ValueError):
        return None
    if not any(n == number for n, *_ in rows):
        return None
    for n, pid, layer, alpha, wx, wy, ww, wh in rows:
        if n == number or pid == exclude_pid or alpha <= 0.05 or layer != 0:
            continue
        if wx <= x <= wx + ww and wy <= y <= wy + wh:
            return True
    return False


def _load_objc() -> None:
    global _objc
    if _objc is None:
        _objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        _objc.sel_registerName.restype = ctypes.c_void_p
        _objc.sel_registerName.argtypes = [ctypes.c_char_p]


def _msg_send(receiver: int, selector: str, *args, argtypes=(), restype=ctypes.c_void_p):
    """objc_msgSend，按这次调用的签名铸一个函数指针（arm64 上必须签名精确），同一个签名铸一次就记着。"""
    _load_objc()
    key = (restype, tuple(argtypes))
    fn = _PROTOS.get(key)
    if fn is None:
        addr = ctypes.cast(_objc.objc_msgSend, ctypes.c_void_p).value
        fn = _PROTOS[key] = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(addr)
    return fn(receiver, _objc.sel_registerName(selector.encode()), *args)


def pointer_event() -> Optional[tuple[int, float]]:
    """正在处理的左键 / 移动事件：(subtype, pressure)。不是这类事件、读不到返回 None。只问这两个：对鼠标事件都合法，问别的（deviceID、stage）可能抛 ObjC 异常。"""
    if sys.platform != "darwin":
        return None
    try:
        app = _msg_send(_class(b"NSApplication"), "sharedApplication")
        event = _msg_send(app, "currentEvent") if app else None
        if not event or _msg_send(event, "type", restype=ctypes.c_ulonglong) not in MOUSE_EVENT_TYPES:
            return None
        return int(_msg_send(event, "subtype", restype=ctypes.c_short)), float(_msg_send(event, "pressure", restype=ctypes.c_float))
    except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
        return None


def from_trackpad() -> bool:
    """这下点击来自触摸板（NSEventSubtypeTouch）。认不出来一律当鼠标：鼠标的手感不能被误伤。"""
    info = pointer_event()
    return info is not None and info[0] == TOUCH_SUBTYPE


def trackpad_system_drag() -> bool:
    """系统里开了「三指拖移」或「轻点两下拖移」：手指抬起后系统还要拖一小会才发松手。"""
    if sys.platform != "darwin":
        return False
    try:
        defaults = _msg_send(_class(b"NSUserDefaults"), "standardUserDefaults")
        for domain in ("com.apple.AppleMultitouchTrackpad", "com.apple.driver.AppleBluetoothMultitouch.trackpad"):
            settings = _msg_send(defaults, "persistentDomainForName:", _nsstring(domain), argtypes=(ctypes.c_void_p,))
            if not settings:
                continue
            for key in ("TrackpadThreeFingerDrag", "Dragging"):
                value = _msg_send(settings, "objectForKey:", _nsstring(key), argtypes=(ctypes.c_void_p,))
                if value and _msg_send(value, "boolValue", restype=ctypes.c_bool):
                    return True
    except (OSError, AttributeError, ValueError, TypeError, RuntimeError):
        pass
    return False


def _all_spaces_bits(behavior: int, on: bool) -> int:
    wanted = (behavior & ~(MOVE_TO_ACTIVE_SPACE | FULL_SCREEN_PRIMARY)) | FULL_SCREEN_AUXILIARY
    return (wanted | CAN_JOIN_ALL_SPACES) if on else (wanted & ~CAN_JOIN_ALL_SPACES)


def _class(name: bytes) -> int:
    _load_objc()
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    return _objc.objc_getClass(name)


def reveal_in_finder(path: str) -> bool:
    """在访达里选中 path，并让访达到前面来（在别的 App 的全屏空间里也会切过去）。成功返回 True；非 cocoa 平台返回 False。
    在全屏的空间里点「在访达中显示」不跳过去——macOS 14 起，程序自己不在前台时叫不动别的程序到前台，
    卡片打开时又特意不激活程序（跳桌面那个修法），访达就留在别的桌面上。所以先把自己激活（卡片在所有空间里，激活不会跳走），
    再用系统的「在访达中显示」（NSWorkspace activateFileViewerSelectingURLs）。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        app = _nsapp()
        if app:
            _msg_send(app, "activateIgnoringOtherApps:", True, argtypes=(ctypes.c_bool,), restype=None)
        text = _msg_send(_class(b"NSString"), "stringWithUTF8String:", path.encode("utf-8"), argtypes=(ctypes.c_char_p,))
        url = _msg_send(_class(b"NSURL"), "fileURLWithPath:", text, argtypes=(ctypes.c_void_p,))
        urls = _msg_send(_class(b"NSArray"), "arrayWithObject:", url, argtypes=(ctypes.c_void_p,))
        ws = _msg_send(_class(b"NSWorkspace"), "sharedWorkspace")
        if not (url and urls and ws):
            return False
        _msg_send(ws, "activateFileViewerSelectingURLs:", urls, argtypes=(ctypes.c_void_p,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def mac_languages() -> tuple[str, list[str]]:
    """直接问 macOS：这个程序的「当前地区」标识（CFLocaleCopyCurrent）和用户的首选语言（CFLocaleCopyPreferredLanguages）。
    第一次打开按首选语言定界面语言（打包的 app 里 Qt 说系统语言是 C，中文系统第一次打开是英文）。
    不是 cocoa（offscreen 单测：不随跑在哪台机器上变）、读不到：("", [])。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return "", []
    try:
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        cf.CFLocaleCopyCurrent.restype = ctypes.c_void_p
        cf.CFLocaleGetIdentifier.restype, cf.CFLocaleGetIdentifier.argtypes = ctypes.c_void_p, [ctypes.c_void_p]
        cf.CFLocaleCopyPreferredLanguages.restype = ctypes.c_void_p
        cf.CFArrayGetCount.restype, cf.CFArrayGetCount.argtypes = ctypes.c_long, [ctypes.c_void_p]
        cf.CFArrayGetValueAtIndex.restype, cf.CFArrayGetValueAtIndex.argtypes = ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_long]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        cf.CFRelease.argtypes = [ctypes.c_void_p]

        def text(ref) -> str:
            buf = ctypes.create_string_buffer(256)
            return buf.value.decode() if ref and cf.CFStringGetCString(ref, buf, 256, 0x08000100) else ""

        loc = cf.CFLocaleCopyCurrent()
        current = text(cf.CFLocaleGetIdentifier(loc))
        cf.CFRelease(loc)
        arr = cf.CFLocaleCopyPreferredLanguages()
        langs = [text(cf.CFArrayGetValueAtIndex(arr, i)) for i in range(cf.CFArrayGetCount(arr))]
        cf.CFRelease(arr)
        return current, langs
    except (OSError, AttributeError, ValueError):
        return "", []


def reduce_motion() -> bool:
    """系统设置里开了「减少动态效果」：标题行的胶囊宽度直接到位、放不下的字不滚，只留省略号。读不到当没开。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        ws = _msg_send(_class(b"NSWorkspace"), "sharedWorkspace")
        return bool(ws) and bool(_msg_send(ws, "accessibilityDisplayShouldReduceMotion", restype=ctypes.c_bool))
    except (OSError, AttributeError, ValueError):
        return False


def color_panel_all_spaces() -> bool:
    """系统取色面板（QColorDialog 用的 NSColorPanel，整个程序共用一个）也放到所有桌面上。
    点设置会跳到一个固定的桌面——程序的窗口里只要有一个只待在某个桌面上，程序一被激活 macOS 就切过去；取色面板是其中一个。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        panel = _msg_send(_class(b"NSColorPanel"), "sharedColorPanel")
        if not panel:
            return False
        behavior = _msg_send(panel, "collectionBehavior", restype=ctypes.c_ulong)
        wanted = _all_spaces_bits(behavior, True)
        if wanted != behavior:
            _msg_send(panel, "setCollectionBehavior:", wanted, argtypes=(ctypes.c_ulong,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def set_all_spaces(window: QWidget, on: bool = True) -> bool:
    """on：这个顶层窗口出现在所有桌面（Spaces）和全屏 App 上面；off：只待在它自己的桌面。成功返回 True；非 cocoa 平台不做事。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        view = int(window.winId())                       # cocoa 上 winId 是 NSView*
        nswindow = _msg_send(view, "window")
        if not nswindow:
            return False
        behavior = _msg_send(nswindow, "collectionBehavior", restype=ctypes.c_ulong)
        wanted = _all_spaces_bits(behavior, on)
        if wanted != behavior:
            _msg_send(nswindow, "setCollectionBehavior:", wanted, argtypes=(ctypes.c_ulong,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def ignore_safe_area(window: QWidget) -> None:
    """窗口里的东西铺满整个窗口，不躲屏幕顶上那一条。
    Qt 默认把窗口的安全区算进内容边距：带刘海的屏上，窗口顶边一进最上面那一条（约 32 点），排版就把里面的画布往下挤、挤矮
    （真机读回过：窗口顶在屏幕最上沿时，零边距的 QVBoxLayout 里的子控件从 y=32 开始）。狗、「···」跟着画低了，
    按窗口坐标算的点击范围（input._update_hit）、地面线却还按没挤算：看到的和点得到的差出这一截。
    这些窗口都在菜单栏上面一层、画在哪自己算，不要这层安全区。tests/test_safe_area.py 查着每个自己建的窗口都调了。"""
    window.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)


class _NSRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("w", ctypes.c_double), ("h", ctypes.c_double)]


class _NSEdgeInsets(ctypes.Structure):
    _fields_ = [("top", ctypes.c_double), ("left", ctypes.c_double), ("bottom", ctypes.c_double), ("right", ctypes.c_double)]


_safe_tops: dict = {}   # screen_safe_top 读过的：(屏的 x, y, 宽, 高) → 高度。「···」每帧都要问


def screen_safe_top(screen) -> int:
    """这块屏顶上被刘海占着的那一条有多高（逻辑像素，NSScreen.safeAreaInsets.top）：刘海那一块没有像素，画在这一条里的东西可能看不见。
    菜单栏显示着时这一条在菜单栏里面（availableGeometry 已经让开了）；菜单栏自动隐藏时 availableGeometry 不让，要靠这个。
    没有刘海、读不出来、非 cocoa 平台（单测）、不是 Apple 芯片（结构体返回值的调用约定不一样）都是 0。每块屏读一次就记着。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa" or platform.machine() != "arm64":
        return 0
    g = screen.geometry()
    key = (g.x(), g.y(), g.width(), g.height())
    if key in _safe_tops:
        return _safe_tops[key]
    top = 0
    try:
        screens = _msg_send(_class(b"NSScreen"), "screens")
        count = _msg_send(screens, "count", restype=ctypes.c_ulong) if screens else 0
        if count:
            main = _msg_send(screens, "objectAtIndex:", 0, argtypes=(ctypes.c_ulong,))
            main_h = _msg_send(main, "frame", restype=_NSRect).h      # Cocoa 的 y 从主屏底边往上算，Qt 的从主屏顶边往下
            selector = _objc.sel_registerName(b"safeAreaInsets")
            for i in range(count):
                s = _msg_send(screens, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,))
                f = _msg_send(s, "frame", restype=_NSRect)
                if (round(f.x), round(main_h - f.y - f.h), round(f.w), round(f.h)) != key:
                    continue
                if _msg_send(s, "respondsToSelector:", selector, argtypes=(ctypes.c_void_p,), restype=ctypes.c_bool):
                    top = max(0, math.ceil(_msg_send(s, "safeAreaInsets", restype=_NSEdgeInsets).top))
                break
    except (OSError, AttributeError, ValueError):
        top = 0
    _safe_tops[key] = top
    return top


POLICY_REGULAR, POLICY_ACCESSORY = 0, 1   # NSApplicationActivationPolicy


def _nsapp() -> Optional[int]:
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    _load_objc()
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    return _msg_send(_objc.objc_getClass(b"NSApplication"), "sharedApplication")


def set_activation_policy(accessory: bool) -> bool:
    """accessory：没有 Dock 图标、不在 Cmd+Tab 里，窗口能盖在别的 App 的全屏空间上；否则普通程序。成功返回 True。"""
    app = _nsapp()
    if not app:
        return False
    policy = POLICY_ACCESSORY if accessory else POLICY_REGULAR
    if activation_policy() == policy:
        return True
    return bool(_msg_send(app, "setActivationPolicy:", policy, argtypes=(ctypes.c_long,), restype=ctypes.c_bool))


def activation_policy() -> Optional[int]:
    """现在的激活策略（0 普通、1 accessory）；非 cocoa 平台 None。"""
    app = _nsapp()
    return int(_msg_send(app, "activationPolicy", restype=ctypes.c_long)) if app else None


def _nsstring(text: str) -> int:
    _load_objc()
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    return _msg_send(_objc.objc_getClass(b"NSString"), "stringWithUTF8String:", text.encode(), argtypes=(ctypes.c_char_p,))


def _content_layers(window: QWidget) -> list[int]:
    """窗口画面所在的 layer：视图自己的那一层，加上它下面一层的子 layer。
    换 Metal 以后 Qt 给视图的是个壳（QContainerLayer），画面在它里面那层 CAMetalLayer 上；普通画法的窗口没有子 layer。"""
    layer = _msg_send(int(window.winId()), "layer")
    if not layer:
        return []
    out = [layer]
    subs = _msg_send(layer, "sublayers")
    for i in range(_msg_send(subs, "count", restype=ctypes.c_ulong) if subs else 0):
        out.append(_msg_send(subs, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,)))
    return out


def pin_contents_to_bottom(window: QWidget) -> bool:
    """窗口改高度的那一帧，新画面和新的窗口大小不一定同一拍到，macOS 先拿手上那张画面按 layer 的 contentsGravity 摆：默认 resize 是拉伸
    （在"原地跳切捡回"时看到狗突然纵向拉长）。要的是钉在底边、不缩放（窗口都是底边不动，顶边长高、缩回）。
    gravity 名字里的上下按 layer 自己的纵轴算：Qt 的视图坐标是上下颠倒的（contentsAreFlipped，真机读回来是 True），这时 bottomLeft 钉的是顶边——
    拍的视频：拎着时窗口长到最高，落地 1.5 秒后一步缩回，那一帧整只狗连「···」在高出（最高 − 平时）的地方多出一份。所以颠倒时用 topLeft。
    画面所在的每一层都设（_content_layers），各按各的颠倒不颠倒。
    要在原生窗口建好之后调（showEvent），Qt 重建窗口（改标志）后再调一次。成功返回 True；非 cocoa 平台不做事。"""
    return pin_contents(window, left=True, bottom=True)


def pin_contents(window: QWidget, left: bool = True, bottom: bool = True) -> bool:
    """窗口改大小那一帧旧画面（或早到的新画面）钉在不动的那个角：左 / 右、底 / 顶（平时左下，pin_contents_to_bottom）。
    窗口铺宽时只往左边、往下长就换成右边、顶边（window._pin_corner）。颠倒的视图上下反过来（见 pin_contents_to_bottom）。
    成功返回 True；非 cocoa 平台不做事。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        layers = _content_layers(window)
        for layer in layers:
            flipped = bool(_msg_send(layer, "contentsAreFlipped", restype=ctypes.c_bool))
            v = ("top" if bottom else "bottom") if flipped else ("bottom" if bottom else "top")
            _msg_send(layer, "setContentsGravity:", _nsstring(v + ("Left" if left else "Right")), argtypes=(ctypes.c_void_p,), restype=None)
        return bool(layers)
    except (OSError, AttributeError, ValueError):
        return False


def contents_gravity(window: QWidget) -> Optional[str]:
    """读回窗口画面那一层的 contentsGravity（自测用；有子 layer 读最里面那层）；非 cocoa 平台 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    layers = _content_layers(window)
    if not layers:
        return None
    s = _msg_send(_msg_send(layers[-1], "contentsGravity"), "UTF8String", restype=ctypes.c_char_p)
    return s.decode() if s else None


def window_occluded(window: QWidget) -> bool:
    """窗口整个看不见：屏幕关了、锁屏、屏保、被别的窗口完全挡住（NSWindow.occlusionState 没有 Visible 位）。
    窗口每帧问一次，看不见就不算也不画（省电，以前屏幕关着也照样每秒 60 帧）。非 cocoa 平台、问不到时当看得见。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        nswindow = _msg_send(int(window.winId()), "window")
        if not nswindow:
            return False
        return not _msg_send(nswindow, "occlusionState", restype=ctypes.c_ulong) & OCCLUSION_VISIBLE
    except (OSError, AttributeError, ValueError):
        return False


def supports_ignores_mouse() -> bool:
    """这个平台能不能按窗口切接不接鼠标（点击范围就是狗靠它）。目前只有 macOS。"""
    return sys.platform == "darwin" and QGuiApplication.platformName() == "cocoa"


def set_ignores_mouse(window: QWidget, on: bool) -> bool:
    """on：这个窗口不接鼠标，点击、滚轮、右键直接落到后面的窗口（NSWindow.ignoresMouseEvents）；off：照常接。
    狗窗口每帧按鼠标底下是不是狗来切（点击范围就是狗，透明的地方点下去穿到后面）。Qt 自己在设窗口标志时（建原生窗口、
    setWindowFlag）按 WindowTransparentForInput 设它，会把这里设的冲掉：所以 showEvent 把 _accepting 清掉，下一帧重说。成功返回 True；非 cocoa 平台不做事。"""
    if not supports_ignores_mouse():
        return False
    try:
        nswindow = _msg_send(int(window.winId()), "window")
        if not nswindow:
            return False
        _msg_send(nswindow, "setIgnoresMouseEvents:", bool(on), argtypes=(ctypes.c_bool,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


# 窗口层级（NSWindow.level），从后到前。同一层里谁在前系统会自己改：点哪个窗口就把它提到这一层最前，切桌面时也会重排
# （一切桌面盆就跑到窝后面）→ 要一直保持的前后都分在不同的层，由窗口系统管着，不靠代码一下下去排。
# 全在菜单栏（24）上面（狗站到贴着屏幕顶的窗口上，头伸进菜单栏那一条也画在上面；狗的窗口只有狗身上接鼠标，别处照常点得到菜单）、
# 弹出菜单（101）下面。物件分两档（things.tier：盆在前，窝、狗屋在后），每一档上面跟着「在这一档的物件里的狗」和这一档的前沿（窝沿、盆沿）：
# 狗趴在窝里 = 窝 < 狗 < 窝沿 < 盆；平时狗在所有物件前面。
LEVEL_RING = 25                # 捡球的圈（地上的烟）：谁都在它前面
LEVEL_THING = (26, 29)         # 物件：后一档（狗窝、狗屋）、前一档（盆；落地扬的灰也在这层）。同一档里新摆的、点过的在前（显示、按下都提到这一层最前）
LEVEL_DOG_IN = (27, 30)        # 狗（主窗口和每块屏的另一半）在这一档的物件里：那件的前沿显示着（things.rims_changed）
LEVEL_RIM = (28, 31)           # 前沿：盖在里面的狗前面
LEVEL_DOG = LEVEL_DOG_IN[-1]   # 平时的狗：在所有物件前面（在盆边吃喝也是这层，盆沿在它前面）
LEVEL_BALL = 32                # 球：在狗、前沿前面
LEVEL_TOP = 33                 # 狗说话的气泡、右键的小胶囊
NONACTIVATING_PANEL = 1 << 7       # NSWindowStyleMaskNonactivatingPanel


def set_no_activate(window: QWidget) -> bool:
    """点这个窗口不把程序切到前台（没停稳就抓起来甩会卡）。点到狗、球时程序被激活，要是又在另一块屏上，系统要切换前台程序和活跃屏幕，
    忙半秒左右，这段时间主线程干什么都要等：对比测过，每次甩卡住的时间 164 毫秒 → 11 毫秒。也不抢你正在用的 App 的焦点。
    只改样式系统不认（窗口建好以后改不生效），要再调 _setPreventsActivation:（未公开）；没有这个接口就只改样式，不会崩。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        _load_objc()
        nswindow = _msg_send(int(window.winId()), "window")
        if not nswindow:
            return False
        mask = _msg_send(nswindow, "styleMask", restype=ctypes.c_ulong)
        _msg_send(nswindow, "setStyleMask:", mask | NONACTIVATING_PANEL, argtypes=(ctypes.c_ulong,), restype=None)
        selector = _objc.sel_registerName(b"_setPreventsActivation:")
        if _msg_send(nswindow, "respondsToSelector:", selector, argtypes=(ctypes.c_void_p,), restype=ctypes.c_bool):
            _msg_send(nswindow, "_setPreventsActivation:", True, argtypes=(ctypes.c_bool,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def activate_app() -> bool:
    """把同桌切到前台（NSApp activateIgnoringOtherApps:）。设置卡片点了不切（set_no_activate），只在非切不可的那一下调：
    打开系统取色器（NSColorPanel 程序不在前台时自己藏起来）、card.TYPE_ACTIVATES 开着时开始打字。切的那一下系统要换前台程序，主线程等半秒左右。"""
    app = _nsapp()
    if not app:
        return False
    try:
        _msg_send(app, "activateIgnoringOtherApps:", True, argtypes=(ctypes.c_bool,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def app_active() -> Optional[bool]:
    """同桌现在是不是前台程序；非 cocoa 平台 None。"""
    app = _nsapp()
    if not app:
        return None
    try:
        return bool(_msg_send(app, "isActive", restype=ctypes.c_bool))
    except (OSError, AttributeError, ValueError):
        return None


def make_key(window: QWidget) -> Optional[bool]:
    """让这个窗口接键盘（成为 key window），不切前台：set_no_activate 过的窗口（NSPanel 那种不激活的）可以这样，别的 App 还在前台。
    返回之后它是不是 key window；非 cocoa 平台 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    try:
        nswindow = _msg_send(int(window.winId()), "window")
        if not nswindow:
            return None
        if not _msg_send(nswindow, "isKeyWindow", restype=ctypes.c_bool):
            _msg_send(nswindow, "makeKeyWindow", restype=None)
        return bool(_msg_send(nswindow, "isKeyWindow", restype=ctypes.c_bool))
    except (OSError, AttributeError, ValueError):
        return None


def warm_audio() -> None:
    """在后台把系统的声音服务初始化好（约 100 毫秒）：不然第一次放声音（狗第一次撞到东西）时主线程卡在这。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return

    def run() -> None:
        class Format(ctypes.Structure):
            _fields_ = [("rate", ctypes.c_double), ("id", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("bpp", ctypes.c_uint32), ("fpp", ctypes.c_uint32),
                        ("bpf", ctypes.c_uint32), ("channels", ctypes.c_uint32), ("bits", ctypes.c_uint32), ("reserved", ctypes.c_uint32)]
        try:
            toolbox = ctypes.CDLL("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox")
            callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(lambda *_: None)
            queue = ctypes.c_void_p()
            pcm = Format(44100.0, 0x6C70636D, 0xC, 4, 1, 4, 2, 16, 0)     # 'lpcm'，16 位整数
            if toolbox.AudioQueueNewOutput(ctypes.byref(pcm), callback, None, None, None, 0, ctypes.byref(queue)) == 0 and queue:
                toolbox.AudioQueueDispose(queue, True)
        except (OSError, AttributeError, ValueError):
            pass
    threading.Thread(target=run, name="warm-audio", daemon=True).start()


def set_level(window: QWidget, level: int) -> bool:
    """窗口放到第 level 层（上面的 LEVEL_*）。Qt 改窗口标志、重新显示时会按自己的规矩重设层级，所以每次 show 之后再设一次。
    成功返回 True；非 cocoa 平台不做事。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return False
    try:
        nswindow = _msg_send(int(window.winId()), "window")
        if not nswindow:
            return False
        _msg_send(nswindow, "setLevel:", int(level), argtypes=(ctypes.c_long,), restype=None)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def window_number(window: QWidget) -> Optional[int]:
    """NSWindow 的窗口号（和 CGWindowList 里的同一个号；自测读回前后用）；非 cocoa 平台 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    nswindow = _msg_send(int(window.winId()), "window")
    return int(_msg_send(nswindow, "windowNumber", restype=ctypes.c_long)) if nswindow else None


def window_level(window: QWidget) -> Optional[int]:
    """读回 NSWindow 的层级（自测用）；非 cocoa 平台 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    nswindow = _msg_send(int(window.winId()), "window")
    return int(_msg_send(nswindow, "level", restype=ctypes.c_long)) if nswindow else None


def ignores_mouse(window: QWidget) -> Optional[bool]:
    """读回 NSWindow.ignoresMouseEvents（自测用）；非 cocoa 平台 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    nswindow = _msg_send(int(window.winId()), "window")
    return bool(_msg_send(nswindow, "ignoresMouseEvents", restype=ctypes.c_bool)) if nswindow else None


def collection_behavior(window: QWidget) -> Optional[int]:
    """读回 NSWindow 的 collectionBehavior（自测用）；非 cocoa 平台 None。"""
    if sys.platform != "darwin" or QGuiApplication.platformName() != "cocoa":
        return None
    nswindow = _msg_send(int(window.winId()), "window")
    return int(_msg_send(nswindow, "collectionBehavior", restype=ctypes.c_ulong)) if nswindow else None


def apply(window: QWidget) -> None:
    if sys.platform == "darwin":
        window.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)   # 是否全局可见在 showEvent 里设（这时原生窗口还会被 Qt 重建）
    elif sys.platform.startswith("win"):
        pass  # TODO(Windows): 未验证。先在 Windows 上跑一遍验收清单再补。
