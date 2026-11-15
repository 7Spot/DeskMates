"""灵动交互的游乐场：真窗口（offscreen）+ 真模型，一帧帧地推：扔球、狗追、叼起、叼到鼠标旁边放下；按住狗再拉跳上窗口、窗口挪了跟着走、
窗口没了 / 切走了 / 被系统收走掉下来；后脚踩在平面上；点狗 duang；拎起来、扔出去；捡球开关；进圈才追（捡球的圈）；球什么时候都抓得住；
调大小时脚不离地。别的 App 的窗口用假的（offscreen 平台问不到系统）。圈本身怎么算、怎么画在 tests/test_ring.py。"""
import math
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import config
from tests.panel_base import QUIET, FakeSettings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DT = 1 / 60


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")

def set_fetch(win, on: bool) -> None:
    """捡球的总闸（window.fetch_on 一直开着）：单测拨它让狗只看着、叼着的放下。"""
    win.fetch_on = bool(on)
    win.playground.fetch_changed()

class PlaygroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        from widget import gltf
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.model = gltf.load(config.MODEL_PATH)

    def setUp(self):
        import widget.window as window
        from widget import native
        self.frames = {}                                     # 假的别的 App 的窗口：窗口号 → (x, y, w, h)
        self.hidden = set()                                  # 切到别的桌面 / 最小化了：列表里没有，单个问照样报位置（真机就是这样）
        patches = [mock.patch.object(window, "QSettings", FakeSettings),
                   mock.patch.object(native, "window_frames",
                                     lambda pid: [(n, 99, *f) for n, f in self.frames.items() if n not in self.hidden]),
                   mock.patch.object(native, "window_frame", lambda n: self.frames.get(n)),
                   mock.patch.object(native, "window_covered", lambda n, x, y, pid: False if n in self.frames else None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.win = window.CompanionWindow(self.model)
        self.win._anim_timer.stop()
        self.win.dog.rng.seed(5)
        self.pg = self.win.playground
        from PySide6.QtWidgets import QApplication
        self.ag = QApplication.primaryScreen().availableGeometry()
        self.floor_y = self.ag.y() + self.ag.height() - 18.0 * self.win.scale
        self.cursor = (self.ag.x() + 200.0, self.floor_y - 150.0)
        p = mock.patch.object(self.pg, "cursor", lambda: self.cursor)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        if self.pg.ball_win is not None:
            self.pg.ball_win.hide()
        for rw in self.pg.ring_wins.values():
            rw.hide()
        self.win.hide()

    def start_on_floor(self, x=560.0):
        self.win.show()
        self.win.place_scene(x, self.floor_y)
        self.win.dog.snap_home(210.0)
        self.assertTrue(self.win.dynamic, "灵动交互新装默认开")
        self.pg.start()
        self.pg._frames_at = -math.inf

    def test_the_charge_sound_swells_so_that_it_is_full_just_as_the_ring_is(self):
        """「倒放的吉他扫弦」：不一拍一拍——离圈满还剩 1 秒以内才开始放，从对得上的位置放，
        圈满那一下正好放到「满」（文件的第 CHARGE_FULL_AT 秒）；停多久满都对得上。满了不淡（让它自己收住、接狗叫）；
        没满就出了圈 / 松手：淡掉；再进圈照那时的进度接着放。"""
        import wave
        from widget.playground import CHARGE_FULL_AT, CHARGE_LATE_S
        from widget.ring import DRAIN_S, Ring
        pg = self.pg
        events = []
        with mock.patch.object(pg.ball_bank, "start", side_effect=lambda event, offset=0.0, gain=1.0: events.append(("start", event, offset, gain)) or True), \
                mock.patch.object(pg.ball_bank, "fade", side_effect=lambda event: events.append(("fade", event))), \
                mock.patch.object(pg.ball_bank, "play", side_effect=AssertionError("不再一拍一拍地放")):
            for hold in (1.0, 0.5, 2.0, 1.36):                   # 1.36：萨摩耶的圈（聪明程度低的满得慢）
                g = Ring()
                g.restart()
                pg._charging = False
                del events[:]
                t, began = 0.0, None
                while not g.ready:
                    g.step(DT, True, hold)
                    pg._charge_sound(not g.ready, g, hold)
                    t += DT
                    if events and began is None:
                        began = t
                self.assertEqual([e[:2] for e in events], [("start", "charge")], f"停 {hold} 秒满：只起一次，满了不淡")
                offset, gain = events[0][2:]
                self.assertEqual(gain, 1.0, "多响是这段声音自己的起伏，不另外推")
                self.assertGreaterEqual(offset, 0.0)
                self.assertAlmostEqual(began + (CHARGE_FULL_AT + CHARGE_LATE_S - offset), t, delta=1.5 * DT,
                                       msg=f"停 {hold} 秒满：圈满那一下声音正好放到「满」")
                if hold >= CHARGE_FULL_AT + 0.1:
                    self.assertAlmostEqual(began, hold - CHARGE_FULL_AT, delta=2 * DT, msg="还剩 1 秒才开始")
                    self.assertLess(offset, 0.06, "从头放")
                else:
                    self.assertLess(began, 2 * DT, "不到 1 秒就满的：一进圈就放")
                    self.assertAlmostEqual(offset, CHARGE_FULL_AT - hold + CHARGE_LATE_S, delta=2 * DT, msg="从中间放起")
                pg._charge_sound(False, g, hold)
                self.assertEqual(len(events), 1, "满了以后不再放、不淡")
            g = Ring()                                           # 没满就出了圈，再进来
            g.restart()
            pg._charging = False
            del events[:]
            for _ in range(36):                                  # 在圈里 0.6 秒
                g.step(DT, True, 1.0)
                pg._charge_sound(True, g, 1.0)
            for _ in range(8):                                   # 出圈 0.13 秒：往回退
                g.step(DT, False, 1.0)
                pg._charge_sound(False, g, 1.0)
            self.assertEqual([e[:2] for e in events], [("start", "charge"), ("fade", "charge")], "出了圈：淡掉，只淡一次")
            p = g.progress
            self.assertAlmostEqual(p, 0.6 - (8 * DT) / DRAIN_S, delta=0.02)
            g.step(DT, True, 1.0)
            pg._charge_sound(True, g, 1.0)
            self.assertEqual(events[-1][:2], ("start", "charge"))
            self.assertAlmostEqual(events[-1][2], CHARGE_FULL_AT - (1.0 - g.progress) * 1.0 + CHARGE_LATE_S, delta=1e-6, msg="再进圈：照那时的进度接着放")
            self.assertGreater(events[-1][2], 0.4)
        files = pg.ball_bank.pack.sounds["charge"].files
        self.assertEqual([f.name for f in files], ["charge.wav"], "球的包里是那段吉他扫弦，不是皮球碰撞那一声")
        with wave.open(str(files[0])) as w:
            self.assertGreaterEqual(w.getnframes() / w.getframerate(), CHARGE_FULL_AT, "文件比「满」的那一刻长")
        self.assertEqual(pg.ball_bank.volume("charge"), self.win.ball_tuning["vol_charge"], "音量有自己的调参项")

    def test_holding_the_ball_in_the_ring_plays_the_charge_once_and_leaving_fades_it(self):
        """走一遍真的：拿着球进圈、涨满——充能的声音起一次，满的那一下不淡，接着狗叫；没满就拿出圈——淡掉；松手、关灵动交互也不留着响。"""
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        self.step(0.5)
        pg, roam, g = self.pg, self.pg.roam, self.pg.ring
        events = []
        with mock.patch.object(pg.ball_bank, "start", side_effect=lambda event, offset=0.0, gain=1.0: events.append(("start", round(offset, 2))) or True), \
                mock.patch.object(pg.ball_bank, "fade", side_effect=lambda event: events.append(("fade", event))):
            self.hold_ball_at(self.ring_point(), 4.0, until=lambda: roam.bowing)
            self.assertTrue(g.ready)
            self.assertEqual(len(events), 1, "涨满这一趟只起一次、不淡")
            self.assertEqual(events[0][0], "start")
            self.assertLess(events[0][1], 0.1, "圈要停 1 秒：一进圈就从头放")
            self.assertFalse(pg._charging)
            pg.ball_release(QPointF(*pg._pointer))
            self.assertIsNotNone(self.step(30.0, lambda: roam.task is None and pg.ball.resting))
            self.assertEqual(len(events), 1, "扔出去、叼回来都不再响")
            del events[:]
            self.hold_ball_at(self.ring_point(), 0.5)            # 进圈半秒：还没满
            self.assertEqual([e[0] for e in events], ["start"])
            self.assertTrue(pg._charging)
            pg.ball_drag(QPointF(*self.ring_point(inside=False)))   # 拿出圈
            self.step(0.1)
            self.assertEqual([e[0] for e in events], ["start", "fade"], "没满就出了圈：淡掉")
            pg.ball_drag(QPointF(*self.ring_point()))               # 再进圈
            self.step(0.1)
            self.assertEqual([e[0] for e in events], ["start", "fade", "start"])
            self.assertGreater(events[-1][1], 0.2, "照那时的进度接着放，不从头来")
            self.win.set_dynamic(False)                             # 响着的时候关灵动交互
            self.assertEqual(events[-1][0], "fade")
            self.assertFalse(pg._charging)
            pg.ball_held = False
            self.win.set_dynamic(True)

    def test_dock_coming_back_lifts_the_dog_and_the_ball_onto_the_new_floor(self):
        """苹果有时回到桌面程序坞不出来，等它出来了狗和球还踩在程序坞上（地面只在接拔显示器、改分辨率时重算）。
        现在可用区域一变就重算：程序坞出来，站在那一带的狗原地跳上去、停着的球弹一下落到新地面；程序坞收起来，照常掉回去。"""
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QScreen
        self.start_on_floor()
        pg, ag = self.pg, self.ag
        self.step(1.0)
        b = pg.ball
        self.assertAlmostEqual(pg.roam.wy, self.floor_y, delta=0.5)
        self.assertAlmostEqual(b.y + b.r, self.floor_y, delta=1.0)
        dock = 70
        raised = QRect(ag.x(), ag.y(), ag.width(), ag.height() - dock)
        with mock.patch.object(QScreen, "availableGeometry", lambda s: raised):
            self.win._after_floor_change()
            self.assertEqual(pg.roam.task, "go", "原地往上跳")
            self.step(3.0)
            self.assertAlmostEqual(pg.roam.wy, self.floor_y - dock, delta=0.5, msg="狗站到程序坞上沿上面")
            self.assertAlmostEqual(b.y + b.r, self.floor_y - dock, delta=1.0, msg="球弹上去停在新地面")
            self.assertTrue(b.resting or b.rolling)
        self.win._after_floor_change()                        # 程序坞收起来：地面降回去，照常掉下去
        self.step(3.0)
        self.assertAlmostEqual(pg.roam.wy, self.floor_y, delta=0.5)
        self.assertAlmostEqual(b.y + b.r, self.floor_y, delta=1.0)

    def test_quiet_only_when_nothing_moves_and_a_still_ball_is_not_repainted(self):
        """待着不动也满帧画。狗没在跑、球停在原地没人拿才算安静（窗口按它少画）；球的小窗口长相没变就不重画
        （停着也每帧重画的话：量过，占每秒工作量的一成半）。"""
        self.start_on_floor()
        pg, bw = self.pg, self.pg.ball_win
        self.step(0.5)
        pg._ball_fade.stop()
        pg.quiet()                                           # 记下球现在在哪
        self.assertTrue(pg.ball.resting)
        self.assertTrue(pg.quiet())
        with mock.patch.object(bw, "update") as update:
            pg._sync_ball()
            pg._sync_ball()
            update.assert_not_called()                       # 球没动：不重画
            pg.ball.spin += 0.3
            pg._sync_ball()
            update.assert_called_once()                      # 转了一点：画一次
        self.assertFalse(pg.quiet(), "球动了")
        self.assertTrue(pg.quiet())
        pg.ball_held = True
        self.assertFalse(pg.quiet(), "球在手上")
        pg.ball_held = False
        pg.ball.resting = False
        self.assertFalse(pg.quiet(), "球在飞")
        pg.ball.resting = True
        pg.roam.lifted = True
        self.assertFalse(pg.quiet(), "狗被拎着")
        pg.roam.lifted = False
        pg.ball_duang.press()
        self.assertFalse(pg.quiet(), "球被按着")
        pg.ball_duang.release()
        self.step(1.5)
        pg.quiet()
        self.assertTrue(pg.quiet(), "duang 弹完了")
        pg.ring.shown = 1.0
        self.assertFalse(pg.quiet(), "圈还看得见（淡入淡出、化开都算在动）")
        pg.ring.clear()

    def step(self, seconds, until=None):
        """按窗口的每一帧那样推（不走真计时器）：游乐场 → 看哪 → 狗 → 窗口跟着狗挪。"""
        w, pg = self.win, self.pg
        for i in range(int(seconds / DT)):
            pg._frames_at = -math.inf if i % 15 == 0 else pg._frames_at
            w._feel(DT)                                          # 兴奋度：和窗口每帧一样排在游乐场前面（window._tick）
            pg.update(DT)
            w.dog.set_look_target(w._look_target(DT))
            w.dog.update(DT)
            w._pose = w.dog.frame()
            pg.after_pose()
            if pg.roam.moved:
                w.place_scene(pg.roam.wx, pg.roam.wy)
            if until is not None and until():
                return i * DT
        return None

    def throw_left(self):
        from PySide6.QtCore import QPointF
        import time as _t
        pg, b = self.pg, self.pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        t0 = _t.perf_counter()
        with mock.patch("widget.playground.time.perf_counter", side_effect=[t0 + 0.30, t0 + 0.33, t0 + 0.36, t0 + 0.36, t0 + 0.36]):
            pg.ball_drag(QPointF(b.x - 30, b.y - 20))
            self.make_ready()
            pg.ball_drag(QPointF(b.x - 70, b.y - 45))
            pg.ball_release(QPointF(b.x - 70, b.y - 45))

    def make_ready(self):
        """跳过等圈：当作球已经在圈里停够了（这一条测的不是等圈；等圈本身在下面「捡球的圈」那几条和 tests/test_ring.py）。"""
        self.pg.ring.ready = True

    def ring_point(self, inside=True):
        """捡球的圈里 / 圈外的一个点（全局坐标）。里面：狗脸前面一点、身子那么高（离圆心 0.34 米，圈半径 0.8 米）；
        外面：往屏幕中间那边 1.8 米。"""
        roam, ppm = self.pg.roam, self.win.ppm
        if inside:
            return roam.wx + roam.facing * 0.3 * ppm, roam.wy - 0.55 * ppm
        d = 1.0 if roam.wx < self.ag.center().x() else -1.0
        return roam.wx + d * 1.8 * ppm, roam.wy - 0.4 * ppm

    def hold_ball_at(self, at, seconds, until=None):
        """按住球、拖到 at（这一拖就是拿起，鼠标、触摸板一样），拿着不动推 seconds 秒（until 说停就停）。返回这期间放过的片段（去重，按顺序）。"""
        from PySide6.QtCore import QPointF
        import time as _t
        pg, b, dog = self.pg, self.pg.ball, self.win.dog
        pg.ball_press(QPointF(b.x, b.y))
        moved = _t.perf_counter() - 1.0                          # 这一拖算在一秒前：推帧比真时间快，不然松手时这一拖还在手速的那 80 毫秒里
        pg.ball_drag(QPointF(*at), moved)
        pg.ball_drag(QPointF(*at), moved)                        # 拖到了就停住
        self.assertTrue(pg.ball_held, "拖了算拿起")
        seen = []

        def watch():
            if not seen or seen[-1] != dog.player.name:
                seen.append(dog.player.name)
            return until is not None and until()
        self.step(seconds, watch)
        return seen

    def ring_shown(self):
        return [rw for rw in self.pg.ring_wins.values() if rw.isVisible()]

    def climb_window(self, top_y, x=380.0, w=360.0):
        pg, roam = self.pg, self.pg.roam
        self.frames[7] = (x, top_y, w, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        s = next(s for s in pg.supports() if s.key == 7 and s.kind == "window")
        self.assertTrue(roam.go_to(s, x + w / 2))
        self.assertEqual(roam.task, "go")
        self.assertIsNotNone(self.step(12.0, lambda: roam.task is None), "跳上去了")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", 7))


    # ---------- 球 ----------
    def test_the_ball_waits_in_front_of_the_dog_on_its_floor(self):
        self.start_on_floor()
        b = self.pg.ball
        self.assertIsNotNone(b)
        self.assertTrue(b.resting)
        self.assertAlmostEqual(b.y + b.r, self.floor_y, delta=0.6, msg="球在狗那条地面上")
        self.assertLess(b.x, self.pg.roam.wx, "狗朝左（home 210°）：球在它左边、屏幕中间那边")
        self.assertTrue(self.pg.ball_win.isVisible())
        self.assertFalse(self.pg.roam.busy, "放在地面上的狗不掉")

    def test_throw_fetch_and_bring_it_to_the_mouse(self):
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        self.throw_left()
        self.assertFalse(pg.ball_held)
        self.assertLess(pg.ball.vx, -500, "往左甩出去")
        self.assertEqual(roam.task, "fetch")
        phases = []

        def watch():
            if roam.phase and (not phases or phases[-1] != roam.phase):
                phases.append(roam.phase)
            return roam.task is None
        took = self.step(40.0, watch)
        self.assertIsNotNone(took, f"40 秒内叼过来：{phases}")
        for ph in ("approach", "pickup", "carry", "putdown"):
            self.assertIn(ph, phases, f"走过 {ph}：{phases}")
        b = pg.ball
        self.assertFalse(self.win.dog.puppet, "交回控制器")
        self.assertFalse(pg.carried)
        self.assertTrue(pg.ball_win.isVisible(), "放下后球的小窗口回来")
        from widget.ball import HIT_PAD
        gap = abs(b.x - self.cursor[0])
        self.assertGreater(gap, b.r + HIT_PAD, "球放在鼠标旁边，点击范围碰不到鼠标")
        self.assertLess(gap, self.win.ppm * 0.45, "就在鼠标旁边")
        self.assertAlmostEqual(b.y + b.r, self.floor_y, delta=1.0)
        self.assertAlmostEqual(roam.home.dx, roam.wx, delta=0.5, msg="就待在这：家改到这")
        self.step(1.0)
        self.assertAlmostEqual((self.win.dog.yaw - self.win._home_yaw() + 180) % 360 - 180, 0.0, delta=3.0, msg="转回这个位置该朝的方向")

    # ---------- 点球、触摸板 ----------
    def clock(self):
        """假的钟：perf_counter 用它，测试自己往前拨。"""
        now = [5000.0]
        p = mock.patch("widget.playground.time.perf_counter", lambda: now[0])
        p.start()
        self.addCleanup(p.stop)
        return now

    def step_with(self, now, seconds, on_tick=None):
        for i in range(int(seconds / DT)):
            now[0] += DT
            if on_tick is not None:
                on_tick(i)
            self.step(DT)

    def test_a_click_on_the_ball_only_squashes_it(self):
        """左键点球和点狗一样：duang 一下，球不动，狗没反应，不响。"""
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        self.step(0.2)
        pg, b = self.pg, self.pg.ball
        x, y = b.x, b.y
        with mock.patch.object(pg.ball_bank, "play") as played, mock.patch.object(pg.roam, "ball_grabbed") as grabbed:
            pg.ball_press(QPointF(x, y))
            self.step(0.08)
            self.assertGreater(pg.ball_duang.value, 0.05, "压扁了")
            self.assertFalse(pg.ball_held)
            pg.ball_release(QPointF(x, y))
            self.step(0.02)
            seen = []
            self.step(0.6, lambda: seen.append(pg.ball_duang.value) and False)
            played.assert_not_called()
            grabbed.assert_not_called()
        self.assertLess(min(seen), 0.0, "弹过头")
        self.assertLess(abs(seen[-1]), 0.03, "弹回来了")
        self.assertEqual((b.x, b.y), (x, y), "球没动")
        self.assertTrue(b.resting)
        self.assertIsNone(pg.roam.task, "狗没反应")

    def test_holding_or_moving_on_the_ball_picks_it_up(self):
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        self.step(0.2)
        pg, b = self.pg, self.pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        self.step(0.25)
        self.assertTrue(pg.ball_held, "按久了算拿起")
        pg.ball_release(QPointF(b.x, b.y))
        self.step(3.0, lambda: pg.ball.resting)
        pg.roam.cancel(drop_ball=True)
        self.step(0.1)
        b = pg.ball
        b.resting, b.rolling, b.vx, b.vy = True, False, 0.0, 0.0
        pg.ball_press(QPointF(b.x, b.y))
        self.assertFalse(pg.ball_held)
        pg.ball_drag(QPointF(b.x + 3.0, b.y))
        self.assertFalse(pg.ball_held, "挪一点点还不算")
        pg.ball_drag(QPointF(b.x + 9.0, b.y))
        self.assertTrue(pg.ball_held, "挪了算拿起")

    def test_a_tap_is_only_a_squash_on_the_trackpad_too(self):
        """鼠标、触摸板操作统一。点一下球只 duang：不粘在光标上，也不弹胶囊（胶囊只有右键 / 两指点）。"""
        from PySide6.QtCore import QPointF
        from widget import native
        self.start_on_floor()
        self.step(0.2)
        pg, b = self.pg, self.pg.ball
        x, y = b.x, b.y
        with mock.patch.object(native, "pointer_event", lambda: (native.TOUCH_SUBTYPE, 0.4)):
            pg.ball_press(QPointF(x, y))
            pg.ball_release(QPointF(x, y))
        self.assertTrue(pg._press_from_pad, "认出来是触摸板")
        self.cursor = (x + 300.0, y)
        self.step(0.5)
        self.assertEqual((b.x, b.y), (x, y), "不跟着光标走")
        self.assertFalse(pg.ball_held)
        self.assertIsNone(self.win._ball_menu, "不弹胶囊")

    def hold_and_move(self, now, dx, frames):
        from PySide6.QtCore import QPointF
        pg, b = self.pg, self.pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        x, y = b.x, b.y
        for _ in range(frames):
            now[0] += DT
            x += dx
            pg.ball_drag(QPointF(x, y))
        return QPointF(x, y)

    def test_a_ball_set_down_gently_just_drops(self):
        self.start_on_floor()
        self.step(0.2)
        now = self.clock()
        pg, b = self.pg, self.pg.ball
        at = self.hold_and_move(now, -30.0, 8)
        now[0] += 0.6                                                # 挪完放稳了才松
        pg.ball_release(at)
        self.assertEqual((b.vx, b.vy), (0.0, 0.0))

    def move_and_slow_down(self, now, fast_px=20.0, stop_s=0.12):
        """像真手：125 赫兹的事件，先快，再慢下来，停一小会。返回松手的位置。"""
        from PySide6.QtCore import QPointF
        pg, b = self.pg, self.pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        x, y = b.x, b.y
        for dx in [fast_px] * 10 + [8.0, 4.0, 2.0, 1.0, 0.5, 0.0]:
            now[0] += 0.008
            x -= dx
            pg.ball_drag(QPointF(x, y))
        now[0] += stop_s
        return QPointF(x, y)

    def test_stopping_just_before_letting_go_puts_the_ball_down(self):
        """想放下，球却比预期快得多地飞出去。别取松手前 0.25 秒里最快的一下：刚才的快动作会算进去。"""
        self.start_on_floor()
        self.step(0.2)
        now = self.clock()
        pg, b = self.pg, self.pg.ball
        at = self.move_and_slow_down(now)
        self.assertGreater(max(abs(x1 - x0) / (t1 - t0) for (t0, x0, _), (t1, x1, _) in zip(pg.grab, list(pg.grab)[1:]) if t1 > t0), 2000.0, "刚才手很快")
        pg.ball_release(at)
        self.assertEqual((b.vx, b.vy), (0.0, 0.0), "最后停下来了：直接掉")

    def test_a_throw_uses_the_last_moment_and_stops_following_the_hand_at_release(self):
        """松手那一刻多快就多快，松手后手再动不算（还跟着手 0.08 秒的话，手指还在甩就会加速）。"""
        from widget import native
        speeds = []
        for pad in (False, True):
            self.start_on_floor()
            self.step(0.2)
            now = self.clock()
            pg, b = self.pg, self.pg.ball
            info = (native.TOUCH_SUBTYPE, 0.4) if pad else None
            with mock.patch.object(native, "pointer_event", lambda: info), mock.patch.object(native, "trackpad_system_drag", lambda: False):
                at = self.hold_and_move(now, -30.0, 8)
                now[0] += DT
                pg.ball_release(at)
            self.assertEqual(pg._press_from_pad, pad)
            v0 = abs(b.vx)
            speeds.append(v0)
            self.assertAlmostEqual(v0, 30.0 / DT * pg.ball_tune.throw_factor, delta=v0 * 0.15, msg="就是手最后的速度")
            self.cursor = (at.x() - 300.0, at.y())
            def faster(i):
                self.cursor = (self.cursor[0] - 80.0, self.cursor[1])
            self.step_with(now, 0.15, faster)
            self.assertLessEqual(abs(b.vx), v0 + 1.0, "松手后手再快也不加速")
            self.pg.stop()
        self.assertAlmostEqual(speeds[0], speeds[1], delta=1.0, msg="鼠标、触摸板一样")

    def test_moving_the_cursor_away_after_setting_the_ball_down_does_not_throw_it(self):
        self.start_on_floor()
        self.step(0.2)
        now = self.clock()
        pg, b = self.pg, self.pg.ball
        at = self.hold_and_move(now, -30.0, 8)
        now[0] += 0.6
        pg.ball_release(at)
        self.cursor = (at.x(), at.y())

        def away(i):
            self.cursor = (self.cursor[0] + 40.0, self.cursor[1])
        self.step_with(now, 0.06, away)
        self.assertLess(abs(b.vx), 1.0, "球还是直接掉")

    def test_the_ball_always_has_its_pattern_and_the_one_in_the_mouth_too(self):
        from widget import props
        self.assertIn("ball_seam", props.meshes())
        self.start_on_floor()
        d = self.win.dog.props
        d.item = {"kind": "ball", "mode": "held", "x": 0.0, "z": 0.0, "yaw": 0.0, "alpha": 1.0}
        pose = self.win.dog.frame()
        self.assertEqual([p.mesh for p in pose.props], ["ball", "ball_seam"])
        d.item = None

    def test_swinging_the_lifted_dog_keeps_its_legs_in_range(self):
        """拎着甩的时候腿会转一整圈：限在 ±30°，甩完很快停。"""
        from widget.lift import LEG_MAX
        self.start_on_floor()
        lift = self.win.dog.lift
        lift.begin()
        peak = 0.0
        for i in range(240):
            lift.feed(40.0 if (i // 15) % 2 == 0 else -40.0)         # 40 米 / 秒，来回猛甩
            lift.update(DT, 1.0)
            peak = max(peak, abs(lift.leg))
        self.assertLessEqual(peak, LEG_MAX + 1e-6)
        self.assertGreater(peak, 15.0, "还是看得出在甩")
        lift.feed(0.0)
        for _ in range(60):
            lift.update(DT, 1.0)
        self.assertLess(abs(lift.leg), 3.0, "手停了腿很快停，不来回抡")
        lift.cut()

    # ---------- 捡球的圈：进圈才追 ----------
    def test_picking_up_the_ball_shows_a_ring_around_the_dog_that_cannot_be_clicked(self):
        """拿起球：狗站好看着它，身边出一个圈（圆心在身子正中、半径一个身高、地面那条线下面不画），点不到，压在狗后面。"""
        from PySide6.QtCore import Qt
        self.start_on_floor()
        self.step(0.5)
        pg, roam = self.pg, self.pg.roam
        self.hold_ball_at(self.ring_point(inside=False), 0.5)
        self.assertEqual((roam.task, roam.phase), ("fetch", "watch"), "站好看着你手里的球")
        self.assertFalse(roam.bowing, "圈没满不俯身")
        self.assertIsNotNone(pg.look_point(), "看着球")
        s, ppm = pg._ring_at, self.win.ppm
        self.assertEqual(s.cx, roam.wx)
        self.assertAlmostEqual(s.cy, roam.wy - 0.4 * ppm, delta=0.5, msg="身子正中")
        self.assertAlmostEqual(s.r, 0.9 * 0.8 * ppm, delta=0.5, msg="0.9 个身高")
        self.assertEqual(s.floor, roam.wy)
        shown = self.ring_shown()
        self.assertEqual(len(shown), 1)
        g = shown[0].geometry()
        self.assertTrue(self.app.primaryScreen().geometry().contains(g), "待在这块屏上")
        self.assertLessEqual(g.bottom(), roam.wy + 1, "地面线下面不画")
        self.assertTrue(shown[0].windowFlags() & Qt.WindowTransparentForInput, "点不到")
        self.assertGreater(pg.ring.alpha, 0.9)
        self.assertEqual(pg.ring.progress, 0.0, "球在圈外：不涨")

    def test_a_full_ring_makes_the_dog_bark_once_then_bow(self):
        """球在圈里停够了，狗才做准备接球的动作。圈一点点涨满，满的那一下狗叫一声（嘴和声音对上：Bark 片段放第一声那段），
        叫完俯身等着；圈满了往外化开、淡掉。"""
        from widget.ring import BURST_S
        self.start_on_floor()
        self.step(0.5)
        pg, roam, dog, g = self.pg, self.pg.roam, self.win.dog, self.pg.ring
        at, rising, frames = [], [], {"n": 0}
        marks = {}

        def watch():
            frames["n"] += 1
            if dog.player.name == "Bark":
                at.append(dog.player.time)
                marks.setdefault("bark", frames["n"])
            if g.ready:
                marks.setdefault("full", frames["n"])
            else:
                rising.append(g.progress)
            return roam.bowing
        seen = self.hold_ball_at(self.ring_point(), 4.0, until=watch)
        self.assertGreater(len(rising), 0.9 * self.win.tuning["ring_hold_s"] / DT, "满之前一点点涨")
        self.assertEqual(rising, sorted(rising), "球一直在圈里：只涨不退")
        self.assertLessEqual(marks["bark"] - marks["full"], 1, "满的那一下就叫，不再等")
        self.assertIn("Bark", seen)
        self.assertLess(seen.index("Bark"), seen.index("Idle_5_start"), "先叫再俯身（俯身是闭着嘴的）")
        heard = [t for t in self.win.pack.clip_sounds["Bark"].at if min(at) < t <= max(at)]
        self.assertEqual(len(heard), 1, "只叫一声，声音跟嘴对上")
        self.assertEqual(roam.phase, "bow")
        self.step(BURST_S + 0.1)
        self.assertEqual(g.alpha, 0.0, "满了化开、淡没了")
        self.assertEqual(self.ring_shown(), [], "圈的窗口收起来了")
        self.assertTrue(roam.bowing, "还俯身等着")
        self.assertTrue(g.ready, "满了一直算到松手")

    def test_a_full_ring_makes_the_dog_bow_and_a_throw_sends_it_at_once(self):
        """俯身：前肢俯下来定住、闭嘴、侧身对着球、尾巴摇得飞快，后脚不动；松手立刻冲，不先站起来。"""
        self.start_on_floor()
        self.step(0.5)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        wags = []
        self.hold_ball_at(self.ring_point(), 4.0, until=lambda: wags.append(dog.expr.cur["wag"]) or roam.bowing)
        self.assertTrue(roam.bowing)
        self.step(0.8)                                               # 尾巴从看着时的慢慢摇加速到俯身时的飞快
        self.assertEqual(roam.phase, "bow")
        self.assertEqual(dog.player.name, "Idle_5_start")
        self.assertTrue(dog.shut_mouth, "闭嘴：Idle_5 自带叫")
        self.assertAlmostEqual(roam.facing, -1.0, msg="侧身对着球")
        self.assertIsNotNone(pg.look_point(), "看着球")
        self.assertLess(wags[len(wags) // 4], wags[-1], "拿着时随圈涨慢慢摇快")
        self.assertGreater(dog.expr.cur["wag"], 0.6, "尾巴摇得飞快")
        hind0 = dog.foot_metrics("Idle_5_start", 0.0)[1]
        hind1 = dog.foot_metrics("Idle_5_start", 1.0)[1]
        self.assertLess(abs(hind1 - hind0), 0.01, "后脚不动")
        self.throw_now(-900.0)                                       # 往狗前面扔：球在狗前面，狗直接冲出去
        self.assertFalse(dog.shut_mouth, "松手就不闭嘴了")
        seen = []
        self.step(0.25, lambda: seen.append(dog.player.name) and False)
        after_bow = [c for c in seen if c != "Idle_5_start"]
        self.assertTrue(after_bow and "_F_IP" in after_bow[0], f"不先站起来，直接冲出去：{seen[:6]}")

    def test_outside_the_ring_the_dog_only_watches_and_with_fetch_off_there_is_no_ring(self):
        """球拿在圈外：狗站着看，圈一直在、空的，不叫不俯身。关「捡球」：圈原地淡掉，狗不等了；关着拿起球不出圈。"""
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        self.step(0.5)
        pg, roam, g = self.pg, self.pg.roam, self.pg.ring
        seen = self.hold_ball_at(self.ring_point(inside=False), 4.0)
        self.assertEqual(roam.phase, "watch")
        self.assertFalse(roam.bowing)
        self.assertNotIn("Bark", seen)
        self.assertGreater(g.alpha, 0.9, "圈一直在")
        self.assertEqual(g.progress, 0.0)
        self.assertIsNotNone(pg.look_point(), "看着你手里的球")
        set_fetch(self.win, False)
        self.step(0.4)
        self.assertEqual(g.alpha, 0.0, "关了：圈原地淡没了")
        self.assertEqual(self.ring_shown(), [])
        self.assertIsNone(roam.task, "狗不等了")
        self.assertTrue(pg.ball_held, "球还在手上")
        pg.ball_release(QPointF(pg.ball.x, pg.ball.y))
        self.step(2.0, lambda: pg.ball.resting)
        seen = self.hold_ball_at(self.ring_point(), 2.0)
        self.assertEqual(g.alpha, 0.0, "关着：拿起球不出圈")
        self.assertIsNone(roam.task)
        self.assertNotIn("Bark", seen)

    def test_ring_size_hold_time_and_the_bark_come_from_the_tuning_page(self):
        """圈多大、停多久、满了叫不叫都在开发者设置页（0.9 个身高、1 秒、一定叫）。"""
        t = self.win.tuning
        self.assertEqual((t["ring_size"], t["ring_hold_s"], t["ready_bark"]), (0.9, 1.0, 1.0))
        self.start_on_floor()
        self.step(0.5)
        pg, roam = self.pg, self.pg.roam
        t.set("ring_hold_s", 0.3)
        t.set("ready_bark", 0.0)
        took = []
        seen = self.hold_ball_at(self.ring_point(), 2.0, until=lambda: took.append(pg.ring.ready) or roam.bowing)
        self.assertLessEqual(took.index(True) * DT, 0.3 + 2 * DT, "停 0.3 秒就满")
        self.assertNotIn("Bark", seen, "调成不叫：直接俯身")
        self.assertTrue(roam.bowing)
        x, y = roam.wx - 0.7 * self.win.ppm, roam.wy - 0.4 * self.win.ppm   # 离圆心 0.7 米
        from widget.ring import in_ring, ring_shape
        h = roam.height_m * self.win.ppm
        self.assertTrue(in_ring(ring_shape(roam.wx, roam.wy, h, t["ring_size"]), x, y))
        t.set("ring_size", 0.8)
        self.assertFalse(in_ring(ring_shape(roam.wx, roam.wy, h, t["ring_size"]), x, y), "调小了：0.7 米在圈外")
        t.reset()

    def test_holding_the_ball_keeps_a_ready_dog_bowing_quietly(self):
        """拿着球不扔，狗不坐下、不撒娇、不再出声，就俯身等着。"""
        self.start_on_floor()
        self.step(0.5)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        self.hold_ball_at(self.ring_point(), 4.0, until=lambda: roam.bowing)
        with mock.patch.object(pg.bank, "play") as played:
            self.step(8.0)
            self.assertTrue(roam.bowing, "还在等")
            self.assertEqual(dog.player.name, "Idle_5_start")
            played.assert_not_called()
        self.throw_now(-900.0)                                       # 往狗前面扔：球在狗前面，狗直接冲出去
        self.assertIsNotNone(self.step(1.0, lambda: "_F_IP" in (dog.player.name or "")), "松手冲出去")

    def test_a_dog_still_standing_up_already_shows_and_counts_the_ring(self):
        """「从拿起那一刻开始算」：狗正坐着、趴着（或换姿势换到一半）时拿起球，它先站起来（根不动），这时圈已经出来、已经在涨。"""
        self.start_on_floor()
        self.step(0.5)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        dog.set_dynamic(False)                                       # 只是为了让它趴下；拿起球时 roam 照样接管
        dog.set_rest_posture("lying")
        self.assertIsNotNone(self.step(8.0, lambda: dog.posture == "lying" and not dog.transition), "趴下了")
        standing = []
        self.hold_ball_at(self.ring_point(), 0.5, until=lambda: standing.append(
            (roam.leg or {}).get("kind") == "stand" and pg.ring.alpha > 0.0 and pg.ring.progress > 0.0) and False)
        self.assertTrue(any(standing), "起身的时候圈已经出来、在涨了")
        dog.set_dynamic(True)

    def test_a_ball_taken_from_the_mouth_counts_from_the_pickup(self):
        """从嘴里拿走的球就在狗脸前面（圈里）：从拿走那一刻算，停够了一样叫、俯身（不设特例）。"""
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        self.fetch_until_carrying()
        mx, my = roam.mouth_point()
        self.assertTrue(pg.try_snatch(QPointF(mx, my)))
        took = self.step(3.0, lambda: pg.ring.ready)
        self.assertIsNotNone(took)
        self.assertAlmostEqual(took, self.win.tuning["ring_hold_s"], delta=3 * DT)
        self.assertIsNotNone(self.step(2.0, lambda: roam.bowing), "接着叫、俯身")

    def test_on_a_moving_window_the_ring_follows_and_a_fall_starts_it_over(self):
        """狗站在窗口上看你手里的球：窗口挪了圈跟着挪（只有这时才每帧挪圈的窗口）；窗口关了狗掉下去，圈作废、原地淡掉，
        落地后接着看球，圈从空的重新算。"""
        self.start_on_floor(560.0)
        pg, roam = self.pg, self.pg.roam
        top_y = self.floor_y - 260
        self.climb_window(top_y)
        self.hold_ball_at(self.ring_point(), 0.5)
        self.assertEqual(roam.phase, "watch")
        rw = self.ring_shown()[0]
        g0, cx0 = rw.geometry(), pg._ring_at.cx
        self.assertGreater(pg.ring.progress, 0.3)
        self.frames[7] = (300.0, top_y - 40, 360.0, 200.0)       # 窗口被拖走：左 80、上 40
        self.step(0.2)
        self.assertAlmostEqual(pg._ring_at.cx, cx0 - 80, delta=0.5, msg="圈跟着狗")
        self.assertEqual(rw.geometry().topLeft() - g0.topLeft(), type(g0.topLeft())(-80, -40), "圈的窗口跟着挪")
        del self.frames[7]                                        # 窗口关了
        self.assertIsNotNone(self.step(1.0, lambda: roam.task == "fall"), "掉下去了")
        self.step(2 * DT)
        self.assertFalse(pg.ring.counting)
        self.assertFalse(pg.ring.ready)
        self.assertIsNotNone(self.step(6.0, lambda: roam.phase == "watch" and roam.support is not None and roam.support.kind == "floor"),
                             "落地后接着看球")
        self.step(0.3)
        self.assertTrue(pg.ring.counting)
        self.assertGreater(pg.ring.alpha, 0.5, "圈在新的地方又出来了")
        self.assertAlmostEqual(pg._ring_at.floor, roam.wy, delta=0.5)
        self.assertEqual(pg.ring.progress, 0.0, "从空的算（球离新圈远）")

    def test_a_lost_mouse_up_lets_the_ball_go(self):
        """按着的时候切走了、系统弹窗：松手事件没来。鼠标键松开 LOST_UP_S 秒还没来就当松了手，原地放下（不然圈和等着的狗一直留着）。
        这次拿着时从没看到键按着（自测脚本里的假拿着）就不管。"""
        from widget.playground import LOST_UP_S
        self.start_on_floor()
        self.step(0.5)
        pg, roam = self.pg, self.pg.roam
        down = [False]
        with mock.patch.object(pg, "_button_down", lambda: down[0]), mock.patch.object(pg, "_let_go", wraps=pg._let_go) as let_go:
            self.hold_ball_at(self.ring_point(inside=False), LOST_UP_S + 0.5)
            self.assertTrue(pg.ball_held, "从没看到键按着：不管")
            down[0] = True
            pg.ball_win._pressed = self.win._ball_drag = True       # 转鼠标事件的窗口以为还按着
            self.step(0.2)
            down[0] = False
            self.step(LOST_UP_S * 0.6)
            self.assertTrue(pg.ball_held, "刚松开：松手事件可能还在路上")
            self.step(LOST_UP_S * 0.4 + 0.1)
        self.assertFalse(pg.ball_held, "一直没来：当松了手")
        self.assertFalse(pg.ball_win._pressed)
        self.assertFalse(self.win._ball_drag)
        self.assertEqual(let_go.call_args.args[:2], (0.0, 0.0), "原地放下")
        self.step(1.0)
        self.assertEqual(pg.ring.alpha, 0.0, "圈淡掉了")
        self.assertIsNone(roam.task, "狗不等了")

    def test_the_fetch_gate_alone_stands_a_waiting_dog_down(self):
        """fetch_on 是唯一的闸（以后「看细节」也从这关）：闸关了即使没叫到 fetch_changed，下一帧圈也不算、俯身的狗也起来；
        闸开了球还在手上，又站好看着它，圈从空的算。"""
        self.start_on_floor()
        self.step(0.5)
        pg, roam = self.pg, self.pg.roam
        self.hold_ball_at(self.ring_point(), 4.0, until=lambda: roam.bowing)
        self.win.fetch_on = False
        self.step(0.5)
        self.assertFalse(roam.bowing)
        self.assertIsNone(roam.task)
        self.assertFalse(pg.ring.ready, "满了也作废")
        self.assertEqual(pg.ring.alpha, 0.0)
        self.win.fetch_on = True
        self.step(0.3)
        self.assertEqual(roam.phase, "watch")
        self.assertFalse(pg.ring.ready)
        self.assertLess(pg.ring.progress, 0.4)

    def test_the_ball_can_be_taken_before_the_nose_touches_it(self):
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        pg.ball.throw(-900.0, -300.0, self.win.ppm)
        roam.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: roam.phase == "pickup"), "低头去叼了")
        self.assertTrue(pg.ball_win.isVisible(), "鼻子碰到之前还是球的小窗口（点得到）")
        self.assertFalse(pg.carried)
        b = pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        self.assertTrue(pg.ball_held)
        self.assertEqual(roam.phase, "look", "狗停下看着你手里的球")
        self.assertFalse(roam.carrying)
        self.step(0.5)
        self.assertTrue(self.win.dog.props.item is None or self.win.dog.props.item["out"], "狗嘴边的 3D 球不出来")

    def test_the_ball_can_be_snatched_from_the_mouth(self):
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        pg.ball.throw(-900.0, -300.0, self.win.ppm)
        roam.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: roam.carrying), "叼起来了")
        self.assertFalse(pg.ball_win.isVisible(), "叼着：小窗口藏起来")
        mx, my = roam.mouth_point()
        self.assertFalse(pg.try_snatch(QPointF(mx + 200, my)), "点在别处不算")
        self.assertTrue(pg.try_snatch(QPointF(mx + 3, my - 2)), "点在嘴里的球上：拿走")
        self.assertTrue(pg.ball_held)
        self.assertFalse(roam.carrying, "狗松口")
        self.assertTrue(pg.ball_win.isVisible())
        self.assertEqual(roam.phase, "look", "站住看着你")
        self.assertLess(math.hypot(pg.ball.x - mx, pg.ball.y - my), pg.ball.r + 6, "球就在嘴那里，不跳")

    def test_a_flying_ball_is_easier_to_catch_and_slides_into_the_hand(self):
        from PySide6.QtCore import QPointF
        from widget.ball import HIT_PAD, catch_radius
        self.assertEqual(catch_radius(10.0, 0.0), 10.0 + HIT_PAD)
        self.assertGreater(catch_radius(10.0, 1500.0), 80.0, "飞得快：点击范围大得多")
        self.assertLessEqual(catch_radius(10.0, 1e6), 10.0 + HIT_PAD + 5 * 10.0 + 20.0, "有上限")
        self.start_on_floor()
        pg = self.pg
        b = pg.ball
        b.throw(-900.0, -900.0, self.win.ppm)
        self.step(0.1)
        hand = QPointF(b.x + 60, b.y + 20)                   # 远远抓住
        pg.ball_press(hand)
        self.step(0.3)
        self.assertLess(math.hypot(b.x - hand.x(), b.y - hand.y()), 0.5 * b.r + 1.0, "很快滑进手里")

    def test_a_big_dog_still_lets_the_ball_rest_on_windows(self):
        """球能停的窗口只看窗口上面放不放得下球，不按狗的身材筛（否则狗调大以后球停不到别的窗口上）。"""
        self.start_on_floor()
        self.win.set_scale(2.0)
        pg = self.pg
        top = self.ag.y() + 120.0                                   # 离屏幕顶 120 像素：两倍大的狗站不下，球停得住
        self.frames[11] = (200.0, top, 300.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        self.assertFalse(any(s.kind == "window" for s in pg.supports()), "狗站不下")
        b = pg.ball
        b.x, b.y, b.resting, b.on = 350.0, top - 80.0, False, None
        b.vx = b.vy = 0.0
        pg.roam.fetch = lambda: None                                # 只看球，别让狗去捡
        self.step(1.5)
        self.assertTrue(b.resting)
        self.assertEqual(b.on, ("window", 11), "球停在窗口上")

    def test_a_ball_hitting_a_window_side_makes_the_dog_flinch(self):
        self.start_on_floor()
        pg = self.pg
        b = pg.ball
        self.frames[9] = (b.x - 260.0, self.floor_y - 400.0, 120.0, 300.0)   # 球左边一个窗口，下边离地面一截
        pg._sups = None
        pg._frames_at = -math.inf
        b.x, b.y = b.x, self.floor_y - 250.0
        b.throw(-1500.0, 0.0, self.win.ppm)
        with mock.patch.object(pg, "_ball_hit_window", wraps=pg._ball_hit_window) as hit:
            self.step(0.4)
        self.assertTrue(hit.called, "撞到窗口右边弹回来，狗有反应")
        self.assertGreater(b.x, self.frames[9][0] + self.frames[9][2], "球弹回窗口右边外面")

    # ---------- 放球 ----------
    def fetch_until_carrying(self):
        pg, roam = self.pg, self.pg.roam
        pg.ball.throw(-900.0, -300.0, self.win.ppm)
        roam.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: roam.carrying), "叼起来了")

    def test_the_dog_puts_the_ball_down_on_arrival_even_if_the_mouse_keeps_moving_a_little(self):
        """到了就放，鼠标小幅度动着也不等（等鼠标停稳的话，会跟很久不放，不跟手）。"""
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        self.fetch_until_carrying()
        x0 = self.cursor[0]
        tick = {"n": 0}

        def wiggle():
            tick["n"] += 1
            self.cursor = (x0 + (tick["n"] % 2) * 10.0, self.cursor[1])   # 鼠标一直小幅地动
            return roam.phase in ("carry", "hold", "hold_done", "turn_put", "putdown") and roam.leg is not None and roam.leg.get("kind") != "run"
        self.assertIsNotNone(self.step(20.0, wiggle), "走到鼠标旁边了")
        t = self.step(0.5, lambda: (wiggle(), roam.phase in ("turn_put", "putdown"))[1])
        self.assertIsNotNone(t, "到了马上开始放，不等鼠标停")
        self.assertIsNotNone(self.step(6.0, lambda: (wiggle(), roam.task is None)[1]), "放下了")
        self.assertFalse(roam.carrying)
        self.assertLess(abs(pg.ball.x - x0), self.win.ppm * 0.9, "就在鼠标旁边")

    def test_moving_the_mouse_before_the_ball_leaves_the_mouth_keeps_it_following(self):
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        self.fetch_until_carrying()
        self.assertIsNotNone(self.step(20.0, lambda: roam.phase == "putdown" and self.win.dog.player.name == "Put_down"), "开始放了")
        self.step(0.1)
        self.assertTrue(roam.carrying, "球还没离嘴")
        far = self.cursor[0] + self.win.ppm * 1.5
        self.cursor = (far, self.cursor[1])
        self.step(0.1)
        self.assertTrue(roam.carrying, "鼠标挪远了：抬头收回来")
        self.assertIn(roam.phase, ("deliver", "carry"), "接着跟")
        self.assertIsNotNone(self.step(25.0, lambda: roam.task is None), "放下了")
        self.assertLess(abs(pg.ball.x - far), self.win.ppm * 0.45, "放在鼠标新的位置旁边")

    def test_a_mouse_that_never_stops_gets_the_ball_put_down_after_a_while(self):
        self.start_on_floor()
        roam = self.pg.roam
        self.fetch_until_carrying()
        x0 = self.cursor[0]
        tick = {"n": 0}

        def wiggle():
            tick["n"] += 1
            self.cursor = (x0 + (tick["n"] % 2) * 10.0, self.cursor[1])  # 一直小幅地动
            return roam.task is None
        self.assertIsNotNone(self.step(30.0, wiggle), "没有没完没了地叼着")
        self.assertFalse(roam.carrying)

    def test_the_ball_goes_to_the_other_side_of_the_mouse_at_a_screen_edge(self):
        self.start_on_floor(300.0)
        roam = self.pg.roam
        self.cursor = (self.ag.x() + 4.0, self.floor_y - 200.0)
        s, gx, d = roam._delivery_target()
        self.assertGreater(gx, self.cursor[0], "狗在右边")
        self.assertLess(d, 0, "朝左放，球在狗和鼠标之间")
        self.cursor = (self.ag.x() + self.ag.width() - 4.0, self.floor_y - 200.0)
        roam.wx = self.ag.x() + self.ag.width() - 10.0
        s, gx, d = roam._delivery_target()
        self.assertTrue(s.covers(gx, roam.margin(s)), "贴着屏幕边：狗站得下")

    # ---------- 追球：看得出停哪就去落点，看不出先追球本身 ----------
    def throw_and_fetch(self, vx, vy=-300.0):
        """球按这个速度飞出去（像素 / 秒），狗去捡。"""
        pg = self.pg
        pg.ball.throw(vx, vy, self.win.ppm)
        pg.throw_id += 1
        pg.roam.fetch()

    def watch_fetch(self, seconds=40.0, until=None):
        """推到叼起来（或 until 说停）为止。回来：用了多久、走过的阶段、每个阶段开始时球已经掉过几次头。"""
        pg, roam = self.pg, self.pg.roam
        phases, turned = [], {}

        def watch():
            if roam.phase and (not phases or phases[-1] != roam.phase):
                phases.append(roam.phase)
                turned.setdefault(roam.phase, pg.ball_turns)
            return until() if until is not None else roam.carrying
        return self.step(seconds, watch), phases, turned

    def test_a_throw_that_never_turns_back_goes_straight_to_where_it_will_stop(self):
        """弧线、落地弹几下、滚到停：一路不掉头，边牧看得出停哪，直接去（很明显能预判的就直接去预判的点）。"""
        self.start_on_floor()
        pg = self.pg
        self.throw_and_fetch(-300.0, -200.0)
        self.assertEqual(pg.ball_turns_left(), 0, "够不到墙：不掉头")
        took, phases, _ = self.watch_fetch()
        self.assertIsNotNone(took, f"叼到了：{phases}")
        self.assertNotIn("chase", phases)
        self.assertIn("approach", phases)

    def test_a_ball_that_will_bounce_back_off_a_wall_is_chased_first(self):
        """会撞墙弹回来的：先追球本身；撞完再看一次，后面不掉头了才去落点。"""
        self.start_on_floor(700.0)
        pg, roam = self.pg, self.pg.roam
        self.throw_and_fetch(-1500.0)
        self.assertEqual(pg.ball_turns_left(), 1, "这一扔会撞左墙弹回来一次")
        x0 = roam.wx
        chased = []
        took, phases, turned = self.watch_fetch(until=lambda: (chased.append(roam.wx) if roam.phase == "chase" else None) or roam.carrying)
        self.assertIsNotNone(took, f"还是叼到了：{phases}")
        self.assertIn("chase", phases)
        self.assertLess(phases.index("chase"), phases.index("approach"), "先追，再去落点")
        self.assertEqual(turned["chase"], 0, "球还没撞墙：追球")
        self.assertEqual(turned["approach"], 1, "撞完了才去落点")
        self.assertLess(min(chased), x0 - 0.2 * self.win.ppm, "追的时候是朝球跑的（球往左飞）")

    def test_how_many_bounces_the_dog_reads_ahead_can_be_tuned(self):
        """调参「能看穿几次反弹」：默认 0；调到 1，撞一次墙的也直接去落点。"""
        self.start_on_floor(700.0)
        self.assertEqual(self.win.tuning["see_bounces"], 0.0)
        self.win.tuning.set("see_bounces", 1)
        self.throw_and_fetch(-1500.0)
        self.assertEqual(self.pg.ball_turns_left(), 1)
        took, phases, _ = self.watch_fetch()
        self.win.tuning.reset()
        self.assertIsNotNone(took, f"叼到了：{phases}")
        self.assertNotIn("chase", phases, "看得穿这一次反弹：不追，直接去落点")

    def test_the_forecast_knows_how_many_times_the_ball_will_turn_back(self):
        self.start_on_floor()
        pg, b = self.pg, self.pg.ball
        set_fetch(self.win, False)                                     # 只看球，狗不动
        b.throw(-4000.0, -300.0, self.win.ppm)
        pg.throw_id += 1
        n = pg.ball_turns_left()
        rest = pg.predict_rest()
        self.assertGreaterEqual(n, 2, "这么快：两头的墙来回撞")
        left = []
        self.assertIsNotNone(self.step(8.0, lambda: left.append(pg.ball_turns_left()) or b.resting), "停了")
        self.assertEqual(pg.ball_turns, n, "真掉头的次数和算的一样")
        self.assertEqual(left, sorted(left, reverse=True), "还剩几次只减不加")
        self.assertEqual(left[-1], 0)
        self.assertAlmostEqual(b.x, rest[0], delta=2.0, msg="停在算好的地方")

    def test_the_dog_waits_for_the_ball_to_land_on_a_window_before_jumping_up(self):
        """跳上窗口等球真落到那一层再做：球还在天上，狗先跑到起跳的地方看着等。"""
        self.start_on_floor(250.0)
        pg, roam, b = self.pg, self.pg.roam, self.pg.ball
        top = self.floor_y - 260
        self.frames[7] = (380.0, top, 360.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        goal = next(s for s in pg.supports() if s.key == 7 and s.kind == "window")
        b.x, b.y = 560.0, top - b.r - 20.0
        self.throw_and_fetch(30.0, -1200.0)                           # 在窗口上方往上抛：一秒多以后才落到窗口顶上
        self.assertEqual(pg.ball_turns_left(), 0, "看得出它停在窗口顶上")
        jumped = []

        def until():
            leg = roam.leg
            if leg is not None and leg.get("kind") == "jump" and not jumped:
                jumped.append(pg.ball_down_on(goal))
            return roam.carrying
        took, phases, _ = self.watch_fetch(until=until)
        self.assertIsNotNone(took, f"叼到了：{phases}")
        self.assertIn("standby", phases, "球还在天上：在下面等")
        self.assertEqual(jumped, [True], "球落到窗口顶上了才跳")
        self.assertEqual(roam.support.kind, "window")

    def test_an_out_of_reach_ball_is_barked_at_only_once_it_has_stopped(self):
        """够不着的等球停了再叫（球还在弹就叫，像是对着空气叫）。"""
        self.start_on_floor(560.0)
        pg, roam, b, dog = self.pg, self.pg.roam, self.pg.ball, self.win.dog
        top = self.floor_y - 300
        self.frames[7] = (self.ag.x() + 20.0, top, self.ag.width() - 40.0, 200.0)   # 铺满：上不去
        pg._sups = None
        pg._frames_at = -math.inf
        b.x, b.y = self.ag.x() + 300.0, top - b.r - 20.0
        self.throw_and_fetch(60.0, -1000.0)
        moving = []

        def until():
            if dog.player.name == "Bark":
                moving.append(not b.resting)
            return roam.task is None
        took, phases, _ = self.watch_fetch(20.0, until)
        self.assertIsNotNone(took, f"叫完了：{phases}")
        self.assertIn("standby", phases, "球还在弹：先等")
        self.assertTrue(moving, "够不着：叫了")
        self.assertFalse(any(moving), "球停了才叫")
        self.assertEqual(roam.support.kind, "floor")

    def test_the_body_turns_to_the_ball_while_the_head_watches_it(self):
        """头看着球、身子却跟着鼠标转，是拧着的。看球的时候身子跟球；不看了再按鼠标在哪边。"""
        from PySide6.QtCore import QPoint, QPointF
        from widget import window as window_module
        self.start_on_floor(400.0)
        self.step(0.3)
        w, dog, pg, b = self.win, self.win.dog, self.pg, self.pg.ball
        set_fetch(w, False)                                            # 只看不捡：站着看球飞
        x = round(w.scene_world()[0])
        y = round(self.floor_y) - 100
        with mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(x + 250, y)):   # 鼠标一直在右边
            self.step(3.0, lambda: dog.turn is None and abs(dog.yaw - 330.0) < 1.0)
            self.assertAlmostEqual(dog.yaw, 330.0, delta=1.0, msg="没球可看：朝鼠标")
            b.x, b.y = x - 200.0, self.floor_y - 200.0                # 球在左边往上飞
            b.throw(-60.0, -1300.0, w.ppm)
            pg.throw_id += 1
            self.step(0.05)
            self.assertIsNotNone(pg.look_point(), "看着球")
            self.assertEqual(w._home_yaw(), 210.0, "球在左边：朝左，鼠标在右边也一样")
            self.assertLess(dog.body_target[0], 0.0, "身子跟的是球")
            self.assertIsNotNone(self.step(3.0, lambda: dog.turn is None and abs(dog.yaw - 210.0) < 1.0), "身子转向球")
            self.assertFalse(b.resting, "这时球还在弹")
            self.assertIsNotNone(self.step(8.0, lambda: b.resting), "球停了")
            self.assertIsNone(pg.look_point(), "不看球了")
            self.step(0.05)
            self.assertEqual(w._home_yaw(), 330.0)
            self.assertAlmostEqual(dog.body_target[0], w._world_point(QPointF(x + 250, y))[0], delta=1e-6, msg="身子又按鼠标")
            self.assertIsNotNone(self.step(4.0, lambda: dog.turn is None and abs(dog.yaw - 330.0) < 1.0), "转回鼠标那边")

    # ---------- 扔了追不追（进圈才追），捡球开关 ----------
    def throw_now(self, speed, vertical=False):
        """手里的球按这个速度扔出去（像素 / 秒，往右；vertical 就是往正上方）。"""
        from PySide6.QtCore import QPointF
        import time as _t
        pg, b = self.pg, self.pg.ball
        t0 = _t.perf_counter()
        pg.grab.clear()
        pg.grab.append((t0 - 0.05, b.x, b.y + speed * 0.05) if vertical else (t0 - 0.05, b.x - speed * 0.05, b.y))
        pg.grab.append((t0, b.x, b.y))
        pg.ball_release(QPointF(b.x, b.y))

    def release_at_speed(self, speed):
        from PySide6.QtCore import QPointF
        import time as _t
        pg, b = self.pg, self.pg.ball
        pg._pick_up(QPointF(b.x, b.y), _t.perf_counter())
        self.throw_now(speed)

    def test_a_throw_before_the_ring_is_full_is_only_watched(self):
        """没进过圈的球扔出去不追；进了圈没停够就扔也不追。狗只看着球飞。"""
        self.start_on_floor()
        self.step(0.3)
        pg, roam, b = self.pg, self.pg.roam, self.pg.ball
        self.release_at_speed(900.0)                                  # 拿起来就扔：圈还是空的
        self.assertFalse(pg.ring.ready)
        self.assertGreater(abs(b.vx), 100.0, "球照样飞")
        self.step(0.3)
        self.assertIsNone(roam.task, "狗不追")
        self.assertIsNotNone(pg.look_point(), "看着球飞")
        self.step(3.0, lambda: b.resting)
        self.hold_ball_at(self.ring_point(), 0.2)                     # 进了圈，没停够
        self.assertGreater(pg.ring.progress, 0.0)
        self.assertFalse(pg.ring.ready)
        self.throw_now(900.0)
        self.step(0.3)
        self.assertIsNone(roam.task, "没停够：还是不追")
        self.assertIsNotNone(pg.look_point())

    def test_once_ready_even_a_gentle_drop_is_fetched(self):
        """圈满了以后松手就去追，扔出去、轻轻放下都算（不按松手快慢猜是玩还是挪开）。"""
        self.start_on_floor()
        self.step(0.3)
        pg, roam = self.pg, self.pg.roam
        self.hold_ball_at(self.ring_point(), 3.0, until=lambda: pg.ring.ready)
        self.throw_now(60.0)                                          # 慢慢放下：直接掉
        self.assertEqual((pg.ball.vx, pg.ball.vy), (0.0, 0.0), "放下的")
        self.assertEqual(roam.task, "fetch", "松手那一刻就去")
        self.assertNotEqual(roam.phase, "done")
        self.assertIsNotNone(self.step(20.0, lambda: roam.carrying), "叼起来了")

    def test_once_ready_the_ball_can_leave_the_ring_before_the_throw(self):
        """扔的那一下球多半已经出了圈：满了就一直算到松手，再拿出圈也不作废。"""
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        self.step(0.3)
        pg, roam = self.pg, self.pg.roam
        self.hold_ball_at(self.ring_point(), 4.0, until=lambda: roam.bowing)
        out = self.ring_point(inside=False)
        pg.ball_drag(QPointF(*out))
        pg.ball_drag(QPointF(*out))
        self.step(1.0)
        self.assertTrue(pg.ring.ready, "出了圈也还算准备好")
        self.assertTrue(roam.bowing, "接着俯身等")
        self.throw_now(-900.0)
        self.assertEqual(roam.task, "fetch")
        self.assertNotEqual(roam.phase, "done")

    def test_leaving_the_ring_before_it_is_full_drains_it_back(self):
        """没满就出了圈：进度往回退（满的 0.6 秒退空），狗接着站着看；回到圈里接着涨，不从头来。"""
        from PySide6.QtCore import QPointF
        from widget.ring import DRAIN_S
        self.start_on_floor()
        self.step(0.3)
        pg, roam, g = self.pg, self.pg.roam, self.pg.ring
        self.hold_ball_at(self.ring_point(), 0.6)
        before = g.progress
        self.assertGreater(before, 0.4)
        out = self.ring_point(inside=False)
        pg.ball_drag(QPointF(*out))
        pg.ball_drag(QPointF(*out))
        self.step(0.2)
        self.assertAlmostEqual(g.progress, before - 0.2 / DRAIN_S, delta=0.03, msg="往回退")
        self.assertEqual(roam.phase, "watch")
        self.assertGreater(g.alpha, 0.9, "圈还在")
        left = g.progress
        inside = self.ring_point()
        pg.ball_drag(QPointF(*inside))
        pg.ball_drag(QPointF(*inside))
        took = self.step(3.0, lambda: g.ready)
        self.assertAlmostEqual(took, (1.0 - left) * self.win.tuning["ring_hold_s"], delta=3 * DT, msg="接着涨")

    def test_letting_go_before_the_ring_is_full_stands_the_dog_back_up(self):
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        self.step(0.5)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        self.hold_ball_at(self.ring_point(), 0.5)
        self.assertEqual(roam.phase, "watch")
        self.assertFalse(pg.ring.ready)
        pg.ball_release(QPointF(pg.ball.x, pg.ball.y))
        self.assertEqual((pg.ball.vx, pg.ball.vy), (0.0, 0.0), "拿着不动松手：直接掉")
        self.step(1.0)
        self.assertFalse(roam.bowing)
        self.assertFalse(dog.shut_mouth)
        self.assertIsNone(roam.task, "起身待着")
        self.assertEqual(pg.ring.alpha, 0.0, "圈原地淡掉了")
        self.assertEqual(self.ring_shown(), [])

    def test_with_fetch_off_the_ball_still_moves_but_the_dog_only_watches(self):
        from PySide6.QtCore import QPointF
        self.start_on_floor()
        pg, roam, b = self.pg, self.pg.roam, self.pg.ball
        set_fetch(self.win, False)
        pg.ball_press(QPointF(b.x, b.y))
        self.step(0.3)
        self.assertIsNone(roam.task, "拿起球：不俯身")
        self.assertFalse(roam.bowing)
        self.assertEqual(pg.ring.alpha, 0.0, "不出圈")
        self.assertEqual(self.ring_shown(), [])
        self.assertIsNotNone(pg.look_point(), "看着球")
        self.release_at_speed(900.0)
        self.assertIsNone(roam.task, "扔出去：不追")
        self.assertGreater(abs(b.vx), 100.0, "球照样飞")
        self.assertIsNotNone(pg.look_point(), "看着球飞")

    def test_turning_fetch_off_stops_a_running_dog_and_puts_down_a_carried_ball(self):
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        pg.ball.throw(-900.0, -300.0, self.win.ppm)
        roam.fetch()
        self.step(0.5)
        set_fetch(self.win, False)
        self.assertIsNotNone(self.step(3.0, lambda: roam.task is None), "跑着的停下")
        set_fetch(self.win, True)
        self.cursor = (self.ag.x() + 700.0, self.floor_y - 100.0)
        pg.ball.throw(-300.0, -200.0, self.win.ppm)
        pg.throw_id += 1
        roam.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: roam.carrying), "叼起来了")
        self.step(0.2)
        x = roam.wx
        set_fetch(self.win, False)
        self.assertIsNotNone(self.step(10.0, lambda: roam.task is None), "放下了")
        self.assertFalse(pg.carried)
        self.assertFalse(roam.carrying)
        self.assertLess(abs(roam.wx - x), self.win.ppm * 1.6, "就地放下，没有再往鼠标那边走")

    def test_small_moves_behind_the_dog_walk_backwards(self):
        """叼着球时鼠标在身后一点点，不用转身，直接倒着走。"""
        self.start_on_floor(560.0)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        self.fetch_until_carrying()
        facing = roam.facing
        self.cursor = (roam.wx - facing * self.win.ppm * 0.45, self.floor_y - 100.0)
        s, gx = roam.here(), roam.wx - facing * self.win.ppm * 0.4       # 要去的地方在身后一点点
        seen = []
        roam._target, roam._put_dir = (s, gx), facing
        roam.route = list(roam._route(roam.here(), roam.wx, s, gx, roam.margin(s)).legs)
        roam.leg = None
        roam.phase = "carry"
        self.assertIsNotNone(self.step(3.0, lambda: seen.append(dog.player.name) or "Walk_B_IP" in seen), f"倒着走：{set(seen)}")
        self.assertEqual(roam.facing, facing, "没转身")

    def test_the_side_only_switches_once_the_mouse_is_well_past_the_dog(self):
        self.start_on_floor(560.0)
        roam = self.pg.roam
        self.cursor = (roam.wx + 100.0, self.floor_y - 100.0)
        _, _, d = roam._delivery_target()
        self.assertGreater(d, 0.0, "鼠标在右边：朝右放")
        self.cursor = (roam.wx - self.win.ppm * 0.3, self.floor_y - 100.0)
        _, _, d = roam._delivery_target()
        self.assertGreater(d, 0.0, "越过一点点：不换边")
        self.cursor = (roam.wx - self.win.ppm * 0.7, self.floor_y - 100.0)
        _, _, d = roam._delivery_target()
        self.assertLess(d, 0.0, "越过够远：换边")

    # ---------- 点狗只 duang ----------
    def test_clicking_the_dog_only_squashes_it(self):
        self.start_on_floor(560.0)
        pg, dog, w = self.pg, self.win.dog, self.win
        self.step(0.2)
        self.frames[7] = (380.0, self.floor_y - 260, 360.0, 200.0)
        pg._sups = None
        dog.action_at = float("inf")
        local = self.press_on_dog()
        self.step(0.15)
        self.assertGreater(dog.expr.squash, 0.12, "按下去压扁约 15%")
        g = w.mapToGlobal(local)
        self.mouse("release", g.x(), g.y())
        values = []
        self.step(0.7, lambda: values.append(dog.expr.squash) and False)
        self.assertLess(min(values), -0.01, "弹过头：微微拉长")
        self.assertLess(abs(values[-1]), 0.01, "弹完回到原样")
        self.assertIsNone(pg.roam.task, "旁边有窗口也不跳")
        self.assertIsNone(dog.action, "没有别的动作")
        self.assertIsNone(dog.jump)

    def test_squash_settings_come_from_the_tuning_page(self):
        self.start_on_floor()
        self.win.tuning.set("duang_depth", 0.3)
        self.press_on_dog()
        self.step(0.25)
        self.assertGreater(self.win.dog.expr.squash, 0.25)

    # ---------- 拎起来、扔出去（只在灵动交互） ----------
    def lift(self, dx=60.0, dy=-200.0):
        """按住狗往上拖。返回手现在在哪（全局）。"""
        w = self.win
        local = self.press_on_dog()
        g = w.mapToGlobal(local)
        self.mouse("move", g.x() + dx, g.y() + dy)
        return g.x() + dx, g.y() + dy

    def test_lifting_hangs_the_dog_from_its_belly(self):
        self.start_on_floor()
        pg, roam, w, dog = self.pg, self.pg.roam, self.win, self.win.dog
        self.step(0.2)
        wy0 = w.scene_world()[1]
        gx, gy = self.lift()
        self.assertTrue(w.dragging)
        self.assertTrue(roam.lifted)
        self.assertLess(w.scene_world()[1], wy0 - 150.0, "跟手上去了")
        self.step(0.5)
        self.assertGreater(dog.lift.w, 0.9, "姿势融进来了")
        pose = dog.frame()
        self.assertEqual(pose.footprint, [], "没有影子")
        spine = next(i for i, n in enumerate(dog.model.nodes) if n.name == "Spine_03")
        self.assertIn(spine, dog.player.rot_offset, "背拱起来")
        thigh = next(i for i, n in enumerate(dog.model.nodes) if n.name == "thigh_b.L")
        self.assertIn(thigh, dog.player.rot_offset, "腿垂着")
        self.mouse("release", gx, gy)
        self.assertFalse(roam.lifted)
        self.assertEqual(roam.task, "fall", "慢慢松手：掉下去")
        self.assertIsNotNone(self.step(5.0, lambda: roam.task is None), "落地")
        self.step(0.5)
        self.assertLess(dog.lift.w, 0.05, "姿势融回去了")
        self.assertNotEqual(dog.frame().footprint, [], "影子回来了")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)

    def test_without_dynamic_dragging_stays_plain(self):
        self.start_on_floor()
        w, dog = self.win, self.win.dog
        w.set_dynamic(False)
        self.step(0.2)
        local = self.press_on_dog()
        g = w.mapToGlobal(local)
        self.mouse("move", g.x() + 40, g.y() - 100)
        self.assertTrue(w.dragging)
        for _ in range(10):
            dog.update(DT)
        self.assertEqual(dog.lift.w, 0.0, "不悬空")
        self.assertFalse(self.pg.roam.lifted)
        self.assertNotEqual(dog.frame().footprint, [], "还有影子")
        self.mouse("release", g.x() + 40, g.y() - 100)

    def fling(self, vx, vy=-200.0):
        """拎起来、手还在动的时候松手。"""
        import time as _t
        pg = self.pg
        gx, gy = self.lift(0.0, -300.0)
        t0 = _t.perf_counter()
        wx, wy = self.win.scene_world()
        pg._hand.clear()
        pg._hand.append((t0 - 0.05, wx - vx * 0.05, wy - vy * 0.05))
        pg._hand.append((t0, wx, wy))
        with mock.patch("widget.playground.time.perf_counter", return_value=t0):   # 机器忙的时候也算刚松手
            self.mouse("release", gx, gy)

    def test_a_throw_counts_by_when_things_happened_not_when_they_were_processed(self):
        """卡在半空、没扔出去：主线程卡住时松手事件在排队，松手只比最后一次移动晚 28 毫秒，程序却隔了 400 毫秒才处理到。"""
        import time as _t
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        pg, roam = self.pg, self.pg.roam
        self.step(0.2)
        gx, gy = self.lift(0.0, -300.0)
        wx, wy = self.win.scene_world()
        t = _t.perf_counter() - 0.45                         # 这些都是 0.45 秒以前发生的
        pg._hand.clear()
        for i in range(8):
            pg.dog_dragged(wx + 1500.0 * 0.008 * (7 - i), wy, t + 0.008 * i)
        self.win.place_scene(wx, wy)
        pg.dog_dropped(t + 0.008 * 7 + 0.028)
        self.assertEqual(roam.task, "fall")
        self.assertLess(roam.leg["vx"], -300.0, "扔出去了，不是当场掉")

    def test_a_throw_has_a_speed_limit(self):
        from widget.roam import THROW_MAX_M
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        roam = self.pg.roam
        self.step(0.2)
        self.fling(-500000.0, 0.0)
        self.assertAlmostEqual(abs(roam.leg["vx"]), THROW_MAX_M * self.win.ppm, delta=1.0)

    def test_a_big_step_flies_up_to_the_wall_instead_of_stopping_short(self):
        """卡一下 dt 就大，一步能跨好几百像素：只看终点的话，离墙老远就当撞上了，看着像在半空撞了堵墙。"""
        from widget.roam import BODY_HALF_M
        self.start_on_floor(self.ag.x() + 900.0)
        pg, roam, w = self.pg, self.pg.roam, self.win
        self.step(0.2)
        self.fling(-1500.0, -300.0)
        leg = roam.leg
        leg["vx"] = -9000.0
        x0, px0 = roam.wx, leg["px"]
        half = BODY_HALF_M * w.ppm
        screen_left = min(s.geometry().x() for s in __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.screens())
        room = x0 - half - screen_left
        with mock.patch.object(pg, "dog_landed"):
            roam._fly_x(leg, min(0.1, room / 9000.0 + 0.01))
        self.assertGreater(leg["vx"], 0.0, "这一步碰到墙了：弹回来")
        self.assertAlmostEqual(leg["px"], px0 - room, delta=2.0, msg="走到墙边才停")

    def test_dragging_cannot_take_the_feet_below_the_floor(self):
        """拖到地面以下松手，下一帧就算落地了，甩不出去（录到的）。"""
        self.start_on_floor()
        w = self.win
        self.step(0.2)
        wx0 = w.scene_world()[0]
        local = self.press_on_dog()
        g = w.mapToGlobal(local)
        self.mouse("move", g.x() + 60, g.y() + 400)
        self.assertAlmostEqual(w.scene_world()[1], self.floor_y, delta=0.6, msg="脚踩在地面上")
        self.assertAlmostEqual(w.scene_world()[0], wx0 + 60, delta=0.6, msg="横着照样跟手")
        self.mouse("release", g.x() + 60, g.y() + 400)

    def land_fast(self, vx):
        """贴地甩出去：返回 (落地时的 x, 停下时的 x)。"""
        roam = self.pg.roam
        self.step(0.2)
        roam.place(roam.wx, self.floor_y - 10.0)
        roam.throw(vx, 0.0)
        self.assertIsNotNone(self.step(2.0, lambda: (roam.leg or {}).get("stage") == "land" or roam.task is None), "落地了")
        x0 = (roam.leg or {}).get("lx", roam.wx)
        self.assertIsNotNone(self.step(4.0, lambda: roam.task is None), "停下来了")
        return x0, roam.wx

    def test_a_fast_low_throw_slides_on_after_landing(self):
        """贴地甩出去，惯性一下就没了，像撞墙：落地后顺着速度滑一段。"""
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        x0, x1 = self.land_fast(-2600.0)
        self.assertLess(x1, x0 - 0.3 * self.win.ppm, "顺着滑了一段")
        self.assertGreater(x1, x0 - 2.5 * self.win.ppm, "滑得有限")
        self.assertAlmostEqual(self.pg.roam.wy, self.floor_y, delta=0.6)

    def test_sliding_can_be_turned_off(self):
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        self.win.tuning.set("land_slide", 0.0)
        x0, x1 = self.land_fast(-2600.0)
        self.assertLess(abs(x1 - x0), 0.15 * self.win.ppm)
        self.win.tuning.reset()

    def test_a_slide_stops_at_the_edge_of_the_screen(self):
        from widget.roam import BODY_HALF_M
        from PySide6.QtWidgets import QApplication
        screen_left = min(s.geometry().x() for s in QApplication.screens())
        self.start_on_floor(screen_left + BODY_HALF_M * self.win.ppm + 30.0)
        self.land_fast(-2600.0)
        self.assertGreaterEqual(self.pg.roam.wx, screen_left - 1.0, "没滑出屏幕")

    def test_sliding_off_a_window_falls_with_what_is_left(self):
        self.start_on_floor(self.ag.x() + self.ag.width() - 150.0)
        pg, roam = self.pg, self.pg.roam
        top = self.floor_y - 200.0
        left = self.ag.x() + self.ag.width() - 560.0
        self.frames[6] = (left, top, 500.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        self.step(0.2)
        self.win.place_scene(left + 60.0, top - 40.0)
        roam.place(left + 60.0, top - 40.0)
        roam.start("fall")
        roam.leg = roam._fall_leg(-2600.0, 0.0)
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None), "停下来了")
        self.assertEqual(roam.support.kind, "floor", "滑出窗口的头，接着掉到地上")
        self.assertLess(roam.wx, left)

    def test_a_gentle_drop_does_not_slide(self):
        self.start_on_floor(700.0)
        roam = self.pg.roam
        self.step(0.2)
        roam.place(700.0, self.floor_y - 20.0)
        roam.start("fall")
        roam.leg = roam._fall_leg(30.0, 0.0)
        self.assertIsNotNone(self.step(2.0, lambda: roam.task is None))
        self.assertLess(abs(roam.wx - 700.0), 30.0)

    def test_the_menu_goes_away_at_once_when_the_dog_is_thrown(self):
        """扔到另一块屏，「···」还短暂留在旧屏上。"""
        import time as _t
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        w, hover = self.win, self.win.hover
        self.step(0.2)
        hover.alpha = 0.5
        hover.active = True
        self.fling(-1500.0, -300.0)
        self.assertEqual(hover.alpha, 0.0, "一松手就收")
        hover.active = True
        hover.since = 0.0
        hover.tick(0.016, _t.perf_counter(), w._flinging())
        self.assertEqual(hover.alpha, 0.0, "飞的时候不出来")
        self.assertIsNotNone(self.step(6.0, lambda: self.pg.roam.task is None))
        hover.tick(0.016, _t.perf_counter(), w._flinging())
        self.assertGreater(hover.alpha, 0.0, "落地了照常")

    def test_no_window_list_while_the_dog_is_flung(self):
        """问一次窗口列表要等系统回话，真甩的时候一次能卡一百多毫秒：拎起来时问一次，拎着、飞着不问，落地后接着问。"""
        from widget import native
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        pg, roam = self.pg, self.pg.roam
        self.step(0.2)
        calls = []
        real = native.window_frames
        with mock.patch.object(native, "window_frames", lambda pid: calls.append(1) or real(pid)):
            self.lift(0.0, -300.0)
            self.assertEqual(len(calls), 1, "拎起来时问一次")
            pg._frames_at = -math.inf
            pg.supports()
            self.assertEqual(len(calls), 1, "拎着不问")
            self.mouse("release", *self.win.mapToGlobal(self.win.rect().center()).toTuple())
            pg._frames_at = -math.inf
            pg.supports()
            if roam.task == "fall":
                self.assertEqual(len(calls), 1, "飞着不问")
                self.step(6.0, lambda: roam.task is None)
            pg._frames_at = -math.inf
            pg.supports()
            self.assertGreater(len(calls), 1, "落地了接着问")

    def test_the_tail_stays_up_while_lifted(self):
        """拎起来尾巴应该还翘着，再甩，不荡下来。"""
        from widget.lift import LEG_MAX, TAIL_SWING, TAIL_UP_DEG
        lift = self.win.dog.lift
        lift.prepare()
        rig = lift.rig
        self.assertGreater(rig.deg[rig.tail], 0.0, "翘着")
        self.assertLess(LEG_MAX * TAIL_SWING, TAIL_UP_DEG * 0.5, "甩到头也还翘着")

    def test_the_ball_menu_does_not_cover_the_ball(self):
        """右击球，胶囊把球挡住了。"""
        from PySide6.QtCore import QPoint, QRectF
        self.start_on_floor()
        self.step(0.2)
        b, w = self.pg.ball, self.win
        w.show_ball_menu(QPoint(round(b.x), round(b.y)))
        menu = w._ball_menu
        pill = menu.pill_rect().translated(menu.pos().x(), menu.pos().y())
        self.assertFalse(pill.intersects(QRectF(b.x - b.r, b.y - b.r, 2.0 * b.r, 2.0 * b.r)), "没盖住球")
        menu.hide()

    def test_the_ball_menu_does_not_take_over_the_mouse(self):
        """胶囊开着时必须先点一下关掉，才拿得到球。球的优先级最大：一按球胶囊就收，球这一下照常算。"""
        from PySide6.QtCore import QPoint, QPointF, Qt
        self.start_on_floor()
        self.step(0.2)
        b, w = self.pg.ball, self.win
        w.show_ball_menu(QPoint(round(b.x), round(b.y)))
        menu = w._ball_menu
        self.assertTrue(menu.isVisible())
        self.assertNotEqual(menu.windowType(), Qt.Popup, "弹出菜单会接管鼠标，点外面的第一下只用来关它")
        self.pg.ball_press(QPointF(b.x, b.y))
        self.assertFalse(menu.isVisible(), "一按球就收")
        self.step(0.25)
        self.assertTrue(self.pg.ball_held, "球这一下照常拿起")

    def test_the_ball_menu_closes_on_a_click_elsewhere_or_when_the_pointer_wanders_off(self):
        """右键球的「我不要小球了」：鼠标移开、点别处就收；弹出来时右键还按着不算点别处。"""
        from PySide6.QtCore import QPoint
        from widget import native, popup
        self.start_on_floor()
        self.step(0.2)
        b, w = self.pg.ball, self.win
        w.show_ball_menu(QPoint(round(b.x), round(b.y)))
        menu = w._ball_menu
        near = QPoint(round(b.x), round(b.y))                     # 右键的那一点：胶囊就在它旁边
        down, at = [True], [near]
        with mock.patch.object(native, "mouse_any_down", lambda: down[0]), mock.patch.object(popup.QCursor, "pos", lambda: at[0]):
            menu._watch()
            self.assertTrue(menu.isVisible(), "弹出来时右键还按着、鼠标就在旁边：不收")
            down[0] = False
            menu._watch()
            at[0] = menu.geometry().center()
            menu._watch()
            self.assertTrue(menu.isVisible(), "鼠标挪到胶囊上：不收")
            down[0] = True
            menu._watch()
            self.assertTrue(menu.isVisible(), "按在胶囊上：不收")
            down[0] = False
            menu._watch()
            down[0], at[0] = True, near + QPoint(0, -2)
            menu._watch()
            self.assertFalse(menu.isVisible(), "点别处就收")
        self.assertTrue(w.ball_out, "收的只是胶囊，球还在")
        w.show_ball_menu(QPoint(round(b.x), round(b.y)))
        far = menu.geometry().center() + QPoint(round(popup.LEAVE_PX * menu._k) + menu.width(), 0)
        with mock.patch.object(native, "mouse_any_down", lambda: False), mock.patch.object(popup.QCursor, "pos", lambda: far):
            menu._watch()
        self.assertFalse(menu.isVisible(), "鼠标走远了就收")

    def test_putting_the_ball_away_mid_fetch_takes_it_from_the_mouth_and_out_again_lands_in_front(self):
        """球也是一件道具。收起来球淡掉，狗就没球玩（没有圈、不捡）；叼着的嘴里那颗也没了、不放下来；再拿出来放在狗前面。"""
        self.start_on_floor()
        pg, roam, w = self.pg, self.pg.roam, self.win
        self.cursor = (self.ag.x() + 700.0, self.floor_y - 100.0)
        pg.ball.throw(-300.0, -200.0, w.ppm)
        pg.throw_id += 1
        roam.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: roam.carrying), "叼起来了")
        w.set_ball_out(False)
        self.assertIsNone(pg.ball, "没有球了")
        self.assertFalse(pg.fetch_on, "捡球的闸跟着关")
        self.assertFalse(roam.carrying)
        self.assertIsNone(roam.task, "不再往你那走")
        self.assertFalse(pg.carried)
        self.step(0.5)
        self.assertFalse(pg.ball_win.isVisible(), "球的小窗口淡掉了")
        self.assertIsNone(pg.look_point())
        w.set_ball_out(True)
        b = pg.ball
        self.assertIsNotNone(b)
        self.assertLess(abs(b.x - roam.wx), w.ppm * 1.0, "放在狗前面")
        self.assertTrue(pg.fetch_on)
        self.step(0.4)
        self.assertTrue(pg.ball_win.isVisible())
        w.set_dynamic(False)
        w.set_ball_out(False)
        w.set_dynamic(True)
        self.assertIsNone(pg.ball, "收着的时候开灵动交互：没有球")

    def test_clicking_the_dog_or_ball_does_not_bring_the_app_forward(self):
        """点到狗、球时程序被激活，系统要忙半秒左右，没停稳就抓起来甩就是这样卡的（真鼠标对比：164 毫秒 → 11 毫秒）。"""
        from widget import native
        self.start_on_floor()
        self.step(0.2)
        with mock.patch.object(native, "set_no_activate") as asked:
            self.win.hide()
            self.win.show()
            self.pg.ball_win.hide()
            self.pg.ball_win.show()
        told = [c.args[0] for c in asked.call_args_list]
        self.assertIn(self.win, told)
        self.assertIn(self.pg.ball_win, told)

    def test_with_dynamic_on_the_dog_turns_to_the_mouse_not_by_screen_half(self):
        """灵动交互里看鼠标在狗哪边转身，一直开着，没有开关；鼠标跟随关着也转。"""
        from PySide6.QtCore import QPoint
        from widget import window as window_module
        self.start_on_floor(300.0)                                    # 屏幕左半边：不一律朝右
        self.step(0.3)
        w, dog = self.win, self.win.dog
        w.set_follow_cursor(False)
        self.assertTrue(dog.auto_turn)
        x = round(w.scene_world()[0])
        y = round(self.floor_y) - 100
        with mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(x - 250, y)):
            self.assertEqual(w._home_yaw(), 210.0, "鼠标在左边朝左")
            self.step(2.0, lambda: dog.turn is None and abs(dog.yaw - 210.0) < 1.0)
            self.assertAlmostEqual(dog.yaw, 210.0, delta=1.0)
        with mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(x + 250, y)):
            self.assertEqual(w._home_yaw(), 330.0, "鼠标在右边朝右")
            self.step(3.0, lambda: dog.turn is None and abs(dog.yaw - 330.0) < 1.0)
            self.assertAlmostEqual(dog.yaw, 330.0, delta=1.0, msg="身子转过去了")

    def test_the_turn_follows_the_mouse_quickly(self):
        """量鼠标过到另一边后多久开始转、多久转完；这几个数在开发者设置页。"""
        from PySide6.QtCore import QPoint
        from widget import window as window_module
        self.start_on_floor(300.0)
        self.step(0.3)
        w, dog = self.win, self.win.dog
        x, y = round(w.scene_world()[0]), round(self.floor_y) - 100
        past = round(0.8 * dog.body_length * w.ppm)                   # 刚离开狗身一点点就转（不用等 1.5 个身长）
        with mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(x + past, y)):
            self.assertIsNotNone(self.step(0.25, lambda: dog.turn is not None), "很快开始转")
            self.assertIsNotNone(self.step(1.0, lambda: dog.turn is None), "1 秒内转完")
            self.assertAlmostEqual(dog.yaw, 330.0, delta=1.0)
        w.tuning.set("turn_reach", 2.0)
        self.step(0.5)
        with mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(x - past, y)):
            self.assertIsNone(self.step(0.6, lambda: dog.turn is not None), "调大门槛：同样的距离不转了")
        w.tuning.reset()

    def test_with_only_follow_cursor_on_the_body_does_not_turn(self):
        """灵动交互关着时只转头，身子不跟着转，也没有开关。"""
        from PySide6.QtCore import QPoint
        from widget import prefs, window as window_module
        self.assertNotIn("auto_turn", prefs.DEFAULTS, "没有开关")
        self.start_on_floor(300.0)
        w, dog = self.win, self.win.dog
        w.set_follow_cursor(True)
        w.set_dynamic(False)
        self.assertFalse(dog.auto_turn)
        before = dog.yaw
        x, y = round(w.scene_world()[0]), round(self.floor_y) - 100
        for side in (-1, 1):
            with mock.patch.object(window_module.QCursor, "pos", lambda: QPoint(x + side * 600, y)):
                for _ in range(120):
                    dog.set_look_target(w._look_target(DT))
                    self.assertIsNone(dog.body_target)
                    dog.update(DT)
                self.assertIsNone(dog.turn)
                self.assertAlmostEqual(dog.yaw, before, delta=1.0, msg="身子没动")

    def test_there_are_no_keyboard_shortcuts_on_the_dog(self):
        """点狗不把程序切到前台，键盘本来也到不了这里。"""
        from PySide6.QtCore import Qt
        from widget.input import InputMixin
        self.assertNotIn("keyPressEvent", InputMixin.__dict__)
        self.assertEqual(self.win.focusPolicy(), Qt.NoFocus)

    def test_a_flung_dog_flies_less_far_than_the_ball_would(self):
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        roam, w = self.pg.roam, self.win
        self.step(0.2)
        self.fling(-1500.0)
        self.assertEqual(roam.task, "fall")
        leg = roam.leg
        self.assertLess(leg["vx"], 0.0, "往手甩的方向飞")
        self.assertAlmostEqual(leg["vx"], -1500.0 * w.tuning.throw_factor, delta=1.0, msg="按质量缩：18 公斤 × 0.45")
        self.assertAlmostEqual(w.tuning.throw_factor, 15.0 / (15.0 + 18.0), delta=0.001)
        x0 = roam.wx
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None), "落地了")
        self.assertLess(roam.wx, x0 - 50.0, "飞了一段")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)

    def test_heavier_dog_flies_less_far(self):
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        w = self.win
        w.tuning.set("mass_kg", 60.0)
        self.step(0.2)
        self.fling(-1500.0)
        self.assertAlmostEqual(self.pg.roam.leg["vx"], -1500.0 * 15.0 / 75.0, delta=1.0)
        self.assertIsNotNone(self.step(6.0, lambda: self.pg.roam.task is None))

    def test_a_flung_dog_hits_window_sides_and_screen_edges_without_leaving_the_screen(self):
        self.start_on_floor(self.ag.x() + self.ag.width() - 200.0)
        pg, roam, w = self.pg, self.pg.roam, self.win
        self.frames[5] = (self.ag.x() + 100.0, self.floor_y - 500.0, 150.0, 480.0)   # 左边一堵高窗口
        pg._sups = None
        pg._frames_at = -math.inf
        self.step(0.2)
        self.fling(-6000.0, 0.0)
        hit = []
        with mock.patch.object(pg, "dog_landed", lambda s: hit.append(s)):
            self.assertIsNotNone(self.step(8.0, lambda: roam.task is None), "落地了")
        self.assertTrue(hit, "撞到了有声音")
        right_of_window = self.frames[5][0] + self.frames[5][2]
        self.assertGreater(roam.wx, right_of_window, "被窗口右边挡住，没穿过去")
        self.frames.clear()
        pg._sups = None
        pg._frames_at = -math.inf
        self.step(0.2)
        self.fling(9000.0, 0.0)
        self.assertIsNotNone(self.step(10.0, lambda: roam.task is None), "落地了")
        self.assertLessEqual(roam.wx, self.ag.x() + self.ag.width(), "没飞出屏幕")

    def test_a_flung_dog_can_land_on_a_window_top(self):
        self.start_on_floor(self.ag.x() + self.ag.width() - 150.0)
        pg, roam = self.pg, self.pg.roam
        top = self.floor_y - 150.0
        self.frames[6] = (self.ag.x() + 60.0, top, self.ag.width() - 420.0, 150.0)
        pg._sups = None
        pg._frames_at = -math.inf
        self.step(0.2)
        self.fling(-1500.0, -300.0)
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None), "落地了")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", 6), "落在窗口上沿")

    def test_a_window_vanishing_just_as_the_dog_lands_does_not_leave_it_stuck(self):
        """从窗口右边 60 像素扔上去：还在空中就认定落在窗口上，这时窗口没了。（过了最高点会换空中姿势：从右边 210 像素扔的那一趟擦着窗口边飞到，
        飞到的那一帧正好落地，来不及在空中删窗口。）"""
        self.start_on_floor(self.ag.x() + self.ag.width() - 300.0)
        pg, roam = self.pg, self.pg.roam
        top = self.floor_y - 150.0
        self.frames[6] = (self.ag.x() + 60.0, top, self.ag.width() - 420.0, 150.0)
        pg._sups = None
        pg._frames_at = -math.inf
        self.step(0.2)
        self.fling(-1500.0, -300.0)
        self.assertIsNotNone(self.step(2.0, lambda: (roam.leg or {}).get("under") is not None and roam.leg["under"].kind == "window"), "正落向窗口")
        del self.frames[6]
        self.assertIsNotNone(self.step(4.0, lambda: roam.task is None), "窗口没了：接着掉，没卡在半空")
        self.assertEqual(roam.support.kind, "floor")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)

    # ---------- 落地分档（只拖了一点点，动作却像从很高掉下来） ----------
    def drop_from(self, height_m):
        roam, dog, w = self.pg.roam, self.win.dog, self.win
        self.step(0.2)
        w.place_scene(700.0, self.floor_y - height_m * w.ppm)
        self.pg.dog_dropped()
        seen = []
        self.assertIsNotNone(self.step(5.0, lambda: seen.append(dog.player.name) or roam.task is None), "落地了")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)
        return seen

    def test_a_tiny_drop_just_puts_the_feet_back(self):
        self.start_on_floor()
        seen = self.drop_from(0.2)
        self.assertFalse(any(c and c.startswith("JumpLand") for c in seen), f"不播落地片段：{set(seen)}")
        self.assertFalse(any(c and c.startswith("JumpAir") for c in seen), "也不换空中姿势")

    def test_a_small_drop_lands_on_its_feet(self):
        self.start_on_floor()
        seen = self.drop_from(0.55)
        self.assertIn("JumpLand_Place", seen)
        self.assertNotIn("JumpLand", seen)

    def test_a_high_drop_lands_like_before(self):
        self.start_on_floor()
        seen = self.drop_from(1.5)
        self.assertIn("JumpLand", seen)

    def throw_up(self, up_m, side_m=0.0):
        """从离地 0.05 米往上扔（米 / 秒）：每帧记（脚在哪、狗在播哪段），返回最高点之前的、之后的片段和真飞到离地多高（米）。"""
        roam, dog, w = self.pg.roam, self.win.dog, self.win
        self.step(0.2)
        w.place_scene(700.0, self.floor_y - 0.05 * w.ppm)
        roam.place(*w.scene_world())
        roam.lift_end(side_m * w.ppm, -up_m * w.ppm)
        rows = []
        self.assertIsNotNone(self.step(5.0, lambda: rows.append((roam.wy, dog.player.name)) or roam.task is None), "落地了")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)
        apex = min(range(len(rows)), key=lambda i: rows[i][0])
        return [c for _, c in rows[:apex]], [c for _, c in rows[apex + 1:]], (self.floor_y - rows[apex][0]) / w.ppm

    def test_a_throw_from_low_down_lands_by_how_high_the_dog_really_flew(self):
        """低处松手往上扔，飞得很高，落下来也得前爪先着地——看狗真飞到多高，不看松手在哪。
        往上飞时身子平着（JumpAir_Horiz）；过了最高点，最高点离下面那条线超过 land_mid_m（0.8 米）的换成往下探（JumpAir_low）、前爪先着地（JumpLand），
        不到的照旧平着、脚先着地（JumpLand_Place）。"""
        self.start_on_floor()
        mid = self.pg.tune["land_mid_m"]
        for up, side in ((3.0, 0.0), (5.0, 0.0), (6.0, 0.0), (5.0, 2.0)):
            rising, falling, top = self.throw_up(up, side)
            label = f"往上 {up:g}、横着 {side:g} 米 / 秒，飞到离地 {top:.2f} 米"
            self.assertEqual(set(rising), {"JumpAir_Horiz"}, f"{label}：往上飞的时候身子平着")
            if up >= 5.0:
                self.assertGreater(top, mid + 0.3, label)
                self.assertIn("JumpAir_low", falling, f"{label}：过了最高点换成往下探")
                self.assertIn("JumpLand", falling, f"{label}：前爪先着地")
                self.assertNotIn("JumpLand_Place", falling, label)
            else:
                self.assertLess(top, mid - 0.2, label)
                self.assertNotIn("JumpAir_low", falling, f"{label}：不高，照旧平着")
                self.assertIn("JumpLand_Place", falling, f"{label}：脚先着地")
                self.assertNotIn("JumpLand", falling, label)

    def test_landing_tiers_come_from_the_tuning_page(self):
        self.start_on_floor()
        self.win.tuning.set("land_light_m", 0.8)
        seen = self.drop_from(0.55)
        self.assertFalse(any(c and c.startswith("JumpLand") for c in seen), "调大了小落地：这个高度也不播")

    # ---------- 按住狗再拉 ----------
    def press_on_dog(self):
        """真走一遍鼠标事件：按在狗身上。"""
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        w = self.win
        local = QPointF(w.width() / 2.0, w.height() - 60.0)
        ev = QMouseEvent(QEvent.MouseButtonPress, local, w.mapToGlobal(local), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        w.mousePressEvent(ev)
        return local

    def mouse(self, kind, gx, gy, buttons=None):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        w = self.win
        g = QPointF(gx, gy)
        local = w.mapFromGlobal(g)
        types = {"move": QEvent.MouseMove, "release": QEvent.MouseButtonRelease}
        ev = QMouseEvent(types[kind], QPointF(local), g, Qt.LeftButton if kind == "release" else Qt.NoButton,
                         Qt.LeftButton if kind == "move" else Qt.NoButton, Qt.NoModifier)
        (w.mouseMoveEvent if kind == "move" else w.mouseReleaseEvent)(ev)
        w._apply_drag()                                      # 真的窗口每帧挪一次，这里当下一帧到了

    def test_pulling_to_a_window_out_of_reach_barks_twice(self):
        self.start_on_floor(560.0)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        self.frames[8] = (380.0, self.ag.y() + 240.0, 360.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        s = next(s for s in pg.supports() if s.key == 8 and s.kind == "window")
        roam_max = roam.max_up
        with mock.patch.object(roam, "max_up", lambda: roam_max() * 0.2):
            self.assertFalse(roam.go_to(s, 500.0))
        seen = set()
        at = []
        self.assertIsNotNone(self.step(8.0, lambda: (seen.add(dog.player.name), at.append(dog.player.time) if dog.player.name == "Bark" else None)[0] or roam.task is None), "叫完了")
        self.assertIn("Bark", seen, "够不着：叫两声")
        openings = [t for t in self.win.pack.clip_sounds["Bark"].at if min(at) < t <= max(at)]
        self.assertEqual(len(openings), 2, "只放嘴张开两次的那一段，声音跟嘴对上")

    # ---------- 跳窗口：方盒子、后脚在平面上 ----------
    def watch_jump(self, seconds=12.0):
        """推到狗做完，记每一帧：阶段、片段、根、后脚、最低的那只脚。"""
        import math as m
        from widget.render import ELEVATION
        roam, dog = self.pg.roam, self.win.dog
        ce = m.cos(m.radians(ELEVATION))
        rows = []

        def rec():
            leg = roam.leg or {}
            root, g = dog._last
            hind = sum(g[i][13] for i in dog._hind_feet) / len(dog._hind_feet)
            hz = sum(g[i][14] for i in dog._hind_feet) / len(dog._hind_feet)
            low = min(g[i][13] for i in dog._hind_feet + dog._front_feet)
            pel = g[dog._pelvis]
            d = roam.facing
            rows.append(dict(stage=leg.get("stage"), kind=leg.get("kind"), mode=leg.get("jump"), clip=dog.player.name,
                             wx=roam.wx, wy=roam.wy, hx=roam.wx + d * hz * roam.ppm,
                             hy=roam.wy - (hind - dog.planted_hind) * ce * roam.ppm, plane=leg.get("plane"),
                             lowest=roam.wy - (low - dog.planted_hind) * ce * roam.ppm,
                             px=roam.wx + d * pel[14] * roam.ppm, py=roam.wy - pel[13] * ce * roam.ppm))
            return roam.task is None
        self.assertIsNotNone(self.step(seconds, rec), "做完了")
        return rows

    def assert_no_pop(self, rows):
        """起跳、空中、落地一路上骨盆每帧走的距离都合理（真重力下最快也就飞行速度那么多），换片段那一帧不跳；落地时脚不钻到线下面。"""
        jump = [r for r in rows if r["stage"] in ("crouch", "air", "land")]
        self.assertTrue(jump)
        for r in jump:
            if r["stage"] == "land":
                self.assertLessEqual(r["lowest"], r["plane"] + 1.0, f"落地时脚不钻到线下面：{r['clip']}")
        for a, b in zip(jump, jump[1:]):
            self.assertLess(math.hypot(b["px"] - a["px"], b["py"] - a["py"]), 0.14 * self.win.ppm, f"身子没有一下子跳一截：{a['clip']} → {b['clip']}")

    def test_jumping_up_lands_with_the_hind_feet_on_the_top(self):
        self.start_on_floor(560.0)
        pg, roam = self.pg, self.pg.roam
        top = self.floor_y - 300
        self.frames[7] = (380.0, top, 360.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        s = next(s for s in pg.supports() if s.key == 7 and s.kind == "window")
        self.assertTrue(roam.go_to(s, 500.0))
        rows = self.watch_jump()
        air = [r for r in rows if r["stage"] == "air"]
        self.assertTrue(air, "跳了")
        self.assertLess(air[0]["wx"], 380.0, "从窗口左边外面起跳")
        self.assertEqual(next(r["clip"] for r in rows if r["stage"] == "land"), "JumpLand_Place", "不是扒着边爬上去的片段")
        crouch = [r for r in rows if r["stage"] == "crouch"]
        for r in crouch:
            self.assertAlmostEqual(r["hy"], self.floor_y, delta=0.06 * self.win.ppm, msg="起跳时后脚在地面上")
        land = [r for r in rows if r["stage"] == "land"]
        for r in land[12:]:
            self.assertLessEqual(r["hy"], top + 0.02 * self.win.ppm, "落地后后脚没有钻到台面下面")
        self.assert_no_pop(rows)

    def test_jumping_down_with_room_pushes_forward_off_the_end(self):
        self.start_on_floor(560.0)
        pg, roam = self.pg, self.pg.roam
        top = self.floor_y - 300
        self.climb_window(top)
        self.assertTrue(roam.go_to(pg.world.floors[0], self.ag.x() + 60.0))
        rows = self.watch_jump()
        air = [r for r in rows if r["stage"] == "air"]
        self.assertEqual(air[0]["mode"], "push")
        crouch = [r for r in rows if r["stage"] == "crouch"]
        hx = [r["hx"] for r in crouch[8:]]
        self.assertLess(max(hx) - min(hx), 0.03 * self.win.ppm, "蹬的时候后脚踩住不动")
        for r in crouch[8:]:
            self.assertAlmostEqual(r["hy"], top, delta=0.05 * self.win.ppm, msg="后脚在台面上")
        self.assertLess(crouch[-1]["wx"], crouch[0]["wx"], "身子往前送出去")
        over = [r for r in air if r["hx"] > 380.0]
        for r in over:
            self.assertLessEqual(r["hy"], top + 1.0, "还在窗口上方时后脚不低于台面")
        self.assertLess(air[-1]["wx"], 380.0, "落在窗口外面")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)
        self.assert_no_pop(rows)

    def test_jumping_down_without_room_drops_from_the_edge_without_going_up(self):
        """不要跳高。走到边上，后脚踩在边上，身子往下，直接落。"""
        self.start_on_floor(560.0)
        pg, roam = self.pg, self.pg.roam
        top = self.floor_y - 300
        left = self.ag.x() + self.win.ppm * 1.2                     # 左边只有 1.2 米，右边更少
        self.frames[7] = (left, top, self.ag.width() - left + self.ag.x() - 40.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        s = next(s for s in pg.supports() if s.key == 7 and s.kind == "window")
        self.win.place_scene(left + 300.0, top)
        pg.dog_dropped()
        self.assertIsNotNone(self.step(4.0, lambda: roam.task is None and roam.support is not None), "站到窗口上")
        self.assertEqual(roam.support.key, s.key)
        self.assertTrue(roam.go_to(pg.world.floors[0], self.ag.x() + 30.0))
        rows = self.watch_jump()
        modes = {r["mode"] for r in rows if r["mode"]}
        self.assertIn("edge", modes)
        crouch = [r for r in rows if r["stage"] == "crouch"]
        for r in crouch[8:]:
            self.assertAlmostEqual(r["hy"], top, delta=0.05 * self.win.ppm, msg="后脚一直踩在台面上")
        locked = crouch[int(len(crouch) * 0.55):]
        hx = [r["hx"] for r in locked]
        self.assertLess(max(hx) - min(hx), 0.03 * self.win.ppm, "后脚踩住不动")
        self.assertLess(abs(hx[-1] - left), 0.08 * self.win.ppm, "就踩在窗口边上")
        self.assertGreater(crouch[-1]["wy"], top + 0.7 * self.win.ppm, "身子已经探下去了")
        py = [r["py"] for r in rows if r["stage"] in ("crouch", "air")]
        self.assertGreaterEqual(min(py), py[0] - 0.05 * self.win.ppm, "全程没有往上蹦")
        landed = [r for r in rows if r["stage"] == "land"][-1]
        self.assertGreater(landed["wx"] - self.ag.x(), 0.5 * self.win.ppm, "落下来鼻子还在屏幕里")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)
        self.assert_no_pop(rows)

    def test_a_window_with_no_room_on_either_side_barks_when_the_ball_is_below(self):
        """窗口铺满：下不来，球在下面就叫两声。"""
        self.start_on_floor(560.0)
        pg, roam, dog = self.pg, self.pg.roam, self.win.dog
        top = self.floor_y - 300
        self.frames[7] = (self.ag.x() + 20.0, top, self.ag.width() - 40.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        self.win.place_scene(self.ag.x() + 300.0, top)
        pg.dog_dropped()
        self.assertIsNotNone(self.step(4.0, lambda: roam.task is None and roam.support is not None and roam.support.kind == "window"), "站到窗口上")
        b = pg.ball
        b.x, b.y, b.resting, b.on = self.ag.x() + 400.0, self.floor_y - b.r, True, ("floor", 0)
        pg.throw_id += 1
        roam.fetch()
        seen = set()
        self.assertIsNotNone(self.step(12.0, lambda: seen.add(dog.player.name) or roam.task is None), "叫完了")
        self.assertIn("Bark", seen)
        self.assertEqual(roam.support.kind, "window", "还在窗口上，等人拖下来")

    def test_a_covered_window_sends_the_dog_down_by_its_edge(self):
        self.start_on_floor(560.0)
        roam = self.pg.roam
        self.climb_window(self.floor_y - 260)
        self.assertTrue(roam.descend())
        self.assertEqual(roam.task, "descend")
        self.assertIsNotNone(self.step(8.0, lambda: roam.task is None), "下来了")
        self.assertEqual(roam.support.kind, "floor")

    def test_the_dog_rides_a_window_and_falls_when_it_closes(self):
        self.start_on_floor(560.0)
        roam = self.pg.roam
        top_y = self.floor_y - 260
        self.climb_window(top_y)
        self.assertAlmostEqual(roam.wy, top_y, delta=0.5, msg="脚踩在窗口上沿")
        self.assertEqual(roam.home.kind, "window", "家改到窗口上")
        wx0 = roam.wx
        self.frames[7] = (300.0, top_y - 40, 360.0, 200.0)       # 窗口被拖走
        self.step(0.2)
        self.assertAlmostEqual(roam.wx, wx0 - 80, delta=0.5, msg="狗跟着窗口挪")
        self.assertAlmostEqual(roam.wy, top_y - 40, delta=0.5)
        sx, sy = self.win.scene_world()
        self.assertAlmostEqual(sx, roam.wx, delta=0.6, msg="窗口跟着狗")
        del self.frames[7]                                        # 窗口关了
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None and roam.support is not None and roam.support.kind == "floor"),
                             "掉回地面")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.5)
        self.assertFalse(self.win.dog.puppet)

    def test_jump_height_follows_the_size_of_the_dog(self):
        """狗大跳得高、狗小跳得矮；不再有按屏幕封顶的那道。"""
        self.start_on_floor()
        roam = self.pg.roam
        at_1 = roam.max_up()
        self.win.set_scale(2.0)
        self.assertAlmostEqual(roam.max_up(), at_1 * 2.0, delta=0.5)
        self.win.set_scale(0.5)
        self.assertAlmostEqual(roam.max_up(), at_1 * 0.5, delta=0.5)

    def test_a_window_too_high_is_out_of_reach(self):
        self.start_on_floor(560.0)
        self.win.set_scale(0.5)
        self.frames[8] = (380.0, self.ag.y() + 120.0, 360.0, 200.0)
        self.pg._sups = None
        self.pg._frames_at = -math.inf
        s = next((s for s in self.pg.supports() if s.key == 8 and s.kind == "window"), None)
        self.assertIsNotNone(s)
        self.assertFalse(self.pg.roam.route_to(s, 500.0).reachable, "狗小跳得矮：够不着")

    # ---------- 推荐大小 ----------
    def test_recommended_size_fits_reach_and_headroom_to_the_screen(self):
        from widget.playground import recommended_scale
        self.assertEqual(recommended_scale(982), 1.25, "MacBook")
        self.assertEqual(recommended_scale(1440), 1.85, "2K、LG 带鱼屏")
        self.assertEqual(recommended_scale(900), 1.15, "13 寸 Air")
        self.assertEqual(recommended_scale(300), 0.6, "有下限")
        self.assertEqual(recommended_scale(2160), 2.75, "4K 电视按 1 倍用（不封顶）")
        self.assertEqual(recommended_scale(5000), 6.4, "没有上限")

    def test_first_time_on_uses_the_recommended_size_only_if_size_was_never_touched(self):
        w = self.win
        with mock.patch.object(w, "recommended_scale", lambda screen=None: 1.5):
            w._apply_first_size(self.app.primaryScreen(), animated=False)
            self.assertEqual(w.scale, 1.5, "没动过：用推荐大小")
            w.set_scale(1.2)
            w.prefs.set("size_suggested", False)
            w._apply_first_size(self.app.primaryScreen(), animated=False)
            self.assertEqual(w.scale, 1.2, "旧版本留下来的大小算动过")
            w.set_scale(1.0)
            w.prefs.set("size_suggested", True)
            w._apply_first_size(self.app.primaryScreen(), animated=False)
            self.assertEqual(w.scale, 1.0, "只用一次")
            w.prefs.set("size_suggested", False)
            w.mark_scale_chosen()
            w._apply_first_size(self.app.primaryScreen(), animated=False)
            self.assertEqual(w.scale, 1.0, "你调过：不动")

    # ---------- 够不着的提示 ----------
    def test_out_of_reach_above_shows_a_bubble_each_time_and_below_only_barks(self):
        self.start_on_floor(560.0)
        pg, roam, w = self.pg, self.pg.roam, self.win
        top = self.ag.y() + 240.0
        self.frames[8] = (380.0, top, 360.0, 200.0)
        pg._sups = None
        pg._frames_at = -math.inf
        s = next(s for s in pg.supports() if s.key == 8 and s.kind == "window")
        with mock.patch.object(w, "show_too_high") as hint:
            pg.barking("window", 8, s.x0 + 100.0)
            pg.barking("window", 8, s.x0 + 100.0)
            self.assertEqual(hint.call_count, 2, "每次够不着都说")
            roam.wy = top - 200.0                                    # 狗在它上面：只叫
            self.frames[9] = (900.0, top + 100.0, 360.0, 200.0)
            pg._sups = None
            pg._frames_at = -math.inf
            pg.barking("window", 9, 950.0)
            self.assertEqual(hint.call_count, 2, "在下面的不说")

    def show_bubble(self):
        w = self.win
        self.step(0.1)
        w.show_too_high()
        return w._bubble

    def head_point(self):
        from widget.geometry import project
        from widget.render import ELEVATION
        w = self.win
        hx, hy = project(w.dog.head_position(), w.ppm, w.ground_px, ELEVATION, w.width(), w.draw_offset)
        return w.x() + hx, w.y() + w.height() - hy

    def test_the_bubble_points_at_the_dog_and_cannot_be_clicked(self):
        from PySide6.QtCore import Qt
        self.start_on_floor(420.0)
        b = self.show_bubble()
        self.assertTrue(b.isVisible())
        self.assertEqual(b.text, "A bit too high")
        self.assertTrue(b.windowFlags() & Qt.WindowTransparentForInput, "点不到")
        self.assertEqual(b._placed, "above", "头顶放得下就放头顶")
        tip = b.tail_global()
        hx, hy = self.head_point()
        self.assertLess(abs(tip.x() - hx), 2.0, "尾巴指着狗头")
        self.assertLess(tip.y(), hy, "在头上面")
        self.assertLess(hy - tip.y(), 0.25 * self.win.ppm, "离头不远")
        self.assertTrue(self.ag.contains(b.frameGeometry().adjusted(b.M, b.M, -b.M, -b.M)), "不出屏幕")

    def test_the_bubble_follows_the_dog_and_goes_away_by_itself(self):
        w = self.win
        self.start_on_floor(420.0)
        b = self.show_bubble()
        x0 = b.x()
        w.place_scene(300.0, self.floor_y)
        w._sync_bubble(DT)
        self.assertLess(b.x(), x0 - 60.0, "狗动它跟着动")
        w._sync_bubble(b.SHOW_S - 0.05)
        self.assertTrue(b.isVisible())
        self.assertLess(b.windowOpacity(), 1.0, "最后淡出")
        w._sync_bubble(0.1)
        self.assertFalse(b.isVisible(), "一会儿自己消失")

    def test_the_bubble_goes_beside_the_head_when_there_is_no_room_above(self):
        w = self.win
        self.start_on_floor(420.0)
        self.step(0.1)
        w.show_too_high()
        b = w._bubble
        b.follow(420.0, self.ag.y() + 2.0, 40.0, 1.0, self.ag, 0.0)
        self.assertEqual(b._placed, "right", "头顶放不下：放在狗脸那边")
        self.assertGreaterEqual(b.y() + b.M, self.ag.y())
        b.follow(self.ag.x() + self.ag.width() - 20.0, self.ag.y() + 2.0, 40.0, 1.0, self.ag, 0.0)
        self.assertEqual(b._placed, "left", "那边也放不下：换另一边")
        self.assertLessEqual(b.x() + b.width() - b.M, self.ag.x() + self.ag.width())
        b.hide()

    def test_dragging_cannot_take_the_head_above_the_top_of_the_screen(self):
        self.start_on_floor()
        w = self.win
        self.step(0.1)
        local = self.press_on_dog()
        g = w.mapToGlobal(local)
        self.mouse("move", g.x(), g.y() - 5000.0)
        self.assertTrue(w.dragging)
        head = w.y() + w.scene_ground - w.dog.rest_top() * w.ppm
        top = min(s.geometry().y() for s in self.app.screens())
        self.assertGreaterEqual(head, top - 0.5, "头顶没有高出屏幕最上沿")
        self.assertLess(head, top + 2.0, "但能拖到最顶上")
        self.mouse("release", g.x(), g.y() - 5000.0)

    def test_scaling_up_near_the_top_keeps_the_head_on_the_screen(self):
        self.start_on_floor()
        w = self.win
        w.set_dynamic(False)
        self.step(0.1)
        top = min(s.geometry().y() for s in self.app.screens())
        w.move(w.x(), top + 5)
        w._anchor = None
        w.set_scale(2.5)
        head = w.y() + w.scene_ground - w.dog.rest_top() * w.ppm
        self.assertGreaterEqual(head, top - 0.5, "放大时头也不出屏幕")
        w.set_scale(1.0)

    def test_a_window_on_another_desktop_drops_the_dog(self):
        """切到别的桌面后系统还照样报那个窗口的位置，狗站在看不见的窗口上、悬在半空。"""
        self.start_on_floor(560.0)
        roam = self.pg.roam
        self.climb_window(self.floor_y - 260)
        self.hidden.add(7)                                         # 切到别的桌面：列表里没有了
        self.pg._frames_at = -math.inf
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None and roam.support is not None and roam.support.kind == "floor"),
                             "掉回地面")

    def test_a_window_swept_away_by_the_system_drops_the_dog_where_it_was(self):
        """台前调度把窗口收进左边那排：系统报的是缩略图的位置。狗不跟着"瞬移"过去，原地掉下来。"""
        self.start_on_floor(560.0)
        roam = self.pg.roam
        self.climb_window(self.floor_y - 260)
        wx0 = roam.wx
        self.frames[7] = (10.0, 150.0, 150.0, 100.0)               # 一帧之内挪走、变小
        self.step(0.1)
        self.assertEqual(roam.task, "fall", "当它没了：掉下去")
        self.assertAlmostEqual(roam.wx, wx0, delta=0.15 * self.win.ppm, msg="原地掉，不跟去缩略图那里")

    def test_dropped_in_mid_air_the_dog_falls_to_the_floor(self):
        self.start_on_floor()
        self.win.place_scene(500.0, self.floor_y - 300)
        self.pg.dog_dropped()
        self.assertEqual(self.pg.roam.task, "fall")
        self.assertIsNotNone(self.step(4.0, lambda: self.pg.roam.task is None))
        self.assertAlmostEqual(self.win.scene_world()[1], self.floor_y, delta=0.6)

    def test_dragging_never_leaves_the_window_straddling_a_screen_edge(self):
        """拖到 LG 左边一闪一闪：拖动时窗口骑在屏幕边上，系统把它弹回去。现在拖动走 place_scene，窗口整个待在屏里。"""
        self.start_on_floor()
        w = self.win
        self.step(0.1)
        local = self.press_on_dog()
        g = w.mapToGlobal(local)
        for dx in range(0, -2400, -120):
            self.mouse("move", g.x() + dx, g.y() - 100)
            self.assertGreaterEqual(w.x(), self.app.primaryScreen().geometry().x(), "窗口没有伸出屏幕左边")
        self.mouse("release", g.x() - 2400, g.y() - 100)

    def test_the_dog_turns_while_it_starts_running(self):
        """边转边跑，不原地转完身（1 秒）才起步。"""
        self.start_on_floor(400.0)
        roam, dog = self.pg.roam, self.win.dog
        self.pg.ball.x = 400.0 + 260.0                             # 球在狗身后（狗朝左）
        self.pg.ball.throw(600.0, -200.0, self.win.ppm)
        roam.fetch()
        x0 = roam.wx
        took = self.step(2.0, lambda: abs(roam.wx - x0) > 3.0)
        self.assertIsNotNone(took)
        self.assertLess(took, 0.45, "扔出去不到半秒就跑起来了")
        self.assertGreater(roam.wx, x0, "往身后（右边）跑")

    def test_resizing_keeps_the_feet_on_the_floor(self):
        """跑着调大小，停下来不能凭空"落地"一下。"""
        self.start_on_floor()
        roam = self.pg.roam
        self.win.set_scale(1.5)
        floor = self.ag.y() + self.ag.height() - 18.0 * 1.5
        self.assertAlmostEqual(roam.wy, floor, delta=0.6, msg="站着调大小：脚贴着新的地面")
        self.assertAlmostEqual(self.win.scene_world()[1], floor, delta=0.6)
        self.assertFalse(roam.busy, "不掉")
        self.pg.ball.throw(-900.0, -300.0, self.win.ppm)
        roam.fetch()
        self.step(0.7)
        self.win.set_scale(1.0)
        tasks = set()
        self.assertIsNotNone(self.step(40.0, lambda: tasks.add(roam.task) or roam.task is None), "跑着调大小：照样叼过来")
        self.assertNotIn("fall", tasks, "没有凭空掉一下")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)

    # ---------- 兜底 ----------
    def test_grabbing_the_dog_mid_fetch_drops_the_ball_from_its_mouth(self):
        self.start_on_floor()
        pg, roam = self.pg, self.pg.roam
        pg.ball.throw(-900.0, -300.0, self.win.ppm)
        roam.fetch()
        self.assertIsNotNone(self.step(40.0, lambda: roam.carrying), "叼起来了")
        pg.dog_grabbed()
        self.assertFalse(roam.carrying)
        self.assertFalse(pg.carried)
        self.assertTrue(pg.ball_win.isVisible(), "球从嘴里掉出来")
        self.assertTrue(roam.lifted, "拎起来了")
        self.assertIsNone(self.win.dog.props.item)
        pg.dog_dropped()
        self.assertIsNotNone(self.step(5.0, lambda: roam.task is None), "松手落回去")
        self.assertFalse(self.win.dog.puppet, "交回控制器")

    def test_an_error_inside_the_playground_never_freezes_the_dog(self):
        self.start_on_floor()
        self.pg.ball.throw(-900.0, -300.0, self.win.ppm)
        self.pg.roam.fetch()
        self.step(0.5)
        with mock.patch.object(self.pg.roam, "update", side_effect=RuntimeError("boom")):
            self.win._frame()
        self.assertFalse(self.pg.active, "出错：灵动交互这一块停掉")
        self.assertFalse(self.win.dog.puppet, "狗交回控制器")
        self.assertTrue(self.win._anim_timer.isActive(), "下一帧照常排上")
        self.win._anim_timer.stop()

    def test_turning_dynamic_off_puts_the_ball_away_and_stops_roaming(self):
        self.start_on_floor()
        self.pg.ball.throw(-900.0, -300.0, self.win.ppm)
        self.pg.roam.fetch()
        self.step(0.5)
        self.win.set_dynamic(False)
        self.assertFalse(self.pg.active)
        self.assertFalse(self.pg.roam.busy)
        self.assertFalse(self.win.dog.puppet)
        self.step(0.5)

    def test_turning_dynamic_off_or_an_error_puts_the_ring_away_at_once(self):
        """停了就没有下一帧来淡掉它：关灵动交互、出错兜底都当场收起圈。"""
        for how in ("off", "error"):
            self.start_on_floor()
            self.step(0.5)
            pg = self.pg
            self.hold_ball_at(self.ring_point(), 0.4)
            self.assertTrue(self.ring_shown())
            if how == "off":
                self.win.set_dynamic(False)
            else:
                with mock.patch.object(pg.roam, "update", side_effect=RuntimeError("boom")):
                    self.win._frame()
                self.win._anim_timer.stop()
            self.assertFalse(pg.active)
            self.assertEqual(self.ring_shown(), [], how)
            self.assertEqual(pg.ring.alpha, 0.0)
            self.assertFalse(pg.ring.ready)
            pg.ball_held = False                                     # 出错兜底不管手里的球（下一次按球重来）
            self.win.set_dynamic(True)

    # ---------- 灵动交互的子选项（窗口当台子；捡球在上面） ----------
    def test_with_hop_windows_off_only_the_floors_are_left_and_whoever_stands_on_a_window_falls(self):
        """「窗口当台子」关着：狗和球都不把别的 App 的窗口当台子（只有每块屏的地面，窗口不挡路、不弹球）；
        关的那一下狗、球正站在窗口上，照窗口没了处理：原地掉下来。开回来窗口又是台子。"""
        self.start_on_floor(560.0)
        pg, roam, w = self.pg, self.pg.roam, self.win
        self.assertTrue(w.hop_windows_on, "默认开")
        top_y = self.floor_y - 260
        self.climb_window(top_y)
        b = pg.ball
        b.x, b.y, b.resting, b.on = roam.wx + 100.0, top_y - 60.0, False, None    # 球也落到这个窗口上
        b.vx = b.vy = 0.0
        roam.fetch = lambda: None                                    # 只看球，别让狗去捡
        self.step(1.5)
        self.assertEqual(b.on, ("window", 7), "球停在窗口上")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", 7))
        self.assertTrue(pg.ball_platforms() and pg.ball_edges() and pg.route_blocks())
        w.set_play_option("hop_windows", False)
        self.assertIs(w.settings.values["hop_windows"], False)
        self.assertTrue(all(s.kind == "floor" for s in pg.supports()), "只剩地面")
        self.assertEqual((pg.ball_platforms(), pg.ball_edges(), pg.route_blocks()), ([], [], []), "球不停窗口、不撞窗口边，窗口也不挡路")
        self.assertFalse(pg.window_listed(7))
        self.assertIsNone(pg.window_top(7))
        self.assertIsNotNone(self.step(6.0, lambda: roam.task is None and roam.support is not None and roam.support.kind == "floor"),
                             "狗原地掉回地面")
        self.assertAlmostEqual(roam.wy, self.floor_y, delta=0.6)
        self.step(2.0, lambda: b.resting)
        self.assertTrue(b.resting)
        self.assertEqual(b.on[0], "floor", "球也掉到地面")
        self.assertAlmostEqual(b.y + b.r, self.floor_y, delta=1.0)
        self.assertFalse(w.dog.puppet)
        self.fling(-1200.0, -900.0)                                  # 往窗口那边扔狗：不落在窗口上
        self.assertIsNotNone(self.step(8.0, lambda: roam.task is None), "落地了")
        self.assertEqual(roam.support.kind, "floor")
        w.set_play_option("hop_windows", True)
        self.assertTrue(any(s.kind == "window" and s.key == 7 for s in pg.supports()), "开回来窗口又是台子")
        self.assertTrue(pg.window_listed(7))


if __name__ == "__main__":
    unittest.main()
