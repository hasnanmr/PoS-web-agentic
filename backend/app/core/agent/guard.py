"""Scope and limits of one agent turn, enforced in code (T-086, T-091; PRD FR6.6, AC6.9).

`AgentGuard` is a LangChain agent middleware around every model call and tool call:

* the model only ever sees our tools (Deep Agents' built-in filesystem, `task`, and any other
  tool are filtered out of the request), and a call to any other tool is refused without
  running it;
* at most `MAX_DATA_CALLS` data-tool calls and `MAX_MODEL_CALLS` model calls per customer
  message; the next one stops the turn (`AgentLimitReached`) and the chat falls back to buttons;
* every tool call is recorded as `(tool, outcome, result size, duration)` — never the
  arguments, the result, or the customer's text.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.agent.tools import DATA_TOOLS, MAX_DATA_CALLS, REPLY_TOOLS

MAX_MODEL_CALLS = 8


class AgentLimitReached(Exception):  # noqa: N818 - a stop signal, not a bug
    def __init__(self, what: str) -> None:
        super().__init__(f"agent limit reached: {what}")
        self.what = what


@dataclass
class ToolCallLog:
    tool: str
    outcome: str  # ok | error | refused | limit
    result_bytes: int = 0
    duration_ms: int = 0


@dataclass
class TurnBudget:
    allowed: frozenset[str]
    data_calls: int = 0
    model_calls: int = 0
    log: list[ToolCallLog] = field(default_factory=list)


def _name(tool: Any) -> str:
    return str(tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", ""))


class AgentGuard(AgentMiddleware):  # type: ignore[type-arg]
    def __init__(self, budget: TurnBudget) -> None:
        super().__init__()
        self.budget = budget

    @property
    def name(self) -> str:
        return "AgentGuard"

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        self.budget.model_calls += 1
        if self.budget.model_calls > MAX_MODEL_CALLS:
            raise AgentLimitReached("model_calls")
        tools = [t for t in request.tools if _name(t) in self.budget.allowed]
        return await handler(request.override(tools=tools))

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        name = str(request.tool_call.get("name", ""))
        call_id = str(request.tool_call.get("id", ""))
        tool = name if name.isascii() and name.replace("_", "").isalpha() else "unknown"
        if name not in self.budget.allowed:
            self.budget.log.append(ToolCallLog(tool=tool[:40].lower(), outcome="refused"))
            return ToolMessage(
                content="Tool ini tidak tersedia.", tool_call_id=call_id, status="error"
            )
        if name in DATA_TOOLS:
            if self.budget.data_calls >= MAX_DATA_CALLS:
                self.budget.log.append(ToolCallLog(tool=name, outcome="limit"))
                raise AgentLimitReached("data_calls")
            self.budget.data_calls += 1
        started = time.monotonic()
        try:
            result = await handler(request)
        except Exception:
            self.budget.log.append(
                ToolCallLog(tool=name, outcome="error", duration_ms=_ms(started))
            )
            raise
        size = len(str(result.content).encode()) if isinstance(result, ToolMessage) else 0
        outcome = "error" if isinstance(result, ToolMessage) and result.status == "error" else "ok"
        self.budget.log.append(
            ToolCallLog(tool=name, outcome=outcome, result_bytes=size, duration_ms=_ms(started))
        )
        return result


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


ALL_TOOLS = DATA_TOOLS | REPLY_TOOLS
