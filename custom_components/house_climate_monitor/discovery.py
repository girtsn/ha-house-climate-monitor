"""Conservative cross-home source discovery with explainable exclusions."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable
import re

NON_AMBIENT = (
    "outdoor", "outside", "yard motion", "garden", "outside yard", "sauna",
    "setpoint", "set_point", "target", "threshold", "effective", "dhw",
    "heating element", "towel dryer", "flow temperature", "flow_temp",
    "water heater", "boiler flow", "return temperature", "return_temp",
    "battery", "inverter", "cpu", "gpu", "drive ", "disk", "nas ",
    "syno_", "syno-", "unifi", "switch", "rackmount", "power supply",
    "server", "processor", "charging", "temp a", "temp b", "heatsink",
    "state of charge", "calibration", "history", "forecast", "limit",
    "heat pump compressor", "hot water", "pcb", "interface temperature",
    "24h", "24 hour", "average", "moving average", "statistics", "rolling",
)
# Some integrations (notably Renson Waves) publish configuration bounds as
# sensor.* entities with a humidity device class and '%' unit. These are NOT
# measurements and must never participate in monitoring, even if an old
# selection override explicitly included them.
CONFIGURATION_WORDS = {"minimum", "maximum", "min", "max", "threshold", "setpoint", "limit"}
CONFIGURATION_REASON = "configuration limit / min-max setting, not a live measurement"


def is_configuration_value(entity_id: str, name: str) -> bool:
    """Identify numeric configuration limits independent of device class/unit."""
    words = set(re.findall(r"[a-z0-9]+", f"{entity_id} {name}".lower()))
    return bool(CONFIGURATION_WORDS & words or {"set", "point"} <= words or {"upper", "bound"} <= words or {"lower", "bound"} <= words)


CO2_SAFETY = {"smoke", "carbon_monoxide", "gas", "heat"}
VALID_PM_UNITS = {"µg/m³", "μg/m³", "ug/m3", "µg/m3", "ug/m³"}


@dataclass
class Reading:
    entity_id: str
    name: str
    room: str
    metric: str
    value: float | None
    unit: str
    fresh: bool
    reported: float
    eligible: bool
    reason: str
    selected: bool
    source: str

    def public(self) -> dict[str, Any]:
        return asdict(self)


def classify(entity_id: str, name: str, attributes: dict) -> tuple[str | None, str]:
    """Return (metric, default eligibility reason); no guessing from raw VOC scales."""
    lower = (entity_id + " " + name).lower().replace("_", " ")
    dclass = str(attributes.get("device_class") or "").lower()
    unit = str(attributes.get("unit_of_measurement") or "")
    if entity_id.startswith("binary_sensor.") and dclass in CO2_SAFETY:
        return "safety", "safety alarm: opt-in forwarding only"
    if entity_id.startswith("climate."):
        if attributes.get("current_temperature") is None:
            return None, "no measured current temperature"
        if any(word in lower for word in NON_AMBIENT):
            return "temperature", "non-ambient device or setpoint"
        return "temperature", "climate current_temperature attribute"
    if not entity_id.startswith("sensor."):
        return None, "unsupported entity domain"
    # Do not infer live environmental values from units/device_class alone.
    # Keep invalid candidates visible in the Sources tab with an explanation.
    if is_configuration_value(entity_id, name):
        if "voc" in lower:
            return "voc_other", CONFIGURATION_REASON
        if dclass == "humidity" or "humidity" in lower:
            return "humidity", CONFIGURATION_REASON
        if dclass == "temperature" or "temperature" in lower or unit in {"°C", "°F"}:
            return "temperature", CONFIGURATION_REASON
        if dclass == "pm25" or "pm2_5" in lower or "pm25" in lower or "pm2.5" in lower:
            return "pm25", CONFIGURATION_REASON
        if dclass == "carbon_dioxide" or "co2" in lower:
            return "co2", CONFIGURATION_REASON
        return None, "configuration value without a climate measurement"
    if "voc" in lower:
        # Renson raw or estimated scales are not IKEA VOC indices.
        if "voc_index" in entity_id or "voc index" in lower or dclass == "volatile_organic_compounds_index":
            return "voc_index", "VOC index"
        return "voc_other", "other VOC scale: display only, not comparable"
    if dclass == "carbon_dioxide" or "co2" in entity_id.lower() or "carbon dioxide" in lower:
        if unit != "ppm":
            return "co2", "unexpected CO2 measurement unit"
        if any(word in lower for word in NON_AMBIENT):
            return "co2", "non-ambient device CO2"
        return "co2", "indoor carbon dioxide concentration"
    if dclass == "pm25" or "pm2_5" in entity_id or "pm25" in entity_id or "pm2.5" in lower:
        if unit not in VALID_PM_UNITS:
            return "pm25", "non-concentration PM2.5 unit"
        if any(word in lower for word in NON_AMBIENT):
            return "pm25", "derived or nonphysical particulate measurement"
        return "pm25", "PM2.5 concentration"
    if dclass == "humidity" or ("humidity" in lower and unit == "%"):
        if unit != "%":
            return "humidity", "unexpected humidity unit"
        if any(word in lower for word in NON_AMBIENT):
            return "humidity", "non-ambient or derived humidity"
        return "humidity", "ambient relative humidity"
    if dclass == "temperature" or unit in {"°C", "°F"} or "temperature" in lower:
        if unit not in {"°C", "°F"}:
            return "temperature", "non-temperature measurement unit"
        if any(word in lower for word in NON_AMBIENT):
            return "temperature", "non-ambient or equipment temperature"
        return "temperature", "ambient temperature"
    return None, "not an environmental measurement"


def is_default_eligible(metric: str, reason: str) -> bool:
    return metric in {"temperature", "humidity", "pm25", "voc_index", "co2"} and reason in {
        "ambient temperature", "ambient relative humidity", "PM2.5 concentration",
        "VOC index", "climate current_temperature attribute", "indoor carbon dioxide concentration",
    }


def safe_float(v: Any) -> float | None:
    try:
        if v is None or str(v).lower() in ("none", "unknown", "unavailable", "nan", "inf", "-inf"):
            return None
        result = float(v)
        return result if abs(result) < 1e7 else None
    except (TypeError, ValueError):
        return None


def convert_temperature(value: float | None, unit: str) -> float | None:
    if value is not None and unit == "°F":
        return (value - 32.0) * (5.0 / 9.0)
    return value


def room_for(hass, entity_id: str) -> str:
    """Resolve HA entity area, then device area; no inferred room on missing metadata."""
    from homeassistant.helpers import area_registry, device_registry, entity_registry
    reg = entity_registry.async_get(hass).async_get(entity_id)
    area_id = reg.area_id if reg else None
    if not area_id and reg and reg.device_id:
        dev = device_registry.async_get(hass).async_get(reg.device_id)
        area_id = dev.area_id if dev else None
    area = area_registry.async_get(hass).async_get_area(area_id) if area_id else None
    return area.name if area else "Unassigned"


def discover(hass, overrides: dict[str, dict], options: dict, now: float | None = None) -> list[Reading]:
    """Detect all plausible metrics; return included, excluded and review candidates."""
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    states = list(hass.states.async_all())
    by_id = {s.entity_id: s for s in states}
    discovered: list[Reading] = []
    for state in states:
        eid = state.entity_id
        attrs = state.attributes
        metric, reason = classify(eid, state.name or eid, attrs)
        if metric is None:
            continue
        room = room_for(hass, eid)
        override = overrides.get(eid, {})
        room = str(override.get("room") or room)
        eligible = is_default_eligible(metric, reason)
        # A generic outdoor sensor can have an indoor-looking entity ID.
        # Check HA Area names as well as entity and friendly names.
        room_words = {word.strip(' -_') for word in room.lower().replace('_', ' ').split()}
        if room_words.intersection({"outdoor", "outside", "garden", "yard", "balcony", "terrace", "patio"}):
            eligible, reason = False, "outdoor area (not an indoor-room reading)"
        if eid.startswith("climate."):
            # Tado exposes its measured room temperature as a sensor as well.
            mirror_id = "sensor." + eid.split(".", 1)[1] + "_temperature"
            if mirror_id in by_id:
                eligible, reason = False, "duplicate of " + mirror_id
        if room == "Unassigned" and not override.get("room"):
            eligible, reason = False, "no assigned HA area; assign a room to include"
        selection = override.get("selection", "auto")
        if selection == "exclude":
            selected, reason = False, "user excluded"
        elif selection == "include":
            selected, reason = True, "user included"
        else:
            selected = bool(options.get("auto_include", True)) and eligible
            if not options.get("auto_include", True) and eligible:
                reason = "awaiting manual inclusion"
        # Hard exclusion is intentional: the user may override an unusual
        # physical source, but cannot turn a fixed max/min threshold into a
        # room measurement. Old "include" overrides are safely neutralized.
        if eid.startswith("sensor.") and is_configuration_value(eid, state.name or eid):
            eligible, selected, reason = False, False, CONFIGURATION_REASON
        elif metric == "voc_other":
            selected = False
            if selection == "include":
                reason = "display only: source has no calibrated VOC-index rule"
        elif metric == "safety" and selection != "include":
            selected = False
        unit = str(attrs.get("unit_of_measurement") or "")
        raw = (None if state.state in ("unknown", "unavailable") else
               (attrs.get("current_temperature") if eid.startswith("climate.") else state.state))
        if metric == "safety":
            value = 1.0 if state.state == "on" else (0.0 if state.state == "off" else None)
        else:
            value = safe_float(raw)
            if metric == "temperature":
                value = convert_temperature(value, unit)
        last = getattr(state, "last_reported", None) or getattr(state, "last_updated", None)
        stamp = last.timestamp() if last else now
        freshness = max(1, int(options.get("freshness_minutes", 180))) * 60
        discovered.append(Reading(eid, str(state.name or eid), room, metric, value,
                                  "°C" if metric == "temperature" else unit,
                                  value is not None and (now-stamp <= freshness), stamp,
                                  eligible, reason, selected, eid.split(".", 1)[0]))
    return sorted(discovered, key=lambda r: (r.room, r.metric, r.name))
