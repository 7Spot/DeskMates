"""显卡上的相机与 CPU 投影共用亚像素原点；无需窗口，不碰显卡。"""
import unittest
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QVector3D

import config
from widget.geometry import prepare_bound_vertices, project, projected_mesh_center
from widget.gltf import IDENTITY, rot_y_mat, transform_point
from widget.render import DogRenderer, ELEVATION, Frame, make_frame, view_proj


class RenderGeometryTests(unittest.TestCase):
    def test_camera_matches_cpu_projection_with_fractional_origin(self):
        for width, height, ppm, ground, offset in (
            (352, 240, 240.0, 46.0, (0.0, 0.0)),
            (401, 347, 273.728, 52.4645, (-0.5, 0.437)),
            (270, 112, 72.0, 13.8, (0.25, -0.49)),
        ):
            matrix = view_proj(width, height, ppm, ground, offset)
            for point in ((0.0, 0.0, 0.0), (0.31, 0.27, -0.11), (-0.4, 0.8, 0.2)):
                clip = matrix.map(QVector3D(*point))
                gpu = ((clip.x() + 1) * width / 2, (clip.y() + 1) * height / 2)
                cpu = project(point, ppm, ground, ELEVATION, width, offset)
                for actual, expected in zip(gpu, cpu):
                    self.assertAlmostEqual(actual, expected, delta=0.00005)

    def test_shadow_and_dog_receive_the_same_screen_translation(self):
        pose = SimpleNamespace(root=IDENTITY, joints=[], footprint=[(-0.4, -0.1), (0.5, 0.2)], lift=0.0, props=())
        base = make_frame(pose, 0.0, 240.0, 46.0, 353)
        shifted = make_frame(pose, 0.0, 240.0, 46.0, 353, (0.35, -0.42))
        self.assertAlmostEqual(shifted.shadow.cx - base.shadow.cx, 0.35)
        self.assertAlmostEqual(shifted.shadow.cy - base.shadow.cy, 0.42, msg="阴影的 y 从底算，向下偏移要反号")
        self.assertEqual((shifted.shadow.rx, shifted.shadow.ry), (base.shadow.rx, base.shadow.ry))
        self.assertEqual(shifted.offset, (0.35, -0.42))

    def test_mesh_center_uses_weighted_skinning_root_and_camera_projection(self):
        points = [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 1.0)]
        positions = [v for point in points + [points[0]] for v in point]
        vertices = prepare_bound_vertices(positions, [0, 1, 0, 0] * 4, [0.25, 0.75, 0, 0] * 4)
        self.assertEqual(len(vertices), 3, "三角面展开的重复顶点只投影一次")
        moved = list(IDENTITY)
        moved[12:15] = [2.0, 1.0, -1.0]
        root = list(rot_y_mat(90.0))
        root[12:15] = [0.3, 0.5, -0.2]
        actual = projected_mesh_center(vertices, [IDENTITY, moved], root, 30.0)
        projected = []
        for x, y, z in points:
            world = transform_point(root, (x + 1.5, y + 0.75, z - 0.75))
            projected.append(project(world, 1.0, 0.0, 30.0, 0.0))
        expected = tuple((min(p[i] for p in projected) + max(p[i] for p in projected)) / 2 for i in range(2))
        for point, want in zip(actual, expected):
            self.assertAlmostEqual(point, want, places=10)
        self.assertIsNone(projected_mesh_center((), [IDENTITY], root, 30.0))

    @unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
    def test_renderers_of_one_model_share_its_vertex_and_outline_tables(self):
        """顶点表、描边表按模型量一次记在模型上（gltf.Model.measured）：主画布、每块屏的窗口、出图那套各建一套渲染器也不重算；
        换模型时原地换的渲染器拿新模型的那份。"""
        from widget import gltf
        from widget.render import bound_vertices, outline_weights
        model = gltf.load(config.MODEL_PATH)
        a, b = DogRenderer(model), DogRenderer(model)
        self.assertIs(a._bound_vertices, b._bound_vertices)
        self.assertIs(a._outline_weights(), b._outline_weights())
        self.assertIs(bound_vertices(model), model.measured["bound_vertices"])
        self.assertIs(outline_weights(model), model.measured["outline_weights"])
        self.assertEqual(len(outline_weights(model)), model.mesh.vertex_count)
        self.assertIn(0.0, outline_weights(model), "眼、舌、嘴、鼻那几块不描边")

    def test_set_model_swaps_the_mesh_in_place_without_the_gpu(self):
        """原地换模型（换模型不重启）：模型、顶点表当场换，投影中心按新网格；显卡上的顶点缓冲标成下一次 draw() 换（离屏没有显卡，
        显卡那一半在真机和 dist.nosync/方案-1113/measure_swap_inplace.py 上看）。没 init 过也能换；换成同一个不标。"""
        def model(points, gain=1.0):
            mesh = SimpleNamespace(positions=[v for p in points for v in p], joints=[0, 0, 0, 0] * len(points),
                                   weights=[1, 0, 0, 0] * len(points))
            return SimpleNamespace(mesh=mesh, gain=gain)
        small, big = model([(-1, 0, 0), (1, 2, 0)]), model([(-3, 0, 0), (5, 4, 0)], gain=1.4)
        renderer = DogRenderer(small)
        frame = Frame(IDENTITY, [IDENTITY], None, 0.0, 1.0, 240.0, 46.0)
        before = renderer.visual_center(frame)
        renderer.set_model(small)
        self.assertFalse(renderer._mesh_dirty, "同一个模型：什么都不做")
        renderer.set_model(big)
        self.assertIs(renderer.model, big)
        self.assertTrue(renderer._mesh_dirty, "顶点缓冲下一次 draw() 换")
        self.assertEqual(renderer._bound_vertices, prepare_bound_vertices(big.mesh.positions, big.mesh.joints, big.mesh.weights))
        after = renderer.visual_center(frame)
        self.assertNotEqual(after, before)
        self.assertAlmostEqual(after[0], 1.0, msg="新网格的中心：(−3 + 5) / 2")
        self.assertIsNone(renderer.rhi, "没碰显卡")
        self.assertIsNone(renderer.coat_image, "毛色贴图不碰：等 look 换上这只的")

    def test_visual_center_excludes_shadow_and_props_and_does_not_touch_the_gpu(self):
        mesh = SimpleNamespace(positions=[-1, 0, 0, 1, 2, 0], joints=[0, 0, 0, 0] * 2,
                               weights=[1, 0, 0, 0] * 2)
        renderer = DogRenderer(SimpleNamespace(mesh=mesh))
        frame = Frame(IDENTITY, [IDENTITY], None, 0.0, 1.0, 240.0, 46.0)
        expected = renderer.visual_center(frame)
        other = Frame(IDENTITY, [IDENTITY], object(), 1.0, 0.6, 960.0, 184.0, (object(),), (0.3, -0.5))
        self.assertEqual(renderer.visual_center(other), expected,
                         "只看狗的蒙皮网格；旁边的道具、地面阴影、缩放和残差都不改变模型空间中心")
        self.assertIsNone(renderer.rhi, "没在任何 QRhi 上建过东西")
