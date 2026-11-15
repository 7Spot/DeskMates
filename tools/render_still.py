"""离屏出图：不开窗口，把狗某个姿势 / 动作在某一刻渲染成 PNG，用来看外观（阴影、线条、道具）。

用法：
  .venv.nosync/bin/python tools/render_still.py --posture standing --seconds 1.5 --out demo/standing.png
  --action scratch  先进姿势再做一个动作（clips.ACTIONS 的 id），--seconds 从动作开始算
  --scale 2  放大两倍      --bg light|dark|none  垫一个桌面似的背景，方便看边缘和阴影
  --clip Jump_Place_IP --at 0.5  不走状态机，直接看某个片段在某个进度（0..1）的样子；--yaw 朝向（默认 210）
  --pack samoyed  画哪个模型包（不写是默认那只）      --coat 2  换上包里第几套毛色（不写是模型里嵌的第一套）
  --thing bed/blue  不画狗，画一款物件（packs/<包>/pack.json 的 thing 里的一款，按包里写的角度和倍数；widget/thing_art.py）；
      --scale 是整体大小，--mirrored 按屏幕右半边的样子画（尖顶狗屋反过来），--empty 画空盆，--yaw 给了就用它，--no-shadow 不画影子
不读写设置：只开一个不上屏的画布。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter                                   # noqa: E402
from PySide6.QtWidgets import QApplication                                                            # noqa: E402

import config                                                                                         # noqa: E402
from widget import gltf, overlay, packs                                                                   # noqa: E402
from widget.anim import Player                                                                        # noqa: E402
from widget.dogctl import DogController, Pose                                                         # noqa: E402
from widget.gltf import IDENTITY, rot_y_mat                                                           # noqa: E402
from widget.dogview import Darkroom                                                                   # noqa: E402
from widget.render import make_frame                                                                  # noqa: E402
from widget.clips import ACTIONS_BY_ID, POSTURE_PLANS                                                 # noqa: E402

BACKGROUNDS = {"light": ("#e8edf4", "#f7f2ea"), "dark": ("#2a2c33", "#191a1e")}


def render(model, room: Darkroom, posture: str, action: str | None, seconds: float, scale: float, seed: int, coat: QImage | None = None) -> QImage:
    k = scale
    w, h = round(config.WINDOW_WIDTH * k), round(config.WINDOW_HEIGHT * k)
    ppm, ground = config.PIXELS_PER_METER * k, config.GROUND_Y * k
    dog = DogController(model, seed=seed)
    dog.set_play(True)
    dog.set_rest_posture(posture)
    for _ in range(int(4.0 * 60)):              # 先进到姿势里
        dog.update(1 / 60)
    if action:
        dog.do_action(action)
    for _ in range(int(seconds * 60)):
        dog.update(1 / 60)
    return room.shoot(make_frame(dog.frame(), 0.0, ppm, ground, w), w, h, coat=coat)


def render_clip(model, room: Darkroom, clip: str, at: float, scale: float, yaw: float = 210.0, coat: QImage | None = None) -> QImage:
    """直接采样一个片段在进度 at（0..1）的姿势。"""
    k = scale
    w, h = round(config.WINDOW_WIDTH * k), round(config.WINDOW_HEIGHT * k)
    player = Player(model)
    player.play(clip, loop=False, fade=0.0)
    player.time = at * model.clips[clip].duration
    player.update(0.0)
    g = player.globals(IDENTITY)
    pose = Pose(rot_y_mat(90.0 + yaw), player.joint_matrices_from(g), g, [], 0.0)
    img = room.shoot(make_frame(pose, 0.0, config.PIXELS_PER_METER * k, config.GROUND_Y * k, w), w, h, coat=coat)
    p = QPainter(img)
    overlay.draw_caption(p, f"{clip} @ {at:.2f}", w / 2, h - 8 * k, max(9, round(11 * k)), 1.0)
    p.end()
    return img


def render_thing(key: str, scale: float, mirrored: bool = False, empty: bool = False, yaw: float | None = None, shadow: bool | None = None) -> QImage:
    """一款物件按包里写的角度、倍数画一张（2 倍像素密度）。"""
    from widget import thing_art
    style = next((t for t in packs.things() if t.key == key), None)
    if style is None:
        sys.exit(f"no such thing, or its model file is missing: {key}")
    path = style.model_empty if empty else style.model
    if path is None or not path.is_file():
        sys.exit(f"{key} has no {'empty ' if empty else ''}model file (the red ball is drawn by widget/ball.py)")
    model = thing_art.scaled(thing_art.load_static(path), thing_art.scale_of(style.spec))
    lay = thing_art.layout(model, thing_art.yaw_of(style.spec, mirrored) if yaw is None else yaw, config.PIXELS_PER_METER * scale,
                           bool(style.spec.get("shadow", True)) if shadow is None else shadow)
    room = thing_art.Studio()
    img = room.shoot_thing(model, lay, 2.0)
    room.close()
    return img


def with_background(img: QImage, bg: str) -> QImage:
    if bg not in BACKGROUNDS:
        return img
    top, bottom = BACKGROUNDS[bg]
    out = QImage(img.size(), QImage.Format_ARGB32_Premultiplied)
    p = QPainter(out)
    g = QLinearGradient(0, 0, 0, out.height())
    g.setColorAt(0, QColor(top))
    g.setColorAt(1, QColor(bottom))
    p.fillRect(out.rect(), g)
    p.drawImage(0, 0, img)
    p.end()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--posture", default="standing", choices=tuple(p for p in POSTURE_PLANS if p != "side"))
    ap.add_argument("--action", choices=tuple(ACTIONS_BY_ID), help="进姿势后做的动作")
    ap.add_argument("--seconds", type=float, default=1.5, help="进姿势（或动作开始）后跑多少秒再定格")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--bg", default="light", choices=("light", "dark", "none"))
    ap.add_argument("--clip", help="直接看某个片段，不走状态机")
    ap.add_argument("--at", type=float, default=0.5, help="片段进度 0..1")
    ap.add_argument("--yaw", type=float, help="朝向（--clip 默认 210；--thing 默认按包里写的）")
    ap.add_argument("--pack", help="模型包的 id（packs/<id>）")
    ap.add_argument("--coat", type=int, default=1, help="第几套毛色（1 起）")
    ap.add_argument("--brightness", type=float, help="临时换一个提亮倍数看效果（不写用模型包里的 brightness）")
    ap.add_argument("--thing", help="画一款物件：<包>/<款>，比如 bed/blue")
    ap.add_argument("--mirrored", action="store_true", help="物件按屏幕右半边的样子画")
    ap.add_argument("--empty", action="store_true", help="画空盆")
    ap.add_argument("--no-shadow", action="store_true", help="物件不画影子")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    app = QApplication([])      # noqa: F841  画布是个控件（widget/dogview.py 的 Darkroom），要 QApplication
    if args.thing:
        img = render_thing(args.thing, args.scale, args.mirrored, args.empty, args.yaw, False if args.no_shadow else None)
        save(img, args.bg, args.out)
        return
    pack = packs.discover().get(args.pack) if args.pack else None
    if args.pack and (pack is None or not pack.available):
        sys.exit(f"no such pack, or its model file is missing: {args.pack}")
    model = packs.load_model(pack) if pack else gltf.load(config.MODEL_PATH)
    if args.brightness:
        model.gain = args.brightness
    coat = None                                 # None = 模型里嵌的那张（第一套）
    if args.coat > 1:
        names, folder = (pack.coats, pack.coat_dir) if pack else (config.COATS, config.COAT_DIR)
        coat = QImage(str(folder / names[args.coat - 1])) if args.coat <= len(names) else QImage()
        if coat.isNull():
            sys.exit(f"coat {args.coat} not found")
    room = Darkroom(model)
    if args.clip:
        img = render_clip(model, room, args.clip, args.at, args.scale, 210.0 if args.yaw is None else args.yaw, coat)
    else:
        img = render(model, room, args.posture, args.action, args.seconds, args.scale, args.seed, coat)
    room.close()
    save(img, args.bg, args.out)


def save(img: QImage, bg: str, out: str) -> None:
    if img.isNull():
        sys.exit("nothing drawn: no Metal here (the offscreen platform has no RHI)")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if not with_background(img, bg).save(out):
        sys.exit(f"cannot save {out}")
    print("saved", out, f"{img.width()}x{img.height()}")


if __name__ == "__main__":
    main()
