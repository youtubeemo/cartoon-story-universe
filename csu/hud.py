"""Animierte Statusanzeigen, Untertitel, Titel und Auswahlkarte als ASS-Overlay (libass/FFmpeg, kostenlos).

Zahlen „zählen“ sichtbar vom alten zum neuen Wert, die Zeile blinkt grün/rot, ein Delta-Pop-up
steigt auf (z. B. „−1.500 €“). Layout hält die TikTok/Shorts-Bedienelemente frei
(oben 130 px, unten 420 px, rechts 160 px).
"""
from __future__ import annotations

from csu.common import fmt_num

W, H = 1080, 1920
TICK_S = 0.8
STEP_S = 1 / 15
ROW_H = 66
HUD_X, HUD_Y = 48, 150

GOOD = "&H0060E070&"      # grün (ASS: &HBBGGRR&)
BAD = "&H004060F0&"       # rot
GOLD = "&H0040D0FF&"


def fmt_value(d: dict, v) -> str:
    typ = d["typ"]
    if typ == "geld":
        return f"{fmt_num(v)} €"
    if typ == "prozent":
        return f"{int(v)} %"
    if typ == "tage":
        return f"Noch {int(v)} {'Tag' if int(v) == 1 else 'Tage'}"
    if typ == "stunden":
        return f"Noch {int(v)} Std."
    if typ == "jahr":
        return str(int(v))
    if typ == "sterne":
        return "★" * int(v) + "☆" * (int(d.get("max", 5)) - int(v))
    if typ == "bruch":
        return f"{int(v)}/{int(d['max'])}"
    if typ == "inventar":
        return ", ".join(v) if v else "leer"
    einheit = d.get("einheit")
    return f"{fmt_num(v)}{' ' + einheit if einheit else ''}"


def fmt_delta(d: dict, before, after) -> str:
    if d["typ"] == "inventar":
        added = [x for x in after if x not in before or after.count(x) > before.count(x)]
        removed = [x for x in before if x not in after or before.count(x) > after.count(x)]
        return "  ".join([f"+ {x}" for x in dict.fromkeys(added)] + [f"− {x}" for x in dict.fromkeys(removed)])
    diff = after - before
    sign = "+" if diff > 0 else "−"
    if d["typ"] == "geld":
        return f"{sign}{fmt_num(abs(diff))} €"
    if d["typ"] == "prozent":
        return f"{sign}{abs(diff)} %"
    if d["typ"] == "jahr":
        return f"→ {after}"
    return f"{sign}{abs(diff)}"


def _good(d: dict, before, after) -> bool:
    if d["typ"] == "inventar":
        return len(after) >= len(before)
    up = after > before
    return up if d.get("gut", "hoch") == "hoch" else not up


def ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(text: str) -> str:
    return str(text).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def wrap(text: str, width: int) -> str:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\\N".join(esc(x) for x in lines)


HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HUD,DejaVu Sans,42,&H00FFFFFF,&H00FFFFFF,&H90201A14,&H90201A14,-1,0,0,0,100,100,0,0,3,10,0,7,0,0,0,1
Style: Pop,DejaVu Sans,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,2,7,0,0,0,1
Style: Sub,DejaVu Sans,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,2,90,170,430,1
Style: SubFig,DejaVu Sans,60,&H0066E6FF,&H0066E6FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,2,90,170,430,1
Style: Titel,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,3,8,60,60,0,1
Style: Frage,DejaVu Sans,64,&H0040D0FF,&H0040D0FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Option,DejaVu Sans,40,&H00FFFFFF,&H00FFFFFF,&HC8402010,&HC8402010,-1,0,0,0,100,100,0,0,3,22,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ev(layer: int, start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}"


def build_ass(story: dict, start_werte: dict, events: list[dict], total: float, cues: list[dict],
              choice: dict | None, titel: str) -> str:
    """events: [{t, key, vorher, nachher, quelle?}] (t = absolute Sekunde)."""
    hud, rows = story["hud"], story["anzeige"]
    lines: list[str] = []
    by_key: dict[str, list[dict]] = {k: [] for k in rows}
    for ev in sorted(events, key=lambda e: e["t"]):
        if ev["key"] in by_key:
            by_key[ev["key"]].append(ev)

    hud_lines: list[tuple] = []
    for i, key in enumerate(rows):
        d = hud[key]
        y = HUD_Y + i * ROW_H
        pos = f"{{\\pos({HUD_X},{y})}}"
        label = esc(d["label"])
        evs = by_key[key]
        cur_t = 0.0
        cur_v = start_werte[key]
        for ev in evs:
            # konstanter Abschnitt bis zum Ereignis
            if ev["t"] > cur_t:
                hud_lines.append((1, cur_t, ev["t"], "HUD", f"{pos}{label}: {esc(fmt_value(d, cur_v))}"))
            good = _good(d, ev["vorher"], ev["nachher"])
            col = GOOD if good else BAD
            numeric = d["typ"] != "inventar"
            steps = max(1, int(TICK_S / STEP_S)) if numeric else 1
            for k in range(steps):
                f = (k + 1) / steps
                v = ev["vorher"] + (ev["nachher"] - ev["vorher"]) * (1 - (1 - f) ** 2) if numeric else ev["nachher"]
                v = round(v) if numeric else v
                t0 = ev["t"] + k * STEP_S
                t1 = ev["t"] + (k + 1) * STEP_S if numeric else ev["t"] + TICK_S
                hud_lines.append((1, t0, t1, "HUD",
                                 f"{pos}{{\\c{col}\\fscx108\\fscy108}}{label}: {esc(fmt_value(d, v))}"))
            # Nachleuchten, dann normal
            glow_end = ev["t"] + TICK_S + 0.6
            hud_lines.append((1, ev["t"] + TICK_S, glow_end, "HUD",
                             f"{pos}{{\\c{col}\\t(0,600,\\c&H00FFFFFF&)}}{label}: {esc(fmt_value(d, ev['nachher']))}"))
            # Delta-Pop-up steigt neben der Zeile auf
            delta = esc(fmt_delta(d, ev["vorher"], ev["nachher"]))
            src = f"  {esc(ev['quelle'])}" if ev.get("quelle") else ""
            px = HUD_X + 560
            hud_lines.append((2, ev["t"], ev["t"] + 1.6, "Pop",
                             f"{{\\move({px},{y},{px},{y - 60})\\fad(100,500)\\c{col}}}{delta}{src}"))
            cur_t, cur_v = glow_end, ev["nachher"]
        hud_lines.append((1, cur_t, total, "HUD", f"{pos}{label}: {esc(fmt_value(d, cur_v))}"))

    # Statusanzeige nur am Anfang und kurz nach jeder Änderung einblenden (keine Dauer-Überlagerung)
    wins = [(0.0, 3.0)] + [(e["t"] - 0.2, e["t"] + 3.5) for e in events]
    wins.sort()
    merged: list[list[float]] = []
    for w0, w1 in wins:
        if merged and w0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], w1)
        else:
            merged.append([w0, w1])
    for layer, t0, t1, style, text in hud_lines:
        for w0, w1 in merged:
            a0, a1 = max(t0, w0), min(t1, w1)
            if a1 - a0 > 0.01:
                fade = "{\\fad(150,250)}" if (abs(a0 - w0) < 0.02 or abs(a1 - w1) < 0.02) and layer == 1 else ""
                lines.append(_ev(layer, a0, a1, style, fade + text))

    # Titel (erste 3 s)
    lines.append(_ev(3, 0.2, 2.7, "Titel", f"{{\\pos({W // 2},{HUD_Y + len(rows) * ROW_H + 40})\\fad(250,400)}}"
                     f"{esc(story['titel'])}\\N{{\\fs40}}{esc(titel)}"))

    # Untertitel
    for c in cues:
        style = "Sub" if c.get("erzaehler") else "SubFig"
        lines.append(_ev(4, c["start"], c["end"], style, f"{{\\fad(60,60)}}{wrap(c['text'], 26)}"))

    # Auswahlkarte
    if choice:
        t0, t1 = choice["start"], total
        lines.append(_ev(5, t0, t1, "Frage", f"{{\\pos({W // 2},640)\\fad(300,0)\\t(0,300,\\fscx110\\fscy110)"
                                              f"\\t(300,500,\\fscx100\\fscy100)}}{wrap(choice['frage'], 22)}"))
        for i, nr in enumerate((1, 2, 3)):
            opt = choice["optionen"][nr] if nr in choice["optionen"] else choice["optionen"][str(nr)]
            y = 820 + i * 135
            st = t0 + 0.5 + i * 0.35
            lines.append(_ev(5, st, t1, "Option",
                             f"{{\\move(-500,{y},{W // 2},{y},0,350)\\fad(150,0)}}"
                             f"{{\\c{GOLD}}}{nr}{{\\c&H00FFFFFF&}}  {wrap(opt['text'], 46)}"))
        lines.append(_ev(5, t0 + 1.8, t1, "Frage",
                         f"{{\\pos({W // 2},1250)\\fs46\\c&H00FFFFFF&\\fad(300,0)}}Schreib 1, 2 oder 3 in die Kommentare!"))
    return HEADER + "\n".join(lines) + "\n"
