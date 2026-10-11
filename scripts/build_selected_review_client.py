"""Keep review navigation source-specific and display selected public metadata."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
client = 'gnet-client-v77-selected-source-review-r2'
package = base / '.artifacts/GNET-SelectedReview-Client-v77-r2' / client
if package.exists():
    raise RuntimeError('Preserve existing candidate')
shutil.copytree(config['package_root'],package,ignore=shutil.ignore_patterns('__pycache__'))
def patch(name,changes):
    path=package/'gnet_broker'/name
    text=path.read_text(encoding='utf-8')
    for old,new in changes:
        if text.count(old)!=1:
            raise RuntimeError('Anchor differs: '+old[:80])
        text=text.replace(old,new)
    path.write_text(text,encoding='utf-8')
patch('data_preparation.html',[(
 '<a class="button-link source-review-button" id="openSourceReview" href="/reviews/">Review &amp; approve sources <span aria-hidden="true">→</span></a>', '')])
metadata='''function displaySourceMetadata(value){
 if(value.custody)displaySourceMetadata.receipt=value;const receipt=displaySourceMetadata.receipt||{};
 const source={...(receipt.custody||{}),...(value.source||{})},coverage={...source,...(value.coverage||{})};
 const meta=source.source_metadata||{},primary=source.primary_report||value.primary_review?.source_contract?.primary_contract;
 const fields=[['Export ID',$('exportId').value],['Symbol',source.symbol],['Bar interval',(source.interval_size||source.bar_size||'')+' '+(source.interval_kind||source.bar_kind||'')],['Records',coverage.rows],['First timestamp',coverage.first_timestamp],['Last timestamp',coverage.last_timestamp],['Source timezone',value.source_timezone||meta.source_timezone],['Transfer status',receipt.state],['Imported on',receipt.imported_at_utc],['Strategy',primary?.strategy_id],['Closed positions',primary?.closed_trades]];
 const table=document.createElement('table');for(const [name,value] of fields){if(value===undefined||value===null||value===' ')continue;const row=document.createElement('tr'),label=document.createElement('th'),cell=document.createElement('td');label.textContent=name;cell.textContent=String(value);row.append(label,cell);table.append(row)}
 $('selectedSourceMetadata').replaceChildren(table);
}
async function loadSourceMetadata(){
 displaySourceMetadata({});let offset=0;
 try{for(let page=0;page<250;page++){const value=await json('/api/transfer-status?offset='+offset+'&page_size=20');const receipt=(value.entries||[]).find(item=>item.export_id===$('exportId').value);if(receipt){displaySourceMetadata(receipt);if(typeof receipt.custody?.synthetic==='boolean')$('synthetic').checked=receipt.custody.synthetic;return}if(value.next_offset===null||value.next_offset===undefined)break;if(!Number.isInteger(value.next_offset)||value.next_offset<=offset)throw Error('Receipt pagination did not advance');offset=value.next_offset;}}
 catch{$('sourceMetadataStatus').textContent='Stored metadata could not be refreshed. The selected export identity is retained.';return}
 $('sourceMetadataStatus').textContent='Stored receipt not found in the bounded lookup; validation may provide source metadata.';
}
'''
patch('ts_review.html',[
 ('<p id="sourceSummary">Loading the selected source…</p>', '<p id="sourceSummary">Loading the selected source…</p><section aria-label="Selected source metadata"><h3>Selected source</h3><div id="selectedSourceMetadata"></div><p id="sourceMetadataStatus" role="status"></p></section>'),
 ('function showTemplate(value){',metadata+'function showTemplate(value){'),
 ("selectedSourceMetadata=value;setProcessDefaults(value);", "selectedSourceMetadata=value;displaySourceMetadata(value);setProcessDefaults(value);"),
 ("busy=true;validationProgress('Loading selected source and running automatic validation…');", "busy=true;await loadSourceMetadata();validationProgress('Loading selected source and running automatic validation…');"),
 ("job('ts_review_template',{export_id:$('exportId').value,automatic_checks:true})", "job('ts_review_template',{export_id:$('exportId').value,automatic_checks:true,synthetic:$('synthetic').checked})"),
])
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path=package/'client-release.json'
manifest=json.loads(manifest_path.read_text())
manifest['client_release_id']=client
manifest['files']={name:sha(package/name) for name in manifest['files']}
manifest_path.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
sys.path.insert(0,str(package))
from gnet_jobs.client_deploy import verify_package
verify_package(package,sha(manifest_path))
print(json.dumps({'package_root':str(package),'manifest_sha256':sha(manifest_path)}))
