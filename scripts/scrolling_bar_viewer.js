/* Shared local chart presentation for every published GNET bar viewer. */
const GNETBarAxis=(()=>{
  function profile(source){const kind=String(source.bar_kind||source.kind||'').toLowerCase(),size=Number(source.bar_size??source.size);
    const seconds={seconds:1,second:1,time:1,minutes:60,minute:60,hours:3600,hour:3600}[kind];
    const scale=/^(month|months|monthly)$/.test(kind)?'month':/^(day|days|daily|week|weeks|weekly)$/.test(kind)?'date':'time';
    return {scale,seconds:Number.isFinite(size)&&size>0&&seconds?seconds*size:null};}
  function formatter(zone){return new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});}
  function epoch(stamp,zone){if(/(?:Z|[+-]\d{2}:?\d{2})$/.test(stamp))return Date.parse(stamp);
    const values=stamp.slice(0,19).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})$/);if(!values)return null;
    try{const format=formatter(zone),target=Date.UTC(...[Number(values[1]),Number(values[2])-1,...values.slice(3).map(Number)]);let guess=target;
      for(let i=0;i<3;i++){const parts=Object.fromEntries(format.formatToParts(new Date(guess)).filter(p=>p.type!=='literal').map(p=>[p.type,Number(p.value)]));
        guess+=target-Date.UTC(parts.year,parts.month-1,parts.day,parts.hour,parts.minute,parts.second);}
      return format.format(new Date(guess)).replace(' ','T')===stamp.slice(0,19).replace(' ','T')?guess:null;
    }catch{return null;}}
  function cashMarkers(points,zone,seconds,displaySeconds=seconds){if(!(seconds>0&&seconds<3600))return [];
    const epochs=points.map(p=>epoch(p.stamp,zone)),ny=formatter('America/New_York'),days=new Set(epochs.filter(Number.isFinite).map(t=>ny.format(new Date(t)).slice(0,10))),markers=[];
    for(const day of days){const weekday=new Date(day+'T12:00:00Z').getUTCDay();if(weekday===0||weekday===6)continue;
      for(const [label,time]of [['OPEN','09:30:00'],['CLOSE','16:00:00']]){const target=epoch(day+'T'+time,'America/New_York');let index=null;
        for(let i=0;i<epochs.length;i++){const current=epochs[i];if(!Number.isFinite(current))continue;if(current===target){index=i;break;}
          const previous=epochs[i-1];if(i>0&&Number.isFinite(previous)&&previous<target&&target<current&&current-previous<=displaySeconds*1500){index=i-1+(target-previous)/(current-previous);break;}}
        if(index!==null)markers.push({label,time:time.slice(0,5),day,index});}}
    return markers;}
  return {profile,epoch,cashMarkers};
})();
(() => {
  'use strict';
  let points, native = false, engine = false, oldChart, mode;
  if (typeof data !== 'undefined' && Array.isArray(data.chart)) {
    native = true; points = data.chart; oldChart = document.getElementById('chart');
  } else if (typeof DATA !== 'undefined' && DATA.view) {
    points = DATA.view.points; oldChart = document.getElementById('dataChart') || document.getElementById('priceChart');
  } else if (typeof view !== 'undefined' && Array.isArray(view.candles)) {
    const clock=new Intl.DateTimeFormat('sv-SE',{timeZone:data.timezone||'UTC',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
    engine = true; points = view.candles.map((b, i) => ({...b, row: i + 1,
      stamp: clock.format(new Date(b.end_ns / 1e6))})); oldChart = document.getElementById('chart');
  } else return;
  if (!oldChart || !window.LightweightCharts) return;
  const source=native?data.source:engine?data.bar_definition:DATA.source;
  const axisProfile=GNETBarAxis.profile(source);
  const chartClock=native?data.source.source_timezone:engine?data.timezone:DATA.source.clock;
  const cashMarkers=GNETBarAxis.cashMarkers(points,chartClock,axisProfile.seconds,axisProfile.seconds*(engine?view.aggregation_factor||1:1));
  oldChart.hidden = true; oldChart.style.display = 'none';
  const shell = document.createElement('section'); shell.id = 'scrolling-bar-viewer';
  shell.style.cssText = 'width:100%;min-width:0;color:#d9e6f6;background:#101a2a;padding:12px;box-sizing:border-box';
  if(oldChart.id==='priceChart')oldChart.before(shell);else oldChart.parentElement.before(shell);
  const controls = document.createElement('div'); controls.style.cssText = 'display:flex;gap:12px;flex-wrap:wrap;align-items:center'; shell.append(controls);
  function button(label, action) { const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.onclick = action; controls.append(b); return b; }
  const host = document.createElement('div'); host.style.cssText = 'height:470px;position:relative'; shell.append(host);
  const timeAxis=document.createElementNS('http://www.w3.org/2000/svg','svg');timeAxis.id='bar-time-axis';
  timeAxis.setAttribute('role','img');timeAxis.setAttribute('aria-label','Timeframe-aware labels, calendar changes, cash-session reference times and trade outcomes');
  timeAxis.style.cssText='display:block;width:100%;height:125px;min-width:0';shell.append(timeAxis);
  const status = document.createElement('p'); status.setAttribute('role', 'status'); shell.append(status);
  const slider = document.createElement('input'); slider.type = 'range'; slider.min = '0'; slider.step = '1';
  slider.setAttribute('aria-label', 'Scroll through loaded bars'); slider.style.cssText = 'width:100%;display:block'; shell.append(slider);
  const help = document.createElement('p'); help.textContent = 'Drag to pan · mouse wheel / pinch to zoom · scrollbar moves the visible window. Pan and zoom run locally. Load earlier/later bars to browse beyond the loaded window.'; shell.append(help);
  let times=points.map((p,i)=>i+1),timeIndex=new Map(times.map((t,i)=>[t,i]));
  const stamp = t => points[timeIndex.get(Number(t))]?.stamp || '';
  const chart = LightweightCharts.createChart(host, {autoSize:true, height:470,
    layout:{background:{color:'#101a2a'}, textColor:'#c8daf0'},
    grid:{vertLines:{color:'#263a50'},horzLines:{color:'#263a50'}},
    localization:{timeFormatter:stamp}, timeScale:{rightOffset:0,minBarSpacing:0.1,fixLeftEdge:true,fixRightEdge:true,
      tickMarkFormatter:() => ''},
    handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
    handleScale:{mouseWheel:true,pinch:true,axisPressedMouseMove:true}});
  const candle = chart.addSeries(LightweightCharts.CandlestickSeries, {upColor:'#63c89a',downColor:'#ee7b91',borderVisible:false,wickUpColor:'#63c89a',wickDownColor:'#ee7b91'});
  const line = chart.addSeries(LightweightCharts.LineSeries, {color:'#82ccea',lineWidth:2});
  function setBars(){candle.setData(points.map((p,i)=>({time:times[i],open:p.open,high:p.high,low:p.low,close:p.close,
    ...(p.open===p.close ? {color:'#a7afb9',wickColor:'#a7afb9'} : {})})));
    line.setData(points.map((p,i)=>({time:times[i],value:p.close})));}
  setBars();
  mode = document.getElementById('mode');
  if(!mode){mode=document.createElement('select');mode.setAttribute('aria-label','Price chart mode');
    mode.append(new Option('Candles','candles'),new Option('Price line','line'));
    mode.value=typeof DATA!=='undefined'?DATA.payload.chart_mode||'candles':'candles';controls.prepend(mode);}
  const applyMode = () => {const isLine = mode ? mode.value === 'line' : typeof DATA !== 'undefined' && DATA.payload.chart_mode === 'line';
    candle.applyOptions({visible:!isLine}); line.applyOptions({visible:isLine});};
  if(mode)mode.addEventListener('change',applyMode); applyMode();
  const scale = chart.timeScale();
  function paintTimeAxis(){
    timeAxis.replaceChildren();const r=scale.getVisibleLogicalRange();if(!r||!points.length)return;
    const width=host.clientWidth;timeAxis.setAttribute('viewBox',`0 0 ${width} 125`);
    const make=(tag,attrs,text)=>{const n=document.createElementNS(timeAxis.namespaceURI,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;timeAxis.append(n);return n;};
    const first=Math.max(0,Math.ceil(r.from)),last=Math.min(points.length-1,Math.floor(r.to));
    const left=scale.logicalToCoordinate(Math.max(-.5,r.from)),right=scale.logicalToCoordinate(Math.min(points.length-.5,r.to));
    if(left===null||right===null||last<first)return;
    make('line',{x1:left,x2:right,y1:22,y2:22,stroke:'#405572','data-role':'time-axis'});
    const trades=native?(data.payload.selected_trade_id?[data.selected]:data.page):engine&&document.getElementById('display').value!=='bars'?view.matches:[];
    const index=(t,role)=>native?(t[role+'_row']<points[0].row?-1:t[role+'_row']>points[points.length-1].row?points.length:points.findIndex(p=>p.row===t[role+'_row'])):observationIndex(view.candles,t[role+'_event'],t[role+'_ns']);
    for(const t of trades){if(!t)continue;const entry=index(t,'entry'),exit=t.exit_price===null?points.length:index(t,'exit');
      if(exit<r.from||entry>r.to)continue;
      const color=t.outcome==='winner'?'#63c89a':t.outcome==='loser'?'#ee7b91':t.outcome==='breakeven'?'#a7afb9':'#f1c878';
      const x1=scale.logicalToCoordinate(Math.max(r.from,entry)),x2=scale.logicalToCoordinate(Math.min(r.to,exit));if(x1===null||x2===null)continue;
      const duration=make('line',{x1,x2,y1:22,y2:22,stroke:color,'stroke-width':6,'stroke-dasharray':t.exit_price===null?'6 4':'none','data-role':'trade-duration','data-trade-id':t.trade_id});
      const title=document.createElementNS(timeAxis.namespaceURI,'title');title.textContent=`${t.trade_id} · ${t.outcome} · net P&L ${t.net_pnl??'unresolved'}`;duration.append(title);
      if(entry>=r.from&&entry<=r.to)make('circle',{cx:x1,cy:22,r:6,fill:color,'data-role':'duration-entry','data-trade-id':t.trade_id});
      if(exit>=r.from&&exit<=r.to&&t.exit_price!==null)make('rect',{x:x2-5,y:17,width:10,height:10,fill:color,'data-role':'duration-exit','data-trade-id':t.trade_id});
    }
    const step=Math.max(1,Math.ceil((last-first+1)/Math.max(2,Math.floor(width/85))));
    const showSeconds=points.some(p=>p.stamp.slice(17,19)!=='00');
    for(let i=first;i<=last;i+=step){const x=scale.timeToCoordinate(times[i]);if(x===null)continue;
      make('line',{x1:x,x2:x,y1:32,y2:40,stroke:'#a4b4c9'});
      const label=axisProfile.scale==='month'?['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][Number(points[i].stamp.slice(5,7))-1]:axisProfile.scale==='date'?points[i].stamp.slice(5,10):points[i].stamp.slice(11,showSeconds?19:16);
      make('text',{x:x-3,y:47,transform:`rotate(90 ${x-3} 47)`,fill:'#c8daf0','font-size':11,'data-role':axisProfile.scale==='time'?'vertical-time':'vertical-date'},label);}
    let previousBadge=-Infinity;
    const periodLength=axisProfile.scale==='month'?4:axisProfile.scale==='date'?7:10;
    for(let i=first;i<=last;i++){const day=points[i].stamp.slice(0,periodLength);if(i!==first&&day===points[i-1].stamp.slice(0,periodLength))continue;
      const x=scale.timeToCoordinate(times[i]);if(x===null)continue;
      if(i!==first)make('line',{x1:x,x2:x,y1:32,y2:103,stroke:'#82ccea','stroke-dasharray':'3 3','data-role':axisProfile.scale==='time'?'day-change':'period-change','data-row':points[i].row});
      const center=Math.max(48,Math.min(width-48,x));if(center-previousBadge<95)continue;previousBadge=center;
      make('rect',{x:center-46,y:104,width:92,height:19,rx:4,fill:'#24394e'});
      make('text',{x:center,y:118,'text-anchor':'middle',fill:'#9dd5ff','font-size':11,'data-role':axisProfile.scale==='time'?'day-label':'period-label'},day);
    }
    for(const marker of cashMarkers){if(marker.index<r.from||marker.index>r.to)continue;const x=scale.logicalToCoordinate(marker.index);if(x===null)continue;
      const color=marker.label==='OPEN'?'#ffd166':'#be9dff';
      make('line',{x1:x,x2:x,y1:0,y2:100,stroke:color,'stroke-dasharray':'4 3','data-role':'cash-session-marker','data-boundary':marker.label,'data-reference-time':marker.day+'T'+marker.time,'data-timezone':'America/New_York'});
      make('text',{x:Math.max(60,Math.min(width-60,x)),y:12,'text-anchor':'middle',fill:color,'font-size':11},marker.label+' '+marker.time+' NY');
    }
  }
  scale.subscribeVisibleLogicalRangeChange(()=>requestAnimationFrame(paintTimeAxis));
  new ResizeObserver(()=>requestAnimationFrame(paintTimeAxis)).observe(host);
  if(native||engine){const legend=document.createElement('p');legend.textContent='Trade outcome on the X-axis: green = winner · red = loser · gray = breakeven · amber = unresolved. ● Entry · ■ Exit · line = trade duration.';timeAxis.after(legend);}
  if(axisProfile.seconds>0&&axisProfile.seconds<3600){const legend=document.createElement('p');legend.textContent='U.S. cash-session reference: yellow OPEN 09:30 · purple CLOSE 16:00, New York time (DST applied). These fixed reference times do not apply holiday or early-close schedules.';timeAxis.after(legend);}
  function show(count = points.length, start = 0) {count = Math.max(1,Math.min(points.length,count));
    if(count>=points.length){scale.fitContent();return;}
    start = Math.max(0,Math.min(points.length-count,start)); scale.setVisibleLogicalRange({from:start-.5,to:start+count-.5});}
  button('Show loaded window',()=>show());
  button('Zoom in',()=>{const r=scale.getVisibleLogicalRange();if(r)show(Math.max(5,(r.to-r.from)/2),r.from+(r.to-r.from)/4);});
  button('Zoom out',()=>{const r=scale.getVisibleLogicalRange();if(r)show((r.to-r.from)*2,r.from-(r.to-r.from)/2);});
  scale.subscribeVisibleLogicalRangeChange(r=>{if(!r)return;const count=Math.min(points.length,Math.max(1,Math.ceil(r.to-r.from)));
    slider.max=String(Math.max(0,points.length-count));slider.value=String(Math.max(0,Math.round(r.from+.5)));slider.disabled=count>=points.length;
    const first=points[Math.max(0,Math.floor(r.from+.5))],last=points[Math.min(points.length-1,Math.ceil(r.to-.5))];
    status.textContent = `${points.length} loaded bars · ${count} visible · ${first?.stamp||''} → ${last?.stamp||''}`;});
  slider.oninput=()=>{const r=scale.getVisibleLogicalRange();if(r)show(r.to-r.from,Number(slider.value));};
  chart.subscribeCrosshairMove(p=>{if(!p.time)return;const b=points[timeIndex.get(Number(p.time))];if(b)help.textContent=`${b.stamp} · Open ${b.open} · High ${b.high} · Low ${b.low} · Close ${b.close}`;});
  const markers=[];
  const addMark=(index,label,color,shape,position)=>{if(index>=0&&index<points.length)markers.push({time:index+1,position,color,shape,text:label});};
  if(native){const byRow=new Map(points.map((p,i)=>[p.row,i]));const trades=data.payload.selected_trade_id?[data.selected]:data.page;
    for(const t of trades){if(!t)continue;const c=t.outcome==='winner'?'#63c89a':t.outcome==='loser'?'#ee7b91':'#f1c878';
      addMark(byRow.get(t.signal_row),'Signal '+t.trade_id,'#8ab9ff','circle','aboveBar');
      addMark(byRow.get(t.entry_row),'Entry '+t.trade_id+' @ '+t.entry_price,c,t.side===1?'arrowUp':'arrowDown','belowBar');
      if(t.exit_price!==null)addMark(byRow.get(t.exit_row),'Exit '+t.trade_id+' @ '+t.exit_price,c,'square','aboveBar');}
    const h=document.querySelector('.toolbar h2');if(h)h.textContent='Price chart · scrollable bar window';
    const p={...data.payload,max_points:500};
    const before=button('← Earlier bars',()=>submit({...p,chart_offset:Math.max(0,(data.payload.chart_offset||0)-500)}));before.disabled=!(data.payload.chart_offset>0);
    const after=button('Later bars →',()=>submit({...p,chart_offset:(data.payload.chart_offset||0)+points.length}));after.disabled=!data.chart_has_more;
    button('Browse bars',()=>{const browse={...p,chart_offset:0};delete browse.selected_trade_id;submit(browse);});
  }
  if(engine){for(const t of view.matches){const at=(event,ns)=>observationIndex(view.candles,event,ns);const c=t.outcome==='winner'?'#63c89a':t.outcome==='loser'?'#ee7b91':'#f1c878';
    addMark(at(t.signal_event,t.signal_ns),'Signal '+t.trade_id,'#8ab9ff','circle','aboveBar');
    addMark(at(t.entry_event,t.entry_ns),'Entry '+t.trade_id,c,'arrowUp','belowBar');if(t.exit_ns!==null)addMark(at(t.exit_event,t.exit_ns),'Exit '+t.trade_id,c,'square','aboveBar');}
    document.getElementById('reset-chart').addEventListener('click',()=>show());
    document.getElementById('matches').addEventListener('click',e=>{const row=e.target.closest('[data-trade-id]');const t=row&&view.matches.find(t=>t.trade_id===row.dataset.tradeId);if(!t)return;
      const a=observationIndex(view.candles,t.entry_event,t.entry_ns),b=observationIndex(view.candles,t.exit_event,t.exit_ns??view.end_ns);show(Math.max(20,b-a+11),a-5);});
  }
  markers.sort((a,b)=>a.time-b.time);const markerLayer=LightweightCharts.createSeriesMarkers(candle,markers);
  const lineMarkers=LightweightCharts.createSeriesMarkers(line,markers);
  const overlay=document.createElementNS('http://www.w3.org/2000/svg','svg');overlay.style.cssText='position:absolute;inset:0;pointer-events:none;width:100%;height:100%;z-index:3';host.append(overlay);
  function paintFills(){overlay.replaceChildren();const trades=native?(data.payload.selected_trade_id?[data.selected]:data.page):engine?view.matches:[];
    for(const t of trades){if(!t)continue;const color=t.outcome==='winner'?'#63c89a':t.outcome==='loser'?'#ee7b91':'#f1c878';
      for(const label of ['entry','exit']){const index=native?points.findIndex(b=>b.row===t[label+'_row']):observationIndex(view.candles,t[label+'_event'],t[label+'_ns']);
        const price=t[label+'_price'];if(index<0||index>=points.length||price==null)continue;
        const x=scale.timeToCoordinate(times[index]),y=(mode?.value==='line'?line:candle).priceToCoordinate(price);if(x==null||y==null)continue;
        const dot=document.createElementNS(overlay.namespaceURI,'circle');for(const [k,v]of Object.entries({cx:x,cy:y,r:4,fill:color}))dot.setAttribute(k,v);overlay.append(dot);
      }
    }
  }
  scale.subscribeVisibleLogicalRangeChange(()=>requestAnimationFrame(paintFills));
  new ResizeObserver(()=>requestAnimationFrame(paintFills)).observe(host);
  if(mode)mode.addEventListener('change',()=>requestAnimationFrame(paintFills));
  if(engine){const display=document.getElementById('display'),signals=document.getElementById('signals');
    const update=()=>{const shown=display.value==='bars'?[]:markers.filter(m=>signals.checked||!m.text.startsWith('Signal ')).map(m=>({...m,time:times[m.time-1]}));markerLayer.setMarkers(shown);lineMarkers.setMarkers(shown);overlay.style.display=display.value==='bars'?'none':'';requestAnimationFrame(paintTimeAxis);};
    display.addEventListener('change',update);signals.addEventListener('change',update);update();
    const axis=document.getElementById('axis');axis.addEventListener('change',()=>{let previous=-Infinity;
      times=points.map((p,i)=>{const value=axis.value==='time'?p.end_ns/1e9:i+1;previous=Math.max(value,previous+.0001);return previous;});
      timeIndex=new Map(times.map((t,i)=>[t,i]));setBars();update();show();requestAnimationFrame(paintFills);});
  }
  // Keep the marker object alive for the lifetime of this document.
  shell.gnetChart={chart,markerLayer,lineMarkers};
  if(points.length){show();requestAnimationFrame(()=>requestAnimationFrame(()=>show()));}else status.textContent='No bars in this window.';
})();
