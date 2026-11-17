# House Climate Monitor v0.1.0

Initial beta implementation for local Home Assistant indoor environmental monitoring.

- HACS-compatible custom integration, UI configuration and options flow.
- Real `notify.send_message` email notifications, failed-call retry queue, and private restart-safe incident history.
- Automatically discover environmental sensors; explain eligibility and support include/exclude/room assignment in sidebar.
- Temperature low alerts (17.5°C/15 min), recovery (18°C/10 min), humidity (70%/60 min), PM2.5 (35µg/m³/30 min), severity tiers, and house-wide VOC monitoring, all configurable.
- New abnormal heat/rapid-rise advisories, indoor CO₂ warnings and optional forwarding of explicitly included existing smoke/CO/gas/heat alarm entities.
- A dedicated admin-only dashboard with Overview, Temperature, Humidity, PM2.5, VOC, CO₂, Emergencies, Incidents and Sensors tabs, date-range controls, and Home Assistant Recorder trends.
- Separate other-scale VOC readings (e.g. Renson) from IKEA VOC index thresholds.
- Optional daily PM2.5 24-hour average reporting (disabled by default until enabled by administrator).
- Added validation workflow and matching-release automation, with default-branch hiding in HACS metadata.

**Beta notice:** The pure monitoring state machine has unit tests; this release has not undergone live Home Assistant end-to-end testing and should not be relied on for emergency response. Please review discovered sources, test real email delivery, and keep certified smoke/CO alarms and existing safety automations enabled.
