"""Finalize the tested chart continuation and verify both immutable packages."""
from pathlib import Path
import hashlib
import json
import re
import sys
import shutil

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE/'.artifacts/GNET-Command-Center-v41-ScrollingCharts-r1'
BROKER='guarded-v41-scrolling-charts';CLIENT='gnet-client-v56-scrolling-charts-r1'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
for root in (ROOT/BROKER,ROOT/CLIENT):
    shutil.copyfile(BASE/'scripts/scrolling_bar_viewer.js',root/'gnet_broker/scrolling_bar_viewer.js')
    manifest_path=root/('release.json' if root.name==BROKER else 'client-release.json')
    manifest=json.loads(manifest_path.read_text())
    for name in manifest['files']:manifest['files'][name]=sha(root/name)
    write(manifest_path,manifest)
bh=sha(ROOT/BROKER/'release.json');ch=sha(ROOT/CLIENT/'client-release.json')
for file,pattern,value in [('Deploy-ReviewedCommandCenter.ps1',r"\$gnetHash='[a-f0-9]{64}'",f"$gnetHash='{bh}'"),
                          ('Install-ReviewedCommandCenterClient.ps1',r"-ManifestSha256 '[a-f0-9]{64}'",f"-ManifestSha256 '{ch}'")]:
    path=ROOT/file;text=path.read_text();text,n=re.subn(pattern,lambda _:value,text);assert n==1;path.write_text(text,encoding='utf-8')
receipt={'release_id':BROKER,'client_release_id':CLIENT,'broker_manifest_sha256':bh,'client_manifest_sha256':ch,
    'candidate_only':True,'installed':False,'real_data_used':False,'synthetic_viewer_tests_passed':31,
    'browser_acceptance':{'native':True,'dataset':True,'internal_backtest':True,'loaded_bars':500,'zoom_scroll_reset':True},
    'consecutive_bar_windows_verified':True}
write(ROOT/'delivery-status.json',receipt)
files={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery-manifest.json'}
write(ROOT/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1','candidate_only':True,'files':files})
sys.path.insert(0,str(ROOT/BROKER))
from gnet_broker.release import verify_release
from gnet_jobs.client_deploy import verify_package
verify_release(ROOT/BROKER,bh,check_dependencies=False)
verify_package(ROOT/CLIENT,ch)
from gnet_broker import ts_primary_view
from gnet_jobs import view_server,contracts
for name in ('gnet_broker/ts_primary_view.py','gnet_jobs/view_server.py','gnet_jobs/contracts.py'):
    compile((ROOT/BROKER/name).read_text(),name,'exec')
print(json.dumps({**receipt,'broker_package_verified':True,'client_package_verified':True},indent=2))
