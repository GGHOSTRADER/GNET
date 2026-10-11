"""Build the unified source inventory as an immutable ordinary-user candidate."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
root = base / '.artifacts/GNET-Unified-Inventory-Client-v64-r2'
client = 'gnet-client-v64-unified-inventory-r2'
package = root / client
if root.exists():
    raise RuntimeError('Candidate exists; choose a new revision')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))

def replace(relative, old, new):
    path = package / 'gnet_broker' / relative
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one anchor in {relative}: {old[:80]}')
    path.write_text(text.replace(old, new), encoding='utf-8')

replace('data_preparation.html', 'Received &amp; raw sources', 'Source inventory')
replace('data_preparation.html', 'What arrived? What is registered?', 'Bars, trades, validation and permissions')
replace('data_preparation.html', '<strong>Approved datasets</strong><small>What can each source be used for?</small>', '<strong>Approved sources</strong><small>Filter the same inventory by approval</small>')
replace('data_preparation.html', '<h2>1. Received sources &amp; registered datasets</h2>', '<h2>1. Source inventory</h2>')
replace('data_preparation.html', '<h3>TradeStation export intake</h3><p>Check pending exports, completion and transfer status before they appear in the received source inventory.</p><a class="button-link" id="openExportIntake" href="/intake/">Open export intake</a>', '<h3>Export transfer troubleshooting</h3><p>Use this only when an export is still writing, failed transfer, or has not reached this inventory.</p><a class="button-link" id="openExportIntake" href="/intake/">Inspect export transfer status</a>')
replace('data_preparation.html', '<h3>Source inventory · received and registered together</h3>', '<h3>All sources · one record per delivery</h3>')
replace('data_preparation.html', '<div class="trade-access" id="exportIntakeAccess"><h3>Export transfer troubleshooting</h3><p>Use this only when an export is still writing, failed transfer, or has not reached this inventory.</p><a class="button-link" id="openExportIntake" href="/intake/">Inspect export transfer status</a></div>', '<details class="trade-access" id="exportIntakeAccess"><summary>Export transfer troubleshooting</summary><p>Use this when an export is still writing, failed transfer, or has not reached this inventory.</p><a class="button-link" id="openExportIntake" href="/intake/">Inspect export transfer status</a></details>')
replace('data_preparation.html', 'Go to approved datasets →', 'Filter approved sources')
replace('data_preparation.html', 'Received TS exports and registered raw datasets share this inventory. Statuses,process permissions and primary-trade links are shown on each source. Synthetic test datasets are visible by default and labelled separately. Clear the checkbox below to focus on real exports. Data coverage describes the exported bar dates. Imported on records completed protected transfer, displayed in your browser timezone. Refresh inventories loads new arrivals; it does not approve them.', 'Expand a source for validation, permissions, candles, primary trades and research. Use status and content filters to find the next source to work on. Data dates show exported coverage; Imported on shows transfer completion. Refresh inventories loads new arrivals.')
replace('data_preparation.html', "function step(name){for(const key of ['raw','approved','sampling']){$(key+'Panel').hidden=key!==name;$(key+'Tab').setAttribute('aria-selected',String(key===name))}}", "function step(name){const panel=name==='approved'?'raw':name;for(const key of ['raw','approved','sampling']){$(key+'Panel').hidden=key!==panel;$(key+'Tab').setAttribute('aria-selected',String(key===name))}if(name!=='sampling')window.GNETLibrary?.setSourceStatus(name==='approved'?'approved':'all');}")
replace('data_preparation.html', "inventory('approvedList',sources().filter(approved),true);", "$('approvedList').replaceChildren();")
replace('research_library.js', "link.href='/imported-primaries/';", "link.href='/research/#primarySources';")
replace('module_boundaries.js', "const imported=$('importedPrimaryNavigation');if(imported){imported.textContent='Open imported primary strategy inventory';primary.prepend", "const imported=$('importedPrimaryNavigation');if(imported){imported.textContent='Find primary trades in source inventory';primary.prepend")
replace('module_boundaries.js', "const imported=$('importedPrimaryNavigation');if(imported&&!$('primaryStage')&&!$('sourcePrimaryInventoryAccess')){const access=fold('sourcePrimaryInventoryAccess','Related inventory · imported primary strategies',[imported]);imported.textContent='Open imported primary strategy inventory';$('receivedSources')?.append(access);}", "const imported=$('importedPrimaryNavigation');if(imported&&!$('primaryStage'))imported.remove();")
replace('research_library.js', "function renderSources(target, receipts, showTests, profiles) {", """function sourceStatus(item){
    if(item.profile?.accepted===true&&item.profile.validation_status==='pass')return 'approved';
    if(item.profile)return 'registered';
    if(/failed|quarantined/i.test(item.state||''))return 'failed';
    return 'pending';
  }
  function setSourceStatus(value){
    inventoryQuery.status=value;
    const select=document.querySelector('#sourceLibraryFilters select[name=status]');if(select)select.value=value;
    sourceOffset=0;rerenderSources();
  }
  function renderSources(target, receipts, showTests, profiles) {""")
replace('research_library.js', "if(!$('refreshSourceInventory'))", """if(!toolbar.querySelector('select[name=status]')){
      const label=el('label','Status / contents'),select=el('select');select.name='status';select.setAttribute('aria-label','Status / contents');
      for(const [value,text] of [['all','All sources'],['pending','Awaiting approval'],['registered','Registered · awaiting approval'],['approved','Approved for research'],['failed','Transfer / validation failed'],['primary','Primary trades available']])select.append(new Option(text,value));
      select.value=inventoryQuery.status||'all';select.onchange=()=>setSourceStatus(select.value);label.append(select);toolbar.append(label);
    }
    if(!$('refreshSourceInventory'))""")
replace('research_library.js', "const filtered = typeof GNETInventoryFilters==='undefined'?GNETLibraryCore.filter(records,query,display):GNETInventoryFilters.filter(records,query,display);", "const eligible=records.filter(item=>!query.status||query.status==='all'||(query.status==='primary'?item.hasPrimary:sourceStatus(item)===query.status));\n    const filtered = typeof GNETInventoryFilters==='undefined'?GNETLibraryCore.filter(eligible,query,display):GNETInventoryFilters.filter(eligible,query,display);")
replace('research_library.js', "renderSources, decorateArtifacts,", "renderSources, decorateArtifacts, setSourceStatus,")
replace('research_library.js', "window.addEventListener('hashchange', () => window.GNETLibrary.update());", """function inventoryRoute(){if(location.pathname==='/research/'&&['#primarySources','#approvedSources','#receivedSources'].includes(location.hash)){window.step?.('raw');setSourceStatus(location.hash==='#primarySources'?'primary':location.hash==='#approvedSources'?'approved':'all');}}
  document.addEventListener('DOMContentLoaded',inventoryRoute);
  window.addEventListener('hashchange', () => {window.GNETLibrary.update();inventoryRoute();});""")
replace('delivery_inventory.js', "const profile=profiles.find(p=>p.origin_export_id===receipt.export_id&&p.source_hash===receipt.custody?.source_sha256&&!!p.source_hash);if(profile)linked.add(profile.id);", "const matches=profiles.filter(p=>p.origin_export_id===receipt.export_id&&p.source_hash===receipt.custody?.source_sha256&&!!p.source_hash);const profile=matches.find(p=>p.accepted&&p.validation_status==='pass')||matches[0];for(const match of matches)linked.add(match.id);")

sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path = package / 'client-release.json'
manifest = json.loads(manifest_path.read_text())
manifest['client_release_id'] = client
manifest['files'] = {name: sha(package / name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(',', ':'))+'\n', encoding='utf-8')
manifest_hash = sha(manifest_path)
sys.path.insert(0, str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package, manifest_hash)
(root / 'candidate-status.json').write_text(json.dumps({'client_release_id':client,'client_manifest_sha256':manifest_hash,'broker_release_id':config['broker_release_id'],'verified':True,'installed':False,'real_data_used':False},indent=2),encoding='utf-8')
print(json.dumps({'package_root':str(package),'manifest_sha256':manifest_hash}))
