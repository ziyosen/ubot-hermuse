# ubot-hermuse

Bot grup Telegram multifungsi (Hermes × Muse) — arsitektur dua lapis:
- **Bot API layer** (`backends/botapi.py`): long-polling, parser perintah titik, callback_query
- **Userbot layer** (`core/nobar_stream.py`): voice-chat streaming via pytgcalls (nobar/musik)

## Fitur aktif
- `.film` — cari film via lk21 API + panel info + tombol ▶️ player
- `.nobar` — nobar via voice chat (fase userbot)

## Deploy
Lihat [deploy/DEPLOY.md](deploy/DEPLOY.md). Token/session TIDAK pernah masuk repo (.gitignore).

## Perintah
`.ping` `.status` `.film <judul>`
