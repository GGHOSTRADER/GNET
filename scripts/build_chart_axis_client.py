"""Package the presentation-only axis update against the installed V41 broker."""
from pathlib import Path
import json
import hashlib
import shutil
import sys

BASE=Path(__file__).resolve().parents[1]
PRIOR=BASE/'.artifacts/GNET-Command-Center-v41-ScrollingCharts-r1'
ROOT=BASE/'.artifacts/GNET-ChartAxis-Client-v60-r2'
CLIENT='gnet-client-v60-timeframe-cash-axis-r2'
assert not (ROOT/'delivery-manifest.json').exists(), 'Preserve an existing reviewed client package'
if not ROOT.exists():
    ROOT.mkdir()
    shutil.copytree(PRIOR/'gnet-client-v56-scrolling-charts-r1',ROOT/CLIENT)
    shutil.copytree(PRIOR/'automation',ROOT/'automation')
shutil.copyfile(BASE/'scripts/scrolling_bar_viewer.js',ROOT/CLIENT/'gnet_broker/scrolling_bar_viewer.js')
page=ROOT/CLIENT/'gnet_broker/dataset_chart_page.html';text=page.read_text(encoding='utf-8')
assert text.count('height:740px')==1
page.write_text(text.replace('height:740px','height:950px'),encoding='utf-8')
guide=ROOT/CLIENT/'documentation/guides/GNET_SCROLLABLE_CHARTS.md'
guide.write_text(guide.read_text(encoding='utf-8')+'\nThe X-axis uses vertical time labels (HH:mm, or HH:mm:ss when seconds matter). A separate date badge identifies the first visible day and each day change; a dashed separator marks the first bar of a new day, using the source timestamp calendar date. In trade viewers, the axis includes outcome-colored entry dots, exit squares and duration lines: green winner, red loser, gray breakeven, amber unresolved. Dataset-only charts contain price observations without a trade population, so they show times and dates but no trade outcomes.\n',encoding='utf-8')
guide.write_text(guide.read_text(encoding='utf-8')+'\nAxis labels adapt to declared timeframe: intraday shows times with day badges; daily and weekly show MM-DD with month badges; monthly shows month names with year badges. On declared time bars shorter than one hour, yellow OPEN 09:30 NY and purple CLOSE 16:00 NY mark fixed U.S. cash-session reference times. Conversion uses the chart timezone and New York daylight saving rules. Weekends are excluded; holiday and early-close calendars are not applied. Markers are omitted when the source clock is unknown or missing observations prevent locating the boundary. Tick and volume bars do not declare a fixed duration and do not get these markers.\n',encoding='utf-8')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path=ROOT/CLIENT/'client-release.json';m=json.loads(manifest_path.read_text());m['client_release_id']=CLIENT
m['files']={name:sha(ROOT/CLIENT/name) for name in m['files']}
manifest_path.write_text(json.dumps(m,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
mh=sha(manifest_path)
installer=(PRIOR/'Install-ReviewedCommandCenterClient.ps1').read_text()
old_hash=sha(PRIOR/'gnet-client-v56-scrolling-charts-r1/client-release.json')
assert installer.count(old_hash)==1
(ROOT/'Install-ReviewedCommandCenterClient.ps1').write_text(installer.replace('gnet-client-v56-scrolling-charts-r1',CLIENT).replace(old_hash,mh),encoding='utf-8')
(ROOT/'README.md').write_text('# Vertical dates and trade outcome axis\n\nOrdinary-user client presentation update for the existing guarded-v41-scrolling-charts broker. No broker installation or password is required. Run Install-ReviewedCommandCenterClient.ps1 -Apply and reopen the normal launcher. Refresh existing chart pages.\n',encoding='utf-8')
sys.path.insert(0,str(ROOT/CLIENT))
from gnet_jobs.client_deploy import verify_package
verify_package(ROOT/CLIENT,mh)
receipt={'client_release_id':CLIENT,'broker_release_id':'guarded-v41-scrolling-charts','client_manifest_sha256':mh,'broker_changed':False,'package_verified':True,'installed':False}
(ROOT/'delivery-status.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
files={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file()}
(ROOT/'delivery-manifest.json').write_text(json.dumps({'schema_version':'gnet-reviewed-delivery-1','files':files},sort_keys=True),encoding='utf-8')
print(json.dumps(receipt,indent=2))
