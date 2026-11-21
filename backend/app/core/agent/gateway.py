"""Web chat agent gateway (T-115, T-086, T-091; PRD FR6.2, FR6.3, FR6.6) — C9 AI, C14, C15.

One customer message = one turn:

1. load this phone's recent conversation (encrypted in `chat_sessions.agent_history`);
2. run a LangChain Deep Agents agent (`create_deep_agent`, inside this FastAPI process) with
   only our outlet-scoped tools, under `AgentGuard` (≤ 4 data-tool calls, ≤ 8 model calls) and
   a 30-second limit;
3. stream the reply text as it is written (`delta` events), then one `final` event with the
   reply and what the reply tools staged (cards, an order or booking draft, quick replies,
   the out-of-scope flag) — or one `error` event, and the chat falls back to its buttons;
4. save the conversation and the tool-call log (no personal data in the log).

Deep Agents configuration (T-086): no general-purpose subagent, no planning tool, the
built-in filesystem tools hidden from the model and refused if called (they would only touch
the in-memory state backend anyway), and no LangSmith tracing unless the environment turns it
on explicitly (customer messages stay in our region, NFR1). Nothing here writes an order or a
booking: drafts are created by the customer's own tap through the button-flow endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from deepagents import create_deep_agent
from deepagents.profiles import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage

from app import db
from app.core import crypto, web_chat
from app.core.actor import ActorContext
from app.core.agent import tracing
from app.core.agent.guard import AgentGuard, AgentLimitReached, TurnBudget
from app.core.agent.prompt import PROMPT_VERSION, Context, system_prompt
from app.core.agent.tools import TurnResult, bind_runner, build_tools

log = logging.getLogger(__name__)

TURN_SECONDS = 30.0
HISTORY_TURNS = 6  # customer + assistant pairs kept for context (FR6.2)
HISTORY_TEXT_CHARS = 600
HISTORY_CONTEXT = "chat_sessions.agent_history"
# Deep Agents' built-in tools: never offered to the model (AgentGuard also refuses them).
BUILTIN_TOOLS = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "write_todos",
        "task",
    }
)

ModelFactory = Callable[[], BaseChatModel]

# LangSmith tracing would send customer messages abroad: off unless explicitly enabled.
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


@dataclass(frozen=True)
class AgentEvent:
    event: str  # delta | final | error
    data: dict[str, Any]

    def sse(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"), default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"


def openai_model_factory(settings: Any) -> ModelFactory | None:
    """The model behind the agent: any OpenAI-compatible chat completions API with tool
    calling (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`). None while not configured."""
    if not settings.agent_configured:
        return None
    from langchain_openai import ChatOpenAI

    key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else "not-needed"

    def make() -> BaseChatModel:
        return ChatOpenAI(
            model=settings.model_name,
            base_url=str(settings.openai_base_url),
            api_key=key,
            # No temperature: Claude 4.7+ through Anthropic's OpenAI-compatible endpoint
            # rejects any value below 1 (400), and the provider default is fine for tool calls.
            timeout=TURN_SECONDS,
            max_retries=1,
            streaming=True,
        )

    return make


_PROFILED: set[str] = set()


def _profile_key(model: BaseChatModel) -> str:
    """The harness-profile key Deep Agents looks up for this model (`provider:model`)."""
    from deepagents._models import get_model_identifier, get_model_provider

    return f"{get_model_provider(model)}:{get_model_identifier(model)}"


def _register_profile(model: BaseChatModel) -> None:
    """Deep Agents harness profile for our model: no general-purpose subagent and none of the
    built-in tools (T-086). Registered once per `provider:model` key."""
    key = _profile_key(model)
    if key in _PROFILED:
        return
    register_harness_profile(
        key,
        HarnessProfile(
            excluded_tools=BUILTIN_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    _PROFILED.add(key)


def build_agent(model: BaseChatModel, tools: list[Any], prompt: str, budget: TurnBudget) -> Any:
    _register_profile(model)
    return create_deep_agent(
        model,
        tools,
        system_prompt=prompt,
        middleware=[AgentGuard(budget)],
        subagents=[],
    )


# History ---------------------------------------------------------------------------------------


async def load_history(conn: Any, scope: web_chat.ChatScope, session: str) -> list[dict[str, str]]:
    cur = await conn.execute(
        "select agent_history from app.chat_sessions where outlet_id = %s"
        " and table_id is not distinct from %s and session_key_hash = %s"
        " and last_activity_at >= %s",
        (scope.outlet_id, scope.table_id, session, datetime.now(UTC) - web_chat.CART_IDLE),
    )
    row = await cur.fetchone()
    if row is None or row[0] is None:
        return []
    try:
        history = json.loads(crypto.decrypt(row[0], HISTORY_CONTEXT) or "[]")
    except (ValueError, TypeError):
        return []
    return [h for h in history if isinstance(h, dict) and h.get("role") in ("user", "assistant")]


async def save_turn(
    conn: Any,
    scope: web_chat.ChatScope,
    session: str,
    history: list[dict[str, str]],
    message_id: uuid.UUID,
    budget: TurnBudget,
) -> None:
    kept = history[-HISTORY_TURNS * 2 :]
    blob = crypto.encrypt(json.dumps(kept, ensure_ascii=False), HISTORY_CONTEXT)
    await conn.execute(
        """
        insert into app.chat_sessions
          (tenant_id, outlet_id, table_id, session_key_hash, agent_history)
        values (%s, %s, %s, %s, %s)
        on conflict (outlet_id, table_id, session_key_hash) do update
          set agent_history = excluded.agent_history, last_activity_at = now()
        """,
        (scope.tenant_id, scope.outlet_id, scope.table_id, session, blob),
    )
    for entry in budget.log:
        await conn.execute(
            "insert into app.agent_tool_calls (tenant_id, outlet_id, session_key_hash, message_id,"
            " prompt_version, tool, outcome, result_bytes, duration_ms)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                scope.tenant_id,
                scope.outlet_id,
                session,
                message_id,
                PROMPT_VERSION,
                entry.tool,
                entry.outcome,
                entry.result_bytes,
                entry.duration_ms,
            ),
        )


def _history_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
    return [
        HumanMessage(h["text"]) if h["role"] == "user" else AIMessage(h["text"])
        for h in history[-HISTORY_TURNS * 2 :]
    ]


def _assistant_memory(reply: str, turn: TurnResult) -> str:
    """What the next turn should remember of this reply: the text plus what was shown."""
    notes = []
    if turn.cards:
        notes.append("kartu: " + ", ".join(c["name"] for c in turn.cards))
    if turn.order_draft:
        notes.append(
            "ringkasan pesanan ditampilkan: "
            + ", ".join(f"{line['quantity']}x {line['name']}" for line in turn.order_draft["lines"])
        )
    if turn.booking_draft:
        notes.append(
            f"booking diusulkan: {turn.booking_draft['party_size']} orang"
            f" {turn.booking_draft['label']}"
        )
    if turn.quick_replies:
        notes.append("pilihan: " + " / ".join(turn.quick_replies))
    return (reply + (f" [{'; '.join(notes)}]" if notes else ""))[:HISTORY_TEXT_CHARS]


def _text(message: AIMessage | AIMessageChunk) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "")
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    )


# One turn --------------------------------------------------------------------------------------


async def run_turn(
    *,
    pool: Any,
    make_model: ModelFactory,
    scope: web_chat.ChatScope,
    session: str,
    text: str,
    context: Context,
    limit_seconds: float | None = None,
    trace_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """`trace_id`: the Langfuse trace of this turn (the evaluation set passes its own to score
    it); a new one when tracing is on and none is given."""
    message_id = uuid.uuid4()
    trace_id = trace_id or tracing.new_trace_id()
    trace_config = tracing.run_config(
        trace_id=trace_id,
        session=session,
        outlet_id=str(scope.outlet_id),
        context=context,
        prompt_version=PROMPT_VERSION,
    )
    correlation = message_id.hex
    ctx = ActorContext.for_agent(scope.tenant_id, correlation_id=correlation)
    async with db.transaction(pool, ctx) as conn:
        history = await load_history(conn, scope, session)

    turn = TurnResult()
    run = bind_runner(pool, scope, correlation)
    tools = build_tools(run, scope, turn)
    budget = TurnBudget(allowed=frozenset(t.name for t in tools))
    agent = build_agent(
        make_model(), tools, system_prompt(scope, context, datetime.now(UTC)), budget
    )
    messages = [*_history_messages(history), HumanMessage(text)]

    reply = ""
    failure: str | None = None
    try:
        async with asyncio.timeout(limit_seconds or TURN_SECONDS):
            async for mode, chunk in agent.astream(
                {"messages": messages},
                stream_mode=["messages", "values"],
                config={"recursion_limit": 40, **trace_config},
            ):
                if mode == "messages":
                    message, meta = chunk
                    if (
                        isinstance(message, AIMessageChunk | AIMessage)
                        and meta.get("langgraph_node") == "model"
                    ):
                        delta = _text(message)
                        if delta:
                            yield AgentEvent("delta", {"text": delta})
                elif mode == "values":
                    last = chunk["messages"][-1] if chunk.get("messages") else None
                    if isinstance(last, AIMessage) and not last.tool_calls:
                        reply = _text(last).strip()
    except AgentLimitReached as exc:
        failure = "agent_limit"
        log.info("agent turn stopped", extra={"limit": exc.what, "outlet_id": str(scope.outlet_id)})
    except TimeoutError:
        failure = "agent_timeout"
        log.info("agent turn timed out", extra={"outlet_id": str(scope.outlet_id)})
    except Exception:  # the model provider failed: fall back to buttons, never a 500
        failure = "agent_unavailable"
        log.exception("agent turn failed", extra={"outlet_id": str(scope.outlet_id)})

    if failure is None and not reply:
        reply = _default_reply(turn)
    if failure is None:
        history = [
            *history,
            {"role": "user", "text": text[:HISTORY_TEXT_CHARS]},
            {"role": "assistant", "text": _assistant_memory(reply, turn)},
        ]
    async with db.transaction(pool, ctx) as conn:
        await save_turn(conn, scope, session, history, message_id, budget)

    if failure is not None:
        yield AgentEvent(
            "error", {"code": failure, "fallback": "cards" if context == "recommend" else "buttons"}
        )
        return
    yield AgentEvent(
        "final", {"reply_text": reply, **asdict(turn), "prompt_version": PROMPT_VERSION}
    )


def _default_reply(turn: TurnResult) -> str:
    if turn.order_draft:
        return "Ini ringkasan pesananmu. Cek dulu ya, harga & total dihitung sistem."
    if turn.booking_draft:
        return f"Siap, {turn.booking_draft['label']} masih ada. Lanjut isi nama & no HP ya."
    if turn.cards:
        return "Ini beberapa pilihan yang cocok buat kamu."
    if turn.out_of_scope:
        return "Maaf, aku cuma bisa bantu pesan, rekomendasi menu, dan reservasi di outlet ini."
    return "Maaf, aku belum paham. Coba tulis lagi, atau pakai tombol di bawah ya."
