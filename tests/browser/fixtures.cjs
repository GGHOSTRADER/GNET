const {test:base,expect}=require('playwright/test');
const {track,violations}=require('./performance-profile.cjs');
const template={source:{symbol:'SYNTHETIC-ES',interval_kind:'minutes',interval_size:5},coverage:{first_timestamp:'2026-01-05T08:00:00',last_timestamp:'2026-01-05T16:00:00'},
 source_timezone:'America/Chicago',calendar_id:'synthetic-calendar',calendar:{calendar_id:'synthetic-calendar'},
 policy:{synthetic:false,review_basis:'captured_export_snapshot',manifest:{dataset_id:'synthetic-dataset',sources:[]}},
 primary_review:{source_contract:{fill_review_basis:'validated_recorded_ledger',fill_properties_reviewed:false,platform_snapshot_reviewed:false}},
 automatic_validation:{ready:true,checks:{timestamps:{status:'pass',reason:'Fabricated ordered timestamps'},coverage:{status:'pass',reason:'Fabricated complete coverage'},sessions:{status:'pass',reason:'Fabricated complete session'}},counts:{rows_scanned:500,expected_sessions:1,observed_sessions:1,missing_sessions:0,incomplete_sessions:0,off_grid_bars:0}},
 captured_evidence:{checks:[{name:'Synthetic recorded ledger',status:'validated',reason:'Browser fixture only'}],missing_evidence:[]}};
const review={review_id:'review-synthetic',export_id:'ts-synthetic',dataset_id:'synthetic-dataset',primary_review_id:'primary-synthetic',requested_processes:['bar_features','training'],status:'awaiting_activation',proposal_sha256:'a'.repeat(64),policy_active:false};
const test=base.extend({
 performanceProfile:[async({page},use,testInfo)=>{
  const profile=track(page);await use(profile);
  const report=await profile.stop();await testInfo.attach('data-fetch-performance',{body:Buffer.from(JSON.stringify(report)),contentType:'application/json'});
  expect(violations(report.requests),'Local fabricated API responses exceeded the 2000 ms request budget; inspect performance.json').toEqual([]);
 },{auto:true}],
 harness:async({page},use)=>{
  const errors=[],unexpected=[],requests=[],jobs=new Map();let sequence=0;
  const h={requests,errors,unexpected,release:'guarded-synthetic-old',template:structuredClone(template),review:structuredClone(review),fail:null,delay:0,receipts:[],registration:true};
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());
   if(u.origin!=='http://127.0.0.1:9089'){unexpected.push(req.url());return route.abort();}
   if(!u.pathname.startsWith('/api/'))return route.continue();
   const reply=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
   if(h.api){const value=await h.api(u,req);if(value!==undefined)return reply(value);}
   if(u.pathname==='/api/config')return reply({release_id:h.release});
   if(u.pathname==='/api/display-names')return reply({labels:{}});
   if(u.pathname==='/api/transfer-status')return reply({entries:h.receipts,next_offset:null});
   if(u.pathname==='/api/jobs'){
    const body=req.postDataJSON();requests.push(body);
    if(body.release_id!==h.release)return reply({error:'Workspace jobs require the configured reviewed release'},400);
    const id='job-synthetic-'+(++sequence);jobs.set(id,{operation:body.operation,payload:body.payload});return reply({job_id:id});
   }
   const job=jobs.get(u.searchParams.get('job_id'));
   if(u.pathname==='/api/status')return reply({state:'published'});
   if(u.pathname==='/api/result'){
    if(h.delay)await new Promise(r=>setTimeout(r,h.delay));
    if(h.fail===job?.operation)return reply({usable:false,error:{message:'Synthetic worker rejection'},metrics:{}});
    if(h.result){const value=await h.result(job,u.searchParams.get('job_id'));if(value!==undefined)return reply(value);}
    const metrics={};let artifact_ids=[];
    if(job?.operation==='ts_review_template')metrics.review_template=h.template;
    else if(['draft_ts_review','ts_review_status'].includes(job?.operation))metrics.review=h.review;
    else if(job?.operation==='ingest_ts_export')metrics.intake={dataset_registered:h.registration,dataset_id:'synthetic-dataset',pending:['Synthetic missing evidence']};
    else if(job?.operation==='prepare_ts_primary_source')artifact_ids=['synthetic-native-source'];
    else if(job?.operation==='source_availability')metrics.source_availability={sources:job.payload.sources.map(s=>({...s,trashed:false}))};
    else if(job?.operation==='dataset_view')metrics.dataset_view={has_more:job.payload.offset===0,next_offset:500,source:{symbol:'SYNTHETIC',size:5,kind:'minutes',clock:'UTC'}};
    else {unexpected.push('Unhandled operation: '+job?.operation);return reply({usable:false,error:{message:'Unmocked operation'},metrics:{}});}
    return reply({usable:true,metrics,artifact_ids,counts:{displayed_observations:500}});
   }
   unexpected.push(u.pathname);return reply({error:'Unmocked API'},404);
  });
  await use(h);
  expect(errors,'Uncaught browser exceptions').toEqual([]);
  expect(unexpected,'Unexpected network/API access').toEqual([]);
 },
});
async function openReview(page){await page.goto('/reviews/?export_id=ts-synthetic');await expect(page.locator('#validationJobStatus')).toContainText('Validation finished');}
async function approve(page){await page.locator('#realScope').check();await page.locator('#draft').click();await expect(page.locator('#approvalStatus')).toContainText('Approval proposal saved');}
module.exports={test,expect,openReview,approve};
