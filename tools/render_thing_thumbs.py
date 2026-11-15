"""画物件的缩略图（设置卡片「物件」页的格子用）：每款按包里写的角度画一张 192 × 192 透明底，存在包里 packs/<包>/thumb-<款>.png。

用法：.venv.nosync/bin/python tools/render_thing_thumbs.py [包 …]（不写是所有带 thing 的包；模型文件不在的款跳过）
画法就是软件自己的（widget/thing_art.py）。大小不一的东西（网球 9 厘米、独木桥 4.7 米）都撑满一格：先把模型缩放到最长边 SIDE_M 米再画，
描边在每一格里一样粗（照真实比例的话网球的描边粗得像轮胎、独木桥的细得看不见）。红球是程序自己画的（widget/ball.py），这里照它画。
不读写设置：只开一个不上屏的画布。"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt                                  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen           # noqa: E402
from PySide6.QtWidgets import QApplication                                       # noqa: E402

SIZE = 192            # 图的边长（像素）：格子里约 76 逻辑像素宽，2 倍屏上不糊
MARGIN = 6            # 四周留白
SIDE_M = 0.5          # 每款都先缩放到画出来最长边这么多米（描边 0.0045 米，在 192 的图里约 1.6 像素）


def thing_thumb(room, style) -> QImage:
    from widget import thing_art
    model = thing_art.load_static(style.model)
    yaw = thing_art.yaw_of(style.spec)
    x0, x1, y0, y1 = thing_art.extent(model, yaw)
    model = thing_art.scaled(model, SIDE_M / max(x1 - x0, y1 - y0))
    shadow = bool(style.spec.get("shadow", True))
    probe = thing_art.layout(model, yaw, 100.0, shadow)                      # 连影子一共多大（米）
    side = max(probe.w - 2 * thing_art.PAD_PX, probe.h - 2 * thing_art.PAD_PX) / 100.0
    lay = thing_art.layout(model, yaw, (SIZE - 2 * MARGIN - 2 * thing_art.PAD_PX) / side, shadow)
    shot = room.shoot_thing(model, lay, 1.0)
    out = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    if not shot.isNull():
        p = QPainter(out)
        p.drawImage(round((SIZE - shot.width()) / 2), round((SIZE - shot.height()) / 2), shot)
        p.end()
    return out if not shot.isNull() else QImage()


def ball_thumb() -> QImage:
    """红球：和球的小窗口同一张图、同一道缝线（widget/ball.py 的 ball_image、paintEvent）。"""
    from widget.ball import ball_image
    from widget.props import SEAM_COLOR
    r = SIZE * 0.36
    img = ball_image(round(r, 1), 3.0, 1.0)
    out = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(SIZE / 2, SIZE / 2)
    p.drawImage(QRectF(c.x() - img.width() / 2, c.y() - img.height() / 2, img.width(), img.height()), img)
    clip = QPainterPath()
    clip.addEllipse(c, r * 0.97, r * 0.97)
    p.setClipPath(clip)
    p.translate(c)
    p.rotate(math.degrees(0.5))
    path = QPainterPath(QPointF(-r * 1.1, -r * 0.25))
    path.cubicTo(QPointF(-r * 0.35, r * 0.95), QPointF(r * 0.35, -r * 0.95), QPointF(r * 1.1, r * 0.25))
    pen = QPen(QColor.fromRgbF(*SEAM_COLOR, 0.86), max(1.2, r * 0.13))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return out


def main() -> int:
    app = QApplication([])      # noqa: F841
    from widget import packs, thing_art
    found = packs.discover()
    wanted = sys.argv[1:] or [p.id for p in found.values() if p.things]
    room = thing_art.Studio()
    failed = 0
    for pid in wanted:
        pack = found.get(pid)
        if pack is None or not pack.things:
            print(f"{pid}: no such pack, or it has no thing", file=sys.stderr)
            failed += 1
            continue
        for style in pack.things:
            if not style.available:
                print(f"{style.key}: model file missing, skipped", file=sys.stderr)
                continue
            img = ball_thumb() if style.spec.get("draw") == "ball" else thing_thumb(room, style)
            if img.isNull():
                print(f"{style.key}: nothing drawn (no Metal here)", file=sys.stderr)
                failed += 1
                continue
            out = pack.root / f"thumb-{style.key.split('/', 1)[1]}.png"
            img.save(str(out))
            print(out)
    room.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
