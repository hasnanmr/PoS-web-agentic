from __future__ import annotations

from uuid import UUID

import pytest

from app.core.actor import ActorContext, ActorType, ReasonRequiredError

T = UUID("00000000-0000-0000-0000-00000000000a")
U = UUID("00000000-0000-0000-0000-0000000000f1")
D = UUID("00000000-0000-0000-0000-000000000201")
OUT = UUID("00000000-0000-0000-0000-0000000000a1")


def test_user_context_sets_session_values() -> None:
    ctx = ActorContext.for_user(T, U)
    s = ctx.session_settings()
    assert s["app.tenant_id"] == str(T)
    assert s["app.user_id"] == str(U)
    assert s["app.actor"] == "user"
    assert s["app.device_outlet_id"] == ""
    assert ctx.actor_id == U


def test_system_and_agent_have_no_actor_id() -> None:
    assert ActorContext.for_system(T).actor_id is None
    assert ActorContext.for_agent(T).actor_type is ActorType.AGENT
    assert ActorContext.for_system(None).session_settings()["app.tenant_id"] == ""


def test_device_context_is_scoped_to_one_outlet() -> None:
    ctx = ActorContext.for_device(T, D, OUT)
    assert ctx.actor_id == D
    assert ctx.session_settings()["app.device_outlet_id"] == str(OUT)


def test_invalid_combinations_are_refused() -> None:
    with pytest.raises(ValueError, match="user_id"):
        ActorContext(ActorType.USER, T)
    with pytest.raises(ValueError, match="device"):
        ActorContext(ActorType.DEVICE, T, device_id=D)
    with pytest.raises(ValueError, match="no user_id"):
        ActorContext(ActorType.SYSTEM, T, user_id=U)


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_blank_reason_is_refused(reason: str | None) -> None:
    with pytest.raises(ReasonRequiredError):
        ActorContext.for_user(T, U).with_reason(reason)


def test_reason_is_trimmed_and_context_is_immutable() -> None:
    base = ActorContext.for_user(T, U)
    with_reason = base.with_reason("  salah input  ")
    assert with_reason.reason == "salah input"
    assert base.reason is None
    assert with_reason.correlation_id == base.correlation_id
