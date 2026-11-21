# Selected UDP forwarding observation — independently verified pilot

Three registered frozen-ML ramp-seed1 trials completed, capture off/on/off.
All three saved reviews reproduce exactly from checkpoint
`342-sdn-checkpoint-20261121-020916.tar.gz`, SHA-256
`7d4c4fdcabe24b952e69fd0a078382ffbd34f0416a78ae45edd41fb958267c16`.
This is a timing/instrumentation pilot, not three new independent efficacy seeds.
The model, threshold, shared controller, source, profile and quality rules are
unchanged. No fitting or new prediction-test evaluation occurred.

## Networking and instrumentation

| Measurement | Before: capture off | Capture on | After: capture off |
| --- | ---: | ---: | ---: |
| Achieved sender payload Mbit/s | 8.802860 | 8.811813 | 8.813105 |
| Receiver payload Mbit/s | 8.798320 | 8.811813 | 8.813105 |
| UDP sequence loss % | 0 | 0 | 0 |
| Source discarded planned budget % | 0.1271 | 0.0256 | 0.0109 |
| Maximum source pacing gap ms | 36.776 | 35.982 | 24.744 |
| Collector CPU % of one core | 4.011 | 4.540 | 3.129 |
| Policy-thread CPU % of one core | 0.911 | 0.804 | 0.907 |
| Guest mean user + system CPU % | 6.083 | 7.867 | 4.983 |
| Collector query p95 ms | 29.459 | 24.448 | 20.164 |
| Collector query maximum ms | 50.397 | 41.526 | 61.403 |
| Received-probe traffic-window median RTT ms | 10.9 | 14.7 | 10.3 |
| Received-probe traffic-window p95 RTT ms | 20.2 | 20.9 | 16.9 |
| Observation age at programming start ms | 108.175 | 98.302 | 64.359 |
| Full decision to final flow readback ms | 262.767 | 201.043 | 89.421 |
| Programming start to final flow readback ms | 154.945 | 105.594 | 44.343 |

Each run applied one admitted alternate action, verified in-traffic forwarding
and restored primary routing and both profiles. All endpoint UDP-error deltas,
reported root-queue drop deltas, failed collector queries and invalid collector
intervals are zero. No admission denials occurred. Sender pacing discard is a
source-generation limitation, not network loss. The whole-run requested scale
is a variable ramp; 11.5 Mbit/s is not its constant or average sending rate.

The capture children consumed 0.019301 and 0.046774 CPU seconds, total 0.066075,
over approximately 69.06 seconds (about 0.096% of one core). This excludes kernel
work charged elsewhere. The clock observer, present in all three runs, consumed
0.022413 / 0.044912 / 0.024888 CPU seconds. Model inference CPU is already part
of policy-thread CPU and must not be added again.

Capture-on probe RTT and mean guest CPU exceed both off controls, while query
maxima do not. With one fixed-order bracket, concurrent host work and varying
source pacing, these are descriptive observations, not a causal capture cost
or evidence of zero perturbation. The uncaptured follow-up omits both packet
capture and this extra clock observer.

## Packet timing

The two outgoing selected-switch interfaces contain **55,074 distinct native
UDP datagrams**, exactly reconciling with the native sender: 6,761 on s1-eth3
and 48,313 on s1-eth4. UUID, selected IP pair, UDP port, payload size, sequence
and embedded send time validate; no duplicate or cross-branch identity occurs.
Both PCAPs match tcpdump record counts, report zero kernel capture drops and
stop cleanly. Interface drop statistics are unavailable, not fabricated zeros.
Decoded saved packet derivatives reproduce exactly from the PCAP bytes.

The last primary packet is sequence 6,760; the first alternate packet is 6,761.
The first alternate outgoing software observation occurs:

- **110.117–110.142 ms after the policy decision**;
- **14.669–14.694 ms after programming starts**;
- **112.971–112.995 ms after observation availability**.

The last primary observation precedes the first alternate observation by
10.524 ms. This inter-packet gap is not a measured traffic outage. Final readback
occurs later, 201.043 ms after the decision. The previously printed 105.594 ms
is only programming-start-to-readback, with a different starting point.

All three clock mappings cover the native source window with 139 samples each;
observed offset envelopes are 5.599 / 24.926 / 8.156 microseconds. These map
software packet timestamps using observed clock pairs. They do not bound
unsampled clock jumps or timestamp accuracy; nanosecond savefile precision is
not nanosecond measurement accuracy. The observation is at the selected-switch
alternate egress, not atomic rule installation, receiver delivery or proof of
intervention before a counterfactual event onset. Do not extrapolate this single
ML ramp timing to every policy, burst or host-load condition.

## Provenance and retained failures

Batch: `20261121-012117-648967-packet-activation-pilot`.

| Step | Policy folder | Native trial folder |
| --- | --- | --- |
| before | 20261121-012218-108233-policy-ml-ramp-seed1 | 20261121-012223-239722-primary-continuous-ramp-8814308bps |
| capture | 20261121-014335-222889-policy-ml-ramp-seed1 | 20261121-014340-266372-primary-continuous-ramp-8814308bps |
| after | 20261121-015818-222509-policy-ml-ramp-seed1 | 20261121-015823-335920-primary-continuous-ramp-8814308bps |

All 81 installed source/artifact pins match. The parent diagnostic evidence and
both older stopped supplemental batches remain intact. All 36 original matched
trials' raw hashes and 19 actions were rechecked. Of 11,298 previous-checkpoint
files, 11,296 are byte-identical; only continuing controller/Mininet logs append.
This archive contains 11,805 regular files. All old contents remain preserved.

The original manually cancelled idle pilot remains failed, with zero traffic
attempts. Its separate one-use administrative review reproduces: 204 complete
partial idle samples are clean, old batch hashes match, and only its registry
was archived. These partial samples are not a completed idle check. The new
pilot's separate full readiness passes. No quality-failed traffic batch was reset.

These clean windows do not identify or repair the earlier intermittent
collector/endpoint fault. Original findings remain unchanged: no additional ML
networking advantage over simple early warning has been established. New
bursty follow-up seeds require their own registration and quality decisions.

## Reproduce without traffic or fitting

```bash
python3 tools/audit_activation_pilot.py \
  --extract scratch/activation-checkpoint \
  --output scratch/activation-audit
```

The tool requires fresh extraction/output directories. It verifies the exact
archives, safely extracts regular files/directories, checks source/parent/raw
pins, replays native summaries, independently classifies collector intervals,
redecodes PCAP identities and clock mappings, reproduces all three guest reviews,
checks the cancellation ledger, compares earlier contents and checks the original
benchmark. Replay derivatives go outside the raw extraction; final hash checks
confirm raw evidence is unchanged. See [audit.json](audit.json) and
[activation-results.csv](activation-results.csv).
