"""系统选区截图只锁界面：视觉快照、交互取消和狗的实时动画分别验证。"""
from unittest import mock

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from tests.panel_base import PanelCase
from widget import capture_ui, native
from widget.widgets import StickerTip


class CaptureUITests(PanelCase):
    def setUp(self):
        super().setUp()
        self.capture = self.win.capture_ui
        self.capture.timer.stop()
        self.settings.show()
        self.settings.finish_animations()
        self.app.processEvents()

    def tearDown(self):
        self.capture.end()
        self.capture.timer.stop()
        self.app.removeEventFilter(self.capture)
        super().tearDown()

    def test_nothing_is_asked_while_the_dog_is_being_flung(self):
        """录到的：问系统要窗口列表、抓画面，真甩的时候一次能卡一百多毫秒。截图选区这时不会出现，先不问。"""
        with mock.patch.object(self.win, "_flinging", return_value=True), mock.patch.object(native, "screenshot_selection_active") as asked:
            self.capture.poll()
            asked.assert_not_called()
            with mock.patch.object(self.capture, "_snapshots") as grabbed:
                self.capture.remember()
                grabbed.assert_not_called()
        with mock.patch.object(native, "screenshot_selection_active", return_value=False) as asked:
            self.capture.poll()
            asked.assert_called_once()

    def test_the_dog_layer_windows_keep_drawing_and_are_not_grabbed(self):
        """另一半狗、球、捡球的圈（owner.live_windows）截图时照常画：不抓（抓一次要把它们整个重画一遍读回来，开着卡片时一次 6～11 毫秒），
        也不换成快照、不藏。别的窗口照旧。"""
        live, other = QWidget(), QWidget()
        for w in (live, other):
            w.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
            w.resize(40, 30)
            w.show()
            self.addCleanup(w.close)
            self.addCleanup(w.deleteLater)
        with mock.patch.object(self.win, "live_windows", create=True, return_value=[live]):
            sources = {shot.source() for shot in self.capture._snapshots() if shot.source is not None}
            self.assertIn(other, sources)
            self.assertNotIn(live, sources)
            with mock.patch.object(live, "grab") as grabbed:
                self.capture.begin()
                grabbed.assert_not_called()
            self.assertEqual(live.windowOpacity(), 1.0, "照常显示，不是藏起来换成快照")
            self.assertEqual(other.windowOpacity(), 0.0, "别的窗口照旧换成快照")
        self.capture.end()
        self.assertEqual(other.windowOpacity(), 1.0)

    def test_the_window_lists_its_dog_layer_windows(self):
        """window.live_windows：每块屏的另一半狗都算；球、捡球的圈看得见才算（藏着的不在画面上，抓不抓都一样）。"""
        win, pg = self.win, self.win.playground
        ghost, ball, ring, hidden_ring = QWidget(), QWidget(), QWidget(), QWidget()
        for w in (ghost, ball, ring, hidden_ring):
            self.addCleanup(w.deleteLater)
        ball.show()
        ring.show()
        self.addCleanup(ball.hide)
        self.addCleanup(ring.hide)
        with mock.patch.dict(win._ghosts, {"LG": ghost}, clear=True), \
                mock.patch.dict(pg.ring_wins, {"LG": ring, "MacBook": hidden_ring}, clear=True), \
                mock.patch.object(pg, "ball_win", ball):
            self.assertEqual(set(win.live_windows()), {ghost, ball, ring})
            ball.hide()
            self.assertNotIn(ball, win.live_windows())

    def _card_layer(self):
        return next(layer for layer in self.capture.layers if layer.geometry() == self.settings.geometry())

    def _show_tip(self):
        tip = StickerTip()
        tip.show_for(self.settings.lang_buttons['en'], 'Keep this explanation visible')
        tip._clock.stop()
        tip._pop = 1.0
        self.addCleanup(tip.close)
        self.addCleanup(tip.deleteLater)
        return tip

    def test_tooltip_keeps_its_window_level_even_when_source_order_is_reversed(self):
        tip = self._show_tip()
        tip.move(self.settings.mapToGlobal(QPoint(20, 60)))
        expected = tip.grab().toImage()
        # QWidget顶层列表不保证z顺序：故意把气泡放在会盖住它的卡片之前。
        with mock.patch.object(QApplication, 'topLevelWidgets', return_value=[tip, self.settings]):
            self.capture.begin()
        layer = next(layer for layer in self.capture.layers if layer.geometry() == tip.geometry())
        self.assertEqual(layer.windowType(), Qt.ToolTip)
        self.assertIs(self.capture.layers[-1], layer)
        self.assertEqual(layer.image.toImage(), expected)
        self.assertTrue(layer.isVisible())
        self.assertEqual(tip.windowOpacity(), 0, '原气泡不能与快照重复叠画')

    def test_cascading_departures_cannot_replace_the_first_hover_and_tip_picture(self):
        tip = self._show_tip()
        button = self.settings.lang_buttons['en']
        button.motion.hover.set_target(1, instant=True)
        expected_card = self.settings.grab().toImage()
        expected_tip = tip.grab().toImage()
        with mock.patch('widget.capture_ui.time.monotonic', return_value=10):
            self.capture.remember()
        button.motion.cancel(instant=True)
        tip.hide()
        # 一个真实失焦会给按钮、父卡片和气泡各发事件；不能每次重拍覆盖。
        with mock.patch('widget.capture_ui.time.monotonic', return_value=10.1):
            self.capture.remember()
        with mock.patch('widget.capture_ui.time.monotonic', return_value=10.6):
            self.capture.begin()
        self.assertEqual(self._card_layer().image.toImage(), expected_card)
        layer = next(layer for layer in self.capture.layers if layer.windowType() == Qt.ToolTip)
        self.assertEqual(layer.image.toImage(), expected_tip)

    def test_tooltip_hide_before_selection_poll_preserves_its_last_visible_frame(self):
        tip = self._show_tip()
        tip._pop = .6
        expected = tip.grab().toImage()
        self.capture.enabled = True
        self.capture._listen(True)
        with mock.patch.object(native, 'screenshot_selection_active', return_value=False):
            with mock.patch('widget.capture_ui.time.monotonic', return_value=20):
                tip.hide()                         # 同气泡的鼠标看门定时器先收起它
        self.assertFalse(tip.isVisible())
        self.assertEqual(tip._pop, 1.0, '气泡自身hideEvent已执行，但缓存应保留之前的绘制状态')
        with mock.patch.object(native, 'screenshot_selection_active', return_value=True):
            with mock.patch('widget.capture_ui.time.monotonic', return_value=20.2):
                self.capture.poll()
        layer = next(layer for layer in self.capture.layers if layer.windowType() == Qt.ToolTip)
        self.assertEqual(layer.image.toImage(), expected)
        self.assertTrue(layer.isVisible())

    def test_real_interaction_discards_a_departure_candidate(self):
        tip = self._show_tip()
        self.capture.remember()
        tip.hide()
        self.capture.enabled = True
        with mock.patch.object(native, 'screenshot_selection_active', return_value=False):
            self.capture.eventFilter(self.settings, QEvent(QEvent.MouseMove))
        self.capture.begin()
        self.assertFalse(any(layer.windowType() == Qt.ToolTip for layer in self.capture.layers),
                         '离开后继续正常操作，之后的截图不能带回旧提示')

    def test_recent_pre_leave_snapshot_stays_unchanged_until_capture_ends(self):
        button = self.settings.lang_buttons['en']
        button.motion.hover.set_target(1, instant=True)
        button.motion.direction_x.set_target(.7, instant=True)
        before = self.settings.grab().toImage()
        with mock.patch('widget.capture_ui.time.monotonic', return_value=10):
            self.capture.remember()
        button.motion.hover.set_target(0, instant=True)
        button.setText('Changed underneath')
        with mock.patch('widget.capture_ui.time.monotonic', return_value=10.2):
            self.capture.begin()
        self.assertTrue(capture_ui.ui_frozen())
        layer = self._card_layer()
        self.assertEqual(layer.image.toImage(), before, '系统选区出现前的悬停画面完整保留')
        self.app.sendEvent(button, QEvent(QEvent.Leave))
        self.app.processEvents()
        self.assertEqual(layer.image.toImage(), before, '底层重绘不能修改已锁定的画面')
        self.assertTrue(layer.testAttribute(Qt.WA_TransparentForMouseEvents))
        self.capture.end()
        self.assertFalse(capture_ui.ui_frozen())
        self.assertEqual(self.capture.layers, [])
        self.assertFalse(layer.isVisible())

    def test_stale_candidate_is_not_used_for_a_later_screenshot(self):
        with mock.patch('widget.capture_ui.time.monotonic', return_value=10):
            self.capture.remember()
        button = self.settings.lang_buttons['en']
        button.motion.hover.set_target(1, instant=True)
        button.motion.direction_x.set_target(.7, instant=True)
        before = self.settings.grab().toImage()
        with mock.patch('widget.capture_ui.time.monotonic', return_value=11):
            self.capture.begin()
        self.assertEqual(self._card_layer().image.toImage(), before,
                         '旧的失焦缓存过期后，使用截图开始时的新画面')

    def test_frozen_layer_replaces_translucent_card_without_changing_its_state(self):
        self.settings.setWindowOpacity(.5)
        opacity = self.settings.windowOpacity()
        page = self.settings.page
        self.capture.begin()
        layer = self._card_layer()
        self.assertTrue(self.settings.isVisible(), '不能hide原窗口，避免触发页面和更新状态重置')
        self.assertEqual(self.settings.windowOpacity(), 0, '原卡片不能继续在快照下面重复叠画阴影和透明边缘')
        self.assertAlmostEqual(layer.windowOpacity(), opacity, delta=1/255)
        self.assertEqual(self.settings.page, page)
        self.capture.end()
        self.assertTrue(self.settings.isVisible())
        self.assertEqual(self.settings.page, page)
        self.assertAlmostEqual(self.settings.windowOpacity(), opacity, delta=1/255)

    def test_deleted_source_does_not_break_restoration_of_surviving_cards(self):
        old = QWidget()
        old.setWindowOpacity(.6)
        old.show()
        self.capture.begin()
        self.assertEqual(old.windowOpacity(), 0)
        old.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.capture.end()                  # Python包装还在，但C++窗口已经销毁
        self.assertTrue(self.settings.isVisible())
        self.assertEqual(self.settings.windowOpacity(), 1)

    def test_download_prompt_uses_existing_retry_after_capture_ends(self):
        from widget.updater import Release
        self.win.show()
        self.win.updater.state = 'downloaded'
        self.win.updater.release = Release('0.6.0', 99, 'v0.6.0-b99', 'https://example.invalid/update.dmg',
                                          1024, '', 'update.dmg', '', '')
        self.capture.begin()
        with mock.patch.object(native, 'window_occluded', return_value=False):
            self.win._update_ready()
            self.assertTrue(self.win._prompt_wait.isActive())
            self.assertIsNone(self.win.update_prompt, '截图期间不创建会弹出的新卡片')
            self.win._prompt_wait.timeout.emit()
            self.assertIsNone(self.win.update_prompt)
            self.capture.end()
            self.win._prompt_wait.timeout.emit()
        self.assertIsNotNone(self.win.update_prompt)
        self.assertTrue(self.win.update_prompt.isVisible())
        self.assertFalse(self.win._prompt_wait.isActive())

    def test_capture_does_not_stop_the_dog_update_or_replay_a_screenshot_drag(self):
        self.win.show()
        self.win.set_dynamic(True)
        self.capture.begin()
        images = [layer.image.toImage() for layer in self.capture.layers]
        with mock.patch.object(self.win.dog, 'update', wraps=self.win.dog.update) as advance:
            for _ in range(3):
                self.win._last_tick -= .03
                self.win._tick()
            self.assertEqual(advance.call_count, 3, '截图时狗的实时动画照常推进')
            self.assertTrue(all(call.args[0] > 0 for call in advance.call_args_list))
        self.assertEqual([layer.image.toImage() for layer in self.capture.layers], images)
        self.capture.end()

    def test_snapshot_cancels_existing_hold_and_blocks_new_clicks_and_slider_drag(self):
        hold = self.settings.quit_button
        clicks, holds = [], []
        self.settings.follow.clicked.connect(lambda *_: clicks.append(True))
        hold.held.connect(lambda: holds.append(True))
        QTest.mousePress(hold, Qt.LeftButton, pos=hold.rect().center())
        self.assertTrue(hold.driver._down)
        self.capture.begin()
        self.assertFalse(hold.driver._down, '保存画面后立刻取消真实长按')
        with mock.patch.object(self.win, '_quit') as quit_app:
            hold.driver._tick()
            QTest.mouseRelease(hold, Qt.LeftButton, pos=hold.rect().center())
            QTest.mouseClick(self.settings.follow, Qt.LeftButton)
            slider = self.settings.size_slider
            before = slider.value
            QTest.mousePress(slider, Qt.LeftButton, pos=QPoint(slider.width()-12, slider.height()//2))
            QTest.mouseRelease(slider, Qt.LeftButton, pos=QPoint(12, slider.height()//2))
            self.assertEqual(slider.value, before)
            self.assertFalse(slider.adjusting)
            self.assertEqual(clicks, [])
            self.assertEqual(holds, [])
            quit_app.assert_not_called()
        self.assertIsNone(self.win._drag)

    def test_capture_finishes_an_in_progress_slider_drag_without_replaying_release(self):
        slider = self.settings.size_slider
        QTest.mousePress(slider, Qt.LeftButton, pos=QPoint(round(slider._thumb_x()), slider.height() // 2))
        self.assertTrue(slider.adjusting)
        value = slider.value
        self.capture.begin()
        self.assertFalse(slider.adjusting)
        self.assertFalse(slider._pointer_drag._active)
        self.assertFalse(self.win._scale_adjusting)
        QTest.mouseRelease(slider, Qt.LeftButton, pos=QPoint(slider.width() - 4, slider.height() // 2))
        self.capture.end()
        QTest.mouseMove(slider, QPoint(4, slider.height() // 2))
        self.assertEqual(slider.value, value, '截图释放和恢复后的鼠标移动都不能补做之前的缩放')

    def test_capture_resume_does_not_hover_the_blank_part_of_the_update_region(self):
        self.settings.show_page('advanced', animated=False)
        self.settings.finish_animations()
        self.app.processEvents()
        button = self.settings.update_button
        button.set_status('检查更新', True, animated=False)
        blank = QPoint(4, button.height() // 2)
        self.assertFalse(button.motion.hit(blank))
        self.capture.begin()
        with mock.patch('widget.capture_ui.QCursor.pos', return_value=button.mapToGlobal(blank)):
            with mock.patch.object(button, 'underMouse', return_value=True):
                self.capture.end()
        self.assertEqual(button.motion.hover.target, 0)
        self.assertEqual(button.cursor().shape(), Qt.ArrowCursor)

    def test_detected_selection_has_one_lifecycle_and_exit_grace(self):
        if not self.capture.enabled:
            self.assertFalse(self.capture._listening, '非 macOS 环境空闲时不注册全局事件过滤器')
        with mock.patch.object(native, 'screenshot_selection_active', return_value=True):
            self.capture.poll()
            self.assertTrue(self.capture._listening)
            first = list(self.capture.layers)
            self.capture.poll()
            self.assertEqual(self.capture.layers, first, '同一次选区不重复建快照窗口')
        with mock.patch.object(native, 'screenshot_selection_active', return_value=False):
            with mock.patch('widget.capture_ui.time.monotonic', return_value=20):
                self.capture.poll()
            with mock.patch('widget.capture_ui.time.monotonic', return_value=20.08):
                self.capture.poll()
                self.assertTrue(self.capture.active, '给系统合成截图留下短暂收尾时间')
            with mock.patch('widget.capture_ui.time.monotonic', return_value=20.2):
                self.capture.poll()
        self.assertFalse(self.capture.active)
        self.assertFalse(capture_ui.ui_frozen())
        self.assertEqual(self.capture.layers, [])
        if not self.capture.enabled:
            self.assertFalse(self.capture._listening, '截图结束后释放临时事件过滤器')


class ScreenshotProbeTests(PanelCase):
    """native.screenshot_selection_active：没有截图的进程就不问窗口列表（问一次要等窗口系统，狗在跑时平均 6.5 毫秒、最长 95）。"""

    def _fake_objc(self):
        """截图服务没在跑：NSRunningApplication 查出来 0 个。"""
        return (mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"),
                mock.patch.object(native.sys, "platform", "darwin"),
                mock.patch.object(native, "_class", return_value=1),
                mock.patch.object(native, "_nsstring", return_value=1),
                mock.patch.object(native, "_msg_send", return_value=0))

    def test_no_screenshot_process_means_the_window_list_is_not_asked(self):
        patches = self._fake_objc()
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        real = native.ctypes.CDLL
        with mock.patch.object(native, "_screencapture_cli_pids", return_value=frozenset()), \
                mock.patch.object(native.ctypes, "CDLL", side_effect=real) as dll:
            self.assertFalse(native.screenshot_selection_active())
            self.assertFalse(any("ApplicationServices" in str(c.args[0]) for c in dll.call_args_list), "没有截图的进程：不该去问窗口列表")
        with mock.patch.object(native, "_screencapture_cli_pids", return_value=frozenset({4242})), \
                mock.patch.object(native.ctypes, "CDLL", side_effect=OSError) as dll:
            self.assertFalse(native.screenshot_selection_active())
            dll.assert_called()                                # 命令行截图在跑：照旧去看选区窗口
        with mock.patch.object(native, "_screencapture_cli_pids", return_value=None), \
                mock.patch.object(native.ctypes, "CDLL", side_effect=OSError) as dll:
            native.screenshot_selection_active()
            dll.assert_called()                                # 数不了进程：当它可能在，照旧去看

    def test_while_the_screenshot_service_runs_the_window_list_is_asked(self):
        """最常见的：截图服务（com.apple.screencaptureui，Cmd+Shift+4/5）在跑、没有命令行截图：照旧去看选区窗口。"""
        def msg(receiver, selector, *args, **kw):
            return {"count": 1, "processIdentifier": 4242}.get(selector, 7)
        for p in (mock.patch.object(native.QGuiApplication, "platformName", return_value="cocoa"),
                  mock.patch.object(native.sys, "platform", "darwin"),
                  mock.patch.object(native, "_class", return_value=1),
                  mock.patch.object(native, "_nsstring", return_value=1),
                  mock.patch.object(native, "_msg_send", side_effect=msg)):
            p.start()
            self.addCleanup(p.stop)
        with mock.patch.object(native, "_screencapture_cli_pids", return_value=frozenset()), \
                mock.patch.object(native.ctypes, "CDLL", side_effect=OSError) as dll:
            self.assertFalse(native.screenshot_selection_active())
            self.assertTrue(any("ApplicationServices" in str(c.args[0]) for c in dll.call_args_list), "截图服务在跑：要去问窗口列表")

    def test_the_command_line_screencapture_is_counted_from_the_process_table_and_cached_briefly(self):
        native._screencapture_cli.update(at=float("-inf"), pids=frozenset())
        first = native._screencapture_cli_pids()
        self.assertIsInstance(first, frozenset)
        self.assertNotIn(0, first)
        with mock.patch.object(native, "_libproc", side_effect=AssertionError("0.3 秒内不该再数")):
            self.assertEqual(native._screencapture_cli_pids(), first)
        self.assertLess(native.SCREENCAPTURE_SCAN_S, capture_ui.CaptureUI.CANDIDATE_SECONDS / 2,
                        "数进程的间隔要远短于候选画面留的时间，不然命令行截图的选区认出来时候选已经过期")
        native._screencapture_cli.update(at=float("-inf"))
        with mock.patch.object(native, "_libproc", side_effect=OSError):
            self.assertIsNone(native._screencapture_cli_pids(), "数不了：返回 None（当它可能在）")
        native._screencapture_cli.update(at=float("-inf"))
        failing = mock.Mock()
        failing.proc_listpids.return_value = 0                # libproc 出错时返回 0
        with mock.patch.object(native, "_libproc", return_value=failing):
            self.assertIsNone(native._screencapture_cli_pids(), "进程表列不出来：也是 None，不能当成「没有」记 0.3 秒")
        self.assertEqual(native._screencapture_cli["at"], float("-inf"), "出错不记")
        native._screencapture_cli.update(at=float("-inf"), pids=frozenset())
