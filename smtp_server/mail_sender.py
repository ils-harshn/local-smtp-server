import logging
from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib
import dns.resolver

from smtp_server.config import Settings

logger = logging.getLogger(__name__)


class MailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _build_message(
        self,
        from_email: str,
        to_emails: list[str],
        subject: str,
        body_text: str,
        body_html: str | None,
    ) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.settings.mail_domain)
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        return msg

    async def send(
        self,
        to_emails: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_email: str | None = None,
    ) -> None:
        sender = from_email or self.settings.outbound_from_email
        if not sender:
            raise ValueError("from_email is required (set OUTBOUND_FROM_EMAIL or pass from_email)")

        message = self._build_message(sender, to_emails, subject, body_text, body_html)

        if self.settings.outbound_mode == "relay":
            await self._send_via_relay(message, sender, to_emails)
        else:
            await self._send_direct(message, to_emails)

    async def _send_via_relay(
        self,
        message: EmailMessage,
        sender: str,
        to_emails: list[str],
    ) -> None:
        host = self.settings.outbound_smtp_host
        if not host:
            raise ValueError("OUTBOUND_SMTP_HOST is required when OUTBOUND_MODE=relay")

        port = self.settings.outbound_smtp_port
        use_tls = self.settings.outbound_smtp_use_tls
        username = self.settings.outbound_smtp_user
        password = self.settings.outbound_smtp_password

        client = aiosmtplib.SMTP(
            hostname=host,
            port=port,
            start_tls=use_tls and port != 465,
            use_tls=use_tls and port == 465,
            timeout=60,
        )

        await client.connect()
        try:
            if username and password:
                await client.login(username, password)
            elif username or password:
                raise ValueError(
                    "OUTBOUND_SMTP_USER and OUTBOUND_SMTP_PASSWORD must both be set for relay auth"
                )
            await client.sendmail(sender, to_emails, message.as_bytes())
        finally:
            await client.quit()

        logger.info("Sent via relay %s:%s to %s", host, port, to_emails)

    async def _send_direct(self, message: EmailMessage, to_emails: list[str]) -> None:
        """Deliver to each recipient's MX host (port 25). Works on VPS; often blocked on PaaS."""
        for recipient in to_emails:
            domain = recipient.split("@", 1)[-1]
            mx_hosts = self._lookup_mx(domain)
            if not mx_hosts:
                raise ValueError(f"No MX records for domain {domain}")

            last_error: Exception | None = None
            delivered = False
            for preference, mx_host in mx_hosts:
                try:
                    await self._deliver_to_mx(mx_host, message, recipient)
                    delivered = True
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("MX %s (pri=%s) failed: %s", mx_host, preference, exc)

            if not delivered:
                raise RuntimeError(f"Failed to deliver to {recipient}") from last_error

    def _lookup_mx(self, domain: str) -> list[tuple[int, str]]:
        try:
            answers = dns.resolver.resolve(domain, "MX")
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers) as exc:
            raise ValueError(f"MX lookup failed for {domain}") from exc

        hosts: list[tuple[int, str]] = []
        for rdata in answers:
            host = str(rdata.exchange).rstrip(".")
            hosts.append((int(rdata.preference), host))
        hosts.sort(key=lambda item: item[0])
        return hosts

    async def _deliver_to_mx(self, mx_host: str, message: EmailMessage, recipient: str) -> None:
        sender = message["From"] or self.settings.outbound_from_email
        client = aiosmtplib.SMTP(hostname=mx_host, port=25, timeout=90)
        await client.connect()
        try:
            await client.sendmail(sender, [recipient], message.as_bytes())
        finally:
            await client.quit()
        logger.info("Direct delivery to %s via %s", recipient, mx_host)
