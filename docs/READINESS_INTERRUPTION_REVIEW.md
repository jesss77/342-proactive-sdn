# Administrative review of an interrupted idle check

The reported first recovery readiness check ended with `KeyboardInterrupt()`
and no quality result. This is not evidence of a passed readiness check or a
collector-quality failure. The recovery registry must be inspected and preserved;
do not delete it or change `batch.json` to manufacture a resumable state.

`tools/review_interrupted_readiness.py` provides one explicit, manual review
exception before traffic acquisition. Run it in the Linux guest with permission
to move the root-created coordination files. It proceeds only when:

- Original sources, recovery registration, captured sources and all 828 parent
  files match their pins.
- The recovery is failed, with exactly one initial idle-readiness entry ending
  in `KeyboardInterrupt()`, no completed quality report, zero trial attempts and
  zero accepted trials.
- No collector process is running and no completed partial collector samples
  already show failed queries or invalid intervals.
- This one-time interruption-review ledger does not already exist.

The helper preserves the complete interrupted batch and failed state byte-for-
byte. A separate review folder records their hashes, the helper digest, captured
coordination files, partial-sample assessment and reason. Only the cancelled
recovery's registry and active pointer are moved into that folder; the original
failed supplemental registry and all its evidence remain unchanged. Rollback
restores pointers if the review fails. A one-time ledger records the exception.

After a successful review, run the unchanged recovery start command once. The
full 60-second idle check must finish before traffic begins. The trial plan,
quality rules, model and controller source remain unchanged. This is a
prospective administrative exception for cancellation before acquisition, not
an automatic retry of a screened quality failure. No traffic trial has been
replaced under this procedure. If any precondition fails, preserve the state
and investigate rather than bypassing the check.

Tests: `python3 -m unittest -q tools.test_review_interrupted_readiness`.
The five checks cover raw preservation/one-time use, prior acquisition, partial
collector failure, active collectors and existing quality results. No guest
review or new acceptance result is claimed by publishing this helper.
