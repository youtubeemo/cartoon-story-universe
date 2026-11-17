"""Zuschauerentscheidungen: Kommentare zählen, Gewinner bestimmen, Ergebnis speichern.

Regeln (docs/ENTSCHEIDUNGEN.md):
* Gültig ist ein Kommentar, der mit 1, 2 oder 3 beginnt („2“, „2!“, „Option 2“, „Nr. 2“, „2️⃣ weil …“).
* Pro Konto zählt eine Stimme (die letzte gültige). Der eigene Kanal zählt nicht.
* Weniger als ``min_stimmen`` gültige Stimmen oder Gleichstand an der Spitze → Standardoption der Folge.
* YouTube: Kommentare über die kostenlose YouTube Data API (commentThreads, nur API-Schlüssel).
* TikTok bietet für normale Konten keine zuverlässige Kommentar-API → Zahlen optional manuell
  im Workflow eintragen („1=34,2=12,3=8“); sie werden zu YouTube addiert.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections import Counter

EMOJI = {"1️⃣": "1", "2️⃣": "2", "3️⃣": "3"}
VOTE = re.compile(r"^\s*(?:option|nr\.?|nummer|#|wahl)?\s*([123])(?![0-9.,])", re.IGNORECASE)


def parse_vote(text: str) -> int | None:
    t = str(text or "").strip()
    for e, d in EMOJI.items():
        t = t.replace(e, d)
    m = VOTE.match(t)
    return int(m.group(1)) if m else None


def tally(comments: list[dict], exclude_authors: set[str] | None = None) -> Counter:
    """comments: [{author, text, time}] – chronologisch; pro Autor zählt die letzte gültige Stimme."""
    exclude = {a.lower() for a in (exclude_authors or set())}
    last: dict[str, int] = {}
    for c in sorted(comments, key=lambda c: c.get("time", "")):
        a = str(c.get("author", "")).lower()
        if not a or a in exclude:
            continue
        v = parse_vote(c.get("text", ""))
        if v:
            last[a] = v
    return Counter(last.values())


def parse_manual(s: str | None) -> Counter:
    out: Counter = Counter()
    for part in (s or "").replace(";", ",").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k in ("1", "2", "3") and v.isdigit():
                out[int(k)] += int(v)
    return out


def decide(counts: Counter, standard: int, min_stimmen: int = 5) -> tuple[int, str]:
    total = sum(counts[k] for k in (1, 2, 3))
    if total < min_stimmen:
        return standard, f"zu wenige gültige Stimmen ({total} < {min_stimmen}) → Standardoption {standard}"
    ranked = sorted(((counts[k], k) for k in (1, 2, 3)), reverse=True)
    if ranked[0][0] == ranked[1][0]:
        return standard, f"Gleichstand ({ranked[0][0]}:{ranked[1][0]}) → Standardoption {standard}"
    return ranked[0][1], f"Mehrheit: Option {ranked[0][1]} mit {ranked[0][0]} von {total} Stimmen"


def fetch_youtube_comments(video_id: str, api_key: str, max_pages: int = 20) -> list[dict]:
    """Kostenlos (YouTube Data API, 1 Quota-Einheit pro Seite; Tageskontingent 10.000)."""
    out, token = [], None
    for _ in range(max_pages):
        q = {"part": "snippet", "videoId": video_id, "maxResults": 100, "textFormat": "plainText", "key": api_key}
        if token:
            q["pageToken"] = token
        url = "https://www.googleapis.com/youtube/v3/commentThreads?" + urllib.parse.urlencode(q)
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read())
        for item in data.get("items", []):
            sn = item["snippet"]["topLevelComment"]["snippet"]
            out.append({"author": sn.get("authorChannelId", {}).get("value") or sn.get("authorDisplayName", ""),
                        "text": sn.get("textOriginal", ""), "time": sn.get("publishedAt", "")})
        token = data.get("nextPageToken")
        if not token:
            break
    return out
