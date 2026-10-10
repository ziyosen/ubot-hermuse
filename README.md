# ubot-hermuse

Bot grup Telegram multifungsi (Hermes × Muse) — arsitektur dua lapis:
- **Bot API layer** (`backends/botapi.py`): long-polling, parser perintah titik, callback_query
- **Userbot layer** (`core/nobar_stream.py`): voice-chat streaming via pytgcalls (nobar/musik)

## Fitur aktif
- Plugin UNO lengkap: lobby, inline keyboard, panel status live (edit), AFK timer, BOT 3 level strategi
- `.film` / `.nobar` — cari & nobar via voice chat (fase userbot)

## Deploy
Lihat [deploy/DEPLOY.md](deploy/DEPLOY.md). Token/session TIDAK pernah masuk repo (.gitignore).

## Perintah
`.ping` `.status` `.uno` `.uno join` `.uno bot <1-3>` `.uno start` `.main <n>` `.ambil` `.kartu` `.uno call` `.uno stop`
