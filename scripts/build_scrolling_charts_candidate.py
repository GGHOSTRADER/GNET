"""Build a fresh chart continuation from the installed V40 package, retaining its other features."""
from pathlib import Path
import hashlib
import json
import shutil
import ast

BASE = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\g_med\.codex\worktrees\guarded-research\GNET')
OLD = BASE/'.artifacts/GNET-Command-Center-v40-SealedCalendarRepair-r1'
NEW = BASE/'.artifacts/GNET-Command-Center-v41-ScrollingCharts-r1'
BROKER = 'guarded-v41-scrolling-charts'
CLIENT = 'gnet-client-v56-scrolling-charts-r1'
assert not NEW.exists(), 'Candidate already exists; do not overwrite a reviewed package'
shutil.copytree(OLD, NEW, ignore=shutil.ignore_patterns('deployment-receipt.json', '.artifacts', '__pycache__'))
(NEW/'guarded-v40-sealed-calendar-repair').rename(NEW/BROKER)
(NEW/'gnet-client-v55-sealed-calendar-repair-r1').rename(NEW/CLIENT)
def patch(path, old, new):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, (str(path), old[:80], text.count(old))
    prior = ast.parse(text) if path.suffix == '.py' else None
    changed = text.replace(old,new)
    if prior:
        defs=lambda tree: [n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
        assert defs(prior)==defs(ast.parse(changed))
    path.write_text(changed,encoding='utf-8')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
for root in (NEW/BROKER,NEW/CLIENT):
    shutil.copyfile(BASE/'scripts/scrolling_bar_viewer.js',root/'gnet_broker/scrolling_bar_viewer.js')
    patch(root/'gnet_jobs/contracts.py', "'page_size':{**POSITIVE,'maximum':20},'max_points':{**POSITIVE,'minimum':20,'maximum':500},", "'page_size':{**POSITIVE,'maximum':20},'max_points':{**POSITIVE,'minimum':20,'maximum':500},\n    'chart_offset':{**NONNEGATIVE,'maximum':1000000},")
    patch(root/'gnet_jobs/client_deploy.py', "'gnet_broker/final_workbench.js',", "'gnet_broker/final_workbench.js','gnet_broker/scrolling_bar_viewer.js',")
    server=root/'gnet_jobs/view_server.py'
    patch(server,'"/research/assets/native-interactive-chart.js",','"/research/assets/scrolling-bar-viewer.js", "/research/assets/native-interactive-chart.js",')
    patch(server,'                        "/research/assets/native-interactive-chart.js":', '                        "/research/assets/scrolling-bar-viewer.js": ("scrolling_bar_viewer.js","text/javascript; charset=utf-8"),\n                        "/research/assets/native-interactive-chart.js":')
    patch(server,"                if parts[2]=='native_trades.html':\n                    content=content.replace(b'</body>',b'<script src=\"/research/assets/lightweight-charts.js\"></script><script src=\"/research/assets/interactive-price-chart.js\"></script><script src=\"/research/assets/native-interactive-chart.js\"></script></body>',1)", "                if parts[2] in ('native_trades.html','viewer.html','dataset_chart.html'):\n                    content=content.replace(b'</body>',b'<script src=\"/research/assets/lightweight-charts.js\"></script><script src=\"/research/assets/scrolling-bar-viewer.js\"></script></body>',1)")
    patch(root/'gnet_broker/dataset_chart_page.html','<option>100</option><option>200</option><option>500</option>','<option>100</option><option>200</option><option selected>500</option>')
for name in ('ts_primary_view.py','ts_primary_view.html'):
    shutil.copyfile(SOURCE/'gnet_broker'/name,NEW/BROKER/'gnet_broker'/name)
guide='''# Scrollable price charts\n\nDataset previews, imported TradeStation primary trades and internal backtest trade reports use the same bundled local chart. Drag to pan, use the mouse wheel or pinch to zoom, or zoom in and move the scrollbar. Show loaded window restores the full window.\n\nImported primary viewers load up to 500 consecutive source bars, independent of the 20-row positions table. Earlier bars / Later bars load another protected window. Browse bars returns to the first bar window for the current filtered page. View on a trade starts a window at that trade. Markers represent positions from the current filtered page that overlap loaded bars. Dataset previews default to 500 observations; use Previous / Next observations for more.\n\nThe original internal report retains its detailed fills, statistics and filters. The chart uses observation order so equal timestamps stay distinct. Source clocks and exact OHLC values remain available on crosshair hover. Source approvals and training are separate steps.\n\nExisting saved reports get the shared presentation after the client update. A fresh imported trade-view job is required to fetch the wider 500-bar window. Old saved reports contain only their originally published bars.\n'''
for root in (NEW/BROKER,NEW/CLIENT):
    (root/'documentation/guides').mkdir(parents=True,exist_ok=True)
    (root/'documentation/guides/GNET_SCROLLABLE_CHARTS.md').write_text(guide,encoding='utf-8')
    mf=root/('release.json' if root.name==BROKER else 'client-release.json')
    manifest=json.loads(mf.read_text())
    manifest['release_id' if root.name==BROKER else 'client_release_id']=root.name
    manifest['files']['gnet_broker/scrolling_bar_viewer.js']=''
    manifest['files']['documentation/guides/GNET_SCROLLABLE_CHARTS.md']=''
    manifest['files']={name:sha(root/name) for name in manifest['files']}
    if root.name==BROKER:
        # Use the package's existing code identity algorithm, below after paths are ready.
        import sys
        sys.path.insert(0,str(root))
        from gnet_broker.release import code_identity
        manifest['code_hash']=code_identity(root)
    write(mf,manifest)
broker_hash=sha(NEW/BROKER/'release.json');client_hash=sha(NEW/CLIENT/'client-release.json')
installer=NEW/'Install-ReviewedCommandCenterClient.ps1'
text=installer.read_text();assert text.count('0d30e69d576f32c5d289857f707cf063871c87c62ae8590d6022d9a52627d674')==1
installer.write_text(text.replace('gnet-client-v55-sealed-calendar-repair-r1',CLIENT).replace('guarded-v40-sealed-calendar-repair',BROKER).replace('0d30e69d576f32c5d289857f707cf063871c87c62ae8590d6022d9a52627d674',client_hash),encoding='utf-8')
deploy=NEW/'Deploy-ReviewedCommandCenter.ps1'
text=deploy.read_text();assert text.count('f1ccd797bda213a60ac7c570c27c681234d451f33984bd075acbe082fc89a88f')==1
text=text.replace('guarded-v40-sealed-calendar-repair',BROKER).replace('f1ccd797bda213a60ac7c570c27c681234d451f33984bd075acbe082fc89a88f',broker_hash)
text=text.replace("@('d0824ae", "@('f1ccd797bda213a60ac7c570c27c681234d451f33984bd075acbe082fc89a88f','d0824ae")
text=text.replace("@('guarded-v39-generic-primary')", "@('guarded-v39-generic-primary','guarded-v40-sealed-calendar-repair')")
deploy.write_text(text,encoding='utf-8')
(NEW/'README.md').write_text(guide+'\nInstall protected broker with Deploy-ReviewedCommandCenter.ps1 -Apply in Administrator PowerShell. Then install matching client with Install-ReviewedCommandCenterClient.ps1 -Apply in ordinary PowerShell. Reopen Open-GNETResearch.ps1 and request a fresh trade viewer.\n',encoding='utf-8')
write(NEW/'delivery-status.json',{'release_id':BROKER,'client_release_id':CLIENT,'broker_manifest_sha256':broker_hash,'client_manifest_sha256':client_hash,'candidate_only':True,'installed':False,'real_data_used':False})
files={p.relative_to(NEW).as_posix():sha(p) for p in NEW.rglob('*') if p.is_file() and p.name!='delivery-manifest.json'}
write(NEW/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1','candidate_only':True,'files':files})
print(json.dumps({'candidate':str(NEW),'broker':BROKER,'client':CLIENT,'broker_manifest_sha256':broker_hash,'client_manifest_sha256':client_hash},indent=2))
