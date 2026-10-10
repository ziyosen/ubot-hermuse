"""plugins/film.py — .film cari film via lk21 API (jalur A: Vercel live).
Cari -> tombol detail -> panel info -> tombol ▶️ (buka player web).
Nobar voice chat = jalur B (nobar_stream.py), menyusul setelah userbot login.
"""
import json, urllib.request, urllib.parse
from core.registry import REGISTRY

API = "https://lk21-unofficial-api-tau.vercel.app"
SESI_FILM = {}  # chat_id -> {query, results}


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


@REGISTRY.daftar("film", "member")
async def film(ktx, arg: str) -> None:
    kata = arg.strip()
    if not kata:
        await ktx.balas("Pakai: `.film <judul>` — misal `.film Dune`")
        return
    d = _get(f"/search?s={urllib.parse.quote(kata)}")
    hasil = (d.get("results") or []) if d.get("status") else []
    if not hasil:
        await ktx.balas(f"Tidak ketemu hasil untuk {kata}. Coba kata kunci lain.")
        return
    SESI_FILM[ktx.chat_id] = {"query": kata, "results": hasil[:10]}
    rows = [[_btn((r.get("title") or r.get("slug"))[:40], f"f:d:{r.get('slug')}")]
            for r in hasil[:10] if r.get("slug")]
    await ktx.balas_kb(f"🎬 Hasil untuk {kata} — pilih salah satu:", _kb(rows))


@REGISTRY.daftar_cb("f:")
async def cb_film(ktx, data: str) -> None:
    # data = "f:d:<slug>" detail | "f:p:<slug>" play
    bag = data.split(":")
    if len(bag) < 3:
        return
    aksi, slug = bag[1], ":".join(bag[2:])
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
        rows = [[_btn("▶️ Tonton di web", f"f:p:{slug}")]]
        await ktx.balas_kb(teks, _kb(rows))
    elif aksi == "p":
        d = _get(f"/movies/{slug}/play")
        url = d.get("hls") if d.get("status") else None
        judul_p = d.get("title") or slug
        if not url:
            await ktx.balas("Link tonton belum tersedia.")
            return
        await ktx.balas_kb(f"▶️ {judul_p}\n{url}", None)


# (cb_film terdaftar via dekorator @REGISTRY.daftar_cb("f:") di atas)
