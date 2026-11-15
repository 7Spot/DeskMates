"""模型的声音（声音绑在模型上）：SoundBank 按事件名放包里的声音，ClipSounds 看狗正在播的片段，到点放（绑定写在 pack.json）。
包里没有这个声音就不响，不报错。总开关、截图时静音都在 widget/sounds.py。"""
from __future__ import annotations

import random
import time
from typing import Optional

from widget import sounds
from widget.packs import ClipSound, Pack
from widget.tuning import Tuning


class SoundBank:
    def __init__(self, pack: Pack, tuning: Optional[Tuning] = None, rng: Optional[random.Random] = None):
        self.pack = pack
        self.tuning = tuning
        self.rng = rng or random.Random()
        self._last_file: dict[str, object] = {}
        self._last_at: dict[str, float] = {}
        self._current: dict[str, object] = {}
        sounds.register(pack.sound_files())

    def has(self, event: str) -> bool:
        return event in self.pack.sounds

    def volume(self, event: str) -> float:
        spec = self.pack.sounds.get(event)
        name = (spec.volume if spec is not None and spec.volume else event)
        return self.tuning.get(f"vol_{name}", 1.0) if self.tuning is not None else 1.0

    def play(self, event: str, gain: float = 1.0, fade_in: float = 0.0) -> bool:
        """放这个事件的一段（几段里随机挑，不连着放同一段）。太密的跳过，不排队。fade_in：从 0 拉上来要几秒。"""
        spec = self.pack.sounds.get(event)
        if spec is None:
            return False
        now = time.monotonic()
        if spec.min_gap and now - self._last_at.get(event, -1e9) < spec.min_gap:
            return False
        choices = [f for f in spec.files if f != self._last_file.get(event)] or list(spec.files)
        f = self.rng.choice(choices)
        self._last_file[event] = f
        self._last_at[event] = now
        self._current[event] = f
        if fade_in > 0.0:
            return sounds.play_file(f, gain * self.volume(event), fade_in=fade_in)
        return sounds.play_file(f, gain * self.volume(event))

    def stop(self, event: str, fade: float = 0.0) -> None:
        """停这个事件正在响的那一段；fade：淡掉要几秒（0 = 当场停）。"""
        f = self._current.pop(event, None)
        if f is not None:
            if fade > 0.0:
                sounds.fade_file(f, fade)
            else:
                sounds.stop_file(f)

    def start(self, event: str, offset: float = 0.0, gain: float = 1.0) -> bool:
        """从第 offset 秒开始放这个事件的第一段（跟着进度走的长声音：充能，回到圈里接着响）。不管 min_gap。"""
        spec = self.pack.sounds.get(event)
        if spec is None or not spec.files:
            return False
        f = spec.files[0]
        self._current[event] = f
        return sounds.play_file(f, gain * self.volume(event), offset)

    def fade(self, event: str) -> None:
        """正在响的这个事件很快淡掉再停。"""
        f = self._current.pop(event, None)
        if f is not None:
            sounds.fade_file(f)


class ClipSounds:
    """每帧看一眼正在播什么（update）：片段或动作在 pack.json 里绑了声音就到点放。换片段时长声音（hold）停。"""

    def __init__(self, bank: SoundBank):
        self.bank = bank
        self.pack = bank.pack
        self._clip: Optional[str] = None
        self._action: Optional[str] = None
        self._t = 0.0
        self._action_t = 0.0
        self._next_clip = 0.0
        self._next_action = 0.0
        self._held: Optional[str] = None
        self._held_fade = 0.0

    def _stop_held(self) -> None:
        if self._held is not None:
            self.bank.stop(self._held, self._held_fade)
            self._held = None

    def update(self, clip: Optional[str], t: float, action: Optional[str], dt: float) -> None:
        """clip：正在播的片段；t：片段播到第几秒；action：正在做的动作 id（没有 None）。
        包里写「动作:片段」的只在做这个动作时算（犬吠 bow_bark 借伏地伸展的片段叫，别的时候播这几段不响），先找它，再找只写片段的。"""
        spec = None
        if clip is not None:
            spec = (self.pack.clip_sounds.get(f"{action}:{clip}") if action is not None else None) or self.pack.clip_sounds.get(clip)
        if clip != self._clip:
            self._stop_held()
            self._clip = clip
            self._t = t
            if spec is not None:
                self._next_clip = spec.first
                if spec.hold:
                    self._held, self._held_fade = spec.sound, spec.fade_out
                    self.bank.play(spec.sound, fade_in=spec.fade_in)
        elif spec is not None:
            if t < self._t:                        # 循环回到开头：先把这一圈末尾的算完，再从头算
                self._fire_at(spec, self._t, float("inf"))
                self._t = -1e-6
            self._fire_at(spec, self._t, t)
            self._t = t
        if spec is not None and spec.every:
            self._next_clip -= dt
            if self._next_clip <= 0.0:
                self.bank.play(spec.sound, fade_in=spec.fade_in)
                self._next_clip = spec.every
        self._update_action(action, dt)

    def _fire_at(self, spec: ClipSound, a: float, b: float) -> None:
        for at in spec.at:
            if a < at <= b:
                self.bank.play(spec.sound, fade_in=spec.fade_in)

    def _update_action(self, action: Optional[str], dt: float) -> None:
        spec = self.pack.action_sounds.get(action) if action is not None else None
        if action != self._action:
            self._action = action
            self._action_t = 0.0
            if spec is not None:
                self._next_action = spec.first
        if spec is None:
            return
        self._action_t += dt
        if spec.every:
            self._next_action -= dt
            if self._next_action <= 0.0:
                self.bank.play(spec.sound)
                self._next_action = spec.every

    def reset(self) -> None:
        self._stop_held()
        self._clip = self._action = None
