"""Package compact delivery badges with their full explanations in the legend."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
root = base / '.artifacts/GNET-Compact-Delivery-Client-v67-r1'
client = 'gnet-client-v67-compact-delivery-r1'
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
for key,short,full in [('bars','Bar','TradeStation bars'),('ticks','1 T','Individual 1-tick data'),('primary','Bar + PT','TradeStation bars + primary trades')]:
    old_full={'bars':'TS bars','ticks':'Individual 1-tick data','primary':'TS bars + primary trades'}[key]
    replace('gnet_broker/delivery_inventory.js', "{key:'"+key+"',label:'"+old_full+"'}", "{key:'"+key+"',label:'"+short+"',description:'"+full+"'}")
    replace('gnet_broker/client_inbox.html', 'data-source-category="'+key+'">'+old_full+'</span>', 'data-source-category="'+key+'">'+short+' = '+full+'</span>')
replace('gnet_broker/delivery_inventory.js', 'badge.dataset.sourceCategory=category.key;return badge;', "badge.dataset.sourceCategory=category.key;badge.title=category.description||category.label;return badge;")

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
