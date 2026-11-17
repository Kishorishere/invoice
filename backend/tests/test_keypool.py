"""Unit tests for KeyPool rotation + the with_pool_rotation wrapper."""

from __future__ import annotations

import pytest

from app.services.providers.base import ProviderError
from app.services.providers.keypool import KeyPool, KeyPoolExhausted, with_pool_rotation


# ---------- KeyPool mechanics ----------


def test_pool_rotates_round_robin() -> None:
    pool = KeyPool(["a", "b", "c"], label="test")
    assert pool.current() == "a"
    assert pool.rotate() == "b"
    assert pool.rotate() == "c"
    assert pool.rotate() == "a"


def test_pool_strips_blanks_and_whitespace() -> None:
    pool = KeyPool([" a ", "", "b", "   "], label="test")
    assert len(pool) == 2
    assert pool.current() == "a"
    assert pool.rotate() == "b"


def test_empty_pool_raises_on_current() -> None:
    pool = KeyPool([], label="test")
    assert len(pool) == 0
    with pytest.raises(KeyPoolExhausted):
        pool.current()


def test_kill_current_removes_from_rotation() -> None:
    pool = KeyPool(["a", "b", "c"], label="test")
    assert pool.current() == "a"
    pool.kill_current()  # 'a' dies, cursor moves to 'b'
    assert pool.current() == "b"
    assert pool.alive_count == 2
    assert pool.rotate() == "c"
    assert pool.rotate() == "b"  # skips 'a'


def test_killing_last_key_raises() -> None:
    pool = KeyPool(["a"], label="test")
    with pytest.raises(KeyPoolExhausted):
        pool.kill_current()


# ---------- with_pool_rotation ----------


def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_succeeds_without_rotation_on_happy_path() -> None:
    pool = KeyPool(["a", "b"], label="test")
    rebuilds: list[str] = []

    async def attempt():
        return "ok"

    def rebuild():
        rebuilds.append(pool.current())

    result = _run(with_pool_rotation(pool, rebuild, attempt, provider_name="X"))
    assert result == "ok"
    assert rebuilds == []
    assert pool.current() == "a"  # cursor didn't move


def test_rotates_on_503_and_succeeds_on_next_key() -> None:
    pool = KeyPool(["a", "b"], label="test")
    calls: list[str] = []

    async def attempt():
        key = pool.current()
        calls.append(key)
        if key == "a":
            raise ProviderError("overloaded", http_status=503)
        return f"ok on {key}"

    def rebuild():
        pass

    result = _run(with_pool_rotation(pool, rebuild, attempt, provider_name="X"))
    assert result == "ok on b"
    assert calls == ["a", "b"]


def test_kills_key_on_401_and_tries_next() -> None:
    pool = KeyPool(["a", "b"], label="test")
    calls: list[str] = []

    async def attempt():
        key = pool.current()
        calls.append(key)
        if key == "a":
            raise ProviderError("bad key", http_status=401)
        return "ok"

    def rebuild():
        pass

    result = _run(with_pool_rotation(pool, rebuild, attempt, provider_name="X"))
    assert result == "ok"
    assert calls == ["a", "b"]
    assert pool.alive_count == 1  # 'a' is dead


def test_all_keys_fail_reraises_last_error() -> None:
    pool = KeyPool(["a", "b"], label="test")

    async def attempt():
        raise ProviderError(f"overload on {pool.current()}", http_status=503)

    def rebuild():
        pass

    with pytest.raises(ProviderError) as excinfo:
        _run(with_pool_rotation(pool, rebuild, attempt, provider_name="X"))
    assert excinfo.value.http_status == 503


def test_non_retriable_error_does_not_rotate() -> None:
    pool = KeyPool(["a", "b"], label="test")
    calls: list[str] = []

    async def attempt():
        calls.append(pool.current())
        raise ProviderError("bad image", http_status=400)

    def rebuild():
        pass

    with pytest.raises(ProviderError) as excinfo:
        _run(with_pool_rotation(pool, rebuild, attempt, provider_name="X"))
    assert excinfo.value.http_status == 400
    assert calls == ["a"]  # did not try 'b'


def test_single_key_pool_passes_503_through() -> None:
    # With one key there's nothing to rotate to; the caller handles it.
    pool = KeyPool(["only"], label="test")
    calls: list[str] = []

    async def attempt():
        calls.append(pool.current())
        raise ProviderError("overloaded", http_status=503)

    def rebuild():
        pass

    with pytest.raises(ProviderError) as excinfo:
        _run(with_pool_rotation(pool, rebuild, attempt, provider_name="X"))
    assert excinfo.value.http_status == 503
    assert calls == ["only"]
