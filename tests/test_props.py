"""道具：吃 / 喝有盆，叼着 / 捡起放下有骨头，捡回有球。球、骨头是程序生成的，盆是买来的饭盆、水盆（不在时程序画）；
什么时候出现由正在播的片段决定，两种模式一样。"""
import math
import unittest
from pathlib import Path
from unittest import mock

import config
from widget import props
from widget.props import BALL_R, BOWL_H, BOWL_R, KNOB_R, LINGER, Props

BOUGHT_FILES = [config.ROOT / "models" / "props" / f"{n}.glb" for n in ("bowl_food", "bowl_water")]


@unittest.skipUnless(all(p.is_file() for p in BOUGHT_FILES), "models/props/bowl_*.glb not present (purchased asset)")
class BoughtBowlTests(unittest.TestCase):
    """动作里的吃、喝换成买来的饭盆、水盆（灵动交互里摆的物件也是它们）。"""

    def test_the_bought_bowls_are_the_full_ones_from_the_thing_packs(self):
        got = props.bought()
        self.assertEqual(set(got), {"bowl_food", "bowl_water"})
        radius = lambda p: max(math.hypot(p[i], p[i + 2]) for i in range(0, len(p), 3))
        for name, r, top in (("bowl_food", 0.143, 0.093), ("bowl_water", 0.100, 0.070)):
            m = got[name]
            self.assertEqual(m.count % 3, 0, f"{name}：三角形")
            self.assertEqual((len(m.normals), len(m.uvs)), (len(m.positions), len(m.positions) // 3 * 2))
            self.assertAlmostEqual(radius(m.positions), r, delta=0.002, msg=f"{name}：照物件包里写的大小（灵动交互里摆的一样大）")
            self.assertAlmostEqual(min(m.positions[1::3]), 0.0, delta=0.002, msg=f"{name}：盆底贴地")
            self.assertAlmostEqual(max(m.positions[1::3]), top, delta=0.003, msg=f"{name}：满的那个样子")
            self.assertFalse(m.image.isNull())
        self.assertIs(got["bowl_food"].image, got["bowl_water"].image, "两个盆共用一张贴图，只解一次、只传一次")
        self.assertIs(props.bought(), got, "只读一次")

    def test_both_dogs_put_their_nose_into_the_bowl_and_keep_their_paws_out(self):
        """两只狗吃、喝时：鼻子最低那一刻正对盆心、比盆沿低（进了盆），前爪离盆心比盆的半径远（不踩进盆里）。"""
        from widget import packs
        from widget.anim import Player
        from widget.gltf import IDENTITY
        found = packs.discover()
        got = props.bought()
        for pid in (packs.DEFAULT_PET, "samoyed"):
            try:
                model = packs.load_model(found[pid])
            except (KeyError, OSError, ValueError):
                continue                                         # 买来的模型不在
            p = Props(model)
            paws = [model.node_by_name(n).index for n in ("foot_f.L", "foot_f.R")]
            for clip, name in (("Eat_loop", "bowl_food"), ("Drink_loop", "bowl_water")):
                m = got[name]
                rim = max(m.positions[1::3])
                r = max(math.hypot(m.positions[i], m.positions[i + 2]) for i in range(0, len(m.positions), 3))
                x, z, _ = p.spot(clip)
                player = Player(model)
                player.play(clip, loop=False, fade=0.0)
                lowest, nearest = 9.0, 9.0
                for i in range(31):
                    player.time = model.clips[clip].duration * i / 30
                    player.update(0.0)
                    g = player.globals(IDENTITY)
                    lowest = min(lowest, g[p.nose][13])
                    nearest = min(nearest, *(math.hypot(g[k][12] - x, g[k][14] - z) for k in paws))
                self.assertLess(lowest, rim + 0.01, f"{pid} {clip}：鼻子进了盆（最低 {lowest:.3f}，盆沿 {rim:.3f}）")
                self.assertGreater(lowest, 0.03, f"{pid} {clip}：没扎到盆底")
                self.assertGreater(nearest, r + 0.05, f"{pid} {clip}：前爪离盆心 {nearest:.3f}，盆半径 {r:.3f}")


class MeshTests(unittest.TestCase):
    def test_meshes_are_closed_triangle_soups_with_unit_normals(self):
        for name, m in props.meshes().items():
            self.assertGreater(m.count, 30, name)
            self.assertEqual(m.count % 3, 0, f"{name}：三角形")
            self.assertEqual(len(m.normals), len(m.positions))
            for i in range(0, len(m.normals), 3 * 37):
                n = m.normals[i:i + 3]
                self.assertAlmostEqual(math.sqrt(sum(v * v for v in n)), 1.0, places=3, msg=f"{name}：法线单位长")

    def test_sizes_match_the_dog(self):
        m = props.meshes()
        bowl, ball, bone = m["bowl"].positions, m["ball"].positions, m["bone"].positions
        radius = lambda p: max(math.hypot(p[i], p[i + 2]) for i in range(0, len(p), 3))
        self.assertAlmostEqual(radius(bowl), BOWL_R, delta=1e-6, msg="盆的最大半径")
        self.assertAlmostEqual(max(bowl[1::3]), BOWL_H, delta=1e-6, msg="盆高")
        self.assertAlmostEqual(min(bowl[1::3]), 0.0, delta=1e-6, msg="盆底贴地")
        self.assertAlmostEqual(max(ball[1::3]) - min(ball[1::3]), 2 * BALL_R, delta=1e-6, msg="球的直径")
        self.assertAlmostEqual(max(bone[0::3]) - min(bone[0::3]), props.BONE_LEN + 2 * KNOB_R, delta=1e-6, msg="骨头长 = 两球心距离 + 两个球半径")
        self.assertAlmostEqual(max(bone[1::3]), KNOB_R, delta=1e-6, msg="骨头躺着时最高点是端头球：XZ 平面里是平的")
        fill = m["fill"].positions
        self.assertLess(max(fill[1::3]), BOWL_H, "盆里的东西在沿口下面")


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class PropBehaviourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from widget import gltf
        cls.model = gltf.load(config.MODEL_PATH)

    def _dog(self):
        from widget.dogctl import DogController
        c = DogController(self.model, seed=1)
        c.set_rest_posture("standing")
        c.set_play(True, home_yaw=330.0)
        self._run(c, 6.0)
        c.action_at = float("inf")
        return c

    @staticmethod
    def _run(c, seconds):
        for _ in range(int(seconds * 60)):
            c.update(1 / 60)
            c.frame()

    def _until(self, c, pred, seconds):
        for i in range(int(seconds * 60)):
            if pred():
                return i / 60
            c.update(1 / 60)
            c.frame()
        return None

    def test_spots_are_measured_from_the_clips(self):
        p = Props(self.model)
        for clip, (zlo, zhi) in (("Pick_up", (0.35, 0.6)), ("Put_down", (0.35, 0.6)), ("Eat_loop", (0.25, 0.45))):
            x, z, u = p.spot(clip)
            self.assertAlmostEqual(x, 0.0, delta=0.03, msg=f"{clip}：鼻子在正前方")
            self.assertTrue(zlo <= z <= zhi, f"{clip}：鼻子最低点在狗前面 z={z:.3f}")
            self.assertTrue(0.0 <= u <= 1.0)
        self.assertTrue(0.2 <= p.spot("Pick_up")[2] <= 0.45, "捡起：鼻子最低在片段前半段")
        self.assertTrue(0.35 <= p.spot("Put_down")[2] <= 0.65, "放下：鼻子最低在片段中段")

    def test_eating_puts_a_food_bowl_under_the_nose_and_drinking_a_water_bowl(self):
        c = self._dog()
        self.assertEqual(c.frame().props, ())
        c.do_action("eating")
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "EatDrink_start", 3.0))
        self.assertIsNotNone(c.props.bowl, "一开始低头就有盆")
        self.assertEqual(c.props.bowl["kind"], "food")
        self._run(c, 0.5)
        self.assertEqual(c.props.bowl["alpha"], 1.0, "0.25 秒淡入完")
        draws = c.frame().props
        if "bowl_food" in props.bought():
            self.assertEqual([d.mesh for d in draws], ["bowl_food"], "买来的饭盆，一块网格")
            self.assertEqual(draws[0].color, (1.0, 1.0, 1.0), "贴图本来的颜色，不另外染")
        with mock.patch.object(props, "bought", return_value={}):    # 买来的模型不在：程序画的盆
            draws = c.frame().props
            self.assertEqual([d.mesh for d in draws], ["bowl", "fill"])
            self.assertEqual(draws[1].color, props.COLORS["food"])
        bx, bz = c.props.bowl["x"], c.props.bowl["z"]
        self.assertGreater(math.hypot(bx - c.x, bz - c.z), 0.25, "盆在狗前面，不在身体中心")
        self.assertIsNotNone(self._until(c, lambda: c.action is None, 12.0), "动作做完")
        self.assertIsNotNone(self._until(c, lambda: c.props.bowl is None, 2.0), "做完淡出")
        c.do_action("drinking")
        self.assertIsNotNone(self._until(c, lambda: c.props.bowl is not None, 3.0))
        self.assertEqual(c.props.bowl["kind"], "water")

    def test_carrying_picks_a_bone_off_the_ground_holds_it_and_puts_it_down(self):
        c = self._dog()
        c.do_action("carrying")
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Pick_up", 3.0))
        it = c.props.item
        self.assertIsNotNone(it, "低头去捡的时候骨头已经在地上")
        self.assertEqual((it["kind"], it["mode"]), ("bone", "ground"))
        d = next(d for d in c.frame().props if d.mesh == "bone")
        self.assertAlmostEqual(d.matrix[13], KNOB_R, delta=1e-6, msg="躺在地上：高度 = 端头球半径")
        grab = c.props.spot("Pick_up")[2]
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Pick_up" and c.player.progress >= grab + 0.02, 3.0))
        self.assertEqual(c.props.item["mode"], "held", "鼻子最低那一刻到嘴里")
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Pick_up_idle", 3.0))
        self._run(c, 1.0)
        self.assertEqual(c.props.item["mode"], "held")
        d = next(d for d in c.frame().props if d.mesh == "bone")
        head = c.head_position()
        self.assertLess(math.dist((d.matrix[12], d.matrix[13], d.matrix[14]), head), 0.2, "叼着：骨头在头附近")
        self.assertGreater(d.matrix[13], 0.3, "叼着：离地")
        release = c.props.spot("Put_down")[2]
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Put_down" and c.player.progress >= release + 0.02, 8.0))
        self.assertEqual(c.props.item["mode"], "linger", "放下了：在地上停着")
        self.assertIsNotNone(self._until(c, lambda: c.action is None, 5.0))
        self.assertIsNotNone(c.props.item, "做完动作骨头还在地上")
        self._run(c, LINGER + 0.6)
        self.assertIsNone(c.props.item, "停够了淡出、消失")

    def test_fetching_uses_a_ball(self):
        c = self._dog()
        c.do_action("fetching")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None, 6.0))
        self.assertEqual(c.props.item["kind"], "ball")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "held", 6.0), "跑到了捡起来")
        self.assertIsNotNone(self._until(c, lambda: c.turn is not None, 4.0), "捡起来转身")
        self.assertEqual(c.props.item["mode"], "held", "转身时球还在嘴里，不掉")
        self.assertIsNotNone(self._until(c, lambda: c.turn is None and c.player.name == "Run_F_IP", 4.0), "往回跑")
        self._run(c, 1.0)
        self.assertEqual(c.props.item["mode"], "held", "往回跑全程叼着")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "linger", 12.0), "跑回来放下")
        d = next(d for d in c.frame().props if d.mesh == "ball")
        self.assertAlmostEqual(d.matrix[13], BALL_R, delta=1e-6, msg="球在地上：高度 = 半径")

    def test_a_cut_while_carrying_fades_the_bone_at_once(self):
        """叼着被切：活动换了就 0.3 秒直接淡出；只有正常放下才在地上停 3 秒。"""
        c = self._dog()
        c.do_action("carrying")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "held", 4.0))
        c.do_action("walking")                                  # 一刀切
        self._run(c, 0.1)
        self.assertTrue(c.props.item is None or c.props.item["out"], "立刻开始淡出")
        self._run(c, 0.4)
        self.assertIsNone(c.props.item, "0.3 秒内没了，不在地上停")
        c.do_action("carrying")                                 # 还没捡到手就被切：也直接淡出
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "ground", 3.0))
        c.do_action("walking")
        self._run(c, 0.5)
        self.assertIsNone(c.props.item)

    def test_a_lingering_bone_fades_when_another_action_starts_but_stays_through_idle(self):
        """放下后在地上停着的那几秒里换别的动作，骨头要直接消失；动作做完回到待机不算换。"""
        c = self._dog()
        c.do_action("picking_up")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "linger", 6.0), "放下了")
        self.assertIsNotNone(self._until(c, lambda: c.action is None, 4.0), "动作做完")
        self._run(c, 0.5)
        self.assertIsNotNone(c.props.item, "回到待机：骨头还在地上停着")
        self.assertEqual(c.props.item["mode"], "linger")
        c.do_action("walking")                                  # 停着的时候换了别的动作
        self._run(c, 0.4)
        self.assertIsNone(c.props.item, "直接淡出，不等 3 秒")
        c.do_action("fetching")                                 # 捡回同样：放下后换动作球立刻没
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "linger", 14.0))
        c.do_action("walking")
        self._run(c, 0.4)
        self.assertIsNone(c.props.item)

    def test_posture_change_or_state_change_cuts_a_lingering_bone(self):
        """放下后换「动作」行的站 / 坐 / 趴也要立刻消失。
        道具的生命周期由控制器明确调 begin / finish / cut，换姿势走一刀切就 cut。"""
        c = self._dog()
        c.do_action("picking_up")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "linger", 6.0))
        self.assertIsNotNone(self._until(c, lambda: c.action is None, 4.0))
        c.set_rest_posture("sitting")                           # 动作行点坐
        self._run(c, 0.4)
        self.assertIsNone(c.props.item, "换姿势：骨头直接淡出")
        self.assertFalse(any(d.mesh == "bone" for d in c.frame().props))

    def test_picking_the_same_bone_again_puts_it_back_on_the_ground_first(self):
        c = self._dog()
        c.do_action("carrying")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "held", 4.0))
        c.do_action("carrying")                                 # 同一根再点：从头捡一遍
        self.assertIsNotNone(self._until(c, lambda: c.player.name == "Pick_up" and c.props.item is not None and c.props.item["mode"] == "ground", 2.0),
                             "骨头先回到地上")
        self.assertIsNotNone(self._until(c, lambda: c.props.item is not None and c.props.item["mode"] == "held", 3.0), "再捡起来")


if __name__ == "__main__":
    unittest.main()
