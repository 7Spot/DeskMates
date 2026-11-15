"""物件（狗窝、盆、公园里的东西）怎么画成图：不带骨架的 .glb（tools/export_things.py 导的）用狗的那套渲染器（widget/render.py，着色器一行不改）画，
样子和狗一样（贴图 × 两档明暗 + 描边）。办法：把静态网格装成渲染器认的 Model——每个顶点只绑第 0 根「骨头」、权重 1，那根骨头的矩阵是单位阵。
这里不碰窗口：读模型、放大、量画面多大、切出前沿、出一张图；摆在哪、什么时候出图在 widget/things.py。

- scale_of、yaw_of：包里写的倍数、角度怎么用（狗窝按狗的身高再乘、尖顶狗屋在屏幕右半边反过来画）。
- load_static：读一个 .glb（按路径记着，同一个文件只读一次）。读不出来、没带贴图就抛 ValueError（那一款当作不在）。
- scaled：尺寸乘 k，烤进顶点。放大写进根矩阵的话描边跟着变粗，和狗不一样（描边是模型空间里的 render.OUTLINE 米）。
- layout：转过 yaw 度、按 ppm 画，画面多大、物件正中和脚下那条线在图里哪；纯几何，没有显卡也有数。
  锚点是画出来最低的那一点（斜着摆的狗屋靠镜头的那个角比模型原点低，原点对线的话底下一截伸到线下面去）。
  影子就是渲染器自己的接触阴影，按物件贴地那一圈的方框算，和物件在同一张图里。
- front_part：只留靠镜头的那些面（窝的前沿，狗趴在窝里时盖在狗前面的那一层）。
- shoot：借一块画布（狗的 DogView，或者不上屏的 Studio）出图。每个模型现建一套渲染器，画完就放（渲染器在显卡上建的东西不归 Python 管）。
  没有显卡（offscreen 平台的单测、画布还没画过第一帧）返回空图。
- Studio：没有狗的窗口时出图用的不上屏画布（tools/render_still.py --thing、tools/render_thing_thumbs.py）；用完 close()。"""
from __future__ import annotations

import json
import math
import struct
from array import array
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPolygonF

from widget.dogctl import Pose
from widget.dogview import Darkroom
from widget.gltf import _COMPONENT, _TYPE_N, IDENTITY, Mesh, Model, Node, rot_y_mat
from widget.render import ELEVATION, OUTLINE, DogRenderer, Frame, make_frame

PET_REF_M = 0.8           # fit_pet 的款（狗窝）倍数是按这么高的狗（边牧）定的，别的狗按身高比再乘
PAD_PX = 6.0              # 图四周留的透明边（逻辑像素）：duang 压扁时横向鼓出来的那一点不被裁
FOOT_BELOW_M = 0.05       # 离地这么高以内的顶点算贴地的那一圈（影子按它们的方框算）


def scale_of(spec, pet_height_m: float = PET_REF_M) -> float:
    """这一款放大多少倍（包里的 scale；fit_pet 的再乘现在这只狗的身高比）。"""
    k = float(spec.get("scale", 1.0))
    return k * pet_height_m / PET_REF_M if spec.get("fit_pet") else k


def yaw_of(spec, right_half: bool = False) -> float:
    """这一款朝哪个角度画（包里的 yaw，度）；mirror 的款在屏幕右半边按 −yaw 画（尖顶狗屋的门朝屏幕中间；是真的重画，光照还从左上来）。"""
    yaw = float(spec.get("yaw", 0.0))
    return -yaw if right_half and spec.get("mirror") else yaw


def load_static(path) -> Model:
    """不带骨架的 glb（一个网格、可以有几个 primitive、一张颜色贴图）→ Model。同一个文件只读一次。"""
    return _load(str(path))


@lru_cache(maxsize=None)
def _load(path: str) -> Model:
    try:
        return _read(Path(path).read_bytes())
    except (OSError, KeyError, IndexError, TypeError, struct.error, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc!r}") from exc


def _read(raw: bytes) -> Model:
    magic, version, _ = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError("not a glTF 2.0 binary")
    json_len, _ = struct.unpack_from("<II", raw, 12)
    j = json.loads(raw[20:20 + json_len])
    bin_off = 20 + json_len
    bin_len, _ = struct.unpack_from("<II", raw, bin_off)
    blob = memoryview(raw)[bin_off + 8: bin_off + 8 + bin_len]

    def accessor(idx: int) -> array:
        acc = j["accessors"][idx]
        view = j["bufferViews"][acc["bufferView"]]
        fmt, size = _COMPONENT[acc["componentType"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        arr = array(fmt)
        arr.frombytes(blob[start: start + acc["count"] * _TYPE_N[acc["type"]] * size].tobytes())
        return arr

    P, N, U = array("f"), array("f"), array("f")
    texture = None
    for node in j["nodes"]:
        if "mesh" not in node:
            continue
        if any(k in node for k in ("translation", "rotation", "scale", "matrix")):
            raise ValueError("node transform not baked in (export with tools/export_things.py)")
        for prim in j["meshes"][node["mesh"]]["primitives"]:
            a = prim["attributes"]
            pos, nrm, uv = accessor(a["POSITION"]), accessor(a["NORMAL"]), accessor(a["TEXCOORD_0"])
            for i in (accessor(prim["indices"]) if "indices" in prim else range(len(pos) // 3)):
                P.extend(pos[3 * i:3 * i + 3])
                N.extend(nrm[3 * i:3 * i + 3])
                U.extend(uv[2 * i:2 * i + 2])
            ref = j["materials"][prim["material"]].get("pbrMetallicRoughness", {}).get("baseColorTexture") if "material" in prim else None
            if ref is not None and texture is None:
                view = j["bufferViews"][j["images"][j["textures"][ref["index"]]["source"]]["bufferView"]]
                texture = blob[view.get("byteOffset", 0): view.get("byteOffset", 0) + view["byteLength"]].tobytes()
    if not P:
        raise ValueError("no mesh")
    if texture is None:
        raise ValueError("no color texture")
    return _model(P, N, U, texture)


def _model(P: array, N: array, U: array, texture: Optional[bytes]) -> Model:
    """静态网格 → 渲染器认的 Model：关节全是第 0 根、权重 (1, 0, 0, 0)，一个节点、一根单位阵的「骨头」，没有片段。"""
    n = len(P) // 3
    bounds = (tuple(min(P[k::3]) for k in range(3)), tuple(max(P[k::3]) for k in range(3)))
    mesh = Mesh(n, n, P, N, U, array("f", bytes(16 * n)), array("f", [1.0, 0.0, 0.0, 0.0] * n), bounds)
    nodes = [Node("thing", 0, None, [], (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0), 0, None)]
    return Model(nodes, [0], mesh, 0, [0], [IDENTITY], {}, texture)


def scaled(model: Model, k: float) -> Model:
    """尺寸乘 k，烤进顶点（描边照旧按米算，不跟着变粗）。k 是 1 就是原来那个。"""
    if abs(k - 1.0) < 1e-6:
        return model
    m = model.mesh
    lo, hi = m.bounds
    mesh = Mesh(m.vertex_count, m.index_count, array("f", [v * k for v in m.positions]), m.normals, m.uvs, m.joints, m.weights,
                (tuple(v * k for v in lo), tuple(v * k for v in hi)))
    return Model(model.nodes, model.roots, mesh, 0, [0], [IDENTITY], {}, model.texture_png)


def front_part(model: Model, z_cut: float) -> Model:
    """只留靠镜头这一侧的三角面（三个顶点的 z 都比 z_cut 大）：窝的前沿。包围盒照整件的（和整件用同一个 layout，两张图对得上）。"""
    m = model.mesh
    P, N, U = array("f"), array("f"), array("f")
    for t in range(0, m.vertex_count, 3):
        if min(m.positions[3 * (t + i) + 2] for i in range(3)) > z_cut:
            P.extend(m.positions[3 * t:3 * t + 9])
            N.extend(m.normals[3 * t:3 * t + 9])
            U.extend(m.uvs[2 * t:2 * t + 6])
    n = len(P) // 3
    mesh = Mesh(n, n, P, N, U, array("f", bytes(16 * n)), array("f", [1.0, 0.0, 0.0, 0.0] * n), m.bounds)
    return Model(model.nodes, model.roots, mesh, 0, [0], [IDENTITY], {}, model.texture_png)


RIM_LIFT_PX = 1.5          # 盆沿那道弧线往上多留这么多（逻辑像素）：盆沿的描边线也算在前面那一层里


def rim_front(whole: QImage, lay: "Layout", r_m: float, y_m: float) -> QImage:
    """盆的前沿那一层（包里 front_rim：吃饭时整个鼻子埋进去、只剩眼睛）：整件那张图只留近处盆沿那道弧线以下——盆壁、盆底；
    粮、水面在弧线上面的不留，鼻子扎进盆里露在盆沿上面、下巴在盆壁后面。盆沿是半径 r_m、高 y_m 的圆（米，已乘倍数），俯视 ELEVATION 度时
    近的那半圈在画面上是半个椭圆。别按模型切（front_z，三个顶点都在切线前面的三角面才留）：切在盆中心近的半堆粮也盖在狗前面；切到盆壁，
    盆壁上的三角面一块块缺，露出后面的狗。whole 是整件按 lay 出的图（带像素密度），出来的图一样大。"""
    out = QImage(whole.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.setDevicePixelRatio(whole.devicePixelRatio())
    out.fill(Qt.transparent)
    e = math.radians(ELEVATION)
    ppm, ground = lay.frame.ppm, lay.frame.ground_px
    pts = []
    n = 48
    for i in range(n + 1):
        x = -r_m + 2.0 * r_m * i / n
        up = y_m * math.cos(e) - math.sqrt(max(0.0, r_m * r_m - x * x)) * math.sin(e)
        pts.append(QPointF(lay.cx + x * ppm, lay.h - (ground + up * ppm) - RIM_LIFT_PX))
    pts += [QPointF(lay.cx + r_m * ppm, lay.h), QPointF(lay.cx - r_m * ppm, lay.h)]
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setClipPath(path)
    p.drawImage(0, 0, whole)
    p.end()
    return out


def extent(model: Model, yaw: float) -> tuple[float, float, float, float]:
    """转了 yaw 度以后在画面上占多大（米）：(左, 右, 下, 上)，从模型原点（横向正中、底面）量；相机俯视 ELEVATION 度，靠镜头的角比原点低。"""
    return _spans(model, yaw)[:4]


def _spans(model: Model, yaw: float) -> tuple[float, ...]:
    """(左, 右, 下, 上, 贴地那一圈的 x 小, x 大, z 小, z 大)。贴地的一圈都没有（悬空的模型）：后四个是 0。"""
    m = rot_y_mat(yaw)
    e = math.radians(ELEVATION)
    c, s = math.cos(e), math.sin(e)
    P = model.mesh.positions
    x0 = y0 = fx0 = fz0 = math.inf
    x1 = y1 = fx1 = fz1 = -math.inf
    for i in range(0, len(P), 3):
        x, y, z = P[i], P[i + 1], P[i + 2]
        wx, wz = m[0] * x + m[8] * z, m[2] * x + m[10] * z
        sy = y * c - wz * s
        x0, x1, y0, y1 = min(x0, wx), max(x1, wx), min(y0, sy), max(y1, sy)
        if y < FOOT_BELOW_M:
            fx0, fx1, fz0, fz1 = min(fx0, wx), max(fx1, wx), min(fz0, wz), max(fz1, wz)
    if fx0 > fx1:
        fx0 = fx1 = fz0 = fz1 = 0.0
    return x0, x1, y0, y1, fx0, fx1, fz0, fz1


@dataclass(frozen=True)
class Layout:
    """一件物件按某个角度、某个比例尺画出来的画面。长度是逻辑像素，从图的左边 / 底边量；带 _m 的是米。"""
    frame: Frame          # 渲染器要的那一帧
    w: int                # 画面多大
    h: int
    cx: float             # 模型原点（物件正中）离图左多少
    base: float           # 物件画出来最低的那一点离图底多少：这一点落在它踩的那条线上
    low_m: float          # 模型原点比最低的那一点高多少（台面、垫子在屏幕上多高要加上它）
    left_m: float         # 物件本身（不算影子）在原点左边、右边、最低点上面各占多少
    right_m: float
    top_m: float

    def box(self) -> tuple[float, float, float, float]:
        """物件本身（不算影子、描边）在图里的方框：(左, 上, 宽, 高)，从图的左上角量。没出图时点击范围用它。"""
        ppm = self.frame.ppm
        return (self.cx - self.left_m * ppm, self.h - self.base - self.top_m * ppm, (self.left_m + self.right_m) * ppm, self.top_m * ppm)


def layout(model: Model, yaw: float, ppm: float, shadow: bool = True) -> Layout:
    """这件物件转 yaw 度、按 ppm（像素 / 米）画。画面 = 物件（连影子）+ 两边各一道描边 + 四周 PAD_PX。"""
    x0, x1, y0, y1, fx0, fx1, fz0, fz1 = _spans(model, yaw)
    left, right, low, high = x0, x1, y0, y1
    foot: list[tuple[float, float]] = []
    if shadow and (fx1 > fx0 or fz1 > fz0):
        foot = [(fx0, fz0), (fx1, fz0), (fx0, fz1), (fx1, fz1)]
        s = math.sin(math.radians(ELEVATION))
        rx = (fx1 - fx0) / 2 * 0.95 + 0.04                     # 和 geometry.shadow_ellipse 同一个算法：影子椭圆占到哪，画面就留到哪
        ry = max((fz1 - fz0) / 2 * s + 0.03, rx * 0.18)
        mx, my = (fx0 + fx1) / 2, -(fz0 + fz1) / 2 * s
        left, right, low, high = min(left, mx - rx), max(right, mx + rx), min(low, my - ry), max(high, my + ry)
    w = math.ceil((right - left + 2 * OUTLINE) * ppm + 2 * PAD_PX)
    h = math.ceil((high - low + 2 * OUTLINE) * ppm + 2 * PAD_PX)
    ground = PAD_PX + (OUTLINE - low) * ppm                    # 模型原点那条线（世界 y = 0、z = 0）离图底
    cx = PAD_PX + (OUTLINE - left) * ppm
    pose = Pose(rot_y_mat(yaw), [IDENTITY], [IDENTITY], foot, 0.0)
    frame = make_frame(pose, 0.0, ppm, ground, w, (cx - w / 2.0, 0.0))
    return Layout(frame, w, h, cx, ground + y0 * ppm, -y0, -x0, x1, y1 - y0)


def shoot(view, model: Model, lay: Layout, dpr: float = 1.0) -> QImage:
    """借 view（DogView 或 Studio）的画布把这件物件画成图：lay.w × lay.h 逻辑像素的 dpr 倍，预乘 alpha。
    画布还没好（没画过第一帧、offscreen 平台没有显卡）返回空图。渲染器现建、画完就放：它建在显卡上的东西得在画布没了之前放掉，不留着。"""
    ready = getattr(view, "ready", None)
    if view is None or (ready is not None and not ready()):
        return QImage()
    renderer = DogRenderer(model)
    try:
        return view.shoot(lay.frame, lay.w, lay.h, dpr, shooter=renderer)
    finally:
        renderer.release()


class Studio(Darkroom):
    """不上屏的画布：没有狗的窗口时出物件的图（tools/ 里的出图工具）。有活才开，出完 close()——开着的时候它是一个「显示着」的顶层控件。"""

    def __init__(self):
        super().__init__(_model(array("f", [0.0] * 9), array("f", [0.0, 0.0, 1.0] * 3), array("f", [0.0] * 6), None))   # 画布自己那套渲染器用不上，给它一个三角形

    def shoot_thing(self, model: Model, lay: Layout, dpr: float = 1.0) -> QImage:
        return shoot(self, model, lay, dpr)
