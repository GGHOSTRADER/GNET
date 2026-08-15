import pandas as pd
import numpy as np

df = pd.read_csv("strategies/zona_strat/processed/df_enriched_mlp.csv")
df["entry_ts"] = pd.to_datetime(df["entry_ts"])
df["exit_ts"]  = pd.to_datetime(df["exit_ts"])
df["hold_min"] = (df["exit_ts"] - df["entry_ts"]).dt.total_seconds() / 60

total = len(df)
print(f"Total trades: {total:,}  Total PNL: ${df['pnl'].sum():,.2f}")
print()

mask_long_hold  = df["hold_min"] > 14
mask_big_win    = df["pnl"] >  300
mask_big_loss   = df["pnl"] < -300
mask_out        = mask_long_hold | mask_big_win | mask_big_loss
mask_clean      = ~mask_out

print(f"Removed — hold > 14 min : {mask_long_hold.sum():,}  PNL: ${df[mask_long_hold]['pnl'].sum():,.2f}")
print(f"Removed — pnl  >  $300  : {mask_big_win.sum():,}   PNL: ${df[mask_big_win]['pnl'].sum():,.2f}")
print(f"Removed — pnl  < -$300  : {mask_big_loss.sum():,}  PNL: ${df[mask_big_loss]['pnl'].sum():,.2f}")
print(f"Removed — total (union) : {mask_out.sum():,}  PNL: ${df[mask_out]['pnl'].sum():,.2f}")
print()
print(f"Remaining trades        : {mask_clean.sum():,}  PNL: ${df[mask_clean]['pnl'].sum():,.2f}")
print()

clean = df[mask_clean]
print(f"  Long  : {(clean['direction']==1).sum():,}  PNL: ${clean[clean['direction']==1]['pnl'].sum():,.2f}")
print(f"  Short : {(clean['direction']==-1).sum():,}  PNL: ${clean[clean['direction']==-1]['pnl'].sum():,.2f}")
print()
print(f"  Win rate : {(clean['pnl'] > 0).mean()*100:.1f}%")
print(f"  Avg win  : ${clean[clean['pnl']>0]['pnl'].mean():.2f}")
print(f"  Avg loss : ${clean[clean['pnl']<0]['pnl'].mean():.2f}")
print(f"  Avg PNL  : ${clean['pnl'].mean():.2f}")
