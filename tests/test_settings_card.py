"""设置卡片、表盘、毛色页、贴纸风：offscreen 平台建出来、点一遍，确认改到窗口设置。不碰真 QSettings。"""
import gc
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


class SettingsCardTests(PanelCase):
    def test_switches_write_window_settings(self):
        self.settings.show()
        self.settings.follow.click()
        self.assertTrue(self.win.follow_cursor)
        self.assertEqual(self.win.settings.values["follow_cursor"], True)
        self.settings.meta.click()
        self.assertTrue(self.win.show_metadata)
        self.settings.follow.click()
        self.assertFalse(self.win.follow_cursor)

    def test_size_slider_keeps_fractional_scale_and_updates_the_label_immediately(self):
        """连续跟手拖动保留小数，整数百分比只是显示格式；松手不把实际大小取整。"""
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent, QWheelEvent
        self.win.set_scale(2.0025)
        self.settings.show()
        r = self.settings.size_slider
        self.assertAlmostEqual(r.value, 200.25)
        self.assertEqual(self.settings.size_label.text(), "200%")
        pos = QPointF(75, 15)
        r.wheelEvent(QWheelEvent(pos, QPointF(r.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
        self.assertAlmostEqual(r.value, 201.25, msg="滚轮一格1个百分点，已有小数保留")
        self.assertAlmostEqual(self.win.scale, 2.0125)
        self.assertEqual(self.settings.size_label.text(), "201%", "同一事件里刷新，不等定时sync")
        def mev(kind, x, buttons=Qt.LeftButton):
            p = QPointF(x, 15)
            return QMouseEvent(kind, p, QPointF(r.mapToGlobal(p.toPoint())), Qt.LeftButton, buttons, Qt.NoModifier)
        r.mousePressEvent(mev(QEvent.MouseButtonPress, 75))
        r.mouseMoveEvent(mev(QEvent.MouseMove, 75.375))
        value = r.value
        self.assertNotAlmostEqual(value, round(value))
        self.assertAlmostEqual(self.win.scale, value / 100.0)
        self.assertEqual(self.settings.size_label.text(), f"{round(value)}%", "拖动时狗、钮、百分比同步")
        r.mouseReleaseEvent(mev(QEvent.MouseButtonRelease, 75.375, Qt.NoButton))
        self.assertEqual(r.value, value, "松手不取整")
        self.assertAlmostEqual(self.win.scale, value / 100.0)
        self.win.set_scale(1.2375)
        self.settings.sync()
        self.assertAlmostEqual(r.value, 123.75, msg="从窗口同步也不抹掉精度")
        self.assertEqual(self.settings.size_label.text(), "124%")

    def test_percentage_edits_inline_and_syncs_the_main_row(self):
        self.settings.finish_animations()                         # 大小是全局的，在主页面
        from widget.sizecontrol import SizeScrubber
        self.win.set_scale(1.3725)
        self.settings.show()
        control = self.settings.size_label
        self.assertIsInstance(control, SizeScrubber)
        control.start_edit()
        self.assertTrue(control.editor.isVisible())
        self.assertEqual(control.editor.text(), "137")
        control.editor.setText("153.25")
        control.editor.setModified(True)
        control._commit_text()
        self.assertAlmostEqual(self.win.scale, 1.5325)
        self.assertAlmostEqual(self.settings.size_slider.value, 153.25)
        self.assertEqual(control.text(), "153%")
        self.assertFalse(self.win._scale_adjusting)
        self.assertFalse(control.editor.isVisible())

    def test_unchanged_integer_edit_keeps_the_full_precision(self):
        self.win.set_scale(1.3725)
        self.settings.show()
        control = self.settings.size_label
        control.start_edit()
        self.assertEqual(control.editor.text(), "137")
        control._commit_text()
        self.assertAlmostEqual(self.win.scale, 1.3725)
        self.assertAlmostEqual(control.value, 137.25)

    def test_settings_sync_preserves_the_selected_fine_adjustment_number(self):
        self.win.set_scale(1.3725)
        self.settings.show()
        control = self.settings.size_label
        control.start_edit()
        self.app.processEvents()
        self.assertEqual(control.editor.selectedText(), "137")
        self.settings.sync()
        self.assertEqual(control.editor.selectedText(), "137", "定时同步不能打断尚未输入第一字的选区")
        control.editor.setText("145")
        control.editor.setModified(True)
        self.settings.show_page("advanced", animated=False)
        self.assertFalse(control.editor.isVisible())
        self.assertAlmostEqual(self.win.scale, 1.3725, msg="换页取消未提交的输入")

    def test_percentage_display_rounds_half_up_without_changing_the_precise_scale(self):
        self.settings.show()
        control = self.settings.size_label
        for text, scale, label in (("125.5", 1.255, "126%"), ("126.5", 1.265, "127%"),
                                   ("125.499", 1.25499, "125%")):
            with self.subTest(text=text):
                control.start_edit()
                control.editor.setText(text)
                control.editor.setModified(True)
                control._commit_text()
                self.assertEqual(control.text(), label, "二进制浮点尾差不应把正好半数显示成向下取整")
                self.assertAlmostEqual(self.win.scale, scale, places=10)
                self.assertAlmostEqual(self.settings.size_slider.value, scale * 100, places=8)

    def test_coat_swatches_and_selection(self):
        self.settings.show()
        self.assertEqual(len(self.settings.swatches), len(config.COATS))
        self.assertTrue(self.settings.swatches[0].isEnabled())
        if self.win.coat_available()[1]:
            self.settings.swatches[1].click()
            self.assertEqual(self.win.coat, 2)
            self.assertEqual(self.win.settings.values["coat"], 2)
            self.assertIsNotNone(self.win.view.renderer.coat_image)
        self.settings.swatches[0].click()
        self.assertEqual(self.win.coat, 1)
        self.assertIsNone(self.win.view.renderer.coat_image)

    def test_custom_coat_page_recolors_persists_and_relaunches(self):
        """自定义毛色是设置卡片的第三页：高级设置的两色圆点进去，‹ 回高级设置；狗本身就是预览。"""
        import widget.window as window
        self.settings.show()
        self.settings.show_advanced(True, animated=False)
        self.settings.custom_swatch.click()                      # Custom 色块：换到自定义毛色页，狗立刻换成自定义贴图
        self.assertEqual(self.win.coat, 0)
        self.assertEqual(self.win.settings.values["coat"], 0)
        self.assertEqual(self.settings.page, "coat")
        self.assertTrue(self.settings.coat_page.isVisibleTo(self.settings))
        self.assertFalse(self.settings.advanced_page.isVisibleTo(self.settings))
        self.assertEqual(self.settings._title_label.text(), "Custom color")
        self.assertTrue(self.settings.back.isVisibleTo(self.settings))
        self.assertIsNotNone(self.win.view.renderer.coat_image)
        self.settings.sync()
        self.assertTrue(self.settings.custom_swatch.isChecked())
        panel = self.settings.coat_page
        panel.swap.click()
        panel.main.on_final("#FF0000")
        panel.flush()
        self.assertTrue(self.win.coat_spec.swap)
        self.assertEqual(self.win.coat_spec.main, "#FF0000")
        self.assertIn('"swap": true', self.win.settings.values["coat_custom"])
        saved = self.win.settings
        with mock.patch.object(window, "QSettings", lambda *a: saved):
            again = window.CompanionWindow(self.model)
        self.assertEqual(again.coat, 0, "重启后还是自定义")
        self.assertEqual(again.coat_spec.main, "#FF0000")
        self.assertIsNotNone(again.view.renderer.coat_image)
        self.assertFalse(panel.eyes_reset.isVisibleTo(panel), "没改过眼睛颜色时没有「默认」按钮")
        panel.eyes.on_final("#3B7BD6")
        self.assertTrue(panel.eyes_reset.isVisibleTo(panel), "选了眼睛颜色才出现「默认」")
        self.assertEqual(panel.eyes_reset.text(), "Default")
        panel._reset()
        self.assertEqual(self.win.coat_spec.main, "#2A2A2E")
        self.assertFalse(self.win.coat_spec.swap)
        self.settings.back.click()                               # ‹ 回这只同桌的详情页（毛色在那一页），不是主页面
        self.assertEqual(self.settings.page, "pet")
        self.settings.back.click()                               # 顶部栏左边同一个圆：详情页回主页面
        self.assertEqual(self.settings.page, "main")
        self.settings.swatches[0].click()                        # 回原装
        self.assertEqual(self.win.coat, 1)
        self.assertIsNone(self.win.view.renderer.coat_image)
        self.assertEqual(self.win.settings.values["coat_custom"], self.win.coat_spec.to_json(), "自定义参数留着，下次再开还在")

    def test_rename_by_clicking_the_title_tag(self):
        """没有名字行了，标题胶囊就是名字。打开时焦点不在任何输入框；点胶囊变输入框，回车生效，Esc 取消。
        改名只在详情页——主页面点顶上的名字是进详情页（和点正中那只一样），别的页标题是页名，点了都不改名。"""
        from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
        from PySide6.QtGui import QKeyEvent, QMouseEvent
        from PySide6.QtWidgets import QApplication, QLineEdit
        from widget.card import sticker_tip
        self.win.open_settings()
        s, bar = self.settings, self.settings._tag

        def click(release: bool = True) -> None:
            pos = bar.tag_rect().center()                              # 标题行自己画，点的是名字胶囊本身
            g = QPointF(bar.mapToGlobal(pos.toPoint()))
            QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseButtonPress, pos, g, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
            if release:
                QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseButtonRelease, pos, g, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        self.assertFalse(any(e.isVisibleTo(s) for e in s.main_page.findChildren(QLineEdit)), "主页面没有输入框")
        self.assertFalse(s.renaming)
        self.assertFalse(hasattr(s, "_pencil"), "没有铅笔")
        self.assertEqual(s._tips[bar], "Click to rename")
        s._tip_target = bar
        s._show_tip(force=True)
        self.assertFalse(sticker_tip().isVisible(), "主页面点名字不改名：不浮「点击改名」")
        click()
        self.assertEqual(s.page, "pet", "主页面点名字：进详情页")
        self.assertFalse(s.renaming)
        s.finish_page_anim()
        click(release=False)
        self.assertTrue(s.renaming, "详情页点胶囊就地改名（按下就开）")
        s._tip_target = bar
        s._show_tip(force=True)
        self.assertFalse(sticker_tip().isVisible(), "输入框开着时不浮「点击改名」")
        self.assertIsNone(s._drag, "这一下不算拖卡片")
        self.assertEqual(s._title_edit.text(), "Milo")
        s._title_edit.setText("Bobo")
        s._title_edit.editingFinished.emit()
        self.assertFalse(s.renaming)
        self.assertEqual(self.win.dog_name, "Bobo")
        self.assertEqual(s._title_label.text(), "Bobo", "胶囊上的字跟着换")
        s.start_rename()
        s._title_edit.setText("Nope")
        QApplication.sendEvent(s._title_edit, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        self.assertFalse(s.renaming)
        self.assertEqual(self.win.dog_name, "Bobo", "Esc 不改")
        s.finish_page_anim()
        s._tip_target = bar
        s._show_tip(force=True)
        tip = sticker_tip()
        self.assertTrue(tip.isVisible() and tip.text == "Click to rename", "详情页上停在名字上：浮「点击改名」")
        r = bar.tag_rect()
        spot = QRect(bar.mapToGlobal(QPoint(math.floor(r.left()), math.floor(r.top()))), QSize(math.ceil(r.width()), math.ceil(r.height())))
        self.assertGreater(spot.left(), bar.mapToGlobal(QPoint(0, 0)).x() + 26, "胶囊居中，不在这一条的左头")
        if tip._placed == "below":
            self.assertEqual((tip.x() + tip.M, tip.y() + tip.M), (spot.left(), spot.top() + spot.height() + tip.GAP_BELOW),
                             "在名字胶囊下面，尾巴指着它的开头（不是这一条的左头、不是左边的圆）")
        else:
            self.assertGreaterEqual(tip.x() + tip.M, spot.left() + spot.width(), "在名字胶囊右边")
            self.assertLessEqual(abs(tip.y() + tip.height() // 2 - (spot.top() + spot.height() // 2)), 2, "和胶囊上下对齐")
        s._hide_tip()
        s.show_advanced(True, animated=False)                         # 高级设置页的标题是"高级设置"，不是名字
        self.assertEqual(s._title_label.text(), "Advanced")
        click()
        self.assertFalse(s.renaming, "高级设置页点标题不改名")
        self.assertEqual(s.page, "advanced", "也不去别处")
        s._tip_target = bar
        s._show_tip(force=True)
        self.assertFalse(sticker_tip().isVisible(), "也不浮「点击改名」")
        s.show_page("pet", animated=False)
        s.start_rename()
        self.assertTrue(s.renaming, "回到详情页又能改")
        s._end_rename()

    def test_main_page_order_and_advanced_page_contents(self):
        """主页面（两个模式 / 动作 / 大小 / 高级设置… + 退出）；语言、省电模式在高级设置页；元数据在开发者设置页。
        毛色、删除在这只同桌的详情页（点正中那只进），高级设置里不再有「同桌」那一行。
        大小（全局的一个）在主页面、鼠标跟随下面；声音是两条音量，在高级设置、外观下面。"""
        from PySide6.QtCore import QPoint
        s = self.settings
        s.show()
        self.app.processEvents()
        self.assertTrue(s.size_slider.isVisibleTo(s), "大小在主页面")
        ys = [w.mapTo(s, w.rect().center()).y() for w in (s.dynamic, s.actions_toggle, s.follow, s.size_label, s.size_slider)]
        self.assertEqual(ys, sorted(ys), "灵动交互、动作（紧跟着管它的灵动交互）、鼠标跟随、大小（上面一行字和数字，下面整行宽的滑杆）")
        self.assertEqual(s.size_slider.width(), 280, "滑杆整行宽")
        self.assertGreater(s.quit_button.mapTo(s, s.quit_button.rect().center()).y(), s.size_slider.mapTo(s, s.size_slider.rect().center()).y())
        self.assertEqual(s.quit_button.mapTo(s, s.quit_button.rect().center()).y(), s.advanced_link.mapTo(s, s.advanced_link.rect().center()).y())
        for w, name in ((s.custom_swatch, "毛色"), (s.meta, "元数据"), (s.media_volume, "媒体音效"),
                        (s.interface_volume, "界面音效"), (s.lang_buttons["en"], "语言"), (s.power, "省电模式"), (s.pet_delete, "删除这只")):
            self.assertFalse(w.isVisibleTo(s), f"{name}不在主页面")
        self.assertFalse(hasattr(s, "restart_button"), "没有重启按钮了")
        self.assertFalse(hasattr(s, "pet_button"), "高级设置里没有「同桌」那一行了：换同桌在主页面，模型在添加时定")
        self.assertNotIn("pets", s.pages, "没有选同桌页了")
        s.show_advanced(True, animated=False)
        for w, name in ((s.power, "省电模式"), (s.lang_buttons["en"], "语言"), (s.media_volume, "媒体音效"),
                        (s.interface_volume, "界面音效")):
            self.assertTrue(w.isVisibleTo(s), f"{name}在高级设置页")
        self.assertFalse(s.custom_swatch.isVisibleTo(s), "毛色不在高级设置页")
        self.assertFalse(s.size_slider.isVisibleTo(s), "大小不在高级设置页了")
        ys = [w.mapTo(s, w.rect().center()).y() for w in (s.appearance_buttons["system"], s.media_volume, s.interface_volume, s.lang_buttons["en"])]
        self.assertEqual(ys, sorted(ys), "外观、媒体音效、界面音效、语言")
        self.assertEqual(s.media_volume.slider.mapTo(s, QPoint(0, 0)).x(), s.interface_volume.slider.mapTo(s, QPoint(0, 0)).x(), "两条滑块从同一个地方开始")
        self.assertFalse(hasattr(s, "global_visible"), "没有「小组件全局显示」，省电模式是第一行")
        self.assertLess(s.power.mapTo(s, s.power.rect().center()).y(), s.appearance_buttons["system"].mapTo(s, QPoint(0, 0)).y())
        self.assertFalse(self.win.power_saving, "省电模式默认关")
        s.power.click()
        self.assertTrue(self.win.power_saving)
        self.assertTrue(self.win.prefs.get("power_saving"))
        s.power.click()
        s.show_page("pet", False)
        for w, name in ((s.custom_swatch, "毛色"), (s.pet_delete, "删除")):
            self.assertTrue(w.isVisibleTo(s), f"{name}在详情页")
        self.assertFalse(s.size_slider.isVisibleTo(s), "大小不在详情页：不是这一只的，是全局的")
        self.assertLess(s.custom_swatch.mapTo(s, s.custom_swatch.rect().center()).y(), s.pet_delete.mapTo(s, s.pet_delete.rect().center()).y(), "毛色、删除")
        s.show_page("tuning", False)
        self.assertTrue(s.meta.isVisibleTo(s), "元数据在开发者设置页")

    def test_version_line_sits_at_the_bottom_of_advanced(self):
        """高级设置页最底下一行居中的灰字「版本 0.5.1 (7)」，macOS「关于」窗口的写法；数字从 config 读（打包脚本每次把构建号加一）。"""
        for lang, word in (("en", "Version"), ("zh", "版本")):
            self.win.set_language(lang)
            s = self.win.settings_panel
            s.show()
            s.show_advanced(True, animated=False)
            self.app.processEvents()
            v = s.version_label
            self.assertEqual(v.text(), f"{word} {config.VERSION} ({config.BUILD})")
            self.assertTrue(v.isVisibleTo(s))
            self.assertTrue(v.property("muted"), "灰字")
            self.assertGreater(v.mapTo(s, v.rect().center()).y(), s.custom_swatch.mapTo(s, s.custom_swatch.rect().center()).y(), "在毛色下面")
            s.show_advanced(False, animated=False)
            self.assertFalse(v.isVisibleTo(s), "主页面没有")

    def test_names_can_be_anything_up_to_32_and_the_capsule_follows(self):
        """名字可以为空、任何字、任何表情；最多 32 个（表情算一个），再打不进去时名字胶囊下面冒「名字太长啦！」，
        2 秒自己收。胶囊宽度跟着名字用弹簧变（打字时连续、不跳）。"""
        from widget.widgets import NAME_MAX, sticker_tip
        s = self.settings
        s.show()
        self.app.processEvents()
        s.show_page("pet", False)                                      # 改名在详情页
        s.finish_page_anim()
        bar = s._tag
        s.start_rename()
        s._title_edit.setText("")
        s._title_edit.textEdited.emit("")
        self.assertEqual(NAME_MAX, 32)
        many = "🐶👨‍👩‍👧‍👦" * 17
        s._title_edit.setText(many)
        s._title_edit.textEdited.emit(many)
        from widget.widgets import grapheme_count
        self.assertEqual(grapheme_count(s._title_edit.text()), 32, "表情也是一个算一个，最多 32 个")
        tip = sticker_tip()
        self.assertTrue(tip.isVisible() and tip.text == "Name is too long!", "再打就提示名字太长")
        s._long_name.timeout.emit()                                    # 2 秒到了
        self.assertFalse(tip.isVisible(), "自己收")
        s._title_edit.setText("小饼干")
        before = bar.tag.value
        s._title_edit.setText("小饼干和大黄狗")                         # 打字：目标变宽，宽度用弹簧连续变过去
        self.assertGreater(bar.tag.target, before)
        values = []
        for _ in range(40):
            bar.tick(1 / 60)
            values.append(bar.tag.value)
        steps = [b - a for a, b in zip([before] + values, values)]
        self.assertTrue(all(st >= -0.01 for st in steps), "一路变宽，不来回")
        self.assertLess(max(steps), 12.0, "每帧不跳")
        self.assertAlmostEqual(values[-1], bar.tag.target, delta=0.5, msg="0.67 秒内到位")
        s._title_edit.setText("  ")
        s._title_edit.editingFinished.emit()
        self.assertEqual(self.win.dog_name, "")
        self.assertEqual(bar.tag.target, bar.H, "名字为空：正圆")

    def _chip_bar(self, name: str):
        """设置卡片打开、名字 name、中文那几种说法的新版本胶囊在、停稳。"""
        s = self.settings
        s.show()
        self.app.processEvents()
        bar = s._tag
        self.win.set_dog_name(name)
        bar.set_chip(("新版本已下载完成", "新版本已下载", "新版本"), animated=False)
        bar.finish_now()
        return s, bar

    def _gaps(self, bar) -> tuple:
        t, c = bar.tag_rect(), bar.chip_rect()
        return t.left() - bar._edge(), c.left() - t.right(), bar._end() - c.right()

    def test_update_chip_and_name_keep_three_even_gaps_and_pick_a_saying(self):
        """有新版本胶囊时名字是主角、照样摆在中间：左边的圆 → 名字 → 胶囊 → × 三段空一样宽（撑满时各 GAP）；
        胶囊按名字剩下的地方挑放得下的最长说法（新版本已下载完成 → 新版本已下载 → 新版本），平常最少留「新版本」，名字还放不下才省略。"""
        from widget.widgets import Marquee, ellipsis_strength
        s, bar = self._chip_bar("小黑")
        base = "我家那只特别能跑特别爱叫的边牧小黑子"
        for n in (1, 2, 4, 6, 8, 14, 18):
            self.win.set_dog_name(base[:n])
            bar.finish_now()
            room = bar._right() - bar._start() - bar.GAP - bar.tag_rect().width()
            fits = [say for say in bar.chip_says if bar.chip_natural(say) <= room + 0.5]
            self.assertEqual(bar._say, fits[0] if fits else "新版本", f"{n} 个字：挑放得下的最长那句")
            self.assertAlmostEqual(bar.chip_rect().width(), bar.chip_natural(bar._say), delta=0.01)
            gaps = self._gaps(bar)
            self.assertLessEqual(max(gaps) - min(gaps), 1.0, f"{n} 个字：三段空一样宽 {gaps}")
            self.assertGreaterEqual(min(gaps), bar.GAP - 0.5)
            self.assertEqual(bar.name_truncated(), bar.natural_tag() > bar.tag_rect().width() + 0.5)
        self.assertEqual(bar._say, "新版本", "名字放不下：胶囊最少留「新版本」，名字省略")
        self.assertTrue(bar.name_truncated())
        self.win.set_dog_name("小")
        bar.finish_now()
        self.assertEqual(bar._say, "新版本已下载完成", "名字短：整句放得下")
        self.assertFalse(bar.chip_truncated())
        self.win.set_dog_name("我家小黑同学")
        for _ in range(3):
            bar.tick(1 / 60)
        self.assertEqual((bar._say_prev, bar._say), ("新版本已下载完成", "新版本"), "换说法：旧的淡出、新的同时淡入")
        self.assertTrue(0.0 < bar._say_k < 1.0)
        for _ in range(30):
            bar.tick(1 / 60)
        self.assertEqual((bar._say, bar._say_prev, bar._say_k), ("新版本", None, 1.0))
        m, distance, dt = Marquee(), 60.0, 1 / 85                      # 整句比整条还长、展开着时才滚：滚法本身
        offsets, alphas = [], []
        for _ in range(int(17 / dt)):                                # 一遍约 5 秒（等 1.2、滚 2.25、停 1.2、淡回 0.3）
            m.step(dt, distance)
            offsets.append(m.offset)
            alphas.append(m.alpha)
        jumps = [abs(b - a) for a, b, al in zip(offsets, offsets[1:], alphas[1:]) if al > 0.05]
        self.assertLess(max(jumps), Marquee.SPEED * dt * 1.01, "看得见的时候每帧最多走 30 像素/秒那么多：起步、到头都不跳")
        self.assertEqual(m.phase, "rest", "滚 3 遍停在开头")
        self.assertEqual(m.offset, 0.0)
        strengths = [ellipsis_strength(o, distance) for o in offsets]
        changes = [max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b, al in zip(strengths, strengths[1:], alphas[1:]) if al > 0.05]
        self.assertLess(max(changes), 0.05, "省略号的浓淡也是连续变的")
        m = Marquee()
        for _ in range(int(2.0 / dt)):
            m.step(dt, distance)
        self.assertGreater(m.offset, 5.0)
        m.interrupt()                                                  # 滚到一半字窗变了：滑回开头，不跳
        prev = m.offset
        for _ in range(30):
            m.step(dt, distance)
            self.assertLess(abs(m.offset - prev), 8.0)
            prev = m.offset
        m = Marquee()
        while m.phase != "fade":
            m.step(dt, distance)
        for _ in range(5):
            m.step(dt, distance)
        seen = [m.alpha]
        m.interrupt()                                                  # 一遍滚完正在淡回开头时字窗变了：浓淡接着变，不闪回全浓
        while m.phase == "fade":
            m.step(dt, distance)
            seen.append(m.alpha)
        self.assertLess(max(abs(b - a) for a, b in zip(seen, seen[1:])), 2 * dt / Marquee.FADE + 1e-6)
        self.assertEqual((m.phase, m.offset, m.alpha), ("wait", 0.0, 1.0), "淡完停在开头、全浓，再等 1.2 秒")

    def test_update_chip_squeezes_in_without_stopping_and_leaves_to_the_right(self):
        """胶囊在最后的位置从 × 那边长出来，碰到名字以后推着名字往左，名字从碰上起一路走到位——不停、不往回走
        （看了第六批：「为什么要在这顿一下？不要在这顿一下」），被挤着时右头压扁一点；最后三段空一样宽。收走时往右缩、淡掉，名字回正中。"""
        s = self.settings
        s.show()
        self.app.processEvents()
        bar = s._tag
        for name in ("小黑", "我家小黑同学"):
            self.win.set_dog_name(name)
            bar.set_chip("", animated=False)
            bar.finish_now()
            centred = bar.tag_rect().left()
            bar.set_chip(("新版本已下载完成", "新版本已下载", "新版本"))
            right = bar.chip_rect().right()
            self.assertLess(bar.chip_rect().width(), bar.H, "从 × 那边冒出来一小截")
            lefts, squish, rights = [bar.left.value], 0.0, []
            for _ in range(90):
                bar.tick(1 / 60)
                lefts.append(bar.left.value)
                if bar._chip_in is not None:
                    squish = max(squish, bar._chip_in.name_box(bar)[1])
                    rights.append(bar.chip_rect().right())
            self.assertIsNone(bar._chip_in, "1.5 秒内挤完")
            self.assertEqual(max(rights), min(rights), "挤进来时右头钉在最后的位置")
            self.assertAlmostEqual(rights[0], right, delta=0.01)
            steps = [a - b for a, b in zip(lefts, lefts[1:])]
            self.assertTrue(all(st >= -1e-6 for st in steps), f"{name}：一路往左，不往回走")
            moving = [i for i, st in enumerate(steps) if st > 0.05]           # 最后弹簧停稳时那一下（不到 0.05 像素）不算
            first, last = moving[0], moving[-1]
            peak = max(steps)
            top = steps.index(peak)
            self.assertTrue(all(b >= a - 1e-6 for a, b in zip(steps[first:top], steps[first + 1:top + 1])), f"{name}：起步一路加快")
            self.assertTrue(all(b <= a + 1e-6 for a, b in zip(steps[top:last], steps[top + 1:last + 1])), f"{name}：到位前一路减慢，中间不停一下再走")
            self.assertLess(lefts[-1], centred, "名字往左让")
            self.assertGreater(squish, 0.03, "被挤着的时候右头压扁一点")
            gaps = self._gaps(bar)
            self.assertLessEqual(max(gaps) - min(gaps), 1.0, f"最后三段空一样宽 {gaps}")
        right = bar.chip_rect().right()
        bar.set_chip("")                                               # 收走：往右缩、淡掉，名字回正中
        seen = []
        for _ in range(30):
            bar.tick(1 / 60)
            r = bar.chip_rect()
            if not r.isNull():
                seen.append(r.right())
        self.assertTrue(seen and all(abs(x - right) < 0.01 for x in seen), "右头钉住、往右缩")
        self.assertTrue(bar.chip_rect().isNull(), "淡没了就不在了")
        bar.finish_now()
        self.assertAlmostEqual(bar.tag_rect().center().x(), bar._span() / 2.0, delta=0.5, msg="名字回正中")

    def test_name_and_update_chip_squeeze_each_other(self):
        """鼠标在被省略的名字上停 0.5 秒（不出「点击改名」）：名字最多拉到只给胶囊留一个圆，胶囊再挑放得下的说法，
        「新版本」也放不下才缩成只剩下载图标的圆；放到被换短了的胶囊上立刻往左展开成整句，名字让开（最窄一个正圆）；移开马上恢复。
        整句比整条还长（别的语言可能这样）就在胶囊里滚。平时两个永远不叠，每帧只挪一点点。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        s, bar = self._chip_bar("我家那只特别能跑特别爱叫的边牧小黑子")
        phases = []

        def edges() -> tuple:
            t, c = bar.tag_rect(), bar.chip_rect()
            return (t.left(), t.right(), None, None) if c.isNull() else (t.left(), t.right(), c.left(), c.right())

        def run(n: int = 45) -> None:
            seq = [edges()]
            for _ in range(n):
                bar.tick(1 / 60)
                seq.append(edges())
            phases.append(seq)

        self.assertTrue(bar.name_truncated() and bar.chip_truncated())
        self.assertEqual(bar._say, "新版本")
        s._tip_target = bar
        s._show_tip(force=True)                                       # 鼠标在名字上停满 0.5 秒
        self.assertIsNone(s._tip_shown, "名字被省略时不出「点击改名」")
        self.assertEqual(bar._peek, "name")
        run()
        self.assertAlmostEqual(bar.chip_rect().width(), bar.H, delta=0.01, msg="18 个字撑满整条：胶囊才缩成圆")
        self.assertIsNone(bar._say)
        self.assertAlmostEqual(bar.chip_rect().left() - bar.tag_rect().right(), bar.GAP, delta=0.01)
        bar.set_peek(None)                                             # 移开
        run()
        self.assertEqual(bar._say, "新版本", "恢复")
        self.win.set_dog_name("我家那只特别能跑的边")                    # 10 个字：停上去名字放得下，胶囊只缩一点点
        run()
        bar.set_peek("name")
        run()
        self.assertAlmostEqual(bar.tag_rect().width(), bar.natural_tag(), delta=0.5, msg="停上去：名字整个露出来")
        room = bar._right() - bar._start() - bar.GAP - bar.natural_tag()
        self.assertEqual(bar._say, "新版本" if bar.chip_natural("新版本") <= room + 0.5 else None, "胶囊挑剩下放得下的，放不下「新版本」才缩成圆")
        bar.set_peek(None)
        run()
        at = bar.chip_rect().center()
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseMove, at, QPointF(bar.mapToGlobal(at.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        self.assertEqual(bar._peek, "chip", "放到被换短了的胶囊上：不用等")
        run()
        self.assertEqual(bar._say, "新版本已下载完成", "整句")
        self.assertAlmostEqual(bar.chip_rect().width(), bar.chip_natural("新版本已下载完成"), delta=0.01)
        self.assertAlmostEqual(bar.chip_rect().right(), bar._right(), delta=0.5, msg="撑满时离 × 也是 GAP")
        self.assertGreaterEqual(bar.tag_rect().width(), bar.H - 0.01, "名字胶囊最窄是正圆")
        QApplication.sendEvent(bar, QEvent(QEvent.Leave))
        self.assertIsNone(bar._peek, "移开马上恢复")
        run()
        bar.set_chip("A new version was downloaded and is ready to install")   # 只有一种说法、比整条还长
        run()
        at = bar.chip_rect().center()
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseMove, at, QPointF(bar.mapToGlobal(at.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        run()
        self.assertAlmostEqual(bar.tag_rect().width(), bar.H, delta=0.01, msg="展开到名字只剩正圆为止")
        self.assertAlmostEqual(bar.chip_rect().width(), bar._right() - bar._start() - bar.H - bar.GAP, delta=0.01, msg="还放不下就在胶囊里滚")
        QApplication.sendEvent(bar, QEvent(QEvent.Leave))
        bar.set_chip("")                                               # 收走：名字回正中
        run()
        for seq in phases:                                             # 弹簧（0.3 秒）一帧最多走全程的 2π/0.3/60/e ≈ 12.8%；跳就是一帧走完全程
            travel = max(max(v) - min(v) for v in ([f[i] for f in seq if f[i] is not None] for i in range(4)) if v)
            for i in range(4):
                for a, b in zip(seq, seq[1:]):
                    if a[i] is not None and b[i] is not None:
                        self.assertLessEqual(abs(b[i] - a[i]), 0.135 * travel + 0.5, "每帧只挪一点点，不跳")
            for f in seq:
                if f[2] is not None:
                    self.assertGreaterEqual(f[2] - f[1], -0.01, "新版本胶囊永远不压到名字胶囊上")

    def _frames(self, card, n: int, probe) -> list:
        """推 n 帧（每帧 1/60 秒，不真等），每帧记一下 probe()。"""
        out = []
        for _ in range(n):
            card.frame_step(card.clock._last + 1 / 60, 1 / 60)
            out.append(probe())
        return out

    def test_every_frame_on_screen_matches_a_full_repaint(self):
        """打开设置后卡片底下多一道影子、顶上的描边被裁，切屏才好。打开时往上浮，只重画了挪动的主叶，
        画在主叶外面一两像素的描边和纸片影没重画。单测拿窗口后备缓冲里真正显示的那张（离屏平台的 grabWindow）和整张重画比，
        每个动画的每一帧都要一样（离屏平台的重画用一个小计时器排着，晚一点才到：每帧推完等它画完再比）。"""
        from PySide6.QtTest import QTest
        s = self.settings
        bad = []

        def frames(label: str, n: int = 24) -> None:
            for i in range(n):
                s.frame_step(s.clock._last + 1 / 60, 1 / 60)
                QTest.qWait(8)                                        # 真的去画：只重画标脏了的地方
                if not s.isVisible():
                    return
                shown, fresh = s.screen().grabWindow(s.winId()).toImage(), s.grab().toImage()
                if shown.size() != fresh.size():
                    bad.append((label, i, "size"))
                    continue
                for y in range(0, fresh.height(), 2):
                    if any(abs(shown.pixelColor(x, y).alpha() - fresh.pixelColor(x, y).alpha()) > 40 for x in range(0, fresh.width(), 2)):
                        bad.append((label, i, y))
                        break

        gc.collect()                                              # 比的是「等 8 毫秒以后窗口里的」：全量跑到这里堆很大，赶上一次垃圾回收就不止 8 毫秒，
        gc.disable()                                              # 那一帧还没画上就被当成残影（查过：再等 60 毫秒就对了；关了回收全量照过）。这期间不回收，只看画得对不对
        self.addCleanup(gc.enable)
        s.show()
        self.app.processEvents()
        frames("打开：淡入上浮")
        s.follow.click()
        frames("开鼠标跟随：开关、动作行展开")
        s.posture_buttons["sitting"].click()
        frames("选动作")
        s.dynamic.click()
        frames("开灵动交互：动作行收起")
        self.win.updater.state = "downloaded"
        s.sync_update()
        frames("新版本胶囊长出来")
        s.show_advanced(True)
        frames("换到高级设置")
        s.swatches[1].setChecked(True)
        frames("选毛色")
        s.back.click()
        frames("返回主页面")
        s._close.click()
        frames("关上：淡出")
        self.assertEqual(bad, [], "窗口里显示的和整张重画的一样（没有残影、没有被裁的边）")

    def test_rows_keep_their_inner_spacing(self):
        """语言的两个胶囊贴在一起了——主页面改成 stack 排（页面间距 0）以后，没自己设间距的行跟着变成 0。补回 10。"""
        s = self.settings
        s.show()
        s.finish_page_anim()
        self.app.processEvents()
        self.assertEqual(s.reset_button.x() - (s.size_label.x() + s.size_label.width()), 1, "数字和重置之间空 1（大小在主页面）")
        s.show_advanced(True, False)                            # 语言在高级设置页
        s.finish_page_anim()
        self.app.processEvents()
        en, zh = s.lang_buttons["en"], s.lang_buttons["zh"]
        self.assertEqual(zh.x() - (en.x() + en.width()), 10, "English 和 中文 之间空 10")

    def test_switching_language_mid_animation_answers_at_once_and_never_freezes(self):
        """从高级设置点 ‹ 回主页面、紧接着点「中文」，整个小组件卡死。卡片的动画挂在狗的每一帧上，换语言时旧卡片删掉了
        还挂在那，狗的下一帧一问它就出错，帧循环断了。现在：删掉的卡片自己摘掉，狗推帧时出错的卡片也摘掉、帧照常往下排；
        新卡片原地顶替，旧的字淡出、新的淡入（用户点了就一定有反馈）。"""
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        win = self.win
        win.show()
        self.app.processEvents()
        s = self.settings
        s.show()
        s.finish_page_anim()
        s.show_advanced(True)
        s.show_advanced(False)                                         # 换页动画还在走
        old_clock = s.clock
        self.assertIn(old_clock, win._frame_clients)
        win.set_language("zh")                                         # 就在这时点「中文」
        new = win.settings_panel
        self.assertIsNot(new, s)
        self.assertTrue(new.isVisible() and new.windowOpacity() == 1.0, "新卡片原地出现，不先消失再淡入")
        self.assertEqual(new.advanced_link.text(), "高级设置…", "点了就换成中文")
        self.assertIsNotNone(new._swap, "旧的样子盖在上面淡出")
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)    # 旧卡片真的删掉
        self.assertNotIn(old_clock, win._frame_clients, "删掉的卡片自己从狗的帧上摘掉")
        win._frame_clients.add(old_clock)                              # 就算还挂着：狗推帧时摘掉它，不出错、下一帧照排
        win._anim_timer.stop()
        win._frame()
        self.assertNotIn(old_clock, win._frame_clients)
        self.assertTrue(win._anim_timer.isActive(), "狗的下一帧照常排上")
        self.assertIn(new.clock, win._frame_clients, "新卡片的淡入淡出挂在狗的帧上接着走")
        new.finish_page_anim()
        self.assertIsNone(new._swap, "淡入淡出走完")
        self.settings = new                                           # tearDown 关新的

    def test_update_line_survives_results_that_come_back_mid_fade(self):
        """卡死在高级设置——点检查更新，「正在检查…」还在淡入，GitHub 已经回了「已是最新版本」：第二个淡入淡出给同一处
        换上效果时 Qt 把第一个的删了，第一个每帧去改它就出错，整张卡片停住。现在同一处的上一个先收尾，新的从屏幕上的样子接着淡；
        哪个出错也只扔掉那一个。换语言之后再来一遍也一样。"""
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        win = self.win
        up = win.updater
        up._fetch = lambda url: []                                     # 没有新版本
        up._spawn = lambda fn: fn()                                    # 结果马上回来（比淡入淡出快）

        def run(card) -> None:
            card.show_advanced(True)
            card.finish_page_anim()
            card._update_clicked()
            self.app.processEvents()
            self.assertEqual(up.state, "latest")
            for _ in range(40):
                card.frame_step(card.clock._last + 1 / 60, 1 / 60)    # 不抛错
            self.assertFalse(card._animators, "淡入淡出都走完了，没有卡住的")
            self.assertEqual(card.update_button.text(), card.update_button._display_text)
            self.assertIsNone(card.update_button.graphicsEffect(), "文字动画不安装透明效果或截图层")

        self.settings.show()
        self.settings.finish_page_anim()
        run(self.settings)
        self.settings.back.click()
        win.set_language("zh")
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settings = win.settings_panel
        self.settings.finish_page_anim()
        up.state = "idle"
        self.settings.sync_update()
        run(self.settings)

    def test_crossfade_snapshots_are_transparent_where_empty(self):
        """深色模式下点检查更新闪一下白框。淡入淡出前给旧样子拍的图以前用 grab，会先铺一层调色板的浅色底；
        现在只画内容，空白的地方透明（换页、换一行字、换语言都一样）。"""
        win = self.win
        win.set_appearance("dark")
        s = self.settings = win.settings_panel
        s.show()
        s.finish_page_anim()
        s.show_advanced(True)                                          # 换页
        swaps = [s._swap]
        s.finish_page_anim()
        win.updater._spawn = lambda fn: None
        s._update_clicked()                                            # 检查更新那一行换字
        swaps += [a for a in s._animators if type(a).__name__ == "_Swap"]
        self.assertEqual(len(swaps), 1, "只有整页换页用快照，更新行只换原位文字")
        for sw in swaps:
            img = sw.label.pixmap().toImage()
            self.assertEqual(img.pixelColor(1, 1).alpha(), 0, "角上是空白：透明，不铺底色")
        win.set_language("zh")
        new = win.settings_panel
        self.assertEqual(new._swap.label.pixmap().toImage().pixelColor(1, 1).alpha(), 0, "换语言：也是透明的")
        self.settings = new

    def test_switches_slide_when_the_setting_changes_while_the_card_is_open(self):
        """开关打开、关上都有动画，别处改了设置也滑过去；只有卡片打开那一下对齐设置时直接到位。"""
        s = self.settings
        s.show()
        s.finish_page_anim()
        self.assertFalse(s.follow.isChecked())
        self.win.set_follow_cursor(True)                               # 别处（「···」菜单、键盘）改的
        s.sync()
        self.assertTrue(s.follow.isChecked())
        self.assertLess(s.follow._pos, 0.1, "这一帧钮还在左边，不跳")
        poses = self._frames(s, 14, lambda: s.follow._pos)
        self.assertTrue(all(b >= a for a, b in zip(poses, poses[1:])), "一路滑过去")
        self.assertEqual(poses[-1], 1.0, "0.18 秒到位")
        s.hide()
        self.win.set_follow_cursor(False)                              # 卡片关着时改
        s.show()
        self.assertEqual(s.follow._pos, 0.0, "打开那一下直接到位，不在淡入时才滑")

    def test_cards_rise_as_they_fade_in_and_fade_out_when_closed(self):
        """卡片打开淡入、同时往上浮 6 像素；×、Esc 关上时 0.12 秒淡出再藏起来；淡出中又点打开：停下淡回来。"""
        from PySide6.QtCore import QPoint
        from widget.sticker import SHADOW
        s = self.settings
        s.show()
        self.assertEqual(s.windowOpacity(), 0.0)
        self.assertEqual(s._outer.contentsMargins().top(), SHADOW + 6, "先低 6 像素")
        frames = self._frames(s, 15, lambda: (s.windowOpacity(), s._outer.contentsMargins().top()))
        self.assertTrue(all(b[0] >= a[0] and b[1] <= a[1] for a, b in zip(frames, frames[1:])), "边淡入边往上浮")
        self.assertEqual(frames[-1], (1.0, SHADOW))
        self.assertEqual(s._outer.contentsMargins().bottom(), SHADOW, "窗口不动，只是上下边距此消彼长")
        s._close.click()
        ops = self._frames(s, 4, s.windowOpacity)
        self.assertTrue(s.isVisible() and all(b < a for a, b in zip(ops, ops[1:])), "淡出中")
        self.win.open_settings()                                       # 淡出到一半又点打开
        self.assertFalse(s.closing)
        ops = self._frames(s, 12, s.windowOpacity)
        self.assertTrue(all(b >= a for a, b in zip(ops, ops[1:])) and ops[-1] == 1.0, "从现在的浓淡淡回来")
        self.assertEqual(s._outer.contentsMargins().top(), SHADOW, "淡回来不再上浮")
        s.keyPressEvent(type("E", (), {"key": lambda self: __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key_Escape})())
        self._frames(s, 10, s.windowOpacity)
        self.assertFalse(s.isVisible(), "Esc：淡完就藏起来")
        self.assertEqual(s.windowOpacity(), 1.0, "藏起来以后浓淡改回 1，下次打开照常")

    def test_pills_and_the_update_line_change_with_a_fade(self):
        """选中换颜色、检查更新那一行换字都有过渡：动作的胶囊 0.15 秒渐变；检查更新换状态时旧字淡出、新字淡入（下载百分比变不算）。"""
        s = self.settings
        s.show()
        s.follow.click()
        s.finish_page_anim()
        sitting = s.posture_buttons["sitting"]
        sitting.click()
        clock = sitting.motion.clock
        clock._timer.stop()                        # 用真实共用FrameClock推进，按钮选中不再依赖Card._animators
        sels, now = [], clock._last
        for _ in range(12):
            now += 1 / 60
            clock.frame_step(now, 1 / 60)
            sels.append(sitting._sel)
        self.assertTrue(0.0 < sels[0] < 1.0 and sels[-1] == 1.0 and all(b >= a for a, b in zip(sels, sels[1:])), "颜色一点点变过去")
        s.show_advanced(True)
        s.finish_page_anim()
        up = self.win.updater
        up.state = "checking"
        s.sync_update()
        fades = [c for c in s._animators if type(c).__name__ == "_Swap"]
        self.assertFalse(fades, "更新行不再复制按钮背景")
        self.assertTrue(s.update_button.text_animating, "文字本身淡出再淡入")
        s.finish_page_anim()
        up.state, up.progress = "downloading", 0.1
        s.sync_update()
        s.finish_page_anim()
        up.progress = 0.2
        s.sync_update()
        self.assertFalse([c for c in s._animators if type(c).__name__ == "_Swap"], "下载百分比变：直接换字，不闪")
        self.assertIn("20", s.update_button.text())
        self.assertFalse(s.update_button.text_animating, "下载进度原位直接更新，不重复闪字")

    def test_reduce_motion_puts_everything_in_place_at_once(self):
        """系统开了「减少动态效果」：开关、展开的行、卡片打开 / 关上、提示、菜单都直接到位。"""
        from widget import native
        from widget.widgets import sticker_tip
        with mock.patch.object(native, "reduce_motion", return_value=True):
            s = self.settings
            s.show()
            self.assertEqual(s.windowOpacity(), 1.0)
            s.follow.click()
            self.assertEqual(s.follow._pos, 1.0)
            s.dynamic.click()
            self.assertFalse(s.posture_collapse.animating)
            self.assertFalse(s.posture_section.isVisibleTo(s))
            row = s.follow.parentWidget()
            sticker_tip().show_for(row, "x", beside=row)
            self.assertEqual(sticker_tip()._pop, 1.0)
            sticker_tip().hide()
            s._close.click()
            self.assertFalse(s.isVisible())

    def _watch_bar(self, n: int = 30) -> list:
        """推 n 帧卡片，每帧记顶部栏的样子：(名字胶囊的正中 x（卡片坐标）, 正在画的字, 它的浓淡, 左边圆里的图案)。"""
        from PySide6.QtCore import QPoint
        s, bar = self.settings, self.settings._tag

        def probe() -> tuple:
            x = bar.mapTo(s._main, QPoint(0, 0)).x() + bar.left.value + bar.tag.value / 2
            return x, bar._drawn_text, bar._drawn_alpha, bar.lead.mix
        return [probe()] + self._frames(s, n, probe)

    def assert_bar_morphs_in_place(self, frames: list, centre: float = 156.0) -> None:
        """换页时顶部栏只是字和宽度在变：胶囊不跑（正中 x 不动）、一直只画一行字（旧字淡没了才换新字）、浓淡一帧只变一点（不跳、不闪）、
        左边圆里的图案一路往一个方向淡（不回头）。"""
        from widget.card import TitleBar
        step = 2 / 60 / TitleBar.TEXT_FADE_S + 1e-6
        mixes = [f[3] for f in frames]
        for (x0, t0, a0, _m0), (x1, t1, a1, _m1) in zip(frames, frames[1:]):
            self.assertAlmostEqual(x1, centre, delta=0.6, msg="胶囊不跑：一直在卡片正中")
            self.assertLessEqual(abs(a1 - a0), step, "字的浓淡一帧只变一点")
            if t1 != t0:
                self.assertEqual(a1, 0.0, "旧字淡没了才换新字：两行不叠")
        self.assertTrue(all(b >= a for a, b in zip(mixes, mixes[1:])) or all(b <= a for a, b in zip(mixes, mixes[1:])), "圆里的图案一路往一个方向淡")

    def test_the_top_bar_stays_and_only_its_text_width_and_icon_change(self):
        """顶部栏每一页都在（同一条，不重建、不搬家），换页时只是里面的字和宽度顺滑地变，左边圆里的图案先淡出再淡入，
        不做飞来飞去的动画；名字胶囊每一页都在卡片正中。下面的内容淡入淡出只拍内容区，盖不到顶部栏。"""
        from PySide6.QtCore import QPoint
        s = self.settings
        s.show()
        self.app.processEvents()
        s.finish_page_anim()
        bar = s._tag
        self.assertIs(bar.parentWidget(), s._main)
        self.assertTrue(bar.centered)
        self.assertEqual((bar.text(), bar.lead_mode, bar.lead.mix), ("Milo", "mark", 0.0))
        close_at = s._close.mapTo(s._main, QPoint(0, 0))
        s.show_advanced(True)                                          # 带动画
        self.assertIs(bar.parentWidget(), s._main, "还是那一条")
        self.assertEqual((bar.text(), bar._drawn_text, bar.lead_mode), ("Advanced", "Milo", "back"), "旧字还在：先淡出")
        self.assertIsNotNone(s._swap, "下面的内容淡入淡出")
        self.assertGreaterEqual(s._swap.label.geometry().top(), 42, "只拍内容区：盖不到顶部栏")
        frames = self._watch_bar()
        self.assert_bar_morphs_in_place(frames)
        self.assertEqual(frames[-1][1:], ("Advanced", 1.0, 1.0), "淡完：新字全浓，圆里是返回")
        s.finish_page_anim()
        self.app.processEvents()
        self.assertEqual(s._close.mapTo(s._main, QPoint(0, 0)), close_at, "× 不动")
        s.show_page("tuning")
        frames = self._watch_bar()
        self.assert_bar_morphs_in_place(frames)
        self.assertEqual(frames[-1][1:], ("Developer", 1.0, 1.0), "别的页之间：圆里一直是返回")
        s.show_page("main")
        frames = self._watch_bar()
        self.assert_bar_morphs_in_place(frames)
        self.assertEqual(frames[-1][1:], ("Milo", 1.0, 0.0), "回主页面：圆里换回 app 图标")
        s.finish_page_anim()
        self.assertEqual(bar.lead_mode, "mark")
        self.assertFalse(bar.isHidden())

    def test_custom_coat_opens_at_once_and_only_the_title_changes(self):
        """点「自定义」= 立刻换成自定义毛色、直接进自定义页；进出只是顶部栏的字从名字换成「自定义毛色」，
        下面内容淡入淡出（不做「流过去变成标题」）。"""
        s = self.settings
        s.show()
        self.app.processEvents()
        s.show_page("pet", animated=False)
        s.finish_page_anim()
        bar = s._tag
        s.custom_swatch.click()
        self.assertEqual((self.win.coat, s.page), (0, "coat"), "一点就换、马上进这一页")
        self.assertEqual((bar.text(), bar.lead_mode), ("Custom color", "back"))
        self.assertGreaterEqual(s._swap.label.geometry().top(), 42, "淡的只是下面的内容")
        frames = self._watch_bar()
        self.assert_bar_morphs_in_place(frames)
        self.assertEqual(frames[-1][1:3], ("Custom color", 1.0))
        s.finish_page_anim()
        s.back.click()
        self.assertEqual(s.page, "pet")
        frames = self._watch_bar()
        self.assert_bar_morphs_in_place(frames)
        self.assertEqual(frames[-1][1:3], ("Milo", 1.0), "回详情页：字换回名字")

    def test_the_title_never_shows_two_texts_or_jumps_when_it_changes_quickly(self):
        """顶部栏的字来回快换（滑动条一路滑过几只、换页又马上换回来）：任何时候只画一行，旧字淡没了才换新字，浓淡一帧只变一点；
        换回原来那个字就从现在的浓淡淡回来；animated=False 把还在走的直接走完。名字 ↔ 标签（「添加同桌」）也照这个规矩换。"""
        from widget.card import TitleBar
        s = self.settings
        s.show()
        self.app.processEvents()
        s.finish_page_anim()
        bar = s._tag
        step = 2 / 60 / TitleBar.TEXT_FADE_S + 1e-6
        seen = [(bar._drawn_text, bar._drawn_alpha)]
        plan = {0: ("A", False), 3: ("B", False), 5: ("A", False), 9: ("Add", True), 20: ("C", False)}
        for i in range(60):
            if i in plan:
                bar.setText(*plan[i][:1], outlined=plan[i][1])
            bar.tick(1 / 60)
            seen.append((bar._drawn_text, bar._drawn_alpha))
        for (t0, a0), (t1, a1) in zip(seen, seen[1:]):
            self.assertLessEqual(abs(a1 - a0), step, "浓淡一帧只变一点")
            if t1 != t0:
                self.assertEqual(a1, 0.0, "旧字淡没了才换新字")
        self.assertEqual(seen[-1], ("C", 1.0))
        bar.setText("D")
        bar.tick(1 / 60)
        self.assertLess(bar._drawn_alpha, 1.0)
        bar.setText("D", animated=False)
        self.assertEqual((bar._drawn_text, bar._drawn_alpha), ("D", 1.0), "同一个字再要一次、不要动画：还在淡的直接走完")

    def test_hold_ring_runs_on_the_outline_and_never_covers_the_text(self):
        """所有要长按的都是一圈进度线（和退出、重置、关机键一样）；新的胶囊按钮上，线压在描边上走，挡不到字。"""
        from PySide6.QtGui import QColor
        from widget import sticker
        from widget.widgets import HoldPill
        for kind in ("danger", "primary"):
            b = HoldPill("删除安装包", kind, self.win.accent_color())
            b.setStyleSheet(sticker.stylesheet(sticker.theme(self.win.accent_color())))
            b.resize(130, 26)
            before = b.grab().toImage()
            b.driver.progress = 0.5
            after = b.grab().toImage()
            for x in range(20, 110):                                   # 字所在的中间一条（离上下边 6 像素以里）：一个像素都不变
                for y in range(6, 20):
                    self.assertEqual(before.pixel(x, y), after.pixel(x, y), f"{kind}：进度线没碰到字（{x}, {y}）")
            changed = sum(before.pixel(x, 1) != after.pixel(x, 1) or before.pixel(x, 2) != after.pixel(x, 2) for x in range(66, 110))
            self.assertGreater(changed, 30, f"{kind}：顶上正中往右那段描边被进度线盖过去了")
            self.assertEqual(before.pixel(30, 1), after.pixel(30, 1), f"{kind}：走一半时左上那段还没到")

    def test_coat_dots_show_the_dark_and_light_fur_and_a_visible_ring(self):
        """色块和狗要一致（取整张贴图的平均色会有色差：第一套 #6a686d，狗身上是 #272730 / #aaa6a8）；
        选中的框有时看不出来（图标 22 一直不变，盖住了加粗描边的里面一半）。现在上深下浅，选中时图标缩到 18。"""
        from PySide6.QtGui import QColor
        from widget.widgets import Avatar
        s = self.settings
        s.show()
        s.show_page("pet", False)
        self.app.processEvents()
        dark, light = self.win.coat_swatches()[0]
        self.assertLess(QColor(dark).lightness(), 80, "上半是深色毛")
        self.assertGreater(QColor(light).lightness(), 140, "下半是浅色毛")
        self.assertFalse(s.swatches[0].icon().isNull(), "原装色块画成上深下浅的图标")
        for sw in s.swatches + [s.custom_swatch]:
            self.assertEqual(sw.inner_px(), Avatar.ICON_CHECKED if sw.isChecked() else Avatar.ICON)
        self.assertTrue(s.swatches[0].isChecked())
        s.custom_swatch.setChecked(True)
        widths = []
        for _ in range(12):                                            # 描边 2 → 4、里面的图 40 → 36 用 0.15 秒渐变
            s.frame_step(s.clock._last + 1 / 60, 1 / 60)
            widths.append(s.custom_swatch.inner_px())
        self.assertTrue(all(b <= a for a, b in zip(widths, widths[1:])) and widths[0] > Avatar.ICON_CHECKED, "一点点缩，不跳")
        s.finish_page_anim()
        self.assertEqual(s.custom_swatch.inner_px(), Avatar.ICON_CHECKED, "自定义选中：里面缩一圈，加粗的框露出来")
        self.assertEqual(s.swatches[0].inner_px(), Avatar.ICON)

    def test_every_pill_is_as_tall_as_the_switch(self):
        """所有胶囊和开关一样高（26）、两头整圆。圆角 13 比高的一半大时，Qt 的样式表就整个不画圆角。"""
        from PySide6.QtWidgets import QPushButton
        from widget.widgets import PILL_H, Swatch
        for card in (self.settings,):                                  # 动作行（站 / 坐 / 趴 / 睡）显示着（灵动交互关着）
            card.show()
            self.app.processEvents()
            pills = [b for b in card.findChildren(QPushButton)
                     if not (b.property("tile") or b.property("big") or isinstance(b, Swatch))]
            self.assertTrue(pills)
            for b in pills:
                self.assertEqual(b.sizeHint().height(), PILL_H + 4, "控件自身提供正确尺寸，隐藏页不依靠扫树补高")
                if b.isVisibleTo(card):
                    self.assertEqual(b.motion.content_rect().height(), PILL_H, f"{b.text()!r} 可见胶囊和开关一样高")
                    self.assertEqual(b.height(), PILL_H + 4, "透明外包为上下各2px动效预留空间")
        self.assertEqual(self.settings.follow.motion.content_rect().height(), PILL_H)
        self.assertEqual(self.settings.follow.height(), PILL_H + 4)
        self.assertEqual(self.settings.actions_toggle.motion.content_rect().width(), PILL_H, "› 可见按下态保持整圆")
        self.assertEqual(self.settings.actions_toggle.width(), PILL_H + 4)

    def test_cards_size_to_their_wrapped_text_and_scroll_on_short_screens(self):
        from PySide6.QtWidgets import QLabel
        from widget.card import EDGE
        from widget.sticker import SHADOW
        def squeezed(card):
            return [lab.text() for lab in card.content.findChildren(QLabel)
                    if lab.isVisibleTo(card) and lab.wordWrap() and lab.height() + 1 < lab.heightForWidth(lab.width())]
        for lang in ("en", "zh"):
            self.win.set_language(lang)
            s = self.win.settings_panel
            s.show()
            s.sync()
            s.fit_height(available=3000)
            self.app.processEvents()
            self.assertEqual(s.height(), s.content_height(), "屏幕够高：卡片和内容一样高")
            self.assertEqual(s.scroll.verticalScrollBar().maximum(), 0, "放得下就没有滚动条")
            self.win.set_follow_cursor(True)                              # 动作行（四个词 + ›）显示出来再量宽
            s.sync()
            s.finish_page_anim()
            self.app.processEvents()
            self.assertLessEqual(s.content.minimumSizeHint().width(), s.scroll.viewport().width(),
                                 f"{lang}：内容不比卡片宽（10/30 英文的 Stand / Sit / Lie / Sleep 加 › 曾经溢出，整列开关被挤到表盘底下）")
            self.win.set_follow_cursor(False)
            s.sync()
            s.finish_page_anim()
            self.assertEqual(squeezed(s), [], f"{lang}：换行的说明文字不被挤（10/20 英文版重叠）")
            for page in ("advanced", "coat"):
                s.show_page(page, animated=False)
                s.finish_page_anim()
                self.app.processEvents()
                self.assertLessEqual(s.content.minimumSizeHint().width(), s.scroll.viewport().width(),
                                     f"{lang}/{page}：按钮外包后整页仍放得下")
                if page == "coat":
                    self.assertLessEqual(s.coat_page.minimumSizeHint().width(), 280,
                                         f"{lang}：两列缩略图、边框和动效余量全部在页面内")
            s.show_page("main", animated=False)
            s.finish_page_anim()
            s.fit_height(available=300)
            self.app.processEvents()
            self.assertEqual(s.height(), 300 + 2 * SHADOW - 2 * EDGE, "屏幕不够高：封顶")
            self.assertGreater(s.scroll.verticalScrollBar().maximum(), 0, "多出来的在卡片里滚动")
            self.assertEqual(squeezed(s), [], "封顶时也不挤，靠滚动")
            s.hide()

    def test_dragging_blank_card_space_still_moves_the_card(self):
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        s = self.settings
        s.show()
        pos0, local = s.pos(), QPointF(4, 4)
        def send(kind, d, buttons):
            gp = QPointF(s.content.mapToGlobal(local.toPoint())) + QPointF(d, d)
            self.app.sendEvent(s.content, QMouseEvent(kind, local + QPointF(d, d), gp, Qt.LeftButton, buttons, Qt.NoModifier))
        send(QEvent.MouseButtonPress, 0, Qt.LeftButton)
        send(QEvent.MouseMove, 30, Qt.LeftButton)
        send(QEvent.MouseButtonRelease, 30, Qt.NoButton)
        self.assertEqual(s.pos() - pos0, QPoint(30, 30), "内容放进滚动区以后，拖空白处照样能挪卡片")

    def test_follow_cursor_row_hides_while_dynamic_is_on(self):
        """灵动交互开着就把鼠标跟随那一行藏起来（灵动交互里狗本来就看鼠标，开关管不着），关了再长出来、按记着的开关。"""
        s, w = self.settings, self.win
        s.show()
        self.assertFalse(w.dynamic)
        self.assertTrue(s.follow.isVisibleTo(s), "灵动交互关着：有鼠标跟随")
        s.follow.click()
        self.assertTrue(w.follow_cursor)
        s.dynamic.click()
        self.assertTrue(s.follow_collapse.animating, "收起有动画，和动作行一起")
        s.finish_page_anim()
        self.assertFalse(s.follow.isVisibleTo(s), "灵动交互开着：鼠标跟随那一行藏起来")
        self.assertTrue(w.follow_cursor, "开关记着的不变")
        s.dynamic.click()
        s.finish_page_anim()
        self.assertTrue(s.follow.isVisibleTo(s), "关了灵动交互：长回来")
        self.assertTrue(s.follow.isChecked())

    def test_posture_row_shows_only_when_dynamic_is_off(self):
        self.settings.show()
        self.assertFalse(self.win.dynamic)
        self.assertTrue(self.settings.posture_section.isVisibleTo(self.settings), "灵动交互关着：有姿势行")
        self.assertTrue(self.win.hover.postures_available())
        self.settings.posture_buttons["standing"].click()
        self.assertEqual(self.win.rest_posture, "standing")
        self.assertEqual(self.win.settings.values["rest_posture"], "standing")
        self.settings.dynamic.click()
        self.assertTrue(self.win.dynamic)
        self.assertTrue(self.settings.posture_collapse.animating, "收起有动画")
        self.settings.finish_page_anim()
        self.assertFalse(self.settings.posture_section.isVisibleTo(self.settings), "灵动交互开着：姿势行藏起来，狗只站着")
        self.assertFalse(self.win.hover.postures_available(), "「···」旁边的站 / 坐 / 趴也不出现")
        self.settings.follow.click()
        self.settings.finish_page_anim()
        self.assertFalse(self.settings.posture_section.isVisibleTo(self.settings), "鼠标跟随不管姿势行")
        self.settings.dynamic.click()
        self.settings.finish_page_anim()
        self.assertTrue(self.settings.posture_section.isVisibleTo(self.settings), "关掉又回来")
        self.assertTrue(self.settings.posture_buttons["standing"].isChecked(), "高亮还是选的那个")

    def open_play_options(self):
        """开灵动交互、点调节图标把子选项展开，动画走完。"""
        s = self.settings
        s.show()
        if not self.win.dynamic:
            s.dynamic.click()
        s.finish_page_anim()
        if not s.play_collapse.is_open:
            s.play_options_btn.click()
        s.finish_page_anim()
        self.app.processEvents()
        return s

    def test_dynamic_row_has_a_tune_icon_left_of_the_switch_that_opens_the_options(self):
        """灵动交互不只有开和关。开关左边一颗调节图标，灵动交互开着才有；
        点开这一行下面滑出几条子选项、卡片变长，再点收起。展开没展开不存盘。"""
        from PySide6.QtWidgets import QLabel
        from widget import prefs
        from widget.widgets import FlatIcon, Switch
        s, w = self.settings, self.win
        s.show()
        icon, block = s.play_options_btn, s.play_collapse
        self.assertIsInstance(icon, FlatIcon)
        self.assertEqual(icon.kind, "tune", "三根横线各带一个小圆点")
        self.assertFalse(w.dynamic)
        self.assertFalse(icon.isVisibleTo(s), "灵动交互关着：没有图标")
        self.assertFalse(block.is_open)
        s.dynamic.click()
        s.finish_page_anim()
        self.app.processEvents()
        self.assertTrue(icon.isVisibleTo(s), "灵动交互开着才出现")
        row = s.dynamic.parentWidget()
        self.assertIs(icon.parentWidget(), row)
        title = row.findChild(QLabel)
        self.assertEqual(title.text(), "Dynamic interaction")
        self.assertGreater(icon.x(), title.x(), "在字的右边")
        self.assertLessEqual(icon.geometry().right(), s.dynamic.x(), "在开关左边")
        self.assertEqual(s._tips[icon], "Interaction options")
        self.assertFalse(block.is_open, "默认收起")
        self.assertFalse(icon.isChecked())
        page = s.main_page.layout()
        self.assertLess(page.indexOf(row), page.indexOf(block))
        self.assertLess(page.indexOf(block), page.indexOf(s.posture_collapse), "在灵动交互那一行正下面、动作那一块前面")
        closed = s.height()
        switch_x = s.dynamic.mapTo(s, s.dynamic.rect().topLeft()).x()
        icon.click()
        self.assertTrue(block.animating, "展开有动画")
        s.finish_page_anim()
        self.app.processEvents()
        self.assertTrue(block.is_open)
        self.assertTrue(icon.isChecked(), "展开着图标是按下的样子")
        rows = [r for r in (block.content.layout().itemAt(i).widget() for i in range(block.content.layout().count()))]
        self.assertEqual([r.findChild(QLabel).text() for r in rows], [o.label for o in prefs.PLAY_OPTIONS])
        self.assertEqual([r.findChild(QLabel).text() for r in rows], ["Window interaction"],
                         "只有一条「窗口交互」；拎起来扔出去、随鼠标转身永远开着，没有「捡球」")
        self.assertEqual(block.content.layout().contentsMargins().left(), 18, "缩进 18")
        for r, option in zip(rows, prefs.PLAY_OPTIONS):
            sw = r.findChild(Switch)
            self.assertIs(sw, s.play_switches[option.key])
            self.assertTrue(sw.isVisibleTo(s))
            self.assertTrue(sw.isChecked(), "默认都开")
            self.assertEqual(sw.mapTo(s, sw.rect().topLeft()).x(), switch_x, "小开关和上面的开关右边对齐")
            self.assertEqual(s._tips.get(r, ""), option.tip, "写了说明的子行停在字上浮出说明（窗口交互）")
        self.assertGreaterEqual(s.height(), closed + rows[0].height(), "卡片变长")
        self.assertFalse(s.posture_section.isVisibleTo(s), "动作行这时不在")
        icon.click()
        self.assertTrue(block.animating, "收起也有动画")
        s.finish_page_anim()
        self.app.processEvents()
        self.assertFalse(block.is_open)
        self.assertFalse(icon.isChecked())
        self.assertEqual(s.height(), closed, "收起回到原来的高度")
        self.assertFalse(any("open" in key or "option" in key for key in w.settings.values), "展开没展开不存盘")
        self.assertFalse(any("open" in key for key in prefs.DEFAULTS))

    def test_play_option_switches_are_wired_to_the_settings(self):
        """子选项（窗口交互）连着一个全局的设置项，默认开。拎起来扔出去、随鼠标转身、捡球没有开关（永远开着；捡球有进圈那一层管着）：
        设置表里没有那几个键，旧设置里存过的关不掉它们。"""
        from widget import prefs
        s, w = self.open_play_options(), self.win
        self.assertEqual([o.key for o in prefs.PLAY_OPTIONS], ["hop_windows"])
        for option in prefs.PLAY_OPTIONS:
            self.assertIs(prefs.DEFAULTS[option.key], True, option.key)
            self.assertNotIn(option.key, prefs.PER_PET, "全局的，不跟同桌走")
            self.assertIs(getattr(w, option.attr), True)
            sw = s.play_switches[option.key]
            sw.click()
            self.assertIs(getattr(w, option.attr), False, option.key)
            self.assertIs(w.settings.values[option.key], False, option.key)
            self.assertIs(w.prefs.get(option.key), False)
            sw.click()
            self.assertIs(getattr(w, option.attr), True, option.key)
            self.assertIs(w.settings.values[option.key], True)
        for gone in ("auto_turn", "throw_dog", "turn_to_pointer", "fetch"):
            self.assertNotIn(gone, prefs.DEFAULTS, "没有这个设置项：读不到、写不了")
            if gone != "fetch":
                self.assertFalse(hasattr(w, gone + "_on"))
            self.assertNotIn(gone, s.play_switches)
        self.assertIs(w.fetch_on, True, "捡球的总闸还在窗口上，一直开着（单测拿它让狗只看着）")
        self.assertFalse(hasattr(w, "set_fetch"), "没有入口能关它")

    def test_the_ball_is_the_same_switch_on_the_toolbar_the_things_page_and_its_right_click(self):
        """小球是一件道具——道具栏那一颗、「物件」页「玩具」那一格、右键球的「我不要小球了」是同一个开关，哪处改了别处跟着变。"""
        from widget.hovermenu import tool_id
        from widget.things import BALL_KEY
        s, w = self.open_play_options(), self.win
        self.assertTrue(w.ball_out, "默认拿出来")
        self.assertTrue(w.hover._is_selected(tool_id(BALL_KEY)))
        s.show_page("things", animated=False)
        s.finish_page_anim()
        page = s.things_page
        tile = page.tiles[BALL_KEY]
        self.assertEqual(tile.accessibleName(), "Ball", "名字叫「小球」")
        self.assertTrue(tile.on)
        self.assertTrue(tile.pin.pinned, "默认钉在道具栏里")
        w._build_ball_menu()._act()                              # 右键球的「我不要小球了」点了走的就是它
        s.sync()
        self.assertFalse(tile.on, "「物件」页跟着变")
        self.assertFalse(w.hover._is_selected(tool_id(BALL_KEY)), "道具栏读的是同一个")
        tile.click()
        self.assertTrue(w.ball_out, "「物件」页上点一下拿出来")
        tile.pin.click()
        self.assertFalse(w.tool_pinned(BALL_KEY), "点勾选圈：从道具栏取下")
        self.assertTrue(tile.on, "点勾选圈不算点这一格")
        tile.pin.click()
        self.assertTrue(w.tool_pinned(BALL_KEY))

    def test_the_toolbar_check_is_a_filled_accent_circle_when_on_and_the_page_says_what_it_means(self):
        """每一格右上角一个勾选圈：勾上的强调色实心（跟卡片换强调色），没勾的米白底；最上面一行灰字说勾了是什么意思。"""
        from PySide6.QtGui import QColor
        from widget import sticker, things_page
        from widget.things import BALL_KEY
        s, w = self.open_play_options(), self.win
        s.show_page("things", animated=False)
        s.finish_page_anim()
        page = s.things_page
        self.assertEqual(page.hint.text(), "Checked ones show up next to ···, up to 4")
        tile = page.tiles[BALL_KEY]
        check = tile.pin
        self.assertIsInstance(check, things_page.ToolCheck)
        self.assertGreaterEqual(check.width(), 24, "可点范围够大")
        self.assertTrue(tile.rect().contains(check.geometry()), "在格子里面")
        self.assertGreater(check.geometry().center().x(), tile.width() * 0.7, "右上角")
        self.assertLess(check.geometry().center().y(), tile.height() * 0.3)

        def inside():                                            # 圈里离勾远一点的地方
            img = check.grab().toImage()
            dpr = img.devicePixelRatio()
            c = check.rect().center()
            return img.pixelColor(round(c.x() * dpr), round((c.y() - 0.55 * things_page.CHECK_D / 2) * dpr))

        def near(a, b):
            return max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) <= 12

        self.assertTrue(check.pinned)
        self.assertTrue(near(inside(), QColor(w.accent_color())), f"勾上：强调色实心 {inside().name()} / {w.accent_color()}")
        check.click()
        self.assertFalse(check.pinned)
        paper = QColor(sticker.PAPER_2 if sticker.is_dark() else sticker.PAPER)
        self.assertTrue(near(inside(), paper), f"没勾：米白底 {inside().name()}")
        check.click()
        s._show_accent(QColor("#3A7D44"), QColor("#FFFFFF"))
        self.assertTrue(near(inside(), QColor("#3A7D44")), "跟卡片换强调色")

    def test_turning_dynamic_off_closes_the_options_and_a_rebuilt_card_keeps_them_open(self):
        """灵动交互关掉：图标淡出，展开着的子选项一起收起，动作行出来；再开回来是收着的。展开着时换外观 / 语言重建卡片：还展开着（程序开着就记着）。"""
        s, w = self.open_play_options(), self.win
        self.assertTrue(w.play_options_open)
        w.rebuild_panels()
        new = w.settings_panel
        self.settings = new                                      # tearDown 关新的
        new.finish_page_anim()
        self.assertIsNot(new, s)
        self.assertTrue(new.play_collapse.is_open, "重建的卡片还展开着")
        self.assertTrue(new.play_options_btn.isChecked())
        s = new
        s.dynamic.click()                                        # 关灵动交互
        self.assertFalse(w.dynamic)
        self.assertTrue(s.play_collapse.animating, "跟着收起，有动画")
        s.finish_page_anim()
        self.app.processEvents()
        self.assertFalse(s.play_collapse.is_open)
        self.assertFalse(s.play_options_btn.isVisibleTo(s), "图标也没了")
        self.assertFalse(s.play_options_btn.isChecked())
        self.assertFalse(w.play_options_open)
        self.assertTrue(s.posture_section.isVisibleTo(s), "动作行出来了")
        s.dynamic.click()
        s.finish_page_anim()
        self.assertTrue(s.play_options_btn.isVisibleTo(s))
        self.assertFalse(s.play_collapse.is_open, "再开灵动交互：收着的")
        w.set_dynamic(False)                                     # 从别处关的（sync 对齐）
        s.sync()
        s.finish_page_anim()
        self.assertFalse(s.play_options_btn.isVisibleTo(s))

    def test_play_options_fit_the_card_in_both_languages(self):
        """子选项的字一行放得下（中文、英文），不被开关挤掉；图标的悬停说明有中文。"""
        from PySide6.QtWidgets import QLabel
        from widget import i18n, prefs
        w = self.win
        for lang in ("en", "zh"):
            w.set_language(lang)
            self.settings = w.settings_panel
            s = self.open_play_options()
            one_line = s.dynamic.parentWidget().findChild(QLabel).height()
            for option in prefs.PLAY_OPTIONS:
                label = s.play_switches[option.key].parentWidget().findChild(QLabel)
                self.assertEqual(label.text(), i18n.tr(option.label))
                self.assertGreaterEqual(label.width(), label.sizeHint().width(), (lang, label.text()))
                self.assertEqual(label.height(), one_line, (lang, label.text()))
        for en, zh in (("Interaction options", "灵动交互的选项"), ("Window interaction", "窗口交互"),
                       ("When it can, your deskmate hops onto windows", "条件允许时，同桌会跳上窗口")):
            self.assertEqual(i18n.ZH[en], zh)
        for gone in ("Throw the dog", "Turn with the pointer", "Jump onto windows", "Windows as platforms", "Fetch the ball", "Fetch",
                     "Show widget in all screens"):
            self.assertNotIn(gone, i18n.ZH, "去掉的几条、改掉的旧名字不留文案")
        self.assertEqual(s._tips[s.play_options_btn], "灵动交互的选项")

    def test_half_dial_pops_out_of_the_posture_row_and_its_hands_turn(self):
        import math
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent, QWheelEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.settings.show()
        self.settings.move(screen.left() + 40, screen.top() + 40)
        self.settings.follow.click()                                  # 实时动态关着才有姿势行和 ›
        self.settings.finish_page_anim()
        w0, main_h0 = self.settings.width(), self.settings._main.height()
        main_at = self.settings._main.mapToGlobal(QPoint(0, 0))
        dial = self.settings.dial
        self.assertFalse(dial.isVisible())
        self.settings.actions_toggle.click()                          # 点 ›：半个表从箭头右边露出来
        self.assertTrue(self.settings.side_open)
        self.assertEqual(self.settings.dock.anim.state(), self.settings.dock.anim.State.Running, "按钮点出来的是带动画的（clicked 的布尔参数不能塞进 animated）")
        self.assertEqual(self.settings.width(), w0 + dial.width() - dial.overlap, "窗口先撑出表盘的地方")
        self.assertEqual(self.settings._main.height(), main_h0, "主叶高度按自己的宽量，不被撑宽的窗口影响（不然底部被裁）")
        self.settings.dock.finish_now()                               # 弹出动画立刻走完（不真等）
        self.assertGreaterEqual(dial.progress, 1.0)
        self.assertTrue(dial.isVisible())
        self.assertAlmostEqual(dial.y() + dial.height() / 2, self.settings.side_anchor_y(), delta=2, msg="圆心对着姿势行")
        self.assertAlmostEqual(dial.x() + dial.hub().x(), 22 + self.settings.dock.main_w, delta=1, msg="圆心在卡片的边上")
        from widget import sticker
        from widget.dial import CARD_CLEAR, R_MAX, RADIUS_RATIO
        room = self.settings.side_room() - CARD_CLEAR
        self.assertAlmostEqual(dial.R, min(R_MAX, RADIUS_RATIO * self.settings._main.height(), room), delta=2,
                               msg="表盘直径 ≈ 主页面高度的 0.88，最大 157；表沿离卡片上下边至少 CARD_CLEAR")
        self.assertEqual(dial.R, R_MAX, "动作行排第二，落在卡片正中，上下都放得下最大的那一档")
        self.assertGreater(CARD_CLEAR, sticker.RADIUS, "留的边比卡片的圆角大：表盘的头不从圆角那里露出来")
        anchor = self.settings.side_anchor_y() - 22
        self.assertGreaterEqual(min(anchor - dial.R, main_h0 - anchor - dial.R), CARD_CLEAR, "表沿离卡片上下边都至少 CARD_CLEAR")
        self.assertLessEqual(abs(anchor - main_h0 / 2), 24, "圆心在卡片正中附近：往正右展开（"
                                                           "动作行比正中低了约 21，多出来的地方在表盘上面：离上边 72、下边 30）")
        self.assertGreaterEqual(dial.r_text, 34, "文字起点离圆心够远，相邻两根的字头不叠")
        self.assertAlmostEqual(dial.R - dial.r_out, dial.r_text - 4.0, msg="外端留一样多的边：字块居中在半径正中（不然整体偏右）")
        self.assertEqual(dial.step, 30.0, "间距拉大到 30°")
        self.assertEqual(dial.font_px, 13, "英文 13 号（中文 15）")
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(dial._font(True))
        start, width, lines = dial.layout_label("Howl", fm)
        self.assertEqual(lines, ["Howl"])
        self.assertAlmostEqual(start + width / 2, dial.r_center, delta=0.6, msg="短的名字以 r_center 为中心，不贴圆心")
        self.assertAlmostEqual(dial.r_center, 0.46 * dial.R, delta=0.6, msg="字块中心在 0.46 R：半圆的视觉重心比半径正中靠圆心")
        start2, width2, lines2 = dial.layout_label("Side-lie a while", fm)
        self.assertEqual(len(lines2), 2, "放不下的英文按词折两行、字不缩")
        self.assertAlmostEqual(start2 + width2 / 2, dial.r_center, delta=0.6, msg="两行的也以同一个中心居中")
        self.assertGreaterEqual(start2, dial.r_text)
        self.assertLessEqual(start2 + width2, dial.r_out + 0.6)
        self.assertEqual(dial.layout_label("仰头叫", fm)[2], ["仰头叫"])
        self.assertGreaterEqual(self.settings.dock.dy, 0)
        self.assertEqual(self.settings._main.mapToGlobal(QPoint(0, 0)), main_at, "卡片本身在屏幕上没动")
        self.assertEqual(self.settings.actions_toggle.symbol, "forward", "矢量箭头永远指右（表盘永远在右边）")
        self.assertEqual(self.settings.actions_toggle.text(), "", "不用字体里的›字符定位箭头")
        self.assertTrue(self.settings.actions_toggle.isChecked(), "开着时按钮按下态")
        order = [a.group for a in dial.items]
        self.assertEqual([g for i, g in enumerate(order) if i == 0 or order[i - 1] != g], ["rest", "move", "body", "nose", "pose"], "按手机页的五组顺序排")
        self.assertEqual([order.index(g) for g in ("rest", "move", "body", "nose", "pose")], [0, 5, 15, 22, 26], "每组从第几根开始")
        self.assertEqual(len(dial.items), 28)
        self.assertNotIn("long_jump", [a.id for a in dial.items], "没有跳远、高跳")
        self.assertEqual((dial.first, dial.last), (0, 27), "上下有边界：第一项到最后一项")
        self.assertAlmostEqual(dial.angle(5) - dial.angle(4), dial.step, msg="组和组之间不留空隙：一格一根、等距")
        self.assertFalse(hasattr(dial, "group_angle"), "没有组间的长刻度 / 胶囊")
        self.assertEqual(dial.current_id(), "look_up")
        done = []
        self.win.dog.do_action = lambda aid: done.append(aid)
        hub = dial.hub()
        reach = 0.7 * dial.R
        front = QPointF(hub.x() + reach, hub.y())                     # 正前方那根指针上的一点
        def wheel(notches):
            ev = QWheelEvent(front, QPointF(dial.mapToGlobal(front.toPoint())), QPoint(0, 0), QPoint(0, -120 * notches), Qt.NoButton,
                             Qt.NoModifier, Qt.NoScrollPhase, False)
            dial.wheelEvent(ev)
        wheel(1)                                                      # 鼠标滚轮往下一格
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual(dial.current_id(), "look_around", "滚一格到下一项")
        self.assertEqual(done, ["look_around"], "停到哪根直接做，不用再点")
        wheel(-5)                                                     # 往上滚 5 格：到头就停在第一项
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual(dial.current_id(), "look_up", "有边界，不绕圈")
        self.assertEqual(done, ["look_around", "look_up"])
        wheel(-1)
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual(done, ["look_around", "look_up"], "停在同一根不重复做")
        def mev(kind, pos, buttons=Qt.LeftButton):
            return QMouseEvent(kind, pos, QPointF(dial.mapToGlobal(pos.toPoint())), Qt.LeftButton, buttons, Qt.NoModifier)
        up = QPointF(front.x(), front.y() - 2 * dial.px_per_item)
        dial.mousePressEvent(mev(QEvent.MouseButtonPress, front))
        dial.mouseMoveEvent(mev(QEvent.MouseMove, up))
        dial.mouseMoveEvent(mev(QEvent.MouseMove, up))                # 停住再松手：没有甩
        dial.mouseReleaseEvent(mev(QEvent.MouseButtonRelease, up, Qt.NoButton))
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual(dial.current_id(), "bow_bark", "往上拖两格的表沿长度 = 两格")
        self.assertEqual(done[-1], "bow_bark")
        n = len(done)
        dial.mousePressEvent(mev(QEvent.MouseButtonPress, front))
        dial.mouseReleaseEvent(mev(QEvent.MouseButtonRelease, front, Qt.NoButton))
        self.assertEqual(done[-1], "bow_bark")
        self.assertEqual(len(done), n + 1, "点当前这根：再做一次")
        self.assertTrue(dial._bar.isActive(), "执行后进度条开始刷新")
        a = math.radians(dial.step)                                        # 下面一根（顺时针一格）
        nxt = QPointF(hub.x() + reach * math.cos(a), hub.y() + reach * math.sin(a))
        self.assertEqual(dial.items[dial.hand_at(nxt)].id, "yawn")
        dial.mousePressEvent(mev(QEvent.MouseButtonPress, nxt))
        dial.mouseReleaseEvent(mev(QEvent.MouseButtonRelease, nxt, Qt.NoButton))
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual(dial.current_id(), "yawn", "点别的那根：转过去")
        self.assertEqual(done[-1], "yawn", "转到就做")
        self.assertEqual(dial.current, 3)
        self.assertAlmostEqual(dial.angle(4), 1.0 * dial.step, places=6)
        self.assertAlmostEqual(dial.angle(5), 2.0 * dial.step, places=6, msg="下一组（移动）的第一根紧挨着上一组的最后一根，中间不空")
        between = QPointF(hub.x() + reach * math.cos(math.radians(1.5 * dial.step)), hub.y() + reach * math.sin(math.radians(1.5 * dial.step)))   # 两根正中间
        self.assertIsNone(dial.hand_at(between), "点在两根正中间：不算任何一根")
        n = len(done)
        dial.mousePressEvent(mev(QEvent.MouseButtonPress, between))
        dial.mouseReleaseEvent(mev(QEvent.MouseButtonRelease, between, Qt.NoButton))
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual((dial.current_id(), len(done)), ("yawn", n), "点在两根之间：不选不做")
        wheel(100)                                                    # 往下滚到头
        dial.settle_now()                                             # 对齐 + 执行立刻走完（不真等）
        self.assertEqual(dial.current_id(), "picking_up", "最后一项在下端")
        self.settings.actions_toggle.click()                          # 再点收回
        self.settings.dock.finish_now()
        self.assertFalse(self.settings.side_open)
        self.assertFalse(dial.isVisible())
        self.assertFalse(self.settings.actions_toggle.isChecked())
        self.assertEqual(self.settings.width(), w0, "收完窗口缩回")
        self.assertEqual(self.settings._main.mapToGlobal(QPoint(0, 0)), main_at, "收完卡片还在原地")
        self.settings.move(screen.right() - w0 - 10, screen.top() + 40)   # 右边放不下：还是往右弹，整张卡片左移补齐（永远不在左边弹）
        x1 = self.settings.x()
        self.settings.toggle_actions(animated=False)
        self.assertLess(self.settings.x(), x1 - 50, "窗口左移让出表盘")
        self.assertLessEqual(self.settings.frameGeometry().right(), screen.right(), "不出屏幕")
        self.assertAlmostEqual(dial.x() + dial.hub().x(), 22 + self.settings.dock.main_w, delta=1, msg="圆心还在卡片右边的边上")
        self.settings.dynamic.click()                                 # 灵动交互一开：姿势行藏起来，表盘也收
        self.assertFalse(self.settings.side_open)
        self.assertEqual(self.settings.x(), x1, "收完窗口回到原位")
        self.settings.dynamic.click()
        self.win.open_actions()
        self.settings.dock.finish_now()                               # 弹出动画立刻走完（不真等）
        self.assertTrue(self.settings.side_open)

    def test_dial_labels_push_outward_instead_of_overlapping_their_neighbours(self):
        """相邻两根的字撞了就往外推（当前那根连长条一起算），中英文同一个规则。
        中英文各 28 格逐个转到正前方（也查转到一半）都不叠；当前那根的长条离表沿上的小三角至少 4 像素；折不折行按粗体量，转到正前方不变形。"""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath, QTransform
        from widget import i18n
        from widget.dial import DialPane

        def area(path):
            poly = path.toFillPolygon()
            pts = [(poly[i].x(), poly[i].y()) for i in range(poly.size())]
            return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2

        for lang in ("en", "zh"):
            i18n.set_language(lang)
            dial = DialPane(self.win)
            dial.fit_to(331)                                          # 主页面约 331 → 半径 146
            ids = [a.id for a in dial.items]
            for pos in [p / 2 for p in range(2 * dial.last + 1)]:
                dial.pos_ = pos
                labels = dial.labels()
                shapes = {}
                for i, lab, _alpha in dial.drawn_labels():                # 画出来的都查（一直到 ±90°，转动时淡进来的那根也算）
                    r = QPainterPath()
                    if lab.pill:
                        r.addRoundedRect(QRectF(lab.start - lab.pad, -lab.thick / 2, lab.width + 2 * lab.pad, lab.thick), lab.thick / 2, lab.thick / 2)
                    else:
                        r.addRect(QRectF(lab.start, -lab.thick / 2, lab.width, lab.thick))
                    shapes[i] = QTransform().rotate(dial.angle(i)).map(r)
                for i in shapes:
                    if i + 1 in shapes:
                        self.assertLess(area(shapes[i].intersected(shapes[i + 1])), 1.0, f"{lang} 转到 {pos}：{ids[i]} 和 {ids[i + 1]} 叠了")
                if pos == int(pos):
                    cur = labels[int(pos)]
                    self.assertLessEqual(cur.start + cur.width + cur.pad, dial.R - 7.0 - 4.0, f"{lang} {ids[int(pos)]}：长条离小三角至少 4 像素")
            dial.pos_ = float(ids.index("stretch_front"))
            here = len(dial.labels()[ids.index("stretch_front")].lines)
            dial.pos_ += 1.0
            self.assertEqual(len(dial.labels()[ids.index("stretch_front")].lines), here, "转到正前方变粗也不会突然折行")
        i18n.set_language("en")
        dial = DialPane(self.win)
        dial.fit_to(331)
        self.assertEqual(dial.wrap_label("Stretch front"), ["Stretch", "front"], "按粗体量放不下：两行")
        dial.pos_ = float([a.id for a in dial.items].index("stretch_front"))
        cur = dial.labels()[int(dial.pos_)]
        self.assertGreater(cur.start + cur.width / 2, dial.r_center + 10, "截图那一格：两行的当前项被邻居推到外面")

    def test_dial_text_fades_in_by_angle_and_switching_actions_never_jumps(self):
        """转动时新字直接冒出来 —— 只画 ±60° 以内的话，那里还有三成浓度；所以一直画到 ±90°，浓度随角度连续变到 0。
        直接点相邻的动作时进度条闪一下、新字往左跳 —— 之前旧动作的进度条一帧消失；现在点了就让它在对齐的 0.18 秒里淡出让位，
        "选中 → 计时"按时间过渡：转动、停稳、开始做，新字的位置和长条的浓度都不跳。"""
        from PySide6.QtCore import QEasingCurve
        from widget.dial import BAR_FADE, DialPane
        dial = DialPane(self.win)
        dial.fit_to(331)
        dial.progress = 1.0
        prev = None
        for k in range(301):                                             # 从第 5 格慢慢转到第 11 格
            dial.pos_ = 5.0 + k * 0.02
            now = {i: alpha for i, _lab, alpha in dial.drawn_labels()}
            for i in set(prev or {}) | set(now) if prev is not None else ():
                self.assertLess(abs(now.get(i, 0.0) - prev.get(i, 0.0)), 0.02, f"第 {i} 根的浓度跳了")
            prev = now
        dial.pos_ = 8.0
        self.assertEqual(sorted(round(a, 2) for _i, _l, a in dial.drawn_labels() if a > 0.01), [0.33, 0.33, 0.67, 0.67, 1.0], "停稳时看得见的还是 5 根")
        dial.pos_ = 8.5
        self.assertTrue(any(0.0 < a < 0.2 for _i, _l, a in dial.drawn_labels()), "转到一半：新字已经淡淡地进来了")

        self.win.set_follow_cursor(True)                                  # 互动模式里表盘才做动作
        ids = [a.id for a in dial.items]
        i = ids.index("stretch_front")
        dial.pos_ = float(i)
        dial._settled()                                                   # 停在 Stretch front 上：开始做
        self.assertEqual(self.win.dog.manual_progress()[0], "stretch_front")
        tints = []
        for _ in range(12):
            dial.step_bars(BAR_FADE / 10)
            tints.append(dial.pill_tints(dial.labels()[i], 1.0))
        for a, b in zip(tints, tints[1:]):
            self.assertLess(abs(a[0] - b[0]) + abs(a[1] - b[1]), 0.07, "选中 → 计时：0.18 秒里一帧一帧变过去（之前一帧就跳 0.58），不闪")
        self.assertAlmostEqual(tints[-1][1], 0.42, places=2)
        dial.snap(i + 1)                                                  # 直接点下面那根 Sniff the ground
        dial._snap.stop()
        self.assertEqual(dial._leaving, "stretch_front", "点了别的：正在做的进度条开始让位")
        curve = QEasingCurve(QEasingCurve.OutCubic)
        starts = []
        for f in range(1, 11):                                           # 对齐转动 0.18 秒
            dial.pos_ = i + curve.valueForProgress(f / 10)
            dial.step_bars(BAR_FADE / 10)
            starts.append(dial.labels()[i + 1].start)
        self.assertNotIn("stretch_front", dial._bar_w, "转到位时旧进度条已经淡完")
        dial.pos_ = float(i + 1)
        before = dial.labels()[i + 1].start
        dial._settled()                                                   # 停稳：开始做 Sniff the ground
        self.assertEqual(self.win.dog.manual_progress()[0], "stretch_back")
        dial.step_bars(BAR_FADE / 2)
        self.assertAlmostEqual(dial.labels()[i + 1].start, before, delta=0.5, msg="开始做的那一刻新字不往回跳（之前往左 8 像素）")
        for a, b in zip(starts, starts[1:]):
            self.assertLess(abs(a - b), 4.0, "转动时新字的位置连续")
        dial.step_bars(BAR_FADE)                                          # 滚轮 / 拖动转走（还没停稳、动作照做）：进度条淡出，转回来再淡入
        dial.pos_ = i + 1.6
        dial.step_bars(BAR_FADE)
        self.assertEqual(self.win.dog.manual_progress()[0], "stretch_back")
        self.assertNotIn("stretch_back", dial._bar_w, "转走就淡出，不挂到做完")
        dial.pos_ = float(i + 1)
        dial.step_bars(BAR_FADE)
        self.assertAlmostEqual(dial._bar_w.get("stretch_back", 0.0), 1.0, msg="转回来再淡入")

    def test_cards_open_diagonally_away_from_the_dog_and_the_dial_stays_clear(self):
        """设置卡片放在狗的斜对面朝屏幕中心那边（右上 → 左下，左上 → 右下，左下 → 右上，右下 → 左上），
        表盘永远往右弹，打开后不盖到狗。"""
        from PySide6.QtCore import QRect
        from PySide6.QtWidgets import QApplication
        from widget.sticker import SHADOW
        ag = QApplication.primaryScreen().availableGeometry()
        s = self.settings
        self.win.show()
        self.win.set_follow_cursor(True)                              # 有姿势行和表盘
        dog_w, dog_h = self.win.width(), self.win.height()
        corners = {"top-right": (ag.right() - dog_w, ag.top()), "top-left": (ag.left(), ag.top()),
                   "bottom-left": (ag.left(), ag.bottom() - dog_h), "bottom-right": (ag.right() - dog_w, ag.bottom() - dog_h)}
        for name, (dx, dy) in corners.items():
            self.win.move(dx, dy)
            dog = self.win.frameGeometry()
            self.win.open_settings()
            self.app.processEvents()
            card = QRect(s.x() + SHADOW, s.y() + SHADOW, s.width() - 2 * SHADOW, s.height() - 2 * SHADOW)
            self.assertFalse(card.intersects(dog), f"{name}：卡片不压狗")
            self.assertTrue(ag.contains(card), f"{name}：卡片在屏幕里")
            if "right" in name:
                self.assertLessEqual(card.right(), dog.left(), f"{name}：狗在右边，卡片在狗左边")
            else:
                self.assertGreaterEqual(card.left(), dog.right(), f"{name}：狗在左边，卡片在狗右边")
            if "top" in name:
                self.assertGreaterEqual(card.top(), dog.bottom(), f"{name}：狗在上面，卡片往下伸")
            else:
                self.assertLessEqual(card.bottom(), dog.top(), f"{name}：狗在下面，卡片往上伸")
            s.toggle_actions(animated=False)
            self.app.processEvents()
            d = s.dial
            dial_rect = QRect(d.mapToGlobal(d.rect().topLeft()), d.size())
            self.assertFalse(dial_rect.intersects(dog), f"{name}：表盘不盖狗")
            self.assertGreater(dial_rect.left(), card.left(), f"{name}：表盘在卡片右边")
            s.toggle_actions(animated=False)
            self.app.processEvents()
            s.hide()

    def test_hint_texts_are_hover_tips_not_grey_lines(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QLabel
        from widget.widgets import sticker_tip
        self.settings.show()
        text = "Watches the pointer from afar"
        self.assertFalse(any(w.text() == text for w in self.settings.findChildren(QLabel)), "灰字描述不再占一行")
        row = self.settings.follow.parentWidget()
        self.assertEqual(self.settings._tips[row], text)
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPoint
        from widget import card
        s = self.settings
        s.show()
        QApplication.processEvents()
        label = s._tip_beside(row)
        on_text = label.mapToGlobal(QPoint(10, label.height() // 2))                       # 文字上
        on_switch = s.follow.mapToGlobal(QPoint(s.follow.width() // 2, s.follow.height() // 2))  # 开关上
        zone = s._tip_zone(row)
        self.assertTrue(zone.contains(on_text) and not zone.contains(on_switch), "触发区只有文字那一段（不要按钮和按钮旁边）")
        self.assertLess(zone.right(), on_switch.x())
        def move(w, x):
            p = QPointF(x, 5)
            QApplication.sendEvent(w, QMouseEvent(QEvent.MouseMove, p, QPointF(w.mapToGlobal(p.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        with mock.patch.object(card.QCursor, "pos", staticmethod(lambda: on_text)):
            QApplication.sendEvent(row, QEvent(QEvent.Enter))
            self.assertEqual(s._tip_timer.interval(), 500, "要停满 0.5 秒")
            self.assertTrue(s._tip_timer.isActive(), "从文字进了这一行开始计时")
            self.assertFalse(sticker_tip().isVisible())
            move(row, 40)                                               # 还在文字上动：重新计时
            self.assertTrue(s._tip_timer.isActive(), "动过了，从头数 0.5 秒")
            s._tip_timer.stop()
            s._show_tip()                                               # 计时器到点（不真等）
            self.assertTrue(sticker_tip().isVisible(), "停下不动满 0.5 秒才浮出说明")
            self.assertEqual(sticker_tip().text, text)
            move(row, 40)
            self.assertTrue(sticker_tip().isVisible(), "出来之后在文字上小幅移动不收")
            self.assertTrue(s._tip_watch.isActive(), "显示期间盯着鼠标位置")
            s._check_tip()
            self.assertTrue(sticker_tip().isVisible(), "鼠标还在文字上：不收")
        move(s.follow, 3)                                               # 移到开关上：收
        self.assertFalse(sticker_tip().isVisible(), "移到开关上就收，要点开关时别挡着")
        self.assertFalse(s._tip_timer.isActive(), "在开关上不计时")
        with mock.patch.object(card.QCursor, "pos", staticmethod(lambda: on_switch)):
            QApplication.sendEvent(row, QEvent(QEvent.Enter))           # 从开关那边进这一行：不计时
            self.assertFalse(s._tip_timer.isActive())
            s._tip_target = row
            s._show_tip()                                               # 就算计时器到点，鼠标不在文字上也不出
            self.assertFalse(sticker_tip().isVisible())
        with mock.patch.object(card.QCursor, "pos", staticmethod(lambda: on_text)):
            QApplication.sendEvent(row, QEvent(QEvent.Enter))
            s._tip_timer.stop()
            s._show_tip()
            self.assertTrue(sticker_tip().isVisible())
        with mock.patch.object(card.QCursor, "pos", staticmethod(lambda: QPoint(-5000, -5000))):
            s._check_tip()                                              # 鼠标一下子甩出了卡片、Qt 没发 Leave：按真实位置收
        self.assertFalse(sticker_tip().isVisible(), "不在文字上就收")
        self.assertFalse(s._tip_watch.isActive())
        with mock.patch.object(card.QCursor, "pos", staticmethod(lambda: on_text)):
            QApplication.sendEvent(row, QEvent(QEvent.Enter))
            s._tip_timer.stop()
            s._show_tip()
            self.assertTrue(sticker_tip().isVisible())
        QApplication.sendEvent(row, QEvent(QEvent.Leave))
        self.assertFalse(sticker_tip().isVisible(), "移开就收")
        self.assertIn(self.settings.custom_swatch, self.settings._tips, "两色圆点的「自定义…」也是贴纸提示，不是系统提示框")
        self.assertEqual(self.settings.custom_swatch.toolTip(), "")

    def test_show_metadata_lives_under_advanced_and_random_actions_are_a_black_box(self):
        self.assertFalse(hasattr(self.win, "set_actions"), "窗口不再记随机动作")      # （QWidget 自带 actions()，不能拿它来查）
        self.assertNotIn("actions", self.win.settings.values)
        self.settings.show()
        self.assertFalse(self.settings.meta.isVisibleTo(self.settings), "显示元数据在高级设置页里，默认在主页面看不到")
        self.settings.show_page("tuning", False)
        self.assertTrue(self.settings.meta.isVisibleTo(self.settings), "元数据是开发用的，在开发者设置页")
        self.assertFalse(self.settings.meta.isChecked())
        self.settings.meta.click()
        self.assertTrue(self.win.show_metadata)
        self.assertEqual(self.win.settings.values["show_metadata"], True)
        self.settings.meta.click()
        self.assertFalse(self.win.show_metadata)

    def test_advanced_is_a_page_with_a_back_arrow(self):
        from PySide6.QtTest import QTest
        self.settings.show()
        self.assertTrue(self.settings.main_page.isVisibleTo(self.settings))
        self.assertFalse(self.settings.advanced_page.isVisibleTo(self.settings), "默认是主页面")
        self.assertEqual(self.settings._tag.lead_mode, "mark", "主页面左上角的圆是 app 图标，不是返回")
        h0 = self.settings.height()
        self.settings.advanced_link.click()                           # 最下面灰字的「高级设置…」
        self.assertTrue(self.settings.advanced_open)
        self.assertTrue(self.settings.height_animating, "高度过渡在走")
        self.settings.finish_page_anim()                              # 高度过渡立刻走完（不真等）
        self.assertTrue(self.settings.advanced_page.isVisibleTo(self.settings))
        self.assertFalse(self.settings.main_page.isVisibleTo(self.settings), "整张卡片只剩高级设置")
        self.assertTrue(self.settings.back.isVisibleTo(self.settings) and self.settings._tag.lead_mode == "back", "左上角是返回")
        self.assertEqual(self.settings._title_label.text(), "Advanced")
        self.assertNotEqual(self.settings.height(), h0, "高度换成了这一页的")
        self.assertEqual(self.settings.height(), self.settings.content_height(), "高度就是高级设置页内容的高度（加了版本行，比主页面高）")
        self.assertTrue(self.settings.power.isVisibleTo(self.settings), "省电模式在这页")
        back, bar = self.settings.back, self.settings._tag
        self.assertEqual(back.width(), 26)
        from PySide6.QtCore import QPoint
        leaf = self.settings._main
        self.assertEqual(back.mapTo(leaf, QPoint(0, 0)), QPoint(16, 16), "返回在左上角：离左边、上边都是 16，和 × 对称")
        capsule_centre = bar.mapTo(leaf, QPoint(0, 0)).x() + bar.tag_rect().center().x()
        self.assertAlmostEqual(capsule_centre, leaf.width() / 2, delta=1,
                               msg="标题胶囊在卡片正中（每一页都居中，换页时胶囊不跑；有新版本胶囊时才靠左，在 ‹ 右边空 INSET）")
        self.settings.meta.click()
        self.assertTrue(self.win.show_metadata)
        self.settings.meta.click()
        self.win.set_dog_name("Bobo")                                  # 在高级设置页改名：回来再显示
        self.assertEqual(self.settings._title_label.text(), "Advanced")
        self.settings.back.click()
        self.settings.finish_page_anim()                              # 高度过渡立刻走完（不真等）
        self.assertFalse(self.settings.advanced_open)
        self.assertTrue(self.settings.main_page.isVisibleTo(self.settings))
        self.assertEqual(self.settings._title_label.text(), "Bobo")
        self.assertEqual(self.settings.height(), h0, "回来高度一样")

    def test_switching_pages_resizes_the_window_once_and_never_out_of_step(self):
        """换页时窗口只改一次大小（变高的一开始长、变矮的走完才缩），
        改大小那一刻卡片画出来的高度、主叶的裁剪都已经是过渡的起点（macOS 改大小时可能当场重画，画的要和上一帧一样）。"""
        from widget import sticker
        s = self.settings
        s.show()
        s.finish_page_anim()
        seen = []
        orig = s.setFixedHeight

        def fixed(h):
            before = s.height()
            orig(h)
            if s.height() != before:
                mask = s._main.mask()
                clip = mask.boundingRect().height() if not mask.isEmpty() else s._main.height()
                seen.append((before, s.height(), s.painted_height(), clip))
        s.setFixedHeight = fixed
        try:
            for go in (lambda: s.show_advanced(True), lambda: s.show_page("coat"), lambda: s.show_page("advanced"),
                       lambda: s.show_advanced(False)):
                seen.clear()
                start = s.height()
                go()
                for before, after, painted, clip in seen:
                    self.assertEqual(painted, start, "改大小那一刻卡片还按上一帧的高度画")
                    self.assertLessEqual(clip, start - 2 * sticker.SHADOW, "主叶已经按上一帧的高度裁好")
                s.finish_page_anim()
                self.assertLessEqual(len(seen), 1, f"一次换页窗口只改一次大小：{seen}")
        finally:
            del s.setFixedHeight

    def test_quit_and_reset_need_a_two_second_hold(self):
        """防误触：重置 / 退出 / 关机键按住 0.6 秒才触发，提前松开不算；按住时进度线在走。"""
        from unittest import mock
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from widget import widgets
        s = self.settings
        s.show()
        fired = []
        self.win._quit = lambda: fired.append("quit")
        def wait(ms):                                             # 不真等：把按下的时刻往前拨，再手动 tick（靠真实计时跑全套会飘）
            for d in (s.quit_button.driver, s.reset_button.driver):
                d._t0 -= ms / 1000.0
            for _ in range(ms // 16 + 1):
                s.quit_button.driver._tick()
                s.reset_button.driver._tick()
        self.assertEqual(widgets.HOLD_MS, 600, "长按 0.6 秒")
        with mock.patch.object(widgets, "HOLD_MS", 300):
            QTest.mousePress(s.quit_button, Qt.LeftButton)
            wait(120)
            self.assertGreater(s.quit_button.driver.progress, 0.1, "按住时进度在走")
            self.assertLess(s.quit_button.driver.progress, 1.0)
            QTest.mouseRelease(s.quit_button, Qt.LeftButton)
            wait(250)
            self.assertEqual(fired, [], "没按满就松开：不退出")
            self.assertEqual(s.quit_button.driver.progress, 0.0, "进度线退回")
            QTest.mousePress(s.quit_button, Qt.LeftButton)
            wait(450)
            self.assertEqual(fired, ["quit"], "按满两秒才退出")
            self.assertEqual(s.quit_button.driver.progress, 0.0, "触发那一刻圈就退回，不等松手")
            wait(400)
            self.assertEqual(fired, ["quit"], "按着不放不会再触发一次")
            QTest.mouseRelease(s.quit_button, Qt.LeftButton)
            self.win.set_scale(2.0)
            s.sync()
            QTest.mouseClick(s.reset_button, Qt.LeftButton)
            wait(50)
            self.assertAlmostEqual(self.win.scale, 2.0, msg="点一下重置没反应")
            QTest.mousePress(s.reset_button, Qt.LeftButton)
            wait(450)
            QTest.mouseRelease(s.reset_button, Qt.LeftButton)
            recommended = self.win.recommended_scale()
            self.assertNotAlmostEqual(recommended, 2.0)
            self.assertAlmostEqual(self.win.world_scale, recommended, msg="长按重置回到这块屏的推荐大小（滑杆上那个小刻度），不是 100%")
            self.assertEqual(s.size_label.text(), f"{math.floor(recommended * 100 + 0.5)}%", "重置也在同一事件里刷新百分比")
            self.assertAlmostEqual(s.size_slider.value, recommended * 100.0)
        self.assertNotIn(s.quit_button, s._tips, "长按按钮没有提示文字")
        self.assertIn(s.reset_button, s._tips, "紧凑重置图标用悬浮说明解释长按操作")
        self.assertTrue(s.reset_button.accessibleName())
        self.assertTrue(s.reset_button.accessibleDescription())

    def test_closing_settings_returns_to_the_main_page_but_rebuilding_keeps_it(self):
        """关掉再打开回主页面；换外观 / 换语言重建卡片时留在当时那一页。"""
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        self.assertEqual(s.page, "advanced")
        self.win.set_language("zh")                                   # 重建：新卡片还在高级设置页
        new = self.win.settings_panel
        self.assertIsNot(new, s)
        self.assertEqual(new.page, "advanced")
        self.assertTrue(new.advanced_page.isVisibleTo(new))
        new.hide()
        self.assertEqual(new.page, "main", "关掉就回主页面")
        new.show()
        self.assertTrue(new.main_page.isVisibleTo(new))
        self.assertEqual(new._tag.lead_mode, "mark", "回到主页面：左上角是 app 图标")
        self.win.set_language("en")

    def test_appearance_has_light_dark_and_system_and_dark_swaps_the_sticker_colours(self):
        """界面要有深色模式，三档放高级设置（浅色 / 深色 / 跟随系统，默认跟随系统）；只换卡片、表盘、菜单、提示、「···」的贴纸颜色，狗不变。"""
        from widget import sticker
        self.addCleanup(lambda: self.win.set_appearance("light"))
        self.addCleanup(lambda: sticker.set_dark(False))
        self.assertEqual(self.win.appearance, "system", "默认跟随系统")
        self.assertFalse(sticker.is_dark(), "离屏平台没有系统深色：浅色")
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        self.assertEqual([m for m, b in s.appearance_buttons.items() if b.isChecked()], ["system"])
        s.appearance_buttons["dark"].click()
        self.assertEqual(self.win.appearance, "dark")
        self.assertEqual(self.win.settings.values["appearance"], "dark")
        self.assertTrue(sticker.is_dark())
        self.assertEqual((sticker.INK, sticker.PAPER), ("#F2F0EC", "#1C1C21"), "描边 / 字变米白、底变深色：菜单、表盘、「···」画的时候都从 sticker 读")
        new = self.win.settings_panel
        self.assertIsNot(new, s, "卡片重建（样式表是建卡片时生成的）")
        self.assertTrue(new.theme.dark)
        self.assertEqual(new.theme.bg.name().upper(), "#1C1C21")
        from PySide6.QtGui import QColor
        accent = QColor(new.theme.accent)
        self.assertGreater(accent.lightnessF(), 0.75, "毛色 1 的强调色是黑的，深色界面里按它自己反转明度成浅灰（不是固定的米白）")
        self.assertNotEqual(new.theme.accent.upper(), "#F2F0EC", "不是退回固定的米白")
        self.assertEqual(new.theme.accent_text, "#1C1C21", "浅强调色上的字是黑：按强调色自己的深浅定，不跟模式走")
        self.assertEqual(new.follow.accent.name(), new.theme.accent, "开关挂上就拿到强调色，不用再点一下毛色")
        self.assertEqual(new.power.accent.name(), new.theme.accent, "高级设置页的开关也是")
        new.show()
        new.show_advanced(True, animated=False)
        self.assertEqual([m for m, b in new.appearance_buttons.items() if b.isChecked()], ["dark"])
        self.win.set_appearance("light")
        self.assertFalse(sticker.is_dark())
        self.assertEqual((sticker.INK, sticker.PAPER), ("#1C1C21", "#F2F0EC"))
        self.win.set_appearance("system")
        self.assertFalse(sticker.is_dark())

    def test_actions_row_has_sleep_and_shows_only_wake_up_while_asleep(self):
        """姿势行叫"动作"，有"睡"；睡着时（含入睡、醒来的动画期间）设置里和「···」旁边都只剩「醒来」，醒来动画放完才回来。"""
        s = self.settings
        self.win.show()
        self.win.move(100, 400)
        s.show()
        s.follow.click()
        self.assertEqual(list(s.posture_buttons), ["standing", "sitting", "lying", "sleeping"])
        self.assertFalse(s.wake_button.isVisibleTo(s))

        def run(seconds):
            for _ in range(int(seconds * 60)):
                self.win.dog.update(1 / 60)
                self.win.dog.frame()
        s.posture_buttons["standing"].click()
        run(6.0)
        self.win.dog.sleep_styles = ("belly",)                           # 趴睡醒来回趴着（侧睡醒来是站着）
        s.posture_buttons["sleeping"].click()
        s.sync()
        self.assertEqual(self.win.rest_posture, "sleeping")
        self.assertTrue(s.wake_button.isVisibleTo(s))
        self.assertFalse(s.wake_button.isEnabled(), "入睡动画没放完先不能点")
        for b in s.posture_buttons.values():
            self.assertFalse(b.isVisibleTo(s))
        self.assertFalse(s.actions_toggle.isVisibleTo(s), "表盘的 › 也藏")
        self.win.hover.alpha, self.win.hover.post_open = 1.0, 1.0
        self.assertEqual([pid for pid, _ in self.win.hover.posture_rects()], ["wake"], "「···」旁边也只有醒来")
        self.win.set_rest_posture("wake")
        self.assertEqual(self.win.rest_posture, "sleeping", "入睡途中点醒来不算")
        run(8.0)
        s.sync()
        self.assertEqual(self.win.dog.sleep_state(), "asleep")
        self.assertTrue(s.wake_button.isEnabled())
        s.wake_button.click()
        s.sync()
        self.assertEqual(self.win.rest_posture, "lying")
        self.assertEqual(self.win.dog.sleep_state(), "waking")
        self.assertTrue(s.wake_button.isVisibleTo(s))
        self.assertFalse(s.wake_button.isEnabled(), "醒来动画放完才回来")
        run(3.0)
        s.sync()
        self.assertEqual(self.win.dog.sleep_state(), "awake")
        self.assertFalse(s.wake_button.isVisibleTo(s))
        self.assertTrue(s.posture_buttons["lying"].isVisibleTo(s) and s.posture_buttons["lying"].isChecked(), "醒来后趴着、高亮在趴")
        self.assertTrue(s.actions_toggle.isVisibleTo(s))
        self.assertEqual([pid for pid, _ in self.win.hover.posture_rects()], ["standing", "sitting", "lying", "sleeping"])

    def test_corner_radii_come_in_two_tiers(self):
        """卡片、「···」菜单、悬浮提示、HUD 一档 22；胶囊控件整圆，图片 8。"""
        from widget import sticker
        self.assertEqual(sticker.RADIUS, 22, "卡片、菜单、HUD 都从 sticker 读同一个")
        self.assertFalse(hasattr(sticker, "RADIUS_MENU"), "菜单没有单独一档")
        self.assertEqual(sticker.RADIUS_TIP, 8, "悬浮提示（对话气泡）和二维码、缩略图一档 8：12 既不是胶囊也不是卡片")
        from widget.widgets import StickerTip
        self.assertEqual((StickerTip.PAD_X, StickerTip.PAD_Y, StickerTip()._font.pixelSize()), (12, 9, 13))

    def test_close_button_is_a_circle_like_the_back_button(self):
        """右上角的 × 和左上角的返回一样是 26 像素的描边圆。"""
        from widget.widgets import IconButton
        s = self.settings
        self.assertIsInstance(s._close, IconButton)
        self.assertEqual((s._close.kind, s._close.width(), s.back.width()), ("close", 26, 26))
        s.show()
        s.finish_page_anim()
        s._close.click()
        self.assertTrue(s.closing, "点 ×：0.12 秒淡出")
        s.finish_page_anim()
        self.assertFalse(s.isVisible(), "淡完就关")

    def test_tips_sit_right_of_the_text_when_they_fit_else_below(self):
        """提示放在这一行文字的右边、和行垂直居中；右边放不下（会盖到开关）才放在行下面。中文短说明在右边，长说明在下面。"""
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication, QLabel
        from widget.card import sticker_tip
        self.win.set_language("zh")
        s = self.win.settings_panel
        s.fit_height()
        s.show()
        QApplication.processEvents()
        tip = sticker_tip()
        row = next(r for r, t in s._tips.items() if t == "远远地看着鼠标")
        label = s._tip_beside(row)
        self.assertIsInstance(label, QLabel)
        s._tip_target = row
        s._tip_timer.stop()
        s._show_tip(force=True)
        self.assertTrue(tip.isVisible())
        self.assertEqual(tip._placed, "beside", "尾巴朝左指着文字")
        text_right = label.mapToGlobal(QPoint(label.sizeHint().width(), 0)).x()
        self.assertGreaterEqual(tip.x() + tip.M, text_right, "在文字右边")
        self.assertLessEqual(tip.x() + tip.width() - tip.M, s.follow.mapToGlobal(QPoint(0, 0)).x(), "没盖到开关")
        row_cy = row.mapToGlobal(QPoint(0, row.height() // 2)).y()
        self.assertLessEqual(abs(tip.y() + tip.height() // 2 - row_cy), 2, "和这一行垂直居中")
        s._hide_tip()
        s.toggle_play_options(animated=False, on=True)            # 灵动交互的选项：「窗口交互」那一行的说明长，右边放不下
        s.finish_page_anim()
        QApplication.processEvents()
        row = next(r for r, t in s._tips.items() if t.startswith("条件允许时"))
        s._tip_target = row
        s._tip_timer.stop()
        s._show_tip(force=True)
        self.assertTrue(tip.isVisible())
        self.assertEqual(tip._placed, "below", "尾巴朝上指着那行字")
        self.assertEqual(tip.y() + tip.M, row.mapToGlobal(QPoint(0, row.height())).y() + tip.GAP_BELOW, "右边放不下：在这一行下面，身体离行底 8（尾巴尖落在行底）")
        self.assertEqual((tip.TAIL, tip.TILT, tip.GAP, tip.GAP_BELOW), (7.0, -2.0, 12, 8))
        s._hide_tip()

    def test_sticker_theme_is_fixed_cream_and_the_accent_follows_the_coat(self):
        from widget.sticker import INK, PAPER, theme
        from widget.coat import CoatSpec
        t = theme()
        self.assertFalse(t.dark, "默认浅色：外观跟随系统，离屏平台没有深色")
        self.assertEqual(t.bg.name().upper(), PAPER)
        self.assertEqual(t.accent.upper(), INK, "没给强调色就是描边黑")
        self.assertTrue(self.win.accent_color().startswith("#"))
        self.win.set_custom_coat(CoatSpec(main="#A0522D", secondary="#F2F0EC"))      # 棕狗：强调色跟主色
        self.assertEqual(self.win.accent_color().lower(), "#a0522d")
        self.assertEqual(self.settings.theme.accent.lower(), "#a0522d", "卡片的强调色跟着换")
        self.assertEqual(self.settings.follow.accent.name().lower(), "#a0522d", "开关开着的填色也跟着")
        from PySide6.QtGui import QColor
        from widget import sticker
        from widget.look import visible_accent
        self.win.set_custom_coat(CoatSpec(main="#F5F5F5", secondary="#FAFAFA"))      # 太浅看不出：按它自己反转明度（不是退回固定的黑）
        self.assertLess(QColor(self.win.accent_color()).lightnessF(), 0.15)
        self.assertNotEqual(self.win.accent_color().upper(), INK)
        self.win.set_coat(1)                                                        # 原装黑白边牧：深色毛是黑的
        self.assertLess(QColor(self.win.accent_color()).lightnessF(), 0.4)
        self.assertEqual(visible_accent(QColor("#A0522D")).name(), "#a0522d", "看得见的不动")
        dark_brown = visible_accent(QColor("#3A2418"))
        self.assertEqual(dark_brown.name(), "#3a2418", "浅色界面里深棕看得见，不动")
        sticker.set_dark(True)
        self.addCleanup(lambda: sticker.set_dark(False))
        light = visible_accent(QColor("#3A2418"))
        self.assertGreater(light.lightnessF(), 0.7, "深色界面里深棕反成浅棕")
        self.assertAlmostEqual(light.hueF(), QColor("#3A2418").hueF(), delta=0.02, msg="色相不变")
        self.assertGreater(visible_accent(QColor("#000000")).lightnessF(), 0.85, "黑反成很浅的灰")
        self.assertGreater(visible_accent(QColor("#000000")).lightnessF(), visible_accent(QColor("#444444")).lightnessF(), "不是固定的浅色：越黑反得越浅")

    def test_language_buttons_always_keep_exactly_one_selection(self):
        from widget import i18n
        self.settings.show()
        current = self.settings.lang_buttons[i18n.current()]
        with mock.patch.object(self.win, "set_language") as change:
            current.click()
            self.assertTrue(current.isChecked(), "再次点当前语言不能取消选中")
            change.assert_not_called()
            other_code = next(code for code in self.settings.lang_buttons if code != i18n.current())
            self.settings.lang_buttons[other_code].click()
            self.assertEqual(sum(b.isChecked() for b in self.settings.lang_buttons.values()), 1)
            self.assertTrue(self.settings.lang_buttons[other_code].isChecked())
            change.assert_called_once_with(other_code)
        self.assertTrue(self.settings._language_group.exclusive())

    @mock.patch("widget.motion.native.reduce_motion", return_value=False)
    def test_initial_and_rebuilt_language_selection_is_visible_without_hover(self, _reduce_motion):
        from widget import i18n
        self.win.tray = None
        for language in ("en", "zh", "en"):
            self.win.set_language(language)
            panel = self.win.settings_panel
            selected = panel.lang_buttons[language]
            self.assertTrue(selected.isChecked())
            self.assertEqual(selected.motion.selection.value, 1, "隐藏构建时设置的选中状态须立即可画，不等待悬停唤醒时钟")
            self.assertEqual(selected.motion.selection.target, 1)
            self.assertTrue(selected.motion.selection.settled)
            self.assertEqual(sum(b.isChecked() for b in panel.lang_buttons.values()), 1)
            for code, button in panel.lang_buttons.items():
                if code != language:
                    self.assertEqual(button.motion.selection.value, 0)
            panel.show()
            panel.finish_page_anim()
            before = self.win.settings_panel
            selected.click()
            self.assertIs(self.win.settings_panel, before, "当前语言不重复重建面板")
            self.assertTrue(selected.isChecked())
            self.assertEqual(selected.motion.selection.value, 1)
        self.assertEqual(i18n.current(), "en")

    def test_language_switch_rebuilds_panels_in_chinese(self):
        from widget import i18n
        self.win.tray = None
        old_settings = self.settings
        try:
            self.win.set_language("zh")
            self.assertEqual(i18n.current(), "zh")
            self.assertIsNot(self.win.settings_panel, old_settings, "面板按新语言重建")
            from PySide6.QtWidgets import QLabel
            self.assertIn("灵动交互", [lab.text() for lab in self.win.settings_panel.findChildren(QLabel)])
            self.assertTrue(self.win.settings_panel.lang_buttons["zh"].isChecked())
            self.assertEqual(self.win.settings_panel.lang_buttons["en"].text(), "English", "选项永远各写自己的文字")
        finally:
            self.win.set_language("en")

    def test_rename_updates_the_card_title_tag(self):
        self.settings.show()
        self.win.set_dog_name("Bobo")
        self.assertEqual(self.settings._title_label.text(), "Bobo", "胶囊标签上的名字跟着换")
        self.assertEqual(self.settings.windowTitle(), "Bobo")

    def test_rename_trims_and_may_be_empty(self):
        self.win.set_dog_name("  Bobo  ")
        self.assertEqual(self.win.dog_name, "Bobo")
        self.assertEqual(self.win.settings.values["dog_name"], "Bobo")
        self.win.set_dog_name("   ")
        self.assertEqual(self.win.dog_name, "", "名字可以为空")
        self.assertEqual(self.settings._title_label.text(), "")
        self.assertEqual(self.settings._tag.tag.target, self.settings._tag.H, "名字胶囊只剩骨头：26 的正圆")

    def test_size_is_a_title_row_and_a_full_width_slider_in_both_languages(self):
        """大小在主页面。上面一行「大小」+ 百分比 + 重置（靠右），下面一条整行宽的滑杆：主页面少了两个声音开关，
        动作行下面只剩一行就放不下 157 的表盘；范围跟着屏变大以后整行宽的滑杆也细一点。"""
        from PySide6.QtCore import QPoint
        from widget.settings import SIZE_GAP
        for lang in ("en", "zh"):
            self.win.set_language(lang)
            card = self.win.settings_panel
            card.show()
            card.finish_page_anim()
            self.app.processEvents()
            slider, number = card.size_slider, card.size_label
            reset = card.reset_button
            self.assertEqual(slider.width(), 280, "滑杆整行宽")
            self.assertEqual(reset.x() - (number.x() + number.width()), 1)
            self.assertEqual(reset.mapTo(card, QPoint(reset.width(), 0)).x(), slider.mapTo(card, QPoint(slider.width(), 0)).x(),
                             "重置靠右，和滑杆的右头对齐")
            self.assertAlmostEqual(number.mapTo(card, number.rect().center()).y(), reset.mapTo(card, reset.rect().center()).y(), delta=1)
            self.assertEqual(slider.mapTo(card, QPoint(0, 0)).y() - number.mapTo(card, QPoint(0, number.height())).y(), SIZE_GAP,
                             "滑杆紧跟在那一行下面")
            self.assertEqual(number.width(), 56, "当前30–400%范围内数字与悬停箭头完整放进56px")
            self.assertEqual(reset.symbol, "reset")
            self.assertLessEqual(reset.width(), 26)
            self.assertEqual(card.width(), 356, "不通过扩大卡片来容纳")
            self.assertLessEqual(card.main_page.minimumSizeHint().width(), card.scroll.viewport().width())
            card.hide()

    @mock.patch("widget.motion.native.reduce_motion", return_value=False)
    def test_update_status_retarget_preserves_one_surface_and_click_gating(self, _reduce_motion):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        s.finish_page_anim()
        self.app.processEvents()
        button = s.update_button
        initial = button.geometry()
        self.assertGreaterEqual(button.width(), 160, "更新控件使用版本号之外的剩余宽度")
        clicks = []
        button.clicked.connect(lambda: clicks.append(True))
        up = self.win.updater
        up._spawn = lambda fn: None
        QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
        for _ in range(12):
            button.motion.tick(.01)
        QTest.mouseRelease(button, Qt.LeftButton, pos=button.rect().center())
        self.assertEqual(up.state, "checking")
        self.app.processEvents()               # 旧实现此处把143px按钮缩到83px，再次换状态只截出右半
        button.tick(.02)
        up.state = "latest"
        s.sync_update()
        self.app.processEvents()
        self.assertIs(s.update_button, button)
        self.assertEqual(button.geometry(), initial)
        self.assertFalse([a for a in s._animators if type(a).__name__ == "_Swap"])
        self.assertIsNone(button.graphicsEffect())
        self.assertEqual(len(clicks), 1)
        button.click()
        QTest.mouseClick(button, Qt.LeftButton, pos=button.rect().center())
        QTest.keyClick(button, Qt.Key_Space)
        self.assertEqual(len(clicks), 1, "正在检查和最终状态不能触发旧按钮动作")
        s.finish_page_anim()
        self.assertEqual(button._display_text, button.text())
        self.assertEqual(button._text_opacity, 1.0)
        for state in ("offline", "checking", "found", "downloading", "downloaded", "failed"):
            up.state = state
            s.sync_update()
            self.app.processEvents()
            self.assertEqual(button.geometry(), initial, state)
            self.assertLessEqual(s.advanced_page.minimumSizeHint().width(), s.scroll.viewport().width(), state)

    def test_the_main_page_only_has_what_you_might_change_right_now(self):
        """主页面的不是高频设置就放进高级。毛色、删除在这只同桌的详情页，高级设置里没有「同桌」那一行了。"""
        from PySide6.QtWidgets import QLabel, QAbstractButton
        s = self.settings
        def texts(page):
            return {w.text() for w in page.findChildren(QLabel)} | {w.text() for w in page.findChildren(QAbstractButton)}
        main, advanced, pet = texts(s.main_page), texts(s.advanced_page), texts(s.pet_page)
        for label in ("Follow cursor", "Dynamic interaction", "Size", "Advanced…"):
            self.assertIn(label, main)
        for label in ("Language / 语言", "Deskmate", "Coat color", "Show metadata", "Media sounds", "Interface sounds"):
            self.assertNotIn(label, main, "不在第一级")
        self.assertFalse(s.play_collapse.is_open, "捡球这些在灵动交互的选项里，默认收着")
        for label in ("Language / 语言", "Low Power Mode", "Media sounds", "Interface sounds"):
            self.assertIn(label, advanced)
        for label in ("Deskmate", "Coat color"):
            self.assertNotIn(label, advanced, "不在高级设置")
        for label in ("Coat color", "Delete"):
            self.assertIn(label, pet, "在详情页")
        for label in ("Size", "Remove this deskmate", "Hold to remove"):
            self.assertNotIn(label, pet, "详情页只有看细节那一行、毛色和一颗「删除」，左边不写字")
        self.assertNotIn("Size", advanced, "大小在主页面了")
        self.assertNotIn("Fetch the ball", advanced, "没有捡球开关（进圈才追就是那一层）")
        self.assertNotIn("Show widget in all screens", advanced, "没有小组件全局显示")
        self.assertFalse(hasattr(s, "auto_turn"), "随鼠标转身绑在灵动交互上，没有开关")

    def test_volume_sliders_have_ten_steps_a_mute_that_remembers_and_old_switches_migrate(self):
        """「媒体音效」「界面音效」各一条 10 档的滑块 + 右边一颗静音；照苹果：70% 时静音变 0，取消静音回到 70%；拖到 0 也是静音。
        档位换成增益按听起来一样大的台阶（响度 ∝ 振幅 ^ 0.6）。"""
        from widget import sounds
        from widget.prefs import Prefs
        s, w = self.settings, self.win
        self.addCleanup(w.set_interface_volume, 10, False)
        self.addCleanup(w.set_media_volume, 10, False)
        s.show_advanced(True, animated=False)
        s.show()
        row = s.interface_volume
        self.assertEqual((row.slider.lo, row.slider.hi, row.slider.value), (0, 10, 10.0))
        with mock.patch.object(sounds, "play") as play:
            row.slider._nudge(-3.0)
            self.assertEqual((w.interface_volume, w.interface_muted), (7, False))
            self.assertAlmostEqual(sounds._gain, (0.7) ** (1 / 0.6))
            self.assertEqual(play.call_args_list[-1].args, ("switch-off",), "调小：放一声「关」，按新的音量")
            row.mute.click()
            self.assertEqual((w.interface_volume, w.interface_muted, row.slider.value), (7, True, 0.0), "静音：滑块到 0，7 记着")
            self.assertEqual(play.call_args_list[-1].args, ("switch-off",), "静音键：「关」一声")
            self.assertFalse(sounds._enabled)
            row.mute.click()
            self.assertEqual((w.interface_volume, w.interface_muted, row.slider.value), (7, False, 7.0), "取消静音：回到 7")
            self.assertEqual(play.call_args_list[-1].args, ("switch-on",))
            row.slider._nudge(-7.0)
            self.assertEqual((w.interface_volume, w.interface_muted), (7, True), "拖到 0：静音，记着拖之前那一档")
            row.slider._nudge(2.0)
            self.assertEqual((w.interface_volume, w.interface_muted), (2, False), "静音时一拖就取消静音")
        self.assertEqual([round(sounds.gain(k), 3) for k in (0, 5, 10)], [0.0, round(0.5 ** (1 / 0.6), 3), 1.0])
        loud = [sounds.gain(k) ** 0.6 for k in range(11)]
        self.assertTrue(all(abs((b - a) - 0.1) < 1e-9 for a, b in zip(loud, loud[1:])), "每一档听起来加得一样多")
        store = FakeSettings()
        store.values.update(interface_sounds="false", pack_sounds="true")
        prefs = Prefs(store)
        self.assertEqual(prefs.volume("interface"), (10, True), "以前关着：静音、记着满格")
        self.assertEqual(prefs.volume("media"), (10, False), "以前开着：满格，和以前一样响")

    def test_both_mute_buttons_click_like_a_switch_at_their_own_volume(self):
        """静音键就是一个开关，两条一样——关的时候「关」一声、开的时候「开」一声，多响按这一条自己设的音量；
        媒体音效那条取消静音不再叫，它的开关声按媒体音效的音量放，不按界面音效的。"""
        from widget import sounds
        s, w = self.settings, self.win
        self.addCleanup(w.set_interface_volume, 10, False)
        self.addCleanup(w.set_media_volume, 10, False)
        s.show_advanced(True, animated=False)
        s.show()
        heard = []                                               # (哪个文件, 增益)：真放出去的那一下

        def play_sound(path, gain=1.0, offset=0.0):
            heard.append((Path(path).name, round(gain, 4)))
            return True
        with mock.patch.object(sounds.native, "play_sound", side_effect=play_sound), mock.patch("widget.capture_ui._frozen", False):
            for row, set_level in ((s.media_volume, w.set_media_volume), (s.interface_volume, w.set_interface_volume)):
                other = w.set_interface_volume if row.media else w.set_media_volume
                for level in (2, 9):
                    other(5, False)                              # 另一条停在 5 档：听的不是它的音量
                    set_level(level, False)
                    del heard[:]
                    row.mute.click()
                    self.assertEqual(heard, [("switch-off.wav", round(sounds.gain(level), 4))], f"{'媒体' if row.media else '界面'} {level} 档：静音前按这一档「关」一声")
                    self.assertTrue(row.mute.muted)
                    row.mute.click()
                    self.assertFalse(row.mute.muted)
                    self.assertEqual(heard[1:], [("switch-on.wav", round(sounds.gain(level), 4))], "取消静音：回到记着的那一档再「开」一声，媒体那条不叫")
                other(5, True)                                   # 另一条静着音：这一条的开关声照响（媒体那条的开关声不归界面音效管）
                del heard[:]
                row.mute.click()
                row.mute.click()
                self.assertEqual([name for name, _ in heard], ["switch-off.wav", "switch-on.wav"])
                other(5, False)
            self.assertLess(sounds.gain(2), sounds.gain(9), "2 档比 9 档小声")

    def test_adjusting_the_volume_plays_how_loud_it_is_now_without_a_burst(self):
        """调的时候听现在多响：界面音效每变一档一声开关声，太快合并成一声（不连成一串）；
        媒体音效拖着时最多每半秒叫一声、松手按最后那一档再叫一声；叫的是模型包里的真录音。"""
        from widget import settings as settings_mod, sounds
        s, w = self.settings, self.win
        self.addCleanup(w.set_interface_volume, 10, False)
        self.addCleanup(w.set_media_volume, 10, False)
        s.show_advanced(True, animated=False)
        s.show()
        now = [100.0]
        row = s.interface_volume
        with mock.patch.object(settings_mod.time, "monotonic", side_effect=lambda: now[0]), mock.patch.object(sounds, "play") as play:
            row._started()
            for k, level in enumerate((9, 8, 7, 6, 5)):
                now[0] = 100.0 + 0.02 * k
                row.slider._apply(float(level))
            self.assertEqual(play.call_count, 1, "第一下马上响，后面太快的先攒着")
            self.assertTrue(row._ui_timer.isActive())
            now[0] = 100.2
            row._flush_ui()
            self.assertEqual([c.args for c in play.call_args_list], [("switch-off",), ("switch-off",)], "攒着的合并成一声")
        media = s.media_volume
        path, _event = media._bark_file()
        self.assertIsNotNone(path, "模型包里有叫声")
        self.assertIn("bark", path.name)
        barks = []
        with mock.patch.object(settings_mod.time, "monotonic", side_effect=lambda: now[0]), \
                mock.patch.object(sounds, "play_file", side_effect=lambda f, g=1.0: barks.append((now[0], w.media_volume))), \
                mock.patch.object(sounds, "stop_file"):
            media._started()
            for k, level in enumerate((9, 8, 7, 6, 5, 4)):
                now[0] = 200.0 + 0.12 * k
                media.slider._apply(float(level))
            now[0] = 200.66
            media.slider._apply(3.0)
            self.assertEqual([t for t, _ in barks], [200.0, 200.6], "拖着时最多每半秒叫一声")
            now[0] = 200.7
            media._finished()
            self.assertEqual(barks[-1], (200.7, 3), "松手按最后那一档再叫一声")
            media._finished()
            self.assertEqual(len(barks), 3, "刚按这一档叫过就不重复")

    def test_the_size_slider_snaps_to_the_recommended_mark_with_its_own_sound(self):
        """拖到推荐值附近吸过去（FineSlider.set_mark、MARK_SNAP_PX）那一下换一种声音（size-snap，跟界面音效的音量）。"""
        from widget import sounds
        s = self.settings
        s.show()
        s.finish_page_anim()
        slider = s.size_slider
        slider.set_mark(247.3)
        span = slider.width() - 2 * slider.EDGE
        x_mark = slider.EDGE + (247.3 - slider.lo) / (slider.hi - slider.lo) * span
        with mock.patch.object(sounds, "_enabled", True), mock.patch.object(sounds, "_last_size_tick", -1e9), \
                mock.patch("widget.capture_ui._frozen", False), mock.patch.object(sounds, "play") as play:
            slider._press = 0.0
            slider._drag_to(x_mark + 2.0)
            self.assertAlmostEqual(slider.value, 247.3, msg="吸过去了")
            self.assertEqual(play.call_args_list[-1].args, ("size-snap",))
            slider._drag_to(x_mark + 2.5)
            self.assertEqual(play.call_count, 1, "停在刻度上动一点：不再响")
            sounds._last_size_tick = -1e9                              # 刻度声 20 次 / 秒的限频：这里不真等
            slider._drag_to(x_mark + 30.0)
            self.assertNotEqual(play.call_args_list[-1].args, ("size-snap",), "离开了：平常的 tick")
            slider._press = None
        self.assertTrue(sounds.FILES["size-snap"].is_file())

    def test_the_size_range_follows_the_dogs_screen(self):
        """滑杆的范围跟着狗在的那块屏（window.scale_range：最小 30，最大到狗站着约占屏高三分之二，至少 400）。
        换屏时大小本身不变：比新屏的上限还大就先包住它，不把它显示成上限。"""
        s, w = self.settings, self.win
        s.show()
        with mock.patch.object(type(w), "scale_range", lambda _self: (30, 790), create=True):
            s.sync()
            self.assertEqual((s.size_slider.lo, s.size_slider.hi), (30.0, 790.0))
            self.assertEqual((s.size_label.lo, s.size_label.hi), (30.0, 790.0))
        with mock.patch.object(type(w), "scale_range", lambda _self: (30, 400), create=True), \
                mock.patch.object(w, "world_scale", 5.3):
            s.sync()
            self.assertEqual(s.size_slider.hi, 530.0, "现在的 530% 比这块屏的上限大：范围包住它")
            self.assertEqual(s.size_label.text(), "530%")

    def test_the_capsule_icon_is_the_pets_species_only_when_it_shows_a_name(self):
        """名字胶囊里写的是同桌的名字（主页面正中那只、详情页）或者添加页选的模型是狗，用物种图标（狗 = 骨头）；
        别的都是 app 图标（高级设置和它下面几页、自定义毛色页、已下载页、停在「+」上的「添加同桌」）。进高级设置时 app 图标从圆里流进胶囊。"""
        from widget import marks
        s = self.settings
        s.show()
        self.app.processEvents()
        s.finish_page_anim()
        bar = s._tag
        self.assertEqual(bar._icon, "bone", "主页面：正中那只的名字")
        for page, icon in (("pet", "bone"), ("coat", marks.APP), ("pet", "bone"), ("main", "bone"), ("add", "bone"), ("main", "bone"),
                           ("advanced", marks.APP), ("tuning", marks.APP), ("uninstall", marks.APP), ("notes", marks.APP)):
            s.show_page(page, animated=False)
            self.assertEqual(bar._icon, icon, page)
        s.show_page("main", animated=False)
        with mock.patch.object(self.win.updater, "state", "downloaded"), \
                mock.patch.object(self.win.updater, "release", mock.Mock(label=lambda: "0.6.1 (60)", size_text=lambda: "38 MB")):
            s.open_downloaded("main")                                  # 已下载页只有下载好了才进得去
            self.assertEqual((s.page, bar._icon), ("downloaded", marks.APP), "已下载页")
            s.show_page("main", animated=False)
        s.sync_update()
        s.strip.go(len(s.strip.pets))
        for _ in range(60):
            s.frame_step(s.clock._last + 1 / 60, 1 / 60)
        self.assertEqual((bar.text(), bar.outlined, bar._icon), ("Add a deskmate", True, marks.APP), "停在「+」上：描边的「添加同桌」，app 图标")
        s.strip.go(0)
        s.finish_page_anim()
        for _ in range(60):
            s.frame_step(s.clock._last + 1 / 60, 1 / 60)
        with mock.patch("widget.card.native.reduce_motion", return_value=False):
            s.show_advanced(True)
            self.assertTrue(bar._flow_on, "进高级设置：app 图标从左上角的圆流进胶囊")
            s.finish_page_anim()
            self.assertFalse(bar._flow_on)
            s.show_page("main")
            self.assertTrue(bar._flow_on, "回来：流回圆里")
            s.finish_page_anim()

    def test_each_volume_is_remembered_and_shown(self):
        """两条音量各记各的（档位 + 静音），卡片每 0.3 秒对一次。"""
        from widget import sounds
        s, w = self.settings, self.win
        self.addCleanup(w.set_media_volume, 10, False)
        self.addCleanup(w.set_interface_volume, 10, False)
        self.assertEqual((w.media_volume, w.media_muted, w.interface_volume, w.interface_muted), (10, False, 10, False), "默认满格：和以前开着一样响")
        w.set_media_volume(4, True)
        s.sync()
        self.assertEqual(s.media_volume.slider.value, 0.0, "静音：滑块在 0")
        self.assertTrue(s.media_volume.mute.muted)
        self.assertEqual(s.interface_volume.slider.value, 10.0, "另一个不受影响")
        self.assertEqual((w.prefs.get("media_volume"), w.prefs.get("media_muted")), (4, True), "记住了：静音前那一档也记着")
        self.assertFalse(sounds._pack_enabled)
        self.assertTrue(sounds._enabled)

    def test_the_custom_coat_page_opens_even_if_its_thumbnails_fail(self):
        """缩略图出错时换页整个停下，点了没反应；这里出错不能挡住进这一页。"""
        from unittest import mock
        s = self.settings
        s.coat_page._thumbs_ready = False
        with mock.patch.object(self.win, "pattern_thumbnails", side_effect=RuntimeError("no GL")), self.assertLogs("coat", "ERROR"):
            self.win.open_coat()
        s.finish_page_anim()
        self.assertEqual(s.page, "coat")

    def test_the_thumbnail_pose_still_matches_the_dog_controller(self):
        """这一帧不碰 GL，单测里也跑得到（只有真机有 GL 才走到的代码出错时，自定义毛色页会一直打不开）。"""
        from widget.geometry import project
        from widget.render import ELEVATION
        look = self.win.look
        frame = look._head_frame(248, 180)
        self.assertTrue(frame.joints)
        head = self.win.model.node_by_name("head").index
        from widget.anim import Player
        from widget.gltf import IDENTITY
        player = Player(self.win.model)
        player.play("Idle_1", loop=False, fade=0.0)
        player.update(0.0)
        m = player.globals(IDENTITY)[head]
        x, up = project((m[12], m[13], m[14]), frame.ppm, frame.ground_px, ELEVATION, 248, frame.offset)
        self.assertAlmostEqual(x, 124.0, delta=0.5, msg="头在画面正中")
        self.assertAlmostEqual(180 - up, 180 * 0.42, delta=0.5, msg="头骨在画面上面四成的地方：装得下耳朵尖到胸口")
        self.assertGreater(frame.ppm, 400, "是特写：一米好几百像素（整只狗的缩略图才 170）")

    def test_coat_faces_names_and_common_colors(self):
        """选毛色那一行是四张小狗头像加名字；
        自定义页每张斑纹图下面一句差在哪，多一排常用颜色，点一下主色和副色一起换。"""
        from unittest import mock
        from PySide6.QtGui import QImage
        from widget.coat import COMMON_COLORS
        from widget.widgets import Avatar
        s = self.settings
        self.assertEqual([lab.text() for lab in s.coat_labels], ["Black", "Red", "Grey", "Odd-eyed"], "名字是包里写的")
        self.assertTrue(all(isinstance(b, Avatar) for b in s.swatches + [s.custom_swatch]))
        face = QImage(160, 160, QImage.Format_ARGB32)
        face.fill(0xFF336699)
        s._faces_ready = False
        before = s.swatches[1].icon().cacheKey()

        def faces(width, height, deliver, done):                     # 一张张画（window.coat_faces）：这里当场给第 2 套那张、画完
            deliver(2, face)
            done()
            return lambda: None
        with mock.patch.object(self.win, "coat_faces", side_effect=faces) as shots:
            s.show()                                                   # 头像只在卡片开着时画（要真的 GL）
            s.show_page("pet", False)
            s.show_page("advanced", False)
            s.show_page("pet", False)
            shots.assert_called_once()                               # 只画一次
        self.assertNotEqual(s.swatches[1].icon().cacheKey(), before, "头像换上了")
        s._faces_ready = False
        with mock.patch.object(self.win, "coat_faces", side_effect=RuntimeError("no GL")), self.assertLogs("coat", "ERROR"):
            s.show_page("advanced", False)
            s.show_page("pet", False)
        self.assertEqual(s.page, "pet", "头像画不出来也进得了这一页")
        page = s.coat_page
        self.assertEqual(page.pattern_notes[4].text(), "White collar · odd eyes")
        self.assertEqual(len(page.color_chips), len(COMMON_COLORS))
        self.win.open_coat()
        s.finish_page_anim()
        main, secondary = COMMON_COLORS[2]
        page.color_chips[2].click()
        page.flush()
        self.assertEqual((self.win.coat_spec.main, self.win.coat_spec.secondary), (main, secondary))
        self.assertEqual((page.main.color, page.secondary.color), (main, secondary), "两个色块跟着变")
        self.assertEqual(self.win.coat, 0)

    def test_uncaught_errors_reach_the_log(self):
        """打包的 app 没有终端：按钮背后的代码出错时界面只是没反应，要写进日志才查得到。"""
        import sys
        from unittest import mock
        import app
        try:
            raise ValueError("boom in a slot")
        except ValueError:
            info = sys.exc_info()
        with mock.patch.object(sys, "__excepthook__"), self.assertLogs("app", "ERROR") as logs:
            app.log_uncaught(*info)
        self.assertIn("boom in a slot", logs.output[0])

    def test_the_pet_page_is_reached_from_the_strip_not_from_advanced(self):
        """换同桌、换模型都在主页面，改毛色在详情页；高级设置里没有选模型那一行。"""
        s = self.settings
        s.show()
        s.finish_page_anim()
        s.strip.open_current()
        self.assertEqual(s.page, "pet")
        s.finish_page_anim()
        self.assertTrue(s.custom_swatch.isVisibleTo(s))
        s.back.click()                                                 # 顶部栏左边的圆
        s.finish_page_anim()
        self.assertEqual(s.page, "main")

    def test_page_registry_preserves_back_targets_and_lifecycle(self):
        s = self.settings
        s.show()
        for page, target in (("advanced", "main"), ("pet", "main"), ("coat", "pet"), ("uninstall", "advanced")):
            s.show_page(page, animated=False)
            self.assertEqual(s._back_target(), target)
            self.assertEqual([name for name, entry in s.pages.items() if entry.widget.isVisibleTo(s)], [page])
            self.assertEqual(s.strip.isVisibleTo(s), page == "pet", "「我的同桌」那一条只在主页面和详情页")
            self.assertEqual(s._tag.lead_mode, "back", "别的页：顶部栏左边是返回")
            self.assertEqual(s._tag.click_action, "rename" if page == "pet" else None, "只有详情页点名字改名")
        for origin in ("main", "advanced"):
            s._downloaded_from = origin
            self.assertEqual(s.pages["downloaded"].back_target(), origin)
        self.assertEqual([name for name, entry in s.pages.items() if not entry.chip], ["downloaded"], "新版本胶囊：除了已下载页自己，每一页都有")
        self.assertEqual({name: entry.title_click for name, entry in s.pages.items() if entry.title_click}, {"main": "open", "pet": "rename"})
        self.assertEqual([name for name, entry in s.pages.items() if entry.lead != "back"], ["main"])
        s.show_page("main", animated=False)
        self.assertFalse(s.advanced_open)
        self.assertEqual((s._tag.lead_mode, s._tag.click_action), ("mark", "open"))

    def test_capture_freeze_defers_settings_and_update_status_until_sync(self):
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        s.finish_page_anim()
        text = s.update_button.text()
        with mock.patch("widget.settings.ui_frozen", return_value=True):
            self.win.set_follow_cursor(True)
            self.win.updater.state = "checking"
            s.sync_update()
            s.sync()
            self.assertEqual(s.update_button.text(), text, "选区截图期间保留原更新文字")
            self.assertFalse(s.follow.isChecked(), "业务状态可以变化，画面保持截图前状态")
            self.assertTrue(s._update_pending)
        s.sync()
        self.assertTrue(s.follow.isChecked())
        self.assertIn("Checking", s.update_button.text())
        self.assertFalse(s._update_pending, "截图结束后的下一次sync补上期间的新状态")
