import asyncio
import logging
import signal
import sys

import uvicorn

from smtp_server.api import create_app
from smtp_server.config import get_settings
from smtp_server.inbound_handler import build_smtp_controller
from smtp_server.mail_store import MailStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def run_http(app, host: str, port: int) -> None:
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    store = MailStore(settings.data_dir)
    smtp_controller = build_smtp_controller(store)
    app = create_app(store)

    smtp_controller.start()
    logger.info(
        "Inbound SMTP listening on %s:%s (AUTH %s)",
        settings.smtp_host,
        settings.smtp_port,
        "required" if settings.smtp_auth_user else "optional/disabled",
    )
    logger.info("HTTP API listening on %s:%s", settings.http_host, settings.port)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(*_args):
        logger.info("Shutting down...")
        smtp_controller.stop()
        for task in asyncio.all_tasks(loop):
            task.cancel()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, shutdown)
        loop.add_signal_handler(signal.SIGINT, shutdown)

    try:
        loop.run_until_complete(run_http(app, settings.http_host, settings.port))
    except KeyboardInterrupt:
        shutdown()
    finally:
        smtp_controller.stop()
        loop.close()


if __name__ == "__main__":
    main()
