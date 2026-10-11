const {test,expect,openReview,approve}=require('./fixtures.cjs');
test('automatic validation renders evidence and keeps downstream gates closed',async({page,harness})=>{
 await openReview(page);await expect(page.locator('#automaticResults')).toContainText('PASS');
 for(const id of ['register','prepareNative','buildTraining'])await expect(page.locator('#'+id)).toBeDisabled();
 expect(harness.requests.map(r=>r.operation)).toEqual(['ts_review_template']);
});
test('unchecked authorization explains why and sends no approval',async({page,harness})=>{
 await openReview(page);await page.locator('#draft').click();
 await expect(page.locator('#approvalStatus')).toContainText('Check the research authorization box');
 expect(harness.requests.filter(r=>r.operation==='draft_ts_review')).toHaveLength(0);
});
test('approval sends exact selected source/processes and truthful evidence',async({page,harness})=>{
 await openReview(page);await approve(page);
 const r=harness.requests.find(r=>r.operation==='draft_ts_review');
 expect(r.payload.policy.real_data_authorized).toBe(true);
 expect(r.payload.policy.approved_processes).toEqual(['bar_features','training']);
 expect(r.payload.primary_review.source_contract.fill_properties_reviewed).toBe(false);
 expect(r.payload.primary_review.source_contract.platform_snapshot_reviewed).toBe(false);
 expect(r.payload.primary_review.source_contract.fill_review_basis).toBe('validated_recorded_ledger');
 await expect(page.locator('#result')).toContainText('review-synthetic');
 await expect(page.locator('#register')).toBeDisabled();
});
test('an open page refreshes its release pin before approval',async({page,harness})=>{
 await openReview(page);harness.release='guarded-synthetic-new';await approve(page);
 expect(harness.requests.find(r=>r.operation==='draft_ts_review').release_id).toBe('guarded-synthetic-new');
});
test('worker rejection is visible beside approval and can be retried',async({page,harness})=>{
 await openReview(page);harness.fail='draft_ts_review';await page.locator('#realScope').check();await page.locator('#draft').click();
 await expect(page.locator('#approvalStatus')).toContainText('Synthetic worker rejection');
 await expect(page.locator('#draft')).toBeEnabled();harness.fail=null;await approve(page);
});
test('in-flight approval shows progress and prevents duplicate submission',async({page,harness})=>{
 await openReview(page);harness.delay=600;await page.locator('#realScope').check();await page.locator('#draft').click();
 await expect(page.locator('#draft')).toBeDisabled();await expect(page.locator('#approvalStatus')).toContainText('Saving approval proposal');
 await expect(page.locator('#approvalStatus')).toContainText('Approval proposal saved');
 expect(harness.requests.filter(r=>r.operation==='draft_ts_review')).toHaveLength(1);
});
test('failed validation keeps approval disabled with visible reason',async({page,harness})=>{
 harness.fail='ts_review_template';await page.goto('/reviews/?export_id=ts-synthetic');
 await expect(page.locator('#validationJobStatus')).toContainText('Synthetic worker rejection');await expect(page.locator('#draft')).toBeDisabled();
});
test('review requires an explicitly selected export',async({page,harness})=>{
 await page.goto('/reviews/');await expect(page.locator('#notice')).toContainText('Select a received source');await expect(page.locator('#draft')).toBeDisabled();expect(harness.requests).toHaveLength(0);
});
test('pending registration does not unlock source preparation',async({page,harness})=>{
 await openReview(page);await approve(page);harness.review.policy_active=true;harness.registration=false;await page.locator('#status').click();await expect(page.locator('#register')).toBeEnabled();await page.locator('#register').click();await expect(page.locator('#notice')).toContainText('Admission still pending');await expect(page.locator('#prepareNative')).toBeDisabled();
});
test('activation then registration then preparation unlocks the correct next stage',async({page,harness})=>{
 await openReview(page);await approve(page);harness.review.policy_active=true;harness.review.status='active';
 await page.locator('#status').click();await expect(page.locator('#register')).toBeEnabled();
 await page.locator('#register').click();await expect(page.locator('#notice')).toContainText('Source registered');
 await page.locator('#prepareNative').click();await expect(page.locator('#buildTraining')).toBeEnabled();
 // Prevent pipeline startup: verify navigation target without unrelated jobs.
 await page.route('**/research/pipeline/**',r=>r.fulfill({body:'Synthetic next stage'}));
 await page.locator('#buildTraining').click();await expect(page).toHaveURL(/dataset_id=synthetic-dataset#primaryStage/);
 expect(harness.requests.find(r=>r.operation==='ingest_ts_export').payload).toEqual({export_id:'ts-synthetic',policy_id:'review-synthetic'});
 expect(harness.requests.find(r=>r.operation==='prepare_ts_primary_source').payload).toEqual({dataset_id:'synthetic-dataset',review_id:'primary-synthetic'});
});
for(const width of [1440,768,390])test(`review renders readable controls at ${width}px`,async({page,harness},testInfo)=>{
 await page.setViewportSize({width,height:1000});await openReview(page);
 await expect(page.locator('#draft')).toBeVisible();
 const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,background:getComputedStyle(document.querySelector('section')).backgroundColor,color:getComputedStyle(document.querySelector('section')).color}));
 expect(layout.scroll).toBeLessThanOrEqual(layout.width+1);expect(layout.color).not.toBe(layout.background);
 await testInfo.attach('review-layout',{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
 await expect(page).toHaveScreenshot(`review-${width}.png`,{fullPage:true,animations:'disabled',maxDiffPixelRatio:0.005});
});
