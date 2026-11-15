"""看细节（widget/closeup.py）：详情页、自定义毛色页最上面那一块；狗站在转台上（一进来先站起来，转盘转它、
站 / 坐 / 趴换它的姿势，离开转回来、回到进来前的姿势），放大以脚下的根为中心、只是画得大、上限和主页面「大小」一样跟着屏走。
窗口那几条按真的 window._tick 一帧帧推（时钟换成假的、每帧 1/60 秒），数 setGeometry：放大只在开始、收完时摆窗口。
控制器那几条用一只单独的 DogController（不开窗口）。offscreen 平台一块 800 × 800 的屏（大小上限 400%），狗默认在右下，设置卡片摆在它左上。"""
import math
import unittest
from pathlib import Path
from unittest import mock

import config
from tests.panel_base import PanelCase

DT = 1 / 60


def wrap(d: float) -> float:
    return (d + 180.0) % 360.0 - 180.0


def dog_actions():
    from widget.clips import ACTIONS_BY_ID
    return list(ACTIONS_BY_ID.values())


class Driven:
    """按窗口的每一帧推：真的 win._tick()，perf_counter 换成每帧走 DT 的假钟。"""

    def drive_setup(self):
        w = self.win
        w._anim_timer.stop()
        self.now = 5000.0
        w._last_tick = self.now

    def tick(self, seconds=DT, until=None, each=None):
        """推 seconds 秒；until 说停就停（返回用了几秒），each 每帧调一次。"""
        import widget.window as window_module
        for i in range(max(1, round(seconds / DT))):
            self.now += DT
            with mock.patch.object(window_module.time, "perf_counter", return_value=self.now):
                self.win._tick()
            if each is not None:
                each()
            if until is not None and until():
                return (i + 1) * DT
        return None


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class CloseupTests(Driven, PanelCase):
    def setUp(self):
        super().setUp()
        self.drive_setup()
        self.win.dog.rng.seed(3)
        self.win.place_initially()
        self.win.show()
        self.assertIsNotNone(self.tick(6.0, lambda: self.win.dog.posture == "lying" and not self.win.dog.transition), "先趴好")
        self.tick(2.0)                                           # 窗口按趴着的高度缩回来（SHRINK_DELAY）
        self.sc = self.win.closeup

    def open_page(self, page="pet", card=True):
        s = self.settings
        if card and not s.isVisible():
            s.toggle_near(self.win)
        s.show_page(page, animated=False)
        s.finish_page_anim()
        self.tick(DT)

    def leave(self, how="back"):
        s = self.settings
        if how == "close":
            s.hide()
        else:
            s.show_page("main", animated=False)
            s.finish_page_anim()

    def geometry_calls(self):
        return self.enterContext(mock.patch.object(self.win, "setGeometry", wraps=self.win.setGeometry))

    def body_box(self):
        """狗现在画出来的身子占的地方（任何朝向，window.BODY_HALF_M），全局坐标。"""
        from widget.window import BODY_HALF_M
        w = self.win
        x, y = w.scene_world()
        half, top = BODY_HALF_M * w.ppm, w.dog.stance_top() * w.ppm
        return x - half, y - top, x + half, y

    def settle(self, posture="standing", seconds=4.0):
        """等它换到 posture、过渡片段播完。"""
        dog = self.win.dog
        return self.tick(seconds, lambda: dog.posture == posture and not dog.transition and not dog.steps)

    def root_kept(self, base, where=""):
        """每帧看一眼：狗脚下的根还在 base（半个像素以内）。"""
        return lambda: self.assertLess(math.dist(self.win.scene_world(), base), 0.5, f"根不动 {where}")

    # ---- 那一行、转台 ----
    def test_only_the_two_coat_pages_have_the_row_and_the_turntable(self):
        from widget.closeup import DetailRow
        s, w = self.settings, self.win
        self.assertEqual({n for n, e in s.pages.items() if e.closeup}, {"pet", "coat"})

        def first_widget(page):
            lay = page.layout()
            return next(lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget() is not None)
        self.assertIsInstance(first_widget(s.pet_page), DetailRow, "详情页：毛色上面")
        self.assertIsInstance(first_widget(s.coat_page), DetailRow, "自定义毛色页：最上面")
        self.assertIsNot(s.pet_detail, s.coat_page.detail, "两页各一个（换页时两页交叉淡入淡出）")
        self.assertIn(s.pet_detail.zoom.accessibleName(), ("Zoom",))
        self.assertFalse(w.dog.on_turntable)
        self.open_page("pet")
        self.assertTrue(w.dog.on_turntable)
        s.pet_detail.ruler._turn(45.0)
        angle = self.sc.angle
        s.show_page("coat", animated=False)
        s.finish_page_anim()
        self.tick(0.2)
        self.assertTrue(w.dog.on_turntable, "详情页 ↔ 自定义页来回，狗一直站在转台上")
        self.assertEqual(self.sc.angle, angle, "转盘转到的角度留着")
        self.assertEqual(s.coat_page.detail.ruler.angle, angle, "这一页的转盘尺照着画")
        for page in ("main", "advanced", "add"):
            s.show_page("pet", animated=False)
            self.tick(0.1)
            s.show_page(page, animated=False)
            self.assertFalse(self.sc.open)
            self.assertIsNotNone(self.tick(2.0, lambda: not w.dog.on_turntable), f"{page}：转回来就下转台")

    def test_on_the_turntable_the_dog_does_nothing_by_itself_and_turns_with_the_ruler(self):
        """转盘往右转 90°：狗靠近你的那面往右（朝向 +90），0.5 秒内到；之后一直停在那（不来随机动作、不跟鼠标、换边不转身、头摆正）。
        每块屏的窗口画的是同一个姿势（window._pose 的根就是控制器这一帧的）。"""
        w, s = self.win, self.settings
        self.open_page("pet")
        dog = w.dog
        yaw0 = dog.yaw
        s.pet_detail.ruler._turn(90.0)
        self.assertIsNotNone(self.tick(0.6, lambda: abs(wrap(dog.yaw - (yaw0 + 90.0))) < 0.5), "跟上去了")
        self.assertEqual(w._pose.root, dog.root_matrix(), "画的就是转到的角度")
        dog.set_home_yaw((dog.home_yaw + 120.0) % 360.0)
        dog.set_look_target((5.0, 0.5, 2.0))
        self.tick(30.0, each=lambda: self.assertTrue(dog.run is None and dog.turn is None, "不来随机动作、不转身"))
        self.assertLess(abs(wrap(dog.yaw - (yaw0 + 90.0))) , 0.01, "一直停在转到的地方")
        self.assertFalse(any(type(st).__name__ in ("TurnStep", "ActionStep") for st in dog.steps))
        self.assertLess(dog._head_free, 0.01, "头不看鼠标（摆正，看得清头和脖子的毛色）")

    def test_leaving_or_closing_turns_it_back_without_overshoot(self):
        """离开、关卡片：走近的那边转回该朝的方向（window._home_yaw），一路单调、不过头；差不到 1° 才放下来，随机动作重新计时。
        刚甩完转盘还在往外转就离开：往外的那点速度不要（不先往外冲一段再回来）。"""
        w, s = self.win, self.settings
        dog = w.dog
        for how, settle in (("back", 0.8), ("close", 0.8), ("back", 0.03)):
            self.open_page("pet")
            s.pet_detail.ruler._turn(150.0)
            self.tick(settle)
            home = w._home_yaw()
            gaps = []
            self.leave(how)
            used = self.tick(1.5, lambda: not dog.on_turntable, each=lambda: gaps.append(abs(wrap(dog.yaw - home))))
            self.assertIsNotNone(used, how)
            self.assertTrue(all(b <= a + 1e-6 for a, b in zip(gaps, gaps[1:])), f"{how}：一路往回转，不回弹 {gaps[:6]}")
            self.assertLess(gaps[-1], 1.0)
            self.tick(0.4)
            self.assertLess(abs(wrap(dog.yaw - home)), 0.05, "剩下那一点滑完")
            self.assertTrue(math.isfinite(dog.action_at) and dog.action_at > dog.t, "随机动作重新计时")

    def test_coming_back_on_the_way_home_stops_where_it_is(self):
        """转回去的路上又回到这一页：就近停住，不倒回来；转盘尺从停的地方接着转。"""
        w, s = self.win, self.settings
        dog = w.dog
        self.open_page("pet")
        s.pet_detail.ruler._turn(160.0)
        self.tick(0.8)
        self.leave()
        self.tick(0.12)
        self.open_page("pet")
        yaws = []
        self.tick(1.0, each=lambda: yaws.append(dog.yaw))
        steps = [wrap(b - a) for a, b in zip(yaws, yaws[1:])]
        self.assertTrue(all(d <= 1e-6 for d in steps) or all(d >= -1e-6 for d in steps), "只往一个方向慢下来，不倒回来")
        self.assertLess(abs(steps[-1]), 1e-3, "停住了")
        self.assertTrue(dog.on_turntable)
        self.assertLess(abs(wrap(self.sc.angle - dog.yaw)), 0.05, "转盘尺画在停的地方")

    def test_entering_stands_it_up_whatever_it_was_doing_and_leaving_puts_it_back(self):
        """不管在做什么，一进这一页狗就站着（趴着、坐着、睡着、正做着随机动作都一样）；离开回到进来前的姿势（选的那个，
        睡的用原来那种睡法）。那一排亮「站」。"""
        w, s = self.win, self.settings
        dog = w.dog
        for posture in ("lying", "sitting", "sleeping"):
            w.set_rest_posture(posture)
            self.assertIsNotNone(self.settle(posture, 8.0), posture)
            style = dog.sleep_style
            if posture == "lying":
                dog._start_action(next(a for a in dog_actions() if a.posture == "lying"))   # 正做着自己来的动作
            self.open_page("pet")
            self.assertIsNone(dog.run, "动作一刀切")
            self.assertIsNotNone(self.settle("standing", 6.0), f"{posture}：站起来")
            self.assertEqual(self.sc.posture, "standing")
            s.pet_detail.sync()
            self.assertTrue(s.pet_detail.pose_buttons["standing"].isChecked(), "那一排亮「站」")
            self.assertEqual(w.rest_posture, posture, "选的姿势不变")
            self.leave()
            self.assertIsNotNone(self.tick(3.0, lambda: not dog.on_turntable), posture)
            self.assertIsNotNone(self.settle(posture, 8.0), f"{posture}：离开回到进来前的姿势")
            if posture == "sleeping":
                self.assertEqual(dog.sleep_style, style, "睡回原来那种睡法")

    def test_the_three_buttons_each_change_the_posture_once_only_for_this_page(self):
        """下面一排站 / 坐 / 趴：点一下换一次姿势（亮那一颗）；只是这一页里摆给你看——选的姿势、存下来的都不变，离开回到进来前的。"""
        w, s = self.win, self.settings
        dog = w.dog
        self.open_page("pet")
        self.assertIsNotNone(self.settle("standing"))
        row = s.pet_detail
        self.assertEqual([b.text() for b in row.pose_buttons.values()], ["Stand", "Sit", "Lie"])
        for posture in ("sitting", "lying", "standing", "lying"):
            row.pose_buttons[posture].click()
            self.assertIsNotNone(self.settle(posture), posture)
            self.assertEqual(self.sc.posture, posture)
            row.sync()
            self.assertEqual([p for p, b in row.pose_buttons.items() if b.isChecked()], [posture])
            self.assertEqual((w.rest_posture, w.prefs.get("rest_posture")), ("lying", "lying"), "选的、存下来的姿势不变")
        row.pose_buttons["sitting"].click()
        self.tick(0.3)
        self.assertTrue(dog.transition, "正坐下去")
        self.leave()
        self.assertIsNotNone(self.tick(3.0, lambda: not dog.on_turntable))
        self.assertIsNotNone(self.settle("lying", 6.0), "离开：回到趴着")

    def test_the_posture_strip_on_the_turntable_is_the_real_posture(self):
        """在这一页从狗头顶「···」旁边的姿势条选的是它真的姿势（存下来）：转台上照样换过去、那一排跟着亮，离开就待在那。"""
        w, s = self.win, self.settings
        dog = w.dog
        self.open_page("pet")
        self.assertIsNotNone(self.settle("standing"))
        w.set_rest_posture("sitting")
        self.assertIsNotNone(self.settle("sitting"))
        self.assertEqual(w.prefs.get("rest_posture"), "sitting")
        s.pet_detail.sync()
        self.assertTrue(s.pet_detail.pose_buttons["sitting"].isChecked())
        w.set_rest_posture("sleeping")
        self.assertIsNotNone(self.settle("sleeping", 6.0))
        s.pet_detail.sync()
        self.assertFalse(any(b.isChecked() for b in s.pet_detail.pose_buttons.values()), "睡：一颗都不亮")
        self.leave()
        self.assertIsNotNone(self.tick(3.0, lambda: not dog.on_turntable))
        self.tick(2.0)
        self.assertEqual((dog.posture, dog.transition), ("sleeping", False), "离开就待在那")

    def test_a_dial_action_right_after_leaving_still_runs(self):
        """离开以后狗还在转回去（不到一秒），这时点表盘的动作照做（只挡狗自己来的）。"""
        w, s = self.win, self.settings
        dog = w.dog
        self.open_page("pet")
        s.pet_detail.ruler._turn(150.0)
        self.tick(0.6)
        self.leave()
        self.tick(0.1)
        self.assertTrue(dog.on_turntable)
        w.do_action("look_up")
        self.assertIsNotNone(self.tick(3.0, lambda: dog.action is not None and dog.action.id == "look_up"), "照做")
        self.assertIsNotNone(self.tick(20.0, lambda: not dog.on_turntable and dog.run is None), "做完转回来、放下")

    # ---- 放大 ----
    def test_the_zoom_goes_up_to_the_size_cap_around_the_root_and_is_never_saved(self):
        """放大到最右是主页面「大小」的上限（这块 800 高的屏 400%，存下来 100% 就是 4 倍），只是画得大：存下来的大小、位置、大小滑杆都不变。
        以脚下的根为中心：放大、缩回的一路上根都不动（靠屏幕右边也不往里挪，出了屏幕的那截看不见）。窗口开始时摆一次（四条边都动：分两步）、
        收完摆一次，中间每帧只改画多大画在哪。"""
        w, s = self.win, self.settings
        self.open_page("pet", card=False)
        self.assertIsNotNone(self.settle("standing"))
        self.tick(2.0)                                           # 站起来窗口长高那一下走完
        base, geo0 = w.scene_world(), w.geometry()
        saved = {k: w.prefs.get(k) for k in ("scale", "pos_fx", "pos_fb", "pos_screen")}
        self.assertEqual(w.scale_range()[1], 400)
        self.assertAlmostEqual(self.sc.max_level(), 4.0, places=6)
        calls = self.geometry_calls()
        self.assertTrue(self.sc.can_zoom())
        self.sc.set_zoom(True)
        boxes = []
        each = self.root_kept(base, "放大")
        self.tick(0.5, each=lambda: (each(), boxes.append(self.body_box())))
        started = calls.call_count
        self.assertLessEqual(started, 2, "开始时摆一次（分两步）")
        self.tick(1.0, each=each)
        self.assertAlmostEqual(w.scale, 4.0, places=3)
        self.assertEqual(w.world_scale, 1.0)
        self.assertEqual(calls.call_count, started, "之后不挪不改大小")
        self.assertGreater(max(b[2] for b in boxes), 800.0, "靠右边：不往里挪，出了屏幕的那截看不见")
        self.assertEqual({k: w.prefs.get(k) for k in saved}, saved, "不存大小、不记位置")
        s._sync_size()
        self.assertEqual(s.size_slider.value, 100.0, "大小滑杆照旧是存下来的大小")
        self.sc.set_zoom(False)
        self.assertIsNotNone(self.tick(1.5, lambda: not w.showing_scaled, each=self.root_kept(base, "缩回")), "缩回去了")
        self.tick(0.3)
        self.assertLessEqual(calls.call_count - started, 2, "收完摆回去一次（分两步）")
        self.assertEqual(w.scale, 1.0)
        self.assertEqual(w.geometry(), geo0)
        self.assertLess(math.dist(w.scene_world(), base), 0.5)
        self.assertEqual({k: w.prefs.get(k) for k in saved}, saved)

    def test_the_cap_follows_the_screen_and_the_saved_size(self):
        """上限跟着狗在的那块屏走（window.scale_range），按放大的狗算：存下来的越小能放的倍数越多；大小快到上限（放不到 1.1 倍）就灰掉、按了也弹回来。"""
        import widget.window as window_module
        w, s = self.win, self.settings
        self.open_page("pet")
        self.assertAlmostEqual(self.sc.max_level(), 4.0, places=6)
        with mock.patch.object(window_module.CompanionWindow, "scale_range", lambda self, screen=None: (30, 560)):
            self.assertAlmostEqual(self.sc.max_level(), 5.6, places=6, msg="更高的屏：上限跟着变")
            s.pet_detail.sync()
            self.assertAlmostEqual(s.pet_detail.zoom.hi, 560.0, places=3)
            self.assertAlmostEqual(s.pet_detail.percent.hi, 560.0, places=3)
        w.set_scale(0.5)
        self.assertAlmostEqual(self.sc.max_level(), 8.0, places=6, msg="存下来 50%：能放 8 倍（放大的狗一样到 400%）")
        w.set_scale(3.8)
        self.assertLess(self.sc.max_level(), 1.1)
        self.assertFalse(self.sc.can_zoom())
        s.pet_detail.sync()
        self.assertFalse(s.pet_detail.zoom.isEnabled(), "灰掉")
        self.assertFalse(s.pet_detail.percent.isEnabled())
        self.sc.set_zoom(True)
        self.assertFalse(self.sc.zoom_on, "按了也弹回来")

    def test_the_zoomed_dog_covers_the_card_and_nothing_moves(self):
        """放大的狗挡到卡片就让它挡（用户自己会挪开），不横着躲、不少放大；卡片也不动。放大着把卡片拖到狗身上、松手，狗也不动、窗口不重摆。
        狗的窗口一直在卡片上面一层：狗在菜单栏上面的那几层（native.set_level，LEVEL_DOG），卡片是普通的置顶小窗口。"""
        from PySide6.QtCore import QRectF
        from widget import native
        from widget.sticker import SHADOW
        w, s = self.win, self.settings
        raised = []
        with mock.patch.object(native, "set_level", side_effect=lambda win, level: raised.append((win, level)) or True):
            w.hide()
            w.show()
            self.open_page("pet")
        self.assertIn((w, native.LEVEL_DOG), raised, "狗的窗口每次显示都放到菜单栏上面那几层")
        self.assertNotIn(s, [win for win, _ in raised], "卡片是普通的置顶小窗口：狗一直盖在卡片上面")
        self.assertIsNotNone(self.settle("standing"))
        card = QRectF(s.frameGeometry()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)
        card_pos, base = s.pos(), w.scene_world()
        self.sc.set_zoom(True)
        self.tick(1.5, each=self.root_kept(base))
        self.assertAlmostEqual(w.scale, 4.0, places=3, msg="不为躲卡片少放大")
        x0, y0, x1, y1 = self.body_box()
        self.assertTrue(card.intersects(QRectF(x0, y0, x1 - x0, y1 - y0)), "盖在卡片上")
        self.assertEqual(s.pos(), card_pos, "卡片不动")
        calls = self.geometry_calls()
        for dx in (-200, -100):
            s.move(round(base[0]) + dx, round(base[1]) - 220)     # 卡片拖到狗身上
            self.tick(0.3, each=self.root_kept(base, "拖着卡片"))
        self.tick(1.2, each=self.root_kept(base, "松了手"))
        self.assertEqual(calls.call_count, 0, "窗口不重摆")
        self.assertAlmostEqual(w.scale, 4.0, places=3)

    def test_turning_or_changing_posture_while_zoomed_keeps_the_size_and_the_root(self):
        """转圈不影响大小、大小变化不位移——放大着转转盘、换站 / 坐 / 趴：放大的倍数、根都不变，窗口不重摆；
        拖滑块变大变小也是绕着根。"""
        w, s = self.win, self.settings
        self.open_page("pet")
        self.assertIsNotNone(self.settle("standing"))
        base = w.scene_world()
        row = s.pet_detail
        row.zoom.adjustmentStarted.emit()
        row.zoom._apply(250.0)
        row.zoom.adjustmentFinished.emit()
        self.tick(1.0, each=self.root_kept(base, "放大到 250%"))
        self.assertAlmostEqual(w.scale, 2.5, places=3)
        calls = self.geometry_calls()

        def same():
            self.assertAlmostEqual(w.scale, 2.5, places=6, msg="大小不变")
            self.root_kept(base, "转、换姿势")()
        for turn in (90.0, 120.0, -300.0):
            row.ruler._turn(turn)
            self.tick(0.5, each=same)
        for posture in ("lying", "sitting", "standing"):
            row.pose_buttons[posture].click()
            self.tick(3.0, each=same)
            self.assertEqual(w.dog.posture, posture)
        self.assertEqual(calls.call_count, 0, "窗口不挪不改大小（开始时按上限、站着的高度摆过）")
        row.zoom.adjustmentStarted.emit()
        row.zoom._apply(140.0)
        row.zoom.adjustmentFinished.emit()
        self.tick(1.0, each=self.root_kept(base, "缩小到 140%"))
        self.assertAlmostEqual(w.scale, 1.4, places=3)

    def test_the_percentage_and_the_reset_work_like_the_size_row(self):
        """和主页面「大小」那一行一样：百分比左右拖精调、单击原位输入（夹在 100% 和上限之间），和滑块互相跟着；长按重置回到 100%（不放大）。"""
        w, s = self.win, self.settings
        self.open_page("pet")
        row = s.pet_detail
        row.sync()
        pct = row.percent
        self.assertEqual((pct.lo, pct.hi), (100.0, 400.0))
        self.assertEqual(pct.text(), "100%")
        pct._begin()
        pct._apply(180.0)
        pct._finish()
        self.assertAlmostEqual(self.sc.level, 1.8)
        self.assertAlmostEqual(row.zoom.value, 180.0, msg="滑块跟着")
        self.tick(1.0)
        self.assertAlmostEqual(w.scale, 1.8, places=3)
        pct.start_edit()
        pct.editor.setText("320")
        pct.editor.setModified(True)
        pct._commit_text()
        self.assertAlmostEqual(self.sc.level, 3.2, msg="输入 320")
        pct.start_edit()
        pct.editor.setText("900")
        pct.editor.setModified(True)
        pct._commit_text()
        self.assertAlmostEqual(self.sc.level, 3.2, msg="超过上限的不收")
        row.zoom._apply(260.0)
        self.assertAlmostEqual(pct.value, 260.0, msg="百分比跟着滑块")
        self.tick(1.0)
        self.assertEqual(row.reset.accessibleDescription(), "Hold to go back to 100%")
        row.reset.held.emit()
        self.assertFalse(self.sc.zoom_on)
        self.assertEqual((row.zoom.value, pct.value), (100.0, 100.0))
        self.assertIsNotNone(self.tick(1.5, lambda: not w.showing_scaled), "长按重置：缩回 100%")
        self.assertEqual(w.scale, w.world_scale)

    def test_after_a_zoom_a_standing_dog_is_kept_on_screen(self):
        """灵动交互关着：狗贴着屏幕顶趴着，进来站起来时头出去了就往下挪进来（平时换姿势就这样）；放大着根不动，缩回来以后也还在屏幕里。"""
        from widget.clips import POSTURE_PLANS
        w = self.win
        dog = w.dog
        stand = max(dog.clip_top(c) for c in POSTURE_PLANS["standing"].loop)
        y0 = stand * config.PIXELS_PER_METER - 20.0              # 趴着放得下；站起来头要出去 20 像素
        w.place_scene(400.0, y0)
        self.tick(0.1)
        self.open_page("pet", card=False)
        self.assertIsNotNone(self.settle("standing"))
        self.tick(0.5)
        self.assertGreaterEqual(w.scene_world()[1] - stand * w.ppm, -0.5, "站起来：头夹回屏幕里")
        base = w.scene_world()
        self.sc.set_zoom(True)
        self.tick(1.0, each=self.root_kept(base, "放大"))
        self.leave()
        self.assertIsNotNone(self.tick(2.0, lambda: not w.showing_scaled, each=self.root_kept(base, "缩回")))
        self.assertIsNotNone(self.settle("lying"), "回到趴着")
        self.assertLess(math.dist(w.scene_world(), base), 0.5)

    def test_while_zoomed_the_wheel_and_pinch_keep_the_size_and_dragging_moves_the_dog(self):
        """放大着：滚轮、捏合不改存下来的大小。按住拖是挪狗：放大的狗跟着手、窗口不挪；拖到哪就是它真的位置——
        松手还放大着、记下来的位置是那，收回来还在那。"""
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent, QWheelEvent
        w = self.win
        self.open_page("pet", card=False)
        self.sc.set_zoom(True)
        self.tick(1.0)
        saved = w.prefs.get("scale")
        w.zoom(1.5)
        p = QPointF(w.width() / 2, w.height() / 2)
        w.wheelEvent(QWheelEvent(p, QPointF(w.mapToGlobal(p.toPoint())), QPoint(), QPoint(0, 240), Qt.NoButton, Qt.NoModifier,
                                 Qt.NoScrollPhase, False))
        self.assertEqual((w.world_scale, w.prefs.get("scale")), (1.0, saved), "滚轮、捏合不改存下来的大小")
        x, y = w.scene_world()
        g = QPointF(x, y - 60)

        def mouse(kind, d):
            types = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove, "release": QEvent.MouseButtonRelease}
            at = g + QPointF(d, 0)
            ev = QMouseEvent(types[kind], at - QPointF(w.pos()), at, Qt.LeftButton, Qt.NoButton if kind == "release" else Qt.LeftButton,
                             Qt.NoModifier)
            {"press": w.mousePressEvent, "move": w.mouseMoveEvent, "release": w.mouseReleaseEvent}[kind](ev)
        mouse("press", 0)
        calls = self.geometry_calls()
        for i in range(1, 7):
            mouse("move", -20.0 * i)
            self.tick(DT)
        self.assertTrue(w.dragging, "拖得动")
        self.assertAlmostEqual(w.scene_world()[0], x - 120.0, delta=0.6, msg="放大的狗跟着手")
        self.assertAlmostEqual(w.scene_world()[1], y, delta=0.6)
        self.assertLessEqual(calls.call_count, 1, "拖的时候窗口不跟着挪（拖出了放大时摆的那一块才往那边长一次）")
        moved = calls.call_count
        for _ in range(3):
            mouse("move", -120.0)
            self.tick(DT)
        self.assertEqual(calls.call_count, moved, "长过一次就不再动")
        mouse("release", -120.0)
        self.tick(0.6)
        self.assertAlmostEqual(w.scale, 4.0, places=3, msg="松手还放大着")
        self.assertAlmostEqual(w.dog_root()[0], x - 120.0, delta=0.6, msg="拖到的就是它真的位置")
        g = w.screen().availableGeometry()
        self.assertAlmostEqual(w.prefs.get("pos_fx"), (x - 120.0 - g.left()) / g.width(), delta=0.002, msg="记下来的位置是拖到的地方")
        self.sc.set_zoom(False)
        self.assertIsNotNone(self.tick(1.5, lambda: not w.showing_scaled))
        self.assertAlmostEqual(w.scene_world()[0], x - 120.0, delta=0.6, msg="收回来还在拖到的地方")
        self.assertEqual(w.world_scale, 1.0)

    def test_the_slider_controls_how_big_and_only_moves_the_window_once(self):
        """放大是一条滑块：最左 100%、最右放得下的最大；拖着狗跟着变，窗口只在开始时按最右摆一次，拖滑块每帧只改画多大；
        每过 10% tick 一声（界面音效）；放不下 1.1 倍时滑块灰掉。"""
        from widget import sounds
        w, s = self.win, self.settings
        self.open_page("pet", card=False)
        s.pet_detail.sync()
        slider = s.pet_detail.zoom
        self.assertTrue(slider.isEnabled())
        self.assertAlmostEqual(slider.lo, 100.0)
        self.assertAlmostEqual(slider.hi, 100.0 * self.sc.max_level(), places=3, msg="最右是放得下的最大")
        ticks = []
        self.enterContext(mock.patch.object(sounds, "_limited_tick", side_effect=lambda kind: ticks.append(kind)))
        self.enterContext(mock.patch.object(sounds, "_enabled", True))
        slider.adjustmentStarted.emit()
        slider._apply(150.0)
        self.tick(0.4)                                           # 开始那一下摆好（四条边都动分两步，第二步最多等 0.25 秒）
        calls = self.geometry_calls()
        start = calls.call_count
        for v in (160.0, 140.0, 130.0, 170.0, 150.0):
            slider._apply(v)
            self.tick(0.05)
        slider.adjustmentFinished.emit()
        self.assertGreaterEqual(len(ticks), 3, "过 10% 一格 tick 一声")
        self.tick(0.8)
        self.assertAlmostEqual(w.scale, 1.5, places=2, msg="停在滑块那")
        self.assertEqual(calls.call_count, start, "拖滑块不挪窗口、不改大小")
        slider._apply(100.0)
        self.assertIsNotNone(self.tick(1.5, lambda: not w.showing_scaled), "拖回最左：收回去")
        self.assertEqual(w.scale, 1.0)

    def test_with_reduce_motion_the_turn_and_the_zoom_are_instant(self):
        from widget import native
        w, s = self.win, self.settings
        dog = w.dog
        self.enterContext(mock.patch.object(native, "reduce_motion", return_value=True))
        self.open_page("pet", card=False)
        yaw0 = dog.yaw
        s.pet_detail.ruler._turn(90.0)
        self.sc.set_zoom(True)
        self.tick(DT)
        self.assertAlmostEqual(wrap(dog.yaw - yaw0), 90.0, places=3)
        self.assertAlmostEqual(w.scale, 4.0, places=6)
        self.leave()
        self.tick(2 * DT)
        self.assertFalse(w.showing_scaled)
        self.assertFalse(dog.on_turntable)
        self.assertLess(abs(wrap(dog.yaw - w._home_yaw())), 0.5)

    def test_changing_screens_or_the_size_snaps_the_zoom_back(self):
        w, s = self.win, self.settings
        self.open_page("pet", card=False)
        for change in (lambda: w._screens_changed(), lambda: w.set_scale(1.2), lambda: w.set_dynamic(True)):
            self.sc.set_zoom(True)
            self.tick(0.5)
            self.assertTrue(w.showing_scaled)
            k = w.world_scale
            change()
            self.assertFalse(w.showing_scaled, "当场收回")
            self.assertFalse(self.sc.zoom_on, "「放大」弹起来")
            self.assertEqual(w.scale, w.world_scale)
            self.assertLessEqual(abs(w.world_scale - k), 0.2 + 1e-9)
            if w.dynamic:
                w.set_dynamic(False)
            self.tick(0.2)

    def test_deleting_this_pet_from_its_page_puts_everything_back_at_once(self):
        """详情页里删了这只：先回主页面（狗开始转回去、缩回去），换到旁边那只时（狗看不见）当场还原：朝向正好是该朝的方向。"""
        w, s = self.win, self.settings
        w.add_pet("border_collie", "奶茶")
        self.tick(0.3)
        self.open_page("pet", card=False)
        s.pet_detail.ruler._turn(150.0)
        self.sc.set_zoom(True)
        self.tick(0.8)
        s._delete_pet()
        self.assertFalse(w.showing_scaled)
        self.assertFalse(w.dog.on_turntable)
        self.assertEqual(w.dog.yaw, w._home_yaw(), "当场转到该朝的方向")
        self.assertEqual(w.scale, w.world_scale)
        self.assertEqual((w.dog.posture, w.dog.transition, w.dog.steps), ("lying", False, []), "当场趴回去（看不见的时候，不播）")

    def test_rebuilding_the_card_keeps_the_dog_on_the_turntable(self):
        """换语言、外观时卡片整张重建：狗留在转台上，转盘的角度留着，新卡片的那一行照着画。"""
        w = self.win
        self.open_page("coat")
        w.settings_panel.coat_page.detail.ruler._turn(60.0)
        w.settings_panel.coat_page.detail.pose_buttons["sitting"].click()
        self.tick(0.3)
        angle = self.sc.angle
        w.set_language("zh")
        new = w.settings_panel
        self.assertIsNot(new, self.settings)
        self.assertEqual(new.page, "coat")
        self.tick(0.3)
        self.assertTrue(w.dog.on_turntable)
        self.assertEqual(self.sc.angle, angle)
        self.assertEqual(new.coat_page.detail.ruler.angle, angle)
        self.assertEqual(new.coat_page.detail.zoom.accessibleName(), "放大")
        self.assertEqual(self.sc.posture, "sitting")
        new.coat_page.detail.sync()
        self.assertTrue(new.coat_page.detail.pose_buttons["sitting"].isChecked(), "新卡片的那一排照着亮")
        self.assertEqual(new.coat_page.detail.pose_buttons["sitting"].text(), "坐")
        self.assertEqual(new.coat_page.detail.reset.accessibleDescription(), "长按回到 100%")
        new.hide()
        self.assertIsNotNone(self.tick(2.0, lambda: not w.dog.on_turntable), "关了新卡片：转回来、放下")


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class DynamicCloseupTests(Driven, PanelCase):
    """灵动交互开着：进这两页先临时退出灵动交互（window.pause_play：球、圈、物件收起，狗能随便拖，开关不变不存），离开回来；
    在空中的先落地再退；上了转台不捡球、不俯身；放大时空间和球照旧按存下来的大小。"""
    DYNAMIC = True

    def setUp(self):
        from widget import native
        from PySide6.QtWidgets import QApplication
        self.frames = {}
        for p in (mock.patch.object(native, "window_frames", lambda pid: [(n, 99, *f) for n, f in self.frames.items()]),
                  mock.patch.object(native, "window_frame", lambda n: self.frames.get(n)),
                  mock.patch.object(native, "window_covered", lambda n, x, y, pid: False if n in self.frames else None)):
            p.start()
            self.addCleanup(p.stop)
        super().setUp()
        self.drive_setup()
        w = self.win
        w.dog.rng.seed(5)
        self.pg, self.sc = w.playground, w.closeup
        ag = QApplication.primaryScreen().availableGeometry()
        self.floor_y = ag.y() + ag.height() - 18.0 * w.world_scale
        w.show()
        w.place_scene(560.0, self.floor_y)
        w.dog.snap_home(210.0)
        self.pg.start()
        self.pg._frames_at = -math.inf
        self.cursor = (ag.x() + 200.0, self.floor_y - 150.0)
        p = mock.patch.object(self.pg, "cursor", lambda: self.cursor)
        p.start()
        self.addCleanup(p.stop)
        self.tick(0.5)

    def tearDown(self):
        if self.pg.ball_win is not None:
            self.pg.ball_win.hide()
        for rw in self.pg.ring_wins.values():
            rw.hide()
        super().tearDown()

    def open_page(self):
        self.settings.show_page("pet", animated=False)
        self.tick(DT)

    def finish_fades(self):
        """球、物件的淡入淡出是 Qt 自己的动画（tick 推不动）：直接放到头。"""
        for anim in (self.pg._ball_fade, self.pg.things._fade):
            if anim.state() == anim.State.Running:
                anim.setCurrentTime(anim.duration())

    def throw(self, ready=True):
        """拿起球往左甩出去（ready：当作球已经在圈里停够了）。"""
        from PySide6.QtCore import QPointF
        import time as _t
        pg, b = self.pg, self.pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        t0 = _t.perf_counter()
        with mock.patch("widget.playground.time.perf_counter", side_effect=[t0 + 0.30, t0 + 0.33, t0 + 0.36, t0 + 0.36, t0 + 0.36]):
            pg.ball_drag(QPointF(b.x - 30, b.y - 20))
            if ready:
                pg.ring.ready = True
            pg.ball_drag(QPointF(b.x - 70, b.y - 45))
            pg.ball_release(QPointF(b.x - 70, b.y - 45))

    def test_on_the_turntable_it_does_not_fetch_bow_or_show_the_ring(self):
        from PySide6.QtCore import QPointF
        pg, roam = self.pg, self.pg.roam
        self.open_page()
        self.assertFalse(pg.fetch_on, "捡球的闸关着")
        b = pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        pg.ball_drag(QPointF(roam.wx - 40, roam.wy - 120))
        self.tick(3.0)
        self.assertIsNone(roam.task, "不站起来看球、不俯身")
        self.assertFalse(pg.ring.counting)
        self.assertEqual(pg.ring.alpha, 0.0, "不出圈")
        pg.ball_release(QPointF(roam.wx - 40, roam.wy - 120))
        self.throw(ready=True)
        self.tick(1.0, each=lambda: self.assertIsNone(roam.task, "扔了不追"))
        self.settings.show_page("main", animated=False)
        self.assertIsNotNone(self.tick(2.0, lambda: not self.win.dog.on_turntable))
        self.assertTrue(pg.fetch_on)
        self.assertIsNone(roam.task, "下来以后也不追已经扔出去的")

    def test_a_fetch_in_progress_stops_and_the_carried_ball_goes_away_with_the_playground(self):
        """叼着球往鼠标那边走的时候打开：临时退出灵动交互——停下、站上转台，嘴里的球跟着收（和关掉开关一样）；离开回来，球放回狗前面。"""
        pg, roam, w = self.pg, self.pg.roam, self.win
        self.throw(ready=True)
        self.assertEqual(roam.task, "fetch")
        self.assertIsNotNone(self.tick(40.0, lambda: roam.carrying), "叼起来了")
        self.cursor = (roam.wx + 3.0 * w.ppm * (1 if roam.wx < 400 else -1), self.floor_y - 100.0)   # 鼠标在远处
        x = roam.wx
        self.open_page()
        self.assertIsNone(roam.task, "停下")
        self.assertFalse(roam.carrying, "嘴里的球跟着收")
        self.assertFalse(pg.carried)
        self.tick(0.5)
        self.assertFalse(pg.ball_win.isVisible(), "球淡掉了")
        self.assertLess(abs(w.scene_world()[0] - x), 0.6 * w.ppm, "就地站住，没有接着往鼠标那边走")
        self.assertTrue(w.dog.on_turntable)
        self.settings.show_page("main", animated=False)
        self.assertIsNotNone(self.tick(3.0, lambda: not w.dog.on_turntable))
        self.assertTrue(pg.active)
        self.assertFalse(roam.carrying, "回来不接着「送球」")
        self.tick(0.5)
        self.assertTrue(pg.ball_win.isVisible(), "球回来了")
        self.assertLess(abs(pg.ball.x - roam.wx), w.ppm * 1.0, "放在狗前面")

    def test_entering_leaves_dynamic_for_a_while_and_leaving_comes_back(self):
        """这两页是看狗、摆姿势的，球不该在，灵动交互里狗也不能随便拖——进页先临时退出灵动交互：球、圈、物件收起来，
        狗能上下拖，姿势听那一排；设置里的开关不变、不存。离开和打开开关一样：拖到半空的狗落下去，球、物件回来。"""
        w, pg, roam = self.win, self.pg, self.pg.roam
        bed = "bed/blue" if any(t.key == "bed/blue" for t in w.things_available()) else None
        if bed is not None:
            w.set_thing(bed, True)
            self.tick(4.0)
        self.assertTrue(pg.ball_win.isVisible())
        self.open_page()
        self.assertFalse(w.dynamic, "这会儿退出了")
        self.assertTrue(w.dynamic_setting, "设置里的开关不变")
        self.assertIs(w.settings.values.get("dynamic", True), True, "也不存")
        self.assertFalse(pg.active)
        self.tick(0.5)
        self.finish_fades()
        self.assertFalse(pg.ball_win.isVisible(), "球淡掉了")
        if bed is not None:
            t = pg.things.items[bed]
            self.assertFalse(t.win.isVisible(), "窝照关灵动交互的规矩收起来了")
            self.assertFalse(pg.things.front_shown(bed), "放大的狗爪子前面不会有窝的前沿")
            self.assertTrue(w.thing_on(bed), "只是收起来，还记着摆着")
        self.settings.sync()
        self.assertTrue(self.settings.dynamic.isChecked(), "卡片上的开关还开着")
        x, y = w.scene_world()
        w.place_scene(x, y - 2.0 * w.ppm)                         # 灵动交互关着：狗能往上拖到半空
        self.tick(0.3)
        self.assertLess(w.scene_world()[1], y - w.ppm, "停在半空，不掉")
        self.sc.set_posture("sitting")
        self.assertIsNotNone(self.tick(4.0, lambda: w.dog.posture == "sitting" and not w.dog.transition), "坐下")
        self.settings.show_page("main", animated=False)
        self.assertIsNotNone(self.tick(3.0, lambda: not w.dog.on_turntable))
        self.assertTrue(w.dynamic)
        self.assertTrue(pg.active)
        self.assertIsNotNone(self.tick(4.0, lambda: roam.task is None and abs(w.scene_world()[1] - self.floor_y) < 1.0), "拖到半空的落下去")
        self.tick(0.5)
        self.assertTrue(pg.ball_win.isVisible(), "球回来了")
        if bed is not None:
            self.assertTrue(pg.things.items[bed].win.isVisible(), "窝摆回来了")

    def test_in_the_air_it_lands_before_the_turntable_and_zoom_take_over(self):
        """被扔在空中时打开、按「放大」：先落地（转台这期间只跟着，灵动交互落地了才临时退出），落地后才放大；朝向一路没有跳变。"""
        w, roam = self.win, self.pg.roam
        roam.throw(-900.0, -1200.0)
        self.tick(0.15)
        self.assertEqual(roam.task, "fall")
        self.open_page()
        self.sc.set_zoom(True)
        self.settings.pet_detail.ruler._turn(40.0)
        yaws = [w.dog.yaw]

        def watch():
            yaws.append(w.dog.yaw)
            if roam.task is not None:
                self.assertFalse(w.showing_scaled, "在空中不放大")
        self.assertTrue(w.dynamic, "在空中：先不退出")
        self.assertIsNotNone(self.tick(6.0, lambda: roam.task is None, each=watch), "落地了")
        self.tick(1.5, each=watch)
        self.assertFalse(w.dynamic, "落地了才临时退出")
        self.assertTrue(w.showing_scaled, "落地后放大")
        self.assertLess(max(abs(wrap(b - a)) for a, b in zip(yaws, yaws[1:])), 5.0, "朝向没有跳变")

    def test_the_zoom_keeps_the_world_at_the_saved_size_and_the_play_resumes_after(self):
        """放大只是画得大：空间的比例尺、地面不变；灵动交互临时退出着，roam 不走（钟也不走），脚还踩在那条线上；离开回来 roam 接着走。"""
        w, pg, roam = self.win, self.pg, self.pg.roam
        self.open_page()
        ppm, floors, t0 = pg.ppm, [f.y for f in pg.world.floors], roam.t
        feet = w.scene_world()[1]
        self.sc.set_zoom(True)
        self.tick(1.2)
        self.assertGreater(w.scale, 1.5 * w.world_scale)
        self.assertEqual((pg.ppm, [f.y for f in pg.world.floors]), (ppm, floors))
        self.assertAlmostEqual(roam.t, t0, delta=2 * DT, msg="roam 停住了")
        self.assertAlmostEqual(w.scene_world()[1], feet, delta=0.5, msg="脚踩的那条线不动")
        self.assertFalse(roam.moved)
        self.sc.set_zoom(False)
        self.assertIsNotNone(self.tick(1.5, lambda: not w.showing_scaled))
        self.settings.show_page("main", animated=False)
        self.assertIsNotNone(self.tick(3.0, lambda: not w.dog.on_turntable))
        self.tick(0.3)
        self.assertGreater(roam.t, t0 + 0.1, "回到灵动交互接着走")
        self.assertAlmostEqual(w.scene_world()[1], feet, delta=1.0, msg="还踩在那条线上")

    def test_on_a_high_window_the_zoom_keeps_its_feet_on_the_window_and_it_does_not_fall(self):
        """站在贴近屏幕顶的窗口上：放大照样到上限（头顶出了屏幕的那截看不见），根钉在窗口上沿上不动；缩回来还站在窗口上。"""
        w, pg, roam = self.win, self.pg, self.pg.roam
        top_y = 330.0
        self.frames[7] = (300.0, top_y, 360.0, 300.0)
        pg._sups = None
        pg._frames_at = -math.inf
        s = next(s for s in pg.supports() if s.key == 7 and s.kind == "window")
        self.assertTrue(roam.go_to(s, 480.0))
        self.assertIsNotNone(self.tick(12.0, lambda: roam.task is None), "跳上去了")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", 7))
        self.open_page()
        base = w.scene_world()
        self.sc.set_zoom(True)
        self.tick(1.2, each=lambda: self.assertLess(math.dist(w.scene_world(), base), 0.5, "根不动"))
        self.assertAlmostEqual(w.scale, w.world_scale * self.sc.max_level(), places=3, msg="照样放到上限")
        x, y = w.scene_world()
        self.assertLess(y - w.dog.stance_top() * w.ppm, 0.0, "头顶出了屏幕的那截看不见")
        self.assertAlmostEqual(y, top_y, delta=0.5, msg="脚还在窗口上沿")
        self.assertTrue(300.0 <= x <= 660.0)
        self.sc.set_zoom(False)
        self.assertIsNotNone(self.tick(1.5, lambda: not w.showing_scaled))
        self.tick(0.5)
        self.assertIsNone(roam.task, "没掉下去")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", 7))


    def test_entering_stops_a_run_where_it_is_and_stands(self):
        """灵动交互开着在跑的也一样——被拉着往远处跑的，进这一页就地站住（不接着跑过去），家改到停下的地方。"""
        w, roam = self.win, self.pg.roam
        far = 60.0 if roam.wx > 400 else 740.0
        self.assertTrue(roam.go_to(roam.support, far))
        self.tick(0.4)
        self.assertEqual(roam.task, "go")
        self.open_page()
        self.assertIsNotNone(self.tick(1.0, lambda: roam.task is None), "就地站住")
        x = roam.wx
        self.tick(2.0)
        self.assertLess(abs(roam.wx - x), 0.5, "不接着跑")
        self.assertGreater(abs(far - x), 100.0, "没跑到")
        self.assertEqual((w.dog.posture, w.dog.on_turntable), ("standing", True))

    def test_the_buttons_work_here_too_and_leaving_stands_it_back_up(self):
        """灵动交互开着：那一排照样能让它坐、趴；被拎起来就是站着（那一排跟着亮「站」）；离开回到灵动交互里的样子（站着）。"""
        w, pg, roam = self.win, self.pg, self.pg.roam
        dog = w.dog
        self.open_page()
        self.sc.set_posture("lying")
        self.assertIsNotNone(self.tick(4.0, lambda: dog.posture == "lying" and not dog.transition), "趴下")
        pg.dog_grabbed((roam.wx, roam.wy))
        self.tick(0.2)
        self.assertEqual(self.sc.posture, "standing", "拎起来：亮「站」")
        pg.dog_dropped()
        self.assertIsNotNone(self.tick(4.0, lambda: roam.task is None and not roam.lifted), "落地")
        self.tick(1.0)
        self.assertEqual((dog.posture, self.sc.posture), ("standing", "standing"))
        self.sc.set_posture("sitting")
        self.assertIsNotNone(self.tick(4.0, lambda: dog.posture == "sitting" and not dog.transition), "坐下")
        self.settings.show_page("main", animated=False)
        self.assertIsNotNone(self.tick(3.0, lambda: not dog.on_turntable))
        self.assertIsNotNone(self.tick(4.0, lambda: dog.posture == "standing" and not dog.transition), "离开：站回来")


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class TurntableControllerTests(unittest.TestCase):
    """控制器自己的转台（play.Turntable、set_turntable）：不开窗口。"""

    @classmethod
    def setUpClass(cls):
        from widget import gltf
        cls.model = gltf.load(config.MODEL_PATH)

    def dog(self, posture="standing"):
        from widget.dogctl import DogController
        c = DogController(self.model, seed=2)
        c.set_rest_posture(posture)
        c.set_play(True, home_yaw=210.0)
        self.play_for(c, 5.0)
        return c

    @staticmethod
    def play_for(c, seconds, each=None):
        for _ in range(int(round(seconds * 60))):
            c.update(DT)
            c.frame()
            if each is not None:
                each()

    def test_getting_on_stands_it_up_and_getting_off_puts_it_back(self):
        """上转台：自己来的动作一刀切、排着的都作废，站起来；之后不来随机动作。下来：回到选的姿势，随机动作重新计时。"""
        from widget.clips import ACTIONS_BY_ID
        from widget.play import ActionStep, PostureStep, TurnStep
        c = self.dog("lying")
        self.assertEqual(c.posture, "lying")
        c._start_action(next(a for a in ACTIONS_BY_ID.values() if a.posture == "lying"))
        c.steps = [TurnStep(330.0), ActionStep(next(iter(ACTIONS_BY_ID.values()))), PostureStep("lying")]
        c.set_turntable(True)
        self.assertIsNone(c.run, "自己来的动作一刀切")
        self.assertEqual(c.steps, [PostureStep("standing")], "排着的转身、动作作废，站起来")
        self.assertEqual(c.turntable_pose, "standing")
        self.play_for(c, 20.0, each=lambda: self.assertIsNone(c.run))
        self.assertEqual((c.posture, c.transition), ("standing", False))
        c.set_turntable(False)
        self.assertIsNone(c.turntable_pose)
        self.assertTrue(c.t < c.action_at < math.inf, "下来：随机动作重新计时")
        self.play_for(c, 4.0)
        self.assertEqual((c.posture, c.transition), ("lying", False), "回到选的姿势")

    def test_the_turntable_pose_waits_while_roam_drives_and_getting_off_can_be_instant(self):
        """被 roam 牵着（拎着、在跑）时点的姿势只记下，交回来再换；roam 接管时转台姿势变成站着。换同桌时下转台当场待在选的姿势里（不播）。"""
        c = self.dog("standing")
        c.set_rest_posture("lying")
        self.play_for(c, 4.0)
        c.set_turntable(True)
        self.play_for(c, 4.0)
        self.assertEqual(c.posture, "standing")
        c.set_turntable_pose("sitting")
        self.play_for(c, 4.0)
        self.assertEqual(c.posture, "sitting")
        c.puppet_begin()
        self.assertEqual(c.turntable_pose, "standing", "牵着就是站着")
        c.puppet_stand()
        self.play_for(c, 3.0)
        c.set_turntable_pose("lying")
        self.assertEqual(c.steps, [], "牵着：只记下")
        c.puppet_end()
        self.play_for(c, 4.0)
        self.assertEqual((c.posture, c.transition), ("lying", False), "交回来再趴下")
        c.set_turntable_pose("standing")
        self.play_for(c, 0.3)
        self.assertTrue(c.transition)
        c.set_turntable(False, instant=True)
        self.assertEqual((c.posture, c.transition, c.steps), ("lying", False, []), "当场待在选的姿势里")

    def test_a_posture_change_in_progress_is_not_cut(self):
        """刚点了「站」、正在起身时打开那一页：起身照样做完（一刀切是给新命令的）。"""
        c = self.dog("lying")
        c.set_rest_posture("standing")
        self.play_for(c, 0.2)
        self.assertTrue(c.transition)
        queue = list(c.queue)
        c.set_turntable(True)
        self.assertTrue(c.transition, "没切")
        self.assertEqual(c.queue, queue)
        self.play_for(c, 4.0)
        self.assertEqual(c.posture, "standing")
        self.assertFalse(c.transition)

    def test_a_cut_turn_slides_on_and_the_ruler_counts_from_where_it_was_going(self):
        c = self.dog("standing")
        c._request_turn(330.0)
        self.play_for(c, 0.2)
        self.assertIsNotNone(c.turn)
        c.set_turntable(True)
        self.assertIsNone(c.turn)
        self.assertIsNotNone(c.settle.yaw, "朝向滑到它要去的地方（一刀切）")
        c.turntable_turn(30.0)
        self.assertAlmostEqual(c.turntable_angle % 360.0, 0.0, places=6, msg="330 + 30")
        prev = [c.yaw]

        def smooth():
            self.assertLess(abs(wrap(c.yaw - prev[0])), 10.0, "不跳（滑回和转盘的弹簧起步都是平的；跳一下是整段 30° 以上）")
            prev[0] = c.yaw
        self.play_for(c, 1.0, each=smooth)
        self.assertLess(abs(wrap(c.yaw - 0.0)), 0.05)

    def test_while_roam_drives_the_turntable_follows_and_takes_over_without_a_jump(self):
        """roam 牵着（在跑、在跳、被拎着）的时候转盘只记着；交回来从实际朝向起步（速度从 0 开始，不甩），走近的那边、按转回去的快慢过去。
        roam 这期间把它转过了半圈（210° → 0°，转盘记的是 150°）：不绕远路转 210°。"""
        c = self.dog("standing")
        c.puppet_begin()
        c.set_turntable(True)
        c.turntable_turn(-60.0)
        c.puppet_face(0.0)
        self.play_for(c, 0.6)
        self.assertLess(abs(wrap(c.yaw - 0.0)), 0.5, "roam 转到哪就是哪")
        c.puppet_end()
        yaws = [c.yaw]
        self.play_for(c, 1.2, each=lambda: yaws.append(c.yaw))
        steps = [wrap(b - a) for a, b in zip(yaws, yaws[1:])]
        self.assertLess(abs(steps[0]), 3.0, "接手那一帧从 0 速度起步，不甩")
        self.assertTrue(all(d >= -1e-6 for d in steps), "走近的那边（往 +150° 转），一路单调")
        self.assertLess(max(steps), 13.0, "转回去的快慢（0.5 秒）")
        self.assertLess(abs(wrap(c.yaw - (210.0 - 60.0))), 0.05, "转到转盘记着的地方（是从当时要朝的方向算的）")

    def test_retargets_never_overshoot(self):
        """Turntable.go_to、animation.Spring.retarget：往反方向跑着的先停住，冲得太快的压到刚好停住，一路单调。"""
        from widget.animation import Spring
        from widget.play import Turntable
        for make in (lambda: Turntable(0.0), lambda: Spring(0.0, 0.5)):
            s = make()
            if isinstance(s, Turntable):
                s.aim_at(100.0)
                s.set_speed(0.12)
            else:
                s.set_target(100.0)
            for _ in range(5):
                s.step(DT)
            self.assertGreater(s.velocity, 100.0, "正往外冲")
            go = s.go_to if isinstance(s, Turntable) else s.retarget
            go(0.0)
            values = []
            for _ in range(120):
                s.step(DT)
                values.append(s.value)
            self.assertTrue(all(b <= a + 1e-9 for a, b in zip(values, values[1:])), "一路往回，不先往外冲")
            self.assertTrue(all(v >= -1e-9 for v in values), "不过头")
        sp = Spring(0.0, 0.5)
        sp.value, sp.velocity = 10.0, -1000.0                    # 朝着目标但冲得太快
        sp.retarget(0.0)
        values = []
        for _ in range(60):
            sp.step(DT)
            values.append(sp.value)
        self.assertTrue(all(v >= -1e-9 for v in values), "压到刚好停在目标上")

    def test_spring_eps_keeps_the_old_default_and_settles_small_ranges_without_a_snap(self):
        from widget.animation import Spring
        a = Spring(0.0, 0.3)
        a.set_target(1.0)
        last = 0.0
        jumps = []
        while not a.settled:
            a.step(DT)
            jumps.append(a.value - last)
            last = a.value
        self.assertEqual(a.eps, 0.02, "默认还是按像素的 0.02")
        b = Spring(0.0, 0.45, eps=1e-3)
        b.set_target(1.0)
        values = []
        while not b.settled:
            b.step(DT)
            values.append(b.value)
        self.assertLess(1.0 - values[-2], 2e-3, "最后一步跳过去的不到千分之二（0..1 的进度，放大两倍时不到 1 像素）")


if __name__ == "__main__":
    unittest.main()
