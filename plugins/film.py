"""plugins/film.py v2 — .film cari film via lk21 API (env FILM_API).
- Tombol "Ganti tampilan": daftar (1/baris) <-> kompak (2/baris)
- .film <link cinema> → slug dari # → langsung panel play
- Link tonton pakai domain cinema (env CINEMA_URL)
"""
import json, os, re, urllib.request, urllib.parse
from core.registry import REGISTRY

API = os.environ.get("FILM_API", "http://localhost:8017")
CINEMA = os.environ.get("CINEMA_URL", "https://cinema.xinquins.de5.net")
SESI_FILM = {}  # chat_id -> {query, results, tampilan}


def _get(path, timeout=25):
    try:
        with urllib.request.urlopen(API + path, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"status": False, "message": str(e)}


def _kb(rows):
    return json.dumps({"inline_keyboard": rows})


def _btn(label, data):
    return {"text": label, "callback_data": data}


def _slug_dari_teks(teks: str):
    """Ambil slug dari link cinema: .../#babes-2024 atau /movies/babes-2024/..."""
    m = re.search(r"[#/]#?([a-z0-9-]{3,80})/?$", (teks or "").strip().lower())
    return m.group(1) if m else None


def _panel_hasil(chat_id: int):
    s = SESI_FILM.get(chat_id)
    if not s:
        return None, None
    per_baris = 2 if s.get("tampilan") == "kompak" else 1
    baris, now = [], []
    for r in s["results"]:
        if r.get("slug"):
            now.append(_btn((r.get("title") or r.get("slug"))[:30], f"f:d:{r.get('slug')}"))
        if len(now) == per_baris:
            baris.append(now)
            now = []
    if now:
        baris.append(now)
    baris.append([_btn("🔀 Ganti tampilan", "f:view")])
    return f"🎬 Hasil untuk {s['query']} ({'kompak' if per_baris == 2 else 'daftar'}):", _kb(baris)


@REGISTRY.daftar("film", "member")
async def film(ktx, arg: str) -> None:
    kata = arg.strip()
    if not kata:
        await ktx.balas("Pakai: `.film <judul>` atau `.film <link cinema>`")
        return
    # link cinema → slug → langsung play
    slug = _slug_dari_teks(kata) if kata.startswith("http") else None
    if slug:
        d = _get(f"/movies/{slug}/play")
        if d.get("status") and d.get("hls"):
            url = d["hls"] if str(d["hls"]).startswith("http") else API.rstrip("/") + str(d["hls"])
            web = f"{CINEMA}/#{slug}"
            await ktx.balas_kb(f"▶️ {d.get('title') or slug}\n{url}\n🌐 {web}", None)
        else:
            await ktx.balas(f"Link tonton untuk {slug} belum tersedia.")
        return
    d = _get(f"/search?s={urllib.parse.quote(kata)}")
    hasil = (d.get("results") or []) if d.get("status") else []
    if not hasil:
        await ktx.balas(f"Tidak ketemu hasil untuk {kata}. Coba kata kunci lain.")
        return
    SESI_FILM[ktx.chat_id] = {"query": kata, "results": hasil[:10], "tampilan": "daftar"}
    teks, kb = _panel_hasil(ktx.chat_id)
    await ktx.balas_kb(teks, kb)


@REGISTRY.daftar_cb("f:")
async def cb_film(ktx, data: str) -> None:
    bag = (data or "").split(":")
    if len(bag) < 2:
        return
    aksi = bag[1]
    if aksi == "view":  # ganti tampilan
        s = SESI_FILM.get(ktx.chat_id)
        if s:
            s["tampilan"] = "kompak" if s.get("tampilan") == "daftar" else "daftar"
            teks, kb = _panel_hasil(ktx.chat_id)
            await ktx.balas_kb(f"🔀 {teks}", kb)
        return
    if len(bag) < 3:
        return
    slug = ":".join(bag[2:])
    if aksi == "d":
        d = _get(f"/movies/{slug}/stream")
        info = (d.get("result") or {}) if d.get("status") else {}
        if not info:
            await ktx.balas("Detail belum tersedia untuk judul ini (kemungkinan series/redirect).")
            return
        judul = info.get("title") or slug
        teks = (f"🎬 {judul}\n"
                f"⭐ {info.get('rating') or '-'} | 🎭 {info.get('genre') or '-'}\n\n"
                f"{(info.get('synopsis') or '-')[:400]}")
        rows = [[_btn("▶️ Tonton", f"f:p:{slug}"), _btn("🌐 Buka web", f"f:w:{slug}")]]
        await ktx.balas_kb(teks, _kb(rows))
    elif aksi == "p":
        d = _get(f"/movies/{slug}/play")
        url = d.get("hls") if d.get("status") else None
        if url and not str(url).startswith("http"):
            url = API.rstrip("/") + str(url)
        if not url:
            await ktx.balas("Link tonton belum tersedia.")
            return
        await ktx.balas_kb(f"▶️ {d.get('title') or slug}\n{url}", None)
    elif aksi == "w":
        await ktx.balas_kb(f"🌐 {CINEMA}/#{bag[2]}", None)
