"""「关于」页（设置主页面左上角圆里的 app 图标点进来）：一张无框的图（widget/about_art.py：猫狗站在水和沙滩交界的地方，
左边水里鸭子和鱼、右边沙滩上卡皮巴拉和乌龟、天上海鸥）、名字（中文「同桌 DeskMates」，英文只有 DeskMates）、版本（发布版不带构建号，
updater.version_text）、一句「养些住在你桌面上的小动物」、两个描边小胶囊链接「访问 GitHub 仓库」（这个软件的仓库）和「访问我的网站」
（个人网站；英文 Visit GitHub Repo / Visit My Site；网址在 config.GITHUB_URL / HOMEPAGE_URL，空着时先占位、点了没反应）。顶部栏没有名字胶囊，只有 ‹ 和 ×（Page.name）。

进来、回去的过渡动画（Hero）：
- 进：左上角的圆底边先打开一个口；圆里实心的 D、M 先往中间挤窄、往下拉长，越拉越细成两根线，从口里出去（不从圈上穿过去），线全出去了口再合上、
  圆里淡出返回键。两根线往下走到猫狗那一层再低一点，大圆弧拐弯，直接往上从下面钻进去把猫狗的轮廓描出来（里圈那根描 D，外圈那根绕到右边描 M），
  描完一个填黑一个，填的时候吞一下再舒展；然后地面从猫狗脚下往两头长，动物和下面的字同时从模糊里出来（动物的动作见 about_art）。
- 回：倒着走（同一个进度钟往回拨）：字、动物、地面一起很快收掉，猫狗的黑退成轮廓，两根线按走过的长度匀着往回收、顺大圆弧回到圆里，
  圆底开口、线钻进去变回粗粗的 D、M，口合上。
- 任何时候点返回 / 再点进来（回到一半、还没真的换回主页面也算）：只把进度钟的速度平滑地掉头（约 0.06 秒），每样东西都是钟的函数，
  所以位置不跳、速度连续，线会先减速再往回走。动画走着时点左上角的圆就掉头（狂点每一下都要有反应；进的路上 → 回主页面，回的路上 → 接着进关于页，settings._lead_click）。
  主页面那块照旧用 Card.crossfade 淡（拍的是屏幕上现在的样子，接着淡）。系统开了「减少动态效果」、卡片没显示：直接到位。
圆、图、字整段都画在卡片最上面一层（_HeroLayer，鼠标穿过它），关于页自己先不画（AboutPage.veil），走完交还给它们自己画，和最后一帧一个像素不差
（图和关于页自己画的是同一段代码 about_art.Scene，字是拍下来的那张）。"""
from __future__ import annotations

import bisect
import math
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

import config
from widget import about_art, marks, sticker, updater
from widget.about_art import clamp, lerp, smooth, span
from widget.card import _Flow, _blurred, picture
from widget.i18n import tr
from widget.widgets import MotionButton, draw_icon

INTRO = "Keep a few little animals that live on your desktop"    # 说明文字不带句号
LINKS = (("Visit GitHub Repo", "GITHUB_URL"), ("Visit My Site", "HOMEPAGE_URL"))   # 这个软件的仓库、个人网站；中文在 i18n 表里
# 两颗要并排放得下（卡片里面 280 宽，英文写 Website 就宽出 7 像素）

# ---- 进来那段的节奏（秒，从点下去算；回去是同一个钟往回拨） ----
T0 = 0.14                         # 两根线开始往下拉
T1 = {"D": 1.47, "M": 1.62}       # 描完 D、描完 M（各自填黑）
TF = max(T1.values())             # 猫狗都画完：地面、动物、字从这开始
LMAX = 110.0                      # 线在路上多长
# 线头怎么走：一开始拉长（越拉越细），中间顺，描轮廓时慢下来。
# 线变细、尾巴渐细、HOME_AT 照线头走到哪跟着挪
TRAVEL = about_art.bez(0.42, 0.0, 0.3, 1.0)
TEXT_AT, TEXT_STEP, TEXT_S = 0.06, 0.04, 0.6  # 字：猫狗画完以后多久开始（和动物同时）、一行比上一行晚多少、多久从模糊里出完
END = TF + about_art.Scene.END + 0.05
SWITCH_S = 0.06                   # 钟的速度掉头要多久（时间常数）
BACK_WORLD = 5.5                  # 回：字、动物、地面那段倒拨多快
BACK_LINE_V = 950.0               # 回：线头每秒往回收多少像素（按长度匀着收，不在描轮廓那截磨蹭）
BACK_TAIL = 1.3                   # 回：最后圆里那段倒拨多快
HOME_AT = 0.36                    # 回：钟倒回到这儿（线快回到圆里）才真的换回主页面：主页面淡回来、卡片变高、名字胶囊长回来都从这开始


def ease_out(u: float, k: float = 2.0) -> float:
    return 1.0 - (1.0 - clamp(u)) ** k


def dip(u: float) -> float:
    """填黑那一下：先吞一下（缩一点）再舒展回来（带一点点过头）。"""
    if u <= 0.0:
        return 1.0
    omega, zeta = 2 * math.pi * 3.2, 0.6
    wd = omega * math.sqrt(1 - zeta * zeta)
    return 1.0 - 0.056 * math.exp(-zeta * omega * u) * math.sin(wd * u)


class AboutScene(QWidget):
    """关于页的那张图（about_art.Scene 到位以后的样子）。过渡动画画着它的时候自己不画（veiled）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(round(about_art.SHOW.width()), round(about_art.SHOW.height()))
        self.veiled = False

    def paintEvent(self, event) -> None:
        if self.veiled:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(-about_art.SHOW.left(), -about_art.SHOW.top())
        about_art.scene().paint_static(p, QColor(sticker.INK))
        p.end()


class _Line(QLabel):
    """关于页的一行字：过渡动画画着它的时候自己不画（veiled）。"""

    def __init__(self, text: str):
        super().__init__(text)
        self.veiled = False

    def paintEvent(self, event) -> None:
        if not self.veiled:
            super().paintEvent(event)


class _Link(MotionButton):
    """关于页最底下的链接：描边的小胶囊（和别的按钮一样），点了用浏览器打开。网址还空着（config 里没填）时先占位，点了没反应。
    过渡动画画着它的时候自己不画（veiled）。"""

    def __init__(self, text: str, url_key: str):
        super().__init__(text)
        self.url_key, self.veiled = url_key, False
        if self.url():
            self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._open)

    def url(self) -> str:
        return getattr(config, self.url_key, "") or ""

    def _open(self, _=False) -> None:
        if self.url():
            QDesktopServices.openUrl(QUrl(self.url()))

    def paintEvent(self, event) -> None:
        if not self.veiled:
            super().paintEvent(event)


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.scene = AboutScene()
        lay.addWidget(self.scene, 0, Qt.AlignHCenter)
        name = tr("DeskMates")
        self.name = _Line(name if name == config.APP_NAME else f"{name} {config.APP_NAME}")   # 中文：同桌 DeskMates
        self.name.setStyleSheet("font-weight: 700; font-size: 15px;")
        self.version = _Line(f"{tr('Version')} {updater.version_text(config.VERSION, config.BUILD)}")
        self.version.setProperty("muted", True)
        self.intro = _Line(tr(INTRO))
        for label in (self.name, self.version, self.intro):
            label.setAlignment(Qt.AlignHCenter)
        self.intro.setWordWrap(True)
        self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lay.addSpacing(8)
        lay.addWidget(self.name)
        lay.addSpacing(2)
        lay.addWidget(self.version)
        lay.addSpacing(12)
        lay.addWidget(self.intro)
        self.links = tuple(_Link(tr(text), key) for text, key in LINKS)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        for link in self.links:
            row.addWidget(link)
        row.addStretch(1)
        lay.addSpacing(12)
        lay.addLayout(row)

    @property
    def lines(self) -> tuple:
        return (self.name, self.version, self.intro, *self.links)

    @property
    def veiled(self) -> bool:
        return self.scene.veiled

    def veil(self, on: bool) -> None:
        """过渡动画接手画图和这几行字（on）/ 交还（off）：大小、排版照旧，只是自己不画。"""
        for w in (self.scene, *self.lines):
            if w.veiled != on:
                w.veiled = on
                w.update()

    def shot(self, label: QWidget) -> QImage:
        """这一行字（链接）现在的样子（透明底，按屏幕的像素密度）：过渡动画照它画，走完交还时一个像素不差。"""
        was, label.veiled = label.veiled, False
        try:
            img = picture(label, label.rect()).toImage()
        finally:
            label.veiled = was
        img.setDevicePixelRatio(label.devicePixelRatioF())
        return img


class _HeroLayer(QWidget):
    """过渡动画画在这：挂在卡片上、盖住整个主叶（顶部栏 + 内容），鼠标穿过它；只在动画的时候显示。不挂在主叶里：换页拍旧样子（Card.crossfade）不会把它拍进去。"""

    def __init__(self, hero: "Hero"):
        super().__init__(hero.card)
        self.hero = hero
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def place(self) -> None:
        g = self.hero.card._main.geometry()
        if self.geometry() != g:
            self.setGeometry(g)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self.hero.paint(p)
        p.end()


class _Text:
    """关于页的一行字在过渡动画里的样子：清楚的一张、糊开的一张（第一次要糊时才做），在主叶里的位置。key：字、大小、像素密度一样就接着用。"""

    BLUR = 4.0

    def __init__(self, img: QImage, at: QPointF, key: tuple):
        self.img, self.at, self.key = img, at, key
        self._soft: Optional[QImage] = None
        self.pad = math.ceil(self.BLUR * 1.5)

    def soft(self) -> QImage:
        if self._soft is None:
            dpr = self.img.devicePixelRatio()
            w, h = self.img.width() / dpr + 2 * self.pad, self.img.height() / dpr + 2 * self.pad
            out = QImage(math.ceil(w * dpr), math.ceil(h * dpr), QImage.Format_ARGB32_Premultiplied)
            out.setDevicePixelRatio(dpr)
            out.fill(Qt.transparent)
            q = QPainter(out)
            _blurred(q, lambda qq: qq.drawImage(QPointF(self.pad, self.pad), self.img), QRectF(0, 0, w, h), self.BLUR, 1.0)
            q.end()
            self._soft = out
        return self._soft

    def draw(self, p: QPainter, a: float) -> None:
        """画出来 a 那么多（0 没有、1 清楚的那张原样）：糊开的那张先出来，清楚的那张后出来。"""
        if a <= 0.003:
            return
        sharp, blur = a * a, a * (1.0 - a) * 1.6
        base = p.opacity()
        for soft, k in ((True, blur), (False, sharp)):
            if k <= 0.003:
                continue
            img, pad = (self.soft(), self.pad) if soft else (self.img, 0)
            p.setOpacity(base * k)
            p.drawImage(QPointF(self.at.x() - pad, self.at.y() - pad), img)
        p.setOpacity(base)


# ---- 两根线的路 ----
def _outer(path: QPainterPath, T: QTransform) -> list:
    polys = path.toSubpathPolygons(T)
    best = max(polys, key=lambda pl: pl.boundingRect().width() * pl.boundingRect().height())
    pts = [QPointF(best[i]) for i in range(best.size())]
    if len(pts) > 1 and (pts[0] - pts[-1]).manhattanLength() < 1e-6:
        pts = pts[:-1]
    return pts


def _resample(pts: list, step: float) -> list:
    seq = pts + [pts[0]]
    out = [seq[0]]
    for a, b in zip(seq, seq[1:]):
        n = max(1, int(math.hypot(b.x() - a.x(), b.y() - a.y()) / step))
        for i in range(1, n + 1):
            out.append(QPointF(a.x() + (b.x() - a.x()) * i / n, a.y() + (b.y() - a.y()) * i / n))
    return out


def _along(path: QPainterPath, step: float = 1.0) -> list:
    L = path.length()
    n = max(2, int(L / step))
    return [path.pointAtPercent(path.percentAtLength(L * i / n)) for i in range(n + 1)]


def _cubic(p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF) -> list:
    pp = QPainterPath(p0)
    pp.cubicTo(p1, p2, p3)
    return _along(pp)


def _seg(a: QPointF, b: QPointF) -> list:
    pp = QPainterPath(a)
    pp.lineTo(b)
    return _along(pp, 0.5)


class _Track:
    """一根线一路的点：圆里那个字母（当成一根粗线，从上到下）→ 往下 → 大圆弧拐弯 → 往上钻进去 → 描一圈轮廓。
    head(p) 线头在第 p 秒走到哪（按长度），tail 线尾；描轮廓时线尾停在轮廓起点，描的那截留着。"""

    def __init__(self, small: QPainterPath, big: list, side: str, down_y: float, bottom: float, turn_x: float, approach: float,
                 exit_y: float, t1: float):
        b = small.boundingRect()

        def middle(y0: float, y1: float) -> QPointF:
            r = QPainterPath()
            r.addRect(QRectF(b.left() - 1, y0, b.width() + 2, y1 - y0))
            return small.intersected(r).boundingRect().center()
        self.W0 = b.width() * 0.8                                # 字母当成多粗的一根线
        top = QPointF(middle(b.top(), b.top() + b.height() * 0.3).x(), b.top() + self.W0 / 2)
        bot = QPointF(middle(b.bottom() - b.height() * 0.3, b.bottom()).x(), b.bottom() - self.W0 / 2)
        cap = _seg(top, bot)
        x = bot.x()
        down = _seg(bot, QPointF(x, down_y))
        ring = _resample(big, 0.6)
        bb = QRectF(min(q.x() for q in ring), min(q.y() for q in ring), 0, 0)
        bb.setRight(max(q.x() for q in ring))
        bb.setBottom(max(q.y() for q in ring))
        y0, y1 = bb.bottom() - 0.36 * bb.height(), bb.bottom() - 0.2 * bb.height()
        cand = [j for j in range(len(ring) - 1) if y0 <= ring[j].y() <= y1]
        j = min(cand, key=lambda k: ring[k].x()) if side == "left" else max(cand, key=lambda k: ring[k].x())
        loop = ring[j:-1] + ring[:j]
        if loop[min(8, len(loop) - 1)].y() > loop[0].y():         # 往上描（顺着拐上来的方向）
            loop = [loop[0]] + loop[1:][::-1]
        loop = loop + [loop[0]]
        s = loop[0]
        u1 = _cubic(QPointF(x, down_y), QPointF(x, bottom - 30), QPointF(x + 22, bottom), QPointF(turn_x, bottom))
        u2 = _cubic(QPointF(turn_x, bottom), QPointF(turn_x + approach, bottom), QPointF(s.x(), s.y() + 34), s)
        self.pts = cap + down[1:] + u1[1:] + u2[1:] + loop[1:]
        self.cum = [0.0]
        for a, c in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + math.hypot(c.x() - a.x(), c.y() - a.y()))
        self.L_cap = self.cum[len(cap) - 1]
        self.L_big0 = self.cum[len(self.pts) - len(loop)]
        self.L = self.cum[-1]
        self.L_exit = self.cum[next(i for i, q in enumerate(self.pts) if q.y() > exit_y)]
        self.t1 = t1

    def head(self, p: float) -> float:
        return self.L_cap + (self.L - self.L_cap) * TRAVEL(span(p, T0, self.t1))

    def tail(self, p: float) -> float:
        return max(0.0, min(self.head(p) - LMAX, self.L_big0))

    def speed(self, p: float) -> float:
        """进来时线头每秒走多少像素（回去按长度匀着收用）。"""
        e = 0.004
        return (self.head(min(self.t1, p + e)) - self.head(max(T0, p - e))) / (2 * e)

    def sub(self, a: float, b: float) -> list:
        pts, cum = self.pts, self.cum
        if b <= a:
            return []
        i = max(1, bisect.bisect_left(cum, a))
        j = min(len(cum) - 1, bisect.bisect_left(cum, b))

        def at(s: float, k: int) -> QPointF:
            s0, s1 = cum[k - 1], cum[k]
            u = 0.0 if s1 == s0 else (s - s0) / (s1 - s0)
            return QPointF(lerp(pts[k - 1].x(), pts[k].x(), u), lerp(pts[k - 1].y(), pts[k].y(), u))
        return [at(a, i)] + pts[i:j] + [at(b, j)]


class Hero:
    """主页面 ↔「关于」页的过渡动画（见文件开头）。settings.show_page 在这两页之间换、能动画时调 go；卡片每帧 tick（Card.run_animator），
    画在 _HeroLayer。只管算和画：走完（或 finish）把圆、图、字交还给它们自己。
    一个进度钟 p（进来那段的第几秒）带着速度 v：进 v → +1，回 v → −k(p)；换方向只让 v 平滑地变过去，所以任何时候点都不跳。"""

    def __init__(self, card, page: AboutPage):
        self.card, self.page = card, page
        self.layer: Optional[_HeroLayer] = None
        self.active = False
        self.into = True
        self.p = 0.0
        self.v = 0.0
        self.texts: list[_Text] = []
        self._kept: list[_Text] = []                 # 上一趟拍的字（字、大小一样就接着用：不用每趟重新糊）
        self.scene_at = QPointF()                    # 图的坐标原点在主叶里的哪
        self.tracks: list[_Track] = []
        self.t_out = 0.5                             # 两根线全出了圆的时刻（口合上、返回键出来）
        self._small: Optional[QTransform] = None     # 圆里的猫狗（拼好的坐标 → 主叶）
        self._home = None                            # 回：钟倒到 HOME_AT 时要调的那一下（settings 真的换回主页面）

    # ---- 开始、反过来、收尾 ----
    def go(self, into: bool) -> bool:
        """开始（或者走到一半反过来）。into：进关于页。返回 False = 不能动画（卡片没显示、减少动态效果），调的人照直接到位。"""
        if not self.card.run_animator(self):
            self.finish()
            return False
        if not self.active:
            if into or not self.texts:
                self.capture()                       # 进：关于页刚排好；回：settings 在换页之前拍过了（那时关于页还显示着）
            self._build()
            self.active = True
            self.p = 0.0 if into else END
            self.v = 1.0 if into else -self._back_speed(END)
        self.into = into
        if into:
            self._home = None
        self._show_layer()
        return True

    def go_home(self, switch) -> bool:
        """回主页面（点了返回）：先不换页，动画倒着走（字、动物、线都还画在关于页上）；钟倒到 HOME_AT（线快回到圆里）再调 switch 真的换页，
        主页面淡回来、卡片变高、名字胶囊长回来都从那一刻开始，和进来时反过来对应。已经倒到那儿了（刚点进来就点返回）就马上换。
        返回 False = 不能动画（调的人照直接换页）。"""
        if not self.card.run_animator(self):
            self.finish()
            return False
        if not self.active:
            if not self.texts:
                self.capture()                       # 关于页这时还显示着、排好了
            self.page.veil(True)
            self._build()
            self.active = True
            self.p, self.v = END, -self._back_speed(END)
        self.into = False
        self._show_layer()
        if self.p <= HOME_AT:
            self._home = None
            switch()
        else:
            self._home = switch
        return True

    def _show_layer(self) -> None:
        lead = self.card._tag.lead
        if lead is not None and not lead.hero_hidden:
            lead.hero_hidden = True
            lead.update()
        if self.layer is None:
            self.layer = _HeroLayer(self)
        self.layer.place()
        self.layer.show()
        self.layer.raise_()
        self.layer.update()

    def capture(self) -> None:
        """拍下关于页那几行字现在的样子、量好图在哪（关于页显示着、排好版时调）。都在这时候量好存着：换页以后藏起来的关于页会被 Qt 挪走。"""
        page, main = self.page, self.card._main
        page.layout().activate()
        old = {text.key: text for text in self._kept}
        self.texts = []
        for label in page.lines:
            key = (label.text(), label.width(), label.height(), label.devicePixelRatioF())
            text = old.get(key) or _Text(page.shot(label), QPointF(), key)
            text.at = QPointF(label.mapTo(main, QPoint(0, 0)))
            self.texts.append(text)
        self._kept = list(self.texts)
        self.scene_at = QPointF(page.scene.mapTo(main, QPoint(0, 0))) - about_art.SHOW.topLeft()

    def _build(self) -> None:
        """这一趟两根线的路（圆在哪、图在哪定了以后算一次）。"""
        c0, _ring, scale = self._circle()
        pcs = marks.app_pieces()
        self._small = marks.pieces_placement(c0, marks.APP_W * scale)
        art = about_art.scene()
        big = art.dm_t * QTransform.fromTranslate(self.scene_at.x(), self.scene_at.y())
        ground = self.scene_at.y() + about_art.WATER_Y
        x0 = self.scene_at.x()
        exit_y = c0.y() + 12.5 * scale + sticker.OUTLINE
        self.tracks = [                              # 圆里右边 M 那根走里圈、描大 D；左边 D 那根走外圈、绕到右边描大 M（两根线不交叉）
            _Track(self._small.map(pcs["cat"]), _outer(pcs["dog"], big), "left", ground - 50, ground + 20, x0 + 56, 24, exit_y, T1["D"]),
            _Track(self._small.map(pcs["dog"]), _outer(pcs["cat"], big), "right", ground - 50, ground + 34, x0 + 84, 70, exit_y, T1["M"]),
        ]
        self.t_out = next((i / 400 for i in range(1, 1200) if all(tr.tail(i / 400) > tr.L_exit + 2 for tr in self.tracks)), 0.6)

    def finish(self, run_pending: bool = True) -> None:
        """立刻走到头（卡片收起、单测、换到别的页、不能动画时）：圆、图、字交还给它们自己画；正等着换回主页面的，现在换
        （run_pending=False：要换去的是别的页，不用先换回主页面）。"""
        pending, self._home = self._home, None
        if not run_pending:
            pending = None
        self.active = False
        self.texts = []
        self.card._animators.discard(self)
        if self.layer is not None:
            self.layer.hide()
        self.page.veil(False)
        lead = self.card._tag.lead
        if lead is not None and lead.hero_hidden:
            lead.hero_hidden = False
            lead.update()
        if pending is not None:
            pending()

    # ---- 钟 ----
    def _back_speed(self, p: float) -> float:
        """回去时钟往回拨多快：字、动物、地面那段快；线那段按线头的长度匀着收（描轮廓那截进来时慢，倒着就快），快回到圆时慢下来；最后圆里那段慢慢来。"""
        if p > TF + 0.02:
            return BACK_WORLD
        if p > T0 + 0.02 and self.tracks:
            fwd = max(tr.speed(p) for tr in self.tracks)
            k = min(6.0, max(1.0, BACK_LINE_V / max(fwd, 1.0)))
            return min(k, 1.0 + 12.0 * (p - T0))
        return BACK_TAIL

    def tick(self, dt: float) -> bool:
        """推一帧；返回 False = 走完了（交还给它们自己画）。dt 很大（卡片 finish_animations）就直接走到头。"""
        if not self.active:
            return False
        if dt >= 1.0:
            self.finish()
            return False
        target = 1.0 if self.into else -self._back_speed(self.p)
        self.v += (target - self.v) * min(1.0, dt / SWITCH_S)
        self.p = min(END, max(0.0, self.p + self.v * dt))
        if not self.into and self._home is not None and self.p <= HOME_AT:
            switch, self._home = self._home, None
            switch()                                 # 真的换回主页面（settings.show_page 里会再调 go(False)：接着倒着走）
        if (self.into and self.p >= END) or (not self.into and self.p <= 0.0):
            self.finish()
            return False
        if self.layer is not None:
            self.layer.place()
            self.layer.update()
        return True

    # ---- 几何 ----
    def _circle(self) -> tuple[QPointF, float, float]:
        """左上角的圆（按它现在的悬停、按下样子）：圆心（主叶里）、描边中线的半径、放大了多少。"""
        bar = self.card._tag
        c, ring, scale = _Flow.circle(bar)
        return c + QPointF(bar.mapTo(self.card._main, QPoint(0, 0))), ring, scale

    # ---- 画 ----
    def paint(self, p: QPainter) -> None:
        if not self.active or not self.tracks:
            return
        card = self.card
        p.setClipRect(QRectF(0.0, 0.0, self.layer.width(), card.painted_height() - 2 * sticker.SHADOW))
        t = self.p
        ink = QColor(sticker.INK)
        self._paint_circle(p, t)
        art = about_art.scene()
        p.save()
        p.translate(self.scene_at)
        for tr, path, key in ((self.tracks[0], art.dog, "D"), (self.tracks[1], art.cat, "M")):      # 描完的填黑，吞一下再舒展
            a = ease_out(span(t, T1[key], T1[key] + 0.12), 2)
            if a > 0.0:
                bb = path.boundingRect()
                k = dip(t - T1[key])
                p.save()
                p.translate(bb.center().x(), bb.bottom())
                p.scale(k, k)
                p.translate(-bb.center().x(), -bb.bottom())
                p.setOpacity(a)
                p.setPen(Qt.NoPen)
                p.setBrush(ink)
                p.drawPath(path)
                p.restore()
        art.paint_ground(p, 1.0 - (1.0 - span(t, TF - 0.02, TF + 0.45)) ** 2.4, ink)
        art.paint_animals(p, t, TF, ink, act=clamp(self.v))
        p.restore()
        for tr in self.tracks:
            self._paint_track(p, tr, t, ink)
        for i, text in enumerate(self.texts):
            at = TF + TEXT_AT + TEXT_STEP * i
            text.draw(p, ease_out(span(t, at, at + TEXT_S), 2.2))

    def _paint_circle(self, p: QPainter, t: float) -> None:
        """左上角的圆：底边开口（线要出去时开，全出去了合上）、圆里的 D、M 变细、合上以后出返回键。"""
        lead = self.card._tag.lead
        c0, ring, scale = self._circle()
        fill = lead.fill_color() if lead is not None else QColor(sticker.PAPER_2)
        glyph = sticker.contrast_color(fill)
        line = QColor(sticker.INK)
        gap = 78.0 * (ease_out(span(t, 0.12, 0.32), 2.5) - smooth(span(t, self.t_out, self.t_out + 0.26)))
        pen = QPen(line, sticker.OUTLINE * scale)
        p.save()
        if gap < 0.5:
            p.setPen(pen)
            p.setBrush(fill)
            p.drawEllipse(c0, ring, ring)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawEllipse(c0, ring, ring)
            rect = QRectF(c0.x() - ring, c0.y() - ring, 2 * ring, 2 * ring)
            arc = QPainterPath()
            arc.arcMoveTo(rect, 270 + gap / 2)
            arc.arcTo(rect, 270 + gap / 2, 360 - gap)
            pen.setCapStyle(Qt.RoundCap)
            p.strokePath(arc, pen)
        a_back = ease_out(span(t, self.t_out + 0.1, self.t_out + 0.38), 2)
        if a_back > 0.0:
            size = lead.glyph_size() * scale if lead is not None else 13.7
            p.setOpacity(a_back)
            draw_icon(p, "back", c0, size, glyph, fill)
            p.setOpacity(1.0)
        a_letter = 1.0 - smooth(span(t, 0.2, 0.36))
        if a_letter > 0.0 and self._small is not None:
            pcs = marks.app_pieces()
            p.setPen(Qt.NoPen)
            p.setBrush(glyph)
            p.setOpacity(a_letter)
            for tr, shape in ((self.tracks[1], pcs["dog"].subtracted(pcs["dog_face"])), (self.tracks[0], pcs["cat"].subtracted(pcs["cat_face"]))):
                sil = self._small.map(shape)
                b = sil.boundingRect()
                k = smooth(span(t, 0.0, 0.34))
                sx = lerp(1.0, tr.W0 * 0.62 / b.width(), k)
                sy = lerp(1.0, 1.35, smooth(span(t, 0.08, 0.34)))
                T = QTransform().translate(b.center().x(), b.top()).scale(sx, sy).translate(-b.center().x(), -b.top())
                p.drawPath(T.map(sil))
        p.restore()

    def _paint_track(self, p: QPainter, tr: _Track, t: float, ink: QColor) -> None:
        """一根线：线头在第 t 秒走到哪、线尾跟着；字母挤窄到和线一样粗时接上，接着越拉越细；尾巴那截渐细；描完、填黑以后淡掉。"""
        a = smooth(span(t, 0.14, 0.28)) * (1.0 - span(t, tr.t1 + 0.07, tr.t1 + 0.22))
        if a <= 0.0:
            return
        h, tail = tr.head(t), tr.tail(t)
        w = lerp(tr.W0 * 0.62, 2.0, smooth(span(t, 0.14, 0.49)))
        taper_on = smooth((h - tr.L_cap) / 40) * (1.0 - smooth((tail - (tr.L_big0 - 50)) / 50)) * smooth(span(t, 0.34, 0.56))
        taper = min(70.0, (h - tail) * 0.6)
        segs = []
        if taper_on > 0.01 and taper > 2.0:
            n = 10
            for k in range(n):
                segs.append((tail + taper * k / n, tail + taper * (k + 1) / n, w * lerp(1.0, 0.3 + 0.7 * (k + 0.5) / n, taper_on)))
            segs.append((tail + taper, h, w))
        else:
            segs.append((tail, h, w))
        c = QColor(ink)
        c.setAlphaF(a)
        p.save()
        p.setBrush(Qt.NoBrush)
        for s0, s1, ww in segs:
            pts = tr.sub(s0, s1)
            if len(pts) >= 2:
                p.setPen(QPen(c, ww, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline(pts)
        p.restore()
