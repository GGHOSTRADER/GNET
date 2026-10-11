const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
const {budgets,violations,percentile}=require('./performance-profile.cjs');
const {performance}=require('node:perf_hooks');
function setup(h){pipeline(h);const result=h.result;h.result=(job,id)=>{const value=result(job,id);if(job?.operation==='data_catalog')value.metrics.catalog.metadata_only=true;return value};h.api=u=>u.pathname==='/api/client-health'?{client_assets_passed:true,client_release_id:'synthetic-client',broker_release_id:h.release}:u.pathname==='/api/client-inbox'?{entries:[],next_offset:null}:u.pathname==='/api/transfer-status'?{entries:[],next_offset:null,enabled:true}:undefined;}
const screens=[
 ['source inventory','/research/','#catalogCount','1 loaded'],
 ['source review','/reviews/?export_id=ts-synthetic','#validationJobStatus','Validation finished'],
 ['export inbox','/intake/','#boundary','enabled'],
 ['legacy primary inventory','/imported-primaries/','#status','metadata only'],
 ...['primaryStage','featuresStage','trainingStage','finalStage','sharedResourcesStage'].map(stage=>[stage,'/research/pipeline/#'+stage,'#'+stage,'']),
 ['dataset chart','/dataset-chart/?export_id=ts-synthetic&date=2026-01-05','#status','500 observations'],
 ['help and client health','/help/','#status','Client assets are available'],
 ['native primary viewer','/ts-trades/?export_id=missing','#status','No verified primary report'],
];
for(const [name,url,selector,text] of screens)for(let sample=1;sample<=3;sample++)test('screen readiness '+name+' sample '+sample,async({page,harness,performanceProfile},testInfo)=>{
 setup(harness);if(name==='dataset chart')await page.route('**/reports/**/dataset_chart.html',r=>r.fulfill({contentType:'text/html',body:'<p>Fabricated chart report</p>'}));const started=performance.now();await page.goto(url);
 if(url.startsWith('/research/pipeline/'))await page.locator('#featureInventoryOptions input').first().waitFor({state:'attached'});
 if(name==='dataset chart')await page.getByRole('button',{name:'Plot window',exact:true}).click();
 const target=page.locator(selector);if(text)await expect(target).toContainText(text);else await expect(target).toBeVisible();
 const durationMs=performance.now()-started;
 await testInfo.attach('screen-readiness',{body:Buffer.from(JSON.stringify({screen:name,sample,durationMs,budgetMs:budgets.screenMs,mode:'fabricated-api'})),contentType:'application/json'});
 expect(durationMs,name+' exceeded its visible-readiness budget').toBeLessThan(budgets.screenMs);
});
test('cached inventory ready within warm-load budget',async({page,harness},testInfo)=>{
 setup(harness);await page.goto('/research/');await expect(page.locator('#status')).toContainText('Inventories refreshed');
 const samples=[];for(let i=0;i<3;i++){const started=performance.now();await page.reload();await expect(page.locator('#status')).toContainText('Saved inventory summary');samples.push(performance.now()-started);}
 await testInfo.attach('screen-readiness',{body:Buffer.from(JSON.stringify({screen:'warm inventory',samplesMs:samples,p95Ms:percentile(samples,.95),budgetMs:budgets.warmInventoryMs})),contentType:'application/json'});
 expect(Math.max(...samples)).toBeLessThan(budgets.warmInventoryMs);
 expect(harness.requests.filter(r=>r.operation==='data_catalog')).toHaveLength(1);
});
test('timing guard detects slow requests and computes tail latency',()=>{
 expect(violations([{endpoint:'/api/config',durationMs:2001},{endpoint:'/api/config',durationMs:20}])).toHaveLength(1);
 expect(percentile([10,20,1000],.95)).toBe(1000);
});
