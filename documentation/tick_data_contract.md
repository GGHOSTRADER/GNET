## Fields

| #   | Field      | Type   | Description                        |
| --- | ---------- | ------ | ---------------------------------- |
| 1   | Symbol     | string | Ticker symbol                      |
| 2   | Date       | int    | Date in YYYMMDD (years since 1900) |
| 3   | Time       | int    | Seconds since midnight             |
| 4   | High       | float  | Highest price in interval          |
| 5   | Low        | float  | Lowest price in interval           |
| 6   | Up         | int    | Market buy orders                  |
| 7   | Down       | int    | Market sell orders                 |
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
- **Invariants:** `open <= high`, `high != 0`, `isinstance(high, float)`

### 5 — Low
- **Type:** Double (float)
- **Invariants:** `open >= low`, `low != 0`, `isinstance(low, float)`, High  == Low


### 6 — Up
- **Type:** Integer
- **Meaning:** Market buy orders
- **Invariants:** `up >= 0`, `isinstance(up, int)`

### 7 — Down
- **Type:** Integer
- **Meaning:** Market sell orders
- **Invariants:** `down >= 0`, `isinstance(down, int)`


### 8 — Bar Number
- **Type:** Integer
- **Invariants:** `bar_number[x] > bar_number[x-1]`, `bar_number >= 0`, `isinstance(bar_num, int)`


