"""Actual imported-primary construction using wholly fabricated market observations."""
from copy import deepcopy
import csv
from datetime import datetime,timedelta
from decimal import Decimal
import json
from pathlib import Path
import os
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
BROKER=Path(os.environ.get('GNET_NATIVE_BROKER',ROOT/'.artifacts/GNET-NativeMultiAsset-v47-r1/guarded-v47-native-multiasset'))
sys.path.insert(0,str(BROKER))
# Root conftest preloads the independent live feature package. Exercise the
# candidate package's copy without editing the live checkout.
for _name in list(sys.modules):
    if _name=='feat_files' or _name.startswith('feat_files.'):
        del sys.modules[_name]
import types
_feature_package=types.ModuleType('feat_files')
_feature_package.__path__=[str(BROKER/'feat_files')]
sys.modules['feat_files']=_feature_package
from gnet_broker.synthetic import dataset_manifest
from gnet_broker.ts_processing import processing_context,native_supported,require_native_process
from gnet_broker.ts_export_names import source_name
from gnet_broker.ts_primary_trades import HEADER as TRADE_HEADER
from gnet_broker.ts_source_bars import HEADER as BAR_HEADER
from training_mlp.native_primary_training import build_native_observations
from training_mlp.tradestation_source import metadata_contract,load_ts_bars
from gnet_broker.feature_labels import feature_observations,ts_feature_contract,contract_hash,contracts_for_mode
from gnet_broker.dataset_capabilities import source_profile
from gnet_jobs.contracts import digest,ContractError


def fixture(folder,kind='stock',quantity=None):
    folder.mkdir(exist_ok=True)
    future=kind=='future';symbol='FUTX26' if future else 'TEST-STOCK'
    tick=Decimal('.25') if future else Decimal('.01');multiplier=20 if future else 1
    quantity=quantity or (2 if future else 3);cost=2 if future else .2
    zone='America/Chicago' if future else 'America/New_York'
    sessions=([{'session':'2026-01-06','open':'17:00:00','close':'16:00:00'}] if future else
        [{'session':'2026-01-06','open':'09:30:00','close':'16:00:00'},
         {'session':'2026-01-07','open':'09:30:00','close':'13:00:00'}])
    calendar={'calendar_id':'fabricated-'+kind,'timezone':zone,'evidence':'Fabricated test schedule',
        'start_session':sessions[0]['session'],'end_session':sessions[-1]['session'],'sessions':sessions,
        'chart_scope':{'asset':symbol,'session_name':'Fabricated','uses_regular_sessions':True,'synthetic':True}}
    points=[]
    for session in sessions:
        day=datetime.fromisoformat(session['session']);a=datetime.fromisoformat(session['session']+'T'+session['open']);b=datetime.fromisoformat(session['session']+'T'+session['close'])
        if a>b:a-=timedelta(days=1)
        current=a+timedelta(minutes=5)
        while current<=b:
            points.append(current);current+=timedelta(minutes=5)
    basename=source_name(symbol,'minutes',5,points[0].isoformat(),'exchange','trade_volume','unadjusted')
    bars=folder/basename;meta=folder/(basename+'.gnet-metadata.txt');trades=folder/(basename.removesuffix('.csv')+'.trades.csv')
    closes=[Decimal(100)+(i%8)*tick for i in range(len(points))]
    with bars.open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(BAR_HEADER)
        for i,(stamp,close) in enumerate(zip(points,closes),1):
            writer.writerow([i,i,stamp.isoformat(),close,close+3*tick,close-3*tick,close,10+i%5,5+i%3])
    params={'quantity':quantity,'long_enabled':True,'short_enabled':True,'round_trip_cost':cost,'warmup_bars':0,'inputs':[]}
    primary={'schema_version':'gnet-ts-primary-contract-3','name':trades.name,'strategy_id':'fabricated-primary',
        'strategy_code_sha256':'a'*64,'chart_export_id':'fabricated-export','rule_family':'fabricated','logic_revision':'fixture-1',
        'parameters':params,'order_semantics':'next_bar_market','entry_clock':'explicit_signal_bar',
        'reported_fill_clock':'ts_position_datetime_unverified','intrabar_order_generation':False,
        'position_mode':'single_full_exit','population':'executed_positions_only','execution_model':'ts_historical_simulation',
        'signal_comparison':'observed_signal_rows','bar_magnifier':'unverified',
        'engine_cost_settings':'unverified','point_value':multiplier,'pnl_currency_basis':'symbol_currency_unverified'}
    expected=[]
    with trades.open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(TRADE_HEADER)
        for seq,signal in enumerate(range(3,len(points)-4,7),1):
            entry=signal+1;exit_row=signal+3;side=1 if seq%2 else -1
            gross=Decimal(side)*(closes[exit_row-1]-closes[entry-1])*quantity*multiplier;net=gross-Decimal(str(cost))
            writer.writerow([seq,'t-'+str(seq),signal,side,quantity,'closed',entry,points[entry-1].isoformat(),
                closes[entry-1],exit_row,points[exit_row-1].isoformat(),closes[exit_row-1],gross,cost,net])
            expected.append(float(net))
    fields={'export_file':str(bars),'generated_at_local':'2026-01-08T12:00:00','chart_symbol':symbol,
        'chart_exchange':'FABRICATED','chart_bar_type':'1','chart_bar_interval':'5','chart_range_start':points[0].isoformat(),
        'chart_range_end':points[-1].isoformat(),'range_scope':'loaded_chart','timestamp_precision':'seconds',
        'max_bars_back':'1','declared_timezone':zone,'declared_volume_mode':'trade_volume','declared_price_basis':'unadjusted',
        'declared_interval_kind':'minutes','declared_timestamp_convention':'bar_close','export_file_verified':'false',
        'chart_timezone_mode':'1','chart_volume_gt_one_evidence':'0','chart_min_move':'1','chart_price_scale':'4' if future else '100'}
    meta.write_text('GNET_METADATA_BEGIN=1\n'+'\n'.join(k+'='+v for k,v in fields.items())+'\nGNET_METADATA_END=1\n')
    manifest=dataset_manifest('fabricated-'+kind)
    manifest.update(asset=symbol,provider_symbol=symbol,source_kind='source_bars',source_bar_kind='time',source_size=300,
        lifecycle_status='active',validation_status='pass',instrument_specification={'tick_size':float(tick),'multiplier':multiplier,'volume_units':'contracts' if future else 'shares'},
        instrument_profile={'profile_sha256':'a'*64,'exchange':'FABRICATED','country':'US','exchange_timezone':zone})
    manifest['contract_segments'][0].update(symbol=symbol,delivery_month=11 if future else None,delivery_year=2026 if future else None,
        start_session=sessions[0]['session'],end_session=sessions[-1]['session'])
    manifest['coverage'].update(first_event=points[0].replace(tzinfo=ZoneInfo(zone)).isoformat(),last_event=points[-1].replace(tzinfo=ZoneInfo(zone)).isoformat(),
        start_session=sessions[0]['session'],end_session=sessions[-1]['session'],timezone=zone,partial_sessions=[],session_count=len(sessions),row_count=len(points))
    manifest['session_policy'].update(open=sessions[0]['open'],close=sessions[0]['close'],calendar_version=calendar['calendar_id'],
        close_overrides=[{'session':s['session'],'close':s['close']} for s in sessions if s['close']!=sessions[0]['close']])
    manifest['sources'][0].update(symbol=symbol,contract=symbol,timezone=zone,first_event=manifest['coverage']['first_event'],last_event=manifest['coverage']['last_event'],row_count=len(points))
    contract={'schema_version':'gnet-ts-training-source-2','strategy':primary['strategy_id'],
        'development_end':manifest['coverage']['last_event'],'order_timing':'next_bar_market',
        'trade_timestamp_convention':'explicit_signal_row','contracts_column':'Quantity','round_trip_cost':cost,
        'reported_fills_include_slippage':True,'exclude_last_bar':True,'primary_contract':primary,
        'fill_properties_reviewed':False,'platform_snapshot_reviewed':False,'fill_review_basis':'validated_recorded_ledger'}
    return bars,trades,meta,contract,manifest,calendar,expected


@pytest.mark.parametrize('kind',['stock','future'])
def test_non_es_positions_produce_real_labels_and_features(tmp_path,kind):
    bars,trades,meta,contract,manifest,calendar,expected=fixture(tmp_path/kind,kind)
    result=build_native_observations(bars,trades,meta,contract,series_manifest=manifest,session_calendar=calendar)
    observed,directions,features,rows,reasons,provenance=result
    assert [r['net_pnl'] for r in rows]==pytest.approx(expected)
    eligible=[r for r in rows if r['eligible']]
    assert len(eligible)>=8 and all(r['quantity']==contract['primary_contract']['parameters']['quantity'] for r in rows)
    assert all(r['Label']==int(r['net_pnl']>0) for r in eligible)
    assert all(np.isfinite([r[n] for n in ts_feature_contract(300)['names']]).all() for r in eligible)
    assert observed[0]['session']==calendar['sessions'][0]['session']
    assert native_supported(manifest)
    require_native_process(manifest,'training')
    profile=source_profile(manifest,approved=['bar_features','training'])
    assert profile['capabilities']['bar_features']['enabled']
    assert not profile['capabilities']['primary_research']['enabled']
    with pytest.raises(ContractError):require_native_process(manifest,'primary_research')


def test_stock_early_close_and_next_session_vwap_reset(tmp_path):
    bars,trades,meta,contract,manifest,calendar,_=fixture(tmp_path)
    observed,_,features,_,_,_=build_native_observations(bars,trades,meta,contract,series_manifest=manifest,session_calendar=calendar)
    last=features[observed[-1]['bar_id']]['features']
    assert last['minutes_since_open']==210
    assert last['is_first_last_30min']==1
    first_day_end=features[observed[77]['bar_id']]['features']
    assert first_day_end['minutes_since_open']==390
    next_open=features[observed[78]['bar_id']]['features']
    assert next_open['minutes_since_open']==5 and next_open['vwap_distance']==pytest.approx(0)


def test_non_es_future_clock_uses_overnight_session_date(tmp_path):
    bars,trades,meta,contract,manifest,calendar,_=fixture(tmp_path,'future')
    observed,_,features,_,_,_=build_native_observations(bars,trades,meta,contract,series_manifest=manifest,session_calendar=calendar)
    first=features[observed[59]['bar_id']]['features']
    assert first['minutes_since_open']==300
    assert first['day_of_week']==1  # Tuesday session, although the opening bars occur Monday.


def test_bad_multiplier_or_calendar_is_rejected(tmp_path):
    bars,trades,meta,contract,manifest,calendar,_=fixture(tmp_path)
    bad=deepcopy(contract);bad['primary_contract']['point_value']=50
    with pytest.raises(ContractError,match='point value differs'):
        build_native_observations(bars,trades,meta,bad,series_manifest=manifest,session_calendar=calendar)
    with pytest.raises(ContractError,match='calendar'):
        build_native_observations(bars,trades,meta,contract,series_manifest=manifest)
    changed=deepcopy(calendar);changed['chart_scope']['asset']='OTHER'
    with pytest.raises(ContractError,match='scope differs'):
        build_native_observations(bars,trades,meta,contract,series_manifest=manifest,session_calendar=changed)


def test_context_hash_versions_and_stock_preflight(tmp_path):
    _,_,_,_,manifest,calendar,_=fixture(tmp_path)
    from gnet_broker.validation import preflight
    identity={'dataset_id':manifest['dataset_id'],'data_hash':manifest['data_hash'],'config_hash':digest({}),
        'release_id':'fixture','code_hash':'a'*64,'dependency_hash':'b'*64,'execution_id':'c'*64,'search_id':None,'attempt_id':'fixture'}
    report=preflight(manifest,identity,'ts_native_recorded',content_verified=True,calendar=calendar)
    assert report['usable'],report
    feature=ts_feature_contract(300,calendar_bound=True)
    assert feature['version']=='ma13-ts-calendar300-v2'
    assert contracts_for_mode('tradestation',feature_version=feature['version'])[0]==feature
    assert contract_hash('tradestation',feature_version=feature['version'])!=contract_hash('tradestation',feature_version='ma13-ts-time300-v1')


@pytest.mark.parametrize('kind',['stock','future'])
def test_actual_workers_build_targets_training_and_load_model_input(tmp_path,kind):
    import shutil
    from gnet_broker.catalog import Catalog
    from gnet_broker.artifacts import register_artifact
    from gnet_broker.validation import record,check
    from gnet_broker.calendar import register_calendar
    from gnet_broker.primary_labels import build_primary_labels
    from gnet_broker.tradestation_training import build_tradestation_training_dataset
    from training_mlp.tradestation_source import source_receipts
    from training_mlp.research_dataset import load_research_dataset
    from gnet_jobs.io import atomic_json
    catalog=Catalog(tmp_path/'state',tmp_path/'vault',synthetic_only=True)
    source_path=catalog.vault/'source'
    source_path.mkdir()
    bars,trades,meta,contract,manifest,calendar,_=fixture(source_path/'originals',kind)
    profile=source_profile(manifest,{'source':{'interval_kind':'minutes','interval_size':5},'export_id':'fabricated-export'},['bar_features','training'])
    manifest=catalog.register('dataset',manifest,source_path,profile=profile)
    register_calendar(catalog,calendar)
    release={'schema_version':'1.0','release_id':'fixture-release','code_hash':'a'*64,'dependency_hash':'b'*64,'operations':['build_training_dataset']}
    catalog.register('release',release)
    identity={'dataset_id':manifest['dataset_id'],'data_hash':manifest['data_hash'],'config_hash':digest({}),
        'release_id':release['release_id'],'code_hash':release['code_hash'],'dependency_hash':release['dependency_hash'],
        'execution_id':'c'*64,'search_id':None,'attempt_id':'fixture'}
    staged=catalog.vault/'staged'
    staged.mkdir()
    for path in (bars,trades,meta):shutil.copyfile(path,staged/path.name)
    receipts=source_receipts([staged/p.name for p in (bars,trades,meta)])
    atomic_json(staged/'source.json',{'schema_version':'gnet-ts-staged-1','files':[p.name for p in (bars,trades,meta)],'contract':contract,'source_receipts':receipts})
    validation=record(identity,'postflight',[check('fabricated_parent',True)])
    parent=register_artifact(catalog,SimpleNamespace(payload={'dataset_id':manifest['dataset_id']},job_id='fixture-parent'),
        SimpleNamespace(identity=identity),'training_source',staged,[],[{'kind':'time','size':300}],validation)
    def request(job,payload):
        from gnet_jobs.contracts import Request
        operation='build_primary_labels' if job=='fixture-labels' else 'build_training_dataset'
        if operation=='build_training_dataset':payload={**payload,'input_mode':'tradestation'}
        return Request.parse({'schema_version':'1.0','payload':payload,'job_id':job,'operation':operation,
            'release_id':release['release_id'],'limits':{'workers':1,'wall_seconds':180,'memory_mb':2048},'output_level':'reports_and_metrics'})
    work=catalog.vault/'labels-job';work.mkdir()
    labels=build_primary_labels(catalog,request('fixture-labels',{'source_artifact_id':parent['artifact_id']}),work)
    assert labels.usable
    work=catalog.vault/'training-job';work.mkdir()
    training=build_tradestation_training_dataset(catalog,request('fixture-training',{'source_artifact_id':parent['artifact_id'],
        'primary_labels_artifact_id':labels.artifact_ids[0]}),work)
    assert training.usable,training
    ref=catalog.artifact(training.artifact_ids[0],'training_dataset',release['release_id'])
    assert manifest['asset'] in ref.manifest['artifact_id']
    assert catalog.profile(ref.manifest['artifact_id'])['capabilities']['training']['enabled']
    catalog.require_capability(ref.manifest['artifact_id'],'training')
    loaded=load_research_dataset(catalog,ref.manifest['artifact_id'],release['release_id'])
    assert loaded.features.shape[0]>=8 and loaded.features.shape[1]==13
    assert np.isfinite(loaded.features).all() and set(loaded.labels)<= {0,1}
    assert loaded.contract['processing_context']['instrument_specification']==manifest['instrument_specification']


def test_artifact_names_preserve_asset_and_encode_non_identifier_symbols():
    from gnet_broker.artifacts import artifact_id
    manifest=dataset_manifest()
    manifest['asset']='ETF'
    manifest['contract_segments'][0]['symbol']='$SOME.INDEX'
    result=artifact_id('features',manifest,SimpleNamespace(payload={},job_id='fixture-job'))
    from gnet_jobs.contracts import ID,validate
    validate(result,ID)
    assert '__ETF__' in result and '$' not in result


def test_dst_boundaries_use_the_dated_exchange_clock():
    from gnet_broker.ts_processing import SessionIndex
    calendar={'calendar_id':'fabricated-dst','timezone':'America/New_York','evidence':'Fabricated dates',
        'start_session':'2026-03-06','end_session':'2026-03-09','sessions':[
            {'session':'2026-03-06','open':'09:30:00','close':'16:00:00'},
            {'session':'2026-03-09','open':'09:30:00','close':'16:00:00'}]}
    index=SessionIndex(calendar,{'calendar_sha256':digest(calendar)})
    ns=lambda s:int(datetime.fromisoformat(s).timestamp()*1_000_000_000)
    winter=index.bind(ns('2026-03-06T14:35:00+00:00'),300)
    summer=index.bind(ns('2026-03-09T13:35:00+00:00'),300)
    assert (ns('2026-03-06T14:35:00+00:00')-winter['session_open_ns'])/60e9==5
    assert (ns('2026-03-09T13:35:00+00:00')-summer['session_open_ns'])/60e9==5
    with pytest.raises(ContractError):index.bind(ns('2026-03-09T13:00:00+00:00'),300)


def test_negative_prices_get_explicit_feature_exclusion(tmp_path):
    bars,trades,meta,contract,manifest,calendar,_=fixture(tmp_path)
    with bars.open(newline='') as stream:rows=list(csv.reader(stream))
    rows[70][3:7]=['-1.00','-0.90','-1.10','-1.00']
    with bars.open('w',newline='') as stream:csv.writer(stream).writerows(rows)
    metadata=metadata_contract(bars,meta,series_manifest=manifest,session_calendar=calendar)
    observed,directions,_,_,_=load_ts_bars(bars,metadata,contract['development_end'],session_calendar=calendar)
    features=feature_observations(observed,directions,duration_seconds=300,processing_context=metadata['processing_context'])
    assert features[observed[69]['bar_id']]['reason']=='nonpositive_price_features'
    assert features[observed[70]['bar_id']]['reason']=='warmup'


def test_position_quantity_mismatch_does_not_change_labels_silently(tmp_path):
    bars,trades,meta,contract,manifest,calendar,_=fixture(tmp_path)
    with trades.open(newline='') as stream:rows=list(csv.reader(stream))
    rows[1][4]='1'
    with trades.open('w',newline='') as stream:csv.writer(stream).writerows(rows)
    with pytest.raises(ValueError,match='quantity contract differs'):
        build_native_observations(bars,trades,meta,contract,series_manifest=manifest,session_calendar=calendar)


def test_default_feature_engine_preserves_legacy_clock_and_vwap():
    from feat_files.canonical_features import FeatureEngine
    engine=FeatureEngine()
    def bar(seconds,close=100):
        return SimpleNamespace(date=1260105,time_s=seconds,open=float(close),high=close+.25,low=close-.25,
            close=float(close),up=10,down=5,vwap=float(close))
    for i in range(60):value=engine.update(bar(34200+(i+1)*30))
    assert value.minutes_since_open==30 and value.is_first_last_30min==1
    assert value.vwap_distance==pytest.approx(0)
    value=engine.update(bar(64800,110))
    assert value.vwap_distance==pytest.approx(0)  # Existing 18:00 reset remains the default.
