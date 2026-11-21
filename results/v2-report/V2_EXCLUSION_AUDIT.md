# Version 2 Data Quality, Exclusion, and Retry Audit

- Main matched trials accepted: **72/72** (`69/72` with `0` invalid collector intervals; `3/72` with `1–2` skipped 250 ms ticks out of ~266, `0` failed queries).
- Steady low-load control trials accepted: **12/12** (`0` failed/retried attempts, `0` screen failures).
- Fixed-alternate control runs: **2/2** clean (`screen_failures: []`).
- Retried/excluded main batch attempts logged in `v2-batch.json`: **8** (zero silently discarded).

## Logged Retried Attempts

| # | Timestamp | Policy | Scenario | `s3` BG (Mbit/s) | Seed | Reason |
| ---: | --- | --- | --- | ---: | ---: | --- |
| 1 | 2026-11-21T13:38:26 | ml | ramp | 4 | 41 | `RuntimeError('Traffic recorder failed; inspect trial')` |
| 2 | 2026-11-21T14:00:30 | reactive | bursty | 14 | 41 | `RuntimeError("Quality screen failed: ['achieved_sender_rate', 'source_pacing_budget_discarded', 'collector_quality'] (failed_q=0, max_invalid=1)")` |
| 3 | 2026-11-21T14:10:38 | reactive | bursty | 14 | 41 | `RuntimeError("Quality screen failed: ['achieved_sender_rate', 'source_pacing_budget_discarded'] (failed_q=0, max_invalid=0)")` |
| 4 | 2026-11-21T14:15:07 | reactive | bursty | 14 | 41 | `RuntimeError("Quality screen failed: ['achieved_sender_rate', 'source_pacing_budget_discarded'] (failed_q=0, max_invalid=0)")` |
| 5 | 2026-11-21T14:33:48 | fixed | ramp | 14 | 42 | `RuntimeError("Quality screen failed: ['udp_error'] (failed_q=0, max_invalid=0)")` |
| 6 | 2026-11-21T14:37:42 | reactive | ramp | 14 | 42 | `RuntimeError("Quality screen failed: ['udp_error'] (failed_q=0, max_invalid=0)")` |
| 7 | 2026-11-21T21:20:54 | early_warning | ramp | 14 | 43 | `RuntimeError("Quality screen failed: ['achieved_sender_rate', 'source_pacing_budget_discarded'] (failed_q=0, max_invalid=0)")` |
| 8 | 2026-11-21T21:23:10 | early_warning | ramp | 14 | 43 | `RuntimeError("Quality screen failed: ['achieved_sender_rate', 'source_pacing_budget_discarded'] (failed_q=0, max_invalid=0)")` |
