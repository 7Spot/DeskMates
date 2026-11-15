"""Settings 面板：悬浮在狗旁边的小卡片，页面/标题/返回路径和生命周期集中登记在pages里（每页顶部栏的样子也登记在那：Page.lead / title_click / chip）：
- 每一页顶上是同一条顶部栏（card.TitleBar；换页不重建，只换字、宽度和左边圆里的图案，_seat_title）：左边的圆（主页面是 app 图标，别的页是返回 ‹）、
  名字胶囊（没有新版本胶囊时整颗居中，有时靠左）——主页面是「我的同桌」正中那一格的名字（滑动时跟着换，停在「+」上是描边的「添加同桌」），点了进详情页；
  详情页是这只的名字，点了就地改名（Card.set_renamable）；别的页是页名——、新版本胶囊（下载好了才有，已下载页上没有）、×。下面的内容换页时淡入淡出，不盖顶部栏。
  名字胶囊里的小图标（Page.icon）：写的是同桌的名字（主页面正中那只、详情页），或者添加页里选的模型有物种图标（狗 = 骨头），用物种图标；
  别的都是 app 图标（高级设置和它下面几页、自定义毛色、已下载、停在「+」上的「添加同桌」）。进高级设置时 app 图标从左上角的圆流进胶囊（TitleBar.set_look）。
- 主页面（_build_main）：顶部栏下面是「我的同桌」滑动条（widget/petstrip.py；和详情页共用）：点正中那只或顶上它的名字进详情页，
  最后一格「+」转到正中再点进添加页（_build_add）；桌沿下面的小圆点点了直接进那只的详情页 / 添加页；两个模式开关（鼠标跟随 / 灵动交互，可以同时开）；
  灵动交互开着时开关左边一颗调节图标，点开这一行下面缩进的几条子选项（灵动交互不只有开和关；prefs.PLAY_OPTIONS 一条一行，
  _play_options），卡片变长，再点收起；展开没展开只在程序开着时记着（window.play_options_open）；
  子选项下面跟着一行「物件 ›」（_things_row：摆着几件写在 › 左边），和子选项一起展开收起，点 › 进「物件」页；能摆的款一款都没有（买来的模型不在）时没有这一行；
  大小（「大小」+ 百分比 + 长按回到推荐大小，下面一条整行宽的滑杆）；
  动作行 站 / 坐 / 趴 / 睡（灵动交互关着才显示；睡着只剩「醒来」；行尾的右箭头在右边露出半个表盘 widget/dial.py）；最后一行「高级设置…」和「退出」。
- 详情页（_build_pet：点正中那只进，顶上还是那一条，这只放大一圈）：看细节那一块（widget/closeup.py 的 DetailRow：转盘刻度尺 + 放大滑块，
  下面站 / 坐 / 趴 + 放大的百分比 + 长按回到 100%；开着这一页狗站在转台上，一进来先站起来）、毛色（四张头像 + 自定义）、一颗居中的长按「删除」。
- 高级设置页（_build_advanced，左上角圆形的 ‹ 返回，高度 0.2 秒过渡）：省电模式；外观；媒体音效、界面音效（两条 10 档的音量 + 静音键，
  调的时候放一声听现在多响，_VolumeRow）；语言；
  缝线下面「卸载小组件 [卸载…]」，最底下和主页面最后一行同一种灰字行：左边「版本 0.5.1 (7)」，右边「检查更新」和它的几种结果（widget/updater.py；
  能点的有悬停框：检查更新、无法连接到 GitHub，点击重试、发现新版本（蓝）、新版本已下载完成（蓝）、下载没完成，点击重试）。所有说明文字不带句号，两句之间用 · 。
- 自定义毛色页（widget/coat_panel.py 的 CoatPage，从详情页毛色行的两色圆点进，‹ 回详情页；进出只是顶部栏的字从名字换成「自定义毛色」、下面淡入淡出）：
  最上面也是看细节那一块（和详情页同一个状态，两页之间来回狗一直站在转台上；Page.closeup 登记哪两页）。
- 开发者设置页（widget/tuning_page.py，连点五下版本号进，‹ 回高级设置）。
- 「物件」页（widget/things_page.py，从主页面灵动交互选项里的「物件 ›」进，‹ 回主页面）：按组排的格子，点一下摆出来 / 收起来。
- 卸载确认页（‹ 回高级设置）：没有说明，只有「取消」和红色的「删除」（长按 0.6 秒）；确认后交给独立原生助手：准备成功才退出，App 移入废纸篓后才清理数据。
- 更新说明页（点「发现新版本」进，‹ 回高级设置）：发布日期 · 大小、Release 正文里的「更新内容」、「下次再说」/「更新」（长按）；更新 = 回到高级设置开始下载。
- 已下载页（点「新版本已下载完成」或顶部栏里的新版本胶囊进，取消回原来那页）：app 名 + 版本、「安装包已下载 · 38 MB」、「删除安装包」（长按）/「取消」/「安装」（长按）。
所有改动直接调窗口的方法，窗口负责记到 QSettings；sync 每 0.3 秒把控件对齐到窗口的状态。"""
from __future__ import annotations

import logging

from dataclasses import dataclass, replace
import time

import shiboken6
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

import config
from widget import i18n, marks, native, sounds, updater
from widget import about_art
from widget.about import AboutPage, Hero as AboutHero
from widget.card import PAD, PAD_QUIET, Card
from widget.capture_ui import ui_frozen
from widget.coat_panel import CoatPage, two_tone_icon
from widget.dial import DialPane
from widget.i18n import tr
from widget.states import POSTURES
from widget.sizecontrol import SizeScrubber
from widget.things_page import ThingsPage
from widget.tuning_page import PetTile, TuningPage
from widget.updatestatus import UpdateStatus
from widget.petstrip import PetStrip
from widget.prefs import PLAY_OPTIONS
from widget.closeup import DetailRow
from widget.widgets import (NAME_MAX, TIGHT_CSS, Avatar, Collapse, Fader, FineSlider, FlatIcon, HoldButton, HoldPill, MotionButton, MuteButton,
                            SelectPill, StepSlider, Switch, stack)

CUSTOM_COAT_ID = 99      # 色块按钮组里 Custom 的 id（窗口里 coat == 0）
STRIP_PAGES = ("main", "pet")   # 顶部栏下面是「我的同桌」那一条的两页：主页面、这只同桌的详情页
# 主页面行和行之间空多少（分隔线上下也是 10）。
# 狗那一排往下 30：主页面（动作行在时）422 高，表盘半径 157（dial.R_MAX），离上边 68、下边 40，上下都不出卡片（test_half_dial 量着）。
ROW_GAP = 10
REBUILD_GAP_MS = 20           # 换了模型以后重建详情页、自定义毛色页：一帧一页（_rebuild_after_switch）
PET_DELETE_W = 104             # 详情页那颗居中的「删除」最窄多少（两个字的胶囊太小，按住时进度看不清）
BODY_TOP = 10                  # 内容区上边距（顶部栏下面）；主页面、详情页是 0：那一条紧贴顶部栏，狗头顶上的 8 在它自己里面
SCALE_LO, SCALE_HI = 30, 400   # 大小的范围（百分比）：狗在的那块屏还没量出来时用（窗口的 scale_range 给真的，跟着屏变）
SUB_INDENT = 18                # 灵动交互的子选项往右缩进多少
SUB_GAP = 6                    # 子选项之间：比主页面的行距（ROW_GAP）紧一点，看得出是灵动交互下面的一组
SIZE_GAP = 4                   # 主页面「大小」那一行和它下面整行宽的滑杆之间
UI_FEEDBACK_GAP = 0.12         # 调界面音效时两声开关声之间至少隔多久：快了合并成一声（最后那个方向），不连成一串
MEDIA_FEEDBACK_GAP = 0.5       # 拖媒体音效时最多多久叫一声
VERSION_CLICKS, VERSION_CLICK_GAP = 5, 0.6   # 版本号连点几下进开发者设置页、两下之间最多隔多久（秒）
PILL_CSS = "QPushButton { font-size: 12px; }"        # 语言 / 外观的小胶囊；选中的填色、描边由控件手绘负责
UPDATE_LINES = {                                  # 「检查更新」这一行右边：(字, 能不能点, 蓝不蓝)；能点的有悬停框
    "idle": ("Check for updates", True, False),
    "checking": ("Checking…", False, False),
    "latest": ("You're up to date", False, False),
    "offline": ("Can't connect · Retry", True, False),
    "found": ("Update available", True, True),
    "downloading": ("Downloading {pct}%", False, False),
    "downloaded": ("Update ready", True, True),
    "failed": ("Download failed · Retry", True, False),
}
UPDATE_ERRORS = {
    "certificate": "Certificate error · Retry",
    "timeout": "Connection timed out · Retry",
    "rate_limit": "GitHub rate limit · Try later",
    "no_release": "No releases yet",
}


@dataclass(frozen=True)
class Page:
    """卡片的一页：内容、标题、‹ 回哪、进出时要做的事、底边距、要不要预先排版；顶部栏在这一页的样子也登记在这里（_seat_title 照着摆）。"""
    widget: QWidget
    title: str | Callable[[], str]
    back: str | Callable[[], str] = "main"
    enter: Optional[Callable[[], None]] = None
    leave: Optional[Callable[[], None]] = None
    quiet: bool = False
    warm: bool = True
    lead: str = "back"                                  # 顶部栏左边的圆：'mark' app 图标（主页面）/ 'back' 返回
    title_click: Optional[str] = None                   # 点顶部栏的名字胶囊：'open' 进正中那只的详情页 / 'rename' 改名 / None 不理（标题是页名）
    chip: bool = True                                   # 新版本下载好了时这一页顶部栏有没有新版本胶囊（除了已下载页自己，每一页都有）
    outlined: Optional[Callable[[], bool]] = None       # 标题这时是不是标签（不是名字：主页面停在「+」上的「添加同桌」，字不加粗）
    closeup: bool = False                              # 这一页开着时狗站在转台上（看细节，widget/closeup.py；详情页、自定义毛色页）
    icon: str | Callable[[], str] = marks.APP           # 名字胶囊里的小图标：写同桌名字时是它的物种图标，别的 app 图标
    name: bool = True                                   # 顶部栏中间有没有名字胶囊（关于页没有：只留 ‹ 和 ×）

    def title_text(self) -> str:
        return self.title() if callable(self.title) else tr(self.title)

    def title_icon(self) -> str:
        return self.icon() if callable(self.icon) else self.icon

    def title_outlined(self) -> bool:
        return bool(self.outlined()) if self.outlined is not None else False

    def back_target(self) -> str:
        return self.back() if callable(self.back) else self.back


def _column(spacing: int = 10) -> tuple[QWidget, QVBoxLayout]:
    """一个竖着排的容器（页、分区）。"""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    return box, lay


class UpdatePrompt(Card):
    """下载完在狗旁边弹的提示：标题「新版本 0.6.0 (10)」，「下载已完成，现在安装吗」，「取消」/「安装」（长按 0.6 秒）。
    不抢键盘、不激活程序（卡片都这样，不会切桌面）、没声音、不挡别的操作，不理它也行；取消或 × 收起，
    设置卡片的顶部栏出现「新版本已下载完成」胶囊，高级设置最底下也一直是「新版本已下载完成」。"""

    def __init__(self, window):
        super().__init__(tr("New version"), accent=window.accent_color())
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)    # 自己弹出来的：不接键盘，你在别的 App 里打着的字不断（卡片要打字，这张没有输入框）
        self.window = window
        self.setFixedWidth(312 + 2 * 22)
        self.body.setSpacing(0)
        text = QLabel(tr("Download complete. Install now?"))
        text.setWordWrap(True)
        self.body.addWidget(text)
        self.body.addSpacing(14)
        cancel = MotionButton(tr("Cancel"))
        cancel.clicked.connect(lambda _=False: window.dismiss_update_prompt())
        self.install_button = HoldPill(tr("Install"), "primary", window.accent_color())
        self.install_button.held.connect(window.install_update)
        row = QHBoxLayout()
        row.setSpacing(10)
        for b in (cancel, self.install_button):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row.addWidget(b, 1)
        self.body.addLayout(row)

    def fill(self, release) -> None:
        self.set_title(tr("Update {version}", version=release.label()))

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.window._update_changed()                            # 收起来了：设置卡片顶部栏的新版本胶囊出来


class SettingsPanel(Card):
    def __init__(self, window):
        super().__init__(window.dog_name, accent=window.accent_color())      # 名字为空：胶囊只剩骨头
        self.window = window
        self._name_title = window.dog_name
        self.set_renamable(window.set_dog_name, tr("Click to rename"))     # 标题胶囊就是名字：点它改
        self.pets = window.available_pets()                         # 能添的模型（添加页一格一个）
        self.strip = PetStrip(self, window)                         # 「我的同桌」：主页面和详情页共用，摆在两页上面、紧贴顶部栏
        self.main_page = self._build_main()
        self.advanced_page = self._build_advanced()
        self.pet_page = self._build_pet()
        self.coat_page = CoatPage(self, window)
        self.tuning_page = self._build_tuning()
        self._built_for = window.model                              # 详情页的毛色那一行、自定义毛色页、开发者设置页照哪个模型建的
        self._stale: set[str] = set()                               # 换了模型、这几页还是照上一个模型建的（_rebuild）
        self.things_page = ThingsPage(self, window) if self.things_collapse is not None else None   # 「物件」页：有能摆的款才建
        self.uninstall_page = self._build_uninstall()
        self.notes_page = self._build_notes()
        self.downloaded_page = self._build_downloaded()
        self._downloaded_from = "main"
        self.add_page = self._build_add()
        self.about_page = AboutPage()                               # 「关于」：主页面左上角圆里的 app 图标点进来
        self.about_hero = AboutHero(self, self.about_page)          # 主页面 ↔ 关于页的过渡动画：圆里的 D、M 变成两根线描出关于页的图（widget/about.py）
        self.pages = {
            "main": Page(self.main_page, self._strip_title, quiet=True, warm=False, lead="mark", title_click="open",
                         outlined=self._strip_at_add, icon=self._strip_icon),
            "advanced": Page(self.advanced_page, "Advanced", quiet=True),
            "pet": Page(self.pet_page, lambda: self._name_title, "main", self._fill_coat_faces, warm=False, title_click="rename",
                        closeup=True, icon=lambda: self.window.pack.icon or marks.APP),
            "coat": Page(self.coat_page, "Custom color", "pet", self.coat_page.on_show,
                         self.coat_page.on_hide, quiet=True, warm=False, closeup=True),
            "tuning": Page(self.tuning_page, "Developer", "advanced", self.tuning_page.on_show, warm=False),   # 开发者设置
            "uninstall": Page(self.uninstall_page, "Uninstall", "advanced"),
            "notes": Page(self.notes_page, self._notes_title, "advanced", self._fill_notes),
            "downloaded": Page(self.downloaded_page, "New version", lambda: self._downloaded_from, self._fill_downloaded, chip=False),
            "add": Page(self.add_page, "Add a deskmate", "main", self._fill_add, warm=False, icon=self._add_icon),
            "about": Page(self.about_page, "About", "main", name=False),
        }
        if self.things_page is not None:
            self.pages["things"] = Page(self.things_page, "Things", "main", self.things_page.on_show, warm=False)
        self.body.setSpacing(0)                                    # 一次只显示一页；那一条和下面的页之间的空在那一条自己里面（petstrip.GAP）
        self.body.addWidget(self.strip)
        for name, page in self.pages.items():
            self.body.addWidget(page.widget)
            page.widget.setVisible(name == "main")
        bar = self._tag                                            # 顶部栏：每一页同一条，_seat_title 按 Page 摆
        bar.set_centered(True, animated=False)                     # 名字胶囊每一页都居中（有新版本胶囊时靠左）：换页时胶囊不跑
        bar.mark_clickable = True                                  # 主页面圆里的 app 图标点得了：进「关于」页
        self.back = bar.set_lead("mark", animated=False)           # 左边的圆：主页面 app 图标，别的页返回
        bar.back_clicked.connect(lambda: self._lead_click(self._back_target()))
        bar.mark_clicked.connect(lambda: self._lead_click("about"))
        bar.chip_clicked.connect(lambda: self.open_downloaded(self.page))   # 取消回点它的那一页
        bar.name_clicked.connect(self.strip.activate_center)       # 主页面点名字 = 点正中那一格（一个整体）
        bar.name_hovered.connect(lambda on: self.strip.set_name_hover(on and bar.click_action == "open"))
        self.strip.lift_changed.connect(bar.set_lift)              # 狗抬起来，名字胶囊一起抬（同一根弹簧）
        self.strip.center_changed.connect(lambda: self._sync_title())
        self.page = "main"
        self._fit_bottom()
        self._seat_title("main", animated=False)
        self.setFixedWidth(312 + 2 * 22)
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.sync)
        self.sync()

    # ---- 主页面 ----
    def _build_main(self) -> QWidget:
        """主页面：行间距由 stack 加（行和行 ROW_GAP、分隔线上下 10），动作行是 Collapse，展开收起有动画。"""
        page, lay = _column(0)
        follow_row, dynamic_row = self._mode_rows()
        self.follow_collapse = Collapse(follow_row, open=not self.window.dynamic_setting, pad=ROW_GAP)   # 鼠标跟随：灵动交互关着才有，和动作行一起藏、一起长出来
        stack(lay, [dynamic_row, self._play_options(),                  # 灵动交互的子选项：开着才有，和动作行（关着才有）不会同时在
                    *self._things_row(),                                # 子选项下面的「物件 ›」：和子选项一起展开收起；没有能摆的款就没有这一行
                    self._posture_section(), self.follow_collapse,      # 动作行紧跟着管它的灵动交互，排第二：落在卡片正中，表盘对着它往正右展开，上下都离圆角远
                    self._size_row(),                                   # 大小
                    self.hairline_widget(), self._foot_row()], gap=ROW_GAP)
        return page

    def _build_pet(self) -> QWidget:
        """这只同桌的详情页（点一下正中那只进来）。
        顶上还是「我的同桌」那一条（PetStrip.set_focus：这只放大一圈，别的退开；返回在顶部栏左边的圆里，点顶部栏的名字改名），这里是下面几行：
        看细节那一块（转盘刻度尺 + 放大，站 / 坐 / 趴，和自定义毛色页最上面那一块一样），毛色，一条分隔线，
        一颗居中的长按「删除」（看得见的长按按钮，不用再问一遍，左边不写字；只剩一只时按不了）。
        大小是全局的，在主页面。模型在添加时就定了，这里不能换。"""
        page, lay = _column()
        lay.addSpacing(4)                                           # 桌沿在这一页往下坐了 12（petstrip.FOCUS_DROP），下面那一行别贴着它
        self.pet_detail = DetailRow(self, self.window)
        lay.addWidget(self.pet_detail)
        lay.addLayout(self._coat_row())
        lay.addWidget(self.hairline_widget())
        self.pet_delete = HoldPill(tr("Delete"), "danger")        # 别叫 delete_button：那是卸载页的「删除」（window.uninstall 也按这个名字找它）
        self.pet_delete.setMinimumWidth(PET_DELETE_W)
        self.pet_delete.held.connect(self._delete_pet)
        lay.addWidget(self.pet_delete, 0, Qt.AlignHCenter)
        return page

    def _build_tuning(self) -> QWidget:
        """开发者设置页（连点五下版本号）：顶上选调哪个（所有的狗、小球、物件，window.tuning_targets，建的时候定），
        下面开发用的「显示元数据」，最底下一行灰字「版本 0.6.0 (66)」：一直带构建号（发布版只在这里有）。"""
        page = TuningPage(self, self.window)
        self.meta = Switch()
        self.meta.toggled.connect(self.window.set_show_metadata)
        self.meta.set_silently(self.window.show_metadata)
        page.layout().addWidget(self.row(tr("Show metadata"), self.meta, tr("Posture · activity · clip · fps")))
        self.build_label = QLabel(f"{tr('Version')} {config.VERSION} ({config.BUILD})")
        self.build_label.setProperty("muted", True)
        page.layout().addWidget(self.build_label)
        return page

    def open_pet(self) -> None:
        self.show_page("pet")

    def _delete_pet(self) -> None:
        """详情页里长按「删除」：先回主页面，那只在滑动条上缩回桌沿后面，旁边的补过来（窗口换成旁边那只）。最后一只删不了。"""
        if len(self.window.pets()) < 2:
            return
        sounds.play("complete")
        self.show_page("main")
        self.strip.remove_current()

    def _mode_rows(self) -> list[QWidget]:
        """两个模式开关（可以同时开）。灵动交互那一行，开关左边一颗调节图标（三根横线各带一个小圆点）：
        灵动交互开着才出现（淡入淡出），点开下面的子选项，再点收起（toggle_play_options）。"""
        window = self.window
        self.follow = Switch()
        self.follow.toggled.connect(lambda on: self._mode_changed(window.set_follow_cursor, on))
        follow_row = self.row(tr("Follow cursor"), self.follow, tr("Watches the pointer from afar"))
        self.dynamic = Switch()
        self.dynamic.toggled.connect(lambda on: self._mode_changed(window.set_dynamic, on))
        dynamic_row = self.row(tr("Dynamic interaction"), self.dynamic, tr("Throw the ball for it · lift the dog and throw it"))
        self.play_options_btn = FlatIcon("tune")
        self.play_options_btn.setAccessibleName(tr("Interaction options"))
        self.play_options_btn.setVisible(window.dynamic_setting)
        self._tune = Fader(self.play_options_btn)                 # 只淡不挪：出现消失旁边的字、开关都不动
        self.play_options_btn.clicked.connect(lambda _=False: self.toggle_play_options())   # clicked 带布尔参数，别塞进 animated
        self.tip_for(self.play_options_btn, tr("Interaction options"))
        dynamic_row.layout().insertWidget(1, self.play_options_btn, 0, Qt.AlignVCenter)
        return [follow_row, dynamic_row]

    def _play_options(self) -> QWidget:
        """灵动交互的子选项：照 prefs.PLAY_OPTIONS 一条一行，缩进，左边字、右边和设置同款的小开关；写了 tip 的这一行停在字上 0.5 秒浮出说明；
        默认收起，灵动交互那一行的调节图标点开（Collapse：高度用弹簧长出来，下面的行跟着滑，卡片变长）。
        以后往这一块加东西（「自己歇着」的开关、一排物件）：开关在那张表里加一行；别的控件接着加在 block 的布局里。"""
        window = self.window
        block, lay = _column(SUB_GAP)
        lay.setContentsMargins(SUB_INDENT, 0, 0, 0)
        self.play_switches: dict[str, Switch] = {}
        for option in PLAY_OPTIONS:
            switch = Switch()
            switch.setAccessibleName(tr(option.label))
            switch.toggled.connect(lambda on, key=option.key: window.set_play_option(key, on))
            self.play_switches[option.key] = switch
            lay.addWidget(self.row(tr(option.label), switch, tr(option.tip) if option.tip else ""))
        shown = window.dynamic_setting and window.play_options_open        # 换外观、换语言重建卡片：展开着的还展开着
        self.play_options_btn.setChecked(shown)
        self.play_collapse = Collapse(block, open=shown, pad=ROW_GAP)
        return self.play_collapse

    def _things_row(self) -> list[QWidget]:
        """灵动交互选项最下面的一行「物件」：右边一颗 ›（和动作行那颗一样），摆着的件数用灰字写在 › 左边（一件没摆不写），点 › 进「物件」页。
        做成紧跟在子选项后面的第二块 Collapse（同样缩进、同样的行距），和子选项一起开合：看上去是连着的一组，子选项那一块里还是只有 PLAY_OPTIONS 那几条。
        能摆的款一款都没有（买来的模型不在）：不建，返回空的。"""
        window = self.window
        self.things_collapse: Optional[Collapse] = None
        if not window.things_available():
            return []
        block, lay = _column(SUB_GAP)
        lay.setContentsMargins(SUB_INDENT, 0, 0, 0)
        right = QWidget()
        side = QHBoxLayout(right)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(4)
        self.things_count = QLabel()
        self.things_count.setProperty("muted", True)
        side.addWidget(self.things_count)
        self.things_open = MotionButton(symbol="forward")
        self.things_open.setAccessibleName(tr("Things"))
        self.things_open.setProperty("quiet", True)
        self.things_open.setFixedWidth(30)                        # 可见 26 × 26 整圆，和动作行的 › 一样
        self.things_open.setCursor(Qt.PointingHandCursor)
        self.things_open.clicked.connect(lambda _=False: self.show_page("things"))
        side.addWidget(self.things_open)
        lay.addWidget(self.row(tr("Things"), right))
        self.things_collapse = Collapse(block, open=self.play_collapse.is_open, pad=SUB_GAP)
        return [self.things_collapse]

    def _posture_section(self) -> QWidget:
        """动作行（叫"动作"）：站 / 坐 / 趴 / 睡 + › 表盘；灵动交互关着才显示（灵动交互里狗只站着）；睡着只剩「醒来」。"""
        window = self.window
        self.posture_section, lay = _column()
        row = QHBoxLayout()
        row.setSpacing(4)                        # 每颗按钮外侧已有2px透明余量，完整英文动作行仍放得下
        row.addWidget(QLabel(tr("Actions")))
        row.addStretch(1)
        self.posture_buttons: dict[str, QPushButton] = {}
        self._posture_group = QButtonGroup(self)
        self._posture_group.setExclusive(True)
        for pid, label in POSTURES:
            b = SelectPill(tr(label))                              # 选中换颜色 0.15 秒渐变
            b.setProperty("horizontalPadding", 6)
            b.setStyleSheet(TIGHT_CSS)
            b.clicked.connect(lambda _=False, p=pid: self._pick_posture(p))
            self._posture_group.addButton(b)
            row.addWidget(b)
            self.posture_buttons[pid] = b
        self.wake_button = MotionButton(tr("Wake up"))                 # 睡着时四个胶囊和 › 都藏起来，只剩它；醒来动画放完才回来
        self.wake_button.setProperty("horizontalPadding", 6)
        self.wake_button.setStyleSheet(TIGHT_CSS)
        self.wake_button.clicked.connect(lambda _=False: window.set_rest_posture("wake"))
        self.wake_button.setVisible(False)
        row.addWidget(self.wake_button)
        self._asleep_shown = False
        self.actions_toggle = MotionButton(symbol="forward")      # 真正居中的矢量箭头；表盘永远从右边展开
        self.actions_toggle.SOUND_KIND = "toggle"
        self.actions_toggle.setAccessibleName(tr("Actions"))
        self.actions_toggle.setProperty("quiet", True)
        self.actions_toggle.setCheckable(True)
        self.actions_toggle.setFixedWidth(30)                     # 可见26 × 26整圆，四周各2px给动效留余量
        self.actions_toggle.setCursor(Qt.PointingHandCursor)
        self.actions_toggle.clicked.connect(lambda _=False: self.toggle_actions())   # clicked 带一个布尔参数，别让它塞进 animated
        row.addWidget(self.actions_toggle)
        lay.addLayout(row)
        self.posture_collapse = Collapse(self.posture_section, open=not window.dynamic_setting, pad=ROW_GAP)   # 关掉灵动交互时从上面长出来
        self.dial = DialPane(window)
        self.attach_side(self.dial)
        return self.posture_collapse

    def _size_row(self) -> QWidget:
        """大小（所有同桌共用一个）：上面一行「大小」、可拖的百分比（左右拖精调、单击原位输入）和长按重置
        （回到这块屏的推荐大小，滑杆上那个小刻度），下面一条整行宽的滑杆（连续跟手；拖到推荐值附近吸过去，咔哒一声）。
        分两行是给表盘留地方：主页面少了两个声音开关，动作行下面只剩一行就放不下 157 的表盘（dial.R_MAX，圆心到下边要 185；
        130 时英文动作名被省略过，test_dial_layout）；大小的范围跟着屏变大以后（电视上到 790%）整行宽的滑杆也细一点。"""
        window = self.window
        section = QWidget()
        column = QVBoxLayout(section)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SIZE_GAP)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        size_title = QLabel(tr("Size"))
        row.addWidget(size_title)
        self.tip_for(size_title, tr("The small tick on the slider fits hopping onto windows best"))
        row.addStretch(1)
        self.size_label = SizeScrubber(self, SCALE_LO, SCALE_HI, self.theme.accent)
        self.size_label.adjustmentStarted.connect(window.begin_scale_adjustment)
        self.size_label.adjustmentFinished.connect(window.end_scale_adjustment)
        self.size_label.valueChanged.connect(self._change_size)
        row.addWidget(self.size_label)
        row.addSpacing(1)
        self.reset_button = HoldButton(tr("Reset"), accent=self.theme.accent, symbol="reset")
        self.reset_button.setAccessibleName(tr("Reset"))
        self.reset_button.setAccessibleDescription(tr("Hold to go back to the recommended size"))
        self.tip_for(self.reset_button, tr("Hold to go back to the recommended size"))
        self.reset_button.held.connect(lambda: self._change_size(self.window.recommended_scale() * 100.0))   # 回到推荐值
        row.addWidget(self.reset_button, 0, Qt.AlignVCenter)
        column.addLayout(row)
        self.size_slider = FineSlider(SCALE_LO, SCALE_HI, self.theme.accent)
        self.size_slider.setAccessibleName(tr("Size"))
        self.size_slider.adjustmentStarted.connect(window.begin_scale_adjustment)
        self.size_slider.adjustmentFinished.connect(window.end_scale_adjustment)
        self.size_slider.valueChanged.connect(self._change_size)
        column.addWidget(self.size_slider)
        self._size_range = (float(SCALE_LO), float(SCALE_HI))
        return section

    def _change_size(self, value: float) -> None:
        self.window.mark_scale_chosen()
        self.window.set_scale(value / 100.0)
        self._sync_size()                          # 狗、圆钮、百分比同一事件里更新，不等 300 ms 定时同步

    def _sync_size(self) -> None:
        value = self.window.world_scale * 100.0                   # 存下来的大小（看细节临时放大不算）
        self._sync_size_range(value)
        self.size_slider.set_value(value)
        self.size_label.set_value(value)
        self.size_slider.set_mark(self.window.recommended_scale() * 100.0 if self.window.dynamic_setting else None)   # 灵动交互开着：小刻度标出最适合跳窗口的大小

    def _sync_size_range(self, value: float) -> None:
        """滑杆、百分比的范围跟着狗在的那块屏走（电视当显示器时上限更大；window.scale_range，最小 30、最大到狗站着约占屏高三分之二）。
        换屏时大小本身不变：现在的比新屏的上限还大，范围就先包住它，不把它显示成上限。拖着的时候不换（手底下的刻度不能跑）。"""
        get = getattr(self.window, "scale_range", None)
        lo, hi = (float(v) for v in (get() if get is not None else (SCALE_LO, SCALE_HI)))
        lo, hi = min(lo, value), max(hi, value)
        if (lo, hi) == self._size_range or self.size_slider.adjusting or self.size_label.adjusting:
            return
        self._size_range = (lo, hi)
        self.size_slider.set_range(lo, hi)
        self.size_label.set_range(lo, hi)

    def _language_row(self) -> QHBoxLayout:
        """语言：标题永远双语，选项永远各写自己的文字。"""
        row = QHBoxLayout()
        row.addWidget(QLabel(i18n.LANGUAGE_ROW))
        row.addStretch(1)
        self.lang_buttons: dict[str, QPushButton] = {}
        self._language_group = QButtonGroup(self)
        self._language_group.setExclusive(True)
        for code in i18n.LANGS:
            b = MotionButton(i18n.LANGUAGE_NAMES[code])
            b.setCheckable(True)
            self._language_group.addButton(b)
            b.setChecked(code == i18n.current())
            b.setProperty("horizontalPadding", 10)
            b.setStyleSheet(PILL_CSS)
            b.clicked.connect(lambda _=False, c=code: self.window.set_language(c) if c != i18n.current() else None)
            row.addWidget(b)
            self.lang_buttons[code] = b
        return row

    def _foot_row(self) -> QHBoxLayout:
        """最下面一行：左边灰字「高级设置…」（整张卡片换成高级设置页），右边「退出」（长按）。"""
        row = QHBoxLayout()
        self.advanced_link = MotionButton(tr("Advanced…"))
        self.advanced_link.setProperty("quiet", True)
        self.advanced_link.setCursor(Qt.PointingHandCursor)
        self.advanced_link.clicked.connect(lambda _=False: self.show_advanced(True))
        row.addWidget(self.advanced_link)
        row.addStretch(1)
        self.quit_button = HoldButton(tr("Quit"), accent=self.theme.accent)
        self.quit_button.held.connect(lambda: self.window._quit())
        row.addWidget(self.quit_button)
        return row

    # ---- 高级设置页 ----
    def _build_advanced(self) -> QWidget:
        window = self.window
        page, lay = _column()
        self.power = Switch()                                       # 省电模式（不写说明小字）：默认关
        self.power.toggled.connect(window.set_power_saving)
        lay.addWidget(self.row(tr("Low Power Mode"), self.power))
        lay.addLayout(self._appearance_row())
        self.media_volume = _VolumeRow(self, tr("Media sounds"), tr("Barks, the ball, landing"), media=True)
        self.interface_volume = _VolumeRow(self, tr("Interface sounds"), tr("Buttons, switches and sliders"), media=False)
        _VolumeRow.align(self.media_volume, self.interface_volume)
        lay.addWidget(self.media_volume)
        lay.addWidget(self.interface_volume)
        lay.addLayout(self._language_row())
        lay.addWidget(self.hairline_widget())
        self.uninstall_button = MotionButton(tr("Uninstall…"))
        self.uninstall_button.clicked.connect(lambda _=False: self.show_page("uninstall"))
        lay.addWidget(self.row(tr("Uninstall widget"), self.uninstall_button))
        lay.addWidget(self._version_row())
        return page

    def _version_row(self) -> QWidget:
        """最底下和主页面最后一行（高级设置… / 退出）同一种灰字行：
        左边「版本 0.5.1 (7)」（macOS「关于」窗口的写法：版本号 (构建号)；发布版只写版本号，构建号在开发者设置页，updater.version_text），右边「检查更新」和它的几种结果。
        没填发布仓库（config.UPDATE_REPO）时右边空着，只有版本号。"""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.version_label = QLabel(f"{tr('Version')} {updater.version_text(config.VERSION, config.BUILD)}")   # 发布版不带构建号
        self.version_label.setProperty("muted", True)
        self.version_label.installEventFilter(self)               # 连点五下进开发者设置页
        self._version_clicks: list[float] = []
        lay.addWidget(self.version_label)
        self.update_button = UpdateStatus()
        self.update_button.clicked.connect(lambda _=False: self._update_clicked())
        lay.addWidget(self.update_button, 1)
        if not updater.enabled():
            self.update_button.hide()
            lay.addStretch(1)
        self._update_state = None
        self._update_pending = False
        return row

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "version_label", None) and event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) \
                and event.button() == Qt.LeftButton:
            self._version_clicked()
        return super().eventFilter(obj, event)

    def _version_clicked(self) -> None:
        """版本号连点五下（两下之间不超过 VERSION_CLICK_GAP 秒）：进开发者设置页。"""
        now = time.monotonic()
        self._version_clicks = [t for t in self._version_clicks if now - t <= VERSION_CLICK_GAP * VERSION_CLICKS] + [now]
        recent = self._version_clicks[-VERSION_CLICKS:]
        if len(recent) >= VERSION_CLICKS and all(b - a <= VERSION_CLICK_GAP for a, b in zip(recent, recent[1:])):
            self._version_clicks = []
            self.show_page("tuning")

    # ---- 卸载 / 更新的页 ----
    def _page_column(self, *items) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for it, gap in items:
            if gap:
                lay.addSpacing(gap)
            (lay.addWidget if isinstance(it, QWidget) else lay.addLayout)(it)
        return page

    @staticmethod
    def _button_row(*buttons) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        for b in buttons:
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)    # 一样宽
            row.addWidget(b, 1)
        return row

    def _build_uninstall(self) -> QWidget:
        """卸载确认：没有说明，只有「取消」和红色的「删除」；删除要按住 0.6 秒。"""
        cancel = MotionButton(tr("Cancel"))
        def cancel_uninstall():
            self.window.cancel_uninstall()
            self.show_page("advanced")
        cancel.clicked.connect(cancel_uninstall)
        self.delete_button = HoldPill(tr("Delete"), "danger")
        self.delete_button.held.connect(self.window.uninstall)
        return self._page_column((self._button_row(cancel, self.delete_button), 0))

    def _build_notes(self) -> QWidget:
        """更新说明：发布日期 · 大小，Release 正文里的「更新内容」，「下次再说」/「更新」（长按）。"""
        self.notes_meta = QLabel()
        self.notes_meta.setProperty("muted", True)
        self.notes_box = QWidget()
        box = QVBoxLayout(self.notes_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        later = MotionButton(tr("Later"))
        later.clicked.connect(lambda _=False: self.show_page("advanced"))
        self.update_now = HoldPill(tr("Update"), "primary", self.theme.accent)
        self.update_now.held.connect(self._start_download)
        return self._page_column((self.notes_meta, 0), (self.notes_box, 10), (self._button_row(later, self.update_now), 16))

    def _build_downloaded(self) -> QWidget:
        """已下载：app 名 + 版本、「安装包已下载 · 38 MB」、「删除安装包」/「取消」/「安装」（删除、安装长按）。"""
        self.downloaded_name = QLabel()
        self.downloaded_name.setStyleSheet("font-weight: 700; font-size: 14px;")
        self.downloaded_size = QLabel()
        self.downloaded_size.setProperty("muted", True)
        self.remove_button = HoldPill(tr("Remove"), "danger")     # 删东西：和卸载的「删除」一样红
        self.remove_button.held.connect(self._remove_package)
        cancel = MotionButton(tr("Cancel"))
        cancel.clicked.connect(lambda _=False: self.show_page(self._downloaded_from))
        self.install_button = HoldPill(tr("Install"), "primary", self.theme.accent)
        self.install_button.held.connect(self.window.install_update)
        for b in (self.remove_button, cancel, self.install_button):
            b.setProperty("horizontalPadding", 8)   # 三个一样宽：「删除安装包」五个字也放得下三等分
        return self._page_column((self.downloaded_name, 0), (self.downloaded_size, 4),
                                 (self._button_row(self.remove_button, cancel, self.install_button), 16))

    def _fill_notes(self) -> None:
        rel = self.window.updater.release
        lay = self.notes_box.layout()
        while lay.count():
            item = lay.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                inner = item.layout()
                while inner.count():
                    w = inner.takeAt(0).widget()
                    if w is not None:
                        w.deleteLater()
        if rel is None:
            return
        lang = i18n.current()
        date = rel.date_text(lang)
        self.notes_meta.setText(tr("Released {date} · {size}", date=date, size=rel.size_text()) if date else rel.size_text())
        notes = rel.notes(lang) or [(False, tr("No release notes for this version"))]
        for bullet, text in notes:
            line = QHBoxLayout()
            line.setSpacing(6)
            if bullet:
                dot = QLabel("·")
                dot.setFixedWidth(8)
                dot.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
                dot.setStyleSheet("font-weight: 700;")
                line.addWidget(dot, 0, Qt.AlignTop)
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            line.addWidget(label, 1)
            lay.addLayout(line)

    def _fill_downloaded(self) -> None:
        rel = self.window.updater.release
        if rel is not None:
            self.downloaded_name.setText(f"{config.APP_NAME} {rel.label()}")
            self.downloaded_size.setText(tr("Downloaded · {size}", size=rel.size_text()))

    def open_downloaded(self, came_from: str) -> None:
        self._downloaded_from = came_from
        self.show_page("downloaded")

    def _update_clicked(self) -> None:
        state = self.window.updater.state
        if state in ("idle", "offline"):
            self.window.updater.check()
        elif state == "found":
            self.show_page("notes")
        elif state == "downloaded":
            self.open_downloaded("advanced")
        elif state == "failed":
            self.window.updater.download()

    def _start_download(self) -> None:
        """更新说明页长按「更新」：回到高级设置，最底下显示正在下载。"""
        self.show_page("advanced")
        self.window.updater.download()

    def _remove_package(self) -> None:
        self.window.updater.remove_package()
        self.show_page(self._downloaded_from)

    def sync_update(self) -> None:
        """「检查更新」这一行、顶部栏的新版本胶囊跟着 updater 的状态变。"""
        if ui_frozen():
            self._update_pending = True
            return
        self._update_pending = False
        up = self.window.updater
        text, clickable, blue = UPDATE_LINES.get(up.state, UPDATE_LINES["idle"])
        if up.state in ("offline", "failed"):
            text = UPDATE_ERRORS.get(up.error_reason, text)
        text = tr(text, pct=round(up.progress * 100)) if "{pct}" in text else tr(text)

        self.update_button.set_status(text, clickable, "blue" if blue else None,
                                      animated=self._update_state not in (None, up.state))
        self._update_state = up.state
        prompt = getattr(self.window, "update_prompt", None)
        chip = up.state == "downloaded" and self.pages[self.page].chip and not (prompt is not None and prompt.isVisible())
        self._tag.set_chip(i18n.says("New version downloaded") if chip else "")   # 新版本下载好了（狗旁边那张提示收起来以后）：顶部栏里名字右边、× 左边，每一页都有；几种说法按地方挑
        if self.page in ("notes", "downloaded") and (up.release is None or (self.page == "downloaded" and up.state != "downloaded")):
            self.show_page("advanced" if self.page == "notes" else self._downloaded_from)   # 安装包被删了 / 说明作废了：退回去

    def _lead_click(self, page: str) -> None:
        """点顶部栏左边的圆。进出关于页的动画走着的时候，点一下就掉头（狂点每一下都要有反应）：进的路上点 → 回主页面，
        回的路上点（还没真的换回主页面、已经换回来都一样）→ 接着进关于页。不照顶部栏这时的样子算（要等动画走到才换），
        也不照圆里这时画的算（画着 D、M 时点了算「进」，进的前 0.8 秒、回的前 0.5 秒点了都没反应）。"""
        hero = self.about_hero
        if hero.active and page in ("main", "about") and self.page in ("main", "about"):
            page = "main" if hero.into else "about"
        self.show_page(page)

    def _back_target(self) -> str:
        return self.pages[self.page].back_target()

    def _notes_title(self) -> str:
        rel = self.window.updater.release
        return tr("Update {version}", version=rel.label()) if rel is not None else tr("New version")

    @property
    def advanced_open(self) -> bool:
        return getattr(self, "page", "main") != "main"

    def _appearance_row(self) -> QHBoxLayout:
        """外观：浅色 / 深色 / 跟随系统（只换界面的贴纸颜色，狗不变）。"""
        row = QHBoxLayout()
        row.setSpacing(4)                        # 连同按钮各自的透明余量，英文三项完整显示
        row.addWidget(QLabel(tr("Appearance")))
        row.addStretch(1)
        self.appearance_buttons: dict[str, QPushButton] = {}
        self._look_group = QButtonGroup(self)
        self._look_group.setExclusive(True)
        for mode, label in (("light", "Light"), ("dark", "Dark"), ("system", "System")):
            b = MotionButton(tr(label))
            b.setCheckable(True)
            b.setProperty("horizontalPadding", 10)
            b.setStyleSheet(PILL_CSS)
            b.clicked.connect(lambda _=False, m=mode: self.window.set_appearance(m))
            self._look_group.addButton(b)
            row.addWidget(b)
            self.appearance_buttons[mode] = b
        return row

    def _coat_row(self) -> QVBoxLayout:
        """毛色：四套原装的各一张小狗头像、下面写名字（两色圆点看不出是哪一套）+ 两色圆点（自定义，点开自定义毛色页；
        不能自定义的模型没有这一格，window.custom_coat_on）。
        头像第一次进这一页时借小组件的画布离屏画（_fill_coat_faces）；画出来之前、画不出来时是上深下浅的两色（showEvent 从贴图里取）。"""
        window = self.window
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(QLabel(tr("Coat color")))                         # 单独一个 Coat 会被读成外套
        row = QHBoxLayout()
        row.setSpacing(0)
        box.addLayout(row)
        self.swatches: list[Avatar] = []
        self.coat_labels: list[QLabel] = []
        self._coat_group = QButtonGroup(self)
        self._coat_group.setExclusive(True)

        def cell(button: Avatar, text: str) -> QLabel:
            col = QVBoxLayout()
            col.setSpacing(6)
            col.addWidget(button, 0, Qt.AlignHCenter)
            label = QLabel(text)
            label.setProperty("muted", True)
            label.setAlignment(Qt.AlignHCenter)
            col.addWidget(label)
            row.addLayout(col, 1)
            return label

        for i in range(1, len(window.coat_names()) + 1):
            s = Avatar("rgba(128,128,128,0.3)")
            s.clicked.connect(lambda _=False, i=i: (window.set_coat(i), self.strip.look_changed()))
            s.setAccessibleName(window.coat_label(i))
            self._coat_group.addButton(s, i)
            self.swatches.append(s)
            self.coat_labels.append(cell(s, window.coat_label(i)))
        self.custom_swatch = Avatar("transparent")                # 两色圆点：自定义毛色的主色 / 副色
        self.custom_swatch.SOUND_KIND = "action"                  # 已选时再点仍进入编辑，不是重复选择
        self.tip_for(self.custom_swatch, tr("Custom…"))
        self.custom_swatch.clicked.connect(window.open_coat)
        self._coat_group.addButton(self.custom_swatch, CUSTOM_COAT_ID)
        if window.custom_coat_on:
            cell(self.custom_swatch, tr("Custom"))
        else:                                                     # 这个模型不能自定义毛色（pack.json 的 custom_coat）：圆点照样建（_sync 要用），不放进这一行，四张头像自己四等分
            self.custom_swatch.setParent(self)
            self.custom_swatch.hide()
        self._custom_colors: Optional[tuple[str, str]] = None
        self._swatches_ready = False
        self._faces_ready = False
        self._faces_cancel = None                  # 一张张画头像那件还在画：取消它的函数（_fill_coat_faces）
        return box

    def _paint_swatches(self, decode: bool = True) -> None:
        """毛色那一行的色块：每套上深下浅两色（头像画出来之前顶着），贴图不在的灰掉。decode：没算过的现在解贴图算（打开卡片时）；
        不解（换了模型以后重建这一行时，狗正在淡入）：只用算过的，没算过的先留灰的等头像。"""
        window = self.window
        pairs = window.coat_swatches() if decode else window.known_swatches()
        available = window.coat_available()
        for s, pair, ok in zip(self.swatches, pairs, available):
            if pair is not None:
                s.set_fur(*pair)
            s.setEnabled(ok)
        self._swatches_ready = decode or all(pair is not None for pair, ok in zip(pairs, available) if ok)

    def _fill_coat_faces(self) -> None:
        """进详情页：四张头像还没画就画——一帧一张（贴图在后台线程解，window.coat_faces；一口气画四张的话，真机上一帧 160～180 毫秒），
        要画布已经好了。卡片开着 0.7 秒后先开始画，点进去时多半已经画好（showEvent）；正在画就不重来。画不出来不挡进页，留着两色圆点。"""
        if self._faces_ready or self._faces_cancel is not None or not self.isVisible():
            return
        swatches, got, finished = self.swatches, [], []

        def deliver(i: int, image) -> None:
            if swatches is self.swatches:             # 那一行重建过（换了模型）：画给旧的不要了
                swatches[i - 1].set_portrait(image)
                got.append(i)

        def done() -> None:
            finished.append(True)
            self._faces_cancel = None
            if swatches is self.swatches:
                self._faces_ready = bool(got)
        try:
            cancel = self.window.coat_faces(Avatar.ICON * 4, Avatar.ICON * 4, deliver, done)
        except Exception:                             # noqa: BLE001 —— 和斑纹图一样：这里出错换页整个停下，点了没反应
            logging.getLogger("coat").exception("coat faces failed")
            return
        if not finished:
            self._faces_cancel = cancel

    # ---- 模式相关 ----
    def _mode_changed(self, setter, on: bool) -> None:
        setter(on)
        self.sync()                       # 开关和窗口的状态立刻对齐

    def _pick_posture(self, posture: str) -> None:
        self.window.set_rest_posture(posture)

    def toggle_actions(self, animated: bool = True) -> None:
        """姿势行的 ›：表盘弹出来 / 收回去。表盘永远在右边，箭头永远指右；开着时按钮显示按下态（别翻成 ‹：会让人以为弹在左边）。"""
        self.actions_toggle.setChecked(self.toggle_side(animated))

    # ---- 换页 ----
    def toggle_play_options(self, animated: bool = True, on: Optional[bool] = None) -> None:
        """灵动交互那一行的调节图标：下面滑出 / 收起子选项，卡片跟着变长变短；展开着图标是按下的样子。"""
        on = (not self.play_collapse.is_open) if on is None else bool(on)
        self.play_options_btn.setChecked(on)
        self.window.play_options_open = on
        if on == self.play_collapse.is_open:
            return
        self.play_collapse.set_open(on, animated)
        if self.things_collapse is not None:
            self.things_collapse.set_open(on, animated)           # 「物件」那一行跟着子选项一起开合
        self._refit(animated)

    def _sync_play_options(self, w) -> None:
        """子选项的开关对齐到窗口；灵动交互关了：图标淡出，展开着的也收起。「物件」页的格子跟着道具栏、右键道具切的变。"""
        for option in PLAY_OPTIONS:
            self.play_switches[option.key].set_silently(getattr(w, option.attr))
        if self.things_collapse is not None:
            n = w.things_placed()
            text = str(n) if n else ""                             # 摆着几件；一件没摆不写
            if self.things_count.text() != text:
                self.things_count.setText(text)
            if self.page == "things":
                if w.dynamic_setting:
                    self.things_page.sync()                        # 道具栏、右键道具把它收了：格子跟着变
                else:
                    self.show_page("main")                         # 灵动交互关了：这一页的入口没了，回主页面
        if self._tune.on != w.dynamic_setting:
            self._tune.set(w.dynamic_setting)
            if not w.dynamic_setting:
                self.toggle_play_options(on=False)

    def show_advanced(self, on: bool, animated: bool = True) -> None:
        """最下面的「高级设置…」：整张卡片换成高级设置页（左上角 ‹ 回来）；高度 0.2 秒过渡。"""
        self.show_page("advanced" if on else "main", animated)

    def show_page(self, page: str, animated: bool = True, home: bool = False) -> None:
        """换到卡片的某一页（pages 里登记的）。顶部栏留着不动，自己换字、宽度和左边圆里的图案（_seat_title）；下面的内容旧的前一半淡出、新的后一半淡入
        （Card.swap_content 只拍内容区，盖不到顶部栏），高度用弹簧过渡。主页面 ↔ 详情页：「我的同桌」那一条留着自己变样，只淡它下面那几行。"""
        self.size_label.cancel_interaction()
        if (not home and page == "main" and self.page == "about" and animated and self.isVisible() and not self._still
                and not native.reduce_motion() and self.about_hero.go_home(lambda: self.show_page("main", animated, home=True))):
            return                                                # 关于页 → 主页面：动画先倒着走，线快回到圆里时它再调回来真的换（about.Hero.go_home）
        if page == self.page and page in ("main", "about") and self.about_hero.active:
            if page == "about" and not self.about_hero.into:
                self.about_hero.go(True)                          # 回主页面走到一半（还没真的换页）又点进来：钟平滑掉头，接着往关于页走
            return                                                # 动画走着时换到同一页什么都不做（不然换页那套会把正淡着的主页面一下子跳到头）
        if page in self._stale and page != self.page:
            self._rebuild((page,))                                # 换了模型以后还没重建的（开发者设置页一直等到这时）：进之前先照新模型建好
        previous, target = self.pages[self.page], self.pages[page]
        if page != self.page and previous.leave is not None:
            previous.leave()
        if page != "main" and self.side_open:
            self.toggle_actions(animated=False)
        if target.enter is not None:
            target.enter()
        if self.window.settings_panel is self:                  # 换语言 / 外观重建卡片时收起来的那张旧的回主页面，不算离开
            self.window.closeup.set_open(target.closeup)      # 详情页、自定义毛色页：狗站上转台；离开、关卡片（hideEvent 回主页面）：转回来、放下

        here, there = self.page in STRIP_PAGES, page in STRIP_PAGES
        crossing = page != self.page and here != there       # 进出有「我的同桌」那一条的两页：那一条跟着内容一起淡
        within = page != self.page and here and there        # 主页面 ↔ 详情页：那一条留着、自己变样，下面几行换
        hero = (page != self.page and {self.page, page} == {"main", "about"} and animated and self.isVisible()
                and not self._still and not native.reduce_motion())   # 主页面 ↔ 关于页：圆里的 app 图标长成关于页的大图标（about.Hero）
        if page != self.page:
            self.end_rename_now()
        if not hero and self.about_hero.active and page != self.page:
            self.about_hero.finish(run_pending=False)         # 走到一半换去别的页：关于页那一段直接到头，交还给它们自己画（再照别的换页拍旧样子）；
                                                              # 正等着换回主页面的不换了（要去的是别的页）

        def change() -> None:
            self.page = page
            self._fit_bottom()
            self.strip.setVisible(there)
            if crossing or not there:
                self.strip.set_focus(page == "pet", animated=False)
            for name, entry in self.pages.items():
                entry.widget.setVisible(page == name)

        self._seating = True                                  # 换页的路上滑动条重新显示会报「正中换了」：顶部栏等下面一次摆好（_seat_title），
        try:                                                  # 不然胶囊里的小图标先换、圆里的图案后换，看不出是 app 图标从圆换到了胶囊（不流）
            if within:
                self._swap_below_strip(change, animated)
                self.strip.set_focus(page == "pet", animated and self.isVisible())
            elif hero:
                self._swap_about(change, page == "about")
            else:
                self.swap_content(change, animated and self.page != page)
        finally:
            self._seating = False
        self._seat_title(page, animated, flow=not hero)
        self.sync_update()
        self._refit(animated)
        if hero and (page == "about" or self.about_hero.active):
            self.about_hero.go(page == "about")                 # 排好版再开始：图落在哪、字在哪都量得准；回：接着倒着走

    def _fit_bottom(self) -> None:
        """底边距：主页面、高级设置、自定义毛色最底下是灰字行，用 PAD_QUIET；最底下是胶囊按钮的页用 PAD（和两边一样）。
        上边距：主页面、详情页上「我的同桌」那一条紧贴顶部栏，不再空 10。"""
        m = self.body.contentsMargins()
        bottom = PAD_QUIET if self.pages[self.page].quiet else PAD
        top = 0 if self.page in STRIP_PAGES else BODY_TOP
        if (m.top(), m.bottom()) != (top, bottom):
            self.body.setContentsMargins(m.left(), top, m.right(), bottom)

    # ---- 顶部栏：每一页同一条，只换字、宽度和左边圆里的图案 ----
    def _seat_title(self, page: str, animated: bool = True, flow: bool = True) -> None:
        """顶部栏在这一页的样子（Page.lead / title_click 登记的）：左边的圆、点名字做什么、名字胶囊上的字。鼠标正停在名字上时，狗抬不抬跟着这一页换。
        flow=False：app 图标不流进胶囊（进出关于页：它长成关于页的大图标，about.Hero），胶囊里照别的换页淡。"""
        entry = self.pages[page]
        self._tag.set_look(entry.lead, entry.title_icon(), animated, flow)   # 圆里的图案和胶囊里的小图标一起换：app 图标从圆换到胶囊就流过去
        self._tag.set_name_shown(entry.name, animated)
        self.set_title_click(entry.title_click)
        self.strip.set_name_hover(self._tag.name_hovering and entry.title_click == "open")
        Card.set_title(self, entry.title_text(), animated, entry.title_outlined())

    def _sync_title(self, animated: bool = True) -> None:
        """这一页的标题可能变了（滑动条正中换了一格、改了名字、名单变了、添加页换了模型）：顶部栏跟上；字没变就什么都不做。"""
        if getattr(self, "_seating", False):
            return
        entry = self.pages[self.page]
        self._tag.set_icon(entry.title_icon(), animated)
        Card.set_title(self, entry.title_text(), animated, entry.title_outlined())

    def _strip_title(self) -> str:
        """主页面顶部栏的名字：「我的同桌」正中那一格的（滑动时过一半就换），停在「+」上是「添加同桌」。"""
        i = self.strip.center()
        return self.strip.names[i] if i < len(self.strip.names) else tr("Add a deskmate")

    def _strip_at_add(self) -> bool:
        """正中是「+」：顶部栏那颗画成描边标签（不是名字，样子也不像名字）。"""
        return self.strip.center() >= len(self.strip.pets)

    def _pack_icon(self, pack_id: str) -> str:
        """这个模型的物种图标（模型包里写的；没有就 app 图标）。模型不在了（文件删了）按现在这个模型的。"""
        pack = next((p for p in self.pets if p.id == pack_id), None) or self.window.pack
        return pack.icon or marks.APP

    def _strip_icon(self) -> str:
        """主页面名字胶囊里的小图标：正中那一格是同桌就是它的物种图标；「+」上是 app 图标（描边的「添加同桌」不是名字）。"""
        i = self.strip.center()
        return self._pack_icon(self.strip.pets[i].pack) if i < len(self.strip.pets) else marks.APP

    def _add_icon(self) -> str:
        """添加页：选的模型有物种图标（狗 = 骨头）就用它，别的 app 图标。"""
        return self._pack_icon(self._add_pack) if self._add_pack else marks.APP

    def _swap_about(self, change, into: bool) -> None:
        """主页面 ↔ 关于页：关于页那一块（大图标、名字、版本、简介）整段由过渡动画画（about.Hero），拍旧样子时不带它们。
        进：主页面的旧样子前一半淡出，关于页不淡入（动画画它）；回：关于页那一块从动画里收掉，主页面后一半淡入（和别的换页一样）。
        上一趟还没淡完（走到一半反过来）不先跳到头：crossfade 拍的是屏幕上现在的样子，接着淡，主页面不会一下子没了再出来。"""
        if not into and not self.about_hero.active:
            self.about_hero.capture()                         # 回：换页之前拍下那几行字（这时关于页还显示着）
        self.about_page.veil(True)
        view = self.scroll.viewport()
        rect = QRect(view.mapTo(self._main, QPoint(0, 0)), view.size())
        self._swap = self.crossfade(self._main, rect, change, [] if into else [self.content], True)

    def _swap_below_strip(self, change, animated: bool) -> None:
        """主页面 ↔ 详情页：只淡入淡出那一条下面的几行（那一条自己在变样，不能被拍下来的旧图盖住）。"""
        if self._swap is not None:
            self._swap.tick(10.0)
        view = self.scroll.viewport()
        top = self.strip.mapTo(self._main, QPoint(0, self.strip.height())).y()
        bottom = view.mapTo(self._main, QPoint(0, 0)).y() + view.height()
        pages = [entry.widget for entry in self.pages.values()]
        self._swap = self.crossfade(self._main, QRect(0, top, self._main.width(), max(1, bottom - top)), change, pages, animated)

    def pet_changed(self) -> None:
        """换了同桌、添了、删了（窗口调）：名字、滑动条、顶部栏、各个开关跟上。换了模型：详情页的毛色那一行（几套、叫什么、有没有「自定义」）、
        自定义毛色页、开发者设置页是照上一个模型建的，记成过期（贴图换上以后重建，coat_landed；开发者设置页进去时才重建）。"""
        self.end_rename_now()
        self._name_title = self.window.dog_name
        if self.window.model is not self._built_for:
            self._built_for = self.window.model
            self._stale = {"pet", "coat", "tuning"}
        self.strip.refresh()
        self._sync_title()
        self.sync()

    def coat_landed(self) -> None:
        """换同桌的贴图换上了（window._coat_on，狗开始淡入）：现在这只的贴纸照身上这张画；换了模型的话，过期的详情页、自定义毛色页这时重建
        （下一轮事件循环里做，不占换的那一下；量过两页共约 3.6 毫秒），开发者设置页进去时才重建（11.5 毫秒）。"""
        self.strip.look_changed()
        if self._stale & {"pet", "coat"}:
            QTimer.singleShot(0, self._rebuild_after_switch)

    def _rebuild_after_switch(self) -> None:
        """一帧重建一页（详情页、自定义毛色页各约 5 毫秒，挤在一帧里那一帧 25 毫秒）。"""
        self._rebuild(("pet",))
        QTimer.singleShot(REBUILD_GAP_MS, lambda: self._rebuild(("coat",)))

    def _rebuild(self, names) -> None:
        """照现在的模型重建过期的那几页（_stale）：详情页（看细节那一块、毛色那一行、删除）、自定义毛色页、开发者设置页。正开着的那一页不动（换模型时它们都藏着）。
        毛色那一行的色块只用算过的深浅两色（没算过的留灰的等头像，不在这里解贴图），四张头像进详情页时再一张张画（_fill_coat_faces）。"""
        names = [n for n in names if n in self._stale and n != self.page]
        if names and self._swap is not None:
            self._swap.tick(10.0)                                 # 正在淡入淡出的（拿着旧的那几页）先走完，再拆旧页
        for name in names:
            self._stale.discard(name)
            if name == "pet":
                if self._faces_cancel is not None:
                    self._faces_cancel()                          # 旧那一行的头像还在一张张画：不画了
                    self._faces_cancel = None
                group, custom = self._coat_group, self.custom_swatch
                self.pet_page = self._build_pet()
                self._swap_page("pet", self.pet_page)
                group.deleteLater()                               # 这两样挂在卡片上，不跟着旧的那一页走
                custom.deleteLater()
                self._paint_swatches(decode=False)            # 头像不在这里补画：进详情页时再一张张画（换完 1.5 秒里不画，一张约 25 毫秒）
            elif name == "coat":
                self.coat_page = CoatPage(self, self.window)
                self._swap_page("coat", self.coat_page, enter=self.coat_page.on_show, leave=self.coat_page.on_hide)
            elif name == "tuning":
                self.tuning_page = self._build_tuning()
                self._swap_page("tuning", self.tuning_page, enter=self.tuning_page.on_show)

    def _swap_page(self, name: str, widget: QWidget, **changes) -> None:
        """换掉一页的内容：新的放在旧的那个位置（藏着），登记的那一项跟着换，旧的删掉（它的悬浮说明一起摘掉）。"""
        old = self.pages[name].widget
        self.body.insertWidget(self.body.indexOf(old), widget)
        widget.setVisible(False)
        self.pages[name] = replace(self.pages[name], widget=widget, **changes)
        self._tips = {w: t for w, t in self._tips.items() if shiboken6.isValid(w) and w is not old and not old.isAncestorOf(w)}
        old.hide()
        self.body.removeWidget(old)
        old.deleteLater()

    def open_add_pet(self) -> None:
        self.show_page("add")

    def _build_add(self) -> QWidget:
        """添加同桌（滑动条最后那格「+」进）：选模型（每个一格）、起名字、「添加」。一只同桌的模型就在这里定，以后不能换（想要别的模型再添一只）。"""
        from PySide6.QtWidgets import QGridLayout, QLineEdit
        page, lay = _column(10)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.add_tiles: list[PetTile] = []
        self._add_pack = ""
        for k, pack in enumerate(self.pets):
            tile = PetTile(pack, k == 0)
            tile.setCursor(Qt.PointingHandCursor)
            tile.clicked.connect(lambda _=False, i=pack.id: self._pick_add(i))
            grid.addWidget(tile, k // 2, k % 2)
            self.add_tiles.append(tile)
        lay.addLayout(grid)
        self.more_note = None
        if len(self.pets) < 2:                                      # 只有一个模型：写一句还会有
            self.more_note = QLabel(tr("More deskmates on the way"))
            self.more_note.setProperty("muted", True)
            self.more_note.setAlignment(Qt.AlignCenter)
            lay.addWidget(self.more_note)
        self.add_name = QLineEdit()
        self.add_name.setMaxLength(NAME_MAX * 12)                  # 真正的上限按看得见的字数算（添加时剪）
        self.add_name.returnPressed.connect(self._add_pet)
        lay.addWidget(self.row(tr("Name"), self.add_name))
        cancel = MotionButton(tr("Cancel"))
        cancel.clicked.connect(lambda _=False: self.show_page("main"))
        self.add_button = MotionButton(tr("Add"))
        self.add_button.setProperty("kind", "primary")
        self.add_button.clicked.connect(lambda _=False: self._add_pet())
        lay.addLayout(self._button_row(cancel, self.add_button))
        return page

    def _pick_add(self, pack_id: str) -> None:
        self._add_pack = pack_id
        self.window.warm_pack(pack_id)                            # 选了别的模型：后台先备着，点「添加」时多半已经好了
        for tile in self.add_tiles:
            tile.selected = tile.pack.id == pack_id
            tile.update()
        pack = next((p for p in self.pets if p.id == pack_id), None)
        if pack is not None:
            self.add_name.setPlaceholderText(pack.default_name)
        if getattr(self, "page", "") == "add":
            self._sync_title()                                    # 胶囊里的小图标跟着选的模型换

    def _fill_add(self) -> None:
        """进添加页：默认选现在这个模型，名字空着（不填就用模型自己的名字）。从已下载页点「取消」回来（顶部栏的新版本胶囊点过去的）：
        照原样留着，打了一半的名字不清掉。"""
        if self.page == "downloaded":
            return
        self.add_name.clear()
        self._pick_add(self.window.pack.id if any(p.id == self.window.pack.id for p in self.pets) else (self.pets[0].id if self.pets else ""))

    def _add_pet(self) -> None:
        pack = next((p for p in self.pets if p.id == self._add_pack), None)
        if pack is None:
            return
        name = self.add_name.text().strip() or pack.default_name
        self.show_page("main")
        self.window.add_pet(pack.id, name, then=self.strip.added)   # 当场换过去（别的模型也是），新的那只从桌沿后面冒出来；
                                                                      # 别的模型还没备好就备好了再添，读不出来的添不进去

    def finish_page_anim(self) -> None:
        """换页 / 子行展开的高度过渡、标题行的滑动和淡入淡出、开关、展开的行立刻走到头（单测用）。"""
        self.finish_animations()
        self.finish_height()
        self._tag.finish_now()

    def _refit(self, animated: bool) -> None:
        """内容变了重新量高度；显示着就从现在画出来的高度过渡到新高度（Card.animate_height：窗口只改一次大小，底边用弹簧滑，和标题行同一个节拍）。"""
        h0 = self.painted_height()
        was = self.height_animating
        smooth = animated and self.isVisible() and not self._still
        if smooth:
            self.hold_height()                                    # 先进入过渡再量：窗口只改一次大小（变矮时走完才缩）
        h1 = self.fit_height()
        if smooth and (h1 != h0 or was):
            self.animate_height(h0, h1)
        else:
            self.finish_height()

    def set_title(self, text: str, animated: bool = True) -> None:
        """改狗的名字（window.set_dog_name 调）：记下来，滑动条上的名字和顶部栏跟上（顶部栏只在主页面、详情页写名字，别的页回来再显示）。"""
        self._name_title = text
        self.strip.refresh()                                      # 滑动条的名单、名字重新取（主页面顶部栏写的是它正中那一格的）
        self._sync_title(animated)

    def side_anchor_y(self) -> float:
        """表盘对着姿势行的 › 那个高度。"""
        b = self.actions_toggle
        return float(b.mapTo(self, QPoint(0, b.height() // 2)).y())

    def side_room(self) -> Optional[float]:
        """动作行到卡片上下边，近的那边还有多少地方：表盘半径不能超过它。"""
        y = self.side_anchor_y() - self._main.y()
        return min(y, self._main.height() - y)

    def side_extent(self) -> tuple[int, int]:
        """表盘要的地方；动作行藏着（灵动交互开着、不在主页面）时表盘打不开，摆卡片时不用给它让地方。
        别按藏着的那一行的旧位置算：卡片会莫名其妙往左让出一个表盘宽。"""
        if not self.actions_toggle.isVisibleTo(self) and not self.side_open:
            return 0, 0
        return super().side_extent()

    # ---- 和窗口对齐 ----
    def showEvent(self, event) -> None:
        if not self._swatches_ready:
            self._paint_swatches()
            QTimer.singleShot(300, self._warm_pages)              # 第一次打开：等淡入完再把后面几页预先排好版
            QTimer.singleShot(700, self._fill_coat_faces)         # 详情页的四张毛色头像先画好（要解码贴图），点进去那一下不卡
            QTimer.singleShot(500, self._warm_about)              # 关于页那张图（拼猫狗、动物，约 40 毫秒）先拼好，第一次点不卡
        QTimer.singleShot(400, self.window.warm_pets)             # 开场动画走完：名单里别的模型在后台先备好（换过去不重启，widget/kits.py）
        with self.still():                                         # 打开那一下对齐设置：开关、动作行直接到位，不在淡入时才滑过去
            self.sync()
            self.sync_update()
        self._timer.start()
        super().showEvent(event)

    def _warm_about(self) -> None:
        if not about_art.ready() and not ui_frozen():
            about_art.scene()

    def _warm_pages(self) -> None:
        """后面几页（高级设置、卸载、更新说明、已下载）在后台先画一次：样式表、字形第一次用时要算，第一次进高级设置那一帧拖到 30 毫秒。"""
        if ui_frozen():
            return
        for entry in self.pages.values():
            page = entry.widget
            if entry.warm and not page.isVisible():
                page.resize(self._main.width(), max(1, page.sizeHint().height()))
                page.grab()
        self.body.invalidate()                                     # 拍藏着的页时 Qt 临时把它当成显示着，主页面的各行被挤上去一帧（录屏查出来的）：马上排回来
        self.body.activate()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        self.size_label.cancel_interaction()
        self.window.updater.forget()                             # 「发现新版本」这些结果关掉设置就作废，下次重新点检查更新
        super().hideEvent(event)
        if self.page != "main":
            self.show_page("main", animated=False)             # 关掉再打开回到主页面；换外观 / 换语言重建时由窗口把页带过去

    def sync(self) -> None:
        if ui_frozen():
            return
        if self._update_pending:
            self.sync_update()
        w = self.window
        if self.page in STRIP_PAGES and self.isVisible():
            self.strip.look_changed()                              # 毛色换了：滑动条上那只的贴纸跟着换
        self.pet_delete.setEnabled(len(w.pets()) > 1)              # 最后一只删不了
        self.follow.set_silently(w.follow_cursor)
        self.dynamic.set_silently(w.dynamic_setting)   # 开关是设置里的（看细节那两页临时退出时不变）
        self.media_volume.sync(w.media_volume, w.media_muted)
        self.interface_volume.sync(w.interface_volume, w.interface_muted)
        self.meta.set_silently(w.show_metadata)
        self.power.set_silently(w.power_saving)
        self._sync_play_options(w)
        self._sync_posture_row(w)
        for mode, b in self.appearance_buttons.items():
            if b.isChecked() != (mode == w.appearance):
                b.setChecked(mode == w.appearance)
        self._sync_size()
        self.pet_detail.sync()                                     # 看细节：放大的上限（换了屏、改了大小）、放到多少、摆的什么姿势（看得见的那一块才对）
        self.coat_page.detail.sync()
        b = self._coat_group.button(w.coat if w.coat else CUSTOM_COAT_ID)
        if b is not None and not b.isChecked():
            b.setChecked(True)
        spec = w.coat_spec
        colors = (spec.secondary, spec.main) if spec.swap else (spec.main, spec.secondary)
        if colors != self._custom_colors:
            self._custom_colors = colors
            self.custom_swatch.setIcon(two_tone_icon(*colors, Avatar.ICON))

    def _sync_posture_row(self, w) -> None:
        """动作行、鼠标跟随那一行：灵动交互开着就藏起来（表盘也收）；高亮永远是用户选的；睡着只剩「醒来」。
        鼠标跟随：灵动交互里狗本来就看鼠标（鼠标停着一阵就不看，window._look_target），开关管不着，就不摆出来；关掉灵动交互再长出来，按它记着的开关。"""
        show_posture = not w.dynamic_setting
        moved = False
        if self.posture_collapse.is_open != show_posture:
            if not show_posture and self.side_open:
                self.close_side(animated=False)                  # 姿势行藏起来，从它长出来的表盘也收
                self.actions_toggle.setChecked(False)
            self.posture_collapse.set_open(show_posture)          # 关掉灵动交互：动作行从上面长出来，下面的行跟着往下滑
            moved = True
        if self.follow_collapse.is_open != show_posture:
            self.follow_collapse.set_open(show_posture)
            moved = True
        if moved:
            self._refit(True)
        for pid, b in self.posture_buttons.items():
            if b.isChecked() != (pid == w.rest_posture):
                b.setChecked(pid == w.rest_posture)
        state = w.dog.sleep_state()
        asleep = state != "awake"
        self.wake_button.setEnabled(state == "asleep")            # 入睡 / 醒来的动画放完才能点
        if asleep != self._asleep_shown:
            self._asleep_shown = asleep
            if asleep and self.side_open:
                self.close_side(animated=False)                  # 睡着了表盘也收
                self.actions_toggle.setChecked(False)
            pills = list(self.posture_buttons.values()) + [self.actions_toggle]
            first = pills[0]
            sec = self.posture_section
            area = QRect(first.mapTo(sec, QPoint(0, 0)).x() - 2, 0, sec.width(), sec.height())   # 四个胶囊到行尾那一块（「动作」两个字不动）

            def change() -> None:
                for b in pills:
                    b.setVisible(not asleep)
                self.wake_button.setVisible(asleep)

            self.crossfade(sec, area, change, [self.wake_button] if asleep else pills)   # 四个胶囊和「醒来」：旧的淡出、新的淡入
            self.fit_height()


class _VolumeRow(QWidget):
    """高级设置里的一条音量（「媒体音效」「界面音效」，开关换成 10 档的滑块 + 右边一颗静音）。照苹果的逻辑：拖大就大、拖小就小；
    静音把实际音量变 0、记着原来那一档（比如 7），取消静音回到 7；拖到 0 也算静音（记着这次拖之前那一档）；静音时一拖就取消静音。
    静音键就是一个开关：两条一样，静音前「关」一声、取消后「开」一声，多响按这一条自己的音量（媒体那条不再叫）。
    调的时候放一声听现在多响：
    - 界面音效：每变一档放一声开关声（调大「开」、调小「关」），两声之间至少 UI_FEEDBACK_GAP，太快的合并成一声（最后那个方向），不连成一串；
    - 媒体音效：拖着时最多每 MEDIA_FEEDBACK_GAP 叫一声，松手按最后那一档再叫一声（刚按这一档叫过就不重复）；叫的是现在这只模型包里叫声的第一段（真录音）。"""

    def __init__(self, card: "SettingsPanel", title: str, hint: str, media: bool):
        super().__init__()
        self.card, self.window, self.media = card, card.window, media
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.title = QLabel(title)
        lay.addWidget(self.title)
        card.tip_for(self.title, hint)
        lay.addSpacing(8)
        self.slider = StepSlider(sounds.STEPS, card.theme.accent)
        self.slider.setAccessibleName(title)
        self.slider.valueChanged.connect(self._dragged)
        self.slider.adjustmentStarted.connect(self._started)
        self.slider.adjustmentFinished.connect(self._finished)
        lay.addWidget(self.slider, 1, Qt.AlignVCenter)
        lay.addSpacing(4)
        self.mute = MuteButton()
        self.mute.setAccessibleName(tr("Mute"))
        card.tip_for(self.mute, tr("Mute"))
        self.mute.clicked.connect(lambda _=False: self._toggle_mute())
        lay.addWidget(self.mute, 0, Qt.AlignVCenter)
        self._start_level = 10                     # 这次拖之前记着的那一档（拖到 0 = 静音，记着它）
        self._last_ui = -1e9                       # 上一声开关声什么时候放的
        self._ui_pending: Optional[str] = None     # 太快了还没放的那一声（"switch-on" / "switch-off"）
        self._ui_timer = QTimer(self)
        self._ui_timer.setSingleShot(True)
        self._ui_timer.timeout.connect(self._flush_ui)
        self._bark_at, self._bark_level = -1e9, -1  # 上一声叫是什么时候、按哪一档叫的
        level, muted = self._state()
        self.sync(level, muted)

    @staticmethod
    def align(*rows: "_VolumeRow") -> None:
        """几条音量的字一样宽：滑块从同一个地方开始。"""
        w = max(r.title.sizeHint().width() for r in rows)
        for r in rows:
            r.title.setFixedWidth(w)

    # ---- 状态（窗口记着：档位 1..10 + 静音）
    def _state(self) -> tuple[int, bool]:
        w = self.window
        return (w.media_volume, w.media_muted) if self.media else (w.interface_volume, w.interface_muted)

    def _set(self, level: int, muted: bool) -> None:
        (self.window.set_media_volume if self.media else self.window.set_interface_volume)(level, muted)
        self._show(level, muted)

    def _show(self, level: int, muted: bool) -> None:
        shown = 0 if muted else level
        if not self.slider.adjusting:
            self.slider.set_value(float(shown))
        self.mute.set_state(shown / sounds.STEPS, muted)

    def sync(self, level: int, muted: bool) -> None:
        """卡片每 0.3 秒对一次（拖着的时候不动手底下的滑块）。"""
        self._show(level, muted)

    # ---- 拖、点
    def _started(self) -> None:
        level, muted = self._state()
        self._start_level = level

    def _dragged(self, value: float) -> None:
        level, muted = self._state()
        new = int(round(value))
        before = 0 if muted else level
        if new <= 0:
            self._set(self._start_level, True)     # 拖到 0：静音，记着拖之前那一档
        else:
            self._set(new, False)                  # 拖大拖小就是那一档；静音时一拖就取消
        self.mute.set_state(new / sounds.STEPS, new <= 0)
        if new != before:
            self._feedback(new > before)

    def _finished(self) -> None:
        level, muted = self._state()
        self._show(level, muted)
        if self.media and not muted:
            self._bark(final=True)

    def _toggle_mute(self) -> None:
        """静音键：开关的「关」「开」（媒体那条取消静音不要狗叫，两条都用开关被打开、关掉的声音，音量就是这一条设的音量）。
        静音前按现在这一档「关」一声，取消后按记着的那一档「开」一声；媒体那条的开关声按媒体音效的音量放（sounds.play_as_media）。"""
        level, muted = self._state()
        if muted:
            self._set(level, False)                # 取消静音：回到记着的那一档，再「开」一声
            if self.media:
                sounds.play_as_media("switch-on")
            else:
                self._feedback(True, force=True)
        else:
            (sounds.play_as_media if self.media else sounds.play)("switch-off")   # 静音前按现在的音量「关」一声
            self._set(level, True)

    # ---- 听现在多响
    def _feedback(self, up: bool, force: bool = False) -> None:
        if self.media:
            self._bark()
            return
        self._ui_pending = "switch-on" if up else "switch-off"
        wait = self._last_ui + UI_FEEDBACK_GAP - time.monotonic()
        if wait <= 0.0 or force:
            self._flush_ui()
        elif not self._ui_timer.isActive():
            self._ui_timer.start(max(1, round(wait * 1000)))

    def _flush_ui(self) -> None:
        if self._ui_pending is None:
            return
        kind, self._ui_pending = self._ui_pending, None
        self._last_ui = time.monotonic()
        sounds.play(kind)                          # 按刚调好的音量放（sounds 里的增益已经换了）

    def _bark_file(self):
        """现在这只模型包里「叫」的第一段：Bark 片段绑的那个声音（没有就叫 bark 的那个事件）的第一个文件。"""
        pack = self.window.pack
        bound = pack.clip_sounds.get("Bark")
        spec = pack.sounds.get(bound.sound if bound is not None else "bark") or pack.sounds.get("bark")
        return (spec.files[0], bound.sound if bound is not None else "bark") if spec is not None and spec.files else (None, "")

    def _bark(self, final: bool = False) -> None:
        level, muted = self._state()
        if muted:
            return
        now = time.monotonic()
        if final:
            if self._bark_level == level and now - self._bark_at < MEDIA_FEEDBACK_GAP:
                return                             # 刚按这一档叫过：不重复
        elif now - self._bark_at < MEDIA_FEEDBACK_GAP:
            return
        path, event = self._bark_file()
        if path is None:
            return
        sounds.stop_file(path)                     # 上一声还没叫完：先停，不叠在一起
        bank = getattr(self.window, "sound_bank", None)
        sounds.play_file(path, bank.volume(event) if bank is not None else 1.0)
        self._bark_at, self._bark_level = now, level

    def hideEvent(self, event) -> None:
        self._ui_timer.stop()
        self._ui_pending = None
        super().hideEvent(event)
