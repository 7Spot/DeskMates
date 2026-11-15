"""叠在狗上面的东西：脚下一行小字（离线 `Last seen HH:MM`，或 Show metadata 的元数据行）、悬停时狗头顶上方的菜单按钮。
QPainter 画，窗口（dogview.py 里盖在画布上的那一层）和离屏出图（tools/render_still.py）共用。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

from widget import sticker   # 贴纸颜色画的时候读，深色模式下一帧就换（「···」和姿势条每帧重画）
from widget.widgets import draw_hold_ring, draw_icon, draw_paw


def _tint(color: str, amount: float) -> QColor:
    c = QColor(color)
    c.setAlpha(round(255 * amount))
    return c


def draw_caption(p: QPainter, text: str, cx: float, bottom: float, px: int, amount: float = 1.0) -> QRectF:
    """以 (cx, bottom) 为底边中点，画一个半透明深色胶囊 + 白字。amount 0..1 整体淡入淡出。"""
    font = QFont()
    font.setPixelSize(px)
    p.setFont(font)
    fm = QFontMetricsF(font)
    w, h = fm.horizontalAdvance(text) + 2.0 * px, fm.height() + 0.7 * px
    rect = QRectF(cx - w / 2, bottom - h, w, h)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(16, 17, 20, round(150 * amount)))
    p.drawRoundedRect(rect, h / 2, h / 2)
    p.setPen(QColor(255, 255, 255, round(236 * amount)))
    p.drawText(rect, Qt.AlignCenter, text)
    return rect


MENU_BASE_H = 18.0   # 菜单按钮、姿势条按钮 1 倍时的高度（像素）：描边、点、字号都按它等比


def strip_font_px(h: float) -> int:
    """姿势条按钮的字号：按钮高的六成（18 → 11）。窗口量宽度和这里画字用同一个数，字才不会溢出胶囊。"""
    return max(9, round(h * 0.6))


def control_colors(checked: float, hot: float, press: float) -> tuple[QColor, QColor]:
    """选中与瞬时按压都指向最终实色；选中项不再逆向反色，文字只绘制一层高对比色。"""
    selected = max(0.0, min(1.0, checked))
    hovered = sticker.mix(QColor(sticker.PAPER), QColor(sticker.PAPER_2), max(0.0, min(1.0, hot)))
    fill = sticker.mix(hovered, QColor(sticker.INK), max(selected, max(0.0, min(1.0, press))))
    return fill, sticker.contrast_color(fill)


def strip_text_anchor(content: QRectF, base_height: float) -> tuple[QFont, QPointF]:
    """按钮局部坐标里的字形基线；跟背景共用同一个 painter 变换。"""
    font = QFont()
    font.setPixelSize(strip_font_px(base_height))
    fm = QFontMetricsF(font)
    return font, QPointF(content.center().x(), content.center().y() + (fm.ascent() - fm.descent()) / 2)


def _control_frame(p: QPainter, rect: QRectF, base_height: float, amount: float) -> QRectF:
    """背景、描边、文字和图标共同缩放 / 偏移，只有这一处变换。"""
    scale = rect.height() / base_height
    p.setOpacity(p.opacity() * amount)
    p.translate(rect.center())
    p.scale(scale, scale)
    return QRectF(-rect.width() / scale / 2, -base_height / 2, rect.width() / scale, base_height)


def draw_menu_button(p: QPainter, rect: QRectF, amount: float = 1.0, hot: float = 0.0, press: float = 0.0,
                     base_height: float = MENU_BASE_H) -> None:
    """省略号的底板、描边、三个点整体轻缩，朝指针侧同幅偏移。"""
    fill, ink = control_colors(False, hot, press)
    p.save()
    rect = _control_frame(p, rect, base_height, amount)
    p.setRenderHint(QPainter.Antialiasing)
    k = base_height / MENU_BASE_H
    p.setPen(QPen(QColor(sticker.INK), max(1.2, 1.9 * k)))
    p.setBrush(fill)
    p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    p.setPen(Qt.NoPen)
    p.setBrush(ink)
    r = 1.8 * k
    for i in (-1, 0, 1):
        p.drawEllipse(QPointF(rect.center().x() + i * rect.width() * 0.22, rect.center().y()), r, r)
    p.restore()


def draw_posture_strip(p: QPainter, items: list, amount: float = 1.0, base_height: float = MENU_BASE_H) -> None:
    """items = [(按钮框, 文字, 选中进度, 悬停进度, 瞬时按压进度)]；整颗按钮只绘制一次。"""
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    for rect, text, checked, hot, press in items:
        p.save()
        rect = _control_frame(p, rect, base_height, amount)
        k = base_height / MENU_BASE_H
        fill, ink = control_colors(checked, hot, press)
        p.setPen(QPen(QColor(sticker.INK), max(1.2, 1.9 * k)))
        p.setBrush(fill)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        font, anchor = strip_text_anchor(rect, base_height)
        p.setFont(font)
        p.setPen(ink)
        p.drawText(QPointF(anchor.x() - QFontMetricsF(font).horizontalAdvance(text) / 2, anchor.y()), text)
        p.restore()


SWITCH_W, SWITCH_H = 19.0, 11.0   # 胶囊里的小开关（1 倍时，像素）
SWITCH_GAP, PILL_PAD = 5.0, 6.0   # 字和开关隔多远、胶囊两头留多少


def plain_pill_width(text: str, base_height: float) -> float:
    """只有字的胶囊多宽（右键道具的「我不要……了」）：字 + 两头的边，和姿势条的胶囊一样。"""
    font = QFont()
    font.setPixelSize(strip_font_px(base_height))
    return QFontMetricsF(font).horizontalAdvance(text) + 2 * PILL_PAD * base_height / MENU_BASE_H


def switch_pill_width(text: str, base_height: float) -> float:
    """带开关的胶囊多宽：字 + 开关 + 两头的边（窗口量宽度和这里画字用同一个字号）。"""
    font = QFont()
    font.setPixelSize(strip_font_px(base_height))
    k = base_height / MENU_BASE_H
    return QFontMetricsF(font).horizontalAdvance(text) + (2 * PILL_PAD + SWITCH_GAP + SWITCH_W) * k


def draw_mini_switch(p: QPainter, r: QRectF, pos: float, accent: QColor, k: float) -> None:
    """和设置里的开关同样的画法（widgets.Switch）：描边胶囊里一个圆钮滑过去，开着底色是强调色，钮上一个小爪印。"""
    pos = max(0.0, min(1.0, pos))
    p.setPen(QPen(QColor(sticker.INK), max(1.0, 1.3 * k)))
    p.setBrush(sticker.blend(QColor(sticker.PAPER_2 if sticker.is_dark() else sticker.PAPER), accent, pos))
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    inset = 1.8 * k
    d = r.height() - 2 * inset
    knob = QRectF(r.left() + inset + (r.width() - 2 * inset - d) * pos, r.top() + inset, d, d)
    knob_color = QColor(sticker.PAPER_3 if sticker.is_dark() else sticker.PAPER)
    p.setBrush(knob_color)
    p.drawEllipse(knob)
    if pos > 0.5:
        ink = sticker.contrast_color(knob_color)
        ink.setAlphaF(min(1.0, (pos - 0.5) * 2.0))
        draw_paw(p, knob.center(), d * 0.62, ink)


def draw_switch_pill(p: QPainter, rect: QRectF, text: str, on: float, hot: float, press: float, amount: float,
                     base_height: float, accent: QColor) -> None:
    """带开关的胶囊（捡球：要开关的样子，不是按钮）：和姿势条的胶囊同样高、同样的描边和字，右边一个小开关。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    rect = _control_frame(p, rect, base_height, amount)
    k = base_height / MENU_BASE_H
    fill, ink = control_colors(0.0, hot, press)
    p.setPen(QPen(QColor(sticker.INK), max(1.2, 1.9 * k)))
    p.setBrush(fill)
    p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    font, anchor = strip_text_anchor(rect, base_height)
    p.setFont(font)
    p.setPen(ink)
    p.drawText(QPointF(rect.left() + PILL_PAD * k, anchor.y()), text)
    w, h = SWITCH_W * k, SWITCH_H * k
    draw_mini_switch(p, QRectF(rect.right() - PILL_PAD * k - w, rect.center().y() - h / 2, w, h), on, accent, k)
    p.restore()


def draw_close_button(p: QPainter, rect: QRectF, amount: float, hot: float, hold: float, base_height: float, accent: QColor) -> None:
    """悬停在「···」上时往下弹出来的关闭键：和「···」同样的胶囊，里面一个关机图标；按住时一圈强调色的进度线沿描边内侧绕。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    rect = _control_frame(p, rect, base_height, amount)
    k = base_height / MENU_BASE_H
    fill, ink = control_colors(0.0, hot, 0.0)
    p.setPen(QPen(QColor(sticker.INK), max(1.2, 1.9 * k)))
    p.setBrush(fill)
    p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    draw_icon(p, "power", rect.center(), 11.0 * k, ink, fill)
    if hold > 0.0:
        ring = QPainterPath()
        inner = rect.adjusted(1.8 * k, 1.8 * k, -1.8 * k, -1.8 * k)
        ring.addRoundedRect(inner, inner.height() / 2, inner.height() / 2)
        draw_hold_ring(p, ring, hold, accent, max(1.5, 1.8 * k))
    p.restore()
