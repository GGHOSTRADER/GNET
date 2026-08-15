import pandas as pd
from pipeline_paths import FEATURES_FILE

df = pd.read_csv(FEATURES_FILE)
df["Date/Time"] = pd.to_datetime(df["Date/Time"])

market_open  = df["Date/Time"].dt.normalize() + pd.Timedelta("09:30:00")
market_close = df["Date/Time"].dt.normalize() + pd.Timedelta("16:00:00")
df["is_rth"] = (df["Date/Time"] >= market_open) & (df["Date/Time"] < market_close)

print(f"Total trades: {len(df):,}")
print()
print(f"{'Session':<8} {'Total':>7} {'Long':>7} {'Short':>7} {'Win%':>6}")
print("-" * 38)
for is_rth, label in [(True, "RTH"), (False, "ETH")]:
    sub = df[df["is_rth"] == is_rth]
    lo  = (sub["direction"] ==  1).sum()
    sh  = (sub["direction"] == -1).sum()
    wr  = sub["Label"].mean() * 100
    print(f"  {label:<6} {len(sub):>7,} {lo:>7,} {sh:>7,} {wr:>5.1f}%")
