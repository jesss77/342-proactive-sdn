from pathlib import Path
import shutil
import subprocess

folder = Path("results/D06-kvm-clock-20261101-235818")
clock = Path("/sys/devices/system/clocksource/clocksource0/current_clocksource")
original = (folder / "clock-before.txt").read_text().strip()

try:
    shutil.copy2(__file__, folder / "comparison-driver.py")
    if clock.read_text().strip() != "kvm-clock":
        raise SystemExit("Expected kvm-clock; stopping comparison.")

    text = Path("check_default_repeats.sh").read_text()
    changes = {
        "results/D04-loopback-repeat-": str(folder / "traffic-"),
        'date -Is > "$PR3_CASE_DIR/started-at.txt"':
            'date -Is > "$PR3_CASE_DIR/started-at.txt"\n'
            f'    cat "{clock}" > "$PR3_CASE_DIR/clock-start.txt"',
        'wait "$PR3_STATS_PID"':
            'wait "$PR3_STATS_PID"\n'
            f'    cat "{clock}" > "$PR3_CASE_DIR/clock-end.txt"'
    }
    for old, new in changes.items():
        if text.count(old) != 1:
            raise SystemExit("Helper differs from expected; stopping.")
        text = text.replace(old, new, 1)

    script = folder / "traffic.sh"
    script.write_text(text)
    subprocess.run(["bash", str(script)], check=True)
finally:
    subprocess.run(
        ["sudo", "tee", str(clock)],
        input=original + "\n", text=True,
        stdout=subprocess.DEVNULL, check=True
    )
    restored = clock.read_text().strip()
    (folder / "clock-restored.txt").write_text(restored + "\n")
    print(f"\nRestored clock: {restored}", flush=True)
    if restored != original:
        raise SystemExit("Clock restoration did not match the saved setting.")
