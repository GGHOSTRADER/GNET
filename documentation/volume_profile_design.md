# Volume Profile Pipeline
> **What:** Full design and API reference for `volume_profile.py` — stateful session volume profile, O(1) per bar, with POC and Value Area computed from Redis bar stream.

**File:** `feat_files/volume_profile.py`
**Run:** `python -m feat_files.volume_profile`

---

## What It Does

Reads bar data from Redis1 in real time and maintains a stateful Volume Profile for the current trading session. On every bar close it emits an updated snapshot.

Data arriving from Redis is already validated at ingestion (`tcp_to_redis_connection.py` + `bar_codec.py`). This file just reads and casts.

Session resets automatically when the date changes (new trading day).

---

## Design: Stateful Incremental Profile

Grid is pre-allocated at session start (`range_ticks + 1` zeros) centered on the first bar's close. Each subsequent bar does a single:

```python
profile[index] += volume   # one C op, no rebuild ever
```

Grid extension only happens if price breaks outside the pre-allocated range. Extension adds 15% of `range_ticks` in the direction of the break via `np.concatenate`. On a typical session with 400 ticks pre-allocated this almost never fires. Even on trend days the 15% buffer absorbs most moves.

---

## Inputs

**Source:** Redis Stream `validated_bar` — `127.0.0.1:6381`
**Parser:** `parse_xread_to_bars()` from `netwo_files/bar_codec.py` (decode + cast only)

### From each Bar

| Field | Type | Description |
|---|---|---|
| `bar.close` | float | Price where volume is assigned (single price per bar) |
| `bar.up` | int | Market buy volume |
| `bar.down` | int | Market sell volume |
| `bar.symbol` | str | Ticker symbol |
| `bar.date` | int | Session date (YYYMMDD, years since 1900) |
| `bar.bar_num` | int | Bar sequence number |

### Launch Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `tick_size` | float | `0.25` | Price increment per level (e.g. 0.25 for ES futures) |
| `range_ticks` | int | `400` | Ticks to pre-allocate at session start. 400 ticks @ 0.25 = ±50 points around open |

**From CLI:**
```bash
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600
```

**From code:**
```python
stream_volume_profile(tick_size=0.25, range_ticks=600)
```

---

## Outputs — `VolumeProfileResult`

Emitted once per bar.

| Field | Type | Description |
|---|---|---|
| `symbol` | str | Ticker symbol |
| `date` | int | Session date |
| `bar_num` | int | Latest bar number |
| `tick_size` | float | Price grid resolution used |
| `range_ticks` | int | Initial pre-allocated ticks |
| `price_levels` | ndarray (L,) | Tick-spaced price grid |
| `volume_at_level` | ndarray (L,) | Volume at each level (parallel to price_levels) |
| `poc_price` | float | Point of Control — price level with most volume |
| `poc_volume` | float | Volume at the POC level |
| `value_area_low` | float | VAL — lower bound of 70% value area |
| `value_area_high` | float | VAH — upper bound of 70% value area |
| `total_volume` | float | Total session volume so far |
| `n_bars` | int | Bars accumulated this session |
| `extensions` | int | How many times the grid was extended this session |

---

## Storage

All state held in memory in `_SessionState`. No persistence. Reset on date change.

| Field | Type | Description |
|---|---|---|
| `profile` | ndarray | Live profile array (pre-allocated) |
| `min_price` | float | Price corresponding to index 0 |
| `tick_size` | float | Price increment |
| `range_ticks` | int | Original range for extension calculation |
| `extensions` | int | Extension count |

---

## Grid Extension Rules

Extension is triggered when `bar.close` falls outside the current grid bounds.

```
extension_ticks = max(1, int(range_ticks * 0.15))
                = max(1, int(400 * 0.15))
                = 60 ticks  (default)

n_add = max(extension_ticks, gap_in_ticks)
```

> `n_add` guarantees the new bar always fits even if the price jump exceeds `extension_ticks`.

| Direction | Action |
|---|---|
| Broke below floor | Prepend zeros, `min_price` shifts down by `n_add * tick_size` |
| Broke above ceiling | Append zeros |

### Example

```
range_ticks = 400, tick_size = 0.25
Initial grid:  4950.00 → 5050.00  (400 ticks = 100 price points)

Price breaks above 5050.00:
  extension = 60 ticks = 15.00 points
  New ceiling: 5065.00
```

---

## Function Summary

### Adapter — Infrastructure

**`stream_bars_from_redis(block_ms, count, start_id)`**
Connects to Redis1, blocking XREAD loop, parses via `parse_xread_to_bars()`. No re-validation. Yields one typed Bar at a time.

---

### Domain — Stateless reads

**`_find_poc(profile, price_levels) → (poc_price, poc_volume)`**
`np.argmax` on profile array.

**`_find_value_area(profile, price_levels, pct=0.70) → (val, vah)`**
`np.argsort` + `np.cumsum`. Selects levels by volume descending until 70% of total volume is covered. VAL/VAH = min/max price of selected levels.

---

### Session State

**`_init_session(bar, tick_size, range_ticks) → _SessionState`**
Pre-allocates profile array of `range_ticks + 1` zeros centered on first close. Called once per session.

**`_update(state, bar) → None`**
Incremental update. O(1) in common case:
1. Snap close to nearest tick
2. Compute integer index
3. If within grid: `profile[index] += volume`
4. If outside grid: extend via `np.concatenate`, then add volume

**`_snapshot(state) → VolumeProfileResult`**
Derives `price_levels` from `min_price + np.arange * tick_size`. Calls `_find_poc` and `_find_value_area`. Returns a copy of the profile.

---

### Application

**`stream_volume_profile(tick_size, range_ticks, block_ms, count, start_id)`**
Main generator. Manages session lifecycle, calls `_init_session` on new day, calls `_update` + `_snapshot` on every bar.

**`run_print_loop(tick_size, range_ticks)`**
Smoke runner. Prints one line per bar including grid size and extension count. Accepts CLI flags via `argparse` when run as `__main__`.

---

## Ports / Dependencies

| Item | Value |
|---|---|
| Redis host | `127.0.0.1:6381` (Docker container) |
| Stream | `validated_bar` |
| Dependencies | `redis`, `numpy` |
