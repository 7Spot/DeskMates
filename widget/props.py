"""道具（吃 / 喝有盆、叼着 / 捡起放下有骨头、捡回有球）。球、骨头是程序生成的小模型；盆用买来的饭盆、水盆
（模型里自带的那两个——灵动交互里摆的物件也是它们，满的那个样子、包里写的大小），买来的模型不在时退回程序画的旋转体。
和狗同一套三渲二画法（平涂或贴图 × 两档明暗 + 反向外壳描边，widget/render.py 画；这里只管形状、什么时候出现、放在哪）。

什么时候出现由控制器明确告诉它（别按正在播的片段名 + 临时的活动标签猜：换姿势这条路会漏）：
带道具的动作 / 状态（clips.Action.prop / Plan.prop）开始时 begin(kind)，正常做完 finish()，任何打断 —— 一刀切、换姿势、换状态、开关模式 —— cut()。
- 盆：begin 时就在鼻子要够到的地上淡入（位置 = Eat_loop 里鼻子最低那一刻投到地面，按模型量不写死）；finish / cut 淡出；喝水的是水盆，吃东西的是饭盆。
  买来的两个盆（bought）在后台线程读、解贴图：建第一个 Props 时开始，到真画盆时早读好了（没读完就等它）。
- 骨头 / 球：Pick_up 一开始在鼻子要够到的地上淡入，鼻子最低那一刻挂到嘴上，Pick_up_idle 一直叼着，同一个活动里片段换成转身、跑（捡回）照样叼着，
  Put_down 鼻子最低那一刻放回地上；finish 后在地上停 LINGER 秒再淡出；cut 一律 0.3 秒直接淡出，不在地上停。捡回用球，其余骨头。
位置：地上的记世界坐标（狗转身、走开它不跟着动）；叼着的挂在头骨上（嘴角前一点，头怎么动都跟着）。
尺寸按模型量：狗宽 0.26 米、鼻子离地 0.52 米；买来的饭盆直径 0.29、高 0.09，水盆直径 0.20、水面高 0.045（程序画的盆直径 0.20）；
吃、喝时鼻子最低离地 0.06～0.07 米、正对盆心，前爪离盆心至少 0.23 米（两只狗都是，tests/test_props.py 量）。球直径 0.09、骨头长 0.15。"""
from __future__ import annotations

import logging
import math
from array import array
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from widget.anim import Player
from widget.gltf import IDENTITY, Mat4, Model, mat_mul, rot_y_mat, table, transform_point

log = logging.getLogger(__name__)

FADE_IN, FADE_OUT, LINGER = 0.25, 0.3, 3.0      # 淡入 / 淡出秒数；放下后在地上停多久
EAT_CLIPS = ("EatDrink_start", "Eat_loop", "Eat_tear", "Drink_loop", "EatDrink_end")
CARRY_CLIPS = ("Pick_up", "Pick_up_idle", "Put_down")
MOUTH_OFFSET = (0.0, 0.105, -0.03)             # 叼着的东西相对头骨的位置（头骨局部坐标：Y 朝前、Z 朝上）：嘴角前一点、鼻子下面一点。边牧的；别的模型在包里写 mouth_offset（Props.mouth）
BOWL_R, BOWL_H = 0.10, 0.05
BALL_R = 0.045
SEAM_COLOR = (1.0, 0.925, 0.87)                # 球的缝线（2D 的球、狗嘴里的 3D 球一个色）
SEAM_WAVE = 0.55                                # 缝线上下起伏多大（弧度）
BONE_LEN, BONE_R, KNOB_R = 0.11, 0.013, 0.022   # 两端球心的距离、杆的半径、端头球的半径
COLORS = {"bowl": (0.43, 0.56, 0.68), "water": (0.56, 0.76, 0.91), "food": (0.54, 0.35, 0.24), "bone": (0.95, 0.91, 0.84), "ball": (0.85, 0.33, 0.25)}


@dataclass(frozen=True)
class Mesh:
    positions: array      # 三角形顶点，x y z 连着放
    normals: array

    @property
    def count(self) -> int:
        return len(self.positions) // 3


@dataclass(frozen=True)
class PropDraw:
    """一帧要画的一个道具零件：哪块网格、世界矩阵、平涂的颜色、透明度。"""
    mesh: str
    matrix: Mat4
    color: tuple[float, float, float]
    alpha: float


# ---------------- 形状 ----------------
def _tri(pos: array, nor: array, a, b, c, na, nb, nc) -> None:
    pos.extend(a); pos.extend(b); pos.extend(c)
    nor.extend(na); nor.extend(nb); nor.extend(nc)


def revolve(profile: list[tuple[float, float]], segments: int = 32) -> Mesh:
    """把 (半径, 高度) 的折线绕 Y 轴转一圈。法线取折线的外法向（平滑），两端半径为 0 的点是极点。"""
    pos, nor = array("f"), array("f")
    normals2d = []
    for i in range(len(profile) - 1):
        (r0, y0), (r1, y1) = profile[i], profile[i + 1]
        dr, dy = r1 - r0, y1 - y0
        n = math.hypot(dr, dy) or 1.0
        normals2d.append((dy / n, -dr / n))                    # 外法向：沿折线前进方向转 -90°
    vert_n = []                                                # 每个折点的法向：相邻两段平均
    for i in range(len(profile)):
        parts = [normals2d[j] for j in (i - 1, i) if 0 <= j < len(normals2d)]
        nx, ny = sum(p[0] for p in parts), sum(p[1] for p in parts)
        n = math.hypot(nx, ny) or 1.0
        vert_n.append((nx / n, ny / n))
    for i in range(len(profile) - 1):
        (r0, y0), (r1, y1) = profile[i], profile[i + 1]
        (nr0, ny0), (nr1, ny1) = vert_n[i], vert_n[i + 1]
        for s in range(segments):
            a0, a1 = 2 * math.pi * s / segments, 2 * math.pi * (s + 1) / segments
            c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
            p00, p01 = (r0 * c0, y0, r0 * s0), (r0 * c1, y0, r0 * s1)
            p10, p11 = (r1 * c0, y1, r1 * s0), (r1 * c1, y1, r1 * s1)
            n00, n01 = (nr0 * c0, ny0, nr0 * s0), (nr0 * c1, ny0, nr0 * s1)
            n10, n11 = (nr1 * c0, ny1, nr1 * s0), (nr1 * c1, ny1, nr1 * s1)
            if r0 > 1e-9:
                _tri(pos, nor, p00, p10, p01, n00, n10, n01)
            if r1 > 1e-9:
                _tri(pos, nor, p01, p10, p11, n01, n10, n11)
    return Mesh(pos, nor)


def sphere(r: float, center=(0.0, 0.0, 0.0), rings: int = 10, segments: int = 20) -> Mesh:
    profile = [(r * math.sin(math.pi * i / rings), -r * math.cos(math.pi * i / rings)) for i in range(rings + 1)]
    m = revolve(profile, segments)
    cx, cy, cz = center
    pos = array("f", [v + (cx, cy, cz)[i % 3] for i, v in enumerate(m.positions)])
    return Mesh(pos, m.normals)


def merge(*meshes: Mesh) -> Mesh:
    pos, nor = array("f"), array("f")
    for m in meshes:
        pos.extend(m.positions)
        nor.extend(m.normals)
    return Mesh(pos, nor)


def bowl_mesh() -> Mesh:
    """狗盆：外壁、卷边、内壁、内底（底面朝下也封上）。"""
    r, h = BOWL_R, BOWL_H
    return revolve([(0.0, 0.0), (r * 0.85, 0.0), (r, h * 0.85), (r * 0.94, h), (r * 0.78, h * 0.9), (r * 0.66, h * 0.28), (0.0, h * 0.28)])


def fill_mesh() -> Mesh:
    """盆里的东西（水 / 粮）：一片平的圆面，比内壁小一圈。"""
    return revolve([(0.0, BOWL_H * 0.66), (BOWL_R * 0.72, BOWL_H * 0.66)])


def ball_mesh() -> Mesh:
    return sphere(BALL_R)


def ball_seam_mesh() -> Mesh:
    """球上的缝线：绕球一圈的一条窄带，上下起伏（像网球的缝），从哪个方向看都是一道 S 形的弧。贴着球面、比球面略高一点，不描边（render.NO_OUTLINE）。"""
    n, r, half = 72, BALL_R * 1.012, BALL_R * 0.065
    pos, nor = array("f"), array("f")

    def on_sphere(a: float, up: float) -> tuple[float, float, float]:
        lat = SEAM_WAVE * math.sin(2.0 * a) + up
        return (math.cos(lat) * math.cos(a), math.sin(lat), math.cos(lat) * math.sin(a))

    for i in range(n):
        a0, a1 = 2.0 * math.pi * i / n, 2.0 * math.pi * (i + 1) / n
        d = half / r
        pa, pb, pc, pd = on_sphere(a0, -d), on_sphere(a0, d), on_sphere(a1, d), on_sphere(a1, -d)
        for tri in ((pa, pb, pc), (pa, pc, pd)):
            for v in tri:
                pos.extend(c * r for c in v)
                nor.extend(v)
    return Mesh(pos, nor)


def bone_mesh() -> Mesh:
    """卡通骨头：沿 X 的杆，两头各两个球（在 XZ 平面里，躺在地上是平的；叼着时 Z 对着头的上下）。"""
    half = BONE_LEN / 2
    shaft = revolve([(0.0, -half), (BONE_R, -half), (BONE_R, half), (0.0, half)], 16)     # 沿 Y 的圆柱，下面转成沿 X
    pos = array("f")
    for i in range(0, len(shaft.positions), 3):
        x, y, z = shaft.positions[i:i + 3]
        pos.extend((y, x, z))                                   # Y → X
    nor = array("f")
    for i in range(0, len(shaft.normals), 3):
        x, y, z = shaft.normals[i:i + 3]
        nor.extend((y, x, z))
    knobs = [sphere(KNOB_R, (sx * half, 0.0, sz * KNOB_R * 0.72), 8, 16) for sx in (-1, 1) for sz in (-1, 1)]
    return merge(Mesh(pos, nor), *knobs)


@lru_cache(maxsize=None)
def meshes() -> dict[str, Mesh]:
    return {"bowl": bowl_mesh(), "fill": fill_mesh(), "ball": ball_mesh(), "ball_seam": ball_seam_mesh(), "bone": bone_mesh()}


# ---------------- 买来的盆（带贴图） ----------------
BOUGHT = {"food": "bowl_food", "water": "bowl_water"}   # 盛什么 → 买来的那个盆在渲染器里叫什么（带贴图的那条路，render._tex_prop）


@dataclass(frozen=True)
class TexMesh:
    """带贴图的道具：三角形顶点、法线、贴图坐标（都按索引展开，和 Mesh 一样），贴图（解码好的 RGBA8888 QImage；两个盆共用一张图，就是同一个对象）。"""
    positions: array
    normals: array
    uvs: array
    image: object

    @property
    def count(self) -> int:
        return len(self.positions) // 3


_bought: Optional[Future] = None


def prepare_bought() -> None:
    """后台线程开始读买来的盆（第一次叫时开始，之后什么都不做）。"""
    global _bought
    if _bought is None:
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bowls")
        _bought = pool.submit(_load_bought)
        pool.shutdown(wait=False)                 # 读完线程就退，不留着


def bought() -> dict[str, TexMesh]:
    """买来的盆：{渲染器里的名字: TexMesh}。没读完就等它读完；模型不在、读不出来的那个不在里面（用程序画的盆）。"""
    prepare_bought()
    return _bought.result()


def _load_bought() -> dict[str, TexMesh]:
    """后台线程里跑：物件包里饭盆、水盆满的那一款（灵动交互摆的就是它们），按包里写的大小；贴图在这里解码（1024 的图主线程上要十几毫秒）。"""
    out: dict[str, TexMesh] = {}
    try:
        from PySide6.QtGui import QImage
        from widget import packs, thing_art           # 在这里才 import：thing_art 要用渲染器，渲染器又要这个文件
        images: dict[bytes, QImage] = {}
        for style in packs.things():
            name = BOUGHT.get(style.spec.get("serves")) if style.role == "bowl" else None
            if name is None or name in out or style.model is None:
                continue
            try:
                m = thing_art.load_static(style.model)
            except ValueError as exc:
                log.warning("bowl %s skipped: %s", style.key, exc)
                continue
            img = images.get(m.texture_png)
            if img is None:
                img = QImage.fromData(m.texture_png).convertToFormat(QImage.Format_RGBA8888)
                if img.isNull():
                    log.warning("bowl %s skipped: texture can't be decoded", style.key)
                    continue
                images[m.texture_png] = img
            k = thing_art.scale_of(style.spec)
            pos = m.mesh.positions if k == 1.0 else array("f", (v * k for v in m.mesh.positions))
            out[name] = TexMesh(pos, m.mesh.normals, m.mesh.uvs, img)
    except Exception:                                 # noqa: BLE001 —— 读不出来就用程序画的盆，不让动作因此出错
        log.exception("bought bowls failed to load")
    return out


# ---------------- 什么时候出现、放在哪 ----------------
def _translate(x: float, y: float, z: float) -> Mat4:
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1)


class Props:
    """谁在用：控制器在动作 / 状态开始时 begin(kind)、正常做完 finish()、任何打断（一刀切、换姿势、换状态、开关模式）cut()；每帧 update。
    这里不猜现在在做什么，只管道具自己的小状态：盆的淡入淡出；骨头 / 球在地上、嘴里、放下后停着、淡出。"""

    def __init__(self, model: Model):
        prepare_bought()                    # 买来的盆后台先读着，等真吃喝时早好了
        self.model = model
        self.nose = model.node_by_name("nose").index
        self.mouth = tuple(getattr(model, "mouth_offset", None) or MOUTH_OFFSET)   # 叼着的东西相对头骨放哪：模型包写了用它的（头大小不一样）
        self._spots: dict[str, tuple[float, float, float]] = table(model, "nose_spots")   # 片段 → (鼻子最低那一刻的 x, z（模型局部）, 进度)：记在模型上（gltf.Model.measured）
        self.active: Optional[str] = None   # 现在的活动带什么道具（begin 设、finish / cut 清）
        self.bowl: Optional[dict] = None    # {"kind": water / food, "x", "z"（世界）, "alpha", "out"（在淡出）}
        self.item: Optional[dict] = None    # {"kind": bone / ball, "mode": ground / held / linger, "x", "z", "yaw", "alpha", "left"（地上还停几秒）, "out"}

    def spot(self, clip: str) -> tuple[float, float, float]:
        """这段片段里鼻子最低那一刻：(x, z, 进度)，模型局部坐标（狗朝 +Z）。这个模型第一次问到时采样，之后记着（记在模型上）。"""
        if clip not in self._spots:
            c = self.model.clips[clip]
            p = Player(self.model)
            p.play(clip, loop=False, fade=0.0)
            best = None
            n = max(10, int(c.duration * 30))
            for i in range(n + 1):
                p.time = c.duration * i / n
                p.update(0.0)
                g = p.globals(IDENTITY)
                m = g[self.nose]
                if best is None or m[13] < best[1]:
                    best = (i / n, m[13], m[12], m[14])
            self._spots[clip] = (best[2], best[3], best[0])
        return self._spots[clip]

    def _world(self, root: Mat4, x: float, z: float) -> tuple[float, float]:
        wx, _, wz = transform_point(root, (x, 0.0, z))
        return wx, wz

    # ---- 生命周期（控制器调） ----
    def begin(self, kind: str, root: Mat4) -> None:
        """活动开始：盆立刻在鼻子要够到的地上淡入（位置按 Eat_loop 量）；骨头 / 球等 Pick_up 开始才出现（update 里）。
        地上还停着同一种东西就接着用（又去捡），不同种的淡掉。"""
        self.active = kind
        if kind in ("food", "water"):
            if self.bowl is None or self.bowl["kind"] != kind:
                x, z, _ = self.spot("Eat_loop")
                wx, wz = self._world(root, x, z)
                self.bowl = {"kind": kind, "x": wx, "z": wz, "alpha": self.bowl["alpha"] if self.bowl else 0.0, "out": False}
            self.bowl["out"] = False
        elif self.item is not None and self.item["kind"] != kind:
            self.item["out"] = True

    def finish(self) -> None:
        """活动正常做完：盆淡出；骨头 / 球放下了的在地上停 LINGER 秒再淡出（update 里数），还没放的下一帧掉在嘴下面。"""
        self.active = None
        if self.bowl is not None:
            self.bowl["out"] = True

    def cut(self) -> None:
        """活动被打断（一刀切、换姿势、换状态、开关模式）：所有道具 0.3 秒直接淡出，不在地上停。"""
        self.active = None
        if self.bowl is not None:
            self.bowl["out"] = True
        if self.item is not None:
            self.item["out"] = True

    # ---- 每帧 ----
    def update(self, dt: float, clip: Optional[str], progress: float, root: Mat4, head: Optional[Mat4], yaw: float) -> None:
        """root 是根矩阵，head 是上一帧头骨的世界矩阵（不含根）。"""
        self._update_bowl(dt)
        self._update_item(dt, clip, progress, root, head, yaw)

    def _update_bowl(self, dt: float) -> None:
        if self.bowl is None:
            return
        if self.bowl["out"]:
            self.bowl["alpha"] -= dt / FADE_OUT
            if self.bowl["alpha"] <= 0.0:
                self.bowl = None
        else:
            self.bowl["alpha"] = min(1.0, self.bowl["alpha"] + dt / FADE_IN)

    def _update_item(self, dt: float, clip: Optional[str], u: float, root: Mat4, head: Optional[Mat4], yaw: float) -> None:
        it = self.item
        carrying = self.active in ("bone", "ball")
        if carrying and clip in CARRY_CLIPS:
            if it is None or it["out"]:
                if clip == "Put_down" and it is None:
                    return                                     # 没叼着东西就放下：没东西可放
                x, z, _ = self.spot("Pick_up")
                wx, wz = self._world(root, x, z)
                alpha = it["alpha"] if it is not None else 0.0
                it = self.item = {"kind": self.active, "mode": "held" if clip == "Pick_up_idle" else "ground", "x": wx, "z": wz, "yaw": yaw,
                                  "alpha": alpha, "left": LINGER, "out": False}
            if not it.get("wait"):                             # wait：灵动交互捡球，鼻子碰到球之前地上是球的小窗口，3D 球先不出来
                it["alpha"] = min(1.0, it["alpha"] + dt / FADE_IN)
            if clip == "Pick_up":
                grab = self.spot("Pick_up")[2]
                if it["mode"] == "held" and u < grab - 0.05:
                    x, z, _ = self.spot("Pick_up")                 # 叼着的时候又从头来一遍捡起（同一根再点）：先放回地上再捡
                    it["x"], it["z"] = self._world(root, x, z)
                    it["mode"] = "ground"
                if it["mode"] != "held" and u >= grab:
                    it["mode"] = "held"                        # 鼻子最低那一刻：到嘴里
                elif it["mode"] == "linger":
                    it["mode"], it["left"] = "ground", LINGER   # 刚放下的又来捡：别在这时候淡掉
            elif clip == "Pick_up_idle":
                it["mode"] = "held"
            elif clip == "Put_down" and it["mode"] == "held" and u >= self.spot("Put_down")[2]:
                x, z, _ = self.spot("Put_down")
                it["x"], it["z"] = self._world(root, x, z)
                it["yaw"], it["mode"], it["left"] = yaw, "linger", LINGER
            return
        if it is None:
            return
        if it["out"]:
            it["alpha"] -= dt / FADE_OUT
            if it["alpha"] <= 0.0:
                self.item = None
            return
        if carrying:
            return                                             # 同一个活动里片段换成转身、跑（捡回）：照样叼着 / 等着
        if it["mode"] == "held":                               # 活动做完了还叼着（不该发生）：掉在嘴下面的地上
            if head is not None:
                px, _, pz = transform_point(mat_mul(root, head), self.mouth)
                it["x"], it["z"] = px, pz
            it["yaw"], it["mode"], it["left"] = yaw, "linger", LINGER
        elif it["mode"] == "ground":
            it["out"] = True                                   # 还没捡到手活动就结束了：淡出
            return
        it["left"] -= dt                                       # 放下后在地上停着：到点淡出
        if it["left"] <= 0.0:
            it["out"] = True

    def draw_list(self, root: Mat4, head: Mat4) -> tuple[PropDraw, ...]:
        """这一帧要画的道具零件。head 是这一帧头骨的世界矩阵（不含根）。"""
        out: list[PropDraw] = []
        if self.bowl is not None:
            m = _translate(self.bowl["x"], 0.0, self.bowl["z"])
            name = BOUGHT[self.bowl["kind"]]
            if name in bought():                                    # 买来的盆：贴图本来的颜色，不另外染
                out.append(PropDraw(name, m, (1.0, 1.0, 1.0), self.bowl["alpha"]))
            else:
                out.append(PropDraw("bowl", m, COLORS["bowl"], self.bowl["alpha"]))
                out.append(PropDraw("fill", m, COLORS[self.bowl["kind"]], self.bowl["alpha"]))
        it = self.item
        if it is not None:
            if it["mode"] == "held":
                m = mat_mul(mat_mul(root, head), _translate(*self.mouth))
            else:
                rest = BALL_R if it["kind"] == "ball" else KNOB_R
                m = mat_mul(_translate(it["x"], rest, it["z"]), rot_y_mat(180.0 + it["yaw"]))   # 躺在地上时骨头顺着狗的朝向：四分之三视角下看得出是根骨头，横着只剩两个球
            out.append(PropDraw(it["kind"], m, COLORS[it["kind"]], it["alpha"]))
            if it["kind"] == "ball":
                out.append(PropDraw("ball_seam", m, SEAM_COLOR, it["alpha"] * 0.86))
        return tuple(out)
