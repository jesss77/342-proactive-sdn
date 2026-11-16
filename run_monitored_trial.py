from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import time

base = Path("/home/jess/342-proactive-sdn")
folder = base / "results/runs" / (
    datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "-monitor-250ms"
)
folder.mkdir(parents=True)
for name in ["collect_link_diagnostic.py", "run_monitored_trial.py"]:
    shutil.copy2(base / name, folder / name)
shutil.copy2(base / "results/runs/active-session.txt",
             folder / "session-reference.txt")

scope = {
    "__name__": "trial_module",
    "__file__": str(base / "run_primary_trial.py")
}
exec(compile(Path(scope["__file__"]).read_text(),
             scope["__file__"], "exec"), scope)

with (folder / "collector.log").open("w") as log:
    collector = subprocess.Popen(
        ["/usr/bin/python3", str(base / "collect_link_diagnostic.py"),
         str(folder / "samples.jsonl"),
         "--interval", "0.25", "--duration", "35"],
        stdout=log, stderr=subprocess.STDOUT
    )
    try:
        time.sleep(2)
        if collector.poll() is not None:
            raise RuntimeError("Collector stopped early; inspect collector.log")
        trial = scope["run"](net, base, requested_bps=globals().get("requested_bps", 3000000))
        (folder / "traffic-run.txt").write_text(str(trial) + "\n")
        (trial / "measurement-context.txt").write_text(
            "Shaped primary path; 1 vCPU; 250 ms requested monitoring.\n"
            "Monitoring adds overhead; compare with unmonitored trials.\n"
            "Collector folder: " + str(folder) + "\n"
        )
        collector.wait(timeout=45)
    finally:
        if collector.poll() is None:
            collector.terminate()
            try:
                collector.wait(timeout=3)
            except subprocess.TimeoutExpired:
                collector.kill()
                collector.wait()
        (folder / "collector-exit.txt").write_text(
            str(collector.returncode) + "\n"
        )

print("Collector exit:", collector.returncode)
print("Monitoring folder:", folder)
