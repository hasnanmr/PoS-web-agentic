"""Entrypoint for the WhatsApp worker process (separate from the API process).

Run locally:  uv run python -m app.worker.main

Consumes `wa.inbound.q` (conversation flows, T-046 to T-050) and `wa.outbound.q` (Cloud API
sender, T-047). Refuses to start without DATABASE_URL; without RABBITMQ_URL or
WHATSAPP_ACCESS_TOKEN it stays on standby (consumes nothing) until restarted with them.
Declares the RabbitMQ topology on start (T-110). Stops cleanly on SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app import db
from app.config import ConfigError, Settings, get_settings, worker_problems
from app.logging import configure_logging
from app.messaging.amqp import AmqpBroker
from app.messaging.topology import WA_INBOUND, WA_OUTBOUND
from app.whatsapp.graph import HttpGraphClient
from app.worker.inbound import InboundHandler
from app.worker.outbound import OutboundHandler

logger = logging.getLogger("app.worker")


async def run(settings: Settings, stop: asyncio.Event) -> None:
    assert settings.database_url is not None  # noqa: S101 - checked by worker_problems
    assert settings.rabbitmq_url is not None  # noqa: S101
    assert settings.whatsapp_access_token is not None  # noqa: S101
    pool = db.create_pool(
        str(settings.database_url),
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
    )
    broker = AmqpBroker(str(settings.rabbitmq_url))
    graph = HttpGraphClient(
        str(settings.whatsapp_graph_url),
        settings.whatsapp_graph_version,
        settings.whatsapp_access_token.get_secret_value(),
    )
    await pool.open(wait=True)
    try:
        await broker.connect()
        await broker.consume(WA_INBOUND, InboundHandler(pool, broker))
        await broker.consume(WA_OUTBOUND, OutboundHandler(pool, graph))
        logger.info("whatsapp worker running")
        await stop.wait()
    finally:
        await broker.close()
        await pool.close()
        logger.info("whatsapp worker stopped")


def main() -> int:
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    missing = worker_problems(settings)
    if "DATABASE_URL" in missing:
        print(f"WhatsApp worker requires these variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    configure_logging(settings.log_level, service="whatsapp-worker", app_env=settings.app_env)

    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        if missing:
            # Deployed before RabbitMQ or the Meta app is set up: idle instead of
            # crash-looping. Railway redeploys the service when its variables change.
            logger.warning(
                "whatsapp worker on standby: %s not set",
                ", ".join(missing),
                extra={"missing": missing},
            )
            await stop.wait()
            return
        await run(settings, stop)

    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    sys.exit(main())
