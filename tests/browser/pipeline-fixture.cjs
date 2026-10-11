const names=['parkinson_vol_5','parkinson_vol_15','parkinson_vol_30','ofi_5','ofi_15','ofi_30','volume_percentile','volume_momentum','amihud_illiquidity','vwap_distance','minutes_since_open','is_first_last_30min','day_of_week'];
function artifact(type,id,parents=[]){return {type,id,parent_ids:parents,usable:true,status:'pass',rows:300,label_contracts:[],input_mode:'tradestation',job_id:'saved-'+id,report:null};}
function pipeline(h,{empty=false,ticks=false}={}){
 const source={id:'synthetic-dataset',symbol:'SYNTHETIC-ES',source_kind:ticks?'tick_tape':'source_bars',bar_kind:ticks?'ticks':'minutes',bar_size:ticks?1:5,synthetic:true,accepted:true,validation_status:'pass',capabilities:Object.fromEntries(['bar_building','vp_features','primary_research','bar_features','training'].map(key=>[key,{enabled:true,reason:'Synthetic permission'}])),rows:500,start_session:'2026-01-05',end_session:'2026-01-05',last_event:'2026-01-05T22:00:00Z'};
 const artifacts=empty?[]:[artifact('training_source','native-source'),artifact('primary_labels','targets',['native-source']),artifact('training_dataset','training',['targets']),artifact('model','model',['training']),artifact('predictions','scores',['model']),artifact('bars','bars'),artifact('candidates','candidates',['bars']),artifact('event_labels','events',['candidates'])];
 const progress={release_id:h.release,selected:source,datasets:[source],artifacts,stages:[{key:'source',group:'primary',title:'Source',status:'ready',reason:'Synthetic accepted source'},{key:'ml_replay',group:'ml',title:'Replay',status:'ready',reason:'Synthetic capability'}],jobs:[],page_size:20,total_datasets:1,generated_at:'2026-01-05T22:00:00Z',history_limit:24,experiment_operations:['reserve_experiment','freeze_experiment','experiment_status','evaluate_final'],comparison_statistics_supported:true};
 const experiment={experiment_id:'demo-final',state:'reserved',binding:{dataset_id:source.id},holdout_start_ns:Date.parse('2026-02-01T00:00:00Z')*1e6,holdout_end_ns:Date.parse('2026-02-02T00:00:00Z')*1e6,freeze_hash:null,final_evaluation_available:false};
 const outputs={build_primary_labels:['primary_labels','new-targets',['native-source']],build_training_dataset:['training_dataset','new-training',['new-targets']],build_event_labels:['event_labels','new-events',['candidates']],build_event_meta_dataset:['training_dataset','new-training',['events']],generate_candidates:['candidates','new-candidates',['bars']],train_model:['model','new-model',['training']],score_model:['predictions','new-scores',['model']],ml_gated_replay:['ml_replay','new-replay',['scores']]};
 h.result=(job,id)=>{
  const operation=job?.operation;const result={usable:true,execution_status:'published',job_id:id,metrics:{},artifact_ids:[],counts:{samples:300},reports:['summary.html']};
  if(!job&&id?.startsWith('saved-'))return {...result,artifact_ids:[id.slice(6)],counts:{bar_counts:{time_30:500},candidate_counts:{time_30:40}}};
  if(operation==='research_progress')result.metrics.progress=progress;
  else if(operation==='data_catalog')result.metrics.catalog={datasets:[source],has_more:false,total:1,offset:0,page_size:20};
  else if(operation==='build_bars'){result.artifact_ids=['bars'];result.counts={bar_counts:{time_30:500}};}
  else if(['backtest_preset','backtest_sweep'].includes(operation)){result.artifact_ids=['replay'];result.reports=['backtest.html'];}
  else if(operation==='feature_inventory')result.metrics.feature_inventory={features:[...names.map(name=>({name,label:name,family:'MA13 bars',implemented:true,allowed:true,reason:'Synthetic compatible bars'})),{name:'vp_poc',label:'VP POC',family:'Volume profile',implemented:true,allowed:false,reason:'Requires ticks'}]};
  else if(operation==='analyze_features'){result.artifact_ids=['analysis'];result.counts={training_prefix_samples:120,features:job.payload.feature_names.length,constant_features:1};}
  else if(operation==='review_features')result.artifact_ids=['feature-review'];
  else if(outputs[operation]){const [type,key,defaults]=outputs[operation];const parents=operation==='train_model'?[job.payload.training_dataset_id]:operation==='score_model'?[job.payload.model_artifact_id]:operation==='ml_gated_replay'?[job.payload.predictions_artifact_id]:defaults;if(!artifacts.some(a=>a.id===key))artifacts.push(artifact(type,key,parents));result.artifact_ids=[key];result.reports=[operation==='train_model'?'model_training.html':'summary.html'];}
  else if(operation==='reserve_experiment'){experiment.experiment_id=job.payload.experiment_id;result.metrics.experiment=experiment;}
  else if(operation==='freeze_experiment'){Object.assign(experiment,{state:'frozen',freeze_hash:'f'.repeat(64),final_evaluation_available:true});result.metrics.experiment=experiment;}
  else if(operation==='experiment_status')result.metrics.experiment=experiment;
  else if(operation==='evaluate_final'){Object.assign(experiment,{state:'evaluated',final_evaluation_available:false,evaluation_job_id:id,result:{result_id:'final-result'}});result.artifact_ids=['final-result'];}
  else if(operation==='statistics_report')result.artifact_ids=['statistics'];
  else return undefined;
  return result;
 };
 return {progress,experiment,names};
}
async function openPipeline(page,hash='trainingStage'){await page.goto('/research/pipeline/#'+hash);await page.locator('#featureInventoryOptions input').first().waitFor({state:'attached'});await page.locator('#'+hash+' details').evaluateAll(rows=>rows.forEach(row=>row.open=true));}
async function openDetails(page,id){await page.locator('#'+id).evaluate(el=>el.open=true);}
async function request(h,expect,operation){await expect.poll(()=>h.requests.filter(r=>r.operation===operation).length).toBeGreaterThan(0);return h.requests.filter(r=>r.operation===operation).at(-1).payload;}
module.exports={pipeline,openPipeline,openDetails,request};
