"""读 GLB（glTF 2.0 二进制）：网格、骨架、蒙皮、动画、贴图。纯 Python，只用标准库。

只支持我们自己用 Blender 导出的这种文件：一个带 skin 的网格，float32 属性，uint8 关节索引，uint16/uint32 索引，
动画每个通道是 translation / rotation / scale，STEP 或 LINEAR 插值。
"""
from __future__ import annotations

import json
import math
import struct
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]   # x, y, z, w（glTF 顺序）
Mat4 = tuple[float, ...]                   # 16 个数，列主序（glTF / OpenGL 顺序）

_COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_TYPE_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


@dataclass
class Node:
    name: str
    index: int
    parent: Optional[int]
    children: list[int]
    translation: Vec3
    rotation: Quat
    scale: Vec3
    mesh: Optional[int] = None
    skin: Optional[int] = None


@dataclass
class Channel:
    node: int
    path: str                 # "translation" | "rotation" | "scale"
    interpolation: str        # "STEP" | "LINEAR"
    times: array              # float32，升序
    values: array             # float32 平铺：每个关键帧 stride 个数（位置 / 缩放 3，旋转 4）。以前每帧一个元组，20 万个占 50 多 MB
    stride: int

    def key(self, i: int) -> tuple:
        """第 i 个关键帧的值。"""
        k = i * self.stride
        return tuple(self.values[k:k + self.stride])


@dataclass
class Clip:
    name: str
    duration: float
    channels: list[Channel]


@dataclass
class Mesh:
    vertex_count: int
    index_count: int
    positions: array          # float32 x3，按索引展开后的顺序
    normals: array
    uvs: array
    joints: array             # float32 x4（关节索引，用 float 传给着色器）
    weights: array            # float32 x4
    bounds: tuple[Vec3, Vec3] = field(default_factory=lambda: ((0, 0, 0), (0, 0, 0)))


@dataclass
class Model:
    nodes: list[Node]
    roots: list[int]
    mesh: Mesh
    mesh_node: int
    skin_joints: list[int]            # 关节 → 节点索引
    inverse_bind: list[Mat4]
    clips: dict[str, Clip]
    texture_png: Optional[bytes]      # 内嵌的颜色贴图（图片文件的字节，多半是 PNG；按内容认格式，look.decode_png）
    bone_fallback: dict[str, str] = field(default_factory=dict)   # 这根骨头没有时用哪根（widget/packs.py）
    gain: float = 1.0                 # 贴图整体提亮多少倍（模型包的 brightness，widget/packs.py 写；widget/render.py 传给着色器）
    mouth_offset: Optional[Vec3] = None                           # 叼着的东西相对头骨放哪（模型包的 mouth_offset；None = widget/props.py 的 MOUTH_OFFSET）
    jump_arcs: dict[str, tuple[float, float]] = field(default_factory=dict)   # 哪种跳法的腾空区间按这个模型改（模型包的 jumps；widget/clips.py 的 jumps_for）
    measured: dict[str, Any] = field(default_factory=dict)       # 按这个模型量一次就记着的（measured / table 取）：片段最高点、脚和骨盆、趴着的身长、拎起来的姿势、
                                                                 # 鼻子最低那一刻、跳法的数、渲染器的顶点表和描边表。记在模型上，新建的控制器、渲染器不重量；
                                                                 # 别的模型由 widget/kits.py 在后台先量好（换模型不重启）

    def node_by_name(self, name: str) -> Node:
        n = next((n for n in self.nodes if n.name == name), None)
        if n is None and name in self.bone_fallback:
            return self.node_by_name(self.bone_fallback[name])
        if n is None:
            raise KeyError(name)
        return n

    def node_index(self, name: str) -> Optional[int]:
        """这根骨头的序号；没有 None（不走 bone_fallback：可有可无的骨头用这个）。"""
        return next((n.index for n in self.nodes if n.name == name), None)


T = TypeVar("T")


def measured(model, key: str, make: Callable[[], T]) -> T:
    """按这个模型量一次的东西（Model.measured[key]）：记过直接给，没记过现量 make() 再记上。不是 Model 的假模型（单测里的）每次现量。"""
    store = getattr(model, "measured", None)
    if store is None:
        return make()
    got = store.get(key)
    if got is None:
        got = store[key] = make()
    return got


def table(model, key: str) -> dict:
    """按这个模型一项一项记的表（片段 → 最高点这种，用到哪项量哪项）：同一个模型的控制器共用这一张。假模型给一张新的。"""
    store = getattr(model, "measured", None)
    return {} if store is None else store.setdefault(key, {})


def transform_point(m: Mat4, p: Vec3) -> Vec3:
    """列主序矩阵 · 点。"""
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def load(path: str | Path) -> Model:
    raw = Path(path).read_bytes()
    magic, version, _length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError(f"{path}: not a glTF 2.0 binary")
    json_len, json_type = struct.unpack_from("<II", raw, 12)
    j = json.loads(raw[20:20 + json_len])
    bin_off = 20 + json_len
    bin_len, _bin_type = struct.unpack_from("<II", raw, bin_off)
    blob = memoryview(raw)[bin_off + 8: bin_off + 8 + bin_len]

    def accessor(idx: int) -> list[tuple]:
        acc = j["accessors"][idx]
        bv = j["bufferViews"][acc["bufferView"]]
        fmt, size = _COMPONENT[acc["componentType"]]
        n = _TYPE_N[acc["type"]]
        count = acc["count"]
        start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride", n * size)
        out = []
        if stride == n * size:
            arr = array(fmt)
            arr.frombytes(blob[start: start + count * n * size].tobytes())
            out = [tuple(arr[i * n:(i + 1) * n]) for i in range(count)]
        else:
            for i in range(count):
                o = start + i * stride
                out.append(struct.unpack_from("<" + fmt * n, blob, o))
        if acc.get("normalized") and fmt in "Bb":
            out = [tuple(v / 255.0 for v in t) for t in out]
        return out

    def floats(idx: int) -> tuple[array, int]:
        """动画数据：整块读成一个 float32 数组（每个元素 n 个数），不拆成元组。不是紧排的 float 就照常读再摊平（我们导出的文件不会这样）。"""
        acc = j["accessors"][idx]
        bv = j["bufferViews"][acc["bufferView"]]
        fmt, size = _COMPONENT[acc["componentType"]]
        n = _TYPE_N[acc["type"]]
        start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        if fmt != "f" or bv.get("byteStride", n * size) != n * size:
            return array("f", [v for t in accessor(idx) for v in t]), n
        arr = array("f")
        arr.frombytes(blob[start: start + acc["count"] * n * size].tobytes())
        return arr, n

    # ---- 节点 ----
    nodes: list[Node] = []
    for i, nd in enumerate(j["nodes"]):
        nodes.append(Node(nd.get("name", f"node{i}"), i, None, list(nd.get("children", [])),
                          tuple(nd.get("translation", (0.0, 0.0, 0.0))), tuple(nd.get("rotation", (0.0, 0.0, 0.0, 1.0))),
                          tuple(nd.get("scale", (1.0, 1.0, 1.0))), nd.get("mesh"), nd.get("skin")))
    for n in nodes:
        for c in n.children:
            nodes[c].parent = n.index
    roots = j["scenes"][j.get("scene", 0)]["nodes"]

    # ---- 网格（按索引展开成非索引三角形列表）----
    mesh_node = next(n for n in nodes if n.mesh is not None)
    prim = j["meshes"][mesh_node.mesh]["primitives"][0]
    attrs = prim["attributes"]
    pos = accessor(attrs["POSITION"])
    nrm = accessor(attrs["NORMAL"])
    uv = accessor(attrs["TEXCOORD_0"])
    jnt = accessor(attrs["JOINTS_0"])
    wgt = accessor(attrs["WEIGHTS_0"])
    idx = [t[0] for t in accessor(prim["indices"])] if "indices" in prim else list(range(len(pos)))
    P, N, U, Jn, W = array("f"), array("f"), array("f"), array("f"), array("f")
    for i in idx:
        P.extend(pos[i]); N.extend(nrm[i]); U.extend(uv[i]); Jn.extend(float(v) for v in jnt[i]); W.extend(wgt[i])
    lo = tuple(min(p[k] for p in pos) for k in range(3))
    hi = tuple(max(p[k] for p in pos) for k in range(3))
    mesh = Mesh(len(idx), len(idx), P, N, U, Jn, W, (lo, hi))

    # ---- 蒙皮 ----
    skin = j["skins"][mesh_node.skin]
    ibm = [tuple(m) for m in accessor(skin["inverseBindMatrices"])]

    # ---- 动画 ----
    clips: dict[str, Clip] = {}
    for a in j.get("animations", []):
        chans: list[Channel] = []
        duration = 0.0
        for ch in a["channels"]:
            smp = a["samplers"][ch["sampler"]]
            times, _ = floats(smp["input"])
            values, stride = floats(smp["output"])
            chans.append(Channel(ch["target"]["node"], ch["target"]["path"], smp.get("interpolation", "LINEAR"), times, values, stride))
            duration = max(duration, times[-1] if times else 0.0)
        clips[a["name"]] = Clip(a["name"], duration, chans)

    # ---- 贴图 ----
    png = None
    mat = j["materials"][prim.get("material", 0)] if j.get("materials") else {}
    tex_ref = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
    if tex_ref is not None:
        src = j["textures"][tex_ref["index"]]["source"]
        img = j["images"][src]
        bv = j["bufferViews"][img["bufferView"]]
        png = blob[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]].tobytes()

    return Model(nodes, roots, mesh, mesh_node.index, list(skin["joints"]), ibm, clips, png)


# ---------- 4x4 矩阵（列主序 16 元组）和四元数 ----------

IDENTITY: Mat4 = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def mat_mul(a: Mat4, b: Mat4) -> Mat4:
    """a · b，列主序。展开写（每帧要乘一两百次，生成器写法是 Python 每帧最大的一块开销）。"""
    a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15 = a
    b0, b1, b2, b3, b4, b5, b6, b7, b8, b9, b10, b11, b12, b13, b14, b15 = b
    return (
        a0 * b0 + a4 * b1 + a8 * b2 + a12 * b3, a1 * b0 + a5 * b1 + a9 * b2 + a13 * b3,
        a2 * b0 + a6 * b1 + a10 * b2 + a14 * b3, a3 * b0 + a7 * b1 + a11 * b2 + a15 * b3,
        a0 * b4 + a4 * b5 + a8 * b6 + a12 * b7, a1 * b4 + a5 * b5 + a9 * b6 + a13 * b7,
        a2 * b4 + a6 * b5 + a10 * b6 + a14 * b7, a3 * b4 + a7 * b5 + a11 * b6 + a15 * b7,
        a0 * b8 + a4 * b9 + a8 * b10 + a12 * b11, a1 * b8 + a5 * b9 + a9 * b10 + a13 * b11,
        a2 * b8 + a6 * b9 + a10 * b10 + a14 * b11, a3 * b8 + a7 * b9 + a11 * b10 + a15 * b11,
        a0 * b12 + a4 * b13 + a8 * b14 + a12 * b15, a1 * b12 + a5 * b13 + a9 * b14 + a13 * b15,
        a2 * b12 + a6 * b13 + a10 * b14 + a14 * b15, a3 * b12 + a7 * b13 + a11 * b14 + a15 * b15,
    )


def trs(t: Vec3, q: Quat, s: Vec3) -> Mat4:
    x, y, z, w = q
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz, wx, wy, wz = x * y, x * z, y * z, w * x, w * y, w * z
    sx, sy, sz = s
    return (
        (1 - 2 * (yy + zz)) * sx, (2 * (xy + wz)) * sx, (2 * (xz - wy)) * sx, 0.0,
        (2 * (xy - wz)) * sy, (1 - 2 * (xx + zz)) * sy, (2 * (yz + wx)) * sy, 0.0,
        (2 * (xz + wy)) * sz, (2 * (yz - wx)) * sz, (1 - 2 * (xx + yy)) * sz, 0.0,
        t[0], t[1], t[2], 1.0,
    )


def rot_y_mat(deg: float) -> Mat4:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1)


def rot_x_mat(deg: float) -> Mat4:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1)


def slerp(a: Quat, b: Quat, u: float) -> Quat:
    d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    if d < 0:
        b, d = (-b[0], -b[1], -b[2], -b[3]), -d
    if d > 0.9995:
        q = tuple(a[i] + (b[i] - a[i]) * u for i in range(4))
        n = math.sqrt(sum(v * v for v in q))
        return tuple(v / n for v in q)
    th = math.acos(d)
    s = math.sin(th)
    wa, wb = math.sin((1 - u) * th) / s, math.sin(u * th) / s
    return tuple(a[i] * wa + b[i] * wb for i in range(4))
