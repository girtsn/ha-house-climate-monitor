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
  const {decodeHistoryResponse} = await import('data:text/javascript;charset=utf-8,' + encodeURIComponent(src));
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
  console.log('Home Assistant history response schema and decoding passed');
})().catch(error => {console.error(error);process.exitCode = 1;});
