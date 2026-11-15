"""某一只同桌放进真窗口（offscreen）里一帧帧地推：萨摩耶的重调、性子的测试共用的底子（tests/test_retune.py、tests/test_temper.py）。
和 tests/test_playground.py 一个架子，只是模型按包来（PACK）：假设置、假的别的 App 的窗口、卸载器挡住（从源码跑到它会清真用户的设置）、
检查更新的缓存放临时目录。模型文件不在（购买的内容不入 git）整类跳过。"""
import math
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from tests.panel_base import QUIET, FakeSettings
from widget import packs

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DT = 1 / 60
COLLIE, SAMOYED = packs.DEFAULT_PET, "samoyed"
HAS = {COLLIE: Path(config.MODEL_PATH).is_file(), SAMOYED: (config.ROOT / "models" / "samoyed.glb").is_file()}
_models: dict = {}


def load(pack_id: str):
    """(包, 模型)：一只只读一遍，几个测试类共用（窗口不改模型）。"""
    if pack_id not in _models:
        pack = packs.discover()[pack_id]
        _models[pack_id] = (pack, packs.load_model(pack))
    return _models[pack_id]


def seeded(values: dict):
    """一开始就存着这些值的假设置（窗口自己建设置对象，所以给的是类）。"""
    class Seeded(FakeSettings):
        def __init__(self, *args):
            super().__init__(*args)
            self.values.update(values)
    return Seeded


def throws(n: int = 60, seed: int = 20261112) -> list[tuple[float, float, float, float, float]]:
    """同一组随机扔（方案量数时用的那一组）：狗站在屏宽的几成、球从狗前面多远（米，带方向）多高（米）出手、横竖多快（米 / 秒）。"""
    rng = random.Random(seed)
    return [(rng.uniform(0.18, 0.82), rng.choice((-1.0, 1.0)) * rng.uniform(0.2, 0.5), rng.uniform(0.3, 1.2),
             rng.choice((-1.0, 1.0)) * rng.uniform(0.6, 7.5), -rng.uniform(0.4, 4.6)) for _ in range(n)]


class RoomCase(unittest.TestCase):
    PACK = SAMOYED
    SETTINGS: dict = {}                                       # 启动前设置里就存着的

    @classmethod
    def setUpClass(cls):
        if not HAS.get(cls.PACK, False):
            raise unittest.SkipTest(f"{cls.PACK} 的模型文件不在（购买的内容不入 git）")
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        qInstallMessageHandler(lambda mode, ctx, msg: None if any(s in msg for s in QUIET) else sys.stderr.write(msg + "\n"))
        cls.app = QApplication.instance() or QApplication([])
        cls.pack, cls.model = load(cls.PACK)

    WANDER = False                                           # 自己溜达：别的测试要的是确定地待着，默认不走；测溜达的类打开

    def setUp(self):
        if not self.WANDER:
            from widget import temper
            p = mock.patch.object(temper, "wander_every", lambda tune: (1e9, 1e9))
            p.start()
            self.addCleanup(p.stop)
        self.frames = {}                                     # 假的别的 App 的窗口：窗口号 → (x, y, w, h)
        self.ag = self.app.primaryScreen().availableGeometry()
        self.cursor = (self.ag.x() + 200.0, self.ag.y() + self.ag.height() - 168.0)   # 假的鼠标（狗叼着球往这走）
        self.win = self.make_window(self.SETTINGS)
        self.pg = self.win.playground
        self.floor_y = self.ag.y() + self.ag.height() - 18.0 * self.win.scale

    def make_window(self, settings: dict = None, pack_id: str = None):
        """建一个窗口（不给 pack_id 就是这一类的那只）。同一条测试里可以再建一只别的来对照。"""
        import widget.window as window
        from widget import native, uninstall, updater
        pack, model = (self.pack, self.model) if pack_id is None else load(pack_id)
        cache = tempfile.TemporaryDirectory()
        self.addCleanup(cache.cleanup)
        from widget.dogctl import DogController
        for p in (mock.patch.object(window, "QSettings", seeded(settings or {})),
                  mock.patch.object(window, "DogController", lambda m: DogController(m, seed=5)),   # 从建出来那一刻起随机数就是定的（头一个随机动作什么时候来、挑哪段待机）
                  mock.patch.object(native, "window_frames", lambda pid: [(n, 99, *f) for n, f in self.frames.items()]),
                  mock.patch.object(native, "window_frame", lambda n: self.frames.get(n)),
                  mock.patch.object(native, "window_covered", lambda n, x, y, pid: False if n in self.frames else None),
                  mock.patch.object(uninstall, "start", side_effect=AssertionError("tests must never start the real uninstaller")),
                  mock.patch.object(updater, "CACHE_DIR", Path(cache.name))):
            p.start()
            self.addCleanup(p.stop)
        win = window.CompanionWindow(model, pack=pack)
        win._anim_timer.stop()
        p = mock.patch.object(win.playground, "cursor", lambda: self.cursor)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.put_away, win)
        return win

    @staticmethod
    def put_away(win):
        pg = win.playground
        if pg.ball_win is not None:
            pg.ball_win.hide()
        for rw in pg.ring_wins.values():
            rw.hide()
        for w in (win.settings_panel, win):
            if w is not None:
                w.hide()

    def attach_card(self):
        """给这只同桌挂上设置卡片（和 tests/panel_base.py 一样的做法；卸载器、检查更新在 make_window 里挡住了）。"""
        from widget.settings import SettingsPanel
        repo = mock.patch.object(config, "UPDATE_REPO", "example/deskmate")
        repo.start()
        self.addCleanup(repo.stop)
        card = SettingsPanel(self.win)
        self.win.attach_panels(card)
        self.addCleanup(card.hide)
        return card

    # ---------- 推帧 ----------
    def start_on_floor(self, x=560.0, win=None):
        win = win or self.win
        win.show()
        win.place_scene(x, self.ag.y() + self.ag.height() - 18.0 * win.scale)
        win.dog.snap_home(210.0)
        self.assertTrue(win.dynamic, "灵动交互新装默认开")
        win.playground.start()
        win.playground._frames_at = -math.inf

    def step(self, seconds, until=None, win=None):
        """按窗口的每一帧那样推（不走真计时器）：游乐场 → 看哪 → 狗 → 窗口跟着狗挪。until 说停就停，返回过了多久；没停过 None。"""
        w = win or self.win
        pg = w.playground
        for i in range(int(seconds / DT)):
            pg._frames_at = -math.inf if i % 15 == 0 else pg._frames_at
            pg.update(DT)
            w.dog.set_look_target(w._look_target(DT))
            w.dog.update(DT)
            w._pose = w.dog.frame()
            pg.after_pose()
            if pg.roam.moved:
                w.place_scene(pg.roam.wx, pg.roam.wy)
            if until is not None and until():
                return (i + 1) * DT
        return None

    # ---------- 球 ----------
    def ring_point(self):
        """捡球的圈里的一个点（全局坐标）：狗脸前面一点、身子那么高。"""
        roam, ppm = self.pg.roam, self.win.ppm
        return roam.wx + roam.facing * 0.3 * ppm, roam.wy - 0.55 * ppm

    def pick_up_ball(self, at=None):
        """按住球、拖到 at（不给就是圈里）：这一拖就是拿起。"""
        from PySide6.QtCore import QPointF
        import time as _t
        pg, b = self.pg, self.pg.ball
        at = at or self.ring_point()
        pg.ball_press(QPointF(b.x, b.y))
        moved = _t.perf_counter() - 1.0                          # 这一拖算在一秒前：推帧比真时间快，不然松手时这一拖还在手速的那 80 毫秒里
        pg.ball_drag(QPointF(*at), moved)
        pg.ball_drag(QPointF(*at), moved)
        self.assertTrue(pg.ball_held, "拖了算拿起")
        return at

    def put_ball_down(self):
        """手不动松开：球原地掉下去。"""
        from PySide6.QtCore import QPointF
        self.pg.ball_release(QPointF(*self.pg._pointer))

    def throw_and_fetch(self, vx, vy=-300.0):
        """球按这个速度飞出去（像素 / 秒），狗去捡。"""
        pg = self.pg
        pg.ball.throw(vx, vy, self.win.ppm)
        pg.throw_id += 1
        pg.roam.fetch()

    def run_throws(self, win, plan, limit: float = 20.0) -> list[dict]:
        """一组随机扔（throws()）挨个来：狗站好、球出手、狗去追，推到叼到（或够不着叫完）为止，再推到放下。每次记：用了多久（没做完 None）、
        叼没叼到、走过的阶段、跑了多远（米）、最快多快（米 / 秒）、朝向换了几次、球还在动就叫了没有、放下后球离鼠标多远（米）。"""
        pg, roam, dog, ppm = win.playground, win.playground.roam, win.dog, win.ppm
        floor_y = self.ag.y() + self.ag.height() - 18.0 * win.scale
        left, right = self.ag.x(), self.ag.x() + self.ag.width()
        rows = []
        for fx, off, up, vxm, vym in plan:
            x = left + fx * self.ag.width()
            roam.cancel(drop_ball=True)
            win.place_scene(x, floor_y)
            roam.place(x, floor_y)
            roam.drop_to_support()
            self.step(0.3, win=win)
            b = pg.ball
            pg.carried = False
            b.x, b.y = min(max(x + off * ppm, left + 20.0), right - 20.0), floor_y - up * ppm
            b.vx = b.vy = 0.0
            b.resting = b.rolling = False
            b.on = None
            self.cursor = (min(max(x + 60.0, left + 60.0), right - 60.0), floor_y - 150.0)   # 鼠标在狗旁边（放球的地方）
            b.throw(vxm * ppm, vym * ppm, ppm)
            pg.throw_id += 1
            roam.fetch()
            row = {"phases": [], "flips": 0, "dist_m": 0.0, "top": 0.0, "bark_moving": False}
            last = {"facing": roam.facing, "x": roam.wx}

            def watch():
                if roam.facing != last["facing"]:
                    last["facing"] = roam.facing
                    row["flips"] += 1
                if roam.phase and (not row["phases"] or row["phases"][-1] != roam.phase):
                    row["phases"].append(roam.phase)
                if dog.player.name == "Bark" and not b.resting:
                    row["bark_moving"] = True
                row["dist_m"] += abs(roam.wx - last["x"]) / ppm
                last["x"] = roam.wx
                row["top"] = max(row["top"], abs(roam.v) / ppm)
                return roam.carrying or roam.task is None
            row["took"] = self.step(limit, watch, win=win)
            row["got"] = roam.carrying
            row["put"] = self.step(25.0, lambda: roam.task is None, win=win) if row["got"] else None
            row["ball_to_cursor"] = abs(b.x - self.cursor[0]) / ppm if row["put"] else None
            rows.append(row)
        return rows

    def add_window(self, number, x, top_y, w, h=200.0):
        """加一个假的别的 App 的窗口，返回它的上沿那条线（站不下狗的没有：None）。"""
        pg = self.pg
        self.frames[number] = (x, top_y, w, h)
        pg._sups = None
        pg._frames_at = -math.inf
        return next((s for s in pg.supports() if s.key == number and s.kind == "window"), None)

    def climb_window(self, top_y, x=380.0, w=360.0, at=None):
        """加一个窗口，让狗跳上去（落在 at，不给就是正中）。"""
        roam = self.pg.roam
        s = self.add_window(7, x, top_y, w)
        self.assertTrue(roam.go_to(s, x + w / 2 if at is None else at))
        self.assertIsNotNone(self.step(12.0, lambda: roam.task is None), "跳上去了")
        self.assertEqual((roam.support.kind, roam.support.key), ("window", 7))
        return s
