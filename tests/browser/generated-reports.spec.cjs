const fs=require('node:fs'),path=require('node:path');
const {test,expect}=require('./fixtures.cjs');
const root=path.resolve(__dirname,'../../.test_artifacts/generated-chart-fixtures');
function html(type,offset){
 const file=path.join(root,`${type}-${offset}.html`);
 // Match the installed view_server's report asset injection exactly.
 return fs.readFileSync(file,'utf8').replace('</body>','<script src="/research/assets/lightweight-charts.js"></script><script src="/research/assets/scrolling-bar-viewer.js"></script></body>');
}
for(const type of ['dataset','native','engine'])for(const width of [1440,390]){
 test(`generated ${type} report renders at ${width}px`,async({page,harness},info)=>{
  await page.setViewportSize({width,height:1000});
  await page.route('**/reports/**',route=>route.fulfill({contentType:'text/html',body:html(type,0)}));
  await page.goto('/reports/generated/'+type+'.html');
  const chart=page.locator('#scrolling-bar-viewer');await expect(chart).toBeVisible();
  await expect(chart).toContainText('500 loaded bars');
  const backgrounds=await chart.locator('svg').evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).backgroundColor));
  expect(backgrounds.every(color=>color==='rgba(0, 0, 0, 0)')).toBe(true);
  if(type!=='dataset')await expect(chart.locator('[data-role=trade-duration]')).toHaveCount(1);
  await info.attach(`${type}-${width}`,{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
  await expect(chart).toHaveScreenshot(`${type}-${width}.png`);
  const range=()=>chart.evaluate(node=>node.gnetChart.chart.timeScale().getVisibleLogicalRange());
  await chart.getByRole('button',{name:'Zoom in',exact:true}).click();
  await expect.poll(async()=>{const r=await range();return Math.abs((r.to-r.from)-250)}).toBeLessThan(2);
  await chart.getByRole('slider',{name:'Scroll through loaded bars'}).fill('40');
  await expect.poll(async()=>Math.abs((await range()).from-39.5)).toBeLessThan(1);
  await chart.getByRole('button',{name:'Show loaded window',exact:true}).click();
  await expect.poll(async()=>{const r=await range();return Math.abs((r.to-r.from)-500)}).toBeLessThan(2);
  const before=await chart.screenshot();
  const mode=type==='dataset'?chart.getByRole('combobox',{name:'Price chart mode'}):page.locator('#mode');
  await mode.selectOption('line');
  await expect.poll(async()=>!(await chart.screenshot()).equals(before)).toBe(true);
 });
}
for(const type of ['dataset','native'])test(`generated ${type} reports navigate 500/500/200 bars and back`,async({page,harness})=>{
 let offset=0;
 harness.result=(job)=>{
  if(job.operation==='dataset_view')offset=job.payload.offset;
  else if(job.operation==='ts_primary_trade_view')offset=job.payload.chart_offset;
  else return undefined;
  return {usable:true,reports:[type==='dataset'?'dataset_chart.html':'native_trades.html'],metrics:{},artifact_ids:[]};
 };
 await page.route('**/reports/**',route=>route.fulfill({contentType:'text/html',body:html(type,offset)}));
 await page.goto('/reports/generated/chart.html');
 const chart=page.locator('#scrolling-bar-viewer');await expect(chart).toContainText('500 loaded bars');
 const next=()=>page.getByRole('button',{name:type==='dataset'?'Next source window':'Later bars →',exact:true});
 const previous=()=>page.getByRole('button',{name:type==='dataset'?'Previous source window':'← Earlier bars',exact:true});
 await expect(previous()).toBeDisabled();await next().click();
 await expect.poll(()=>offset).toBe(500);await expect(chart).toContainText('500 loaded bars');
 await next().click();await expect.poll(()=>offset).toBe(1000);await expect(chart).toContainText('200 loaded bars');
 await expect(next()).toBeDisabled();await previous().click();await expect.poll(()=>offset).toBe(500);
 await expect(chart).toContainText('500 loaded bars');
 const payloads=harness.requests.map(r=>r.payload);
 expect(payloads.map(p=>p.offset??p.chart_offset)).toEqual([500,1000,500]);
 expect(payloads.every(p=>p.export_id==='generated-synthetic'&&p.max_points===500)).toBe(true);
});
