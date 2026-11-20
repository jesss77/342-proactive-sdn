# Recreate the experiment and saved results

The repository contains the complete exact 21.4 MB compressed checkpoint (9,818 files), frozen runtime/model/protocols, original development-search code and selected-model report, analysis/table/plot generators, tests and live-lab commands.

## Reproduce all saved numerical results

With Python 3.12, from a clean clone:

```bash
python3 tools/reproduce_results.py --output scratch/reproduced
```

No third-party Python packages, Mininet, running controller or fitting are needed for this default command. Allow about 400 MB for the checkpoint and derivatives. Use a new output directory each time. It verifies the exact checkpoint digest, safely extracts only regular files/directories, checks source/model pins, and reproduces:

- P01 diagnostic arithmetic, retaining its exclusion.
- Six primary calibration and six dual-profile alternate controls, including accounting and restoration checks.
- The development-only event-target audit.
- All 16 development traces: 1,594 eligible rows, 559 positives and 79 observed events.
- Frozen-tree training/validation review with the original model-input fingerprint.
- The full 36-trial matched report, paired ML comparisons, quality/CPU/source/adverse-outcome summaries and additional tables.
- The untouched six-run held-out prediction report, exactly matching the published reference.
- The 36-run received-reply mean RTT supplement, exactly matching published values.

Logs identify the failed stage if a check fails. Original raw metadata is never rewritten, including runtime `pending_review` statuses. Regenerated development audit wording belongs to its original pre-test design stage; it does not mean the final held-out evaluation is still pending.

## Regenerate figures

The original plot environment used NumPy 2.3.5; the original fitting environment used NumPy 2.5.4. Keep them separate. They are recorded environments, not instructions to update the model or claim compatibility with arbitrary library versions.

```bash
python3.12 -m venv .venv-analysis
.venv-analysis/bin/python -m pip install -r requirements-analysis.txt
python3 tools/reproduce_results.py --output scratch/reproduced-with-plots --figures --plot-python .venv-analysis/bin/python
```

On Windows, replace `bin/python` with `Scripts/python.exe`. This regenerates four figure sets in PNG and editable SVG under the output's `plots/figures/`. The numbers and trial selection are checked exactly. File hashes/pixels can differ with renderer, fonts, metadata and library build; that is separate from reproducing the experiment's numerical results.

To plot an already reproduced report without extracting again:

```bash
.venv-analysis/bin/python tools/plot_matched.py --report scratch/reproduced/networking/matched-report.json --output scratch/plots
```

## Replay the original training search, without changing the frozen model

```bash
python3.12 -m venv .venv-training
.venv-training/bin/python -m pip install -r requirements-ml.txt
python3 tools/reproduce_results.py --output scratch/reproduced-with-fit --refit --training-python .venv-training/bin/python
```

Combine `--figures` and `--refit`, with both interpreter arguments, to run every stage. Fitting uses only the ten original training traces; selection uses the six original validation traces. No fresh test rows enter selection or fitting. The resulting JSON tree is compared structurally, including node values and thresholds, with `selected_tree.json`. The replay is saved separately and never replaces the frozen model.

Original selection evidence is in [results/model-development-v1](../results/model-development-v1/): all 36 parameter/threshold candidates, tie rules, weights, float32 feature fingerprint, export parity, software versions and the selected tree. Recomputed wall/CPU inference timings are hardware-dependent; the historical measured timings remain in the published reports.

## New live measurements

Follow [LIVE_REPLAY.md](LIVE_REPLAY.md) for Ubuntu/VirtualBox resources, controller/topology startup, path controls, in-traffic pilot, full matched matrix and analysis. No VM disk image is provided. Saved-data reproduction is verified independently of fresh live acquisition; fresh VM loss/RTT numbers can vary.

## Exact checkpoint and provenance

`evidence/raw/342-sdn-checkpoint-20261116-214839.tar.gz`

SHA-256: `e8f2e4e4294d35918c8b0d2e37fa79e92366732a19b0a12daad6f7c2a521b8e3`

- Development: `20261115-194521-170669-fixed-development-batch`, seeds 11-15 train and 21-23 validation.
- Untouched prediction test: `20261115-220149-096785-frozen-heldout-batch`, seeds 31-33.
- Matched policies: `20261116-191234-565387-matched-policy-batch`, seeds 41-43.

Earlier failed/superseded diagnostics and historical source snapshots remain in the checkpoint and original `results/archive`. Versions, engines and profiles must not be pooled as matched data. Queue root drops, sender pacing shortfall and UDP sequence loss have distinct meanings. The paper's claims remain bounded by [the reported limitations](../results/matched-v1/PROPOSAL_ALIGNMENT.md).

Run `python3 tools/verify_bundle.py` to check the current publication file hashes against `evidence/loaded-recovery-publication-manifest.json`. The earlier recreation and recovery manifests remain historical snapshots. The former `evidence/publication-manifest.json` records the November 16 snapshot; it is retained as history, not the checksum list for changed documentation/tools. Previous results and frozen source pins are preserved. The submitted PR4 is recorded separately; it is not needed to run this pipeline and is not uploaded by this update.

## November-20 failed recovery audit

The original accepted benchmark above remains separate from the later stopped
supplement. The newer full checkpoint is
`evidence/raw/342-sdn-checkpoint-20261120-223910.tar.gz`, SHA-256
`7ea47c86690aca1b8767577a0accaa9e16797d1c0e8115e0c5494350bfec64cc`.
It preserves the six alternate controls, partial failed supplement, readiness
cancellation review and failed loaded recovery. No extra complete policy block
was obtained. [Diagnosis and exact audit command](../results/loaded-recovery-diagnostics-v1/DIAGNOSIS.md)
explain the endpoint/collector failures and timing limits. The diagnostic audit
starts no traffic and changes no model or raw metadata.
