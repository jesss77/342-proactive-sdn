# Audit every paper figure and table

The default branch is the entry point for the combined paper evidence. The
frozen Version 1 experiment stays in `experiment/`. Version 2 runs on a separate
platform; its source is pinned to
[`512cafc`](https://github.com/jesss77/342-proactive-sdn/tree/512cafc5f48748b741bb2961fa9a644b8333d4a5).
Neither cohort is pooled with the other.

For a fresh V2 checkout, use the separately documented
[repaired source at `2a89041`](https://github.com/jesss77/342-proactive-sdn/tree/2a8904141b18cfb471e2b70aa15084bc9945596e).
The original source commit and its reported results remain unchanged. The
repair restores the exact model/feature bytes required by the original loader,
preserves them through `.gitattributes`, fixes smoke-test indentation, and adds
an offline preflight. [Before/after verification](V2_REPRODUCTION_REPAIR.json)
uses a checkout with Git automatic line-ending conversion disabled. This
verified checkout repair is not a new live network trial.

## One rebuild command

Use Python 3.12 and the plotting dependencies:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce.py --output scratch/paper-audit --figures
```

Use a new output directory. This command checks file hashes, reconstructs the
V1 raw inputs, reruns their inspectors and prediction calculations, verifies
the V2 summary snapshot, and generates all six tables and four paper figures
under `scratch/paper-audit/paper/`. It starts no network traffic or model fitting.
Without `--figures`, all numerical tables, plot coordinates and provenance are
still generated using the standard library.

The checked-in equivalents are under [`results/paper/`](../results/paper/).
The private manuscript is intentionally not published in this repository.

## Figure sources

| Paper figure | Generator | Input and interpretation |
| --- | --- | --- |
| 1. Topology | `analysis/build_paper_assets.py` | Reads link endpoints, ports and configured rates from the literal declarations in `experiment/topology.py`. It is a schematic, not a measured trace. Node positions are presentation choices. |
| 2. ML minus trend loss | `analysis/build_paper_assets.py` | Subtracts the exact per-run loss values for seeds 41–43. V1 comes from the raw-backed matched report; V2 uses the reported bursty + 4 Mbit/s background summaries. Separate panels have different scales; no cohort pooling. |
| 3. Captured ML ramp | `analysis/plot_paper_evidence.py` | Native sender packet-count deltas, qdisc byte-counter deltas, query midpoints, configured capacities, queue packet counts, and captured decision/egress timestamps. Actual source packet size is read from the sender record. |
| 4. Forwarding timing | `analysis/plot_paper_evidence.py` | Recorded observation availability, decision, programming start, the first identified alternate UDP packet's clock-mapping interval, and final readback. Outgoing software capture is not receiver delivery or atomic installation. |

All four are plotted by Python/Matplotlib. No image-generation model is used.
Figures 3 and 4 already existed in the V1 repository; this update publishes the
paper's revised Figures 1 and 2 and connects all four to one rebuild.

`plot-data/` exports every plotted numerical series. The first-alternate packet
coordinate in Figure 4 is the midpoint of the observed clock-mapping interval;
the CSV preserves both interval endpoints. Figure 3's two forwarding markers
nearly coincide at its 60-second scale. Lines joining Figure 2 seeds guide the
eye; seeds are independent run pairs, not a time series.

## Table sources

| Paper table | Machine-generated source | Calculation |
| --- | --- | --- |
| I. Settings | Frozen protocol, bounds, model JSON and trigger/actor source defaults | Formats configuration values. These are settings, not measured outcomes. |
| II. Dataset accounting | Replayed `paper-evidence.json` exclusion records | Whole-run sums for train, validation and test; all exclusions remain explicit. |
| III. Path validation | V1 matched runs, steady alternate controls and six variable controls | Goodput ranges, overload means and actual loss/packet counts. Historical and matched controls are identified separately. |
| IV. V1 networking | All accepted original per-trial records | Three-run arithmetic means; RTT is the mean of within-run reply p95 values. |
| V. Held-out prediction | Fresh fixed-primary test traces and frozen-model scoring | Counts, precision, recall and F1; no controlled traces enter prediction labels. |
| VI. V2 loss | Pinned 72-record batch summary | Three-run means for each policy/scenario/background cell; all retained quality exceptions are disclosed. |

`table-data.json` is the table source for the manuscript. No measured table
values live in the layout configuration: `analysis/paper_layout.json` contains
only headings, captions and widths. `table-provenance.json` retains exact
unrounded values, display strings, calculations and contributing run identifiers.
Rounding happens only when producing displayed cells or plot annotations.

## What can be independently checked

- V1: raw sender/receiver records, qdisc samples, decisions, packet captures,
  source versions, exclusions and restoration evidence are reconstructed from
  the hash-verified compact package. The full rebuild reproduces scientific
  inspection results, not just formatted summaries.
- V2: four original summary files are copied byte-for-byte from the pinned
  commit. Their original paths and SHA-256 values are in `data/v2/manifest.json`.
  The retained 72 records, 12 steady controls, two fixed-alternate controls and
  29-action timing table remain available. V2 has eight logged failed/retried
  attempts and three retained collector-quality exceptions. The complete audit
  rebuilds the paper's V2 means and pairs; it does **not** recreate missing raw
  endpoint records, queue traces or packet activation observations.

The Version 2 GitHub branch provides acquisition code for running a new network
experiment. New measurements are not the original measurements. Its existing
batch-state files must be kept separate from a fresh acquisition. The committed
original smoke-test entry point has an indentation defect, and its normalized
model/feature blob bytes fail the loader's frozen fingerprints. The repaired
source above passes parsing and model preflight while preserving the learned
parameters, feature logic and summary bytes. Source availability is not a claim
that every live V2 entry point has been tested or that its original raw logs
are present. V2's complete raw provenance remains an explicit limitation.

## Integrity and review

`provenance.json` maps each figure to its generator and data series, records
evidence levels, and hashes code, inputs and V1 measurement files. Those
measurement hashes are checked against the raw package's original byte index.
`SHA256SUMS.json` hashes the emitted artifacts. The repository-level
`MANIFEST.json` verifies the checked-in package, scripts and results.

```bash
python reproduce.py --verify
python -m unittest discover -s tests -v
```

The guards reject changed V2 input bytes, duplicate or reordered trial cells,
nonfinite metrics, and hand-edited table cells. The full rebuild compares every
paper table and plotted data CSV with the published references. PDF/SVG metadata
or font rendering can vary across machines; the numerical coordinates and
displayed table cells must agree exactly.
