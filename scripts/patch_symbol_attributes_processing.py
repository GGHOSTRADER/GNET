"""Apply precise compatibility changes to the new staged package."""
import ast
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]/'.artifacts/GNET-SymbolAttributes-v46-r1'
BROKER=ROOT/'guarded-v46-symbol-attributes'
CLIENT=ROOT/'gnet-client-v79-symbol-attributes'


def patch(name,changes):
    path=BROKER/name
    text=path.read_text(encoding='utf-8')
    inventory=lambda s:[n.name for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    before=inventory(text)
    for old,new,count in changes:
        if text.count(old)!=count:
            raise RuntimeError('Unexpected anchor in '+name+': '+old)
        text=text.replace(old,new)
    if inventory(text)!=before:
        raise RuntimeError('Existing definition inventory changed')
    path.write_text(text,encoding='utf-8')


def main():
    patch('scripts/guarded_export_metadata.py',[
        ("'chart_min_move','chart_price_scale','chart_session_schedule_json'))", "'chart_min_move','chart_price_scale','chart_session_schedule_json','symbol_attributes_json'))",1),
        ("limit=16384 if line.startswith('chart_session_schedule_json=') else 512", "limit=16384 if line.startswith('chart_session_schedule_json=') else 2048 if line.startswith('symbol_attributes_json=') else 512",1),
        ("    timezone = values['declared_timezone']", "    attributes=None\n    if 'symbol_attributes_json' in values:\n        from gnet_broker.symbol_attributes import validate_capture,exchange_mapping\n        attributes=validate_capture(json.loads(values['symbol_attributes_json']),values['chart_symbol'])\n        if attributes['exchange_raw']!=values['chart_exchange']:\n            raise ValueError('Chart exchange differs from captured symbol attributes')\n        if attributes['status']!='loaded':warnings.append('Symbol metadata lookup unresolved: '+attributes['status'])\n    timezone = values['declared_timezone']\n    mapping=exchange_mapping(attributes) if attributes is not None else None\n    if mapping and mode=='1':\n        if timezone=='unknown':\n            timezone=mapping[1]\n        elif timezone!=mapping[1]:\n            raise ValueError('Declared chart exchange clock contradicts captured exchange identity')",1),
        ("    if grid is not None:result['price_grid']=grid", "    result['declared']['timezone']=timezone\n    if attributes is not None:result['symbol_attributes']=attributes\n    if grid is not None:result['price_grid']=grid",1),
    ])
    # Each versioned source schema has already been cloned, so add the optional fact block to all of them.
    path=BROKER/'gnet_broker/ts_export_contracts.py'
    text=path.read_text(encoding='utf-8')
    addition="\nfrom gnet_broker.symbol_attributes import CAPTURE\nfor _schema in (BUNDLE,NAMED_BUNDLE,GENERIC_BUNDLE,PRIMARY_BUNDLE):\n    _schema['properties']['source']['properties']['symbol_attributes']=CAPTURE\n"
    if addition in text:raise RuntimeError('Capture schema already present')
    path.write_text(text+addition,encoding='utf-8')
    patch('gnet_broker/ts_export_bundle.py',[("    generic=source['series_type']!='individual_contract'", "    if 'symbol_attributes' in metadata:source['symbol_attributes']=metadata['symbol_attributes']\n    generic=source['series_type']!='individual_contract'",1)])
    patch('gnet_broker/ts_custody.py',[("'source_metadata':{key:bundle['source'].get(key,'unknown') for key in ('series_type','source_timezone','volume_mode','price_basis','chart_timezone_mode')},", "'source_metadata':{**{key:bundle['source'].get(key,'unknown') for key in ('series_type','source_timezone','volume_mode','price_basis','chart_timezone_mode')},\n                        **({'symbol_attributes':bundle['source']['symbol_attributes']} if 'symbol_attributes' in bundle['source'] else {})},",1)])
    patch('gnet_broker/instrument_profiles.py',[("    else:\n        return None\n    if 'min_move'", "    else:\n        from gnet_broker.symbol_attributes import captured_profile\n        profile=captured_profile(source)\n        if profile is None:return None\n    if 'min_move'",1)])
    # Identical source metadata reaches review pending/success results.
    patch('gnet_broker/ts_review_template.py',[("'source':{'symbol':symbol,", "'source':{'symbol':symbol,**({'symbol_attributes':src['symbol_attributes']} if 'symbol_attributes' in src else {}),",3)])
    patch('gnet_broker/dataset_chart.py',[
        ("    view=select_window(rows,p)", "    from gnet_broker.symbol_attributes import session_reference\n    from gnet_broker.calendar import calendar_for\n    calendar=calendar_for(catalog,m) if p.get('dataset_id') else None\n    descriptor['session_reference']=session_reference({'symbol':descriptor['symbol'],**source} if 'source' in locals() else {'symbol':descriptor['symbol']},calendar)\n    if 'source' in locals() and source.get('symbol_attributes'):descriptor['symbol_attributes']=source['symbol_attributes']\n    view=select_window(rows,p)",1),
    ])
    patch('gnet_broker/ts_primary_view.py',[("    public = {'export_id': export_id, 'symbol': source['symbol'],", "    from gnet_broker.symbol_attributes import session_reference\n    public = {'session_reference':session_reference(source),\n        **({'symbol_attributes':source['symbol_attributes']} if 'symbol_attributes' in source else {}),\n        'export_id': export_id, 'symbol': source['symbol'],",1)])
    # Metadata parsing and sealing run in the ordinary-user finalizer as well as the protected broker.
    for name in ('gnet_jobs/contracts.py','scripts/guarded_export_metadata.py','gnet_broker/symbol_attributes.py',
            'gnet_broker/ts_export_contracts.py','gnet_broker/ts_export_bundle.py'):
        shutil.copyfile(BROKER/name,CLIENT/name)
    print('Metadata parser, schemas, sealed source, receipts and chart descriptors patched.')


if __name__=='__main__':
    main()
