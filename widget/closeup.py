"""看细节（放大不挪狗、照主页面「大小」的规矩、一进来就站着）：详情页、自定义毛色页最上面一模一样的一块
（DetailRow，两行：转盘刻度尺 + 放大滑块；站 / 坐 / 趴 + 放大的百分比 + 长按回到 100%），直接在桌面那只大的上面转着看、换姿势看、放大看。
状态都在 Closeup（window.closeup，一个窗口一个），两页的那一块只转达、只显示。
- 转台：两页之一开着，狗就站在转台上（dog.set_turntable）：先站起来——不管在做什么（灵动交互开着在跑、关着趴着坐着睡着都一样），正做的一刀切。
  灵动交互开着的先临时退出（window.pause_play：这两页是看狗、摆姿势的，球不该在，狗也该能随便拖）：和关掉开关一样，开关不变不存；
  狗下了转台再回来（_release），和打开开关一样。为灵动交互加的那些（追球的停下、叼着的放下 Playground.fetch_on，走回窝、去吃、被拉去别处的
  就地站住 Playground.halt，只横着拖 drag_limit）这时用不上，留着当保险。
  朝向只听转盘：转盘转了 → dog.turntable_turn，狗 0.12 秒跟上；姿势听那一排站 / 坐 / 趴（dog.set_turntable_pose，各换一次）。
  离开两页、关卡片 → 0.5 秒走近的那边转回该朝的方向（window._home_yaw）、放大缩回去，差不到 1° 而且放大也收完了才放狗下来：
  回到进来前该待的姿势（关着灵动交互是选的姿势，开着是站着 / 自己歇成的样子）——这一页和临时放大一样是临时看的，离开就回到进来前的样子。
  朝向的弹簧在控制器里（play.Turntable）：只有它写 dog.yaw，这里只给去处。
- 放大（和主页面「大小」同样的逻辑、要能放得很大看清细节）：滑块、百分比（左右拖精调、单击原位输入，sizecontrol.SizeScrubber）
  从 100%（不放大）到上限；长按重置回到 100%。上限跟着狗在的那块屏走：放大的狗最大和「大小」的上限一样大（window.scale_range，狗站着约占屏高三分之二），
  所以存下来的越小能放的倍数越多（MacBook 上 100% 的狗能放到 400%）；放不到 1.1 倍（大小已经快到上限）就灰掉。
  以狗脚下的根为中心：放大、缩小、转圈、换姿势时根在屏幕上都不动；不躲卡片（挡到卡片就让它挡，用户自己会挪开），狗的窗口一直在卡片上面一层
  （狗在菜单栏上面那几层，native.LEVEL_DOG；卡片是普通的置顶小窗口），出了屏幕的那截就看不见。
  只是画得大（window.show_scaled）——不存大小，空间和球照旧按存下来的大小（window.world_scale），放大期间 roam 不走、滚轮捏合不改大小。
  拖着狗跟手地变（ZOOM_FOLLOW_S），滑块每过 10% tick 一声，百分比每过 1% 一声（和主页面的大小一样）。
  放大着能拖狗（drag_to，widget/input.py）：放大的狗跟着手，拖到哪就是它真在哪（不放大的根也挪过去，缩回来还在那）；能拖到哪按不放大的狗算
  （灵动交互里只横着挪、脚踩的线不动、待在站的窗口上；关着身子不出屏幕）。
  窗口在开始时按上限摆一次（window.hold_scaled，和拎着、飞着一样高；灵动交互里窗口本来就宽着，多半不用动），拖滑块、拖狗每帧只改画多大、画在哪
  （拖出了那一块才往那边长）；收完再摆回去（window.end_scaled）：中间不挪窗口、不改大小（改一次大小画布要重建）。
  狗在忙先记着，停下再放；换屏、改大小、换模式、换同桌当场收回（drop_zoom、finish）。
- 动画都是不过头的弹簧（animation.Spring），换去处用 retarget、跟滑块用 set_target；系统开了「减少动态效果」就直接到位。
不 import window、settings（window 建 Closeup；settings、coat_panel 建 DetailRow）。"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QObject, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QVBoxLayout, QWidget

from widget import native, sounds, sticker
from widget.animation import Spring
from widget.capture_ui import ui_frozen
from widget.i18n import tr
from widget.sizecontrol import SizeScrubber
from widget.states import POSTURES
from widget.turnruler import TurnRuler
from widget.wheel import is_notch, notches
from widget.widgets import TIGHT_CSS, FineSlider, HoldButton, SelectPill

ZOOM_MIN_GAIN = 1.1     # 上限不到存下来的大小的这么多倍（大小已经快到上限了）滑块、百分比就灰掉
ZOOM_S = 0.45           # 缩回去（离开这一页、关卡片、长按重置）的弹簧（秒基本到位，不过头）
ZOOM_FOLLOW_S = 0.12    # 拖滑块、百分比时狗跟上去的弹簧（和转盘一样跟手）
ZOOM_TICK = 10          # 滑块每过这么多（百分比）tick 一声；滚轮一格、方向键一下也走这么多
LEVEL_EPS = 1e-4        # 离 1 倍不到这么多就算没放大
ROWS_GAP = 8            # 那一块两行之间（比页里的行距 10 紧一点：看得出是一组）
TABLE_POSES = tuple(p for p in POSTURES if p[0] != "sleeping")   # 转台上能摆的姿势：站 / 坐 / 趴（看的是醒着的样子，不要睡）


@dataclass
class _Zoom:
    """一次放大：根钉在 (x, y)（狗脚下：放大、缩小、转圈、换姿势都不动，放大着拖狗才挪），倍数从 base（存下来的大小）放到滑块的 level 倍，
    一根弹簧（倍数取对数）。most：开始时按上限算的最大倍数（窗口照它摆了一次）。out：在缩回 base 的路上。"""
    base: float
    x: float
    y: float
    most: float
    level: float = 1.0
    out: bool = False
    spring: Spring = field(init=False)

    def __post_init__(self) -> None:
        self.spring = Spring(math.log(self.base), ZOOM_S, eps=1e-4)

    @property
    def k(self) -> float:
        """这一帧画多大（倍）。"""
        return math.exp(self.spring.value)

    @property
    def gain(self) -> float:
        """最多放到存下来的大小的几倍。"""
        return self.most / self.base

    def aim(self, k: float, instant: bool, response: float = ZOOM_S, follow: bool = False) -> None:
        """换去处。follow：跟着滑块连续地改（保留速度，set_target）；不然是换个新去处（不过头，retarget）。"""
        s = self.spring
        if follow:
            s.omega = 2.0 * math.pi / response
            s.set_target(math.log(k), instant=instant)
        else:
            s.retarget(math.log(k), response=response, instant=instant)

    def step(self, dt: float) -> None:
        self.spring.step(dt)

    @property
    def settled(self) -> bool:
        return self.spring.settled


class Closeup(QObject):
    """看细节的总管（一个窗口一个，window 每帧 tick）。设置卡片换页时 set_open；那一块转转盘 turn_by、点站 / 坐 / 趴 set_posture、拖滑块和百分比 set_level。"""
    changed = Signal()      # 放大到多少、最多能放多大、能不能放、转盘在哪、摆的什么姿势：两页的那一块跟着对齐（DetailRow.sync）

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self._open = False          # 两页之一开着
        self._holding = False       # 狗在转台上：从打开到转回来、缩回来放下
        self.level = 1.0            # 要放到存下来的大小的几倍（1 = 不放大；狗在忙时先记着，停下再放）
        self._z: Optional[_Zoom] = None
        self._pause_due = False     # 打开时狗在空中、被拎着：落地了再临时退出灵动交互（tick 看）

    # ---- 给别处看的 ----
    @property
    def open(self) -> bool:
        return self._open

    @property
    def holding(self) -> bool:
        return self._holding

    @property
    def zoom_on(self) -> bool:
        """不在 100%（要放大着；狗在忙时先记着）。"""
        return self.level > 1.0 + LEVEL_EPS

    @property
    def zoomed(self) -> bool:
        """放大着（放大、缩回的路上都算；和 window.showing_scaled 同进同出）。"""
        return self._z is not None

    @property
    def angle(self) -> float:
        """转盘尺该画在哪（度，不折回）：狗要转到的地方。"""
        return self.w.dog.turntable_angle

    @property
    def posture(self) -> Optional[str]:
        """狗在转台上摆的姿势（那一排站 / 坐 / 趴亮哪颗；「···」旁边的姿势条选了睡就一颗都不亮）；不在转台上 None。"""
        return self.w.dog.turntable_pose

    @property
    def moving(self) -> bool:
        """还在动（转台在转、在放大缩回）：窗口按它算有动静（省电模式不降帧）。"""
        z = self._z
        return self.w.dog.turntable_moving or (z is not None and not z.settled)

    def max_level(self) -> float:
        """最多放到存下来的大小的几倍（滑块、百分比的最右）：放大的狗最大和主页面「大小」的上限一样大（window.scale_range，跟着狗在的那块屏走），
        所以存下来的越小能放的倍数越多；已经比上限大的（从大屏挪过来的）1。页没开着 1；放大着按开始时定的（换屏、改大小会先收掉）。"""
        if not self._open:
            return 1.0
        z = self._z
        if z is not None and not z.out:
            return z.gain
        return max(1.0, self.w.scale_range()[1] / 100.0 / self.w.world_scale)

    def can_zoom(self) -> bool:
        """滑块、百分比现在能不能拖：那两页开着，而且上限至少是 ZOOM_MIN_GAIN 倍（已经放大着的当然能拖，好拖回来）。"""
        if not self._open:
            return False
        if self.zoom_on or self._z is not None:
            return True
        return self.max_level() >= ZOOM_MIN_GAIN - 1e-9

    # ---- 那两页、那一块调的 ----
    def set_open(self, on: bool) -> None:
        """详情页 / 自定义毛色页开着没有（settings.show_page，只有挂在窗口上的那张卡片调；两页之间换来换去不算离开）。
        打开：狗站上转台、先站起来（每次进来都是站着：转回去的路上又回来的也站起来）；手上的事就地停下。"""
        on = bool(on)
        if on == self._open:
            return
        self._open = on
        dog, pg = self.w.dog, self.w.playground
        if on:
            if self._holding:
                dog.turntable_stop()               # 转回去的路上又回来了：就近停住，不倒回来
                dog.set_turntable_pose("standing")
            else:
                self._pause_due = True             # 临时退出灵动交互：球、圈、物件收起，狗能随便拖（开关不变）；在空中、被拎着的落地再退
                self._pause_now()
                self._holding = True
                dog.set_turntable(True)            # 站起来，自己的事都停
                pg.fetch_changed()                 # 捡球的闸关了：在追的停下、叼着的放下、俯身的起来（退出了灵动交互就用不上，保险）
            pg.halt()                              # 走回窝、去吃、被拉去别处的就地站住
        else:
            self.level = 1.0
            self._pause_due = False
            dog.turntable_return(self.w._home_yaw(), instant=native.reduce_motion())
        self.changed.emit()

    def _pause_now(self) -> None:
        """该临时退出灵动交互了：狗在空中、被拎着（灵动交互里）先等它落地（一刀切会把它停在半空，转台这期间只跟着）。"""
        if not self._pause_due:
            return
        pg = self.w.playground
        if pg.active and (pg.roam.lifted or pg.roam.airborne or pg.roam.task == "fall"):
            return
        self._pause_due = False
        self.w.pause_play(True)

    def turn_by(self, degrees: float) -> None:
        """转盘尺转了（TurnRuler.turned）。"""
        if self._open and self._holding:
            self.w.dog.turntable_turn(degrees, instant=native.reduce_motion())

    def set_posture(self, posture: str) -> None:
        """那一排点了站 / 坐 / 趴：狗在转台上换过去（正做的、正换到一半的一刀切）。只是这一页里摆给你看，离开就回到进来前的姿势。页没开着不理。"""
        if self._open and self._holding:
            self.w.dog.set_turntable_pose(posture)
            self.changed.emit()

    def set_level(self, level: float) -> None:
        """滑块、百分比拖到了存下来的大小的 level 倍：夹在 1 和上限之间（超了的弹回去：发 changed，那一块照着对齐）。页没开着不理。"""
        want = max(1.0, float(level)) if self._open else 1.0
        if want > 1.0 + LEVEL_EPS:
            most = self.max_level()
            if most < ZOOM_MIN_GAIN - 1e-9 and self._z is None:
                want = 1.0
            elif want > most:
                want = most
        clamped = abs(want - max(1.0, float(level))) > LEVEL_EPS
        self.level = want
        if clamped:
            self.changed.emit()

    def set_zoom(self, on: bool) -> None:
        """一下放到最大 / 收回（自测、单测用；界面上是滑块和百分比）。"""
        self.set_level(self.max_level() if on else 1.0)
        self.changed.emit()

    # ---- 放大着拖狗（widget/input.py） ----
    def drag_limit(self, x: float, y: float) -> tuple[float, float]:
        """放大着把狗拖到 (x, y) 时它最多到哪：按不放大的狗算（拖到哪就是它真在哪，缩回来就在那）——灵动交互里脚踩的那条线不动、横着不出屏幕、
        站在窗口上的不出那个窗口；关着身子（含脚下的影子）不出屏幕（window.inside_at）。放大的狗出了屏幕的那截照旧看不见（和放大时一样）。"""
        z = self._z
        if z is None:
            return x, y
        w = self.w
        top_m = w.dog.stance_top()
        if w.dynamic:
            lo, hi = self._footing()
            return min(max(w.inside_at(x, z.y, z.base, top_m, shadow=False)[0], lo), hi), z.y
        return w.inside_at(x, y, z.base, top_m)

    def drag_to(self, x: float, y: float) -> None:
        """放大着拖狗（每帧一次，widget/input.py 的 _apply_drag）：放大的狗跟着手，拖到哪就是它真在哪——不放大的根也挪过去
        （window.slide_scaled：dog_rect、记位置、缩回来都按它）。"""
        z = self._z
        if z is None:
            return
        z.x, z.y = x, y
        self.w.slide_scaled(x, y)
        self.w.show_scaled(z.k, x, y)

    # ---- 窗口调的 ----
    def tick(self, dt: float) -> None:
        """每帧（window._tick，狗这一帧的姿势定下来以后）：推放大；离开了、转回来了、缩回来了就放狗下转台。"""
        if ui_frozen():
            return
        if self._pause_due and self._open:
            self._pause_now()
        if self._z is not None or (self.zoom_on and self._open):
            self._step_zoom(dt)
        if self._holding and not self._open and self._z is None and self.w.dog.turntable_back:
            self._release()

    def drop_zoom(self) -> None:
        """临时放大当场收掉（换屏、改存下来的大小、换模式之前；收完窗口就摆回去了），回到 100%。"""
        was_on = self.zoom_on
        self.level = 1.0
        z, self._z = self._z, None
        if z is not None:
            self.w.end_scaled(z.x, z.y)
        if was_on or z is not None:
            self.changed.emit()

    def finish(self) -> None:
        """换同桌（window._enter_pet，狗这时看不见）：临时放大收掉；已经离开那两页、还在转回去的，当场转到该朝的方向、待在该待的姿势里、放下来。"""
        self.drop_zoom()
        if self._holding and not self._open:
            self._holding = False
            self._pause_due = False
            dog = self.w.dog
            self.w.pause_play(False)
            dog.set_turntable(False, instant=True)
            dog.snap_home(self.w._home_yaw())
            self.w.playground.fetch_changed()
            self.changed.emit()

    # ---- 放大 ----
    def _step_zoom(self, dt: float) -> None:
        w = self.w
        want = self.zoom_on and self._open
        z = self._z
        instant = native.reduce_motion()
        if z is None:
            if not self._dog_settled():
                return                                         # 狗在忙：先记着
            k0, gain = w.world_scale, self.max_level()
            if gain < ZOOM_MIN_GAIN - 1e-9:
                self.level = 1.0                               # 停下来一看放不大了（大小改到快到上限、挪到了小屏）：滑块弹回去
                self.changed.emit()
                return
            x, y = w.dog_root()
            z = self._z = _Zoom(k0, x, y, k0 * gain)
            w.hold_scaled(w.scaled_window([(k0, x, y), (z.most, x, y)]), k0, x, y)   # 一开始就按上限摆一次：之后只改画多大、画在哪
            self._follow(z, instant)
            self.changed.emit()                                # 最右照开始时定的上限对齐
        elif not want:
            if not z.out:
                z.out = True
                z.aim(z.base, instant)                         # 回到 100%、离开了、关了：缩回去
        elif z.out or abs(self.level - z.level) > LEVEL_EPS:
            z.out = False
            self._follow(z, instant)                           # 拖滑块（缩回去的路上又拖了也一样）：只换去处，窗口不动
        z.step(dt)
        if z.out and z.settled:
            self._z = None
            w.end_scaled(z.x, z.y)
            return
        w.show_scaled(z.k, z.x, z.y)

    def _follow(self, z: _Zoom, instant: bool) -> None:
        """照着滑块换去处（跟手：ZOOM_FOLLOW_S，保留速度）。"""
        self.level = min(self.level, z.gain)
        z.level = self.level
        z.aim(z.base * self.level, instant, ZOOM_FOLLOW_S, follow=True)

    def _dog_settled(self) -> bool:
        """狗停着：没在被拖、没被 roam 牵着（跑、跳、掉、被拎着）、没在平滑变大小（推荐大小）、主窗口没在换屏。"""
        w = self.w
        if w._drag is not None or w.dog.puppet or w._flip_until is not None or w._scale_anim.state() == QVariantAnimation.Running:
            return False
        pg = w.playground
        return not (pg.active and (pg.roam.busy or pg.roam.lifted))

    def _footing(self) -> tuple[float, float]:
        """灵动交互里站在别的窗口上：根只能在那个窗口的上沿上横着挪（脚不悬空，两头留的边和平时一样）。地面上不管（屏幕边 inside_at 管）。"""
        pg = self.w.playground
        s = pg.roam.support if pg.active else None
        if s is None or s.kind != "window":
            return -math.inf, math.inf
        m = pg.roam.margin(s)
        return s.x0 + m, s.x1 - m

    # ---- 放狗下来 ----
    def _release(self) -> None:
        """离开了、转回来了、缩回来了：放狗下转台——灵动交互临时退出过的先回来（window.pause_play：建空间、球和物件回来；狗还在转台上，
        这一下不动它），再回到进来前该待的姿势（dog.set_turntable），随机动作重新计时、捡球的闸打开，按现在该朝哪再对一次（这期间换了边就转过去）。"""
        self._holding = False
        self._pause_due = False
        dog = self.w.dog
        self.w.pause_play(False)
        dog.set_turntable(False)
        self.w.playground.fetch_changed()
        dog.set_home_yaw(self.w._home_yaw())
        self.changed.emit()


class ZoomSlider(FineSlider):
    """看细节的放大滑块：值是放大到存下来的大小的百分之几（100 = 不放大，最右是上限），每过 ZOOM_TICK 一格 tick 一声（界面音效，sounds.notches，
    和转盘尺一样）；带格的滚轮一格、方向键一下走一格。颜色跟卡片的强调色（画的时候读卡片的 theme，换同桌时跟着变）。"""

    def _apply(self, v: float) -> None:
        old = self.value
        self._value = max(float(self.lo), min(float(self.hi), v))
        self.update()
        if self.value != old:
            sounds.notches(old, self.value, ZOOM_TICK)
            self.valueChanged.emit(self.value)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Right, Qt.Key_Up):
            self._nudge(-ZOOM_TICK if event.key() in (Qt.Key_Left, Qt.Key_Down) else ZOOM_TICK)
            event.accept()
        else:
            QWidget.keyPressEvent(self, event)               # Esc 这些照旧交给卡片（关卡片）

    def wheelEvent(self, event) -> None:
        if not self.isEnabled() or ui_frozen() or event.phase() == Qt.ScrollMomentum:
            event.accept()
            return
        if is_notch(event):
            event.accept()
            self._nudge(-notches(event) * ZOOM_TICK)          # notches：往下 / 往左是正数 → 缩小
            return
        super().wheelEvent(event)                            # 触摸板：按位移走（FineSlider，1 像素四分之一格）

    def paintEvent(self, event) -> None:
        t = getattr(self.window(), "theme", None) or sticker.theme()
        self.accent = QColor(t.accent)
        super().paintEvent(event)


class DetailRow(QWidget):
    """看细节那一块（详情页、自定义毛色页最上面，两页各一个：一个控件不能同时待在两页里，换页时两页还要交叉淡入淡出），两行：
    上面左边转盘刻度尺（widget/turnruler.py），右边放大滑块（ZoomSlider：最左 100%，最右上限）；
    下面左边站 / 坐 / 趴三颗胶囊（和主页面动作行的一样，狗在转台上摆什么姿势），右边放大的百分比和长按回到 100%（和主页面「大小」那一行同一套：
    sizecontrol.SizeScrubber 左右拖精调、单击原位输入，HoldButton 长按重置），百分比在滑块正下方。只转达、只显示，状态都在 window.closeup。"""

    def __init__(self, card, window):
        super().__init__()
        self.closeup = window.closeup
        rows = QVBoxLayout(self)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(ROWS_GAP)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.ruler = TurnRuler()
        self.ruler.setAccessibleName(tr("Turn"))
        top.addWidget(self.ruler, 1)
        self.zoom = ZoomSlider(100, 400)                     # 范围显示出来时照上限对齐（sync）
        self.zoom.setAccessibleName(tr("Zoom"))
        top.addWidget(self.zoom, 1, Qt.AlignVCenter)
        rows.addLayout(top)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(4)                                 # 和动作行一样：每颗胶囊外侧已有 2 像素透明余量
        self._pose_group = QButtonGroup(self)
        self._pose_group.setExclusive(True)
        self.pose_buttons: dict[str, SelectPill] = {}
        for pid, label in TABLE_POSES:
            b = SelectPill(tr(label))                        # 选中换颜色 0.15 秒渐变，和动作行一样
            b.setProperty("horizontalPadding", 6)
            b.setStyleSheet(TIGHT_CSS)
            b.clicked.connect(lambda _=False, p=pid: self.closeup.set_posture(p))
            self._pose_group.addButton(b)
            bottom.addWidget(b)
            self.pose_buttons[pid] = b
        bottom.addStretch(1)
        self.percent = SizeScrubber(None, 100, 400, card.theme.accent)
        self.percent.editor.setAccessibleName(tr("Zoom"))
        bottom.addWidget(self.percent)
        bottom.addSpacing(1)
        self.reset = HoldButton(tr("Reset"), accent=card.theme.accent, symbol="reset")
        self.reset.setAccessibleName(tr("Reset"))
        self.reset.setAccessibleDescription(tr("Hold to go back to 100%"))
        bottom.addWidget(self.reset, 0, Qt.AlignVCenter)
        rows.addLayout(bottom)
        card.tip_for(self.ruler, tr("Drag left or right to turn your deskmate"))
        card.tip_for(self.zoom, tr("Slide to zoom in · back to normal when you leave this page"))
        card.tip_for(self.reset, tr("Hold to go back to 100%"))
        self._range = (100.0, 400.0)
        self.ruler.turned.connect(self.closeup.turn_by)
        for control in (self.zoom, self.percent):
            control.valueChanged.connect(lambda v, c=control: self._set_level(v, c))
            control.adjustmentStarted.connect(self._fresh_range)   # 按下去先按现在的上限定好最右（换了屏、改了大小）
            control.adjustmentFinished.connect(self.sync)         # 松手：超了上限弹回去的，跟着回去
        self.reset.held.connect(self._reset)
        self.closeup.changed.connect(self.sync)

    def _set_level(self, value: float, source) -> None:
        """滑块或百分比动了：放大到 value%，另一个跟着对齐（不出声）。"""
        sc = self.closeup
        sc.set_level(value / 100.0)
        for other in (self.zoom, self.percent):
            if other is not source and not other.adjusting:
                other.set_value(100.0 * sc.level)

    def _reset(self) -> None:
        """长按重置：回到 100%（和主页面「大小」的长按重置一样，这里回的是不放大）。"""
        self.closeup.set_level(1.0)
        self.sync()

    def _fresh_range(self) -> None:
        hi = max(100.0 * ZOOM_MIN_GAIN, 100.0 * self.closeup.max_level())
        if (100.0, hi) != self._range:
            self._range = (100.0, hi)
            self.zoom.set_range(100.0, hi)
            self.percent.set_range(100.0, hi)

    def sync(self) -> None:
        """照着 closeup 对齐：滑块和百分比在哪、最右是多少、能不能拖，转盘尺画在哪（正在拖的不动它），站 / 坐 / 趴亮哪颗。看不见的不对（显示出来时再对）。"""
        if not self.isVisible():
            return
        sc = self.closeup
        if not (self.zoom.adjusting or self.percent.adjusting):
            self._fresh_range()
            self.zoom.set_value(100.0 * sc.level)              # 不出声（只有拖的时候出声）
            self.percent.set_value(100.0 * sc.level)
        on = sc.can_zoom()
        for control in (self.zoom, self.percent, self.reset):
            control.setEnabled(on)
        if not self.ruler.adjusting:
            self.ruler.set_angle(sc.angle)
        b = self.pose_buttons.get(sc.posture)
        if b is not None:
            if not b.isChecked():
                b.setChecked(True)
        elif self._pose_group.checkedButton() is not None:  # 姿势条选了睡：一颗都不亮
            self._pose_group.setExclusive(False)
            self._pose_group.checkedButton().setChecked(False)
            self._pose_group.setExclusive(True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync()
