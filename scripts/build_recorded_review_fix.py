"""Restore recorded-ledger evidence support in a fresh protected candidate."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
prior = base / '.artifacts/GNET-Command-Center-v41-ScrollingCharts-r1'
root = base / '.artifacts/GNET-Command-Center-v42-RecordedReviewFix-r3'
broker = 'guarded-v42-recorded-review-fix'
client = 'gnet-client-v62-recorded-review-fix-r2'
assert not root.exists()
shutil.copytree(prior, root, ignore=shutil.ignore_patterns('__pycache__', '.artifacts', 'deployment-receipt.json', 'delivery-manifest.json'))
(root/'guarded-v41-scrolling-charts').rename(root/broker)
# Retain the latest display and approval feedback client.
shutil.rmtree(root/'gnet-client-v56-scrolling-charts-r1')
shutil.copytree(base/'.artifacts/GNET-ReviewFeedback-Client-v61-r1/gnet-client-v61-review-feedback-r1',root/client,ignore=shutil.ignore_patterns('__pycache__'))
path = root/broker/'training_mlp/native_primary_training.py'
text = path.read_text(encoding='utf-8')
before = ast.parse(text)
old = "NATIVE_SOURCE['properties'].update(primary_contract=PRIMARY,fill_properties_reviewed={'const':True},platform_snapshot_reviewed={'const':True})"
assert text.count(old)==1
text = text.replace(old,"NATIVE_SOURCE['properties'].update(primary_contract=PRIMARY,fill_properties_reviewed=BOOL,platform_snapshot_reviewed=BOOL,\n    fill_review_basis={'const':'validated_recorded_ledger'})")
old = '    validate(contract,NATIVE_SOURCE)\n'
assert text.count(old)==1
text = text.replace(old,old+"    require((contract['fill_properties_reviewed'] and contract['platform_snapshot_reviewed'])\n        or contract.get('fill_review_basis')=='validated_recorded_ledger',\n        'ts_primary_evidence','Reviewed platform evidence or explicit validated recorded-ledger interpretation required')\n")
old = "'source_tape_verified':False,'complete_sessions_verified':False}"
assert text.count(old)==1
text = text.replace(old,"'source_tape_verified':False,'complete_sessions_verified':False,\n        'fill_review_basis':contract.get('fill_review_basis','reviewed_platform_settings'),\n        'platform_fill_settings_verified':contract['fill_properties_reviewed'],\n        'platform_snapshot_reviewed':contract['platform_snapshot_reviewed']}")
names = lambda tree: [n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
assert names(before)==names(ast.parse(text))
path.write_text(text,encoding='utf-8')
sys.path.insert(0,str(root/broker))
from gnet_broker.release import code_identity, verify_release
from training_mlp.native_primary_training import NATIVE_SOURCE, build_native_observations
from gnet_jobs.contracts import validate, ContractError
# Schema recognizes only the explicit recorded-ledger basis; no platform flags invented.
validate(False,NATIVE_SOURCE['properties']['fill_properties_reviewed'])
validate('validated_recorded_ledger',NATIVE_SOURCE['properties']['fill_review_basis'])
try:
    validate('anything_else',NATIVE_SOURCE['properties']['fill_review_basis'])
except ContractError:
    pass
else:
    raise AssertionError('Unknown evidence basis accepted')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
for name,manifest_name,key in [(broker,'release.json','release_id'),(client,'client-release.json','client_release_id')]:
    p=root/name/manifest_name;m=json.loads(p.read_text(encoding='utf-8'));m[key]=name
    m['files']={f:sha(root/name/f) for f in m['files']}
    if name==broker:m['code_hash']=code_identity(root/name)
    write(p,m)
bh=sha(root/broker/'release.json');ch=sha(root/client/'client-release.json')
old_bh=sha(prior/'guarded-v41-scrolling-charts/release.json')
deploy=(prior/'Deploy-ReviewedCommandCenter.ps1').read_text(encoding='utf-8')
assert deploy.count("$gnetHash='"+old_bh+"'")==1
deploy=deploy.replace("$gnetHash='"+old_bh+"'","$gnetHash='"+bh+"'")
deploy=deploy.replace("$gnetRelease='guarded-v41-scrolling-charts'","$gnetRelease='"+broker+"'")
anchor = "$gnetConfig.release_manifest_sha256 -notin @("
assert deploy.count(anchor)==1
deploy=deploy.replace(anchor,anchor+"'"+old_bh+"',")
deploy=deploy.replace("@('guarded-v39-generic-primary','guarded-v40-sealed-calendar-repair')","@('guarded-v39-generic-primary','guarded-v40-sealed-calendar-repair','guarded-v41-scrolling-charts')")
(root/'Deploy-ReviewedCommandCenter.ps1').write_text(deploy,encoding='utf-8')
installer=(base/'.artifacts/GNET-ReviewFeedback-Client-v61-r1/Install-ReviewedCommandCenterClient.ps1').read_text(encoding='utf-8')
installer=installer.replace('gnet-client-v61-review-feedback-r1',client).replace('guarded-v41-scrolling-charts',broker).replace(sha(base/'.artifacts/GNET-ReviewFeedback-Client-v61-r1/gnet-client-v61-review-feedback-r1/client-release.json'),ch)
(root/'Install-ReviewedCommandCenterClient.ps1').write_text(installer,encoding='utf-8')
verify_release(root/broker,bh,check_dependencies=False)
from gnet_jobs.client_deploy import verify_package
verify_package(root/client,ch)
write(root/'delivery-status.json',{'release_id':broker,'client_release_id':client,'broker_manifest_sha256':bh,'client_manifest_sha256':ch,'candidate_only':True,'installed':False,'real_data_used':False,'schema_checks_passed':True})
write(root/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1','files':{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}})
print(json.dumps({'candidate':str(root),'verified':True,'broker_manifest_sha256':bh}))
