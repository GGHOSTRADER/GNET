"""Exact-block changes for the recorded-primary processing route."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'.artifacts/GNET-NativeMultiAsset-v47-r1/guarded-v47-native-multiasset'


def patch(name,changes):
    path=ROOT/name;text=path.read_text(encoding='utf-8')
    inventory=lambda s:[(n.name,[m.name for m in n.body if isinstance(m,ast.FunctionDef)] if isinstance(n,ast.ClassDef) else []) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    before=inventory(text)
    for old,new,count in changes:
        if text.count(old)!=count:raise RuntimeError('Unexpected anchor '+name+': '+old[:100])
        text=text.replace(old,new)
    if inventory(text)!=before:raise RuntimeError('Existing definitions changed: '+name)
    path.write_text(text,encoding='utf-8')


def main():
    patch('feat_files/canonical_features.py',[
        ('    def update(self, bar: Any) -> FeatureValues | None:', '    def update(self, bar: Any, *, session_id: str | None = None) -> FeatureValues | None:',1),
        ('        if session_date != self._date:', '        if session_id is not None:\n            session_date = session_id\n        if session_date != self._date:',1),
    ])
    patch('training_mlp/tradestation_source.py',[
        ('def metadata_contract(bars_path, metadata_path, *, series_manifest=None):','def metadata_contract(bars_path, metadata_path, *, series_manifest=None, session_calendar=None):',1),
        ('    if not re.fullmatch(r"ES[HMUZ][0-9]{2}", observed["chart_symbol"]):\n        from gnet_broker.ts_series import require_training_series\n        require_training_series(series_manifest, observed["chart_symbol"])',
         '''    from gnet_broker.ts_processing import processing_context
    if series_manifest is not None:
        from gnet_jobs.contracts import Manifest
        Manifest.parse('dataset',series_manifest)
        require(series_manifest['provider_symbol']==observed['chart_symbol'],'ts_metadata','Manifest symbol differs from the exact export')
        grid=summary.get('price_grid',{'min_move':1,'price_scale':4})
        require(abs(grid['min_move']/grid['price_scale']-series_manifest['instrument_specification']['tick_size'])<1e-12,
            'ts_metadata','Exported price grid differs from reviewed instrument specification')
        summary['instrument_specification']=series_manifest['instrument_specification']
        if session_calendar is not None:
            summary['processing_context']=processing_context(series_manifest,session_calendar)
        elif series_manifest['asset']!='ES':
            require(False,'ts_calendar','Non-ES processing requires its reviewed dated calendar')
    if series_manifest is not None and series_manifest['series_type']=='provider_continuous':
        from gnet_broker.ts_series import require_training_series
        require_training_series(series_manifest, observed['chart_symbol'])
    elif series_manifest is None and not re.fullmatch(r"ES[HMUZ][0-9]{2}", observed['chart_symbol']):
        require(False,'ts_metadata','A reviewed instrument manifest is required')''',1),
        ('def load_ts_bars(path, metadata, development_end):','def load_ts_bars(path, metadata, development_end, *, session_calendar=None):',1),
        ('    rows, directions, previous, count, source_first = [], [], None, 0, None',
         "    from gnet_broker.ts_processing import metadata_spec,grid_price,SessionIndex\n    spec=metadata_spec(metadata);tick_size=spec['tick_size']\n    context=metadata.get('processing_context')\n    require(not context or session_calendar is not None,'ts_calendar','Dated session context is required')\n    sessions=SessionIndex(session_calendar,context) if context else None\n    rows, directions, previous, count, source_first = [], [], None, 0, None",1),
        ('all(values[n] > 0 and abs(values[n] / .25 - round(values[n] / .25)) < 1e-8 for n in ("open", "high", "low", "close"))',
         'all(grid_price(values[n],tick_size) and (versioned or values[n]>0) for n in ("open", "high", "low", "close"))',1),
        ('TS bars require finite coherent ES tick-grid OHLC','TS bars require finite coherent instrument-grid OHLC',1),
        ('TS Up/Down must be nonnegative whole traded-contract quantities','TS Up/Down must be nonnegative whole traded-volume units',1),
        ('        local = stamp.tz_convert(FEATURE_CONTRACT["timezone"])\n        session = (local + pd.Timedelta(hours=6)).strftime("%Y-%m-%d")',
         '        local = stamp.tz_convert(FEATURE_CONTRACT["timezone"])\n        session = (local + pd.Timedelta(hours=6)).strftime("%Y-%m-%d")\n        binding=sessions.bind(ns,duration) if sessions else {}',1),
        ('"session": session, "vintage": observed["chart_symbol"] + "__" + declared["price_basis"]})',
         '"session": session, "vintage": observed["chart_symbol"] + "__" + declared["price_basis"],**binding})',1),
        ('    quantity = contract["contracts_column"]','    quantity = contract["contracts_column"]\n    from gnet_broker.ts_processing import metadata_spec,grid_price\n    spec=metadata_spec(metadata)',1),
        ('        require(number(entry[quantity]) == 1 and number(exit[quantity]) == 1,\n                "ts_quantity", "Both TS fills must declare one ES contract; scaling requires another contract")',
         '''        units=number(entry[quantity]);expected=contract.get('quantity',None if metadata.get('processing_context') else 1)
        require(units>0 and units.is_integer() and units<=1000000 and number(exit[quantity])==units
            and (expected is None or units==expected),'ts_quantity','Paired whole-position quantities must agree with the declared quantity')''',1),
        ('all(p is None or (p > 0 and abs(p / .25 - round(p / .25)) < 1e-8) for p in prices)',
         "all(p is None or grid_price(p,spec['tick_size']) for p in prices)",1),
        ('TS fills must be finite positive ES tick-grid prices','TS fills must match the reviewed instrument price grid',1),
        ('side * (prices[1] - prices[0]) * 50','side * (prices[1] - prices[0]) * units * spec["multiplier"]',1),
        ('"entry_price": prices[0], "exit_price": prices[1], "side": side,','"entry_price": prices[0], "exit_price": prices[1], "side": side, "quantity":int(units),',1),
        ('def build_ts_observations(bars_path, trades_path, metadata_path, contract, *, series_manifest=None):',
         'def build_ts_observations(bars_path, trades_path, metadata_path, contract, *, series_manifest=None, session_calendar=None):',1),
        ('build_native_observations(bars_path,trades_path,metadata_path,contract,series_manifest=series_manifest)',
         'build_native_observations(bars_path,trades_path,metadata_path,contract,series_manifest=series_manifest,session_calendar=session_calendar)',1),
        ('metadata = metadata_contract(bars_path, metadata_path)','metadata = metadata_contract(bars_path, metadata_path,series_manifest=series_manifest,session_calendar=session_calendar)',1),
        ('load_ts_bars(bars_path, metadata, contract["development_end"])','load_ts_bars(bars_path, metadata, contract["development_end"],session_calendar=session_calendar)',1),
        ('features = feature_observations(bars, directions, duration_seconds=ts_duration(metadata))','features = feature_observations(bars, directions, duration_seconds=ts_duration(metadata),processing_context=metadata.get("processing_context"))',1),
        ('side * (exit fill - entry fill) * ES multiplier 50 - declared round-trip cost; report percent-profit unused',
         'side * (exit fill - entry fill) * recorded quantity * reviewed multiplier - declared total position cost; report percent-profit unused',1),
    ])
    path=ROOT/'training_mlp/tradestation_source.py'
    text=path.read_text(encoding='utf-8')
    anchor='\n\ndef source_receipts(paths):'
    if text.count(anchor)!=1:raise RuntimeError('Source contract anchor differs')
    text=text.replace(anchor,"\nSOURCE_CONTRACT['properties']['quantity']={'type':'integer','minimum':1,'maximum':1000000}\n"+anchor)
    path.write_text(text,encoding='utf-8')
    patch('training_mlp/native_primary_training.py',[
        ('def build_native_observations(bars_path,trades_path,metadata_path,contract,*,series_manifest=None):',
         'def build_native_observations(bars_path,trades_path,metadata_path,contract,*,series_manifest=None,session_calendar=None):',1),
        ("primary['strategy_id']==contract['strategy'] and parameters['quantity']==1\n        and primary['point_value']==50 and parameters['round_trip_cost']==contract['round_trip_cost']",
         "primary['strategy_id']==contract['strategy'] and parameters['quantity']>=1\n        and parameters['round_trip_cost']==contract['round_trip_cost']",1),
        ('one ES contract, multiplier and costs','whole-position quantity and costs',1),
        ('metadata_contract(bars_path,metadata_path,series_manifest=series_manifest)',
         'metadata_contract(bars_path,metadata_path,series_manifest=series_manifest,session_calendar=session_calendar)',1),
        ('    # Full original bar parent validates signal/fill/occupancy before development filtering.',
         "    from gnet_broker.ts_processing import metadata_spec\n    require(primary['point_value']==metadata_spec(metadata)['multiplier'],'ts_primary_contract','Native point value differs from reviewed instrument specification')\n    # Full original bar parent validates signal/fill/occupancy before development filtering.",1),
        ("load_ts_bars(bars_path,metadata,contract['development_end'])","load_ts_bars(bars_path,metadata,contract['development_end'],session_calendar=session_calendar)",1),
        ('feature_observations(bars,directions,duration_seconds=ts_duration(metadata))',
         'feature_observations(bars,directions,duration_seconds=ts_duration(metadata),processing_context=metadata.get("processing_context"))',1),
        ("'entry_price':trade['entry_price'],'exit_price':trade['exit_price'],'side':trade['side'],",
         "'entry_price':trade['entry_price'],'exit_price':trade['exit_price'],'side':trade['side'],'quantity':trade['quantity'],",1),
    ])
    patch('gnet_broker/feature_labels.py',[
        ('def feature_observations(bars, directional, *, duration_seconds=30):','def feature_observations(bars, directional, *, duration_seconds=30, processing_context=None):',1),
        ('ZoneInfo(FEATURE_CONTRACT["timezone"])','ZoneInfo(processing_context["timezone"] if processing_context else FEATURE_CONTRACT["timezone"])',1),
        ('        validate_bar(bar)', '''        if processing_context:
            require(row.get('calendar_sha256')==processing_context['calendar_sha256'],'feature_session','Feature bar calendar identity differs')
            if any(getattr(bar,n)<=0 for n in ('open','high','low','close')):
                output[row['bar_id']]={'features':None,'reason':'nonpositive_price_features','bar':row}
                engine=FeatureEngine()
                continue
        validate_bar(bar)''',1),
        ('            values = engine.update(bar)','            values = engine.update(bar,session_id=row["session"]) if processing_context else engine.update(bar)',1),
        ('        output[row["bar_id"]] = {"features": features, "reason": reason, "bar": row}', '''        if features is not None and processing_context:
            elapsed=(row['end_ns']-row['session_open_ns'])/60_000_000_000
            remaining=(row['session_close_ns']-row['end_ns'])/60_000_000_000
            require(elapsed>=0 and remaining>=0,'feature_session','Bar availability falls outside dated session')
            features['minutes_since_open']=float(elapsed)
            features['is_first_last_30min']=int(elapsed<=30 or remaining<=30)
            features['day_of_week']=datetime.fromisoformat(row['session']).weekday()
            features['amihud_illiquidity']/=processing_context['instrument_specification']['multiplier']
        output[row["bar_id"]] = {"features": features, "reason": reason, "bar": row}''',1),
    ])
    print('Native grids, costs, quantities and dated feature clocks patched.')


if __name__=='__main__':main()
