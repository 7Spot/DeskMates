"""「关于」页和主页面 ↔ 关于页的过渡动画（widget/about.py、widget/about_art.py）：
app 图标是耳朵 B（没有眼珠）；关于页是无框的图、名字、版本、一句话、两个链接，顶部栏没有名字胶囊；
进来：圆里的 D、M 变细成两根线描出猫狗，地面、动物、字一起出来，走完交还给关于页时一个像素不差；
回去：动画先倒着走，线快回到圆里才真的换回主页面；任何时候点返回 / 再点进来都不跳（进度钟的速度平滑地掉头）。
逐帧推（1/60 秒，不真等）。offscreen 平台，不出声。"""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF
from PySide6.QtGui import QColor, QImage, QPainterPath, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from tests.panel_base import PanelCase
from widget import about, about_art, dm_shapes, marks, native


def shot(w: QWidget, dpr: float = 1.0) -> QImage:
    img = QImage(round(w.width() * dpr), round(w.height() * dpr), QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(QColor("#DCD8D0"))
    w.render(img, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return img


def differ(a: QImage, b: QImage, rect: QRect, over: int = 0) -> int:
    """rect 里有几个像素差得比 over 多（四个通道里最大的那个差）。"""
    n = 0
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(rect.left(), rect.right() + 1):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            if max(abs(ca.red() - cb.red()), abs(ca.green() - cb.green()), abs(ca.blue() - cb.blue()), abs(ca.alpha() - cb.alpha())) > over:
                n += 1
    return n


class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dog_has_one_ear_and_plain_white_eyes(self):
        """定稿是耳朵 B：藏在猫后面那只耳朵不要，所有尺寸狗的眼睛都是实心白点。"""
        self.assertFalse(hasattr(dm_shapes, "DOG_PUPILS"))
        img = marks.app_icon(1024)
        whole = dm_shapes.dog_cat()
        fit = dm_shapes.fitting(whole.boundingRect(), *dm_shapes.SCENE_FIT)
        for eye in dm_shapes.DOG_EYES:
            c = fit.map(QPointF(*eye))
            self.assertGreater(img.pixelColor(round(c.x()), round(c.y())).lightness(), 200, "眼睛正中是白的（没有眼珠）")
        far = dm_shapes.blob((486, 378), 46, 86, -50)               # 原来（耳朵 A）藏在猫后面那只耳朵和它里侧那道缝
        below = QPainterPath()
        below.addRect(QRectF(150, 352, 600, 600))
        seam = dm_shapes.stroke(far, 28).subtracted(far).intersected(below).intersected(marks.app_pieces()["dog"])
        b = seam.boundingRect()
        pts = [QPointF(b.left() + b.width() * i / 20, b.top() + b.height() * j / 20) for i in range(21) for j in range(21)]
        inside = [q for q in pts if seam.contains(q) and seam.contains(q + QPointF(4, 0)) and seam.contains(q - QPointF(4, 0))
                  and seam.contains(q + QPointF(0, 4)) and seam.contains(q - QPointF(0, 4))]
        self.assertTrue(inside)
        for q in inside[:: max(1, len(inside) // 5)]:
            c = fit.map(q)
            self.assertLess(img.pixelColor(round(c.x()), round(c.y())).lightness(), 80, "这里是狗的身子（墨色），没有缝")

    def test_pieces_put_back_together_are_the_icon(self):
        """拆开的几块（关于页的图、两根线描的轮廓用）拼回去就是 app 图标的猫狗。"""
        pcs = marks.app_pieces()
        rebuilt = pcs["dog"].subtracted(pcs["dog_face"]).united(pcs["cat"].subtracted(pcs["cat_face"]))
        whole = dm_shapes.dog_cat()
        diff = rebuilt.subtracted(whole).united(whole.subtracted(rebuilt)).boundingRect()
        self.assertLess(diff.width() * diff.height(), 4.0)


class AboutTests(PanelCase):
    def setUp(self):
        super().setUp()
        motion = mock.patch.object(native, "reduce_motion", return_value=False)
        motion.start()
        self.addCleanup(motion.stop)
        s = self.settings
        s.show()
        self.app.processEvents()
        s.finish_page_anim()
        about_art.scene()
        self.hero = s.about_hero

    def step(self, n: int = 1) -> None:
        s = self.settings
        for _ in range(n):
            s.frame_step(s.clock._last + 1 / 60, 1 / 60)

    def run_until_done(self, limit: int = 600) -> int:
        n = 0
        while self.hero.active and n < limit:
            self.step()
            n += 1
        return n

    def test_about_page_has_one_line_two_links_and_no_name_chip(self):
        """名字下面紧跟一句「养些住在你桌面上的小动物」，再下面一行「版本 0.9.0 · 检查更新」，再下面两个描边小胶囊链接（这个软件的仓库、网站：
        「访问 GitHub 仓库」「访问我的网站」，英文 Visit GitHub Repo / Visit My Site），两种语言都并排放得下：不被挤窄、这一页不比主页面宽；
        最底下一行版权；顶部栏没有「关于」两个字，只有 ‹ 和 ×。"""
        from widget import i18n
        self.assertEqual((i18n.ZH["Visit GitHub Repo"], i18n.ZH["Visit My Site"]), ("访问 GitHub 仓库", "访问我的网站"))
        s, bar = self.settings, self.settings._tag
        s.show_page("about", animated=False)
        self.app.processEvents()
        page = s.about_page
        self.assertEqual(page.intro.text(), about.tr(about.INTRO))
        self.assertEqual([link.text() for link in page.links], [about.tr("Visit GitHub Repo"), about.tr("Visit My Site")])
        for link in page.links:
            self.assertGreaterEqual(link.width(), link.sizeHint().width(), f"「{link.text()}」不被挤窄")
            self.assertTrue(page.rect().contains(link.geometry()), f"「{link.text()}」在这一页里面")
        self.assertLessEqual(page.width(), s.main_page.width(), "链接没把这一页撑得比卡片里面宽")
        self.assertEqual(page.copyright.text(), "Copyright © 2026 JUN7 · GPL v3", "最底下一行版权，中英文一样")
        self.assertTrue(page.rect().contains(page.copyright.geometry()))
        self.assertGreater(page.copyright.y(), page.links[0].geometry().bottom(), "在两个链接下面")
        self.assertIn(page.copyright, page.lines, "进出关于页时跟别的字一起出来")
        y = lambda w: w.mapTo(page, QPoint(0, 0)).y()
        row = page.version_row
        self.assertLess(y(page.name), y(page.intro), "一句话紧跟在名字下面")
        self.assertLess(y(page.intro) + page.intro.height(), y(row) + 1, "版本号那一行在一句话下面")
        self.assertLess(y(row) + row.height(), y(page.links[0]) + 1, "…在两个链接上面")
        self.assertEqual(page.lines, (page.name, page.intro, row, *page.links, page.copyright), "过渡动画里从上往下一行行出来")
        self.assertEqual(page.status.text(), about.tr("Check for updates"))
        dot_right = row.dot.mapTo(page, QPoint(row.dot.width(), 0)).x()
        self.assertAlmostEqual(dot_right, page.width() / 2, delta=2, msg="从正中分开：版本号和「·」在左半边，检查更新在右半边")
        self.assertLessEqual(page.status.capsule_rect().left(), 3, "检查更新的字和悬停的胶囊贴左（换字时版本号不挪）")
        from PySide6.QtGui import QFontMetricsF
        from widget.motion import MOTION_PAD
        st = page.status
        hug = QFontMetricsF(st.font()).horizontalAdvance(st.text()) + 2 * (st.TEXT_INSET - MOTION_PAD)
        self.assertAlmostEqual(st.capsule_rect().width(), hug, delta=2, msg="胶囊只包着字，不是撑满右半边")
        self.assertFalse(page.links[0].property("quiet"))
        self.assertFalse(bar.name_shown)
        self.assertEqual(bar._name_vis, 0.0)
        self.assertEqual(bar.lead_mode, "back")
        s.show_page("main", animated=False)
        self.assertTrue(bar.name_shown)
        self.assertEqual(bar._name_vis, 1.0)

    def test_check_for_updates_here_is_the_same_as_in_advanced_settings(self):
        """关于页的「检查更新」和高级设置最底下那个是同一个状态（一起换字、一起变蓝）；在关于页点「发现新版本」进更新说明页，
        返回、长按「更新」开始下载都回到关于页。"""
        from tests.test_updater import rel
        s, up = self.settings, self.win.updater
        up._fetch = lambda url: [rel("v99.0.0", pre=False, body="**更新内容**\n- 新东西")]
        up._spawn = lambda fn: fn()
        s.show()
        s.show_page("about", animated=False)
        s.finish_page_anim()
        status = s.about_page.status
        status.click()
        self.app.processEvents()
        self.assertEqual(up.state, "found")
        self.assertEqual((status.text(), status.clickable, status.property("tone")),
                         (s.update_button.text(), True, "blue"), "和高级设置那个一样：发现新版本，蓝字，能点")
        status.click()
        s.finish_page_anim()
        self.assertEqual(s.page, "notes")
        self.assertEqual(s.pages["notes"].back_target(), "about", "从关于页进来的，返回回关于页")
        s.back.click()
        s.finish_page_anim()
        self.assertEqual(s.page, "about")
        status.click()
        s.finish_page_anim()
        next(b for b in s.notes_page.findChildren(type(s.update_now).__mro__[1]) if b.text() == about.tr("Later")).click()
        s.finish_page_anim()
        self.assertEqual(s.page, "about", "「下次再说」也回关于页")
        status.click()
        s.finish_page_anim()
        with mock.patch.object(up, "download") as download:
            s._start_download()
        s.finish_page_anim()
        download.assert_called_once()
        self.assertEqual(s.page, "about", "长按「更新」：回关于页，在这一行看下载进度")
        s.show_advanced(True, animated=False)
        s.finish_page_anim()
        s._update_clicked()
        s.finish_page_anim()
        self.assertEqual(s.pages["notes"].back_target(), "advanced", "从高级设置进的还回高级设置")

    def test_entering_draws_the_scene_and_hands_over_pixel_for_pixel(self):
        """进：走完交还给关于页自己画（图是同一段代码 about_art.Scene，字是拍下来的那张），和最后一帧看不出差别。"""
        s, h = self.settings, self.hero
        s.show_page("about")
        self.app.processEvents()
        self.assertTrue(h.active)
        self.assertTrue(s.about_page.veiled)
        self.assertTrue(s._tag.lead.hero_hidden)
        while h.active and h.p < about.END - 2 / 60:
            self.step()
        self.app.processEvents()
        before = shot(s)
        self.run_until_done()
        self.app.processEvents()
        self.assertFalse(h.active)
        self.assertFalse(s.about_page.veiled)
        self.assertFalse(s._tag.lead.hero_hidden)
        after = shot(s)
        box = QRect(QPoint(0, 0), s.size()).adjusted(0, 0, -1, -1)
        self.assertLess(differ(before, after, box, over=24), 30, "交还时和最后一帧几乎一样")

    def test_back_at_any_moment_never_jumps(self):
        """进来的路上任何时候点返回：进度钟的速度平滑地掉头（不跳、不一下子反向），线先减速再往回走，最后回到主页面。"""
        s, h = self.settings, self.hero
        for at in range(3, int(about.END * 60) - 3, 9):        # 每 0.15 秒点一次（每一种都从头进）
            s.show_page("about")
            self.app.processEvents()
            ps = [h.p]
            for _ in range(at):
                self.step()
                ps.append(h.p)
            s.show_page("main")                                # 点返回
            for _ in range(400):
                if not h.active:
                    break
                self.step()
                ps.append(h.p)
            self.assertFalse(h.active, f"{at} 帧时点返回，最后走完了")
            self.assertEqual(s.page, "main")
            v = [b - a for a, b in zip(ps, ps[1:])]
            dv = [abs(b - a) for a, b in zip(v, v[1:])]
            self.assertLess(max(dv), 0.11, f"{at} 帧时点返回：钟每帧的速度变化不大（不跳）")
            self.app.processEvents()

    def test_back_then_in_again_keeps_going_from_where_it_is(self):
        """回到一半（已经换回主页面）又点进来：接着往关于页走，钟不跳。"""
        s, h = self.settings, self.hero
        s.show_page("about")
        self.app.processEvents()
        self.step(int(1.2 * 60))
        s.show_page("main")
        ps = [h.p]
        while h.active and s.page == "about":
            self.step()
            ps.append(h.p)
        self.assertEqual(s.page, "main", "线快回到圆里时才真的换回主页面")
        self.assertLessEqual(h.p, about.HOME_AT + 0.05)
        self.step(2)
        ps.append(h.p)
        s.show_page("about")                                   # 再点进来
        for _ in range(30):
            self.step()
            ps.append(h.p)
        self.assertTrue(h.into)
        v = [b - a for a, b in zip(ps, ps[1:])]
        dv = [abs(b - a) for a, b in zip(v, v[1:])]
        self.assertLess(max(dv), 0.11)
        self.run_until_done()
        self.assertEqual(s.page, "about")
        self.assertFalse(h.active)

    def _click_circle(self) -> None:
        """点顶部栏左边的圆（走的是真的点击：顶部栏按自己的样子发返回 / 进关于页，动画走着时 settings 让它掉头）。"""
        self.settings._tag._lead_clicked()

    def _going_in(self) -> bool:
        """现在是往关于页走（动画走着时看钟往哪拨，停着时看在哪一页）。"""
        h = self.hero
        return h.into if h.active else self.settings.page == "about"

    def _reset(self, page: str) -> None:
        self.hero.finish(run_pending=False)
        self.settings.show_page(page, animated=False)
        self.settings.finish_page_anim()
        self.app.processEvents()

    def _assert_smooth(self, ps: list, what: str) -> None:
        v = [b - a for a, b in zip(ps, ps[1:])]
        dv = [abs(b - a) for a, b in zip(v, v[1:])]
        self.assertLess(max(dv), 0.11, f"{what}：钟每帧的速度变化不大（不跳）")

    def test_in_again_before_the_page_switches_back(self):
        """关于页点返回，回到一半（还没真的换回主页面，圆里已经是 D、M）又点圆：钟平滑掉头，接着往关于页走，最后停在关于页（
        「你没有考虑关于页面返回被打断的情况」）。"""
        s, h = self.settings, self.hero
        s.show_page("about")
        self.app.processEvents()
        self.run_until_done()
        self.assertEqual(s.page, "about")
        self._click_circle()                                   # 点返回
        self.assertTrue(h.active)
        self.assertFalse(h.into)
        ps = [h.p]
        while h.p > 1.0:                                       # 线收回来一半
            self.step()
            ps.append(h.p)
        self.assertEqual(s.page, "about", "还没真的换回主页面")
        self.assertGreater(h.p, about.HOME_AT)
        self._click_circle()                                   # 又点进来
        self.assertTrue(h.into)
        for _ in range(int(about.END * 60) + 30):
            if not h.active:
                break
            self.step()
            ps.append(h.p)
        self._assert_smooth(ps, "回到一半又点进来")
        self.assertFalse(h.active)
        self.assertEqual(s.page, "about")
        self.assertFalse(s.about_page.veiled)
        self.assertFalse(s._tag.lead.hero_hidden)

    def test_a_click_at_any_frame_turns_it_around(self):
        """动画走着时点圆就掉头：进的路上哪一帧点都回主页面；回的路上哪一帧点
        （还没换回主页面、已经换回来）都接着进关于页。"""
        s, h = self.settings, self.hero
        for n in range(1, int(about.END * 60) - 1, 3):        # 进的路上
            self._reset("main")
            self._click_circle()                               # 点 app 图标进来
            self.assertTrue(h.active and h.into)
            self.step(n)
            self.assertTrue(h.active)
            self._click_circle()
            self.assertFalse(self._going_in(), f"进来第 {n} 帧点圆：掉头回主页面")
        switched = False
        for n in range(1, 90, 3):                              # 回的路上
            self._reset("about")
            self._click_circle()                               # 点返回
            self.assertTrue(h.active and not h.into)
            self.step(n)
            if not h.active:
                break
            switched |= s.page == "main"
            self._click_circle()
            self.assertTrue(self._going_in(), f"回去第 {n} 帧点圆（{s.page}）：掉头接着进关于页")
        self.assertTrue(switched, "已经换回主页面以后点的也试到了")
        self._reset("main")

    def test_mashing_the_circle_turns_it_around_every_time(self):
        """狂点（每 4 帧点一下，连着 2.4 秒）：每一下都掉头，钟不跳；停手以后停在最后一下点去的那一页，圆、图、字都交还了。"""
        s, h = self.settings, self.hero
        self._click_circle()                                   # 主页面点 app 图标
        self.assertTrue(self._going_in())
        ps = [h.p]
        for i in range(36):
            for _ in range(4):
                self.step()
                ps.append(h.p)
            before = self._going_in()
            self._click_circle()
            self.assertNotEqual(self._going_in(), before, f"第 {i + 1} 下：掉头")
        last = self._going_in()
        for _ in range(600):
            if not h.active:
                break
            self.step()
            ps.append(h.p)
        self._assert_smooth(ps, "狂点")
        self.assertFalse(h.active)
        self.assertEqual(s.page, "about" if last else "main")
        self.assertFalse(s.about_page.veiled)
        self.assertFalse(s._tag.lead.hero_hidden)

    def test_clicking_back_and_forth_at_random_moments_never_jumps(self):
        """来回乱点（随机的时刻、连着点几下）：每帧钟的速度都只平滑地变，最后停在最后一次点去的那一页，圆、图、字都交还了。"""
        import random
        s, h = self.settings, self.hero
        rng = random.Random(1115)
        for trial in range(6):
            s.show_page("about")
            self.app.processEvents()
            ps = [h.p]
            for _ in range(rng.randint(3, 7)):
                for _ in range(rng.randint(1, 50)):
                    if not h.active:
                        break
                    self.step()
                    ps.append(h.p)
                if not h.active:
                    break
                self._click_circle()
            for _ in range(600):
                if not h.active:
                    break
                self.step()
                ps.append(h.p)
            self._assert_smooth(ps, f"第 {trial} 串")
            self.assertFalse(h.active)
            self.assertEqual(s.page, "about" if h.into else "main")
            self.assertFalse(s.about_page.veiled)
            self.assertFalse(s._tag.lead.hero_hidden)
            if s.page == "about":
                s.show_page("main", animated=False)
            self.app.processEvents()

    def test_lines_come_out_through_the_opened_bottom_of_the_circle(self):
        """线出去之前圆的底边已经打开（不从圈上穿过去）；两根线全出了圆，口才合上。"""
        s, h = self.settings, self.hero
        s.show_page("about")
        self.app.processEvents()
        c0, ring, _scale = h._circle()
        crossed = False
        for _ in range(int(0.6 * 60)):
            self.step()
            gap = 78.0 * (about.ease_out(about.span(h.p, 0.12, 0.32), 2.5) - about.smooth(about.span(h.p, h.t_out, h.t_out + 0.26)))
            for tr in h.tracks:
                hd = tr.head(h.p)
                if hd > tr.L_cap + 0.5:
                    head = tr.sub(hd - 0.5, hd)[-1]
                    if head.y() > c0.y() + ring - 1.0 and h.p < h.t_out:
                        crossed = True
                        self.assertGreater(gap, 30.0, "线头到圆的底边时，口已经开了")
        self.assertTrue(crossed)

    def test_reduce_motion_goes_straight_there(self):
        s, h = self.settings, self.hero
        with mock.patch.object(native, "reduce_motion", return_value=True):
            s.show_page("about")
            self.assertFalse(h.active)
            self.assertEqual(s.page, "about")
            s.show_page("main")
            self.assertFalse(h.active)
            self.assertEqual(s.page, "main")

    def test_hiding_the_card_mid_way_finishes_cleanly(self):
        s, h = self.settings, self.hero
        s.show_page("about")
        self.app.processEvents()
        self.step(40)
        s.finish_animations()
        self.assertFalse(h.active)
        self.assertFalse(s.about_page.veiled)
        self.assertFalse(s._tag.lead.hero_hidden)


if __name__ == "__main__":
    unittest.main()
