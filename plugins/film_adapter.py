"""Adapter Zona Cinema (LK21 API di VPS :8017) untuk @v2rayconvertBot.
Fungsi dipakai plugin film.py (sisi Muse): cari_film, detail_film, url_stream.
"""
import re, json, urllib.request

API = "http://localhost:8017"   # server.js lk21-unofficial-api (VPS)

def _get(path, timeout=25):
    try:
        with urllib.request.urlopen(API + path, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"status": False, "message": str(e)}

def cari_film(query: str, page: int = 1) -> dict:
    d = _get(f"/search?s={urllib.parse.quote(query)}&page={page}")
    out = []
    for r in (d.get("results") or []):
        out.append({"slug": r.get("slug"), "title": r.get("title"),
                    "year": (r.get("year") or r.get("date") or "")})
    return {"ok": d.get("status"), "page": page, "total_pages": d.get("total_pages", 1), "results": out}

def film_terbaru(page: int = 1) -> dict:
    d = _get(f"/movies/latest?page={page}")
    out = [{"slug": r.get("slug"), "title": r.get("title")} for r in (d.get("results") or [])]
    return {"ok": d.get("status"), "results": out}

def url_stream(slug: str) -> dict:
    """Ambil info play (HLS/stream URL + kualitas) — buat nobar voice chat & tombol ▶️."""
    d = _get(f"/movies/{slug}/play")
    if not d.get("status"):
        return d
    data = d.get("data") or {}
    return {"ok": True, "title": data.get("title") or slug, "stream_url": data.get("url"),
            "qualities": data.get("qualities") or [], "subtitle": data.get("subtitle")}

import urllib.parse  # noqa
