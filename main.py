"""Entry point runtime Bot API — long-polling + registry plugin.

Jalankan:  .venv/bin/python main.py
Token:     BOTAPI_TOKEN dari .env.botapi (chmod 600, jangan commit)
"""
from __future__ import annotations

import asyncio
import importlib
import os
import pkgutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def muat_env() -> None:
    p = ROOT / ".env.botapi"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def muat_plugin() -> list[str]:
    import plugins  # noqa: F401
    nama = []
    for m in pkgutil.iter_modules(plugins.__path__):
        importlib.import_module(f"plugins.{m.name}")
        nama.append(m.name)
    return nama


async def main() -> None:
    muat_env()
    token = os.environ.get("BOTAPI_TOKEN")
    if not token:
        raise SystemExit("BOTAPI_TOKEN belum ada di .env.botapi")
    modul = muat_plugin()
    from core.registry import REGISTRY
    print(f"[main] plugin: {', '.join(modul)}")
    print(f"[main] perintah: {', '.join(REGISTRY.semua())}")

    from backends.botapi import BotAPI
    bot = BotAPI(token)
    await bot.start()
    while True:
        try:
            await bot.poll_once()
        except Exception as e:
            print(f"[main] poll err: {type(e).__name__} {e}")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
