"""GPU 渲染：蒙皮三渲二 + 接触阴影 + 离线去色淡出。走 Qt 的 RHI（Mac 上底下是 Metal，OpenGL 上屏每半秒卡一下）。
画面不回读 CPU，只有鼠标在窗口范围里时每帧顺手读回鼠标底下的一小块像素看是不是狗（点击范围就是狗）。

每帧（DogRenderer.draw）：
1. 阴影椭圆 → 边长 2 倍的离屏画布（先画，狗会盖住它）
2. 狗：反向外壳轮廓线 + 本体贴图 × 两档明暗 → 同一块画布；道具跟在后面，用同一个深度缓冲
3. 把画布当贴图用线性过滤缩小一半画到目标上（每个像素平均 4 个样本，边缘抗锯齿），顺便去色、变淡。
   颜色一路都是预乘 alpha。不用多重采样：样子要和换 Metal 之前一样。
着色器在 widget/shaders/（Vulkan 写法的 GLSL，改了跑 tools/build_shaders.sh 转成 .qsb）。RHI 的一帧只能在 QRhiWidget 的 initialize() / render() 里画，
所以窗口里的画布和离屏出图都是 QRhiWidget（widget/dogview.py），共用这个类。相机公式和 geometry.project 一致：
模型单位是米，glTF +Z 是狗的正前方，根矩阵转 90° 后朝屏幕右边；相机正交、绕 x 轴俯视 ELEVATION 度。
"""
from __future__ import annotations

import struct
from array import array
from dataclasses import dataclass
from itertools import chain
from typing import Optional

import shiboken6
from PySide6.QtCore import QByteArray, QRect, QSize, Qt
from PySide6.QtGui import (QColor, QImage, QMatrix4x4, QRhi, QRhiBuffer, QRhiColorAttachment, QRhiCommandBuffer, QRhiDepthStencilClearValue,
                           QRhiGraphicsPipeline, QRhiReadbackDescription, QRhiReadbackResult, QRhiRenderBuffer, QRhiRenderTarget, QRhiSampler,
                           QRhiShaderResourceBinding, QRhiShaderStage, QRhiTexture, QRhiTextureRenderTargetDescription, QRhiVertexInputAttribute,
                           QRhiVertexInputBinding, QRhiVertexInputLayout, QRhiViewport, QShader)

import config
from widget.dogctl import Pose
from widget.geometry import Shadow, prepare_bound_vertices, projected_mesh_center, shadow_ellipse, smoothstep
from widget.gltf import Mat4, Model, measured
from widget.props import PropDraw, bought as bought_props, meshes as prop_meshes

SHADER_DIR = config.ROOT / "widget" / "shaders"
MAX_JOINTS = 64
ELEVATION = 10.0          # 俯视角（度）
OUTLINE = 0.0045          # 轮廓线外推（米）
SUPERSAMPLE = 2           # 离屏画布边长倍数，合成时线性过滤缩小 → 4 倍超采样抗锯齿
SUPERSAMPLE_BIG, BIG_SCALE = 1.5, 4.0   # 狗画得比 4 倍大（大小能到屏高的三分之二，电视上 7～8 倍）：画布边长只按 1.5 倍，显卡少画一小半；4 倍以内样子不变
STALE_DIM = 0.4           # 离线时变淡多少：不透明度 1 → 0.6
HIT_ALPHA = 128           # 离屏画布上 alpha 不低于这个才算狗：狗、轮廓线、道具是实心的 255，接触阴影中心才 0.3（77），不算
LIGHT = (-0.5, 1.0, 0.9, 0.0)
# 藏在头里的零件不参与轮廓线，否则会胀出来穿透眼皮和脸颊
INNER_BONES = ("eye.L", "eye.R", "eyelid.L", "eyelid.R", "tongue_1", "tongue_2", "tongue_3", "tongue_4", "mouth", "Mouth.L", "Mouth.R", "nose")
NO_OUTLINE = frozenset({"ball_seam"})     # 贴在别的道具表面上的，不要描边
CLEAR = QColor(0, 0, 0, 0)
SCENE_BYTES = 64 + 64 + 64 * MAX_JOINTS   # dog.vert 的 Scene：uViewProj、uModel、uJoints[64]
ITEM_BYTES = 96                           # prop.vert / prop_tex.vert 的 Item：uModel、uColor、uOutline、uMode（凑整到 16 的倍数）
ITEM_SLOTS = 16                           # 一帧最多画几次道具（每个零件描边、本体各一次）；不够了翻倍


@dataclass(frozen=True)
class Frame:
    """一帧要画的东西。"""
    root: Mat4
    joints: list[Mat4]
    shadow: Optional[Shadow]
    gray: float          # 0..1 去色程度
    opacity: float       # 0..1
    ppm: float           # 像素/米（逻辑像素）
    ground_px: float     # 地面离窗口底部多少逻辑像素
    props: tuple[PropDraw, ...] = ()   # 道具零件（盆 / 骨头 / 球），画在狗之后、同一个深度缓冲里
    offset: tuple[float, float] = (0.0, 0.0)  # 窗口整数坐标之外的绘制偏移（逻辑像素，向右 / 下）
    region: Optional[tuple[int, int, int, int]] = None   # 只画窗口里这一块：(左, 底, 宽, 高)，逻辑像素、从窗口左下角算（宽着的窗口）；
                                                         # 这时 ground_px、offset、阴影都按这一块算（它就像一个平时贴着狗的窗口），离屏画布也只有它那么大


def make_frame(pose: Pose, fade: float, ppm: float, ground_px: float, width_px: float,
               offset: tuple[float, float] = (0.0, 0.0), region: Optional[tuple[int, int, int, int]] = None) -> Frame:
    """控制器的 Pose + 离线渐变量（0 在线 … 1 离线）→ Frame。region 给了：width_px、ground_px、offset 都是那一块的。"""
    amount = smoothstep(fade)
    shadow = shadow_ellipse(pose.footprint, pose.lift, ppm, ground_px, ELEVATION, width_px, offset)
    return Frame(pose.root, pose.joints, shadow, amount, 1.0 - STALE_DIM * amount, ppm, ground_px, tuple(pose.props), offset, region)


def view_proj(width: float, height: float, ppm: float, ground_px: float,
              offset: tuple[float, float] = (0.0, 0.0)) -> QMatrix4x4:
    proj = QMatrix4x4()
    half_w, half_h = width / (2 * ppm), height / (2 * ppm)
    proj.ortho(-half_w, half_w, -half_h, half_h, -10.0, 10.0)
    view = QMatrix4x4()
    view.translate(offset[0] / ppm, -half_h + (ground_px - offset[1]) / ppm, 0.0)
    view.rotate(ELEVATION, 1.0, 0.0, 0.0)
    return proj * view


def qmat(m: Mat4) -> QMatrix4x4:
    """列主序 16 元组 → QMatrix4x4（构造函数按行主序取值）。"""
    return QMatrix4x4(m[0], m[4], m[8], m[12], m[1], m[5], m[9], m[13], m[2], m[6], m[10], m[14], m[3], m[7], m[11], m[15])


def supersample(ppm: float) -> float:
    """狗画成每米 ppm 逻辑像素时离屏画布的边长倍数（SUPERSAMPLE；特别大的狗 SUPERSAMPLE_BIG）。"""
    return SUPERSAMPLE if ppm <= config.PIXELS_PER_METER * BIG_SCALE + 1e-6 else SUPERSAMPLE_BIG


def hit_rect(x: float, y: float, margin: float, width: int, height: int, dpr: float,
             ss: float = SUPERSAMPLE) -> Optional[tuple[int, int, int, int]]:
    """窗口里 (x, y)（逻辑像素，左上角原点）周围 margin 像素那一块，在离屏画布上是哪些像素：(x0, y0, 宽, 高)，y 从画的那一块的底边往上数
    （画布底边对着窗口底边，窗口长高缩回时狗脚不动）。落在画面外返回 None。ss：画布的边长倍数（supersample，和 draw 用的一样）。"""
    s = dpr * ss                                               # 一个逻辑像素在画布上多少个像素
    sw, sh = round(round(width * dpr) * ss), round(round(height * dpr) * ss)
    cx, cy, m = x * s, (height - y) * s, margin * s
    x0, x1 = max(0, int(cx - m)), min(sw, int(cx + m) + 1)
    y0, y1 = max(0, int(cy - m)), min(sh, int(cy + m) + 1)
    if x0 >= x1 or y0 >= y1:
        return None
    return x0, y0, x1 - x0, y1 - y0


def _shader(name: str) -> QShader:
    shader = QShader.fromSerialized(QByteArray((SHADER_DIR / f"{name}.qsb").read_bytes()))
    if not shader.isValid():
        raise RuntimeError(f"shader {name}.qsb can't be read")
    return shader


def _floats(*values: float) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def bound_vertices(model):
    """这个模型的顶点表（合并重复顶点、留位置和蒙皮权重；visual_center 用）：量一次记在模型上，同一个模型的几套渲染器（主画布、每块屏的窗口、
    出图那套）共用，别的模型由 widget/kits.py 在后台先量好。"""
    mesh = model.mesh
    return measured(model, "bound_vertices", lambda: prepare_bound_vertices(mesh.positions, mesh.joints, mesh.weights))


def outline_weights(model) -> array:
    """每个顶点一个 0/1：主要受内部骨头（眼、舌、嘴、鼻）控制的顶点不参与轮廓线（init 传上显卡）。量一次记在模型上。"""
    def make() -> array:
        inner = {i for i, j in enumerate(model.skin_joints) if model.nodes[j].name in INNER_BONES}
        out = array("f")
        J, W = model.mesh.joints, model.mesh.weights
        for v in range(model.mesh.vertex_count):
            k = 4 * v
            best = max(range(4), key=lambda q: W[k + q])
            out.append(0.0 if int(J[k + best]) in inner else 1.0)
        return out
    return measured(model, "outline_weights", make)


class DogRenderer:
    """一块画布（一个 QRhi）配一个。init() 一次，之后每帧 draw()，都要在 QRhiWidget 的 initialize() / render() 里调。"""

    def __init__(self, model: Model):
        self.model = model
        self._bound_vertices = bound_vertices(model)
        self.rhi: Optional[QRhi] = None
        self._rhi_at = 0                               # 这个 QRhi 的地址：Qt 每次给的 Python 对象不是同一个，只能比地址（bound_to）
        self.canvas: Optional[QRhiTexture] = None      # 离屏画布（边长 2 倍）
        self.film: Optional[QRhiTexture] = None        # 离屏出图画到这（shoot），用到才建
        self.coat_image: Optional[QImage] = None       # None = 模型自带的贴图
        self._coat_once: Optional[QImage] = None       # 模型自带的那张已经在后台解好了（look._CoatJobs）：传一次就丢
        self._coat_dirty = False
        self._mesh_dirty = False                       # 换了模型（set_model）、狗的顶点缓冲还是上一个模型的：下一次 draw() 开头换
        self._made_things: list = []                   # 显卡上建的每一样：不归 Python 管，得自己放掉（release）
        self._hit: Optional[QRhiReadbackResult] = None
        self._shot: Optional[QRhiReadbackResult] = None

    def set_model(self, model: Model) -> None:
        """换成另一个模型（换模型不重启）：同一套渲染器原地换——记下新模型和它的顶点表，下一次 draw() 开头新建 6 条顶点缓冲传上去、
        改顶点数和提亮倍数，旧的放掉；离屏画布、深度、管线、采样器、别的缓冲一样不动（放掉旧的新建一套每次多留约 13 MB 显卡内存，量过）。
        毛色贴图不碰（还是上一只的，等 look 换上这只的）：只在狗看不见时调。没 init 过也能调：init() 照 self.model 建。"""
        if model is self.model:
            return
        self.model = model
        self._bound_vertices = bound_vertices(model)
        self._mesh_dirty = True

    def visual_center(self, frame: Frame) -> Optional[tuple[float, float]]:
        """这帧狗本身的投影中心（米）；不碰显卡，阴影和道具不影响中心。"""
        return projected_mesh_center(self._bound_vertices, frame.joints, frame.root, ELEVATION)

    # ---- 建立 ----
    def bound_to(self, rhi: QRhi) -> bool:
        """已经在这个 QRhi 上 init() 过了。"""
        return self.rhi is not None and shiboken6.getCppPointer(rhi)[0] == self._rhi_at

    def init(self, rhi: QRhi, cb: QRhiCommandBuffer) -> None:
        self.release()
        self.rhi, self._rhi_at = rhi, shiboken6.getCppPointer(rhi)[0]
        rub = rhi.nextResourceUpdateBatch()
        self.dog_bufs: list = []
        self._upload_mesh(rub)
        self.prop_bufs: dict[str, tuple[list, int]] = {}     # 道具的小模型（程序生成，widget/props.py）
        for name, mesh in prop_meshes().items():
            self.prop_bufs[name] = ([self._vertex_buffer(rub, mesh.positions), self._vertex_buffer(rub, mesh.normals)], mesh.count)
        self.tex_props: dict[str, tuple] = {}         # 带贴图的道具（买来的盆）：第一次画到时才传上显卡（_tex_prop），不吃喝不占显存
        self.tex_images: dict[int, QRhiTexture] = {}  # 它们的贴图，按图认（QImage.cacheKey；两个盆共用一张）
        self.quad_buf =self._vertex_buffer(rub, array("f", [-1, -1, 1, -1, -1, 1, 1, 1]))   # 铺满画面的四边形，阴影和合成共用

        self.ub_scene = self._uniform_buffer(SCENE_BYTES)
        self.ub_outline, self.ub_body = self._uniform_buffer(32), self._uniform_buffer(32)   # dog 的 Pass：描边、本体各一份，换了模型才变（提亮倍数）
        self._pass_params(rub)
        self.ub_prop_scene = self._uniform_buffer(80)
        self.ub_shadow = self._uniform_buffer(32)
        self.ub_composite = self._uniform_buffer(32)

        mip = QRhiSampler.Linear
        self.coat_sampler = self._made(rhi.newSampler(QRhiSampler.Linear, QRhiSampler.Linear, mip, QRhiSampler.Repeat, QRhiSampler.Repeat))
        self.canvas_sampler = self._made(rhi.newSampler(QRhiSampler.Linear, QRhiSampler.Linear, QRhiSampler.None_,   # 缩小时线性过滤 = 4 个样本取平均
                                                        QRhiSampler.ClampToEdge, QRhiSampler.ClampToEdge))
        # 先按 2×2 建出来：模型没有自带贴图时要传的正好是 2×2 的灰图（_image），大小没变 _upload_coat 就不会再建，往没建过的贴图上传会直接崩
        self.tex = self._made(rhi.newTexture(QRhiTexture.RGBA8, QSize(2, 2), 1, QRhiTexture.MipMapped | QRhiTexture.UsedWithGenerateMips))
        self._upload_coat(rub)

        # 离屏画布：先建一块小的，定下它那一趟的格式，管线照着建；多大等第一帧（_ensure_canvas）。
        # 贴图要先 create() 再问格式（newCompatibleRenderPassDescriptor），不然格式是空的，管线建得出来但什么都画不上
        self.canvas = self._made(rhi.newTexture(QRhiTexture.RGBA8, QSize(64, 64), 1, QRhiTexture.RenderTarget | QRhiTexture.UsedAsTransferSource))
        self.canvas_depth = self._made(rhi.newRenderBuffer(QRhiRenderBuffer.DepthStencil, QSize(64, 64)))
        desc = QRhiTextureRenderTargetDescription(QRhiColorAttachment(self.canvas))
        desc.setDepthStencilBuffer(self.canvas_depth)
        self.canvas_rt = self._keep_alive(rhi.newTextureRenderTarget(desc))
        self.canvas_pass = self._keep_alive(self.canvas_rt.newCompatibleRenderPassDescriptor())
        self.canvas_rt.setRenderPassDescriptor(self.canvas_pass)
        if not self.canvas_rt.create():
            raise RuntimeError("can't create the offscreen canvas")

        vert, frag = QRhiShaderResourceBinding.VertexStage, QRhiShaderResourceBinding.FragmentStage
        both = vert | frag
        binding = QRhiShaderResourceBinding
        self.srb_outline, self.srb_body = (self._bindings([binding.uniformBuffer(0, vert, self.ub_scene), binding.uniformBuffer(1, both, ub),
                                                           binding.sampledTexture(2, frag, self.tex, self.coat_sampler)])
                                           for ub in (self.ub_outline, self.ub_body))
        self.srb_shadow = self._bindings([binding.uniformBuffer(0, frag, self.ub_shadow)])
        self.srb_composite = self._bindings([binding.uniformBuffer(0, frag, self.ub_composite),
                                             binding.sampledTexture(1, frag, self.canvas, self.canvas_sampler)])
        self.item_stride = rhi.ubufAligned(ITEM_BYTES)
        self._item_slots(ITEM_SLOTS)

        f = QRhiVertexInputAttribute
        dog_layout = self._layout([(12, f.Float3), (12, f.Float3), (8, f.Float2), (16, f.Float4), (16, f.Float4), (4, f.Float)])
        prop_layout = self._layout([(12, f.Float3), (12, f.Float3)])
        self.quad_layout = self._layout([(8, f.Float2)])
        dog_v, dog_f, prop_v, prop_f = _shader("dog.vert"), _shader("dog.frag"), _shader("prop.vert"), _shader("prop.frag")
        self.quad_v, self.composite_f = _shader("quad.vert"), _shader("composite.frag")
        rp = self.canvas_pass
        self.ps_shadow = self._pipeline(self.quad_v, _shader("shadow.frag"), self.quad_layout, self.srb_shadow, rp, blend=True, strip=True)
        # 轮廓线：只画背面（外推后的壳），本体会盖住壳的内侧。本体：材质是双面的，不剔除，靠深度测试决定前后
        self.ps_outline = self._pipeline(dog_v, dog_f, dog_layout, self.srb_outline, rp, depth=True, cull=True)
        self.ps_body = self._pipeline(dog_v, dog_f, dog_layout, self.srb_body, rp, depth=True)
        # 道具：和狗同一套画法、同一个深度缓冲（叼在嘴里的被嘴挡住一半才对），淡入淡出靠预乘 alpha 混合
        self.ps_prop_outline = self._pipeline(prop_v, prop_f, prop_layout, self.srb_items[0], rp, depth=True, cull=True, blend=True)
        self.ps_prop_body = self._pipeline(prop_v, prop_f, prop_layout, self.srb_items[0], rp, depth=True, blend=True)
        # 带贴图的道具（买来的盆）：同样的画法多一条贴图坐标、一张贴图。管线这时就建（第一次吃喝时现建要编着色器，会顿一下），
        # 绑定的样子先拿毛色贴图凑一份，真画时用 _tex_prop 给每个盆自己配的
        tex_v, tex_f = _shader("prop_tex.vert"), _shader("prop_tex.frag")
        tex_layout = self._layout([(12, f.Float3), (12, f.Float3), (8, f.Float2)])
        shape = self._bindings([binding.uniformBuffer(0, both, self.ub_prop_scene), binding.uniformBuffer(1, both, self.ub_items, 0, ITEM_BYTES),
                                binding.sampledTexture(2, frag, self.tex, self.coat_sampler)])
        self.ps_tex_outline = self._pipeline(tex_v, tex_f, tex_layout, shape, rp, depth=True, cull=True, blend=True)
        self.ps_tex_body = self._pipeline(tex_v, tex_f, tex_layout, shape, rp, depth=True, blend=True)
        self._composites: dict[tuple, QRhiGraphicsPipeline] = {}    # 合成那一步的管线跟目标的格式走：窗口的画布一种，离屏出图一种
        self._hit = None
        cb.resourceUpdate(rub)

    def _upload_mesh(self, rub) -> None:
        """狗的 6 条顶点缓冲（位置、法线、贴图坐标、关节、权重、描边表）按现在的模型建、传上去；有旧的（换了模型）放掉。"""
        old = self.dog_bufs
        m = self.model.mesh
        self.dog_bufs = [self._vertex_buffer(rub, arr) for arr in (m.positions, m.normals, m.uvs, m.joints, m.weights, self._outline_weights())]
        self.count = m.vertex_count
        for buf in old:
            self._made_things.remove(buf)
            buf.deleteLater()                          # 正在画一帧时 Qt 会等这一帧交完再删
        self._mesh_dirty = False

    def _pass_params(self, rub) -> None:
        """描边、本体两趟的光照、描边宽和提亮倍数（模型包的 brightness，widget/packs.py 写在模型上）。"""
        gain = float(getattr(self.model, "gain", 1.0))
        rub.updateDynamicBuffer(self.ub_outline, 0, struct.pack("4ffif", *LIGHT, OUTLINE, 1, gain))
        rub.updateDynamicBuffer(self.ub_body, 0, struct.pack("4ffif", *LIGHT, 0.0, 0, gain))

    def release(self) -> None:
        """显卡上的东西全放掉：QRhi 要没了（画布换窗口、要销毁）之前必须调，之后要再画得重新 init()。"""
        for thing in reversed(self._made_things):
            thing.deleteLater()                        # 正在画一帧时 Qt 会等这一帧交完再删
        self._made_things.clear()
        self.rhi = self.canvas = self.film = self._hit = self._shot = None
        self._rhi_at = 0

    def _keep_alive(self, thing):
        self._made_things.append(thing)
        return thing

    def _made(self, thing):
        if not thing.create():
            raise RuntimeError(f"can't create {type(thing).__name__}")
        return self._keep_alive(thing)

    def _vertex_buffer(self, rub, arr) -> QRhiBuffer:
        raw = arr.tobytes()
        buf = self._made(self.rhi.newBuffer(QRhiBuffer.Immutable, QRhiBuffer.VertexBuffer, len(raw)))
        rub.uploadStaticBuffer(buf, raw)
        return buf

    def _uniform_buffer(self, size: int) -> QRhiBuffer:
        return self._made(self.rhi.newBuffer(QRhiBuffer.Dynamic, QRhiBuffer.UniformBuffer, size))

    def _bindings(self, bindings: list):
        srb = self.rhi.newShaderResourceBindings()
        srb.setBindings(bindings)
        return self._made(srb)

    @staticmethod
    def _layout(streams: list) -> QRhiVertexInputLayout:
        """每个属性一条自己的缓冲：(每个顶点几字节, 格式)，location 就是第几条。"""
        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(stride) for stride, _ in streams])
        layout.setAttributes([QRhiVertexInputAttribute(i, i, fmt, 0) for i, (_, fmt) in enumerate(streams)])
        return layout

    def _pipeline(self, vert: QShader, frag: QShader, layout, srb, rp, depth: bool = False, cull: bool = False, blend: bool = False,
                  strip: bool = False) -> QRhiGraphicsPipeline:
        ps = self.rhi.newGraphicsPipeline()
        ps.setShaderStages([QRhiShaderStage(QRhiShaderStage.Vertex, vert), QRhiShaderStage(QRhiShaderStage.Fragment, frag)])
        ps.setVertexInputLayout(layout)
        ps.setShaderResourceBindings(srb)
        ps.setRenderPassDescriptor(rp)
        if strip:
            ps.setTopology(QRhiGraphicsPipeline.TriangleStrip)
        if cull:
            ps.setCullMode(QRhiGraphicsPipeline.Front)
        if depth:
            ps.setDepthTest(True)
            ps.setDepthWrite(True)
            ps.setDepthOp(QRhiGraphicsPipeline.Less)
        if blend:                                              # 预乘 alpha：源 × 1 + 目标 × (1 − 源 alpha)
            b = QRhiGraphicsPipeline.TargetBlend()
            b.enable = True
            b.srcColor = b.srcAlpha = QRhiGraphicsPipeline.One
            b.dstColor = b.dstAlpha = QRhiGraphicsPipeline.OneMinusSrcAlpha
            ps.setTargetBlends([b])
        return self._made(ps)

    def _item_slots(self, slots: int) -> None:
        """道具每画一次要一份自己的 Item（一帧里同一块缓冲只能有一份内容），所以开一排格子，每格配一份绑定。"""
        vert, frag = QRhiShaderResourceBinding.VertexStage, QRhiShaderResourceBinding.FragmentStage
        self.ub_items = self._uniform_buffer(slots * self.item_stride)
        self.srb_items = [self._bindings([QRhiShaderResourceBinding.uniformBuffer(0, vert | frag, self.ub_prop_scene),
                                          QRhiShaderResourceBinding.uniformBuffer(1, vert | frag, self.ub_items, i * self.item_stride, ITEM_BYTES)])
                          for i in range(slots)]

    def _image(self) -> QImage:
        """要上传的毛色贴图：换过的用换上的；没换过就用模型自带的那张（后台解好的，或者现解码），传完就丢（2048 解码后 16 MB）。"""
        if self.coat_image is not None:
            return self.coat_image
        once, self._coat_once = self._coat_once, None
        if once is not None and not once.isNull():
            return once
        img = QImage.fromData(self.model.texture_png) if self.model.texture_png else QImage()
        if img.isNull():
            img = QImage(2, 2, QImage.Format_RGBA8888)
            img.fill(Qt.gray)
        return img

    def _upload_coat(self, rub) -> None:
        """不翻：QImage 的第一行就是 v=0，和 glTF 的左上原点一致（已用舌头 / 鼻子的 UV 验证）。"""
        img = self._image().convertToFormat(QImage.Format_RGBA8888)
        if self.tex.pixelSize() != img.size():
            self.tex.setPixelSize(img.size())
            if not self.tex.create():
                raise RuntimeError("can't create the coat texture")
        rub.uploadTexture(self.tex, img)
        rub.generateMips(self.tex)
        self._coat_dirty = False

    def set_coat(self, image: Optional[QImage], once: Optional[QImage] = None) -> None:
        """换毛色贴图（None 回到模型自带的）。下一次 draw() 时传上显卡，init() 之前调也行。
        once：回到模型自带的、而且那张已经解好了（换同桌时后台线程解的）：拿它传，不在主线程再解一遍，传完照样不留。"""
        self.coat_image = image
        self._coat_once = once if image is None else None
        self._coat_dirty = True

    def _outline_weights(self):
        """每个顶点一个 0/1：主要受内部骨头（眼、舌、嘴、鼻）控制的顶点不参与轮廓线。这个模型算一次记着（gltf.Model.measured）。"""
        return outline_weights(self.model)

    def _build_canvas(self, w: int, h: int) -> None:
        size = QSize(w, h)
        self.canvas.setPixelSize(size)
        self.canvas_depth.setPixelSize(size)
        if not (self.canvas.create() and self.canvas_depth.create() and self.canvas_rt.create()):
            raise RuntimeError("can't create the offscreen canvas")

    def _ensure_canvas(self, sw: int, sh: int) -> None:
        """离屏画布放不下才重新分配，高只增不减（按 64 像素取整），画的时候只用左下角 sw × sh 那块（合成时 uScale）。
        窗口跟着悬停 / 起跳长高缩回，高度变了不新建一块（每次新建在 2 倍超采样时 10 到 20 MB）。宽变了（缩放、换屏）才按新的宽重建。"""
        size = self.canvas.pixelSize()
        if size.width() == sw and size.height() >= sh:
            return
        h = max(sh, size.height() if size.width() == sw else 0)
        self._build_canvas(sw, (h + 63) // 64 * 64)

    def _composite(self, target: QRhiRenderTarget) -> QRhiGraphicsPipeline:
        rp = target.renderPassDescriptor()
        key = tuple(rp.serializedFormat())
        ps = self._composites.get(key)
        if ps is None:
            ps = self._composites[key] = self._pipeline(self.quad_v, self.composite_f, self.quad_layout, self.srb_composite, rp, strip=True)
        return ps

    # ---- 每帧 ----
    def draw(self, cb: QRhiCommandBuffer, target: QRhiRenderTarget, width: int, height: int, dpr: float, frame: Frame,
             twice: bool = False, probe: Optional[tuple[int, int, int, int]] = None) -> None:
        """把 frame 画到 target（宽高是逻辑像素，dpr 是设备像素比）。一帧里只能调一次（同一块缓冲一帧只能有一份内容）。
        twice：颜色再乘一遍 alpha（窗口上屏用，见 dogview.TWICE）。probe：hit_rect() 给的那一块，画完读回来，下一帧 hit() 问。"""
        rhi = self.rhi
        size = target.pixelSize()
        pw, ph = size.width(), size.height()
        if frame.region is not None:                       # 只画窗口里狗那一块（宽着的窗口）：画布按那一块大，合成时只盖那一块
            rx, rb, width, height = frame.region
            vx, vb, vw, vh = round(rx * dpr), round(rb * dpr), round(width * dpr), round(height * dpr)
        else:
            vx, vb, vw, vh = 0, 0, pw, ph
        ss = supersample(frame.ppm)
        sw, sh = round(vw * ss), round(vh * ss)
        self._ensure_canvas(sw, sh)
        canvas = self.canvas.pixelSize()
        rub = rhi.nextResourceUpdateBatch()                # 拿了就得交上去（beginPass），所以放在会出错的那几步后面
        if self._mesh_dirty:                               # 换了模型（set_model）：顶点缓冲、提亮倍数这一帧换上
            self._upload_mesh(rub)
            self._pass_params(rub)
        if self._coat_dirty:
            self._upload_coat(rub)
        vp = rhi.clipSpaceCorrMatrix() * view_proj(width, height, frame.ppm, frame.ground_px, frame.offset)
        joints = frame.joints[:MAX_JOINTS]                 # 关节矩阵一次传完（列主序原样）
        rub.updateDynamicBuffer(self.ub_scene, 0, array("f", chain(vp.data(), frame.root, chain.from_iterable(joints))).tobytes())
        s = frame.shadow
        if s is not None:
            k = dpr * ss
            rub.updateDynamicBuffer(self.ub_shadow, 0, _floats(sw, sh, s.cx * k, s.cy * k, max(1.0, s.rx * k), max(1.0, s.ry * k), s.alpha))
        items = self._prop_items(rub, vp, frame.props) if frame.props else ()
        flip = 0.0 if rhi.isYUpInFramebuffer() else 1.0
        rub.updateDynamicBuffer(self.ub_composite, 0, _floats(sw / canvas.width(), sh / canvas.height(), frame.gray, frame.opacity,
                                                                  flip, 1.0 if twice else 0.0))
        port = QRhiViewport(0, 0, sw, sh)
        cb.beginPass(self.canvas_rt, CLEAR, QRhiDepthStencilClearValue(1.0, 0), rub)
        if s is not None:
            cb.setGraphicsPipeline(self.ps_shadow)
            cb.setViewport(port)
            cb.setShaderResources(self.srb_shadow)
            cb.setVertexInput(0, [(self.quad_buf, 0)])
            cb.draw(4)
        dog_input = [(b, 0) for b in self.dog_bufs]
        for ps, srb in ((self.ps_outline, self.srb_outline), (self.ps_body, self.srb_body)):
            cb.setGraphicsPipeline(ps)
            cb.setViewport(port)
            cb.setShaderResources(srb)
            cb.setVertexInput(0, dog_input)
            cb.draw(self.count)
        for ps, srb, bufs, count in items:
            cb.setGraphicsPipeline(ps)
            cb.setViewport(port)
            cb.setShaderResources(srb)
            cb.setVertexInput(0, [(b, 0) for b in bufs])
            cb.draw(count)
        cb.endPass()

        cb.beginPass(target, CLEAR, QRhiDepthStencilClearValue(1.0, 0))
        cb.setGraphicsPipeline(self._composite(target))
        cb.setViewport(QRhiViewport(vx, vb, vw, vh))           # QRhi 的视口从左下角算
        cb.setShaderResources(self.srb_composite)
        cb.setVertexInput(0, [(self.quad_buf, 0)])
        cb.draw(4)
        cb.endPass()
        self._hit = None
        if probe is not None:
            self._read_back(cb, probe, sw, sh, canvas.height())

    def _prop_items(self, rub, vp: QMatrix4x4, props) -> list[tuple]:
        """道具这一帧要画的每一次：(管线, 绑定, 顶点缓冲, 顶点数)，顺序就是画的顺序；每次的 Item 顺手传上去。
        程序画的（盆、骨头、球）共用一排格子；带贴图的（买来的盆）各用自己的两格（一帧最多画一次：描边、本体）。"""
        rub.updateDynamicBuffer(self.ub_prop_scene, 0, array("f", chain(vp.data(), LIGHT)).tobytes())
        need = sum(1 if d.mesh in NO_OUTLINE else 2 for d in props if d.mesh in self.prop_bufs)
        if need > len(self.srb_items):
            self._item_slots(max(need, 2 * len(self.srb_items)))
        out, slot, done = [], 0, set()
        for d in props:
            tex = None
            if d.mesh not in self.prop_bufs:
                tex = self._tex_prop(rub, d.mesh) if d.mesh not in done else None
                if tex is None:
                    continue                                       # 不认识的、这一帧已经画过的（props 那头一次只有一个盆）
                done.add(d.mesh)
            for k, outline in enumerate((True, False) if d.mesh not in NO_OUTLINE else (False,)):
                data = struct.pack("16f4ffi", *d.matrix, *d.color, d.alpha, OUTLINE if outline else 0.0, 1 if outline else 0)
                if tex is None:
                    rub.updateDynamicBuffer(self.ub_items, slot * self.item_stride, data)
                    out.append((self.ps_prop_outline if outline else self.ps_prop_body, self.srb_items[slot]) + self.prop_bufs[d.mesh])
                    slot += 1
                else:
                    bufs, count, ub, srbs = tex
                    rub.updateDynamicBuffer(ub, k * self.item_stride, data)
                    out.append((self.ps_tex_outline if outline else self.ps_tex_body, srbs[k], bufs, count))
        return out

    def _tex_prop(self, rub, name: str) -> Optional[tuple]:
        """带贴图的道具第一次画到：顶点、贴图传上显卡，配自己的两格 Item（描边、本体）和绑定。贴图按图认，两个盆共用一张。
        返回 (顶点缓冲, 顶点数, Item 缓冲, 两份绑定)；props 没有这个名字（买来的模型不在）返回 None。"""
        got = self.tex_props.get(name)
        if got is not None:
            return got
        mesh = bought_props().get(name)
        if mesh is None:
            return None
        img = mesh.image
        tex = self.tex_images.get(img.cacheKey())
        if tex is None:
            tex = self._made(self.rhi.newTexture(QRhiTexture.RGBA8, img.size(), 1, QRhiTexture.MipMapped | QRhiTexture.UsedWithGenerateMips))
            rub.uploadTexture(tex, img)                             # 不翻：QImage 第一行就是 v=0（和毛色贴图一样）
            rub.generateMips(tex)
            self.tex_images[img.cacheKey()] = tex
        bufs = [self._vertex_buffer(rub, arr) for arr in (mesh.positions, mesh.normals, mesh.uvs)]
        ub = self._uniform_buffer(2 * self.item_stride)
        vert, frag = QRhiShaderResourceBinding.VertexStage, QRhiShaderResourceBinding.FragmentStage
        binding = QRhiShaderResourceBinding
        srbs = [self._bindings([binding.uniformBuffer(0, vert | frag, self.ub_prop_scene), binding.uniformBuffer(1, vert | frag, ub, k * self.item_stride, ITEM_BYTES),
                                binding.sampledTexture(2, frag, tex, self.coat_sampler)]) for k in range(2)]
        got = self.tex_props[name] = (bufs, mesh.count, ub, srbs)
        return got

    # ---- 离屏出图 ----
    def shoot(self, cb: QRhiCommandBuffer, width: int, height: int, dpr: float, frame: Frame) -> None:
        """把 frame 画到自己的一块贴图上再读回（画面 width × height 逻辑像素，图是它的 dpr 倍）。这一帧交上去以后 shot() 拿图。"""
        size = QSize(max(1, round(width * dpr)), max(1, round(height * dpr)))
        if self.film is None:
            self.film = self._made(self.rhi.newTexture(QRhiTexture.RGBA8, size, 1, QRhiTexture.RenderTarget | QRhiTexture.UsedAsTransferSource))
            self.film_rt = self._keep_alive(self.rhi.newTextureRenderTarget(QRhiTextureRenderTargetDescription(QRhiColorAttachment(self.film))))
            self.film_rt.setRenderPassDescriptor(self._keep_alive(self.film_rt.newCompatibleRenderPassDescriptor()))
            if not self.film_rt.create():
                raise RuntimeError("can't create the offscreen target")
        elif self.film.pixelSize() != size:
            self.film.setPixelSize(size)
            if not (self.film.create() and self.film_rt.create()):
                raise RuntimeError("can't create the offscreen target")
        self.draw(cb, self.film_rt, width, height, dpr, frame)
        self._shot = QRhiReadbackResult()
        batch = self.rhi.nextResourceUpdateBatch()
        batch.readBackTexture(QRhiReadbackDescription(self.film), self._shot)
        cb.resourceUpdate(batch)

    def shot(self) -> QImage:
        """shoot() 那一帧读回来的图（预乘 alpha）；没有就是空图。"""
        got, self._shot = self._shot, None
        if got is None or got.data.isEmpty():
            return QImage()
        size, raw = got.pixelSize, bytes(got.data)                             # raw 得活到下一行转完：QImage 只是借用这块字节
        img = QImage(raw, size.width(), size.height(), 4 * size.width(), QImage.Format_RGBA8888_Premultiplied)
        img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)          # 转完字节是它自己的了
        return img if not self.rhi.isYUpInFramebuffer() else img.mirrored(False, True)

    # ---- 点击范围就是狗 ----
    def _read_back(self, cb, rect: tuple[int, int, int, int], sw: int, sh: int, canvas_h: int) -> None:
        x0, y0, w, h = rect
        w, h = min(w, sw - x0), min(h, sh - y0)
        if w <= 0 or h <= 0:
            return
        top = y0 if self.rhi.isYUpInFramebuffer() else canvas_h - y0 - h     # Metal 的贴图第一行在上面，画的那一块贴着底
        what = QRhiReadbackDescription(self.canvas)
        what.setRect(QRect(x0, top, w, h))
        self._hit = QRhiReadbackResult()                   # 这一帧交上去以后里面才有数；得留着引用
        batch = self.rhi.nextResourceUpdateBatch()
        batch.readBackTexture(what, self._hit)
        cb.resourceUpdate(batch)

    def hit(self) -> Optional[bool]:
        """上一次 draw(probe=…) 读回来的那一块里有没有狗：狗、轮廓线、道具算，接触阴影不算（HIT_ALPHA）。没读过返回 None。"""
        if self._hit is None:
            return None
        data = bytes(self._hit.data)
        return bool(data) and max(data[3::4]) >= HIT_ALPHA
