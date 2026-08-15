import pandas as pd
from pipeline_paths import FEATURES_FILE

df = pd.read_csv(FEATURES_FILE)
df["Date/Time"] = pd.to_datetime(df["Date/Time"])
df["hour"] = df["Date/Time"].dt.hour

print(f"Total trades: {len(df):,}")
print()
print(f"{'Hour':<8} {'Total':>7} {'Long':>7} {'Short':>7} {'Win%':>6}")
print("-" * 38)
for h in sorted(df["hour"].unique()):
    sub = df[df["hour"] == h]
    lo  = (sub["direction"] ==  1).sum()
    sh  = (sub["direction"] == -1).sum()
    wr  = sub["Label"].mean() * 100
    print(f"  {h:02d}:00  {len(sub):>7,} {lo:>7,} {sh:>7,} {wr:>5.1f}%")
