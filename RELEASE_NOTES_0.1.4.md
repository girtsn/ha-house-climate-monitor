# House Climate Monitor v0.1.4

## Fix: "Unknown error occurred" when saving options

Saving any options page (including Low temperature and recovery) failed because House Climate Monitor simultaneously:
- extended Home Assistant's `OptionsFlowWithReload` (automatically reloads after saving), and
- registered a separate config-entry update listener which reloaded the same integration.

Recent Home Assistant rejects this combination with `ValueError: Config entry update listeners should not be used with OptionsFlowWithReload`. The problem is **not** caused by entering a decimal such as 17.5 or 17,5.

This release removes the redundant update listener and its reload helper. Home Assistant now uses the supported `OptionsFlowWithReload` pathway exclusively. No changes to monitoring, user-selected sensors, threshold defaults, notifications or incident storage.

Regression tests verify the exclusivity of the two reload mechanisms and that the form merges submitted temperature options into existing settings without losing unrelated options.

### Upgrade

Install v0.1.4 through Home Assistant HACS/Marketplace and restart Home Assistant. Open Settings → Devices & services → House Climate Monitor → Configure → Low temperature and recovery. You can then set **17.0°C** cold threshold and **17.5°C** recovery threshold, retaining 15/10-minute confirmation intervals.

Source: https://contributors.home-assistant.io/core/integrations/options-flow/
