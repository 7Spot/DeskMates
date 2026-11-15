"""贴纸风的调色板、主题和样式表（贴纸风：平涂米白、2 像素描边、圆角、实心偏移的纸片影）。
五个贴纸颜色（INK 描边 / 字、PAPER 底、PAPER_2 按钮底、PAPER_3 按钮悬停、MUTED 说明字）是这个模块的变量，set_dark 只改这里；
别的模块写 `sticker.INK`，画的时候才读（别往每个 import 过它们的模块里改同名变量）。
样式表（stylesheet）是建卡片时生成的，窗口换外观后重建卡片；自己每帧重画的（表盘、菜单、提示、「···」、姿势条）下一帧就换。狗本身不变。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

RADIUS = 22                                   # 卡片、「···」菜单、悬浮提示、HUD 一档圆角（
                                              # 角里 26 高的圆 / 胶囊离边 16，22 和它们接近同心）。
RADIUS_TIP = 8                                # 悬浮提示：对话气泡，圆角和二维码 / 缩略图一档（12 在 34 高上占 38%，既不是胶囊也不是卡片，看着不是一家人；
                                              # 8 占 24%，读成小矩形便签；气泡带尾巴、歪 2°，一眼不像按钮）；
#                                               按钮、开关、标签、输入框、胶囊 = 整圆（高度的一半）；二维码、斑纹缩略图这类图片 8
SHADOW = 22                                   # 卡片四周给纸片影留的边（窗口比卡片大这么一圈）
OUTLINE = 2.0                                 # 描边宽（像素）
SHADOW_OFFSET = QPointF(3.0, 5.0)             # 纸片影往右下偏多少
SHADOW_ALPHA = 60
DANGER = "#C8443A"                            # 删东西的按钮（卸载的「删除」、删除安装包）：红描边红字
BLUE_LIGHT, BLUE_DARK = "#2A5FC4", "#78A6FF"  # 「发现新版本」「新版本已下载完成」这种可以点的好消息：浅色界面上对比 5.2，深色界面用浅一点的蓝
LIGHT = {"INK": "#1C1C21", "PAPER": "#F2F0EC", "PAPER_2": "#E7E2D8", "PAPER_3": "#D9D2C4", "MUTED": "#75706A"}   # 浅色贴纸：狗的轮廓线、狗的浅色、按钮底、按钮悬停、说明字
DARK = {"INK": "#F2F0EC", "PAPER": "#1C1C21", "PAPER_2": "#2B2B32", "PAPER_3": "#393941", "MUTED": "#9B968F"}    # 深色贴纸（界面要有深色模式，狗不变）
INK, PAPER, PAPER_2, PAPER_3, MUTED = (LIGHT[k] for k in ("INK", "PAPER", "PAPER_2", "PAPER_3", "MUTED"))
_dark = False


def set_dark(on: bool) -> None:
    """界面深色 / 浅色（高级设置「外观」：浅色 / 深色 / 跟随系统）：换掉五个贴纸颜色。"""
    global _dark, INK, PAPER, PAPER_2, PAPER_3, MUTED
    _dark = bool(on)
    p = DARK if on else LIGHT
    INK, PAPER, PAPER_2, PAPER_3, MUTED = p["INK"], p["PAPER"], p["PAPER_2"], p["PAPER_3"], p["MUTED"]


def is_dark() -> bool:
    return _dark


def blue() -> str:
    return BLUE_DARK if _dark else BLUE_LIGHT


def rgba(color: str, alpha: float) -> str:
    """样式表里带透明度的颜色。"""
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.2f})"


def blend(a: QColor, b: QColor, u: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * u), round(a.green() + (b.green() - a.green()) * u),
                  round(a.blue() + (b.blue() - a.blue()) * u), round(a.alpha() + (b.alpha() - a.alpha()) * u))


def mix(a: QColor, b: QColor, u: float) -> QColor:
    """连续颜色过渡，透明底也保留 alpha。"""
    u = max(0.0, min(1.0, u))
    return QColor.fromRgbF(*(x + (y - x) * u for x, y in zip(a.getRgbF(), b.getRgbF())))


def contrast_color(background: QColor) -> QColor:
    """反色过渡只混底色；文字选择当下对比度更高的深 / 浅墨色。"""
    bg = mix(QColor(PAPER), background, background.alphaF())
    def luminance(c):
        rgb = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c.getRgbF()[:3]]
        return sum(v * w for v, w in zip(rgb, (0.2126, 0.7152, 0.0722)))
    light, dark = QColor(LIGHT["PAPER"]), QColor(LIGHT["INK"])
    lum = luminance(bg)
    def ratio(c):
        v = luminance(c)
        return (max(lum, v) + 0.05) / (min(lum, v) + 0.05)
    return light if ratio(light) > ratio(dark) else dark


@dataclass(frozen=True)
class Theme:
    dark: bool
    bg: QColor
    hairline: QColor
    text: str
    muted: str
    btn: str
    btn_hover: str
    btn_press: str
    groove: str
    accent: str
    accent_text: str           # 强调色上的字：深色强调用米白，浅色强调用描边黑


def theme(accent: Optional[str] = None) -> Theme:
    """贴纸配色：浅色 / 深色两套（set_dark），强调色随毛色变。强调色上的字按强调色自己的深浅定，和模式无关。"""
    a = QColor(accent or INK)
    if not a.isValid():
        a = QColor(INK)
    hair = QColor(INK)
    hair.setAlpha(90)
    return Theme(_dark, QColor(PAPER), hair, INK, MUTED, PAPER_2, PAPER_3, INK, PAPER, a.name(),
                 LIGHT["PAPER"] if a.lightnessF() < 0.6 else LIGHT["INK"])


def stylesheet(t: Theme) -> str:
    """卡片的样式表。不放强调色：换同桌时强调色跟着毛色换，重套一次样式表整张卡片要重排 20～35 毫秒；
    输入框选中文字的底色走卡片的调色板（Highlight，card.Card._show_accent 设），改一次 1～3 毫秒。"""
    return f"""
    QWidget {{ font-size: 13px; }}
    QLabel {{ color: {t.text}; background: transparent; }}
    QLabel[muted="true"] {{ color: {t.muted}; font-size: 12px; }}
    QLineEdit[titleedit="true"] {{ background: transparent; color: {INK}; border: none; border-radius: 0; padding: 0;
                                   font-size: 13px; font-weight: 700; }}
    QPushButton {{ font-weight: 600; }}
    QLabel[status="true"] {{ color: {t.muted}; font-weight: 600; }}
    QLineEdit {{ background: {PAPER}; color: {t.text}; border: 2px solid {INK}; border-radius: 13px; padding: 3px 10px; }}
    QSlider::groove:horizontal {{ height: 10px; background: {PAPER}; border: 2px solid {INK}; border-radius: 6px; }}
    QSlider::sub-page:horizontal {{ background: {INK}; border: 2px solid {INK}; border-radius: 6px; }}
    QSlider::handle:horizontal {{ width: 18px; height: 18px; margin: -6px 0; border-radius: 10px; background: {PAPER}; border: 2px solid {INK}; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {INK}; border-radius: 5px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    """
