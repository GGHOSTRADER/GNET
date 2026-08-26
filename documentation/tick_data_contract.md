# Tick Data Contract

> **What:** Defines the eight TradeStation tick fields and the transport-only
> timing metadata carried through the live Redis pipeline.

## Fields

| #   | Field      | Type   | Description                        |
| --- | ---------- | ------ | ---------------------------------- |
| 1   | Symbol     | string | Ticker symbol                      |
| 2   | Date       | int    | Date in YYYMMDD (years since 1900) |
| 3   | Time       | int    | Seconds since midnight             |
| 4   | High       | float  | Tick execution price               |
| 5   | Low        | float  | Tick execution price; equals High  |
| 6   | Up         | int    | TradeStation-classified uptick volume proxy |
| 7   | Down       | int    | TradeStation-classified downtick volume proxy |
| 8   | Bar Number | int    | Bar sequence number                |

---

## Field Contracts

### 1 — Symbol
- **Type:** String pointer
- **Invariants:** `symbol != null`, `type == string`

### 2 — Date
- **Type:** Integer
- **Format:** `YYYMMDD` where `YYY = years since 1900`
- **Example:** April 12 of 2026 = `1260412`
- **Invariants:** `date > 1260000`, `1 ≤ MM ≤ 12`, `1 ≤ DD ≤ 31`

### 3 — Time in Seconds
- **Type:** Integer
- **Calculation:**
```
HOUR   * 3600 = X
MINUTE * 60   = Y
SECOND * 1    = Z
TOTAL SECONDS = X + Y + Z
```
- **Note:** HOUR 0 = Midnight

### 4 — High
- **Type:** Double (float)
- **Invariants:** `high > 0`, `high == low`, `isinstance(high, float)`

### 5 — Low
- **Type:** Double (float)
- **Invariants:** `low > 0`, `low == high`, `isinstance(low, float)`


### 6 — Up
- **Type:** Integer
- **Meaning:** TradeStation-classified uptick volume; not true aggressor-side volume without historical bid/ask
- **Invariants:** `up >= 0`, `isinstance(up, int)`

### 7 — Down
- **Type:** Integer
- **Meaning:** TradeStation-classified downtick volume; not true aggressor-side volume without historical bid/ask
- **Invariants:** `down >= 0`, `isinstance(down, int)`


### 8 — Bar Number
- **Type:** Integer
- **Invariants:** `bar_number[x] > bar_number[x-1]`, `bar_number >= 0`, `isinstance(bar_num, int)`

The monotonic sequence is local to the active TradeStation chart series. A
chart reload can reset `CurrentBar`; restart the Tick Validator pane to reset
its in-memory baseline when that happens.

---

## Transport Timing Metadata

These fields are Redis adapter metadata, not members of the canonical `Tick`
domain object:

| Stream | Field | Meaning |
|---|---|---|
| `tick_data_raw` | `tcp_received_ns` | Local wall-clock time when the TCP server completed a newline-delimited tick |
| `tick_data_validated` | `tcp_received_ns` | Propagated ingress timestamp |
| `tick_data_validated` | `validator_received_ns` | Local wall-clock time when validation began |

Redis stream IDs provide raw, validated, and VP publication time. The passive
`netwo_files.tick_pipeline_profiler` joins exact tick identities to report hop
and total p50/p95/p99/max latency without changing canonical VP math.

