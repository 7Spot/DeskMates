"""狗的姿势、动作、跳法对照表：模型动画片段怎么拼成姿势（Plan）、动作（Action）、跳（Jump）。

Plan：enter 进入姿势时按顺序各播一遍；exit 离开时先播（趴着的先起身），再进下一个；loop 之后循环播，每次随机挑一个；
base：叠在哪个姿势上的一层（趴睡叠在趴上）。
片段名以 models/collie.glb 里的为准（Blender 导出时剔除了打架、受伤、死亡、排泄、游泳）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Plan:
    loop: tuple[str, ...]
    enter: tuple[str, ...] = ()
    exit: tuple[str, ...] = ()
    base: Optional[str] = None   # 叠在哪个姿势上的一层（趴睡叠在 lying 上）：从那个姿势来只播 enter，回那个姿势只播 exit，去别处 exit 后再播底下姿势的 exit


FADE_STATE = 0.45   # 换姿势的交叉淡入（秒）
FADE_CLIP = 0.30    # 同一姿势内换片段、转身、起身后接下一段

# ---- 姿势 ----
PLAY_IDLE = Plan(loop=("Idle_1", "Idle_2"))                 # 站着待机；抬头看那段不用，头由鼠标跟随管
PLAY_LYING = Plan(enter=("Lie_belly_start",), loop=("Lie_belly_loop_1",), exit=("Lie_belly_end",))   # 趴着待机；哈欠是随机动作
PLAY_SLEEP = Plan(enter=("Lie_belly_sleep_start",), loop=("Lie_belly_sleep",), exit=("Lie_belly_sleep_end",), base="lying")   # 趴睡：三段叠在趴上，量过首末帧和趴着差 0 厘米
PLAY_SIDE = Plan(enter=("Lie_start",), loop=("Lie_loop_1", "Lie_loop_2"), exit=("Lie_end",))                  # 侧躺（只做侧睡的底，不是用户能选的姿势）：从站着躺下、起来是站着
PLAY_SIDE_SLEEP = Plan(enter=("Lie_Sleep_start",), loop=("Lie_Sleep_loop",), exit=("Lie_Sleep_end",), base="side")   # 侧睡：三段叠在侧躺上，首末帧和侧躺差 0 厘米
SLEEP_PLANS = {"belly": PLAY_SLEEP, "side": PLAY_SIDE_SLEEP}   # 点"睡"随机挑一种
PLAY_SITTING = Plan(enter=("Sitting_start",), loop=("Sitting_loop_1", "Sitting_loop_2"), exit=("Sitting_end",))
LOOKS_AROUND = frozenset({"Sitting_loop_2"})   # 头自己左右张望的循环片段（头骨头横着挪约 0.13 米、身子几乎不动）：头在看东西（鼠标跟随、灵动交互里看球）时不播，
                                               # 张望交给看鼠标——两样叠在一起像机器人转头（萨摩耶坐下以后头左右晃）
POSTURE_PLANS = {"lying": PLAY_LYING, "sitting": PLAY_SITTING, "standing": PLAY_IDLE, "sleeping": PLAY_SLEEP, "side": PLAY_SIDE}
ACTION_EVERY = (8.0, 20.0)                                   # 普通随机动作的间隔（秒）；甩毛、哈欠按 RARE


@dataclass(frozen=True)
class Action:
    """互动模式里的一个动作：program 按顺序做完，回到形态的循环。program 的每一项：
    片段名 → 播一遍；("loop", 片段, 秒) → 循环这么久；
    ("turn", 度) → 用转身片段转这么多度（180 自动挑背对镜头的那边）；
    ("jump", 跳法名) → 跳一下（clips.JUMPS）；("pitch", 度) → 头的附加俯仰，不占时间，做完自动复位。
    posture：做这个动作要的姿势（dogctl.do_action 姿势不对先换过去）。via_standing：坐着趴着的随机动作要先站起来做、做完回去。
    rare：按 RARE 里这个片段的间隔来。spin：播的时候身体连续转一圈。group：动作卡片里的分组（states.GROUPS 的 id）。
    gaze：做这个动作时头还跟不跟鼠标（头有自己的戏的不跟 —— 低头嗅、吃喝、刨土、伏地、抬头、左右看、侧躺、叼 / 捡；
    其余照样看着鼠标）。
    label 是英文名，i18n 表里有中文。default：在随机池里。池是固定的、用户不能选；
    不在池里的狗不会自己做，只能从动作卡片点（dogctl.do_action）。listed：在不在动作卡片（表盘）里。"""
    id: str
    label: str
    posture: str
    program: tuple
    group: str = "body"
    via_standing: bool = False
    rare: Optional[str] = None
    default: bool = True
    spin: bool = False
    gaze: bool = True
    mouth: bool = True     # False：做的时候把嘴和舌头压回不张的姿势（模型的伏地、伏低片段自带叫：伏地伸展不该叫）
    prop: Optional[str] = None   # 这个动作带什么道具（widget/props.py）：bone / ball / food / water；动作开始 begin、做完 finish、被切 cut
    listed: bool = True    # False：只在随机池里，动作卡片（表盘）里没有


# 随机池（default）：站着 前伸 后伸 甩毛 挠痒 抬头 左右观望 伏地伸展 刨土；坐着 甩毛（先站起来）；趴着 打哈欠。其余只在动作卡片里。
# 动作卡片（LIST_ACTIONS）按 states.GROUPS 的五组排；狗在窗口里居中不走位，走动类都是原地做几秒。
ACTIONS = (
    # 休息
    Action("look_up", "Howl", "standing", ("Idle_6",), group="rest", gaze=False),                                # Idle_6 是仰头张嘴叫（id 不动）
    Action("look_around", "Look around", "standing", ("Crouch_Idle_start", "Crouch_Idle_loop_2", "Crouch_Idle_end"), group="rest", gaze=False, mouth=False),   # 伏低左右看：loop_2 头才转（loop_1 头不动），嘴压住
    Action("bow", "Bow stretch", "standing", ("Idle_5_start", "Idle_5_loop", "Idle_5_end"), group="rest", gaze=False, mouth=False,
           listed=False),   # Idle_5 自带叫，压住嘴：狗自己随机做的伏地伸展不出声（狗自己待着没声音），表盘里是下面的犬吠
    Action("bow_bark", "Bow and bark", "standing", ("Idle_5_start", "Idle_5_loop", "Idle_5_end"), group="rest", gaze=False,
           default=False),  # 犬吠：同一组片段，嘴照片段张，叫声在包里 clip_sounds 的「bow_bark:Idle_5_*」（只有从表盘点的才响）
    Action("yawn", "Yawn", "lying", ("Lie_belly_loop_2",), group="rest", rare="Lie_belly_loop_2"),
    Action("side_lie", "Side-lie a while", "standing", ("Lie_start", "Lie_loop_1", "Lie_loop_2", "Lie_end"), group="rest", default=False, gaze=False),
    # 侧躺算站姿动作：趴着点它照样是 起身 → 侧躺 → 起身 → 趴回去，但中途被切时狗直接从侧躺切到下一个，不用先趴一次再起来
    # 移动
    Action("walking", "Walking", "standing", (("loop", "Walk_F_IP", 5.0),), group="move", default=False),
    Action("active", "Run and jump", "standing", (("loop", "Run_F_IP", 2.0), ("jump", "bound")), group="move", default=False),
    Action("trotting", "Trotting", "standing", (("loop", "Trot_F_IP", 5.0),), group="move", default=False),
    Action("running", "Running", "standing", (("loop", "RunFast_F_IP", 4.0),), group="move", default=False),
    Action("pacing", "Pacing", "standing", (("loop", "Walk_F_IP", 2.0), ("turn", 180.0), ("loop", "Walk_F_IP", 2.0), ("turn", 180.0)),
           group="move", default=False),                                                                          # 来回走一趟
    Action("backing_up", "Backing up", "standing", (("loop", "Walk_B_IP", 4.0),), group="move", default=False),
    Action("turning", "Turning", "standing", (("turn", 180.0), ("loop", "Idle_1", 0.8), ("turn", 180.0)), group="move", default=False),   # 转过去停一下转回来
    Action("hopping", "Hopping", "standing", (("jump", "hop"),), group="move", default=False),
    Action("jumping", "Jumping", "standing", (("jump", "up"),), group="move", default=False),
    Action("fetching", "Fetching", "standing", (("loop", "Run_F_IP", 2.0), "Pick_up", ("turn", 180.0), ("loop", "Run_F_IP", 2.0), "Put_down", ("turn", 180.0)),
           group="move", default=False, gaze=False, prop="ball"),                                                              # 跑去捡、转身跑回放下、转回来
    # 身体
    Action("stretch_front", "Stretch front", "standing", ("Idle_3",), group="body"),
    Action("stretch_back", "Sniff the ground", "standing", ("Idle_4",), group="body"),     # Idle_4 是低头嗅地，不是伸展
    Action("shake", "Paw up", "standing", ("Idle_7",), group="body", rare="Idle_7"),      # Idle_7 是转头、抬一只前爪看一会，不是甩毛（模型里没有甩毛）
    Action("scratch", "Scratch", "standing", ("Scratching",), group="body"),
    Action("bark", "Bark", "standing", ("Bark",), group="body", default=False),
    Action("spin", "Spin", "standing", ("Turn_L_IP", "Turn_L_IP", "Turn_L_IP"), group="body", default=False, spin=True),
    Action("carrying", "Carrying", "standing", ("Pick_up", ("loop", "Pick_up_idle", 4.0), "Put_down"), group="body", default=False, gaze=False, prop="bone"),
    # 鼻子和嘴
    Action("sniffing", "Nose-down walk", "standing", (("pitch", -30.0), ("loop", "Walk_F_IP", 5.0), ("pitch", 0.0)), group="nose", default=False, gaze=False),   # 模型里没有嗅的片段：就是低头走
    Action("dig", "Dig", "standing", ("Digging_start", "Digging_loop", "Digging_end"), group="nose", gaze=False),
    Action("drinking", "Drinking", "standing", ("EatDrink_start", ("loop", "Drink_loop", 5.0), "EatDrink_end"), group="nose", default=False, gaze=False, prop="water"),
    Action("eating", "Eating", "standing", ("EatDrink_start", ("loop", "Eat_loop", 5.0), "EatDrink_end"), group="nose", default=False, gaze=False, prop="food"),
    # 姿势
    Action("creeping", "Creeping", "standing", (("loop", "Crouch_F_IP", 4.0),), group="pose", default=False),
    Action("picking_up", "Picking up", "standing", ("Pick_up", "Put_down"), group="pose", default=False, gaze=False, prop="bone"),
    # 坐着的随机动作：先站起来甩毛、做完坐回去（和站着的甩毛是同一段动画，动作卡片里不重复列）
    Action("sit_shake", "Paw up", "sitting", ("Idle_7",), group="body", via_standing=True, rare="Idle_7"),
)
ACTIONS_BY_ID = {a.id: a for a in ACTIONS}
LIST_ACTIONS = tuple(a for a in ACTIONS if not a.via_standing and a.listed)   # 动作卡片里的 28 个
DEFAULT_ACTIONS = tuple(a.id for a in ACTIONS if a.default)


@dataclass(frozen=True)
class Jump:
    """一种跳法。whole：整段片段自己完成，抛物线叠在片段进度 arc 那一段上；
    否则 start 起跳 → air 空中姿势 + 程序算的抛物线（height 米、air_time 秒）→ land 落地。"""
    name: str
    whole: Optional[str] = None
    start: Optional[str] = None
    air: Optional[str] = None
    land: Optional[str] = None
    height: float = 0.0
    air_time: float = 0.0
    arc: tuple[float, float] = (0.0, 1.0)
    pitch: float = 0.0            # 随抛物线的俯仰（度）：起跳抬头这么多，顶点水平，落地低头这么多；绕身体中心转


# 窗口会按需要临时长高（window.py），所以高度不用迁就窗口；顶到屏幕就裁掉，算跳出屏幕。
# 整段片段自己只离地两三厘米，抛物线叠在它腾空的那段进度上（量过脚高曲线）。
# JumpAir_low 是鼻子朝下屁股朝上的俯冲姿势，不用；拼的平跳都用水平姿势 + 随抛物线的俯仰。
JUMPS = (
    Jump("hop", whole="Jump_Place_IP", height=0.20, arc=(0.22, 0.50)),
    Jump("bound", whole="Jump_Run_IP", height=0.25, arc=(0.42, 0.82)),
    Jump("medium", start="JumpStart_Place", air="JumpAir_Horiz", land="JumpLand_Place", height=0.35, air_time=0.50, pitch=20.0),
    Jump("long", start="JumpStart_Place", air="JumpAir_Horiz", land="JumpLand_Place", height=0.45, air_time=0.58, pitch=20.0),
    Jump("up", start="JumpStart_Up", air="JumpAir_Up", land="JumpUp_End_IP", height=0.50, air_time=0.60),
)   # 不加跳远（JumpAir_high_F）和高跳（JumpAir_high，0.65 米）


def jumps_for(model) -> tuple[Jump, ...]:
    """这个模型的五种跳法：模型包没改过（pack.json 的 jumps → model.jump_arcs）就是 JUMPS 本身；改过的那几种换上它自己的腾空区间
    （同名片段在另一个模型里长短不一样，脚离地、落回的进度就不一样）。"""
    arcs = getattr(model, "jump_arcs", None)
    if not arcs:
        return JUMPS
    return tuple(replace(j, arc=(float(arcs[j.name][0]), float(arcs[j.name][1]))) if j.name in arcs else j for j in JUMPS)


# 稀有片段：不随机轮，只按间隔来。值是"下次允许播的间隔"范围（秒），平均是中点。打哈欠平均 60 秒最短 40，甩毛平均 50 秒最短 30。
RARE = {"Lie_belly_loop_2": (40.0, 80.0), "Idle_7": (30.0, 70.0)}

TURN_180 = {"L": "Turn_L180_IP", "R": "Turn_R180_IP"}
TURN_90 = {"L": "Turn_L_IP", "R": "Turn_R_IP"}
QUARTER_POSES = (210.0, 330.0)   # 静止时的两个四分之三朝向：头朝左略向镜头 / 头朝右略向镜头
