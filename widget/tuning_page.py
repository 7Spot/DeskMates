"""设置卡片的开发者设置页（高级设置里连点五下版本号打开），和添加同桌页用的模型格子（PetTile）。

开发者设置页：顶上两行选调哪个（window.tuning_targets：所有的狗一行，小球和「物件」页能摆的那几类一行；一行排不下往下排，进来默认选现在这只狗），
下面一行一个数，拖了马上生效并记住（widget/tuning.py）；「恢复默认」「复制数值」；最下面是 settings 加的「显示元数据」和版本号（带构建号）。
数多，放在能滚的一块里；滚轮是滚这一块，不改数。每一样的那一列第一次选到才建（七样一下全建要多建上百根滑杆）。
模型格子：一格一个模型（缩略图 + 名字）。一只同桌的模型在添加时定，想要别的模型就添一只。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetricsF, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from widget import i18n, sticker
from widget.card import PAD
from widget.i18n import tr
from widget.packs import Pack
from widget.tuning import Param, Tuning
from widget.widgets import FineSlider, MotionButton, SelectPill

SCROLL_H = 250              # 能滚的那一块多高（顶上的选项多了一两行、下面加了实时的兴奋度和版本号，整页还要放得进笔记本屏幕）
SCROLL_CSS = ("QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }"
              "QScrollBar:vertical { width: 6px; background: transparent; margin: 0; }"
              "QScrollBar::handle:vertical { background: rgba(128,128,128,0.45); border-radius: 3px; min-height: 24px; }"
              "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
              "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }")
PILLS_W = 312 - 2 * PAD     # 顶上选调哪个的那几颗一行最多排多宽：卡片内容的宽（卡片 312、内容离描边 PAD），排不下的换到下一行
PILL_GAP, LINE_GAP = 4, 6   # 同一行两颗之间、两行之间
TILE_W, TILE_H = 136, 138   # 选模型的一格
NAME_BOTTOM = 4             # 名字离这一格下边框多远


class TuneSlider(FineSlider):
    """调参用的滑杆：按这一项的步长走，没有大小滑杆的滴答声；滚轮留给外面滚页面。"""

    def __init__(self, param: Param, accent: str):
        super().__init__(0, 1, accent)
        self.param = param
        self.lo, self.hi = param.lo, param.hi
        self.setMinimumWidth(100)

    def _apply(self, v: float) -> None:
        p = self.param
        v = max(p.lo, min(p.hi, p.lo + round((v - p.lo) / p.step) * p.step))
        old = self.value
        self._value = v
        self.update()
        if v != old:
            self.valueChanged.emit(v)

    def _nudge(self, delta: float) -> None:
        self._apply(self.value + (self.param.step if delta > 0 else -self.param.step))

    def wheelEvent(self, event) -> None:
        event.ignore()


class TuneRow(QWidget):
    """一个数：上面标题和数值，下面滑杆。"""

    def __init__(self, tuning: Tuning, param: Param, accent: str):
        super().__init__()
        self.tuning, self.param = tuning, param
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(0)
        top = QHBoxLayout()
        top.setSpacing(6)
        title = QLabel(tr(param.label))
        title.setWordWrap(True)                              # 英文的长标题折行：不然整列被撑得比卡片宽，右边的数被裁掉
        top.addWidget(title, 1)
        self.value_label = QLabel()
        self.value_label.setProperty("muted", True)
        top.addWidget(self.value_label)
        lay.addLayout(top)
        self.slider = TuneSlider(param, accent)
        self.slider.valueChanged.connect(self._changed)
        lay.addWidget(self.slider)
        self.refresh()

    def _text(self, v: float) -> str:
        return f"{v:.{self.param.digits}f}"

    def _changed(self, v: float) -> None:
        self.tuning.set(self.param.key, v)
        self.value_label.setText(self._text(self.tuning[self.param.key]))

    def refresh(self) -> None:
        v = self.tuning[self.param.key]
        self.slider.set_value(v)
        self.value_label.setText(self._text(v))


class PillFlow(QWidget):
    """一组选项胶囊：从左往右排，一行排不下（PILLS_W）换到下一行，高度跟着行数。排的时候才量：胶囊的字体是卡片的样式表给的，建的时候还没有。"""

    def __init__(self):
        super().__init__()
        self.pills: list[QWidget] = []
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def add(self, pill: QWidget) -> None:
        pill.setParent(self)
        self.pills.append(pill)
        self.updateGeometry()

    def lines(self) -> list[list[QWidget]]:
        out, used = [], 0
        for b in self.pills:
            w = b.sizeHint().width()
            if not out or used + PILL_GAP + w > PILLS_W:
                out.append([b])
                used = w
            else:
                out[-1].append(b)
                used += PILL_GAP + w
        return out

    def sizeHint(self) -> QSize:
        lines = self.lines()
        h = sum(max(b.sizeHint().height() for b in line) for line in lines) + LINE_GAP * max(0, len(lines) - 1)
        return QSize(PILLS_W, h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def place(self) -> None:
        y = 0
        for line in self.lines():
            x = 0
            for b in line:
                size = b.sizeHint()
                b.setGeometry(x, y, size.width(), size.height())
                x += size.width() + PILL_GAP
            y += max(b.sizeHint().height() for b in line) + LINE_GAP

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.StyleChange, QEvent.FontChange):     # 放进卡片、换了字体：重量重排
            self.updateGeometry()
            self.place()


class TuningPage(QWidget):
    def __init__(self, panel, window):
        super().__init__()
        self.panel, self.window = panel, window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        groups = window.tuning_targets()                         # [[狗…], [小球、物件…]]
        self.targets: list[tuple[str, Tuning]] = [t for g in groups for t in g]
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.pills: list[SelectPill] = []
        self.flows: list[PillFlow] = []
        for g in groups:
            flow = PillFlow()
            for name, _ in g:
                k = len(self.pills)
                b = SelectPill(name)
                b.setProperty("horizontalPadding", 10)                 # 中文的小球和四类物件排得下一行
                b.clicked.connect(lambda _=False, k=k: self.select(k))
                self._group.addButton(b)
                self.pills.append(b)
                flow.add(b)
            lay.addWidget(flow)
            self.flows.append(flow)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(SCROLL_CSS)
        self.scroll.setFixedHeight(SCROLL_H)
        self.lists: list[Optional[QWidget]] = [None] * len(self.targets)   # 每一样的那一列：第一次选到才建（_build）
        self.rows: list[list[TuneRow]] = [[] for _ in self.targets]
        holder = QWidget()
        self._hold = QVBoxLayout(holder)
        self._hold.setContentsMargins(0, 0, 0, 0)
        self._hold.setSpacing(0)
        self._hold.addStretch(1)
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll)
        live = QHBoxLayout()                                     # 现在这只狗此刻的兴奋度（widget/excite.py）：只看不调，开着这一页每 0.1 秒刷一次
        live.setSpacing(6)
        live.addWidget(QLabel(tr("Excitement right now")), 1)
        self.live_label = QLabel()
        self.live_label.setProperty("muted", True)
        live.addWidget(self.live_label)
        lay.addLayout(live)
        self._live = QTimer(self)
        self._live.setInterval(100)
        self._live.timeout.connect(self._show_live)
        foot = QHBoxLayout()
        foot.setSpacing(10)
        self.reset_button = MotionButton(tr("Restore defaults"))
        self.reset_button.clicked.connect(lambda _=False: self.reset())
        self.copy_button = MotionButton(tr("Copy values"))
        self.copy_button.clicked.connect(lambda _=False: self.copy())
        for b in (self.reset_button, self.copy_button):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            foot.addWidget(b, 1)
        lay.addLayout(foot)
        self.current = 0
        self.select(next((i for i, (_, t) in enumerate(self.targets) if t is window.tuning), 0))   # 进来默认选现在这只狗

    def _build(self, k: int) -> None:
        """第 k 样的那一列：一个数一行。"""
        tuning = self.targets[k][1]
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        rows = [TuneRow(tuning, p, self.panel.theme.accent) for p in tuning.params]
        for r in rows:
            col.addWidget(r)
        self._hold.insertWidget(self._hold.count() - 1, box)    # 最后那个是撑开的空白
        self.lists[k], self.rows[k] = box, rows

    def select(self, k: int) -> None:
        self.current = k
        if self.lists[k] is None:
            self._build(k)
        for i, (box, pill) in enumerate(zip(self.lists, self.pills)):
            if box is not None:
                box.setVisible(i == k)
            pill.setChecked(i == k)
        self.scroll.verticalScrollBar().setValue(0)

    def _show_live(self) -> None:
        self.live_label.setText(f"{self.window.dog.excite.value:.2f}")

    def showEvent(self, event) -> None:
        self._show_live()
        self._live.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._live.stop()
        super().hideEvent(event)

    def on_show(self) -> None:
        for rows in self.rows:
            for r in rows:
                r.refresh()

    def reset(self) -> None:
        self.targets[self.current][1].reset()
        for r in self.rows[self.current]:
            r.refresh()

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.targets[self.current][1].copy_text())
        self.copy_button.setText(tr("Copied"))
        QTimer.singleShot(1200, lambda: self.copy_button.setText(tr("Copy values")))


class PetTile(QAbstractButton):
    """选模型的一格：缩略图 + 名字；选中的实线描边。"""

    def __init__(self, pack: Pack, selected: bool):
        super().__init__()
        self.pack, self.selected = pack, selected
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.PointingHandCursor if not selected else Qt.ArrowCursor)
        self.setAccessibleName(pack.display_name(i18n.current()))
        self._thumb = QPixmap(str(pack.thumb)) if pack.thumb is not None and pack.thumb.is_file() else QPixmap()

    def sizeHint(self) -> QSize:
        return QSize(TILE_W, TILE_H)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        ink = QColor(sticker.INK)
        if not self.selected:
            ink.setAlphaF(0.35)
        pen = QPen(ink, 2.0 if self.selected else 1.5)
        if not self.selected:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 14.0, 14.0)
        name = self.pack.display_name(i18n.current())
        fm = QFontMetricsF(p.font())
        name_h = fm.height() + 6
        if not self._thumb.isNull():
            area = r.adjusted(8, 8, -8, -name_h - NAME_BOTTOM - 2)
            s = min(area.width() / self._thumb.width(), area.height() / self._thumb.height())
            w, h = self._thumb.width() * s, self._thumb.height() * s
            p.drawPixmap(QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h), self._thumb, QRectF(self._thumb.rect()))
        p.setPen(QColor(sticker.INK))
        p.drawText(QRectF(r.left(), r.bottom() - name_h - NAME_BOTTOM, r.width(), name_h), Qt.AlignCenter, name)
