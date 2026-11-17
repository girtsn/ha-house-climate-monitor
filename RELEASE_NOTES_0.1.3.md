# House Climate Monitor v0.1.3

## Fix: false bathroom humidity alerts caused by Renson Waves settings

Renson Waves exposes configurable humidity limits as numeric `sensor.*` entities. Values such as **static maximum 80%**, **static minimum 75%**, and **dynamic minimum 35%** are configuration parameters, **not live relative-humidity measurements**. Earlier versions mistakenly selected them because they had the `humidity` device class and `%` units.

- Automatically exclude environmental configuration limits and min/max setting entities from climate monitoring, regardless of prior Include overrides. The Sensors tab still lists them with an explicit exclusion reason; they cannot be re-enabled as live measurements.
- Continue monitoring genuine bathroom readings such as `sensor.1fl_vent_waves_humidity`, `sensor.2fl_vent_waves_humidity` and corresponding Tado humidity sensors.
- **Automatically reconcile existing false incidents on the first refresh after upgrading**, retiring any alert supported only by excluded settings. Record this as an administrative retirement, **not** a physical recovery, and do not send misleading recovery emails.
- Cancel stale queued notifications supported only by excluded sources. If a legitimate source also remains involved, retain the incident and omit nonphysical sources/peaks from queued evidence.
- Reset peaks potentially contaminated by excluded sources when a valid incident remains active. No need to recreate automations, edit YAML, or manually exclude individual Renson settings.
- Add unit and migration regression tests for real vs static/dynamic humidity values, forced Include overrides, false-incident retirement, pending-email cancellation, and mixed genuine/invalid incidents.

No change to configured alert thresholds or delivery settings. Already delivered emails cannot be recalled; the incident history will retain an explanatory retirement record.
