"""Unit tests for ``core.prices`` -- the price-locking / freshness module.

These tests are intentionally dependency-free (no ``telegram``,
``httpx``, ``web3`` etc.) so they run in any environment with Python
3.10+ available -- mirroring ``tests/test_game_math.py``.

References:
    upgrade_and_fixes.txt  S19   "HARDCODED LIVE_PRICES" -- staleness
                                  exploit on every USD<->crypto convert.
    upgrade_and_fixes.txt  14.1.6 "Hardcoded LIVE_PRICES -> live feed
                                  with TTL cache".
"""

from __future__ import annotations

import math

import pytest

from core import prices


# ---------------------------------------------------------------------
# PriceQuote: construction / validation
# ---------------------------------------------------------------------


def test_price_quote_basic_construction() -> None:
    q = prices.PriceQuote("BTC", 60000.0, locked_at=1_700_000_000.0)
    assert q.coin == "BTC"
    assert q.usd_per_coin == 60000.0
    assert q.locked_at == 1_700_000_000.0
    assert q.source == "live"


def test_price_quote_uppercases_coin() -> None:
    q = prices.PriceQuote("btc", 60000.0, locked_at=1.0)
    assert q.coin == "BTC"


def test_price_quote_rejects_empty_coin() -> None:
    with pytest.raises(ValueError):
        prices.PriceQuote("", 60000.0)
    with pytest.raises(ValueError):
        prices.PriceQuote(None, 60000.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1.0, None])
def test_price_quote_rejects_non_positive_price(bad) -> None:
    with pytest.raises(ValueError):
        prices.PriceQuote("BTC", bad)


def test_price_quote_rejects_non_positive_max_age() -> None:
    with pytest.raises(ValueError):
        prices.PriceQuote("BTC", 60000.0, max_age_seconds=0)
    with pytest.raises(ValueError):
        prices.PriceQuote("BTC", 60000.0, max_age_seconds=-30)


# ---------------------------------------------------------------------
# PriceQuote: usd<->crypto round trip
# ---------------------------------------------------------------------


def test_price_quote_round_trip_is_identity() -> None:
    """Convert USD to crypto then back to USD; result must equal input."""
    q = prices.PriceQuote("BTC", 60000.0, locked_at=1.0)
    for usd in [1.0, 100.0, 1_234.56, 50_000.0]:
        crypto = q.usd_to_crypto(usd)
        assert math.isclose(q.crypto_to_usd(crypto), usd, rel_tol=1e-12)


@pytest.mark.parametrize(
    "price,usd,expected_crypto",
    [
        (60000.0, 100.0, 100.0 / 60000.0),     # BTC at $60k
        (2000.0,  50.0,  50.0 / 2000.0),       # ETH at $2k
        (0.10,    10.0,  100.0),               # TRX at $0.10
        (100.0,   25.0,  0.25),                # SOL at $100
        (1.0,     1.0,   1.0),                 # USDT
    ],
)
def test_price_quote_usd_to_crypto_known_values(
    price: float, usd: float, expected_crypto: float
) -> None:
    q = prices.PriceQuote("X", price, locked_at=1.0)
    assert math.isclose(q.usd_to_crypto(usd), expected_crypto, rel_tol=1e-12)


# ---------------------------------------------------------------------
# PriceQuote: expiry
# ---------------------------------------------------------------------


def test_price_quote_not_expired_immediately() -> None:
    q = prices.PriceQuote("BTC", 60000.0, locked_at=1_700_000_000.0,
                          max_age_seconds=600.0)
    assert q.is_expired(now=1_700_000_000.0) is False
    assert q.is_expired(now=1_700_000_300.0) is False  # 5 min later
    assert q.age_seconds(now=1_700_000_300.0) == 300.0


def test_price_quote_expires_after_max_age() -> None:
    q = prices.PriceQuote("BTC", 60000.0, locked_at=1_700_000_000.0,
                          max_age_seconds=600.0)
    # exactly at max_age -> NOT expired (boundary inclusive)
    assert q.is_expired(now=1_700_000_600.0) is False
    # one second past -> expired
    assert q.is_expired(now=1_700_000_601.0) is True
    # 1 hour later -> definitely expired
    assert q.is_expired(now=1_700_003_600.0) is True


def test_price_quote_age_seconds_floors_at_zero_for_future_now() -> None:
    """Don't return negative ages if the clock is weird."""
    q = prices.PriceQuote("BTC", 60000.0, locked_at=1_700_000_000.0)
    assert q.age_seconds(now=1_699_999_999.0) == 0.0


# ---------------------------------------------------------------------
# PriceQuote: serialisation
# ---------------------------------------------------------------------


def test_price_quote_round_trip_dict() -> None:
    original = prices.PriceQuote(
        "ETH", 1995.55, locked_at=1_700_000_000.5,
        max_age_seconds=1234.5, source="mexc",
    )
    payload = original.to_dict()
    restored = prices.PriceQuote.from_dict(payload)
    assert restored == original


def test_price_quote_from_dict_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        prices.PriceQuote.from_dict("not a dict")  # type: ignore[arg-type]


def test_price_quote_from_dict_requires_core_keys() -> None:
    with pytest.raises(ValueError):
        prices.PriceQuote.from_dict({"coin": "BTC"})  # missing usd_per_coin
    with pytest.raises(ValueError):
        prices.PriceQuote.from_dict({"usd_per_coin": 1.0})  # missing coin


# ---------------------------------------------------------------------
# DictPriceSource (production adapter)
# ---------------------------------------------------------------------


def _make_source(prices_map=None, updated_at_map=None):
    """Test helper: build a DictPriceSource from python dicts."""
    return prices.DictPriceSource(
        prices_map or {}, updated_at_map or {},
    )


def test_dict_price_source_returns_price_when_present() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1.0})
    assert src.get_price("BTC") == 60000.0
    assert src.get_price("btc") == 60000.0  # case-insensitive lookup


def test_dict_price_source_returns_none_for_missing_coin() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1.0})
    assert src.get_price("ETH") is None
    assert src.get_updated_at("ETH") is None


def test_dict_price_source_returns_none_for_non_numeric() -> None:
    """Defensive: source may have a corrupt entry."""
    src = _make_source({"BTC": "oops"}, {"BTC": "also oops"})
    assert src.get_price("BTC") is None
    assert src.get_updated_at("BTC") is None


def test_dict_price_source_handles_non_mapping_input() -> None:
    """If somebody passes a non-mapping by mistake, return None
    rather than crashing the call site."""
    src = prices.DictPriceSource(object(), object())  # type: ignore[arg-type]
    assert src.get_price("BTC") is None
    assert src.get_updated_at("BTC") is None


# ---------------------------------------------------------------------
# price_age_seconds
# ---------------------------------------------------------------------


def test_price_age_seconds_returns_inf_for_missing() -> None:
    src = _make_source({"BTC": 60000.0}, {})
    age = prices.price_age_seconds("BTC", src, now=1_700_000_000.0)
    assert age == float("inf")


def test_price_age_seconds_basic() -> None:
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    assert prices.price_age_seconds(
        "BTC", src, now=1_700_000_120.0,
    ) == 120.0


# ---------------------------------------------------------------------
# is_price_fresh
# ---------------------------------------------------------------------


def test_is_price_fresh_true_when_recent() -> None:
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    # 5 min old, default max 30 min -> fresh
    assert prices.is_price_fresh(
        "BTC", src, now=1_700_000_300.0,
    ) is True


def test_is_price_fresh_false_when_stale() -> None:
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    # 1 hour old, default max 30 min -> stale
    assert prices.is_price_fresh(
        "BTC", src, now=1_700_003_600.0,
    ) is False


def test_is_price_fresh_respects_custom_max_age() -> None:
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    # 2 min old, custom max 60s -> stale
    assert prices.is_price_fresh(
        "BTC", src, max_age_seconds=60.0, now=1_700_000_120.0,
    ) is False


def test_is_price_fresh_false_for_unknown_coin() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1_700_000_000.0})
    assert prices.is_price_fresh(
        "DOGE", src, now=1_700_000_001.0,
    ) is False


def test_is_price_fresh_false_for_zero_or_negative_price() -> None:
    src = _make_source(
        {"BTC": 0.0, "ETH": -1.0},
        {"BTC": 1_700_000_000.0, "ETH": 1_700_000_000.0},
    )
    assert prices.is_price_fresh(
        "BTC", src, now=1_700_000_001.0,
    ) is False
    assert prices.is_price_fresh(
        "ETH", src, now=1_700_000_001.0,
    ) is False


# ---------------------------------------------------------------------
# lock_price -- the core helper
# ---------------------------------------------------------------------


def test_lock_price_returns_quote_when_fresh() -> None:
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    quote = prices.lock_price(
        "BTC", src, now=1_700_000_120.0, source_name="mexc",
    )
    assert isinstance(quote, prices.PriceQuote)
    assert quote.coin == "BTC"
    assert quote.usd_per_coin == 60000.0
    assert quote.locked_at == 1_700_000_120.0
    assert quote.source == "mexc"


def test_lock_price_raises_for_unknown_coin() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1_700_000_000.0})
    with pytest.raises(prices.UnknownCoinError):
        prices.lock_price("DOGE", src, now=1_700_000_001.0)


def test_lock_price_raises_for_stale_price() -> None:
    """The headline audit fix: a stale price must NOT silently lock."""
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    # 1 hour old at default 30 min ceiling -> StalePriceError
    with pytest.raises(prices.StalePriceError):
        prices.lock_price("BTC", src, now=1_700_003_600.0)


def test_lock_price_raises_for_zero_price() -> None:
    src = _make_source({"BTC": 0.0}, {"BTC": 1_700_000_000.0})
    with pytest.raises(prices.UnknownCoinError):
        prices.lock_price("BTC", src, now=1_700_000_001.0)


def test_lock_price_uppercases_coin_symbol() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1_700_000_000.0})
    quote = prices.lock_price("btc", src, now=1_700_000_001.0)
    assert quote.coin == "BTC"


def test_lock_price_default_quote_lifetime() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1_700_000_000.0})
    quote = prices.lock_price("BTC", src, now=1_700_000_001.0)
    assert quote.max_age_seconds == prices.DEFAULT_MAX_PRICE_AGE_SECONDS


def test_lock_price_custom_quote_lifetime() -> None:
    src = _make_source({"BTC": 60000.0}, {"BTC": 1_700_000_000.0})
    quote = prices.lock_price(
        "BTC", src,
        quote_lifetime_seconds=30.0,
        now=1_700_000_001.0,
    )
    assert quote.max_age_seconds == 30.0


# ---------------------------------------------------------------------
# Integration scenarios (the bug we're fixing, end-to-end)
# ---------------------------------------------------------------------


def test_bet_round_trip_uses_same_price_even_if_market_moved() -> None:
    """The headline behavioural change: bet at $60k, win settles at $55k,
    payout should still use $60k because we locked the quote."""
    # State at bet time
    src_at_bet = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )
    quote = prices.lock_price("BTC", src_at_bet, now=1_700_000_001.0)

    # Bet $100 -> deduct 0.001666... BTC
    bet_usd = 100.0
    crypto_deducted = quote.usd_to_crypto(bet_usd)
    assert math.isclose(crypto_deducted, 100.0 / 60000.0, rel_tol=1e-12)

    # ... 5 minutes pass, BTC drops to $55k. But we settle with the
    # ORIGINAL quote -- the source dict moving is irrelevant.
    # (in production: we'd never re-read the source for this bet.)
    payout_usd = 200.0
    crypto_credited = quote.usd_to_crypto(payout_usd)
    # House net (USD-equivalent of the wallet movement) at the LOCKED price
    house_net_usd = quote.crypto_to_usd(crypto_credited) - bet_usd
    assert math.isclose(house_net_usd, 100.0, rel_tol=1e-12)


def test_bet_at_locked_price_isolates_from_subsequent_feed_movement() -> None:
    """Even if we keep a reference to the dict and the operator
    over-writes it, the PriceQuote we already captured is by-value
    -- it has its own ``usd_per_coin`` float."""
    prices_map = {"BTC": 60000.0}
    updated_at_map = {"BTC": 1_700_000_000.0}
    src = prices.DictPriceSource(prices_map, updated_at_map)
    quote = prices.lock_price("BTC", src, now=1_700_000_001.0)

    # Simulate operator (or feed) shoving in a new price.
    prices_map["BTC"] = 80000.0
    updated_at_map["BTC"] = 1_700_001_000.0

    # Quote is unchanged -- this is THE critical invariant.
    assert quote.usd_per_coin == 60000.0
    assert quote.usd_to_crypto(100.0) == 100.0 / 60000.0


def test_stale_price_blocks_new_bets_but_not_existing_quote() -> None:
    """If the upstream price feed has gone silent, we refuse to lock a
    new quote -- but bets already in flight with an existing quote
    continue to settle correctly (and not get re-priced)."""
    src = _make_source(
        {"BTC": 60000.0},
        {"BTC": 1_700_000_000.0},
    )

    # Earlier in the day someone locked a quote.
    existing_quote = prices.lock_price(
        "BTC", src, now=1_700_000_001.0,
    )

    # An hour passes, MEXC has been down. New bet attempts fail.
    with pytest.raises(prices.StalePriceError):
        prices.lock_price("BTC", src, now=1_700_003_700.0)

    # But the in-flight quote still settles. The credit/refund path
    # works off ``existing_quote.usd_to_crypto(...)``, never the source.
    assert existing_quote.usd_to_crypto(100.0) == 100.0 / 60000.0
