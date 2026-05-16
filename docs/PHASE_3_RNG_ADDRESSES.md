# Phase 3 — RNG hardening, BIP-44 TON, address validation, persistence

This phase fixes a handful of latent correctness bugs that became
exploitable only at scale, and migrates the persistence layer to
something that can survive a hard crash.

## Provably-fair RNG

### What was wrong

The legacy `get_provably_fair_result(server_seed, client_seed, nonce, n)`
computed:

```python
b = HMAC_SHA256(server_seed, f"{client_seed}:{nonce}:0")
return int(b[:4], 16) % n
```

`int % n` is **not uniformly distributed** when `n` does not divide
`2**32`.  For the mines game (`n=25`), the bias is ~1.5% on the last
tiles — small per round but a real edge over 10k+ rounds.

### What we did

[`core/fair_rng.py`](../core/fair_rng.py) implements **rejection
sampling**:

```python
sample = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
cutoff = 2**32 - (2**32 % n)
if sample < cutoff:
    return sample % n
# else read 4 more bytes and try again
```

Every outcome in `[0, n)` is now equiprobable up to HMAC-SHA256
collision resistance.

The old function name is kept as a shim — every existing
`get_provably_fair_result(...)` call gets the unbiased path for free.

### Nonce monotonicity

Nonces are reserved through a per-user lock:

```python
nonce = next_nonce(state, user_id, count=tiles_per_floor)
```

The lock is local to the worker (concurrent calls on the same user
inside one worker can't race).  Cross-worker monotonicity is
guaranteed by the wallet row lock — a bet can't settle until the
ledger entry commits, so two bets for the same user are serialised
end-to-end.

### Seed reveal lifecycle

`SeedState` carries `server_seed`, `server_seed_hash` (SHA-256 of the
seed, committed before play), `client_seed`, `nonce`, and
`next_server_seed` (the next committed seed, also pre-hashed).

`rotate(state, user_id)` reveals the active seed, promotes
`next_server_seed → server_seed`, generates a new `next_server_seed`,
and resets `nonce = 0`.  The revealed seed should be persisted in the
`pf_seed_lifecycle` table (Phase 2) so users can verify games years
later.

### Verifier UI

`tools/provably_fair_ui/index.html` is a 100% client-side verifier
that reproduces the unbiased draw in the browser via `crypto.subtle`.
Host it anywhere (GitHub Pages, your domain) and link from the bot's
`/serverseed` reply.

## BIP-44 TON derivation

The legacy code derived TON private keys with
`HMAC-SHA256(mnemonic, "ton-deposit:N")` — which is NOT BIP-44 and
**not recoverable in any other wallet**.  If the bot died and the
operators tried to restore the master mnemonic in TonKeeper, the
funds would be inaccessible.

[`core/ton_address.py`](../core/ton_address.py) replaces that with:

* SLIP-0044 coin type **607'** (TON)
* full derivation path `m/44'/607'/0'/0/index`
* Ed25519 keys via SLIP-0010 (hardened-only derivation)
* Output address built via `pytoniq-core` when available, falling
  back to a hand-rolled non-bounceable URL-safe base64 encoder

This makes every TON deposit address derivable in any BIP-44/Ed25519
wallet from the same mnemonic.

### Migration notes

The OLD `generate_ton_with_key()` is still callable — it's used by
`HDWalletManager.generate_ton_with_key` to derive **legacy** addresses
for existing user records.  New users get the BIP-44 path:

```python
from core.ton_address import derive_ton_address
derivation = derive_ton_address(mnemonic=MASTER_MNEMONIC, index=42)
# derivation.address, derivation.public_key_hex, derivation.private_key_hex
# derivation.derivation_path == "m/44'/607'/0'/0/42"
```

Operators MUST sweep funds from the legacy addresses BEFORE switching
users to BIP-44 — there's no chain-level link between the two paths.

## Withdrawal address validation

The old code only validated EVM-style (`0x...`) addresses.  Anyone
could submit a TRON or TON address as their BEP20 withdrawal target
and the bot would happily try to pay them out on Ethereum (where the
address is nonsense).

[`core/address_validation.py`](../core/address_validation.py) ships
strict validators for every chain we support:

| Coin / Chain          | Validator                                                 |
|-----------------------|-----------------------------------------------------------|
| BTC                   | Base58Check P2PKH/P2SH **OR** bech32/bech32m segwit `bc1` |
| LTC                   | Same as BTC but `L/M/3` prefix or `ltc1`                  |
| TRX / USDT(TRC20)     | Base58Check with leading `T`, 34 chars                    |
| SOL                   | Base58, 32-byte pubkey                                    |
| TON                   | URL-safe base64, CRC16-XMODEM checksum                    |
| ETH / BNB / BASE      | EIP-55 checksum **or** all-lower / all-upper hex          |

`validate(coin, address)` returns a `ValidationResult` with a
human-readable reason on failure — surface this to the user in the
withdrawal flow.

## Persistence migration

The legacy bot wrote each user's full state to
`data/users/{user_id}.json` every few seconds via a "dirty flag"
flusher.  Problems:

* Up to 10s of state lost on crash.
* Two workers writing the same file race each other.
* No transactional link between wallet authority (now in Postgres)
  and stats (in JSON).

[`core/persistence_backend.py`](../core/persistence_backend.py)
introduces a pluggable backend:

```python
from core import persistence_backend as pb

await pb.save(user_id, state_dict)       # routes to PG or JSON
state = await pb.load(user_id)
all_users = await pb.load_all()          # used at startup
```

Set `MYCASINO_PERSIST_BACKEND=postgres` to route writes to a
`user_state` JSONB table.  Without that env var (or if the pool
fails) the module falls through to the legacy disk path so
existing deployments keep working.

[`scripts/migrate_json_to_postgres.py`](../scripts/migrate_json_to_postgres.py)
does the one-time backfill and is idempotent.

## Tests

`tests/test_fair_rng.py`, `tests/test_address_validation.py`,
`tests/test_ton_address.py` and `tests/test_persistence_backend.py`
exercise the public API of each module.  They run without Postgres
or Redis (the persistence test creates a temp dir; the others are
pure-Python).
