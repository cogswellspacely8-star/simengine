# Real-Time Data Feeds (opt-in)

SimEngine's core is offline and pure-stdlib. The `v3/feeds/` package is the
optional bridge to live data. It is the only part of the engine that touches the
network, it still uses only the standard library (`urllib`), and the core never
imports it.

## Polymarket Gamma (`feeds/polymarket.py`)

Turns a live prediction-market price into a SimEngine prior you can drop into a
domain config and refine with the Beta-Binomial updater. Zero auth, zero new
dependencies.

### Why this is the differentiated move

Every dashboard can show you a market price. The value here is the bridge:
a market-implied probability becomes a **calibrated prior** with explicit
uncertainty, which the engine then updates as your own evidence arrives.
Price in → prior → posterior, not price in → price out.

### Functions

| Function | Pure? | Returns |
|---|---|---|
| `implied_probabilities(market)` | yes | `{outcome: prob}` from a Gamma market dict |
| `yes_probability(market)` | yes | the 'Yes' price (else first outcome) |
| `beta_prior(p, strength=20)` | yes | `{alpha, beta}` Beta prior with mean `p` |
| `prior_variable(p, strength=20)` | yes | a SimEngine triangular variable_def |
| `market_prior(market, strength=20)` | yes | raw market dict → variable_def |
| `fetch_markets(query, active, closed, limit, _get)` | no (network) | list of market dicts |

`strength` is the prior's concentration in pseudo-observations: higher = more
confident the market is right. 20 is a sane default; lower it if you trust the
market less.

### Worked example

```python
from feeds import polymarket
from bayesian import beta_binomial_update

# 1. Pull markets and read an implied probability
markets = polymarket.fetch_markets(query="fed rate", limit=5)
m = markets[0]
print(polymarket.implied_probabilities(m))      # {'Yes': 0.62, 'No': 0.38}

# 2. Turn the market price into a prior variable for a domain config
var = polymarket.market_prior(m, strength=20)
# -> {"distribution": "triangular", "params": {...}, "calibration": {...}}
config["parameters"]["event_happens"] = var

# 3. As your own evidence arrives, tighten it with the Beta-Binomial updater
updated_params, report = beta_binomial_update(var["params"], observations=[(7, 10)])
```

### ToS / posture

Treat market prices as **internal simulation inputs** feeding a derived
analytical prior — not a rebroadcast price feed, and never a trade signal.
Polymarket's participant terms restrict redistribution; this adapter keeps the
price inside the model. Kalshi's data terms are stricter (no software/AI use
without written consent) — do not build a Kalshi feed adapter on the same
footing until there is a signed agreement.
