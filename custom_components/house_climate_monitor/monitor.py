"""Persistent runtime, HA source reconciliation and real notification delivery."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import logging
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (DOMAIN, DEFAULTS, STORAGE_KEY, HISTORY_KEY, STORAGE_VERSION,
                    MAX_HISTORY, HISTORY_DAYS)
from .discovery import discover, CONFIGURATION_REASON
from .rules import IncidentRules

_LOGGER = logging.getLogger(__name__)


def ts() -> float:
    return datetime.now(timezone.utc).timestamp()


class ClimateMonitor:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.options = {**DEFAULTS, **entry.data, **entry.options}
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY, private=True, atomic_writes=True)
        self.history_store = Store(hass, STORAGE_VERSION, HISTORY_KEY, private=True, atomic_writes=True)
        self.rules = IncidentRules()
        self.overrides: dict[str, dict] = {}
        self.queue: list[dict] = []
        self.history: list[dict] = []
        self.readings = []
        self.pm_samples: dict[str, list[list[float]]] = {}
        self.daily_sent = ""
        self._lock = asyncio.Lock()
        self.running = True
        self.email_last_error: str | None = None
        self.last_delivery: str | None = None

    async def load(self):
        raw = await self.store.async_load() or {}
        self.overrides = raw.get("overrides", {})
        self.queue = raw.get("queue", [])
        self.rules = IncidentRules(raw.get("rules", {}))
        self.pm_samples = raw.get("pm_samples", {})
        self.daily_sent = raw.get("daily_sent", "")
        hist = await self.history_store.async_load() or {}
        self.history = hist.get("events", [])

    def record(self, event: dict):
        self.history.append(event)
        cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)
        self.history = [e for e in self.history[-MAX_HISTORY:]
                        if self._parse_event_date(e) >= cutoff]

    @staticmethod
    def _parse_event_date(e):
        try:
            return datetime.fromisoformat(e.get("when", "")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    async def save(self):
        await self.store.async_save({
            "rules": self.rules.snapshot(), "overrides": self.overrides,
            "queue": self.queue, "pm_samples": self.pm_samples,
            "daily_sent": self.daily_sent,
        })
        await self.history_store.async_save({"events": self.history})

    def _sample_pm(self, now: float):
        for r in self.readings:
            if r.metric != "pm25" or not r.selected or not r.fresh or r.value is None:
                continue
            rows = self.pm_samples.setdefault(r.entity_id, [])
            if not rows or r.reported > rows[-1][0]:
                rows.append([r.reported, r.value])
            # Preserve one checkpoint preceding 24h; cap memory per sensor.
            before = [i for i, row in enumerate(rows) if row[0] < now - 86400]
            cut = before[-1] if before else 0
            rows[:] = rows[cut:][-2000:]

    @staticmethod
    def pm24_average(rows: list[list[float]], now: float) -> float | None:
        """Time-weighted average, >=18h real coverage, no gaps longer than 2h."""
        points = sorted((float(t), float(v)) for t, v in rows if now-90000 <= t <= now)
        if len(points) < 2:
            return None
        start = now - 86400
        weighted = covered = 0.0
        for (t0, v0), (t1, _) in zip(points, points[1:]):
            if t1 <= start or t0 >= now:
                continue
            left, right = max(start, t0), min(now, t1)
            gap = t1-t0
            if gap <= 7200 and right > left:
                d = right-left
                covered += d
                weighted += d*v0
        # Treat recent last report as valid until now only for <=2h.
        last_t, last_v = points[-1]
        if last_t > start and 0 <= now-last_t <= 7200:
            d = now-last_t
            covered += d
            weighted += d*last_v
        if covered < 64800:
            return None
        return round(weighted/covered, 2)

    def _daily_pm(self, now: float):
        if not self.options.get("pm25_daily_enabled", False):
            return
        local = dt_util.as_local(datetime.fromtimestamp(now, timezone.utc))
        if local.hour < int(self.options.get("pm25_daily_hour", 20)):
            return
        key = local.date().isoformat()
        if key == self.daily_sent:
            return
        self.daily_sent = key
        limit = float(self.options.get("pm25_daily_threshold", 15))
        notices = []
        for r in self.readings:
            if r.metric != "pm25" or not r.selected:
                continue
            avg = self.pm24_average(self.pm_samples.get(r.entity_id, []), now)
            if avg is not None and avg > limit:
                notices.append({"room": r.room, "name": r.name, "value": avg,
                                "entity_id": r.entity_id})
        if notices:
            eid = f"daily:{key}"
            event = {
                "id": eid, "kind": "daily", "key": "Household|pm25_daily",
                "room": "Household", "metric": "pm25_daily", "level": "warning",
                "when": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "reason": f"24-hour PM2.5 average above {limit:g} µg/m³",
                "readings": [{"name": x["name"], "value": x["value"],
                              "unit": "µg/m³ (24h avg)", "entity_id": x["entity_id"],
                              "room": x["room"], "fresh": True} for x in notices],
                "implicated": [x["entity_id"] for x in notices], "peak": None,
            }
            self._new_event(event)

    def _new_event(self, event: dict):
        self.record(dict(event))
        if self.options.get("notifications_enabled", True):
            self.queue.append({"event": event, "attempts": 0, "next_retry": 0})
        else:
            self.record({"kind": "suppressed", "when": event["when"],
                         "id": event["id"], "reason": "Notifications disabled", "key": event["key"]})

    def _reconcile_excluded_sources(self, now: float):
        """Retire no-longer-selected sources before evaluating/sending alerts.

        Previously monitored HA entity values can become ineligible after an
        integration update (e.g. Renson humidity 'static maximum' settings).
        Removing them must not generate a fake room-recovery email or leave
        a pending false alert queued. We do not retire missing entities,
        because an absent/stale *physical* sensor is not proof of recovery.
        """
        excluded = {r.entity_id: r for r in self.readings if not r.selected}
        for eid, r in excluded.items():
            if r.reason == CONFIGURATION_REASON and self.overrides.get(eid, {}).get("selection") == "include":
                self.overrides[eid]["selection"] = "auto"
                self.record({
                    "kind": "source_excluded", "when": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                    "key": eid, "reason": f"Old include override neutralized: {CONFIGURATION_REASON}",
                })
            for event in self.rules.retire_source(
                eid, now, f"Monitoring source excluded: {r.reason}"
            ):
                self.record(event)
        # Prevent previously queued emails based on excluded entities from
        # arriving after a corrected version of the integration is installed.
        retained = []
        for item in self.queue:
            event = item.get("event", {})
            ids = set(event.get("implicated") or [])
            blocked = ids & excluded.keys()
            if not blocked:
                retained.append(item)
                continue
            remaining = ids - blocked
            if not remaining:
                self.record({
                    "kind": "email_cancelled",
                    "when": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                    "key": event.get("key", ""), "event_id": event.get("id"),
                    "reason": "Pending notification cancelled: all implicated sources were excluded",
                })
                continue
            # Retain genuine ongoing events, but never send misleading
            # thresholds, peaks or rows from now-excluded sources.
            event["implicated"] = sorted(remaining)
            event["readings"] = [row for row in event.get("readings", [])
                                 if row.get("entity_id") not in blocked]
            event["peak"] = None
            event["reason"] = "Alert continues for selected live sources; excluded readings were removed"
            retained.append(item)
        self.queue = retained

    async def refresh(self):
        if not self.running or self._lock.locked():
            return
        async with self._lock:
            now = ts()
            self.readings = discover(self.hass, self.overrides, self.options, now)
            self._reconcile_excluded_sources(now)
            self._sample_pm(now)
            for event in self.rules.evaluate(self.readings, self.options, now):
                self._new_event(event)
            self._daily_pm(now)
            await self._send_due(now)
            await self.save()

    async def _send_due(self, now: float):
        if not self.options.get("notifications_enabled", True):
            return
        recipient = str(self.options.get("notify_entity", ""))
        for item in list(self.queue)[:20]:
            if float(item.get("next_retry", 0)) > now:
                continue
            event = item["event"]
            title, message = format_email(event, self.options)
            try:
                # The selected notify entity actually sends the email. We track
                # only service completion, not confirmed mailbox delivery.
                if not recipient.startswith("notify.") or self.hass.states.get(recipient) is None:
                    raise ValueError(f"Configured notify entity {recipient!r} is not available")
                await self.hass.services.async_call(
                    "notify", "send_message", {"title": title, "message": message},
                    target={"entity_id": recipient}, blocking=True,
                )
            except Exception as exc:  # HA notify connectors can raise diverse exceptions.
                item["attempts"] += 1
                item["next_retry"] = now + max(1, int(self.options.get("email_retry_minutes", 5))) * 60
                self.email_last_error = str(exc)[:400]
                self.record({"kind": "email_failed", "when": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                             "key": event["key"], "event_id": event["id"],
                             "reason": self.email_last_error, "attempts": item["attempts"],
                             "recipient": recipient})
                _LOGGER.warning("Climate monitor notification failed: %s", exc)
            else:
                self.queue.remove(item)
                self.email_last_error = None
                self.last_delivery = datetime.fromtimestamp(now, timezone.utc).isoformat()
                self.record({"kind": "email_sent", "when": self.last_delivery,
                             "key": event["key"], "event_id": event["id"],
                             "reason": "Home Assistant notify service accepted call",
                             "recipient": recipient})

    async def send_test_email(self) -> str:
        """Explicit admin-requested email test; does not alter incidents."""
        recipient = str(self.options.get("notify_entity", ""))
        stamp = datetime.now(timezone.utc).isoformat()
        if not recipient.startswith("notify.") or self.hass.states.get(recipient) is None:
            raise ValueError("Configured notification entity is unavailable")
        try:
            await self.hass.services.async_call(
                "notify", "send_message",
                {"title": f"{self.options.get('subject_prefix', '[HASS Climate]')} TEST EMAIL",
                 "message": f"House Climate Monitor test message.\nTime (UTC): {stamp}\n"
                            "This test confirms Home Assistant accepted the notification service call; "
                            "verify arrival in your mailbox separately."},
                target={"entity_id": recipient}, blocking=True,
            )
        except Exception as exc:
            self.email_last_error = str(exc)[:400]
            self.record({"kind": "email_failed", "key": "test", "when": stamp,
                         "reason": self.email_last_error, "recipient": recipient})
            await self.save()
            raise
        self.email_last_error = None
        self.last_delivery = stamp
        self.record({"kind": "email_sent", "key": "test", "when": stamp,
                     "reason": "User-initiated test email accepted by Home Assistant notify service",
                     "recipient": recipient})
        await self.save()
        return recipient

    async def set_source(self, entity_id: str, selection: str, room: str | None):
        if selection not in {"auto", "include", "exclude"}:
            raise ValueError("Unknown selection")
        if not self.hass.states.get(entity_id):
            raise ValueError("Entity is not present in Home Assistant")
        if entity_id not in {r.entity_id for r in self.readings}:
            raise ValueError("Entity is not an identified climate/safety candidate")
        source = next((r for r in self.readings if r.entity_id == entity_id), None)
        if selection == "include" and source and source.reason == CONFIGURATION_REASON:
            raise ValueError("Configuration limits are not room measurements and cannot be monitored")
        if selection == "include" and source and source.metric == "voc_other":
            raise ValueError("Other VOC scales are display-only until a scale-specific alert rule is configured")
        data = {"selection": selection}
        if room:
            data["room"] = room.strip()[:96]
        # Changing eligibility/room invalidates a previously attributed incident.
        # Record an explicit administrative retirement, never a false recovery.
        previous = self.overrides.get(entity_id, {})
        if selection == "exclude" or (room and room != previous.get("room") and previous.get("room")):
            for event in self.rules.retire_source(entity_id, ts()):
                self.record(event)
        self.overrides[entity_id] = data
        await self.refresh()

    def status(self, start: str | None = None, end: str | None = None) -> dict:
        def include(e):
            when = e.get("when", "")
            return (start is None or when >= start) and (end is None or when <= end)
        return {
            "version": self.entry.version, "options": dict(self.options),
            "sources": [r.public() for r in self.readings], "overrides": dict(self.overrides),
            "incidents": {k: v for k, v in self.rules.states.items() if v.get("active")},
            "events": [e for e in self.history if include(e)][-MAX_HISTORY:],
            "email": {"pending": len(self.queue), "last_error": self.email_last_error,
                      "last_accepted": self.last_delivery,
                      "note": "Service acceptance does not confirm mailbox delivery"},
        }


def format_email(event: dict, options: dict) -> tuple[str, str]:
    metric = str(event.get("metric", "unknown"))
    label = {"temp_low": "LOW TEMPERATURE", "temp_high": "HIGH TEMPERATURE",
             "humidity": "HIGH HUMIDITY", "co2": "CO2 ELEVATED", "pm25": "PM2.5 HIGH",
             "pm25_daily": "24H PM2.5 AVERAGE", "voc": "VOC ELEVATION"}.get(metric, "EXISTING SAFETY ALARM" if metric.startswith("safety:") else metric.upper())
    kind = event.get("kind", "alert")
    status = {"alert": "ALERT", "escalation": "ESCALATION",
              "recovery": "RECOVERED", "daily": "DAILY REPORT"}.get(kind, kind.upper())
    room = event.get("room", "Unknown")
    level = event.get("level", "warning")
    title = f"{options.get('subject_prefix', '[HASS Climate]')} {status} {label} — {room}"
    rows = []
    for r in event.get("readings", []):
        val = r.get("value")
        formatted = f"{val:.2f}" if isinstance(val, (float, int)) else "unavailable"
        fresh = "" if r.get("fresh", True) else " [STALE/UNAVAILABLE]"
        rows.append(f"- {r.get('name', r.get('entity_id'))}: {formatted} {r.get('unit', '')}{fresh} ({r.get('entity_id')})")
    advice = {
        "temp_low": "Check heating schedule, windows and room sensors.",
        "temp_high": ("Potential abnormal heat. Check the room safely. If you suspect fire, "
                      "leave the building and call emergency services. This is NOT a fire detector."),
        "humidity": "Check ventilation, condensation and possible water intrusion.",
        "co2": "Check ventilation and occupancy. CO2 concentration is NOT a carbon-monoxide alarm.",
        "pm25": "Check cooking, smoke, candles and outdoor air before deciding on ventilation.",
        "voc": "Investigate indoor VOC sources. VOC index is not a gas/CO/fire alarm.",
        "pm25_daily": "Review prolonged particle sources and filtration.",
        "safety": "Follow the certified alarm instructions immediately. If fire or CO is suspected, evacuate and contact emergency services. Do not rely on email delivery.",
    }.get("safety" if metric.startswith("safety:") else metric, "Investigate the reported condition.")
    evidence_lines = []
    if metric == "voc":
        for _, detail in sorted(event.get("source_evidence", {}).items()):
            evidence_lines.append(
                f"- {detail.get('room', '')} / {detail.get('name', '')}: "
                f"first >= elevated index {detail.get('first_elevated', 'unknown')}; "
                f"peak index {detail.get('peak', 'unknown')} "
                f"at {detail.get('peak_at', 'unknown')}"
            )
    evidence_text = ("\nEPISODE PEAKS BY SENSOR\n" + "\n".join(evidence_lines) + "\n") if evidence_lines else ""
    message = (f"HOUSE CLIMATE MONITOR — {status}\n\n"
               f"Room: {room}\nMeasurement: {label}\nSeverity: {level}\n"
               f"Reason: {event.get('reason', '')}\n"
               f"When: {event.get('when', '')}\n"
               f"Original incident start: {event.get('since') or 'N/A'}\n"
               f"Peak/worst recorded: {event.get('peak') if event.get('peak') is not None else 'N/A'}\n\n"
               f"SENSOR READINGS\n" + "\n".join(rows) + "\n" + evidence_text + "\n" + advice +
               "\n\nNotification delivery is via Home Assistant's configured notify entity; "
               "successful service execution does not prove email arrival.")
    return title, message
