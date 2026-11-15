#!/bin/zsh
# 着色器源码（widget/shaders/*.vert、*.frag，Vulkan 写法的 GLSL）→ 同名的 .qsb（里面带 Metal 和 GLSL 4.1 两份，widget/render.py 读它）。
# 只有改了着色器才要跑；.qsb 入 git、进安装包（packaging/Deskmate.spec）。
# 转换工具 qsb 在 PySide6-Addons 里，只放在本机的 archive/qsb-tool/（pip install --target archive/qsb-tool PySide6-Addons==<和 PySide6 同一版>），
# 不装进开发环境，所以不会进安装包。.venv.nosync/bin/pyside6-qsb 是空壳，别用。
set -euo pipefail
cd "${0:A:h}/.."
QSB=archive/qsb-tool/PySide6/qsb
[[ -x $QSB ]] || { echo "没有 $QSB（见这个脚本开头的说明）" >&2; exit 1; }
SITE=$(.venv.nosync/bin/python -c "import PySide6.QtCore as m, os; print(os.path.dirname(os.path.dirname(m.__file__)))")
export DYLD_FRAMEWORK_PATH="$SITE/PySide6/Qt/lib:$PWD/archive/qsb-tool/PySide6/Qt/lib"
for src in widget/shaders/*.vert widget/shaders/*.frag; do
    $QSB --glsl 410 --msl 12 -o "$src.qsb" "$src"
    echo "$src.qsb"
done
