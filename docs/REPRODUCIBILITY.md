# Reproduce the saved experiment

## Numerical results

Use Python 3.12 and a fresh output directory:

```bash
python reproduce.py --output scratch/reproduced
```

This verifies and unpacks `data/inputs.zip`, restores the original relative paths
needed by the frozen inspectors, and reproduces:

- Six historical primary calibration and six dual-profile alternate controls.
- Development labels and the frozen-model review: 16 runs, 1,594 eligible rows,
  559 positives and 79 observed events.
- All 36 matched networking trials, paired differences and received-probe RTT.
- Six fresh no-intervention test traces and their original prediction scores.
- Initial alternate controls and the stopped supplement/recovery outcomes.
- All four component diagnostic cases and all three capture off/on/off steps.
- All seven attempted extra bursty trials, including the quality failure.
- Consolidated exclusions, warning denominators/rates and paper evidence tables.

Stage logs identify any failed check. Reproduction stops on a mismatch. It starts
no traffic and changes no source, model, raw record or acceptance threshold.

Use `python reproduce.py --verify` for a quick repository checksum check.
The four extraction/integrity guard tests run with
`python -m unittest discover -s tests -v`. Allow about 500 MB for reconstructed
raw inputs and derived output; only the compact package is stored in Git.

The curated archive stores each distinct input byte sequence once. Its index
restores original filenames in the output folder; the frozen inspectors can
therefore verify the same captured-source and raw-record hashes. The collection
contains only dependencies required for this rebuild, not an entire VM checkout.
Old full-checkpoint-to-checkpoint preservation checks are historical provenance
receipts, not repeated claims about the smaller curated archive.

## Figures

```bash
python3.12 -m venv .venv-analysis
.venv-analysis/bin/python -m pip install -r requirements-analysis.txt
.venv-analysis/bin/python reproduce.py --output scratch/with-figures --figures
```

Windows uses `Scripts/python.exe` instead of `bin/python`. This regenerates the
five paper figures and representative four-policy time traces in PNG/SVG/PDF
where supported. The saved publication figures are PDFs; alternative exports are
generated on demand. Metadata and font differences can change image hashes;
the underlying numerical comparisons must still match.

## Optional training replay

```bash
python3.12 -m venv .venv-training
.venv-training/bin/python -m pip install -r requirements-ml.txt
.venv-training/bin/python reproduce.py --output scratch/with-fit --refit
```

This replays the original train/validation search into the new output directory
and checks the exported tree against the frozen model. No validation or test
rows enter training. Keep the training and plotting environments separate;
their historical NumPy versions differ. Timings measured on the reproduction
machine are not substituted for historical inference/control costs.

## Live lab

[LIVE_LAB.md](LIVE_LAB.md) describes a separate clean Mininet experiment. New live
measurements will vary with VM scheduling and software. They do not replace the
historical records. The final supplementary acquisition remains closed; the
reproduction command never resumes or resets a failed batch.
