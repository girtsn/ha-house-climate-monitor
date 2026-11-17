# House Climate Monitor

[![Validate](https://github.com/girtsn/ha-house-climate-monitor/actions/workflows/validate.yaml/badge.svg)](https://github.com/girtsn/ha-house-climate-monitor/actions/workflows/validate.yaml)

A local Home Assistant custom integration to group existing environmental measurements by indoor room, send **real** incident/recovery emails and show events, sensor selections and recorded trends in one sidebar dashboard. Reusable in other homes: **no household sensor IDs or private readings in source code**.

> **Beta / safety notice:** The rules engine has automated unit tests but has **not been verified on a running Home Assistant instance**. Email delivery depends on your existing notification entity; a successful HA service call does not prove mailbox delivery. This is not a smoke, fire, gas or CO alarm. Keep certified alarms and any existing safety notification automations active. Disable duplicate environmental automations only after testing the new integration.

## Installation

### HACS / Home Assistant Marketplace (after the GitHub Release is published)

1. Open HACS or Marketplace in Home Assistant; add `https://github.com/girtsn/ha-house-climate-monitor` as a **custom Integration repository**.
2. Install the latest **published release `v0.1.0` or later**. Branch installs are intentionally hidden in `hacs.json`.
3. Restart Home Assistant and navigate to **Settings → Devices & services → Add integration → House Climate Monitor**.
4. Select a working `notify.*` entity (for example `notify.email_family`), verify real notifications are enabled and review auto-include.
5. Open **Climate Monitor** in the sidebar, then **Sensors** to inspect source selection and area assignments.
6. Check the correct recipient by causing a safe test incident using a dedicated synthetic test sensor; **do not deliberately create smoke, combustion, dangerous heating or poor air conditions**.
7. In the **Overview** tab, click **Send test email** and verify the message arrives in your mailbox. After confirming actual email receipt and sensor grouping, disable overlapping older temperature/humidity/PM2.5/VOC notification automations. Keep independent safety, Vaillant and device-availability automations.

### Manual install

Copy `custom_components/house_climate_monitor/` into `/config/custom_components/house_climate_monitor/`, restart Home Assistant and add the integration through the UI. This works without HACS while repository publication is pending.

## Defaults (all thresholds and durations are UI-configurable)

| Type | Confirmation | Recovery | Notes |
|---|---|---|---|
| Low room temperature | Below 17.5°C for 15 min | ≥18°C for 10 min | Per-room deduplication; any sensor qualifies |
| High humidity | Above 70% for 60 min | ≤65% for 30 min | Severe >90% for 30 min |
| PM2.5 | >35 µg/m³ for **30 min** | ≤25 µg/m³ for 15 min | Severe >150 for 5 min; extreme >300 for 1 min |
| IKEA-style VOC index | >350 for 30 min **or** ≥3 distinct rooms ≥200 for 10 min | All previously affected sources fresh below 200 for 30 min | Household episode with peaks, one warning and one recovery |
| Abnormal room heat | ≥45°C for 2 min | ≤38°C for 10 min | Critical ≥55°C for 1 min; rapid rise 10°C within 5 min when ≥30°C; *advisory only* |
| Indoor CO₂ | >1500 ppm for 30 min | ≤1000 ppm for 30 min | Severe >2500 ppm for 15 min; **not** a carbon-monoxide detector |
| Existing smoke/CO/gas/heat binary alarms | Immediate when enabled *and manually included* | On reported clear | Forwarding disabled by default to prevent duplicates |
| PM2.5 24h average | >15 µg/m³, daily at 20:00 | Daily report only | Disabled by default; requires ≥18h of sampled coverage |

The basic PM2.5 automation pasted in chat **actually waits 30 minutes**, despite a description mentioning 15. This integration takes the executable value as the default. Set **PM2.5 → Warning minutes = 15** if that was the intended policy.

Recovery is not emitted when previously implicated sources are unavailable, unknown or stale; it is not inferred from absence of data. Pending timers and active incidents are persisted across restarts; any source whose data has become stale is not used as evidence of sustained conditions.

## Discovering and managing sensors

Sensor candidates are enumerated from Home Assistant state/area/device registries on startup, after source changes and on a periodic evaluation. Measurement types are derived from device class, unit and entity metadata. Indoor eligible sources are included automatically by default, provided they have a known room. Devices may be excluded or explicitly included, and room mappings may be overridden from the **Sensors** tab.

Conservative defaults exclude outdoor and equipment temperatures, boilers and hot-water setpoints, towel-dryer heating elements, sauna values, inverter/battery/CPU temperatures, diagnostic values, and other VOC scales. Mirrored Tado climate temperature attributes are excluded when a matching `sensor.*_temperature` is present; independent Fujitsu climate attribute readings can be included. The integration **never polls the source cloud** and never controls heating.

The distinction between **ambient room temperature** and **equipment temperature** is important: overriding an equipment sensor into room monitoring will apply the room limits, which may be inappropriate. Check source selection before enabling alerts.

## Configuration

Use **Settings → Devices & services → House Climate Monitor → Configure** to change notifications, low temperature, humidity, PM2.5, VOC, CO₂, emergency heat and discovery rules. Source overrides are made directly from the sidebar Sensors tab and stored privately in `.storage`.

- Notification entity: `notify.*`, preferably your existing SMTP email family notifier. Defaults to a working notifier selected from the registry.
- Notification emails: enabled by default, with configurable subject prefix and retry interval. A failed send is queued and retried; attempts and service-accepted sends are visible in Incidents.
- Automatic source inclusion: enabled by default only for room-assigned and positively classified indoor measurement sources. Unknown areas are review candidates, not grouped together into an artificial room.
- Safety forwarding: disabled by default, and only enabled for individually included existing certified safety-alarm entities. No new smoke/CO/gas measurement is inferred from PM2.5/VOC values.

**History and privacy:** Only incident events and a compact PM2.5 sample cache are persisted in Home Assistant's private `.storage` (90-day event retention, maximum 5,000 events). Ordinary graphs come from Recorder and its long-term statistics; the panel does not manufacture history before retention or installation. Dashboard/WebSocket status is restricted to administrators.

## Dashboard

The sidebar panel offers Overview, Temperature, Humidity, PM2.5, VOC, CO₂, Emergencies, Incidents and Sensors tabs. Date controls offer current day, yesterday, current week/month/year, 48h, 7/30/90/365-day windows, 3 years, previous/next and custom ranges. Recorder's history/statistics are queried when opening a measurement tab. **For `climate` attribute sources, raw temperature history must be inspected in the original HA climate entity**; they do not appear as standalone numeric history series.

## Migration notes

- The latest **chat-provided** automations are the source of truth for the three basic alerts and the existing VOC family v2 policy.
- Useful ideas from older `home_assistant_sensor_alerts.yaml` are included as extra, configurable measures: high-temperature anomalies, severe humidity, CO₂ and optional certified-alarm forwarding.
- The older repository's daily-average PM2.5 and multi-level escalation logic were optional enhancements; daily reporting is **off** initially, while severity escalation is on.
- Leave Vaillant diagnostics, Device Availability Digest and smoke/CO/gas alarm automations independent. The custom integration is not a replacement for safety sensors.
- Emails are real if enabled and the `notify.*` entity works. There is **no dry-run mode by default**.

## Release hygiene

`custom_components/house_climate_monitor/manifest.json` contains a version `X.Y.Z`; `RELEASE_NOTES_X.Y.Z.md` matches it. CI `Validate` checks Python tests, JavaScript, JSON metadata, HACS and Home Assistant hassfest. Only after a **successful push validation on the current main-branch SHA** does `.github/workflows/release.yml` publish an actual `vX.Y.Z` GitHub Release. `hacs.json` has `hide_default_branch: true`, so HACS presents releases rather than `main` as an install option.

The repository must be created and the content pushed to `main` before the workflow can publish anything. See [PUBLISHING.md](PUBLISHING.md).

## Development/testing

```bash
python -m compileall -q custom_components tests
python -m unittest discover -s tests -p 'test_*.py' -v
node --input-type=module --check < custom_components/house_climate_monitor/www/managed-panel.js
node --input-type=module --check < custom_components/house_climate_monitor/www/panel-loader.js
```
