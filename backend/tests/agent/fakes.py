"""A scripted chat model for agent tests: replays AI messages (text and/or tool calls) and
records what each call was offered, so tests can check which tools the model saw."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


def call(name: str, args: dict[str, Any] | None = None, n: int = 0) -> dict[str, Any]:
    return {"name": name, "args": args or {}, "id": f"call_{name}_{n}", "type": "tool_call"}


class ScriptedModel(BaseChatModel):
    script: list[AIMessage] = Field(default_factory=list)
    model_name: str = "scripted"
    seen_tools: list[list[str]] = Field(default_factory=list)
    seen_messages: list[list[BaseMessage]] = Field(default_factory=list)
    bound: list[str] = Field(default_factory=list)
    delay: float = 0.0
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Any:
        names = [t.get("name") if isinstance(t, dict) else getattr(t, "name", None) for t in tools]
        self.bound = [n for n in names if n]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.fail:
            raise RuntimeError("provider down")
        self.seen_tools.append(list(self.bound))
        self.seen_messages.append(list(messages))
        message = self.script.pop(0) if self.script else AIMessage("…")
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.delay:
            await asyncio.sleep(self.delay)
        return self._generate(messages, stop, None, **kwargs)
