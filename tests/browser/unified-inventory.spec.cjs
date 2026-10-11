const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
function setup(h){
 const {progress}=pipeline(h);const source=progress.selected;
 Object.assign(source,{dataset_id:source.id,origin_export_id:'ts-toy',source_hash:'a'.repeat(64),has_primary:true});
 h.receipts=[{export_id:'ts-toy',state:'stored',imported_at_utc:'2026-01-06T12:00:00Z',custody:{source_sha256:source.source_hash,symbol:'ES',bar_kind:'minutes',bar_size:5,rows:500,first_timestamp:'2026-01-05T08:00:00',last_timestamp:'2026-01-05T16:00:00',primary_report:{strategy_id:'toy',closed_trades:10}}},
 {export_id:'ts-pending',state:'stored',custody:{symbol:'NQ',bar_kind:'minutes',bar_size:5,rows:200,first_timestamp:'2026-01-05T08:00:00',last_timestamp:'2026-01-05T16:00:00'}}];
 return source;
}
test('received export and registered primary share one expandable row and exact actions',async({page,harness})=>{
 setup(harness);await page.goto('/research/');await expect(page.locator('#catalogCount')).toContainText('1 loaded');
 await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(2);
 await expect(page.locator('#sourcePrimaryInventoryAccess')).toHaveCount(0);
 const row=page.locator('#delivery-ts-toy');expect(await row.getAttribute('open')).toBeNull();await row.locator(':scope>summary').click();
 await expect(row.getByRole('link',{name:'Review / register source',exact:true})).toHaveAttribute('href','/reviews/?export_id=ts-toy');
 await expect(row.getByRole('link',{name:'OPEN IMPORTED TS PRIMARY TRADES',exact:true})).toHaveAttribute('href','/ts-trades/?export_id=ts-toy');
 await expect(row.getByRole('link',{name:'Open research pipeline',exact:true})).toHaveAttribute('href','/research/pipeline/?dataset_id=synthetic-dataset#primaryStage');
 await expect(row).toContainText('Permitted processes:');
});
for(const width of [1440,390])test(`dataset breakdown displays captured instrument attributes at ${width}px`,async({page,harness})=>{
 await page.setViewportSize({width,height:1000});setup(harness);harness.receipts[0].custody.symbol='BTC';harness.receipts[0].custody.source_metadata={symbol_attributes:{country_raw:'United States',exchange_raw:'ARCX',symbol_type:'stock',point_value:1,chart_big_point_value:1,min_move:1,price_scale:100,status:'loaded',captured_at_local:'2026-01-06T06:59:50'}};
 await page.goto('/research/');await expect(page.locator('#catalogCount')).toContainText('1 loaded');const row=page.locator('#delivery-ts-toy');await row.locator(':scope>summary').click();
 await expect(row).toContainText('United States');await expect(row).toContainText('ARCX');await expect(row).toContainText('stock');
 await page.screenshot({path:require('node:path').resolve(__dirname,`../../.test_artifacts/browser/symbol-metadata-${width}.png`),fullPage:true});
});
test('registered dataset inspection shows instrument specification and captured metadata',async({page,harness})=>{
 const profile=setup(harness),old=harness.result;harness.result=(job,id)=>job.operation==='data_inventory'?{usable:true,execution_status:'published',metrics:{dataset:{dataset_id:profile.dataset_id,provider_symbol:'BTC',synthetic:true,source_kind:'source_bars',source_size:300,source_bar_kind:'time',price_basis:'unadjusted',validation_status:'pass',lifecycle_status:'active',coverage:{timezone:'America/New_York',start_session:'2026-01-05',end_session:'2026-01-05',row_count:500},instrument_specification:{tick_size:.01,multiplier:1,volume_units:'shares'},symbol_attributes:{country_raw:'United States',exchange_raw:'ARCX',symbol_type:'stock'}}}}:old(job,id);
 await page.goto('/research/');await expect(page.locator('#catalogCount')).toContainText('1 loaded');const row=page.locator('#delivery-ts-toy');await row.locator(':scope>summary').click();await row.getByRole('button',{name:'Inspect metadata',exact:true}).click();
 await expect.poll(()=>harness.requests.filter(r=>r.operation==='data_inventory').length).toBe(1);
 await expect(page.locator('#sourceFacts')).toContainText('United States');await expect(page.locator('#sourceFacts')).toContainText('ARCX');await expect(page.locator('#sourceFacts')).toContainText('shares');
 await expect(page.locator('#sourceFacts')).toBeVisible();
 expect(harness.requests.find(r=>r.operation==='data_inventory').payload.dataset_id).toBe(profile.dataset_id);
});
test('status filters exclude rows and primary shortcut uses the same inventory',async({page,harness})=>{
 setup(harness);await page.goto('/research/');await expect(page.locator('#catalogCount')).toContainText('1 loaded');
 const status=page.getByLabel('Status / contents');await status.selectOption('pending');await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(1);await expect(page.locator('#delivery-ts-pending')).toBeVisible();
 await page.locator('#approvedTab').click();await expect(status).toHaveValue('approved');await expect(page.locator('#delivery-ts-toy')).toBeVisible();await expect(page.locator('#delivery-ts-pending')).toHaveCount(0);
 await page.locator('#rawTab').click();await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(2);
 await page.goto('/research/#primarySources');await expect(page.getByLabel('Status / contents')).toHaveValue('primary');await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(1);
});
for(const width of [1440,768,390])test('unified inventory layout '+width,async({page,harness})=>{
 setup(harness);await page.setViewportSize({width,height:1100});await page.goto('/research/');
 await expect(page.locator('#catalogCount')).toContainText('1 loaded');await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(2);
 await expect(page.locator('#rawPanel')).toHaveScreenshot('unified-inventory-'+width+'.png');
});
