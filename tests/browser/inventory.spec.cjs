const {test,expect}=require('./fixtures.cjs');
// Legacy bookmark compatibility only; main-route behavior is covered by
// unified-inventory.spec.cjs and inventory-current-route.spec.cjs.
function receipt(n,symbol,kind='minutes'){
 return {export_id:'ts-synthetic-'+n,state:'stored',imported_at_utc:`2026-01-${String(n+5).padStart(2,'0')}T12:00:00Z`,
 custody:{symbol,bar_kind:kind,bar_size:kind==='minutes'?5:30,first_timestamp:'2026-01-05T08:00:00',last_timestamp:'2026-01-05T16:00:00',primary_report:{strategy_id:'toy-'+n,closed_trades:n,open_trades:0,trade_contract_passed:true}}};
}
async function inventory(page,h){h.receipts=[receipt(1,'ES'),receipt(2,'NQ','seconds'),receipt(3,'ES')];await page.goto('/imported-primaries/');await expect(page.locator('#entries>details')).toHaveCount(3);}
test('primary inventory is numbered, collapsed and has date/interval labels',async({page,harness})=>{
 await inventory(page,harness);const rows=page.locator('#entries>details');
 await expect(rows.first().locator(':scope>summary')).toContainText('1.');
 await expect(rows.first().locator(':scope>summary')).toContainText('Imported on:');
 await expect(rows.first().locator(':scope>summary')).toContainText('Data:');
 expect(await rows.first().getAttribute('open')).toBeNull();await rows.first().locator(':scope>summary').click();
 await expect(rows.first().getByRole('link',{name:'Review / register source'})).toHaveAttribute('href','/reviews/?export_id=ts-synthetic-3');
});
test('sorting and filtering change actual rows, refresh retrieves new inventory',async({page,harness})=>{
 await inventory(page,harness);await page.locator('#sort').selectOption('import_oldest');await page.getByRole('button',{name:'Apply filters',exact:true}).click();
 await expect(page.locator('#entries>details').first().locator(':scope>summary')).toContainText('toy-1');
 await page.locator('#kind').selectOption('seconds');await page.getByRole('button',{name:'Apply filters',exact:true}).click();
 await expect(page.locator('#entries>details')).toHaveCount(1);await expect(page.locator('#entries')).toContainText('NQ');
 await page.locator('#kind').selectOption('');harness.receipts.push(receipt(4,'YM'));await page.locator('#refresh').click();
 await expect(page.locator('#entries>details')).toHaveCount(4);
});
test('date filters exclude sources and invalid date ranges explain the problem',async({page,harness})=>{
 await inventory(page,harness);await page.locator('#importStart').fill('2026-01-08');await page.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#entries>details')).toHaveCount(1);
 await page.locator('#start').fill('2026-01-08');await page.locator('#end').fill('2026-01-01');await page.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#status')).toContainText('Date ranges must run from earlier to later');
});
test('asset checkboxes exclude unselected assets',async({page,harness})=>{
 await inventory(page,harness);await page.getByRole('checkbox',{name:'Asset NQ',exact:true}).uncheck();await page.getByRole('button',{name:'Apply filters',exact:true}).click();await expect(page.locator('#entries>details')).toHaveCount(2);
});
