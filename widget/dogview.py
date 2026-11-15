"""画狗的画布（QRhiWidget，Mac 上底下是 Metal）：把 render.py 的渲染器接到窗口上，透明背景。
- DogView：窗口里那块。每帧外面调 set_frame() 再 refresh()；probe() 问窗口里某一点是不是狗（点击范围就是狗，widget/input.py）。
  「···」和脚下那行字画在它上面一层透明的普通控件里（QRhiWidget 上不能开 QPainter）。
  shoot() 借它的 QRhi 离屏画一张（贴纸、头像；物件的图也借它，另给一套渲染器），不动窗口里那一帧。
- Darkroom：不上屏的一块，没有窗口时离屏出图用（tools/render_still.py）。
offscreen 平台（单测）没有 RHI：DogView 一直不 ready()，shoot() 返回空图。"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QRhiDepthStencilClearValue
from PySide6.QtWidgets import QRhiWidget, QWidget

from widget.gltf import Model
from widget.render import CLEAR, DogRenderer, Frame, hit_rect, supersample

# 上屏时颜色再乘一遍 alpha：换 Metal 之前（QOpenGLWidget + WA_AlwaysStackOnTop）Qt 是按「没预乘」把画布混到窗口上的，
# 预乘过的颜色又被乘了一遍，半透明的边（抗锯齿那一圈、淡入淡出的道具）比算出来的暗一点。
TWICE = True
HIT_FRESH_S = 0.1      # 读回来的「是不是狗」超过这么久就不作数（鼠标刚进窗口：上一次问还是很久以前、别的地方）


class Cover(QWidget):
    """盖在画布上面的一层：「···」、姿势条、脚下那行字。透明、不接鼠标；没东西要画时什么都不画。"""

    def __init__(self, parent: QWidget, draw: Callable[[QPainter], None], needed: Optional[Callable[[], bool]]):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.draw, self.needed = draw, needed
        self.shown = False                       # 上一次画的时候有没有东西

    def paintEvent(self, event) -> None:
        self.shown = self.needed is None or bool(self.needed())
        if self.shown:
            p = QPainter(self)
            self.draw(p)
            p.end()


class _Shooting:
    """离屏出图：shoot() 让 Qt 马上叫一次 render()，那一次不画窗口里的东西，只把要的那一帧画到渲染器自己的贴图上读回来。
    （RHI 的一帧只能在 render() 里画；PySide 里没法自己开一帧。）"""
    _job: Optional[tuple[Frame, int, int, float, DogRenderer]] = None

    def _shooter(self) -> DogRenderer:
        raise NotImplementedError

    def shoot(self, frame: Frame, width: int, height: int, dpr: float = 1.0, coat: Optional[QImage] = None,
              shooter: Optional[DogRenderer] = None) -> QImage:
        """画 frame：画面 width × height 逻辑像素，出来的图是它的 dpr 倍、预乘 alpha；coat 是要贴的毛色（None = 模型自带的）。
        shooter：用这一套渲染器画（别的模型：物件，widget/thing_art.py；谁给的谁放掉）；不给就是自己那套（_shooter）。
        没有 RHI（offscreen 单测、还没画过第一帧）返回空图。"""
        shooter = self._shooter() if shooter is None else shooter
        if shooter.coat_image is not coat:
            shooter.set_coat(coat)
        self._job = (frame, width, height, dpr, shooter)
        try:
            self.grabFramebuffer()               # 它读回来的是画布本身，不要；要的图在 shooter 那
        finally:
            self._job = None
        return shooter.shot() if shooter.rhi is not None else QImage()

    def _shoot_now(self, cb) -> bool:
        """render() 开头调：这一次是不是出图。"""
        if self._job is None:
            return False
        frame, width, height, dpr, shooter = self._job
        rhi = self.rhi()
        if not shooter.bound_to(rhi):
            shooter.init(rhi, cb)
        shooter.shoot(cb, width, height, dpr, frame)
        return True


class DogView(_Shooting, QRhiWidget):
    def __init__(self, model: Model, parent=None, overlay: Optional[Callable[[QPainter], None]] = None,
                 overlay_needed: Optional[Callable[[], bool]] = None):
        super().__init__(parent)
        self.setApi(QRhiWidget.Api.Metal)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.renderer = DogRenderer(model)
        self.frame: Optional[Frame] = None
        self.cover = Cover(self, overlay, overlay_needed) if overlay is not None else None
        self._second: Optional[DogRenderer] = None                  # 离屏出图用的另一套（shoot），用完 shoot_done() 放掉
        self._ask: Optional[tuple[float, float, float]] = None     # 下一帧画完要读回哪一点（probe）
        self._answer: Optional[tuple[bool, float]] = None           # 上一次读回来的：是不是狗、什么时候
        self._reading = False
        self.cover_area = None                                      # 上面那层只重画这一块（窗口坐标，QRect）；None = 整层（宽着的窗口铺满屏宽，整层重画、传显卡太大）
        self._cover_last = None
        self.frames, self.last_report, self.fps = 0, time.perf_counter(), 0.0

    def set_frame(self, frame: Optional[Frame]) -> None:
        self.frame = frame

    def refresh(self) -> None:
        """重画这一帧。上面那层有东西要画（或者上一帧有、这一帧要擦掉）时一起重画：两样在同一次上屏里。"""
        area, last = self.cover_area, self._cover_last
        self._cover_last = area
        dirty = None if area is None else (area.united(last) if last is not None else area)   # 上一帧画过的那块也擦掉
        if dirty is None or dirty.isEmpty():
            self.update()
        else:
            self.update(dirty)          # 画布整张照画（合成时整张盖上去）；只是窗口那层（光栅的）只清、只传这一块：宽着的窗口整层清一遍、传一遍显卡，每帧十几兆（sample 量的）
        cover = self.cover
        if cover is not None and (cover.shown or cover.needed is None or cover.needed()):
            if dirty is None or dirty.isEmpty():
                cover.update()
            else:
                cover.update(dirty)

    def ready(self) -> bool:
        """画过第一帧了（RHI 建好了）。程序刚启动、offscreen 平台（单测）是 False。"""
        return self.renderer.rhi is not None

    def set_model(self, model: Model) -> None:
        """换模型（换模型不重启）：画布这套渲染器原地换（DogRenderer.set_model，下一次画的时候换顶点）；出图那套下一批照新模型现建。
        手上这一帧还是旧骨头的：调的人接着给新的一帧。上一次读回来的「是不是狗」是旧身子的，不算了。"""
        self.renderer.set_model(model)
        self.shoot_done()
        self._answer = None

    def resizeEvent(self, event) -> None:
        if self.cover is not None:
            self.cover.setGeometry(self.rect())
        super().resizeEvent(event)                # 里面会马上按新大小画一帧

    # ---- QRhiWidget ----
    def initialize(self, cb) -> None:
        """第一次画之前、画布换了大小、换了 QRhi 时 Qt 调。显卡上的东西只在 QRhi 换了才重建。"""
        rhi = self.rhi()
        if not self.renderer.bound_to(rhi):
            self.release()
            self.renderer.init(rhi, cb)

    def render(self, cb) -> None:
        if self._shoot_now(cb):
            return
        self._collect()
        target = self.renderTarget()
        if self.frame is None:
            cb.beginPass(target, CLEAR, QRhiDepthStencilClearValue(1.0, 0))     # 画空的
            cb.endPass()
        else:
            ask, self._ask = self._ask, None
            rect = self._hit_rect(ask) if ask is not None else None
            self.renderer.draw(cb, target, self.width(), self.height(), self.devicePixelRatioF(), self.frame, twice=TWICE, probe=rect)
            self._reading = rect is not None
        self._count_frame()

    def releaseResources(self) -> None:
        self.release()

    def _hit_rect(self, ask: tuple[float, float, float]):
        """要读回的那一点（窗口坐标）在离屏画布上是哪一块；只画了窗口里一块的（frame.region）按那一块算。"""
        x, y, margin = ask
        frame, w, h = self.frame, self.width(), self.height()
        if frame.region is not None:
            rx, rb, rw, rh = frame.region
            x, y, w, h = x - rx, y - (h - rb - rh), rw, rh      # 那一块的左上角在窗口里 (rx, 窗口高 − 底 − 块高)
        return hit_rect(x, y, margin, w, h, self.devicePixelRatioF(), supersample(frame.ppm))

    def release(self) -> None:
        """显卡上的东西全放掉。Qt 要收走 QRhi 时会调（releaseResources）；窗口要销毁之前自己调。"""
        self.renderer.release()
        self.shoot_done()
        self._reading, self._answer = False, None

    # ---- 离屏出图 ----
    def _shooter(self) -> DogRenderer:
        if self._second is None:
            self._second = DogRenderer(self.renderer.model)
        return self._second

    def shoot(self, frame: Frame, width: int, height: int, dpr: float = 1.0, coat: Optional[QImage] = None,
              shooter: Optional[DogRenderer] = None) -> QImage:
        if not self.ready():
            return QImage()
        return super().shoot(frame, width, height, dpr, coat, shooter)

    def shoot_done(self) -> None:
        """这一批图出完了：出图那一套放掉（一张 2048 的毛色贴图在显卡上 20 多 MB）。"""
        if self._second is not None:
            self._second.release()
            self._second = None

    # ---- 点击范围就是狗 ----
    def probe(self, x: float, y: float, margin: float) -> Optional[bool]:
        """窗口里 (x, y)（逻辑像素）周围 margin 像素内有没有狗。答的是上一帧画完时、上一次问的那一点（鼠标一帧挪不了多远）；
        这一次问的记下来，下一帧画完顺手读回（render.hit_rect：读离屏画布上那一小块的 alpha，不重画）。
        鼠标刚进窗口、还没读回过算不是狗；还没画过、没有 RHI（offscreen 单测）返回 None。"""
        if not self.ready():
            return None
        self._collect()
        self._ask = (x, y, margin)
        answer = self._answer
        return answer is not None and answer[0] and time.perf_counter() - answer[1] < HIT_FRESH_S

    def _collect(self) -> None:
        """上一帧读回来的结果这时候到了：收下。"""
        if self._reading:
            self._reading = False
            got = self.renderer.hit()
            self._answer = (got, time.perf_counter()) if got is not None else None

    def _count_frame(self) -> None:
        self.frames += 1
        now = time.perf_counter()
        if now - self.last_report >= 2.0:
            self.fps = self.frames / (now - self.last_report)
            self.frames, self.last_report = 0, now


class Darkroom(_Shooting, QRhiWidget):
    """不上屏的画布，只用来 shoot()。用完 close()。"""

    def __init__(self, model: Model):
        super().__init__(None)
        self.setApi(QRhiWidget.Api.Metal)
        self.renderer = DogRenderer(model)
        # 标成「不上屏」再 show：屏幕上没有这个窗口，但 Qt 当它显示着，给它一个固定的 QRhi。
        # 从不 show 的 QRhiWidget 每 grabFramebuffer() 一次 Qt 就新建一个 QRhi，第二张起显卡上的东西就串了（Qt 6.12）。
        self.setAttribute(Qt.WA_DontShowOnScreen)
        self.resize(16, 16)
        self.show()

    def _shooter(self) -> DogRenderer:
        return self.renderer

    def render(self, cb) -> None:
        if not self._shoot_now(cb):
            cb.beginPass(self.renderTarget(), CLEAR, QRhiDepthStencilClearValue(1.0, 0))
            cb.endPass()

    def releaseResources(self) -> None:
        self.renderer.release()

    def closeEvent(self, event) -> None:
        self.renderer.release()
        super().closeEvent(event)
