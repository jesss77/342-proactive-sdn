# Loaded recovery: validation hold

The full checkpoint SHA-256 is
`7ea47c86690aca1b8767577a0accaa9e16797d1c0e8115e0c5494350bfec64cc`.
All 10,720 regular files were safely extracted. All 72 installed source/artifact
hashes match their pins; all 828 parent supplement files remain unchanged.
The saved guest inspection reproduces exactly. No live traffic or rule changes
were performed by this offline audit.

## Outcome and evidence

Recovery batch `20261120-220211-529321-bursty-supplement-recovery` passed its
60-second idle check, then stopped on the first reactive bursty seed-44 trial:
`20261120-220314-270068-policy-reactive-bursty-seed44`.
Its source trial is `20261120-220320-770161-primary-continuous-bursty-7881320bps`.
There are **zero accepted recovery trials and zero complete extra blocks**.
The frozen inspector correctly rejects `udp_error` and `collector_quality`.
Both profile and route restoration passed. The bounded recovery is exhausted;
its failed state must not be reset or silently retried.

| Measurement | Observed |
| --- | ---: |
| Actual sender payload rate | 7.737331 Mbit/s |
| Receiver goodput | 6.515880 Mbit/s |
| Sent / unique received datagrams | 48,359 / 40,764 |
| Missing datagrams / sequence loss | 7,595 / 15.705453% |
| Primary bottleneck root drops | 7,575 |
| h2 receive-buffer / input-error deltas | 43 / 43 |
| Sender error counters / source send errors | 0 / none |
| Source discarded pacing budget | 1.821785% |
| Maximum sender pacing gap | 359.304 ms |
| Collector query failures | 0 |
| Invalid intervals per queue | 6 |
| Collector / policy CPU, percent of one core | 18.174 / 3.190 |

The two h2 error counters overlap; do not sum them into 86 separate losses.
The [Linux UDP receive path](https://code.googlesource.com/linux/torvalds/linux/+/586b5dfb51b962c1b6c06495715e4c4f76a7fc5a/net/ipv4/udp.c)
increments both for a receive-buffer allocation failure. Root qdisc counters
also include RTT probes and control traffic and have different boundaries from
UDP sequence accounting. No exact cross-layer loss decomposition is claimed.
Source pacing discard is unsent budget, not network packet loss. It remains
below the inherited 5% source screen; that does not waive the endpoint or
collector failures.

## Collector and action timing

Three shared reads lasted 383.011, 288.034 and 302.203 ms, exceeding the
250 ms polling interval. Each invalidates its own derived rate and the next
interval; the next samples also record skipped deadlines. Thus six intervals
are invalid on each of four queues, from three shared read overruns, not
24 independent query failures. Counters did not reset. See
[the interval table](invalid-collector-intervals.csv).

The first incident spans approximately source seconds 29.51–30.28. Two later
incidents span 47.30–48.78, overlapping primary-rule verification and rule
installation. Temporal overlap does not prove which process caused the delay.

The applied decision used a 7.493 ms old observation, but primary-rule
verification and other work aged it before installation:

| Timing relative to source start | Seconds |
| --- | ---: |
| Observation available | 46.557290 |
| Decision recorded | 46.564783 |
| Rule programming started | 48.084273 |
| Final rule readback finished | 48.935071 |
| Measurement age at programming start | 1.526983 |
| Full decision to final readback | 2.370287 |
| Reported programming/readback subinterval | 0.850798 |

There were nine stale-observation denials and seven admission-headroom denials.
The frozen loop checks 0.5-second freshness before entering the shared action;
its primary-rule verification can add delay before the first installation.
The reported programming/readback duration excludes that verification. Neither
timestamp measures the first selected UDP packet using the new route.

Guest one-second resource observations average 54.97% user plus system CPU
during the source window and reach 100% in one interval near installation.
The runnable count reaches six; no guest swap activity is observed. These
averages and the pacing/collector gaps are consistent with transient resource
contention, but do not establish a host scheduling, clock or kernel root cause.
The idle pass therefore does not establish loaded stability.

## Preserved historical evidence

Comparing against the exact November-16 archive: 9,816 files are byte-identical.
The two continuing session logs have appended records and preserve their exact
original byte prefixes. No historical contents were replaced. All 36 original
matched-run evidence hashes still match; their 19 action records remain intact.
Their maximum program-start measurement age is 0.235558 s and maximum full
decision-to-readback duration is 0.413106 s. The six independently accepted
fixed-alternate controls also remain intact. The failed recovery is excluded
from their aggregates and provides no new policy-benefit estimate.

The earlier readiness cancellation was independently checked: zero traffic
attempts, unchanged interrupted raw batch, preserved coordination snapshots and
the one-time review ledger. That administrative cancellation review did not
waive either later screened traffic failure.

## Reproduce this audit

From the repository root, with Python 3.12:

```bash
python3 tools/audit_loaded_recovery.py --extract scratch/recovery-checkpoint --output scratch/recovery-audit
```

Both output directories must be new. The tool verifies and safely extracts the
new checkpoint, rechecks pins, readiness, interruption review, endpoint/collector
screens, source schedule, original archive preservation and all original
matched-run raw hashes. It never fits a model, generates traffic or edits raw
metadata. [audit.json](audit.json) contains the full independent result.

## Next experimental decision

Do not change buffers, VM resources, sampling, quality thresholds or trigger
parameters inside the frozen benchmark. Before further acquisition, isolate
the loaded measurement failure with a small prospective diagnostic comparison
that separates source/receiver, collector and policy/action overhead. Record
the host/guest conditions and retain every outcome. Any implementation fix
requires a separately versioned protocol and renewed calibration. The existing
accepted study can be written with these supplemental failures and limits
reported explicitly; further repetitions must not become open-ended retries.
