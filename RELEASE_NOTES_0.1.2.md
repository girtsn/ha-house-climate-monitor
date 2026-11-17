# House Climate Monitor v0.1.2

## Explain active room alerts with individual sensor evidence

- Active incident cards now display the **current reading**, entity ID, freshness, and incident participation for every selected sensor in the room.
- Show the source that qualified for the warning, the **historical peak** (which is not necessarily current), recovery thresholds, pending confirmation start, and any sensor still blocking recovery.
- Highlight humidity sensor disagreements of 15 percentage points or more (for example Tado versus Renson Waves), without arbitrarily choosing a device or suppressing an alert.
- Clarify that recovery is established against the individual selected sources, **not their average**.
- Add a pure diagnostic function and Node tests for conflicting readings, fresh/stale affected sources, and recovery blockers.

No humidity thresholds or existing incident states have been changed. Alerts continue to require >70% sustained for the configured interval, with all selected readings <=65% for the configured recovery interval by default. Existing incidents and notification settings are preserved.

This display improvement does **not** determine which of two conflicting physical sensors is correct. Compare the current values and their installation positions before excluding or calibrating a source.
