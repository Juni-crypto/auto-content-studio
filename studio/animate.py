"""Animated carousel slides. The Codex design stays the whole design: the motion is taken from it, never drawn over it.

For a finished slide (the approved design A) Codex paints its empty plate B: the same slide with every word, number, label,
logo and photo removed. Where A and B differ are the slide's elements. They are grouped into blocks in reading order and
brought in one by one over the plate with the brand's entrance (SPORTS DESK slams in, TECHDESK wipes across like tape, BIZDESK
paints on), then the approved design holds, exactly as the committee passed it, until the clip loops.

A plate that doesn't line up gives the slide a whole-design entrance instead; a slide whose motion looks broken to the picture
editor goes out as the still image. Clips are 1080x1350, 30 fps, H.264 with a silent AAC track (Instagram carousel video).
"""
import math, pathlib, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

W, H, FPS, SECONDS = 1080, 1350, 30, 6.0
STYLE = {"sportsdesk": "slam", "techdesk": "wipe", "bizdesk": "paint"}
PLATE = ("Image 1 is a finished Instagram slide. Make its EMPTY BACKGROUND PLATE: the exact same canvas, framing, crop, background "
         "colour, texture, lighting, grain, halftone and purely decorative scenery, pixel-aligned with Image 1, but with every "
         "foreground element removed: all words, letters and numbers; labels, pills, badges, tags and tape strips; logos and brand "
         "marks; photos and photo frames; arrows, divider lines, icons, slide counters and \"swipe\" hints. Where an element is "
         "removed, continue the background behind it naturally (same texture, same light) so nothing hints that something was "
         "there. Do not add anything new; do not move, resize, recolour or restyle anything that stays. The output contains no "
         "text of any kind.")
CHECK = ("These slides are ANIMATED: each row of the attached sheet is one slide's clip, frames left to right in time (the "
         "timestamp is under each frame) and the LAST frame of the row is the approved finished design. During the build the "
         "slide's words, numbers, labels and logos arrive one after another over the empty background, so missing, half-revealed, "
         "scaled or sliding elements in the early frames are CORRECT. Pass unless a frame looks broken: garbled, doubled or ghosted "
         "letters, a smeared or torn patch, the background jumping or changing between frames, or a stray piece of an element "
         "left behind. For each broken row add an issue with \"where\": \"slide N\"; those slides go out as still images.")


def plate_size(raw):
    w, h = Image.open(raw).size
    return "1024x1024" if abs(w / h - 1) < 0.1 else "1024x1536" if h > w else "1536x1024"


def fit_plate(plate_raw, raw):
    """The plate at the design's exact pixel size (the image tool may answer in another size). None when the shape changed."""
    p, r = Image.open(plate_raw).convert("RGB"), Image.open(raw)
    if abs(p.width / p.height - r.width / r.height) > 0.03: return None
    return p.resize(r.size, Image.LANCZOS)


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def shift(img, dy, dx):
    """Move an image by whole pixels, repeating the edge (no wrap-around)."""
    p = max(abs(dy), abs(dx))
    if not p: return img
    big = np.pad(img, ((p, p), (p, p), (0, 0)), mode="edge")
    return big[p - dy:p - dy + img.shape[0], p - dx:p - dx + img.shape[1]]


def align(a, b, lim=48):
    """Phase correlation: the whole-pixel shift that lines the plate up with the design (kept only if it helps)."""
    ga, gb = a.mean(2), b.mean(2)
    r = np.fft.irfft2(np.fft.rfft2(ga - ga.mean()) * np.conj(np.fft.rfft2(gb - gb.mean())), s=ga.shape)
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    dy = dy - ga.shape[0] if dy > ga.shape[0] // 2 else dy
    dx = dx - ga.shape[1] if dx > ga.shape[1] // 2 else dx
    if (dy, dx) == (0, 0) or abs(dy) > lim or abs(dx) > lim: return b
    moved = shift(b, int(dy), int(dx))
    return moved if np.abs(moved - a).mean() < np.abs(b - a).mean() else b


class Block:
    def __init__(self, box, mask):
        self.y0, self.x0, self.y1, self.x1 = box
        self.mask = mask                     # bool, full frame

    @property
    def h(self): return self.y1 - self.y0

    @property
    def w(self): return self.x1 - self.x0

    def merge(self, o):
        return Block((min(self.y0, o.y0), min(self.x0, o.x0), max(self.y1, o.y1), max(self.x1, o.x1)), self.mask | o.mask)


def _near(p, q):
    """Two blocks that belong together: small text lines of one paragraph, a caption under its logo, an arrow beside its line."""
    vgap = max(p.y0, q.y0) - min(p.y1, q.y1)
    hgap = max(p.x0, q.x0) - min(p.x1, q.x1)
    small = min(p.h, q.h) < 70
    return small and ((vgap < 30 and hgap < 0) or (vgap < 0 and hgap < 90))


def _box(mask):
    ys, xs = np.nonzero(mask)
    return (ys.min(), xs.min(), ys.max() + 1, xs.max() + 1)


def _lines(k, raw):
    """Split a stacked headline so it arrives line by line. Cuts sit in the valleys of the raw difference (the smoothed mask
    bridges tight line gaps). A block that would leave a short piece (a logo, a small-text paragraph) stays whole."""
    rows = (raw & k.mask)[k.y0:k.y1, k.x0:k.x1].sum(1)
    if k.h < 120 or not rows.any(): return [k]
    empty = rows <= max(2, 0.05 * np.median(rows[rows > 0]))
    cuts, y = [], 0
    while y < len(rows):
        if empty[y]:
            e = y
            while e < len(rows) and empty[e]: e += 1
            if 0 < y and e < len(rows): cuts.append((y + e) // 2)
            y = e
        else:
            y += 1
    pieces, start, mass = [], 0, k.mask.sum()
    for c in cuts + [len(rows)]:
        m = np.zeros_like(k.mask); m[k.y0 + start:k.y0 + c, k.x0:k.x1] = k.mask[k.y0 + start:k.y0 + c, k.x0:k.x1]
        start = c
        if not m.any(): continue
        piece = Block(_box(m), m)
        if pieces and m.sum() < 0.03 * mass: pieces[-1] = pieces[-1].merge(piece)   # a sliver (descender, dot) joins its line
        else: pieces.append(piece)
    if len(pieces) < 2 or any(q.h < 60 for q in pieces): return [k]
    return pieces


def elements(a, b, max_blocks=10):
    """The slide's elements (blocks in reading order) and how much of the frame they cover."""
    d = np.abs(ndimage.gaussian_filter(a, (1.5, 1.5, 0)) - ndimage.gaussian_filter(b, (1.5, 1.5, 0))).max(2)
    raw = ndimage.binary_opening(d > 38, iterations=1)
    m = ndimage.binary_fill_holes(ndimage.binary_closing(raw, structure=np.ones((9, 9))))
    lab, n = ndimage.label(ndimage.binary_dilation(m, structure=np.ones((9, 45))))   # letters -> words -> one line
    blocks = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None: continue
        own = m & (lab == i)
        if own.sum() < 500: continue
        blocks += _lines(Block((sl[0].start, sl[1].start, sl[0].stop, sl[1].stop), own), raw)
    merged = True
    while merged:
        merged = False
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                if _near(blocks[i], blocks[j]):
                    blocks[i] = blocks[i].merge(blocks.pop(j)); merged = True; break
            if merged: break
    blocks.sort(key=lambda k: (k.y0 // 90, k.x0))
    while len(blocks) > max_blocks:   # too many pieces: join the smallest neighbouring pair
        k = min(range(len(blocks) - 1), key=lambda i: blocks[i].mask.sum() + blocks[i + 1].mask.sum())
        blocks[k] = blocks[k].merge(blocks.pop(k + 1))
    cover = float(np.mean(np.logical_or.reduce([k.mask for k in blocks]))) if blocks else 0.0
    return blocks, cover


# ---------------------------------------------------------------- motion
def ease_out(p, k=3): return 1 - (1 - p) ** k


def ease_back(p, s=1.6):
    p -= 1
    return p * p * ((s + 1) * p + s) + 1


def _soft(mask):
    """A feathered alpha (0..1) that also takes the anti-aliased rim of each letter."""
    grown = ndimage.binary_dilation(mask, iterations=3)
    return np.clip(ndimage.gaussian_filter(grown.astype(np.float32), 1.6) * 1.4, 0, 1)


class Clip:
    def __init__(self, a, b, blocks, style, seed=0):
        self.a, self.b, self.style = a, b, style
        self.rng = np.random.default_rng(seed)
        n = max(1, len(blocks)); self.dur = {"slam": 0.42, "wipe": 0.5, "paint": 0.62}[style]
        step = min(0.34, max(0.16, 1.9 / n))
        self.parts = []
        for i, k in enumerate(blocks):
            pad = 6
            y0, x0 = max(0, k.y0 - pad), max(0, k.x0 - pad)
            y1, x1 = min(a.shape[0], k.y1 + pad), min(a.shape[1], k.x1 + pad)
            alpha = _soft(k.mask)[y0:y1, x0:x1]
            noise = ndimage.gaussian_filter1d(self.rng.standard_normal(y1 - y0), 9) * 60   # a painted, uneven brush edge
            self.parts.append(dict(t=0.2 + i * step, box=(y0, x0, y1, x1), rgb=a[y0:y1, x0:x1], alpha=alpha, noise=noise,
                                   big=(k.y1 - k.y0) > 110, grow=min(0.4, max(0.08, (W - 30) / max(1, x1 - x0) - 1))))
        self.done = (self.parts[-1]["t"] + self.dur) if self.parts else 0.2
        self.fade = (self.done, self.done + 0.25)          # then exactly the approved design

    def _place(self, canvas, rgb, alpha, y, x):
        h, w = alpha.shape
        ys, xs = max(0, y), max(0, x)
        ye, xe = min(canvas.shape[0], y + h), min(canvas.shape[1], x + w)
        if ye <= ys or xe <= xs: return
        al = alpha[ys - y:ye - y, xs - x:xe - x, None]
        region = canvas[ys:ye, xs:xe]
        canvas[ys:ye, xs:xe] = region * (1 - al) + rgb[ys - y:ye - y, xs - x:xe - x] * al

    def frame(self, t):
        if t >= self.fade[1]: return self.a
        c = self.b.copy(); shake = (0, 0)
        for p in self.parts:
            q = (t - p["t"]) / self.dur
            if q <= 0: continue
            q = min(q, 1.0); y0, x0, y1, x1 = p["box"]; rgb, alpha = p["rgb"], p["alpha"]
            if self.style == "slam":
                s = 1 + p["grow"] * (1 - ease_back(q)) if q < 1 else 1.0   # wide lines grow less, never far off the frame
                al = alpha * min(1.0, q / 0.3)
                since = t - (p["t"] + self.dur)
                if 0 <= since < 0.14:   # a flash on landing, and the frame kicks on the big lines
                    rgb = rgb + (255 - rgb) * 0.55 * (1 - since / 0.14)
                    if p["big"]:
                        amp = 9 * (1 - since / 0.14); shake = (int(self.rng.uniform(-amp, amp)), int(self.rng.uniform(-amp, amp)))
                if abs(s - 1) > 1e-3:
                    h, w = alpha.shape; nh, nw = max(1, round(h * s)), max(1, round(w * s))
                    rgb = np.asarray(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((nw, nh), Image.BILINEAR), np.float32)
                    al = np.asarray(Image.fromarray((al * 255).astype(np.uint8)).resize((nw, nh), Image.BILINEAR), np.float32) / 255
                    self._place(c, rgb, al, y0 + (h - nh) // 2, x0 + (w - nw) // 2)
                else:
                    self._place(c, rgb, al, y0, x0)
            else:
                h, w = alpha.shape; e = ease_out(q, 4 if self.style == "wipe" else 3)
                edge = -80 + e * (w + 160)
                cols = np.arange(w)[None, :]
                if self.style == "paint":
                    ramp = np.clip((edge + p["noise"][:, None] - cols) / 44, 0, 1)
                    self._place(c, rgb, alpha * ramp, y0 + round(18 * (1 - e)), x0)
                else:
                    ramp = np.clip((edge - cols) / 56, 0, 1) * np.ones((h, 1))
                    self._place(c, rgb, alpha * ramp, y0, x0 - round(46 * (1 - e)))
        if t > self.fade[0]:
            k = (t - self.fade[0]) / (self.fade[1] - self.fade[0]); c = c * (1 - k) + self.a * k
        if t < 1.4:   # the whole slide settles into place as it builds
            s = 1 + 0.03 * (1 - ease_out(t / 1.4))
            im = Image.fromarray(np.clip(c, 0, 255).astype(np.uint8))
            nw, nh = round(W * s), round(H * s)
            im = im.resize((nw, nh), Image.BILINEAR).crop(((nw - W) // 2, (nh - H) // 2, (nw - W) // 2 + W, (nh - H) // 2 + H))
            c = np.asarray(im, np.float32)
        if shake != (0, 0): c = shift(c, *shake)
        return c


def encode(clip, out, cover=False, seconds=SECONDS):
    """Write the clip. A cover slide shows the finished design on frame 0 (the grid thumbnail), then builds."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds}", "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "30",
           "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    final = np.clip(clip.a, 0, 255).astype(np.uint8).tobytes()
    try:
        for f in range(int(seconds * FPS)):
            t = f / FPS
            if (f == 0 and cover) or t >= clip.fade[1]: p.stdin.write(final); continue
            p.stdin.write(np.clip(clip.frame(t), 0, 255).astype(np.uint8).tobytes())
    finally:
        p.stdin.close()
    if p.wait() != 0: raise RuntimeError(f"ffmpeg failed for {out}")
    return out


def whole(a, brand):
    """No usable plate: the whole design is one element, entering over a plain field of its own darkest/background tone."""
    edge = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3)])
    b = np.broadcast_to(np.median(edge, axis=0), a.shape).astype(np.float32).copy()
    return [Block((0, 0, a.shape[0], a.shape[1]), np.ones(a.shape[:2], bool))], b


def make_clip(design, plate, brand, out, cover=False, seed=0):
    """design / plate: 1080x1350 images. Returns (mp4, how) — how is 'elements' or 'whole'."""
    a = load(design); how = "whole"
    if plate is not None:
        b = align(a, load(plate)); blocks, cover_frac = elements(a, b)
        if blocks and 0.01 < cover_frac < 0.55: how = "elements"
    if how == "whole": blocks, b = whole(a, brand)
    encode(Clip(a, b, blocks, STYLE.get(brand, "wipe"), seed), out, cover)
    return out, how


def sheet(clips, dest, times=(0.35, 0.8, 1.3, 1.9, SECONDS - 0.1)):
    """One row per clip (frames over time, the last is the settled design) for the picture editor."""
    tw, th = 216, 270
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    im = Image.new("RGB", (60 + len(times) * (tw + 6), len(clips) * (th + 26)), "white"); d = ImageDraw.Draw(im)
    for r, (n, mp4) in enumerate(clips):
        y = r * (th + 26)
        d.text((6, y + th // 2), f"slide {n}", fill="black", font=font)
        for c, t in enumerate(times):
            fr = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(mp4), "-frames:v", "1", "-f", "image2pipe",
                                 "-vcodec", "png", "-"], capture_output=True, check=True).stdout
            from io import BytesIO
            x = 60 + c * (tw + 6)
            im.paste(Image.open(BytesIO(fr)).convert("RGB").resize((tw, th)), (x, y))
            d.text((x + 4, y + th + 4), f"{t:.1f}s", fill="black", font=font)
    im.save(dest, quality=88)
    return dest


if __name__ == "__main__":   # python -m studio.animate DESIGN.jpg PLATE.jpg BRAND OUT.mp4 [--cover]
    import sys
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    print(make_clip(args[0], args[1] if args[1] != "-" else None, args[2], args[3], cover="--cover" in sys.argv))
