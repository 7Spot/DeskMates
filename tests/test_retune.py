"""照边牧写死的数按模型来（萨摩耶重调）：身子的骨头按蒙皮认、身高、叼球的位置、头像取景、原地小跳的腾空区间、拎起来的尾巴、
闭眼的角度；不能自定义毛色的模型不出「自定义」。边牧一样都不变。两只的模型文件都是购买的内容，不在就跳过。"""
import math
import os
import unittest

from tests.room_base import COLLIE, HAS, SAMOYED, RoomCase, load
from widget import clips, packs
from widget.anim import Player, axis_angle
from widget.gltf import IDENTITY, mat_mul, transform_point

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BOTH = unittest.skipUnless(HAS[COLLIE] and HAS[SAMOYED], "两只的模型文件要都在（购买的内容不入 git）")


def angle_deg(q) -> float:
    return math.degrees(2.0 * math.acos(min(1.0, abs(q[3]))))


class PackFieldTests(unittest.TestCase):
    """包里新加的三项（读包不看模型文件在不在）。"""

    def test_the_samoyed_pack_carries_its_own_numbers_and_the_collie_none(self):
        found = packs.discover()
        dog, sam = found[COLLIE], found[SAMOYED]
        self.assertEqual((sam.height_m, sam.fit_m), (0.86, 0.92), "站着的片段里最高的关节 0.745 + 耳朵 0.11，再 + 0.06（和边牧一个量法）")
        self.assertEqual(sam.mouth_offset, (0.0, 0.126, -0.036), "头大 1.2 倍：叼着的球往前、往下各多 1.2 倍")
        self.assertEqual(dict(sam.head_shot), {"clip": "Sitting_loop_1", "tall_m": 0.36, "at": 0.45}, "头像坐着拍：站着时卷着的尾巴在两耳之间露一团")
        self.assertEqual(dict(sam.jumps), {"hop": {"arc": (0.24, 0.55)}})
        self.assertEqual((dog.height_m, dog.fit_m), (0.8, 0.86))
        self.assertEqual((dog.mouth_offset, dict(dog.head_shot), dict(dog.jumps)), (None, {}, {}), "边牧不写：用代码里的")
        self.assertTrue(dog.custom_coat)
        self.assertTrue(sam.custom_coat, "第 13 条：萨摩耶也能自定义（整身一个色 + 可选背上一片）")
        self.assertEqual(sam.coat_custom["mode"], "tint")


@BOTH
class MeasuredPerModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from widget.dogctl import DogController
        cls.models = {k: load(k)[1] for k in (COLLIE, SAMOYED)}
        cls.dogs = {k: DogController(m, seed=1) for k, m in cls.models.items()}

    def test_body_bones_are_the_skinned_ones_whatever_the_nodes_are_called(self):
        """别按节点名排除（Root_bone、Cartoon_BorderCollie、Arm_Collie）：萨摩耶的网格节点、骨架节点叫别的名字，会被算进身子。"""
        collie, sam = self.dogs[COLLIE], self.dogs[SAMOYED]
        by_name = [i for i, n in enumerate(self.models[COLLIE].nodes) if n.name not in ("Root_bone", "Cartoon_BorderCollie", "Arm_Collie")]
        self.assertEqual(collie.body, by_name, "边牧：和按名字排除的那个列表逐项相同")
        self.assertEqual(len(sam.body), 56)
        joints = set(self.models[SAMOYED].skin_joints)
        self.assertTrue(set(sam.body) <= joints)
        names = {self.models[SAMOYED].nodes[i].name for i in sam.body}
        self.assertFalse(names & {"Root_bone", "Cartoon_Samoyed", "Arm_Samoyed"})
        self.assertEqual(names, {self.models[COLLIE].nodes[i].name for i in collie.body}, "两只是同一套骨头")

    def mesh_top(self, model, clip: str, samples: int = 6) -> float:
        """这段片段里蒙皮后的网格最高点（米）。"""
        mesh = model.mesh
        P, J, W = mesh.positions, mesh.joints, mesh.weights
        verts = {(P[3 * i], P[3 * i + 1], P[3 * i + 2], J[4 * i], J[4 * i + 1], J[4 * i + 2], J[4 * i + 3]): tuple(W[4 * i:4 * i + 4])
                 for i in range(mesh.vertex_count) if P[3 * i + 1] > 0.3 or abs(P[3 * i + 2]) > 0.3}     # 只算高处、两头的（耳朵、头、尾巴）：肚子、腿不会是最高点
        c = model.clips[clip]
        p = Player(model)
        p.play(clip, loop=False, fade=0.0)
        top = -math.inf
        for k in range(samples + 1):
            p.time = c.duration * k / samples
            p.update(0.0)
            g = p.globals(IDENTITY)
            jm, mw = p.joint_matrices_from(g), g[model.mesh_node]
            for (x, y, z, *js), ws in verts.items():
                sx = sy = sz = 0.0
                for j, w in zip(js, ws):
                    if w:
                        a = jm[int(j)]
                        sx += w * (a[0] * x + a[4] * y + a[8] * z + a[12])
                        sy += w * (a[1] * x + a[5] * y + a[9] * z + a[13])
                        sz += w * (a[2] * x + a[6] * y + a[10] * z + a[14])
                top = max(top, mw[1] * sx + mw[5] * sy + mw[9] * sz + mw[13])
        return top

    def test_the_ear_margin_covers_both_dogs(self):
        """窗口按「最高的关节 + MESH_MARGIN」长高：耳朵尖、尾巴的毛都要在里面（萨摩耶跑起来尾巴的毛比关节高 4～6 厘米）。"""
        from widget.dogctl import MESH_MARGIN
        for key, dog in self.dogs.items():
            for clip in ("Idle_1", "Run_F_IP", "RunFast_F_IP", "JumpLand"):
                top = self.mesh_top(self.models[key], clip)
                self.assertLessEqual(top, dog.clip_top(clip) + 1e-6, f"{key} {clip}")
                self.assertLess(top - (dog.clip_top(clip) - MESH_MARGIN), MESH_MARGIN, f"{key} {clip}")

    def test_the_carried_ball_sits_at_each_dogs_own_mouth(self):
        from widget.props import MOUTH_OFFSET, Props
        self.assertEqual(Props(self.models[COLLIE]).mouth, MOUTH_OFFSET)
        self.assertEqual(Props(self.models[SAMOYED]).mouth, (0.0, 0.126, -0.036))
        self.assertEqual(self.dogs[SAMOYED].props.mouth, (0.0, 0.126, -0.036))
        for key, model in self.models.items():                    # 叼起那一刻（Pick_up 里鼻子最低）嘴里的点离地上的球（鼻子正下方，球心离地一个半径）多远
            from widget.props import BALL_R
            props = Props(model)
            x, z, u = props.spot("Pick_up")
            p = Player(model)
            p.play("Pick_up", loop=False, fade=0.0)
            p.time = model.clips["Pick_up"].duration * u
            p.update(0.0)
            g = p.globals(IDENTITY)
            mouth = transform_point(g[model.node_by_name("head").index], props.mouth)
            self.assertLess(math.dist(mouth, (x, BALL_R, z)), 0.06, f"{key}：交接时球不跳一截")

    def test_a_lifted_dog_only_raises_a_tail_that_hangs(self):
        """拎起来尾巴再翘 40°是给垂着的尾巴定的；萨摩耶的尾巴本来就卷在背上，再翘整个卷压扁在背上。"""
        from widget.lift import TAIL_UP_DEG, TAILS, LiftRig
        collie, sam = LiftRig(self.models[COLLIE]), LiftRig(self.models[SAMOYED])
        self.assertFalse(collie.tail_curled)
        self.assertTrue(sam.tail_curled)
        self.assertEqual(collie.deg[collie.idx["Tail_01"]], TAIL_UP_DEG * 0.5)
        for n in TAILS:
            self.assertEqual(collie.deg[collie.idx[n]], TAIL_UP_DEG * 0.2)
        for n in ("Tail_01",) + TAILS:
            self.assertNotIn(sam.idx[n], sam.deg, f"萨摩耶 {n}：不加")
        self.assertIn(sam.idx["Tail_01"], sam.offsets(1.0, 20.0), "尾巴照样跟着腿甩")
        moved = lambda rig: {n for n, i in rig.idx.items() if i in rig.deg}      # noqa: E731
        self.assertEqual(moved(collie) - {"Tail_01", *TAILS}, moved(sam), "别的骨头两只一样地摆")

    def test_closed_eyes_are_measured_from_each_dogs_sleeping_clip(self):
        from widget.expression import EYE_CLOSE_DEG, Expression, ExpressionRig
        want = {COLLIE: (60.0, 0.2), SAMOYED: (53.5, 0.5)}
        for key, model in self.models.items():
            rig = ExpressionRig(model)
            self.assertEqual(set(rig.eye_close), set(rig.eyelids))
            e = Expression()
            e.cur["eyes"] = 1.0
            out = rig.offsets(e)
            for i in rig.eyelids:
                self.assertAlmostEqual(angle_deg(out[i]), want[key][0], delta=want[key][1], msg=key)
            e.cur["eyes"] = 0.5
            half = rig.offsets(e)
            self.assertAlmostEqual(angle_deg(half[rig.eyelids[0]]), angle_deg(out[rig.eyelids[0]]) / 2, delta=0.05, msg="闭多少 = 这个旋转的几成")
        rig = ExpressionRig(self.models[COLLIE])                 # 边牧：还是绕 -X，和写死的那个旋转差不到零点几度
        e = Expression()
        e.cur["eyes"] = 1.0
        fixed = axis_angle((-1.0, 0.0, 0.0), EYE_CLOSE_DEG)
        for q in (rig.offsets(e)[i] for i in rig.eyelids):
            self.assertGreater(abs(sum(a * b for a, b in zip(q, fixed))), math.cos(math.radians(0.5) / 2))

    def test_the_hop_arc_follows_each_dogs_clip(self):
        """原地小跳（Jump_Place_IP）萨摩耶的片段短 0.125 秒（末尾剪了）：同样的时刻换成它的进度。别的跳法、边牧都不变。"""
        collie, sam = self.dogs[COLLIE], self.dogs[SAMOYED]
        self.assertIs(clips.jumps_for(self.models[COLLIE]), clips.JUMPS)
        self.assertIs(collie.jumps, clips.JUMPS)
        by_name = {j.name: j for j in sam.jumps}
        self.assertEqual(by_name["hop"].arc, (0.24, 0.55))
        self.assertEqual([j for j in sam.jumps if j.name != "hop"], [j for j in clips.JUMPS if j.name != "hop"])
        self.assertEqual([j.name for j in sam.jumps], [j.name for j in clips.JUMPS], "顺序不变（随机挑跳法按它）")
        hop = next(j for j in clips.JUMPS if j.name == "hop")
        d0, d1 = (self.models[k].clips["Jump_Place_IP"].duration for k in (COLLIE, SAMOYED))
        for a, b in zip(hop.arc, by_name["hop"].arc):
            self.assertAlmostEqual(a * d0, b * d1, delta=0.012, msg="腾空的时刻（秒）两只一样")


class CollieCoatRowTests(RoomCase):
    PACK = COLLIE

    def test_the_collie_keeps_its_custom_coat(self):
        win = self.win
        self.assertTrue(win.custom_coat_on)
        card = self.attach_card()
        self.assertFalse(card.custom_swatch.isHidden(), "边牧：「自定义」照旧在")
        self.assertIsNotNone(win.look.painter())


class NoCustomCoat:
    """包里写了 custom_coat: false 的模型（这里拿萨摩耶的包改成 false 来测这条路）。"""

    @classmethod
    def setUpClass(cls):
        import dataclasses
        super().setUpClass()
        cls.pack = dataclasses.replace(cls.pack, custom_coat=False)


class SamoyedCoatRowTests(NoCustomCoat, RoomCase):
    def test_no_custom_coat_cell_and_the_custom_page_does_not_open(self):
        """pack.json 写了 custom_coat: false：设置卡片毛色那一行只有四张头像，自定义毛色页打不开。"""
        win = self.win
        self.assertFalse(win.custom_coat_on)
        card = self.attach_card()
        self.assertEqual(len(card.swatches), 4)
        self.assertTrue(card.custom_swatch.isHidden(), "没有「自定义」那一格")
        card.show()
        self.app.processEvents()
        card.show_page("pet", animated=False)
        card.finish_page_anim()
        self.assertFalse(card.custom_swatch.isVisible())
        self.assertTrue(all(s.isVisible() for s in card.swatches))
        xs = [s.mapTo(card, s.rect().center()).x() for s in card.swatches]
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        self.assertLess(max(gaps) - min(gaps), 2, "四张头像四等分")
        win.open_coat()
        self.assertEqual((card.page, win.coat), ("pet", 1), "不换页、毛色不动")
        self.assertIsNone(win.look.painter())
        card.sync()                                               # 每 0.3 秒对齐的那一步：没有那一格也不出错


class SamoyedSavedCustomCoatTests(NoCustomCoat, RoomCase):
    from widget.coat import CoatSpec
    from widget.prefs import pet_key
    SETTINGS = {pet_key("", SAMOYED, "coat"): 0, pet_key("", SAMOYED, "coat_custom"): CoatSpec(2, "#FF0000", "#00FF00").to_json()}

    def test_a_saved_custom_coat_falls_back_to_the_first_coat(self):
        """包里写了不能自定义、设置里却记着自定义的：启动回到第一套并记回去；那串参数留着（哪天这个包能自定义了还在）。"""
        win = self.win                                            # 建窗口时已经按设置换过毛色（look.restore）
        self.assertEqual((win.coat, win.prefs.get("coat")), (1, 1))
        self.assertEqual(win.look._wearing, ("coat", 1))
        self.assertIn("#FF0000", win.prefs.get("coat_custom").upper())
        self.assertEqual(win.look._saved_key(), ("coat", 1))


if __name__ == "__main__":
    unittest.main()
