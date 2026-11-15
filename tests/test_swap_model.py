"""换到别的模型的同桌不重启：灵动交互开着的时候旧狗手上的事怎么收、新狗站哪
（playground.pet_leaving / pet_arrived、roam.leave / use_dog / land_now），和整条路真的走一遍（window.add_pet → switch_pet → _use_kit，
边牧换萨摩耶，萨摩耶的模型不在跳过）。新狗一律站在旧狗那条线上，不接着做上一只做到一半的事：在半空的直接落到正下方、在窝里的不接着趴、
叼着的球掉在原地；灵动交互关着就直接是选的姿势。换完没人还拿着旧狗，这一帧就是新狗。
真窗口（offscreen）+ 假设置（卸载器挡住），窝、盆的款表用 tests/test_nest.py、tests/test_bowl.py 那两张假的。"""
import dataclasses
import gc
import math
import os
import unittest
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF

from tests.room_base import COLLIE, DT, HAS, SAMOYED, load
from tests.test_bowl import FOOD, BowlCase
from tests.test_nest import BED, NestCase
from widget import roam as roam_mod, temper


class LeavingTests(NestCase):
    """旧狗要走了（pet_leaving）：手上的事收掉，球和物件留着、灵动交互不关。"""
    PACK = COLLIE

    def test_a_ball_in_the_mouth_is_let_go_right_there(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=200.0)
        self.step(0.3)
        self.throw_and_fetch(500.0)
        self.assertIsNotNone(self.step(15.0, lambda: roam.carrying), "叼起来了")
        self.step(0.4)
        mouth = roam.mouth_point()
        pg._charging = True
        with mock.patch.object(pg.ball_bank, "fade") as fade:
            pg.pet_leaving()
        b = pg.ball
        self.assertEqual((pg.carried, roam.carrying, roam.task, roam.leg), (False, False, None, None))
        self.assertTrue(pg.ball_win.isVisible(), "球的小窗口回来")
        self.assertAlmostEqual(b.x, mouth[0], delta=1.0, msg="掉在嘴那儿")
        self.assertEqual(b.vx, 0.0, "原地松口，不带着跑的速度飞出去")
        fade.assert_called_once_with("charge")
        self.assertFalse(pg._charging, "充能的声音一起收")
        self.assertTrue(pg.active, "灵动交互不关")

    def test_a_dog_in_its_bed_gets_out_and_the_front_goes_away(self):
        pg, dog = self.pg, self.win.dog
        t, spot = self.home(BED)
        self.assertGreater(dog.perch, 0.0)
        self.assertTrue(self.things.front_shown(BED))
        pg.pet_leaving()
        self.assertIsNone(pg._nest)
        self.assertEqual((dog.perch, pg._perch_to, pg._idle_for), (0.0, 0.0, 0.0), "根落回线上，钟归零：到时候新狗自己再回")
        self.assertFalse(self.things.front_shown(BED))
        self.assertTrue(t.win.isVisible(), "窝还在")

    def test_held_or_flying_it_just_stops(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        pg.dog_grabbed()
        self.step(0.2)
        self.assertTrue(roam.lifted)
        pg.pet_leaving()
        self.assertFalse(roam.lifted)
        self.assertFalse(self.win.dog.lift.on)
        roam.throw(900.0, -1200.0)
        self.step(0.15)
        self.assertEqual(roam.task, "fall")
        pg.pet_leaving()
        self.assertEqual((roam.task, roam.leg, roam.v), (None, None, 0.0), "不接着飞")

    def test_off_it_does_nothing(self):
        pg = self.pg
        self.assertFalse(pg.active)
        pg.pet_leaving()
        self.assertFalse(pg.active)


class LandingTests(NestCase):
    """新狗站哪（roam.land_now）：站在旧狗那条线上；在半空的、那条线站不下它的，直接放到正下方最近的线上，不起 fall。"""
    PACK = COLLIE

    def test_on_its_line_it_stays(self):
        roam = self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        x, y = roam.wx, roam.wy
        roam.land_now()
        self.assertEqual((roam.wx, roam.wy, roam.support.kind, roam.task), (x, y, "floor", None))
        self.assertEqual((roam.home.kind, roam.home.dx), ("floor", x), "记作家")

    def test_in_the_air_it_is_put_straight_down(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        roam.throw(0.0, -1500.0)
        self.step(0.2)
        self.assertLess(roam.wy, self.floor_y - 20.0, "在半空")
        x = roam.wx
        pg.pet_leaving()
        roam.land_now()
        self.assertEqual((roam.wx, roam.wy, roam.support.kind), (x, self.floor_y, "floor"), "正下方")
        self.assertIsNone(roam.task, "不起 fall、不播落地")
        self.assertTrue(roam.moved, "窗口要跟着摆")

    def test_a_window_too_low_for_the_new_dog_drops_it_to_the_floor(self):
        """只够边牧站的窗口（离屏幕最上沿 0.89 米：边牧要 0.86，萨摩耶 0.92）：换成高的那只，落到地面。"""
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        top = self.app.primaryScreen().geometry().y() + 0.89 * pg.ppm
        s = self.add_window(7, 200.0, top, 400.0)
        self.assertIsNotNone(s, "边牧站得下")
        roam.place(400.0, s.y)                                # 站上去（怎么跳上去的不是这里要看的）
        self.assertEqual(roam.settle_support().key, s.key)
        self.win.place_scene(roam.wx, roam.wy)
        pg.pet_leaving()
        roam.land_now()
        self.assertEqual(roam.support.key, s.key, "还是边牧：站在原地")
        pg.pack = dataclasses.replace(pg.pack, height_m=0.86, fit_m=0.92)
        pg._compose_frames()
        roam.land_now()
        self.assertEqual((roam.support.kind, roam.wy), ("floor", self.floor_y), "头顶不够了：落到正下方的地面")


class ArrivingTests(NestCase):
    """新狗来了（pet_arrived）：抄着的引用改成新的，roam 牵新狗，跳法的数按新模型拿。"""
    PACK = COLLIE

    def test_it_points_everything_at_the_new_dog(self):
        from widget.dogctl import DogController
        from widget.tuning import Tuning
        from widget.voice import SoundBank
        win, pg, roam = self.win, self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        roam.leap_spec()
        pg.mood.cue("put", roam.t)
        win.dog.excite.value = 0.8
        pg.pet_leaving()
        pack = dataclasses.replace(self.pack, id="other")
        win.pack, win.dog = pack, DogController(self.model, seed=9)
        win.tuning = Tuning(pack, win.settings)
        win.sound_bank = SoundBank(pack, win.tuning)
        win.dog.tune = win.tuning
        win.dog.set_dynamic(True)
        win.dog.set_play(True)
        win.dog.snap_home(330.0)
        pg.pet_arrived()
        self.assertEqual((pg.dog, pg.pack, pg.tune, pg.bank, roam.dog), (win.dog, pack, win.tuning, win.sound_bank, win.dog))
        self.assertIsNone(roam._spec, "跳法的数按新模型重拿")
        self.assertEqual(roam.leap_spec().push_x, roam_mod.leap_measures(win.dog)[0].push_x)
        self.assertEqual((win.dog.excite.value, pg.mood.cue("put", roam.t)), (0.0, True), "招牌时刻、兴奋度重来（新狗新的一份）")
        self.assertEqual(roam.facing, 1.0, "朝向照新狗（330° 朝右）")
        self.assertIsNotNone(win.dog.lift.rig, "拎起来的姿势先量好（模型上有就直接拿）")
        self.step(0.5)
        self.assertTrue(pg.active)


@unittest.skipUnless(HAS[SAMOYED], "models/samoyed.glb not present (purchased asset)")
class SwapTests(BowlCase):
    """真的换一遍：边牧（启动时那只）→ 添一只萨摩耶、当场换过去。"""
    PACK = COLLIE

    def swap(self, pack_id=SAMOYED, name=""):
        """添一只 pack_id 的同桌、当场换过去（window.add_pet → switch_pet → _use_kit）。模型用 tests/room_base.py 读好的那份、先记成备好的
        （后台怎么备在 tests/test_kits.py）；萨摩耶调参、声音照真的建。不许重启。返回新那只的号。"""
        from widget.tuning import Tuning
        from widget.voice import SoundBank
        win = self.win
        pack, model = load(pack_id)
        if not win.kits.ready(pack.id):
            tuning = Tuning(pack, win.settings)
            win.kits.adopt(pack, model, tuning, SoundBank(pack, tuning))
        with mock.patch.object(win, "restart", side_effect=AssertionError("换模型不重启")):
            pet_id = win.add_pet(pack.id, name or pack.default_name)   # 添加页没填名字给的就是模型自己的名字
        self.assertIsNotNone(pet_id)
        self.assertEqual((win.pack.id, win.model, win.prefs.pet_id), (pack.id, model, pet_id))
        return pet_id

    def test_everything_points_at_the_new_dog_and_nobody_keeps_the_old_one(self):
        win, pg = self.win, self.pg
        self.start_on_floor(x=300.0)
        self.step(0.5)
        old = weakref.ref(win.dog)
        self.swap()
        dog = win.dog
        self.assertEqual((pg.dog, pg.roam.dog, pg.pack, pg.tune, pg.bank), (dog, dog, win.pack, win.tuning, win.sound_bank))
        self.assertEqual((dog.model, win.view.renderer.model, win.look.model, dog.tune), (win.model,) * 3 + (win.tuning,))
        self.assertIs(win.clip_sounds.bank, win.sound_bank)
        self.assertEqual((win.tuning.pack.id, win.sound_bank.pack.id, win.prefs.pack_id, win.dog_name), (SAMOYED, SAMOYED, SAMOYED, "Mochi"))
        self.assertEqual(win.settings.values["pack"], SAMOYED, "下次启动按它载入")
        self.assertEqual(win._pose.joints, dog.frame().joints, "这一帧就是新狗排的")
        self.assertTrue(win.view.renderer._mesh_dirty or win.view.renderer.rhi is None, "顶点缓冲下一次画的时候换")
        self.step(1.0)
        gc.collect()
        self.assertIsNone(old(), "没人还拿着旧狗（漏改的「抄了一份」靠这条抓）")
        self.assertTrue(pg.active)

    def test_the_ghost_windows_swap_too_and_start_empty(self):
        win = self.win
        self.start_on_floor(x=300.0)
        ghost = mock.Mock()
        with mock.patch.dict(win._ghosts, {"side": ghost}, clear=True):
            self.swap()
        ghost.view.set_model.assert_called_once_with(win.model)
        ghost.view.renderer.set_coat.assert_called_once_with(None)
        ghost.clear.assert_called_once_with()

    def test_back_to_the_first_one_reads_nothing_again(self):
        from widget import packs
        win = self.win
        self.start_on_floor(x=300.0)
        first = win.pets()[0].id
        collie = win.model
        with mock.patch.object(packs, "load_model", side_effect=AssertionError("不重读")):
            sam = self.swap()
            win.switch_pet(first)
            self.assertEqual((win.pack.id, win.model), (COLLIE, collie), "换回来：启动时那只现成的")
            win.switch_pet(sam)
        self.assertEqual(win.pack.id, SAMOYED)

    def test_a_ball_in_the_mouth_falls_where_it_is(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=200.0)
        self.step(0.3)
        self.throw_and_fetch(500.0)
        self.assertIsNotNone(self.step(15.0, lambda: roam.carrying), "叼起来了")
        self.step(0.3)
        mouth = roam.mouth_point()
        self.swap()
        self.assertEqual((pg.carried, roam.carrying, roam.task), (False, False, None))
        self.assertTrue(pg.ball_win.isVisible(), "球的小窗口回来")
        self.assertAlmostEqual(pg.ball.x, mouth[0], delta=1.0)
        self.step(2.0)
        self.assertTrue(pg.ball.resting, "球掉在脚边")
        self.assertIsNone(roam.task, "新狗不接着叼")

    def test_in_its_bed_it_stands_on_the_cushion_and_comes_back_later(self):
        pg = self.pg
        t, spot = self.home(BED)
        self.swap()
        dog = self.win.dog
        self.assertIsNone(pg._nest, "不接着趴")
        self.assertEqual((dog.posture, dog.lounge, dog.transition, pg._idle_for), ("standing", None, False, 0.0))
        self.assertEqual(pg._pad, BED, "站在窝那儿：踩着垫子")
        self.assertEqual(dog.perch, pg._perch_to, "这一帧就抬好，不从地上缓上去")
        self.assertGreater(t.geo[1], 1.6 * 0.80 / 0.8, "狗窝跟着萨摩耶的身高变大")
        pg._idle_for = pg._nest_after()
        self.assertIsNotNone(self.step(25.0, self.nested), "到时候它自己再回窝趴下")

    def test_flying_it_is_put_straight_down(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        roam.throw(400.0, -1500.0)
        self.step(0.2)
        self.assertLess(roam.wy, self.floor_y - 20.0, "在半空")
        x = roam.wx
        self.swap()
        self.assertEqual((roam.task, roam.support.kind, roam.wy), (None, "floor", self.floor_y), "不接着飞，不起 fall")
        self.assertAlmostEqual(roam.wx, x, delta=0.01, msg="正下方")
        for got, want in zip(self.win.scene_world(), (roam.wx, roam.wy)):
            self.assertAlmostEqual(got, want, delta=0.5, msg="窗口跟着摆好了")

    def test_held_up_it_is_let_go(self):
        pg, roam, win = self.pg, self.pg.roam, self.win
        self.start_on_floor(x=300.0)
        self.step(0.3)
        win._drag = QPointF(10.0, 10.0).toPoint()
        win._dragged = True
        pg.dog_grabbed()
        self.step(0.3)
        self.swap()
        self.assertFalse(roam.lifted)
        self.assertIsNone(win._drag, "这次拖动作废：松手不算扔")
        self.assertEqual(roam.support.kind, "floor")

    def test_eating_stops_and_the_bowl_stays_full(self):
        roam = self.pg.roam
        self.start_on_floor(x=140.0)
        t = self.put(FOOD)
        self.tap(t)
        self.assertIsNotNone(self.step(10.0, lambda: roam.phase == "loop"))
        self.swap()
        self.assertEqual((roam.task, self.pg._eating), (None, None))
        self.step(2.0)
        self.assertTrue(t.full, "没吃完：盆还是满的")
        self.assertIsNone(roam.task, "不接着吃")

    def test_a_window_only_the_collie_fits_drops_the_samoyed_to_the_floor(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        top = self.app.primaryScreen().geometry().y() + 0.89 * pg.ppm      # 边牧要 0.86 米，萨摩耶 0.92
        s = self.add_window(7, 200.0, top, 400.0)
        roam.place(400.0, s.y)
        roam.settle_support()
        self.win.place_scene(roam.wx, roam.wy)
        self.step(0.3)
        self.assertEqual(roam.support.key, 7)
        self.swap()
        self.assertEqual((roam.support.kind, roam.wy, roam.task), ("floor", self.floor_y, None), "头顶不够了：落到正下方的地面")

    def test_a_ball_in_your_hand_is_watched_again_from_an_empty_ring(self):
        pg, roam = self.pg, self.pg.roam
        self.start_on_floor(x=300.0)
        self.step(0.3)
        self.pick_up_ball()
        self.assertIsNotNone(self.step(3.0, lambda: pg.ring.progress > 0.2), "圈在涨")
        self.swap()
        self.assertTrue(pg.ball_held, "球还在你手上")
        self.assertEqual((pg.ring.progress, pg.ring.ready, pg._charging), (0.0, False, False), "圈清掉，充能的声音收了")
        self.step(DT)
        self.assertTrue(roam.waiting_for_throw or pg._seat_watch, "下一帧照「球在你手上」重新看球（萨摩耶默认坐着：坐着看）")
        self.assertIsNotNone(self.step(4.0, lambda: pg.ring.ready), "圈从空的重新涨满")

    def test_with_play_off_a_lying_dog_is_lying_at_once(self):
        win = self.win
        win.show()
        win.set_dynamic(False)
        win.set_rest_posture("lying")
        for _ in range(6 * 60):
            win.dog.update(DT)
        self.swap()
        dog = win.dog
        self.assertEqual((dog.posture, dog.transition, dog.steps), ("lying", False, []), "不先站着再趴下")
        self.assertTrue(dog.player.name.startswith("Lie_belly_loop"))
        self.assertFalse(win.playground.active)


if __name__ == "__main__":
    unittest.main()
