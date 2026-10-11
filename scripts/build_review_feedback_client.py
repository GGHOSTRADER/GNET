"""Build a client-only review submission feedback fix from the current client."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

base = Path(__file__).resolve().parents[1]
prior = base / '.artifacts/GNET-ChartAxis-Client-v60-r2'
old = 'gnet-client-v60-timeframe-cash-axis-r2'
new = 'gnet-client-v61-review-feedback-r1'
root = base / '.artifacts/GNET-ReviewFeedback-Client-v61-r1'
assert not root.exists(), 'Preserve reviewed candidates'
shutil.copytree(prior / old, root / new)
shutil.copytree(prior / 'automation', root / 'automation')
page = root / new / 'gnet_broker/ts_review.html'
text = page.read_text(encoding='utf-8')
def replace(before, after):
    global text
    assert text.count(before) == 1, before[:100]
    text = text.replace(before, after)

replace(' Named real-data research explicitly authorized</label>',
        ' Named real-data research explicitly authorized</label><p>I authorize this selected export for the checked research processes above, including bar features and ML training. This permission does not authorize live orders.</p>')
replace('<button id="draft">Validate and save review draft</button>',
        '<button id="draft">Validate and save review draft</button><p id="approvalStatus" role="status" aria-live="polite"></p>')
replace("async function job(operation,payload){const value=await json('/api/jobs'",
        "async function job(operation,payload){config=await json('/api/config');const value=await json('/api/jobs'")
replace("$('notice').textContent='Job '+value.job_id;",
        "$('notice').textContent='Job '+value.job_id;if(operation==='draft_ts_review')$('approvalStatus').textContent='Saving approval proposal · '+value.job_id;")
replace("catch(error){$('notice').textContent=error.message;if(!automaticReady)",
        "catch(error){$('notice').textContent=error.message;$('approvalStatus').textContent=error.message;$('approvalStatus').style.color='#ff9cac';if(!automaticReady)")
replace("$('draft').onclick=()=>action(async()=>{if(!automaticReady)",
        "$('draft').onclick=()=>action(async()=>{$('approvalStatus').style.color='#a4dfee';$('approvalStatus').textContent='Preparing approval proposal…';if(!$('synthetic').checked&&!$('realScope').checked)throw Error('Check the research authorization box above to permit the selected research processes.');if(!automaticReady)")
replace("show(result.metrics.review);$('notice').textContent='Draft saved. Awaiting local reviewer activation; no registration or training performed.'",
        "show(result.metrics.review);$('approvalStatus').textContent='Approval proposal saved. Next: local Administrator activation in step 2.';$('notice').textContent='Draft saved. Awaiting local reviewer activation; no registration or training performed.'")
page.write_text(text, encoding='utf-8')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path = root / new / 'client-release.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
manifest['client_release_id'] = new
manifest['files'] = {name: sha(root / new / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':'))+'\n', encoding='utf-8')
pin = sha(manifest_path)
installer = (prior / 'Install-ReviewedCommandCenterClient.ps1').read_text(encoding='utf-8')
old_pin = sha(prior / old / 'client-release.json')
assert installer.count(old_pin) == 1
(root / 'Install-ReviewedCommandCenterClient.ps1').write_text(installer.replace(old,new).replace(old_pin,pin),encoding='utf-8')
sys.path.insert(0,str(root / new))
sys.dont_write_bytecode = True
from gnet_jobs.client_deploy import verify_package
verify_package(root / new, pin)
(root / 'delivery-manifest.json').write_text(json.dumps({'files':{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}},sort_keys=True),encoding='utf-8')
print(json.dumps({'client_release_id':new,'manifest_sha256':pin,'broker_changed':False,'package_verified':True}))
