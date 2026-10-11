"""Render actual V43 report templates from 1,200 fabricated observations only."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
broker = base / '.artifacts/GNET-Command-Center-v43-NativeBrowseFix-r1/guarded-v43-native-browse-fix'
sys.path.insert(0, str(broker))
from gnet_broker.ts_primary_view import native_chart, render_native_view
from gnet_broker.dataset_chart import select_window
from gnet_broker.viewer import render_view
from gnet_jobs.contracts import canonical

root = base / '.test_artifacts/generated-chart-fixtures'
root.mkdir(parents=True, exist_ok=True)
start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
points = [dict(row=i+1, stamp=(start+timedelta(minutes=i)).isoformat(),
               open=100+i*.01, high=102+i*.01, low=99+i*.01, close=101+i*.01)
          for i in range(1200)]
bars = root / 'fabricated-bars.csv'
with bars.open('w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['Timestamp', 'Open', 'High', 'Low', 'Close'])
    writer.writerows([p['stamp'], p['open'], p['high'], p['low'], p['close']] for p in points)
trade = dict(trade_id='t-1', signal_row=28, entry_row=29, exit_row=60,
             status='closed', boundary=False, net_pnl=50, side=1, outcome='winner',
             entry_price=101, exit_price=102, entry_reported_time=points[28]['stamp'],
             exit_reported_time=points[59]['stamp'])
source = dict(export_id='generated-synthetic', symbol='SYNTHETIC', bar_size=1,
              bar_kind='minutes', chart_clock_mode=2, source_timezone='UTC',
              strategy_id='fabricated-primary', strategy_settings_sha256='a'*64,
              rule_family='fabricated', strategy_inputs=[], rule_signal_checks='fixture', synthetic=True)
for offset in (0, 500, 1000):
    candles, overlay = native_chart(bars, trade, 500, chart_offset=offset, focused=False)
    data = dict(source=source, payload=dict(export_id=source['export_id'], chart_offset=offset, max_points=500),
                release_id='guarded-v43-native-browse-fix', page=[trade], chart=candles,
                selected=overlay, chart_has_more=overlay['chart_has_more'], matching_count=1,
                population_count=1, offset=0, page_size=20, has_more=False)
    (root / f'native-{offset}.html').write_text(render_native_view(data), encoding='utf-8')
    payload = dict(export_id=source['export_id'], start_date='2026-01-05', end_date='2026-01-06',
                   max_points=500, offset=offset, chart_mode='candles')
    window = select_window(iter(points), payload)
    data = dict(source=dict(id=source['export_id'], symbol='SYNTHETIC', kind='minutes', size=1, clock='UTC'),
                view=window, payload=payload, release_id='guarded-v43-native-browse-fix')
    template = (broker / 'gnet_broker/interactive_dataset_report.html').read_text(encoding='utf-8')
    encoded = canonical(data).decode().replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (root / f'dataset-{offset}.html').write_text(template.replace('__DATASET_CHART_DATA__', encoded), encoding='utf-8')
ns = lambda p: int(datetime.fromisoformat(p['stamp']).timestamp()*1e9)
candles = [dict(start_ns=ns(p)-60_000_000_000, end_ns=ns(p), first_event=i, last_event=i,
                bar_id=i, complete=True, **{k:p[k] for k in ('open','high','low','close')})
           for i,p in enumerate(points[:500])]
match = dict(trade_id='t-1', candidate_id='toy', entry_ns=ns(points[28]), exit_ns=ns(points[59]),
             entry_event=28, exit_event=59, entry_price=101, exit_price=102, net_pnl=50,
             gross_pnl=52, cost=2, outcome='winner', status='closed', valid=True,
             signal_ns=ns(points[27]), signal_price=101, signal_event=27)
view = dict(candles=candles, matches=[match], signals=[], matching_count=1, shown_count=1,
            offset=0, has_more=False, source_bar_count=500, point_count=500, aggregation_factor=1,
            aggregation='engineered bars', start_ns=candles[0]['start_ns'], end_ns=candles[-1]['end_ns'],
            selected_trade_id=None, bar_definition=dict(kind='time', size=60, label='60-second bars', default_axis='time'))
request = SimpleNamespace(dictionary=lambda: dict(payload=dict(run_id='fabricated-run',policy_id='toy',
    bar_series='time_60',phase='development',start=points[0]['stamp'],end=points[499]['stamp'])))
manifest = dict(coverage=dict(timezone='UTC',partial_sessions=[]),contract_segments=[dict(symbol='SYNTHETIC')],synthetic=True)
(root / 'engine-0.html').write_text(render_view(view,request,manifest,dict(status='pass',usable=True)),encoding='utf-8')
files = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.html')}
(root / 'receipt.json').write_text(json.dumps(dict(synthetic_only=True,rows=1200,
    broker_manifest_sha256=hashlib.sha256((broker/'release.json').read_bytes()).hexdigest(),
    scope='actual report renderers/templates and pagination math; no protected custody or worker acceptance',files=files),indent=2))
print(json.dumps(dict(output=str(root), reports=len(files), synthetic_only=True)))
