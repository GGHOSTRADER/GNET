"""Package bounded publication retry and feature-section ordering fixes."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
root = base / '.artifacts/GNET-Publication-Retry-Client-v68-r2'
client = 'gnet-client-v68-publication-retry-r2'
package = root / client
if root.exists():
    raise RuntimeError('Candidate exists; use a fresh revision')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
def replace(relative, old, new):
    path = package / relative
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one anchor in {relative}: {old[:60]}')
    path.write_text(text.replace(old, new), encoding='utf-8')
replace('gnet_broker/research_workspace.html', "if(!r.ok)throw Error(v.error||'Broker request failed');return v", "if(!r.ok){const error=Error(typeof v.error==='string'?v.error:v.error?.message||'Broker request failed');error.status=r.status;throw error;}return v")
replace('gnet_broker/research_workspace.html', "const id=submitted.job_id;if(submitted.trigger_status", "const id=submitted.job_id;let publicationWaits=0;if(submitted.trigger_status")
replace('gnet_broker/research_workspace.html', "const result=await json('/api/result?job_id='+encodeURIComponent(id));if(result.execution_status", "let result;try{result=await json('/api/result?job_id='+encodeURIComponent(id));}catch(error){if(s.state==='published'&&error.status===404&&error.message==='Published result unavailable'&&publicationWaits++<8){$('jobStatus').textContent='Waiting for published result · '+id;continue;}error.message+=' · '+id;throw error;}if(result.execution_status")
replace('gnet_broker/feature_workbench.js', 'featureHost.prepend(panel);', "const join=$('featureDatasetJoin');if(join)featureHost.insertBefore(panel,join);else featureHost.prepend(panel);")
replace('gnet_broker/feature_workbench.js', 'analysis.append(reviewState);panel.after(analysis);', 'analysis.append(reviewState);if(join)join.after(analysis);else panel.after(analysis);')
replace('gnet_broker/ts_primary_launch.html', "const receipts=await(await fetch('/api/transfer-status')).json();const delivery=receipts.entries.find(e=>e.export_id===exportId),source=delivery?.custody", "let delivery,offset=0;for(let page=0;page<250;page++){const response=await fetch('/api/transfer-status?offset='+offset+'&page_size=20');if(!response.ok)throw Error('Receipt metadata unavailable');const receipts=await response.json();delivery=receipts.entries.find(e=>e.export_id===exportId);if(delivery||receipts.next_offset===null||receipts.next_offset===undefined)break;if(!Number.isInteger(receipts.next_offset)||receipts.next_offset<=offset)throw Error('Receipt pagination did not advance');offset=receipts.next_offset;}const source=delivery?.custody")
replace('gnet_broker/ts_primary_launch.html', 'at most20 positions and200 chart observations', 'at most 20 positions and 500 chart observations')
replace('gnet_broker/ts_primary_launch.html', 'page_size:20,max_points:200', 'page_size:20,max_points:500')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':'))+'\n', encoding='utf-8')
manifest_hash = sha(manifest_path)
sys.path.insert(0, str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package, manifest_hash)
(root / 'candidate-status.json').write_text(json.dumps({'client_release_id':client,'client_manifest_sha256':manifest_hash,'broker_release_id':config['broker_release_id'],'verified':True,'installed':False,'real_data_used':False},indent=2),encoding='utf-8')
print(json.dumps({'package_root':str(package),'manifest_sha256':manifest_hash}))
