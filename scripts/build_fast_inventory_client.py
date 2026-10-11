"""Build a metadata-only, bounded persistent inventory cache in the client."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
client = 'gnet-client-v75-fast-inventory-r1'
package = base / '.artifacts/GNET-FastInventory-Client-v75-r1' / client
if package.exists():
    raise RuntimeError('Preserve existing candidate')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))

def patch(name, changes):
    path = package / 'gnet_broker' / name
    text = path.read_text(encoding='utf-8')
    for old, new in changes:
        if text.count(old) != 1:
            raise RuntimeError('Anchor differs: ' + old[:100])
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')

cache = '''const GNETInventoryCache={
 key(payload){return 'gnet-inventory:'+config.release_id+':'+JSON.stringify(payload)},
 get(payload){try{const value=JSON.parse(localStorage.getItem(this.key(payload)));return value&&value.catalog?.metadata_only===true&&Array.isArray(value.catalog.datasets)?value:null}catch{return null}},
 put(payload,catalog){if(catalog?.metadata_only!==true)return;try{const keys=Object.keys(localStorage).filter(k=>k.startsWith('gnet-inventory:'));while(keys.length>=40)localStorage.removeItem(keys.shift());localStorage.setItem(this.key(payload),JSON.stringify({saved:Date.now(),catalog}))}catch{}},
 clear(){try{for(const key of Object.keys(localStorage))if(key.startsWith('gnet-inventory:'))localStorage.removeItem(key)}catch{}}
};
'''
path = package / 'gnet_broker/data_preparation.html'
text = path.read_text(encoding='utf-8')
old_load = next(line for line in text.splitlines() if line.startswith('async function load(append=false)'))
new_load = '''function renderCatalog(records,last,wanted,append){const seen=new Map((append?accumulatedCatalog:[]).map(item=>[item.id,item]));for(const item of records)seen.set(item.id,item);accumulatedCatalog=Array.from(seen.values());catalog={...last,datasets:accumulatedCatalog,offset,page_size:wanted,next_offset:last.has_more?offset+records.length:null};window.GNETWorkbench.catalog(catalog);window.GNETDeliveries.setCatalog(catalog);inventory('rawList',sources(),false);$('approvedList').replaceChildren();$('catalogCount').textContent=accumulatedCatalog.length+' loaded metadata records · '+sources().length+' raw sources · '+sources().filter(approved).length+' accepted';$('previous').disabled=offset===0;$('next').disabled=!catalog.has_more;populate();recipe();window.GNETLibrary.update()}
async function load(append=false,force=false){if(working)return;working=true;$('reload').disabled=true;let saved=null;const wanted=catalogSize==='all'?20:Number(catalogSize),payload={collection:'all',offset,page_size:Math.min(20,wanted),only_enabled:false,sort:'recent',...catalogQuery};try{
 if(!force)saved=GNETInventoryCache.get({...payload,page_size:wanted});
 if(saved){renderCatalog(saved.catalog.datasets,saved.catalog,wanted,append);status('Saved inventory summary · '+new Date(saved.saved).toLocaleTimeString()+'.');if(Date.now()-saved.saved<60000)return;status('Saved inventory summary shown · refreshing metadata…')}
 else status('Requesting bounded catalog metadata…');
 let records=[],cursor=offset,last;while(records.length<wanted){last=(await job('data_catalog',{...payload,offset:cursor,page_size:Math.min(20,wanted-records.length)})).metrics.catalog;records.push(...last.datasets);cursor+=last.datasets.length;if(!last.has_more||!last.datasets.length)break}
 GNETInventoryCache.put({...payload,page_size:wanted},{...last,datasets:records});renderCatalog(records,last,wanted,append);status('Inventories refreshed. Source contents remain private.')
 }catch(error){status((saved?'Saved summary retained; refresh failed: ':'')+error.message,true)}finally{working=false;$('reload').disabled=false;recipe()}}
window.addEventListener('gnet-source-management-changed',()=>{GNETInventoryCache.clear();load(false,true)});'''
patch('data_preparation.html', [
 (old_load, new_load),
 ('async function json(url,options)', cache+'async function json(url,options)'),
 ("$('reload').onclick=()=>{load();", "$('reload').onclick=()=>{GNETInventoryCache.clear();load(false,true);"),
])
# Render public receipt summaries first; availability remains a background broker check.
patch('delivery_inventory.js', [
 ("if(window.GNETSourceManagement)await window.GNETSourceManagement.availability(page);", ''),
 ("return value;\n    }catch", "if(page.length&&window.GNETSourceManagement)window.GNETSourceManagement.availability(page).then(()=>{if(lastReceipts===entries)render(target,entries,filter?.checked===true,options.includeCatalog?catalogProfiles:[],options)}).catch(()=>{if(status)status.textContent+=' · availability refresh unavailable; actions remain broker checked'});return value;\n    }catch"),
])
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
