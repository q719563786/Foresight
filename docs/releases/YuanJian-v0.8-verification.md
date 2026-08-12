# YuanJian v0.8 verification

Verified on 2026-08-12 on Windows 10 with the packaged pywebview desktop build.

## User experience

- The primary navigation contains only Risk Home, My Situation, and Settings.
- Risk Home is the default and shows one overall state, three workload counts, and at most five personal risk cards.
- Each card states the affected interest, time window, confidence, direction, and current action.
- The action detail keeps evidence collapsed by default. Evidence appears only after the user asks why the judgment was made.
- Raw intelligence is absent from daily navigation. It is available only through Settings, Intelligence Back Office, and View Raw Intelligence.
- Closing the window removes the window while the process and loopback API keep running in the tray.

## Automated verification

- Full suite: 152 tests passed in 41.537 seconds.
- JavaScript syntax check: passed.
- Packaged smoke: loopback only, local assets only, Risk Home default, local cognition fallback, second-instance rejection, and safe shutdown all passed.
- Final packaged-data check: five current risks returned; every action/watch card used the matching user-facing label; safe shutdown passed.
- Privacy scan of all 81 tracked files: `safe=True blocked=0 findings=0`.
- Targeted private-data search: zero matches.

## Desktop acceptance

The packaged desktop application was exercised against an isolated SQLite backup of the existing local data. The official database was not modified.

- Risk Home loaded with the simplified conclusion-first layout.
- View Action opened the decision detail without exposing evidence.
- Why This Judgment opened the evidence drawer explicitly.
- Intelligence Back Office opened as a summary without raw articles.
- View Raw Intelligence revealed raw articles only after the explicit click.
- Closing the window hid it while the process and authenticated loopback API remained alive.
- The acceptance process exited cleanly through the authenticated shutdown endpoint, and all temporary acceptance data was removed.

## Artifact

- Path: `outputs/YuanJianApp-v0.8/YuanJian.exe`
- Size: 6,616,264 bytes
- SHA-256: `F7B73F4B23C368FE9D032D74997FF82D89C27D60317FFF2261541F60E91199B2`
- The previous v0.7 package remains available for rollback.
