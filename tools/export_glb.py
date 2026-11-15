"""用 Blender 把 models/ 下买来的 .blend 导成 .glb，带骨架、蒙皮、全部动画和颜色贴图。两只狗同一个作者、同一套骨架和动作，共用这一份。

运行（`--` 后面是输出文件名，写在 .blend 旁边；不写是 collie.glb）：
  边牧：/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --disable-autoexec models/Cartoon_BorderCollie_anim_IP.blend --python tools/export_glb.py
  萨摩耶：/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --disable-autoexec models/Cartoon_Samoyed_Anim_IP.blend --python tools/export_glb.py -- samoyed.glb
--factory-startup --disable-autoexec：下载来的 .blend 当数据看，不跑里面带的脚本。
只导 Albedo1 贴图；法线、粗糙度、AO 三渲二用不上。打架、受伤、死亡、排泄、游泳这些动画不导。名字以 _LowPoly 结尾的网格不导（widget/gltf.py 只认一个网格）。
"""
import os
import re
import sys

import bpy

SKIP = re.compile(r"^(Attack|Death|Hit|Defecate|Pissing|Swim|Fall|A_Pose)")

blend_dir = os.path.dirname(bpy.data.filepath)
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = os.path.join(blend_dir, os.path.basename(args[0]) if args else "collie.glb")

# 低模（萨摩耶的 .blend 里多带一个）：删掉，只留主网格
for o in list(bpy.data.objects):
    if o.type == "MESH" and o.name.endswith("_LowPoly"):
        print("drop mesh", o.name)
        bpy.data.objects.remove(o, do_unlink=True)

# 贴图路径：.blend 里写的是 //../texture/，我们把贴图放在 models/texture/ 下
for img in bpy.data.images:
    p = os.path.join(blend_dir, "texture", os.path.basename(img.filepath))
    if os.path.isfile(p):
        img.filepath = p
        img.reload()
        print("image ->", p, img.size[:])

# 材质：.blend 里没连贴图节点（作者的说明图要求手动连），这里连上 Albedo1 → Base Color
albedo = next((i for i in bpy.data.images if "Albedo1" in i.name), None)
for m in bpy.data.materials:
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    out_node = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    if out_node is None:
        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
    for n in [n for n in nt.nodes if n.type in ("TEX_IMAGE", "NORMAL_MAP")]:      # 萨摩耶的材质自带法线、粗糙度、金属度的节点：拿掉，只留颜色
        nt.nodes.remove(n)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = albedo
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    print("material", m.name, "-> albedo", albedo.name if albedo else None)

# 不导的动作：直接删掉，导出器就不会带上
for a in list(bpy.data.actions):
    if SKIP.match(a.name):
        bpy.data.actions.remove(a)
print("actions kept:", len(bpy.data.actions))

bpy.ops.export_scene.gltf(
    filepath=out,
    export_format="GLB",
    export_apply=True,
    export_texcoords=True,
    export_normals=True,
    export_materials="EXPORT",
    export_image_format="AUTO",
    export_skins=True,
    export_animations=True,
    export_animation_mode="ACTIONS",
    export_force_sampling=True,
    export_frame_step=1,
    export_optimize_animation_size=True,
    export_anim_single_armature=True,
    export_yup=True,
)
print("exported", out, round(os.path.getsize(out) / 1e6, 1), "MB")
