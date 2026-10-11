"""Persistence and standalone HTML for ONE backtest, not an exit sweep."""
from html import escape
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd

from backtester.config import atomic_json
from backtester.results import build_equity, calculate_results


STYLE = """body{font:16px system-ui;color:#192f44;background:#fafbfd;max-width:1100px;margin:32px auto;padding:0 24px}
table{border-collapse:collapse;width:100%;margin:16px 0}td,th{padding:9px;border-bottom:1px solid #d4dce5;text-align:left}
.scroll{overflow-x:auto}svg{width:100%;height:auto}a{color:#155fa3}h2{margin-top:32px}pre{white-space:pre-wrap}
.note{background:#fff1d4;padding:16px} .metric{font-variant-numeric:tabular-nums}"""


def display(value):
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:,.6g}"
    return escape(str(value))


def metric_table(values):
    return "<table><tbody>" + "".join(
        f"<tr><th>{escape(key.replace('_', ' '))}</th><td class='metric'>{display(value)}</td></tr>"
        for key, value in values.items()) + "</tbody></table>"


def equity_svg(curve):
    """Min/max envelope sampling keeps extrema visible without giant HTML."""
    finite = curve.loc[np.isfinite(curve.liquidation_net_usd)].copy()
    if finite.empty:
        return "<p>No finite equity marks.</p>"
    values = finite.liquidation_net_usd.to_numpy()
    chosen = {0, len(finite) - 1}
    for chunk in np.array_split(np.arange(len(finite)), min(len(finite), 400)):
        chosen.update([int(chunk[0]), int(chunk[-1]), int(chunk[np.argmin(values[chunk])]), int(chunk[np.argmax(values[chunk])])])
    rows = finite.iloc[sorted(chosen)]
    first, last = int(finite.time_ns.iloc[0]), int(finite.time_ns.iloc[-1])
    low, high = min(0., float(values.min())), max(0., float(values.max()))
    pad = max(1., (high - low) * .08)
    low, high = low - pad, high + pad
    points = " ".join(f"{85 + (int(t) - first) / max(1, last-first) * 880:.2f},{280 - (v-low)/(high-low)*245:.2f}"
                      for t, v in zip(rows.time_ns, rows.liquidation_net_usd))
    zero = 280 - (0 - low) / (high - low) * 245
    start = pd.Timestamp(first, unit="ns", tz="UTC").strftime("%Y-%m-%d %H:%M")
    end = pd.Timestamp(last, unit="ns", tz="UTC").strftime("%Y-%m-%d %H:%M")
    return ("<svg viewBox='0 0 1000 345' role='img' aria-label='Estimated liquidation equity in USD over UTC time'>"
        "<rect x='85' y='35' width='880' height='245' fill='none' stroke='#bac9d8'/>"
        f"<line x1='85' x2='965' y1='{zero}' y2='{zero}' stroke='#bac9d8'/>"
        f"<polyline points='{points}' fill='none' stroke='#176a99' stroke-width='2'/>"
        f"<text x='78' y='42' text-anchor='end'>{high:,.0f}</text><text x='78' y='280' text-anchor='end'>{low:,.0f}</text>"
        f"<text x='85' y='305'>{start}</text><text x='965' y='305' text-anchor='end'>{end}</text>"
        "<text x='520' y='338' text-anchor='middle'>Time (UTC)</text>"
        "<text x='20' y='165' transform='rotate(-90 20 165)' text-anchor='middle'>Net liquidation P&amp;L (USD)</text></svg>")


def write_html(directory, metrics, curve):
    title = f"Backtest results — {metrics['bar_spec']} / {metrics['policy_id']} / {metrics['phase']}"
    html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>{STYLE}</style></head><body><h1>{escape(title)}</h1>"
    html += f"<p>Strategy: {escape(metrics['strategy'])}. Status: {escape(metrics['status'])}. No exit selection occurs in this report.</p>"
    html += "<p class='note'>Research replay, not proof of profitability. Fractions (win rate, exposure, return and probabilities) use 0–1 units. Unavailable statistics are not zero.</p>"
    html += "<h2>Estimated liquidation equity</h2>" + equity_svg(curve)
    for section in ("activity", "performance", "path", "execution", "risk_adjusted"):
        html += f"<h2>{escape(section.replace('_', ' ').title())}</h2>" + metric_table(metrics[section])
    for section, rows in metrics["attribution"].items():
        html += f"<h2>Distribution by {escape(section.replace('_', ' '))}</h2>"
        html += "<div class='scroll'>" + pd.DataFrame(rows).to_html(index=False, escape=True, float_format=lambda x: f"{x:,.4f}") + "</div>" if rows else "<p>No closed trades.</p>"
    html += "<h2>Assumptions and limits</h2><ul>" + "".join(f"<li>{escape(note)}</li>" for note in metrics["assumptions"]) + "</ul>"
    html += "<h2>Run settings</h2><pre>" + escape(json.dumps(metrics["run_config"], indent=2)) + "</pre>"
    html += "<p><a href='https://catalogimages.wiley.com/images/db/pdf/9781119482086.toc.pdf'>AFML Chapter 14 categories</a>; <a href='https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf'>Bailey and López de Prado: Sharpe inference</a>.</p>"
    html += "<p><a href='statistics.json'>Statistics JSON</a> · <a href='session_returns.csv'>Session returns</a> · <a href='drawdowns.csv'>Underwater episodes</a> · <a href='equity.parquet'>Equity / positions</a> · <a href='trades.parquet'>Trades</a></p></body></html>"
    temporary = directory / "results.html.tmp"
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(directory / "results.html")


def save_results(directory, config, times, prices, trades, signals, sessions, summary, begin, end):
    curve = build_equity(times, prices, trades, sessions, config, begin, end)
    lookup = {int(signal["signal_id"]): signal for signal in signals}
    shortfall, slip = 0.0, 0.0
    for trade in trades:
        signal = lookup[trade["signal_id"]]
        shortfall += (trade["entry_price"] - float(prices[signal["bar_last_event"]])) * 50
        slip += config.slippage_ticks * 12.5  # entry market fill
        if trade["exit_event"] is not None and trade["exit_reason"] != "profit":
            slip += config.slippage_ticks * 12.5
    metrics, daily, episodes = calculate_results(trades, curve, summary, config,
                                               entry_shortfall=shortfall, modeled_slippage=slip)
    metrics["run_config"] = config.dictionary()
    curve.to_parquet(directory / "equity.parquet", index=False)
    daily.to_csv(directory / "session_returns.csv", index=False)
    pd.DataFrame(episodes, columns=["start_ns", "end_ns", "depth_usd", "duration_seconds", "recovered"]).to_csv(directory / "drawdowns.csv", index=False)
    atomic_json(directory / "statistics.json", metrics)
    write_html(directory, metrics, curve)


def write_catalog(config):
    """Index all existing per-policy reports, in either mode and either phase."""
    root = Path(config.output)
    rows = []
    for path in sorted((root / "policies").glob("*/*/*/statistics.json")):
        metrics = json.loads(path.read_text(encoding="utf-8"))
        if not (path.parent / "summary.json").exists():
            continue  # incomplete policy output is not a completed result
        write_html(path.parent, metrics, pd.read_parquet(path.parent / "equity.parquet"))
        link = (path.parent / "results.html").relative_to(root).as_posix()
        rows.append(f"<tr><td><a href='{escape(link)}'>{escape(metrics['bar_spec'])} / {escape(metrics['policy_id'])}</a></td>"
                    f"<td>{escape(metrics['phase'])}</td><td>{escape(metrics['status'])}</td>"
                    f"<td>{metrics['activity']['closed_trades']}</td><td>{metrics['performance']['net_pnl']:,.2f}</td></tr>")
    html = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Backtesting results</title><style>{STYLE}</style></head><body><h1>Backtesting results</h1><p>One report per configuration. These statistics do not choose exit parameters.</p><table><thead><tr><th>Backtest</th><th>Phase</th><th>Status</th><th>Closed trades</th><th>Net USD</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"
    path = root / "backtesting_results.html"
    path.write_text(html, encoding="utf-8")
    return str(path)
