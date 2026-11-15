"""自定义毛色页（设置卡片的一页）：详情页毛色行点「自定义」→ 立刻换成自定义毛色并换到这一页（window.open_coat），
顶部栏左边的 ‹ 回详情页；进出只是顶部栏的字从名字换成「自定义毛色」、下面淡入淡出（不做「流过去变成标题」）。
狗本身就是预览：改哪项桌面上的狗立刻变。最上面是看细节那一块（和详情页同一块，widget/closeup.py）：狗站在转台上，转着看、换姿势看、放大看自己改的颜色。
Pattern：四套斑纹分布，各一张深灰 / 米白两色的头和脖子特写（借小组件的画布离屏画一次），下面一句差在哪；Common colors：一排常用的主色 / 副色，点一下就用；
Main / Secondary：点色块开系统取色器
（macOS 的取色面板自带吸管：悬浮说明里不提）；Swap 对调；Eyes 单独换色，改过了才出现「默认」按钮（回贴图原本的眼睛颜色）；Reset 长按 0.6 秒回默认。
拖颜色时 30 毫秒合并一次出 1024 的预览贴图，停手 0.25 秒出 2048 的正式贴图。
参数由窗口记进 QSettings。"""
from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QButtonGroup, QColorDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from widget import native
from widget.widgets import Fader, HoldButton, MotionButton, Swatch, Switch
from widget.coat import CoatSpec
from widget.i18n import tr
from widget.closeup import DetailRow

THUMB = QSize(124, 90)             # 两列各含12px描边/动效余量，加8px间距，正好放进280px内容区
PREVIEW_MS, FINAL_MS = 30, 250


def two_tone_icon(a: str, b: str, px: int = 22) -> QIcon:
    """对角线分成两色的圆点（左上 a、右下 b），Settings 里的 Custom 色块用。"""
    pm = QPixmap(px * 2, px * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    circle = QPainterPath()
    circle.addEllipse(0.5, 0.5, px - 1, px - 1)
    p.setClipPath(circle)
    p.fillRect(0, 0, px, px, QColor(a))
    tri = QPainterPath()
    tri.moveTo(px, 0)
    tri.lineTo(px, px)
    tri.lineTo(0, px)
    tri.closeSubpath()
    p.fillPath(tri, QColor(b))
    p.end()
    return QIcon(pm)


class ColorButton(MotionButton):
    """一个色块；点开系统取色器。拖颜色时 on_preview(hex)，确定后 on_final(hex)，取消回到打开前的颜色。"""

    MOTION_COLOR = "none"

    def __init__(self, color: str, on_preview, on_final, empty_text: str = ""):
        super().__init__()
        self.on_preview, self.on_final, self.empty_text = on_preview, on_final, empty_text
        self.color = color
        self.setFixedSize(68, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.color = color or ""
        if self.color:
            self.setText("")
            self.setStyleSheet("QPushButton { font-size: 12px; }")
        else:
            self.setText(self.empty_text)
            self.setStyleSheet("QPushButton { font-size: 12px; }")

    def _pick(self) -> None:
        native.activate_app()                  # 系统取色器（NSColorPanel）程序不在前台时自己藏起来：卡片点了不切前台，打开它这一下切
        dlg = QColorDialog(QColor(self.color) if self.color else QColor("#808080"), self)
        dlg.currentColorChanged.connect(lambda c: self.on_preview(c.name()))
        dlg.colorSelected.connect(self._chosen)
        dlg.rejected.connect(lambda: self.on_final(self.color))
        dlg.finished.connect(dlg.deleteLater)
        dlg.open()
        native.color_panel_all_spaces()        # 系统取色面板也放到所有桌面（跳桌面）

    def _chosen(self, c: QColor) -> None:
        self.set_color(c.name())
        self.on_final(c.name())


class CoatPage(QWidget):
    """设置卡片里的自定义毛色页。card 是所在的 Settings 卡片（借它的行、分组标题、悬浮提示、主题），window 是狗的窗口。"""

    def __init__(self, card, window):
        super().__init__()
        self.card, self.window = card, window
        self.spec: CoatSpec = CoatSpec.from_json(window.coat_custom_json(), window.default_coat_spec())
        t = card.theme
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.detail = DetailRow(card, window)                    # 看细节：转盘刻度尺 + 放大，站 / 坐 / 趴（状态在 window.closeup，和详情页那一块同一个）
        lay.addWidget(self.detail)

        # ---- 斑纹 ----
        lay.addLayout(card.header_row(tr("Pattern")))
        grid = QGridLayout()
        grid.setSpacing(8)
        self._pattern_group = QButtonGroup(self)
        self._pattern_group.setExclusive(True)
        self.pattern_buttons: dict[int, QPushButton] = {}
        self.pattern_notes: dict[int, QLabel] = {}
        available = window.custom_pattern_slots()                 # 深浅两色的四套 / 通体一色的纯色、背上一片
        for i in range(1, len(available) + 1):
            b = MotionButton(str(i))                      # 缩略图来之前先显示编号
            b.setProperty("tile", True)                  # 缩略图自己声明尺寸，选中时描边加粗
            b.setCheckable(True)
            b.setEnabled(available[i - 1])
            b.setIconSize(THUMB)
            b.setFixedSize(THUMB.width() + 12, THUMB.height() + 12)

            b.clicked.connect(lambda _=False, i=i: self._set(pattern=i))
            self._pattern_group.addButton(b, i)
            cell = QVBoxLayout()                          # 图下面一句：这套和别的差在哪（点了看不出区别）
            cell.setSpacing(5)
            cell.addWidget(b)
            note = QLabel(window.pattern_note(i))
            note.setProperty("muted", True)
            note.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            note.setWordWrap(True)                        # 英文长，一行放不下就折成两行，不把整页撑宽
            note.setFixedWidth(b.width())
            cell.addWidget(note)
            cell.addStretch(1)
            grid.addLayout(cell, (i - 1) // 2, (i - 1) % 2)
            self.pattern_buttons[i] = b
            self.pattern_notes[i] = note
        lay.addLayout(grid)
        self._thumbs_ready = False

        # ---- 常用颜色：点一下，主色和副色一起换 ----
        lay.addLayout(card.header_row(tr("Common colors")))
        chips = QHBoxLayout()
        chips.setSpacing(0)
        self.color_chips: list[Swatch] = []
        for k, (main, secondary) in enumerate(window.common_colors()):   # 按模型给（萨摩耶只给自然的毛色，跳的颜色从取色器选）
            chip = Swatch("transparent")
            chip.setCheckable(False)
            chip.setIcon(two_tone_icon(main, secondary))
            chip.setAccessibleName(f"{main} / {secondary}")
            chip.clicked.connect(lambda _=False, a=main, b=secondary: self._use_colors(a, b))
            if k:
                chips.addStretch(1)
            chips.addWidget(chip)
            self.color_chips.append(chip)
        lay.addLayout(chips)

        # ---- 颜色 ----
        self.main = ColorButton(self.spec.main, lambda c: self._set(main=c, preview=True), lambda c: self._set(main=c))   # 说明都悬浮才显示（不提吸管和照片）
        tint = window.coat_mode() == "tint"
        lay.addWidget(card.row(tr("Main"), self.main, tr("The whole coat") if tint else tr("Dark areas of the pattern")))
        self.secondary = ColorButton(self.spec.secondary, lambda c: self._set(secondary=c, preview=True), lambda c: self._set(secondary=c))
        lay.addWidget(card.row(tr("Secondary"), self.secondary, tr("The saddle on the back") if tint else tr("Light areas of the pattern")))
        self.swap = Switch()
        self.swap.toggled.connect(lambda on: self._set(swap=on))
        lay.addWidget(card.row(tr("Swap"), self.swap, tr("Main and secondary trade places")))
        self.eyes = ColorButton(self.spec.eyes, lambda c: self._set(eyes=c, preview=True), lambda c: self._set(eyes=c), empty_text=tr("Default"))
        self.eyes_reset = MotionButton(tr("Default"))             # 改过眼睛颜色才出现：回贴图原本的眼睛颜色
        self.eyes_reset.setProperty("quiet", True)
        self.eyes_reset.clicked.connect(lambda: (self.eyes.set_color(""), self._set(eyes="")))
        eyes_row = QHBoxLayout()
        eyes_row.addWidget(QLabel(tr("Eyes")))
        eyes_row.addStretch(1)
        eyes_row.addWidget(self.eyes_reset)
        self.eyes_reset.setVisible(False)
        self._eyes_fader = Fader(self.eyes_reset)                # 出现 / 消失淡入淡出
        eyes_row.addWidget(self.eyes)
        lay.addLayout(eyes_row)

        lay.addWidget(card.hairline_widget())
        foot = QHBoxLayout()
        self.reset = HoldButton(tr("Reset"), accent=t.accent)    # 长按 0.6 秒才重置（防误触），没有提示文字
        self.reset.held.connect(self._reset)
        foot.addWidget(self.reset)
        foot.addStretch(1)
        lay.addLayout(foot)

        self._preview_timer = QTimer(self)        # 合并连续的颜色变化
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(PREVIEW_MS)
        self._preview_timer.timeout.connect(lambda: self.window.set_custom_coat(self.spec, preview=True))
        self._final_timer = QTimer(self)          # 停手之后出正式贴图
        self._final_timer.setSingleShot(True)
        self._final_timer.setInterval(FINAL_MS)
        self._final_timer.timeout.connect(self.flush)
        self._sync_controls()

    # ---- 改参数 ----
    def _set(self, preview: bool = False, **changes) -> None:
        for k, v in changes.items():
            setattr(self.spec, k, v)
        self._eyes_fader.set(bool(self.spec.eyes))
        self._preview_timer.start()
        self._final_timer.start()

    def _use_colors(self, main: str, secondary: str) -> None:
        self.main.set_color(main)
        self.secondary.set_color(secondary)
        self._set(main=main, secondary=secondary)

    def flush(self) -> None:
        """把当前参数定稿（2048 贴图）。"""
        self._preview_timer.stop()
        self._final_timer.stop()
        self.window.set_custom_coat(self.spec, preview=False)

    def _reset(self) -> None:
        self.spec = self.window.default_coat_spec()               # 这个模型的默认（萨摩耶是雪白，不是边牧的深灰）
        self._sync_controls()
        self.flush()

    def _sync_controls(self) -> None:
        b = self._pattern_group.button(self.spec.pattern)
        if b is not None:
            b.setChecked(True)
        self.main.set_color(self.spec.main)
        self.secondary.set_color(self.spec.secondary)
        self.swap.set_silently(self.spec.swap)
        self.eyes.set_color(self.spec.eyes)
        self._eyes_fader.set(bool(self.spec.eyes))

    # ---- 页面切换（Settings 调） ----
    def on_show(self) -> None:
        """换到这一页：参数可能被窗口改过（重启、重置）；第一次来把四张斑纹缩略图画出来（借小组件的画布，没好就先空着）。"""
        self.spec = CoatSpec.from_json(self.window.coat_custom_json(), self.window.default_coat_spec())
        self._sync_controls()
        if not self._thumbs_ready:
            try:
                thumbs = self.window.pattern_thumbnails(THUMB.width() * 2, THUMB.height() * 2)
            except Exception:                         # 缩略图画不出来也要进得了这一页：这里一出错，换页整个停下，点了没反应
                logging.getLogger("coat").exception("pattern thumbnails failed")
                thumbs = {}
            for i, img in thumbs.items():
                pm = QPixmap.fromImage(img)
                pm.setDevicePixelRatio(2.0)
                self.pattern_buttons[i].setIcon(QIcon(pm))
                self.pattern_buttons[i].setText("")
            self._thumbs_ready = bool(thumbs)

    def on_hide(self) -> None:
        """离开这一页：还没出正式贴图的先定稿。"""
        if self._final_timer.isActive() or self._preview_timer.isActive():
            self.flush()
