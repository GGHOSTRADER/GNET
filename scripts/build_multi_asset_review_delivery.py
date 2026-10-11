"""Prepare a matching client and reviewed deployment wrappers; never install."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[1]
PRIOR=BASE/'.artifacts/GNET-ReviewPublication-v44-r1'
ROOT=BASE/'.artifacts/GNET-MultiAssetReview-v45-r1'
BROKER='guarded-v45-multi-asset-review'
CLIENT='gnet-client-v78-multi-asset-review'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')


def replace(text,old,new,count=1):
    if text.count(old)!=count:
        raise RuntimeError('Unexpected delivery anchor: '+old)
    return text.replace(old,new)


def main():
    target=ROOT/CLIENT
    if target.exists():
        raise RuntimeError('Preserve existing matching client')
    shutil.copytree(PRIOR/'gnet-client-v77-selected-source-review-r2',target,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(ROOT/BROKER/'gnet_jobs/contracts.py',target/'gnet_jobs/contracts.py')
    html=target/'gnet_broker/ts_review.html'
    text=html.read_text(encoding='utf-8')
    text=replace(text,"['Symbol',source.symbol],", "['Symbol',source.symbol],['Series type',source.series_type||meta.series_type],['Asset',source.asset],['Exchange',source.exchange],['Country',source.country],['Exchange timezone',source.exchange_timezone],")
    html.write_text(text,encoding='utf-8')
    manifest=target/'client-release.json'
    value=json.loads(manifest.read_text())
    value['client_release_id']=CLIENT
    value['files']={name:sha(target/name) for name in value['files']}
    write(manifest,value)
    sys.path.insert(0,str(target))
    from gnet_jobs.client_deploy import verify_package
    verify_package(target,sha(manifest))
    shutil.copytree(PRIOR/'automation',ROOT/'automation',ignore=shutil.ignore_patterns('__pycache__','Test-GNETBrokerDeploymentExtended.ps1'))
    for name in ('Check-GNETMVPIdle.py','Deploy-ReviewedCommandCenter.ps1','Install-ReviewedCommandCenterClient.ps1'):
        shutil.copyfile(PRIOR/name,ROOT/name)
    audit=ROOT/'automation/guarded_research/Test-GNETBrokerDeployment.ps1'
    audit.write_text(replace(audit.read_text(), '[ValidateRange(1,1000000)]','[ValidateRange(1,5000000)]'),encoding='utf-8')
    finish()


def finish():
    manifest=ROOT/CLIENT/'client-release.json'
    prior_hash=sha(PRIOR/'guarded-v44-review-publication-fix/release.json')
    broker_hash=sha(ROOT/BROKER/'release.json')
    deploy=ROOT/'Deploy-ReviewedCommandCenter.ps1'
    text=deploy.read_text()
    for old,new in (("$gnetRelease='guarded-v44-review-publication-fix'","$gnetRelease='"+BROKER+"'"),
            ("$gnetHash='"+prior_hash+"'","$gnetHash='"+broker_hash+"'"),
            ("$gnetConfig.release_manifest_sha256 -notin @(","$gnetConfig.release_manifest_sha256 -notin @('"+prior_hash+"',"),
            ('-MaximumObjects 1000000','-MaximumObjects 5000000'),
            ("-AllowedPriorRelease @(","-AllowedPriorRelease @('guarded-v44-review-publication-fix',")):
        text=replace(text,old,new)
    deploy.write_text(text,encoding='utf-8')
    installer=ROOT/'Install-ReviewedCommandCenterClient.ps1'
    text=installer.read_text()
    text=replace(text,'gnet-client-v77-selected-source-review-r2',CLIENT,3)
    text=replace(text,'guarded-v44-review-publication-fix',BROKER,2)
    text=replace(text,sha(PRIOR/'gnet-client-v77-selected-source-review-r2/client-release.json'),sha(manifest))
    installer.write_text(text,encoding='utf-8')
    write(ROOT/'delivery-status.json',{'broker_release_id':BROKER,'broker_manifest_sha256':broker_hash,
        'client_release_id':CLIENT,'client_manifest_sha256':sha(manifest),'installed':False,
        'real_market_data_read':False,'limitations':['Non-ES calculation adapters and continuous ownership remain pending']})
    write(ROOT/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1',
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery-manifest.json'}})
    print(json.dumps({'root':str(ROOT),'broker_sha256':broker_hash,'client_sha256':sha(manifest),'installed':False}))


def refresh():
    status=json.loads((ROOT/'delivery-status.json').read_text())
    shutil.copyfile(ROOT/BROKER/'gnet_jobs/contracts.py',ROOT/CLIENT/'gnet_jobs/contracts.py')
    path=ROOT/CLIENT/'client-release.json'
    manifest=json.loads(path.read_text())
    manifest['files']={name:sha(ROOT/CLIENT/name) for name in manifest['files']}
    write(path,manifest)
    broker_hash=sha(ROOT/BROKER/'release.json')
    client_hash=sha(path)
    deploy=ROOT/'Deploy-ReviewedCommandCenter.ps1'
    deploy.write_text(replace(deploy.read_text(),"$gnetHash='"+status['broker_manifest_sha256']+"'","$gnetHash='"+broker_hash+"'"),encoding='utf-8')
    installer=ROOT/'Install-ReviewedCommandCenterClient.ps1'
    installer.write_text(replace(installer.read_text(),status['client_manifest_sha256'],client_hash),encoding='utf-8')
    status.update(broker_manifest_sha256=broker_hash,client_manifest_sha256=client_hash)
    write(ROOT/'delivery-status.json',status)
    write(ROOT/'delivery-manifest.json',{'schema_version':'gnet-reviewed-delivery-1',
        'files':{p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='delivery-manifest.json'}})
    sys.path.insert(0,str(ROOT/CLIENT))
    from gnet_jobs.client_deploy import verify_package
    verify_package(ROOT/CLIENT,client_hash)
    print(json.dumps(status))


if __name__=='__main__':
    if sys.argv[1:]==['--refresh']:
        refresh()
    elif sys.argv[1:]==['--finish-only']:
        finish()
    else:
        main()
