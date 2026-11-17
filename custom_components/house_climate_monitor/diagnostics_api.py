"""Administrator-only WebSocket status and source override API."""
from __future__ import annotations

from datetime import datetime, timedelta
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from .const import DOMAIN


def _monitor(hass):
    return next(iter(hass.data.get(DOMAIN, {}).values()), None)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/status",
    vol.Optional("start_time"): str,
    vol.Optional("end_time"): str,
})
@websocket_api.require_admin
@callback
def ws_status(hass, connection, msg):
    monitor = _monitor(hass)
    if monitor is None:
        connection.send_error(msg["id"], "not_ready", "Climate Monitor is not loaded")
        return
    start, end = msg.get("start_time"), msg.get("end_time")
    if (start is None) != (end is None):
        connection.send_error(msg["id"], "invalid_range", "Start and end are both required")
        return
    if start is not None:
        try:
            a, b = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in (start, end)]
            if not a.tzinfo or not b.tzinfo or not a < b or b-a > timedelta(days=1099):
                raise ValueError("invalid range")
        except ValueError:
            connection.send_error(msg["id"], "invalid_range", "Use timezone-aware date/time range up to 3 years")
            return
    connection.send_result(msg["id"], monitor.status(start, end))


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/source",
    vol.Required("entity_id"): str,
    vol.Required("selection"): vol.In(["auto", "include", "exclude"]),
    vol.Optional("room"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_source(hass, connection, msg):
    monitor = _monitor(hass)
    if monitor is None:
        connection.send_error(msg["id"], "not_ready", "Climate Monitor is not loaded")
        return
    try:
        await monitor.set_source(msg["entity_id"], msg["selection"], msg.get("room"))
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_source", str(exc))
        return
    connection.send_result(msg["id"], {"saved": True})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/test_email"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_test_email(hass, connection, msg):
    """Send one test message only when requested by an HA administrator."""
    monitor = _monitor(hass)
    if monitor is None:
        connection.send_error(msg["id"], "not_ready", "Climate Monitor is not loaded")
        return
    try:
        recipient = await monitor.send_test_email()
    except Exception as exc:
        connection.send_error(msg["id"], "notification_failed", str(exc)[:250])
        return
    connection.send_result(msg["id"], {"accepted": True, "recipient": recipient})
