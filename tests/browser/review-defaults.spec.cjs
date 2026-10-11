const {test,expect,openReview,approve}=require('./fixtures.cjs');
for(const scenario of [
 {name:'captured bars',kind:'minutes',size:5,captured:true,processes:['bar_features','training']},
 {name:'time bars',kind:'minutes',size:5,processes:['primary_research','bar_features','training']},
 {name:'aggregated tick bars',kind:'ticks',size:100,processes:['primary_research','bar_features','training']},
 {name:'volume bars',kind:'volume',size:500,processes:['primary_research','bar_features','training']},
 {name:'individual ticks',kind:'ticks',size:1,processes:['vp_features','bar_building']},
 {name:'unknown source',kind:'unknown',size:1,processes:[]},
])test('review defaults for '+scenario.name,async({page,harness})=>{
 Object.assign(harness.template.source,{interval_kind:scenario.kind,interval_size:scenario.size});
 if(!scenario.captured){delete harness.template.captured_evidence;delete harness.template.policy.review_basis;harness.template.primary_review=null;}
 await openReview(page);
 expect(await page.locator('[data-process]:checked').evaluateAll(nodes=>nodes.map(n=>n.dataset.process))).toEqual(scenario.processes);
 await expect(page.locator('#realScope')).not.toBeChecked();await expect(page.locator('#platformCheck')).not.toBeChecked();
 await expect(page.locator('#processDefaultsHelp')).toContainText(scenario.processes.length?'selected':'not recognized');
 if(!scenario.processes.length){await page.locator('#realScope').check();await page.locator('#draft').click();await expect(page.locator('#approvalStatus')).toContainText('Select at least one');expect(harness.requests.filter(r=>r.operation==='draft_ts_review')).toHaveLength(0);return;}
 await approve(page);expect(harness.requests.find(r=>r.operation==='draft_ts_review').payload.policy.approved_processes).toEqual(scenario.processes);
});
test('user removals survive validation refresh and define exact permission',async({page,harness})=>{
 await openReview(page);await page.locator('[data-process="training"]').uncheck();
 await page.locator('#template').click();await expect(page.locator('#template')).toBeEnabled();
 await expect(page.locator('[data-process="training"]')).not.toBeChecked();
 await approve(page);expect(harness.requests.find(r=>r.operation==='draft_ts_review').payload.policy.approved_processes).toEqual(['bar_features']);
});
