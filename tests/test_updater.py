"""检查更新：按管仓库那边定的规则挑版本、读「更新内容」、下载后核对大小和 sha256；设置里那一行的几种样子、几页、卸载。
不联网：GitHub 的列表和下载都换成假的，后台线程换成当场跑。"""
import hashlib
import io
import json
import ssl
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import config
from tests.panel_base import PanelCase
from widget import updater
from widget.updater import Updater, failure_reason, parse_notes, pick_release


def rel(tag, pre=True, dmgs=1, body="", size=100, digest="", published="2026-11-01T02:00:00Z"):
    assets = [{"name": f"Deskmate-{tag}.dmg", "size": size, "digest": digest,
               "browser_download_url": f"https://example.invalid/{tag}.dmg"} for _ in range(dmgs)]
    assets.append({"name": "notes.txt", "size": 1, "browser_download_url": "x"})
    return {"tag_name": tag, "prerelease": pre, "draft": False, "assets": assets, "body": body, "published_at": published}


OLD = [rel("deskmate-dev-0.5.1"), rel("deskmate-dev-0.5.0"), rel("deskmate-dev-0.4.0")]   # 现在仓库里的：格式对不上，跳过
NEXT = config.BUILD + 1                         # 比现在这个包新一号的测试版（构建号每打一次包加一，不能写死）
NEXT_TAG, NEXT_LABEL = f"v0.6.0-b{NEXT}", f"0.6.0 ({NEXT})"
REPO = "example/deskmate"                       # 测试用的假发布仓库，不碰真的
API = f"https://api.github.com/repos/{REPO}/releases?per_page=100"


class NetworkFailureTests(unittest.TestCase):
    def test_certificate_timeout_and_rate_limit_have_distinct_reasons(self):
        cases = [
            (urllib.error.URLError(ssl.SSLCertVerificationError(1, "unable to get local issuer certificate")), "certificate"),
            (TimeoutError("read timed out"), "timeout"),
            (urllib.error.URLError(TimeoutError("connect timed out")), "timeout"),
            (urllib.error.HTTPError(API, 429, "Too Many Requests", {}, None), "rate_limit"),
            (urllib.error.HTTPError(API, 403, "Forbidden", {"X-RateLimit-Remaining": "0"}, None), "rate_limit"),
            (urllib.error.HTTPError(API, 403, "Forbidden", {"Retry-After": "60"}, None), "rate_limit"),
            (urllib.error.HTTPError(API, 403, "Forbidden", {"X-RateLimit-Remaining": "55"}, None), "network"),
            (urllib.error.URLError(OSError("host lookup failed")), "network"),
            (urllib.error.HTTPError(API, 404, "Not Found", {}, None), "no_release"),
        ]
        for error, expected in cases:
            with self.subTest(error=repr(error), expected=expected):
                self.assertEqual(failure_reason(error), expected)

    def test_check_and_download_both_use_the_certificate_aware_transport(self):
        with mock.patch.object(updater, "open_url", return_value=io.BytesIO(b"[]")) as opened:
            self.assertEqual(Updater._fetch_json(API), [])
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, API)
            self.assertEqual(request.get_header("User-agent"), f"DeskMates/{config.VERSION}")
            self.assertEqual(opened.call_args.kwargs["timeout"], 10)
            self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")
        with mock.patch.object(updater, "open_url", return_value=io.BytesIO(b"dmg")) as opened:
            with Updater._open_url("https://example.invalid/update.dmg") as response:
                self.assertEqual(response.read(), b"dmg")
            self.assertEqual(opened.call_args.args[0].full_url, "https://example.invalid/update.dmg")
            self.assertEqual(opened.call_args.kwargs["timeout"], 30)


class PickTests(unittest.TestCase):
    def test_prerelease_line_takes_the_biggest_build_that_matches_all_three_rules(self):
        self.assertIsNone(pick_release(OLD, "pre", "0.5.1", 7), "旧的 deskmate-dev-* 对不上格式")
        lst = OLD + [rel("v0.6.0-b10"), rel("v0.6.0-b12", dmgs=2), rel("v0.6.1-b11", pre=False), rel("v0.6.0-b9"), rel("v0.6.0-b13x")]
        r = pick_release(lst, "pre", "0.5.1", 7)
        self.assertEqual((r.tag, r.version, r.build), ("v0.6.0-b10", "0.6.0", 10), "两个 DMG、没勾 pre-release、标签不对的都不算")
        self.assertIsNone(pick_release(lst, "pre", "0.6.0", 10), "不比自己的构建号大：已是最新")
        self.assertEqual(r.label(), "0.6.0 (10)")
        self.assertEqual(r.size_text(), "1 MB")

    def test_stable_line_never_sees_prereleases_and_compares_versions(self):
        lst = [rel("v0.6.0-b10"), rel("v1.0.0", pre=False), rel("v1.2.0", pre=False), rel("v1.10.0", pre=False, dmgs=0)]
        r = pick_release(lst, "stable", "1.0.0", 0)
        self.assertEqual((r.tag, r.build, r.label()), ("v1.2.0", 0, "1.2.0"))
        self.assertIsNone(pick_release(lst, "stable", "1.2.0", 0))
        self.assertIsNone(pick_release([rel("v0.6.0-b10")], "stable", "0.1.0", 0), "正式版看不到测试版")
        self.assertIsNone(pick_release({"message": "rate limited"}, "pre", "0.5.1", 7), "返回的不是列表")


class BetaToStableTests(unittest.TestCase):
    """测试版能更新到正式版。"""
    def test_a_beta_is_offered_a_newer_stable_version(self):
        r = pick_release([rel("v1.0.0", pre=False)], "pre", "0.6.0", 45)
        self.assertEqual((r.tag, r.version, r.build, r.label()), ("v1.0.0", "1.0.0", 0, "1.0.0"))

    def test_the_stable_release_of_the_same_version_beats_its_betas(self):
        lst = [rel("v0.6.0-b50"), rel("v0.6.0", pre=False)]
        self.assertEqual(pick_release(lst, "pre", "0.6.0", 45).tag, "v0.6.0")
        self.assertEqual(pick_release(lst, "pre", "0.6.0", 50).tag, "v0.6.0", "已经是最后一个测试版：也能更新到正式版")

    def test_an_older_stable_version_is_not_offered(self):
        self.assertIsNone(pick_release([rel("v0.5.0", pre=False)], "pre", "0.6.0", 45))

    def test_a_newer_beta_beats_an_older_stable(self):
        lst = [rel("v0.6.0", pre=False), rel("v0.7.0-b60")]
        self.assertEqual(pick_release(lst, "pre", "0.6.0", 45).tag, "v0.7.0-b60")

    def test_betas_still_compare_by_build_within_a_version(self):
        self.assertEqual(pick_release([rel("v0.6.0-b46")], "pre", "0.6.0", 45).tag, "v0.6.0-b46")
        self.assertIsNone(pick_release([rel("v0.6.0-b45")], "pre", "0.6.0", 45))

    def test_the_tag_and_the_pre_release_box_must_still_agree(self):
        self.assertIsNone(pick_release([rel("v1.0.0", pre=True)], "pre", "0.6.0", 45), "正式版的标签却勾了 pre-release")
        self.assertIsNone(pick_release([rel("v1.0.0-b60", pre=False)], "pre", "0.6.0", 45), "测试版的标签却没勾")


class NotesTests(unittest.TestCase):
    def test_only_the_update_section_is_shown(self):
        body = ("**更新内容**：修复已知问题，优化性能\r\n\r\n**开发者版本**：包含仍在开发中的功能\r\n\r\n"
                "**怎么打开**\r\n1. 下载 `Deskmate-dev-0.5.1.zip`\r\n")
        self.assertEqual(parse_notes(body, "zh"), [(False, "修复已知问题，优化性能")], "现在的写法：到下一个粗体标题为止；网页改过的 \\r\\n 也认")
        self.assertEqual(parse_notes(body, "en"), [(False, "修复已知问题，优化性能")], "没写 What's new：英文界面显示中文那段")
        body = ("**更新内容**\n- 点击范围就是狗\n- 修好了 [跳桌面](https://x)\n\n**What’s new**\n- The click area is the dog\n\n**需要**：M 芯片\n")
        self.assertEqual(parse_notes(body, "zh"), [(True, "点击范围就是狗"), (True, "修好了 跳桌面")])
        self.assertEqual(parse_notes(body, "en"), [(True, "The click area is the dog")])
        self.assertEqual(parse_notes("随便写的", "zh"), [], "两段都没有：页上写「这个版本没有写更新说明」")


class NoReleaseRepoTests(unittest.TestCase):
    """发布仓库：每个软件一个自己的；没填就不检查更新、不联网。"""
    def test_shipped_config_uses_the_apps_own_release_repo(self):
        self.assertEqual(config.UPDATE_REPO, "7Spot/Deskmate", "新版本发到这个仓库的 Release")
        self.assertEqual(updater.api_url(), "https://api.github.com/repos/7Spot/Deskmate/releases?per_page=100")
        self.assertTrue(updater.enabled())

    def test_check_does_nothing_without_a_repo(self):
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        fetched = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(config, "UPDATE_REPO", None):
            u = Updater(cache_dir=Path(tmp), fetch=lambda url: fetched.append(url) or [], spawn=lambda fn: fn(), channel="pre")
            u.check()
            self.assertEqual(u.state, "idle")
            self.assertEqual(fetched, [], "没有仓库就不联网")
        with mock.patch.object(config, "UPDATE_REPO", REPO):
            self.assertEqual(updater.api_url(), API)
            self.assertTrue(updater.enabled())


class UpdaterFlowTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtWidgets import QApplication
        repo = mock.patch.object(config, "UPDATE_REPO", REPO)
        repo.start()
        self.addCleanup(repo.stop)
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.payload = b"dmg bytes " * 1000
        self.digest = "sha256:" + hashlib.sha256(self.payload).hexdigest()
        self.list = OLD + [rel(NEXT_TAG, size=len(self.payload), digest=self.digest, body="**更新内容**\n- 新东西")]

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, fetch=None, data=None):
        return Updater(cache_dir=Path(self.tmp.name), fetch=fetch or (lambda url: self.list),
                       opener=lambda url: io.BytesIO(self.payload if data is None else data), spawn=lambda fn: fn(), channel="pre")

    def test_check_download_verify_and_keep_the_package_for_next_time(self):
        u = self.make()
        self.assertEqual(u.state, "idle")
        u.check()
        self.assertEqual(u.state, "found", "比 0.5.1 (7) 新：发现新版本")
        self.assertEqual(u.release.notes("zh"), [(True, "新东西")])
        u.forget()
        self.assertEqual(u.state, "idle", "关掉设置就作废")
        u.check()
        ready = []
        u.ready.connect(lambda: ready.append(1))
        u.download()
        self.assertEqual(u.state, "downloaded")
        self.assertEqual(ready, [1], "下载完弹提示")
        pkg = u.package()
        self.assertTrue(pkg.is_file())
        self.assertEqual(pkg.read_bytes(), self.payload)
        again = self.make()
        self.assertEqual(again.state, "downloaded", "下次打开小组件：安装包还在，接着是「新版本已下载完成」")
        again.forget()
        self.assertEqual(again.state, "downloaded", "关设置不影响下好的")
        again.remove_package()
        self.assertEqual(again.state, "idle")
        self.assertFalse(pkg.exists(), "删除安装包：文件也删了")

    def test_wrong_size_or_hash_or_no_network_never_leaves_files_behind(self):
        u = self.make(data=b"truncated")
        u.check()
        u.download()
        self.assertEqual(u.state, "failed", "大小对不上：下载没完成，点击重试")
        self.assertFalse(any(Path(self.tmp.name).rglob("*.dmg*")), "半截文件删掉")
        self.list[-1]["assets"][0]["digest"] = "sha256:" + "0" * 64
        u = self.make()
        u.check()
        u.download()
        self.assertEqual(u.state, "failed", "sha256 对不上")

        def boom(url):
            raise OSError("no route to host")
        u = self.make(fetch=boom)
        u.check()
        self.assertEqual(u.state, "offline", "连不上：无法连接到 GitHub，点击重试")
        self.list = OLD
        u = self.make()
        u.check()
        self.assertEqual(u.state, "latest", "没有更新的：已是最新版本")

    def test_a_hanging_lookup_times_out_in_the_ui(self):
        u = Updater(cache_dir=Path(self.tmp.name), fetch=lambda url: self.list, spawn=lambda fn: None, channel="pre")
        u.check()
        self.assertEqual(u.state, "checking")
        with self.assertLogs("updater", level="INFO") as logs:
            u._timeout(u._token)
        self.assertEqual(u.state, "offline", "10 秒没结果（比如系统的域名解析挂住）就当连不上，界面不卡")
        self.assertEqual(u.error_reason, "timeout")
        self.assertIn("no response after 10 seconds", logs.output[0])
        u._got.emit(u._token - 1, None)
        self.assertEqual(u.state, "offline", "迟到的结果不要了")
        self.assertEqual(u.error_reason, "timeout")

    def test_certificate_failure_is_cleared_on_check_retry_and_close(self):
        error = urllib.error.URLError(ssl.SSLCertVerificationError(1, "missing issuer"))
        u = self.make(fetch=mock.Mock(side_effect=error))
        u.check()
        self.assertEqual((u.state, u.error_reason), ("offline", "certificate"))
        u._spawn = lambda fn: None
        u.check()
        self.assertEqual((u.state, u.error_reason), ("checking", None))
        u._got.emit(u._token, error)
        self.assertEqual(u.error_reason, "certificate")
        u.forget()
        self.assertEqual((u.state, u.error_reason), ("idle", None))

    def test_download_certificate_failure_keeps_release_for_retry_and_cleans_partial_file(self):
        u = self.make()
        u.check()
        u._open = mock.Mock(side_effect=urllib.error.URLError(ssl.SSLCertVerificationError(1, "missing issuer")))
        u.download()
        self.assertEqual((u.state, u.error_reason), ("failed", "certificate"))
        self.assertIsNotNone(u.release)
        self.assertFalse(u.dir.exists())
        u._open = lambda url: io.BytesIO(self.payload)
        transitions = []
        u.changed.connect(lambda: transitions.append((u.state, u.error_reason)))
        u.download()
        self.assertEqual(transitions[0], ("downloading", None))
        self.assertEqual((u.state, u.error_reason), ("downloaded", None))
        self.assertEqual(u.package().read_bytes(), self.payload)


class SettingsUpdateTests(PanelCase):
    def _fake(self, payload=b"x" * 2000):
        up = self.win.updater
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        lst = [rel(NEXT_TAG, size=len(payload), digest=digest, body="**更新内容**\n- 新东西\n- 修好了")]
        up._fetch = lambda url: lst
        up._open = lambda url: io.BytesIO(payload)
        up._spawn = lambda fn: fn()

    def test_network_error_reasons_are_shown_in_both_languages_and_remain_retryable(self):
        from widget import i18n
        up, s = self.win.updater, self.settings
        expected = {
            "certificate": ("Certificate error · Retry", "证书验证失败 · 重试"),
            "timeout": ("Connection timed out · Retry", "连接超时 · 重试"),
            "rate_limit": ("GitHub rate limit · Try later", "GitHub 限流 · 稍后重试"),
            "no_release": ("No releases yet", "还没有发布版本"),                 # 发布仓库还没建：不是连不上
        }
        for language_index, lang in enumerate(("en", "zh")):
            i18n.set_language(lang)
            for state in ("offline", "failed"):
                for reason, text in expected.items():
                    with self.subTest(lang=lang, state=state, reason=reason):
                        up.state, up.error_reason = state, reason
                        s.sync_update()
                        self.assertEqual(s.update_button.text(), text[language_index])
                        self.assertTrue(s.update_button.clickable)
        i18n.set_language("en")
        up.state, up.error_reason = "offline", "network"
        s.sync_update()
        self.assertEqual(s.update_button.text(), "Can't connect · Retry")
        up.state = "failed"
        s.sync_update()
        self.assertEqual(s.update_button.text(), "Download failed · Retry")

    def test_version_row_states_clickable_ones_have_a_hover_frame(self):
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        self.app.processEvents()
        self._fake()
        up = self.win.updater
        self.assertTrue(s.update_button.isVisibleTo(s))
        self.assertEqual(s.update_button.text(), "Check for updates")
        self.assertTrue(s.update_button.property("quiet"), "灰字按钮：悬停出描边框")
        self.assertEqual(s.update_button.motion.content_rect().height(), 26)
        self.assertEqual(s.update_button.height(), 30, "可见高度保持26，外侧透明余量避免动效截边")
        for state, clickable in (("checking", False), ("latest", False), ("offline", True), ("found", True), ("downloading", False),
                                 ("downloaded", True), ("failed", True)):
            up.state = state
            up.changed.emit()
            self.assertTrue(s.update_button.isVisibleTo(s), "状态始终留在同一控件里")
            self.assertEqual(s.update_button.clickable, clickable, state)
        up.state = "found"
        up.changed.emit()
        self.assertEqual(s.update_button.property("tone"), "blue", "发现新版本是蓝色")
        up.state = "idle"
        up.release = None
        s.update_button.click()
        self.assertEqual(up.state, "found")
        s.update_button.click()
        self.assertEqual(s.page, "notes", "点「发现新版本」：整张卡片换成更新说明")
        self.assertIn(NEXT_LABEL, s._title_label.text())
        texts = [w.text() for w in s.notes_box.findChildren(type(s.version_label))]
        self.assertIn("新东西", texts)
        s.update_now.held.emit()                                     # 长按「更新」
        self.assertEqual(s.page, "advanced", "回到高级设置")
        self.assertEqual(up.state, "downloaded")
        self.assertEqual(s.update_button.text(), "Update ready")
        s.update_button.click()
        self.assertEqual(s.page, "downloaded")
        self.assertEqual(s.downloaded_name.text(), f"{config.APP_NAME} {NEXT_LABEL}")
        self.assertEqual({b.motion.content_rect().height() for b in (s.remove_button, s.install_button)}, {26})
        self.assertEqual({b.height() for b in (s.remove_button, s.install_button)}, {30})
        s.back.click()
        self.assertEqual(s.page, "advanced", "从高级设置进来的回高级设置")

    def test_download_finished_prompts_beside_the_dog_and_cancel_leaves_a_chip(self):
        self._fake()
        up = self.win.updater
        self.win.show()
        up.check()
        up.download()
        prompt = self.win.update_prompt
        self.assertIsNotNone(prompt)
        self.assertTrue(prompt.isVisible(), "下载完：狗旁边弹出「下载已完成，现在安装吗」")
        from PySide6.QtCore import Qt
        self.assertTrue(prompt.testAttribute(Qt.WA_ShowWithoutActivating), "不抢键盘、不激活程序（不切桌面）")
        self.assertIn(NEXT_LABEL, prompt._title_label.text())
        self.settings.show()
        self.app.processEvents()
        from PySide6.QtCore import QEvent, QPoint, QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        s, bar = self.settings, self.settings._tag
        self.assertEqual(bar.chip_text, "", "提示还开着：顶部栏先不出新版本胶囊")
        self.win.dismiss_update_prompt()
        self.assertEqual(bar.chip_text, "New version downloaded", "点了取消：顶部栏里名字右边、× 左边出现「新版本已下载完成」")
        self.assertEqual(bar.chip_says, ("New version downloaded", "Update ready", "Update"), "放不下时换短的说法")
        self.assertEqual((bar.lead.isHidden(), bar.lead_mode), (False, "mark"), "左上角的图标一直在，不让给它")
        self.assertLess(bar.chip_rect().width(), bar.chip_natural(), "从一个小圆长出来")
        s.finish_page_anim()
        main = lambda y: bar.mapTo(s._main, QPoint(0, 0)).y() + y
        self.assertEqual(main(bar.chip_rect().top()), s._close.mapTo(s._main, QPoint(0, 0)).y(), "顶和 × 齐平")
        self.assertEqual(main(bar.chip_rect().top()), 16)
        t, c = bar.tag_rect(), bar.chip_rect()
        close_x = s._close.x() - bar.x()
        gaps = (t.left() - s.back.width(), c.left() - t.right(), close_x - c.right())
        self.assertLessEqual(max(gaps) - min(gaps), 1.0, f"有它时名字往左让：左边的圆、名字、胶囊、× 三段空一样宽 {gaps}")
        self.assertGreaterEqual(min(gaps), bar.GAP - 0.5)
        room = bar._right() - bar._start() - bar.GAP - t.width()
        self.assertEqual(bar._say, next(x for x in bar.chip_says if bar.chip_natural(x) <= room + 0.5), "挑放得下的最长那句")
        self.win.set_language("zh")                                     # 中文整句挨着名字放不下：平时压窄、鼠标放上去展开
        s = self.settings = self.win.settings_panel
        s.show()
        self.app.processEvents()
        s.finish_page_anim()
        bar = s._tag
        self.assertEqual(bar.chip_text, "新版本已下载完成")
        self.assertTrue(bar.chip_truncated())
        at = bar.chip_rect().center()
        QApplication.sendEvent(bar, QMouseEvent(QEvent.MouseMove, at, QPointF(bar.mapToGlobal(at.toPoint())), Qt.NoButton, Qt.NoButton, Qt.NoModifier))
        self.assertEqual(bar._peek, "chip")
        for _ in range(45):
            bar.tick(1 / 60)
        self.assertAlmostEqual(bar.chip_rect().width(), bar.chip_natural(), delta=0.01, msg="鼠标放上去：展开成整句，名字让开")
        QApplication.sendEvent(bar, QEvent(QEvent.Leave))
        self.assertIsNone(bar._peek, "移开马上恢复")
        for page in ("advanced", "pet", "coat", "tuning"):
            s.show_page(page, animated=False)
            self.assertEqual(bar.chip_text, "新版本已下载完成", f"每一页都有（{page}）")
        s.show_page("main", animated=False)
        s.show_page("add", animated=False)
        s.add_name.setText("豆豆")
        bar.chip_clicked.emit()
        self.assertEqual((s.page, s._downloaded_from), ("downloaded", "add"), "点了去已下载页，记着从哪来")
        self.assertEqual(bar.chip_text, "", "已下载页上没有（就是它自己）")
        s.back.click()
        self.assertEqual((s.page, s.add_name.text()), ("add", "豆豆"), "取消回原来那页：打了一半的名字还在")
        s.show_page("main", animated=False)
        bar.chip_clicked.emit()
        self.assertEqual(s.page, "downloaded")
        s.remove_button.held.emit()                                    # 长按删除安装包
        self.assertEqual(up.state, "idle")
        self.assertEqual(s.page, "main", "从主页面进来的回主页面")
        self.assertEqual(bar.chip_text, "", "安装包删了：胶囊收回去")

    def test_closing_settings_forgets_found_and_install_opens_the_dmg(self):
        self._fake()
        up = self.win.updater
        self.settings.show()
        up.check()
        self.assertEqual(up.state, "found")
        self.settings.hide()
        self.assertEqual(up.state, "idle", "关一次设置，发现新版本就作废")
        up.check()
        up.download()
        quits = []
        with mock.patch.object(updater.subprocess, "Popen") as popen, \
             mock.patch("widget.window.QTimer.singleShot", side_effect=lambda ms, fn: quits.append(ms)):
            self.win.install_update()
        popen.assert_called_once()
        cmd = popen.call_args.args[0]
        self.assertEqual(cmd[0], "/usr/bin/open")
        self.assertTrue(cmd[1].endswith(".dmg"), "安装 = 打开下载好的 DMG，拖进 Applications 替换旧的（app 不自己换自己）")
        from widget.widgets import sticker_hud
        self.assertIn("Applications", sticker_hud().text)
        sticker_hud().finish_now()
        self.assertEqual(quits, [3000], "提示一下就退出，换好再打开")

    def test_uninstall_confirm_page_waits_for_ready_before_quitting(self):
        from widget import uninstall
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        s.uninstall_button.click()
        self.assertEqual(s.page, "uninstall")
        from PySide6.QtWidgets import QLabel
        self.assertFalse([label for label in s.uninstall_page.findChildren(QLabel)
                          if label.isVisibleTo(s) and label.text()])
        self.assertEqual(s.delete_button.kind, "danger")
        s.back.click()
        self.assertEqual(s.page, "advanced")
        s.uninstall_button.click()
        self.win.settings.values["dog_name"] = "Bobo"
        session = mock.Mock()
        session.poll.return_value = {"state": "starting"}
        with mock.patch.object(uninstall, "start", return_value=session) as start, \
             mock.patch.object(updater, "bundle_path", return_value=None), \
             mock.patch.object(self.win, "_quit") as quit_app:
            s.delete_button.held.emit()
            start.assert_called_once_with(None, self.win.language)
            self.assertFalse(s.delete_button.isEnabled())
            self.assertTrue(s.isVisible())
            self.win.uninstall()
            start.assert_called_once()
            quit_app.assert_not_called()
            session.commit.assert_not_called()
            self.assertEqual(self.win.settings.values["dog_name"], "Bobo")
            session.poll.return_value = {"state": "ready"}
            self.win._poll_uninstall()
            session.commit.assert_called_once()
            quit_app.assert_called_once()
            self.assertFalse(s.isVisible())
            self.assertFalse(self.win._uninstall_timer.isActive())
            self.assertEqual(self.win.settings.values["dog_name"], "Bobo",
                             "The independent helper cleans data only after the actual process exits")

    def test_uninstall_prepare_or_commit_failure_retains_app_and_data(self):
        from widget import uninstall
        from widget.widgets import sticker_hud
        self.settings.show()
        self.win.settings.values["dog_name"] = "Bobo"
        for stage in ("start", "poll", "commit"):
            with self.subTest(stage=stage):
                session = mock.Mock()
                session.poll.return_value = {"state": "error" if stage == "poll" else "ready",
                                             "code": "The uninstall helper could not start"}
                if stage == "commit":
                    session.commit.side_effect = OSError("handshake failed")
                failure = uninstall.UninstallError("Move the app to Applications before uninstalling")
                with mock.patch.object(uninstall, "start", return_value=session,
                                       side_effect=failure if stage == "start" else None), \
                     mock.patch.object(self.win, "_quit") as quit_app:
                    self.win.uninstall()
                    quit_app.assert_not_called()
                self.assertTrue(self.settings.isVisible())
                self.assertTrue(self.settings.delete_button.isEnabled())
                self.assertEqual(self.win.settings.values["dog_name"], "Bobo")
                self.assertIsNone(self.win._uninstall_session)
                self.assertFalse(self.win._uninstall_timer.isActive())
                if stage != "start":
                    session.cancel.assert_called_once()
                sticker_hud().finish_now()

    def test_cancel_uninstall_preparation_keeps_running_app(self):
        from widget import uninstall
        from widget.widgets import MotionButton
        session = mock.Mock()
        session.poll.return_value = {"state": "starting"}
        self.settings.show()
        self.settings.show_page("uninstall", animated=False)
        self.win.settings.values["dog_name"] = "Bobo"
        with mock.patch.object(uninstall, "start", return_value=session), \
             mock.patch.object(self.win, "_quit") as quit_app:
            self.win.uninstall()
            cancel = next(button for button in self.settings.uninstall_page.findChildren(MotionButton)
                          if button.text() == "Cancel")
            cancel.click()
            self.win._poll_uninstall()
            quit_app.assert_not_called()
        session.cancel.assert_called_once()
        session.commit.assert_not_called()
        self.assertIsNone(self.win._uninstall_session)
        self.assertFalse(self.win._uninstall_timer.isActive())
        self.assertEqual(self.win.settings.values["dog_name"], "Bobo")
        self.assertEqual(self.settings.page, "advanced")

    def test_interface_sound_setting_persists_without_sync_playback(self):
        from widget import sounds
        from widget.prefs import Prefs
        with mock.patch.object(sounds, "play") as play:
            self.win.set_interface_sounds(False)
            self.settings.sync()
            self.assertTrue(self.settings.interface_volume.mute.muted)
            self.assertTrue(Prefs(self.win.settings).get("interface_muted"))
            self.win.set_interface_sounds(True)
            self.settings.sync()
            self.assertFalse(self.settings.interface_volume.mute.muted)
            play.assert_not_called()

if __name__ == "__main__":
    unittest.main()


class SettingsWithoutReleaseRepoTests(PanelCase):
    """没填发布仓库：高级设置最底下只有「版本 0.6.0 (45)」，没有「检查更新」。"""
    UPDATE_REPO = None

    def test_version_row_shows_only_the_version(self):
        s = self.settings
        s.show()
        s.show_advanced(True, animated=False)
        self.app.processEvents()
        self.assertTrue(s.version_label.isVisibleTo(s))
        self.assertEqual(s.version_label.text(), f"Version {config.VERSION} ({config.BUILD})")
        self.assertFalse(s.update_button.isVisibleTo(s), "没有发布仓库：不显示「检查更新」")
        s._update_clicked()
        self.assertEqual(self.win.updater.state, "idle", "就算点到也不联网")
