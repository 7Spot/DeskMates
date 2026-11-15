"""生成 macOS 应用图标 packaging/Deskmate.icns（和旁边那张 256 的 Deskmate.png）：米白圆角方底、黑边、没有影子，上面是猫狗拼成的 DM。
128 像素以上（访达、Dock：icns 里 128、256、512、1024 那几张）是整张——猫狗站在水边，天上一只海鸥、水下一条鱼；
64 像素以下（16、32、64 那几张）只有猫狗。每一张都从 widget/marks.py 取（marks.app_icon，app 图标只认它一个出处），这里只管有哪几个尺寸、交给 iconutil（macOS 自带）。
用法：.venv.nosync/bin/python tools/make_icon.py（tools/build_app.sh 打包时自己跑）"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "packaging" / "Deskmate.icns"

from PySide6.QtGui import QGuiApplication                               # noqa: E402

from widget import marks                                                 # noqa: E402

SIZES = ((16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2))


def main() -> None:
    app = QGuiApplication([])   # noqa: F841
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Deskmate.iconset"
        iconset.mkdir()
        for pt, scale in SIZES:
            name = f"icon_{pt}x{pt}" + ("@2x" if scale == 2 else "") + ".png"
            marks.app_icon(pt * scale).save(str(iconset / name))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT)], check=True)
    marks.app_icon(256).save(str(OUT.with_suffix(".png")))
    print("wrote", OUT, f"({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
