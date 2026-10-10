"""Plugin dasar: .ping (publik) dan .status (owner) — selaras dengan
pola yang disepakati (pesan status satu yang di-EDIT, bukan spam baru).

.ping  -> balas "pong 123ms"
.status -> balas "memproses..." lalu di-EDIT jadi laporan status
"""
from __future__ import annotations

import os
import time

from core.registry import REGISTRY

T0 = time.time()


@REGISTRY.daftar("ping", "publik")
async def ping(ktx, arg: str) -> None:
    t = time.time()
    await ktx.balas(f"pong {(t - T0):.0f}s uptime · {t:.3f}")


@REGISTRY.daftar("status", "owner")
async def status(ktx, arg: str) -> None:
    mid = await ktx.balas("memproses...")
    await ktx.edit(mid, (
        "status: hidup ✅\n"
        f"backend: {ktx.backend}\n"
        f"uptime: {(time.time() - T0) / 60:.1f} menit\n"
        f"pid: {os.getpid()}"
    ))
