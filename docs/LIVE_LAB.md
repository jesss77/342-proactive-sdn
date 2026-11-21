# Run the live lab separately

Saved historical results are rebuilt with `python reproduce.py --output scratch/reproduced`.
This page is for new measurements in a separate clean Ubuntu/Mininet workspace.
Do not run new trials inside the reconstructed historical inputs or reset the
archived failed batches. New observations are a separate experiment.

## Setup

The recorded environment used one VirtualBox vCPU, approximately 6 GiB RAM,
Python 3.12.3, Mininet 2.3.0, Open vSwitch 3.3.9 and OS-Ken 3.1.1. Exact live timings
depend on VM/host scheduling. Install Mininet, Open vSwitch and iperf3 using the
Ubuntu packages; create a Python environment from `requirements.txt`. Frozen
inference does not require scikit-learn. Capture requires tcpdump; the historical
pilot recorded tcpdump 4.99.4 and libpcap 1.10.4.

Use `experiment/` as the working directory. Its relative filenames are preserved
because acquisition protocols bind source hashes. Do not pre-apply the temporary
calibrated profile: wrappers check baseline shaping, apply the recorded profile
during traffic and restore it afterward.

## Start the original topology

Controller terminal, with the controller environment activated:

```bash
cd experiment
SDN_PATH=primary osken-manager --ofp-tcp-listen-port 6653 diamond_controller.py
```

Mininet terminal, from the same directory, when no other lab is active:

```bash
sudo mn -c
sudo mn --custom topology.py --topo diamond --link tc --arp --controller remote,ip=127.0.0.1,port=6653 --switch ovs,protocols=OpenFlow13 --wait
```

Record the actual kernel, package versions, vCPU/RAM, clock source and host
conditions. At `mininet>`, check `pingall` and retain flow/class/qdisc readbacks.

## Path checks and one policy trial

```text
py exec(compile(open('run_routing_smoke.py').read(), 'run_routing_smoke.py', 'exec'), {'net': net, '__file__': 'run_routing_smoke.py'})
py exec(compile(open('run_path_control.py').read(), 'run_path_control.py', 'exec'), {'net': net, '__file__': 'run_path_control.py', 'route': 'alternate', 'requested_bps': 12000000, 'duration': 20})
py exec(compile(open('run_policy_experiment.py').read(), 'run_policy_experiment.py', 'exec'), {'net': net, '__file__': 'run_policy_experiment.py', 'policy': 'ml', 'scenario': 'ramp', 'requested_bps': 11500000, 'duration': 60, 'seed': 1})
```

Require the original source/accounting/collector/path/restoration screens.
Completed traffic is not acceptance. Use `policy` values `fixed`, `reactive`,
`early_warning` and `ml`; scenarios are `steady`, `ramp` and `bursty`. Steady
requests 3 Mbit/s; the variable scenarios use 11.5 Mbit/s as a schedule scale.
Record every outcome, including no action, denied requests and poor QoS.

The frozen matched runner requires an accepted same-source seed 1 ML pilot:

```text
py exec(compile(open('run_matched_batch.py').read(), 'run_matched_batch.py', 'exec'), {'net': net, '__file__': 'run_matched_batch.py', 'limit': 4})
```

It runs the registered four-policy × three-scenario × three-seed matrix and
stops on a quality failure. Follow its recorded paused-batch path only for a
valid continuation; never delete a registry to force a retry. Completed results
can be inspected from the repository root:

```bash
python analysis/analyze_matched.py --repo experiment --output scratch/new-live-results
```

The additional frozen-tree, held-out, capture and follow-up protocols are retained
with their source. Their historical parent gates are deliberate; this cleanup
does not create permission to restart closed collections. Any different resource
configuration, background load or source/model revision must be reported as a
separate experiment rather than pooled with the original 36 trials.
