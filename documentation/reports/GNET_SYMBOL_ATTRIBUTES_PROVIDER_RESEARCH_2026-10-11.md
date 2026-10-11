# SymbolAttributesProvider exporter research

TradeStation 10 documents Country (country of the trading exchange), Exchange,
SymbolType, PointValue, MinMove, PriceScale and delivery identity on
[SymbolAttributesProvider](https://help.tradestation.com/10_00/eng/tsdevhelp/elobject/class/symbolattributesprovider_class.htm).
It can retrieve symbol attributes without that symbol appearing in a chart.
[DataProvider](https://help.tradestation.com/10_00/eng/tsdevhelp/elobject/class/dataprovider_class.htm)
uses asynchronous loading; Realtime=false disables subsequent realtime updates.
[Provider events](https://help.tradestation.com/10_00/eng/tsdevhelp/elobject/topics/provider_classes.htm)
include initial loading as well as updates. Thus initial symbol metadata lookup
without a live tick is supported by the documented model. Actual installed
historical-chart behavior has not yet been verified.

The existing exporter writes chart_exchange=unknown. Provider capture can replace
that placeholder and supply raw country, security type and pricing facts.
Capture the exact requested/returned symbol, lookup status, time of capture and
raw provider values in a bounded metadata section. Country format and provider
PointValue/PriceScale semantics must be observed before normalization or conversion.
Do not automatically equate provider PointValue with BigPointValue without checking.

The provider documentation does not establish dated historical symbol attributes.
Treat the result as a snapshot fetched at export time, not an as-of-history proof.
Likewise, its [SymbolSession](https://help.tradestation.com/10_00/eng/tsdevhelp/elobject/class/symbolsession_class.htm)
example concerns this week's sessions. Continue capturing the actual chart session
template and using dated exchange calendars for historical closures/early closes.
A GMT offset alone does not identify a historical DST timezone.

## Prepared standalone probe

`.artifacts/SymbolAttributesProvider-Probe/GNET_Symbol_Attributes_Probe.els`
is a new Indicator source, not a change to any installed exporter or package.
It requests GetSymbolName with Realtime=false, handles initial StateChanged and
polls via a timer for at most 30 timer callbacks. It prints metadata only, with
historical/realtime calculation counters. It issues no orders and exports no rows.
It uses documented provider methods plus event/timer signatures already present
in the exporter. TradeStation Verify and native execution remain pending.

1. Create a new Indicator with this source and run Verify; retain any compile error.
2. Apply it to a separate research chart with a fixed end date in the past,
   while connected to TradeStation's data service. Leave trading automation off.
3. Observe the Print Log without waiting for a live bar. A loaded result with
   matching requested/provider symbol, nonempty Country/Exchange and zero realtime
   calculations establishes that test's historical-chart startup behavior.
4. Compare reported instrument properties against the platform symbol settings.
   Repeat for a stock, outright future, continuous future and expired contract
   where the platform supports the symbol. Do not treat unavailable/blank values
   as an American exchange or invent a contract owner for a continuous symbol.
5. Recalculate/reload and verify late loading/timeout behavior before integrating
   capture into export closure. Preserve price/row export ordering and closure.

No native TradeStation control or compiler tool is exposed in this session.
No successful compile, runtime probe, exporter installation or historical
point-in-time metadata certification is claimed. V45/V78 remains staged and is
not deployed while this exporter improvement is evaluated.
