"""Weg 1 – Bildfolge zu MP4 (kostenlos, lokal): Kamera auf Standbildern, Anzeigen, Pop-ups, Wort-Untertitel.

Ein Bild je Shot. Die Kamera fährt kontrolliert (ran/raus/Schwenk) auf den im Storyboard festgelegten Fokus,
damit nie willkürliche Bewegungen entstehen. Darüber: schwebende Lichtpartikel, Vignette, weiße Werte-Schilder
mit Zeiger (zählen sichtbar und springen bei Änderungen), gelbe Ausrufe, 1–2-Wort-Untertitel mit rotem
Schlüsselwort und am Ende die Auswahlkarte 1/2/3.
"""
from __future__ import annotations

import math
import random
import subprocess
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from csu.hud import fmt_delta, fmt_value
from illu.storyboard import schluesselwort, stil, verlauf, woerter

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920
UEBER = 1.25          # Bilder werden einmal größer skaliert → Kamerafahrt rechnet nur herunter (scharf)
ZOOM = {"ran": (1.0, 1.13), "raus": (1.13, 1.0), "links": (1.10, 1.10), "rechts": (1.10, 1.10),
        "hoch": (1.10, 1.10), "runter": (1.10, 1.10), "ruhig": (1.03, 1.06)}
PAN = {"links": (0.035, -0.035, 0, 0), "rechts": (-0.035, 0.035, 0, 0),
       "hoch": (0, 0, 0.03, -0.03), "runter": (0, 0, -0.03, 0.03)}


# =================================================================== Zeitleiste
def _chunks(text: str, max_z: int) -> list[str]:
    out: list[str] = []
    satzende = True
    for roh in woerter(text):
        w = roh.replace("*", "").upper().rstrip(",.;:–-")
        if out and not satzende and len(out[-1].split()) == 1 and len(out[-1]) + 1 + len(w) <= max_z:
            out[-1] += " " + w
        else:
            out.append(w)
        satzende = roh.rstrip("*").endswith((".", "!", "?", ":", ","))
    return out


def zeitleiste(story: dict, sb: dict, start: dict, bilder: dict[str, Path], ton: dict[str, dict],
               st: dict | None = None) -> dict:
    """ton: Shot-ID → {"file", "dauer"} (Sprachaufnahme). Shot-Länge = Sprechzeit + Vor-/Nachlauf."""
    st = st or stil()
    vs = verlauf(story, sb, start)
    t, shots, cues, anz = 0.0, [], [], []
    vor_ort = None
    for s, v in zip(sb["shots"], vs):
        sprech = float(ton.get(s["id"], {}).get("dauer", 0.0))
        dauer = max(st["shot"]["min_s"], float(s.get("dauer", 0) or 0),
                    st["shot"]["vorlauf_s"] + sprech + st["shot"]["nachlauf_s"])
        if s.get("entscheidung"):
            dauer += 1.6                                    # Auswahlkarte stehen lassen
        t0 = t
        # Wort-Untertitel: Zeit proportional zur Zeichenzahl innerhalb der Sprechzeit
        ch = _chunks(s.get("text", ""), st["untertitel"]["max_zeichen"])
        if ch and sprech > 0:
            gew = [len(c) + 2 for c in ch]
            a = t0 + st["shot"]["vorlauf_s"]
            for c, g in zip(ch, gew):
                d = sprech * g / sum(gew)
                cues.append({"t0": a, "t1": a + d, "text": c, "wort": schluesselwort(s)})
                a += d
        for ae in v["aenderungen"]:
            anz.append({"key": ae["key"], "t0": t0, "t1": t0 + dauer + st["anzeige"]["halten_s"],
                        "tw": t0 + 0.35, "vor": ae["vor"], "nach": ae["nach"], "popup": bool(s.get("popup"))})
        for k in s.get("zeige") or []:
            anz.append({"key": k, "t0": t0, "t1": t0 + dauer + st["anzeige"]["halten_s"],
                        "tw": t0, "vor": v["werte"][k], "nach": v["werte"][k]})
        shots.append({"id": s["id"], "t0": t0, "t1": t0 + dauer, "bild": str(bilder[s["id"]]),
                      "kamera": s.get("kamera", "ran"), "fokus": s.get("fokus", [0.5, 0.45]),
                      "popup": s.get("popup"), "entscheidung": bool(s.get("entscheidung")),
                      "neuer_ort": vor_ort is not None and s["ort"] != vor_ort, "sfx": s.get("sfx") or [],
                      "sprache": ton.get(s["id"], {}).get("file"), "sprache_at": t0 + st["shot"]["vorlauf_s"]})
        vor_ort = s["ort"]
        t += dauer
    return {"dauer": t, "shots": shots, "cues": cues, "anzeigen": anz, "hud": story["hud"],
            "titel": sb.get("titel", ""), "entscheidung": sb.get("entscheidung"), "stil": st}


# =================================================================== Zeichnen
@lru_cache(maxsize=16)
def _font(pfad: str, groesse: int, variante: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(ROOT / pfad), groesse)
    if variante:
        f.set_variation_by_name(variante)
    return f


def _hex(c: str, a: int = 255) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _pop(x: float) -> float:
    """Überschwingende Skalierung 0 → 1.18 → 1 in x ∈ [0, 1]."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1 + 0.18 * math.sin(x * math.pi) * (1 - x) * 2.2 - (1 - _ease_out(x)) * 0.9


_BASIS: dict[str, Image.Image] = {}


def _basis(pfad: str) -> Image.Image:
    if pfad not in _BASIS:
        if len(_BASIS) > 4:
            _BASIS.pop(next(iter(_BASIS)))
        im = Image.open(pfad).convert("RGB")
        bw, bh = int(W * UEBER), int(H * UEBER)
        s = max(bw / im.width, bh / im.height)
        im = im.resize((math.ceil(im.width * s), math.ceil(im.height * s)), Image.LANCZOS)
        l, o = (im.width - bw) // 2, (im.height - bh) // 2
        _BASIS[pfad] = im.crop((l, o, l + bw, o + bh))
    return _BASIS[pfad]


def kamera(shot: dict, t: float) -> Image.Image:
    p = (t - shot["t0"]) / max(1e-6, shot["t1"] - shot["t0"])
    e = _ease_out(p) * 0.35 + p * 0.65                    # fast linear, sanfter Start
    z0, z1 = ZOOM[shot["kamera"]]
    z = z0 + (z1 - z0) * e
    dx0, dx1, dy0, dy1 = PAN.get(shot["kamera"], (0, 0, 0, 0))
    b = _basis(shot["bild"])
    bw, bh = b.size
    sicht_w, sicht_h = bw / (UEBER * z), bh / (UEBER * z)
    cx = shot["fokus"][0] * bw + (dx0 + (dx1 - dx0) * e) * bw
    cy = shot["fokus"][1] * bh + (dy0 + (dy1 - dy0) * e) * bh
    cx = min(max(cx, sicht_w / 2), bw - sicht_w / 2)
    cy = min(max(cy, sicht_h / 2), bh - sicht_h / 2)
    k = sicht_w / W
    return b.transform((W, H), Image.AFFINE, (k, 0, cx - sicht_w / 2, 0, k, cy - sicht_h / 2), Image.BILINEAR)


@lru_cache(maxsize=1)
def _vignette() -> Image.Image:
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((x - W / 2) / (W * 0.62)) ** 2 + ((y - H * 0.5) / (H * 0.62)) ** 2)
    a = np.clip((r - 0.55) / 0.6, 0, 1) ** 1.6 * 120
    unten = np.clip((y - H * 0.52) / (H * 0.4), 0, 1) ** 2 * 70      # Untertitel-Lesbarkeit
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., 3] = np.clip(a + unten, 0, 170).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _partikel(ebene: Image.Image, shot: dict, t: float, n: int) -> None:
    rnd = random.Random(shot["id"])
    d = ImageDraw.Draw(ebene)
    for _ in range(n):
        x0, y0 = rnd.random() * W, rnd.random() * H
        v, r, ph = 18 + rnd.random() * 40, 2 + rnd.random() * 5, rnd.random() * 6.28
        x = (x0 + math.sin(t * 0.7 + ph) * 22) % W
        y = (y0 - v * t) % H
        a = int(60 + 70 * (0.5 + 0.5 * math.sin(t * 1.3 + ph)))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 244, 214, a))


@lru_cache(maxsize=256)
def _text(text: str, schrift: str, groesse: int, farbe: str, kontur: int, wort: str | None = None,
          wort_farbe: str = "#FF3B30", kursiv: bool = False) -> Image.Image:
    f = _font(schrift, groesse)
    teile = text.split(" ")
    breiten = [f.getlength(w) for w in teile]
    luecke = f.getlength(" ")
    bw = int(sum(breiten) + luecke * (len(teile) - 1)) + kontur * 2 + 40
    bh = int(groesse * 1.45) + kontur * 2
    im = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # weicher Schlagschatten
    sch = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(sch)
    x = kontur + 20
    for w, bw_ in zip(teile, breiten):
        ds.text((x + 6, kontur + 10), w, font=f, fill=(0, 0, 0, 150), stroke_width=kontur, stroke_fill=(0, 0, 0, 150))
        x += bw_ + luecke
    im.alpha_composite(sch.filter(ImageFilter.GaussianBlur(6)))
    x = kontur + 20
    for w, bw_ in zip(teile, breiten):
        rot = wort and wort.strip("!?.,") and wort.strip("!?.,") in w
        d.text((x, kontur), w, font=f, fill=_hex(wort_farbe if rot else farbe), stroke_width=kontur,
               stroke_fill=(0, 0, 0, 255))
        x += bw_ + luecke
    if kursiv:
        im = im.transform((bw + bh // 4, bh), Image.AFFINE, (1, 0.22, -bh * 0.22, 0, 1, 0), Image.BICUBIC)
    return im


def _setze(bild: Image.Image, ebene: Image.Image, mx: float, my: float, skala: float = 1.0, drehung: float = 0.0):
    if skala <= 0.02:
        return
    e = ebene
    if abs(skala - 1) > 1e-3:
        e = e.resize((max(1, int(e.width * skala)), max(1, int(e.height * skala))), Image.BILINEAR)
    if drehung:
        e = e.rotate(drehung, resample=Image.BICUBIC, expand=True)
    bild.alpha_composite(e, (int(mx - e.width / 2), int(my - e.height / 2)))


@lru_cache(maxsize=128)
def _schild(oben: str, wert: str, farbe: str, groesse: int, schrift: str) -> Image.Image:
    fw = _font(schrift, groesse, "ExtraBold")
    fl = _font(schrift, int(groesse * 0.42), "Bold")
    tw = max(fw.getlength(wert), fl.getlength(oben))
    bw, bh = int(tw + 64), int(groesse * 1.75)
    zeiger = 26
    im = Image.new("RGBA", (bw + 20, bh + zeiger + 20), (0, 0, 0, 0))
    sch = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sch).rounded_rectangle((10, 16, bw + 10, bh + 16), 30, fill=(0, 0, 0, 110))
    im.alpha_composite(sch.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, bw + 10, bh + 10), 30, fill=(255, 255, 255, 250))
    m = 10 + bw / 2
    d.polygon([(m - 20, bh + 8), (m + 20, bh + 8), (m, bh + 10 + zeiger)], fill=(255, 255, 255, 250))
    d.text((m, 10 + groesse * 0.32), oben, font=fl, fill=(120, 120, 130, 255), anchor="mm")
    d.text((m, 10 + groesse * 1.05), wert, font=fw, fill=_hex(farbe), anchor="mm")
    return im


def _anzeigen(bild: Image.Image, tl: dict, t: float) -> None:
    st = tl["stil"]["anzeige"]
    aktiv: dict[str, dict] = {}
    for a in tl["anzeigen"]:                         # jüngstes Ereignis je Anzeige gewinnt
        if a["t0"] <= t <= a["t1"]:
            aktiv[a["key"]] = a
    if not aktiv:
        return
    eintraege = list(aktiv.values())
    abstand = W / (len(eintraege) + 1)
    for i, a in enumerate(eintraege):
        d = tl["hud"][a["key"]]
        x = abstand * (i + 1)
        y = H * st["y"]
        rein = _pop((t - a["t0"]) / 0.35)
        aus = 1 - _ease_out((t - (a["t1"] - 0.25)) / 0.25) if t > a["t1"] - 0.25 else 1
        wert, farbe, skala, wackel = a["nach"], "#1B1B24", 1.0, 0.0
        if a["vor"] != a["nach"]:
            p = (t - a["tw"]) / 0.6
            if p < 0:
                wert = a["vor"]
            elif p < 1 and d["typ"] != "inventar":
                diff = a["nach"] - a["vor"]
                stufe = 10 ** max(0, len(str(abs(int(diff)))) - 2)       # zählt in glatten Schritten
                wert = int(round((a["vor"] + diff * _ease_out(p)) / stufe) * stufe)
            if 0 <= p < 1.6:
                gut = (a["nach"] > a["vor"]) == (d.get("gut", "hoch") == "hoch") if d["typ"] != "inventar" \
                    else len(a["nach"]) >= len(a["vor"])
                farbe = "#1FA64A" if gut else "#E0262B"
                skala = 1 + 0.16 * math.sin(min(p, 1) * math.pi)
                wackel = 5 * math.sin(p * 40) * max(0, 1 - p)
            if 0 <= p < 1.4 and not a.get("popup"):   # Delta erscheint unter dem Schild und sinkt leicht
                dt_ = _text(fmt_delta(d, a["vor"], a["nach"]), tl["stil"]["schrift"]["popup"], 76,
                            "#5BE37D" if farbe == "#1FA64A" else "#FF5A4E", 8)
                _setze(bild, dt_, x, y + st["groesse"] * 1.9 + 40 * _ease_out(p / 1.4),
                       _pop(p / 0.3) * (1 - max(0, p - 1) / 0.4))
        sch = _schild(d["label"].upper(), fmt_value(d, wert), farbe, st["groesse"], tl["stil"]["schrift"]["anzeige"])
        _setze(bild, sch, x + wackel, y, rein * aus * skala)


def _untertitel(bild: Image.Image, tl: dict, t: float) -> None:
    u = tl["stil"]["untertitel"]
    for c in tl["cues"]:
        if c["t0"] <= t < c["t1"]:
            im = _text(c["text"], tl["stil"]["schrift"]["untertitel"], u["groesse"], u["farbe"], u["kontur"],
                       c["wort"], u["wort_farbe"])
            if im.width > W - 80:
                im = im.resize((W - 80, int(im.height * (W - 80) / im.width)), Image.LANCZOS)
            _setze(bild, im, W / 2, H * u["y"], _pop((t - c["t0"]) / 0.12) if t - c["t0"] < 0.12 else 1.0)
            return


def _popup(bild: Image.Image, tl: dict, shot: dict, t: float) -> None:
    if not shot["popup"]:
        return
    p = tl["stil"]["popup"]
    x = (t - shot["t0"] - 0.4) / 0.3
    if x <= 0:
        return
    im = _text(str(shot["popup"]), tl["stil"]["schrift"]["popup"], p["groesse"], p["farbe"], p["kontur"], kursiv=True)
    if im.width > W - 120:
        im = im.resize((W - 120, int(im.height * (W - 120) / im.width)), Image.LANCZOS)
    _setze(bild, im, W / 2, H * 0.40 - 8 * math.sin(t * 5), _pop(x), drehung=6)


def _auswahl(bild: Image.Image, tl: dict, shot: dict, t: float) -> None:
    ent = tl["entscheidung"] or {}
    x = t - shot["t0"] - 0.3
    if x <= 0:
        return
    frage = _text(str(ent.get("frage", "")).upper(), tl["stil"]["schrift"]["untertitel"], 92, "#FFFFFF", 8)
    if frage.width > W - 80:
        frage = frage.resize((W - 80, int(frage.height * (W - 80) / frage.width)), Image.LANCZOS)
    _setze(bild, frage, W / 2, H * 0.17, _pop(x / 0.3))
    fs = _font(tl["stil"]["schrift"]["anzeige"], 44, "ExtraBold")
    for i, (nr, opt) in enumerate(sorted((ent.get("optionen") or {}).items())):
        p = (x - 0.25 - i * 0.22) / 0.3
        if p <= 0:
            continue
        box = Image.new("RGBA", (W - 90, 132), (0, 0, 0, 0))
        d = ImageDraw.Draw(box)
        d.rounded_rectangle((0, 0, box.width - 1, 131), 34, fill=(255, 255, 255, 245))
        d.ellipse((18, 16, 118, 116), fill=_hex(["#FF3B30", "#FFB800", "#2F80ED"][i % 3]))
        d.text((68, 66), str(nr), font=_font(tl["stil"]["schrift"]["popup"], 64), fill=(255, 255, 255), anchor="mm")
        txt = str(opt["text"])
        while fs.getlength(txt) > box.width - 160 and len(txt) > 4:
            txt = txt[:-2] + "…"
        d.text((140, 66), txt, font=fs, fill=(27, 27, 36), anchor="lm")
        _setze(bild, box, W / 2, H * 0.27 + i * 158, _pop(p))


def bild(tl: dict, f: int, fps: int = 30) -> Image.Image:
    t = f / fps
    shot = next((s for s in tl["shots"] if s["t0"] <= t < s["t1"]), tl["shots"][-1])
    im = kamera(shot, t).convert("RGBA")
    ebene = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _partikel(ebene, shot, t, tl["stil"]["partikel"])
    im.alpha_composite(ebene)
    im.alpha_composite(_vignette())
    if shot["neuer_ort"] and t - shot["t0"] < 0.1:   # kurzer Lichtblitz beim Ortswechsel
        a = int(110 * (1 - (t - shot["t0"]) / 0.1))
        im.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, a)))
    if shot["entscheidung"]:
        _auswahl(im, tl, shot, t)
    else:
        _anzeigen(im, tl, t)
        _popup(im, tl, shot, t)
    _untertitel(im, tl, t)
    return im.convert("RGB")


# =================================================================== Video + Ton
_TL: dict = {}


def _init(tl: dict) -> None:
    _TL.clear()
    _TL.update(tl)


def _roh(f: int) -> bytes:
    return bild(_TL, f).tobytes()


def standbild(tl: dict, t: float, ziel: Path) -> Path:
    bild(tl, int(t * 30)).save(ziel)
    return ziel


def tonspur(tl: dict, ziel: Path, stimmung: str = "spannend") -> Path:
    from toon import ton
    stimmen = [(Path(s["sprache"]), s["sprache_at"]) for s in tl["shots"] if s.get("sprache")]
    effekte: list[tuple[Path, float, float]] = []
    tmp = ziel.parent / "sfx"
    tmp.mkdir(parents=True, exist_ok=True)

    def fx(name: str, at: float, var: int = 0) -> None:
        effekte.append((ton.effekt(name, tmp / f"{name}_{var}.wav", var), max(0.0, at), ton.LAUTSTAERKE.get(name, 0.5)))

    for i, s in enumerate(tl["shots"]):
        if s["neuer_ort"]:
            fx("whoosh", s["t0"] - 0.15, i % 3)
        for n in s["sfx"]:
            fx(n, s["t0"] + 0.3, i % 3)
    for a in tl["anzeigen"]:
        if a["vor"] != a["nach"] and tl["hud"][a["key"]]["typ"] == "geld":
            fx("kasse", a["tw"])
    musik = ton.musik(tl["dauer"], stimmung, ziel.parent / "musik.wav")
    return ton.mischen(stimmen, effekte, musik, tl["dauer"], ziel)


def video(tl: dict, ton_wav: Path, ziel: Path, fps: int = 30, prozesse: int = 2, crf: int = 17) -> Path:
    n = int(math.ceil(tl["dauer"] * fps))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-i", str(ton_wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
           "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-shortest", str(ziel)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(prozesse, initializer=_init, initargs=(tl,)) as pool:
        for frame in pool.imap(_roh, range(n), chunksize=8):
            p.stdin.write(frame)
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg-Fehler beim Kodieren")
    return ziel

