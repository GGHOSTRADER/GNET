"""Publication regression using fabricated custody/calendar metadata only."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BROKER = Path(os.environ.get('GNET_REVIEW_BROKER', ROOT / '.artifacts/GNET-ReviewPublication-v44-r1/guarded-v44-review-publication-fix'))
sys.path.insert(0, str(BROKER))
from gnet_jobs.contracts import digest
from gnet_broker.publication import bounded_tree
from gnet_broker import ts_review_template, ts_series, ts_session_schedule


def test_pending_calendar_choices_do_not_publish_internal_evidence(tmp_path, monkeypatch):
    protected = tmp_path / 'protected'
    calendars = protected / 'calendars'
    calendars.mkdir(parents=True)
    (calendars / 'fabricated-calendar.json').write_text('{}')
    source = {'symbol': 'ESU26', 'series_type': 'individual_contract', 'interval_kind': 'minutes', 'interval_size': 5,
              'source_timezone': 'unknown', 'observed_session_name': 'Fabricated',
              'uses_regular_sessions': True}
    bundle = {'source': source}
    receipt = {'custody_committed': True, 'row_contract_status': 'pass', 'bundle_sha256': digest(bundle),
               'first_timestamp': '2026-01-05T08:00:00', 'last_timestamp': '2026-01-05T16:00:00', 'rows': 500}
    calendar = {'calendar_id': 'fabricated-calendar', 'timezone': 'America/Chicago',
                'start_session': '2026-01-05', 'end_session': '2026-01-05',
                'evidence': 'Reviewed settings at C:/protected/fabricated-evidence.json'}
    documents = {'custody-receipt.json': receipt, 'bundle.json': bundle, 'fabricated-calendar.json': calendar}
    monkeypatch.setattr(ts_review_template, 'read_json', lambda path, *args: documents[Path(path).name])
    monkeypatch.setattr(ts_series, 'template_series', lambda *args: ('individual_contract', [], 'none'))
    monkeypatch.setattr(ts_session_schedule, 'chart_scope_matches', lambda *args, **kwargs: False)
    output = ts_review_template.ts_review_template(SimpleNamespace(vault=tmp_path/'vault', protected=protected, synthetic_only=True),
        SimpleNamespace(payload={'export_id': 'fabricated-export', 'automatic_checks': True, 'synthetic': True}), tmp_path/'workspace')
    bounded_tree(output.metrics)
    choice = output.metrics['review_template']['calendar_choices'][0]
    assert choice['calendar_id'] == 'fabricated-calendar'
    assert 'evidence' not in choice
