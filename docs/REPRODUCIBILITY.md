# Reproduce the saved study

This repository includes the exact 21.4 MB compressed checkpoint, all 9,818 raw/source/derived files it contained, current frozen runtime code and separately reviewed results. Earlier failed/superseded diagnostics are retained. It includes no VM disk image or private report draft.

Checkpoint: `evidence/raw/342-sdn-checkpoint-20261116-214839.tar.gz`

SHA-256: `e8f2e4e4294d35918c8b0d2e37fa79e92366732a19b0a12daad6f7c2a521b8e3`

## One command, no traffic or fitting

From the repository root with Python 3.12 and roughly 400 MB free disk space:

```bash
python3 tools/reproduce_results.py --output scratch/reproduced
```

Use a new output directory each time. The command refuses overwrites, verifies the archive checksum, checks archive paths/entry types, and extracts the original repository into `scratch/reproduced/checkpoint/342-proactive-sdn/`. It never overwrites the published source or rewrites the archived evidence.

It then:

1. Checks the frozen source/model/protocol pins against both the published files and checkpoint.
2. Re-inspects the registered 36-trial batch and compares the entire networking report exactly with the published report.
3. Re-evaluates the untouched six-run prediction test and compares its entire report exactly with the published reference.
4. Saves `reproduction.json` plus independently generated review/CSV/label files.

No Mininet installation, running controller or scikit-learn is required for these offline calculations. No models are trained, thresholds changed or new traffic collected. This validates saved evidence, not a fresh live experiment on different hardware.

## Data and provenance

- Matched batch: `20261116-191234-565387-matched-policy-batch`, seeds 41–43, four policies × three scenarios.
- Development batch: `20261115-194521-170669-fixed-development-batch`, 10 training and 6 validation traces.
- Fresh prediction batch: `20261115-220149-096785-frozen-heldout-batch`, six traces, seeds 31–33.
- The continuous source and dual calibration differ from earlier diagnostic configurations; do not pool versions as matched trials.
- The original runtime `pending_review` metadata remains unchanged. [Derived independent assessments](../results/matched-v1/reviews/) are separate.
- Failed smoke tests, source failures and older collector outcomes remain in the checkpoint. Their presence does not make them accepted comparative trials.
- Historical source copies inside runs are part of the evidence and can differ from later files. Current model/protocol pins must not be updated to hide a mismatch.

The 36-trial CSV, paired summaries, figure sources and adverse outcomes are in [results/matched-v1](../results/matched-v1/). Received-reply means were completed from timestamped ping logs; see [latency supplement](../results/matched-v1/LATENCY_SUPPLEMENT.md). Plot formats are PNG and editable SVG. Sampled queue maxima and received-probe quantiles are not packet-level continuous observations.

The old `results/archive` directory remains unchanged and has its original checksum listing. The final raw checkpoint is tracked as a compressed artifact rather than thousands of duplicated historical files. Git history preserves the original public baseline.

PR4 is under author review; its final edited/submitted version is intentionally not represented as published. [Alignment limits](../results/matched-v1/PROPOSAL_ALIGNMENT.md) must remain alongside the obtained results.
