// Regression test for the HA WebSocket history schema and compressed result format.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const src = fs.readFileSync(path.join(__dirname, '../custom_components/house_climate_monitor/www/managed-panel.js'), 'utf8');
assert.match(src, /significant_changes_only:false/);
assert.doesNotMatch(src, /\bsignificant_changes:/);
globalThis.customElements = {get: () => true, define: () => {}};
globalThis.HTMLElement = class {};
(async () => {
  const {decodeHistoryResponse,getRange,rangeForCalendarDays} = await import('data:text/javascript;charset=utf-8,' + encodeURIComponent(src));
  const response = {
    'sensor.first': [
      {s: '19.1', lu: 1790000000},
      {s: 'unavailable', lu: 1790000060},
      {s: '18.9', lc: 1790000120},
      {state: '17.5', last_changed: '2026-11-17T18:00:00Z'},
    ],
    'sensor.second': [{s: '22', lu: 1790000005}],
  };
  assert.deepEqual(decodeHistoryResponse(response, ['sensor.first', 'sensor.second', 'sensor.missing']), {
    'sensor.first': [[1790000000000, 19.1], [1790000120000, 18.9], [Date.parse('2026-11-17T18:00:00Z'), 17.5]],
    'sensor.second': [[1790000005000, 22]],
    'sensor.missing': [],
  });
  assert.deepEqual(decodeHistoryResponse([], ['sensor.first']), {'sensor.first': []});

  const ha={config:{time_zone:'Europe/Brussels'},locale:{first_weekday:'monday',language:'en-GB'}};
  const oneDay=rangeForCalendarDays('2026-11-22','2026-11-22',ha);
  assert.deepEqual(oneDay,{
    start:'2026-11-21T23:00:00.000Z',
    end:'2026-11-22T23:00:00.000Z'
  });
  const fromOtherZone=getRange('yesterday',new Date('2026-11-22T23:30:00.000Z'),0,ha);
  assert.deepEqual(fromOtherZone,oneDay);
  const spring=rangeForCalendarDays('2026-03-29','2026-03-29',ha);
  assert.equal(Date.parse(spring.end)-Date.parse(spring.start),23*3600000);
  assert.equal(spring.start,'2026-03-28T23:00:00.000Z');
  const autumn=rangeForCalendarDays('2026-10-25','2026-10-25',ha);
  assert.equal(Date.parse(autumn.end)-Date.parse(autumn.start),25*3600000);
  assert.equal(autumn.start,'2026-10-24T22:00:00.000Z');
  const us={config:{time_zone:'America/New_York'},locale:{first_weekday:'sunday'}};
  const monday=new Date('2026-11-23T12:00:00Z');
  const usWeek=getRange('week',monday,0,us);
  assert.equal(usWeek.start,'2026-11-22T05:00:00.000Z');
  assert.throws(()=>rangeForCalendarDays('2026-11-23','2026-11-22',ha));

  console.log('Home Assistant history response schema and decoding passed');
})().catch(error => {console.error(error);process.exitCode = 1;});
