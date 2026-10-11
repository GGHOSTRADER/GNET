const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
function trash(h,{configured=true,protectedByFinal=false,retired=false}={}){
 pipeline(h);const priorResult=h.result;
 const actions=[];h.confirmations=[];h.api=(u,req)=>{if(u.pathname==='/api/confirm-source-management'){h.confirmations.push(req.postDataJSON());return {confirmed:true};}};
 h.result=(job)=>{
  if(job?.operation==='source_trash_catalog')return {usable:true,metrics:{trash:{records:[{kind:'dataset',id:'synthetic-retired',changed_at:'2026-01-05'}],next_offset:null}}};
  if(job?.operation==='source_management_plan')return {usable:true,metrics:{source_management_plan:{authentication_configured:configured,protected_by_final:protectedByFinal,trashed:retired,source_hash:'a'.repeat(64)}}};
  if(job?.operation==='source_management'){actions.push(job.payload);return {usable:true,metrics:{source_management:{action:job.payload.action}}};}
  return priorResult(job);
 };
 return actions;
}
async function openTrash(page){await page.goto('/research/#sharedResourcesStage');await expect(page.locator('#sharedResourcesStage')).toBeVisible();await page.locator('#sourceTrashInventory').evaluate(el=>el.open=true);await page.getByRole('button',{name:'Load Trash metadata',exact:true}).click();await expect(page.locator('#sourceTrashInventory')).toContainText('synthetic-retired');await page.locator('#sourceTrashInventory details').evaluateAll(rows=>rows.forEach(row=>row.open=true));}
test('Trash metadata is collapsed and restore binds hash through local confirmation API',async({page,harness})=>{trash(harness,{retired:true});await openTrash(page);await page.getByRole('button',{name:'Restore source',exact:true}).click();await expect(page.locator('#sourceTrashInventory')).toContainText('Committed restore');expect(harness.confirmations).toHaveLength(1);expect(harness.confirmations[0].payload).toEqual({target_kind:'dataset',target_id:'synthetic-retired',source_hash:'a'.repeat(64),action:'restore'});expect(JSON.stringify(harness.requests)).not.toMatch(/password|credential/i);});
for(const [name,options,message] of [['unconfigured authentication',{configured:false},'researcher confirmation needs reviewed protected setup'],['reserved final source',{protectedByFinal:true},'active final reservation/freeze protects this source']])test('Trash blocks '+name,async({page,harness})=>{trash(harness,options);await openTrash(page);await page.getByRole('button',{name:'Restore source',exact:true}).click();await expect(page.locator('#sourceTrashInventory')).toContainText(message);expect(harness.confirmations).toHaveLength(0);expect(harness.requests.some(r=>r.operation==='source_management')).toBe(false);});
