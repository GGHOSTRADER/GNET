| Feature                   | Description                                                                      |
|---------------------------|----------------------------------------------------------------------------------|
| parkinson_vol_{5,15,30}   | Volatility estimated from High/Low range — more efficient than close-to-close vol|
| ofi_{5,15,30}             | Order Flow Imbalance — net buy vs sell volume (Up - Down) over rolling window    |
| volume_percentile         | Where current volume ranks vs last 60 bars (0–1)                                 |
| volume_momentum           | Volume % change over last 5 bars                                                 |
| amihud_illiquidity        | Price impact per unit volume — high = illiquid, moves easily                     |
| vwap_distance             | How far price is from VWAP, normalized by ATR                                    |
| minutes_since_open        | Minutes elapsed since 09:30 open                                                 |
| is_first_last_30min       | Binary flag — 1 if in first or last 30min of session                             |

Target: rv_15m_fwd — realized volatility over next 15 bars (forward-looking, scaled by train median)