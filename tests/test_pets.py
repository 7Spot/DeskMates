"""「我的同桌」：名单和每只各记一份的设置（widget/prefs.py）、窗口里换 / 添 / 删（widget/window.py）、
设置主页面顶部栏下面的滑动条（widget/petstrip.py）和它跟顶部栏（card.TitleBar）的配合、添加页（widget/settings.py）。
贴纸要真的 GL 才画得出来，这里测的是它以外的东西。"""
import json
import unittest
from unittest import mock

from tests.panel_base import FakeSettings, PanelCase


class RosterTests(unittest.TestCase):
    def test_the_first_deskmate_keeps_its_old_keys_and_later_ones_get_their_own(self):
        """升级上来的那只：名字、毛色还在原来的键上（不丢设置）；后来添加的每只一份，同一个模型养两只也分开。大小是全局的一个，谁读都一样。"""
        from widget.prefs import FIRST_PET, Prefs, Roster
        store = FakeSettings()
        store.values.update(dog_name="Milo", coat=2, scale=1.5)
        roster = Roster(store, "border_collie")
        self.assertEqual([(p.id, p.pack) for p in roster.pets()], [(FIRST_PET, "border_collie")], "没记过名单：只有原来那只")
        first = Prefs(store, "border_collie", "Milo", roster.current_id)
        self.assertEqual((first.get("dog_name"), first.get("coat"), first.get("scale")), ("Milo", 2, 1.5))
        second = roster.add("border_collie")
        self.assertEqual(second.id, "p1")
        mine = first.of(second.id, second.pack, "Milo")
        self.assertEqual((mine.get("dog_name"), mine.get("coat")), ("Milo", 1), "新的一只从默认值开始")
        self.assertEqual(mine.get("scale"), 1.5, "大小是全局的：新的一只和别的一样大")
        mine.set("scale", 0.9)
        self.assertEqual((store.values["scale"], first.get("scale")), (0.9, 0.9))
        self.assertNotIn("pet/p1/scale", store.values)
        mine.set("dog_name", "奶茶")
        mine.set("coat", 3)
        self.assertEqual(store.values["pet/p1/dog_name"], "奶茶")
        self.assertEqual((first.get("dog_name"), first.get("coat")), ("Milo", 2), "第一只的不受影响")
        self.assertEqual(json.loads(store.values["pets"]), [{"id": "", "pack": "border_collie"}, {"id": "p1", "pack": "border_collie"}])
        again = Roster(store, "border_collie")
        self.assertEqual([p.id for p in again.pets()], ["", "p1"], "重启读得回来")

    def test_sizes_kept_per_deskmate_by_older_builds_become_one_shared_size(self):
        """0.6.0 (54) 以前大小每只各记一份。大小是全局的 —— 启动时把现在这只的搬到全局的键上，别的丢掉，只搬这一次。"""
        from widget.prefs import Pet, Prefs, share_size
        store = FakeSettings()
        store.values.update({"scale": 1.0, "pet/p1/scale": 1.3, "pet/p1/scale_chosen": True, "pet/p2/scale": 0.7, "pet/p1/coat": 3})
        pets = [Pet("", "border_collie"), Pet("p1", "border_collie"), Pet("p2", "border_collie")]
        share_size(store, pets, "p1")
        self.assertEqual((store.values["scale"], store.values["scale_chosen"]), (1.3, True), "现在这只的大小成了全局的")
        self.assertFalse([k for k in store.values if k.startswith("pet/") and "scale" in k], "各记一份的旧键都清掉")
        self.assertEqual(store.values["pet/p1/coat"], 3, "毛色还是每只一份，不动")
        store.values["scale"] = 0.8                                    # 之后你又调了大小
        share_size(store, pets, "p1")
        self.assertEqual(store.values["scale"], 0.8, "只搬一次")
        self.assertEqual(Prefs(store, "border_collie", "", "p2").get("scale"), 0.8)
        other = FakeSettings()
        other.values.update({"pack/husky/scale": 1.2, "scale": 0.6})
        share_size(other, [Pet("", "husky")], "")
        self.assertEqual(other.values, {"scale": 1.2}, "第一只换成了别的模型：它的大小记在 pack/<模型>/ 下面，一样搬过来")
        share_size(object(), pets, "p1")                               # 删不了键的设置（别的假设置）：什么都不做，不出错

    def test_selecting_removing_and_never_reusing_a_number(self):
        from widget.prefs import Prefs, Roster
        store = FakeSettings()
        roster = Roster(store, "border_collie")
        self.assertFalse(roster.remove(""), "最后一只删不了")
        a, b = roster.add("border_collie"), roster.add("other")
        roster.select(b.id)
        self.assertEqual((store.values["pet"], store.values["pack"]), ("p2", "other"), "下次启动载入这只的模型")
        Prefs(store, "other", "", b.id).set("dog_name", "芝麻")
        self.assertTrue(roster.remove(b.id))
        self.assertNotIn("pet/p2/dog_name", store.values, "它那一份设置一起删")
        self.assertEqual(roster.current_id, a.id, "删的是现在这只：换到旁边那只（右边没有就左边）")
        self.assertEqual(store.values["pack"], "border_collie")
        self.assertEqual(roster.add("border_collie").id, "p3", "删掉的号不重用")
        roster.select("")
        self.assertTrue(roster.remove(""), "第一只也能删（还有别的）")
        self.assertEqual([p.id for p in roster.pets()], ["p1", "p3"])
        self.assertEqual(roster.current_id, "p1")
        store.values["pets"] = "not json"
        self.assertEqual([p.id for p in Roster(store, "border_collie").pets()], [""], "名单坏了：当只有第一只")


class PetsCase(PanelCase):
    def frames(self, n: int = 60) -> None:
        """卡片的节拍往前走 n 帧（不真等）。"""
        s = self.settings
        for _ in range(n):
            s.frame_step(s.clock._last + 1 / 60, 1 / 60)

    def other_pack(self, **changes):
        """假的「另一个模型」：指着边牧的模型文件（不用买来的萨摩耶也能跑），id、名字、个头不一样。"""
        import dataclasses
        return dataclasses.replace(self.win.pack, **{"id": "other", "names": {"en": "Other"}, "default_name": "Bo", "height_m": 0.9, **changes})

    def three(self):
        """三只边牧：Milo（黑白）、奶茶（棕白）、芝麻（灰白），停在奶茶。"""
        win = self.win
        win.add_pet("border_collie", "奶茶")
        win.add_pet("border_collie", "芝麻")
        win.switch_pet(win.pets()[1].id)
        self.settings.finish_page_anim()                               # 滑动条滑到位
        return win.pets()


class WindowPetsTests(PetsCase):
    def test_adding_switches_right_away_and_each_keeps_its_own_name_and_coat_but_the_size_is_shared(self):
        win = self.win
        self.assertEqual(len(win.pets()), 1)
        win.set_scale(1.4)
        win.add_pet("border_collie", "  奶茶  ")
        pets = win.pets()
        self.assertEqual(len(pets), 2)
        self.assertEqual(win.prefs.pet_id, pets[1].id, "添完马上换过去")
        self.assertEqual(win.dog_name, "奶茶")
        self.assertEqual(self.settings._title_label.text(), "奶茶")
        self.assertEqual(win.coat, 1, "新的一只从第一套毛色开始")
        self.assertAlmostEqual(win.scale, 1.4, msg="大小是全局的：新的一只和原来那只一样大")
        if win.coat_available()[1]:
            win.set_coat(2)
        win.set_scale(0.8)
        win.set_dog_name("拿铁")
        win.switch_pet(pets[0].id)
        win.look.settle()                                              # 贴图在后台线程出（look._CoatJobs）：等它换上
        self.assertEqual((win.dog_name, win.coat), ("Milo", 1))
        self.assertAlmostEqual(win.scale, 0.8, msg="换同桌不改大小")
        self.assertIsNone(win.view.renderer.coat_image, "换回第一套：模型自带的贴图")
        win.switch_pet(pets[1].id)
        win.look.settle()
        self.assertEqual(win.dog_name, "拿铁")
        self.assertAlmostEqual(win.scale, 0.8)
        if win.coat_available()[1]:
            self.assertEqual(win.coat, 2)
            self.assertIsNotNone(win.view.renderer.coat_image)
        self.assertEqual(win.pet_name(pets[0]), "Milo", "不换过去也读得到别的同桌的名字（滑动条上画）")
        self.assertEqual(win.settings.values["pack"], "border_collie")

    def test_the_dog_fades_out_and_back_in_around_a_switch(self):
        """换同桌时狗渐隐渐显，不要突然切。换的那一下（重载毛色要几十毫秒）狗是看不见的；淡出以后没人管也会自己回来。"""
        from widget import native
        from widget import window as window_module
        win = self.win
        ghost = mock.Mock()
        with mock.patch.object(native, "reduce_motion", return_value=False), mock.patch.dict(win._ghosts, {"side": ghost}, clear=True):
            win.fade_dog(False)
            self.assertEqual(win.dog_opacity, 1.0, "窗口没显示：不管")
            win.show()
            win.add_pet("border_collie", "奶茶")
            self.assertEqual(win.dog_opacity, 0.0, "刚换好：还看不见")
            ghost.setWindowOpacity.assert_called_with(0.0)             # 每块屏上画另一半的窗口一起
            self.assertTrue(win._fade_soon.isActive(), "等新毛色画出来再淡入")
            self.assertFalse(win._fade_guard.isActive())
            win.fade_dog(True)                                         # 滑动条到位时再叫一次：不抢在约好的前面
            self.assertEqual(win.dog_opacity, 0.0)
            self.assertTrue(win._fade_soon.isActive())
            win._fade_soon.stop()
            win._fade_soon.timeout.emit()
            anim = win._opacity_anim
            self.assertEqual(anim.state(), anim.State.Running)
            anim.setCurrentTime(anim.duration() // 3)
            part = win.dog_opacity
            win.fade_dog(True)                                         # 已经在淡入了：不重来
            self.assertEqual((anim.state(), win.dog_opacity, anim.startValue()), (anim.State.Running, part, 0.0))
            anim.setCurrentTime(anim.duration())
            self.assertEqual(win.dog_opacity, 1.0)
            ghost.setWindowOpacity.assert_called_with(1.0)
            win.fade_dog(False)                                        # 滑动条：要去另一只，先淡出
            self.assertEqual((anim.endValue(), anim.duration()), (0.0, round(window_module.PET_FADE_OUT_S * 1000)))
            anim.setCurrentTime(anim.duration() // 2)
            half = win.dog_opacity
            self.assertTrue(0.0 < half < 1.0)
            win.fade_dog(True)                                         # 半路折回来：从现在的浓淡接着淡回去，不跳
            self.assertEqual((anim.startValue(), anim.endValue()), (half, 1.0))
            self.assertLess(anim.duration(), round(window_module.PET_FADE_IN_S * 1000), "只走剩下那一段的时间")
            anim.setCurrentTime(anim.duration())
            win.fade_dog(False, 0.0)
            self.assertEqual(win.dog_opacity, 0.0)
            self.assertTrue(win._fade_guard.isActive())
            win._fade_guard.stop()
            win._fade_guard.timeout.emit()                             # 没人叫它回来（滑动条半路被打断）：自己淡回来
            anim.setCurrentTime(anim.duration())
            self.assertEqual(win.dog_opacity, 1.0)
        with mock.patch.object(native, "reduce_motion", return_value=True):
            win.fade_dog(False)
            self.assertEqual(win.dog_opacity, 0.0)
            win.fade_dog(True, delay=0.04)
            self.assertEqual(win.dog_opacity, 1.0, "减少动态效果：当场换，不淡")

    def test_a_custom_coat_belongs_to_one_deskmate(self):
        from widget.coat import CoatSpec
        win = self.win
        win.set_custom_coat(CoatSpec(2, "#FF0000", "#00FF00"))
        win.add_pet("border_collie", "奶茶")
        self.assertEqual(win.coat, 1)
        self.assertEqual(win.coat_spec.main, CoatSpec().main, "新的一只：自定义毛色回到默认")
        first, second = win.pets()
        self.assertEqual(win.pet_look(first)[0], 0)
        self.assertIn("#FF0000", win.pet_look(first)[1])
        self.assertNotEqual(win.pet_look(first)[2], win.pet_look(second)[2], "相邻两只坐相不一样（一只侧一点、一只正着）")
        win.switch_pet(first.id)
        self.assertEqual((win.coat, win.coat_spec.main), (0, "#FF0000"))

    def test_removing_goes_to_the_neighbour_and_the_last_one_stays(self):
        win = self.win
        win.remove_pet(win.pets()[0].id)
        self.assertEqual(len(win.pets()), 1, "最后一只删不了")
        pets = self.three()
        win.remove_pet(pets[1].id)                                     # 删现在这只（奶茶）：换到右边那只
        self.assertEqual([win.pet_name(p) for p in win.pets()], ["Milo", "芝麻"])
        self.assertEqual(win.dog_name, "芝麻")
        self.assertNotIn(f"pet/{pets[1].id}/dog_name", win.settings.values)
        win.remove_pet(win.pets()[0].id)                               # 删别的那只：现在这只不动
        self.assertEqual(win.dog_name, "芝麻")
        self.assertEqual(len(win.pets()), 1)

    def test_a_deskmate_of_another_model_is_switched_to_in_place(self):
        """换模型不能重启。换成别的模型的同桌：当场换好（模型、控制器、渲染器、毛色、声音、调参、游乐场都是新的），
        记下来（下次启动按它载入）；换回去不重读。模型文件不在了的不换。"""
        import gc
        import weakref
        from widget import packs
        win = self.win
        other = self.other_pack()
        first, collie, collie_pack, old_dog = win.pets()[0].id, win.model, win.pack, weakref.ref(win.dog)
        reads = []
        real = packs.load_model
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]), mock.patch.object(win, "restart") as restart, \
                mock.patch.object(packs, "load_model", side_effect=lambda p: (reads.append(p.id), real(p))[1]):
            win.kits.get(other)                                        # 先备好（卡片打开 0.4 秒后就开始备）；没备好时不等、备好再添，见 PendingSwitchTests
            new = win.add_pet("other", "Bo")                          # 添加页没填名字时给的就是这个模型自己的名字（settings._add_pet）
            restart.assert_not_called()
            self.assertEqual(win.prefs.pet_id, new)
            self.assertEqual((win.pack.id, win.prefs.pack_id, win.settings.values["pack"], win.roster.current().pack), ("other",) * 4)
            self.assertEqual(win.dog_name, "Bo")
            self.assertIsNot(win.model, collie)
            self.assertEqual((win.dog.model, win.view.renderer.model, win.look.model), (win.model,) * 3)
            self.assertEqual((win.playground.dog, win.playground.roam.dog, win.dog.tune), (win.dog, win.dog, win.tuning))
            self.assertEqual((win.tuning.pack, win.sound_bank.pack, win.clip_sounds.bank), (other, other, win.sound_bank))
            gc.collect()
            self.assertIsNone(old_dog(), "没人还拿着旧狗")
            win.look.settle()
            win.switch_pet(first)
            self.assertEqual((win.pack.id, win.model, win.prefs.pack_id, win.dog_name), (packs.DEFAULT_PET, collie, packs.DEFAULT_PET, "Milo"))
            win.look.settle()
            win.switch_pet(new)
            self.assertEqual(win.pack.id, "other")
            self.assertEqual(reads, ["other"], "换回去不重读：两个模型都留着")
            restart.assert_not_called()
        with mock.patch.object(packs, "pets", return_value=[collie_pack]), mock.patch.object(win, "restart") as restart:
            win.switch_pet(first)                                      # 边牧这只：模型在
            self.assertEqual(win.roster.current_id, first)
            win.switch_pet(new)                                        # 它的模型不在了
            restart.assert_not_called()
            self.assertEqual(win.roster.current_id, first)

    def test_a_model_that_cannot_be_read_keeps_the_one_you_have(self):
        """模型读不出来（文件坏了、缺骨头）：滑动条滑回原来那只、狗淡回来，什么都不弹、不重启，只记日志；添加页也添不进去。"""
        import tempfile
        from pathlib import Path
        from widget import native, packs
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        bad = Path(folder.name) / "bad.glb"
        bad.write_bytes(b"not a glb")
        win, s = self.win, self.settings
        broken = self.other_pack(id="broken", model=bad)
        win.show()
        s.show()
        with mock.patch.object(packs, "pets", return_value=[win.pack, broken]), mock.patch.object(win, "restart") as restart, \
                mock.patch.object(native, "reduce_motion", return_value=False):
            with self.assertLogs("kits", "ERROR"):
                self.assertIsNone(win.kits.get(broken), "读不出来")
            with self.assertLogs("window", "WARNING"):
                self.assertIsNone(win.add_pet("broken", "x"), "读不出来：不添")
            self.assertEqual(len(win.pets()), 1)
            pet = win.roster.add("broken")                             # 以前添的、后来文件坏了
            s.pet_changed()
            self.frames(30)
            s.strip.go(1)
            self.assertLess(win.dog_opacity, 1.0 + 1e-9)
            with self.assertLogs("window", "WARNING"):
                self.frames(60)                                        # 滑到位、换不过去、滑回来
            self.frames(60)
            restart.assert_not_called()
            self.assertEqual((win.prefs.pet_id, win.roster.current_id), ("", ""), "还是原来那只")
            self.assertEqual((s.strip.target, s.strip.center()), (0, 0), "滑动条滑回来")
            anim = win._opacity_anim
            if anim.state() == anim.State.Running:
                anim.setCurrentTime(anim.duration())                 # 还在淡：走到头
            self.assertEqual(win.dog_opacity, 1.0, "狗淡回来")
            self.assertNotEqual(win.prefs.pet_id, pet.id)

    def test_removing_skips_a_neighbour_that_cannot_be_read(self):
        """删现在这只、旁边那只的模型读不出来：往另一边找一只读得出来的；都读不出来就不删（不留一只换不过去的空着）。"""
        import tempfile
        from pathlib import Path
        from widget import packs
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        bad = Path(folder.name) / "bad.glb"
        bad.write_bytes(b"not a glb")
        win = self.win
        broken = self.other_pack(id="broken", model=bad)
        with mock.patch.object(packs, "pets", return_value=[win.pack, broken]), mock.patch.object(win, "restart") as restart:
            middle = win.add_pet(packs.DEFAULT_PET, "奶茶")
            right = win.roster.add("broken")
            with self.assertLogs("kits", "ERROR"):
                win.remove_pet(middle)                                 # 右边那只读不出来：换到左边那只
            self.assertEqual((win.prefs.pet_id, [p.id for p in win.pets()]), ("", ["", right.id]))
            win.remove_pet(right.id)                                   # 删的不是现在这只：照删
            only = win.add_pet(packs.DEFAULT_PET, "芝麻")
            win.remove_pet("")
            again = win.roster.add("broken")
            with self.assertLogs("window", "WARNING"):
                win.remove_pet(only)                                   # 剩下的那只读不出来：不删
            self.assertEqual((win.prefs.pet_id, [p.id for p in win.pets()]), (only, [only, again.id]))
            restart.assert_not_called()

    def test_an_unexpected_error_halfway_falls_back_to_a_restart(self):
        """换到一半出了没想到的错：记日志、退回重启（名单已经存好，重启上来就是新那只）。"""
        from widget import packs
        win = self.win
        other = self.other_pack()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]), mock.patch.object(win, "restart") as restart, \
                mock.patch.object(win.playground, "pet_arrived", side_effect=RuntimeError("boom")), self.assertLogs("window", "ERROR"):
            win.kits.get(other)
            win.add_pet("other", "")
        restart.assert_called_once()
        self.assertEqual(win.settings.values["pack"], "other")

    def test_the_dog_fades_the_same_way_for_another_model(self):
        """淡出淡入照旧（和同一个模型一样）：当场收起，贴图在后台出好了才淡入；滑动条到位叫的淡入这时不算。"""
        from widget import native, packs
        win = self.win
        other = self.other_pack()
        win.show()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]), mock.patch.object(win, "_fade_to") as fade_to, \
                mock.patch.object(native, "reduce_motion", return_value=False):
            win.kits.get(other)
            win.add_pet("other", "")
            self.assertEqual([c.args[0] for c in fade_to.call_args_list], [0.0], "先收起")
            self.assertTrue(win.coat_pending(), "这只的贴图在后台出")
            win.fade_dog(True)
            self.assertEqual([c.args[0] for c in fade_to.call_args_list], [0.0], "贴图没换上：不淡入")
            win.look.settle()
            self.assertTrue(win._fade_soon.isActive() or fade_to.call_args_list[-1].args[0] == 1.0, "换上了：淡入（或等新的画出来再淡入）")


class PendingSwitchTests(PetsCase):
    """别的模型还没备好就去换 / 添，不在主线程上等（等 kits.get 会让界面停最多约 0.3 秒；子进程备要 0.5 秒多）：
    记下要换去哪只，狗淡出着等、不先淡回来，备好了再换；等的时候回到现在这只就不换了；添一只的备好了再添；读不出来留在原来那只。"""

    def land(self):
        """等后台那件做完、信号回到主线程（备好了的回调在这时叫），再等下一帧（备好了以后下一帧才换，window.SWITCH_LATER_MS）。"""
        from PySide6.QtTest import QTest
        for job in list(self.win.kits._jobs.values()):
            job.result()
        self.app.processEvents()
        QTest.qWait(60)

    def test_switching_to_a_model_that_is_not_ready_does_not_wait_and_switches_once_it_is(self):
        from widget import native, packs
        win = self.win
        other = self.other_pack()
        win.show()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]), mock.patch.object(native, "reduce_motion", return_value=False):
            pet = win.roster.add("other")
            win.fade_dog(False)                                        # 滑动条滑过去的路上已经让它淡出了
            win.switch_pet(pet.id)
            self.assertEqual((win.pack.id, win.prefs.pet_id), (packs.DEFAULT_PET, ""), "没备好：先不换，也不等")
            self.assertIn("other", win.kits._jobs, "开始在后台备")
            with mock.patch.object(win, "_fade_to") as fade_to:
                win.fade_dog(True)                                     # 滑动条到位叫的淡入
            fade_to.assert_not_called()                                # 狗淡出着等，不先把原来那只淡回来
            self.land()
            self.assertEqual((win.pack.id, win.prefs.pet_id, win.roster.current_id), ("other", pet.id, pet.id), "备好了：换过去")
            self.assertIsNone(win._pending_pet)

    def test_going_back_before_the_model_is_ready_keeps_the_one_you_have(self):
        from widget import packs
        win = self.win
        other = self.other_pack()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]):
            pet = win.roster.add("other")
            win.switch_pet(pet.id)
            win.cancel_switch()                                        # 滑动条又回到现在这只（petstrip._commit）
            self.land()
            self.assertEqual((win.pack.id, win.prefs.pet_id), (packs.DEFAULT_PET, ""), "回来了：不换")
            self.assertTrue(win.kits.ready("other"), "备好的留着，下次去就是热的")

    def test_the_last_one_asked_for_wins(self):
        from widget import packs
        win = self.win
        other = self.other_pack()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]):
            first = win.roster.add("other")
            second = win.roster.add("other")
            win.switch_pet(first.id)
            win.switch_pet(second.id)                                  # 等的时候又滑到了另一只
            self.land()
            self.assertEqual(win.prefs.pet_id, second.id)

    def test_adding_a_model_that_is_not_ready_adds_it_once_it_is(self):
        from widget import packs
        win = self.win
        other = self.other_pack()
        got = []
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]):
            self.assertIsNone(win.add_pet("other", "Bo", then=got.append), "没备好：先不添")
            self.assertEqual(len(win.pets()), 1)
            self.land()
            pets = win.pets()
            self.assertEqual(len(pets), 2, "备好了：添进名单")
            self.assertEqual((win.prefs.pet_id, win.pack.id, win.dog_name), (pets[1].id, "other", "Bo"), "马上换过去")
            self.assertEqual(got, [pets[1].id], "卡片那边让它从桌沿后面冒出来")

    def test_a_model_that_turns_out_unreadable_while_waiting_keeps_the_one_you_have(self):
        import tempfile
        from pathlib import Path
        from widget import packs
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        bad = Path(folder.name) / "bad.glb"
        bad.write_bytes(b"not a glb")
        win = self.win
        broken = self.other_pack(id="broken", model=bad)
        with mock.patch.object(packs, "pets", return_value=[win.pack, broken]), mock.patch.object(win, "restart") as restart:
            pet = win.roster.add("broken")
            with self.assertLogs("kits", "ERROR"), self.assertLogs("window", "WARNING"):
                win.switch_pet(pet.id)
                self.land()                                            # 读不出来：留在原来那只，滑动条滑回来（_stay）
            self.assertEqual((win.pack.id, win.prefs.pet_id), (packs.DEFAULT_PET, ""))
            self.assertIsNone(win._pending_pet)
            restart.assert_not_called()
            self.assertIsNone(win.add_pet("broken", "x"), "读坏了的添不进去")
            self.land()
            self.assertEqual(len(win.pets()), 2, "名单里还是原来那两只（以前添的那只留着）")


class AnotherModelCardTests(PetsCase):
    """换到别的模型以后卡片跟上：详情页的毛色那一行、自定义毛色页、开发者设置页照新模型重建；滑动条上原来是缩略图的那只照真的画；
    别的模型在卡片打开 0.4 秒后、滑动条要去它、添加页选它的时候就开始在后台备。"""
    NOTES = tuple({"name": {"en": n}} for n in ("Snow", "Cream", "Biscuit", "Ice"))

    def test_the_coat_row_the_custom_page_and_tuning_follow_the_new_model(self):
        from widget import packs
        win, s = self.win, self.settings
        other = self.other_pack(custom_coat=False, coat_notes=self.NOTES)
        self.assertTrue(s.pet_page.isAncestorOf(s.custom_swatch), "边牧能自定义：毛色那一行有「自定义」那一格")
        old_pet, old_coat, old_tuning = s.pet_page, s.coat_page, s.tuning_page
        s.show()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]):
            win.kits.get(other)
            win.add_pet("other", "")
            self.assertEqual(s._stale, {"pet", "coat", "tuning"}, "照上一个模型建的三页：过期")
            self.assertIs(s.pet_page, old_pet, "贴图换上之前不动（不占换的那一下）")
            with mock.patch.object(win.look, "coat_image", side_effect=AssertionError("重建时不在主线程上解贴图")):
                from PySide6.QtTest import QTest
                win.look.settle()                                  # 贴图换上 → 下一轮事件循环里重建详情页，再下一帧自定义毛色页
                self.app.processEvents()
                QTest.qWait(60)
            self.assertEqual(s._stale, {"tuning"}, "开发者设置页进去时才重建")
            self.assertIsNot(s.pet_page, old_pet)
            self.assertIsNot(s.coat_page, old_coat)
            self.assertEqual([label.text() for label in s.coat_labels], ["Snow", "Cream", "Biscuit", "Ice"], "毛色的名字是新包的")
            self.assertFalse(s.pet_page.isAncestorOf(s.custom_swatch), "不能自定义：没有「自定义」那一格")
            self.assertEqual(s.pages["pet"].widget, s.pet_page)
            self.assertEqual((s.pages["coat"].widget, s.pages["coat"].enter), (s.coat_page, s.coat_page.on_show))
            self.assertGreaterEqual(s.body.indexOf(s.pet_page), 0, "新的那一页放在卡片里原来的位置")
            s.show_page("tuning", animated=False)
            self.assertIsNot(s.tuning_page, old_tuning)
            page = s.tuning_page
            self.assertEqual(page.targets[page.current][1].pack.id, "other", "开发者设置页进来选的是新包")
            self.assertIs(page.targets[page.current][1], win.tuning, "就是在用的那一份")
            self.assertEqual(s._stale, set())
            self.assertTrue(s.tuning_page.isAncestorOf(s.meta), "显示元数据那一行跟着搬过来")
            s.show_page("main", animated=False)
            win.switch_pet(win.pets()[0].id)
            win.look.settle()
            self.app.processEvents()
            QTest.qWait(60)
            self.assertTrue(s.pet_page.isAncestorOf(s.custom_swatch), "换回边牧：「自定义」又回来")
            self.assertEqual(s.coat_labels[0].text(), win.coat_label(1))

    def test_a_sticker_drawn_from_the_thumbnail_is_redrawn_once_its_model_is_in_use(self):
        from widget import packs
        win, s = self.win, self.settings
        other = self.other_pack()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]):
            pet = win.roster.add("other")
            s.pet_changed()
            strip = s.strip
            strip._render_missing()
            before = strip._stickers[pet.id][0]
            self.assertFalse(win.pet_drawable(pet), "别的模型：缩略图")
            self.assertEqual(before, strip._signature(pet), "记好了，不反复试")
            win.kits.get(other)
            win.switch_pet(pet.id)
            win.look.settle()
            self.assertTrue(win.pet_drawable(pet))
            self.assertNotEqual(strip._stickers.get(pet.id, (None, None))[0], strip._signature(pet), "换过去了：记成要照真的重画")

    def test_another_models_deskmate_gets_a_sticker_of_its_own_coat_once_its_model_is_ready(self):
        """别的模型的同桌在滑动条上也照它自己的毛色画——它的模型在后台备好了就画（另起一套照它的模型建的渲染器、画完放掉，
        毛色照那个包的），没备好先用模型包的缩略图；备好了签名跟着变、重画。"""
        from PySide6.QtGui import QImage
        from widget import packs
        win, s = self.win, self.settings
        other = self.other_pack()
        with mock.patch.object(packs, "pets", return_value=[win.pack, other]):
            pet = win.roster.add("other")
            win.pet_prefs(pet).set("coat", 2)
            s.pet_changed()
            before = s.strip._signature(pet)
            self.assertFalse(win.pet_drawable(pet), "模型还没备：缩略图")
            self.assertEqual(win.pet_shots([pet], 64, 100.0, 10.0), {})
            kit = win.kits.get(other)
            self.assertTrue(win.pet_drawable(pet))
            self.assertNotEqual(s.strip._signature(pet), before, "备好了：照真的重画")
            shots = []

            def shoot(frame, w, h, dpr=1.0, coat=None, shooter=None):
                shots.append((coat, shooter))
                img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
                img.fill(0)
                return img
            with mock.patch.object(win.view, "ready", return_value=True), mock.patch.object(win.view, "shoot", side_effect=shoot):
                out = win.pet_shots([pet], 64, 100.0, 10.0)
            self.assertEqual(list(out), [pet.id])
            coat, shooter = shots[0]
            self.assertIs(shooter.model, kit.model, "照它自己的模型画")
            self.assertIsNone(shooter.rhi, "那套渲染器画完放掉")
            if win.coat_available()[1]:
                self.assertFalse(coat is None or coat.isNull(), "它自己记的第 2 套，照那个包的贴图文件")

    def test_other_models_are_prepared_early(self):
        """卡片打开 0.4 秒后备名单里的别的模型（离现在这只近的先）、滑动条要去那只的时候、添加页选那一格的时候。"""
        from PySide6.QtTest import QTest
        from widget import packs
        win, s = self.win, self.settings
        near, far = self.other_pack(id="near"), self.other_pack(id="far")
        with mock.patch.object(packs, "pets", return_value=[win.pack, near, far]), mock.patch.object(win.kits, "want") as want:
            win.roster.add("far")
            win.roster.add("near")
            s.pet_changed()
            s.show()
            self.assertEqual(want.call_args_list, [], "开场动画还在走：先不备")
            import time as _time
            deadline = _time.monotonic() + 2.0                         # 0.4 秒后那一下：等到它为止（全部一起跑时事件循环忙，固定等 0.5 秒偶尔赶不上）
            while want.call_count < 2 and _time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertEqual([c.args[0].id for c in want.call_args_list], ["far", "near"], "名单里离现在这只近的先")
            want.reset_mock()
            s.strip.go(2)
            self.assertEqual([c.args[0].id for c in want.call_args_list], ["near"], "滑动条要去的那只")
            want.reset_mock()
            s._pick_add("far")
            self.assertEqual([c.args[0].id for c in want.call_args_list], ["far"], "添加页选的那一格")
            want.reset_mock()
            s._pick_add(win.pack.id)
            self.assertEqual(want.call_args_list, [], "现在这个模型：不用备")


class PetStripTests(PetsCase):
    def setUp(self):
        super().setUp()
        self.settings.show()
        self.app.processEvents()
        self.settings.finish_page_anim()
        self.strip = self.settings.strip

    def at(self, slot: float, above: float = 30.0):
        """第 slot 格的狗身上那一点（滑动条自己的坐标）。"""
        from widget.petstrip import RADIUS, STEP
        return self.strip.at((slot - self.strip.pos) * STEP, RADIUS + above)

    def click(self, point, release: bool = True) -> None:
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        strip = self.strip
        g = QPointF(strip.mapToGlobal(point.toPoint()))
        strip.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, point, g, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        if release:
            strip.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, point, g, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

    def wheel(self, pixel=(0, 0), angle=None, phase=None, t=0, precise=True):
        """给滑动条一个滚动事件（照 macOS 上 Qt 给的样子，见 widget/wheel.py）。precise：精确位移（触摸板、平滑滚动的鼠标，角度 = 2 × 像素）；
        带格的滚轮传 precise=False 和 angle。t：事件时间戳（毫秒），0 = 没有（滑动条改看现在的钟），所以连续滚动的从 1000 起。"""
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        at = QPointF(140, 60)
        px = QPoint(*pixel)
        ang = QPoint(*angle) if angle is not None else px * 2
        e = QWheelEvent(at, QPointF(self.strip.mapToGlobal(at.toPoint())), px, ang, Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase if phase is None else phase, False,
                        Qt.MouseEventSynthesizedBySystem if precise else Qt.MouseEventNotSynthesized)
        e.setTimestamp(t)
        self.strip.wheelEvent(e)
        return e

    def test_the_top_bar_sits_above_the_strip_and_the_dogs_moved_down_30(self):
        """名字在顶部栏（card.TitleBar，每一页同一条，不放进滑动条），「我的同桌」紧贴在它下面、只画桌沿那一带；
        狗那一排比原来往下 30（桌沿中线 80 → 110、第一行 140 → 170），再往下 4（碰到名字胶囊了，桌沿中线 114）。"""
        from PySide6.QtCore import QPoint
        from widget import petstrip
        s, strip, bar = self.settings, self.strip, self.settings._tag

        def main(w) -> QPoint:
            return w.mapTo(s._main, QPoint(0, 0))
        self.assertIs(bar.parentWidget(), s._main, "顶部栏在卡片自己的标题行里")
        self.assertIs(s._close.parentWidget(), s._main)
        self.assertEqual(main(s._close), QPoint(312 - 16 - 26, 16), "× 还在右上角，离上边、右边 16")
        self.assertEqual((main(s.back), s.back.width(), bar.lead_mode), (QPoint(16, 16), 26, "mark"), "左边的圆：和 × 一样大、顶齐平、离边一样 16，主页面是 app 图标")
        tag = bar.tag_rect()
        self.assertEqual(main(bar).y() + tag.top(), 16, "名字胶囊的顶也离上边 16")
        self.assertAlmostEqual(main(bar).x() + tag.center().x(), 16 + 280 / 2, delta=1, msg="名字胶囊在内容区正中：和下面正中那只一条线")
        self.assertEqual(bar.text(), "Milo", "写的是正中那只的名字")
        self.assertEqual(main(strip), QPoint(16, 42), "滑动条紧贴顶部栏下面")
        self.assertEqual((strip.width(), strip.height()), (280, petstrip.HEIGHT + petstrip.GAP))
        self.assertEqual(strip.height(), 132)
        self.assertEqual(main(strip).y() + strip.yc(), 114, "桌沿中线在 114")
        self.assertEqual(petstrip.YC - petstrip.VISIBLE, 12, "正中那只头顶离顶部栏 12")
        first_row = main(s.dynamic).y()
        self.assertLessEqual(abs(first_row + s.dynamic.height() / 2 - (42 + petstrip.HEIGHT + petstrip.GAP + 13)), 3, "第一行在它下面 12")
        self.assertEqual(strip.slots(), 2, "一只 + 最后那格「+」")
        self.assertTrue(strip.settled())
        for gone in ("chip", "back", "pill_rect", "title_geometry", "docked", "_paint_corner"):
            self.assertFalse(hasattr(strip, gone), f"滑动条里不再有 {gone}：× 、名字、返回、新版本胶囊都在顶部栏")

    def test_the_dog_in_the_middle_never_touches_the_name_above_it(self):
        """鼠标放上去（狗往外抬 3、大 4%，名字胶囊同时往上抬 3）、详情页里放大 1.25 倍，正中那只的头顶都不碰顶上的名字胶囊：
        最挤的时候也不少于原来平时的 8。量的是头顶（贴纸里描边以内）到名字胶囊下沿。"""
        from PySide6.QtCore import QPoint
        from widget import petstrip
        from widget.card import TitleBar
        s, strip, bar = self.settings, self.strip, self.settings._tag
        capsule_bottom = bar.mapTo(s._main, QPoint(0, 0)).y() + TitleBar.ROOM + TitleBar.H
        top = strip.mapTo(s._main, QPoint(0, 0)).y()
        rest = top + strip.yc() - petstrip.VISIBLE - capsule_bottom
        lifted = (top + strip.yc() - petstrip.LIFT_PX - petstrip.VISIBLE * petstrip.LIFT_SCALE) - (capsule_bottom - petstrip.LIFT_PX)
        self.assertEqual(rest, 12, "平时离名字 12")
        self.assertGreaterEqual(lifted, 8, "鼠标放上去、两样一起抬：还有 8 以上")
        s.show_page("pet", animated=False)
        self.frames(90)
        self.assertEqual(strip.gone(), 1.0)
        focused = top + strip.yc() - petstrip.VISIBLE * petstrip.FOCUS_SCALE - capsule_bottom
        self.assertGreaterEqual(focused, 8, "详情页放大 1.25：还有 8 以上")
        self.assertGreaterEqual(strip.yc() - petstrip.VISIBLE * petstrip.FOCUS_SCALE - 2.5, 0.0, "描边也不出这一条")

    def test_the_dots_under_the_desk_only_navigate(self):
        """小圆点只导航，和点旁边那只一样——点别的同桌的点：转过去、换成它，停在主页面，不进详情页；点「+」的点：转到「+」，
        不进添加页；点正中那只自己的点：不动。点的范围比点本身大（整排最宽才 88）；详情页上点不到。
        悬停：别的点慢慢长大一圈、变深（和狗抬起来同一根弹簧）；正中那只自己的点悬停不变。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import petstrip
        pets = self.three()
        strip, s, win = self.strip, self.settings, self.win
        xs, gap, y = strip._dot_xs()
        self.assertEqual(len(xs), 4, "三只 + 「+」")
        self.assertEqual(strip.dot_at(QPointF(xs[2], y)), 2)
        self.assertEqual(strip.dot_at(QPointF(xs[2] + gap / 2 - 0.5, y + petstrip.DOT_HIT_H / 2 - 0.5)), 2, "比点本身大：左右到一半、上下 9")
        self.assertEqual(strip.dot_at(QPointF(xs[0] - gap / 2 - petstrip.DOT_HIT_OUT + 1, y)), 0, "两头再往外 8")
        self.assertIsNone(strip.dot_at(QPointF(xs[0], y + petstrip.DOT_HIT_H)), "离得太远不算")

        def move(point):
            strip.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, point, QPointF(strip.mapToGlobal(point.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))

        self.assertEqual(win.prefs.pet_id, pets[1].id)
        move(QPointF(xs[1], y))
        self.frames(30)
        self.assertEqual(strip.dot_hover(1), 0.0, "正中那只自己的点：悬停不变")
        move(QPointF(xs[2], y))
        self.assertLess(strip.dot_hover(2), 0.5, "慢慢长，不是一下跳过去")
        self.frames(30)
        self.assertEqual(strip.dot_hover(2), 1.0, "停稳了长到头")
        self.click(QPointF(xs[2], y))
        self.frames(90)
        self.assertEqual(win.prefs.pet_id, pets[2].id, "换成芝麻")
        self.assertEqual(s.page, "main", "只转过去，不进详情页")
        self.assertEqual(s._tag.text(), "芝麻")
        xs, gap, y = strip._dot_xs()
        self.click(QPointF(xs[2], y))
        self.frames(30)
        self.assertEqual(s.page, "main", "点正中那只的点：不动")
        self.assertEqual(strip.target, 2)
        self.click(QPointF(xs[-1], y))
        self.frames(90)
        self.assertEqual(s.page, "main", "点「+」的点：只转到「+」，不进添加页")
        self.assertEqual(strip.target, len(pets), "停在「+」上")
        self.assertEqual(win.prefs.pet_id, pets[2].id, "现在这只不换")
        s.show_page("pet", animated=False)
        s.finish_page_anim()
        self.frames(30)
        xs, gap, y = strip._dot_xs()
        self.assertIsNone(strip.dot_at(QPointF(xs[2], y)), "详情页上小圆点淡掉了，点不到")

    def test_clicking_a_neighbour_slides_there_ticks_and_switches_as_it_gets_there(self):
        """点旁边那只：滑过去，每过一只 tick 一声；点的那一刻桌面上的狗开始淡出，滑到位就换、再淡入（立马切，不等半秒）。
        顶部栏的名字跟着正中那一格换（过一半就换）：旧字先淡出再淡入新字，一直只有一行、浓淡一帧只变一点，胶囊不跑。"""
        from widget import sounds
        pets = self.three()
        strip, win, s, bar = self.strip, self.win, self.settings, self.settings._tag
        self.assertEqual((strip.target, strip.pos), (1, 1.0))
        self.assertEqual(strip.names, ["Milo", "奶茶", "芝麻"])
        self.assertEqual(strip.slot_at(self.at(1)), 1)
        self.assertEqual(strip.slot_at(self.at(2)), 2)
        self.assertEqual(strip.slot_at(self.at(3)), None, "「+」在两格以外，淡没了，点不到")
        step = 2 / 60 / bar.TEXT_FADE_S + 1e-6
        centre = bar.left.value + bar.tag.value / 2
        with mock.patch.object(sounds, "play") as play, mock.patch.object(win, "fade_dog") as fade:
            self.click(self.at(2))
            self.assertEqual(strip.target, 2)
            self.assertEqual(fade.call_args_list, [mock.call(False)], "点下去那一刻狗就开始淡出")
            seen, switched, drawn = [], None, [(bar._drawn_text, bar._drawn_alpha)]
            for i in range(40):
                s.frame_step(s.clock._last + 1 / 60, 1 / 60)
                seen.append(strip.pos)
                drawn.append((bar._drawn_text, bar._drawn_alpha))
                self.assertTrue(bar.isVisible(), "顶部栏一直在")
                self.assertEqual(bar.text(), "芝麻" if round(strip.pos) == 2 else "奶茶", "顶部栏写正中那一格的名字：过一半就换")
                self.assertAlmostEqual(bar.left.value + bar.tag.value / 2, centre, delta=0.6, msg="胶囊不跑")
                if i == 5:
                    self.assertEqual(win.dog_name, "奶茶", "还在路上：没换")
                if switched is None and win.dog_name == "芝麻":
                    switched = (i, strip.pos)
            for (t0, a0), (t1, a1) in zip(drawn, drawn[1:]):
                self.assertLessEqual(abs(a1 - a0), step, "字的浓淡一帧只变一点：不跳、不闪")
                if t1 != t0:
                    self.assertEqual(a1, 0.0, "旧字淡没了才换新字：两行不叠")
            self.assertEqual(drawn[-1], ("芝麻", 1.0))
            self.assertLess(2.0 - switched[1], 0.01, "离停的地方不到 1 像素就换")
            self.assertGreater(2.0 - switched[1], 0.0, "不等弹簧走完最后那一点")
            self.assertLessEqual((switched[0] + 1) / 60, 0.32, "点下去约 0.3 秒就换了")
            self.assertEqual(fade.call_args_list[1:3], [mock.call(False, 0.0), mock.call(True, delay=mock.ANY)], "换的那一下狗是看不见的，换好再淡入")
            self.assertEqual(fade.call_args_list[-1], mock.call(True))
            self.assertTrue(all(b >= a - 1e-9 for a, b in zip(seen, seen[1:])), "一路滑过去，不回弹")
            self.assertLess(max(b - a for a, b in zip([1.0] + seen, seen)), 0.2, "每帧只挪一点")
            self.assertEqual(strip.pos, 2.0)
            self.assertEqual([c.args[0] for c in play.call_args_list], ["tick"], "过了一只：tick 一声")
        self.assertEqual(win.dog_name, "芝麻", "停下时已经换好了")
        self.assertEqual(win.prefs.pet_id, pets[2].id)
        self.assertTrue(strip.settled())
        self.assertEqual(s._title_label.text(), "芝麻")

    def test_passing_through_does_not_switch_one_by_one(self):
        self.three()
        strip, win = self.strip, self.win
        with mock.patch.object(win, "switch_pet") as switch, mock.patch.object(win, "fade_dog") as fade:
            strip.go(2)
            self.frames(10)
            strip.go(0)                                                # 还没停稳又往回滑
            self.frames(8)
            switch.assert_not_called()                                 # 一路滑过去的（芝麻、中间的奶茶）都不换
            self.frames(60)
            self.assertEqual(strip.pos, 0.0)
            self.assertEqual({c.args for c in switch.call_args_list}, {(win.pets()[0].id,)}, "只换最后停的那只")
            self.assertLessEqual(switch.call_count, 2, "没换成的（这里是假的 switch_pet）快到时试一次、停稳再试一次，不是每帧都试")
            strip.go(2)
            self.frames(5)
            strip.go(1)                                                # 折回现在这只（奶茶）
            self.assertEqual(fade.call_args_list[-1], mock.call(True), "不换了：狗淡回来")

    def test_a_notched_wheel_goes_one_deskmate_per_notch(self):
        """滚轮、触摸板都是「一次动作换一只」（widget/wheel.py 有完整的规矩，这里测滑动条接上了）：带格的滚轮一格一只，到头不动。"""
        self.three()
        strip = self.strip
        self.assertFalse(hasattr(strip, "_scroll_end"), "不按「停 0.14 秒算松手」")
        self.assertTrue(self.wheel(angle=(0, -120), precise=False).isAccepted(), "滚轮归它：卡片不跟着滚")
        self.assertEqual(strip.target, 2, "往下滚一格：下一只")
        self.wheel(pixel=(0, -20), angle=(0, -120), precise=False, t=1008)
        self.assertEqual(strip.target, 3, "macOS 上带格的也带 pixelDelta：照样一格一只，转快了也不并")
        self.wheel(angle=(0, 120), precise=False)
        self.wheel(angle=(120, 0), precise=False)
        self.assertEqual(strip.target, 1, "往上、往右各一格：回两只")
        self.wheel(angle=(0, 240), precise=False)
        self.assertEqual(strip.target, 0, "一下两格：到头就停在第一只，不回弹")
        self.frames(60)
        self.assertEqual(strip.pos, 0.0)
        self.click(self.at(1), release=False)                         # 正按着鼠标
        self.wheel(angle=(0, -120), precise=False)
        self.assertEqual(strip.target, 0, "按着鼠标时不翻：不和拖打架")
        self.click(self.at(1))
        self.assertEqual(strip.target, 1, "松开还是一次点：转到旁边那只")

    def test_one_trackpad_swipe_is_one_deskmate_and_its_momentum_never_adds_one(self):
        """触摸板随手一划（不跟着手指走：跟着走会一下划过三四只，停一下就换一次同桌）：攒到 20 像素翻一只，剩下的连惯性都不要；
        滑过去和点旁边那只一样，用不回弹的弹簧转过去，到位才换，所以狗只淡出一次、只换一次。"""
        from PySide6.QtCore import Qt
        pets = self.three()
        strip, win = self.strip, self.win
        t = 1000
        with mock.patch.object(win, "switch_pet", wraps=win.switch_pet) as switch, mock.patch.object(win, "fade_dog") as fade:
            self.wheel(phase=Qt.ScrollBegin, t=t)
            self.wheel(pixel=(-8, 1), phase=Qt.ScrollUpdate, t=t + 8)
            self.wheel(pixel=(-10, 0), phase=Qt.ScrollUpdate, t=t + 16)
            self.assertEqual((strip.target, strip.pos), (1, 1.0), "不跟着手指走：不到 20 像素不动")
            self.wheel(pixel=(-12, -2), phase=Qt.ScrollUpdate, t=t + 24)
            self.assertEqual(strip.target, 2, "攒到 30：翻一只")
            for i, d in enumerate((-40, -60, -70)):
                self.wheel(pixel=(d, 0), phase=Qt.ScrollUpdate, t=t + 32 + 8 * i)
            self.wheel(pixel=(-60, 0), phase=Qt.ScrollUpdate, t=t + 64)            # 惯性的第一个报成 ScrollUpdate（前面的 ScrollEnd 被吞了）
            for i, d in enumerate((-50, -30, -18, -9, -4, -1, 0, 0)):
                self.wheel(pixel=(d, 0), phase=Qt.ScrollMomentum, t=t + 80 + 16 * i)
                self.frames(1)
            self.wheel(phase=Qt.ScrollEnd, t=t + 220)
            self.assertEqual(strip.target, 2, "这一下剩下的、惯性都不再翻")
            self.frames(60)
            self.assertEqual(strip.pos, 2.0)
            self.assertEqual(win.prefs.pet_id, pets[2].id)
            self.assertEqual(switch.call_count, 1, "只换一次同桌")
            self.assertEqual(fade.call_args_list.count(mock.call(False)), 1, "狗只淡出一次")
        self.wheel(pixel=(-40, 0), phase=Qt.ScrollMomentum, t=t + 620)
        self.assertEqual(strip.target, 2, "停了一会儿才到的惯性：开不了新的一次")
        self.wheel(phase=Qt.ScrollBegin, t=t + 2000)
        self.wheel(pixel=(30, 0), phase=Qt.ScrollUpdate, t=t + 2008)
        self.assertEqual(strip.target, 1, "下一次（手指重新放上去）：往右划回前一只")

    def test_dragging_on_the_table_slides_and_dragging_elsewhere_moves_the_card(self):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget.petstrip import SLOT_PX
        self.three()
        strip = self.strip

        def event(kind, point, buttons=Qt.LeftButton):
            return QMouseEvent(kind, point, QPointF(strip.mapToGlobal(point.toPoint())), Qt.LeftButton, buttons, Qt.NoModifier)
        corner = event(QEvent.MouseButtonPress, QPointF(20, 10))
        strip.mousePressEvent(corner)
        self.assertFalse(corner.isAccepted(), "桌沿上面的空白：不归它，卡片照旧能拖")
        start = self.at(1)
        strip.mousePressEvent(event(QEvent.MouseButtonPress, start))
        strip.mouseMoveEvent(event(QEvent.MouseMove, start + QPointF(-2, 0)))
        self.assertEqual(strip.pos, 1.0, "挪 2 像素还不算拖")
        strip.mouseMoveEvent(event(QEvent.MouseMove, start + QPointF(-SLOT_PX * 0.7, 0)))
        self.assertAlmostEqual(strip.pos, 1.7, delta=0.01, msg="往左拖：后面的过来，狗差不多跟着手")
        strip.mouseMoveEvent(event(QEvent.MouseMove, start + QPointF(-SLOT_PX * 5, 0)))
        self.assertAlmostEqual(strip.pos, strip.slots() - 1 + 0.22, delta=0.01, msg="拖过头只让一点")
        strip.mouseReleaseEvent(event(QEvent.MouseButtonRelease, start + QPointF(-SLOT_PX * 5, 0), Qt.NoButton))
        self.assertEqual(strip.target, 3, "松手：吸到最近的一格（「+」）")
        self.frames(60)
        self.assertEqual(strip.pos, 3.0)
        self.assertEqual(self.win.dog_name, "奶茶", "停在「+」上：不换同桌")

    def test_the_plus_turns_to_the_middle_first_and_then_opens_the_add_page(self):
        """「+」和同桌一个规矩——在旁边时点它只转到正中，到了正中再点才进添加页。
        停在「+」上时顶部栏写「添加同桌」，画成描边标签（不是名字，样子也不像名字）；点它和点「+」一样。"""
        from widget import petstrip, sounds
        strip, s, win, bar = self.strip, self.settings, self.win, self.settings._tag
        with mock.patch.object(sounds, "play") as play:
            self.click(self.at(1, above=14.0))                         # 旁边的「+」
        self.assertEqual((s.page, strip.target), ("main", 1), "只转到正中")
        self.assertNotIn(mock.call("tap"), play.call_args_list)
        self.frames(60)
        self.assertEqual(strip.pos, 1.0)
        self.assertEqual(win.dog_name, "Milo", "停在「+」上：不换同桌")
        s.finish_page_anim()
        self.assertEqual((bar.text(), bar.outlined), ("Add a deskmate", True), "顶部栏：描边的「添加同桌」")
        self.click(self.at(1, above=14.0))                             # 到了正中再点
        self.assertEqual(s.page, "add")
        s.finish_page_anim()
        self.assertEqual((s._title_label.text(), bar.outlined), ("Add a deskmate", False), "添加页的标题是页名：字加粗")
        self.assertIs(bar.parentWidget(), s._main, "顶部栏还是那一条")
        self.assertEqual(bar.lead_mode, "back")
        self.assertTrue(strip.isHidden(), "别的页上没有那一条")
        self.assertEqual(len(s.add_tiles), len(s.pets))
        self.assertTrue(s.add_tiles[0].selected)
        self.assertEqual(s.add_name.placeholderText(), "Milo", "不填就用模型自己的名字")
        s.add_name.setText("奶茶")
        s.add_button.click()
        self.assertEqual(s.page, "main")
        self.assertEqual([win.pet_name(p) for p in win.pets()], ["Milo", "奶茶"])
        self.assertEqual(win.dog_name, "奶茶")
        self.assertEqual(strip.target, 1, "要滑到新来的那只")
        self.assertEqual(strip._rising, win.pets()[1].id, "它从桌沿后面冒出来")
        self.assertEqual(strip._rise.value, 0.0)
        self.assertEqual((strip._gap_at, strip._gap.value), (2, -1.0), "「+」还在它原来那一格，往右让")
        self.assertAlmostEqual(strip.coord(2) - strip.pos, 1.0, msg="「+」还在刚才的位置（正中右边一格）")
        self.assertAlmostEqual(strip.coord(1) - strip.pos, 1.0, msg="新来的就从「+」那个座位冒出来")
        self.assertFalse(strip.settled(), "还没坐稳")
        strip.tick(petstrip.RISE_DELAY_S / 2)
        self.assertEqual(strip._rise.value, 0.0, "等换页淡入过半再冒")
        s.finish_page_anim()
        self.frames(90)
        self.assertEqual(strip.pos, 1.0)
        self.assertIsNone(strip._rising)
        self.assertEqual((strip._gap_at, strip._gap.value), (petstrip.NO_GAP, 0.0))
        self.assertTrue(strip.settled())
        self.assertEqual((s._title_label.text(), bar.outlined), ("奶茶", False))
        self.click(self.at(2, above=14.0))                             # 「+」在右边一格：先转过去
        self.assertEqual(s.page, "main")
        self.frames(60)
        self.assertEqual(bar.text(), "Add a deskmate")
        self._press_title()                                            # 顶部栏的「添加同桌」也能点：和点正中的「+」一样
        self.assertEqual(s.page, "add")
        s.finish_page_anim()
        s.add_button.click()                                           # 不起名字
        self.assertEqual(win.dog_name, "Milo")
        self.assertEqual(len(win.pets()), 3)

    def _press_title(self) -> None:
        """在顶部栏的名字胶囊上按下、松开（主页面：松开时还在胶囊上才算点）。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        bar = self.settings._tag
        at = bar.tag_rect().center()
        g = QPointF(bar.mapToGlobal(at.toPoint()))
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseButtonPress, at, g, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseButtonRelease, at, g, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

    def test_clicking_the_one_in_the_middle_opens_its_page_on_the_same_table(self):
        """点一下正中那只进它的详情页（毛色、删除都在那）；顶上还是这一条，它放大一圈，别的退开。"""
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import petstrip
        self.three()
        strip, s, win, bar = self.strip, self.settings, self.win, self.settings._tag
        height = strip.height()
        self.assertEqual(height, petstrip.HEIGHT + petstrip.GAP)
        self.click(self.at(1))
        self.assertEqual(s.page, "pet")
        self.assertEqual(strip._focus_to, 1.0)
        self.assertLess(strip.gone(), 1.0, "放大、退开是动画")
        self.assertIs(bar.parentWidget(), s._main, "顶部栏还是那一条，不搬家")
        self.assertIs(s._close.parentWidget(), s._main)
        s.finish_page_anim()
        self.frames(90)
        self.assertEqual(strip.gone(), 1.0)
        self.assertFalse(strip.isHidden())
        self.assertEqual(strip.height(), height, "这一条不变高：桌沿往下坐进空着的那 12")
        self.assertGreaterEqual(strip.yc() - petstrip.VISIBLE * petstrip.FOCUS_SCALE, 0.0, "放大的那只头不出这一条")
        self.assertEqual(strip._aside(), 0.0, "别的同桌、「+」、小圆点都淡掉了")
        self.assertEqual(bar.lead_mode, "back", "顶部栏左边的圆换成返回")
        self.assertEqual((s.back.mapTo(s._main, QPoint(0, 0)), s.back.mix), (QPoint(16, 16), 1.0), "还是那个圆，在原地")
        self.assertIsNone(s.back.graphicsEffect(), "返回不挂 QGraphicsOpacityEffect：换页时下面整块也挂着一层，Qt 把里面那层画偏（+17、+7）")
        self.assertTrue(strip.settled())
        self.assertFalse(s.pet_page.isHidden())
        self.assertTrue(s.main_page.isHidden())
        self.assertEqual(s._title_label.text(), "奶茶")
        s.start_rename()
        self.assertTrue(s.renaming, "详情页上点顶上的名字改名")
        s.end_rename_now()
        # 详情页上不滑：滚轮、按下都不理（按下交给卡片，照旧拖卡片）
        self.assertFalse(self.wheel(angle=(0, -120), precise=False).isAccepted(), "滚轮交给卡片")
        self.assertEqual(strip.target, 1)
        press = QMouseEvent(QEvent.MouseButtonPress, self.at(1), QPointF(strip.mapToGlobal(self.at(1).toPoint())), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        strip.mousePressEvent(press)
        self.assertFalse(press.isAccepted())
        self.assertIsNone(strip._press)
        s.back.click()
        self.assertEqual(s.page, "main")
        self.assertEqual(bar.lead_mode, "mark", "回主页面：圆里换回 app 图标")
        self.assertEqual(strip._focus_to, 0.0)
        s.finish_page_anim()
        self.frames(90)
        self.assertEqual(strip.gone(), 0.0)
        self.assertEqual(s.back.mix, 0.0)
        self.assertFalse(s.main_page.isHidden())
        s.start_rename()
        self.assertFalse(s.renaming, "主页面不能改名：点名字进详情页")
        # 进了别的页再回来、关了卡片再开：都回到一排
        self.click(self.at(1))
        s.finish_page_anim()
        win.open_coat()
        s.finish_page_anim()
        self.assertEqual(s.page, "coat")
        self.assertTrue(strip.isHidden())
        s.back.click()                                                 # 下面还在淡入淡出（返回键不能在这时往右下跳一下）
        self.assertEqual(s.page, "pet", "自定义毛色页返回的是详情页")
        self.assertIsNotNone(s._swap)
        self.assertIsNone(s.back.graphicsEffect())
        self.assertEqual((s.back.isHidden(), s.back.mapTo(s._main, QPoint(0, 0)), s.back.mix), (False, QPoint(16, 16), 1.0),
                         "从自定义毛色页回来：返回一直在原位、全浓（它在淡的内容外面）")
        self.assertEqual(strip.gone(), 1.0)
        s.hide()
        s.show()
        self.app.processEvents()
        self.assertEqual(s.page, "main")
        self.assertEqual(strip.gone(), 0.0)

    def test_the_round_icon_is_the_close_circle_with_a_bone_and_stays(self):
        """左上角的图标改成圆的——和右上角 × 同一个圆（26，顶齐平、离边一样 16），里面的 app 图标宽 14.5、填实；
        一直在（新版本胶囊不顶掉它），点了进「关于」页；别的页同一个圆里换成返回。"""
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QColor, QImage, QMouseEvent, QRegion
        from PySide6.QtWidgets import QWidget
        from widget import sticker
        from widget import marks
        s, bar = self.settings, self.settings._tag
        lead, close = s.back, s._close

        def shot(w) -> QImage:
            """2 倍屏上的样子（只画它自己，透明的地方留透明）。"""
            img = QImage(w.width() * 2, w.height() * 2, QImage.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(2.0)
            img.fill(0)
            w.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
            return img
        self.assertEqual((lead.width(), lead.height()), (close.width(), close.height()), "和 × 一样 26 见方")
        a, b = shot(lead), shot(close)
        for x, y in ((26, 2), (2, 26), (50, 26), (26, 50), (9, 9)):
            self.assertEqual(a.pixelColor(x, y), b.pixelColor(x, y), f"同一个圆：描边、底一个像素都不差（{x}, {y}）")
        self.assertEqual(a.pixelColor(1, 1).alpha(), 0, "圆外面是透明的")
        self.assertEqual(a.pixelColor(26, 26).name(), QColor(sticker.INK).name(), "正中是 app 图标（填实）")
        self.assertEqual(marks.APP_W, 14.5)
        self.assertEqual((bar.lead_mode, lead.mix), ("mark", 0.0))
        bar.set_chip("Update ready", animated=False)
        self.assertEqual((lead.isHidden(), bar.lead_mode), (False, "mark"), "新版本胶囊出来也一直在")
        self.assertFalse(lead.testAttribute(Qt.WA_TransparentForMouseEvents), "点得了：进「关于」页")
        bar.set_chip("", animated=False)
        s.show_page("pet", animated=False)
        self.assertEqual((bar.lead_mode, lead.mix, lead.testAttribute(Qt.WA_TransparentForMouseEvents)), ("back", 1.0, False), "详情页：同一个圆里是返回，能点")
        self.assertEqual(shot(lead).pixelColor(26, 2), b.pixelColor(26, 2), "换成返回时圆不变")
        s.show_page("main", animated=False)
        self.assertEqual((bar.lead_mode, lead.cursor().shape()), ("mark", Qt.PointingHandCursor))
        import config
        from widget import updater
        from widget.i18n import tr
        lead.click()
        self.assertEqual((s.page, bar.lead_mode), ("about", "back"), "点主页面圆里的 app 图标：进「关于」页，圆里换成返回")
        self.assertEqual(s.about_page.version.text(), f"{tr('Version')} {updater.version_text(config.VERSION, config.BUILD)}")
        s.finish_animations()                     # 进关于页那段走完：圆里出了返回键（动画走着时点圆照圆里画的算，画的还是 D、M 时点了接着进）
        lead.click()
        s.finish_animations()                     # 回主页面那段走完（动画先倒着走，线快回到圆里才真的换页）
        self.assertEqual((s.page, bar.lead_mode), ("main", "mark"), "返回：回主页面")

    def test_the_detail_page_is_the_coat_and_one_centred_delete(self):
        """不要「删除这只同桌」那行字，直接一颗删除键放中间；大小不绑在某一只上。"""
        from PySide6.QtCore import QPoint
        from widget.card import PAD
        self.three()
        s = self.settings
        s.show_page("pet", False)
        s.finish_page_anim()
        self.app.processEvents()
        d = s.pet_delete
        at = d.mapTo(s._main, QPoint(0, 0))
        self.assertEqual(at.x() + d.width() / 2, s._main.width() / 2, "正中")
        self.assertEqual(s._main.height() - (at.y() + d.height()), PAD, "离底边 16：和别的页最底下的按钮一样")
        self.assertGreaterEqual(d.width(), 104)
        self.assertFalse(s.size_slider.isVisibleTo(s))
        self.assertLess(s.custom_swatch.mapTo(s._main, QPoint(0, s.custom_swatch.height())).y(), at.y())

    def test_it_has_switched_by_the_time_it_stops_so_a_click_opens_the_right_page(self):
        pets = self.three()
        strip, s, win = self.strip, self.settings, self.win
        strip.go(0)
        self.frames(60)
        self.assertEqual(win.prefs.pet_id, pets[0].id, "停下时已经换过去了：详情页里改的就是桌面上这只")
        self.click(self.at(0))                                         # 这时点它
        self.assertEqual(s.page, "pet")
        self.assertEqual(s._title_label.text(), "Milo")

    def test_hovering_the_one_in_the_middle_lifts_it_together_with_its_name(self):
        """正中那只和顶部栏里它的名字胶囊是一个整体——鼠标放到狗或胶囊上，两样一起抬（同一根不回弹的弹簧：狗往外 3、大 4%，
        胶囊往上 3、不放大）；点哪个都进详情页，主页面不能改名。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from widget import petstrip
        self.three()
        strip, s, bar = self.strip, self.settings, self.settings._tag

        def hover(point) -> None:
            strip.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, point, QPointF(strip.mapToGlobal(point.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))

        def lifts(n: int = 30) -> list:
            out = []
            for _ in range(n):
                self.frames(1)
                out.append(bar._lift)
            return out
        hover(self.at(1))
        self.assertEqual(strip._lift.target, 1.0, "鼠标在正中那只上：抬一下，告诉人能点")
        self.assertEqual(strip.cursor().shape(), Qt.PointingHandCursor)
        up = lifts()
        self.assertEqual(up[-1], petstrip.LIFT_PX, "顶部栏的名字胶囊跟着一起抬 3")
        self.assertTrue(all(b >= a for a, b in zip(up, up[1:])) and max(up) <= petstrip.LIFT_PX, "一路抬上去，不过头")
        hover(self.at(0))
        self.assertEqual(strip._lift.target, 0.0)
        self.assertEqual(strip.cursor().shape(), Qt.PointingHandCursor, "旁边那只也能点（转过来）")
        hover(QPointF(4.0, 4.0))
        self.assertEqual(strip.cursor().shape(), Qt.ArrowCursor)
        hover(self.at(1))
        strip.leaveEvent(QEvent(QEvent.Leave))
        self.assertEqual(strip._lift.target, 0.0)
        self.assertEqual(lifts()[-1], 0.0)
        at = bar.tag_rect().center()
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseMove, at, QPointF(bar.mapToGlobal(at.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        self.assertTrue(bar.name_hovering)
        self.assertEqual(strip._lift.target, 1.0, "鼠标在顶部栏的名字上：正中那只一起抬")
        self.assertEqual(bar.cursor().shape(), Qt.PointingHandCursor, "点得进详情页")
        self.assertEqual(lifts()[-1], petstrip.LIFT_PX)
        self.assertEqual(bar.tag_rect().top(), bar.ROOM, "点和悬停按没抬的位置算（不然在边上来回跳）")
        QApplication.sendEvent(bar, QEvent(QEvent.Leave))
        self.assertFalse(bar.name_hovering)
        self.assertEqual(strip._lift.target, 0.0)
        self._press_title()
        self.assertEqual(s.page, "pet", "点名字胶囊：进详情页")
        self.assertFalse(s.renaming, "主页面上点名字不改名")

    def test_the_lift_eases_down_when_the_plus_opens_the_add_page(self):
        """点正中的「+」（或顶部栏的「添加同桌」）去添加页：滑动条藏起来时抬着的慢慢放下，顶部栏的胶囊一帧只落一点，不一下掉下去。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from widget import petstrip
        strip, s, bar = self.strip, self.settings, self.settings._tag
        strip.go(1)
        self.frames(60)
        plus = self.at(1, above=14.0)
        strip.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, plus, QPointF(strip.mapToGlobal(plus.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        self.frames(30)
        self.assertEqual(bar._lift, petstrip.LIFT_PX, "停在正中的「+」也和同桌一样抬起来")
        strip.activate_center()
        self.assertEqual(s.page, "add")
        self.assertTrue(strip.isHidden())
        seen = [bar._lift]
        for _ in range(30):
            self.frames(1)
            seen.append(bar._lift)
        self.assertGreater(seen[1], 1.0, "刚换页那一帧还抬着")
        self.assertEqual(seen[-1], 0.0)
        self.assertTrue(all(b <= a for a, b in zip(seen, seen[1:])), "一路落下去")
        self.assertLessEqual(max(a - b for a, b in zip(seen, seen[1:])), 0.3 * petstrip.LIFT_PX, "一帧只落一点")

    def test_a_row_of_dots_under_the_desk_marks_where_you_are(self):
        """没有「2 / 5」：桌沿下面一排小圆点，一只一个、正中那只的深，最后一个小「+」；
        整排在正中；删一只时删掉的那个点在原地淡掉，不跳；详情页上和别的同桌一起淡掉；同桌多了不伸到旁边的灰色名字下面。"""
        from PySide6.QtGui import QImage, QPainter
        from widget import petstrip
        self.three()
        strip, win = self.strip, self.win

        def marks() -> list:
            img = QImage(strip.size(), QImage.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            strip._paint_dots(p)
            p.end()
            y = round(strip.yc() + petstrip.DOT_DY)
            row = [img.pixelColor(x, y).alpha() for x in range(img.width())]
            runs, start = [], None
            for x, a in enumerate(row + [0]):
                if a > 0 and start is None:
                    start = x
                elif a == 0 and start is not None:
                    runs.append((start, x - 1, max(row[start:x]), img.pixelColor((start + x - 1) // 2, y - 4).alpha()))   # 上面 4 像素：「+」那一竖够得着，圆点够不着
                    start = None
            return runs
        got = marks()
        self.assertEqual(len(got), 4, "三只一个一个点，最后一个「+」")
        centres = [(a + b) / 2 for a, b, _, _ in got]
        self.assertAlmostEqual((centres[0] + centres[-1]) / 2, strip.width() / 2, delta=1, msg="整排在正中")
        self.assertTrue(all(abs((b - a) - petstrip.DOT_GAP) <= 1 for a, b in zip(centres, centres[1:])), "隔得一样远")
        alphas = [m[2] for m in got]
        self.assertGreater(alphas[1], max(alphas[0], alphas[2]), "正中那只（奶茶）的点最深")
        self.assertGreater(got[3][3], 0, "最后一个是「+」：竖的那一笔伸出点的上面")
        self.assertEqual(got[0][3], 0, "同桌是圆点")
        strip.go(2)
        self.frames(60)
        alphas = [m[2] for m in marks()]
        self.assertGreater(alphas[2], max(alphas[1], alphas[3]), "滑到芝麻：深的那个点跟着换")
        s = self.settings
        s.show_page("pet", animated=False)
        self.frames(60)
        self.assertEqual(marks(), [], "详情页上和别的同桌一起淡掉")
        s.show_page("main", animated=False)
        self.frames(60)
        strip.remove_current()                                         # 删芝麻（详情页里长按「删除」回到主页面以后就是这一下）
        got = marks()
        self.assertEqual(len(got), 4, "删掉的那个点还在原地淡")
        self.assertAlmostEqual(((got[0][0] + got[0][1]) / 2 + (got[-1][0] + got[-1][1]) / 2) / 2, strip.width() / 2, delta=1,
                               msg="整排的正中不跳")
        self.frames(90)
        self.assertEqual(len(marks()), 3, "淡完：两只 + 「+」")
        for i in range(8):
            win.add_pet("border_collie", f"豆{i}")
        s.finish_page_anim()
        self.frames(90)
        got = marks()
        self.assertEqual(len(got), 11)
        self.assertLessEqual(got[-1][1] - got[0][0], petstrip.DOT_SPAN + 10, "同桌多了：点挨近、变小，不伸到旁边的灰色名字下面")

    def test_delete_is_a_hold_button_on_its_page_and_the_last_one_stays(self):
        """按住狗删除是手机的做法，去掉；删除在详情页里，是一颗看得见的长按按钮，不用再问一遍。最后一只删不了。"""
        from widget import petstrip
        from widget.widgets import HoldPill
        strip, s, win = self.strip, self.settings, self.win
        self.assertFalse(hasattr(strip, "_hold_timer"))
        self.assertIsInstance(s.pet_delete, HoldPill)
        self.assertIsNot(s.pet_delete, s.delete_button, "和卸载页的「删除」是两颗按钮（重名时测试会按到卸载）")
        self.click(self.at(0))
        s.finish_page_anim()
        self.assertEqual(s.page, "pet")
        self.assertFalse(s.pet_delete.isEnabled(), "只有一只：删不了")
        s.pet_delete.held.emit()
        self.assertEqual(len(win.pets()), 1)
        s.show_page("main", False)
        pets = self.three()
        s.sync()
        self.assertTrue(s.pet_delete.isEnabled())
        self.click(self.at(1))
        s.finish_page_anim()
        self.frames(60)
        s.pet_delete.held.emit()                                    # 按满了
        self.assertEqual(s.page, "main", "先回主页面")
        self.assertEqual([win.pet_name(p) for p in win.pets()], ["Milo", "芝麻"])
        self.assertEqual(win.dog_name, "芝麻", "换成旁边那只")
        self.assertEqual(strip._leaving[1], 1, "删的那只在它原来那一格缩回桌沿后面")
        self.assertEqual(strip._leave.value, 1.0)
        self.assertEqual((strip._gap_at, strip._gap.value), (1, 1.0), "后面的还在原来的位置，补过来是动画")
        self.assertAlmostEqual(strip.coord(1) - strip.pos, 1.0)
        self.assertFalse(strip.settled())
        s.finish_page_anim()
        self.frames(90)
        self.assertIsNone(strip._leaving)
        self.assertEqual(strip._gap_at, petstrip.NO_GAP)
        self.assertEqual((strip.target, strip.pos), (1, 1.0), "停在现在这只上")
        self.assertTrue(strip.settled())
        self.assertEqual(strip.names, ["Milo", "芝麻"])
        self.click(self.at(1))                                         # 删最后面那只：正中滑到左边那只
        s.finish_page_anim()
        self.frames(60)
        s.pet_delete.held.emit()
        self.assertEqual([win.pet_name(p) for p in win.pets()], ["Milo"])
        self.assertEqual(strip.target, 0)
        s.finish_page_anim()
        self.frames(90)
        self.assertEqual((strip.target, strip.pos), (0, 0.0))
        self.assertTrue(strip.settled())
        self.assertEqual(win.prefs.pet_id, pets[0].id)

    def test_closing_the_card_finishes_a_pending_switch_and_leaves_the_plus(self):
        pets = self.three()
        strip, s, win = self.strip, self.settings, self.win
        strip.go(0)
        self.frames(3)
        self.assertEqual(win.dog_name, "奶茶")
        s.hide()                                                       # 正往 Milo 滑、还没到就关了卡片：马上换
        self.assertEqual(win.prefs.pet_id, pets[0].id)
        s.show()
        self.app.processEvents()
        s.finish_page_anim()
        self.assertEqual((strip.target, strip.pos), (0, 0.0))
        strip.go(3)
        self.frames(60)
        s.hide()                                                       # 停在「+」上关掉
        s.show()
        self.app.processEvents()
        self.assertEqual((strip.target, strip.pos), (0, 0.0), "下次打开回到现在这只")

    def test_renaming_happens_on_the_detail_page_and_the_strip_follows(self):
        """主页面不能改名（点名字进详情页）；改名只在详情页里点顶上的名字：输入框在胶囊里：胶囊一直居中、两边一起长，
        长到最宽就不长了，输入框里滚；滑动条上的名字跟着换。"""
        self.three()
        s, strip, win, bar = self.settings, self.strip, self.win, self.settings._tag
        s.start_rename()
        self.assertFalse(s.renaming, "主页面不能改名")
        s.show_page("pet", animated=False)
        s.finish_page_anim()
        s.start_rename()
        self.assertTrue(s.renaming)
        left, width = bar.left.target, bar.tag.target
        s._title_edit.setText("拿铁拿铁拿铁拿铁")
        self.assertLess(bar.left.target, left, "左边也往外长")
        self.assertGreater(bar.tag.target, width)
        self.assertAlmostEqual(bar.left.target + bar.tag.target / 2, bar._span() / 2, delta=0.6, msg="打字时一直居中")
        s._title_edit.setText("拿铁" * 12)
        self.assertEqual(bar.tag.target, bar._cap(), "长到最宽就不长了，在输入框里滚")
        self.assertAlmostEqual(bar.left.target + bar.tag.target / 2, bar._span() / 2, delta=0.6, msg="还是居中")
        s._title_edit.setText("拿铁")
        s._title_edit.editingFinished.emit()
        self.assertFalse(s.renaming)
        self.assertEqual(win.dog_name, "拿铁")
        self.assertEqual(strip.names, ["Milo", "拿铁", "芝麻"])
        s.finish_page_anim()
        self.assertAlmostEqual(bar.left.value + bar.tag.value / 2, bar._span() / 2, delta=0.6, msg="改完弹回居中")
        s.start_rename()
        s.back.click()                                                 # 改到一半点返回：先收尾
        self.assertFalse(s.renaming)
        self.assertEqual(s.page, "main")

    def test_stickers_are_cut_from_a_whole_dog(self):
        """贴纸：整只狗的图 → 头缩到 42 宽、从头顶往下留 60、描一圈；定位点在切口那条线上。没有 GL 时画一个圆点顶着，不出错。"""
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QColor, QImage, QPainter
        from widget import petstrip
        shot = QImage(400, 400, QImage.Format_ARGB32_Premultiplied)
        shot.fill(Qt.transparent)
        p = QPainter(shot)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#335577"))
        p.drawEllipse(QRectF(150, 40, 100, 90))                        # 头：宽 100
        p.drawRect(QRectF(170, 120, 60, 90))                           # 脖子
        p.drawRect(QRectF(140, 200, 160, 160))                         # 身子
        p.end()
        made = petstrip.cutout(shot, 220.0, "#111111")
        self.assertIsNotNone(made)
        k = petstrip.HEAD_W / 100.0
        self.assertAlmostEqual(made.h, petstrip.VISIBLE + 2 * petstrip.MARGIN, delta=1.0)
        self.assertAlmostEqual(made.w, 160 * k + 2 * petstrip.MARGIN, delta=1.5)
        self.assertAlmostEqual(made.anchor.y(), petstrip.MARGIN + petstrip.VISIBLE)
        self.assertAlmostEqual(made.anchor.x(), petstrip.MARGIN + ((200 - 140) * 0.5 + (220 - 140) * 0.5) * k, delta=0.5, msg="头正中和身子正中之间")
        body = made._body[4]
        edge = body.pixelColor(round((petstrip.MARGIN + 60 * k) * 4), round((petstrip.MARGIN - 1.0) * 4))   # 头顶正中的上面一点
        self.assertGreater(edge.alpha(), 200, "头顶外面有一圈描边")
        self.assertLess(edge.red(), 60)
        empty = QImage(64, 64, QImage.Format_ARGB32_Premultiplied)
        empty.fill(Qt.transparent)
        self.assertIsNone(petstrip.cutout(empty, 32.0, "#111111"))
        self.assertEqual(self.strip._stickers, {}, "单测没有 GL：贴纸没做出来")
        self.strip.grab()                                              # 画得出来（圆点顶着）


if __name__ == "__main__":
    unittest.main()
