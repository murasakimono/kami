# Tam boy karakter kareleri: FINAL_ana.png gövdesi + FINAL_mimikler göz bölgesi (yumuşak maskeyle), siyah zemin saydam.
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps
from scipy import ndimage
A = Image.open('/mnt/user-data/uploads/kami/_tasarim_tmp/FINAL_ana.png').convert('RGB')
S = 0.93; AC = (485, 392)
CROP = (176, 0, 848, 1024); K = 0.6
def patch(f, fc):
    f = f.resize((round(f.width*S), round(f.height*S)), Image.LANCZOS)
    f = ImageEnhance.Brightness(f).enhance(0.86)
    ox = AC[0]-round(fc[0]*S); oy = AC[1]-round(fc[1]*S)
    m = Image.new('L', f.size, 0); cx, cy = fc[0]*S, fc[1]*S
    ImageDraw.Draw(m).ellipse((cx-160, cy-122, cx+158, cy+74), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(16))
    r = A.copy(); r.paste(f, (ox, oy), m); return r
# zemin maskesi: kenardan erişilen koyu pikseller
arr = np.asarray(A).astype(np.float32)
mx = arr.max(axis=2)
dark = mx < 26
lab, _ = ndimage.label(dark)
edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
bg = np.isin(lab, list(edge))
bg = ndimage.binary_erosion(bg, iterations=2)
soft = ndimage.gaussian_filter(bg.astype(np.float32), 1.5)
# etek altindaki zemin (golge + yesil isima) tamamen isik olarak ele alinir: koyu kutu kalmasin
rows = np.clip((np.arange(1024) - 935) / 25.0, 0, 1)[:, None]
soft = np.maximum(soft, rows * (mx < 200))
def rgba(img):
    a = np.asarray(img).astype(np.float32)
    lum = a.max(axis=2)
    alpha_bg = np.clip(lum / 70.0, 0, 1)          # ışıma/parlama zeminde yarı saydam kalır
    alpha = (1 - soft) + soft * alpha_bg
    rgb = np.where(alpha[..., None] > 0.01, np.clip(a / np.maximum(alpha[..., None], 0.01) * np.where(soft[..., None] > 0.5, 1, 1), 0, 255), 0)
    rgb = soft[..., None] * rgb + (1 - soft[..., None]) * a
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    fade = np.clip((1024 - np.arange(1024)) / 60.0, 0, 1)[:, None]
    out[..., 3] = (out[..., 3] * fade).astype(np.uint8)
    im = Image.fromarray(out, 'RGBA').crop(CROP)
    return im.resize((round(im.width*K), round(im.height*K)), Image.LANCZOS)
import os; os.makedirs('char', exist_ok=True)
for n in 'idle down speed done error sleep alert lock'.split():
    f = Image.open(f'web/eye/assets/{n}.webp').convert('RGB')
    rgba(patch(f, (190, 252))).save(f'char/{n}.webp', quality=90, method=6)
f = ImageOps.mirror(Image.open('web/eye/assets/alert.webp').convert('RGB'))
rgba(patch(f, (352-190, 252))).save('char/alertL.webp', quality=90, method=6)
print(Image.open('char/idle.webp').size, sum(os.path.getsize('char/'+x) for x in os.listdir('char'))//1024, 'KB')
