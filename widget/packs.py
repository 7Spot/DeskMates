"""模型包（声音绑在模型上，以后加模型不用改代码）：一个模型一个文件夹 packs/<id>/pack.json，球也是一个包。
怎么加一个模型看 packs/README.md。这里只管读包、把模型里的名字换成代码认的名字，别的都从包里取。

代码里的片段名、骨头名（Run_F_IP、head、foot_b.L……）就是"角色"：另一个模型名字不一样，包里写 clips / bones 对照，
载入时换过来（apply_names）。缺的片段按 CLIP_FALLBACK 往下找，最后落到站着待机；缺的骨头按 BONE_FALLBACK 找。
所以缺东西的模型不会崩，那个动作只是跳过去；缺得太多（没有头、骨盆、脚、站着待机）就不能用（problems）。
声音由 widget/voice.py 放，调参由 widget/tuning.py 存。
物件（狗窝、盆、公园里的东西）也是包：kind 还是 prop，多一段 thing（分在哪组、怎么用、朝哪画、放多大），几款样子写在 styles 里，
一款 = 一个 ThingStyle（包里那段盖上这一款写的）。things() 列出能用的款；买来的模型不入 git，文件不在的款不列。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

import config
from widget.gltf import Model

log = logging.getLogger("packs")

PACKS_DIR = config.ROOT / "packs"
DEFAULT_PET = "border_collie"
BALL = "ball"
DEFAULT_GAITS = {"walk": 0.65, "trot": 1.96, "run": 3.2, "fast": 4.5, "back": 0.65}   # 片段本来的速度（米 / 秒，从脚着地时往后蹬的速度量的）
IDLE = "Idle_1"
REQUIRED_BONES = ("head", "Spine_base")
CLIP_FALLBACK = {
    "Idle_2": "Idle_1", "RunFast_F_IP": "Run_F_IP", "Run_F_IP": "Trot_F_IP", "Trot_F_IP": "Walk_F_IP", "Crouch_F_IP": "Walk_F_IP",
    "Walk_B_IP": "Walk_F_IP", "Walk_F_IP": "Idle_1", "Pick_up_idle": "Idle_1", "JumpAir_Up_F": "JumpAir_Up", "JumpAir_low_F": "JumpAir_low",
    "JumpAir_high": "JumpAir_low", "JumpAir_Up": "JumpAir_Horiz", "JumpAir_low": "JumpAir_Horiz", "JumpLand_F_IP": "JumpLand_Place", "JumpLand": "JumpLand_Place",
    "JumpStart_F_IP": "JumpStart_Place", "JumpStart_Up": "JumpStart_Place", "JumpStart_Down_IP": "JumpStart_Place",
}
BONE_FALLBACK = {"neck": "head", "nose": "head", "eye.L": "head", "eye.R": "head", "Tail_01": "Spine_base"}
THING_GROUPS = ("rest", "food", "toys", "park")   # 「物件」页的四组，按这个先后：窝 / 吃喝 / 玩具 / 公园
THING_ROLES = ("bed", "house", "bowl", "fetch", "push", "hurdle", "decor")   # 怎么用：窝 / 屋 / 盆 / 叼的玩具 / 顶的玩具 / 栏 / 摆设
SPECIES_ICONS = {"dog": "bone"}            # 物种图标（顶部栏名字胶囊里名字左边那个，widget/marks.py）：包里没写 icon 就按物种取；不认识的物种没有，胶囊里换成 app 图标


@dataclass(frozen=True)
class SoundSet:
    """一个声音事件：几段文件（放的时候随机挑，不连着放同一段）、两次之间至少隔多久、音量跟哪个调参项（不写就跟事件名）。"""
    files: tuple[Path, ...]
    min_gap: float = 0.0
    volume: str = ""


@dataclass(frozen=True)
class ClipSound:
    """片段或动作和声音的绑定。at：片段播到第几秒响；every：一直放的时候每隔几秒响一次（第一下在 first 秒）；hold：长声音，片段换了就停。
    fade_in：每一下从 0 拉上来要几秒；fade_out：长声音停的时候淡掉要几秒（0 = 当场停）（吃喝的声音出来得太突然）。"""
    sound: str
    at: tuple[float, ...] = ()
    every: float = 0.0
    first: float = 0.0
    hold: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0


@dataclass(frozen=True)
class ThingStyle:
    """物件的一款样子（狗窝的蓝垫子、矮栏……）。spec 是包里 thing 那段盖上这一款写的以后的结果（不含 styles），用的地方直接取：
    group / order / role / scale / fit_pet / yaw / mirror / shadow，和各种用法自己的键（rest、front_z、platform、serves、hurdle、draw、carry、tint、radius，
    见 packs/README.md）。"""
    key: str                                   # "<包>/<款>"：设置里记的、窗口上认的都是它
    pack: str
    names: Mapping[str, str] = field(default_factory=dict)
    model: Optional[Path] = None               # 这一款的 .glb（tools/export_things.py 导的）；程序自己画的那一款（红球）没有
    model_empty: Optional[Path] = None         # 盆：空了以后的样子
    thumb: Optional[Path] = None               # 「物件」页格子里的缩略图（tools/render_thing_thumbs.py 画的，跟包走）
    spec: Mapping = field(default_factory=dict)
    land_sound: Optional[Path] = None          # 扔下去、拖着放下落地那一声（包里 physics.sound）

    def display_name(self, lang: str = "en") -> str:
        return self.names.get(lang) or self.names.get("en") or self.key

    @property
    def group(self) -> str:
        return str(self.spec.get("group", ""))

    @property
    def role(self) -> str:
        return str(self.spec.get("role", ""))

    @property
    def available(self) -> bool:
        """模型文件在（买来的模型不入 git）；程序自己画的那一款（draw: ball）算在。"""
        return self.spec.get("draw") == "ball" or (self.model is not None and self.model.is_file())


@dataclass(frozen=True)
class Pack:
    id: str
    kind: str                                  # pet / prop
    root: Path
    names: Mapping[str, str] = field(default_factory=dict)
    default_name: str = ""
    model: Optional[Path] = None
    thumb: Optional[Path] = None
    coat_dir: Optional[Path] = None
    coats: tuple[str, ...] = ()
    coat_notes: tuple[Mapping, ...] = ()       # 每套毛色的名字、这套斑纹差在哪：{"name": {语言: 字}, "pattern": {语言: 字}}（widget/look.py 取）
    custom_coat: bool = False
    coat_custom: Mapping = field(default_factory=dict)   # 自定义毛色怎么分：mode（"pattern" 按深浅分两色，边牧；"tint" 整身一个色 + 可选背上一片，萨摩耶）、
                                               # patch_from（背上那一片取自第几套贴图）、default（主色、副色、斑纹）、patterns（每种斑纹的名字、那一句）、common_colors（常用颜色）
    brightness: float = 1.0                    # 贴图整体提亮多少倍：照着打了光来画的贴图（萨摩耶）在三渲二下偏灰，按模型提亮；1 = 原样
    height_m: float = 0.8                      # 站着多高（含耳朵）
    fit_m: float = 0.86                        # 窗口上沿离屏幕最上沿至少这么高才站得下
    mass_kg: float = 18.0
    gaits: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_GAITS))
    clips: Mapping[str, str] = field(default_factory=dict)      # 角色 → 这个模型里的片段名（一样的不用写）
    bones: Mapping[str, str] = field(default_factory=dict)      # 角色 → 这个模型里的骨头名
    sounds: Mapping[str, SoundSet] = field(default_factory=dict)
    clip_sounds: Mapping[str, ClipSound] = field(default_factory=dict)
    action_sounds: Mapping[str, ClipSound] = field(default_factory=dict)
    tuning: Mapping[str, float] = field(default_factory=dict)  # 调参项默认值：覆盖 widget/tuning.py 表里的
    species: str = "dog"                       # 什么动物（pack.json 的 species，不写是狗）
    icon: str = "bone"                         # 物种图标：内置的名字（marks.SPECIES）或包里一张图的路径；空 = 没有（名字胶囊里用 app 图标）
    mouth_offset: Optional[tuple[float, float, float]] = None   # 叼着的东西相对头骨放哪（头骨局部，米）；不写用 props.MOUTH_OFFSET（边牧的）
    head_shot: Mapping = field(default_factory=dict)            # 毛色那一行的头像怎么取景：clip（哪段片段的第一帧）、tall_m（画面多高）、at（头骨在画面里多高）；不写的用 look.py 的
    jumps: Mapping = field(default_factory=dict)                # 跳法名 → {"arc": (起, 止)}：整段片段腾空的那段进度按这个模型改（clips.jumps_for）
    things: tuple[ThingStyle, ...] = ()                         # 这个包是物件的话有几款样子（pack.json 的 thing；没有就是空的）

    def display_name(self, lang: str = "en") -> str:
        return self.names.get(lang) or self.names.get("en") or self.id

    def sound_files(self) -> list[Path]:
        return [f for s in self.sounds.values() for f in s.files]

    @property
    def available(self) -> bool:
        """模型文件在（购买内容不入 git，新 clone 下来可能没有）；不带模型的包（球）算在。"""
        return self.model is None or self.model.is_file()


class ClipTable(dict):
    """片段表：要的片段这个模型没有时，按 CLIP_FALLBACK 往下找，最后落到站着待机。
    Player.name 报的是真正播的那段，所以"等这段播完"的地方（roam 的 clip）一下就过去了：这个动作跳过。"""

    def __missing__(self, name: str):
        seen = {name}
        alt = CLIP_FALLBACK.get(name)
        while alt is not None and alt not in seen:
            if dict.__contains__(self, alt):
                return dict.__getitem__(self, alt)
            seen.add(alt)
            alt = CLIP_FALLBACK.get(alt)
        return dict.__getitem__(self, IDLE)


def _sound_sets(raw: Mapping, root: Path) -> dict[str, SoundSet]:
    out = {}
    for event, spec in raw.items():
        spec = {"files": spec} if isinstance(spec, list) else spec
        files = tuple(p for p in (root / f for f in spec.get("files", ())) if p.is_file())
        if files:                                  # 文件不在就当没有这个声音
            out[event] = SoundSet(files, float(spec.get("min_gap", 0.0)), str(spec.get("volume", "")))
    return out


def _clip_sounds(raw: Mapping) -> dict[str, ClipSound]:
    return {name: ClipSound(str(s["sound"]), tuple(float(t) for t in s.get("at", ())), float(s.get("every", 0.0)),
                            float(s.get("first", 0.0)), bool(s.get("hold", False)), float(s.get("fade_in", 0.0)), float(s.get("fade_out", 0.0)))
            for name, s in raw.items()}


def _vec3(raw) -> Optional[tuple[float, float, float]]:
    return (float(raw[0]), float(raw[1]), float(raw[2])) if raw else None


def _head_shot(raw: Mapping) -> dict:
    out = {}
    if "clip" in raw:
        out["clip"] = str(raw["clip"])
    out.update({k: float(raw[k]) for k in ("tall_m", "at") if k in raw})
    return out


def _thing_styles(pack_id: str, raw, where) -> tuple[ThingStyle, ...]:
    """pack.json 的 thing 那段 → 每款一个 ThingStyle：款里写的盖掉包里写的；缩略图不写就是 thumb-<款>.png。"""
    if not isinstance(raw, Mapping):
        return ()
    base = {k: v for k, v in raw.items() if k != "styles"}
    out = []
    for style in raw.get("styles", ()):
        sid = str(style["id"])
        spec = {**base, **{k: v for k, v in style.items() if k not in ("id", "name", "model", "model_empty", "thumb")}}
        physics = spec.get("physics") if isinstance(spec.get("physics"), Mapping) else {}
        sound = where(physics.get("sound")) if physics.get("sound") else None
        out.append(ThingStyle(key=f"{pack_id}/{sid}", pack=pack_id, names=dict(style.get("name", {})), model=where(style.get("model")),
                              model_empty=where(style.get("model_empty")), thumb=where(style.get("thumb", f"thumb-{sid}.png")), spec=spec,
                              land_sound=sound if sound is not None and sound.is_file() else None))
    return tuple(out)


def read_pack(folder: Path) -> Pack:
    """读一个包。文件路径：先找包自己的文件夹，再找程序根目录（models/ 是购买内容，放在外面）。"""
    data = json.loads((folder / "pack.json").read_text(encoding="utf-8"))

    def where(rel: Optional[str]) -> Optional[Path]:
        if not rel:
            return None
        own = folder / rel
        return own if own.exists() else config.ROOT / rel

    gaits = dict(DEFAULT_GAITS)
    gaits.update({k: float(v) for k, v in data.get("gaits", {}).items()})
    species = str(data.get("species", "dog"))
    icon = str(data.get("icon", SPECIES_ICONS.get(species, "")))
    if icon and ("." in icon or "/" in icon):                  # 包里的一张图（不是内置的名字）
        found = where(icon)
        icon = str(found) if found is not None and found.is_file() else ""
    return Pack(
        id=str(data["id"]), kind=str(data.get("kind", "pet")), root=folder, names=dict(data.get("name", {})),
        default_name=str(data.get("default_name", "")), model=where(data.get("model")), thumb=where(data.get("thumb")),
        coat_dir=where(data.get("coat_dir")), coats=tuple(data.get("coats", ())), coat_notes=tuple(data.get("coat_notes", ())), custom_coat=bool(data.get("custom_coat", False)),
        coat_custom=dict(data.get("coat_custom", {})) if isinstance(data.get("coat_custom"), Mapping) else {},
        brightness=max(0.2, min(3.0, float(data.get("brightness", 1.0)))),
        height_m=float(data.get("height_m", 0.8)), fit_m=float(data.get("fit_m", 0.86)), mass_kg=float(data.get("mass_kg", 18.0)), gaits=gaits,
        clips=dict(data.get("clips", {})), bones=dict(data.get("bones", {})), sounds=_sound_sets(data.get("sounds", {}), folder),
        clip_sounds=_clip_sounds(data.get("clip_sounds", {})), action_sounds=_clip_sounds(data.get("action_sounds", {})),
        tuning={k: float(v) for k, v in data.get("tuning", {}).items()}, species=species, icon=icon,
        mouth_offset=_vec3(data.get("mouth_offset")), head_shot=_head_shot(data.get("head_shot", {})),
        jumps={name: {"arc": (float(j["arc"][0]), float(j["arc"][1]))} for name, j in data.get("jumps", {}).items() if "arc" in j},
        things=_thing_styles(str(data["id"]), data.get("thing"), where))


_found: dict[Path, dict[str, Pack]] = {}     # discover 读过的（按目录）：包是 app 里带的文件，运行中不变


def discover(root: Optional[Path] = None, fresh: bool = False) -> dict[str, Pack]:
    """所有读得出来的包（文件夹名排序）。读不出来的记一笔跳过，不影响别的。同一个目录只读一次（fresh 才重读）：以前每次都把几十个 pack.json 重读一遍，
    约 5 毫秒，换一次同桌要调十来次（量的）。给的是一份新的字典，包本身（Pack）是只读的。"""
    root = PACKS_DIR if root is None else root
    key = Path(root)
    if not fresh and key in _found:
        return dict(_found[key])
    out: dict[str, Pack] = {}
    for f in sorted(root.glob("*/pack.json")) if root.is_dir() else ():
        try:
            pack = read_pack(f.parent)
            out[pack.id] = pack
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("pack %s skipped: %s", f.parent.name, exc)
    _found[key] = out
    return dict(out)


def builtin_pet() -> Pack:
    """packs/ 不在时的兜底：还是现在这只狗，只是没有声音。"""
    return Pack(id=DEFAULT_PET, kind="pet", root=config.ROOT, names={"en": "Border Collie", "zh": "边牧"}, default_name="Milo", model=config.MODEL_PATH,
                coat_dir=config.COAT_DIR, coats=config.COATS, custom_coat=True)


def pets(found: Optional[dict[str, Pack]] = None) -> list[Pack]:
    """能选的模型：kind = pet、模型文件在。第一个是默认的那只。"""
    found = discover() if found is None else found
    out = [p for p in found.values() if p.kind == "pet" and p.available]
    return sorted(out, key=lambda p: (p.id != DEFAULT_PET, p.id))


def choose_pet(wanted: Optional[str] = None, found: Optional[dict[str, Pack]] = None) -> Pack:
    """记着的那只（不在了就默认的那只）。"""
    all_pets = pets(found)
    if not all_pets:
        return builtin_pet()
    return next((p for p in all_pets if p.id == wanted), all_pets[0])


def ball_pack(found: Optional[dict[str, Pack]] = None) -> Pack:
    found = discover() if found is None else found
    return found.get(BALL) or Pack(id=BALL, kind="prop", root=config.ROOT, names={"en": "Ball", "zh": "球"}, mass_kg=0.06)


def things(found: Optional[dict[str, Pack]] = None) -> list[ThingStyle]:
    """能用的物件，一款一个，按「物件」页上的先后：组（THING_GROUPS）、包里写的 order、款在包里的先后。模型文件不在的不列；
    group、role 不认识的（写错了、更新的包）跳过，记一笔。"""
    found = discover() if found is None else found
    rows = []
    for pack in found.values():
        for i, style in enumerate(pack.things):
            if style.group not in THING_GROUPS or style.role not in THING_ROLES:
                log.warning("thing %s skipped: unknown group %r or role %r", style.key, style.group, style.role)
                continue
            if style.available:
                rows.append(((THING_GROUPS.index(style.group), float(style.spec.get("order", 0)), pack.id, i), style))
    return [style for _, style in sorted(rows, key=lambda row: row[0])]


def apply_names(model: Model, pack: Pack) -> Model:
    """把模型里的片段名、骨头名换成代码认的角色名；缺的片段走 ClipTable。"""
    if pack.bones:
        rev = {actual: role for role, actual in pack.bones.items()}
        for n in model.nodes:
            n.name = rev.get(n.name, n.name)
    rev = {actual: role for role, actual in pack.clips.items()}
    clips = {}
    for name, clip in model.clips.items():
        role = rev.get(name, name)
        clip.name = role
        clips[role] = clip
    model.clips = ClipTable(clips)
    model.bone_fallback = dict(BONE_FALLBACK)
    model.gain = pack.brightness
    model.mouth_offset = pack.mouth_offset
    model.jump_arcs = {name: tuple(j["arc"]) for name, j in pack.jumps.items()}
    return model


def problems(model: Model) -> list[str]:
    """这个模型缺了哪些缺不得的东西：头、骨盆、脚、站着待机。"""
    names = {n.name for n in model.nodes}
    out = [f"bone {b}" for b in REQUIRED_BONES if b not in names]
    if not any(n.startswith("foot_") for n in names):
        out.append("bone foot_*")
    if not dict.__contains__(model.clips, IDLE):
        out.append(f"clip {IDLE}")
    return out


def load_model(pack: Pack) -> Model:
    from widget import gltf
    return apply_names(gltf.load(pack.model), pack)
