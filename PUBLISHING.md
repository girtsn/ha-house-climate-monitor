# Publishing and installing House Climate Monitor

Repository: https://github.com/girtsn/ha-house-climate-monitor

## Automated release process

The `main` branch contains the reusable Home Assistant integration. Every push runs `.github/workflows/validate.yaml`, which checks Python and JavaScript, isolated tests, HACS compliance and Home Assistant hassfest. `.github/workflows/release.yml` triggers only after a successful validation run for the current `main` commit. It reads the version from `custom_components/house_climate_monitor/manifest.json` and creates a matching GitHub Release (`vX.Y.Z`) with `RELEASE_NOTES_X.Y.Z.md`.

The file `hacs.json` contains `hide_default_branch: true` so HACS users select the published release, not `main`. Each future version change should update the manifest version and add matching release notes. Do not modify an existing published release/tag in place.

## HACS installation — no manual configuration YAML

1. In Home Assistant HACS / Marketplace add `https://github.com/girtsn/ha-house-climate-monitor` as a **custom integration** repository.
2. Install the newest **published GitHub Release**, then restart Home Assistant.
3. In **Settings → Devices & Services → Add integration**, select **House Climate Monitor** and choose an existing email-capable `notify.*` entity (such as `notify.email_family`).
4. Use the automatically registered **Climate Monitor** sidebar dashboard to review discovered sensors, exclude irrelevant entities and assign rooms to unmapped sources. Use **Send test email** on the Overview tab and confirm actual delivery to the mailbox.
5. Adjust thresholds, persistence periods and recipient via **Configure** in Devices & Services. When confirmed operational, disable the overlapping old environmental *email* automations to prevent duplicate messages. Keep smoke/CO/gas safety alarms and separate diagnostic integrations enabled.

The custom integration owns its runtime, sensor discovery, incident and recovery state, email queue, dashboard assets and private persistence; no manual YAML, helper entities or dashboard cards are necessary. Existing Home Assistant notification entities are external prerequisites; the integration does not configure SMTP itself.

## Validation and limitations

A green CI run means the static checks and isolated tests passed. End-to-end behavior and email delivery must still be checked in the user's Home Assistant. This software is **not a certified fire, smoke, carbon-monoxide or gas detector**. Do not use it as the primary emergency alert system.