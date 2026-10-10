"""Plugin UNO Telegram — sesi per-grup di memori (v1), state engine di RAM.

CATATAN v1 (review Muse): state di memori = restart runtime = game hilang.
Pindah ke sqlite (pola kv (chat_id,scope,kunci) seperti modul lain) di fase 2.
Adaptor Telegram: callback_query (tombol kartu) ditangani backends/botapi.py
-> dispatch ke handler "cb" di sini dengan data "u:<aksi>:<arg>".

Perintah (semua diawali titik, case-insensitive):
  .uno            -> mulai lobby / lihat status lobby
  .uno join       -> gabung lobby
  .uno start      -> mulai permainan (host saja)
  .uno bot <1-3>  -> tambah BOT dengan level kesulitan
  .main <n> [warna]  -> mainkan kartu ke-n dari tanganmu (warna utk wild)
  .ambil          -> ambil 1 kartu (kalau tak bisa main)
  .kartu          -> lihat tanganmu (balasan privat via reply)
  .uno call       -> klaim UNO (sisa 1 kartu)
  .uno status     -> status permainan (giliran, arah, kartu atas)

Pemetaan identitas: user_id Telegram -> nama pendek (first_name).
BOT = pemain "BOT" dengan strategi core/strategi.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import random

from backends.botapi import api
from core.registry import REGISTRY
from core.strategi import pilih
from core.uno import Engine, Hasil, WARNA

# sesi per chat_id (v1 memori; sqlite menyusul)
SESI: dict[int, dict] = {}
TASK_BOT: dict[int, asyncio.Task] = {}

WARNA_ALIAS = {
    "m": "merah", "merah": "merah", "r": "merah", "red": "merah",
    "k": "kuning", "kuning": "kuning", "yellow": "kuning",
    "h": "hijau", "hijau": "hijau", "green": "hijau",
    "b": "biru", "biru": "biru", "blue": "biru",
}


def _sesi(chat_id: int) -> dict | None:
    s = SESI.get(chat_id)
    if not s:
        return None
    e = s.get("engine")
    # lobby (engine None) tetap valid; sesi selesai dianggap tidak ada
    if e is not None and e.state.fase == "selesai":
        return None
    return s


def _kartu_str(k) -> str:
    ikon = {"skip": "🚫", "reverse": "🔄", "draw2": "+2", "wild": "🌈", "wild4": "+4"}
    w = {"merah": "🔴", "kuning": "🟡", "hijau": "🟢", "biru": "🔵", None: "⚫"}
    return f"{w.get(k.warna, '⚫')}{ikon.get(k.nilai, k.nilai)}"


def _tangan_str(tangan: list) -> str:
    return "  ".join(f"[{i+1}]{_kartu_str(k)}" for i, k in enumerate(tangan))


def _status_str(e: Engine) -> str:
    s = e.state
    atas = _kartu_str(s.kartu_atas) if s.kartu_atas else "-"
    panah = "🔁" if s.arah == -1 else "➡️"
    baris = [f"🎴 atas: {atas} | warna: {s.warna_aktif} | {panah}"]
    for p in s.pemain:
        tanda = "👉" if p == e.pemain_giliran() else "  "
        sisa = len(s.tangan[p])
        uno = " ❗UNO" if sisa == 1 else ""
        baris.append(f"{tanda} {p}: {sisa} kartu{uno}")
    baris.append(f"draw pile: {len(s.draw_pile)}")
    return "\n".join(baris)


def _host(sesi: dict, user_id: int) -> bool:
    return sesi.get("host") == user_id


def _sebut(e: Engine, nama: str, ktx) -> str:
    """Nama pemain (fase 1: teks biasa — mention HTML menyusul, butuh noescape path)."""
    return nama


def sesi_uid(chat_id: int) -> dict:
    return SESI.get(chat_id, {}).get("uid", {})


# ---------- bot loop: main otomatis saat giliran BOT ----------
async def bot_loop(ktx, chat_id: int) -> None:
    sesi = SESI.get(chat_id)
    if not sesi:
        return
    e = sesi["engine"]
    while e.state.fase == "bermain" and e.pemain_giliran() == "BOT":
        await asyncio.sleep(1 + random.random())  # 1-2 dtk, biar natural
        pl = pilih(e.state, sesi.get("bot_level", 1), random.Random())
        if pl is None:
            e.ambil("BOT")
            await ktx.balas(f"🤖 BOT ambil kartu ({len(e.state.tangan['BOT'])} sisa)")
            if e.state.fase == "selesai":
                break
            continue
        k, warna = pl
        e.main_kartu("BOT", k, warna)
        teks = f"🤖 BOT main {_kartu_str(k)}"
        if k.nilai in ("wild", "wild4"):
            teks += f" → warna: {warna}"
        teks += f" ({len(e.state.tangan['BOT'])} sisa)"
        await ktx.balas(teks)
        if e.state.fase == "selesai":
            break
    if e.state.fase == "selesai":
        pemenang = e.state.pemenang
        await ktx.balas(f"🏆 PERMAINAN SELESAI! Pemenang: **{pemenang}**\n" + _status_str(e))
        SESI.pop(chat_id, None)
        TASK_BOT.pop(chat_id, None)
    elif e.state.fase == "bermain":
        await ktx.balas(_sebut_milik(ktx, chat_id, e) + "\n" + _status_str(e))


def _panel_teks(e: Engine, extra: str = "") -> str:
    """Teks panel status untuk pesan yang di-edit terus."""
    teks = "🎮 **UNO**\n" + _status_str(e)
    if extra:
        teks += "\n" + extra
    return teks


def _tombol_untuk(e: Engine, uid: int, uid_map: dict) -> list:
    """Inline keyboard utk pemain yg giliran; lawan lihat info saja."""
    from core.strategi import _bisa  # reuse predikat
    p = e.pemain_giliran()
    rows = []
    if p != "BOT" and uid_map.get(p) == uid:
        tangan = e.state.tangan[p]
        row = []
        for i, k in enumerate(tangan):
            if _bisa(e.state, k):
                row.append({"text": _kartu_str(k), "callback_data": f"u:m:{i}"})
                if len(row) == 5:
                    rows.append(row); row = []
        if row: rows.append(row)
        rows.append([{"text": "🃏 Ambil", "callback_data": "u:a:"},
                     {"text": "❗ UNO!", "callback_data": "u:c:"}])
    else:
        rows.append([{"text": f"⏳ giliran {p}", "callback_data": "u:x:"}])
    # pilih warna (kalau kartu atas wild & barusan dimainkan)
    return rows


async def kirim_panel(ktx, chat_id: int, extra: str = "") -> None:
    """Kirim/edit panel status (SATU pesan, di-edit terus)."""
    s = SESI.get(chat_id)
    if not s or not s.get("engine"):
        return
    e = s["engine"]
    teks = _panel_teks(e, extra)
    rows = _tombol_untuk(e, s.get("panel_uid", 0), s["uid"])
    mid = s.get("status_msg_id")
    if mid:
        try:
            import backends.botapi as B
            B.api(B.os.environ["BOTAPI_TOKEN"], "editMessageText",
                  chat_id=chat_id, message_id=mid, text=teks,
                  reply_markup=json.dumps({"inline_keyboard": rows}))
            return
        except Exception as ex:
            body = getattr(ex, "read", lambda: b"")().decode()[:150]
            print(f"[panel] edit gagal ({type(ex).__name__} {body}) → kirim baru")
            s["status_msg_id"] = None  # pesan hilang/korup → kirim baru
    import backends.botapi as B
    r = B.api(B.os.environ["BOTAPI_TOKEN"], "sendMessage",
              chat_id=chat_id, text=teks,
              reply_markup=json.dumps({"inline_keyboard": rows}))
    s["status_msg_id"] = r["result"]["message_id"]


def _sebut_milik(ktx, chat_id: int, e: Engine) -> str:
    p = e.pemain_giliran()
    return f"👉 giliran {p}"


def _jadikan_bot(ktx, chat_id: int) -> None:
    old = TASK_BOT.get(chat_id)
    if old and not old.done():
        old.cancel()
    TASK_BOT[chat_id] = asyncio.create_task(bot_loop(ktx, chat_id))


# ---------- perintah ----------
@REGISTRY.daftar("uno", "member")
async def uno(ktx, arg: str) -> None:
    chat_id = ktx.chat_id
    arg = arg.strip().lower()
    s = _sesi(chat_id)

    if not s:
        # lobby baru — engine dipasang setelah ada >= 2 pemain
        nama = ktx.raw["from"].get("first_name", str(ktx.sender_id))
        SESI[chat_id] = {
            "engine": None,
            "host": ktx.sender_id,
            "uid": {nama: ktx.sender_id},
            "pemain": [nama],
            "bot_level": 1,
        }
        await ktx.balas(
            f"🎮 Lobby UNO dibuat oleh {nama}!\n"
            "Ketik `.uno join` untuk gabung, `.uno bot <1-3>` tambah BOT,\n"
            "`.uno start` mulai (host)."
        )
        return

    e = s["engine"]
    if arg == "join":
        if e and e.state.fase != "lobby":
            await ktx.balas("Permainan udah jalan, tunggu ronde berikutnya 🙏")
            return
        nama = ktx.raw["from"].get("first_name", str(ktx.sender_id))
        if nama in s["pemain"]:
            await ktx.balas(f"{nama} udah di lobby 😄")
            return
        s["pemain"].append(nama)
        s["uid"][nama] = ktx.sender_id
        await ktx.balas(f"✅ {nama} gabung! ({len(s['pemain'])} pemain)")
    elif arg.startswith("bot"):
        parts = arg.split()
        lvl = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        lvl = max(1, min(3, lvl))
        if e:
            await ktx.balas("Bot cuma bisa ditambah pas lobby 🙏")
            return
        if "BOT" in s["pemain"]:
            await ktx.balas("BOT udah ada di lobby")
            return
        s["pemain"].append("BOT")
        s["bot_level"] = lvl
        await ktx.balas(f"🤖 BOT gabung (level {lvl})! ({len(s['pemain'])} pemain)")
    elif arg == "start":
        if not _host(s, ktx.sender_id):
            await ktx.balas("Cuma host yang bisa mulai 🙏")
            return
        if len(s["pemain"]) < 2:
            await ktx.balas("Minimal 2 pemain (bisa BOT: `.uno bot 2`)")
            return
        eng = Engine()
        eng.buat_lobby(list(s["pemain"]))
        eng.mulai()
        # state baru DIPASANG hanya setelah pesan status sukses (pola Muse: tak ada state setengah jalan)
        mid = await ktx.balas("🎮 UNO DIMULAI!\n" + _status_str(eng) +
                              "\n`.main <n>` main kartu, `.ambil` ambil, `.kartu` lihat tangan, `.uno call` UNO!")
        s["engine"] = eng
        e = eng
        s["deadline"] = asyncio.get_event_loop().time() + 60
        s["status_msg_id"] = mid
        _mulai_watchdog(ktx, chat_id)
        if eng.pemain_giliran() == "BOT":
            _jadikan_bot(ktx, chat_id)
    elif arg == "call":
        # klaim UNO
        nama = ktx.raw["from"].get("first_name", str(ktx.sender_id))
        r = e.uno(nama)
        if r == Hasil.OK:
            await ktx.balas(f"❗ {nama}: UNO!")
        else:
            await ktx.balas(f"{nama}, UNO cuma bisa dibilang pas sisa 1 kartu 😅")
    elif arg == "status":
        if e.state.fase == "lobby":
            await ktx.balas(f"Lobby ({len(e.state.pemain)}): {', '.join(e.state.pemain)}")
        else:
            await ktx.balas(_status_str(e))
    elif arg == "stop":
        if _host(s, ktx.sender_id):
            SESI.pop(chat_id, None)
            t = TASK_BOT.pop(chat_id, None)
            if t: t.cancel()
            await ktx.balas("🛑 UNO dihentikan host.")
        else:
            await ktx.balas("Cuma host yang bisa stop 🙏")
    else:
        await ktx.balas(
            "Pakai: `.uno join` | `.uno bot <1-3>` | `.uno start` | "
            "`.uno call` | `.uno status` | `.uno stop`"
        )


@REGISTRY.daftar("main", "member")
async def main_kartu_cmd(ktx, arg: str) -> None:
    s = _sesi(ktx.chat_id)
    if not s:
        await ktx.balas("Belum ada game. `.uno` buat mulai!")
        return
    e = s["engine"]
    nama = ktx.raw["from"].get("first_name", str(ktx.sender_id))
    if e.pemain_giliran() != nama:
        await ktx.balas(f"Bukan giliranmu, sekarang {e.pemain_giliran()} 🙏")
        return
    parts = arg.split()
    if not parts or not parts[0].isdigit():
        await ktx.balas("Pakai: `.main <nomor> [warna]` — `.kartu` buat lihat nomor")
        return
    idx = int(parts[0]) - 1
    tangan = e.state.tangan[nama]
    if idx < 0 or idx >= len(tangan):
        await ktx.balas(f"Nomor 1-{len(tangan)} aja 🙏")
        return
    kartu = tangan[idx]
    warna = WARNA_ALIAS.get(parts[1]) if len(parts) > 1 else None
    if kartu.nilai in ("wild", "wild4") and not warna:
        await ktx.balas("Pilih warna: `.main <n> merah|kuning|hijau|biru`")
        return
    r = e.main_kartu(nama, kartu, warna)
    if r == Hasil.TAK_COCOK:
        await ktx.balas(f"{_kartu_str(kartu)} nggak cocok (atas: {_kartu_str(e.state.kartu_atas)}, warna: {e.state.warna_aktif})")
        return
    if r == Hasil.TAK_MILIK:
        await ktx.balas("Kartu itu bukan milikmu 🤨")
        return
    if r == Hasil.MENANG:
        await ktx.balas(f"🏆 {nama} MENANG! (main {_kartu_str(kartu)})")
        SESI.pop(ktx.chat_id, None)
        t = TASK_BOT.pop(ktx.chat_id, None)
        if t: t.cancel()
        return
    teks = f"▶️ {nama} main {_kartu_str(kartu)}"
    if kartu.nilai in ("wild", "wild4"):
        teks += f" → warna: {e.state.warna_aktif}"
    await ktx.balas(teks + "\n" + _status_str(e))
    # sisa 1 kartu → ingatkan UNO
    if len(e.state.tangan[nama]) == 1 and nama not in e.state.uno_diklaim:
        await ktx.balas(f"❗ {nama} sisa 1 kartu! Jangan lupa `.uno call`")
    if e.pemain_giliran() == "BOT":
        _jadikan_bot(ktx, ktx.chat_id)


@REGISTRY.daftar("ambil", "member")
async def ambil_cmd(ktx, arg: str) -> None:
    s = _sesi(ktx.chat_id)
    if not s:
        await ktx.balas("Belum ada game. `.uno` buat mulai!")
        return
    e = s["engine"]
    nama = ktx.raw["from"].get("first_name", str(ktx.sender_id))
    if e.pemain_giliran() != nama:
        await ktx.balas(f"Bukan giliranmu 🙏 (sekarang: {e.pemain_giliran()})")
        return
    r, k = e.ambil(nama)
    if r == Hasil.AMBIL_MAIN_OK:
        await ktx.balas(f"🃏 {nama} ambil {_kartu_str(k)} — cocok! `.main` nomornya atau biarkan lewat")
        return
    await ktx.balas(f"🃏 {nama} ambil kartu ({len(e.state.tangan[nama])} sisa)\n" + _status_str(e))
    if e.pemain_giliran() == "BOT":
        _jadikan_bot(ktx, ktx.chat_id)


@REGISTRY.daftar("cb", "publik")
async def cb_handler(ktx, data: str) -> None:
    """Handler callback_query tombol UNO: u:m:<i> | u:a: | u:c: | u:p:<warna>."""
    chat_id = ktx.chat_id
    s = _sesi(chat_id)
    if not s or not s.get("engine"):
        return
    e = s["engine"]
    uid = ktx.sender_id
    # cari nama pemain dari uid
    nama = next((n for n, u in s["uid"].items() if u == uid), None)
    parts = data.split(":")
    aksi = parts[1] if len(parts) > 1 else ""

    if aksi == "x":  # info tombol (bukan giliranmu) — sudah dijawab answerCallbackQuery
        return
    if e.state.fase != "bermain":
        return

    # guard: aksi kartu/ambil hanya pemilik giliran
    if aksi in ("m", "a", "c"):
        if e.pemain_giliran() != nama:
            return
        s["deadline"] = asyncio.get_event_loop().time() + 60  # reset AFK

    if aksi == "m":
        try:
            idx = int(parts[2])
        except (IndexError, ValueError):
            return
        tangan = e.state.tangan[nama]
        if idx < 0 or idx >= len(tangan):
            return
        kartu = tangan[idx]
        if kartu.nilai in ("wild", "wild4"):
            # minta pilih warna: tampilkan tombol warna (simpan indeks)
            s["menunggu_warna"] = idx
            s["panel_uid"] = uid
            rows = [[{"text": e_, "callback_data": f"u:p:{w_}"} for e_, w_ in
                     [("🔴 merah","merah"),("🟡 kuning","kuning"),
                      ("🟢 hijau","hijau"),("🔵 biru","biru")]]]
            import backends.botapi as B
            B.api(os.environ["BOTAPI_TOKEN"], "editMessageReplyMarkup",
                  chat_id=chat_id, message_id=s.get("status_msg_id"),
                  reply_markup=json.dumps({"inline_keyboard": rows}))
            return
        _eksekusi_main(ktx, chat_id, nama, kartu, None)
    elif aksi == "p":
        idx = s.pop("menunggu_warna", None)
        if idx is None or e.pemain_giliran() != nama:
            return
        warna = parts[2] if len(parts) > 2 else None
        if warna not in WARNA:
            return
        kartu = e.state.tangan[nama][idx]
        _eksekusi_main(ktx, chat_id, nama, kartu, warna)
    elif aksi == "a":
        r, k = e.ambil(nama)
        extra = f"🃏 {nama} ambil kartu"
        if r == Hasil.AMBIL_MAIN_OK:
            extra += f" — dapat {_kartu_str(k)}, cocok! tap kartunya"
        elif r == Hasil.BUKAN_GILIRAN:
            return
        else:
            extra += f" ({len(e.state.tangan[nama])} sisa)"
        s["panel_uid"] = uid
        await kirim_panel(ktx, chat_id, extra)
        if e.pemain_giliran() == "BOT":
            _jadikan_bot(ktx, chat_id)
    elif aksi == "c":
        r = e.uno(nama)
        extra = f"❗ {nama}: UNO!" if r == Hasil.OK else f"{nama}, sisa 1 kartu dulu baru UNO 😅"
        await kirim_panel(ktx, chat_id, extra)


def _eksekusi_main(ktx, chat_id: int, nama: str, kartu, warna) -> None:
    s = SESI[chat_id]
    e = s["engine"]
    r = e.main_kartu(nama, kartu, warna)
    if r in (Hasil.TAK_COCOK, Hasil.TAK_MILIK, Hasil.BUKAN_GILIRAN):
        return
    extra = f"▶️ {nama} main {_kartu_str(kartu)}"
    if kartu.nilai in ("wild", "wild4"):
        extra += f" → warna: {e.state.warna_aktif}"
    if r == Hasil.MENANG:
        s["engine"].state.fase = "selesai"
        import asyncio as _a
        _a.get_event_loop().create_task(ktx.balas(f"🏆 {nama} MENANG! 🎉"))
        SESI.pop(chat_id, None)
        t = TASK_BOT.pop(chat_id, None)
        if t: t.cancel()
        return
    if len(e.state.tangan[nama]) == 1 and nama not in e.state.uno_diklaim:
        extra += f"\n❗ {nama} sisa 1 — jangan lupa UNO!"
    s["panel_uid"] = s["uid"].get(nama, 0)
    import asyncio as _a
    _a.get_event_loop().create_task(kirim_panel(ktx, chat_id, extra))
    if e.pemain_giliran() == "BOT":
        _jadikan_bot(ktx, chat_id)


@REGISTRY.daftar("kartu", "member")
async def kartu_cmd(ktx, arg: str) -> None:
    s = _sesi(ktx.chat_id)
    if not s:
        await ktx.balas("Belum ada game.")
        return
    e = s["engine"]
    nama = ktx.raw["from"].get("first_name", str(ktx.sender_id))
    if nama not in e.state.tangan:
        await ktx.balas("Kamu nggak ikut main 🙏")
        return
    await ktx.balas(
        f"🤚 Tangan {nama} ({len(e.state.tangan[nama])} kartu):\n"
        + _tangan_str(e.state.tangan[nama])
        + f"\nAtas: {_kartu_str(e.state.kartu_atas)} | warna aktif: {e.state.warna_aktif}"
    )


# ---------- watchdog anti-AFK ----------
def _mulai_watchdog(ktx, chat_id: int) -> None:
    async def watch():
        while True:
            await asyncio.sleep(5)
            s = _sesi(chat_id)
            if not s or not s.get("engine"):
                return
            e = s["engine"]
            if e.state.fase != "bermain":
                return
            dl = s.get("deadline", 0)
            if dl and asyncio.get_event_loop().time() > dl:
                p = e.pemain_giliran()
                if p == "BOT":
                    continue  # BOT punya loop sendiri
                e.ambil(p)
                s["deadline"] = asyncio.get_event_loop().time() + 60
                await ktx.balas(f"⏰ {p} AFK 60 dtk — auto ambil kartu")
                if e.pemain_giliran() == "BOT":
                    _jadikan_bot(ktx, chat_id)
    TASK_BOT[chat_id] = asyncio.create_task(watch())
