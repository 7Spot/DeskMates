"""名字输入框：把拼音预编辑与已提交文本分开，避免确认选字时重复反馈。
字比输入框宽、滚出去了的那一头盖一个省略号（elide_colors 给了才画；顶部栏改名用：和别处长名字一样，左边省略、最后打的字一直看得见）。"""
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QGuiApplication, QInputMethodEvent, QLinearGradient, QPainter
from PySide6.QtWidgets import QLineEdit

ELLIPSIS = "…"
ELLIPSIS_RAMP = 12.0          # 字多出来这么多像素以内省略号从淡到浓（和 widgets.ELLIPSIS_RAMP 一样，约一个字宽）
SOFT = 6.0                    # 省略号后面那一小段渐变：被盖住的字不是一刀切


class NameEdit(QLineEdit):
    preeditEdited = Signal(str)
    compositionFinished = Signal()
    hidden = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preedit = ""
        self.handling_preedit = False
        self.elide_colors: Optional[tuple[QColor, QColor]] = None   # (底色, 字的颜色)：给了就在滚出去的那头画省略号

    @property
    def composing(self) -> bool:
        return bool(self._preedit)

    def shown_text(self) -> str:
        """框里现在显示的字：已经打进去的，加上拼音还没选字时的字母（插在光标那儿）。"""
        if not self._preedit:
            return self.text()
        text, at = self.text(), self.cursorPosition()
        return text[:at] + self._preedit + text[at:]

    def inputMethodEvent(self, event) -> None:
        previous = self._preedit
        self._preedit = event.preeditString()
        # QLineEdit 的 textEdited 在 super() 内同步发出。第一次预编辑可能
        # 删除选区；选字又会提交文本，两者都不能再叠加一个打字声。
        self.handling_preedit = bool(previous or self._preedit)
        try:
            super().inputMethodEvent(event)
        finally:
            self.handling_preedit = False
        if self._preedit and self._preedit != previous:
            self.preeditEdited.emit(self._preedit)
        if previous and not self._preedit:
            self.compositionFinished.emit()

    def keyPressEvent(self, event) -> None:
        if self.composing and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            method = QGuiApplication.inputMethod()
            if event.key() == Qt.Key_Escape:
                method.reset()
                # offscreen / 部分输入法不会另发空预编辑事件。
                if self.composing:
                    self.inputMethodEvent(QInputMethodEvent("", []))
            else:
                method.commit()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:
        self._preedit = ""
        self.handling_preedit = False
        self.hidden.emit()
        super().hideEvent(event)

    def clipped_ends(self) -> tuple[bool, bool]:
        """字有没有从左头 / 右头滚出去（QLineEdit 不给滚了多少，问它两头那一点是第几个字）。"""
        if not self.shown_text():
            return False, False
        cy = self.height() // 2
        left = self.cursorPositionAt(QPoint(3, cy)) > 0
        right = self.cursorPositionAt(QPoint(self.width() - 3, cy)) < len(self.text())
        return left, right

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.elide_colors is None:
            return
        fm = QFontMetricsF(self.font())
        over = fm.horizontalAdvance(self.shown_text()) + 4.0 - self.width()      # 字比框宽多少（+ 两头各 2 的边）
        if over <= 0.0:
            return
        left, right = self.clipped_ends()
        if not (left or right):
            return
        k = max(0.0, min(1.0, over / ELLIPSIS_RAMP))
        bg, fg = self.elide_colors
        ew = fm.horizontalAdvance(ELLIPSIS)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setOpacity(k)
        p.setFont(self.font())
        h = float(self.height())
        for side, on in ((-1, left), (1, right)):
            if not on:
                continue
            if side < 0:
                solid = QRectF(0.0, 0.0, 2.0 + ew + 1.0, h)
                g = QLinearGradient(QPointF(solid.right(), 0.0), QPointF(solid.right() + SOFT, 0.0))
                fade = QRectF(solid.right(), 0.0, SOFT, h)
                text = QRectF(2.0, 0.0, ew + 2.0, h)
            else:
                solid = QRectF(self.width() - 2.0 - ew - 1.0, 0.0, 2.0 + ew + 1.0, h)
                g = QLinearGradient(QPointF(solid.left(), 0.0), QPointF(solid.left() - SOFT, 0.0))
                fade = QRectF(solid.left() - SOFT, 0.0, SOFT, h)
                text = QRectF(self.width() - 2.0 - ew - 2.0, 0.0, ew + 2.0, h)
            clear = QColor(bg)
            clear.setAlphaF(0.0)
            g.setColorAt(0.0, bg)
            g.setColorAt(1.0, clear)
            p.fillRect(solid, bg)
            p.fillRect(fade, g)
            p.setPen(fg)
            p.drawText(text, int(Qt.AlignLeft | Qt.AlignVCenter), ELLIPSIS)
        p.end()
