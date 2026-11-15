"""面板类测试共用的底子：offscreen 平台、假的 QSettings、每条测试一套窗口 + 设置卡片，跑完停掉计时器。
三个测试模块：test_settings_card（卡片 / 表盘 / 毛色页 / 贴纸风）、test_hover_menu（狗窗口上的交互）、test_modes_platform（模式 / 平台）。"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

import config

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from widget import kits as _kits                 # noqa: E402

_kits.PROCESS = False      # 别的模型在本进程的线程里备（快；给 packs.load_model 打的补丁才管用）。子进程那条路 tests/test_kits.py 单独测
# offscreen 平台没有 RHI（画不了 QRhiWidget）、不支持 raise()，Qt 每次都警告；这里不需要，过滤掉
QUIET = ("QRhiWidget", "This plugin does not support")


class FakeSettings:
    def __init__(self, *args):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass

    def clear(self):
        self.values.clear()

    def remove(self, key):
        self.values.pop(key, None)


@unittest.skipUnless(Path(config.MODEL_PATH).is_file(), "models/collie.glb not present (purchased asset)")
class PanelCase(unittest.TestCase):
    DYNAMIC = False
    # 检查更新那一行的测试用一个假的发布仓库，不碰真的
    UPDATE_REPO: "str | None" = "example/deskmate"
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
        from widget.settings import SettingsPanel
        import tempfile
        from widget import updater
        repo = mock.patch.object(config, "UPDATE_REPO", self.UPDATE_REPO)
        repo.start()
        self.addCleanup(repo.stop)
        # 面板测试绝不能启动真的卸载器：从源码跑时它没有 app 可删，握手一成就直接清真用户的设置、日志、缓存
        # （新按钮和卸载页的「删除」重名时，测试会按到它、清掉真用户的设置）。要测卸载流程的用例自己再 patch 一层。
        from widget import uninstall
        guard = mock.patch.object(uninstall, "start", side_effect=AssertionError("tests must never start the real uninstaller"))
        guard.start()
        self.addCleanup(guard.stop)
        self._cache = tempfile.TemporaryDirectory()             # 检查更新的缓存放临时目录，不碰真的 ~/Library/Caches
        with mock.patch.object(window, "QSettings", FakeSettings), mock.patch.object(updater, "CACHE_DIR", Path(self._cache.name)):
            self.win = window.CompanionWindow(self.model)
        if not self.DYNAMIC:
            self.win.set_dynamic(False)                         # 灵动交互新装默认开；老用例按"关着"写（姿势行在、点击不理），要开的用例自己开
        self.settings = SettingsPanel(self.win)
        self.win.attach_panels(self.settings)

    def tearDown(self):
        from widget import i18n
        i18n.set_language("en")                 # 换过语言的测试别把 zh 漏给后面的模块
        """每条测试一套窗口，跑完停掉它们的计时器、藏起来：不然 50 多个窗口的 60 fps 动画计时器把事件循环挤满，靠真实计时的测试会飘。"""
        # 外观 / 语言测试会重建卡片；只藏最初两个引用会留下新卡片，挡住后续 QTest 悬停。
        for w in {self.settings, self.win.settings_panel, self.win}:
            w.hide()
        if self.win.update_prompt is not None:
            self.win.update_prompt.hide()
        self._cache.cleanup()
        self.win._anim_timer.stop()
        self.app.processEvents()
