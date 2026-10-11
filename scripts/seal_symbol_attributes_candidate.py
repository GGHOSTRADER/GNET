"""Verify precise candidate edits and seal immutable delivery manifests."""
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
PRIOR=BASE/'.artifacts/GNET-MultiAssetReview-v45-r1'
ROOT=BASE/'.artifacts/GNET-SymbolAttributes-v46-r1'
BROKER=ROOT/'guarded-v46-symbol-attributes'
CLIENT=ROOT/'gnet-client-v79-symbol-attributes'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')


def replace(text,old,new,count=1):
    if text.count(old)!=count:raise RuntimeError('Unexpected seal anchor: '+old)
    return text.replace(old,new)


def main():
    path=CLIENT/'gnet_broker/delivery_inventory.js'
    text=path.read_text(encoding='utf-8')
    old='item.receipt?.custody?.source_metadata?.symbol_attributes'
    if old in text:
        path.write_text(replace(text,old,'item.symbol_attributes'),encoding='utf-8')
    elif text.count('const attributes=item.symbol_attributes;')!=1:
        raise RuntimeError('Inventory capture anchor differs')
    for name in ('GNET_Bar_Export.els','GNET_Primary_Research_Export.els','GNET_Primary_Generic_Scaffold.els'):
        path=CLIENT/'EL_files'/name
        text=path.read_text(encoding='utf-8')
        old='If Not AutoRemoved And Not AutoPublishing And Not ExportFinished Then Begin'
        new='If SymbolDone And Not AutoRemoved And Not AutoPublishing And Not ExportFinished Then Begin'
        if old in text:text=replace(text,old,new)
        elif text.count(new)!=1:raise RuntimeError('Publication gate differs')
        before=(PRIOR/'gnet-client-v78-multi-asset-review/EL_files'/name).read_text(encoding='utf-8')
        methods=lambda s:re.findall(r'^method\s+\w+\s+(\w+)\(',s,re.M)
        expected=methods(before);current=methods(text)
        if [m for m in current if m in expected]!=expected or len(current)!=len(expected)+5:
            raise RuntimeError('Exporter method inventory differs')
        if text.count('SymbolProvider.Realtime=false;')!=1 or text.count('GnetSymbolAttributesText()')!=2:
            raise RuntimeError('Capture lifecycle contract differs')
        path.write_text(text,encoding='utf-8')
    for name in ('gnet_jobs/contracts.py','scripts/guarded_export_metadata.py','gnet_broker/symbol_attributes.py','gnet_broker/ts_export_contracts.py','gnet_broker/ts_export_bundle.py'):
        shutil.copyfile(BROKER/name,CLIENT/name)
    inventory=lambda p:[(n.name,[m.name for m in n.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef))] if isinstance(n,ast.ClassDef) else [])
        for n in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
    for name in ('scripts/guarded_export_metadata.py','gnet_broker/ts_export_contracts.py','gnet_broker/ts_export_bundle.py',
        'gnet_broker/ts_custody.py','gnet_broker/instrument_profiles.py','gnet_broker/ts_review_template.py',
        'gnet_broker/dataset_chart.py','gnet_broker/ts_primary_view.py','gnet_jobs/contracts.py','gnet_broker/catalog.py'):
        if inventory(BROKER/name)!=inventory(PRIOR/'guarded-v45-multi-asset-review'/name):
            raise RuntimeError('Existing Python definitions changed: '+name)
    sys.path.insert(0,str(BROKER))
    from gnet_broker.release import code_identity,verify_release
    from gnet_broker.ts_export_contracts import SCHEMAS
    from gnet_broker import symbol_attributes, ts_export_bundle, ts_custody, instrument_profiles, ts_review_template, dataset_chart, ts_primary_view
    from scripts.guarded_export_metadata import parse_metadata
    from gnet_jobs.contracts import DATASET_SCHEMA,INTAKE_REVIEW_POLICY
    for root in (BROKER,CLIENT):
        if (root/'schemas').exists():
            write(root/'schemas/dataset.v1.json',DATASET_SCHEMA)
            write(root/'schemas/ts-intake-policy.v1.json',INTAKE_REVIEW_POLICY)
    for name,schema in SCHEMAS.items():
        for root in (BROKER,CLIENT):
            path=root/'schemas'/(name+'.json')
            if path.exists():write(path,schema)
    path=BROKER/'release.json'
    value=json.loads(path.read_text())
    value['release_id']=BROKER.name
    names=set(value['files'])|{'gnet_broker/symbol_attributes.py'}
    value['files']={name:sha(BROKER/name) for name in names}
    value['code_hash']=code_identity(BROKER)
    write(path,value)
    broker_hash=sha(path)
    verify_release(BROKER,broker_hash,check_dependencies=False)
    path=CLIENT/'client-release.json'
    value=json.loads(path.read_text())
    value['client_release_id']=CLIENT.name
    names=set(value['files'])|{'gnet_broker/symbol_attributes.py'}
    value['files']={name:sha(CLIENT/name) for name in names}
    write(path,value)
    from gnet_jobs.client_deploy import verify_package
    verify_package(CLIENT,sha(path))
    client_hash=sha(path)
    if not (ROOT/'automation').exists():shutil.copytree(PRIOR/'automation',ROOT/'automation',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(PRIOR/'Check-GNETMVPIdle.py',ROOT/'Check-GNETMVPIdle.py')
    deploy=(PRIOR/'Deploy-ReviewedCommandCenter.ps1').read_text()
    prior_hash=sha(PRIOR/'guarded-v45-multi-asset-review/release.json')
    deployed_v44_hash=sha(BASE/'.artifacts/GNET-ReviewPublication-v44-r1/guarded-v44-review-publication-fix/release.json')
    deploy=replace(deploy,"$gnetRelease='guarded-v45-multi-asset-review'","$gnetRelease='"+BROKER.name+"'")
    deploy=replace(deploy,"$gnetHash='"+prior_hash+"'","$gnetHash='"+broker_hash+"'")
    # V45 is staged; the actual prior machine remains V44 (already allowlisted).
    if deployed_v44_hash not in deploy:raise RuntimeError('Actual V44 continuation missing')
    deploy=replace(deploy,"-AllowedPriorRelease @(","-AllowedPriorRelease @('guarded-v45-multi-asset-review',")
    (ROOT/'Deploy-ReviewedCommandCenter.ps1').write_text(deploy,encoding='utf-8')
    installer=(PRIOR/'Install-ReviewedCommandCenterClient.ps1').read_text()
    installer=replace(installer,'gnet-client-v78-multi-asset-review',CLIENT.name,3)
    installer=replace(installer,'guarded-v45-multi-asset-review',BROKER.name,2)
    installer=replace(installer,sha(PRIOR/'gnet-client-v78-multi-asset-review/client-release.json'),client_hash)
    (ROOT/'Install-ReviewedCommandCenterClient.ps1').write_text(installer,encoding='utf-8')
    write(ROOT/'delivery-status.json',{'broker_release_id':BROKER.name,'broker_manifest_sha256':broker_hash,
        'client_release_id':CLIENT.name,'client_manifest_sha256':client_hash,'installed':False,
        'tradestation_production_compile_verified':False,'real_market_rows_read':False})
    write(ROOT/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1',
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery-manifest.json'}})
    print(json.dumps({'broker_sha256':broker_hash,'client_sha256':client_hash,'installed':False}))


if __name__=='__main__':
    main()
