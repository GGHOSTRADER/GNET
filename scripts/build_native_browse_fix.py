"""Build an immutable broker candidate for full-source native chart browsing."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
prior = base / '.artifacts/GNET-Command-Center-v42-RecordedReviewFix-r3'
root = base / '.artifacts/GNET-Command-Center-v43-NativeBrowseFix-r1'
broker = 'guarded-v43-native-browse-fix'
client = 'gnet-client-v70-native-browse-fix-r1'
if root.exists():
    raise RuntimeError('Use a fresh candidate revision')
shutil.copytree(prior, root, ignore=shutil.ignore_patterns('__pycache__', '.artifacts', 'deployment-receipt.json', 'delivery-manifest.json'))
(root / 'guarded-v42-recorded-review-fix').rename(root / broker)
shutil.rmtree(root / 'gnet-client-v62-recorded-review-fix-r2')
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
shutil.copytree(config['package_root'], root / client, ignore=shutil.ignore_patterns('__pycache__'))
path = root / broker / 'gnet_broker/ts_primary_view.py'
text = path.read_text(encoding='utf-8')
before = ast.parse(text)
changes = [
    ('def native_chart(bars_path, selected, max_points, window_trades=None, chart_offset=0):\n    if selected is None:\n        return [], None',
     'def native_chart(bars_path, selected, max_points, window_trades=None, chart_offset=0, focused=True):\n    """Browse from source row one, or focus an explicitly selected trade."""\n    if selected is None and focused:\n        return [], None'),
    ("    window_trades = window_trades or [selected]\n    anchor = selected['signal_row']\n    start = max(1, min(t['signal_row'] for t in window_trades) - 5) + chart_offset",
     "    window_trades = window_trades or ([selected] if selected else [])\n    anchor = selected['signal_row'] if selected else None\n    start = (max(1, min(t['signal_row'] for t in window_trades) - 5) if focused else 1) + chart_offset"),
    ("    overlay = {**selected, 'chart_has_more': has_more,", "    overlay = {**(selected or {}), 'chart_has_more': has_more,"),
    ("available.get(selected['entry_row'], {})", "available.get((selected or {}).get('entry_row'), {})"),
    ("available.get(selected['exit_row'], {})", "available.get((selected or {}).get('exit_row'), {})"),
    ("chart_window, request.payload.get('chart_offset', 0))", "chart_window, request.payload.get('chart_offset', 0), focused=bool(request.payload.get('selected_trade_id')))"),
]
for old, new in changes:
    if text.count(old) != 1:
        raise RuntimeError('Unexpected patch anchor: ' + old[:80])
    text = text.replace(old, new)
names = lambda tree: [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
if names(before) != names(ast.parse(text)):
    raise RuntimeError('Top-level definitions changed')
path.write_text(text, encoding='utf-8')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
write = lambda p, v: p.write_text(json.dumps(v, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
sys.path.insert(0, str(root / broker))
from gnet_broker.release import code_identity, verify_release
from gnet_broker.ts_primary_view import native_chart
from gnet_jobs.client_deploy import verify_package
for release, filename, key in [(broker, 'release.json', 'release_id'), (client, 'client-release.json', 'client_release_id')]:
    p = root / release / filename
    manifest = json.loads(p.read_text())
    manifest[key] = release
    manifest['files'] = {f: sha(root / release / f) for f in manifest['files']}
    if release == broker:
        manifest['code_hash'] = code_identity(root / release)
    write(p, manifest)
bh, ch = sha(root / broker / 'release.json'), sha(root / client / 'client-release.json')
old_bh = sha(prior / 'guarded-v42-recorded-review-fix/release.json')
deploy = (prior / 'Deploy-ReviewedCommandCenter.ps1').read_text()
for old, new in [("$gnetRelease='guarded-v42-recorded-review-fix'", "$gnetRelease='" + broker + "'"),
                 ("$gnetHash='" + old_bh + "'", "$gnetHash='" + bh + "'"),
                 ("$gnetConfig.release_manifest_sha256 -notin @(", "$gnetConfig.release_manifest_sha256 -notin @('" + old_bh + "',"),
                 ("-AllowedPriorRelease @(", "-AllowedPriorRelease @('guarded-v42-recorded-review-fix',")]:
    if deploy.count(old) != 1:
        raise RuntimeError('Unexpected deploy anchor')
    deploy = deploy.replace(old, new)
(root / 'Deploy-ReviewedCommandCenter.ps1').write_text(deploy, encoding='utf-8')
installer = (prior / 'Install-ReviewedCommandCenterClient.ps1').read_text()
installer = installer.replace('gnet-client-v62-recorded-review-fix-r2', client).replace('guarded-v42-recorded-review-fix', broker).replace(sha(prior / 'gnet-client-v62-recorded-review-fix-r2/client-release.json'), ch)
(root / 'Install-ReviewedCommandCenterClient.ps1').write_text(installer, encoding='utf-8')
verify_release(root / broker, bh, check_dependencies=False)
verify_package(root / client, ch)
write(root / 'delivery-status.json', {'release_id': broker, 'client_release_id': client, 'broker_manifest_sha256': bh, 'client_manifest_sha256': ch, 'verified': True, 'installed': False, 'real_data_used': False})
write(root / 'delivery-manifest.json', {'schema_version': 'gnet-reviewed-delivery-1', 'files': {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file()}})
print(json.dumps({'candidate': str(root), 'broker_manifest_sha256': bh, 'client_manifest_sha256': ch}))
