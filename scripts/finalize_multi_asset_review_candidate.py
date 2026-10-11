"""Finalize the staged review candidate using asserted block substitutions."""
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / '.artifacts/GNET-MultiAssetReview-v45-r1/guarded-v45-multi-asset-review'


def replace(path, old, new, count=1):
    text = path.read_text(encoding='utf-8')
    if text.count(old) != count:
        raise RuntimeError(f'Unexpected anchor count in {path.name}: {old!r}')
    before = [n.name for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    changed = text.replace(old, new)
    after = [n.name for n in ast.parse(changed).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    if before != after:
        raise RuntimeError('Top-level definition inventory changed')
    path.write_text(changed, encoding='utf-8')


def main():
    template = PACKAGE / 'gnet_broker/ts_review_template.py'
    replace(template, "asset='ES'", 'asset=asset', 3)
    replace(template, "'asset':'ES'", "'asset':asset", 3)
    replace(template, "if chart_scope_matches(candidate,src,asset=asset,synthetic=p['synthetic']) and",
        "if candidate['timezone']==profile['exchange_timezone'] and chart_scope_matches(candidate,src,asset=asset,synthetic=p['synthetic']) and")
    replace(template, "    zone=p['source_timezone']", "    if calendar['timezone'] != profile['exchange_timezone']:\n        raise ContractError('review_calendar_scope','Calendar timezone differs from the reviewed exchange timezone')\n    zone=p['source_timezone']")
    replace(template, "'instrument_specification':{'tick_size':.25,'multiplier':50,'volume_units':'contracts'}",
        "'instrument_specification':profile['specification'],\n        'instrument_profile':{'profile_sha256':digest(profile),'exchange':profile['exchange'],\n            'country':profile['country'],'exchange_timezone':profile['exchange_timezone']}")
    # Existing pricing/feature/final engines are not yet generic. Do not enable them merely because admission is generic.
    capabilities = PACKAGE / 'gnet_broker/dataset_capabilities.py'
    replace(capabilities, "    return {'schema_version':'gnet-dataset-profile-1','id':manifest['dataset_id']",
        "    if manifest['asset'] != 'ES':\n        caps = {p:{'enabled':False,'reason':'Source metadata can be reviewed; this research engine still requires an asset-specific calculation adapter'} for p in PROCESSES}\n    return {'schema_version':'gnet-dataset-profile-1','id':manifest['dataset_id']")
    catalog = PACKAGE / 'gnet_broker/catalog.py'
    replace(catalog, "        value = self.profile(identifier)\n        if value and value['origin_export_id']",
        "        if self.dataset(identifier).manifest['asset'] != 'ES':\n            raise ContractError('asset_adapter','This research operation requires an asset-specific calculation adapter')\n        value = self.profile(identifier)\n        if value and value['origin_export_id']")


def seal():
    prior=ROOT/'.artifacts/GNET-ReviewPublication-v44-r1/guarded-v44-review-publication-fix'
    for name in ('gnet_jobs/contracts.py','gnet_broker/ts_series.py','gnet_broker/ts_review_template.py',
            'gnet_broker/ts_bundle_intake.py','gnet_broker/catalog.py','gnet_broker/dataset_capabilities.py','gnet_broker/viewer.py'):
        inventory=lambda p:[(n.name,[m.name for m in n.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef))] if isinstance(n,ast.ClassDef) else [])
            for n in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
        if inventory(prior/name)!=inventory(PACKAGE/name):
            raise RuntimeError('Existing definition inventory changed: '+name)
    sys.path.insert(0, str(PACKAGE))
    from gnet_broker.release import code_identity, verify_release
    from gnet_broker import instrument_profiles, ts_review_template, ts_series, ts_bundle_intake, dataset_capabilities, catalog
    from gnet_jobs.contracts import DATASET_SCHEMA, INTAKE_REVIEW_POLICY
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    write = lambda p,v: p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    write(PACKAGE/'schemas/dataset.v1.json', DATASET_SCHEMA)
    write(PACKAGE/'schemas/ts-intake-policy.v1.json', INTAKE_REVIEW_POLICY)
    manifest_path = PACKAGE/'release.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['release_id'] = PACKAGE.name
    names = set(manifest['files']) | {'gnet_broker/instrument_profiles.py', 'scripts/guarded_instrument_admin.py'}
    manifest['files'] = {name: sha(PACKAGE/name) for name in names}
    manifest['code_hash'] = code_identity(PACKAGE)
    write(manifest_path,manifest)
    verify_release(PACKAGE,sha(manifest_path),check_dependencies=False)
    print(json.dumps({'candidate':str(PACKAGE),'manifest_sha256':sha(manifest_path),'installed':False}))


if __name__ == '__main__':
    if sys.argv[1:] != ['--seal-only']:
        main()
    seal()
