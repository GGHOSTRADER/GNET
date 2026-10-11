const {performance}=require('node:perf_hooks');
const budgets={apiMs:2000,screenMs:1500,warmInventoryMs:750};
function percentile(values,p){const sorted=[...values].sort((a,b)=>a-b);return sorted.length?sorted[Math.max(0,Math.ceil(sorted.length*p)-1)]:null;}
function summarize(rows){const groups=new Map();for(const row of rows){const key=[row.screen,row.endpoint,row.operation||''].join(' | ');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row.durationMs);}return [...groups].map(([key,values])=>({key,count:values.length,p50Ms:percentile(values,.5),p95Ms:percentile(values,.95),maxMs:Math.max(...values)}));}
function violations(rows,budget=budgets.apiMs){return rows.filter(r=>r.endpoint.startsWith('/api/')&&!r.failed&&r.durationMs>budget);}
function track(page){
 const rows=[],jobs=[],starts=new Map(),operations=new Map(),submitted=new Map(),pending=[];
 const start=req=>{const url=new URL(req.url());if(url.origin==='http://127.0.0.1:9089')starts.set(req,{started:performance.now(),screen:new URL(page.url()==='about:blank'?req.url():page.url()).pathname,endpoint:url.pathname,method:req.method()});};
 const finish=(req,failed=false)=>{const record=starts.get(req);if(!record)return;starts.delete(req);const url=new URL(req.url()),began=record.started;record.durationMs=performance.now()-record.started;record.failed=failed;delete record.started;
  const body=req.method()==='POST'&&record.endpoint==='/api/jobs'?req.postDataJSON():null;
  record.operation=body?.operation||operations.get(url.searchParams.get('job_id'))||null;
  rows.push(record);
  if(body)pending.push((async()=>{try{const response=await req.response();const value=await response.json();operations.set(value.job_id,body.operation);submitted.set(value.job_id,{started:began,operation:body.operation,screen:record.screen});}catch{}})());
  if(record.endpoint==='/api/result'&&submitted.has(url.searchParams.get('job_id'))){const job=submitted.get(url.searchParams.get('job_id'));jobs.push({operation:job.operation,screen:job.screen,durationMs:performance.now()-job.started});submitted.delete(url.searchParams.get('job_id'));}
 };
 const complete=req=>finish(req),failed=req=>finish(req,true);
 page.on('request',start);page.on('requestfinished',complete);page.on('requestfailed',failed);
 return {rows,async stop(){page.off('request',start);page.off('requestfinished',complete);page.off('requestfailed',failed);await Promise.all(pending);return {mode:'fabricated-api-browser-regression',budgets,requests:rows,jobs,summary:summarize(rows),unfinishedRequests:starts.size};}};
}
module.exports={budgets,percentile,summarize,violations,track};
