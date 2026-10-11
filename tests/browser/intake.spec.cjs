const {test,expect}=require('./fixtures.cjs');
function intake(h){
 h.http=[];h.api=(u,req)=>{
  if(u.pathname==='/api/client-inbox')return {entries:[],next_offset:null};
  if(u.pathname==='/api/transfer-status')return {entries:[],next_offset:null,enabled:true};
  if(['/api/prepare-export-inbox','/api/prepare-primary-exporter','/api/transfer-exports','/api/custody-acceptance'].includes(u.pathname)){h.http.push({path:u.pathname,body:req.postDataJSON()});return {source_file:'synthetic-exporter.txt',protected_boundary_enabled:true,enabled:true,queued:2,passed:true};}
 };
}
for(const [id,path,text] of [['prepareInbox','/api/prepare-export-inbox','Full indicator source'],['preparePrimary','/api/prepare-primary-exporter','Create a Strategy'],['transferNow','/api/transfer-exports','Queued 2'],['retryTransfers','/api/transfer-exports','Queued 2'],['testCustody','/api/custody-acceptance','Synthetic custody passed']])test('intake '+id+' sends action and shows outcome',async({page,harness})=>{intake(harness);await page.goto('/intake/');await page.locator('#'+id).click();await expect(page.locator('#transferMessage')).toContainText(text);const r=harness.http.find(r=>r.path===path);expect(r).toBeDefined();if(path==='/api/transfer-exports')expect(r.body).toEqual({max_exports:8,retry_failed:id==='retryTransfers'});if(id==='testCustody')expect(r.body).toEqual({wait_seconds:45});});
test('intake matched source preparation sends dataset and protected review',async({page,harness})=>{intake(harness);await page.goto('/intake/');await page.locator('#preparePrimarySource').evaluate(el=>el.closest('details').open=true);await page.locator('#primaryDataset').fill('synthetic-dataset');await page.locator('#primaryReview').fill('synthetic-review');await page.locator('#preparePrimarySource').click();await expect(page.locator('#primarySourceMessage')).toContainText('Queued matched source preparation');expect(harness.requests.at(-1)).toMatchObject({operation:'prepare_ts_primary_source',payload:{dataset_id:'synthetic-dataset',review_id:'synthetic-review'}});});
test('pending custody test prevents duplicate requests and recovers after failure',async({page,harness})=>{
 intake(harness);const prior=harness.api;let release;const pending=new Promise(resolve=>release=resolve);let attempts=0;
 harness.api=async(u,req)=>{if(u.pathname==='/api/custody-acceptance'){attempts++;if(attempts===1){await pending;return {passed:false,reason:'Synthetic custody rejection'};}return {passed:true};}return prior(u,req);};
 await page.goto('/intake/');await expect(page.locator('#boundary')).toContainText('enabled');await page.locator('#testCustody').click();await expect(page.locator('#testCustody')).toBeDisabled();
 await page.locator('#testCustody').evaluate(button=>button.dispatchEvent(new MouseEvent('click',{bubbles:true})));expect(attempts).toBe(1);
 release();await expect(page.locator('#transferMessage')).toContainText('Synthetic custody rejection');await expect(page.locator('#testCustody')).toBeEnabled();await page.locator('#testCustody').click();await expect(page.locator('#transferMessage')).toContainText('Synthetic custody passed');expect(attempts).toBe(2);
});
