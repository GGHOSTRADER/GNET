"""Generic review tests with invented asset metadata and no market data."""
from copy import deepcopy
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
BROKER=Path(os.environ.get('GNET_REVIEW_BROKER',ROOT/'.artifacts/GNET-MultiAssetReview-v45-r1/guarded-v45-multi-asset-review'))
sys.path.insert(0,str(BROKER))
from gnet_broker.instrument_profiles import install_profile, resolve_profile, require_manifest_profile
from gnet_broker import ts_review_template
from gnet_broker.publication import bounded_tree
from gnet_broker.ts_series import template_series, series_problems
from gnet_broker.dataset_capabilities import source_profile
from gnet_broker.synthetic import dataset_manifest
from gnet_jobs.contracts import ContractError, DATASET_SCHEMA, digest, validate


@pytest.fixture
def catalog(tmp_path):
    protected=tmp_path/'protected'
    protected.mkdir()
    return SimpleNamespace(protected=protected,vault=tmp_path/'vault',synthetic_only=True)


@pytest.fixture
def profile():
    return {'schema_version':'gnet-instrument-profile-1','symbol':'$FABRICATED-STOCK',
        'source_series_type':'unclassified','asset':'TEST-STOCK','exchange':'TEST-US-EXCHANGE',
        'country':'US','exchange_timezone':'America/New_York',
        'specification':{'tick_size':.01,'multiplier':1,'volume_units':'shares'},
        'series_type':'outright','delivery_month':None,'delivery_year':None,
        'evidence':'Fabricated unit-test facts; not a real instrument specification'}


def source(profile):
    return {'symbol':profile['symbol'],'series_type':profile['source_series_type'],
        'min_move':1,'price_scale':100,'source_timezone':'America/New_York',
        'interval_kind':'minutes','interval_size':5,'observed_session_name':'Fabricated',
        'uses_regular_sessions':True}


def save(catalog,profile):
    return install_profile(catalog,profile,reviewer_evidence='Fabricated reviewer',synthetic_test=True)


def test_exact_profile_is_saved_and_reused(catalog,profile):
    save(catalog,profile)
    assert resolve_profile(catalog,source(profile))==profile
    assert save(catalog,profile)['research_permissions_granted'] is False
    assert resolve_profile(catalog,{**source(profile),'symbol':'OTHER'}) is None


def test_unknown_symbol_does_not_inherit_es(catalog,profile):
    assert resolve_profile(catalog,source(profile)) is None
    es=resolve_profile(catalog,{'symbol':'ESZ26','series_type':'individual_contract','min_move':25,'price_scale':100})
    assert es['asset']=='ES' and es['specification']['multiplier']==50


def test_profile_rejects_changed_increment(catalog,profile):
    save(catalog,profile)
    with pytest.raises(ContractError,match='price increment'):
        resolve_profile(catalog,{**source(profile),'min_move':2})


def test_profile_cannot_be_replaced(catalog,profile):
    save(catalog,profile)
    altered=deepcopy(profile)
    altered['specification']['multiplier']=50
    with pytest.raises(ContractError,match='already differs'):
        save(catalog,altered)


def test_profile_requires_review_commit(catalog,profile):
    save(catalog,profile)
    marker=next((catalog.protected/'ts-review-activations').glob('instrument-*.json'))
    import json
    receipt=json.loads(marker.read_text())
    receipt['profile_sha256']='0'*64
    marker.write_text(json.dumps(receipt))
    with pytest.raises(ContractError,match='reviewed identity'):
        resolve_profile(catalog,source(profile))


def test_generic_manifest_retains_economics_and_blocks_es_engine(catalog,profile):
    save(catalog,profile)
    manifest=dataset_manifest()
    manifest.update(asset=profile['asset'],provider_symbol=profile['symbol'],
        instrument_specification=profile['specification'],instrument_profile={
            'profile_sha256':digest(profile),'exchange':profile['exchange'],'country':profile['country'],
            'exchange_timezone':profile['exchange_timezone']})
    manifest['contract_segments'][0].update(symbol=profile['symbol'],delivery_month=None,delivery_year=None)
    validate(manifest,DATASET_SCHEMA)
    require_manifest_profile(catalog,manifest,source(profile))
    assert not series_problems(manifest,source(profile),[])
    capabilities=source_profile(manifest,approved=['bar_features'])['capabilities']
    assert all(not value['enabled'] for value in capabilities.values())
    altered=deepcopy(manifest)
    altered['instrument_specification']['multiplier']=50
    with pytest.raises(ContractError,match='settings differ'):
        require_manifest_profile(catalog,altered,source(profile))


def test_generic_series_does_not_invent_futures_delivery(profile):
    kind,segments,_=template_series(source(profile),profile)
    assert kind=='outright'
    assert segments[0]['symbol']==profile['symbol']
    assert segments[0]['delivery_month'] is None and segments[0]['delivery_year'] is None


def test_generic_specification_cannot_enable_es_calculations_by_relabeling(catalog,profile):
    profile['asset']='ES'
    with pytest.raises(ContractError,match='different instrument economics'):
        save(catalog,profile)


def test_viewer_retains_manifest_asset():
    from gnet_broker.viewer import render_view
    manifest=dataset_manifest()
    manifest['asset']='TEST-STOCK'
    html=render_view({'bar_definition':{'kind':'time','size':300}},
        SimpleNamespace(dictionary=lambda:{}),manifest,{'status':'pass','usable':True})
    assert '"asset":"TEST-STOCK"' in html


@pytest.mark.parametrize('known', [False,True])
def test_pending_review_reports_missing_profile_or_matching_calendar(catalog,profile,monkeypatch,known):
    if known:
        save(catalog,profile)
    src=source(profile)
    bundle={'source':src}
    receipt={'custody_committed':True,'row_contract_status':'pass','bundle_sha256':digest(bundle),
        'first_timestamp':'2026-01-05T09:35:00','last_timestamp':'2026-01-05T16:00:00','rows':78}
    docs={'bundle.json':bundle,'custody-receipt.json':receipt}
    monkeypatch.setattr(ts_review_template,'read_json',lambda path,*args:docs[Path(path).name])
    result=ts_review_template.ts_review_template(catalog,
        SimpleNamespace(payload={'export_id':'fabricated-export','automatic_checks':True,'synthetic':True}),Path('unused'))
    value=result.metrics['review_template']
    bounded_tree(result.metrics)
    assert result.usable and result.validation_status=='pending'
    assert value['source']['symbol']==profile['symbol']
    assert value['needs_instrument_profile'] if not known else value['needs_calendar']
    assert 'policy' not in value


@pytest.mark.parametrize('wrong_asset', [False,True])
def test_known_instrument_uses_its_own_calendar_and_manifest(catalog,profile,monkeypatch,wrong_asset):
    save(catalog,profile)
    src={**source(profile),'price_basis':'unadjusted','timestamp_convention':'bar_close'}
    bundle={'source':src,'files':[{'role':'bars','name':'bars.csv','sha256':'a'*64,'bytes':100}],
        'finalized_at_utc':'2026-01-05T21:00:00+00:00','producer':{'exporter_sha256':'b'*64}}
    receipt={'custody_committed':True,'row_contract_status':'pass','bundle_sha256':digest(bundle),
        'first_timestamp':'2026-01-05T09:35:00','last_timestamp':'2026-01-05T16:00:00','rows':78}
    calendar={'calendar_id':'fabricated-calendar','timezone':'America/New_York',
        'evidence':'Fabricated session reference','start_session':'2026-01-05','end_session':'2026-01-05',
        'sessions':[{'session':'2026-01-05','open':'09:30:00','close':'16:00:00'}],
        'chart_scope':{'asset':'ES' if wrong_asset else profile['asset'],'session_name':'Fabricated',
            'uses_regular_sessions':True,'synthetic':True}}
    docs={'bundle.json':bundle,'custody-receipt.json':receipt}
    monkeypatch.setattr(ts_review_template,'read_json',lambda path,*args:docs[Path(path).name])
    request=SimpleNamespace(payload={'export_id':'fabricated-export','automatic_checks':False,
        'synthetic':True,'calendar':calendar},job_id='fabricated-job',release_id='fabricated-release')
    if wrong_asset:
        with pytest.raises(ContractError,match='instrument asset'):
            ts_review_template.ts_review_template(catalog,request,Path('unused'))
        return
    result=ts_review_template.ts_review_template(catalog,request,Path('unused'))
    manifest=result.metrics['review_template']['policy']['manifest']
    assert manifest['asset']==profile['asset']
    assert manifest['instrument_specification']==profile['specification']
    assert manifest['coverage']['timezone']=='America/New_York'
    bounded_tree(result.metrics)


def test_training_capability_resolves_artifact_parent_without_breaking_es():
    from gnet_broker.catalog import Catalog
    stub=SimpleNamespace(profile=lambda identifier:{'dataset_id':'parent-es','origin_export_id':None},
        dataset=lambda identifier:SimpleNamespace(manifest={'asset':'ES'}) if identifier=='parent-es' else None)
    Catalog.require_capability(stub,'training-artifact','training')
    stub.dataset=lambda identifier:SimpleNamespace(manifest={'asset':'TEST-STOCK'})
    with pytest.raises(ContractError,match='asset-specific'):
        Catalog.require_capability(stub,'training-artifact','training')
