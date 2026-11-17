"""House Climate Monitor defaults; configuration is stored in HA UI/options."""
DOMAIN = "house_climate_monitor"
PANEL_PATH = "house-climate-monitor"
ASSET_PATH = "/house_climate_monitor"
STORAGE_KEY = "house_climate_monitor_state"
HISTORY_KEY = "house_climate_monitor_history"
STORAGE_VERSION = 1

DEFAULTS = {
    "notify_entity": "notify.email_family",
    "subject_prefix": "[HASS Climate]",
    "notifications_enabled": True,
    "auto_include": True,
    "temp_low_c": 17.5,
    "temp_low_minutes": 15,
    "temp_recovery_c": 18.0,
    "temp_recovery_minutes": 10,
    "humidity_high": 70.0,
    "humidity_minutes": 60,
    "humidity_recovery": 65.0,
    "humidity_recovery_minutes": 30,
    "humidity_severe": 90.0,
    "humidity_severe_minutes": 30,
    "co2_warning": 1500.0,
    "co2_warning_minutes": 30,
    "co2_severe": 2500.0,
    "co2_severe_minutes": 15,
    "co2_recovery": 1000.0,
    "co2_recovery_minutes": 30,
    "pm25_warning": 35.0,
    # Latest pasted YAML *executes* a 30-minute duration, despite its 15-minute description.
    "pm25_warning_minutes": 30,
    "pm25_severe": 150.0,
    "pm25_severe_minutes": 5,
    "pm25_extreme": 300.0,
    "pm25_extreme_minutes": 1,
    "pm25_recovery": 25.0,
    "pm25_recovery_minutes": 15,
    "voc_elevated_index": 200.0,
    "voc_severe_index": 350.0,
    "voc_severe_minutes": 30,
    "voc_multiroom_count": 3,
    "voc_multiroom_minutes": 10,
    "voc_recovery_minutes": 30,
    "temp_high_c": 45.0,
    "temp_high_minutes": 2,
    "temp_critical_c": 55.0,
    "temp_critical_minutes": 1,
    "temp_rapid_rise_c": 10.0,
    "temp_rapid_rise_minutes": 5,
    "temp_rapid_rise_min_c": 30.0,
    "temp_high_recovery_c": 38.0,
    "temp_high_recovery_minutes": 10,
    "safety_alarm_forwarding": False,
    "pm25_daily_enabled": False,
    "pm25_daily_threshold": 15.0,
    "pm25_daily_hour": 20,
    "freshness_minutes": 180,
    "email_retry_minutes": 5,
}

METRICS = ("temperature", "humidity", "pm25", "voc_index", "co2")
MAX_HISTORY = 5000
HISTORY_DAYS = 90
