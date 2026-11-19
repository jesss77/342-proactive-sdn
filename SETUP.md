# Setup and verification

The accepted experiments used a dedicated Ubuntu 24.04.5 VirtualBox guest with **one vCPU and 6 GiB RAM**, Python 3.12.3, Mininet 2.3.0, Open vSwitch 3.3.9, iperf3 3.16 and OS-Ken 3.1.1. Earlier four-vCPU timing diagnostics are historical. Recorded calibration and source/collector changes stabilized the tested protocol; this is not a claim that a clock problem was universally fixed.

## Inspect the saved results first

Clone this repository and run offline verification with Python 3.12. Frozen-tree inference and result reproduction do not require scikit-learn or a running SDN lab.

```bash
git clone https://github.com/jesss77/342-proactive-sdn.git
cd 342-proactive-sdn
python3 -m unittest discover -v
python3 tools/reproduce_results.py --output scratch/reproduced
```

The reproduction command checks the checkpoint digest, safely extracts into a new output directory, verifies published protocol pins, independently re-inspects all 36 networking trials and reproduces the untouched six-run prediction metrics. It starts no traffic, updates no rules and performs no fitting. See [the detailed reproduction guide](docs/REPRODUCIBILITY.md).

The original Ubuntu installation reported 137 tests: 135 passed and two optional training tests skipped. Windows reproduction has additional platform skips for POSIX process-signal checks. Local mock/loopback tests do not replace guest path or performance evidence. Existing validation logs are in [evidence/validation](evidence/validation/).

## Dedicated live lab

The commands below change the dedicated lab environment. They are not needed to read or reproduce saved results.

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf3 python3-venv python3-pip git iproute2 procps iputils-ping
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl start openvswitch-switch
```

`requirements.txt` records the original controller environment. System packages are not pinned by apt; record actual versions before new acquisition. Optional fitting dependencies are recorded separately in `requirements-ml.txt`; do not refit or change the frozen model to reproduce reported results.

In Terminal A, from the repository:

```bash
SDN_PATH=primary .venv/bin/osken-manager --ofp-tcp-listen-port 6653 diamond_controller.py
```

In Terminal B, when no other Mininet experiment is active:

```bash
sudo mn -c
sudo mn --custom topology.py --topo diamond --link tc --arp --controller remote,ip=127.0.0.1,port=6653 --switch ovs,protocols=OpenFlow13 --wait
```

At `mininet>`, verify `pingall` gives 12/12 replies, baseline s1/s4 uplinks use port 3 and the expected shaped classes exist. Live trial wrappers apply and restore the recorded calibration. Their admission and restoration checks are part of the experiment; do not bypass them.

The historical matched batch is complete. Do not reuse its registry or replace its runs. For new live replay, use the separate clean-clone procedure in [LIVE_REPLAY.md](docs/LIVE_REPLAY.md); retain the frozen model/protocol and report fresh outcomes separately.

To stop, enter `exit` in Mininet and Ctrl+C in the controller terminal. Refer to [protocol notes](docs/PROTOCOL_INDEX.md) for individual wrappers. Older setup and diagnostic descriptions remain in [docs/history](docs/history/) and the raw checkpoint.
