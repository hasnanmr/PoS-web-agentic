"""Agent tracing with Langfuse (opt-in) — one trace per customer message.

Off unless `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set (`Settings.langfuse_configured`).
When on, the LangChain callback sends the model calls, tool calls, and timings of each agent
turn to `LANGFUSE_HOST`. What leaves our service:

* the customer's text and the agent's reply, with phone numbers and email addresses masked
  (`mask`) before export — customers type them in free text even though the chat never asks;
* tool results (menu, prices, free times): outlet data, no customer data — the agent has no
  tool that reads customers, orders, or bookings (FR6.6);
* a short hash of the chat session (never the session id the phone holds), the outlet id, the
  prompt version, and the chat context as tags.

Data residency (NFR1): the host decides where these traces live. Use a self-hosted Langfuse
or a region the T-108 decision allows; Langfuse Cloud is outside Indonesia.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

_PHONE = re.compile(r"(?<!\w)(?:\+?62[\s.\-]?|0)8[\d\s.\-]{7,14}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ENABLED = False
DEFAULT_HOST = "https://cloud.langfuse.com"


def mask(*, data: Any, **_: Any) -> Any:
    """Langfuse mask function: redact phone numbers and emails anywhere in the payload."""
    if isinstance(data, str):
        return _EMAIL.sub("[email]", _PHONE.sub("[no HP]", data))
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [mask(data=v) for v in data]
    return data


def configure(settings: Any) -> bool:
    """Create the process-wide Langfuse client when both keys are set. Returns whether tracing
    is on. Never raises: a bad Langfuse setup must not take the chat down."""
    global _ENABLED
    if not settings.langfuse_configured:
        _ENABLED = False
        return False
    try:
        from langfuse import Langfuse

        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=str(settings.langfuse_host or DEFAULT_HOST),
            environment=settings.app_env,
            mask=mask,
        )
        _ENABLED = True
    except Exception:
        log.exception("langfuse tracing could not start; agent runs without traces")
        _ENABLED = False
    return _ENABLED


def enabled() -> bool:
    return _ENABLED


def new_trace_id() -> str | None:
    if not _ENABLED:
        return None
    from langfuse import Langfuse

    return Langfuse.create_trace_id()


def run_config(
    *, trace_id: str | None, session: str, outlet_id: str, context: str, prompt_version: str
) -> dict[str, Any]:
    """LangChain run config for one agent turn: the Langfuse callback plus its trace attributes.
    Empty when tracing is off."""
    if not _ENABLED or trace_id is None:
        return {}
    from langfuse.langchain import CallbackHandler

    return {
        "callbacks": [CallbackHandler(trace_context={"trace_id": trace_id})],
        "run_name": "web-chat-agent",
        "metadata": {
            # A short hash of the session hash: groups one phone's turns, never the raw id.
            "langfuse_session_id": f"chat-{session[:16]}",
            "langfuse_tags": [f"context:{context}", f"prompt:{prompt_version}"],
            "outlet_id": outlet_id,
            "prompt_version": prompt_version,
        },
    }


def score_session(session_id: str, name: str, value: float, comment: str | None = None) -> None:
    """Score a chat session's traces (the evaluation set, T-092, scores each case this way)."""
    if not _ENABLED:
        return
    from langfuse import get_client

    get_client().create_score(session_id=session_id, name=name, value=value, comment=comment)


def flush() -> None:
    if not _ENABLED:
        return
    from langfuse import get_client

    try:
        get_client().flush()
    except Exception:
        log.exception("langfuse flush failed")
