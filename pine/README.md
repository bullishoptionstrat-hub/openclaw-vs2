# OpenClaw · ICT / Institutional Confluence Engine (TradingView, Pine v5)

Two Pine Script **v5** scripts that codify a discretionary institutional-confluence
framework into a rules-based, **non-repainting** system for **ES1! / NQ1! / GC1! / SI1!**
(and any other liquid future, index or ETF).

| File | Type | Purpose |
| --- | --- | --- |
| `openclaw-ict-confluence-indicator.pine` | `indicator()` | Chart engine, dashboard, `alertcondition()` webhooks |
| `openclaw-ict-confluence-strategy.pine` | `strategy()` | Same engine + order execution, sizing, partials |

Both files are **generated** from `parts/` by `./build.sh`, which also asserts that
the shared `SHARED CONFLUENCE ENGINE` block is byte-identical in both outputs — so
strategy fills always mirror indicator signals. Edit `parts/*.pine`, never the
generated `.pine` files at the top level.

```bash
./build.sh   # regenerates both scripts and verifies engine parity
```

---

## Non-repainting contract

* Every `request.security()` call uses `lookahead = barmerge.lookahead_off`.
* HTF structure (`f_htfPack`) returns the state of the **last closed HTF bar**, so a
  Monthly/Weekly/Daily/4H bias only changes when that HTF bar actually closes.
* All structure and setup-state transitions are gated behind `barstate.isconfirmed`
  (`confirm` in the code). Nothing is written to state from an unclosed bar.
* Swing structure uses `ta.pivothigh` / `ta.pivotlow`, which confirm N bars later by
  construction — no forward reference.
* The strategy runs `process_orders_on_close = true`, `calc_on_every_tick = false`,
  `pyramiding = 0`, so orders are submitted on confirmed closes only.
* No `security()` on future offsets, no `varip`, no bar-magnifier tricks.

---

## Framework → code map

### Tier 1 — non-negotiables (hard blockers)

| Framework item | Implementation |
| --- | --- |
| HTF top-down bias | `f_structure()` swing/BOS/CHoCH machine run on Monthly, Weekly, Daily, 4H via `request.security`. States: Bullish / Bearish / Neutral. |
| HTF conflict resolution | **Daily is the arbiter.** Weekly, then Monthly, override it *only* while their own BOS is fresh (`overrideAge`, default 3 HTF bars). A direct **Daily vs 4H conflict resolves to Neutral ⇒ blocked**. No LTF longs under bearish bias, no LTF shorts under bullish bias. |
| Internal vs external liquidity | Two pivot lengths: `intLen` (internal) and `extLen` (external). External pivots *promote* the matching internal level. Internal = dashed orange, external = solid blue. |
| Valid external liquidity | An external pool counts as a **valid external target** only after (a) internal liquidity was taken and (b) BOS/CHoCH confirmed the shift (`extValidBuy` / `extValidSell`). Otherwise TP2 falls back to the dealing-range extreme and the dashboard labels it `unqualified external`. |
| Protected highs/lows | `protHigh` / `protLow` are set on each sweep; `sProt` is the swing that produced the displacement and anchors the stop. `smtProtect` marks the protected swing at a valid SMT. |
| Kill zones (New York time) | London `0200-0400`, CBDR/pre-market `0700-0830`, NY AM `0800-1100`, NY PM `1300-1600` — all user-configurable and individually toggleable, shaded on chart. Entries are blocked outside enabled zones (`kzUse`). |

### Tier 2 — core structure confluences

| Framework item | Implementation |
| --- | --- |
| SMT divergence | Compares the chart symbol against a configurable pair. On a raid of a stored reference swing, if the pair fails to confirm ⇒ bullish/bearish SMT; if it confirms ⇒ `Correlated (no divergence)`; stale/no data ⇒ `Unclear`. `smtStrict` makes *unclear* a hard blocker. `smtInverse` mirrors the pair for inverse-correlation proxies (e.g. DXY). |
| Sweep → displacement → retest | Explicit state machine (`sState`: idle → swept → displaced). Displacement is measurable: range ≥ `dispAtrMult` × ATR, body/range ≥ `dispBodyRatio`, optional volume expansion, and (default) it must leave an FVG. CHoCH after the sweep is required by default. **Entry only on the retest of the displacement origin — the first touch of the swept liquidity is never traded.** |
| FVG / OB / breaker | Classic 3-candle FVGs; order blocks = last opposite-colour candle before the displacement; a violated zone flips once into a breaker and dies on the second violation. When an FVG and an OB overlap, the **intersection** becomes the entry zone and the overlap flag counts toward Tier-2. |
| Premium / discount / OTE | Dealing range from the most recent external swings. Equilibrium = 50 %. OTE = 62–79 % retracement, plotted as a band. Longs only in discount/OTE, shorts only in premium/OTE (`pdStrict`). |

### Tier 3 — institutional tools

| Framework item | Implementation |
| --- | --- |
| Session VWAP | Cumulative `hlc3 × volume`, reset daily. |
| Anchored VWAP | Optional, user-set anchor timestamp. |
| Volume profile | **PROXY** (labelled everywhere): a rolling-window profile that bins bar volume at `hlc3` into `vpBins` buckets and derives POC, VAH, VAL and a nearest-HVN. Pine has no access to true per-price traded volume; this is a deterministic approximation, recomputed every `vpEvery` bars to keep it cheap. |
| "Triple threat" cluster | VWAP **and** a profile node **and** a swing/liquidity level all within `clusterAtr × ATR` of the entry ⇒ cluster confirmed (`clusterCount` 3/3). |
| GEX | **PROXY / manual**: six user levels, each tagged positive or negative gamma, plotted and distance-tested. Positive gamma = pinning: a `+γ` level between entry and the runner target **caps the R measurement** at that level, and can optionally block entries outright (`gexPinBlock`). Negative gamma = expansion, left uncapped. No fabricated auto-downloaded dataset. |

### Tier 4 — macro / AMD

| Framework item | Implementation |
| --- | --- |
| PO3 / AMD | Accumulation = the `0400-0830` pre-market range. Manipulation = a Judas raid of that range inside `0830-0930` that closes back inside. Distribution is only *inferred after* a CHoCH or displacement in the opposite direction. State shown on the dashboard; `po3Require` can make agreement mandatory. |
| Economic calendar | **Manual** event slots (CPI, NFP, FOMC, GDP, PPI, Other) with configurable no-trade minutes before/after. The strategy will not enter during a lockout, and `evtReArm` additionally requires a fresh BOS/CHoCH after the window before trading resumes. The release spike itself is never traded. |

---

## Scoring engine — resolving the source contradiction

The source framework says both "all required before triggering" and "missing 3+ = blocked".
That is resolved as:

* **Hard blockers** (Tier 1 + critical execution logic) — any one of these invalidates
  the setup regardless of score: HTF bias missing/neutral/opposed, no kill zone, no
  valid sweep, no displacement + retest structure, no defined invalidation, less than
  the minimum R, event lockout, plus the optional strict gates.
* **Point-based scoring** for the remaining confluences, on the 10-point checklist:

  1. HTF narrative confirmed 2. Kill zone active 3. Liquidity sweep labelled
  4. Displacement present 5. SMT confirmed 6. Premium/discount + OTE
  7. VWAP/profile cluster 8. GEX nearby and factored 9. Invalidation defined
  10. Minimum R confirmed

* Checks that are genuinely unavailable (SMT disabled for GC/SI, no GEX levels entered,
  VWAP+profile disabled) **drop out of the denominator** and the score is redistributed
  proportionally back onto the 10-point scale.
* Defaults: **PASS needs ≥ 8/10**, missing **≥ 3** points ⇒ **BLOCKED**, otherwise
  **WATCHLIST**. `strictMode` additionally requires SMT + cluster; `needTier2` requires
  at least 3 of the 4 Tier-2 structure confluences.

The dashboard prints every row, the live score, the state, and the blocking reason.

---

## Entry / exit / risk (strategy)

* **Entry** — limit order at the retest zone (FVG/OB boundary, position inside the zone
  set by `zoneEntryPct`) after displacement + CHoCH. `entryMode` can be switched to a
  market order on the confirmed retest close instead.
* **Stop** — beyond the protected swing that produced the displacement, plus an ATR
  buffer (`atrStopBuf`).
* **Targets** — TP1 at the next *internal* liquidity pool (partial %, configurable),
  TP2/runner at the next *valid external* pool. A minimum-R hard filter (`minRR`,
  default 2.0) must pass before any order is allowed.
* **Sizing** — risk % of equity; contracts derived from stop distance and
  `syminfo.pointvalue`. If one contract would exceed the risk budget the setup is
  skipped (unless `forceMinQty` is on).
* **One attempt per idea** — after an order is submitted for an idea, no re-entry on
  that same liquidity/HTF setup until a **new sweep + displacement** creates a new idea.
* **Order hygiene** — resting limits are cancelled when the idea expires, the kill zone
  closes, or an event lockout begins; optional end-of-session flatten.
* The plan (entry/stop/TP1/TP2) is **frozen at submission time**, not re-derived at fill.

Commission and slippage live in the `strategy()` declaration (Pine requires constants
there) at `$2.50 / contract` and `2 ticks`. Adjust per instrument in *Strategy Properties*.

---

## Instrument presets

| Symbol | SMT pair | Notes |
| --- | --- | --- |
| `CME_MINI:ES1!` | `CME_MINI:NQ1!` | SMT on |
| `CME_MINI:NQ1!` | `CME_MINI:ES1!` | SMT on |
| `AMEX:SPY` | `NASDAQ:QQQ` | SMT on |
| `NASDAQ:QQQ` | `AMEX:SPY` | SMT on |
| `COMEX:GC1!` | — | **SMT off by default.** Optionally pair against `TVC:DXY` with *Inverse correlation* ON; the checklist point is redistributed when off. |
| `COMEX:SI1!` | — | Same as GC. |

Execution timeframe: 15m / 5m / 1m. Bias timeframes stay Monthly / Weekly / Daily / 4H.

---

## Alerts

Indicator (`alertcondition`, JSON messages with `{{plot("…")}}` placeholders):
PASS long, PASS short, retest trigger, score threshold crossed, kill zone activation,
SMT bullish, SMT bearish, liquidity sweep.

Strategy: `alert()` with the same JSON schema plus `alert_message` on every entry and
exit order, ready for webhook automation.

```json
{"schema":"openclaw-ict/1","event":"pass_long","dir":"long","symbol":"…","tf":"…",
 "score":"9","entry":"…","stop":"…","tp1":"…","tp2":"…","rr":"…","time":"…"}
```

---

## Honest limitations (labelled `PROXY` in code)

1. **Volume profile** — binned bar volume, not exchange per-price volume.
2. **GEX** — manual levels only; Pine cannot fetch dealer gamma.
3. **Economic calendar** — manual event times; Pine has no calendar feed.
4. **SMT protected swing** — drawn on the primary chart, though the swing that held
   belongs to the correlated instrument.
5. Session-based logic (kill zones, PO3, VWAP reset) assumes an intraday chart.
