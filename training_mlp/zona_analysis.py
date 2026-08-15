"""
zona_analysis.py
================
Exploratory analysis on the enriched dataset.
Run after zona_backtest.py has generated df_enriched.csv.

    cd training_mlp
    python zona_analysis.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from pathlib import Path

ENRICHED_FILE = Path("strategies/zona_strat/processed/df_enriched.csv")
REPORTS_DIR   = Path("strategies/zona_strat/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(ENRICHED_FILE)
df["entry_ts"] = pd.to_datetime(df["entry_ts"])
df["hour"]     = df["entry_ts"].dt.hour
df["pnl_net"]  = df["pnl"] - 3   # commission per trade (MNQ = $3)

REGIME_MAP = {
    "regime_late_expansion":    "Late Expansion",
    "regime_mid_expansion":     "Mid Expansion",
    "regime_early_contraction": "Early Contraction",
    "regime_early_expansion":   "Early Expansion",
    "regime_late_contraction":  "Late Contraction",
}

def get_regime(row):
    for col, label in REGIME_MAP.items():
        if col in row and row[col] == 1:
            return label
    return "Unknown"

df["regime"] = df.apply(get_regime, axis=1)

# ── P&L by hour ───────────────────────────────────────────────────────────────
by_hour = df.groupby("hour").agg(
    trades    = ("pnl_net", "count"),
    total_pnl = ("pnl_net", "sum"),
    avg_pnl   = ("pnl_net", "mean"),
    win_rate  = ("pnl_net", lambda x: (x > 0).mean()),
).reset_index()

print("=" * 65)
print("  P&L BY HOUR OF DAY")
print("=" * 65)
print(f"{'Hour':>5} {'Trades':>7} {'Total P&L':>11} {'Avg P&L':>9} {'Win Rate':>9}")
print("-" * 65)
for _, row in by_hour.iterrows():
    h = int(row["hour"])
    label = f"{h:02d}:00"
    print(f"{label:>5}  {int(row['trades']):>7,}  ${row['total_pnl']:>10,.2f}  "
          f"${row['avg_pnl']:>8,.2f}  {row['win_rate']*100:>8.1f}%")
print("-" * 65)
print(f"{'TOTAL':>5}  {len(df):>7,}  ${df['pnl_net'].sum():>10,.2f}  "
      f"${df['pnl_net'].mean():>8,.2f}  {(df['pnl_net']>0).mean()*100:>8.1f}%")

# ── Plot ──────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 1, figsize=(12, 12))

# Total P&L per hour
ax = axes[0]
colors = ["steelblue" if v >= 0 else "tomato" for v in by_hour["total_pnl"]]
ax.bar(by_hour["hour"], by_hour["total_pnl"], color=colors, alpha=0.85, width=0.7)
ax.axhline(0, color="black", linewidth=0.8)
ax.set_title("Total Net P&L by Hour of Day")
ax.set_xlabel("Hour (UTC-5 / ET)")
ax.set_ylabel("Total P&L ($)")
ax.set_xticks(by_hour["hour"])
ax.set_xticklabels([f"{h:02d}:00" for h in by_hour["hour"]], rotation=45)
ax.grid(True, axis="y", alpha=0.3)
for _, row in by_hour.iterrows():
    ax.text(row["hour"], row["total_pnl"] + (500 if row["total_pnl"] >= 0 else -1000),
            f"${row['total_pnl']:,.0f}", ha="center", fontsize=7)

# Avg P&L per trade per hour
ax = axes[1]
colors2 = ["steelblue" if v >= 0 else "tomato" for v in by_hour["avg_pnl"]]
ax.bar(by_hour["hour"], by_hour["avg_pnl"], color=colors2, alpha=0.85, width=0.7)
ax.axhline(0, color="black", linewidth=0.8)
ax.set_title("Avg Net P&L per Trade by Hour")
ax.set_xlabel("Hour (ET)")
ax.set_ylabel("Avg P&L ($)")
ax.set_xticks(by_hour["hour"])
ax.set_xticklabels([f"{h:02d}:00" for h in by_hour["hour"]], rotation=45)
ax.grid(True, axis="y", alpha=0.3)
for _, row in by_hour.iterrows():
    ax.text(row["hour"], row["avg_pnl"] + (0.3 if row["avg_pnl"] >= 0 else -0.8),
            f"${row['avg_pnl']:.1f}", ha="center", fontsize=7)

# Win rate + trade count per hour
ax = axes[2]
ax2 = ax.twinx()
ax.bar(by_hour["hour"], by_hour["win_rate"] * 100, color="seagreen", alpha=0.6, width=0.7, label="Win rate %")
ax2.plot(by_hour["hour"], by_hour["trades"], color="darkorange", marker="o", linewidth=1.5, label="# Trades")
ax.axhline(50, color="dimgray", linestyle="--", linewidth=0.8)
ax.set_title("Win Rate & Trade Count by Hour")
ax.set_xlabel("Hour (ET)")
ax.set_ylabel("Win Rate (%)")
ax2.set_ylabel("# Trades")
ax.set_xticks(by_hour["hour"])
ax.set_xticklabels([f"{h:02d}:00" for h in by_hour["hour"]], rotation=45)
ax.set_ylim(0, 100)
ax.grid(True, axis="y", alpha=0.3)
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

fig.tight_layout()
path = REPORTS_DIR / "pnl_by_hour.png"
fig.savefig(path, dpi=100)
print(f"\nSaved -> {path}")


# ── P&L by Regime ─────────────────────────────────────────────────────────────
by_regime = df.groupby("regime").agg(
    trades    = ("pnl_net", "count"),
    total_pnl = ("pnl_net", "sum"),
    avg_pnl   = ("pnl_net", "mean"),
    win_rate  = ("pnl_net", lambda x: (x > 0).mean()),
).reset_index().sort_values("total_pnl", ascending=False)

print()
print("=" * 70)
print("  P&L BY MACRO REGIME")
print("=" * 70)
print(f"{'Regime':<25} {'Trades':>7} {'Total P&L':>12} {'Avg P&L':>9} {'Win Rate':>9}")
print("-" * 70)
for _, row in by_regime.iterrows():
    print(f"{row['regime']:<25}  {int(row['trades']):>7,}  ${row['total_pnl']:>10,.2f}"
          f"  ${row['avg_pnl']:>7,.2f}  {row['win_rate']*100:>8.1f}%")
print("-" * 70)
print(f"{'TOTAL':<25}  {len(df):>7,}  ${df['pnl_net'].sum():>10,.2f}"
      f"  ${df['pnl_net'].mean():>7,.2f}  {(df['pnl_net']>0).mean()*100:>8.1f}%")

fig2, axes2 = plt.subplots(1, 3, figsize=(16, 5))

regimes   = by_regime["regime"].tolist()
total_pnl = by_regime["total_pnl"].tolist()
avg_pnl   = by_regime["avg_pnl"].tolist()
win_rates = (by_regime["win_rate"] * 100).tolist()
trades    = by_regime["trades"].tolist()

colors_pnl = ["steelblue" if v >= 0 else "tomato" for v in total_pnl]

ax = axes2[0]
ax.barh(regimes[::-1], total_pnl[::-1], color=colors_pnl[::-1], alpha=0.85)
ax.axvline(0, color="black", linewidth=0.8)
ax.set_title("Total Net P&L by Regime")
ax.set_xlabel("Total P&L ($)")
ax.grid(True, axis="x", alpha=0.3)

ax = axes2[1]
colors_avg = ["steelblue" if v >= 0 else "tomato" for v in avg_pnl]
ax.barh(regimes[::-1], avg_pnl[::-1], color=colors_avg[::-1], alpha=0.85)
ax.axvline(0, color="black", linewidth=0.8)
ax.set_title("Avg Net P&L per Trade by Regime")
ax.set_xlabel("Avg P&L ($)")
ax.grid(True, axis="x", alpha=0.3)

ax = axes2[2]
ax2r = ax.twiny()
ax.barh(regimes[::-1], win_rates[::-1], color="seagreen", alpha=0.6, label="Win rate %")
ax2r.plot(trades[::-1], regimes[::-1], color="darkorange", marker="o", linewidth=1.5, label="# Trades")
ax.axvline(50, color="dimgray", linestyle="--", linewidth=0.8)
ax.set_title("Win Rate & Trade Count by Regime")
ax.set_xlabel("Win Rate (%)")
ax2r.set_xlabel("# Trades")
ax.set_xlim(0, 100)
ax.grid(True, axis="x", alpha=0.3)

fig2.tight_layout()
path2 = REPORTS_DIR / "pnl_by_regime.png"
fig2.savefig(path2, dpi=100)
print(f"Saved -> {path2}")


# ── Rule-Based Filter: no 15:00, no weak regimes ──────────────────────────────
WEAK_REGIMES  = {"Early Expansion", "Late Contraction"}
BAD_HOURS     = {12, 15}

mask_hour   = ~df["hour"].isin(BAD_HOURS)
mask_regime = ~df["regime"].isin(WEAK_REGIMES)

naive    = df
hour_only   = df[mask_hour]
regime_only = df[mask_regime]
combined    = df[mask_hour & mask_regime]

print()
print("=" * 70)
print("  RULE-BASED FILTER COMPARISON")
print("=" * 70)
print(f"{'Filter':<30} {'Trades':>7} {'Total P&L':>12} {'Avg P&L':>9} {'Win Rate':>9}")
print("-" * 70)
for label, subset in [
    ("Naive (no filter)",              naive),
    ("No 12:00 + 15:00",               hour_only),
    ("No weak regimes",                regime_only),
    ("No 12:00+15:00 + no weak reg.",  combined),
]:
    t   = len(subset)
    tot = subset["pnl_net"].sum()
    avg = subset["pnl_net"].mean()
    wr  = (subset["pnl_net"] > 0).mean() * 100
    print(f"{label:<30}  {t:>7,}  ${tot:>10,.2f}  ${avg:>7,.2f}  {wr:>8.1f}%")
print("-" * 70)
pct_taken = len(combined) / len(naive) * 100
print(f"\nCombined filter takes {len(combined):,} / {len(naive):,} trades ({pct_taken:.1f}%)")
