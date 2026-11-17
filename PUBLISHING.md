# Publishing House Climate Monitor as a release-based HACS repository

The new GitHub repository itself must exist before a GitHub Release can be published. The build package includes repository and CI contents; it does not create the GitHub repository or a live Home Assistant installation.

## One-time publishing procedure

1. Authenticate GitHub CLI locally with `gh auth login`, using an account allowed to create repositories under `girtsn`.
2. Extract the source ZIP and run the following inside its `ha-house-climate-monitor/` directory:

```bash
git init -b main
git add .
git commit -m "Initial House Climate Monitor v0.1.0"
gh repo create girtsn/ha-house-climate-monitor --public --source=. --remote=origin --push
```

3. Open the repository Settings → Actions → General and allow Actions to create and approve pull requests only if needed; **the release workflow needs Contents: read and write permission**, configured in the workflow. Ensure Actions are enabled.
4. Add GitHub repository topics including `home-assistant`, `hacs`, `home-assistant-custom-component` if HACS recommends them; remove the `ignore: topics` workaround afterward.
5. Watch GitHub **Actions → Validate**. Once its run for the current `main` commit is successful, **Publish validated House Climate Monitor release** will create `v0.1.0`. Check it appears under **Releases**, not just under Tags.
6. Add the GitHub URL as a custom **Integration** in HACS / Marketplace. Choose the published release (not `main`).

A failed CI run does not publish a release. On subsequent updates, increment both `manifest.json` version and release-notes filename, then push to `main`; the release workflow creates a matching release after validation.

## Manual installation before repository publication

Copy the `custom_components/house_climate_monitor/` folder to `/config/custom_components/house_climate_monitor/`, restart, and add the integration through Settings → Devices & services. This does not use HACS, so no GitHub Release is needed. Confirm which other climate automations are active before enabling new emails to avoid duplicates.
