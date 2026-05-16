"""Phase 1d: live-price freshness + per-bet price locking.

This module is intentionally dependency-free (std-lib + ``typing`` only)
so it can be unit-tested without a running event loop, without
``telegram`` / ``web3`` / ``httpx``, and without any of the bot's
global state.

Audit references:
    upgrade_and_fixes.txt  S19   "HARDCODED LIVE_PRICES" -- staleness
                                  exploit on every USD<->crypto convert.
    upgrade_and_fixes.txt  M11   admin /cancel refunds at *current*
                                  price, not the price at bet time.
    upgrade_and_fixes.txt  14.1.6 "Hardcoded LIVE_PRICES -> live feed
                                  with TTL cache".

Design
------

The bot used to do this all over the codebase::

    price = LIVE_PRICES.get(coin, 1.0)
    crypto_amount = usd_amount / price

with two problems:

1. ``LIVE_PRICES`` is a process-local dict updated by a background job
   every 5 minutes. If MEXC (or whatever the source is) is unreachable
   for an hour, the dict silently keeps serving stale values. A user
   can deposit when this dict over-prices their coin and withdraw when
   it under-prices it -- free arbitrage on operator inattention (S19).

2. A bet places when BTC=$60k and settles a few minutes later when
   BTC=$55k. The deduct call used $60k; the credit call used $55k. The
   *house balance* is denominated in mixed prices, the user's wallet is
   credited at a different price than the bet was deducted at, and over
   thousands of bets the house leaks money via random price moves.

This module provides three primitives that, taken together, fix both:

* ``PriceQuote`` -- an immutable record of ``(coin, usd_per_coin,
  locked_at_ts)`` you pass through one bet from deduct to credit.
* ``lock_price(coin, source, *, now=None)`` -- snapshots the current
  price into a ``PriceQuote`` *only if* it is fresh enough. Stale
  prices raise ``StalePriceError`` instead of silently being served.
* ``is_price_fresh(coin, source, max_age_seconds=...)`` -- the boolean
  variant of the above for places that want to softly degrade.

``source`` is any mapping-like object (a dict, a Redis adapter, a fake
in unit tests) that supports ``.get_price(coin)`` and
``.get_updated_at(coin)``. The default production source wraps the
existing ``LIVE_PRICES`` / ``LIVE_PRICES_UPDATED_AT`` globals so this
module doesn't need to know about them.

Calling code can then::

    quote = lock_price("BTC", _DEFAULT_SOURCE)
    crypto_deducted = quote.usd_to_crypto(100.0)   # 0.001666... BTC
    ...
    # later, when the game settles:
    crypto_credited = quote.usd_to_crypto(200.0)   # 0.003333... BTC
    # -- uses the SAME price, regardless of how LIVE_PRICES moved in
    # between.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Protocol


__all__ = [
    "PriceQuote",
    "PriceSource",
    "StalePriceError",
    "UnknownCoinError",
    "DictPriceSource",
    "DEFAULT_MAX_PRICE_AGE_SECONDS",
    "HARD_MAX_PRICE_AGE_SECONDS",
    "lock_price",
    "is_price_fresh",
    "price_age_seconds",
]


# How long a quote may stay locked for. After this many seconds the
# `PriceQuote.is_expired()` flag flips to True so the bot can decide to
# requote (e.g. a long-running PvP duel may outlive its initial quote
# and need a fresh one before the settlement leg).
DEFAULT_MAX_PRICE_AGE_SECONDS: float = 600.0  # 10 minutes -- 2x the MEXC poll interval.

# Hard ceiling. If the upstream feed has been stale longer than this,
# we refuse to lock a quote at all. The caller must surface an error
# to the user rather than silently betting against a stale price.
HARD_MAX_PRICE_AGE_SECONDS: float = 1800.0  # 30 minutes.


class StalePriceError(RuntimeError):
    """Raised when the upstream price feed has been stale for longer
    than ``HARD_MAX_PRICE_AGE_SECONDS``.

    Callers must surface this to the user as "this coin is temporarily
    unavailable; please pick another or try again shortly" rather than
    silently proceeding with the last-known price.
    """


class UnknownCoinError(KeyError):
    """Raised when the source does not have a price recorded for the
    requested coin (i.e. the symbol isn't in our supported set or the
    feed has never returned a value)."""


class PriceSource(Protocol):
    """Anything that can produce ``(price, updated_at)`` pairs.

    Used to inject the production globals (or a test double) into
    ``lock_price`` / ``is_price_fresh`` without making this module
    import ``core.foundation``.
    """

    def get_price(self, coin: str) -> Optional[float]:
        """Return the USD price of one unit of ``coin`` or ``None``."""

    def get_updated_at(self, coin: str) -> Optional[float]:
        """Return the unix-time the price was last refreshed, or
        ``None`` if it has never been seen."""


class DictPriceSource:
    """Production adapter wrapping the existing ``LIVE_PRICES`` /
    ``LIVE_PRICES_UPDATED_AT`` globals (or any equivalent mapping pair).

    Usage::

        from core.prices import lock_price, DictPriceSource
        from core.foundation import LIVE_PRICES, LIVE_PRICES_UPDATED_AT

        src = DictPriceSource(LIVE_PRICES, LIVE_PRICES_UPDATED_AT)
        quote = lock_price("BTC", src)

    Notes
    -----
    * Coin lookup is case-insensitive on the caller side -- we upper
      the key before reading.
    * If ``updated_at_map`` does not have a timestamp for the coin
      (e.g. process just started and MEXC fetcher hasn't run yet),
      ``get_updated_at`` returns ``None`` so ``price_age_seconds``
      reports ``+inf`` and freshness checks fail safely.
    """

    __slots__ = ("_prices", "_updated_at")

    def __init__(self, prices_map, updated_at_map) -> None:
        self._prices = prices_map
        self._updated_at = updated_at_map

    def get_price(self, coin: str) -> Optional[float]:
        coin_u = coin.upper()
        try:
            val = self._prices.get(coin_u)
        except AttributeError:  # not a mapping
            return None
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_updated_at(self, coin: str) -> Optional[float]:
        coin_u = coin.upper()
        try:
            val = self._updated_at.get(coin_u)
        except AttributeError:
            return None
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None


class PriceQuote:
    """Immutable snapshot of one coin's USD price at a moment in time.

    Pass instances of this through the bet lifecycle (deduct -> game
    play -> credit) to guarantee a single, time-frozen exchange rate.

    Attributes
    ----------
    coin:
        Ticker symbol ("BTC", "ETH", ...).
    usd_per_coin:
        Price of one unit of the coin in USD at lock time. Strictly
        positive.
    locked_at:
        Unix timestamp at which this quote was taken. Used to compute
        ``age_seconds()`` for expiry checks.
    max_age_seconds:
        How long the quote is considered valid. After
        ``locked_at + max_age_seconds``, ``is_expired()`` returns True.
    source:
        Free-form string identifying who produced this quote (e.g.
        ``"mexc"``, ``"oxapay-callback"``, ``"manual"``). Useful for
        audit logs.
    """

    __slots__ = ("coin", "usd_per_coin", "locked_at",
                 "max_age_seconds", "source")

    def __init__(
        self,
        coin: str,
        usd_per_coin: float,
        *,
        locked_at: Optional[float] = None,
        max_age_seconds: float = DEFAULT_MAX_PRICE_AGE_SECONDS,
        source: str = "live",
    ) -> None:
        if not coin or not isinstance(coin, str):
            raise ValueError(f"coin must be a non-empty string, got {coin!r}")
        if usd_per_coin is None or usd_per_coin <= 0:
            raise ValueError(
                f"usd_per_coin must be strictly positive, got {usd_per_coin!r}"
            )
        if max_age_seconds <= 0:
            raise ValueError(
                f"max_age_seconds must be positive, got {max_age_seconds!r}"
            )
        self.coin = coin.upper()
        self.usd_per_coin = float(usd_per_coin)
        self.locked_at = float(locked_at) if locked_at is not None else time.time()
        self.max_age_seconds = float(max_age_seconds)
        self.source = source or "live"

    # ----- price math ------------------------------------------------

    def usd_to_crypto(self, usd_amount: float) -> float:
        """Convert ``usd_amount`` USD into the equivalent amount of
        coin at this locked price."""
        return float(usd_amount) / self.usd_per_coin

    def crypto_to_usd(self, crypto_amount: float) -> float:
        """Convert ``crypto_amount`` of coin into the equivalent USD at
        this locked price."""
        return float(crypto_amount) * self.usd_per_coin

    # ----- expiry ----------------------------------------------------

    def age_seconds(self, now: Optional[float] = None) -> float:
        """How long ago (seconds) this quote was locked."""
        ref = float(now) if now is not None else time.time()
        return max(0.0, ref - self.locked_at)

    def is_expired(self, now: Optional[float] = None) -> bool:
        """True if this quote has been held longer than
        ``max_age_seconds``."""
        return self.age_seconds(now) > self.max_age_seconds

    # ----- serialisation --------------------------------------------

    def to_dict(self) -> dict:
        """Stable dict representation suitable for JSON / session
        persistence."""
        return {
            "coin": self.coin,
            "usd_per_coin": self.usd_per_coin,
            "locked_at": self.locked_at,
            "max_age_seconds": self.max_age_seconds,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "PriceQuote":
        """Inverse of ``to_dict()``. Validates required keys."""
        if not isinstance(payload, dict):
            raise TypeError(
                f"PriceQuote.from_dict expected dict, got {type(payload)!r}"
            )
        try:
            coin = payload["coin"]
            usd_per_coin = payload["usd_per_coin"]
        except KeyError as e:
            raise ValueError(f"missing key in price-quote payload: {e}") from e
        return cls(
            coin,
            usd_per_coin,
            locked_at=payload.get("locked_at"),
            max_age_seconds=payload.get(
                "max_age_seconds", DEFAULT_MAX_PRICE_AGE_SECONDS,
            ),
            source=payload.get("source", "live"),
        )

    # ----- equality / repr ------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"PriceQuote(coin={self.coin!r}, "
            f"usd_per_coin={self.usd_per_coin!r}, "
            f"locked_at={self.locked_at!r}, "
            f"max_age_seconds={self.max_age_seconds!r}, "
            f"source={self.source!r})"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PriceQuote):
            return NotImplemented
        return (
            self.coin == other.coin
            and self.usd_per_coin == other.usd_per_coin
            and self.locked_at == other.locked_at
            and self.max_age_seconds == other.max_age_seconds
            and self.source == other.source
        )

    def __hash__(self) -> int:
        return hash(
            (self.coin, self.usd_per_coin, self.locked_at,
             self.max_age_seconds, self.source)
        )


# ---------------------------------------------------------------------
# Top-level helpers
# ---------------------------------------------------------------------


def price_age_seconds(
    coin: str,
    source: PriceSource,
    *,
    now: Optional[float] = None,
) -> float:
    """Return how many seconds ago ``coin``'s price was last refreshed.

    Returns ``+inf`` if the source has never seen a price for this
    coin (so callers can use it as a staleness comparator without a
    None check).
    """
    updated_at = source.get_updated_at(coin)
    if updated_at is None:
        return float("inf")
    ref = float(now) if now is not None else time.time()
    return max(0.0, ref - float(updated_at))


def is_price_fresh(
    coin: str,
    source: PriceSource,
    *,
    max_age_seconds: float = HARD_MAX_PRICE_AGE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """True iff the source has a price for ``coin`` AND it was
    refreshed within ``max_age_seconds``.

    Use this when you want to softly degrade (e.g. hide a coin from
    the deposit menu) rather than throw.
    """
    price = source.get_price(coin)
    if price is None or price <= 0:
        return False
    return price_age_seconds(coin, source, now=now) <= max_age_seconds


def lock_price(
    coin: str,
    source: PriceSource,
    *,
    max_age_seconds: float = HARD_MAX_PRICE_AGE_SECONDS,
    quote_lifetime_seconds: float = DEFAULT_MAX_PRICE_AGE_SECONDS,
    now: Optional[float] = None,
    source_name: str = "live",
) -> PriceQuote:
    """Take a ``PriceQuote`` for ``coin`` using the current value from
    ``source``.

    Raises:
        UnknownCoinError:
            ``source`` has no price for this coin at all.
        StalePriceError:
            the price exists but was last refreshed longer than
            ``max_age_seconds`` ago (default 30 min). Callers should
            translate this into a user-visible "coin temporarily
            unavailable" message.
    """
    coin_upper = coin.upper()
    price = source.get_price(coin_upper)
    if price is None:
        raise UnknownCoinError(coin_upper)
    if price <= 0:
        raise UnknownCoinError(coin_upper)
    age = price_age_seconds(coin_upper, source, now=now)
    if age > max_age_seconds:
        raise StalePriceError(
            f"{coin_upper} price is {age:.0f}s old (max {max_age_seconds:.0f}s)"
        )
    return PriceQuote(
        coin_upper,
        price,
        locked_at=now if now is not None else time.time(),
        max_age_seconds=quote_lifetime_seconds,
        source=source_name,
    )
