"""Add source-content labels to stored and staged TradeStation deliveries."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
root = base / '.artifacts/GNET-Delivery-Categories-Client-v66-r1'
client = 'gnet-client-v66-delivery-categories-r1'
package = root / client
if root.exists():
    raise RuntimeError('Candidate exists; use a fresh revision')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
def replace(relative, old, new):
    path = package / relative
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one patch anchor in {relative}: {old[:60]}')
    path.write_text(text.replace(old, new), encoding='utf-8')

replace('gnet_broker/delivery_inventory.js', 'function gnetImportedDateLabel(value)', """function gnetDeliveryCategory(item){
  const source=item.custody||item.observed_chart;
  if(item.identity_status==='invalid_metadata')return {key:'pending',label:'Source type pending'};
  if(source?.primary_report||item.has_primary===true)return {key:'primary',label:'TS bars + primary trades'};
  if(['tick','ticks'].includes(source?.bar_kind)&&Number(source.bar_size)===1)return {key:'ticks',label:'Individual 1-tick data'};
  if(source?.bar_kind&&Number(source.bar_size)>0)return {key:'bars',label:'TS bars'};
  return {key:'pending',label:'Source type pending'};
}
function gnetImportedDateLabel(value)""")
replace('gnet_broker/delivery_inventory.js', '.delivery-type{', '.delivery-category{display:inline-block;padding:4px 10px;border:1px solid;border-radius:6px;font-size:12px;font-weight:700}.delivery-category[data-source-category=bars]{background:#203b5b;color:#9fc4ff;border-color:#7eb9ff}.delivery-category[data-source-category=ticks]{background:#203f34;color:#8fe1bd;border-color:#72dfbb}.delivery-category[data-source-category=primary]{background:#3b2e53;color:#dfc7ff;border-color:#c6afff}.delivery-category[data-source-category=pending]{background:#303947;color:#c7d0dd;border-color:#7b8b9f}.delivery-category-legend{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.delivery-type{')
replace('gnet_broker/delivery_inventory.js', 'function pair(parent,label,value)', """function categoryBadge(item){styles();const category=gnetDeliveryCategory(item),badge=el('span',category.label,'delivery-category');badge.dataset.sourceCategory=category.key;return badge;}
  function pair(parent,label,value)""")
replace('gnet_broker/delivery_inventory.js', "headSummary.append(el('strong',(deliveryIndex+1)+'. ','delivery-number'),type,", "headSummary.append(el('strong',(deliveryIndex+1)+'. ','delivery-number'),categoryBadge(receipts.find(r=>r.export_id===item.id)||{custody:{bar_kind:item.bar_kind,bar_size:item.bar_size},has_primary:item.hasPrimary}),type,")
replace('gnet_broker/delivery_inventory.js', "(statusFilter==='primary'&&m.hasPrimary)", "(statusFilter==='primary'&&m.hasPrimary)||(statusFilter==='ticks'&&gnetDeliveryCategory({custody:{bar_kind:m.bar_kind,bar_size:m.bar_size},has_primary:m.hasPrimary}).key==='ticks')||(statusFilter==='bars'&&gnetDeliveryCategory({custody:{bar_kind:m.bar_kind,bar_size:m.bar_size},has_primary:m.hasPrimary}).key==='bars')")
replace('gnet_broker/delivery_inventory.js', 'window.GNETDeliveries={refresh,render,', 'window.GNETDeliveries={categoryBadge,refresh,render,')
replace('gnet_broker/client_inbox.html', '<option value="primary">With primary trades</option>', '<option value="primary">TS bars + primary trades</option><option value="ticks">Individual 1-tick data</option><option value="bars">TS bars only</option>')
replace('gnet_broker/client_inbox.html', '<div id="custodyReceipts"></div>', '<div class="delivery-category-legend" aria-label="Delivery content legend"><span class="delivery-category" data-source-category="bars">TS bars</span><span class="delivery-category" data-source-category="ticks">Individual 1-tick data</span><span class="delivery-category" data-source-category="primary">TS bars + primary trades</span></div><div id="custodyReceipts"></div>')
replace('gnet_broker/client_inbox.html', 'row.append(number,type,name,badge,importLine,dateLine);', 'row.append(number,window.GNETDeliveries.categoryBadge(item),type,name,badge,importLine,dateLine);')
replace('gnet_jobs/export_identity.py', "'acceptance_verified': False, 'matching_request':", "'has_primary': bool(not invalid and producer and producer.get('strategy_file')),\n        'acceptance_verified': False, 'matching_request':")

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':'))+'\n', encoding='utf-8')
manifest_hash = sha(manifest_path)
sys.path.insert(0, str(package))
from gnet_jobs.client_deploy import verify_package
from gnet_jobs import export_identity
verify_package(package, manifest_hash)
(root / 'candidate-status.json').write_text(json.dumps({'client_release_id':client,'client_manifest_sha256':manifest_hash,'broker_release_id':config['broker_release_id'],'verified':True,'installed':False,'real_data_used':False},indent=2),encoding='utf-8')
print(json.dumps({'package_root':str(package),'manifest_sha256':manifest_hash}))
