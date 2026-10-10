"""Registry perintah — AGNOSTIK backend.

Perintah = (nama, izin_min, callback). Backend (Bot API / Telethon) tinggal
memanggil dispatch(); registry tidak tahu asal pesan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .backend import Konteks

# hierarki izin: publik < member < agent < owner
PERINGKAT = {"publik": 0, "member": 1, "agent": 2, "owner": 3}


@dataclass
class Perintah:
    nama: str
    izin_min: str
    callback: Callable[[Konteks, str], Awaitable[None]]


class Registry:
    def __init__(self) -> None:
        self._cmds: dict[str, Perintah] = {}

    def daftar(self, nama: str, izin_min: str = "member"):
        def deco(fn):
            self._cmds[nama.lower()] = Perintah(nama.lower(), izin_min, fn)
            return fn
        return deco

    def get(self, nama: str) -> Perintah | None:
        return self._cmds.get(nama.lower())

    def semua(self) -> list[str]:
        return sorted(self._cmds)

    def boleh(self, izin_user: str, izin_min: str) -> bool:
        """izin_user bisa berupa status Telegram mentah (creator/administrator/
        member/restricted/left) ATAU level izin (owner/agent/member/publik).
        Petakan status Telegram dulu, baru bandingkan."""
        MAP = {"creator": "owner", "administrator": "agent",
               "restricted": "member", "member": "member", "left": "publik"}
        lvl = MAP.get(izin_user, izin_user)
        return PERINGKAT.get(lvl, 0) >= PERINGKAT.get(izin_min, 99)


REGISTRY = Registry()
