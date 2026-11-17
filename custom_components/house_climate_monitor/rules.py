"""Pure, restart-serializable per-room incident state machine.

No Home Assistant imports: the same engine is exercised in CI tests.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

LEVEL_RANK = {"warning": 1, "severe": 2, "extreme": 3, "critical": 4}


def config(options: dict, key: str, fallback: float) -> float:
    try:
        return float(options.get(key, fallback))
    except (ValueError, TypeError):
        return float(fallback)


class IncidentRules:
    def __init__(self, snapshot: dict | None = None):
        snapshot = snapshot or {}
        self.states: dict[str, dict] = snapshot.get("states", {})
        self.samples: dict[str, list[list[float]]] = snapshot.get("samples", {})
        self.multi_since = snapshot.get("multi_since")

    def snapshot(self) -> dict:
        return {"states": self.states, "samples": self.samples,
                "multi_since": self.multi_since}

    def _state(self, key: str) -> dict:
        return self.states.setdefault(key, {
            "active": False, "level": "", "pending": {}, "recovery_since": None,
            "implicated": [], "peak": None, "since": None, "last_reason": "",
            "last_event": None, "source_evidence": {}, "voc_idle_since": None,
        })

    def _hold(self, entry: dict, token: str, active: bool, now: float, seconds: float) -> bool:
        pending = entry["pending"]
        if not active:
            pending.pop(token, None)
            return False
        if token not in pending or float(pending[token]) > now:
            pending[token] = now
        return now - float(pending[token]) >= seconds

    def _details(self, items: list, now: float) -> list[dict]:
        return [
            {"entity_id": r.entity_id, "name": r.name, "value": r.value,
             "unit": r.unit, "fresh": r.fresh, "reported": r.reported,
             "room": r.room}
            for r in items
        ]

    def _event(self, kind: str, key: str, entry: dict, level: str, items: list,
               now: float, reason: str) -> dict:
        return {
            "id": f"{key}:{kind}:{int(now*1000)}", "kind": kind, "key": key,
            "room": key.rsplit("|", 1)[0], "metric": key.rsplit("|", 1)[-1],
            "level": level, "when": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "since": entry.get("since"), "reason": reason,
            "peak": entry.get("peak"), "implicated": list(entry["implicated"]),
            "readings": self._details(items, now),
            "source_evidence": deepcopy(entry.get("source_evidence", {})) if key.endswith("|voc") else {},
        }

    def _check_group(self, key: str, items: list, options: dict, now: float) -> list[dict]:
        entry = self._state(key)
        metric = key.split("|")[-1]
        valid = [r for r in items if r.selected and r.fresh and r.value is not None]
        selected = [r for r in items if r.selected]
        fired: list[tuple[str, str, object]] = []
        in_breach: list = []
        if metric == "temp_low":
            limit = config(options, "temp_low_c", 17.5)
            recover = config(options, "temp_recovery_c", 18)
            recovery_minutes = config(options, "temp_recovery_minutes", 10)
            levels = [("warning", "temp_low_minutes", 15, lambda v: v < limit)]
            recovered = lambda v: v >= recover
        elif metric == "humidity":
            limit = config(options, "humidity_high", 70)
            recover = config(options, "humidity_recovery", 65)
            recovery_minutes = config(options, "humidity_recovery_minutes", 30)
            levels = [("warning", "humidity_minutes", 60, lambda v: v > limit),
                      ("severe", "humidity_severe_minutes", 30, lambda v: v > config(options, "humidity_severe", 90))]
            recovered = lambda v: v <= recover
        elif metric == "co2":
            recover = config(options, "co2_recovery", 1000)
            recovery_minutes = config(options, "co2_recovery_minutes", 30)
            levels = [
                ("warning", "co2_warning_minutes", 30, lambda v: v > config(options, "co2_warning", 1500)),
                ("severe", "co2_severe_minutes", 15, lambda v: v > config(options, "co2_severe", 2500)),
            ]
            recovered = lambda v: v <= recover
        elif metric == "pm25":
            recover = config(options, "pm25_recovery", 25)
            recovery_minutes = config(options, "pm25_recovery_minutes", 15)
            levels = [
                ("warning", "pm25_warning_minutes", 30, lambda v: v > config(options, "pm25_warning", 35)),
                ("severe", "pm25_severe_minutes", 5, lambda v: v > config(options, "pm25_severe", 150)),
                ("extreme", "pm25_extreme_minutes", 1, lambda v: v > config(options, "pm25_extreme", 300)),
            ]
            recovered = lambda v: v <= recover
        elif metric == "temp_high":
            recover = config(options, "temp_high_recovery_c", 38)
            recovery_minutes = config(options, "temp_high_recovery_minutes", 10)
            levels = [
                ("warning", "temp_high_minutes", 2, lambda v: v >= config(options, "temp_high_c", 45)),
                ("critical", "temp_critical_minutes", 1, lambda v: v >= config(options, "temp_critical_c", 55)),
            ]
            recovered = lambda v: v <= recover
        else:
            return []
        valid_ids = {r.entity_id for r in valid}
        for r in selected:
            good = r.entity_id in valid_ids
            if good and any(predicate(r.value) for _, _, _, predicate in levels):
                in_breach.append(r)
            for level, minutes_key, fallback, predicate in levels:
                active = good and predicate(r.value)
                if self._hold(entry, f"{r.entity_id}:{level}", active, now,
                              config(options, minutes_key, fallback) * 60):
                    fired.append((level, r.entity_id, r))
        events = []
        if metric == "temp_high":
            # An observed rapid rise is an additional advisory, not certified fire detection.
            delta = config(options, "temp_rapid_rise_c", 10)
            minutes = config(options, "temp_rapid_rise_minutes", 5)
            floor = config(options, "temp_rapid_rise_min_c", 30)
            for r in valid:
                rows = self.samples.setdefault("heat:" + r.entity_id, [])
                if not rows or r.reported > rows[-1][0]:
                    rows.append([r.reported, r.value])
                rows[:] = [x for x in rows if now - x[0] <= max(300, minutes * 60)]
                previous = [x for x in rows[:-1] if r.reported-x[0] <= minutes*60]
                if previous and r.value >= floor and r.value-min(x[1] for x in previous) >= delta:
                    fired.append(("severe", r.entity_id, r))
        current_bad_ids = [r.entity_id for r in in_breach]
        if entry["active"]:
            entry["implicated"] = sorted(set(entry["implicated"]) | set(current_bad_ids))
        if in_breach:
            values = [r.value for r in in_breach]
            extreme = min(values) if metric == "temp_low" else max(values)
            if entry["peak"] is None:
                entry["peak"] = extreme
            else:
                entry["peak"] = min(entry["peak"], extreme) if metric == "temp_low" else max(entry["peak"], extreme)
        if fired:
            level, eid, r = max(fired, key=lambda x: LEVEL_RANK[x[0]])
            reason = f"{r.name} qualified for {level}"
            if not entry["active"]:
                entry.update(active=True, level=level, since=datetime.fromtimestamp(now, timezone.utc).isoformat(),
                             implicated=sorted(set(current_bad_ids + [eid])), last_reason=reason,
                             recovery_since=None)
                events.append(self._event("alert", key, entry, level, selected, now, reason))
            elif LEVEL_RANK[level] > LEVEL_RANK.get(entry["level"], 0):
                entry.update(level=level, recovery_since=None, last_reason=reason)
                events.append(self._event("escalation", key, entry, level, selected, now, reason))
        if entry["active"]:
            by_id = {r.entity_id: r for r in valid}
            previously_affected_reporting = all(eid in by_id for eid in entry["implicated"])
            all_valid_normal = bool(valid) and all(recovered(r.value) for r in valid)
            if previously_affected_reporting and all_valid_normal and not in_breach:
                if entry["recovery_since"] is None:
                    entry["recovery_since"] = now
                if now - entry["recovery_since"] >= recovery_minutes*60:
                    events.append(self._event("recovery", key, entry, entry["level"], selected, now,
                                              f"Confirmed normal for {recovery_minutes:g} min"))
                    entry.update(active=False, level="", pending={}, recovery_since=None,
                                 implicated=[], peak=None, since=None, last_reason="")
            else:
                entry["recovery_since"] = None
        return events

    def _voc(self, items: list, options: dict, now: float) -> list[dict]:
        key = "Household|voc"
        entry = self._state(key)
        valid = [r for r in items if r.selected and r.fresh and r.value is not None]
        selected = [r for r in items if r.selected]
        high_limit = config(options, "voc_severe_index", 350)
        low_limit = config(options, "voc_elevated_index", 200)
        elevated_rooms = {r.room for r in valid if r.value >= low_limit and r.room != "Unassigned"}
        elevated = [r for r in valid if r.value >= low_limit]
        source_evidence = entry.setdefault("source_evidence", {})
        stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
        for reading in elevated:
            evidence = source_evidence.setdefault(reading.entity_id, {
                "name": reading.name, "room": reading.room, "first_elevated": stamp,
                "peak": reading.value, "peak_at": stamp,
            })
            if reading.value > evidence["peak"]:
                evidence["peak"] = reading.value
                evidence["peak_at"] = stamp
            evidence["last_elevated"] = stamp
        if not elevated and not entry.get("active"):
            if entry.get("voc_idle_since") is None:
                entry["voc_idle_since"] = now
            if now - entry["voc_idle_since"] >= config(options, "voc_recovery_minutes", 30) * 60:
                entry["source_evidence"] = {}
                entry["peak"] = None
        else:
            entry["voc_idle_since"] = None
        confirmed_severe = []
        for r in selected:
            if self._hold(entry, "severe:" + r.entity_id, r in valid and r.value > high_limit,
                          now, config(options, "voc_severe_minutes", 30)*60):
                confirmed_severe.append(r)
        enough = len(elevated_rooms) >= int(config(options, "voc_multiroom_count", 3))
        if not enough:
            self.multi_since = None
        elif self.multi_since is None or self.multi_since > now:
            self.multi_since = now
        multi = enough and self.multi_since is not None and now-self.multi_since >= config(options, "voc_multiroom_minutes", 10)*60
        reason = "Severe individual VOC index" if confirmed_severe else "Elevated VOC in multiple rooms"
        events = []
        if elevated:
            peak = max(r.value for r in elevated)
            entry["peak"] = max(entry["peak"] or peak, peak)
        if entry["active"]:
            entry["implicated"] = sorted(set(entry["implicated"]) | {r.entity_id for r in elevated})
        if (confirmed_severe or multi) and not entry["active"]:
            entry.update(active=True, level="severe" if confirmed_severe else "warning",
                         since=datetime.fromtimestamp(now, timezone.utc).isoformat(),
                         implicated=sorted({r.entity_id for r in elevated}),
                         recovery_since=None, last_reason=reason)
            events.append(self._event("alert", key, entry, entry["level"], selected, now, reason))
        elif confirmed_severe and entry["active"] and entry["level"] == "warning":
            entry.update(level="severe", last_reason=reason)
            events.append(self._event("escalation", key, entry, "severe", selected, now, reason))
        if entry["active"]:
            valid_by_id = {r.entity_id: r for r in valid}
            cleared = (not elevated and all(eid in valid_by_id and valid_by_id[eid].value < low_limit
                                             for eid in entry["implicated"]))
            if cleared:
                if entry["recovery_since"] is None:
                    entry["recovery_since"] = now
                minutes = config(options, "voc_recovery_minutes", 30)
                if now-entry["recovery_since"] >= minutes*60:
                    events.append(self._event("recovery", key, entry, entry["level"], selected, now,
                                              "VOC readings cleared for sustained recovery window"))
                    entry.update(active=False, level="", pending={}, recovery_since=None,
                                 implicated=[], peak=None, since=None, last_reason="",
                                 source_evidence={}, voc_idle_since=None)
                    self.multi_since = None
            else:
                entry["recovery_since"] = None
        return events

    def _safety(self, items: list, now: float) -> list[dict]:
        events = []
        for r in items:
            if not r.selected:
                continue
            key = f"{r.room}|safety:{r.entity_id}"
            entry = self._state(key)
            if not r.fresh or r.value is None:
                continue
            if r.value == 1 and not entry["active"]:
                entry.update(active=True, level="critical", since=datetime.fromtimestamp(now, timezone.utc).isoformat(),
                             implicated=[r.entity_id], peak=1, last_reason="Existing safety alarm triggered")
                events.append(self._event("alert", key, entry, "critical", [r], now, entry["last_reason"]))
            elif r.value == 0 and entry["active"]:
                events.append(self._event("recovery", key, entry, "critical", [r], now,
                                          "Existing safety alarm reports clear"))
                entry.update(active=False, level="", since=None, peak=None, implicated=[], pending={})
        return events

    def retire_source(self, entity_id: str, now: float, reason: str = "Administrator changed source selection") -> list[dict]:
        """Reset source evidence without falsely claiming measured recovery."""
        events = []
        for key, entry in self.states.items():
            entry["pending"] = {name: when for name, when in entry.get("pending", {}).items()
                                 if not name.startswith((entity_id + ":", "severe:" + entity_id))}
            if not entry.get("active") or entity_id not in entry.get("implicated", []):
                continue
            entry["implicated"] = [eid for eid in entry["implicated"] if eid != entity_id]
            entry["recovery_since"] = None
            if entry["implicated"]:
                # The old peak may have come solely from the removed source;
                # never keep presenting that peak as a physical reading.
                entry["peak"] = None
                entry["last_reason"] = reason
                entry.get("source_evidence", {}).pop(entity_id, None)
            if not entry["implicated"]:
                events.append(self._event("retired", key, entry, entry["level"], [], now, reason))
                entry.update(active=False, level="", peak=None, since=None,
                             implicated=[], pending={}, last_reason="")
        self.samples.pop("heat:" + entity_id, None)
        return events

    def evaluate(self, readings: list, options: dict, now: float) -> list[dict]:
        groups: dict[tuple[str, str], list] = defaultdict(list)
        by_voc: list = []
        by_safety: list = []
        for r in readings:
            if r.metric in {"temperature", "humidity", "pm25", "co2"}:
                metric = {"temperature": "temp_low", "humidity": "humidity", "pm25": "pm25", "co2": "co2"}[r.metric]
                groups[(r.room, metric)].append(r)
                if r.metric == "temperature":
                    groups[(r.room, "temp_high")].append(r)
            elif r.metric == "voc_index":
                by_voc.append(r)
            elif r.metric == "safety":
                by_safety.append(r)
        events = []
        for (room, metric), items in groups.items():
            if any(r.selected for r in items):
                events.extend(self._check_group(f"{room}|{metric}", items, options, now))
        events.extend(self._voc(by_voc, options, now))
        if options.get("safety_alarm_forwarding", False):
            events.extend(self._safety(by_safety, now))
        return events
