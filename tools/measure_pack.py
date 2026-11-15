"""量一个模型包该填的数：站着多高、五种步子本来多快、Bark 片段里嘴开合的时刻。只读模型，不开窗口、不读写设置。

用法：.venv.nosync/bin/python tools/measure_pack.py samoyed            （不写 id 是默认那只）
      .venv.nosync/bin/python tools/measure_pack.py samoyed --ref border_collie   再按参照的那只折算出该填进 pack.json 的数

怎么量：
- 步速：四个脚趾（claws_*）往后走的那些帧里速度的中位数（脚着地时往后蹬的速度；片段是原地做的，脚往后多快狗就该往前多快）。
  边牧量出来 0.65 / 1.92 / 3.07 / 4.52 / 0.66，和包里写的 0.65 / 1.96 / 3.2 / 4.5 / 0.65 差 5% 以内。
- 身高：height_m = 站着的那些片段（站着待机 + 站着做的动作）里最高的关节 + 耳朵的余量 0.11（dogctl.MESH_MARGIN），fit_m 再加 0.06。
  边牧：仰头叫（Idle_6）的鼻尖 0.680 → 0.79 ≈ 0.8 / 0.86；萨摩耶 0.745 → 0.86 / 0.92。height_m 在代码里当「身子的尺度」用（圈多大、
  一次跳多高、推荐大小），不是头顶在哪，所以不按网格最高点之比折（萨摩耶高出来的主要是脖子和头）。网格最高点（耳朵尖）也照样列出来。
- 嘴：mouth 这根骨头离绑定姿势转了多少度，列出张开的每一段（开始、合上）。pack.json 里 Bark 的 at 是对着这些时刻放的。
- --ref 再给三样建议值（和参照的那只比出来的，看图定稿）：mouth_offset（叼着的东西放哪）、head_shot（头像取景）按头的大小之比
  （绑定姿势里头骨到嘴角多远）；jumps.hop.arc（原地小跳的腾空区间）= 参照的那只腾空的时刻换成这个模型的片段进度。
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widget import clips, packs          # noqa: E402
from widget.anim import Player           # noqa: E402
from widget.dogctl import MESH_MARGIN    # noqa: E402
from widget.gltf import IDENTITY         # noqa: E402
from widget.look import HEAD_AT, HEAD_TALL_M   # noqa: E402
from widget.props import MOUTH_OFFSET    # noqa: E402

GAIT_CLIPS = {"walk": "Walk_F_IP", "trot": "Trot_F_IP", "run": "Run_F_IP", "fast": "RunFast_F_IP", "back": "Walk_B_IP"}
TOES = ("claws_f.L", "claws_f.R", "claws_b.L", "claws_b.R")
STEPS = 240                              # 一个片段采多少个点
GROUND = 0.005                           # 脚趾离它最低的地方这么近（米）算贴着地
FIT_EXTRA = 0.06                         # fit_m 比 height_m 多多少（边牧 0.86 − 0.8）
HOP = next(j for j in clips.JUMPS if j.name == "hop")


def gait_speed(model, clip: str) -> float:
    c = model.clips[clip]
    p = Player(model)
    p.play(clip, loop=False, fade=0.0)
    toes = [model.node_by_name(b).index for b in TOES]
    y, z = [], []
    for i in range(STEPS):
        p.time = c.duration * i / STEPS
        p.update(0.0)
        g = p.globals(IDENTITY)
        y.append([g[j][13] for j in toes])
        z.append([g[j][14] for j in toes])
    dt = c.duration / STEPS
    v = [[(z[(i + 1) % STEPS][k] - z[(i - 1) % STEPS][k]) / (2 * dt) for i in range(STEPS)] for k in range(len(toes))]
    low = [min(y[i][k] for i in range(STEPS)) for k in range(len(toes))]
    grounded = [v[k][i] for k in range(len(toes)) for i in range(STEPS) if y[i][k] <= low[k] + GROUND]
    sign = -1.0 if statistics.median(grounded) < 0 else 1.0                  # 贴着地的那些帧往哪边走，哪边就是往后蹬
    return statistics.median(x * sign for row in v for x in row if x * sign > 0)


def standing_top(model, clip: str = packs.IDLE) -> float:
    mesh = model.mesh
    P, J, W = mesh.positions, mesh.joints, mesh.weights
    verts = {(P[3 * i], P[3 * i + 1], P[3 * i + 2], J[4 * i], J[4 * i + 1], J[4 * i + 2], J[4 * i + 3]): tuple(W[4 * i:4 * i + 4]) for i in range(mesh.vertex_count)}
    c = model.clips[clip]
    p = Player(model)
    p.play(clip, loop=False, fade=0.0)
    n = max(6, int(c.duration * 6))
    top = -math.inf
    for i in range(n + 1):
        p.time = c.duration * i / n
        p.update(0.0)
        g = p.globals(IDENTITY)
        jm, mw = p.joint_matrices_from(g), g[model.mesh_node]
        for (x, y, z, *js), ws in verts.items():
            sx = sy = sz = 0.0
            for j, w in zip(js, ws):
                if w:
                    a = jm[int(j)]
                    sx += w * (a[0] * x + a[4] * y + a[8] * z + a[12])
                    sy += w * (a[1] * x + a[5] * y + a[9] * z + a[13])
                    sz += w * (a[2] * x + a[6] * y + a[10] * z + a[14])
            top = max(top, mw[1] * sx + mw[5] * sy + mw[9] * sz + mw[13])
    return top


def standing_clips() -> list[str]:
    """站着的那些片段：站着待机的循环 + 站着做的动作里的片段（跳是程序拼的，不算）。"""
    out = list(clips.PLAY_IDLE.loop)
    for a in clips.ACTIONS:
        if a.posture == "standing":
            out += [item if isinstance(item, str) else item[1] for item in a.program if isinstance(item, str) or item[0] == "loop"]
    return sorted(set(out))


def top_joint(model) -> tuple[float, str, str]:
    """站着的那些片段里最高的关节：(多高, 哪段片段, 哪根骨头)。身子的骨头和 dogctl 一个认法：蒙皮的关节、父节点也是蒙皮的关节。"""
    joints = set(model.skin_joints)
    body = [i for i in range(len(model.nodes)) if i in joints and model.nodes[i].parent in joints]
    best = (-math.inf, "", "")
    for clip in standing_clips():
        if not dict.__contains__(model.clips, clip):
            continue
        c = model.clips[clip]
        p = Player(model)
        p.play(clip, loop=False, fade=0.0)
        n = max(6, int(c.duration * 12))
        for i in range(n + 1):
            p.time = c.duration * i / n
            p.update(0.0)
            g = p.globals(IDENTITY)
            j = max(body, key=lambda k: g[k][13])
            if g[j][13] > best[0]:
                best = (g[j][13], clip, model.nodes[j].name)
    return best


def head_size(model) -> float:
    """头多大：绑定姿势里头骨到嘴角多远（米）。没有嘴角的骨头用鼻子。"""
    p = Player(model)
    p.update(0.0)
    g = p.globals(IDENTITY)
    h = g[model.node_by_name("head").index]
    j = model.node_index("Mouth.L")
    m = g[j if j is not None else model.node_by_name("nose").index]
    return math.dist((h[12], h[13], h[14]), (m[12], m[13], m[14]))


def air_span(model, clip: str = HOP.whole) -> tuple[float, float]:
    """整段跳的片段里脚离地、落回的时刻（秒）：四脚最低点比站着高出 2 毫米的那一段，取含最高点的那一段。"""
    feet = [n.index for n in model.nodes if n.name.startswith(("foot_", "claws_"))]
    c = model.clips[clip]
    p = Player(model)
    p.play(clip, loop=False, fade=0.0)
    n, hs = 200, []
    for i in range(n + 1):
        p.time = c.duration * i / n
        p.update(0.0)
        g = p.globals(IDENTITY)
        hs.append(min(g[j][13] for j in feet))
    floor = hs[0] + 0.002
    peak = max(range(n + 1), key=lambda i: hs[i])
    up = next((i for i in range(peak, 0, -1) if hs[i] <= floor), 0)
    down = next((i for i in range(peak, n) if hs[i] <= floor), n)
    return up / n * c.duration, down / n * c.duration


def tail_curled(model) -> bool:
    """站着时尾尖比尾根高（卷在背上）。"""
    a, b = model.node_index("Tail_01"), model.node_index("Tail_05")
    if a is None or b is None:
        return False
    p = Player(model)
    p.play(packs.IDLE, loop=False, fade=0.0)
    p.update(0.0)
    g = p.globals(IDENTITY)
    return g[b][13] > g[a][13]


def mouth_open(model, clip: str = "Bark") -> list[tuple[float, float]]:
    """嘴张开的每一段（开始、合上，秒）：mouth 骨头转过最大角度的一半算张开。没有这段片段或这根骨头就是空的。"""
    j = model.node_index("mouth")
    if j is None or not dict.__contains__(model.clips, clip):
        return []
    c = model.clips[clip]
    p = Player(model)
    p.play(clip, loop=False, fade=0.0)
    step, ang = 1 / 240, []
    for i in range(int(c.duration / step) + 1):
        p.time = min(c.duration, i * step)
        p.update(0.0)
        ang.append(math.degrees(2 * math.acos(min(1.0, abs(sum(a * b for a, b in zip(p.locals[j].r, p.base[j].r)))))))
    half, out, start = max(ang) / 2, [], None
    for i, a in enumerate(ang):
        if a > half and start is None:
            start = i
        elif a <= half and start is not None:
            out.append((round(start * step, 3), round(i * step, 3)))
            start = None
    return out


def measure(pack_id: str) -> dict:
    pack = packs.discover()[pack_id]
    if not pack.available:
        sys.exit(f"model file missing: {pack.model}")
    model = packs.load_model(pack)
    return {"pack": pack, "model": model, "top": standing_top(model), "joint": top_joint(model), "gaits": {k: gait_speed(model, c) for k, c in GAIT_CLIPS.items()},
            "mouth": mouth_open(model), "head": head_size(model), "air": air_span(model), "hop_s": model.clips[HOP.whole].duration, "curled": tail_curled(model)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack", nargs="?", default=packs.DEFAULT_PET)
    ap.add_argument("--ref", help="参照的模型包：按它量出来的和它包里写的折算")
    args = ap.parse_args()
    got = measure(args.pack)
    high, clip, bone = got["joint"]
    print(f"{args.pack}: 站着网格最高 {got['top']:.3f} 米；站着的片段里最高的关节 {high:.3f} 米（{clip} 的 {bone}）")
    tall = math.ceil((high + MESH_MARGIN) * 100 - 1e-6) / 100                # 往上取到厘米（0.855 → 0.86）
    print(f"  height_m {tall:.2f}  fit_m {tall + FIT_EXTRA:.2f}（最高的关节 + {MESH_MARGIN} = {high + MESH_MARGIN:.3f}，往上取；再 + {FIT_EXTRA}）")
    print("  步速（米 / 秒）", {k: round(v, 2) for k, v in got["gaits"].items()})
    print("  Bark 嘴张开的每一段", got["mouth"])
    if args.ref:
        ref = measure(args.ref)
        rp = ref["pack"]
        print(f"{args.ref}: 站着网格最高 {ref['top']:.3f} 米，最高的关节 {ref['joint'][0]:.3f} 米（包里写的 height_m {rp.height_m} / fit_m {rp.fit_m}），步速",
              {n: round(v, 2) for n, v in ref["gaits"].items()})
        print(f"  Bark 嘴张开的每一段和 {args.ref} 一样：{got['mouth'] == ref['mouth']}")
        print(f"按 {args.ref} 折算：")
        print("  gaits", {n: round(rp.gaits[n] * got["gaits"][n] / ref["gaits"][n], 2) for n in GAIT_CLIPS})
        k = got["head"] / ref["head"]
        base = rp.mouth_offset or MOUTH_OFFSET
        print(f"  头的大小之比 {k:.2f}：mouth_offset {[round(v * k, 3) for v in base]}")
        shot = rp.head_shot
        clip = "Sitting_loop_1" if got["curled"] else shot.get("clip", packs.IDLE)
        print(f"  head_shot {{\"clip\": \"{clip}\", \"tall_m\": {shot.get('tall_m', HEAD_TALL_M) * k:.2f}, \"at\": {shot.get('at', HEAD_AT)}}}"
              + ("（站着时尾巴卷在背上，正对着拍会在两耳之间露一团：坐着拍；at 看图定）" if got["curled"] else "（at 看图定）"))
        arc = ref["model"].jump_arcs.get(HOP.name, HOP.arc)
        t0, t1 = arc[0] * ref["hop_s"], arc[1] * ref["hop_s"]
        print(f"  jumps.hop.arc [{t0 / got['hop_s']:.2f}, {t1 / got['hop_s']:.2f}]（{HOP.whole}：这只 {got['hop_s']:.3f} 秒、脚离地 {got['air'][0]:.2f}～{got['air'][1]:.2f} 秒；"
              f"参照的 {ref['hop_s']:.3f} 秒、{ref['air'][0]:.2f}～{ref['air'][1]:.2f} 秒）")


if __name__ == "__main__":
    main()
