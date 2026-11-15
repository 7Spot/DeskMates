#!/bin/zsh
# 打包成 .app，再做成 DMG（打开后把 app 拖进「应用程序」那种）。只在 Apple 芯片 Mac 上验证过；
# 给 Intel Mac 要换 python.org 的通用 Python 重打。
# 用法：zsh tools/build_app.sh             开发版：自己试的（DMG 叫 DeskMates-0.6.0-b45.dmg，版本号旁边显示构建号）；别拿去发
#       zsh tools/build_app.sh --release   发布用的测试版（DMG 名字一样；版本号旁边不显示构建号，只在开发者设置里有）
#       zsh tools/build_app.sh --stable    正式版（自带 --release；DMG 固定叫 DeskMates.dmg：网站的下载链接是固定的）
# 两条线的 app 都叫 DeskMates.app，中文系统里显示「同桌」。
# 在 ~/Library/Caches 里打包和签名：项目在 iCloud 同步的目录里，iCloud 的 File Provider 会给 .app / .framework 这类包目录
# 加 FinderInfo 扩展属性（连 .nosync 目录里的也加），codesign 见了一律拒签。签好、做好 DMG 再把 DMG 和 app 拷回 dist.nosync/。
set -euo pipefail
setopt NULL_GLOB                          # 没有旧的 DMG / zip 时，通配符什么都不匹配也不报错
cd "$(dirname "$0")/.."
PY=.venv.nosync/bin/python
STABLE=0
RELEASE=0
for arg in "$@"; do
  case "$arg" in
    --stable) STABLE=1; RELEASE=1 ;;
    --release) RELEASE=1 ;;
    *) echo "不认识的参数：$arg（只有 --release、--stable）"; exit 2 ;;
  esac
done
BUILD="$HOME/Library/Caches/Deskmate-build"
[ -f models/collie.glb ] || { echo "缺 models/collie.glb：先按 README 把购买的模型导出"; exit 1; }
$PY -m pip install -q -r requirements-dev.txt
$PY tools/make_icon.py
rm -rf "$BUILD"
mkdir -p "$BUILD" dist.nosync
# 构建号每打一次包自动加一：改 config.py 的 BUILD，Info.plist 和设置页的版本行都读它；
# 打包中途失败（或按了 Ctrl-C）就退回原来的号，不白占一个；打好了 config.py 留着新号，要提交。
# --stable 时 config.py 的 CHANNEL 临时改成 stable（检查更新看哪条线跟着变），打完一律改回 pre。
# --release、--stable 时 config.py 的 DEV_BUILD 临时改成 False（版本号旁边不显示构建号），打完一律改回 True。
OLD_BUILD=$(sed -nE 's/^BUILD = ([0-9]+)$/\1/p' config.py)
[ -n "$OLD_BUILD" ] || { echo "config.py 里找不到 BUILD = 数字"; exit 1; }
grep -qE '^DEV_BUILD = True$' config.py || { echo "config.py 里找不到 DEV_BUILD = True（平时就该是 True）"; exit 1; }
NEW_BUILD=$((OLD_BUILD + 1))
VERSION=$(sed -nE 's/^VERSION = "(.*)"$/\1/p' config.py)
PACKED=0
DMG_VERIFY_MOUNT=""
cleanup() {
  if [ -n "$DMG_VERIFY_MOUNT" ]; then
    hdiutil detach "$DMG_VERIFY_MOUNT" >/dev/null 2>&1 || true
  fi
  [ "$PACKED" = 1 ] || sed -i "" -E "s/^BUILD = [0-9]+$/BUILD = $OLD_BUILD/" config.py
  sed -i "" -E 's/^CHANNEL = "stable"$/CHANNEL = "pre"/' config.py
  sed -i "" -E 's/^DEV_BUILD = False$/DEV_BUILD = True/' config.py
}
trap cleanup EXIT
trap 'exit 130' INT TERM
sed -i '' -E "s/^BUILD = [0-9]+$/BUILD = $NEW_BUILD/" config.py
[ "$STABLE" = 1 ] && sed -i '' -E 's/^CHANNEL = "pre"$/CHANNEL = "stable"/' config.py
[ "$RELEASE" = 1 ] && sed -i '' -E 's/^DEV_BUILD = True$/DEV_BUILD = False/' config.py
NAME=$($PY -c 'import config; print(config.APP_NAME)')
if [ "$STABLE" = 1 ]; then
  TAG="v$VERSION"; TITLE="$NAME $VERSION"; DMG="$NAME.dmg"; PRE="不勾"
else
  TAG="v$VERSION-b$NEW_BUILD"; TITLE="$NAME $VERSION ($NEW_BUILD)"; DMG="$NAME-$VERSION-b$NEW_BUILD.dmg"; PRE="勾上"
fi
# iCloud 有时占着旧副本删不掉：重试几次，还不行就只出 DMG，不拷 app 副本
KEEP_COPY=1
for i in 1 2 3 4 5; do rm -rf "dist.nosync/$NAME.app" 2>/dev/null && break; sleep 1; done
[ -e "dist.nosync/$NAME.app" ] && KEEP_COPY=0
$PY -m PyInstaller --noconfirm --clean --log-level WARN --workpath "$BUILD/work" --distpath "$BUILD/dist" packaging/Deskmate.spec
APP="$BUILD/dist/$NAME.app"
# 中文名：Info.plist 里 LSHasLocalizedDisplayName，访达、程序坞、聚焦按系统语言读这两份；app 文件名是 DeskMates.app（config.APP_NAME）
for pair in "en:$NAME" "zh-Hans:同桌"; do
  lproj="$APP/Contents/Resources/${pair%%:*}.lproj"
  mkdir -p "$lproj"
  printf '"CFBundleDisplayName" = "%s";\n"CFBundleName" = "%s";\n' "${pair#*:}" "${pair#*:}" > "$lproj/InfoPlist.strings"
  plutil -convert binary1 "$lproj/InfoPlist.strings"
done
# 冻结后的模块从 Frameworks 取资源；同时验实际 Resources 文件和 PyInstaller 的链接。
$PY - "$APP" <<'PY'
import ssl
import sys
from pathlib import Path
import certifi

bundle = Path(sys.argv[1]).resolve()
expected = Path(certifi.where()).read_bytes()
for folder in ("Resources", "Frameworks"):
    ca = bundle / "Contents" / folder / "certifi" / "cacert.pem"
    if not ca.resolve().is_relative_to(bundle) or ca.read_bytes() != expected:
        raise SystemExit(f"随包根证书缺失或与构建依赖不一致：{ca}")
    context = ssl.create_default_context(cafile=str(ca))
    if context.cert_store_stats()["x509_ca"] == 0:
        raise SystemExit(f"随包根证书不可用：{ca}")
print(f"随包 HTTPS 根证书验证通过：{context.cert_store_stats()['x509_ca']} 个 CA")
PY
# 独立原生卸载助手，主程序退出后仍可通过 NSWorkspace 把 app 移入废纸篓。
# 放在标准 Contents/Helpers，避免 PyInstaller 重排嵌套 .app 的目录。
zsh tools/build_uninstaller.sh "$APP/Contents/Helpers/Deskmate Uninstaller.app"
# 最低系统：Info.plist 写的不能低于包里任何一个程序文件要的系统（写低了老系统上点了没反应、不说原因）。写低了在这里停，列出是哪些文件
$PY tools/check_min_os.py "$APP"
# PyInstaller 自己签一遍可能失败（它只是警告）。清掉 AppleDouble 文件和扩展属性再临时签名；没有开发者账号，无法公证，
# 新 Mac 第一次打开要在"系统设置 → 隐私与安全性"里点"仍要打开"，见 packaging/安装说明.md
dot_clean -m "$APP"
find "$APP" -name '._*' -delete
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
# 换模型的子进程：打包版里备别的模型是从 app 自己的可执行文件起子进程（multiprocessing spawn，app.py 最先 freeze_support）。
# 打完真起一次：不建窗口、不读写设置，只在子进程里备默认那只一遍、打印结果（app.prepare_check）；起不来就停在这，不出 DMG
DESKMATE_PREPARE_CHECK=border_collie "$APP/Contents/MacOS/$NAME"
mkdir -p dist.nosync/helpers
ditto "$APP/Contents/Helpers/Deskmate Uninstaller.app" "dist.nosync/helpers/Deskmate Uninstaller.app"
# DMG：打开后左边 app、右边「应用程序」、中间贴纸风的箭头（packaging/dmg_settings.py，背景 tools/make_dmg_background.py 现画）；卷名对外叫 DeskMates（config.APP_NAME）
$PY tools/make_dmg_background.py "$BUILD/dmg-bg" >/dev/null
$PY -m dmgbuild -s packaging/dmg_settings.py -D app="$APP" -D background="$BUILD/dmg-bg/background.png" "$NAME" "$BUILD/$DMG"
hdiutil verify "$BUILD/$DMG" >/dev/null
# 验最终 DMG 里的 app：封装时也可能写入 FinderInfo（如 hide_extensions），不能只验封装前的源 app。
DMG_VERIFY_MOUNT="$BUILD/verify-dmg"
mkdir -p "$DMG_VERIFY_MOUNT"
hdiutil attach -readonly -nobrowse -mountpoint "$DMG_VERIFY_MOUNT" "$BUILD/$DMG" >/dev/null
codesign --verify --deep --strict "$DMG_VERIFY_MOUNT/$NAME.app"
hdiutil detach "$DMG_VERIFY_MOUNT" >/dev/null
DMG_VERIFY_MOUNT=""
rm -f dist.nosync/Deskmate-*.dmg dist.nosync/Deskmate.dmg "dist.nosync/$NAME"-*.dmg "dist.nosync/$NAME.dmg" 2>/dev/null || true   # 旧名字 Deskmate 的 DMG 也清掉
cp "$BUILD/$DMG" "dist.nosync/$DMG"
PACKED=1                                  # 带新构建号的包已经出来了：这个号算用掉了
if [ "$KEEP_COPY" = 1 ]; then
  ditto "$APP" "dist.nosync/$NAME.app"    # 本机直接跑用的副本；拷回 iCloud 目录后会再被加扩展属性，发给别人请用 DMG
  touch "dist.nosync/$NAME.app"           # 改了图标后 macOS 还按旧缓存显示：改修改时间并重新登记，Dock / 访达才换
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "dist.nosync/$NAME.app" 2>/dev/null || true
  echo; du -sh "dist.nosync/$NAME.app" "dist.nosync/$DMG"
else
  echo "旧副本删不掉（iCloud 占着），这次只出 DMG"; du -sh "dist.nosync/$DMG"
fi
echo "done: $NAME $VERSION ($NEW_BUILD) → dist.nosync/$DMG"
if [ "$RELEASE" != 1 ]; then
  echo "这是开发版（版本号旁边带构建号），只在本机试、别拿去发；发布用 --release（正式版 --stable）重打"
fi
echo "config.py 的构建号改成了 $NEW_BUILD，记得提交"
