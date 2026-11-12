# Python SMTP Server (Receive + Send) for Render

This project runs:

- **Inbound SMTP** (`aiosmtpd`) to receive and store messages as `.eml` files
- **Outbound sending** via SMTP relay (recommended on Render) or direct MX delivery (VPS/local)
- **HTTP API** (`FastAPI`) for health checks, listing mail, and sending mail — required for [Render](https://render.com) web services

## Render.com limitations (important)

| Feature | On Render | Notes |
|--------|-----------|--------|
| HTTP API + health | Yes | Uses `PORT` env var |
| Outbound send via relay | Yes | Set `OUTBOUND_MODE=relay` and provider credentials (SendGrid, Mailgun, etc.) |
| Inbound SMTP from the public internet | **Limited** | Render web services expose **HTTP only** on `$PORT`. SMTP listens on `SMTP_PORT` inside the container but is **not** reachable on port 25/587 from the internet unless you use a **Private Service** or TCP proxy on a paid plan. |
| Direct MX delivery (`OUTBOUND_MODE=direct`) | Usually **no** | Outbound port 25 is blocked on most PaaS hosts |

For production **receive**, point an MX record to a host that can accept SMTP (VPS, mail provider) or use inbound parse webhooks from your provider. This app still receives mail from any client that can reach `host:SMTP_PORT` (tests, private network, port-forward).

**Full setup:** see [setup.md](setup.md).

## Environment variables

Copy `.env.example` to `.env` and adjust.

## HTTP API

- `GET /health` — no auth (Render health check)
- `GET /messages` — list received mail (optional `API_KEY`)
- `GET /messages/{id}` — raw message (base64)
- `POST /send` — send email JSON body (optional `API_KEY`)

Example send:

```json
{
  "to": ["user@example.com"],
  "subject": "Hello",
  "body_text": "Plain text body"
}
```

Header: `X-API-Key: your-key` if `API_KEY` is set.

## Local SMTP test (receive)

Use any SMTP client targeting `localhost:2525` (or your `SMTP_PORT`). If `SMTP_AUTH_USER` / `SMTP_AUTH_PASSWORD` are set, authenticate with PLAIN.
