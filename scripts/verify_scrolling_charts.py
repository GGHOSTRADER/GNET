"""Synthetic consecutive-window and actual Edge rendering acceptance for all three charts."""
from pathlib import Path
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta

BASE=Path(__file__).resolve().parents[1]
SOURCE=Path(r'C:\Users\g_med\.codex\worktrees\guarded-research\GNET')
OUT=BASE/'.test_artifacts/scrolling-browser'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(SOURCE))
from gnet_broker.ts_primary_view import native_chart,render_native_view
points=[{'row':i+1,'stamp':(datetime(2026,1,5)+timedelta(minutes=5*i)).isoformat(),
    'open':100+i*.01,'high':101+i*.01,'low':99+i*.01,'close':100.5+i*.01} for i in range(1100)]
path=OUT/'fabricated-bars.csv'
with path.open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['Timestamp','Open','High','Low','Close'])
    w.writerows([p['stamp'],p['open'],p['high'],p['low'],p['close']] for p in points)
t={'trade_id':'t-1','side':1,'status':'closed','signal_row':10,'entry_row':11,'exit_row':14,
   'entry_price':100.1,'exit_price':101,'net_pnl':45,'outcome':'winner',
   'entry_reported_time':points[10]['stamp'],'exit_reported_time':points[13]['stamp']}
first,overlay=native_chart(path,t,500,[t],0)
second,following=native_chart(path,t,500,[t],500)
assert len(first)==len(second)==500 and second[0]['row']==first[-1]['row']+1
assert overlay['chart_has_more'] and following['signal_price'] is None
assert first[0]['row']==5 and second[0]['row']==505
source={'symbol':'SYNTHETIC','export_id':'fabricated','bar_size':5,'bar_kind':'minutes',
    'strategy_id':'toy','synthetic':True,'source_timezone':'UTC','chart_clock_mode':2}
native={'source':source,'payload':{},'release_id':'synthetic','page':[t],'chart':first,'selected':overlay,
    'chart_has_more':True,'matching_count':1,'population_count':1,'offset':0,'page_size':20,'has_more':False}
documents={'native':render_native_view(native)}
dataset={'source':{'symbol':'SYNTHETIC','size':5,'kind':'minutes','clock':'UTC','id':'synthetic'},
    'view':{'points':points[:500]},'payload':{'chart_mode':'candles'}}
documents['dataset']=(SOURCE/'gnet_broker/dataset_chart_report.html').read_text().replace('__DATASET_CHART_DATA__',json.dumps(dataset))
documents['dataset-retained']='<html><body><h2>Retained synthetic chart</h2><div id="priceChart">Previous renderer</div><script>const DATA='+json.dumps(dataset)+'</script></body></html>'
for kind,days in [('days',1),('weeks',7),('months',31)]:
    dates=[{**p,'stamp':(datetime(2026,1,5)+timedelta(days=days*i)).isoformat()} for i,p in enumerate(points[:500])]
    calendar_dataset={**dataset,'source':{**dataset['source'],'kind':kind,'size':1},'view':{'points':dates}}
    documents['dataset-'+kind]='<html><body><h2>Synthetic '+kind+' chart</h2><div id="priceChart"></div><script>const DATA='+json.dumps(calendar_dataset)+'</script></body></html>'
engine_file=next((BASE/'.test_artifacts/scrolling-charts-unrestricted').rglob('viewer.html'))
engine=engine_file.read_text();match=re.search(r'<script id="view-data" type="application/json">(.*?)</script>',engine,re.S)
engine_data=json.loads(match[1]);v=engine_data['view'];seed=v['candles'][0];start=seed['start_ns']
v['candles']=[{**seed,'start_ns':start+i*30_000_000_000,'end_ns':start+(i+1)*30_000_000_000,
    'first_event':i*2,'last_event':i*2+1,'open':p['open'],'high':p['high'],'low':p['low'],'close':p['close']} for i,p in enumerate(points[:500])]
v['end_ns']=v['candles'][-1]['end_ns'];v['point_count']=500
documents['engine']=engine.replace(match[1],json.dumps(engine_data))
(OUT/'lightweight.js').write_bytes((SOURCE/'gnet_broker/lightweight_charts.js').read_bytes())
(OUT/'shared.js').write_bytes((BASE/'scripts/scrolling_bar_viewer.js').read_bytes())
diagnostics=r'''<script>
window.addEventListener('error',e=>{document.body.dataset.chartError=e.message;});
setTimeout(async()=>{try{const shell=document.getElementById('scrolling-bar-viewer');if(!shell)throw Error('Missing shared chart');
const chart=shell.gnetChart.chart,scale=chart.timeScale(),count=()=>{const r=scale.getVisibleLogicalRange();return r.to-r.from;};
if(Math.abs(count()-500)>2)throw Error('Default window does not show 500 bars: '+count());
const axisRules=GNETBarAxis;
for(const kind of ['days','daily','weeks','weekly'])if(axisRules.profile({kind,size:1}).scale!=='date')throw Error('Daily/weekly axis misclassified');
if(axisRules.profile({kind:'months',size:1}).scale!=='month')throw Error('Monthly axis misclassified');
for(const [day,utcOpen,utcClose]of [['2026-01-05','14:30','21:00'],['2026-07-06','13:30','20:00']]){
  const samples=[{stamp:day+'T'+utcOpen+':00Z'},{stamp:day+'T'+utcClose+':00Z'}];
  const marks=axisRules.cashMarkers(samples,'UTC',300);if(marks.length!==2||marks[0].label!=='OPEN'||marks[1].label!=='CLOSE')throw Error('Cash reference DST conversion failed');
  const chicago=axisRules.cashMarkers([{stamp:day+'T08:30:00'},{stamp:day+'T15:00:00'}],'America/Chicago',300);if(chicago.length!==2)throw Error('Source-clock conversion failed');
  if(axisRules.cashMarkers(samples,'UTC',3600).length)throw Error('Hourly chart incorrectly shows cash markers');
}
if(axisRules.cashMarkers([{stamp:'2026-01-10T09:30:00'},{stamp:'2026-01-10T16:00:00'}],'America/New_York',300).length)throw Error('Weekend markers should be absent');
if(axisRules.cashMarkers([{stamp:'2026-01-05T09:00:00'},{stamp:'2026-01-05T10:00:00'}],'America/New_York',300).length)throw Error('Cash marker bridged missing data');
if(axisRules.cashMarkers([{stamp:'2026-01-05T09:30:00'}],'unknown',300).length)throw Error('Unknown clock must not create a marker');
const profile=typeof DATA!=='undefined'?axisRules.profile(DATA.source):typeof view!=='undefined'?axisRules.profile(data.bar_definition):axisRules.profile(data.source);
const dates=shell.querySelectorAll(profile.scale==='time'?'[data-role=vertical-time]':'[data-role=vertical-date]');
const labelPattern=profile.scale==='month'?/^[A-Z][a-z]{2}$/:profile.scale==='date'?/^\d{2}-\d{2}$/:/^\d{2}:\d{2}(:\d{2})?$/;
if(!dates.length||!Array.from(dates).every(n=>n.getAttribute('transform').startsWith('rotate(90 ')&&labelPattern.test(n.textContent)))throw Error('Timeframe-aware vertical labels missing');
if(!shell.querySelector(profile.scale==='time'?'[data-role=day-label]':'[data-role=period-label]'))throw Error('Visible calendar badge missing');
if(typeof view==='undefined'&&!shell.querySelector(profile.scale==='time'?'[data-role=day-change]':'[data-role=period-change]'))throw Error('Calendar change boundary missing');
if(typeof DATA==='undefined'&&!shell.querySelector('[data-role=trade-duration]'))throw Error('Trade outcome duration missing from X-axis');
if(typeof view==='undefined'&&profile.seconds>0&&profile.seconds<3600&&shell.querySelectorAll('[data-role=cash-session-marker]').length<2)throw Error('Rendered cash open/close markers missing');
if(!(profile.seconds>0&&profile.seconds<3600)&&shell.querySelector('[data-role=cash-session-marker]'))throw Error('Cash markers present on ineligible chart');
Array.from(shell.querySelectorAll('button')).find(b=>b.textContent==='Zoom in').click();
await new Promise(r=>setTimeout(r,100));
if(Math.abs(count()-250)>2)throw Error('Zoom did not change visible bars: '+count());
const slider=shell.querySelector('input[type=range]');slider.value='37';slider.dispatchEvent(new Event('input'));
await new Promise(r=>setTimeout(r,100));
if(Math.abs(scale.getVisibleLogicalRange().from-36.5)>1)throw Error('Scrollbar did not pan');
Array.from(shell.querySelectorAll('button')).find(b=>b.textContent==='Show loaded window').click();
await new Promise(r=>setTimeout(r,100));
if(Math.abs(count()-500)>2)throw Error('Reset did not restore full loaded window');
const axis=document.getElementById('axis');if(axis){axis.value='time';axis.dispatchEvent(new Event('change'));axis.value='observations';axis.dispatchEvent(new Event('change'));}
const mode=document.getElementById('mode');if(mode){mode.value='line';mode.dispatchEvent(new Event('change'));}
document.body.dataset.chartAcceptance='passed';
}catch(e){document.body.dataset.chartAcceptance='failed';document.body.dataset.chartFailure=e.message;}},500);
</script>'''
results={}
edge=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
for name,html in documents.items():
    page=OUT/(name+'.html');page.write_text(html.replace('</body>','<script src="lightweight.js"></script><script src="shared.js"></script>'+diagnostics+'</body>'),encoding='utf-8')
    if '--prepare-only' in sys.argv:
        continue
    result=subprocess.run([edge,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
        '--user-data-dir='+str(OUT/(name+'-profile')),'--virtual-time-budget=1600','--dump-dom',page.as_uri()],capture_output=True,text=True,encoding='utf-8',timeout=40)
    body=re.search(r'<body[^>]*>',result.stdout)
    assert body and 'data-chart-acceptance="passed"' in body[0], (name,body[0] if body else result.stderr[-1000:])
    assert 'data-chart-error=' not in body[0],(name,body[0])
    results[name]={'passed':True,'bars':500,'zoom':True,'scrollbar':True,'reset':True}
if '--prepare-only' not in sys.argv:
    (OUT/'acceptance.json').write_text(json.dumps({'synthetic_only':True,'consecutive_windows':True,'charts':results},indent=2))
print(json.dumps({'synthetic_only':True,'consecutive_windows':True,'charts':results},indent=2))
