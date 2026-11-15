"""狗的毛色和卡片的强调色：四套原贴图（第 1 套是 glb 里嵌的，2 到 4 从 models/texture/ 读，没文件就灰掉）+ 自定义毛色
（widget/coat.py 按斑纹 / 主色 / 副色 / 对调 / 眼睛现算贴图：拖颜色时 30 毫秒合并一次出 1024 的预览贴图，停手出 2048）；
卡片的强调色跟毛色走（贴纸风）：自定义用主色，原装四套用斑纹深色区的平均色，浅色界面里太浅、深色界面里太深就换副色，再不行用描边色。
头像、斑纹图、贴纸要的图借小组件的画布离屏画（dogview.shoot）。参数记在 QSettings：coat = 0 表示自定义，参数在 coat_custom（JSON）。
换同桌时的贴图在后台线程出（_CoatJobs，出好了再淡入）；别的时候当场出。
窗口（widget/window.py）建一个 Look，设置卡片、毛色页、表盘通过窗口的同名方法调过来。"""
from __future__ import annotations

import json
import logging
import math
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from PySide6.QtCore import QByteArray, QCoreApplication, QDataStream, QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QImageReader

import config
from widget import i18n, sticker
from widget.anim import Player
from widget.coat import COMMON_COLORS, THUMB_DARK, THUMB_LIGHT, CoatPainter, CoatSpec, LazyAlbedos, TintPainter, otsu_threshold
from widget.dogctl import Pose
from widget.gltf import IDENTITY, Model, rot_y_mat, table
from widget.packs import IDLE
from widget.render import ELEVATION, DogRenderer, make_frame

HEAD_TALL_M = 0.30     # 头像、斑纹图：画面有多高（米），装得下耳朵尖到胸口的白毛
SIT, SIT_TURN_DEG = "Sitting_loop_1", 30.0   # 「我的同桌」的贴纸：坐着待机的第一帧；侧着坐的那些转这么多度
HEAD_AT = 0.42         # 头骨（后脑勺附近）在画面里离上边多远（占高度的几成）


def visible_accent(q: QColor) -> QColor:
    """强调色要和当前模式的底色拉开：浅色界面里太浅、深色界面里太深的，按它自己反转明度（色相、饱和度不变），再卡进看得见的范围。
    自定义毛色选了黑，开关也要自动变浅，而且不是固定的浅色，是按强调色反过来的（黑 → 很浅的灰，深棕 → 浅棕）。"""
    h, s, l, _ = q.getHslF()
    lo, hi = (0.30, 0.90) if sticker.is_dark() else (0.10, 0.72)
    if lo <= l <= hi:
        return q
    return QColor.fromHslF(max(0.0, h), s, min(hi, max(lo, 1.0 - l)))


def decode_png(data: bytes) -> QImage:
    """模型里嵌的贴图字节 → QImage（按内容认格式：glTF 里也可能是 JPEG）。走 QImageReader：PySide6 解码时放开 GIL，放到后台线程主线程照常走
    （试过：QImage.fromData 不放，后台解 2048 那张主线程照样停 30 多毫秒；QImageReader 最多停 0.8 毫秒）。
    读的设备用 QDataStream 在 C++ 里自己建的那个 QBuffer，不用 Python 建的（查到会卡死：Python 建的 QBuffer，Qt 认格式时在 QImageReader 的全局锁里
    调它的虚函数要拿 GIL，这时别的线程正拿着 GIL 用 QImage.fromData / QImage(路径) 等这把锁，两边一直等，整个程序卡住；单测里撞上过，脚本复现过）。"""
    raw = QByteArray(data)
    stream = QDataStream(raw)                  # raw、stream 活到读完：设备是 stream 的
    return QImageReader(stream.device()).read()


def read_image(path: str) -> QImage:
    """图片文件 → QImage（QImageReader：解码时放开 GIL，同 decode_png）。"""
    return QImageReader(path).read()


def fur_pair(img: QImage) -> tuple[str, str]:
    """一张原贴图的 (深色毛, 浅色毛) 平均色：缩到 48×48，按灰度的大津阈值分成两区各自平均。不碰别的东西，后台线程也能算。"""
    small = img.scaled(48, 48, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_RGB32)
    gray = small.convertToFormat(QImage.Format_Grayscale8)
    cut = otsu_threshold(gray)
    sums = [[0, 0, 0, 0], [0, 0, 0, 0]]                      # 深、浅：r, g, b, 个数
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            acc = sums[0 if gray.pixelColor(x, y).red() < cut else 1]
            acc[0] += c.red()
            acc[1] += c.green()
            acc[2] += c.blue()
            acc[3] += 1
    dark, light = (QColor(r // n, g // n, b // n).name() if n else sticker.INK for r, g, b, n in sums)
    return dark, light


_pool: Optional[ThreadPoolExecutor] = None     # 整个程序一条后台线程（用到才开，worker）
_worker_painters: dict[int, tuple[Model, CoatPainter]] = {}   # 那条线程自己的 CoatPainter，一个模型一份（_worker_painter）


def worker() -> ThreadPoolExecutor:
    """整个程序一条后台线程（用到才开）：出换同桌的贴图（_CoatJobs）、备别的模型（widget/kits.py），一次一件。"""
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="coat")
    return _pool


def forget_model(model: Model) -> None:
    """这个模型不用了（widget/kits.py 的 forget）：出贴图那条线程给它留的遮罩也丢掉。"""
    _worker_painters.pop(id(model), None)


def default_spec_of(pack) -> CoatSpec:
    """这个模型的自定义毛色默认参数（包里 coat_custom.default；没写是边牧那套深灰 + 米白）。"""
    raw = (getattr(pack, "coat_custom", None) or {}).get("default")
    if not isinstance(raw, dict):
        return CoatSpec()
    return CoatSpec.from_json(json.dumps(raw))


def make_painter(model: Model, albedos, pack) -> CoatPainter:
    """这个模型的自定义毛色画笔：包里写了整身一个色（coat_custom.mode = "tint"，萨摩耶）的是 TintPainter，别的按深浅分两色（CoatPainter）。"""
    custom = getattr(pack, "coat_custom", None) or {}
    if custom.get("mode") == "tint":
        return TintPainter(model, albedos, getattr(pack, "brightness", 1.0), int(custom.get("patch_from", 3)))
    return CoatPainter(model, albedos)


def _worker_painter(model: Model, load: Callable[[int], Optional[QImage]], patterns: list[int], pack=None) -> CoatPainter:
    """出贴图那条线程自己的画笔：遮罩（保护区、眼睛、斑纹）算一次留着（每次现算要多 100 毫秒，大多是拿着 GIL 的 Python，
    主线程跟着停 17～31 毫秒）；原贴图每次现解（QImageReader，放开 GIL）、出完就丢。只在那条线程上用，不碰主线程的 Look.painter()。"""
    entry = _worker_painters.get(id(model))
    if entry is None or entry[0] is not model:
        entry = _worker_painters[id(model)] = (model, make_painter(model, LazyAlbedos(load, patterns), pack))
    entry[1].albedos = LazyAlbedos(load, patterns)
    return entry[1]


FACE_GAP_MS = 34   # 毛色头像画完一张隔这么久（约两帧）再画下一张（Look.coat_faces）


class _CoatJobs(QObject):
    """换同桌时出贴图的后台线程（量的：2048 的 PNG 解码一次 30～90 毫秒、自定义的现算 40～160 毫秒，放在主线程上，
    「我的同桌」滑到位的那一下整张卡片停住）。一次只做一件；又换了一只，前面那件做完也不用（按号认）。
    后台只用 work 带进去的东西（模型、PNG 字节、文件路径、参数），自己解码、自己建 CoatPainter，不碰主线程的缓存。"""
    landed = Signal(int, object)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._ticket = 0
        self._then: Optional[tuple[int, Callable]] = None     # (号, 回到主线程以后拿结果做的事)
        self._future: Optional[Future] = None
        self.landed.connect(self._land)

    def pending(self) -> bool:
        return self._then is not None

    def start(self, work: Callable[[], object], then: Callable[[object], None]) -> None:
        """work() 在后台线程跑；做完回到主线程调 then(结果)（work 出错结果是 None）。前面没做完的那件作废。"""
        self._ticket += 1
        ticket = self._ticket
        self._then = (ticket, then)

        def run() -> None:
            result = None
            if ticket == self._ticket:                   # 排队的时候又换了一只：不用做了
                try:
                    result = work()
                except Exception:                        # noqa: BLE001 —— 出不来就当没有，回主线程照常收尾
                    logging.getLogger("look").exception("coat job failed")
            try:
                self.landed.emit(ticket, result)
            except RuntimeError:                         # 窗口已经关了
                pass

        self._future = worker().submit(run)

    def drop(self) -> None:
        """手上那件不要了（它的 then 也不调）。"""
        self._ticket += 1
        self._then = None

    def _land(self, ticket: int, result) -> None:
        if self._then is None or self._then[0] != ticket:
            return
        then = self._then[1]
        self._then = None
        then(result)

    def settle(self) -> None:
        """等手上那件做完、当场收尾（当场换毛色之前、单测）。"""
        while self._then is not None and self._future is not None:
            future = self._future
            future.result()
            QCoreApplication.sendPostedEvents(self, QEvent.MetaCall)
            if self._future is future and self._then is not None:   # 结果没送到（不该发生）：别一直等
                self._then = None


class Look:
    def __init__(self, window, model: Model, prefs) -> None:
        self.w, self.model, self.prefs = window, model, prefs
        self._coat_dark: dict[int, Optional[tuple[str, str]]] = table(model, "coat_dark")   # 四套原贴图的 (深色毛, 浅色毛) 平均色（色块、卡片强调色用），算一次记在模型上
        self.coat = 1                             # 1..4 四套原贴图，0 = 自定义（coat_spec）
        self.coat_spec = CoatSpec.from_json(prefs.get("coat_custom"), self.default_spec())
        self._coat_painter: Optional[CoatPainter] = None   # 主线程自定义毛色用的（遮罩算一次留着）：也记在模型上（painter）
        self._wearing: Optional[tuple] = None     # 狗身上现在这张：("coat", i) / ("custom", 参数) / ("preview", 参数)；一样的不用重出
        self._jobs = _CoatJobs(window)
        self._face_jobs = _CoatJobs(window)       # 毛色头像要的贴图在后台解（coat_faces），和换同桌的那件分开认号
        self._accent_last = sticker.INK           # 上一次算出来的强调色：换同桌的贴图还在后台出时先用它（accent_color）

    def use_model(self, model: Model) -> None:
        """换了模型（换模型不重启，window._use_kit）：模型换成这一只；四套的深浅两色、自定义毛色的遮罩用这个模型自己的那份（记在模型上，换回来不重算）；
        身上这张记成「不知道」——两只都是第 1 套时也得重出（不然当成「和身上一样」，新身子一直贴着上一只的贴图）。接着窗口叫 reload 出这只的贴图。"""
        self.model = model
        self._coat_dark = table(model, "coat_dark")
        store = getattr(model, "measured", None)
        self._coat_painter = store.get("coat_painter") if store is not None else None
        self._wearing = None

    def restore(self) -> None:
        """启动时按记着的设置换上贴图（窗口的画布建好之后调）。"""
        saved_coat = self.prefs.get("coat")
        if saved_coat == 0 and self.painter() is None:
            self.set_coat(1)                         # 记着自定义、这个模型却没法自定义（包里 custom_coat 是假的、模型没嵌贴图）：第一套，并记回去
        elif saved_coat == 0:
            self.set_custom_coat(self.coat_spec, preview=False)
        else:
            self.set_coat(saved_coat)

    def reload(self, then: Callable[[], None]) -> None:
        """换了一只同桌（window._enter_pet）：按它那一份设置换上毛色；它记的那套贴图不在了就用第一套。
        号（self.coat、coat_spec）当场就是新的；贴图在后台线程出（_CoatJobs），出好了换上、换好卡片的强调色，再调 then()（窗口在那里淡入、画现在这只的贴纸）。
        和身上这张一样的不用重出，当场 then()。"""
        self.coat_spec = CoatSpec.from_json(self.prefs.get("coat_custom"), self.default_spec())
        key = self._saved_key()
        self.coat = 0 if key[0] == "custom" else key[1]
        if key == self._wearing:
            self._jobs.drop()
            self.apply_accent()
            self.w._dirty = True
            then()
            return
        self._jobs.start(self._work(key), lambda result: self._wear(key, result, then))

    def pending(self) -> bool:
        """换同桌的贴图还在后台出：狗身上、显卡上还是上一只的。"""
        return self._jobs.pending()

    def settle(self) -> None:
        """换同桌的贴图还在后台出：等它出好、当场换上（单测、要马上用身上这张的地方）。"""
        self._jobs.settle()

    def _saved_key(self) -> tuple:
        """这只同桌记的毛色：("custom", 参数) 或 ("coat", i)。那套贴图不在了、模型没嵌贴图没法自定义，就是第一套，并记回去。"""
        saved = self.prefs.get("coat")
        if saved == 0 and self.model.texture_png and self.w.pack.custom_coat:
            return ("custom", self.coat_spec.to_json())
        i = max(1, min(len(self.coat_names()), int(saved or 1)))
        if i != 1 and not self.coat_available()[i - 1]:
            i = 1
        if i != saved:
            self.prefs.set("coat", i)
        return ("coat", i)

    def _work(self, key: tuple) -> Callable[[], tuple]:
        """key 那张贴图在后台线程怎么出：(贴图, 深浅两色或 None)。只带走不会变的东西，不碰 self。"""
        model, png, pack = self.model, self.model.texture_png, self.w.pack
        files = {i: str(self._coat_dir() / name)
                 for i, (name, ok) in enumerate(zip(self.coat_names(), self.coat_available()), start=1) if i > 1 and ok}

        def load(i: int) -> Optional[QImage]:
            if i == 1:
                return decode_png(png) if png else None
            return read_image(files[i]) if i in files else None

        if key[0] == "custom":
            spec = CoatSpec.from_json(key[1], self.default_spec())

            def work() -> tuple:
                painter = _worker_painter(model, load, [1, *files], pack)
                try:
                    return painter.paint(spec, 2048), None
                finally:
                    painter.albedos = LazyAlbedos(load, [])      # 解出来的原贴图（16 MB）不留
            return work
        i, known = key[1], key[1] in self._coat_dark

        def work() -> tuple:
            img = load(i)
            ok = img is not None and not img.isNull()
            return img, (fur_pair(img) if ok and not known else None)
        return work

    def _wear(self, key: tuple, result, then: Callable[[], None]) -> None:
        """后台出好的贴图回到主线程：换上（第一套是模型自带的，传完照样不留）、换卡片的强调色，再 then()。没出来（文件坏了）换回第一套。"""
        img, pair = result if result is not None else (None, None)
        if img is None or img.isNull():
            if key != ("coat", 1):
                self.coat = 1
                self.prefs.set("coat", 1)
            key, img = ("coat", 1), None
        if key[0] == "coat" and pair is not None:
            self._coat_dark.setdefault(key[1], pair)
        renderer = self.w.view.renderer
        if key == ("coat", 1):
            renderer.set_coat(None, once=img)
            if img is not None:
                for ghost in self.w.drawing_ghosts():         # 正画着另一半狗的每块屏的窗口也带上解好的这张（不然它在主线程上再解一遍）；没在画的等它第一次画时自己解
                    ghost.view.renderer.set_coat(None, once=img)
        else:
            renderer.set_coat(img)                            # 每块屏的窗口下一帧照主画布的拿同一张（window._sync_ghost）
        self._wearing = key
        self.apply_accent()
        self.w._dirty = True
        then()

    # ---- 四套原贴图 ----
    def coat_names(self) -> tuple[str, ...]:
        return self.w.pack.coats or (config.COATS[0],)

    def _coat_dir(self):
        return self.w.pack.coat_dir or config.COAT_DIR

    def coat_available(self) -> list[bool]:
        return [True] + [(self._coat_dir() / name).is_file() for name in self.coat_names()[1:]]

    def coat_image(self, i: int) -> Optional[QImage]:
        if i <= 1:
            return decode_png(self.model.texture_png) if self.model.texture_png else None
        path = self._coat_dir() / self.coat_names()[i - 1]
        return QImage(str(path)) if path.is_file() else None

    def known_swatches(self) -> list[Optional[tuple[str, str]]]:
        """每套算过的深浅两色，没算过的 None（不解贴图）：换了模型以后重建毛色那一行时用（狗正在淡入，主线程上不解 2048 的图）。"""
        return [self._coat_dark.get(i) for i in range(1, len(self.coat_names()) + 1)]

    def coat_swatches(self) -> list[Optional[tuple[str, str]]]:
        """每套毛色的 (深色毛, 浅色毛) 平均色，给 Settings 的色块画上深下浅（整张贴图的平均色，
        第一套平均出来是 #6a686d，狗身上是 #272730 和 #aaa6a8）。贴图不在的是 None。"""
        return [self._fur_pair(i) for i in range(1, len(self.coat_names()) + 1)]

    def set_coat(self, i: int) -> None:
        """选四套原贴图之一（0 交给 set_custom_coat）。当场换：先把换同桌还没出好的那张收尾，不然它后到、把这次选的盖掉。"""
        self._jobs.settle()
        i = max(1, min(len(self.coat_names()), int(i)))
        img = None if i == 1 else self.coat_image(i)
        if i != 1 and (img is None or img.isNull()):
            return                                   # 贴图文件不在（没放 models/texture），忽略
        self.coat = i
        self.prefs.set("coat", i)
        self.w.view.renderer.set_coat(img)
        self._wearing = ("coat", i)
        self.apply_accent()
        self.w._dirty = True

    # ---- 自定义 ----
    def custom_json(self) -> str:
        return self.coat_spec.to_json()

    def painter(self) -> Optional[CoatPainter]:
        if self._coat_painter is None:
            if not self.model.texture_png or not self.w.pack.custom_coat:
                return None                      # 模型里没嵌贴图、包里写了不能自定义：没法自定义
            have = [i for i, ok in enumerate(self.coat_available(), start=1) if ok]
            self._coat_painter = make_painter(self.model, LazyAlbedos(self.coat_image, have), self.w.pack)   # 原贴图用到才解码，只留一张；通体一色的萨摩耶是 TintPainter
            store = getattr(self.model, "measured", None)
            if store is not None:
                store["coat_painter"] = self._coat_painter          # 换模型再换回来不重算遮罩（use_model）
        return self._coat_painter

    def set_custom_coat(self, spec: CoatSpec, preview: bool = False) -> None:
        """自定义毛色：按 spec 现算贴图换上。preview 用 1024（拖颜色时每次十来毫秒），定稿用 2048。记成 coat=0 + coat_custom。"""
        self._jobs.settle()
        painter = self.painter()
        if painter is None:
            return
        self.coat_spec = CoatSpec(**vars(spec))
        self.coat = 0
        self.prefs.set("coat", 0)
        self.prefs.set("coat_custom", self.coat_spec.to_json())
        self.w.view.renderer.set_coat(painter.paint(self.coat_spec, 1024 if preview else 2048))
        self._wearing = ("preview" if preview else "custom", self.coat_spec.to_json())
        if not preview:
            self.apply_accent()                  # 拖颜色时不换：每 30 毫秒重套一遍样式表太费
        self.w._dirty = True

    # ---- 强调色 ----
    def accent_color(self) -> str:
        """卡片的强调色跟毛色走：自定义毛色用主色（对调了就是副色），原装四套用斑纹深色区的平均色；
        和当前模式的底色太接近的（浅色界面里太浅、深色界面里太深）按它自己反转明度（visible_accent），不是退回固定的黑 / 米白。"""
        if self.coat == 0:
            spec = self.coat_spec
            c = spec.secondary if spec.swap else spec.main
        else:
            if self.coat not in self._coat_dark and self.pending():
                return self._accent_last                  # 换同桌的贴图还在后台出（深浅两色和它一起算）：先用原来的，不在主线程上解 2048 的图（「···」每帧要，一帧卡 26 毫秒）
            c = self._dark_color(self.coat)
        q = QColor(c)
        self._accent_last = visible_accent(q).name() if q.isValid() else sticker.INK
        return self._accent_last

    def _dark_color(self, i: int) -> str:
        """第 i 套原贴图里深色毛的平均色（强调色用）。"""
        pair = self._fur_pair(i)
        return pair[0] if pair is not None else sticker.INK

    def _fur_pair(self, i: int) -> Optional[tuple[str, str]]:
        """第 i 套原贴图的 (深色毛, 浅色毛) 平均色：缩到 48×48，按灰度的大津阈值分成两区各自平均。贴图不在返回 None。"""
        if i not in self._coat_dark:
            img = self.coat_image(i)
            self._coat_dark[i] = fur_pair(img) if img is not None and not img.isNull() else None
        return self._coat_dark[i]

    def apply_accent(self) -> None:
        color = self.accent_color()
        for p in self.w.panels():
            if p is not None:
                p.set_accent(color)

    # ---- 头像、斑纹图：头和脖子的特写 ----
    def _head_frame(self, width: int, height: int):
        """特写用的一帧：站着待机的第一帧（眼睛睁着）、正对着你，画面高 HEAD_TALL_M 米，头骨在 HEAD_AT 的高度。
        模型包可以改这三样（pack.json 的 head_shot：萨摩耶站着时卷在背上的尾巴在两耳之间露一团，改成坐着拍、画面放大一点）。
        四套的差别都在头、脖子上，以前画趴着的整只狗（头才十几个像素宽）看不出来。
        不碰显卡，单测跑得到。"""
        shot = self.w.pack.head_shot
        player = Player(self.model)
        player.play(shot.get("clip", IDLE), loop=False, fade=0.0)
        player.update(0.0)
        g = player.globals(IDENTITY)
        m = g[self.model.node_by_name("head").index]
        ppm = height / shot.get("tall_m", HEAD_TALL_M)
        e = math.radians(ELEVATION)
        ground = height * (1.0 - shot.get("at", HEAD_AT)) - (m[13] * math.cos(e) - m[14] * math.sin(e)) * ppm
        return make_frame(Pose(IDENTITY, player.joint_matrices_from(g), g, [], 0.0), 0.0, ppm, ground, width, (-m[12] * ppm, 0.0))

    def _head_shots(self, width: int, height: int, coat_for) -> dict[int, QImage]:
        """每套各渲一张特写：coat_for(i) 给第 i 套要贴的图（None = 模型自带的）。借小组件的画布离屏画（dogview.shoot），
        窗口里那一帧和它的贴图不动。画布还没好（程序刚启动、单测的 offscreen 平台）就返回空。"""
        view = self.w.view
        if not view.ready():
            return {}
        frame = self._head_frame(width, height)
        out: dict[int, QImage] = {}
        try:
            for i, ok in enumerate(self.coat_available(), start=1):
                if not ok:
                    continue
                img = view.shoot(frame, width, height, coat=coat_for(i))
                if not img.isNull():
                    out[i] = img
        finally:
            view.shoot_done()
        return out

    def coat_thumbnails(self, width: int, height: int) -> dict[int, QImage]:
        """四套毛色本来的样子，各一张小狗头像，一口气画完（当场要的地方用；卡片里选毛色那一行用 coat_faces，一帧一张）。"""
        return self._head_shots(width, height, lambda i: None if i == 1 else self.coat_image(i))

    def coat_faces(self, width: int, height: int, deliver: Callable[[int, QImage], None], done: Callable[[], None]) -> Callable[[], None]:
        """四套毛色各一张小狗头像，一帧一张（卡片里选毛色那一行，以前四张一口气画——主线程上解 3～4 张 2048 的贴图、
        再画 4 张，真机上一帧 160～180 毫秒，开卡片、换了模型以后各来一下）：第 i 套的贴图在后台线程解（_face_jobs），解好了回主线程
        借小组件的画布画一张（约 15 毫秒），deliver(i, 图)，隔 FACE_GAP_MS 再下一张；都画完 done()。画布还没好（刚启动、单测）什么都不画，
        下一轮事件循环里 done()。返回一个函数：叫它就不画了（换了模型、那一行重建了）。"""
        view = self.w.view
        live = {"on": True}
        if not view.ready():
            QTimer.singleShot(0, lambda: live["on"] and done())
            return lambda: live.update(on=False)
        todo = [i for i, ok in enumerate(self.coat_available(), start=1) if ok]
        png = self.model.texture_png
        files = {i: str(self._coat_dir() / name)
                 for i, (name, ok) in enumerate(zip(self.coat_names(), self.coat_available()), start=1) if i > 1 and ok}
        frame = self._head_frame(width, height)
        jobs = self._face_jobs

        def load(i: int) -> Optional[QImage]:
            if i == 1:
                return decode_png(png) if png else None            # 模型自带的那套也在后台解：交给画的那一套，它就不在主线程上自己解
            return read_image(files[i]) if i in files else None

        def step() -> None:
            if not live["on"]:
                return
            if not todo:
                live["on"] = False
                view.shoot_done()
                done()
                return
            i = todo.pop(0)
            jobs.start(lambda: load(i), lambda img: shoot(i, img))

        def shoot(i: int, img: Optional[QImage]) -> None:
            if not live["on"]:
                return
            if view.ready() and img is not None and not img.isNull():
                try:
                    shot = view.shoot(frame, width, height, coat=img)
                except Exception:                                  # noqa: BLE001 —— 一张画不出来不挡别的，留着两色圆点
                    logging.getLogger("coat").exception("coat face %d failed", i)
                    shot = QImage()
                if not shot.isNull():
                    deliver(i, shot)
            QTimer.singleShot(FACE_GAP_MS, step)

        def cancel() -> None:
            if live["on"]:
                live["on"] = False
                jobs.drop()
                view.shoot_done()
        step()
        return cancel

    def pattern_thumbnails(self, width: int, height: int) -> dict[int, QImage]:
        """每种斑纹分布各一张（固定深灰 / 米白，只看分布），给自定义毛色页：深浅两色的四套是头和脖子的特写；通体一色的（萨摩耶，纯色 / 背上一片）
        是整只侧着站（差别在背上）。"""
        painter = self.painter()
        if painter is None:
            return {}
        if self.coat_mode() == "tint":
            return self._body_shots(width, height, lambda i: painter.paint(CoatSpec(i, THUMB_LIGHT, THUMB_DARK), 512))
        return self._head_shots(width, height, lambda i: painter.paint(CoatSpec(i, THUMB_DARK, THUMB_LIGHT), 512))

    def _body_shots(self, width: int, height: int, coat_for) -> dict[int, QImage]:
        """每种斑纹各一张整只侧着站的（通体一色的模型的斑纹图）。画布没好就是空的。"""
        view = self.w.view
        if not view.ready():
            return {}
        frame = self._body_frame(width, height)
        out: dict[int, QImage] = {}
        try:
            for i, ok in enumerate(self.custom_pattern_slots(), start=1):
                if not ok:
                    continue
                img = view.shoot(frame, width, height, coat=coat_for(i))
                if not img.isNull():
                    out[i] = img
        finally:
            view.shoot_done()
        return out

    def _body_frame(self, width: int, height: int):
        """整只站着待机的第一帧，四分之三侧着（210°，和平时待着一样），装得下整只（按模型的身高定比例尺）。不碰显卡。"""
        player = Player(self.model)
        player.play(IDLE, loop=False, fade=0.0)
        player.update(0.0)
        g = player.globals(IDENTITY)
        tall = max(0.3, float(getattr(self.w.pack, "height_m", 0.75) or 0.75))
        ppm = min(height / (1.25 * tall), width / (1.45 * tall))
        return make_frame(Pose(rot_y_mat(90.0 + 210.0), player.joint_matrices_from(g), g, [], 0.0), 0.0, ppm, 0.12 * height, width, (0.0, 0.0))

    # ---- 自定义毛色按模型（包里 coat_custom） ----
    def coat_mode(self) -> str:
        """自定义毛色怎么分："pattern" 按深浅分两色（边牧），"tint" 整身一个色 + 可选背上一片（萨摩耶）。"""
        return str((self.w.pack.coat_custom or {}).get("mode", "pattern"))

    def custom_pattern_slots(self) -> list[bool]:
        """自定义页有几种斑纹、各能不能选：深浅两色的是四套原贴图（文件在才能选），通体一色的是包里写的那几种。"""
        if self.coat_mode() == "tint":
            return [True] * max(1, len((self.w.pack.coat_custom or {}).get("patterns", ())) or TintPainter.PATTERNS)
        return self.coat_available()

    def common_colors(self) -> tuple:
        """自定义页的「常用颜色」：包里给了用包的（萨摩耶只给自然的毛色，跳的颜色从取色器选），没给用 COMMON_COLORS。"""
        given = (self.w.pack.coat_custom or {}).get("common_colors")
        try:
            pairs = tuple((str(a), str(b)) for a, b in given) if given else ()
        except (TypeError, ValueError):
            pairs = ()
        return pairs or COMMON_COLORS

    def default_spec(self) -> CoatSpec:
        return default_spec_of(self.w.pack)

    # ---- 「我的同桌」滑动条上的贴纸要的图 ----
    def _coat_for(self, coat: int, custom: str) -> Optional[QImage]:
        """另一只同桌记的毛色 → 要贴的图（None = 模型自带的第一套）。"""
        if coat == 0:
            painter = self.painter()
            return painter.paint(CoatSpec.from_json(custom, self.default_spec()), 1024) if painter is not None else None
        return None if coat <= 1 else self.coat_image(coat)

    def _kit_coat(self, kit, coat: int, custom: str) -> Optional[QImage]:
        """别的模型那只同桌记的毛色 → 要贴的图（None = 它模型自带的第一套）：那个包的贴图文件；自定义的用它自己的画笔
        （遮罩算一次，记在那个模型上；原贴图照那个包的文件读，不借现在这只的）。"""
        model, pack = kit.model, kit.pack
        names = pack.coats or (config.COATS[0],)
        folder = pack.coat_dir or config.COAT_DIR
        if coat == 0:
            if not (model.texture_png and pack.custom_coat):
                return None
            painter = model.measured.get("sticker_painter")
            if painter is None:
                files = {i: folder / name for i, name in enumerate(names, start=1) if i > 1 and (folder / name).is_file()}

                def load(i: int) -> Optional[QImage]:
                    return decode_png(model.texture_png) if i <= 1 else (read_image(str(files[i])) if i in files else None)
                painter = model.measured["sticker_painter"] = make_painter(model, LazyAlbedos(load, [1, *files]), pack)
            return painter.paint(CoatSpec.from_json(custom, default_spec_of(pack)), 1024)
        path = folder / names[coat - 1] if 1 < coat <= len(names) else None
        return QImage(str(path)) if path is not None and path.is_file() else None

    def _sit_frame(self, px: int, ppm: float, ground: float, turned: bool, model: Optional[Model] = None):
        """坐着的整只（坐着待机的第一帧）：正对着你，或者稍微侧一点。model：别的模型的那只（不给是现在这个模型）。不碰显卡。"""
        player = Player(model or self.model)
        player.play(SIT, loop=False, fade=0.0)
        player.update(0.0)
        g = player.globals(IDENTITY)
        root = rot_y_mat(SIT_TURN_DEG) if turned else IDENTITY
        return make_frame(Pose(root, player.joint_matrices_from(g), g, [], 0.0), 0.0, ppm, ground, px)

    def pet_shots(self, wanted: list, px: int, ppm: float, ground: float, kit=None) -> dict[str, QImage]:
        """每只一张坐着的整只、透明底（widget/petstrip.py 再剪成贴纸）。wanted 的每一项：(号, (毛色编号, 自定义参数) 或 None = 现在身上这套, 侧不侧)。
        借小组件的画布离屏画（dogview.shoot）；画布还没好返回空。kit：别的模型的同桌（那个模型在后台备好了，widget/kits.py）——
        另起一套照它的模型建的渲染器画、画完放掉，毛色照那个包的（_kit_coat；第一套是它模型自带的，现解一张，和同一个模型的别的同桌一样）。"""
        view = self.w.view
        if not wanted or not view.ready():
            return {}
        if kit is not None:
            shooter = DogRenderer(kit.model)
            out: dict[str, QImage] = {}
            try:
                for key, look, turned in wanted:
                    img = view.shoot(self._sit_frame(px, ppm, ground, turned, kit.model), px, px, coat=self._kit_coat(kit, *look), shooter=shooter)
                    if not img.isNull():
                        out[key] = img
            finally:
                shooter.release()                      # 显卡上的东西得在画布没了之前放掉，不留着
            return out
        if self._jobs.pending() and any(look is None for _key, look, _turned in wanted):
            self.settle()                        # 换同桌的贴图还没换上：身上还是上一只的，先等它（会顺带让卡片跟上）
        wearing = view.renderer.coat_image
        out: dict[str, QImage] = {}
        try:
            for key, look, turned in wanted:
                coat = self._coat_for(*look) if look is not None else wearing
                img = view.shoot(self._sit_frame(px, ppm, ground, turned), px, px, coat=coat)
                if not img.isNull():
                    out[key] = img
        finally:
            view.shoot_done()
        return out

    # ---- 每套叫什么（包里写的，pack.json 的 coat_notes） ----
    def coat_label(self, i: int) -> str:
        """第 i 套毛色的名字（头像下面那行）；包里没写就是编号。"""
        return self._note(i, "name") or str(i)

    def pattern_note(self, i: int) -> str:
        """第 i 套斑纹和别的差在哪（自定义页每张图下面那句）；包里没写就空着。通体一色的照 coat_custom.patterns 里那一种的名字和那一句。"""
        if self.coat_mode() == "tint":
            patterns = (self.w.pack.coat_custom or {}).get("patterns", ())
            entry = patterns[i - 1] if 0 < i <= len(patterns) and isinstance(patterns[i - 1], dict) else {}
            lang = i18n.current()
            name = (entry.get("name") or {}).get(lang) or (entry.get("name") or {}).get("en") or ""
            note = (entry.get("note") or {}).get(lang) or (entry.get("note") or {}).get("en") or ""
            return " · ".join(x for x in (name, note) if x)
        return self._note(i, "pattern")

    def _note(self, i: int, key: str) -> str:
        notes = self.w.pack.coat_notes
        text = notes[i - 1].get(key, {}) if 0 < i <= len(notes) else {}
        return text.get(i18n.current()) or text.get("en") or ""
