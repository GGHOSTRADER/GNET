const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
function setup(h){pipeline(h);const original=h.result;h.result=(job,id)=>{const value=original(job,id);if(job?.operation==='data_catalog')value.metrics.catalog.metadata_only=true;return value};h.receipts=[{export_id:'fast-source',state:'stored',custody:{symbol:'SYNTHETIC-ES',bar_kind:'minutes',bar_size:5,rows:500}}];}
async function ready(page){await expect(page.locator('#status')).toHaveText('Inventories refreshed. Source contents remain private.');}
test('warm reload renders saved catalog without scheduling another catalog job',async({page,harness})=>{
 setup(harness);await page.goto('/research/');await ready(page);
 const count=harness.requests.filter(r=>r.operation==='data_catalog').length;
 await page.reload();await expect(page.locator('#status')).toContainText('Saved inventory summary');
 await expect(page.locator('#catalogCount')).toContainText('1 loaded');
 expect(harness.requests.filter(r=>r.operation==='data_catalog')).toHaveLength(count);
 await page.locator('#reload').click();await ready(page);
 expect(harness.requests.filter(r=>r.operation==='data_catalog')).toHaveLength(count+1);
});
test('received rows render even when broker availability is still pending',async({page,harness})=>{
 setup(harness);const original=harness.api;harness.api=async(u,req)=>{if(u.pathname==='/api/status'){const r=harness.requests.find((_,i)=>'job-synthetic-'+(i+1)===u.searchParams.get('job_id'));if(r?.operation==='source_availability')return {state:'running'};}return original?.(u,req)};
 await page.goto('/research/');await expect(page.locator('#delivery-fast-source')).toBeVisible();await ready(page);
});
test('expired summary remains visible during failed background refresh',async({page,harness})=>{
 setup(harness);await page.goto('/research/');await ready(page);
 await page.evaluate(()=>{for(const key of Object.keys(localStorage))if(key.startsWith('gnet-inventory:')){const value=JSON.parse(localStorage.getItem(key));value.saved=Date.now()-120000;localStorage.setItem(key,JSON.stringify(value));}});
 harness.fail='data_catalog';await page.reload();await expect(page.locator('#status')).toContainText('Saved summary retained; refresh failed');await expect(page.locator('#catalogCount')).toContainText('1 loaded');
});
test('broker release change never reuses previous release summaries',async({page,harness})=>{
 setup(harness);await page.goto('/research/');await ready(page);harness.release='guarded-synthetic-next';
 await page.reload();await ready(page);expect(harness.requests.filter(r=>r.operation==='data_catalog')).toHaveLength(2);
});
test('unavailable browser storage falls back to fresh catalog jobs',async({page,harness})=>{
 setup(harness);await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw Error('Storage unavailable')}});
 await page.goto('/research/');await ready(page);await page.reload();await ready(page);expect(harness.requests.filter(r=>r.operation==='data_catalog')).toHaveLength(2);
});
