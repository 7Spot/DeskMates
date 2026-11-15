"""同桌 DeskMates：可调参数。要改数值改这里，不改别处。"""
import sys
from pathlib import Path

# 打包成 .app 后（PyInstaller）资源在 sys._MEIPASS 下；平时就是这个文件所在的目录。
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# 名字：英文 DeskMates，中文「同桌」。app 文件叫 DeskMates.app，中文系统的访达、程序坞里显示「同桌」
# （tools/build_app.sh 写进 zh-Hans.lproj/InfoPlist.strings）；界面里的中文名走 i18n 的 tr("DeskMates")。
# 存东西的地方（设置、日志 ~/Library/Logs/Deskmate.log、缓存、卸载器认的这些路径）还用 DATA_NAME：改名只改显示的，改了它老用户的东西就丢在原地、卸载也清不到。
APP_NAME = "DeskMates"
DATA_NAME = "Deskmate"
BUNDLE_ID = "com.deskmate.companion"
# 版本号 / 构建号：设置的高级设置页最底下显示「版本 0.6.0 (45)」（发布版不带构建号，见 DEV_BUILD），打包配方 packaging/Deskmate.spec 从这里填 Info.plist。
# 构建号由 tools/build_app.sh 每打一次包自动加一（打包失败退回），
# 别手改。版本号要升时手改。
# 发布线：pre = 测试版（测试版、正式版的更新都收）；stable = 正式版（只收正式版）。打包脚本 --stable 时改成 stable，打完退回。
CHANNEL = "pre"
VERSION = "1.0.0"
BUILD = 80
# 开发版：True = 高级设置最底下「版本 0.6.0 (66)」带构建号（直接跑源码、平时 zsh tools/build_app.sh 打的包）；
# 发布用的包（--release、--stable）打包时改成 False：版本号旁边不显示构建号，只在开发者设置页（连点五下版本号）最底下有。别手改，打完脚本改回 True。
DEV_BUILD = True
# 检查更新去哪个 GitHub 仓库找新版本（"owner/name"，公开仓库；None = 设置里不显示「检查更新」、不联网）。
# 每个软件一个自己的发布仓库。
UPDATE_REPO = "7Spot/DeskMates"
# 「关于」页最底下的两个链接：GitHub 仓库、个人网页。填完整网址（https://…）就能点；空着 = 字更淡、点不了
GITHUB_URL = "https://github.com/7Spot/DeskMates"
HOMEPAGE_URL = "https://7spot.github.io"

# 动画帧率：跟着窗口所在屏幕的刷新率走（固定 17 毫秒一帧在 85 赫兹的宽屏上一帧停一次刷新、一帧停两次，快速转头时一跛一跛）。
# 每 k 次刷新画一帧，k 取让帧率不超过 ANIM_MAX_FPS 的最小整数（120 赫兹 → 60 帧、85 → 85）；读不到刷新率按 ANIM_FPS。
# 上限维持 100、不降到 60（接外接显示器的 Mac 一般性能都够；降到 60 的话 85 赫兹只剩 42.5 帧）。
ANIM_FPS = 60
ANIM_MAX_FPS = 100
# 待着时少画：每几帧画一帧在开发者设置页（idle_skip），再少也不低于 IDLE_MIN_FPS（120 赫兹的屏平时 60 帧，最多隔一帧画）；
# 有动静马上回满帧（widget/window.py 的 _pace）。
IDLE_MIN_FPS = 24

# 窗口尺寸（逻辑像素）和比例尺。模型单位是米，狗长约 1.1 米、高约 0.63 米。
# 宽度包住狗在任意朝向下的范围（关节 x ±0.62 米加边距）。高度平时只包住站着的狗（待机片段最高 0.68 米 + 耳朵 0.11 米），
# 播更高的片段或起跳时窗口临时向上长高（底边不动），落地后缩回；最高不超过 WINDOW_MAX_HEIGHT，顶到屏幕就不再长。
# 底部留 GROUND_Y 像素给阴影和脚下那行小字。
WINDOW_WIDTH = 352
WINDOW_HEIGHT = 240
WINDOW_MAX_HEIGHT = 520
GROUND_Y = 46
PIXELS_PER_METER = 240

# 元数据行（姿势 · 在做什么 · 片段 · fps，给开发测试看）默认不显示；Settings 里的 Show metadata 打开，记在 QSettings。
SHOW_METADATA_DEFAULT = False

# 鼠标跟随（狗的头和眼睛看向鼠标）默认关；Settings 里开，记在 QSettings。
FOLLOW_CURSOR_DEFAULT = False

# 毛色：模型自带 4 套 Albedo 贴图。第 1 套就是 collie.glb 里嵌的那张，其余从 models/texture/ 读（购买内容，不入 git）。
COAT_DIR = ROOT / "models" / "texture"
COATS = tuple(f"Cartoon_BorderCollie_Albedo{i}.png" for i in (1, 2, 3, 4))

# 狗的模型：购买的 Cartoon Dog - Border Collie，用 tools/export_glb.py 从 Blender 导出
MODEL_PATH = ROOT / "models" / "collie.glb"

# 第一次启动（没记过位置）放在主屏的哪：窗口中心 x、底边占屏的比例（新装的默认在右下）
DEFAULT_POS = (0.874, 0.976)            # MacBook 屏幕右下，贴近底边
