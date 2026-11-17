"""Configure House Climate Monitor through HA Devices & Services UI."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN, DEFAULTS


def _notify_selector():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="notify"))


def _number(current: dict, field: str, minimum: float = 1, maximum: float = 360, step: float = 1):
    return vol.Required(field, default=current.get(field, DEFAULTS[field])), selector.NumberSelector(
        selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX)
    )


def _bool(current: dict, field: str):
    return vol.Required(field, default=current.get(field, DEFAULTS[field])), selector.BooleanSelector()


class HouseClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            recipient = user_input["notify_entity"]
            if not self.hass.states.get(recipient):
                return self.async_show_form(step_id="user", data_schema=self._schema(),
                                            errors={"notify_entity": "notify_missing"})
            return self.async_create_entry(title="House Climate Monitor", data=user_input)
        return self.async_show_form(step_id="user", data_schema=self._schema())

    def _schema(self):
        available = [s.entity_id for s in self.hass.states.async_all("notify")]
        preferred = next((x for x in ("notify.email_family", "notify.email_girts") if x in available), None)
        preferred = preferred or (available[0] if available else DEFAULTS["notify_entity"])
        return vol.Schema({
            vol.Required("notify_entity", default=preferred): _notify_selector(),
            vol.Required("notifications_enabled", default=True): selector.BooleanSelector(),
            vol.Required("auto_include", default=True): selector.BooleanSelector(),
        })

    @staticmethod
    def async_get_options_flow(config_entry):
        return HouseClimateOptionsFlow()


class HouseClimateOptionsFlow(config_entries.OptionsFlowWithReload):
    def _settings(self):
        return {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=[
            "notifications", "temperature", "humidity", "particles", "voc", "co2", "emergency", "discovery"])

    async def _form(self, step_id, fields, user_input):
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema(dict(fields)))

    async def async_step_notifications(self, user_input=None):
        p = self._settings()
        return await self._form("notifications", [
            (vol.Required("notify_entity", default=p["notify_entity"]), _notify_selector()),
            _bool(p, "notifications_enabled"),
            (vol.Required("subject_prefix", default=p["subject_prefix"]), str),
            _number(p, "email_retry_minutes", 1, 120),
        ], user_input)

    async def async_step_temperature(self, user_input=None):
        p = self._settings()
        return await self._form("temperature", [
            _number(p, "temp_low_c", -30, 35, .5),
            _number(p, "temp_low_minutes", 1, 1440),
            _number(p, "temp_recovery_c", -30, 40, .5),
            _number(p, "temp_recovery_minutes", 1, 1440),
        ], user_input)

    async def async_step_humidity(self, user_input=None):
        p = self._settings()
        return await self._form("humidity", [
            _number(p, "humidity_high", 1, 100, 1),
            _number(p, "humidity_minutes", 1, 1440),
            _number(p, "humidity_recovery", 1, 100, 1),
            _number(p, "humidity_recovery_minutes", 1, 1440),
            _number(p, "humidity_severe", 1, 100, 1),
            _number(p, "humidity_severe_minutes", 1, 1440),
        ], user_input)

    async def async_step_particles(self, user_input=None):
        p = self._settings()
        return await self._form("particles", [
            _number(p, "pm25_warning", 1, 1000, 1),
            _number(p, "pm25_warning_minutes", 1, 240),
            _number(p, "pm25_severe", 1, 2000, 1),
            _number(p, "pm25_severe_minutes", 1, 240),
            _number(p, "pm25_extreme", 1, 3000, 1),
            _number(p, "pm25_extreme_minutes", 1, 240),
            _number(p, "pm25_recovery", 1, 1000, 1),
            _number(p, "pm25_recovery_minutes", 1, 240),
            _bool(p, "pm25_daily_enabled"),
            _number(p, "pm25_daily_threshold", 1, 500, 1),
            _number(p, "pm25_daily_hour", 0, 23),
        ], user_input)

    async def async_step_voc(self, user_input=None):
        p = self._settings()
        return await self._form("voc", [
            _number(p, "voc_elevated_index", 1, 500, 1),
            _number(p, "voc_severe_index", 1, 500, 1),
            _number(p, "voc_severe_minutes", 1, 240),
            _number(p, "voc_multiroom_count", 2, 30),
            _number(p, "voc_multiroom_minutes", 1, 240),
            _number(p, "voc_recovery_minutes", 1, 240),
        ], user_input)

    async def async_step_co2(self, user_input=None):
        p = self._settings()
        return await self._form("co2", [
            _number(p, "co2_warning", 400, 20000, 50),
            _number(p, "co2_warning_minutes", 1, 1440),
            _number(p, "co2_severe", 500, 20000, 50),
            _number(p, "co2_severe_minutes", 1, 1440),
            _number(p, "co2_recovery", 400, 20000, 50),
            _number(p, "co2_recovery_minutes", 1, 1440),
        ], user_input)

    async def async_step_emergency(self, user_input=None):
        p = self._settings()
        return await self._form("emergency", [
            _number(p, "temp_high_c", 25, 100, .5),
            _number(p, "temp_high_minutes", 1, 120),
            _number(p, "temp_critical_c", 25, 120, .5),
            _number(p, "temp_critical_minutes", 1, 120),
            _number(p, "temp_rapid_rise_c", 2, 60, .5),
            _number(p, "temp_rapid_rise_minutes", 1, 30),
            _number(p, "temp_rapid_rise_min_c", 20, 100, .5),
            _number(p, "temp_high_recovery_c", 20, 100, .5),
            _number(p, "temp_high_recovery_minutes", 1, 240),
            _bool(p, "safety_alarm_forwarding"),
        ], user_input)

    async def async_step_discovery(self, user_input=None):
        p = self._settings()
        return await self._form("discovery", [
            _bool(p, "auto_include"),
            _number(p, "freshness_minutes", 5, 10080),
        ], user_input)
