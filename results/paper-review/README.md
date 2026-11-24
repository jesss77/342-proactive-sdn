# Manuscript revision evidence

This supplement clarifies the frozen results. It does not fit a model, tune a
trigger, change acquisition rules, or acquire new network traffic.

Run the complete offline rebuild from the repository root:

```sh
python reproduce.py --output scratch/revision-check --figures
```

Or use an existing complete replay:

```sh
python analysis/build_review_supplement.py --replay scratch/revision-check --output scratch/review-only
```

- `confusion.csv`: exact held-out ML TP/FP/FN/TN counts.
- `admission_timing.csv`: V2 successful programming starts, demand and alternate
  load for bursty traffic with 4 Mbit/s background. These are reported timing
  summaries, not raw decision or first-packet timestamps.
- `tree_splits.csv` and `tree_leaves.csv`: all frozen nodes and leaf scores.
- `tables.json`: display cells generated from those records; manuscript headings
  and captions may be adapted without changing numerical cells.
- `review-evidence.json`: per-event allocation of positive rows, late trend
  episode delays, comparable V1/V2 timing statistics and source hashes.

The bursty test contains 146 correctly positive rows across 24 events, but only
nine matched advance-warning episodes. Ninety-seven correctly positive rows
belong to events without a matched advance episode under the original rising
crossing and five-second cooldown rules. Row recall and episode recall measure
different behavior; the replay does not simulate new routing policies.

The V2 field named `s3_drops` is the sum of root drops at `s1-eth4` and
`s3-eth2`, according to the pinned exporter. Background loss is reported over
the background process lifetime and defaults to zero when background records
are absent. Missing original logs prevent independently establishing that all
reported background zeros were measured zeros.

Original six paper tables, four figures and their provenance remain in
[`../paper`](../paper/README.md). V2 raw records remain unavailable. These
clarifications do not increase the independent run count.
