"""普通按钮接入统一动效后，卡片入口、选择状态和确认框行为保持一致。"""
from unittest import mock

from tests.panel_base import PanelCase


class ButtonMotionIntegrationTests(PanelCase):
    def test_all_card_pages_and_auxiliary_cards_use_motion_buttons(self):
        from PySide6.QtWidgets import QPushButton
        from widget.coat_panel import ColorButton
        from widget.settings import UpdatePrompt
        from widget.widgets import MotionButton
        from widget.sizecontrol import SizeScrubber

        prompt = UpdatePrompt(self.win)
        try:
            for card in (self.settings, prompt):
                buttons = card.findChildren(QPushButton)
                self.assertTrue(buttons)
                for button in buttons:
                    self.assertIsNot(type(button), QPushButton,
                                     f"{type(card).__name__}: {button.text()!r} 没有接入动效")
            for button in self.settings.coat_page.findChildren(ColorButton):
                self.assertIsInstance(button, MotionButton)
            self.assertIsInstance(self.settings.size_label, SizeScrubber)
        finally:
            prompt.hide()
            prompt.deleteLater()

    @mock.patch("widget.motion.native.reduce_motion", return_value=False)
    def test_motion_control_keeps_click_and_checked_state_without_moving_its_layout(self, _reduce_motion):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QEnterEvent
        from PySide6.QtTest import QTest
        from widget.widgets import MotionButton

        self.settings.show()
        self.app.processEvents()
        button = self.settings.posture_buttons["sitting"]
        self.assertIsInstance(button, MotionButton)
        rect = button.geometry()
        clicks = []
        button.clicked.connect(lambda checked: clicks.append(checked))
        center = button.rect().center()
        self.app.sendEvent(button, QEnterEvent(QPointF(center), QPointF(center), QPointF(button.mapToGlobal(center))))
        for _ in range(30):
            button.motion.tick(1 / 60)
        self.assertAlmostEqual(button.motion.scale, 0.975, places=4,
                               msg="悬停时整个按钮轻缩，文字和底板一起运动")
        QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
        for _ in range(30):
            button.motion.tick(1 / 60)
        self.assertTrue(button.isDown())
        self.assertAlmostEqual(button.motion.scale, 0.95, places=4,
                               msg="悬停基础上再轻缩，按下约95%，同时保留按钮命中区域")
        self.assertEqual(button.geometry(), rect, "动效不推动卡片行列")
        QTest.mouseRelease(button, Qt.LeftButton, pos=button.rect().center())
        self.app.processEvents()
        self.assertEqual(self.win.rest_posture, "sitting")
        self.assertEqual(clicks, [True], "一次鼠标操作仍只触发一次点击")
        self.assertTrue(button.isChecked())
        self.assertEqual(button.geometry(), rect)

    def test_initial_and_rebuilt_language_selection_is_visible_without_hover(self):
        from widget import i18n

        def assert_selected(card, code):
            selected = [key for key, button in card.lang_buttons.items() if button.isChecked()]
            self.assertEqual(selected, [code])
            for key, button in card.lang_buttons.items():
                self.assertEqual(button.motion.selection.value, float(key == code),
                                 "当前语言必须在首次绘制前就有选中颜色，不等hover启动clock")
                self.assertEqual(button.motion.selection.target, float(key == code))

        assert_selected(self.settings, i18n.current())
        self.settings.show()
        self.settings.finish_animations()
        for code in ("zh", "en", "zh"):
            self.win.set_language(code)
            card = self.win.settings_panel
            self.assertTrue(card.isVisible())
            assert_selected(card, code)
            # 已选中的语言不能先反选，也不应重建同一套页面。
            same = self.win.settings_panel
            card.lang_buttons[code].click()
            self.assertIs(self.win.settings_panel, same)
            assert_selected(card, code)

    def test_language_pill_margins_survive_parent_card_render_in_both_themes(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QColor
        from widget import sticker

        self.settings.show()
        for mode in ("light", "dark"):
            self.win.set_appearance(mode)
            card = self.win.settings_panel
            card.finish_animations()
            card.show_advanced(True, False)                      # 语言在高级设置页
            card.finish_animations()
            image = card.grab().toImage()
            paper = QColor(sticker.PAPER)
            for button in card.lang_buttons.values():
                with self.subTest(mode=mode, language=button.text()):
                    self.assertEqual(button.motion.content_rect().height(), 26)
                    self.assertEqual(button.height(), 30)
                    origin = button.mapTo(card, QPoint())
                    edges = [QPoint(x, y) for x in range(button.width()) for y in (0, button.height() - 1)]
                    self.assertTrue(all(image.pixelColor(origin + p) == paper for p in edges),
                                    "真实父卡片中按钮上下必须各有透明余量，圆弧不能被行边界截掉")
