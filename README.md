# Congestion prediction and SDN rerouting

CMPS 342 · Youssef Shawwa and Jessy Karamaoun · American University of Beirut

We compare fixed routing, reactive rerouting, trend early warning and a frozen
Decision Tree. The observation, admission and rerouting mechanism are shared.
The original benchmark contains 36 matched trials: four policies, three traffic
scenarios and three seeds.

**Result: no consistent added networking benefit from ML over the simple trend
rule was established.** Earlier rerouting helped relative to fixed routing.

| Policy | Ramp goodput (Mbit/s) | Ramp loss (%) | Bursty goodput (Mbit/s) | Bursty loss (%) |
| --- | ---: | ---: | ---: | ---: |
| Fixed primary | 7.510 | 9.741 | 6.121 | 18.682 |
| Reactive | 8.319 | 0.002 | 7.137 | 5.591 |
| Trend early warning | 8.329 | 0.000 | 7.537 | 0.013 |
| Frozen Decision Tree | 8.329 | 0.000 | 7.521 | 0.195 |

These are means over three independent runs per cell. All steady 3 Mbit/s trials
had zero UDP loss; ML switched unnecessarily once. Held-out F1 was 0.957 for ramps
and 0.811 for bursts, but advance warnings reached only 2/3 and 9/25 scorable
events. The stronger alternate path handled all six fixed-alternate variable
controls without loss. The extra bursty cohort stopped on quality failure;
only seed 51 is a complete extra block and is reported separately.

## Reproduce the saved results

With Python 3.12, from this directory:

```bash
python reproduce.py --output scratch/reproduced
```

No VM, Mininet, third-party Python packages, live traffic or model fitting is
needed for this command. Use a new output directory each time. It verifies the
compact inputs, reconstructs the required original paths under `scratch/`,
rebuilds the datasets and results, and compares them with the saved references.
The result is `scratch/reproduced/reproduction.json` plus the rebuilt tables and
stage logs.

For figures, install `requirements-analysis.txt` in a separate environment and
add `--figures`. For an optional replay of the original training search, use the
separate `requirements-ml.txt` environment and `--refit`; the frozen model is
never overwritten. [Details](docs/REPRODUCIBILITY.md).

## Repository map

| Directory | What belongs here |
| --- | --- |
| [`experiment/`](experiment/) | Frozen source, model, acquisition protocols and their pinned tests/docs. Original file bytes preserved. |
| [`data/`](data/) | One compact raw-input package and its checksum/inventory. No VM checkpoints, installers or source-backup chains. |
| [`analysis/`](analysis/) | Calculations, independent inspections and plotting used by the single rebuild command. |
| [`results/`](results/) | Main results, prediction evaluation, per-run tables, figures and follow-up limitations. [Start here](results/README.md). |
| [`docs/`](docs/) | Reproduction and live-lab instructions. |

The cleanup removed redundant checkpoints, installation packages, old publication
manifests, duplicate figure exports and obsolete historical result folders from
the current tree. Required raw records, including failed outcomes used in the
paper, remain in the compact data package. Raw validity decisions and the frozen
model are unchanged. Full local backups remain preserved outside this repository.

The study covers one UDP pair on a small asymmetric Mininet topology, with at
most one successful switch per trial. Probe RTT is not one-way delay, high
utilization is not packet-loss ground truth, and three original seeds do not
establish general superiority. [Methods and limits](docs/METHODS.md).
