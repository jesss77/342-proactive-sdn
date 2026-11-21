# Evidence status and remaining work — November 21, 2026

## Research question and agreed scope

Does a lightweight Decision Tree provide useful advance warning that improves
SDN networking outcomes beyond a simpler early-warning rule? Keep observations,
flow selection, alternate-path admission and rule installation common. This is
a controlled trigger comparison, not a new path-selection algorithm. Preserve
the DT-only, four-switch, single UDP pair, asymmetric-path study. No new models,
larger topology, polling sweep, switch-back controller or test-set retuning.

## What is implemented and evidenced

| Checkpoint | Evidence and present status |
| --- | --- |
| Measurement and shaping | Primary low-load/overload calibration, alternate-path controls, achieved sender/receiver accounting, interface-specific root drops and endpoint errors. Early anomalous runs remain excluded diagnostics; loopback/clock observations alone were never proof of a shaped-path fix. |
| Traffic and observation | Persistent 1,200-byte UDP; reproducible steady/ramp/bursty schedules; actual elapsed counter rates; four forward qdiscs at requested 250 ms; source pacing and resource diagnostics. |
| Prediction dataset | 16 fixed-primary development runs: ten training, six validation; 1,594 eligible rows, 559 positives, 79 observed events. Whole-run splits, causal history, explicit gaps/censoring and a disclosed pre-fit source-audit amendment. |
| Target and model | New 85% configured-utilization onset, sustained one second, within a two-second horizon; two-second history and sufficient future confirmation information. This is a high-utilization target, not universal packet-loss ground truth. Frozen tree: depth 3, minimum leaf 25, 15 nodes, probability threshold 0.65. |
| Untouched prediction test | Six no-intervention runs, seeds 31–33, 642 eligible rows, 206 positives, 29 events. Ramp F1 0.957; bursty F1 0.811. Useful warnings: 2/3 ramp and 9/25 scorable burst events. Do not equate row F1 with usable networking warning. |
| Common control | h1/h2 IPv4 pair including probes; recent valid upstream demand; both standby queues; operating budget 15.9 Mbit/s with 80% admission bound; carrier/freshness gates; five-second cooldown and one successful switch. No return during traffic; cleanup restores primary. |
| Four trigger modes | Fixed primary; reactive after one second of observed high utilization; causal trend early warning; frozen-tree ML. Same sampler/admission/action. No-action, denials and unnecessary actions retained. The trend rule's recorded parameters are not claimed to have undergone an unrecorded validation search. |
| Main networking experiment | 36 independently accepted trials: four policies × three scenarios × seeds 41–43, with matched schedules, balanced ordering and per-run/paired results. Loss, goodput, received-probe RTT, queue observations, rerouting and costs are reported separately. |
| Interpretation | Mean burst loss: fixed 18.682%, reactive 5.591%, early warning 0.013%, ML 0.195%. No added ML advantage is established. One unnecessary low-load ML switch remains visible. This small study cannot establish general Internet/TCP performance. |
| Follow-up capacity controls | Six accepted variable fixed-alternate controls, ramp/bursty seeds 41–43. All datagrams arrived. Choosing the stronger route permanently already avoids loss in these tested workloads; disclose this limitation. |
| Time traces and provenance | Representative ramp/bursty/adverse/low-load traces and saved-data reproduction published. Code/model/protocol pins, raw checkpoints, rejected attempts and original metadata preserved. Submitted PR4 remains the private author-edited reference. |

Main [networking results](../results/matched-v1/RESULTS.md),
[prediction reference](../results/matched-v1/PREDICTION_REFERENCE.md),
[proposal alignment](../results/matched-v1/PROPOSAL_ALIGNMENT.md),
[initial supplement audit](../results/supplement-diagnostics-v1/DIAGNOSIS.md) and
[loaded recovery audit](../results/loaded-recovery-diagnostics-v1/DIAGNOSIS.md)
remain separately identifiable.

## Why additional acquisition stopped

The initial supplemental batch accepted six controls and reactive seed 44, then
stopped on early-warning collector quality. Its partial policy block cannot
support a new paired mean. A separately registered once-only whole-block
recovery passed idle readiness but failed its first reactive loaded trial:
43 receiver-buffer errors, three query overruns, six invalid intervals per
queue, a 359 ms maximum pacing gap and 2.370 s decision-to-final-readback.
Restoration passed. Those two phases produced zero complete extra four-policy
blocks; the later, separate follow-up produced one complete seed51 block.

The full failure archive and both stopped states are preserved. Their failures
do not invalidate the already independently checked historical benchmark, but
current loaded repeatability is unresolved. No further automatic recovery is
permitted. Source, model, buffers, profile, vCPU, clock, polling and thresholds
stay unchanged while the smallest reproducing case is investigated.

## Ordered plan and acceptance gates

| ID | Work | Completion criterion | Current state |
| --- | --- | --- | --- |
| R1 | Isolate loaded measurement failure | Four-step bounded component ladder, one case per explicit call; stop at first quality failure and inspect preserved evidence. Do not require a desired loss result. | All four cases independently verified from the new checkpoint. Earlier fault not reproduced; root cause unresolved. |
| R2 | Decide fix versus bounded stopping | Explain observed failure mechanism and remaining uncertainty. Any actual change gets a separate version and renewed low-load/overload/path/monitoring calibration. If unresolved promptly, retain the failure limitation and finish the accepted study. | Bounded diagnostic complete. No fix is justified from these four windows; preserve intermittent-failure limitation and keep failed batches closed. |
| R3 | Close supplemental repetition decision | Keep old partial attempts unpooled and honor the separately registered bounded stopping rule. | [Acquisition closed](../results/bursty-followup-v1/CLOSED.md): seven attempted, six individually valid, one collector-quality failure, nine unattempted. Only seed51 is a complete extra block. All seven reviews independently reproduce; no more traffic or recovery. |
| R4 | Measure forwarding activation if feasible | Separate narrowly instrumented pilot; correlate observation availability, decision, programming/readback and first selected UDP on alternate egress, with capture/clock limitations. | [All three off/on/off reviews independently reproduce](../results/activation-pilot-v1/RESULTS.md). Captured first alternate UDP at 110.117–110.142 ms after decision; full final readback 201.043 ms. Single ML ramp, not a general latency bound or before-onset proof. |
| R5 | Consolidate existing offline evidence | Compact calibration/settings; split/run exclusions; explicit warning-time denominators and missed/late/unmatched rates; individual paired differences and timing uncertainty. No controlled-trace relabeling. | Complete: [consolidated tables, figures and exact rebuild commands](../results/paper-evidence-v1/README.md). Original held-out row/episode reports reproduce exactly. |
| R6 | Finish final IEEE paper and reproducibility audit | Topology, common-loop pseudocode, parameters, workload/exclusion rules, closest-work comparison, measured outcomes, timing/costs and limitations. Trace claims to frozen evidence and verify layout/references. | Complete private author-review draft prepared in IEEE PDF and editable Word formats. Final author review, exact Moodle-template check and submission remain; deadline November 24. No paper draft is published here. |

R1 is a diagnostic ladder: (1) source/receiver with existing snapshots, probes
and vmstat; (2) add continuous collector; (3) frozen fixed-policy loop; (4)
frozen reactive loop. It is not another four-policy efficacy study. Jess's
reported host condition is plugged in with other work still running. Keep that
limitation visible; neither an idle readiness pass nor one passing loaded case
proves a resource-contention fix. See [the executable diagnostic protocol](../LOADED_DIAGNOSTICS.md).

By November 21, make an evidence-based R2/R3 decision rather than adding another
open-ended retry. Use November 22 for evidence consolidation and the complete
paper draft, November 23 for verification/review, and November 24 for final
submission. These are work targets around the known deadline, not new course
requirements. Write established methods/results while targeted diagnostics
proceed; do not hold the whole paper for an optional ML win.

The existing 95/100 is a planning rubric for the narrowed implementation and
delivery, not a grade, time estimate, or percentage of all research uncertainty
resolved. Creating this plan or installing the diagnostic adds no points.

Latest evidence: [final follow-up closure](../results/bursty-followup-v1/CLOSED.md).
All seven attempted guest reviews reproduce, all 85 installed pins and original
topology/controller match, original/seed51 raw evidence remains verified and the
failed state is unchanged. One shared missed deadline caused one invalid interval
per queue. Six individual trials pass, but only seed51 is a complete extra block.
New live acquisition is closed under the registered rule. The earlier
[component ladder](../results/component-ladder-v1/RESULTS.md) and completed timing
pilot remain validation evidence, not proof that the intermittent fault was fixed.

The [activation pilot](../ACTIVATION_PILOT.md) is prepared after confirming
tcpdump 4.99.4/libpcap 1.10.4. It observes outgoing selected-switch interfaces,
checks payload identity/capture completeness, brackets host/monotonic clocks
and compares capture off/on/off without changing the common controller. Kernel
software capture timestamps are observations, not atomic rule-activation or
application-delivery timestamps. Per-capture child CPU omits kernel work
charged elsewhere; retain whole-guest resources and descriptive bracket
variation. All three guest steps completed and independently reproduce from
checkpoint `20261121-020916`; no pilot repetitions remain. Both failed
supplemental matrices stay closed. See the [timing and overhead evidence](../results/activation-pilot-v1/RESULTS.md).

The reported initial activation readiness was cancelled with KeyboardInterrupt,
zero traffic attempts and no new raw folders. The [explicit cancellation
review](ACTIVATION_INTERRUPTION_REVIEW.md) is a separately recorded
pre-acquisition administrative amendment, not permission to retry a screened
experiment. It preserves failed raw/state, checks all partial samples and
processes, archives only the registry once and leaves the 81 source/protocol
files unchanged. Its 15 guard/regression checks pass. Jess reports successful
guest review at `20261120-230735-648374-reviewed-activation-idle-interruption`:
zero traffic attempts, 204 completed partial samples, old batch unchanged and
no source/quality change. The exported review now independently reproduces:
204 clean partial rows, exact old-batch hashes and archived registry. Partial
idle samples are not a full readiness pass; the new completed pilot has its own
full passing idle check. The one-use helper must not run again.
