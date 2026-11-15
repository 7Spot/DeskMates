"""灵动交互开着时的"游乐场"：把空间（widget/world.py）、球（widget/ball.py）、狗在空间里的移动（widget/roam.py）串起来，
窗口（widget/window.py）每帧调 update，输入（widget/input.py）把鼠标事件转过来。

- start()：按现在的屏幕建空间；狗脚下没东西就掉下去（被放在半空的）；球放在狗前面（朝屏幕中间那边）、狗那条线上（小球收起来了就没有球）；每块屏一个圈的窗口建好（不显示）。
- 小球也是一件道具（window.ball_out：道具栏、「物件」页、右键球的「我不要小球了」）：收起来球淡掉，狗就没球玩（没有圈、不捡）；
  再拿出来放在狗前面（ball_out_changed）。
- stop()：狗正在跑 / 跳的就地停（叼着的球不见）、球的小窗口淡掉、圈收起来、表情复原。
- 每帧：球的物理（窗口上沿接住往下掉的球，左右边、下边把球弹回去；球停在窗口上、窗口挪了球跟着挪）→ 捡球的圈 → roam（跑、跳、骑窗口）
  → 表情 → 球和圈的小窗口摆好。
- 扔球：按住球拖、松手按手的速度扔（widget/hand.py，按系统给事件打的时间算，程序卡了也算得准）；只是点一下（没怎么动）只 duang，球不动（鼠标、触摸板一样）。幅度按球的质量算（调参）。
  进圈才追（widget/ring.py、_step_ring）：你拿起球，狗站好看着它，身边出一个圈；球在圈里停够了（调参 ring_hold_s）圈满，
  狗叫一声（调参 ready_bark 的概率）、前肢俯下来等着（roam），拿多久等多久；这之后松手才去追，扔出去、放下都算（不猜玩还是挪开球）。
  没满就松手狗只看着。捡球的总闸 fetch_on 只在看细节、小球收起来时是假的。
  球什么时候都抓得住：飞着的球越快点击范围越大，远远抓住的很快滑进手里；狗低头去叼、鼻子还没碰到球时照样能拿走；
  叼在嘴里的也能点住拿走（狗松口）。拿着球时松手事件丢了（按着的时候切走了、系统弹窗）：鼠标键松开 LOST_UP_S 秒还没来就当松了手，原地放下。
- 点狗（input.py 认手势）：只 duang 一下（压下去、弹回来），没有别的反应。
- 招牌时刻（性子里憨的那一份，widget/temper.py 的 Mood、express；边牧没有）：roam 报的时刻（放下球、被球晃到、够不着叫完、路上愣住，_cue）
  和鼠标从远处挪到狗跟前（_greet）记在 mood 里，_express 最后叠到表情上。都不出声。
  呆萌的来回看（_glance）：狗只看着的球（没进圈满、狗没去追）停下那一刻，按 temper.glance_chance 的概率看球 0.5 秒—看你 0.6—看球 0.5—看你 0.6，
  之后照常；只动头和眼睛（look_point 按时间表给球 / 鼠标，身子不跟着转），25 秒内不再演；拿起球、拎它、点它、它有事要做就停。
- 自己歇着（_lounge）：活跃度低的狗（性子，widget/temper.py 的 rest_plan；边牧没有）默认坐着（萨摩耶一闲下来就坐，
  temper.sits_by_default），没人理 60 秒趴下；拿起球、球在动叫醒它时回到坐着（不站起来），拎它、要走的事站起来、做完坐回去。
  拿起球：坐着转头看（不交给 roam），趴着的先坐起来；圈照样算，满了坐着叫一声（_seated_bark：只张嘴 + 狗叫的声音，没有坐着叫的片段）、坐着等，不俯身；
  松手才站起来去追（起身那半拍就是它的「慢半拍」）。
  点它只 duang、不起来；站在转台上（看细节）钟停着、姿势不变；站在窗口边上只坐不趴。
- 按下立刻拖 = 拎起来（dog_grabbed；姿势在 widget/lift.py）：松手手还在动就扔出去，幅度按质量算（调参），不动就掉下去；拎到窗口上方松手也能站上去。
- 狗够不着、那条线又在它上面：狗头旁边冒一个气泡「好像有点高」（widget/bubble.py，点不到）；线在它下面的只叫。
- 别的 App 的窗口（狗跳上去的地方）每 0.25 秒问一次系统（native.window_frames，只读位置大小）；狗、球站在哪个窗口上就每帧问那一个。
  那个窗口不在这个桌面了、被台前调度收走了、一帧之内被系统挪走又变了大小：当它没了，狗和球原地掉下来。
  「窗口当台子」关着（灵动交互的选项，window.hop_windows_on）：一个窗口都不算，空间里只有每块屏的地面。
- 球能停的窗口和狗能站的窗口分开算（以前共用一张按狗身材筛的表，狗调大了球就停不上去）。
- 声音（模型包里，widget/voice.py）：球撞到东西按力度响、你拿起球响一声；狗落地响一声。圈满时狗叫的那一声是 Bark 片段自带的（window.clip_sounds），圈本身不出声。
- 物件（widget/things.py）：摆出来的狗窝、狗屋、盆，各是一个小窗口，things 管摆、拖、落、记位置；这里只在开、关、每帧、
  屏幕和大小变了的时候叫它一声。家具不进空间，狗和球从它前面过（例外：平顶狗屋的屋顶是台子，狗窝的垫子狗踩着过）。
- 摆下去马上有反应（thing_placed）：窝、盆刚摆出来落定、刚拖完松手落定，狗闲着（_free：没任务、没被拎、球不在你手上也没在动、
  不在转台上）就过来——窝：走过去趴进去，不等该歇的时候，去的是刚放下的这一个；满着的盆：吃 / 喝一次（和敲盆同一条路，够不着就算了、不叫）。
  忙着就算了：窝等到该歇的时候再回，盆等你敲。
- 踩着窝过去（狗不能从狗窝里穿过去，_tread）：狗在线上跑、走、站，身子正中进了狗窝垫子的范围，根抬到垫子上（dog.perch，和歇进窝同一根）、
  窝的前沿盖到脚前面；出了范围落回线上。跳、掉、被拎、被扔，低头叼球、放球、吃喝时不抬。
- 回窝（_lounge 里）：摆了狗窝、狗屋（things.nest_spots），狗够得着：到第一次该歇的时候（自己歇的狗是计划的第一段，萨摩耶 20 秒；
  不自己歇的边牧 temper.NEST_AFTER_S 90 秒）安静地走过去（roam.go_nest，最快小跑、不出声），到了直接趴下（settle_in：根缓到垫子那么高 dog.perch、
  歇在垫子上的不画影子、窝的前沿盖到狗前面）。没摆窝、够不着：和没有物件时一样（萨摩耶原地坐下再趴下，边牧一直站着）。已经在原地歇着的不为了新摆的窝起来。
  叫起来还是那几样（拿起球、拎它、球在动；_can_lounge），再加窝被拿走、收起（nest_gone）：rouse——站起来，根缓回去、影子回来、前沿收掉。点狗只 duang，不起来。
- 自己溜达（_wander）：没人理一阵子（temper.wander_every：边牧 60～150 秒，萨摩耶 120～300 秒，趴着的再长一半）在脚下这条线上
  慢慢走一小段（temper.wander_reach，只走路、不跳、不换线、不出声），走完家改到这，接着照常待着（萨摩耶坐回去）。拴着「这次闲下来的地方」
  （_wander_anchor，离它不超过 WANDER_LEASH_M），不停在物件上（狗窝垫子、狗屋、盆的左右再留 WANDER_CLEAR_M）。趴在窝里的到点也起来走出窝，
  之后照回窝的规矩回去。摆着满盆、够得着（同一条线、WANDER_SIP_M 以内）时 WANDER_SIP_P 去吃两口（roam.eat 的 sip：低头一半时间、盆不变空、
  不出声 hushed）。卡片开着、鼠标在狗身上或离它一个身高以内（停着一阵、狗不看你了的不算：watching_you）、正做随机动作或换姿势、看细节时不走；半路你伸手过来、拿起球、球动了、拎它、打开卡片就地站住。
- 吃喝（bowl_tapped）：点一下摆着的饭盆、水盆 = 敲盆，盆先添满（things），狗过去吃 / 喝（roam.eat，每点一次都来；在窝里的起来过去），吃完盆变空（bowl_emptied）。
  狗这时被拎着拖着、在空中、球在你手上、在捡球、掉着、站在转台上、已经在吃这个盆：不来，盆只 duang。盆被拿走、收起：正吃着的抬头站住（bowl_gone）。
- 台子：摆着的平顶狗屋（包里写了 platform 的款）是混进窗口表的假窗口框——frames = things.frames() + 问系统得到的那份（_native_frames），
  窗口号是负的：_frame 直接问 things、不问系统，_check_cover 不管它（不会被别的窗口盖住）。台子摆了、拿起、落定：platforms_changed 重拼，不重问系统。
  「窗口当台子」关着 _native_frames 是空的，台子照留。别的（狗站上去、跳上跳下、骑着走、球停在上面、撞上去弹回）都是窗口上沿现成的那一套。
- 看细节（狗站在转台上，dog.on_turntable，widget/closeup.py）：不捡球——fetch_on 是假的（不出圈、不俯身、拿起球不叫、扔了不追），
  上下转台时 window.closeup 叫 fetch_changed；也不跳下被盖住的窗口。临时放大时空间、球照旧按存下来的大小（ppm 是 window.world_scale），roam 不走（update 的 hold）。
roam 要的"host"接口（ppm、supports、window_top…、ball_*、fetch_ready、cursor、pack、tune…）都在这里。"""
from __future__ import annotations

import math
import logging
import os
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QVariantAnimation
from PySide6.QtGui import QCursor, QGuiApplication

import config
from widget import excite, hand, native, sticker, temper
from widget.ball import Squash
from widget.props import BALL_R
from widget.render import ELEVATION
from widget.ring import MIN_HOLD_S, Ring, RingShape, RingWindow, in_ring, prepare_soon as prepare_ring, ring_extent, ring_shape
from widget.roam import DOG_H_M, MAX_UP_DOG, Roam
from widget import things as things_mod
from widget.things import NestSpot, Things
from widget.tuning import LOOK_IDLE_S
from widget.world import (GRAVITY_M, Area, Ball, BallPhysics, Block, Edge, Support, World, WindowFrame, blocks_from, step_ball, support_below,
                          support_under)

log = logging.getLogger("playground")

FLOOR_MARGIN_PX = 18.0      # 地面离可用区域底边多少（1 倍大小时，跟着缩放）：狗的影子画在这一条里
FRAMES_EVERY = 0.25         # 多久问一次别的窗口在哪
COVER_EVERY = 0.3           # 站在窗口上时多久看一次脚下有没有被别的窗口盖住
THROW_SAMPLE = 0.08         # 算手的速度时取多长一段（秒，按系统给事件打的时间算，见 widget/hand.py）
THUD_HOP_M = 1.6           # 狗屋落地：旁边停着的球往上蹦多快（米 / 秒，再按远近、落地多重减；things._shake）
THUD_LOOK_S = 0.9          # 狗屋落地：闲着的狗看过去多久
THROW_WINDOW_SYS, THROW_FADE_SYS = 0.7, 0.45   # 系统开了三指拖移 / 轻点两下拖移：手指抬起后系统还要拖一小会才发松手
TAP_HOLD_S, TAP_MOVE_PX = 0.15, 6.0   # 按住停着的球：这么久（秒）或挪了这么远（像素）才算拿起，不然是点了一下（只 duang）
DOG_FIT_M = 0.86            # 窗口上沿离屏幕最上沿（含菜单栏）至少这么高（米）才站得下狗：狗连耳朵约 0.83 米，耳朵尖伸进菜单栏那条、碰不到屏幕顶
                            # （狗要能放到屏幕最顶上）。这是默认值，模型包的 fit_m 为准
MIN_PLATFORM_PX = 200.0     # 窗口至少这么宽（像素）才算狗的台子：小工具窗、台前调度漏网的缩略图都不跳
BALL_MIN_PLATFORM_PX = 30.0 # 球能停的窗口上沿至少这么宽（像素）
BALL_HEADROOM_R = 2.2       # 球能停的窗口上沿离屏幕顶至少几个球半径（放得下球就行）
SNAP_SECONDS = 0.05         # 远远抓住的球滑进手里的时间常数
SIZE_MIN = 0.6              # 推荐大小最小这么多倍（不再封顶；上限是 window.scale_range）
JUMP_MOVE_PX, JUMP_RESIZE = 20.0, 0.08   # 窗口一帧之内挪了这么远、大小又变了这么多成：是系统收起 / 摆放窗口，不是人在拖
DOG_THROW_MIN_M = 0.8       # 松手时手比这快（米 / 秒）才算把狗扔出去，慢的是放下
HAND_WINDOW = 0.05          # 拎着的时候手的速度按最后这么久算（秒）
BOUNCE_MIN_M = 0.7          # 球撞上去比这快（米 / 秒）才响（滚、贴地跳的最后几下不响）
BOUNCE_FULL_M = 8.0         # 比这快就是最响
CHARGE_FULL_AT = 1.0        # 充能的声音（玩具包里的 charge：木鱼越敲越密，1.30 秒）放到第几秒是「满」（最后一下）：圈满那一下对着它
CHARGE_LATE_S = 0.03        # 声音从叫它放到真出声晚这么多（NSSound 起播约 0.025 秒，把音量设成 0 量的）：开始的位置往前赶这么多
PERCH_S = 0.12              # 歇进窝、起来：根抬到垫子上 / 落回去缓这么久
CURL_MARGIN_M = 0.03        # 歇在狗窝里：尾巴尖离窝的内沿至少留这么多（米）
WANDER_LEASH_M = 1.5        # 自己溜达：离这次闲下来的地方最远这么多（米），不越逛越远
WANDER_MIN_M = 0.4          # …一趟至少走这么远（米），不够就换一边、再不够这次不走
WANDER_NEST_OUT = (0.8, 1.5)   # …从窝里起来：走出窝这么远（米）
WANDER_CLEAR_M = 0.15       # …停下的地方离物件（狗窝、狗屋、盆）左右至少这么远（米）
WANDER_RETRY_S = 12.0       # …到点了却没地方走（贴着屏幕边、窗口上沿太窄）：过这么久再看
WANDER_SIP_P = 0.35         # …摆着满盆、够得着：这一趟去吃两口的概率
WANDER_SIP_M = 3.0          # …盆在同一条线上、这么近（米）以内才去
NEST_RETRY_S = 3.0          # 该回窝了却没去成（够不着、窝还在落）：隔这么久再看一次（排路线不便宜，不每帧排）
NEST_NEAR_M = 0.15          # 走到离该歇的那一点这么近才算到了窝（半路被别的事岔开、掉下去了的不算）
POINTER_STILL_PX = 2.0      # 鼠标停着就不看：离上次算「动了」的地方挪不到这么远（像素）不算动，滤掉手抖、触摸板的毛刺
LIE_ROOM_M = 0.55           # 站在窗口上：离窗口两头都至少这么远（米）才趴（趴下前爪往前伸 0.40、身后 0.49 米，贴着边趴有一截悬空），不然只坐着
LOST_UP_S = 1.0             # 拿着球、鼠标键却已经松开这么久（秒）还没收到松手事件：当松手丢了，原地放下。
                            # 要比系统三指拖移抬手后还接着拖的那一小会（约 0.7 秒，THROW_WINDOW_SYS）长，不然会抢在真的松手前面
TURN_MIN_M = 1.0            # 球横着比这快（米 / 秒）撞回来才算掉头；慢慢碰一下墙就落下的，一眼看得出停在哪
FORECAST_HZ = 60            # 往后算球的路线时一秒算几步


@dataclass
class Forecast:
    """球从某一刻起会怎么走（用同一套物理往后算的）。"""
    key: tuple[int, int]              # (第几次扔, 已经掉头几次)：对不上就是过期了
    at: float                         # 算的时候球的钟走到哪（秒，Playground._ball_clock）
    rest: tuple[float, float]         # 最后停在哪
    path: list[tuple[float, float]]   # 每一步在哪（第 0 个是算的那一刻）
    turns: list[int]                  # 第几步掉的头（撞墙、撞窗口侧边弹回来）


def recommended_scale(screen_height: float, max_up: float = MAX_UP_DOG, height: float = DOG_H_M, fit: float = DOG_FIT_M) -> float:
    """这么高的屏幕，灵动交互最合适多大：狗越大跳得越高，但站到窗口上要的头顶空间也越大。两头碰上的时候最多窗口能上能下：
    够得到（从地面往上最多跳这么高）+ 站得下（窗口上沿离屏幕顶至少这么远）= 屏幕高。这时狗站着约占屏高四分之一。取到 0.05 倍；只有下限（SIZE_MIN）。"""
    k = screen_height / ((fit + max_up * height) * config.PIXELS_PER_METER)
    return round(max(SIZE_MIN, k) * 20.0) / 20.0


def _system_jump(prev: tuple[float, float, float, float], cur: tuple[float, float, float, float]) -> bool:
    (x0, y0, w0, h0), (x1, y1, w1, h1) = prev, cur
    moved = math.hypot(x1 - x0, y1 - y0)
    resized = max(abs(w1 - w0) / max(w0, 1.0), abs(h1 - h0) / max(h0, 1.0))
    return moved > JUMP_MOVE_PX and resized > JUMP_RESIZE


class Playground:
    def __init__(self, window):
        self.w = window
        self.dog = window.dog                 # dog、pack、tune、bank 是抄着的：换模型时 pet_arrived 改（别处要用就现读 self.w 的，别再抄）
        self.pack = window.pack
        self.tune = window.tuning
        self.ball_tune = window.ball_tuning
        self.bank = window.sound_bank
        self.ball_bank = window.ball_bank
        self.world: Optional[World] = None
        self.frames: list[WindowFrame] = []           # 狗和球看的窗口表：台子的假窗口框（things.frames）在前 + 别的 App 的窗口
        self._native_frames: list[WindowFrame] = []   # 问系统得到的那份（别的 App 的窗口）：物件自己找线只看它
        self._frames_at = -math.inf
        self._sups: Optional[list[Support]] = None
        self._ball_tops: Optional[list[Support]] = None
        self._edges: Optional[list[Edge]] = None
        self._blocks: Optional[list[Block]] = None
        self._tick_frames: dict[int, Optional[tuple[float, float, float, float]]] = {}
        self._prev_frames: dict[int, tuple[float, float, float, float]] = {}
        self.ball: Optional[Ball] = None
        self.ball_win = None
        self.ring = Ring()                    # 捡球的圈：进度、满没满（widget/ring.py）；roam 看 fetch_ready
        self._charging = False                # 充能的声音这会儿在响（_charge_sound）
        self.ring_wins: dict[str, RingWindow] = {}   # 圈的窗口：每块屏一个，按屏的名字记（和 window._ghosts 一样；_ensure_ring_windows）
        self._ring_at: Optional[RingShape] = None    # 圈在哪：狗站好看着球时每帧更新；不算了就停在最后那处淡掉，不跟着狗走
        self.ball_held = False
        self._seat_watch = False              # 默认坐着的狗（萨摩耶）这一趟是坐着看你手里的球（_watch_held_ball），圈只这时算
        self._lost = hand.LostRelease()       # 拿着球、鼠标键却松开多久了（_check_lost_release：离屏测试、自测里的「拿着」没有真按键，不算）
        self.carried = False
        self.throw_id = 0                     # 每扔一次（或放下、掉下）加一：狗按它判断要不要重新算球停在哪
        self._predicted: Optional[Forecast] = None   # 球从上次掉头（或离手）起会怎么走；过期了重算（_forecast）
        self.ball_turns = 0                   # 球真掉过几次头（撞墙、撞窗口侧边弹回来；只加不清）：狗按它判断球是不是又拐了个没料到的弯
        self._ball_clock = 0.0                # 球的物理一共走了多久（秒）：对上算好的路线走到第几步
        self._ball_touch: Optional[tuple[int, tuple[str, int]]] = None   # (第几次扔, 线)：球这一扔最近碰过（弹、滚、停）哪条线
        self.grab: deque[tuple[float, float, float]] = deque()
        self._grab_off = (0.0, 0.0)
        self._pointer = (0.0, 0.0)            # 拿着球时鼠标最后在哪
        self._tap: Optional[tuple[float, float]] = None   # 按在停着的球上、还没算拿起：按下的位置
        self._tap_age = 0.0
        self._press_from_pad = False          # 这一下是触摸板点的
        self.ball_duang = Squash()
        self.roam = Roam(self.dog, self)
        self.mood = temper.Mood()             # 招牌时刻：哪个表情演到什么时候（_cue、_greet 记，_express 读）
        self.roam.on_cue = self._cue
        self._hand: deque[tuple[float, float, float]] = deque()   # 拎着狗时手在哪（时间, x, y）
        self.active = False
        self._idle_for = 0.0                  # 没人理多久了（秒）：自己歇着按它算（_lounge）
        self._still_for = 0.0                 # 鼠标停着多久了（秒；你在跟它玩也算动）：停够调参 look_idle_s 狗就不看你了（watching_you）
        self._cursor_seen: Optional[tuple[float, float]] = None   # 上次算「鼠标动了」时它在哪
        self._nest: Optional[NestSpot] = None        # 狗歇在哪个窝里（settle_in 记，rouse 清）
        self._nest_going: Optional[NestSpot] = None  # 狗正往哪个窝走（roam 的 nest）
        self._nest_wait = 0.0                 # 回窝没去成：还要等多久再看一次（NEST_RETRY_S）
        self._perch_to = 0.0                  # dog.perch 要缓到多少（米）：歇在窝里是 settle_in 定的，别的时候每帧按脚下有没有垫子定（_tread）
        self._pad: Optional[str] = None       # 狗正踩着哪个狗窝的垫子（走过、站着；_tread）
        self._eating: Optional[str] = None    # 狗正往哪个盆去 / 正吃着哪个盆（roam 的 eat）
        self._bowl_front_key: Optional[str] = None   # 哪个盆的前沿正盖在狗前面（_bowl_front）
        self._rng = random.Random()           # 自己溜达的随机数（不动狗的那一份：随机动作的先后照旧）
        self._wander_in = 0.0                 # 还要等多久走下一趟（秒，_wander）
        self._wander_anchor: Optional[tuple[str, int, float]] = None   # 这次闲下来的地方（哪条线、x）：溜达拴着它
        self._sipping = False                 # 正在自己溜达过去吃两口（roam 的 eat 的 sip）：不出声、盆不变空
        self.roam.on_done = self._roam_done
        self._cover_at = 0.0
        self._ball_ride: Optional[tuple[int, float]] = None
        self._ball_seen: Optional[tuple[float, float, float]] = None   # 上一帧球在哪、转到哪（quiet 用）
        self._now = 0.0                        # 游乐场开着走了多久（秒，update 推；呆萌时刻的 25 秒按它算）
        self._ball_moving = False              # 上一帧球在不在动（停下那一刻才看要不要演呆萌时刻）
        self._glance_t: Optional[float] = None # 呆萌的来回看演到第几秒（None = 没在演）
        self._glance_last = -math.inf          # 上次演是什么时候（_now）
        self._thud_look: Optional[tuple[float, float, float]] = None   # 狗屋落地：狗看过去哪、看到什么时候（thing_thudded）
        self._ball_fade = QVariantAnimation()
        self._ball_fade.valueChanged.connect(self._set_ball_alpha)
        self._ball_fade.finished.connect(self._ball_fade_done)
        self._pid = os.getpid()
        self.things = Things(self)            # 摆出来的物件（widget/things.py）

    # ---------- host 接口（roam 用） ----------
    @property
    def ppm(self) -> float:
        """空间、球、roam 的比例尺：存下来的大小（window.world_scale）。看细节临时放大时狗画得更大（window.ppm），这里不跟着变；
        要狗画出来的大小就明着用 window.ppm。"""
        return config.PIXELS_PER_METER * self.w.world_scale

    @property
    def fetch_on(self) -> bool:
        """捡球的总闸：关着不出圈、狗不追，球照样能拖能扔。能关它的：狗站在转台上（看细节）、小球收起来了（没有球）；window.fetch_on
        一直开着（单测拿它让狗只看着）。闸一变要叫 fetch_changed；没叫到的话 _step_ring 也会让还在等你扔的狗起来。"""
        return self.w.fetch_on and self.ball is not None and not self.dog.on_turntable

    @property
    def fetch_ready(self) -> bool:
        """球在圈里停够了（满过，一直算到球离手）：狗该叫一声、俯身等你扔（roam 看它，自己接着做）。"""
        return self.ring.ready

    def supports(self) -> list[Support]:
        """狗能站的：地面 + 看得见、站得下狗的窗口上沿。窗口列表每 FRAMES_EVERY 秒问一次系统（球的那两张表跟着重算）。
        狗被拎着、飞着的时候不问（这一问要等系统回话，真甩的时候一次能卡一百多毫秒）：用拎起来时问的那份，落地时站的窗口还会单独再问一次。"""
        now = time.perf_counter()
        if self._sups is None or (now - self._frames_at > FRAMES_EVERY and not self.w._flinging()):
            self._refresh_frames(now)
        return self._sups

    def frames_stale(self) -> None:
        """要落的窗口没了、「窗口当台子」切了：窗口表过时了，下次重新问。"""
        self._sups = None

    def _refresh_frames(self, now: float) -> None:
        self._frames_at = now
        self._native_frames = [WindowFrame(*f) for f in native.window_frames(self._pid)] if self.w.hop_windows_on else []   # 「窗口当台子」关着：只有每块屏的地面（和摆着的台子）
        self._compose_frames()

    def _compose_frames(self) -> None:
        """窗口表 = 摆着的台子（假窗口框，排在前面）+ 别的 App 的窗口；狗能站的线、球的那几张表跟着重算。"""
        platforms = self.things.frames()
        self.frames = platforms + self._native_frames if platforms else self._native_frames
        self._ball_tops = self._edges = self._blocks = None
        self._sups = list(self.world.floors) + self.world.window_tops(self.frames, max(MIN_PLATFORM_PX, self.ppm * 0.7),
                                                                      self.ppm * self.pack.fit_m, from_screen_top=True)

    def platforms_changed(self) -> None:
        """摆着的台子变了（摆了、拿起、落定、收起、跟着脚下的窗口挪了；things 叫）：窗口表重拼，不重问系统。还没问过窗口表就等第一次问。"""
        if self._sups is not None and self.world is not None:
            self._compose_frames()

    def route_blocks(self) -> list[Block]:
        """挡路的窗口（带前后）：从人眼看，飞的路线不能穿过挡在前面的窗口（widget/world.py 的 Leaper）。"""
        self.supports()
        if self._blocks is None:
            self._blocks = blocks_from(self.frames, self.world)
        return self._blocks

    def ball_platforms(self) -> list[Support]:
        """球能停的窗口上沿：看得见、比球宽、上面放得下球就行，和狗多大没关系。"""
        self.supports()
        if self._ball_tops is None:
            r = BALL_R * self.ppm
            self._ball_tops = self.world.window_tops(self.frames, max(BALL_MIN_PLATFORM_PX, 3.0 * r), BALL_HEADROOM_R * r)
        return self._ball_tops

    def ball_edges(self) -> list[Edge]:
        """窗口的左右边、下边（看得见的那几段）：球、被扔出去的狗从外面撞上来会被挡回去。"""
        self.supports()
        if self._edges is None:
            self._edges = self.world.window_edges(self.frames)
        return self._edges

    def window_listed(self, number: int) -> bool:
        """这个窗口还在这个桌面上看得见（没关、没最小化、没切到别的桌面、没被台前调度收进左边那排）。"""
        self.supports()
        return any(f.number == number for f in self.frames)

    def _frame(self, number: int) -> Optional[tuple[float, float, float, float]]:
        if number < 0:                                            # 摆着的台子（假窗口号）：问 things，不问系统；「窗口当台子」关着也在
            f = self.things.frame(number)
            return (f.x, f.y, f.w, f.h) if f is not None else None
        if not self.w.hop_windows_on:
            return None                                           # 「窗口当台子」关了：正站着的窗口也当它没了（狗、球原地掉下来）
        if number not in self._tick_frames:
            f = native.window_frame(number)
            prev = self._prev_frames.get(number)
            if f is not None and prev is not None and _system_jump(prev, f):
                f = None                                          # 被系统一下子挪走又变了大小（台前调度收起、平铺）：当它没了
            self._tick_frames[number] = f
        return self._tick_frames[number]

    def window_left(self, number: int) -> Optional[float]:
        f = self._frame(number)
        return f[0] if f is not None else None

    def window_top(self, number: int, at_x: Optional[float] = None, headroom: Optional[float] = None) -> Optional[Support]:
        """那个窗口现在的上沿（整条，夹在它所在的那块屏里）；窗口没了、上面放不下了返回 None。
        headroom 不给：放得下狗（从整块屏的最上沿量，留一点余量免得窗口挪一点就掉）；给了：从菜单栏下沿量这么多（球用）。"""
        f = self._frame(number)
        if f is None or self.world is None:
            return None
        x, y, w, h = f
        i = None
        for px in ((at_x,) if at_x is not None else ()) + (x + w / 2, x + 12, x + w - 12):
            i = self.world.area_index(px, y + 1)
            if i is not None:
                break
        if i is None:
            return None
        a = self.world.areas[i]
        if headroom is None:
            ref, need = self.world.screen_top(i), self.ppm * self.pack.fit_m * 0.9
        else:
            ref, need = a.top, headroom
        if y - ref < need or y >= self.world.floor_y(i) - 4:
            return None
        return Support(max(x, a.left), min(x + w, a.right), y, "window", number)

    def cursor(self) -> tuple[float, float]:
        """鼠标现在在哪（全局坐标）：狗叼着球往这走。"""
        p = QCursor.pos()
        return float(p.x()), float(p.y())

    def barking(self, kind: str, key: int, x: float) -> None:
        """狗够不着要去的地方（kind、key 那条线上的 x），正冲那边叫：那条线在它上面就冒气泡「好像有点高」，像狗说的；在下面的只叫。"""
        line = next((s for s in self.supports() if s.kind == kind and s.key == key and s.covers(x)), None) \
            or next((s for s in self.ball_platforms() if s.kind == kind and s.key == key and s.covers(x)), None)
        if line is None or line.y >= self.roam.wy - 1.0:
            return
        self.w.show_too_high()

    def home_yaw_here(self) -> Optional[float]:
        """狗现在歇着该朝哪（灵动交互里：头看着球就朝球那边，不然看鼠标在哪边，window._home_yaw）。
        刚走到狗屋门口的朝那个窝要它朝的那边（头朝外）；走到狗窝、平顶狗屋，靠边的朝所有屏合起来的中间（window._edge_yaw）。"""
        going = self._nest_going
        if going is not None and going.yaw is not None:
            return going.yaw
        edge = self.w._edge_yaw() if going is not None else None
        return edge if edge is not None else self.w._home_yaw()

    def dog_landed(self, speed_m: float) -> None:
        """狗落地、撞到东西：响一声，越快越响。自己走回窝、自己溜达路上的那几跳不出声。"""
        if self.roam.task in ("nest", "wander"):
            return
        self.bank.play("drop", max(0.25, min(1.0, speed_m / 6.0)))

    def predict_rest(self) -> Optional[tuple[float, float]]:
        """球最后会停在哪（用同一套物理往后算，最多 8 秒）。球被拿着、叼着的时候 None。
        狗什么时候直接往这跑、什么时候先追球本身，看 ball_turns_left（roam._plan_pickup）。"""
        b = self.ball
        if b is None or self.ball_held or self.carried or self.world is None:
            return None
        if b.resting:
            return (b.x, b.y)
        return self._forecast().rest

    def ball_turns_left(self) -> int:
        """球从现在到停下还要掉头几次（撞墙、撞窗口侧边弹回来）。0 = 一路不掉头：弧线、落地弹几下、滚到停，一眼看得出它停哪。"""
        b = self.ball
        if b is None or self.ball_held or self.carried or self.world is None or b.resting:
            return 0
        f = self._forecast()
        now = (self._ball_clock - f.at) * FORECAST_HZ
        return sum(1 for i in f.turns if i > now)                 # 按路线上的时刻数：真球晚一两帧才撞上也不会卡在"还有一次"

    def ball_ahead(self, seconds: float) -> Optional[tuple[float, float]]:
        """球再过这么久在哪（按算出来的路线）。没球 None；拿着、叼着、停着的就是它现在在哪。"""
        b = self.ball
        if b is None:
            return None
        if self.ball_held or self.carried or self.world is None or b.resting:
            return (b.x, b.y)
        f = self._forecast()
        i = int(round((self._ball_clock - f.at + seconds) * FORECAST_HZ))
        return f.path[max(0, min(len(f.path) - 1, i))]

    def ball_down_on(self, s: Support) -> bool:
        """球这一扔已经落到过这条线上（弹过、滚着、停着）。"""
        t = self._ball_touch
        return t is not None and t[0] == self.throw_id and t[1] == (s.kind, s.key)

    def _turned(self, before: float, after: float) -> bool:
        """横向速度从 before 变成 after：算不算掉头。"""
        return before * after < 0.0 and abs(before) >= TURN_MIN_M * self.ppm

    def _forecast(self) -> Forecast:
        """球从现在起会怎么走（用同一套物理往后算，最多 8 秒）。同一次扔、掉头次数没变只算一次；球每真掉一次头重算一遍
        （真球和算出来的差一点点，撞完从它真在的地方重算）。"""
        key = (self.throw_id, self.ball_turns)
        f = self._predicted
        if f is not None and f.key == key:
            return f
        b = self.ball
        sim = Ball(b.x, b.y, b.r, b.vx, b.vy, b.rolling, b.resting, b.spin, b.bounces, b.on)
        platforms, edges = self.ball_platforms(), self.ball_edges()
        phys = self._ball_phys()
        path, turns = [(sim.x, sim.y)], []
        for i in range(8 * FORECAST_HZ):
            vx = sim.vx
            step_ball(self.world, sim, 1 / FORECAST_HZ, self.ppm, platforms, edges, phys)
            path.append((sim.x, sim.y))
            if self._turned(vx, sim.vx):
                turns.append(i + 1)
            if sim.resting:
                break
        f = self._predicted = Forecast(key, self._ball_clock, (sim.x, sim.y), path, turns)
        return f

    def ball_carried(self, on: bool) -> None:
        self.carried = on
        if on and self.ball_win is not None:
            self.ball_win.alpha = 0.0
            self.ball_win.hide()

    def ball_dropped(self, gx: float, gy: float, vx: float, vy: float) -> None:
        """狗把球放下 / 掉下来 / 被你从嘴里拿走：球的小窗口在这里重新出来。"""
        self.carried = False
        if self.ball is None:
            return
        b = self.ball
        b.x, b.y = gx, gy
        b.vx, b.vy = vx, vy
        b.rolling = b.resting = False
        b.on = None
        self.throw_id += 1
        s = support_under(self.supports() + self.ball_platforms(), gx, gy + b.r, 2.5)
        if s is not None and abs(vx) < 1 and abs(vy) < 1:
            b.y, b.resting, b.on = s.y - b.r, True, (s.kind, s.key)
        if self.ball_win is not None:
            self._sync_ball()
            self.ball_win.alpha = 1.0
            self.ball_win.show()

    # ---------- 开 / 关 ----------
    def start(self) -> None:
        self.active = True
        self.dog.lift.prepare()
        self.rebuild_world()
        self.things.start()                                       # 记着摆着的物件各回原处
        self.roam.place(*self.w.scene_world())
        self.roam.facing = -1.0 if math.cos(math.radians(self.dog.home_yaw)) < 0 else 1.0
        self.roam.drop_to_support()
        self.ring.clear()
        self._idle_for = 0.0
        self._still_for, self._cursor_seen = 0.0, None             # 刚开灵动交互：你刚点过开关，先看着你
        self._leave_nest(now=True)
        self._wander_anchor, self._sipping = None, False
        self._reset_wander()
        self.mood = temper.Mood()
        self._ensure_ring_windows()
        if self.w.ball_out:
            self._spawn_ball()
        else:
            self.ball = None                                      # 小球收起来了：这一趟没有球

    def stop(self) -> None:
        self.active = False
        self._end_lift_now()
        self.roam.lose_ball()                                     # 叼着的球跟着收（以前只剪掉嘴里的那颗，roam 还当自己叼着，再开灵动交互会接着「送球」）
        self.roam.cancel(drop_ball=False)
        self.dog.props.cut()
        self.carried = False
        self.ball_held = False
        self._seat_watch = False
        self._tap = None
        self.ball_duang.release()
        self.dog.expr.reset()
        self.dog.expr.release()
        self.dog.lounge = None                                    # 不换姿势：接着 set_dynamic(False) 会让它回到选的姿势
        self._leave_nest(now=True)                                # 歇在窝里的：根当场落回去、前沿当场收（停了以后没有下一帧）
        self._eating = None
        self._bowl_front_key = None
        self._sipping = False
        if self.ball_win is not None and self.ball_win.isVisible():
            self._fade_ball(0.0, 220)
        self.things.stop()                                        # 物件一起淡出、藏起来，位置留着
        self._put_ring_away()                                     # 当场收：停了以后没有下一帧来淡掉它
        self.roam.home = None

    # ---------- 换模型（换模型不重启，window._use_kit；狗这时看不见） ----------
    def pet_leaving(self) -> None:
        """旧狗要走了：它手上的事收掉——拎着的放下、叼着的球原地松口（球的小窗口回来）、跑到一半跳到一半被扔着的不接着做（roam.leave）、
        歇在窝里的根落回线上前沿收掉、吃到一半的不吃了（盆还满着）、捡球的圈清掉（充能的声音一起收）、没人理的钟归零。
        和 stop() 收的一样，但不关灵动交互：球、物件不淡出，圈的窗口留着；你手里的球还在你手里。灵动交互关着时 stop() 早收过了。"""
        if not self.active:
            return
        self._end_lift_now()
        self._hand.clear()
        self.roam.leave()
        self._leave_nest(now=True)
        self._eating = None
        self._bowl_front_key = None
        self._seat_watch = False                                  # 坐着看球的那一趟是旧狗的：新狗下一帧照它自己的性子重新看（_step_ring）
        self._put_ring_away()
        self._idle_for = self._nest_wait = 0.0

    def pet_arrived(self) -> None:
        """新狗来了（窗口已经换好 dog、pack、tuning、sound_bank，新狗朝向定好了）：抄着的引用改成新的、roam 牵新狗；招牌时刻、兴奋重来。
        灵动交互开着：新狗站在旧狗那条线上（站不下、在半空的放到正下方最近的线上，roam.land_now）；能站的窗口按新狗的个头重算（fit_m），
        狗窝按新身高重排（things.pet_changed），踩着垫子的这一帧就抬好；捡球圈的墨带按新身高重画、拎起来的姿势先量好（模型上有就直接拿）。
        球不动；你手里拿着球的，下一帧照「球在你手上」重新站好看球、圈从空的算（_step_ring）。"""
        w = self.w
        self.dog, self.pack, self.tune, self.bank = w.dog, w.pack, w.tuning, w.sound_bank   # 这四样是抄着的：换模型只在这里改
        self.roam.use_dog(self.dog)
        self.mood = temper.Mood()
        if not self.active:
            return
        self.dog.lift.prepare()
        if self._sups is not None and self.world is not None:
            self._compose_frames()                                # 能站的窗口按新狗的 fit_m 重拼（不重问系统）
        roam = self.roam
        roam.land_now()
        roam.facing = -1.0 if math.cos(math.radians(self.dog.yaw)) < 0 else 1.0
        if roam.moved:
            w.place_scene(roam.wx, roam.wy)
        self.things.pet_changed()
        self._tread()
        self.dog.perch = self._perch_to                           # 踩在狗窝的垫子上：这一帧就抬好，不从地上缓上去
        self._ensure_ring_windows()

    def _end_lift_now(self) -> None:
        if self.roam.lifted:
            self.roam.lifted = False
            self.dog.puppet_end()
        self.dog.lift.cut()

    def fail_safe(self) -> None:
        """出错兜底（window._frame 抓到异常时调）：狗交回控制器、球收起来、灵动交互这一块停掉，别的照常。"""
        self.active = False
        try:
            self._end_lift_now()
            self.roam.task, self.roam.route, self.roam.leg = None, [], None
            self.roam.carrying = False
            self.dog.shut_mouth = self.dog.hide_shadow = False
            self.dog.props.item = None
            self.dog.props.active = None
            self.dog.puppet_end()
            self.dog.expr.reset()
            self.dog.expr.release()
            self.dog.lounge = None
            self._nest = self._nest_going = self._eating = self._pad = None
            self._perch_to = self.dog.perch = 0.0
        finally:
            if self.ball_win is not None:
                self.ball_win.hide()
            self.things.fail_safe()
            self._put_ring_away()

    def _put_ring_away(self) -> None:
        """圈当场收起来（停掉灵动交互、出错兜底）。"""
        if self._charging:
            self._charging = False
            self.ball_bank.fade("charge")
        self.ring.clear()
        self._ring_at = None
        for rw in self.ring_wins.values():
            rw.put_away()

    def _ensure_ring_windows(self) -> None:
        """每块屏一个圈的窗口（和每块屏画另一半狗的窗口一样，按屏的名字记）：屏拔了收掉，接了新屏建一个。
        原生窗口这时就建好（winId），先不显示：第一次拿球时不现建（建一个原生窗口要等窗口系统）。"""
        prepare_ring(self.tune["ring_size"] * self.roam.height_m * self.ppm, sticker.is_dark())   # 墨环两层先在空的时候一帧画一点（共约 30 毫秒）：第一次拿球不现画
        screens = {s.name(): s for s in QGuiApplication.screens()}
        for name in [n for n in self.ring_wins if n not in screens]:
            rw = self.ring_wins.pop(name)
            rw.put_away()
            rw.deleteLater()
        for name, s in screens.items():
            rw = self.ring_wins.get(name)
            if rw is None:
                rw = self.ring_wins[name] = RingWindow(s)
                rw.winId()
            rw.home = s

    def rebuild_world(self) -> None:
        screens = QGuiApplication.screens()
        areas = [Area(g.x(), g.y(), g.x() + g.width(), g.y() + g.height(), s.name()) for s in screens for g in (s.availableGeometry(),)]
        full = [Area(g.x(), g.y(), g.x() + g.width(), g.y() + g.height(), s.name()) for s in screens for g in (s.geometry(),)]
        self.world = World(areas, FLOOR_MARGIN_PX * self.w.world_scale, full)
        self._sups = None
        self._frames_at = -math.inf

    def floor_changed(self) -> None:
        """屏幕的可用区域变了（程序坞出来、收起来：苹果有时回到桌面程序坞不出来，等它出来了狗和球还踩在程序坞上）：
        空间重建；站在程序坞那一带的狗跳上去（roam.floor_changed），停在那一带的球弹一下落到新地面上；地面降了，狗和球照常掉下去。"""
        if not self.active:
            return
        self.rebuild_world()
        self.roam.floor_changed()
        self.things.floor_changed()
        b = self.ball
        if b is None or self.carried or self.ball_held or not (b.resting or b.rolling):
            return
        above = self.world.floor_above(b.x, b.y + b.r)
        if above is not None:
            rise = b.y + b.r - above.y + 0.8 * b.r                     # 弹得比新地面高一点，落下来
            b.on = None
            b.throw(0.0, -math.sqrt(2.0 * GRAVITY_M * self.ppm * rise), self.ppm)
        elif self.world.floor_at(b.x, b.y + b.r) is not None:
            b.on = None
            b.rolling = b.resting = False                              # 地面降了：掉下去

    def screens_changed(self) -> None:
        """接上 / 拔掉显示器、改分辨率：空间重建；狗、球不在任何一块屏的线上就落到下面。"""
        if not self.active:
            return
        self.rebuild_world()
        self._ensure_ring_windows()
        if not self.roam.busy and not self.roam.lifted:
            self.roam.place(*self.w.scene_world())
            self.roam.drop_to_support()
        if self.ball is not None and not self.carried and self.world.room_at(self.ball.x, self.ball.y) is None:
            f = self.world.nearest_floor(self.ball.x, self.ball.y)
            self.ball.x, self.ball.y = f.clamp(self.ball.x, self.ball.r), f.y - self.ball.r
            self.ball.resting, self.ball.on = True, (f.kind, f.key)
        self.things.screens_changed()

    def scale_changed(self) -> None:
        """狗缩放了：地面离底边的距离、球的大小跟着变。狗的脚贴回它站的那条线（以前跑着调大小，停下来会凭空"落地"一下；
        窗口按狗的中心缩放，脚会挪开，这里把窗口挪回去），正在走的路按新大小重排。roam 记着缩放前狗的根在哪（每帧从窗口读，或它自己在挪）。"""
        if not self.active:
            return
        self.rebuild_world()
        self.things.scale_changed()                               # 物件等大小停稳了再重排、重出图
        self._predicted = None                                    # 重力按新大小算了：球的落点重算
        if self.ball is not None:
            self.ball.r = BALL_R * self.ppm
            if self.ball.resting and self.ball.on is not None and self.ball.on[0] == "floor":
                f = self.world.floor_at(self.ball.x, self.ball.y - 50) or self.world.nearest_floor(self.ball.x, self.ball.y)
                self.ball.y = f.y - self.ball.r
        roam = self.roam
        if roam.lifted:
            return                                                # 拎着：位置听手的
        if roam.support is None and not roam.busy:
            roam.place(*self.w.scene_world())
        roam.reseat()
        if not roam.busy and roam.support is None:
            roam.settle_support()
        self.w.place_scene(roam.wx, roam.wy)

    def _spawn_ball(self) -> None:
        """球放在狗前面（朝屏幕中间那边）、狗那条线上；放不下就放在狗脚下那条线的另一边。"""
        from widget.ball import BallWindow
        r = BALL_R * self.ppm
        d = -1.0 if math.cos(math.radians(self.dog.home_yaw)) < 0 else 1.0
        s = self.roam.support or self.roam.here()
        x = self.roam.wx + d * self.ppm * 0.62
        if not s.covers(x, r):
            x = self.roam.wx - d * self.ppm * 0.62
        x = s.clamp(x, r)
        self.ball = Ball(x, s.y - r, r, on=(s.kind, s.key))
        if self.ball_win is None:
            self.ball_win = BallWindow(self)
        self.carried = False
        self._sync_ball()
        self.ball_win.alpha = 0.0
        self.ball_win.show()
        self._fade_ball(1.0, 260)

    def ball_out_changed(self) -> None:
        """小球拿出来 / 收起来了（window.set_ball_out）。收起来：圈原地淡掉，追着的停下，叼着的嘴里的球没了（不放下），按着的松开，
        球的小窗口 0.22 秒淡掉；之后没有球（fetch_on 是假的），狗就没球玩。拿出来：放在狗前面（_spawn_ball，和开灵动交互一样）。
        灵动交互关着什么都不做：start 照 window.ball_out 来。"""
        if not self.active:
            return
        if self.w.ball_out:
            if self.ball is None:
                self._spawn_ball()
            return
        if self.ball is None:
            return
        self.roam.lose_ball()                                     # 嘴里的球跟着收：道具一起没了
        self.ring.stop()
        self.ball_held = False
        self._tap = None
        self._lost.reset()
        self.ball_duang.release()
        self.carried = False
        self.ball = None
        self.throw_id += 1
        if self.ball_win is not None and self.ball_win.isVisible():
            self._fade_ball(0.0, 220)

    def _fade_ball(self, to: float, ms: int) -> None:
        self._ball_fade.stop()
        self._ball_fade.setDuration(ms)
        self._ball_fade.setStartValue(self.ball_win.alpha if self.ball_win is not None else 0.0)
        self._ball_fade.setEndValue(to)
        self._ball_fade.start()

    def _set_ball_alpha(self, v) -> None:
        if self.ball_win is not None:
            self.ball_win.alpha = float(v)
            self.ball_win.update()

    def _ball_fade_done(self) -> None:
        if self.ball_win is not None and self.ball_win.alpha <= 0.01:
            self.ball_win.hide()

    # ---------- 每帧 ----------
    def update(self, dt: float, hold: bool = False) -> None:
        """每帧。hold：看细节临时放大着（window.closeup.zoomed）——roam 整个停住、狗的根不从窗口读（窗口里画的是放大、挪开了的狗），
        球照常飞、照常滚。"""
        if not self.active or self.world is None:
            return
        self._prev_frames = {k: v for k, v in self._tick_frames.items() if v is not None}
        self._tick_frames = {}
        if not hold and not self.roam.busy and not self.w.dragging and not self.roam.lifted:
            wx, wy = self.w.scene_world()
            if self.roam.support is None or self.roam.support.kind != "window":
                self.roam.place(wx, wy)
        if self.dog.expr.pressing and self.w._drag is None:
            self.dog_unpress()                                    # 按着的时候窗口丢了鼠标（切走了、系统弹窗）：没有松手事件，也要弹回来
        self.ball_duang.step(dt)
        self._check_tap(dt)
        self._check_lost_release(dt)
        self._hold_ball(dt)
        self._step_ball(dt)
        self._now += dt
        self._step_glance(dt)
        self.things.update(dt)                                    # 一件没摆什么都不碰
        self._feed_lift()
        self._step_ring(dt)                                       # 在 roam 前面：圈满的这一帧狗就接着叫、俯身
        self._step_still(dt)                                      # 鼠标停着多久了：_wander 和窗口这一帧看不看你按它
        self._lounge(dt)
        self._wander(dt)
        self.roam.update(dt, hold)
        if not hold:
            self._tread()                                         # 狗这一帧走到哪了：脚下是不是狗窝的垫子
            self._bowl_front()                                    # 在这个盆吃喝、头低着：盆沿近的那半圈盖在狗前面
        if self.dog.perch != self._perch_to:
            self._step_perch(dt)
        if not hold and not self.dog.on_turntable:
            self._check_cover()                                   # 站在转台上（看细节）不跳下被盖住的窗口
        self._express(dt)
        self._sync_ball()
        self._sync_ring()

    def live_windows(self) -> list:
        """看得见的球、捡球的圈、物件的窗口（狗那一层，window.live_windows）。"""
        wins = [rw for rw in self.ring_wins.values() if rw.isVisible()]
        if self.ball_win is not None and self.ball_win.isVisible():
            wins.append(self.ball_win)
        return wins + self.things.live_windows()

    def quiet(self) -> bool:
        """什么都没在动：狗没在跑、没被拎着，球停在原地、没人拿、没在淡入淡出，球的 duang 弹完了，圈看不见了，物件没在拖、没在落。
        窗口按它定待着时能不能少画（window._pace）；球跟着脚下的窗口挪也算在动。"""
        roam, b = self.roam, self.ball
        if roam.busy or roam.lifted or roam.moved or self.ball_held or self._tap is not None or self.ring.alpha > 0.0:
            return False
        if not self.things.quiet() or self.dog.perch != self._perch_to:
            return False
        if self.ball_duang.pressing or self.ball_duang.value != 0.0 or self._ball_fade.state() == QVariantAnimation.Running:
            return False
        if b is not None and not self.carried:
            at = (b.x, b.y, b.spin)
            if not b.resting or at != self._ball_seen:
                self._ball_seen = at
                return False
        return True

    def after_pose(self) -> None:
        """这一帧的姿势定下来了（窗口画完 dog.frame 调）：跳的时候狗按真实的姿势摆。"""
        if self.active:
            self.roam.after_pose()

    def _ball_headroom(self) -> float:
        return BALL_HEADROOM_R * (self.ball.r if self.ball is not None else BALL_R * self.ppm)

    def _ball_phys(self) -> BallPhysics:
        t = self.ball_tune
        return BallPhysics(e_floor=t.get("e_floor", 0.52), e_wall=t.get("e_wall", 0.62), roll_gain=t.get("roll", 1.0))

    def _step_ball(self, dt: float) -> None:
        b = self.ball
        if b is None or self.carried or self.ball_held:
            return
        on_window = b.on is not None and b.on[0] == "window" and (b.resting or b.rolling)
        platforms: list[Support] = []
        if on_window:                                             # 停 / 滚在窗口上：窗口挪了跟着挪；窗口没了就掉下去
            key = b.on[1]
            left = self.window_left(key) if self.window_listed(key) else None
            if left is not None and self._ball_ride is not None and self._ball_ride[0] == key:
                b.x += left - self._ball_ride[1]
            top = self.window_top(key, at_x=b.x, headroom=self._ball_headroom()) if left is not None else None
            if top is None or not top.covers(b.x):
                b.resting = b.rolling = False
                b.on = None
                self._ball_ride = None
            else:
                b.y = top.y - b.r
                platforms = [top]
                self._ball_ride = (key, left)
        else:
            self._ball_ride = None
        if not b.resting and not on_window:
            platforms = self.ball_platforms()
        b.impact = 0.0
        vx = b.vx
        events = step_ball(self.world, b, dt, self.ppm, platforms, self.ball_edges() if not b.resting else (), self._ball_phys())
        self._ball_clock += dt
        if self._turned(vx, b.vx):
            self.ball_turns += 1
        if "floor" in events or b.on is not None:                 # 记下球这一扔碰过哪条线（狗等它真落到那一层再跳过去）
            line = b.on
            if line is None:                                      # 弹了一下：b.on 只在滚、停的时候才有；它弹在正下方最近的那条线上
                s = support_below(list(self.world.floors) + platforms, b.x, b.y)
                line = (s.kind, s.key) if s is not None else None
            if line is not None:
                self._ball_touch = (self.throw_id, line)
        if "window" in events:
            self._ball_hit_window()
        if b.impact > 0.0:
            self._ball_sound(b.impact / self.ppm)

    def _ball_sound(self, speed_m: float) -> None:
        """球撞到东西：越快越响；太慢的不响（贴地跳的最后几下、滚）。两次太近的跳过（包里的 min_gap）。"""
        if speed_m < BOUNCE_MIN_M:
            return
        k = (speed_m - BOUNCE_MIN_M) / (BOUNCE_FULL_M - BOUNCE_MIN_M)
        self.ball_bank.play("bounce", 0.18 + 0.82 * min(1.0, k) ** 0.7)

    def _ball_hit_window(self) -> None:
        """球撞到窗口边上弹回来：狗耳朵一抖、身子一缩（头本来就跟着球转）。"""
        if self.carried:
            return
        e = self.dog.expr
        e.ear_flick(0.3, 0.55)
        e.bob(0.02, 0.16)
        self.dog.excite.kick(excite.KICK_BOUNCE)

    def _check_cover(self) -> None:
        """站在窗口上：脚下那一截被别的窗口盖住了（你点了别的窗口）就跳下来。"""
        s = self.roam.support
        if s is None or s.kind != "window" or self.roam.busy or s.key < 0:   # 摆着的台子不会被别的窗口盖住（它画在所有窗口上面）
            return
        now = time.perf_counter()
        if now - self._cover_at < COVER_EVERY:
            return
        self._cover_at = now
        covered = native.window_covered(s.key, self.roam.wx, s.y + 3, self._pid)
        if covered:
            self.roam.descend()

    # ---------- 自己歇着（活跃度低的狗） ----------
    def _lounge(self, dt: float) -> None:
        """每帧：没人理一阵子自己坐下、再过一阵趴下（dog.set_lounge）；有人跟它玩就起来。两件事分开问：
        _can_lounge「现在能不能歇」（有人在跟它玩就不能）、_lounge_wish「没人理了这么久，该歇成什么姿势」（歇的计划只从 _rest_plan 一处取）。
        不自己歇的狗（边牧，计划是 None）没摆窝时下面一行都不走，dog.lounge 一直是 None。
        摆了窝（things.has_nests）：到第一次该歇的时候先看有没有够得着的窝，有就走过去直接趴下（_try_nest → roam → _roam_done → settle_in），
        没有就照没摆窝的来。已经在原地歇着的（dog.lounge 不是 None）不为了新摆的窝起来，下次歇再去。"""
        dog, roam = self.dog, self.roam
        nests = self.things.has_nests()
        if self._rest_plan() is None and dog.lounge is None and not nests and self._nest is None:
            return
        if dog.on_turntable:                                      # 看细节：自己的事都停——歇着的不起来、站着的不坐下，钟也不走
            if self._nest is not None and (roam.busy or roam.lifted):
                self._leave_nest()                                # …但真被牵走、拎走了：垫子的高度、前沿不留在身上
            return
        if roam.task == "nest":                                   # 正往窝走：自己的事，不算有人跟它玩；真有人来玩了（拿起球、球动了）就不去了
            if self.ball_held or self._tap is not None or not self._ball_still():
                self._nest_going = None
                self._idle_for = 0.0
                roam.call_off()
            return
        if not self._can_lounge():                                # 有人在跟它玩：钟归零，该待的姿势回到站着（roam 接管时自己会让它站起来）
            self._idle_for = 0.0
            if self._seated_play():
                self._rest_as("sitting")                          # 默认坐着的狗：拿起球、球在动叫醒它时回到坐着（窝里的就在窝里坐起来）
            else:
                self.rouse()
            return
        self._idle_for += dt
        self._nest_wait = max(0.0, self._nest_wait - dt)
        if self._nest is not None:                                # 歇在窝里：一直趴着
            return
        want = self._lounge_wish(self._idle_for)
        sits = temper.sits_by_default(self.tune)
        homing = nests and (dog.lounge is None or (sits and dog.lounge == "sitting")) and self._idle_for >= self._nest_after()   # 该回窝了（还站着的、默认坐着的狗坐着的才去）
        if (want != dog.lounge or homing) and (dog.phase != "idle" or dog.steps):
            return                                                # 正做着随机动作、正换姿势：做完再换（再去窝），不一刀切
        if homing and self._try_nest():
            return
        self._rest_as(want)

    def _rest_as(self, posture: Optional[str]) -> None:
        """自己歇成 posture（dog.set_lounge）。要坐下、趴下了才问朝哪（_rest_face）。"""
        if posture != self.dog.lounge:
            self.dog.set_lounge(posture, None if posture is None else self._rest_face())

    def _rest_face(self) -> Optional[float]:
        """歇下来朝哪：歇在尖顶狗屋门口的照门朝外（spot.yaw；门朝哪按狗屋在它那块屏的哪半边，和靠边不一定一致）；
        别的靠边的朝所有屏合起来的中间（window._edge_yaw）；中间那一半 None，照旧。"""
        spot = self._nest
        if spot is not None and spot.yaw is not None:
            return spot.yaw
        return self.w._edge_yaw()

    # ---------- 自己溜达 ----------
    def _reset_wander(self) -> None:
        """下一趟从头计时：temper.wander_every 里随便挑一个。"""
        lo, hi = temper.wander_every(self.tune)
        self._wander_in = self._rng.uniform(lo, hi)

    @property
    def hushed(self) -> bool:
        """这会儿狗的片段声音不响（window 每帧问）：自己溜达过去吃两口的时候（没人跟它玩，嚼、舔水的声音不响）。"""
        return self._sipping and self.roam.task == "eat"

    def _end_wander(self) -> None:
        """溜达、吃两口不做了（有人来玩、摆了东西叫它）：就地站住，下一趟重新计时。"""
        roam = self.roam
        if roam.task == "wander" or (roam.task == "eat" and self._sipping):
            if roam.task == "eat":
                self._eating = None
            roam.call_off()
        self._sipping = False
        self._reset_wander()

    # ---------- 鼠标停着就不看 ----------
    def _step_still(self, dt: float) -> None:
        """每帧：鼠标停着多久了。离上次算「动了」的地方挪过 POINTER_STILL_PX 算动；你在跟它玩（拿着、按着球，球在动，拎着拖着狗，
        它在捡球、叼回来）也算动，所以叼回球放下以后还看你一阵。它自己的事（溜达、回窝、吃两口）不算。"""
        cx, cy = self.cursor()
        seen = self._cursor_seen
        moved = seen is None or math.hypot(cx - seen[0], cy - seen[1]) > POINTER_STILL_PX
        if moved:
            self._cursor_seen = (cx, cy)
        roam = self.roam
        if moved or self.ball_held or self._tap is not None or not self._ball_still() or roam.lifted or self.w.dragging \
                or roam.task == "fetch":
            self._still_for = 0.0
        else:
            self._still_for += dt

    @property
    def watching_you(self) -> bool:
        """狗还看着你（鼠标）：鼠标停着不到调参 look_idle_s 秒（边牧 10、萨摩耶 7）。停够了就自己做自己的事：头回正、身子不跟着鼠标换边
        （window._look_target）、停下来朝哪就朝哪（window._home_yaw）、停在旁边的鼠标不挡它溜达（_you_are_near）。鼠标一动马上回来看。
        看球不归它管（look_point）：球在你手上、在动本来就算动。"""
        return self._still_for < self.tune.get("look_idle_s", LOOK_IDLE_S)

    def _you_are_near(self) -> bool:
        """你在跟前：卡片开着（你在调设置，狗别从卡片底下走过）、「···」出着、鼠标在狗身上或离它一个身高以内（你要伸手了）。
        鼠标停在旁边一阵了不算（狗已经不看你了，watching_you）：停着的鼠标不挡它溜达。"""
        w, roam = self.w, self.roam
        panel = getattr(w, "settings_panel", None)
        if (panel is not None and panel.isVisible()) or w.hover.active:
            return True
        if not self.watching_you:
            return False
        cx, cy = self.cursor()
        h = roam.height_m * self.ppm
        return math.hypot(cx - roam.wx, cy - (roam.wy - 0.5 * h)) < h

    def _wander_waits(self) -> bool:
        """现在不该开始走（也不往下数）：你在跟前、正做随机动作或换姿势、正演着呆萌的来回看。"""
        dog = self.dog
        return self._you_are_near() or dog.phase != "idle" or bool(dog.steps) or dog.transition or self.glancing

    def _wander(self, dt: float) -> None:
        """每帧（_lounge 之后、roam 之前）：没人理就数着，到点走一趟（_start_wander）。有人来玩（球在手上、按着、在动，拎着拖着，roam 在做别的事）：
        钟和拴的那一点都重来（闲下来那一刻站哪就拴哪）；走着的时候有人伸手过来、打开卡片：就地站住。"""
        roam, dog = self.roam, self.dog
        own = roam.task == "wander" or (roam.task == "eat" and self._sipping)
        playing = self.ball_held or self._tap is not None or not self._ball_still() or roam.lifted or self.w.dragging \
            or (roam.busy and not own) or dog.on_turntable
        if playing:
            if own:
                self._end_wander()
            self._wander_anchor = None
            self._sipping = False
            self._reset_wander()
            return
        if own:
            if roam.task == "wander" and self._you_are_near():
                self._end_wander()                                # 你伸手过来、打开卡片：就地站住
            return
        if self._wander_anchor is None and roam.support is not None:
            s = roam.support
            self._wander_anchor = (s.kind, s.key, roam.wx)
        if self._wander_waits():
            return
        lying = dog.lounge == "lying" or self._nest is not None
        self._wander_in -= dt / (temper.WANDER_LYING_GROW if lying else 1.0)
        if self._wander_in > 0.0:
            return
        if not self._start_wander():
            self._wander_in = WANDER_RETRY_S

    def _start_wander(self) -> bool:
        """到点了：摆着满盆、够得着就按 WANDER_SIP_P 去吃两口；不然在脚下这条线上挑个地方走过去（_wander_target）。走成了返回 True。"""
        roam = self.roam
        s = roam.support
        if s is None:
            return False
        if self._try_sip(s):
            return True
        x = self._wander_target(s)
        if x is None or not roam.wander(s, x):
            return False
        self.rouse()                                              # 歇着的起来：在窝里的根、前沿收掉（roam 已经接手，只是记下）
        return True

    def _try_sip(self, s: Support) -> bool:
        """同一条线上 WANDER_SIP_M 以内有满盆：按 WANDER_SIP_P 过去吃两口（不出声、盆不变空）。"""
        roam, ppm = self.roam, self.ppm
        bowls = []
        for key, t in self.things.items.items():
            if t.serves is None or not t.full or t.on != (s.kind, s.key):
                continue
            spot = self.things.bowl_spot(key)
            if spot is not None and abs(spot[1] - roam.wx) <= WANDER_SIP_M * ppm:
                bowls.append((key, spot))
        if not bowls or self._rng.random() >= WANDER_SIP_P:
            return False
        key, spot = self._rng.choice(bowls)
        self._eating, self._sipping = key, True
        if not roam.eat(*spot, bark=False, sip=True):
            self._eating, self._sipping = None, False
            return False
        self.rouse()
        return True

    def _wander_target(self, s: Support) -> Optional[float]:
        """这一趟走到哪（全局 x，同一条线上）：走多远照 temper.wander_reach（从窝里起来的走出窝 WANDER_NEST_OUT），随便挑一边——离拴的那一点
        超过半根绳就往回走；夹在线头（roam.margin）和绳长里；停的地方要是在物件上（左右再留 WANDER_CLEAR_M），挪到它外面那一头。不够 WANDER_MIN_M 换一边，
        两边都不行 None。"""
        roam, ppm, rng = self.roam, self.ppm, self._rng
        lo, hi = WANDER_NEST_OUT if self._nest is not None else temper.wander_reach(self.tune)
        dist = rng.uniform(lo, hi) * ppm
        x0 = roam.wx
        a = self._wander_anchor
        ax = a[2] if a is not None and (a[0], a[1]) == (s.kind, s.key) else x0
        leash = WANDER_LEASH_M * ppm
        m = roam.margin(s)
        left, right = max(s.x0 + m, ax - leash), min(s.x1 - m, ax + leash)
        first = -1.0 if x0 > ax + 0.5 * leash else 1.0 if x0 < ax - 0.5 * leash else rng.choice((-1.0, 1.0))
        for d in (first, -first):
            x = min(max(x0 + d * dist, left), right)
            x = self._clear_of_things(s, x, d, left, right)
            if x is not None and abs(x - x0) >= WANDER_MIN_M * ppm:
                return x
        return None

    def _clear_of_things(self, s: Support, x: float, d: float, left: float, right: float) -> Optional[float]:
        """停在 x 会不会站在物件上（同一条线上的狗窝、狗屋、盆，左右再留 WANDER_CLEAR_M）：会的话挪到它往 d 那边的外头；挪出了 [left, right] 就 None。"""
        clear = WANDER_CLEAR_M * self.ppm
        for _ in range(4):                                        # 挪出一件可能又踩上旁边那件：最多挪几次
            hit = None
            for t in self.things.items.values():
                if t.lay is None or t.state not in ("rest", "tap") or t.on != (s.kind, s.key):
                    continue
                a, b = t.span()
                if a - clear <= x <= b + clear:
                    hit = (a - clear, b + clear)
                    break
            if hit is None:
                return x if left <= x <= right else None
            x = hit[1] + 1.0 if d > 0 else hit[0] - 1.0
            if not left <= x <= right:
                return None
        return None

    def _nest_after(self) -> float:
        """没人理多久回窝（temper.nest_after）：自己歇的狗是原来该坐下的那一刻（萨摩耶 20 秒），不自己歇的（边牧）temper.NEST_AFTER_S。"""
        return temper.nest_after(self.tune)

    def _seated_play(self) -> bool:
        """默认坐着的狗、这会儿有人跟它玩、但没被牵着走（拿着球、按着球、球在动）：坐着玩，不站起来。"""
        roam = self.roam
        return temper.sits_by_default(self.tune) and not (roam.busy or roam.lifted or self.w.dragging)

    def _ball_still(self) -> bool:
        b = self.ball
        return b is None or self.carried or b.resting

    def nest_spot(self) -> Optional[NestSpot]:
        """现在摆着、狗够得着的窝里最近的一个（things.nest_spots 里挑：路线排得通、离狗最近）；没有 None。"""
        roam, best = self.roam, None
        for spot in sorted(self.things.nest_spots(), key=lambda n: math.hypot(n.x - roam.wx, n.support.y - roam.wy)):
            if roam.route_to(spot.support, spot.x).reachable:
                best = spot
                break
        return best

    def _try_nest(self) -> bool:
        """该回窝了：有够得着的窝就让 roam 走过去，返回去没去成。没去成 NEST_RETRY_S 秒内不再看（排路线不便宜）。"""
        if self._nest_wait > 0.0:
            return False
        self._nest_wait = NEST_RETRY_S
        spot = self.nest_spot()
        if spot is None or not self.roam.go_nest(spot.support, spot.x, spot.yaw):
            return False
        self._nest_going = spot
        self._nest_wait = 0.0
        return True

    def _roam_done(self, task: str) -> None:
        """roam 做完一件事（roam.on_done）：走回窝的走到了——窝还在原处、狗真站在那一点上、这会儿没人跟它玩，就趴下。
        自己溜达完、吃完两口：下一趟重新计时。"""
        if task == "eat":
            self._eating = None
            if self._sipping:
                self._sipping = False
                self._reset_wander()
        if task == "wander":
            self._reset_wander()
        if task != "nest":
            return
        spot, self._nest_going = self._nest_going, None
        roam = self.roam
        if spot is None or self.ball_held or self._tap is not None or not self._ball_still() or self.dog.on_turntable:
            return
        s = roam.support
        if s is None or (s.kind, s.key) != (spot.support.kind, spot.support.key) or abs(roam.wx - spot.x) > NEST_NEAR_M * self.ppm \
                or not self.things.spot_holds(spot):
            return
        self.settle_in(spot)

    def settle_in(self, spot: NestSpot, posture: str = "lying") -> None:
        """狗到窝了：歇成 posture（直接趴下，不先坐）。根缓到垫子那么高（dog.perch），歇在垫子上的不画影子（影子会画在窝后面的地上），
        窝的前沿盖到狗前面。朝哪 roam 到的时候已经转好了（go_nest、home_yaw_here）：狗屋门口的朝门外（spot.yaw），狗窝、平顶狗屋靠边的朝中间（window._edge_yaw，趴下时再对一次）。"""
        dog = self.dog
        self._nest = spot
        self._perch_to = spot.perch_m
        if spot.perch_m > 0.0:
            dog.hide_shadow = True
        self.things.show_front(spot.key)
        dog.set_lounge(posture, self._rest_face())
        self._curl_tail(spot)

    def _curl_tail(self, spot: NestSpot) -> None:
        """歇进狗窝（有垫子、有窝壁的）：尾巴往身子这边卷（边牧趴在窝里尾巴穿过窝壁），卷多少按模型和这个窝量（dog.tail_curl：
        尾巴尖落在窝的内沿里面，再留 CURL_MARGIN_M）；往靠镜头那一侧卷（绕在近处的后腿边上；往远的那一侧卷尾巴反而往后伸）。萨摩耶的尾巴卷在背上，量出来是 0。
        狗屋（趴在门口，狗画在屋前面）不卷。"""
        half = self.things.pad_half_m(spot.key)
        dog = self.dog
        if half is None or spot.perch_m <= 0.0:
            dog.expr.curl = 0.0
            return
        inner = max(0.05, half - CURL_MARGIN_M)
        curl = dog.tail_curl(inner, toward_camera=True)            # 往远的那一侧卷尾巴反而往后伸（量过），只往靠镜头那一侧卷
        right = math.cos(math.radians(dog.home_yaw)) >= 0.0           # 歇着朝右（home_yaw：这会儿可能还在转过去）：模型的 −X 靠镜头；朝左反过来
        dog.expr.curl_side = -1.0 if right else 1.0
        dog.expr.curl = curl

    def rouse(self) -> None:
        """狗该起来了（有人跟它玩、窝被拿走）：该待的姿势回到站着；歇在窝里的根缓回去、影子回来、前沿收掉。"""
        self.dog.set_lounge(None)
        if self._nest is not None or self._nest_going is not None:
            self._leave_nest()

    def _leave_nest(self, now: bool = False) -> None:
        """不在窝里了：根落回线上（now：当场，不缓）、影子回来、前沿收掉。起来以后还站在垫子上的，这一帧后面 _tread 接着让它踩在垫子上。"""
        if self._nest is not None:
            if self._nest.perch_m > 0.0:
                self.dog.hide_shadow = False
            self._nest = None
            self.dog.expr.curl = 0.0                              # 起来：尾巴缓回去
        self._nest_going = None
        self._pad = None
        self._perch_to = 0.0
        if now:
            self.dog.perch = 0.0
        self.things.hide_front(now)

    def nest_gone(self, key: str) -> None:
        """这个窝离开原地了（被拿起、收起、落下去、挪了；things 叫）：歇在里面的狗站起来，正往这走的站住。钟归零：下次该歇了再去。"""
        if self._nest is not None and self._nest.key == key:
            self._idle_for = 0.0
            self.rouse()
        if self._nest_going is not None and self._nest_going.key == key:
            self._nest_going = None
            self._idle_for = 0.0
            self.roam.call_off()

    # ---------- 摆下去马上有反应、踩着窝过去 ----------
    def _free(self) -> bool:
        """狗闲着：没任务、没被拎着拖着、球不在你手上（也没被按着）也没在动、不在转台上。物件刚落定时看它：闲着才过来（thing_placed）。"""
        return self.active and self._can_lounge() and not self.dog.on_turntable

    def thing_placed(self, key: str) -> None:
        """这一件刚从「物件」页摆出来落定、或者你拖完松手落定了（things 叫；重开、开灵动交互回原处的，脚下的窗口没了落下去的不算）：
        狗闲着（_free）就过来——满着的盆：吃 / 喝一次（和敲盆同一条路；够不着就算了，没人叫它不过去叫）；窝：走过去趴进去，不等该歇的时候，
        去的是刚放下的这一个（正在原地歇着、歇在别的窝里的也起来过去；够不着就算了）。忙着就算了：窝等到该歇的时候再回（_lounge），盆等你敲。空盆不叫它。"""
        self._end_wander()                                        # 自己溜达着的、吃着两口的：先站住（算闲着）
        if not self._free():
            return
        things = self.things
        if things.bowl_full(key):
            self.bowl_tapped(key, bark=False)
            return
        spot = things.nest_spot(key)
        if spot is None or not self.roam.go_nest(spot.support, spot.x, spot.yaw):
            return
        self.rouse()                                              # 正歇着的：该待的姿势回到站着（roam 已经接手，只是记下），在别的窝里的根、前沿收掉
        self._nest_going = spot
        self._nest_wait = 0.0

    def _tread(self) -> None:
        """每帧（roam 走完这一帧以后）：狗脚下是不是狗窝的垫子。狗在线上跑、走、站（roam.afoot），身子正中进了哪个狗窝垫子的范围（things.pad_at）：
        根往垫子那么高缓（dog.perch，和歇进窝同一根，PERCH_S）、那个窝的前沿盖到脚前面；出了范围、窝被拿走：落回线上、前沿收掉。
        根抬着的时候不画影子（dogctl.frame）。跳、掉、被拎、被扔，低头叼球、放球、吃喝时不抬。歇在窝里（_nest）的听 settle_in 定的，这里不管。
        前沿的窗口只在踩上、离开那一下显示 / 收掉，踩着不动时每帧什么都不碰。一件没摆时两行就出去。"""
        if self._nest is not None:
            return
        roam, pad = self.roam, None
        if self.things.items and roam.afoot:
            pad = self.things.pad_at(roam.support.kind, roam.support.key, roam.wx)
        key = pad[0] if pad is not None else None
        if key != self._pad:
            self._pad = key
            if key is None:
                self.things.hide_front()
            else:
                self.things.show_front(key)
        self._perch_to = pad[1] if pad is not None else 0.0

    # ---------- 吃喝（摆着的饭盆、水盆） ----------
    def bowl_tapped(self, key: str, bark: bool = True) -> bool:
        """敲了一下盆（things：点一下、没算拿起就松手；盆已经添满了）：叫狗过去吃 / 喝，返回它来不来。每点一次都来。
        不来的时候：被拎着拖着、在空中、球在你手上、在捡球（追着、叼着）、掉着、被叫去别处、站在转台上，已经在往这个盆来 / 正吃着它；盆踩的线站不下狗。
        在窝里的起来过去；正走回窝、正吃着另一个盆的改道（跳到一半的不改）。够不着：走到最近的地方叫两声（roam.eat）；
        bark=False（满盆刚落定，thing_placed：没人叫它）够不着就不去也不叫。"""
        roam, dog = self.roam, self.dog
        if not self.active or roam.lifted or roam.airborne or self.w.dragging or dog.on_turntable or self.ball_held or self._tap is not None:
            return False
        if roam.task == "wander" or (roam.task == "eat" and self._sipping):
            self._end_wander()                                    # 自己溜达着、吃着两口：你敲盆了，正经来吃
        if roam.task not in (None, "nest", "eat") or (roam.task == "eat" and self._eating == key):
            return False
        spot = self.things.bowl_spot(key)
        if spot is None:
            return False
        roam.call_off()
        if roam.task is not None:
            return False
        self._nest_going = None
        self._eating = key
        roam.eat(*spot, bark=bark)
        if roam.task != "eat":
            self._eating = None                                   # 这只狗没有吃喝的动作
        return roam.task == "eat"

    def nest_tapped(self, key: str) -> bool:
        """点了一下这个窝（狗窝、狗屋；things：没算拿起就松手：点哪个窝狗就去哪个）：狗走过去趴进这一个
        （和「摆下去马上有反应」同一条路：roam.go_nest → _roam_done → settle_in），在别的窝里的起来过去，正往别的窝走、正吃着的改道，
        已经趴在这一个里的、正往这一个走的不动。被拎着拖着、在空中、球在你手上（按着）、在捡球、被叫去别处、掉着、站在转台上：不来，窝只 duang。
        萨摩耶默认坐着也一样：点了就站起来去。够不着不去也不叫。返回来不来。"""
        roam, dog = self.roam, self.dog
        if not self.active or roam.lifted or roam.airborne or self.w.dragging or dog.on_turntable or self.ball_held or self._tap is not None:
            return False
        if roam.task == "wander" or (roam.task == "eat" and self._sipping):
            self._end_wander()
        if roam.task not in (None, "nest", "eat"):
            return False
        if (self._nest is not None and self._nest.key == key) or (self._nest_going is not None and self._nest_going.key == key):
            return False
        spot = self.things.nest_spot(key)
        if spot is None or not roam.route_to(spot.support, spot.x).reachable:
            return False
        roam.call_off()                                           # 正往别的窝走、正吃着：站住（跳到一半的跳完再说：这一下不来）
        if roam.task is not None:
            return False
        self._eating = None
        if not roam.go_nest(spot.support, spot.x, spot.yaw):
            return False
        self.rouse()                                              # 歇着的起来：在别的窝里的根、前沿收掉（roam 已经接手，只是记下）
        self._nest_going = spot
        self._nest_wait = 0.0
        return True

    def _bowl_front(self) -> None:
        """每帧（_tread 之后）：狗在这个盆吃 / 喝、头低着的那几段（转正、低头、吃喝；roam 的 eat 走到盆边以后），这个盆的前沿（包里 front_z：
        盆中心往镜头那半圈盆沿）盖在狗前面——嘴和舌头在近处那半圈盆沿后面（像在盆外面吃）；抬头（盆这时变空）、被叫走、盆被拿走就淡掉。
        和窝的前沿共用一层（同一时刻只有一个）：只在变了的那一下叫 things，平时每帧什么都不碰。"""
        roam = self.roam
        want = self._eating if roam.task == "eat" and roam.phase in ("face", "start", "loop") else None
        if want == self._bowl_front_key:
            return
        if self._bowl_front_key is not None and self._nest is None and self._pad is None:
            self.things.hide_front()
        self._bowl_front_key = want
        if want is not None:
            self.things.show_front(want)

    def bowl_emptied(self) -> None:
        """狗抬头了（roam 的 eat 走到 EatDrink_end）：这个盆空了。"""
        if self._eating is not None:
            self.things.empty(self._eating)

    def bowl_gone(self, key: str) -> None:
        """这个盆离开原地了（被拿起、收起、落下去；things 叫）：正往这来、正吃着的抬头站住。"""
        if self._eating == key:
            self._eating = None
            if self.roam.task == "eat":
                self.roam.call_off()

    def _step_perch(self, dt: float) -> None:
        """根往垫子的高度（或回 0）缓一步：PERCH_S 秒走完一个垫子高。"""
        dog = self.dog
        rate = max(self._perch_to, dog.perch, 0.05) / PERCH_S * dt
        dog.perch = min(self._perch_to, dog.perch + rate) if self._perch_to > dog.perch else max(self._perch_to, dog.perch - rate)

    def _rest_plan(self) -> Optional[tuple[float, float]]:
        """这只狗歇的计划：(没人理多久坐下, 坐下后再多久趴下)，None = 不自己歇。按性子（temper.rest_plan）。"""
        return temper.rest_plan(self.tune)

    def _can_lounge(self) -> bool:
        """现在能不能歇：没人在跟它玩——狗没被牵着跑跳（roam）、没被拎着拖着，球不在你手上、没被按着、没在动。
        点狗（duang）不算跟它玩：趴着点一下还是趴着，钟不归零（点狗只 duang）。"""
        roam, b = self.roam, self.ball
        if roam.busy or roam.lifted or self.w.dragging or self.ball_held or self._tap is not None:
            return False
        return b is None or self.carried or b.resting

    def _lounge_wish(self, idle_s: float) -> Optional[str]:
        """没人理了 idle_s 秒，该歇成什么姿势：None（站着）/ "sitting" / "lying"。该趴了但趴不下（_room_to_lie）就坐着。"""
        plan = self._rest_plan()
        if plan is None or idle_s < plan[0]:
            return None
        return "lying" if idle_s >= plan[0] + plan[1] and self._room_to_lie() else "sitting"

    def _room_to_lie(self) -> bool:
        """趴得下：站在窗口上时离窗口两头都够远（LIE_ROOM_M），地面上随便趴。"""
        s = self.roam.support
        return s is None or s.kind != "window" or s.covers(self.roam.wx, LIE_ROOM_M * self.ppm)

    def excite_scene(self, near_you: bool) -> excite.Scene:
        """这一刻狗在干什么（window._feel 拿去算兴奋度，widget/excite.py）：拿着球给它看、俯身等扔、追球、叼着、吃、溜达；
        捡球关着的时候球那几项都不算；被拎着、飞着不算。"""
        roam, b = self.roam, self.ball
        play = b is not None and self.fetch_on
        task = roam.task if roam.task != "fetch" or play else None
        return excite.Scene(posture=self.dog.posture, near_you=near_you, task=task,
                            ball_shown=self.ring.progress if play and self.ball_held else None,
                            bowing=play and roam.bowing, carrying=play and self.carried,
                            held=roam.lifted or roam.task == "fall")

    def _express(self, dt: float) -> None:
        """表情：尾巴摇多欢窗口已经按兴奋度设好了（window._feel）；这里把别的几样归零，憨的狗（性子）再叠上招牌时刻：
        笑、歪头、打招呼、趴着眼睛放松（temper.express）。"""
        e = self.dog.expr
        roam = self.roam
        e.eyes = e.tilt = e.lift = e.ears = 0.0
        e.crouch = 0.0
        goof, lazy = temper.goof(self.tune), temper.lazy(self.tune)
        if goof > 0.0 or lazy > 0.0:                              # 招牌时刻叠在最后（边牧两项都是 0：不走）
            dog = self.dog
            if goof > 0.0:
                self._greet()
            temper.express(e, self.mood, roam.t, goof, lazy, dog.lounge == "lying" and dog.posture == "lying" and not dog.transition,
                           -1.0 if math.cos(math.radians(dog.yaw)) < 0.0 else 1.0)

    def _cue(self, name: str) -> None:
        """roam 报了一个值得演个表情的时刻（放下球 put、被弹回来的球晃到 fooled、够不着叫完 stumped、叼回来路上愣住 daze）：憨的狗记下来演。"""
        if temper.goof(self.tune) <= 0.0:
            return
        if self.mood.cue(name, self.roam.t) and name == "fooled":
            self.dog.expr.ear_flick()                             # 被晃到：耳朵一抖，再歪头（歪头隔一阵才演一次，耳朵跟着它）

    def _greet(self) -> None:
        """鼠标从远处挪到狗跟前（离身子正中 temper.GREET_NEAR_DOGS 个身高以内）：闲着的狗尾巴轻轻摇一阵（不是点，是靠近；不出声）。
        在忙、球在你手上、拎着拖着、站在转台上的时候不打招呼。"""
        roam = self.roam
        cx, cy = self.cursor()
        h = roam.height_m * self.ppm
        near = math.hypot(cx - roam.wx, cy - (roam.wy - 0.5 * h)) <= temper.GREET_NEAR_DOGS * h
        free = not (roam.busy or roam.lifted or self.ball_held or self.w.dragging or self.dog.on_turntable)
        self.mood.pointer(near, roam.t, free)

    def _sync_ball(self) -> None:
        b, bw = self.ball, self.ball_win
        if b is None or bw is None or self.carried:
            return
        floor = None
        lines = list(self.world.floors) + (self._ball_tops or []) if self.world is not None else []
        s = support_below(lines, b.x, b.y)
        if s is not None:
            floor = s.y
        moving = b.rolling or not b.resting
        speed = math.hypot(b.vx, b.vy) if moving and not self.ball_held else 0.0
        bw.squash = self.ball_duang.value
        bw.sync(b.x, b.y, b.r, self.ppm, floor, b.spin, speed)
        bw.update_hit(QCursor.pos())

    # ---------- 捡球的圈（进圈才追） ----------
    def _step_ring(self, dt: float) -> None:
        """每帧：球在你手上、狗站好看着它（roam.waiting_for_throw）时才算，球心在圈里就涨、出了圈往回退（widget/ring.py）；
        满了狗自己接着叫一声、俯身（roam 看 fetch_ready，不等这里叫它）。
        狗被打断（掉下去、站的窗口没了）：满了也作废，圈原地淡掉；球还在手上的话等狗忙完接着看球，圈从空的重新算。
        闸（fetch_on）关着不算；狗还在等你扔（闸关的时候没叫到 fetch_changed）就让它起来。"""
        g, roam, b = self.ring, self.roam, self.ball
        held = self.ball_held and b is not None
        if held and not self.fetch_on:
            held = False
            if roam.waiting_for_throw:
                roam.fetch_off()
        elif held and not roam.busy and not roam.lifted and not self._seat_watch:
            self._watch_held_ball()                                   # 狗忙完了球还在手上：接着看，圈从空的算
        if not held or roam.busy or roam.lifted:
            self._seat_watch = False                                  # 坐着看的那一趟断了（松手、被拎、被牵走）
        inside = None
        if held and (roam.waiting_for_throw or self._seat_watch):
            self._ring_at = self._ring_here()
            inside = in_ring(self._ring_at, b.x, b.y)
        elif g.counting or g.ready:
            g.stop()
        hold = max(MIN_HOLD_S, temper.ring_hold(self.tune))          # 调参 ring_hold_s，聪明程度低的满得慢
        if g.step(dt, inside, hold):
            log.info("fetch ring full")
            if self._seat_watch:
                self._seated_bark()
        self._charge_sound(inside is True and g.counting and not g.ready, g, hold)

    def _watch_held_ball(self) -> None:
        """球到你手上了（拿起来、狗忙完了球还在手上）：圈从空的算，狗看着它。边牧：站好看着（roam.ball_grabbed，圈满了叫、俯身）。
        默认坐着的狗（萨摩耶，temper.sits_by_default）不交给 roam：手上自己的事（回窝、去吃、追着的）停下，趴着的坐起来、站着的坐下（_lounge），
        坐着转头看球，圈照样算（_seat_watch），满了坐着叫一声、坐着等；松手 roam.fetch 才站起来追。正在空中、被拎着的落地了再来一次（_step_ring）。"""
        self.ring.restart(native.reduce_motion())
        roam = self.roam
        if not temper.sits_by_default(self.tune):
            roam.ball_grabbed()
            return
        if roam.task in ("nest", "eat", "wander"):
            if roam.task == "nest":
                self._nest_going = None
            elif roam.task == "eat":
                self._eating = None
                self._sipping = False
            roam.call_off()
        elif roam.task == "fetch" and not roam.carrying and not roam.airborne:
            roam.cancel(drop_ball=False)
        self._seat_watch = not roam.busy and not roam.lifted
        if self._seat_watch:
            self._rest_as("sitting")

    def _seated_bark(self) -> None:
        """坐着等的狗圈满了：按调参 ready_bark 的概率坐着叫一声——模型里没有坐着叫的片段，就在坐着的姿势上张一下嘴（expr.bark，嘴张多大照 Bark 片段量的）、
        放一声狗叫（媒体音效）。之后坐着等你扔，不俯身。"""
        if self.dog.rng.random() < self.tune.get("ready_bark", 1.0):
            self.dog.expr.bark()
            self.bank.play("bark")

    def _charge_sound(self, charging: bool, g: Ring, hold_s: float) -> None:
        """充能的声音（木鱼敲六下，越敲越密、音一下比一下高，最后一下在第 CHARGE_FULL_AT 秒）。一个文件从对得上的位置放，不一下一下地放：
        球在圈里涨到离圈满还剩 CHARGE_FULL_AT 秒以内才开始放（ball_bank.start 的 offset），圈满那一下正好敲最后一下、接狗叫——
        停多久满（调参 ring_hold_s、性子）都对得上，不到 1 秒的从中间放起。
        球出了圈、松手、闸关了：很快淡掉（ball_bank.fade，不「咔」一下断）；再进圈照那时的进度接着放。满了不淡：最后一下的余音（约 0.3 秒）让它自己收住。
        只有你拿着球玩的时候才有，跟「媒体音效」的音量（调参 vol_charge）。charging：球在圈里、正在涨、还没满；hold_s：照现在的调参从空到满要多久。"""
        if not charging:
            if self._charging:
                self._charging = False
                if not g.ready:
                    self.ball_bank.fade("charge")
            return
        if self._charging:
            return
        left = (1.0 - g.progress) * hold_s                           # 照现在的涨法离圈满还有多久
        if left <= CHARGE_FULL_AT:
            self._charging = True
            self.ball_bank.start("charge", max(0.0, CHARGE_FULL_AT - left + CHARGE_LATE_S))

    def _ring_here(self) -> RingShape:
        """狗现在这个位置的圈（调参 ring_size）。狗站在狗窝的垫子上（根抬着）：圆心跟着身子抬，地面那条线不变。"""
        roam = self.roam
        s = ring_shape(roam.wx, roam.wy, roam.height_m * self.ppm, self.tune["ring_size"])
        if self.dog.perch > 0.0:
            s = RingShape(s.cx, s.cy - self.dog.perch * math.cos(math.radians(ELEVATION)) * self.ppm, s.r, s.floor)
        return s

    def _sync_ring(self) -> None:
        """圈的窗口：每块屏一个，各画落在自己那块屏上的那一截（ring.RingWindow）；圈不动不挪窗口，长相变了才重画，看不见了收起来。
        还在算的圈按狗这一帧走完以后的位置摆（狗骑在挪动的窗口上时和狗一起挪，不慢一帧）；不算了就停在最后那处淡掉。"""
        g = self.ring
        if g.counting and self.roam.waiting_for_throw:
            self._ring_at = self._ring_here()
        s = self._ring_at
        alpha = g.alpha
        look = g.look(s, self.ppm) if s is not None and alpha > 0.0 else None
        extent = ring_extent(s) if look is not None else None
        if look is not None:
            self._ensure_ring_windows()                           # 看得见的时候按现在的屏对一遍（刚拔掉的屏，那块屏的窗口不再去问它在哪）
        for rw in self.ring_wins.values():
            rw.sync(look, extent, alpha)
        if look is None and not g.counting:
            self._ring_at = None

    # ---------- 狗该看哪 ----------
    # ---------- 呆萌的来回看（萨摩耶） ----------
    @property
    def glancing(self) -> bool:
        """正在演「看球—看你—看球—看你」：只动头和眼睛，身子照旧跟鼠标（window._look_target 不拿它当身子的目标）。"""
        return self._glance_t is not None

    def _step_glance(self, dt: float) -> None:
        """每帧（球这一帧动完以后）：狗只看着的球刚停下（没去追、没在你手上、没在嘴里），按概率开演；演着的往前走，演完、有人来玩、它有事就停。"""
        b, roam = self.ball, self.roam
        moving = b is not None and not self.carried and not self.ball_held and (not b.resting or b.rolling)
        stopped = self._ball_moving and not moving and b is not None and b.resting and not self.carried and not self.ball_held
        self._ball_moving = moving
        if self._glance_t is not None:
            self._glance_t += dt
            if self._glance_t >= sum(s for _, s in temper.GLANCE) or roam.busy or roam.lifted or self.ball_held or self._tap is not None \
                    or self.dog.on_turntable or b is None:
                self._glance_t = None
            return
        if not stopped or roam.busy or roam.lifted or self.dog.on_turntable or self._now - self._glance_last < temper.GLANCE_AGAIN_S:
            return
        chance = temper.glance_chance(self.tune)
        if chance > 0.0 and self.dog.rng.random() < chance:              # 边牧 0：不抽随机数（它的随机动作一个都不能变）
            self._glance_t = 0.0
            self._glance_last = self._now

    def stop_glance(self) -> None:
        """拿起球、拎它、点它：不演了。"""
        self._glance_t = None

    def thing_thudded(self, x: float, line, strength: float) -> None:
        """重的东西（狗屋）扔下来落地（things._shake）：同一条线上附近停着的球蹦一下；狗闲着就耳朵一抖、看过去一眼（THUD_LOOK_S）。
        盆跳一下是 things 自己做的。只动我们自己的窗口，不碰别的 App。"""
        ppm = self.ppm
        reach = things_mod.SHAKE_REACH_M * ppm
        b = self.ball
        if b is not None and b.resting and not self.carried and not self.ball_held and b.on == (line.kind, line.key):
            d = abs(b.x - x)
            if d < reach:
                b.throw(0.0, -THUD_HOP_M * ppm * strength * (1.0 - d / reach), ppm)
        roam = self.roam
        if not self.active or roam.busy or roam.lifted or self.w.dragging or self.dog.on_turntable or abs(roam.wx - x) > 2.0 * reach:
            return
        self.dog.expr.ear_flick(dur=0.45, peak=min(1.0, 0.5 + strength))
        self._thud_look = (x, line.y - 0.25 * ppm, self._now + THUD_LOOK_S)

    def _glance_point(self) -> Optional[tuple[float, float]]:
        """演着的这一段该看哪：球、你（鼠标）。"""
        t = self._glance_t
        if t is None or self.ball is None:
            return None
        for target, seconds in temper.GLANCE:
            if t < seconds:
                return (self.ball.x, self.ball.y) if target == "ball" else self.cursor()
            t -= seconds
        return None

    def look_point(self, glance: bool = True) -> Optional[tuple[float, float]]:
        """狗该看哪（全局坐标）：在追球 / 冲球叫 / 站着看你手里的球、俯身等着的时候看球；球在飞、被拿着也看球；
        演着呆萌的来回看时按那张时间表看球、看你（glance=False 不算它：转身朝哪边不跟着它）；都没有 None（鼠标跟随开着就看鼠标）。"""
        if not self.active:
            return None
        if glance:
            point = self._glance_point()
            if point is not None:
                return point
            if self._thud_look is not None:
                if self._now < self._thud_look[2] and not (self.roam.busy or self.roam.lifted):
                    return self._thud_look[:2]                         # 狗屋落地那一下：看过去一眼
                self._thud_look = None
        b = self.ball
        if self.roam.watching_ball and b is not None and not self.carried:
            return (b.x, b.y)
        if self.roam.busy or self.roam.lifted:
            return None
        if b is not None and not self.carried and (self.ball_held or not b.resting):
            return (b.x, b.y)
        return None

    # ---------- 捡球开关 ----------
    def halt(self) -> None:
        """狗站上转台（看细节，window.closeup）：手上自己的事就地停下——走回窝、去吃、被拉去别处、跳下被盖住的窗口（roam.halt；
        追球的由 fetch_changed 管）。"""
        if not self.active:
            return
        roam = self.roam
        if roam.task == "nest":
            self._nest_going = None
        elif roam.task == "eat":
            self._eating = None
        roam.halt()

    def fetch_changed(self) -> None:
        """总闸（fetch_on）变了：「捡球」切了、狗上下转台了（看细节，window.closeup）。关了圈原地淡掉，跑着的停下，叼着的就地放下，
        看着球的、俯身的起来；开了球又在手上就站好看球，圈从空的算。"""
        if not self.active:
            return
        if self.fetch_on:
            if self.ball_held:
                self._watch_held_ball()
        else:
            self.ring.stop()
            self._seat_watch = False
            self.roam.fetch_off()

    # ---------- 球的鼠标 ----------
    def ball_press(self, pos: QPointF, at: Optional[float] = None) -> None:
        """按在球上。飞着、滚着的马上抓住；停着的先不算拿起：松手就是点了一下（duang），按久了、挪了才拿起。
        at：这个鼠标事件发生的时刻（hand.event_time），不给就是现在。"""
        b = self.ball
        if b is None or self.carried:
            return
        now = time.perf_counter() if at is None else at
        self.w.hide_ball_menu()                                    # 球的优先级最大：一按球，开关胶囊就收
        self.stop_glance()
        info = native.pointer_event()
        self._press_from_pad = info is not None and info[0] == native.TOUCH_SUBTYPE
        log.info("ball press: subtype %s pressure %s -> %s", *(info or (None, None)), "trackpad" if self._press_from_pad else "mouse")
        if self.ball_held:
            return
        if b.resting and not b.rolling and self.roam.task != "fetch":   # 狗正要来叼的就马上抓住，不然它先叼走了
            self._tap, self._tap_age = (pos.x(), pos.y()), 0.0
            self.ball_duang.press()
            return
        self._pick_up(pos, now)

    def _pick_up(self, pos: QPointF, now: float) -> None:
        """球到手里了：响一声；捡球开着的话狗停下来站好看着它，身边出圈（从这一刻算，圈满了才俯身：_step_ring）。"""
        b = self.ball
        self._tap = None
        self.ball_duang.release()
        self.ball_held = True
        self._lost.reset()
        self.throw_id += 1
        b.vx = b.vy = 0.0
        b.rolling = b.resting = False
        b.on = None
        self._grab_off = (b.x - pos.x(), b.y - pos.y())
        self._pointer = (pos.x(), pos.y())
        self.grab.clear()
        self.grab.append((now, pos.x(), pos.y()))
        self.ball_bank.play("grab")
        if self.fetch_on:
            self._watch_held_ball()

    def _check_tap(self, dt: float) -> None:
        """按在停着的球上按久了：算拿起。"""
        if self._tap is None:
            return
        self._tap_age += dt
        if self._tap_age >= TAP_HOLD_S and self.ball is not None:
            self._pick_up(QPointF(*self._tap), time.perf_counter())

    def _place_held(self) -> None:
        """拿着的球放在手上（鼠标 + 抓的时候的偏移），出了屏幕就夹回鼠标所在的那块屏里。"""
        b = self.ball
        px, py = self._pointer
        b.x, b.y = px + self._grab_off[0], py + self._grab_off[1]
        if self.world is not None and self.world.room_at(b.x, b.y) is None:
            i = self.world.area_index(px, py)
            if i is not None:
                a = self.world.areas[i]
                b.x = min(max(b.x, a.left + b.r), a.right - b.r)
                b.y = min(max(b.y, a.top + b.r), a.bottom - b.r)

    def _button_down(self) -> Optional[bool]:
        """鼠标键现在按没按着（全局，native.mouse_any_down）。不在真的窗口系统上（离屏测试）不问，返回 None：
        那里的「拿着」没有真按键，问到的是跑测试的人自己的鼠标。"""
        return native.mouse_any_down() if QGuiApplication.platformName() == "cocoa" else None

    def _check_lost_release(self, dt: float) -> None:
        """拿着球时鼠标键其实已经松开、松手事件却一直没来（按着的时候切走了、系统弹窗）：LOST_UP_S 秒还没来就当松了手，原地放下
        （不然圈和等着的狗一直留在桌面上；狗身上的 duang 有同样的兜底，update 里 dog_unpress 那条）。
        只在这次拿着的时候真看到过键按着才算：自测脚本里的「拿着」是假的，没有真按键。"""
        if not self.ball_held or not self._lost.gone(self._button_down(), dt, LOST_UP_S):   # 问键、数时间那一小段和物件共用（hand.LostRelease）
            return
        log.info("ball release lost: letting go")
        if self.ball_win is not None:
            self.ball_win._pressed = False                         # 转鼠标事件的两个窗口也当松了手：不然下次按在狗身上还当成在拖球
        self.w._ball_drag = False
        self._let_go(0.0, 0.0, time.perf_counter())

    def _hold_ball(self, dt: float) -> None:
        """拿着球的每一帧：远远抓住的（飞着的球点击范围大）很快滑进手里，最后停在手指底下半个球的地方。"""
        b = self.ball
        if b is None or not self.ball_held:
            return
        ox, oy = self._grab_off
        d = math.hypot(ox, oy)
        lim = 0.5 * b.r
        if d > lim:
            nd = lim + (d - lim) * math.exp(-dt / SNAP_SECONDS)
            self._grab_off = (ox * nd / d, oy * nd / d)
        self._place_held()

    def ball_drag(self, pos: QPointF, at: Optional[float] = None) -> None:
        b = self.ball
        if b is None:
            return
        now = time.perf_counter() if at is None else at
        if self._tap is not None:
            if math.hypot(pos.x() - self._tap[0], pos.y() - self._tap[1]) < TAP_MOVE_PX:
                return
            self._pick_up(QPointF(*self._tap), now)
        if not self.ball_held:
            return
        self._pointer = (pos.x(), pos.y())
        self._place_held()
        self._note_hand(now, pos.x(), pos.y())

    def _note_hand(self, now: float, x: float, y: float) -> None:
        self.grab.append((now, x, y))
        while len(self.grab) > 2 and now - self.grab[0][0] > THROW_WINDOW_SYS + THROW_SAMPLE:
            self.grab.popleft()

    def ball_release(self, pos: QPointF, at: Optional[float] = None) -> None:
        b = self.ball
        if b is None:
            return
        if self._tap is not None:                                  # 只是点了一下：duang，球不动，狗也没反应（鼠标、触摸板一样）
            self._tap = None
            self.ball_duang.release()
            return
        if not self.ball_held:
            return
        now = time.perf_counter() if at is None else at
        self.ball_drag(pos, now)
        self._let_go(*self._release_velocity(now), now)

    def _release_velocity(self, now: float) -> tuple[float, float]:
        """松手时球该多快：松手前 80 毫秒的平均速度，和狗一样（想放下，球却比预期快得多地飞出去）。
        只有系统开了三指拖移例外：手指抬起后系统还要拖一小会才发松手，手早停了，要看前面一段里最快的那一下。"""
        if self._press_from_pad and native.trackpad_system_drag():
            return hand.peak_velocity(self.grab, now, THROW_SAMPLE, THROW_WINDOW_SYS, THROW_FADE_SYS)
        return hand.velocity(self.grab, now, THROW_SAMPLE)

    def _let_go(self, vx: float, vy: float, now: float) -> None:
        """球离手：快的扔出去，慢的直接掉。狗准备好了（圈满过，一直算到这一刻）就去追，扔出去、放下都算；没准备好起身待着，
        头还跟着球（进圈才追。不按松手快慢猜是玩还是挪开球）。"""
        b = self.ball
        self.ball_held = False
        ready = self.ring.ready
        self.ring.stop()                                           # 圈原地淡掉（满的接着化开）
        speed = math.hypot(vx, vy)
        if speed < 0.4 * self.ppm:
            vx = vy = 0.0                                          # 慢慢放下：直接掉
        k = self.ball_tune.throw_factor
        b.throw(vx * k, vy * k, self.ppm)
        self.throw_id += 1
        log.info("ball released: %s, %.0f px/s, dog %s", "trackpad" if self._press_from_pad else "mouse", speed, "ready" if ready else "not ready")
        if not self.fetch_on:
            return
        if ready:
            self.dog.excite.lift_to(1.0)                      # 圈满了扔出去：兴奋一下子到顶
            self.roam.fetch()                                      # 松手那一刻就冲出去，不用等球飞一段
        else:
            self.roam.fetch_off()

    def try_snatch(self, gpos: QPointF) -> bool:
        """点在狗嘴里叼着的球上：狗松口，球到你手里（接着按住拖、松手扔）。点得到返回 True。"""
        b = self.ball
        if not self.active or b is None or not self.roam.carrying:
            return False
        mouth = self.roam.mouth_point()
        if mouth is None or math.hypot(gpos.x() - mouth[0], gpos.y() - mouth[1]) > b.r + 9:
            return False
        self.roam.let_go()
        self._press_from_pad = native.from_trackpad()
        self._pick_up(gpos, time.perf_counter())
        return True

    # ---------- 狗的鼠标（input.py 转过来） ----------
    def dog_press(self) -> None:
        """按在狗身上：压下去（duang 的前半，按多久压多久）。演着的呆萌来回看不演了。"""
        self.stop_glance()
        self.dog.expr.press(self.tune["duang_depth"])

    def dog_unpress(self) -> None:
        """松手、或者开始拎了：弹回来。"""
        self.dog.expr.release(self.tune["duang_seconds"])

    def dog_grabbed(self, root: Optional[tuple[float, float]] = None, at: Optional[float] = None) -> None:
        """开始拖狗：拎起来。正在做的事作废（叼着的球掉下来）。root、at：按下时狗在哪、什么时候按的（手速从那算起）。
        窗口列表这时问一次：拎着、飞着的时候就不问了（supports）。"""
        self.dog_unpress()
        self._hand.clear()
        if root is not None:
            self._hand.append((time.perf_counter() if at is None else at, root[0], root[1]))
        self.roam.lift_begin()
        self._refresh_frames(time.perf_counter())

    def dog_dragged(self, wx: float, wy: float, at: Optional[float] = None) -> None:
        """拎着，手挪了：记下来算手有多快（摆、腿晃、松手时扔多远）。at：这个鼠标事件发生的时刻（hand.event_time），不给就是现在。"""
        now = time.perf_counter() if at is None else at
        self._hand.append((now, wx, wy))
        while len(self._hand) > 2 and now - self._hand[0][0] > 0.25:
            self._hand.popleft()

    def floor_limit(self, x: float, y: float) -> Optional[float]:
        """拖到 (x, y) 时狗的根最低能到哪：这一列的地面（屏幕高低不齐时按 x 所在的那块屏；上下摆的两块屏算连通）。这一列没有地面 None。"""
        if self.world is None:
            return None
        floors = [f.y for f in self.world.floors if f.covers(x)]
        if not floors:
            return None
        below = [f for f in floors if f >= y]
        return min(below) if below else max(floors)

    def _feed_lift(self) -> None:
        if self.roam.lifted:
            self.dog.lift.feed(hand.velocity(self._hand, time.perf_counter(), HAND_WINDOW)[0] / self.ppm)

    def dog_dropped(self, at: Optional[float] = None) -> None:
        """拖完松手：手还在动就扔出去（幅度按质量算）；不动就掉下去，落在下面的窗口上沿或地面；脚下就是线就站在那。
        at：松手这个事件发生的时刻（hand.event_time），不给就是现在。"""
        vx, vy = hand.velocity(self._hand, time.perf_counter() if at is None else at, THROW_SAMPLE)
        self.roam.place(*self.w.scene_world())
        if math.hypot(vx, vy) < DOG_THROW_MIN_M * self.ppm:
            vx = vy = 0.0
        k = self.tune.throw_factor
        self.roam.lift_end(vx * k, vy * k)

    def dog_slid(self, wx: float, wy: float) -> None:
        """看细节放大着把狗横着挪到了 (wx, wy)（脚踩的那条线没变，不拎、不扔，widget/input.py）：这就是它现在在哪，脚下那条线照旧记作家。
        roam 这时停着（放大着 hold），缩回来从这里接着走。"""
        if not self.active or self.roam.lifted:
            return
        roam = self.roam
        roam.place(wx, wy)
        if roam.settle_support() is not None and not roam.busy:
            roam.remember_home()

    def window_settled(self) -> None:
        """狗的窗口停稳了（被系统挪过、缩放过、拔了屏）而狗没在忙：位置从窗口读回来，脚下没东西就掉，有就记作家。"""
        if not self.active or self.roam.busy or self.roam.lifted:
            return
        if self.roam.support is not None and self.roam.support.kind == "window":
            return                                                # 骑在窗口上：位置由 roam 管
        self.roam.place(*self.w.scene_world())
        self.roam.drop_to_support()

    @property
    def busy(self) -> bool:
        """狗正被牵着跑 / 跳，或者球正被你拿着。"""
        return self.roam.busy or self.ball_held
