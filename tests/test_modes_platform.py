"""两个模式开关、没有鼠标穿透、全屏可见、Dock 点击、菜单栏骨头、屏幕正中的 HUD、Cmd+Q：offscreen 平台，平台相关的只验证不出错。不碰真 QSettings。"""
import math
import os
import sys
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import config
from tests.panel_base import QUIET, FakeSettings, PanelCase

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ModesAndPlatformTests(PanelCase):
    def test_defaults_follow_config(self):
        from widget.prefs import DEFAULTS
        self.assertFalse(self.win.follow_cursor, "鼠标跟随默认关")
        self.assertTrue(DEFAULTS["dynamic"], "灵动交互默认开")
        self.assertTrue(self.win.dog.play)
        self.assertFalse(self.win.show_metadata)
        self.assertEqual(self.win.coat, 1)

    def test_there_is_no_click_through(self):
        """删了鼠标穿透（没人会用，开了反而挪不动小组件）。它从来不跨启动保存，没有旧设置要迁移：高级设置里没有这一行、
        窗口没有这个开关、狗的窗口从不整个不接鼠标（点击范围就是狗：native.set_ignores_mouse 每帧按鼠标底下是不是狗切，留着）。"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        from widget import i18n
        from widget.prefs import DEFAULTS
        self.win.show()
        self.settings.show()
        self.settings.show_advanced(True, animated=False)
        self.assertFalse(hasattr(self.settings, "through"), "高级设置里没有鼠标穿透的开关")
        texts = [label.text() for label in self.settings.findChildren(QLabel)]
        self.assertFalse([t for t in texts if "Click-through" in t or "穿透" in t], "也没有它那一行字")
        self.assertFalse(hasattr(self.win, "set_click_through") or hasattr(self.win, "click_through"))
        self.assertFalse(self.win.windowFlags() & Qt.WindowTransparentForInput, "狗的窗口不整个穿透")
        self.assertEqual([k for k in DEFAULTS if "click" in k or "through" in k], [], "没有存下来的穿透设置")
        self.assertNotIn("Click-through", i18n.ZH)

    def test_follow_and_dynamic_combine_and_each_does_its_own_thing(self):
        self.win.show()
        self.settings.show()
        self.win.set_dynamic(False)
        self.win.set_follow_cursor(True)
        self.settings.sync()
        self.assertTrue(self.win.dog.play)
        self.assertFalse(self.win.dog.dynamic)
        self.assertIsNotNone(self.win._look_target(1 / 60) if self.win.dog.head_position() else (0,), "鼠标跟随开着就有目标")
        self.win.set_follow_cursor(False)
        self.assertTrue(self.win.dog.play, "两个都关：狗自己待着")
        self.assertIsNone(self.win._look_target(1 / 60))
        self.settings.dynamic.click()
        self.assertTrue(self.win.dynamic)
        self.assertIsNotNone(self.win._look_target(1 / 60) if self.win.dog.head_position() else (0,),
                             "只开灵动交互：也看鼠标（灵动交互里头跟着鼠标，鼠标跟随那一行藏起来）")
        self.assertTrue(self.win.dog.dynamic)
        self.settings.follow.click()
        self.assertTrue(self.win.follow_cursor)
        self.assertTrue(self.win.dynamic, "鼠标跟随和灵动交互可以同时开")
        self.assertTrue(self.settings.dynamic.isChecked())
        self.assertEqual((self.win.settings.values["follow_cursor"], self.win.settings.values["dynamic"]), (True, True))
        self.assertIn(self.win.dog.home_yaw, (210.0, 330.0))
        self.settings.dynamic.click()
        self.assertFalse(self.win.dynamic)
        self.assertTrue(self.win.follow_cursor, "关灵动交互不动鼠标跟随")
        self.assertNotIn("live", self.win.settings.values)
        self.assertNotIn("demo", self.win.settings.values)

    def test_settings_live_in_deskmates_own_store(self):
        """设置记在这个 app 自己那份（~/Library/Preferences/com.deskmate.Companion.plist），
        不碰别的 app 的设置。"""
        import widget.window as window
        made = []
        def settings(*args):
            made.append(args)
            return FakeSettings()
        with mock.patch.object(window, "QSettings", settings):
            w = window.CompanionWindow(self.model)
        w._anim_timer.stop()
        w.hide()
        self.assertEqual(made, [("Deskmate", "Companion")])

    def test_menus_have_no_remote_or_phone_entries(self):
        self.assertFalse(hasattr(self.settings, "live"))
        self.assertFalse(hasattr(self.settings, "demo"))

    def test_accessory_rules_without_the_global_display_switch(self):
        import types
        from widget import native
        self.assertFalse(native.set_all_spaces(self.win, True), "offscreen 平台不碰 NSWindow")
        self.assertIsNone(native.collection_behavior(self.win))
        self.assertFalse(native.pin_contents_to_bottom(self.win), "offscreen 平台不碰 layer")
        self.assertIsNone(native.contents_gravity(self.win))
        self.assertFalse(native.set_activation_policy(True), "offscreen 平台不碰 NSApp")
        self.assertIsNone(native.activation_policy())
        self.win.show()                                   # showEvent 里也调它，不能炸
        self.settings.show()
        self.assertFalse(hasattr(self.settings, "global_visible"), "没有「小组件全局显示」这个开关：一直开着")
        self.assertFalse(hasattr(self.win, "set_global_visible"))
        self.win.settings.values["global_visible"] = False     # 以前关着的人：存着的那个设置不再读
        self.win.tray = types.SimpleNamespace(isVisible=lambda: False, rebuild=lambda: None)
        self.assertFalse(self.win.wants_accessory(), "菜单栏骨头不在就不切 accessory（留 Dock 图标当退路）")
        self.win.tray = types.SimpleNamespace(isVisible=lambda: True, rebuild=lambda: None)
        self.assertTrue(self.win.wants_accessory(), "骨头在就切：全屏 App 上也有狗、程序坞里没有图标")
        self.win.tray = None

    def test_global_mouse_state_is_readable_on_mac(self):
        import sys
        from widget import native
        down = native.mouse_left_down()
        if sys.platform == "darwin":
            self.assertIn(down, (True, False))
        else:
            self.assertIsNone(down)

    def test_dock_click_only_restores_the_identity(self):
        """点 Dock 图标：当场校验身份（见下面几个策略的测试），不弹设置。"""
        self.win.show()
        self.settings.hide()
        self.win.on_dock_reopen()
        self.assertFalse(self.settings.isVisible(), "点 Dock 不弹设置")
        self.assertFalse(hasattr(self.win, "fade_out_and_hide"), "没有隐藏：狗一直在桌面上")

    @contextmanager
    def _fake_activation_policy(self, initial, *, tray_visible=True):
        """模拟 Dock 把运行中的辅助应用提升成普通应用；不碰真正的 NSApplication。"""
        from widget import native
        state = {"policy": initial, "succeeds": True}
        self.win.tray = SimpleNamespace(isVisible=lambda: tray_visible, rebuild=lambda: None)

        def set_policy(accessory):
            if state["succeeds"]:
                state["policy"] = native.POLICY_ACCESSORY if accessory else native.POLICY_REGULAR
            return state["succeeds"]

        with mock.patch.object(native, "activation_policy", side_effect=lambda: state["policy"]), \
             mock.patch.object(native, "set_activation_policy", side_effect=set_policy) as setter:
            yield state, setter

    def test_pinned_dock_reopen_restores_policy_after_the_system_finishes_activating(self):
        """固定在 Dock 的图标仍能唤起 accessory；系统晚到的策略变化也要恢复，不能只在启动时设置。"""
        from PySide6.QtCore import Qt
        from widget import native
        with self._fake_activation_policy(native.POLICY_REGULAR) as (state, setter):
            self.win.on_app_state(Qt.ApplicationInactive)
            self.win.on_app_state(Qt.ApplicationActive)
            self.win.on_app_state(Qt.ApplicationActive)     # Dock 的 reopen 通知
            self.assertEqual(state["policy"], native.POLICY_ACCESSORY, "重新打开时立即修复")
            state["policy"] = native.POLICY_REGULAR         # 当前系统事件处理完才落下来的覆盖
            self.app.processEvents()
            self.assertEqual(state["policy"], native.POLICY_ACCESSORY, "下一轮事件再校验，覆盖不能残留")
            self.assertFalse(self.settings.isVisible(), "点 Dock 只恢复身份，不打开设置")
            repaired = setter.call_count
            self.win.on_app_state(Qt.ApplicationActive)
            self.app.processEvents()
            self.assertEqual(setter.call_count, repaired, "身份已经正确就不反复设置，避免激活 / 跳桌面")

    def test_normal_activation_repairs_policy_after_the_event_loop_turn(self):
        from PySide6.QtCore import Qt
        from widget import native
        reopens = []
        self.win.on_dock_reopen = lambda: reopens.append(1)
        with self._fake_activation_policy(native.POLICY_REGULAR) as (state, setter):
            self.win.on_app_state(Qt.ApplicationInactive)
            self.win.on_app_state(Qt.ApplicationActive)     # 切桌面 / 点窗口，只有一次 Active
            self.assertEqual(state["policy"], native.POLICY_REGULAR, "当场不改：AppKit 激活以后会再改回去一次，要等这一轮过去")
            setter.assert_not_called()
            self.app.processEvents()
            self.assertEqual(state["policy"], native.POLICY_ACCESSORY, "普通激活也校验身份，等本轮事件处理完")
            self.assertEqual(reopens, [], "普通激活（只有一次 Active）不当成点 Dock")

    def test_dock_policy_guard_preserves_regular_mode_without_the_tray(self):
        from widget import native
        with self._fake_activation_policy(native.POLICY_ACCESSORY, tray_visible=False) as (state, setter):
            self.win.on_dock_reopen()
            self.app.processEvents()
            self.assertEqual(state["policy"], native.POLICY_REGULAR, "菜单栏不可用时保留 Dock 入口")
            setter.assert_called_once_with(False)

    def test_menu_recovers_policy_before_creation_and_replaces_the_old_window_only_once(self):
        from widget import native
        import widget.window as window
        with self._fake_activation_policy(native.POLICY_ACCESSORY) as (state, setter):
            old = self.win._build_ball_menu()
            old.show()
            state["policy"] = native.POLICY_REGULAR
            created_as = []
            menu_class = window.SwitchMenu

            def new_menu(parent):
                created_as.append(state["policy"])
                return menu_class(parent)

            with mock.patch.object(window, "SwitchMenu", side_effect=new_menu):
                menu = self.win._build_ball_menu()
                self.assertIsNot(menu, old, "修复身份后重建菜单，不能沿用错误身份期间的原生窗口")
                self.assertFalse(old.isVisible(), "旧菜单先收起")
                self.assertEqual(created_as, [native.POLICY_ACCESSORY], "原生窗口必须在正确身份下创建")
                self.assertIs(self.win._build_ball_menu(), menu, "正常情况下仍重复使用同一个菜单")
                self.assertEqual(len(created_as), 1)
            setter.assert_called_once_with(True)

    def test_failed_policy_recovery_keeps_the_existing_menu(self):
        from widget import native
        with self._fake_activation_policy(native.POLICY_ACCESSORY) as (state, setter):
            menu = self.win._build_ball_menu()
            state.update(policy=native.POLICY_REGULAR, succeeds=False)
            with self.assertLogs("window", level="WARNING"):
                self.assertIs(self.win._build_ball_menu(), menu, "系统拒绝恢复时不能销毁菜单、反复重建")
            self.assertEqual(state["policy"], native.POLICY_REGULAR)
            setter.assert_called_once_with(True)

    def test_policy_recovery_checks_the_actual_result_before_discarding_a_menu(self):
        from widget import native
        with self._fake_activation_policy(native.POLICY_ACCESSORY) as (state, setter):
            menu = self.win._build_ball_menu()
            state["policy"] = native.POLICY_REGULAR
            setter.side_effect = lambda accessory: True    # 系统说成功，实际身份却没变
            with self.assertLogs("window", level="WARNING"):
                self.assertFalse(self.win.apply_policy())
            self.assertIs(self.win._ball_menu, menu, "只有读回确认恢复成功后才能换菜单")

    def test_activation_sent_during_policy_recovery_is_not_a_dock_click(self):
        from PySide6.QtCore import Qt
        from widget import native
        reopens = []
        self.win.on_dock_reopen = lambda: reopens.append(1)
        self.win._app_state = Qt.ApplicationActive
        with self._fake_activation_policy(native.POLICY_REGULAR) as (state, setter):
            def activate_while_switching(accessory):
                self.win.on_app_state(Qt.ApplicationActive)
                state["policy"] = native.POLICY_ACCESSORY
                return True

            setter.side_effect = activate_while_switching
            self.assertTrue(self.win.apply_policy())
            self.app.processEvents()
            setter.assert_called_once_with(True)
            self.assertEqual(reopens, [], "策略切换自己发出的 Active 不能被误认为又点了 Dock")

    def test_opening_cards_never_activates_the_app(self):
        """在别的桌面点设置会连跳几个桌面、停在一个固定的桌面。程序一被激活，macOS 就切到程序有窗口的那个桌面；
        现在打开卡片、换到毛色页都不激活程序（点卡片时才激活，那时卡片就在眼前）；提示、HUD、菜单、取色面板也都放到所有桌面。"""
        from unittest import mock
        from PySide6.QtCore import Qt
        from widget import native
        self.assertTrue(self.settings.testAttribute(Qt.WA_ShowWithoutActivating), "显示时不激活")
        with mock.patch.object(type(self.settings), "activateWindow") as act:
            self.win.open_settings()
            self.win.open_coat()
        act.assert_not_called()
        self.assertFalse(native.color_panel_all_spaces(), "offscreen 平台不碰 NSColorPanel")

    def test_only_a_dock_click_counts_not_switching_spaces(self):
        from PySide6.QtCore import Qt
        reopens = []
        self.win.on_dock_reopen = lambda: reopens.append(1)
        self.win.on_app_state(Qt.ApplicationInactive)
        self.win.on_app_state(Qt.ApplicationActive)       # 切桌面 / ⌘Tab / 点自己的窗口：只有一次激活
        self.assertEqual(reopens, [], "普通激活不算点 Dock（不然一切桌面设置就自己出来）")
        self.win.on_app_state(Qt.ApplicationActive)       # 点 Dock 图标：系统紧接着再补一次
        self.assertEqual(reopens, [1], "已经激活又来一次，才是点了 Dock 图标")
        self.win.on_app_state(Qt.ApplicationActive)       # 程序在前台时再点 Dock：只补那一次
        self.assertEqual(reopens, [1, 1])
        self.win.on_app_state(Qt.ApplicationInactive)
        self.win.on_app_state(Qt.ApplicationActive)
        self.assertEqual(reopens, [1, 1], "切走再切回来还是普通激活")

    def test_hud_sits_in_the_middle_of_the_screen(self):
        """屏幕正中的贴纸 HUD（骨头 + 两行字，淡入 0.2 停 4 淡出 0.5 秒，不用点、点不到）：装新版本、卸载没成时用。"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from widget.i18n import tr
        from widget.widgets import sticker_hud
        hud = sticker_hud()
        text = tr("Drag to Applications to replace the old one") + "\n" + tr("then open the widget again")   # 和 window.install_update 一样
        hud.show_text(text)
        self.assertTrue(hud.isVisible())
        self.assertEqual(hud.text, text)
        self.assertTrue(hud.windowFlags() & Qt.WindowTransparentForInput, "点不到：鼠标穿过去")
        self.assertTrue(hud.testAttribute(Qt.WA_ShowWithoutActivating), "不抢焦点")
        self.assertEqual((hud.FADE_IN_MS, hud.HOLD_MS, hud.FADE_OUT_MS), (200, 4000, 500), "停 4 秒：2 秒来不及读完，5 秒又长了")
        self.assertEqual((hud.BONE_W, hud.GAP, hud.PAD_Y), (32, 12, 20), "小骨头、上下等边距（按笔画量：骨头笔画上边、字笔画下边到描边一样远）")
        r_top = hud.M + 1                                             # 描边里面
        ink_top = r_top + hud.PAD_Y
        ink_bottom = ink_top + hud._bone.height() + hud.GAP + (hud._ink[1] - hud._ink[0])
        self.assertAlmostEqual(hud.height() - hud.M - 1 - ink_bottom, hud.PAD_Y, delta=1.0, msg="字的笔画下边离描边也是 PAD_Y：重心不偏上")
        ag = QApplication.primaryScreen().availableGeometry()
        self.assertLessEqual(abs(hud.x() + hud.width() // 2 - ag.center().x()), 2, "横向居中")
        self.assertLessEqual(abs(hud.y() + hud.height() // 2 - (ag.center().y() - 20)), 2, "竖向居中偏上 20")
        hud.finish_now()
        self.assertFalse(hud.isVisible(), "走完就收起")

    def test_tray_builds_a_mask_icon_and_menu(self):
        from widget.tray import Tray, menu_icon
        self.assertTrue(menu_icon().isMask(), "骨头是模板图：macOS 按菜单栏深浅自动反色")
        tray = Tray(self.win, self.app)
        texts = [a.text() for a in tray.menu.actions() if a.text()]
        self.assertEqual(texts, ["Settings…", "Quit DeskMates"], "10/28 起没有 Hide dog；11/7 起没有动作控制；11/8 改名 Deskmate")
