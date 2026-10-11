"""Build the ordinary-client source-review navigation correction."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
client = 'gnet-client-v73-source-review-button-r1'
package = base / '.artifacts/GNET-ReviewButton-Client-v73-r1' / client
if package.exists():
    raise RuntimeError('Candidate already exists; preserve it')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
page = package / 'gnet_broker/data_preparation.html'
text = page.read_text(encoding='utf-8')
changes = [
    ('<body><p style="padding:12px"><a href="/reviews/">Source review and policy approval controls →</a></p>', '<body>'),
    ('<div class="eyebrow">Start here</div><h1>Data cleaning & sampling</h1><p>Inspect raw inputs, identify approved sources, then choose how to turn a source into bars.</p>',
     '<section class="source-preparation-heading" aria-label="Data preparation"><div><div class="eyebrow">Start here</div><h1>Data cleaning & sampling</h1><p>Inspect raw inputs, identify approved sources, then choose how to turn a source into bars.</p></div><a class="button-link source-review-button" id="openSourceReview" href="/reviews/">Review &amp; approve sources <span aria-hidden="true">→</span></a></section>'),
]
for old, new in changes:
    if text.count(old) != 1:
        raise RuntimeError('Source-review anchor differs')
    text = text.replace(old, new)
page.write_text(text, encoding='utf-8')
css = package / 'gnet_broker/workbench.css'
css.write_text(css.read_text(encoding='utf-8') + '\n.source-preparation-heading{display:flex;align-items:center;justify-content:space-between;gap:24px}.source-preparation-heading>div{min-width:0}.source-review-button{flex:none;display:inline-flex;align-items:center;justify-content:center;gap:12px;min-height:44px;background:var(--mint);border-color:var(--mint);color:#092c26;font-weight:700}.source-review-button:hover{background:#98ebce;color:#092c26}.source-review-button span{font-size:20px}@media(max-width:1060px){.source-preparation-heading{align-items:flex-start;flex-direction:column;gap:12px}}@media(max-width:650px){.source-review-button{width:100%}}\n', encoding='utf-8')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
sys.path.insert(0, str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package, sha(manifest_path))
print(json.dumps({'package_root': str(package), 'manifest_sha256': sha(manifest_path)}))
