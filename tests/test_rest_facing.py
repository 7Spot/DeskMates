"""歇下来朝哪（widget/window.py 的 _edge_yaw、_home_yaw）：灵动交互里狗在所有屏合起来那块左右各四分之一（EDGE_SHARE）里坐下、
趴下、走进狗窝，先转过来朝中间；中间那一半照旧（站着时身子跟鼠标转到哪就朝哪歇）。灵动交互关着时按那块的竖直中线分左右。
离屏测试只有一块 800 宽的屏：左边 200 以内朝右、右边 600 以外朝左。"""
import unittest
from unittest import mock

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

import widget.window as window_mod
from tests.room_base import COLLIE, SAMOYED, RoomCase

THREE = (QRect(-1920, 0, 1920, 1080), QRect(0, 0, 1512, 982), QRect(1512, -200, 2560, 1440))   # 左外接屏、笔记本、右外接屏：合起来 −1920～4072


class _Screen:
    def __init__(self, rect: QRect):
        self._rect = rect

    def geometry(self) -> QRect:
        return self._rect


class Pointer:
    """window 里身子跟着转、歇着朝哪看的是系统的鼠标（QCursor.pos），和游乐场里假的鼠标（case.cursor）对上。"""

    def __init__(self, case):
        self.case = case

    def pos(self) -> QPoint:
        return QPoint(round(self.case.cursor[0]), round(self.case.cursor[1]))


def wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


class AllScreensTests(RoomCase):
    PACK = COLLIE

    def three_screens(self):
        return mock.patch.object(QApplication, "screens", lambda: [_Screen(r) for r in THREE])

    def at(self, x: float):
        return mock.patch.object(self.win, "dog_root", lambda: (x, 500.0))

    def test_the_edges_are_a_quarter_of_all_the_screens_together(self):
        win = self.win
        with self.three_screens():
            self.assertEqual(win._screens_span(), (-1920.0, 4072.0))
            for x, want in ((-1900.0, 330.0), (-500.0, 330.0), (-300.0, None), (1076.0, None), (2500.0, None), (2700.0, 210.0), (4000.0, 210.0)):
                with self.at(x):
                    self.assertEqual(win._edge_yaw(), want, f"x = {x}")

    def test_without_dynamic_interaction_the_middle_of_all_screens_splits_left_from_right(self):
        """左边那块屏的右半边、笔记本的右半边（中线 1076 以左）都朝右：按的是所有屏合起来的中线，不是狗在的那块屏的。"""
        win = self.win
        win.set_dynamic(False)
        with self.three_screens():
            for x, want in ((-200.0, 330.0), (1000.0, 330.0), (1200.0, 210.0), (3000.0, 210.0)):
                with self.at(x):
                    self.assertEqual(win._home_yaw(), want, f"x = {x}")


    def test_at_a_gable_house_door_it_keeps_facing_out(self):
        """尖顶狗屋的门朝哪按狗屋在它那块屏的哪半边，多块屏时和靠边不一定一致：歇在门口的（坐起来看球也是）照门朝外。"""
        pg = self.pg
        self.addCleanup(setattr, pg, "_nest", None)
        with mock.patch.object(self.win, "_edge_yaw", lambda: 210.0):
            self.assertEqual(pg._rest_face(), 210.0, "没歇在窝里：靠边朝中间")
            pg._nest = mock.Mock(yaw=330.0)
            self.assertEqual(pg._rest_face(), 330.0, "尖顶狗屋门口：照门朝外")
            pg._nest = mock.Mock(yaw=None)
            self.assertEqual(pg._rest_face(), 210.0, "狗窝、平顶狗屋：靠边朝中间")


class SamoyedEdgeTests(RoomCase):
    """萨摩耶一闲下来就坐下：在哪坐下、坐下前朝哪、鼠标在哪，看它坐好以后朝哪。"""
    PACK = SAMOYED

    def sit_at(self, x: float, facing: float, cursor_x: float) -> list:
        """放在 x、朝 facing、鼠标在 cursor_x（地面上方），推到坐好；返回一路上的姿势。"""
        dog = self.win.dog
        self.cursor = (cursor_x, self.floor_y - 60.0)
        p = mock.patch.object(window_mod, "QCursor", Pointer(self))
        p.start()
        self.addCleanup(p.stop)
        self.start_on_floor(x=x)
        dog.snap_home(facing)
        seen = []

        def sat():
            if not seen or seen[-1] != dog.posture:
                seen.append(dog.posture)
            return dog.lounge == "sitting" and dog.posture == "sitting" and not dog.transition and not dog.steps
        self.assertIsNotNone(self.step(8.0, sat), "坐好了")
        self.step(1.0)
        return seen

    def test_at_the_right_edge_it_turns_to_the_middle_before_sitting(self):
        dog = self.win.dog
        seen = self.sit_at(720.0, 330.0, self.ag.right() - 4.0)       # 靠右边、朝右，鼠标也在右边
        self.assertGreater(self.win.dog_root()[0], 600.0)
        self.assertLess(abs(wrap(dog.yaw - 210.0)), 3.0, "朝左：朝着中间坐")
        self.assertEqual(seen, ["standing", "sitting"], "站着转过来再坐，不先坐下再起来转")

    def test_at_the_left_edge_it_turns_to_the_middle_before_sitting(self):
        dog = self.win.dog
        self.sit_at(90.0, 210.0, self.ag.x() + 4.0)
        self.assertLess(self.win.dog_root()[0], 200.0)
        self.assertLess(abs(wrap(dog.yaw - 330.0)), 3.0, "朝右：朝着中间坐")

    def test_in_the_middle_half_it_sits_the_way_it_faces(self):
        dog = self.win.dog
        self.sit_at(400.0, 330.0, self.ag.right() - 4.0)
        self.assertLess(abs(wrap(dog.yaw - 330.0)), 3.0, "中间那一半照旧：朝着鼠标那边坐")


if __name__ == "__main__":
    unittest.main()
