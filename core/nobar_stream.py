# nobar_stream.py — voice-chat streamer (sisi userbot + pytgcalls)
# Diparkir: butuh TG_STRING_SESSION valid (akun dedicated). Plugin film.py manggil ini saat ▶️.
import yt_dlp
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, Update, StreamAudioEnded

class NobarStreamer:
    """Satu instance per client Telethon (userbot). Antrean per chat_id."""

    def __init__(self, client):
        from telethon import TelegramClient
        assert isinstance(client, TelegramClient)
        self.client = client
        self.app = PyTgCalls(client)
        self.antre = {}   # chat_id -> list[str url file audio/video]
        self.now = {}     # chat_id -> str
        self.app.add_handler(self._selesai)

    async def mulai(self):
        await self.app.start()

    def _cari_url(self, judul: str) -> str:
        """judul -> direct URL via yt-dlp (bestaudio)."""
        opts = {"format": "bestaudio/best", "quiet": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(f"ytsearch1:{judul}", download=False)
        return info["entries"][0]["url"]

    async def join(self, chat_id: int, judul: str):
        url = self._cari_url(judul)
        stream = MediaStream(url, video_flags=MediaStream.Flags.IGNORE)
        await self.app.join_group_call(chat_id, stream)
        self.now[chat_id] = judul

    async def ganti(self, chat_id: int, judul: str):
        url = self._cari_url(judul)
        stream = MediaStream(url, video_flags=MediaStream.Flags.IGNORE)
        await self.app.change_stream(chat_id, stream)
        self.now[chat_id] = judul

    async def tinggalkan(self, chat_id: int):
        await self.app.leave_group_call(chat_id)
        self.now.pop(chat_id, None)
        self.antre.pop(chat_id, None)

    async def _selesai(self, app, update: Update):
        if isinstance(update, StreamAudioEnded):
            chat_id = update.chat_id
            q = self.antre.get(chat_id)
            if q:
                berikut = q.pop(0)
                await self.ganti(chat_id, berikut)
