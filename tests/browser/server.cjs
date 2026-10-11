// Serve real packaged HTML/assets only. This server has no broker connection.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const base=path.resolve(__dirname,'../..');
const config=JSON.parse(fs.readFileSync(path.join(base,'.artifacts/client-delivery-installed/client-config.json'),'utf8'));
const root=path.resolve(process.env.GNET_BROWSER_PACKAGE||config.package_root);
console.log('Testing UI package: '+root);
const evidence=path.join(base,'.test_artifacts/browser');fs.mkdirSync(evidence,{recursive:true});
const crypto=require('node:crypto');
fs.writeFileSync(path.join(evidence,'tested-package.json'),JSON.stringify({package_root:root,client_release_id:JSON.parse(fs.readFileSync(path.join(root,'client-release.json'),'utf8')).client_release_id,manifest_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'client-release.json'))).digest('hex'),synthetic_api:true,broker_jobs_submitted:false,real_data_used:false},null,2));
const pages={'/reviews/':'ts_review.html','/research/':'data_preparation.html','/research/pipeline/':'research_workspace.html',
 '/intake/':'client_inbox.html','/help/':'client_help.html','/imported-primaries/':'imported_primary_inventory.html','/dataset-chart/':'dataset_chart_page.html','/ts-trades/':'ts_primary_launch.html'};
http.createServer((req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1');
 if(url.pathname==='/health'){res.end('synthetic browser harness');return;}
 let name=pages[url.pathname];
 if(url.pathname.startsWith('/research/assets/')){
  name=path.basename(url.pathname).replaceAll('-','_');
  if(name==='lightweight_charts.js')name='lightweight_charts.js';
 }
 if(!name){res.writeHead(404);res.end('No route in synthetic harness');return;}
 const file=path.join(root,'gnet_broker',name);
 if(!fs.existsSync(file)){res.writeHead(404);res.end('Packaged asset missing: '+name);return;}
 res.setHeader('Content-Type',(name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html')+'; charset=utf-8');
 res.end(fs.readFileSync(file));
}).listen(9089,'127.0.0.1');
