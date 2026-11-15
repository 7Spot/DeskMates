import unittest

from widget.geometry import (SHADOW_ALPHA, frame_period, initial_position, keep_on_screens, place_relative, project, relative_position, shadow_ellipse,
                             smoothstep)

SCREENS = [(0, 0, 1512, 944), (1512, 0, 1920, 1080)]   # 主屏 + 右边一块外接屏


class InitialPositionTests(unittest.TestCase):
    def test_saved_position_on_a_screen_is_kept(self):
        self.assertEqual(initial_position((100, 100), (352, 256), SCREENS), (100, 100))
        self.assertEqual(initial_position((2000, 300), (352, 256), SCREENS), (2000, 300), "外接屏上的位置也认")

    def test_saved_position_off_every_screen_falls_back_to_top_right(self):
        self.assertEqual(initial_position((5000, 5000), (352, 256), SCREENS), (1512 - 352 - 24, 24))
        self.assertEqual(initial_position((-2000, 100), (352, 256), SCREENS), (1512 - 352 - 24, 24))

    def test_no_record_goes_top_right_and_no_screens_goes_origin(self):
        self.assertEqual(initial_position(None, (352, 256), SCREENS), (1136, 24))
        self.assertEqual(initial_position(None, (352, 256), []), (0, 0))


class RelativePositionTests(unittest.TestCase):
    """位置按屏幕比例记（记绝对坐标的话，宽屏左半边的位置到了笔记本上会落在右半边）。"""

    def test_round_trip_on_the_same_screen(self):
        screen = (0, 25, 1512, 900)
        self.assertEqual(place_relative(relative_position((600, 500), (352, 240), screen), (352, 240), screen), (600, 500))

    def test_left_half_of_the_ultrawide_stays_left_half_on_the_laptop(self):
        rel = relative_position((1094, 686), (352, 240), (0, 25, 3440, 1385))   # 宽屏上中心 1270，左半边
        x, y = place_relative(rel, (352, 240), (0, 33, 1512, 879))
        self.assertLess(x + 176, 756, "到笔记本上还在左半边")
        self.assertAlmostEqual((y + 240 - 33) / 879, rel[1], delta=0.01, msg="底边同样的比例")

    def test_kept_on_screen_but_may_hang_half_a_window_below(self):
        self.assertEqual(place_relative((1.3, 1.4), (352, 240), (0, 0, 1512, 982)), (1512 - 352, 982 + 120 - 240), "右边整个放进来，底边最多低出半个窗口")
        self.assertEqual(place_relative((-0.5, -1.0), (352, 240), (0, 0, 1512, 982)), (0, 0), "左边、顶边不出屏")


class FramePeriodTests(unittest.TestCase):
    """动画节拍跟屏幕刷新率，每帧在屏幕上停的刷新次数一样。"""

    def test_whole_refreshes_per_frame_and_at_most_100_fps(self):
        for hz, fps in ((120, 60), (85, 85), (60, 60), (144, 72), (75, 75), (50, 50), (240, 80)):
            period = frame_period(hz, 60, 100)
            self.assertAlmostEqual(1 / period, fps, places=6, msg=f"{hz} 赫兹")
            self.assertAlmostEqual(period * hz, round(period * hz), places=9, msg="每帧停整数次刷新")

    def test_unknown_refresh_rate_falls_back(self):
        self.assertAlmostEqual(frame_period(0.0, 60, 100), 1 / 60)


class ProjectTests(unittest.TestCase):
    def test_ground_origin_lands_on_the_ground_line(self):
        self.assertEqual(project((0.0, 0.0, 0.0), 240, 46, 10, 352), (176, 46))

    def test_up_goes_up_and_towards_camera_goes_down(self):
        x, y_up = project((0.0, 0.5, 0.0), 240, 46, 10, 352)
        self.assertGreater(y_up, 46)
        x, y_near = project((0.0, 0.0, 0.5), 240, 46, 10, 352)
        self.assertLess(y_near, 46, "俯视时靠近镜头的点在屏幕上更低")


class ShadowTests(unittest.TestCase):
    FOOT = [(-0.5, -0.1), (0.5, 0.1), (0.0, 0.0)]

    def test_on_the_ground_is_a_flat_ellipse_under_the_dog(self):
        s = shadow_ellipse(self.FOOT, 0.0, 240, 46, 10, 352)
        self.assertAlmostEqual(s.cx, 176)
        self.assertAlmostEqual(s.cy, 46, delta=1)
        self.assertGreater(s.rx, s.ry)
        self.assertAlmostEqual(s.alpha, SHADOW_ALPHA)

    def test_jumping_shrinks_and_fades_the_shadow(self):
        ground, air = shadow_ellipse(self.FOOT, 0.0, 240, 46, 10, 352), shadow_ellipse(self.FOOT, 0.1, 240, 46, 10, 352)
        self.assertLess(air.rx, ground.rx)
        self.assertLess(air.ry, ground.ry)
        self.assertLess(air.alpha, ground.alpha)
        self.assertEqual((air.cx, air.cy), (ground.cx, ground.cy), "阴影留在地上，不跟着跳")

    def test_no_footprint_no_shadow(self):
        self.assertIsNone(shadow_ellipse([], 0.0, 240, 46, 10, 352))


class KeepOnScreensTests(unittest.TestCase):
    ONE = [(0, 0, 1000, 800)]
    LG_AND_MAC = [(0, 0, 3440, 1440), (-1512, 458, 1512, 982)]    # MacBook 在 LG 左边、比 LG 矮：LG 左边高出来的那段是墙
    STACKED = [(0, 0, 1000, 800), (0, 800, 1000, 800)]

    def test_the_body_stays_inside_one_screen(self):
        self.assertEqual(keep_on_screens(self.ONE, -50, 400, 100, 200, 10), (100, 400), "左边")
        self.assertEqual(keep_on_screens(self.ONE, 1050, 400, 100, 200, 10), (900, 400), "右边")
        self.assertEqual(keep_on_screens(self.ONE, 500, 100, 100, 200, 10), (500, 200), "头顶")
        self.assertEqual(keep_on_screens(self.ONE, 500, 900, 100, 200, 10), (500, 790), "脚下留出影子")
        self.assertEqual(keep_on_screens(self.ONE, -50, 900, 100, 200, 10), (100, 790), "角上")
        self.assertEqual(keep_on_screens(self.ONE, 500, 400, 100, 200, 10), (500, 400), "在里面不动")

    def test_a_neighbour_screen_lets_the_body_cross_where_it_really_continues(self):
        self.assertEqual(keep_on_screens(self.LG_AND_MAC, 10, 1000, 100, 300, 10), (10, 1000), "这个高度 MacBook 也有：能跨过去")
        self.assertEqual(keep_on_screens(self.LG_AND_MAC, -10, 1000, 100, 300, 10), (-10, 1000))

    def test_the_part_of_a_taller_screen_that_sticks_out_is_still_a_wall(self):
        self.assertEqual(keep_on_screens(self.LG_AND_MAC, 10, 600, 100, 300, 10), (100, 600), "头高出 MacBook 上沿：LG 左边还是边界")
        self.assertEqual(keep_on_screens(self.LG_AND_MAC, -200, 600, 100, 300, 10), (-200, 758), "在 MacBook 上：头顶到它的上沿")

    def test_stacked_screens_are_connected(self):
        self.assertEqual(keep_on_screens(self.STACKED, 500, 850, 100, 200, 10), (500, 850), "跨在上下两块屏之间")
        self.assertEqual(keep_on_screens(self.STACKED, 500, 1700, 100, 200, 10), (500, 1590), "下面那块的底边还是边界")
        self.assertEqual(keep_on_screens(self.STACKED, 50, 850, 100, 200, 10), (100, 850), "横着也不出去")

    def test_a_narrower_screen_below_blocks_a_body_that_would_stick_out(self):
        screens = [(0, 0, 1000, 800), (200, 800, 600, 800)]
        self.assertEqual(keep_on_screens(screens, 250, 850, 100, 200, 10), (250, 790), "下面那块窄：身子放不下就不让下去")
        self.assertEqual(keep_on_screens(screens, 500, 850, 100, 200, 10), (500, 850), "放得下就能跨")

    def test_a_root_outside_every_screen_comes_back_to_the_nearest(self):
        self.assertEqual(keep_on_screens(self.ONE, 5000, 5000, 100, 200, 10), (900, 790))

    def test_no_screens_changes_nothing(self):
        self.assertEqual(keep_on_screens([], 5, 6, 100, 200), (5, 6))


class SmoothstepTests(unittest.TestCase):
    def test_endpoints_and_middle(self):
        self.assertEqual(smoothstep(-1), 0.0)
        self.assertEqual(smoothstep(2), 1.0)
        self.assertAlmostEqual(smoothstep(0.5), 0.5)

    def test_column_top_counts_stacked_screens_only_in_that_column(self):
        from widget.geometry import column_top
        wide, mac = (0, 0, 3440, 1440), (745, -982, 1512, 982)
        self.assertEqual(column_top([wide, mac], 1500, 800), -982, "正上方有屏：能拖到上面那块的顶")
        self.assertEqual(column_top([wide, mac], 200, 800), 0, "这一列上面没屏：到这块屏的顶")
        side = (-1512, 458, 1512, 982)
        self.assertEqual(column_top([wide, side], -300, 800), 458, "左边那块屏比较矮：这一列到它的顶")
        self.assertEqual(column_top([wide, side], 300, 800), 0)
        self.assertIsNone(column_top([wide], 5000, 800), "这一列没有屏")
