const {test,expect}=require('./fixtures.cjs');
function receipts(){return [
 {export_id:'ts-bars',state:'stored',custody:{symbol:'ES',bar_kind:'minutes',bar_size:5,rows:100}},
 {export_id:'ts-ticks',state:'stored',custody:{symbol:'ES',bar_kind:'ticks',bar_size:1,rows:100}},
 {export_id:'ts-primary',state:'stored',custody:{symbol:'ES',bar_kind:'minutes',bar_size:5,rows:100,primary_report:{closed_trades:12}}},
 {export_id:'ts-tick-bars',state:'stored',custody:{symbol:'ES',bar_kind:'ticks',bar_size:100,rows:100}}
];}
function configure(h,staged=[]){h.receipts=receipts();h.api=u=>{
 if(u.pathname==='/api/transfer-status')return {entries:h.receipts,next_offset:null,enabled:true};
 if(u.pathname==='/api/client-inbox')return {entries:staged,next_offset:null,scan_complete:true};
};}
test('stored delivery summaries distinguish bars, individual ticks and primary trades',async({page,harness})=>{
 configure(harness);await page.goto('/intake/');await expect(page.locator('#custodyReceipts>.delivery-card')).toHaveCount(4);
 for(const [id,key,text] of [['ts-bars','bars','Bar'],['ts-ticks','ticks','1 T'],['ts-primary','primary','Bar + PT'],['ts-tick-bars','bars','Bar']]){
 const label=page.locator('#delivery-'+id+' summary .delivery-category');await expect(label).toHaveText(text);await expect(label).toHaveAttribute('data-source-category',key);
 }
 await expect(page.getByLabel('Delivery content legend')).toContainText('Individual 1-tick data');
 await expect(page.getByLabel('Delivery content legend')).toContainText('Bar + PT = TradeStation bars + primary trades');
 await expect(page.locator('#delivery-ts-primary summary .delivery-category')).toHaveAttribute('title','TradeStation bars + primary trades');
 const colors=await page.locator('.delivery-category-legend .delivery-category').evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n).backgroundColor));expect(new Set(colors).size).toBe(3);
 await page.screenshot({path:'../../.test_artifacts/browser/delivery-category-layout.png',fullPage:true});
});
test('delivery content filters exclude other export types',async({page,harness})=>{
 configure(harness);await page.goto('/intake/');await expect(page.locator('#custodyReceipts>.delivery-card')).toHaveCount(4);
 for(const [value,ids] of [['primary',['ts-primary']],['ticks',['ts-ticks']],['bars',['ts-bars','ts-tick-bars']]]){
 await page.locator('#deliveryStatus').selectOption(value);await expect(page.locator('#custodyReceipts>.delivery-card')).toHaveCount(ids.length);
 for(const id of ids)await expect(page.locator('#delivery-'+id)).toBeVisible();
 }
 await page.locator('#clearDeliveryFilters').click();await expect(page.locator('#custodyReceipts>.delivery-card')).toHaveCount(4);
});
test('staged summaries use observed metadata and keep unknown exports pending',async({page,harness})=>{
 const chart={symbol:'ES',bar_kind:'minutes',bar_size:5,start:'2026-01-05T08:00:00',end:'2026-01-05T16:00:00'};
 const item=(id,observed,extra={})=>({export_id:id,identity_status:'metadata_reported',state:'Writing',alerts:[],controls_present:{},observed_chart:observed,...extra});
 configure(harness,[item('stage-primary',chart,{has_primary:true}),item('stage-ticks',{...chart,bar_kind:'ticks',bar_size:1}),item('stage-bars',chart),item('stage-unknown',null,{requested_chart:{asset:'ES',bar_kind:'ticks',bar_size:1}})]);
 await page.goto('/intake/');await expect(page.locator('#entries>.staged-delivery')).toHaveCount(4);
 await expect(page.locator('#entries>details').nth(0).locator(':scope>summary .delivery-category')).toHaveText('Bar + PT');
 await expect(page.locator('#entries>details').nth(1).locator(':scope>summary .delivery-category')).toHaveText('1 T');
 await expect(page.locator('#entries>details').nth(2).locator(':scope>summary .delivery-category')).toHaveText('Bar');
 await expect(page.locator('#entries>details').nth(3).locator(':scope>summary .delivery-category')).toHaveText('Source type pending');
});
