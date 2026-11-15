"""画模型包的缩略图（设置里「同桌」那一行、选模型页用）：站着、四分之三朝向、透明背景。

用法：.venv.nosync/bin/python tools/render_pack_thumb.py border_collie（或 samoyed；不写是默认那只）
输出：packs/<id>/thumb.png"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from PySide6.QtWidgets import QApplication      # noqa: E402

W, H, PPM, FLOOR, YAW = 360, 300, 300.0, 34.0, 330.0


def main() -> int:
    app = QApplication([])      # noqa: F841
    from widget import packs
    from widget.anim import Player
    from widget.dogctl import Pose
    from widget.dogview import Darkroom
    from widget.gltf import IDENTITY, rot_y_mat
    from widget.render import make_frame
    pack = packs.discover()[sys.argv[1] if len(sys.argv) > 1 else packs.DEFAULT_PET]
    model = packs.load_model(pack)
    room = Darkroom(model)
    p = Player(model)
    p.play(packs.IDLE, loop=False, fade=0.0)
    p.update(0.0)
    g = p.globals(IDENTITY)
    pose = Pose(rot_y_mat(90.0 + YAW), p.joint_matrices_from(g), g, [], 0.0)
    img = room.shoot(make_frame(pose, 0.0, PPM, FLOOR, W, (0.0, 0.0)), W, H)
    room.close()
    if img.isNull():
        print("nothing drawn: no Metal here", file=sys.stderr)
        return 1
    out = pack.root / "thumb.png"
    img.save(str(out))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
