# Fresh test acquisition of the already frozen model

Frozen model SHA-256:
`63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595`.
Depth 3, minimum leaf 25, fifteen nodes, alarm threshold .65. Ubuntu already
reproduced the selected development metrics. No test results have been used
to choose this model or threshold.

Collect six untouched fixed-primary traces: ramp and bursty seeds 31, 32 and
33, in registered alternating scenario order. Preserve the same frozen dual
profile, 60-second schedule, 11.5 Mbit/s scale and 250 ms sampler. No ML
inference or rerouting occurs during collection, so the primary-path labels
are not censored by intervention. Source-integrity checks retain disclosed
pacing deviations under the previously recorded amendment.

Before collection the gate checks model bytes, profile/label/feature context,
matching Ubuntu development review and pinned acquisition source. The batch
snapshots model, protocol and evaluation code before any fresh traffic. A
registry prevents accidentally reacquiring another batch for this model.
Failed attempts stop and preserve references; resume accepts only a paused
batch with unchanged model/protocol/pipeline and accepted identity prefix.

After all six pass, `heldout_dataset.py` independently rechecks acquisition,
source hashes, counters and frozen snapshots. It evaluates the pinned model
and previously defined baselines without fitting or changing thresholds.
Reports contain per-run and per-scenario row metrics, warning recall/precision,
false/late warnings, censored warnings and leads to the operational target.
These are prediction-test outcomes, not live ML networking benefits.

The test derivative is explicitly marked `complete_development: false` and
`complete_heldout: true`; the existing training loader rejects its identities.
Do not tune this model after seeing its test result and still call that result
untouched. Any later revised model needs a disclosed development iteration
and a new independent final-test plan.

T2 acquisition command:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_heldout_batch.py').read(), '/home/jess/342-proactive-sdn/run_heldout_batch.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_heldout_batch.py'})
```

After `completed | accepted 6 / 6`, T3 evaluation:

```bash
python3 heldout_dataset.py --repo . --batch "$(cat results/runs/active-heldout-batch.txt)" --output "results/derived/heldout-v1-$(date +%Y%m%d-%H%M%S)"
```

Live ML integration, steady-load false-alarm controls and repeated four-policy
QoS comparisons remain separate next steps. This update changes no existing
acquisition, feature, label or model source, and installation starts no traffic.
