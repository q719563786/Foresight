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
- Post-redesign release checkpoint: 145 tests passed in 48.057 seconds.
- Privacy scan: `safe=True blocked=0 findings=0`.
- Targeted search for the private addresses, dates and financial figures supplied during planning: no match.
- Package-path smoke, SHA-256 and real desktop acceptance are recorded after the versioned v0.7 build is produced.
