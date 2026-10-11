"""Prevent duplicate GUI synthetic custody requests while one is pending."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
root = base / '.artifacts/GNET-Custody-Button-Client-v69-r1'
client = 'gnet-client-v69-custody-button-r1'
package = root / client
if root.exists():
    raise RuntimeError('Candidate exists; use a fresh revision')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
path = package / 'gnet_broker/client_inbox.html'
text = path.read_text(encoding='utf-8')
changes = [
    ('function deliveryControls(){', 'let custodyTesting=false,custodyEnabled=false;\nfunction deliveryControls(){'),
    ("async function custody(){return window.GNETDeliveries.refresh({target:'custodyReceipts',status:'storedStatus',filter:'showStoredTests',boundary:'boundary',controls:deliveryControls()})}", "async function custody(){const value=await window.GNETDeliveries.refresh({target:'custodyReceipts',status:'storedStatus',filter:'showStoredTests',boundary:'boundary',controls:deliveryControls()});custodyEnabled=value?.enabled===true;$('testCustody').disabled=custodyTesting||!custodyEnabled;return value;}"),
    ("$('testCustody').onclick=async()=>{try{", "$('testCustody').onclick=async()=>{if(custodyTesting||$('testCustody').disabled)return;custodyTesting=true;$('testCustody').disabled=true;try{"),
    ("await custody()}catch(error){$('transferMessage').textContent=error.message}};$('preparePrimarySource')", "await custody()}catch(error){$('transferMessage').textContent=error.message}finally{custodyTesting=false;$('testCustody').disabled=!custodyEnabled;}};$('preparePrimarySource')"),
]
for old,new in changes:
    if text.count(old)!=1:
        raise RuntimeError('Expected one custody button anchor: '+old[:60])
    text=text.replace(old,new)
path.write_text(text,encoding='utf-8')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path=package/'client-release.json'
manifest=json.loads(manifest_path.read_text())
manifest['client_release_id']=client
manifest['files']={name:sha(package/name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
manifest_hash=sha(manifest_path)
sys.path.insert(0,str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package,manifest_hash)
(root/'candidate-status.json').write_text(json.dumps({'client_release_id':client,'client_manifest_sha256':manifest_hash,'broker_release_id':config['broker_release_id'],'verified':True,'installed':False,'real_data_used':False},indent=2),encoding='utf-8')
print(json.dumps({'package_root':str(package),'manifest_sha256':manifest_hash}))
