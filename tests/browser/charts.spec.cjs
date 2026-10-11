const fs=require('node:fs'),path=require('node:path');
const {test,expect}=require('./fixtures.cjs');
const base=path.resolve(__dirname,'../..');
const config=JSON.parse(fs.readFileSync(path.join(base,'.artifacts/client-delivery-installed/client-config.json'),'utf8'));
const packageRoot=process.env.GNET_BROWSER_PACKAGE||config.package_root;
function chartDocument(type,kind='minutes',size=5,extras={}){
 const points=Array.from({length:500},(_,i)=>({row:i+1,stamp:new Date(Date.UTC(2026,0,5,12)+i*300000).toISOString(),open:100+i*.01,high:102+i*.01,low:99+i*.01,close:101+i*.01}));
 const source={symbol:'SYNTHETIC',size,kind,bar_size:size,bar_kind:kind,clock:'UTC',source_timezone:'UTC',...extras};
 const trade={trade_id:'toy-1',outcome:'winner',status:'closed',side:1,signal_row:28,entry_row:29,exit_row:60,entry_price:101,exit_price:102,net_pnl:50};
 let content;
 if(type==='dataset')content=`<div id="priceChart"></div><script>const DATA=${JSON.stringify({source,view:{points},payload:{chart_mode:'candles'}})};</script>`;
 if(type==='native')content=`<div class="chart-container"><svg id="chart"></svg></div><script>const data=${JSON.stringify({source,chart:points,payload:{},page:[trade],selected:trade,chart_has_more:true})};function submit(p){window.lastChartRequest=p;}</script>`;
 if(type==='engine'){
  const candles=points.map((p,i)=>({...p,start_ns:Date.UTC(2026,0,5,12)*1e6+i*300e9,end_ns:Date.UTC(2026,0,5,12)*1e6+(i+1)*300e9,first_event:i,last_event:i}));
  const data={timezone:'UTC',bar_definition:source,view:{candles,matches:[{...trade,entry_event:28,exit_event:59,entry_ns:candles[28].start_ns,exit_ns:candles[59].start_ns}],aggregation_factor:1,end_ns:candles[499].end_ns}};
  content=`<select id="mode"><option value="candles">Candles</option><option value="line">Line</option></select><select id="display"><option value="both">Both</option><option value="bars">Bars</option></select><select id="axis"><option value="observations">Observations</option><option value="time">Time</option></select><input id="signals" type="checkbox"><button id="reset-chart">Reset</button><div id="matches"></div><svg id="chart"></svg><script>const data=${JSON.stringify(data)},view=data.view;function observationIndex(c,e,n){return c.findIndex(b=>b.first_event===e)};</script>`;
 }
 return `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:20px;background:#101a2a;color:#edf3ff}</style></head><body>${content}<script src="/research/assets/lightweight-charts.js"></script><script src="/research/assets/scrolling-bar-viewer.js"></script></body></html>`;
}
for(const type of ['dataset','native','engine'])test(`${type} shared chart fits 500 bars, zooms, scrolls and resets`,async({page,harness},testInfo)=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument(type)}));await page.goto('/fixture-chart');
 const shell=page.locator('#scrolling-bar-viewer');await expect(shell).toBeVisible();
 const range=()=>page.evaluate(()=>document.querySelector('#scrolling-bar-viewer').gnetChart.chart.timeScale().getVisibleLogicalRange());
 await expect.poll(async()=>{const r=await range();return Math.abs((r.to-r.from)-500)}).toBeLessThan(2);
 await shell.getByRole('button',{name:'Zoom in',exact:true}).click();await expect.poll(async()=>{const r=await range();return Math.abs((r.to-r.from)-250)}).toBeLessThan(2);
 await shell.locator('input[type=range]').fill('40');await expect.poll(async()=>Math.abs((await range()).from-39.5)).toBeLessThan(1);
 await shell.getByRole('button',{name:'Show loaded window',exact:true}).click();await expect.poll(async()=>{const r=await range();return Math.abs((r.to-r.from)-500)}).toBeLessThan(2);
 await expect(shell.locator('[data-role=vertical-time]').first()).toHaveText(/^\d\d:\d\d$/);
 await expect(shell.locator('[data-role=cash-session-marker][data-boundary=OPEN]')).toHaveCount(2);
 await expect(shell.locator('[data-role=cash-session-marker][data-boundary=CLOSE]')).toHaveCount(2);
 if(type!=='dataset')await expect(shell.locator('[data-role=trade-duration]')).toHaveCount(1);
 await testInfo.attach(type+'-chart',{body:await shell.screenshot(),contentType:'image/png'});
});
test('dataset window buttons send mode, date range and next offset',async({page,harness})=>{
 await page.route('**/reports/**/dataset_chart.html',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset')}));
 await page.goto('/dataset-chart/?export_id=ts-synthetic&date=2026-01-05');await page.locator('#mode').selectOption('line');await page.getByRole('button',{name:'Plot window',exact:true}).click();
 await expect(page.locator('#status')).toContainText('500 observations');await page.locator('#next').click();await expect.poll(()=>harness.requests.filter(r=>r.operation==='dataset_view').length).toBe(2);
 const r=harness.requests.filter(r=>r.operation==='dataset_view')[1];expect(r.payload).toMatchObject({offset:500,chart_mode:'line',max_points:500,export_id:'ts-synthetic',start_date:'2026-01-05',end_date:'2026-01-05'});
});
test('hourly charts omit cash-session markers',async({page,harness})=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset','hours',1)}));await page.goto('/fixture-chart');await expect(page.locator('#scrolling-bar-viewer')).toBeVisible();await expect(page.locator('[data-role=cash-session-marker]')).toHaveCount(0);
});
test('native later-bars button preserves consecutive window request',async({page,harness})=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('native')}));await page.goto('/fixture-chart');
 await page.getByRole('button',{name:'Later bars →',exact:true}).click();
 expect(await page.evaluate(()=>window.lastChartRequest)).toMatchObject({chart_offset:500,max_points:500});
 await expect(page.getByRole('button',{name:'← Earlier bars',exact:true})).toBeDisabled();
});
test('native Browse bars clears trade focus and resets source offset',async({page,harness})=>{
 const document=chartDocument('native').replace('"payload":{}','"payload":{"export_id":"toy","selected_trade_id":"toy-1","chart_offset":500}');
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:document}));await page.goto('/fixture-chart');
 await page.getByRole('button',{name:'Browse bars',exact:true}).click();
 const request=await page.evaluate(()=>window.lastChartRequest);
 expect(request).toMatchObject({export_id:'toy',chart_offset:0,max_points:500});
 expect(request).not.toHaveProperty('selected_trade_id');
});
test('chart mode switches to a visibly different price-line rendering',async({page,harness})=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset')}));await page.goto('/fixture-chart');
 const host=page.locator('#scrolling-bar-viewer');await expect(host).toBeVisible();
 const before=await host.screenshot();await page.getByRole('combobox',{name:'Price chart mode'}).selectOption('line');
 await expect.poll(async()=>!(await host.screenshot()).equals(before)).toBe(true);
});
test('cash reference conversion handles summer/winter DST, gaps and unknown clocks',async({page,harness})=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset')}));await page.goto('/fixture-chart');
 const facts=await page.evaluate(()=>{
  const marks=(points,clock,seconds)=>GNETBarAxis.cashMarkers(points,clock,seconds).map(m=>m.label);
  return {winter:marks([{stamp:'2026-01-05T14:30:00Z'},{stamp:'2026-01-05T21:00:00Z'}],'UTC',300),
   summer:marks([{stamp:'2026-07-06T13:30:00Z'},{stamp:'2026-07-06T20:00:00Z'}],'UTC',300),
   unknown:marks([{stamp:'2026-01-05T09:30:00'}],'unknown',300),
   gap:marks([{stamp:'2026-01-05T09:00:00'},{stamp:'2026-01-05T10:00:00'}],'America/New_York',300)};
 });expect(facts).toEqual({winter:['OPEN','CLOSE'],summer:['OPEN','CLOSE'],unknown:[],gap:[]});
});
test('captured stock metadata appears with exchange reference hours',async({page,harness})=>{
 const extras={symbol:'BTC',symbol_attributes:{status:'loaded',country_raw:'United States',exchange_raw:'ARCX',symbol_type:'stock',point_value:1},session_reference:{timezone:'America/New_York',label:'ARCX core-session reference',basis:'reference_only',open:'09:30:00',close:'16:00:00'}};
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset','minutes',5,extras)}));await page.goto('/fixture-chart');
 await expect(page.locator('[data-role=instrument-metadata]')).toContainText('Country: United States · Exchange: ARCX · Type: stock');
 await expect(page.locator('#scrolling-bar-viewer')).toContainText('ARCX core-session reference');
 await expect(page.locator('[data-role=cash-session-marker][data-boundary=OPEN]').first()).toHaveAttribute('data-timezone','America/New_York');
});
test('unresolved exchange suppresses inherited US session hours',async({page,harness})=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset','minutes',5,{session_reference:null})}));await page.goto('/fixture-chart');
 await expect(page.locator('#scrolling-bar-viewer')).toBeVisible();
 await expect(page.locator('[data-role=cash-session-marker]')).toHaveCount(0);
 await expect(page.locator('#scrolling-bar-viewer')).toContainText('Session markers unavailable');
});
test('dated session markers respect early close, closed days and overnight windows',async({page,harness})=>{
 await page.route('**/fixture-chart',r=>r.fulfill({contentType:'text/html',body:chartDocument('dataset')}));await page.goto('/fixture-chart');
 const facts=await page.evaluate(()=>{
  const points=[{stamp:'2026-11-27T14:30:00Z'},{stamp:'2026-11-27T18:00:00Z'},{stamp:'2026-11-27T21:00:00Z'}];
  const ref={timezone:'America/New_York',sessions:[{session:'2026-11-27',open:'09:30:00',close:'13:00:00'}]};
  return {early:GNETBarAxis.cashMarkers(points,'UTC',300,300,ref).map(m=>m.label+' '+m.time),
   closed:GNETBarAxis.cashMarkers(points,'UTC',300,300,{...ref,sessions:[]}),
   overnight:GNETBarAxis.cashMarkers([{stamp:'2026-11-26T23:00:00Z'},{stamp:'2026-11-27T22:00:00Z'}],'UTC',300,300,{timezone:'America/Chicago',sessions:[{session:'2026-11-27',open:'17:00:00',close:'16:00:00'}]}).map(m=>m.label+' '+m.day+' '+m.time)};
 });expect(facts).toEqual({early:['OPEN 09:30','CLOSE 13:00'],closed:[],overnight:['OPEN 2026-11-26 17:00','CLOSE 2026-11-27 16:00']});
});
test('dataset worker failure appears in the chart status',async({page,harness})=>{
 harness.fail='dataset_view';await page.goto('/dataset-chart/?export_id=ts-synthetic&date=2026-01-05');await page.getByRole('button',{name:'Plot window',exact:true}).click();await expect(page.locator('#status')).toContainText('Chart is not usable');await expect(page.locator('#next')).toBeDisabled();
});
