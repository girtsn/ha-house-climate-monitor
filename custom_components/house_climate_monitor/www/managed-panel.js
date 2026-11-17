/* Standalone read-only trend panel with admin source selection.
 * Uses HA Recorder for measurements; diagnostic history is stored locally.
 */
/** Decode HA history/history_during_period object keyed by entity ID. */
export function decodeHistoryResponse(data, ids) {
  const response = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  const output = {};
  for (const id of ids) {
    const states = Array.isArray(response[id]) ? response[id] : [];
    output[id] = states.map(point => {
      const rawTime = point?.lu ?? point?.lc;
      const time = Number.isFinite(Number(rawTime)) ? Number(rawTime) * 1000 :
        Date.parse(point?.last_changed ?? point?.last_updated ?? '');
      const rawValue = point?.s ?? point?.state;
      const value = rawValue === '' || rawValue == null ? NaN : Number(rawValue);
      return [time, value];
    }).filter(([time, value]) => Number.isFinite(time) && Number.isFinite(value));
  }
  return output;
}

const version=new URL(import.meta.url).searchParams.get('v')||'dev';
const TAG='house-climate-monitor-panel-v'+version.replace(/\./g,'-');
const TABS=['Overview','Temperature','Humidity','PM2.5','VOC','CO₂','Emergencies','Incidents','Sensors'];
const METRIC={Temperature:'temperature',Humidity:'humidity','PM2.5':'pm25',VOC:'voc_index','CO₂':'co2',Emergencies:'temperature'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dt=t=>t?new Date(t).toLocaleString(): '—';
const fmt=v=>v===null||v===undefined?'—':Number.isFinite(Number(v))?Number(v).toFixed(1):String(v);
function getRange(mode,anchor=new Date(),offset=0){
 const now=new Date(),e=new Date(anchor),s=new Date(anchor),day=86400000;
 let length=7*day;
 if(mode==='48h')length=2*day;else if(mode==='30d')length=30*day;
 else if(mode==='90d')length=90*day;else if(mode==='365d')length=365*day;
 else if(mode==='3y')length=3*365*day;
 else if(mode==='today'){s.setHours(0,0,0,0);e.setTime(s.getTime()+day);length=day;}
 else if(mode==='yesterday'){s.setHours(0,0,0,0);s.setTime(s.getTime()-day);e.setTime(s.getTime()+day);length=day;}
 else if(mode==='week'){s.setHours(0,0,0,0);s.setDate(s.getDate()-((s.getDay()+6)%7));e.setTime(s.getTime()+7*day);length=7*day;}
 else if(mode==='month'){s.setDate(1);s.setHours(0,0,0,0);e.setFullYear(s.getFullYear(),s.getMonth()+1,1);length=e-s;}
 else if(mode==='year'){s.setMonth(0,1);s.setHours(0,0,0,0);e.setFullYear(s.getFullYear()+1);length=e-s;}
 if(!['today','yesterday','week','month','year'].includes(mode)){e.setTime(anchor.getTime());s.setTime(e.getTime()-length);}
 if(offset){s.setTime(s.getTime()+offset*length);e.setTime(e.getTime()+offset*length);}
 if(e>now)e.setTime(now.getTime());
 if(s>=e)s.setTime(e.getTime()-length);
 return {start:s.toISOString(),end:e.toISOString()};
}
const CSS=`
:host{display:block;color:var(--primary-text-color,#222);background:var(--primary-background-color,#fafafa);min-height:100%;font-family:Roboto,Arial,sans-serif}
*{box-sizing:border-box}button,select,input{font:inherit}button{cursor:pointer;background:var(--card-background-color,#fff);color:inherit;border:1px solid var(--divider-color,#ddd);border-radius:8px;padding:7px 12px}button.active{background:var(--primary-color,#1976d2);color:#fff;border-color:transparent}
button:hover{filter:brightness(.96)}button:disabled{opacity:.5;cursor:not-allowed}.shell{max-width:1480px;margin:auto;padding:20px 18px 60px}
.header,.toolbar,.tabs,.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.header{justify-content:space-between;margin-bottom:15px}.header h1{font-size:24px;margin:0}
.sub{color:var(--secondary-text-color,#666);font-size:13px}.tabs{overflow-x:auto;flex-wrap:nowrap;border-bottom:1px solid var(--divider-color,#ddd);padding-bottom:10px;margin-bottom:16px}.tabs button{white-space:nowrap}
.toolbar{margin-bottom:18px}.toolbar select,.toolbar input{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#ccc);border-radius:8px;color:inherit;padding:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:16px}.card{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#ddd);border-radius:12px;padding:16px;box-shadow:0 1px 3px #0001;min-width:0}
.card h3{margin:0 0 8px;font-size:16px}.metric{font-weight:600;font-size:25px}.chip{border-radius:12px;padding:2px 9px;background:var(--secondary-background-color,#eee);font-size:12px;display:inline-block;margin:2px}
.warn{color:var(--error-color,#c62828)}.ok{color:var(--success-color,#278447)}.list{display:flex;flex-direction:column;gap:8px}.incident{border-left:4px solid var(--error-color,#c62828)}.incident.resolved{border-left-color:var(--success-color,#278447)}
.table-wrap{overflow:auto}.table{width:100%;border-collapse:collapse;font-size:13px}.table th,.table td{padding:8px;border-bottom:1px solid var(--divider-color,#ddd);vertical-align:top;text-align:left}.table th{position:sticky;top:0;background:var(--card-background-color,#fff)}.table td small{display:block;color:var(--secondary-text-color,#666);margin-top:3px}
.graph{height:250px;width:100%;background:var(--card-background-color,#fff)}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;margin-top:8px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.note{margin:12px 0;color:var(--secondary-text-color,#666);font-size:13px}.problem{padding:11px;color:var(--error-color,#c62828)}
.room-select{min-width:230px}code{word-break:break-all;font-size:12px}a{color:var(--primary-color,#1976d2)}@media(max-width:650px){.shell{padding:12px 10px 40px}.header h1{font-size:20px}.card{padding:12px}.toolbar button{padding:7px}}
`;
class HouseClimateMonitorPanel extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._hass=null;this._tab='Overview';this._mode='7d';this._offset=0;this._range=getRange('7d');this._data=null;this._room='';this._graph=null;this._busy=false;this._graphBusy=false;this._error='';this._timer=null;this._graphToken=0;this._narrow=false;this._customDates=null;}
 set hass(v){this._hass=v;if(this.isConnected&&!this._data)this._load();}
 set panel(v){this._panel=v;}
 set route(v){this._route=v;}
 set narrow(v){this._narrow=v;}
 connectedCallback(){this._render();this._load();this._timer=setInterval(()=>this._load(),60000);}
 disconnectedCallback(){if(this._timer)clearInterval(this._timer);}
 _sources(){return this._data?.sources||[];}
 async _load(){if(!this._hass?.callWS||this._busy)return;this._busy=true;
  try{this._data=await this._hass.callWS({type:'house_climate_monitor/status',start_time:this._range.start,end_time:this._range.end});this._overrides=Object.fromEntries(Object.entries(this._data.overrides||{}).map(([id,o])=>[id,o.selection]));this._error='';}
  catch(e){this._error=e.message||String(e);}finally{this._busy=false;this._render();}
 }
 async _testEmail(){
  try{
    const recipient=this._data?.options?.notify_entity||'configured recipient';
    if(!confirm('Send an actual test email using '+recipient+'?'))return;
    const result=await this._hass.callWS({type:'house_climate_monitor/test_email'});
    alert('Home Assistant accepted the test email call for '+result.recipient+'. Please confirm arrival in the mailbox.');
    await this._load();
  }catch(e){alert('Test email failed: '+(e.message||e));await this._load();}
 }
 async _setSource(id,selection,room){try{await this._hass.callWS({type:'house_climate_monitor/source',entity_id:id,selection,...(room?{room}:{})});await this._load();}
  catch(e){alert('Could not save sensor setting: '+(e.message||e));}}
 _changeRange(){this._range=this._customDates||getRange(this._mode,new Date(),this._offset);this._graph=null;this._render();this._load();if(METRIC[this._tab])this._loadGraph();}
 async _loadGraph(){if(!this._hass?.callWS||!this._data)return;
  const metric=METRIC[this._tab];if(!metric)return;
  let selected=this._sources().filter(x=>x.selected&&x.metric===metric&&x.room===this._room);
  if(!selected.length)return;
  const ids=selected.map(x=>x.entity_id).filter(x=>x.startsWith('sensor.')).slice(0,8);
  if(!ids.length){this._graph={error:'Current_temperature climate attributes cannot be plotted as independent sensor history. Use their original climate history in Home Assistant.'};this._render();return;}
  const token=++this._graphToken;this._graphBusy=true;this._render();
  try{let result={};const days=(new Date(this._range.end)-new Date(this._range.start))/86400000;
   if(days>30){const data=await this._hass.callWS({type:'recorder/statistics_during_period',start_time:this._range.start,end_time:this._range.end,statistic_ids:ids,period:days>400?'month':days>95?'week':'day',types:['mean','min','max']});
    for(const id of ids)result[id]=(data[id]||[]).filter(x=>x.mean!==null&&x.mean!==undefined).map(x=>[new Date(x.start).getTime(),x.mean]);
   }else{const data=await this._hass.callWS({type:'history/history_during_period',start_time:this._range.start,end_time:this._range.end,entity_ids:ids,significant_changes_only:false,minimal_response:false,no_attributes:true});
    result=decodeHistoryResponse(data,ids);
   }
   if(token===this._graphToken)this._graph={result,ids};
  }catch(e){if(token===this._graphToken)this._graph={error:'Recorder history could not be loaded: '+(e.message||e)};}
  finally{if(token===this._graphToken){this._graphBusy=false;this._render();}}
 }
 _drawGraph(){if(!this._graph)return '<p class="note">Select a room to load the recorded measurements.</p>';
  if(this._graph.error)return '<p class="note">'+esc(this._graph.error)+'</p>';
  const series=this._graph.ids.map((id,i)=>({id,i,points:this._graph.result[id]||[]})).filter(x=>x.points.length);
  if(!series.length)return '<p class="note">No Recorder data in this period. History is not inferred or backfilled.</p>';
  const start=new Date(this._range.start).getTime(),end=new Date(this._range.end).getTime();
  const vals=series.flatMap(s=>s.points.map(p=>p[1]));let min=Math.min(...vals),max=Math.max(...vals);if(min===max){min-=1;max+=1;}
  const colors=['#3278d3','#e27f19','#2f987a','#b74f90','#9768dd','#c6573c','#4482a1','#666'];
  const w=900,h=220,l=53,r=12,t=15,b=30;
  const x=p=>l+(p[0]-start)/Math.max(1,end-start)*(w-l-r);
  const y=p=>t+(max-p[1])/Math.max(.001,max-min)*(h-t-b);
  let paths=series.map(s=>`<polyline fill="none" stroke="${colors[s.i%colors.length]}" stroke-width="2" points="${s.points.map(p=>x(p).toFixed(1)+','+y(p).toFixed(1)).join(' ')}"/>`).join('');
  let labels=`<text x="3" y="20" fill="currentColor" font-size="12">${max.toFixed(1)}</text><text x="3" y="${h-30}" fill="currentColor" font-size="12">${min.toFixed(1)}</text>`;
  return `<svg class="graph" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="History of ${esc(this._room)} sensors"><path d="M${l} ${t}V${h-b}H${w-r}" fill="none" stroke="currentColor" opacity=".25"/>${paths}${labels}<text x="${l}" y="${h-8}" font-size="12" fill="currentColor">${esc(new Date(start).toLocaleDateString())}</text><text x="${w-r-105}" y="${h-8}" font-size="12" fill="currentColor">${esc(new Date(end).toLocaleDateString())}</text></svg>`+
   `<div class="legend">${series.map(s=>`<span><i class="dot" style="background:${colors[s.i%colors.length]}"></i>${esc(this._sources().find(r=>r.entity_id===s.id)?.name||s.id)} (${s.points.length} pts)</span>`).join('')}</div>`;
 }
 _tabOverview(){const sources=this._sources();const active=Object.entries(this._data?.incidents||{});
  const counts={temperature:sources.filter(s=>s.selected&&s.metric==='temperature').length,humidity:sources.filter(s=>s.selected&&s.metric==='humidity').length,pm25:sources.filter(s=>s.selected&&s.metric==='pm25').length,co2:sources.filter(s=>s.selected&&s.metric==='co2').length,voc_index:sources.filter(s=>s.selected&&s.metric==='voc_index').length};
  const card=(label,metric)=>`<div class="card"><h3>${label}</h3><div class="metric">${counts[metric]}</div><div class="sub">Selected sources</div></div>`;
  const rooms=[...new Set(sources.filter(x=>x.selected).map(x=>x.room))].sort();
  return `<div class="grid">${card('Temperature','temperature')}${card('Humidity','humidity')}${card('PM2.5','pm25')}${card('VOC index','voc_index')}${card('CO₂','co2')}</div>
    <div class="grid"><div class="card"><h3>Active incidents</h3><div class="metric ${active.length?'warn':'ok'}">${active.length}</div><p class="sub">Room-based incidents; recent alerts and recoveries below</p></div>
    <div class="card"><h3>Email queue</h3><div class="metric">${this._data.email?.pending||0}</div><p class="sub">Last accepted: ${esc(dt(this._data.email?.last_accepted))}</p>${this._data.email?.last_error?`<p class="warn">${esc(this._data.email.last_error)}</p>`:''}<button data-role="test-email">Send test email</button><p class="note">Actually invokes the configured Home Assistant notify entity.</p></div></div>
    <div class="card"><h3>Active room alerts</h3>${active.length?active.map(([key,s])=>`<div class="incident card"><b>${esc(key)}</b> · ${esc(s.level)}<div class="sub">Since ${esc(dt(s.since))} · Worst reading ${fmt(s.peak)}</div></div>`).join(''):'<p class="ok">No confirmed active incidents.</p>'}</div>
    <div class="card"><h3>Monitored rooms</h3>${rooms.map(room=>`<span class="chip">${esc(room)}</span>`).join('')}</div>`;
 }
 _tabMetric(){const metric=METRIC[this._tab], sources=this._sources().filter(x=>x.selected&&x.metric===metric);
  const extraRooms=this._tab==='VOC'?this._sources().filter(x=>x.metric==='voc_other'&&this._data?.overrides?.[x.entity_id]?.selection!=='exclude').map(x=>x.room):[];
  const rooms=[...new Set([...sources.map(x=>x.room),...extraRooms])].sort();if(!rooms.includes(this._room))this._room=rooms[0]||'';
  const inRoom=sources.filter(x=>x.room===this._room);
  const items=inRoom.map(s=>`<div class="card"><b>${esc(s.name)}</b><div class="metric">${s.value==null?'—':fmt(s.value)} <small>${esc(s.unit)}</small></div><div class="sub">${esc(s.entity_id)} · ${s.fresh?'Fresh':'Not recently reported'}</div></div>`).join('');
  const renson=(this._tab==='VOC'?this._sources().filter(x=>x.metric==='voc_other'&&x.room===this._room&&this._data?.overrides?.[x.entity_id]?.selection!=='exclude'):[]);
  const context=renson.length?'<div class="card"><h3>Other VOC measurements — different scale</h3>'+renson.map(x=>'<p>'+esc(x.name)+': '+fmt(x.value)+' '+esc(x.unit)+' <small>('+esc(x.entity_id)+')</small></p>').join('')+'<p class="note">Context only. These values are NOT compared against IKEA VOC-index thresholds.</p></div>':'';
  const affected=(this._data?.events||[]).filter(e=>e.room===this._room && (e.metric===metric || e.metric==='temp_low'&&metric==='temperature'||e.metric==='temp_high'&&metric==='temperature'));
  let extra=this._tab==='VOC'?'<p class="note">IKEA VOC indices are comparable with each other. Raw/estimated Renson VOC readings use another scale and are display-only.</p>':'';
  if(this._tab==='Emergencies')extra='<p class="note warn">Abnormal heat/rapid-rise emails are advisory. They are not smoke, CO or certified heat alarms. Keep dedicated safety alarms operational.</p>';
  return `${extra}<div class="toolbar"><b>Room</b><select class="room-select" data-role="room">${rooms.map(r=>`<option value="${esc(r)}" ${r===this._room?'selected':''}>${esc(r)}</option>`).join('')}</select></div>
    <div class="grid">${items||'<div class="card">No selected sensor in this category. Open Sensors to review candidates.</div>'}</div>${context}
    <div class="card"><h3>${esc(this._tab)} trend · ${esc(this._room)}</h3>${this._graphBusy?'<p class="note">Loading from Home Assistant Recorder...</p>':this._drawGraph()}<p class="note">Measurements come from Recorder; long-term periods require matching statistics. Missing historical data is not estimated.</p></div>
    <div class="card"><h3>Recorded events for room</h3>${affected.slice(-30).reverse().map(e=>`<p><b>${esc(e.kind)}</b> ${esc(e.level||'')} · ${esc(dt(e.when))}<br><small>${esc(e.reason||'')}</small></p>`).join('')||'<p class="note">No events in selected period.</p>'}</div>`;
 }
 _tabIncidents(){const events=[...(this._data?.events||[])].reverse();
  return `<div class="card"><h3>Incident and email history</h3><p class="note">History is retained for 90 days. Date-range selections older than retention cannot reconstruct past incidents.</p><div class="table-wrap"><table class="table"><thead><tr><th>Time</th><th>Event</th><th>Room / metric</th><th>Reason</th></tr></thead><tbody>${events.map(e=>`<tr><td>${esc(dt(e.when))}</td><td>${esc(e.kind)}</td><td>${esc(e.key||e.room||'')}</td><td>${esc(e.reason||'')}${e.recipient?`<small>${esc(e.recipient)}</small>`:''}</td></tr>`).join('')}</tbody></table></div>${!events.length?'<p>No incidents in selected period.</p>':''}</div>`;
 }
 _tabSensors(){const sources=this._sources();
  return `<div class="card"><h3>Discovered measurements (${sources.length})</h3><p class="note">Default classification is conservative. Out-of-room, appliance, outdoor and setpoint readings are excluded automatically. Use Include, Exclude or Auto for individual entities. For unassigned sensors, set a room first.</p>
    <div class="toolbar"><input data-role="filter" placeholder="Filter by room, sensor, entity or reason" value="${esc(this._filter||'')}"><span class="sub">Changes take effect immediately and are persisted locally.</span></div>
    <div class="table-wrap"><table class="table"><thead><tr><th>Room / reading</th><th>Entity / reason</th><th>Selection</th><th>Assign</th></tr></thead><tbody>${sources.filter(x=>!this._filter||[x.room,x.name,x.entity_id,x.reason].join(' ').toLowerCase().includes(this._filter.toLowerCase())).map(s=>`<tr><td><b>${esc(s.room)}</b><small>${esc(s.metric)} · ${s.value==null?'—':fmt(s.value)} ${esc(s.unit)} · ${s.fresh?'fresh':'stale'}</small></td>
    <td>${esc(s.name)}<small><code>${esc(s.entity_id)}</code></small><small>${esc(s.reason)}</small></td>
    <td><select data-source="${esc(s.entity_id)}"><option value="auto" ${(!this._override(s.entity_id)||this._override(s.entity_id)==='auto')?'selected':''}>Auto (${s.eligible?'eligible':'not eligible'})</option><option value="include" ${s.metric==='voc_other'?'disabled':''} ${this._override(s.entity_id)==='include'?'selected':''}>Include</option><option value="exclude" ${this._override(s.entity_id)==='exclude'?'selected':''}>Exclude</option></select><small>${s.selected?'Monitored':'Not monitored'}</small></td>
    <td><button data-room="${esc(s.entity_id)}">Room...</button></td></tr>`).join('')}</tbody></table></div></div>`;
 }
 _override(id){return this._overrides?.[id]||'';}
 _rangeControls(){return `<div class="toolbar"><b>Period:</b><select data-role="period">${[['today','Today'],['yesterday','Yesterday'],['week','This week'],['month','This month'],['year','This year'],['48h','Last 48 hours'],['7d','Last 7 days'],['30d','Last 30 days'],['90d','Last 90 days'],['365d','Last 365 days'],['3y','Last 3 years'],['custom','Custom dates']].map(([id,name])=>`<option value="${id}" ${id===this._mode?'selected':''}>${name}</option>`).join('')}</select>
  <button data-move="-1" title="Previous period">◀</button><button data-move="1" title="Next period">▶</button>${this._mode==='custom'?`<input type="date" data-role="from" value="${(this._customDates?.start||'').slice(0,10)}"><input type="date" data-role="to" value="${(this._customDates?.end||'').slice(0,10)}"><button data-role="apply">Apply</button>`:''}
  <span class="sub">${esc(new Date(this._range.start).toLocaleDateString())} – ${esc(new Date(this._range.end).toLocaleDateString())}</span></div>`;}
 _render(){const root=this.shadowRoot;
  if(!this._data){root.innerHTML='<style>'+CSS+'</style><div class="shell">Loading Climate Monitor... '+esc(this._error)+'</div>';return;}
  const other=this._tab==='Overview'?this._tabOverview():METRIC[this._tab]?this._tabMetric():this._tab==='Incidents'?this._tabIncidents():this._tabSensors();
  root.innerHTML=`<style>${CSS}</style><div class="shell"><div class="header"><div class="row"><button data-role="drawer" aria-label="Open Home Assistant navigation menu">☰</button><h1>Climate Monitor</h1><span class="sub">v${esc(version)}</span></div><button data-role="refresh">Refresh</button></div>
   <div class="tabs">${TABS.map(t=>`<button data-tab="${esc(t)}" class="${t===this._tab?'active':''}">${esc(t)}</button>`).join('')}</div>
   ${this._rangeControls()}${this._error?`<div class="problem">${esc(this._error)}</div>`:''}
   ${other}<p class="note">This is advisory climate monitoring using existing Home Assistant sensors. It never controls heating or replaces certified fire, CO or smoke alarms.</p></div>`;
  root.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{this._tab=b.dataset.tab;this._graph=null;this._render();if(METRIC[this._tab])this._loadGraph();}));
  root.querySelector('[data-role=period]')?.addEventListener('change',e=>{this._mode=e.target.value;this._offset=0;this._customDates=null;if(this._mode!=='custom')this._changeRange();else this._render();});
  root.querySelectorAll('[data-move]').forEach(b=>b.addEventListener('click',()=>{this._offset+=Number(b.dataset.move);if(this._mode!=='custom')this._changeRange();}));
  root.querySelector('[data-role=apply]')?.addEventListener('click',()=>{
    const a=root.querySelector('[data-role=from]').value,b=root.querySelector('[data-role=to]').value;
    if(!a||!b||a>b){alert('Choose a valid date interval');return;}
    const start=new Date(a+'T00:00:00'),end=new Date(b+'T23:59:59');
    if((end-start)>1099*86400000){alert('Maximum range is 3 years');return;}
    this._customDates={start:start.toISOString(),end:end.toISOString()};this._changeRange();
  });
  root.querySelector('[data-role=refresh]')?.addEventListener('click',()=>this._load());
  root.querySelector('[data-role=test-email]')?.addEventListener('click',()=>this._testEmail());
  root.querySelector('[data-role=drawer]')?.addEventListener('click',()=>this.dispatchEvent(new Event('hass-toggle-menu',{bubbles:true,composed:true})));
  root.querySelector('[data-role=room]')?.addEventListener('change',e=>{this._room=e.target.value;this._graph=null;this._render();this._loadGraph();});
  root.querySelector('[data-role=filter]')?.addEventListener('change',e=>{this._filter=e.target.value;this._render();});
  root.querySelectorAll('[data-source]').forEach(el=>el.addEventListener('change',async e=>{
    const entity=e.target.dataset.source;this._overrides??={};this._overrides[entity]=e.target.value;
    const source=this._sources().find(s=>s.entity_id===entity);
    if(source?.room==='Unassigned'&&e.target.value==='include'){const room=prompt('Assign an indoor room before including this sensor:','');if(!room?.trim()){this._render();return;}await this._setSource(entity,e.target.value,room.trim());}
    else await this._setSource(entity,e.target.value,this._data.overrides?.[entity]?.room||'');}));
  root.querySelectorAll('[data-room]').forEach(el=>el.addEventListener('click',async()=>{
    const id=el.dataset.room,s=this._sources().find(x=>x.entity_id===id);
    const room=prompt('Assign an indoor room name for this sensor:',s?.room==='Unassigned'?'':(s?.room||''));
    if(room&&room.trim())await this._setSource(id,this._override(id)||'auto',room.trim());
  }));
 }
}
if(!customElements.get(TAG))customElements.define(TAG,HouseClimateMonitorPanel);
