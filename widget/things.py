"""灵动交互里的物件（狗窝、盆、公园里的东西）：摆出来、拖、落、记位置。游乐场（widget/playground.py）每帧调 update，
窗口（widget/thing_win.py，一件一个只画那张图的小窗口）把鼠标事件转过来；图由 widget/thing_art.py 借狗的画布出。
只列有用法的（SUPPORTED_ROLES：狗窝、狗屋、盆；栏、长椅、公园里那些摆设的包留着，不列、摆不出来）。
家具不进空间：狗、球从它前面过，不挡——例外：台子（平顶狗屋的屋顶）能站，狗窝的垫子狗踩着过去（pad_at）。

- Shelf：设置里记的（prefs 的 things）——摆着哪些款、各在哪块屏的地面上、占屏宽的几成（不记绝对坐标）。收起来的款位置留着，再摆出来回到原处。
- Thing：摆着的一件。x 是物件正中、y 是它踩的那条线（画出来最低的那一点落在线上）。
- 规矩照球：按下先 duang，按够 TAP_HOLD_S 或挪了 TAP_MOVE_PX 才算拿起，之前松手只是点了一下；拖的时候鼠标事件只记位置、每帧挪一次窗口，
  窗口整个夹在鼠标所在那块屏里（不骑交界）。松手：手快的扔出去（按手的速度，和球一样按系统给事件打的时间算；越重的出手越慢），
  手慢的直着落；飞、撞这块屏的边和「窗口交互」开着时别的 App 窗口的侧面弹回、落到线上（地面，或别的 App 的窗口上沿——看得见、够宽、上面放得下）
  都照球的那一套，只是按盒子算（_fall）；每一款有自己的轻重软硬（包里 thing.physics → ThingPhysics：质量、弹性、摩擦、压扁多少、弹回多快、
  扬灰、震、落地的声音和音量），落地按撞得多重压扁、出声（只在人扔、拖着放下的时候响），重的扬一圈灰（widget/dust.py）、震得同一条线上附近的盆和球跳一下、
  狗看过去（playground.thing_thudded）；弹完、滑停了落定、存位置。松手事件丢了：键松开 LOST_UP_S 秒当松了手。右键：「我不要……了」，点了 = 收起来。
- 前后由窗口的层级管（native.LEVEL_*：同一层里系统自己会重排——点了垫子它跑到狗前面、一切桌面盆跑到窝后面——代码排不住）：
  物件分两档（tier：盆在前，窝、狗屋在后），各在一层；狗在所有物件前面，歇进窝、踩上垫子时换到窝和窝沿之间、盆后面（rims_changed）。
  同一档里新摆的、点过的在前（两个窝叠着，点了的那个要在前面）：显示、按下都提到这一层最前，设置里的先后跟着挪（Shelf.to_front），
  重开按先后从早到晚显示。盖在狗前面的物件看得见的地方狗不接鼠标（covers_dog），点在那儿算物件。
- 点一下（没算拿起就松手）：盆 = 敲盆（添满、叫狗来吃）；窝、狗屋= 叫狗过来趴进这一个（playground.nest_tapped）。
- 大小：包里写的倍数（狗窝再乘狗的身高比）× 整体大小；画出来比那块屏可用宽度的 SCREEN_SHARE 还宽的整件缩到那么宽（独木桥在小屏上）。
  拖大小滑杆时物件不动、不重画，停稳 RESIZE_SETTLE_S 秒后各重排一次。
- 图：摆出来、换大小（停稳以后）、落到像素密度不一样的屏时重出，一帧最多出一件；狗在动、窗口铺宽着时先等一等（出图要读回整块主画布）。
  按（模型、倍数、角度、比例尺、像素密度）记着，同一把钥匙不重出；不存盘。没有显卡（单测）图是空的：窗口照样摆，点击范围退成物件的方框。
- 站在别的窗口顶上的：窗口表每重问一次（0.25 秒，和狗用同一份；狗待着时本来不问，有物件站在窗口上才多这一问）对一遍——窗口没了、那一段被盖住了、「窗口当台子」关了就落下去；
  窗口挪了，这 FOLLOW_S 秒里每帧问这一个窗口跟着挪。位置只记在哪块屏的地面上：重开落在正下方的地面。
- 关灵动交互：0.2 秒淡出、藏起来，再开回来还在原地。停着的物件每帧一次系统调用都没有（窗口那头没变就什么都不做）。
- 摆下去马上有反应：从「物件」页摆出来落定、拖完松手落定的那一下告诉 playground（thing_placed：狗闲着就过来——窝 → 趴进去，
  满着的盆 → 吃 / 喝一次）。重开、开灵动交互回原处的，脚下的窗口没了落下去的，不算。
- 窝（包里写了 rest 的狗窝、狗屋）：nest_spots 说狗能歇在哪（NestSpot：哪条线、横着在哪、根抬多高、朝哪）；什么时候去、怎么趴下在 playground（_lounge、settle_in）。
  狗窝：歇在窝正中、根抬到垫子那么高；尖顶狗屋：歇在门朝的那一侧外面（留多远按狗趴着的身长量，放不下换到屋的正前面）；平顶狗屋：趴在门前。
  窝的前沿（包里的 front_z：比它更靠镜头的面另画一层；盆是 front_rim：整件的图只留近处盆沿以下）另开一个点得穿的小窗口，
  只在狗歇在这个窝里、在这个盆吃喝时显示，盖在狗前面（show_front / hide_front；显示着时狗在这一档里，rims_changed）。
  窝被拿起、收起、脚下的线没了、换了大小挪了地方：告诉 playground（nest_gone），里面的狗站起来、正往这走的站住。
  狗窝的垫子（pad_at：rest.rise 大于 0 的窝，横着的范围是 rest.half）：狗在这条线上跑、走、站，身子正中进了范围就踩在垫子上（根抬多高和歇进来一样），
  playground._tread 每帧问；前沿那一层的图、窗口闲着的时候先备好（_front_due），狗第一次踩上来不用现出。
- 盆（包里写了 serves 的饭盆、水盆）：满的、空的两个样子（两个模型，各一张图；摆出来是满的，另一张闲着的时候先出好）。点一下（没算拿起就松手）= 敲盆：
  空的先添满，再叫狗来吃（playground.bowl_tapped；狗来不来它定）。狗吃完那一刻变空（empty）。盆被拿起、收起、落下去：告诉 playground（bowl_gone），正吃着的抬头站住。
- 台子（包里写了 platform 的款：现在列出来的只有平顶狗屋）：摆着、停着的每个台子是一个混进窗口表的假窗口框（frames，窗口号是负的，真窗口号是正的），
  狗和球现成的「窗口上沿」那一套原样生效：能站、能跳上去、球能停、从侧面和下面撞上来弹回去；厚到地的（平顶狗屋）是实心盒子，薄板（长椅那种，包里的写法还认）球能从底下滚过去。
  摆了、拿起、落定、收起、跟着脚下的窗口挪了：告诉 playground 重拼窗口表（platforms_changed，不重问系统）；拿起台子，上面的狗和球照「窗口没了」原地掉。
  物件自己找线只看真窗口（playground._native_frames）：物件不叠在物件上。「窗口当台子」关着时台子照留（它不是别的 App 的窗口）。"""
from __future__ import annotations

import json
import logging
import math
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, QVariantAnimation
from PySide6.QtGui import QCursor, QGuiApplication, QImage

from widget import hand, native, packs, sounds, thing_art
from widget.ball import Squash
from widget.dust import DustCloud
from widget.render import ELEVATION
from widget.hand import LostRelease
from widget.thing_win import ThingWindow
from widget.world import EPS, GRAVITY_M, Support, WindowFrame, support_below

log = logging.getLogger("things")

SUPPORTED_ROLES = frozenset({"bed", "house", "bowl"})   # 列出来、摆得出来的角色：有用法的才算（窝、屋、盆）。摆设（decor）、栏（hurdle）、玩具（fetch、push）的包留着，不列
BALL_KEY = "ball/red"        # 小球（球也是一件道具）：「物件」页「玩具」那一格、道具栏、右键球都是它；它不归这里摆，归 playground（球的物理、窗口）
FADE_S = 0.2                 # 摆出来淡入、收起来淡出多久
DROP_IN_M = 0.3              # 从设置里摆出来：从这么高落下来（看得见它来了）
FIRST_GAP_M = 1.2            # 第一次摆出来：离狗这么远（再加半个物件宽），在狗朝屏幕中间的那一侧
SCREEN_SHARE = 0.7           # 画出来最宽占那块屏可用宽度的几成，再宽就整件缩小
RESIZE_SETTLE_S = 0.25       # 大小停稳这么久才重排、重出图（拖滑杆的每一格都改几个窗口就是卡顿）
FOLLOW_S = 0.6               # 脚下的窗口挪了：这么久里每帧问这一个窗口跟着挪，停了就不问
SHOT_WAIT_S = 0.6            # 狗在动、窗口铺宽着时出图最多等这么久（等不到就照出）
DUANG_DEPTH = 0.08           # 按下压扁多少；大件按 DUANG_REACH_M 封顶
DUANG_REACH_M = 0.03         # 压扁、弹过头最多动这么多米（狗屋压 8% 就是十几厘米，弹过头会顶出窗口上沿）
LAND_NEAR_PX = 2.0           # 松手时脚下这么近就有线：原地放下，不落
NEST_ROLES = frozenset({"bed", "house"})   # 包里写了 rest 的这两种角色是窝：狗会回来歇
FRONT_ROLES = frozenset({"bowl"})          # 物件之间前后分两档：盆一档在前，窝、狗屋一档在后（饭盆水盆在狗屋、垫子前面）
PAD_SHARE = 0.7              # 狗窝的垫子横着占多宽：包里没写 rest.half 的，按物件画出来宽度的这么多成（两头是窝的边沿）
FRONT_FADE_S = 0.12          # 窝的前沿那一层盖上、收掉多久（和狗的根抬到垫子上一样长，playground.PERCH_S）
QUARTER_COS = math.cos(math.radians(30.0))   # 狗歇着是四分之三朝向（330° / 210°）：身长在画面上横着占这么多成
# 扔出去（手速的算法和球一样，见 playground.THROW_SAMPLE、widget/hand.py）
THROW_MIN_M = 0.4            # 松手时手比这慢（米 / 秒）：放下，直着落（和球一样）
THROW_SAMPLE = 0.08          # 算手的速度取松手前多长一段（秒，按系统给事件打的时间算）
THROW_WINDOW_SYS, THROW_FADE_SYS = 0.7, 0.45   # 系统开了三指拖移：手指抬起后系统还要拖一小会才发松手，往前看一段里最快的那一下（和球一样）
MASS_REF_KG = 1.0            # 越重扔得越近：出手速度 × 1/√(1 + 质量 / 这个)（饭盆 0.85、狗窝 0.58、狗屋 0.28）
THROW_MAX_M = 9.0            # 出手最快多少（米 / 秒）
REST_BOUNCE_M = 0.7          # 落地往回弹得比这慢（米 / 秒）就不弹了，贴着线滑
LAND_KEEP = 0.75             # 落地那一下横着的速度留几成（再按摩擦滑）
WALL_E = (0.15, 0.6)         # 撞屏幕边、窗口侧面、天花板弹回几成：0.15 + 弹性，最多 0.6
SLIDE_STOP_M = 0.05          # 滑得比这慢（米 / 秒）就停
IMPACT_FULL_M = 4.0          # 落地时往下这么快（米 / 秒）算最重的一下：压扁、声音、扬灰、震都按它几成
LAND_REACH_M = 0.08          # 落地压扁最多压下去这么多米（大件；软的阻尼到 1 不弹过头，不会顶出窗口上沿）
SHAKE_REACH_M = 1.6          # 重的落地：同一条线上这么远以内的轻东西跳一下、球蹦一下；狗在两倍这么远以内看过去
HOP_M = 1.2                  # 被震的盆往上跳多快（米 / 秒，再按远近、落地多重减）
HOP_MASS_KG = 1.0            # 比这轻的才被震得跳（盆）；窝、狗屋不动


@dataclass(frozen=True)
class ThingPhysics:
    """一款物件扔出去、落地的样子（包里 thing.physics，代码里不写死哪一款；数是看着模型、材质定的）。"""
    mass_kg: float = 1.0       # 越重出手越慢（MASS_REF_KG）
    bounce: float = 0.2        # 落地往回弹几成（也决定撞墙弹回多少）
    friction: float = 6.0      # 落到线上以后滑的时候每秒慢多少（米 / 秒²）
    squash: float = 0.1        # 落地最重时压扁几成（按物件高度；LAND_REACH_M 封顶）
    recover: float = 1.0       # 压扁以后弹回来多快（弹簧的倍数；小于 0.8 的不弹过头，慢慢鼓回来）
    dust: float = 0.0          # 落地扬灰多少（0 = 不扬）
    shake: float = 0.0         # 落地震旁边的东西多重（0 = 不震）
    volume: float = 1.0        # 落地那一声多响（再乘撞得多重、媒体音效的音量）

    @classmethod
    def of(cls, spec: Mapping) -> "ThingPhysics":
        raw = spec.get("physics") if isinstance(spec.get("physics"), Mapping) else {}
        out = {}
        for f in fields(cls):
            try:
                out[f.name] = float(raw.get(f.name, f.default))
            except (TypeError, ValueError):
                out[f.name] = f.default
        return cls(**out)
YAW_HEAD_RIGHT, YAW_HEAD_LEFT = 330.0, 210.0  # 歇着头朝右 / 朝左（window._home_yaw 的那两个朝向）


def page_styles(styles=None) -> list:
    """「物件」页上能列的款（按页上的先后）：接进来了的角色、有模型的，加上小球。styles 不给就是 packs.things()。"""
    styles = packs.things() if styles is None else styles
    return [t for t in styles if t.key == BALL_KEY or (t.role in SUPPORTED_ROLES and t.model is not None)]


@dataclass(frozen=True)
class NestSpot:
    """狗能歇的一处：哪件物件、踩哪条线、根横着在哪（全局 x）、根再抬多高（米，垫子的高度；歇在地上的 0）、朝哪（None = 照平时歇着的朝向）。"""
    key: str
    support: Support
    x: float
    perch_m: float
    yaw: Optional[float]


class Shelf:
    """设置里记的物件：一款一项 {"key", "on", "screen", "fx"}，从后到前（点过、新摆的挪到最后，to_front）。读不出来当空的。玩具那一个位置（toy）也记在这。"""

    def __init__(self, store) -> None:
        self.store = store
        self._rows = self._read()

    def _read(self) -> list[dict]:
        try:
            raw = json.loads(self.store.value("things", "") or "[]")
            rows = [{"key": str(r["key"]), "on": bool(r.get("on", False)), "screen": str(r.get("screen", "")), "fx": float(r.get("fx", -1.0))}
                    for r in raw]
        except (ValueError, KeyError, TypeError, AttributeError):
            return []
        seen: set[str] = set()
        return [r for r in rows if not (r["key"] in seen or seen.add(r["key"]))]

    def _save(self) -> None:
        self.store.setValue("things", json.dumps(self._rows))

    def _row(self, key: str, make: bool = False) -> Optional[dict]:
        row = next((r for r in self._rows if r["key"] == key), None)
        if row is None and make:
            row = {"key": key, "on": False, "screen": "", "fx": -1.0}
            self._rows.append(row)
        return row

    def placed(self) -> list[str]:
        """摆着的款。"""
        return [r["key"] for r in self._rows if r["on"]]

    def on(self, key: str) -> bool:
        row = self._row(key)
        return row is not None and row["on"]

    def spot(self, key: str) -> Optional[tuple[str, float]]:
        """这一款上次在哪：(屏的名字, 占那块屏可用宽度的几成)；没记过 None。"""
        row = self._row(key)
        return (row["screen"], row["fx"]) if row is not None and row["fx"] >= 0.0 else None

    def put(self, key: str, on: bool) -> None:
        row = self._row(key, make=True)
        if row["on"] != bool(on):
            row["on"] = bool(on)
            self._save()

    def move(self, key: str, screen: str, fx: float) -> None:
        row = self._row(key, make=True)
        fx = max(0.0, min(1.0, float(fx)))
        if (row["screen"], row["fx"]) != (screen, fx):
            row["screen"], row["fx"] = screen, fx
            self._save()

    def to_front(self, key: str) -> None:
        """这一款挪到最后（点过、新摆的在别的物件前面；重开按这个先后摆出来，后摆的在前面）。已经在最后不存。"""
        row = self._row(key)
        if row is not None and self._rows[-1] is not row:
            self._rows.remove(row)
            self._rows.append(row)
            self._save()

    def toy(self) -> str:
        """玩具那一个位置现在是哪款；空 = 红球（现在这只）。"""
        return str(self.store.value("toy", "") or "")

    def set_toy(self, key: str) -> None:
        self.store.setValue("toy", key)


class Thing:
    """摆着的一件。state：rest 停着 / tap 按着还没算拿起 / held 拿着 / fall 在落 / gone 正在收起（不接鼠标了）。"""

    def __init__(self, style: packs.ThingStyle, tune=None):
        self.style, self.key = style, style.key
        self.nest = style.role in NEST_ROLES and isinstance(style.spec.get("rest"), Mapping)   # 是窝：狗会回来歇
        self.serves: Optional[str] = str(style.spec["serves"]) if style.role == "bowl" and style.spec.get("serves") in ("food", "water") else None   # 是盆：盛的什么
        self.full = True                            # 盆：满着（摆出来是满的；狗吃完变空，敲一下添满）
        self.platform = style.spec.get("platform") if isinstance(style.spec.get("platform"), Mapping) else None   # 是台子：台面在哪（模型单位）
        self.number = 0                             # 台子在窗口表里的假窗口号（负的；Things._spawn 定）
        self.empty_model = None                     # 盆：空了的样子的模型文件（读得出来才有；_spawn 定）
        self.x = self.y = 0.0                       # 物件正中、它踩的那条线（全局坐标）
        self.on: Optional[tuple[str, int]] = None   # 踩着哪条线（kind, key）；拿着、在落的时候 None
        self.area = 0                               # 在哪块屏（world.areas 的序号）
        self.screen = ""                            # 那块屏的名字（屏的序号会变，名字不变）
        self.right_half = False                     # 停在屏幕右半边（mirror 的款反过来画）；落定时才换
        self.state = "rest"
        self.vy = 0.0
        self.vx = 0.0                               # 在落：横着多快（像素 / 秒；扔出去的有，直着落的 0）
        self._phys = ThingPhysics.of(style.spec)    # 轻重软硬（包里 thing.physics）；开发者设置里调过的项盖在上面（phys）
        self.tune = tune                            # 这一类的调参（window.tuning_of；单测的假 host 没有就 None）
        self.slide: Optional[Support] = None        # 在落：已经落到这条线上、贴着它滑（停了落定）
        self.loud = False                           # 这一趟是你扔的、拖着放下的：落地出声（只在人扔、放下的时候响）
        self.hand: deque = deque()                  # 拖着的时候手在哪：(时刻, x, y)，松手按它算扔多快（和球一样）
        self.from_pad = False                       # 这一下是触摸板按的（三指拖移要往前看一段）
        self.target: Optional[Support] = None       # 在落：指定落在哪条线（从设置里摆出来的落在地面上）；None = 正下方最近的
        self.fresh = False                          # 刚从「物件」页摆出来、刚被你拖完松手，还在落：落定那一下告诉 playground（Things._placed）
        self.ride: Optional[tuple[float, float]] = None   # 站在窗口上：上次看到那个窗口的左、上
        self.follow = 0.0                           # 还要每帧跟着脚下的窗口多久
        self.grab = (0.0, 0.0)                      # 拿着：物件相对鼠标在哪
        self.pointer = (0.0, 0.0)
        self.tap_at = (0.0, 0.0)
        self.tap_age = 0.0
        self.duang = Squash()
        self.alpha, self.fade_to = 0.0, 1.0
        self.model = None                           # 放大过的模型（thing_art.scaled）
        self.lay: Optional[thing_art.Layout] = None
        self.geo: Optional[tuple] = None            # 画面是按什么量的：(模型, 倍数, 角度, 比例尺, 影子)
        self.pivot = QPointF()
        self.box = QRectF()
        self.shot: Optional[QImage] = None
        self.shot_key: Optional[tuple] = None
        self.need_shot = True
        self.shot_wait = 0.0
        self.win: Optional[ThingWindow] = None
        self.front_win: Optional[ThingWindow] = None   # 窝的前沿那一层的窗口（狗第一次歇进来时才建）
        self.front_model = None                     # 前沿的模型和它是按哪次量的切的：(Thing.geo, 模型)
        self.front_shot: Optional[QImage] = None
        self.front_key: Optional[tuple] = None
        self.front_alpha, self.front_to = 0.0, 0.0

    @property
    def phys(self) -> ThingPhysics:
        """轻重软硬：包里 thing.physics（这一款盖掉的照这一款），开发者设置里调过的项（不是默认值的）用调过的数；每次现读，改了下一次扔、落就生效。"""
        tune, base = self.tune, self._phys
        if tune is None:
            return base
        changed = {f.name: tune[f.name] for f in fields(ThingPhysics) if f.name in tune.values and not tune.is_default(f.name)}
        return replace(base, **changed) if changed else base

    @phys.setter
    def phys(self, value: ThingPhysics) -> None:
        self._phys = value

    @property
    def width(self) -> float:
        """物件本身画出来多宽（像素，不算影子）。"""
        return (self.lay.left_m + self.lay.right_m) * self.lay.frame.ppm

    @property
    def height(self) -> float:
        return self.lay.top_m * self.lay.frame.ppm

    def span(self) -> tuple[float, float]:
        """物件本身占的左右（全局 x）。"""
        ppm = self.lay.frame.ppm
        return self.x - self.lay.left_m * ppm, self.x + self.lay.right_m * ppm


def tier(t: "Thing") -> int:
    """前后哪一档（窗口按它取层，native.LEVEL_THING / LEVEL_RIM / LEVEL_DOG_IN）：盆 1（在前，FRONT_ROLES），窝、狗屋 0。"""
    return 1 if t.style.role in FRONT_ROLES else 0


def has_front(t: "Thing") -> bool:
    """这一款有没有盖在狗前面的那一层：窝写了 front_z（按模型切），盆写了 front_rim（按图遮）。"""
    return t.style.spec.get("front_z") is not None or isinstance(t.style.spec.get("front_rim"), Mapping)


class Things:
    def __init__(self, host):
        from widget import playground             # 这里才引：playground 也引这个文件
        self._tap_hold, self._tap_move, self._lost_after = playground.TAP_HOLD_S, playground.TAP_MOVE_PX, playground.LOST_UP_S
        self.host = host                          # Playground：world、ppm、frames、窗口
        self.shelf = Shelf(host.w.settings)
        self.styles: dict[str, packs.ThingStyle] = {}
        self.items: dict[str, Thing] = {}         # 摆着的（连正在收起的），按摆出来的先后
        self._shots: dict[tuple, QImage] = {}     # 出过的图：钥匙是 Thing.geo + 像素密度
        self._layouts: dict[tuple, thing_art.Layout] = {}
        self._spans: dict[tuple, tuple[float, float]] = {}   # (模型, 角度) → 1 倍时画出来的左右（米）
        self._held: Optional[Thing] = None        # 按着 / 拿着的那一件
        self._dust: Optional[DustCloud] = None    # 落地扬的灰（重的落地才建，_dust_at）
        self._front: Optional[Thing] = None       # 前沿那一层显示着的那个窝（狗歇在里面）
        self._lost = LostRelease()
        self._frames_seen = None                  # 上次对线时窗口表是哪一份（host._frames_at）
        self._resize_in: Optional[float] = None   # 大小变了：还要等多久才重排
        self._fade = QVariantAnimation()          # 关灵动交互时的淡出（那以后没有下一帧了，得自己走）
        self._fade.setDuration(round(FADE_S * 1000))
        self._fade.valueChanged.connect(self._fade_all)
        self._fade.finished.connect(self._fade_done)
        self.use(packs.things())

    # ---------- 能用的款 ----------
    def use(self, styles) -> None:
        """能摆的款：接进来了的角色、有模型的（程序自己画的小球不归这里摆，只在 page 里列）。"""
        styles = list(styles)
        self.styles = {t.key: t for t in styles if t.role in SUPPORTED_ROLES and t.model is not None}
        self.ball_style = next((t for t in styles if t.key == BALL_KEY), None)
        self._order = [t.key for t in styles]

    def available(self) -> list:
        return list(self.styles.values())

    def page(self) -> list:
        """「物件」页上列的（按页上的先后）：能摆的款，加上小球（球归 playground 管，窗口 thing_on / set_thing 分开问）。"""
        listed = dict(self.styles)
        if self.ball_style is not None:
            listed[BALL_KEY] = self.ball_style
        return [listed[k] for k in self._order if k in listed]

    def is_on(self, key: str) -> bool:
        """这一款摆着没有（设置里记的；灵动交互关着时窗口藏着也算摆着）。"""
        return key in self.styles and self.shelf.on(key)

    def count(self) -> int:
        return sum(1 for key in self.shelf.placed() if key in self.styles)

    # ---------- 摆出来 / 收起来 ----------
    def set_on(self, key: str, on: bool) -> None:
        """摆出来 / 收起来一款（「物件」页的格子、右键的胶囊）。收起来位置留着。灵动交互关着只记下，开了才摆。"""
        if key not in self.styles:
            return
        self.shelf.put(key, on)
        if not self.host.active:
            return
        t = self.items.get(key)
        if on:
            self.shelf.to_front(key)                            # 新摆的在别的物件前面
            if t is None:
                self._spawn(key, drop=True)
            elif t.state == "gone":                             # 正在收的又要回来
                t.state, t.fade_to = "rest", 1.0
                self._staged(t)
                self._placed(t)
        elif t is not None and t.state != "gone":
            self._put_away(t)

    def put_all_away(self) -> None:
        for key in self.shelf.placed():
            self.set_on(key, False)

    def start(self) -> None:
        """灵动交互开起来：记着摆着的款各回原处（上次藏起来的还在内存里就原样出来，脚下的线对一遍）。"""
        self._fade.stop()
        self._resize_in = None
        rank = {key: i for i, key in enumerate(self.shelf.placed())}
        for t in sorted(self.items.values(), key=lambda t: rank.get(t.key, -1)):   # 按先后从早到晚显示：同一档里后摆的、后点的在前面
            if t.state == "gone" or not self.shelf.on(t.key):
                self._remove(t)
                continue
            t.alpha, t.fade_to, t.state = 0.0, 1.0, "rest"
            self._come_back(t)
            self._show(t)
        for key in self.shelf.placed():
            if key in self.styles and key not in self.items:
                self._spawn(key, drop=False)

    def stop(self) -> None:
        """关灵动交互：手上的原地放下，全部淡出、藏起来；位置留着。"""
        self._let_go_now()
        for t in list(self.items.values()):
            if t.state == "gone":
                self._remove(t)
            elif t.state == "fall":
                self._land(t, self._line_below(t), thud=False)
            t.duang.release()
        if any(t.win.isVisible() for t in self.items.values()):
            self._fade.setStartValue(1.0)
            self._fade.setEndValue(0.0)
            self._fade.start()

    def fail_safe(self) -> None:
        """出错兜底：直接藏。"""
        self._fade.stop()
        self._held = None
        self._front = None
        for t in self.items.values():
            t.win.let_go()
            t.win.hide()
            t.front_alpha = t.front_to = 0.0
            if t.front_win is not None:
                t.front_win.hide()

    def _fade_all(self, v) -> None:
        for t in self.items.values():
            t.alpha = min(t.alpha, float(v))
            self._sync(t)

    def _fade_done(self) -> None:
        if not self.host.active:
            for t in self.items.values():
                t.win.hide()

    def _tune_for(self, style: packs.ThingStyle):
        """这一款那一类的调参（开发者设置里调物件的那一份，window.tuning_of）；单测的假 host 没有：None，照包里写的。"""
        of = getattr(getattr(self.host, "w", None), "tuning_of", None)
        pack = packs.discover().get(style.pack) if of is not None else None
        return of(pack) if pack is not None else None

    def _spawn(self, key: str, drop: bool) -> Optional[Thing]:
        """把这一款摆出来。记过位置：回到那块屏的地面上那一处；没记过：狗朝屏幕中间的那一侧。drop：从半空落下来（从设置里摆的）。"""
        style = self.styles[key]
        try:
            thing_art.load_static(style.model)
        except ValueError as exc:
            log.warning("thing %s can't be drawn, dropped: %s", key, exc)
            del self.styles[key]
            return None
        world = self.host.world
        t = Thing(style, self._tune_for(style))
        t.win = ThingWindow(self, t, tier=tier(t))
        if t.serves is not None and style.model_empty is not None:
            try:
                thing_art.load_static(style.model_empty)
                t.empty_model = style.model_empty
            except ValueError as exc:
                log.warning("thing %s has no empty look: %s", key, exc)   # 空盆的模型不在：吃完还画满的那张
        t.number = -(1 + list(self.styles).index(key))             # 台子的假窗口号：按款表里的先后，同一款每次都是同一个号
        spot = self.shelf.spot(key)
        if spot is not None:
            t.area = self._area_named(spot[0])
            a = world.areas[t.area]
            t.x = a.left + spot[1] * (a.right - a.left)
            t.right_half = t.x > (a.left + a.right) / 2
            self._fit(t)
            line = self._floor(t.area, t.x)
        else:
            line = self._first_spot(t)
        self.items[key] = t
        self._seat(t, line)
        self._settle(t)
        if drop:
            t.state, t.on, t.vy, t.target, t.fresh = "fall", None, 0.0, line, True
            t.vx, t.slide, t.loud = 0.0, None, False
            t.y = line.y - DROP_IN_M * self.host.ppm
            top = world.areas[t.area].top + (t.lay.h - t.lay.base)
            t.y = min(line.y, max(t.y, top))
            self._staged(t)                                        # 还在落：这会儿不算台子
        self._show(t)
        return t

    def _come_back(self, t: Thing) -> None:
        """藏着的这一件再出来：屏、大小可能都变过了，重新量、脚下的线对一遍（地面的回到地面；窗口的等下一次对线）。"""
        world = self.host.world
        t.area = self._area_named(t.screen)
        t.geo = None
        self._fit(t)
        if t.on is None or t.on[0] != "window" or not self.host.w.hop_windows_on:
            self._seat(t, self._floor(t.area, t.x))
        self._settle(t)
        self._frames_seen = None
        if world.area_index(t.x, t.y - 1.0) is None:
            self._seat(t, world.nearest_floor(t.x, t.y))

    def _show(self, t: Thing) -> None:
        self._sync(t)
        if not t.win.isVisible():
            t.win.show()                           # 显示出来就在它那一档那一层的最前面（ThingWindow.level）

    def _put_away(self, t: Thing) -> None:
        """收起来：0.2 秒淡出，位置留着。"""
        if self._held is t:
            self._held = None
            t.win.let_go()
        if t.state in ("held", "fall"):
            self._land(t, self._line_below(t), thud=False)
        t.duang.release()
        t.state, t.fade_to = "gone", 0.0
        self._left(t)
        self.host.w.hide_thing_menu()

    def _remove(self, t: Thing) -> None:
        t.win.hide()
        t.win.deleteLater()
        if t.front_win is not None:
            t.front_win.hide()
            t.front_win.deleteLater()
            t.front_win = None
        if self._front is t:
            self._front = None
        self.items.pop(t.key, None)
        self._left(t)                              # 摘掉以后再说：窗口表里不留它的台子
        if self._held is t:
            self._held = None
        self._prune_shots()

    # ---------- 量：多大、朝哪、画面 ----------
    def _fit(self, t: Thing) -> None:
        """按它现在那块屏、现在的大小重新量：倍数（太宽的封顶）、朝向、画面。量的东西没变就什么都不动；变了，图等落定再出。"""
        host, spec = self.host, t.style.spec
        path = str(t.style.model if t.full or t.empty_model is None else t.empty_model)   # 盆空了画空的那个模型
        yaw = thing_art.yaw_of(spec, t.right_half)
        k = thing_art.scale_of(spec, host.pack.height_m)
        span = self._spans.get((path, yaw))
        if span is None:
            x0, x1, _, _ = thing_art.extent(thing_art.load_static(path), yaw)
            span = self._spans[(path, yaw)] = (x0, x1)
        a = host.world.areas[t.area]
        wide = (span[1] - span[0]) * k * host.ppm
        if wide > SCREEN_SHARE * (a.right - a.left):
            k *= SCREEN_SHARE * (a.right - a.left) / wide
        geo = (path, round(k, 4), yaw, round(host.ppm, 3), bool(spec.get("shadow", True)))
        if geo == t.geo:
            return
        t.geo = geo
        t.model, lay = self._measure(geo)
        t.lay = lay
        t.pivot = QPointF(lay.cx, lay.h - lay.base)
        t.box = QRectF(*lay.box())
        t.duang.DEPTH = min(DUANG_DEPTH, DUANG_REACH_M / max(lay.top_m, 1e-3))

    def _measure(self, geo: tuple) -> tuple:
        """按一次量的结果（模型, 倍数, 角度, 比例尺, 影子）：(放大过的模型, 画面)。画面记着，同一组数不重算。"""
        model = thing_art.scaled(thing_art.load_static(geo[0]), geo[1])
        lay = self._layouts.get(geo)
        if lay is None:
            if len(self._layouts) > 64:
                self._layouts.clear()
            lay = self._layouts[geo] = thing_art.layout(model, geo[2], geo[3], geo[4])
        return model, lay

    def _spare(self, t: Thing) -> Optional[tuple]:
        """盆现在没画的那个样子（满着时是空的那张，空着时是满的那张）：(物件, 那张图的钥匙)；不是盆、没有空盆的模型、还没量过：None。"""
        if t.empty_model is None or t.geo is None or t.state == "gone":
            return None
        other = str(t.empty_model if t.full else t.style.model)
        return t, (other,) + t.geo[1:] + (self._dpr(t.area),)

    def _settle(self, t: Thing) -> None:
        """落定了：在屏幕哪半边（mirror 的款换边）、这块屏上多大重新量一遍，窗口夹回屏里，图对不上就重出，位置存下来。"""
        world = self.host.world
        a = world.areas[t.area]
        t.screen = a.name
        t.right_half = t.x > (a.left + a.right) / 2
        self._fit(t)
        t.x = self._clamp_x(t, t.x)
        key = t.geo + (self._dpr(t.area),)
        if key != t.shot_key:
            if not t.need_shot:
                t.need_shot, t.shot_wait = True, 0.0
            cached = self._shots.get(key)
            if cached is not None:
                t.shot, t.shot_key, t.need_shot = cached, key, False
        if t.state != "gone":
            self.shelf.move(t.key, a.name, (t.x - a.left) / max(1.0, a.right - a.left))

    def _clamp_x(self, t: Thing, x: float) -> float:
        """窗口整个留在它那块屏的可用宽度里（不骑交界）；比屏还宽的放正中。"""
        a, lay = self.host.world.areas[t.area], t.lay
        lo, hi = a.left + lay.cx, a.right - (lay.w - lay.cx)
        return (a.left + a.right) / 2 if lo > hi else min(max(x, lo), hi)

    def _dpr(self, area: int) -> float:
        name = self.host.world.areas[area].name
        screen = next((s for s in QGuiApplication.screens() if s.name() == name), None) or QGuiApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen is not None else 1.0

    def _area_named(self, name: str) -> int:
        """叫这个名字的屏是第几块；不在了（拔了）就是主屏。"""
        areas = self.host.world.areas
        i = next((i for i, a in enumerate(areas) if a.name == name), None)
        if i is None:
            primary = QGuiApplication.primaryScreen()
            i = next((i for i, a in enumerate(areas) if primary is not None and a.name == primary.name()), 0)
        return i

    def _area_at(self, x: float, y: float, fallback: int) -> int:
        """(x, y) 在哪块屏：先看可用区域，再看整块屏（鼠标在菜单栏、程序坞那一条上）；都不在就还是原来那块。"""
        world = self.host.world
        i = world.area_index(x, y)
        if i is None and world.screens is not None:
            i = next((k for k, s in enumerate(world.screens) if s.contains(x, y)), None)
        return fallback if i is None or i >= len(world.areas) else i

    # ---------- 线：踩在哪 ----------
    def _floor(self, area: int, x: float) -> Support:
        """这块屏的地面（盖得住 x 的那一截；没有就是离得最近的地面）。"""
        world = self.host.world
        floors = [f for f in world.floors if f.key == area]
        hit = next((f for f in floors if f.covers(x)), None)
        if hit is not None:
            return hit
        a = world.areas[area]
        return min(floors, key=lambda f: abs(f.clamp(x) - x)) if floors else world.nearest_floor(x, a.bottom)

    def _tops(self, t: Thing) -> list[Support]:
        """这一件放得上去的窗口上沿：看得见、够宽放下它宽度的一半、上面放得下它那么高。「窗口当台子」关着没有。"""
        host = self.host
        if not host.w.hop_windows_on:
            return []
        host.supports()                            # 窗口表过时了就重问（0.25 秒一次，狗也用这一份）
        return host.world.window_tops(host._native_frames, max(40.0, 0.5 * t.width), t.height)   # 只看真窗口：物件不叠在物件上

    def _line_below(self, t: Thing) -> Support:
        """它正下方最近的线（地面或窗口上沿）；这一列没有线（两块屏上下摞着的那一段）就是最近的地面。"""
        world = self.host.world
        line = support_below(list(world.floors) + self._tops(t), t.x, t.y)
        return line if line is not None else world.nearest_floor(t.x, t.y)

    def _seat(self, t: Thing, line: Support) -> None:
        """坐到这条线上（不落、不 duang）。"""
        world = self.host.world
        t.state, t.vy, t.target, t.follow, t.fresh = ("rest" if t.state != "gone" else "gone"), 0.0, None, 0.0, False
        t.vx, t.slide, t.loud = 0.0, None, False
        t.x, t.y, t.on = line.clamp(t.x), line.y, (line.kind, line.key)
        if line.kind == "floor":
            t.area = line.key
            t.ride = None
        else:
            t.area = self._area_at(t.x, line.y - 1.0, t.area)
            f = next((f for f in self.host.frames if f.number == line.key), None)
            t.ride = (f.x, f.y) if f is not None else (line.x0, line.y)
        if t.lay is not None:
            t.x = self._clamp_x(t, t.x)
        self._staged(t)

    def _land(self, t: Thing, line: Support, thud: bool = True) -> None:
        was = t.state
        self._seat(t, line)
        self._settle(t)
        if thud and was != "gone":
            t.duang.pressing = False
            t.duang.value, t.duang.v = t.duang.DEPTH, 0.0          # 落地 duang 一下：压到底再弹回

    def _first_spot(self, t: Thing) -> Support:
        """第一次摆出来放哪：狗踩的那块屏的地面上，狗朝屏幕中间那一侧、离狗 FIRST_GAP_M 再加半个物件宽；那里已经有别的物件就再往外挪一个身位；
        放不下换另一侧。"""
        host, world, roam = self.host, self.host.world, self.host.roam
        i = world.area_index(roam.wx, roam.wy - 2.0)
        if i is None:
            floor = world.nearest_floor(roam.wx, roam.wy)
            i = floor.key
        a = world.areas[i]
        t.area = i
        d = 1.0 if roam.wx < (a.left + a.right) / 2 else -1.0
        gap = FIRST_GAP_M * host.ppm
        best = None
        for side in (d, -d):
            t.right_half = roam.wx + side * gap > (a.left + a.right) / 2
            t.geo = None
            self._fit(t)
            lay, ppm = t.lay, host.ppm
            half = (lay.right_m if side < 0 else lay.left_m) * ppm
            x = roam.wx + side * (gap + half)
            for _ in range(8):
                if self._clamp_x(t, x) != x:
                    break
                other = self._overlapping(t, x, i)
                if other is None:
                    best = x
                    break
                lo, hi = other.span()
                x = (hi + lay.left_m * ppm + 0.1 * ppm) if side > 0 else (lo - lay.right_m * ppm - 0.1 * ppm)
            if best is not None:
                break
        if best is None:                                           # 两边都放不下：夹在屏里，叠着就叠着
            t.right_half = roam.wx + d * gap > (a.left + a.right) / 2
            t.geo = None
            self._fit(t)
            best = self._clamp_x(t, roam.wx + d * (gap + 0.5 * t.width))
        t.x = best
        return self._floor(i, best)

    def _overlapping(self, t: Thing, x: float, area: int) -> Optional[Thing]:
        ppm = t.lay.frame.ppm
        lo, hi = x - t.lay.left_m * ppm, x + t.lay.right_m * ppm
        for o in self.items.values():
            if o is t or o.state == "gone" or o.area != area or o.lay is None or (o.on is not None and o.on[0] != "floor"):
                continue
            a, b = o.span()
            if a < hi and lo < b:
                return o
        return None

    # ---------- 每帧 ----------
    def update(self, dt: float) -> None:
        if not self.items:
            return
        self._shoot_one(dt)
        self._check_lost_release(dt)
        for t in list(self.items.values()):
            if t.state == "tap":
                t.tap_age += dt
                if t.tap_age >= self._tap_hold:
                    self._pick_up(t)
            if t.state == "held":
                self._carry(t)
            elif t.state == "fall":
                self._fall(t, dt)
        self._check_lines(dt)
        if self._resize_in is not None:
            self._resize_in -= dt
            if self._resize_in <= 0.0:
                self._resize_in = None
                self._resize_all()
        if self._dust is not None and self._dust.puffs:
            self._dust.step(dt)
        cursor = QCursor.pos()
        for t in list(self.items.values()):
            t.duang.step(dt)
            if t.alpha != t.fade_to:
                step = dt / FADE_S
                t.alpha = min(t.fade_to, t.alpha + step) if t.fade_to > t.alpha else max(t.fade_to, t.alpha - step)
                if t.state == "gone" and t.alpha <= 0.0:
                    self._remove(t)
                    continue
            self._sync(t)
            t.win.update_hit(cursor)
            if t.front_win is not None and (t.front_alpha > 0.0 or t.front_to > 0.0):
                self._step_front(t, dt)

    def _frame_of(self, t: Thing) -> tuple[QRect, QPointF]:
        """这一件的窗口该在哪：(方框, 图的左上角在窗口里哪)。底下、两边伸出它那块屏的那一截裁掉：窗口不骑在两块屏中间。"""
        lay, world = t.lay, self.host.world
        rect = QRect(round(t.x - lay.cx), round(t.y + lay.base - lay.h), lay.w, lay.h)
        s = (world.screens if world.screens is not None else world.areas)[t.area]
        clip = rect.intersected(QRect(round(s.left), round(s.top), round(s.right - s.left), round(s.bottom - s.top)))
        if clip.isEmpty():
            clip = rect
        return clip, QPointF(rect.left() - clip.left(), rect.top() - clip.top())

    def _sync(self, t: Thing) -> None:
        """窗口摆到它该在的地方（窗口那头没变就什么都不做）。"""
        clip, origin = self._frame_of(t)
        t.win.place(clip, origin, (float(t.lay.w), float(t.lay.h)), t.pivot, t.box, t.shot, t.duang.value, t.alpha)

    def _shoot_one(self, dt: float) -> None:
        """出一张还没出的图（一帧最多一张）：先出物件本身的，都出好了再出窝的前沿那一层的（显示着的先出，别的闲着时先备好：_front_due），
        最后是盆的另一个样子。画布没好（刚启动、单测没有显卡）不出；狗在动、窗口铺宽着时先等，最多 SHOT_WAIT_S。"""
        t = next((t for t in self.items.values() if t.need_shot and t.lay is not None), None)
        front, spare = None, None
        if t is None:
            front = self._front_due()
            if front is None:
                spare = next((s for s in map(self._spare, self.items.values()) if s is not None and s[1] not in self._shots), None)
                if spare is None:
                    return
            t = front if front is not None else spare[0]
        w = self.host.w
        if not w.view.ready():
            return
        t.shot_wait += dt
        if (w._scene_busy() or w._wide) and t.shot_wait < SHOT_WAIT_S:
            return
        dpr = self._dpr(t.area)
        key = spare[1] if spare is not None else t.geo + (dpr,) if front is None else t.geo + (dpr, "front")
        img = self._shots.get(key)
        if img is None:
            rim = t.style.spec.get("front_rim") if front is not None else None
            if isinstance(rim, Mapping):                   # 盆：前沿那一层拿整件那张图遮出来（只留近处盆沿以下），不另画
                whole = self._shots.get(t.geo + (dpr,))
                if whole is None:
                    return                                 # 整件的图还没出：等它（一帧最多出一张，下一帧再来）
                k = t.geo[1]
                img = thing_art.rim_front(whole, t.lay, float(rim.get("r", 0.1)) * k, float(rim.get("y", 0.07)) * k)
            else:
                if spare is not None:
                    model, lay = self._measure(spare[1][:5])
                else:
                    model, lay = (t.model if front is None else self._front_model(t)), t.lay
                img = thing_art.shoot(w.view, model, lay, dpr)
                if img.isNull():
                    return
                img.setDevicePixelRatio(dpr)
            self._shots[key] = img
        t.shot_wait = 0.0
        if spare is not None:
            return                                 # 盆的另一个样子先出好放着：换的那一下不用等
        if front is not None:
            t.front_shot, t.front_key = img, key
            if t.front_win is None:                # 窗口也这时建好（原生窗口先建出来，不显示）：狗第一次踩上来、歇进来不用现建（建窗口要等窗口系统）
                t.front_win = ThingWindow(self, t, front=True, tier=tier(t))
                t.front_win.winId()
            return
        if t.shot is None:
            t.alpha = 0.0                          # 第一张图出好了才淡入（之前窗口是空的）
        t.shot, t.shot_key, t.need_shot = img, key, False
        self._prune_shots()

    def _front_due(self) -> Optional[Thing]:
        """前沿那一层的图还没出、或者对不上现在的量（换了大小、换了屏）的窝：显示着的那个先出；别的也先备好——狗跑过狗窝踩上垫子只有一眨眼，
        那时狗在动、出图要等（SHOT_WAIT_S），等出来狗已经过去了。包里没写 front_z 的款没有这一层。都出好了 None。"""
        shown = self._front
        for t in ([shown] if shown is not None else []) + [t for t in self.items.values() if t is not shown]:
            if t.lay is None or t.state == "gone" or not has_front(t):
                continue
            if t.front_key != t.geo + (self._dpr(t.area), "front"):
                return t
        return None

    def _prune_shots(self) -> None:
        """没有哪一件还在用的图丢掉（收起来的款、换大小以前的）。"""
        used = {t.shot_key for t in self.items.values()} | {t.front_key for t in self.items.values()} \
            | {s[1] for s in map(self._spare, self.items.values()) if s is not None}
        for key in [k for k in self._shots if k not in used]:
            del self._shots[key]

    def _fall(self, t: Thing, dt: float) -> None:
        """在落（扔出去的、松手直着落的、脚下的线没了的、从设置里摆出来的）：照球的那一套（world.step_ball），只是按盒子算——左右按半宽、
        上下按高度。撞这块屏的边、天花板、「窗口交互」开着时别的 App 窗口的侧面和下沿弹回去；落到线上按包里的弹性弹、按摩擦滑（_slide），
        停了落定（_land），刚扔的、刚放下的告诉 playground（_placed）。指定了落在哪条线（target：从设置里摆出来的）只认那一条、不撞窗口。"""
        host, world = self.host, self.host.world
        hw, h = 0.5 * t.width, t.height
        lines = [t.target] if t.target is not None else list(world.floors) + self._tops(t)
        edges = world.window_edges(host._native_frames) if (host.w.hop_windows_on and t.target is None) else ()
        g = GRAVITY_M * host.ppm
        n = max(1, min(32, math.ceil(max(abs(t.vx), abs(t.vy), g * dt) * dt / max(3.0, 0.3 * min(hw, max(h, 1.0))))))
        step = dt / n
        for _ in range(n):
            if t.state != "fall":
                return
            if t.slide is not None:
                self._slide(t, step)
            else:
                self._fly(t, step, g, hw, h, lines, edges)

    def _fly(self, t: Thing, step: float, g: float, hw: float, h: float, lines: list, edges) -> None:
        """在空中走一小步（_fall 分的）。"""
        world, ppm, phys = self.host.world, self.host.ppm, t.phys
        a = world.areas[t.area]
        e_wall = min(WALL_E[1], WALL_E[0] + phys.bounce)
        t.vy += g * step
        nx, ny = t.x + t.vx * step, t.y + t.vy * step
        if t.vx > 0 and nx + hw > a.right:                              # 这块屏的左右边：墙（物件不骑交界，见 _carry）
            nx = a.right - hw - (nx + hw - a.right)
            t.vx = -t.vx * e_wall
        elif t.vx < 0 and nx - hw < a.left:
            nx = a.left + hw + (a.left - (nx - hw))
            t.vx = -t.vx * e_wall
        if t.vy < 0 and ny - h < a.top:                                 # 天花板
            ny = a.top + h
            t.vy = -t.vy * e_wall
        for e in edges:                                                 # 别的 App 窗口的左右边、下边：从外面撞上来弹回去（和球一样）
            if e.side == "left":
                if t.vx > 0 and t.x + hw <= e.at + EPS and nx + hw > e.at and ny > e.lo and ny - h < e.hi:
                    nx, t.vx = e.at - hw, -t.vx * e_wall
            elif e.side == "right":
                if t.vx < 0 and t.x - hw >= e.at - EPS and nx - hw < e.at and ny > e.lo and ny - h < e.hi:
                    nx, t.vx = e.at + hw, -t.vx * e_wall
            elif t.vy < 0 and t.y - h >= e.at - EPS and ny - h < e.at and nx + hw > e.lo and nx - hw < e.hi:
                ny, t.vy = e.at + h, -t.vy * e_wall
        if t.vy > 0:                                                    # 地面、窗口上沿：只接往下落的，上一步还在线以上；同时碰到几条取最高的
            hit = None
            for line in lines:
                if line.covers(nx) and t.y <= line.y + EPS and ny >= line.y and (hit is None or line.y < hit.y):
                    hit = line
            if hit is None and ny > world.floor_y(t.area):              # 兜底：不该穿过自己那块屏的地面
                hit = self._floor(t.area, nx)
            if hit is not None:
                ny = hit.y
                down = t.vy
                self._impact(t, down, hit)
                t.vx *= LAND_KEEP
                if down * phys.bounce >= REST_BOUNCE_M * ppm:
                    t.vy = -down * phys.bounce
                else:
                    t.vy, t.slide = 0.0, hit
        t.x, t.y = nx, ny

    def _slide(self, t: Thing, step: float) -> None:
        """落到线上以后贴着它滑一小步，按包里的摩擦慢下来；滑出了线头往下掉；停了落定。"""
        line, ppm = t.slide, self.host.ppm
        if not line.covers(t.x):
            t.slide = None                                              # 滑出了线头（窗口上沿到头了）：往下掉
            return
        decel = t.phys.friction * ppm * step
        t.vx = 0.0 if abs(t.vx) <= decel else t.vx - math.copysign(decel, t.vx)
        a, hw = self.host.world.areas[t.area], 0.5 * t.width
        nx = t.x + t.vx * step
        if nx + hw > a.right:
            nx, t.vx = a.right - hw, -t.vx * WALL_E[0]
        elif nx - hw < a.left:
            nx, t.vx = a.left + hw, -t.vx * WALL_E[0]
        t.x, t.y = nx, line.y
        if abs(t.vx) < SLIDE_STOP_M * ppm:
            fresh = t.fresh
            self._land(t, line, thud=False)                             # 落地那一下已经压扁过（_impact）
            if fresh:
                self._placed(t)

    def _impact(self, t: Thing, down: float, line: Support) -> None:
        """落到线上的那一下（往下 down 像素 / 秒）：按撞得多重压扁（包里的软硬）、出声（你扔的、放下的才响）、重的扬灰、震旁边的东西。"""
        ppm, phys = self.host.ppm, t.phys
        k = min(1.0, down / (IMPACT_FULL_M * ppm))
        if k < 0.05:
            return
        top = t.lay.top_m if t.lay is not None else 1.0
        depth = min(phys.squash * (0.35 + 0.65 * k), LAND_REACH_M / max(top, 1e-3))
        if depth > t.duang.value:
            t.duang.pressing = False
            t.duang.value, t.duang.v = depth, 0.0
            t.duang.omega_scale = max(0.1, phys.recover)
            t.duang.zeta_min = 1.0 if phys.recover < 0.8 else 0.0         # 软的不弹过头：压扁一大下再慢慢鼓回来
        if t.loud and t.style.land_sound is not None and k >= 0.12:
            sounds.play_file(t.style.land_sound, phys.volume * (0.35 + 0.65 * k))
        if phys.dust > 0.0 and k >= 0.2:
            self._dust_at(t, line, phys.dust * k)
        if phys.shake > 0.0 and k >= 0.2:
            self._shake(t, line, phys.shake * k)

    def _dust_at(self, t: Thing, line: Support, strength: float) -> None:
        """脚下扬起一圈灰（widget/dust.py：只在落地那一刻出现的透明小窗口，点得穿）。"""
        if self._dust is None:
            self._dust = DustCloud()
        self._dust.burst(t.x, line.y, t.width, strength, self.host.ppm)

    def _shake(self, t: Thing, line: Support, strength: float) -> None:
        """重的落地震一下：同一条线上 SHAKE_REACH_M 以内停着的轻东西（盆）跳一小下（不出声、不算挪了地方）；球、狗交给 playground。"""
        ppm = self.host.ppm
        reach = SHAKE_REACH_M * ppm
        for o in self.items.values():
            if o is t or o.state != "rest" or o.on != (line.kind, line.key) or o.phys.mass_kg >= HOP_MASS_KG:
                continue
            d = abs(o.x - t.x)
            hop = HOP_M * ppm * strength * (1.0 - d / reach)
            if d >= reach or hop < 0.2 * ppm:
                continue
            o.state, o.vx, o.vy, o.slide, o.target, o.fresh, o.loud = "fall", 0.0, -hop, None, None, False, False
        self.host.thing_thudded(t.x, line, strength)

    def _check_lines(self, dt: float) -> None:
        """站在别的窗口顶上的：窗口表每重问一次对一遍；窗口在挪的那一小会每帧问这一个窗口跟着挪。"""
        riders = [t for t in self.items.values() if t.state in ("rest", "tap") and t.on is not None and t.on[0] == "window"]
        if not riders:
            return
        host = self.host
        if not host.w.hop_windows_on:              # 「窗口当台子」关了：别的 App 的窗口都不算台子，落下去
            for t in riders:
                self._drop(t)
            return
        host.supports()                            # 到点了就重问窗口表（狗、球用的也是这一份）
        fresh = host._frames_at != self._frames_seen
        self._frames_seen = host._frames_at
        for t in riders:
            number = t.on[1]
            if t.follow > 0.0:
                t.follow = max(0.0, t.follow - dt)
                f = host._frame(number)
                if f is None:
                    self._drop(t)
                    continue
                self._ride(t, f[0], f[1])
            if not fresh:
                continue
            f = next((f for f in host.frames if f.number == number), None)
            if f is None:
                self._drop(t)                      # 窗口没了、切走了
                continue
            self._ride(t, f.x, f.y)
            if t.state == "fall" or not any(s.key == number and s.covers(t.x) for s in self._tops(t)):
                self._drop(t)                      # 脚下那一段被前面的窗口盖住了、窗口挪得放不下了

    def _ride(self, t: Thing, left: float, top: float) -> None:
        """脚下的窗口现在在 (left, top)：挪了就跟着挪，接下来 FOLLOW_S 秒每帧问它。挪出了屏就落下去。"""
        if t.ride is None or (left, top) == t.ride:
            return
        t.x += left - t.ride[0]
        t.y = top
        t.ride = (left, top)
        t.follow = FOLLOW_S
        i = self.host.world.area_index(t.x, t.y - 1.0)
        if i is None:
            self._drop(t)
            return
        if i != t.area:
            t.area = i
            self._fit(t)
        t.x = self._clamp_x(t, t.x)
        self._staged(t)

    def _drop(self, t: Thing) -> None:
        if t.state == "tap":
            t.duang.release()
            if self._held is t:
                self._held = None
                t.win.let_go()
        t.state, t.on, t.vy, t.target, t.ride, t.follow, t.fresh = "fall", None, 0.0, None, None, 0.0, False
        t.vx, t.slide, t.loud = 0.0, None, False
        self._left(t)

    def _resize_all(self) -> None:
        """大小停稳了：每件按新大小重排一次（窗口各改一次大小），图重出。"""
        for t in self.items.values():
            was = self.spot_of(t) if t.nest else None
            t.target = None
            self._fit(t)
            if t.state in ("rest", "tap", "gone") and t.on is not None and t.on[0] == "floor":
                self._seat(t, self._floor(t.area, t.x))
            if t.state != "held":
                self._settle(t)
            if was is not None and not self._same_spot(was, self.spot_of(t)):
                self._left(t)                      # 窝换了大小、狗歇的地方挪了：里面的狗站起来，下次歇再过去
            self._staged(t)
        self._frames_seen = None                   # 站在窗口上的：下一帧对一遍放不放得下

    # ---------- 游乐场那头的几件事 ----------
    def pet_changed(self) -> None:
        """换了一只狗（换模型，playground.pet_arrived）：狗窝（fit_pet 的款）按新狗的身高当场重排，位置不动，图一帧一件重出（和拖大小停稳以后同一条路，
        图没出来的那一两帧是旧图）；盆、狗屋不变。狗屋门口留多远下次问的时候按新狗趴着的身长算（spot_of 现读 host.dog）。"""
        if self.items:
            self._resize_all()

    def scale_changed(self) -> None:
        if self.items:
            self._resize_in = RESIZE_SETTLE_S

    def floor_changed(self) -> None:
        """程序坞出来 / 收起：站在地面上的按新地面重新坐好（直接到位、duang 一下）。"""
        for t in self.items.values():
            t.target = None                        # 在落的：原来指定的那条地面作废，落到现在正下方的
            if t.state in ("rest", "tap") and t.on is not None and t.on[0] == "floor":
                y = t.y
                t.area = self._area_named(t.screen)
                self._seat(t, self._floor(t.area, t.x))
                if abs(t.y - y) > 0.5:
                    self._left(t)
                    self._land(t, self._floor(t.area, t.x))

    def screens_changed(self) -> None:
        """接上 / 拔掉显示器、改分辨率：每件回到它那块屏（不在了就是主屏）的地面上，照记着的那一成宽。"""
        world = self.host.world
        for t in self.items.values():
            if t.state == "held":
                continue
            self._left(t)
            gone = not any(a.name == t.screen for a in world.areas)
            t.area = self._area_named(t.screen)
            a = world.areas[t.area]
            spot = self.shelf.spot(t.key)
            if gone and spot is not None:
                t.x = a.left + spot[1] * (a.right - a.left)
            t.geo = None
            self._fit(t)
            self._seat(t, self._floor(t.area, t.x))
            self._settle(t)

    def live_windows(self) -> list:
        """看得见的物件窗口（狗那一层：截图时照常画，不抓、不换成快照）。"""
        return [t.win for t in self.items.values() if t.win.isVisible()] \
            + [t.front_win for t in self.items.values() if t.front_win is not None and t.front_win.isVisible()]

    def quiet(self) -> bool:
        """什么都没在动：没在拖、没在落、没在淡入淡出、duang 弹完了、没有等着出的图、没在跟着窗口挪。"""
        if self._resize_in is not None or self._fade.state() == QVariantAnimation.Running:
            return False
        ready = None
        for t in self.items.values():
            if t.state != "rest" or t.alpha != t.fade_to or t.follow > 0.0 or t.duang.pressing or t.duang.value != 0.0:
                return False
            if t.front_alpha != t.front_to:
                return False
            if t.need_shot:
                ready = self.host.w.view.ready() if ready is None else ready
                if ready:
                    return False
        return True

    def near(self, cursor, margin: int) -> bool:
        """鼠标在哪件物件的窗口旁边（省电模式：有人要碰了，回满帧）。"""
        return any(t.win.isVisible() and t.win.geometry().adjusted(-margin, -margin, margin, margin).contains(cursor) for t in self.items.values())

    # ---------- 窝：狗歇在哪、前沿那一层 ----------
    def has_nests(self) -> bool:
        """摆着窝没有（一件没摆：假，playground._lounge 那几行不走）。"""
        return any(t.nest for t in self.items.values())

    def nest_spots(self) -> list[NestSpot]:
        """现在能歇的窝各在哪（摆着、没被拿着、没在落、没在收，踩的那条线站得下狗）。够不够得着由 playground 问 roam。"""
        out = []
        for t in self.items.values():
            spot = self.spot_of(t) if t.nest else None
            if spot is not None:
                out.append(spot)
        return out

    def _dog_line(self, t: Thing) -> Optional[Support]:
        """这一件踩的那条线，狗也站得上去的（地面，或站得下狗的窗口上沿）；拿着、在落、在收的，线站不下狗的：None。"""
        if t.state not in ("rest", "tap") or t.on is None or t.lay is None:
            return None
        kind, key = t.on
        host = self.host
        lines = host.world.floors if kind == "floor" else host.supports()
        return next((s for s in lines if s.kind == kind and s.key == key and s.covers(t.x)), None)

    def spot_of(self, t: Thing) -> Optional[NestSpot]:
        """狗歇在这个窝的哪（包里的 rest）。side 0：歇在物件正中偏 x 的地方（米 × 倍数），rise 不是 0 就把根抬到垫子上（狗窝），是 0 就趴在它前面的地上（平顶狗屋门前）；
        side 1：歇在门朝的那一侧外面，头朝外——离物件那条边 rest.x 米再加狗趴着身后那一截（按模型量，dog.lie_span × 四分之三朝向），
        那一侧放不下（线到头了）换到物件正前面，还放不下这个窝不算。"""
        line = self._dog_line(t) if t.nest else None
        if line is None:
            return None
        rest, ppm, k = t.style.spec["rest"], self.host.ppm, t.geo[1]
        rx = float(rest.get("x", 0.0))
        if not int(rest.get("side", 0)):
            x = t.x + rx * k * ppm
            return NestSpot(t.key, line, x, self._perch_of(t), None) if line.covers(x) else None
        yaw = t.geo[2]
        a = self.host.world.areas[t.area]
        d = 1.0 if yaw > 0.0 else -1.0 if yaw < 0.0 else (1.0 if t.x < (a.left + a.right) / 2 else -1.0)   # 门朝哪边（转过去的那一边；正着摆的朝屏幕中间）
        rear, fore = (v * QUARTER_COS * ppm for v in self.host.dog.lie_span())
        lo, hi = t.span()
        x = (hi if d > 0.0 else lo) + d * (rx * ppm + rear)
        if not (line.covers(x) and line.covers(x + d * fore)):
            x = t.x                                                # 那一侧放不下：屋的正前面（盖住一部分屋）
            if not (line.covers(x - d * rear) and line.covers(x + d * fore)):
                return None
        return NestSpot(t.key, line, x, 0.0, YAW_HEAD_RIGHT if d > 0.0 else YAW_HEAD_LEFT)

    def nest_spot(self, key: str) -> Optional[NestSpot]:
        """这一款窝现在能歇在哪（刚摆下来的那一个：playground.thing_placed）；不是窝、没摆着、被拿着、在落、线站不下狗：None。"""
        t = self.items.get(key)
        return self.spot_of(t) if t is not None and t.nest else None

    @staticmethod
    def _perch_of(t: Thing) -> float:
        """狗在这个窝的垫子上，根要抬多高（米）：（画面上原点比最低点高的那一截 + 包里 rest.rise × 倍数）÷ cos 俯视角；rise 是 0（狗屋）不抬。"""
        rest = t.style.spec["rest"]
        rise = float(rest.get("rise", 0.0))
        if rise <= 0.0 or int(rest.get("side", 0)):
            return 0.0
        return (t.lay.low_m + rise * t.geo[1]) / math.cos(math.radians(ELEVATION))

    def pad_half_m(self, key: str) -> Optional[float]:
        """这个狗窝的垫子横着半宽（米，窝正中往两边各多少，和 pad_at 同一个范围）：狗歇在里面时尾巴尖要落在它里面（playground.settle_in 量尾巴卷多少）。
        不是有垫子的窝（狗屋、平地上的）None。"""
        t = self.items.get(key)
        if t is None or not t.nest or t.lay is None or self._perch_of(t) <= 0.0:
            return None
        rest = t.style.spec["rest"]
        if rest.get("half") is not None:
            return float(rest["half"]) * t.geo[1]
        return PAD_SHARE * 0.5 * t.width / t.lay.frame.ppm

    def pad_at(self, kind: str, key: int, x: float) -> Optional[tuple[str, float]]:
        """狗站在（kind, key）这条线上的 x（身子正中）：脚下是哪个狗窝的垫子——(哪一款, 根该抬多高)；不在哪个垫子上 None。
        垫子 = 根要抬的窝（_perch_of 大于 0：狗窝；狗屋不算，狗从屋前面过）、停着的（拿着、在落、在收的不算）、踩的是同一条线；
        横着的范围：窝正中偏 rest.x，左右各 rest.half（米，模型单位 × 倍数；包里没写按画出来宽度的 PAD_SHARE）。"""
        for t in self.items.values():
            if not t.nest or t.state not in ("rest", "tap") or t.on != (kind, key) or t.lay is None:
                continue
            perch = self._perch_of(t)
            if perch <= 0.0:
                continue
            rest, ppm, k = t.style.spec["rest"], t.lay.frame.ppm, t.geo[1]
            half = float(rest["half"]) * k * ppm if rest.get("half") is not None else PAD_SHARE * 0.5 * t.width
            if abs(x - (t.x + float(rest.get("x", 0.0)) * k * ppm)) <= half:
                return t.key, perch
        return None

    @staticmethod
    def _same_spot(a: Optional[NestSpot], b: Optional[NestSpot]) -> bool:
        return a is not None and b is not None and (a.support.kind, a.support.key) == (b.support.kind, b.support.key) \
            and abs(a.x - b.x) <= 2.0 and abs(a.support.y - b.support.y) <= 1.0 and abs(a.perch_m - b.perch_m) <= 0.002

    def spot_holds(self, spot: NestSpot) -> bool:
        """这一处还在不在（窝没被拿走、没挪地方）：狗走到了、要趴下之前问一次。"""
        t = self.items.get(spot.key)
        return t is not None and self._same_spot(spot, self.spot_of(t))

    def _left(self, t: Thing) -> None:
        """这一件离开原地了（拿起、落下去、收起、挪了）：是窝就告诉 playground——歇在里面的狗站起来，正往这走的站住；是盆——正往这来、正吃着的站住。"""
        if t.nest:
            self.host.nest_gone(t.key)
        if t.serves is not None:
            self.host.bowl_gone(t.key)
        self._staged(t)

    def _placed(self, t: Thing) -> None:
        """这一件刚摆出来、刚被你拖完松手，落定了：告诉 playground（thing_placed：狗闲着就过来；来不来它定）。"""
        t.fresh = False
        self.host.thing_placed(t.key)

    # ---------- 台子：混进窗口表的假窗口框 ----------
    def _staged(self, t: Thing) -> None:
        """这件台子坐好了、挪了、离开了：窗口表要重拼（playground.platforms_changed，不重问系统）。不是台子什么都不做。"""
        if t.platform is not None:
            self.host.platforms_changed()

    def frame_of(self, t: Thing) -> Optional[WindowFrame]:
        """这件台子现在的假窗口框：左、台面上沿、宽、往下多厚。不是台子、被拿着、在落、在收：None。
        台面在屏幕上的 y = 它踩的线 −（layout.low_m + 包里 platform.y × 倍数 × cos 俯视角）× 比例尺。
        包里的 thick 不比台面的高度小（厚到模型的地面）= 实心盒子：框一直到它踩的那条线；不然是一块薄板（底下是空的）。"""
        if t.platform is None or t.state not in ("rest", "tap") or t.on is None or t.lay is None:
            return None
        p, k, ppm = t.platform, t.geo[1], self.host.ppm
        ce = math.cos(math.radians(ELEVATION))
        x0, x1 = float(p.get("x0", 0.0)) * k, float(p.get("x1", 0.0)) * k
        if t.style.spec.get("mirror") and t.right_half:
            x0, x1 = -x1, -x0
        high, deep = float(p.get("y", 0.0)), float(p.get("thick", 0.1))
        top = t.y - (t.lay.low_m + high * k * ce) * ppm
        thick = t.y - top if deep >= high else deep * k * ce * ppm
        return WindowFrame(t.number, 0, t.x + x0 * ppm, top, (x1 - x0) * ppm, thick) if x1 > x0 and thick > 0.0 else None

    def frames(self) -> list[WindowFrame]:
        """摆着、停着的台子各一个假窗口框（排在真窗口前面：物件本来就画在所有 App 的窗口上面）。一个台子都没有：空的。"""
        return [f for f in map(self.frame_of, self.items.values()) if f is not None]

    def frame(self, number: int) -> Optional[WindowFrame]:
        """这个假窗口号的台子现在的框（狗、球站在上面时每帧问；台子跟着脚下的窗口挪时是它这一帧在哪）；没有了 None。"""
        t = next((t for t in self.items.values() if t.number == number), None)
        return self.frame_of(t) if t is not None else None

    def show_front(self, key: str) -> None:
        """狗歇进这个窝了：前沿那一层盖到狗前面（包里没写 front_z 的款没有这一层）。窗口第一次用时才建；图下一帧出，出好之前这一层是空的。"""
        t = self.items.get(key)
        if self._front is not None and self._front is not t:
            self.hide_front()
        if t is None or t.lay is None or not has_front(t):
            return
        self._front, t.front_to = t, 1.0
        if t.front_win is None:
            t.front_win = ThingWindow(self, t, front=True, tier=tier(t))
        self._sync_front(t)
        if not t.front_win.isVisible():
            t.front_win.show()                                     # 狗跟着换到这一档里（rims_changed）

    def hide_front(self, now: bool = False) -> None:
        """狗起来了：前沿那一层淡掉（now：当场藏，关灵动交互时没有下一帧）。"""
        t, self._front = self._front, None
        if t is None:
            return
        t.front_to = 0.0
        if now and t.front_win is not None:
            t.front_alpha = 0.0
            t.front_win.hide()

    def front_shown(self, key: str) -> bool:
        t = self.items.get(key)
        return t is not None and t is self._front and t.front_win is not None and t.front_win.isVisible()

    def rims_changed(self) -> None:
        """前沿的窗口显示了 / 藏起来了（ThingWindow 的 showEvent、hideEvent 叫；淡出完才藏）：狗换到它在的那一档里——
        窝沿显示着，狗在窝和窝沿之间、盆后面（native.LEVEL_DOG_IN）；都没有就回到所有物件前面（LEVEL_DOG；在盆边吃喝也是这层，盆沿在它前面）。"""
        tiers = [tier(t) for t in self.items.values() if t.front_win is not None and t.front_win.isVisible()]
        self.host.w.set_dog_level(min((native.LEVEL_DOG_IN[k] for k in tiers), default=native.LEVEL_DOG))

    def covers_dog(self, pos) -> bool:
        """全局坐标 pos 上有没有盖在狗前面的物件：层级比狗高的窗口（前沿；狗趴在窝里时还有盆）这一点看得见（图上够不透明，ThingWindow.covers）。
        狗的点击范围扣掉这里（input._covered：前沿点得穿，点在窝沿上落到被它挡住的狗身上）。图还没出好、淡得快看不见的不算。"""
        dog = self.host.w.level
        for t in self.items.values():
            for win in (t.win, t.front_win):
                if win is not None and win.level > dog and win.isVisible() and win.shot is not None and win.alpha >= 0.5 \
                        and win.geometry().contains(pos) and win.covers(QPointF(pos - win.pos())):
                    return True
        return False

    def _front_model(self, t: Thing):
        """前沿那一层的模型：比包里 front_z（× 倍数）更靠镜头的面。按现在量的切，量变了重切。"""
        if t.front_model is None or t.front_model[0] != t.geo:
            t.front_model = (t.geo, thing_art.front_part(t.model, float(t.style.spec["front_z"]) * t.geo[1]))
        return t.front_model[1]

    def _sync_front(self, t: Thing) -> None:
        """前沿的窗口和物件的窗口摆在同一处、同一个画面（两张图对得上），跟着一起 duang；图对不上现在的量（换了大小、换了屏）就先空着。"""
        clip, origin = self._frame_of(t)
        shot = t.front_shot if t.front_key is not None and t.front_key[:len(t.geo)] == t.geo else None
        t.front_win.place(clip, origin, (float(t.lay.w), float(t.lay.h)), t.pivot, t.box, shot, t.duang.value, t.front_alpha * t.alpha)

    def _step_front(self, t: Thing, dt: float) -> None:
        """前沿那一层淡入淡出走一步、摆好；淡完了藏起来。"""
        if t.front_alpha != t.front_to:
            step = dt / FRONT_FADE_S
            t.front_alpha = min(t.front_to, t.front_alpha + step) if t.front_to > t.front_alpha else max(t.front_to, t.front_alpha - step)
        if t.front_alpha <= 0.0 and t.front_to <= 0.0:
            t.front_win.hide()
            return
        self._sync_front(t)

    # ---------- 盆：满的、空的 ----------
    def bowl_spot(self, key: str) -> Optional[tuple[Support, float, bool]]:
        """狗来吃这个盆：(盆踩的那条线, 盆心的 x, 是不是水)。不是盆、被拿着、在落、在收，线站不下狗：None。"""
        t = self.items.get(key)
        line = self._dog_line(t) if t is not None and t.serves is not None else None
        return (line, t.x, t.serves == "water") if line is not None else None

    def bowl_full(self, key: str) -> bool:
        """这一款是盆、摆着、现在满着（刚落定的满盆：playground.thing_placed 叫狗来吃）。"""
        t = self.items.get(key)
        return t is not None and t.serves is not None and t.full and t.state != "gone"

    def set_full(self, t: Thing, full: bool) -> None:
        """盆添满 / 吃空：换成另一个模型的图（另一张闲着的时候已经出好了就当场换；没出好旧图先撑着，下一帧出）。"""
        if t.serves is None or t.full == bool(full):
            return
        t.full = bool(full)
        if t.empty_model is None or t.lay is None:
            return
        self._fit(t)
        key = t.geo + (self._dpr(t.area),)
        cached = self._shots.get(key)
        if cached is not None:
            t.shot, t.shot_key, t.need_shot = cached, key, False
        else:
            t.need_shot, t.shot_wait = True, 0.0

    def empty(self, key: str) -> None:
        """狗把这个盆吃空了（playground.bowl_emptied）。"""
        t = self.items.get(key)
        if t is not None:
            self.set_full(t, False)

    # ---------- 鼠标（thing_win 转过来） ----------
    def thing_press(self, t: Thing, pos, at: Optional[float] = None) -> None:
        """按在物件上：先 duang；按久了、挪了才算拿起（_pick_up）。正在落的马上接住。"""
        if t.state == "gone" or t.key not in self.items:
            return
        self.host.w.hide_thing_menu()
        t.win.raise_()                             # 提到它那一档的最前面（系统在点完以后本来也会提），重开也是它在前
        self.shelf.to_front(t.key)
        self._held = t
        self._lost.reset()
        t.tap_at = t.pointer = (pos.x(), pos.y())
        t.tap_age = 0.0
        t.hand.clear()
        t.hand.append((time.perf_counter() if at is None else at, pos.x(), pos.y()))
        info = native.pointer_event()
        t.from_pad = info is not None and info[0] == native.TOUCH_SUBTYPE
        t.duang.omega_scale, t.duang.zeta_min = 1.0, 0.0                # 点、按的 duang 用平常的弹簧（落地压扁另调过）
        if t.state == "fall":
            self._pick_up(t)
            return
        t.state = "tap"
        t.duang.press()

    def thing_drag(self, t: Thing, pos, at: Optional[float] = None) -> None:
        if t.state == "tap":
            if abs(pos.x() - t.tap_at[0]) < self._tap_move and abs(pos.y() - t.tap_at[1]) < self._tap_move:
                return
            self._pick_up(t)
        if t.state == "held":
            t.pointer = (pos.x(), pos.y())         # 只记位置：窗口每帧挪一次（update → _carry）
            self._note_hand(t, time.perf_counter() if at is None else at, pos.x(), pos.y())

    def thing_release(self, t: Thing, pos, at: Optional[float] = None) -> None:
        if self._held is t:
            self._held = None
        if t.state == "tap":                       # 只是点了一下：duang 弹回；盆 = 敲盆（添满、叫狗来吃），窝 = 叫狗过来趴进这一个
            t.state = "rest"
            t.duang.release()
            if t.serves is not None:
                self.set_full(t, True)
                self.host.bowl_tapped(t.key)
            elif t.nest:
                self.host.nest_tapped(t.key)
        elif t.state == "held":
            now = time.perf_counter() if at is None else at
            t.pointer = (pos.x(), pos.y())
            self._note_hand(t, now, pos.x(), pos.y())
            self._carry(t)
            vx, vy = self._hand_velocity(t, now)
            if math.hypot(vx, vy) >= THROW_MIN_M * self.host.ppm:
                self._throw(t, vx, vy)
            else:
                self._release(t)

    @staticmethod
    def _note_hand(t: Thing, now: float, x: float, y: float) -> None:
        t.hand.append((now, x, y))
        while len(t.hand) > 2 and now - t.hand[0][0] > THROW_WINDOW_SYS + THROW_SAMPLE:
            t.hand.popleft()

    @staticmethod
    def _hand_velocity(t: Thing, now: float) -> tuple[float, float]:
        """松手时手多快：松手前 THROW_SAMPLE 秒的平均速度；系统开了三指拖移的往前看一段里最快的那一下（和球一样，playground._release_velocity）。"""
        if t.from_pad and native.trackpad_system_drag():
            return hand.peak_velocity(t.hand, now, THROW_SAMPLE, THROW_WINDOW_SYS, THROW_FADE_SYS)
        return hand.velocity(t.hand, now, THROW_SAMPLE)

    def _throw(self, t: Thing, vx: float, vy: float) -> None:
        """扔出去：越重出手越慢（MASS_REF_KG），封顶 THROW_MAX_M。之后照 _fall 飞、弹、滑。"""
        ppm = self.host.ppm
        gain = 1.0 / math.sqrt(1.0 + max(0.0, t.phys.mass_kg) / MASS_REF_KG)
        vx, vy = vx * gain, vy * gain
        speed, cap = math.hypot(vx, vy), THROW_MAX_M * ppm
        if speed > cap:
            vx, vy = vx * cap / speed, vy * cap / speed
        t.state, t.on, t.target, t.ride, t.follow = "fall", None, None, None, 0.0
        t.vx, t.vy, t.slide = vx, vy, None
        t.fresh = t.loud = True
        log.info("thing %s thrown: %.1f m/s", t.key, math.hypot(vx, vy) / ppm)

    def thing_menu(self, t: Thing, global_pos) -> None:
        if t.state != "gone":
            self.host.w.show_thing_menu(t.key, global_pos)

    def _pick_up(self, t: Thing) -> None:
        """拿起来了：从线上摘下来，跟手。"""
        t.duang.release()
        t.state, t.on, t.vy, t.target, t.ride, t.follow = "held", None, 0.0, None, None, 0.0
        t.vx, t.slide, t.loud = 0.0, None, False
        t.grab = (t.x - t.tap_at[0], t.y - t.tap_at[1])
        self.host.w.hide_thing_menu()
        self._left(t)

    def _carry(self, t: Thing) -> None:
        """拿着的每一帧：放在手上，窗口整个夹在鼠标所在那块屏里（左右、上沿；最低到那块屏的地面）。换了屏、那块屏上要缩小就当场按新的量。"""
        world = self.host.world
        px, py = t.pointer
        i = self._area_at(px, py, t.area)
        if i != t.area:
            t.area = i
            self._fit(t)
        a, lay = world.areas[i], t.lay
        t.x = self._clamp_x(t, px + t.grab[0])
        t.y = min(max(py + t.grab[1], a.top + (lay.h - lay.base)), world.floor_y(i))

    def _release(self, t: Thing) -> None:
        """松手：脚下就是线就原地放下，不然直着落下去。落定那一下告诉 playground（_placed）。"""
        line = self._line_below(t)
        if abs(line.y - t.y) <= LAND_NEAR_PX:
            self._land(t, line, thud=False)
            self._placed(t)
        else:
            t.state, t.vy, t.target, t.fresh = "fall", 0.0, None, True
            t.vx, t.slide, t.loud = 0.0, None, True

    def _let_go_now(self) -> None:
        t, self._held = self._held, None
        if t is None:
            return
        t.win.let_go()
        if t.state == "tap":
            t.state = "rest"
            t.duang.release()
        elif t.state == "held":
            self._release(t)

    def _check_lost_release(self, dt: float) -> None:
        """按着物件时松手事件丢了（按着的时候切走了、系统弹窗）：键松开 LOST_UP_S 秒还没来就当松了手——点着的弹回，拿着的原地落下。"""
        t = self._held
        if t is None or t.state not in ("tap", "held"):
            return
        if self._lost.gone(self.host._button_down(), dt, self._lost_after):
            log.info("thing release lost: letting go of %s", t.key)
            self._let_go_now()
