"""Entrypoint for the WhatsApp worker process (separate from the API process).

Run locally:  uv run python -m app.worker.main

The worker will consume RabbitMQ queues for inbound/outbound WhatsApp messages in later
tasks. For now it only validates configuration and exits.
"""

from __future__ import annotations

import logging
import sys

from app.config import ConfigError, get_settings
from app.logging import configure_logging

logger = logging.getLogger("app.worker")


def main() -> int:
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    configure_logging(settings.log_level, service="whatsapp-worker", app_env=settings.app_env)
    logger.info(
        "whatsapp worker not implemented yet; exiting",
        extra={"rabbitmq_configured": bool(settings.rabbitmq_url)},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
