"""同桌不抢别的 App 的键盘（在别的 App 里打着字，狗一动输入框就失去焦点）。
狗自己显示出来的窗口都不接焦点、显示时不激活；Qt 的 raise_() 不顺手把程序切到前台；切前台只在取色器、开始打字那两处。
offscreen 平台读不到真的 key window、前台程序，只查窗口标志和代码；真机上的读回在 tools/selftest_playground.py 的 focus 那一段。"""
import os
import re
import sys
import unittest
from pathlib import Path

from tests.panel_base import PanelCase


def _refuses_focus(w) -> bool:
    from PySide6.QtCore import Qt
    return bool(w.windowFlags() & Qt.WindowDoesNotAcceptFocus) and w.testAttribute(Qt.WA_ShowWithoutActivating)


class FocusTests(PanelCase):
    DYNAMIC = True

    def test_dog_window_never_takes_the_keyboard(self):
        self.assertTrue(_refuses_focus(self.win))

    def test_every_window_the_dog_shows_by_itself_refuses_focus(self):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QPixmap
        from widget.bubble import DogBubble
        from widget.capture_ui import _FrozenLayer, _Snapshot
        from widget.settings import UpdatePrompt
        from widget.thing_win import ThingWindow
        from widget.widgets import StickerHud, StickerTip
        pg = self.win.playground
        wins = [self.win, *self.win._ghosts.values(), pg.ball_win, *pg.ring_wins.values()]
        wins += [ThingWindow(pg.things), ThingWindow(pg.things, front=True), DogBubble(), StickerTip(), StickerHud(), UpdatePrompt(self.win)]
        pix = QPixmap(4, 4)
        layer = _FrozenLayer(_Snapshot(QRect(0, 0, 4, 4), pix))
        wins.append(layer)
        self.addCleanup(layer.close)
        for w in wins:
            if w is None:
                continue
            with self.subTest(window=type(w).__name__):
                self.assertTrue(_refuses_focus(w), type(w).__name__)

    def test_settings_card_still_takes_the_keyboard_for_typing(self):
        from PySide6.QtCore import Qt
        self.assertFalse(self.settings.windowFlags() & Qt.WindowDoesNotAcceptFocus)   # 改名、输大小要打字（Card.ensure_typing）


class RaiseTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "Qt 的 raise 只在 Mac 上顺手激活程序")
    def test_raise_does_not_activate_the_app(self):
        import widget.native  # noqa: F401  导入时关掉
        self.assertEqual(os.environ.get("QT_MAC_SET_RAISE_PROCESS"), "0")

    def test_only_the_color_panel_and_typing_switch_to_front(self):
        root = Path(__file__).resolve().parents[1]
        callers = sorted(p.name for p in (root / "widget").glob("*.py")
                         if p.name != "native.py" and re.search(r"\bactivate_app\(", p.read_text(encoding="utf-8")))
        self.assertEqual(callers, ["card.py", "coat_panel.py"])
        self.assertNotIn("activateWindow(", "".join(p.read_text(encoding="utf-8") for p in (root / "widget").glob("*.py")))


if __name__ == "__main__":
    unittest.main()
