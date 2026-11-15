"""狗窗口的输入（CompanionWindow 的 mixin：class CompanionWindow(InputMixin, QWidget)）：
左键拖动（超过 4 像素才算拖，松手记位置、拖过中线换边）。拖的时候狗头顶不能高出屏幕最上沿（
狗窗口在菜单栏上面一层，系统不再把它往下推，拖出去就拿不回来了；上下摆的两块屏算连通）。拖动走 window.place_scene（别直接挪窗口：
拖到两块屏交界时窗口骑在中间，系统来回换屏、把窗口弹回去）。
灵动交互里：点一下 = 只 duang 一下（按下压扁、松手弹回）；
按下再拖 = 拎起来（松手手还在动就扔出去，不动就掉下去）；点在狗嘴里叼着的球上 = 把球拿走（接着拖、松手扔）。点屏幕别处狗不理——那是你自己在用电脑。
「···」和它旁边那一条（姿势条；灵动交互开着时是道具栏）的点击（走 widget/hovermenu.py，里面的点击不算点狗、不拖）、右键（狗、「···」开设置卡片；道具栏摆着的那一颗弹「我不要……了」）、滚轮 / 触控板捏合缩放。没有键盘快捷键：点狗不把程序切到前台，键盘本来也到不了这里。
看细节放大着（window.showing_scaled，widget/closeup.py）：按下再拖是挪狗，不拎、不扔：拖的是放大的狗，拖到哪就是它真的位置（收回来还在那）；
能拖到哪按不放大的狗算，灵动交互里脚踩的那条线不动、只横着挪（closeup.drag_limit）。窗口不跟着挪（宽着、放大着的窗口里只改狗画在哪）。滚轮、捏合不改大小（window.zoom 自己挡）。
点击范围就是狗（窗口透明的地方太大，点空白也算点到狗）：每帧看鼠标底下是不是狗（_update_hit），不是就让这个窗口不接鼠标，
点击、滚轮、右键直接落到后面的窗口；悬停（「···」出不出来）也按狗本身算。"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

from widget import native, sounds
from widget.capture_ui import ui_frozen
from widget.geometry import column_top
from widget.hand import event_time
from widget.hovermenu import CUSTOM, DOTS, tool_key

HIT_MARGIN = 6                         # 点击范围：狗的边上这么多像素内也算点到狗（腿、尾巴细；点偏了会点到桌面，开着台前调度时窗口就收起来了）
HOVER_GRACE = 0.3                      # 鼠标离开狗和「···」这么久才算离开悬停（斜着从狗身上移到「···」，难免擦过一点空白）


class InputMixin:
    def _init_input(self) -> None:
        self._drag: Optional[QPoint] = None
        self._press_pos: Optional[QPoint] = None
        self._dragged = False
        self._press_event_at = 0.0                    # 这个按下事件发生的时刻（系统打的时间，算手速用）
        self._drag_target: Optional[tuple[float, float]] = None   # 拖到这了，窗口还没挪：每帧挪一次（_apply_drag）
        self._press_global = None
        self._press_root = (0.0, 0.0)                 # 按下时狗的根在哪：拖动时根 = 这里 + 鼠标挪了多少（含亚像素）
        self._ball_drag = False                       # 这一下按在狗嘴里的球上：拖的是球（playground.try_snatch），不是狗
        self._sliding = False                         # 这一下是看细节放大着开始拖的：挪狗，不拎（closeup.drag_to）
        self._shape = False                           # 点击范围就是狗（cocoa、画过第一帧之后）；offscreen 单测里照旧整个窗口都算
        self._accepting: Optional[bool] = None        # 上次告诉系统的：窗口接不接鼠标；None = 还没说过 / Qt 改标志、重新显示后作废
        self._left_at: Optional[float] = None         # 鼠标离开狗和「···」的时刻：HOVER_GRACE 之后才算离开悬停
        self._cursor_at: Optional[QPoint] = None      # 上一帧鼠标在窗口里的位置

    @property
    def dragging(self) -> bool:
        return self._drag is not None and self._dragged

    # ---- 悬停 ----
    def enterEvent(self, event) -> None:
        if not self._shape:                           # 点击范围就是狗时悬停每帧按狗本身定（_update_hit），不靠系统的进出事件
            self.hover.set_hover(True)

    def leaveEvent(self, event) -> None:
        if not self._shape:
            self.hover.set_hover(False)

    # ---- 点击范围就是狗 ----
    def _update_hit(self, now: float) -> None:
        """每帧：鼠标在窗口范围里就读它底下那一小块像素（dogview.probe，上一帧画好的画布；影子不算，边上留 HIT_MARGIN）。
        是狗，或是看得见的「···」/姿势按钮 → 窗口接鼠标；不是 → 告诉系统这个窗口不接鼠标（native.set_ignores_mouse），
        点击、滚轮、右键直接落到后面的窗口。按着鼠标的时候不切：拖到一半狗动了也不会脱手。
        悬停也在这里定（窗口不接鼠标时收不到进出、移动事件）：在狗或「···」上算；「···」出来以后它附近、它正下方到地面那一条、
        姿势条旁边也不算离开（hover.keeps，透明的，点击照样穿过去）；离开这些地方 HOVER_GRACE 才算离开。
        盖在狗前面的物件（窝沿、盆沿，狗趴在窝里时还有盆）看得见的地方不算狗（_covered）：点击落到物件本身的窗口上。
        还没画过第一帧、offscreen 单测里不管（照旧整个窗口都算）。"""
        if ui_frozen():
            self._set_accepting(False)
            for ghost in self._ghosts.values():
                ghost.set_accepting(False)
            return
        if not self._shape:
            self._shape = native.supports_ignores_mouse() and self.view.ready()
            if not self._shape:
                return
        hover = self.hover
        local = self.mapFromGlobal(QCursor.pos())
        held = self._drag is not None or hover.press or hover.post_press is not None or hover.close_press
        on_ghost = self._update_ghost_hit(held)
        if not self.isVisible():
            accept = over = False
        elif held:
            accept, over = True, hover.active
        else:
            inside = self._hit_area().contains(local) and self._flip_until is None and not self._parked   # 主窗口这时是空的（读回来的还是上次画的狗）；宽着只看狗那一块
            on_dog = inside and self.view.probe(local.x(), local.y(), HIT_MARGIN) is not False and not self._covered()
            accept = inside and (hover.on_controls(local) or on_dog)
            if accept or on_ghost or (inside and hover.keeps(local)):
                self._left_at, over = None, True
            else:
                if self._left_at is None:
                    self._left_at = now
                over = hover.active and now - self._left_at < HOVER_GRACE
        self._set_accepting(accept)
        if over != hover.active:
            hover.set_hover(over)
        if over and not held and local != self._cursor_at:
            hover.mouse_move(local)                   # 高亮、靠近全实：窗口不接鼠标时收不到移动事件，这里每帧补上
        self._cursor_at = local

    def _update_ghost_hit(self, held: bool) -> bool:
        """另一块屏上的窗口画的狗也能点（站在两块屏中间只有一边点得到，有时两边都点不到）：鼠标在它画的狗身上它就接鼠标，
        按下去转交给主窗口（ghost.py）。返回鼠标在不在那样的狗身上。"""
        on_ghost = False
        for ghost in self._ghosts.values():
            accept = ghost.pressed
            if not accept and not held and ghost.drawing and self.isVisible():
                local = ghost.mapFromGlobal(QCursor.pos())
                accept = ghost.rect().contains(local) and ghost.view.probe(local.x(), local.y(), HIT_MARGIN) is True and not self._covered()
                on_ghost = on_ghost or accept
            ghost.set_accepting(accept)
        return on_ghost

    def _covered(self) -> bool:
        """鼠标底下的狗被物件盖着（层级比狗高的物件窗口看得见的地方：窝沿、盆沿，狗趴在窝里时还有盆，things.covers_dog）：这里不算狗
        （狗趴在窝里，右键窝弹不出「我不要……了」）。前沿是点得穿的，不扣的话点在窝沿上会落到被它挡住的狗身子上——
        右键开了设置卡片、左键点了狗；扣掉以后落到物件本身的窗口上，点、拖、扔、右键都算物件。灵动交互关着一句话就出去。"""
        return self.playground.active and self.playground.things.covers_dog(QCursor.pos())

    def _set_accepting(self, accept: bool) -> None:
        """告诉系统窗口接不接鼠标，变了才说；没说成（原生窗口还没建）下一帧再说。"""
        if accept != self._accepting and native.set_ignores_mouse(self, not accept):
            self._accepting = accept

    # ---- 鼠标 ----
    def mousePressEvent(self, event) -> None:
        local = event.position().toPoint()
        if event.button() == Qt.LeftButton and self.hover.close_at(local):
            self.hover.begin_close()                          # 关闭键：按住 0.6 秒才退出
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.hover.posture_at(local):
            self.hover.begin_press(self.hover.posture_at(local), local)   # 点姿势按钮：不拖、不算点狗
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.hover.on_menu(local):
            self.hover.begin_press(DOTS, local)       # 点按钮：不拖、不算点狗
            event.accept()
            return
        if event.button() == Qt.LeftButton and self.playground.active and self.playground.try_snatch(event.globalPosition()):
            self._ball_drag = True                            # 点在狗嘴里的球上：狗松口，球到你手里
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            pos = event.globalPosition().toPoint()
            self._drag = pos - self.frameGeometry().topLeft()
            self._press_pos, self._dragged, self._sliding = pos, False, False
            self._press_global = event.globalPosition()
            self._press_event_at = event_time(event)
            self._press_root = self.scene_world()
            if self.playground.active:
                self.playground.dog_press()                   # 压下去（duang 的前半）
            event.accept()

    def _dragged_to(self, wx: float, wy: float) -> tuple[float, float]:
        """拖到这里（狗的根，全局坐标）：狗头顶不高出这一列屏幕的最上沿，再往上拖狗不动；灵动交互里脚也不穿过这一列的地面
        （拖到地面以下松手，下一帧就算落地了，甩不出去）。上下摆的两块屏算连通。
        灵动交互关着：整个身子都不出屏幕（keep_scene_inside）。"""
        if self._sliding and self.showing_scaled:
            return self.closeup.drag_limit(wx, wy)
        if not self.dynamic:
            return self.keep_scene_inside(wx, wy)
        if self.playground.active:
            limit = self.playground.floor_limit(wx, wy)
            if limit is not None:
                wy = min(wy, limit)
        top = column_top([(s.geometry().x(), s.geometry().y(), s.geometry().width(), s.geometry().height()) for s in QApplication.screens()],
                         wx, wy)
        if top is not None:
            over = top - (wy - self.dog.rest_top() * self.ppm)
            if over > 0.0:
                return wx, wy + over
        return wx, wy

    def mouseMoveEvent(self, event) -> None:
        if self._ball_drag:
            self.playground.ball_drag(event.globalPosition(), event_time(event))
            event.accept()
            return
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            pos = event.globalPosition().toPoint()
            if self._dragged or (pos - self._press_pos).manhattanLength() > 4:   # 超过 4 像素才算拖，不然是点击
                if not self._dragged and self.showing_scaled:
                    self._sliding = True                      # 看细节放大着：挪狗，不拎（duang 弹回来）
                    if self.playground.active:
                        self.playground.dog_unpress()
                elif not self._dragged and self.playground.active:
                    self.playground.dog_grabbed(self._press_root, self._press_event_at)   # 拎起来了：正在做的事作废（叼着的球掉下来）
                self._dragged = True
                self._drag_to(event)
            event.accept()
        else:
            local = event.position().toPoint()
            if not self._shape and not self.hover.active and self.rect().contains(local):
                self.hover.set_hover(True)            # 拖动中 Qt 会丢 Enter（拖完要出去再进来三个点才出）：没按键的移动落在窗口里也算悬停
            self.hover.mouse_move(local)

    def _drag_to(self, event) -> None:
        """手拖到这了：记下来，窗口每帧挪一次（_apply_drag）。鼠标事件比帧勤（8 毫秒一个），每挪一次窗口都要等系统回话，一个事件挪一次帧间隔要翻倍（录到的）。"""
        gp, press = event.globalPosition(), self._press_global
        wx, wy = self._dragged_to(self._press_root[0] + gp.x() - press.x(), self._press_root[1] + gp.y() - press.y())
        self._drag_target = (wx, wy)
        if self.playground.active and not self._sliding:
            self.playground.dog_dragged(wx, wy, event_time(event))

    def _apply_drag(self) -> None:
        target, self._drag_target = self._drag_target, None
        if target is None:
            return
        if self._sliding and self.showing_scaled:
            self.closeup.drag_to(*target)                    # 看细节放大着：拖的是放大的狗（closeup 画在哪），窗口不跟着挪
        else:
            self.place_scene(*target)

    def mouseReleaseEvent(self, event) -> None:
        local = event.position().toPoint()
        hover = self.hover
        if self._ball_drag:
            if event.button() == Qt.LeftButton:
                self._ball_drag = False
                self.playground.ball_release(event.globalPosition(), event_time(event))
            event.accept()
            return
        if hover.close_press:
            hover.end_close()
            event.accept()
            return
        if hover.post_press or hover.press:
            target = hover.end_press(local)
            if event.button() == Qt.LeftButton and target is not None:
                if target == DOTS:
                    sounds.play("tap")
                    self.open_settings()                      # 点「···」直接开设置，再点收起
                elif target == CUSTOM:                      # 道具栏最右边的「自定义」：开设置卡片的「物件」页，在那里勾放进道具栏的
                    sounds.play("tap")
                    self.open_things_page()
                elif tool_key(target) is not None:          # 道具栏的一颗：开 = 拿出来、关 = 收起来（和「物件」页那一格同一个开关）
                    key = tool_key(target)
                    on = not self.thing_on(key)
                    sounds.play("switch-on" if on else "switch-off")
                    self.set_thing(key, on)
                else:
                    if target != self.rest_posture:
                        sounds.play("tap")
                    self.set_rest_posture(target)
            return
        if self._drag is not None:
            playground = self.playground
            if self._dragged and self._sliding:
                self._drag_to(event)
                self._apply_drag()
                if playground.active:
                    playground.dog_slid(*self.dog_root())
                self._save_pos()
                if not self._shape and self.rect().contains(local):
                    hover.set_hover(True)
            elif self._dragged:
                self._drag_to(event)
                self._apply_drag()
                self.dog.set_home_yaw(self._home_yaw())       # 拖过中线就换边（没换边什么都不做）
                if playground.active:
                    playground.dog_dropped(event_time(event)) # 灵动交互：手还在动就扔出去；不动就掉下去，落在下面的窗口上沿或地面
                if not (playground.active and playground.roam.busy):
                    self._save_pos()                          # 还在飞的等停稳了再记（_after_move）：这时窗口还在旧地方
                if playground.active and playground.roam.task == "fall":
                    hover.hide_now()                          # 扔到另一块屏，「···」还留在旧屏上
                elif not self._shape and self.rect().contains(local):
                    hover.set_hover(True)                     # 松手时鼠标还在狗上：算悬停，三个点照常出来（拖动中 Qt 可能丢了 Enter；点击范围就是狗时下一帧自己看）
            elif playground.active:
                playground.dog_unpress()                      # 点一下：弹回来（duang 的后半），没有别的反应
        self._drag, self._sliding = None, False

    def mouseDoubleClickEvent(self, event) -> None:
        """连点时第二下 Qt 报成双击、不报按下：「···」、姿势条、狗身上一律当成一次按下，不然这一下点了没反应、按住也拖不动
        （狂点三个点有几率没反应，菜单开着时那一下被 macOS 吞了只关菜单，前后两下就凑成双击；
        刚打开时点一下狗、紧接着按住拖，怎么都拖不动）。"""
        if event.button() != Qt.LeftButton:
            return
        self.mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        key = tool_key(self.hover.posture_at(event.pos()))
        if key is None:
            self.open_settings()                          # 右键狗和点「···」一样
        elif self.thing_on(key):
            self.show_thing_menu(key, event.globalPos())  # 右键道具栏的一颗：和右键摆着的那一件一样「我不要……了」（右键道具通通是它）
        event.accept()                                    # 没摆出来的那一颗：没有可收的，什么都不弹

    # ---- 缩放 ----
    def wheelEvent(self, event) -> None:
        dy = event.angleDelta().y()
        if dy:
            self.zoom(math.exp(dy / 600.0))
            event.accept()

    def event(self, ev) -> bool:
        if ev.type() == QEvent.NativeGesture and ev.gestureType() == Qt.ZoomNativeGesture:
            self.zoom(1.0 + ev.value())
            return True
        return super().event(ev)
