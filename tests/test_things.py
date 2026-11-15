"""物件：摆出来、点、拖、落、站在别的窗口上、记位置、关了灵动交互藏起来、右键的胶囊、设置卡片的「物件」那一行和页；
哪些列得出来（只有有用法的：窝、屋、盆；摆设、栏、玩具的包留着不列）。狗怎么用它们在 tests/test_nest.py、test_bowl.py、test_platform.py。
真窗口（offscreen）+ 假设置（卸载器挡住，tests/room_base.py、tests/panel_base.py 的底子）+ 一张假的款表：模型是现写的最小 glb，
不要求买来的物件模型在（这张表里的窝、盆没写 rest、serves，狗不理它们）。offscreen 没有显卡，图是空的：这里看的都是摆在哪、什么状态，不看图。"""
import json
import math
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QImage

import config
from tests.panel_base import FakeSettings, PanelCase
from tests.room_base import COLLIE, DT, RoomCase
from tests.test_thing_art import glb
from widget import hand, packs, things as things_mod
from widget.things import DROP_IN_M, FIRST_GAP_M, FOLLOW_S, RESIZE_SETTLE_S, SCREEN_SHARE, SHOT_WAIT_S, Shelf, Things
from widget.world import Area, World


def box(w: float, h: float, d: float):
    """一个盒子的六个面（宽 w、高 h、前后 d，横向居中、底贴地）。"""
    x, z = w / 2, d / 2
    return [((-x, 0, z), (x, 0, z), (x, h, z), (-x, h, z)), ((x, 0, -z), (-x, 0, -z), (-x, h, -z), (x, h, -z)),
            ((-x, 0, -z), (-x, 0, z), (-x, h, z), (-x, h, -z)), ((x, 0, z), (x, 0, -z), (x, h, -z), (x, h, z)),
            ((-x, h, z), (x, h, z), (x, h, -z), (-x, h, -z)), ((-x, 0, -z), (x, 0, -z), (x, 0, z), (-x, 0, z))]


def fake_styles(folder: Path) -> list:
    """假的款表：一个狗窝（跟着狗的身高放大）、一个盆、一个斜着摆的狗屋（右半屏反过来）、一间比屏还宽的长屋、一个坏文件，
    加上不列的三种：一根骨头（玩具，还没接）、一条长椅（摆设）、一道矮栏。"""
    def style(key, role, group, size, **spec):
        path = folder / (key.replace("/", "_") + ".glb")
        path.write_bytes(glb(box(*size)) if size else b"not a glb")
        return packs.ThingStyle(key=key, pack=key.split("/")[0], names={"en": key.split("/")[1].title(), "zh": "假" + key.split("/")[1]}, model=path,
                                thumb=folder / "none.png", spec={"group": group, "role": role, "order": 10, "scale": 1.0, "yaw": 0, "shadow": True, **spec})
    return [style("bed/blue", "bed", "rest", (0.8, 0.25, 0.5), scale=1.6, fit_pet=True), style("house/gable", "house", "rest", (0.8, 1.0, 1.2), yaw=35, mirror=True),
            style("bowl/food", "bowl", "food", (0.3, 0.1, 0.3)), style("bone/yellow", "fetch", "toys", (0.2, 0.05, 0.05), shadow=False),
            style("house/long", "house", "rest", (6.0, 0.4, 0.4)), style("house/broken", "house", "rest", None),
            style("bench/bench", "decor", "park", (1.6, 0.9, 0.5)), style("barrier/low", "hurdle", "park", (1.2, 0.6, 0.1))]


class ShelfTests(unittest.TestCase):
    def test_it_remembers_what_is_out_and_where(self):
        store = FakeSettings()
        shelf = Shelf(store)
        self.assertEqual((shelf.placed(), shelf.spot("bed/blue"), shelf.on("bed/blue")), ([], None, False))
        shelf.put("bed/blue", True)
        self.assertIsNone(shelf.spot("bed/blue"), "摆了还没落定：没有位置")
        shelf.move("bed/blue", "LG", 0.31)
        shelf.put("bowl/food", True)
        shelf.move("bowl/food", "LG", 1.7)
        self.assertEqual(shelf.placed(), ["bed/blue", "bowl/food"])
        self.assertEqual(shelf.spot("bed/blue"), ("LG", 0.31))
        self.assertEqual(shelf.spot("bowl/food"), ("LG", 1.0), "占屏宽的几成，夹在 0～1")
        shelf.put("bed/blue", False)
        again = Shelf(store)
        self.assertEqual(again.placed(), ["bowl/food"])
        self.assertEqual(again.spot("bed/blue"), ("LG", 0.31), "收起来的款位置留着")
        self.assertFalse(again.on("bed/blue"))
        self.assertEqual(json.loads(store.values["things"])[0], {"key": "bed/blue", "on": False, "screen": "LG", "fx": 0.31})

    def test_unreadable_settings_count_as_empty(self):
        for raw in ("{ not json", "42", '{"key": "x"}', '[{"on": true}]', '[["bed"]]', None):
            store = FakeSettings()
            store.values["things"] = raw
            shelf = Shelf(store)
            self.assertEqual(shelf.placed(), [], raw)
            shelf.put("bed/blue", True)                          # 读不出来的那份被新的盖掉
            self.assertEqual(Shelf(store).placed(), ["bed/blue"])
        store = FakeSettings()
        store.values["things"] = json.dumps([{"key": "a", "on": True}, {"key": "a", "on": False}, {"key": "b", "on": 1, "screen": 3, "fx": "0.5"}])
        shelf = Shelf(store)
        self.assertEqual(shelf.placed(), ["a", "b"], "同一款记了两回只认第一回")
        self.assertEqual((shelf.spot("a"), shelf.spot("b")), (None, ("3", 0.5)))

    def test_the_toy_slot_defaults_to_the_red_ball(self):
        store = FakeSettings()
        shelf = Shelf(store)
        self.assertEqual(shelf.toy(), "", "空 = 红球")
        shelf.set_toy("bone/yellow")
        self.assertEqual(Shelf(store).toy(), "bone/yellow")

    def test_both_keys_are_in_the_settings_table(self):
        from widget.prefs import DEFAULTS
        self.assertEqual((DEFAULTS["things"], DEFAULTS["toy"]), ("", ""))


class LostReleaseTests(unittest.TestCase):
    def test_it_only_counts_after_the_button_was_really_seen_down(self):
        lost = hand.LostRelease()
        self.assertFalse(lost.gone(False, 5.0, 1.0), "没真看到过键按着（自测里的假按着）：不算")
        self.assertFalse(lost.gone(None, 5.0, 1.0), "问不到（离屏）：不算")
        self.assertFalse(lost.gone(True, 0.1, 1.0))
        self.assertFalse(lost.gone(False, 0.6, 1.0))
        self.assertFalse(lost.gone(True, 0.1, 1.0), "又按着了：重新数")
        self.assertFalse(lost.gone(False, 0.6, 1.0))
        self.assertTrue(lost.gone(False, 0.5, 1.0), "松开满 1 秒")
        lost.reset()
        self.assertFalse(lost.gone(False, 5.0, 1.0))


class ThingWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def window(self, front=False):
        from widget.thing_win import ThingWindow
        w = ThingWindow(mock.Mock(), "the thing", front=front)
        self.addCleanup(w.hide)
        return w

    def test_only_the_drawn_part_takes_the_mouse(self):
        """点击范围只有画出来的地方：图上够不透明的那一点才算（影子最浓也不算）；图还没出好按物件的方框。"""
        from PySide6.QtGui import QColor
        w = self.window()
        box = QRectF(10, 20, 60, 30)
        w.place(QRect(100, 100, 80, 60), QPointF(0, 0), (80.0, 60.0), QPointF(40, 50), box, None, 0.0, 1.0)
        self.assertTrue(w.covers(QPointF(40, 35)))
        self.assertFalse(w.covers(QPointF(5, 5)), "方框外面")
        shot = QImage(160, 120, QImage.Format_ARGB32_Premultiplied)   # 2 倍像素密度的图
        shot.fill(0)
        for x in range(40, 80):
            for y in range(40, 80):
                shot.setPixelColor(x, y, QColor(200, 100, 50, 255))    # 物件：实心
        for x in range(80, 120):
            for y in range(40, 80):
                shot.setPixelColor(x, y, QColor(0, 0, 0, 77))          # 影子：最浓 0.3
        shot.setDevicePixelRatio(2.0)
        w.place(QRect(100, 100, 80, 60), QPointF(0, 0), (80.0, 60.0), QPointF(40, 50), box, shot, 0.0, 1.0)
        self.assertTrue(w.covers(QPointF(30, 30)), "图上实心的地方")
        self.assertFalse(w.covers(QPointF(50, 30)), "影子点得穿")
        self.assertFalse(w.covers(QPointF(12, 22)), "方框里但图上是透明的")
        w.place(QRect(100, 100, 80, 40), QPointF(0, -20), (80.0, 60.0), QPointF(40, 50), box, shot, 0.0, 1.0)   # 窗口被屏幕边裁掉上面 20
        self.assertTrue(w.covers(QPointF(30, 10)), "图在窗口里往上挪了 20")
        w.show()
        self.assertTrue(w.update_hit(QPoint(130, 110)))
        self.assertFalse(w.update_hit(QPoint(150, 110)))
        self.assertFalse(w.update_hit(QPoint(500, 500)), "不在窗口里：不往下看")

    def test_nothing_is_touched_when_nothing_changed(self):
        w = self.window()
        args = (QRect(100, 100, 80, 60), QPointF(0, 0), (80.0, 60.0), QPointF(40, 50), QRectF(0, 0, 80, 60), None, 0.0, 1.0)
        w.place(*args)
        with mock.patch.object(w, "setGeometry") as resize, mock.patch.object(w, "move") as move, mock.patch.object(w, "update") as update:
            w.place(*args)
            self.assertEqual((resize.call_count, move.call_count, update.call_count), (0, 0, 0))
            w.place(QRect(120, 100, 80, 60), *args[1:])
            self.assertEqual((resize.call_count, move.call_count, update.call_count), (0, 1, 0), "只挪了：move，不重画")
            w.move.side_effect = None
        w.move(120, 100)
        with mock.patch.object(w, "setGeometry") as resize, mock.patch.object(w, "move") as move, mock.patch.object(w, "update") as update:
            w.place(QRect(120, 100, 80, 60), *args[1:6], 0.05, 1.0)
            self.assertEqual((resize.call_count, move.call_count, update.call_count), (0, 0, 1), "压扁了：只重画")
            w.place(QRect(120, 100, 90, 60), *args[1:6], 0.05, 1.0)
            self.assertEqual(resize.call_count, 1, "大小变了才 setGeometry")

    def test_native_attributes_are_set_again_on_every_show_and_the_front_layer_never_takes_the_mouse(self):
        """Qt 每次显示都会把原生属性改回去：所有桌面、不激活、层级在 showEvent 里重设，接不接鼠标下一帧重说。"""
        from PySide6.QtCore import Qt
        from widget import native
        w, front = self.window(), self.window(front=True)
        self.assertTrue(w.windowFlags() & Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(w.testAttribute(Qt.WA_ShowWithoutActivating))
        self.assertFalse(w.windowFlags() & Qt.WindowTransparentForInput)
        self.assertTrue(front.windowFlags() & Qt.WindowTransparentForInput)
        with mock.patch.object(native, "set_all_spaces") as spaces, mock.patch.object(native, "set_no_activate") as quiet, \
                mock.patch.object(native, "set_level") as level, mock.patch.object(native, "set_ignores_mouse") as ignore:
            for _ in range(2):
                w._accepting = True
                w.show()
                self.assertIsNone(w._accepting)
                w.hide()
            self.assertEqual((spaces.call_count, quiet.call_count, level.call_count), (2, 2, 2))
            level.assert_called_with(w, native.LEVEL_THING[0])
            ignore.assert_not_called()
            w.host.rims_changed.assert_not_called()
            front.show()
            ignore.assert_called_once_with(front, True)
            level.assert_called_with(front, native.LEVEL_RIM[0])
            self.assertFalse(front.update_hit(QPoint(0, 0)))
            self.assertEqual(front.host.rims_changed.call_count, 1, "前沿显示了：狗跟着换层")
            front.hide()
            self.assertEqual(front.host.rims_changed.call_count, 2, "藏起来了：狗回到物件前面")

    def test_each_tier_has_its_own_level(self):
        """窗口按前后那一档定层：盆那一档在窝、狗屋那一档前面，前沿在它那一档的物件和里面的狗前面。"""
        from widget import native
        from widget.thing_win import ThingWindow
        levels = [(ThingWindow(mock.Mock(), tier=k).level, ThingWindow(mock.Mock(), front=True, tier=k).level) for k in (0, 1)]
        self.assertEqual(levels, [(native.LEVEL_THING[0], native.LEVEL_RIM[0]), (native.LEVEL_THING[1], native.LEVEL_RIM[1])])


class ThingsCase(RoomCase):
    PACK = COLLIE

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.fakes = fake_styles(Path(folder.name))
        p = mock.patch.object(packs, "things", lambda found=None: list(self.fakes))
        p.start()
        self.addCleanup(p.stop)
        super().setUp()
        self.things = self.pg.things

    def make_window(self, settings=None, pack_id=None):
        win = super().make_window(settings, pack_id)
        self.addCleanup(lambda: [t.win.hide() for t in win.playground.things.items.values()])
        return win

    def put(self, key="bed/blue", settle=1.5, win=None):
        """从设置里摆出来，推到落定。"""
        win = win or self.win
        win.set_thing(key, True)
        t = win.playground.things.items[key]
        if settle:
            self.step(settle, win=win)
        return t

    def grab(self, t, to=None):
        """按在物件上拖到 to：这一拖就是拿起。按、拖都算在一秒前（推帧比真时间快）：之后马上松手是手停着放下，不是扔出去。"""
        at = QPointF(t.x, t.y - 10.0)
        ago = time.perf_counter() - 1.0
        self.things.thing_press(t, at, ago)
        to = to or (t.x, t.y - 200.0)
        self.things.thing_drag(t, QPointF(to[0], to[1] - 10.0), ago + 0.02)
        self.assertEqual(t.state, "held", "挪了算拿起")
        self.step(2 * DT)
        return to


class ThrowTests(ThingsCase):
    """物件都能像球一样扔出去，各有各的轻重软硬（包里 thing.physics → things.ThingPhysics）。"""
    BOWL = things_mod.ThingPhysics(mass_kg=0.4, bounce=0.3, friction=4.0, squash=0.06, recover=1.0, volume=0.55)
    BED = things_mod.ThingPhysics(mass_kg=2.0, bounce=0.04, friction=9.0, squash=0.3, recover=0.45, volume=0.7)
    HOUSE = things_mod.ThingPhysics(mass_kg=12.0, bounce=0.0, friction=30.0, squash=0.05, recover=0.7, dust=1.0, shake=1.0, volume=0.85)

    def place(self, key, x, phys):
        """摆出来、挪到地面上的 x、换上这套轻重软硬。"""
        t = self.put(key)
        t.phys = phys
        t.x = x
        self.things._seat(t, self.things._floor(0, x))
        self.things._settle(t)
        return t

    def fling(self, t, vx, vy, lift=300.0):
        """拿起来举到 lift 像素高，松手前 0.1 秒里手按 (vx, vy) 像素 / 秒匀速甩出去。"""
        ago = time.perf_counter() - 1.0
        x0, y0 = t.x, t.y - lift
        self.things.thing_press(t, QPointF(t.x, t.y - 10.0), ago)
        self.things.thing_drag(t, QPointF(x0, y0 - 10.0), ago + 0.3)
        self.step(2 * DT)
        now = time.perf_counter()
        for k in range(1, 6):
            self.things.thing_drag(t, QPointF(x0 + vx * 0.02 * k, y0 - 10.0 + vy * 0.02 * k), now - 0.1 + 0.02 * k)
        self.things.thing_release(t, QPointF(x0 + vx * 0.1, y0 - 10.0 + vy * 0.1), now)

    def settle(self, t, seconds=6.0, each=None):
        self.assertIsNotNone(self.step(seconds, lambda: (each(t) if each else None) or t.state == "rest"), "落定了")

    def test_a_fast_hand_throws_it_and_a_heavier_one_flies_shorter(self):
        self.start_on_floor(x=self.ag.x() + 60.0)
        ppm = self.pg.ppm
        travel = {}
        for key, phys in (("bowl/food", self.BOWL), ("house/gable", self.HOUSE)):
            t = self.place(key, self.ag.x() + 300.0, phys)
            self.fling(t, 2.5 * ppm, -1.0 * ppm)
            self.assertEqual(t.state, "fall", "手快：扔出去")
            self.assertGreater(t.vx, 0.0, "带着手的速度飞")
            start = t.x
            self.settle(t)
            self.assertEqual((t.y, t.on), (self.floor_y, ("floor", 0)), "最后落在线上")
            travel[key] = t.x - start
            self.assertAlmostEqual(self.things.shelf.spot(key)[1], (t.x - self.ag.x()) / self.ag.width(), places=4, msg="落定存位置")
            self.win.set_thing(key, False)
            self.step(0.5)
        self.assertGreater(travel["bowl/food"], 2.0 * travel["house/gable"], f"同样的手速，越重飞得越近：{travel}")

    def test_it_bounces_back_off_the_edge_of_the_screen(self):
        self.start_on_floor(x=self.ag.x() + 60.0)
        right = self.ag.x() + self.ag.width()
        t = self.place("bowl/food", right - 200.0, self.BOWL)
        self.fling(t, 6.0 * self.pg.ppm, -0.5 * self.pg.ppm)
        back = []
        self.settle(t, each=lambda t: back.append(t.vx < 0.0) and None)
        self.assertTrue(any(back), "撞到屏幕右边弹回来")
        self.assertLessEqual(t.x + 0.5 * t.width, right + 1.0, "没出屏")
        self.assertEqual(t.on, ("floor", 0))

    def test_a_soft_bed_squashes_a_lot_without_bouncing_and_a_hard_bowl_bounces(self):
        self.start_on_floor(x=self.ag.x() + 60.0)
        for key, phys in (("bed/blue", self.BED), ("bowl/food", self.BOWL)):
            t = self.place(key, self.ag.x() + 500.0, phys)
            self.fling(t, 0.0, 1.5 * self.pg.ppm, lift=360.0)
            seen = {"landed": False, "up": False, "squash": 0.0}

            def watch(t):
                if t.slide is not None or t.state == "rest" or (seen["landed"] or t.duang.value > 0.0):
                    seen["landed"] = seen["landed"] or t.duang.value > 0.0 or t.slide is not None
                if seen["landed"] and t.state == "fall" and t.slide is None and t.vy < 0.0:
                    seen["up"] = True
                seen["squash"] = max(seen["squash"], t.duang.value)
            self.settle(t, each=watch)
            if key == "bed/blue":
                self.assertFalse(seen["up"], "垫子落地几乎不弹")
                self.assertGreater(seen["squash"], 0.12, "软的：压扁一大下")
                self.assertGreaterEqual(t.duang.zeta_min, 1.0, "慢慢鼓回来，不弹过头")
            else:
                self.assertTrue(seen["up"], "盆是硬的：落地弹起来")
                self.assertLess(seen["squash"], 0.07, "硬的：几乎不压扁")
            self.win.set_thing(key, False)
            self.step(0.5)

    def test_the_landing_sound_plays_only_when_you_throw_it_or_put_it_down(self):
        import dataclasses
        from widget import sounds
        self.start_on_floor(x=self.ag.x() + 60.0)
        t = self.place("bowl/food", self.ag.x() + 400.0, self.BOWL)
        t.style = dataclasses.replace(t.style, land_sound=Path("land.wav"))
        with mock.patch.object(sounds, "play_file") as play:
            self.fling(t, 1.5 * self.pg.ppm, -0.5 * self.pg.ppm)
            self.settle(t)
            self.assertGreaterEqual(play.call_count, 1, "扔下去落地响一声")
            self.assertEqual(play.call_args_list[0].args[0], Path("land.wav"))
            self.assertLessEqual(play.call_args_list[0].args[1], self.BOWL.volume + 1e-6, "音量按包里写的，撞得轻的小一点")
            play.reset_mock()
            t.y -= 300.0                                           # 脚下的线没了那种：自己掉下去
            self.things._drop(t)
            self.settle(t)
            play.assert_not_called()                               # 不是人扔的、放下的：不出声

    def test_thrown_at_a_window_it_bounces_off_the_side_or_lands_on_the_top(self):
        """「窗口交互」开着：别的 App 的窗口侧面撞上去弹回来，扔到上沿就落在上面（和球一样）。"""
        self.start_on_floor(x=self.ag.x() + 60.0)
        ppm = self.pg.ppm
        self.assertTrue(self.win.hop_windows_on)
        top = self.floor_y - 1.0 * ppm
        self.add_window(7, self.ag.x() + 450.0, top, 240.0, h=0.95 * ppm)
        t = self.place("bowl/food", self.ag.x() + 250.0, self.BOWL)
        self.fling(t, 3.0 * ppm, 0.0, lift=0.3 * ppm)                       # 平着扔向窗口的左边（比上沿低）
        back = []
        self.settle(t, each=lambda t: back.append(t.vx < 0.0) and None)
        self.assertTrue(any(back), "撞到窗口左边弹回来")
        self.assertLess(t.x, self.ag.x() + 450.0)
        self.assertEqual(t.on, ("floor", 0))
        self.fling(t, 1.1 * ppm, -3.2 * ppm, lift=0.6 * ppm)               # 往上抛过去，落到上沿（太猛会弹一下滑出窗口那头掉下去，和球一样）
        self.settle(t)
        self.assertEqual((t.on, t.y), (("window", 7), top), "落在窗口上沿")

    def test_a_heavy_house_raises_dust_shakes_a_bowl_nearby_and_the_dog_looks(self):
        self.start_on_floor(x=self.ag.x() + 900.0)
        ppm = self.pg.ppm
        bowl = self.place("bowl/food", self.ag.x() + 400.0 + 0.6 * ppm, self.BOWL)
        house = self.place("house/gable", self.ag.x() + 400.0, self.HOUSE)
        self.grab(house, (house.x, self.floor_y - 2.2 * ppm))
        with mock.patch.object(self.pg, "thing_thudded", wraps=self.pg.thing_thudded) as thud:
            self.things.thing_release(house, QPointF(*house.pointer))            # 手停着放下：直着砸下去
            hopped = []
            self.settle(house, each=lambda t: hopped.append(bowl.state == "fall" and bowl.vy < 0.0) and None)
            thud.assert_called_once()
        self.assertTrue(any(hopped), "旁边的盆被震得跳了一下")
        dust = self.things._dust
        self.assertIsNotNone(dust, "扬起一圈灰")
        self.assertTrue(dust.windowFlags() & Qt.WindowTransparentForInput, "灰点得穿")
        self.settle(bowl)
        self.assertEqual((bowl.on, bowl.y), (("floor", 0), self.floor_y), "盆落回原地")
        self.assertIsNotNone(self.pg._thud_look, "闲着的狗看过去一眼")
        self.step(2.0)
        self.assertFalse(dust.puffs, "灰一会儿就散了")


class PlacingTests(ThingsCase):
    def test_only_wired_roles_with_a_model_are_offered(self):
        self.assertEqual([t.key for t in self.win.things_available()], ["bed/blue", "house/gable", "bowl/food", "house/long", "house/broken"],
                         "只列有用法的：窝、屋、盆。摆设（长椅）、栏、玩具不列")
        self.assertEqual(things_mod.SUPPORTED_ROLES, {"bed", "house", "bowl"}, "摆在那跟狗没有来往的不如不要")

    def test_styles_that_are_no_longer_offered_cannot_be_put_out_and_remembered_ones_are_ignored(self):
        """长椅、栏这些不列的款：点不出来；62 里摆过、设置里还记着摆着的，这次不显示、不算数、不报错，那一行记录留着不动。"""
        remembered = json.dumps([{"key": "bench/bench", "on": True, "screen": "", "fx": 0.5}, {"key": "barrier/low", "on": True, "screen": "", "fx": 0.3},
                                 {"key": "bowl/food", "on": True, "screen": "", "fx": 0.7}])
        win = self.make_window({"things": remembered})
        self.start_on_floor(win=win)
        things = win.playground.things
        self.assertEqual(list(things.items), ["bowl/food"], "记着的长椅、栏不出来")
        self.assertEqual((win.things_placed(), win.thing_on("bench/bench"), win.thing_on("barrier/low")), (1, False, False))
        win.set_thing("bench/bench", True)
        win.set_thing("barrier/low", False)
        self.step(0.5, win=win)
        self.assertEqual(list(things.items), ["bowl/food"])
        self.assertEqual(win.playground.frames, win.playground._native_frames, "也没有混进窗口表的台子")
        win.put_things_away()
        self.step(0.5, win=win)
        self.assertEqual((list(things.items), win.things_placed()), ([], 0))
        rows = {r["key"]: r["on"] for r in json.loads(win.settings.values["things"])}
        self.assertEqual(rows, {"bench/bench": True, "barrier/low": True, "bowl/food": False}, "不认识的那几行原样留着")

    def test_nothing_out_means_nothing_is_touched(self):
        """一件没摆：update 什么都不碰。"""
        from PySide6.QtGui import QCursor
        self.start_on_floor()
        self.assertEqual((self.things.items, self.things.live_windows(), self.win.things_placed()), ({}, [], 0))
        before = self.pg.live_windows()
        with mock.patch.object(QCursor, "pos", side_effect=AssertionError("no cursor query")), \
                mock.patch.object(self.win.view, "ready", side_effect=AssertionError("no canvas query")):
            self.things.update(DT)
        self.assertEqual(self.pg.live_windows(), before)
        self.step(0.5)
        self.assertTrue(self.things.quiet())
        self.assertNotIn("things", self.win.settings.values, "没摆过：设置里什么都没写")

    def test_it_drops_onto_the_floor_beside_the_dog_and_is_remembered(self):
        """从设置里摆出来：狗踩的那块屏的地面上、狗朝屏幕中间的那一侧，从 0.3 米落下来、duang 一下，存位置。"""
        self.start_on_floor(x=140.0)                         # 狗在屏幕左边：物件放它右边
        pg, ppm = self.pg, self.pg.ppm
        self.win.set_thing("bowl/food", True)
        t = self.things.items["bowl/food"]
        self.assertEqual(t.state, "fall")
        self.assertAlmostEqual(t.y, self.floor_y - DROP_IN_M * ppm, delta=0.5)
        self.assertAlmostEqual(t.x, 140.0 + FIRST_GAP_M * ppm + t.lay.left_m * ppm, delta=1.0, msg="离狗 1.2 米再加半个物件宽")
        self.assertTrue(t.win.isVisible())
        self.assertIn(t.win, pg.live_windows(), "截图时照常画，不抓、不换成快照")
        self.assertIn(t.win, self.win.live_windows())
        self.assertFalse(self.things.quiet(), "在落：算有动静")
        self.assertFalse(pg.quiet())
        x = t.x
        landed = self.step(1.0, lambda: t.state == "rest")
        self.assertIsNotNone(landed)
        self.assertEqual((t.x, t.y, t.on), (x, self.floor_y, ("floor", 0)), "直着落到地面")
        self.assertGreater(t.duang.value, 0.0, "落地 duang 一下")
        self.step(1.5)
        self.assertEqual(t.duang.value, 0.0)
        self.assertEqual(t.alpha, 1.0)
        self.assertTrue(self.things.quiet())
        self.assertTrue(self.win.thing_on("bowl/food"))
        self.assertEqual(self.win.things_placed(), 1)
        screen, fx = self.things.shelf.spot("bowl/food")
        self.assertAlmostEqual(fx, (x - self.ag.x()) / self.ag.width(), places=4, msg="记的是占屏宽的几成")
        geo = t.win.geometry()
        self.assertEqual(geo.left(), round(t.x - t.lay.cx))
        self.assertEqual(geo.top(), round(t.y + t.lay.base - t.lay.h), "画出来最低的那一点落在地面上")
        self.assertEqual(self.pg.ball.resting and self.pg.roam.task is None, True, "狗和球没反应：这张假表里的盆没写 serves，不是能吃的盆")

    def test_a_second_thing_goes_one_place_further_out(self):
        self.start_on_floor(x=60.0)
        bowl = self.put("bowl/food")
        bed = self.put("bed/blue")
        self.assertGreater(bed.span()[0], bowl.span()[1], "那里已经有别的物件：再往外挪一个身位，不叠着")
        self.assertEqual(self.things.shelf.placed(), ["bowl/food", "bed/blue"])

    def test_the_bed_grows_with_the_dog_and_wide_things_are_capped_to_the_screen(self):
        self.start_on_floor()
        bed = self.put("bed/blue")
        self.assertAlmostEqual(bed.geo[1], 1.6 * self.pack.height_m / 0.8, places=3, msg="狗窝 1.6 倍再乘狗的身高比")
        self.assertAlmostEqual(bed.width, 0.8 * bed.geo[1] * self.pg.ppm, delta=1.0)
        bridge = self.put("house/long")
        self.assertAlmostEqual(bridge.width, SCREEN_SHARE * self.ag.width(), delta=1.0, msg="6 米的长屋比屏宽：整件缩到屏宽的七成")
        self.assertLess(bridge.geo[1], 1.0)
        for t in (bed, bridge):
            self.assertGreaterEqual(t.win.geometry().left(), self.ag.left())
            self.assertLessEqual(t.win.geometry().right(), self.ag.right(), "窗口不出屏")

    def test_a_new_dog_of_another_size_resizes_the_bed_where_it_is(self):
        """换模型（things.pet_changed）：狗窝（fit_pet）按新狗的身高当场重排、位置不动（大了出屏的照旧夹回屏里，这里离屏边远）；盆不变。"""
        import dataclasses
        self.start_on_floor(x=60.0)
        bed, bowl = self.put("bed/blue"), self.put("bowl/food")
        before = {k: (t.geo, t.x, t.y, t.on) for k, t in self.things.items.items()}
        self.pg.pack = dataclasses.replace(self.pg.pack, height_m=self.pack.height_m * 0.86 / 0.80)   # 边牧 0.80 → 萨摩耶 0.86
        self.things.pet_changed()
        self.assertAlmostEqual(bed.geo[1], before["bed/blue"][0][1] * 0.86 / 0.80, places=3, msg="狗窝大 7.5%")
        self.assertEqual((bed.x, bed.y, bed.on), before["bed/blue"][1:], "位置不动")
        self.assertEqual((bowl.geo, bowl.x, bowl.y, bowl.on), before["bowl/food"], "盆不变")
        self.assertTrue(bed.need_shot or bed.shot is None, "图接着重出")

    def test_a_mirrored_style_turns_its_door_to_the_middle_of_the_screen(self):
        """尖顶狗屋：屏幕左半边按 +35 度画，右半边按 −35 度重画（门朝屏幕中间）。落定时才换边。"""
        self.start_on_floor(x=700.0)                          # 狗在右边：物件放它左边
        house = self.put("house/gable")
        mid = self.ag.center().x()
        self.assertEqual((house.right_half, house.geo[2]), (house.x > mid, -35.0 if house.x > mid else 35.0))
        side = house.right_half
        other = (self.ag.left() + 150.0) if side else (self.ag.right() - 150.0)
        self.grab(house, (other, self.floor_y - 100.0))
        self.assertEqual(house.right_half, side, "拿着的时候不换")
        self.things.thing_release(house, QPointF(other, self.floor_y - 110.0))
        self.step(1.5)
        self.assertEqual((house.state, house.right_half, house.geo[2]), ("rest", not side, 35.0 if side else -35.0))

    def test_a_file_that_cannot_be_drawn_is_dropped_quietly(self):
        self.start_on_floor()
        with self.assertLogs("things", level="WARNING"):
            self.win.set_thing("house/broken", True)
        self.assertNotIn("house/broken", self.things.items)
        self.assertNotIn("house/broken", [t.key for t in self.win.things_available()], "这一款当作不在")
        self.win.set_thing("no/such", True)
        self.assertEqual(self.things.items, {})

    def test_putting_away_fades_out_and_it_comes_back_where_it_was(self):
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        x, win = t.x, t.win
        self.grab(t, (500.0, self.floor_y - 80.0))
        self.things.thing_release(t, QPointF(500.0, self.floor_y - 90.0))
        self.step(1.5)
        self.assertNotEqual(t.x, x)
        x = t.x
        self.win.set_thing("bowl/food", False)
        self.assertEqual((t.state, self.win.thing_on("bowl/food"), self.win.things_placed()), ("gone", False, 0))
        self.assertTrue(win.isVisible(), "0.2 秒淡出")
        self.things.thing_press(t, QPointF(t.x, t.y - 5.0))
        self.assertEqual(t.state, "gone", "正在收的不接鼠标")
        self.step(0.4)
        self.assertNotIn("bowl/food", self.things.items)
        self.assertFalse(win.isVisible())
        self.assertEqual(self.pg.live_windows(), [w for w in self.pg.live_windows() if w is not win])
        back = self.put("bowl/food")
        self.assertAlmostEqual(back.x, x, delta=1.0, msg="再摆出来回到原处")
        self.assertEqual(back.y, self.floor_y)
        self.put("bed/blue")
        self.win.put_things_away()
        self.step(0.4)
        self.assertEqual((self.things.items, self.win.things_placed()), ({}, 0), "全部收起")
        self.assertEqual({r["key"] for r in self.things.shelf._rows if r["fx"] >= 0}, {"bowl/food", "bed/blue"}, "位置都留着")

    def test_it_is_still_there_after_a_restart(self):
        """重开（新建一个窗口、同一份设置）：摆着的还在原处，直接在地面上（不再落一遍）；收起来的不出来。"""
        self.start_on_floor(x=140.0)
        bowl = self.put("bowl/food")
        self.put("bed/blue")
        self.win.set_thing("bed/blue", False)
        self.step(0.4)
        saved = dict(self.win.settings.values)
        self.pg.stop()
        again = self.make_window(saved)
        self.start_on_floor(x=600.0, win=again)
        things = again.playground.things
        self.assertEqual(list(things.items), ["bowl/food"])
        t = things.items["bowl/food"]
        self.assertEqual((t.state, t.y), ("rest", self.floor_y))
        self.assertAlmostEqual(t.x, bowl.x, delta=1.0)
        self.assertTrue(t.win.isVisible())
        self.assertFalse(again.thing_on("bed/blue"))

    def test_a_remembered_screen_that_is_gone_falls_back_to_the_main_screen(self):
        win = self.make_window({"things": json.dumps([{"key": "bowl/food", "on": True, "screen": "unplugged", "fx": 0.25},
                                                      {"key": "gone/model", "on": True, "screen": "", "fx": 0.5}])})
        self.start_on_floor(win=win)
        things = win.playground.things
        self.assertEqual(list(things.items), ["bowl/food"], "记着的款这次不在（模型没了）：留着不动、不显示")
        self.assertAlmostEqual(things.items["bowl/food"].x, self.ag.x() + 0.25 * self.ag.width(), delta=1.0, msg="照那一成宽放到主屏")
        self.assertIn("gone/model", [r["key"] for r in things.shelf._rows])

    def test_turning_dynamic_off_hides_them_and_on_brings_them_back_in_place(self):
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        x, win = t.x, t.win
        self.win.set_dynamic(False)
        self.assertFalse(self.pg.active)
        self.assertTrue(self.win.thing_on("bowl/food"), "还算摆着")
        self.things._fade.setCurrentTime(self.things._fade.duration())       # 0.2 秒淡出走完
        self.assertFalse(win.isVisible())
        self.assertEqual(self.things.live_windows(), [])
        self.win.set_thing("bed/blue", True)                                 # 关着的时候只记下
        self.assertNotIn("bed/blue", self.things.items)
        self.win.set_dynamic(True)
        self.assertTrue(self.pg.active)
        t = self.things.items["bowl/food"]
        self.assertTrue(t.win.isVisible())
        self.assertEqual((t.x, t.y, t.state, t.alpha), (x, self.floor_y, "rest", 0.0), "还在原地，淡入")
        self.assertIn("bed/blue", self.things.items, "关着的时候摆的，开了才出来")
        self.step(0.5)
        self.assertEqual(t.alpha, 1.0)

    def test_fail_safe_just_hides(self):
        self.start_on_floor()
        t = self.put("bowl/food")
        self.grab(t)
        self.pg.fail_safe()
        self.assertFalse(t.win.isVisible())
        self.assertIsNone(self.things._held)


class StackingTests(ThingsCase):
    """前后由窗口的层级管（native.LEVEL_*）：同一层里系统自己会重排（点了的提到最前：一切桌面盆就跑到窝后面），
    要一直保持的前后都分在不同的层。单测里没有原生窗口：验每个窗口该在哪一层、显示时设没设；真的前后在真机自测（things 那一步）读回。"""

    def test_one_level_per_layer_from_back_to_front(self):
        """从后到前：圈 → 窝、狗屋 → 趴在窝里的狗 → 窝沿 → 盆 → 平时的狗（在盆边吃喝也是）→ 盆沿 → 球 → 气泡、胶囊；
        都在菜单栏（24）上面、弹出菜单（101）下面。"""
        from widget import native
        order = [native.LEVEL_RING, native.LEVEL_THING[0], native.LEVEL_DOG_IN[0], native.LEVEL_RIM[0], native.LEVEL_THING[1],
                 native.LEVEL_DOG_IN[1], native.LEVEL_RIM[1], native.LEVEL_BALL, native.LEVEL_TOP]
        self.assertEqual(order, sorted(set(order)), "一层一个，从后到前")
        self.assertEqual(native.LEVEL_DOG, native.LEVEL_DOG_IN[1], "平时的狗在所有物件前面")
        self.assertGreater(order[0], 24)
        self.assertLess(order[-1], 101)

    def test_bowls_are_a_tier_in_front_of_beds_and_houses(self):
        """饭盆水盆在狗屋、垫子前面——盆在前一档那一层，窝、狗屋在后一档；每次显示都设到那一层（Qt 显示时会改回去）。"""
        from widget import native
        self.start_on_floor(x=140.0)
        levels = []
        with mock.patch.object(native, "set_level", side_effect=lambda win, level: levels.append((win, level)) or True):
            bowl, bed, house = self.put("bowl/food"), self.put("bed/blue"), self.put("house/gable")
        self.assertEqual([t.win.level for t in (bowl, bed, house)], [native.LEVEL_THING[1], native.LEVEL_THING[0], native.LEVEL_THING[0]])
        for t in (bowl, bed, house):
            self.assertIn((t.win, t.win.level), levels)

    def test_the_touched_one_comes_to_the_front_of_its_tier_and_is_remembered(self):
        """两个窝叠着，点了的那个要在前面——按下就提到它那一层的最前面；设置里的先后跟着挪，重开还是它在前。"""
        self.start_on_floor(x=140.0)
        bed = self.put("bed/blue")
        self.put("house/gable")
        self.assertEqual(self.things.shelf.placed(), ["bed/blue", "house/gable"])
        with mock.patch.object(bed.win, "raise_") as raised, mock.patch.object(bed.win, "lower") as lowered:
            self.things.thing_press(bed, QPointF(bed.x, bed.y - 5.0))
            self.things.thing_release(bed, QPointF(bed.x, bed.y - 5.0))
            self.app.processEvents()
        raised.assert_called_once_with()
        lowered.assert_not_called()
        self.assertEqual(self.things.shelf.placed(), ["house/gable", "bed/blue"])
        self.assertEqual([r["key"] for r in json.loads(self.win.settings.values["things"]) if r["on"]], ["house/gable", "bed/blue"], "存下来了")

    def test_coming_back_shows_them_in_the_remembered_order(self):
        """重开、开回灵动交互：按先后从早到晚一件件显示（后显示的在它那一层最前面）——点过的那件最后。"""
        self.start_on_floor(x=140.0)
        bed, house, bowl = self.put("bed/blue"), self.put("house/gable"), self.put("bowl/food")
        self.things.thing_press(bed, QPointF(bed.x, bed.y - 5.0))
        self.things.thing_release(bed, QPointF(bed.x, bed.y - 5.0))
        self.pg.stop()
        shown = []
        for t in (bed, house, bowl):
            t.win.hide()
            p = mock.patch.object(t.win, "show", side_effect=lambda key=t.key: shown.append(key))
            p.start()
            self.addCleanup(p.stop)
        self.pg.start()
        self.assertEqual(shown, ["house/gable", "bowl/food", "bed/blue"])


class HandlingTests(ThingsCase):
    def test_a_click_only_squashes_it(self):
        """点一下只 duang，位置不变，别的什么都不发生（照球）。"""
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        at, moves = (t.x, t.y), self.win.settings.values["things"]
        self.things.thing_press(t, QPointF(t.x, t.y - 5.0))
        self.assertEqual(t.state, "tap")
        self.assertTrue(t.duang.pressing)
        self.step(0.08)
        self.assertGreater(t.duang.value, 0.0)
        self.things.thing_drag(t, QPointF(t.x + 3.0, t.y - 5.0))
        self.assertEqual(t.state, "tap", "挪了不到 6 像素：不算拿起")
        self.things.thing_release(t, QPointF(t.x + 3.0, t.y - 5.0))
        self.assertEqual((t.state, t.duang.pressing, (t.x, t.y), t.on), ("rest", False, at, ("floor", 0)))
        self.step(1.5)
        self.assertEqual(t.duang.value, 0.0)
        self.assertEqual(self.win.settings.values["things"], moves)
        self.assertIsNone(self.pg.roam.task)

    def test_holding_long_enough_picks_it_up(self):
        from widget.playground import TAP_HOLD_S
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        self.things.thing_press(t, QPointF(t.x, t.y - 5.0))
        self.step(TAP_HOLD_S - 2 * DT)
        self.assertEqual(t.state, "tap")
        self.step(4 * DT)
        self.assertEqual((t.state, t.on), ("held", None), "按够 0.15 秒算拿起")
        self.assertFalse(self.things.quiet())

    def test_let_go_with_a_still_hand_it_falls_straight_down(self):
        """手停着松开（拖完停一下再放）：直着落，不带手的速度；落到地面、弹完停下、存位置。手快的扔出去见 ThrowTests。"""
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        self.grab(t, (500.0, self.floor_y - 300.0))
        self.assertAlmostEqual(t.x, 500.0, delta=1.0)
        self.assertAlmostEqual(t.y, self.floor_y - 300.0, delta=1.0)
        self.assertEqual(t.win.geometry().left(), round(t.x - t.lay.cx), "窗口每帧跟到手上")
        self.things.thing_release(t, QPointF(500.0, self.floor_y - 310.0))
        self.assertEqual((t.state, t.vx, t.vy), ("fall", 0.0, 0.0), "直着落：不带手的速度")
        x, xs = t.x, []
        self.step(3.0, lambda: xs.append(t.x) or t.state == "rest")
        self.assertEqual(set(xs), {x}, "一路直上直下")
        self.assertEqual((t.x, t.y, t.on), (x, self.floor_y, ("floor", 0)))
        self.assertAlmostEqual(self.things.shelf.spot("bowl/food")[1], (x - self.ag.x()) / self.ag.width(), places=4, msg="落定存位置")

    def test_released_right_on_the_line_it_is_just_put_down(self):
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        self.grab(t, (420.0, self.floor_y))
        self.things.thing_release(t, QPointF(420.0, self.floor_y - 10.0))
        self.assertEqual((t.state, t.y), ("rest", self.floor_y), "脚下就是线：原地放下，不落")
        self.assertLess(t.duang.value, 0.5 * t.duang.DEPTH, "不 duang（落地的那一下是压到底）")

    def test_the_window_stays_inside_the_screen_under_the_pointer(self):
        self.start_on_floor(x=140.0)
        t = self.put("bed/blue")
        for to in ((-500.0, -500.0), (5000.0, 100.0), (400.0, 5000.0)):
            self.grab(t, to) if t.state != "held" else self.things.thing_drag(t, QPointF(*to))
            self.step(2 * DT)
            geo = t.win.geometry()
            self.assertGreaterEqual(geo.left(), self.ag.left(), to)
            self.assertLessEqual(geo.right(), self.ag.right(), to)
            self.assertGreaterEqual(geo.top(), self.ag.top(), to)
            self.assertLessEqual(t.y, self.floor_y, "最低到地面")

    def test_a_lost_release_lets_go_after_a_second(self):
        """按着的时候切走了、系统弹窗：松手事件没来。键松开 1 秒还没来就当松了手，原地落下。"""
        from widget.playground import LOST_UP_S
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        down = [True]
        with mock.patch.object(self.pg, "_button_down", lambda: down[0]):
            self.grab(t, (500.0, self.floor_y - 200.0))
            t.win._pressed = True
            self.step(0.3)
            down[0] = False
            self.step(LOST_UP_S * 0.6)
            self.assertEqual(t.state, "held")
            self.step(LOST_UP_S * 0.4 + 0.1)
            self.assertIn(t.state, ("fall", "rest"))
            self.assertFalse(t.win._pressed)
            self.step(1.5)
            self.assertEqual((t.state, t.y), ("rest", self.floor_y))

    def test_a_resting_thing_costs_no_window_calls(self):
        """停着的物件每帧零次挪窗口、改大小、重画，也不再告诉系统接不接鼠标。"""
        from widget import native
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food", settle=3.0)
        self.assertTrue(self.things.quiet())
        told = []
        with mock.patch.object(t.win, "setGeometry") as resize, mock.patch.object(t.win, "move") as move, mock.patch.object(t.win, "update") as update, \
                mock.patch.object(t.win, "show") as show, mock.patch.object(native, "set_ignores_mouse", side_effect=lambda w, on: told.append(w) or True):
            self.step(0.1)                                        # 接不接鼠标说过一次（offscreen 上说不成，这里当它说成了）
            told.clear()
            self.step(1.0)
            self.assertEqual((resize.call_count, move.call_count, update.call_count, show.call_count, told.count(t.win)), (0, 0, 0, 0, 0))

    def test_the_hit_area_follows_the_pointer(self):
        """鼠标在物件上才接鼠标；没出图时按物件的方框。变了才告诉系统。"""
        from PySide6.QtGui import QCursor
        from widget import native
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food", settle=2.0)
        on_it, off_it = QPoint(round(t.x), round(t.y - 8.0)), QPoint(round(t.x), round(t.y - 300.0))
        calls = []
        with mock.patch.object(native, "set_ignores_mouse", side_effect=lambda w, on: calls.append((w, on)) or True):
            with mock.patch.object(QCursor, "pos", return_value=off_it):
                self.step(3 * DT)
            with mock.patch.object(QCursor, "pos", return_value=on_it):
                self.step(3 * DT)
            with mock.patch.object(QCursor, "pos", return_value=off_it):
                self.step(3 * DT)
        mine = [on for w, on in calls if w is t.win]
        self.assertEqual(mine, [True, False, True], "不在物件上点得穿，在上面才接，每次变了只说一次")

    def test_right_click_says_no_more_with_its_name_and_a_click_puts_it_away(self):
        """右键（触摸板两指点）：不带开关的小胶囊「我不要{这一款的名字}了」，点一下 = 收起来，胶囊跟着收；鼠标走远了、拿起来胶囊也收。"""
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import popup
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        self.things.thing_menu(t, QPoint(round(t.x), round(t.y - 8.0)))
        menu = self.win._thing_menu
        self.addCleanup(menu.hide)
        self.assertTrue(menu.isVisible())
        self.assertEqual((menu.text, menu.action), ("No more food", True), "不带开关，名字放进句子里头一个字母小写")
        self.assertIsNot(menu, self.win._ball_menu)
        self.things.thing_press(t, QPointF(t.x, t.y - 8.0))
        self.assertFalse(menu.isVisible(), "一按物件胶囊就收")
        self.things.thing_release(t, QPointF(t.x, t.y - 8.0))
        self.things.thing_menu(t, QPoint(round(t.x), round(t.y - 8.0)))
        self.assertTrue(menu.isVisible())
        far = menu.geometry().center() + QPoint(round(popup.LEAVE_PX * menu._k) + menu.width(), 0)
        with mock.patch.object(popup.native, "mouse_any_down", lambda: False), mock.patch.object(popup.QCursor, "pos", lambda: far):
            menu._watch()
        self.assertFalse(menu.isVisible(), "鼠标走远了就收")
        self.assertTrue(self.win.thing_on("bowl/food"), "收的只是胶囊")
        self.things.thing_menu(t, QPoint(round(t.x), round(t.y - 8.0)))
        c = menu.pill_rect().center()
        menu.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, c, QPointF(menu.mapToGlobal(c.toPoint())), Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
        self.assertFalse(menu.isVisible(), "点了胶囊跟着收")
        self.assertEqual((t.state, self.win.thing_on("bowl/food")), ("gone", False), "这一件收起来了")
        from widget import i18n
        i18n.set_language("zh")
        self.addCleanup(i18n.set_language, "en")
        bed = self.put("bed/blue")
        self.things.thing_menu(bed, QPoint(round(bed.x), round(bed.y - 8.0)))
        self.assertEqual(menu.text, "我不要假blue了", "写的是这一款的名字")

    def test_the_power_saving_pace_wakes_near_a_thing(self):
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        g = t.win.geometry()
        self.assertTrue(self.things.near(QPoint(g.right() + 100, g.center().y()), 120))
        self.assertFalse(self.things.near(QPoint(g.right() + 200, g.center().y()), 120))


class WindowTopTests(ThingsCase):
    def on_window(self, key="bowl/food", number=7, x=380.0, top=420.0, w=260.0):
        self.start_on_floor(x=140.0)
        t = self.put(key)
        self.add_window(number, x, top, w)
        self.grab(t, (x + w / 2, top - 120.0))
        self.things.thing_release(t, QPointF(x + w / 2, top - 130.0))
        self.assertIsNotNone(self.step(2.0, lambda: t.state == "rest"))
        self.assertEqual((t.on, t.y), (("window", number), top), "落在别的 App 的窗口上沿")
        return t

    def test_it_lands_on_a_window_top_and_follows_the_window(self):
        t = self.on_window()
        x = t.x
        self.frames[7] = (430.0, 400.0, 260.0, 200.0)             # 窗口被拖走了一点
        self.step(0.5)
        self.assertEqual((t.x, t.y, t.on), (x + 50.0, 400.0, ("window", 7)), "窗口挪了跟着挪")
        self.assertGreater(t.follow, 0.0)
        self.frames[7] = (440.0, 400.0, 260.0, 200.0)
        self.step(2 * DT)
        self.assertEqual(t.x, x + 60.0, "刚挪过的这一小会每帧跟")
        self.step(FOLLOW_S + 0.3)
        self.assertEqual(t.follow, 0.0, "停了就不每帧问了")
        with mock.patch.object(self.pg, "_frame", side_effect=AssertionError("asked the window every frame")):
            self.step(0.2)
        self.assertTrue(self.things.quiet())
        saved = self.things.shelf.spot("bowl/food")
        self.assertAlmostEqual(saved[1], (x - self.ag.x()) / self.ag.width(), places=3, msg="位置只记它落下那一处的 x（重开落在正下方的地面）")

    def test_the_window_going_away_drops_it(self):
        t = self.on_window()
        x = t.x
        del self.frames[7]
        self.step(2.0)
        self.assertEqual((t.state, t.x, t.y, t.on), ("rest", x, self.floor_y, ("floor", 0)), "窗口没了：落到下面的地面")

    def test_turning_off_jump_onto_windows_drops_it(self):
        t = self.on_window()
        self.win.set_play_option("hop_windows", False)
        self.step(2.0)
        self.assertEqual((t.state, t.y, t.on), ("rest", self.floor_y, ("floor", 0)))
        self.grab(t, (510.0, 300.0))
        self.things.thing_release(t, QPointF(510.0, 290.0))
        self.step(2.0)
        self.assertEqual(t.y, self.floor_y, "关着的时候窗口上沿不接物件")

    def test_a_window_too_narrow_or_too_close_to_the_top_does_not_take_it(self):
        self.start_on_floor(x=140.0)
        bed = self.put("bed/blue")
        self.add_window(8, 400.0, 420.0, 0.3 * bed.width)           # 不到物件宽度的一半
        self.grab(bed, (400.0 + 0.15 * bed.width, 300.0))
        self.things.thing_release(bed, QPointF(400.0 + 0.15 * bed.width, 290.0))
        self.step(2.0)
        self.assertEqual(bed.y, self.floor_y)
        self.add_window(9, 300.0, self.ag.top() + 0.5 * bed.height, 400.0)   # 上面放不下物件那么高
        self.grab(bed, (500.0, self.ag.top() + 0.5 * bed.height))
        self.things.thing_release(bed, QPointF(500.0, self.ag.top()))
        self.step(2.0)
        self.assertEqual(bed.on, ("floor", 0))

    def test_a_covered_stretch_of_the_top_drops_it(self):
        t = self.on_window()
        self.frames = {9: (t.x - 60.0, 300.0, 120.0, 300.0), **self.frames}   # 前面开了一个窗口，正好盖住它脚下那一段
        self.step(2.0)
        self.assertNotEqual(t.on, ("window", 7))
        self.assertEqual(t.state, "rest")

    def test_turning_dynamic_off_and_on_keeps_it_on_its_window(self):
        t = self.on_window()
        x = t.x
        self.win.set_dynamic(False)
        self.win.set_dynamic(True)
        self.step(1.0)
        t = self.things.items["bowl/food"]
        self.assertEqual((t.x, t.y, t.on), (x, 420.0, ("window", 7)), "再开回来还在原地")


class RoomChangeTests(ThingsCase):
    def test_dragging_the_size_slider_moves_nothing_until_it_settles(self):
        """拖大小滑杆的过程里物件不动、不重排；停稳 0.25 秒后各重排一次，窗口各改一次大小。"""
        self.start_on_floor(x=140.0)
        bed = self.put("bed/blue", settle=2.5)
        w0, ppm0 = bed.lay.w, self.pg.ppm
        with mock.patch.object(bed.win, "setGeometry", wraps=bed.win.setGeometry) as resize:
            for k in (1.1, 1.2, 1.3, 1.4):
                self.win.set_scale(k)
                self.step(0.1)
            self.assertEqual((bed.lay.w, resize.call_count), (w0, 0), "还在拖：不动")
            self.assertFalse(self.things.quiet())
            self.step(RESIZE_SETTLE_S + 0.1)
            self.assertEqual(resize.call_count, 1, "停稳了改一次")
        self.assertAlmostEqual(bed.width / (self.pg.ppm / ppm0), w0 - 2 * 6 - 0.0, delta=0.12 * w0)
        self.assertAlmostEqual(bed.lay.frame.ppm, 240.0 * 1.4)
        floor = self.ag.y() + self.ag.height() - 18.0 * 1.4
        self.assertEqual((bed.y, bed.on), (floor, ("floor", 0)), "坐回新的地面（地面离底边的距离跟着大小变）")
        self.assertTrue(bed.need_shot or bed.shot is None, "图等着重出")

    def test_the_dock_appearing_reseats_things_on_the_new_floor(self):
        from PySide6.QtGui import QScreen
        self.start_on_floor(x=140.0)
        t = self.put("bowl/food")
        ag = self.ag
        raised = QRect(ag.x(), ag.y(), ag.width(), ag.height() - 70)
        with mock.patch.object(QScreen, "availableGeometry", lambda s: raised):
            self.win._after_floor_change()
            self.assertEqual((t.y, t.state), (self.floor_y - 70, "rest"), "程序坞出来：直接坐到新地面上")
            self.assertGreater(t.duang.value, 0.0)
        self.win._after_floor_change()
        self.assertEqual(t.y, self.floor_y)

    def test_two_screens_it_never_straddles_and_changes_screen_with_the_pointer(self):
        """两块屏左右挨着：拖着的物件整个夹在鼠标所在的那块屏里，鼠标过了交界一下换到那块屏；落定记的是那块屏。"""
        self.start_on_floor(x=140.0)
        t = self.put("bed/blue")
        ag = self.ag
        left = Area(ag.x(), ag.y(), ag.x() + ag.width(), ag.y() + ag.height(), "left")
        right = Area(left.right, ag.y(), left.right + 1200, ag.y() + 700, "right")
        with mock.patch.object(self.pg, "rebuild_world", lambda: setattr(self.pg, "world", World([left, right], 18.0, [left, right]))):
            self.pg.rebuild_world()
            self.pg._sups = None
            self.things.screens_changed()
            self.assertEqual((t.area, t.screen), (0, "left"))
            edge = left.right
            self.grab(t, (edge - 20.0, 400.0))
            self.assertLessEqual(t.win.geometry().right(), edge - 1, "鼠标还在左屏：整个窗口在左屏")
            self.assertEqual(t.area, 0)
            self.things.thing_drag(t, QPointF(edge + 20.0, 400.0))
            self.step(2 * DT)
            self.assertEqual(t.area, 1)
            self.assertGreaterEqual(t.win.geometry().left(), edge, "过了交界：一下换到右屏，不骑在中间")
            self.things.thing_release(t, QPointF(edge + 20.0, 400.0))
            self.step(2.0)
            self.assertEqual((t.state, t.on, t.y), ("rest", ("floor", 1), 700.0 - 18.0))
            self.assertGreaterEqual(t.win.geometry().left(), edge)
            self.assertEqual(self.things.shelf.spot("bed/blue")[0], "right")
            with mock.patch.object(self.pg, "rebuild_world", lambda: setattr(self.pg, "world", World([left], 18.0, [left]))):
                self.pg.rebuild_world()                          # 右屏拔了
                self.pg._sups = None
                self.things.screens_changed()
                self.assertEqual((t.area, t.on), (0, ("floor", 0)), "那块屏拔了：放到主屏的地面上")
                self.step(0.2)
                self.assertLessEqual(t.win.geometry().right(), left.right)


class ShotTests(ThingsCase):
    """出图（offscreen 没有显卡：这里把画布当成好了的、出图换成假的）。"""

    def fake_canvas(self, busy=lambda: False):
        made = []

        def shoot(view, model, lay, dpr):
            img = QImage(max(1, round(lay.w * dpr)), max(1, round(lay.h * dpr)), QImage.Format_ARGB32_Premultiplied)
            img.fill(0xFF336699)
            made.append((model, lay, dpr))
            return img
        for p in (mock.patch.object(self.win.view, "ready", lambda: True), mock.patch.object(things_mod.thing_art, "shoot", shoot),
                  mock.patch.object(self.win, "_scene_busy", lambda: busy())):
            p.start()
            self.addCleanup(p.stop)
        return made

    def test_one_picture_a_frame_and_it_fades_in_when_ready(self):
        self.start_on_floor(x=140.0)
        made = self.fake_canvas()
        self.win.set_thing("bowl/food", True)
        self.win.set_thing("bed/blue", True)
        bowl, bed = self.things.items["bowl/food"], self.things.items["bed/blue"]
        self.assertEqual((bowl.shot, bed.shot), (None, None), "没出好之前窗口是空的")
        self.pg.update(DT)
        self.assertEqual(len(made), 1, "一帧最多出一件")
        self.assertIsNotNone(bowl.shot)
        self.assertIsNone(bed.shot)
        self.assertLessEqual(bowl.alpha, DT / 0.2 + 1e-6, "出好了才从 0 淡入")
        self.pg.update(DT)
        self.assertEqual(len(made), 2)
        self.assertIs(bed.win.shot, bed.shot)
        self.assertEqual(bed.shot.devicePixelRatio(), made[1][2])
        self.step(2.5)
        self.assertEqual(len(made), 2, "出过的不再出")
        self.assertEqual((bowl.alpha, bowl.need_shot), (1.0, False))
        self.assertTrue(self.things.quiet())
        self.win.set_scale(1.3)
        self.step(RESIZE_SETTLE_S + 0.3)
        self.assertEqual(len(made), 4, "大小停稳了各重出一次")
        self.assertEqual(len(self.things._shots), 2, "换大小以前的图丢掉")
        self.win.set_thing("bed/blue", False)
        self.step(0.5)
        self.assertEqual(len(self.things._shots), 1, "收起来的款的图丢掉")

    def test_it_waits_while_the_dog_is_moving_but_not_for_ever(self):
        busy = [True]
        self.start_on_floor(x=140.0)
        made = self.fake_canvas(lambda: busy[0])
        self.win.set_thing("bowl/food", True)
        self.things.update(DT)
        self.assertEqual(made, [], "狗在动：先等（出图要读回整块主画布）")
        busy[0] = False
        self.things.update(DT)
        self.assertEqual(len(made), 1)
        busy[0] = True
        self.win.set_thing("bed/blue", True)
        for _ in range(int(SHOT_WAIT_S / DT) - 2):
            self.things.update(DT)
        self.assertEqual(len(made), 1)
        for _ in range(4):
            self.things.update(DT)
        self.assertEqual(len(made), 2, "等不到就照出")

    def test_an_empty_picture_is_tried_again_next_frame(self):
        self.start_on_floor(x=140.0)
        self.fake_canvas()
        with mock.patch.object(things_mod.thing_art, "shoot", lambda *a: QImage()):
            self.win.set_thing("bowl/food", True)
            self.things.update(DT)
            t = self.things.items["bowl/food"]
            self.assertTrue(t.need_shot)
            self.assertIsNone(t.shot)
        self.fake_canvas()
        self.things.update(DT)
        self.assertIsNotNone(t.shot)


@unittest.skipUnless((config.ROOT / "models" / "props" / "bed_1.glb").is_file(), "买来的物件模型不在（models/props/，不入 git）")
class RealListTests(RoomCase):
    """真的包（买来的模型在）：「物件」页只列狗窝四款、狗屋两款、饭盆、水盆；别的包还在仓库里，不列、摆不出来。"""
    PACK = COLLIE

    def test_only_the_eight_styles_with_a_use_are_offered(self):
        keys = [t.key for t in self.win.things_available()]
        self.assertEqual(keys, ["bed/blue", "bed/grey", "bed/paws", "bed/orange", "doghouse/gable", "doghouse/flat", "food_bowl/bowl", "water_bowl/bowl",
                                "ball/red"], "小球也是一件道具，在「玩具」那一组")
        known = {t.key for t in packs.things()}
        for gone in ("bench/bench", "seesaw/seesaw", "bridge/bridge", "barrier/low", "barrier/mid", "barrier/high",
                     "park/a_frame", "park/poles", "park/tire", "park/fence", "park/bin"):
            self.assertIn(gone, known, "包和模型还留着")
            self.assertNotIn(gone, keys, "不列")
            self.win.set_thing(gone, True)
        self.assertEqual((self.pg.things.count(), self.pg.things.items), (0, {}), "也摆不出来")
        self.assertEqual(self.win.things_placed(), 1, "拿出来的小球算一件")
        self.win.set_ball_out(False)
        self.assertEqual(self.win.things_placed(), 0)
        self.win.set_ball_out(True)
        card = self.attach_card()
        self.assertEqual(list(card.things_page.group_labels), ["rest", "food", "toys"], "公园那一组是空的：不显示")
        self.assertEqual(list(card.things_page.tiles), keys)


class ThingsCardTests(PanelCase):
    """设置卡片：灵动交互的选项下面多一行「物件」，点 › 进「物件」页。"""
    DYNAMIC = True
    FAKES = True

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.fakes = fake_styles(Path(folder.name)) if self.FAKES else []
        p = mock.patch.object(packs, "things", lambda found=None: list(self.fakes))
        p.start()
        self.addCleanup(p.stop)
        super().setUp()

    def open_options(self):
        s = self.settings
        s.show()
        s.finish_page_anim()
        if not s.play_collapse.is_open:
            s.play_options_btn.click()
        s.finish_page_anim()
        self.app.processEvents()
        return s

    def test_a_things_row_sits_under_the_play_options_and_opens_with_them(self):
        from PySide6.QtWidgets import QLabel
        from widget.widgets import MotionButton
        s, w = self.settings, self.win
        s.show()
        row_block = s.things_collapse
        self.assertIsNotNone(row_block)
        page = s.main_page.layout()
        self.assertEqual(page.indexOf(row_block), page.indexOf(s.play_collapse) + 1, "紧跟在子选项那一块后面")
        self.assertLess(page.indexOf(row_block), page.indexOf(s.posture_collapse))
        self.assertFalse(row_block.is_open, "默认和子选项一起收着")
        closed = s.height()
        self.open_options()
        self.assertTrue(row_block.is_open)
        row = row_block.content.layout().itemAt(0).widget()
        self.assertEqual(row.findChild(QLabel).text(), "Things")
        self.assertEqual(row_block.content.layout().contentsMargins().left(), 18, "和子选项一样缩进")
        self.assertIsInstance(s.things_open, MotionButton)
        self.assertEqual(s.things_open.symbol, "forward")
        self.assertTrue(s.things_open.isVisibleTo(s))
        last = s.play_switches["hop_windows"]
        self.assertGreater(s.things_open.mapTo(s, QPoint(0, 0)).y(), last.mapTo(s, QPoint(0, 0)).y(), "在最后一条子选项下面")
        self.assertLessEqual(abs(s.things_open.mapTo(s, QPoint(s.things_open.width(), 0)).x() - last.mapTo(s, QPoint(last.width(), 0)).x()), 2, "› 和开关右边对齐")
        gap = s.things_open.mapTo(s, QPoint(0, 0)).y() - (last.mapTo(s, QPoint(0, 0)).y() + last.height())
        self.assertEqual(gap, 6, "行距和子选项之间一样，看上去是连着的一组")
        self.assertGreater(s.height(), closed + 2 * last.height() - 1, "卡片再长一行（一条开关 + 物件）")
        self.assertEqual(s.things_count.text(), "", "一件没摆不写（这里的假包里没有小球）")
        w.set_thing("bowl/food", True)
        w.set_thing("bed/blue", True)
        s.sync()
        self.assertEqual(s.things_count.text(), "2", "摆着几件写在 › 左边")
        s.play_options_btn.click()
        s.finish_page_anim()
        self.app.processEvents()
        self.assertFalse(row_block.is_open)
        self.assertEqual(s.height(), closed, "一起收起，回到原来的高度")

    def test_the_arrow_opens_the_things_page_and_back_keeps_the_options_open(self):
        s = self.open_options()
        s.things_open.click()
        s.finish_page_anim()
        self.assertEqual(s.page, "things")
        self.assertEqual(s.pages["things"].title_text(), "Things")
        self.assertEqual(s._back_target(), "main")
        self.assertFalse(s.strip.isVisibleTo(s), "「我的同桌」那一条不在这一页")
        self.assertTrue(s.things_page.isVisibleTo(s))
        s.show_page("main")
        s.finish_page_anim()
        self.assertTrue(s.play_collapse.is_open and s.things_collapse.is_open, "回来选项还展开着")
        self.assertTrue(self.win.play_options_open)

    def test_tiles_are_grouped_and_a_click_puts_the_thing_out_or_away(self):
        from widget import sounds
        from widget.things_page import COLUMNS, TILE_H, TILE_W, ThingTile
        s, w = self.open_options(), self.win
        s.show_page("things")
        s.finish_page_anim()
        page = s.things_page
        self.assertEqual(list(page.tiles), ["bed/blue", "house/gable", "house/long", "house/broken", "bowl/food"])
        self.assertEqual([(g, lab.text()) for g, lab in page.group_labels.items()],
                         [("rest", "Beds & houses"), ("food", "Food & water")], "只列有东西的组：公园那一组空了（长椅、栏不列），玩具还没接")
        tile = page.tiles["bowl/food"]
        self.assertIsInstance(tile, ThingTile)
        self.assertEqual((tile.width(), tile.height(), COLUMNS), (TILE_W, TILE_H, 3))
        self.assertEqual(tile.accessibleName(), "Food")
        self.assertLessEqual(3 * TILE_W + 2 * 6 + 8, page.scroll.width(), "三列放得下（右边给滚动条留 8）")
        self.assertFalse(tile.on)
        self.assertFalse(page.put_away_button.isEnabled(), "一件没摆：「全部收起」按不了")
        played = []
        with mock.patch.object(sounds, "play", side_effect=lambda kind, *a, **k: played.append(kind)), \
                mock.patch.object(w, "set_thing", wraps=w.set_thing) as set_thing:
            tile.click()
            set_thing.assert_called_once_with("bowl/food", True)
            self.assertTrue(tile.on)
            self.assertTrue(w.thing_on("bowl/food"))
            self.assertEqual(played[-1], "switch-on", "响开关的声音")
            self.assertTrue(page.put_away_button.isEnabled())
            tile.click()
            set_thing.assert_called_with("bowl/food", False)
            self.assertFalse(tile.on)
            self.assertEqual(played[-1], "switch-off")
        tile.click()
        page.tiles["bed/blue"].click()
        w.set_thing("bowl/food", False)                         # 右键物件的胶囊把它收了
        s.sync()
        self.assertFalse(tile.on, "每 0.3 秒跟着卡片对一遍")
        self.assertTrue(page.tiles["bed/blue"].on)
        self.assertEqual(page.put_away_button.text(), "Put everything away")
        with mock.patch.object(w, "put_things_away", wraps=w.put_things_away) as away:
            page.put_away_button.click()
            away.assert_called_once()
        self.assertEqual([k for k, t in page.tiles.items() if t.on], [])
        self.assertEqual(w.things_placed(), 0)
        img = tile.grab()                                       # 画得出来（没有缩略图的只写名字）
        self.assertEqual((img.width() / img.devicePixelRatio(), img.height() / img.devicePixelRatio()), (TILE_W, TILE_H))

    def test_chinese_labels(self):
        from widget import i18n
        for en, zh in (("Things", "物件"), ("Beds & houses", "窝"), ("Food & water", "吃喝"), ("Toys", "玩具"), ("Park", "公园"),
                       ("Put everything away", "全部收起")):
            self.assertEqual(i18n.ZH[en], zh)
        self.win.set_language("zh")
        s = self.win.settings_panel
        self.addCleanup(s.hide)
        self.assertEqual(s.pages["things"].title_text(), "物件")
        self.assertEqual(s.things_page.group_labels["rest"].text(), "窝")
        self.assertEqual(s.things_page.tiles["bed/blue"].accessibleName(), "假blue", "款的名字写在包里")

    def test_turning_dynamic_off_leaves_the_page(self):
        s = self.open_options()
        s.show_page("things")
        s.finish_page_anim()
        self.win.set_dynamic(False)
        s.sync()
        s.finish_page_anim()
        self.assertEqual(s.page, "main", "入口没了：回主页面")


class NoThingsCardTests(ThingsCardTests):
    """能摆的款一款都没有（新 clone 下来、买来的模型不在）：没有那一行、没有那一页，别的照旧。"""
    FAKES = False

    def test_a_things_row_sits_under_the_play_options_and_opens_with_them(self):
        s = self.settings
        self.assertEqual(self.win.things_available(), [])
        self.assertIsNone(s.things_collapse)
        self.assertIsNone(s.things_page)
        self.assertNotIn("things", s.pages)
        self.assertFalse(hasattr(s, "things_open"))
        closed = s.height() if s.isVisible() else None
        self.open_options()
        page = s.main_page.layout()
        self.assertEqual(page.indexOf(s.posture_collapse), page.indexOf(s.play_collapse) + 1, "子选项后面紧跟动作那一块，和以前一样")
        s.sync()
        s.play_options_btn.click()
        s.finish_page_anim()
        self.assertFalse(s.play_collapse.is_open)
        self.assertIsNone(closed)

    def test_the_arrow_opens_the_things_page_and_back_keeps_the_options_open(self):
        self.win.set_thing("bowl/food", True)                   # 记着也没用：没有这一款
        self.assertEqual((self.win.thing_on("bowl/food"), self.win.things_placed()), (False, 0))
        self.assertNotIn("things", self.win.settings.values)

    test_tiles_are_grouped_and_a_click_puts_the_thing_out_or_away = None
    test_chinese_labels = None
    test_turning_dynamic_off_leaves_the_page = None


if __name__ == "__main__":
    unittest.main()
