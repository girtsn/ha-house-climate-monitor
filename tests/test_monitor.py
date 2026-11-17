"""Notification service and rolling-average tests with small HA API stubs."""
import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace

SRC=Path(__file__).resolve().parents[1]/'custom_components'/'house_climate_monitor'


def stub_ha():
    home=types.ModuleType('homeassistant');home.__path__=[]
    helpers=types.ModuleType('homeassistant.helpers');helpers.__path__=[]
    storage=types.ModuleType('homeassistant.helpers.storage')
    util=types.ModuleType('homeassistant.util');util.__path__=[]
    dt=types.ModuleType('homeassistant.util.dt')
    class Store:
        def __init__(self,*args,**kwargs):self.saved={}
        async def async_save(self,data):self.saved=data
        async def async_load(self):return self.saved
    storage.Store=Store
    dt.as_local=lambda value:value.astimezone(timezone.utc)
    sys.modules.update({'homeassistant':home,'homeassistant.helpers':helpers,
                        'homeassistant.helpers.storage':storage,'homeassistant.util':util,
                        'homeassistant.util.dt':dt})
    pkg=types.ModuleType('climatestub');pkg.__path__=[str(SRC)]
    sys.modules['climatestub']=pkg

stub_ha()
monitor=importlib.import_module('climatestub.monitor')


class FakeServices:
    def __init__(self):self.calls=[];self.fail=False
    async def async_call(self,domain,service,data,*,target,blocking):
        if self.fail:raise RuntimeError('SMTP failed')
        self.calls.append((domain,service,data,target,blocking))


class FakeStates:
    def get(self,entity):return object() if entity=='notify.email_family' else None


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services=FakeServices()
        hass=SimpleNamespace(services=self.services,states=FakeStates())
        entry=SimpleNamespace(data={},options={},version=1)
        self.mon=monitor.ClimateMonitor(hass,entry)
        self.now=monitor.ts()
        self.event={"id":"r1","kind":"alert","key":"Kitchen|temp_low","room":"Kitchen",
                    "metric":"temp_low","level":"warning","when":datetime.now(timezone.utc).isoformat(),
                    "reason":"Low for 15 minutes", "implicated":["sensor.kitchen"],
                    "readings":[{"name":"Kitchen","value":16.7,"unit":"°C",
                                 "entity_id":"sensor.kitchen","fresh":True}],"peak":16.7}

    async def test_real_notify_service_is_called(self):
        self.mon._new_event(self.event)
        await self.mon._send_due(self.now)
        self.assertEqual(len(self.services.calls),1)
        d,service,data,target,blocking=self.services.calls[0]
        self.assertEqual((d,service),('notify','send_message'))
        self.assertEqual(target,{'entity_id':'notify.email_family'})
        self.assertIn('Kitchen',data['title'])
        self.assertIn('16.70',data['message'])
        self.assertFalse(self.mon.queue)
        self.assertTrue(any(e['kind']=='email_sent' for e in self.mon.history))

    async def test_retry_retains_failed_event_then_sends(self):
        self.mon._new_event(self.event)
        self.services.fail=True
        await self.mon._send_due(self.now)
        self.assertEqual(len(self.mon.queue),1)
        self.assertTrue(any(e['kind']=='email_failed' for e in self.mon.history))
        self.services.fail=False
        await self.mon._send_due(self.now+1)
        self.assertEqual(len(self.services.calls),0)
        await self.mon._send_due(self.now+301)
        self.assertEqual(len(self.services.calls),1)
        self.assertFalse(self.mon.queue)

    async def test_notification_toggle_suppresses_real_email(self):
        self.mon.options['notifications_enabled']=False
        self.mon._new_event(self.event)
        await self.mon._send_due(self.now)
        self.assertFalse(self.mon.queue)
        self.assertEqual(len(self.services.calls),0)
        self.assertTrue(any(e['kind']=='suppressed' for e in self.mon.history))

    def test_weighted_pm25_requires_coverage(self):
        now=100000.0
        rows=[[now-86400+i*3600,20.0] for i in range(24)]
        self.assertAlmostEqual(self.mon.pm24_average(rows,now),20.0)
        self.assertIsNone(self.mon.pm24_average(rows[-2:],now))

if __name__=='__main__':unittest.main()

class LegacyHumidityAlertMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services = FakeServices()
        hass = SimpleNamespace(services=self.services, states=FakeStates())
        self.mon = monitor.ClimateMonitor(hass, SimpleNamespace(data={}, options={}, version=1))
        self.now = monitor.ts()
        self.room = '2fl bathroom'
        self.bad = ['sensor.2fl_bathroom_2fl_vent_waves_humidity_static_maximum',
                    'sensor.2fl_bathroom_2fl_vent_waves_humidity_static_minimum']
        self.live = 'sensor.2fl_vent_waves_humidity'

    def _readings(self, live_value=54):
        from climatestub.discovery import Reading, CONFIGURATION_REASON
        # In the pre-fix build the 80% setting was included in the alert.
        return [
            Reading(self.live, 'Renson humidity', self.room, 'humidity', live_value, '%',
                    True, self.now, True, 'ambient relative humidity', True, 'sensor'),
            *[Reading(eid, eid, self.room, 'humidity', value, '%', True,
                      self.now, False, CONFIGURATION_REASON, False, 'sensor')
              for eid, value in zip(self.bad, [80, 75])]
        ]

    async def _refresh_with(self, readings):
        old = monitor.discover
        monitor.discover = lambda hass, overrides, options, now: readings
        try:
            await self.mon.refresh()
        finally:
            monitor.discover = old

    async def test_old_false_humidity_alert_is_retired_without_recovery_email(self):
        key = self.room + '|humidity'
        state = self.mon.rules._state(key)
        state.update(active=True, level='warning', implicated=list(self.bad),
                     peak=80, since=datetime.now(timezone.utc).isoformat(),
                     last_reason='humidity static maximum qualified for warning')
        fake = {'id': 'old-false', 'kind': 'alert', 'key': key, 'metric': 'humidity',
                'room': self.room, 'level': 'warning', 'reason': state['last_reason'],
                'implicated': list(self.bad), 'peak': 80,
                'when': datetime.now(timezone.utc).isoformat(),
                'readings': [{'entity_id': eid, 'value': 80} for eid in self.bad]}
        self.mon.queue = [{'event': fake, 'attempts': 0, 'next_retry': 0}]
        await self._refresh_with(self._readings())
        self.assertFalse(state['active'])
        self.assertFalse(self.mon.queue)
        self.assertFalse(self.services.calls)
        self.assertEqual([x['kind'] for x in self.mon.history if x['kind'] == 'retired'], ['retired'])
        self.assertTrue(any(x['kind'] == 'email_cancelled' for x in self.mon.history))
        self.assertFalse(any(x['kind'] == 'recovery' for x in self.mon.history))

    async def test_real_humidity_alert_remains_when_invalid_peak_source_removed(self):
        key = self.room + '|humidity'
        state = self.mon.rules._state(key)
        state.update(active=True, level='warning',
                     implicated=[self.live, self.bad[0]], peak=80,
                     since=datetime.now(timezone.utc).isoformat(),
                     last_reason='humidity static maximum qualified for warning')
        await self._refresh_with(self._readings(live_value=74))
        self.assertTrue(state['active'])
        self.assertEqual(state['implicated'], [self.live])
        self.assertEqual(state['peak'], 74)
        self.assertFalse(any(x['kind'] == 'recovery' for x in self.mon.history))
