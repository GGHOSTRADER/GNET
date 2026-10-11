# Installed GUI testing, October 11

Existing synthetic replay results survived a workspace reload. Selecting the
score-matched arm increased rendered equity curves from three to four; drawdown
also rendered four curves. Switching from observed-price to closed-position
equity changed the actual rendered polyline. Evidence:
`.artifacts/installed-gui-replay-curves.png`.

## Fresh custody

The installed **Test with fabricated bars** button completed actual protected
custody for 25 generated bars. Exact hash verification and staging cleanup passed;
no dataset was admitted. The new receipt appeared with today's import date and
the Bar badge:

- Export: `qa-5c8c6882e70e4f618819acaee02005cf`.
- Job: `job-20261011T043529Z-59791883b9fd40adbf4886910eb73cb3`.
- State: stored; custody committed; staging cleaned; 25 rows.

The button remained enabled during its asynchronous request. V69 now disables it
and guards against re-entry until completion, restoring the appropriate boundary
state on failure. The regression checks duplicate prevention and retry recovery.
The full fabricated-response suite passed 100/100 in 2.0 minutes, with retries
disabled. Client V69 was installed; the broker remains V42. Manifest SHA-256:
`3bf2e85a71b355e240a55360fcf81af198f7686edd0a464cddd7d1b5198db328`.

## Received native synthetic trades

The received `acceptance-generic-primary-v39-r1` fixture has 120 bars and two
positions. Its real GUI launcher opened the protected native report successfully:
`job-20261011T043814Z-f64d1fd7ede1429c8816950903db605c`.
Filtering to winners returned exactly one matching position, t-2:
`job-20261011T044245Z-e35a7ae001f949419473a13861dded1c`.

## Failed installed check: Browse bars

Browse bars issued a new protected viewer job but still returned 58 observations,
identical to the original trade-focused window, rather than starting at the first
of 120 source bars:
`job-20261011T043928Z-08c5a67d87e545ebb7bd3bf12835ba64`.

V42 `gnet_broker/ts_primary_view.py` computes the start as the first matching
trade's signal row minus five, plus chart_offset. Thus an explicit zero offset
still starts at the trade anchor. The client correctly removes selected_trade_id
and sends chart_offset=0; fixing only its payload cannot correct this behavior.
The protected broker needs distinct full-source and selected-trade chart windows,
with bounded consecutive pagination. This failed gate is **not** covered by the
passing browser suite, whose shared-chart checks use fabricated report data.

Only fabricated data was used. Fresh research admission, native Windows
authentication, full isolation and real TradeStation platform acceptance remain
separate. This report does not certify the full native bar-browsing workflow.
