"""Pure incident engine regression checks: no HA runtime required."""
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC=Path(__file__).resolve().parents[1]/'custom_components'/'house_climate_monitor'
def load(name):
    spec=importlib.util.spec_from_file_location(name,SRC/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod
rules=load('rules')
discovery=load('discovery')

def r(entity,room,metric,value,fresh=True,reported=1,selected=True):
    return SimpleNamespace(entity_id=entity,name=entity,room=room,metric=metric,
                           value=value,fresh=fresh,reported=reported,selected=selected,unit='°C')

class RuleTests(unittest.TestCase):
    def test_temp_consolidation_and_recovery(self):
        m=rules.IncidentRules();p={}
        items=[r('sensor.a','Kitchen','temperature',17),r('sensor.b','Kitchen','temperature',17.3)]
        self.assertEqual(m.evaluate(items,p,1000),[])
        events=m.evaluate(items,p,1000+15*60+1)
        self.assertEqual([(e['kind'],e['key']) for e in events],[('alert','Kitchen|temp_low')])
        self.assertEqual(m.evaluate(items,p,1000+15*60+2),[])
        items[0].value=18.2;items[1].value=18.1
        self.assertEqual(m.evaluate(items,p,2000),[])
        self.assertEqual([e['kind'] for e in m.evaluate(items,p,2601)],['recovery'])
        self.assertEqual(m.evaluate(items,p,2700),[])

    def test_stale_affected_sensor_blocks_recovery(self):
        m=rules.IncidentRules();a=r('a','Kitchen','temperature',15);b=r('b','Kitchen','temperature',16)
        m.evaluate([a,b],{},1000);m.evaluate([a,b],{},1901)
        a.value=19;b.value=19;b.fresh=False
        self.assertEqual(m.evaluate([a,b],{},3000),[])
        self.assertEqual(m.evaluate([a,b],{},4000),[])
        b.fresh=True
        self.assertEqual(m.evaluate([a,b],{},4010),[])
        self.assertEqual([e['kind'] for e in m.evaluate([a,b],{},4620)],['recovery'])

    def test_restart_no_duplicate_email(self):
        m=rules.IncidentRules();item=r('a','Bedroom','humidity',85)
        m.evaluate([item],{},1000);self.assertEqual([e['kind'] for e in m.evaluate([item],{},4600)],['alert'])
        m2=rules.IncidentRules(m.snapshot())
        self.assertEqual(m2.evaluate([item],{},4700),[])
        item.value=64
        m2.evaluate([item],{},5000)
        self.assertEqual([e['kind'] for e in m2.evaluate([item],{},6801)],['recovery'])

    def test_pm_severity_escalation(self):
        m=rules.IncidentRules();item=r('a','Laundry','pm25',155)
        m.evaluate([item],{},1000)
        self.assertEqual([(e['kind'],e['level']) for e in m.evaluate([item],{},1301)],[('alert','severe')])
        item.value=350
        m.evaluate([item],{},1302)
        self.assertEqual([(e['kind'],e['level']) for e in m.evaluate([item],{},1363)],[('escalation','extreme')])
        self.assertEqual(m.evaluate([item],{},1400),[])

    def test_voc_distinct_rooms_and_recovery(self):
        m=rules.IncidentRules()
        items=[r('a','R1','voc_index',250),r('b','R1','voc_index',300),r('c','R2','voc_index',240)]
        m.evaluate(items,{},1000)
        self.assertEqual(m.evaluate(items,{},1700),[])
        items.append(r('d','R3','voc_index',210))
        m.evaluate(items,{},1701)
        self.assertEqual([(e['kind'],e['key']) for e in m.evaluate(items,{},2302)],[('alert','Household|voc')])
        for item in items:item.value=100
        self.assertEqual(m.evaluate(items,{},2400),[])
        self.assertEqual([e['kind'] for e in m.evaluate(items,{},4201)],['recovery'])

    def test_rapid_heat_and_recover(self):
        m=rules.IncidentRules()
        p={}
        a=r('a','Kitchen','temperature',22,reported=1000)
        m.evaluate([a],p,1000)
        a.value=35;a.reported=1120
        self.assertEqual([(e['kind'],e['level']) for e in m.evaluate([a],p,1120)],[('alert','severe')])

    def test_certified_alarm_forwarding_opt_in(self):
        m=rules.IncidentRules();a=r('binary_sensor.co','Hallway','safety',1)
        self.assertEqual(m.evaluate([a],{},1000),[])
        self.assertEqual([e['kind'] for e in m.evaluate([a],{'safety_alarm_forwarding':True},1001)],['alert'])
        a.value=0
        self.assertEqual([e['kind'] for e in m.evaluate([a],{'safety_alarm_forwarding':True},1002)],['recovery'])

    def test_classification_and_no_miscompare_voc(self):
        c=discovery.classify
        self.assertEqual(c('sensor.1fl_vent_waves_voc','Renson raw',{})[0],'voc_other')
        self.assertEqual(c('sensor.vindstyrka_voc_index','VOC',{})[0],'voc_index')
        self.assertIn('non-ambient',c('sensor.disk_temperature','NAS drive temperature',{'device_class':'temperature','unit_of_measurement':'°C'})[1])
        self.assertEqual(c('sensor.pm2_5','PM',{'device_class':'pm25','unit_of_measurement':'µg/m³'})[0],'pm25')

if __name__=='__main__':unittest.main()

class MoreRuleTests(unittest.TestCase):
    def test_old_sources_can_be_retired_without_fake_recovery(self):
        m=rules.IncidentRules();a=r('sensor.old','Kitchen','temperature',15)
        m.evaluate([a],{},1000);m.evaluate([a],{},1901)
        changes=m.retire_source(a.entity_id,1950)
        self.assertEqual([e['kind'] for e in changes],['retired'])
        self.assertFalse(m.states['Kitchen|temp_low']['active'])

    def test_humidity_severe_faster_than_mild_warning(self):
        m=rules.IncidentRules();a=r('humid','Bathroom','humidity',96)
        m.evaluate([a],{},1000)
        self.assertEqual([(e['kind'],e['level']) for e in m.evaluate([a],{},2801)],[('alert','severe')])

    def test_co2_and_clean_air(self):
        m=rules.IncidentRules();a=r('sensor.co2','Living','co2',2600)
        m.evaluate([a],{},1000)
        self.assertEqual([e['level'] for e in m.evaluate([a],{},1901)],['severe'])
        a.value=900
        m.evaluate([a],{},2000)
        self.assertEqual([e['kind'] for e in m.evaluate([a],{},3801)],['recovery'])

    def test_adjustable_threshold_and_confirmation(self):
        m=rules.IncidentRules();a=r('sensor.a','Bed','temperature',18)
        p={'temp_low_c':18.5,'temp_low_minutes':5}
        m.evaluate([a],p,1000)
        self.assertEqual(m.evaluate([a],p,1290),[])
        self.assertEqual([e['kind'] for e in m.evaluate([a],p,1301)],['alert'])

    def test_alarm_not_forwarded_without_explicit_selection(self):
        m=rules.IncidentRules();a=r('binary_sensor.smoke','Kitchen','safety',1,selected=False)
        self.assertEqual(m.evaluate([a],{'safety_alarm_forwarding':True},1000),[])

class DiscoveryTests(unittest.TestCase):
    def test_rolling_average_not_treated_as_live_pm_source(self):
        metric,reason=discovery.classify('sensor.pm25_24h_vindstyrka_3','24h PM2.5 average',
                         {'unit_of_measurement':'µg/m³','device_class':'pm25'})
        self.assertEqual(metric,'pm25')
        self.assertFalse(discovery.is_default_eligible(metric,reason))

    def test_tado_setpoint_is_not_room_measurement(self):
        m,reason=discovery.classify('sensor.tado_target_temperature','Tado target',
                      {'device_class':'temperature','unit_of_measurement':'°C'})
        self.assertFalse(discovery.is_default_eligible(m,reason))

    def test_fahrenheit_conversion(self):
        self.assertAlmostEqual(discovery.convert_temperature(68,'°F'),20)

class VOCEvidenceTests(unittest.TestCase):
    def test_recovery_contains_distinct_room_peaks_and_times(self):
        m=rules.IncidentRules();a=r('a','Kitchen','voc_index',230);b=r('b','Bedroom','voc_index',250);c=r('c','Hall','voc_index',210)
        m.evaluate([a,b,c],{},1000)
        a.value=300;m.evaluate([a,b,c],{},1060)
        first=m.evaluate([a,b,c],{},1661)
        self.assertEqual(first[0]['source_evidence']['a']['peak'],300)
        self.assertEqual(len(first[0]['source_evidence']),3)
        a.value=b.value=c.value=100
        m.evaluate([a,b,c],{},1800)
        recovered=m.evaluate([a,b,c],{},3601)
        self.assertEqual(recovered[0]['kind'],'recovery')
        self.assertEqual(recovered[0]['source_evidence']['a']['peak'],300)
        self.assertEqual(m.states['Household|voc']['source_evidence'],{})

class ConfigurationLimitDiscoveryTests(unittest.TestCase):
    def test_renson_humidity_bounds_are_not_measurements(self):
        cases = [
            ('sensor.1fl_bathroom_1fl_vent_waves_humidity_static_maximum', '1fl-vent-waves Humidity static maximum'),
            ('sensor.1fl_bathroom_1fl_vent_waves_humidity_static_minimum', '1fl-vent-waves Humidity static minimum'),
            ('sensor.2fl_bathroom_2fl_vent_waves_humidity_dynamic_minimum', '2fl-vent-waves Humidity dynamic minimum'),
            ('sensor.generic_humidity_max', 'Bedroom humidity max'),
        ]
        for entity, name in cases:
            with self.subTest(entity=entity):
                metric, reason = discovery.classify(entity, name, {'device_class': 'humidity', 'unit_of_measurement': '%'})
                self.assertEqual(metric, 'humidity')
                self.assertEqual(reason, discovery.CONFIGURATION_REASON)
                self.assertFalse(discovery.is_default_eligible(metric, reason))
        metric, reason = discovery.classify('sensor.2fl_vent_waves_humidity', '2fl-vent-waves Humidity',
                                             {'device_class': 'humidity', 'unit_of_measurement': '%'})
        self.assertEqual(metric, 'humidity')
        self.assertTrue(discovery.is_default_eligible(metric, reason))

    def test_user_override_cannot_force_monitoring_a_configuration_limit(self):
        from datetime import datetime, timezone
        states = [
            SimpleNamespace(entity_id='sensor.x_humidity_static_maximum',
                            name='Renson humidity static maximum',
                            state='80', attributes={'device_class': 'humidity', 'unit_of_measurement': '%'},
                            last_reported=datetime.now(timezone.utc)),
            SimpleNamespace(entity_id='sensor.x_humidity',
                            name='Renson humidity', state='54',
                            attributes={'device_class': 'humidity', 'unit_of_measurement': '%'},
                            last_reported=datetime.now(timezone.utc)),
        ]
        hass = SimpleNamespace(states=SimpleNamespace(async_all=lambda: states))
        original = discovery.room_for
        discovery.room_for = lambda h, e: 'Bathroom'
        try:
            found = discovery.discover(
                hass, {'sensor.x_humidity_static_maximum': {'selection': 'include'}},
                {'auto_include': True})
        finally:
            discovery.room_for = original
        by_id = {r.entity_id: r for r in found}
        self.assertFalse(by_id['sensor.x_humidity_static_maximum'].selected)
        self.assertTrue(by_id['sensor.x_humidity'].selected)
