"""半圆表盘：设置卡片姿势行的 › 右边露出半个表（圆心在卡片边上，右半圆露出来；每个动作是一根从圆心放射出去的"指针"，
文字沿着指针写，整把指针绕圆心转，指向正右方（3 点钟）的那根是当前项、大字黑字，离得越远越淡）。
相邻指针 18°、文字起点统一一个半径（之前随角度外移，整圈看着往里凹）；上下有边界（第一项在上端、最后一项在下端，
拖到头有橡皮筋手感），不绕圈；转盘停到哪一根就直接做（和上次停的不是同一根才做），点那根能再做一次。
分组不占指针、不写组名；表盘永远在右边（Card 永远往右弹，不再镜像）；圆心的轴整个画全（面板多叠进卡片几像素）。
直径 ≈ 主页面高度的 0.88（fit_to，打开时量），相邻指针 30°，正前方上下各两根写字（最多 5 根），线和字随角度淡到 ±90°；
组和组之间不留空隙；字中文 15 号、英文 13 号，每根指针上的字在半径正中居中，放不下的英文按词折两行（字不缩）；没有指针细线，
当前那根后面一条紧贴着字的淡强调色长条（强调色跟毛色，深色模式下自动反成浅的），正在做的那根这条长条当计时器：剩多少填多少、从右往左退
（dogctl.manual_progress；转走就淡出、转回来再淡入）。
（中文 15 号不变）：相邻两根的字撞了就往外推（labels），
当前那根连长条一起算，中英文同一个规则；折不折行一律按粗体量，转到正前方不会突然变成两行；两行字行距 0.85；长条两头 6 像素。
同一晚：字随角度淡到 ±90°，转进来的一点点显出来（之前在 ±60° 一下子冒出来）；长条和进度条都连续过渡，点了别的动作时
旧进度条在对齐的 0.18 秒里淡出让位、"选中 → 计时"按时间过渡（之前进度条闪一下、新字往左跳 8 像素）。
滚轮 / 触摸板上下、在表盘上按住上下拖都能转（拖的是表沿），松手有惯性，停下对齐到最近的一根动作，转过一根轻响一次（sounds.play）。
弹出：Card 的侧边动画喂 set_progress，半圆从圆心放大的同时指针从正前方扇开（带一点回弹），收回时合拢再缩回。和卡片一个窗口、跟着卡片走。"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from widget import sounds
from widget import sticker
from widget.clips import LIST_ACTIONS
from widget import i18n
from widget.i18n import tr
from widget.states import GROUPS

R_MAX, R_MIN = 157, 64   # 半径的上下限（像素）
CARD_CLEAR = 28          # 表沿离卡片上下边至少这么远：要比卡片的圆角（sticker.RADIUS 22）大，不然表盘的头从圆角那里露出来
RADIUS_RATIO = 0.44      # 半径 = 卡片主页面高度 × 它（直径 0.88：字不能缩，表盘放大、间距拉大）
TEXT_START_RATIO = 0.24  # 字块内端离圆心至少 R × 它（且 ≥ 34 像素）；和邻居撞了再往外推（labels）
CENTER_RATIO = 0.46      # 字块的中心在 R × 它：半圆的视觉重心比半径正中靠圆心
STEP = 30.0           # 相邻两根指针差多少度（最多 5 根写字）
FONT_PX = {"zh": 15, "en": 13}   # 指针上的字，按语言定（12 号太小；中文 15 正好，英文 15 太大）；放不下的英文折两行、字不缩
PILL_PAD = 6          # 当前那根后面一条淡淡的强调色长条（代替每根指针的细线）：紧贴着字块，两头各多这么多
                      # （12 → 6：字往外推之后 12 会碰到表沿上的小三角）
LEADING = 0.85        # 折成两行的字，行距是行高的这么多倍：字块薄一点，往外推得少
GAP = 2.0             # 相邻两根的字块（当前那根连长条一起算）至少隔这么多像素，不够就往外推
RIM_CLEAR = 11.0      # 字块外端（当前那根连长条）离表沿至少这么远：表沿上的小三角伸进来 7 像素，再留 4 像素
TEXT_FADE = 90.0      # 指针上的字随角度淡出，到离正前方这么多度为零：停稳时看得清的是正前方上下各两根（±60° 那两根已经很淡），
                      # 转动时新字从这里一点点显出来
HUB = 12             # 圆心离面板贴卡片那一边多远（这几像素压在卡片上，半圆的直边藏在卡片下面；要能把圆心的轴整个画下）
MARGIN = 16           # 外面留给描边、阴影和弹出时的回弹
FRICTION = 5.0        # 惯性衰减（每秒）
MAX_VEL = 12.0        # 甩出去最快多少格 / 秒
SNAP_MS = 180         # 停下对齐到刻度的时间
BAR_FADE = SNAP_MS / 1000.0   # 进度条淡入淡出要多久（秒）："选中 → 计时"、点了别的动作时旧进度条让位；和对齐转动一样长，转到位时旧的刚好让开
SETTLE_MS = 160       # 滚轮事件停多久算停下（停下就执行）
RUBBER = 0.35         # 拖到头的橡皮筋：超出的部分只走这么多
RUBBER_MAX = 0.8      # 最多超出多少格
TICK_GAP = 0.055      # 和温润木鱼试听一致：最快55ms一格，密集时再轻最多约2.5dB


@dataclass
class Label:
    """一根写字指针上的字块，沿指针方向量（原点是圆心）：几行、多宽、行高、内端离圆心多远；
    长条：选中有几分（sel，离正前方越近越满）、进度条有几分（bar，按时间淡入淡出）、进度条还剩多少（frac）。"""
    lines: list
    width: float
    line_h: float
    start: float
    sel: float = 0.0
    bar: float = 0.0
    frac: float = 0.0

    @property
    def pill(self) -> float:
        """长条有几分（0 没有 … 1 整条）：选中和进度条里大的那个。"""
        return max(self.sel, self.bar)

    @property
    def pad(self) -> float:
        """长条比字块两头各多出多少。"""
        return PILL_PAD * self.pill

    @property
    def thick(self) -> float:
        """字块连同长条，垂直于指针方向有多厚。"""
        return len(self.lines) * self.line_h + 8.0 * self.pill


class DialPane(QWidget):
    READS_ACCENT = True           # 画的时候读卡片的强调色：换同桌时跟着卡片一起淡过去（card.Card.set_accent）
    overlap = HUB                 # 和卡片叠多少
    centered = True               # 竖直方向对着 side_anchor_y（› 那一行）
    margin = MARGIN               # 面板四周留的边

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.items: list = []                                        # 28 个动作；组只决定顺序，表盘上不留空隙、不画分隔
        for gid in GROUPS:
            self.items += [a for a in LIST_ACTIONS if a.group == gid]
        self.first, self.last = 0, len(self.items) - 1
        self.setMouseTracking(True)
        self.pos_ = float(self.first)  # 转到哪一格（小数 = 转到一半），只在 first..last 之间（拖到头能短暂超一点）
        self.vel = 0.0                 # 惯性速度（格 / 秒）
        self.progress = 0.0            # 弹出进度 0..1（OutBack 会略过 1）
        self._executed = self.first    # 上次停下执行的是哪一格（停在同一格不重复做）
        self._press: Optional[tuple[float, float, float]] = None   # (按下的 y, 上次 y, 上次时刻)
        self._moved = 0.0
        self._last_index = self.first
        self._last_tick = 0.0
        self._tick_at = 0.0
        self._snap = QVariantAnimation(self)
        self._snap.setDuration(SNAP_MS)
        self._snap.setEasingCurve(QEasingCurve.OutCubic)
        self._snap.valueChanged.connect(lambda v: self._set_pos(float(v)))
        self._snap.finished.connect(self._settled)
        self._inertia = QTimer(self)
        self._inertia.setInterval(16)
        self._inertia.timeout.connect(self._coast)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self.snap)
        self._bar = QTimer(self)                                     # 进度条：动作在做、或长条正在淡入淡出时每帧重画（_bar_tick）
        self._bar.setInterval(16)
        self._bar.timeout.connect(self._bar_tick)
        self._bar_at = 0.0
        self._bar_w: dict[str, float] = {}                           # 每根动作的进度条有几分，按时间淡入淡出（step_bars）
        self._bar_frac: dict[str, float] = {}                        # 进度条最后还剩多少：淡出时照着画
        self._leaving: Optional[str] = None                          # 点了别的动作、正在转过去：这根的进度条先淡出让位
        self.fit_to(round(R_MAX / 0.4))

    @staticmethod
    def _tint(color: QColor, alpha: float) -> QColor:
        c = QColor(color)
        c.setAlphaF(max(0.0, min(1.0, alpha)))
        return c

    def _font(self, bold: bool) -> QFont:
        font = QFont()
        font.setPixelSize(self.font_px)
        font.setBold(bold)
        return font

    def _metrics(self, bold: bool) -> QFontMetricsF:
        return QFontMetricsF(self._font(bold))

    def wrap_label(self, text: str) -> list[str]:
        """一根指针上的字分几行，一律按粗体量（转到正前方变粗也不会突然折成两行：Stretch front 就是这样撞上邻居的）：
        放得下就一行，放不下的英文按词折成两行（两行里长的那行尽量短，字不缩），一个词都放不下才省略。"""
        fm = self._metrics(True)
        if fm.horizontalAdvance(text) <= self.text_len:
            return [text]
        words = text.split(" ")
        best = None
        for k in range(1, len(words)):                              # 按词分两行：两行里长的那行尽量短
            a, b = " ".join(words[:k]), " ".join(words[k:])
            longer = max(fm.horizontalAdvance(a), fm.horizontalAdvance(b))
            if best is None or longer < best[0]:
                best = (longer, [a, b])
        if best is None or best[0] > self.text_len:                 # 没法分、或分了还放不下：一行省略
            return [fm.elidedText(text, Qt.ElideRight, self.text_len)]
        return best[1]

    def layout_label(self, text: str, fm: QFontMetricsF) -> tuple[float, float, list[str]]:
        """一根指针上的字自己怎么摆（不看邻居）：(起点离圆心多远, 文字块多宽, 几行)。行按粗体折（wrap_label），宽按这根实际用的字体量；
        字块都以 r_center 为中心（所有字在轮盘里居中，一行两行一样），放不下才往两头让。和邻居撞了由 labels 再往外推。"""
        lines = self.wrap_label(text)
        w = max(fm.horizontalAdvance(s) for s in lines)
        start = max(self.r_text, min(self.r_out - w, self.r_center - w / 2.0))
        return start, w, lines

    def labels(self) -> dict[int, Label]:
        """现在写字的那几根怎么摆：先各自居中（layout_label），再看相邻两根 ——
        一根字块内端的角离邻居的中线不到"邻居半厚 + GAP"，就往外推到够为止（当前那根连长条一起算，中英文同一个规则）。
        一对里只要有一根推够了就不会叠，所以推到表沿跟前（RIM_CLEAR）就停：字体比预想宽时由邻居那根让开，长条不碰小三角。
        长条的粗细全是连续的：选中按离正前方多近渐变，进度条按时间淡入淡出（step_bars），推的距离跟着连续变、字不跳；
        比写字的范围（TEXT_FADE）多排一格，刚转进来的那根不会把邻居一下顶开。"""
        bold, regular = self._metrics(True), self._metrics(False)
        out: dict[int, Label] = {}
        for i, a in enumerate(self.items):
            theta = self.angle(i)
            if abs(theta) > TEXT_FADE + self.step:
                continue
            near = max(0.0, 1.0 - abs(theta) / self.step)            # 离正前方不到一格的：当前那根
            fm = bold if near > 0.5 else regular
            start, width, lines = self.layout_label(tr(a.label), fm)
            line_h = fm.height() * (LEADING if len(lines) > 1 else 1.0)
            lab = Label(lines, width, line_h, start, sel=max(0.0, min(1.0, 2.0 * near - 1.0)),
                        bar=self._bar_w.get(a.id, 0.0), frac=self._bar_frac.get(a.id, 0.0))
            lab.start = max(start, self.r_text + lab.pad)
            out[i] = lab
        s, c = math.sin(math.radians(self.step)), math.cos(math.radians(self.step))
        for i, lab in out.items():
            for j in (i - 1, i + 1):
                nb = out.get(j)
                if nb is None:
                    continue
                need = (nb.thick / 2 + GAP + lab.thick / 2 * c) / s    # 离圆心 r 处两根指针相隔 r·sin(间距)，内端的角还要让出自己的半厚
                if lab.start - lab.pad < need:
                    lab.start = need + lab.pad
        for lab in out.values():
            lab.start = min(lab.start, self.R - RIM_CLEAR - lab.width - lab.pad)
        return out

    def fit_to(self, card_h: int, room: Optional[float] = None) -> None:
        """按卡片主页面的高度定大小：直径是它的 0.8。文字从离圆心 15% 处起、12 号不缩（主页面约 330 → 半径约 133，最长的英文名也放得下）。"""
        radius = round(card_h * RADIUS_RATIO)
        if room is not None:                                         # 圆心到卡片上下边还有多少地方：表盘不出卡片边框，卡片矮了表盘跟着小
            radius = min(radius, round(room) - CARD_CLEAR)
        self.R = max(R_MIN, min(R_MAX, radius))
        self.r_text = max(34, round(self.R * TEXT_START_RATIO))      # 单行文字的内端
        self.r_out = self.R - (self.r_text - 4.0)                     # 外端留一样多的边
        self.text_len = self.r_out - self.r_text                     # 单行文字最多写多长
        self.r_center = round(self.R * CENTER_RATIO)                 # 字块的中心
        self.font_px = FONT_PX.get(i18n.current(), FONT_PX["en"])
        self.step = STEP
        self.px_per_item = 2 * math.pi * self.R * self.step / 360.0  # 表沿上一格多长：拖多少像素转一格
        self.setFixedSize(HUB + self.R + MARGIN, 2 * (self.R + MARGIN))
        self.update()

    # ---- 状态 ----
    @property
    def current(self) -> int:
        """现在正前方那一格（动作序号）。"""
        return max(self.first, min(self.last, int(round(self.pos_))))

    def current_id(self) -> Optional[str]:
        return self.items[self.current].id

    def set_progress(self, t: float) -> None:
        self.progress = t
        if t >= 1.0:
            self._wake_bars()
        self.update()

    def hub(self) -> QPointF:
        """圆心（面板坐标）：贴着卡片那一边。"""
        return QPointF(HUB, self.height() / 2)

    # ---- 进度条：按时间淡入淡出 ----
    def _wake_bars(self) -> None:
        """进度条要动了（开始做、换动作、表盘打开）：每帧推进，都到位了、也没在做就停（_bar_tick）。"""
        if not self._bar.isActive():
            self._bar_at = time.perf_counter()
            self._bar.start()

    def _bar_tick(self) -> None:
        now = time.perf_counter()
        busy = self.step_bars(min(0.05, now - self._bar_at))
        self._bar_at = now
        if not busy:
            self._bar.stop()
        self.update()

    def step_bars(self, dt: float) -> bool:
        """进度条淡入淡出往前走 dt 秒（单测直接调，不真等）：正在做的那根在正前方时往 1 走；转走了（滚轮、拖动、点了别的正在让位）
        往 0 走，转回来再往 1 走。BAR_FADE 秒走完。
        还在做、或还没走到位返回 True。"""
        running = self.window.dog.manual_progress()
        live = None
        if running is not None:
            self._bar_frac[running[0]] = running[1]
            if running[0] != self._leaving and self.items[self.current].id == running[0]:
                live = running[0]
        busy = running is not None
        for aid in set(self._bar_w) | ({live} if live else set()):
            target = 1.0 if aid == live else 0.0
            w = self._bar_w.get(aid, 0.0)
            w = min(target, w + dt / BAR_FADE) if target > w else max(target, w - dt / BAR_FADE)
            if abs(w - target) < 1e-6:                               # 一格格加减的浮点零头：到了就是到了
                w = target
            if w > 0.0:
                self._bar_w[aid] = w
            else:
                self._bar_w.pop(aid, None)
            busy = busy or w != target
        return busy

    # ---- 几何：格 ↔ 角度 ----
    def angle(self, i: int) -> float:
        """第 i 根指针现在偏离正前方多少度（往下为正）。一格一根、等距。"""
        return (i - self.pos_) * self.step

    # ---- 转 ----
    def _set_pos(self, value: float, *, audible: bool = False) -> None:
        """仅手势/惯性跨格发短木音；程序同步和最终吸附静音，最密55ms一次。"""
        self.pos_ = value
        idx = int(round(value))
        if idx != self._last_index:
            self._last_index = idx
            if audible:
                now = time.perf_counter()
                interval = now - self._tick_at
                if interval >= TICK_GAP:
                    self._tick_at = now
                    gain = .75 + .25 * min(1.0, max(0.0, (interval - TICK_GAP) / .065))
                    sounds.play("tick", gain)
        self.update()

    def _nearest_item(self, p: float) -> int:
        return max(self.first, min(self.last, int(round(p))))

    def snap(self, target: Optional[int] = None) -> None:
        """对齐到最近的一根动作（或指定的那一根），带缓动；停稳了就执行（_settled）。
        要停的不是上次做的那根（停稳就换动作）：正在做的进度条现在就开始淡出让位，转到位时新字不会再往回跳。"""
        self._inertia.stop()
        self._settle.stop()
        end = float(self._nearest_item(self.pos_ if target is None else float(target)))
        running = self.window.dog.manual_progress()
        switching = running is not None and int(end) != self._executed and self.items[int(end)].id != running[0]
        self._leaving = running[0] if switching else None
        self._wake_bars()
        if abs(end - self.pos_) < 1e-3:
            self._set_pos(end)
            self._settled()
            return
        self._snap.stop()
        self._snap.setStartValue(self.pos_)
        self._snap.setEndValue(end)
        self._snap.start()

    def settle_now(self) -> None:
        """立刻停下并对齐、执行（单测用，不真等 0.2 秒的对齐动画和 0.16 秒的滚轮停顿）。"""
        self._settle.stop()
        self._inertia.stop()
        end = float(self._snap.endValue()) if self._snap.state() == QVariantAnimation.Running else float(self._nearest_item(self.pos_))
        self._snap.stop()
        self._set_pos(end)
        self._settled()

    def _settled(self) -> None:
        """停稳在一格动作上：和上次停的不是同一格就直接做（滑到哪个直接放动画，不用再点）。"""
        idx = self.current
        if idx == self._executed or self.progress < 1.0:
            self._leaving = None                                      # 没换动作：让位的进度条回来
            self._wake_bars()
            return
        self._executed = idx
        self.window.do_action(self.items[idx].id)
        self._leaving = None
        self._wake_bars()
        self.update()

    def _stop_motion(self) -> None:
        self._snap.stop()
        self._inertia.stop()
        self._settle.stop()
        self.vel = 0.0

    def cancel_interaction(self) -> None:
        """关闭卡片或截图接管时结束手势，不能在不可见处继续发声/提交动作。"""
        self._stop_motion()
        self._press = None
        self._moved = 0.0
        self._leaving = None

    def hideEvent(self, event) -> None:
        self.cancel_interaction()
        self._bar.stop()
        super().hideEvent(event)

    def _coast(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, now - self._last_tick)
        self._last_tick = now
        p = self.pos_ + self.vel * dt
        if p < self.first or p > self.last:                 # 滑到头：停住
            self._set_pos(max(self.first, min(self.last, p)), audible=True)
            self.vel = 0.0
        else:
            self._set_pos(p, audible=True)
            self.vel *= math.exp(-FRICTION * dt)
        if abs(self.vel) < 0.4:
            self._inertia.stop()
            self.snap()

    # ---- 输入 ----
    def wheelEvent(self, event) -> None:
        if self.progress < 1.0:
            return
        pd = event.pixelDelta()
        d = pd.y() / self.px_per_item if not pd.isNull() else event.angleDelta().y() / 120.0   # 触摸板按像素，鼠标滚轮一格一项
        if d:
            self._snap.stop()
            self._inertia.stop()
            self.vel = -d
            self._set_pos(max(self.first, min(self.last, self.pos_ - d)), audible=True)   # 往上滚 = 指针往上走 = 前一项；到头就停
            self._settle.start()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self.progress < 1.0:
            return
        self._stop_motion()
        y = event.position().y()
        self._press = (y, y, time.perf_counter())
        self._moved = 0.0
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            return
        y0, y_last, t_last = self._press
        y = event.position().y()
        now = time.perf_counter()
        dy = y - y_last
        self._moved = max(self._moved, abs(y - y0))
        dt = max(1e-3, now - t_last)
        self.vel = max(-MAX_VEL, min(MAX_VEL, (-dy / self.px_per_item) / dt))
        self._press = (y0, y, now)
        raw = self.pos_ - dy / self.px_per_item            # 往下拖：指针往下走，前一项转到正前方
        if raw < self.first:                                # 拖到头：橡皮筋
            raw = self.first - min(RUBBER_MAX, (self.first - raw) * RUBBER)
        elif raw > self.last:
            raw = self.last + min(RUBBER_MAX, (raw - self.last) * RUBBER)
        self._set_pos(raw, audible=True)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._press is None:
            return
        self._press = None
        if self._moved <= 4.0:                            # 点一下：点当前这根再做一次，点别的转过去（转到就做）
            hit = self.hand_at(event.position())
            if hit is None:
                self.snap()
            elif hit == self.current:
                self._executed = hit
                self.window.do_action(self.items[hit].id)
                self._wake_bars()
                self.update()
            else:
                self.snap(hit)
        elif abs(self.vel) > 1.0 and self.first <= self.pos_ <= self.last:   # 甩：惯性滑一段再对齐
            self._last_tick = time.perf_counter()
            self._inertia.start()
        else:
            self.snap()
        event.accept()

    def _angle_of(self, p: QPointF) -> tuple[float, float]:
        """点相对圆心：(角度, 半径)。角度 0 = 正前方（正右），往下为正。"""
        c = self.hub()
        dx, dy = p.x() - c.x(), p.y() - c.y()
        return math.degrees(math.atan2(dy, dx)), math.hypot(dx, dy)

    def hand_at(self, p: QPointF) -> Optional[int]:
        """点在哪根指针上（动作序号）；不在指针上（空隙、胶囊、表盘外）就 None。"""
        theta, r = self._angle_of(p)
        if r < self.r_text - 12 or r > self.R + 4 or abs(theta) > 90.0:
            return None
        i = min(range(len(self.items)), key=lambda k: abs(theta - self.angle(k)))
        return i if abs(theta - self.angle(i)) <= self.step * 0.45 else None

    # ---- 画 ----
    def paintEvent(self, event) -> None:
        if self.progress <= 0.0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.translate(self.hub())
        s = self.progress                                 # 放大 + 指针扇开都跟它（OutBack 略过 1：回弹）
        p.scale(s, s)
        spread = min(1.15, s)                             # 弹出时指针从正前方扇开

        self._paint_disc(p)
        self._paint_ticks(p, spread, self.fade)
        theme = getattr(QWidget.window(self), "theme", None)   # 卡片现在的强调色（换同桌时在淡）；没挂在卡片上用窗口的
        accent = QColor(theme.accent) if theme is not None else QColor(self.window.accent_color())
        R = self.R
        p.save()
        inner = QPainterPath()
        inner.addEllipse(QRectF(-R + 4, -R + 4, 2 * R - 8, 2 * R - 8))
        p.setClipPath(inner)
        for i, lab, alpha in self.drawn_labels():
            self._paint_hand(p, lab, self.angle(i), spread, alpha, accent)
        p.restore()
        self._paint_marker_and_hub(p)
        p.end()

    def fade(self, theta_full: float) -> float:
        """线和字随角度平滑淡出，到 ±TEXT_FADE 为零，没有任何硬切线；弹出时一起淡入。"""
        return max(0.0, 1.0 - abs(theta_full) / TEXT_FADE) * min(1.0, self.progress * 1.4)

    def drawn_labels(self) -> list[tuple[int, Label, float]]:
        """要画的字：(动作序号, 字块, 浓度)。一直画到浓度为零的 ±TEXT_FADE：停稳时看得清的是正前方上下各两根，
        转动时新字从那里一点点显出来、转出去的一点点淡掉。"""
        return [(i, lab, self.fade(self.angle(i))) for i, lab in self.labels().items() if abs(self.angle(i)) < TEXT_FADE]

    @staticmethod
    def pill_tints(lab: Label, alpha: float) -> tuple[float, float]:
        """长条的 (底色浓度, 计时填充浓度)：选中是淡底（30%），在做的是更淡的底（14%）+ 剩多少填多少（42%），两种按 bar 渐变过去；
        都乘上随角度的浓度。全是连续的：转到一半、开始做的那一帧都不跳。"""
        return (0.30 * lab.sel * (1.0 - lab.bar) + 0.14 * lab.bar) * alpha, 0.42 * lab.bar * alpha

    def _paint_disc(self, p: QPainter) -> None:
        """露出来的右半圆：纸片影、米白底、表沿描边（直边藏在卡片下面，不描）。"""
        R = self.R
        disc = QRectF(-R, -R, 2 * R, 2 * R)
        half = QPainterPath()
        half.moveTo(0.0, -R)
        half.arcTo(disc, 90.0, -180.0)
        half.closeSubpath()
        p.save()
        p.setClipRect(QRectF(HUB - 2.0, -R - MARGIN, R + MARGIN, 2 * (R + MARGIN)))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 28, 33, sticker.SHADOW_ALPHA))      # 纸片影，只画露出来的部分
        p.drawPath(half.translated(sticker.SHADOW_OFFSET))
        p.restore()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(sticker.PAPER))
        p.drawPath(half)
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
        p.setBrush(Qt.NoBrush)
        p.drawArc(disc, 90 * 16, -180 * 16)

    def _paint_ticks(self, p: QPainter, spread: float, fade) -> None:
        """表沿的刻度：每根动作一个，随角度淡出。"""
        R = self.R
        tick = max(4.0, R * 0.035)
        for i in range(len(self.items)):
            theta_full = self.angle(i)
            if abs(theta_full) >= 90.0:
                continue
            a = math.radians(theta_full * spread)
            ink = QColor(sticker.INK)
            ink.setAlphaF(fade(theta_full))
            p.setPen(QPen(ink, 1.3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF((R - 2.0) * math.cos(a), (R - 2.0) * math.sin(a)), QPointF((R - 2.0 - tick) * math.cos(a), (R - 2.0 - tick) * math.sin(a)))

    def _paint_hand(self, p: QPainter, lab: Label, theta_full: float, spread: float, alpha: float, accent: QColor) -> None:
        """一根写字的指针：字块按 labels 排好的位置（一行或两行）；当前那根加粗、后面一条紧贴字块的淡强调色长条；
        正在做的那根长条当计时器，剩多少填多少（从右往左退；转走就淡出，step_bars）。长条的浓度见 pill_tints。"""
        near = max(0.0, 1.0 - abs(theta_full) / self.step)            # 离正前方不到一格的：当前那根
        font = self._font(near > 0.5)
        p.save()
        p.rotate(theta_full * spread)
        if lab.pill > 0.0:                                              # 当前那根、正在做的那根
            thick = lab.thick
            pill = QRectF(lab.start - lab.pad, -thick / 2, lab.width + 2 * lab.pad, thick)
            shape = QPainterPath()
            shape.addRoundedRect(pill, thick / 2, thick / 2)
            base, fill = self.pill_tints(lab, alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(self._tint(accent, base))
            p.drawPath(shape)
            if lab.bar > 0.0:
                p.setBrush(self._tint(accent, fill))
                p.save()
                p.setClipPath(shape)
                p.drawRect(QRectF(pill.left(), pill.top(), pill.width() * max(0.0, lab.frac), thick))
                p.restore()
        p.setFont(font)
        ink = QColor(sticker.INK)
        ink.setAlphaF(alpha)
        p.setPen(ink)
        h = QFontMetricsF(font).height()
        n = len(lab.lines)
        for k, line in enumerate(lab.lines):                             # 一行居中在指针上；两行上下各一行（行距收紧到 LEADING）
            y = (k - (n - 1) / 2.0) * lab.line_h
            p.drawText(QRectF(lab.start, y - h / 2, lab.width, h), Qt.AlignHCenter | Qt.AlignVCenter, line)
        p.restore()

    def _paint_marker_and_hub(self, p: QPainter) -> None:
        """正前方的标记（表沿上一个小三角，指着当前那根）和圆心的轴（面板叠进卡片 HUB 像素，整个轴都画得下）。"""
        R = self.R
        marker = QPainterPath()
        marker.moveTo(R + 1.0, -5.0)
        marker.lineTo(R + 1.0, 5.0)
        marker.lineTo(R - 7.0, 0.0)
        marker.closeSubpath()
        p.setPen(QPen(QColor(sticker.INK), 1.5))
        p.setBrush(QColor(sticker.INK))
        p.drawPath(marker)
        p.setBrush(QColor(sticker.PAPER_2))
        p.setPen(QPen(QColor(sticker.INK), sticker.OUTLINE))
        p.drawEllipse(QPointF(0.0, 0.0), 6.0, 6.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(sticker.INK))
        p.drawEllipse(QPointF(0.0, 0.0), 2.0, 2.0)
