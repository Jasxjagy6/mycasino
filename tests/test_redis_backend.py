"""Tests for ``core.redis_backend`` using fakeredis."""

from __future__ import annotations


import pytest

from core import redis_backend


@pytest.fixture(autouse=True)
async def _reset_redis_state():
    # Make sure each test starts fresh.
    await redis_backend.reset_client()
    redis_backend._dedup_local.clear()
    redis_backend._jackpot_local.clear()
    redis_backend._leaderboard_local.clear()
    redis_backend._rl_local_state.clear()
    yield
    await redis_backend.reset_client()


def _fakeredis():
    try:
        import fakeredis.aioredis as far  # type: ignore[import-not-found]

        return far.FakeRedis(decode_responses=True)
    except Exception:
        return None


# ---- rate limit ----


async def test_rate_limit_allows_within_window():
    client = _fakeredis()
    if client is None:
        pytest.skip("fakeredis not available")
    for i in range(5):
        r = await redis_backend.check_rate_limit(
            "u:1", limit=5, window_ms=1000, client=client, nonce=f"n{i}"
        )
        assert r.allowed, f"call {i} should be allowed"
    r = await redis_backend.check_rate_limit(
        "u:1", limit=5, window_ms=1000, client=client, nonce="n5"
    )
    assert not r.allowed
    assert r.retry_after_ms > 0


async def test_rate_limit_local_fallback():
    # No client supplied + Redis backend not enabled ⇒ local memory.
    redis_backend._rl_local_state.clear()
    for i in range(3):
        r = await redis_backend.check_rate_limit(
            "u:2", limit=3, window_ms=10_000, client=None, nonce=f"n{i}"
        )
        assert r.allowed
    r = await redis_backend.check_rate_limit(
        "u:2", limit=3, window_ms=10_000, client=None
    )
    assert not r.allowed


# ---- dedup ----


async def test_claim_once_only_first_call_succeeds():
    client = _fakeredis()
    if client is None:
        pytest.skip("fakeredis not available")
    assert await redis_backend.claim_once("intent-a", client=client) is True
    assert await redis_backend.claim_once("intent-a", client=client) is False
    # Different intent ⇒ ok.
    assert await redis_backend.claim_once("intent-b", client=client) is True


async def test_claim_once_local_fallback():
    redis_backend._dedup_local.clear()
    assert await redis_backend.claim_once("foo", client=None) is True
    assert await redis_backend.claim_once("foo", client=None) is False


# ---- jackpot ----


async def test_jackpot_increment_and_drop():
    client = _fakeredis()
    if client is None:
        pytest.skip("fakeredis not available")
    await redis_backend.incr_jackpot("blackjack", 1.5, client=client)
    await redis_backend.incr_jackpot("blackjack", 2.5, client=client)
    assert await redis_backend.get_jackpot("blackjack", client=client) == pytest.approx(4.0)
    paid = await redis_backend.drop_jackpot("blackjack", client=client)
    assert paid == pytest.approx(4.0)
    assert await redis_backend.get_jackpot("blackjack", client=client) == 0.0


async def test_jackpot_local_fallback():
    redis_backend._jackpot_local.clear()
    assert (await redis_backend.incr_jackpot("p", 1.0)) == pytest.approx(1.0)
    assert (await redis_backend.incr_jackpot("p", 2.5)) == pytest.approx(3.5)
    paid = await redis_backend.drop_jackpot("p")
    assert paid == pytest.approx(3.5)


# ---- leaderboard ----


async def test_leaderboard_incr_top_rank():
    client = _fakeredis()
    if client is None:
        pytest.skip("fakeredis not available")
    await redis_backend.lb_incr("daily", "wagered", 1, 100, client=client)
    await redis_backend.lb_incr("daily", "wagered", 2, 250, client=client)
    await redis_backend.lb_incr("daily", "wagered", 3, 50, client=client)
    top = await redis_backend.lb_top("daily", "wagered", limit=3, client=client)
    assert top == [(2, 250.0), (1, 100.0), (3, 50.0)]
    assert await redis_backend.lb_rank("daily", "wagered", 2, client=client) == 1
    assert await redis_backend.lb_rank("daily", "wagered", 3, client=client) == 3
    assert await redis_backend.lb_rank("daily", "wagered", 99, client=client) is None


async def test_leaderboard_local_fallback():
    redis_backend._leaderboard_local.clear()
    await redis_backend.lb_incr("weekly", "won", 1, 10.0)
    await redis_backend.lb_incr("weekly", "won", 2, 30.0)
    top = await redis_backend.lb_top("weekly", "won", limit=2)
    assert top == [(2, 30.0), (1, 10.0)]
