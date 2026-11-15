"""毛色自定义：大津阈值、斑纹遮罩、换色落在对的区域、保护区不动、眼睛只改眼睛、参数 JSON 往返。"""
import os
import unittest
from pathlib import Path

import config

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication        # 要 QApplication 不要 QGuiApplication：同一进程里后面的面板测试要建 QWidget
    return QApplication.instance() or QApplication([])


def _half_image(size: int, left: int, right: int):
    from PySide6.QtGui import QColor, QImage
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    for x in range(size):
        v = left if x < size // 2 else right
        for y in range(size):
            img.setPixelColor(x, y, QColor(v, v, v))
    return img


class CoatMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_otsu_splits_a_bimodal_image(self):
        from widget.coat import otsu_threshold
        t = otsu_threshold(_half_image(64, 40, 200))
        self.assertTrue(40 <= t < 200, t)

    def test_pattern_mask_marks_the_dark_side(self):
        from widget.coat import pattern_mask
        mask = pattern_mask(_half_image(64, 40, 200), 64)
        self.assertEqual(mask.pixelColor(8, 32).red(), 255, "深色侧 = 255")
        self.assertEqual(mask.pixelColor(56, 32).red(), 0, "浅色侧 = 0")

    def test_spec_round_trip_and_bad_input(self):
        from widget.coat import CoatSpec
        spec = CoatSpec(3, "#112233", "#AABBCC", True, "#3B7BD6")
        self.assertEqual(CoatSpec.from_json(spec.to_json()), spec)
        self.assertEqual(CoatSpec.from_json(""), CoatSpec())
        self.assertEqual(CoatSpec.from_json("not json"), CoatSpec())
        self.assertEqual(CoatSpec.from_json('{"pattern": 9}').pattern, 1, "超范围的斑纹编号回 1")


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class CoatPaintTests(unittest.TestCase):
    SIZE = 128

    @classmethod
    def setUpClass(cls):
        from PySide6.QtGui import QImage

        from widget import gltf
        from widget.coat import CoatPainter
        cls.app = _app()
        cls.model = gltf.load(config.MODEL_PATH)
        cls.painter = CoatPainter(cls.model, {1: QImage.fromData(cls.model.texture_png)})

    def _region_mean(self, img, dark: bool):
        """斑纹遮罩里深色（或浅色）且不在保护区的像素的平均 RGB。"""
        mask, protected = self.painter._mask(1, self.SIZE), self.painter.protected_mask(self.SIZE)
        r = g = b = n = 0
        for y in range(self.SIZE):
            for x in range(self.SIZE):
                if protected.pixelColor(x, y).red():
                    continue
                m = mask.pixelColor(x, y).red()
                if (dark and m > 200) or (not dark and m < 50):
                    c = img.pixelColor(x, y)
                    r, g, b, n = r + c.red(), g + c.green(), b + c.blue(), n + 1
        self.assertGreater(n, 100)
        return r / n, g / n, b / n

    def test_main_goes_on_dark_fur_and_secondary_on_light(self):
        from widget.coat import CoatSpec
        img = self.painter.paint(CoatSpec(1, "#FF0000", "#0000FF"), self.SIZE)
        r, g, b = self._region_mean(img, dark=True)
        self.assertTrue(r > 2 * g and r > 2 * b, (r, g, b))
        r, g, b = self._region_mean(img, dark=False)
        self.assertTrue(b > 2 * r and b > 2 * g, (r, g, b))

    def test_swap_trades_the_regions(self):
        from widget.coat import CoatSpec
        img = self.painter.paint(CoatSpec(1, "#FF0000", "#0000FF", swap=True), self.SIZE)
        r, g, b = self._region_mean(img, dark=True)
        self.assertTrue(b > 2 * r, (r, g, b))

    def test_protected_regions_keep_the_original_texture(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage

        from widget.coat import CoatSpec
        size = 256
        base = self.painter.albedo(1).scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        img = self.painter.paint(CoatSpec(1, "#00FF00", "#FF00FF"), size)
        protected = self.painter.protected_mask(size)
        covered = checked = 0
        for y in range(size):
            for x in range(size):
                if protected.pixelColor(x, y).red() == 255:
                    covered += 1
                    a, b = base.pixelColor(x, y), img.pixelColor(x, y)
                    if max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())) <= 1:
                        checked += 1
        share = covered / (size * size)
        self.assertTrue(0.005 < share < 0.12, f"保护区占贴图 {share:.1%}")
        self.assertEqual(checked, covered, "保护区里每个像素都是原图")

    def test_eye_color_changes_only_the_eyes(self):
        from widget.coat import CoatSpec
        size = 256
        plain = self.painter.paint(CoatSpec(1, "#2A2A2E", "#F2F0EC"), size)
        tinted = self.painter.paint(CoatSpec(1, "#2A2A2E", "#F2F0EC", eyes="#3B7BD6"), size)
        eyes = self.painter.eye_mask(size)
        changed = outside = 0
        for y in range(size):
            for x in range(size):
                if plain.pixelColor(x, y) != tinted.pixelColor(x, y):
                    changed += 1
                    if eyes.pixelColor(x, y).red() == 0:
                        outside += 1
        self.assertGreater(changed, 20, "眼睛确实换了色")
        self.assertEqual(outside, 0, "眼睛以外一个像素都没变")

    def test_recolor_is_fast_enough_for_live_preview(self):
        import time

        from widget.coat import CoatSpec
        self.painter.paint(CoatSpec(1, "#7A4A28", "#F4EFE6"), 1024)          # 第一次建遮罩
        t0 = time.perf_counter()
        self.painter.paint(CoatSpec(1, "#1E1E22", "#2A2A2E"), 1024)
        self.assertLess(time.perf_counter() - t0, 0.25, "1024 预览贴图要在 250 毫秒内")


if __name__ == "__main__":
    unittest.main()


class TintPaintTests(unittest.TestCase):
    """通体一色的模型（萨摩耶，包里 coat_custom.mode = "tint"）：整身染主色，「背上一片」染副色，对调，
    耳朵里的粉（红比绿多）、眼鼻舌爪垫留原图。用边牧的模型（骨头齐）、自己画的贴图：灰毛 + 一块粉 + 第 3 套里一块偏黄。"""
    SIZE = 128

    @classmethod
    def setUpClass(cls):
        from PySide6.QtGui import QColor, QImage

        from widget import gltf
        from widget.coat import FUR_GRAY, TintPainter
        cls.app = _app()
        cls.model = gltf.load(config.MODEL_PATH)
        s = cls.SIZE
        fur = QImage(s, s, QImage.Format.Format_ARGB32)
        fur.fill(QColor(FUR_GRAY, FUR_GRAY, FUR_GRAY))
        for y in range(0, 16):                                   # 左上角一块粉（耳朵里那种）
            for x in range(0, 16):
                fur.setPixelColor(x, y, QColor(235, 170, 180))
        third = QImage(s, s, QImage.Format.Format_ARGB32)        # 第 3 套：右半边偏黄 = 背上那一片
        third.fill(QColor(FUR_GRAY, FUR_GRAY, FUR_GRAY))
        for y in range(s):
            for x in range(s // 2, s):
                third.setPixelColor(x, y, QColor(225, 200, 140))
        cls.painter = TintPainter(cls.model, {1: fur, 3: third}, brightness=1.0, patch_from=3)

    def _mean(self, img, pick):
        protected, pink = self.painter.protected_mask(self.SIZE), self.painter._mask("pink", self.SIZE)
        r = g = b = n = 0
        for y in range(self.SIZE):
            for x in range(self.SIZE):
                if protected.pixelColor(x, y).red() or pink.pixelColor(x, y).red() or not pick(x, y):
                    continue
                c = img.pixelColor(x, y)
                r, g, b, n = r + c.red(), g + c.green(), b + c.blue(), n + 1
        self.assertGreater(n, 50)
        return r / n, g / n, b / n

    def test_the_whole_coat_takes_the_main_color(self):
        from widget.coat import CoatSpec
        img = self.painter.paint(CoatSpec(1, "#E6CBA2", "#4C6E9A"), self.SIZE)
        r, g, b = self._mean(img, lambda x, y: True)
        self.assertLess(max(abs(r - 0xE6), abs(g - 0xCB), abs(b - 0xA2)), 6, f"毛平常的亮度乘出来正好是选的颜色：{(r, g, b)}")
        r, g, b = self._mean(img, lambda x, y: x >= self.SIZE // 2 + 8)
        self.assertGreater(r, 2 * b - 200, "纯色：背上那一片也是主色")
        self.assertLess(abs(b - 0xA2), 8)

    def test_the_saddle_takes_the_secondary_and_swap_trades_them(self):
        from widget.coat import CoatSpec
        half = self.SIZE // 2
        img = self.painter.paint(CoatSpec(2, "#FFFFFF", "#3060C0"), self.SIZE)
        r, g, b = self._mean(img, lambda x, y: x >= half + 8)
        self.assertTrue(b > r + 60, f"背上一片：副色 {(r, g, b)}")
        r, g, b = self._mean(img, lambda x, y: x < half - 8)
        self.assertTrue(min(r, g, b) > 230, f"别处：主色 {(r, g, b)}")
        swapped = self.painter.paint(CoatSpec(2, "#FFFFFF", "#3060C0", swap=True), self.SIZE)
        r, g, b = self._mean(swapped, lambda x, y: x < half - 8)
        self.assertTrue(b > r + 60, f"对调：身子是副色 {(r, g, b)}")

    def test_pink_and_protected_parts_keep_the_original(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage

        from widget.coat import CoatSpec
        size = self.SIZE
        base = self.painter.albedo(1).scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        img = self.painter.paint(CoatSpec(1, "#00FF00", "#FF00FF"), size)
        a, b = base.pixelColor(6, 6), img.pixelColor(6, 6)
        self.assertLessEqual(max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue())), 2, "耳朵里那种粉：原图")
        protected = self.painter.protected_mask(size)
        bad = sum(1 for y in range(size) for x in range(size) if protected.pixelColor(x, y).red() == 255
                  and max(abs(base.pixelColor(x, y).red() - img.pixelColor(x, y).red()), abs(base.pixelColor(x, y).green() - img.pixelColor(x, y).green())) > 1)
        self.assertEqual(bad, 0, "眼鼻舌爪垫：原图")
