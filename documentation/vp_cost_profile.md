# Volume-Profile Live Cost Profile

The canonical VP engine was profiled on 2026-08-25 using real prepared tick
Parquets from the lowest-, median-, and highest-activity historical sessions.
The reproducible command is:

```powershell
python -m training_mlp.profile_vp_cost
```

Results are written to
`historical_vp/features/profile/vp_cost_profile.json`. Historical TradeStation
ticks have whole-second timestamps, so the three-preview policy uses the 25th,
60th, and 90th percentile ordered ticks within each final second as proxies for
fractional wall-clock gates. Snapshot costs are real; exact historical
millisecond gate placement cannot be reconstructed.

## Measured Results

| Session | Ticks | Final-second ticks | Update only | One commit | Three previews + commit | Every final tick |
|---|---:|---:|---:|---:|---:|---:|
| 2026-04-03 | 56,880 | 1,673 | 0.136 s | 0.207 s | 0.334 s | 0.400 s |
| 2026-04-24 | 1,020,286 | 32,104 | 2.113 s | 2.466 s | 3.105 s | 7.372 s |
| 2026-06-09 | 1,878,587 | 62,247 | 3.858 s | 4.349 s | 5.548 s | 20.336 s |

On the highest-activity session, one snapshot cost approximately 0.265 ms. Its
final-second tick distribution was:

| Statistic | Ticks in final second | Approximate snapshot CPU |
|---|---:|---:|
| Median | 10 | 2.6 ms |
| 95th percentile | 117 | 31 ms |
| 99th percentile | 185 | 49 ms |
| Maximum | 4,158 | 1,101 ms |

The profile update itself averaged roughly 2 microseconds per tick in the
highest-activity replay. The risk is therefore not ingesting every tick; it is
running the full 32-feature snapshot for every tick during a burst. A bounded
three-preview policy plus one interval-history advancement reduces the worst
observed interval from roughly 1.1 seconds of snapshot work to roughly 1 ms.

## Decision Still Required

Keep updating the canonical profile on every tick, but bound snapshot
calculation/publication to fixed fractional wall-clock gates during the final
second. Candidate gates discussed are `29.250`, `29.600`, and `29.900`. The
historical data supports throttling, but the exact gates and live scheduling
implementation remain pending approval.
