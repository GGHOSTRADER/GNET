# Custom primary strategies: human guide

## What the primary receiver accepts

The primary receiver is intended to capture a strategy's reviewed positions and
the bars that produced them. It is not intended to understand every trading rule
inside TradeStation.

The generic trade record is stable across strategy families:

- strategy identity and source revision;
- signal-bar reference;
- side and quantity;
- open or closed state;
- entry and exit bar references;
- reported entry and exit times and prices;
- gross P&L, declared costs and net P&L.

The strategy descriptor carries the strategy family and its inputs. A strategy
with seven inputs does not need seven new broker columns. Its inputs belong in an
extensible parameter object, for example:

```json
{
  "strategy_id": "rsi-vwap-primary",
  "logic_family": "custom",
  "logic_revision": "rev01",
  "parameters": {
    "rsi_length": 14,
    "vwap_filter": true,
    "entry_threshold": 55,
    "session_filter": "regular",
    "stop_ticks": 8,
    "target_ticks": 12,
    "hold_bars": 20
  }
}
```

The broker also stores a canonical settings fingerprint. That fingerprint binds
the displayed inputs to the exact export and prevents a review from being reused
with different settings.

## Current release limitation

The currently installed primary validator is still the original MA contract. It
expects `rule_family=ma_cross`, fixed MA parameters and a single full-size
position with one complete exit. The Command Center currently shows the strategy
ID and settings fingerprint; it does not yet render an arbitrary parameter list.

Therefore, do not label an RSI, VWAP, order-flow or multi-trigger strategy as
`ma_cross`. It may be stored privately as a pending custom source, but it is not
eligible for the MA-specific automatic rule check or training mapping.

## What changes require a new implementation

| Change | Contract change? | Reason |
|---|---:|---|
| Add an input while keeping the same position model | Usually no, after extensible parameters are enabled | The input is metadata in `parameters` |
| Add a new rule family | Yes, a family adapter or reviewed custom family | The broker cannot independently reproduce the rule yet |
| Reverse from long to short | Yes unless the current position adapter explicitly supports it | Position transitions and signal joins change |
| Pyramid entries | Yes | Multiple entry lots and quantities must be represented |
| Partial exits or partial fills | Yes | One entry/one exit rows are insufficient |
| Multiple simultaneous positions | Yes | Position identity and occupancy rules change |
| New bar fields already allowed by the bar contract | No broker release if the schema already supports them | The bar receiver is transport-oriented |
| New required fields or validation rules | Yes | The broker and schemas must agree on a new version |

## Scaffold workflow

Use the primary strategy scaffold as the starting point. It contains the export,
metadata, session, identity and trade-ledger code. The user or agent edits only
the marked strategy-logic block and declares the strategy inputs in the scaffold's
parameter section.

The scaffold must fail closed while its logic is empty. It must not publish a
zero-trade file that looks like a completed strategy implementation.

After implementation:

1. Verify the EasyLanguage source in TradeStation.
2. Preserve the actual strategy inputs and chart settings.
3. Run the synthetic export acceptance check.
4. Recalculate the research chart and wait for the closed-export receipt.
5. Open the received source in the Command Center and run automatic validation.
6. Review the generated strategy family, input manifest and execution shape.
7. Promote the exact source fingerprint only after the appropriate adapter and
   policy are reviewed.

## What the Command Center should display

For every imported primary source, the detail panel should show:

- full strategy name and optional nickname;
- strategy family and logic revision;
- every declared input as name, type, value and source (`declared` or `automatic`);
- source fingerprint and settings fingerprint;
- position model: single, reverse, pyramid, partial or multi-position;
- trade population and validation status;
- capabilities allowed by the selected adapter.

The seven inputs are read from the strategy descriptor written by the exporter,
not by scraping EasyLanguage source or reading the private TradeStation chart.
The agent can verify that the descriptor matches the source's declared inputs;
the broker keeps the descriptor bound to the source and bundle hashes.

## Human and administrator boundary

The ordinary user may create and test a custom strategy in TradeStation. The
agent may prepare its metadata and review proposal. A protected broker release
or adapter is required when the execution shape or validation family changes.
The administrator activates that reviewed release and source fingerprint. No
password is entered into the Command Center or sent to the agent.
