"""Agent tracing with Langfuse (opt-in) — one trace per customer message.

Off unless `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set (`Settings.langfuse_configured`).
Follows the Langfuse best practices (docs: observability/best-practices, LangChain integration):

* one trace per agent turn, grouped by `session_id` (a short hash of the chat session, never
  the id the phone holds); trace name `web-chat-reply`, version = the prompt version, tag
  `context:*`, environment = APP_ENV, release = the deployed commit when Railway provides it;
* a root span `web-chat-reply` (one turn) whose input is only the customer's message and
  whose output is the agent's reply (drafts, cards, and the tool-call summary go to its
  metadata), with the LangChain `CallbackHandler` nested under it: the Deep Agents run as the
  `agent`, one `generation` named `generate-reply` per model call (model name and token usage;
  the model streams with usage on), and one `tool` per tool call; Deep Agents' middleware hook
  spans (`*.before_agent`, `*.after_agent`, …) are dropped at export as framework noise;
* a categorical `turn_outcome` score per trace (answered / cards / order_draft /
  booking_draft / out_of_scope / agent_limit / agent_timeout / agent_unavailable), so failed
  and refused turns are one filter away;
* phone numbers and email addresses masked in every exported span attribute
  (`mask_otel_spans`, the recommended export-stage hook): customers type them in free text.

Data residency (NFR1): customer text leaves our service. Point LANGFUSE_HOST at a self-hosted
Langfuse or a region the T-108 decision allows; Langfuse Cloud is outside Indonesia.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)

TRACE_NAME = "web-chat-reply"
DEFAULT_HOST = "https://cloud.langfuse.com"
_PHONE = re.compile(r"(?<!\w)(?:\+?62[\s.\-]?|0)8[\d\s.\-]{7,14}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MIDDLEWARE_HOOK = re.compile(r"\.(before|after)_(agent|model)$|\.wrap_(model|tool)_call$")
_ENABLED = False


# Masking ---------------------------------------------------------------------------------------


def mask_text(value: str) -> str:
    return _EMAIL.sub("[email]", _PHONE.sub("[no HP]", value))


def mask(*, data: Any, **_: Any) -> Any:
    """Redact phone numbers and emails anywhere in a JSON-like value."""
    if isinstance(data, str):
        return mask_text(data)
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, list | tuple):
        return [mask(data=v) for v in data]
    return data


def mask_otel_spans(*, params: Any) -> Any:
    """Export-stage masking for every span attribute (input, output, metadata, framework
    attributes). JSON-encoded attributes are plain strings here, so the same regex covers them."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        changed: dict[str, Any] = {}
        for key, value in (span.attributes or {}).items():
            if isinstance(value, str):
                masked = mask_text(value)
                if masked != value:
                    changed[key] = masked
            elif (
                isinstance(value, list | tuple) and value and all(isinstance(v, str) for v in value)
            ):
                masked_seq = [mask_text(v) for v in value]
                if masked_seq != list(value):
                    changed[key] = masked_seq
        if changed:
            patches[identifier] = OtelSpanPatch(set_attributes=changed)
    return MaskOtelSpansResult(span_patches=patches)


def should_export_span(span: Any) -> bool:
    """Langfuse's default export filter, minus Deep Agents' middleware hook spans (leaves with
    no information for a reviewer)."""
    from langfuse import is_default_export_span

    return is_default_export_span(span) and not _MIDDLEWARE_HOOK.search(span.name or "")


# Client ----------------------------------------------------------------------------------------


def configure(settings: Any, **client_options: Any) -> bool:
    """Create the process-wide Langfuse client when both keys are set. Returns whether tracing
    is on. Never raises: a bad Langfuse setup must not take the chat down. `client_options`
    are for tests (e.g. an in-memory `span_exporter`)."""
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
            release=os.environ.get("RAILWAY_GIT_COMMIT_SHA") or None,
            mask_otel_spans=mask_otel_spans,
            should_export_span=should_export_span,
            **client_options,
        )
        _ENABLED = True
    except Exception:
        log.exception("langfuse tracing could not start; agent runs without traces")
        _ENABLED = False
    return _ENABLED


def enabled() -> bool:
    return _ENABLED


# One agent turn --------------------------------------------------------------------------------


class TurnTrace:
    """Handle of one turn's trace: LangChain callbacks to pass to the agent, and `finish`."""

    def __init__(self, root: Any = None) -> None:
        self._root = root
        self.callbacks: list[Any] = []
        if root is not None:
            from langfuse.langchain import CallbackHandler

            self.callbacks = [CallbackHandler()]  # nests under the current (root) observation

    @property
    def trace_id(self) -> str | None:
        return getattr(self._root, "trace_id", None)

    def finish(
        self, *, reply: str, outcome: str, failure: str | None, metadata: dict[str, Any]
    ) -> None:
        if self._root is None:
            return
        try:
            level = (
                "ERROR" if failure == "agent_unavailable" else "WARNING" if failure else "DEFAULT"
            )
            self._root.update(
                output={"role": "assistant", "content": reply} if failure is None else None,
                metadata={**metadata, "outcome": outcome},
                level=level,
                status_message=failure,
            )
            from langfuse import get_client

            get_client().create_score(
                trace_id=self._root.trace_id,
                name="turn_outcome",
                value=outcome,
                data_type="CATEGORICAL",
            )
        except Exception:
            log.exception("langfuse: could not finish the turn trace")


@contextmanager
def turn_trace(
    *,
    session: str,
    text: str,
    outlet_id: str,
    context: str,
    prompt_version: str,
    trace_id: str | None = None,
) -> Iterator[TurnTrace]:
    """Open the turn's root span and the trace attributes for everything run
    inside the block. Keep the whole agent run inside it, in one task (OpenTelemetry context
    must not cross an async generator's `yield`)."""
    if not _ENABLED:
        yield TurnTrace()
        return
    try:
        from langfuse import get_client, propagate_attributes

        root_cm = get_client().start_as_current_observation(
            trace_context={"trace_id": trace_id} if trace_id else None,
            name=TRACE_NAME,
            as_type="span",  # the turn; the Deep Agents run below it is the `agent` node
            input=[{"role": "user", "content": text}],
            version=prompt_version,
            metadata={"outlet_id": outlet_id, "context": context},
        )
        attrs_cm = propagate_attributes(
            session_id=f"chat-{session[:16]}",
            trace_name=TRACE_NAME,
            version=prompt_version,
            tags=[f"context:{context}"],
            metadata={"outlet_id": outlet_id, "prompt_version": prompt_version},
        )
    except Exception:
        log.exception("langfuse: could not open the turn trace")
        yield TurnTrace()
        return
    with root_cm as root, attrs_cm:
        yield TurnTrace(root)


def outcome_of(failure: str | None, turn: Any) -> str:
    if failure:
        return failure
    if turn.out_of_scope:
        return "out_of_scope"
    if turn.order_draft:
        return "order_draft"
    if turn.booking_draft:
        return "booking_draft"
    if turn.cards:
        return "cards"
    return "answered"


def score_session(session_id: str, name: str, value: float, comment: str | None = None) -> None:
    """Score a chat session's traces (the evaluation set, T-092, scores each case this way)."""
    if not _ENABLED:
        return
    from langfuse import get_client

    get_client().create_score(
        session_id=session_id, name=name, value=value, data_type="NUMERIC", comment=comment
    )


def flush() -> None:
    """Send what is buffered (server shutdown, end of the eval run)."""
    if not _ENABLED:
        return
    from langfuse import get_client

    try:
        get_client().flush()
    except Exception:
        log.exception("langfuse flush failed")
