"""在真机上（cocoa、真窗口、真屏幕）把灵动交互按剧本跑一遍，记日志、存截图，给开发验证用；不进 app 包。

用法：.venv.nosync/bin/python tools/selftest_playground.py OUT_DIR [--pack samoyed] [--only swap|rise|swapcard|things]
- --pack：用哪个模型包的那只跑（不写是默认那只）；--only swap：放好以后直接跳到「换模型」那一步（只看换模型时用，少在屏幕上折腾）；
  --only rise：只跑「起身」那一段（s10r_rise，要自己会趴下的狗：--pack samoyed），每帧一行记到 OUT_DIR/rise.jsonl；
  --only swapcard：只跑「卡片开着从滑动条换模型」（s10q_swapcard，两个模型都在才跑），每帧一行记到 OUT_DIR/swapcard.jsonl；
  --only things：放好以后直接从「物件」那一步跑到底（摆窝和盆、读回前后、回窝、吃喝、台子、换模型）；
- 设置存在 OUT_DIR/settings.ini（不碰真的 QSettings）；不动鼠标、不点别的 App，"鼠标在哪"用剧本里定的点代替；
- 剧本：放在主屏地面右边 → 扔球（狗叼到"鼠标"旁边放下、待在那）→ 有摆在主屏正上方的屏就往上扔球
  （飞进上面那块屏再掉回来）、把狗放到上面那块屏的半空（穿过菜单栏掉回主屏：看换屏那一下）→ 开一个测试窗口（另一个进程）→
  叫它跳上去（roam.go_to）→ 窗口挪走（狗跟着）→ 空地够：叫它跳下来（往前蹬）→ 再开一个左右空地都紧的测试窗口，放上去，
  叫它跳下来（走到边上直接落）→ 再开一个紧贴屏幕顶的测试窗口，把狗放上去（「···」挪到旁边、层级在菜单栏上面）
  → SELFTEST_MISSION=1 时扔一个球、打开调度中心 2.5 秒再关（看狗和球藏没藏、动画停没停）
  → 拿着球进圈（圈满、叫一声、俯身；读回圈的窗口的层级、点不点得到）→ 拎起来、扔出去 → 拖过屏幕交界（有第二块屏时）→ 跑过屏幕交界
  → 开发者设置页和提示的截图 → 摆一个狗窝、一个盆（买来的物件模型在才有这一步：读回窗口的层级、点不点得穿、在不在屏里，假拿起、挪、松手，存 things-*.png；
    起窝一落定闲着的狗就走过去趴进去：读回 placed_task / nest_going；盆这时落定狗已经上路了，不来，留着给「吃」那一步敲）
  → 回窝（狗这时多半已经在窝里了，钟照旧拨到该回窝的时候：读回 dog.perch、前沿那一层的窗口在不在、层级、点不点得穿，存 …-nest-dog.png、nest-front.png；
    再假拿起球，读回起来没有——起来了还站在垫子上，perch、前沿照留）
  → 吃（假点一下饭盆：狗过去吃，吃到一半存 …-eat-dog.png、读回鼻子离盆心多远；吃完读回盆变空没有、换成空盆的图没有，存 eat-bowl-empty.png）
  → 台子（摆一个平顶狗屋、挪到屏幕中间：读回它的假窗口框，叫狗跳上屋顶（roam.go_to），存 …-roof-dog.png、roof.png；再假拿起狗屋，读回狗掉下来没有。
    这一步改完没在真机上跑过）
  → 换模型（两个模型都在才跑；不重启）：后台先备另一个模型（读回备了多久、这期间最长的帧间隔）→ 狗闲着时添一只另一个模型的、当场换过去
    （读回进程号没变、换的那一下主线程多久、从换到狗淡回来多久、这期间最长的帧间隔，存 swap-before / swap-after）→ 叼着球的时候换回去（读回球在哪、
    球的窗口看不看得见）→ 歇在窝里的时候换（读回 dog.perch、踩没踩着垫子、前沿的窗口、狗窝的窗口大小变了没有，存 swap-nest-*）→ 换完再扔一次球
    （照常叼回来）→ 来回换 10 次，头尾各记一次 footprint 里显卡那几类，看涨不涨。设置照旧在 OUT_DIR/settings.ini。
  → 退出。声音全程关着，只查声音文件载不载得进来。
  剧本里的扔球都是真拿起来（playground._pick_up）再松手；进圈才追，所以除了「拿着球进圈」那一步，别的扔之前都当作圈已经满了。
  OUT_DIR/cross.jsonl：拖、跑过交界时每帧一行：主窗口和另一个窗口在哪、在哪块屏、狗身子有没有哪一截没窗口画。
- OUT_DIR/log.jsonl 每 50 毫秒一行：剧本到哪、狗在哪、窗口在哪块屏、像素密度、这 50 毫秒里画了几帧、看不看得见、球在哪、圈多满多浓；
  每 50 毫秒还看一眼程序有没有被切到前台、有没有接键盘的窗口（不抢别的 App 的焦点），退出前记一行 focus 汇总；
  OUT_DIR/*.png 关键时刻的狗、球和圈；OUT_DIR/jump.jsonl 跳的时候每帧一行：阶段、片段、根、后脚、骨盆（看后脚在不在平面上、身子跳没跳）。"""
from __future__ import annotations

import ctypes
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt, QTimer   # noqa: E402
from PySide6.QtGui import QGuiApplication, QMouseEvent    # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

import config                                                          # noqa: E402
from widget.world import support_below
from widget.render import ELEVATION                                    # noqa: E402

ARGS = sys.argv[1:]
PACK = None                                                            # --pack <模型包>：用那一只跑；不写是默认那只
if "--pack" in ARGS:
    at = ARGS.index("--pack")
    PACK = ARGS[at + 1]
    del ARGS[at:at + 2]
ONLY = None                                                            # --only swap：放好以后直接跳到「换模型」那一步
if "--only" in ARGS:
    at = ARGS.index("--only")
    ONLY = ARGS[at + 1]
    del ARGS[at:at + 2]
OUT = Path(ARGS[0] if ARGS else "/tmp/deskmate-selftest").resolve()
OUT.mkdir(parents=True, exist_ok=True)

PLATFORM_SCRIPT = r'''
import sys, time
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QLabel
app = QApplication(sys.argv)
x, y, w, h, move_at, close_at, mx, my = [float(v) for v in sys.argv[1:9]]
win = QLabel("Deskmate self-test platform")
win.setAlignment(Qt.AlignCenter)
win.setWindowTitle("Deskmate self-test platform")
win.setGeometry(int(x), int(y), int(w), int(h))
win.show()
win.raise_()
if move_at > 0:
    QTimer.singleShot(int(move_at * 1000), lambda: win.move(int(mx), int(my)))
QTimer.singleShot(int(close_at * 1000), app.quit)
app.exec()
'''


def main() -> int:
    import widget.window as window_mod
    ini = OUT / "settings.ini"
    if ini.exists():
        ini.unlink()
    window_mod.QSettings = lambda *a: QSettings(str(ini), QSettings.IniFormat)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    from widget import gltf, native, uninstall

    def no_uninstall(*_args, **_kw):
        raise AssertionError("自测绝不能启动真的卸载器：从源码跑到它会清真用户的设置、日志、缓存")
    uninstall.start = no_uninstall
    from widget.settings import SettingsPanel
    if PACK:
        from widget import packs
        pack = packs.discover()[PACK]
        win = window_mod.CompanionWindow(packs.load_model(pack), pack=pack)
    else:
        model = gltf.load(config.MODEL_PATH)
        win = window_mod.CompanionWindow(model)
    win.attach_panels(SettingsPanel(win))
    win.prefs.set("language", "zh")
    win.set_interface_sounds(False)                        # 自测不出声（查声音文件的在最后）
    win.set_pack_sounds(False)
    pg = win.playground
    screens = [(s.name(), s.geometry(), s.availableGeometry()) for s in QGuiApplication.screens()]
    primary_screen = QGuiApplication.primaryScreen()
    primary = primary_screen.availableGeometry()
    pgeo = primary_screen.geometry()
    above = next((s for s in QGuiApplication.screens() if s is not primary_screen and abs(s.geometry().bottom() + 1 - pgeo.top()) <= 2
                  and s.geometry().right() > pgeo.left() and s.geometry().left() < pgeo.right()), None)
    log = open(OUT / "log.jsonl", "w")
    jump_log = open(OUT / "jump.jsonl", "w")
    cross_log = open(OUT / "cross.jsonl", "w")
    state = {"step": "start", "t0": time.perf_counter(), "last": time.perf_counter(), "platforms": [], "shots": 0, "ticks": 0,
             "cursor": (primary.x() + primary.width() * 0.35, primary.y() + primary.height() - 220.0)}
    pg.cursor = lambda: state["cursor"]                    # 不读真鼠标：剧本里定"鼠标在哪"

    real_tick = win._tick
    real_paint = win.view.render
    state["paints"] = 0
    ce = math.cos(math.radians(ELEVATION))

    def body_gap() -> int:
        """狗身子的矩形里，有多少像素宽在某块屏上但那块屏上没有窗口画（主窗口 + 另一块屏上的窗口）：0 才是没断开。"""
        wx, wy = win.scene_world()
        body = win._body_rect(wx, wy)
        rects = [win.frameGeometry()]
        rects.extend(g.frameGeometry() for g in win._ghosts.values() if g.drawing)
        worst = 0
        for s in QGuiApplication.screens():
            part = body.intersected(s.geometry())
            if part.isEmpty():
                continue
            cover = max((part.intersected(r).width() for r in rects if s.geometry().intersects(r)), default=0)
            worst = max(worst, part.width() - cover)
        return worst

    # ---- 有没有"在远处闪一下"：每个窗口上一次真正画出来的狗，按它现在的位置摆，离狗真实的地方有多远 ----
    flash_log = open(OUT / "flash.jsonl", "w")
    flash_stats = {}
    state["flash_stats"] = flash_stats
    painted = {}
    last_root = {"xy": None, "jump_at": -1.0}

    def watch_view(name, w):
        def swapped():
            f = w.view.frame
            painted[name] = (time.perf_counter(), None if f is None else (w.width() / 2.0 + f.offset[0], w.height() - f.ground_px + f.offset[1]))
        w.view.frameSubmitted.connect(swapped)

    watch_view("main", win)
    watched = set()

    def flash_check():
        now = time.perf_counter()
        for name, g in win._ghosts.items():
            if name not in watched:
                watched.add(name)
                watch_view(name, g)
        wx, wy = win.scene_world()
        prev = last_root["xy"]
        if prev is not None and math.hypot(wx - prev[0], wy - prev[1]) > 0.8 * win.ppm:
            last_root["jump_at"] = now                         # 一帧挪这么远：脚本瞬移的
        last_root["xy"] = (wx, wy)
        half = 0.5 * win.ppm
        for name, w in [("main", win)] + list(win._ghosts.items()):
            p = painted.get(name)
            if p is None or p[1] is None:
                continue
            lx, ly = p[1]
            if not (-half < lx < w.width() + half and 0 < ly < w.height() + 0.9 * win.ppm):
                continue                                       # 画的那一帧狗不在这个窗口的画布里：看不见
            sx, sy = w.x() + lx, w.y() + ly
            off = math.hypot(sx - wx, sy - wy)
            key = state["step"] + "/" + name
            flash_stats[key] = max(flash_stats.get(key, 0.0), round(off, 1))
            flash_stats["checks"] = flash_stats.get("checks", 0) + 1
            if off > 0.35 * win.ppm:
                flash_log.write(json.dumps({"t": round(now - state["t0"], 3), "step": state["step"], "who": name, "off": round(off), "shown": [round(sx), round(sy)], "true": [round(wx), round(wy)],
                                            "age_ms": round((now - p[0]) * 1000), "win": [w.x(), w.y(), w.width(), w.height()], "after_jump_ms": round((now - last_root["jump_at"]) * 1000),
                                            "busy": win._scene_busy(), "scene": win._scene_screen.name() if win._scene_screen else None, "drawing": getattr(w, "drawing", True)}, ensure_ascii=False) + "\n")
                flash_log.flush()

    def counted_tick():
        state["ticks"] += 1
        t0 = time.perf_counter()
        real_tick()
        state["tick_ms"] = (time.perf_counter() - t0) * 1000
        if state.get("frames") is not None:                # 换模型那几步：每帧记时刻和狗几成浓（帧间隔、多久淡回来）
            state["frames"].append((time.perf_counter(), win.dog_opacity))
        flash_check()
        if state.get("rise_on"):
            state["rise_row"]()
        if state.get("swapcard_on"):
            state["swapcard_row"]()
        if state.get("cross"):
            g = next((g for g in win._ghosts.values() if g.drawing), None)
            cross_log.write(json.dumps({"t": round(time.perf_counter() - state["t0"], 3), "step": state["step"], "root": [round(v, 1) for v in win.scene_world()],
                                        "win": [win.x(), win.y(), win.width(), win.height()], "scene_screen": win._scene_screen.name() if win._scene_screen else None,
                                        "real_screen": win.screen().name() if win.screen() else None,
                                        "ghost": None if g is None else [g.x(), g.y(), g.width(), g.height(), g.screen().name() if g.screen() else None],
                                        "gap": body_gap(), "swaps": win._ghost_swaps}, ensure_ascii=False) + "\n")
        roam, dog = pg.roam, win.dog
        leg = roam.leg or {}
        if leg.get("kind") in ("jump", "fall") and dog._last is not None and leg.get("stage") != "face":
            _, g = dog._last
            hh = sum(g[i][13] for i in dog._hind_feet) / len(dog._hind_feet)
            hz = sum(g[i][14] for i in dog._hind_feet) / len(dog._hind_feet)
            pel = g[dog._pelvis]
            d = roam.facing
            jump_log.write(json.dumps({"t": round(time.perf_counter() - state["t0"], 3), "step": state["step"], "stage": leg.get("stage"),
                                       "mode": leg.get("jump"), "clip": dog.player.name, "u": round(dog.player.progress, 3), "plane": leg.get("plane"),
                                       "win": [round(v, 1) for v in win.scene_world()], "root": [round(roam.wx, 1), round(roam.wy, 1)],
                                       "hind": [round(roam.wx + d * hz * roam.ppm, 1), round(roam.wy - (hh - dog.planted_hind) * ce * roam.ppm, 1)],
                                       "pelvis": [round(roam.wx + d * pel[14] * roam.ppm, 1), round(roam.wy - pel[13] * ce * roam.ppm, 1)]}) + "\n")
    win._tick = counted_tick

    def counted_paint(cb):
        state["paints"] += 1
        state["rise_paints"] = state.get("rise_paints", 0) + 1
        t0 = time.perf_counter()
        real_paint(cb)
        state["paint_ms"] = state.get("paint_ms", 0.0) + (time.perf_counter() - t0) * 1000
    win.view.render = counted_paint

    def screen_switched(screen):
        if log.closed:
            return
        log.write(json.dumps({"screen_switch": round(time.perf_counter() - state["t0"], 3), "to": screen.name() if screen else None,
                              "dpr": screen.devicePixelRatio() if screen else None, "win": [win.x(), win.y()]}, ensure_ascii=False) + "\n")

    def floor_y(g):
        return g.y() + g.height() - 18.0 * win.scale

    def record():
        now = time.perf_counter()
        dt = now - state["last"]
        state["last"] = now
        roam, b = pg.roam, pg.ball
        row = {"t": round(now - state["t0"], 3), "step": state["step"], "dt_ms": round(dt * 1000, 1), "ticks": state["ticks"],
               "occluded": native.window_occluded(win), "fps": round(win.view.fps, 1), "task": roam.task, "phase": roam.phase,
               "leg": (roam.leg or {}).get("kind"), "stage": (roam.leg or {}).get("stage"), "jump": (roam.leg or {}).get("jump"),
               "dog": [round(v, 1) for v in win.scene_world()], "dog_screen": win.screen().name() if win.screen() else None,
               "dpr": win.devicePixelRatioF(), "win": [win.x(), win.y(), win.width(), win.height()],
               "support": None if roam.support is None else [roam.support.kind, roam.support.key, round(roam.support.y, 1)],
               "clip": win.dog.player.name, "yaw": round(win.dog.yaw, 1), "side_menu": win.hover.side,
               "ball": None if b is None else [round(b.x, 1), round(b.y, 1), b.resting, pg.carried, pg.ball_held],
               "ball_win": None if pg.ball_win is None else [pg.ball_win.x(), pg.ball_win.y(), pg.ball_win.isVisible(),
                                                              pg.ball_win.screen().name() if pg.ball_win.screen() else None],
               "ring": [round(pg.ring.progress, 3), round(pg.ring.alpha, 3), pg.ring.ready,
                        [name for name, rw in pg.ring_wins.items() if rw.isVisible()]]}
        row["paints"] = state["paints"]
        state["ticks"] = state["paints"] = 0
        focus = state.setdefault("focus", {"samples": 0, "app_active": 0, "key_window": 0, "reactivated": 0, "where": [], "was": None, "left": False})
        focus["samples"] += 1                                  # 不抢别的 App 的焦点。从终端起的程序刚启动时本来在前台，切走以后又被切回来（reactivated）才算抢
        active, key = bool(native.app_active()), QApplication.activeWindow()
        focus["app_active"] += active
        if key is not None:
            focus["key_window"] += 1
        if not active:
            focus["left"] = True
        elif focus["left"] and focus["was"] is False:
            focus["reactivated"] += 1
            if len(focus["where"]) < 8:
                focus["where"].append(state["step"])
        focus["was"] = active
        log.write(json.dumps(row, ensure_ascii=False) + "\n")

    def note(**kw):
        log.write(json.dumps({"note": state["step"], **kw}, ensure_ascii=False) + "\n")

    def stack():
        """我们几个窗口的前后（系统窗口表的次序，从前到后，「名字@层」）：狗、球、窝的前沿、每件物件。"""
        mine = {native.window_number(win): "dog"}
        if pg.ball_win is not None and pg.ball_win.isVisible():
            mine[native.window_number(pg.ball_win)] = "ball"
        for t in pg.things.items.values():
            if t.win.isVisible():
                mine[native.window_number(t.win)] = t.key
            if t.front_win is not None and t.front_win.isVisible():
                mine[native.window_number(t.front_win)] = t.key + ":front"
        return [f"{mine[row[0]]}@{row[2]}" for row in native._window_info(1, 0) if row[0] in mine]   # kCGWindowListOptionOnScreenOnly：从前到后

    def shuffle():
        """照系统自己重排那样（点一下把被点的窗口提到最前、切桌面时重排）：按该有的前后反过来，一个个 orderFront（和点一下一样）——
        层越高的越先提，最后提的是最后面那层的。分了层以后读回来的前后不该变（同一层里这样一提，窝就盖住了盆、狗和窝沿）。"""
        wins = [win] + [t.win for t in pg.things.items.values() if t.win.isVisible()]
        wins += [t.front_win for t in pg.things.items.values() if t.front_win is not None and t.front_win.isVisible()]
        if pg.ball_win is not None and pg.ball_win.isVisible():
            wins.append(pg.ball_win)
        for w in sorted(wins, key=lambda w: native.window_level(w) or 0, reverse=True):
            native._msg_send(native._msg_send(int(w.winId()), "window"), "orderFront:", None, argtypes=(ctypes.c_void_p,), restype=None)

    def shot(name):
        state["shots"] += 1
        win.grab().save(str(OUT / f"{state['shots']:02d}-{name}-dog.png"))      # 狗的画布 + 上面那层「···」
        if pg.ball_win is not None and pg.ball_win.isVisible():
            pg.ball_win.grab().save(str(OUT / f"{state['shots']:02d}-{name}-ball.png"))
        for k, rw in enumerate(rw for rw in pg.ring_wins.values() if rw.isVisible()):   # 圈的窗口（每块屏一截；grab 不带窗口的不透明度）
            rw.grab().save(str(OUT / f"{state['shots']:02d}-{name}-ring{k}.png"))

    def throw(vx, vy):
        """真拿起来（和按住球拖了一下一样，狗站好看着）再按 (vx, vy) 扔出去。进圈才追：这里当作圈已经满了，等圈本身是 s10c_bow 那一步。"""
        b = pg.ball
        t = time.perf_counter()
        pg._pick_up(QPointF(b.x, b.y), t - 0.06)
        pg.ring.ready = True
        pg.grab.clear()
        pg.grab.extend([(t - 0.06, b.x - vx * 0.06, b.y - vy * 0.06), (t, b.x, b.y)])
        pg.ball_release(QPointF(b.x, b.y))

    def wait_done(next_step, timeout, shot_name=None, cond=None):
        start = time.perf_counter()

        def check():
            done = (cond() if cond else (not pg.roam.busy and not pg.carried))
            if done or time.perf_counter() - start > timeout:
                if not done:
                    note(timeout=True)
                if shot_name:
                    shot(shot_name)
                next_step()
            else:
                QTimer.singleShot(100, check)
        QTimer.singleShot(300, check)

    def platform(x, y, w, h, move_at, close_at, mx, my):
        p = subprocess.Popen([sys.executable, "-c", PLATFORM_SCRIPT] + [str(v) for v in (x, y, w, h, move_at, close_at, mx, my)])
        state["platforms"].append(p)
        return p

    def when_listed(p, then, waited=0.0):
        """测试窗口出来了（Python 起得慢、台前调度在摆）再接着走。"""
        if any(f[1] == p.pid for f in native.window_frames(os.getpid())) or waited > 15:
            QTimer.singleShot(600, then)
        else:
            QTimer.singleShot(250, lambda: when_listed(p, then, waited + 0.25))

    # ---- 剧本 ----
    def s1_place():
        state["step"] = "place"
        win.place_scene(primary.x() + primary.width() * 0.7, floor_y(primary))
        win._after_move()                                  # 停稳：记位置、朝向、家（playground.window_settled）
        win.dog.snap_home(win._home_yaw())
        if not win.dynamic:
            win.set_dynamic(True)
        elif not pg.active:
            pg.start()
        QTimer.singleShot(2500, s10o_swap if ONLY == "swap" else (lambda: s10r_rise(s11_quit)) if ONLY == "rise"
                          else (lambda: s10q_swapcard(s11_quit)) if ONLY == "swapcard" else s10k_things if ONLY == "things" else s2_throw)

    def s2_throw():
        state["step"] = "throw-deliver"
        shot("ready")
        throw(-1600.0 * win.scale, -900.0 * win.scale)
        QTimer.singleShot(900, lambda: shot("running"))

        def done():
            note(ball=[round(pg.ball.x, 1), round(pg.ball.y, 1)], cursor=state["cursor"], dog=[round(v, 1) for v in win.scene_world()])
            s3_stacked()
        wait_done(done, 40, "delivered")

    def s3_stacked():
        if above is None:
            note(skipped="no screen above the primary one")
            s5_platform()
            return
        state["step"] = "stacked-ball"
        g = above.geometry()
        x = max(g.left(), pgeo.left()) + min(g.right(), pgeo.right())
        b = pg.ball
        b.x, b.y = x / 2, floor_y(primary) - b.r
        b.resting, b.on = True, ("floor", 0)
        state["top_y"] = b.y
        throw(0.0, -40.0 * win.ppm)

        def watch():
            state["top_y"] = min(state["top_y"], pg.ball.y)
            if pg.roam.busy or pg.carried or not pg.ball.resting:
                QTimer.singleShot(50, watch)
            else:
                note(ball_highest_y=round(state["top_y"], 1), upper_screen_bottom=g.bottom() + 1)
                s4_drop_from_above()
        QTimer.singleShot(100, watch)

    def s4_drop_from_above():
        state["step"] = "drop-from-above"
        g = above.geometry()
        win.place_scene((max(g.left(), pgeo.left()) + min(g.right(), pgeo.right())) / 2, g.top() + g.height() * 0.6)
        pg.dog_dropped()
        wait_done(s5_platform, 10, "landed-from-above")

    def s5_platform():
        state["step"] = "platform"
        win.place_scene(primary.x() + primary.width() * 0.6, floor_y(primary))
        win._after_move()
        x0 = win.scene_world()[0]
        top = floor_y(primary) - 1.8 * win.ppm                                  # 1.8 米：跳得上去，跳下来是头朝下扑
        p = platform(x0 - 300, top, 620, 280, 4.0, 30.0, x0 - 700, top - 60)
        when_listed(p, s6_climb)

    def pull_to(x, y):
        """叫狗跑、跳到 (x, y) 下面那条线上。"""
        target = support_below(pg.supports(), x, y) or pg.world.nearest_floor(x, y)
        return pg.roam.go_to(target, target.clamp(x, pg.roam.margin(target)))

    def s6_climb():
        state["step"] = "climb"
        pg._frames_at = -math.inf
        pg.supports()
        frame = next(f for f in pg.frames if f.pid == state["platforms"][-1].pid)
        started = pull_to(frame.x + frame.w / 2, frame.y - 30)
        note(climb_started=started and pg.roam.task == "go", frames=[[f.number, f.x, f.y, f.w, f.h] for f in pg.frames])
        wait_done(s7_ride, 12, "on-window")

    def s7_ride():
        state["step"] = "riding"
        QTimer.singleShot(5000, lambda: (shot("riding"), s8_push()))

    def s8_push():
        state["step"] = "jump-down-push"
        started = pull_to(primary.x() + primary.width() * 0.1, floor_y(primary) - 50)
        note(started=started, task=pg.roam.task, route=[[l.kind, l.mode] for l in pg.roam.route])
        wait_done(s8b_tight, 10, "pushed-down")

    def s8b_tight():
        """左右空地都紧的窗口：放上去，叫它下来，走到边上直接落。"""
        state["step"] = "tight-window"
        room = 1.2 * win.ppm
        top = floor_y(primary) - 1.8 * win.ppm
        p = platform(primary.x() + room, top, primary.width() - 2 * room, 280, 0, 18.0, 0, 0)

        def put_on():
            frame = next((f for f in native.window_frames(os.getpid()) if f[1] == p.pid), None)
            note(tight_frame=None if frame is None else list(frame[2:]))
            y = frame[3] if frame is not None else top
            win.place_scene(primary.x() + primary.width() * 0.4, y)
            pg._frames_at = -math.inf
            pg.dog_dropped()
            QTimer.singleShot(1500, go_down)

        def go_down():
            state["step"] = "jump-down-edge"
            started = pull_to(primary.x() + 40, floor_y(primary) - 50)
            note(started=started, task=pg.roam.task, on=None if pg.roam.support is None else pg.roam.support.kind,
                 route=[[l.kind, l.mode] for l in pg.roam.route])
            wait_done(s9_top, 10, "edge-dropped")
        when_listed(p, put_on)

    def s9_top():
        state["step"] = "top-of-screen"
        top = pgeo.top() + 0.88 * win.ppm + 30                                  # 内容区的顶；标题栏在它上面，窗口上沿离屏幕顶 0.88 米左右：狗刚好站得下
        x = primary.x() + primary.width() * 0.45
        p = platform(x - 320, top, 640, 260, 0, 12.0, 0, 0)

        def put_on():
            frame = next((f for f in native.window_frames(os.getpid()) if f[1] == p.pid), None)
            y = frame[3] if frame is not None else top
            note(platform_frame=None if frame is None else list(frame[2:]), screen_top=pgeo.top())
            win.place_scene(x, y)
            pg._frames_at = -math.inf
            pg.dog_dropped()

            def check():
                note(on=None if pg.roam.support is None else [pg.roam.support.kind, round(pg.roam.support.y, 1)],
                     side_menu=win.hover.side, level=native.window_level(win), ball_level=native.window_level(pg.ball_win))
                shot("top-of-screen")
                QTimer.singleShot(500, s10_mission if os.environ.get("SELFTEST_MISSION") == "1" else s10c_bow)
            win.hover.set_hover(True)
            QTimer.singleShot(1800, check)
        when_listed(p, put_on)

    def s10_mission():
        state["step"] = "mission-control"
        win.hover.set_hover(False)
        win.place_scene(primary.x() + primary.width() * 0.6, floor_y(primary))
        pg.dog_dropped()

        def go():
            throw(-1400.0 * win.scale, -1400.0 * win.scale)
            QTimer.singleShot(150, lambda: subprocess.run(["open", "-b", "com.apple.exposelauncher"]))
            QTimer.singleShot(2800, lambda: subprocess.run(["open", "-b", "com.apple.exposelauncher"]))
            wait_done(s10c_bow, 40, "after-mission-control")    # 等它捡回来（球可能飞到别的屏：看换屏那一下）
        QTimer.singleShot(2500, go)

    def mouse(kind, gx, gy):
        """假的鼠标事件，直接给狗的窗口（不动真鼠标）。"""
        types = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove, "release": QEvent.MouseButtonRelease}
        g = QPointF(gx, gy)
        local = QPointF(win.mapFromGlobal(g))
        button = Qt.NoButton if kind == "move" else Qt.LeftButton
        buttons = Qt.NoButton if kind == "release" else Qt.LeftButton
        ev = QMouseEvent(types[kind], local, g, button, buttons, Qt.NoModifier)
        {"press": win.mousePressEvent, "move": win.mouseMoveEvent, "release": win.mouseReleaseEvent}[kind](ev)

    def s10c_bow():
        """拿着球进圈（进圈才追）：圈出来、涨满（调参 ring_hold_s，默认 1 秒），叫一声，俯身，一直等着；松手冲出去。
        读回圈的窗口的层级（该是 native.LEVEL_RING，在狗那层后面）、点不点得到（该是点不到）。"""
        state["step"] = "bow"
        win.place_scene(primary.x() + primary.width() * 0.7, floor_y(primary))
        win._after_move()
        b = pg.ball
        pg.ball_press(QPointF(b.x, b.y))
        pg.ball_drag(QPointF(pg.roam.wx - 0.35 * win.ppm, pg.roam.wy - 0.55 * win.ppm))   # 按住拖进圈里（这一拖就是拿起）
        note(held=pg.ball_held, task=pg.roam.task, phase=pg.roam.phase)

        def ring_check():
            shown = [rw for rw in pg.ring_wins.values() if rw.isVisible()]
            note(ring=round(pg.ring.progress, 2), ring_alpha=round(pg.ring.alpha, 2), phase=pg.roam.phase,
                 ring_windows=[[rw.x(), rw.y(), rw.width(), rw.height()] for rw in shown],
                 ring_levels=[native.window_level(rw) for rw in shown], ring_ignores=[native.ignores_mouse(rw) for rw in shown],
                 dog_level=native.window_level(win))
            shot("ring")
        QTimer.singleShot(350, ring_check)
        QTimer.singleShot(1200, lambda: (note(phase=pg.roam.phase, clip=win.dog.player.name, ready=pg.ring.ready), shot("ring-full")))
        QTimer.singleShot(2400, lambda: (note(phase=pg.roam.phase, clip=win.dog.player.name, shut=win.dog.shut_mouth,
                                              ring_alpha=round(pg.ring.alpha, 2)), shot("bow")))

        def beg():
            note(phase=pg.roam.phase, clip=win.dog.player.name, bowing=pg.roam.bowing)
            shot("bow-long")
            t = time.perf_counter()
            pg.grab.clear()
            pg.grab.extend([(t - 0.06, b.x + 1600.0 * win.scale * 0.06, b.y), (t, b.x, b.y)])
            pg.ball_release(QPointF(b.x, b.y))
            state["step"] = "after-bow"
            wait_done(s10d_lift, 40, "after-bow")
        QTimer.singleShot(5200, beg)

    def s10d_lift():
        """拎起来（假的鼠标事件）：悬空的样子；手甩着松手：扔出去。"""
        state["step"] = "lift"
        x0, y0 = primary.x() + primary.width() * 0.75, floor_y(primary)
        win.place_scene(x0, y0)
        win._after_move()
        gx, gy = x0, y0 - 0.5 * win.ppm
        mouse("press", gx, gy)
        path = [(0.0, -10.0 * k) for k in range(1, 31)]

        def lift_step(i=0):
            if i < len(path):
                mouse("move", gx + path[i][0], gy + path[i][1])
                QTimer.singleShot(16, lambda: lift_step(i + 1))
            else:
                QTimer.singleShot(700, hold)

        def hold():
            note(lift_w=round(win.dog.lift.w, 3), lifted=pg.roam.lifted, footprint=len(win.dog.frame().footprint))
            shot("lifted")
            fling(0)

        def fling(i):
            state["step"] = "fling"
            if i < 10:
                mouse("move", gx - 40.0 * i, gy - 300.0 - 10.0 * i)
                QTimer.singleShot(12, lambda: fling(i + 1))
            else:
                mouse("release", gx - 360.0, gy - 390.0)
                note(after_release=pg.roam.task, vx=(pg.roam.leg or {}).get("vx"), vy=(pg.roam.leg or {}).get("vy"), factor=round(win.tuning.throw_factor, 3))
                wait_done(s10e_drag_cross, 8, "flung")
        lift_step()

    def other_side():
        """主屏左右挨着的那块屏：(屏, 主屏靠它那条边的 x, 朝它的方向)。没有 None。"""
        for s in QGuiApplication.screens():
            if s is primary_screen:
                continue
            g = s.geometry()
            if abs(g.right() + 1 - pgeo.left()) <= 2:
                return s, pgeo.left(), -1.0
            if abs(g.left() - (pgeo.right() + 1)) <= 2:
                return s, pgeo.right() + 1, 1.0
        return None

    def s10e_drag_cross():
        """拖过屏幕交界（假的鼠标事件）：不闪、窗口不骑边、不来回换屏。"""
        side = other_side()
        if side is None:
            note(skipped="no screen beside the primary one")
            s10g_cards()
            return
        state["step"] = "drag-cross"
        state["cross"] = True
        screen, edge, d = side
        floor2 = floor_y(screen.availableGeometry())
        y = min(floor_y(primary), floor2) - 2.0 * win.ppm
        x0 = edge - d * 1.5 * win.ppm
        win.place_scene(x0, y)
        win._after_move()
        pg.roam.place(x0, y)
        gy = y - 0.5 * win.ppm
        mouse("press", x0, gy)
        steps = 90

        def go(i=0):
            if i <= steps:
                mouse("move", x0 + d * i * (3.0 * win.ppm) / steps, gy)
                QTimer.singleShot(20, lambda: go(i + 1))
            else:
                QTimer.singleShot(300, end)

        def end():
            note(drag_end_screen=win.screen().name(), scene=win._scene_screen.name() if win._scene_screen else None)
            mouse("release", x0 + d * 3.0 * win.ppm, gy)
            wait_done(s10f_run_cross, 8, "after-drag-cross")
        go()

    def s10f_run_cross():
        """狗自己跑过屏幕交界（两块屏的地面一样高才跑得过去；不一样高就跳）：不断开。"""
        state["step"] = "run-cross"
        side = other_side()
        screen, edge, d = side
        floors = pg.world.floors
        here = pg.roam.here()
        there = next((f for f in floors if f.key != here.key), None)
        if there is None:
            s10g_cards()
            return
        x = there.clamp(there.x0 + (there.x1 - there.x0) * 0.5)
        ok = pg.roam.go_to(there, x)
        note(start=here.key, goal=there.key, reachable=ok, route=[[l.kind, l.mode] for l in pg.roam.route])

        def back():
            state["step"] = "run-cross-back"
            home = next(f for f in pg.world.floors if f.key != pg.roam.here().key)
            ok2 = pg.roam.go_to(home, home.clamp(home.x0 + (home.x1 - home.x0) * 0.6))
            note(reachable=ok2)
            wait_done(s10g_cards, 25, "after-run-back")
        wait_done(back, 25, "after-run-cross")

    def s10g_cards():
        state["cross"] = False
        s10b_cards()

    def s10h_straddle():
        """狗正好跨在屏幕交界上（拖着不动）：截两块屏的图，看两半接不接得上（要录屏权限，没有就只是看不到狗）。"""
        side = other_side()
        if side is None:
            s11_quit()
            return
        state["step"] = "straddle"
        state["cross"] = True
        screen, edge, d = side
        floor2 = floor_y(screen.availableGeometry())
        y = min(floor_y(primary), floor2) - 1.2 * win.ppm
        x0 = edge - d * 1.5 * win.ppm
        win.place_scene(x0, y)
        win._after_move()
        pg.roam.place(x0, y)
        gy = y - 0.5 * win.ppm
        mouse("press", x0, gy)
        steps = 30

        def go(i=0):
            if i <= steps:
                mouse("move", x0 + d * i * (1.5 * win.ppm) / steps, gy)
                QTimer.singleShot(16, lambda: go(i + 1))
            else:
                QTimer.singleShot(1200, capture)

        def capture():
            r = subprocess.run(["screencapture", "-x", str(OUT / "straddle-1.png"), str(OUT / "straddle-2.png")], capture_output=True, text=True)
            note(capture=r.returncode, err=r.stderr[-200:], win=[win.x(), win.y(), win.width(), win.height()],
                 ghosts=[[g.x(), g.y(), g.width(), g.height(), g.drawing] for g in win._ghosts.values()],
                 root=[round(v, 1) for v in win.scene_world()])
            QTimer.singleShot(400, end)

        def end():
            mouse("release", edge, gy)
            state["cross"] = False
            wait_done(s10i_ghost_click, 6, "after-straddle")
        go()

    def s10i_ghost_click():
        """狗站在交界上：另一块屏上那半只也点得到吗（读那个窗口的像素、把按下松手转交给主窗口）。真鼠标点不了，这里直接给它送事件。"""
        side = other_side()
        screen, edge, d = side
        state["step"] = "ghost-click"
        y = floor_y(primary)
        win.place_scene(edge, y)
        pg.roam.place(edge, y)

        def check():
            ghost = next((g for g in win._ghosts.values() if g.drawing), None)
            if ghost is None:
                note(ghost_click="没有画着狗的第二个窗口")
                QTimer.singleShot(100, s10j_park)
                return
            wx, wy = win.scene_world()
            on = ghost.mapFromGlobal(QPoint(round(wx + d * 0.2 * win.ppm), round(wy - 0.45 * win.ppm)))
            off = ghost.mapFromGlobal(QPoint(round(wx + d * 0.95 * win.ppm), round(wy - 0.95 * win.ppm)))
            # probe 答的是上一帧、上一次问的那一点（widget/dogview.py）：先问，等几帧再拿答案。这几帧不让窗口自己按真鼠标的位置去问。
            real_hit, win._update_hit = win._update_hit, lambda now: None
            ghost.view.probe(on.x(), on.y(), 2.0)

            def asked_on():
                hit_on = ghost.view.probe(off.x(), off.y(), 2.0)
                QTimer.singleShot(70, lambda: asked_off(hit_on))

            def asked_off(hit_on):
                hit_off = ghost.view.probe(off.x(), off.y(), 2.0)
                win._update_hit = real_hit
                g = QPointF(ghost.mapToGlobal(on))
                ghost.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(on), g, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
                pressed = win._drag is not None
                ghost.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, QPointF(on), g, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))
                note(ghost_on_dog=hit_on, ghost_off_dog=hit_off, forwarded_press=pressed, released=win._drag is None,
                     ghost_screen=ghost.home.name(), main_screen=win._scene_screen.name() if win._scene_screen else None)
                QTimer.singleShot(300, s10j_park)
            QTimer.singleShot(70, asked_on)
        QTimer.singleShot(500, check)

    def s10j_park():
        """狗停在交界旁边那条带子里（估算的身子还碰着这块屏，真实的已经全过去了）：主窗口要跟过去，不能两边都点不到。"""
        side = other_side()
        screen, edge, d = side
        state["step"] = "park"
        y = floor_y(screen.availableGeometry())
        x = edge + d * (0.62 * win.ppm - 4.0)
        win._scene_screen = primary_screen
        win.place_scene(x, y)
        pg.roam.place(x, y)
        before = win._scene_screen.name()

        def check():
            note(parked_root=[round(v, 1) for v in win.scene_world()], before=before, main_screen=win._scene_screen.name(), real_screen=win.screen().name(),
                 main_rect=[win.x(), win.y(), win.width(), win.height()], drawing=[g.home.name() for g in win._ghosts.values() if g.drawing])
            s10k_things()
        QTimer.singleShot(800, check)

    def s10k_things():
        """物件：从设置里摆一个狗窝、一个盆（落下来）→ 读回每个窗口的层级（窝 native.LEVEL_THING[0]、盆 [1]、狗 LEVEL_DOG）、
        平时点不点得穿（真鼠标不在上面：该是点得穿）、在不在它那块屏里、图出好没有 → 假拿起狗窝、挪到半空、松手（直着落回地面）→ 每件的窗口存一张 things-*.png。
        前后（stack：窗口表从前到后的次序）摆好时、照系统那样反着提一遍以后（shuffle）、松手落定后各读一次：球在狗前面、狗在所有物件前面、盆在窝前面，
        提过以后不变。买来的模型不在就跳过。"""
        state["step"] = "things"
        keys = [k for k in ("bed/blue", "food_bowl/bowl") if any(t.key == k for t in win.things_available())]
        if not keys:
            note(things="no thing models here, skipped")
            s10o_swap()
            return
        win.place_scene(primary.x() + primary.width() * 0.5, floor_y(primary))
        win._after_move()
        for k in keys:
            win.set_thing(k, True)

        def rows():
            out = []
            for t in pg.things.items.values():
                g, screen = t.win.geometry(), t.win.screen()
                sg = screen.geometry() if screen is not None else None
                out.append({"key": t.key, "state": t.state, "on": t.on, "root": [round(t.x, 1), round(t.y, 1)],
                            "rect": [g.x(), g.y(), g.width(), g.height()], "screen": screen.name() if screen is not None else None,
                            "inside_screen": sg is not None and sg.contains(g), "level": native.window_level(t.win),
                            "ignores_mouse": native.ignores_mouse(t.win), "drawn": t.shot is not None, "alpha": round(t.alpha, 2),
                            "scale": t.geo[1] if t.geo else None, "yaw": t.geo[2] if t.geo else None})
            return out

        def lift():
            before = stack()
            shuffle()
            QTimer.singleShot(300, lambda: lift_after(before))

        def lift_after(before):
            after = stack()
            note(things=rows(), stack=before, shuffled=after, same_after_shuffle=before == after, dog_level=native.window_level(win),
                 ball_level=native.window_level(pg.ball_win), placed=win.things_placed(), quiet=pg.things.quiet(), placed_task=pg.roam.task,
                 nest_going=pg._nest_going.key if pg._nest_going is not None else None, nest=pg._nest.key if pg._nest is not None else None)   # 窝落定就过去：这时该在路上或者已经趴下
            t = pg.things.items[keys[0]]
            pg.things.thing_press(t, QPointF(t.x, t.y - 10.0))
            pg.things.thing_drag(t, QPointF(t.x + 260.0 * win.scale, t.y - 320.0 * win.scale))   # 这一拖就是拿起
            QTimer.singleShot(500, drop)

        def drop():
            t = pg.things.items[keys[0]]
            note(held=t.state, things=rows())
            pg.things.thing_release(t, QPointF(*t.pointer))
            QTimer.singleShot(1800, done)

        def done():
            note(things=rows(), stack=stack(), saved=win.settings.value("things", ""))
            for k, t in enumerate(pg.things.items.values()):
                t.win.grab().save(str(OUT / f"things-{k}-{t.key.replace('/', '-')}.png"))
            shot("things")
            s10l_nest()
        QTimer.singleShot(1800, lift)

    def s10l_nest():
        """回窝：狗窝摆着（上一步松手落定时狗多半已经走过来了；钟照旧拨到该回窝的时候，没来的这时也来）→ 狗在窝里趴下
        → 读回 dog.perch（该等于垫子的高度）、影子收没收、前沿那一层的窗口在不在、层级（前沿 LEVEL_RIM[0]，狗换到 LEVEL_DOG_IN[0]）、点不点得穿（该一直点得穿）、
        图出好没有、和物件的窗口是不是同一处；前后（stack）读一次，照系统那样反着提一遍（shuffle，点趴着的狗就是这样）再读一次：窝沿在狗前面、盆在窝沿前面，提过不变
        → 存 nest.png、nest-front.png → 假拿起球 → 读回狗起来没有（起来了还站在垫子上：perch 还是垫子的高度、前沿还在，狗不从窝里穿过去）。没有狗窝就跳过。"""
        state["step"] = "nest"
        t = pg.things.items.get("bed/blue")
        if t is None:
            note(nest="no bed here, skipped")
            s10o_swap()
            return
        b = pg.ball
        state["cursor"] = (pg.roam.wx - 0.4 * win.ppm, pg.roam.wy - 0.6 * win.ppm)
        pg._idle_for = pg._nest_after()

        def row():
            fw = t.front_win
            shown = fw is not None and fw.isVisible()
            g = fw.geometry() if shown else None
            return {"nest": pg._nest.key if pg._nest is not None else None, "task": pg.roam.task, "posture": win.dog.posture, "lounge": win.dog.lounge,
                    "perch": round(win.dog.perch, 4), "perch_to": round(pg._perch_to, 4), "shadow_hidden": win.dog.hide_shadow,
                    "dog_root": [round(pg.roam.wx, 1), round(pg.roam.wy, 1)], "bed_root": [round(t.x, 1), round(t.y, 1)],
                    "front_shown": shown, "front_level": native.window_level(fw) if shown else None, "dog_level": native.window_level(win),
                    "front_ignores_mouse": native.ignores_mouse(fw) if shown else None, "front_drawn": t.front_shot is not None,
                    "front_rect": [g.x(), g.y(), g.width(), g.height()] if shown else None,
                    "same_rect_as_bed": shown and g == t.win.geometry(), "front_alpha": round(t.front_alpha, 2)}

        def lying():
            before = stack()
            shuffle()
            QTimer.singleShot(300, lambda: lying_after(before))

        def lying_after(before):
            after = stack()
            note(**row(), stack=before, shuffled=after, same_after_shuffle=before == after)
            shot("nest")
            if t.front_win is not None and t.front_win.isVisible():
                t.front_win.grab().save(str(OUT / "nest-front.png"))
            pg.ball_press(QPointF(b.x, b.y))
            pg.ball_drag(QPointF(pg.roam.wx - 0.35 * win.ppm, pg.roam.wy - 0.55 * win.ppm))   # 这一拖就是拿起：狗该起来
            QTimer.singleShot(1500, up)

        def up():
            note(roused=row())
            pg.ball_release(QPointF(b.x, b.y))
            wait_done(s10m_eat, 15.0)                             # 松手它会去追、叼回来：等它把球放下、闲下来再点盆（叼着球时点盆它不来）
        QTimer.singleShot(9000, lying)

    def s10m_eat():
        """吃：假点一下饭盆（按下、不挪、马上松手）→ 狗过去吃 → 吃到一半读回鼻子离盆心多远（米）、播的哪一段、盆还满不满，截图
        → 吃完读回盆变空没有、画的是不是空盆的模型、图出好没有，存 eat-bowl-empty.png。声音关着（自测全程不出声），嘴对不对得上声音要真机听。没有饭盆就跳过。"""
        state["step"] = "eat"
        t = pg.things.items.get("food_bowl/bowl")
        if t is None:
            note(eat="no food bowl here, skipped")
            s10o_swap()
            return
        at = QPointF(t.x, t.y - 5.0)
        pg.things.thing_press(t, at)
        pg.things.thing_release(t, at)
        note(tapped=True, task=pg.roam.task, phase=pg.roam.phase, full=t.full, bowl_root=[round(t.x, 1), round(t.y, 1)])

        def row():
            nose = None
            if win.dog._last is not None:
                root, g = win.dog._last
                from widget.gltf import mat_mul, transform_point
                nx, ny = pg.roam.scene_point(*transform_point(mat_mul(root, g[win.dog.props.nose]), (0.0, 0.0, 0.0)))
                nose = [round((nx - t.x) / win.ppm, 3), round((t.y - ny) / win.ppm, 3)]      # 鼻子在盆心右边多少、比盆踩的线高多少（米）
            return {"task": pg.roam.task, "phase": pg.roam.phase, "clip": win.dog.player.name, "full": t.full, "model": Path(t.geo[0]).name,
                    "drawn": t.shot is not None and not t.need_shot, "nose_from_bowl_m": nose, "dog_root": [round(pg.roam.wx, 1), round(pg.roam.wy, 1)],
                    "program_bowl": win.dog.props.bowl is not None}

        def eating():
            note(eating=row())
            shot("eat")
            wait_done(eaten, 15.0, cond=lambda: pg.roam.task is None)   # 吃完（片段播完、任务结束）再读盆

        def eaten():
            note(eaten=row())
            t.win.grab().save(str(OUT / "eat-bowl-empty.png"))
            s10n_roof()
        # 走到盆边要多久看离得多远：等真的播到吃的那一段，再过 0.6 秒（鼻子最低的那一刻附近）读
        wait_done(lambda: QTimer.singleShot(600, eating), 12.0, cond=lambda: win.dog.player.name in ("Eat_loop", "Drink_loop"))

    def s10n_roof():
        """台子：摆一个平顶狗屋，挪到主屏中间偏右的地面上 → 读回它的假窗口框（窗口号是负的）、
        在不在窗口表里、狗能站的线里有没有它 → 叫狗跳上屋顶（roam.go_to）→ 读回狗踩的是不是屋顶、脚在不在台面那条线上，截图 → 假拿起狗屋 → 读回狗掉下来、落到地面没有。
        狗屋也是窝：一落定闲着的狗会走过去趴在门前（读回 placed_task）；挪狗屋之前照「窝离开原地了」告诉它一声（things._left：在路上的站住、趴下的起来）。
        狗的脚和屋顶对不对得上、狗画在狗屋前面：看 …-roof-dog.png 和 roof.png 拼起来，或真屏幕。没有平顶狗屋就跳过。"""
        state["step"] = "roof"
        key = "doghouse/flat"
        if not any(s.key == key for s in win.things_available()):
            note(roof="no flat doghouse here, skipped")
            s10o_swap()
            return
        win.set_thing(key, True)

        def placed():
            t = pg.things.items[key]
            note(placed_task=pg.roam.task, nest_going=pg._nest_going.key if pg._nest_going is not None else None)
            pg.things._left(t)
            t.x = primary.x() + primary.width() * 0.62
            pg.things._seat(t, pg.things._floor(t.area, t.x))
            pg.things._settle(t)
            f = pg.things.frame_of(t)
            top = next((s for s in pg.supports() if s.kind == "window" and s.key == t.number), None)
            note(number=t.number, frame=[round(v, 1) for v in (f.x, f.y, f.w, f.h)] if f is not None else None, house_root=[round(t.x, 1), round(t.y, 1)],
                 in_table=[fr.number for fr in pg.frames][:4], standable=top is not None, dog_root=[round(pg.roam.wx, 1), round(pg.roam.wy, 1)])
            if top is None:
                s10o_swap()
                return
            note(go=pg.roam.go_to(top, t.x), task=pg.roam.task, phase=pg.roam.phase)
            QTimer.singleShot(7000, lambda: up(t, top))

        def up(t, top):
            s = pg.roam.support
            note(task=pg.roam.task, on=[s.kind, s.key] if s is not None else None, dog_root=[round(pg.roam.wx, 1), round(pg.roam.wy, 1)], top_y=round(top.y, 1),
                 feet_on_top=abs(pg.roam.wy - top.y) < 1.0)
            shot("roof")
            t.win.grab().save(str(OUT / "roof.png"))
            pg.things.thing_press(t, QPointF(t.x, t.y - 10.0))
            pg.things.thing_drag(t, QPointF(t.x - 200.0 * win.scale, t.y - 260.0 * win.scale))   # 这一拖就是拿起：台子没了，狗原地掉
            QTimer.singleShot(2500, lambda: down(t))

        def down(t):
            s = pg.roam.support
            note(held=t.state, task=pg.roam.task, on=[s.kind, s.key] if s is not None else None, dog_root=[round(pg.roam.wx, 1), round(pg.roam.wy, 1)],
                 in_table=[fr.number for fr in pg.frames][:4])
            pg.things.thing_release(t, QPointF(*t.pointer))
            QTimer.singleShot(1500, s10o_swap)
        QTimer.singleShot(1800, placed)

    def footprint_gfx() -> float:
        """这个进程在显卡上占多少（MB）：footprint 里带 (graphics) 的那几行加起来。"""
        out = subprocess.run(["/usr/bin/footprint", "-p", str(os.getpid())], capture_output=True, text=True, timeout=60).stdout
        units = {"B": 1 / 1048576, "KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}
        total = 0.0
        for line in out.splitlines():
            m = re.match(r"\s*([\d.]+)\s+(B|KB|MB|GB)\s+.*\(graphics\)\s*$", line)
            if m:
                total += float(m.group(1)) * units[m.group(2)]
        return round(total, 1)

    def frame_gaps(since=None) -> dict:
        """从开始记（state["frames"] = []）到现在：几帧、最长的帧间隔、超过 20 毫秒的有几次；since 给了再算从那一刻到狗淡回满的秒数。"""
        rows = state.pop("frames", None) or []
        ts = [t for t, _ in rows]
        gaps = [(b - a) * 1000 for a, b in zip(ts, ts[1:])]
        out = {"frames": len(rows), "worst_gap_ms": round(max(gaps), 1) if gaps else None, "gaps_over_20ms": sum(g > 20.0 for g in gaps)}
        if since is not None:
            full = next((t for t, o in rows if t >= since and o >= 0.999), None)
            out["opacity_back_s"] = round(full - since, 3) if full is not None else None
        return out

    def s10r_rise(then):
        """起身（「萨摩耶趴着时拿起球，一下弹起来」）：自己会趴下的狗（萨摩耶；边牧不自己歇，跳过）趴好以后起来四次，每帧记一行到 rise.jsonl：
        拿起球（坐起来）→ 扔出去（站起来追）→ 叼回来、再趴下 → 到点溜达（站起来走）→ 再趴下 → 拿起球，这一次每帧截狗的窗口（rise/*.png，截图本身拖慢帧，
        所以计时看前三次）。每行：离上一帧多久（dt_ms）、这一帧画了几次、片段和播到几成、窗口和宽着时画的那一块、骨架最高点（加耳朵）离窗口顶 / 那一块的顶还有多少
        （room_px，负的就是头被截了）、分两步改窗口走没走完。截不了真屏幕（没有录屏权限），上屏和窗口改大小同不同步看不到。"""
        state["step"] = "rise"
        plan = pg._rest_plan()
        b = pg.ball
        if plan is None or b is None:
            note(rise="this dog does not lie down by itself, or no ball: skipped")
            then()
            return
        dog = win.dog
        rise_log = open(OUT / "rise.jsonl", "w")
        shots_dir = OUT / "rise"
        shots_dir.mkdir(exist_ok=True)
        rs = {"label": None, "last": None, "n": 0, "rows": {}, "gc": [], "gc_at": None}
        import gc

        def gc_watch(phase, info):                                    # 垃圾回收：每一次多久、第几代（看卡的那几帧是不是它）
            if phase == "start":
                rs["gc_at"] = time.perf_counter()
            elif rs["gc_at"] is not None:
                rs["gc"].append((info.get("generation"), round((time.perf_counter() - rs["gc_at"]) * 1000, 1)))
                rs["gc_at"] = None
        gc.callbacks.append(gc_watch)
        from widget import ring as ring_mod                           # 圈的窗口：每次同步、重画、改不透明度各多久（拿起球那一下卡的是不是它）
        timed = {"ring_sync": 0.0, "ring_paint": 0.0, "ring_opacity": 0.0}

        def timing(key, fn):
            def wrapped(*a, **kw):
                t0 = time.perf_counter()
                try:
                    return fn(*a, **kw)
                finally:
                    timed[key] += (time.perf_counter() - t0) * 1000
            return wrapped
        RW = ring_mod.RingWindow
        RW.sync = timing("ring_sync", RW.sync)
        RW.paintEvent = timing("ring_paint", RW.paintEvent)
        RW.setWindowOpacity = timing("ring_opacity", RW.setWindowOpacity)
        state["cursor"] = (pg.roam.wx, pg.roam.wy - 6.0 * win.ppm)   # 「鼠标」在狗头顶上很远：不算你在跟前（溜达照常），叼回来也放在狗这一带
        pg._wander_in = 1e9                                           # 趴好之前不自己走开

        def rise_row():
            now = time.perf_counter()
            last, rs["last"] = rs["last"], now
            paints, state["rise_paints"] = state.get("rise_paints", 0), 0
            paint_ms, state["paint_ms"] = state.get("paint_ms", 0.0), 0.0
            top_px = head_y = room = None
            h = win.height()
            if dog._last is not None:
                _, g = dog._last
                top_m = max(g[j][13] for j in dog.body) + 0.11 + dog.perch          # dogctl.MESH_MARGIN：最高关节到耳朵尖
                top_px = top_m * ce * win.ppm
                root_y = h - win.ground_px + win.draw_offset[1]                     # 根在窗口里（从上往下数）
                head_y = root_y - top_px
                fr = win.view.frame
                ceiling = 0.0 if fr is None or fr.region is None else h - (fr.region[1] + fr.region[3])
                room = head_y - ceiling
            fr = win.view.frame
            row = {"t": round(now - state["t0"], 3), "label": rs["label"], "dt_ms": None if last is None else round((now - last) * 1000, 1),
                   "paints": paints, "clip": dog.player.name, "u": round(dog.player.progress, 3), "posture": dog.posture,
                   "transition": dog.transition, "task": pg.roam.task, "required": round(dog.required, 3), "stance_top": round(dog.stance_top(), 3),
                   "win": [win.x(), win.y(), win.width(), h], "wide": win._wide, "region": None if fr is None else fr.region,
                   "reshape_pending": win._reshape_next is not None, "top_px": None if top_px is None else round(top_px, 1),
                   "room_px": None if room is None else round(room, 1), "tick_ms": round(state.get("tick_ms", 0.0), 1),
                   "paint_ms": round(paint_ms, 1), **{k: round(v, 1) for k, v in timed.items()}, "gc": [g for g in rs["gc"] if g[0] == 2 or g[1] >= 2.0]}
            rs["gc"] = []
            for k in timed:
                timed[k] = 0.0
            rise_log.write(json.dumps(row, ensure_ascii=False) + "\n")
            rs["rows"].setdefault(rs["label"], []).append(row)
            if rs.get("grab"):
                rs["n"] += 1
                win.grab().save(str(shots_dir / f"{rs['label']}-{rs['n']:03d}.png"))
        state["rise_row"] = rise_row

        def record_for(label, seconds, next_step, grab=False):
            rs.update(label=label, last=None, n=0, grab=grab)
            state["rise_on"] = True

            def stop():
                state["rise_on"] = False
                rs["grab"] = False
                next_step()
            QTimer.singleShot(int(seconds * 1000), stop)

        def lie_down(next_step, waited=0.0):
            pg._wander_in = 1e9
            if dog.posture == "lying" and not dog.transition and not pg.roam.busy:
                QTimer.singleShot(1500, next_step)                           # 趴稳、窗口按趴着的高度缩回来、宽着的回到平时大小
            elif waited > 30.0:
                note(rise_timeout="never lay down", posture=dog.posture, lounge=dog.lounge, task=pg.roam.task)
                finish()
            else:
                if not pg.roam.busy and not pg.carried and not pg.ball_held:
                    pg._idle_for = max(pg._idle_for, plan[0] + plan[1] + 0.5)
                QTimer.singleShot(100, lambda: lie_down(next_step, waited + 0.1))

        def pick():
            pg.ball_press(QPointF(b.x, b.y))
            pg.ball_drag(QPointF(pg.roam.wx - 0.35 * win.ppm, pg.roam.wy - 0.55 * win.ppm))

        def pickup():
            record_for("pickup", 2.0, toss)
            pick()

        def toss():
            t = time.perf_counter()
            pg.ring.ready = True
            pg.grab.clear()
            vx = 900.0 * win.scale
            pg.grab.extend([(t - 0.06, b.x - vx * 0.06, b.y + 30.0), (t, b.x, b.y)])
            record_for("throw", 2.5, lambda: wait_done(lambda: lie_down(wander), 20.0))
            pg.ball_release(QPointF(b.x, b.y))

        def wander():
            record_for("wander", 2.5, lambda: wait_done(lambda: lie_down(pickup_grab), 20.0))
            pg._wander_in = 0.0

        def pickup_grab():
            record_for("pickup-grab", 1.6, drop, grab=True)
            pick()

        def drop():
            pg.grab.clear()
            pg.ball_release(QPointF(b.x, b.y))                                 # 手不动松开：球直着落
            QTimer.singleShot(1500, finish)

        def finish():
            state["rise_on"] = False
            rise_log.close()
            if gc_watch in gc.callbacks:
                gc.callbacks.remove(gc_watch)
            for label, rows in rs["rows"].items():
                dts = [r["dt_ms"] for r in rows if r["dt_ms"] is not None]
                rooms = [r["room_px"] for r in rows if r["room_px"] is not None]
                clips = []
                for r in rows:
                    if not clips or clips[-1][0] != r["clip"]:
                        clips.append([r["clip"], r["t"]])
                note(rise=label, frames=len(rows), dt_max_ms=max(dts, default=None), slow_frames=sum(1 for d in dts if d > 25.0),
                     least_room_px=min(rooms, default=None), cut_frames=sum(1 for v in rooms if v < 0.0),
                     resized=len({tuple(r["win"]) for r in rows}) - 1, went_wide=any(r["wide"] for r in rows), clips=clips)
            then()
        lie_down(pickup)

    def s10q_swapcard(then):
        """卡片开着从滑动条换模型（换模型那一下界面不能跟着卡）：打开卡片、名单里添一只另一个模型的（不换过去）、等它在后台备好，
        再像人那样滑过去（strip.go）、滑回来，来回两趟。每帧一行记到 OUT_DIR/swapcard.jsonl：离上一帧多久、这一帧主线程上换同桌那几步各花了多久
        （贴纸、卡片跟上、贴图换上、重建详情页、毛色那一行、头像、换模型本身），慢的那几帧是哪一步。设置照旧在 OUT_DIR/settings.ini。"""
        state["step"] = "swapcard"
        from widget import packs as packs_mod
        other = next((p for p in packs_mod.pets() if p.id != win.pack.id), None)
        if other is None:
            note(swapcard="only one model here, skipped")
            then()
            return
        panel, strip = win.settings_panel, win.settings_panel.strip
        out = open(OUT / "swapcard.jsonl", "w")
        spent = {}
        rec = {"on": False, "last": None, "label": None, "rows": {}}

        def timing(obj, name):
            real = getattr(obj, name)

            def wrapper(*a, **k):
                t = time.perf_counter()
                try:
                    return real(*a, **k)
                finally:
                    spent[name] = spent.get(name, 0.0) + (time.perf_counter() - t) * 1000
            setattr(obj, name, wrapper)
        for obj, name in ((strip, "_render"), (panel, "pet_changed"), (panel, "coat_landed"), (panel, "_rebuild"), (panel, "_paint_swatches"),
                          (panel, "_fill_coat_faces"), (win, "_use_kit"), (win.look, "_wear"), (win.kits, "_land"), (win, "switch_pet"),
                          (win.view, "render")):
            timing(obj, name)

        import threading
        import traceback as tb
        main_id = threading.get_ident()
        stacks = []                                          # 主线程的调用栈，每 1 毫秒看一眼（只在记的时候）：慢的那一帧主线程在干什么

        def sampler():
            while rec.get("sampling"):
                if state.get("swapcard_on"):
                    f = sys._current_frames().get(main_id)
                    names = [] if f is None else [(fr.f_code.co_filename.rsplit("/", 1)[-1], fr.f_code.co_name) for fr, _ in tb.walk_stack(f)][:10]
                    f = None                                 # 马上放掉：拿着主线程的帧，帧里的 QPainter 就活过了 paintEvent（这样崩过一次）
                    stacks.append((time.perf_counter(), names))
                time.sleep(0.001)
        rec["sampling"] = True
        threading.Thread(target=sampler, daemon=True).start()

        def row():
            now = time.perf_counter()
            last, rec["last"] = rec["last"], now
            r = {"t": round(now - state["t0"], 3), "label": rec["label"], "dt_ms": None if last is None else round((now - last) * 1000, 1),
                 "tick_ms": round(state.get("tick_ms", 0.0), 1), "pack": win.pack.id, "opacity": round(win.dog_opacity, 2),
                 **{k: round(v, 1) for k, v in spent.items() if v >= 0.05}}
            if last is not None and now - last > 0.025:
                from collections import Counter
                seen = Counter()
                for t, st in stacks:
                    if last < t < now:
                        for fr in {f for f in st if f[0] not in ("selftest_playground.py",)}:
                            seen[fr] += 1
                r["busy"] = [f"{n}×{a}:{b}" for (a, b), n in seen.most_common(6)]
            stacks[:] = [x for x in stacks if x[0] >= now]
            spent.clear()
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            rec["rows"].setdefault(rec["label"], []).append(r)
        state["swapcard_row"] = row

        def record(label, seconds, next_step):
            rec.update(label=label, last=None)
            spent.clear()
            state["swapcard_on"] = True

            def stop():
                state["swapcard_on"] = False
                next_step()
            QTimer.singleShot(int(seconds * 1000), stop)

        def opened():
            pet = win.roster.add(other.id)                     # 名单里有另一个模型的一只（不换过去）
            panel.pet_changed()
            state["swapcard_pet"] = pet.id
            win.warm_pets()                                    # 卡片打开 0.4 秒后那一下：后台备它
            wait_ready()

        def wait_ready(waited=0.0):
            if win.kits.ready(other.id) or waited > 15.0:
                note(swapcard_ready=win.kits.ready(other.id), waited_s=round(waited, 1))
                QTimer.singleShot(1500, lambda: go(1, "to-other-1"))
            else:
                QTimer.singleShot(100, lambda: wait_ready(waited + 0.1))

        plan = [(1, "to-other-1"), (0, "back-1"), (1, "to-other-2"), (0, "back-2")]

        def go(index, label):
            record(label, 2.2, lambda: after(label))
            strip.go(index)

        def after(label):
            k = [lab for _, lab in plan].index(label)
            if k + 1 < len(plan):
                QTimer.singleShot(800, lambda: go(*plan[k + 1]))
            else:
                finish()

        def finish():
            rec["sampling"] = False
            out.close()
            for label, rows in rec["rows"].items():
                slow = [r for r in rows if r["dt_ms"] is not None and r["dt_ms"] > 20.0]
                note(swapcard=label, frames=len(rows), worst_ms=max((r["dt_ms"] or 0.0) for r in rows),
                     over_20ms=len(slow), over_25ms=sum(1 for r in slow if r["dt_ms"] > 25.0),
                     slow=[{k: v for k, v in r.items() if k not in ("label", "pack")} for r in sorted(slow, key=lambda r: -r["dt_ms"])[:5]],
                     pack=rows[-1]["pack"] if rows else None)
            panel.hide()
            then()
        panel.toggle_near(win)
        QTimer.singleShot(1500, opened)

    def s10o_swap():
        """换模型（换模型不重启）：两个模型都在才跑，没有另一个就跳过。见文件开头。"""
        state["step"] = "swap"
        from widget import packs as packs_mod
        other = next((p for p in packs_mod.pets() if p.id != win.pack.id), None)
        if other is None:
            note(swap="only one model here, skipped")
            s11_quit()
            return
        pid, first = os.getpid(), win.prefs.pet_id
        win.place_scene(primary.x() + primary.width() * 0.45, floor_y(primary))
        win._after_move()
        state["cursor"] = (pg.roam.wx - 0.6 * win.ppm, pg.roam.wy - 0.4 * win.ppm)
        state["frames"] = []
        t0 = time.perf_counter()
        win.kits.want(other)                                 # 后台备（真的时候是卡片打开 0.4 秒后）：这期间主线程卡不卡

        def prepared():
            note(other=other.id, prepare_s=round(time.perf_counter() - t0, 3), ready=win.kits.ready(other.id), **frame_gaps())
            QTimer.singleShot(800, swap_idle)

        spent = {}                                           # 换的那一下各步多久（毫秒）：真机比离屏多出来的在哪

        def timed(obj, name):
            real = getattr(obj, name)

            def wrapper(*a, **k):
                t = time.perf_counter()
                try:
                    return real(*a, **k)
                finally:
                    spent.setdefault(name, []).append(round((time.perf_counter() - t) * 1000, 1))
            setattr(obj, name, wrapper)
            return real

        def swap_idle():
            shot("swap-before")
            state["frames"] = []
            originals = [(obj, name, timed(obj, name)) for obj, name in (
                (win, "_use_kit"), (win, "fade_dog"), (win.closeup, "finish"), (win.settings, "sync"), (win.look, "reload"),
                (win.settings_panel, "pet_changed"), (win.roster, "add"), (win.roster, "select"), (win.view, "set_model"), (win.playground, "pet_arrived"),
                (win.playground, "pet_leaving"), (win.look, "use_model"))]
            t1 = time.perf_counter()
            state["new"] = win.add_pet(other.id, "自测")
            call_ms = (time.perf_counter() - t1) * 1000
            for obj, name, real in originals:
                setattr(obj, name, real)
            note(same_process=os.getpid() == pid, pack=win.pack.id, new=state["new"], call_ms=round(call_ms, 1), opacity=round(win.dog_opacity, 2),
                 all_new=win.dog.model is win.model and win.view.renderer.model is win.model and pg.roam.dog is win.dog, spent=dict(spent))

            def faded():
                note(**frame_gaps(since=t1))
                shot("swap-after")
                QTimer.singleShot(600, carry_back)
            QTimer.singleShot(1500, faded)

        def carry_back():
            state["step"] = "swap-carry"
            throw(-900.0 * win.scale, -700.0 * win.scale)
            wait_done(carried, 12.0, cond=lambda: pg.roam.carrying)

        def carried():
            was = pg.roam.carrying
            win.switch_pet(first)                             # 叼着球换回去：球掉在原地、小窗口回来
            b = pg.ball
            note(carrying_before=was, pack=win.pack.id, carried=pg.carried, task=pg.roam.task, ball=[round(b.x, 1), round(b.y, 1), b.resting],
                 ball_win_visible=pg.ball_win is not None and pg.ball_win.isVisible())
            QTimer.singleShot(1500, lambda: (note(ball_after=[round(b.x, 1), round(b.y, 1), b.resting]), nest_swap()))

        def nest_swap():
            state["step"] = "swap-nest"
            if not any(s.key == "bed/blue" for s in win.things_available()):
                note(nest="no bed here, skipped")
                fetch_after()
                return
            if "bed/blue" not in pg.things.items:
                win.set_thing("bed/blue", True)               # 只跑这一步时还没摆：摆出来（落定闲着的狗就过去）
            pg._idle_for = pg._nest_after()
            wait_done(in_nest, 25.0, cond=lambda: pg._nest is not None and win.dog.perch == pg._perch_to and not win.dog.transition)

        def in_nest():
            t = pg.things.items["bed/blue"]
            before = {"nest": pg._nest.key if pg._nest is not None else None, "perch": round(win.dog.perch, 4), "bed": [t.win.width(), t.win.height(), round(t.geo[1], 3)]}
            shot("swap-nest-before")
            win.switch_pet(state["new"])                      # 歇在窝里换：不接着趴，站在窝那儿（踩着垫子）；狗窝按新狗的身高变大变小

            def after():
                fw = t.front_win
                note(before=before, nest=pg._nest.key if pg._nest is not None else None, pad=pg._pad, perch=round(win.dog.perch, 4),
                     perch_to=round(pg._perch_to, 4), posture=win.dog.posture, front_shown=fw is not None and fw.isVisible(),
                     bed=[t.win.width(), t.win.height(), round(t.geo[1], 3)])
                shot("swap-nest-after")
                fetch_after()
            QTimer.singleShot(1200, after)

        def fetch_after():
            state["step"] = "swap-fetch"
            state["cursor"] = (pg.roam.wx - 0.6 * win.ppm, pg.roam.wy - 0.4 * win.ppm)
            throw(1400.0 * win.scale, -800.0 * win.scale)     # 换完再扔一次：新狗照常追、叼回来（跳法的数、步子按它的模型）
            wait_done(fetched, 20.0)

        def fetched():
            b = pg.ball
            note(pack=win.pack.id, task=pg.roam.task, carried=pg.carried, ball=[round(b.x, 1), round(b.y, 1), b.resting],
                 ball_to_cursor_m=round(abs(b.x - state["cursor"][0]) / win.ppm, 2))
            churn()

        def churn():
            state["step"] = "swap-churn"
            before = footprint_gfx()
            ids = [first, state["new"]] if win.prefs.pet_id == state["new"] else [state["new"], first]
            state["frames"] = []

            def go(i=0):
                if i < 20:                                    # 来回换 10 次
                    win.switch_pet(ids[i % 2])
                    QTimer.singleShot(400, lambda: go(i + 1))
                else:
                    QTimer.singleShot(3000, lambda: (note(gfx_before_mb=before, gfx_after_mb=footprint_gfx(), pack=win.pack.id, **frame_gaps()), s11_quit()))
            go()
        wait_done(prepared, 15.0, cond=lambda: win.kits.ready(other.id) or win.kits.failed(other.id))

    def s10b_cards():
        """提示卡片、设置里滑杆上的小刻度、开发者设置页：截个图看样子；查模型包的声音文件载不载得进来。"""
        state["step"] = "cards"
        loaded = {str(f.relative_to(config.ROOT)): native.prepare_sound(str(f)) for p in (win.pack, win.ball_pack) for f in p.sound_files()}
        note(recommended=win.recommended_scale(), scale=win.scale, sounds_loaded=sum(loaded.values()), sounds_failed=[k for k, v in loaded.items() if not v])
        win.hover.set_hover(False)
        win.show_too_high()
        win.open_settings()

        def snap():
            b = win._bubble
            note(bubble=[b.x(), b.y(), b.width(), b.height()], visible=b.isVisible(), level=native.window_level(b), placed=b._placed)
            b.grab().save(str(OUT / "too-high-bubble.png"))
            panel = win.settings_panel
            panel.fit_height()
            panel.grab().save(str(OUT / "settings.png"))
            panel.show_advanced(True, animated=False)
            panel.finish_page_anim()
            panel.grab().save(str(OUT / "settings-advanced.png"))
            for _ in range(5):
                panel._version_clicked()
            panel.finish_page_anim()
            panel.grab().save(str(OUT / "settings-tuning.png"))
            page = panel.tuning_page
            page.select(next(k for k, (_, t) in enumerate(page.targets) if t is win.ball_tuning))   # 小球那一样（狗一行在前面）
            panel.grab().save(str(OUT / "settings-tuning-ball.png"))
            win.settings_panel.hide()
            state["real_hit"] = win._update_hit
            win._update_hit = lambda now: None                  # 真鼠标不在狗上：这几帧假装在「···」上
            win.hover.set_hover(True)
            win.hover.hot = True
            QTimer.singleShot(700, strip)

        def strip():
            win.grab().save(str(OUT / "fetch-pill.png"))
            win.hover.hot = False
            win.hover.set_hover(False)
            win._update_hit = state["real_hit"]
            s10h_straddle()
        QTimer.singleShot(900, snap)

    def s11_quit():
        (OUT / "flash_stats.json").write_text(json.dumps(state["flash_stats"], ensure_ascii=False, indent=0))
        note(focus=state.get("focus"))                     # 程序被切到前台、有接键盘的窗口各几次（每 50 毫秒看一次；该一直是 0）
        state["step"] = "quit"
        ticker.stop()
        record()
        log.close()
        jump_log.close()
        cross_log.close()
        for p in state["platforms"]:
            if p.poll() is None:
                p.kill()
        app.quit()

    ticker = QTimer()
    ticker.timeout.connect(record)
    ticker.start(50)
    log.write(json.dumps({"screens": [(n, [g.x(), g.y(), g.width(), g.height()], [a.x(), a.y(), a.width(), a.height()])
                                      for n, g, a in screens],
                          "primary": [primary.x(), primary.y(), primary.width(), primary.height()],
                          "above": None if above is None else above.name()}) + "\n")
    win.place_initially()
    win.fade_in()
    win.windowHandle().screenChanged.connect(screen_switched)
    QTimer.singleShot(1500, s1_place)
    QTimer.singleShot(300000, s11_quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
