"""Izin — hirarki owner > agent > member > publik.

Aturan:
- OWNER_IDS (env, numeric user_id dipisah koma) = owner.
- status Telegram 'creator' = owner; 'administrator' = agent;
  'member' = member; selain itu = publik.
- Peran kustom (fase lanjut) TIDAK boleh melebihi langit-langit ini.
"""
from __future__ import annotations

import os

PERINGKAT = {"publik": 0, "member": 1, "agent": 2, "owner": 3}


def owner_ids() -> set[int]:
    raw = os.environ.get("OWNER_IDS", "")
    out = set()
    for x in raw.replace(";", ",").split(","):
        x = x.strip()
        if x.isdigit():
            out.add(int(x))
    return out


def level(chat_id: int, user_id: int, status: str) -> str:
    if user_id in owner_ids():
        return "owner"
    st = (status or "").lower()
    if st == "creator":
        return "owner"
    if st == "administrator":
        return "agent"
    if st in ("member", "restricted"):
        return "member"
    return "publik"


def boleh(izin_user: str, izin_min: str) -> bool:
    return PERINGKAT.get(izin_user, -1) >= PERINGKAT.get(izin_min, 99)
