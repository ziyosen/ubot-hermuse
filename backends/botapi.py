"""Backend Bot API — adapter long-polling getUpdates -> Konteks.

- Token dari env BOTAPI_TOKEN (dari .env.botapi, chmod 600).
- Offset disimpan sqlite (tabel botapi_state) — restart tidak replay.
- Parser titik: case-insensitive, hanya teks yang DIMULAI '.',
  dan TIDAK menembus pesan yang punya entity link/code/pre/bot_command
  (misal '.ping' di dalam backtick diabaikan).
- Perintah (NewMessage) vs edited_message dipisah: edit TIDAK memicu perintah.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

from core.backend import Konteks, StatusCache
from core.registry import REGISTRY
from html import escape as _html_escape


def _html(text: str) -> str:
    """Escape teks ke HTML-safe (entitas user seperti <1-3> atau nama aneh aman)."""
    return _html_escape(text)

DB = os.path.join(os.path.dirname(__file__), "..", "botapi.db")


# ---------- infra ----------
def _db() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("""CREATE TABLE IF NOT EXISTS botapi_state
                 (kunci TEXT PRIMARY KEY, nilai TEXT)""")
    return c


def _offset_get(c: sqlite3.Connection) -> int:
    r = c.execute("SELECT nilai FROM botapi_state WHERE kunci='update_offset'").fetchone()
    return int(r[0]) if r else 0


def _offset_set(c: sqlite3.Connection, v: int) -> None:
    c.execute("INSERT INTO botapi_state(kunci,nilai) VALUES('update_offset',?) "
              "ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai", (str(v),))
    c.commit()


def api(token: str, method: str, **params):
    """Panggilan Bot API tahan error (pola review Muse):
    - 'message is not modified' dianggap sukses (edit dobel bukan error)
    - 429 → tunggu retry_after lalu coba lagi (maks 3x)
    - error lain → raise HTTPError asli (pemanggil di atas yang putuskan balasan ramah)
    """
    import time as _time
    for percobaan in range(3):
        data = urllib.parse.urlencode(params).encode()
        try:
            r = urllib.request.urlopen(
                f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=40)
            return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                info = json.loads(e.read())
            except Exception:
                info = {}
            desk = info.get("description", str(e))
            if "message is not modified" in desk:
                return {"ok": True, "result": True}
            if e.code == 429:
                _time.sleep(info.get("parameters", {}).get("retry_after", 2))
                continue
            print(f"[botapi] {method} gagal {e.code}: {desk}")
            raise
        except Exception as e:
            print(f"[botapi] {method} error: {e}")
            if percobaan == 2:
                raise
            _time.sleep(1)
    raise RuntimeError(f"{method} gagal 3x")


# ---------- entity guard ----------
_ENTITY_BLOCK = {"url", "text_link", "code", "pre", "bot_command", "mention"}


def _kena_entity_guard(msg: dict) -> bool:
    """True kalau perintah titik 'tersembunyi' di dalam link/code/pre."""
    ents = msg.get("entities") or []
    teks = msg.get("text", "") or ""
    if not teks.lstrip().startswith("."):
        return False  # bukan perintah titik sama sekali
    for e in ents:
        if e.get("type") in _ENTITY_BLOCK and e.get("offset", 0) == 0:
            return True
    return False


def _parse_perintah(teks: str):
    """Return (nama, argumen) kalau teks dimulai '.', selain itu None."""
    s = teks.strip()
    if not s.startswith("."):
        return None
    s = s[1:]
    if not s:
        return None
    parts = s.split(None, 1)
    return parts[0].lower(), (parts[1] if len(parts) > 1 else "")


# ---------- adapter ----------
class BotAPI:
    def __init__(self, token: str) -> None:
        self.token = token
        self.me_id = 0
        self.status_cache = StatusCache()
        self.db = _db()

    async def start(self) -> None:
        me = api(self.token, "getMe")["result"]
        self.me_id = me["id"]
        print(f"[botapi] login OK: @{me['username']} id={self.me_id} "
              f"privacy_off={me.get('can_read_all_group_messages')}")

    def _status(self, chat_id: int, user_id: int) -> str:
        cached = self.status_cache.get(chat_id, user_id)
        if cached:
            return cached
        try:
            r = api(self.token, "getChatMember", chat_id=chat_id, user_id=user_id)
            st = r["result"]["status"]
        except Exception:
            st = "member"
        self.status_cache.set(chat_id, user_id, st)
        return st

    def _ktx(self, msg: dict, chat: dict, is_edit: bool = False) -> Konteks:
        chat_id = chat["id"]
        sender_id = msg["from"]["id"]
        ktx = Konteks(
            chat_id=chat_id,
            sender_id=sender_id,
            msg_id=msg["message_id"],
            teks=msg.get("text", "") or msg.get("caption", ""),
            chat_type=chat.get("type", "private"),
            sender_status=self._status(chat_id, sender_id),
            backend="botapi",
            is_edit=is_edit,
            entities=msg.get("entities") or msg.get("caption_entities") or [],
            raw=msg,
        )
        ktx._balas = self._mk_balas(chat_id, msg["message_id"])
        ktx._balas_kb = self._mk_balas(chat_id, msg["message_id"], with_kb=True)
        ktx._edit = self._mk_edit(chat_id)
        ktx._hapus = self._mk_hapus(chat_id)
        return ktx

    def _mk_balas(self, chat_id: int, reply_to: int, with_kb: bool = False):
        async def balas(teks: str) -> int:
            try:
                r = api(self.token, "sendMessage", chat_id=chat_id, text=_html(teks),
                        reply_to_message_id=reply_to, parse_mode="HTML")
                print(f"[send] chat={chat_id} ok id={r['result']['message_id']}")
                return r["result"]["message_id"]
            except Exception as e:
                print(f"[send] GAGAL chat={chat_id}: {type(e).__name__} {e}")
                raise

        async def balas_kb(teks: str, kb=None) -> int:
            params = {"chat_id": chat_id, "text": _html(teks), "parse_mode": "HTML"}
            if kb:
                params["reply_markup"] = kb
            try:
                r = api(self.token, "sendMessage", **params)
                print(f"[send] chat={chat_id} kb ok id={r['result']['message_id']}")
                return r["result"]["message_id"]
            except Exception as e:
                print(f"[send] GAGAL kb chat={chat_id}: {type(e).__name__} {e}")
                raise

        return balas_kb if with_kb else balas

    def _mk_edit(self, chat_id: int):
        async def edit(msg_id: int, teks: str) -> None:
            try:
                api(self.token, "editMessageText",
                    chat_id=chat_id, message_id=msg_id, text=_html(teks),
                    parse_mode="HTML")
            except urllib.error.HTTPError as e:
                body = e.read().decode()
                if "message is not modified" not in body:
                    raise
        return edit

    def _mk_hapus(self, chat_id: int):
        async def hapus(msg_ids: list[int]) -> None:
            for mid in msg_ids:
                try:
                    api(self.token, "deleteMessage", chat_id=chat_id, message_id=mid)
                except urllib.error.HTTPError as e:
                    body = e.read().decode()
                    # idempoten: pesan hilang/terlarang = anggap sukses
                    if "not found" not in body and "message can't be deleted" not in body:
                        raise
        return hapus

    async def _handle_callback(self, cb: dict) -> None:
        """callback_query -> Konteks + jawab answerCallbackQuery (selalu)."""
        user = cb.get("from", {})
        data = cb.get("data", "")
        msg = cb.get("message") or {}
        # selalu jawab callback (biar HP user nggak loading terus)
        try:
            api(self.token, "answerCallbackQuery", callback_query_id=cb["id"])
        except Exception:
            pass
        # dispatch: handler 'cb' lama (u:) + tabel prefix (f: dll)
        from core.backend import Konteks
        chat = msg.get("chat", {})
        ktx = Konteks(
            chat_id=chat.get("id", 0),
            sender_id=user.get("id", 0),
            msg_id=msg.get("message_id", 0),
            teks=data,
            chat_type=chat.get("type", "private"),
            sender_status=self._status(chat.get("id", 0), user.get("id", 0)),
            backend="botapi",
            raw={"callback": cb, "data": data},
        )
        ktx._balas = self._mk_balas(chat.get("id", 0), msg.get("message_id", 0))
        ktx._balas_kb = self._mk_balas(chat.get("id", 0), msg.get("message_id", 0), with_kb=True)
        ktx._edit = self._mk_edit(chat.get("id", 0))
        ktx._hapus = self._mk_hapus(chat.get("id", 0))
        print(f"[callback] {user.get('id')} {data}")
        from core.registry import REGISTRY
        if data.startswith("u:"):
            cmd = REGISTRY.get("cb")
            if cmd:
                try:
                    await cmd.callback(ktx, data)
                except Exception as e:
                    print(f"[callback] err: {type(e).__name__} {e}")
            return
        fn = REGISTRY.cb_handler(data)
        if fn:
            try:
                await fn(ktx, data)
            except Exception as e:
                print(f"[callback] err {data[:12]}: {type(e).__name__} {e}")

    async def poll_once(self) -> int:
        """Satu putaran long-poll. Return jumlah update diproses."""
        offset = _offset_get(self.db)
        updates = api(self.token, "getUpdates", offset=offset, timeout=25,
                      allowed_updates=json.dumps(["message", "edited_message", "callback_query"]))
        n = 0
        for upd in updates.get("result", []):
            n += 1
            self.db and _offset_set(self.db, upd["update_id"] + 1)
            if "message" in upd:
                m0=upd["message"]
                print(f"[poll] msg {m0.get('message_id')} from={m0.get('from',{}).get('id')} text={(m0.get('text') or '')[:40]!r}")
                await self._handle(m0, is_edit=False)
            elif "edited_message" in upd:
                await self._handle(upd["edited_message"], is_edit=True)
            elif "callback_query" in upd:
                await self._handle_callback(upd["callback_query"])
        return n

    async def _handle(self, msg: dict, is_edit: bool) -> None:
        sender = msg.get("from", {})
        if sender.get("is_bot"):  # abaikan bot (anti-loop)
            return
        chat = msg.get("chat", {})
        ktx = self._ktx(msg, chat, is_edit=is_edit)
        if is_edit:
            # moderasi edit dikerjakan plugin kunci/filter — di sini tidak memicu perintah
            return
        parsed = _parse_perintah(ktx.teks)
        if not parsed:
            return
        if _kena_entity_guard(msg):
            return  # perintah di dalam code/link diabaikan
        nama, argumen = parsed
        cmd = REGISTRY.get(nama)
        if not cmd:
            return
        if not REGISTRY.boleh(ktx.sender_status, cmd.izin_min):
            await ktx.balas("Maaf, izin kurang buat perintah itu 🙏")
            return
        try:
            await cmd.callback(ktx, argumen)
        except Exception as e:  # jangan crash-loop
            body = ""
            if hasattr(e, "read"):  # HTTPError → ambil deskripsi Telegram
                try: body = e.read().decode()[:200]
                except Exception: pass
            print(f"[botapi] err {nama}: {type(e).__name__} {e} {body}")
            try:
                await ktx.balas("⚠️ Perintah gagal — sudah dicatat di log, coba lagi 🙏")
            except Exception:
                pass
