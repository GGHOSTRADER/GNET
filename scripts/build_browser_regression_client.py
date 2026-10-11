"""Build a fresh client candidate for defects exposed by browser regressions."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
prior = Path(config['package_root'])
root = base / '.artifacts/GNET-BrowserRegression-Client-v63-r2'
client = 'gnet-client-v63-browser-regressions-r2'
package = root / client
if root.exists():
    raise RuntimeError('Candidate already exists; use its immutable contents or a new revision')
shutil.copytree(prior, package, ignore=shutil.ignore_patterns('__pycache__'))

def replace(relative, old, new):
    path = package / relative
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'Expected exactly one patch anchor in {relative}')
    path.write_text(text.replace(old, new), encoding='utf-8')

# Read the live selector: its original element may have been replaced by stage setup.
replace('gnet_broker/feature_workbench.js',
        "const data=snapshot.artifacts.find(a=>a.id===$('trainingData').value),features=selectedNames();",
        "const data=snapshot.artifacts.find(a=>a.id===$('trainingData').value),features=selectedNames(),modelFamily=$('modelFamily').value;")
feature = package / 'gnet_broker/feature_workbench.js'
text = feature.read_text(encoding='utf-8')
old = "model_family:family.value"
if text.count(old) != 1:
    raise RuntimeError('Training model-family anchor changed')
text = text.replace(old, 'model_family:modelFamily')
for family in ['xgboost', 'logistic_regression', 'random_forest']:
    old = f"if(family.value==='{family}')payload."
    if text.count(old) != 1:
        raise RuntimeError('Training family-settings anchor changed')
    text = text.replace(old, f"if(modelFamily==='{family}')payload.")
feature.write_text(text, encoding='utf-8')
# Metadata loading must release both primary target and dataset-join buttons.
replace('gnet_broker/research_workspace.html',
        "finally{busy=false;$('refresh').disabled=false;syncPrimary();syncReplay()}",
        "finally{busy=false;$('refresh').disabled=false;syncPrimary();syncReplay();window.GNETPrimaryTargets?.update()}")

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
manifest_hash = sha(manifest_path)
sys.path.insert(0, str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package, manifest_hash)
(root / 'candidate-status.json').write_text(json.dumps({
    'client_release_id': client, 'client_manifest_sha256': manifest_hash,
    'broker_release_id': config['broker_release_id'], 'verified': True,
    'installed': False, 'real_data_used': False,
}, indent=2), encoding='utf-8')
print(json.dumps({'package_root': str(package), 'manifest_sha256': manifest_hash}))
