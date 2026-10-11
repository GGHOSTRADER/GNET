"""Package the duplicate primary-navigation fix found by current-route tests."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
root = base / '.artifacts/GNET-Inventory-Navigation-Client-v65-r1'
client = 'gnet-client-v65-inventory-navigation-r1'
package = root / client
if root.exists():
    raise RuntimeError('Candidate exists; use a fresh revision')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
path = package / 'gnet_broker/research_library.js'
text = path.read_text(encoding='utf-8')
old = "if(!$('importedPrimaryNavigation')){const link=el('a'"
new = "if($('primaryStage')&&!$('importedPrimaryNavigation')){const link=el('a'"
if text.count(old) != 1:
    raise RuntimeError('Expected one primary navigation anchor')
path.write_text(text.replace(old, new), encoding='utf-8')
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
