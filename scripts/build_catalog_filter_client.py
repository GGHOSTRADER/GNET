"""Build a client-only candidate compatible with the pinned V43 catalog schema."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
prior = Path(config['package_root'])
root = base / '.artifacts/GNET-GUIAcceptance-Client-v72-r2'
client = 'gnet-client-v72-gui-acceptance-fixes-r2'
package = root / client
if root.exists():
    raise RuntimeError('Preserve existing candidate; choose a new revision')
shutil.copytree(prior, package, ignore=shutil.ignore_patterns('__pycache__'))
path = package / 'gnet_broker/data_preparation.html'
text = path.read_text(encoding='utf-8')
old = "catalogQuery={sort:q.sort};for(const [name,key] of [['asset','asset'],['assets','assets'],['types','source_types'],['kind','bar_kind'],['start','date_start'],['end','date_end'],['search','search']])"
new = "catalogQuery={sort:({import_recent:'recent',import_oldest:'oldest',data_newest:'coverage_newest',data_oldest:'oldest'}[q.sort]||q.sort)};for(const [name,key] of [['asset','asset'],['kind','bar_kind'],['start','date_start'],['end','date_end'],['search','search']])"
if text.count(old) != 1:
    raise RuntimeError('Catalog request anchor differs')
path.write_text(text.replace(old, new), encoding='utf-8')
chart_path = package / 'gnet_broker/scrolling_bar_viewer.js'
chart_text = chart_path.read_text(encoding='utf-8')
changes = [
    ("shell.style.cssText = 'width:100%;min-width:0;color:#d9e6f6;background:#101a2a;padding:12px;box-sizing:border-box';",
     "shell.style.cssText = 'width:100%;min-width:0;color:#d9e6f6;background:#101a2a;padding:12px;box-sizing:border-box';\n  const scopedStyle=document.createElement('style');scopedStyle.textContent='#scrolling-bar-viewer svg{background:transparent;border:0;border-radius:0}';shell.append(scopedStyle);"),
    ("timeAxis.style.cssText='display:block;width:100%;height:125px;min-width:0'",
     "timeAxis.style.cssText='display:block;width:100%;height:125px;min-width:0;background:transparent;border:0;border-radius:0'"),
    ("overlay.style.cssText='position:absolute;inset:0;pointer-events:none;width:100%;height:100%;z-index:3'",
     "overlay.style.cssText='position:absolute;inset:0;pointer-events:none;width:100%;height:100%;z-index:3;background:transparent;border:0;border-radius:0'"),
]
for old, new in changes:
    if chart_text.count(old) != 1:
        raise RuntimeError('Chart styling anchor differs')
    chart_text = chart_text.replace(old, new)
chart_path.write_text(chart_text, encoding='utf-8')
# Asset/source-type/import-date choices remain filters over loaded public metadata.
# Their arrays and local sort names are not fields in the pinned broker contract.
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
sys.path.insert(0, str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package, sha(manifest_path))
(root / 'candidate-status.json').write_text(json.dumps({
    'client_release_id': client, 'client_manifest_sha256': sha(manifest_path),
    'broker_release_id': config['broker_release_id'], 'verified': True,
    'installed': False, 'real_data_used': False,
}, indent=2), encoding='utf-8')
print(json.dumps({'package_root': str(package), 'manifest_sha256': sha(manifest_path)}))
