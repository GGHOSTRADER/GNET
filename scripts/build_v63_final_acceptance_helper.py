"""Prepare a pinned, synthetic-only local review helper for a fresh final archive."""
import ast
import hashlib
from pathlib import Path
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
artifacts = base / '.artifacts'
source = artifacts / 'Prepare-GNETNativeFinalAcceptance.py'
destination = artifacts / 'Prepare-GNETV63FinalAcceptance.py'
if destination.exists():
    raise RuntimeError('Preserve the existing reviewed helper')
original = source.read_text(encoding='utf-8')
text = original
replacements = {
    "RELEASE = 'guarded-v25-final-evaluation'": "RELEASE = 'guarded-v42-recorded-review-fix'",
    "PIN = '9cb33dc5df7e213ffe14cef88227e38b1bb4fce239f7432616356ab0610b0d07'": "PIN = 'c5925fd6564563271648cf6fba0f53d677c21e088ab9656b2d7617a4d52fdd9e'",
    "EXPORT = 'acceptance-native-final-v25'": "EXPORT = 'acceptance-native-final-v63-r1'",
    "DATASET = 'ES__ESU26__synthetic_native_final_v25__rev01'": "DATASET = 'ES__ESU26__synthetic_native_final_v63__rev01'",
    "REVIEW = 'review-native-final-v25'": "REVIEW = 'review-native-final-v63'",
    "PRIMARY = 'primary-native-final-v25'": "PRIMARY = 'primary-native-final-v63'",
    "DAY = '2026-08-17'": "DAY = '2026-08-24'",
    "RECEIPT = BASE / 'v25-native-final-seed.json'": "RECEIPT = BASE / 'v63-native-final-seed.json'",
    "source_root = BASE / RELEASE if args.verify_fixture else RUNTIME": "source_root = BASE / 'GNET-Command-Center-v42-RecordedReviewFix-r3' / RELEASE if args.verify_fixture else RUNTIME",
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise RuntimeError('Exact final helper anchor changed: ' + old)
    text = text.replace(old, new)
for old, new in [('native-final-v25', 'native-final-v63'), ('20260817', '20260824'), ('installed v25', 'installed V42'), ('fixed v25', 'fixed V63')]:
    if old not in text:
        raise RuntimeError('Final helper token missing: ' + old)
    text = text.replace(old, new)
names = lambda value: [n.name for n in ast.parse(value).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
if names(original) != names(text):
    raise RuntimeError('Final helper definition inventory changed')
destination.write_text(text, encoding='utf-8')
print('Helper SHA256: ' + hashlib.sha256(destination.read_bytes()).hexdigest())
