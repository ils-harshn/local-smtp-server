import logging

from aiosmtpd.controller import Controller

from smtp_server.config import get_settings
from smtp_server.inbound_auth import StaticAuthenticator
from smtp_server.mail_store import MailStore

logger = logging.getLogger(__name__)


class BindController(Controller):
    """
    aiosmtpd uses `hostname` for both bind address and post-start probe.
    On Windows, connecting to 0.0.0.0 fails — bind on smtp_bind_host, probe via 127.0.0.1.
    """

    def __init__(self, handler, *, bind_host: str, probe_host: str, **kwargs) -> None:
        self._bind_host = bind_host
        super().__init__(handler, hostname=probe_host, **kwargs)

    def _create_server(self):
        return self.loop.create_server(
            self._factory_invoker,
            host=self._bind_host,
            port=self.port,
            ssl=self.ssl_context,
        )


class ReceivingHandler:
    """Accepts inbound SMTP sessions and persists raw messages."""

    def __init__(self, store: MailStore, require_auth: bool) -> None:
        self.store = store
        self.require_auth = require_auth

    def _authenticated(self, session) -> bool:
        return bool(getattr(session, "authenticated", False))

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        if self.require_auth and not self._authenticated(session):
            return "530 Authentication required"
        envelope.mail_from = address
        return "250 OK"

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if self.require_auth and not self._authenticated(session):
            return "530 Authentication required"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        if self.require_auth and not self._authenticated(session):
            return "530 Authentication required"

        raw = envelope.content
        if raw is None:
            return "554 No message content"
        if not isinstance(raw, bytes):
            raw = raw.encode("utf-8", errors="replace")

        mail_from = envelope.mail_from or ""
        rcpt_tos = list(envelope.rcpt_tos or [])

        try:
            record = self.store.save(raw, mail_from, rcpt_tos)
            logger.info(
                "Received message id=%s from=%s to=%s",
                record.id,
                mail_from,
                rcpt_tos,
            )
        except Exception:
            logger.exception("Failed to store message")
            return "451 Temporary failure storing message"

        return "250 Message accepted for delivery"


def _probe_host(bind_host: str) -> str:
    if bind_host in ("0.0.0.0", "", "::"):
        return "127.0.0.1"
    return bind_host


def build_smtp_controller(store: MailStore) -> Controller:
    settings = get_settings()
    require_auth = bool(settings.smtp_auth_user and settings.smtp_auth_password)

    handler = ReceivingHandler(store, require_auth=require_auth)

    auth_required = False
    authenticator = None
    if require_auth:
        auth_required = True
        authenticator = StaticAuthenticator(
            settings.smtp_auth_user,
            settings.smtp_auth_password,
        )

    probe_host = _probe_host(settings.smtp_host)

    controller = BindController(
        handler,
        bind_host=settings.smtp_host,
        probe_host=probe_host,
        port=settings.smtp_port,
        server_hostname=settings.mail_domain,
        authenticator=authenticator,
        auth_require_tls=False,
        auth_required=auth_required,
        decode_data=False,
    )
    return controller
