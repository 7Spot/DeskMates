"""设置卡片的「物件」页：灵动交互的选项最下面那一行「物件 ›」进，‹ 回主页面。

一块能滚的区域，按组排（窝 / 吃喝 / 玩具 / 公园，只列有东西的组）：每组一行灰色小字的组名，下面三列的格子，一格一款（缩略图 + 名字）。
点一下摆出来、再点收起来（收起来位置留着，再摆出来回到原处）；摆着的实线描边，没摆的虚线。最底下一颗「全部收起」（普通按钮：收起不丢位置，
再点格子就回来，不算危险操作；小球也收）。道具栏、右键道具的「我不要……了」把它收了，这里每 0.3 秒跟着卡片对一遍。
「玩具」组里是小球（球也是一件道具，默认拿出来）。每一格右上角一个勾选圈（ToolCheck）：
勾上 = 放进道具栏（「···」旁边那一条）、再点取下来，默认只勾小球；最上面一行灰字说勾了是什么意思。道具栏满了（hovermenu.TOOLS_MAX）没勾的圈淡掉、点了不理。
道具栏最右边的「自定义」直接打开这一页（window.open_things_page）。
列哪些款问窗口（window.things_available：买来的模型在的狗窝、狗屋、盆，加上小球）。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QFrame, QGridLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from widget import i18n, sounds, sticker
from widget.hovermenu import TOOLS_MAX
from widget.i18n import tr
from widget.packs import THING_GROUPS, ThingStyle
from widget.tuning_page import SCROLL_CSS, SCROLL_H
from widget.widgets import MotionButton

TILE_W, TILE_H = 86, 96      # 一格：卡片里面 280 宽，三列 + 两道缝 + 右边给滚动条留的 8 正好放下
COLUMNS = 3
TILE_GAP = 6                 # 格子之间
NAME_PX = 11                 # 名字的字号（比正文小一号：英文名要放进 86 宽的一格，放不下的省略）
GROUP_TITLES = {"rest": "Beds & houses", "food": "Food & water", "toys": "Toys", "park": "Park"}
CHECK = 26                   # 右上角勾选圈的可点范围（正方形）
CHECK_D = 17.0               # 圈画多大（直径）；圆心离格子上沿、右沿各 15：在格子的圆角里，离描边 5
CHECK_AT = (TILE_W - 15, 15)
FULL_ALPHA = 0.3             # 道具栏满了：没勾的圈淡成这样


class ToolCheck(QAbstractButton):
    """格子右上角的勾选圈：勾上 = 在道具栏里，强调色实心圆 + 白勾（照相册里选照片的那个圈）；
    没勾的米白底、描边圈，悬停描边变实、圈里浮出一个淡勾（点了就是这样）。道具栏满了，没勾的淡掉（点了 ThingsPage 不理）。"""

    def __init__(self, parent=None, accent: Optional[str] = None):
        super().__init__(parent)
        self.setFixedSize(CHECK, CHECK)
        self.setCursor(Qt.PointingHandCursor)
        self.accent = QColor(accent or sticker.INK)    # 卡片换强调色时跟着换（card.Card._show_accent 认 accent 这个属性）
        self.pinned = False
        self.full = False
        self._hover = False

    def set_state(self, pinned: bool, full: bool) -> None:
        if (bool(pinned), bool(full)) != (self.pinned, self.full):
            self.pinned, self.full = bool(pinned), bool(full)
            self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        blocked = self.full and not self.pinned
        if blocked:
            p.setOpacity(FULL_ALPHA)
        hot = (self._hover or self.isDown()) and not blocked
        c = QPointF(CHECK / 2, CHECK / 2)
        r = CHECK_D / 2
        ink = QColor(sticker.INK)
        if self.pinned:
            fill = QColor(self.accent)
            if self.isDown():
                fill = sticker.blend(fill, ink, 0.15)
            mark = sticker.contrast_color(fill)
        else:
            fill = QColor(sticker.PAPER_2 if sticker.is_dark() else sticker.PAPER)
            if not hot:
                ink.setAlphaF(0.6)
            mark = QColor(sticker.MUTED) if hot else None
        p.setPen(QPen(ink, 1.6))
        p.setBrush(fill)
        p.drawEllipse(c, r, r)
        if mark is not None:
            p.setPen(QPen(mark, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            path = QPainterPath(c + QPointF(-0.42 * r, 0.02 * r))
            path.lineTo(c + QPointF(-0.12 * r, 0.32 * r))
            path.lineTo(c + QPointF(0.42 * r, -0.28 * r))
            p.drawPath(path)


class ThingTile(QAbstractButton):
    """一款物件的格子：缩略图 + 名字；摆着的实线描边，没摆的虚线（照添加页的模型格子 tuning_page.PetTile；缩略图不变淡：深色外观下深色的狗屋会看不清）。"""

    def __init__(self, style: ThingStyle, on: bool, accent: Optional[str] = None):
        super().__init__()
        self.style, self.on = style, bool(on)
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(style.display_name(i18n.current()))
        self._thumb = QPixmap(str(style.thumb)) if style.thumb is not None and style.thumb.is_file() else QPixmap()
        self.pin = ToolCheck(self, accent)          # 放进道具栏（子控件：点它不算点这一格）
        self.pin.setAccessibleName(tr("Add to the toolbar"))
        self.pin.move(CHECK_AT[0] - CHECK // 2, CHECK_AT[1] - CHECK // 2)

    def sizeHint(self) -> QSize:
        return QSize(TILE_W, TILE_H)

    def set_on(self, on: bool) -> None:
        if bool(on) != self.on:
            self.on = bool(on)
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        ink = QColor(sticker.INK)
        if not self.on:
            ink.setAlphaF(0.35)
        pen = QPen(ink, 2.0 if self.on else 1.5)
        if not self.on:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 12.0, 12.0)
        font = QFont(p.font())
        font.setPixelSize(NAME_PX)
        p.setFont(font)
        fm = QFontMetricsF(font)
        name_h = fm.height() + 4
        if not self._thumb.isNull():
            area = r.adjusted(8, 6, -8, -name_h - 4)
            s = min(area.width() / self._thumb.width(), area.height() / self._thumb.height())
            w, h = self._thumb.width() * s, self._thumb.height() * s
            p.drawPixmap(QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h), self._thumb, QRectF(self._thumb.rect()))
        p.setPen(QColor(sticker.INK))
        name = fm.elidedText(self.style.display_name(i18n.current()), Qt.ElideRight, r.width() - 8)
        p.drawText(QRectF(r.left() + 4, r.bottom() - name_h - 3, r.width() - 8, name_h), Qt.AlignCenter, name)


class ThingsPage(QWidget):
    def __init__(self, panel, window):
        super().__init__()
        self.panel, self.window = panel, window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.hint = QLabel(tr("Checked ones show up next to ···, up to {n}", n=TOOLS_MAX))
        self.hint.setProperty("muted", True)
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(SCROLL_CSS)
        self.scroll.setFixedHeight(SCROLL_H)
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(6)
        self.tiles: dict[str, ThingTile] = {}
        self.group_labels: dict[str, QLabel] = {}
        styles = window.things_available()
        for group in THING_GROUPS:
            mine = [t for t in styles if t.group == group]
            if not mine:
                continue
            if self.group_labels:
                column.addSpacing(6)
            label = QLabel(tr(GROUP_TITLES[group]))
            label.setProperty("muted", True)
            self.group_labels[group] = label
            column.addWidget(label)
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(TILE_GAP)
            for k, style in enumerate(mine):
                tile = ThingTile(style, window.thing_on(style.key), window.accent_color())
                tile.clicked.connect(lambda _=False, key=style.key: self.toggle(key))
                tile.pin.clicked.connect(lambda _=False, key=style.key: self.toggle_pin(key))
                grid.addWidget(tile, k // COLUMNS, k % COLUMNS)
                self.tiles[style.key] = tile
            grid.setColumnStretch(COLUMNS, 1)
            column.addLayout(grid)
        column.addStretch(1)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll)
        self.put_away_button = MotionButton(tr("Put everything away"))
        self.put_away_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.put_away_button.clicked.connect(lambda _=False: self.put_all_away())
        lay.addWidget(self.put_away_button)

    def toggle(self, key: str) -> None:
        """点一格：没摆的摆出来，摆着的收起来；响开关的声音。"""
        on = not self.window.thing_on(key)
        sounds.play("switch-on" if on else "switch-off")
        self.window.set_thing(key, on)
        self.sync()

    def toggle_pin(self, key: str) -> None:
        """点一格右上角的勾选圈：放进道具栏 / 取下来；满了放不进去（悬停说明写着最多几样），什么都不响。"""
        on = not self.window.tool_pinned(key)
        if not self.window.set_tool_pinned(key, on):
            return
        sounds.play("switch-on" if on else "switch-off")
        self.sync()

    def put_all_away(self) -> None:
        self.window.put_things_away()
        self.sync()

    def on_show(self) -> None:
        self.scroll.verticalScrollBar().setValue(0)
        self.sync()

    def sync(self) -> None:
        """格子对齐到现在摆着的（道具栏、右键道具收了它，这里跟着变），勾选圈对齐到道具栏；一件没摆时「全部收起」按不了。"""
        any_on = False
        full = self.window.tools_full()
        for key, tile in self.tiles.items():
            on = self.window.thing_on(key)
            tile.set_on(on)
            any_on = any_on or on
            pinned = self.window.tool_pinned(key)
            if (pinned, full) != (tile.pin.pinned, tile.pin.full) or not tile.pin.property("tipped"):
                tip = tr("Remove from the toolbar") if pinned else tr("The toolbar holds {n} at most", n=TOOLS_MAX) if full else tr("Add to the toolbar")
                self.panel.tip_for(tile.pin, tip)
                tile.pin.setProperty("tipped", True)
            tile.pin.set_state(pinned, full)
        if self.put_away_button.isEnabled() != any_on:
            self.put_away_button.setEnabled(any_on)
