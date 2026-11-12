"""Kami 3D muzik gorsellestirici: Blender icinde calisir (blender -b --factory-startup -P blender_viz.py -- is.json).

Sahne: kapakli doner plak, etrafinda sese tepki veren cubuk halkasi, basla nabiz atan halka, yansitan zemin,
sanatci / sarki yazisi. Ses analizi Blender'in numpy'si ile yapilir (Kami ortaminda numpy yok).
Ilerleme: stdout'a "KAMI_FRAME n/toplam" satirlari.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

import bpy
import bmesh
import numpy as np

OBSIDIAN = (0.043, 0.035, 0.063)
PURPLE = (0.486, 0.227, 0.929)
EMERALD = (0.18, 0.902, 0.651)
N_BARS = 72


def log(*a):
    print(*a, flush=True)


def lin(c):   # sRGB -> lineer (malzeme renkleri)
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# ---------------- ses analizi ----------------
def analyze(src, ffmpeg, fps, n_bars):
    sr = 22050
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", src, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         stdout=subprocess.PIPE, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if x.size < sr:
        raise SystemExit("ses cok kisa")
    n_frames = int(math.ceil(x.size / sr * fps))
    win = 2048
    hann = np.hanning(win).astype(np.float32)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    edges = np.geomspace(40, 11000, n_bars + 1)
    idx = [np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0] for i in range(n_bars)]
    idx = [ix if ix.size else np.array([int(np.argmin(abs(freqs - edges[i])))]) for i, ix in enumerate(idx)]
    bass_ix = np.where((freqs >= 30) & (freqs < 150))[0]
    pad = np.concatenate([np.zeros(win, np.float32), x, np.zeros(win, np.float32)])
    bands = np.zeros((n_frames, n_bars), np.float32)
    bass = np.zeros(n_frames, np.float32)
    for f in range(n_frames):
        c = int(f / fps * sr) + win
        seg = pad[c - win // 2:c + win // 2]
        if seg.size < win:
            break
        mag = np.abs(np.fft.rfft(seg * hann))
        bands[f] = [np.log1p(mag[ix].mean()) for ix in idx]
        bass[f] = np.log1p(mag[bass_ix].mean())
    ref = np.percentile(bands, 97, axis=0) + 1e-6
    bands = np.clip(bands / ref, 0, 1.25)
    bass = np.clip(bass / (np.percentile(bass, 97) + 1e-6), 0, 1.3)
    # yumusatma: hizli yuksel, yavas dus
    for f in range(1, n_frames):
        bands[f] = np.maximum(bands[f], bands[f - 1] * 0.82)
        bass[f] = max(bass[f], bass[f - 1] * 0.86)
    bands = bands ** 1.6   # sessiz kisimlar dusuk, vuruslar belirgin
    return bands, bass, n_frames


def extract_cover(src, ffmpeg):
    out = os.path.join(tempfile.gettempdir(), "kami_viz_cover.png")
    try:
        os.remove(out)
    except OSError:
        pass
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-frames:v", "1", out],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out if os.path.isfile(out) and os.path.getsize(out) > 0 else ""


# ---------------- malzemeler ----------------
def mat_emit_objcolor(name, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    nt.links.new(oi.outputs["Color"], em.inputs["Color"])
    nt.links.new(oi.outputs["Alpha"], mul.inputs[0])
    nt.links.new(mul.outputs[0], em.inputs["Strength"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def mat_principled(name, color, rough, metal=0.0, emit=None, emit_s=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*lin(color), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[key].default_value = (*lin(emit), 1)
        b.inputs["Emission Strength"].default_value = emit_s
    return m, b


def mat_vinyl():
    m, b = mat_principled("Plak", (0.02, 0.018, 0.03), 0.25, 0.0)
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = 60
    wave.inputs["Distortion"].default_value = 0.6
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["To Min"].default_value = 0.18
    ramp.inputs["To Max"].default_value = 0.42
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], b.inputs["Roughness"])
    return m


def mat_cover(path):
    m, b = mat_principled("Kapak", PURPLE, 0.35, 0.0, PURPLE, 0.6)
    if not path:
        return m
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    mix = nt.nodes.new("ShaderNodeMix")   # saydam koseler siyah
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.01, 0.008, 0.015, 1)
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Factor"])
    nt.links.new(tex.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
    nt.links.new(mix.outputs["Result"], b.inputs[key])
    b.inputs["Emission Strength"].default_value = 0.35
    return m


# ---------------- sahne ----------------
def disc_mesh(name, r, segs=128):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=r, segments=segs)
    uv = bm.loops.layers.uv.new()
    for f in bm.faces:
        for lp in f.loops:
            co = lp.vert.co
            lp[uv].uv = (co.x / r * 0.5 + 0.5, co.y / r * 0.5 + 0.5)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build(job, n_frames):
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    fps = job["fps"]
    sc.render.fps = fps
    sc.frame_start, sc.frame_end = 1, n_frames
    sc.render.resolution_x, sc.render.resolution_y = job["w"], job["h"]
    sc.render.resolution_percentage = 100
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    ee = sc.eevee
    for attr, val in (("taa_render_samples", job.get("samples", 10)), ("use_raytracing", True), ("use_gtao", False),
                      ("use_bloom", True), ("bloom_intensity", 0.08), ("shadow_ray_count", 1), ("shadow_step_count", 4),
                      ("use_volumetric_shadows", False)):
        try:
            setattr(ee, attr, val)
        except Exception:
            pass
    try:
        ee.ray_tracing_options.resolution_scale = "2"   # yansimalar yarim cozunurlukte: hiz
        ee.ray_tracing_method = "SCREEN"
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "Standard"
    except Exception:
        pass

    w = sc.world or bpy.data.worlds.new("Dunya")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (*lin(OBSIDIAN), 1)
    bg.inputs["Strength"].default_value = 0.6

    rig = bpy.data.objects.new("Kamera_kok", None)
    sc.collection.objects.link(rig)
    cam_d = bpy.data.cameras.new("Kamera")
    cam_d.lens = 42
    cam = bpy.data.objects.new("Kamera", cam_d)
    sc.collection.objects.link(cam)
    cam.parent = rig
    cam.location = (0, -8.0, 5.0)
    tgt = bpy.data.objects.new("Hedef", None)
    sc.collection.objects.link(tgt)
    tgt.location = (0, 0, 0.35)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis, tc.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    sc.camera = cam

    floor = bpy.data.objects.new("Zemin", bpy.data.meshes.new("Zemin"))
    sc.collection.objects.link(floor)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40)
    bm.to_mesh(floor.data)
    bm.free()
    floor.location.z = -0.02
    floor.data.materials.append(mat_principled("Zemin", (0.03, 0.025, 0.045), 0.18, 0.3)[0])

    vinyl = disc_mesh("Plak", 2.0)
    vinyl.location.z = 0.12
    sol = vinyl.modifiers.new("kalinlik", "SOLIDIFY")
    sol.thickness = 0.08
    vinyl.data.materials.append(mat_vinyl())
    label = disc_mesh("Etiket", 1.08)
    label.parent = vinyl
    label.location.z = 0.004
    label.data.materials.append(mat_cover(job.get("cover") or ""))

    ring_mat = mat_emit_objcolor("Isik", 3.0)
    bpy.ops.mesh.primitive_torus_add(major_radius=2.18, minor_radius=0.025, major_segments=160, minor_segments=8,
                                     location=(0, 0, 0.13))
    torus = bpy.context.active_object
    torus.name = "Halka"
    torus.data.materials.append(ring_mat)
    torus.color = (*PURPLE, 0.6)

    bars = []
    bpy.ops.mesh.primitive_cube_add(size=1)
    base = bpy.context.active_object
    base.data.materials.append(ring_mat)
    me = base.data
    for v in me.vertices:   # tabani z=0'a otur: olcek yukari buyusun
        v.co.z += 0.5
    bpy.data.objects.remove(base, do_unlink=True)
    for i in range(N_BARS):
        a = i / N_BARS * math.tau
        ob = bpy.data.objects.new(f"Cubuk{i}", me)
        sc.collection.objects.link(ob)
        ob.location = (math.cos(a) * 2.55, math.sin(a) * 2.55, 0)
        ob.rotation_euler.z = a
        t = abs((i / N_BARS) * 2 - 1)   # 0 -> zumrut, 1 -> mor (halka boyunca simetrik)
        ob.color = (*[EMERALD[k] * (1 - t) + PURPLE[k] * t for k in range(3)], 0.8)
        ob.scale = (0.085, 0.05, 0.05)
        bars.append(ob)

    # arka plan tozu
    rng = np.random.default_rng(7)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1)
    dust_me = bpy.context.active_object.data
    bpy.data.objects.remove(bpy.context.active_object, do_unlink=True)
    dust_me.materials.append(ring_mat)
    dust_root = bpy.data.objects.new("Toz", None)
    sc.collection.objects.link(dust_root)
    for k in range(160):
        ob = bpy.data.objects.new(f"Toz{k}", dust_me)
        sc.collection.objects.link(ob)
        ob.parent = dust_root
        r, a = rng.uniform(6, 16), rng.uniform(0, math.tau)
        ob.location = (math.cos(a) * r, math.sin(a) * r, rng.uniform(0.3, 7))
        s = rng.uniform(0.015, 0.05)
        ob.scale = (s, s, s)
        c = PURPLE if rng.random() < 0.6 else EMERALD
        ob.color = (*c, rng.uniform(0.3, 1.0))

    for nm, loc, energy, col in (("Mor", (-5, -3, 6), 900, PURPLE), ("Yesil", (5, 2, 5), 600, EMERALD),
                                 ("Ust", (0, 0, 8), 250, (1, 1, 1))):
        ld = bpy.data.lights.new(nm, "AREA")
        ld.energy, ld.color, ld.size = energy, col, 4
        ld.use_shadow = nm == "Ust"   # golge tek isikta: hiz
        lo = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lc = lo.constraints.new("TRACK_TO")
        lc.target, lc.track_axis, lc.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"

    title = (job.get("title") or "").strip()
    if title:
        cu = bpy.data.curves.new("Baslik", "FONT")
        cu.body = title[:60]
        cu.align_x = "CENTER"
        cu.size = 0.26
        cu.extrude = 0.02
        if job.get("font") and os.path.isfile(job["font"]):
            cu.font = bpy.data.fonts.load(job["font"])
        tob = bpy.data.objects.new("Baslik", cu)
        sc.collection.objects.link(tob)
        tob.parent = cam
        tob.location = (0, -1.25, -6.0)   # kameraya gore: ekranin alt kismi
        tob.data.materials.append(ring_mat)
        tob.color = (1, 1, 1, 0.5)

    return dict(rig=rig, vinyl=vinyl, torus=torus, bars=bars, dust=dust_root, cam=cam)


def add_audio(sc, src):
    se = sc.sequence_editor or sc.sequence_editor_create()
    coll = se.strips if hasattr(se, "strips") else se.sequences
    coll.new_sound("ses", src, 1, 1)


def setup_output(sc, out):
    sc.render.filepath = out
    im = sc.render.image_settings
    try:
        im.media_type = "VIDEO"   # Blender 5.x
    except Exception:
        pass
    im.file_format = "FFMPEG"
    ff = sc.render.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = "HIGH"
    ff.ffmpeg_preset = "GOOD"
    ff.audio_codec = "AAC"
    ff.audio_bitrate = 256
    ff.audio_channels = "STEREO"


def main():
    job = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
    log("KAMI_STAGE analiz")
    bands, bass, n_frames = analyze(job["src"], job["ffmpeg"], job["fps"], N_BARS)
    if job.get("limit"):
        n_frames = min(n_frames, int(job["limit"] * job["fps"]))
    if not job.get("cover"):
        job["cover"] = extract_cover(job["src"], job["ffmpeg"]) or job.get("fallback_cover") or ""
    log("KAMI_STAGE sahne")
    o = build(job, n_frames)
    sc = bpy.context.scene
    fps = job["fps"]

    def on_frame(scene, *_):
        f = min(max(scene.frame_current - 1, 0), n_frames - 1)
        t = f / fps
        b = float(bass[f])
        for i, ob in enumerate(o["bars"]):
            j = i if i < N_BARS // 2 else N_BARS - 1 - i   # ayna: bas onde, tiz arkada
            v = float(bands[f, j * 2])
            ob.scale.z = 0.05 + v * 1.35
            ob.color[3] = 0.15 + v * 0.5
        o["vinyl"].rotation_euler.z = -t * math.tau * 33.3 / 60
        s = 1 + b * 0.045
        o["vinyl"].scale = (s, s, 1)
        o["torus"].scale = (1 + b * 0.09, 1 + b * 0.09, 1)
        o["torus"].color[3] = 0.12 + b * 0.7
        o["rig"].rotation_euler.z = math.sin(t * 0.11) * 0.55
        o["cam"].location.y = -8.0 + b * 0.3
        o["dust"].rotation_euler.z = t * 0.02
        if scene.frame_current % 10 == 0:
            log(f"KAMI_FRAME {scene.frame_current}/{n_frames}")

    bpy.app.handlers.frame_change_pre.append(on_frame)
    if job.get("preview_t") is not None:
        sc.frame_set(int(job["preview_t"] * fps) + 1)
        on_frame(sc)
        sc.render.image_settings.file_format = "PNG"
        sc.render.filepath = job["out"]
        bpy.ops.render.render(write_still=True)
        log("KAMI_DONE " + job["out"])
        return
    add_audio(sc, job["src"])
    setup_output(sc, job["out"])
    log(f"KAMI_STAGE render {n_frames}")
    bpy.ops.render.render(animation=True)
    log("KAMI_DONE " + job["out"])


main()
