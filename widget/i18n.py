"""界面语言：英文 / 中文。tr(英文原文) → 当前语言的文案，查不到就原样返回。

规则：
- 语言行的标题永远是 "Language / 语言"，两个选项永远各写自己的文字（中文 / English），不管当前是哪种语言，
  只看得懂其中一种的人也能找到切换的地方。
- 动作名只写动作不写情绪，中文同样。
- 首次启动跟系统语言：系统是中文就中文，否则英文；用户改过就记在 QSettings。
"""
from __future__ import annotations

LANGS = ("en", "zh")
_current = "en"

ZH: dict[str, str] = {
    # Settings
    "Click to rename": "点击改名",
    "Fine adjustment": "精细调节",
    "Name is too long!": "名字太长啦！",
    "Follow cursor": "鼠标跟随",
    "Watches the pointer from afar": "远远地看着鼠标",
    "Follow options": "跟随选项",
    "Turn with the mouse (standing only)": "随鼠标转身（仅站姿生效）",
    "Dynamic interaction": "灵动交互",
    "Throw the ball for it · lift the dog and throw it": "扔球给它捡 · 拎起来能扔出去",
    "Interaction options": "灵动交互的选项",                     # 灵动交互那一行的调节图标，点开下面几条（prefs.PLAY_OPTIONS）
    "Things": "物件",                                           # 灵动交互选项最下面那一行、页名（widget/things_page.py）
    "Beds & houses": "窝", "Food & water": "吃喝", "Toys": "玩具", "Park": "公园",   # 「物件」页的组名
    "Put everything away": "全部收起",
    "No more {name}": "我不要{name}了",                          # 右键道具弹的那颗胶囊：点了就把这一件收起来
    "Add to the toolbar": "放进道具栏", "Remove from the toolbar": "从道具栏取下",   # 「物件」页每一格右上角的勾选圈（道具栏 = 「···」旁边那一条）
    "The toolbar holds {n} at most": "道具栏最多放 {n} 样",
    "Checked ones show up next to ···, up to {n}": "勾上的会出现在「···」旁边，最多 {n} 样",   # 「物件」页最上面那行灰字
    "Customize": "自定义",                                       # 道具栏最右边那一颗：点了打开「物件」页
    "Window interaction": "窗口交互",                            # 灵动交互的选项
    "When it can, your deskmate hops onto windows": "条件允许时，同桌会跳上窗口",   # 它的悬浮说明（说明文字不带句号）
    "A bit too high": "好像有点高",
    "The small tick on the slider fits hopping onto windows best": "滑杆上的小刻度：最适合跳窗口的大小",
    "Posture": "姿势",
    "Advanced…": "高级设置…", "Advanced": "高级设置",
    "Standing": "站着",
    "Stand": "站", "Sit": "坐", "Lie": "趴", "Sleep": "睡", "Wake up": "醒来",
    "Sitting": "坐着",
    "Lying": "趴着",
    "Show metadata": "显示元数据",
    "Media sounds": "媒体音效", "Interface sounds": "界面音效", "Barks, the ball, landing": "狗叫、球碰撞、落地这些",
    "Buttons, switches and sliders": "按钮、开关、滑杆这些", "Mute": "静音",
    "Posture · activity · clip · fps": "姿势 · 在做什么 · 片段 · 帧率",
    "Size": "大小",
    "Reset": "重置",
    "Hold to go back to the recommended size": "长按回到推荐大小",
    "Coat color": "毛色",
    "Custom": "自定义",
    "Quit": "退出",
    "Back": "返回",
    "Version": "版本",
    "About": "关于",                                            # 「关于」页（设置主页面左上角的 app 图标点进来，widget/about.py）
    "Keep a few little animals that live on your desktop": "养些住在你桌面上的小动物",   # 关于页的一句话
    "Visit GitHub Repo": "访问 GitHub 仓库",                   # 关于页底下的两个链接
    "Visit My Site": "访问我的网站",
    # 卸载、检查更新
    "Uninstall widget": "卸载小组件",
    "Uninstall…": "卸载…",
    "Uninstall": "卸载",
    "Automatic uninstall is available on macOS": "自动卸载仅支持 macOS",
    "The running app could not be verified": "无法确认当前 App，尚未卸载",
    "Move the app to Applications before uninstalling": "请先将 App 移至应用程序，再卸载",
    "The uninstall helper could not start": "卸载助手未能启动，App 与数据均已保留",
    "The uninstall helper is not ready": "卸载助手尚未就绪，App 与数据均已保留",
    "Uninstall cancelled": "已取消卸载",
    "Uninstall could not finish": "卸载未完成",
    "Cancel": "取消",
    "Delete": "删除",
    "Show in Finder": "在访达中显示",
    "{name} uninstalled": "已卸载 {name}",
    "Drag to Applications to replace the old one": "拖至 Applications 替换旧版本",
    "then open the widget again": "然后重新打开小组件",
    "Check for updates": "检查更新",
    "Checking…": "正在检查…",
    "You're up to date": "已是最新版本",
    "Can't connect · Retry": "无法连接到 GitHub，点击重试",
    "Certificate error · Retry": "证书验证失败 · 重试",
    "Connection timed out · Retry": "连接超时 · 重试",
    "GitHub rate limit · Try later": "GitHub 限流 · 稍后重试",
    "No releases yet": "还没有发布版本",
    "More deskmates on the way": "更多同桌在路上",
    "Update available": "发现新版本",
    "Downloading {pct}%": "正在下载 {pct}%",
    "Update ready": "新版本已下载完成",
    "New version downloaded": "新版本已下载完成",                # 顶部栏的新版本胶囊（放不下时换短的说法，SHORTER）
    "Download failed · Retry": "下载没完成，点击重试",
    "Update {version}": "新版本 {version}",
    "New version": "新版本",
    "Released {date} · {size}": "{date}发布 · {size}",
    "No release notes for this version": "这个版本没有写更新说明",
    "Later": "下次再说",
    "Update": "更新",
    "Download complete. Install now?": "下载已完成，现在安装吗",
    "Install": "安装",
    "Downloaded · {size}": "安装包已下载 · {size}",
    "Remove": "删除安装包",

    "Appearance": "外观", "Light": "浅色", "Dark": "深色", "System": "跟随系统",
    # 菜单栏、右键
    "Settings…": "设置…",
    "DeskMates": "同桌",
    "Quit DeskMates": "退出同桌",
    # 动作卡片（随机池也从这里挑）。同样只写动作不写情绪
    "Actions": "动作",
    "Stretch front": "前伸", "Sniff the ground": "嗅地", "Paw up": "抬前爪", "Scratch": "挠痒", "Howl": "仰头叫",
    "Look around": "左右观望", "Bow stretch": "伏地伸展", "Dig": "刨土", "Bark": "叫", "Spin": "转圈",
    "Yawn": "打哈欠", "Side-lie a while": "侧躺一会",
    "Walking": "走路", "Run and jump": "跑跳", "Trotting": "小跑", "Running": "快跑", "Pacing": "踱步", "Backing up": "后退",
    "Turning": "转身", "Hopping": "小跳", "Jumping": "原地跳", "Fetching": "捡回", "Carrying": "叼着",
    "Nose-down walk": "低头走", "Drinking": "喝水", "Eating": "吃东西", "Creeping": "匍匐", "Picking up": "捡起",
    # 开发者设置页（连点五下版本号）
    "Developer": "开发者设置", "Restore defaults": "恢复默认", "Copy values": "复制数值", "Copied": "已复制",
    "Energy": "活跃度", "Cleverness": "聪明程度",
    "Mass (kg)": "质量（公斤）", "Throw distance": "扔出去的幅度", "Bounce off things": "撞到东西弹多少", "Highest jump (body heights)": "一次最多跳几个身高",
    "Leap speed (m/s)": "往前蹬的速度（米 / 秒）", "Squash depth": "duang 压多深", "Squash time (s)": "duang 弹多久（秒）", "Bow depth": "俯身多低",
    "Float amount (m)": "悬空浮多大（米）", "Swing amount": "悬空晃多大",
    "Slide after landing": "落地后滑多远", "Bounces the dog can read ahead": "能看穿几次反弹",
    "Fetch ring size (body heights)": "捡球的圈多大（几个身高）", "Hold in the ring before the dog is ready (s)": "球在圈里停多久狗才准备好（秒）",
    "Chance of a bark when the dog is ready": "准备好时狗叫的概率",
    "Turn when the pointer passes the dog by (body lengths)": "鼠标过去多远才转身（身长）",
    "Wait before turning (s)": "转身前等多久（秒）", "Turn speed": "转身快慢", "Rest after turning (s)": "转完多久能再转（秒）", "Stop watching a still pointer after (s)": "鼠标不动多久不看（秒）", "Low Power Mode: while resting, draw one frame in every": "省电模式：待着时每几帧画一帧", "Low Power Mode": "省电模式", "Light landing below (m)": "小落地：掉多高以内（米）", "Full landing above (m)": "大落地：掉多高以上（米）",
    "Bark volume": "叫声音量", "Lick volume": "舔的音量",
    "Eating volume": "吃东西音量", "Landing volume": "落地音量",
    "Landing bounce": "落地弹回多少", "Slide friction (m/s²)": "滑的时候慢得多快（米 / 秒²）", "Squash on landing": "落地压扁多少", "Spring-back speed": "弹回来多快", "Dust": "扬灰", "Shake nearby things": "震旁边的东西",
    "Floor bounce": "落地弹多少", "Wall bounce": "撞墙弹多少", "Roll distance": "滚多远", "Bounce volume": "碰撞音量", "Pick-up volume": "拿起音量", "Charge-up volume": "充能音量",
    # 选模型
    "Choose your deskmate": "选择同桌",
    # 毛色自定义
    "Custom color": "自定义毛色", "Pattern": "斑纹", "Main": "主色", "Secondary": "副色", "Swap": "对调",
    "Main and secondary trade places": "主色和副色互换", "Eyes": "眼睛", "Default": "默认",
    "Custom…": "自定义…", "Custom": "自定义", "Common colors": "常用颜色",
    "Add a deskmate": "添加同桌", "Add": "添加", "Name": "名字", "Dark areas of the pattern": "斑纹里的深色区", "Light areas of the pattern": "斑纹里的浅色区",
    "The whole coat": "整身的颜色", "The saddle on the back": "背上那一片（选了「背上一片」才有）",
    # 看细节：详情页、自定义毛色页最上面那一块（站 / 坐 / 趴、重置用上面现成的）
    "Zoom": "放大", "Turn": "转动",
    "Drag left or right to turn your deskmate": "左右拖动，桌面上的同桌跟着转",
    "Slide to zoom in · back to normal when you leave this page": "拖着临时放大 · 离开这一页就回去",
    "Hold to go back to 100%": "长按回到 100%",
    # 分组
    "Resting": "休息", "Moving": "移动", "Body": "身体", "Nose & mouth": "鼻子和嘴", "Poses": "姿势",
}

# 放不下时依次换的短说法（顶部栏的新版本胶囊先换短的说法，实在没地方才缩成圆）：英文原文 → 每种语言从长到短，不含 tr 出来的那一句
SHORTER: dict[str, dict[str, tuple[str, ...]]] = {
    "New version downloaded": {"en": ("Update ready", "Update"), "zh": ("新版本已下载", "新版本")},
}

LANGUAGE_ROW = "Language / 语言"          # 永远双语
LANGUAGE_NAMES = {"en": "English", "zh": "中文"}   # 永远各写自己的文字


def current() -> str:
    return _current


def set_language(lang: str) -> None:
    global _current
    _current = lang if lang in LANGS else "en"


def system_default(preferred=()) -> str:
    """系统语言是中文就 zh，否则 en。preferred = 系统的首选语言列表（macOS 直接问出来的，native.mac_languages）：有就按第一个；
    打包的 app 里 Qt 的 QLocale.system() 是 C，中文系统第一次打开也是英文。没有再问 Qt。"""
    if preferred:
        return "zh" if str(preferred[0]).lower().startswith("zh") else "en"
    try:
        from PySide6.QtCore import QLocale
        return "zh" if QLocale.system().language() == QLocale.Language.Chinese else "en"
    except Exception:   # noqa: BLE001
        return "en"


def tr(text: str, **fmt) -> str:
    out = ZH.get(text, text) if _current == "zh" else text
    return out.format(**fmt) if fmt else out


def says(text: str) -> tuple[str, ...]:
    """text 在当前语言里的几种说法，从长到短：第一种就是 tr(text)，后面是登记的短说法（SHORTER）；没登记的只有一种。"""
    return (tr(text), *SHORTER.get(text, {}).get(_current, ()))
