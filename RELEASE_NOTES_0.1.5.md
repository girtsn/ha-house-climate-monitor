# House Climate Monitor v0.1.5

## Fix: Home Assistant 2026.11 error unloading/reloading the integration

In v0.1.4, changing settings saved the new options but the automatic integration reload logged:

```text
AttributeError: 'ConfigEntry' object has no attribute 'async_unload_callbacks'
```

The integration's `async_unload_entry` erroneously called `entry.async_unload_callbacks()`, a method that is not part of Home Assistant's supported `ConfigEntry` API. Listeners were already registered properly using `entry.async_on_unload(...)`; Home Assistant runs these callbacks itself after a successful unload, or during setup failure.

- Remove the invalid manual callback invocation.
- Keep the existing graceful monitor-state save, monitoring stop and sidebar panel cleanup.
- Add regression tests simulating the public 2026.11 ConfigEntry API, including the absence of the invalid method; test correct unload results and lifecycle registration.
- Keep the `OptionsFlowWithReload` approach from v0.1.4; no duplicate update listener is restored.

Settings, history, alerts, source exclusions and email targets remain unchanged.

## Upgrade

Update to `v0.1.5` in HACS/Marketplace and restart Home Assistant, particularly if a previous options save left the config entry in failed-unload state. Then open **Settings → Devices & services → House Climate Monitor → Configure**, save the desired temperature settings (for example 17°C and 17.5°C), and confirm that no new `Error unloading entry` log is created.

The saved values from the previous submission may already be present; verify them rather than entering them again if correct.

Reference: https://contributors.home-assistant.io/core/quality-scale/config-entry-unloading/
