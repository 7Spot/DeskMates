"""启动：加载狗模型 + Qt 窗口 + Settings 面板 + 菜单栏图标。一条命令：python app.py"""
from __future__ import annotations

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()   # 打包版里备别的模型的子进程（widget/kits.py，spawn）也从这个可执行文件起：是它就在这里做完活退出，不往下导入、不建界面

import logging                         # noqa: E402
import os                              # noqa: E402
import signal                          # noqa: E402
import traceback                       # noqa: E402
from pathlib import Path               # noqa: E402

from PySide6.QtCore import QSettings, QTimer   # noqa: E402
from PySide6.QtWidgets import QApplication     # noqa: E402

import config                                  # noqa: E402
from widget import kits, packs                 # noqa: E402
from widget.settings import SettingsPanel      # noqa: E402
from widget import native                      # noqa: E402
from widget.tray import Tray                   # noqa: E402
from widget.window import CompanionWindow      # noqa: E402

FREEZE_AFTER_S = 3.0   # 启动这么久以后收一遍垃圾、把活着的都冻起来（kits.freeze_heap）：以后的全量回收不再扫启动时的那一大堆（模型、界面），一次从 20～30 毫秒降下来


def log_uncaught(kind, value, trace) -> None:
    """没接住的错误也写进日志：打包的 app 没有终端，按钮背后的代码出错时，界面只是没反应，日志里什么都没有。"""
    logging.getLogger("app").error("uncaught error\n%s", "".join(traceback.format_exception(kind, value, trace)))
    sys.__excepthook__(kind, value, trace)


def check_qt_can_see_its_plugins() -> None:
    """venv 放在 iCloud 同步的目录（如 ~/Documents）里时，Qt 列不出自己的插件目录，启动会直接 abort。
    先用同样的方式查一遍，查不到就给出明白的提示，而不是弹崩溃报告。"""
    from PySide6.QtCore import QDir, QLibraryInfo

    platforms = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath) + "/platforms"
    if not QDir(platforms).entryList(QDir.Filter.Files):
        sys.exit(
            f"Qt cannot list its platform plugins in {platforms}\n"
            "Most likely the venv lives inside an iCloud-synced folder (e.g. ~/Documents).\n"
            "Recreate it with a name ending in .nosync, e.g.:  python3 -m venv .venv.nosync   (see README)"
        )


def prepare_check(pack_id: str) -> int:
    """开发验证用（环境变量 DESKMATE_PREPARE_CHECK=模型包的 id，tools/build_app.sh 打完跑一次）：在子进程里备这个模型一遍（和换同桌时一样，
    kits._prepare_apart），打印结果就退出。不建窗口、不读写设置。验的是打包版里备模型的子进程起不起得来（它是从 app 自己的可执行文件起的）。"""
    import time
    pack = packs.discover().get(pack_id)
    if pack is None or not pack.available:
        print(f"prepare check: no usable pack {pack_id!r}", file=sys.stderr)
        return 2
    started = time.perf_counter()
    try:
        model = kits._prepare_apart(pack)
    except Exception as exc:                      # noqa: BLE001 —— 什么错都算没过，打出来
        print(f"prepare check: {pack_id} failed in the child process: {exc}", file=sys.stderr)
        return 1
    print(f"prepare check: {pack_id} prepared in a child process in {time.perf_counter() - started:.2f} s, "
          f"{len(dict.keys(model.clips))} clips, {model.mesh.vertex_count} vertices")
    return 0


def main() -> int:
    check = os.environ.get("DESKMATE_PREPARE_CHECK")
    if check:
        return prepare_check(check)
    log_file = None
    if getattr(sys, "frozen", False):          # 打包的 .app 没有终端：日志写到 ~/Library/Logs/Deskmate.log
        log_dir = Path.home() / "Library" / "Logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / f"{config.DATA_NAME}.log")      # 改名不改它（config.DATA_NAME）
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-5s %(message)s", datefmt="%H:%M:%S", filename=log_file)
    sys.excepthook = log_uncaught
    check_qt_can_see_its_plugins()

    signal.signal(signal.SIGINT, signal.SIG_DFL)   # 终端 Ctrl+C 直接退出
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setQuitOnLastWindowClosed(False)   # 面板关了也不退出；退出走菜单栏 / Settings / Ctrl+C
    # 选的是哪个模型（widget/packs.py）：记在设置里；不在了、缺东西用不了就回到默认那只
    pack = packs.choose_pet(QSettings("Deskmate", "Companion").value("pack", ""))
    if not pack.available:
        sys.exit(f"Missing {pack.model}\nPut the purchased model files in models/ and run tools/export_glb.py (see README).")
    model = packs.load_model(pack)
    missing = packs.problems(model)
    if missing:
        logging.getLogger("app").warning("pack %s can't be used, missing: %s", pack.id, missing)
        pack = packs.choose_pet()
        model = packs.load_model(pack)
    logging.getLogger("app").info("model %s: %d clips, %d joints", pack.id, len(model.clips), len(model.skin_joints))
    window = CompanionWindow(model, pack=pack)
    window.attach_panels(SettingsPanel(window))   # 自定义毛色是设置卡片的第三页
    native.warm_audio()                           # 声音服务在后台初始化：第一次放声音不卡
    native.start_sound_thread()                   # 声音在后台线上放：每次 9～15 毫秒不占主线程（滑动条的 tick、狗叫都不掉帧）
    window.tray = Tray(window, app)               # 菜单栏骨头；留引用免得被回收
    window.apply_policy()                      # 爪子建好了才能决定要不要切 accessory（小组件全局可见）
    window.place_initially()   # 上次放哪就放哪，否则右上角
    window.fade_in()
    QTimer.singleShot(round(FREEZE_AFTER_S * 1000), lambda: kits.freeze_heap(collect=True))
    # 跟着程序的激活状态校验身份；点 Dock 图标当场校验（见 window.on_app_state）
    window.watch_app_state(app)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
