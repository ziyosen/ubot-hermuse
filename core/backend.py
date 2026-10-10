"""Konteks seragam (backend-agnostic) — fondasi dua lapis Hermes x Muse.

Field wajib (disepakati cross-review):
  chat_id, sender_id, msg_id, teks, chat_type, sender_status, backend, target_id
Metode: balas() -> mengembalikan msg_id hasil kirim, edit(), hapus(), react().
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Konteks:
    chat_id: int
    sender_id: int
    msg_id: int
    teks: str
    chat_type: str = "group"          # private | group | supergroup | channel
    sender_status: str = "member"     # creator | administrator | member | left | restricted
    backend: str = "botapi"           # botapi | telethon
    target_id: Optional[int] = None   # hasil reply / argumen
    is_edit: bool = False
    entities: list = field(default_factory=list)
    raw: Any = None
    # diisi adapter:
    _balas: Optional[Callable[[str], Awaitable[int]]] = None
    _balas_kb: Optional[Callable[[str, Any], Awaitable[int]]] = None
    _edit: Optional[Callable[[int, str], Awaitable[None]]] = None
    _hapus: Optional[Callable[[list[int]], Awaitable[None]]] = None

    # ---- operasi umum, semuanya lewat adapter backend ----
    async def balas(self, teks: str) -> int:
        assert self._balas, "adapter belum memasang _balas"
        return await self._balas(teks)

    async def balas_kb(self, teks: str, kb=None) -> int:
        """Kirim pesan dengan inline keyboard opsional (fallback: tanpa kb)."""
        if self._balas_kb:
            return await self._balas_kb(teks, kb)
        return await self.balas(teks)

    async def edit(self, msg_id: int, teks: str) -> None:
        assert self._edit, "adapter belum memasang _edit"
        await self._edit(msg_id, teks)

    async def hapus(self, msg_ids: list[int]) -> None:
        assert self._hapus, "adapter belum memasang _hapus"
        await self._hapus(msg_ids)


class StatusCache:
    """Cache status pengirim per (chat_id, user_id) — hot path, TTL 60 dtk."""

    TTL = 60

    def __init__(self) -> None:
        self._d: dict[tuple[int, int], tuple[str, float]] = {}

    def get(self, chat_id: int, user_id: int) -> Optional[str]:
        v = self._d.get((chat_id, user_id))
        if not v:
            return None
        status, ts = v
        if time.time() - ts > self.TTL:
            self._d.pop((chat_id, user_id), None)
            return None
        return status

    def set(self, chat_id: int, user_id: int, status: str) -> None:
        self._d[(chat_id, user_id)] = (status, time.time())
