#!/usr/bin/env bash
set -euo pipefail
cd ~/cmps342

PR3_SESSION_DIR="results/S02-primary-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$PR3_SESSION_DIR"
printf '%s\n' "$PR3_SESSION_DIR" > results/active-session.txt

PR3_CLOCK_FILE="/sys/devices/system/clocksource/clocksource0/current_clocksource"
PR3_ORIGINAL_CLOCK=$(cat "$PR3_CLOCK_FILE")
printf '%s\n' "$PR3_ORIGINAL_CLOCK" > "$PR3_SESSION_DIR/clock-before.txt"

restore_clock() {
    printf '%s\n' "$PR3_ORIGINAL_CLOCK" | sudo tee "$PR3_CLOCK_FILE" > /dev/null
    cat "$PR3_CLOCK_FILE" | tee "$PR3_SESSION_DIR/clock-restored.txt"
}
trap restore_clock EXIT

printf 'kvm-clock\n' | sudo tee "$PR3_CLOCK_FILE" > /dev/null
cat "$PR3_CLOCK_FILE" | tee "$PR3_SESSION_DIR/clock-active.txt"
test "$(cat "$PR3_CLOCK_FILE")" = "kvm-clock"

cp topology.py diamond_controller.py requirements.txt "$0" "$PR3_SESSION_DIR/"
sha256sum topology.py diamond_controller.py requirements.txt > "$PR3_SESSION_DIR/code-sha256.txt"
date -Is > "$PR3_SESSION_DIR/started-at.txt"

sudo mn -c 2>&1 | tee "$PR3_SESSION_DIR/cleanup.log"

SDN_PATH=primary .venv/bin/osken-manager \
    --ofp-tcp-listen-port 6653 diamond_controller.py \
    2>&1 | tee "$PR3_SESSION_DIR/controller.log"
