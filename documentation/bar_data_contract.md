# Raw Data Contract
> **What:** Defines all 11 fields sent from TradeStation to Python via TCP — field names, types, calculations, and invariants that must always hold.

**Source:** TradeStation → Python TCP Server via `BarBridge.dll`
**Transport:** 11 fields as CSV over TCP

---

## Fields

| #   | Field      | Type   | Description                              |
| --- | ---------- | ------ | ---------------------------------------- |
| 1   | Symbol     | string | Ticker symbol                            |
| 2   | Date       | int    | Date in YYYMMDD (years since 1900)       |
| 3   | Time       | int    | Seconds since midnight                   |
| 4   | Open       | float  | Price at bar start                       |
| 5   | High       | float  | Highest price in interval                |
| 6   | Low        | float  | Lowest price in interval                 |
| 7   | Close      | float  | Last price in interval                   |
| 8   | Up         | int    | Market buy orders                        |
| 9   | Down       | int    | Market sell orders                       |
| 10  | VWAP       | float  | Volume Weighted Average Price since open |
| 11  | Bar Number | int    | Bar sequence number                      |

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

### 4 — Open
- **Type:** Double (float)
- **Invariants:** `open > 0`, `isinstance(open, float)`

### 5 — High
- **Type:** Double (float)
- **Invariants:** `open <= high`, `high != 0`, `isinstance(high, float)`

### 6 — Low
- **Type:** Double (float)
- **Invariants:** `open >= low`, `low != 0`, `isinstance(low, float)`

### 7 — Close
- **Type:** Double (float)
- **Invariants:** `low <= close <= high`, `close != 0`, `isinstance(close, float)`

### 8 — Up
- **Type:** Integer
- **Meaning:** Market buy orders
- **Invariants:** `up >= 0`, `isinstance(up, int)`

### 9 — Down
- **Type:** Integer
- **Meaning:** Market sell orders
- **Invariants:** `down >= 0`, `isinstance(down, int)`

### 10 — VWAP
- **Type:** Double (float)
- **Meaning:** Volume Weighted Average Price since market open
- **Components:** Volume = `Up + Down`, uses High, Low, Close
- **Formula:** `Sum(((high+low+close)/3) * (Up+Down)) / Sum(Up+Down)` *(calculated in TradeStation, not here)*
- **Invariants:** `vwap >= 0`, `isinstance(vwap, float)`

### 11 — Bar Number
- **Type:** Integer
- **Invariants:** `bar_number[x] > bar_number[x-1]`, `bar_number >= 0`, `isinstance(bar_num, int)`
