"""login_userbot.py — login sekali jalan di VPS (interaktif).
Jalankan: cd /opt/ubot-hermuse && .venv/bin/python login_userbot.py
Butuh: .env.nobar berisi TG_API_ID & TG_API_HASH.
OTP akan dikirim Telegram ke akun dedicated (app/HP bos) — ketik di prompt ini dalam 60 detik!
Output: TG_STRING_SESSION dicetak + otomatis ditulis ke .env.nobar (chmod 600). TIDAK dikirim ke chat mana pun.
"""
import os, sys, getpass
from dotenv import load_dotenv
load_dotenv("/opt/ubot-hermuse/.env.nobar")
api_id = os.environ.get("TG_API_ID")
api_hash = os.environ.get("TG_API_HASH")
if not api_id or not api_hash:
    sys.exit("TG_API_ID/TG_API_HASH kosong di .env.nobar")
from telethon import TelegramClient
from telethon.sessions import StringSession

with TelegramClient(StringSession(), int(api_id), api_hash) as c:
    if not c.is_user_authorized():
        phone = input("Nomor HP akun dedicated (format +62...): ")
        c.send_code_request(phone)
        code = input("Kode OTP (cek Telegram/SMS akun dedicated, ~60 dtk): ").strip()
        try:
            c.sign_in(phone, code)
        except Exception as e:
            if "Two-steps" in str(e) or "PASSWORD" in str(e).upper():
                pw = getpass.getpass("Password 2FA: ")
                c.sign_in(password=pw)
            else:
                raise
    ses = c.session.save()
    print("TG_STRING_SESSION OK (panjang", len(ses), ")")
    path = "/opt/ubot-hermuse/.env.nobar"
    lines = open(path).read().splitlines()
    lines = [l for l in lines if not l.startswith("TG_STRING_SESSION=")]
    lines.append(f"TG_STRING_SESSION={ses}")
    open(path, "w").write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)
    print("Tersimpan di .env.nobar (600) ✅ — jalankan: systemctl restart ubot-nobar")
