"""物件的打底：静态模型装成渲染器认的 Model、放大、画面多大、前沿那一层、没有显卡时出图返回空（widget/thing_art.py）；
模型包里 thing 那一段怎么读、哪些款能用（widget/packs.py 的 ThingStyle、things）；出图多了一个可选的渲染器参数（widget/dogview.py）。
逻辑测试用现写的最小 glb 和临时文件夹里的假包，不要求买来的模型在；看真模型的那一类，models/props/ 不在就跳过。"""
import json
import math
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage

import config
from tests.panel_base import QUIET
from widget import dogview, packs, thing_art
from widget.render import ELEVATION, OUTLINE, DogRenderer

SIN, COS = math.sin(math.radians(ELEVATION)), math.cos(math.radians(ELEVATION))
PROPS = config.ROOT / "models" / "props"
HAS_PROPS = (PROPS / "bed_1.glb").is_file()


def png_2x2() -> bytes:
    """一张 2 × 2 的红色 PNG（手写：不靠 Qt）。"""
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def glb(quads, texture: bool = True, node_extra: dict = None) -> bytes:
    """最小的 glb：几个四边形（每个给四个角，逆时针）、带贴图坐标、一张 2 × 2 的贴图。一个网格、一个 primitive、uint16 索引。"""
    pos, nrm, uv, idx = [], [], [], []
    for q in quads:
        base = len(pos) // 3
        for (x, y, z), (u, v) in zip(q, ((0, 0), (1, 0), (1, 1), (0, 1))):
            pos += [x, y, z]
            nrm += [0.0, 0.0, 1.0]
            uv += [u, v]
        idx += [base, base + 1, base + 2, base, base + 2, base + 3]
    parts = [struct.pack(f"<{len(pos)}f", *pos), struct.pack(f"<{len(nrm)}f", *nrm), struct.pack(f"<{len(uv)}f", *uv), struct.pack(f"<{len(idx)}H", *idx)]
    if texture:
        parts.append(png_2x2())
    views, blob = [], b""
    for part in parts:
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(part)})
        blob += part + b"\x00" * (-len(part) % 4)
    n = len(pos) // 3
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0, **(node_extra or {})}], "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": n, "type": "VEC3"}, {"bufferView": 1, "componentType": 5126, "count": n, "type": "VEC3"},
                         {"bufferView": 2, "componentType": 5126, "count": n, "type": "VEC2"}, {"bufferView": 3, "componentType": 5123, "count": len(idx), "type": "SCALAR"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
           "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}} if texture else {}}]}
    if texture:
        doc.update({"textures": [{"source": 0}], "images": [{"bufferView": 4, "mimeType": "image/png"}]})
    text = json.dumps(doc).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + blob
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


CARD = [((-0.5, 0.0, 0.0), (0.5, 0.0, 0.0), (0.5, 1.0, 0.0), (-0.5, 1.0, 0.0))]          # 立着的一张牌：宽 1、高 1，正对镜头
TILE = [((-0.5, 0.0, 0.3), (0.5, 0.0, 0.3), (0.5, 0.0, -0.3), (-0.5, 0.0, -0.3))]        # 铺在地上的一块：宽 1、前后 0.6


class StaticModelTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def file(self, name: str, raw: bytes) -> Path:
        path = Path(self.dir.name) / name
        path.write_bytes(raw)
        return path

    def model(self, quads, name="m.glb"):
        return thing_art.load_static(self.file(name, glb(quads)))

    def test_a_static_mesh_becomes_a_model_the_dog_renderer_takes(self):
        """每个顶点只绑第 0 根「骨头」、权重 1，那根骨头是单位阵：渲染器、着色器一行不用改。"""
        m = self.model(CARD)
        mesh = m.mesh
        self.assertEqual((mesh.vertex_count, mesh.index_count), (6, 6), "按索引展开：两个三角形六个顶点")
        self.assertEqual(len(mesh.positions), 18)
        self.assertEqual(len(mesh.uvs), 12)
        self.assertEqual(list(mesh.weights), [1.0, 0.0, 0.0, 0.0] * 6)
        self.assertEqual(set(mesh.joints), {0.0})
        self.assertEqual(len(mesh.joints), 24)
        self.assertEqual(mesh.bounds, ((-0.5, 0.0, 0.0), (0.5, 1.0, 0.0)))
        self.assertEqual((len(m.nodes), m.skin_joints, len(m.inverse_bind), dict(m.clips)), (1, [0], 1, {}))
        self.assertEqual(m.texture_png, png_2x2())
        self.assertEqual(m.gain, 1.0, "不提亮")
        renderer = DogRenderer(m)                                    # 构造不碰显卡
        self.assertIsNone(renderer.rhi)
        self.assertIs(thing_art.load_static(Path(self.dir.name) / "m.glb"), m, "同一个文件只读一次")

    def test_files_that_cannot_be_drawn_raise_so_the_style_counts_as_missing(self):
        for name, raw in (("no_texture.glb", glb(CARD, texture=False)), ("garbage.glb", b"not a glb at all"), ("short.glb", b"glTF"),
                          ("moved.glb", glb(CARD, node_extra={"translation": [1, 0, 0]}))):
            with self.assertRaises(ValueError, msg=name):
                thing_art.load_static(self.file(name, raw))
        with self.assertRaises(ValueError):
            thing_art.load_static(Path(self.dir.name) / "gone.glb")

    def test_scaling_is_baked_into_the_vertices(self):
        """放大写进顶点（写进根矩阵的话描边跟着变粗，和狗不一样）。"""
        m = self.model(CARD)
        big = thing_art.scaled(m, 1.6)
        self.assertEqual(big.mesh.bounds, ((-0.8, 0.0, 0.0), (0.8, 1.6, 0.0)))
        for a, b in zip(m.mesh.positions, big.mesh.positions):
            self.assertAlmostEqual(b, a * 1.6, places=5)
        self.assertIs(big.mesh.normals, m.mesh.normals)
        self.assertIs(big.texture_png, m.texture_png)
        self.assertIs(thing_art.scaled(m, 1.0), m, "1 倍就是原来那个")
        self.assertEqual(m.mesh.bounds, ((-0.5, 0.0, 0.0), (0.5, 1.0, 0.0)), "原来的没被改")

    def test_scale_and_yaw_come_from_the_pack(self):
        self.assertEqual(thing_art.scale_of({}), 1.0)
        self.assertEqual(thing_art.scale_of({"scale": 1.3}, 0.86), 1.3, "不跟狗走的款")
        self.assertAlmostEqual(thing_art.scale_of({"scale": 1.6, "fit_pet": True}, 0.8), 1.6)
        self.assertAlmostEqual(thing_art.scale_of({"scale": 1.6, "fit_pet": True}, 0.928), 1.6 * 1.16, msg="狗窝再乘狗的身高比")
        self.assertEqual(thing_art.yaw_of({"yaw": 35, "mirror": True}), 35.0)
        self.assertEqual(thing_art.yaw_of({"yaw": 35, "mirror": True}, right_half=True), -35.0, "屏幕右半边反过来画，门朝中间")
        self.assertEqual(thing_art.yaw_of({"yaw": 70}, right_half=True), 70.0)
        self.assertEqual(thing_art.yaw_of({}), 0.0)

    def test_layout_of_an_upright_card_matches_hand_arithmetic(self):
        m = self.model(CARD)
        x0, x1, y0, y1 = thing_art.extent(m, 0.0)
        self.assertEqual((x0, x1, y0), (-0.5, 0.5, 0.0))
        self.assertAlmostEqual(y1, COS, places=6, msg="相机俯视 10 度：1 米高在画面上是 cos10°")
        ppm, pad = 200.0, thing_art.PAD_PX
        lay = thing_art.layout(m, 0.0, ppm, shadow=False)
        self.assertEqual(lay.w, math.ceil((1.0 + 2 * OUTLINE) * ppm + 2 * pad))
        self.assertEqual(lay.h, math.ceil((COS + 2 * OUTLINE) * ppm + 2 * pad))
        self.assertAlmostEqual(lay.cx, pad + (OUTLINE + 0.5) * ppm, places=4)
        self.assertAlmostEqual(lay.base, pad + OUTLINE * ppm, places=4)
        self.assertAlmostEqual(lay.low_m, 0.0)
        self.assertAlmostEqual(lay.left_m, 0.5)
        self.assertAlmostEqual(lay.right_m, 0.5)
        self.assertAlmostEqual(lay.top_m, COS, places=6)
        frame = lay.frame
        self.assertIsNone(frame.shadow)
        self.assertEqual((frame.ppm, frame.opacity, frame.gray, len(frame.joints)), (ppm, 1.0, 0.0, 1))
        self.assertAlmostEqual(frame.ground_px, lay.base, places=4, msg="原点就是最低点：那条线就是原点那条线")
        self.assertAlmostEqual(frame.offset[0], lay.cx - lay.w / 2.0, places=4)
        left, top, w, h = lay.box()
        self.assertAlmostEqual(left, lay.cx - 0.5 * ppm, places=4)
        self.assertAlmostEqual(top + h, lay.h - lay.base, places=4)
        self.assertAlmostEqual(w, 1.0 * ppm, places=4)
        side = thing_art.layout(m, 90.0, ppm, shadow=False)
        self.assertLess(side.w, 2 * pad + 2 * OUTLINE * ppm + 2, "转 90 度只剩一条线")

    def test_the_anchor_is_the_lowest_drawn_point_not_the_origin(self):
        """靠镜头的那条边比模型原点低（俯视）：锚点是画出来最低的那一点，原点比它高 low_m。"""
        m = self.model(TILE, "tile.glb")
        ppm, pad = 100.0, thing_art.PAD_PX
        lay = thing_art.layout(m, 0.0, ppm, shadow=False)
        self.assertAlmostEqual(lay.low_m, 0.3 * SIN, places=6)
        self.assertAlmostEqual(lay.top_m, 0.6 * SIN, places=6)
        self.assertAlmostEqual(lay.base, pad + OUTLINE * ppm, places=4)
        self.assertAlmostEqual(lay.frame.ground_px, lay.base + 0.3 * SIN * ppm, places=4)

    def test_the_shadow_is_in_the_same_picture_and_the_anchor_does_not_move(self):
        """影子是渲染器自己的接触阴影，按贴地那一圈的方框算；画面留到影子的边，物件脚下那条线离图底跟着多出来。"""
        m = self.model(TILE, "tile.glb")
        ppm, pad = 100.0, thing_art.PAD_PX
        bare, lay = thing_art.layout(m, 0.0, ppm, shadow=False), thing_art.layout(m, 0.0, ppm, shadow=True)
        rx = 0.5 * 0.95 + 0.04
        ry = max(0.3 * SIN + 0.03, rx * 0.18)
        s = lay.frame.shadow
        self.assertIsNotNone(s)
        self.assertAlmostEqual(s.rx, rx * ppm, places=4)
        self.assertAlmostEqual(s.ry, ry * ppm, places=4)
        self.assertAlmostEqual(s.cx, lay.cx, places=4, msg="影子在物件正下方")
        self.assertAlmostEqual(s.cy, lay.frame.ground_px, places=4)
        self.assertEqual(lay.w, math.ceil((2 * rx + 2 * OUTLINE) * ppm + 2 * pad), "影子比物件宽：画面按影子留")
        self.assertGreaterEqual(s.cx - s.rx, pad - 1e-6)
        self.assertGreaterEqual(s.cy - s.ry, pad - 1e-6)
        self.assertAlmostEqual(lay.base - bare.base, (ry - 0.3 * SIN) * ppm, places=4)
        self.assertEqual((lay.low_m, lay.left_m, lay.right_m, lay.top_m), (bare.low_m, bare.left_m, bare.right_m, bare.top_m), "物件本身占多大不算影子")
        floating = self.model([tuple((x, y + 0.5, z) for x, y, z in CARD[0])], "floating.glb")
        self.assertIsNone(thing_art.layout(floating, 0.0, ppm, shadow=True).frame.shadow, "没有贴地的一圈：没有影子")

    def test_front_part_keeps_only_the_faces_nearer_the_camera(self):
        """窝的前沿：比 z_cut 更靠镜头的面另成一层（狗趴在窝里时盖在狗前面）；包围盒照整件的，两张图用同一个画面。"""
        back = tuple((x, y, -0.2) for x, y, _ in CARD[0])
        front = tuple((x, y, 0.2) for x, y, _ in CARD[0])
        m = self.model([back, front], "two.glb")
        self.assertEqual(m.mesh.vertex_count, 12)
        part = thing_art.front_part(m, 0.0)
        self.assertEqual(part.mesh.vertex_count, 6)
        self.assertEqual({round(z, 3) for z in part.mesh.positions[2::3]}, {0.2})
        self.assertEqual(list(part.mesh.weights), [1.0, 0.0, 0.0, 0.0] * 6)
        self.assertEqual(part.mesh.bounds, m.mesh.bounds)
        self.assertEqual(thing_art.front_part(m, 0.5).mesh.vertex_count, 0)

    def test_shooting_without_a_canvas_gives_an_empty_picture(self):
        """画布没好（offscreen 平台没有显卡、真机上还没画过第一帧）：返回空图，不报错。借到画布时渲染器现建、画完就放。"""
        m = self.model(CARD)
        lay = thing_art.layout(m, 0.0, 100.0)
        self.assertTrue(thing_art.shoot(None, m, lay).isNull())
        calls = []
        not_ready = SimpleNamespace(ready=lambda: False, shoot=lambda *a, **k: calls.append(a))
        self.assertTrue(thing_art.shoot(not_ready, m, lay, 2.0).isNull())
        self.assertEqual(calls, [], "没好就不去画")
        seen = {}

        def fake_shoot(frame, w, h, dpr, shooter=None):
            seen.update(frame=frame, size=(w, h), dpr=dpr, shooter=shooter)
            return QImage(4, 4, QImage.Format_ARGB32_Premultiplied)
        with mock.patch.object(DogRenderer, "release", autospec=True) as release:
            img = thing_art.shoot(SimpleNamespace(ready=lambda: True, shoot=fake_shoot), m, lay, 2.0)
        self.assertEqual(img.width(), 4)
        self.assertIs(seen["frame"], lay.frame)
        self.assertEqual((seen["size"], seen["dpr"]), ((lay.w, lay.h), 2.0))
        self.assertIsInstance(seen["shooter"], DogRenderer)
        self.assertIs(seen["shooter"].model, m, "用这件物件自己的一套渲染器")
        release.assert_called_once_with(seen["shooter"])


class ShooterArgumentTests(unittest.TestCase):
    """出图多了一个可选的 shooter：不给走的还是原来那套（贴纸、头像一点不变）。"""

    class Canvas(dogview._Shooting):
        def __init__(self, own):
            self.own, self.asked, self.jobs = own, 0, []

        def _shooter(self):
            self.asked += 1
            return self.own

        def grabFramebuffer(self):
            self.jobs.append(self._job)

    @staticmethod
    def renderer():
        r = SimpleNamespace(coat_image=None, rhi=None, coats=[])
        r.set_coat = lambda coat: (r.coats.append(coat), setattr(r, "coat_image", coat))
        r.shot = lambda: QImage()
        return r

    def test_without_a_shooter_the_canvas_uses_its_own(self):
        own = self.renderer()
        canvas = self.Canvas(own)
        coat = QImage(2, 2, QImage.Format_ARGB32)
        self.assertTrue(canvas.shoot("frame", 64, 48, 2.0, coat).isNull())
        self.assertEqual(canvas.jobs, [("frame", 64, 48, 2.0, own)])
        self.assertEqual(own.coats, [coat])
        self.assertIsNone(canvas._job, "出完就清")

    def test_a_given_shooter_is_the_one_that_draws(self):
        own, other = self.renderer(), self.renderer()
        canvas = self.Canvas(own)
        canvas.shoot("frame", 10, 20, shooter=other)
        self.assertEqual(canvas.jobs, [("frame", 10, 20, 1.0, other)])
        self.assertEqual(canvas.asked, 0, "自己那套没被叫出来（DogView 的那套是用到才建的）")
        self.assertEqual(other.coats, [], "物件不换毛色")
        other.rhi = object()
        other.shot = lambda: QImage(3, 3, QImage.Format_ARGB32)
        self.assertEqual(canvas.shoot("frame", 10, 20, shooter=other).width(), 3, "图从给的那套上取")

    def test_the_render_step_draws_with_the_shooter_in_the_job(self):
        own, other = self.renderer(), self.renderer()
        canvas = self.Canvas(own)
        drawn = []
        other.bound_to = lambda rhi: True
        other.shoot = lambda cb, w, h, dpr, frame: drawn.append((cb, w, h, dpr, frame))
        canvas.rhi = lambda: "rhi"
        self.assertFalse(canvas._shoot_now("cb"), "没有活：照常画窗口里的")
        canvas._job = ("frame", 10, 20, 2.0, other)
        self.assertTrue(canvas._shoot_now("cb"))
        self.assertEqual(drawn, [("cb", 10, 20, 2.0, "frame")])
        self.assertEqual(canvas.asked, 0)


class DarkCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])

    def test_the_studio_and_a_dog_view_give_empty_pictures_offscreen(self):
        """单测里没有显卡：物件的图是空的，摆放、拖动这些逻辑不看图。"""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "card.glb"
            path.write_bytes(glb(CARD))
            m = thing_art.load_static(path)
        lay = thing_art.layout(m, 0.0, 120.0)
        room = thing_art.Studio()
        self.addCleanup(room.deleteLater)
        self.assertTrue(room.shoot_thing(m, lay, 2.0).isNull())
        room.close()
        view = dogview.DogView(SimpleNamespace(mesh=SimpleNamespace(positions=[-1, 0, 0, 1, 2, 0], joints=[0, 0, 0, 0] * 2, weights=[1, 0, 0, 0] * 2)))
        self.addCleanup(view.deleteLater)
        self.assertTrue(thing_art.shoot(view, m, lay, 2.0).isNull())


def write_pack(root: Path, pid: str, thing=None, **more) -> None:
    (root / pid).mkdir()
    data = {"id": pid, "kind": "prop", "name": {"en": pid.title(), "zh": pid}, **more}
    if thing is not None:
        data["thing"] = thing
    (root / pid / "pack.json").write_text(json.dumps(data), encoding="utf-8")


class ThingPackTests(unittest.TestCase):
    """假的包（临时文件夹）：不要求买来的模型在。"""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    def model_file(self, pid: str, name: str) -> str:
        (self.root / pid / name).write_bytes(b"x")
        return name

    def test_each_style_is_the_pack_section_overlaid_with_its_own(self):
        write_pack(self.root, "bed", {
            "group": "rest", "order": 10, "role": "bed", "scale": 1.6, "fit_pet": True, "yaw": 0, "shadow": True,
            "rest": {"x": 0.0, "rise": 0.075, "side": 0}, "front_z": 0.14,
            "styles": [{"id": "blue", "name": {"en": "Blue bed", "zh": "蓝垫子"}, "model": "blue.glb", "thumb": "blue.png"},
                       {"id": "paws", "name": {"en": "Paw nest"}, "model": "paws.glb", "rest": {"x": 0.0, "rise": 0.06, "side": 0}, "front_z": 0.12, "yaw": 5}]})
        self.model_file("bed", "blue.glb")
        (self.root / "bed" / "blue.png").write_bytes(b"x")
        pack = packs.discover(self.root)["bed"]
        self.assertEqual((pack.kind, len(pack.things)), ("prop", 2))
        blue, paws = pack.things
        self.assertEqual((blue.key, blue.pack, blue.group, blue.role), ("bed/blue", "bed", "rest", "bed"))
        self.assertEqual((blue.display_name("zh"), blue.display_name("en")), ("蓝垫子", "Blue bed"))
        self.assertEqual(paws.display_name("zh"), "Paw nest", "没写中文用英文")
        self.assertEqual(blue.model, self.root / "bed" / "blue.glb")
        self.assertEqual(blue.thumb, self.root / "bed" / "blue.png")
        self.assertEqual((blue.spec["scale"], blue.spec["front_z"], blue.spec["rest"]["rise"], blue.spec["yaw"]), (1.6, 0.14, 0.075, 0))
        self.assertEqual((paws.spec["scale"], paws.spec["front_z"], paws.spec["rest"]["rise"], paws.spec["yaw"]), (1.6, 0.12, 0.06, 5), "款里写的盖掉包里的")
        for style in pack.things:
            self.assertFalse({"styles", "id", "name", "model", "thumb"} & set(style.spec))
        self.assertEqual(paws.thumb.name, "thumb-paws.png", "缩略图不写就是 thumb-<款>.png")
        self.assertTrue(blue.available)
        self.assertFalse(paws.available, "模型文件不在")
        self.assertEqual([t.key for t in packs.things(packs.discover(self.root))], ["bed/blue"], "不在的款不列")

    def test_a_pack_without_a_thing_section_has_no_styles(self):
        write_pack(self.root, "plain")
        write_pack(self.root, "odd", "not a mapping")
        found = packs.discover(self.root)
        self.assertEqual((found["plain"].things, found["odd"].things), ((), ()))
        self.assertEqual(packs.things(found), [])

    def test_things_are_listed_by_group_then_order_then_style(self):
        def thing(group, order, role, ids):
            return {"group": group, "order": order, "role": role, "styles": [{"id": i, "model": f"{i}.glb"} for i in ids]}
        write_pack(self.root, "park", thing("park", 50, "decor", ["bin", "fence"]))
        write_pack(self.root, "bench", thing("park", 20, "decor", ["bench"]))
        write_pack(self.root, "water", thing("food", 20, "bowl", ["bowl"]))
        write_pack(self.root, "food", thing("food", 10, "bowl", ["bowl"]))
        write_pack(self.root, "bed", thing("rest", 10, "bed", ["b", "a"]))
        write_pack(self.root, "ball", {"group": "toys", "order": 10, "role": "fetch", "scale": 1.43,
                                       "styles": [{"id": "red", "draw": "ball", "scale": 1.0}, {"id": "tennis", "model": "tennis.glb"}]})
        for pid, names in (("park", ("bin", "fence")), ("bench", ("bench",)), ("water", ("bowl",)), ("food", ("bowl",)), ("bed", ("a", "b"))):
            for n in names:
                self.model_file(pid, f"{n}.glb")
        found = packs.discover(self.root)
        self.assertEqual([t.key for t in packs.things(found)],
                         ["bed/b", "bed/a", "food/bowl", "water/bowl", "ball/red", "bench/bench", "park/bin", "park/fence"])
        red = found["ball"].things[0]
        self.assertIsNone(red.model)
        self.assertTrue(red.available, "程序自己画的那一款不要模型")
        self.assertEqual(red.spec["scale"], 1.0)
        self.assertFalse(found["ball"].things[1].available)

    def test_an_unknown_group_or_role_is_skipped_with_a_note(self):
        write_pack(self.root, "good", {"group": "park", "role": "decor", "styles": [{"id": "x", "model": "x.glb"}]})
        write_pack(self.root, "typo", {"group": "prak", "role": "decor", "styles": [{"id": "x", "model": "x.glb"}]})
        write_pack(self.root, "newer", {"group": "park", "role": "trampoline", "styles": [{"id": "x", "model": "x.glb"}]})
        for pid in ("good", "typo", "newer"):
            self.model_file(pid, "x.glb")
        with self.assertLogs("packs", level="WARNING") as logs:
            listed = packs.things(packs.discover(self.root))
        self.assertEqual([t.key for t in listed], ["good/x"])
        self.assertEqual(len(logs.output), 2)

    def test_a_style_without_an_id_spoils_only_its_own_pack(self):
        write_pack(self.root, "good", {"group": "park", "role": "decor", "styles": [{"id": "x", "model": "x.glb"}]})
        write_pack(self.root, "bad", {"group": "park", "role": "decor", "styles": [{"model": "x.glb"}]})
        with self.assertLogs("packs", level="WARNING"):
            self.assertEqual(list(packs.discover(self.root)), ["good"])


class ShippedThingPackTests(unittest.TestCase):
    """入 git 的那十二个包（pack.json 和缩略图在，模型不一定在）。"""
    PACKS = ("ball", "barrier", "bed", "bench", "big_ball", "bone", "bridge", "doghouse", "food_bowl", "park", "seesaw", "water_bowl")

    @classmethod
    def setUpClass(cls):
        cls.found = packs.discover()

    def styles(self):
        return [t for pid in self.PACKS for t in self.found[pid].things]

    def test_twelve_packs_and_twenty_nine_styles_read(self):
        self.assertEqual(sorted(p.id for p in self.found.values() if p.things), list(self.PACKS))
        styles = self.styles()
        self.assertEqual(len(styles), 29)
        self.assertEqual(len({t.key for t in styles}), 29)
        for t in styles:
            self.assertIn(t.group, packs.THING_GROUPS, t.key)
            self.assertIn(t.role, packs.THING_ROLES, t.key)
            self.assertTrue(t.names.get("en") and t.names.get("zh"), t.key)
            self.assertEqual(self.found[t.pack].kind, "prop")
            self.assertGreater(float(t.spec["scale"]), 0.0)
            self.assertIsInstance(t.spec["shadow"], bool)
            if t.spec.get("draw") == "ball":
                self.assertIsNone(t.model)
            else:
                self.assertEqual(t.model.parent, PROPS, f"{t.key}: 买来的模型放 models/props/，不入 git")
        self.assertEqual({t.group for t in styles}, set(packs.THING_GROUPS))

    def test_thumbnails_ship_with_the_packs(self):
        for t in self.styles():
            self.assertTrue(t.thumb is not None and t.thumb.is_file(), t.key)
            self.assertEqual(t.thumb.parent, self.found[t.pack].root, "缩略图跟包走")
            self.assertEqual(t.thumb.name, f"thumb-{t.key.split('/', 1)[1]}.png")

    def test_what_each_kind_needs_is_written(self):
        by_key = {t.key: t for t in self.styles()}
        for key in ("bed/blue", "bed/grey", "bed/paws", "bed/orange"):
            spec = by_key[key].spec
            self.assertTrue(spec["fit_pet"], "狗窝跟着狗的身高放大")
            self.assertEqual(spec["rest"]["side"], 0)
            self.assertGreater(spec["front_z"], 0.0)
        gable, flat = by_key["doghouse/gable"].spec, by_key["doghouse/flat"].spec
        self.assertEqual((gable["yaw"], gable["mirror"], gable["rest"]["side"]), (35, True, 1), "尖顶狗屋斜着摆、门朝屏幕中间，狗趴在门外")
        self.assertNotIn("platform", gable)
        self.assertEqual((flat["yaw"], flat.get("mirror", False)), (0, False))
        for key in ("doghouse/flat", "bench/bench", "seesaw/seesaw", "bridge/bridge"):
            p = by_key[key].spec["platform"]
            self.assertLess(p["x0"], p["x1"], key)
            self.assertGreater(p["y"], 0.0)
            self.assertLessEqual(p["thick"], p["y"] + 0.04)
        for key, serves in (("food_bowl/bowl", "food"), ("water_bowl/bowl", "water")):
            self.assertEqual(by_key[key].spec["serves"], serves)
            self.assertIsNotNone(by_key[key].model_empty, "盆有空了以后的样子")
        self.assertEqual(by_key["barrier/low"].spec["hurdle"], {"h": 0.56})
        self.assertNotIn("hurdle", by_key["barrier/mid"].spec)
        self.assertNotIn("hurdle", by_key["barrier/high"].spec)
        toys = [t for t in self.styles() if t.group == "toys"]
        self.assertEqual({t.role for t in toys}, {"fetch", "push"})
        for t in toys:
            self.assertFalse(t.spec["shadow"], f"{t.key}: 玩具的影子是球的小窗口自己画的（离地越高越淡）")
            self.assertGreater(t.spec["radius"], 0.0)
        self.assertEqual(by_key["ball/red"].spec["draw"], "ball")
        self.assertEqual({t.spec.get("carry") for t in toys if t.pack == "bone"}, {"bone"})
        self.assertEqual({t.spec.get("carry") for t in toys if t.pack == "big_ball"}, {None}, "大球叼不动")

    def test_the_ball_pack_is_still_the_ball_and_the_pets_are_untouched(self):
        ball = packs.ball_pack(self.found)
        self.assertEqual((ball.id, ball.kind, ball.mass_kg, dict(ball.tuning)), ("ball", "prop", 0.06, {}))
        self.assertEqual(set(ball.sounds), {"bounce", "grab", "charge"})
        self.assertEqual(ball.things[0].key, "ball/red", "第一款是现在这只红球")
        self.assertEqual([p.id for p in self.found.values() if p.kind == "pet"], ["border_collie", "samoyed"])
        self.assertEqual((self.found["border_collie"].things, self.found["samoyed"].things), ((), ()))
        self.assertTrue({p.id for p in packs.pets(self.found)} <= {"border_collie", "samoyed"}, "物件的包不进能选的模型")
        for pid in ("bone", "big_ball"):
            self.assertEqual(set(self.found[pid].sounds), {"bounce", "grab", "charge"}, "玩具各包自带一份声音")
            for f in self.found[pid].sound_files():
                self.assertEqual(f.parent, self.found[pid].root / "sounds")

    def test_without_the_bought_models_only_the_drawn_ball_is_listed(self):
        """新 clone 下来没有 models/props/：除了程序自己画的红球，一款都不列。"""
        from dataclasses import replace
        gone = {pid: replace(pack, things=tuple(replace(t, model=Path("/nowhere") / t.model.name if t.model else None) for t in pack.things))
                for pid, pack in self.found.items()}
        self.assertEqual([t.key for t in packs.things(gone)], ["ball/red"])

    def test_the_app_bundle_takes_whatever_models_are_there(self):
        spec = (config.ROOT / "packaging" / "Deskmate.spec").read_text(encoding="utf-8")
        self.assertIn('(ROOT / "models" / "props").glob("*.glb")', spec)
        self.assertIn('"models/props"', spec)


@unittest.skipUnless(HAS_PROPS, "models/props/*.glb not present (purchased assets)")
class RealModelTests(unittest.TestCase):
    """买来的模型在的时候：每一款都读得出、量得出画面。"""

    def test_every_style_loads_and_lays_out(self):
        listed = packs.things()
        self.assertEqual(len(listed), 29)
        self.assertEqual([t.group for t in listed], sorted((t.group for t in listed), key=packs.THING_GROUPS.index), "按组排")
        for t in listed:
            if t.model is None:
                continue
            for path in filter(None, (t.model, t.model_empty)):
                m = thing_art.load_static(path)
                self.assertGreater(m.mesh.vertex_count, 0, path)
                self.assertTrue(m.texture_png, path)
                self.assertAlmostEqual(m.mesh.bounds[0][1], 0.0, places=3, msg=f"{path.name}: 底贴地")
                self.assertAlmostEqual(m.mesh.bounds[0][0], -m.mesh.bounds[1][0], places=3, msg=f"{path.name}: 横向居中")
            m = thing_art.scaled(thing_art.load_static(t.model), thing_art.scale_of(t.spec))
            lay = thing_art.layout(m, thing_art.yaw_of(t.spec), 240.0, bool(t.spec["shadow"]))
            self.assertGreater(lay.w, 12, t.key)
            self.assertGreater(lay.h, 12, t.key)
            self.assertGreaterEqual(lay.low_m, 0.0)
            self.assertEqual(lay.frame.shadow is not None, bool(t.spec["shadow"]), t.key)

    def test_platforms_sit_inside_what_is_drawn(self):
        """台面（平顶狗屋、长椅、跷跷板、独木桥）的左右、高度在画出来的范围里。"""
        for t in packs.things():
            p = t.spec.get("platform")
            if p is None:
                continue
            m = thing_art.load_static(t.model)
            x0, x1, _, y1 = thing_art.extent(m, thing_art.yaw_of(t.spec))
            self.assertGreaterEqual(p["x0"], x0 - 0.02, t.key)
            self.assertLessEqual(p["x1"], x1 + 0.02, t.key)
            self.assertLessEqual(p["y"] * COS, y1 + 0.02, t.key)

    def test_the_bed_front_layer_is_a_real_part_of_the_bed(self):
        for t in packs.things():
            if t.role != "bed":
                continue
            m = thing_art.load_static(t.model)
            part = thing_art.front_part(m, t.spec["front_z"])
            self.assertTrue(0 < part.mesh.vertex_count < m.mesh.vertex_count, t.key)


if __name__ == "__main__":
    unittest.main()
