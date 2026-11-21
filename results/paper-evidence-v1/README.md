# Consolidated final evidence — November 21, 2026

This package consolidates the frozen study after live acquisition closed. It
contains results and reproducible analysis, not the private paper draft. The
original model, labels, triggers, topology, 36-run benchmark and historical
failures remain unchanged. No new acquisition, fitting or threshold tuning was
performed.

## Main conclusion

Early rerouting improved delivery relative to fixed primary routing. A consistent
additional networking advantage of the Decision Tree over simple trend early
warning is **not established**. The alternate route already carries these
workloads without loss when selected permanently. The one complete extra bursty
seed is separate descriptive follow-up; partial/invalid cells are not pooled.

## Files

| Evidence | Location |
| --- | --- |
| Frozen inputs, source hashes, all consolidated metrics and definitions | `tables/paper-evidence.json` |
| Whole-run dataset exclusions and reasons | `tables/exclusions-by-run.csv`, `tables/exclusions-by-split.csv` |
| Held-out row precision/recall/F1 | `tables/prediction-rows.csv` |
| Advance, late, other unmatched and censored warning episodes | `tables/warnings-by-run.csv`, `tables/warnings-by-scenario.csv` |
| Individual ML-minus-trend comparisons | `tables/paired-differences.csv` |
| Original three-seed means, sample SDs and ranges | `tables/network-aggregates.csv` |
| Fixed settings and post-benchmark acquisition counts | `tables/parameters.csv`, `tables/attrition.csv` |
| Historical primary calibration and dual-profile steady alternate controls | `tables/historical-path-controls.csv` |
| Standalone scientific figures | `figures/` (PDF, editable SVG, PNG and checksums) |

## Compact path-validation record

| Condition | Runs | Observed result | Scope |
| --- | ---: | --- | --- |
| Historical primary 3 Mbit/s calibration | 3 | Receiver 2.989–2.995 Mbit/s; zero sequence loss/root drops | Recorded historical primary profile; separate from final dual-profile benchmark |
| Historical primary 12 Mbit/s overload | 3 | Sender 11.954–11.993 Mbit/s; receiver 9.323–9.611; sequence loss 19.494–21.918% at intended bottleneck | Same historical calibration version; not pooled with later profile |
| Dual-profile alternate 12 Mbit/s steady | 3 | Receiver 11.994–11.997 Mbit/s; zero sequence loss | Selected/inactive path counters, collector and restoration checks pass |
| Dual-profile alternate 16 Mbit/s steady | 3 | Receiver 15.993–15.996 Mbit/s; zero sequence loss | Same path/accounting checks; 20-second controls |
| Final benchmark fixed-primary 3 Mbit/s | 3 | Approximately 3 Mbit/s; zero sequence loss | Current dual profile; 60-second runs, seeds 41–43 |
| Fixed-alternate ramp and bursty schedules | 6 | All sender datagrams received; all reported root-drop deltas zero | Seeds 41–43; independent supplemental controls, not new four-policy repetitions |

Exact run identifiers, achieved sending rates and profiles are retained in the
CSV/JSON and linked historical audits. Root qdisc drops and UDP sequence loss
have different denominators and must not be added.

## Warning rates and denominators

The original held-out row and episode reports reproduce exactly before new
summaries are computed. A rising score crossing starts an episode, subject to
the original five-second cooldown. Each observed event onset can match at most
one episode in the next-two-second target window. A warning during an already
started event is late, even before confirmation. No-intervention traces provide
these labels; intervened runs are never relabeled as false alarms.

Two rate denominators are explicit:

- Counter-covered source time: 179.257 s ramp, 179.240 s bursty.
- Scorable opportunity exposure: duration-weighted rows with available features
  and complete 3.75-second future support; 161.996 s ramp, 161.496 s bursty.
  This is discrete opportunity exposure, not continuous decision availability.

For ML, ramp warnings cover 2/3 scorable events; eight unmatched episodes consist
of seven late and one other. Bursty warnings cover 9/25 scorable events (26 were
observed); sixteen unmatched consist of thirteen late and three other. Two ramp
and three bursty tail episodes are censored. Under the scorable denominator,
unmatched ML rates are 2.963/min ramp and 5.944/min bursty; other-unmatched rates
are 0.370/min and 1.115/min. The unchanged original counter-covered rates are
2.678/min and 5.356/min. Late, other and censored counts remain separate.

Offline episodes are not live reroutes: replay does not simulate admission,
freshness rechecks or the live one-successful-action limit. Lead-margin plots
are descriptive 0–2-second sensitivities, not new trigger tuning or proof of
successful pre-onset intervention.

## Figures

1. `01-topology`: original four-switch/four-host topology. h3/h4 idle; configured
   link capacities shown. No teammate background-load/vCPU experiment is pooled.
2. `02-paired-differences`: each independent ML-minus-trend pair; R=ramp,
   B=bursty. Negative loss/RTT and positive goodput favor ML. Orange B51 is a
   distinct cohort. Original burst loss differences are -0.0065, -0.0158 and
   +0.5684 percentage points; the favorable extra pair is not a fourth original
   benchmark repetition.
3. `03-aligned-captured-trace`: real capture-pilot source load, measured branch
   utilization and sampled queue occupancy. Dashed orange=decision; dotted
   purple=first alternate UDP observation. Both root-drop deltas are zero.
4. `04-forwarding-timing`: distinct observation, decision, programming, packet
   observation and readback times. First alternate UDP is observed at
   110.117–110.142 ms after decision; the observed clock envelope is not a bound
   on unsampled clock jumps/kernel timestamp accuracy. Not atomic activation,
   application delivery, interruption or a general latency bound.
5. `05-warning-margin`: fraction of scorable test events warned at each required
   offline lead margin. ML burst coverage is 9/25 at zero margin, 8/25 at 0.5 s
   and 7/25 at 1 s. Equal ramp traces overlap. No simulated admission/activation.

## Rebuild from saved data

Run from the repository root, using fresh directories:

```bash
python3 tools/audit_closed_bursty_followup.py --extract scratch/closed-followup --output scratch/closed-followup-audit
python3 tools/consolidate_paper_evidence.py --repo scratch/closed-followup/342-proactive-sdn --output scratch/paper-evidence
.venv-analysis/bin/python tools/plot_paper_evidence.py --repo scratch/closed-followup/342-proactive-sdn --analysis scratch/paper-evidence --output scratch/paper-figures
```

Python 3.12 standard library suffices for audits/numerical consolidation. Figures
use the recorded `requirements-analysis.txt` environment. Windows virtualenvs use
`Scripts/python.exe` rather than `bin/python`. Exact numerical reproduction is
separate from identical PDF metadata/font bytes. [Full reproduction guide](../../docs/REPRODUCIBILITY.md).

Final raw checkpoint SHA-256:
`a4c9f96e7a5029d7a28d2abf1ef86e7a62c84722e23eb0c585e286ab4f78c64d`.
Model SHA-256:
`63b8b320ca7c6ca7c7e49d9bca6fb8408e491ea5bec168dd206dd9beeadaf595`.
All 85 installed source/artifact pins and original topology/controller remain
unchanged. The [closed follow-up](../bursty-followup-v1/CLOSED.md),
[timing pilot](../activation-pilot-v1/RESULTS.md),
[main benchmark](../matched-v1/RESULTS.md) and
[original time traces](../time-traces-v1/) remain separately identifiable.
