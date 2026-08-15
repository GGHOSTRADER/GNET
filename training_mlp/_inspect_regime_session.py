import pandas as pd
from pipeline_paths import FEATURES_FILE

df = pd.read_csv(FEATURES_FILE)
df["Date/Time"] = pd.to_datetime(df["Date/Time"])

market_open  = df["Date/Time"].dt.normalize() + pd.Timedelta("09:30:00")
market_close = df["Date/Time"].dt.normalize() + pd.Timedelta("16:00:00")
df["session"] = ((df["Date/Time"] >= market_open) & (df["Date/Time"] < market_close)).map({True: "rth", False: "eth"})

regimes = [
    ("regime_late_expansion",    "late_expansion"),
    ("regime_mid_expansion",     "mid_expansion"),
    ("regime_early_contraction", "early_contraction"),
    ("regime_early_expansion",   "early_expansion"),
    ("regime_late_contraction",  "late_contraction"),
]

print(f"Total: {len(df):,}")
print()
print(f"{'Regime + Session':<35} {'Total':>7} {'Win%':>6}")
print("-" * 52)
for col, label in regimes:
    for session in ["rth", "eth"]:
        sub = df[(df[col] == 1) & (df["session"] == session)]
        wr  = sub["Label"].mean() * 100 if len(sub) > 0 else 0
        print(f"  {label}_{session:<6}  {len(sub):>7,}  {wr:>5.1f}%")
    print()
