"""换姿势时窗口不改大小，起身那几帧窗口不跟着一帧帧改。
真机上量到的（tools/selftest_playground.py --only rise）：萨摩耶趴着拿起球坐起来，窗口跟着「···」按钮平滑上去的高度连着改了 25 次、每次多画一帧；
 Metal 窗口改大小主线程还要等 67～95 毫秒。窗口一直按站、坐、趴、睡里最高的那个（连起身坐下的过渡片段）留高度
（dog.posture_tops），按钮按最高的那个姿势留位置（hover.room_m），换姿势不改窗口；跳、高的随机动作照旧临时长。
2 倍大小、窗口不贴着屏幕底（真机上屏幕底下还有程序坞那一条，窗口能往下伸）时坐着、站着都比基础高度高。"""
import unittest
from unittest import mock

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from tests.panel_base import PanelCase
from tests.room_base import COLLIE, HAS, SAMOYED
from tests.test_closeup import Driven


class RiseCase(Driven, PanelCase):
    PET = COLLIE
    SCALE = 2.0

    def setUp(self):
        from widget import packs, temper
        self.enterContext(mock.patch.object(temper, "wander_every", lambda tune: (1e9, 1e9)))   # 别自己溜达走
        self.enterContext(mock.patch.object(packs, "choose_pet", lambda *a, **k: packs.discover()[self.PET]))
        super().setUp()
        self.drive_setup()
        w = self.win
        self.assertEqual(w.pack.id, self.PET)
        w.show()
        w.set_scale(self.SCALE)

    def lie_down(self):
        w = self.win
        w.dog.set_rest_posture("lying")
        self.assertIsNotNone(self.tick(10.0, lambda: w.dog.posture == "lying" and not w.dog.transition), "先趴好")
        self.tick(3.0)                                            # 窗口按趴着的高度缩回来（SHRINK_DELAY）

    def heights_after(self, start, seconds):
        """start() 之前一行、之后每帧一行：窗口的高度和底边 [(片段, 高, 底边)]。"""
        w = self.win
        rows = [(w.dog.player.name, w.height(), w.y() + w.height())]
        start()
        self.tick(seconds, each=lambda: rows.append((w.dog.player.name, w.height(), w.y() + w.height())))
        return rows

    def assert_still(self, rows, what):
        heights = [h for _, h, _ in rows]
        self.assertEqual(len(set(heights)), 1, f"{what}：换姿势时窗口不改大小：{heights[:60]}")
        self.assertEqual(len({b for _, _, b in rows}), 1, f"{what}：底边不动")
        w = self.win
        self.assertLessEqual(w._height_needed(), heights[0], f"{what}：起来以后要的高度趴着时就留够了")


@unittest.skipUnless(HAS[COLLIE], "models/collie.glb not present (purchased asset)")
class CollieRiseTests(RiseCase):
    """边牧（狗自己待着，用户换姿势）：趴 → 站、趴 → 坐，窗口都不改大小。"""

    def setUp(self):
        super().setUp()
        self.win.place_scene(400.0, 560.0)                        # 屏幕中间：窗口不贴屏幕底，脚下那一截留得满
        self.lie_down()

    def test_lying_to_standing(self):
        rows = self.heights_after(lambda: self.win.dog.set_rest_posture("standing"), 1.5)
        self.assertEqual(rows[1][0], "Lie_belly_end")
        self.assert_still(rows, "趴 → 站")

    def test_lying_to_sitting(self):
        rows = self.heights_after(lambda: self.win.dog.set_rest_posture("sitting"), 2.0)
        self.assertIn("Sitting_start", [c for c, _, _ in rows])
        self.assert_still(rows, "趴 → 坐")


@unittest.skipUnless(HAS[SAMOYED], "models/samoyed.glb not present (purchased asset)")
class SamoyedRiseTests(CollieRiseTests):
    PET = SAMOYED


@unittest.skipUnless(HAS[SAMOYED], "models/samoyed.glb not present (purchased asset)")
class SamoyedPickupTests(RiseCase):
    """灵动交互里萨摩耶趴着、你拿起球：坐起来看着。按钮照旧平滑滑上去、一直放得下。"""
    PET = SAMOYED
    DYNAMIC = True

    def test_the_menu_button_glides_up_inside_the_window(self):
        w = self.win
        pg, hover = w.playground, w.hover
        ag = QApplication.primaryScreen().availableGeometry()
        w.place_scene(400.0, ag.y() + ag.height() - 18.0 * w.world_scale)
        pg.start()
        self.addCleanup(pg.stop)                                 # 球、圈的窗口收起来：留在屏上会挡住后面测试的悬停（PanelCase 只藏主窗口和卡片）
        plan = pg._rest_plan()
        pg._idle_for = plan[0] + plan[1] + 1.0
        self.assertIsNotNone(self.tick(10.0, lambda: w.dog.posture == "lying" and not w.dog.transition), "先趴好")
        self.tick(3.0)
        hover.set_hover(True)                                    # 鼠标在狗身上、没冲着按钮：按钮看得见，跟着狗平滑地挪（看不见时直接到位）
        hover.since = -1.0e9                                     # 早就悬停着了（这里的钟是假的，每帧走 DT）
        self.tick(0.5)
        b = pg.ball
        lifts = []
        pg.ball_press(QPointF(b.x, b.y))
        pg.ball_drag(QPointF(pg.roam.wx - 0.35 * w.ppm, pg.roam.wy - 0.55 * w.ppm))
        self.tick(1.0, each=lambda: lifts.append((hover.lift, hover.min_height(w.ground_px - w.draw_offset[1]), w.height())))
        pg.ball_release(QPointF(*pg._pointer))                   # 手不动松开：球原地掉下去（拿着不放会把后面的测试带歪）
        self.assertEqual(w.dog.lounge, "sitting", "拿起球：趴着的坐起来看着")
        steps = [b2[0] - a[0] for a, b2 in zip(lifts, lifts[1:])]
        self.assertGreater(lifts[-1][0], lifts[0][0], "按钮跟着坐起来的高度上去了")
        self.assertLess(max(steps), 0.25 * (lifts[-1][0] - lifts[0][0]), "一帧只走一小段：平滑滑上去")
        self.assertTrue(all(need <= h for _, need, h in lifts), "按钮一直放得下")


if __name__ == "__main__":
    unittest.main()
