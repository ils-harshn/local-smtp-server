"""Optional SMTP AUTH for the inbound listener."""

import logging

from aiosmtpd.smtp import AuthResult, LoginPassword

logger = logging.getLogger(__name__)


class StaticAuthenticator:
    """Validates a single username/password if configured."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password

    def __call__(
        self,
        server,
        session,
        envelope,
        mechanism: str,
        login_data: LoginPassword | None,
    ) -> AuthResult:
        if login_data is None:
            return AuthResult(success=False, handled=False)

        try:
            username = login_data.login.decode("utf-8", errors="replace")
            password = login_data.password.decode("utf-8", errors="replace")
        except AttributeError:
            username = str(login_data.login)
            password = str(login_data.password)

        if username == self.username and password == self.password:
            return AuthResult(success=True, handled=True, auth_data=login_data)

        logger.warning("SMTP AUTH failed for user=%s", username)
        return AuthResult(success=False, handled=True, message="535 Authentication failed")
