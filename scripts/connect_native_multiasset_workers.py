"""Connect only imported-source workers to their reviewed calendar context."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'.artifacts/GNET-NativeMultiAsset-v47-r1/guarded-v47-native-multiasset'


def patch(name,changes):
    path=ROOT/name;text=path.read_text(encoding='utf-8')
    inventory=lambda s:[(n.name,[m.name for m in n.body if isinstance(m,ast.FunctionDef)] if isinstance(n,ast.ClassDef) else []) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    before=inventory(text)
    for old,new,count in changes:
        if text.count(old)!=count:raise RuntimeError('Worker anchor differs '+name+': '+old[:100])
        text=text.replace(old,new)
    if inventory(text)!=before:raise RuntimeError('Definition inventory changed')
    path.write_text(text,encoding='utf-8')


def main():
    patch('gnet_broker/feature_labels.py',[
        ('def ts_feature_contract(duration_seconds):', '''TS_CALENDAR_30_CONTRACT={**TS_FEATURE_CONTRACT,'version':'ma13-ts-calendar30-v2',
    'timezone':'reviewed dated calendar','vwap_reset_local_seconds':None,
    'session_clock':'dated session open/close; inclusive close boundary',
    'amihud_units':'price * traded units * instrument multiplier',
    'directional_volume':'validated native traded units; shares/contracts/units'}
TS_CALENDAR_300_CONTRACT={**TS_CALENDAR_30_CONTRACT,'version':'ma13-ts-calendar300-v2',
    'bar_series':'time_300','duration_seconds':300,'window_units':'completed observations'}


def ts_feature_contract(duration_seconds, *, calendar_bound=False):''',1),
        ('    return TS_FEATURE_CONTRACT if duration_seconds == 30 else TS_FIVE_MINUTE_CONTRACT',
         '    if calendar_bound:return TS_CALENDAR_30_CONTRACT if duration_seconds==30 else TS_CALENDAR_300_CONTRACT\n    return TS_FEATURE_CONTRACT if duration_seconds == 30 else TS_FIVE_MINUTE_CONTRACT',1),
        ('if input_mode == "tradestation": supported[TS_FIVE_MINUTE_CONTRACT["version"]] = TS_FIVE_MINUTE_CONTRACT',
         'if input_mode == "tradestation":\n            supported.update({c["version"]:c for c in (TS_FIVE_MINUTE_CONTRACT,TS_CALENDAR_30_CONTRACT,TS_CALENDAR_300_CONTRACT)})',1),
    ])
    patch('gnet_broker/source_features.py',[
        ('    metadata=metadata_contract(bars_path,metadata_path,series_manifest=source.manifest)',
         '    from gnet_broker.calendar import calendar_for\n    calendar=calendar_for(catalog,source.manifest)\n    metadata=metadata_contract(bars_path,metadata_path,series_manifest=source.manifest,session_calendar=calendar)',1),
        ("load_ts_bars(bars_path,metadata,source.manifest['coverage']['last_event'])","load_ts_bars(bars_path,metadata,source.manifest['coverage']['last_event'],session_calendar=calendar)",1),
        ("ts_feature_contract(source.manifest['source_size'])","ts_feature_contract(source.manifest['source_size'],calendar_bound=bool(metadata.get('processing_context')))",1),
        ("feature_observations(bars,directions,duration_seconds=source.manifest['source_size'])","feature_observations(bars,directions,duration_seconds=source.manifest['source_size'],processing_context=metadata.get('processing_context'))",1),
    ])
    patch('gnet_broker/ts_primary_source.py',[
        ('    metadata=metadata_contract(paths[0],paths[2],series_manifest=manifest)',
         '    from gnet_broker.calendar import calendar_for\n    metadata=metadata_contract(paths[0],paths[2],series_manifest=manifest,session_calendar=calendar_for(catalog,manifest))',1),
    ])
    patch('gnet_broker/primary_labels.py',[
        ('    metadata=metadata_contract(paths[0],paths[2],series_manifest=dataset.manifest)',
         '    from gnet_broker.calendar import calendar_for\n    calendar=calendar_for(catalog,dataset.manifest)\n    metadata=metadata_contract(paths[0],paths[2],series_manifest=dataset.manifest,session_calendar=calendar)',1),
        ("load_ts_bars(paths[0],metadata,contract['development_end'])","load_ts_bars(paths[0],metadata,contract['development_end'],session_calendar=calendar)",1),
    ])
    patch('gnet_broker/comparison_reports.py',[
        ('    metadata = metadata_contract(bars_path, metadata_path, series_manifest=manifest)',
         '    from gnet_broker.calendar import calendar_for\n    calendar=calendar_for(catalog,manifest)\n    metadata = metadata_contract(bars_path, metadata_path, series_manifest=manifest,session_calendar=calendar)',1),
        ("load_ts_bars(bars_path, metadata, pd.Timestamp(end, unit='ns', tz='UTC').isoformat())",
         "load_ts_bars(bars_path, metadata, pd.Timestamp(end, unit='ns', tz='UTC').isoformat(),session_calendar=calendar)",1),
    ])
    patch('gnet_broker/tradestation_training.py',[
        ('    feature_contract = ts_feature_contract(dataset.manifest["source_size"])',
         '    from gnet_broker.ts_processing import processing_context\n    calendar=calendar_for(catalog,dataset.manifest)\n    context=processing_context(dataset.manifest,calendar)\n    feature_contract = ts_feature_contract(dataset.manifest["source_size"],calendar_bound=True)',1),
        ('    if request.payload.get(\'primary_labels_artifact_id\'):settings',
         "    settings['processing_context']=context\n    if request.payload.get('primary_labels_artifact_id'):settings",1),
        ('build_ts_observations(*paths, contract, series_manifest=dataset.manifest)',
         'build_ts_observations(*paths, contract, series_manifest=dataset.manifest,session_calendar=calendar)',1),
    ])
    patch('training_mlp/research_dataset.py',[
        ('    frame = pd.read_parquet(ref.path / "training.parquet")', '''    if feature_version in ('ma13-ts-calendar30-v2','ma13-ts-calendar300-v2'):
        from gnet_broker.ts_processing import processing_context
        from gnet_broker.calendar import calendar_for
        source=catalog.dataset(ref.manifest['dataset_id']).manifest
        require(settings.get('processing_context')==processing_context(source,calendar_for(catalog,source)),
            'training_contract','Instrument or calendar processing context differs from the immutable training dataset')
    frame = pd.read_parquet(ref.path / "training.parquet")''',1),
    ])
    patch('gnet_broker/catalog.py',[
        ("        if self.dataset(source_id).manifest['asset'] != 'ES':\n            raise ContractError('asset_adapter','This research operation requires an asset-specific calculation adapter')",
         "        from gnet_broker.ts_processing import require_native_process\n        require_native_process(self.dataset(source_id).manifest,process)",1),
        ("        if self.dataset(identifier).manifest['asset'] != 'ES':\n            raise ContractError('asset_adapter','This research operation requires an asset-specific calculation adapter')",
         "        from gnet_broker.ts_processing import require_native_process\n        require_native_process(self.dataset(identifier).manifest,process)",1),
    ])
    patch('gnet_broker/dataset_capabilities.py',[
        ("    if manifest['asset'] != 'ES':\n        caps = {p:{'enabled':False,'reason':'Source metadata can be reviewed; this research engine still requires an asset-specific calculation adapter'} for p in PROCESSES}",
         "    if manifest['asset'] != 'ES':\n        from gnet_broker.ts_processing import native_supported\n        for p in PROCESSES:\n            if p not in ('bar_features','training') or not native_supported(manifest):\n                caps[p]={'enabled':False,'reason':'Select a supported recorded-primary source and reviewed instrument/session contract'}",1),
    ])
    print('Recorded-source workers, versioned feature contracts and capability gates connected.')


if __name__=='__main__':main()
