# House Climate Monitor v0.1.7 — Honor Home Assistant time zone profile

- Native date selectors now follow **Settings → Profile → Time zone**:
  - **Use local time zone:** The time zone of the viewing browser/device (e.g. Riga while travelling).
  - **Use server time zone:** The Home Assistant installation's time zone (e.g. Europe/Brussels).
- All presets and custom calendar-date ranges convert civil calendar midnights to actual UTC instants, including 23- and 25-hour DST transition days.
- Changing the Home Assistant profile preference recalculates currently selected dates and reloads history without editing underlying measurements.
- Preserve existing one-day selection and optional blank end-date behavior.
- Regression tests cover Brussels vs Riga, local vs server, and DST transitions.
- No Recorder history, monitoring thresholds, notifications, or device settings are modified.

See the other custom integration releases made alongside this version for consistent date-picker behavior across the household.
