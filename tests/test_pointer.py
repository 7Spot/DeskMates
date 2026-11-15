"""原生精细拖动的语义：只消费当前控件手势，Qt 回退不重复计数。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from widget import pointer


class PointerDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.owner = QWidget()
        self.owner.show()
        self.app.processEvents()
        self.moves = []
        self.drag = pointer.PointerDrag(self.owner, lambda point, now: self.moves.append((point, now)))
        self.press = self.event(QEvent.MouseButtonPress, QPointF(1690.125, 700.75), 12000)
        self.origin = pointer._Sample(1, 77, 12.0, 1, 1690.125, 739.25)

    def tearDown(self):
        self.drag.end()
        self.owner.close()
        self.owner.deleteLater()
        self.app.processEvents()

    @staticmethod
    def event(kind, point, stamp):
        e = QMouseEvent(kind, QPointF(32, 13), point, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        e.setTimestamp(stamp)
        return e

    def begin(self, sample=None):
        with mock.patch.object(pointer.QGuiApplication, "platformName", return_value="cocoa"), \
                mock.patch.object(pointer.native, "_nsapp", return_value=42), \
                mock.patch.object(pointer.native, "_msg_send", side_effect=lambda _receiver, sel: 77 if sel == "window" else 99), \
                mock.patch.object(pointer, "_sample", return_value=sample or self.origin):
            self.drag.begin(self.press)

    def deliver(self, sample, message_type=b"mac_generic_NSEvent"):
        with mock.patch.object(pointer, "_sample", return_value=sample):
            return self.drag.nativeEventFilter(message_type, 99)

    def test_non_cocoa_uses_qt_without_reading_native_state(self):
        with mock.patch.object(pointer.QGuiApplication, "platformName", return_value="offscreen"), \
                mock.patch.object(pointer.native, "_nsapp") as app:
            self.drag.begin(self.press)
        app.assert_not_called()
        self.assertFalse(self.drag.move(self.press))

    def test_stale_or_other_window_press_cannot_enable_native_path(self):
        for sample in (pointer._Sample(1, 77, 11.999, 1, 1690.125, 739.25),
                       pointer._Sample(1, 88, 12.0, 1, 1690.125, 739.25),
                       pointer._Sample(6, 77, 12.0, 1, 1690.125, 739.25)):
            with self.subTest(sample=sample):
                self.begin(sample)
                self.deliver(pointer._Sample(6, 77, 12.02, 2, 1690.135, 739.25))
                self.assertEqual(self.moves, [])

    def test_tiny_native_moves_arrive_once_and_match_qt_coordinates(self):
        self.begin()
        for number, dx in enumerate((0.01, 0.011, 0.011125), 2):
            sample = pointer._Sample(6, 77, 12 + number * .02, number, self.origin.x + dx, self.origin.y + .001)
            self.assertEqual(self.deliver(sample), (False, 0))
            self.deliver(sample)             # 重复回调不再次累加
            point = self.moves[-1][0]
            self.assertAlmostEqual(point.x(), 1690.125 + dx, places=11)
            self.assertAlmostEqual(point.y(), 700.749, places=11)
            event = self.event(QEvent.MouseMove, point, int(sample.timestamp * 1000))
            self.assertTrue(self.drag.move(event))
        self.assertEqual(len(self.moves), 3)
        self.assertTrue(self.drag.move(self.event(QEvent.MouseMove, self.moves[0][0], 12040)),
                        "稍后到达的同一 Qt 事件仍需去重")
        self.assertFalse(self.drag.move(self.event(QEvent.MouseMove, QPointF(1691, 700), 12100)))

    def test_unrelated_window_old_events_and_other_native_types_are_ignored(self):
        self.begin()
        for sample in (pointer._Sample(6, 88, 12.1, 2, 1691, 739),
                       pointer._Sample(6, 77, 11.9, 2, 1691, 739),
                       pointer._Sample(1, 77, 12.1, 2, 1691, 739), None):
            self.deliver(sample)
        self.deliver(pointer._Sample(6, 77, 12.1, 2, 1691, 739), b"windows_generic_MSG")
        self.assertEqual(self.moves, [])

    def test_end_hide_disable_and_new_gesture_clear_native_delivery(self):
        for reason in ("end", "hide", "disable"):
            with self.subTest(reason=reason):
                self.owner.show()
                self.owner.setEnabled(True)
                self.begin()
                if reason == "end":
                    self.drag.end()
                elif reason == "hide":
                    self.owner.hide()
                else:
                    self.owner.setEnabled(False)
                self.deliver(pointer._Sample(6, 77, 12.1, 2, 1691, 739))
                self.assertFalse(self.drag._active)
        self.assertEqual(self.moves, [])
        self.owner.show()
        self.owner.setEnabled(True)
        self.begin()
        sample = pointer._Sample(6, 77, 12.1, 2, 1691, 739)
        self.deliver(sample)
        qt_event = self.event(QEvent.MouseMove, self.moves[-1][0], 12100)
        self.assertTrue(self.drag.move(qt_event))
        self.drag.end()
        self.begin()
        self.assertFalse(self.drag.move(qt_event))

    def test_native_read_failure_falls_back_and_owner_destruction_stops_filter(self):
        self.begin()
        with mock.patch.object(pointer, "_sample", side_effect=ValueError("missing native event")):
            self.assertEqual(self.drag.nativeEventFilter(b"mac_generic_NSEvent", 99), (False, 0))
        self.assertFalse(self.drag.move(self.press))
        self.begin()
        self.owner.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(self.drag._active)
        # Recreate only for tearDown; the helper keeps no strong reference to the old QWidget.
        self.owner = QWidget()


if __name__ == "__main__":
    unittest.main()
