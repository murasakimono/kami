"""3D Kami karakteri (Blender, tamamen kodla). Calistir:
  blender -b --factory-startup -P design/blender/kami_3d.py -- <cikti_klasoru> [durum ...] [--anim] [--size 512]
Durumlar: idle down speed done error. Her durum icin <durum>.png (seffaf zemin); --anim ile 48 karelik dongu (PNG dizisi).
Tasarim 2D maskota uyar: koyu mor sutun govde, krom serit, yanardoner boynuzlar ve dikenler, tek goz,
zumrut alevli kemer + elmas, parlayan zumrut zikzak etek.
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(HERE, "..", "..", "app", "ui", "web"))
PURPLE = (0.30, 0.10, 0.62)
EMERALD = (0.10, 1.0, 0.55)
W, D, H = 1.0, 0.78, 2.7          # govde genislik / derinlik / yukseklik
HEM = 0.32                         # etek zikzak derinligi
TEETH = 7                          # on yuzde zikzak dis sayisi

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.join(HERE, "out")
ANIM = "--anim" in argv
SIZE = int(argv[argv.index("--size") + 1]) if "--size" in argv else 512
STATES = [a for a in argv[1:] if a in ("idle", "down", "speed", "done", "error")] or ["idle", "down", "speed", "done", "error"]


def lin(c):
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---------------- malzemeler ----------------
def principled(name, color, rough=0.5, metal=0.0, film=0.0, emit=None, es=0.0, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*lin(color), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if film and "Thin Film Thickness" in b.inputs:   # yanardoner krom (Blender 4.2+)
        b.inputs["Thin Film Thickness"].default_value = film
        b.inputs["Thin Film IOR"].default_value = 1.9
    if coat and "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    if emit:
        b.inputs["Emission Color"].default_value = (*lin(emit), 1)
        b.inputs["Emission Strength"].default_value = es
    return m, b


def mat_body():
    """Karbon dokulu koyu mor kumas + UV'ye gore zikzak etekte zumrut isik (geometriyle ayni formul)."""
    m, b = principled("Govde", (0.075, 0.03, 0.14), 0.62, coat=0.15)
    nt, L = m.node_tree, m.node_tree.links
    uvn = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L.new(uvn.outputs["UV"], sep.inputs[0])
    # karbon: ince kare desen
    chk = nt.nodes.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 140
    chk.inputs["Color1"].default_value = (*lin((0.085, 0.035, 0.16)), 1)
    chk.inputs["Color2"].default_value = (*lin((0.05, 0.02, 0.10)), 1)
    L.new(uvn.outputs["UV"], chk.inputs["Vector"])
    # zikzak: tri(u*TEETH*4) -> etek cizgisi; v (yukseklik 0..1) cizginin hemen ustundeyse isik
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = TEETH * 4
    L.new(sep.outputs["X"], mul.inputs[0])
    pp = nt.nodes.new("ShaderNodeMath"); pp.operation = "PINGPONG"; pp.inputs[1].default_value = 1.0
    L.new(mul.outputs[0], pp.inputs[0])
    edge = nt.nodes.new("ShaderNodeMath"); edge.operation = "MULTIPLY_ADD"
    edge.inputs[1].default_value = HEM / H; edge.inputs[2].default_value = 0.0
    L.new(pp.outputs[0], edge.inputs[0])
    dist = nt.nodes.new("ShaderNodeMath"); dist.operation = "SUBTRACT"
    L.new(sep.outputs["Y"], dist.inputs[0]); L.new(edge.outputs[0], dist.inputs[1])
    glow = nt.nodes.new("ShaderNodeMapRange")
    glow.inputs["From Min"].default_value = 0.0; glow.inputs["From Max"].default_value = 0.045
    glow.inputs["To Min"].default_value = 1.0; glow.inputs["To Max"].default_value = 0.0
    L.new(dist.outputs[0], glow.inputs["Value"])
    L.new(chk.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Emission Color"].default_value = (*lin(EMERALD), 1)
    sm = nt.nodes.new("ShaderNodeMath"); sm.operation = "MULTIPLY"; sm.inputs[1].default_value = 7.0
    L.new(glow.outputs["Result"], sm.inputs[0])
    L.new(sm.outputs[0], b.inputs["Emission Strength"])
    return m


def mat_belt():
    """Koyu kemer, uzerinde zumrut 'alev' deseni (dalgali gurultu esigi)."""
    m, b = principled("Kemer", (0.03, 0.02, 0.05), 0.4, 0.3)
    nt, L = m.node_tree, m.node_tree.links
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (5.0, 5.0, 14.0)
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave"); wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 1.2; wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 3.0
    L.new(mp.outputs[0], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.62; ramp.color_ramp.elements[1].position = 0.7
    L.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    b.inputs["Emission Color"].default_value = (*lin(EMERALD), 1)
    sm = nt.nodes.new("ShaderNodeMath"); sm.operation = "MULTIPLY"; sm.inputs[1].default_value = 5.0
    L.new(ramp.outputs["Color"], sm.inputs[0])
    L.new(sm.outputs[0], b.inputs["Emission Strength"])
    return m


def mat_iris(red=False):
    m, b = principled("Iris_kirmizi" if red else "Iris", (1, 1, 1), 0.08, coat=1.0)
    nt, L = m.node_tree, m.node_tree.links
    tex = nt.nodes.new("ShaderNodeTexImage")
    img = os.path.join(WEB, "eye", "iris.webp")
    tex.image = bpy.data.images.load(img)
    tex.extension = "CLIP"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")   # gozun on yuzune duz yansit (nesne X,Z -> UV)
    mp.inputs["Location"].default_value = (0.5, 0.5, 0)
    mp.inputs["Scale"].default_value = (2.4, 2.4, 1)
    mp.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    L.new(mp.outputs[0], tex.inputs["Vector"])
    white = (*lin((0.92, 0.9, 0.95)), 1)
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs["A"].default_value = white
    L.new(tex.outputs["Alpha"], mix.inputs["Factor"])
    col = tex.outputs["Color"]
    if red:   # yesil irisi kirmiziya cevir
        hue = nt.nodes.new("ShaderNodeHueSaturation"); hue.inputs["Hue"].default_value = 0.17
        hue.inputs["Saturation"].default_value = 1.3
        L.new(col, hue.inputs["Color"]); col = hue.outputs["Color"]
    L.new(col, mix.inputs["B"])
    L.new(mix.outputs["Result"], b.inputs["Base Color"])
    L.new(col, b.inputs["Emission Color"])
    ems = nt.nodes.new("ShaderNodeMath"); ems.operation = "MULTIPLY"; ems.inputs[1].default_value = 1.6
    L.new(tex.outputs["Alpha"], ems.inputs[0])
    L.new(ems.outputs[0], b.inputs["Emission Strength"])
    return m


# ---------------- geometri ----------------
def body():
    """Acik tabanli kutu; taban halkasi zikzak. UV: u = cevre orani, v = z / H."""
    me = bpy.data.meshes.new("Govde")
    bm = bmesh.new()
    per = 2 * (W + D)
    n_u = int(TEETH * 4 * 4)            # her disin tepe/dip noktasi + ara noktalar
    rings = [0.0] + [HEM + (H - HEM) * k / 10 for k in range(11)]
    verts = []

    def perim(u):   # 0..1 -> (x, y) dikdortgen cevresi, on yuz ortadan baslar
        s = (u * per + W / 2) % per
        if s < W:
            return (W / 2 - s, -D / 2)
        s -= W
        if s < D:
            return (-W / 2, -D / 2 + s)
        s -= D
        if s < W:
            return (-W / 2 + s, D / 2)
        s -= W
        return (W / 2, D / 2 - s)

    def zig(u):
        t = (u * TEETH * 4) % 2.0
        return HEM * (t if t <= 1 else 2 - t)

    corners = sorted(set([i / n_u for i in range(n_u)] + [((W / 2) / per), ((W / 2 + D) / per), ((1.5 * W + D) / per), ((1.5 * W + 2 * D) / per)]))
    for ri, z in enumerate(rings):
        row = []
        for u in corners:
            x, y = perim(u)
            zz = zig(u) if ri == 0 else max(z, zig(u) + 0.02)
            row.append(bm.verts.new((x, y, zz)))
        verts.append(row)
    uv = bm.loops.layers.uv.new()
    nu = len(corners)
    for ri in range(len(rings) - 1):
        for i in range(nu):
            j = (i + 1) % nu
            f = bm.faces.new((verts[ri][i], verts[ri][j], verts[ri + 1][j], verts[ri + 1][i]))
            us = (corners[i], 1.0 if j == 0 else corners[j])
            for lp, u in zip(f.loops, (us[0], us[1], us[1], us[0])):
                lp[uv].uv = (u, lp.vert.co.z / H)
    top = bm.faces.new(list(reversed(verts[-1])))
    for lp in top.loops:
        lp[uv].uv = (0.5, 1.0)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new("Govde", me))
    sol = ob.modifiers.new("kalinlik", "SOLIDIFY"); sol.thickness = 0.03
    bev = ob.modifiers.new("yuvarlak", "BEVEL"); bev.width = 0.12; bev.segments = 6; bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(50)
    ob.modifiers.new("yumusak", "WEIGHTED_NORMAL")
    for p in me.polygons:
        p.use_smooth = True
    ob.data.materials.append(mat_body())
    return ob


def band(name, z, h, grow, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, z))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (W + grow, D + grow, h)
    bev = ob.modifiers.new("b", "BEVEL"); bev.width = 0.06; bev.segments = 4
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def horn(name, pts, r0, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = r0
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for i, (bp, p) in enumerate(zip(sp.bezier_points, pts)):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
        bp.radius = max(0.02, 1 - i / (len(pts) - 1))
    ob = link(bpy.data.objects.new(name, cu))
    ob.data.materials.append(mat)
    return ob


def build():
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    root = link(bpy.data.objects.new("Kami", None))
    chrome = principled("Krom", (0.75, 0.7, 0.85), 0.12, 1.0, film=480)[0]
    hornm = principled("Boynuz", (0.55, 0.45, 0.75), 0.18, 1.0, film=620)[0]

    g = body(); g.parent = root
    b1 = band("Serit", H - 0.42, 0.07, 0.05, chrome); b1.parent = root
    belt = band("Kemer", 1.25, 0.26, 0.06, mat_belt()); belt.parent = root
    for zz in (1.25 + 0.15, 1.25 - 0.15):
        e = band("KemerKenar", zz, 0.035, 0.08, chrome); e.parent = root
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.11, depth=0.2, location=(0, -(D / 2 + 0.07), 1.25 + 0.1))
    gem_t = bpy.context.active_object
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.11, depth=0.2, location=(0, -(D / 2 + 0.07), 1.25 - 0.1),
                                    rotation=(math.pi, 0, 0))
    gem_b = bpy.context.active_object
    gem_m = principled("Elmas", (0.9, 0.88, 1.0), 0.05, 1.0, film=380, emit=(0.75, 0.6, 1.0), es=0.6)[0]
    for gm in (gem_t, gem_b):
        gm.scale = (1, 0.5, 1)
        gm.rotation_euler.z = math.radians(45) if gm is gem_t else gm.rotation_euler.z
        gm.data.materials.append(gem_m)
        gm.parent = root
    gem_b.rotation_euler = (math.pi, 0, math.radians(45))

    # boynuzlar: ust koselerden disa-yukari kivrik; yanlarda uc kucuk diken
    for s in (-1, 1):
        horn("Boynuz", [Vector((s * 0.42, 0, H - 0.08)), Vector((s * 0.72, 0, H + 0.18)), Vector((s * 0.78, 0, H + 0.55)),
                        Vector((s * 0.6, 0, H + 0.82))], 0.13, hornm).parent = root
        for k, zz in enumerate((H - 0.75, H - 1.0, H - 1.25)):
            horn("Diken", [Vector((s * (W / 2 - 0.02), 0, zz)), Vector((s * (W / 2 + 0.2), 0, zz + 0.02)),
                           Vector((s * (W / 2 + 0.36), 0, zz - 0.08))], 0.06, hornm).parent = root

    # goz: oyuk + goz kuresi + iki goz kapagi
    socket_m = principled("Oyuk", (0.01, 0.005, 0.02), 0.9)[0]
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(0, -D / 2 + 0.02, H - 1.0))
    sock = bpy.context.active_object; sock.name = "Oyuk"; sock.scale = (1.25, 0.25, 0.72)
    sock.data.materials.append(socket_m); sock.parent = root
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, segments=48, ring_count=24, location=(0, -D / 2 + 0.03, H - 1.0))
    eye = bpy.context.active_object; eye.name = "Goz"; eye.scale = (1.0, 0.45, 0.82)
    for p in eye.data.polygons:
        p.use_smooth = True
    eye.data.materials.append(mat_iris(False)); eye.data.materials.append(mat_iris(True))
    eye.parent = root
    lids = []
    lid_m = principled("Kapak", (0.07, 0.03, 0.13), 0.55)[0]
    for s in (1, -1):   # ust / alt kapak: yarim kure kabuk, X ekseninde doner
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.262, segments=48, ring_count=24)
        lid = bpy.context.active_object
        bm = bmesh.new(); bm.from_mesh(lid.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z * s < -0.001], context="VERTS")
        bm.to_mesh(lid.data); bm.free()
        piv = link(bpy.data.objects.new("KapakMil", None))
        piv.location = (0, -D / 2 + 0.03, H - 1.0); piv.scale = (1.0, 0.47, 0.84); piv.parent = root
        lid.parent = piv; lid.location = (0, 0, 0)
        sol = lid.modifiers.new("k", "SOLIDIFY"); sol.thickness = 0.012
        for p in lid.data.polygons:
            p.use_smooth = True
        lid.data.materials.append(lid_m)
        lids.append(piv)
    brow = horn("Kas", [Vector((-0.34, -D / 2 - 0.03, H - 0.72)), Vector((0, -D / 2 - 0.07, H - 0.68)),
                        Vector((0.34, -D / 2 - 0.03, H - 0.72))], 0.035, lid_m)
    brow.parent = root

    # zemin isigi
    floor_m = principled("Zemin", (0.02, 0.015, 0.03), 0.3)[0]
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
    fl = bpy.context.active_object; fl.data.materials.append(floor_m)
    fl.is_shadow_catcher = True if hasattr(fl, "is_shadow_catcher") else False
    gl = bpy.data.lights.new("EtekIsik", "POINT"); gl.energy = 60; gl.color = EMERALD; gl.shadow_soft_size = 0.8
    link(bpy.data.objects.new("EtekIsik", gl)).location = (0, -0.9, 0.15)

    for nm, loc, e, col, size in (("Ana", (-2.6, -4.2, 4.2), 700, (0.85, 0.78, 1.0), 3),
                                  ("Mor", (3.2, 1.5, 3.5), 900, PURPLE, 3), ("Arka", (0, 3.5, 4.5), 500, (0.6, 0.4, 1.0), 2)):
        ld = bpy.data.lights.new(nm, "AREA"); ld.energy, ld.color, ld.size = e, col, size
        lo = link(bpy.data.objects.new(nm, ld)); lo.location = loc
        c = lo.constraints.new("TRACK_TO"); c.target = root; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"

    cam_d = bpy.data.cameras.new("Kamera"); cam_d.lens = 70
    cam = link(bpy.data.objects.new("Kamera", cam_d))
    cam.location = (1.9, -7.4, 2.4)
    tgt = link(bpy.data.objects.new("Hedef", None)); tgt.location = (0, 0, H / 2 + 0.25)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.camera = cam

    w = sc.world or bpy.data.worlds.new("Dunya"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (*lin((0.05, 0.035, 0.08)), 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    for a, v in (("taa_render_samples", 64), ("use_raytracing", True), ("use_gtao", True)):
        try:
            setattr(sc.eevee, a, v)
        except Exception:
            pass
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = SIZE
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Punchy"
    except Exception:
        pass
    return dict(root=root, eye=eye, lids=lids, brow=brow, socket=sock)


# durum: (ust kapak acisi, alt kapak acisi, kas yuksekligi, kas egimi, kirmizi, goz olcegi)
POSE = {
    "idle": (35, -12, 0.0, 0.0, False, 1.0),     # yari kapali, rahat
    "down": (48, -28, -0.04, 0.0, False, 0.95),  # odakli, kisik
    "speed": (-8, 8, 0.07, 0.0, False, 1.12),    # fal tasi gibi acik
    "done": (98, -70, 0.03, 0.0, False, 1.0),    # kapali (memnun)
    "error": (30, -10, -0.05, 18, True, 1.05),   # kizgin, kirmizi
}


def pose(o, st, t=0.0):
    up, lo, by, tilt, red, es = POSE[st]
    blink = 0.0
    if ANIM and st != "done":   # dongude bir kez goz kirpma (t: 0..1)
        blink = max(0.0, 1 - abs(t - 0.62) / 0.05)
    o["lids"][0].rotation_euler.x = math.radians(-(up + (100 - up) * blink))
    o["lids"][1].rotation_euler.x = math.radians(-(lo - (lo + 70) * blink * 0.4))
    o["brow"].location.z = by
    o["brow"].rotation_euler.y = math.radians(tilt)
    o["eye"].active_material_index = 0
    for p in o["eye"].data.polygons:
        p.material_index = 1 if red else 0
    o["eye"].scale = (es, 0.45 * es, 0.82 * es)
    o["root"].location.z = 0.04 * math.sin(t * math.tau) if ANIM else 0.0      # nefes / suzulme
    o["root"].rotation_euler.z = math.radians(6 * math.sin(t * math.tau)) if ANIM else 0.0
    o["eye"].location.x = 0.05 * math.sin(t * math.tau * 2) if ANIM and st == "idle" else 0.0


def main():
    os.makedirs(OUT, exist_ok=True)
    o = build()
    sc = bpy.context.scene
    for st in STATES:
        if ANIM:
            for f in range(48):
                pose(o, st, f / 48)
                sc.render.filepath = os.path.join(OUT, st, f"{f:03d}.png")
                bpy.ops.render.render(write_still=True)
        else:
            pose(o, st)
            sc.render.filepath = os.path.join(OUT, f"{st}.png")
            bpy.ops.render.render(write_still=True)
        print("KAMI_DONE", st, flush=True)


main()
