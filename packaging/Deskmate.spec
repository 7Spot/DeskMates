# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配方。用 tools/build_app.sh 跑，产物 dist.nosync/Deskmate.app（名字读 config.APP_NAME；中文系统显示「同桌」，见 build_app.sh）。
资源（模型、贴图、音效）打进包里，config.ROOT 在打包后指向 sys._MEIPASS。
默认以辅助应用身份启动；关闭全局显示或菜单栏不可用时，程序在建窗口前切回普通 Dock 应用。"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).resolve().parent          # SPECPATH 由 PyInstaller 提供：这个 spec 所在的目录
sys.path.insert(0, str(ROOT))
import config                                   # 版本号 / 构建号只写在 config.py（构建号由 tools/build_app.sh 每次打包加一）

datas = [
    (str(ROOT / "models" / "collie.glb"), "models"),
    (str(ROOT / "assets" / "sounds"), "assets/sounds"),
    (str(ROOT / "packs"), "packs"),             # 模型包（声音、署名 CREDITS.md）：widget/packs.py
]
# CA 和许可证随包分发；urllib 不再读取构建机 /opt/homebrew 下的证书。
datas += collect_data_files("certifi") + copy_metadata("certifi")
# 第二只起的模型（萨摩耶）：文件在才带；不在的那个包程序自己不列出来（widget/packs.py 的 pets）。边牧那份必须在，tools/build_app.sh 先查
for glb in ("samoyed.glb",):
    if (ROOT / "models" / glb).is_file():
        datas.append((str(ROOT / "models" / glb), "models"))
# 物件的模型（狗窝、盆、公园里的东西；tools/export_things.py 导到 models/props/）：在的都带上；不在的款程序自己不列（widget/packs.py 的 things）
for glb in sorted((ROOT / "models" / "props").glob("*.glb")):
    datas.append((str(glb), "models/props"))
for pattern in ("Cartoon_BorderCollie_Albedo*.png", "Cartoon_Samoyed_Albedo*.png"):
    for png in sorted((ROOT / "models" / "texture").glob(pattern)):
        datas.append((str(png), "models/texture"))
for qsb in sorted((ROOT / "widget" / "shaders").glob("*.qsb")):      # 着色器（tools/build_shaders.sh 转好的）：widget/render.py 从 config.ROOT/widget/shaders 读
    datas.append((str(qsb), "widget/shaders"))

# 用不到的 Qt 模块，别让它们混进包里
excludes = [f"PySide6.{m}" for m in (
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtQml", "QtQuick", "QtQuickWidgets", "QtQuick3D", "Qt3DCore", "Qt3DRender",
    "QtMultimedia", "QtMultimediaWidgets", "QtCharts", "QtDataVisualization", "QtGraphs", "QtPdf", "QtPdfWidgets", "QtWebView", "QtLocation",
    "QtPositioning", "QtBluetooth", "QtNfc", "QtRemoteObjects", "QtScxml", "QtSensors", "QtSerialPort", "QtSerialBus", "QtSql", "QtTest",
    "QtXml", "QtSvg", "QtSvgWidgets", "QtNetworkAuth", "QtHttpServer", "QtDesigner", "QtHelp", "QtUiTools", "QtPrintSupport", "QtConcurrent",
    "QtDBus", "QtSpatialAudio", "QtTextToSpeech", "QtWebChannel", "QtWebSockets", "QtStateMachine", "QtAsyncio", "QtOpenGLFunctions",
)] + ["tkinter", "unittest", "test", "pydoc", "doctest"]

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name=config.APP_NAME, console=False, icon=str(ROOT / "packaging" / "Deskmate.icns"))
coll = COLLECT(exe, a.binaries, a.datas, name=config.APP_NAME)
app = BUNDLE(
    coll,
    name=f"{config.APP_NAME}.app",
    icon=str(ROOT / "packaging" / "Deskmate.icns"),
    bundle_identifier=config.BUNDLE_ID,
    info_plist={
        "CFBundleName": config.APP_NAME,
        "CFBundleDisplayName": config.APP_NAME,
        "CFBundleShortVersionString": config.VERSION,
        "CFBundleVersion": str(config.BUILD),
        "CFBundleDevelopmentRegion": "en",
        "CFBundleLocalizations": ["en", "zh-Hans"],   # 不声明的话 macOS 只告诉 app「英文」，首次启动跟不了系统的中文
        "LSHasLocalizedDisplayName": True,             # 中文系统里访达、程序坞、聚焦显示「同桌」（zh-Hans.lproj/InfoPlist.strings，打包脚本写）
        "LSUIElement": True,        # 默认全局显示；固定 Dock 图标再次唤起也保留辅助身份，普通模式由 wants_accessory 决定
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "26.0",      # 包里程序文件要的最高那个（PySide6 6.12 的绑定、shiboken6、Homebrew 的 liblzma 要 26.0）；
                                               # 写低了老系统上点了没反应、不说原因。打包时 tools/check_min_os.py 逐个查，写低了就停
        "NSHumanReadableCopyright": config.APP_NAME,
    },
)
