const fs=require('node:fs'),path=require('node:path');
const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
// Exported from the pinned broker's PAYLOADS['data_catalog']; never a permissive mock.
const schema=JSON.parse(fs.readFileSync(path.join(__dirname,'catalog-contract-v43.json'),'utf8'));
for(const [choice,wire] of [['import_recent','recent'],['import_oldest','oldest'],['data_newest','coverage_newest'],['data_oldest','oldest'],['name','name'],['asset','asset']]){
 test('source Apply filters obeys V43 catalog contract: '+choice,async({page,harness})=>{
  pipeline(harness);
  await page.goto('/research/');await expect(page.locator('#catalogCount')).toContainText('1 loaded');
  const form=page.locator('#sourceLibraryFilters');
  await form.getByLabel('Sort',{exact:true}).selectOption(choice);
  await form.getByRole('button',{name:'Apply filters',exact:true}).click();
  await expect.poll(()=>harness.requests.filter(r=>r.operation==='data_catalog').length).toBe(2);
  const payload=harness.requests.filter(r=>r.operation==='data_catalog').at(-1).payload;
  expect(Object.keys(payload).filter(key=>!Object.hasOwn(schema.properties,key))).toEqual([]);
  expect(schema.properties.sort.enum).toContain(payload.sort);
  expect(payload.sort).toBe(wire);
  await expect(page.locator('#status')).toHaveText('Inventories refreshed. Source contents remain private.');
 });
}
