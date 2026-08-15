import pandas as pd
from pipeline_paths import FEATURES_FILE

df = pd.read_csv(FEATURES_FILE)
regimes = [
    "regime_late_expansion",
    "regime_mid_expansion",
    "regime_early_contraction",
    "regime_early_expansion",
    "regime_late_contraction",
]

print(f"Total trades: {len(df):,}")
print()
print(f"{'Regime':<28} {'Total':>7} {'Long':>7} {'Short':>7} {'Win%':>6}")
print("-" * 58)
for r in regimes:
    sub = df[df[r] == 1]
    lo  = (sub["direction"] ==  1).sum()
    sh  = (sub["direction"] == -1).sum()
    wr  = sub["Label"].mean() * 100
    print(f"  {r:<26} {len(sub):>7,} {lo:>7,} {sh:>7,} {wr:>5.1f}%")

unknown = df[(df[regimes] == 0).all(axis=1)]
print(f"  {'unknown':<26} {len(unknown):>7,}")
