const {test,expect}=require('./fixtures.cjs');
const {pipeline}=require('./pipeline-fixture.cjs');
async function open(page,h){
 pipeline(h);h.receipts=[
 {export_id:'ts-new',state:'stored',imported_at_utc:'2026-01-08T12:00:00Z',custody:{symbol:'NQ',bar_kind:'seconds',bar_size:30,rows:100,first_timestamp:'2026-01-07T08:00:00',last_timestamp:'2026-01-07T16:00:00'}},
 {export_id:'ts-old',state:'stored',imported_at_utc:'2026-01-06T12:00:00Z',custody:{symbol:'ES',bar_kind:'minutes',bar_size:5,rows:100,first_timestamp:'2026-01-05T08:00:00',last_timestamp:'2026-01-05T16:00:00',primary_report:{strategy_id:'toy'}}}];
 await page.goto('/research/');await expect(page.locator('#catalogCount')).toContainText('1 loaded');await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(3);
}
test('current source route sorts import dates and applies bar filters',async({page,harness})=>{
 await open(page,harness);const rows=page.locator('#receivedDeliveries>.library-source-card'),form=page.locator('#sourceLibraryFilters');
 await expect(rows.first()).toHaveAttribute('data-source-id','ts-new');await form.getByLabel('Sort',{exact:true}).selectOption('import_oldest');await form.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(rows.first()).toHaveAttribute('data-source-id','ts-old');
 await form.getByLabel('Bar type',{exact:true}).selectOption('seconds');await form.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(rows).toHaveCount(1);await expect(rows.first()).toHaveAttribute('data-source-id','ts-new');
});
test('current source route filters assets, source contents and imported dates',async({page,harness})=>{
 await open(page,harness);await page.locator('#sourceAdvancedFilters').evaluate(el=>el.open=true);const form=page.locator('#sourceLibraryFilters');
 await page.getByRole('checkbox',{name:'Asset NQ',exact:true}).uncheck();await form.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#delivery-ts-new')).toHaveCount(0);
 await page.getByRole('checkbox',{name:'TS bars',exact:true}).uncheck();await form.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(1);await expect(page.locator('#delivery-ts-old')).toBeVisible();
 await page.getByLabel('Imported from',{exact:true}).fill('2026-01-07');await form.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#receivedDeliveries>.library-source-card')).toHaveCount(0);await expect(page.locator('#receivedDeliveries')).toContainText('No matching sources');
});
test('hash navigation does not recreate a separate primary inventory link',async({page,harness})=>{
 await open(page,harness);await expect(page.locator('#importedPrimaryNavigation')).toHaveCount(0);
 await page.evaluate(()=>location.hash='primarySources');await expect(page.getByLabel('Status / contents')).toHaveValue('primary');await expect(page.locator('#importedPrimaryNavigation')).toHaveCount(0);
 await page.evaluate(()=>location.hash='receivedSources');await expect(page.getByLabel('Status / contents')).toHaveValue('all');await expect(page.locator('#importedPrimaryNavigation')).toHaveCount(0);
});
