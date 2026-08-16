# Volume Profile Pipeline
> **What:** Full design and API reference for `volume_profile.py` — stateful session volume profile, O(1) per bar, with POC and Value Area computed from Redis bar stream.

**File:** `feat_files/volume_profile.py`
**Run:** `python -m feat_files.volume_profile`

---

## What It Does

Reads tick data from Redis1 in real time and maintains a stateful Volume Profile for the current trading session. The profile updates on every tick. The current gate emits a snapshot for every tick timestamped in the final second, so an interval may contain multiple snapshots.

Data arriving from Redis is already validated at ingestion (`tick_validator.py` + `tick_codec.py`). This file just reads and casts.

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

**Source:** Redis Stream `tick_data_validated` — `127.0.0.1:6381`
**Parser:** `parse_xread_to_ticks()` from `netwo_files/tick_codec.py` (decode + cast only)

### From each Tick

| Field | Type | Description |
|---|---|---|
| `tick.high` | float | Price (high == low for tick data — single price point) |
| `tick.up` | int | Market buy volume at this tick |
| `tick.down` | int | Market sell volume at this tick |
| `tick.symbol` | str | Ticker symbol |
| `tick.date` | int | Session date (YYYYMMDD) |
| `tick.time_s` | int | Seconds since midnight — drives the snapshot gate (`time_s % snapshot_interval_s == snapshot_interval_s - 1`) |
| `tick.bar_num` | int | Tick sequence number |

### Launch Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `tick_size` | float | `0.25` | Price increment per level (e.g. 0.25 for ES futures) |
| `range_ticks` | int | `400` | Ticks to pre-allocate at session start. 400 ticks @ 0.25 = ±50 points around open |
| `snapshot_interval_s` | int | `30` | Interval length. Every tick satisfying `tick.time_s % snapshot_interval_s == snapshot_interval_s - 1` fires a snapshot. Set to match the live bar size. |

**From CLI:**
```bash
python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30
```

**From code:**
```python
stream_volume_profile(tick_size=0.25, range_ticks=600, snapshot_interval_s=30)
```

---

## Snapshot Cadence

`_update()` runs on every tick — O(1), just `profile[index] += volume`. `_snapshot()` (POC, Value Area, and all derived features below) only runs when `tick.time_s % snapshot_interval_s == snapshot_interval_s - 1`.

**Why 1 second before bar close, not exactly at close:** the profile is session-cumulative, so missing the last second of ticks is statistically negligible — POC/VA/entropy etc. are dominated by the full session's accumulated volume. Snapshotting 1s early guarantees the row is already sitting in `features_volume_profile` before `features_transformer` fires for that bar, so `consolidator.py`'s `xrevrange(count=1)` reliably grabs the right one instead of racing.

**Why this also solves the compute problem:** every derived feature (POC, VA, entropy, kurtosis, `vol_above_poc_ratio`, ...) requires an O(L) or O(L log L) pass over the profile array — numpy vectorizes that in microseconds regardless of array size (L ≈ 400–1000). The savings from gating isn't per-call cost, it's call *frequency*: once per 30s instead of once per tick (potentially hundreds of times per second).

---

## Outputs — `VolumeProfileResult`

Emitted on every qualifying tick in the final second; multiple records per interval are possible.

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
| `poc_distance` | float | `(current_price - poc_price) / tick_size` — signed distance from POC, in ticks |
| `poc_concentration` | float | `poc_volume / total_volume` — peaked vs diffuse |
| `va_width` | float | `(value_area_high - value_area_low) / tick_size` |
| `va_position` | float | `(current_price - VAL) / (VAH - VAL)` — 0=at VAL, 1=at VAH, outside [0,1]=outside VA |
| `vol_above_poc_ratio` | float | Fraction of `total_volume` traded above `poc_price` |
| `profile_entropy` | float | `-Σ p·log(p)` over the volume distribution — low=concentrated, high=diffuse |
| `profile_kurtosis` | float | Excess kurtosis of the volume distribution — peakedness |
| `poc_migration` | float | `(poc_price_now - poc_price_prev_bar) / tick_size` — POC drift since last snapshot, in ticks |

`current_price` is the most recent tick's price (`_SessionState.last_price`) at the moment the snapshot fires.

---

## What Is Stateful

`_SessionState` is the single live object that accumulates data across all ticks in a trading session. It is created once per day by `_init_session` and mutated in-place by every `_update` call.

| Field | Type | Stateful? | Description |
|---|---|---|---|
| `profile` | `ndarray (L,)` | **Yes** | The core accumulator. `profile[i]` holds total volume traded at `price_levels[i]` so far this session. Grows via `np.concatenate` only on boundary break. |
| `min_price` | `float` | **Yes** | Price corresponding to index 0. Shifts down when grid extends below floor. |
| `tick_size` | `float` | No | Fixed at session init. |
| `range_ticks` | `int` | No | Fixed at session init. Used to compute 15% extension size. |
| `symbol` | `str` | No | Set at init from first tick. |
| `date` | `int` | No | Set at init. Session resets when this changes. |
| `bar_num` | `int` | **Yes** | Updated to the latest tick's bar_num on every `_update`. |
| `n_bars` | `int` | **Yes** | Incremented by 1 on every `_update`. |
| `extensions` | `int` | **Yes** | Incremented each time the grid is extended. |
| `last_price` | `float` | **Yes** | Most recent tick's snapped price. Used as `current_price` for `poc_distance` / `va_position` at snapshot time. |
| `prev_poc_price` | `float \| None` | **Yes** | POC price as of the previous snapshot. `None` until the first snapshot fires. Used to compute `poc_migration`. |

**What is NOT in state:** POC, Value Area, and all other derived features (entropy, kurtosis, concentration, etc.) are not stored — they are derived fresh on every `_snapshot` call directly from `profile` using `np.argmax`, `np.argsort`, and `_compute_derived_features`. The full `profile` array remains the only source of truth for the distribution itself. The one exception is `prev_poc_price`, which `_snapshot` persists back into state purely so the *next* snapshot can compute `poc_migration`.

**Lifetime:** state lives in Python heap for the duration of the session. No disk persistence. On date change `stream_volume_profile` replaces the old `_SessionState` with a fresh one — previous session data is discarded.

---

## Storage

All state held in memory in `_SessionState`. No persistence. Reset on date change.

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

**`_compute_derived_features(profile, price_levels, poc_price, poc_volume, value_area_low, value_area_high, total_volume, current_price, tick_size, prev_poc_price) → dict`**
Pure. Computes `poc_distance`, `poc_concentration`, `va_width`, `va_position`, `vol_above_poc_ratio`, `profile_entropy`, `profile_kurtosis`, `poc_migration`. All distance-like features are expressed in ticks (divided by `tick_size`). Handles zero-volume / single-level edge cases (e.g. `va_position` defaults to `0.5` when `va_range == 0`).

---

### Session State

**`_init_session(bar, tick_size, range_ticks) → _SessionState`**
Pre-allocates profile array of `range_ticks + 1` zeros centered on first close. Sets `last_price` to the first tick's price and `prev_poc_price = None`. Called once per session.

**`_update(state, bar) → None`**
Incremental update. O(1) in common case:
1. Snap close to nearest tick
2. Compute integer index
3. If within grid: `profile[index] += volume`
4. If outside grid: extend via `np.concatenate`, then add volume
5. Update `state.last_price` to the snapped price

**`_snapshot(state) → VolumeProfileResult`**
Derives `price_levels` from `min_price + np.arange * tick_size`. Calls `_find_poc`, `_find_value_area`, and `_compute_derived_features`. Updates `state.prev_poc_price = poc_price` for the next call. Returns a copy of the profile plus all derived features.

---

### Application

**`stream_volume_profile(tick_size, range_ticks, snapshot_interval_s, block_ms, count, start_id)`**
Main generator. Manages session lifecycle, calls `_init_session` on new day, and calls `_update` on every tick. It calls `_snapshot` whenever `tick.time_s % snapshot_interval_s == snapshot_interval_s - 1`; every tick in that second qualifies.

**`run_publish_loop(tick_size, range_ticks, snapshot_interval_s)`**
Main loop. Pushes each `VolumeProfileResult` to `features_volume_profile` via `xadd` and prints one line per bar including grid size, extension count, and all derived features. Accepts CLI flags via `argparse` when run as `__main__`.

---

## Ports / Dependencies

| Item | Value |
|---|---|
| Redis host | `127.0.0.1:6381` (Docker container) |
| Stream | `validated_bar` |
| Dependencies | `redis`, `numpy` |
