import base64
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from smtp_server.config import get_settings
from smtp_server.mail_sender import MailSender
from smtp_server.mail_store import MailStore


class SendMailRequest(BaseModel):
    to: list[EmailStr] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=998)
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    from_email: EmailStr | None = None


def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Query()] = None,
) -> None:
    settings = get_settings()
    if not settings.api_key:
        return
    token = x_api_key or api_key
    if token != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def create_app(store: MailStore) -> FastAPI:
    settings = get_settings()
    sender = MailSender(settings)
    app = FastAPI(title="SMTP Mail Server", version="1.0.0")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "smtp_listen": f"{settings.smtp_host}:{settings.smtp_port}",
            "outbound_mode": settings.outbound_mode,
        }

    @app.get("/messages", dependencies=[Depends(verify_api_key)])
    async def list_messages(limit: int = Query(default=50, ge=1, le=200)):
        return {"messages": store.list_messages(limit=limit)}

    @app.get("/messages/{message_id}", dependencies=[Depends(verify_api_key)])
    async def get_message(message_id: str):
        found = store.get_message(message_id)
        if not found:
            raise HTTPException(status_code=404, detail="Message not found")
        record, raw = found
        return {
            "message": record.to_dict(),
            "raw_base64": base64.b64encode(raw).decode("ascii"),
        }

    @app.post("/send", dependencies=[Depends(verify_api_key)])
    async def send_mail(body: SendMailRequest):
        try:
            await sender.send(
                to_emails=[str(e) for e in body.to],
                subject=body.subject,
                body_text=body.body_text,
                body_html=body.body_html,
                from_email=str(body.from_email) if body.from_email else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc
        return {"status": "sent", "to": body.to}

    return app
