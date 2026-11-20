# Explicit review of the cancelled initial activation readiness

Reported batch: `20261121-005102-775241-packet-activation-pilot`.
The saved guest state reports `KeyboardInterrupt()`, no traffic attempts and
no new raw folders. The initial idle-readiness record also reports interruption,
without a completed quality report. This is not a passed readiness check.

The original [activation protocol](../ACTIVATION_PILOT.md) blocks failed/partial
resumption and says: “No automatic retry, cancellation reset, seed replacement
or model/threshold change.” It remains byte-identical. The external review
below is an explicit, separately recorded **pre-acquisition administrative
amendment** for this specific manual cancellation. It is not an original
protocol permission, a hidden state edit, or a waiver of an experimental
traffic, source, collector or capture-quality failure. No traffic result is
removed or replaced.

## Runtime requirements

`tools/review_activation_interruption.py` proceeds only if:

- The original protocol digest is exactly
  `48d4c2ddade50ee3266c1bfa811b3c2f8cff622fffa63dcb11678b4ec312f237`.
  All 81 installed files, captured source/protocol pins and completed-parent
  evidence pass the unchanged loaders. Both older failed matrices stay closed.
- The registry names the specifically reported batch; its failed state is
  exactly `KeyboardInterrupt()`, with empty attempts and new-raw lists.
- The `before` step contains only completed environment preflight records;
  no clock, execution, policy review or packet-capture artifact exists.
- Readiness is failed by `KeyboardInterrupt()`, declares no generated traffic,
  and has no quality result. Every complete partial polling row has the expected
  schema/coverage and zero failed queries/invalid intervals. Any unfinished
  final JSON tail is preserved, not imputed or counted as a successful sample.
  A known quality failure blocks the exception even if interruption also occurred.
- No project UDP source, collector or relevant packet-capture process remains
  active. The helper does not kill processes, change rules or generate packets.
- The one-use activation review ledger does not already exist.

## What changes

The helper preserves the complete interrupted batch, failed `batch.json`,
environment and readiness files byte-for-byte. A new review directory records
all their hashes, source/protocol/helper digests, registry bytes, partial-sample
assessment and the explicit amendment reason. Only the activation coordination
registry moves into that review directory. A new
`results/runs/activation-interruption-review-v1.json` ledger records the one-use
exception. This ledger is separate from the earlier recovery cancellation
ledger and cannot authorize another restart of this activation pilot.

The ledger is reserved before moving the registry. A later review error restores
the registry and records failure; it does not delete the ledger or grant another
automatic attempt. Never delete either ledger or manually change failed status.
Run the review without a simultaneous Mininet acquisition command.

After a successful review, inspect its output before running the unchanged
`before` start command once. That starts a new separately named batch, retains
the interrupted one as cancelled pre-acquisition evidence, and requires the
entire 60-second idle check again. Let that check finish even when it is quiet.
The model, source, workload, three-step order, sampling, capture and quality
rules remain unchanged. A subsequent failed traffic/quality result stays failed;
this review cannot be used on it.

## Execute the review only

The helper is staged in the existing shared update folder as
`activation-pilot-v1/review_interrupted_activation.py`. In T3, mount SDNUpdate
and run it with `sudo python3` and the repository path. It starts no traffic.
The original five-file installer/ZIP and frozen 81-file guest source set are
unchanged; the helper is external, not a payload replacement.

Tests:

```bash
python3 -m unittest -v tools.test_review_activation_interruption tools.test_review_interrupted_readiness
```

The ten new tests cover preservation/one-use enforcement, traffic/raw artifacts,
quality reports, bad complete partial rows, preserved unfinished tails, active
processes, captured-source mutation, non-cancellation errors and rollback. The
five older recovery-review tests are retained. Passing these tests prepares a
guarded review; it does not claim the guest review has already succeeded.
