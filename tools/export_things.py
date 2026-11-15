"""用 Blender 把买来的狗用品（models/props/src/ 下的 .blend + texture/）导成物件用的 .glb：一件一个文件、一个网格、一张颜色贴图，不带骨架和动画。
画它们的是 widget/thing_art.py（装成渲染器认的模型，和狗同一套三渲二）；哪一款用哪个文件写在 packs/<包>/pack.json 的 thing 里。

运行（五个 .blend 各跑一次；`--` 后面是贴图最长边，不写是 1024；出在 models/props/）：
  for f in Doghouse Dog_bed Food_toy Big_ball Dog_park; do
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --disable-autoexec models/props/src/$f.blend --python tools/export_things.py
  done
--factory-startup --disable-autoexec：下载来的 .blend 当数据看，不跑里面带的脚本。
每件：几个物体合成一个网格（盆 + 粮、跷跷板 + 板）→ 世界变换烤进顶点（栏挂在空物体下面、粮和水是子物体）→ 横向按包围盒居中、底贴地
（平顶狗屋的原点不在正中）→ 新建材质只连颜色贴图 → 导 GLB。贴图比最长边大的先缩小另存再嵌（1.85 倍、2 倍屏上 1024 和 2048 看不出差别，
出图快一倍、文件小一半）。朝哪个角度、放大多少在运行时做，换了不用重导。
狗窝的 .blend 里材质只挂着第一张贴图（蓝垫子、白底爪印圆窝都在这张里）；第二张是另一套配色（灰垫子、橙色圆窝），这里自己指：两款窝各出两个文件。
"""
import os
import sys

import bpy
from mathutils import Matrix, Vector

PARK = "Dog_park_Albedo.png"
TOYS = "Food_Toy_Albedo.png"
GROUPS = {   # .blend 的名字 → {出的文件名: ((物体名…), 贴图文件)}
    "Doghouse": {"house_1": (("Doghouse_1",), "Doghouse_Albedo.png"), "house_2": (("Doghouse_2",), "Doghouse_Albedo.png")},
    "Dog_bed": {"bed_1": (("Bed_1",), "Dog_bed_Albedo_1.png"), "bed_1b": (("Bed_1",), "Dog_bed_Albedo_2.png"),
                "bed_2": (("Bed_2",), "Dog_bed_Albedo_2.png"), "bed_2b": (("Bed_2",), "Dog_bed_Albedo_1.png")},
    "Food_toy": {"bowl_food": (("Bowl_1", "Food_1"), TOYS), "bowl_food_empty": (("Bowl_1",), TOYS),
                 "bowl_water": (("Bowl_2", "Water"), TOYS), "bowl_water_empty": (("Bowl_2",), TOYS),
                 "ball_1": (("Ball_1",), TOYS), "ball_2": (("Ball_2",), TOYS), "ball_3": (("Ball_3",), TOYS),
                 "bone_1": (("Bone_1",), TOYS), "bone_2": (("Bone_2",), TOYS)},
    "Big_ball": {f"big_ball_{i}": ((f"Big_ball_{i}",), "Big_ball_Albedo.png") for i in range(1, 5)},
    "Dog_park": {**{f"barrier_{i}": ((f"Barrier_{i}",), PARK) for i in range(1, 4)},
                 "bench": (("Bench",), PARK), "wheel": (("Wheel",), PARK), "seesaw": (("Swing", "Swing_plank"), PARK),
                 "a_frame": (("Fence_dog",), PARK), "bridge": (("Bridge",), PARK), "poles": (("Ladder",), PARK),
                 "fence": (("Fence",), PARK), "bin": (("Bin",), PARK)},
}

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
max_side = int(args[0]) if args else 1024
src_dir = os.path.dirname(bpy.data.filepath)
out_dir = os.path.dirname(src_dir)                       # models/props/src/x.blend → models/props/
stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
if stem not in GROUPS:
    sys.exit(f"don't know what to export from {stem}.blend")
_images = {}


def albedo(name):
    """颜色贴图：读进来，比 max_side 大就缩小另存一份再读（导出器嵌的是磁盘上那一份）。"""
    if name not in _images:
        img = bpy.data.images.load(os.path.join(src_dir, "texture", name))
        if max(img.size) > max_side:
            k = max_side / max(img.size)
            img.scale(max(1, round(img.size[0] * k)), max(1, round(img.size[1] * k)))
            small = os.path.join(src_dir, "_small", f"{os.path.splitext(name)[0]}_{max_side}.png")
            os.makedirs(os.path.dirname(small), exist_ok=True)
            img.filepath_raw, img.file_format = small, "PNG"
            img.save()
            img = bpy.data.images.load(small)
        _images[name] = img
    return _images[name]


def material_for(name):
    m = bpy.data.materials.new("thing_" + name)
    m.use_nodes = True
    tree = m.node_tree
    bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = albedo(name)
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    return m


for name, (parts, texture) in GROUPS[stem].items():
    copies = []
    for part in parts:
        src = bpy.data.objects[part]
        o = src.copy()
        o.data = src.data.copy()
        bpy.context.scene.collection.objects.link(o)
        o.parent = None
        o.matrix_world = src.matrix_world.copy()
        o.data.transform(o.matrix_world)                 # 世界变换烤进顶点
        o.matrix_world = Matrix.Identity(4)
        copies.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in copies:
        o.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    if len(copies) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    vs = [v.co for v in obj.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    obj.data.transform(Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))   # 横向居中、底贴地（Blender 里 z 朝上）
    obj.data.materials.clear()
    obj.data.materials.append(material_for(texture))
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    path = os.path.join(out_dir, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_texcoords=True,
                              export_normals=True, export_materials="EXPORT", export_image_format="AUTO", export_skins=False,
                              export_animations=False, export_yup=True)
    d = hi - lo
    print(f"EXPORTED {name} size=({d.x:.3f},{d.y:.3f},{d.z:.3f}) verts={len(obj.data.vertices)} {os.path.getsize(path) / 1e3:.0f} KB")
    bpy.data.objects.remove(obj, do_unlink=True)
