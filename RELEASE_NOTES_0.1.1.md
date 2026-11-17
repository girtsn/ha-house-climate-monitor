# House Climate Monitor v0.1.1

## Fix: historical trend graphs

- Use the supported Home Assistant history WebSocket argument `significant_changes_only`, replacing the unsupported `significant_changes` parameter. This resolves the `invalid_format` error when opening temperature, humidity, PM2.5, VOC or CO₂ historical graphs.
- Decode the Recorder response correctly as an object keyed by entity ID, including compact state `s` and timestamp `lu`/`lc` fields. The previous graph handler incorrectly expected an array of rows.
- Ignore unavailable/non-numeric history samples rather than inventing a measurement.
- Add a Node regression test, run by the validation workflow, for the WebSocket argument and history response.

## Unchanged

- Room monitoring thresholds and incident/recovery email rules, notification target, source exclusions and all persistent state are unchanged.
- `hacs.json` still contains valid, documented metadata. On Home Assistant Marketplace 2026.11, warnings about omitted optional `hacs`, `filename` and `persistent_directory` keys are a separately reported Marketplace issue, not a reason to insert invalid placeholder values.

Update through the published GitHub release in HACS / Marketplace and restart Home Assistant so the updated version-scoped dashboard assets load.
