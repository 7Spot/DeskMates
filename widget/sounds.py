"""所有声音的唯一入口和两个音量（分开的）：高级设置里的「界面音效」（按钮、开关、滑杆的 tick 这些，set_volume）
和「媒体音效」（狗叫、球碰撞、落地这些，set_pack_volume；代码里叫同桌音效）。音量 0..10 档，静音另记（静音前的那一档记着，取消静音回去）。
档位按听起来一样大的台阶换成增益（gain：响度大约跟振幅的 0.6 次方走，所以每一档加的响度一样）。
播放用户选定的原音，运行时不生成或归一化。界面音效在这里；模型自己的声音在模型包里，widget/voice.py 按事件挑好文件，从 play_file 放。"""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Iterable

import config
from widget import native
from widget.capture_ui import ui_frozen


RENAME_DURATIONS = {"enter": 0.078, "type": 0.024, "limit": 0.175, "done": 0.065}
FILES = {name: config.ROOT / "assets" / "sounds" / f"{name}.wav"
         for name in ("tap", "switch-on", "switch-off", "complete", "tick", "size-fine", "size-snap",
                      *(f"rename-{kind}" for kind in RENAME_DURATIONS))}
STEPS = 10                                 # 音量几档（只有 10 档）
LOUDNESS = 0.6                             # 听起来多响 ∝ 振幅 ^ 0.6（Stevens）：gain = (档 / 10) ^ (1 / 0.6)，每一档加的响度一样
_enabled = True                            # 界面音效响不响（音量 > 0 且没静音）；单测直接改它
_pack_enabled = True                       # 同桌音效（媒体音效）响不响
_gain = 1.0                                # 界面音效现在的增益
_pack_gain = 1.0                           # 媒体音效现在的增益
_extra: set[Path] = set()                  # 模型包的声音（register）：开着时预载，关掉时全停
SIZE_TICK_INTERVAL = 0.05
_last_size_tick = -math.inf
RENAME_TYPE_INTERVAL = 0.06
RENAME_LIMIT_INTERVAL = 0.6
_last_rename_type = _last_rename_limit = _rename_busy_until = -math.inf
_rename_current: str | None = None


def gain(level: float) -> float:
    """音量档（0..STEPS）→ 增益（0..1）：每一档听起来加得一样多。0 档没声音。"""
    level = max(0.0, min(float(STEPS), float(level)))
    return (level / STEPS) ** (1.0 / LOUDNESS) if level > 0.0 else 0.0


def set_volume(level: float, muted: bool = False) -> None:
    """界面音效的音量（0..10 档；静音了就是 0，档位由调的人记着）。"""
    global _gain
    _gain = 0.0 if muted else gain(level)
    set_enabled(_gain > 0.0)


def set_pack_volume(level: float, muted: bool = False) -> None:
    """媒体音效（狗叫、球、落地）的音量。"""
    global _pack_gain
    _pack_gain = 0.0 if muted else gain(level)
    set_pack_enabled(_pack_gain > 0.0)


def volume_gain(pack: bool = False) -> float:
    """现在的增益（单测、试听用）。"""
    return (_pack_gain if pack else _gain) if (_pack_enabled if pack else _enabled) else 0.0


def set_enabled(on: bool) -> None:
    """界面音效响不响（set_volume 调；单测、出图脚本直接关）。开着就预载原音。"""
    global _enabled
    _enabled = bool(on)
    if _enabled:
        for path in FILES.values():
            native.prepare_sound(str(path))
    else:
        stop_rename()


def set_pack_enabled(on: bool) -> None:
    global _pack_enabled
    _pack_enabled = bool(on)
    for path in _extra:
        if _pack_enabled:
            native.prepare_sound(str(path))
        else:
            native.stop_sound(str(path))


def register(paths: Iterable[Path]) -> None:
    """模型包的声音文件：媒体音效没静音就预载（第一次放不卡）。"""
    for path in paths:
        if path not in _extra:
            _extra.add(path)
            if _pack_enabled:
                native.prepare_sound(str(path))


def play_file(path: Path, gain: float = 1.0, offset: float = 0.0, fade_in: float = 0.0) -> bool:
    """放一个文件（模型的声音），按媒体音效的音量；静音、截图时不响。offset：从第几秒开始放；fade_in：从 0 拉上来要几秒（吃喝的声音）。"""
    if _pack_enabled and not ui_frozen():
        if fade_in > 0.0:
            return native.play_sound(str(path), gain * _pack_gain, offset, fade_in=fade_in)
        return native.play_sound(str(path), gain * _pack_gain, offset)
    return False


def play_as_media(kind: str, gain: float = 1.0) -> bool:
    """界面的那几个声音按媒体音效的音量放（高级设置里「媒体音效」那条的静音键：开关的「开」「关」多响，听的是这一条自己的音量）。"""
    return play_file(FILES[kind], gain)


def stop_file(path: Path) -> None:
    native.stop_sound(str(path))


def fade_file(path: Path, seconds: float = native.FADE_SOUND_S) -> None:
    """淡掉再停（不「咔」一下断；默认很快，吃完了嚼的声音 0.5 秒）。"""
    native.fade_sound(str(path), seconds)


def play(kind: str, gain: float = 1.0) -> None:
    """只在真实交互处调用，按界面音效的音量；截图、静音和不支持的音频平台都安静跳过。"""
    if _enabled and not ui_frozen():
        native.play_sound(str(FILES[kind]), gain * _gain)


def size_changed(before: float, after: float, *, fine: bool = False, mark: float | None = None) -> None:
    """跟整数数显过格发声；粗调/精调共享20Hz上限，不叠音、不排队补播。
    mark：滑杆上推荐值那个小刻度；这一下正好吸到它上面（after == mark），放「咔哒」（size-snap：和平时每格的 tick 不一样），不算在限频里。"""
    if not _enabled or ui_frozen() or not (math.isfinite(before) and math.isfinite(after)):
        return
    if mark is not None and abs(after - mark) < 1e-6 and abs(before - mark) >= 1e-6:   # 正好吸上去那一下（大小存回来会差一点点浮点，不算又吸一次）
        global _last_size_tick
        _last_size_tick = time.monotonic()
        play("size-snap")
        return
    # 与 SizeScrubber 的数显舍入一致，只量反馈，不改变实际缩放精度。
    if math.floor(before + 0.5 + 1e-9) == math.floor(after + 0.5 + 1e-9):
        return
    _limited_tick("size-fine" if fine else "tick")


def notches(before: float, after: float, step: float) -> None:
    """没有头的刻度（看细节的转盘尺，widget/turnruler.py）从 before 转到 after：跨过一根刻度（step 的整数倍）tick 一声。
    和大小滑杆共用 20 次 / 秒的上限：转得快只是密一点，不叠音、不排队补播。"""
    if not _enabled or ui_frozen() or step <= 0 or not (math.isfinite(before) and math.isfinite(after)):
        return
    if math.floor(before / step) == math.floor(after / step):
        return
    _limited_tick("tick")


def _limited_tick(kind: str) -> None:
    """刻度这一类的 tick：两声之间至少隔 SIZE_TICK_INTERVAL，太密的直接不响。"""
    global _last_size_tick
    now = time.monotonic()
    if now < _last_size_tick + SIZE_TICK_INTERVAL:
        return
    _last_size_tick = now
    play(kind)


def stop_rename() -> None:
    """停止当前改名反馈；保留限频时间，避免取消/重新进入绕过门限。"""
    global _rename_current
    if _rename_current is not None:
        native.stop_sound(str(FILES[_rename_current]))
        _rename_current = None


def rename_feedback(kind: str) -> None:
    """播放已试听的改名原音；打字不盖住提示音，过密输入直接跳过。"""
    global _last_rename_type, _last_rename_limit, _rename_busy_until, _rename_current
    if not _enabled or ui_frozen():
        return
    now = time.monotonic()
    if kind == "type" and (now < _last_rename_type + RENAME_TYPE_INTERVAL or now < _rename_busy_until):
        return
    if kind == "limit" and now < _last_rename_limit + RENAME_LIMIT_INTERVAL:
        return
    stop_rename()
    name = f"rename-{kind}"
    play(name)
    _rename_current = name
    if kind == "type":
        _last_rename_type = now
    else:
        _rename_busy_until = now + RENAME_DURATIONS[kind]
    if kind == "limit":
        _last_rename_limit = now
