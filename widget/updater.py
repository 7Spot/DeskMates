"""检查更新、下载、安装。只有用户点「检查更新」才联网，从不自动查、不在后台联网。

发布仓库：config.UPDATE_REPO（GitHub 上的公开仓库，这个软件自己的）。没填就不检查更新，设置里也不显示那一行（enabled）。
规则：
- 正式版的 Release：没勾 pre-release、标签形如 v1.0.0、正好一个 .dmg。测试版的 Release：勾了 pre-release、标签形如 v0.6.0-b10、正好一个 .dmg。
- 装测试版（config.CHANNEL == "pre"）：两种都看（测试版要能更新到正式版），先比版本号，同一个版本号正式版比测试版新，都是测试版比构建号；
- 装正式版（"stable"）：只看正式版，比版本号。测试版更新到正式版以后就只收正式版了（打包时写死在 config.CHANNEL 里）。
  两条线都从列表里按标签挑，不看 Latest（仓库只有一个 Latest，测试版和正式版会抢）。
- 下载完核对文件大小和 sha256（Release 里每个文件自带的 size、digest），对不上就删掉。
- 更新说明 = 正文里「**更新内容**」那一段（英文界面「**What's new**」，没写就用中文那段），到下一个粗体标题为止；
  网页上新建或改过的正文换行是 \\r\\n，按行切开后先去掉 \\r。
联网都在后台线程里做：macOS 15 起「本地网络」权限没点之前系统的域名解析可能挂住（打包的坑），所以界面 10 秒没等到结果就当连不上。
安装 = 打开下载好的 DMG，和第一次安装一样把 app 拖进 Applications 替换旧的。
自动卸载由 widget/uninstall.py 与独立原生助手负责。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

import config
from widget.https import open_url

log = logging.getLogger("updater")

PRE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-b(\d+)$")
STABLE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
TIMEOUT_S = 10.0                      # 界面最多等这么久；超过就显示「无法连接到 GitHub，点击重试」
LATEST_SHOWN_MS = 3000                # 「已是最新版本」显示 3 秒变回「检查更新」
CACHE_DIR = Path.home() / "Library" / "Caches" / config.DATA_NAME   # 卸载器认这个路径（改名不改它）
USER_AGENT = f"{config.APP_NAME}/{config.VERSION}"


def api_url() -> Optional[str]:
    """发布仓库的 Release 列表；没填仓库（config.UPDATE_REPO 是 None）就是 None。"""
    repo = config.UPDATE_REPO
    return f"https://api.github.com/repos/{repo}/releases?per_page=100" if repo else None


def enabled() -> bool:
    """有发布仓库才检查更新；没有的话设置里不显示「检查更新」，check() 什么都不做。"""
    return api_url() is not None


def failure_reason(error: Exception) -> str:
    """只按实际错误分类；普通 403 不是限流，不读取可能阻塞的响应体。"""
    if isinstance(error, urllib.error.HTTPError):
        headers = error.headers or {}
        if error.code == 429 or (error.code == 403 and (
            headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After") is not None
        )):
            return "rate_limit"
        if error.code == 404:
            return "no_release"                  # 发布仓库还没建、还没发过：不是连不上
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "certificate"
    if isinstance(reason, TimeoutError):
        return "timeout"
    return "network"


def version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def version_text(version: str, build: int) -> str:
    """给人看的版本号（高级设置最底下、新版本提示、已下载页）：开发版「0.6.0 (66)」（macOS「关于」的写法：版本号 (构建号)）；
    发布版（config.DEV_BUILD 是 False，--release / --stable 打的包）只写「0.6.0」，构建号只在开发者设置页最底下有。"""
    return f"{version} ({build})" if build and config.DEV_BUILD else version


@dataclass
class Release:
    version: str
    build: int                         # 正式版没有构建号：0
    tag: str
    url: str                           # DMG 的下载地址
    size: int
    digest: str                        # "sha256:…"，旧的 Release 可能没有：空
    name: str                          # DMG 文件名
    body: str
    published: str                     # ISO 时间，比如 2026-10-30T10:14:21Z

    def label(self) -> str:
        return version_text(self.version, self.build)

    def size_text(self) -> str:
        return f"{max(1, round(self.size / 1e6))} MB"

    def date_text(self, lang: str) -> str:
        try:
            d = datetime.fromisoformat(self.published.replace("Z", "+00:00")).astimezone()
        except ValueError:
            return ""
        return f"{d.month} 月 {d.day} 日" if lang == "zh" else d.strftime("%b ") + str(d.day)

    def notes(self, lang: str) -> list[tuple[bool, str]]:
        return parse_notes(self.body, lang)


def _rank(version: str, build: int) -> tuple[int, ...]:
    """比新旧：先比版本号；同一个版本号正式版（构建号记 0）比它的测试版新；都是测试版比构建号。"""
    return (*version_tuple(version), 1 if build == 0 else 0, build)


def is_newer(rel: "Release", channel: str, version: str, build: int) -> bool:
    """这个 Release 比装着的新吗。正式版只比版本号；测试版连同正式版一起比（测试版要能更新到正式版）。"""
    if channel == "stable":
        return version_tuple(rel.version) > version_tuple(version)
    return _rank(rel.version, rel.build) > _rank(version, build)


def pick_release(releases: list, channel: str, version: str, build: int) -> Optional[Release]:
    """从 GitHub 的 Release 列表里挑这条线能收到的最新的那个；比自己新就返回它，否则 None。规则见模块说明。
    测试版能收到测试版和正式版，正式版只收正式版。"""
    best = None
    for r in releases if isinstance(releases, list) else []:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        tag = str(r.get("tag_name") or "")
        dmgs = [a for a in (r.get("assets") or []) if str(a.get("name", "")).lower().endswith(".dmg")]
        if len(dmgs) != 1:
            continue
        stable, pre = STABLE_TAG.match(tag), PRE_TAG.match(tag)
        if stable and not r.get("prerelease"):
            ver, bld = ".".join(stable.groups()), 0
        elif pre and r.get("prerelease") and channel != "stable":
            ver, bld = ".".join(pre.groups()[:3]), int(pre.group(4))
        else:
            continue
        key = _rank(ver, bld)
        if best is None or key > best[0]:
            a = dmgs[0]
            best = (key, Release(ver, bld, tag, str(a.get("browser_download_url") or ""), int(a.get("size") or 0),
                                 str(a.get("digest") or ""), str(a.get("name") or ""), str(r.get("body") or ""),
                                 str(r.get("published_at") or "")))
    if best is None:
        return None
    rel = best[1]
    return rel if is_newer(rel, channel, version, build) else None


_BOLD_HEAD = re.compile(r"^\*\*(.+?)\*\*\s*[:：]?\s*(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BULLET = re.compile(r"^(?:[-*•]|\d+[.)])\s+")


def _section(lines: list[str], titles: tuple[str, ...]) -> list[str]:
    out, inside = [], False
    for raw in lines:
        s = raw.strip()
        m = _BOLD_HEAD.match(s)
        if m:
            if inside:
                break
            if m.group(1).strip().lower().replace("’", "'") in titles:
                inside = True
                if m.group(2).strip():
                    out.append(m.group(2).strip())
            continue
        if inside and s:
            out.append(s)
    return out


def parse_notes(body: str, lang: str) -> list[tuple[bool, str]]:
    """正文 → [(是不是圆点, 字)]。只取「更新内容」（英文界面「What's new」，没写就用另一种）那一段。"""
    lines = [line.rstrip("\r") for line in (body or "").replace("\r\n", "\n").split("\n")]
    zh, en = _section(lines, ("更新内容",)), _section(lines, ("what's new",))
    picked = (en or zh) if lang == "en" else (zh or en)
    out = []
    for s in picked:
        bullet = bool(_BULLET.match(s))
        text = _LINK.sub(r"\1", _BULLET.sub("", s)).replace("**", "").replace("`", "").strip()
        if text:
            out.append((bullet, text))
    return out


def bundle_path() -> Optional[Path]:
    """打包的 app 本身（…/Deskmate.app）；从源码跑的时候 None。"""
    if not getattr(sys, "frozen", False):
        return None
    p = Path(sys.executable).resolve()
    for parent in p.parents:
        if parent.suffix == ".app":
            return parent
    return None


class Updater(QObject):
    """「检查更新」这一行背后的状态：idle（检查更新）/ checking（正在检查…）/ latest（已是最新版本，3 秒后回 idle）/
    offline（无法连接到 GitHub，点击重试）/ found（发现新版本，关掉设置就忘）/ downloading（正在下载 38%）/
    downloaded（新版本已下载完成；安装包留在缓存里，下次打开小组件也还在）/ failed（下载没完成，点击重试）。"""
    changed = Signal()
    ready = Signal()                                   # 刚下载完（弹「下载已完成，现在安装吗」）
    _got = Signal(int, object)                         # 后台线程 → 主线程：(第几次查, 结果或异常)
    _tick = Signal(int, float)
    _done = Signal(int, object)

    def __init__(self, cache_dir: Path = CACHE_DIR, fetch: Optional[Callable] = None, opener: Optional[Callable] = None,
                 spawn: Optional[Callable] = None, channel: str = config.CHANNEL, parent=None):
        super().__init__(parent)
        self.dir = Path(cache_dir) / "updates"
        self.channel = channel
        self.state = "idle"
        self.error_reason: Optional[str] = None
        self.release: Optional[Release] = None
        self.progress = 0.0
        self._fetch = fetch or self._fetch_json
        self._open = opener or self._open_url
        self._spawn = spawn or (lambda fn: threading.Thread(target=fn, daemon=True).start())
        self._token = 0
        self._got.connect(self._on_checked)
        self._tick.connect(self._on_progress)
        self._done.connect(self._on_downloaded)
        self._load_pending()

    # ---- 状态 ----
    def _set(self, state: str) -> None:
        self.state = state
        if state not in ("offline", "failed"):
            self.error_reason = None
        self.changed.emit()

    def package(self) -> Optional[Path]:
        return self.dir / self.release.name if (self.release is not None and self.release.name) else None

    def _load_pending(self) -> None:
        """上次下好、没装的安装包：还在、而且比现在这个新，就接着是「新版本已下载完成」。"""
        meta = self.dir / "pending.json"
        try:
            rel = Release(**json.loads(meta.read_text()))
        except (OSError, ValueError, TypeError):
            return
        if is_newer(rel, self.channel, config.VERSION, config.BUILD) and (self.dir / rel.name).is_file():
            self.release, self.state = rel, "downloaded"
        elif getattr(sys, "frozen", False):
            shutil.rmtree(self.dir, ignore_errors=True)               # 装过了 / 不比现在新：打包的 app 里顺手清掉（从源码跑的单测不碰真缓存）

    def forget(self) -> None:
        """关掉设置：发现新版本 / 已是最新 / 连不上这些结果作废，下次打开要重新点检查更新。"""
        if self.state in ("found", "latest", "offline", "checking"):
            self._token += 1
            self.release = None
            self._set("idle")

    # ---- 检查 ----
    def check(self) -> None:
        url = api_url()
        if url is None or self.state in ("checking", "downloading"):
            return
        self._token += 1
        token = self._token
        self._set("checking")
        QTimer.singleShot(round(TIMEOUT_S * 1000), lambda: self._timeout(token))

        def work():
            try:
                result = pick_release(self._fetch(url), self.channel, config.VERSION, config.BUILD)
            except Exception as e:                      # noqa: BLE001 —— 主线程按错误类型显示原因，保持重试入口
                result = e
            self._got.emit(token, result)

        self._spawn(work)

    def _timeout(self, token: int) -> None:
        if token == self._token and self.state == "checking":
            self._token += 1
            self.error_reason = "timeout"
            log.info("check failed: no response after %.0f seconds", TIMEOUT_S)
            self._set("offline")

    def _on_checked(self, token: int, result) -> None:
        if token != self._token or self.state != "checking":
            return                                          # 已经超时 / 关了设置：这次的结果不要了
        if isinstance(result, Exception):
            self.error_reason = failure_reason(result)
            log.info("check failed: %r", result)
            self._set("offline")
        elif result is None:
            self._set("latest")
            QTimer.singleShot(LATEST_SHOWN_MS, lambda: self._set("idle") if self.state == "latest" else None)
        else:
            self.release = result
            self._set("found")

    @staticmethod
    def _fetch_json(url: str):
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                                                   "User-Agent": USER_AGENT})
        with open_url(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---- 下载 ----
    def download(self) -> None:
        if self.release is None or self.state == "downloading":
            return
        rel = self.release
        self._token += 1
        token = self._token
        self.progress = 0.0
        self._set("downloading")

        def work():
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
                part = self.dir / (rel.name + ".part")
                h, got, last = hashlib.sha256(), 0, -1
                with self._open(rel.url) as resp, open(part, "wb") as f:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        h.update(chunk)
                        got += len(chunk)
                        pct = int(100 * got / rel.size) if rel.size else 0
                        if pct != last:
                            last = pct
                            self._tick.emit(token, got / rel.size if rel.size else 0.0)
                if rel.size and got != rel.size:
                    raise ValueError(f"size {got} != {rel.size}")
                if rel.digest.startswith("sha256:") and h.hexdigest() != rel.digest.split(":", 1)[1]:
                    raise ValueError("sha256 mismatch")
                part.replace(self.dir / rel.name)
                (self.dir / "pending.json").write_text(json.dumps(asdict(rel), ensure_ascii=False))
                self._done.emit(token, None)
            except Exception as e:                          # noqa: BLE001 —— 断了、对不上：删掉，提示点击重试
                shutil.rmtree(self.dir, ignore_errors=True)
                self._done.emit(token, e)

        self._spawn(work)

    @staticmethod
    def _open_url(url: str):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        return open_url(req, timeout=30)

    def _on_progress(self, token: int, value: float) -> None:
        if token == self._token and self.state == "downloading":
            self.progress = value
            self.changed.emit()

    def _on_downloaded(self, token: int, error) -> None:
        if token != self._token:
            return
        if error is None:
            self._set("downloaded")
            self.ready.emit()
        else:
            self.error_reason = failure_reason(error)
            log.info("download failed: %r", error)
            self._set("failed")

    def remove_package(self) -> None:
        """删除安装包：缓存里的 DMG 和记录都删掉，回到「检查更新」。"""
        shutil.rmtree(self.dir, ignore_errors=True)
        self.release = None
        self._set("idle")

    # ---- 安装 / 卸载 ----
    def install(self) -> Optional[Path]:
        """安装 = 打开下载好的 DMG：和第一次安装一样，把 app 拖进 Applications 替换旧的，设置都留着。
        app 不自己换自己——macOS 保护 app 本身，后台替换会被挡住、卡住。返回 DMG 的路径；没有安装包返回 None。
        安装包留在缓存里，等下次打开新版本时（构建号不比它小）再清掉。"""
        pkg = self.package()
        if pkg is None or not pkg.is_file():
            return None
        subprocess.Popen(["/usr/bin/open", str(pkg)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return pkg


def reveal(path: Path) -> None:
    """在访达里打开它所在的文件夹并选中它，访达到前面来（全屏的空间里也切过去，native.reveal_in_finder）；不是 cocoa 时退回 open -R。"""
    from widget import native
    if not native.reveal_in_finder(str(path)):
        subprocess.Popen(["/usr/bin/open", "-R", str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
