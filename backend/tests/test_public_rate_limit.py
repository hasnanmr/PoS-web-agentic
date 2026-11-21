"""The public web chat's in-memory limiters stay bounded and cheap (#77)."""

from __future__ import annotations

import pytest

from app.api.errors import ApiError
from app.api.v1 import public_chat as pc


def test_blocks_after_the_limit_and_counts_per_key() -> None:
    for _ in range(3):
        pc.rate_limit("ip:1", 3)
    with pytest.raises(ApiError) as exc:
        pc.rate_limit("ip:1", 3)
    assert exc.value.status_code == 429
    pc.rate_limit("ip:2", 3)  # another client is unaffected


def test_many_live_keys_never_grow_past_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "_MAX_KEYS", 50)
    for i in range(500):  # a client rotating tokens / addresses, every key still "live"
        pc.rate_limit(f"token:{i}", 10)
    assert len(pc._hits) == 50
    assert "token:499" in pc._hits and "token:0" not in pc._hits


def test_recently_used_keys_survive_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "_MAX_KEYS", 3)
    for k in ("a", "b", "c"):
        pc.rate_limit(k, 10)
    pc.rate_limit("a", 10)  # "a" becomes the most recent
    pc.rate_limit("d", 10)  # evicts "b", the least recently used
    assert set(pc._hits) == {"a", "c", "d"}
