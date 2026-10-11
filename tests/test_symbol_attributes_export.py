"""Symbol metadata propagation tests; fabricated rows only when sealing fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
BROKER=Path(os.environ.get('GNET_REVIEW_BROKER',ROOT/'.artifacts/GNET-SymbolAttributes-v46-r1/guarded-v46-symbol-attributes'))
sys.path.insert(0,str(BROKER))
from gnet_broker.symbol_attributes import validate_capture,captured_profile,session_reference
from gnet_broker.instrument_profiles import resolve_profile
from scripts.guarded_export_metadata import parse_metadata
from gnet_broker.ts_export_contracts import BUNDLE,NAMED_BUNDLE,GENERIC_BUNDLE,PRIMARY_BUNDLE
from gnet_jobs.contracts import ContractError


@pytest.fixture
def capture():
    return {'schema_version':'gnet-ts-symbol-attributes-1','status':'loaded','requested_symbol':'BTC',
        'provider_symbol':'BTC','country_raw':'United States','exchange_raw':'ARCX','symbol_type':'stock',
        'point_value':1,'min_move':1,'price_scale':100,'delivery_month':-1,'delivery_year':0,
        'chart_big_point_value':1,'captured_at_local':'2026-10-11T10:00:00','realtime_updates':False}


def metadata(capture=None,**overrides):
    fields={'export_file':'bars.csv','generated_at_local':'2026-10-11T10:00:00',
        'chart_symbol':'BTC','chart_exchange':capture['exchange_raw'] if capture else 'unknown',
        'chart_bar_type':'1','chart_bar_interval':'5','chart_range_start':'2026-10-09T09:35:00',
        'chart_range_end':'2026-10-09T16:00:00','range_scope':'loaded_chart','timestamp_precision':'seconds',
        'max_bars_back':'1','declared_timezone':'unknown','declared_volume_mode':'trade_volume',
        'declared_price_basis':'unknown','declared_interval_kind':'minutes','export_file_verified':'false',
        'chart_timezone_mode':'1','chart_min_move':'1','chart_price_scale':'100',
        'declared_timestamp_convention':'bar_close'}
    if capture is not None:fields['symbol_attributes_json']=json.dumps(capture,separators=(',',':'))
    fields.update(overrides)
    return 'GNET_METADATA_BEGIN=1\n'+'\n'.join(k+'='+v for k,v in fields.items())+'\nGNET_METADATA_END=1\n'


def source(capture):
    return {'symbol':'BTC','series_type':'unclassified','min_move':1,'price_scale':100,
        'symbol_attributes':capture,'source_timezone':'America/New_York'}


def test_user_observed_stock_attributes_resolve_exchange_clock(capture):
    value=parse_metadata(metadata(capture))
    assert value['symbol_attributes']==capture
    assert value['declared']['timezone']=='America/New_York'
    assert value['observed']['chart_exchange']=='ARCX'
    assert 'price_basis' in value['declared'] and value['declared']['price_basis']=='unknown'


def test_legacy_metadata_remains_readable():
    value=parse_metadata(metadata())
    assert 'symbol_attributes' not in value
    assert value['declared']['timezone']=='unknown'


@pytest.mark.parametrize('change',[{'provider_symbol':'OTHER'},{'requested_symbol':'OTHER'},
    {'point_value':0},{'captured_at_local':'2026-02-31T12:00:00'},{'realtime_updates':True}])
def test_bad_loaded_identity_or_values_are_rejected(capture,change):
    capture.update(change)
    with pytest.raises((ValueError,ContractError)):
        parse_metadata(metadata(capture))


def test_failed_lookup_is_preserved_without_clock_guess(capture):
    capture.update(status='timeout',provider_symbol='',country_raw='',exchange_raw='',symbol_type='',
        point_value=0,min_move=0,price_scale=0)
    value=parse_metadata(metadata(capture))
    assert value['symbol_attributes']['status']=='timeout'
    assert value['declared']['timezone']=='unknown'
    assert any('timeout' in warning for warning in value['warnings'])


def test_non_us_exchange_is_not_given_ny_hours(capture):
    capture.update(country_raw='Germany',exchange_raw='XETR')
    assert parse_metadata(metadata(capture))['declared']['timezone']=='unknown'
    assert captured_profile(source(capture)) is None
    assert session_reference(source(capture)) is None


def test_local_chart_clock_is_not_replaced_by_exchange_clock(capture):
    assert parse_metadata(metadata(capture,chart_timezone_mode='0'))['declared']['timezone']=='unknown'
    with pytest.raises(ValueError,match='clock contradicts'):
        parse_metadata(metadata(capture,declared_timezone='America/Chicago'))


def test_stock_profile_uses_captured_economics_without_manual_profile(tmp_path,capture):
    catalog=SimpleNamespace(protected=tmp_path,synthetic_only=True)
    profile=resolve_profile(catalog,source(capture))
    assert profile['asset']=='BTC'
    assert profile['exchange']=='ARCX' and profile['country']=='US'
    assert profile['specification']=={'tick_size':.01,'multiplier':1,'volume_units':'shares'}
    assert profile['delivery_month'] is None and profile['delivery_year'] is None
    assert session_reference(source(capture))['label']=='ARCX core-session reference'


def test_grid_conflict_keeps_automatic_specification_unresolved(capture):
    capture['min_move']=2
    assert captured_profile(source(capture)) is None
    capture['min_move']=1
    capture['point_value']=50
    assert captured_profile(source(capture)) is None


def test_dated_calendar_overrides_core_reference_and_is_bounded(capture):
    calendar={'calendar_id':'fabricated-half-day','timezone':'America/New_York','sessions':[
        {'session':'2026-11-26','open':'09:30:00','close':'16:00:00'},
        {'session':'2026-11-27','open':'09:30:00','close':'13:00:00'},
        {'session':'2026-11-30','open':'09:30:00','close':'16:00:00'}]}
    ref=session_reference(source(capture),calendar,'2026-11-27','2026-11-27')
    assert ref['basis']=='reviewed_calendar'
    assert ref['sessions']==[{'session':'2026-11-27','open':'09:30:00','close':'13:00:00'}]


def test_all_bundle_versions_accept_optional_captured_metadata():
    for schema in (BUNDLE,NAMED_BUNDLE,GENERIC_BUNDLE,PRIMARY_BUNDLE):
        assert 'symbol_attributes' in schema['properties']['source']['properties']
        assert 'symbol_attributes' not in schema['properties']['source']['required']


def test_all_three_exporters_preserve_methods_and_coordinate_closure():
    import re
    prior=ROOT/'.artifacts/GNET-MultiAssetReview-v45-r1/gnet-client-v78-multi-asset-review/EL_files'
    current=ROOT/'.artifacts/GNET-SymbolAttributes-v46-r1/gnet-client-v79-symbol-attributes/EL_files'
    for name in ('GNET_Bar_Export.els','GNET_Primary_Research_Export.els','GNET_Primary_Generic_Scaffold.els'):
        before=(prior/name).read_text();text=(current/name).read_text()
        methods=lambda s:re.findall(r'^method\s+\w+\s+(\w+)\(',s,re.M)
        assert [m for m in methods(text) if m in methods(before)]==methods(before)
        assert 'SymbolProvider.Realtime=false;' in text
        assert 'If AutoProbeDone And SymbolDone And Not AutoRemoved' in text
        assert 'If SymbolDone And Not AutoRemoved And Not AutoPublishing' in text
        assert 'SymbolTimerCalls>=30' in text
        assert 'If SymbolProvider<>null Then SymbolProvider.Load=false;' in text
        assert text.count('        + GnetSymbolAttributesText()')==1


@pytest.mark.parametrize('security_type',['future','stock'])
def test_sealed_bundle_retains_attributes_and_observed_security_type(tmp_path,monkeypatch,capture,security_type):
    from gnet_broker import ts_acceptance_fixture,ts_export_bundle
    monkeypatch.setattr(ts_acceptance_fixture,'finalize_session',lambda folder:None)
    folder=ts_acceptance_fixture.create_export(tmp_path)
    capture.update(requested_symbol='ESU26',provider_symbol='ESU26',exchange_raw='CME',
        symbol_type=security_type,point_value=50,min_move=1,price_scale=4,chart_big_point_value=50,
        delivery_month=9 if security_type=='future' else -1,delivery_year=2026 if security_type=='future' else 0)
    path=next(folder.glob('*.gnet-metadata.txt.partial'))
    text=path.read_text()
    assert text.count('GNET_METADATA_END=1')==1
    path.write_text(text.replace('GNET_METADATA_END=1','symbol_attributes_json='+json.dumps(capture)+'\nGNET_METADATA_END=1'))
    ts_export_bundle.finalize_session(folder)
    bundle=json.loads((folder/'bundle.json').read_text())
    assert bundle['source']['symbol_attributes']==capture
    assert bundle['source']['series_type']==('individual_contract' if security_type=='future' else 'unclassified')
    checked=ts_export_bundle.validate_bundle(folder)
    assert checked['transport_ready'] is True and checked['rows']==ts_acceptance_fixture.ROWS


def test_primary_point_value_must_match_captured_chart(tmp_path,monkeypatch,capture):
    from gnet_broker import ts_acceptance_fixture,ts_export_bundle
    monkeypatch.setattr(ts_acceptance_fixture,'finalize_session',lambda folder:None)
    folder=ts_acceptance_fixture.create_export(tmp_path)
    capture.update(requested_symbol='ESU26',provider_symbol='ESU26',exchange_raw='CME',
        symbol_type='future',point_value=1,min_move=1,price_scale=4,chart_big_point_value=1,
        delivery_month=9,delivery_year=2026)
    path=next(folder.glob('*.gnet-metadata.txt.partial'))
    text=path.read_text()
    assert text.count('GNET_METADATA_END=1')==1
    path.write_text(text.replace('GNET_METADATA_END=1','symbol_attributes_json='+json.dumps(capture)+'\nGNET_METADATA_END=1'))
    with pytest.raises(ValueError,match='point value differs'):
        ts_export_bundle.finalize_session(folder)
    assert not (folder/'ready.json').exists()


def test_registered_inventory_keeps_metadata_and_pricing(capture):
    from gnet_broker.catalog import Catalog
    from gnet_broker.synthetic import dataset_manifest
    from gnet_jobs.contracts import DATASET_SCHEMA,validate
    manifest=dataset_manifest()
    manifest['sources'][0]['symbol_attributes']=capture
    validate(manifest,DATASET_SCHEMA)
    stub=SimpleNamespace(dataset=lambda identifier:SimpleNamespace(manifest=manifest),profile=lambda identifier:None)
    result=Catalog.inventory(stub,'fabricated-source')
    assert result['symbol_attributes']==capture
    assert result['instrument_specification']==manifest['instrument_specification']
    assert 'original_filename' not in result and 'vault_ref' not in result
