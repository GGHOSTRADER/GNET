"""Seal the reviewed native-processing continuation; no activation."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
PRIOR=BASE/'.artifacts/GNET-SymbolAttributes-v46-r1'
ROOT=BASE/'.artifacts/GNET-NativeMultiAsset-v47-r1'
BROKER=ROOT/'guarded-v47-native-multiasset'
CLIENT=ROOT/'gnet-client-v80-native-multiasset'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')


def replace(text,old,new,count=1):
    if text.count(old)!=count:raise RuntimeError('Seal anchor differs: '+old[:80])
    return text.replace(old,new)


def main():
    prior=PRIOR/'guarded-v46-symbol-attributes'
    inventory=lambda p:[(n.name,[m.name for m in n.body if isinstance(m,ast.FunctionDef)] if isinstance(n,ast.ClassDef) else []) for n in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    for name in ('feat_files/canonical_features.py','training_mlp/tradestation_source.py','training_mlp/native_primary_training.py',
        'training_mlp/research_dataset.py','gnet_broker/feature_labels.py','gnet_broker/source_features.py',
        'gnet_broker/ts_primary_source.py','gnet_broker/primary_labels.py','gnet_broker/comparison_reports.py',
        'gnet_broker/tradestation_training.py','gnet_broker/catalog.py','gnet_broker/dataset_capabilities.py',
        'gnet_broker/validation.py','gnet_broker/artifacts.py'):
        if inventory(BROKER/name)!=inventory(prior/name):raise RuntimeError('Existing definitions changed: '+name)
        if (CLIENT/name).exists():shutil.copyfile(BROKER/name,CLIENT/name)
    shutil.copyfile(BROKER/'gnet_broker/ts_processing.py',CLIENT/'gnet_broker/ts_processing.py')
    sys.path.insert(0,str(BROKER))
    from gnet_broker.release import code_identity,verify_release
    from gnet_broker import ts_processing,source_features,ts_primary_source,primary_labels,comparison_reports,tradestation_training
    from training_mlp import native_primary_training,tradestation_source,research_dataset
    path=BROKER/'release.json';value=json.loads(path.read_text())
    value['release_id']=BROKER.name
    value['files']={name:sha(BROKER/name) for name in set(value['files'])|{'gnet_broker/ts_processing.py'}}
    value['code_hash']=code_identity(BROKER);write(path,value)
    verify_release(BROKER,sha(path),check_dependencies=False)
    path=CLIENT/'client-release.json';value=json.loads(path.read_text());value['client_release_id']=CLIENT.name
    value['files']={name:sha(CLIENT/name) for name in set(value['files'])|{'gnet_broker/ts_processing.py'}};write(path,value)
    from gnet_jobs.client_deploy import verify_package
    verify_package(CLIENT,sha(path))
    if not (ROOT/'automation').exists():shutil.copytree(PRIOR/'automation',ROOT/'automation',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(PRIOR/'Check-GNETMVPIdle.py',ROOT/'Check-GNETMVPIdle.py')
    deploy=(PRIOR/'Deploy-ReviewedCommandCenter.ps1').read_text()
    deploy=replace(deploy,"$gnetRelease='guarded-v46-symbol-attributes'","$gnetRelease='"+BROKER.name+"'")
    deploy=replace(deploy,"$gnetHash='"+sha(prior/'release.json')+"'","$gnetHash='"+sha(BROKER/'release.json')+"'")
    deploy=replace(deploy,"-AllowedPriorRelease @(","-AllowedPriorRelease @('guarded-v46-symbol-attributes',")
    (ROOT/'Deploy-ReviewedCommandCenter.ps1').write_text(deploy,encoding='utf-8')
    installer=(PRIOR/'Install-ReviewedCommandCenterClient.ps1').read_text()
    installer=replace(installer,'gnet-client-v79-symbol-attributes',CLIENT.name,3)
    installer=replace(installer,'guarded-v46-symbol-attributes',BROKER.name,2)
    installer=replace(installer,sha(PRIOR/'gnet-client-v79-symbol-attributes/client-release.json'),sha(CLIENT/'client-release.json'))
    (ROOT/'Install-ReviewedCommandCenterClient.ps1').write_text(installer,encoding='utf-8')
    status={'broker_release_id':BROKER.name,'broker_manifest_sha256':sha(BROKER/'release.json'),
        'client_release_id':CLIENT.name,'client_manifest_sha256':sha(CLIENT/'client-release.json'),
        'installed':False,'real_data_read':False,'scope':'recorded native primary positions with reviewed outright instrument and dated calendar'}
    write(ROOT/'delivery-status.json',status)
    write(ROOT/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1',
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery-manifest.json'}})
    print(json.dumps(status))


if __name__=='__main__':main()
