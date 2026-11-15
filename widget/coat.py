"""毛色自定义：在模型自带的贴图上换颜色，身形不变。

做法（全用 QPainter 合成和 256 项查找表，不逐像素循环，2048 一张一两百毫秒）：
1. 斑纹：从四套原贴图之一按亮度分出"深色毛"遮罩（大津法找阈值，±12 级的软边），决定主色 / 副色各在哪里。
2. 细节：原贴图去色当细节层（毛的纹理、明暗都在）；深色区乘 3 把明度拉上来，不然黑毛染成浅色一片死平；浅色区微提 1.15。
3. 合成：深色区 = 主色 × 深色细节，浅色区 = 副色 × 细节，按遮罩拼起来；Swap 就把两张遮罩对调。
4. 保护区：眼、眼皮、鼻、舌、嘴、爪垫从骨骼权重划出的 UV 区域永远用原图。眼睛可以单独换色：Overlay 合成模式给虹膜的中间调上色，
   白眼球和黑瞳孔基本不动（Qt 的 QPainter 没有 Hue 模式）。
参数记在 CoatSpec 里，QSettings 存成 JSON。

通体一色的（萨摩耶，包里 coat_custom.mode = "tint"；上面那套分深浅的做法给它就是一片死白）用 TintPainter：
整身染主色（第 1 套贴图去色当细节，按毛平常的亮度和提亮倍数归一，选的颜色就是看到的颜色）；第 2 种斑纹「背上一片」再把一块染成副色
（范围取自第 patch_from 套贴图里偏黄的地方，大津法分界）；眼鼻舌嘴爪垫（保护区）和耳朵里、舌头那块粉色（红比绿多 PINK_FROM 以上）留原样。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

from widget.gltf import Model

PROTECTED_BONES = ("eye.L", "eye.R", "eyelid.L", "eyelid.R", "nose", "tongue_1", "tongue_2", "tongue_3", "tongue_4",
                   "mouth", "Mouth.L", "Mouth.R", "claws_f.L", "claws_f.R", "claws_b.L", "claws_b.R")
EYE_BONES = ("eye.L", "eye.R")
TINT_PROTECTED_BONES = tuple(b for b in PROTECTED_BONES if b not in ("mouth", "Mouth.L", "Mouth.R"))   # 通体一色的：嘴那几根管着一圈口鼻毛，留原图就是一圈白，跟着染
                                                                                                      # （深色的嘴唇乘上去还是深的，舌头另有保护）
SOFT_EDGE = 12          # 斑纹遮罩软边：阈值上下这么多亮度级
DARK_BOOST = 3.0        # 深色区细节层的明度倍数
LIGHT_BOOST = 1.15
THUMB_DARK, THUMB_LIGHT = "#3B3B40", "#EFECE6"   # 斑纹缩略图用的固定两色：只看分布，不看颜色
PINK_FROM, PINK_FULL = 35, 50   # 通体一色的：红比绿多这么多的地方留原样（35 开始、50 全留；量的萨摩耶第 1 套：毛 −20～5，脸上那点 10～45，
                                # 耳朵里、舌头那簇粉 50～65——试做时从 18 开始留，脸也被留成白的、没跟着染）
FUR_GRAY = 163                  # 通体一色的：贴图里毛平常多亮（中位数，萨摩耶第 1 套量的）：细节层按它 × 提亮倍数归一
# 自定义页的「常用颜色」：(主色, 副色)，点一下两个一起换。黑白、巧克力、红棕、金、蓝灰、银灰、奶油（模型包可以另给，coat_custom.common_colors）
COMMON_COLORS = (("#2A2A2E", "#F2F0EC"), ("#5E3B26", "#F3EADC"), ("#B5652B", "#F6EBDD"), ("#D9A35B", "#FBF3E4"),
                 ("#6F7686", "#EEF0F3"), ("#9A9AA0", "#FFFFFF"), ("#D8C4A4", "#FFFDF8"))


@dataclass
class CoatSpec:
    pattern: int = 1              # 用第几套原贴图的斑纹分布（1..4）
    main: str = "#2A2A2E"         # 深色毛
    secondary: str = "#F2F0EC"    # 白斑
    swap: bool = False            # 深浅对调
    eyes: str = ""                # 眼睛颜色，空 = 原装

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: Optional[str], default: Optional["CoatSpec"] = None) -> "CoatSpec":
        """读记着的；读不出来、没记过是 default（这个模型的默认，模型包的 coat_custom.default），没给就是边牧的。"""
        base = default if default is not None else cls()
        try:
            d = json.loads(text or "")
            spec = cls(**{**vars(base), **{k: d[k] for k in ("pattern", "main", "secondary", "swap", "eyes") if k in d}})
            spec.pattern = int(spec.pattern) if 1 <= int(spec.pattern) <= 4 else 1
            return spec
        except (ValueError, TypeError):
            return cls(**vars(base))


# ---------- 小工具 ----------
def _lut_apply(gray: QImage, lut: bytes) -> QImage:
    """灰度图按 256 项查找表映射。"""
    g = gray if gray.format() == QImage.Format.Format_Grayscale8 else gray.convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = g.width(), g.height()
    data = bytes(g.constBits())[: g.bytesPerLine() * h]
    out = QImage(data.translate(lut), w, h, g.bytesPerLine(), QImage.Format.Format_Grayscale8).copy()
    return out


def _lut_scale(factor: float) -> bytes:
    return bytes(min(255, int(round(v * factor))) for v in range(256))


def _lut_soft_threshold(t: int, soft: int = SOFT_EDGE) -> bytes:
    """亮度 ≤ t - soft → 255（深色），≥ t + soft → 0，中间线性。"""
    out = []
    for v in range(256):
        if v <= t - soft:
            out.append(255)
        elif v >= t + soft:
            out.append(0)
        else:
            out.append(int(round(255 * (t + soft - v) / (2 * soft))))
    return bytes(out)


def _invert(mask: QImage) -> QImage:
    return _lut_apply(mask, bytes(255 - v for v in range(256)))


def _alpha_image(mask: QImage, size: int) -> QImage:
    """白底、alpha = 遮罩，给 DestinationIn 用。"""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.white)
    img.setAlphaChannel(mask if mask.width() == size else mask.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
    return img


def otsu_threshold(gray: QImage) -> int:
    """大津法：把亮度直方图分成两堆，类间方差最大的阈值。128² 下采样上算，够用。"""
    small = gray.convertToFormat(QImage.Format.Format_Grayscale8).scaled(128, 128, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    data = bytes(small.constBits())[: small.bytesPerLine() * 128]
    hist = [0] * 256
    for y in range(128):
        row = data[y * small.bytesPerLine(): y * small.bytesPerLine() + 128]
        for v in row:
            hist[v] += 1
    total = 128 * 128
    sum_all = sum(i * h for i, h in enumerate(hist))
    best_t, best_var, w_b, sum_b = 128, -1.0, 0, 0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return best_t


# ---------- 遮罩 ----------
def pattern_mask(albedo: QImage, size: int) -> QImage:
    """深色毛的软遮罩（255 = 深色）。"""
    gray = albedo.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format.Format_Grayscale8)
    return _lut_apply(gray, _lut_soft_threshold(otsu_threshold(gray)))


def _uv_mask(model: Model, bones: tuple[str, ...], size: int, dilate: float = 3.0) -> QImage:
    """主要受这些骨头控制的顶点所在的三角形，画到 UV 空间里当遮罩；描一圈边免得接缝漏色。"""
    joint_name = [model.nodes[j].name for j in model.skin_joints]
    mesh = model.mesh
    J, W, UV = mesh.joints, mesh.weights, mesh.uvs
    wanted = set(bones)
    mask = QImage(size, size, QImage.Format.Format_Grayscale8)
    mask.fill(0)
    p = QPainter(mask)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(Qt.white)
    p.setPen(QPen(Qt.white, dilate))
    for t in range(0, mesh.vertex_count, 3):
        hit = False
        for k in range(3):
            v = 4 * (t + k)
            best = max(range(4), key=lambda q: W[v + q])
            if joint_name[int(J[v + best])] in wanted:
                hit = True
                break
        if hit:
            p.drawPolygon(QPolygonF([QPointF(UV[2 * (t + k)] * size, UV[2 * (t + k) + 1] * size) for k in range(3)]))
    p.end()
    return mask


class LazyAlbedos:
    """斑纹 → 原贴图：用到才解码，只留最近用的那一张（四张 2048 全解码常驻，占 64 MB）。
    拖颜色时一直是同一套斑纹，不会反复解码；换斑纹、画四张缩略图时才重新解码。"""

    def __init__(self, load: Callable[[int], Optional[QImage]], patterns: Sequence[int]):
        self._load, self.patterns = load, tuple(patterns)
        self._last: Optional[tuple[int, QImage]] = None

    def get(self, pattern: int) -> Optional[QImage]:
        if pattern not in self.patterns:
            return None
        if self._last is None or self._last[0] != pattern:
            img = self._load(pattern)
            if img is None or img.isNull():
                return None
            self._last = (pattern, img)
        return self._last[1]

    def __getitem__(self, pattern: int) -> QImage:
        img = self.get(pattern)
        if img is None:
            raise KeyError(pattern)
        return img


class CoatPainter:
    """拿着模型和原贴图（字典，或用到才解码的 LazyAlbedos），按 CoatSpec 出新贴图。遮罩只留当前斑纹的。"""

    def __init__(self, model: Model, albedos: dict[int, QImage]):
        self.model = model
        self.albedos = albedos              # pattern → 原贴图（至少要有 1）
        self._pattern_masks: dict[tuple[int, int], QImage] = {}
        self._protected: dict[int, QImage] = {}
        self._eyes: dict[int, QImage] = {}

    def albedo(self, pattern: int) -> QImage:
        return self.albedos.get(pattern) or self.albedos[1]

    def _mask(self, pattern: int, size: int) -> QImage:
        key = (pattern, size)
        if key not in self._pattern_masks:
            self._pattern_masks = {k: m for k, m in self._pattern_masks.items() if k[0] == pattern}   # 换了斑纹，别的斑纹的遮罩不留
            self._pattern_masks[key] = pattern_mask(self.albedo(pattern), size)
        return self._pattern_masks[key]

    def protected_mask(self, size: int) -> QImage:
        if size not in self._protected:
            self._protected[size] = _uv_mask(self.model, PROTECTED_BONES, size)
        return self._protected[size]

    def eye_mask(self, size: int) -> QImage:
        if size not in self._eyes:
            self._eyes[size] = _uv_mask(self.model, EYE_BONES, size, dilate=1.0)
        return self._eyes[size]

    def paint(self, spec: CoatSpec, size: int = 2048) -> QImage:
        base = self.albedo(spec.pattern).scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation) \
            .convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        gray = base.convertToFormat(QImage.Format.Format_Grayscale8)
        dark_detail = _lut_apply(gray, _lut_scale(DARK_BOOST))
        light_detail = _lut_apply(gray, _lut_scale(LIGHT_BOOST))
        mask_dark = self._mask(spec.pattern, size)
        mask_light = _invert(mask_dark)
        if spec.swap:
            mask_dark, mask_light = mask_light, mask_dark
        out = self._tinted(QColor(spec.main), dark_detail, mask_dark, size)
        p = QPainter(out)
        p.drawImage(0, 0, self._tinted(QColor(spec.secondary), light_detail, mask_light, size))
        keep = base.copy()                                   # 保护区用原图
        kp = QPainter(keep)
        kp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        kp.drawImage(0, 0, _alpha_image(self.protected_mask(size), size))
        kp.end()
        p.drawImage(0, 0, keep)
        if spec.eyes:
            layer = QImage(size, size, QImage.Format.Format_ARGB32)
            layer.fill(QColor(spec.eyes))
            layer.setAlphaChannel(self.eye_mask(size))
            p.setCompositionMode(QPainter.CompositionMode_Overlay)   # Qt 没有 Hue 模式；Overlay 给中间调上色，白眼球和黑瞳孔基本不动
            p.drawImage(0, 0, layer)
        p.end()
        return out

    @staticmethod
    def _tinted(color: QColor, detail: QImage, mask: QImage, size: int) -> QImage:
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(color)
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_Multiply)
        p.drawImage(0, 0, detail)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(0, 0, _alpha_image(mask, size))
        p.end()
        return img


def _channel_mask(img: QImage, fn, size: int = 256) -> QImage:
    """按每个像素的 (r, g, b) 算一个 0..255 的数，出一张 size 的灰度图（size² 个像素的 Python 循环，256 时约 0.1 秒，算一次留着）。"""
    im = img.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format.Format_ARGB32)
    bpl = im.bytesPerLine()
    raw = bytes(im.constBits())[: bpl * size]
    vals = bytearray(size * size)
    for y in range(size):
        row = raw[y * bpl: y * bpl + 4 * size]
        for x in range(size):
            v = fn(row[4 * x + 2], row[4 * x + 1], row[4 * x])
            vals[y * size + x] = 0 if v < 0 else 255 if v > 255 else int(v)
    return QImage(bytes(vals), size, size, size, QImage.Format.Format_Grayscale8).copy()


class TintPainter:
    """通体一色的模型（萨摩耶）的自定义毛色：整身染主色，pattern 2「背上一片」再染副色；swap 对调；眼睛单独换色和 CoatPainter 一样。
    细节层、保护区用第 1 套贴图；背上那一片的范围、耳朵里的粉色各算一次（256 上算、放大）留着。和 CoatPainter 一样的用法（paint、protected_mask）。"""
    PATTERNS = 2

    def __init__(self, model: Model, albedos, brightness: float = 1.0, patch_from: int = 3):
        self.model = model
        self.albedos = albedos
        self.brightness = max(0.1, float(brightness))
        self.patch_from = int(patch_from)
        self._base = CoatPainter(model, albedos)            # 保护区、眼睛的遮罩照它的
        self._masks: dict[tuple[str, int], QImage] = {}

    @property
    def albedos(self):
        return self._albedos

    @albedos.setter
    def albedos(self, value) -> None:
        self._albedos = value
        if hasattr(self, "_base"):
            self._base.albedos = value

    def albedo(self, pattern: int = 1) -> QImage:
        return self._base.albedo(1)

    def protected_mask(self, size: int) -> QImage:
        key = ("protected", size)
        if key not in self._masks:
            self._masks[key] = _uv_mask(self.model, TINT_PROTECTED_BONES, size)
        return self._masks[key]

    def eye_mask(self, size: int) -> QImage:
        return self._base.eye_mask(size)

    def _mask(self, kind: str, size: int) -> QImage:
        key = (kind, size)
        if key not in self._masks:
            small = self._masks.get((kind, 256))
            if small is None:
                if kind == "pink":
                    k = 255.0 / max(1, PINK_FULL - PINK_FROM)
                    small = _channel_mask(self._base.albedo(1), lambda r, g, b: (r - g - PINK_FROM) * k)
                else:                                          # 背上那一片：偏黄的地方（(r + g) / 2 − b 大），大津法分界、软边
                    src = self._base.albedos.get(self.patch_from) if hasattr(self._base.albedos, "get") else None
                    yellow = _channel_mask(src if src is not None and not src.isNull() else self._base.albedo(1),
                                           lambda r, g, b: ((r + g) / 2 - b) * 2 + 128)
                    small = _invert(_lut_apply(yellow, _lut_soft_threshold(otsu_threshold(yellow), 10)))
                self._masks[(kind, 256)] = small
            self._masks[key] = small if size == 256 else small.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return self._masks[key]

    def paint(self, spec: CoatSpec, size: int = 2048) -> QImage:
        base = self._base.albedo(1).scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation) \
            .convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        gray = base.convertToFormat(QImage.Format.Format_Grayscale8)
        detail = _lut_apply(gray, _lut_scale(255.0 / (FUR_GRAY * self.brightness)))
        body, patch = (spec.secondary, spec.main) if spec.swap else (spec.main, spec.secondary)
        out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(QColor(body))
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode_Multiply)
        p.drawImage(0, 0, detail)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if spec.pattern == 2:
            p.drawImage(0, 0, CoatPainter._tinted(QColor(patch), detail, self._mask("patch", size), size))
        for mask in (self._mask("pink", size), self.protected_mask(size)):   # 耳朵里的粉、眼鼻舌嘴爪垫：原图
            keep = base.copy()
            kp = QPainter(keep)
            kp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            kp.drawImage(0, 0, _alpha_image(mask, size))
            kp.end()
            p.drawImage(0, 0, keep)
        if spec.eyes:
            layer = QImage(size, size, QImage.Format.Format_ARGB32)
            layer.fill(QColor(spec.eyes))
            layer.setAlphaChannel(self.eye_mask(size))
            p.setCompositionMode(QPainter.CompositionMode_Overlay)
            p.drawImage(0, 0, layer)
        p.end()
        return out
