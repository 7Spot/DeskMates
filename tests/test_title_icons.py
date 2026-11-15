"""顶部栏的两个图标（app 图标和物种图标分开）、进高级设置时 app 图标流进胶囊、改名一直居中、强调色淡过去、卡片点了不切前台。
只用卡片本身（card.Card），不建狗的窗口；offscreen 平台，不出声。"""
import math
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from widget import marks, native, sticker


SAYS = ("新版本已下载完成", "新版本已下载", "新版本")    # 新版本胶囊的几种说法（i18n.says 中文那套）


def shot(w: QWidget, dpr: float = 2.0, bg: str = "#DCD8D0") -> QImage:
    img = QImage(round(w.width() * dpr), round(w.height() * dpr), QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(QColor(bg))
    w.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return img


class MarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_the_app_icon_has_one_source_used_by_the_menu_bar_and_the_icon_file(self):
        """换 app 图标只改 widget/marks.py（形状在 dm_shapes，只有 marks 用它）：菜单栏图标、App 图标文件、左上角的圆都从它取；物种图标（狗 = 骨头）是另一个出处。"""
        from widget import tray
        import inspect
        from PySide6.QtCore import QSize
        img = tray.menu_icon().pixmap(QSize(22, 22), 2.0).toImage()
        self.assertEqual((img.width(), img.height()), (44, 44))
        ref = QImage(44, 44, QImage.Format_ARGB32_Premultiplied)
        ref.fill(0)
        p = QPainter(ref)
        p.scale(2.0, 2.0)
        marks.draw_app(p, QPointF(11.0, 11.0), QColor(Qt.black), 18.0)
        p.end()
        same = all(img.pixelColor(x, y).alpha() == ref.pixelColor(x, y).alpha() for x in range(0, 44, 3) for y in range(0, 44, 3))
        self.assertTrue(same, "菜单栏图标就是 marks 画的 app 图标")
        icon_src = (Path(__file__).resolve().parents[1] / "tools" / "make_icon.py").read_text(encoding="utf-8")
        self.assertIn("marks.app_icon", icon_src, "App 图标文件也从 marks 取")
        self.assertNotIn("drawPath", icon_src, "make_icon.py 里不自己画")
        root = Path(__file__).resolve().parents[1]
        users = sorted(p.name for p in list((root / "widget").glob("*.py")) + list((root / "tools").glob("*.py"))
                       if p.name != "dm_shapes.py" and "dm_shapes" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["about_art.py", "marks.py"], "形状文件只有 marks 和关于页的图用")
        art_src = (root / "widget" / "about_art.py").read_text(encoding="utf-8")
        for name in ("dog_cat", "dog_body", "cat_m", "pieces()", "small()", "scene()"):
            self.assertNotIn(f"S.{name}", art_src, "关于页的图不直接拿猫狗：猫狗只认 marks（app_pieces），它只借画圆角、描边这些小工具和海鸥、鱼")
        card_src = inspect.getsource(__import__("widget.card", fromlist=["_Lead"])._Lead)
        self.assertIn("marks.draw_app", card_src, "左上角的圆画的是 app 图标")
        self.assertIsNotNone(marks.species_path("bone", QPointF(0, 0)), "狗的物种图标是骨头")
        self.assertIsNone(marks.species_path("", QPointF(0, 0)))

    def test_the_icon_file_is_the_whole_scene_from_128_up_and_only_the_cat_and_dog_below(self):
        """App 图标文件：米白圆角方底、黑边（26 粗、一半在方底外面）、没有影子；
        128 以上整张（天上的海鸥、脚下的水线、水下的鱼），64 以下只有猫狗。"""
        big = marks.app_icon(1024)
        self.assertEqual((big.width(), big.height()), (1024, 1024))
        self.assertEqual(big.pixelColor(20, 20).alpha(), 0, "方底外面透明")
        self.assertEqual(big.pixelColor(512, 960).alpha(), 0, "方底下面没有影子")
        for y in (89, 100, 111):
            self.assertEqual(big.pixelColor(512, y).name(), "#1c1c21", f"黑边（{y}）：从方底外面 13 到里面 13")
        self.assertEqual(big.pixelColor(512, 84).alpha(), 0, "黑边外面透明")
        self.assertEqual(big.pixelColor(512, 116).name(), "#f2f0ec", "黑边里面就是米白底")
        self.assertEqual(big.pixelColor(512, 150).name(), "#f2f0ec", "米白底")
        for name, (x, y) in (("海鸥", (716, 244)), ("水线", (512, 706)), ("鱼", (372, 806))):
            self.assertEqual(big.pixelColor(x, y).name(), "#1c1c21", name)

        def darkest(img, x, y):
            return min(img.pixelColor(i, j).lightness() for i in range(x - 1, x + 2) for j in range(y - 1, y + 2))
        at = lambda px, x, y: (round(x * px / 1024), round(y * px / 1024))
        self.assertLess(darkest(marks.app_icon(128), *at(128, 716, 244)), 100, "128：整张，有海鸥")
        small = marks.app_icon(64)
        self.assertGreater(darkest(small, *at(64, 716, 244)), 200, "64：只有猫狗，没有海鸥")
        self.assertGreater(darkest(small, *at(64, 372, 806)), 200, "也没有鱼")

    def test_packs_say_which_species_icon_they_have(self):
        import json
        import tempfile
        from widget import packs
        dog = packs.read_pack(packs.PACKS_DIR / "border_collie")
        self.assertEqual((dog.species, dog.icon), ("dog", "bone"))
        with tempfile.TemporaryDirectory() as tmp:
            for name, data in (("cat", {"id": "cat", "species": "cat"}), ("fox", {"id": "fox", "species": "fox", "icon": "paw.png"}),
                               ("pup", {"id": "pup"})):
                folder = Path(tmp) / name
                folder.mkdir()
                (folder / "pack.json").write_text(json.dumps(data), encoding="utf-8")
            img = QImage(8, 8, QImage.Format_ARGB32)
            img.fill(QColor("black"))
            img.save(str(Path(tmp) / "fox" / "paw.png"))
            found = packs.discover(Path(tmp))
            self.assertEqual(found["pup"].icon, "bone", "不写物种的是狗：骨头")
            self.assertEqual(found["cat"].icon, "", "不认识的物种、没写图标：没有（胶囊里换成 app 图标）")
            self.assertTrue(found["fox"].icon.endswith("paw.png") and Path(found["fox"].icon).is_file(), "包里的一张图")
            canvas = QImage(40, 40, QImage.Format_ARGB32_Premultiplied)
            canvas.fill(0)
            p = QPainter(canvas)
            self.assertTrue(marks.draw_species(p, found["fox"].icon, QPointF(20, 20), QColor("#F2F0EC")), "图按形状涂成胶囊上的颜色")
            self.assertFalse(marks.draw_species(p, "", QPointF(20, 20), QColor("white")))
            p.end()
            self.assertEqual(canvas.pixelColor(20, 20).name(), "#f2f0ec")


class TitleBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from widget.card import Card
        self.motion = mock.patch.object(native, "reduce_motion", return_value=False)
        self.motion.start()
        self.addCleanup(self.motion.stop)
        self.card = Card("Milo")
        self.card.setFixedWidth(312 + 2 * 22)
        self.card.setAttribute(Qt.WA_DontShowOnScreen)
        bar = self.bar = self.card._tag
        bar.set_centered(True, animated=False)
        bar.set_look("mark", "bone", animated=False)
        self.card.show()
        self.app.processEvents()
        self.card.finish_animations()
        bar.finish_now()
        self.addCleanup(self.card.hide)

    def frames(self, n: int) -> list:
        """推 n 帧（每帧 1/60 秒），每帧记：那一滴走到哪、在不在流、胶囊画多宽、那一滴横着拉长多少（没在流就是 None）。"""
        out = []
        for _ in range(n):
            self.card.frame_step(self.card.clock._last + 1 / 60, 1 / 60)
            f = self.bar._flow
            out.append((self.bar.flow, self.bar._flow_on, 2.0 * f.cap(self.bar)[1] if f else None, f.sx.value if f else None))
        return out

    def test_the_capsule_icon_is_the_species_for_names_and_the_app_icon_otherwise(self):
        bar = self.bar
        self.assertEqual((bar._icon, bar._drawn_icon), ("bone", "bone"))
        self.assertEqual(bar.text_x(True), bar.text_x(False), "描边的「添加同桌」也有图标：字离左边一样远")
        bar.set_icon(marks.APP)
        self.assertEqual((bar._icon, bar._drawn_icon), (marks.APP, "bone"), "先淡出旧的")
        self.assertFalse(bar._flow_on, "圆里还是 app 图标（主页面停在「+」上）：不流，胶囊里自己换")
        alphas = [bar._icon_alpha]
        for _ in range(20):
            bar.tick(1 / 60)
            alphas.append(bar._icon_alpha)
        self.assertEqual((bar._drawn_icon, bar._icon_alpha), (marks.APP, 1.0))
        self.assertEqual(min(alphas), 0.0, "淡没了才换")

    def test_entering_advanced_the_app_icon_flows_into_the_capsule_and_back(self):
        """进高级设置，左上角的 app 图标液态地流进胶囊，圆里 ‹ 糊进来；回来反过来。要灵动岛那种回弹：
        墨滴被拉出去时拉长、断开后弹回圆；连上胶囊时胶囊先吞一下（比原来还窄）再舒展到新宽度。"""
        bar, card = self.bar, self.card
        still = shot(card)
        old_w = bar.tag.value
        bar.set_look("back", marks.APP)
        bar.setText("Advanced")
        self.assertTrue(bar._flow_on)
        self.assertTrue(bar._flow_layer.isVisible(), "整块画在最上面一层")
        self.assertTrue(bar.lead.flow_hidden, "流的时候圆自己不画：会鼓、会吞，画在上面一层")
        seen = self.frames(90)
        values = [v for v, on, _, _ in seen if on]
        widths = [w for _, on, w, _ in seen if on]
        stretch = [sx for _, on, _, sx in seen if on]
        self.assertTrue(any(0.3 < v < 0.7 for v in values), "是一段动画，不是一下跳过去")
        self.assertLess(min(widths), old_w * 0.9, "连上那一下胶囊先吞（比原来还窄）")
        self.assertGreater(max(stretch), 1.1, "被拉出去的时候拉长")
        top = stretch.index(max(stretch))
        self.assertLess(min(stretch[top:]), 1.0, "断开后弹回来：稍微过头一点（回弹）")
        self.assertEqual(seen[-1][1], False, "走完了：那一层收起来，胶囊、圆自己画")
        self.assertFalse(bar._flow_layer.isVisible())
        self.assertFalse(bar.lead.flow_hidden)
        self.assertEqual(bar.lead.mix, 1.0, "圆里是返回")
        self.assertEqual(bar._drawn_icon, marks.APP)
        self.assertAlmostEqual(bar.tag.value, bar.tag.target, places=3)
        bar.set_look("mark", "bone")
        bar.setText("Milo")
        self.assertTrue(bar._flow_on, "回来：流回圆里")
        seen = self.frames(90)
        self.assertEqual(seen[-1][1], False)
        self.assertFalse(bar.lead.flow_hidden)
        self.assertEqual(bar.lead.mix, 0.0)
        card.finish_animations()
        bar.finish_now()
        back = shot(card)
        diff = sum(1 for x in range(0, back.width(), 2) for y in range(0, round(84 * 2), 2) if back.pixelColor(x, y) != still.pixelColor(x, y))
        self.assertEqual(diff, 0, "流回来停下以后和原来一个像素都不差")

    def go_back(self, name: str = "Milo") -> None:
        """进高级设置、停稳，再点返回（回主页面，名字胶囊写 name）。"""
        self.bar.set_look("back", marks.APP)
        self.bar.setText("Advanced")
        self.frames(90)
        self.bar.set_look("mark", "bone")
        self.bar.setText(name)

    def test_going_back_the_back_key_vanishes_and_the_icon_overshoots_its_spot(self):
        """点返回，返回键连圆整个没了（不等图标）；app 图标从名字里出来、自己走回去当那个圆，像有惯性——位置冲过头一点再回来，
        大小不吞；冲过头画到圆左边外面也不被切；流完换回真的圆，位置不跳。"""
        from widget.card import FLOW_OVERSHOOT, FLOW_PAD
        bar, card = self.bar, self.card
        self.go_back()
        f = bar._flow
        c0 = f.circle(bar)[0].x()
        self.assertTrue(bar._flow_on)
        layer = bar._flow_layer.geometry()
        self.assertEqual(layer.left(), bar.mapTo(card, QPoint(0, 0)).x() - FLOW_PAD, "流动那一层往左多出一截")
        sizes, xs, radii, cs, last, after = [], [], [], [], None, None
        for _ in range(90):
            self.frames(1)
            f = bar._flow
            if f is None:
                after = shot(card)
                break
            last = shot(card)
            sizes.append(f.circle_size)
            xs.append(f.head(bar, f.cap(bar)).x() - c0)
            radii.append(f.drop_r * f.sx.value)
            cs.append(f.cs.value)
        self.assertEqual(sizes[8], 0.0, "点返回后 0.14 秒内返回键连圆整个没了")
        low = min(xs)
        self.assertLess(abs(-low - FLOW_OVERSHOOT), 1.5, f"到位前往左冲过头约 {FLOW_OVERSHOOT} 像素再回来：{-low:.2f}")
        self.assertAlmostEqual(xs[-1], 0.0, delta=0.05, msg="停稳在圆心")
        self.assertGreater(min(x - r for x, r in zip(xs, radii)) + c0, -FLOW_PAD, "冲过头那一下整个在流动那一层里：不被切")
        self.assertEqual(min(cs), 1.0, "到位时大小不吞")
        self.assertIsNotNone(after, "1.5 秒内流完")
        self.assertLess(len(sizes), 66, "1.1 秒内流完")
        circle = bar.mapTo(card, QPoint(0, bar.ROOM))
        moved = sum(1 for x in range(circle.x() * 2, (circle.x() + bar.H) * 2) for y in range(circle.y() * 2, (circle.y() + bar.H) * 2)
                    if abs(last.pixelColor(x, y).lightness() - after.pixelColor(x, y).lightness()) > 40)
        self.assertLess(moved, 6, "流完那一刻换回真的圆：位置、样子不跳")

    def test_with_the_update_chip_names_come_back_within_a_second_with_even_gaps(self):
        """有新版本胶囊时进出高级设置（短、中、长名字）：
         1.1 秒内流完，回来以后左边的圆、名字、胶囊、× 三段空一样宽。"""
        bar = self.bar
        bar.set_chip(SAYS, animated=False)
        for name in ("Mo", "Bartholomew", "Maximilian Augustus"):
            bar.setText(name, animated=False)
            bar.finish_now()
            self.go_back(name)
            seen = self.frames(66)
            self.assertFalse(seen[-1][1], f"{name}：1.1 秒内流完")
            self.assertAlmostEqual(bar.tag.value, bar.tag.target, places=1)
            t, c = bar.tag_rect(), bar.chip_rect()
            gaps = (t.left() - bar._edge(), c.left() - t.right(), bar._end() - c.right())
            self.assertLessEqual(max(gaps) - min(gaps), 1.0, f"{name}：三段空一样宽 {gaps}")
        self.assertGreater(bar.tag.target, 120, "长名字：名字胶囊长到了它该有的宽")

    def test_the_flow_frames_are_one_continuous_drop(self):
        """分出去的那一个从圆里分裂出去，走完一点都不留。一路都是白底黑框，
        进了胶囊黑框也是一笔（胶囊里面没有那一个自己的那圈线）。"""
        bar, card = self.bar, self.card
        bar.set_look("back", marks.APP)
        seen = {}
        for _ in range(90):
            self.frames(1)
            f = bar._flow
            if f is None:
                break
            cap = f.cap(bar)
            m = f.progress(bar, cap)
            key = next((k for k, on in (("parted", f.parted is not None), ("near", m > 0.78), ("in", m > 0.95)) if on and k not in seen), None)
            if key is None:
                continue
            img = shot(card)
            head = f.head(bar, cap)
            off = bar.mapTo(card, QPoint(0, 0))
            seen[key] = img.pixelColor(round((off.x() + head.x()) * 2), round((off.y() + head.y() + 0.65 * f.drop_r) * 2)).lightness()   # 图标下面一点：那一个自己的底色
            if key == "in":                                           # 那一个自己那圈线（描边中线）该在的地方，偏右下 17°：图标外、胶囊里
                r, a, sx = f.drop_r - sticker.OUTLINE / 2.0, math.radians(17), f.sx.value
                x, y = off.x() + head.x() + r * sx * math.cos(a), off.y() + head.y() + r / math.sqrt(sx) * math.sin(a)
                seen["seam"] = min(img.pixelColor(round(x * 2) + dx, round(y * 2) + dy).lightness() for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        self.assertGreater(seen["parted"], 170, "刚分出去：白底")
        self.assertGreater(seen["near"], 170, "快到胶囊：还是白底，不变黑")
        self.assertGreater(seen["seam"], 150, "进了胶囊：那一个自己那圈线不画在胶囊里面")
        self.frames(90)
        self.assertFalse(bar._flow_on)

    def test_reversing_halfway_flows_back_without_a_jump(self):
        """走到一半又点了返回：新的一趟从现在的样子接着走（位置、速度都接上），不跳，最后回到圆里。"""
        bar = self.bar
        bar.set_look("back", marks.APP)
        self.frames(14)
        mid = bar.flow
        self.assertTrue(0.1 < mid < 0.9, mid)
        bar.set_look("mark", "bone")
        self.assertTrue(bar._flow_on)
        self.assertAlmostEqual(bar.flow, mid, msg="从现在的位置接着走，不先跳回去")
        seen = self.frames(120)
        values = [mid] + [v for v, on, _, _ in seen if on]
        self.assertTrue(all(abs(b - a) < 0.2 for a, b in zip(values, values[1:])), "每一帧挪得不多：没有跳")
        self.assertEqual(seen[-1][1], False)
        self.assertEqual(bar.lead.mix, 0.0, "回到圆里：圆里是 app 图标")

    def test_other_page_changes_do_not_flow(self):
        bar = self.bar
        bar.set_look("back", "bone")                     # 主页面 → 详情页：圆里 app 图标换成返回，胶囊里还是骨头
        self.assertFalse(bar._flow_on)
        bar.finish_now()
        bar.set_look("back", marks.APP)                  # 详情页 → 自定义毛色页：胶囊里骨头换成 app 图标，圆里一直是返回
        self.assertFalse(bar._flow_on, "app 图标不是从圆里来的：胶囊里淡出淡入")
        bar.finish_now()
        with mock.patch.object(native, "reduce_motion", return_value=True):
            bar.set_look("mark", "bone")
            bar.set_look("back", marks.APP)
            self.assertFalse(bar._flow_on, "减少动态效果：直接到位")

    def test_renaming_keeps_the_capsule_centred_and_elides_the_left_when_full(self):
        """改名时胶囊一直居中、两边一起长；长到最宽不再长，左边是省略号、最后打的字一直看得见。"""
        bar, card = self.bar, self.card
        card.set_renamable(lambda _t: None, "Click to rename")
        card.start_rename()
        self.assertTrue(card.renaming)
        edit = bar.edit
        edit.setText("拿铁拿铁")
        for _ in range(40):
            bar.tick(1 / 60)
        centre = bar.left.value + bar.tag.value / 2
        self.assertAlmostEqual(centre, bar._span() / 2, delta=0.6)
        self.assertAlmostEqual(edit.x(), round(bar.left.value + bar.text_x() - 2.0), delta=1, msg="输入框跟着胶囊走")
        edit.setText("拿铁" * 14)
        edit.setCursorPosition(len(edit.text()))
        for _ in range(40):
            bar.tick(1 / 60)
        self.assertTrue(bar.edit_capped())
        self.assertAlmostEqual(bar.tag.value, bar._cap(), delta=0.5, msg="长到最宽就不长了")
        self.assertAlmostEqual(bar.left.value + bar.tag.value / 2, bar._span() / 2, delta=0.6)
        img = shot(edit, bg="#3060C0")                                # QLineEdit 画的时候才按光标滚；垫一块和胶囊分得开的蓝
        left, right = edit.clipped_ends()
        self.assertEqual((left, right), (True, False), "前面的滚出去了、最后打的看得见")
        paper, ink = QColor(sticker.PAPER_2), QColor(sticker.INK)
        cover = img.pixelColor(2 * 4, 2 * 4)
        self.assertLess(abs(cover.red() - paper.red()) + abs(cover.blue() - paper.blue()), 30, "左头盖了一块胶囊的底色（米白）")
        dots = [(x, y) for x in range(2 * 2, 2 * 14) for y in range(2 * 12, 2 * 22)
                if abs(img.pixelColor(x, y).red() - ink.red()) < 30 and abs(img.pixelColor(x, y).blue() - ink.blue()) < 30]
        self.assertTrue(dots, "上面画着黑的省略号")
        card._end_rename()


class AccentFadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_switching_pets_fades_the_accent_without_restyling_every_frame(self):
        """换同桌时按钮、开关的颜色和狗一样淡过去。样式表一次都不重套（里面不放强调色，
        重套一次整张卡片重排 20～35 毫秒）：输入框选中文字的底色淡到头时设在卡片的调色板上。"""
        from PySide6.QtGui import QPalette
        from widget.card import ACCENT_S, Card
        from widget.widgets import Switch
        with mock.patch.object(native, "reduce_motion", return_value=False):
            card = Card("Milo", accent="#3366cc")
            card.setAttribute(Qt.WA_DontShowOnScreen)
            sw = Switch(accent="#3366cc")
            card.body.addWidget(sw)
            card.show()
            self.app.processEvents()
            card.finish_animations()
            styled = []
            real = card.setStyleSheet
            card.setStyleSheet = lambda css: (styled.append(css), real(css))
            card.set_accent("#cc6633")
            self.assertEqual(styled, [], "样式表不重套（里面没有强调色）")
            reds = [sw.accent.red()]
            for _ in range(round(ACCENT_S * 60) + 3):
                card.frame_step(card.clock._last + 1 / 60, 1 / 60)
                reds.append(sw.accent.red())
            self.assertEqual(styled, [], "淡的路上也不套")
            self.assertEqual(card.palette().color(QPalette.Highlight).name(), "#cc6633", "淡到头：输入框选中文字的底色是新的强调色")
            self.assertEqual(sw.accent.name(), "#cc6633")
            self.assertEqual(card.theme.accent, "#cc6633")
            self.assertTrue(all(b >= a for a, b in zip(reds, reds[1:])), "一路淡过去")
            self.assertGreater(len(set(reds)), 6, "是渐变，不是一下换")
            card.hide()
            card.set_accent("#3366cc")
            self.assertEqual(sw.accent.name(), "#3366cc", "没显示：一下换好")


class NoActivateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clicking_the_card_does_not_activate_and_typing_makes_it_key(self):
        """从别的 App 过来第一下点卡片卡半秒（切前台在等）：卡片和狗、球一样 set_no_activate。
        输入框拿到焦点时只让卡片接键盘（make_key，不切前台）；接不了才切前台。真机点击假不出来。"""
        from widget import card as card_mod
        from widget.card import Card
        with mock.patch.object(native, "set_no_activate") as no_activate:
            card = Card("Milo")
            card.setAttribute(Qt.WA_DontShowOnScreen)
            edit = QLineEdit()
            card.body.addWidget(edit)
            card.show()
            self.app.processEvents()
            no_activate.assert_called_with(card)
        with mock.patch.object(native, "app_active", return_value=False), \
                mock.patch.object(native, "make_key", return_value=True) as make_key, \
                mock.patch.object(native, "activate_app") as activate:
            card._focus_changed(None, edit)
            make_key.assert_called_once_with(card)
            activate.assert_not_called()
            make_key.return_value = False
            card._focus_changed(None, edit)
            activate.assert_called_once()
            with mock.patch.object(card_mod, "TYPE_ACTIVATES", True):
                make_key.return_value = True
                card._focus_changed(None, edit)
                self.assertEqual(activate.call_count, 2, "TYPE_ACTIVATES 开着：开始打字就切前台")
            card._focus_changed(None, QWidget())
            self.assertEqual(activate.call_count, 2, "别的窗口的东西不管")
            make_key.reset_mock()
            make_key.return_value = True
            from PySide6.QtCore import QEvent, QPointF
            from PySide6.QtGui import QMouseEvent
            QApplication.sendEvent(edit, QMouseEvent(QEvent.MouseButtonPress, QPointF(3, 3), QPointF(3, 3), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
            make_key.assert_called_once_with(card)                     # Qt 可能连焦点都不给（窗口没激活）：按在输入框上那一下就先让卡片接键盘
        with mock.patch.object(native, "app_active", return_value=True), mock.patch.object(native, "make_key") as make_key:
            card._focus_changed(None, edit)
            make_key.assert_not_called()
        card.hide()

    def test_the_colour_picker_activates_the_app_when_it_opens(self):
        """系统取色器（NSColorPanel）程序不在前台时自己藏起来：打开它的那一下切前台。"""
        from widget.coat_panel import ColorButton
        b = ColorButton("#808080", lambda _c: None, lambda _c: None)
        with mock.patch.object(native, "activate_app") as activate, \
                mock.patch("widget.coat_panel.QColorDialog") as dialog:
            b._pick()
            activate.assert_called_once()
            dialog.return_value.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
