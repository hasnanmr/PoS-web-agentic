"""Production entrypoint for the API process: validate config first, then serve.

uv run python -m app.serve
"""

from __future__ import annotations

import sys

import uvicorn

from app.config import ConfigError, get_settings


def main() -> int:
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container must listen on all interfaces
        port=settings.port,
        log_config=None,  # logging is configured by create_app
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
