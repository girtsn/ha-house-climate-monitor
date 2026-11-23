# House Climate Monitor 0.1.6 — Correct HA-local calendar selections

- All calendar presets (Today, Yesterday, This week/month/year) use Home Assistant's configured timezone, rather than the browser's timezone.
- Home Assistant first weekday selection is respected, including Sunday-start locales.
- Exactly selected days use midnight-to-midnight, with an exclusive end and correct 23-/25-hour DST transitions.
- The custom date picker now allows an exact single-day selection by leaving the end date blank. An explicit end date is inclusive in the UI but converted to an exclusive boundary for Recorder queries.
- Dashboard date labels use the Home Assistant timezone, avoiding off-by-one dates when browsing from abroad.
- Rolling last N-hours/days presets remain rolling windows and existing sensor, alert and incident data is untouched.
- Regression tests cover Brussels dates, DST changes and Sunday-start weeks.

No history is rewritten and no climate-control operations are changed.
