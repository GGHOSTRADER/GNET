const fs=require('node:fs'),path=require('node:path');
const {summarize,budgets}=require('./performance-profile.cjs');
class PerformanceReporter{
 constructor(){this.tests=[];}
 onTestEnd(test,result){for(const attachment of result.attachments.filter(a=>a.name==='data-fetch-performance')){try{const value=JSON.parse(attachment.body?attachment.body.toString():fs.readFileSync(attachment.path,'utf8'));const readiness=result.attachments.filter(a=>a.name==='screen-readiness').map(a=>JSON.parse(a.body?a.body.toString():fs.readFileSync(a.path,'utf8')));this.tests.push({test:test.titlePath().join(' / '),status:result.status,readiness,...value});}catch(error){this.tests.push({test:test.title,error:error.message});}}}
 onEnd(){const output=path.resolve(__dirname,'../../.test_artifacts/browser/performance.json');fs.mkdirSync(path.dirname(output),{recursive:true});const requests=this.tests.flatMap(t=>t.requests||[]);fs.writeFileSync(output,JSON.stringify({mode:'fabricated-api-browser-regression',generatedAt:new Date().toISOString(),budgets,tests:this.tests,summary:summarize(requests)},null,2));}
}
module.exports=PerformanceReporter;
