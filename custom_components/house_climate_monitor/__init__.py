"""Monitor existing HA measurements, no direct device access or cloud polling."""
from __future__ import annotations

from datetime import timedelta
import json
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, PANEL_PATH, ASSET_PATH
from .discovery import classify
from .monitor import ClimateMonitor
from .diagnostics_api import ws_status, ws_source, ws_test_email

_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    root = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths([
        StaticPathConfig(f"{ASSET_PATH}/assets/{VERSION}/panel-loader.js", str(root / "panel-loader.js"), cache_headers=False),
        StaticPathConfig(f"{ASSET_PATH}/assets/{VERSION}/managed-panel.js", str(root / "managed-panel.js"), cache_headers=False),
    ])
    websocket_api.async_register_command(hass, ws_status)
    websocket_api.async_register_command(hass, ws_source)
    websocket_api.async_register_command(hass, ws_test_email)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    monitor = ClimateMonitor(hass, entry)
    await monitor.load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = monitor
    await monitor.refresh()

    @callback
    def on_state(event):
        eid = event.data.get("entity_id", "")
        if not eid.startswith(("sensor.", "climate.", "binary_sensor.")):
            return
        new = event.data.get("new_state")
        if new is None:
            return
        metric, _ = classify(eid, new.name or eid, new.attributes)
        if metric is not None and monitor.running:
            hass.async_create_task(monitor.refresh())

    @callback
    def on_tick(_now):
        hass.async_create_task(monitor.refresh())

    entry.async_on_unload(hass.bus.async_listen(EVENT_STATE_CHANGED, on_state))
    entry.async_on_unload(async_track_time_interval(hass, on_tick, timedelta(seconds=60)))
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    if not frontend.async_panel_exists(hass, PANEL_PATH):
        try:
            await panel_custom.async_register_panel(
                hass, frontend_url_path=PANEL_PATH,
                webcomponent_name="house-climate-monitor-loader",
                sidebar_title="Climate Monitor", sidebar_icon="mdi:home-thermometer",
                module_url=f"{ASSET_PATH}/assets/{VERSION}/panel-loader.js",
                config={"integration_version": VERSION}, require_admin=True,
            )
        except (ValueError, RuntimeError):
            _LOGGER.exception("Could not register Climate Monitor sidebar")
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    monitor = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if monitor:
        monitor.running = False
        await monitor.save()
    entry.async_unload_callbacks()
    if frontend.async_panel_exists(hass, PANEL_PATH):
        frontend.async_remove_panel(hass, PANEL_PATH)
    return True
