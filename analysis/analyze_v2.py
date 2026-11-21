"""Summarize completed V2 trials into CSV, Markdown tables, and PNG figure."""
import csv
import json
from pathlib import Path
import statistics

BASE = Path(__file__).resolve().parents[1]
STATE = BASE / 'results/v2-batch.json'
OUT = BASE / 'results/v2-report'

POLICIES = ['fixed', 'reactive', 'early_warning', 'ml']
SCENARIOS = ['ramp', 'bursty']
BG_LEVELS = [0, 4_000_000, 14_000_000]


def fmt(vals, digits=3):
    if not vals:
        return 'n/a'
    m = statistics.mean(vals)
    return f'{m:.{digits}f} [{min(vals):.{digits}f}, {max(vals):.{digits}f}]'


def main():
    data = json.loads(STATE.read_text())
    rows = data['completed']
    if not rows:
        raise SystemExit('No completed trials in results/v2-batch.json yet.')
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. Save full per-trial CSV
    with (OUT / 'v2_trials.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # 2. Build clean Markdown tables ready for your IEEE paper
    lines = [
        '# Version 2 Results: Busy Alternate-Path Admission & Proactive Rerouting',
        '',
        f'Completed trials: **{len(rows)}** (Failed/retried attempts logged: {len(data["failed"])})',
        '',
        '| Scenario | `s3` BG (Mbit/s) | Policy | Goodput mean [range] (Mbit/s) | UDP loss mean [range] (%) | RTT p95 mean [range] (ms) | Switches | Total Denials | `s2` Drops | `s3` Drops | BG Loss (%) |',
        '| --- | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for scenario in SCENARIOS:
        for bg in BG_LEVELS:
            for policy in POLICIES:
                g = [r for r in rows if (r['scenario'], r['bg_bps'], r['policy']) == (scenario, bg, policy)]
                if not g:
                    continue
                bg_loss = statistics.mean(r.get('bg_loss_percent', 0.0) for r in g)
                lines.append(
                    f"| {scenario} | {bg // 1_000_000} | {policy} | "
                    f"{fmt([r['receiver_mbps'] for r in g])} | "
                    f"{fmt([r['udp_loss_percent'] for r in g])} | "
                    f"{fmt([r['rtt_p95_ms'] for r in g], 1)} | "
                    f"{sum(r['actions'] for r in g)}/{len(g)} | "
                    f"{sum(r['denials'] for r in g)} | "
                    f"{sum(r['s2_drops'] for r in g)} | "
                    f"{sum(r['s3_drops'] for r in g)} | "
                    f"{bg_loss:.3f} |"
                )

    md_path = OUT / 'V2_RESULTS.md'
    md_path.write_text('\n'.join(lines) + '\n')
    print(md_path.read_text())

    # 3. Generate publication-ready figure
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        colors = {'fixed': '#555555', 'reactive': '#0072B2', 'early_warning': '#D55E00', 'ml': '#8D3C91'}
        fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), layout='constrained')
        for r_idx, scenario in enumerate(SCENARIOS):
            for c_idx, bg in enumerate(BG_LEVELS):
                ax = axes[r_idx, c_idx]
                for p_idx, policy in enumerate(POLICIES):
                    vals = [r['udp_loss_percent'] for r in rows
                            if (r['scenario'], r['bg_bps'], r['policy']) == (scenario, bg, policy)]
                    if vals:
                        ax.bar(p_idx, statistics.mean(vals), color=colors[policy], alpha=0.85, width=0.6)
                        ax.scatter([p_idx] * len(vals), vals, color='black', s=22, zorder=4)
                ax.set_xticks(range(4), ['Fixed', 'Reactive', 'Early', 'ML'], rotation=15)
                if r_idx == 0:
                    ax.set_title(f's3 BG = {bg // 1_000_000} Mbit/s')
                if c_idx == 0:
                    ax.set_ylabel(f'{scenario.capitalize()}\nUDP loss (%)')
                ax.grid(axis='y', alpha=0.25)
        fig.suptitle('Version 2: UDP Loss Across Alternate-Path Background Loads', fontsize=14)
        fig.savefig(OUT / 'v2_udp_loss.png', dpi=200, bbox_inches='tight')
        plt.close(fig)
        print('Saved plot:', OUT / 'v2_udp_loss.png')
    except ImportError:
        print('matplotlib not installed; CSV and V2_RESULTS.md saved cleanly.')


if __name__ == '__main__':
    main()
