"""鼠标悬停时狗肩膀上方的「···」菜单按钮，和它旁边滑出的那一条（姿势条：站 / 坐 / 趴 / 睡，睡着只剩「醒来」；灵动交互开着时是道具栏）：
位置、透明度、可点范围、画法。
窗口（widget/window.py）每帧调 tick / track，鼠标事件从 widget/input.py 转过来，画在狗上面（widget/overlay.py 的画法）。

按钮：32×18 的胶囊、可点范围 44×30（扩出来的部分不画；里面的点击只开菜单，不算点狗、不拖）；鼠标移到狗身上就开始淡入
（狗本身，窗口里透明的地方不算，见 widget/input.py 的点击范围）；平时 50% 透明，
靠近 14 像素内、或鼠标在姿势条上时全实；拖动时不出现，离开 0.3 秒淡出；跟缩放 1.0 到 1.6 倍（缩小不跟）。
横向锚在身体中心往头 0.2 米（肩膀上方，不跟着头转），底边在当前姿势 / 状态循环片段的最高点（dogctl.rest_top）上方 6 像素：
跳、随机动作、呼吸都不动它，换姿势 / 换状态、转身 0.25 秒平滑移过去；鼠标冲着它来（在它附近、在姿势条 / 道具栏、关闭键上、按着）时横向、高度都钉住
（鼠标不离开按钮就永远不动），只是在狗身上不钉（扔出去落地以后狗转了身、站起来了，按钮还钉在原来那儿，要移开再移上去才回来）；
看不见的时候（淡没了、拎着飞着）直接到该在的地方，出来就在对的地方。
钉住的是在狗身上的位置（米），画的时候按现在的缩放换成像素：缩放时跟着狗一起缩放（别钉窗口像素：滚轮 / 捏合缩放时
鼠标正好在狗上，按钮钉在旧像素上，放大 4 格漂出去近 100 像素，移开鼠标才滑回来）。
狗太靠上、头顶到屏幕顶上那一条（菜单栏、刘海：_usable）之间放不下按钮时（狗要能放到屏幕最顶上），按钮挪到狗旁边：
狗背那一侧、头顶那么高；狗背贴着屏幕边、那一侧放不下就到脸那一侧（低一点，在胸前，不挡脸）。同样 0.25 秒滑过去，有地方了再回到头顶上
（_choose_place）。按钮和旁边那一条一直画在那一条下面（_top_limit）：刘海那一块没有像素，画进去就看不见、却点得到。
画在哪和点得到哪用的是同一个矩形（_rects）；窗口里的画布铺满整个窗口（native.ignore_safe_area），两边才是同一套坐标。
姿势条：鼠标悬在三个点上时右边 0.15 秒滑出（右边放不下就放有地方的那边，窗口里、屏幕上都算）；可点范围和三个点一样比画出来的大一圈
（上下各 6、两头 6、中间到缝的一半；和三个点重叠处姿势按钮优先）。
道具栏（灵动交互开着时这个位置）：勾了的道具一颗一样（window.tool_entries：「物件」页那一格右上角的圈，默认只有小球），
样子（名字 + 开关），开 = 拿出来、关 = 收起来（window.set_thing，和「物件」页那一格、右键道具是同一个开关）；
最右边一直有一颗「自定义」（只有字，和姿势按钮一样）：点了打开设置卡片的「物件」页（window.open_things_page），在那里勾哪几样放进来；
一行放不下就往下排（_rows），道具最多 TOOLS_MAX 颗（「自定义」不算）。
窗口一直留够它们的位置（悬停时窗口不改大小）：高度留出「···」（min_height），缩小时宽度至少放得下姿势条、最宽的一颗道具（needed_width）。"""
from __future__ import annotations

import math
import time
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter

import config
from widget import native, overlay
from widget.capture_ui import ui_frozen
from widget.i18n import tr
from widget.states import POSTURES, WAKE
from widget.widgets import HoldDriver, Spring

MENU_W, MENU_H, MENU_GAP = 32, 18, 6   # 按钮：宽、高、离姿势最高点多远（随缩放 1.0 到 1.6 倍，缩小不跟）
MENU_HIT_W, MENU_HIT_H = 44, 30        # 可点范围：比画出来的大一圈，扩出来的部分不画
MENU_FORWARD = 0.2                     # 按钮横向锚在身体中心往头的方向这么多米（肩膀上方）：不跟着头转，鼠标过去不会左右晃
MENU_TAU = 0.25                        # 换姿势 / 换状态时按钮移到新高度的时间常数（秒）；跳、随机动作、呼吸不动它
SIDE_OFFSET_M = 0.42                   # 头顶放不下时按钮挪到狗旁边：离身体中心这么远（米，四分之三视角下大约半个身长）再加半个按钮
SIDE_HEIGHT = 0.85                     # …在狗背那一侧时，按钮中心在当前姿势最高点的几成高
FRONT_HEIGHT = 0.5                     # …狗背那一侧放不下、到脸那一侧时低一点：在胸前，不挡脸
PLACE_TOP, PLACE_BACK, PLACE_FRONT = "top", "back", "front"   # 按钮放哪：头顶、狗背那一侧、脸那一侧（_choose_place）
STICKY = 10                            # 放哪要变时多出这么多像素才换（随缩放）：在边上不来回跳
MENU_DELAY = 0.0                       # 鼠标移到狗身上就开始淡入；拖动时不出现
MENU_IDLE_ALPHA, MENU_NEAR = 0.5, 14   # 平时半透明；鼠标离按钮不到这么多像素就全实
MENU_IN, MENU_OUT = 0.25, 0.3          # 淡入、淡出秒数
POST_GAP, POST_SLIDE = 4, 0.15         # 姿势条：按钮间距（像素）、滑出秒数
EDGE = 2                               # 按钮、姿势条离窗口边至少这么多像素
HOVER_SCALE, PRESS_SCALE = 0.975, 0.975
MOTION_S = 0.16
PRESS_TINT_S = 0.12
DIRECTION_SHIFT = 2.0
DOTS = "__menu__"
TOOL = "tool:"                         # 道具栏上一颗的 id：前缀 + 款的钥匙（things.BALL_KEY 是小球）
TOOLS_MAX = 4                          # 道具栏最多几颗
CUSTOM = "__custom__"                  # 道具栏最右边的「自定义」：点了打开「物件」页
CUSTOM_LABEL = "Customize"
POSTURE_IDS = frozenset(pid for pid, _ in POSTURES)
_WIDTHS: dict = {}                     # entry_widths 量过的（字 + 倍数 → 宽）：悬停时每帧要问好几次，量字要 0.1 毫秒级


def tool_id(key: str) -> str:
    return TOOL + key


def tool_key(pid) -> Optional[str]:
    """道具栏那一颗的款钥匙；不是道具栏的（姿势按钮、「自定义」）None。"""
    return pid[len(TOOL):] if isinstance(pid, str) and pid.startswith(TOOL) else None


def on_bar(pid) -> bool:
    """这一颗是道具栏上的（道具或最右边的「自定义」），不是姿势条的。"""
    return pid == CUSTOM or tool_key(pid) is not None


class _TintProgress:
    """按压 / 选中只渐变背景，不把文字和整张按钮交叉淡入。中途松手从当前颜色返回。"""
    def __init__(self, value: float = 0.0):
        self.value = self._from = self.target = value
        self._elapsed = PRESS_TINT_S

    def step(self, target: float, dt: float) -> bool:
        if target != self.target:
            self._from, self.target, self._elapsed = self.value, target, 0.0
        previous = self.value
        self._elapsed = min(PRESS_TINT_S, self._elapsed + dt)
        t = self._elapsed / PRESS_TINT_S
        smooth = t * t * (3.0 - 2.0 * t)
        self.value = self._from + (self.target - self._from) * smooth
        return self.value != previous

    def reset(self, value: float) -> bool:
        changed = self.value != value
        self.value = self._from = self.target = value
        self._elapsed = PRESS_TINT_S
        return changed


def menu_scale(scale: float) -> float:
    """按钮和姿势条随缩放的倍数：1.0 到 1.6。缩小时不再跟着缩（按钮太小点不准）。"""
    return max(1.0, min(1.6, scale))


def strip_widths(labels, k: float) -> list[float]:
    """姿势条每个按钮多宽：字宽 + 两头各 6 像素（乘 k）。字号和画法共用 overlay.strip_font_px，字才不会溢出胶囊。"""
    font = QFont()
    font.setPixelSize(overlay.strip_font_px(MENU_H * k))
    fm = QFontMetricsF(font)
    return [fm.horizontalAdvance(tr(label)) + 12 * k for label in labels]


def entry_widths(entries, k: float) -> list[float]:
    """这一条上每个按钮多宽：道具栏的带开关、字是款的名字（已经是当前语言，不再 tr）；姿势条的按 tr 过的字。量过的记着。"""
    out = []
    for pid, label in entries:
        tool = tool_key(pid) is not None
        key = (tool, label if tool else tr(label), k)
        w = _WIDTHS.get(key)
        if w is None:
            if len(_WIDTHS) > 256:
                _WIDTHS.clear()
            w = _WIDTHS[key] = overlay.switch_pill_width(label, MENU_H * k) if tool else strip_widths([label], k)[0]
        out.append(w)
    return out


def _strip_motion_width(entries, k: float) -> float:
    """控件悬停轻缩，最大尺寸是原尺寸；额外留出向指针侧偏移的空间。"""
    widths = entry_widths(entries, k)
    return (sum(widths) + POST_GAP * k * (len(widths) - 1)
            + DIRECTION_SHIFT * k)


def needed_width(scale: float, tools=()) -> int:
    """窗口至少多宽，姿势条才在窗口里放得下（悬停时窗口临时变宽不行；窗口一直留够，透明的地方点不到，宽一点看不出来）。
    三个点在肩膀上方、往狗头偏 MENU_FORWARD 米，姿势条放在它离窗口边远的那一侧；按当前语言里最长的一组（站 / 坐 / 趴 / 睡，或「醒来」）算。
    道具栏一行放不下就往下排，只要最宽的一颗放得下（tools：能勾进去的款的名字，当前语言；还有最右边的「自定义」）。
    也预留悬停偏移，100% 时英文中文都比狗的宽度窄；缩小时窗口才可能比贴着狗的宽度宽。"""
    k = menu_scale(scale)
    widest_tool = max((_strip_motion_width([(tool_id(""), name)], k) for name in tools), default=0.0)
    strip = max(_strip_motion_width(POSTURES, k), _strip_motion_width((WAKE,), k), widest_tool,
                _strip_motion_width([(CUSTOM, CUSTOM_LABEL)], k))
    offset = MENU_FORWARD * config.PIXELS_PER_METER * scale
    return math.ceil(2 * (MENU_W * k / 2 + POST_GAP * k + strip + EDGE - offset))


class HoverMenu:
    def __init__(self, window):
        self.w = window
        self.active = False                       # 鼠标在小组件上
        self.since = 0.0                          # 进来的时刻：停够 MENU_DELAY 才出按钮
        self.alpha = 0.0                          # 按钮当前透明度
        self.hot = False                          # 鼠标悬在按钮上
        self.near = False                         # 鼠标离按钮很近：全实
        self.press = False                        # 在按钮上按下了左键
        self.post_open = 0.0                      # 姿势条滑出进度 0..1
        self.post_hover = False                   # 鼠标在姿势条那一条上
        self.hot_posture: Optional[str] = None    # 鼠标悬在哪个姿势按钮上
        self.post_press: Optional[str] = None     # 在哪个姿势按钮上按下了左键
        self.top_m: Optional[float] = None        # 按钮钉在狗身上的高度：姿势循环片段的最高点（米，平滑后），窗口长高缩回、缩放都不受影响
        self.room_m: Optional[float] = None       # 窗口给按钮留到多高（米，track 算的）：最高的那个姿势时按钮在哪（min_height），换姿势窗口不用改大小
        self._room_max = 0.0                      # 这次运行里用过的模型里最高的那个姿势（换回矮的那只不缩）
        self.x_m: Optional[float] = None          # 按钮中心离窗口中线多远（米，平滑后）：身体中心往头 MENU_FORWARD
        self.place = PLACE_TOP                    # 按钮放哪：头顶；头顶放不下（狗太靠近屏幕顶）在狗旁边（_choose_place）
        self._pinned_place = PLACE_TOP            # 钉住的时候放在哪
        self._motions: dict[str, Spring] = {}
        self._directions: dict[str, tuple[Spring, Spring]] = {}
        self._tints: dict[str, _TintProgress] = {}
        self._hover_tints: dict[str, _TintProgress] = {}
        self._selected: dict[str, _TintProgress] = {}
        self._selection_context = None
        self._press_direction = QPointF()
        self._target: Optional[str] = None
        self._pivot = DOTS
        self._offset = Spring(0.0, MOTION_S)        # 组内让位的锚点偏移，按 k=1 记；离开时平滑归位
        self._row_of: dict[str, int] = {}         # 道具栏一行放不下往下排：每颗在第几行（_base_rects 记；「···」和姿势条都在第 0 行）
        self._on_right: Optional[bool] = None     # 展开到完全收起期间固定方向，动效不能触发左右翻转
        self._pointer: Optional[QPointF] = None
        self._pressed_inside = True
        self._press_hit: Optional[QRectF] = None
        self._reduced = native.reduce_motion()
        self.close_hover = False                  # 鼠标在「···」下面弹出来的关闭键上
        self.close_press = False                  # 在关闭键上按住了
        self._close_tint = _TintProgress()
        self.close_hold = HoldDriver()            # 关闭键要按住 0.6 秒才退出（防误触）
        self.close_hold.changed.connect(self._close_changed)
        self.close_hold.held.connect(self._close_held)

    def _close_changed(self) -> None:
        self.w._dirty = True

    def _close_held(self) -> None:
        self.close_press = False
        self.w._quit()

    def k(self) -> float:
        return menu_scale(self.w.scale)

    @property
    def side(self) -> bool:
        """按钮在狗旁边（头顶放不下）。"""
        return self.place != PLACE_TOP

    @property
    def lift(self) -> Optional[float]:
        """按钮底边离地面线多少像素：钉住的高度（米）按现在的缩放换算，再隔 MENU_GAP。"""
        return None if self.top_m is None else self.top_m * self.w.ppm + MENU_GAP * self.k()

    @property
    def x(self) -> Optional[float]:
        """按钮中心 x（窗口像素）：钉住的位置（米）按现在的缩放换算。"""
        return None if self.x_m is None else self.w.scene_x + self.x_m * self.w.ppm

    # ---- 悬停状态 ----
    def set_hover(self, on: bool) -> None:
        if ui_frozen():
            return
        if on and not self.active:
            self.since = time.perf_counter()
        self.active = bool(on)
        if not on:
            self.set_hot(False)
            self.near = False
            self.post_hover, self.hot_posture = False, None
            self.close_hover = False
            self._pointer = None
        self.w._dirty = True

    def hide_now(self) -> None:
        """狗被扔出去了：三个点马上收，不留在原地慢慢淡（窗口这时可能还留在旧屏上）。"""
        self.set_hover(False)
        self.alpha = self.post_open = 0.0
        self.w._dirty = True

    def set_hot(self, hot: bool) -> None:
        if ui_frozen():
            return
        if hot != self.hot:
            self.hot = hot
            self.w.setCursor(Qt.PointingHandCursor if hot else Qt.ArrowCursor)
            self.w._dirty = True

    def mouse_move(self, local: QPoint) -> None:
        """只在鼠标真的移动时换目标，按钮让位不会让静止鼠标在两个目标间抖动。按下期间只跟踪原目标。"""
        if ui_frozen():
            return
        point = QPointF(local)
        if point == self._pointer:
            return
        self._pointer = point
        w = self.w
        if self.press or self.post_press is not None:
            target = self.post_press or DOTS
            hit = self._target_hit(target)
            self._pressed_inside = hit.contains(point)
            w._dirty = True
            return
        self.set_hot(self.on_menu(local))
        close = self.close_at(local)
        if close != self.close_hover:
            self.close_hover = close
            w.setCursor(Qt.PointingHandCursor if close or self.hot else Qt.ArrowCursor)
            w._dirty = True
        if self.close_press and not close:
            self.end_close()
        m = MENU_NEAR * self.k()
        near = self.rect().adjusted(-m, -m, m, m).contains(QPointF(local))
        if near != self.near:
            self.near = near
            w._dirty = True
        g = 6 * self.k()                                                 # 从三个点挪到姿势按钮中间有条缝，留点余量别收起来
        rects = self.posture_hit_rects()
        post_hover = any(r.adjusted(-g, -g, g, g).contains(QPointF(local)) for _, r in rects) or self._near_close(local)
        hot_posture = next((pid for pid, r in rects if r.contains(QPointF(local))), None)
        if post_hover != self.post_hover or hot_posture != self.hot_posture:
            self.post_hover, self.hot_posture = post_hover, hot_posture
            w.setCursor(Qt.PointingHandCursor if (hot_posture or self.hot) else Qt.ArrowCursor)
            w._dirty = True

    def begin_press(self, target: str, local: QPoint) -> None:
        """输入层先确定命中的目标；后续移动和松开都只属于这一颗按钮。"""
        if ui_frozen():
            return
        self.post_press, self.press = (None, True) if target == DOTS else (target, False)
        self._press_hit = None
        self._press_hit = self._target_hit(target)
        self._press_direction = self._pointer_direction(target, QPointF(local))
        self._pressed_inside = True
        self._pointer = QPointF(local)
        self.w._dirty = True

    def end_press(self, local: QPoint) -> Optional[str]:
        if ui_frozen():
            return None
        target = self.post_press or (DOTS if self.press else None)
        if target is None:
            return None
        hit = self._target_hit(target)
        accepted = hit.contains(QPointF(local))
        self.post_press, self.press = None, False
        self._press_hit = None
        self._pressed_inside = True
        self._pointer = None
        self.mouse_move(local)
        self.w._dirty = True
        return target if accepted else None

    def _target_hit(self, target: str) -> QRectF:
        hit = self.hit_rect() if target == DOTS else dict(self.posture_hit_rects()).get(target, QRectF())
        if hit.isEmpty():
            return hit                            # 姿势 / 模式改变让按钮消失时，旧的按下不再触发
        # 按下时缩小不能把静止鼠标从命中范围里挤出去。
        return hit.united(self._press_hit) if self._press_hit is not None else hit

    def _pointer_direction(self, target: Optional[str], pointer: Optional[QPointF]) -> QPointF:
        if target is None or pointer is None:
            return QPointF()
        content = self._layout()[1].get(target)
        if content is None:
            return QPointF()
        return QPointF(max(-1.0, min(1.0, (pointer.x() - content.center().x()) / (content.width() / 2))),
                       max(-1.0, min(1.0, (pointer.y() - content.center().y()) / (content.height() / 2))))

    # ---- 每帧 ----
    def tick(self, dt: float, now: float, dragging: bool) -> bool:
        """透明度和姿势条的滑出进度；变了返回 True（窗口要重画）。"""
        if ui_frozen():
            return False
        changed = False
        shown = self.active and not dragging and (now - self.since) >= MENU_DELAY
        want = 0.0 if not (shown or self.press or self.post_press is not None or self.close_press) else (1.0 if (self.hot or self.near or self.post_hover) else MENU_IDLE_ALPHA)   # 鼠标在姿势条上时三个点和四个按钮一起全实
        if self.alpha != want:
            step = dt / (MENU_IN if want > self.alpha else MENU_OUT)
            self.alpha = min(want, self.alpha + step) if want > self.alpha else max(want, self.alpha - step)
            changed = True
        want_open = 1.0 if (self.alpha > 0.0 and (self.hot or self.post_hover or self.post_press is not None or self.close_press)) else 0.0
        if self.post_open != want_open:
            if self.post_open == 0.0 and want_open > 0.0:
                self._on_right = self._choose_direction()
            step = 1.0 if native.reduce_motion() else dt / POST_SLIDE
            self.post_open = min(want_open, self.post_open + step) if want_open > self.post_open else max(want_open, self.post_open - step)
            changed = True
        changed = self._close_tint.step(1.0 if self.close_hover or self.close_press else 0.0, dt) or changed
        changed = self._tick_motion(dt) or changed
        if self.post_open == 0.0:
            self._on_right = None
        return changed

    def _tick_motion(self, dt: float) -> bool:
        if ui_frozen():
            return False
        reduced = native.reduce_motion()
        context = self._selection_key()
        sync_selection = context != self._selection_context or self.alpha <= 0.0
        if self._selection_context is not None and context != self._selection_context and self.post_press is not None:
            self.post_press, self._press_hit, self._pressed_inside = None, None, True
        pressed = self.post_press or (DOTS if self.press else None)
        target = pressed or self.hot_posture or (DOTS if self.hot else None)
        if self.alpha <= 0.0:
            target = None
        base = self._base_rects()
        if target not in base:
            target = None
        if target != self._target:
            current = self._layout()[1]
            pivot = target or DOTS
            # 换目标那一帧保持所有位置，新的目标从当前状态衔接。
            shift = (current[pivot].center().x() - base[pivot].center().x()) / self.k()
            self._pivot = pivot
            self._offset.set_target(shift, instant=True)
            if target is None:
                self._offset.set_target(0.0)
            self._target = target
        changed = reduced != self._reduced
        self._reduced = reduced
        self._selection_context = context
        # 可选项按下就预览最终选中色，松手实际选中后继续同一条进度，不再做第二次反色。
        selection = pressed if pressed in POSTURE_IDS and pressed in base and self._pressed_inside else self.w.rest_posture
        direction = self._press_direction if pressed else self._pointer_direction(target, self._pointer)
        for pid in set(base) | set(self._motions):
            if pid not in self._motions:
                self._motions[pid] = Spring(0.0, MOTION_S)
                self._directions[pid] = (Spring(0.0, MOTION_S), Spring(0.0, MOTION_S))
                self._tints[pid] = _TintProgress()
                self._hover_tints[pid] = _TintProgress()
                self._selected[pid] = _TintProgress(float(self._is_selected(pid)))
            motion = self._motions[pid]
            active = pid == target and (not pressed or self._pressed_inside)
            want = 1.0 if active and not reduced else 0.0
            previous = motion.value
            motion.set_target(want, instant=reduced)
            motion.step(dt)
            changed = changed or motion.value != previous
            for spring, component in zip(self._directions[pid], (direction.x(), direction.y())):
                previous = spring.value
                spring.set_target(component if active and not reduced else 0.0, instant=reduced)
                spring.step(dt)
                changed = changed or spring.value != previous
            tool = tool_key(pid)
            changed = self._tints[pid].step(1.0 if pressed and active and pid not in POSTURE_IDS and tool is None else 0.0, dt) or changed
            changed = self._hover_tints[pid].step(float(active), dt) or changed
            if sync_selection:
                changed = self._selected[pid].reset(float(self._is_selected(pid))) or changed
            if tool is not None:                                     # 道具栏的开关：按下就预览按完的样子
                chosen = self.w.thing_on(tool) != (pressed == pid and self._pressed_inside)
            else:
                chosen = selection == pid
            changed = self._selected[pid].step(float(chosen), dt) or changed
        previous = self._offset.value
        if reduced:
            self._offset.set_target(0.0, instant=True)
        self._offset.step(dt)
        return changed or self._offset.value != previous

    def track(self, dt: float) -> None:
        """按钮的位置（都按米记，缩放时跟着狗）：头顶放得下就横向锚在肩膀上方、底边在当前姿势的最高点上方，放不下在狗旁边（_choose_place）；
        看不见时直接到位，鼠标冲着它来时钉住（_aimed），别的时候按 MENU_TAU 平滑跟过去。"""
        if ui_frozen():
            return
        w = self.w
        rest = w.dog.rest_top()
        forward = 1.0 if math.cos(math.radians(w.dog.yaw)) >= 0 else -1.0          # 朝向约定 forward = (cos yaw, 0, -sin yaw)
        self._room_max = room = max(rest, w.dog.posture_tops()[0], self._room_max)
        self.place = self._choose_place(rest, forward)
        want_x, want_top, self.room_m = self._place_at(self.place, rest, room, forward)
        if self.top_m is None or self.alpha <= 0.0:
            self.top_m, self.x_m = want_top, want_x    # 看不见：直接到该在的地方（落地、转身、换姿势以后一出来就在对的地方）
            self._pinned_place = self.place
            return
        if self._aimed() and self.place == self._pinned_place:
            return                                     # 钉住；放哪变了（狗被拖到屏幕顶、屏幕边）照样挪过去
        self._pinned_place = self.place
        a = 1.0 - math.exp(-dt / MENU_TAU)
        self.top_m += (want_top - self.top_m) * a
        self.x_m += (want_x - self.x_m) * a

    def _place_at(self, place: str, rest: float, room: float, forward: float) -> tuple[float, float, float]:
        """按钮放在 place 时：中心离窗口中线多远、钉住的高度，和窗口要给它留到多高（都按米；rest 是当前姿势的最高点，room 是最高的那个姿势的）。
        头顶：身体中心往头 MENU_FORWARD（肩膀上方，头怎么转都不动），底边在最高点上方。
        旁边：离身体中心 SIDE_OFFSET_M 再加半个按钮；狗背那一侧中心在最高点的 SIDE_HEIGHT 高，脸那一侧低到 FRONT_HEIGHT（在胸前，不挡脸）。"""
        w = self.w
        if place == PLACE_TOP:
            return w.dog.x + forward * MENU_FORWARD, rest, room
        k, ppm = self.k(), w.ppm
        sign, height = (-1.0, SIDE_HEIGHT) if place == PLACE_BACK else (1.0, FRONT_HEIGHT)
        x = w.dog.x + sign * forward * (SIDE_OFFSET_M + (MENU_W / 2 + 6) * k / ppm)
        down = (MENU_H / 2 + MENU_GAP) * k / ppm                 # 钉住的高度 + MENU_GAP 是底边：中心在那个高度，底边低半个按钮
        return x, height * rest - down, height * room - down

    def _choose_place(self, rest: float, forward: float) -> str:
        """「···」放哪：狗头顶（当前姿势最高点）到看得全的地方的上沿（_usable：菜单栏、刘海那一条下面）放得下就在头顶；
        放不下挪到狗背那一侧，那一侧出了看得全的地方（狗背贴着屏幕边）就到脸那一侧，两边都不行还是狗背那一侧（左右会被推回屏幕里）。
        放哪要变时多出 STICKY 才换，在边上不来回跳。单测里的假窗口、还没显示出来（窗口还没摆好）：照旧。"""
        usable = self._usable()
        if usable is None:
            return self.place
        w, k = self.w, self.k()
        sticky = STICKY * k
        head = w.y() + w.scene_ground - rest * w.ppm
        need = (MENU_GAP + MENU_H + 4 + DIRECTION_SHIFT) * k
        if head - usable.top() >= need + (0.0 if self.place == PLACE_TOP else sticky):
            return PLACE_TOP
        for place in (PLACE_BACK, PLACE_FRONT):
            cx = w.x() + w.scene_x + self._place_at(place, rest, rest, forward)[0] * w.ppm     # 按钮中心的全局横坐标
            half = MENU_W * k / 2 + EDGE + (0.0 if self.place == place else sticky)
            if usable.left() + half <= cx <= usable.right() - half:
                return place
        return PLACE_BACK

    def _usable(self) -> Optional[QRectF]:
        """「···」能放在哪（全局坐标）：狗那块屏去掉菜单栏和程序坞（availableGeometry），顶上再去掉被刘海占着的那一条
        （菜单栏自动隐藏时 availableGeometry 不让它，native.screen_safe_top）；底边到屏幕底（按钮总在狗上面、旁边）。
        单测里的假窗口、还没显示出来：None。"""
        w = self.w
        if not hasattr(w, "frameGeometry") or not w.isVisible():
            return None
        screen = QGuiApplication.screenAt(w.frameGeometry().center()) or w.screen()
        if screen is None:
            return None
        g, a = screen.geometry(), screen.availableGeometry()
        top = max(a.top(), g.top() + native.screen_safe_top(screen))
        return QRectF(a.left(), top, a.width(), g.top() + g.height() - top)

    def _top_limit(self) -> float:
        """按钮、旁边那一条最高画到哪（窗口坐标）：窗口上沿和看得全的地方的上沿（_usable）里低的那个，再留 EDGE。"""
        usable = self._usable()
        return max(0.0, 0.0 if usable is None else usable.top() - self.w.y()) + EDGE

    def _aimed(self) -> bool:
        """鼠标冲着按钮来：在「···」附近（MENU_NEAR）、在姿势条 / 道具栏、关闭键上，或者按着——这时按钮钉住不动（鼠标不离开按钮就永远不动）。
        只是在狗身上不算（落地以后狗转了身、站起来了，按钮还钉在落地前那儿）。"""
        return (self.hot or self.near or self.press or self.post_open > 0.0 or self.post_press is not None
                or self.close_hover or self.close_press)

    def min_height(self, ground_px: float) -> int:
        """窗口至少要这么高，按钮才放得下：按钮现在的高度（姿势最高点上方，或钉住的高度：趴下了按钮还在站着的高度）和最高的那个姿势时它在哪
        （room_m）里高的那个 + 按钮 + 4 像素。一直按它留，不管鼠标在不在：悬停时窗口不改大小；换姿势也不改：
        按钮在留够的窗口里滑上滑下。"""
        if self.top_m is None:
            return 0
        top = self.top_m if self.room_m is None else max(self.top_m, self.room_m)
        return math.ceil(ground_px + top * self.w.ppm + MENU_GAP * self.k() + (MENU_H + 4 + DIRECTION_SHIFT) * self.k())

    # ---- 几何 ----
    def _dots_base(self) -> QRectF:
        """按钮画出来的范围：底边离当前姿势最高点 MENU_GAP（平滑后）。顶到窗口上沿、屏幕顶上那一条就停在下面（_top_limit），左右不出窗口。"""
        w, k = self.w, self.k()
        bw, bh = MENU_W * k, MENU_H * k
        lift = self.lift if self.lift is not None else w.dog.rest_top() * w.ppm + MENU_GAP * k
        cx = self.x if self.x is not None else w.scene_x + w.dog.x * w.ppm
        cx = min(max(cx, bw / 2 + 2), w.width() - bw / 2 - 2)
        top = max(self._top_limit() + DIRECTION_SHIFT * k, w.scene_ground - lift - bh)
        return QRectF(cx - bw / 2, top, bw, bh)

    def rect(self) -> QRectF:
        return self._rects()[DOTS]

    def hit_rect(self) -> QRectF:
        """可点范围：比画出来的大一圈（MENU_HIT_W × MENU_HIT_H 乘缩放），扩出来的部分不画。"""
        k = self.k()
        dx, dy = (MENU_HIT_W - MENU_W) / 2 * k, (MENU_HIT_H - MENU_H) / 2 * k
        return self.rect().adjusted(-dx, -dy, dx, dy)

    def postures_available(self) -> bool:
        """站 / 坐 / 趴能不能选：灵动交互关着（灵动交互里狗只站着），和 Settings 的姿势行一致。"""
        return not self.w.dynamic

    def _entries(self) -> list:
        """这一条上有什么：灵动交互开着是道具栏（勾了的道具一颗一样，window.tool_entries，字是款的名字；最右边「自定义」）；否则站 / 坐 / 趴 / 睡，睡着只剩「醒来」。"""
        if not self.postures_available():
            return [(tool_id(key), name) for key, name in self.w.tool_entries()] + [(CUSTOM, CUSTOM_LABEL)]
        return [WAKE] if self.w.dog.sleep_state() != "awake" else list(POSTURES)

    def _is_selected(self, pid: str) -> bool:
        tool = tool_key(pid)
        return self.w.thing_on(tool) if tool is not None else self.w.rest_posture == pid

    def _choose_direction(self) -> bool:
        dots, k = self._dots_base(), self.k()
        total = _strip_motion_width(self._entries(), k)
        lo, hi = self._visible_span()
        room_right, room_left = hi - (dots.right() + POST_GAP * k), dots.left() - POST_GAP * k - lo
        return total <= room_right or room_right >= room_left

    def _rows(self, entries, widths: list[float], on_right: bool) -> list[list[int]]:
        """这一条分几行：姿势条一直一行；道具栏一行放不下（那一侧窗口里、屏幕上看得见的地方）就往下排，每行至少一颗。"""
        if not entries or not on_bar(entries[0][0]):
            return [list(range(len(entries)))]
        dots, gap = self._dots_base(), POST_GAP * self.k()
        lo, hi = self._visible_span()
        room = hi - (dots.right() + gap) if on_right else dots.left() - gap - lo
        rows: list[list[int]] = [[]]
        used = 0.0
        for i, bw in enumerate(widths):
            if rows[-1] and used + gap + bw + DIRECTION_SHIFT * self.k() > room:
                rows.append([])
                used = 0.0
            used += (gap if rows[-1] else 0.0) + bw
            rows[-1].append(i)
        return rows

    def _base_rects(self) -> dict[str, QRectF]:
        """展开动画的静止几何；放大、让位由 _rects 一次算出，画法与命中都用那个结果。
        道具栏往下排的几行：第 r 行在「···」那一行下面 r 个（按钮高 + 缝），每行贴着「···」那一侧排；滑出来时从「···」那里往外、往下展开。"""
        dots = self._dots_base()
        self._row_of = {DOTS: 0}
        if self.post_open <= 0.0:
            return {DOTS: dots}
        k = self.k()
        h, gap = MENU_H * k, POST_GAP * k
        entries = self._entries()
        widths = entry_widths(entries, k)
        if self._on_right is None:
            self._on_right = self._choose_direction()
        on_right = self._on_right
        ease = 1.0 - (1.0 - self.post_open) ** 2
        out = {DOTS: dots} if on_right else {}
        for r, row in enumerate(self._rows(entries, widths, on_right)):
            total = sum(widths[i] for i in row) + gap * (len(row) - 1)
            x = dots.right() + gap if on_right else dots.left() - gap - total
            top = dots.top() + r * (h + gap) * ease
            for i in row:
                pid, bw = entries[i][0], widths[i]
                start = dots.center().x() - bw / 2
                out[pid] = QRectF(start + (x - start) * ease, top, bw, h)
                self._row_of[pid] = r
                x += bw + gap
        if not on_right:
            out[DOTS] = dots
        return out

    def _layout(self) -> tuple[dict[str, QRectF], dict[str, QRectF]]:
        """整颗按钮轻缩、偏向指针，邻居按实际边缘轻靠；另保留未偏移参考框供稳定指针计算。"""
        base = self._base_rects()
        ids = list(base)
        pivot = ids.index(self._pivot if self._pivot in base else DOTS)
        scales = [self.control_scale(pid) for pid in ids]
        extra = [base[pid].width() * (scale - 1.0) for pid, scale in zip(ids, scales)]
        biases = [QPointF() if self._reduced or pid not in self._directions else
                  QPointF(*(max(-1.0, min(1.0, spring.value)) * DIRECTION_SHIFT * self.k()
                            for spring in self._directions[pid])) for pid in ids]
        shifts = [0.0] * len(ids)
        rows: dict[int, list[int]] = {}                     # 每一行各自让位（道具栏往下排的几行互不挤）；行里从左到右
        for i, pid in enumerate(ids):
            rows.setdefault(self._row_of.get(pid, 0), []).append(i)
        for row in rows.values():
            if pivot in row:
                at = row.index(pivot)
            else:                                           # 这一行没有被指着的：贴着「···」那一头不动
                at = 0 if self._on_right is not False else len(row) - 1
            for j in range(at + 1, len(row)):
                a, b = row[j - 1], row[j]
                shifts[b] = shifts[a] + (extra[a] + extra[b]) / 2 + biases[a].x() - biases[b].x()
            for j in range(at - 1, -1, -1):
                a, b = row[j + 1], row[j]
                shifts[b] = shifts[a] - (extra[a] + extra[b]) / 2 + biases[a].x() - biases[b].x()
        offset = 0.0 if self._reduced else self._offset.value * self.k()
        out, content = {}, {}
        for pid, scale, shift, bias in zip(ids, scales, shifts, biases):
            r = base[pid]
            cx, cy = r.center().x() + shift + offset, r.center().y()
            content[pid] = QRectF(cx - r.width() / 2, cy - r.height() / 2, r.width(), r.height())
            out[pid] = QRectF(cx + bias.x() - r.width() * scale / 2, cy + bias.y() - r.height() * scale / 2,
                             r.width() * scale, r.height() * scale)
        # 边缘只退让整组，不改变展开方向；窗口已按最大动效留空间，悬停不 resize。
        lo, hi = self._visible_span()
        left, right = min(r.left() for r in out.values()), max(r.right() for r in out.values())
        dx = lo - left if left < lo else min(0.0, hi - right)
        dy = max(0.0, self._top_limit() - min(r.top() for r in out.values()))
        if dx or dy:
            for r in list(out.values()) + list(content.values()):
                r.translate(dx, dy)
        return out, content

    def _rects(self) -> dict[str, QRectF]:
        return self._layout()[0]

    def control_scale(self, pid: str) -> float:
        motion = self._motions.get(pid)
        return 1.0 if motion is None or self._reduced else 1.0 + (HOVER_SCALE - 1.0) * max(0.0, min(1.0, motion.value))

    def press_tint(self, pid: str) -> float:
        tint = self._tints.get(pid)
        return tint.value if tint is not None else 0.0

    def selected_tint(self, pid: str) -> float:
        if self._selection_context != self._selection_key() or self.alpha <= 0.0:
            return float(self._is_selected(pid))
        tint = self._selected.get(pid)
        return tint.value if tint is not None else float(self._is_selected(pid))

    def _selection_key(self) -> tuple:
        return self.w.dynamic, tuple(pid for pid, _ in self._entries())

    def hover_tint(self, pid: str) -> float:
        tint = self._hover_tints.get(pid)
        return tint.value if tint is not None else 0.0

    def posture_rects(self) -> list:
        return [(pid, r) for pid, r in self._rects().items() if pid != DOTS]

    def _visible_span(self) -> tuple[float, float]:
        """窗口里接鼠标、屏幕上看得见的横向范围（窗口坐标，两头各留 EDGE）：窗口被拖到屏幕边上时，姿势条别放到屏幕外面去；
        窗口铺宽着只在平时贴着狗的那一块里排（window.menu_span：宽着只有那一块接鼠标，道具栏伸到外面那几颗点不到、
        鼠标一过去整条就收）——铺宽着、缩回以后排得一样。"""
        w = self.w
        lo, hi = float(EDGE), float(w.width() - EDGE)
        span = getattr(w, "menu_span", None)                  # 单测里的假窗口没有：整个窗口
        if span is not None:
            left, right = span()
            lo, hi = max(lo, left + EDGE), min(hi, right - EDGE)
        screen = w.screen()
        if screen is not None:
            g = screen.availableGeometry()
            lo, hi = max(lo, g.left() - w.x() + EDGE), min(hi, g.right() + 1 - w.x() - EDGE)
        return lo, hi

    def posture_hit_rects(self) -> list:
        """姿势按钮（道具栏的每一颗）的可点范围：上下各扩 (MENU_HIT_H − MENU_H)/2，左右扩到和邻居的缝中间，两头扩 (MENU_HIT_W − MENU_W)/2。
        道具栏往下排了几行：邻居只算同一行的；行和行之间只扩到缝的一半；下面几行贴着「···」那一头只扩到缝的一半（不抢「···」底下的关闭键）。"""
        rects = self.posture_rects()
        if not rects:
            return []
        k = self.k()
        dx, dy = (MENU_HIT_W - MENU_W) / 2 * k, (MENU_HIT_H - MENU_H) / 2 * k
        half = POST_GAP * k / 2
        last_row = max(self._row_of.get(pid, 0) for pid, _ in rects)
        rows: dict[int, list] = {}
        for pid, r in rects:
            rows.setdefault(self._row_of.get(pid, 0), []).append((pid, r))
        hits = []
        for n, row in rows.items():
            up = dy if n == 0 else half
            down = dy if n == last_row else half
            for i, (pid, r) in enumerate(row):
                inner_left = n > 0 and self._on_right is not False and i == 0            # 往下排的那几行贴着「···」的那一头
                inner_right = n > 0 and self._on_right is False and i == len(row) - 1
                left = (r.left() - (half if inner_left else dx)) if i == 0 else (row[i - 1][1].right() + r.left()) / 2
                right = (r.right() + (half if inner_right else dx)) if i == len(row) - 1 else (r.right() + row[i + 1][1].left()) / 2
                hits.append((pid, QRectF(left, r.top() - up, right - left, r.height() + up + down)))
        return hits

    def posture_at(self, local: QPoint) -> Optional[str]:
        if self.post_open < 0.5:
            return None
        for pid, r in self.posture_hit_rects():
            if r.contains(QPointF(local)):
                return pid
        return None

    def on_menu(self, local: QPoint) -> bool:
        return self.alpha > 0.0 and self.hit_rect().contains(QPointF(local)) and self.posture_at(local) is None \
            and not self.close_at(local)

    def on_controls(self, local: QPoint) -> bool:
        """这一点在「···」或姿势按钮的可点范围里（看得见的时候）：窗口要接鼠标（点击范围 = 狗 + 这些）。"""
        if self.alpha <= 0.0:
            return False
        p = QPointF(local)
        return self.hit_rect().contains(p) or any(r.contains(p) for _, r in self.posture_hit_rects()) or self.close_at(local)

    def keeps(self, local: QPoint) -> bool:
        """「···」出来以后，鼠标在它附近（MENU_NEAR）、它正下方到地面那一条（从狗背上移上来要经过的空白）、姿势条旁边都不算离开。
        这些地方是透明的，点击照样穿到后面：只有 on_controls 的地方和狗本身接鼠标。"""
        if self.alpha <= 0.0:
            return False
        w, k, p = self.w, self.k(), QPointF(local)
        m, g = MENU_NEAR * k, 6 * k
        near = self.rect().adjusted(-m, -m, m, m)
        below = QRectF(near.left(), near.bottom(), near.width(), max(0.0, w.scene_ground - near.bottom()))
        return near.contains(p) or below.contains(p) or any(r.adjusted(-g, -g, g, g).contains(p) for _, r in self.posture_hit_rects()) \
            or self._near_close(local)

    # ---- 关闭键（点「···」直接开设置，悬停在「···」上才往下弹出关闭键） ----
    def close_rect(self) -> Optional[QRectF]:
        """关闭键画在哪：从「···」底下滑出来，和它一样大。没弹出来 None。"""
        if self.post_open <= 0.0:
            return None
        d, gap = self.rect(), POST_GAP * self.k()
        ease = 1.0 - (1.0 - self.post_open) ** 2
        return QRectF(d.left(), d.top() + (d.height() + gap) * ease, d.width(), d.height())

    def close_at(self, local: QPoint) -> bool:
        """这一点在关闭键的可点范围里（上边不扩，不抢「···」）。道具栏往下排了：关闭键旁边就是下一行的道具，往那边只扩到缝的一半。"""
        r = self.close_rect()
        if r is None or self.post_open < 0.5 or self.alpha <= 0.0:
            return False
        k = self.k()
        dx, dy = (MENU_HIT_W - MENU_W) / 2 * k, (MENU_HIT_H - MENU_H) / 2 * k
        left = right = dx
        if any(n > 0 for n in self._row_of.values()):
            if self._on_right is not False:
                right = POST_GAP * k / 2
            else:
                left = POST_GAP * k / 2
        return r.adjusted(-left, -POST_GAP * k / 2, right, dy).contains(QPointF(local))

    def _near_close(self, local: QPoint) -> bool:
        r = self.close_rect()
        g = 6 * self.k()
        return r is not None and r.adjusted(-g, -g, g, g).contains(QPointF(local))

    def begin_close(self) -> None:
        if ui_frozen():
            return
        self.close_press = True
        self.close_hold.press()
        self.w._dirty = True

    def end_close(self) -> None:
        self.close_press = False
        self.close_hold.release()
        self.w._dirty = True

    # ---- 画 ----
    def draw(self, p: QPainter) -> None:
        if self.alpha <= 0.0:
            return
        w = self.w
        labels = dict(POSTURES + (WAKE, (CUSTOM, CUSTOM_LABEL)))
        can_wake = w.dog.sleep_state() == "asleep"
        rects = self._rects()
        items = [(r, tr(labels[pid]), self.selected_tint(pid), self.hover_tint(pid) if pid != "wake" or can_wake else 0.0,
                  self.press_tint(pid) if pid != "wake" or can_wake else 0.0)
                 for pid, r in rects.items() if pid != DOTS and tool_key(pid) is None]
        if items:
            overlay.draw_posture_strip(p, items, self.alpha * self.post_open, MENU_H * self.k())
        accent = QColor(w.accent_color())
        names = dict(self._entries()) if any(tool_key(pid) is not None for pid in rects) else {}
        for pid, r in rects.items():
            if tool_key(pid) is not None:                         # 道具栏：名字 + 开关（开 = 拿出来）
                overlay.draw_switch_pill(p, r, names.get(pid, ""), self.selected_tint(pid), self.hover_tint(pid), 0.0,
                                         self.alpha * self.post_open, MENU_H * self.k(), accent)
        close = self.close_rect()
        if close is not None:
            overlay.draw_close_button(p, close, self.alpha * self.post_open, self._close_tint.value, self.close_hold.progress, MENU_H * self.k(), accent)
        overlay.draw_menu_button(p, rects[DOTS], self.alpha, self.hover_tint(DOTS), self.press_tint(DOTS),
                                 MENU_H * self.k())
