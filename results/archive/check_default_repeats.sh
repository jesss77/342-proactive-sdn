#!/usr/bin/env bash
cd ~/cmps342 || exit 1
PR3_PAIR_DIR="results/D04-loopback-repeat-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$PR3_PAIR_DIR"
cp "$0" "$PR3_PAIR_DIR/protocol.sh"
sysctl net.core.rmem_default net.core.rmem_max net.core.wmem_default net.core.wmem_max > "$PR3_PAIR_DIR/socket-limits.txt"

for PR3_MODE in default-1 default-2 default-3; do
    PR3_CASE_DIR="$PR3_PAIR_DIR/$PR3_MODE"
    mkdir -p "$PR3_CASE_DIR"
    date -Is > "$PR3_CASE_DIR/started-at.txt"
    PR3_BUFFER_ARGS=()
    if [ "$PR3_MODE" = larger ]; then
        PR3_BUFFER_ARGS=(-w 1M)
    fi

    printf '\n=== %s socket buffers ===\n' "$PR3_MODE"
    nstat -az UdpInErrors UdpRcvbufErrors UdpSndbufErrors > "$PR3_CASE_DIR/udp-before.txt"
    timeout 35s iperf3 -s -1 -B 127.0.0.1 -p 5209 -J > "$PR3_CASE_DIR/server.json" 2> "$PR3_CASE_DIR/server.err" &
    PR3_SERVER_PID=$!
    vmstat -t 1 12 > "$PR3_CASE_DIR/vmstat.txt" &
    PR3_STATS_PID=$!

    sleep 1
    timeout 30s iperf3 -c 127.0.0.1 -p 5209 -u -b 3M -l 1200 -t 10 "${PR3_BUFFER_ARGS[@]}" 2>&1 | tee "$PR3_CASE_DIR/client.txt"
    PR3_CLIENT_STATUS=${PIPESTATUS[0]}
    wait "$PR3_SERVER_PID"
    PR3_SERVER_STATUS=$?
    nstat -az UdpInErrors UdpRcvbufErrors UdpSndbufErrors > "$PR3_CASE_DIR/udp-after.txt"
    wait "$PR3_STATS_PID"

    printf 'Client exit: %s; server exit: %s\n' "$PR3_CLIENT_STATUS" "$PR3_SERVER_STATUS" | tee "$PR3_CASE_DIR/exit-status.txt"
    python3 - "$PR3_CASE_DIR" <<'PY'
import pathlib, sys
folder = pathlib.Path(sys.argv[1])
def counters(name):
    rows = (folder / name).read_text().splitlines()
    return {p[0]: int(p[1]) for row in rows
            if len(p := row.split()) >= 2 and p[0].startswith('Udp')}
before = counters('udp-before.txt')
after = counters('udp-after.txt')
summary = '\n'.join(f'{k} delta: {after[k] - before[k]}' for k in before)
print(summary)
(folder / 'udp-deltas.txt').write_text(summary + '\n')
PY
done
printf '\nSaved in: %s\n' "$PR3_PAIR_DIR"
