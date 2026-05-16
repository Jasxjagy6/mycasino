# Provably-fair verifier UI

`tools/provably_fair_ui/index.html` is a 100% client-side HTML page
that re-derives any game outcome from `(server_seed, client_seed,
nonce, modulus)`.  Nothing is uploaded — everything runs in
WebCrypto.

## Hosting

The simplest option is GitHub Pages:

1. Copy the file to `gh-pages` branch.
2. Configure GitHub Pages to serve from `gh-pages`.
3. Link the bot's `/serverseed` reply to
   `https://<youraccount>.github.io/mycasino/`.

For full white-labelling, drop the HTML behind your own static host
(nginx, Cloudflare Pages, Vercel) and replace the page metadata.

## What it verifies

For each game we expose the right modulus:

| Game            | Modulus n | Notes                                          |
|-----------------|-----------|------------------------------------------------|
| Mines           | 25        | One nonce per tile shuffled in Fisher-Yates    |
| Coinflip / Dice | 2         | Nonce 0 picks the outcome                      |
| Roulette        | 37        | Pocket 0..36 inclusive                         |
| Plinko          | 2         | One bit per row                                |
| Slots           | 7         | Per-reel symbol index                          |
| Keno            | 40        | Picks distinct numbers via reservoir-shuffle   |
| Limbo           | —         | Uniform float in [0, 1)                        |
| Custom          | user-set  | For one-off audits                             |

The page shows the SHA-256 of the user's server seed first — if the
hash matches the commit the bot showed BEFORE play, the operator
couldn't have changed the seed after the round.

## Embedding the verifier in the bot

The bot's `/serverseed` flow already has a "Verify" button.  Have it
deep-link to the verifier with the seeds pre-filled:

```
https://<yourdomain>/verify?game=mines&server_seed=<seed>&client_seed=<cseed>&nonce=42
```

Patch `index.html` to parse `window.location.search` and pre-fill the
form (TODO — left as a follow-up since the static page already lets
users paste).
