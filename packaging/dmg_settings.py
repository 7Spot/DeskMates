# dmgbuild 的配置（tools/build_app.sh 用：dmgbuild -s packaging/dmg_settings.py -D app=<.app 的路径> -D background=<背景.png> Deskmate <输出.dmg>）。
# 打开 DMG：左边是 app，右边是「应用程序」的替身，中间一支圆润的贴纸风箭头，顶上写「拖至 Applications 即可安装」。
# 背景是 tools/make_dmg_background.py 现画的，同名的 @2x.png 给 Retina，dmgbuild 自己合成）。图标位置和背景上的箭头要对上。
import os

application = defines["app"]          # noqa: F821 —— dmgbuild 传进来的
appname = os.path.basename(application)

format = "UDZO"
files = [application]
symlinks = {"Applications": "/Applications"}
# 不用 hide_extensions：它会给签好的 .app 写 FinderInfo，破坏严格签名校验。
# 扩展名是否显示遵循访达设置，不修改 App 的扩展属性。
background = defines.get("background", "builtin-arrow")   # noqa: F821
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
window_rect = ((200, 120), (600, 412))    # 背景 290 高 + 访达的标题栏、标签栏、路径栏、状态栏（全开着，背景比剩下的地方高就出滚动条）
icon_size = 112
text_size = 13
icon_locations = {appname: (165, 165), "Applications": (435, 165)}   # 和 make_dmg_background.py 的 APP_X / FOLDER_X / ICON_Y 一样
