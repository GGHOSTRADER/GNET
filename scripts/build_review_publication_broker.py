"""Prepare an immutable protected continuation; never activate it."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
base=Path(__file__).resolve().parents[1]
prior=base/'.artifacts/GNET-Command-Center-v43-NativeBrowseFix-r1'
root=base/'.artifacts/GNET-ReviewPublication-v44-r1'
broker='guarded-v44-review-publication-fix'
client='gnet-client-v77-selected-source-review-r2'
if root.exists():
    raise RuntimeError('Preserve existing candidate')
shutil.copytree(prior,root,ignore=shutil.ignore_patterns('guarded-v43-native-browse-fix','gnet-client-v70-native-browse-fix-r1','__pycache__','.artifacts','deployment-receipt.json','delivery-manifest.json'))
shutil.copytree(prior/'guarded-v43-native-browse-fix',root/broker,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(base/'.artifacts/GNET-SelectedReview-Client-v77-r2'/client,root/client,ignore=shutil.ignore_patterns('__pycache__'))
path=root/broker/'gnet_broker/ts_review_template.py'
text=path.read_text(encoding='utf-8')
old="('calendar_id','timezone','start_session','end_session','evidence')"
new="('calendar_id','timezone','start_session','end_session')"
if text.count(old)!=1:
    raise RuntimeError('Calendar choices anchor differs')
updated=text.replace(old,new)
names=lambda text:[node.name for node in ast.parse(text).body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
if names(text)!=names(updated):
    raise RuntimeError('Top-level definitions changed')
path.write_text(updated,encoding='utf-8')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
write=lambda path,value:path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
sys.path.insert(0,str(root/broker))
from gnet_broker.release import code_identity,verify_release
from gnet_broker.ts_review_template import ts_review_template
manifest_path=root/broker/'release.json'
manifest=json.loads(manifest_path.read_text())
manifest['release_id']=broker
manifest['files']={name:sha(root/broker/name) for name in manifest['files']}
manifest['code_hash']=code_identity(root/broker)
write(manifest_path,manifest)
broker_hash=sha(manifest_path)
prior_hash=sha(prior/'guarded-v43-native-browse-fix/release.json')
deploy=(root/'Deploy-ReviewedCommandCenter.ps1').read_text(encoding='utf-8')
for old,new in [("$gnetRelease='guarded-v43-native-browse-fix'","$gnetRelease='"+broker+"'"),
               ("$gnetHash='"+prior_hash+"'","$gnetHash='"+broker_hash+"'"),
               ("$gnetConfig.release_manifest_sha256 -notin @(","$gnetConfig.release_manifest_sha256 -notin @('"+prior_hash+"',"),
               ("-AllowedPriorRelease @(","-AllowedPriorRelease @('guarded-v43-native-browse-fix',")]:
    if deploy.count(old)!=1:raise RuntimeError('Deployment anchor differs')
    deploy=deploy.replace(old,new)
(root/'Deploy-ReviewedCommandCenter.ps1').write_text(deploy,encoding='utf-8')
installer=(root/'Install-ReviewedCommandCenterClient.ps1').read_text(encoding='utf-8')
installer=installer.replace('gnet-client-v70-native-browse-fix-r1',client).replace('guarded-v43-native-browse-fix',broker).replace(sha(prior/'gnet-client-v70-native-browse-fix-r1/client-release.json'),sha(root/client/'client-release.json'))
# This matching-client handoff must also pass the full browser gate before stopping.
anchor="if(Test-Path -LiteralPath $gnetConfigPath){"
if installer.count(anchor)!=1:raise RuntimeError('Client installer anchor differs')
gate="& 'C:/Users/g_med/python_new/GNET/scripts/Test-GNETCommandCenterBrowser.ps1' -PackageRoot (Join-Path $PSScriptRoot '"+client+"')\n"+anchor
installer=installer.replace(anchor,gate)
(root/'Install-ReviewedCommandCenterClient.ps1').write_text(installer,encoding='utf-8')
verify_release(root/broker,broker_hash,check_dependencies=False)
write(root/'delivery-status.json',{'release_id':broker,'broker_manifest_sha256':broker_hash,'client_release_id':client,'verified':True,'installed':False,'raw_market_data_read':False})
write(root/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1','files':{path.relative_to(root).as_posix():sha(path) for path in root.rglob('*') if path.is_file()}})
print(json.dumps({'candidate':str(root),'broker_manifest_sha256':broker_hash,'installed':False}))
