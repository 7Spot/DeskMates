"""DMG 窗口的背景（箭头平的、短一点、圆角；
字不要黑胶囊和骨头，中文深灰、英文小一号浅灰）。和小组件同一套贴纸画法：米白底，顶上两行字，中间一支平的圆角箭头
（深色描边、浅色箭身、带纸片影）从 app 指向「应用程序」，两个图标都不压。
窗口高度按访达开着标签栏 / 路径栏 / 状态栏时还剩的地方定（访达全开着，背景比窗口里剩的地方高就会出滚动条）；
没开那些栏的访达窗口底下会多出一截白色，所以背景最下面渐变成白，接得上。打包时现生成（tools/build_app.sh），不入 git。
用法：python tools/make_dmg_background.py <输出目录>   → background.png（600×290）和 background@2x.png（Retina）
图标的位置和窗口大小在 packaging/dmg_settings.py，两边的数要对上（APP_X / FOLDER_X / ICON_Y）。"""
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

W, H = 600, 290                      # 背景（= 访达开着各种栏时窗口里剩的地方；窗口的大小在 dmg_settings.py）
APP_X, FOLDER_X, ICON_Y = 165, 435, 165
ICON = 112
FADE = 26                            # 最下面这么高渐变成白

app = QApplication.instance() or QApplication([])
from widget import sticker                           # noqa: E402
from widget.widgets import draw_sticker_shape, flat_arrow   # noqa: E402

INK, PAPER, PAPER_2, MUTED = (QColor(sticker.LIGHT[k]) for k in ("INK", "PAPER", "PAPER_2", "MUTED"))


def centered(p: QPainter, text: str, y: float, size: int, color: QColor, weight: QFont.Weight = QFont.Normal) -> None:
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(weight)
    p.setFont(font)
    p.setPen(color)
    fm = QFontMetricsF(font)
    p.drawText(QPointF((W - fm.horizontalAdvance(text)) / 2, y + fm.ascent()), text)


def render(scale: int) -> QImage:
    img = QImage(W * scale, H * scale, QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(scale)
    img.fill(PAPER)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    fade = QLinearGradient(0.0, H - FADE, 0.0, H)                    # 最下面渐变成白：没开路径栏 / 状态栏的访达窗口底下多出来的那截是白的
    fade.setColorAt(0.0, PAPER)
    fade.setColorAt(1.0, QColor("#FFFFFF"))
    p.fillRect(QRectF(0.0, H - FADE, W, FADE), fade)
    centered(p, "拖至 Applications 即可安装", 30.0, 15, QColor("#45454B"), QFont.Medium)        # 中文深灰（中等字重：英文那段不比汉字粗）
    centered(p, "Drag to Applications to install", 54.0, 13, QColor("#A29D96"))               # 英文小一号、浅灰
    draw_sticker_shape(p, flat_arrow(300 - 44, 300 + 44, ICON_Y - 4), PAPER_2)               # 平的、短一点（88 宽）、圆角、带纸片影
    p.end()
    return img


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    render(1).save(str(out / "background.png"))
    render(2).save(str(out / "background@2x.png"))
    print(out / "background.png")


if __name__ == "__main__":
    main()
