"""Build the final-review figures and numerical tables from verified inputs."""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows([header, *rows])


def save_plot(fig, output, name):
    fig.savefig(output / (name + ".png"), dpi=320)
    fig.savefig(output / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def make_paired(plot_data, output):
    rows = read_csv(plot_data / "paired-differences.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.25, 2.35), layout="constrained")
    for ax, version, title in zip(axes, ("V1", "V2"), ("V1: idle alternate", "V2: 4 Mbit/s background")):
        group = [row for row in rows if row["cohort"] == version]
        seeds = [int(row["seed"]) for row in group]
        values = [float(row["delta_loss_pp"]) for row in group]
        ax.axhline(0, color="#656565", lw=0.8)
        ax.scatter(seeds, values, color="#633583", s=28, zorder=3)
        ax.set(title=title, xlabel="Matched seed", xticks=seeds, xlim=(40.7, 43.3))
        ax.margins(y=0.28)
        ax.grid(axis="y", alpha=0.2)
        for seed, value in zip(seeds, values):
            ax.annotate(f"{value:+.3f}", (seed, value), xytext=(0, 7 if value >= 0 else -12),
                        textcoords="offset points", ha="center", fontsize=7.5)
    axes[0].set_ylabel("ML minus trend loss (pp)")
    save_plot(fig, output, "02-paired-differences")


def make_capture(plot_data, output):
    source = read_csv(plot_data / "captured-source.csv")
    queues = read_csv(plot_data / "captured-queues.csv")
    events = read_json(plot_data / "capture-events.json")
    decision, egress = events["decision_s"], events["first_alternate_egress_s"]
    fig = plt.figure(figsize=(3.5, 3.8), layout="constrained")
    grid = fig.add_gridspec(4, 1, height_ratios=[1, 1, 1, 0.42])
    top = fig.add_subplot(grid[0])
    util = fig.add_subplot(grid[1], sharex=top)
    queue = fig.add_subplot(grid[2], sharex=top)
    detail = fig.add_subplot(grid[3])
    top.plot([float(r["source_midpoint_s"]) for r in source],
             [float(r["sender_payload_mbps"]) for r in source], color="#333333", lw=1)
    top.set_ylabel("UDP payload\n(Mbit/s)")
    for path, color, label in [("primary", "#0072B2", "Primary"), ("alternate", "#009E73", "Alternate")]:
        times = [float(r[f"{path}_query_midpoint_s"]) for r in queues]
        util.plot(times, [float(r[f"{path}_utilization"]) for r in queues], color=color, lw=1, label=label)
        queue.plot(times, [int(r[f"{path}_queue_packets"]) for r in queues], color=color, lw=0.9)
    util.axhline(events["threshold"], color="#666666", lw=0.8, ls=":", label="0.85 target")
    util.set_ylabel("Utilization")
    lower, upper = util.get_ylim()
    util.set_ylim(lower, upper + 0.20)
    util.legend(loc="upper right", ncol=3, fontsize=6.4, frameon=False, borderpad=0.2,
                handlelength=1.15, columnspacing=0.8)
    queue.set(ylabel="Queue\n(packets)", xlabel="Seconds from sender start")
    for ax in (top, util, queue):
        ax.axvspan(decision, egress, color="#9365aa", alpha=0.40)
        ax.set_xlim(0, 60)
        ax.grid(axis="y", alpha=0.20)
    for ax in (top, util):
        ax.tick_params(labelbottom=False)
    for time, color, marker, label in [
        (0, "#D55E00", "o", "Decision"),
        ((egress - decision) * 1000, "#633583", "D", "First alternate UDP"),
    ]:
        detail.scatter(time, 0, color=color, marker=marker, s=20, zorder=3)
        detail.annotate(label, (time, 0), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=7)
    detail.set(xlim=(-21, 149), ylim=(-0.1, 0.42), yticks=[], xticks=[0, 50, 100],
               xlabel="Milliseconds from decision")
    detail.spines["left"].set_visible(False)
    save_plot(fig, output, "03-aligned-captured-trace")


def make_adverse(trace, output):
    fig, axes = plt.subplots(2, 1, figsize=(3.5, 2.55), sharex=True, layout="constrained")
    for run, color, label, rail in zip(trace, ("#C34E22", "#0072B2"), ("Reactive", "Trend"), (0.94, 0.84)):
        counter = run["queues"]["s2-eth2"]
        samples = [(r["t1_s"], r) for r in counter if 0 <= r["t1_s"] <= 60]
        x = [t for t, _ in samples]
        axes[0].plot(x, [r["utilization"] if r["valid"] else None for _, r in samples],
                     color=color, lw=0.9, label=label)
        values, cumulative = [], 0
        for _, row in samples:
            cumulative += row["root_drops_delta"] or 0
            values.append(cumulative)
        axes[1].step(x, values, where="post", color=color, lw=1.1)
        denials = [e["decision_s"] for e in run["events"] if e["rejection"]]
        axes[1].scatter(denials, [rail] * len(denials), transform=axes[1].get_xaxis_transform(),
                        color=color, marker="x", lw=0.7, s=10, zorder=3)
        action = next(e for e in run["events"] if e["applied"])
        for ax in axes:
            ax.axvline(action["started_s"], color=color, ls="--", lw=1)
    axes[0].axhline(0.85, color="#777777", ls=":", lw=0.7)
    axes[0].set_ylabel("Primary\nutilization")
    axes[0].legend(loc="lower left", ncol=2, fontsize=7, frameon=False)
    axes[1].set(ylabel="Cumulative\nroot drops", xlabel="Seconds from each run's sender start",
                xlim=(0, 60))
    for ax in axes:
        ax.grid(axis="y", alpha=0.20)
    save_plot(fig, output, "05-delayed-reactive-trace")


def build(repo, replay, out):
    out.mkdir(parents=True, exist_ok=True)
    plot_data = replay / "paper/plot-data"
    v2 = read_csv(replay / "paper/v2-trials.csv")
    assert len(v2) == 72
    groups = []
    labels = dict(fixed="Fixed", reactive="Reactive", early_warning="Trend", ml="ML")
    for scenario in ("ramp", "bursty"):
        for bg in (0, 4, 14):
            for policy, name in labels.items():
                group = [r for r in v2 if (r["scenario"], int(r["bg_bps"]), r["policy"]) ==
                         (scenario, bg * 1_000_000, policy)]
                assert len(group) == 3
                loss, goodput, rtt = [[float(r[k]) for r in group] for k in
                                      ("udp_loss_percent", "receiver_mbps", "rtt_p95_ms")]
                groups.append(dict(scenario=scenario, bg=bg, policy=name, n=3,
                                   loss=statistics.mean(loss), loss_min=min(loss), loss_max=max(loss),
                                   goodput=statistics.mean(goodput), rtt=statistics.mean(rtt),
                                   moves=sum(int(r["actions"]) for r in group),
                                   denials=sum(int(r["denials"]) for r in group),
                                   drops=sum(int(r["s2_drops"]) for r in group)))
    main = [r for r in groups if (r["scenario"], r["bg"]) == ("bursty", 4)]
    assert [(r["moves"], r["denials"], r["drops"]) for r in main][1:] == [
        (0, 207, 25882), (2, 143, 13765), (3, 3, 903)]
    write_csv(out / "v2-all-conditions.csv", list(groups[0]), [list(r.values()) for r in groups])

    heldout = read_json(replay / "heldout/test_report.json")
    metrics = []
    for method, report in [("ML", heldout["metrics"]), ("Trend", heldout["baselines"]["past_trend"])]:
        for scenario in ("ramp", "bursty", "pooled"):
            row = report["rows"]["pooled"] if scenario == "pooled" else report["rows"]["by_scenario"][scenario]
            assert abs(row["accuracy"] - (row["tp"] + row["tn"]) / row["n"]) < 1e-12
            metrics.append([f"{method} / {scenario}", str(row["n"]), f"{row['precision']:.3f}",
                            f"{row['recall']:.3f}", f"{row['f1']:.3f}", f"{100*row['accuracy']:.2f}"])
    warning_leads = []
    for name, report in [("ML", heldout["metrics"]), ("Trend", heldout["baselines"]["past_trend"])]:
        for run in report["warnings"]["by_run"]:
            for lead in run["lead_s"]:
                warning_leads.append([name, run["scenario"], run["run"], lead])
    write_csv(out / "warning-leads.csv", ["method", "scenario", "run", "lead_seconds"], warning_leads)

    matched = read_json(replay / "matched/matched-report.json")["rows"]
    ml_p95 = [r["inference_wall_p95_us"] for r in matched if r["policy"] == "ml"]
    trend = next(r for r in matched if (r["scenario"], r["seed"], r["policy"]) == ("bursty", 42, "early_warning"))
    reactive = next(r for r in matched if (r["scenario"], r["seed"], r["policy"]) == ("bursty", 42, "reactive"))
    lab = replay / "inputs/lab"
    sys.path[:0] = [str(repo / "analysis"), str(lab)]
    from build_time_traces import extract
    trace = [extract(lab, row) for row in (reactive, trend)]
    (out / "adverse-trace-data.json").write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_csv(out / "v1-adverse-pair.csv", ["policy", "run", "loss_percent", "denials", "program_start_s"],
              [[r["policy"], r["folder"], r["udp_loss_percent"], r["denials"],
                next(e["started_s"] for e in tr["events"] if e["applied"])]
               for r, tr in zip((reactive, trend), trace)])
    result = dict(groups=groups, accuracy=metrics, v1_p95_range=[min(ml_p95), max(ml_p95)],
                  warning_leads=warning_leads, moderate_loss_difference=main[-1]["loss"] - main[-2]["loss"])
    (out / "review-tables.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    plt.rcParams.update({"font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42})
    make_paired(plot_data, out)
    make_capture(plot_data, out)
    make_adverse(trace, out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.repo.resolve(), args.replay.resolve(), args.output.resolve())
