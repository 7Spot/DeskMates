"""轮盘跟随 Actions 行：展开子项时逐帧对齐，主叶动画不混入侧叶占位高度。"""
from unittest import mock


from tests.panel_base import PanelCase
from widget import native
from widget.sticker import SHADOW


class DialLayoutTests(PanelCase):
    def test_the_dial_stays_inside_the_card(self):
        """设置卡片变小了，表盘不能出卡片的边框。"""
        from widget import i18n
        from widget.dial import CARD_CLEAR
        for lang in ("zh", "en"):
            with self.subTest(lang=lang):
                i18n.set_language(lang)
                s = self.settings
                s.show()
                s.finish_page_anim()
                self.app.processEvents()
                if not s.side_open:
                    s.toggle_actions(False)
                self.app.processEvents()
                y = s.side_anchor_y() - s._main.y()
                self.assertLessEqual(s.dial.R + CARD_CLEAR, min(y, s._main.height() - y) + 1)
                s.toggle_actions(False)
        i18n.set_language("en")

    def test_a_shorter_card_makes_the_dial_smaller(self):
        d = self.settings.dial
        d.fit_to(400)
        big = d.R
        d.fit_to(400, 100.0)
        self.assertEqual(d.R, 72, "圆心离卡片边 100：表沿再留 28（比卡片的圆角 22 大，表盘的头不从圆角露出来）")
        self.assertLess(d.R, big)

    def test_no_action_name_is_cut_off_at_the_size_the_card_gives(self):
        """卡片变矮，表盘半径降到 134，英文的 Nose-down walk 被省略成 Nose-do…。"""
        from widget import i18n
        s = self.settings
        s.show()
        s.finish_page_anim()
        self.app.processEvents()
        s.toggle_actions(False)
        self.app.processEvents()
        d = s.dial
        for lang in ("en", "zh"):
            i18n.set_language(lang)
            d.fit_to(s._main.height(), s.side_room())
            for item in d.items:
                self.assertFalse(any("…" in line for line in d.wrap_label(i18n.tr(item.label))), f"{lang}: {item.label}")
        i18n.set_language("en")

    def setUp(self):
        super().setUp()
        self.motion = mock.patch.object(native, "reduce_motion", return_value=False)
        self.motion.start()
        self.addCleanup(self.motion.stop)

    def _open(self, language="en", expanded=False):
        self.win.set_follow_cursor(True)
        if language != "en":
            self.win.set_language(language)
        s = self.win.settings_panel
        s.show_in_place()
        self.app.processEvents()
        s.finish_page_anim()
        if expanded:
            s.toggle_follow_options(animated=False, on=True)
        self.app.processEvents()
        s.toggle_actions(animated=False)
        self.app.processEvents()
        s.finish_page_anim()
        s.clock.stop()
        self.win._anim_timer.stop()
        s._timer.stop()
        patch = mock.patch.object(s.clock, "start")
        patch.start()
        self.addCleanup(patch.stop)
        return s

    def _assert_aligned(self, s):
        expected = max(0, round(s.side_anchor_y() - s.dial.height() / 2))
        self.assertEqual(s.dial.y(), expected, "轮盘在当前帧对齐，不能等下一次点击才补位")
        self.assertLessEqual(s.dial.y() + s.dial.height(), s.height(), "动画过程中侧叶不能被窗口裁掉")

    def _frames(self, s, count=50):
        for _ in range(count):
            s._tick(1 / 60)
            self.app.processEvents()
            self._assert_aligned(s)

    def _cycles(self, language):
        s = self._open(language)
        start = (s.pos(), s.dial.size(), s.height(), s._main.height(), s.dial.y())
        for _ in range(2):
            for opened in (True, False):
                with self.subTest(language=language, opened=opened):
                    before = s.dial.y()
                    s.toggle_follow_options(on=opened)
                    self.assertEqual(s.dial.y(), before, "点击瞬间不补跳上一轮子项的完整高度")
                    self.assertEqual(s._leaf.target, s._main_final, "主叶目标只由主叶内容决定")
                    self._frames(s)
                    self.assertFalse(s.height_animating)
                    self.assertEqual(s._leaf.value, s._main.height(), "动画终点与最终主叶一致，没有尾部高度修正")
                    self.assertEqual(s.height(), max(s._main.height() + 2 * SHADOW + s.dock.dy,
                                                     s.dial.y() + s.dial.height()))
                    self.assertEqual((s.pos(), s.dial.size()), start[:2])
            self.assertEqual((s.height(), s._main.height(), s.dial.y()), start[2:])

