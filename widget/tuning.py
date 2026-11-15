"""调参（开发者设置页：连点五下版本号打开：所有的狗、小球、所有物件都能调）：每个包一份，数值记在设置里，改了马上生效。
表（PET_PARAMS 狗、BALL_PARAMS 小球、THING_PARAMS 物件）在这里；默认值是包里写的：狗和小球是包里的 tuning，物件是包里的 thing.physics。
谁用谁每次读（tune["key"]），不抄进常量。每个包只建一份 Tuning（widget/kits.py 的 Kits.tuning），页上改的就是在用的那份。纯数据，不碰 Qt。
最上面两项是性子（活跃度、聪明程度）：别的数是「满分的狗」的数，性子在它们上面打折（widget/temper.py），两根滑杆一拉整只狗都变。
跟鼠标转身的四个（turn_*）默认值写在 widget/play.py（没接调参时控制器直接用那几个常量），这里读过来，不再抄一遍。"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Iterable, Optional

from widget.packs import BALL, Pack
from widget.play import BODY_FLIP_LENGTHS, BODY_TURN_COOLDOWN, BODY_TURN_DEBOUNCE, TURN_SPEED

LOOK_IDLE_S = 10.0  # 灵动交互里鼠标停着多久狗就不看你了（秒；边牧的数，萨摩耶走神快，包里写 7）：playground.watching_you
HAND_KG = 15.0     # 手甩出去的力气，按手臂这么重算：东西越沉飞得越慢（速度 × 手 / (手 + 东西)，18 公斤的狗 × 0.45，飞的距离约为球的五分之一）


@dataclass(frozen=True)
class Param:
    """一个能调的数：键、标题（英文原文，i18n 查中文）、默认、范围、每格多少、小数位。"""
    key: str
    label: str
    default: float
    lo: float
    hi: float
    step: float = 0.01
    digits: int = 2


PET_PARAMS = (
    Param("energy", "Energy", 1.0, 0.0, 1.0, 0.05),          # 活跃度（性子，widget/temper.py）：1 = 边牧（一直以来的样子）；低了不冲刺、反应慢半拍、没人理就歇着
    Param("smarts", "Cleverness", 1.0, 0.0, 1.0, 0.05),      # 聪明程度：1 = 边牧；低了不预判落点、会被弹回来的球晃到、圈满得慢、放得没那么准
    Param("mass_kg", "Mass (kg)", 18.0, 1.0, 80.0, 0.5, 1),
    Param("throw_gain", "Throw distance", 1.0, 0.0, 3.0, 0.05),
    Param("hit_bounce", "Bounce off things", 0.15, 0.0, 0.8),
    Param("max_up", "Highest jump (body heights)", 3.0, 1.0, 6.0, 0.1, 1),
    Param("push_vx", "Leap speed (m/s)", 1.9, 1.2, 4.5, 0.05),
    Param("duang_depth", "Squash depth", 0.15, 0.0, 0.4),
    Param("duang_seconds", "Squash time (s)", 0.45, 0.15, 1.2),
    Param("bow_depth", "Bow depth", 1.0, 0.3, 1.0),
    Param("float_bob", "Float amount (m)", 0.02, 0.0, 0.08, 0.002, 3),
    Param("float_sway", "Swing amount", 1.0, 0.0, 2.5, 0.05),
    Param("land_light_m", "Light landing below (m)", 0.3, 0.0, 1.0),
    Param("land_mid_m", "Full landing above (m)", 0.8, 0.3, 2.5),
    Param("land_slide", "Slide after landing", 1.0, 0.0, 3.0, 0.05),
    Param("ring_size", "Fetch ring size (body heights)", 0.9, 0.8, 2.0, 0.05),                       # 捡球的圈（widget/ring.py）：半径几个身高
    Param("ring_hold_s", "Hold in the ring before the dog is ready (s)", 1.0, 0.3, 4.0, 0.1, 1),     # 球在圈里停多久圈满
    Param("ready_bark", "Chance of a bark when the dog is ready", 1.0, 0.0, 1.0, 0.05),              # 圈满那一下叫不叫（「可能叫」）
    Param("see_bounces", "Bounces the dog can read ahead", 0.0, 0.0, 5.0, 1.0, 0),
    Param("turn_reach", "Turn when the pointer passes the dog by (body lengths)", BODY_FLIP_LENGTHS, 0.1, 2.0, 0.05),
    Param("turn_delay", "Wait before turning (s)", BODY_TURN_DEBOUNCE, 0.0, 0.6),
    Param("turn_speed", "Turn speed", TURN_SPEED, 1.0, 2.5, 0.05),
    Param("turn_rest", "Rest after turning (s)", BODY_TURN_COOLDOWN, 0.0, 1.5, 0.05),
    Param("look_idle_s", "Stop watching a still pointer after (s)", LOOK_IDLE_S, 2.0, 60.0, 0.5, 1),
    Param("idle_skip", "Low Power Mode: while resting, draw one frame in every", 3.0, 1.0, 3.0, 1.0, 0),
    Param("vol_bark", "Bark volume", 0.7, 0.0, 1.0),
    Param("vol_lick", "Lick volume", 0.35, 0.0, 1.0),        # 吃喝的声音太突然（咬的那几下 bite 跟着 vol_eat）
    Param("vol_eat", "Eating volume", 0.35, 0.0, 1.0),
    Param("vol_drop", "Landing volume", 0.35, 0.0, 1.0),
)
BALL_PARAMS = (
    Param("mass_kg", "Mass (kg)", 0.06, 0.01, 5.0, 0.01),
    Param("throw_gain", "Throw distance", 1.0, 0.0, 3.0, 0.05),
    Param("e_floor", "Floor bounce", 0.52, 0.0, 0.95),
    Param("e_wall", "Wall bounce", 0.62, 0.0, 0.95),
    Param("roll", "Roll distance", 1.0, 0.1, 4.0, 0.05),
    Param("vol_bounce", "Bounce volume", 1.0, 0.0, 1.0),
    Param("vol_grab", "Pick-up volume", 0.8, 0.0, 1.0),
    Param("vol_charge", "Charge-up volume", 1.0, 0.0, 1.0),      # 捡球的圈快满时的那一声（packs/ball 的 charge）
)

THING_PARAMS = (                                             # 物件（狗窝、狗屋、盆）：包里 thing.physics 那一组，widget/things.py 的 ThingPhysics 读（这里的默认值和它的一样，tests/test_tuning_all.py 守着）
    Param("mass_kg", "Mass (kg)", 1.0, 0.1, 40.0, 0.1, 1),   # 越重出手越慢、飞得越近
    Param("bounce", "Landing bounce", 0.2, 0.0, 0.95),       # 落地往回弹几成（也决定撞墙弹回多少）
    Param("friction", "Slide friction (m/s²)", 6.0, 0.0, 60.0, 0.5, 1),   # 落到线上以后滑的时候每秒慢多少
    Param("squash", "Squash on landing", 0.1, 0.0, 0.5),     # 落地最重时压扁几成
    Param("recover", "Spring-back speed", 1.0, 0.1, 3.0, 0.05),   # 压扁以后弹回来多快（小于 0.8 的不弹过头、慢慢鼓回来）
    Param("dust", "Dust", 0.0, 0.0, 2.0, 0.05),              # 落地扬灰多少（0 = 不扬）
    Param("shake", "Shake nearby things", 0.0, 0.0, 2.0, 0.05),   # 落地震旁边的东西多重（0 = 不震）
    Param("volume", "Landing volume", 1.0, 0.0, 1.0),        # 落地那一声多响
)


def kind_of(pack: Pack) -> str:
    """按哪张表调：pet 狗、ball 小球、thing 物件（写了 thing 那一段的别的包）。"""
    if pack.kind == "pet":
        return "pet"
    return "thing" if pack.id != BALL and pack.things else "ball"


def _number(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def params_for(pack: Pack) -> tuple[Param, ...]:
    """这个包能调哪些：表 + 包里的默认值。狗、小球：包里的 tuning，质量的默认值就是包写的质量；物件：包里的 thing.physics（款都一样，取第一款的）。"""
    kind = kind_of(pack)
    if kind == "thing":
        raw = pack.things[0].spec.get("physics")
        raw = raw if isinstance(raw, Mapping) else {}
        return tuple(replace(p, default=_number(raw.get(p.key), p.default)) for p in THING_PARAMS)
    base = PET_PARAMS if kind == "pet" else BALL_PARAMS
    out = []
    for p in base:
        default = pack.mass_kg if p.key == "mass_kg" else pack.tuning.get(p.key, p.default)
        out.append(replace(p, default=default))
    return tuple(out)


class Tuning:
    """一个包的调参值。store 是 QSettings（或测试里的假设置），键 tuning/<包>/<项>；没动过的不存，表里默认值变了跟着变。"""

    def __init__(self, pack: Pack, store=None, params: Optional[Iterable[Param]] = None):
        self.pack = pack
        self.store = store
        self.kind = kind_of(pack)
        self.params = tuple(params) if params is not None else params_for(pack)
        self._by_key = {p.key: p for p in self.params}
        self.values = {p.key: p.default for p in self.params}
        for p in self.params:
            v = store.value(self._key(p.key)) if store is not None else None
            if v is not None:
                try:
                    self.values[p.key] = self._clamp(p, float(v))
                except (TypeError, ValueError):
                    pass

    def _key(self, key: str) -> str:
        return f"tuning/{self.pack.id}/{key}"

    @staticmethod
    def _clamp(p: Param, v: float) -> float:
        return max(p.lo, min(p.hi, v))

    def __getitem__(self, key: str) -> float:
        return self.values[key]

    def get(self, key: str, default: float = 1.0) -> float:
        return self.values.get(key, default)

    def set(self, key: str, value: float) -> float:
        p = self._by_key[key]
        v = self._clamp(p, float(value))
        self.values[key] = v
        if self.store is not None:
            self.store.setValue(self._key(key), v)
        return v

    def is_default(self, key: str) -> bool:
        return abs(self.values[key] - self._by_key[key].default) < 1e-9

    def reset(self) -> None:
        """全部回到默认值，设置里不留。"""
        for p in self.params:
            self.values[p.key] = p.default
            if self.store is not None and hasattr(self.store, "remove"):
                self.store.remove(self._key(p.key))

    def copy_text(self) -> str:
        """「复制数值」：一行一个，贴到 pack.json 的 tuning 里就能当默认值；质量写在包的 mass_kg。物件包在 "physics" 里：贴进包里的 thing.physics
        （没列的项照包里原来的）。只列动过的，一个都没动就全列。"""
        changed = [p for p in self.params if not self.is_default(p.key)]
        rows = changed or self.params
        pad = "    " if self.kind == "thing" else "  "
        body = ",\n".join(f'{pad}"{p.key}": {round(self.values[p.key], max(p.digits, 3))}' for p in rows)
        if self.kind == "thing":
            return f'"{self.pack.id}": {{\n  "physics": {{\n{body}\n  }}\n}}'
        return f'"{self.pack.id}": {{\n{body}\n}}'

    @property
    def throw_factor(self) -> float:
        """手甩出去的速度乘多少才是这东西飞出去的速度。"""
        return HAND_KG / (HAND_KG + self.get("mass_kg", 0.0)) * self.get("throw_gain", 1.0)
