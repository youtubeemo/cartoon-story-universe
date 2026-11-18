"""Kostenlose Retusche vorhandener Bilder (OpenCV-Inpainting) – statt neu und kostenpflichtig zu erzeugen.

Geeignet für KLEINE störende Details in festgelegten Rechtecken: Fantasieschrift auf Schildern, Augen/Münder auf
Broten. In jedem Rechteck werden nur Pixel ersetzt, die stark von ihrer Umgebung abweichen (Schrift, Augen),
die Fläche selbst bleibt erhalten. Nicht geeignet für falsche Figuren, falsches Alter oder 3D-Look – dafür
braucht es ein neues Bild.

Steuerdatei stories/<slug>/retusche.yaml:
    <dateiname.png>:
      - {box: [x0, y0, x1, y1], grund: "Fantasieschrift", schwelle: 45, durchgaenge: 1}
Ergebnis: <dateiname>.ret.png neben dem Original (Original bleibt unverändert). Die Retusche ist danach
„ungeprueft“ und muss die Qualitätskontrolle erneut bestehen.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent


def flicken(img: np.ndarray, box: list[int], schwelle: int = 38) -> np.ndarray:
    x0, y0, x1, y1 = box
    roi = img[y0:y1, x0:x1]
    umgebung = cv2.medianBlur(roi, 41)
    abw = np.abs(roi.astype(int) - umgebung.astype(int)).sum(axis=2)
    maske = cv2.dilate((abw > schwelle).astype(np.uint8) * 255, np.ones((5, 5), np.uint8), iterations=1)
    voll = np.zeros(img.shape[:2], np.uint8)
    voll[y0:y1, x0:x1] = maske
    return cv2.inpaint(img, voll, 5, cv2.INPAINT_TELEA)


def anwenden(slug: str) -> list[Path]:
    steuer = ROOT / "stories" / slug / "retusche.yaml"
    if not steuer.exists():
        return []
    out = []
    for name, eintraege in (yaml.safe_load(steuer.read_text(encoding="utf-8")) or {}).items():
        src = ROOT / "assets" / "illu" / slug / name
        img = cv2.imread(str(src))
        if img is None:
            raise SystemExit(f"Retusche: {src} fehlt")
        for e in eintraege:
            for _ in range(int(e.get("durchgaenge", 1))):      # große Buchstaben: zweiter Durchgang
                img = flicken(img, e["box"], int(e.get("schwelle", 38)))
        ziel = src.with_suffix(".ret.png")
        cv2.imwrite(str(ziel), img)
        out.append(ziel)
    return out
