const {test,expect,openReview}=require('./fixtures.cjs');
test('selected source metadata stays visible when automatic validation fails',async({page,harness})=>{
 harness.receipts=[{export_id:'ts-synthetic',state:'stored',imported_at_utc:'2026-01-06T12:00:00Z',custody:{symbol:'SYNTHETIC-ES',bar_kind:'minutes',bar_size:5,rows:500,first_timestamp:'2026-01-05T08:00:00',last_timestamp:'2026-01-05T16:00:00',source_metadata:{source_timezone:'America/Chicago'}}}];
 harness.fail='ts_review_template';await page.goto('/reviews/?export_id=ts-synthetic');
 await expect(page.locator('#validationJobStatus')).toContainText('Validation failed');
 await expect(page.getByRole('region',{name:'Selected source metadata'})).toContainText('SYNTHETIC-ES');
 await expect(page.locator('#selectedSourceMetadata')).toContainText('500');await expect(page.locator('#selectedSourceMetadata')).toContainText('America/Chicago');await expect(page.locator('#draft')).toBeDisabled();
});
test('recorded fabricated scope is passed before initial validation',async({page,harness})=>{
 harness.receipts=[{export_id:'ts-synthetic',state:'stored',custody:{symbol:'SYNTHETIC-ES',synthetic:true,bar_kind:'minutes',bar_size:5}}];
 await openReview(page);expect(harness.requests.find(r=>r.operation==='ts_review_template').payload.synthetic).toBe(true);
 await expect(page.locator('#selectedSourceMetadata')).toContainText('SYNTHETIC-ES');
});
test('unknown asset shows missing instrument metadata and keeps approval closed',async({page,harness})=>{
 harness.template={ready:false,needs_instrument_profile:true,source:{symbol:'FABRICATED-STOCK',series_type:'unclassified',interval_kind:'minutes',interval_size:5},coverage:{rows:78},reason:'No reviewed instrument profile is saved. Save its exchange, timezone, tick size, multiplier and volume units once.'};
 await page.goto('/reviews/?export_id=ts-synthetic');
 await expect(page.locator('#automaticResults')).toContainText('No reviewed instrument profile');
 await expect(page.locator('#automaticResults')).toContainText('exchange, timezone, tick size, multiplier');
 await expect(page.locator('#selectedSourceMetadata')).toContainText('FABRICATED-STOCK');
 await expect(page.locator('#draft')).toBeDisabled();
 expect(harness.requests.filter(r=>r.operation==='draft_ts_review')).toHaveLength(0);
});
test('selected source shows captured country exchange type and point value',async({page,harness})=>{
 harness.receipts=[{export_id:'ts-synthetic',state:'stored',custody:{symbol:'BTC',bar_kind:'minutes',bar_size:5,source_metadata:{symbol_attributes:{country_raw:'United States',exchange_raw:'ARCX',symbol_type:'stock',point_value:1,chart_big_point_value:1,min_move:1,price_scale:100,status:'loaded',captured_at_local:'2026-10-11T10:00:00'}}}}];
 await openReview(page);
 const metadata=page.locator('#selectedSourceMetadata');await expect(metadata).toContainText('United States');await expect(metadata).toContainText('ARCX');await expect(metadata).toContainText('stock');await expect(metadata).toContainText('Point value');
});
