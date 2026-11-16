# Setup

Use a dedicated Ubuntu machine or VM. The recorded environment was Ubuntu 24.04.5, Python 3.12.3, Mininet 2.3.0, Open vSwitch 3.3.9, iperf3 3.16 and OS-Ken 3.1.1. The VirtualBox VM had 4 vCPUs, 6 GiB RAM and a 40 GB disk. Timing problems in that VM remain unresolved.

## Install

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf3 python3-venv python3-pip git iproute2 procps iputils-ping
git clone https://github.com/jesss77/342-proactive-sdn.git
cd 342-proactive-sdn
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl start openvswitch-switch
```

Select **No** if asked to start iperf3 automatically. Each trial starts its own server. Ubuntu packages are not pinned by these commands. Record installed versions and any dependency changes before collecting results.

```bash
uname -r
python3 --version
mn --version
ovs-vsctl --version
iperf3 --version
.venv/bin/osken-manager --version
sha256sum -c results/SHA256SUMS
```

## Start the primary path

Run both terminals from the repository directory. In Terminal A:

```bash
SDN_PATH=primary .venv/bin/osken-manager --ofp-tcp-listen-port 6653 diamond_controller.py
```

In Terminal B, clean up any previous lab and start Mininet. `mn -c` must only run when no other Mininet experiment is active.

```bash
sudo mn -c
sudo mn --custom topology.py --topo diamond --link tc --arp --controller remote,ip=127.0.0.1,port=6653 --switch ovs,protocols=OpenFlow13 --wait
```

At the `mininet>` prompt:

```text
pingall
sh ovs-ofctl -O OpenFlow13 dump-flows s1
sh ovs-ofctl -O OpenFlow13 dump-flows s4
sh tc -s class show dev s2-eth2
sh tc -s qdisc show dev s2-eth2
```

Check all 12 ping replies, primary uplink port 3 on s1/s4, and the 10 Mbit/s bottleneck class. Historical Eventlet and HTB quantum warnings are recorded in the results. Successful pings alone do not verify timing or shaping accuracy.

## Record one traffic trial

Use this only with the primary route above. At `mininet>`, paste:

```text
py exec(compile(open('run_primary_trial.py').read(), 'run_primary_trial.py', 'exec'), {'net': net, '__file__': 'run_primary_trial.py'})
```

The runner sends h1 → h2 UDP at a requested 3 Mbit/s, 1,200-byte payloads, for 20 seconds. It creates a fresh directory under `results/runs/`, saving endpoint JSON/stderr, queue and UDP counters, resource samples, code hashes, source copies, commands and exit statuses. It records the current clock source without changing it. No other traffic trial should be active.

The portable runner was revised after the archived experiments. Its success and timeout handling were checked with simulated processes; a fresh Mininet traffic run is still required. A completed process is not automatically a valid performance measurement. Inspect actual duration, achieved rate, loss, sampling gaps and source/bottleneck drops.

## Stop or change route

Enter `exit` in Terminal B and press Ctrl+C in Terminal A. To test the alternate path, rebuild the network and start Terminal A with `SDN_PATH=alternate`. The primary-trial runner does not describe alternate-route measurements. Dynamic rerouting is not implemented yet.
