"""Build explicit source-type defaults without asserting human approval."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
base = Path(__file__).resolve().parents[1]
config = json.loads((base / '.artifacts/client-delivery-installed/client-config.json').read_text())
client = 'gnet-client-v74-review-process-defaults-r1'
package = base / '.artifacts/GNET-ReviewDefaults-Client-v74-r1' / client
if package.exists():
    raise RuntimeError('Preserve existing candidate')
shutil.copytree(config['package_root'], package, ignore=shutil.ignore_patterns('__pycache__'))
page = package / 'gnet_broker/ts_review.html'
text = page.read_text(encoding='utf-8')
changes = [
 ('Confirm exported chart settings match the intended setup', 'I checked that the exported symbol, bar interval and session match the chart I intended to export'),
 ('<h3>Requested processes</h3>', '<h3>Requested processes</h3><p id="processDefaultsHelp">Compatible processes will be selected from the detected source type. You can remove any you do not want to authorize.</p>'),
 ('Named real-data research explicitly authorized</label><p>I authorize this selected export for the checked research processes above, including bar features and ML training. This permission does not authorize live orders.</p>', 'I authorize research use of this export for the selected processes</label><p>Permission to use this source is separate from checking its chart settings. Only the checked processes are requested; this does not start training or authorize live orders.</p>'),
 ('selectedSourceMetadata=null;', 'selectedSourceMetadata=null,processDefaultsKey=null;'),
 ('function showTemplate(value){', '''function setProcessDefaults(value){
 const source=value.source||{},captured=value.policy?.review_basis==='captured_export_snapshot';
 const ticks=source.interval_kind==='ticks'&&source.interval_size===1;
 const bars=['seconds','minutes','ticks','volume'].includes(source.interval_kind)&&Number(source.interval_size)>0&&!ticks;
 const allowed=captured?['bar_features','training']:ticks?['vp_features','bar_building']:bars?['primary_research','bar_features','training']:[];
 const key=$('exportId').value+':'+source.interval_kind+':'+source.interval_size+':'+captured;
 for(const option of document.querySelectorAll('[data-process]')){
  option.disabled=!allowed.includes(option.dataset.process);
  if(option.disabled)option.checked=false;
  else if(processDefaultsKey!==key)option.checked=true;
 }
 processDefaultsKey=key;
 $('processDefaultsHelp').textContent=captured?'Captured export evidence permits bar features and ML training only. These are selected for you; remove any you do not want.':ticks?'Individual 1-tick data detected: volume-profile features and bar building are selected. Other research uses follow after bars are created.':bars?'Bar data detected: primary research, bar features and ML training are selected. Remove any you do not want. Tick-only processes are unavailable.':'Source type is not recognized. No processes are selected; resolve the source metadata first.';
}
function showTemplate(value){'''),
 ("selectedSourceMetadata=value;$('continuousConfirmation')", "selectedSourceMetadata=value;setProcessDefaults(value);$('continuousConfirmation')"),
 ("for(const option of document.querySelectorAll('[data-process]')){option.checked=['bar_features','training'].includes(option.dataset.process);option.disabled=!['bar_features','training'].includes(option.dataset.process)}", 'setProcessDefaults(value);'),
 ("const calendarReference=JSON.parse($('calendar').value);", "if(!document.querySelector('[data-process]:checked'))throw Error('Select at least one research process to request.');const calendarReference=JSON.parse($('calendar').value);"),
]
for old, new in changes:
    if text.count(old) != 1:
        raise RuntimeError('Review anchor differs: ' + old[:70])
    text = text.replace(old, new)
page.write_text(text, encoding='utf-8')
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
