"""PySide6 窗口：无边框、透明、置顶、可拖动、可缩放。按屏幕刷新率用 GPU 画三渲二的狗。狗的模型由 app.py 加载后传进来。
这里只管：设置项（QSettings）、两个模式开关、外观（浅色 / 深色 / 跟随系统）、卡片和菜单、窗口的位置 / 高度 / 缩放、每帧推进狗。
拆出去的：鼠标 / 键盘 / 拖动 / 全局点击在 widget/input.py（mixin），「···」按钮和姿势条在 widget/hovermenu.py，毛色和强调色在 widget/look.py。

默认桌面上只有狗，没有文字（Show metadata 打开时脚下多一行给开发测试看的元数据）。
右键、点「···」：直接开设置；悬停在「···」上往下弹出关闭键（widget/hovermenu.py）。
两个模式开关：Follow cursor（头眼看鼠标）、Dynamic interaction（灵动交互），可以同时开；都关 = 狗自己待着（按姿势和随机动作过日子，不看鼠标不理点击）。
模型：狗的模型、片段名、声音、调参都从模型包来（widget/packs.py，packs/）；名字、毛色每只同桌各记一份，大小全局一份。
换到别的模型的同桌不重启：别的模型由 widget/kits.py 在后台先备好，滑到位时当场换（_use_kit：新建控制器、渲染器原地换模型，毛色、声音、调参、游乐场跟上），再走和同一个模型一样的淡入。
没调过大小的，第一次开灵动交互用这块屏的推荐大小（playground.recommended_scale）；调过的不动。
狗和卡片在所有普通桌面（Spaces）都看得见（默认、不可关，native.set_all_spaces）；Settings「小组件全局显示」开着时程序切成 accessory（没有 Dock 图标），
狗连全屏 App 上也显示；策略在建窗口前设好（窗口创建时就定了能不能进全屏空间），开关一改就重启；菜单栏骨头不在时不切，Cmd+Q 自己接。
点 Dock 图标只当场校验身份、不弹设置（on_app_state）。
灵动交互关着时小组件在所有屏合起来那块的右半边狗朝左、左半边朝右：换了半边（拖过中线、拔掉外接屏后被系统挪过去）狗就转过去，趴着坐着睡着也起来转。
随机动作是黑箱：池固定在 clips.ACTIONS 的 default，用户不能选。
缩放：触控板双指捏合、滚轮、键盘 + / -，围绕狗的浮点中心。倍数、位置、开关、毛色都记在 QSettings 里，下次启动沿用；
位置记的是在哪块屏、屏上的比例（别记绝对坐标：宽屏左半边的位置到了笔记本上落在右半边）。启动时淡入。
点击范围就是狗：窗口里透明的地方点不到，点击、滚轮、右键穿到后面的窗口（widget/input.py 的 _update_hit）。
所以窗口可以一直留够「···」和姿势条的位置（头顶留按钮的高度，缩小时宽度至少放得下姿势条），悬停时不改大小。
看细节（widget/closeup.py）：详情页、自定义毛色页开着时狗站在转台上（先站起来，朝向听转盘、姿势听那一页的站 / 坐 / 趴）；「放大」只是画得大——
scale / ppm / ground_px 是现在画多大，world_scale 是存下来的大小（设置、空间、球、大小滑杆都看它）；以狗脚下的根为中心放大，根不动、不躲卡片；
放大时窗口一开始按上限摆一次（hold_scaled）、每帧只改画多大画在哪（show_scaled，和 _park 一样只动 draw_offset）、收完再摆回去（end_scaled），
中间不挪窗口、不改大小，也不夹身子、不换屏；放大着能拖狗（拖到哪就是它真在哪）。
加宽（停够了才缩回）：灵动交互里狗一动起来，窗口铺满狗那块屏的宽、和拎着一样高（_wide_rect），
之后只长不缩、在这块屏上不挪——跑、跳、被拖、被扔、改大小都只改狗画在窗口里哪、画多大（_place_held），画的也只有狗那一块（_frame_for，离屏画布不跟着变大）；
放不下了只往那一边长（四条边都要动就分两步，_reshape）；换屏在新屏上重铺；狗停够 WIDE_REST_S、关灵动交互才回到平时贴着狗的大小（一直宽着时悬停卡得多）。
每帧挪窗口要等窗口系统（跑、扔时空档的大半）；也不挪着走一大步：Metal 上屏不跟着窗口的位置一起提交（presentsWithTransaction 是假的），
挪一大步那一两帧狗会闪到别处，长大小时旧画面钉在不动的那个角就还在原地（_pin_corner）。记位置、摆卡片按狗本身（_save_pos、dog_rect），不按窗口。"""
from __future__ import annotations

import json
import math
import os
import sys
import logging
import time
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QLocale, QPoint, QPointF, QRect, QSettings, Qt, QTimer, QVariantAnimation, QRectF
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QVBoxLayout, QWidget

import config
from widget import excite, i18n, native, overlay, packs, sounds, sticker, temper, uninstall as uninstall_service, updater
from widget.capture_ui import CaptureUI, ui_frozen
from widget.clips import POSTURE_PLANS, QUARTER_POSES
from widget.coat import CoatSpec
from widget.dogctl import DogController
from widget.gaze import Z_FRONT
from widget.geometry import column_top, frame_period, initial_position, keep_on_screens, place_relative, project, relative_position
from widget.bubble import DogBubble
from widget.ghost import GhostWindow
from widget.gltf import Model, Vec3, transform_point
from widget.dogview import DogView
from widget.hovermenu import HoverMenu, menu_scale, needed_width
from widget.i18n import tr
from widget.input import InputMixin
from widget import kits as kits_mod
from widget.kits import Kits
from widget.look import Look
from widget.playground import Playground, recommended_scale
from widget.popup import SwitchMenu
from widget.prefs import PLAY_OPTIONS, Pet, Prefs, Roster, share_size
from widget.things import BALL_KEY, page_styles
from widget.render import ELEVATION, make_frame
from widget.closeup import Closeup
from widget.tuning import LOOK_IDLE_S, Tuning
from widget.voice import ClipSounds, SoundBank
from widget.widgets import NAME_MAX, FrameClock, clip_graphemes, hide_tip, sticker_hud

log = logging.getLogger("window")

SCALE_MIN_PCT, SCALE_MAX_PCT = 30, 400   # 大小最小 30%；最大跟着狗在的那块屏（scale_range），至少到 400%
TALL_SHARE = 2.0 / 3.0  # 大小最大到狗站着约占这块屏高的这么多（推荐大小约四分之一，playground.recommended_scale）
WIDE_REST_S = 3.0      # 宽着的窗口：狗停够这么久（没人按着、没在看细节放大）才回到平时贴着狗的大小（_tick）；None = 一直宽着不缩回。
                       # 一直宽着时悬停（「···」出来）空档多 3～10 倍、待着每秒指令多两成（窗口大，Qt 每帧清、传、合成的都多），跑、扔照样少一大半
RESHAPE_SWAPS, RESHAPE_MAX_S = 2, 0.25   # 窗口四条边都要动时分两步（_reshape）：第一步画够这么多帧、最多等这么久再走第二步
SHRINK_DELAY = 1.5     # 不需要那么高之后，等这么久再把窗口缩回去（防抖）
GROW_PX_PER_SEC = 1500 # 窗口长高的速度上限（1 倍时逻辑像素 / 秒，随缩放）：一帧最多长 25 像素，追得上起跳（最快约 6 像素 / 帧），又不会一下长很多让旧画面拉伸得明显
APPEARANCES = ("light", "dark", "system")   # 界面外观（高级设置）
CAPTION_PX = 11        # 脚下小字字号（逻辑像素），随缩放等比，最小 9
FLOOR_SETTLE_MS = 300  # 程序坞出来 / 收起来（可用区域变了）：停稳这么久再重算地面（程序坞的动画约 0.25 秒）
MOVE_SETTLE_MS = 500   # 窗口被挪动后（拔屏、改分辨率、改显示器排列）停稳这么久再记位置、看换没换半边
HIDDEN_POLL_MS = 250   # 窗口整个看不见时（屏幕关了、锁屏、被完全挡住）隔多久看一眼：这期间不算也不画，省电
IDLE_AFTER_S = 0.6     # 待着时少画：没动静这么久才降档
IDLE_NEAR_PX = 120     # 鼠标离狗、球的窗口这么近就算有动静：点击范围每帧才切一次，「···」也要马上出来
BODY_HALF_M = 0.62     # 狗的身子从根往左右最多伸多远（米，任何朝向）：还有一截在这块屏上，窗口就不换屏
SHADOW_ROOM_PX = 18.0  # 灵动交互关着时脚离屏幕底边至少多远（1 倍时，跟着缩放）：影子画在这一条里，和灵动交互的地面一样
BODY_SKIN_M = 0.07     # 骨头外面还有多少皮毛（米）：算狗真实占的地方
BUBBLE_HEAD_M, BUBBLE_REACH_M = 0.13, 0.17   # 气泡的尾巴指着头骨上方多高、头左右多宽（米）
GHOST_SWAPS = 2        # 主窗口接手以后画完这么多帧才收掉另一个窗口（第一帧可能还是旧的密度）
GHOSTS_REST = True     # 安静时把用不着的每屏窗口收起来（_sync_ghost）
PET_FADE_OUT_S = 0.16  # 换同桌：狗淡出多久（滑动条滑到位约 0.3 秒，到位时已经看不见了）
PET_FADE_IN_S = 0.24   # 换好以后淡入多久
PET_FADE_WAIT_S = 0.04 # 换好以后等这么久再开始淡入：新毛色先画出两三帧，不让旧的那帧露一下
PET_FADE_GUARD_S = 1.5 # 淡出以后这么久没人叫它回来就自己淡回来
GC_HOLD_S = 1.5        # 换模型以后这么久不让自动垃圾回收跑（kits.hold_gc；贴图换上、卡片重建都挤在这一阵）
SWITCH_LATER_MS = 20   # 没备好就去换的那只：模型备好的下一帧再换（_pending_ready）
GHOST_REST_S = 3.0     # 安静这么久才收
GHOST_NEAR_M = 0.3     # 身子离别的屏不到这么远（米），那块屏上的窗口一直摆着
FLIP_HOLD_S, FLIP_HOLD_SWAPS, FLIP_HOLD_MAX_S = 0.15, 3, 0.6   # 主窗口换屏：这么久（秒）、画够这么多帧之前只画空的；一直没画够（看不见）最多再等这么久
PARK_MARGIN_M = 0.15   # 狗的身子离开主窗口那块屏再远这么多（米），主窗口才歇着
PARK_SWAPS = 2         # 歇下来之前再画这么多帧空的
BALL_MENU_GAP = 6      # 右键球的小胶囊离球多远（1 倍大小时的逻辑像素）
EDGE_SHARE = 0.25      # 所有屏合起来那块左右各这么宽算靠边：灵动交互里在这歇下来朝中间（_edge_yaw）


def _rect(g) -> tuple[int, int, int, int]:
    return g.x(), g.y(), g.width(), g.height()


class CompanionWindow(InputMixin, QWidget):
    def __init__(self, model: Model, parent=None, pack: Optional[packs.Pack] = None):
        # 不接键盘、显示时不激活：狗本身不用键盘（点、拖、滚轮、捏合都按鼠标位置送）；少了这两样，狗的窗口重新显示（fade_in）时
        # 系统让它成了 key window，你在别的 App 里正在打字的输入框就失去焦点（真机读回过：重新显示那一下 isKeyWindow、程序被激活）
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.model = model
        self.pack = pack or packs.choose_pet()
        self.setAttribute(Qt.WA_TranslucentBackground)
        native.ignore_safe_area(self)            # 内容铺满整个窗口，不躲屏幕顶上那一条（刘海）
        self.setWindowTitle(config.APP_NAME)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)              # 没按键也收 mouseMove：菜单按钮悬停
        native.apply(self)
        self.level = native.LEVEL_DOG            # 狗在窗口的哪一层（native.LEVEL_*：趴在窝里时在窝和窝沿之间，set_dog_level）

        ppm = config.PIXELS_PER_METER
        self.dog = DogController(model)
        self.view = DogView(model, parent=self, overlay=self._overlay, overlay_needed=self._overlay_needed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)

        self.settings = QSettings("Deskmate", "Companion")   # ~/Library/Preferences/com.deskmate.Companion.plist
        self.roster = Roster(self.settings, self.pack.id)          # 「我的同桌」的名单：现在是哪一只
        share_size(self.settings, self.roster.pets(), self.roster.current_id)   # 大小全局一份：旧版每只各记的，把现在这只的搬过来
        self.prefs = Prefs(self.settings, self.pack.id, self.pack.default_name, self.roster.current_id)   # 设置项的表（widget/prefs.py）：键、默认值、类型只写一处；名字、毛色每只一份
        self.ball_pack = packs.ball_pack()
        self.tuning = Tuning(self.pack, self.settings)            # 调参（连点五下版本号），每个模型一份
        self.ball_tuning = Tuning(self.ball_pack, self.settings)
        self.dog.tune = self.tuning
        self._kept_top = 0.0                                      # 上次按多高检查过身子在不在屏幕里（_tick）
        self.sound_bank = SoundBank(self.pack, self.tuning)       # 声音绑在模型上
        self.ball_bank = SoundBank(self.ball_pack, self.ball_tuning)
        self.clip_sounds = ClipSounds(self.sound_bank)
        self.kits = Kits(self.settings, self)                     # 每个模型备好的东西（widget/kits.py）：别的模型在后台先备好，换过去不重启
        self.kits.adopt(self.pack, model, self.tuning, self.sound_bank)
        self.kits.share(self.ball_tuning)                         # 每个包的调参只有一份（开发者设置页改的就是在用的）
        for option in PLAY_OPTIONS:                               # 灵动交互的子选项（hop_windows_on 窗口交互）
            setattr(self, option.attr, self.prefs.get(option.key))
        self.fetch_on = True                                      # 捡球的总闸（playground.fetch_on）：没有开关（把球放进狗那一圈才追，本来就有一层管着），一直开着；单测拿它让狗只看着
        self.ball_out = self.prefs.get("ball_out")                # 小球拿出来没有（球也是一件道具，道具栏、「物件」页、右键球都能收）
        self.tools = self._read_tools()                           # 道具栏放了哪几样（「物件」页每一格右上角的勾选圈）
        self.play_options_open = False                            # 设置卡片上那几条展开着没有：只在程序开着时记着（换外观重建卡片也在），不存盘
        self.updater = updater.Updater(cache_dir=updater.CACHE_DIR, parent=self)   # 检查更新：只有点了才联网
        self.updater.changed.connect(self._update_changed)
        self.updater.ready.connect(self._update_ready)
        self._uninstall_session = None
        self._uninstall_timer = QTimer(self)
        self._uninstall_timer.setInterval(100)
        self._uninstall_timer.timeout.connect(self._poll_uninstall)
        self.update_prompt = None                # 下载完在狗旁边弹的「下载已完成，现在安装吗」（用到才建）
        self._scale_anim = QVariantAnimation(self)
        self._scale_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._scale_anim.valueChanged.connect(lambda v: self.set_scale(float(v)))
        self._scale_anim.finished.connect(self._scale_anim_done)
        self._scale_anim_then = None
        self._prompt_wait = QTimer(self)         # 狗被挡住（全屏 App、锁屏）时先不弹，每秒看一眼
        self._prompt_wait.setInterval(1000)
        self._prompt_wait.timeout.connect(self._show_update_prompt)
        prefs = self.prefs
        cf_current, cf_langs = native.mac_languages()
        system = i18n.system_default(cf_langs)               # 第一次打开跟系统的首选语言（直接问 macOS；打包的 app 里 Qt 说是 C）
        self.language = prefs.text("language") or system
        log.info("locale qt %s %s · env %s · mac %s %s → system %s, using %s", QLocale.system().name(), QLocale.system().uiLanguages()[:2],
                 {k: v for k in ("LC_ALL", "LC_NUMERIC", "LANG", "LC_CTYPE") if (v := os.environ.get(k))}, cf_current, cf_langs[:2],
                 system, self.language)
        i18n.set_language(self.language)
        self.dog_name = clip_graphemes(prefs.get("dog_name").strip(), NAME_MAX)     # 可以是空的；没记过的才是默认的 Milo
        self.tray = None
        self.interface_volume, self.interface_muted = prefs.volume("interface")   # 界面音效：0..10 档 + 静音（静音前的那一档记着）； 以前是开关，开 = 满格
        sounds.set_volume(self.interface_volume, self.interface_muted)
        self.media_volume, self.media_muted = prefs.volume("media")               # 媒体音效（狗叫、球、落地）
        sounds.set_pack_volume(self.media_volume, self.media_muted)
        self.show_metadata = prefs.get("show_metadata")
        self.follow_cursor = prefs.get("follow_cursor")
        self.dynamic_setting = prefs.get("dynamic")          # 设置里的「灵动交互」开关（卡片上显示的、存着的）
        self._play_paused = False                            # 看细节那两页开着：临时退出灵动交互（pause_play）
        self.dynamic = self.dynamic_setting                  # 灵动交互这会儿真开着没有（狗、游乐场、「···」都看它）= 开关开着、没临时退出
        self.power_saving = prefs.get("power_saving")        # 省电模式：待着时少画帧、安静时收起用不着的每屏窗口（_pace、_sync_ghost）；默认关
        self.appearance = prefs.get("appearance")            # 界面外观：light / dark / system（狗本身不变）
        if self.appearance not in APPEARANCES:
            self.appearance = "system"
        sticker.set_dark(self._wants_dark())                # 建任何卡片之前定好贴纸颜色
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _scheme: self._apply_appearance())   # 跟随系统：系统切深浅色时跟着换
        self.rest_posture = prefs.get("rest_posture")
        if self.rest_posture not in POSTURE_PLANS:
            self.rest_posture = "lying"
        self.dog.set_dynamic(self.dynamic)
        self.dog.set_auto_turn(self.dynamic)         # 随鼠标转身只在灵动交互里，一直开着，没有开关
        self.dog.set_rest_posture(self.rest_posture)
        native.set_activation_policy(self.wants_accessory())   # 必须在任何原生窗口建出来之前定：窗口创建时就决定了能不能进全屏空间（实测运行中切无效）
        self._opacity_anim = QVariantAnimation(self)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._opacity_anim.valueChanged.connect(lambda v: self._set_dog_opacity(float(v)))
        self.dog_opacity = 1.0           # 狗现在几成浓（窗口的不透明度；换同桌时淡出淡入，fade_dog）
        self._fade_soon = QTimer(self)   # 换好了等新的画出来再淡入
        self._fade_soon.setSingleShot(True)
        self._fade_soon.timeout.connect(lambda: self._fade_to(1.0, PET_FADE_IN_S))
        self._pending_pet: Optional[str] = None   # 要换去的那只（别的模型、还没备好）：备好了再换（switch_pet、_pending_ready）
        self._room_m = 0.0                         # 窗口给狗留到多高（米）：这次运行里用过的模型、姿势里最高的，只长不缩（_needed_height）
        self._fade_guard = QTimer(self)  # 保险：淡出以后没人管（滑动条半路被打断）也自己淡回来，狗不会一直看不见
        self._fade_guard.setSingleShot(True)
        self._fade_guard.setInterval(round(PET_FADE_GUARD_S * 1000))
        self._fade_guard.timeout.connect(lambda: self.fade_dog(True))
        self.settings_panel = None       # 设置卡片 app.py 建好后 attach_panels 挂上来；先占位
        self._dirty = True               # 画面有变化，冻结时也要重画一次
        self.look = Look(self, model, self.prefs)      # 毛色、强调色（widget/look.py）
        self.look.restore()
        self._moved_timer = QTimer(self)         # 窗口被挪动后停稳了再记位置、看换没换半边（_after_move；拖动的松手时当场做）
        self._moved_timer.setSingleShot(True)
        self._moved_timer.setInterval(MOVE_SETTLE_MS)
        self._moved_timer.timeout.connect(self._after_move)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._watch_screen)
        app.screenRemoved.connect(self._screens_changed)
        for s in app.screens():
            s.geometryChanged.connect(self._screens_changed)
            s.availableGeometryChanged.connect(self._floor_changed)
        self._floor_timer = QTimer(self)             # 程序坞出来 / 收起来：等它的动画停稳再重算地面（_after_floor_change）
        self._floor_timer.setSingleShot(True)
        self._floor_timer.setInterval(FLOOR_SETTLE_MS)
        self._floor_timer.timeout.connect(self._after_floor_change)
        self.scale = self.world_scale = 1.0         # 现在画多大 / 存下来的大小：只有看细节临时放大时前者大（show_scaled）
        self.ppm, self.ground_px = float(ppm), float(config.GROUND_Y)
        self._unzoomed: Optional[tuple[float, float]] = None   # 看细节放大期间：狗不放大时的根在哪（全局坐标；dog_rect、记位置照它，放大着拖狗也改它）
        self._wide = False                         # 灵动交互：窗口铺宽了（_wide_rect；只长不缩，狗在里面跑、被拖、被扔，窗口不跟着挪，_place_held）
        self._still_since: Optional[float] = None  # 宽着时狗从什么时候起停着（_tick：停够 WIDE_REST_S 回到平时的大小）
        self._reshape_next: Optional[QRect] = None # 改窗口分两步时的第二步（_reshape）
        self._reshape_swaps, self._reshape_at = 0, 0.0
        self._pinned: Optional[tuple[bool, bool]] = None   # 窗口改大小那一帧旧画面钉在哪个角：(钉左边, 钉底边)（_pin_corner）
        self._was_busy = False                     # 上一帧狗在动（宽着时窗口不挪，停下来要自己记位置，_tick）
        self._flip_until: Optional[float] = None   # 主窗口刚换屏，还没真到位：到这个时刻之前只画空的（_update_flip）
        self._flip_swaps = 0
        self._parked = False                       # 狗的身子不在主窗口那块屏上、还在动：主窗口歇着（_park）
        self._flung = False                        # 上一帧狗被拎着或在空中（_follow_refresh）
        self._park_swaps = 0
        self.draw_offset = (0.0, 0.0)               # 窗口只能放整像素；剩下的小数由狗、阴影、操作栏共同保留
        self._pose = None                           # 最近一帧姿势：改几何时重新投影，不推进动画
        self._scale_adjusting = False
        self._anchor: Optional[tuple[float, float, float, float]] = None  # 视觉中心的屏幕坐标 + 投影坐标（米），每次调节只捕获一次
        self._anchor_rest_top: Optional[float] = None        # 非拖动的缩放：换姿势后才重新取中心，普通呼吸不触发
        self._anchor_frame_ready = False
        self._anchor_root: Optional[tuple[float, float]] = None   # 上次缩放把狗的根放到哪；狗挪了（被拖、跑了、被系统挪了）就重新取中心
        self.set_scale(prefs.get("scale"), keep_center=False)

        self._shrink_at: Optional[float] = None
        self._app_state = None       # 上一次的程序激活状态：用来认出"点了 Dock 图标"（见 on_app_state）
        self._applying_policy = False
        self._policy_timer = QTimer(self)      # Dock / Finder 重新唤起后，等系统处理完本轮事件再校验身份
        self._policy_timer.setSingleShot(True)
        self._policy_timer.timeout.connect(self.apply_policy)
        self._ball_menu: Optional[SwitchMenu] = None   # 右键球的小胶囊（「我不要小球了」）
        self._thing_menu: Optional[SwitchMenu] = None  # 右键物件的小胶囊（「我不要饭盆了」，点了 = 收起来）
        self._thing_menu_key = ""
        self._ghosts: dict[str, GhostWindow] = {}  # 每块屏一个：过屏幕交界时画另一半（widget/ghost.py）
        self._bubble: Optional[DogBubble] = None   # 狗说话的气泡（widget/bubble.py）
        self._ghost_swaps = 0                      # 主窗口换屏以后那块屏上的窗口还要画几帧才收
        self._scene_screen = None                  # 主窗口现在在哪块屏：狗停下来、身子全离开才换
        self.view.frameSubmitted.connect(self._frame_swapped)   # 窗口把这一帧交上去了
        self.hover = HoverMenu(self)             # 「···」按钮和姿势条（widget/hovermenu.py）
        self.playground = Playground(self)     # 灵动交互：球、狗跑去捡、跳窗口（widget/playground.py）；place_initially 放好窗口后才开
        self.closeup = Closeup(self)          # 看细节：转台、临时放大（widget/closeup.py）；设置卡片换页时开关，_tick 每帧推
        self._init_input()
        self._last_tick = time.perf_counter()

        self._anim_timer = QTimer(self)                  # 动画节拍：单次计时器，每帧按理想时刻重排（_frame），间隔跟屏幕刷新率（_sync_frame_rate）
        self._anim_timer.setSingleShot(True)
        self._anim_timer.setTimerType(Qt.PreciseTimer)
        self._anim_timer.timeout.connect(self._frame)
        self._rate_screen = None                         # 现在听着哪块屏的刷新率变化
        self._lively_at = time.perf_counter()            # 最后一次有动静是什么时候（_pace）
        self._feel_cursor: Optional[tuple[float, float]] = None   # 兴奋度：上一帧鼠标在哪（_pointer_near）
        self._feel_still = 0.0                           # …鼠标停着多久了
        self._feel_away = 0.0                            # …鼠标多久没在狗身边动了：够 excite.GREET_AFTER_S 再过来算打招呼
        self._paced_geo = None                           # 上一帧窗口在哪、多大：变了算有动静
        self._frame_clients: set = set()         # 跟着狗的每一帧一起动的卡片、菜单、提示（widgets.FrameClock）：全程序一个节拍，不和狗打架
        self._sync_frame_rate()
        self.dog.set_play(True)                     # home 朝向等放好窗口再定（place_initially → snap_home）
        self._tick()
        self._next_frame = time.perf_counter()
        self.capture_ui = CaptureUI(self)
        self._anim_timer.start(0)

    # ---------- 设置 ----------
    def set_language(self, lang: str) -> None:
        """换界面语言：记下来，重建两个面板和菜单栏菜单，Settings 原地重新打开。"""
        self.language = lang if lang in i18n.LANGS else "en"
        self.prefs.set("language", self.language)
        i18n.set_language(self.language)
        self._apply_width()                      # 姿势条的字变了：缩小时窗口宽度跟着变
        self.rebuild_panels()
        self._dirty = True

    def set_dog_name(self, name: str) -> None:
        self.dog_name = clip_graphemes((name or "").strip(), NAME_MAX)   # 名字可以为空、可以是任何字和表情，最多 32 个（表情算一个）
        self.prefs.set("dog_name", self.dog_name)
        if self.settings_panel is not None:
            self.settings_panel.set_title(self.dog_name)      # 胶囊标签上的名字也换
        self._dirty = True

    def rebuild_panels(self) -> None:
        """用当前语言重新生成 Settings，开着的留在原位。"""
        from widget.settings import SettingsPanel
        olds = self.panels()
        page = self.settings_panel.page if self.settings_panel is not None else "main"   # 换外观 / 换语言时留在当时那一页
        self.attach_panels(SettingsPanel(self))
        for old, new in zip(olds, self.panels()):
            if old is not None:
                if old.isVisible():
                    if new is self.settings_panel and page != "main":
                        new.show_page(page, animated=False)
                    snap = old.snapshot()         # 原地换：旧的字淡出、新的淡入（用户点了就一定有反馈；别整张先消失再淡入上浮：像闪了一下）
                    new.move(old.pos())
                    new.fit_height()              # 先量好高度再显示：显示后再改大小，macOS 会按自己的规则挪窗口，换语言时卡片一点点往上爬
                    new.show_in_place()
                    new.move(old.pos())           # 左上角钉在原处，只有底边动
                    new.fade_from(snap)
                old.hide()
                old.deleteLater()
        if self.tray is not None:
            self.tray.rebuild()

    def set_show_metadata(self, on: bool) -> None:
        self.show_metadata = bool(on)
        self.prefs.set("show_metadata", self.show_metadata)
        self._dirty = True

    def set_interface_volume(self, level: int, muted: bool = False) -> None:
        """界面音效（高级设置）：level 是记着的那一档（1..10），静音时它还记着，取消静音回到它。"""
        self.interface_volume, self.interface_muted = max(1, min(sounds.STEPS, int(level))), bool(muted)
        self.prefs.set("interface_volume", self.interface_volume)
        self.prefs.set("interface_muted", self.interface_muted)
        sounds.set_volume(self.interface_volume, self.interface_muted)

    def set_media_volume(self, level: int, muted: bool = False) -> None:
        """媒体音效（狗叫、球、落地）：同上。"""
        self.media_volume, self.media_muted = max(1, min(sounds.STEPS, int(level))), bool(muted)
        self.prefs.set("media_volume", self.media_volume)
        self.prefs.set("media_muted", self.media_muted)
        sounds.set_pack_volume(self.media_volume, self.media_muted)

    @property
    def interface_sounds(self) -> bool:
        """界面音效现在响不响（没静音）。"""
        return not self.interface_muted

    @property
    def pack_sounds(self) -> bool:
        return not self.media_muted

    def set_interface_sounds(self, on: bool) -> None:
        """开 / 关界面音效（自测脚本用）：关 = 静音，开 = 回到记着的那一档。"""
        self.set_interface_volume(self.interface_volume, not on)

    def set_pack_sounds(self, on: bool) -> None:
        self.set_media_volume(self.media_volume, not on)

    def set_power_saving(self, on: bool) -> None:
        """省电模式（高级设置：不降帧率是默认；开了才少画帧、收窗口，动作会没那么顺）。"""
        self.power_saving = bool(on)
        self.prefs.set("power_saving", self.power_saving)
        self.wake()                                      # 关掉：马上回满帧，收起来的窗口下一帧摆回去

    def set_play_option(self, key: str, on: bool) -> None:
        """灵动交互的一条子选项（prefs.PLAY_OPTIONS；设置卡片主页面灵动交互那一行点开的几条）：记下、存盘，要当场动的叫它登记的那个方法。"""
        option = next(o for o in PLAY_OPTIONS if o.key == key)
        setattr(self, option.attr, bool(on))
        self.prefs.set(key, bool(on))
        if option.changed:
            getattr(self, option.changed)()
        self._dirty = True

    def _hop_windows_changed(self) -> None:
        """「窗口交互」切了：窗口表作废重问。关的那一下狗、球正站在窗口上，照窗口没了处理（下一帧原地掉下来）。"""
        self.playground.frames_stale()

    def show_ball_menu(self, global_pos: QPoint) -> None:
        """右键球：一颗不带开关的小胶囊「我不要小球了」，点了球收起来（和「物件」页、道具栏关掉是同一个开关），胶囊跟着收。
        摆在球的旁边，不挡着球。"""
        ball = self.playground.ball
        if ball is None:
            return
        reach = ball.r + BALL_MENU_GAP * self.world_scale                   # 球按存下来的大小（看细节放大不放大球）
        self._build_ball_menu().popup_at(QPoint(round(ball.x), round(ball.y)), QRectF(ball.x - reach, ball.y - reach, 2.0 * reach, 2.0 * reach))

    def hide_ball_menu(self) -> None:
        if self._ball_menu is not None:
            self._ball_menu.hide()

    def _build_ball_menu(self) -> SwitchMenu:
        self.apply_policy()                     # 在创建原生窗口前修正身份，覆盖未收到 reopen 通知的情况
        if self._ball_menu is None:
            self._ball_menu = SwitchMenu(self)
        self._ball_menu.set_action(self.no_more_text(BALL_KEY), lambda: self.set_thing(BALL_KEY, False), menu_scale(self.world_scale))
        return self._ball_menu

    def no_more_text(self, key: str) -> str:
        """右键道具那颗胶囊的字：「我不要饭盆了」；英文 No more food bowl（名字放进句子里，头一个字母小写）。"""
        lang = i18n.current()
        style = next((t for t in self.things_available() if t.key == key), None)
        name = style.display_name(lang) if style is not None else key
        if lang == "en":
            name = name[:1].lower() + name[1:]
        return tr("No more {name}", name=name)

    # ---------- 物件（灵动交互里的狗窝、狗屋、盆，都转给 playground.things；小球也是一件，转给 playground） ----------
    def things_available(self) -> list:
        """「物件」页上列的款（packs.ThingStyle，按页上的先后）：买来的模型在的狗窝、狗屋、盆，加上小球。"""
        return self.playground.things.page()

    def thing_on(self, key: str) -> bool:
        return self.ball_out if key == BALL_KEY else self.playground.things.is_on(key)

    def things_placed(self) -> int:
        """摆着几件（拿出来的小球也算一件）。"""
        ball = 1 if self.ball_out and self.playground.things.ball_style is not None else 0
        return self.playground.things.count() + ball

    def set_thing(self, key: str, on: bool) -> None:
        """摆出来 / 收起来一款（「物件」页的格子、道具栏的开关、右键道具的「我不要……了」）；收起来位置留着。小球归 playground：set_ball_out。"""
        if key == BALL_KEY:
            self.set_ball_out(on)
        else:
            self.playground.things.set_on(key, bool(on))
        if not on and self._thing_menu is not None and self._thing_menu_key == key:
            self._thing_menu.hide()
        self._dirty = True

    def set_ball_out(self, on: bool) -> None:
        """小球拿出来 / 收起来（球也是一件道具，默认拿出来）：收起来球淡掉，狗就没球玩（没有圈、不捡球）；
        再拿出来球放在狗前面（playground._spawn_ball）。灵动交互关着只记下，开了照它来。"""
        on = bool(on)
        if on == self.ball_out:
            return
        self.ball_out = on
        self.prefs.set("ball_out", on)
        if not on:
            self.hide_ball_menu()
        self.playground.ball_out_changed()
        self._dirty = True

    def put_things_away(self) -> None:
        """全部收起（位置都留着），小球也收。"""
        self.playground.things.put_all_away()
        self.set_ball_out(False)
        self.hide_thing_menu()
        self._dirty = True

    # ---------- 道具栏（「···」旁边那一条，灵动交互开着时；hovermenu 画、input 点） ----------
    def _read_tools(self) -> list[str]:
        """设置里记的道具栏（JSON 的款钥匙列表）；没记过、读不出来 = 只有小球。"""
        try:
            raw = json.loads(self.prefs.get("tools") or "null")
        except ValueError:
            raw = None
        return [str(k) for k in raw] if isinstance(raw, list) else [BALL_KEY]

    def tool_entries(self) -> list[tuple[str, str]]:
        """道具栏上有什么：勾了的、现在能用的款，按「物件」页的先后，最多 hovermenu.TOOLS_MAX 颗；(钥匙, 名字)。最右边的「自定义」hovermenu 自己加。"""
        from widget.hovermenu import TOOLS_MAX
        lang = i18n.current()
        return [(t.key, t.display_name(lang)) for t in self.things_available() if t.key in self.tools][:TOOLS_MAX]

    def tool_pinned(self, key: str) -> bool:
        return key in self.tools

    def tools_full(self) -> bool:
        from widget.hovermenu import TOOLS_MAX
        return len(self.tool_entries()) >= TOOLS_MAX

    def set_tool_pinned(self, key: str, on: bool) -> bool:
        """放进道具栏 / 取下来（「物件」页那一格的勾选圈），存进设置。满了（TOOLS_MAX 颗）放不进去，返回 False。"""
        on = bool(on)
        if on == (key in self.tools):
            return True
        if on and self.tools_full():
            return False
        self.tools = [k for k in self.tools if k != key] + ([key] if on else [])
        self.prefs.set("tools", json.dumps(self.tools))
        self._dirty = True
        return True

    def open_things_page(self) -> None:
        """道具栏最右边的「自定义」：打开设置卡片，直接到「物件」页（那一格右上角的圈勾上 = 放进道具栏）。
        卡片没开着就先换好页再弹出来（按这一页的高度摆在狗旁边，不先出主页面再换）；开着就照常换过去。"""
        panel = self.settings_panel
        if panel is None or "things" not in panel.pages:
            return
        shown = panel.isVisible()
        panel.show_page("things", animated=shown)
        if not shown or panel.closing:
            self.open_settings()                                       # 没开着弹出来；正在淡出就淡回来
        panel.raise_()                                                 # 不激活程序（跳桌面）

    def toy_key(self) -> str:
        """玩具那一个位置现在是哪款；没选过就是红球。"""
        return self.playground.things.shelf.toy() or "ball/red"

    def show_thing_menu(self, key: str, global_pos: QPoint) -> None:
        """右键物件（触摸板两指点）、右键道具栏里摆着的那一颗（小球也走这里）：和右键球同一种小胶囊「我不要{这一款的名字}了」，
        点了 = 收起来，胶囊跟着收。摆在点的地方旁边。"""
        style = next((t for t in self.things_available() if t.key == key), None)
        if style is None:
            return
        self.apply_policy()                     # 在创建原生窗口前修正身份（和右键球一样）
        if self._thing_menu is None:
            self._thing_menu = SwitchMenu(self)
        self._thing_menu_key = key
        self._thing_menu.set_action(self.no_more_text(key), lambda key=key: self.set_thing(key, False), menu_scale(self.world_scale))
        self._thing_menu.popup_at(global_pos, QRectF(global_pos.x() - 12.0, global_pos.y() - 12.0, 24.0, 24.0))

    def hide_thing_menu(self) -> None:
        if self._thing_menu is not None:
            self._thing_menu.hide()

    # ---------- 模型 ----------
    def available_pets(self) -> list:
        """能添的模型（添加页一格一个）。"""
        return packs.pets()

    # ---------- 我的同桌：名单在 prefs.Roster，滑动条在 widget/petstrip.py ----------
    def pets(self) -> list[Pet]:
        return self.roster.pets()

    def pet_prefs(self, pet: Pet) -> Prefs:
        """这一只的那一份名字、毛色（不换过去也能读）。"""
        pack = self._pet_pack(pet)
        return self.prefs.of(pet.id, pet.pack, pack.default_name if pack is not None else "")

    def _pet_pack(self, pet: Pet) -> Optional[packs.Pack]:
        return self.pack if pet.pack == self.pack.id else next((p for p in packs.pets() if p.id == pet.pack), None)

    def pet_name(self, pet: Pet) -> str:
        return self.dog_name if pet.id == self.prefs.pet_id else clip_graphemes(self.pet_prefs(pet).get("dog_name").strip(), NAME_MAX)

    def pet_look(self, pet: Pet) -> tuple:
        """这一只长什么样（毛色编号、自定义毛色的参数、是不是侧着坐）：变了滑动条上的贴纸要重做。坐相按号定，不跟着位置换。"""
        if pet.id == self.prefs.pet_id:
            coat, custom = self.look.coat, (self.look.custom_json() if self.look.coat == 0 else "")
        else:
            prefs = self.pet_prefs(pet)
            coat = prefs.get("coat")
            custom = prefs.get("coat_custom") if coat == 0 else ""
        return coat, custom, sum(pet.id.encode()) % 2 == 0

    def pet_shots(self, pets: list, px: int, ppm: float, ground: float) -> dict:
        """滑动条上的贴纸要的图：每只一张坐着的整只（look.pet_shots）。别的模型的同桌：它的模型在后台备好了（kits）就照它自己的毛色画，
        还没备好的不在结果里（先用模型包的缩略图，备好了签名变了再画，pet_drawable）。"""
        wanted, others = [], {}
        for pet in pets:
            coat, custom, turned = self.pet_look(pet)
            if pet.pack == self.pack.id:
                wanted.append((pet.id, None if pet.id == self.prefs.pet_id else (coat, custom), turned))
            elif self.kits.ready(pet.pack):
                others.setdefault(pet.pack, []).append((pet.id, (coat, custom), turned))
        out = self.look.pet_shots(wanted, px, ppm, ground)
        for pack_id, rows in others.items():
            out.update(self.look.pet_shots(rows, px, ppm, ground, kit=self.kits.ready_kit(pack_id)))
        return out

    def pet_drawable(self, pet: Pet) -> bool:
        """滑动条上这只的贴纸能不能照它真的样子画：现在这个模型的能；别的模型的在后台备好了（kits）也能，没备好用模型包的缩略图。
        变了（换了模型、备好了）签名跟着变、重画（petstrip._signature）。"""
        return pet.pack == self.pack.id or self.kits.ready(pet.pack)

    def warm_pets(self) -> None:
        """卡片打开 0.4 秒后（开场动画走完）：名单里用到、还没备的别的模型，在后台一个一个备（kits.want），离现在这只近的先。"""
        here = self.roster.index(self.prefs.pet_id)
        packs_here = {p.id: p for p in packs.pets()}
        for pet in sorted(self.roster.pets(), key=lambda p: abs(self.roster.index(p.id) - here)):
            if pet.pack != self.pack.id and pet.pack in packs_here:
                self.kits.want(packs_here[pet.pack])

    def warm_pack(self, pack_id: str) -> None:
        """这个模型马上可能要用（滑动条要去的那只、添加页选的那一格）：还没备就在后台开始备。现在这个模型、不在了的模型什么都不做。"""
        if pack_id == self.pack.id or self.kits.ready(pack_id):
            return
        pack = next((p for p in packs.pets() if p.id == pack_id), None)
        if pack is not None:
            self.kits.want(pack)

    def pet_thumb(self, pet: Pet) -> QImage:
        pack = self._pet_pack(pet)
        return QImage(str(pack.thumb)) if pack is not None and pack.thumb is not None and pack.thumb.is_file() else QImage()

    def switch_pet(self, pet_id: str) -> None:
        """换到名单里的另一只：同一个模型的当场换名字、毛色（大小是全局的，不跟着换）；别的模型（不能重启）
        拿它备好的东西（kits：卡片打开后后台已经备好）当场换上（_use_kit），再走同一条路。还没备好不在主线程上等（界面不跟着卡）：
        记下要换去哪只（_pending_pet），狗淡出着等（fade_dog 不让它先淡回来），备好了再换（_pending_ready）。模型不在了（文件删了）的不换；
        读不出来（文件坏了、缺骨头）的也不换：留在原来那只，滑动条滑回来，只记日志（_stay）。
        狗不是一下跳成另一只：先看不见、换好了再淡入（滑动条那边在滑过去的路上就已经让它淡出了，fade_dog）。"""
        pet = self.roster.get(pet_id)
        pack = self._pet_pack(pet) if pet is not None else None
        if pet is None or pet.id == self.prefs.pet_id or pack is None:
            self._pending_pet = None
            return
        kit = None
        if pet.pack != self.pack.id:
            kit = self.kits.ready_kit(pack.id)
            if kit is None:
                if self.kits.failed(pack.id):
                    self._pending_pet = None
                    self._stay(pet)
                    return
                self._pending_pet = pet.id
                self.kits.when_ready(pack, lambda _kit, pid=pet.id: self._pending_ready(pid))
                return
        self._pending_pet = None
        self.roster.select(pet.id)
        if kit is not None:
            self.settings.sync()                     # 现在是哪只、哪个模型马上落盘（下次启动按它载入）
        self._enter_pet(pet, kit)

    def _pending_ready(self, pet_id: str) -> None:
        """没备好就去换的那只，它的模型备好了（或读不出来）：还要换就换（switch_pet 再走一遍：备好了当场换，读不出来留在原来那只）——
        放到下一帧（SWITCH_LATER_MS）：备好的这一帧主线程已经在建调参、预载声音（kits._land，6～10 毫秒），挤在一起那一帧 25 毫秒。
        等的时候又去了别处、回到了现在这只（cancel_switch）的不换。"""
        if self._pending_pet != pet_id:
            return

        def go() -> None:
            if self._pending_pet == pet_id:
                self._pending_pet = None
                self.switch_pet(pet_id)
        QTimer.singleShot(SWITCH_LATER_MS, go)

    def cancel_switch(self) -> None:
        """滑动条回到现在这只、停在「+」上（petstrip._commit）：没备好还在等的那次换不换了。"""
        self._pending_pet = None

    def _stay(self, pet: Pet) -> None:
        """要去的那只的模型读不出来：留在原来那只——名单、名字不变，滑动条滑回现在这只，狗淡回来；什么都不弹，只记日志。"""
        log.warning("deskmate %s (%s) can't be loaded, staying with %s", pet.id, pet.pack, self.prefs.pet_id)
        if self.settings_panel is not None:
            self.settings_panel.pet_changed()
            strip = self.settings_panel.strip
            strip.go(strip.current_index())          # 它正滑在半路（到位前就来换了）：名单没变它不会自己回头，明着叫它滑回来
        self.fade_dog(True)

    def _enter_pet(self, pet: Pet, kit=None) -> None:
        """换成这一只（名单已经记好）。kit：别的模型那只备好的东西（kits.Kit），同一个模型是 None。"""
        self.fade_dog(False, 0.0)                    # 还看得见的（添了、删了一只）当场收起：换毛色那几十毫秒不让人看见半截
        self.closeup.finish()                       # 看不见了再收：转台、临时放大当场还原（详情页里删了这只，狗还在转回去、缩回去的路上）；用的是旧狗，所以在换之前
        if kit is not None:
            kits_mod.hold_gc()                       # 换模型那 1.5 秒里不让全量回收跑（一次 20～30 毫秒，拿着 GIL）
            QTimer.singleShot(round(GC_HOLD_S * 1000), kits_mod.release_gc)
            try:
                self._use_kit(kit)
            except Exception:                        # noqa: BLE001 —— 换到一半出了没想到的错：退回重启（名单已经存好，起来就是新那只）
                log.exception("switching to %s failed, restarting", kit.pack.id)
                self.restart()
                return
            self.prefs.pack_id, self.prefs.default_name = kit.pack.id, kit.pack.default_name   # 名字、毛色存在哪个键要看模型（prefs.pet_key）
        self.prefs.pet_id = pet.id
        self.dog_name = clip_graphemes(self.prefs.get("dog_name").strip(), NAME_MAX)
        self.look.reload(self._coat_on)              # 贴图在后台线程出（2048 的解码、自定义现算在主线程上会卡住滑动条）
        if self.settings_panel is not None:
            self.settings_panel.pet_changed()        # 名单、名字、开关当场跟上（滑动条要按新名单走、添的那只要冒出来）；现在这只的贴纸等贴图换上再画
        self._dirty = True

    def _use_kit(self, kit) -> None:
        """换成别的模型的那只（换模型不重启；狗这时看不见）：同一个窗口、同一套渲染器，只换引用——新建一只控制器，渲染器原地换模型
        （DogRenderer.set_model），毛色、声音、调参、游乐场跟上；这一帧就按新狗排好（_commit 在卡片那一拍里叫，这一帧的画面已经按旧狗排好了，
        不重排的话下一次上屏是「新身子 + 旧骨头」）。主线程约 3 毫秒：模型和按模型量的表由 kits 在后台备好。
        新狗：灵动交互开着站在旧狗那条线上（playground.pet_arrived），关着直接是选的姿势（settle_into，不先站着再趴下）；朝向和启动时一样（snap_home）。"""
        self._drag = self._drag_target = None        # 正拖着狗：这次拖动作废（松手不算扔）
        self._dragged = self._sliding = False
        self.playground.pet_leaving()                # 旧狗手上的事收掉（灵动交互开着时）
        self.clip_sounds.reset()                     # 吃的那段长声音停掉
        self.model, self.pack, self.tuning, self.sound_bank = kit.model, kit.pack, kit.tuning, kit.bank
        self.clip_sounds = ClipSounds(self.sound_bank)
        dog = DogController(kit.model)               # 从这个模块里的名字建（单测给它打了补丁）
        dog.tune = self.tuning
        dog.set_dynamic(self.dynamic)
        dog.set_auto_turn(self.dynamic)
        dog.set_rest_posture(self.rest_posture)
        dog.set_play(True)
        dog.settle_into("standing" if self.dynamic or self.closeup.holding else self.rest_posture)
        if self.closeup.holding:
            dog.set_turntable(True)                  # 保险：还站在转台上（看细节那两页开着）就让新狗也上去，站着
        self.dog = dog
        dog.snap_home(self._home_yaw())
        self.view.set_model(kit.model)
        for ghost in self._ghosts.values():          # 每块屏的窗口：同样原地换；它手上那一帧还是旧骨头，先画空的，下一帧 _sync_ghost 照常给新的
            ghost.view.set_model(kit.model)
            ghost.view.renderer.set_coat(None)       # 上一个模型的贴图不留在新身子上（look._wear 换上这只的；第一套没在画的等它第一次画时自己解）
            ghost.clear()
        self.look.use_model(kit.model)
        self.playground.pet_arrived()
        self._anchor = None                          # 调大小的固定点、头顶检查过的高度、「···」钉的高度都是按旧狗记的
        self._kept_top = 0.0
        self.hover.top_m = self.hover.room_m = None
        dog.update(0.0)
        self._pose = dog.frame()
        self._refresh_frame()
        log.info("model %s: %d clips, %d joints", kit.pack.id, len(kit.model.clips), len(kit.model.skin_joints))

    def _coat_on(self) -> None:
        """换同桌的贴图换上了（look.reload 的 then）：现在这只的贴纸照身上这张画（换了模型的话卡片里过期的那几页接着重建），狗淡入。"""
        if self.settings_panel is not None:
            self.settings_panel.coat_landed()
        self._dirty = True
        self.fade_dog(True, delay=PET_FADE_WAIT_S)

    def coat_pending(self) -> bool:
        """换同桌的贴图还在后台出（显卡上还是上一只的）：滑动条先别画现在这只的贴纸。"""
        return self.look.pending()

    def add_pet(self, pack_id: str, name: str, then: Optional[Callable[[str], None]] = None) -> Optional[str]:
        """添一只、起好名字，马上换过去，再 then(新那只的号)（卡片让它从桌沿后面冒出来）；当场添好了也返回号。别的模型要它备好的东西：
        还没备好不在主线程上等，备好了再添（kits.when_ready），这时返回 None；读不出来就不添（只记日志）。"""
        pack = next((p for p in packs.pets() if p.id == pack_id), None)
        if pack is None:
            return None
        if pack.id != self.pack.id and self.kits.ready_kit(pack.id) is None:
            if self.kits.failed(pack.id):
                log.warning("pack %s can't be loaded, not adding", pack.id)
                return None

            def ready(kit) -> None:
                if kit is None:
                    log.warning("pack %s can't be loaded, not adding", pack.id)
                else:
                    QTimer.singleShot(SWITCH_LATER_MS, lambda: self.add_pet(pack_id, name, then))   # 下一帧再添（同 _pending_ready）
            self.kits.when_ready(pack, ready)
            return None
        pet = self.roster.add(pack.id)
        self.prefs.of(pet.id, pack.id).set("dog_name", clip_graphemes((name or "").strip(), NAME_MAX))
        self.switch_pet(pet.id)
        if then is not None:
            then(pet.id)
        return pet.id

    def remove_pet(self, pet_id: str) -> None:
        """删一只（详情页里长按「删除」）；最后一只删不了。删的是现在这只就换到旁边那只（先右后左）；旁边那只的模型读不出来就往外找一只读得出来的，
        都读不出来就不删。名单里再没有哪只用的模型丢掉它备好的东西（kits）。"""
        was_current = pet_id == self.prefs.pet_id
        target, kit = None, None
        if was_current:
            found = self._loadable_neighbour(pet_id)
            if found is None:
                log.warning("no other deskmate can be loaded, %s stays", pet_id)
                return
            target, kit = found
        if not self.roster.remove(pet_id):
            return
        if target is not None:
            self.roster.select(target.id)
            if kit is not None:
                self.settings.sync()
            self._enter_pet(target, kit)
        elif self.settings_panel is not None:
            self.settings_panel.pet_changed()
        self.kits.keep({p.pack for p in self.roster.pets()} | {self.pack.id})

    def _loadable_neighbour(self, pet_id: str) -> Optional[tuple]:
        """删掉 pet_id 以后换到哪只：(那只, 它的模型备好的东西；同一个模型是 None)。先右后左、由近及远，跳过模型不在、读不出来的。"""
        pets = self.roster.pets()
        i = next((k for k, p in enumerate(pets) if p.id == pet_id), None)
        if i is None:
            return None
        order = [pets[k] for d in range(1, len(pets)) for k in (i + d, i - d) if 0 <= k < len(pets)]
        for pet in order:
            pack = self._pet_pack(pet)
            if pack is None:
                continue
            if pet.pack == self.pack.id:
                return pet, None
            kit = self.kits.get(pack)
            if kit is not None:
                return pet, kit
        return None

    def tuning_targets(self) -> list:
        """开发者设置页顶上能选的，两行（名字，调参）：所有的狗（模型文件在的：边牧、萨摩耶都能调，不只是现在这只），
        小球和「物件」页能摆的那几类（狗窝、狗屋、饭盆、水盆）。每个包的调参只有一份（kits.tuning）：现在这只的就是在用的那份，改了马上生效，
        别的狗换过去就是调过的数；物件下一次扔、落就用调过的数（things.Thing.phys）。"""
        lang = i18n.current()
        found = packs.discover()
        pets = [(p.display_name(lang), self.kits.tuning(p)) for p in packs.pets(found)]
        if not any(t is self.tuning for _, t in pets):
            pets.insert(0, (self.pack.display_name(lang), self.tuning))   # 内置的那只（模型包都不在时）
        props, seen = [(self.ball_pack.display_name(lang), self.ball_tuning)], set()
        for style in page_styles():
            pack = found.get(style.pack)
            if style.key == BALL_KEY or pack is None or pack.id in seen:
                continue
            seen.add(pack.id)
            props.append((pack.display_name(lang), self.kits.tuning(pack)))
        return [pets, props]

    def tuning_of(self, pack) -> Tuning:
        """这个包的调参（那一份，kits.tuning）：物件摆出来时拿它（things.Things._spawn）。"""
        return self.kits.tuning(pack)

    def showEvent(self, event) -> None:
        native.set_all_spaces(self, True)        # 所有普通桌面上都看得见（默认，不可关）
        native.set_no_activate(self)             # 点狗不把程序切到前台
        native.set_level(self, self.level)       # 菜单栏上面、物件前面；前后由窗口的层级管（native.LEVEL_*）
        self._pinned = (True, True) if native.pin_contents_to_bottom(self) else None   # 长高那一帧旧画面钉在底边，不拉伸（原地跳切捡回时狗突然纵向拉长）；只往左、往下长时换角（_pin_corner）
        self._accepting = None                   # 原生窗口可能重建过：接不接鼠标下一帧重新告诉系统（点击范围就是狗）
        handle = self.windowHandle()
        if handle is not None and handle is not getattr(self, "_screen_hooked", None):
            handle.screenChanged.connect(self._screen_switched)
            self._screen_hooked = handle
        super().showEvent(event)
        if self._anim_timer.isActive():
            self._anim_timer.start(0)            # 显示出来马上接着动（看不见的时候 0.25 秒才看一眼）

    def _screen_switched(self, screen) -> None:
        """窗口换到另一块屏（狗在两块屏之间跳的时候闪一下）：两块屏像素密度不一样时画布要按新密度重建，
        这一帧马上按新屏重画，不等下一拍、不留空帧。"""
        self._refresh_frame()
        self.view.repaint()

    def wants_accessory(self) -> bool:
        """什么时候真的切 accessory（没有 Dock 图标；macOS 只让这种程序的窗口盖在别的 App 的全屏空间上，窗口建出来时就定了）：
        菜单栏骨头确实在就切（没有骨头就留 Dock 图标当退路）。
        全屏 App 上也有狗、程序坞里没有图标。"""
        return self.tray.isVisible() if self.tray is not None else QSystemTrayIcon.isSystemTrayAvailable()   # 启动时骨头还没建，先看系统有没有菜单栏

    def apply_policy(self) -> bool:
        """保持应用身份（accessory，见 wants_accessory）；固定在 Dock 的图标即使在 accessory 模式下也能再次唤起。
        再次点 Dock 后系统可能把身份变回 regular，新建的省略号菜单就进不了全屏空间。
        只在身份确实不符时切换，并读回确认；恢复 accessory 后丢掉旧菜单，让它在正确身份下重建。
        """
        if self._applying_policy:
            return False
        accessory = self.wants_accessory()
        wanted = native.POLICY_ACCESSORY if accessory else native.POLICY_REGULAR
        before = native.activation_policy()
        if before is None or before == wanted:   # 非 cocoa 平台不做事；相符时不反复切换、避免跳桌面
            return True
        self._applying_policy = True
        try:
            native.set_activation_policy(accessory)
            after = native.activation_policy()
            if after != wanted:
                log.warning("activation policy restore failed: wanted %s, got %s", wanted, after)
                return False
            log.info("activation policy restored: %s -> %s", before, after)
            if accessory:
                self._discard_menu()
            return True
        finally:
            self._applying_policy = False

    def _quit(self) -> None:
        QApplication.instance().quit()

    # ---------- 两个模式 ----------
    def _apply_modes(self, follow: bool, dynamic: bool, keep_zoom: bool = False) -> None:
        """鼠标跟随和灵动交互可以同时开。都关 = 狗自己待着（按姿势和随机动作过日子，不看鼠标、不理点击）。
        dynamic 是设置里的开关（存下来）；灵动交互这会儿真开着没有（self.dynamic）还要看有没有临时退出（pause_play）。
        keep_zoom：看细节要的放大还没开始（狗在空中时就拖了滑块），临时退出灵动交互不算换模式，别把它清掉。"""
        if not keep_zoom:
            self.closeup.drop_zoom()                # 看细节还在缩回去的路上：当场收完（下面要从窗口读狗的根、要夹身子）
        self.follow_cursor, self.dynamic_setting = bool(follow), bool(dynamic)
        for key, value in (("follow_cursor", self.follow_cursor), ("dynamic", self.dynamic_setting)):
            self.prefs.set(key, value)
        self.dynamic = self.dynamic_setting and not self._play_paused
        if not self.follow_cursor:
            self.dog.set_look_target(None)
        self._mouse_was_down, self._global_press = None, None
        playground = getattr(self, "playground", None)
        if playground is not None and playground.active and not self.dynamic:
            playground.stop()                                       # 先收掉球、狗停下（交回控制器），再让它回到选的姿势
        self.dog.set_dynamic(self.dynamic)
        self.dog.set_auto_turn(self.dynamic)
        if not self.dynamic:
            self._leave_wide()                                      # 关了灵动交互：窗口回到贴着狗的大小（身子出了屏幕的这一下就夹回来）
        if self.isVisible():
            self._keep_body_on_screen()
        if playground is not None and self.dynamic and not playground.active and self.isVisible():
            playground.start()
            self._apply_first_size(self.screen(), animated=True)
        if self.dynamic and self.settings_panel is not None and self.settings_panel.side_open:
            self.settings_panel.toggle_actions(animated=False)      # 姿势行藏起来了，从它长出来的动作叶也收
        self._dirty = True

    def set_follow_cursor(self, on: bool) -> None:
        """鼠标跟随：头和眼睛远远地看着鼠标；和灵动交互可以同时开。"""
        self._apply_modes(on, self.dynamic_setting)

    def set_dynamic(self, on: bool) -> None:
        """灵动交互；和鼠标跟随可以同时开；开着狗只站着，姿势行藏起来。"""
        self._apply_modes(self.follow_cursor, on)

    @property
    def play_paused(self) -> bool:
        return self._play_paused

    def pause_play(self, on: bool) -> None:
        """看细节那两页（详情页、自定义毛色页：看狗、摆姿势的）开着时临时退出灵动交互：和关掉开关一样——球、圈收起来，
        物件照关灵动交互的规矩收起，狗能随便拖、上下也能拖，姿势听那一排站 / 坐 / 趴；设置里的「灵动交互」开关不变、不存。
        回来（离开那两页、狗下了转台，closeup._release）和打开开关一样：按现在的屏幕建空间，脚下没东西就落下去，球放回狗前面，物件摆回来。
        开关本来关着：只记下，什么都不动。"""
        on = bool(on)
        if on == self._play_paused:
            return
        self._play_paused = on
        if self.dynamic_setting:
            self._apply_modes(self.follow_cursor, self.dynamic_setting, keep_zoom=not self.closeup.zoomed)

    def _screens_span(self) -> tuple[float, float]:
        """所有屏合起来那块的左右两头（全局 x）：歇着朝哪按它的中线（_home_yaw）、靠边按它两头的四分之一（_edge_yaw）。"""
        rects = [s.geometry() for s in QApplication.screens()]
        if not rects:
            return 0.0, 1.0
        return float(min(r.x() for r in rects)), float(max(r.x() + r.width() for r in rects))

    def _edge_yaw(self) -> Optional[float]:
        """灵动交互里歇下来（坐下、趴下、走进平的窝）朝哪：狗在所有屏合起来那块左右各 EDGE_SHARE 宽里就朝中间
        （左边朝右 330°、右边朝左 210°）；在中间那一半返回 None，照旧（站着时身子跟鼠标转到哪就朝哪歇）。"""
        left, right = self._screens_span()
        x, edge = self.dog_root()[0], (right - left) * EDGE_SHARE
        if x < left + edge:
            return 330.0
        if x > right - edge:
            return 210.0
        return None

    def _home_yaw(self) -> float:
        """互动模式里歇着时朝哪边：小组件在所有屏合起来那块的右半边朝左（210°），左半边朝右（330°）。分界线是那块的竖直中线（_screens_span）。"""
        if self.dynamic:                                 # 灵动交互：看鼠标在哪边，不看在屏幕哪半边
            playground = getattr(self, "playground", None)   # 建窗口的时候还没有
            live = playground is not None and playground.active
            point = playground.look_point(glance=False) if live else None
            if point is None and live and not playground.watching_you:
                return QUARTER_POSES[1] if self.dog.facing_right() else QUARTER_POSES[0]   # 鼠标停着一阵了：朝哪就待着朝哪，不转回去对着鼠标
            x = point[0] if point is not None else QCursor.pos().x()   # 头看着球的时候朝球那边，不看了再按鼠标
            return 210.0 if x < self.dog_root()[0] else 330.0
        left, right = self._screens_span()
        return 210.0 if self.dog_root()[0] > (left + right) / 2.0 else 330.0   # 按狗本身（窗口可能比狗大：看细节放大着）

    # ---------- 外观 ----------
    def _wants_dark(self) -> bool:
        if self.appearance == "dark":
            return True
        if self.appearance == "light":
            return False
        hints = QGuiApplication.styleHints()
        return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark

    def set_appearance(self, mode: str) -> None:
        """高级设置「外观」：浅色 / 深色 / 跟随系统。只换界面的贴纸颜色，狗不变。"""
        if mode not in APPEARANCES:
            return
        self.appearance = mode
        self.prefs.set("appearance", mode)
        self._apply_appearance(force=True)

    def _apply_appearance(self, force: bool = False) -> None:
        """按外观设置和系统深浅色定贴纸颜色；变了就重建卡片（样式表是建卡片时生成的）和菜单。"""
        dark = self._wants_dark()
        if dark == sticker.is_dark() and not force:
            return
        sticker.set_dark(dark)
        hide_tip()                               # 提示的颜色也换了：收起来，下次悬停再出
        self._discard_menu()
        if self.settings_panel is not None:
            self.rebuild_panels()
        self._dirty = True

    # ---------- 姿势、动作 ----------
    def set_rest_posture(self, posture: str) -> None:
        if posture == "wake":                                  # 「醒来」：睡着了才有用，醒来动画放完才能继续控制
            if self.dog.sleep_state() != "asleep":
                return
            posture = "standing" if self.dog.sleep_style == "side" else "lying"   # 侧睡的醒来片段本来就是起身，趴睡醒来还是趴着
        if posture in POSTURE_PLANS:
            self.rest_posture = posture
            self.prefs.set("rest_posture", posture)
            self.dog.set_rest_posture(posture)
            self._dirty = True

    def do_action(self, action_id: str) -> None:
        """表盘点了一个：狗做一次再回原姿势（dogctl.do_action）。"""
        self.dog.do_action(action_id)
        self._dirty = True

    # ---------- 毛色（widget/look.py）：卡片、毛色页、表盘都从这里调 ----------
    @property
    def coat(self) -> int:
        return self.look.coat

    @property
    def coat_spec(self) -> CoatSpec:
        return self.look.coat_spec

    def coat_names(self) -> tuple[str, ...]:
        return self.look.coat_names()

    def coat_available(self) -> list[bool]:
        return self.look.coat_available()

    def coat_swatches(self) -> list:
        return self.look.coat_swatches()

    def known_swatches(self) -> list:
        return self.look.known_swatches()

    def coat_label(self, i: int) -> str:
        return self.look.coat_label(i)

    def pattern_note(self, i: int) -> str:
        return self.look.pattern_note(i)

    def coat_thumbnails(self, width: int, height: int) -> dict[int, QImage]:
        return self.look.coat_thumbnails(width, height)

    def coat_faces(self, width: int, height: int, deliver, done):
        """四套毛色的头像，一帧一张（look.coat_faces）；返回取消的函数。"""
        return self.look.coat_faces(width, height, deliver, done)

    def set_coat(self, i: int) -> None:
        self.look.set_coat(i)

    def coat_custom_json(self) -> str:
        return self.look.custom_json()

    def set_custom_coat(self, spec: CoatSpec, preview: bool = False) -> None:
        self.look.set_custom_coat(spec, preview)

    def accent_color(self) -> str:
        return self.look.accent_color()

    def pattern_thumbnails(self, width: int, height: int) -> dict[int, QImage]:
        return self.look.pattern_thumbnails(width, height)

    def coat_mode(self) -> str:
        """自定义毛色怎么分（look.coat_mode）："pattern" 深浅两色（边牧）/ "tint" 整身一个色 + 可选背上一片（萨摩耶）。"""
        return self.look.coat_mode()

    def custom_pattern_slots(self) -> list:
        return self.look.custom_pattern_slots()

    def common_colors(self) -> tuple:
        return self.look.common_colors()

    def default_coat_spec(self) -> CoatSpec:
        return self.look.default_spec()

    @property
    def custom_coat_on(self) -> bool:
        """这只同桌能不能自定义毛色：模型包说能（pack.json 的 custom_coat）、模型里嵌着贴图。不能的设置卡片不出「自定义」、自定义毛色页打不开。"""
        return self.pack.custom_coat and bool(self.model.texture_png)

    def open_coat(self) -> None:
        """打开自定义毛色页（设置卡片的第三页）：狗本身就是预览，所以一打开就换成自定义贴图。"""
        if not self.custom_coat_on:
            return
        if self.coat != 0:
            self.set_custom_coat(self.coat_spec, preview=False)
        if self.settings_panel is None:
            return
        if not self.settings_panel.isVisible():
            self.open_settings()
        self.settings_panel.show_page("coat", animated=self.settings_panel.isVisible())
        self.settings_panel.raise_()                                   # 不激活程序（跳桌面）

    # ---------- 面板 ----------
    def attach_panels(self, settings_panel) -> None:
        self.settings_panel = settings_panel
        settings_panel.frame_host = self         # 卡片的动画跟着狗的每一帧走（Card.animate）
        FrameClock.default_host = self           # 菜单、悬浮提示这些小窗口的弹出也跟着狗的每一帧走
        self.look.apply_accent()                 # 开关建的时候没拿到强调色：挂上就套一次（不套的话，切深色后要点一下毛色，开关才变米白）

    def can_drive_frames(self) -> bool:
        """狗的节拍在走（窗口看得见、没被挡住）：卡片的动画可以挂上来。"""
        return self.isVisible() and self._anim_timer.isActive() and not native.window_occluded(self)

    def request_frames(self, card) -> None:
        self._frame_clients.add(card)
        self.wake()

    def release_frames(self, card) -> None:
        """卡片删掉了（换语言 / 外观时整张重建）：不再推它。"""
        self._frame_clients.discard(card)

    def panels(self) -> tuple:
        return (self.settings_panel,)

    # ---------- 更新 / 卸载（widget/updater.py） ----------
    def _update_changed(self) -> None:
        if self.settings_panel is not None:
            self.settings_panel.sync_update()

    def _update_ready(self) -> None:
        """下载完了：在狗旁边弹「下载已完成，现在安装吗」。不抢键盘、不激活程序（不切桌面）、没声音；狗看不见时等它露出来再弹。"""
        self._prompt_wait.start()
        self._show_update_prompt()

    def _show_update_prompt(self) -> None:
        if self.updater.state != "downloaded" or self.updater.release is None:
            self._prompt_wait.stop()
            return
        if ui_frozen() or not self.isVisible() or native.window_occluded(self):
            return                         # 截图或狗看不见：已有1秒轮询继续等，不新建/弹出卡片
        self._prompt_wait.stop()
        if self.update_prompt is None:
            from widget.settings import UpdatePrompt
            self.update_prompt = UpdatePrompt(self)
            self.update_prompt.frame_host = self
        self.update_prompt.fill(self.updater.release)
        if not self.update_prompt.isVisible():
            self.update_prompt.place_near(self)
            self.update_prompt.show()
            self.update_prompt.raise_()
        self._update_changed()

    def dismiss_update_prompt(self) -> None:
        """提示卡点了取消：收起来，设置卡片顶部栏出现「新版本已下载完成」胶囊。"""
        if self.update_prompt is not None:
            self.update_prompt.hide()
        self._update_changed()

    def install_update(self) -> None:
        """长按「安装」：打开下载好的 DMG（和第一次安装一样拖进 Applications 替换旧的），提示一下就退出，用户换好再打开（设置在 app 外面，全都留着）。"""
        if self.updater.install() is None:
            return
        for card in self.panels() + (self.update_prompt,):
            if card is not None:
                card.hide()
        sticker_hud().show_text(tr("Drag to Applications to replace the old one") + "\n" + tr("then open the widget again"), self.screen())
        QTimer.singleShot(3000, self._quit)

    def uninstall(self) -> None:
        """Prepare the independent helper; retain the app and data until it is ready."""
        if self._uninstall_session is not None:
            return
        try:
            self._uninstall_session = uninstall_service.start(updater.bundle_path(), self.language)
        except uninstall_service.UninstallError as exc:
            self._uninstall_failed(exc.code)
            return
        if self.settings_panel is not None:
            self.settings_panel.delete_button.setEnabled(False)
        self._uninstall_timer.start()
        self._poll_uninstall()

    def _poll_uninstall(self) -> None:
        session = self._uninstall_session
        if session is None:
            self._uninstall_timer.stop()
            return
        status = session.poll()
        if status.get("state") == "ready":
            try:
                # Commit first: a failed handshake must leave the running widget intact.
                session.commit()
            except (uninstall_service.UninstallError, OSError) as exc:
                self._uninstall_failed(getattr(exc, "code", "The uninstall helper could not start"))
                return
            self._uninstall_timer.stop()
            self.settings.sync()
            for card in self.panels() + (self.update_prompt,):
                if card is not None:
                    card.hide()
            self._quit()
        elif status.get("state") in ("error", "cancelled"):
            self._uninstall_failed(status.get("message") or status.get("code", "Uninstall cancelled"))

    def _uninstall_failed(self, code: str) -> None:
        self.cancel_uninstall()
        sticker_hud().show_text(tr(code), self.screen())

    def cancel_uninstall(self) -> None:
        self._uninstall_timer.stop()
        if self._uninstall_session is not None:
            self._uninstall_session.cancel()
            self._uninstall_session = None
        if self.settings_panel is not None:
            self.settings_panel.delete_button.setEnabled(True)

    def watch_app_state(self, app) -> None:
        """app.py 调：从现在的激活状态开始，跟着 applicationStateChanged 走。"""
        self._app_state = app.applicationState()
        app.applicationStateChanged.connect(self.on_app_state)

    def on_app_state(self, state) -> None:
        """程序激活状态变了：每次激活都等本轮事件处理完再校验身份（_policy_timer）。点 Dock 图标（或在访达里再打开一次）时，系统先正常激活程序，
        紧接着再补一次"重新打开"，Qt 把后面这次也报成 Active：已经是 Active 又来一次 Active，才是点了 Dock 图标，当场校验（on_dock_reopen）。
        切换桌面、⌘Tab、点自己的窗口都只有一次。"""
        previous = self._app_state
        self._app_state = state
        if self._applying_policy:                # 切身份本身也可能触发激活通知，不把它当成又点了一次 Dock
            return
        if state == Qt.ApplicationActive:
            self._policy_timer.start(0)
            if previous == Qt.ApplicationActive:
                self.on_dock_reopen()

    def on_dock_reopen(self) -> None:
        """点了 Dock / Finder 里的图标（固定图标在 accessory 模式下也在）：当场恢复身份，不弹设置（设置从菜单栏骨头、右键、点「···」进）。"""
        self.apply_policy()
        self._policy_timer.start(0)              # AppKit 处理完 reopen 后可能还会调整身份，再核对一次

    def open_settings(self) -> None:
        self.apply_policy()                     # 在创建原生窗口前修正身份，覆盖未收到 reopen 通知的情况
        if self.settings_panel is not None:
            self.settings_panel.toggle_near(self)

    def open_actions(self) -> None:
        """表盘从设置卡片上弹出来 / 收回去（Settings 动作行的 › 也是它）。"""
        if self.settings_panel is not None:
            self.settings_panel.toggle_actions()

    # ---------- 菜单 ----------
    def _discard_menu(self) -> None:
        if self._ball_menu is not None:
            self._ball_menu.hide()
            self._ball_menu.deleteLater()
            self._ball_menu = None
        if self._thing_menu is not None:
            self._thing_menu.hide()
            self._thing_menu.deleteLater()
            self._thing_menu = None

    # ---------- 淡入 ----------
    def _set_dog_opacity(self, v: float) -> None:
        """狗几成浓：主窗口和每块屏上画另一半的窗口一起（球、气泡、设置卡片是别的窗口，不跟着）。"""
        self.dog_opacity = v
        self.setWindowOpacity(v)
        for ghost in self._ghosts.values():
            ghost.setWindowOpacity(v)

    def _fade_to(self, end: float, seconds: float, whole: bool = False) -> None:
        """从现在的浓淡淡到 end。seconds 是从头到尾要多久：淡到一半又折回来的只走剩下那一段的时间（whole：不折算）。"""
        anim = self._opacity_anim
        if anim.state() == QVariantAnimation.Running and float(anim.endValue()) == end:
            return                                   # 已经在往那边淡了：不重来（滑动条到位时会再叫一次）
        anim.stop()
        start = self.dog_opacity
        span = abs(end - start)
        if seconds <= 0.0 or span < 1e-3 or (native.reduce_motion() and not whole):
            self._set_dog_opacity(end)
            return
        anim.blockSignals(True)                      # 改时长时它会按旧的进度重算一遍现在的值：不能让那个值写回窗口（测试里折回来时跳了一下）
        anim.setDuration(max(1, round(seconds * 1000 * (1.0 if whole else span))))
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.blockSignals(False)
        anim.start()

    def fade_dog(self, on: bool, seconds: Optional[float] = None, delay: float = 0.0) -> None:
        """换同桌（渐隐渐显）：狗淡出（on=False）/ 淡入。seconds 是从头到尾要多久（不给 = PET_FADE_OUT_S / PET_FADE_IN_S，
        0 = 当场）；delay：等这么久再开始淡入（新毛色先画出来）。淡出以后 PET_FADE_GUARD_S 没人叫它回来就自己淡回来。窗口没显示时不管。"""
        if not self.isVisible():
            return
        if on and (self.look.pending() or self._pending_pet is not None) and self._fade_guard.isActive():
            return                                   # 换同桌的贴图还没换上、要去的那只的模型还没备好：等它（_coat_on）来淡入，不先带着上一只淡回来；保险响了照样淡回来
        if on:
            self._fade_guard.stop()
            if delay > 0.0 and self.dog_opacity < 1.0 and not native.reduce_motion():
                self._fade_soon.start(round(delay * 1000))
            elif not self._fade_soon.isActive():     # 已经约好等新毛色画出来再淡入的：不抢在它前面
                self._fade_to(1.0, PET_FADE_IN_S if seconds is None else seconds)
        else:
            self._fade_soon.stop()
            self._fade_guard.start()
            self._fade_to(0.0, PET_FADE_OUT_S if seconds is None else seconds)

    def fade_in(self, seconds: float = 0.35) -> None:
        """显示出来并从透明淡入。"""
        self._opacity_anim.stop()
        self._fade_soon.stop()
        self._fade_guard.stop()
        if not self.isVisible():
            self._set_dog_opacity(0.0)
            self.show()
        self._fade_to(1.0, seconds, whole=True)

    # ---------- 位置 ----------
    def place_initially(self) -> None:
        """上次在哪块屏、屏上什么比例的位置就放回去；那块屏不在了（拔了外接屏）按同样的比例放到主屏；没有记录按 config.DEFAULT_POS 放主屏右下。
        旧版本记的绝对坐标（pos_x / pos_bottom）读一次、照旧放，再存成比例。
        放好就定朝向：窗口还没显示，狗直接朝 home，不播转身（别先按"站着"排一个转身：左半边启动时趴下后会又站着转一下）。"""
        screens = QApplication.screens()
        if self.dynamic:
            name = self.prefs.get("pos_screen")
            self._apply_first_size(next((s for s in screens if s.name() == name), None) or QApplication.primaryScreen(), animated=False)
        size = (self.width(), self.height())
        fx, fb = self.prefs.get("pos_fx"), self.prefs.get("pos_fb")
        if fx >= 0.0 and fb >= 0.0 and screens:
            name = self.prefs.get("pos_screen")
            screen = next((s for s in screens if s.name() == name), screens[0])
            self.move(*place_relative((fx, fb), size, _rect(screen.availableGeometry())))
        else:
            x, b = self.prefs.get("pos_x"), self.prefs.get("pos_bottom")
            saved = (x, b - self.height()) if x is not None and b is not None else None   # 旧版本记的是左边和底边
            if saved is None and screens:
                self.move(*place_relative(config.DEFAULT_POS, size, _rect(QApplication.primaryScreen().availableGeometry())))
            else:
                self.move(*initial_position(saved, size, [_rect(s.availableGeometry()) for s in screens]))
            if saved is not None:
                self._save_pos()
        self.dog.snap_home(self._home_yaw())
        self._keep_body_on_screen()
        if self.dynamic and not self.playground.active:
            self.playground.start()                     # 灵动交互：放好了才知道狗站在哪（被放在半空的掉下去）、球放哪

    def _save_pos(self) -> None:
        """记位置：狗在哪块屏（主窗口那块），在屏上的比例位置——按狗本身（根的 x、脚下的底边）记，不按窗口（宽着、看细节放大着的窗口比狗大）。
        读回来（place_initially）按平时贴着狗的窗口摆，所以记的就是那个窗口的中线和底边。"""
        screen = QApplication.screenAt(self.frameGeometry().center()) or self.screen()
        if screen is None:
            return
        rx, ry = self.dog_root()
        w, h = self._window_size(self.world_scale)
        bottom = ry + config.GROUND_Y * self.world_scale
        fx, fb = relative_position((rx - w / 2.0, bottom - h), (w, h), _rect(screen.availableGeometry()))
        self.prefs.set("pos_screen", screen.name())
        self.prefs.set("pos_fx", fx)
        self.prefs.set("pos_fb", fb)

    def moveEvent(self, event) -> None:
        """窗口挪了（拖动、长高缩回、缩放、拔屏后系统挪的）：停稳了再记位置、看换没换半边。"""
        super().moveEvent(event)
        self._moved_timer.start()

    def _watch_screen(self, screen) -> None:
        """接上一块屏：它改分辨率时也要重新看左右；接上本身也可能挪窗口。"""
        screen.geometryChanged.connect(self._screens_changed)
        screen.availableGeometryChanged.connect(self._floor_changed)
        self._screens_changed()

    def _screens_changed(self, *_) -> None:
        """接上 / 拔掉显示器、改分辨率、改排列：系统可能挪窗口、中线也可能变，停稳了再看；灵动交互的空间重建。看细节的临时放大当场收掉（按旧屏幕排的）。"""
        closeup = getattr(self, "closeup", None)
        if closeup is not None:
            closeup.drop_zoom()
        self._moved_timer.start()
        playground = getattr(self, "playground", None)
        if playground is not None:
            playground.screens_changed()                 # 宽着的窗口按旧屏幕铺的：出了屏的下一次摆时在这块屏上重铺（_place_held），狗停够了缩回平时的

    def _floor_changed(self, *_) -> None:
        """一块屏的可用区域变了（程序坞出来、收起来、改了大小，屏幕本身没变）：等程序坞的动画停稳再重算地面。"""
        self._floor_timer.start()

    def _after_floor_change(self) -> None:
        playground = getattr(self, "playground", None)
        if playground is not None:
            playground.floor_changed()                   # 站在程序坞那一带的狗跳上去、球弹上去；地面降了照常掉

    def _after_move(self) -> None:
        """窗口停稳了：动画节拍换成这块屏的刷新率；记位置；换了半边狗就转过去（没换边什么都不做）。拖动中不管，松手时 input.py 当场做。
        灵动交互里狗正被牵着跑 / 跳（roam）也不管：跑完了它自己回到 home 朝向，停稳了再记。看细节放大着也不管（窗口是为放大摆的）：缩回来摆回去时再来一次。"""
        self._sync_frame_rate()
        if self.dragging or not self.isVisible() or self.playground.roam.busy or self.showing_scaled:
            return
        self._scene_screen = self.screen()               # 窗口停稳了：它现在就在这块屏（被系统挪过也算）
        self._save_pos()
        self.dog.set_home_yaw(self._home_yaw())
        self.playground.window_settled()

    # ---------- 高度、缩放 ----------
    def _window_size(self, k: float) -> tuple[int, int]:
        """缩放后的基础尺寸：宽度贴着狗（352 × 缩放），缩小到放不下「···」旁边的姿势条时取放得下的宽度（hovermenu.needed_width，
        窗口一直留够，悬停时不改大小；透明的地方点不到）；高度是只包住站着的狗的最小值，需要时 _fit_height 再临时长高。
        按倍数和语言记下来（量字宽要 0.1～0.2 毫秒；宽着时每帧要问好几次，悬停时每秒指令多一半多）。"""
        sizes = self.__dict__.setdefault("_sizes", {})
        key = (k, i18n.current())
        got = sizes.get(key)
        if got is None:
            if len(sizes) > 256:
                sizes.clear()                            # 拖大小滑杆每格一个倍数：别一直攒
            got = sizes[key] = (max(round(config.WINDOW_WIDTH * k), needed_width(k, self._tool_names(key[1]))), round(config.WINDOW_HEIGHT * k))
        return got

    def _tool_names(self, lang: str) -> list[str]:
        """道具栏里可能出现的每一样的名字（这个语言里）：留宽度时最宽的一颗也要放得下（一行放不下往下排）。按语言记着：一次运行里能列的款不变。
        建窗口时游乐场还没有，不问它，直接照包列（things.page_styles）。"""
        cache = self.__dict__.setdefault("_tool_name_cache", {})
        got = cache.get(lang)
        if got is None:
            got = cache[lang] = [t.display_name(lang) for t in page_styles()]
        return got

    def _apply_width(self) -> None:
        """换语言后姿势条长短变了：按新的宽度重算窗口（只有缩小时才会变），中线和底边不动。看细节放大着不管：缩回来摆回去时按新宽度摆（end_scaled）。
        宽着也不管：铺满屏宽的窗口本来就放得下姿势条。"""
        if self.showing_scaled or self._wide:
            return
        w = self._window_size(self.scale)[0]
        if w != self.width():
            cx = self.x() + self.scene_x
            x = round(cx - w / 2.0)
            self.draw_offset = (cx - x - w / 2.0, self.draw_offset[1])
            self._commit_scene_geometry(QRect(x, self.y(), w, self.height()))
            self._dirty = True

    def live_windows(self) -> list:
        """狗那一层的窗口：每块屏一个的另一半狗、球、捡球的圈。系统截图时照常画，不抓、不换成快照（capture_ui）。"""
        return [*self._ghosts.values(), *self.playground.live_windows()]

    def dog_rect(self) -> QRect:
        """狗占的地方（全局坐标）：贴着狗的宽度（352 × 缩放，和狗同一条中线）× 平时窗口的高。窗口缩小时可能比它宽（给姿势条留的，透明、点不到），
        宽着、看细节放大着的窗口更大；卡片按这个摆在狗旁边（Card.place_near），不按窗口。看细节放大着按不放大的狗（缩回去的路上又打开卡片：摆在狗缩回去以后的旁边）。"""
        k = self.world_scale
        w = round(config.WINDOW_WIDTH * k)
        if self._unzoomed is None and not self._wide:
            g, sx = self.frameGeometry(), self.scene_x           # 平时窗口就贴着狗：高度照窗口
            w = min(g.width(), w)
            return QRect(round(g.x() + sx - w / 2), g.y(), w, g.height())
        rx, ry = self.dog_root()
        h = self._needed_height(k, config.GROUND_Y * k)
        bottom = round(ry + config.GROUND_Y * k)
        return QRect(round(rx - w / 2), bottom - h, w, h)

    def dog_root(self) -> tuple[float, float]:
        """狗不放大时的根在哪（全局坐标）：平时就是 scene_world；看细节放大着是放大前的地方（放大着拖过就是拖到的地方）。"""
        return self._unzoomed if self._unzoomed is not None else self.scene_world()

    def scene_world(self) -> tuple[float, float]:
        """狗的根（脚踩的那条线、身子正中）在屏幕上的全局坐标（含亚像素）。"""
        return self.x() + self.scene_x, self.y() + self.scene_ground

    def place_scene(self, wx: float, wy: float, size: Optional[tuple[int, int]] = None) -> None:
        """把窗口挪到狗的根在 (wx, wy)：大小不变（size 给了就一起改成这么大），整数位置放不下的小数留在 draw_offset
        （狗、影子、操作栏一起）。灵动交互里狗跑、跳、骑窗口、被拖着时每帧调。宽着、看细节放大着窗口不跟着挪（_place_held）。
        窗口顶边出不了屏幕最上沿（真机：macOS 会把它往下推，狗站在紧贴屏幕顶的窗口上时被推下去 20 像素、掉下来）：
        顶到了就从上面截短（底边、狗都不动；头顶的「···」这时已经挪到狗旁边了）。
        窗口也不骑在两块屏中间（真机：macOS 一个窗口只画在一块屏上，骑在交界上时 0.2 秒里来回换了 5 次屏，两块屏像素密度不一样，
        每换一次画布重建一次，狗一闪一闪：拖到 LG 左边也是这样）：整个待在它现在那块屏里，狗还在窗口正中画，只是窗口挪开一点，
        伸过交界的那一截由另一块屏上的窗口画（_sync_ghost）。狗停下来、身子全离开这块屏了才换过去（_screen_for_scene）。
        拎着、飞着的时候窗口大小不变（第一下长到最高）：改一次大小画布要重建，下一帧要等的时间是平时的两倍（录到的）。"""
        if self._park(wx, wy):
            return
        if not self._wide and size is None and self._wants_wide():
            self._enter_wide()                           # 狗动起来了：窗口铺宽，之后在里面跑、被拖、被扔都不挪窗口
        if (self._wide or self.showing_scaled) and size is None:
            self._place_held(wx, wy)
            return
        rect = self._normal_rect(wx, wy, size)
        offset = (wx - rect.x() - rect.width() / 2.0, wy - (rect.y() + rect.height() - self.ground_px))
        if rect == self.geometry() and abs(offset[0] - self.draw_offset[0]) < 0.02 and abs(offset[1] - self.draw_offset[1]) < 0.02:
            return
        self.draw_offset = offset
        self._commit_scene_geometry(rect)
        self._dirty = True

    def _normal_rect(self, wx: float, wy: float, size: Optional[tuple[int, int]] = None) -> QRect:
        """平时（贴着狗）根在 (wx, wy) 的窗口：size 那么大（不给是现在的大小），拎着飞着最高、顶到屏幕最上沿从上面截短，夹在狗那块屏里（place_scene 说的那几条）。"""
        w, h = size or (self.width(), self.height())
        screen = self._screen_for_scene(wx, wy)
        if screen is not None:
            g = screen.geometry()
            if self._flinging():
                h = min(round(config.WINDOW_MAX_HEIGHT * self.scale), g.height())
            else:
                room = math.floor(wy + self.ground_px - g.top())
                if 0 < room < h:
                    h = max(room, round(self.ground_px + self.dog.required * self.ppm + 2 * self.scale))
        x = round(wx - w / 2.0)
        y = round(wy + self.ground_px - h)
        if screen is not None:
            x = min(max(x, g.left()), g.left() + g.width() - w)
            y = min(max(y, g.top()), g.top() + g.height() - h)
        return QRect(x, y, w, h)

    # ---------- 加宽不缩回：窗口宽着、只长不缩，狗在里面动 ----------
    def _rest_rect(self, wx: float, wy: float) -> QRect:
        """根在 (wx, wy) 时平时贴着狗的那个窗口在哪（全局坐标、现在画的大小，含亚像素的那一圈往外取整）：宽着、看细节放大着，窗口至少要留出这一块——
        狗、头顶的「···」、姿势条、脚下的影子都在里面，和平时一模一样。"""
        w, h = self._window_size(self.scale)[0], self._needed_height(self.scale, self.ground_px)
        bottom = wy + self.ground_px
        left, top = math.floor(wx - w / 2.0), math.floor(bottom - h)
        return QRect(left, top, math.ceil(wx + w / 2.0) - left, math.ceil(bottom) - top)

    def _wide_rect(self, wx: float, wy: float, screen) -> QRect:
        """铺宽的窗口（全局坐标）：这块屏那么宽、和拎着飞着一样高（WINDOW_MAX_HEIGHT × 倍数；屏没那么高就屏高），底边在狗脚下留影子的那条（夹在屏里）。"""
        g = screen.geometry()
        need = self._rest_rect(wx, wy)
        h = min(max(round(config.WINDOW_MAX_HEIGHT * self.scale), need.height()), g.height())
        y = min(max(need.y() + need.height() - h, g.top()), g.top() + g.height() - h)
        return QRect(g.left(), y, g.width(), h)

    def set_dog_level(self, level: int) -> None:
        """狗换到窗口的第 level 层（things.rims_changed：歇进窝、踩上垫子时在窝和窝沿之间、盆后面，起来回到所有物件前面）：
        主窗口和每块屏的另一半一起换，变了才跟系统说；没显示的窗口下次显示时照 self.level 设（showEvent）。"""
        if level == self.level:
            return
        self.level = level
        for win in (self, *self._ghosts.values()):
            if win.isVisible():
                native.set_level(win, level)

    def menu_span(self) -> tuple[float, float]:
        """「···」旁边那一条（姿势条、道具栏）能摆在哪一段（窗口坐标，左、右）：接鼠标的那一块（_hit_area）——平时整个窗口，
        铺宽着、放大着只有平时贴着狗的那一块（道具栏按铺宽的窗口排成一长行，鼠标到了外面那几颗上就点穿了、整条收起）。"""
        area = self._hit_area()
        return float(area.left()), float(area.left() + area.width())

    def _hit_area(self) -> QRect:
        """窗口里哪一块可能点到狗（窗口坐标）：平时整个窗口；宽着、放大着只有贴着狗的那一块（别处不读回像素，input._update_hit）。"""
        if not (self._wide or self.showing_scaled):
            return self.rect()
        return self._rest_rect(*self.scene_world()).translated(-self.x(), -self.y()).intersected(self.rect())

    def _wants_wide(self) -> bool:
        """狗动起来了（跑、跳、被拖、被扔）、灵动交互开着、看得见：窗口该铺宽（place_scene 平时那条路上第一次挪的时候铺）。"""
        playground = getattr(self, "playground", None)
        return (self.dynamic and playground is not None and playground.active and self.isVisible() and not self.showing_scaled
                and self._scene_busy())

    def _enter_wide(self) -> None:
        """铺宽：按狗现在那块屏铺一次（_wide_rect）。狗一动起来就铺（place_scene），停够 WIDE_REST_S 缩回平时的（_tick → _leave_wide）。
        看得见的时候四条边都要动，分两步（_reshape）。"""
        if not self.dynamic or self.showing_scaled:
            return
        wx, wy = self.scene_world()
        screen = self._screen_for_scene(wx, wy) or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        self._wide, self._shrink_at, self._still_since = True, None, None
        rect = self._wide_rect(wx, wy, screen)
        if rect != self.geometry():
            if self.isVisible():
                self._reshape(rect, wx, wy)
            else:
                self._commit_keeping_dog(rect, wx, wy)
        self._dirty = True

    def _rest_wide(self, now: float) -> None:
        """宽着、狗停够 WIDE_REST_S（没人按着、没在看细节放大、没在换屏、分两步改窗口也走完了）：回到平时贴着狗的大小（狗停着，这一下看不出卡）。"""
        if not self._wide or WIDE_REST_S is None:
            return
        if (self._scene_busy() or self._drag is not None or self.showing_scaled or self._parked or self._flip_until is not None
                or self._reshape_next is not None or self._scale_adjusting):
            self._still_since = None
            return
        if self._still_since is None:
            self._still_since = now
        elif now - self._still_since >= WIDE_REST_S:
            self._leave_wide()

    def _leave_wide(self) -> None:
        """不铺宽了（狗停够了、关了灵动交互）：窗口回到平时贴着狗的大小，四条边都动就分两步；灵动交互关着身子不出屏幕，这一下就夹进来。"""
        self._still_since = None
        if not self._wide:
            return
        self._wide = False
        if self.showing_scaled:
            return                                           # 放大收完时按平时的摆（end_scaled）
        wx, wy = self.scene_world()
        if not self.dynamic and not self.dragging:
            wx, wy = self.keep_scene_inside(wx, wy)
            self._kept_top = self.dog.rest_top()
        self._reshape(self._normal_rect(wx, wy, (self._window_size(self.scale)[0], self._needed_height(self.scale, self.ground_px))), wx, wy)
        self._dirty = True

    def _place_held(self, wx: float, wy: float, switch: bool = True) -> None:
        """宽着（_wide）、看细节放大着：窗口不跟着狗挪，只改狗画在窗口里哪（draw_offset）。平时贴着狗的那一块（_rest_rect）出了窗口才动窗口：
        只往出去的那一边长、一直长到这块屏的边（不挪、不缩，长的那一下旧画面钉在不动的那个角，_pin_corner）；换了屏（switch：可以换）在新屏上重新铺。"""
        if switch:
            screen = self._screen_for_scene(wx, wy)
        else:
            screen = self._scene_screen if self._scene_screen in QApplication.screens() else self.screen()
        cur = self.geometry()
        if screen is not None:
            g = screen.geometry()
            if not g.contains(cur):                          # 换屏了（主窗口这时只画空的，_update_flip）、屏幕变了：在这块屏上重新铺，一步过去
                self._commit_keeping_dog(self._wide_rect(wx, wy, screen), wx, wy)
                return
            target = self._reshape_target()                  # 分两步的还没走完：按走完的算
            need = self._rest_rect(wx, wy).intersected(g)
            if not need.isEmpty() and not target.contains(need):
                left, top = (g.left() if need.left() < target.left() else target.left()), (g.top() if need.top() < target.top() else target.top())
                right = g.left() + g.width() - 1 if need.right() > target.right() else target.right()
                bottom = g.top() + g.height() - 1 if need.bottom() > target.bottom() else target.bottom()
                self._reshape(QRect(QPoint(left, top), QPoint(right, bottom)), wx, wy)
                return
        self._offset_in(cur, wx, wy)

    def _keep_held_fit(self) -> None:
        """宽着、狗停着的每一帧：站起来变高、跳的片段比平时高了，贴着狗的那一块出了窗口也要长（_place_held 平时只在狗挪了的时候调）。"""
        screen = self._scene_screen if self._scene_screen in QApplication.screens() else self.screen()
        if screen is None or self._parked:
            return
        wx, wy = self.scene_world()
        need = self._rest_rect(wx, wy).intersected(screen.geometry())
        if not need.isEmpty() and not self._reshape_target().contains(need):
            self._place_held(wx, wy, switch=False)

    def _reshape_target(self) -> QRect:
        """窗口要变成的样子：分两步改窗口还没走完第二步时是第二步，不然就是现在的。"""
        return QRect(self._reshape_next) if self._reshape_next is not None else self.geometry()

    def _offset_in(self, rect: QRect, wx: float, wy: float) -> None:
        """窗口在 rect（不动它）：狗的根画在 (wx, wy)。"""
        self.draw_offset = (wx - rect.x() - rect.width() / 2.0, wy - (rect.y() + rect.height() - self.ground_px))
        self._dirty = True

    def _commit_keeping_dog(self, rect: QRect, wx: float, wy: float) -> None:
        """窗口改成 rect，狗的根还画在 (wx, wy)。"""
        self._offset_in(rect, wx, wy)
        if rect != self.geometry():
            self._commit_scene_geometry(rect)

    def _reshape(self, rect: QRect, wx: float, wy: float) -> None:
        """窗口改成 rect、狗的根还在 (wx, wy)。新画面和新的窗口位置大小不一定同一拍到（Metal 上屏不跟着窗口一起提交），那一两帧系统拿手上那张画面
        按 layer 的 gravity 摆：只动相邻的两条边时钉在不动的那个角（_commit_scene_geometry → _pin_corner），早到、晚到都在原地。
        左右两边或上下两边都要动就分两步：先动右边和上边（钉左下），画够 RESHAPE_SWAPS 帧（最多等 RESHAPE_MAX_S）再动左边和下边（钉右上，_step_reshape）。"""
        cur = self.geometry()
        both = (rect.left() != cur.left() and rect.right() != cur.right()) or (rect.top() != cur.top() and rect.bottom() != cur.bottom())
        if both:
            first = QRect(QPoint(cur.left(), rect.top()), QPoint(rect.right(), cur.bottom()))
            if first.width() > 0 and first.height() > 0 and first != cur and first != rect:
                self._commit_keeping_dog(first, wx, wy)
                self._reshape_next, self._reshape_swaps, self._reshape_at = QRect(rect), 0, time.perf_counter()
                return
        self._commit_keeping_dog(rect, wx, wy)

    def _step_reshape(self, now: float) -> None:
        """分两步改窗口的第二步：第一步画够了（或等够了）再走。"""
        nxt = self._reshape_next
        if nxt is not None and (self._reshape_swaps >= RESHAPE_SWAPS or now - self._reshape_at >= RESHAPE_MAX_S):
            self._reshape_next = None
            self._commit_keeping_dog(nxt, *self.scene_world())

    def _pin_corner(self, left: bool, bottom: bool) -> None:
        """窗口改大小那一帧旧画面（或早到的新画面）钉在哪个角：不动的那个角（左 / 右、底 / 顶）。平时钉左下（native.pin_contents_to_bottom）；
        只往左边、往下长的时候换成右边、顶边。怎么设见 native.pin_contents；只在显示着的时候做，设不上就算了（钉左下）。"""
        if self._pinned == (left, bottom) or not self.isVisible():
            return
        if native.pin_contents(self, left, bottom):
            self._pinned = (left, bottom)

    def _park(self, wx: float, wy: float) -> bool:
        """狗还在动、身子已经不在主窗口那块屏上：主窗口不挪、不改大小、不画（再画 PARK_SWAPS 帧空的就歇着），只记下狗在哪。这时那块屏上没有东西要画，
        挪一次窗口、交一帧都要等系统回话（录到的：只有一个窗口在画时，交帧这一类卡顿几乎没了）。身子快回来了、狗停了就接着干。"""
        cur = self._scene_screen
        if cur is None or cur not in QApplication.screens() or not self._scene_busy() or cur.geometry().intersects(self._body_rect(wx, wy, PARK_MARGIN_M)):
            self._parked = False
            return False
        if not self._parked:
            self._parked, self._park_swaps = True, 0
        w, h = self.width(), self.height()
        self.draw_offset = (wx - self.x() - w / 2.0, wy - (self.y() + h - self.ground_px))
        return True

    def _flinging(self) -> bool:
        """狗被拎着，或者在空中（扔出去、掉下去）。"""
        if getattr(self, "_drag", None) is not None and getattr(self, "_dragged", False):
            return True
        playground = getattr(self, "playground", None)
        return playground is not None and playground.active and (playground.roam.lifted or playground.roam.task == "fall")

    def _body_rect(self, wx: float, wy: float, margin: float = 0.0, k: Optional[float] = None, top_m: Optional[float] = None) -> QRect:
        """狗的身子大约占的地方（全局坐标；任何朝向都在里面，BODY_HALF_M）。k、top_m 不给就是现在画的大小、现在要画多高（看细节算放大到哪时给）。"""
        ppm = self.ppm if k is None else config.PIXELS_PER_METER * k
        half = (BODY_HALF_M + margin) * ppm
        top = wy - ((self.dog.required if top_m is None else top_m) + margin) * ppm
        return QRect(round(wx - half), round(top), round(2 * half), round(wy + margin * ppm - top))

    def _screen_for_scene(self, wx: float, wy: float):
        """主窗口该待哪块屏：狗动着的时候不换（换一次两块屏像素密度不一样，画布要重建，快速甩的时候就是卡）；
        停下来了，还有身子在现在这块屏上也不换；身子全离开了才换到根所在的那块（别按估算的身子宽度判断：比狗真实的宽，
        狗停在那条差值里时主窗口还在这边、狗全由另一块屏上的窗口画，两边都点不到）。"""
        here = QApplication.screenAt(QPoint(round(wx), round(wy) - 4)) or QApplication.screenAt(QPoint(round(wx), round(wy)))
        cur = self._scene_screen
        if cur not in QApplication.screens():
            cur = None
        if cur is None:
            self._scene_screen = here or self.screen()
            return self._scene_screen
        if here is None or here is cur:
            return cur
        if self._scene_busy() or cur.geometry().intersects(self._real_body_rect(wx, wy)):
            return cur
        self._scene_screen = here
        self._ghost_swaps = GHOST_SWAPS                     # 新的一帧画好了另一个窗口才收（_frame_swapped）
        self._flip_until, self._flip_swaps = time.perf_counter() + FLIP_HOLD_S, 0   # 真到位之前只画空的（_update_flip）
        return here

    def _scene_busy(self) -> bool:
        """狗正动着：被拖着、在跑、在跳、在飞。"""
        if getattr(self, "_drag", None) is not None:
            return True
        playground = getattr(self, "playground", None)
        return playground is not None and playground.active and (playground.roam.busy or playground.roam.lifted)

    def _real_body_rect(self, wx: float, wy: float) -> QRect:
        """狗现在真实占的地方（全局坐标）：这一帧的骨头加一层皮毛。"""
        pose = self._pose
        if pose is None or not pose.world:
            return self._body_rect(wx, wy)
        xs = [transform_point(pose.root, (m[12], m[13], m[14]))[0] for m in pose.world]
        skin = BODY_SKIN_M * self.ppm
        left, right = wx + min(xs) * self.ppm - skin, wx + max(xs) * self.ppm + skin
        top = wy - self.dog.required * self.ppm
        return QRect(round(left), round(top), max(1, round(right - left)), max(1, round(wy - top)))

    def _settle_screen(self) -> None:
        """狗停下来了：身子全在另一块屏上就把主窗口换过去（狗身上的「···」、设置卡片都跟着主窗口）。"""
        if self._scene_busy() or self._scene_screen is None or not self.isVisible():
            return
        wx, wy = self.scene_world()
        here = QApplication.screenAt(QPoint(round(wx), round(wy) - 4)) or QApplication.screenAt(QPoint(round(wx), round(wy)))
        if here is None or here is self._scene_screen:
            return
        self.place_scene(wx, wy)

    def _follow_refresh(self) -> None:
        """拎着、飞着：帧率跟狗所在的屏，不跟主窗口那块屏（录到的：狗飞在 85 赫兹的 LG 上、主窗口留在 MacBook，只有 60 帧）。落地了换回主窗口那块屏的。"""
        if not self._flinging():
            if self._flung:
                self._flung = False
                self._sync_frame_rate()
            return
        self._flung = True
        wx, wy = self.scene_world()
        screen = QApplication.screenAt(QPoint(round(wx), round(wy) - 4))
        if screen is not None and hasattr(screen, "refreshRate"):
            self._frame_period = frame_period(screen.refreshRate(), config.ANIM_FPS, config.ANIM_MAX_FPS)

    def _update_flip(self, now: float) -> None:
        """主窗口刚换屏（拍的视频：旧屏上闪一两帧）：系统还没把窗口真挪过去，画面已经按新屏的像素密度画了，
        这一两帧显示在旧屏上（LG 上是放大一倍、被窗口切掉的半只狗，MacBook 上是缩小一半的狗）。所以到位之前主窗口只画空的，狗一直由新屏上的窗口画。"""
        until = self._flip_until
        if until is not None and now >= until and (self._flip_swaps >= FLIP_HOLD_SWAPS or now >= until + FLIP_HOLD_MAX_S):
            self._flip_until = None

    def _frame_swapped(self) -> None:
        if self._flip_until is not None:
            self._flip_swaps += 1
        elif self._ghost_swaps > 0:
            self._ghost_swaps -= 1
        if self._parked:
            self._park_swaps += 1
        if self._reshape_next is not None:
            self._reshape_swaps += 1

    def _ensure_ghosts(self, screens) -> None:
        """每块屏一个窗口，一直待在那块屏上。屏拔了收掉，接了新屏建一个。"""
        names = {s.name(): s for s in screens}
        for name in [n for n in self._ghosts if n not in names]:
            ghost = self._ghosts.pop(name)
            ghost.hide()
            ghost.view.release()                          # 显卡上的东西不归 Python 管：窗口删掉之前自己放
            ghost.deleteLater()
        k = self.scale
        for name, s in names.items():
            ghost = self._ghosts.get(name)
            if ghost is None:
                ghost = self._ghosts[name] = GhostWindow(self.model, self, s)
                g = s.geometry()
                h = min(round(config.WINDOW_MAX_HEIGHT * k), g.height())
                w = min(self._window_size(k)[0], g.width())   # 平时贴着狗的宽：主窗口宽着时比别的屏还宽，照它建就骑在两块屏上
                ghost.setGeometry(QRect(g.left(), g.top() + g.height() - h, w, h))
                ghost.show()                   # 建好就显示一次：原生窗口和画布在启动时建好（临时建那一下卡）
            ghost.home = s

    def drawing_ghosts(self) -> list:
        """正画着狗（另一半）的每块屏的窗口（look._wear 给它们带上解好的第一套毛色）。"""
        return [g for g in self._ghosts.values() if g.drawing]

    def _sync_ghost(self) -> None:
        """狗靠近哪块屏，那块屏上的窗口就画同一个姿势（画布按全局坐标摆，两边接得上）。主窗口所在的屏不用（主窗口刚换过来、新的一帧还没画好时除外）。
        看细节放大着：照着主窗口（放大开始时摆好就不动）摆、一样大（比这块屏宽就屏宽），之后只改画在哪（和主窗口一样不挪、不改大小）。
        平时按贴着狗的宽（_window_size），不按主窗口：主窗口宽着时铺满它那块屏的宽。"""
        screens = QApplication.screens()
        if len(screens) < 2 or self._pose is None or not self.isVisible():
            for ghost in self._ghosts.values():
                ghost.clear()
                if not self.isVisible():
                    ghost.hide()
            return
        self._ensure_ghosts(screens)
        wx, wy = self.scene_world()
        cur = self._scene_screen or self.screen()
        body = self._body_rect(wx, wy)
        normal_w = self._window_size(self.scale)[0]
        # 省电模式开着时，安静下来 GHOST_REST_S 以后把用不着的收起来（空的透明窗口一直摆着也占合成；摆回去一次 7～29 毫秒，伸手时卡一下，所以默认不收）：主窗口那块屏上的、身子离得远的那块屏上的。
        # 一有动静（鼠标靠近、按下、狗动了，_lively）全摆回去，比狗真到交界早得多；身子挨着的那块屏上的一直摆着。
        resting = GHOSTS_REST and self.power_saving and time.perf_counter() - self._lively_at >= GHOST_REST_S
        near = self._body_rect(wx, wy, GHOST_NEAR_M) if resting else None
        for ghost in self._ghosts.values():
            g = ghost.home.geometry()
            if resting and (ghost.home is cur or not g.intersects(near)):
                if ghost.drawing:
                    ghost.clear()                         # 先画一帧空的、下一帧再收：收起来的窗口里不留狗的画面（再摆出来会闪一下旧的）
                elif ghost.isVisible():
                    ghost.hide()
                continue
            if not ghost.isVisible():
                ghost.show()
            if (ghost.home is cur and self._ghost_swaps <= 0 and self._flip_until is None) or not g.intersects(body):
                ghost.clear()
                continue
            if self.showing_scaled:                          # 看细节放大着（hold_scaled）
                w, h = min(self.width(), g.width()), min(self.height(), g.height())
                x = min(max(self.x(), g.left()), g.left() + g.width() - w)
                y = min(max(self.y(), g.top()), g.top() + g.height() - h)
            else:
                w = min(normal_w, g.width())
                h = min(round(config.WINDOW_MAX_HEIGHT * self.scale), g.height())   # 高度固定：改大小画布也要重建
                x = min(max(round(wx - w / 2.0), g.left()), g.left() + g.width() - w)
                y = min(max(round(wy + self.ground_px - h), g.top()), g.top() + g.height() - h)
            offset = (wx - x - w / 2.0, wy - (y + h - self.ground_px))
            ghost.sync(QRect(x, y, w, h), make_frame(self._pose, 0.0, self.ppm, self.ground_px, w, offset), self.view.renderer.coat_image)

    @property
    def scene_x(self) -> float:
        """狗的坐标原点在窗口中的横坐标，含整数窗口位置留下的半像素。"""
        return self.width() / 2.0 + self.draw_offset[0]

    @property
    def scene_ground(self) -> float:
        """地面在窗口中的纵坐标（从顶算），狗、操作栏和鼠标投影共用。"""
        return self.height() - self.ground_px + self.draw_offset[1]

    def _height_needed(self) -> int:
        return self._needed_height(self.scale, self.ground_px - self.draw_offset[1])

    def _needed_height(self, k: float, ground: float) -> int:
        """k 倍大小、地面离窗口底边 ground 像素时，平时贴着狗的窗口要多高：狗最高到哪（站、坐、趴、睡和起身坐下这些过渡片段里最高的 dog.posture_tops，
        再算上正在播、排着的 dog.stance_top：跳、高的随机动作）、头顶给「···」留的（hover.min_height：也按最高的姿势留），不低于基础高度、不高过最高。
        换姿势时窗口和宽着时画的那一块都不改大小，只有跳、高的动作临时长（真机上量到起身时窗口跟着「···」连着改了 25 次、每次多画一帧；
        改成起身前一次长够，那一次 Metal 窗口改大小主线程还要等 67～95 毫秒）。换了模型也不缩：按这次运行里用过的模型里最高的留（_room_m，
        真机上换回矮的那只 1.5 秒后缩一下又是 45～54 毫秒的一帧）。"""
        tallest = self.dog.posture_tops()[1]
        if tallest > self._room_m:
            self._room_m = tallest                   # 这次运行里用过的模型里最高的（换回矮的那只不缩：换模型时窗口不改大小）
        top = max(self.dog.stance_top(), self._room_m)
        need = math.ceil(ground + top * config.PIXELS_PER_METER * k + 6 * k)
        hover = getattr(self, "hover", None)       # 启动第一次定大小时操作栏尚未创建
        if hover is not None:
            need = max(need, hover.min_height(ground))
        return max(round(config.WINDOW_HEIGHT * k), min(need, round(config.WINDOW_MAX_HEIGHT * k)))

    def _refresh_frame(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        if self._flip_until is not None or self._parked:
            self.view.set_frame(None)                       # 主窗口这时不该有东西（_update_flip、_park）
        elif self._pose is not None:
            w, h = self.width() if width is None else width, self.height() if height is None else height
            self.view.set_frame(self._frame_for(w, h))
            self.view.cover_area = self._cover_area(w, h)

    def _cover_area(self, w: int, h: int) -> Optional[QRect]:
        """宽着、放大着：上面那层（「···」、姿势条、脚下的字）只重画狗附近那一块（窗口坐标；平时那个窗口左右再各留一个那么宽）；平时整层（None）。"""
        if not (self._wide or self.showing_scaled):
            return None
        k = self.scale
        dx, dy = self.draw_offset
        root_x, bottom = w / 2.0 + dx, h + dy                        # 根的 x；平时那个窗口的底边（根往下 ground_px）
        half = 1.5 * self._window_size(k)[0]                          # 平时那个窗口左右再各留一个那么宽（姿势条往外伸也在里面）
        top = bottom - self._needed_height(k, self.ground_px)
        return QRect(math.floor(root_x - half), math.floor(top), math.ceil(2 * half) + 1, math.ceil(bottom - top) + 1).intersected(QRect(0, 0, w, h))

    def _frame_for(self, w: int, h: int):
        """窗口 w × h 时这一帧画什么（make_frame）。宽着、看细节放大着只画贴着狗的那一块（region：平时那个窗口那么大，从窗口左下角算）：
        离屏画布、显卡每帧要画的只有那么大，不跟着窗口变大（铺满屏宽的窗口按整个窗口画，每帧多出十几兆像素）。那一块出了窗口的截掉。"""
        if not (self._wide or self.showing_scaled):
            return make_frame(self._pose, 0.0, self.ppm, self.ground_px, w, self.draw_offset)
        dx, dy = self.draw_offset
        root_x, root_b = w / 2.0 + dx, self.ground_px - dy           # 狗的根在窗口里：离左边、离底边多远
        rw, rh = self._window_size(self.scale)[0], self._needed_height(self.scale, self.ground_px)
        x0, b0 = max(0, math.floor(root_x - rw / 2.0)), max(0, math.floor(root_b - self.ground_px))
        x1, b1 = min(w, math.ceil(root_x + rw / 2.0)), min(h, math.ceil(root_b - self.ground_px + rh))
        if x1 <= x0 or b1 <= b0:
            return None
        rw = x1 - x0
        return make_frame(self._pose, 0.0, self.ppm, self.ground_px, rw, (root_x - x0 - rw / 2.0, dy + b0), region=(x0, b0, rw, b1 - b0))

    def _commit_scene_geometry(self, rect: QRect) -> None:
        """先准备同一套投影，再一次提交位置和尺寸。画布一改大小就会当场画一帧，不能等下个 tick 才换 Frame。
        改大小时旧画面钉在不动的那个角（_pin_corner：左边不动钉左、只有右边不动钉右；底边不动钉底、只有顶边不动钉顶；都动照旧钉左下）。
        分两步改窗口还没走完第二步的（_reshape）：别处改了窗口，那一步作废。"""
        cur = self.geometry()
        if rect.size() != cur.size():
            self._pin_corner(rect.left() == cur.left() or rect.right() != cur.right(), rect.bottom() == cur.bottom() or rect.top() != cur.top())
        self._reshape_next = None
        self._refresh_frame(rect.width(), rect.height())
        self.setGeometry(rect)                     # 无边框窗口不需要 fixedSize；避免先 resize 后 move 的中间状态
        self.view.refresh()

    def _fit_height(self, now: float, dt: float = 1.0) -> None:
        """窗口按狗现在要画多高临时长高、缩回：底边不动；长到屏幕顶就停（头顶被裁，算跳出屏幕）；缩回等 SHRINK_DELAY 防抖。
        长高每帧最多 GROW_PX_PER_SEC × dt（旧画面拉伸那一帧才不明显）。狗头顶上方一直给「···」留着位置（hover.min_height：
        鼠标在不在都一样，悬停时窗口不改大小），钉住的按钮比狗高时窗口也不缩到把它顶下来。宽着另算（_keep_held_fit：只长不缩）。"""
        if self._parked or self._flinging() or self.showing_scaled or self._wide or self._reshape_next is not None:
            self._shrink_at = None                       # 拎着、飞着、看细节放大着、宽着、分两步改窗口还没走完：不在这里改大小
            return
        k = self.scale
        target = self._height_needed()
        h = self.height()
        if target > h:
            self._set_height(min(target, h + max(1, round(GROW_PX_PER_SEC * k * dt))))
            self._shrink_at = None
        elif target < h:
            if self._shrink_at is None:
                self._shrink_at = now + SHRINK_DELAY
            elif now >= self._shrink_at:
                self._set_height(target)
                self._shrink_at = None
        else:
            self._shrink_at = None

    def _set_height(self, h: int) -> None:
        """改高度，底边不动。顶到屏幕最上沿就不再长（狗画在菜单栏上面以后，窗口能长进菜单栏那一条）。"""
        bottom = self.y() + self.height()
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if screen is not None:
            h = min(h, max(round(config.WINDOW_HEIGHT * self.scale), bottom - screen.geometry().top()))
        if h == self.height():
            return
        self._commit_scene_geometry(QRect(self.x(), bottom - h, self.width(), h))   # 狗没动：缩放的固定点照旧（set_scale 按狗的根看动没动）
        self._dirty = True

    def _dog_center(self) -> tuple[float, float, float, float]:
        """这一刻狗网格的视觉中心：屏幕坐标 + 投影空间坐标（米）。只在新调节 / 锚点失效时调用。
        尚无姿势帧时以半高兜底；画面准备好后，下一次调节会取实际网格中心。"""
        frame = self.view.frame
        center = self.view.renderer.visual_center(frame) if frame is not None else None
        mx, my = center if center is not None else (0.0, self.dog.rest_top() / 2.0)
        return self.x() + self.scene_x + mx * self.ppm, self.y() + self.scene_ground - my * self.ppm, mx, my

    def _capture_scale_anchor(self) -> None:
        self._anchor = self._dog_center()
        self._anchor_rest_top = self.dog.rest_top()
        self._anchor_frame_ready = self.view.frame is not None
        self._anchor_root = self.scene_world()

    def _dog_moved_since_anchor(self) -> bool:
        """上次缩放以后狗挪过（被拖过、跑过、被放到角落、窗口被系统挪过）：按狗的根看，不按窗口（宽着时狗挪了窗口不动；窗口长高缩回时狗不动）。"""
        r = self._anchor_root
        return r is None or math.dist(self.scene_world(), r) > 0.5

    def scale_range(self, screen=None) -> tuple[int, int]:
        """大小滑杆、捏合、滚轮能调的范围（百分比）：最小 30%；最大是狗站着约占这块屏（狗现在在的那块，或给的那块）屏高的三分之二（TALL_SHARE，
        取到 10%），至少 400%（电视当显示器，LG 约 530%、4K 电视按 1 倍约 790%）。只按屏幕的点数算，不猜是不是电视。
        换屏时大小本身不变（这个范围跟着变）。"""
        if screen is None:
            screen = self._scene_screen if getattr(self, "_scene_screen", None) in QApplication.screens() else (self.screen() or QApplication.primaryScreen())
        h = screen.geometry().height() if screen is not None else 900.0
        stand = max(self.dog.clip_top(c) for c in POSTURE_PLANS["standing"].loop)
        top = round(TALL_SHARE * h / (stand * config.PIXELS_PER_METER) * 10.0) * 10
        return SCALE_MIN_PCT, max(SCALE_MAX_PCT, top)

    def _scale_limits(self) -> tuple[float, float]:
        """set_scale 夹到的范围（倍）：显示着按狗在的那块屏（scale_range）；还没显示（启动时第一次定大小）按最大的那块屏，接着电视记下的大小不被笔记本的上限截掉。"""
        if self.isVisible():
            lo, hi = self.scale_range()
        else:
            lo, hi = SCALE_MIN_PCT, max([self.scale_range(s)[1] for s in QApplication.screens()] or [SCALE_MAX_PCT])
        return lo / 100.0, hi / 100.0

    def begin_scale_adjustment(self) -> None:
        """一次拖动 / 精调期间锁住支点；重复 begin 不会重新量中心。"""
        if not self._scale_adjusting:
            self._capture_scale_anchor()
            self._scale_adjusting = True

    def end_scale_adjustment(self) -> None:
        """只结束锁定，保留浮点支点和绘制残差；松手不取整、不挪狗。"""
        self._scale_adjusting = False

    def set_scale(self, k: float, keep_center: bool = True) -> None:
        """缩放（滑块、捏合、滚轮、+ -、重置）以狗的中心为固定点（给狗的中心打一个点）。
        别以窗口中心为准：站着 / 坐着时窗口给头顶的「···」多长了一截（_fit_height），下一格缩放从长高的窗口重新量中心，
        中心每格往上偏几像素，拖大小滑块时狗一路往上跑。这是存下来的大小（world_scale）；看细节的临时放大当场先收掉。
        夹在 scale_range 里；已经比上限大（从大屏挪到小屏上了）的只能往小调，不会一调就缩到上限。宽着：窗口不挪，只在里面换狗画多大（放不下了往那边长）。"""
        closeup = getattr(self, "closeup", None)       # 启动时第一次定大小，它还没建
        if closeup is not None:
            closeup.drop_zoom()
        lo, hi = self._scale_limits()
        k = max(lo, min(max(hi, self.world_scale), k))
        if keep_center and not self._scale_adjusting and (self._anchor is None or self._dog_moved_since_anchor()
                or self.dog.rest_top() != self._anchor_rest_top or (not self._anchor_frame_ready and self.view.frame is not None)):
            # 第一次缩放，或者上次缩放之后狗被拖过、被放到角落、被系统挪过、换了姿势：以现在狗的中心为准。
            # 不能在窗口显示之前就记，否则记的是 (0, 0) 附近的默认位置，第一次缩放会跳过去。
            self._capture_scale_anchor()
        root = self.scene_world()
        self.world_scale = k
        self._set_drawn_scale(k)
        w, _ = self._window_size(k)
        if keep_center:
            cx, cy, mx, my = self._anchor
            origin_x = cx - mx * self.ppm
            bottom = cy + my * self.ppm + self.ground_px
            if getattr(self, "dynamic", True):
                bottom += self._head_overshoot(origin_x, bottom - self.ground_px)
            else:                                        # 灵动交互关着：调大了身子也不出屏幕，调回去又回到原来的地方（固定点没变）
                origin_x, ground = self.keep_scene_inside(origin_x, bottom - self.ground_px)
                bottom = ground + self.ground_px
            if self._wide:
                self._place_held(origin_x, bottom - self.ground_px, switch=False)
            else:
                x, b = round(origin_x - w / 2.0), round(bottom)
                self.draw_offset = (origin_x - x - w / 2.0, bottom - b)
        elif self._wide:
            self._place_held(*root, switch=False)
        else:
            x, b = self.x(), self.y() + self._window_size(k)[1]
            self.draw_offset = (0.0, 0.0)
        if not self._wide:
            h = self._height_needed()               # 一次到所需高度，不先缩回基础高度再让下一帧长高
            screen = QApplication.screenAt(QPoint(x + w // 2, b - h // 2)) or QApplication.primaryScreen()
            if screen is not None:
                h = min(h, max(round(config.WINDOW_HEIGHT * k), b - screen.geometry().top()))
            self._commit_scene_geometry(QRect(x, b - h, w, h))
        self._shrink_at = None
        if keep_center:
            self._anchor_root = self.scene_world()
            self._save_pos()
        self.prefs.set("scale", k)
        playground = getattr(self, "playground", None)
        if playground is not None:
            playground.scale_changed()
        self._dirty = True

    def keep_scene_inside(self, wx: float, wy: float) -> tuple[float, float]:
        """灵动交互关着时狗的根最多到哪：身子（BODY_HALF_M 是任何姿势、任何朝向都不超出的宽度）、头顶、脚下的影子都不出屏幕。"""
        return self.inside_at(wx, wy, self.scale)

    def inside_at(self, wx: float, wy: float, k: float, top_m: Optional[float] = None, shadow: bool = True) -> tuple[float, float]:
        """狗画成 k 倍、根在 (wx, wy) 时，身子不出屏幕最多到哪（keep_scene_inside 的那一套，看细节算放大到哪时也用）。
        top_m：身子多高（米，不给是现在这个姿势的 rest_top）；shadow=False 不给脚下的影子留地方（灵动交互里脚踩在线上，下面本来就有地面的边）。"""
        ppm = config.PIXELS_PER_METER * k
        top = self.dog.rest_top() if top_m is None else top_m
        return keep_on_screens([_rect(s.geometry()) for s in QApplication.screens()], wx, wy, BODY_HALF_M * ppm,
                               top * ppm, SHADOW_ROOM_PX * k if shadow else 0.0)

    def _keep_body_on_screen(self) -> None:
        """灵动交互关着：狗现在的地方身子出去了就挪回来（刚关灵动交互、刚启动、站起来变高了）。"""
        if self.dynamic or self.dragging:
            return
        wx, wy = self.scene_world()
        nx, ny = self.keep_scene_inside(wx, wy)
        if (nx, ny) != (wx, wy):
            self.place_scene(nx, ny)

    def _head_overshoot(self, x: float, ground: float) -> float:
        """狗的根在全局 (x, ground) 时头顶高出这一列屏幕最上沿多少（像素，没高出 0）。"""
        top = column_top([_rect(s.geometry()) for s in QApplication.screens()], x, ground)
        return 0.0 if top is None else max(0.0, top - (ground - self.dog.rest_top() * self.ppm))

    def zoom(self, factor: float) -> None:
        """滚轮、捏合（widget/input.py）：改存下来的大小（夹在 scale_range 里）。看细节放大着（滑块不在 1 倍）时不理（临时的放大不能被它变成存下来的大小）；
        已经在缩回去的路上就当场收完再改。"""
        if self.closeup.zoom_on:
            return
        self.mark_scale_chosen()
        self.set_scale(self.world_scale * factor)

    # ---------- 看细节的临时放大（widget/closeup.py 调） ----------
    @property
    def showing_scaled(self) -> bool:
        """看细节放大着：窗口是为放大摆的（hold_scaled 到 end_scaled 之间）。这期间不挪窗口、不改大小、不存位置、不夹身子、不换屏，roam 不走。"""
        return self._unzoomed is not None

    def _set_drawn_scale(self, k: float) -> None:
        """狗现在画多大（scale、ppm、ground_px 一起改）。存下来的大小是 world_scale，只有 set_scale 改它。"""
        self.scale = k
        self.ppm, self.ground_px = config.PIXELS_PER_METER * k, config.GROUND_Y * k

    def scaled_window(self, states: list[tuple[float, float, float]]) -> QRect:
        """放得下 states 里每一个 (倍数, 根 x, 根 y) 的狗的窗口（全局坐标）：和拎着、飞着一样高（WINDOW_MAX_HEIGHT × 倍数，放大期间换姿势变高也放得下），
        宽是那个倍数下平时的宽，夹在主窗口这块屏里（不骑在两块屏中间、顶不出屏幕最上沿：放不下的那截由每块屏的窗口画、或本来就在屏幕外）。"""
        left = top = math.inf
        right = bottom = -math.inf
        for k, wx, wy in states:
            half = self._window_size(k)[0] / 2.0
            ground = config.GROUND_Y * k
            left, right = min(left, wx - half), max(right, wx + half)
            top, bottom = min(top, wy + ground - config.WINDOW_MAX_HEIGHT * k), max(bottom, wy + ground)
        x0, y0, x1, y1 = math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)
        screen = self._scene_screen if self._scene_screen in QApplication.screens() else (self.screen() or QApplication.primaryScreen())
        if screen is None:
            return QRect(x0, y0, x1 - x0, y1 - y0)
        g = screen.geometry()
        y0, y1 = max(y0, g.top()), min(y1, g.top() + g.height())
        w, h = min(x1 - x0, g.width()), max(1, min(y1 - y0, g.height()))
        x = min(max(x0, g.left()), g.left() + g.width() - w)
        y = min(max(y0, g.top()), g.top() + g.height() - h)
        return QRect(x, y, w, h)

    def hold_scaled(self, rect: QRect, k: float, wx: float, wy: float) -> None:
        """看细节放大：窗口要装得下 rect（scaled_window 算的，按上限）——只长不缩：已经装得下（宽着的窗口多半是）就不动，装不下和现在的合起来
        （四条边都动就分两步，_reshape）；狗画成 k 倍、根在 (wx, wy)。只在放大开始时调；之后每帧只调 show_scaled（拖出了那一块才往那边长），
        收完 end_scaled 摆回去。(wx, wy) 就是不放大的狗的根（dog_root）。"""
        if self._unzoomed is None:
            self._unzoomed = (wx, wy)
            self._shrink_at, self._anchor_root = None, None         # 下一次调大小重新量狗的中心
        self._set_drawn_scale(k)
        cur = self._reshape_target()
        if not cur.contains(rect):
            self._reshape(rect.united(cur), wx, wy)
        else:
            self._offset_in(self.geometry(), wx, wy)
        self._dirty = True

    def show_scaled(self, k: float, wx: float, wy: float) -> None:
        """看细节放大的每一帧：狗画成 k 倍、根在 (wx, wy)，窗口不挪不改大小（和 _park 一样只改 draw_offset；放大着拖到窗口外了才往那边长，_place_held）。
        不存大小、不告诉灵动交互。"""
        self._set_drawn_scale(k)
        self._place_held(wx, wy, switch=False)

    def slide_scaled(self, wx: float, wy: float) -> None:
        """看细节放大着把狗拖到了 (wx, wy)（closeup.drag_to）：这就是它真的位置——不放大的狗的根也挪过去（dog_rect、记位置、收完回到这）。"""
        if self._unzoomed is not None:
            self._unzoomed = (wx, wy)

    def end_scaled(self, wx: float, wy: float) -> None:
        """放大收完：回到存下来的大小，狗的根回到 (wx, wy)。宽着：窗口不动（它本来就装得下）；平时：窗口按平时的大小摆回去，只摆这一次（四条边都动分两步）：
        灵动交互关着时放大期间换过姿势（站起来变高了）的，这一下就按现在的姿势夹进屏幕（keep_scene_inside），不再挪第二次。"""
        if self._unzoomed is None:
            return
        self._unzoomed = None
        self._set_drawn_scale(self.world_scale)
        self._shrink_at, self._anchor_root = None, None
        if not self.dynamic and not self.dragging:
            wx, wy = self.keep_scene_inside(wx, wy)
            self._kept_top = self.dog.rest_top()
        if self._wide:
            self._place_held(wx, wy, switch=False)
        else:
            self.draw_offset = (0.0, 0.0)
            size = (self._window_size(self.scale)[0], self._needed_height(self.scale, self.ground_px))
            self._reshape(self._normal_rect(wx, wy, size), wx, wy)
        self._dirty = True

    # ---------- 推荐大小：没调过大小的，第一次开灵动交互直接用；调过的不动，滑杆上标个刻度 ----------
    def mark_scale_chosen(self) -> None:
        """你自己调了大小：以后不再替你改（正在平滑变大小的停下）。"""
        if self._scale_anim.state() == QVariantAnimation.Running:
            self._scale_anim.stop()
            self._scale_anim_then = None
            self.end_scale_adjustment()
        self.prefs.set("scale_chosen", True)

    def recommended_scale(self, screen=None) -> float:
        """狗现在所在的屏（或给定的屏）最适合跳窗口的大小。跨屏时大小不自动变，这个数跟着屏变。"""
        screen = screen or self.screen() or QApplication.primaryScreen()
        return recommended_scale(screen.geometry().height() if screen is not None else 900.0, temper.max_up(self.tuning), self.pack.height_m, self.pack.fit_m)

    def _apply_first_size(self, screen, animated: bool) -> None:
        """第一次开灵动交互、大小没动过：用这块屏的推荐大小（只这一次）。动过的不碰（旧版本留下来的大小也算动过）。"""
        if self.prefs.get("size_suggested"):
            return
        self.prefs.set("size_suggested", True)
        if self.prefs.get("scale_chosen") or abs(self.prefs.get("scale") - 1.0) > 1e-3:
            return
        k = self.recommended_scale(screen)
        if abs(k - self.world_scale) < 0.01:
            return
        if animated:
            self._animate_scale(k)
        else:
            self.set_scale(k, keep_center=False)

    def _animate_scale(self, k: float, then=None) -> None:
        """平滑地变到这个大小（围绕狗的中心，和拖滑块一样）。从存下来的大小起（看细节还在缩回去的路上就先当场收完）。"""
        self._scale_anim.stop()
        self._scale_anim_then = then
        self.closeup.drop_zoom()
        if native.reduce_motion():
            self.set_scale(k)
            self._scale_anim_done()
            return
        self.begin_scale_adjustment()
        self._scale_anim.setDuration(450)
        self._scale_anim.setStartValue(self.world_scale)
        self._scale_anim.setEndValue(k)
        self._scale_anim.start()

    def _scale_anim_done(self) -> None:
        self.end_scale_adjustment()
        then, self._scale_anim_then = self._scale_anim_then, None
        if then is not None:
            then()

    def show_too_high(self) -> None:
        """狗够不着、那条线又在它上面：每块屏正中弹一张点不到的提示「好像有点高」（和卸载提示同一种，淡入 0.2 秒、停 4 秒、淡出 0.5 秒）。"""
        if ui_frozen() or not self.isVisible():
            return
        if self._bubble is None:
            self._bubble = DogBubble()
        self._bubble.say(tr("A bit too high"), menu_scale(self.scale))
        if self._place_bubble(0.0):
            self._bubble.present()

    def _place_bubble(self, dt: float) -> bool:
        """气泡摆到狗头旁边（全局坐标）。狗头还不知道在哪返回 False。"""
        head = self.dog.head_position()
        if head is None:
            return False
        hx, hy = project(head, self.ppm, self.ground_px, ELEVATION, self.width(), self.draw_offset)
        x, y = self.x() + hx, self.y() + self.height() - hy
        screen = QApplication.screenAt(QPoint(round(x), round(y))) or self.screen()
        facing = 1.0 if math.cos(math.radians(self.dog.yaw)) >= 0.0 else -1.0
        self._bubble.follow(x, y - BUBBLE_HEAD_M * self.ppm, BUBBLE_REACH_M * self.ppm, facing, screen.geometry(), dt)
        return True

    def _sync_bubble(self, dt: float) -> None:
        b = self._bubble
        if b is None or not b.isVisible():
            return
        if ui_frozen() or not self.isVisible() or not self._place_bubble(dt):
            b.hide()

    # ---------- 每帧 ----------
    def _look_target(self, dt: float) -> Optional[Vec3]:
        """鼠标在屏幕上的位置 → 狗头前方 Z_FRONT 米那个平面上的世界坐标点。
        灵动交互里有要看的东西（球在飞、被你拿着、在追球）就看它；没有就看鼠标，不看鼠标跟随开没开（灵动交互开着时那个开关藏起来）；
        鼠标停着一阵了（playground.watching_you 是假的）就不看了：头回正，身子也不跟着鼠标换边，自己做自己的事，鼠标一动马上回来看。
        灵动交互关着：鼠标跟随开着就一直看，鼠标不动也盯着。
        身子朝哪边转（play._follow_body）：头看着球的时候跟球，不跟鼠标（头看着球、身子却跟着鼠标转，是拧着的）；不看球了再按鼠标。"""
        playground = self.playground
        point = playground.look_point() if playground.active else None
        ball = self._world_point(QPointF(*point)) if point is not None else None
        eyes = not playground.active or playground.watching_you
        if not self.dynamic:
            self.dog.body_target = None
        elif point is not None and not playground.glancing:               # 呆萌的来回看只动头，身子照旧跟鼠标
            self.dog.body_target = ball
        else:
            self.dog.body_target = self._world_point(QPointF(QCursor.pos())) if eyes else None
        if point is not None:
            return ball
        if not (eyes if self.dynamic else self.follow_cursor) or (playground.active and playground.roam.head_busy):
            return None                                  # 鼠标停着一阵了 / 没开鼠标跟随；头正埋在盆里吃喝（摆着的饭盆、水盆）也不看鼠标
        return self._world_point(QPointF(QCursor.pos()))

    def _world_point(self, cur: QPointF) -> Optional[Vec3]:
        """屏幕全局坐标 → 狗头前方 Z_FRONT 米那个平面上的世界坐标点。"""
        head = self.dog.head_position()
        if head is None:
            return None
        hx, hy = project(head, self.ppm, self.ground_px, ELEVATION, self.width(), self.draw_offset)
        local = cur - QPointF(self.pos())
        return (head[0] + (local.x() - hx) / self.ppm, head[1] + ((self.height() - local.y()) - hy) / self.ppm, head[2] + Z_FRONT)

    def _sync_frame_rate(self, *_) -> None:
        """动画节拍跟窗口所在屏幕的刷新率（config.ANIM_MAX_FPS：120 赫兹 → 60 帧、85 → 85）。换了屏（停稳时）、屏幕改了刷新率都重新算。"""
        screen = self.screen()
        if screen is not self._rate_screen:
            if self._rate_screen is not None:
                try:
                    self._rate_screen.refreshRateChanged.disconnect(self._sync_frame_rate)
                except (RuntimeError, TypeError):
                    pass                                 # 那块屏已经拔掉了
            self._rate_screen = screen
            if screen is not None:
                screen.refreshRateChanged.connect(self._sync_frame_rate)
        hz = screen.refreshRate() if screen is not None else 0.0
        self._frame_period = frame_period(hz, config.ANIM_FPS, config.ANIM_MAX_FPS)
        self._pace_period = self._frame_period

    # ---------- 待着时少画 ----------
    def _lively(self) -> bool:
        """有动静：狗在跑跳、被拎着、在转身、在换姿势，球在动，有人碰（鼠标在旁边），卡片、「···」、气泡在动，窗口在挪、在长高缩回。
        狗自己待着时播的那些（呼吸、摇尾巴、挠痒、嗅地）不算。"""
        if self._scene_busy() or self._frame_clients or self._flip_until is not None or self._ghost_swaps > 0 or self._parked:
            return True
        dog, run = self.dog, self.dog.run
        if dog.turn is not None or dog.steps or dog.jump is not None or dog.manual is not None:
            return True                                  # 转身、排着要换的姿势、跳、表盘点的那整段
        if self.closeup.moving:
            return True                                  # 看细节：转盘在转、在放大缩回
        if run is None and (dog.transition or dog.queue):
            return True                                  # 换姿势的退出 / 进入片段（自己随机做的动作也播过渡片段，那个不算）
        if self.hover.alpha > 0.0 or self.hover.active:
            return True
        if self.playground.active and not self.playground.quiet():
            return True
        geo = (self.x(), self.y(), self.width(), self.height())
        if geo != self._paced_geo:
            self._paced_geo = geo
            return True
        if self._bubble is not None and self._bubble.isVisible():
            return True
        cursor, m = QCursor.pos(), IDLE_NEAR_PX
        near = self._rest_rect(*self.scene_world()) if (self._wide or self.showing_scaled) else self.geometry()   # 按狗：宽着的窗口铺满屏宽
        if near.adjusted(-m, -m, m, m).contains(cursor):
            return True
        if any(g.drawing and g.geometry().adjusted(-m, -m, m, m).contains(cursor) for g in self._ghosts.values()):
            return True
        ball = self.playground.ball_win
        if ball is not None and ball.isVisible() and ball.geometry().adjusted(-m, -m, m, m).contains(cursor):
            return True
        return self.playground.things.near(cursor, m)

    def _pace(self, now: float) -> None:
        """省电模式开着才少画（默认满帧，省电做成高级设置里的开关）：没动静 IDLE_AFTER_S 以后每 idle_skip 帧画一帧（开发者设置页，
        1 = 不降；再少也不低于 config.IDLE_MIN_FPS），间隔还是屏幕刷新的整数倍，不会一跛一跛。有动静（_lively、wake）马上回满帧。"""
        if self._lively():
            self._lively_at = now
        period = self._frame_period
        n = int(self.tuning["idle_skip"]) if self.power_saving else 1
        if n > 1 and now - self._lively_at >= IDLE_AFTER_S:
            while n > 1 and period * n > 1.0 / config.IDLE_MIN_FPS + 1e-6:
                n -= 1
            period *= n
        self._pace_period = period

    def wake(self) -> None:
        """有动静了（卡片要动、有人点）：下一帧不等降档的那一格，马上画。"""
        now = time.perf_counter()
        self._lively_at = now
        if self._pace_period > self._frame_period:
            self._pace_period = self._frame_period
            if self._anim_timer.isActive() and self._next_frame - now > self._frame_period:
                self._next_frame = now
                self._anim_timer.start(0)

    def _frame(self) -> None:
        """动画一帧，再按屏幕刷新的节拍排下一帧：理想时刻一格格往后排（计时器只能按整毫秒，85 赫兹就交替 11 / 12 毫秒，平均正好跟上），
        卡了一下就从现在重排、不补帧。窗口整个看不见（屏幕关了、锁屏、被完全挡住）就不算也不画，每 0.25 秒看一眼
"""
        if native.window_occluded(self) and not ui_frozen() and not self._scene_busy():   # 狗正动着不算：主窗口在关着的那块屏上，狗可能在另一块屏上飞
            for card in list(self._frame_clients):
                try:
                    card.own_clock()                     # 狗看不见了：卡片的动画用它们自己的节拍走完
                except Exception:                        # noqa: BLE001 —— 见下
                    log.exception("frame client failed")
            self._frame_clients.clear()
            self._anim_timer.start(HIDDEN_POLL_MS)
            return
        try:
            self._tick()
        except Exception:                                # noqa: BLE001 —— 哪一帧出错也不能让节拍断掉（断了狗就定住不动了）：记下来，下一帧照排
            log.exception("frame failed")
            if self.playground.active:
                self.playground.fail_safe()              # 灵动交互出的错：把它关掉，狗照常过日子
        if self._frame_clients:
            now = time.perf_counter()
            for card in list(self._frame_clients):
                try:
                    keep = card.isVisible() and card.frame_step(now, self._frame_period)
                except Exception:                        # noqa: BLE001 —— 哪张卡片的动画出错就摘掉它，狗的帧循环不能断：下一帧是在这之后才排的，
                    log.exception("frame client failed") # 断了狗就不动、卡片停在半截（换语言时旧卡片删掉了还挂在这，整个小组件像卡死）
                    keep = False
                if not keep:
                    self._frame_clients.discard(card)
        now = time.perf_counter()
        period = self._pace_period                       # 平时就是 _frame_period；待着只剩呼吸时更长（_pace）
        self._next_frame += period
        if self._next_frame < now:
            self._next_frame = now + period
        self._anim_timer.start(max(0, round((self._next_frame - now) * 1000)))

    def _tick(self) -> None:
        now = time.perf_counter()
        dt = min(now - self._last_tick, 0.1)   # 卡顿时不要一下跳很远
        self._last_tick = now
        self._follow_refresh()
        self._update_flip(now)
        self._step_reshape(now)                  # 分两步改窗口的第二步（_reshape）
        top = self.dog.rest_top()
        if top != self._kept_top and not self.showing_scaled:   # 灵动交互关着：换了姿势变高了，头也不出屏幕（看细节放大着：根不动，缩回来再夹）
            self._kept_top = top
            self._keep_body_on_screen()
        self._update_hit(now)                    # 点击范围就是狗：鼠标底下不是狗就让窗口不接鼠标（widget/input.py）
        if self.hover.tick(dt, now, self._flinging()):   # 拎着、飞着不出「···」
            self._dirty = True
        self._dirty = False
        self._feel(dt)                              # 兴奋度：按这一刻的状态推一帧，尾巴跟着它（招牌时刻在 playground 里叠在上面）
        if self.playground.active:
            self.playground.update(dt, hold=self.showing_scaled)   # 球、狗在空间里跑跳（roam）、表情；看细节放大着 roam 不走
        self.dog.set_look_target(self._look_target(dt))
        self.dog.update(dt)                         # 站在转台上时朝向也在这里转（控制器自己的弹簧，dog.turntable_turn）
        self._pose = self.dog.frame()
        hushed = self.playground.active and self.playground.hushed     # 自己溜达过去吃两口：没人跟它玩，嚼、舔水的声音不响
        self.clip_sounds.update(None if hushed else self.dog.player.name, self.dog.player.time,
                                self.dog.action.id if self.dog.action is not None else None, dt)
        self.playground.after_pose()                # 跳的时候按这一帧真实的姿势摆根（脚踩在平面上、身子走的路线不跳）
        self._apply_drag()                          # 拖动：窗口每帧挪一次（widget/input.py）
        if self.playground.active and self.playground.roam.moved:
            self.place_scene(self.playground.roam.wx, self.playground.roam.wy)
        self.closeup.tick(dt)                      # 看细节：放大的这一帧画多大、画在哪（窗口不动；开始、收完那一帧摆一次窗口，画的是这一帧的姿势）、什么时候放狗下转台
        if self._parked and not self._scene_busy():
            self._parked = False
        self.hover.track(dt)
        if not ui_frozen():
            self._fit_height(now, dt)
            if self._wide and not self.showing_scaled:
                self._keep_held_fit()               # 宽着：站起来变高了、跳的片段高了也装得下（只长不缩）
        busy = self._scene_busy()
        if self._wide and self._was_busy and not busy:
            self._moved_timer.start()               # 宽着窗口不挪，狗停下来自己记位置（和平时窗口停稳一样，_after_move）
        self._was_busy = busy
        self._rest_wide(now)                        # 宽着、狗停够了：回到平时的大小
        self._refresh_frame()
        if not self._parked or self._park_swaps < PARK_SWAPS:
            self.view.refresh()
        self._sync_ghost()
        if not self.showing_scaled:
            self._settle_screen()                   # 看细节放大着不换屏：缩回来再说
        self._sync_bubble(dt)
        self._pace(now)

    def _feel(self, dt: float) -> None:
        """兴奋度（widget/excite.py）：按狗这一刻在干什么推一帧，尾巴摇多欢照它。灵动交互开着、关着都走；
        开着时球、跑的那几项由 playground.excite_scene 填。"""
        dog = self.dog
        near = self._pointer_near(dt)
        pg = self.playground
        scene = pg.excite_scene(near) if pg.active else excite.Scene(posture=dog.posture, near_you=near)
        dog.excite.step(dt, excite.target(scene))
        dog.expr.wag = excite.wag(dog.excite.value)

    def _pointer_near(self, dt: float) -> bool:
        """鼠标在狗身边动：离身子正中 temper.GREET_NEAR_DOGS 个身高以内，停着不到调参 look_idle_s 秒。
        离开（或停着）够 excite.GREET_AFTER_S 以后再过来算打招呼：兴奋度加 KICK_GREET，耳朵一抖、身子轻轻弹一下（睡着、被拎着的不算）。"""
        pg = self.playground
        if pg.active:
            pos = pg.cursor()
        else:
            p = QCursor.pos()
            pos = (float(p.x()), float(p.y()))
        moved = pos != self._feel_cursor
        self._feel_cursor = pos
        self._feel_still = 0.0 if moved else self._feel_still + dt
        wx, wy = self.scene_world()
        h = max(1.0, self.dog.rest_top() * self.ppm)
        near = math.hypot(pos[0] - wx, pos[1] - (wy - 0.5 * h)) <= temper.GREET_NEAR_DOGS * h
        here = near and self._feel_still < self.tuning.get("look_idle_s", LOOK_IDLE_S)
        held = pg.active and (pg.roam.lifted or pg.roam.task == "fall")
        if here and self._feel_away >= excite.GREET_AFTER_S and self.dog.posture != "sleeping" and not held:
            self.dog.excite.kick(excite.KICK_GREET)
            self.dog.expr.ear_flick(0.3, 0.55)
            self.dog.expr.bob(0.02, 0.16)
        self._feel_away = 0.0 if here else self._feel_away + dt
        return here

    def dog_tapped(self) -> None:
        """点了狗一下（没拖）：兴奋度加一点（excite.KICK_TAP），尾巴随后多摇一会儿。睡着的不加。"""
        if self.dog.posture != "sleeping":
            self.dog.excite.kick(excite.KICK_TAP)

    def _overlay_needed(self) -> bool:
        """这一帧有没有要叠在狗上面的东西（_overlay 画的那些）：没有的话上面那层就不重画。"""
        hover = getattr(self, "hover", None)       # 启动第一次定大小时操作栏尚未创建
        return hover is not None and not ui_frozen() and (hover.alpha > 0.0 or self.show_metadata)

    def meta_text(self) -> str:
        """元数据行（永远英文，给开发测试看）：姿势 · 在做什么 · 正在播的片段 · 帧率。"""
        dog = self.dog
        doing = dog.action.id if dog.action is not None else dog.phase
        roam = self.playground.roam
        if roam.busy:
            doing = f"{roam.task}:{roam.phase or (roam.leg or {}).get('kind', '')}"
        return f"{dog.posture} · {doing} · {dog.player.name or '-'} · excite {dog.excite.value:.2f} · {self.view.fps:.0f} fps"

    def _overlay(self, p: QPainter) -> None:
        """画在狗上面的：「···」和姿势条、Show metadata 的元数据行。"""
        if ui_frozen() or self._flip_until is not None or self._parked:
            return
        self.hover.draw(p)
        if not self.show_metadata:
            return
        k = self.scale
        overlay.draw_caption(p, self.meta_text(), self.scene_x, self.height() - 8 * k + self.draw_offset[1], max(9, round(CAPTION_PX * k)), 1.0)

    def restart(self) -> None:
        """用同样的命令把自己重新启动一遍（改了代码或配置后用）。"""
        self.settings.sync()
        os.chdir(str(config.ROOT))
        # 打包后的 app：sys.argv[0] 就是可执行文件本身，别再拼一份，不然每重启一次命令行就多一截
        own = bool(sys.argv) and os.path.realpath(sys.argv[0]) == os.path.realpath(sys.executable)
        os.execv(sys.executable, [sys.executable] + (sys.argv[1:] if own else sys.argv))
