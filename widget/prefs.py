"""设置项的唯一一张表：键和默认值（类型就是默认值的类型）。窗口（widget/window.py）和毛色（widget/look.py）都通过 Prefs 读写 QSettings，
键名、默认值、类型只写这一处（各处自己写 setValue 的话，布尔读回来要猜 "true" / "1"）。
不在表里的键不给读写（写错键名当场报错）。单测里 QSettings 换成假的，Prefs 只要求它有 value / setValue。
每只同桌各记一份的（PER_PET：名字、毛色；同一个模型养两只也分开）：第一只（升级前就有的那只）还放在原来的键上，
升级不丢设置（它换了别的模型就放在 pack/<模型>/ 下面）；后来添加的放在 pet/<号>/ 下面。名单在 Roster。调参按模型记（widget/tuning.py）。
大小是全局的一个（以后两只一起玩，不能不一样大）： 以前每只各记一份，share_size 把现在这只的搬到全局的键上。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import config

PER_PET = frozenset({"dog_name", "coat", "coat_custom"})
SIZE_KEYS = ("scale", "scale_chosen", "size_suggested")   # 大小那几项：全局一份
DEFAULT_PACK = "border_collie"
FIRST_PET = ""                                    # 第一只的号：升级前就有的那只
DEFAULTS: dict[str, Any] = {
    "pack": "",                                   # 现在这只用的是哪个模型（启动时按它载入）；空 = 默认那只
    "pets": "",                                   # 「我的同桌」的名单（JSON，Roster 读写）；空 = 只有第一只
    "pet": FIRST_PET,                             # 现在是名单里的哪一只
    "language": "",                               # 界面语言；空 = 第一次启动跟系统
    "dog_name": "Milo",
    "show_metadata": config.SHOW_METADATA_DEFAULT,
    "follow_cursor": config.FOLLOW_CURSOR_DEFAULT,
    "dynamic": True,                              # 灵动交互：新装默认开
    "hop_windows": True,                          # 窗口交互（PLAY_OPTIONS）：关了狗和球都不把别的 App 的窗口当台子，只有每块屏的地面
    "things": "",                                 # 灵动交互里摆着的物件和各自的位置（JSON，widget/things.py 的 Shelf 读写）；空 = 一件没摆过
    "toy": "",                                    # 玩具那一个位置现在是哪款（<包>/<款>）；空 = 红球
    "ball_out": True,                             # 小球拿出来没有（球也是一件道具，默认拿出来；收起来狗就没球玩）
    "tools": "",                                  # 道具栏（「···」旁边那一条）放了哪几样（JSON 的款钥匙列表，按「物件」页的先后显示）；空 = 只有小球
    "power_saving": False,                        # 省电模式（默认满帧，看得出来的省法都放这个开关后面）
    "appearance": "system",                       # light / dark / system
    "interface_volume": 10,                       # 界面音效（按钮、开关、滑杆的 tick）：记着的那一档 1..10
    "interface_muted": False,                     # 静音了（档位还记着，取消静音回去）
    "media_volume": 10,                           # 媒体音效（狗叫、球碰撞、落地：和界面音效分开）
    "media_muted": False,
    "rest_posture": "lying",                      # standing / sitting / lying / sleeping
    "coat": 1,                                    # 1..4 原装，0 自定义
    "coat_custom": "",                            # 自定义毛色的参数（JSON）
    "scale": 1.0,
    "scale_chosen": False,                        # 你自己调过大小（调过就不再替你改）
    "size_suggested": False,                      # 第一次开灵动交互时的推荐大小用过了（只用一次）
    "pos_x": None,                                # 旧版本记的位置（None = 没记过）：左边和底边的绝对坐标，只在第一次启动时读一次、换成下面的比例
    "pos_bottom": None,
    "pos_screen": "",                             # 位置：在哪块屏（QScreen.name）
    "pos_fx": -1.0,                               # 窗口中心 x 占那块屏宽的几成；负数 = 没记过
    "pos_fb": -1.0,                               # 底边占屏高的几成（窗口高度会变，狗脚不动）
}
TRUE_WORDS = (True, 1, "1", "true", "True")


@dataclass(frozen=True)
class PlayOption:
    """灵动交互的一条子选项（灵动交互不只有开和关）：一个全局的开关，不跟同桌走。设置卡片主页面灵动交互那一行的调节图标点开，
    一条一行（settings._play_options）；窗口照这张表读、存、切（window.set_play_option），读它的地方读窗口上的 attr。
    加一条：这里加一行、DEFAULTS 里加默认值、i18n 里加中文，再在读它的地方读 window.<键>_on，别处不用动。
    现在一条：窗口交互（拎起来扔出去、随鼠标转身不做成选项，永远开着；把球放进狗那一圈才追，本来就有一层管着；
    旧设置里存过的那几个键没人读）。"""
    key: str                                      # DEFAULTS 里的键（默认值写在那）
    label: str                                    # 卡片上那一行的字（英文原文，i18n.tr 翻）
    changed: str = ""                             # 切的那一下叫窗口的哪个方法；读它的地方每次现读的不用填
    tip: str = ""                                 # 鼠标停在这一行的字上浮出的说明（英文原文；空 = 没有）

    @property
    def attr(self) -> str:
        """窗口上记着它的那个属性（hop_windows → hop_windows_on）。"""
        return self.key + "_on"


PLAY_OPTIONS = (                                  # 卡片上从上到下；后面注明谁读它
    PlayOption("hop_windows", "Window interaction", "_hop_windows_changed",       # 窗口交互（狗能站、球能停；键不变）：playground._refresh_frames、_frame
               "When it can, your deskmate hops onto windows"),
)
VOLUMES = {"interface": ("interface_volume", "interface_muted", "interface_sounds"),   # 音量：(档位, 静音,  以前那个开关的键)
           "media": ("media_volume", "media_muted", "pack_sounds")}


def pet_key(pet_id: str, pack_id: str, key: str) -> str:
    """每只各记一份的那几项实际存在哪个键上。"""
    if pet_id != FIRST_PET:
        return f"pet/{pet_id}/{key}"
    return f"pack/{pack_id}/{key}" if pack_id != DEFAULT_PACK else key


def share_size(store, pets, current_id: str) -> None:
    """大小以前每只各记一份（pet/<号>/scale、pack/<模型>/scale），现在全局一份：现在这只的搬到全局的键上，别的丢掉。只在启动时做；
    搬完旧键就没了，所以只会搬一次。存不了删不了的假设置（单测）什么都不做。"""
    drop = getattr(store, "remove", None)
    if drop is None:
        return
    for pet in pets:
        for key in SIZE_KEYS:
            old = pet_key(pet.id, pet.pack, key)
            if old == key:
                continue                                  # 第一只、默认模型：本来就在全局的键上
            value = store.value(old, None)
            if value is None:
                continue
            if pet.id == current_id:
                store.setValue(key, value)
            drop(old)


class Prefs:
    def __init__(self, store, pack_id: str = DEFAULT_PACK, default_name: str = "", pet_id: str = FIRST_PET) -> None:
        self.store = store                        # QSettings（或测试里的假设置）
        self.pack_id = pack_id
        self.default_name = default_name          # 这个模型没起过名字时叫什么
        self.pet_id = pet_id                      # 现在是哪一只（window.switch_pet 换）

    def _store_key(self, key: str) -> str:
        return pet_key(self.pet_id, self.pack_id, key) if key in PER_PET else key

    def of(self, pet_id: str, pack_id: str, default_name: str = "") -> "Prefs":
        """另一只同桌的那一份（滑动条上画它的名字、毛色用）。"""
        return Prefs(self.store, pack_id, default_name, pet_id)

    def get(self, key: str) -> Any:
        """按默认值的类型读回来：布尔认 "true" / "1"，整数、小数转型，None 默认的（位置）读到就是 int。"""
        default = DEFAULTS[key]
        if key == "dog_name" and self.default_name:
            default = self.default_name
        v = self.store.value(self._store_key(key), default)
        if v is None:
            return default
        if isinstance(default, bool):
            return v in TRUE_WORDS
        if isinstance(default, int):
            return int(v)
        if isinstance(default, float):
            return float(v)
        if default is None:
            return int(v)
        return str(v)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        self.store.setValue(self._store_key(key), value)

    def volume(self, kind: str) -> tuple[int, bool]:
        """「interface」/「media」的音量：(记着的那一档 1..10, 静音没有)。以前是开关（interface_sounds / pack_sounds）：
        还没记过音量的照它换过来——开着 = 满格（和以前一样响），关着 = 静音、记着满格。"""
        level_key, muted_key, old_key = VOLUMES[kind]
        if self.store.value(muted_key, None) is None:
            old = self.store.value(old_key, None)
            if old is not None:
                self.set(muted_key, old not in TRUE_WORDS)
                self.set(level_key, DEFAULTS[level_key])
        return max(1, min(10, self.get(level_key))), self.get(muted_key)

    def text(self, key: str) -> Optional[str]:
        """字符串项：空的当没有。"""
        v = self.get(key)
        return v or None


@dataclass(frozen=True)
class Pet:
    id: str                                       # 号：第一只是 ""，后来添加的是 p1、p2……（不重复用）
    pack: str                                     # 用哪个模型


class Roster:
    """「我的同桌」的名单：每只一个号 + 用哪个模型，按滑动条上的顺序；名字、毛色在各自那一份设置里（Prefs 按号存）。
    没记过名单就是只有第一只（升级上来的、新装的都是）。"pack" 那一项一直等于现在这只的模型：启动时按它载入。"""

    def __init__(self, store, pack_id: str = DEFAULT_PACK) -> None:
        self.store = store
        self._pets = self._read(pack_id)
        current = str(store.value("pet", FIRST_PET) or FIRST_PET)
        self.current_id = current if any(p.id == current for p in self._pets) else self._pets[0].id

    def _read(self, pack_id: str) -> list[Pet]:
        try:
            rows = json.loads(self.store.value("pets", "") or "[]")
            pets = [Pet(str(r["id"]), str(r["pack"])) for r in rows]
        except (ValueError, KeyError, TypeError):
            pets = []
        seen: set[str] = set()
        pets = [p for p in pets if not (p.id in seen or seen.add(p.id))]
        return pets or [Pet(FIRST_PET, pack_id)]

    def _save(self) -> None:
        self.store.setValue("pets", json.dumps([{"id": p.id, "pack": p.pack} for p in self._pets]))

    def pets(self) -> list[Pet]:
        return list(self._pets)

    def get(self, pet_id: str) -> Optional[Pet]:
        return next((p for p in self._pets if p.id == pet_id), None)

    def current(self) -> Pet:
        return self.get(self.current_id) or self._pets[0]

    def index(self, pet_id: str) -> int:
        return next((i for i, p in enumerate(self._pets) if p.id == pet_id), 0)

    def select(self, pet_id: str) -> None:
        """现在是这一只；"pack" 跟着它（下次启动载入它的模型）。"""
        pet = self.get(pet_id)
        if pet is None:
            return
        self.current_id = pet.id
        self.store.setValue("pet", pet.id)
        self.store.setValue("pack", pet.pack)

    def add(self, pack_id: str) -> Pet:
        """添一只，排在最后；号从没用过的里取（删掉的号不重用，旧设置串不过来）。"""
        used = [int(p.id[1:]) for p in self._pets if p.id[:1] == "p" and p.id[1:].isdigit()]
        last = int(self.store.value("pets_last", 0) or 0)
        n = max(used + [last]) + 1
        self.store.setValue("pets_last", n)
        pet = Pet(f"p{n}", pack_id)
        self._pets.append(pet)
        self._save()
        return pet

    def remove(self, pet_id: str) -> bool:
        """删一只，连它那一份名字、毛色一起删；最后一只删不了。删的是现在这只就换到旁边那只（先右后左）。"""
        pet = self.get(pet_id)
        if pet is None or len(self._pets) < 2:
            return False
        i = self._pets.index(pet)
        self._pets.remove(pet)
        self._save()
        drop = getattr(self.store, "remove", None)
        if drop is not None:
            for key in PER_PET:
                drop(pet_key(pet.id, pet.pack, key))
        if self.current_id == pet.id:
            self.select(self._pets[min(i, len(self._pets) - 1)].id)
        return True
