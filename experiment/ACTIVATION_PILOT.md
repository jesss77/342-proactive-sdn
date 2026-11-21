# Selected-UDP activation pilot — November 21, 2026

The four-case loaded diagnostic and its independent raw audit are complete.
The earlier failure remains unresolved and both failed supplemental matrices
stay closed. This bounded pilot addresses one remaining timing question:
when is an identified selected UDP datagram first observed leaving the chosen
switch on the alternate egress, relative to the trigger and installation?

## Three registered calls

| Step | Timed workload | Extra instrumentation |
| --- | --- | --- |
| before | Frozen ML, ramp seed1, scale 11.5 Mbit/s, 60 s | Common 0.5-second clock-pair probe; packet capture off |
| capture | Identical frozen ML ramp | Same clock probe plus two tcpdump processes |
| after | Identical frozen ML ramp | Same clock probe; capture off |

One step per explicit call; exactly one attempt per step. Stop on any network,
source, collector, capture, clock-mapping, identity or restoration failure.
No automatic retry, cancellation reset, seed replacement or model/threshold
change. A no-action outcome is retained and supplies no activation time.
The off/on/off bracket describes variation and capture cost; one ordered
bracket cannot prove a causal overhead bound or a policy-benefit difference.
These runs are not pooled into the original 36-trial result.

The original source, profile, endpoints, four-queue collector, model, trigger,
admission, action and cleanup files stay byte-identical. The new wrapper adds
only external instrumentation. It requires the completed four-case parent and
pins its raw files, both earlier failed batches and all 76 existing installed
source/artifact files. The first call includes the existing 60-second idle
readiness check. Each frozen runner retains its own idle guard and restoration.
Jess's reported host condition remains plugged in with other work running;
keep it explicit and report changes before subsequent calls.

## Capture and timestamp meaning

Two ingress captures at the merge would identify the path, but a forwarded
virtual-link skb can carry an earlier software timestamp. This pilot therefore
uses `s1-eth3` and `s1-eth4`, **outgoing only**. The Linux outgoing capture tap
refreshes the timestamp on its cloned skb. This is a defined software egress
observation point, not proof of an atomic flow-mod instant or application
delivery. See the Linux [outgoing capture path](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/core/dev.c)
and [packet timestamp selection](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/packet/af_packet.c).

Registered capability: tcpdump 4.99.4, libpcap 1.10.4. Both interfaces must
support the host timestamp type. Capture uses `-n -p -Q out -j host`, requested
nanosecond savefile precision, 128-byte snapshots and 4,096 KiB capture buffers.
The filter selects only UDP from 10.0.0.1 to 10.0.0.2. `-Z root` permits the
existing root Mininet process to write its root-owned run directory; it changes
no system account or experiment socket buffer. Files remain buffered during
capture and flush on SIGINT. The wrapper checks startup, exit and drop counters
and obtains each process's CPU usage with Linux wait4.

The decoder accepts only the declared classic Ethernet PCAP format and checks
IPv4/UDP lengths, no fragmentation, current native run UUID, destination port,
sequence and embedded monotonic send timestamp. It rejects truncation of the
identity header, duplicates, wrong flows and malformed records. A deliberately
short payload snapshot is expected; the full native datagram is 1,200 bytes.
Both egress captures together must contain each sender datagram once, with no
cross-path duplicate, and counts must reconcile with the native sender. Packet
capture loss must be zero. Downstream bottleneck loss remains an outcome, so
the captures need not equal receiver goodput/counts.

The identical low-rate clock probe in all three cases brackets realtime reads
with monotonic reads. Require source coverage, at least 100 samples, gaps at
most two seconds, sampling brackets at most 10 ms and a total observed offset
envelope at most 10 ms. Packet timestamps are mapped with that observed
envelope and checked against embedded send times. This is not a bound on
unsampled clock jumps, virtual-machine scheduling or kernel timestamp error.
Nanosecond storage precision is not nanosecond accuracy. These limitations
follow the [libpcap timestamp documentation](https://raw.githubusercontent.com/the-tcpdump-group/libpcap/libpcap-1.10.4/pcap-tstamp.manmisc.in).

Report observation availability → decision → programming/readback → first
matching alternate-egress packet, including mapped intervals and any primary
tail overlap. The first packet's send timestamp is not its branch-observation
time. No counterfactual primary onset or useful-warning success is manufactured
from rerouted traffic. The no-intervention test remains prediction evidence.

## Execute

Install `activation-pilot-v1/install_activation_pilot.py` from the existing
SDNUpdate share. It adds five files and changes none of the 76 existing files.
No capture/traffic starts during installation. In the existing T2 Mininet CLI,
run **before only**:

```text
py exec(compile(open('/home/jess/342-proactive-sdn/run_activation_pilot.py').read(), '/home/jess/342-proactive-sdn/run_activation_pilot.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_activation_pilot.py', 'step': 'before'})
```

Review its output before `capture`, then review the captured result before
`after`. The registry enforces order and blocks repeat/failed acquisition.
Keep all pcaps, capture logs/CPU, clock samples, source/policy folders, reviews
and registered hashes. After the three calls or a stop, export a full checkpoint
for independent analysis. Existing network quality criteria remain unchanged.
Publish descriptive capture-off/on/off differences in collector/policy CPU,
capture CPU, query timing, source pacing, achieved rates and RTT; do not claim
zero perturbation. The paper can retain timing bounds if this optional pilot
fails. No larger experiment matrix follows automatically.

Capture option/counter semantics and savefile format are documented in the
versioned [tcpdump manual](https://raw.githubusercontent.com/the-tcpdump-group/tcpdump/tcpdump-4.99.4/tcpdump.1.in)
and [libpcap format](https://raw.githubusercontent.com/the-tcpdump-group/libpcap/libpcap-1.10.4/pcap-savefile.manfile.in).
The parser deliberately refuses other formats rather than guessing their layout.
