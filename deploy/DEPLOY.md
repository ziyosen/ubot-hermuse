# Deploy ke VPS (Ubuntu/Debian)
1. rsync -av --delete --exclude '.env*' --exclude '.venv' ubot-hermuse/ root@VPS:/opt/ubot-hermuse/
2. cd /opt/ubot-hermuse && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   (atau: uv venv && uv pip install -r requirements.txt)
3. buat .env.botapi dari .env.example, isi BOTAPI_TOKEN, chmod 600
4. cp deploy/ubot-hermuse.service /etc/systemd/system/ && systemctl daemon-reload
5. systemctl enable --now ubot-hermuse
6. smoke test: .ping / .status di grup
Token & session TIDAK pernah ikut git (tercatat di .gitignore).
