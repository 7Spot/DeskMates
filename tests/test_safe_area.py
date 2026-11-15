"""自己建的窗口都不留安全区（native.ignore_safe_area）：带刘海的屏上，窗口顶边进了最上面那一条，Qt 会把窗口里的东西往下挤，
画出来的和按窗口坐标算的点击范围就差出一截（「···」看着在这，点得到的地方在上面）。新建窗口忘了调就在这里报出来。"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SafeAreaTest(unittest.TestCase):
    def test_every_frameless_window_ignores_the_safe_area(self):
        """widget/ 里构造时带 FramelessWindowHint 的类（自己建的窗口），构造函数里都调了 native.ignore_safe_area。"""
        missing = []
        for path in sorted((ROOT / "widget").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
                init = next((f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"), None)
                if init is None:
                    continue
                names = {n.attr for n in ast.walk(init) if isinstance(n, ast.Attribute)}
                if "FramelessWindowHint" in names and "ignore_safe_area" not in names:
                    missing.append(f"{path.name}:{cls.name}")
        self.assertEqual(missing, [], "这些窗口没调 native.ignore_safe_area(self)")

    def test_ignore_safe_area_survives_showing_the_window(self):
        """Qt 在窗口建出来、显示时才把「按安全区排」打开（真机读回过：刚建好是关的、显示以后是开的），没自己设过才开：
        构造时设成关，显示以后还是关。"""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QWidget
        from widget import native
        QApplication.instance() or QApplication([])
        w = QWidget(None, Qt.FramelessWindowHint | Qt.Tool)
        native.ignore_safe_area(w)
        w.show()
        self.assertFalse(w.testAttribute(Qt.WA_ContentsMarginsRespectsSafeArea))
        w.close()


if __name__ == "__main__":
    unittest.main()
