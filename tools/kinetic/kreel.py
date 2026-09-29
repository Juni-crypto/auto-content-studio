"""Kinetic news reels (HyperFrames) from a JSON spec, in any brand theme.

  python3 kreel.py SPEC.json THEME OUT_DIR        ->  OUT_DIR/index.html + assets (then: npx hyperframes render)

SPEC: {"voice_dir": dir with timing.json + vo-NN.wav (from voice.py), "music": wav, "kicker": {theme: text},
       "beats": [{"caption": "...", "hold": 0.4, "cues": [{"at": "word", "do": "slam" | "count" | "image" | "line" |
       "tag" | "clear", ...}]}]}
Layout (EDITING-RULES.md): one bonded column per beat, centred on y 785 inside y 350-1220, re-centred as each element
lands (existing elements glide to their new slot). Bonded pieces sit 40 px apart, stack lines 16-33 px. Captions on a
rail at y 1260 (x 60-940), dropped when they only repeat the words already on screen. Brand chrome at y 244-320 (below
Instagram's top overlay). Text is measured with the real fonts; a line that would fall below its floor wraps to two.
The hook is on screen at frame 0; camera shake only on hero moments, at least 4 s apart.
"""
import json, pathlib, random, re, shutil, subprocess, sys
from PIL import Image, ImageFont

HERE = pathlib.Path(__file__).parent
FONTS, BRANDS, SFXDIR, EMOJI = HERE / "fonts", HERE / "brands", HERE / "sfx", HERE / "emoji"
W, H, GAP, SAFE, WIDE = 1080, 1920, 0.3, 900, 940
TOP, BOTTOM, MID, CAP_Y = 350, 1220, 785, 1260   # content zone, its centre, caption rail
BOND = 40                                        # gap between pieces that belong together
FLOOR = {"hero": 150, "stack": 140, "head": 90, "label": 44}
THEMES = {
    "techdesk": dict(name="TECHDESK", tile="techdesk-tile.png", tagline="Tech news, shipped fast.", tile_rot=-3,
                     bg="radial-gradient(ellipse at 50% 35%,#1f1f1f 0%,#121212 70%)", ink="#F2EFE8", dim="#F2EFE899",
                     accent="#FF5B1F", accent2="#FFD23F", head="barlow-condensed-latin-800-italic.woff2", upper=True,
                     label="jetbrains-mono-latin-700-normal.woff2", head_shadow="0 8px 24px #000a", grain=0.16,
                     cap_swipe="#FF5B1F", motif="streak", slam_sfx="stamp", solid="#161616"),
    "push": dict(name="push", tile="push-tile.png", tagline="The notification worth getting.", tile_rot=0,
                 bg="linear-gradient(180deg,#3957FF 0%,#2B4BFF 45%,#2141E6 100%)", ink="#FFFFFF", dim="#FFFFFFBB",
                 accent="#FF4B3E", accent2="#FFC83D", head="m-plus-rounded-1c-latin-800-normal.woff2", upper=False,
                 label="m-plus-rounded-1c-latin-700-normal.woff2", head_shadow="0 10px 30px #0b1a8a55", grain=0.04,
                 cap_swipe="#FF4B3E", motif="badge", slam_sfx="ding", solid="#2B4BFF"),
    "breakpoint": dict(name="BREAKPOINT", tile="breakpoint-tile.png", tagline="Tech news that stops you.", tile_rot=0,
                       bg="#0F0F0F", ink="#F3F1EC", dim="#9A9A9A", accent="#FF2D2D", accent2="#F3F1EC",
                       head="inter-latin-800-normal.woff2", upper=False, label="jetbrains-mono-latin-500-normal.woff2",
                       head_shadow="none", grain=0.07, cap_swipe="#FF2D2D", motif="dot", slam_sfx="tick", solid="#0F0F0F"),
    "sportsdesk": dict(name="SPORTS DESK", tile="sportsdesk-tile.png", tagline="First. Every time.", tile_rot=-3,
                      bg="#111111", ink="#FFF6E5", dim="#FFF6E5AA", accent="#E6007E", accent2="#FFB300",
                      head="anton-latin-400-normal.woff2", upper=True, label="barlow-condensed-latin-700-normal.woff2",
                      head_shadow="0 6px 0 #000, 0 14px 30px #000c", grain=0.14, cap_swipe="#E6007E", motif="burst",
                      slam_sfx="stamp", plate="plate-crowd.png", solid="#111111"),
    "bizdesk": dict(name="BIZDESK", tile="bizdesk-tile.png", tagline="Bizdesk samjho, duniya samjho.", tile_rot=-3,
                    bg="radial-gradient(ellipse at 50% 35%,#FFD23A 0%,#F5B800 70%,#E0A200 100%)", ink="#141414", dim="#141414AA",
                    accent="#E0262B", accent2="#1F4FB8", head="YatraOne-Regular.ttf", upper=False, label="Baloo2-ExtraBold.ttf",
                    head_shadow="5px 5px 0 #FFFFFF, 9px 9px 0 #E0262B", grain=0.12, cap_swipe="#FFFFFF", motif="none",
                    slam_sfx="stamp", solid="#F5B800", cap_shadow="3px 3px 0 #fff"),
}


class Reel:
    def __init__(self, spec_path, theme, out):
        self.spec_path = pathlib.Path(spec_path).resolve(); self.spec = json.loads(self.spec_path.read_text())
        self.th, self.t, self.outdir = theme, THEMES[theme], pathlib.Path(out)
        self.vdir = (self.spec_path.parent / self.spec["voice_dir"]).resolve()
        self.T = json.loads((self.vdir / "timing.json").read_text())
        gap = 0.0 if self.T and self.T[0].get("cont") else GAP   # one continuous take: beats play back to back
        self.S, t = [], 0.0                       # the hook starts at frame 0
        for b, sb in zip(self.T, self.spec["beats"]):
            self.S.append(round(t, 3)); t += b["dur"] + gap + sb.get("hold", 0)
        self.end = t - gap
        self.has_outro = any(c.get("do") == "outro" for sb in self.spec["beats"] for c in sb.get("cues", []))
        self.total = round(self.end + (1.8 if self.has_outro else 3.2), 3)
        self.html, self.js, self.audio, self.live = [], [], [], []
        self.fx, self.n, self.sfx_len, self.assets = 0, 0, {}, {}
        self.col, self.base, self.off = [], {}, {}  # the content column: entries, slot base y, current offset
        self.slot_html = {}                         # element id -> index of its slot div in self.html (frame-0 hook baking)
        self.entry, self.words_on, self.t_out, self.labels = {}, {}, {}, set()
        self.log, self.last_shake, self.cur, self.elem, self.slotted = [], -10.0, 0, {}, set()
        self.em_n = 0
        self.room = 860 if theme == "breakpoint" else WIDE   # breakpoint keeps its red gutter dot clear
        self.left = 110 if theme == "breakpoint" else 40
        self.digw = max(self.font("head", 100).getlength(d) for d in "0123456789") / 100 + 0.03

    # ---------- measuring ----------
    def font(self, kind, size):
        return ImageFont.truetype(str(FONTS / self.t["head" if kind == "head" else "label"]), max(1, round(size)))

    def text_w(self, text, size, kind="head"):
        s = text.upper() if (kind == "head" and self.t["upper"]) else text
        return self.font(kind, size).getlength(s)

    def fit(self, text, size, kind="head", room=SAFE):
        tw = self.text_w(text, size, kind)
        if tw > room: size = int(size * room / tw); tw = self.text_w(text, size, kind)
        return size, tw

    def fit_wrap(self, text, size, kind, room, floor):
        """One line if it stays at or above `floor`; otherwise two balanced lines (never shrink below the floor to fit)."""
        s1, tw = self.fit(text, size, kind, room)
        if s1 >= floor or " " not in text.strip(): return s1, [text], tw
        words = text.split(" "); best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            m = max(self.text_w(a, size, kind), self.text_w(b, size, kind))
            if best is None or m < best[0]: best = (m, a, b)
        m, a, b = best; s2 = min(size, int(size * room / m))
        return (s2, [a, b], m * s2 / size) if s2 > s1 else (s1, [text], tw)

    # ---------- timeline plumbing ----------
    def at(self, i, token, nth=0):
        if isinstance(token, (int, float)): return round(self.S[i] + token, 3)
        hits = [w for w in self.T[i]["words"] if w["w"].lower().strip('.,?!":;').startswith(token.lower())]
        if not hits: raise SystemExit(f"beat {i + 1}: cue word '{token}' not in caption")
        return round(self.S[i] + hits[min(nth, len(hits) - 1)]["s"], 3)

    def uid(self, p="e"):
        self.n += 1; return f"{p}{self.n}"

    def sfx(self, name, t, vol=0.5):
        f = SFXDIR / f"{name}.wav"
        if name not in self.sfx_len:
            self.sfx_len[name] = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))
            self.assets[f"sfx/{name}.wav"] = f
        self.fx += 1
        self.audio.append(f'<audio id="fx{self.fx}" src="assets/sfx/{name}.wav" data-start="{max(t, 0):.3f}" data-duration="{self.sfx_len[name]:.3f}" data-volume="{vol}"></audio>')

    def shake(self, t):
        if t - self.last_shake >= 4.0:   # loud accents only on hero moments, at least 4 s apart
            self.js.append(f"shakes.push({t:.3f});"); self.last_shake = t

    @staticmethod
    def norm_words(text):
        return {w for w in (re.sub(r"[^a-z0-9]", "", x.lower()) for x in re.split(r"[\s·/–-]+", text)) if w}

    # ---------- the bonded column ----------
    def layout(self):
        order = sorted(self.col, key=lambda e: (e["order"], e["seq"]))
        gaps, total = [], 0.0
        for k, e in enumerate(order):
            g = 0 if k == 0 else (max(16, 0.1 * min(e["size"], order[k - 1]["size"])) if e.get("stack") and e.get("stack") == order[k - 1].get("stack") else BOND)
            gaps.append(g); total += g + e["h"]
        y = MID - total / 2
        y = TOP if total > BOTTOM - TOP else max(TOP, min(y, BOTTOM - total))
        pos = {}
        for e, g in zip(order, gaps):
            y += g; pos[e["id"]] = y; y += e["h"]
        return pos, total

    def room_left(self, drop_zone=None, extra=0):
        """Height still free in the content zone for one more piece (after the pieces it will replace leave)."""
        keep = [e for e in self.col if not (drop_zone and e.get("zone") == drop_zone) and e["id"] not in self.labels]
        return (BOTTOM - TOP) - sum(e["h"] for e in keep) - BOND * len(keep) - extra

    def place(self, id_, inner, h, t, zone=None, order=None, size=100, stack=None, words="", is_text=False):
        if zone:   # one piece per zone: the new one replaces the old (but a stack keeps its own lines)
            old = [e["id"] for e in self.col if e.get("zone") == zone and not (stack and e.get("stack") == stack)]
            if old: self.out(old, t - 0.26)
        if zone == "mid" and stack is None:
            lab = [e["id"] for e in self.col if e["id"] in self.labels]
            if lab: self.out(lab, t - 0.26)
        self.col.append({"id": id_, "h": h, "order": order if order is not None else {"top": 0, "mid": 1, "low": 2}.get(zone, 1),
                         "seq": self.n, "zone": zone, "size": size, "stack": stack, "text": is_text})
        pos, total = self.layout()
        self.slot_html[id_] = len(self.html)
        self.html.append(f'<div class="slot" id="s{id_}" style="top:{pos[id_]:.0f}px;height:{h:.0f}px">{inner}</div>')
        self.base[id_], self.off[id_] = pos[id_], 0.0
        for e in self.col:   # everything already on screen glides to its new slot
            if e["id"] == id_: continue
            no = pos[e["id"]] - self.base[e["id"]]
            if abs(no - self.off[e["id"]]) > 1:
                if t <= 0.12 and e["id"] in self.slot_html:   # the frame-0 hook: bake the final slot into the page (a set at time 0
                    k = self.slot_html[e["id"]]                  # is lost when the renderer seeks to frame 0)
                    self.html[k] = re.sub(r"top:-?[0-9]+px", f"top:{pos[e['id']]:.0f}px", self.html[k], count=1)
                    self.base[e["id"]], no = pos[e["id"]], 0.0
                else:
                    self.js.append(f'tl.fromTo("#s{e["id"]}",{{y:{self.off[e["id"]]:.0f}}},{{y:{no:.0f},duration:0.28,ease:"power3.out",immediateRender:false}},{t - 0.06:.3f});')
                self.off[e["id"]] = no
        self.live.append(id_); self.entry[id_] = t; self.slotted.add(id_)
        self.elem[id_] = (t, h, is_text, size)
        self.last_placed = id_
        if words: self.words_on[id_] = (self.norm_words(words), t)
        self.log.append((t, total, len(self.col), is_text and len(self.col) == 1 and size < FLOOR["hero"]))

    def out(self, ids, t):
        ids = [i for i in ids if i in self.live]
        if not ids: return
        t = max([t] + [self.entry.get(i, 0) + 0.35 for i in ids])   # never leave before arriving
        arr = ",".join(f'"#s{i}"' if i in self.slotted else f'"#{i}"' for i in ids)
        self.js.append(f'tl.fromTo([{arr}],{{xPercent:0,yPercent:0}},{{yPercent:-120,opacity:0,filter:"blur(10px)",duration:0.18,ease:"power2.in"}},{t:.3f});')
        self.live = [i for i in self.live if i not in ids]
        self.col = [e for e in self.col if e["id"] not in ids]
        for i in ids: self.t_out[i] = t

    def clear(self, t, dx=0):
        if not self.live: return
        t = max([t] + [self.entry.get(i, 0) + 0.35 for i in self.live])
        arr = ",".join(f'"#s{i}"' if i in self.slotted else f'"#{i}"' for i in self.live)
        if self.th == "push": dx = 1 if dx >= 0 else -1   # swiped away sideways, like a dismissed notification
        xp, yp = (-150 if dx < 0 else 150 if dx > 0 else 0), (0 if dx else -220)
        self.js.append(f'tl.fromTo([{arr}],{{xPercent:0,yPercent:0}},{{xPercent:{xp},yPercent:{yp},opacity:0,filter:"blur(12px)",duration:0.22,ease:"power4.in"}},{t:.3f});')
        for i in self.live: self.t_out[i] = t
        self.sfx("whoosh", t - 0.05, 0.3)
        self.transition(t)
        self.live, self.col = [], []
        self.log.append((t + 0.22, 0, 0, False))

    def transition(self, t):
        """Each brand's own scene-change signature (under the content, never over the new headline)."""
        id_ = self.uid("tx")
        if self.th == "techdesk":      # a hazard tape slaps across the frame
            self.html.append(f'<div class="txtape" id="{id_}">{" · ".join(["PATCH 0927"] * 6)}</div>')
            self.js.append(f'tl.fromTo("#{id_}",{{x:-2200}},{{x:1400,duration:0.42,ease:"power2.inOut"}},{t - 0.08:.3f});')
        elif self.th == "breakpoint":  # a red debugger step line scans the frame
            self.html.append(f'<div class="txscan" id="{id_}"></div>')
            self.js.append(f'tl.fromTo("#{id_}",{{opacity:0}},{{opacity:1,duration:0.01}},{t - 0.02:.3f});'
                           f'tl.fromTo("#{id_}",{{y:0}},{{y:1060,duration:0.3,ease:"power2.in"}},{t - 0.02:.3f});'
                           f'tl.to("#{id_}",{{opacity:0,duration:0.05}},{t + 0.3:.3f});')
        elif self.th == "sportsdesk":   # stadium flash, peaking on the cut
            self.html.append(f'<div class="txflash" id="{id_}"></div>')
            self.js.append(f'tl.fromTo("#{id_}",{{opacity:0}},{{opacity:0.3,duration:0.06}},{t - 0.02:.3f});tl.to("#{id_}",{{opacity:0,duration:0.25}},{t + 0.04:.3f});')
            self.motif_js(t, None)

    # ---------- entrances (anything landing in the first 0.35 s is already on screen at frame 0) ----------
    def instant(self, id_, t):
        if t > 0.35: return False
        self.js.append(f'tl.fromTo("#{id_}",{{opacity:1,scale:1.05}},{{opacity:1,scale:1,duration:0.25,ease:"power2.out"}},0);')
        return True

    def slam_in(self, id_, t, width, rot=0, scale=1.6, sound=None, vol=0.5, hero=False):
        if self.instant(id_, t): return
        scale = min(scale, 1 + 260 / max(width, 1))   # never overflow the frame on entry
        self.js.append(f'tl.fromTo("#{id_}",{{scale:{scale:.2f},opacity:0,rotation:{rot - 4},filter:"blur(10px)"}},'
                       f'{{scale:1,opacity:1,rotation:{rot},filter:"blur(0px)",duration:0.26,ease:"power4.out"}},{t:.3f});')
        if hero: self.shake(t + 0.18)
        if sound: self.sfx(sound, t + 0.04, vol)

    def pop_in(self, id_, t, rot=0, sound="pop"):
        if self.instant(id_, t): return
        self.js.append(f'tl.fromTo("#{id_}",{{scale:0.3,opacity:0,rotation:{rot - 10}}},{{scale:1,opacity:1,rotation:{rot},duration:0.32,ease:"back.out(1.7)"}},{t:.3f});')
        if sound: self.sfx(sound, t, 0.35)

    def rise_in(self, id_, t, rot=0):
        if self.instant(id_, t): return
        self.js.append(f'tl.fromTo("#{id_}",{{y:60,opacity:0,rotation:{rot}}},{{y:0,opacity:1,rotation:{rot},duration:0.3,ease:"power3.out"}},{t:.3f});')

    # ---------- brand flourishes (inside the slot, so they travel with their line) ----------
    def motif_html(self, size, h):
        m = self.t["motif"]
        if m == "streak":
            i = self.uid("st"); return i, f'<div class="streak" id="{i}" style="top:{size * 0.1:.0f}px;height:{size * 0.8:.0f}px"></div>'
        if m == "dot":
            i = self.uid("dot"); return i, f'<div class="bpdot" id="{i}" style="top:{h / 2 - 17:.0f}px"><i></i></div>'
        return None, ""

    def motif_js(self, t, mid):
        m = self.t["motif"]
        if m == "streak" and mid:
            self.js.append(f'tl.fromTo("#{mid}",{{x:-700,opacity:0}},{{x:0,opacity:1,duration:0.18,ease:"power3.out"}},{t - 0.06:.3f});'
                           f'tl.fromTo("#{mid}",{{scaleY:1}},{{scaleY:0.08,opacity:0,duration:0.4,ease:"power2.in"}},{t + 0.3:.3f});')
        elif m == "dot" and mid:
            self.js.append(f'tl.fromTo("#{mid}",{{scale:0,opacity:0}},{{scale:1,opacity:1,duration:0.25,ease:"back.out(3)"}},{t - 0.04:.3f});'
                           f'tl.fromTo("#{mid} i",{{scale:1,opacity:0.9}},{{scale:3.2,opacity:0,duration:0.7,ease:"power2.out"}},{t:.3f});')
        elif m == "burst":
            self.js.append(f'tl.fromTo("#burst",{{opacity:0.35,scale:1}},{{opacity:0.9,scale:1.08,duration:0.12,ease:"power2.out"}},{t:.3f});'
                           f'tl.fromTo("#burst",{{opacity:0.9,scale:1.08}},{{opacity:0.35,scale:1,duration:0.6,ease:"power2.inOut"}},{t + 0.12:.3f});')

    def colour(self, c):
        if c.get("accent") or c.get("color") == "accent": return self.t["accent2"] if self.th == "push" else self.t["accent"]
        if c.get("accent2") or c.get("color") == "accent2": return self.t["accent2"]
        if c.get("dim") or c.get("color") == "dim": return self.t["dim"]
        return self.t["ink"]

    def word_html(self, id_, lines, size, kind, color, lh, cls=""):
        return (f'<div class="word {kind} {cls}" id="{id_}" style="left:{self.left}px;top:0;width:{W - 2 * self.left}px;'
                f'font-size:{size}px;line-height:{lh};color:{color}">{"<br>".join(lines)}</div>')

    # ---------- cues ----------
    def c_slam(self, c, t):
        zone = c.get("zone", "top"); want = c.get("size", 190 if zone == "top" else 300)
        size, lines, tw = self.fit_wrap(c["text"], want, "head", self.room, FLOOR["hero"])
        lh = 1.02 if len(lines) == 1 else 0.95
        h_text = size * lh * len(lines); h = h_text + (54 if c.get("underline") else 0)
        free = self.room_left(zone)
        if h > free and free > 120:   # squeeze to fit what's left of the column
            k = free / h; size = int(size * k); h_text = size * lh * len(lines); h = h_text + (54 if c.get("underline") else 0); tw *= k
        id_ = self.uid("w"); mid, mhtml = self.motif_html(size, h_text)
        inner = mhtml + self.word_html(id_, lines, size, "head", self.colour(c), lh)
        u = None
        if c.get("underline"):
            u = self.uid("u"); uw = min(tw, self.room) * 0.86; x = 540 - uw / 2 - 10
            inner += (f'<svg class="mark" id="{u}" style="left:{x:.0f}px;top:{h_text + 6:.0f}px;width:{uw + 20:.0f}px;height:40px" viewBox="0 0 {uw + 20:.0f} 40">'
                      f'<path d="M10 24 C {uw * 0.3:.0f} 10, {uw * 0.65:.0f} 32, {uw + 10:.0f} 16" fill="none" stroke="{self.t["accent2"] if self.th != "breakpoint" else self.t["accent"]}" stroke-width="12" stroke-linecap="round"/></svg>')
        self.place(id_, inner, h, t, zone=zone, size=size, words=c["text"], is_text=True)
        self.motif_js(t, mid)
        self.slam_in(id_, t - 0.04, tw, rot=c.get("rot", 0), scale=c.get("scale", 1.6), sound=self.t["slam_sfx"], vol=0.5, hero=(zone == "mid"))
        if u: self.js.append(f'drawOn(tl,"#{u} path",{max(t + 0.3, 0.05):.3f},0.3);'); self.sfx("marker", t + 0.3, 0.25)

    def c_line(self, c, t):
        zone = c.get("zone", "low"); kind = c.get("font", "label")
        want = c.get("size", 56 if kind == "label" else 104); floor = FLOOR["label"] if kind == "label" else FLOOR["head"]
        room = 900 if kind == "label" else self.room
        size, lines, tw = self.fit_wrap(c["text"], want, kind, room, floor)
        lh = 1.1 if kind == "label" else (1.02 if len(lines) == 1 else 0.95)
        h = size * lh * len(lines); id_ = self.uid("w")
        self.place(id_, self.word_html(id_, lines, size, kind, self.colour(c), lh, "wrap" if kind == "label" else ""), h, t, zone=zone,
                   size=size, words=c["text"], is_text=True)
        if c.get("_label"): self.labels.add(id_)
        self.rise_in(id_, t - 0.05, rot=c.get("rot", 0))

    def c_count(self, c, t):
        zone = c.get("zone", "mid"); size = c.get("size", 380)
        frm, to = c.get("from", 0), c["to"]; pre, suf = c.get("prefix", ""), c.get("suffix", "")
        digits = str(to); badge = self.t["motif"] == "badge"

        def width(sz):
            extra = sum(self.text_w(p, sz * 0.6) + 20 for p in (pre, suf) if p)
            return len(digits.replace(".", "")) * self.digw * sz + (digits.count(".") * 0.3 * sz) + extra + (60 if badge else 0)
        if width(size) > self.room - 40: size = int(size * (self.room - 40) / width(size))
        free = self.room_left(zone, extra=(60 + BOND) if c.get("label") else 0)
        if size * 1.2 > free: size = int(free / 1.2)
        x = round((W - width(size)) / 2)
        fs = str(frm).rjust(len(digits), "0"); cols = []; id_ = self.uid("n"); dur = c.get("dur", 0.8)
        for k, (a, b) in enumerate(zip(fs, digits)):
            if b == ".":
                cols.append('<span class="dotc">.</span>'); continue
            a = int(a) if a.isdigit() else 0; b = int(b)
            steps = (b - a) % 10 + (10 if k < len(digits) - 2 and a != b else 0)
            strip = "".join(f"<span>{(a + j) % 10}</span>" for j in range(steps + 1))
            cols.append(f'<span class="col"><span class="strip" id="{id_}c{k}">{strip}</span></span>')
            self.js.append(f'tl.fromTo("#{id_}c{k}",{{y:0}},{{y:{-steps * size * 1.2:.1f},duration:{dur:.2f},ease:"power3.inOut"}},{max(t, 0.02):.3f});')
        p1 = f'<span class="pre">{pre}</span>' if pre else ""; s1 = f'<span class="pre">{suf}</span>' if suf else ""
        color = "#fff" if badge else self.colour(c)
        inner = f'<div class="odo{" badge" if badge else ""}" id="{id_}" style="left:{x}px;top:0;font-size:{size}px;color:{color}">{p1}{"".join(cols)}{s1}</div>'
        self.place(id_, inner, size * 1.2, t, zone=zone, size=size, words=f"{pre}{to}{suf}", is_text=True)
        if not self.instant(id_, t - 0.08):
            self.js.append(f'tl.fromTo("#{id_}",{{opacity:0,scale:0.8}},{{opacity:1,scale:1,duration:0.25,ease:"back.out(2)"}},{t - 0.08:.3f});')
        for k in range(4): self.sfx("tick", t + k * dur / 4, 0.2)
        if c.get("label"):
            self.c_line({"text": c["label"], "zone": "low", "_label": True}, t + min(dur, 0.5))

    def c_image(self, c, t):
        zone = c.get("zone", "mid"); src = (self.spec_path.parent / c["img"]).resolve(); kind = c.get("kind", "photo")
        name = f"img/{src.name}"; self.assets[name] = src
        iw, ih = Image.open(src).size
        bonded = any(e.get("zone") != zone and e["id"] not in self.labels for e in self.col)
        if kind == "logo":   # logos read at 440+ px bonded, 560+ alone
            w = max(c.get("w", 0), 440 if bonded else 560); pad = 56
        else:
            w = max(c.get("w", 0), 760); pad = 0
        box_w = w + 2 * pad; box_h = w * ih / iw + 2 * pad
        maxh = min(560 if bonded else 700, self.room_left(zone, extra=0 if not c.get("expect_below") else 160))
        if kind == "bleed": box_w, box_h, pad = W, min(c.get("h", 700), maxh), 0
        elif box_h > maxh: s = maxh / box_h; box_w, box_h, w, pad = box_w * s, maxh, w * s, pad * s
        x = round((W - box_w) / 2); id_ = self.uid("i"); rot = c.get("rot", {"techdesk": -2, "sportsdesk": 3}.get(self.th, 0))
        tape = ('<i class="tape" style="left:-40px;top:-14px;transform:rotate(-30deg)"></i><i class="tape" style="right:-40px;bottom:-14px;transform:rotate(-30deg)"></i>'
                if self.th == "techdesk" and kind == "photo" else "")
        inner = (f'<div class="img {kind} {self.th}" id="{id_}" style="left:{x}px;top:0;width:{box_w:.0f}px;height:{box_h:.0f}px;padding:{pad:.0f}px">'
                 f'<img src="assets/{name}">{tape}</div>')
        self.place(id_, inner, box_h + 20, t, zone=zone, size=400)
        if kind == "bleed" and t <= 0.35:   # the hook image is already there at frame 0
            self.js.append(f'tl.fromTo("#{id_} img",{{x:-24,scale:1.08}},{{x:24,scale:1.02,duration:4,ease:"none"}},0);'); return
        if kind == "bleed":
            self.js.append(f'tl.fromTo("#{id_}",{{clipPath:"inset(0% 100% 0% 0%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:0.4,ease:"power3.out"}},{max(t - 0.1, 0):.3f});'
                           f'tl.fromTo("#{id_} img",{{x:-24,scale:1.08}},{{x:24,scale:1.02,duration:4,ease:"none"}},{max(t - 0.1, 0):.3f});')
            self.sfx("whoosh", t - 0.12, 0.3); return
        self.js.append(f'tl.set("#{id_}",{{rotation:{rot}}},0);')
        self.pop_in(id_, t - 0.05, rot=rot, sound="pop")

    def c_tag(self, c, t):
        zone = c.get("zone", "top"); style = {"techdesk": "tape", "push": "notify", "breakpoint": "code", "sportsdesk": "pill", "bizdesk": "pill"}[self.th]
        id_ = self.uid("g"); msg = c["text"]
        if style == "notify":
            size, _ = self.fit(msg, 46, "head", 690); h = 156
            inner = (f'<div class="notify" id="{id_}" style="top:0"><b class="ico"><i></i></b><div><small>{c.get("title", "push · now")}</small>'
                     f'<p style="font-size:{size}px">{msg}</p></div></div>')
        elif style == "tape":
            size, tw = self.fit(msg, 64, "head", 820); h = size * 1.2 + 24
            inner = f'<div class="htape" id="{id_}" style="top:0;left:{round(540 - tw / 2 - 40)}px;font-size:{size}px">{msg}</div>'
        elif style == "code":
            size, tw = self.fit(msg, 48, "label", 820); h = size * 1.3
            inner = f'<div class="code" id="{id_}" style="top:0;left:{round(540 - (tw + 52) / 2)}px;font-size:{size}px"><i></i><span class="msg">{msg}</span></div>'
        else:
            size, tw = self.fit(msg.upper(), 60, "label", 860); h = size * 1.2 + 20
            inner = f'<div class="pill" id="{id_}" style="top:0;left:{round(540 - tw / 2 - 38)}px;font-size:{size}px">{msg}</div>'
        self.place(id_, inner, h, t, zone=zone, size=size, words=msg, is_text=True)
        if self.instant(id_, t): return
        if style == "notify":
            self.js.append(f'tl.fromTo("#{id_}",{{y:-260,opacity:0}},{{y:0,opacity:1,duration:0.45,ease:"back.out(1.6)"}},{t - 0.1:.3f});'); self.sfx("ding", t - 0.05, 0.45)
        elif style == "tape":
            self.js.append(f'tl.fromTo("#{id_}",{{scaleX:0,rotation:-4}},{{scaleX:1,rotation:-4,duration:0.25,ease:"power4.out"}},{t - 0.06:.3f});'); self.sfx("whoosh", t - 0.1, 0.3)
        elif style == "code":
            self.js.append(f'tl.fromTo("#{id_}",{{opacity:0}},{{opacity:1,duration:0.05}},{t - 0.05:.3f});typeOn(tl,"#{id_} .msg",{t:.3f},0.5);'); self.sfx("tick", t, 0.3)
        else:
            self.pop_in(id_, t - 0.05, sound="pop")

    def emoji_img(self, name):
        self.assets[f"emoji/{name}.png"] = EMOJI / f"{name}.png"
        return f"assets/emoji/{name}.png"

    def free_band(self, sz):
        """A vertical band (y0, y1) at least sz tall where an emoji can float without touching the column's words:
        below the block (above the caption rail) first, then above it (below the brand chrome)."""
        if not self.col: return (TOP, BOTTOM - sz)
        pos, _ = self.layout()
        top = min(pos[e["id"]] for e in self.col); bot = max(pos[e["id"]] + e["h"] for e in self.col)
        for y0, y1 in ((bot + 24, CAP_Y - 12), (TOP - 20, top - 24)):
            if y1 - y0 >= sz: return (y0, y1)
        return None

    def c_emoji(self, c, t):
        """Real emojis float up beside the content like live reactions (they never cover the words)."""
        names = c["e"] if isinstance(c["e"], list) else [c["e"]]
        n = c.get("n", 3); side = c.get("side", "both"); big = c.get("big", False)
        r = random.Random(self.em_n * 7919 + 17)
        for k in range(n):
            self.em_n += 1; i = f"em{self.em_n}"; nm = names[k % len(names)]
            sz = (240 if big else r.randint(120, 170)) * (1 if k == 0 else 0.85)
            sd = side if side != "both" else ("left" if k % 2 == 0 else "right")
            x = r.randint(60, 200) if sd == "left" else r.randint(W - 200 - int(sz), W - 60 - int(sz))
            if sd == "right": x = min(x, 940 - int(sz))                   # clear of Instagram's right-hand buttons
            rise = r.randint(260, 420)
            band = self.free_band(sz)                                     # free room above/below the words, or None
            if band is None: continue                                     # no room: skip it rather than cover text
            y = r.randint(int(band[0]), int(max(band[0], band[1] - sz)))
            rise = max(30, min(rise, y - band[0]))                        # float up, but stop before the words
            self.html.append(f'<img class="emo" id="{i}" src="{self.emoji_img(nm)}" style="left:{x}px;top:{y}px;width:{sz:.0f}px">')
            tk = t + k * 0.14; rot = r.randint(-18, 18); life = c.get("life", 1.6)
            self.js.append(f'tl.fromTo("#{i}",{{scale:0,opacity:0,rotation:{rot - 20}}},{{scale:1,opacity:1,rotation:{rot},duration:0.34,ease:"back.out(2.4)"}},{tk:.3f});'
                           f'tl.fromTo("#{i}",{{y:0,x:0}},{{y:{-rise},x:{r.randint(-40, 40)},duration:{life:.2f},ease:"sine.out",immediateRender:false}},{tk:.3f});'
                           f'tl.to("#{i}",{{opacity:0,scale:0.8,duration:0.3}},{tk + life - 0.3:.3f});')
        self.sfx("pop", t, 0.3)

    def c_outro(self, c, t):
        """End card: brand tile, tagline, a Follow button that gets tapped, and a 'catch you later' sign-off."""
        T = self.t
        if self.col: self.out([e["id"] for e in self.col], t - 0.26)
        ti = Image.open(BRANDS / T["tile"]); tw_ = 440; th_ = tw_ * ti.height / ti.width   # leaves room for button + sign-off
        e = self.uid("end")
        self.place(e, f'<img class="endtile" id="{e}" src="assets/brand/{T["tile"]}" style="left:{(W - tw_) / 2:.0f}px;top:0;width:{tw_}px">', th_, t, order=0, size=400)
        self.pop_in(e, t, rot=T["tile_rot"], sound="pop")
        tf = self.at(self.cur, c.get("follow_at", "follow")) if c.get("follow_at", "follow") else t + 0.6
        fb = self.uid("fb"); acc = T["accent"] if self.th != "push" else "#FF4B3E"
        inner = (f'<div class="follow" id="{fb}" style="background:{acc}"><span class="f1">+ Follow</span><span class="f2">Following ✓</span>'
                 f'<i class="tap" id="{fb}t"></i></div>')
        self.place(fb, inner, 150, tf, order=1, size=90, words="follow")
        self.js.append(f'tl.fromTo("#{fb}",{{scale:0.4,opacity:0}},{{scale:1,opacity:1,duration:0.35,ease:"back.out(2)"}},{tf - 0.05:.3f});'
                       f'tl.fromTo("#{fb}t",{{scale:0,opacity:0.9}},{{scale:3,opacity:0,duration:0.5,ease:"power2.out"}},{tf + 0.7:.3f});'
                       f'tl.fromTo("#{fb}",{{scale:1}},{{scale:0.92,duration:0.08,yoyo:true,repeat:1,immediateRender:false}},{tf + 0.7:.3f});'
                       f'tl.fromTo("#{fb}",{{backgroundColor:"{acc}"}},{{backgroundColor:"#2a2a2a",duration:0.15,immediateRender:false}},{tf + 0.78:.3f});'
                       f'tl.fromTo("#{fb} .f1",{{opacity:1}},{{opacity:0,duration:0.1,immediateRender:false}},{tf + 0.78:.3f});'
                       f'tl.fromTo("#{fb} .f2",{{opacity:0}},{{opacity:1,duration:0.15,immediateRender:false}},{tf + 0.82:.3f});')
        self.sfx("ding", tf + 0.72, 0.4)
        tc = self.at(self.cur, c.get("catch_at", "catch"))
        self.c_line({"text": c.get("signoff", "Catch you later"), "font": "head", "size": 96, "zone": None, "color": "accent2"}, tc)
        self.c_emoji({"e": ["wave", "peace"], "n": 2, "side": "left"}, tc + 0.2)
        if self.spec.get("end_note"):
            nt = self.uid("w"); size, lines, _ = self.fit_wrap(self.spec["end_note"], 30, "label", 940, 30)
            self.html.append(f'<div class="word label wrap" id="{nt}" style="left:70px;top:1330px;width:940px;font-size:{size}px;line-height:1.2;color:{T["dim"]}">{"<br>".join(lines)}</div>')
            self.live.append(nt); self.entry[nt] = t + 0.4; self.rise_in(nt, t + 0.4)

    def stack_start(self, c, t):
        """A stack owns the whole column: clear it, then plan line sizes so the finished stack fits."""
        if self.col: self.out([e["id"] for e in self.col], t - 0.26)
        lh = 0.92; plan = []
        for l in c["lines"]:
            size, lines, tw = self.fit_wrap(l["text"], l.get("max", c.get("max", 330)), "head", self.room, FLOOR["stack"])
            plan.append([size, lines, tw])
        def total(p): return sum(z * lh * len(ls) for z, ls, _ in p) + sum(max(16, 0.1 * z) for z, _, _ in p[1:])
        if total(plan) > BOTTOM - TOP:
            k = (BOTTOM - TOP) / total(plan); plan = [[int(z * k), ls, tw * k] for z, ls, tw in plan]
        c["_plan"], c["_sid"] = plan, self.uid("stk")

    def stack_line(self, c, k, t):
        lh = 0.92; size, lines, tw = c["_plan"][k]; l = c["lines"][k]
        id_ = self.uid("k"); h = size * lh * len(lines); mid, mhtml = self.motif_html(size, h)
        self.place(id_, mhtml + self.word_html(id_, lines, size, "head", self.colour(l), lh, "stk"), h, t, zone="mid", order=1, size=size,
                   stack=c["_sid"], words=l["text"], is_text=True)
        if k == 0 and len(c["lines"]) > 1 and len(self.col) == 1 and size < 210 and not c.get("together"):
            # alone: land at hero size, shrink into its slot later (not when the lines land together, e.g. the frame-0 hook)
            sc = min(210 / size, (self.room - 20) / max(tw, 1), 1.8)
            if sc > 1.05:
                self.js.append(f'tl.set("#s{id_}",{{scale:{sc:.2f}}},0);'); c["_lone"] = (id_, sc)
                v = self.elem[id_]; self.elem[id_] = (v[0], v[1] * sc, v[2], v[3] * sc)
        if k == 1 and c.get("_lone"):
            i0, sc = c.pop("_lone"); self.js.append(f'tl.fromTo("#s{i0}",{{scale:{sc:.2f}}},{{scale:1,duration:0.26,ease:"power3.out",immediateRender:false}},{t - 0.06:.3f});')
        if self.th == "push":
            self.pop_in(id_, t - 0.05, sound="ding" if k == 0 else "pop")
        elif self.th == "breakpoint":
            self.motif_js(t, mid)
            if not self.instant(id_, t): self.js.append(f'tl.fromTo("#{id_}",{{y:40,opacity:0}},{{y:0,opacity:1,duration:0.28,ease:"power3.out"}},{t - 0.04:.3f});')
            self.sfx("tick", t, 0.35)
        else:
            self.motif_js(t, mid); self.slam_in(id_, t - 0.04, tw, scale=1.35, sound=self.t["slam_sfx"], vol=0.45, hero=(k == 0))

    # ---------- the reel ----------
    def build(self):
        T = self.t
        kicker = self.spec.get("kicker", {}).get(self.th, "")
        self.html.append(f'<img class="tile" id="tile" src="assets/brand/{T["tile"]}">'); self.assets[f"brand/{T['tile']}"] = BRANDS / T["tile"]
        if kicker: self.html.append(f'<div class="kicker" id="kicker">{kicker}</div>')
        g = self.spec.get("greeting")
        if g:   # the brand's constant hello, on screen from frame 0 while the hook lands
            gw = self.t["accent2"] if self.th != "techdesk" else self.t["accent"]
            self.html.append(f'<div class="greet" id="greet" style="background:{gw}"><img src="{self.emoji_img(g.get("emoji", "wave"))}">{g["text"]}</div>')
            gend = self.at(0, g["until"]) if g.get("until") else 2.6
            self.js.append('tl.fromTo("#greet img",{rotation:-25},{rotation:25,duration:0.22,yoyo:true,repeat:5,ease:"sine.inOut"},0.05);'
                           f'tl.to("#greet",{{opacity:0,y:-20,duration:0.25}},{gend:.3f});')
            if kicker: self.js.append(f'tl.fromTo("#kicker",{{opacity:0}},{{opacity:1,duration:0.25}},{gend + 0.1:.3f});')
        for i, (b, sb) in enumerate(zip(self.T, self.spec["beats"])):
            self.cur = i; events = []
            for c in sb.get("cues", []):
                if c["do"] == "stack":
                    t0 = self.at(i, c["lines"][0]["at"], c["lines"][0].get("nth", 0))
                    events.append((t0, 0, "start", c, None))
                    for k, l in enumerate(c["lines"]):
                        tk = t0 if c.get("together") else max(t0, self.at(i, l["at"], l.get("nth", 0)))
                        events.append((tk + 0.001 * k, 1, "line", c, k))
                else:
                    events.append((self.at(i, c["at"], c.get("nth", 0)) + c.get("delay", 0), 1, "cue", c, None))
            events.sort(key=lambda e: (e[0], e[1]))
            if i and events:   # the old visual holds until the new beat's first visual lands
                self.clear(max(self.S[i] - 0.25, events[0][0] - 0.2), dx=sb.get("cut", (0, -1, 0, 1)[i % 4]))
            for t, _, kind, c, k in events:
                if kind == "start": self.stack_start(c, t)
                elif kind == "line": self.stack_line(c, k, t)
                elif c["do"] == "clear": self.clear(t)
                else: getattr(self, "c_" + c["do"])(c, t)
        te = self.end + 0.1
        if self.has_outro:   # the spoken outro already carries the end card
            self.checks = self.audit(self.end); self.captions()
            for i, b in enumerate(self.T):
                self.audio.append(f'<audio id="vo{i + 1}" src="assets/vo/vo-{i + 1:02d}.wav" data-start="{self.S[i]:.3f}" data-duration="{b["dur"]:.3f}" data-volume="1"></audio>')
                self.assets[f"vo/vo-{i + 1:02d}.wav"] = self.vdir / f"vo-{i + 1:02d}.wav"
            self.audio.append(f'<audio id="bgm" src="assets/music.wav" data-start="0" data-duration="{self.total:.3f}" data-volume="1"></audio>')
            return
        # end card: one group, centred
        self.clear(te - 0.2)
        ti = Image.open(BRANDS / T["tile"]); tw_, th_ = 600, 600 * ti.height / ti.width
        e = self.uid("end")
        self.place(e, f'<img class="endtile" id="{e}" src="assets/brand/{T["tile"]}" style="left:{(W - tw_) / 2:.0f}px;top:0;width:{tw_}px">', th_, te, order=0, size=400)
        self.pop_in(e, te, rot=T["tile_rot"], sound="pop")
        self.c_line({"text": T["tagline"], "font": "head", "size": 110, "zone": None, "color": "accent" if self.th != "push" else None}, te + 0.45)
        self.c_line({"text": "Follow for more", "font": "label", "size": 56, "zone": None, "dim": True}, te + 0.9)
        if self.spec.get("end_note"):
            nt = self.uid("w"); size, lines, _ = self.fit_wrap(self.spec["end_note"], 30, "label", 940, 30)
            self.html.append(f'<div class="word label wrap" id="{nt}" style="left:70px;top:1330px;width:940px;font-size:{size}px;line-height:1.2;color:{T["dim"]}">{"<br>".join(lines)}</div>')
            self.live.append(nt); self.entry[nt] = te + 1.1; self.rise_in(nt, te + 1.1)
        self.checks = self.audit(te - 0.2)
        self.captions()
        for i, b in enumerate(self.T):
            self.audio.append(f'<audio id="vo{i + 1}" src="assets/vo/vo-{i + 1:02d}.wav" data-start="{self.S[i]:.3f}" data-duration="{b["dur"]:.3f}" data-volume="1"></audio>')
            self.assets[f"vo/vo-{i + 1:02d}.wav"] = self.vdir / f"vo-{i + 1:02d}.wav"
        self.audio.append(f'<audio id="bgm" src="assets/music.wav" data-start="0" data-duration="{self.total:.3f}" data-volume="1"></audio>')

    def audit(self, end):
        """Build-time editing checks, sampled every 0.1 s from what is actually live: blank centre, thin block, lone small line."""
        warn, runs = [], {"BLANK CENTRE": None, "THIN BLOCK": None, "LONE LINE": None}
        limits = {"BLANK CENTRE": 0.8, "THIN BLOCK": 1.0, "LONE LINE": 0.6}
        steps = int(end / 0.1) + 1
        for k in range(steps + 1):
            t = k * 0.1; live = [v for i, v in self.elem.items() if v[0] <= t + 0.3 and self.t_out.get(i, 1e9) > t]
            tot = sum(v[1] for v in live) + BOND * max(0, len(live) - 1)
            hero = any((v[2] and v[3] >= 250) or (not v[2] and v[1] >= 500) for v in live)   # a big hero on its own is fine
            state = {"BLANK CENTRE": not live and k < steps, "THIN BLOCK": bool(live) and tot < 440 and not hero and k < steps,
                     "LONE LINE": len(live) == 1 and live[0][2] and live[0][3] < FLOOR["hero"] and k < steps}
            for name, on in state.items():
                if on and runs[name] is None: runs[name] = t
                if not on and runs[name] is not None:
                    if t - runs[name] > limits[name]: warn.append(f"{name} {runs[name]:.1f}-{t:.1f}s")
                    runs[name] = None
        return warn

    def captions(self):
        chunks = []
        for i, b in enumerate(self.T):
            cur = []
            for w in b["words"]:
                cur.append(w)
                if len(cur) >= 3 or w["w"].endswith((".", ",", "?", "!", ":")): chunks.append((i, cur)); cur = []
            if cur: chunks.append((i, cur))
        merged = []   # a chunk too short to read joins the one before it
        for i, ch in chunks:
            if merged and merged[-1][0] == i and (ch[-1]["e"] - ch[0]["s"] < 0.4 or ch[0]["s"] - merged[-1][1][0]["s"] < 0.4):
                merged[-1] = (i, merged[-1][1] + ch)
            else:
                merged.append((i, ch))
        chunks = merged
        starts = [self.S[i] + ch[0]["s"] for i, ch in chunks] + [10 ** 6]
        dedupe = self.spec.get("caption_dedupe", True); n_shown = 0
        for n, (i, ch) in enumerate(chunks, 1):
            s0 = self.S[i] + ch[0]["s"]; e0 = max(min(max(self.S[i] + ch[-1]["e"] + 0.1, s0 + 0.4), starts[n] - 0.02), s0 + 0.2)
            if dedupe:   # caption what adds; skip what the kinetic type already says
                cw = self.norm_words(" ".join(w["w"] for w in ch))
                on = set().union(*[ws for id_, (ws, tin) in self.words_on.items() if tin <= s0 + 0.15 and self.t_out.get(id_, 1e9) > s0 + 0.1] or [set()])
                if cw and len(cw & on) / len(cw) >= 0.6: continue
            n_shown += 1
            spans = "".join(f'<span class="cw"><i class="sw" id="sw{n}_{k}"></i><b>{w["w"]}</b></span> ' for k, w in enumerate(ch))
            self.html.append(f'<div class="clip cap" id="capclip{n}" data-start="{s0:.3f}" data-duration="{e0 - s0:.3f}" data-track-index="5"><div class="capin" id="cap{n}">{spans}</div></div>')
            self.js.append(f'tl.fromTo("#cap{n}",{{y:14,opacity:0}},{{y:0,opacity:1,duration:0.1}},{s0:.3f});')
            for k, w in enumerate(ch):
                self.js.append(f'tl.fromTo("#sw{n}_{k}",{{scaleX:0}},{{scaleX:1,duration:0.12,ease:"power2.out"}},{self.S[i] + w["s"]:.3f});')
        self.cap_stats = (n_shown, len(chunks))

    def css(self):
        T = self.t; up = "text-transform:uppercase;" if T["upper"] else ""
        plate = (f'.plate{{position:absolute;left:0;right:0;bottom:0;height:1180px;background:url(assets/brand/{T["plate"]}) center bottom/cover;opacity:.95}}'
                 f'.plate:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#111 0%,#1110 30%,#1110 40%,#111c 52%,#111c 68%,#111d 100%)}}') if T.get("plate") else ""
        return f"""
@font-face{{font-family:head;src:url(assets/fonts/{T['head']})}}
@font-face{{font-family:label;src:url(assets/fonts/{T['label']})}}
html,body{{margin:0;background:#111}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;color:{T['ink']}}}
.bg{{position:absolute;inset:0;background:{T['bg']}}}
{plate}
#burst{{position:absolute;left:-460px;top:-60px;width:2000px;height:2000px;opacity:.35;border-radius:50%;
  background:repeating-conic-gradient(from 0deg,#E6007E33 0deg 7deg,#0000 7deg 15deg,#FFB30026 15deg 21deg,#0000 21deg 30deg);
  -webkit-mask:radial-gradient(circle,#000 0%,#000a 40%,#0000 70%);mask:radial-gradient(circle,#000 0%,#000a 40%,#0000 70%)}}
.gutter{{position:absolute;left:34px;top:300px;font-family:label;font-size:30px;line-height:60px;color:#2E2E2E;white-space:pre}}
.tile{{position:absolute;right:70px;top:244px;height:76px;width:auto;border-radius:10px;box-shadow:0 10px 22px #0008;z-index:5}}
.kicker{{position:absolute;left:70px;top:262px;font-family:label;font-size:32px;letter-spacing:1px;z-index:5;{self.kicker_css()}}}
.endtile{{position:absolute;border-radius:24px;box-shadow:0 30px 60px #000a}}
.slot{{position:absolute;left:0;width:1080px;z-index:2}}
.emo{{position:absolute;z-index:1;filter:drop-shadow(0 14px 18px #0007);pointer-events:none}}   /* behind the words: reactions never cover text */
.greet{{position:absolute;left:70px;top:250px;height:74px;padding:0 30px 0 12px;border-radius:999px;display:flex;align-items:center;gap:12px;font-family:head;font-size:44px;color:#111;{'text-transform:uppercase;' if T['upper'] else ''}z-index:6;box-shadow:0 10px 24px #0008}}
.greet img{{width:62px;height:62px;transform-origin:70% 80%}}
.follow{{position:absolute;left:280px;width:520px;height:132px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-family:head;font-size:62px;color:#fff;box-shadow:0 16px 36px #0009;overflow:visible}}
.follow span{{position:absolute}}
.follow .f2{{opacity:0}}
.tap{{position:absolute;right:70px;bottom:10px;width:70px;height:70px;border-radius:50%;background:#ffffffcc;opacity:0}}
.word.wrap{{white-space:normal}}
.word{{position:absolute;line-height:1.02;white-space:nowrap;text-align:center}}
.word.head{{font-family:head;{up}text-shadow:{T['head_shadow']}}}
.word.label{{font-family:label}}
.streak{{position:absolute;left:0;width:1080px;background:repeating-linear-gradient(180deg,#0000 0 16px,{T['accent']}66 16px 22px);transform-origin:center}}
.bpdot{{position:absolute;left:74px;width:34px;height:34px;border-radius:50%;background:{T['accent']};z-index:4}}
.bpdot i{{position:absolute;inset:-6px;border:4px solid {T['accent']};border-radius:50%}}
.mark{{position:absolute;overflow:visible}}
.img{{position:absolute;box-sizing:border-box}}
.img img{{display:block;width:100%;height:100%;object-fit:contain}}
.img.photo img{{object-fit:cover;border-radius:22px}}
.img.photo{{filter:drop-shadow(0 26px 34px #000b)}}
.img.photo.push img{{border:10px solid #fff;border-radius:36px;box-sizing:border-box}}
.img.photo.breakpoint img{{border-radius:6px;outline:2px solid #F3F1EC55;outline-offset:8px}}
.img.photo.sportsdesk img{{border:12px solid #FFF6E5;border-radius:8px;box-sizing:border-box}}
.img.logo{{background:#fff;border-radius:28px;box-shadow:0 20px 40px #0008}}
.img.sticker{{filter:drop-shadow(0 22px 28px #000b)}}
.img.bleed{{overflow:hidden}}
.txtape{{position:absolute;left:0;top:780px;width:2200px;height:230px;background:{T['accent']};color:#111;font-family:head;font-size:120px;line-height:236px;white-space:nowrap;text-transform:uppercase;transform:rotate(-9deg);z-index:1;box-shadow:0 20px 50px #000a;overflow:hidden}}
.txscan{{position:absolute;left:0;right:0;top:280px;height:4px;background:{T['accent']};box-shadow:0 0 24px {T['accent']};opacity:0;z-index:6}}
.txflash{{position:absolute;inset:0;background:radial-gradient(circle at 50% 40%,#fff 0%,#FFB300aa 35%,#0000 70%);opacity:0;z-index:6;pointer-events:none}}
.img.bleed img{{object-fit:cover}}
.img.bleed:after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,{T['solid']} 0%,{T['solid']}00 20%,{T['solid']}00 72%,{T['solid']} 100%)}}
.bgw{{position:absolute;top:620px;left:0;font-family:head;font-size:560px;line-height:1;white-space:nowrap;color:transparent;-webkit-text-stroke:3px #ffffff10;text-transform:uppercase}}
.bgtape{{position:absolute;left:-400px;width:2800px;height:78px;background:#FF5B1F1c;color:#FF5B1F4d;font-family:head;font-size:46px;line-height:80px;white-space:nowrap;text-transform:uppercase;letter-spacing:4px}}
.ghost{{position:absolute;top:0;height:128px;border-radius:34px;background:linear-gradient(#ffffff30,#ffffff30) 28px 29px/70px 70px no-repeat,linear-gradient(#ffffff24,#ffffff24) 124px 36px/40% 18px no-repeat,linear-gradient(#ffffff18,#ffffff18) 124px 72px/60% 16px no-repeat,#ffffff10}}
.orb{{position:absolute;width:780px;height:780px;border-radius:50%;background:radial-gradient(circle,#ffffff24 0%,#ffffff00 65%)}}
.codebg{{position:absolute;left:112px;top:0;width:820px}}
.codebg i{{display:block;height:12px;margin:0 0 48px;border-radius:6px;background:#ffffff09}}
.minimap{{position:absolute;right:24px;top:0;width:60px}}
.minimap i{{display:block;height:5px;margin:0 0 9px;border-radius:3px;background:#ffffff12}}
.tape{{position:absolute;width:170px;height:48px;background:{T['accent']};opacity:.95;box-shadow:0 2px 6px #0005}}
.odo{{position:absolute;display:flex;align-items:flex-start;font-family:head;font-variant-numeric:tabular-nums lining-nums;overflow:hidden;height:1.2em;line-height:1.2em;text-shadow:{T['head_shadow']}}}
.odo.badge{{background:{T['accent']};border-radius:.3em;padding:0 30px;text-shadow:none;box-shadow:0 20px 40px #0b1a8a66}}
.odo .col{{display:inline-block;overflow:hidden;height:1.2em;width:{self.digw:.3f}em;text-align:center}}
.odo .dotc{{display:inline-block;width:.3em;text-align:center}}
.odo .strip{{display:flex;flex-direction:column}}
.odo .strip span{{height:1.2em;line-height:1.2em}}
.odo .pre{{font-size:.6em;line-height:2em;margin:0 10px}}
.notify{{position:absolute;left:90px;width:900px;box-sizing:border-box;display:flex;gap:26px;align-items:center;background:#fff;color:#111318;border-radius:40px;padding:30px 34px;box-shadow:0 24px 50px #0b1a8a66;z-index:4}}
.notify .ico{{position:relative;flex:0 0 96px;height:96px;border-radius:26px;background:#2B4BFF}}
.notify .ico i{{position:absolute;right:-10px;top:-10px;width:34px;height:34px;border-radius:50%;background:#FF4B3E;border:4px solid #fff}}
.notify small{{display:block;font-family:label;font-size:28px;color:#7a7f8c;margin-bottom:6px}}
.notify p{{margin:0;font-family:head;line-height:1.15;white-space:nowrap}}
.htape{{position:absolute;left:60px;padding:14px 40px 10px;background:{T['accent']};color:#111;font-family:head;{up}transform-origin:left center;box-shadow:0 10px 24px #0008;white-space:nowrap}}
.code{{position:absolute;height:1.2em;font-family:label;color:{T['ink']};white-space:nowrap;display:flex;align-items:center;gap:22px}}
.code em{{font-style:normal;color:#8a8a8a;font-size:30px;width:40px;background:{T['bg']}}}
.code i{{width:30px;height:30px;border-radius:50%;background:{T['accent']};flex:0 0 30px}}
.pill{{position:absolute;padding:12px 38px 8px;border-radius:999px;background:{T['accent2']};color:#111;font-family:label;text-transform:uppercase;white-space:nowrap;box-shadow:0 10px 24px #0008}}
.cap{{position:absolute;left:60px;right:140px;top:{CAP_Y}px;display:flex;justify-content:center;z-index:6}}
.capin{{max-width:820px;text-align:center;font-family:head;font-size:{64 if self.th != 'sportsdesk' else 72}px;line-height:1.12;{up}color:{T['ink']};text-shadow:{T.get('cap_shadow', '0 4px 16px #000c')};{'-webkit-text-stroke:5px #000;paint-order:stroke fill;' if self.th == 'sportsdesk' else ''}}}
.cw{{position:relative;display:inline-block;padding:0 6px}}
.cw b{{position:relative;font-weight:inherit}}
.sw{{position:absolute;left:-2px;right:-2px;top:{'86%' if self.th == 'breakpoint' else '54%'};height:{'10%' if self.th == 'breakpoint' else '38%'};background:{T['cap_swipe']};transform-origin:left center;transform:skewX(-12deg);opacity:.9}}
.grain{{position:absolute;inset:-50%;pointer-events:none;opacity:{T['grain']};mix-blend-mode:overlay;z-index:7}}
"""

    def bg_layers(self):
        """Constant, quiet background motion per brand, so no frame is ever a lone word on an empty screen."""
        r = random.Random(7)
        if self.th == "techdesk":
            tape = " · ".join(["PATCH 0927", "SHIPPED FAST"] * 8)
            return (f'<div class="bgw" id="bgw">{"TECHDESK " * 4}</div>'
                    f'<div class="bgtape" id="bgt1" style="top:560px;transform:rotate(-8deg)">{tape}</div>'
                    f'<div class="bgtape" id="bgt2" style="top:1250px;transform:rotate(6deg)">{tape}</div>')
        if self.th == "push":
            cards = "".join(f'<div class="ghost" id="gh{k}" style="left:{x}px;width:{w}px"></div>'
                            for k, (x, w) in enumerate([(60, 620), (400, 560), (140, 700), (430, 520), (90, 640), (360, 600)]))
            return '<div class="orb" id="orb1" style="left:-200px;top:200px"></div><div class="orb" id="orb2" style="left:500px;top:1100px"></div>' + cards
        if self.th == "breakpoint":
            code = "".join(f'<i style="width:{r.randint(120, 700)}px;margin-left:{r.choice([0, 0, 40, 80])}px"></i>' for _ in range(34))
            mini = "".join(f'<i style="width:{r.randint(18, 60)}px"></i>' for _ in range(160))
            return f'<div class="codebg" id="codebg">{code}{code}</div><div class="minimap" id="mini">{mini}{mini}</div>'
        return ""

    def bg_js(self):
        if self.th == "techdesk":
            return ('const now = tl.time(); document.getElementById("bgw").style.translate = (-((now * 50) % 1400)).toFixed(1) + "px 0";'
                    'document.getElementById("bgt1").style.translate = (-((now * 80) % 700)).toFixed(1) + "px 0";'
                    'document.getElementById("bgt2").style.translate = (((now * 70) % 700) - 700).toFixed(1) + "px 0";')
        if self.th == "push":
            return ('const now = tl.time(); for (let k = 0; k < 6; k++) { const y = ((k * 440 + 1900 - now * 55) % 2640 + 2640) % 2640 - 300;'
                    ' document.getElementById("gh" + k).style.translate = "0 " + y.toFixed(1) + "px"; }'
                    'document.getElementById("orb1").style.translate = (Math.sin(now * 0.3) * 200).toFixed(1) + "px " + (Math.cos(now * 0.25) * 260).toFixed(1) + "px";'
                    'document.getElementById("orb2").style.translate = (Math.cos(now * 0.22) * 220).toFixed(1) + "px " + (Math.sin(now * 0.28) * 240).toFixed(1) + "px";')
        if self.th == "breakpoint":
            return ('const now = tl.time(); document.getElementById("codebg").style.translate = "0 " + (-((now * 22) % 2040)).toFixed(1) + "px";'
                    'document.getElementById("mini").style.translate = "0 " + (-((now * 12) % 2240)).toFixed(1) + "px";')
        return ""

    def kicker_css(self):
        return {"techdesk": f"background:{self.t['accent']};color:#111;padding:8px 20px 6px;transform:rotate(-4deg);font-weight:700",
                "push": "color:#fff;opacity:.85", "breakpoint": "color:#9A9A9A",
                "sportsdesk": f"background:{self.t['accent2']};color:#111;padding:8px 22px 4px;border-radius:999px;text-transform:uppercase",
                "bizdesk": f"color:{self.t['accent']}"}[self.th]

    def write(self):
        out = self.outdir
        if out.exists(): shutil.rmtree(out / "assets", ignore_errors=True)
        for sub in ("fonts", "sfx", "vo", "img", "brand", "emoji"): (out / "assets" / sub).mkdir(parents=True, exist_ok=True)
        self.build()
        for f in (self.t["head"], self.t["label"]): shutil.copy(FONTS / f, out / "assets" / "fonts" / f)
        if self.t.get("plate"): shutil.copy(BRANDS / self.t["plate"], out / "assets" / "brand" / self.t["plate"])
        for dst, src in self.assets.items(): shutil.copy(src, out / "assets" / dst)
        music = (self.spec_path.parent / self.spec["music"][self.th] if isinstance(self.spec["music"], dict) else self.spec_path.parent / self.spec["music"]).resolve()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(music), "-t", f"{self.total:.2f}", "-af",
                        f"highpass=f=60,afade=t=in:d=0.4,afade=t=out:st={self.total - 1.8:.2f}:d=1.8,loudnorm=I=-24:TP=-3:LRA=11",
                        "-ar", "48000", "-ac", "2", str(out / "assets" / "music.wav")], check=True)
        gutter = ('<div class="gutter">' + "\n".join(str(n) for n in range(41, 58)) + "</div>") if self.th == "breakpoint" else ""
        burst = '<div id="burst"></div><div class="plate"></div>' if self.th == "sportsdesk" else ""
        gutter = self.bg_layers() + gutter
        grain = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='260' height='260'><filter id='n'>"
                 "<feTurbulence type='fractalNoise' baseFrequency='0.95' numOctaves='2' seed='9'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")
        caps = [h for h in self.html if 'class="clip cap"' in h]; body = [h for h in self.html if 'class="clip cap"' not in h]
        helpers = """
function hash(n){ const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
function drawOn(tl, sel, t, dur){ document.querySelectorAll(sel).forEach(function(p){ const L = p.getTotalLength(); p.style.strokeDasharray = L + " " + L;
  tl.fromTo(p, {opacity: 0}, {opacity: 1, duration: 0.01}, t); tl.fromTo(p, {strokeDashoffset: L}, {strokeDashoffset: 0, duration: dur, ease: "power2.inOut"}, t); }); }
function typeOn(tl, sel, t, dur){ const el = document.querySelector(sel);
  const nodes = Array.from(el.childNodes).filter(function(n){ return n.nodeType === 3; });
  nodes.forEach(function(node){ const txt = node.textContent; const frag = document.createDocumentFragment();
    txt.split("").forEach(function(c, i){ const s = document.createElement("span"); s.textContent = c; frag.appendChild(s);
      tl.fromTo(s, {opacity: 0}, {opacity: 1, duration: 0.01}, t + dur * i / txt.length); });
    node.replaceWith(frag); });
  tl.fromTo(sel, {opacity: 0}, {opacity: 1, duration: 0.01}, t); }
const shakes = [];
"""
        doc = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={W}, height={H}" />
<title>{self.t['name']} · {self.spec.get('title', 'reel')}</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{self.css()}</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="{W}" data-height="{H}" data-duration="{self.total:.3f}">
<div class="bg"></div>{burst}{gutter}
<div id="cam" style="position:absolute;inset:0">
{chr(10).join(body)}
</div>
{chr(10).join(caps)}
<div class="grain" id="grain" style="background-image:url(&quot;{grain}&quot;)"></div>
{chr(10).join(self.audio)}
</div>
<script>
{helpers}
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(self.js)}
shakes.forEach(function(t){{ tl.fromTo("#cam",{{x:0,y:0}},{{keyframes:[{{x:-12,y:7}},{{x:9,y:-5}},{{x:-5,y:3}},{{x:0,y:0}}],duration:0.2,ease:"none"}},t); }});
tl.to({{}},{{duration:{self.total:.2f},ease:"none",onUpdate:function(){{
  const step = Math.floor(tl.time() * 8);
  document.getElementById("grain").style.translate = (hash(step) * 60 - 30).toFixed(1) + "px " + (hash(step + 7) * 60 - 30).toFixed(1) + "px";
  {'document.getElementById("burst").style.rotate = (tl.time() * 4).toFixed(2) + "deg";' if self.th == 'sportsdesk' else ''}
  {self.bg_js()}
}}}},0);
window.__timelines["main"] = tl;
</script>
</body></html>
"""
        (out / "index.html").write_text(doc)
        for f in ("hyperframes.json", "package.json"):
            if (HERE / f).exists() and not (out / f).exists(): shutil.copy(HERE / f, out / f)
        print(f"{self.th}: {self.total:.1f}s, {len(self.js)} animation calls, {len(self.audio)} audio tracks -> {out}")
        for w in self.checks: print("  " + w)
        print(f"  captions shown {self.cap_stats[0]}/{self.cap_stats[1]} (the rest repeat on-screen words)")


if __name__ == "__main__":
    spec, out_root = sys.argv[1], pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "reels")
    for th in sys.argv[2].split(","):
        Reel(spec, th, out_root / th).write()
