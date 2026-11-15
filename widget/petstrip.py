"""「我的同桌」滑动条：设置主页面和详情页上，卡片顶部栏下面那一条，只画桌沿那一带。
几只同桌是沿轮廓剪下来的贴纸（坐着的上半身），并排坐在一条弧形的桌沿后面；桌沿和狗都钉在一个圆心在下面的大圆上，滑动 = 整个盘绕圆心转。
正中那只最大、正着、带纸片影；旁边的顺着弧歪过去、小一号，名字是灰色小字。桌沿是固定的、左右对称的一段弧，下面一排小圆点（_paint_dots）：
一只一个，正中那只的深，最后一个小「+」。小圆点只导航：点哪只的点就转过去、换成它，点「+」的点转到「+」，都不进详情页、添加页
（和点旁边那只一样）；正中这一格自己的点点了不动、悬停也不变；别的点悬停时慢慢长大一圈、变深，按着缩一点。点的范围比点本身大（dot_at）。最后一格是「+」：和同桌一个规矩，在旁边时点它只转到正中，到了正中再点才去添加页。
正中那只的名字不在这里画（card.TitleBar）：这一条告诉卡片正中是哪一格（center、center_changed），卡片把它写进顶部栏的名字胶囊。
那颗胶囊算正中那一格的一部分（一个整体）：鼠标在狗上或胶囊上，两样一起抬（同一根弹簧 _lift，lift_changed 告诉卡片抬多少）；
点哪个都是 activate_center（同桌进详情页，「+」进添加页）。

怎么滑：左右拖（跟着手走，松手吸到最近的一格）、点旁边那只、滚轮和触摸板（一次动作换一只，widget/wheel.py）。每过一只 tick 一声（界面音效）。
换同桌（立马切，不等；狗渐隐渐显）：点旁边那只、松手、滚轮或触摸板翻一只的那一刻桌面上的狗就开始淡出（window.fade_dog），滑到位就换
（window.switch_pet：同一个模型、别的模型都当场换，再淡入；别的模型在卡片打开后就在后台备着，go 的时候还没备的也开始备）。弹簧只在最后要停的那一格到位，所以一路滑过去不会挨个换。
点正中那只：进它的详情页（毛色、删除都在那）。详情页顶上还是这一条（set_focus）：
正中这只放大一圈、往下坐一点，别的往两边退开淡掉（返回在顶部栏左边的圆里）。删的那只缩回桌沿后面、后面的补过来；新添的从桌沿后面冒出来。

这里只管画和手势。名单、每只的名字和毛色问窗口（pets / pet_name / pet_look / pet_shots），画贴纸要的整只狗也是窗口借狗的画布离屏画的；
画布还没好（单测里一直没有）画不出来，用一个圆点顶着；别的模型的同桌在它的模型备好（widget/kits.py）之前用模型包的缩略图，备好了照它自己的毛色画。"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from widget import sounds, sticker
from widget.animation import Spring
from widget.wheel import WheelSteps
from widget.widgets import drive

# ---- 版面（这一条自己的坐标：左上角在卡片内容区的左上角、紧贴顶部栏下面，宽就是内容区的宽）
HEIGHT = 120                  # 顶部栏下沿到桌沿那一带的底；下面到第一行再空 GAP（这一条占 HEIGHT + GAP = 132）。
GAP = 12
RADIUS = 185.0                # 大圆的半径：桌沿的中线、狗的切口都在这个圆上
STEP = 26.0                   # 相邻两只隔多少度
YC = 72.0                     # 桌沿中线最高那一点的 y（大圆的圆心在它正下方 RADIUS）：正中那只头顶离顶部栏 12。
                              # 最挤的两种：主页面鼠标放上去（狗往外抬 3、大 4%，名字胶囊同时往上抬 3）头顶离胶囊下沿约 9.6；详情页放大 1.25（不抬）约 9；
                              # 都不少于原来平时的 8（test_pets 量着）。别再往上挪（这一条的顶就是滚动区的顶，出去的会被裁）
HEAD_W = 42.0                 # 正中那只头（连耳朵）的宽
VISIBLE = 60.0                # 从头顶往下留多高（头 + 胸口）
SIDE_SCALE = 0.78             # 旁边一格缩到多少（描边跟着细）
FADE_FROM, FADE_TO = 1.0, 1.18    # 离正中几格开始淡、几格淡没
BAND = 10.0                   # 桌沿的宽（连描边）
ARC = 1.32                    # 桌沿左右各画到离正中几格（再远的同桌已经淡没了）
SIDE_TEXT_MAX = 40.0          # 旁边的名字最宽多少
NAME_CLEAR = 4.0              # 旁边的名字离桌沿下边至少多少
ADD_R0, ADD_R1 = 18.0, 15.0   # 添加格那个虚线圆的半径：正中 / 旁边
ADD_TUCK = 5.0                # 虚线圆的下沿藏进桌沿后面多少（像空着的座位，不是浮在桌沿上面的按钮）
DOT_DY, DOT_GAP = 25.0, 13.0  # 桌沿下面那排小圆点：在桌沿中线下面多少、相邻两个隔多少
DOT_SPAN = 88.0               # 那一排最宽多少（同桌多了点挨近、一起变小）：不伸到旁边两只的灰色名字下面
DOT_HIT_H, DOT_HIT_OUT = 18.0, 8.0   # 点小圆点的范围：高 18；每个点左右到和旁边那个的正中，两头再往外 8（点本身才 5～7）
DOT_HOVER_INK = 0.6           # 鼠标放在小圆点上：深到几成（要有悬停的动效，和狗抬起来同一根弹簧 LIFT_S，慢慢长大一圈、变深）
DOT_PRESS_S, DOT_PRESS_SHRINK = 0.075, 0.18   # 按着小圆点：缩一点（和按钮按下一样快）
# ---- 详情页、添加、删除
FOCUS_DROP = 12.0             # 详情页上桌沿往下坐多少（坐进下面那 GAP 里），给放大的那只腾地方
FOCUS_SCALE = 1.25            # 详情页上正中那只放大到多少（再大头顶出这一条了）
FOCUS_PUSH = 0.55             # 别的往两边退开多少格
FOCUS_S = 0.32                # 进出详情页的弹簧
LIFT_PX, LIFT_SCALE, LIFT_S = 3.0, 1.04, 0.16   # 鼠标在正中那一格或顶部栏它的名字上：狗往外抬多少、大多少（告诉人能点；名字胶囊跟着往上抬同样的 LIFT_PX、不放大）
SINK_PX = 46.0                # 删掉的那只往桌沿后面缩多少；新添的从这么深的地方冒出来
RISE_DELAY_S = 0.16           # 新添的等换页淡入过半再冒
BLEND_S = 0.25                # 换毛色：旧贴纸淡成新的
NO_GAP = 1 << 30
# ---- 手感
SLOT_PX = RADIUS * math.sin(math.radians(STEP))   # 鼠标拖这么多像素 = 一格（狗差不多跟着手走）
DRAG_START_PX = 4.0           # 按下后挪这么多才算拖
OVER = 0.22                   # 两头最多拖过头多少格（松手弹回）
RESPONSE_S = 0.28             # 滑到位的弹簧
COMMIT_NEAR = 0.01            # 离要停的那一格只差这么多（不到 1 像素）就换同桌：比弹簧完全停稳早约 0.08 秒，换的那一下卡的是已经看不出在动的最后一点
CENTER_HALF = 0.42            # 离一格的正中多少格以内算点在这一格上（slot_at；正中那一格悬停、点它也按这个）
# ---- 贴纸
SS = 4                        # 备图的倍数
FMT = QImage.Format_ARGB32_Premultiplied
MARGIN = 6.0                  # 贴纸画布四周留的空，够放描边
SHOT_PX, SHOT_PPM, SHOT_GROUND = 640, 700.0, 24.0   # 窗口给的整只狗：画布多大、一米多少像素、地面离底多少
_ALPHA = bytes(0 if a <= 8 else 1 for a in range(256))


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def smooth(u: float) -> float:
    u = clamp(u)
    return u * u * (3.0 - 2.0 * u)


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def font(px: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def ink(color, alpha: float) -> QColor:
    q = QColor(color)
    q.setAlphaF(clamp(q.alphaF() * alpha))
    return q


# ---------------------------------------------------------------- 贴纸
def tinted(img: QImage, color) -> QImage:
    """有东西的地方全涂成 color，透明度照旧（剪影）。"""
    out = QImage(img.size(), FMT)
    out.fill(Qt.transparent)
    q = QPainter(out)
    q.drawImage(0, 0, img)
    q.setCompositionMode(QPainter.CompositionMode_SourceIn)
    q.fillRect(out.rect(), QColor(color))
    q.end()
    return out


def grown(img: QImage, px: float, color, steps: int = 28) -> QImage:
    """img 的剪影往外长 px 个逻辑像素，涂成 color（沿轮廓的描边就是它）；尺寸和 img 一样，四周要留够 px 的空。"""
    t = tinted(img, color)
    out = QImage(img.size(), FMT)
    out.fill(Qt.transparent)
    q = QPainter(out)
    for ring in (1.0, 0.5):
        for k in range(steps):
            a = 2.0 * math.pi * k / steps
            q.drawImage(QPointF(math.cos(a) * px * SS * ring, math.sin(a) * px * SS * ring), t)
    q.drawImage(0, 0, t)
    q.end()
    return out


def _half(img: QImage) -> QImage:
    return img.scaled(max(1, img.width() // 2), max(1, img.height() // 2), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


class Sticker:
    """一张做好的贴纸。body：SS 倍的图，描边和狗都画在里面；anchor：定位点在图里的逻辑坐标。影子是 body 整块的剪影。
    备 4 / 2 / 1 倍三档，画的时候挑合适的一档：转着画、缩着画都清楚。"""

    def __init__(self, body: QImage, anchor: QPointF):
        self.w, self.h = body.width() / SS, body.height() / SS
        self.anchor = QPointF(anchor)
        sil = tinted(body, QColor(28, 28, 33, sticker.SHADOW_ALPHA))
        self._body = {4: body, 2: _half(body), 1: _half(_half(body))}
        self._shadow = {4: sil, 2: _half(sil), 1: _half(_half(sil))}

    def draw(self, p: QPainter, x: float, y: float, *, scale: float = 1.0, angle: float = 0.0, opacity: float = 1.0,
             shadow: float = 0.0) -> None:
        """定位点放到 (x, y)；绕定位点转 angle 度、缩 scale 倍（描边跟着细）；shadow 0..1：纸片影露出来多少，方向固定往右下。"""
        if opacity <= 0.004 or scale <= 0.0:
            return
        t = p.deviceTransform()
        need = math.hypot(t.m11(), t.m12()) * scale            # 这一下每个逻辑像素占多少设备像素
        lv = next((n for n in (1, 2, 4) if n >= need - 0.03), 4)
        rect = QRectF(-self.anchor.x(), -self.anchor.y(), self.w, self.h)
        off = sticker.SHADOW_OFFSET
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setOpacity(p.opacity() * opacity)
        for img, k in ((self._shadow[lv], shadow), (self._body[lv], 0.0)):
            if img is self._shadow[lv] and shadow <= 0.004:
                continue
            p.save()
            p.translate(x + off.x() * k, y + off.y() * k)
            if angle:
                p.rotate(angle)
            if scale != 1.0:
                p.scale(scale, scale)
            p.drawImage(rect, img, QRectF(img.rect()))
            p.restore()
        p.restore()


def _rows(img: QImage) -> tuple[bytes, int, int]:
    q = img.convertToFormat(QImage.Format_RGBA8888)
    w, h = q.width(), q.height()
    data = bytes(q.constBits())
    line = q.bytesPerLine()
    if line != w * 4:                                        # 行尾有补齐：去掉
        data = b"".join(data[y * line:y * line + w * 4] for y in range(h))
    return data, w, h


def _span(data: bytes, w: int, y: int) -> Optional[tuple[int, int]]:
    """第 y 行有东西的地方从哪到哪（没有就 None）。"""
    row = data[y * w * 4 + 3:(y + 1) * w * 4:4].translate(_ALPHA)
    x0 = row.find(b"\x01")
    return None if x0 < 0 else (x0, row.rfind(b"\x01"))


def cutout(shot: QImage, origin_x: float, color, *, head_w: float = HEAD_W, visible: float = VISIBLE, outline: float = sticker.OUTLINE) -> Optional[Sticker]:
    """一张整只的狗（透明底）→ 贴纸小狗：头（连耳朵）缩到 head_w 宽，从头顶往下只留 visible 这么高，沿轮廓描一圈 color。
    切口是一条平线（描边在切口下面还多出一点），要拿桌沿盖住。origin_x：狗的原点（身子正中）在图里的 x。
    定位点 = 切口那条线上、头正中和身子正中之间。图是空的返回 None。"""
    data, w, h = _rows(shot)
    spans = {y: s for y in range(h) if (s := _span(data, w, y)) is not None}
    if not spans:
        return None
    top, bottom = min(spans), max(spans)
    left, right = min(s[0] for s in spans.values()), max(s[1] for s in spans.values())
    head = [spans[y] for y in range(top, top + max(1, int((bottom - top) * 0.30))) if y in spans]   # 头：上面三成
    hx0, hx1 = min(s[0] for s in head), max(s[1] for s in head)
    if hx1 <= hx0:
        return None
    k = head_w / float(hx1 - hx0)                            # 图上一个像素 = 多少逻辑像素
    crop = shot.copy(QRect(left, top, right - left + 1, bottom - top + 1)).convertToFormat(FMT)
    big = crop.scaled(max(1, round(crop.width() * k * SS)), max(1, round(crop.height() * k * SS)), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    W, H = math.ceil(crop.width() * k + 2 * MARGIN), math.ceil(visible + 2 * MARGIN)

    def layer(paint) -> QImage:
        img = QImage(W * SS, H * SS, FMT)
        img.fill(Qt.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.SmoothPixmapTransform)
        q.scale(SS, SS)
        paint(q)
        q.end()
        return img

    def dog(q: QPainter) -> None:
        q.setClipRect(QRectF(0, 0, W + 2, MARGIN + visible))
        q.drawImage(QRectF(MARGIN, MARGIN, big.width() / SS, big.height() / SS), big, QRectF(big.rect()))

    shape = layer(dog)
    edge = grown(shape, outline, color)

    def both(q: QPainter) -> None:
        q.drawImage(QRectF(0, 0, W, H), edge, QRectF(edge.rect()))
        dog(q)

    ax = MARGIN + (((hx0 + hx1) / 2.0 - left) * 0.5 + (origin_x - left) * 0.5) * k
    return Sticker(layer(both), QPointF(ax, MARGIN + visible))


def thumb_sticker(image: QImage, color) -> Optional[Sticker]:
    """别的模型的同桌（它的模型还没在后台备好，画不了坐着的样子）：拿模型包的缩略图当贴纸，整张缩到 visible 高，描一圈。"""
    if image.isNull():
        return None
    k = VISIBLE / image.height()
    W, H = math.ceil(image.width() * k + 2 * MARGIN), math.ceil(VISIBLE + 2 * MARGIN)
    big = image.convertToFormat(FMT).scaled(max(1, round(image.width() * k * SS)), round(VISIBLE * SS), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    shape = QImage(W * SS, H * SS, FMT)
    shape.fill(Qt.transparent)
    q = QPainter(shape)
    q.drawImage(QPointF(MARGIN * SS, MARGIN * SS), big)
    q.end()
    body = grown(shape, sticker.OUTLINE, color)
    q = QPainter(body)
    q.drawImage(QPointF(MARGIN * SS, MARGIN * SS), big)
    q.end()
    return Sticker(body, QPointF(W / 2.0, MARGIN + VISIBLE))



class PetStrip(QWidget):
    center_changed = Signal()                 # 正中换了一格（滑过一半）、名单或名字变了：顶部栏的名字跟上（center）
    lift_changed = Signal(float)              # 正中那一格抬起来多少像素（0 … LIFT_PX）：顶部栏的名字胶囊跟着抬

    def __init__(self, card, window):
        super().__init__()
        self.card, self.w = card, window
        self.setFixedHeight(round(HEIGHT + GAP))
        self.setMouseTracking(True)
        self.pets: list = []                  # 名单（prefs.Pet），refresh 时从窗口取
        self.names: list[str] = []
        self.pos = 0.0                        # 正中是第几格（小数）；第 len(pets) 格是「+」
        self.target = 0                       # 要滑到第几格
        self._v = 0.0                         # 弹簧的速度
        self._sliding = False                 # 弹簧在走
        self._early = False                   # 这一趟已经提前换过了（_commit 只提前试一次）
        self._center = 0                      # 正中是哪一格（滑过一半就换）：tick 一声、顶部栏的名字都跟它
        self._stickers: dict[str, tuple[tuple, Optional[Sticker]]] = {}   # 号 → (长相的签名, 贴纸)
        self._press: Optional[QPointF] = None
        self._press_pos = 0.0
        self._dragging = False
        self._focus = Spring(0.0, FOCUS_S)    # 0 = 一排同桌，1 = 详情页（只剩正中这只）
        self._focus_to = 0.0
        self._lift = Spring(0.0, LIFT_S)      # 正中那一格抬起来几成（狗和顶部栏的名字胶囊共用这一根）
        self._lift_px = 0.0                   # 上次告诉卡片的（lift_changed）
        self._hover_center = False            # 鼠标在正中那一格上
        self._hover_name = False              # 鼠标在顶部栏它的名字上（卡片告诉的，set_name_hover）
        self._gap_at = NO_GAP                 # 刚添了 / 刚删了一只：从第几格起后面的还没挪到位
        self._gap = Spring(0.0, FOCUS_S)      # 还差几格（删：1 → 0；添：-1 → 0）
        self._leaving: Optional[tuple[Optional[Sticker], int]] = None   # 刚删的那只：(贴纸, 它原来在第几格)
        self._leave = Spring(0.0, 0.22)       # 它还剩几成（1 → 0）
        self._rising: Optional[str] = None    # 刚添的那只的号
        self._rise = Spring(1.0, 0.34)        # 它冒出来几成（0 → 1）
        self._rise_wait = 0.0
        self._blend: Optional[tuple[str, Sticker]] = None   # 现在这只刚换了毛色：(号, 旧贴纸)，淡成新的
        self._blend_t = Spring(0.0, BLEND_S)
        self._wheel = WheelSteps()            # 滚轮、触摸板：一次动作换一只
        self._dot_press: Optional[int] = None # 在第几个小圆点上按下的（「+」是 len(pets)）
        self._hover_dot: Optional[int] = None
        self._dot_hover: dict[int, Spring] = {}   # 每个小圆点悬停的那根弹簧（0 → 1：慢慢长大一圈、变深；和狗抬起来一样 LIFT_S、不回弹）
        self._dot_down = Spring(0.0, DOT_PRESS_S)  # 按着的那个点缩一点（和按钮按下一样）
        self._shots = QTimer(self)            # 别的同桌的贴纸晚一点画（要解码它们的贴图，放在卡片弹出来之后）
        self._shots.setSingleShot(True)
        self._shots.setInterval(360)
        self._shots.timeout.connect(self._render_missing)
        self.refresh(jump=True)

    # ---- 数据
    def slots(self) -> int:
        return len(self.pets) + 1

    def current_index(self) -> int:
        return next((i for i, p in enumerate(self.pets) if p.id == self.w.prefs.pet_id), 0)

    def center(self) -> int:
        """正中是第几格（滑动时过一半就算下一格）：顶部栏的名字写它的；第 len(pets) 格是「+」。"""
        return max(0, min(self.slots() - 1, self._center))

    def refresh(self, jump: bool = False) -> None:
        """名单、名字、毛色可能变了（打开卡片、换了同桌、添了删了、改了毛色、改了名字）：重新取，顶部栏的名字跟上。
        jump：直接停在现在这只上（不滑过去）。"""
        self.pets = list(self.w.pets())
        self.names = [self.w.pet_name(p) for p in self.pets]
        cur = self.current_index()
        if jump or self.target >= self.slots() or not (self._sliding or self._dragging or self.target == len(self.pets)):
            self.target = cur                                 # 没在滑：正中就是现在这只（停在「+」上不动）
            if jump:
                self.pos, self._v, self._sliding = float(cur), 0.0, False
                self._center = cur
            else:
                self._slide()
        live = {p.id for p in self.pets}
        self._stickers = {k: v for k, v in self._stickers.items() if k in live}
        self._ensure_stickers()
        self.update()
        self.center_changed.emit()                            # 名字可能变了：顶部栏不管正中换没换都再写一遍（字没变它什么都不做）

    def look_changed(self) -> None:
        """有同桌换了毛色（设置卡片每 0.3 秒问一次）：它的贴纸重做。没变就什么都不做。"""
        self._ensure_stickers()

    def _signature(self, pet) -> tuple:
        """长相的签名：变了贴纸重做。画得出真样子没有（模型在不在用着，window.pet_drawable）也算：换了模型，原来是缩略图的那只要照真的画。"""
        return (*self.w.pet_look(pet), sticker.INK, pet.pack, self.w.pet_drawable(pet))

    def _ensure_stickers(self) -> None:
        """现在这只的贴纸马上做（它的毛色就在显卡上，画一下就行）；别的晚一点一起做。"""
        missing = [p for p in self.pets if self._stickers.get(p.id, (None, None))[0] != self._signature(p)]
        if not missing:
            return
        now = [p for p in missing if p.id == self.w.prefs.pet_id]
        if now and self.w.coat_pending():             # 刚换的同桌，显卡上还是上一只的毛色：等贴图换上（window._coat_on 再叫一次）
            missing = [p for p in missing if p not in now]
            now = []
        if now:
            self._render(now)
        if len(missing) > len(now) and not self._shots.isActive():
            if self.isVisible():
                self._shots.start()
            else:
                self._render_missing()

    def _render_missing(self) -> None:
        pending = self.w.coat_pending()
        self._render([p for p in self.pets if self._stickers.get(p.id, (None, None))[0] != self._signature(p)
                      and not (pending and p.id == self.w.prefs.pet_id)])

    def _render(self, pets: list) -> None:
        try:
            shots = self.w.pet_shots(pets, SHOT_PX, SHOT_PPM, SHOT_GROUND)
        except Exception:                                    # noqa: BLE001 —— 贴纸画不出来不能挡住设置卡片
            import logging
            logging.getLogger("pets").exception("pet stickers failed")
            shots = {}
        ready = self.w.view.ready()                           # 画布好了没有（程序刚启动、单测里都没有）
        for pet in pets:
            shot = shots.get(pet.id)
            made = None
            other = pet.pack != self.w.pack.id
            if shot is not None and not shot.isNull():
                made = cutout(shot, SHOT_PX / 2.0, sticker.INK)
            elif other:
                made = thumb_sticker(self.w.pet_thumb(pet), sticker.INK)
            if made is not None or ready or other:            # 画布还没好的不记：等卡片显示出来再试；别的情况画不出来就认了（圆点顶着），不反复试
                old = self._stickers.get(pet.id, (None, None))[1]
                if old is not None and made is not None and pet.id == self.w.prefs.pet_id and self.isVisible():
                    self._blend = (pet.id, old)               # 现在这只换了毛色：旧的淡成新的，不一下跳过去
                    self._blend_t.set_target(1.0, True)
                    self._blend_t.set_target(0.0)
                    self._run()
                self._stickers[pet.id] = (self._signature(pet), made)
        self.update()

    # ---- 几何
    def gone(self) -> float:
        """别的同桌退开了几成（0 = 一排都在，1 = 详情页，只剩正中这只）。"""
        return clamp(self._focus.value)

    def yc(self) -> float:
        """桌沿中线最高那一点现在的 y：详情页上往下坐一点。"""
        return YC + FOCUS_DROP * self.gone()

    def coord(self, i: int) -> float:
        """第 i 格现在排在第几格的位置上：刚添了、刚删了一只时，后面的还在挪（_gap）。"""
        return i + (self._gap.value if i >= self._gap_at else 0.0)

    def hub(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.yc() + RADIUS)

    def at(self, theta: float, r: float) -> QPointF:
        """大圆上角度 theta（0 = 正上方，正数 = 往右）、半径 r 的那一点。"""
        a = math.radians(theta)
        hub = self.hub()
        return QPointF(hub.x() + r * math.sin(a), hub.y() - r * math.cos(a))

    @staticmethod
    def scale_at(u: float) -> float:
        return lerp(1.0, SIDE_SCALE, smooth(u)) if u <= 1.0 else max(0.5, SIDE_SCALE - (u - 1.0) * 0.18)

    @staticmethod
    def alpha_at(u: float) -> float:
        return 1.0 if u <= FADE_FROM else 1.0 - smooth((u - FADE_FROM) / (FADE_TO - FADE_FROM))

    def on_table(self, pos: QPointF) -> bool:
        """这一点在不在桌沿那一带（狗、「+」都在这一带）：在这儿按下拖是滑同桌，别处按下拖还是拖卡片。"""
        off = self._offset_at(pos)
        return off is not None and abs(off) <= ARC + 0.2

    def _offset_at(self, pos: QPointF) -> Optional[float]:
        """这一点离正中隔几格（小数，正数在右边）；不在狗、「+」坐的那一圈上返回 None。"""
        hub = self.hub()
        dx, dy = pos.x() - hub.x(), hub.y() - pos.y()
        r = math.hypot(dx, dy)
        if dy <= 0 or not (RADIUS - 46.0 <= r <= RADIUS + VISIBLE + 8.0):
            return None
        return math.degrees(math.atan2(dx, dy)) / STEP

    def slot_at(self, pos: QPointF) -> Optional[int]:
        """这一点是哪一格的（狗身上、「+」上都算）；不在任何一格上返回 None。"""
        off = self._offset_at(pos)
        if off is None:
            return None
        i = round(self.pos + off)
        if not (0 <= i < self.slots()) or abs(self.pos + off - i) > CENTER_HALF or abs(i - self.pos) > FADE_TO:
            return None
        return i

    def _over_center(self, pos: QPointF) -> bool:
        """这一点在正中那一格的地方（不管现在是哪一只坐在那：正中那块地方一直在这儿）。"""
        off = self._offset_at(pos)
        return off is not None and abs(off) <= CENTER_HALF

    def _dot_xs(self) -> tuple[list[float], float, float]:
        """那一排小圆点：每一格的 x（「+」是最后一个）、相邻两个隔多远、y。和 _paint_dots 一个算法。"""
        n = len(self.pets)
        last = self.coord(n)
        gap = min(DOT_GAP, DOT_SPAN / max(1.0, last))
        x0 = self.width() / 2.0 - last * gap / 2.0
        return [x0 + self.coord(i) * gap for i in range(n + 1)], gap, self.yc() + DOT_DY

    def dot_at(self, pos: QPointF) -> Optional[int]:
        """这一点在哪个小圆点上（「+」是 len(pets)）：点的范围比点本身大（DOT_HIT_H 高，左右到旁边那个的一半，两头再往外 DOT_HIT_OUT）。
        详情页上小圆点淡掉了，点不到。"""
        if self._focus_to > 0.0 or self._aside() < 0.5:
            return None
        xs, gap, y = self._dot_xs()
        if abs(pos.y() - y) > DOT_HIT_H / 2.0 or not xs:
            return None
        if not (xs[0] - gap / 2.0 - DOT_HIT_OUT <= pos.x() <= xs[-1] + gap / 2.0 + DOT_HIT_OUT):
            return None
        return min(range(len(xs)), key=lambda i: abs(xs[i] - pos.x()))

    def go_to_dot(self, index: int) -> None:
        """点了一个小圆点（只导航）：转到那一格，和点旁边那只一样——同桌换成它、「+」转到正中，都不进详情页、添加页；
        点的是正中这一格自己的点：不动。"""
        if index == self.target and self.settled():
            return
        self.go(index)

    def _dot_here(self, index: int) -> bool:
        """这个小圆点是不是正中停着的这一格自己的（点了不动）。"""
        return index == self.target and self.settled()

    def _set_hover_dot(self, dot: Optional[int]) -> None:
        """鼠标换到了另一个小圆点上（None = 不在任何一个上）：新的那个慢慢长大变深，旧的慢慢回去。"""
        self._hover_dot = dot
        live = drive(self, self)
        for index, spring in self._dot_hover.items():
            spring.set_target(0.0, instant=not live)
        if dot is not None:
            spring = self._dot_hover.setdefault(dot, Spring(0.0, LIFT_S))
            spring.set_target(1.0, instant=not live)
        self.update()

    def dot_hover(self, index: int) -> float:
        """这个小圆点悬停了几成（0..1）。"""
        spring = self._dot_hover.get(index)
        return min(1.0, max(0.0, spring.value)) if spring is not None else 0.0

    def settled(self) -> bool:
        """停稳了：没在滑、没在拖，添了删了一只后挪的也到位了。正中那一格这时才抬起来。"""
        return (not self._sliding and not self._dragging and self._gap.settled and abs(self.pos - self.target) < 1e-3)

    # ---- 滑
    def go(self, index: int) -> None:
        """滑到第 index 格（「+」是最后一格）。要去的是另一只同桌：桌面上的狗这一刻就开始淡出，到位再换（_commit）；折回现在这只、去「+」：淡回来。"""
        index = max(0, min(self.slots() - 1, int(index)))
        self.target = index
        self._early = False
        if index < len(self.pets):
            self.w.warm_pack(self.pets[index].pack)           # 要去的是别的模型的那只：还没备好就现在开始备（兜底，滑过去还有 0.3 秒）
        self._fade_for_target()
        self._slide()

    def _fade_for_target(self) -> None:
        away = self.target < len(self.pets) and self.pets[self.target].id != self.w.prefs.pet_id
        self.w.fade_dog(not away)

    def _slide(self) -> None:
        if abs(self.pos - self.target) < 1e-4 and abs(self._v) < 1e-3:
            self._arrived()
            return
        if not self._sliding:
            self._sliding = True
            if not drive(self, self):                        # 挂不上卡片的节拍（没显示、减少动态效果）：直接到位
                self._sliding = False
                self._set_pos(float(self.target))
                self._v = 0.0
                self._arrived()
                return
        self._update_lift()                                   # 一动起来正中那一格就放下

    def tick(self, dt: float) -> bool:
        """卡片的每一帧：滑动的弹簧往目标走；进出详情页、抬起来、添了删了、换毛色那几根也走。返回还要不要下一帧。"""
        more = False
        if self._sliding:
            w = 2.0 * math.pi / RESPONSE_S                   # 临界阻尼弹簧（和卡片别处一样不回弹）
            d0 = self.pos - self.target
            c = self._v + w * d0
            e = math.exp(-w * dt)
            pos = self.target + (d0 + c * dt) * e
            self._v = (self._v - w * c * dt) * e
            if abs(pos - self.target) < 0.002 and abs(self._v) < 0.05:
                pos, self._v, self._sliding = float(self.target), 0.0, False
            self._set_pos(pos)
            if self._sliding:
                more = True
                if abs(pos - self.target) < COMMIT_NEAR and not self._early:
                    self._early = True
                    self._commit()                            # 看着已经到了：现在就换，不等弹簧走完最后那不到 1 像素
            else:
                self._arrived()
        if self._rise_wait > 0.0:                             # 新添的那只：等换页淡入过半再冒出来
            self._rise_wait -= dt
            if self._rise_wait <= 0.0:
                self._rise.set_target(1.0)
            more = True
        moved = False
        for spring in (*self._springs(), *self._dot_hover.values(), self._dot_down):
            if not spring.settled:
                spring.step(dt)
                moved = True
                more = more or not spring.settled
        for index in [i for i, sp in self._dot_hover.items() if sp.settled and sp.value <= 0.0]:
            del self._dot_hover[index]
        if moved:
            self._tidy()
            self.update()
        self._emit_lift()
        return more

    def _springs(self) -> tuple:
        return self._focus, self._lift, self._gap, self._leave, self._rise, self._blend_t

    def _tidy(self) -> None:
        """走完了的收掉。"""
        if self._gap.settled and self._gap_at != NO_GAP:
            self._gap_at = NO_GAP
            self._update_lift()                               # 补位走完了：鼠标还在正中就抬
        if self._leave.settled and self._leave.value <= 0.0:
            self._leaving = None
        if self._rise.settled and self._rise_wait <= 0.0 and self._rise.value >= 1.0:
            self._rising = None
        if self._blend_t.settled and self._blend_t.value <= 0.0:
            self._blend = None

    def _run(self) -> None:
        """有弹簧要走：挂到卡片的节拍上；挂不上（卡片没显示、减少动态效果）就全部直接到位。"""
        if drive(self, self):
            return
        self._rise_wait = 0.0
        if self._rising is not None:
            self._rise.set_target(1.0)
        for spring in self._springs():
            spring.set_target(spring.target, True)
        self._tidy()
        self._emit_lift()
        self.update()

    # ---- 正中那一格：抬起来、点它（顶部栏里它的名字也算）
    def _update_lift(self) -> None:
        """鼠标在正中那一格上、或在顶部栏它的名字上，而且停稳了、不在详情页：抬起来；否则放下（同一根弹簧，不回弹）。"""
        on = (self._hover_center or self._hover_name) and self._focus_to == 0.0 and self.settled()
        target = 1.0 if on else 0.0
        if self._lift.target != target:
            self._lift.set_target(target)
            self._run()

    def set_name_hover(self, on: bool) -> None:
        """卡片说：鼠标进 / 出了顶部栏里正中那一格的名字。"""
        if on != self._hover_name:
            self._hover_name = on
            self._update_lift()

    def _emit_lift(self) -> None:
        px = round(LIFT_PX * clamp(self._lift.value), 3)
        if px != self._lift_px:
            self._lift_px = px
            self.lift_changed.emit(px)

    def activate_center(self) -> None:
        """点正中那一格（狗身上、顶部栏里它的名字都算：一个整体）：同桌进它的详情页（还在滑不理，open_current），
        「+」进添加页（和同桌一个规矩，在旁边点只转过来；它不用先换同桌，所以快滑到时点也算）。详情页上、拖着的时候不理。"""
        if self._focus_to > 0.0 or self._dragging:
            return
        if self.target >= len(self.pets):
            sounds.play("tap")
            self.card.open_add_pet()
        else:
            self.open_current()

    # ---- 详情页、添加、删除
    def set_focus(self, on: bool, animated: bool = True) -> None:
        """详情页（on）/ 一排同桌：正中这只放大一圈、往下坐一点，别的往两边退开淡掉（返回在卡片顶部栏左边的圆里）。"""
        self._focus_to = 1.0 if on else 0.0
        if on:
            self._press, self._dragging = None, False
            self._wheel.reset()
            cur = self.current_index()
            self.target, self.pos, self._v, self._sliding = cur, float(cur), 0.0, False
            self._set_center(cur)
            self.setCursor(Qt.ArrowCursor)
        self._focus.set_target(self._focus_to, not animated)
        if animated:
            self._run()
        self._update_lift()
        self.update()

    def open_current(self) -> None:
        """点正中那只：进它的详情页。还没换过去的先换（详情页里改的就是桌面上这只）。"""
        if self.target >= len(self.pets) or self._sliding or self._dragging:
            return
        self._commit()
        if self.target < len(self.pets) and self.pets[self.target].id == self.w.prefs.pet_id:
            sounds.play("tap")
            self.card.open_pet()

    def remove_current(self) -> None:
        """删掉现在这只（详情页里长按「删除」；卡片这时已经在回主页面）：它缩回桌沿后面，后面的补过来。最后一只删不了。"""
        if len(self.pets) < 2:
            return
        i = self.current_index()
        pet = self.pets[i]
        self._leaving = (self._stickers.get(pet.id, (None, None))[1], i)
        self._leave.set_target(1.0, True)
        self._leave.set_target(0.0)
        self._gap_at = i
        self._gap.set_target(1.0, True)
        self._gap.set_target(0.0)
        self.w.remove_pet(pet.id)                             # → pet_changed → refresh：名单少了一只
        self.go(self.current_index())                         # 正中滑到现在这只（旁边那只）上；删的是最后一只时不停在「+」上
        self._run()

    def added(self, pet_id: str) -> None:
        """刚添了一只（卡片正从添加页回来）：它从桌沿后面冒出来，「+」往右让一格。"""
        i = next((k for k, pet in enumerate(self.pets) if pet.id == pet_id), None)
        if i is None:
            return
        self._rising = pet_id
        self._rise.set_target(0.0, True)
        self._rise_wait = RISE_DELAY_S
        self._gap_at = i + 1
        self._gap.set_target(-1.0, True)
        self._gap.set_target(0.0)
        self._run()

    def _set_center(self, i: int, sound: bool = False) -> None:
        if i != self._center:
            self._center = i
            if sound:
                sounds.play("tick")                           # 每过一只 tick 一声
            self.center_changed.emit()

    def _set_pos(self, pos: float) -> None:
        self.pos = pos
        self._set_center(max(0, min(self.slots() - 1, round(pos))), sound=True)
        self.update()

    def _arrived(self) -> None:
        self._commit()                                        # 到位就换（不等）；一路滑过去的不在这儿停，所以不挨个换
        self._update_lift()                                   # 停稳了：鼠标还在正中（滚轮、拖完）就抬
        self.update()

    def _commit(self) -> None:
        """正中要停的那只不是现在这只：换过去（狗已经在路上淡出了，换好窗口自己淡入）。停在现在这只、「+」上：狗淡回来。拖着的时候不换。"""
        if self._dragging:
            return
        pet = self.pets[self.target] if self.target < len(self.pets) else None
        if pet is not None and pet.id != self.w.prefs.pet_id:
            self.w.switch_pet(pet.id)                         # 换好回来时 pet_changed → refresh；模型读不出来的不换，窗口那边让它滑回来（window._stay）；
                                                              # 别的模型还没备好：窗口记下、狗淡出着等，备好了再换
        else:
            self.w.cancel_switch()                            # 回到现在这只、停在「+」上：没备好还在等的那次不换了
        if not self._sliding:
            self.w.fade_dog(True)                             # 没换成（模型不在了）、本来就是这只：别让狗一直看不见

    def _release(self) -> None:
        """松手（拖完）：吸到最近的一格。"""
        self._dragging = False
        self.go(round(clamp(self.pos, 0.0, self.slots() - 1.0)))

    def _drag_to(self, pos: float) -> None:
        lo, hi = -OVER, self.slots() - 1.0 + OVER
        if self._sliding:
            self.w.fade_dog(True)                             # 滑到一半又抓住了：狗先回来，松手再说（不让它在手里一直看不见）
        self._sliding, self._v = False, 0.0
        self._set_pos(clamp(pos, lo, hi))

    # ---- 鼠标
    def mousePressEvent(self, event) -> None:
        dot = self.dot_at(event.position()) if event.button() == Qt.LeftButton else None
        if dot is not None and not self._dot_here(dot):        # 小圆点：松开时还在同一个点上才算；正中这一格自己的点点了不动（交给卡片，照旧能拖）
            self._dot_press = dot
            self._dot_down.set_target(1.0, instant=not drive(self, self))
            self.update()
            event.accept()
            return
        if dot is not None:
            event.ignore()
            return
        if event.button() != Qt.LeftButton or self._focus_to > 0.0 or not self.on_table(event.position()):
            event.ignore()                                    # 桌沿以外（上面、两边的空白）、详情页上：交给卡片，照旧能拖卡片
            return
        self._press, self._press_pos = event.position(), self.pos
        self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        self._hover_center = self._focus_to == 0.0 and self._over_center(pos)
        dot = self.dot_at(pos) if self._press is None else None
        if dot is not None and self._dot_here(dot):
            dot = None                                        # 正中这一格自己的点：点了没用，悬停也不变、不出小手
        if dot != self._hover_dot:
            self._set_hover_dot(dot)
        if self._dot_press is not None:
            event.accept()
            return
        if self._press is None:
            hit = None if self._focus_to > 0.0 else self.slot_at(pos)
            self.setCursor(Qt.PointingHandCursor if (hit is not None or dot is not None) else Qt.ArrowCursor)   # 每一格、每个小圆点都能点
            self._update_lift()
            return
        dx = pos.x() - self._press.x()
        if not self._dragging and abs(dx) >= DRAG_START_PX:
            self._dragging = True
            self._update_lift()
        if self._dragging:
            self._drag_to(self._press_pos - dx / SLOT_PX)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._dot_press is not None and event.button() == Qt.LeftButton:
            pressed, self._dot_press = self._dot_press, None
            self._dot_down.set_target(0.0, instant=not drive(self, self))
            self.update()
            if self.dot_at(event.position()) == pressed:
                self.go_to_dot(pressed)
            event.accept()
            return
        if self._press is None or event.button() != Qt.LeftButton:
            return
        pos, dragged = self._press, self._dragging
        self._press = None
        if dragged:
            self._release()
        else:
            hit = self.slot_at(pos)
            if hit is None:
                pass
            elif hit != self.target or abs(self.pos - hit) > 0.05:
                self.go(hit)                                  # 点旁边的（同桌、「+」一个规矩）：只转到正中
            else:
                self.activate_center()                        # 点正中的：同桌进详情页，「+」去添加页
        event.accept()

    def leaveEvent(self, event) -> None:
        self.setCursor(Qt.ArrowCursor)
        self._hover_center = False
        if self._hover_dot is not None:
            self._set_hover_dot(None)
        self._update_lift()
        super().leaveEvent(event)

    def wheelEvent(self, event) -> None:
        """滚轮、触摸板：一次动作换一只（wheel.WheelSteps）；翻的时候和点旁边那只一样，用滑到位的弹簧转过去（不回弹），到位才换同桌。
        详情页上不滑（交给卡片）；正按着鼠标的时候不翻（不和拖打架），但照样记着这一次动作。"""
        if self._focus_to > 0.0:
            event.ignore()
            return
        event.accept()                                        # 滚轮归它：卡片不跟着滚
        steps = self._wheel.feed(event)
        if steps and self._press is None:
            self.go(self.target + steps)                      # 两头到头了就不动（go 自己夹住），不回弹

    def hideEvent(self, event) -> None:
        """卡片收起、换到别的页：滑到一半的直接到位；停在别的同桌上还没换的马上换（不然下次打开正中又跳回去）。
        抬起来的慢慢放下（卡片还开着时照常走完；卡片收起了就直接到位）：顶部栏的名字胶囊跟着这一根，不能一下掉下去。"""
        self._press, self._dragging = None, False
        self._dot_press, self._hover_dot = None, None
        self._dot_hover.clear()
        self._dot_down.set_target(0.0, instant=True)
        self._wheel.reset()
        if not self._sliding:                                 # 拖到一半：算最近的那一格（滑到一半的就是它要去的那一格）
            self.target = max(0, min(self.slots() - 1, round(self.pos)))
        self._sliding, self._v = False, 0.0
        if self.target >= len(self.pets):
            self.target = self.current_index()                # 停在「+」上关掉的：下次打开回到现在这只
        self.pos = float(self.target)
        self._set_center(self.target)
        self._commit()
        self._hover_center = self._hover_name = False
        self._update_lift()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh(jump=True)

    # ---- 画
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # 狗只画在大圆外面（桌沿中线往里 3 像素以外）：切口、切口下面那圈描边、影子都剪在桌沿后面
        hub = self.hub()
        above = QPainterPath()
        above.addRect(QRectF(-10.0, -10.0, self.width() + 20.0, self.height() + 60.0))
        hole = QPainterPath()
        hole.addEllipse(hub, RADIUS - 3.0, RADIUS - 3.0)
        p.save()
        p.setClipPath(above.subtracted(hole), Qt.IntersectClip)
        n = len(self.pets)
        self._paint_leaving(p)
        for i in sorted(range(n), key=lambda i: -abs(self.coord(i) - self.pos)):
            self._paint_pet(p, i)
        self._paint_add(p, self.coord(n) - self.pos)
        p.restore()
        self._paint_table(p)
        self._paint_dots(p)
        for i in range(n):
            self._paint_names(p, i)
        p.end()

    def _aside(self) -> float:
        """进详情页时旁边的东西（别的同桌、「+」、它们的名字、小圆点）还剩几成：先淡掉，正中那只再长大。"""
        return 1.0 - smooth(self.gone() * 1.3)

    def _push(self, off: float) -> float:
        """进详情页时旁边的往两边退开多少格。"""
        return math.copysign(FOCUS_PUSH * self.gone(), off) if off else 0.0

    def _paint_leaving(self, p: QPainter) -> None:
        """刚删的那只：在它原来那一格缩回桌沿后面。"""
        if self._leaving is None:
            return
        made, at = self._leaving
        k = clamp(self._leave.value)
        if made is None or k <= 0.01:
            return
        off = at - self.pos
        theta = off * STEP
        pt = self.at(theta, RADIUS - (1.0 - k) * SINK_PX)
        made.draw(p, pt.x(), pt.y(), scale=self.scale_at(abs(off)) * lerp(0.8, 1.0, k), angle=theta, opacity=self.alpha_at(abs(off)) * k)

    def _paint_pet(self, p: QPainter, i: int) -> None:
        pet = self.pets[i]
        off = self.coord(i) - self.pos
        u = abs(off)
        a = self.alpha_at(u)
        center = i == self.target and u < 0.5
        s = self.scale_at(u)
        r = RADIUS
        if center:                                            # 正中这只：鼠标在它或顶部栏它的名字上抬一下；详情页上放大一圈
            lift = clamp(self._lift.value)
            s *= lerp(1.0, FOCUS_SCALE, self.gone()) * lerp(1.0, LIFT_SCALE, lift)
            r += LIFT_PX * lift
        else:                                                 # 别的：详情页上往两边退开、淡掉
            a *= self._aside()
            off += self._push(off)
        if pet.id == self._rising:                            # 刚添的：从桌沿后面冒出来
            k = clamp(self._rise.value)
            r -= (1.0 - k) * SINK_PX
            s *= lerp(0.8, 1.0, k)
        if a < 0.05:
            return
        theta = off * STEP
        pt = self.at(theta, r)
        made = self._stickers.get(pet.id, (None, None))[1]
        if made is not None:
            made.draw(p, pt.x(), pt.y(), scale=s, angle=theta, opacity=a, shadow=smooth(1.0 - u / 0.6))
            if self._blend is not None and self._blend[0] == pet.id and self._blend_t.value > 0.01:   # 刚换了毛色：旧的盖在上面淡掉
                self._blend[1].draw(p, pt.x(), pt.y(), scale=s, angle=theta, opacity=a * clamp(self._blend_t.value))
            return
        p.save()                                              # 贴纸还没做出来 / 做不出来：一个描边的圆点顶着
        c = self.at(theta, r + 26.0 * s)
        p.setOpacity(p.opacity() * a)
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE * s))
        p.setBrush(QColor(sticker.PAPER_2))
        p.drawEllipse(c, 22.0 * s, 22.0 * s)
        p.restore()

    def _paint_table(self, p: QPainter) -> None:
        """桌沿：固定的、左右对称的一段弧（预览里两只时只往一边伸，像滑梯）。"""
        hub = self.hub()
        rect = QRectF(hub.x() - RADIUS, hub.y() - RADIUS, 2 * RADIUS, 2 * RADIUS)
        half = ARC * STEP
        path = QPainterPath()
        path.arcMoveTo(rect, 90.0 + half)
        path.arcTo(rect, 90.0 + half, -2.0 * half)
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(sticker.INK), BAND, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(QColor(sticker.PAPER_2), BAND - 2 * sticker.OUTLINE, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.restore()

    def _paint_dots(self, p: QPainter) -> None:
        """桌沿下面一排小圆点：一只一个，正中那只的深、大一点，最后一个小「+」。
        深浅跟着滑动连续变；添删一只时跟着补位（coord），删掉的那个点在原地淡掉、新添的那个跟着它从桌沿后面冒出来，不跳；详情页上和别的同桌一起淡掉。
        最宽 DOT_SPAN：同桌多了点挨近、一起变小，不伸到旁边两只的灰色名字下面。"""
        a = self._aside()
        if a <= 0.0:
            return
        n = len(self.pets)
        last = self.coord(n)                                 # 「+」那一格；添删时是小数，跟着补位，整排的正中不跳
        gap = min(DOT_GAP, DOT_SPAN / max(1.0, last))
        k = gap / DOT_GAP
        x0 = self.width() / 2.0 - last * gap / 2.0
        y = self.yc() + DOT_DY
        marks = [(self.coord(i), clamp(self._rise.value) if self.pets[i].id == self._rising else 1.0, False, i) for i in range(n)]
        if self._leaving is not None:
            marks.append((float(self._leaving[1]), clamp(self._leave.value), False, None))
        marks.append((last, 1.0, True, n))
        p.save()
        for c, alpha, plus, slot in marks:
            sel = smooth(1.0 - abs(c - self.pos))
            h = self.dot_hover(slot) if slot is not None else 0.0
            down = 1.0 - DOT_PRESS_SHRINK * clamp(self._dot_down.value) if slot is not None and slot == self._dot_press else 1.0
            big = max(sel, h)                                 # 鼠标放上去：慢慢长到正中那个点那么大
            sel = max(sel, DOT_HOVER_INK * h)                 # 也慢慢变深（能点）
            color = sticker.mix(QColor(sticker.MUTED), QColor(sticker.INK), sel)
            color.setAlphaF(clamp(a * alpha * lerp(0.55, 1.0, sel)))
            x = x0 + c * gap
            if plus:
                arm = lerp(3.0, 4.0, big) * k * down
                p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                p.drawLine(QPointF(x - arm, y), QPointF(x + arm, y))
                p.drawLine(QPointF(x, y - arm), QPointF(x, y + arm))
            else:
                r = lerp(2.3, 3.3, big) * k * down
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawEllipse(QPointF(x, y), r, r)
        p.restore()

    def _paint_names(self, p: QPainter, i: int) -> None:
        """旁边那只的名字：12 像素灰字，正着，在它那一段桌沿下面；离正中 0.35 格以内没有（正中那只的名字在顶部栏），过了一格马上淡没。"""
        name = self.names[i] if i < len(self.names) else ""
        off = self.coord(i) - self.pos
        u = abs(off)
        side = smooth((u - 0.35) / 0.45) * (1.0 - smooth((u - 1.0) / 0.10)) * self._aside()
        if side <= 0.02 or not name:
            return
        f = font(12)
        fm = QFontMetricsF(f)
        theta = (off + self._push(off)) * STEP
        text = fm.elidedText(name, Qt.ElideRight, SIDE_TEXT_MAX)
        half_w = fm.horizontalAdvance(text) / 2.0
        a = math.radians(abs(theta))
        back = BAND / 2.0 + NAME_CLEAR + half_w * math.sin(a) + 7.0 * math.cos(a)   # 往圆心退到字的外上角也离桌沿下边 NAME_CLEAR
        pt = self.at(theta, RADIUS - back)
        p.setFont(f)
        p.setPen(ink(sticker.MUTED, side))
        p.drawText(QRectF(pt.x() - 60.0, pt.y() - 10.0, 120.0, 20.0), int(Qt.AlignCenter), text)

    def _paint_add(self, p: QPainter, off: float) -> None:
        """最后多出来的那一格：桌沿后面的一个空位。虚线小圆 + 正着的「+」；停在正中时和同桌一样，鼠标在它或顶部栏的「添加同桌」上就抬一下。"""
        u = abs(off)
        a = self.alpha_at(u) * self._aside()
        if a < 0.05:
            return
        sel = smooth(1.0 - u)
        lift = clamp(self._lift.value) if self.target == len(self.pets) and u < 0.5 else 0.0
        r = lerp(ADD_R1, ADD_R0, sel) * lerp(1.0, LIFT_SCALE, lift)
        c = self.at((off + self._push(off)) * STEP, RADIUS + BAND / 2.0 - ADD_TUCK + r + LIFT_PX * lift)
        p.save()
        pen = QPen(ink(sticker.MUTED, lerp(0.40, 0.85, sel) * a), 1.5, Qt.CustomDashLine, Qt.RoundCap)
        pen.setDashPattern([2.4, 2.6])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)
        arm = r * 0.36
        p.setPen(QPen(ink(sticker.mix(QColor(sticker.MUTED), QColor(sticker.INK), sel), lerp(0.7, 1.0, sel) * a), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(c.x() - arm, c.y()), QPointF(c.x() + arm, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - arm), QPointF(c.x(), c.y() + arm))
        p.restore()
