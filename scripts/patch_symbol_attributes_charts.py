"""Use precise chart/helper edits; preserve older report rendering contracts."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]/'.artifacts/GNET-SymbolAttributes-v46-r1'
BROKER=ROOT/'guarded-v46-symbol-attributes'
CLIENT=ROOT/'gnet-client-v79-symbol-attributes'


def patch(path,changes):
    text=path.read_text(encoding='utf-8')
    for old,new in changes:
        if text.count(old)!=1:raise RuntimeError('Chart anchor differs: '+old[:90])
        text=text.replace(old,new)
    path.write_text(text,encoding='utf-8')


def main():
    path=CLIENT/'gnet_broker/scrolling_bar_viewer.js'
    patch(path,[
        ('function cashMarkers(points,zone,seconds,displaySeconds=seconds){if(!(seconds>0&&seconds<3600))return [];',
         'function cashMarkers(points,zone,seconds,displaySeconds=seconds,reference){if(!(seconds>0&&seconds<3600)||reference===null)return [];'),
        ("    const epochs=points.map(p=>epoch(p.stamp,zone)),ny=formatter('America/New_York'),days=new Set(epochs.filter(Number.isFinite).map(t=>ny.format(new Date(t)).slice(0,10))),markers=[];\n    for(const day of days){const weekday=new Date(day+'T12:00:00Z').getUTCDay();if(weekday===0||weekday===6)continue;\n      for(const [label,time]of [['OPEN','09:30:00'],['CLOSE','16:00:00']]){const target=epoch(day+'T'+time,'America/New_York');let index=null;",
         "    const epochs=points.map(p=>epoch(p.stamp,zone)),referenceZone=reference?.timezone||'America/New_York',markers=[],targets=[];\n    let clock;try{clock=formatter(referenceZone)}catch{return []}\n    const days=new Set(epochs.filter(Number.isFinite).map(t=>clock.format(new Date(t)).slice(0,10)));\n    if(reference?.sessions){for(const session of reference.sessions){let windows=session.windows;if(!windows){let opened=session.session;if(session.open>session.close)opened=new Date(Date.parse(opened+'T12:00:00Z')-86400000).toISOString().slice(0,10);windows=[{open:opened+'T'+session.open,close:session.session+'T'+session.close}]}for(const window of windows){targets.push(['OPEN',window.open],['CLOSE',window.close])}}}\n    else for(const day of days){const weekday=new Date(day+'T12:00:00Z').getUTCDay();if(weekday===0||weekday===6)continue;targets.push(['OPEN',day+'T'+(reference?.open||'09:30:00')],['CLOSE',day+'T'+(reference?.close||'16:00:00')])}\n    for(const [label,stamp] of targets){const day=stamp.slice(0,10),time=stamp.slice(11,19),target=epoch(stamp,referenceZone);if(!Number.isFinite(target))continue;let index=null;"),
        ("        if(index!==null)markers.push({label,time:time.slice(0,5),day,index});}}",
         "        if(index!==null)markers.push({label,time:time.slice(0,5),day,index,timezone:referenceZone,zoneLabel:referenceZone==='America/New_York'?'NY':referenceZone});}"),
        ("  const cashMarkers=GNETBarAxis.cashMarkers(points,chartClock,axisProfile.seconds,axisProfile.seconds*(engine?view.aggregation_factor||1:1));",
         "  const sessionReference=source.session_reference;\n  const cashMarkers=GNETBarAxis.cashMarkers(points,chartClock,axisProfile.seconds,axisProfile.seconds*(engine?view.aggregation_factor||1:1),sessionReference);"),
        ("'data-timezone':'America/New_York'", "'data-timezone':marker.timezone"),
        ("marker.label+' '+marker.time+' NY'", "marker.label+' '+marker.time+' '+marker.zoneLabel"),
        ("  const controls = document.createElement('div'); controls.style.cssText", "  if(source.symbol_attributes){const a=source.symbol_attributes,metadata=document.createElement('p');metadata.setAttribute('data-role','instrument-metadata');metadata.textContent='Country: '+(a.country_raw||'unresolved')+' · Exchange: '+(a.exchange_raw||'unresolved')+' · Type: '+(a.symbol_type||'unresolved')+' · Point value: '+a.point_value+' · Lookup: '+a.status;shell.append(metadata)}\n  const controls = document.createElement('div'); controls.style.cssText"),
        ("legend.textContent='U.S. cash-session reference: yellow OPEN 09:30 · purple CLOSE 16:00, New York time (DST applied). These fixed reference times do not apply holiday or early-close schedules.';",
         "legend.textContent=sessionReference===null?'Session markers unavailable: no matched exchange or reviewed session calendar.':sessionReference?(sessionReference.label+' · '+sessionReference.timezone+' · yellow OPEN / purple CLOSE. '+(sessionReference.basis==='reviewed_calendar'?'Dated calendar hours include recorded early closes and session breaks.':'Reference hours only; holiday and early-close schedules require a dated calendar.')):'U.S. cash-session reference: yellow OPEN 09:30 · purple CLOSE 16:00, New York time (DST applied). These fixed reference times do not apply holiday or early-close schedules.';"),
    ])
    shutil.copyfile(path,BROKER/'gnet_broker/scrolling_bar_viewer.js')
    review=CLIENT/'gnet_broker/ts_review.html'
    patch(review,[
        ("const meta=source.source_metadata||{},primary=", "const meta=source.source_metadata||{},attributes=source.symbol_attributes||meta.symbol_attributes||{},primary="),
        ("['Exchange',source.exchange],['Country',source.country],['Exchange timezone',source.exchange_timezone],",
         "['Exchange',source.exchange||attributes.exchange_raw],['Country',source.country||attributes.country_raw],['Exchange timezone',source.exchange_timezone],['Security type',attributes.symbol_type],['Point value',attributes.point_value],['Chart point value',attributes.chart_big_point_value],['Provider price grid',attributes.min_move===undefined?undefined:attributes.min_move+' / '+attributes.price_scale],['Symbol lookup',attributes.status],['Metadata captured at',attributes.captured_at_local],"),
    ])
    inventory=CLIENT/'gnet_broker/delivery_inventory.js'
    patch(inventory,[("pair(meta,'Export ID',item.id);", "const attributes=item.receipt?.custody?.source_metadata?.symbol_attributes;if(attributes){pair(meta,'Country',attributes.country_raw||'unresolved');pair(meta,'Exchange',attributes.exchange_raw||'unresolved');pair(meta,'Security type',attributes.symbol_type||'unresolved');pair(meta,'Point value',String(attributes.point_value));pair(meta,'Symbol lookup',attributes.status)}pair(meta,'Export ID',item.id);")])
    for name in ('scripts/guarded_export_metadata.py','gnet_broker/symbol_attributes.py'):
        shutil.copyfile(BROKER/name,CLIENT/name)
    print('Chart reference policy and metadata presentation patched.')


if __name__=='__main__':
    main()
