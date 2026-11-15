"""纯几何：窗口放哪（上次的位置、换屏按比例放回去）、接触阴影多大，外加动画节拍（屏幕刷新率 → 每帧间隔）。不碰 Qt，可单测。

坐标约定：世界单位是米，x 向右、y 向上、z 朝镜头；相机正交、绕 x 轴俯视 elevation 度。
窗口像素从左上角算，但"离底多少像素"的量单独注明。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

Rect = tuple[int, int, int, int]   # x, y, w, h（逻辑像素）

FOOT_REST = 0.013          # 四脚站地时脚骨离地面的高度（米），模型量出来的
SHADOW_ALPHA = 0.30        # 阴影中心不透明度

BoundVertex = tuple[tuple[float, float, float], tuple[tuple[int, float], ...]]


def prepare_bound_vertices(positions: Sequence[float], joints: Sequence[float],
                           weights: Sequence[float]) -> tuple[BoundVertex, ...]:
    """每个模型只做一次：合并三角面重复顶点，保留位置和非零蒙皮权重（不含道具 / 阴影）。"""
    unique = {tuple(positions[i * 3:i * 3 + 3]) + tuple(joints[i * 4:i * 4 + 4]) + tuple(weights[i * 4:i * 4 + 4])
              for i in range(len(positions) // 3)}
    return tuple((v[:3], tuple((int(v[3 + j]), v[7 + j]) for j in range(4) if v[7 + j])) for v in unique)


def projected_mesh_center(vertices: Sequence[BoundVertex], joints: Sequence[Sequence[float]],
                          root: Sequence[float], elevation_deg: float) -> Optional[tuple[float, float]]:
    """当前蒙皮网格的投影包围框中心（米，x 向右、y 向上）。只在开始调节时算，不读 GPU、不跟踪动画每一帧。
    和着色器一样先加权蒙皮、再根变换、再相机投影；提前合成两行投影，避免为每个顶点建矩阵。"""
    if not vertices or not joints:
        return None
    c, s = math.cos(math.radians(elevation_deg)), math.sin(math.radians(elevation_deg))
    rx = (root[0], root[4], root[8], root[12])
    ry = tuple(c * root[i] - s * root[i + 1] for i in (1, 5, 9, 13))
    rows = [(tuple(sum(rx[k] * m[j + k] for k in range(4)) for j in (0, 4, 8, 12)),
             tuple(sum(ry[k] * m[j + k] for k in range(4)) for j in (0, 4, 8, 12))) for m in joints]
    left = bottom = math.inf
    right = top = -math.inf
    for (x, y, z), influences in vertices:
        px = py = 0.0
        for joint, weight in influences:
            a, b = rows[joint]
            px += weight * (a[0] * x + a[1] * y + a[2] * z + a[3])
            py += weight * (b[0] * x + b[1] * y + b[2] * z + b[3])
        left, right = min(left, px), max(right, px)
        bottom, top = min(bottom, py), max(top, py)
    return (left + right) / 2.0, (bottom + top) / 2.0


def initial_position(saved: Optional[tuple[int, int]], size: tuple[int, int], screens: Sequence[Rect],
                     margin: int = 24) -> tuple[int, int]:
    """上次的位置还在某个屏幕里就用上次的；否则放到第一个屏幕右上角。"""
    w, h = size
    if saved is not None:
        x, y = saved
        cx, cy = x + w / 2, y + h / 2
        for sx, sy, sw, sh in screens:
            if sx <= cx < sx + sw and sy <= cy < sy + sh:
                return (x, y)
    if not screens:
        return (0, 0)
    sx, sy, sw, sh = screens[0]
    return (sx + sw - w - margin, sy + margin)


def relative_position(pos: tuple[int, int], size: tuple[int, int], screen: Rect) -> tuple[float, float]:
    """窗口在这块屏（可用区域）上的比例位置：(中心 x 占屏宽的几成, 底边占屏高的几成)。记底边：窗口高度会变，狗脚不动。"""
    x, y = pos
    w, h = size
    sx, sy, sw, sh = screen
    return ((x + w / 2 - sx) / sw, (y + h - sy) / sh)


def place_relative(rel: tuple[float, float], size: tuple[int, int], screen: Rect) -> tuple[int, int]:
    """比例位置 → 窗口左上角，换到大小不同的屏上还在同一边、差不多的地方。左右整个放进屏幕里（放得下的话）；
    底边可以低出屏幕一点（往下拖出屏幕不挡），但窗口中心不出屏、顶不高过屏幕顶，换到小屏上也找得到。"""
    fx, fb = rel
    w, h = size
    sx, sy, sw, sh = screen
    x = sx + fx * sw - w / 2
    x = min(max(x, sx), sx + sw - w) if sw >= w else sx + (sw - w) / 2
    bottom = min(max(sy + fb * sh, sy + h), sy + sh + h / 2)
    return (round(x), round(bottom - h))


def project(point: tuple[float, float, float], ppm: float, ground_px: float, elevation_deg: float,
            width_px: float, offset: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    """世界点 → (x 像素, 离底像素)。offset 是向右 / 下的亚像素偏移，和显卡上的相机（render.view_proj）共用。"""
    x, y, z = point
    e = math.radians(elevation_deg)
    return (width_px / 2 + offset[0] + x * ppm, ground_px - offset[1] + (y * math.cos(e) - z * math.sin(e)) * ppm)


@dataclass(frozen=True)
class Shadow:
    cx: float      # 椭圆中心 x（像素，从左算）
    cy: float      # 椭圆中心（像素，从底算）
    rx: float
    ry: float
    alpha: float   # 中心不透明度 0..1


def shadow_ellipse(footprint: Sequence[tuple[float, float]], lift: float, ppm: float, ground_px: float,
                   elevation_deg: float, width_px: float, offset: tuple[float, float] = (0.0, 0.0)) -> Optional[Shadow]:
    """footprint：身体各关节投到地面的 (x, z)（米）；lift：四脚离地高度（米，跳起来时 > 0）。
    返回地面上的接触阴影椭圆。离地越高阴影越小越淡。"""
    if not footprint:
        return None
    xs = [p[0] for p in footprint]
    zs = [p[1] for p in footprint]
    x_mid, z_mid = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    half_x, half_z = (max(xs) - min(xs)) / 2, (max(zs) - min(zs)) / 2
    e = math.radians(elevation_deg)
    cx, cy = project((x_mid, 0.0, z_mid), ppm, ground_px, elevation_deg, width_px, offset)
    rx = (half_x * 0.95 + 0.04) * ppm
    ry = max((half_z * math.sin(e) + 0.03) * ppm, rx * 0.18)
    k = 1.0 / (1.0 + 3.0 * max(0.0, lift))
    return Shadow(cx, cy, rx * k, ry * k, SHADOW_ALPHA / (1.0 + 5.0 * max(0.0, lift)))


def column_top(screens: Sequence[Rect], x: float, y: float) -> Optional[float]:
    """横坐标 x 这一列屏幕最上面到哪：从 y 所在的（不在就是最近的）那块屏开始，往上数上下挨着的屏。这一列没有屏 None。
    屏幕高低不齐时，别的列的屏不算（那边高出去的那段这一列没有屏）。"""
    col = [r for r in screens if r[0] <= x < r[0] + r[2]]
    if not col:
        return None
    cur = min(col, key=lambda r: 0.0 if r[1] <= y < r[1] + r[3] else min(abs(y - r[1]), abs(y - (r[1] + r[3]))))
    while True:
        up = next((r for r in col if r is not cur and abs(r[1] + r[3] - cur[1]) <= 2), None)
        if up is None:
            return float(cur[1])
        cur = up


def keep_on_screens(screens: Sequence[Rect], x: float, y: float, half: float, top: float, bottom: float = 0.0) -> tuple[float, float]:
    """狗的身子（根 (x, y)，左右各 half，往上 top，往下 bottom）留在几块屏拼成的范围里，返回挪好的根（灵动交互关着时身子不能出边界）。
    两块屏挨着、身子这一段全在旁边那块屏的范围里，这一边就不算边界，可以过去；屏幕高低不齐时高出去的那段还是边界，和灵动交互里的墙一样。"""
    if not screens:
        return x, y
    for strict in (False, True):                       # 横竖互相影响，排两遍：第一遍根在旁边那块屏的这一列就算连着（横着还没夹好，别被错夹回去），第二遍要整个身子都在
        mid = y - top / 2.0
        cur = next((r for r in screens if r[0] <= x < r[0] + r[2] and r[1] <= mid < r[1] + r[3]), None)
        if cur is None:
            cur = min(screens, key=lambda r: max(r[0] - x, 0.0, x - r[0] - r[2]) ** 2 + max(r[1] - mid, 0.0, mid - r[1] - r[3]) ** 2)
        left, up, width, height = cur
        right, down = left + width, up + height
        others = [r for r in screens if r is not cur]
        column = [r for r in others if (r[0] <= x - half and x + half <= r[0] + r[2] if strict else r[0] <= x < r[0] + r[2])]
        if not any(abs(r[1] + r[3] - up) <= 2 for r in column):
            y = max(y, up + top)
        if not any(abs(r[1] - down) <= 2 for r in column):
            y = min(y, down - bottom)
        a, b = y - top, y + bottom
        if not any(abs(r[0] + r[2] - left) <= 2 and r[1] <= a and b <= r[1] + r[3] for r in others):
            x = max(x, left + half)
        if not any(abs(r[0] - right) <= 2 and r[1] <= a and b <= r[1] + r[3] for r in others):
            x = min(x, right - half)
    return x, y


def frame_period(refresh_hz: float, fallback_fps: float, max_fps: float) -> float:
    """屏幕刷新率 → 动画每帧间隔（秒）：每 k 次刷新画一帧，k 取让帧率不超过 max_fps 的最小整数（120 赫兹 → 60 帧、85 → 85、144 → 72），
    每帧在屏幕上停的刷新次数一样，动作不一跛一跛；读不到刷新率（低于 20 当没读到）按 fallback_fps。"""
    if refresh_hz < 20.0:
        return 1.0 / fallback_fps
    return math.ceil(refresh_hz / max_fps - 1e-9) / refresh_hz


def smoothstep(u: float) -> float:
    u = 0.0 if u < 0 else 1.0 if u > 1 else u
    return u * u * (3 - 2 * u)
