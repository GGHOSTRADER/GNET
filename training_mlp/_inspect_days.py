import pandas as pd

df = pd.read_csv("strategies/zona_strat/processed/df_enriched_mlp.csv")
df["entry_ts"] = pd.to_datetime(df["entry_ts"])
df["date"] = df["entry_ts"].dt.date

jul4 = df[df["date"] == pd.Timestamp("2025-07-04").date()]
print("=== July 4 2025 ===")
print(jul4[["entry_ts", "pnl", "direction"]].to_string())
print(f"  Total PNL: {jul4['pnl'].sum():.2f}  Trades: {len(jul4)}")

print()
apr4 = df[df["date"] == pd.Timestamp("2025-04-04").date()]
print("=== April 4 2025 ===")
print(apr4[["entry_ts", "pnl", "direction"]].to_string())
print(f"  Total PNL: {apr4['pnl'].sum():.2f}  Trades: {len(apr4)}")

print()
by_day = df.groupby("date").agg(total_pnl=("pnl", "sum"), trades=("pnl", "count")).sort_values("total_pnl", ascending=False)
print("=== Top 15 days by PNL ===")
print(by_day.head(15).to_string())
print()
print("=== Bottom 10 days by PNL ===")
print(by_day.tail(10).to_string())
print()

# What % of total PNL comes from top 10 days
total = df["pnl"].sum()
top10 = by_day.head(10)["total_pnl"].sum()
print(f"Total PNL (all): ${total:,.2f}")
print(f"Top 10 days PNL: ${top10:,.2f}  ({top10/total*100:.1f}% of total)")
print(f"Rest of days:    ${total - top10:,.2f}")
