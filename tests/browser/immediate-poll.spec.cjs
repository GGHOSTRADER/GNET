const {test,expect}=require('./fixtures.cjs');
const {pipeline,openPipeline}=require('./pipeline-fixture.cjs');
test('ready metadata does not pay first-poll delay and feature refresh reuses metadata',async({page,harness,performanceProfile})=>{
 pipeline(harness);await openPipeline(page,'sharedResourcesStage');
 await page.locator('#refresh').evaluate(el=>{for(let parent=el.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;});
 await expect(page.locator('#refresh')).toBeEnabled();
 await page.locator('#refresh').click();await expect(page.locator('#refresh')).toBeEnabled();
 const featureRequests=harness.requests.filter(r=>r.operation==='feature_inventory');
 expect(featureRequests.length).toBe(new Set(featureRequests.map(r=>JSON.stringify(r.payload))).size);
 expect(harness.requests.filter(r=>r.operation==='research_progress')).toHaveLength(2);
 const profile=await performanceProfile.stop();
 for(const job of profile.jobs.filter(j=>['research_progress','feature_inventory'].includes(j.operation)))expect(job.durationMs).toBeLessThan(500);
});
test('pending jobs retain polling backoff without duplicate submissions',async({page,harness})=>{
 pipeline(harness);const statusTimes=[];let pending=true;
 harness.api=u=>{if(u.pathname==='/api/status'){statusTimes.push(Date.now());if(pending){pending=false;return {state:'running'}}}};
 await openPipeline(page,'trainingStage');
 expect(statusTimes[1]-statusTimes[0]).toBeGreaterThanOrEqual(650);
 expect(harness.requests.filter(r=>r.operation==='research_progress')).toHaveLength(1);
});
