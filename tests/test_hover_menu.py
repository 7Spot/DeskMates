"""狗窗口上的交互：「···」按钮和姿势条、点击范围就是狗、拖动和点击、全局点击、窗口长高缩回、右键菜单、淡入。offscreen 平台，不碰真 QSettings。
offscreen 没有 GL 也不能让窗口不接鼠标：点击范围的测试用假的"鼠标底下是不是狗"（view.probe）和假的鼠标位置，记下告诉系统的每一次。"""
import math
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import config
from tests.panel_base import QUIET, FakeSettings, PanelCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class HoverMenuTests(PanelCase):
    def _on_floor(self, w, x: float = 400.0) -> None:
        """把狗放在主屏的地面上（灵动交互里放在半空的会掉下去）。"""
        from PySide6.QtWidgets import QApplication
        from widget.playground import FLOOR_MARGIN_PX
        ag = QApplication.primaryScreen().availableGeometry()
        w.place_scene(x, ag.y() + ag.height() - FLOOR_MARGIN_PX * w.scale)

    def test_window_grows_for_a_jump_and_shrinks_back_keeping_the_ground(self):
        from widget.clips import JUMPS
        self.win.show()
        self._on_floor(self.win)
        self.win.set_dynamic(True)
        self.assertFalse(self.win.playground.roam.busy, "放在地面上：不掉")
        dog = self.win.dog
        dog.action_at = float("inf")                       # 别让随机动作（仰头叫这类更高的）插进来
        for _ in range(8 * 60):
            dog.update(1 / 60)
            dog.frame()
        dog._start_jump()
        for _ in range(3 * 60):
            dog.update(1 / 60)
            dog.frame()
        self.win._fit_height(now=0.0)
        h0, bottom = self.win.height(), self.win.y() + self.win.height()
        self.assertEqual(h0, self.win._height_needed(), "站着时窗口就是站着要的高度（狗 + 头顶给「···」留的）")
        self.assertLessEqual(h0, round(config.WINDOW_HEIGHT * self.win.scale) + 10)
        j = next(j for j in JUMPS if j.name == "up")
        dog._start_jump(jump=j)
        dog.update(1 / 60)
        self.win._fit_height(now=0.1, dt=1 / 60)
        self.assertGreater(self.win.height(), h0, "起跳时窗口长高")
        self.assertLessEqual(self.win.height() - h0, 25 * self.win.scale + 1, "一帧最多长 25 像素：旧画面拉伸那一帧才不明显（切捡回时狗纵向拉长）")
        self.assertEqual(self.win.y() + self.win.height(), bottom, "底边不动")
        for _ in range(30):
            self.win._fit_height(now=0.1, dt=1 / 60)
        self.assertEqual(self.win.y() + self.win.height(), bottom, "分几帧长完，底边还是不动")
        self.assertGreater(self.win.height(), h0 + 60, "几帧之后长到位")
        while dog.jump is not None:
            dog.update(1 / 60)
            dog.frame()
        self.win._fit_height(now=10.0)
        self.assertGreater(self.win.height(), h0, "落地后先不缩，等防抖时间")
        self.win._fit_height(now=12.0)
        self.assertEqual(self.win.height(), h0, "1.5 秒后缩回")
        self.assertEqual(self.win.y() + self.win.height(), bottom)

    def _fresh_window(self, values=None):
        import widget.window as window

        def settings(*args):
            fake = FakeSettings()
            fake.values["dynamic"] = False                    # 按"狗自己待着"写的用例（灵动交互新装默认开）
            return fake
        with mock.patch.object(window, "QSettings", settings):
            w = window.CompanionWindow(self.model)
        w._anim_timer.stop()
        w.settings.values.update(values or {})
        return w

    def test_position_is_saved_per_screen_as_proportions(self):
        """位置记在哪块屏 + 屏上的比例（中心 x、底边），换到大小不同的屏上按比例放回去；那块屏不在了按比例放到主屏；
        旧版本只记了绝对坐标的照旧放、顺手存成比例。"""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        g = screen.availableGeometry()
        self.win.show()
        self.win.move(g.x() + 400, g.y() + 300)
        self.win._save_pos()
        saved = dict(self.win.settings.values)
        h = self.win.height()
        self.assertEqual(saved["pos_screen"], screen.name())
        self.assertAlmostEqual(saved["pos_fx"], (400 + self.win.width() / 2) / g.width())
        self.assertAlmostEqual(saved["pos_fb"], (300 + h) / g.height())
        again = self._fresh_window(saved)
        again.place_initially()
        self.assertEqual((again.x(), again.y() + again.height()), (g.x() + 400, g.y() + 300 + h), "重启后底边（狗脚）在原地")
        gone = self._fresh_window({"pos_screen": "拔掉的外接屏", "pos_fx": 0.25, "pos_fb": 0.9})
        gone.place_initially()
        self.assertAlmostEqual(gone.x() + gone.width() / 2, g.x() + 0.25 * g.width(), delta=1, msg="那块屏不在了：按比例放到主屏")
        self.assertAlmostEqual(gone.y() + gone.height(), g.y() + 0.9 * g.height(), delta=1)
        first = self._fresh_window({})                                 # 新装、没记过位置（默认主屏右下）
        first.place_initially()
        self.assertGreater(first.x() + first.width() / 2, g.center().x(), "在右半边")
        self.assertGreater(first.y() + first.height(), g.y() + 0.8 * g.height(), "靠下")
        old = self._fresh_window({"pos_x": g.x() + 100, "pos_bottom": g.y() + 500})
        old.place_initially()
        self.assertEqual((old.x(), old.y() + old.height()), (g.x() + 100, g.y() + 500), "旧版本的绝对坐标照旧放")
        self.assertGreaterEqual(old.settings.values.get("pos_fx", -1.0), 0.0, "顺手存成比例")

    def test_dog_faces_the_screen_centre_at_launch_and_turns_after_a_system_move(self):
        """启动：窗口放好就直接朝 home，不播转身。
        程序开着时窗口被系统挪到另一半（拔掉外接屏）：停稳后重新看左右，狗转过去。"""
        from PySide6.QtWidgets import QApplication
        g = QApplication.primaryScreen().availableGeometry()
        for fx, home in ((0.2, 330.0), (0.8, 210.0)):               # 左半边朝右，右半边朝左
            w = self._fresh_window({"pos_fx": fx, "pos_fb": 0.8})
            w.set_follow_cursor(True)                               # 互动模式（趴着）
            w.place_initially()
            self.assertEqual((w.dog.home_yaw, w.dog.yaw), (home, home), "放好就直接朝 home")
            names = set()
            for _ in range(4 * 60):
                w.dog.update(1 / 60)
                w.dog.frame()
                names.add(w.dog.player.name)
            self.assertFalse(any(n.startswith("Turn_") for n in names), f"启动不播转身：{names}")
        w.show()
        w.dog.action_at = float("inf")
        w.move(g.x() + round(0.2 * g.width()) - w.width() // 2, w.y())   # 被系统挪到左半边：没有拖动、没有松手
        w._after_move()                                             # 停稳 0.5 秒（MOVE_SETTLE_MS）到了
        self.assertEqual(w.dog.home_yaw, 330.0)
        for _ in range(8 * 60):
            w.dog.update(1 / 60)
            w.dog.frame()
        self.assertLess(abs((w.dog.yaw - 330.0 + 180) % 360 - 180), 6.0, "趴着的也起来转过去")
        self.assertEqual(w.dog.posture, "lying")
        self.assertAlmostEqual(w.settings.values["pos_fx"], 0.2, delta=0.01, msg="系统挪过去的位置也记下")

    def test_hover_menu_button_fades_immediately_tracks_and_opens_the_menu(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        self.win.show()
        self.win.move(100, 400)                              # 离屏幕顶远一点，窗口才有地方往上长
        self.assertEqual(self.win.hover.alpha, 0.0)
        self.win.enterEvent(None)
        self.win._last_tick = time.perf_counter() - 0.2
        self.win._tick()
        self.assertGreater(self.win.hover.alpha, 0.0, "鼠标移入后第一帧就开始显示，不等待")
        self.assertLess(self.win.hover.alpha, 0.5, "保留淡入动画，不直接跳到目标透明度")
        for _ in range(4):
            self.win._last_tick = time.perf_counter() - 0.2      # 每次 tick 算 0.1 秒
            self.win._tick()
        self.assertAlmostEqual(self.win.hover.alpha, 0.5, places=3, msg="平时半透明")
        self.win.hover.near = True
        for _ in range(4):
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        self.assertEqual(self.win.hover.alpha, 1.0, "鼠标靠近才全实")
        r = self.win.hover.rect()
        self.assertTrue(self.win.rect().contains(r.toRect()), "按钮在窗口里")
        self.assertEqual((r.width(), r.height()), (32, 18), "1 倍时 32×18")
        top_px = self.win.height() - self.win.ground_px - self.win.dog.rest_top() * self.win.ppm
        self.assertLessEqual(r.bottom(), top_px + 0.5, "在这个姿势循环片段的最高点之上，不重叠")
        self.assertGreaterEqual(self.win.height(), math.ceil(self.win.ground_px + self.win.dog.required * self.win.ppm) + 24, "悬停时窗口给按钮留位置")
        opened = []
        self.win.open_settings = lambda: opened.append(True)
        center = r.center()
        gp = QPointF(self.win.mapToGlobal(center.toPoint()))
        press = QMouseEvent(QEvent.MouseButtonPress, center, gp, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        release = QMouseEvent(QEvent.MouseButtonRelease, center, gp, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        self.win.mousePressEvent(press)
        self.assertIsNone(self.win._drag, "点按钮不是拖狗")
        self.win.mouseReleaseEvent(release)
        self.assertEqual(len(opened), 1, "点按钮弹菜单")
        self.win._drag, self.win._dragged = QPoint(0, 0), True   # 拖动中：藏起来
        for _ in range(6):
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        self.assertEqual(self.win.hover.alpha, 0.0, "拖动时不出现")
        self.win._drag, self.win._dragged = None, False
        self.win.leaveEvent(None)
        for _ in range(4):
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        self.assertEqual(self.win.hover.alpha, 0.0, "离开后淡出")
        self.win.mousePressEvent(press)
        self.assertIsNotNone(self.win._drag, "按钮没显示时同一位置是普通点击")
        self.win.mouseReleaseEvent(release)
        self.assertEqual(len(opened), 1)

    def settle_hover_on_dots(self):
        h = self.win.hover
        self.win.show()
        self.win.move(100, 400)
        self.win.enterEvent(None)
        h.since = time.perf_counter() - 1.0

        def tick(n=6):
            for _ in range(n):
                self.win._last_tick = time.perf_counter() - 0.2
                self.win._tick()
        tick()
        h.mouse_move(h.rect().center().toPoint())
        tick()
        return h, tick

    def test_right_click_on_the_dog_opens_settings_like_the_dots(self):
        from unittest import mock as m
        with m.patch.object(self.win, "open_settings") as opened:
            self.win.contextMenuEvent(m.Mock())
        opened.assert_called_once()

    def test_right_clicking_a_tool_on_the_bar_offers_to_put_it_away(self):
        """右键道具栏里的那一颗，右键道具通通是「我不要……了」，
        道具栏里的也是：摆着的那一颗弹它那颗胶囊（摆在点的地方旁边）；没摆出来的没有可收的，什么都不弹；右键「···」、狗照旧开设置卡片。"""
        from unittest import mock as m
        from PySide6.QtGui import QContextMenuEvent
        from widget import hovermenu
        from widget.things import BALL_KEY
        win = self.win
        win.set_dynamic(True)
        h, tick = self.settle_hover_on_dots()
        center = dict(h.posture_rects())[hovermenu.tool_id(BALL_KEY)].center().toPoint()

        def right_click(local):
            win.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, local, win.mapToGlobal(local)))
        with m.patch.object(win, "show_thing_menu") as menu, m.patch.object(win, "open_settings") as settings:
            right_click(center)
            menu.assert_called_once_with(BALL_KEY, win.mapToGlobal(center))
            settings.assert_not_called()
            win.set_ball_out(False)
            right_click(center)
            self.assertEqual((menu.call_count, settings.call_count), (1, 0), "没摆出来的：什么都不弹")
            right_click(h.rect().center().toPoint())
            self.assertEqual(settings.call_count, 1, "右键「···」照旧开设置卡片")
        win.set_ball_out(True)

    def test_hovering_the_dots_slides_out_a_close_button_and_only_holding_it_quits(self):
        """点「···」直接开设置；悬停在「···」上往下弹出关闭键（按住 0.6 秒才退出，防误触）。"""
        from unittest import mock as m
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        self.assertIsNone(self.win.hover.close_rect(), "没悬停在「···」上没有关闭键")
        h, tick = self.settle_hover_on_dots()
        r = h.close_rect()
        self.assertIsNotNone(r, "弹出来了")
        dots = h.rect()
        self.assertGreater(r.top(), dots.bottom(), "在「···」下面")
        self.assertEqual((r.left(), r.width(), r.height()), (dots.left(), dots.width(), dots.height()), "和「···」一样的胶囊")
        center = r.center().toPoint()
        self.assertTrue(h.close_at(center))
        self.assertTrue(h.on_controls(center), "窗口要接这里的鼠标")
        self.assertFalse(h.on_menu(center), "不算点「···」")
        gp = QPointF(self.win.mapToGlobal(center))

        def event(kind, buttons=Qt.LeftButton):
            return QMouseEvent(kind, r.center(), gp, Qt.LeftButton, buttons, Qt.NoModifier)
        h.mouse_move(center)
        tick()
        self.assertTrue(h.close_hover)
        self.assertIsNotNone(h.close_rect(), "鼠标挪到关闭键上它不收")
        with m.patch.object(self.win, "_quit") as quit_app, m.patch.object(self.win, "open_settings") as settings:
            self.win.mousePressEvent(event(QEvent.MouseButtonPress))
            self.assertTrue(h.close_press)
            self.assertIsNone(self.win._drag, "不算按狗")
            self.win.mouseReleaseEvent(event(QEvent.MouseButtonRelease, Qt.NoButton))
            quit_app.assert_not_called()
            settings.assert_not_called()
            self.win.mousePressEvent(event(QEvent.MouseButtonPress))
            h.close_hold._t0 -= 1.0
            h.close_hold._tick()
            quit_app.assert_called_once()
        h.end_close()

    def test_moving_off_the_close_button_cancels_the_hold(self):
        from unittest import mock as m
        h, tick = self.settle_hover_on_dots()
        center = h.close_rect().center().toPoint()
        h.mouse_move(center)
        h.begin_close()
        h.mouse_move(h.rect().center().toPoint())
        self.assertFalse(h.close_press, "挪开就取消")
        with m.patch.object(self.win, "_quit") as quit_app:
            h.close_hold._t0 -= 1.0
            h.close_hold._tick()
            quit_app.assert_not_called()

    def test_the_toolbar_has_one_switch_pill_per_pinned_thing_and_the_ball_by_default(self):
        """「···」右边换成道具栏——一颗胶囊一样道具，样子照原来那颗「捡球」（名字 + 开关），开 = 拿出来、关 = 收起来；默认只放小球。"""
        from unittest import mock as m
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import hovermenu, overlay
        from widget.things import BALL_KEY
        win = self.win
        win.set_dynamic(True)
        h, tick = self.settle_hover_on_dots()
        rects = dict(h.posture_rects())
        ball = hovermenu.tool_id(BALL_KEY)
        self.assertEqual(list(rects), [ball, hovermenu.CUSTOM], "默认只放了小球，最右边是「自定义」")
        self.assertGreater(rects[ball].width(), hovermenu.strip_widths(["Ball"], h.k())[0] + 10.0, "放得下开关")
        with m.patch.object(overlay, "draw_switch_pill") as pill, m.patch.object(overlay, "draw_posture_strip") as strip, \
             m.patch.object(overlay, "draw_menu_button"), m.patch.object(overlay, "draw_close_button"):
            h.draw(None)
        self.assertEqual([item[1] for item in strip.call_args[0][1]], ["Customize"], "「自定义」只有字，和姿势按钮一样画")
        self.assertEqual(pill.call_count, 1, "开关胶囊只有道具那一颗")
        self.assertEqual(pill.call_args[0][2], "Ball", "字是这一样的名字")
        self.assertAlmostEqual(pill.call_args[0][3], 1.0, msg="拿出来着：圆钮在右边")
        center = h.posture_rects()[0][1].center()
        gp = QPointF(win.mapToGlobal(center.toPoint()))
        h.mouse_move(center.toPoint())
        tick()
        win.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, center, gp, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        win.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, center, gp, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        self.assertFalse(win.ball_out, "点一下收起来")
        self.assertFalse(win.thing_on(BALL_KEY), "和「物件」页那一格同一个开关")
        tick()
        with m.patch.object(overlay, "draw_switch_pill") as pill, m.patch.object(overlay, "draw_posture_strip"), \
             m.patch.object(overlay, "draw_menu_button"), m.patch.object(overlay, "draw_close_button"):
            h.draw(None)
        self.assertAlmostEqual(pill.call_args[0][3], 0.0, msg="收起来：圆钮滑回左边")
        win.set_ball_out(True)

    def test_customize_at_the_right_end_opens_the_things_page_without_closing_an_open_card(self):
        """道具栏最右边一颗「自定义」，点了打开设置卡片的「物件」页，在那里勾哪几样放进来。
        卡片没开着：直接在「物件」页弹出来；开着在别的页：换过去，卡片不关（「···」点一下是开关卡片，这颗不是）。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import hovermenu
        win = self.win
        win.set_dynamic(True)
        h, tick = self.settle_hover_on_dots()
        rects = h.posture_rects()
        self.assertEqual(rects[-1][0], hovermenu.CUSTOM)
        self.assertGreater(rects[-1][1].left(), rects[0][1].right(), "在最右边")

        def click():
            center = dict(h.posture_rects())[hovermenu.CUSTOM].center()
            gp = QPointF(win.mapToGlobal(center.toPoint()))
            h.mouse_move(center.toPoint())
            tick()
            win.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, center, gp, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
            win.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, center, gp, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

        s = win.settings_panel
        self.assertFalse(s.isVisible())
        click()
        self.assertTrue(s.isVisible(), "卡片弹出来")
        self.assertEqual(s.page, "things", "直接是「物件」页")
        self.assertTrue(win.ball_out, "点「自定义」不动小球")
        s.show_page("main", animated=False)
        click()
        s.finish_page_anim()
        self.assertTrue(s.isVisible() and not s.closing, "开着再点：卡片不关")
        self.assertEqual(s.page, "things")

    def test_the_toolbar_stays_where_the_wide_window_takes_the_mouse_and_lays_out_the_same_after_it_shrinks(self):
        """挪过狗以后道具栏排成一长行伸到狗旁边很远，鼠标移到「饭盆」上整条就收了，过一会儿再出来变成两行。
        狗动过窗口铺宽，宽着时只有平时贴着狗的那一块接鼠标（window._hit_area）：道具栏只在那一块里排，每一颗都点得到，缩回以后排得一样。"""
        import time
        win = self.win
        win.set_dynamic(True)
        win.playground.roam.cancel(drop_ball=False)
        for t in win.things_available():
            win.set_tool_pinned(t.key, True)                        # 放满 4 颗，再加「自定义」
        win.show()
        win.move(100, 400)
        win._enter_wide()
        win._step_reshape(time.perf_counter() + 10.0)
        self.assertTrue(win._wide)
        area = win._hit_area()
        self.assertGreater(win.width(), area.width() + 150, "铺宽了：窗口比接鼠标的那一块宽得多")
        h, tick = self.settle_hover_on_dots()
        wide = h.posture_hit_rects()
        self.assertGreaterEqual(len(wide), 2)

        def rows(rects):
            dots = h.rect()
            return sorted((round(r.top() - dots.top()), round(r.left() - dots.left())) for _, r in rects)

        for pid, r in wide:
            self.assertGreaterEqual(r.left(), area.left(), f"{pid} 在接鼠标的那一块里")
            self.assertLessEqual(r.right(), area.right() + 1.0, f"{pid} 在接鼠标的那一块里")
            self.assertEqual(h.posture_at(r.center().toPoint()), pid, "点得到")
        laid = rows(wide)
        h.set_hover(False)
        tick(20)
        win._leave_wide()
        win._step_reshape(time.perf_counter() + 10.0)
        self.assertFalse(win._wide)
        win.enterEvent(None)
        h.since = time.perf_counter() - 1.0
        tick()
        h.mouse_move(h.rect().center().toPoint())
        tick()
        self.assertEqual(rows(h.posture_hit_rects()), laid, "缩回以后排得一样（一行两行都一样）")

    def test_pins_choose_what_is_on_the_toolbar_in_page_order_four_at_most_and_are_remembered(self):
        """栏里放哪几样用户能设（「物件」页每一格右上角的勾选圈），默认只放球；最多 4 颗；存在设置里。"""
        from widget import hovermenu
        from widget.things import BALL_KEY
        win = self.win
        keys = [t.key for t in win.things_available()]
        self.assertIn(BALL_KEY, keys)
        self.assertEqual([k for k, _ in win.tool_entries()], [BALL_KEY])
        others = [k for k in keys if k != BALL_KEY]
        if len(others) < hovermenu.TOOLS_MAX:
            self.skipTest("买来的物件模型不在：只有小球")
        for k in others[:hovermenu.TOOLS_MAX - 1]:
            self.assertTrue(win.set_tool_pinned(k, True))
        self.assertTrue(win.tools_full())
        self.assertFalse(win.set_tool_pinned(others[hovermenu.TOOLS_MAX - 1], True), "满了钉不进去")
        shown = [k for k, _ in win.tool_entries()]
        self.assertEqual(len(shown), hovermenu.TOOLS_MAX)
        self.assertEqual(shown, [k for k in keys if k in shown], "按「物件」页的先后")
        import json
        self.assertEqual(sorted(json.loads(win.settings.values["tools"])), sorted(shown), "存在设置里")
        self.assertEqual(win._read_tools(), win.tools, "重开读回来一样")
        self.assertTrue(win.set_tool_pinned(BALL_KEY, False))
        self.assertNotIn(BALL_KEY, [k for k, _ in win.tool_entries()], "小球也能取下来")

    def test_rapid_clicks_on_the_dots_never_get_lost_as_double_clicks(self):
        """狂点三个点，有几率点了没反应。连点时第二下 Qt 报成双击、不报按下（菜单开着时点三个点那一下被 macOS 吞了只用来关菜单，
        Qt 就把前后两下凑成双击）；双击不理的话，后面的松开没有对应的按下，菜单不开，所以双击也要当成一次按下。姿势条同理。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        self.win.show()
        self.win.move(100, 400)
        self.win.enterEvent(None)
        self.win.hover.since = time.perf_counter() - 1.0
        for _ in range(6):
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        opened = []
        self.win.open_settings = lambda: opened.append(True)
        center = self.win.hover.rect().center()
        gp = QPointF(self.win.mapToGlobal(center.toPoint()))

        def event(kind, buttons=Qt.LeftButton):
            return QMouseEvent(kind, center, gp, Qt.LeftButton, buttons, Qt.NoModifier)

        self.win.mousePressEvent(event(QEvent.MouseButtonPress))
        self.win.mouseReleaseEvent(event(QEvent.MouseButtonRelease, Qt.NoButton))
        self.win.mouseDoubleClickEvent(event(QEvent.MouseButtonDblClick))   # 下一下被报成双击
        self.win.mouseReleaseEvent(event(QEvent.MouseButtonRelease, Qt.NoButton))
        self.assertEqual(len(opened), 2, "双击那一下也开菜单")
        self.assertIsNone(self.win._drag, "也不算拖狗")

    def test_a_quick_second_press_on_the_dog_still_drags(self):
        """刚打开时点一下狗、紧接着按住拖，怎么都拖不动。连点的第二下 Qt 报成双击、不报按下。
        双击也当成一次按下：按住就能拖；松手没拖动才算双击（链接留空就当普通点一下）。"""
        from unittest import mock
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        import widget.input as input_mod
        self.win.show()
        self.win.move(100, 400)
        local = QPointF(self.win.width() / 2, self.win.height() - 70)          # 狗身上
        g0 = QPointF(self.win.mapToGlobal(local.toPoint()))

        def ev(kind, shift, buttons):
            return QMouseEvent(kind, local + shift, g0 + shift, Qt.LeftButton, buttons, Qt.NoModifier)

        self.win.set_dynamic(True)
        clicks = []
        self.win.playground.dog_unpress = lambda *a: clicks.append(1)
        none = QPointF(0, 0)
        self.win.mousePressEvent(ev(QEvent.MouseButtonPress, none, Qt.LeftButton))
        self.win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, none, Qt.NoButton))
        self.assertEqual(len(clicks), 1, "先点一下")
        start = self.win.scene_world()
        self.win.mouseDoubleClickEvent(ev(QEvent.MouseButtonDblClick, none, Qt.LeftButton))   # 紧接着按下：Qt 报成双击
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, QPointF(40, 0), Qt.LeftButton))
        self.win._apply_drag()                              # 每帧挪一次，这里当下一帧到了（灵动交互里窗口铺宽了，挪的是窗口里的狗）
        self.assertAlmostEqual(self.win.scene_world()[0], start[0] + 40, delta=0.6, msg="按住就能拖")
        self.win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, QPointF(40, 0), Qt.NoButton))
        self.win.playground.dog_unpress = lambda *a: clicks.append(1)
        self.assertLessEqual(len(clicks), 2, "拖了不算点")
        clicks[:] = [1]
        self.win.mouseDoubleClickEvent(ev(QEvent.MouseButtonDblClick, QPointF(40, 0), Qt.LeftButton))
        self.win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, QPointF(40, 0), Qt.NoButton))
        self.assertEqual(len(clicks), 2, "没拖动的双击：当普通点一下")

    def test_dots_come_back_after_a_drag_even_if_qt_lost_the_enter_event(self):
        """拖完小组件，三个点要鼠标出去再进来才出现。拖动中 Qt 会丢 Enter（_hover 变 False、之后不再给 Enter）：
        松手时鼠标还在狗上就算悬停重新计时；没按键的移动落在窗口里也算。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        def tick():
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        def ev(kind, pos, button=Qt.NoButton, buttons=Qt.NoButton):
            return QMouseEvent(kind, pos, QPointF(self.win.mapToGlobal(pos.toPoint())), button, buttons, Qt.NoModifier)
        self.win.show()
        self.win.move(100, 400)
        self.win.enterEvent(None)
        self.win.hover.since = time.perf_counter() - 1.0
        for _ in range(4):
            tick()
        self.assertGreater(self.win.hover.alpha, 0.0)
        foot = QPointF(30, self.win.height() - 30)                           # 狗脚边、不在三个点上
        self.assertFalse(self.win.hover.on_menu(foot.toPoint()))
        self.win.mousePressEvent(ev(QEvent.MouseButtonPress, foot, Qt.LeftButton, Qt.LeftButton))
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, foot + QPointF(30, 0), Qt.NoButton, Qt.LeftButton))
        self.assertTrue(self.win._dragged)
        self.win.leaveEvent(None)                                            # 拖动中 Qt 丢的那个 Leave
        for _ in range(6):
            tick()
        self.assertEqual(self.win.hover.alpha, 0.0, "拖动时不出现")
        self.win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, foot + QPointF(30, 0), Qt.LeftButton))
        self.assertTrue(self.win.hover.active, "松手时鼠标还在狗上：算悬停")
        self.win.hover.since = time.perf_counter() - 1.0
        for _ in range(4):
            tick()
        self.assertGreater(self.win.hover.alpha, 0.0, "三个点照常出来，不用出去再进来")
        self.win.leaveEvent(None)
        self.assertFalse(self.win.hover.active)
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, foot))                 # 没 Enter 只有移动：落在窗口里也算悬停
        self.assertTrue(self.win.hover.active)

    def test_click_on_the_dog_is_a_click_not_a_drag(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        self.win.show()
        self._on_floor(self.win)
        self.win.set_dynamic(True)
        for _ in range(8 * 60):
            self.win.dog.update(1 / 60)
            self.win.dog.frame()
        self.assertEqual(self.win.dog.posture, "standing", "打开灵动交互先站着")
        start = QPoint(self.win.x() + 100, self.win.y() + 100)
        def ev(kind, pos, buttons):
            return QMouseEvent(kind, QPointF(pos - self.win.pos()), QPointF(pos), Qt.LeftButton, buttons, Qt.NoModifier)
        self.win.mousePressEvent(ev(QMouseEvent.Type.MouseButtonPress, start, Qt.LeftButton))
        self.win.mouseMoveEvent(ev(QMouseEvent.Type.MouseMove, start + QPoint(2, 1), Qt.LeftButton))   # 2 像素：还是点击
        self.win.mouseReleaseEvent(ev(QMouseEvent.Type.MouseButtonRelease, start + QPoint(2, 1), Qt.NoButton))
        self.assertIsNone(self.win.playground.roam.task, "点狗不跳（点一下只 duang）")
        self.assertFalse(self.win.dog.expr.pressing, "弹回来了")
        before = self.win.scene_world()
        self.win.mousePressEvent(ev(QMouseEvent.Type.MouseButtonPress, start, Qt.LeftButton))
        self.win.mouseMoveEvent(ev(QMouseEvent.Type.MouseMove, start + QPoint(40, 0), Qt.LeftButton))     # 40 像素：拖
        self.win.mouseReleaseEvent(ev(QMouseEvent.Type.MouseButtonRelease, start + QPoint(40, 0), Qt.NoButton))
        self.assertAlmostEqual(self.win.scene_world()[0], before[0] + 40, delta=0.6, msg="狗跟手（灵动交互里窗口铺宽了，不跟着挪）")
        self.assertTrue(self.win._wide, "一拖就铺宽")

    def test_clicking_elsewhere_on_the_screen_no_longer_makes_the_dog_jump(self):
        """点屏幕别处是你自己在用电脑（开着台前调度时点桌面还会把窗口收起来），狗不该跟着跳。"""
        import time
        import widget.input as input_mod
        self.win.show()
        self._on_floor(self.win)
        self.win.set_dynamic(True)
        down = {"v": False}
        with mock.patch.object(input_mod.native, "mouse_left_down", lambda: down["v"]):
            for k in range(12):
                down["v"] = k % 2 == 0
                self.win._last_tick = time.perf_counter() - 1 / 60
                self.win._tick()
        dog = self.win.dog
        self.assertIsNone(dog.jump, "没跳")
        self.assertFalse(self.win.playground.roam.busy)

    def test_posture_strip_slides_out_of_the_dots_when_selectable(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        def tick():
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        def ev(kind, pos, button=Qt.NoButton, buttons=Qt.NoButton):
            return QMouseEvent(kind, pos, QPointF(self.win.mapToGlobal(pos.toPoint())), button, buttons, Qt.NoModifier)
        self.win.show()
        self.win.move(100, 400)
        self.win.set_follow_cursor(True)
        self.win.enterEvent(None)
        self.win.hover.since = time.perf_counter() - 1.0
        for _ in range(4):
            tick()
        self.assertEqual(self.win.hover.posture_rects(), [], "没悬在三个点上不滑出")
        dots = self.win.hover.rect()
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, dots.center()))
        self.assertTrue(self.win.hover.hot)
        for _ in range(4):
            tick()
        self.assertEqual(self.win.hover.post_open, 1.0)
        rects = self.win.hover.posture_rects()
        self.assertEqual([pid for pid, _ in rects], ["standing", "sitting", "lying", "sleeping"])
        self.assertTrue(all(r.left() > dots.right() for _, r in rects) or all(r.right() < dots.left() for _, r in rects), "在三个点旁边一字排开")
        sit = next(r for pid, r in rects if pid == "sitting")
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, sit.center()))
        self.assertEqual(self.win.hover.hot_posture, "sitting")
        for _ in range(6):
            tick()
        self.assertEqual(self.win.hover.alpha, 1.0, "鼠标在姿势按钮上：三个点和四个按钮都全实")
        above = QPointF(sit.center().x(), sit.top() - 5)                    # 画出来的胶囊上方 5 像素：也算在按钮上（可点范围和「···」一样大一圈）
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, above))
        self.assertEqual(self.win.hover.hot_posture, "sitting", "可点范围上下各扩 6 像素")
        self.assertFalse(self.win.hover.hot)
        self.win.mousePressEvent(ev(QEvent.MouseButtonPress, above, Qt.LeftButton, Qt.LeftButton))
        self.assertIsNone(self.win._drag, "点姿势按钮不是拖狗")
        self.win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, above, Qt.LeftButton))
        self.assertEqual(self.win.rest_posture, "sitting")
        hit = dict(self.win.hover.posture_hit_rects())
        drawn = dict(self.win.hover.posture_rects())
        self.assertEqual(hit["sitting"].height(), drawn["sitting"].height() + 12)
        self.assertAlmostEqual(hit["standing"].right(), hit["sitting"].left(), msg="相邻按钮的可点范围在缝中间接上，不重叠")
        self.assertEqual(hit["sleeping"].right(), drawn["sleeping"].right() + 6, "两头扩 6")
        stand = drawn["standing"]
        sit = drawn["sitting"]
        on_sit_side = QPointF(sit.left() - 1, sit.center().y())             # 站和坐之间的缝里、靠坐那半
        self.assertEqual(self.win.hover.posture_at(on_sit_side.toPoint()), "sitting")
        self.assertEqual(self.win.hover.posture_at(QPointF(stand.right() + 1, stand.center().y()).toPoint()), "standing")
        self.win.set_dynamic(True)
        self.win.playground.roam.cancel(drop_ball=False)    # 窗口放在半空，刚开灵动交互狗会往下掉（在空中不出「···」）
        for _ in range(4):
            tick()
        rects = dict(self.win.hover.posture_rects())
        self.assertEqual(list(rects), ["tool:ball/red", "__custom__"], "灵动交互开着：这一条是道具栏，默认只有小球，最右边「自定义」")
        before = self.win.ball_out
        from PySide6.QtCore import QEvent as _E
        from PySide6.QtGui import QMouseEvent as _M
        p = rects["tool:ball/red"].center()
        g = QPointF(self.win.mapToGlobal(p.toPoint()))
        self.win.mousePressEvent(_M(_E.MouseButtonPress, p, g, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.win.mouseReleaseEvent(_M(_E.MouseButtonRelease, p, g, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        self.assertEqual(self.win.ball_out, not before, "点一下切换")
        self.win.set_ball_out(before)

    def test_menu_button_holds_still_through_a_jump_and_is_pinned_while_aimed_at(self):
        """用户测试：按钮跟着狗跳、晃，点不准。现在高度按当前姿势的循环片段定，跳不动；鼠标冲着它来（在它附近、在条上、按着）时横向、高度都钉住，
        转身、换姿势都不挪（鼠标不离开按钮就永远不动）；鼠标只是在狗身上就跟着转身、换姿势 0.25 秒平滑挪过去
        （扔出去落地以后狗转了身、站起来了，按钮还钉在原来那儿，要移开再移上去才回来）。"""
        from PySide6.QtCore import QPoint
        def tick():
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        h = self.win.hover
        self.win.show()
        self.win.move(100, 400)
        self.win.set_dynamic(True)
        for _ in range(60):                                   # 6 秒：站好、转到 home
            tick()
        self.assertEqual(self.win.dog.posture, "standing")
        self.win.enterEvent(None)
        h.since = time.perf_counter() - 1.0
        for _ in range(4):
            tick()
        lift0, x0 = h.lift, h.x
        self.win.dog._start_jump()                            # 起跳
        peak, frames = 0.0, 0
        while (self.win.dog.jump is not None or frames < 5) and frames < 300:
            tick()
            peak = max(peak, self.win.dog.y_offset)
            self.assertAlmostEqual(h.lift, lift0, delta=0.5, msg="跳的时候按钮不动")
            frames += 1
        self.assertGreater(peak, 0.1, "确实跳起来了")
        self.win.dog.auto_turn = False                        # 这里只看按钮：别让狗按鼠标位置自己转回去
        h.mouse_move(h.rect().center().toPoint())            # 鼠标到了「···」上
        self.assertTrue(h.hot and h.near)
        self.win.dog.yaw = (self.win.dog.yaw + 180.0) % 360.0   # 转过身：锚点从一侧肩膀换到另一侧
        for _ in range(10):
            tick()
        self.assertAlmostEqual(h.x, x0, delta=0.5, msg="鼠标在按钮上：横向钉住")

        def on_body():                                        # 狗身子正中：在狗身上、离按钮远
            return QPoint(round(self.win.scene_x), round(self.win.scene_ground - 0.25 * self.win.ppm))
        h.mouse_move(on_body())
        self.assertFalse(h.hot or h.near)
        for _ in range(20):
            tick()
        self.assertTrue(h.active, "还在狗身上：照样悬停")
        self.assertGreater(abs(h.x - x0), 0.3 * self.win.ppm, "鼠标只是在狗身上：跟着转身挪过去")
        h.mouse_move(h.rect().center().toPoint())            # 又到了「···」上
        self.win.set_dynamic(False)
        self.win.set_rest_posture("lying")                    # 鼠标在按钮上换姿势：按钮高度钉住，窗口也不缩到把它顶下来
        lift1 = h.lift
        for _ in range(40):
            tick()
            self.assertAlmostEqual(h.lift, lift1, delta=0.01, msg="鼠标不离开按钮，按钮高度不变")
            self.assertGreaterEqual(self.win.height(), self.win.ground_px + lift1 + 18 + 2, "窗口给钉住的按钮留着位置")
        self.assertEqual(self.win.dog.posture, "lying")
        h.mouse_move(on_body())                               # 移回狗身上：降到趴着的高度
        lifts = []
        for _ in range(40):
            tick()
            lifts.append(h.lift)
        self.assertAlmostEqual(lifts[-1], self.win.dog.rest_top() * self.win.ppm + 6, delta=1.0, msg="到了趴着的高度")
        self.assertLess(lifts[-1], lift0 - 0.1 * self.win.ppm, "趴着比站着低")
        self.assertTrue(all(b <= a + 0.01 for a, b in zip(lifts, lifts[1:])), "一路往下平滑，不跳")

    def test_a_hidden_button_goes_straight_to_where_it_belongs(self):
        """看不见的时候（拎着、飞着、淡没了）按钮直接到该在的地方：扔出去落地、转了身、换了姿势以后一出来就在肩膀上方。"""
        from widget.hovermenu import MENU_FORWARD
        h, dog = self.win.hover, self.win.dog
        self.win.show()
        self.win.move(200, 300)
        h.track(1 / 60)
        h.set_hover(True)                                     # 鼠标在狗身上，按钮还没淡出来（飞着、刚落地时就是这样）
        h.alpha = 0.0
        dog.auto_turn = False
        dog.yaw = (dog.yaw + 180.0) % 360.0
        h.track(1 / 60)
        forward = 1.0 if math.cos(math.radians(dog.yaw)) >= 0 else -1.0
        self.assertAlmostEqual(h.x_m, dog.x + forward * MENU_FORWARD, places=6, msg="一帧就到肩膀上方，不慢慢滑")
        self.assertAlmostEqual(h.top_m, dog.rest_top(), places=6)

    def test_pinned_menu_button_scales_with_the_dog_when_zooming(self):
        """鼠标在狗上时「···」钉住不动；钉住的是在狗身上的位置，缩放时跟着狗一起缩放（钉窗口像素的话，
        滚轮 / 捏合缩放时鼠标正好在狗上，放大 4 格漂出去近 100 像素、压进狗头，移开鼠标才滑回来）。"""
        from widget.hovermenu import MENU_FORWARD, MENU_GAP
        self.win.show()
        self.win.move(200, 300)
        hover, dog = self.win.hover, self.win.dog
        hover.track(1 / 60)
        hover.set_hover(True)                                   # 鼠标在狗上：滚轮、捏合缩放时就是这样，按钮钉住
        for factor in (1.15,) * 4 + (1 / 1.15,) * 8:
            self.win.zoom(factor)
            hover.track(1 / 60)
            forward = 1.0 if math.cos(math.radians(dog.yaw)) >= 0 else -1.0
            r = hover.rect()
            want_x = self.win.width() / 2 + (dog.x + forward * MENU_FORWARD) * self.win.ppm
            want_top = self.win.height() - self.win.ground_px - (dog.rest_top() * self.win.ppm + MENU_GAP * hover.k()) - r.height()
            self.assertAlmostEqual(r.center().x(), want_x, delta=1.0, msg=f"缩放到 {self.win.scale:.2f}：还在肩膀上方")
            self.assertAlmostEqual(r.top(), max(2.0, want_top), delta=1.0, msg=f"缩放到 {self.win.scale:.2f}：高度跟着狗，不压进狗头")

    def test_clicks_in_the_menu_hit_area_open_the_menu_and_never_count_as_dog_clicks(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        def tick():
            self.win._last_tick = time.perf_counter() - 0.2
            self.win._tick()
        def ev(kind, pos, button=Qt.NoButton, buttons=Qt.NoButton):
            return QMouseEvent(kind, pos, QPointF(self.win.mapToGlobal(pos.toPoint())), button, buttons, Qt.NoModifier)
        self.win.show()
        self.win.move(100, 400)
        self.win.set_dynamic(True)
        for _ in range(60):
            tick()
        self.win.enterEvent(None)
        self.win.hover.since = time.perf_counter() - 1.0
        for _ in range(4):
            tick()
        opened = []
        self.win.open_settings = lambda: opened.append(True)
        r, hit = self.win.hover.rect(), self.win.hover.hit_rect()
        self.assertEqual((round(hit.width()), round(hit.height())), (44, 30), "可点范围 44×30")
        spot = QPointF(r.right() + 4, r.center().y())        # 画出来的胶囊外面、可点范围里面
        self.assertFalse(r.contains(spot))
        self.assertTrue(hit.contains(spot))
        self.win.mouseMoveEvent(ev(QEvent.MouseMove, spot))
        self.assertTrue(self.win.hover.hot, "可点范围里就算悬在按钮上")
        clicks = []
        self.win.playground.dog_click = lambda *a: clicks.append(1)
        self.win.mousePressEvent(ev(QEvent.MouseButtonPress, spot, Qt.LeftButton, Qt.LeftButton))
        self.assertIsNone(self.win._drag, "不是拖狗")
        self.win.mouseReleaseEvent(ev(QEvent.MouseButtonRelease, spot, Qt.LeftButton))
        self.assertEqual(len(opened), 1, "只开菜单")
        self.assertEqual(clicks, [], "不算点狗")

    def test_window_keeps_room_for_the_menu_and_never_resizes_on_hover(self):
        """悬停时窗口临时变大不行。窗口一直给「···」留着高度：鼠标进来、三个点出来、姿势条滑出、离开，窗口一像素都不变。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        def tick():
            self.win._last_tick = time.perf_counter() - 0.05
            self.win._tick()
        self.win.show()
        self.win.move(150, 350)
        self.win.set_follow_cursor(True)                                  # 互动模式：有姿势条
        for posture in ("standing", "sitting", "lying"):
            self.win.set_rest_posture(posture)
            self.win.dog.action_at = float("inf")
            for _ in range(120):                                          # 6 秒：换好姿势
                tick()
            self.win._shrink_at = None
            far = time.perf_counter() + 1000.0
            self.win._fit_height(now=far)
            self.win._fit_height(now=far + 10.0)                          # 防抖时间过了，该缩的缩完
            size = (self.win.width(), self.win.height())
            self.win.enterEvent(None)
            self.win.hover.since = time.perf_counter() - 1.0
            sizes = set()
            for _ in range(10):
                tick()
                sizes.add((self.win.width(), self.win.height()))
            dots = self.win.hover.rect()
            gp = QPointF(self.win.mapToGlobal(dots.center().toPoint()))
            self.win.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, dots.center(), gp, Qt.NoButton, Qt.NoButton, Qt.NoModifier))
            for _ in range(10):
                tick()
                sizes.add((self.win.width(), self.win.height()))
            self.assertEqual(self.win.hover.post_open, 1.0)
            self.assertTrue(self.win.rect().contains(self.win.hover.rect().toRect()), f"{posture}：「···」在窗口里")
            self.win.leaveEvent(None)
            for _ in range(60):
                tick()
                sizes.add((self.win.width(), self.win.height()))
            self.win._fit_height(now=time.perf_counter() + 5.0)
            sizes.add((self.win.width(), self.win.height()))
            self.assertEqual(sizes, {size}, f"{posture}：悬停前后窗口大小一直不变")

    def test_posture_strip_fits_in_the_window_at_every_size(self):
        """缩小时「···」旁边的姿势条超出窗口被裁掉（中文六成、英文八成以下）。现在窗口一直至少放得下它（悬停时不改大小），
        中英文、两个朝向、醒着四个 / 睡着一个「醒来」都在窗口里；正常大小时窗口还是贴着狗的宽度。"""
        from PySide6.QtWidgets import QApplication
        from widget.hovermenu import needed_width
        ag = QApplication.primaryScreen().availableGeometry()
        hover, dog = self.win.hover, self.win.dog
        self.win.show()
        self.win.set_follow_cursor(True)
        for lang in ("en", "zh"):
            self.win.set_language(lang)
            for pct in (30, 35, 40, 50, 60, 70, 80, 90, 100, 130, 160):
                s = pct / 100
                self.win.set_scale(s)
                self.win.move(ag.center().x() - self.win.width() // 2, ag.center().y() - self.win.height() // 2)
                if (lang, s) == ("zh", 0.6) or s >= 1.0:
                    self.assertEqual(self.win.width(), round(config.WINDOW_WIDTH * s), f"{lang} {pct}%：放得下时窗口还是贴着狗的宽度")
                self.assertEqual(self.win.width(), max(round(config.WINDOW_WIDTH * s), needed_width(s)))
                for yaw in (210.0, 330.0):
                    for state in ("awake", "asleep"):
                        dog.yaw = yaw
                        hover.top_m = hover.x_m = None
                        hover.track(0.0)
                        hover.alpha, hover.post_open = 1.0, 1.0
                        with mock.patch.object(dog, "sleep_state", lambda _s=state: _s):
                            rects = [hover.rect()] + [r for _, r in hover.posture_rects()]
                        self.assertEqual(len(rects), 5 if state == "awake" else 2)
                        left, right = min(r.left() for r in rects), max(r.right() for r in rects)
                        self.assertGreaterEqual(left, 0.0, f"{lang} {pct}% 朝向 {yaw:.0f} {state}：左边没出窗口")
                        self.assertLessEqual(right, self.win.width(), f"{lang} {pct}% 朝向 {yaw:.0f} {state}：右边没出窗口")
        self.win.set_scale(0.3)
        self.win.set_language("en")
        w_en = self.win.width()
        self.win.set_language("zh")
        self.assertLess(self.win.width(), w_en, "换语言：缩小时窗口宽度跟着姿势条变")
        self.win.set_language("en")
        self.assertEqual(self.win.width(), w_en)

    def _shape_mode(self):
        """装作在 macOS 上、画过第一帧：鼠标底下是不是狗用假的（狗占 dog 这块），鼠标位置用假的，记下每次告诉系统的"不接鼠标"。"""
        import widget.input as input_mod
        from PySide6.QtCore import QPoint
        w = self.win
        cursor = {"pos": QPoint(0, 0)}
        told = []
        class FakeCursor:
            @staticmethod
            def pos():
                return cursor["pos"]
        def ignores(_win, on):
            told.append(on)
            return True
        def tick():
            w._last_tick = time.perf_counter() - 0.05
            w._tick()
        def at(local):
            cursor["pos"] = w.mapToGlobal(local)
        patches = [mock.patch.object(input_mod, "QCursor", FakeCursor), mock.patch.object(input_mod.native, "set_ignores_mouse", ignores)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        w._shape = True
        return at, tick, told

    def test_only_the_dog_takes_clicks_and_hover(self):
        """窗口透明的地方太大，点空白也算点到狗。现在点击范围就是狗：鼠标底下不是狗就让窗口不接鼠标（点击穿到后面），
        是狗或「···」才接；悬停也按狗算；「···」出来以后它正下方那条空白不算离开；按着的时候不切；重新显示过（Qt 会把原生的接不接鼠标改回去）下一帧再说一次。"""
        from PySide6.QtCore import QPoint, QRect
        w, hover = self.win, self.win.hover
        w.show()
        w.move(200, 300)
        at, tick, told = self._shape_mode()
        w.view.probe = lambda x, y, m: False                               # 先站好（躺好）：鼠标在空白处，「···」看不见时直接到它该在的地方
        at(QPoint(4, 4))
        for _ in range(10):
            tick()
        dots = hover.rect().toRect()
        dog = QRect(dots.center().x() - 100, dots.bottom() + 40, 200, w.height() - round(w.ground_px) - dots.bottom() - 40)
        w.view.probe = lambda x, y, m: dog.adjusted(-round(m), -round(m), round(m), round(m)).contains(QPoint(round(x), round(y)))
        blank = QPoint(4, 4)
        self.assertFalse(dog.contains(blank) or hover.rect().contains(blank))
        at(blank)
        tick()
        self.assertEqual(told[-1], True, "空白处：窗口不接鼠标，点击穿到后面")
        self.assertFalse(hover.active, "空白处不算悬停")
        w.enterEvent(None)
        self.assertFalse(hover.active, "系统的进出事件不算（窗口不接鼠标时本来就收不到）")
        at(dog.center())
        tick()
        self.assertEqual(told[-1], False, "狗身上：接鼠标")
        self.assertTrue(hover.active, "狗身上算悬停")
        at(QPoint(dog.left() - 2, dog.center().y()))
        tick()
        self.assertEqual(told[-1], False, "狗的边上 3 像素内也算狗")
        hover.since = time.perf_counter() - 1.0
        for _ in range(4):
            tick()
        self.assertGreater(hover.alpha, 0.0, "停在狗身上：「···」出来")
        at(hover.rect().center().toPoint())
        tick()
        self.assertEqual(told[-1], False, "「···」上：接鼠标")
        self.assertTrue(hover.hot, "窗口不接鼠标时收不到移动，每帧补一次：悬在「···」上")
        between = QPoint(dots.center().x(), dots.bottom() + 25)            # 从狗背上移到「···」要经过的空白
        self.assertFalse(dog.contains(between) or hover.hit_rect().contains(between))
        at(between)
        tick()
        self.assertEqual(told[-1], True, "「···」和狗中间的空白：点击照样穿过去")
        self.assertTrue(hover.active, "但不算离开，「···」不收")
        self.assertIsNone(w._left_at)
        w.leaveEvent(None)
        self.assertTrue(hover.active, "系统报离开也不算")
        at(blank)
        tick()
        self.assertTrue(hover.active, "离开 0.3 秒之内还算悬停（斜着移过去难免擦过空白）")
        w._left_at -= 1.0
        tick()
        self.assertFalse(hover.active, "离开 0.3 秒后才算离开")
        at(dog.center())
        tick()
        w._drag = QPoint(10, 10)                                            # 按住狗
        w.view.probe = lambda x, y, m: False                                # 狗动了，鼠标底下没狗了
        tick()
        self.assertEqual(told[-1], False, "按着的时候不切，拖到一半不会脱手")
        w._drag = None
        tick()
        self.assertEqual(told[-1], True, "松开了才按鼠标底下的切")
        w.view.probe = lambda x, y, m: True
        tick()
        self.assertEqual(told[-1], False, "鼠标底下又是狗：接鼠标")
        n = len(told)
        tick()
        self.assertEqual(told[n:], [], "没变就不再说")
        w.hide()
        w.show()
        tick()
        self.assertEqual(told[n:], [False], "重新显示过：下一帧重新告诉系统一次（showEvent 清掉 _accepting）")

    def test_the_rim_over_the_dog_is_not_the_dog(self):
        """狗趴在窝里右键窝，弹的是设置卡片——窝沿那一层点得穿，点在窝沿上落到被它挡住的狗身上。
        鼠标在盖着狗的物件看得见的地方（_covered，things.covers_dog）：鼠标底下就算是狗也不接，点击落到物件本身的窗口；没盖着的狗照旧接。"""
        from PySide6.QtCore import QPoint
        w = self.win
        w.show()
        w.move(200, 300)
        at, tick, told = self._shape_mode()
        w.view.probe = lambda x, y, m: True                                 # 鼠标底下是狗（被窝沿挡着的身子也是）
        rim = {"on": False}
        with mock.patch.object(w, "_covered", lambda: rim["on"]):
            at(QPoint(w.width() // 2, w.height() - 40))
            tick()
            self.assertEqual(told[-1], False, "没盖着：狗接鼠标")
            rim["on"] = True
            tick()
            self.assertEqual(told[-1], True, "窝沿盖着的地方：狗不接，点击、右键落到窝的窗口")
            rim["on"] = False
            tick()
            self.assertEqual(told[-1], False)

    def test_menu_button_moves_beside_the_dog_near_the_top_of_the_screen(self):
        """狗要能放到屏幕最顶上。头顶到屏幕最上沿放不下「···」时挪到狗旁边（狗背那一侧），离开屏幕顶又回到头顶上。"""
        from PySide6.QtWidgets import QApplication
        from widget.hovermenu import SIDE_OFFSET_M
        w, hover = self.win, self.win.hover
        w.show()
        top = QApplication.primaryScreen().geometry().top()
        w.place_scene(400.0, top + w.dog.rest_top() * w.ppm + 4)          # 狗头几乎顶到屏幕最上沿
        for _ in range(60):
            hover.track(1 / 30)
        self.assertTrue(hover.side, "头顶放不下：挪到旁边")
        r = hover.rect()
        forward = 1.0 if math.cos(math.radians(w.dog.yaw)) >= 0 else -1.0
        self.assertLess((r.center().x() - w.scene_x) * forward, -SIDE_OFFSET_M * w.ppm * 0.9, "在狗背那一侧，不挡脸")
        self.assertGreater(r.bottom(), w.scene_ground - w.dog.rest_top() * w.ppm, "和狗头差不多高，不在头顶上方")
        self.assertLessEqual(w._height_needed(), max(round(config.WINDOW_HEIGHT * w.scale),
                                                     math.ceil(w.ground_px + w.dog.stance_top() * w.ppm + 6 * w.scale)),
                             "窗口不用再为按钮往上长")
        w.place_scene(400.0, top + 500)
        for _ in range(60):
            hover.track(1 / 30)
        self.assertFalse(hover.side, "离开屏幕顶：回到头顶上")

    def test_menu_button_stays_out_of_the_menu_bar_and_notch_strip(self):
        """屏幕顶上那一条（菜单栏、刘海）不算地方：头顶离那一条不够高就挪到旁边；按钮怎么都画在那一条下面
        （刘海那一块没有像素，画进去看不见、却点得到）。离那一条够高了回到头顶上。"""
        from PySide6.QtCore import QRectF
        from PySide6.QtWidgets import QApplication
        from widget import hovermenu
        w, hover = self.win, self.win.hover
        w.show()
        g = QApplication.primaryScreen().geometry()
        band = 32
        usable = QRectF(g.left(), g.top() + band, g.width(), g.height() - band)
        with mock.patch.object(hovermenu.HoverMenu, "_usable", lambda self: usable):
            w.place_scene(400.0, g.top() + band + w.dog.rest_top() * w.ppm + 4)    # 头顶到那一条下沿只差 4 像素（按屏幕最上沿算放得下）
            for _ in range(60):
                hover.track(1 / 30)
            self.assertTrue(hover.side, "离那一条不够高：挪到旁边")
            w.place_scene(400.0, g.top() + w.dog.rest_top() * w.ppm + 4)           # 狗头伸进那一条
            for _ in range(60):
                hover.track(1 / 30)
            self.assertGreaterEqual(w.y() + hover.rect().top(), g.top() + band, "按钮画在那一条下面")
            w.place_scene(400.0, g.top() + band + w.dog.rest_top() * w.ppm + 80)
            for _ in range(60):
                hover.track(1 / 30)
            self.assertFalse(hover.side, "离那一条够高了：回到头顶上")

    def test_menu_button_goes_to_the_face_side_when_the_back_is_at_the_screen_edge(self):
        """头顶放不下、狗背贴着屏幕边（那一侧放不下）：按钮到脸那一侧，比狗背那一侧低（在胸前，不挡脸）；画在哪就点得到哪。"""
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from widget.hovermenu import PLACE_FRONT, SIDE_HEIGHT, SIDE_OFFSET_M
        w, hover = self.win, self.win.hover
        w.show()
        a = QApplication.primaryScreen().availableGeometry()
        forward = 1.0 if math.cos(math.radians(w.dog.yaw)) >= 0 else -1.0
        x = a.left() + 10 if forward > 0 else a.left() + a.width() - 10               # 狗背那一侧贴着屏幕边
        w.place_scene(float(x), a.top() + w.dog.rest_top() * w.ppm + 4)
        for _ in range(60):
            hover.track(1 / 30)
        self.assertEqual(hover.place, PLACE_FRONT)
        r = hover.rect()
        self.assertGreater((r.center().x() - w.scene_x) * forward, SIDE_OFFSET_M * w.ppm * 0.9, "在脸那一侧")
        self.assertGreater(r.center().y(), w.scene_ground - SIDE_HEIGHT * w.dog.rest_top() * w.ppm + 1, "比狗背那一侧低，不挡脸")
        hover.alpha = 1.0
        self.assertTrue(hover.on_controls(r.center().toPoint()), "画在哪就点得到哪")
        self.assertFalse(hover.on_controls(r.center().toPoint() - QPoint(0, round(r.height() * 2))), "上面一截点不到")

    def test_cards_sit_next_to_the_dog_not_the_wider_window(self):
        """缩小时窗口比狗宽（给姿势条留的，透明、点不到）：设置卡片还是贴着狗摆（dog_rect），不按窗口。"""
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QApplication
        from widget.sticker import SHADOW
        ag = QApplication.primaryScreen().availableGeometry()
        self.win.show()
        self.win.set_scale(0.4)
        dog = self.win.dog_rect()
        self.assertLess(dog.width(), self.win.width(), "40% 时窗口比狗宽")
        self.assertAlmostEqual(dog.center().x(), self.win.frameGeometry().center().x(), delta=1,
                               msg="同一条中线；狗和窗口整数宽度奇偶不同时最多半个像素取整差")
        self.win.move(ag.right() - self.win.width(), ag.top())             # 右上角
        dog = self.win.dog_rect()
        self.win.open_settings()
        self.app.processEvents()
        s = self.settings
        card = QRect(s.x() + SHADOW, s.y() + SHADOW, s.width() - 2 * SHADOW, s.height() - 2 * SHADOW)
        self.assertLessEqual(card.right(), dog.left(), "卡片在狗左边")
        self.assertGreater(card.right(), self.win.x(), "贴着狗，不是贴着更宽的窗口")
        s.hide()

    def test_fade_in(self):
        from PySide6.QtTest import QTest
        self.win.fade_in(seconds=0.05)
        self.assertTrue(self.win.isVisible())
        for _ in range(50):                                # 等淡入真的走完（最多 1 秒）；机器忙时固定等 150 毫秒会差最后一帧
            if abs(self.win.windowOpacity() - 1.0) < 0.005:
                break
            QTest.qWait(20)
        self.assertAlmostEqual(self.win.windowOpacity(), 1.0, places=2)

    def test_context_menu_targets_exist_and_toggle(self):
        self.win.open_settings()
        self.assertTrue(self.settings.isVisible())
        self.win.open_settings()
        self.assertTrue(self.settings.closing, "再点一次：淡出关上")
        self.win.open_settings()
        self.assertTrue(self.settings.isVisible() and not self.settings.closing, "淡出时又点：停下淡回来")
        self.win.open_settings()
        self.settings.finish_page_anim()
        self.assertFalse(self.settings.isVisible())


class HoverMotionGeometryTests(unittest.TestCase):
    """动效只依赖浮点几何，不需要模型、GL 或面板计时器。"""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from types import SimpleNamespace
        from widget.hovermenu import HoverMenu
        self.window = SimpleNamespace(
            scale=1.0, ppm=100.0, scene_x=350.0, scene_ground=160.0,
            dynamic=False, rest_posture="standing", accent_color=lambda: "#7F8FA6",
            tool_entries=lambda: [("ball/red", "Ball")], thing_on=lambda key: True,
            dog=SimpleNamespace(rest_top=lambda: 1.0, posture_tops=lambda: (1.0, 1.0), sleep_state=lambda: "awake", x=0.0, yaw=330.0),
            width=lambda: 760, height=lambda: 180, x=lambda: 0, y=lambda: 0,
            screen=lambda: None, setCursor=lambda cursor: None, _dirty=False,
        )
        self.hover = HoverMenu(self.window)
        self.hover.track(0.0)
        self.hover.set_hover(True)
        self.hover.alpha = self.hover.post_open = 1.0
        self.hover._on_right = True

    def settle(self, frames=60):
        for _ in range(frames):
            self.hover._tick_motion(1 / 120)

    def test_popup_placement_tries_sides_when_vertical_room_is_insufficient(self):
        from PySide6.QtCore import QPointF, QRectF
        from widget.popup import place_menu
        screen, painted = QRectF(0, 0, 800, 120), QRectF(8, 8, 120, 58)
        for anchor, expected in ((QRectF(200, 45, 220, 30), "right"),
                                 (QRectF(610, 45, 180, 30), "left")):
            pos, side = place_menu(anchor.center(), painted, screen, anchor, 12)
            result = painted.translated(QPointF(pos))
            self.assertEqual(side, expected)
            self.assertTrue(screen.contains(result))
            self.assertFalse(result.intersects(anchor))
            if side == "right":
                self.assertGreaterEqual(result.left() - anchor.right(), 12)
            else:
                self.assertGreaterEqual(anchor.left() - result.right(), 12)

    def test_capture_guard_keeps_hover_selection_and_anchor_state_unchanged(self):
        from PySide6.QtCore import QPoint
        from widget.hovermenu import DOTS
        h, w = self.hover, self.window
        h.mouse_move(dict(h.posture_rects())["sitting"].center())
        self.settle()

        def state():
            return (h.alpha, h.post_open, h._on_right, h.top_m, h.x_m, h.hot_posture,
                    tuple((key, value.value) for key, value in h._motions.items()),
                    tuple((key, value.value) for key, value in h._selected.items()))

        before = state()
        with mock.patch("widget.hovermenu.ui_frozen", return_value=True):
            w.dog.x, w.dog.yaw, w.rest_posture = 2.0, 90.0, "sleeping"
            w.dog.sleep_state = lambda: "asleep"
            h.set_hover(False)
            h.mouse_move(QPoint())
            h.begin_press(DOTS, QPoint())
            self.assertIsNone(h.end_press(QPoint()))
            h.tick(0.5, time.perf_counter(), False)
            h.track(0.5)
            self.assertEqual(state(), before, "截图选区输入不能改变悬停、选择进度或锚点；冻结画面由CaptureUI统一保存")
        h.set_hover(False)
        h.tick(0.5, time.perf_counter(), False)
        self.assertNotEqual(state(), before, "截图结束后恢复正常交互")

    def test_hover_shrinks_evenly_and_neighbours_move_closer_without_scaling_them(self):
        from widget.hovermenu import HOVER_SCALE
        h = self.hover
        before = dict(h.posture_rects())
        h.mouse_move(before["sitting"].center())
        h._tick_motion(1 / 120)
        first = dict(h.posture_rects())["sitting"]
        self.assertLess(first.width(), before["sitting"].width())
        self.assertGreater(first.width(), before["sitting"].width() * HOVER_SCALE)
        self.settle()
        after = dict(h.posture_rects())
        self.assertEqual(after["sitting"].center(), before["sitting"].center())
        self.assertAlmostEqual(after["sitting"].width(), before["sitting"].width() * HOVER_SCALE)
        self.assertGreater(after["standing"].center().x(), before["standing"].center().x())
        self.assertLess(after["lying"].center().x(), before["lying"].center().x())
        self.assertEqual(after["standing"].width(), before["standing"].width())
        self.assertEqual(after["lying"].width(), before["lying"].width())
        hits = dict(h.posture_hit_rects())
        self.assertAlmostEqual(hits["standing"].right(), hits["sitting"].left())
        self.assertAlmostEqual(hits["sitting"].right(), hits["lying"].left())
        for pid, rect in after.items():
            self.assertTrue(hits[pid].contains(rect))
            self.assertEqual(h.posture_at(rect.center()), pid)

    def test_retarget_preserves_current_centres_and_leaving_returns_to_the_original_layout(self):
        from PySide6.QtCore import QPointF
        h = self.hover
        initial = h._rects()
        h.mouse_move(initial["standing"].center())
        self.settle()
        previous = h._rects()
        h.mouse_move(previous["lying"].center())
        h._tick_motion(0.0)
        for pid, rect in h._rects().items():
            self.assertAlmostEqual(rect.center().x(), previous[pid].center().x())
        self.settle()
        self.assertEqual(dict(h.posture_rects())["lying"].center(), previous["lying"].center())
        # 重复的鼠标位置不会因为邻居让位重新挑目标。
        for _ in range(10):
            h.mouse_move(previous["lying"].center())
            h._tick_motion(1 / 60)
            self.assertEqual(h.hot_posture, "lying")
        h.mouse_move(QPointF(0.0, 160.0))
        self.settle()
        for pid, rect in h._rects().items():
            self.assertAlmostEqual(rect.center().x(), initial[pid].center().x())
            self.assertAlmostEqual(rect.width(), initial[pid].width())

    def test_press_stays_on_original_target_and_shrinking_does_not_cancel_a_stationary_click(self):
        from PySide6.QtCore import QPointF
        from widget.hovermenu import PRESS_SCALE
        h = self.hover
        base_width = dict(h.posture_rects())["sitting"].width()
        h.mouse_move(dict(h.posture_rects())["sitting"].center())
        self.settle()
        hit = dict(h.posture_hit_rects())["sitting"]
        point = QPointF(hit.center().x(), hit.top() + 0.1)
        h.begin_press("sitting", point)
        self.settle()
        self.assertAlmostEqual(dict(h.posture_rects())["sitting"].width(), base_width * PRESS_SCALE)
        self.assertEqual(h.end_press(point), "sitting", "按钮缩小不取消原先边缘上的按下")
        centre = dict(h.posture_rects())["sitting"].center()
        h.begin_press("sitting", centre)
        other = dict(h.posture_rects())["sleeping"].center()
        h.mouse_move(other)
        self.settle()
        self.assertEqual(h.post_press, "sitting")
        self.assertIsNone(h.end_press(other), "移到另一颗按钮松开不能触发另一颗")
        h.begin_press("sitting", centre)
        self.window.dynamic = True
        self.assertIsNone(h.end_press(centre), "模式切换让按钮消失时取消旧的按下")

    def test_opening_direction_stays_fixed_and_maximum_scale_fits_before_hover(self):
        from PySide6.QtCore import QRect
        from types import SimpleNamespace
        from widget.hovermenu import EDGE, needed_width
        h = self.hover
        self.window.scale = 0.3
        self.window.ppm = 30.0
        width = needed_width(self.window.scale)
        self.window.width = lambda: width
        self.window.scene_x = width / 2
        self.window.screen = lambda: SimpleNamespace(availableGeometry=lambda: QRect(0, 0, width, 300))
        h.top_m = h.x_m = None
        h.track(0.0)
        h._on_right = h._choose_direction()
        direction = h._on_right
        for pid in [key for key, _ in h.posture_rects()]:
            h.mouse_move(dict(h.posture_rects())[pid].center())
            self.settle()
            self.assertEqual(h._on_right, direction)
            for rect in h._rects().values():
                self.assertGreaterEqual(rect.left(), EDGE - 1e-6)
                self.assertLessEqual(rect.right(), width - EDGE + 1e-6)
        self.assertEqual(self.window.width(), width)

    def test_reduced_motion_preserves_hover_colour_without_scaling_or_neighbour_movement(self):
        from widget import hovermenu
        h = self.hover
        initial = h._rects()
        h.mouse_move(initial["sitting"].center())
        with mock.patch.object(hovermenu.native, "reduce_motion", return_value=True):
            self.settle()
            self.assertEqual(h._rects(), initial)
            with mock.patch.object(hovermenu.overlay, "draw_posture_strip") as strip, \
                 mock.patch.object(hovermenu.overlay, "draw_menu_button"), \
                 mock.patch.object(hovermenu.overlay, "draw_close_button"):
                h.draw(None)
            self.assertTrue(next(item for item in strip.call_args.args[1] if item[1] == "Sit")[3])
            h.begin_press("sitting", initial["sitting"].center())
            self.settle()
            self.assertEqual(h._rects(), initial)

    def test_motion_bounds_and_hit_areas_for_both_languages_directions_and_all_scales(self):
        from PySide6.QtCore import QPointF, QRect
        from types import SimpleNamespace
        from widget import i18n
        from widget.hovermenu import EDGE, HoverMenu, needed_width
        self.addCleanup(i18n.set_language, "en")
        for language in ("en", "zh"):
            i18n.set_language(language)
            for scale in (0.3, 0.8, 1.0, 1.15, 1.6, 4.0):
                width = max(round(config.WINDOW_WIDTH * scale), needed_width(scale))
                self.window.scale = scale
                self.window.ppm = config.PIXELS_PER_METER * scale
                self.window.scene_x = width / 2
                self.window.width = lambda _width=width: _width
                self.window.screen = lambda _width=width: SimpleNamespace(availableGeometry=lambda: QRect(0, 0, _width, 900))
                for direction in (False, True):
                    self.hover = h = HoverMenu(self.window)
                    h.track(0.0)
                    h.alpha = h.post_open = 1.0
                    h._on_right = direction
                    for pid in [key for key, _ in h.posture_rects()]:
                        for side in (-1.0, 1.0):
                            content = h._layout()[1][pid]
                            h.mouse_move(content.center() + QPointF(side * content.width() * 0.45, side * content.height() * 0.3))
                            self.settle()
                            rects = h._rects()
                            context = f"{language} {scale} {direction} {pid} pointer={side}"
                            for rect in rects.values():
                                self.assertGreaterEqual(rect.left(), EDGE - 1e-6, context)
                                self.assertLessEqual(rect.right(), width - EDGE + 1e-6, context)
                            self.assertEqual(h.posture_at(rects[pid].center()), pid, context)
                            ordered = list(rects.values())
                            self.assertTrue(all(a.right() < b.left() for a, b in zip(ordered, ordered[1:])), context)

    def test_whole_button_tracks_pointer_and_pressed_direction_stays_fixed(self):
        from PySide6.QtCore import QPointF
        from widget.hovermenu import DIRECTION_SHIFT
        h = self.hover
        original = h._layout()[1]["sitting"]
        left = original.center() + QPointF(-original.width() * 0.45, -original.height() * 0.3)
        right = original.center() + QPointF(original.width() * 0.45, original.height() * 0.3)
        for point, sign in ((left, -1), (right, 1)):
            h.mouse_move(point)
            self.settle()
            background, content = h._layout()
            delta = background["sitting"].center() - content["sitting"].center()
            self.assertGreater(delta.x() * sign, 1.0)
            self.assertLessEqual(abs(delta.x()), DIRECTION_SHIFT)
            self.assertAlmostEqual(h.control_scale("sitting"), 0.975)
        h.begin_press("sitting", left)
        h.mouse_move(right)
        self.settle()
        background, content = h._layout()
        self.assertLess(background["sitting"].center().x(), content["sitting"].center().x(),
                        "按下锁定左侧方向，按着移动到右侧不改方向")
        self.assertAlmostEqual(h.control_scale("sitting"), 0.975, msg="按下不再额外大幅缩小")

    def test_press_background_fades_for_120ms_and_quick_release_reverses_from_current_colour(self):
        from widget import overlay, sticker
        from widget.hovermenu import DOTS
        h = self.hover
        point = h.rect().center()
        h.mouse_move(point)
        self.settle()
        rest, _ = overlay.control_colors(False, True, h.press_tint(DOTS))
        h.begin_press(DOTS, point)
        self.assertEqual(overlay.control_colors(False, True, h.press_tint(DOTS))[0], rest)
        samples = []
        for _ in range(12):
            h._tick_motion(0.01)
            samples.append(h.press_tint(DOTS))
        self.assertGreater(samples[0], 0.0)
        self.assertLess(samples[0], 0.05, "第一帧渐入，不能瞬间变成反色")
        self.assertTrue(all(a < b for a, b in zip(samples, samples[1:])))
        self.assertAlmostEqual(samples[-1], 1.0)
        self.assertEqual(overlay.control_colors(False, True, samples[-1])[0].name(), sticker.INK.lower())
        h.end_press(point)
        self.settle()
        h.begin_press(DOTS, point)
        h._tick_motion(0.04)
        halfway = h.press_tint(DOTS)
        h.end_press(point)
        h._tick_motion(0.0)
        self.assertEqual(h.press_tint(DOTS), halfway, "提前松手不强行闪到最深色")
        h._tick_motion(0.01)
        self.assertGreater(h.press_tint(DOTS), 0.0)
        self.assertLess(h.press_tint(DOTS), halfway)

    def test_background_border_text_and_dots_share_one_transform_in_both_themes(self):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QImage, QPainter, QTransform
        from widget import sticker, i18n
        h = self.hover
        old_dark = sticker.is_dark()
        self.addCleanup(sticker.set_dark, old_dark)
        self.addCleanup(i18n.set_language, "en")

        class RecordedPainter(QPainter):
            def __init__(self, image):
                super().__init__(image)
                self.texts = []
                self.plates = []
                self.dots = []

            def drawRoundedRect(self, rect, *args):
                self.plates.append((QTransform(self.worldTransform()), self.worldTransform().mapRect(rect)))
                super().drawRoundedRect(rect, *args)

            def drawText(self, point, text):
                self.texts.append((text, QTransform(self.worldTransform()), self.pen().color(), self.brush().color(), self.opacity()))
                super().drawText(point, text)

            def drawEllipse(self, *args):
                self.dots.append(QTransform(self.worldTransform()))
                super().drawEllipse(*args)

        def render():
            canvas = QImage(760, 180, QImage.Format_ARGB32_Premultiplied)
            canvas.fill(0)
            painter = RecordedPainter(canvas)
            h.draw(painter)
            painter.end()
            self.assertEqual(len(painter.texts), 4, "每颗按钮只绘制一层文字，没有整图交叉淡入")
            self.assertEqual(len(painter.plates), 6, "每颗按钮只绘制一个底板：四个姿势、关闭键、「···」")
            for text, plate in zip(painter.texts, painter.plates):
                self.assertEqual(text[1], plate[0], "文字、描边与底板共用完全相同的 painter 变换")
                self.assertEqual(text[2], sticker.contrast_color(text[3]))
                self.assertEqual(text[4], 1.0)
            self.assertEqual(len(painter.dots), 3)
            self.assertTrue(all(transform == painter.plates[-1][0] for transform in painter.dots), "三个点跟底板同幅缩放 / 偏移")
            return painter.plates[1]

        for dark in (False, True):
            sticker.set_dark(dark)
            for language in ("en", "zh"):
                i18n.set_language(language)
                h.mouse_move(QPointF(0.0, 160.0))
                self.settle()
                normal = render()
                content = h._layout()[1]["sitting"]
                point = content.center() + QPointF(-content.width() * 0.4, -content.height() * 0.3)
                h.mouse_move(point)
                self.settle()
                hovered = render()
                self.assertAlmostEqual(hovered[0].m11(), 0.975)
                self.assertLess(hovered[1].center().x(), normal[1].center().x())
                self.assertLess(hovered[1].center().y(), normal[1].center().y())
                self.assertEqual(hovered[1], dict(h.posture_rects())["sitting"], "实际绘制与命中使用同一个最终矩形")
                h.begin_press("sitting", point)
                for _ in range(12):
                    h._tick_motion(0.01)
                    current = render()
                    self.assertAlmostEqual(current[0].m11(), 0.975, msg="按下仍是相同轻缩比例")
                h.end_press(point)
                self.settle()

    def test_selectable_press_previews_final_colour_and_commit_never_inverts_twice(self):
        from widget import overlay, sticker
        h = self.hover
        old_dark = sticker.is_dark()
        self.addCleanup(sticker.set_dark, old_dark)
        for dark in (False, True):
            sticker.set_dark(dark)
            self.window.rest_posture = "standing"
            self.settle()
            point = dict(h.posture_rects())["sitting"].center()
            h.mouse_move(point)
            self.settle()

            def colour(pid):
                self.assertEqual(h.press_tint(pid), 0.0, "可选项不叠加瞬时反色")
                return overlay.control_colors(h.selected_tint(pid), h.hover_tint(pid), h.press_tint(pid))[0]

            samples = [colour("sitting")]
            h.begin_press("sitting", point)
            for _ in range(6):
                h._tick_motion(0.01)
                samples.append(colour("sitting"))
            at_release = samples[-1]
            self.assertEqual(h.end_press(point), "sitting")
            self.window.rest_posture = "sitting"    # 同一个 release 事件中的实际选择
            h._tick_motion(0.0)
            self.assertEqual(colour("sitting"), at_release)
            for _ in range(18):
                h._tick_motion(0.01)
                samples.append(colour("sitting"))
            for channel in range(3):
                values = [colour.getRgbF()[channel] for colour in samples]
                sign = 1.0 if values[-1] >= values[0] else -1.0
                self.assertTrue(all((b - a) * sign >= -1e-6 for a, b in zip(values, values[1:])),
                                "按下到松开保持单向接近最终选中色，没有白黑白黑")
            self.assertEqual(samples[-1].name(), sticker.INK.lower())
            h.begin_press("sitting", point)
            for _ in range(15):
                h._tick_motion(0.01)
                self.assertEqual(colour("sitting"), samples[-1], "已选中再按不反回去")
            h.end_press(point)
            self.settle()
            self.assertEqual(colour("sitting"), samples[-1])

    def test_a_toolbar_that_does_not_fit_wraps_into_rows_below_that_do_not_overlap(self):
        """道具栏一行放不下就往下排，最多 4 颗（加最右边的「自定义」）；行和行、颗和颗的可点范围不重叠，下面几行不抢「···」底下的关闭键。"""
        from widget import hovermenu
        w = self.window
        w.dynamic = True
        w.tool_entries = lambda: [("a/1", "Blue bed"), ("b/1", "Food bowl"), ("c/1", "Water bowl"), ("ball/red", "Ball")]
        w.width = lambda: 520                                      # 「···」右边只放得下一两颗
        h = self.hover
        h._on_right = True
        self.settle()
        rects = dict(h.posture_rects())
        self.assertEqual(len(rects), 5)
        self.assertEqual(list(rects)[-1], hovermenu.CUSTOM, "「自定义」排在最后")
        rows = sorted({round(r.top(), 3) for r in rects.values()})
        self.assertGreater(len(rows), 1, "放不下：往下排了")
        dots = h.rect()
        k = h.k()
        for top in rows:
            row = sorted((r for r in rects.values() if round(r.top(), 3) == top), key=lambda r: r.left())
            self.assertGreaterEqual(row[0].left(), dots.right(), "每一行都从「···」右边起")
            self.assertLessEqual(row[-1].right(), w.width() - hovermenu.EDGE + 0.5, "不出窗口")
        self.assertAlmostEqual(rows[1] - rows[0], (hovermenu.MENU_H + hovermenu.POST_GAP) * k, delta=0.5, msg="下一行隔一个按钮高加一道缝")
        hits = [r for _, r in h.posture_hit_rects()]
        for i, a in enumerate(hits):
            for b in hits[i + 1:]:
                self.assertFalse(a.intersects(b), "可点范围不重叠")
        from PySide6.QtCore import QPointF
        for pid, r in h.posture_hit_rects():
            if round(rects[pid].top(), 3) != rows[0]:
                for y in (r.top() + 0.5, r.center().y(), r.bottom() - 0.5):
                    self.assertFalse(h.close_at(QPointF(r.left() + 0.5, y).toPoint()), "关闭键不抢下面几行的道具")
        self.assertTrue(h.close_at(h.close_rect().center().toPoint()), "关闭键自己照样点得到")

    def test_selection_initialisation_mode_changes_and_rapid_retarget_use_current_colour(self):
        from widget import overlay
        h = self.hover
        self.window.rest_posture = "lying"
        self.assertEqual(h.selected_tint("lying"), 1.0)
        h._tick_motion(0.0)
        self.assertEqual(h.selected_tint("lying"), 1.0, "初始化直接是实际选中状态")
        point = dict(h.posture_rects())["sitting"].center()
        h.begin_press("sitting", point)
        h._tick_motion(0.04)
        partial = h.selected_tint("sitting")
        self.assertGreater(partial, 0.0)
        self.assertLess(partial, 1.0)
        h.end_press(point)
        self.window.rest_posture = "sitting"
        h._tick_motion(0.0)
        self.assertEqual(h.selected_tint("sitting"), partial)
        other = dict(h.posture_rects())["standing"].center()
        before = {pid: overlay.control_colors(h.selected_tint(pid), h.hover_tint(pid), 0.0)[0]
                  for pid, _ in h.posture_rects()}
        h.begin_press("standing", other)
        h._tick_motion(0.0)
        after = {pid: overlay.control_colors(h.selected_tint(pid), h.hover_tint(pid), 0.0)[0]
                 for pid, _ in h.posture_rects()}
        self.assertEqual(after, before, "快速换目标从当前画面衔接")
        self.window.dynamic, self.window.rest_posture = True, "lying"
        self.assertEqual(h.selected_tint("lying"), 1.0, "模式切换不先露出旧状态")
        self.assertEqual(h.selected_tint("sitting"), 0.0)
        h._tick_motion(0.0)
        self.assertIsNone(h.post_press, "模式切换取消旧按下预览")
        self.window.dynamic = False
        h._tick_motion(0.0)
        self.assertEqual(h.selected_tint("lying"), 1.0)
        self.assertEqual(h.selected_tint("standing"), 0.0)
