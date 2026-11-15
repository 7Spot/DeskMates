# 同桌 DeskMates

住在 Mac 桌面上的小狗。可以扔球给它捡，可以把它拎起来扔出去，它会自己跳上旁边的窗口去追球；也可以摆上狗窝、饭盆。现在有边牧和萨摩耶两只。

## 下载

直接用的话，到右边的 **Releases** 下载 DMG，打开后把 DeskMates 拖进「应用程序」。

- 要求：Apple 芯片的 Mac（M1 及以后），macOS 26 以上。
- 这个 app 没有经过 Apple 公证，第一次打开会被拦下，怎么打开见 [安装说明](packaging/安装说明.md)。

## 为什么仓库里没有模型

狗和物件（狗窝、饭盆这些）的 3D 模型是付费购买的素材，版权属于原作者，不能和源代码一起公开，所以仓库里没有模型文件。
Releases 里的 DMG 是打包好的 app，下载就能用。想从源代码运行，需要自己买到同样的模型，再按下面的步骤导出。

- 边牧：CGTrader 上的 **Cartoon Dog - Border Collie**。
- 萨摩耶：CGTrader 上的 **Cartoon Dog - Samoyed**。
- 没有边牧的模型，程序启动不了；萨摩耶、物件的模型缺了，只是那几样不出现。

## 从源代码运行

需要 Python 3.11 以上（打包用的是 3.13）：

```bash
python3 -m venv .venv.nosync
source .venv.nosync/bin/activate
pip install -r requirements.txt
python app.py
```

- 项目放在 iCloud 同步的文件夹（比如「文稿」）里时，venv 的名字要以 `.nosync` 结尾，不然 Qt 找不到自己的插件，一启动就崩。
- 模型放进 `models/`，用 Blender 导出（`--factory-startup --disable-autoexec`：只把 .blend 当数据读，不跑里面带的脚本）：
  - 边牧：`Cartoon_BorderCollie_anim_IP.blend` 和 `texture/` 放进 `models/`，导出 `models/collie.glb`：

    ```bash
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --disable-autoexec models/Cartoon_BorderCollie_anim_IP.blend --python tools/export_glb.py
    ```
  - 萨摩耶：`Cartoon_Samoyed_Anim_IP.blend` 放进 `models/`，四张 `Cartoon_Samoyed_Albedo*.png` 放进 `models/texture/`，导出 `models/samoyed.glb`：

    ```bash
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --disable-autoexec models/Cartoon_Samoyed_Anim_IP.blend --python tools/export_glb.py -- samoyed.glb
    ```
  - 物件：买来的五个 `.blend` 和它们的 `texture/` 放进 `models/props/src/`，用 `tools/export_things.py` 导出到 `models/props/`（用法写在这个脚本开头）。

## 测试

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
```

没有模型时，要用模型的那些测试会跳过。

## 打包

```bash
pip install -r requirements-dev.txt
zsh tools/build_app.sh
```

出来的是 `dist.nosync/DeskMates.app` 和 DMG。`--release` 打发布用的测试版，`--stable` 打正式版。只在 Apple 芯片的 Mac 上打过；要给 Intel Mac 用，得换成 python.org 的通用版 Python 重打。
改了着色器（`widget/shaders/`）才要先跑 `tools/build_shaders.sh`，用法写在脚本开头。

## 代码在哪

- `app.py`：入口；`config.py`：名字、版本、路径。
- `widget/`：狗、界面和交互，每个文件开头写着它管什么。
- `packs/`：模型包（每只狗、每类物件一个文件夹，加新模型不用改代码），写法见 [packs/README.md](packs/README.md)。
- `tools/`：打包、导模型、出图这些开发用的脚本。
- `tests/`：单元测试。

## 许可证

代码以 [GNU GPL v3](LICENSE) 发布，Copyright © 2026 JUN7。
模型不在仓库里；声音的来源和各自的授权见 [packs/CREDITS.md](packs/CREDITS.md)。
