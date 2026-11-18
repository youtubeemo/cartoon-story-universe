"""KI-Bildprüfung des Storyboards (Claude, ≈ 0,03 €) – VOR den teuren Animationskosten.

Claude bekommt zwei Bögen: die freigegebenen Charaktervorlagen und die nummerierten Storyboard-Bilder samt
geplanter Handlung je Szene. Geprüft wird je Szene: richtige Figuren, gleiches Aussehen wie Vorlage,
Bild passt zur Handlung, Stil eingehalten, kein Text im Bild. Ergebnis ist ein Gutachten, kein Beweis –
die menschliche Storyboard-Freigabe bleibt Pflicht, solange storyboard_freigabe_erforderlich: true ist.
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from csu.common import budget

MAX_KANTE = 1568


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def bogen(bilder: list[tuple[str, Path]], spalten: int, kachel_b: int = 300) -> Image.Image:
    tiles = []
    for label, p in bilder:
        im = Image.open(p).convert("RGB")
        im = im.resize((kachel_b, int(im.height * kachel_b / im.width)))
        t = Image.new("RGB", (im.width, im.height + 28), "white")
        t.paste(im, (0, 28))
        ImageDraw.Draw(t).text((4, 4), label, fill="black", font=_font(18))
        tiles.append(t)
    w, h = tiles[0].size
    rows = (len(tiles) + spalten - 1) // spalten
    sheet = Image.new("RGB", (w * spalten, h * rows), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % spalten) * w, (i // spalten) * h))
    f = min(1.0, MAX_KANTE / max(sheet.size))
    return sheet.resize((int(sheet.width * f), int(sheet.height * f)))


def _b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def max_cost_eur() -> float:
    b = budget()
    a = b["anthropic"]
    usd = 15000 / 1e6 * a["usd_input_mtok"] + 3000 / 1e6 * a["usd_output_mtok"]
    return round(usd * float(b["eur_per_usd"]) * (1 + float(b["vat_rate"])), 4)


def pruefen(story: dict, ep: dict, vorlagen: dict[str, str], storyboard: dict[str, str]) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY fehlt")
    a = budget()["anthropic"]
    v_sheet = bogen([(t, Path(p)) for t, p in sorted(vorlagen.items())], spalten=6, kachel_b=220)
    sb = [(f"{int(k.split('_S')[1])}", Path(p)) for k, p in sorted(storyboard.items())]
    s_sheet = bogen(sb, spalten=5, kachel_b=260)
    plan = [{"nr": s["nr"], "figuren": s["figuren"], "ort": s["ort"], "kamera": s["kamera"],
             "tageszeit": s["tageszeit"], "handlung": s["handlung"], "bild": s["bild"]}
            for s in ep["szenen"] if f"KF_{s['id']}" in storyboard]
    namen = {k: f["name"] for k, f in story["figuren"].items()}
    text = (
        "Du bist Qualitätsprüfer:in einer 2D-Cartoon-Serie. Bild 1: freigegebene Charaktervorlagen "
        "(Tag = figur_v/_s/_d für vorne/seite/dreiviertel, sonst Ortsvorlage). Bild 2: nummerierte Storyboard-"
        f"Startbilder. Figurennamen: {json.dumps(namen, ensure_ascii=False)}. Geplante Szenen: "
        f"{json.dumps(plan, ensure_ascii=False)}\n\nPrüfe JEDE Szene streng: (a) genau die geplanten Figuren, "
        "keine zusätzlichen; (b) Figuren sehen aus wie in den Vorlagen (Gesicht, Haare, Kleidung, Farben, "
        "Proportionen); (c) Bild passt zu Handlung, Ort, Kamera und Tageszeit; (d) einfacher 2D-Cartoon-Stil mit "
        "klaren Konturen wie die Vorlagen; (e) kein Text/Schrift im Bild; (f) keine Fehlbildungen. Antworte NUR mit "
        'JSON: {"szenen":[{"nr":1,"ok":true,"probleme":""}],"gesamt_ok":true,"zusammenfassung":""}'
    )
    body = {"model": a["modell"], "max_tokens": 3000, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(v_sheet)}},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _b64(s_sheet)}},
        {"type": "text", "text": text}]}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    raw = "".join(b.get("text", "") for b in data.get("content", [])).strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    try:
        res = json.loads(raw)
    except json.JSONDecodeError:
        res = {"gesamt_ok": False, "zusammenfassung": "Antwort nicht lesbar", "szenen": []}
    res["usage"] = data.get("usage", {})
    res["gesamt_ok"] = bool(res.get("gesamt_ok")) and all(s.get("ok") for s in res.get("szenen", []))
    return res
