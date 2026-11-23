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

/** Explain why a per-room incident is still active without hiding source disagreement. */
export function describeIncidentSources(key, incident, sources, options = {}) {
  const pipe = key.lastIndexOf('|');
  const room = pipe < 0 ? key : key.slice(0, pipe);
  const rule = pipe < 0 ? '' : key.slice(pipe + 1);
  const metric = rule === 'temp_low' || rule === 'temp_high' ? 'temperature' :
    rule === 'voc' ? 'voc_index' : rule.startsWith('safety:') ? 'safety' : rule;
  const limits = {
    humidity: ['humidity_high', 70, 'humidity_recovery', 65, 'humidity_recovery_minutes', 30],
    temp_low: ['temp_low_c', 17.5, 'temp_recovery_c', 18, 'temp_recovery_minutes', 10],
    temp_high: ['temp_high_c', 45, 'temp_high_recovery_c', 38, 'temp_high_recovery_minutes', 10],
    pm25: ['pm25_warning', 35, 'pm25_recovery', 25, 'pm25_recovery_minutes', 15],
    co2: ['co2_warning', 1500, 'co2_recovery', 1000, 'co2_recovery_minutes', 30],
    voc: ['voc_elevated_index', 200, 'voc_elevated_index', 200, 'voc_recovery_minutes', 30],
  };
  const policy = limits[rule];
  const warning = policy ? Number(options[policy[0]] ?? policy[1]) : null;
  const recovery = policy ? Number(options[policy[2]] ?? policy[3]) : null;
  const recoveryMinutes = policy ? Number(options[policy[4]] ?? policy[5]) : null;
  const affected = new Set(incident?.implicated ?? []);
  const selected = (sources ?? []).filter(s => s.selected && s.metric === metric &&
    (room === 'Household' && metric === 'voc_index' || s.room === room) &&
    (!rule.startsWith('safety:') || rule === 'safety:' + s.entity_id));
  const rows = selected.map(s => {
    const valid = Boolean(s.fresh && s.value != null && Number.isFinite(Number(s.value)));
    const value = valid ? Number(s.value) : null;
    const implicated = affected.has(s.entity_id);
    const blocksRecovery = rule === 'temp_low'
      ? (valid ? value < recovery : implicated)
      : (valid ? recovery != null && value > recovery : implicated);
    const condition = !valid ? (implicated ? 'No fresh reading — recovery blocked' : 'No fresh reading')
      : blocksRecovery ? 'Above/below recovery limit — still blocking'
      : implicated ? 'Previously elevated — now normal' : 'Normal';
    return {entity_id: s.entity_id, name: s.name, unit: s.unit, value: s.value,
      fresh: valid, implicated, blocksRecovery, condition};
  });
  const good = rows.filter(r => r.fresh);
  const values = good.map(r => Number(r.value));
  const disagreement = rule === 'humidity' && values.length >= 2
    ? Math.max(...values) - Math.min(...values) : null;
  const allReady = good.length > 0 && rows.every(r => !r.blocksRecovery) && policy != null;
  return {room, rule, warning, recovery, recoveryMinutes, rows,
    disagreement, allReady, hasAffected: affected.size > 0,
    pendingRecoverySince: incident?.recovery_since ?? null};
}

const version=new URL(import.meta.url).searchParams.get('v')||'dev';
const TAG='house-climate-monitor-panel-v'+version.replace(/\./g,'-');
const TABS=['Overview','Temperature','Humidity','PM2.5','VOC','CO₂','Emergencies','Incidents','Sensors'];
const METRIC={Temperature:'temperature',Humidity:'humidity','PM2.5':'pm25',VOC:'voc_index','CO₂':'co2',Emergencies:'temperature'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dt=t=>t?new Date(t).toLocaleString(): '—';
const fmt=v=>v===null||v===undefined?'—':Number.isFinite(Number(v))?Number(v).toFixed(1):String(v);
const evidenceHTML=(key,state,sources,options)=>{
 const diag=describeIncidentSources(key,state,sources,options);
 const policy=diag.recovery==null?'':`<p class="note">Alert threshold: ${fmt(diag.warning)}. Recovery requires ${diag.rule==='temp_low'?'at least':'at most'} ${fmt(diag.recovery)} for ${fmt(diag.recoveryMinutes)} minutes. This uses every selected reporting sensor, not an average.</p>`;
 const readings=diag.rows.map(r=>`<div class="evidence-source"><b>${esc(r.name)}: ${r.value==null?'—':fmt(r.value)} ${esc(r.unit)}</b><small>${esc(r.entity_id)}</small><small class="${r.blocksRecovery?'warn':'sub'}">${esc(r.condition)}${r.implicated?' · Affected this incident':''}</small></div>`).join('');
 const discrepancy=diag.disagreement!=null&&diag.disagreement>=15
   ? `<p class="warn">Sensors disagree by ${fmt(diag.disagreement)} percentage points. Compare locations and calibration; no source is automatically discarded.</p>` : '';
 const recovery=diag.pendingRecoverySince
   ? `<p class="ok">Recovery confirmation started ${esc(dt(Number(diag.pendingRecoverySince)*1000))}; a notification follows only when the full interval completes.</p>`
   : diag.allReady
     ? '<p class="sub">Readings meet the recovery limit; confirmation has not yet started in the monitoring state.</p>'
     : '<p class="sub">Recovery is not yet confirmed. Inspect the readings above for blockers.</p>';
 return `<p class="sub">Trigger: ${esc(state.last_reason||'Not recorded')}</p>${policy}<div class="evidence-list">${readings||'<p class="note">No selected source is currently reporting for this incident.</p>'}</div>${discrepancy}${recovery}`;
};
// Use HA-local calendar dates in every browser; UTC surrogate dates avoid DST arithmetic.
const cmZone=hass=>hass?.config?.time_zone||'UTC';
const cmCivil=(instant,hass)=>{
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{
  timeZone:cmZone(hass),year:'numeric',month:'2-digit',day:'2-digit'
 }).formatToParts(instant).filter(x=>x.type!=='literal').map(x=>[x.type,+x.value]));
 return new Date(Date.UTC(parts.year,parts.month-1,parts.day));
};
const cmAddDays=(date,n)=>new Date(date.getTime()+86400000*n);
const cmFirstWeekday=hass=>{
 const day=['sunday','monday','tuesday','wednesday','thursday','friday','saturday']
  .indexOf(hass?.locale?.first_weekday);
 if(day>=0)return day;
 try{
  const l=new Intl.Locale(hass?.locale?.language||hass?.language||'en-GB');
  return (l.weekInfo?.firstDay??l.getWeekInfo?.().firstDay??1)%7;
 }catch(_){return 1;}
};
const cmToUtc=(civil,hass)=>{
 const target=civil.getTime();
 const format=new Intl.DateTimeFormat('en-GB',{
  timeZone:cmZone(hass),year:'numeric',month:'2-digit',day:'2-digit',
  hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'
 });
 let epoch=target;
 for(let i=0;i<4;i++){
  const p=Object.fromEntries(format.formatToParts(new Date(epoch))
   .filter(x=>x.type!=='literal').map(x=>[x.type,+x.value]));
  const step=target-Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute,p.second);
  epoch+=step;if(step===0)break;
 }
 return new Date(epoch);
};
export function rangeForCalendarDays(first,last,hass=null){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(first)||!/^\d{4}-\d{2}-\d{2}$/.test(last)||last<first)
  throw new Error('Choose a valid date interval');
 const start=new Date(first+'T00:00:00.000Z');
 const inclusiveEnd=new Date(last+'T00:00:00.000Z');
 if(Number.isNaN(start.getTime())||Number.isNaN(inclusiveEnd.getTime())||
    start.toISOString().slice(0,10)!==first||inclusiveEnd.toISOString().slice(0,10)!==last)
  throw new Error('Invalid calendar date');
 const end=cmAddDays(inclusiveEnd,1);
 if((end-start)/86400000>1099)throw new Error('Maximum range is 3 years');
 return {start:cmToUtc(start,hass).toISOString(),end:cmToUtc(end,hass).toISOString()};
}
export function getRange(mode,anchor=new Date(),offset=0,hass=null){
 const now=new Date();
 const today=cmCivil(anchor,hass);
 if(['today','yesterday','week','month','year'].includes(mode)){
  let start,end;
  const year=today.getUTCFullYear(),month=today.getUTCMonth();
  if(mode==='today'||mode==='yesterday'){
   start=cmAddDays(today,(mode==='yesterday'?-1:0)+offset);
   end=cmAddDays(start,1);
  }else if(mode==='week'){
   const weekday=(today.getUTCDay()-cmFirstWeekday(hass)+7)%7;
   start=cmAddDays(today,-weekday+7*offset);
   end=cmAddDays(start,7);
  }else if(mode==='month'){
   start=new Date(Date.UTC(year,month+offset,1));
   end=new Date(Date.UTC(year,month+offset+1,1));
  }else{
   start=new Date(Date.UTC(year+offset,0,1));
   end=new Date(Date.UTC(year+offset+1,0,1));
  }
  let startTime=cmToUtc(start,hass),endTime=cmToUtc(end,hass);
  if(endTime>now)endTime=now;
  if(startTime>=endTime){startTime=cmToUtc(start,hass);endTime=cmToUtc(end,hass);}
  return {start:startTime.toISOString(),end:endTime.toISOString()};
 }
 const day=86400000;
 const lengths={'48h':2,'7d':7,'30d':30,'90d':90,'365d':365,'3y':1095};
 const duration=(lengths[mode]||7)*day;
 let end=new Date(anchor.getTime()+offset*duration);
 if(end>now)end=now;
 return {start:new Date(end.getTime()-duration).toISOString(),end:end.toISOString()};
}
const cmDayLabel=(instant,hass)=>new Intl.DateTimeFormat(
 hass?.locale?.language||hass?.language||undefined,
 {timeZone:cmZone(hass),day:'numeric',month:'short',year:'numeric'}
).format(new Date(instant));
const cmInputDate=(instant,hass)=>cmCivil(new Date(instant),hass).toISOString().slice(0,10);
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
.evidence-list{display:flex;flex-direction:column;gap:5px;margin-top:10px}.evidence-source{border-left:2px solid var(--divider-color,#ddd);padding:5px 10px}.evidence-source small{display:block;color:var(--secondary-text-color,#666);overflow-wrap:anywhere;margin-top:3px}.evidence-source small.warn{color:var(--error-color,#c62828)}
.room-select{min-width:230px}code{word-break:break-all;font-size:12px}a{color:var(--primary-color,#1976d2)}@media(max-width:650px){.shell{padding:12px 10px 40px}.header h1{font-size:20px}.card{padding:12px}.toolbar button{padding:7px}}
`;
class HouseClimateMonitorPanel extends HTMLElement {
 constructor(){super();this.attachShadow({mode:'open'});this._hass=null;this._tab='Overview';this._mode='7d';this._offset=0;this._range=getRange('7d');this._data=null;this._room='';this._graph=null;this._busy=false;this._graphBusy=false;this._error='';this._timer=null;this._graphToken=0;this._narrow=false;this._customDates=null;}
 set hass(v){const old=cmZone(this._hass);this._hass=v;if(old!==cmZone(v)&&this._mode!=='custom')this._range=getRange(this._mode,new Date(),this._offset,v);if(this.isConnected&&!this._data)this._load();}
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
 _changeRange(){this._range=this._customDates||getRange(this._mode,new Date(),this._offset,this._hass);this._graph=null;this._render();this._load();if(METRIC[this._tab])this._loadGraph();}
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
  return `<svg class="graph" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="History of ${esc(this._room)} sensors"><path d="M${l} ${t}V${h-b}H${w-r}" fill="none" stroke="currentColor" opacity=".25"/>${paths}${labels}<text x="${l}" y="${h-8}" font-size="12" fill="currentColor">${esc(cmDayLabel(start,this._hass))}</text><text x="${w-r-105}" y="${h-8}" font-size="12" fill="currentColor">${esc(cmDayLabel(end-1,this._hass))}</text></svg>`+
   `<div class="legend">${series.map(s=>`<span><i class="dot" style="background:${colors[s.i%colors.length]}"></i>${esc(this._sources().find(r=>r.entity_id===s.id)?.name||s.id)} (${s.points.length} pts)</span>`).join('')}</div>`;
 }
 _tabOverview(){const sources=this._sources();const active=Object.entries(this._data?.incidents||{});
  const counts={temperature:sources.filter(s=>s.selected&&s.metric==='temperature').length,humidity:sources.filter(s=>s.selected&&s.metric==='humidity').length,pm25:sources.filter(s=>s.selected&&s.metric==='pm25').length,co2:sources.filter(s=>s.selected&&s.metric==='co2').length,voc_index:sources.filter(s=>s.selected&&s.metric==='voc_index').length};
  const card=(label,metric)=>`<div class="card"><h3>${label}</h3><div class="metric">${counts[metric]}</div><div class="sub">Selected sources</div></div>`;
  const rooms=[...new Set(sources.filter(x=>x.selected).map(x=>x.room))].sort();
  return `<div class="grid">${card('Temperature','temperature')}${card('Humidity','humidity')}${card('PM2.5','pm25')}${card('VOC index','voc_index')}${card('CO₂','co2')}</div>
    <div class="grid"><div class="card"><h3>Active incidents</h3><div class="metric ${active.length?'warn':'ok'}">${active.length}</div><p class="sub">Room-based incidents; recent alerts and recoveries below</p></div>
    <div class="card"><h3>Email queue</h3><div class="metric">${this._data.email?.pending||0}</div><p class="sub">Last accepted: ${esc(dt(this._data.email?.last_accepted))}</p>${this._data.email?.last_error?`<p class="warn">${esc(this._data.email.last_error)}</p>`:''}<button data-role="test-email">Send test email</button><p class="note">Actually invokes the configured Home Assistant notify entity.</p></div></div>
    <div class="card"><h3>Active room alerts</h3><p class="note">Peak is historical, not the current reading. All currently selected sources are shown below.</p>${active.length?active.map(([key,s])=>`<div class="incident card"><b>${esc(key)}</b> · ${esc(s.level)}<div class="sub">Since ${esc(dt(s.since))} · Historical worst ${fmt(s.peak)}</div>${evidenceHTML(key,s,sources,this._data?.options||{})}</div>`).join(''):'<p class="ok">No confirmed active incidents.</p>'}</div>
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
    <td><select data-source="${esc(s.entity_id)}"><option value="auto" ${(!this._override(s.entity_id)||this._override(s.entity_id)==='auto')?'selected':''}>Auto (${s.eligible?'eligible':'not eligible'})</option><option value="include" ${s.metric==='voc_other'||s.reason?.startsWith('configuration limit')?'disabled':''} ${this._override(s.entity_id)==='include'?'selected':''}>Include</option><option value="exclude" ${this._override(s.entity_id)==='exclude'?'selected':''}>Exclude</option></select><small>${s.selected?'Monitored':'Not monitored'}</small></td>
    <td><button data-room="${esc(s.entity_id)}">Room...</button></td></tr>`).join('')}</tbody></table></div></div>`;
 }
 _override(id){return this._overrides?.[id]||'';}
 _rangeControls(){return `<div class="toolbar"><b>Period:</b><select data-role="period">${[['today','Today'],['yesterday','Yesterday'],['week','This week'],['month','This month'],['year','This year'],['48h','Last 48 hours'],['7d','Last 7 days'],['30d','Last 30 days'],['90d','Last 90 days'],['365d','Last 365 days'],['3y','Last 3 years'],['custom','Custom dates']].map(([id,name])=>`<option value="${id}" ${id===this._mode?'selected':''}>${name}</option>`).join('')}</select>
  <button data-move="-1" title="Previous period">◀</button><button data-move="1" title="Next period">▶</button>${this._mode==='custom'?`<input type="date" data-role="from" value="${(this._customDates?.start?cmInputDate(this._customDates.start,this._hass):'')}"><input type="date" data-role="to" value="${(this._customDates?.end?cmInputDate(Date.parse(this._customDates.end)-1,this._hass):'')}"><button data-role="apply">Apply</button><small class="sub">Leave the end date blank to select one day.</small>`:''}
  <span class="sub">${esc(cmDayLabel(this._range.start,this._hass))} – ${esc(cmDayLabel(Date.parse(this._range.end)-1,this._hass))}</span></div>`;}
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
    if(!a||(b&&a>b)){alert('Choose a valid date interval');return;}
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
