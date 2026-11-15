"""灵动交互里狗离开原地：在空间（widget/world.py）里跑、跳上跳下、掉下来、骑在窗口上、去捡球再叼给你。

位置：(wx, wy) 是狗的根在屏幕上的全局坐标（wy = 脚踩的那条线），窗口每帧按它摆（window.place_scene）；
控制器里的 x / z 一直是 0（狗永远在窗口正中，动画都是原地的 _IP 片段）。脚下是哪条线记在 support（地面或某个窗口的上沿）。

一段段地走（leg）：
- run：边转边跑：身子 0.2～0.36 秒平滑转到朝那边
  （侧身：朝左 180°、朝右 0°），同时起步；按距离挑走 / 小跑 / 跑 / 快跑，速度和片段的步子对上（片段播放速度 = 实际速度 /
  片段本来的速度，脚不打滑；本来的速度是从模型脚着地时往后蹬的速度量的），起步加速、到点前减速；
- jump：窗口是方盒子（路线、空地怎么量在 widget/world.py 的 Leaper）。每一帧都按这一帧真实的姿势摆根（window 画完姿势后调 after_pose），
  换片段时身子不会一下子跳一截：脚踩着的时候按后脚反算根（后脚一定在平面上），空中骨盆走抛物线，落地骨盆跟着落地片段走、融完根正好在台面上。
  - up：从窗口一头的外面起跳（JumpStart_Up）→ JumpAir_Up → 到顶前换 JumpAir_Up_F → 越过窗口边，后脚落在台面上（JumpLand_Place）；
  - push（空地够）：走到窗口一头，后脚踩住往前蹬（JumpStart_F_IP）→ JumpAir_Horiz → 过了最高点 JumpAir_low_F → 前爪先着地（JumpLand）；
    落差小（一米以内）落地换 JumpLand_F_IP；
  - edge（空地不够：不要跳高）：走到窗口边，前爪先探出去，后脚并到边上踩住，身子往下探（JumpStart_Down_IP）→ 放手直接落（JumpAir_high）→ JumpLand_Place；
    落差小的探到一半前爪就够着了，不用探到底；
  - across（屏和屏交界、差不多一样高）：JumpStart_F_IP → JumpAir_Horiz → JumpLand_F_IP。落差超过四个狗身高先压低身子往下看一眼再跳；
- fall：脚下没东西了（窗口关了、被收走、切到别的桌面、被拖到半空松手）或被扔出去：重力 + 手给的速度，落到下面那条线上。
  扔出去撞到屏幕边、窗口的左右边和下边几乎不弹；飞不出屏幕。落地按掉了多高分三档（只拖了一点点，动作却像从很高掉下来）：
  很低（调参 land_light_m 以内）不播落地，脚回到线上轻轻 duang 一下；中间用 JumpLand_Place；高的才用 JumpLand。
  掉了多高看狗真飞到的最高点，不看松手在哪（低处松手往上扔，飞得很高落下来也得是前爪先着地）：往上飞的时候身子平着，
  过了最高点按「最高点到下面那条线」重挑空中的姿势——高的融成往下探（JumpAir_low）再前爪先着地，不高的照旧平着、脚先着地；
  半路下面那条线换了（飞过窗口边）跟着重挑（_advance_fall）。

大事（task）：
- fetch：球扔出去 → 看一眼 → 看得出球停哪就直接去落点，看不出就先追球本身（不是永远真追，很明显能预判的就直接去
  预判的点）。看得出 = 球这一路不再掉头（弧线、落地弹几下、滚到停）：用同一套物理算出它停在哪（playground.predict_rest），按路线跑过去。
  看不出 = 球还要撞墙、撞窗口侧边弹回来（playground.ball_turns_left 比调参 see_bounces 多，默认 0）：在脚下这一层朝球前面 CHASE_LEAD 秒
  的位置跑（_chase_step、_chase_update），球撞完、后面不再掉头了就改去落点。要跳的（上窗口、下窗口、跨屏）等球真落到那一层再跳，
  够不着的等球停了再叫（_hold_off：先走到这一层离得最近的地方看着球等）；不接空中的球。站着看球时球换了边、过一小会儿身子才转（_watch）。
  → 到了球还没停就看着它等 → 侧身正对球低头叼（鼻子碰到球那一刻道具接手：球的小窗口藏起来、
  狗嘴里的 3D 球出来，同一个位置；碰到之前球照样能被你拿走）→ 叼到鼠标旁边（球放在靠狗这一侧，点击范围碰不到鼠标；贴着边就换另一侧；
  路上鼠标挪了跟着改）→ 叼着等鼠标停稳再放（球离嘴前鼠标又挪远了就抬头收回来接着跟；一直挪超过几秒就放下）→ 就待在那（家改到这）。
  什么时候去追由 playground 定（进圈才追，widget/ring.py：圈满过才追，扔出去、放下都算；不猜玩还是挪开球）。
  不想让它捡就关「捡球」开关（playground.fetch_changed → fetch_off：跑着的停下，看着球的不看了，叼着的就地放下）。
  小幅后退不转身：要去的地方在身后 BACK_M 以内就直接倒着走；鼠标要越过狗 SIDE_SWITCH_M 才换到另一边。
  性子（widget/temper.py，边牧两项都是 1、下面这些都不走）：聪明程度低的看不出球停哪，一直追球本身、球停了才排路线去叼；追着的球掉头朝身后去了
  还往前多冲一小段才刹住；球放得离鼠标远一点（只往狗这一侧让）；叼回来的路上偶尔站住愣一下（_maybe_daze）。活跃度低的松手后还俯着愣一下才冲（fetch、_bow_step）。
  这几下、放下球、够不着叫完都报给 on_cue（playground 接去演表情）。
  球被你拿起来（包括半路、从嘴里拿走）：狗停下站着看你手里的球（watch，起身的时候也算；球到了另一边一小会儿才转身）。
  圈满了（host.fetch_ready，只看满没满这一个状态）：按调参 ready_bark 的概率叫一声（Bark 的第一声，嘴和声音对上），然后前肢俯下来等着
  （Idle_5_start 定在调参 bow_depth 那一帧，闭嘴，侧身对着球，尾巴摇）；松手立刻冲出去，叫到一半也冲。拿着不扔它就一直俯身等着；
  没满就松手（playground 叫 fetch_off）起身待着。够不着：走到离球最近的地方，冲它叫两声，就待在那（球留在那，可以再扔）。
- go：跑、跳到指定的那条线上，家改到那；够不着同样叫两声。
- nest（go_nest）：自己走回窝（摆着的狗窝、狗屋，widget/things.py）：最快小跑、不出声、够不着就不去（不叫）；到了报给 on_done，
  playground 接着让它趴下（settle_in）。不做了（call_off：窝被拿走了、球被拿起来了）就地站住，跳到一半的把这一跳跳完。
- eat（eat）：你敲了一下盆（摆着的饭盆、水盆）：走到盆旁边——鼻子最低那一刻正对盆心（props.spot 按模型量），盆那一边放不下狗就从另一边——
  转正 → EatDrink_start → Eat_loop / Drink_loop 循环 EAT_S 秒 → EatDrink_end（这一段一开始告诉 host 盆空了，host.bowl_emptied）→ 就待在那。
  够不着：照 go 走到最近的地方叫两声，盆不变空。吃喝的时候头不看鼠标（head_busy）。声音是这几段片段在包里绑的，这里不管。
  中途拿起球（ball_grabbed）、拎它、盆被拿走（host 叫 call_off）：抬头站住，盆还是满的。直接 puppet_play，不走控制器的吃喝动作：程序画的那只盆不出来。
- descend：站着的窗口被别的窗口盖住：走到一头跳下去；跳不下去原地掉。
- wander（wander）：自己溜达——在脚下这条线上慢慢走到 playground 挑好的地方（只走路、不跳、不换线、不出声），到了家改到这，报 on_done。
  不做了（call_off：你伸手过来、拿起球、球动了、拎它、打开卡片）就地站住。去盆边吃两口（eat 的 sip）：低头的那一段短一半、盆不变空，声音由 playground 静音。
- fall：见上。
拎起来（lift_begin、lift_end，只在灵动交互）：拎着的时候狗听手的（窗口跟着鼠标），姿势在 widget/lift.py；松手手还在动就是扔（throw），不动就掉。
家（home）记"哪条线 + 横着在哪"：窗口的记相对窗口左边的距离，窗口挪了家跟着挪；窗口没了就落到下面。
看细节（狗站在转台上，dog.on_turntable）：playground 关掉捡球（fetch_on），这里照常把手上的事做完；临时放大期间整个停住（update 的 hold）。"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable, Optional

from widget import temper
from widget.ball import HIT_PAD
from widget.clips import FADE_CLIP
from widget.gltf import mat_mul, measured, rot_y_mat, transform_point
from widget.props import BALL_R, LINGER
from widget.render import ELEVATION
from widget.world import Ball, Leaper, LeapSpec, Leg, Route, Support, plan_route, support_below, support_under

GAIT_CLIPS = {"walk": "Walk_F_IP", "trot": "Trot_F_IP", "run": "Run_F_IP", "fast": "RunFast_F_IP"}   # 片段本来的速度在模型包里（pack.gaits）
BACK_CLIP = "Walk_B_IP"
YAW_LEFT, YAW_RIGHT = 180.0, 0.0
ACCEL_M = 7.0               # 起跑 / 刹车的加速度（米 / 秒²）
GRAVITY_M = 9.8
MAX_UP_DOG = 3.0            # 一次最多往上跳身高的几倍，默认值（调参 max_up 改：更高的找中间的窗口当台阶，一级一级跳）。像素 = 这个 × 狗身高 × 比例尺，所以狗大跳得高、狗小跳得矮
BIG_DROP_DOG = 4.0          # 往下跳超过身高的几倍算大落差：先压低身子看一眼再跳；排路线时有台阶就一级一级下
DIVE_DROP_M = 1.0           # 落差至少这么大（米）落地才用前爪先着地的 JumpLand；小的 JumpLand_F_IP
DOG_H_M = 0.8               # 狗站着多高（含耳朵，米）：默认值，模型包的 height_m 为准
GAP_REACH_M = 1.0           # 同一层的两条线之间横着最多跳多远（米）：屏和屏的交界
MARGIN_FLOOR_M, MARGIN_WINDOW_M = 0.22, 0.30   # 狗的根离线头至少这么远（米）
SUPPORT_TOL = 10.0          # 脚离线多近（像素）算站在上面
EDGE_M = 0.6                # 过屏幕交界：离交界这么远起跳、落地（米，半个身长：蹲着起跳时鼻子还在这块屏里，不被边框切掉）
UP_MIN_M = 0.22             # 高度差小于这个就当"往前跳"，不算往上 / 往下
UP_CLEAR_M = 0.10           # 往上跳：骨盆到顶比落地片段第一帧高这么多（越过窗口边时后脚比台面高）
EDGE_FRONT_OVER_M = 0.09    # 直接落：前爪伸出线头这么多（后脚并过来正好踩在线头上）
EDGE_SWITCH = 0.45          # 直接落：起跳片段播到这里之前前爪站在边上、后脚并过来，之后后脚锁住、身子往下探


@dataclass(frozen=True)
class JumpClips:
    """一种跳法的片段：起跳、起跳的播放速度、空中、换到空中融多久、落地、换到落地融多久。"""
    start: Optional[str]
    speed: float
    air: str
    air_fade: float
    land: str
    land_fade: float


JUMPS = {
    "up": JumpClips("JumpStart_Up", 1.15, "JumpAir_Up", 0.10, "JumpLand_Place", 0.08),
    "push": JumpClips("JumpStart_F_IP", 1.0, "JumpAir_Horiz", 0.12, "JumpLand", 0.14),
    "hop": JumpClips("JumpStart_F_IP", 1.0, "JumpAir_Horiz", 0.12, "JumpLand_F_IP", 0.10),     # 落差小的 push
    "edge": JumpClips("JumpStart_Down_IP", 1.0, "JumpAir_high", 0.06, "JumpLand_Place", 0.14),
    "across": JumpClips("JumpStart_F_IP", 1.1, "JumpAir_Horiz", 0.10, "JumpLand_F_IP", 0.08),
    "fall": JumpClips(None, 1.0, "JumpAir_low", 0.15, "JumpLand", 0.08),      # 从高处掉下来：往下探，前爪先着地
    "drop": JumpClips(None, 1.0, "JumpAir_Horiz", 0.15, "JumpLand_Place", 0.08),   # 不高，或被扔出去还没过最高点：身子平着，脚先着地
}
AIR_SWAP_FADE = 0.2         # 过了最高点才知道真掉多高：空中的姿势换过去融这么久（平着 ↔ 往下探）
LAND_ERR_SECONDS = 0.2      # 落地那一刻骨盆和落地片段差一点（窗口在空中挪了、提前放手）：这么久里融掉，不跳
PEEK_AT, PEEK_HOLD = 0.3, 0.45   # 大落差：起跳片段播到这里（压低身子往下看）停这么久再跳
PEEK_PITCH = -22.0          # …往前蹬的片段头不够低：看的时候再低这么多度
FETCH_LOOK = 0.15           # 球扔出去先看这么久再追（性子两项都是 1 时；活跃度低的更久，temper.fetch_look）
HOP_UP_M = 0.9               # 程序坞出来、地面升上去这么高以内（米）：原地跳上去；再高就当没站稳、照常处理
BARK_ONE_UNTIL = 0.215      # 圈满时叫一声：Bark 片段放到这（第一声放完）
BARK_FROM, BARK_UNTIL = 0.10, 0.345   # 够不着：叫两声（Bark 片段这一段，嘴张开两次；声音在 pack.json 里按嘴张开的时刻放）
MAX_REPLANS = 3             # 叼球没对准时最多重新走几次，再不行就当够不着
RETARGET_EVERY = 0.5        # 叼着球往你那走时，多久看一次鼠标挪没挪（秒）
RETARGET_M = 0.8            # 目标挪了这么远（米）才改路线
CURSOR_MARGIN_PX = 8.0      # 球的点击范围离鼠标至少再隔这么多（像素）
ARROW_W_PX = 14.0           # 鼠标箭头往右下伸这么宽：球放在鼠标右边时多让开这些
HOLD_MOVE_M = 0.8           # 到了鼠标旁边以后目标挪了这么远（米）才跟过去，挪得少不算数，直接放（不跟手）
PUT_ABORT_M = 1.0           # 放球动作开始后、球离嘴前，目标挪了这么远（米）就抬头收回来接着跟
PUT_PATIENCE = 1.0          # 到了鼠标旁边以后鼠标一直走远：最多再跟这么久（秒）就放下
CARRY_PATIENCE = 12.0       # 叼起来以后最多追这么久（秒），鼠标一直动就放下
BACK_M = 0.7                # 要去的地方在身后这么近（米）：直接倒着走，不转身
SIDE_SWITCH_M = 0.5         # 鼠标 / 球要越过狗这么远（米）才换边
BOW_SPEED = 1.25            # 俯身片段的播放速度
EAT_S = 5.0                 # 敲盆叫来吃 / 喝：循环那一段多久（和表盘的吃、喝一样长，clips.ACTIONS）
EAT_CLIPS = ("EatDrink_start", "Eat_loop", "Drink_loop", "EatDrink_end")
SIP_SHARE = 0.5             # 自己溜达去吃两口（eat 的 sip）：低头吃喝那一段是 EAT_S 的这么多
NOSE_DOWN = {"fetch": ("face_ball", "pickup", "hold", "hold_done", "turn_put", "putdown"), "eat": ("face", "start", "loop", "end")}   # 鼻子要对着线上的东西（叼球、放球、吃喝）的那几步：这时身子不能抬在狗窝的垫子上（afoot）
FOOLED_MIN_M = 1.0          # 追着的球朝身后去得比这快（米 / 秒）才算被晃到（聪明程度低的；和算掉头的 playground.TURN_MIN_M 一个数）
DAZE_AFTER_M = 0.6          # 叼回来的路上愣一下（聪明程度低的）：叼起来以后走出这么远（米）才愣，路不够这么长就不愣
CHASE_LEAD = 0.4            # 追球本身时瞄它前面这么久的位置（秒；temper.chase_lead）
CHASE_NEAR_M = 0.3          # 追到离那一点这么近就站着看，不再挪
WATCH_TURN_S = 0.2          # 站着看球：球到了另一边、持续这么久才转身（来回弹的球不带着身子来回抖；temper.watch_turn）
BODY_HALF_M = 0.4          # 被扔在空中：身子往前后各占多少（米），撞屏幕边、窗口边用
THROW_MIN_PX = 3.0          # 扔出去的速度小于这个（像素 / 秒）当没扔
THROW_MAX_M = 30.0          # 扔出去最快多快（米 / 秒）
ROOM_STEP_PX = 24.0         # 算前面还能飞多远时一步试多长（像素）
LAND_FAST_M = 3.0           # 落地时横着比这快（米 / 秒）：不算轻落，脚先着地的落地片段
SLIDE_MAX_M, SLIDE_MIN_M, SLIDE_STOP_M = 6.0, 0.8, 0.25   # 落地后滑：最快多快；比 MIN 慢的不滑；慢到 STOP 就停（米 / 秒）
SLIDE_TAU = 0.16            # 滑的速度减慢的时间常数（秒）：最快时滑 6 × 0.16 ≈ 1 米（调参 land_slide 是倍数）


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


@dataclass
class Home:
    kind: str           # floor / window
    key: int
    dx: float           # 地面：绝对 x；窗口：离窗口左边多远
    y: float            # 那条线当时的 y


def leap_measures(dog) -> tuple[LeapSpec, float]:
    """跳上跳下要用的数，按模型量：(LeapSpec，蹬地速度是默认的、用的时候换成调参的；头朝下落时前爪碰到线那一刻骨盆在线上面多高，米，屏幕上的)。
    这个模型量一次记在模型上（gltf.Model.measured），新的 Roam、换上来的狗直接拿；别的模型由 widget/kits.py 在后台先量好。"""
    return measured(dog.model, "leap", lambda: _measure_leap(dog))


def _measure_leap(dog) -> tuple[LeapSpec, float]:
    ce = math.cos(math.radians(ELEVATION))
    planted = dog.planted_hind
    start = JUMPS["push"].start
    _, z0, _, _ = dog.foot_metrics(start, 0.0)
    h1, z1, _, _ = dog.foot_metrics(start, 1.0)
    ph, pz = dog.pelvis_metrics(start, 1.0)
    lh_big, lz_big = dog.pelvis_metrics(JUMPS["push"].land, 0.0)
    lh_small, lz_small = dog.pelvis_metrics(JUMPS["hop"].land, 0.0)
    drop = JUMPS["edge"].start
    lh_edge, lz_edge = dog.pelvis_metrics(JUMPS["edge"].land, 0.0)
    f0 = dog.foot_metrics(drop, 0.0)[3]
    _, hzs, _, fzs = dog.foot_metrics(drop, EDGE_SWITCH)
    foot = EDGE_FRONT_OVER_M - fzs + hzs                    # 后脚锁在离线头多远
    eh1, ez1, _, _ = dog.foot_metrics(drop, 1.0)
    eph, epz = dog.pelvis_metrics(drop, 1.0)
    ph_air = dog.pelvis_metrics(JUMPS["edge"].air, 0.0)[0]
    fh_air = dog.foot_metrics(JUMPS["edge"].air, 0.0)[2]
    edge_touch = (ph_air - (fh_air - planted)) * ce         # 头朝下落的时候：前爪碰到线时骨盆在线上面多高（米，屏幕上的）
    spec = LeapSpec(
        near=UP_MIN_M, floor_edge=EDGE_M, window_margin=MARGIN_WINDOW_M,
        push_x=(z0 - z1) + pz, push_h=(ph - (h1 - planted)) * ce,
        land_big=(lz_big, lh_big * ce), land_small=(lz_small, lh_small * ce), big_drop=DIVE_DROP_M,
        edge_stand=f0 - EDGE_FRONT_OVER_M, edge_land=(foot - ez1 + epz) - lz_edge, edge_h=(eph - (eh1 - planted)) * ce,
        edge_v=edge_speed(dog, 1.0), edge_land_h=max(lh_edge * ce, edge_touch))
    return spec, edge_touch


def edge_speed(dog, u: float) -> float:
    """直接落：探到进度 u 时骨盆往下多快（米 / 秒）：放手之后接着这个速度掉。"""
    clips = JUMPS["edge"]
    du = 0.03
    ce = math.cos(math.radians(ELEVATION))

    def below(v: float) -> float:
        hh, _, _, _ = dog.foot_metrics(clips.start, v)
        ph, _ = dog.pelvis_metrics(clips.start, v)
        return (hh - ph) * ce
    dur = dog.model.clips[clips.start].duration / clips.speed
    return max(0.0, (below(u) - below(u - du)) / (du * dur))


class Roam:
    """host（widget/playground.py）提供：ppm、world、supports()（现在能站的线：地面 + 窗口上沿）、window_top(窗口号, at_x)
    → 那个窗口现在的上沿（at_x 所在那一段）或 None、window_left(窗口号)、window_listed(窗口号)（还在这个桌面上、没被收走）、
    cursor()（鼠标在哪）、home_yaw_here()（狗现在的位置该朝哪）、ball / ball_held、ball_carried(叼没叼着)、
    ball_dropped(gx, gy, vx, vy)（球交接）、predict_rest()、ball_turns_left()（球到停下还要掉头几次）、ball_turns（已经掉过几次）、
    ball_ahead(秒)（球过一会儿在哪）、ball_down_on(线)（球落到过这条线没有）、throw_id、barking(kind, key, x)（够不着那条线上的 x，正冲那边叫）、
    fetch_ready（你手里的球在圈里停够了：该叫一声、俯身等你扔）、
    pack（模型包）、tune[…]（调参）、route_blocks()（挡路的窗口）、ball_edges()（窗口的左右边、下边）、dog_landed(速度)。"""

    def __init__(self, dog, host):
        self.dog = dog                              # 换模型时换成新的那只（use_dog）
        self.host = host
        self.wx = self.wy = 0.0
        self.support: Optional[Support] = None
        self.ride_left: Optional[float] = None      # 站在窗口上：上一帧窗口左边在哪（窗口挪了狗跟着挪）
        self.home: Optional[Home] = None
        self.task: Optional[str] = None
        self.phase = ""
        self.route: list[Leg] = []
        self.leg: Optional[dict] = None
        self.carrying = False
        self.facing = -1.0                          # +1 朝右 / -1 朝左
        self.v = 0.0                                # 横向速度（像素 / 秒，带方向）
        self.moved = False                          # 这一帧挪了位置（窗口要跟着挪）
        self._ready_seen = False                    # 这次拿着球，圈满以后该不该叫已经定过了（叫没叫都只定一次；_wait_for_throw）
        self.t = 0.0
        self.replans = 0
        self.planned = -1                           # 按第几次扔排的路线（playground.throw_id）
        self._plan_turns = 0                        # 排这条路线时算好的：球会掉头到第几次（playground.ball_turns）；又多掉了一次就重新看
        self._watch_since: Optional[float] = None   # 站着看球：球从什么时候起一直在身后那边
        self.wait_ball = 0.0
        self.pending_fetch = False
        self.on_done: Optional[Callable[[str], None]] = None
        self._target: Optional[tuple[Support, float]] = None   # 叼着球要去的地方（线, x）
        self._retarget_at = 0.0
        self._put_dir = -1.0                        # 放球时朝哪边（朝着鼠标，球在狗和鼠标之间）
        self._put_final = False                     # 这次放下不收回来接着跟（捡球关了、上了转台：就地放下就是放下）
        self._bark_at: Optional[tuple[str, int, float]] = None      # 够不着哪：(线的 kind, key, x)，叫的时候冲着那边
        self._picked_at = 0.0                       # 什么时候叼起来的
        self._arrived_at: Optional[float] = None    # 什么时候第一次走到鼠标旁边
        self._deliver_side: Optional[float] = None  # 球放在鼠标哪一边（-1 左、+1 右）：鼠标要越过狗 SIDE_SWITCH_M 才换
        self.lifted = False                         # 被你拎着
        self._short = 0.0                           # 这一趟球放得比该放的地方离鼠标远多少（米；聪明程度低的，叼到那一刻定，temper.drop_short）
        self._daze: Optional[float] = None          # 这一趟路上还要愣多少秒（None = 不愣 / 愣过了；temper.daze）
        self._carry_from = 0.0                      # 在哪叼起来的
        self.on_cue: Optional[Callable[[str], None]] = None   # 值得演个表情的时刻（put 放下球 / fooled 被晃到 / stumped 够不着叫完 / daze 路上愣住）：playground 接
        self._spec: Optional[LeapSpec] = None
        self._edge_touch = 0.0
        self._nest_yaw: Optional[float] = None      # 走回窝：到了朝哪（go_nest 给的；None = 照平时歇着的朝向）
        self._eat: tuple[float, str, bool] = (1.0, "Eat_loop", False)   # 去吃 / 喝：(站好以后朝哪边, 循环的那一段, 只吃两口)

    # ---------- 比例尺 ----------
    @property
    def ppm(self) -> float:
        """空间的比例尺：存下来的大小（playground.ppm）。看细节临时放大时狗画得更大，但那时 roam 不走（update 的 hold），
        这里的路线、根和 _to_screen / scene_point / mouth_point 算的屏幕位置只在画的大小和存下来的一样时才对。"""
        return self.host.ppm

    def m(self, meters: float) -> float:
        return meters * self.ppm

    @property
    def busy(self) -> bool:
        return self.task is not None

    @property
    def watching_ball(self) -> bool:
        """在看着球（你拿着时站着看、俯身等着，扔出去先看一眼、追它、跑去落点、等它落到那一层、等它停、冲它汪）。"""
        return self.task == "fetch" and not self.carrying and self.phase in (
            "look", "watch", "bow", "chase", "standby", "approach", "wait_ball", "bark_go", "bark", "barked")

    @property
    def waiting_for_throw(self) -> bool:
        """狗站在原地等你扔手里的球（起身的那一下、站着看、圈满时叫的那一声、俯身）：根不动，捡球的圈只在这时算（playground._step_ring）。
        跳到一半、掉着、被拎着、在跑都不算。球在不在你手上这里不管（host 自己知道）。"""
        leg = self.leg
        return self.task == "fetch" and not self.carrying and self.phase in ("look", "watch", "bow") \
            and (leg is None or leg.get("kind") in ("stand", "wait", "clip", "bow"))

    @property
    def head_busy(self) -> bool:
        """头正埋在盆里（吃、喝的那几段）：不看鼠标（window._look_target）。"""
        return self.task == "eat" and self.phase in ("start", "loop", "end")

    @property
    def bowing(self) -> bool:
        """球在你手上，狗俯身等着。"""
        return self.leg is not None and self.leg.get("kind") == "bow"

    @property
    def airborne(self) -> bool:
        return self.leg is not None and self.leg.get("stage") == "air"

    @property
    def afoot(self) -> bool:
        """脚踩在线上，只是跑、走、站（歇）着：没被拎，没在跳、掉、被扔（整段跳连蹲和落地都不算），也没在低头叼球、放球、吃喝（NOSE_DOWN）。
        踩不踩狗窝的垫子看它（playground._tread）。"""
        if self.lifted or self.support is None:
            return False
        if self.leg is not None and self.leg.get("kind") in ("jump", "fall"):
            return False
        return self.phase not in NOSE_DOWN.get(self.task, ())

    @property
    def height_m(self) -> float:
        return self.host.pack.height_m

    def max_up(self) -> float:
        return temper.max_up(self.host.tune) * self.m(self.height_m)                # 调参 max_up 按性子打折（边牧不打）

    def margin(self, s: Support) -> float:
        return self.m(MARGIN_WINDOW_M if s.kind == "window" else MARGIN_FLOOR_M)

    def leap_spec(self) -> LeapSpec:
        """跳上跳下要用的数：按模型量的（leap_measures，记在模型上）+ 调参的蹬地速度。"""
        if self._spec is None:
            self._spec, self._edge_touch = leap_measures(self.dog)
        vx = self.host.tune["push_vx"]
        if abs(self._spec.push_vx - vx) > 1e-6:
            self._spec = replace(self._spec, push_vx=vx)
        return self._spec

    def _edge_speed(self, u: float) -> float:
        return edge_speed(self.dog, u)

    def leaper(self) -> Leaper:
        return Leaper(self.host.world, self.ppm, self.leap_spec(), self.host.route_blocks())

    def _route(self, here: Support, x: float, goal: Support, gx: float, margin: Optional[float] = None) -> Route:
        return plan_route(self.host.supports(), here, x, goal, gx, self.max_up(), self.m(GAP_REACH_M),
                          self.m(MARGIN_FLOOR_M) if margin is None else margin, self.leaper(),
                          soft_drop=self.m(BIG_DROP_DOG * self.height_m))

    # ---------- 位置 ----------
    def place(self, wx: float, wy: float) -> None:
        """窗口被拖过、缩放过、启动刚放好：从窗口读回来的位置。"""
        self.wx, self.wy = wx, wy

    def here(self) -> Support:
        s = self.support or support_under(self.host.supports(), self.wx, self.wy, SUPPORT_TOL)
        return s or self.host.world.nearest_floor(self.wx, self.wy)

    def settle_support(self) -> Optional[Support]:
        """脚下是哪条线（容差 SUPPORT_TOL，贴上去）；没有就 None（悬空，要掉下去）。正站着的窗口重新问一次它现在在哪。"""
        s = self.support
        if s is not None and s.kind == "window":
            s = self.host.window_top(s.key, at_x=self.wx) if self.host.window_listed(s.key) else None
        if s is None or not s.covers(self.wx, 0.0) or abs(s.y - self.wy) > SUPPORT_TOL:
            s = support_under(self.host.supports(), self.wx, self.wy, SUPPORT_TOL)
        self.support = s
        if self.support is not None:
            if abs(self.support.y - self.wy) > 0.01:
                self.wy = self.support.y
                self.moved = True
            self.ride_left = self.host.window_left(self.support.key) if self.support.kind == "window" else None
        return self.support

    def _fresh_floor(self, s: Support) -> Support:
        """地面按现在的大小重建过（离屏幕底边的距离跟着大小变）：同一块屏、盖得住现在这个 x 的那条。"""
        world = self.host.world
        return next((f for f in world.floors if f.key == s.key and f.covers(self.wx)), None) or world.nearest_floor(self.wx, self.wy)

    def reseat(self) -> None:
        """大小变了：站在地面上的，脚贴到新的那条地面上（不再"掉一下"）；正在去捡球 / 叼着球走的，按新大小重排路线。"""
        s = self.support
        if s is not None and s.kind == "floor" and not self.airborne:
            f = self._fresh_floor(s)
            self.support = f
            if self.leg is not None and "plane" in self.leg:
                self.leg["plane"] = f.y                             # 正蹲着起跳 / 正在落地：脚踩的平面跟着换
            elif abs(f.y - self.wy) > 0.01:
                self.wy = f.y
                self.moved = True
        if self.task == "fetch" and not self.airborne and self.phase in (
                "look", "plan", "chase", "standby", "approach", "wait_ball", "face_ball", "carry", "hold"):
            self.route = []
            self._stop_leg()
            self.phase = "deliver" if self.carrying else "look"

    def remember_home(self) -> None:
        s = self.support
        if s is None:
            return
        if s.kind == "window":
            left = self.host.window_left(s.key)
            self.home = Home("window", s.key, self.wx - (left if left is not None else s.x0), s.y)
        else:
            self.home = Home("floor", s.key, self.wx, s.y)

    def home_target(self) -> tuple[Support, float]:
        """家现在在哪：(线, x)。窗口没了 / 不在这个桌面了 / 屏幕变了：回到正下方的那条线（或最近的地面）。"""
        h = self.home
        sups = self.host.supports()
        if h is not None and h.kind == "window":
            left = self.host.window_left(h.key) if self.host.window_listed(h.key) else None
            if left is not None:
                top = self.host.window_top(h.key, at_x=left + h.dx)
                if top is not None:
                    return top, top.clamp(left + h.dx, self.margin(top))
                x = left + h.dx
            else:
                x = h.dx
            s = support_below(sups, x, h.y + 1)
            if s is not None:
                return s, s.clamp(x, self.margin(s))
        elif h is not None:
            s = support_under(sups, h.dx, h.y, SUPPORT_TOL) or support_below(sups, h.dx, h.y)
            if s is not None:
                return s, s.clamp(h.dx, self.margin(s))
        f = self.host.world.nearest_floor(self.wx, self.wy)
        return f, f.clamp(self.wx, self.margin(f))

    # ---------- 大事：开始、收尾 ----------
    def start(self, task: str, route: Optional[Route] = None) -> None:
        self.dog.puppet_begin()
        self.task = task
        self._put_final = False
        self._nest_yaw = None
        self.route = list(route.legs) if route else []
        self.leg = None
        self.phase = ""
        self.replans = 0
        if self.dog.puppet_stand_needed():
            self.dog.puppet_stand()
            self.leg = {"kind": "stand"}

    def finish(self) -> None:
        """做完：交回控制器，0.3 秒转回现在这个位置该朝的方向（host.home_yaw_here）。"""
        task = self.task
        self.task, self.route, self.leg, self.phase = None, [], None, ""
        self.v = 0.0
        self._target = None
        self._quiet_pose()
        if self.carrying:                                   # 不该发生：还叼着就放在嘴下面
            self._drop_from_mouth()
        self.dog.puppet_end()
        home_yaw = self.host.home_yaw_here()
        if home_yaw is not None:
            self.dog.home_yaw = home_yaw
        if abs(_wrap(self.dog.home_yaw - self.dog.yaw)) > 1.0:
            self.dog.settle.yaw = (self.dog.yaw, self.dog.home_yaw, 0.0)
        if self.on_done is not None and task is not None:
            self.on_done(task)
        if self.pending_fetch:
            self.pending_fetch = False
            self.fetch()

    def leave(self) -> None:
        """换了一只狗（换模型，playground.pet_leaving；这时看不见）：旧狗手上的事全作废——叼着的球原地松口（不带速度，球的小窗口回来）、
        跑到一半、跳到一半、被扔着的都不接着做（不接着飞）。位置留着，换上来的狗站哪由 land_now 定。拎着的由 playground 先放下。"""
        if self.carrying:
            self._drop_from_mouth(speed=0.0)
        self.cancel(drop_ball=False)
        self.leg, self.route, self.v = None, [], 0.0

    def use_dog(self, dog) -> None:
        """牵的换成这一只（换模型，playground.pet_arrived）：跳法的数按它的模型重拿（leap_measures，记在模型上，不重量）。"""
        self.dog = dog
        self._spec = None
        self._edge_touch = 0.0

    def land_now(self) -> None:
        """换了一只狗（换模型）：站在旧狗那条线上——脚下的线还在、站得下这只（按新狗的个头，host.supports）就站在原地；
        在半空的、脚下那条站不下它的（新狗更高、头顶不够了）直接放到正下方最近的线上，没有就最近的地面。不起 fall、不播落地（这时看不见），记作家。"""
        sups = self.host.supports()
        s = support_under(sups, self.wx, self.wy, SUPPORT_TOL)
        if s is None:
            s = support_below(sups, self.wx, self.wy - 1.0) or self.host.world.nearest_floor(self.wx, self.wy)
        x = s.clamp(self.wx, 0.0)
        if abs(x - self.wx) > 0.01 or abs(s.y - self.wy) > 0.01:
            self.wx, self.wy = x, s.y
            self.moved = True
        self.support = s
        self.ride_left = self.host.window_left(s.key) if s.kind == "window" else None
        self.remember_home()

    def cancel(self, drop_ball: bool = True) -> None:
        """被打断（拖走狗、关掉灵动交互）：叼着的球掉在嘴下面；控制器交回。"""
        if self.carrying and drop_ball:
            self._drop_from_mouth()
        self.pending_fetch = False
        self._ready_seen = False
        self._quiet_pose()
        if self.task is not None:
            self.task, self.route, self.leg, self.phase = None, [], None, ""
            self.v = 0.0
            self._target = None
            self.dog.props.cut()
            self.dog.puppet_end()

    def _cue(self, name: str) -> None:
        if self.on_cue is not None:
            self.on_cue(name)

    def _quiet_pose(self) -> None:
        """俯身的闭嘴、空中的没影子这些临时的都收掉。"""
        self.dog.shut_mouth = False
        self.dog.hide_shadow = False

    # ---------- 外面叫的 ----------
    def fetch(self) -> None:
        """球被扔出去了（圈满过才叫，playground._let_go）：去追。在追了就重新算（路上不打断跳）；俯身等着的、圈满正叫着的立刻冲出去；
        正在起身的站起来再追；正在空中（跳窗口、掉下来）等落地再追。
        活跃度低的慢半拍（temper.release_beat，边牧 0）：俯身的还俯着看球那么久才起身冲（_bow_step 的 go_at），站着的多站那么久。"""
        if self.task == "fetch" and not self.carrying and self.phase not in ("bark", "barked"):
            beat = temper.release_beat(self.host.tune)
            self.phase = "look"
            self.route = []
            leg = self.leg
            if leg is not None and leg.get("kind") == "bow":
                if beat > 0.0:                              # 慢半拍：还俯着（头跟着球，尾巴照摇），到点 _bow_step 起身
                    leg["go_at"] = self.t + beat
                    self.phase = "bow"
                else:
                    self._end_bow()                         # 不回站姿：下一帧直接跑
                    self.leg = None
            elif leg is not None and (leg.get("kind") in ("run", "wait", "face") or leg.get("ready_bark")):
                self._stop_leg()
                if beat > 0.0:
                    self.leg = {"kind": "wait", "until": self.t + beat}
            return
        if self.task == "fetch" and self.carrying:
            return                                          # 正叼着（球在嘴里，扔的不是这个球）
        if self.airborne or self.task == "fall":
            self.pending_fetch = True
            return
        if self.task is not None:
            self.cancel(drop_ball=True)
        self.start("fetch")
        self.phase = "look"
        self.leg = self.leg or {"kind": "wait", "until": self.t + temper.fetch_look(self.host.tune)}

    def fetch_off(self) -> None:
        """捡球的闸关了（「捡球」开关、上了转台），或者圈没满你就松了手：跑着的停下、看着球的不看了、俯身的起来，
        叼着的就地放下（放的时候鼠标在别处也不收回来接着跟：_watch_putdown）。"""
        self.pending_fetch = False
        if self.task != "fetch":
            return
        if self.carrying:
            self._put_here()
            self._put_final = True
            return
        if self.leg is not None and self.leg.get("kind") == "bow":
            self._end_bow()
            self.leg = None
        if self.phase == "pickup":
            self.dog.props.cut()
        self.route = []
        self._stop_leg()
        self.phase = "done"

    def ball_grabbed(self) -> None:
        """球被你拿起来了（包括狗正低头去叼、鼻子还没碰到的时候；捡球开着才走到这）：狗停下，站好看着你手里的球（watch），
        圈满了才叫、俯身（_wait_for_throw）。空中的等落地；别的事（跳到你拉的地方、掉下来）做完 playground 再叫一次。"""
        self._ready_seen = False
        if self.leg is not None:
            self.leg.pop("go_at", None)                     # 松手后愣着的那半拍里又拿起来了：不冲了，_bow_step 照「圈还满不满」接着看
        if self.task in ("nest", "eat", "wander"):
            self.call_off()                                 # 自己的事、吃到一半、溜达都让给球（跳到一半的落地再说：playground 等它不忙了再叫一次）
        if self.task is None:
            self.start("fetch")
            self.phase = "look"
        elif self.task == "fetch" and not self.carrying and self.phase not in ("watch", "bow"):
            if self.phase == "pickup":
                self.dog.props.cut()
            self.phase = "look"
            self.route = []
            self._stop_leg()

    # ---------- 拎起来、扔出去 ----------
    def lift_begin(self) -> None:
        """被你拎起来：正在做的作废（叼着的球掉下来），姿势变成肚子提着、四腿垂着。位置听窗口的（input.py 拖的是窗口）。"""
        self.cancel(drop_ball=True)
        self.support, self.ride_left = None, None
        self.lifted = True
        tune = self.host.tune
        lift = self.dog.lift
        lift.bob, lift.sway = tune["float_bob"], tune["float_sway"]
        lift.begin()
        self.dog.puppet_begin()
        self.dog.puppet_stand()
        self.dog.puppet_play("Idle_1", loop=True, fade=0.18, restart=False)

    def lift_end(self, vx: float = 0.0, vy: float = 0.0) -> None:
        """松手：手还在动就扔出去（vx、vy 是这东西飞出去的速度，像素 / 秒），不动就掉下去；脚下就是线就站在那。"""
        was_lifted = self.lifted
        self.lifted = False
        self.dog.lift.end()
        if math.hypot(vx, vy) >= THROW_MIN_PX:
            self.throw(vx, vy)
        else:
            self.drop_to_support()
        if self.task is None and was_lifted:
            self.dog.puppet_end()
            self._settle_yaw()

    def throw(self, vx: float, vy: float) -> None:
        """被扔出去：飞到哪落到哪。"""
        if self.task is not None:
            self.cancel(drop_ball=True)
        self.support, self.ride_left = None, None
        self.start("fall")
        speed, cap = math.hypot(vx, vy), self.m(THROW_MAX_M)
        if speed > cap:
            vx, vy = vx * cap / speed, vy * cap / speed
        self.leg = self._fall_leg(vx, vy)

    def _settle_yaw(self) -> None:
        home_yaw = self.host.home_yaw_here()
        if home_yaw is not None:
            self.dog.home_yaw = home_yaw
        if abs(_wrap(self.dog.home_yaw - self.dog.yaw)) > 1.0:
            self.dog.settle.yaw = (self.dog.yaw, self.dog.home_yaw, 0.0)

    def mouth_point(self) -> Optional[tuple[float, float]]:
        """叼着的球现在在屏幕上的哪（全局坐标，嘴角前一点）；还没画过一帧 None。"""
        dog = self.dog
        if dog._last is None:
            return None
        root, g = dog._last
        p = transform_point(mat_mul(root, g[dog.head]), dog.props.mouth)
        return self.scene_point(p[0], p[1], p[2])

    def let_go(self) -> None:
        """叼着的球被你从嘴里拿走：松口（球放在嘴那里），站住看着你，等你再扔。"""
        if not self.carrying:
            return
        self._drop_from_mouth(speed=0.0)
        if self.task == "fetch":
            self.phase = "look"
            self.route = []
            self._target = None
            self._stop_leg()

    def route_to(self, s: Support, x: float) -> Route:
        """从现在的地方走到 s 上的 x 的路线（按住狗再拉时看够不够得着）。"""
        return self._route(self.here(), self.wx, s, s.clamp(x, self.margin(s)), self.margin(s))

    def go_to(self, s: Support, x: float) -> bool:
        """按住狗再拉：跑、跳到 s 上的 x，家改到那。够不着：走到最近的地方，冲那边叫两声。正在忙不理。返回够不够得着。"""
        if self.busy:
            return False
        route = self.route_to(s, x)
        self.start("go", route)
        if not route.reachable:
            self._bark_at = (s.kind, s.key, x)
            self.phase = "bark_go"
        return route.reachable

    def go_nest(self, s: Support, x: float, yaw: Optional[float] = None) -> bool:
        """自己走回窝（s 上的 x）：安静地过去（最快小跑，_gait），到了先转到 yaw（给了的话：歇在狗屋门口头朝外），再报 on_done("nest")。
        够不着、正忙着、被拎着：不去也不叫，返回 False。"""
        if self.busy or self.lifted:
            return False
        route = self.route_to(s, x)
        if not route.reachable:
            return False
        self.start("nest", route)
        self._nest_yaw = yaw
        return True

    def wander(self, s: Support, x: float) -> bool:
        """自己溜达（playground._wander 挑好了去哪）：在脚下这条线上走到 x，只走路（_gait）、不出声；到了家改到这，报 on_done("wander")。
        正忙着、被拎着、路线够不着或者要跳（换了线）：不去，返回 False。"""
        if self.busy or self.lifted:
            return False
        route = self.route_to(s, x)
        if not route.reachable or any(leg.kind != "run" for leg in route.legs):
            return False
        self.start("wander", route)
        return True

    def eat(self, s: Support, x: float, drink: bool = False, bark: bool = True, sip: bool = False) -> bool:
        """你敲了盆（在 s 上的 x）：过去吃（drink：喝）。站哪：盆在狗哪边就从哪边过去，鼻子最低那一刻正对盆心；那边放不下狗换另一边。
        够不着（两边都放不下、路线不通）：走到最近的地方叫两声（人在叫它，可以出声）；bark=False（满盆刚摆下来，没人叫它）就不去也不叫。
        正忙着、被拎着不理。返回去不去得成。"""
        if self.busy or self.lifted:
            return False
        if any(c not in self.dog.model.clips for c in EAT_CLIPS):
            return False                                    # 这个模型没有吃喝的动作
        loop = "Drink_loop" if drink else "Eat_loop"
        d = 1.0 if x >= self.wx else -1.0
        gx = x - self._spot_offset(loop, d)
        if not s.covers(gx, self.margin(s) * 0.5):
            d = -d
            gx = x - self._spot_offset(loop, d)
        fits = s.covers(gx, 0.0)
        route = self._route(self.here(), self.wx, s, gx, self.margin(s) * 0.5) if fits else self.route_to(s, x)
        if not bark and not (fits and route.reachable):
            return False
        self.start("eat", route)
        self._eat = (d, loop, sip)
        if not fits or not route.reachable:
            self._bark_at = (s.kind, s.key, x)
            self.phase = "bark_go"
            return False
        self.phase = "go"
        return True

    def _eat_step(self) -> None:
        """去吃走到哪一步了（没在走的时候调）：到了 → 转正 → 低头 → 吃 / 喝 EAT_S 秒 → 抬头（盆这时空了）→ 待在这。"""
        d, loop, sip = self._eat
        ph = self.phase
        if ph == "go":
            self.phase = "face"
            self.leg = {"kind": "face", "yaw": YAW_RIGHT if d > 0 else YAW_LEFT}
        elif ph == "face":
            self.phase = "start"
            self.dog.puppet_play("EatDrink_start", loop=False, fade=FADE_CLIP)
            self.leg = {"kind": "clip", "clip": "EatDrink_start"}
        elif ph == "start":
            self.phase = "loop"
            self.dog.puppet_play(loop, loop=True, fade=FADE_CLIP)
            self.leg = {"kind": "wait", "until": self.t + EAT_S * (SIP_SHARE if sip else 1.0)}
        elif ph == "loop":
            self.phase = "end"
            if not sip:
                self.host.bowl_emptied()                    # 吃两口（自己溜达过来的）盆不变空
            self.dog.puppet_play("EatDrink_end", loop=False, fade=FADE_CLIP)
            self.leg = {"kind": "clip", "clip": "EatDrink_end"}
        else:
            self._stay_here()

    def call_off(self) -> None:
        """自己的事（走回窝、去吃、溜达）不做了：就地站住（吃到一半的抬头）；跳到一半的把这一跳跳完再停（空中一刀切会悬在半空）。"""
        if self.task not in ("nest", "eat", "wander"):
            return
        self._nest_yaw = None
        if self.leg is not None and self.leg.get("kind") in ("jump", "fall"):
            self.route = []
            self.phase = "off"                              # 落地以后不接着吃、不叫，就待在那
            return
        self.cancel()

    def halt(self) -> None:
        """站上转台（看细节：进那一页狗就站着）：就地站住，不接着去——走回窝、去吃（call_off），被拉去别处、跳下被盖住的窗口
        （路线到这为止：家改到这）；跳到一半的把这一跳跳完再停（空中一刀切会悬在半空）。追球的由 fetch_off 管（叼着的要放下）；
        掉着、被扔着、被拎着的不管，落地、松手了自己会停。"""
        if self.task in ("nest", "eat", "wander"):
            self.call_off()
            return
        if self.task not in ("go", "descend"):
            return
        self.route = []
        if self.leg is not None and self.leg.get("kind") in ("jump", "fall"):
            self.phase = "off"                              # 落地以后不叫、不接着走
            return
        self._stop_leg()
        self.phase = ""                                     # 下一帧走完：站稳、家改到这、交回控制器（update 的收尾）

    def descend(self) -> bool:
        """站着的窗口上沿被别的窗口盖住了：走到一头跳下去；跳不下去原地掉。"""
        here = self.here()
        if self.busy or here.kind != "window":
            return False
        others = [s for s in self.host.supports() if not (s.kind == "window" and s.key == here.key)]
        below = support_below(others, self.wx, self.wy + 2)
        if below is None:
            return False
        route = self.route_to(below, self.wx)
        if route.reachable:
            self.start("descend", route)
        else:
            self.support, self.ride_left = None, None
            self._lost_footing()
        return True

    def floor_changed(self) -> None:
        """屏幕的可用区域变了（程序坞出来、收起来）：还站得住就不动；脚下这条线没了、新地面在头顶上不远（程序坞那一带）：
        原地往上跳上去（和跳上窗口沿同一跳）；新地面在下面：照常掉下去。正忙着、拎着、在空中的不管（落地时自己会找）。"""
        if self.busy or self.lifted or self.airborne:
            return
        self.support, self.ride_left = None, None                   # 记着的那条线是旧空间里的：按新空间重新找
        if self.settle_support() is not None:
            return
        above = self.host.world.floor_above(self.wx, self.wy)
        if above is not None and self.wy - above.y <= HOP_UP_M * self.ppm:
            x = above.clamp(self.wx, self.margin(above))
            self.start("go", Route([Leg("jump", above, x, self.wx, self.wy, "up")]))
            return
        self.drop_to_support()

    def drop_to_support(self) -> None:
        """被拖到半空松手、窗口不见了、屏幕变了：脚下没东西就掉下去；有就站稳、记作家。"""
        if self.settle_support() is not None:
            if not self.busy:
                self.remember_home()
            return
        if self.task != "fall":
            if self.task is not None:
                self.cancel(drop_ball=True)
            self.start("fall")
        self.leg = self._fall_leg()

    def _stop_leg(self) -> None:
        """跑到一半要改主意：就地停下（跳到一半的不管，等它落地）。"""
        if self.leg is not None and self.leg.get("kind") in ("jump", "fall"):
            return
        self.leg = None
        self.v = 0.0
        self._idle()

    # ---------- 每帧 ----------
    def update(self, dt: float, hold: bool = False) -> None:
        """每帧推一步。hold：整个停住——不走、不跟着脚下的窗口挪、不掉、钟也不走，这一帧也不算挪过（moved）。
        看细节临时放大时用（window.show_scaled）：那时狗画的比例和空间不一样（host.ppm 是存下来的大小），根在屏幕上的位置和这里的 (wx, wy) 对不上；
        缩回来再接着走（站的窗口这期间挪了、没了，那时才跟、才掉）。"""
        self.moved = False
        if hold:
            return
        self.t += dt
        if self.lifted:
            return
        self._ride()
        if self.task is None:
            return
        if self.task == "fetch":
            if self.carrying:
                if self.phase == "carry":
                    if self._out_of_patience():
                        self._put_here()
                    else:
                        self._maybe_retarget()
                        if self._daze is not None:
                            self._maybe_daze()
            elif self.phase == "chase":
                self._chase_update()
            elif self.phase in ("approach", "wait_ball", "standby") and self.host.ball_turns > self._plan_turns:
                if self.leg is None or self.leg.get("kind") in ("run", "wait"):   # 球掉了个没料到的头：重新看（正在跳的等落地）
                    self.phase = "plan"
                    self.route = []
                    self.leg = None
        if self.leg is None:
            if self.route:
                self._begin_leg(self.route.pop(0))
            elif self.task == "fetch":
                self._fetch_step()
                if self.leg is None and self.route and self.v != 0.0:
                    self._begin_leg(self.route.pop(0))                  # 跑着改了主意（追球 → 去落点）：这一帧就接着跑，不顿一下
            elif self.phase in ("bark_go", "bark", "barked"):
                self._bark_step()
            elif self.task == "eat":
                self._eat_step()
            elif self.task == "nest" and self._nest_yaw is not None:    # 走到窝了：先转到该朝的那边，下一轮再收尾
                self.leg = {"kind": "face", "yaw": self._nest_yaw}
                self._nest_yaw = None
            else:
                self.settle_support()
                if self.support is None:
                    self.leg = self._fall_leg()
                    return
                self.remember_home()
                self.finish()
                return
        if self.leg is not None and self._advance_leg(dt):
            self.leg = None

    def after_pose(self) -> None:
        """这一帧的姿势定下来以后（窗口画完 dog.frame 调）：跳的时候按真实的姿势摆根，身子走的路线不受换片段、融合影响。"""
        leg = self.leg
        if leg is None or leg["kind"] not in ("jump", "fall"):
            return
        stage = leg.get("stage")
        if stage == "crouch":
            self._place_stance(leg)
        elif stage == "air":
            self._place_air(leg)
        elif stage == "land":
            self._place_land(leg)

    # ---------- 骑在窗口上 ----------
    def _ride(self) -> None:
        """站在窗口上沿（或正沿着它跑）：窗口挪了跟着挪；窗口没了、不在这个桌面了、被收走了、上沿挪开了就掉下去。
        空中的不管（落地时再看）。"""
        s = self.support
        if s is None or s.kind != "window" or self.airborne:
            return
        left = self.host.window_left(s.key) if self.host.window_listed(s.key) else None
        top = None
        if left is not None:
            top = self.host.window_top(s.key, at_x=self.wx + ((left - self.ride_left) if self.ride_left is not None else 0.0))
        if left is None or top is None:
            self.support, self.ride_left = None, None
            self._lost_footing()
            return
        dx = (left - self.ride_left) if self.ride_left is not None else 0.0
        dy = top.y - s.y
        if abs(dx) > 0.01 or abs(dy) > 0.01:
            self.wx += dx
            self.wy += dy
            self.moved = True
            if self.leg is not None:                        # 正在窗口上跑：目标跟着挪
                if "to" in self.leg and self.leg.get("support") is not None and self.leg["support"].kind == "window" \
                        and self.leg["support"].key == s.key:
                    self.leg["to"] += dx
                for key in ("foot_x", "front_x", "lx"):             # 正蹲着起跳 / 正在落地：脚踩的地方跟着挪
                    if self.leg.get(key) is not None:
                        self.leg[key] += dx
                if "plane" in self.leg:
                    self.leg["plane"] += dy
        self.support, self.ride_left = top, left
        planted = self.leg is not None and self.leg.get("stage") in ("crouch", "land")   # 这两段根会伸出线头（后脚还踩着），不算掉
        if not planted and not top.covers(self.wx, 0.0):
            self.support, self.ride_left = None, None
            self._lost_footing()

    def _lost_footing(self) -> None:
        """脚下的窗口没了：掉下去（正在做的事作废，叼着的球跟着掉）。"""
        if self.task == "fall":
            return
        if self.task is not None:
            self.cancel(drop_ball=True)
        self.start("fall")
        self.leg = self._fall_leg()

    # ---------- 一段段走 ----------
    def _begin_leg(self, leg: Leg) -> None:
        if leg.kind == "run":
            self.leg = {"kind": "run", "to": leg.x, "support": leg.support, "stage": "face"}
        else:
            self.leg = {"kind": "jump", "to": leg.x, "support": leg.support, "stage": "face", "mode": leg.mode}

    def _advance_leg(self, dt: float) -> bool:
        leg = self.leg
        kind = leg["kind"]
        if kind == "stand":
            return not self.dog.transition
        if kind == "wait":
            return self.t >= leg["until"] or (leg.get("until_ready", False) and self.host.fetch_ready)
        if kind == "face":
            if not leg.get("started"):
                self.dog.puppet_face(leg["yaw"])
                leg["started"] = True
                self.facing = 1.0 if math.cos(math.radians(leg["yaw"])) > 0 else -1.0
            return not self.dog.puppet_turning
        if kind == "clip":
            hook = leg.get("hook")
            if hook is not None:
                hook()
            p = self.dog.player
            return p.name != leg["clip"] or p.finished or p.progress >= leg.get("until", 1.0)
        if kind == "hold":
            return self._hold_step()
        if kind == "bow":
            return self._bow_step(leg)
        if kind == "run":
            return self._advance_run(leg, dt)
        if kind in ("jump", "fall"):
            return self._advance_jump(leg, dt)
        return True

    def _turn_toward(self, d: float) -> float:
        """开始转到朝 d（+1 右 / -1 左），不等转完；返回目标朝向。正在转向同一个方向就不重来。"""
        yaw = YAW_RIGHT if d > 0 else YAW_LEFT
        self.facing = d
        spin = self.dog._spin
        target = (spin[0] + spin[1]) % 360.0 if spin is not None else None
        if abs(_wrap(yaw - self.dog.yaw)) >= 2.0 and (target is None or abs(_wrap(target - yaw)) > 1.0):
            self.dog.puppet_face(yaw)
        return yaw

    def _face_dir(self, d: float) -> bool:
        """转到朝 d；返回 True = 已经朝对了。"""
        yaw = self._turn_toward(d)
        return abs(_wrap(yaw - self.dog.yaw)) < 2.0 and not self.dog.puppet_turning

    def _gait(self, dist_px: float) -> tuple[str, float]:
        d = dist_px / self.ppm
        name = temper.gait(d, self.host.tune)                       # 边牧：3 米以上快跑、0.9 以上跑、0.3 以上小跑；活跃度低的门槛高、不冲刺
        if self.carrying and name == "fast":
            name = "run"
        if self.task == "nest" and name in ("fast", "run"):
            name = "trot"                                           # 自己走回窝：不急，最快小跑
        if self.task == "wander":
            name = "walk"                                           # 自己溜达：只走路（两只都不要太活跃）
        return GAIT_CLIPS[name], self.host.pack.gaits[name]

    def _idle(self) -> None:
        self.dog.puppet_play("Idle_1", loop=True, fade=0.25, restart=False)

    def _advance_run(self, leg: dict, dt: float) -> bool:
        to = leg["to"]
        dist = to - self.wx
        if leg["stage"] == "face":
            if abs(dist) < 1.0:
                self.wx = to
                self.moved = True
                return True
            d = 1.0 if dist > 0 else -1.0
            if d * self.facing < 0.0 and abs(dist) <= self.m(BACK_M) and not self.route and not self.dog.puppet_turning:
                clip, natural = BACK_CLIP, self.host.pack.gaits["back"]   # 就在身后一点点：直接倒着走
            else:
                self._turn_toward(d)                                # 边转边跑：不等转完
                clip, natural = self._gait(abs(dist))
            if self.v * d <= 0.0:
                self.v = 0.0                                        # 掉头：从零起步；同一个方向接着跑（改了目标）不减速
            leg.update(stage="go", clip=clip, natural=natural, dir=d)
            self.dog.puppet_play(clip, loop=True, fade=0.18, speed=0.6, restart=self.dog.player.name != clip)
        d = leg["dir"]
        if dist * d <= 0.5:                                         # 到了（或越过了）
            if abs(dist) < self.m(0.6):
                self.wx = to
                self.moved = True
            self.v = 0.0
            if not self.route or self.route[0].kind != "run":
                self._idle()
            return True
        vmax = leg["natural"] * self.ppm
        brake = math.sqrt(max(0.0, 2.0 * ACCEL_M * self.ppm * abs(dist)))
        target = min(vmax, brake)
        speed = abs(self.v)
        if speed < target:
            speed = min(target, speed + ACCEL_M * self.ppm * dt)
        else:
            speed = max(target, speed - 1.6 * ACCEL_M * self.ppm * dt)
        speed = max(speed, min(abs(dist) / max(dt, 1e-3), 0.12 * vmax))   # 别停在离目标一两个像素的地方
        self.v = speed * d
        step = self.v * dt
        if abs(step) > abs(dist):
            step = dist
        self.wx += step
        self.moved = True
        self.dog.puppet_speed(max(0.45, min(1.35, speed / max(1.0, vmax))))
        return False

    # ---------- 跳 ----------
    def _to_screen(self, p: tuple[float, float, float]) -> tuple[float, float]:
        """狗局部的世界点（米）相对根在屏幕上偏多少（像素，y 向下；和 scene_point 一样的正交俯视）。"""
        e = math.radians(ELEVATION)
        return p[0] * self.ppm, -(p[1] * math.cos(e) - p[2] * math.sin(e)) * self.ppm

    def _pelvis_now(self) -> tuple[float, float]:
        """这一帧真实的（融合后的）骨盆相对根在屏幕上偏多少。"""
        dog = self.dog
        if dog._last is None:
            return self._pelvis_pure("Idle_1", 0.0)
        root, g = dog._last
        m = g[dog._pelvis]
        return self._to_screen(transform_point(root, (m[12], m[13], m[14])))

    def _pelvis_pure(self, clip: str, u: float) -> tuple[float, float]:
        """这个片段自己（没融合）在进度 u 时，骨盆相对根在屏幕上偏多少（按狗现在的朝向）。"""
        h, z = self.dog.pelvis_metrics(clip, u)
        return self._to_screen(transform_point(rot_y_mat(90.0 + self.dog.yaw), (0.0, h, z)))

    def _clip_progress(self, clip: str) -> float:
        p = self.dog.player
        return p.progress if p.name == clip else 0.0

    def _advance_jump(self, leg: dict, dt: float) -> bool:
        stage = leg["stage"]
        if stage == "face":
            dx = leg["to"] - self.wx
            d = (1.0 if dx > 0 else -1.0) if abs(dx) > 4.0 else self.facing
            if not self._face_dir(d):
                return False
            self._begin_stance(leg)
            return False
        if stage == "crouch":
            self._peek(leg)
            if self.dog.player.finished or self._edge_reached(leg):
                self._begin_air(leg)
            return False
        if stage == "air":
            leg["t"] += dt
            if leg["kind"] == "fall":
                self._advance_fall(leg, dt)
                return False
            while leg["plan"] and leg["t"] >= leg["plan"][0][0]:
                _, clip, fade = leg["plan"].pop(0)
                self.dog.puppet_play(clip, loop=True, fade=fade)
            if leg["t"] >= leg["T"]:
                self._land(leg)
            return False
        if stage == "land":
            leg["land_t"] += dt
            self._slide(leg, dt)
            if leg["stage"] != "land":                              # 滑出线头，接着掉
                return False
            if leg.get("gentle"):
                return not leg.get("slide")
            if (self.dog.player.finished or self.dog.player.progress >= 0.96) and not leg.get("slide"):
                self.wx, self.wy = leg["lx"], leg["plane"]
                self.moved = True
                if not self.route or self.route[0].kind != "run":
                    self._idle()
                return True
            return False
        return True

    def _begin_stance(self, leg: dict) -> None:
        """朝对了：脚踩着平面开始起跳。站的地方记下来（后脚或前爪的 x），之后每帧按片段反算根（_place_stance）。"""
        s: Support = leg["support"]
        drop = s.y - self.wy
        mode = leg["mode"] or ("up" if drop < 0 else "push" if drop > self.m(UP_MIN_M) else "across")
        clips = JUMPS["hop" if mode == "push" and drop < self.m(DIVE_DROP_M) else mode]
        leg.update(stage="crouch", jump=mode, clips=clips, speed=clips.speed, plane=self.wy)
        _, hz, _, fz = self.dog.foot_metrics(clips.start, 0.0)
        d = self.facing
        leg["front_x"] = self.wx + d * fz * self.ppm if mode == "edge" else None
        leg["foot_x"] = None if mode == "edge" else self.wx + d * hz * self.ppm
        leg["peek"] = "go" if drop > self.m(BIG_DROP_DOG * self.height_m) else None
        self.dog.puppet_play(clips.start, loop=False, fade=0.12, speed=0.8 if leg["peek"] else clips.speed)

    def _peek(self, leg: dict) -> None:
        """大落差：压低身子停一下，往下看一眼再跳（片段停在 PEEK_AT 一会儿）。"""
        peek = leg.get("peek")
        if peek == "go" and self._clip_progress(leg["clips"].start) >= PEEK_AT:
            leg["peek"] = self.t + PEEK_HOLD
            self.dog.puppet_speed(0.0)
            if leg["jump"] != "edge":
                self.dog.head_pitch_target = PEEK_PITCH
        elif isinstance(peek, float) and self.t >= peek:
            leg["peek"] = None
            self.dog.puppet_speed(leg["speed"])
            self.dog.head_pitch_target = 0.0

    def _place_stance(self, leg: dict) -> None:
        """脚踩着：后脚的高度一直在平面上，根按片段里后脚抬多高、往前多少反算（往前蹬时身子就往前送出去）。
        直接落：前半段前爪站在边上、后脚并过来（按前爪反算），后半段后脚锁住、身子往下探（按后脚反算）。"""
        clips = leg["clips"]
        u = self._clip_progress(clips.start)
        hh, hz, _, fz = self.dog.foot_metrics(clips.start, u)
        d = self.facing
        if leg["foot_x"] is None and u >= EDGE_SWITCH:
            _, hs, _, fs = self.dog.foot_metrics(clips.start, EDGE_SWITCH)
            leg["foot_x"] = leg["front_x"] - d * fs * self.ppm + d * hs * self.ppm
        if leg["foot_x"] is None:
            self.wx = leg["front_x"] - d * fz * self.ppm
        else:
            self.wx = leg["foot_x"] - d * hz * self.ppm
        self.wy = leg["plane"] + (hh - self.dog.planted_hind) * math.cos(math.radians(ELEVATION)) * self.ppm
        self.moved = True

    def _edge_reached(self, leg: dict) -> bool:
        """直接落、落差小：探到一半骨盆就到落地片段第一帧那么低了，不用探到底。"""
        clips = leg["clips"]
        if leg["jump"] != "edge" or leg.get("peek") or leg["foot_x"] is None:
            return False
        _, ly = self._pelvis_pure(clips.land, 0.0)
        _, oy = self._pelvis_pure(clips.start, self._clip_progress(clips.start))
        return self.wy + oy >= leg["support"].y + ly

    def _begin_air(self, leg: dict) -> None:
        """脚离开平面：算空中这一段（骨盆的抛物线，从这一刻骨盆在哪，到落地片段第一帧骨盆该在哪），换空中姿势。"""
        s: Support = leg["support"]
        g = GRAVITY_M * self.ppm
        mode, clips = leg["jump"], leg["clips"]
        ox, oy = self._pelvis_now()
        px0, py0 = self.wx + ox, self.wy + oy
        lx, ly = self._pelvis_pure(clips.land, 0.0)
        px1, py1 = leg["to"] + lx, s.y + ly
        plan: list[tuple[float, str, float]] = []
        if mode == "edge":
            self.leap_spec()
            py1 = min(py1, s.y - self.m(self._edge_touch))          # 头朝下：前爪一碰到线就算落地，不等骨盆那么低（前爪会钻到线下面）
            v0 = self._edge_speed(self._clip_progress(clips.start)) * self.ppm
            if py1 <= py0:                                          # 已经够低了：直接落地
                self._land(leg)
                return
            T = (-v0 + math.sqrt(v0 * v0 + 2.0 * g * (py1 - py0))) / g
        elif mode == "up":
            clear = self.m(UP_CLEAR_M)
            vup = math.sqrt(max(0.0, 2.0 * g * (py0 - (py1 - clear))))
            T = vup / g + math.sqrt(2.0 * clear / g)
            plan = [(vup / g - 0.12, "JumpAir_Up_F", 0.18)]
        elif mode == "across":
            apex = min(py0, py1) - self.m(0.35)
            T = math.sqrt(2.0 * (py0 - apex) / g) + math.sqrt(2.0 * (py1 - apex) / g)
        else:
            vup = self.leap_spec().push_vup * self.ppm
            if vup * vup + 2.0 * g * (py1 - py0) < 0.0:             # 目标比蹬出去够得着的还高一点（小台阶）
                vup = math.sqrt(2.0 * g * (py0 - py1)) + 1.0
            T = (vup + math.sqrt(vup * vup + 2.0 * g * (py1 - py0))) / g
            plan = [(vup / g + 0.05, "JumpAir_low_F", 0.25)]
        T = max(T, 0.12, abs(px1 - px0) / self.m(6.5))              # 横着太远就飞得久一点（不超过 6.5 米 / 秒）
        vup = (py0 - py1 + 0.5 * g * T * T) / T                     # 按定下的 T 算往上的速度，保证正好到 py1（负的就是往下）
        leg.update(stage="air", t=0.0, T=T, px0=px0, py0=py0, vx=(px1 - px0) / T, vup=vup, plan=plan)
        self.support, self.ride_left = None, None
        self.dog.head_pitch_target = 0.0
        self.dog.puppet_play(clips.air, loop=True, fade=clips.air_fade)

    def _place_air(self, leg: dict) -> None:
        """空中：骨盆走抛物线，根 = 骨盆 - 这一帧姿势里骨盆相对根的偏移（换片段、融合都不影响身子走的路线）。"""
        ox, oy = self._pelvis_now()
        if leg["kind"] == "fall":
            if leg.get("py") is None:
                leg["px"], leg["py"] = self.wx + ox, self.wy + oy
            self.wx, self.wy = leg["px"] - ox, leg["py"] - oy
        else:
            g = GRAVITY_M * self.ppm
            t = min(leg["t"], leg["T"])
            self.wx = leg["px0"] + leg["vx"] * t - ox
            self.wy = leg["py0"] - leg["vup"] * t + 0.5 * g * t * t - oy
        self.moved = True

    def _land(self, leg: dict) -> None:
        """落到线上：骨盆接着落地片段走（_place_land），融完根正好在 (to, 线)。"""
        s: Support = leg["support"]
        clips = leg["clips"]
        lx = leg["to"]
        if s.kind == "window":
            fresh = self.host.window_top(s.key, at_x=lx) if self.host.window_listed(s.key) else None
            if fresh is None or not fresh.covers(lx, 0.0):          # 落地那一刻窗口没了 / 挪开了：接着往下掉
                self.host.frames_stale()
                self._start_fall(leg)
                return
            s = fresh
            self.ride_left = self.host.window_left(s.key)
        else:
            s = self._fresh_floor(s)                                # 跳的时候调过大小：地面按现在的算
            self.ride_left = None
        ox, oy = self._pelvis_now()
        dx, dy = self._pelvis_pure(clips.land, 0.0)
        leg.update(stage="land", lx=lx, plane=s.y, land_t=0.0, err=(self.wx + ox - (lx + dx), self.wy + oy - (s.y + dy)))
        self.support = s
        self.dog.head_pitch_target = 0.0
        self.dog.puppet_play(clips.land, loop=False, fade=clips.land_fade)

    def _place_land(self, leg: dict) -> None:
        if leg.get("gentle"):
            self.wx, self.wy = leg["lx"], leg["plane"]
            self.moved = True
            return
        clips = leg["clips"]
        dx, dy = self._pelvis_pure(clips.land, self._clip_progress(clips.land))
        k = max(0.0, 1.0 - leg["land_t"] / LAND_ERR_SECONDS)
        ox, oy = self._pelvis_now()
        self.wx = leg["lx"] + dx + leg["err"][0] * k * k - ox
        self.wy = leg["plane"] + dy + leg["err"][1] * k * k - oy
        dog = self.dog
        if dog._last is not None:                                   # 脚不钻到线下面：融合的时候哪只脚先碰到线，身子就先被它撑住
            g = dog._last[1]
            low = min(g[i][13] for i in dog._hind_feet + dog._front_feet)
            self.wy = min(self.wy, leg["plane"] + (low - dog.planted_hind) * math.cos(math.radians(ELEVATION)) * self.ppm)
        self.moved = True

    # ---------- 掉下去、飞出去 ----------
    def _fall_leg(self, vx: float = 0.0, vy: float = 0.0) -> dict:
        leg = {"kind": "fall"}
        self._start_fall(leg, vx, vy)
        return leg

    def _fall_height_m(self) -> float:
        """现在脚下面第一条线离脚多远（米）。"""
        sups = self.host.supports()
        below = support_below(sups, self.wx, self.wy - 1.0) or self.host.world.nearest_floor(self.wx, self.wy)
        return max(0.0, below.y - self.wy) / self.ppm

    def _land_clips(self, height_m: float) -> JumpClips:
        """掉了这么高用哪种落地：高的（调参 land_mid_m 以上）前爪先着地（JumpLand），不高的脚先着地（JumpLand_Place）。"""
        return JUMPS["fall"] if height_m > self.host.tune["land_mid_m"] else JUMPS["drop"]

    def _start_fall(self, leg: dict, vx: float = 0.0, vy: float = 0.0) -> None:
        """开始掉：不高的连空中姿势都不换（脚回到线上就行），高的换空中姿势；扔出去的先身子平着飞，过了最高点再按实际掉多高挑空中和落地的片段（_advance_fall）。"""
        ox, oy = self._pelvis_now()
        thrown = abs(vx) >= THROW_MIN_PX or vy < -THROW_MIN_PX
        height = self._fall_height_m()
        gentle = not thrown and height <= self.host.tune["land_light_m"]
        clips = JUMPS["drop"] if thrown else self._land_clips(height)
        leg.update(kind="fall", stage="air", t=0.0, vx=vx, vy=vy, clips=clips, px=self.wx + ox, py=self.wy + oy, jump="fall",
                   gentle=gentle, top=self.wy, under=None)
        self.support, self.ride_left = None, None
        self.dog.hide_shadow = True
        if not gentle:
            self.dog.puppet_play(clips.air, loop=True, fade=clips.air_fade)

    def _bounce(self) -> float:
        return self.host.tune["hit_bounce"]

    def _hit(self, speed: float) -> None:
        self.host.dog_landed(speed / self.ppm)

    def _room_ahead(self, x: float, d: float, dist: float, y: float) -> float:
        """身子从 x 往 d 方向走 dist（像素）：前沿走出所有屏幕之前能走多远。一小步一小步试：卡一下 dt 就大，一步能跨好几百像素，
        只看终点会离墙老远就当撞上了，看着像在半空撞了堵墙（录到的）。"""
        world = self.host.world
        half = self.m(BODY_HALF_M)
        done = 0.0
        while done < dist:
            ahead = min(dist, done + ROOM_STEP_PX)
            if not world.dog_open(x + d * (half + ahead), y):
                lo, hi = done, ahead
                for _ in range(5):
                    mid = (lo + hi) / 2.0
                    if world.dog_open(x + d * (half + mid), y):
                        lo = mid
                    else:
                        hi = mid
                return lo
            done = ahead
        return dist

    def _fly_x(self, leg: dict, dt: float) -> None:
        """横着飞：屏幕边（外面没有屏）、窗口的左右边挡住，飞到碰上才停，几乎不弹。本来就和窗口重叠（在它前面）的，等于从窗口前面过，不挡。"""
        vx = leg["vx"]
        if abs(vx) < 1e-3:
            return
        half = self.m(BODY_HALF_M)
        d = 1.0 if vx > 0.0 else -1.0
        step = abs(vx * dt)
        y = self.wy - self.m(0.4)
        room = self._room_ahead(self.wx, d, step, y)
        for e in self.host.ball_edges():
            if e.side not in ("left", "right") or not e.lo <= y <= e.hi:
                continue
            if e.side == "left" and vx > 0.0 and self.wx + half <= e.at + 0.5:
                room = min(room, max(0.0, e.at - (self.wx + half)))
            elif e.side == "right" and vx < 0.0 and self.wx - half >= e.at - 0.5:
                room = min(room, max(0.0, self.wx - half - e.at))
        if room < step:
            leg["px"] += d * room
            self._hit(abs(vx))
            leg["vx"] = -vx * self._bounce()
            return
        leg["px"] += d * step

    def _fly_y(self, leg: dict) -> None:
        """往上飞：头顶到屏幕最上沿（往上没有屏）、窗口的下边就回来。"""
        if leg["vy"] >= 0.0:
            return
        top = self.wy - self.m(self.height_m)
        world = self.host.world
        hit = not world.dog_open(self.wx, top)
        if not hit:
            for e in self.host.ball_edges():
                if e.side == "bottom" and e.lo <= self.wx <= e.hi and top <= e.at <= top + self.m(0.15):
                    hit = True
                    break
        if hit:
            self._hit(abs(leg["vy"]))
            leg["vy"] = -leg["vy"] * self._bounce()

    def _support_to_land_on(self, sups, py: float, top: float) -> Optional[Support]:
        """要播落地的下落落在哪条线上：正下方、骨盆（py）还没低过「在它上面落地」那一刻该在的高度（落地片段第一帧）的，最高的那条。
        按骨盆找、不按根：过了最高点空中的姿势会换（平着 ↔ 往下探，骨盆离根差约 0.13 米），根跟着挪一截，按根找会把擦边飞到的窗口当成在脚上面。"""
        best = None
        for s in sups:
            if s.covers(self.wx) and (best is None or s.y < best.y):
                land = self._land_clips(max(0.0, s.y - top) / self.ppm).land
                if py < s.y + self._pelvis_pure(land, 0.0)[1] + 1.0:
                    best = s
        return best

    def _advance_fall(self, leg: dict, dt: float) -> None:
        clips = leg["clips"]
        before, pelvis_before = self.wy, leg["py"]
        leg["top"] = min(leg["top"], before)
        self._fly_x(leg, dt)
        self._fly_y(leg)
        leg["vy"] = min(leg["vy"] + GRAVITY_M * self.ppm * dt, self.m(30.0))
        leg["py"] += leg["vy"] * dt
        if leg["vy"] <= 0.0:                                        # 还在往上：不落地
            return
        sups = self.host.supports()
        below = support_below(sups, self.wx, before - 1.0) if leg["gentle"] else self._support_to_land_on(sups, pelvis_before, leg["top"])
        under = leg.get("under")                                    # 脚刚越过那条线、骨盆还没到落地的高度：还算落在它上面，不穿过去
        if under is not None and under in sups and under.covers(self.wx) and (below is None or under.y < below.y):
            below = under
        if below is None:                                           # 底下什么都没有（屏幕外）：落到最近的地面
            below = self.host.world.nearest_floor(self.wx, before)
            leg["px"] += below.clamp(self.wx, self.margin(below)) - self.wx
        leg["under"] = below
        height = max(0.0, below.y - leg["top"]) / self.ppm          # 真掉多高：飞到的最高点到下面那条线（不看松手在哪）
        if not leg["gentle"]:
            if height <= self.host.tune["land_light_m"] and abs(leg["vx"]) < self.m(LAND_FAST_M):
                leg["gentle"] = True                                # 扔得不高又不快：不播落地
            else:
                want = self._land_clips(height)
                if want.air != clips.air:                           # 空中的姿势跟着真掉的高度换：高的往下探（前爪先着地看得出来），不高的平着
                    self.dog.puppet_play(want.air, loop=True, fade=AIR_SWAP_FADE)
                clips = leg["clips"] = JumpClips(clips.start, clips.speed, want.air, want.air_fade, want.land, want.land_fade)
        if leg["gentle"]:
            if self.wy + leg["vy"] * dt >= below.y:
                if below.kind == "window" and not self._window_still_there(below):
                    return                                          # 窗口表过时了（飞的时候不问系统）：下一帧按新的算
                self._begin_slide(leg)
                self._touch_down(leg, below)
            return
        lx, ly = self._pelvis_pure(clips.land, 0.0)
        if leg["py"] >= below.y + ly:                               # 骨盆到了落地片段第一帧的高度
            leg["support"], leg["to"] = below, leg["px"] - lx
            self._landed_sound(leg)
            self._begin_slide(leg)
            self._land(leg)

    def _window_still_there(self, s: Support) -> bool:
        """要落到这个窗口上了：它还在这吗（只问这一个）。不在了让窗口表下次重新问。"""
        fresh = self.host.window_top(s.key, at_x=self.wx) if self.host.window_listed(s.key) else None
        if fresh is not None and fresh.covers(self.wx, 0.0):
            return True
        self.host.frames_stale()
        return False

    def _begin_slide(self, leg: dict) -> None:
        """落地时横着还有速度：顺着滑一段，不当场停住（贴地甩出去，惯性一下就没了，像撞墙）。"""
        v, cap = leg["vx"], self.m(SLIDE_MAX_M)
        leg["slide"] = max(-cap, min(cap, v)) * self.host.tune.get("land_slide", 1.0) if abs(v) >= self.m(SLIDE_MIN_M) else 0.0

    def _slide(self, leg: dict, dt: float) -> None:
        """落地这段里每帧：落点跟着滑（_place_land 按它摆根），越滑越慢；碰到屏幕边就停；滑出这条线的头：下面还有线就接着掉，没有（前面的地面更高）就停在头上。"""
        v = leg.get("slide", 0.0)
        if not v:
            return
        v *= math.exp(-dt / SLIDE_TAU)
        if abs(v) < self.m(SLIDE_STOP_M):
            leg["slide"] = 0.0
            return
        leg["slide"] = v
        d = 1.0 if v > 0.0 else -1.0
        step = abs(v * dt)
        room = self._room_ahead(leg["lx"], d, step, leg["plane"] - self.m(0.4))
        x = leg["lx"] + d * room
        if room < step:
            leg["slide"] = 0.0
        s = self.support
        if s is not None and not s.covers(x):
            if support_below(self.host.supports(), x, leg["plane"] - 1.0) is not None:
                leg["lx"] = x
                self._start_fall(leg, v, 0.0)
                return
            x, leg["slide"] = s.clamp(x), 0.0
        leg["lx"] = x

    def _landed_sound(self, leg: dict) -> None:
        self.dog.hide_shadow = False
        self.host.dog_landed(leg["vy"] / self.ppm)

    def _touch_down(self, leg: dict, below: Support) -> None:
        """掉得不高：脚回到线上，轻轻 duang 一下，不播落地片段（只拖了一点点，动作却像从很高掉下来）。"""
        x = below.clamp(self.wx, 0.0)
        if below.kind == "window":
            self.ride_left = self.host.window_left(below.key)
        else:
            self.ride_left = None
        self.support = below
        self.wx, self.wy = x, below.y
        self.moved = True
        self._landed_sound(leg)
        self.dog.expr.kick(0.05)
        self.dog.puppet_play("Idle_1", loop=True, fade=0.15, restart=self.dog.player.name != "Idle_1")
        leg.update(stage="land", lx=x, plane=below.y, land_t=0.0, err=(0.0, 0.0), gentle=True)

    # ---------- 捡球 ----------
    def _pick_offset(self, d: float) -> float:
        """狗朝 d 时，低头叼球那一刻鼻子在根的前面多远（像素，带方向）。"""
        return self._spot_offset("Pick_up", d)

    def _spot_offset(self, clip: str, d: float) -> float:
        x, z, _ = self.dog.props.spot(clip)
        wx, _, _ = transform_point(rot_y_mat(90.0 + (YAW_RIGHT if d > 0 else YAW_LEFT)), (x, 0.0, z))
        return wx * self.ppm

    def _fetch_step(self) -> None:
        """捡球走到哪一步了：没在走的时候调，按 phase 排下一段。"""
        b = self.host.ball
        if b is None:
            self.finish()
            return
        ph = self.phase
        held = self.host.ball_held
        if ph == "done":
            self._stay_here()
            return
        if ph in ("look", "watch"):
            if held:                                                # 球在你手上：站着看它，圈满了叫一声、俯身
                self._wait_for_throw()
                return
            if ph == "watch":                                       # 球离手了却没人叫去追、也没叫算了（不该发生）：就待在这
                self._stay_here()
                return
            self.phase = "plan"
            ph = "plan"
        if ph == "plan":
            self._plan_pickup(b)
            return
        if ph in ("chase", "standby"):
            if held or self.planned != self.host.throw_id:          # 又被拿起来 / 又扔了：重新看、重新算
                self.phase = "look"
                return
            if ph == "chase":                                       # 追着球：这一段跑完了（或站着看了一小会儿），再看球到哪了
                self._chase_step(b)
            else:                                                   # 等球落到那一层 / 等它停：再看一次现在能不能过去
                self._plan_pickup(b)
            return
        if ph in ("approach", "wait_ball"):
            if held or self.planned != self.host.throw_id:          # 又被拿起来 / 又扔了：重新看、重新算
                self.phase = "look"
                return
            if not b.resting:
                self.phase = "wait_ball"                            # 到了球还在滚：看着它等
                self._watch(0.1)
                self.wait_ball += 0.1
                if self.wait_ball > 6.0:
                    self.wait_ball = 0.0
                    self.phase = "plan"
                return
            self.wait_ball = 0.0
            d = 1.0 if b.x > self.wx else -1.0
            aligned = abs((b.x - self._pick_offset(d)) - self.wx) <= self.m(0.3)
            level = self.support is not None and abs(self.support.y - (b.y + b.r)) <= self.m(0.15)
            if not (aligned and level):
                self.replans += 1
                if self.replans < MAX_REPLANS:
                    self.phase = "plan"
                else:
                    self._go_bark(b)
                return
            self.phase = "face_ball"
            self.leg = {"kind": "face", "yaw": YAW_RIGHT if d > 0 else YAW_LEFT}
            return
        if ph == "face_ball":
            if held or not b.resting:
                self.phase = "look"
                return
            if "Pick_up" not in self.dog.model.clips:               # 这个模型没有叼东西的动作：跑到球旁边就算了
                self._stay_here()
                return
            self._pickup(b)
            return
        if ph == "pickup":
            if not self.carrying:                                   # 叼之前球被拿走了
                self.dog.props.cut()
                self.phase = "look"
                return
            self.phase = "deliver"
            ph = "deliver"
        if ph == "deliver":
            if self._out_of_patience():
                self._put_here()
                return
            s, gx, d = self._delivery_target()
            self._target, self._put_dir = (s, gx), d
            self._retarget_at = self.t + RETARGET_EVERY
            self.route = list(self._route(self.here(), self.wx, s, gx, self.margin(s)).legs)
            self.phase = "carry"
            return
        if ph == "carry":                                           # 走到鼠标旁边了：叼着等鼠标停稳
            if self._arrived_at is None:
                self._arrived_at = self.t
            self.phase = "hold"
            self.dog.puppet_play("Pick_up_idle", loop=True, fade=0.25, restart=False)
            self.leg = {"kind": "hold"}
            return
        if ph == "hold_done":
            self.phase = "turn_put"
            self.leg = {"kind": "face", "yaw": YAW_RIGHT if self._put_dir > 0 else YAW_LEFT}
            return
        if ph == "turn_put":
            self.phase = "putdown"
            self.dog.puppet_play("Put_down", loop=False, fade=FADE_CLIP)
            self.leg = {"kind": "clip", "clip": "Put_down", "hook": self._watch_putdown}
            return
        if ph in ("putdown", "barked"):
            if ph == "barked":
                self._cue("stumped")                                # 够不着，叫完了
            self._stay_here()
            return
        if ph in ("bark_go", "bark"):
            kind, key = b.on if b.on is not None else ("floor", 0)   # 这时候球已经落定了：冲它现在在的地方叫
            self._bark_at = (kind, key, b.x)
            self._bark_step()
            return
        self.finish()

    def _wait_for_throw(self) -> None:
        """球在你手上：圈还没满就站着看它（watch，球到了另一边一小会儿才转身；圈一满这一小段就不等完）；
        满了（host.fetch_ready）先按调参 ready_bark 的概率叫一声，再前肢俯下来等你扔。只看「满没满」这一个状态，不等「刚满」那一下：
        圈在狗起身、叫的时候满了也一样走到这，叫不叫只定一次（_ready_seen，拿起球时清掉）。"""
        if self.host.fetch_ready:
            if not self._ready_seen:
                self._ready_seen = True
                if self.dog.rng.random() < self.host.tune.get("ready_bark", 1.0):
                    self._bark_once()
                    return
            self._begin_bow()
            return
        self.phase = "watch"
        self._watch(0.1, until_ready=True)

    def _bark_once(self) -> None:
        """圈满那一下叫一声：Bark 片段只放第一声（BARK_FROM 到 BARK_ONE_UNTIL；声音在 pack.json 里按嘴张开的时刻放，嘴和声音对上），
        先转向球。俯身的样子是闭着嘴的，所以叫在俯身前面。叫完 _fetch_step 接着俯身；这时松手（fetch）不等叫完就冲出去。"""
        b = self.host.ball
        if b is not None and abs(b.x - self.wx) > 1.0:
            self._turn_toward(1.0 if b.x > self.wx else -1.0)
        self.dog.puppet_play("Bark", loop=False, fade=0.12, at=BARK_FROM)
        self.leg = {"kind": "clip", "clip": "Bark", "until": BARK_ONE_UNTIL, "ready_bark": True}

    def _begin_bow(self) -> None:
        """圈满了、球在你手上：前肢俯下来（Idle_5_start 定在调参 bow_depth 那一帧，闭嘴），侧身对着球。"""
        b = self.host.ball
        self.phase = "bow"
        if b is not None and abs(b.x - self.wx) > 1.0:
            self._turn_toward(1.0 if b.x > self.wx else -1.0)
        self.dog.shut_mouth = True
        self.dog.puppet_play("Idle_5_start", loop=False, fade=0.18, speed=BOW_SPEED)
        self.leg = {"kind": "bow"}

    def _end_bow(self) -> None:
        self.dog.shut_mouth = False

    def _bow_step(self, leg: dict) -> bool:
        """俯身等着：球到了另一边够远就转过去；到了 bow_depth 就定住，一直等到你扔。
        球不在手上了、或者不算准备好了（return True）就起来，接着按 phase 走：俯身只跟着「球在手上、圈满过」这一个状态。
        你松手了、它还愣着（leg 里记了 go_at，fetch 记的）：到点才起身去追。"""
        host, dog = self.host, self.dog
        go_at = leg.get("go_at")
        if go_at is not None:
            if self.t < go_at:
                return False
            self._end_bow()
            self.phase = "look"
            return True
        b = host.ball
        if b is None or not host.ball_held or not host.fetch_ready:
            self._end_bow()
            self.phase = "look"
            return True
        if abs(b.x - self.wx) > self.m(SIDE_SWITCH_M):
            self._turn_toward(1.0 if b.x > self.wx else -1.0)
        p = dog.player
        if p.name == "Idle_5_start" and p.progress >= host.tune["bow_depth"]:
            dog.puppet_speed(0.0)
        return False

    def _stay_here(self) -> None:
        """这事做完了，就待在这：家改到这。"""
        self.settle_support()
        self.remember_home()
        self.finish()

    def _bark_step(self) -> None:
        """够不着：走到了离它最近的地方（路线走完才调），朝它叫两声。"""
        if self.phase == "bark_go":
            self.phase = "bark"
            self.leg = {"kind": "face", "yaw": YAW_RIGHT if self._bark_at[2] > self.wx else YAW_LEFT}
        elif self.phase == "bark":
            self.phase = "barked"
            self.dog.puppet_play("Bark", loop=False, fade=0.12, at=BARK_FROM)
            self.leg = {"kind": "clip", "clip": "Bark", "until": BARK_UNTIL}
            self.host.barking(*self._bark_at)
        else:
            self._cue("stumped")
            self._stay_here()

    def _delivery_target(self) -> tuple[Support, float, float]:
        """叼着球要去哪：(鼠标正下方那条线, 站在哪, 放球时朝哪边)。球落在鼠标旁边、狗这一侧，朝着鼠标放，点击范围碰不到鼠标
        （球盖住鼠标就没法工作了）；这一侧放不下（贴着屏幕边、台子到头了）就换另一侧。"""
        cx, cy = self.host.cursor()
        sups = self.host.supports()
        s = support_below(sups, cx, cy) or self.host.world.nearest_floor(cx, cy)
        r = BALL_R * self.ppm
        gap = r + HIT_PAD + CURSOR_MARGIN_PX + self.m(self._short)   # 聪明程度低的放得远一点（只往狗这一侧让，离鼠标只会更远；边牧 + 0）
        if self._deliver_side is None:
            self._deliver_side = -1.0 if self.wx < cx else 1.0
        elif cx > self.wx + self.m(SIDE_SWITCH_M):                  # 鼠标越过狗够远才换边：小幅来回不转身，倒着走
            self._deliver_side = -1.0
        elif cx < self.wx - self.m(SIDE_SWITCH_M):
            self._deliver_side = 1.0
        mine = self._deliver_side
        margin = self.margin(s)
        for side in (mine, -mine):
            bx = cx + side * (gap + (ARROW_W_PX if side > 0 else 0.0))
            d = -side
            gx = bx - self._spot_offset("Put_down", d)
            if s.covers(gx, margin) and s.covers(bx, r):
                return s, gx, d
        d = 1.0 if cx >= self.wx else -1.0
        return s, s.clamp(cx - d * gap - self._spot_offset("Put_down", d), margin), d

    def _maybe_retarget(self) -> None:
        """叼着球往你那走：每 RETARGET_EVERY 秒看一次鼠标，挪远了就改路线（正在跳的等落地）。"""
        if not self.carrying or self.airborne or self.t < self._retarget_at:
            return
        self._retarget_at = self.t + RETARGET_EVERY
        s, gx, d = self._delivery_target()
        old = self._target
        if old is not None and old[0] == s and abs(old[1] - gx) <= self.m(RETARGET_M):
            return
        if self.leg is not None and self.leg.get("kind") != "run":
            return
        self._target, self._put_dir = (s, gx), d
        self.route = list(self._route(self.here(), self.wx, s, gx, self.margin(s)).legs)
        self.leg = None

    def _maybe_daze(self) -> None:
        """叼回来的路上愣一下（聪明程度低的；这一趟愣不愣叼到那一刻就定了，temper.daze）：跑出 DAZE_AFTER_M 以后站住，叼着球愣一会儿，
        再重新看鼠标在哪接着走（_fetch_step 的 deliver）。一趟最多一次，路不够长就不愣。"""
        leg = self.leg
        if leg is None or leg.get("kind") != "run" or leg.get("stage") != "go" or abs(self.wx - self._carry_from) < self.m(DAZE_AFTER_M):
            return
        seconds, self._daze = self._daze, None
        self._stop_leg()
        self.route = []
        self.dog.puppet_play("Pick_up_idle", loop=True, fade=0.2)
        self.leg = {"kind": "wait", "until": self.t + seconds}
        self.phase = "deliver"
        self._cue("daze")

    def _out_of_patience(self) -> bool:
        """鼠标一直在动（你在干别的）：跟了几秒就放下，不没完没了地追。"""
        if self.t - self._picked_at >= CARRY_PATIENCE:
            return True
        return self._arrived_at is not None and self.t - self._arrived_at >= PUT_PATIENCE

    def _put_here(self) -> None:
        """就地放下：跑着的停下，跳到一半的等落地。"""
        if self.leg is not None and self.leg.get("kind") in ("jump", "fall"):
            self.route = []
            return
        self.route = []
        self._stop_leg()
        self._put_dir = self.facing
        self.phase = "hold_done"

    def _hold_step(self) -> bool:
        """到了鼠标旁边：不等鼠标停稳，直接放（鼠标小幅度动着时它跟很久不放，不跟手）；鼠标真走远了才跟过去，跟够了也放。"""
        self._turn_toward(self._put_dir)
        if self._out_of_patience():
            self._put_dir = self.facing
            self.phase = "hold_done"
            return True
        s, gx, d = self._delivery_target()
        old = self._target
        if old is None or old[0] != s or abs(gx - self.wx) > self.m(HOLD_MOVE_M):
            self.phase = "deliver"
            return True
        self._put_dir = d
        self.phase = "hold_done"
        return True

    def _see(self) -> int:
        """球还要掉头（撞墙、撞窗口侧边弹回来）几次以内，狗看得出它最后停哪（调参「能看穿几次反弹」，默认 0）。"""
        return int(round(self.host.tune.get("see_bounces", 0.0)))

    def _watch(self, seconds: float, until_ready: bool = False) -> None:
        """站着看球等一小会儿。球到了身后那边（超过 SIDE_SWITCH_M）、又持续了一小会儿才转过去：头一直看着球，身子不跟着来回弹的球抖。
        until_ready：看的是你手里的球，圈一满这一小段就不等完（这一帧就叫、俯身）。"""
        b = self.host.ball
        off = b.x - self.wx if b is not None else 0.0
        if off * self.facing < 0.0 and abs(off) > self.m(SIDE_SWITCH_M):
            if self._watch_since is None:
                self._watch_since = self.t
            if self.t - self._watch_since >= temper.watch_turn(self.host.tune) and not self.dog.puppet_turning:
                self._turn_toward(1.0 if off > 0.0 else -1.0)
                self._watch_since = None
        else:
            self._watch_since = None
        self.v = 0.0
        self._idle()
        self.leg = {"kind": "wait", "until": self.t + seconds}
        if until_ready:
            self.leg["until_ready"] = True

    def _chase_point(self, s: Support) -> float:
        """追球本身时往哪跑：球再过 CHASE_LEAD 秒（聪明程度低的瞄得近，temper.chase_lead）在哪，夹在脚下这条线上。"""
        ahead = self.host.ball_ahead(temper.chase_lead(self.host.tune))
        return s.clamp(ahead[0], self.margin(s)) if ahead is not None else self.wx

    def _chase_step(self, b: Ball) -> None:
        """球还要撞墙、撞窗口弹回来，看不出最后停哪：在脚下这一层朝球前面一点跑；到跟前了、或者那一点就在身后一点点，站着看。"""
        here = self.here()
        gx = self._chase_point(here)
        off = gx - self.wx
        if abs(off) <= self.m(CHASE_NEAR_M) or (off * self.facing < 0.0 and abs(off) <= self.m(BACK_M)):
            self._watch(0.1)                                        # 身后 BACK_M 以内起跑会变成倒着走（_advance_run）：追球不倒着走
            return
        self.leg = {"kind": "run", "to": gx, "support": here, "stage": "face"}

    def _chase_update(self) -> None:
        """追着球的每一帧：看得出它停哪了（后面不再掉头 / 已经停了）就改去落点；不然目标跟着球前面那一点挪。"""
        b = self.host.ball
        if b is None or self.host.ball_held or self.planned != self.host.throw_id:
            return                                                  # 被拿起来 / 又扔了：ball_grabbed、fetch 管
        leg = self.leg
        running = leg is not None and leg.get("kind") == "run"
        if leg is not None and not running and leg.get("kind") != "wait":
            return
        if b.resting or (temper.reads_landing(self.host.tune) and self.host.ball_turns_left() <= self._see()):   # 看不出落点的只等球停
            self.phase = "plan"
            self.leg = None                                         # 不清速度：落点在同一边就接着跑，不顿一下
            return
        if not running:
            return
        s = leg["support"]
        gx = self._chase_point(s)
        if leg["stage"] != "go":
            leg["to"] = gx
            return
        d = leg["dir"]
        ahead = (gx - self.wx) * d
        if ahead > 0.0:
            leg["to"] = gx
            leg.pop("braking", None)
            if leg["clip"] != BACK_CLIP:
                clip, natural = self._gait(ahead)
                if natural > leg["natural"]:                        # 球跑远了：换快一档的步子（只升不降，不来回换）
                    leg.update(clip=clip, natural=natural)
                    self.dog.puppet_play(clip, loop=True, fade=0.18, speed=0.6, restart=False)
        elif not leg.get("braking"):                                # 那一点到身后去了：先刹住（不急停、不掉头就跑）；停稳了 _chase_step 再看
            leg["braking"] = True                                   # 刹车点只算一次：每帧按当前速度重算的话永远刹不下来
            stop = self.v * self.v / (2.0 * ACCEL_M * self.ppm)
            beat = temper.fooled(self.host.tune)
            if beat > 0.0 and b.vx * d < -FOOLED_MIN_M * self.ppm:  # 被晃到（聪明程度低的；边牧 0，不走这里）：球是掉了头朝身后去的（不是追上了
                stop += abs(self.v) * beat                          # 同一个方向滚着的球）——还照原样往前冲这么久才反应过来刹车
                self._cue("fooled")
            leg["to"] = s.clamp(self.wx + d * stop, self.margin(s))

    def _hold_off(self, route: Optional[Route]) -> None:
        """还不能过去（球还没落到那一层 / 够不着但球还没停）：先走脚下这一层能走的那段，到了站着看球等。"""
        runs = []
        for leg in (route.legs if route is not None else []):
            if leg.kind != "run":
                break
            runs.append(leg)
        self.phase = "standby"
        if runs and abs(runs[-1].x - self.wx) > 2.0:
            self.route = runs
        else:
            self._watch(0.1)

    def _plan_pickup(self, b: Ball) -> None:
        """排去叼球的路线。球还在飞：看得出它停哪（这一路不再撞墙、撞窗口侧边弹回来，或者调参 see_bounces 够看穿）就按算出来的落点排，
        看不出就先追球本身（_chase_step）。要跳的等球真落到那一层再跳，够不着的等球停了再叫（_hold_off）。
        聪明程度低的（temper.reads_landing 是假的）球在飞就一律追球本身：追球只在脚下这一层跑，球停了才走到这里排路线、才跳、才叫。"""
        rest = self.host.predict_rest()
        if rest is None:
            self.phase = "look"
            return
        self.planned = self.host.throw_id
        flying = not b.resting
        left = self.host.ball_turns_left() if flying else 0
        self._plan_turns = self.host.ball_turns + min(left, self._see())   # 料到的掉头不算意外
        if flying and not temper.reads_landing(self.host.tune):     # 聪明程度低：看不出球停哪，不管它还掉不掉头都追球本身，球停了再来排路线
            self._plan_turns = self.host.ball_turns                 # 得是现在的掉头数：不然 update 里「球又掉了个没料到的头」每帧重排
            self.phase = "chase"
            self._chase_step(b)
            return
        if left > self._see():
            self.phase = "chase"
            self._chase_step(b)
            return
        bx, by = rest
        sups = self.host.supports()
        goal = support_under(sups, bx, by + b.r, max(3.0, b.r * 0.6)) or support_below(sups, bx, by) \
            or self.host.world.nearest_floor(bx, by)
        here = self.here()
        d = 1.0 if bx >= goal.clamp(self.wx, 0.0) else -1.0           # 从狗这边过去
        gx = bx - self._pick_offset(d)
        if not goal.covers(gx, self.margin(goal) * 0.5):               # 这边放不下狗（球在墙角 / 窗口边上）：从另一边叼
            d = -d
            gx = bx - self._pick_offset(d)
        if not goal.covers(gx, 0.0):
            if flying:                                              # 够不着：先走到这一层离它最近的地方，等球停了再叫
                self._hold_off(self._route(here, self.wx, goal, goal.clamp(bx, self.margin(goal))))
            else:
                self._go_bark(b)
            return
        route = self._route(here, self.wx, goal, gx, self.margin(goal) * 0.5)
        jumps = any(leg.kind != "run" for leg in route.legs)
        if flying and (not route.reachable or (jumps and not self.host.ball_down_on(goal))):
            self._hold_off(route)                                   # 要跳过去的：等球真落到那一层；够不着的：等球停了再叫
            return
        if not route.reachable:
            self._go_bark(b, route)
            return
        self.route = list(route.legs)
        self.phase = "approach"

    def _go_bark(self, b: Ball, route: Optional[Route] = None) -> None:
        """够不着：走到离球最近的地方，看着它叫两声，就待在那。"""
        if route is None:
            sups = self.host.supports()
            goal = support_below(sups, b.x, b.y) or self.host.world.nearest_floor(b.x, b.y)
            route = self._route(self.here(), self.wx, goal, goal.clamp(b.x, self.margin(goal)))
        self.route = list(route.legs)
        self.phase = "bark_go"

    def _pickup(self, b: Ball) -> None:
        """正对着球：低头叼。鼻子碰到球之前球还是那个小窗口（照样能被你拿走），碰到那一刻才换成嘴里的 3D 球（_watch_pickup）。"""
        self.phase = "pickup"
        props = self.dog.props
        props.begin("ball", self.dog.root_matrix())
        props.item = {"kind": "ball", "mode": "ground", "x": (b.x - self.wx) / self.ppm, "z": 0.0, "yaw": self.dog.yaw,
                      "alpha": 0.0, "left": LINGER, "out": False, "wait": True}
        self.dog.puppet_play("Pick_up", loop=False, fade=FADE_CLIP)
        self.leg = {"kind": "clip", "clip": "Pick_up", "hook": self._watch_pickup}

    def _watch_pickup(self) -> None:
        """低头叼球：鼻子碰到球那一刻（Pick_up 里鼻子最低）道具接手——球的小窗口藏起来、嘴里的 3D 球出来，同一个位置。"""
        if self.carrying:
            return
        it = self.dog.props.item
        p = self.dog.player
        if it is None or p.name != "Pick_up" or p.progress < self.dog.props.spot("Pick_up")[2]:
            return
        it["wait"] = False
        it["alpha"] = 1.0
        self.host.ball_carried(True)
        self.carrying = True
        self._picked_at, self._arrived_at = self.t, None
        self._deliver_side = None
        tune = self.host.tune                                        # 这一趟的性子：放得多不准、路上愣不愣（边牧 0 / None，不抽随机数）
        self._short, self._daze, self._carry_from = temper.drop_short(tune, self.dog.rng), temper.daze(tune, self.dog.rng), self.wx

    def _watch_putdown(self) -> None:
        """放下：球离嘴之前鼠标又挪远了就抬头收回来，叼着接着跟（动作一开始就停不下来，球落下时鼠标早走了，很不连贯）；
        捡球的闸关了才放的（fetch_off）不收回来。3D 球落到地上的那一刻换回球的小窗口。"""
        it = self.dog.props.item
        if not self.carrying or it is None:
            return
        if it.get("mode") == "held":
            if not self._put_final and not self._out_of_patience():
                s, _, _ = self._delivery_target()
                landing = self.wx + self._spot_offset("Put_down", self.facing)       # 现在这么放，球落在哪
                if self._target is None or self._target[0] != s or abs(landing - self.host.cursor()[0]) > self.m(PUT_ABORT_M):
                    self.dog.puppet_play("Pick_up_idle", loop=True, fade=0.2)
                    self.phase = "deliver"
            return
        if it.get("mode") != "linger":
            return
        gx, gy = self.scene_point(it["x"], BALL_R, it["z"])
        self.dog.props.item = None
        self.dog.props.active = None
        self.carrying = False
        self.host.ball_dropped(gx, gy, 0.0, 0.0)
        self._cue("put")

    def lose_ball(self) -> None:
        """小球收起来了（球也是一件道具，playground.ball_out_changed）：嘴里叼着的那颗跟着没了（不放下来，球的小窗口也不回来），
        捡球这件事作废、就地站住。"""
        if self.carrying:
            self.dog.props.item = None
            self.dog.props.active = None
            self.carrying = False
        self.pending_fetch = False
        if self.task == "fetch":
            self.cancel(drop_ball=False)

    def _drop_from_mouth(self, speed: Optional[float] = None) -> None:
        p = self.mouth_point()
        gx, gy = p if p is not None else (self.wx, self.wy - self.m(0.5))
        self.dog.props.item = None
        self.dog.props.active = None
        self.carrying = False
        self.host.ball_dropped(gx, gy, self.v * 0.5 if speed is None else speed, 0.0)

    def scene_point(self, x: float, y: float, z: float) -> tuple[float, float]:
        """狗局部的世界点（米）→ 屏幕全局坐标（和 geometry.project 一样的正交俯视）。"""
        e = math.radians(ELEVATION)
        return self.wx + x * self.ppm, self.wy - (y * math.cos(e) - z * math.sin(e)) * self.ppm
