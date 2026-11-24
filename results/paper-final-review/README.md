# Final paper figures and numerical audit

This supplement adds three figure exports and the supporting numerical data for
the final CMPS 342 paper. It uses the frozen V1 experiment and the retained V2
per-trial summaries.

| Asset | Input |
| --- | --- |
| [Figure 2](02-paired-differences.pdf), burst loss by matched seed | Rebuilt `paper/plot-data/paired-differences.csv` |
| [Figure 3](03-aligned-captured-trace.pdf), ML ramp with packet capture | Rebuilt `paper/plot-data/captured-source.csv`, `captured-queues.csv` and `capture-events.json` |
| [Figure 5](05-delayed-reactive-trace.pdf), V1 bursty seed 42 | Rebuilt matched report and the corresponding raw queue and action logs in `inputs/lab` |
| [Held-out accuracy](review-tables.json) and [warning leads](warning-leads.csv) | Rebuilt `heldout/test_report.json` |
| [V2 condition metrics](v2-all-conditions.csv) | Rebuilt `paper/v2-trials.csv` |
| [V1 delayed-switch pair](v1-adverse-pair.csv) | Verified matched outcomes and raw decisions aligned to each sender start |

Figures 1 and 4 use the [original generators and data](../paper/). V2 arithmetic
is reproducible from the pinned summaries. Its original endpoint and collector
logs are unavailable. In Figure 5, the dashed lines mark programming starts.
Figure 3 uses packet capture to observe egress.

From the repository root with Python 3.12:

```bash
python -m pip install -r requirements-analysis.txt
python reproduce.py --output scratch/final-review-replay
python analysis/build_final_review_assets.py --repo . --replay scratch/final-review-replay --output scratch/final-review-assets
```

The generator also writes PNGs for Word and a JSON of Figure 5's aligned raw
measurements with input SHA-256 digests. The reported values come from the
reproduced records and use full precision before rounding for the paper. The
CSV contains means for goodput, UDP loss and within-run probe RTT p95, and totals
for successful moves, denied requests and primary root queue drops.
