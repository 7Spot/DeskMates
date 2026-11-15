"""改名反馈：真实 Qt 输入/输入法和共享限频；音频后端全程 mock。"""
import math
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication, QInputMethodEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from widget import native, sounds
from widget.animation import FrameClock
from widget.card import Card
from widget.widgets import NAME_MAX, grapheme_count


class RenameSoundCase(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.hits = []
        for name, value in (("_enabled", True), ("_last_rename_type", -math.inf),
                            ("_last_rename_limit", -math.inf), ("_rename_busy_until", -math.inf),
                            ("_rename_current", None)):
            self.enterContext(mock.patch.object(sounds, name, value))
        self.enterContext(mock.patch("widget.capture_ui._frozen", False))
        self.enterContext(mock.patch.object(sounds.time, "monotonic", side_effect=lambda: self.now))
        self.enterContext(mock.patch.object(native, "prepare_sound", return_value=True))
        self.play = self.enterContext(mock.patch.object(native, "play_sound", side_effect=self.record))
        self.stop = self.enterContext(mock.patch.object(native, "stop_sound", return_value=True))

    def record(self, filename, gain=1):
        self.hits.append((self.now, Path(filename).stem, gain))
        return True

    @property
    def kinds(self):
        return [hit[1] for hit in self.hits]


class RenameSoundGateTests(RenameSoundCase):
    def test_typing_has_sixty_ms_limit_and_does_not_replace_semantic_clips(self):
        sounds.rename_feedback("enter")
        self.now = .077
        sounds.rename_feedback("type")
        self.assertEqual(self.kinds, ["rename-enter"])
        self.now = .078
        sounds.rename_feedback("type")
        self.now = .137
        sounds.rename_feedback("type")
        self.now = .138
        sounds.rename_feedback("type")
        self.assertEqual(self.kinds, ["rename-enter", "rename-type", "rename-type"])
        self.now = .2
        sounds.rename_feedback("done")
        self.now = .264
        sounds.rename_feedback("type")
        self.now = .265
        sounds.rename_feedback("type")
        self.assertEqual(self.kinds[-2:], ["rename-done", "rename-type"])
        self.assertEqual(sounds.RENAME_TYPE_INTERVAL, .06)

    def test_limit_is_six_hundred_ms_and_suppressed_events_are_not_queued(self):
        sounds.rename_feedback("limit")
        for i in range(1, 60):
            self.now = i / 100
            sounds.rename_feedback("limit")
        self.assertEqual(self.kinds, ["rename-limit"])
        self.now = .6
        sounds.rename_feedback("limit")
        self.now = .774
        sounds.rename_feedback("type")
        self.assertEqual(self.kinds, ["rename-limit", "rename-limit"])
        self.now = .776
        sounds.rename_feedback("type")
        self.assertEqual(self.kinds[-1], "rename-type")
        self.now = 10
        self.assertEqual(len(self.hits), 3, "限频期间跳过的事件不补播")
        self.assertEqual(sounds.RENAME_LIMIT_INTERVAL, .6)

    def test_fast_input_restarts_keep_gate_and_play_only_the_original_sample(self):
        for i in range(101):
            self.now = i * .0021
            sounds.rename_feedback("type")
            sounds.stop_rename()
        self.assertEqual(len(self.hits), 4)
        self.assertTrue(all(b[0] - a[0] >= .06 for a, b in zip(self.hits, self.hits[1:])))
        self.assertTrue(all(hit[1:] == ("rename-type", 1.0) for hit in self.hits))
        self.assertIsNone(sounds._rename_current)

    def test_mute_stops_current_clip_and_capture_is_silent_without_consuming_gate(self):
        sounds.rename_feedback("type")
        with mock.patch.object(sounds, "_extra", set()):
            sounds.set_enabled(False)
        self.stop.assert_called_once_with(str(sounds.FILES["rename-type"]))
        self.assertIsNone(sounds._rename_current)
        self.now = .2
        for kind in sounds.RENAME_DURATIONS:
            sounds.rename_feedback(kind)
        sounds.set_enabled(True)
        with mock.patch("widget.capture_ui._frozen", True):
            for kind in sounds.RENAME_DURATIONS:
                sounds.rename_feedback(kind)
        self.assertEqual(self.kinds, ["rename-type"])
        sounds.rename_feedback("type")
        self.assertEqual(self.kinds, ["rename-type", "rename-type"])


class RenameInputSoundTests(RenameSoundCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(FrameClock, "default_host", None))
        self.enterContext(mock.patch.object(native, "reduce_motion", return_value=True))
        self.card = Card("Milo")
        self.changes = []
        self.card.set_renamable(self.changes.append, "Click to rename")
        self.other = QLineEdit()
        self.card.body.addWidget(self.other)
        self.card.resize(380, 180)
        self.card.show()
        self.card.activateWindow()
        self.app.processEvents()
        self.edit = self.card._title_edit

    def tearDown(self):
        self.card._end_rename()
        self.card.hide()
        self.card.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def start(self):
        self.card.start_rename()
        self.app.processEvents()
        self.assertTrue(self.card.renaming)
        self.now += .1  # 输入不盖住进入编辑的78ms原音。

    def ime(self, preedit="", commit=""):
        event = QInputMethodEvent(preedit, [])
        if commit:
            event.setCommitString(commit)
        self.app.sendEvent(self.edit, event)

    def test_real_keys_enter_once_then_return_and_blur_commit_once(self):
        QTest.mouseClick(self.card._tag, Qt.LeftButton, pos=self.card._tag.tag_rect().center().toPoint())
        self.assertTrue(self.card.renaming)
        self.assertEqual(self.kinds, ["rename-enter"])
        self.card.start_rename()
        self.now = .1
        QTest.keyClicks(self.edit, "Bobo")
        self.assertEqual(self.kinds, ["rename-enter", "rename-type"])
        self.now = .3
        QTest.keyClick(self.edit, Qt.Key_Return)
        self.other.setFocus()
        self.edit.editingFinished.emit()
        self.app.processEvents()
        self.assertEqual(self.changes, ["Bobo"])
        self.assertEqual(self.kinds, ["rename-enter", "rename-type", "rename-done"])
        self.assertFalse(self.card.renaming)

    def test_focus_loss_commits_once_and_escape_cancels_without_completion(self):
        self.start()
        QTest.keyClicks(self.edit, "Bobo")
        self.now = .3
        self.other.setFocus()
        self.app.processEvents()
        self.assertEqual(self.changes, ["Bobo"])
        self.assertEqual(self.kinds.count("rename-done"), 1)
        self.now = .5
        self.start()
        QTest.keyClicks(self.edit, "Nope")
        QTest.keyClick(self.edit, Qt.Key_Escape)
        self.assertFalse(self.card.renaming)
        self.assertEqual(self.card._tag.text(), "Bobo")
        self.assertEqual(self.changes, ["Bobo"])
        self.assertEqual(self.kinds.count("rename-done"), 1)

    def test_programmatic_updates_and_unchanged_completion_are_silent(self):
        self.card.set_title("Luna", animated=False)
        self.edit.setText("programmatic")
        self.assertEqual(self.hits, [])
        self.start()
        self.edit.setText("Luna")
        QTest.keyClick(self.edit, Qt.Key_Return)
        self.assertEqual(self.kinds, ["rename-enter"])
        self.assertEqual(self.changes, [])

    def test_ime_preedit_changes_sound_but_selection_commit_does_not_repeat(self):
        self.start()
        self.ime("n")
        self.now = .17
        self.ime("ni")
        self.now = .24
        self.ime("ni")
        self.assertEqual(self.kinds, ["rename-enter", "rename-type", "rename-type"])
        self.ime(commit="你")
        self.ime()
        self.assertEqual(self.kinds, ["rename-enter", "rename-type", "rename-type"])
        self.assertEqual(self.edit.text(), "你")
        self.assertTrue(self.card.renaming)
        self.now = .4
        QTest.keyClick(self.edit, Qt.Key_Return)
        self.assertEqual(self.changes, ["你"])
        self.assertEqual(self.kinds[-1], "rename-done")

    def test_ime_return_selects_first_and_escape_clears_preedit_before_cancel(self):
        self.start()
        self.ime("ni")
        self.now = .2
        method = QGuiApplication.inputMethod()
        with mock.patch.object(method, "commit", side_effect=lambda: self.ime(commit="你")) as commit:
            QTest.keyClick(self.edit, Qt.Key_Return)
        commit.assert_called_once_with()
        self.assertTrue(self.card.renaming, "选字用的第一次回车不能同时结束改名")
        self.assertEqual(self.changes, [])
        self.assertEqual(self.kinds, ["rename-enter", "rename-type"])
        QTest.keyClick(self.edit, Qt.Key_Return)
        self.assertEqual(self.changes, ["你"])
        self.now = .4
        self.start()
        self.ime("x")
        QTest.keyClick(self.edit, Qt.Key_Escape)
        self.assertTrue(self.card.renaming)
        self.assertFalse(self.edit.composing)
        QTest.keyClick(self.edit, Qt.Key_Escape)
        self.assertFalse(self.card.renaming)
        self.assertEqual(self.card._tag.text(), "你")
        self.assertEqual(self.kinds.count("rename-done"), 1)

    def test_focus_loss_waits_for_pending_ime_commit_and_finishes_once(self):
        self.start()
        self.ime("ni")
        self.now = .2
        self.other.setFocus()
        self.app.processEvents()
        self.assertTrue(self.card.renaming)
        self.assertEqual(self.changes, [])
        self.ime(commit="你")
        self.ime()
        self.edit.editingFinished.emit()
        self.assertFalse(self.card.renaming)
        self.assertEqual(self.changes, ["你"])
        self.assertEqual(self.kinds, ["rename-enter", "rename-type", "rename-done"])

    def test_cursor_moves_and_noop_deletes_do_not_make_typing_sounds(self):
        self.start()
        QTest.keyClick(self.edit, Qt.Key_End)
        QTest.keyClick(self.edit, Qt.Key_Delete)
        QTest.keyClick(self.edit, Qt.Key_Home)
        QTest.keyClick(self.edit, Qt.Key_Backspace)
        self.assertEqual(self.edit.text(), "Milo")
        self.assertEqual(self.kinds, ["rename-enter"])

    def test_overlong_input_clips_graphemes_and_only_warns(self):
        self.start()
        # insert模拟一次粘贴；家庭表情由7码点组成，但在长度限制中只算一字。
        family = "👨‍👩‍👧‍👦"
        self.edit.insert(family * (NAME_MAX + 1))
        self.assertEqual(grapheme_count(self.edit.text()), NAME_MAX)
        self.assertEqual(self.edit.text(), family * NAME_MAX)
        self.assertEqual(self.kinds, ["rename-enter", "rename-limit"])
        self.now = .3
        self.edit.insert("x")
        self.assertEqual(self.kinds, ["rename-enter", "rename-limit"])
        self.now = .8
        self.edit.insert("x")
        self.assertEqual(self.kinds, ["rename-enter", "rename-limit", "rename-limit"])
        self.assertEqual(grapheme_count(self.edit.text()), NAME_MAX)


if __name__ == "__main__":
    unittest.main()
