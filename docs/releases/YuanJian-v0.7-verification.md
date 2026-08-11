# YuanJian v0.7 Verification

## Scope

- Action-center desktop redesign with four primary navigation groups.
- Server-side pagination and filtering for clusters, external radar and notifications.
- Historical and new feed text sanitized at trusted presentation/storage boundaries.
- Single and batch notification read actions.
- User-facing Chinese labels, local time formatting, non-blocking operation feedback and responsive layout.

## Compatibility and privacy

- Database schema remains unchanged from v0.6.
- Runtime remains loopback-only with per-launch API token protection.
- v0.5 and v0.6 packages are retained as rollback options.
- Source contains no private database, secrets, personal profile, Obsidian text or runtime cache.

## Automated verification

- Baseline before changes: 128 tests passed.
- Final release checkpoint: 145 tests passed in 43.874 seconds.
- The Windows loopback unauthorized-POST regression was repeated 10 times after the fix, with 10 passes.
- Privacy scan: `safe=True blocked=0 findings=0`.
- Targeted search for the private addresses, dates and financial figures supplied during planning: no match.

## Packaged desktop smoke

- Database initialization: passed.
- Loopback listeners: exactly one on `127.0.0.1`.
- Home response: HTTP 200.
- Remote scripts: none.
- Default view: `today` action center.
- Local judgment fallback: `local`.
- Second-instance guard: passed with exit code 0.
- Safe shutdown: returned `shutting_down` and the process exited.

## Real desktop acceptance

- All four primary navigation areas opened in the packaged pywebview window.
- Metric cards filtered the action center; notifications could be marked read.
- External-world results were paginated at 10 items per page and historical markup rendered as readable text.
- Source failures remained visible and distinct from “no news”.
- User-facing trend categories and source kinds were translated into Chinese labels.
- Closing the title-bar hid the window while monitoring continued; the same process restored its window successfully.
- The temporary acceptance database was isolated from the official runtime data and removed after verification.

## Release artifact

- Executable: `YuanJianApp-v0.7/YuanJian.exe`
- Size: 6,612,744 bytes.
- SHA-256: `ACF91E25926FDCD685689A41BDD48B6388F683A1984F9D61A8B23EDDB511A8DA`
