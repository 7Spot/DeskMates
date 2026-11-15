"""选定音色（整体 +6dB）、提交时机和静音边界；不使用真实音频输出。"""
import hashlib
import os
import struct
import time
import unittest
import wave
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QButtonGroup, QWidget

from widget import native, sounds
from widget.animation import FrameClock
from widget.widgets import FlatIcon, HoldButton, HoldPill, IconButton, MotionButton, SelectPill, Swatch, Switch


class SoundAssetsTests(unittest.TestCase):
    def test_approved_sounds_with_louder_master_are_packaged_unclipped(self):
        hashes = {
            "complete": "1e388d01730b8cc39e52c4755bc9b6a034463e72652d267385fb17fb0d118273",
            "switch-off": "48ae5b192524aead8498be2382d4c4212bab4edf954152afad1b6b83a8593807",
            "switch-on": "43687367563ac0b0a759e4aa8e5040a14ade474cc522121bc3d88a6ac5006025",
            "tap": "86274864f7786ff31c7591e89c2340735b2aac1d955cf9d2754527bfc7b72806",
            "tick": "ae848b1764ffac0c685bb4d7458ed6debd8c53e7b018f0c6e5a713e96a948798",
            "size-fine": "62b7e930da36eb53308ab9047a0e304b98de468b43500fab79949e6c32bc1e38",
            "rename-enter": "bc63db6c2f68b5dcc6830527e12dbc75955bc0f30c7d3ac6a1c29deadc151429",
            "rename-type": "fd7d8e6e429c363c1606d0cc9acea93042d523cce580eaac3fb4693a07f48196",
            "rename-limit": "1c832fb9dadb46ae559d606cc2dbf42343989d3d904e90a2233c0c4a8a31f754",
            "rename-done": "bcff163927ec872b2431b6c535d82759803abfc381a76111872e05fa7c95dad0",
            "size-snap": "07158e0ca6ec33a04ac23d47db89b8bd29d736691b9ad48f1aa7ab142cda5606",   # 大小滑杆吸到推荐值（「落槽」）
        }
        durations = {"tick": .032, "size-fine": .024, "rename-enter": .078,
                     "rename-type": .024, "rename-limit": .175, "rename-done": .065}
        for name, path in sounds.FILES.items():
            with self.subTest(sound=name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), hashes[name])
                with wave.open(str(path)) as wav:
                    self.assertEqual((wav.getframerate(), wav.getsampwidth(), wav.getnchannels()), (48000, 2, 1))
                    samples = struct.unpack("<" + "h" * wav.getnframes(), wav.readframes(wav.getnframes()))
                    self.assertEqual((samples[0], samples[-1]), (0, 0))
                    self.assertGreater(max(map(abs, samples)), 0)
                    self.assertLess(max(map(abs, samples)), 32767)
                    if name in durations:
                        self.assertAlmostEqual(len(samples) / wav.getframerate(), durations[name])

    def test_default_pref_and_dispatch_obey_mute_and_capture(self):
        from tests.panel_base import FakeSettings
        from widget.prefs import Prefs
        prefs = Prefs(FakeSettings())
        self.assertEqual(prefs.volume("interface"), (10, False), "默认满格、没静音")
        prefs.set("interface_muted", True)
        self.assertEqual(prefs.volume("interface"), (10, True))
        with mock.patch.object(sounds, "_enabled", True), mock.patch.object(native, "prepare_sound") as prepare, \
                mock.patch.object(native, "play_sound") as play, mock.patch.object(sounds, "_extra", set()):
            sounds.set_enabled(True)
            self.assertEqual(prepare.call_count, len(sounds.FILES))
            sounds.play("tap")
            play.assert_called_once_with(str(sounds.FILES["tap"]), 1.0)
            sounds.set_enabled(False)
            sounds.play("tap")
            sounds.set_enabled(True)
            with mock.patch("widget.capture_ui._frozen", True):
                sounds.play("complete")
            self.assertEqual(play.call_count, 1)


class SoundInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = QWidget()
        self.host.resize(300, 200)
        self.host.show()
        self.app.processEvents()
        self.buttons = []
        self.play = self.enterContext(mock.patch.object(sounds, "play"))
        self.enterContext(mock.patch.object(FrameClock, "default_host", None))
        self.enterContext(mock.patch.object(native, "reduce_motion", return_value=True))

    def tearDown(self):
        self.host.hide()
        self.host.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def add(self, button):
        button.setParent(self.host)
        button.resize(button.sizeHint().expandedTo(button.minimumSize()))
        button.move(40, 40)
        button.show()
        self.buttons.append(button)
        self.app.processEvents()
        return button

    def click(self, button):
        QTest.mouseClick(button, Qt.LeftButton, pos=button.rect().center())

    def finish_hold(self, button):
        button.driver._timer.stop()
        button.driver._t0 -= 1
        button.driver._tick()

    def test_mouse_keyboard_and_immediate_hide_emit_once_after_commit(self):
        button = self.add(MotionButton("Go"))
        QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
        self.play.assert_not_called()
        QTest.mouseRelease(button, Qt.LeftButton, pos=button.rect().center())
        QTest.keyClick(button, Qt.Key_Space)
        button.clicked.connect(button.hide)
        self.click(button)
        self.assertEqual(self.play.call_args_list, [mock.call("tap")] * 3)

    def test_selected_choices_and_programmatic_state_sync_are_silent(self):
        button = self.add(SelectPill("English"))
        group = QButtonGroup(self.host)
        group.addButton(button)
        button.setChecked(True)
        self.click(button)
        alternate = self.add(SelectPill("中文"))
        group.addButton(alternate)
        alternate.setChecked(True)
        self.click(button)
        self.click(button)
        self.assertEqual(self.play.call_args_list, [mock.call("tap")])
        # ControlsPanel 的按钮用回调恢复当前选中项，未使用 exclusive group。
        other = self.add(SelectPill("Walking"))
        other.setChecked(True)
        other.clicked.connect(lambda: other.setChecked(True))
        self.click(other)
        self.assertEqual(self.play.call_count, 1)

    def test_switch_has_only_direction_sound_even_when_toggled_hides_it(self):
        button = self.add(Switch())
        button.set_silently(True)
        button.set_silently(False)
        button.toggled.connect(button.hide)
        self.click(button)
        button.show()
        QTest.keyClick(button, Qt.Key_Space)
        self.assertEqual(self.play.call_args_list, [mock.call("switch-on"), mock.call("switch-off")])

    def test_programmatic_mutual_exclusion_is_silent(self):
        first, second = self.add(Switch()), self.add(Switch())
        second.setChecked(True)
        first.toggled.connect(lambda _: second.setChecked(False))
        self.click(first)
        self.assertEqual(self.play.call_args_list, [mock.call("switch-on")])

    def test_immediate_cpp_deletion_in_callbacks_does_not_lose_sound(self):
        import shiboken6
        normal = self.add(MotionButton("Close"))
        normal.clicked.connect(lambda: shiboken6.delete(normal))
        self.click(normal)
        toggle = self.add(Switch())
        toggle.toggled.connect(lambda: shiboken6.delete(toggle))
        self.click(toggle)
        hold = self.add(HoldPill("Install"))
        hold.held.connect(lambda: shiboken6.delete(hold))
        QTest.mousePress(hold, Qt.LeftButton, pos=hold.rect().center())
        self.finish_hold(hold)
        self.assertEqual(self.play.call_args_list,
                         [mock.call("tap"), mock.call("switch-on"), mock.call("complete")])

    def test_toggle_icons_sound_in_both_directions(self):
        icon = self.add(FlatIcon("tune"))
        self.click(icon)
        self.click(icon)
        self.assertEqual(self.play.call_args_list, [mock.call("tap")] * 2)

    def test_checkable_action_reopens_with_one_sound_even_when_already_selected(self):
        button = self.add(Swatch("transparent"))
        button.SOUND_KIND = "action"
        group = QButtonGroup(self.host)
        group.addButton(button)
        opened = mock.Mock()
        button.clicked.connect(opened)
        self.click(button)
        self.click(button)
        QTest.keyClick(button, Qt.Key_Space)
        self.assertTrue(button.isChecked())
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(self.play.call_args_list, [mock.call("tap")] * 3)

    def test_cancel_disabled_drag_out_and_screenshot_have_no_click_sound(self):
        button = self.add(MotionButton("Go"))
        button.setEnabled(False)
        self.click(button)
        button.setEnabled(True)
        QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
        QTest.mouseMove(button, QPoint(-20, -20))
        QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-20, -20))
        with mock.patch("widget.capture_ui._frozen", True):
            self.click(button)
            QTest.keyClick(button, Qt.Key_Space)
        self.play.assert_not_called()

    def test_hold_completion_plays_once_before_immediate_hide_or_delete(self):
        for factory in (lambda: HoldPill("Install"), lambda: HoldButton("Quit"), lambda: IconButton("power", hold=True)):
            button = self.add(factory())
            button.held.connect(button.hide)
            button.held.connect(button.deleteLater)
            QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
            self.finish_hold(button)
            self.finish_hold(button)
            QTest.mouseRelease(button, Qt.LeftButton, pos=button.rect().center())
        self.assertEqual(self.play.call_args_list, [mock.call("complete")] * 3)

    def test_keyboard_hold_and_early_release(self):
        button = self.add(HoldPill("Install"))
        QTest.keyClick(button, Qt.Key_Space)
        self.play.assert_not_called()
        QTest.keyPress(button, Qt.Key_Space)
        self.finish_hold(button)
        QTest.keyRelease(button, Qt.Key_Space)
        self.assertEqual(self.play.call_args_list, [mock.call("complete")])

    def test_cancelled_holds_never_complete_or_tap(self):
        for cancel in (lambda b: b.hide(), lambda b: b.setEnabled(False),
                       lambda b: QTest.mouseMove(b, QPoint(-20, -20)), lambda b: b.driver.cancel()):
            button = self.add(HoldPill("Delete"))
            QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
            cancel(button)
            self.finish_hold(button)
            QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(-20, -20))
        button = self.add(HoldPill("Delete"))
        QTest.mousePress(button, Qt.LeftButton, pos=button.rect().center())
        with mock.patch("widget.capture_ui._frozen", True):
            self.finish_hold(button)
        self.play.assert_not_called()

    def test_dial_spacing_and_fast_gain_match_approved_audition(self):
        from widget.dial import DialPane
        dial = DialPane(mock.Mock())
        try:
            with mock.patch("widget.dial.time.perf_counter", side_effect=[1.0, 1.030, 1.056, 1.146, 1.426]):
                for value in (1, 2, 3, 4, 5):
                    dial._set_pos(value, audible=True)
            self.assertEqual(self.play.call_count, 4, "小于55ms的跨格没有额外声")
            gains = [call.args[1] for call in self.play.call_args_list]
            self.assertAlmostEqual(gains[0], 1.0)
            self.assertAlmostEqual(gains[1], .75 + .25 * (.056 - .055) / .065)
            self.assertAlmostEqual(gains[2], .75 + .25 * (.090 - .055) / .065)
            self.assertAlmostEqual(gains[3], 1.0)
        finally:
            dial.deleteLater()

    def test_dial_programmatic_sync_open_and_settle_never_add_sound(self):
        from widget.dial import DialPane
        window = mock.Mock()
        window.dog.manual_progress.return_value = None
        dial = DialPane(window)
        try:
            dial.set_progress(1.0)
            dial.fit_to(350)
            dial._set_pos(5.7)
            dial.settle_now()
            dial.snap(2)
            dial.settle_now()
            dial._settled()
            self.play.assert_not_called()
        finally:
            dial._bar.stop()
            dial.deleteLater()

    def test_hiding_parent_stops_dial_inertia_sound_and_old_drag(self):
        from widget.dial import DialPane
        window = mock.Mock()
        window.dog.manual_progress.return_value = None
        window.accent_color.return_value = "#665544"
        dial = DialPane(window)
        dial.setParent(self.host)
        dial.show()
        dial.set_progress(1.0)
        dial._set_pos(4.0)
        dial.vel = 12.0
        dial._last_tick = time.perf_counter()
        dial._press = (100.0, 100.0, dial._last_tick)
        dial._inertia.start()
        self.host.hide()
        QTest.qWait(250)
        self.assertEqual(dial.pos_, 4.0)
        self.assertEqual(dial.vel, 0.0)
        self.assertFalse(dial._inertia.isActive())
        self.assertFalse(dial._settle.isActive())
        self.assertIsNone(dial._press)
        self.play.assert_not_called()
        window.do_action.assert_not_called()
        self.host.show()
        QTest.mouseMove(dial, QPoint(100, 150))
        self.assertEqual(dial.pos_, 4.0, "重新打开不继承上次未松开的拖动")

    def test_cancelling_dial_interaction_stops_pending_settle_and_snap(self):
        from widget.dial import DialPane
        window = mock.Mock()
        window.dog.manual_progress.return_value = None
        dial = DialPane(window)
        try:
            dial.set_progress(1.0)
            dial._set_pos(2.6)
            dial.snap()
            dial._settle.start()
            dial.cancel_interaction()
            QTest.qWait(220)
            self.assertEqual(dial.pos_, 2.6)
            self.assertFalse(dial._settle.isActive())
            self.play.assert_not_called()
            window.do_action.assert_not_called()
        finally:
            dial._bar.stop()
            dial.deleteLater()


class NativeSoundTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(native, "_sounds", {}))
        self.enterContext(mock.patch.object(native, "_sound_index", {}))
        self.enterContext(mock.patch.object(native.sys, "platform", "darwin"))

    def test_offscreen_never_loads_sound_backend(self):
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="offscreen"), \
                mock.patch.object(native.ctypes, "CDLL") as load:
            self.assertFalse(native.play_sound("test.wav"))
            load.assert_not_called()

    def test_stop_only_touches_loaded_pool_and_survives_a_backend_failure(self):
        with mock.patch.object(native, "prepare_sound") as prepare, \
                mock.patch.object(native, "_msg_send", side_effect=[RuntimeError, True, True]) as send:
            native.stop_sound("missing.wav")
            send.assert_not_called()
            native._sounds["loaded.wav"] = [1, 2, 3]
            native.stop_sound("loaded.wav")
            self.assertEqual([call.args for call in send.call_args_list],
                             [(1, "stop"), (2, "stop"), (3, "stop")])
            prepare.assert_not_called()

    def test_native_pool_is_preloaded_reused_and_volume_cannot_exceed_original(self):
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(native.ctypes, "CDLL"), mock.patch.object(native, "_class", return_value=1), \
                mock.patch.object(native, "_nsstring", return_value=2), mock.patch.object(native, "_msg_send", return_value=3) as send:
            self.assertTrue(native.prepare_sound("test.wav"))
            self.assertTrue(native.play_sound("test.wav", 5.0))
            self.assertTrue(native.play_sound("test.wav", .75))
            loads = [c for c in send.call_args_list if c.args[1] == "initWithContentsOfFile:byReference:"]
            self.assertEqual(len(loads), 3)
            self.assertTrue(all(c.args[3] is False for c in loads), "预载进内存，不在点击时读文件")
            volumes = [c.args[2].value for c in send.call_args_list if c.args[1] == "setVolume:"]
            self.assertEqual(volumes, [1.0, .75])

    def test_with_the_sound_thread_the_main_thread_only_queues(self):
        """声音在后台线上放（NSSound 的 stop + play 在主线程上每次占 9～15 毫秒，滑动条每过一只就掉一帧）。
        主线程只排队；停和放排同一条队，先后不乱；排太久才轮到的不放了。"""
        import queue
        jobs = queue.SimpleQueue()
        native._sounds["a.wav"], native._sound_index["a.wav"] = [1, 2, 3], 0
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(native, "_sound_queue", jobs), mock.patch.object(native, "_msg_send", return_value=True) as send:
            self.assertTrue(native.play_sound("a.wav", 0.5))
            native.stop_sound("a.wav")
            send.assert_not_called()                              # 主线程上一次 NSSound 都没碰
            got = [jobs.get_nowait() for _ in range(4)]
            self.assertTrue(jobs.empty())
            self.assertEqual([job[:2] for job in got], [("play", 1), ("stop", 1), ("stop", 2), ("stop", 3)])
            native._sound_job(*got[0])
            self.assertEqual([c.args[1] for c in send.call_args_list], ["stop", "setVolume:", "play"])
            send.reset_mock()
            native._sound_job("play", 1, 0.5, got[0][3] - 10.0)     # 排了 10 秒才轮到
            send.assert_not_called()
            native._sound_job("stop", 2, 0.0, 0.0)                  # 停不看排了多久
            self.assertEqual([c.args for c in send.call_args_list], [(2, "stop")])

    def test_ramps_go_smoothly_from_one_volume_to_the_other(self):
        self.assertEqual(native.ramp_volume(0.0, 0.35, 0.0, 0.4), 0.0)
        self.assertEqual(native.ramp_volume(0.0, 0.35, 0.4, 0.4), 0.35)
        self.assertEqual(native.ramp_volume(0.0, 0.35, 9.0, 0.4), 0.35)
        ups = [native.ramp_volume(0.0, 0.35, k * 0.02, 0.4) for k in range(21)]
        self.assertEqual(ups, sorted(ups), "淡入一路往上")
        downs = [native.ramp_volume(0.35, 0.0, k * 0.025, 0.5) for k in range(21)]
        self.assertEqual(downs, sorted(downs, reverse=True), "淡出一路往下")
        self.assertEqual(native.ramp_volume(0.3, 0.0, 0.1, 0.0), 0.0, "0 秒 = 当场到")

    def test_fades_run_on_the_sound_thread_without_holding_up_the_queue(self):
        """吃的声音 0.4 秒淡入、0.5 秒淡出——在声音线上一步步调音量，不睡在那一件事里（排在后面的声音还是马上放，不会排太久被丢）。"""
        native._ramps.clear()
        self.addCleanup(native._ramps.clear)
        volume = {"v": 0.0}

        def send(snd, sel, *args, **kw):
            if sel == "setVolume:":
                volume["v"] = args[0].value
            if sel == "volume":
                return volume["v"]
            return True
        with mock.patch.object(native, "_msg_send", side_effect=send), mock.patch.object(native.time, "monotonic", return_value=100.0):
            native._sound_job("play", 7, 0.35, 100.0, 0.0, 0.4)
            self.assertEqual(volume["v"], 0.0, "淡入：从 0 开始放")
            self.assertEqual(len(native._ramps), 1)
        with mock.patch.object(native, "_msg_send", side_effect=send), mock.patch.object(native.time, "monotonic", return_value=100.2):
            native._step_ramps()
            self.assertTrue(0.0 < volume["v"] < 0.35, "走到一半")
        with mock.patch.object(native, "_msg_send", side_effect=send), mock.patch.object(native.time, "monotonic", return_value=100.5):
            native._step_ramps()
            self.assertEqual((round(volume["v"], 6), native._ramps), (0.35, []), "到了设定的音量，不再调")
        stops = []
        with mock.patch.object(native, "_msg_send", side_effect=lambda snd, sel, *a, **k: stops.append(sel) if sel == "stop" else send(snd, sel, *a, **k)), \
                mock.patch.object(native.time, "monotonic", return_value=200.0):
            native._sound_job("fade", 7, 0.5, 0.0, 0.0)
            self.assertEqual((stops, len(native._ramps)), ([], 1), "淡出排上了，这一件马上就回来")
        with mock.patch.object(native, "_msg_send", side_effect=lambda snd, sel, *a, **k: stops.append(sel) if sel == "stop" else send(snd, sel, *a, **k)), \
                mock.patch.object(native.time, "monotonic", return_value=200.6):
            native._step_ramps()
            self.assertEqual((volume["v"], stops, native._ramps), (0.0, ["stop"], []), "淡到 0 停掉")

    def test_the_sound_thread_only_starts_on_a_real_screen(self):
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="offscreen"), \
                mock.patch.object(native.threading, "Thread") as thread:
            self.assertFalse(native.start_sound_thread())
            thread.assert_not_called()
            self.assertIsNone(native._sound_queue, "单测里声音照旧当场放（上面几条测的就是）")

    def test_missing_backend_is_cached_and_no_hardware_failure_escapes(self):
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(native.ctypes, "CDLL", side_effect=OSError) as load:
            self.assertFalse(native.play_sound("test.wav"))
            self.assertFalse(native.play_sound("test.wav"))
            self.assertEqual(load.call_count, 1)
        native._sounds["loaded.wav"], native._sound_index["loaded.wav"] = [1, 2, 3], 0
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(native, "_msg_send", side_effect=RuntimeError):
            self.assertFalse(native.play_sound("loaded.wav"))
        with mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(native, "_msg_send", return_value=False):
            self.assertFalse(native.play_sound("loaded.wav"))
