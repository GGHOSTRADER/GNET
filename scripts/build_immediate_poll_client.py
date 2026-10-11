"""Remove unconditional first polling waits; retain pending-job backoff."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
client = 'gnet-client-v76-immediate-metadata-poll-r1'
package = base / '.artifacts/GNET-ImmediatePoll-Client-v76-r1' / client
if package.exists():
    raise RuntimeError('Preserve existing candidate')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
for name, count, delay in [
    ('research_workspace.html',720,750), ('data_preparation.html',360,750),
    ('ts_review.html',240,750), ('dataset_chart_page.html',240,500),
    ('ts_primary_launch.html',120,500), ('delivery_inventory.js',120,500),
]:
    path = package / 'gnet_broker' / name
    text = path.read_text(encoding='utf-8')
    old = f'for(let i=0;i<{count};i++){{await new Promise(r=>setTimeout(r,{delay}));'
    new = f'for(let i=0;i<{count};i++){{if(i>0)await new Promise(r=>setTimeout(r,{delay}));'
    if text.count(old) != 1:
        raise RuntimeError('Polling anchor differs: '+name)
    path.write_text(text.replace(old,new), encoding='utf-8')
path = package / 'gnet_broker/research_workspace.html'
text = path.read_text(encoding='utf-8')
old = 'async function job(operation,payload){'
new = '''const featureMetadataCache=new Map();
async function job(operation,payload){
 if(operation!=='feature_inventory')return uncachedJob(operation,payload);
 const key=JSON.stringify([config.release_id,payload]),saved=featureMetadataCache.get(key);
 if(saved&&(saved.pending||Date.now()-saved.saved<60000))return saved.value;
 if(featureMetadataCache.size>=32)featureMetadataCache.delete(featureMetadataCache.keys().next().value);
 const entry={pending:true,saved:0,value:null};entry.value=uncachedJob(operation,payload).then(value=>{entry.pending=false;entry.saved=Date.now();return value}).catch(error=>{if(featureMetadataCache.get(key)===entry)featureMetadataCache.delete(key);throw error});featureMetadataCache.set(key,entry);return entry.value;
}
async function uncachedJob(operation,payload){'''
if text.count(old) != 1:
    raise RuntimeError('Job function anchor differs')
path.write_text(text.replace(old,new), encoding='utf-8')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
sys.path.insert(0,str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package,sha(manifest_path))
print(json.dumps({'package_root':str(package),'manifest_sha256':sha(manifest_path)}))
