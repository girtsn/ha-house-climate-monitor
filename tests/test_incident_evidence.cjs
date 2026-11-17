// Active incident diagnostics: a lower Renson reading does not negate a higher Tado reading.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const src = fs.readFileSync(path.join(__dirname, '../custom_components/house_climate_monitor/www/managed-panel.js'), 'utf8');
globalThis.customElements = {get: () => true, define: () => {}};
globalThis.HTMLElement = class {};
(async()=>{
 const {describeIncidentSources} = await import('data:text/javascript;charset=utf-8,'+encodeURIComponent(src));
 const a={entity_id:'sensor.1fl_bathroom_humidity',name:'Tado bathroom',room:'1fl bathroom',metric:'humidity',value:80,unit:'%',fresh:true,selected:true};
 const b={entity_id:'sensor.1fl_vent_waves_humidity',name:'Renson Waves',room:'1fl bathroom',metric:'humidity',value:54,unit:'%',fresh:true,selected:true};
 const episode={implicated:[a.entity_id],last_reason:'Tado bathroom qualified for warning',recovery_since:null};
 const result=describeIncidentSources('1fl bathroom|humidity',episode,[a,b],{humidity_high:70,humidity_recovery:65,humidity_recovery_minutes:30});
 assert.equal(result.rows.length,2);
 assert.equal(result.disagreement,26);
 assert.equal(result.recovery,65);
 assert.equal(result.rows[0].blocksRecovery,true);
 assert.equal(result.rows[1].blocksRecovery,false);
 assert.equal(result.allReady,false);
 const normal=describeIncidentSources('1fl bathroom|humidity',episode,[{...a,value:62},b],{});
 assert.equal(normal.allReady,true);
 const missing=describeIncidentSources('1fl bathroom|humidity',episode,[{...a,fresh:false},b],{});
 assert.equal(missing.allReady,false);
 assert.match(missing.rows[0].condition,/recovery blocked/);
 const inactive=describeIncidentSources('1fl bathroom|humidity',episode,[{...a,selected:false},b],{});
 assert.equal(inactive.rows.length,1);
 assert.equal(inactive.allReady,true); // Excluding affected source is separately retired by backend.
 console.log('Active incident per-sensor and recovery diagnostics passed');
})().catch(err=>{console.error(err);process.exitCode=1});
