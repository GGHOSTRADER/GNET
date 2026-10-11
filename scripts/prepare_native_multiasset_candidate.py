"""Prepare a new immutable candidate; never alter installed code."""
from pathlib import Path
import shutil

base=Path(__file__).resolve().parents[1]
prior=base/'.artifacts/GNET-SymbolAttributes-v46-r1'
root=base/'.artifacts/GNET-NativeMultiAsset-v47-r1'
if root.exists():raise RuntimeError('Preserve existing candidate')
root.mkdir()
for old,new in [('guarded-v46-symbol-attributes','guarded-v47-native-multiasset'),
    ('gnet-client-v79-symbol-attributes','gnet-client-v80-native-multiasset')]:
    shutil.copytree(prior/old,root/new,ignore=shutil.ignore_patterns('__pycache__'))
print(root)
