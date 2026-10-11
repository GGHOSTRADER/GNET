"""Fabricated worker regressions for native browsing versus explicit focus."""
import csv
import importlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

PACKAGE = Path(os.environ.get('GNET_NATIVE_VIEW_PACKAGE', str(Path(__file__).resolve().parents[1] / '.artifacts/GNET-Command-Center-v43-NativeBrowseFix-r1/guarded-v43-native-browse-fix')))
sys.path.insert(0, str(PACKAGE))
view = importlib.import_module('gnet_broker.ts_primary_view')


@pytest.fixture
def bars(tmp_path):
    path = tmp_path / 'bars.csv'
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Timestamp', 'Open', 'High', 'Low', 'Close'])
        for i in range(1, 1201):
            writer.writerow([f'2026-01-05T{i // 60:02}:{i % 60:02}:00', 100, 102, 99, 101])
    return path


@pytest.fixture
def trade():
    return {'trade_id': 'toy-1', 'signal_row': 68, 'entry_row': 69, 'exit_row': 72,
            'status': 'closed', 'boundary': False, 'net_pnl': 1,
            'entry_reported_time': '2026-01-05T01:09:00'}


def test_browse_includes_start_before_first_trade(bars, trade):
    candles, overlay = view.native_chart(bars, trade, 500, focused=False)
    assert [c['row'] for c in candles] == list(range(1, 501))
    assert overlay['signal_stamp'] == '2026-01-05T01:08:00'
    assert overlay['chart_has_more'] is True


def test_browse_120_bar_source_returns_all_120(tmp_path, trade):
    path = tmp_path / 'bars.csv'
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Timestamp', 'Open', 'High', 'Low', 'Close'])
        writer.writerows(['2026-01-05T00:00:00', 100, 102, 99, 101] for _ in range(120))
    candles, overlay = view.native_chart(path, trade, 500, focused=False)
    assert len(candles) == 120
    assert candles[0]['row'] == 1 and candles[-1]['row'] == 120
    assert overlay['chart_has_more'] is False


def test_browse_consecutive_windows_and_last_page(bars, trade):
    pages = [view.native_chart(bars, trade, 500, chart_offset=i, focused=False) for i in (0, 500, 1000)]
    assert [len(p[0]) for p in pages] == [500, 500, 200]
    assert [p[1]['chart_has_more'] for p in pages] == [True, True, False]
    assert [c['row'] for p, _ in pages for c in p] == list(range(1, 1201))


def test_explicit_trade_focus_preserved(bars, trade):
    candles, overlay = view.native_chart(bars, trade, 20, focused=True)
    assert [c['row'] for c in candles] == list(range(63, 83))
    assert overlay['entry_bar_stamp'] == '2026-01-05T01:09:00'
    assert overlay['exit_bar_stamp'] == '2026-01-05T01:12:00'


def test_browse_with_no_matching_trades_still_shows_bars(bars):
    candles, overlay = view.native_chart(bars, None, 500, focused=False)
    assert len(candles) == 500
    assert overlay['signal_price'] is None
    assert overlay['chart_has_more'] is True


def test_empty_focus_preserved(bars):
    assert view.native_chart(bars, None, 500, focused=True) == ([], None)


@pytest.mark.parametrize('focused', [False, True])
def test_worker_dispatches_explicit_focus_only(tmp_path, bars, trade, monkeypatch, focused):
    """Exercise the worker caller and report output; custody is a fabricated boundary."""
    import scripts.guarded_export_metadata as metadata
    monkeypatch.setattr(view, 'validate', lambda *args: None)
    monkeypatch.setattr(view, 'safe_path', lambda p: p)
    monkeypatch.setattr(view, 'read_json', lambda p, size: (
        {'enabled': True, 'real_data_authorized': True, 'allowed_exporter_sha256': ['toy']} if p.name == 'ts-custody-policy.json'
        else {'export_id': 'toy', 'custody_committed': True, 'row_contract_status': 'pass',
              'exporter_sha256': 'toy', 'primary_report': {'trade_contract_passed': True}}))
    contract = {'schema_version': 'gnet-ts-primary-contract-3', 'strategy_id': 'toy', 'parameters': {}, 'rule_family': 'toy'}
    def snapshot(catalog, export_id, destination):
        destination.mkdir(parents=True)
        (destination / 'bars.csv').write_bytes(bars.read_bytes())
        (destination / 'metadata.txt').write_text('fabricated')
        return {'strategy_report': contract, 'files': [{'role': r, 'name': n} for r, n in
                [('metadata', 'metadata.txt'), ('bars', 'bars.csv'), ('strategy_report', 'trades.csv')]],
                'source': {'symbol': 'TOY', 'interval_kind': 'minutes', 'interval_size': 1,
                           'chart_timezone_mode': 2, 'source_timezone': 'UTC'}}, {}
    monkeypatch.setattr(view, 'custody_snapshot', snapshot)
    monkeypatch.setattr(metadata, 'parse_metadata', lambda text: {})
    monkeypatch.setattr(view, 'validate_primary', lambda *args, **kwargs: (
        {'strategy_inputs': {}, 'rule_signal_checks': {}, 'trades_received': 1}, [trade]))
    payload = {'export_id': 'toy', 'max_points': 500, 'chart_offset': 0}
    if focused:
        payload['selected_trade_id'] = trade['trade_id']
    output = view.ts_primary_trade_view(SimpleNamespace(protected=tmp_path, vault=tmp_path, synthetic_only=False),
        SimpleNamespace(payload=payload, release_id='toy'), tmp_path)
    assert output.counts['points'] == 500
    # Extract only the fabricated report contract produced by the actual worker.
    expected = '"row":63' if focused else '"row":1'
    assert expected in output.reports['native_trades.html']
