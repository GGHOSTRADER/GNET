# Automatic TradeStation instrument metadata — V46 / client V79

Staged delivery: `.artifacts/GNET-SymbolAttributes-v46-r1`.
Installed V44/V77 is unchanged. V45/V78 remains a superseded staged candidate.

Broker `guarded-v46-symbol-attributes`, manifest SHA256:
`15948766c7cc730c3122a02ee7f1d735ee48bcc5a61e9cf248955820d7c5e650`.
Client `gnet-client-v79-symbol-attributes`, manifest SHA256:
`3f836b1f4fd15877939760138f6a51306bf74459b5cc3118fcf10b27a731fcd9`.

## Three sources

The matching client contains updated `EL_files/GNET_Bar_Export.els`,
`GNET_Primary_Research_Export.els`, and `GNET_Primary_Generic_Scaffold.els`.
All three initialize one SymbolAttributesProvider for the captured chart symbol
when the export starts, with Realtime=false. No new Inputs or changed strategy,
bar, sampling, live-pipeline or terminal-hotkey settings are introduced.

The capture records requested/returned symbol, raw exchange country, exchange,
security type, provider point value, minimum move, price scale, delivery month/year,
native chart BigPointValue, local capture time and loaded/incomplete/failed/timeout
status. Provider initialization/read failure stays unresolved. A timer bounds
pending lookup to 30 callbacks. Existing uninitialization closes the new provider
and timer. Publication waits for both the existing volume probe and this lookup
to finish; errors/timeouts finish with unresolved metadata.

Historical row ordering, first-20-bar filename selection, terminal-bar exclusion
and the existing first-realtime-calculation closure are preserved. This change
does not finalize a historical-only/expired chart without its existing closure
evidence. Metadata is written once in the normal closed export sidecar, not on
each market row. No market-data CSV column changes.

## Stored metadata and charts

The strict sidecar parser validates the optional snapshot and exact symbol/exchange
identity. Older sidecars remain supported. The finalizer carries the capture into
the sealed bundle; broker custody receipts and registered source manifests retain
it. A native strategy point value must agree with captured chart BigPointValue.
An observed stock is not classified as an ES future merely because its name
matches a futures-symbol pattern.

Dataset breakdowns, source reviews, registered metadata inspection and dataset/
native-primary charts display the captured fields. Inventory uses saved summary
metadata and does not inspect raw exports for these facts.

The exact observed United States / ARCX / stock combination resolves Exchange-mode
timestamps to America/New_York. Matched provider/native price grids and point values
supply the stock's automatic instrument profile; stock delivery sentinels become
not-applicable ownership fields. Country alone supplies no timezone or session.
Other unrecognized exchange/type combinations retain their raw attributes and
remain unresolved until a reviewed mapping/profile is available. A Local-mode
chart does not inherit the exchange clock.

Registered datasets prefer their reviewed dated calendar, scoped to requested
dates. Markers support early closes, closed days, overnight sessions and breaks.
Known ARCX received sources can show clearly labeled 09:30–16:00 New York core
reference hours. Those reference hours do not certify holidays or historical
early closes. Unresolved assets get no inherited US markers. Existing marker
visibility for intraday intervals below one hour remains unchanged.

Sources: [TradeStation SymbolAttributesProvider](https://help.tradestation.com/10_00/eng/tsdevhelp/elobject/class/symbolattributesprovider_class.htm),
[TradeStation supported exchanges](https://help.tradestation.com/10_00/eng/tradestationhelp/symbology/supported_exchanges.htm),
[NYSE trading information](https://www.nyse.com/trade/trading-information).
Country denotes the trading exchange's country. These attributes are snapshots
at export time; they do not certify historical point-in-time instrument settings.

## Acceptance and handoff

The user verified the standalone probe on BTC: Country United States, exchange
ARCX, security type stock, provider/native point value 1, min move 1 and price scale
100; 389 historical calculations and zero realtime calculations. This validates
that probe on that chart, not the three integrated production sources.

34 focused tests passed in 1.23 seconds: optional/legacy metadata, identity and
pricing failures, clock resolution, unresolved/non-US metadata, automatic stock
profiles, registered inventory, real sealing of fabricated exports, observed stock
classification, primary point-value conflict and exporter lifecycle contracts.
All 180 browser checks passed in 54.3 seconds without snapshot updates. They include
metadata in source breakdown/review/registered inspection, exact inspection payload,
stock exchange references, unresolved-exchange suppression and dated early-close/
overnight markers. The 1440px and 390px metadata layouts were visually inspected;
screenshots are `.test_artifacts/browser/symbol-metadata-1440.png` and
`.test_artifacts/browser/symbol-metadata-390.png`. Existing screenshot baselines
passed unchanged. Generated-report fixture tests still use the separately pinned
V43 templates; new reference descriptors are covered by focused tests and the
shared chart's fabricated browser contracts, not installed worker acceptance.

All changed Python modules import; existing definitions and class methods match
the prior immutable candidate. Every old EL method remains, with five new methods.
Broker/client closed package verification, deployment-plan hashes and PowerShell
parser checks passed. The new schema is included in both broker and ordinary-user
finalizer. No protected installation, real-data read, source registration, training
or new native isolation certification was performed.

The three integrated sources still require TradeStation Verify and a fresh export
acceptance test. The matching V46/V79 installation is required before applying the
new metadata format; V44's strict parser rejects the new sidecar field. Native
compile can be checked on separate candidate documents with export disabled,
preserving existing chart inputs and live services. Existing code-review/exporter
activation and real-source approval gates remain in place.

Administrator activation uses this delivery's `Deploy-ReviewedCommandCenter.ps1
-Apply`, with the existing account/password entered locally. The matching ordinary
client installer reruns the entire browser suite before restart. No approval to
activate this new V46 candidate has been collected. Non-ES calculation adapters
and continuous-contract ownership remain separate unfinished work; source metadata
capture does not enable unsupported research calculations.
