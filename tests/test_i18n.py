import unittest

from widget import i18n
from widget.i18n import LANGUAGE_NAMES, LANGUAGE_ROW, ZH, tr
from widget.states import BANNED_WORDS_ZH, GROUPS


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_every_action_and_group_has_a_chinese_label(self):
        from widget.clips import ACTIONS
        for title in GROUPS.values():
            self.assertIn(title, ZH, title)
        for a in ACTIONS:
            self.assertIn(a.label, ZH, a.id)

    def test_chinese_labels_are_actions_not_emotions(self):
        from widget.clips import ACTIONS
        for text in [ZH[a.label] for a in ACTIONS]:
            for word in BANNED_WORDS_ZH:
                self.assertNotIn(word, text, text)

    def test_descriptions_end_without_full_stops(self):
        """所有说明去掉句号、句点（中英文）。"""
        for en, zh in ZH.items():
            self.assertFalse(en.rstrip().endswith("."), en)
            self.assertFalse(zh.rstrip().endswith("。"), zh)

    def test_tr_switches_and_falls_back(self):
        self.assertEqual(tr("Follow cursor"), "Follow cursor")
        i18n.set_language("zh")
        self.assertEqual(tr("Follow cursor"), "鼠标跟随")
        self.assertEqual(tr("Not a known string"), "Not a known string")
        self.assertEqual(tr("Update {version}", version="0.6"), "新版本 0.6")
        i18n.set_language("klingon")
        self.assertEqual(i18n.current(), "en")

    def test_first_launch_follows_the_systems_preferred_language(self):
        """中文系统第一次打开是英文——打包的 app 里 Qt 说系统语言是 C。现在按 macOS 的首选语言列表的第一个定。"""
        self.assertEqual(i18n.system_default(["zh-Hans-AU", "en-AU"]), "zh")
        self.assertEqual(i18n.system_default(["zh-Hant-TW"]), "zh")
        self.assertEqual(i18n.system_default(["en-AU", "zh-Hans-AU"]), "en")
        self.assertIn(i18n.system_default([]), ("zh", "en"), "读不到列表：退回问 Qt")

    def test_language_row_is_always_bilingual(self):
        self.assertIn("Language", LANGUAGE_ROW)
        self.assertIn("语言", LANGUAGE_ROW)
        self.assertEqual(LANGUAGE_NAMES, {"en": "English", "zh": "中文"})
