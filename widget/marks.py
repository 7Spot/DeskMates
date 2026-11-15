"""两种小图标，分开的两个出处：
- app 图标（app_path / draw_app / app_icon）：猫狗拼成的 DM（形状在 widget/dm_shapes.py，只有这里和关于页的图 widget/about_art.py 用它）。
  设置卡片左上角的圆（card._Lead）、顶部栏名字胶囊写的不是同桌名字时（高级设置这些页，card.TitleBar 的 "app"）、菜单栏图标（tray.menu_icon）
  画的是只有猫狗的那张（app_path）；App 图标文件（tools/make_icon.py）每一张都从 app_icon 取：128 像素以上是整张（猫狗站在水边，天上海鸥、水下一条鱼），
  64 以下只有猫狗。以后换 app 图标只改这里和 dm_shapes。
- 物种图标（species_path / draw_species）：名字胶囊写的是同桌的名字时名字左边那个（狗 = 骨头）。哪一种写在模型包里（pack.json 的 icon，packs.Pack.icon）：
  内置的名字（SPECIES，现在只有 "bone"），或者包里的一张图（按形状涂成胶囊上的颜色）。
两种都是单色的形状，眼睛、鼻子这些是挖空的洞：画的人给颜色（胶囊上黑、圆里是圆的字色）。
形状只拼一次存着（布尔运算拼的，很费），要多大用 QTransform 缩放：card._Flow 每帧宽度都不一样，按宽度重拼会卡。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QTransform

APP = "app"                     # card.TitleBar 里表示「app 图标」的那个键；别的键都是物种图标
APP_W = 14.5                    # 左上角那个 26 的圆里多宽（猫狗的 DM 照这个宽）
SCENE_FROM = 128                # App 图标文件：这么大（像素）以上画整张，以下只画猫狗（小动物缩到这么小只剩一串点）
SPECIES_W = 15.0                # 名字胶囊里的物种图标多宽（骨头和 App 图标一样斜 28°）
BOX_W, BOX_H = round(15 * 1.12) + 2, round(15 * 0.92) + 2   # 名字胶囊里图标占的格子（斜着的骨头的包围盒）
TILT = -28.0
SPECIES = ("bone",)             # 内置的物种图标
_paths: dict[tuple, QPainterPath] = {}
_images: dict[tuple, QImage] = {}
_dm: dict[str, tuple[QPainterPath, QRectF]] = {}   # 拼好的 DM（"small" 只有猫狗、"scene" 整张），按 1024 的画布，和它的包围盒
_pieces: Optional[dict] = None                      # 拆开的几块（app_pieces）


def _bone(width: float) -> QPainterPath:
    from widget.widgets import bone_path
    return bone_path(QPointF(0.0, 0.0), width, tilt=TILT)


def _at(key: tuple, make, center: QPointF) -> QPainterPath:
    path = _paths.get(key)
    if path is None:
        path = _paths[key] = make()
    return QTransform().translate(center.x(), center.y()).map(path)


def _shape(kind: str) -> tuple[QPainterPath, QRectF]:
    """拼好的 DM 和它的包围盒：第一次用到时拼（dm_shapes），之后一直用这一份。"""
    got = _dm.get(kind)
    if got is None:
        from widget import dm_shapes
        path = dm_shapes.small() if kind == "small" else dm_shapes.scene()
        got = _dm[kind] = (path, path.boundingRect())
    return got


def app_pieces() -> dict:
    """拼好的猫狗拆成几块（dm_shapes.pieces：狗、狗脸上的洞、猫、猫脸上的洞、整个；1024 画布的坐标）：关于页的图和进出它的过渡动画用
    （圆里的 D、M 变细成两根线，线描出大的猫狗）。第一次用到时拆（布尔运算），之后一直用这一份。"""
    global _pieces
    if _pieces is None:
        from widget import dm_shapes
        _pieces = dm_shapes.pieces()
    return _pieces


def pieces_ready() -> bool:
    return _pieces is not None


def app_placement(center: QPointF, width: float = APP_W) -> QTransform:
    """只有猫狗的那张缩到 width 宽、正中摆在 center 的变换（app_path 用的就是它）。"""
    return _placed(center, width)


def pieces_placement(center: QPointF, width: float = APP_W) -> QTransform:
    """拆开的几块（app_pieces，还没 fit 的坐标）摆成和 app_path(center, width) 一模一样的变换：过渡动画照它找圆里的 D、M 在哪。"""
    from widget import dm_shapes
    fit = dm_shapes.fitting(app_pieces()["whole"].boundingRect(), *dm_shapes.SMALL_FIT)
    return fit * _placed(center, width)


def _placed(center: QPointF, width: float) -> QTransform:
    """把只有猫狗的那张缩到 width 宽、正中摆在 center。"""
    box = _shape("small")[1]
    k = width / box.width()
    return QTransform().translate(center.x(), center.y()).scale(k, k).translate(-box.center().x(), -box.center().y())


def app_path(center: QPointF, width: float = APP_W) -> QPainterPath:
    """app 图标的形状（中心在 center、宽 width）：只有猫狗的 DM，眼睛、鼻子是洞。"""
    return _placed(center, width).map(_shape("small")[0])


def draw_app(p: QPainter, center: QPointF, color: QColor, width: float = APP_W) -> None:
    """填实的 app 图标（这么小再描边留白，1× 的屏上糊成一团）；洞里露出底下的颜色。
    拼好的那一份按 QTransform 缩着画，不重拼：card._Flow 每帧宽度都不一样。"""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.setTransform(_placed(center, width), True)
    p.drawPath(_shape("small")[0])
    p.restore()


def app_icon(px: int) -> QImage:
    """App 图标文件里 px 像素见方的那一张（tools/make_icon.py）：米白圆角方底、黑边（一半压在方底外面）、没有影子；SCENE_FROM 以上画整张
    （猫狗站在水边，天上一只海鸥、水下一条鱼），以下只画猫狗。狗的眼睛都是实心白点。
    先按 1024 画，再一半一半往下缩（一步缩到 16 会花，像系统给小图标做的那样）。"""
    from widget import dm_shapes, sticker
    ink, paper = QColor(sticker.LIGHT["INK"]), QColor(sticker.LIGHT["PAPER"])
    img = QImage(1024, 1024, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(ink, dm_shapes.TILE_LINE))
    p.setBrush(paper)
    p.drawRoundedRect(dm_shapes.TILE, dm_shapes.RADIUS, dm_shapes.RADIUS)
    p.setPen(Qt.NoPen)
    p.setBrush(ink)
    p.drawPath(_shape("scene" if px >= SCENE_FROM else "small")[0])
    p.end()
    while img.width() // 2 >= px:
        img = img.scaled(img.width() // 2, img.height() // 2, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    if img.width() != px:
        img = img.scaled(px, px, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return img


def species_path(icon: str, center: QPointF, width: float = SPECIES_W) -> Optional[QPainterPath]:
    """内置物种图标的形状；不是内置的（包里的图、没有）返回 None。"""
    if icon == "bone":
        return _at(("bone", round(width, 3)), lambda: _bone(width), center)
    return None


def _image(icon: str, color: QColor, px: int) -> Optional[QImage]:
    key = (icon, color.rgba(), px)
    if key not in _images:
        img = QImage(icon) if Path(icon).is_file() else QImage()
        out = None
        if not img.isNull():
            out = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
            out.fill(Qt.transparent)
            q = QPainter(out)
            q.setRenderHint(QPainter.SmoothPixmapTransform)
            q.drawImage(QRectF(0, 0, px, px), img.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            q.setCompositionMode(QPainter.CompositionMode_SourceIn)
            q.fillRect(out.rect(), color)
            q.end()
        if len(_images) > 32:
            _images.clear()
        _images[key] = out
    return _images[key]


def draw_species(p: QPainter, icon: str, center: QPointF, color: QColor, width: float = SPECIES_W) -> bool:
    """画物种图标；画不出来（没有这个图标、图读不出来）返回 False，调的人换成 app 图标。"""
    path = species_path(icon, center, width)
    if path is not None:
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawPath(path)
        p.restore()
        return True
    if not icon:
        return False
    dpr = max(1.0, p.device().devicePixelRatioF() if p.device() is not None else 1.0)
    img = _image(icon, QColor(color), max(1, round(width * dpr)))
    if img is None:
        return False
    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.drawImage(QRectF(center.x() - width / 2, center.y() - width / 2, width, width), img)
    p.restore()
    return True


def draw(p: QPainter, key: str, center: QPointF, color: QColor, width: Optional[float] = None) -> None:
    """名字胶囊里的图标：key 是 APP 就画 app 图标，别的是物种图标（画不出来退回 app 图标）。"""
    if key != APP and draw_species(p, key, center, color, SPECIES_W if width is None else width):
        return
    draw_app(p, center, color, SPECIES_W if width is None else width)
