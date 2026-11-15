"""捡球的圈（widget/ring.py：进圈才追）：怎么算（停够了满、从拿起就算不设特例、出了圈往回退、满了一直算到松手）、
圈在哪、样子（《降临》那种墨环，墨从狗身后往外聚，浅色是墨烟、深色是亮烟，地面线下面不画，淡入、散开都不过头不回弹）、
窗口（点不到、压在后面、每块屏一截不骑交界、圈不动不挪窗口、看得见就每帧重画、窗口不透明度只管出没）。不用模型，离屏平台就能跑。"""
import math
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DT = 1 / 60
QUIET = ("This plugin does not support",)   # offscreen 平台不支持 raise / lower / 窗口不透明度，Qt 每次都警告


def run(g, seconds, inside, hold=1.0):
    """推 seconds 秒，每帧记 (进度, 画出来的进度, 浓淡, 半径倍数, 满没满, 这一帧刚满)。"""
    out = []
    for _ in range(round(seconds / DT)):
        filled = g.step(DT, inside, hold)
        out.append((g.progress, g.drawn, g.alpha, g.grow, g.ready, filled))
    return out


class RingStateTests(unittest.TestCase):
    def setUp(self):
        from widget.ring import Ring
        self.g = Ring()
        self.g.restart()

    def test_a_ball_held_in_the_ring_fills_it_in_the_hold_time_and_says_so_once(self):
        g = self.g
        run(g, 0.2, False)                                       # 先在圈外拿了一会儿：不涨
        self.assertEqual(g.progress, 0.0)
        rows = run(g, 2.0, True, hold=1.0)
        full = [i for i, r in enumerate(rows) if r[5]]
        self.assertEqual(len(full), 1, "满的那一下只报一次")
        self.assertAlmostEqual((full[0] + 1) * DT, 1.0, delta=DT * 1.01, msg="停够 ring_hold_s 才满")
        self.assertTrue(g.ready)

    def test_a_ball_already_in_the_ring_needs_the_same_hold(self):
        """不设特例，从拿起那一刻开始算（拿起时球本来就在圈里也一样）。"""
        g = self.g
        rows = run(g, 2.0, True, hold=1.0)
        first = next(i for i, r in enumerate(rows) if r[4])
        self.assertAlmostEqual((first + 1) * DT, 1.0, delta=DT * 1.01)

    def test_leaving_before_full_drains_back_smoothly_and_coming_back_carries_on(self):
        from widget.ring import DRAIN_S
        g = self.g
        run(g, 0.6, True)
        self.assertAlmostEqual(g.progress, 0.6, delta=0.02)
        rows = run(g, 0.2, False)
        self.assertAlmostEqual(g.progress, 0.6 - 0.2 / DRAIN_S, delta=0.02, msg="满的 DRAIN_S 秒退空")
        drawn = [0.6] + [r[1] for r in rows]
        steps = [a - b for a, b in zip(drawn, drawn[1:])]
        self.assertTrue(all(s >= -1e-9 for s in steps), "画出来的只往回退")
        self.assertLessEqual(max(steps), DT / DRAIN_S + 1e-9, "顺着退，不一下子跳回去")
        self.assertFalse(g.ready)
        left = 1.0 - g.progress
        rows = run(g, 2.0, True)
        first = next(i for i, r in enumerate(rows) if r[4])
        self.assertAlmostEqual((first + 1) * DT, left, delta=2 * DT, msg="回来接着涨，不从头来")
        run(g, 0.0, False)

    def test_a_full_drain_takes_drain_s(self):
        from widget.ring import DRAIN_S
        g = self.g
        run(g, 0.9, True)
        rows = run(g, 0.9 * DRAIN_S + 2 * DT, False)
        self.assertEqual(rows[-1][0], 0.0)
        self.assertGreater(rows[round(0.8 * DRAIN_S / DT)][0], 0.0, "不是一下子没的")

    def test_once_full_it_stays_ready_until_the_ball_leaves_the_hand(self):
        g = self.g
        run(g, 1.2, True)
        self.assertTrue(g.ready)
        run(g, 2.0, False)
        self.assertTrue(g.ready, "满了再拿出圈也不作废")
        self.assertEqual(g.progress, 1.0)
        g.stop()
        self.assertFalse(g.ready, "松手（或关捡球、狗被打断）才作废")

    def test_it_fades_in_fills_and_dissolves_without_overshoot_or_bounce(self):
        """液态，不要 Q 弹。淡入、涨、化开、淡掉，每一样都只朝一个方向走，到头就停。"""
        from widget.ring import BURST_GROW, BURST_S
        g = self.g
        rows = run(g, 1.0 + BURST_S + 0.2, True)
        full = next(i for i, r in enumerate(rows) if r[4])
        alphas, grows, drawn = [r[2] for r in rows], [r[3] for r in rows], [r[1] for r in rows]
        self.assertTrue(all(0.0 <= a <= 1.0 for a in alphas))
        self.assertEqual(alphas[:full], sorted(alphas[:full]), "满之前只变浓")
        self.assertGreater(alphas[full - 1], 0.99, "满之前已经全出来了")
        after = alphas[full:]
        self.assertEqual(after, sorted(after, reverse=True), "化开时只变淡")
        self.assertEqual(alphas[full + round(BURST_S / DT)], 0.0, "化开 BURST_S 秒淡没")
        self.assertEqual(grows, sorted(grows), "只往外化开，不缩回来")
        self.assertLessEqual(max(grows), 1.0 + BURST_GROW + 1e-9, "不过头")
        self.assertEqual(drawn, sorted(drawn))
        self.assertLessEqual(max(drawn), 1.0)

    def test_letting_go_fades_it_where_it_is_and_clears_it_once_gone(self):
        from widget.ring import FADE_S
        g = self.g
        run(g, 0.5, True)
        g.stop()
        rows = run(g, FADE_S + DT, None)
        alphas = [r[2] for r in rows]
        self.assertEqual(alphas, sorted(alphas, reverse=True))
        self.assertEqual(alphas[-1], 0.0)
        self.assertEqual((g.progress, g.drawn, g.burst, g.counting), (0.0, 0.0, 0.0, False), "看不见了：下一圈从头来")

    def test_picking_up_again_while_it_dissolves_starts_from_invisible(self):
        from widget.ring import BURST_S
        g = self.g
        run(g, 1.0 + BURST_S / 2, True)
        self.assertGreater(g.alpha, 0.1)
        g.stop()
        g.restart()
        self.assertEqual(g.alpha, 0.0, "不会化开到一半又变回实心的")
        self.assertEqual(g.grow, 1.0)
        rows = run(g, 0.3, True)
        self.assertEqual([r[2] for r in rows], sorted(r[2] for r in rows), "重新淡入")
        self.assertFalse(g.ready)
        self.assertLess(g.progress, 0.35)

    def test_with_reduce_motion_it_only_fades(self):
        from widget.ring import BURST_S
        g = self.g
        g.restart(still=True)
        rows = run(g, 1.0 + BURST_S, True)
        self.assertEqual({r[3] for r in rows}, {1.0}, "不变大")
        self.assertEqual(rows[-1][2], 0.0, "照样淡掉")


class RingGeometryTests(unittest.TestCase):
    def test_where_the_ring_is_and_what_counts_as_inside(self):
        from widget.ring import in_ring, ring_shape
        s = ring_shape(500.0, 800.0, 192.0, 1.0)
        self.assertEqual((s.cx, s.cy, s.r, s.floor), (500.0, 704.0, 192.0, 800.0), "圆心在身子正中，半径按 ring_size 个身高")
        self.assertTrue(in_ring(s, 500.0 + 192.0, 704.0), "圆上算")
        self.assertFalse(in_ring(s, 500.0 + 193.0, 704.0))
        self.assertTrue(in_ring(s, 560.0, 800.0), "贴着地面算")
        self.assertFalse(in_ring(s, 560.0, 801.0), "地面线下面不算")
        self.assertEqual(ring_shape(500.0, 800.0, 192.0, 1.5).r, 288.0, "ring_size 是几个身高")

    def test_the_window_area_holds_the_spreading_ring_and_stops_at_the_floor(self):
        from widget.ring import BURST_GROW, INK_R1, ring_extent, ring_shape
        s = ring_shape(500.3, 800.6, 192.0, 1.0)
        e = ring_extent(s)
        far = s.r * INK_R1 * (1.0 + BURST_GROW) + 0.25 * s.r
        self.assertLessEqual(e.left(), s.cx - far, "散开到最大连烟都在里面")
        self.assertGreaterEqual(e.right(), s.cx + far)
        self.assertLessEqual(e.top(), s.cy - far)
        self.assertLessEqual(e.bottom(), s.floor + 1, "地面线下面不要")
        self.assertGreaterEqual(e.bottom(), s.floor)

    def test_the_default_ring_is_a_little_smaller(self):
        """默认 0.9 个身高；看得见的墨环比算不算进圈的那一圈还小：0.82 → 0.70 个圈半径，
        带宽按比例跟着收；算不算进圈（ring_size、in_ring）不变，手不用放得更准。"""
        from widget import tuning
        from widget.ring import INK_R0, INK_R1, INK_W0, INK_W1, in_ring, ring_shape
        self.assertEqual(next(p for p in tuning.PET_PARAMS if p.key == "ring_size").default, 0.9)
        self.assertEqual(INK_R1, 0.70)
        self.assertAlmostEqual(INK_W1 / INK_R1, 0.111 / 0.82, delta=0.002, msg="带宽和环的比例没变")
        self.assertAlmostEqual(INK_W0 / INK_W1, 0.056 / 0.111, delta=0.01)
        self.assertAlmostEqual(INK_R0 / INK_R1, 0.245 / 0.82, delta=0.005, msg="从狗身后涌出来的那一段也按比例")
        s = ring_shape(500.0, 800.0, 192.0, 0.9)
        self.assertTrue(in_ring(s, 500.0 + 0.95 * s.r, s.cy), "墨环外面、圈半径以内照样算进圈")


class _Painting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(q in msg for q in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])

    def look(self, a=0.8, dark=False, r=180.0, t=0.4, cx=300.0, cy=250.0, floor=380.0, shown=1.0):
        from widget.ring import INK_R1, INK_W1, RingLook
        return RingLook(cx, cy, r, floor, 28.8, INK_R1 * r, INK_W1 * r, a, t, 0.0, dark, shown)


class RingPaintTests(_Painting):
    def paint(self, look):
        from PySide6.QtCore import QRectF, Qt
        from PySide6.QtGui import QImage, QPainter
        from widget.ring import paint_ink
        img = QImage(600, 500, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        paint_ink(p, look, QRectF(0, 0, 600, 500))
        p.end()
        return img

    def ring_pixels(self, img, look):
        """墨环上（看得见的那一圈）一圈点的颜色：地面线上面那一段。"""
        out = []
        for d in range(0, 181, 6):
            x = look.cx + look.vr * math.cos(math.radians(d))
            y = look.cy - look.vr * math.sin(math.radians(d))
            out.append(img.pixelColor(round(x), round(y)))
        return out

    def test_light_mode_is_ink_smoke_around_the_dog_and_nothing_below_the_floor(self):
        look = self.look()
        img = self.paint(look)
        ring = self.ring_pixels(img, look)
        self.assertGreater(sum(c.alphaF() for c in ring) / len(ring), 0.3, "一整圈墨烟")
        self.assertLess(sum(c.lightnessF() for c in ring if c.alphaF() > 0.3) / max(1, sum(1 for c in ring if c.alphaF() > 0.3)), 0.6, "浅色外观：墨色的")
        self.assertLess(img.pixelColor(round(look.cx), round(look.cy)).alphaF(), 0.05, "里面是空的（不罩住狗）")
        below = [img.pixelColor(x, y).alpha() for y in range(round(look.floor) + 1, 500, 3) for x in range(0, 600, 5)]
        self.assertEqual(max(below), 0, "地面线下面一点都不画")

    def test_the_ink_ring_sits_at_seven_tenths_of_the_ring_and_fades_out_before_the_old_radius(self):
        """满的墨环：最浓的一圈在 0.70 个圈半径上；0.82 那里只剩一点飘出去的烟，再往外几乎没有（看着比 60 小一圈）。"""
        look = self.look()
        img = self.paint(look)

        def mean_alpha(f):
            a = [img.pixelColor(round(look.cx + f * look.r * math.cos(math.radians(d))), round(look.cy - f * look.r * math.sin(math.radians(d)))).alphaF()
                 for d in range(0, 181, 3)]
            return sum(a) / len(a)
        self.assertAlmostEqual(look.vr / look.r, 0.70, places=6)
        self.assertGreater(mean_alpha(0.70), 0.4)
        self.assertGreater(mean_alpha(0.70), max(mean_alpha(0.62), mean_alpha(0.78)), "最浓的一圈就在 0.70")
        self.assertLess(mean_alpha(0.82), 0.15, "原来墨环在的地方只剩淡淡的烟")
        self.assertLess(mean_alpha(0.92), 0.06)

    def test_dark_mode_is_light_smoke(self):
        look = self.look(dark=True)
        ring = [c for c in self.ring_pixels(self.paint(look), look) if c.alphaF() > 0.1]
        self.assertTrue(ring, "深色外观也看得见")
        self.assertGreater(sum(c.lightnessF() for c in ring) / len(ring), 0.7, "深色外观：亮烟")

    def test_an_empty_ring_draws_nothing(self):
        img = self.paint(self.look(a=0.0))
        self.assertEqual(max(img.pixelColor(x, y).alpha() for y in range(0, 500, 4) for x in range(0, 600, 4)), 0)


class RingWindowTests(_Painting):
    def make(self, screen=(0, 0, 1000, 800)):
        from PySide6.QtCore import QRect
        from widget.ring import RingWindow
        home = SimpleNamespace(geometry=lambda: QRect(*screen))
        rw = RingWindow(home)
        self.addCleanup(rw.hide)
        return rw

    def shape(self, cx=500.0):
        from widget.ring import ring_shape
        return ring_shape(cx, 700.0, 192.0, 1.0)

    def sync(self, rw, s, alpha=1.0, shown=1.0, t=0.0):
        from widget.ring import ring_extent
        look = self.look(cx=s.cx, cy=s.cy, r=s.r, floor=s.floor, shown=shown, t=t)
        rw.sync(look, ring_extent(s), alpha)
        return look

    def test_it_cannot_be_clicked_and_goes_behind_the_dog(self):
        from PySide6.QtCore import Qt
        rw = self.make()
        flags = rw.windowFlags()
        self.assertTrue(flags & Qt.WindowTransparentForInput, "点不到：鼠标直接落到后面")
        self.assertTrue(flags & Qt.WindowDoesNotAcceptFocus)
        from widget import native
        with mock.patch.object(native, "set_level") as level:
            self.sync(rw, self.shape())
        self.assertTrue(rw.isVisible())
        level.assert_called_once_with(rw, native.LEVEL_RING)     # 最后面那一层：物件、狗、球都在它前面

    def test_each_screen_draws_only_its_own_part_and_no_window_crosses_a_screen_edge(self):
        """一个窗口只显示在一块屏上，也不能骑在两块屏中间：交界旁边的圈两块屏各画一截。"""
        from widget.ring import ring_extent
        left, right = self.make((0, 0, 1000, 800)), self.make((1000, 0, 1000, 800))
        s = self.shape(cx=980.0)
        for rw in (left, right):
            self.sync(rw, s)
        self.assertTrue(left.isVisible() and right.isVisible(), "两截都画")
        self.assertLessEqual(left.geometry().right(), 999)
        self.assertGreaterEqual(right.geometry().left(), 1000)
        e = ring_extent(s)
        self.assertEqual(left.geometry().united(right.geometry()), e, "两截合起来就是整个圈")
        far = self.shape(cx=200.0)
        self.sync(right, far)
        self.assertFalse(right.isVisible(), "圈不在这块屏上：收起来")

    def test_it_hides_once_faded_out(self):
        rw = self.make()
        self.sync(rw, self.shape())
        self.assertTrue(rw.isVisible())
        self.sync(rw, self.shape(), alpha=0.0)
        self.assertFalse(rw.isVisible())
        rw.sync(None, None, 1.0)
        self.assertFalse(rw.isVisible())

    def test_it_is_placed_once_while_the_ring_stays_put(self):
        rw = self.make()
        s = self.shape()
        with mock.patch.object(rw, "setGeometry", wraps=rw.setGeometry) as placed:
            for k in range(20):
                self.sync(rw, s, t=k / 60)
            self.assertEqual(placed.call_count, 1, "出来那一下摆一次，之后不挪（挪一次要等窗口系统）")
            self.sync(rw, self.shape(cx=520.0))
            self.assertEqual(placed.call_count, 2, "圈挪了（狗骑在挪动的窗口上）才挪")

    def test_the_smoke_moves_so_it_repaints_every_frame_and_the_window_opacity_only_follows_the_fade_in(self):
        rw = self.make()
        s = self.shape()
        self.sync(rw, s, shown=0.2)
        with mock.patch.object(rw, "update") as update, mock.patch.object(rw, "setWindowOpacity") as opacity:
            self.sync(rw, s, shown=0.6, t=0.1)
            self.sync(rw, s, shown=0.6, t=0.2)
            self.sync(rw, s, shown=1.0, t=0.3)
        self.assertEqual(update.call_count, 3, "烟每帧都在动：看得见就每帧重画")
        self.assertEqual([c.args[0] for c in opacity.call_args_list], [0.6, 1.0], "窗口的不透明度只跟着出没，变了才改，到 1 一定改到")

    def test_it_paints_the_part_of_the_ring_on_its_screen(self):
        rw = self.make()
        self.sync(rw, self.shape())
        img = rw.grab().toImage()
        alphas = [img.pixelColor(x, y).alpha() for y in range(0, img.height(), 4) for x in range(0, img.width(), 4)]
        self.assertGreater(max(alphas), 60, "画出了墨环")


if __name__ == "__main__":
    unittest.main()
