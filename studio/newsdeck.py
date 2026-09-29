"""News carousels: real official images carry the post, placed pixel-true by code (never redrawn, so faces, screenshots and
products stay exactly as their owner published them); every word is a Codex design.

Slide types (the writer picks them, prompts/news-carousel.md):
  cover       the image full-bleed on top, a Codex headline panel under it, the official logo in a round badge on the seam
  text        a full Codex slide: one or two short news paragraphs
  images      one or two images stacked, no words
  image_text  an image on top, a short Codex line panel under it
  text_image  a short Codex paragraph panel on top, an image under it
  end         a full Codex slide: the question and "Follow @handle for more"
Panels fade into their image, so each slide reads as one piece.
"""
import pathlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from . import assets
from .config import ASSETS, BRANDS

W, H, PH = 1080, 1350, 720          # slide size; a Codex panel (1536x1024 canvas) is scaled to 1080x720
FADE = 130                          # px of the panel that fades into the image
LOOK = {   # panel colours: background, headline base, accent, accent2, category pill, pill text, badge ring
    "sportsdesk": dict(bg="#111111", base="#FFF6E5", accent="#E6007E", accent2="#FFB300", pill="#FFB300", pill_text="#111111", ring="#FFB300",
                      type="heavy wide display type in the style of a modern Indian single-screen cinema poster, subtle halftone grain"),
    "techdesk": dict(bg="#121212", base="#F2EFE8", accent="#FF5B1F", accent2="#FFD23F", pill="#FF5B1F", pill_text="#111111", ring="#FF5B1F",
                     type="ultra-heavy condensed ITALIC grotesk, tight leading, subtle print grain, urgent editorial feel"),
    "bizdesk": dict(bg="#111111", base="#FFF3D6", accent="#FFC400", accent2="#1FA34A", pill="#E0262B", pill_text="#FFFFFF", ring="#FFC400",
                    type="bold hand-lettered Indian signboard display type with painted drop shadows, slight brush texture"),
}
RULES = ("Exact readable text only as quoted, spelled and punctuated exactly, in English; digits exactly right; no other words "
         "anywhere, no logos, no icons, no photos, no people, no illustrations, no watermarks, no slide counters. Avoid: purple "
         "gradients, neon glow, clutter, boxes inside boxes, emoji.")


def rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fit(im, w, h, bias=0.42):
    """Cover-crop an image to w x h (a little above centre, where faces and titles usually sit)."""
    im = im.convert("RGB"); s = max(w / im.width, h / im.height)
    r = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.LANCZOS)
    x = (r.width - w) // 2; y = round((r.height - h) * bias)
    return r.crop((x, y, x + w, y + h))


def contain(im, w, h):
    """The whole image at full width over a blurred, darkened copy of itself (never crops a landscape screenshot)."""
    im = im.convert("RGB"); bg = fit(im, w, h).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", bg.size, "black"), 0.45)
    s = min(w / im.width, h / im.height); fg = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2)); return bg


def panel_brief(brand, what, fade_edge):
    b, L = BRANDS[brand], LOOK[brand]
    fade = (f"The {fade_edge} 13% of the canvas is plain {L['bg']} with nothing on it (it fades into a photo there). ")
    return (f"Design a text panel for an Instagram news post by \"{b['name']}\" ({b['beat']}). Landscape canvas, solid {L['bg']} "
            f"background with a very subtle texture, flat and even. {fade}Type: {L['type']}. Image 1 is the brand's identity board: "
            f"follow its type and colours, not its words or layout. {what} {RULES}")


def cover_what(s, brand):
    b, L = BRANDS[brand], LOOK[brand]
    acc = " ".join(f'"{x}"' for x in s.get("accent") or []); acc2 = " ".join(f'"{x}"' for x in s.get("accent2") or [])
    return (f"Layout, centred, filling the width: a small rounded pill \"{s.get('category', '').upper()}\" ({L['pill']} with {L['pill_text']} "
            f"text); under it the headline in ALL CAPS on 3–5 tight lines, as big as fits: \"{s['headline'].upper()}\". Colour these "
            f"exact phrases {L['accent']}: {acc or 'none'}; these {L['accent2']}: {acc2 or 'none'}; every other word {L['base']}. At the "
            f"bottom, small and spaced: \"SWIPE FOR MORE\" in {L['base']}. Nothing else.")


def text_what(text, brand, big=False):
    L = LOOK[brand]
    return (f"The paragraph below set as a clean news text block, left-aligned with generous margins, {'large' if big else 'medium-large'} "
            f"readable type in {L['base']} (a clean sans for body is fine; key numbers and names may be bold in {L['accent']}), comfortable "
            f"line spacing, vertically centred in the free area: \"{text}\". Nothing else.")


def codex_panel(dest, brief, brand):
    raw = pathlib.Path(dest).with_suffix(".raw.png")
    if not raw.exists(): assets.codex_image(raw, brief, [ASSETS / BRANDS[brand]["board"]], size="1536x1024")
    return fit(Image.open(raw), W, PH, bias=0.5)


def join(img, panel, panel_top, brand):
    """Stack an image and a panel on one slide; the panel fades into the image over FADE px (and the image darkens into it)."""
    L = LOOK[brand]; slide = Image.new("RGB", (W, H), rgb(L["bg"]))
    if panel_top:
        ih = H - PH + FADE; slide.paste(img, (0, H - ih)); py, ramp = 0, np.linspace(1, 0, FADE)
        a = np.ones(PH, np.float32); a[PH - FADE:] = ramp
    else:
        ih = H - PH + FADE; slide.paste(img, (0, 0)); py, ramp = H - PH, np.linspace(0, 1, FADE)
        a = np.ones(PH, np.float32); a[:FADE] = ramp
    shade = Image.new("RGB", (W, PH), rgb(L["bg"]))   # the image darkens towards the panel so the seam never shows
    base = slide.crop((0, py, W, py + PH))
    s = np.asarray(base, np.float32); sh = np.asarray(shade, np.float32); p = np.asarray(panel.convert("RGB"), np.float32)
    k = np.clip(a * 1.25, 0, 1)[:, None, None]
    s = s * (1 - k) + sh * k
    s = s * (1 - a[:, None, None]) + p * a[:, None, None]
    slide.paste(Image.fromarray(np.clip(s, 0, 255).astype(np.uint8)), (0, py))
    return slide, ih


def badge(slide, logo, cx, cy, brand, d=230):
    """The official logo, unaltered, on a white disc with a brand-colour ring."""
    L = LOOK[brand]; size = d + 16
    disc = Image.new("RGBA", (size, size), (0, 0, 0, 0)); dr = ImageDraw.Draw(disc)
    dr.ellipse((0, 0, size - 1, size - 1), fill=rgb(L["ring"]) + (255,)); dr.ellipse((8, 8, size - 9, size - 9), fill=(255, 255, 255, 255))
    lg = Image.open(logo).convert("RGBA"); box = round(d * 0.68); s = min(box / lg.width, box / lg.height)
    lg = lg.resize((max(1, round(lg.width * s)), max(1, round(lg.height * s))), Image.LANCZOS)
    disc.alpha_composite(lg, ((size - lg.width) // 2, (size - lg.height) // 2))
    slide.paste(disc, (cx - size // 2, cy - size // 2), disc)


def full_slide(dest, brand, what, n, total):
    """A whole Codex slide (text / end): 2:3 canvas composed for the 4:5 crop, like the designed carousels."""
    from .pipeline import BOARD_NOTE, POST, crop45
    b, L = BRANDS[brand], LOOK[brand]
    raw = pathlib.Path(dest).with_suffix(".raw.png")
    if not raw.exists():
        assets.codex_image(raw, (f"Design a finished Instagram news carousel slide ({n}/{total}) for \"{b['name']}\" ({b['beat']}). Solid "
                                 f"{L['bg']} background with a very subtle texture. Type: {L['type']}. {POST} {BOARD_NOTE} {what} "
                                 f"Small brand wordmark \"{b['name']}\" at the bottom-left in {L['accent']}. {RULES}"),
                           [ASSETS / b["board"]])
    crop45(raw, dest)
    return pathlib.Path(dest)


def slide(s, total, brand, handle, gallery, logo_file, dest, note=""):
    """Render one slide to dest (1080x1350 JPG). `note` carries the picture editor's fixes into the Codex part."""
    dest = pathlib.Path(dest); g = {x["id"]: x for x in gallery}; t = s["type"]
    if note:   # a fix: the Codex part is made again
        for f in dest.parent.glob(f"{dest.stem}*.raw.png"): f.unlink()
    img = lambda i: Image.open(g[i]["path"])
    if t == "cover":
        panel = codex_panel(dest.with_name(dest.stem + "-panel.png"), panel_brief(brand, cover_what(s, brand) + " " + note, "top"), brand)
        out, ih = join(fit(img(s["image"]), W, H - PH + FADE), panel, False, brand)
        if logo_file: badge(out, logo_file, W - 190, H - PH - 40, brand)
    elif t in ("image_text", "text_image"):
        top = t == "text_image"
        panel = codex_panel(dest.with_name(dest.stem + "-panel.png"),
                            panel_brief(brand, text_what(s["text"], brand, big=not top) + " " + note, "bottom" if top else "top"), brand)
        out, _ = join(fit(img(s["image"]), W, H - PH + FADE), panel, top, brand)
    elif t == "images":
        ids = [i for i in s.get("images", []) if i in g][:2]
        if len(ids) == 2:
            out = Image.new("RGB", (W, H), "black"); h = (H - 8) // 2
            out.paste(fit(img(ids[0]), W, h), (0, 0)); out.paste(fit(img(ids[1]), W, H - h - 8), (0, h + 8))
        else:
            out = contain(img(ids[0]), W, H)
    elif t == "text":
        return full_slide(dest, brand, text_what("  ".join(s.get("paragraphs", [])), brand, big=True) + " " + note, s["n"], total)
    else:   # end
        what = (f"Centred: the question \"{s.get('question', '')}\" huge in {LOOK[brand]['base']}; under it \"Follow @{handle} for more\" "
                f"in {LOOK[brand]['accent']}; at the very bottom in tiny print \"Logos belong to their owners. Not affiliated.\". Nothing else.")
        return full_slide(dest, brand, what + " " + note, s["n"], total)
    out.save(dest, quality=92, subsampling=0)
    return dest


def build(plan, brand, handle, gallery, logo_file, sdir, fixes=None, only=None):
    """All slides (or `only` those numbers, with `fixes`) side by side. Returns the slide JPGs in order."""
    sdir = pathlib.Path(sdir); sdir.mkdir(parents=True, exist_ok=True); n = len(plan["slides"])
    todo = [s for s in plan["slides"] if only is None or s["n"] in only]
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(lambda s: slide(s, n, brand, handle, gallery, logo_file, sdir / f"slide-{s['n']:02d}.jpg", fixes or ""), todo))
    return [sdir / f"slide-{s['n']:02d}.jpg" for s in plan["slides"]]


def view(plan, gallery):
    """The slides as text, for the committee."""
    g = {x["id"]: x for x in gallery}; out = []
    pic = lambda i: f"[official image #{i}: {g[i]['what']}]" if i in g else f"[image #{i} MISSING]"
    for s in plan["slides"]:
        t = s["type"]
        if t == "cover": body = f"{pic(s.get('image'))} pill \"{s.get('category')}\" headline \"{s.get('headline')}\" (accent {s.get('accent')}, {s.get('accent2')}); logo badge: {s.get('logo')}"
        elif t == "text": body = " / ".join(s.get("paragraphs", []))
        elif t == "images": body = " + ".join(pic(i) for i in s.get("images", []))
        elif t in ("image_text", "text_image"): body = f"{pic(s.get('image'))} text \"{s.get('text')}\""
        else: body = f"question \"{s.get('question')}\" + Follow line"
        out.append(f"Slide {s['n']} ({t}): {body}")
    return "\n".join(out)


def check(plan, gallery):
    """Structural problems the writer must fix."""
    ids = {x["id"] for x in gallery}; p = []; sl = plan.get("slides") or []
    if not 5 <= len(sl) <= 8: p.append(f"{len(sl)} slides; use 5-8")
    if not sl or sl[0].get("type") != "cover": p.append("slide 1 must be the cover")
    if sl and sl[-1].get("type") != "end": p.append("the last slide must be the end slide")
    used = []
    for s in sl:
        for i in ([s.get("image")] if s.get("image") is not None else []) + list(s.get("images") or []):
            if i not in ids: p.append(f"slide {s.get('n')}: image {i} is not in the gallery")
            used.append(i)
        if s.get("type") == "cover":
            h = (s.get("headline") or "").upper()
            for x in (s.get("accent") or []) + (s.get("accent2") or []):
                if x.upper() not in h: p.append(f"cover: accent phrase {x!r} is not in the headline")
            if next((x for x in gallery if x["id"] == s.get("image")), {}).get("text_heavy"): p.append("cover: pick an image without big text")
    if len(used) != len(set(used)): p.append("use each image once")
    if not (plan.get("caption") or "").strip(): p.append("the caption is empty")
    types = [s.get("type") for s in sl]
    if any(a == b == "text" for a, b in zip(types, types[1:])): p.append("never two text slides in a row")
    return p
