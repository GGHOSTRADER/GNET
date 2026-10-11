const {test,expect}=require('./fixtures.cjs');
test('native viewer locates an exact older export and submits the shared chart window',async({page,harness})=>{
 const offsets=[];harness.api=u=>{if(u.pathname==='/api/transfer-status'){const offset=Number(u.searchParams.get('offset')||0);offsets.push(offset);return offset===0?{entries:[],next_offset:20}:{entries:[{export_id:'ts-synthetic-old',custody:{symbol:'SYNTHETIC',bar_size:5,bar_kind:'minutes',primary_report:{trade_contract_passed:true,closed_trades:70,open_trades:0,boundary_trades:0,strategy_id:'toy'}}}],next_offset:null};}};
 harness.result=job=>job?.operation==='capabilities'?{execution_status:'published',usable:false,metrics:{operations:{ts_primary_trade_view:'implemented'}}}:job?.operation==='ts_primary_trade_view'?{execution_status:'published',usable:true,reports:['native_trades.html']}:undefined;
 await page.goto('/ts-trades/?export_id=ts-synthetic-old');await expect(page.locator('#view')).toBeEnabled();expect(offsets).toEqual([0,20]);
 await page.locator('#view').click();await expect.poll(()=>harness.requests.filter(r=>r.operation==='ts_primary_trade_view').length).toBe(1);expect(harness.requests.at(-1).payload).toEqual({export_id:'ts-synthetic-old',page_size:20,max_points:500});
});
test('missing native export stays blocked after receipt pages are exhausted',async({page,harness})=>{
 harness.api=u=>u.pathname==='/api/transfer-status'?{entries:[],next_offset:null}:undefined;
 await page.goto('/ts-trades/?export_id=ts-synthetic-missing');await expect(page.locator('#status')).toContainText('No verified primary report');await expect(page.locator('#view')).toBeDisabled();expect(harness.requests).toHaveLength(0);
});
