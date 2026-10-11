const {test,expect}=require('./fixtures.cjs');
const {pipeline,openPipeline,openDetails}=require('./pipeline-fixture.cjs');
async function delayedResult(page,h,always){let misses=0;
 await page.route('**/api/result?job_id=*',async route=>{
 const id=new URL(route.request().url()).searchParams.get('job_id');const index=Number(id.split('-').at(-1))-1;
 if(h.requests[index]?.operation==='analyze_features'&&(always||misses===0)){misses++;return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({error:'Published result unavailable'})});}
 return route.fallback();
 });return ()=>misses;
}
test('publication delay is retried without submitting the calculation twice',async({page,harness})=>{
 pipeline(harness);const misses=await delayedResult(page,harness,false);await openPipeline(page,'featuresStage');await openDetails(page,'featureAnalysisPanel');
 await page.locator('#analyzeSelectedFeatures').click();await expect(page.locator('#featureAnalysisState')).toContainText('120 training-prefix rows');
 expect(misses()).toBe(1);expect(harness.requests.filter(r=>r.operation==='analyze_features')).toHaveLength(1);
});
test('missing publication stops after bounded retries and preserves job identity',async({page,harness})=>{
 pipeline(harness);const misses=await delayedResult(page,harness,true);await openPipeline(page,'featuresStage');await openDetails(page,'featureAnalysisPanel');
 await page.locator('#analyzeSelectedFeatures').click();await expect(page.locator('#featureAnalysisState')).toContainText('Published result unavailable',{timeout:15000});await expect(page.locator('#featureAnalysisState')).toContainText('job-synthetic-');
 expect(misses()).toBe(9);expect(harness.requests.filter(r=>r.operation==='analyze_features')).toHaveLength(1);await expect(page.locator('#analyzeSelectedFeatures')).toBeEnabled();
});
test('feature sections follow 3.1, 3.2, 3.3 after metadata refresh',async({page,harness})=>{
 pipeline(harness);await openPipeline(page,'featuresStage');
 expect(await page.locator('#featuresStage>.module-subsection').evaluateAll(nodes=>nodes.map(n=>n.id))).toEqual(['featureEngineeringPanel','featureDatasetJoin','featureAnalysisPanel']);
});
