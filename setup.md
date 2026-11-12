# Setup guide — self-hosted SMTP mail server

This project runs **your own** SMTP receiver (`aiosmtpd`), optional **direct outbound** delivery (MX on port 25), and an **HTTP API** (`FastAPI`) for health checks and sending mail. No Gmail, SendGrid, or other email SaaS is required.

Open-source **Python libraries** from `requirements.txt` are installed into **your** environment only.

---

## Prerequisites

- **Python 3.11+**
- Virtual environment at `.venv` (create below if missing)
- **Domain** you control (production)
- **VPS or dedicated server** recommended for real internet mail (inbound 25 / outbound 25)
- **Render.com** (optional): HTTP + API works; **direct SMTP to the world is usually blocked** on PaaS (see [Render](#rendercom-optional))

---

## 1. Local setup (Windows)

Project root (example):

`D:\Public\Local\temp_python`

### Create / activate virtual environment

```powershell
cd D:\Public\Local\temp_python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Environment file

```powershell
copy .env.example .env
```

Edit `.env` for your case:

| Variable | Typical local value | Notes |
|----------|---------------------|--------|
| `SMTP_HOST` | `0.0.0.0` | Listen on all interfaces (Windows bind fix is built-in) |
| `SMTP_PORT` | `2525` | Use `25` or `587` only if you run as admin and open firewall |
| `MAIL_DOMAIN` | `mail.yourdomain.com` | EHLO / Message-ID domain |
| `OUTBOUND_MODE` | `direct` | Self-owned sending |
| `OUTBOUND_FROM_EMAIL` | `noreply@yourdomain.com` | Must match your domain for deliverability |
| `SMTP_AUTH_USER` / `SMTP_AUTH_PASSWORD` | set strong values | Recommended before exposing SMTP |
| `API_KEY` | random secret | Protects `/messages` and `/send` |
| `DATA_DIR` | `data` | Stored `.eml` files |

### Run the server

```powershell
python -m smtp_server.main
```

Expected logs:

- Inbound SMTP on `SMTP_HOST:SMTP_PORT`
- HTTP API on `http://0.0.0.0:PORT` (default `8000`)

### Verify HTTP

```powershell
curl http://127.0.0.1:8000/health
```

### Test receive (SMTP client)

```powershell
python -c "
import smtplib
from email.message import EmailMessage
msg = EmailMessage()
msg['Subject'] = 'Inbound test'
msg['From'] = 'sender@example.com'
msg['To'] = 'you@example.com'
msg.set_content('Hello')
with smtplib.SMTP('127.0.0.1', 2525) as s:
    s.send_message(msg)
print('OK')
"
```

If SMTP AUTH is enabled:

```powershell
python -c "
import smtplib
from email.message import EmailMessage
msg = EmailMessage()
msg['Subject'] = 'Auth test'
msg['From'] = 'sender@example.com'
msg['To'] = 'you@example.com'
msg.set_content('Hello')
with smtplib.SMTP('127.0.0.1', 2525) as s:
    s.login('YOUR_SMTP_AUTH_USER', 'YOUR_SMTP_AUTH_PASSWORD')
    s.send_message(msg)
"
```

### List received mail

```powershell
curl http://127.0.0.1:8000/messages
# With API_KEY:
curl -H "X-API-Key: YOUR_API_KEY" http://127.0.0.1:8000/messages
```

### Send mail (HTTP → outbound direct or relay)

```powershell
curl -X POST http://127.0.0.1:8000/send -H "Content-Type: application/json" -d "{\"to\":[\"recipient@example.com\"],\"subject\":\"Test\",\"body_text\":\"Hello\"}"
```

With API key:

```powershell
curl -X POST http://127.0.0.1:8000/send -H "Content-Type: application/json" -H "X-API-Key: YOUR_API_KEY" -d "{\"to\":[\"recipient@example.com\"],\"subject\":\"Test\",\"body_text\":\"Hello\"}"
```

---

## 2. Production on your VPS (recommended for owned mail)

### Install on Linux

```bash
cd /opt/mail-server
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: SMTP_PORT=25 or 587, MAIL_DOMAIN, SPF/DKIM aligned From address
```

### systemd unit (example)

Create `/etc/systemd/system/smtp-mail-server.service`:

```ini
[Unit]
Description=Python SMTP mail server
After=network.target

[Service]
Type=simple
User=mailapp
WorkingDirectory=/opt/mail-server
EnvironmentFile=/opt/mail-server/.env
ExecStart=/opt/mail-server/.venv/bin/python -m smtp_server.main
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now smtp-mail-server
```

### Firewall

```bash
# SMTP submission / MTA (adjust ports you use)
sudo ufw allow 25/tcp
sudo ufw allow 587/tcp
# HTTP API if exposed
sudo ufw allow 8000/tcp
```

### DNS (required for receive + deliverability)

On your domain registrar / DNS host:

1. **A record**: `mail.yourdomain.com` → VPS public IP  
2. **MX record**: `@` (or subdomain) → `mail.yourdomain.com` (priority 10)  
3. **SPF** (TXT): `v=spf1 a mx ip4:YOUR_VPS_IP -all` (tune for your setup)  
4. **DKIM** — sign mail (this app does not generate DKIM keys; add via OpenDKIM/Rspamd or DNS if you extend the stack)  
5. **DMARC** (TXT): `v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com`  
6. **PTR (reverse DNS)** at your VPS provider: IP → `mail.yourdomain.com`

Without SPF/PTR/DKIM, many providers (Gmail, Outlook) will **reject or spam-folder** your mail.

### Outbound modes

| Mode | Config | When to use |
|------|--------|-------------|
| **direct** (default) | `OUTBOUND_MODE=direct` | Your VPS can use **outbound TCP 25** |
| **relay** | `OUTBOUND_MODE=relay` + `OUTBOUND_SMTP_*` | **Your** second SMTP host (still no public SaaS required) |

---

## 3. Render.com (optional)

Use Render mainly for the **HTTP API** and **persistent disk** (`render.yaml`).

**Limits on Render:**

- Health check: `GET /health` on `$PORT` — supported.
- **Inbound SMTP from the internet** on port 25/587 — **not** exposed like a normal MTA.
- **Outbound `direct` (port 25)** — usually **blocked**; sending to arbitrary addresses may fail.

For Render:

**Build must use Python 3.11**, not 3.14. If `pydantic-core` / `maturin` / Rust errors appear, Render picked the wrong Python: add `runtime.txt` and `.python-version` (both in this repo), set **`PYTHON_VERSION`** = `3.11.9` in the service environment, then **Clear build cache & deploy** again.

1. Push repo to Git; create **Blueprint** from `render.yaml` or a **Web Service** with:
   - **Build**: `pip install -r requirements.txt`
   - **Start**: `python -m smtp_server.main`
   - **Health check path**: `/health`
2. Set env vars in dashboard: `MAIL_DOMAIN`, `OUTBOUND_FROM_EMAIL`, `API_KEY`, `SMTP_AUTH_*`, disk path `DATA_DIR=/var/data`.
3. Prefer **your VPS** for full SMTP; use Render as API + storage if needed.

```bash
git init
git add .
git commit -m "SMTP mail server"
# push to GitHub/GitLab and connect in Render
```

---

## 4. HTTP API reference

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Liveness (Render) |
| GET | `/messages` | Optional `API_KEY` | List inbox metadata |
| GET | `/messages/{id}` | Optional `API_KEY` | Message metadata + raw base64 |
| POST | `/send` | Optional `API_KEY` | Send JSON email |

**Send JSON body:**

```json
{
  "to": ["user@example.com"],
  "subject": "Subject",
  "body_text": "Plain text body",
  "body_html": "<p>Optional HTML</p>",
  "from_email": "optional@yourdomain.com"
}
```

---

## 5. Project layout

```
smtp_server/
  main.py              # Entry point: SMTP + HTTP
  inbound_handler.py   # Receive SMTP
  inbound_auth.py      # Optional PLAIN AUTH
  mail_store.py        # Inbox on disk
  mail_sender.py       # Direct MX or relay send
  api.py               # FastAPI routes
  config.py            # Environment settings
data/                  # Created at runtime (gitignored)
.env                   # Your secrets (gitignored)
```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| Server exits on start (Windows) | Was `0.0.0.0` probe bug | Fixed via `BindController`; update code |
| `Connection refused` on SMTP | Server not running / wrong port | Check `SMTP_PORT`, firewall |
| Send fails on Render with `direct` | Outbound 25 blocked | Use VPS or `OUTBOUND_MODE=relay` to **your** host |
| Gmail rejects mail | No SPF/DKIM/PTR | Fix DNS and reverse DNS |
| 401 on API | `API_KEY` set | Send `X-API-Key` header |
| 530 on MAIL | AUTH required | `AUTH PLAIN` before MAIL, or disable auth only in dev |

---

## 7. Security checklist

- Set `SMTP_AUTH_USER` / `SMTP_AUTH_PASSWORD` on any internet-facing host.
- Set `API_KEY` for HTTP endpoints.
- Do not commit `.env`.
- Restrict firewall to needed ports only.
- Keep TLS termination in front of HTTP if public (reverse proxy).

---

## Quick command recap

```powershell
cd D:\Public\Local\temp_python
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m smtp_server.main
```
