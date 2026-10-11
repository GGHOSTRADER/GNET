"""Exit analyzer's comparison report, not the per-backtest statistics report."""
from __future__ import annotations

from collections import deque
from html import escape
from pathlib import Path
import json

import numpy as np
import pandas as pd

from backtester.config import atomic_json


def find_regions(rows, profits, stops, required_positive_blocks):
    """Area counts only rectangles whose FOUR evaluated corners qualify."""
    all_regions = []
    for hold in sorted({r["hold_seconds"] for r in rows}):
        nodes = {(profits.index(r["profit_ticks"]), stops.index(r["stop_ticks"])): r for r in rows
                 if r["hold_seconds"] == hold and r["eligible"] and r["net_pnl"] > 0
                 and r["positive_blocks"] >= required_positive_blocks}
        remaining = set(nodes)
        while remaining:
            seed = min(remaining)
            remaining.remove(seed)
            pending, component = deque([seed]), {seed}
            while pending:
                x, y = pending.popleft()
                for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        pending.append(neighbor)
            area = 0
            for x, y in component:
                if {(x + 1, y), (x, y + 1), (x + 1, y + 1)} <= component:
                    area += (profits[x + 1] - profits[x]) * (stops[y + 1] - stops[y])
            center = np.mean(list(component), axis=0)
            representative = min(component, key=lambda p: (float(np.sum((np.asarray(p) - center) ** 2)), -nodes[p]["net_pnl"], p))
            all_regions.append({
                "hold_seconds": hold, "nodes": len(component), "supported_area_ticks_squared": area,
                "representative": nodes[representative]["policy_id"],
                "minimum_net_pnl": min(nodes[p]["net_pnl"] for p in component),
                "policies": [nodes[p]["policy_id"] for p in sorted(component)],
            })
    return sorted(all_regions, key=lambda r: (-r["supported_area_ticks_squared"], -r["nodes"], -r["minimum_net_pnl"]))


def edges(axis):
    values = np.asarray(axis, dtype=float)
    if len(values) == 1:
        return np.array([values[0] - 0.5, values[0] + 0.5])
    mids = (values[1:] + values[:-1]) / 2
    return np.r_[values[0] - (mids[0] - values[0]), mids, values[-1] + (values[-1] - mids[-1])]


def write_report(config, bar_key, rows, search_stop):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    root = Path(config.output)
    directory = root / "reports" / bar_key
    directory.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows).sort_values("net_pnl", ascending=False)
    table.to_csv(directory / "policies.csv", index=False)
    regions = find_regions(rows, config.profits, config.stops, config.region_min_positive_blocks)
    atomic_json(directory / "regions.json", regions)
    eligible = [row for row in rows if row["eligible"]]
    supported = [r for r in regions if r["supported_area_ticks_squared"] > 0]
    if supported:
        selected = next(row for row in eligible if row["policy_id"] == supported[0]["representative"])
        selection_rule = "representative of largest supported positive region"
    else:
        selected = max(eligible, key=lambda row: row["net_pnl"], default=None)
        selection_rule = "best eligible sampled point; no supported positive area found"
    atomic_json(directory / "selection.json", {"policy": selected, "rule": selection_rule})
    images = []
    for hold in sorted({row["hold_seconds"] for row in rows}):
        z = np.full((len(config.stops), len(config.profits)), np.nan)
        bad_x, bad_y = [], []
        for row in rows:
            if row["hold_seconds"] != hold:
                continue
            x, y = config.profits.index(row["profit_ticks"]), config.stops.index(row["stop_ticks"])
            z[y, x] = row["net_pnl"]
            if not row["eligible"]:
                bad_x.append(row["profit_ticks"])
                bad_y.append(row["stop_ticks"])
        fig, ax = plt.subplots(figsize=(8, 6), constrained_layout=True)
        palette = plt.get_cmap("RdYlGn").copy()
        palette.set_bad("#d0d0d0")
        scale = max(1.0, float(np.nanmax(np.abs(z))))
        plot = ax.pcolormesh(edges(config.profits), edges(config.stops), np.ma.masked_invalid(z),
                             cmap=palette, vmin=-scale, vmax=scale, shading="flat")
        if bad_x:
            ax.scatter(bad_x, bad_y, marker="x", c="black", label="Ineligible result")
            ax.legend(loc="best")
        ax.set(xlabel="Profit target (ticks)", ylabel="Stop loss (ticks)",
               xticks=config.profits, yticks=config.stops,
               title=f"{bar_key}: {hold}s maximum hold\nSampled net P&L; gray = untested")
        fig.colorbar(plot, ax=ax, label="USD after costs")
        name = f"surface_h{hold}.png"
        fig.savefig(directory / name, dpi=150)
        plt.close(fig)
        images.append(name)
        fig = plt.figure(figsize=(8, 6), constrained_layout=True)
        ax = fig.add_subplot(111, projection="3d")
        x, y = np.meshgrid(config.profits, config.stops)
        mask = np.isfinite(z)
        ax.scatter(x[mask], y[mask], z[mask], c=z[mask], cmap=palette, vmin=-scale, vmax=scale)
        faces = []
        for j in range(len(config.stops) - 1):
            for i in range(len(config.profits) - 1):
                corners = [(j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)]
                if all(mask[a, b] for a, b in corners):
                    faces.append([(x[a, b], y[a, b], z[a, b]) for a, b in corners])
        if faces:
            ax.add_collection3d(Poly3DCollection(faces, alpha=0.2, facecolor="steelblue"))
        ax.set(xlabel="Target ticks", ylabel="Stop ticks", zlabel="Net USD",
               title=f"{bar_key}, {hold}s: tested nodes\nMesh only connects fully sampled cells")
        name = f"surface3d_h{hold}.png"
        fig.savefig(directory / name, dpi=150)
        plt.close(fig)
        images.append(name)
    if selected:
        trades = pd.read_parquet(root / "policies" / bar_key / "development" / selected["policy_id"] / "trades.parquet")
        closed = trades.dropna(subset=["net_pnl"]).copy()
        fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
        dates = pd.to_datetime(closed["exit_ns"], unit="ns", utc=True).dt.tz_convert(config.timezone)
        equity = np.r_[0.0, closed["net_pnl"].cumsum().to_numpy()]
        first = pd.to_datetime(int(closed.iloc[0]["entry_ns"]), unit="ns", utc=True).tz_convert(config.timezone)
        ax.step([first, *dates], equity, where="post")
        ax.axhline(0, color="gray", linewidth=0.7)
        ax.set(title=f"{bar_key}: {selected['policy_id']} — realized equity", ylabel="Net USD", xlabel=config.timezone)
        fig.savefig(directory / "equity.png", dpi=150)
        plt.close(fig)
        images.insert(0, "equity.png")
    display = table[["policy_id", "closed_trades", "skipped_busy", "net_pnl", "win_rate", "max_drawdown", "eligible"]]
    html = "<!doctype html><html><head><meta charset='utf-8'><title>GNET Exit Analysis</title>"
    html += "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#182b3a}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:right}img{max-width:100%}code{background:#eee;padding:3px}</style></head><body>"
    html += f"<h1>GNET Exit Analysis — {escape(bar_key)}</h1><p>{len(rows)} sampled policies. Search stopped: {escape(search_stop)}.</p>"
    html += "<p><a href='../../backtesting_results.html'>Separate backtesting statistics for each configuration</a></p>"
    html += f"<p>One ES contract; ${config.round_trip_cost:.2f} round-trip cost; {config.slippage_ticks:g} tick slippage per market fill. Separate position state per policy; crosses while occupied are skipped.</p>"
    html += f"<p>Selection: {escape(selection_rule)}. Results shown here are development results.</p>"
    html += "<p>Drawdown includes tick-level estimated liquidation equity. The equity chart shows realized closes. Black crosses identify results failing configured validity/trade-count/drawdown criteria.</p>"
    html += display.to_html(index=False, float_format=lambda x: f"{x:,.2f}", escape=True)
    html += f"<h2>Positive regions</h2><p>{len(regions)} connected groups; {len(supported)} have fully sampled positive area. Missing cells are unknown.</p>"
    if regions:
        html += pd.DataFrame([{k: v for k, v in r.items() if k != "policies"} for r in regions]).to_html(index=False, escape=True)
    html += "".join(f"<img src='{escape(name)}' alt='{escape(name)}'>" for name in images)
    html += "<p>Figures and CSV/JSON summaries are stored beside this report.</p></body></html>"
    (directory / "index.html").write_text(html, encoding="utf-8")
    return {"bar_spec": bar_key, "selection": selected, "selection_rule": selection_rule,
            "report": str(directory / "index.html")}
