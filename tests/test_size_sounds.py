"""尺寸音效：整数显示过格、共享20Hz门限和真实控件输入；音频后端全程mock。"""
import hashlib
import math
import os
import unittest
import wave
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from widget import native, sounds
from widget.animation import FrameClock
from widget.sizecontrol import SizeScrubber
from widget.widgets import FineSlider


class SizeSoundCase(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.hits = []
        self.enterContext(mock.patch.object(sounds, "_enabled", True))
        self.enterContext(mock.patch.object(sounds, "_last_size_tick", -math.inf))
        self.enterContext(mock.patch("widget.capture_ui._frozen", False))
        self.enterContext(mock.patch.object(sounds.time, "monotonic", side_effect=lambda: self.now))
        self.enterContext(mock.patch.object(native, "prepare_sound", return_value=True))
        self.play = self.enterContext(mock.patch.object(native, "play_sound", side_effect=self.record))

    def record(self, filename, gain=1):
        self.hits.append((self.now, Path(filename).stem, gain))
        return True


class SizeSoundGateTests(SizeSoundCase):
    def test_only_displayed_integer_crossings_sound_and_match_rounding_tolerance(self):
        sounds.size_changed(100.0, 100.49)
        sounds.size_changed(100.125, 100.125)
        self.assertEqual(self.hits, [])
        sounds.size_changed(100.49, 100.5 - 5e-10)
        self.assertEqual(SizeScrubber._integer(100.5 - 5e-10), "101")
        self.assertEqual(self.hits, [(0.0, "tick", 1.0)])
        self.now = .1
        sounds.size_changed(100.5 - 5e-10, 101.49)
        self.assertEqual(len(self.hits), 1, "变化了小数但数显同为101，不多响")
        for invalid in (math.inf, -math.inf, math.nan):
            sounds.size_changed(100.0, invalid)
            sounds.size_changed(invalid, 100.0)
        self.assertEqual(len(self.hits), 1)

    def test_fifty_ms_boundary_and_large_jump_emit_one_unchanged_sample(self):
        sounds.size_changed(30, 400)
        self.now = .049
        sounds.size_changed(400, 30, fine=True)
        self.assertEqual(len(self.hits), 1)
        self.now = .05
        sounds.size_changed(30, 400, fine=True)
        self.assertEqual(self.hits, [(0, "tick", 1.0), (.05, "size-fine", 1.0)])
        self.now = .1
        sounds.size_changed(400, 30)
        self.assertEqual(len(self.hits), 3, "跳过370个百分点也只调一次原音播放，不合批")

    def test_fast_bidirectional_updates_share_one_gate_without_a_playback_queue(self):
        previous = 100
        for i in range(101):
            self.now = i * .0021  # 约476Hz输入，门限采样点避开十进制浮点等号。
            value = 101 if i % 2 == 0 else 100
            sounds.size_changed(previous, value, fine=bool(i % 2))
            previous = value
        self.assertEqual(len(self.hits), 5)
        self.assertTrue(all(b[0] - a[0] >= .05 - 1e-12 for a, b in zip(self.hits, self.hits[1:])))
        self.assertEqual(sounds.SIZE_TICK_INTERVAL, .05)

    def test_mute_and_capture_do_not_play_or_consume_the_next_audible_slot(self):
        sounds.set_enabled(False)
        sounds.size_changed(30, 400)
        sounds.set_enabled(True)
        with mock.patch("widget.capture_ui._frozen", True):
            sounds.size_changed(400, 30, fine=True)
        self.assertEqual(self.hits, [])
        sounds.size_changed(100, 101, fine=True)
        self.assertEqual(self.hits, [(0, "size-fine", 1.0)])
        self.now = .01
        sounds.set_enabled(False)
        sounds.set_enabled(True)
        sounds.size_changed(101, 100)
        self.assertEqual(len(self.hits), 1, "切换静音不能重置门限")

    def test_production_pcm_matches_the_approved_capped_preview(self):
        # 从用户批准的wood-size-capped.html提取的PCM摘要；不依赖ignored试听目录。
        approved = {
            "tick": ("2b215fea9af806dd5906ba054bb23fc12f272c58b09ffd6fc20a297ecd130fe0", .032),
            "size-fine": ("0380e5239062bb5a9f24887dce48eec4ee11905074f961c513394e49cd63f5ae", .024),
        }
        for name, (digest, duration) in approved.items():
            with self.subTest(sound=name), wave.open(str(sounds.FILES[name])) as wav:
                self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (48000, 1, 2))
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), duration)
                self.assertEqual(hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest(), digest)


class SizeControlSoundTests(SizeSoundCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(FrameClock, "default_host", None))
        self.enterContext(mock.patch.object(native, "reduce_motion", return_value=True))
        self.slider = FineSlider(30, 400)
        self.slider.resize(392, 30)  # 370px轨道，1px恰好1个百分点，验证分数坐标。
        self.fine = SizeScrubber()
        self.slider.show()
        self.fine.show()
        self.app.processEvents()

    def tearDown(self):
        for widget in (self.slider, self.fine):
            widget.hide()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    @staticmethod
    def key(control, key):
        control.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))

    def mouse(self, control, kind, x, dt=.1):
        self.now += dt
        local = QPointF(x, control.height() / 2)
        global_pos = QPointF(1000.125 + x, 800.375)
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
        event = QMouseEvent(kind, local, global_pos, Qt.LeftButton, buttons, Qt.NoModifier)
        with mock.patch("widget.sizecontrol.time.perf_counter", return_value=self.now):
            {QEvent.MouseButtonPress: control.mousePressEvent,
             QEvent.MouseMove: control.mouseMoveEvent,
             QEvent.MouseButtonRelease: control.mouseReleaseEvent}[kind](event)

    def test_programmatic_sync_and_hover_are_silent_and_keep_float(self):
        for control in (self.slider, self.fine):
            changes = []
            control.valueChanged.connect(changes.append)
            control.set_value(123.4567890123)
            control.enterEvent(QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10)))
            control.leaveEvent(QEvent(QEvent.Leave))
            self.assertEqual(control.value, 123.4567890123)
            self.assertEqual(changes, [])
        self.assertEqual(self.fine.text(), "123%")
        self.assertEqual(self.hits, [])

    def test_real_slider_drag_sounds_only_at_integer_crossing_and_preserves_fraction(self):
        self.slider.set_value(100.125)
        x = self.slider._thumb_x()
        self.mouse(self.slider, QEvent.MouseButtonPress, x)
        self.mouse(self.slider, QEvent.MouseMove, x + .25)
        self.assertEqual(self.hits, [])
        self.mouse(self.slider, QEvent.MouseMove, x + .500125)
        self.assertEqual(len(self.hits), 1)
        self.assertEqual(self.hits[0][1:], ("tick", 1.0))
        exact = self.slider.value
        self.assertAlmostEqual(exact, 100.625125)
        self.mouse(self.slider, QEvent.MouseButtonRelease, x + .500125)
        self.assertEqual(self.slider.value, exact)
        self.assertEqual(len(self.hits), 1)
        QTest.qWait(75)
        self.assertEqual(len(self.hits), 1, "松手后不补播")

    def test_fine_drag_keeps_subpixel_precision_and_uses_approved_short_sound(self):
        self.fine.set_value(100)
        self.mouse(self.fine, QEvent.MouseButtonPress, 32)
        self.mouse(self.fine, QEvent.MouseMove, 36)
        self.assertAlmostEqual(self.fine.value, 100.4)
        for n in range(1, 11):
            self.mouse(self.fine, QEvent.MouseMove, 36 + n * .000125, dt=.02)
        self.assertAlmostEqual(self.fine.value, 100.400125, places=10)
        self.assertEqual(self.hits, [])
        self.mouse(self.fine, QEvent.MouseMove, 37.25)
        self.assertAlmostEqual(self.fine.value, 100.525, places=10)
        self.assertEqual(len(self.hits), 1)
        self.assertEqual(self.hits[-1][1:], ("size-fine", 1.0))
        exact = self.fine.value
        self.mouse(self.fine, QEvent.MouseButtonRelease, 37.25)
        self.assertEqual(self.fine.value, exact)
        self.assertEqual(len(self.hits), 1)

    def test_reverse_new_gestures_and_switching_controls_cannot_reset_gate(self):
        self.slider.set_value(100.125)
        self.fine.set_value(100.125)
        self.key(self.slider, Qt.Key_Right)
        self.now = .01
        self.key(self.slider, Qt.Key_Left)
        self.now = .02
        self.key(self.fine, Qt.Key_Right)
        self.assertEqual(len(self.hits), 1)
        self.now = .05
        self.key(self.fine, Qt.Key_Left)
        self.assertEqual(self.hits, [(0, "tick", 1.0), (.05, "size-fine", 1.0)])
        self.assertEqual(self.slider.value, 100.125)
        self.assertEqual(self.fine.value, 100.125)

    def test_linked_control_sync_does_not_double_play_and_boundaries_stay_silent(self):
        self.slider.valueChanged.connect(self.fine.set_value)
        self.fine.valueChanged.connect(self.slider.set_value)
        self.slider.set_value(100.25)
        self.fine.set_value(100.25)
        p = QPointF(self.slider.rect().center())
        event = QWheelEvent(p, p, QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        self.slider.wheelEvent(event)
        self.assertEqual(len(self.hits), 1)
        self.assertEqual((self.slider.value, self.fine.value), (101.25, 101.25))
        self.now = .1
        self.key(self.fine, Qt.Key_Left)
        self.assertEqual(len(self.hits), 2)
        for control in (self.slider, self.fine):
            control.set_value(400)
            self.now += .1
            self.key(control, Qt.Key_Right)
            control.set_value(30)
            self.now += .1
            self.key(control, Qt.Key_Left)
        self.assertEqual(len(self.hits), 2, "上下限没有值变化就不发声")

    def test_escape_restore_editor_cancel_and_hide_do_not_make_a_confirmation_sound(self):
        self.fine.set_value(100.125)
        self.mouse(self.fine, QEvent.MouseButtonPress, 32)
        self.mouse(self.fine, QEvent.MouseMove, 42)
        self.assertEqual(len(self.hits), 1)
        self.now += .1
        self.key(self.fine, Qt.Key_Escape)
        self.assertEqual(self.fine.value, 100.125)
        self.assertFalse(self.fine.adjusting)
        self.assertEqual(len(self.hits), 1, "Esc回滚不能发声")
        self.fine.start_edit()
        self.fine.editor.setText("240")
        self.fine.editor.setModified(True)
        QTest.keyClick(self.fine.editor, Qt.Key_Escape)
        self.assertEqual(self.fine.value, 100.125)
        self.fine.hide()
        QTest.qWait(75)
        self.assertEqual(len(self.hits), 1)

    def test_real_controls_obey_mute_and_capture_while_changes_keep_their_precision(self):
        for control in (self.slider, self.fine):
            control.set_value(100.125)
        sounds.set_enabled(False)
        self.key(self.slider, Qt.Key_Right)
        sounds.set_enabled(True)
        with mock.patch("widget.capture_ui._frozen", True):
            self.key(self.fine, Qt.Key_Right)
        self.assertEqual((self.slider.value, self.fine.value), (101.125, 101.125))
        self.assertEqual(self.hits, [])
        self.key(self.fine, Qt.Key_Right)
        self.assertEqual(self.hits, [(0, "size-fine", 1.0)])


if __name__ == "__main__":
    unittest.main()
