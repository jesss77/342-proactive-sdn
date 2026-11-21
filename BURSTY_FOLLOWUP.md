# Bounded bursty follow-up — four new matched seeds

This separate follow-up implements the [reserved design](docs/BURSTY_FOLLOWUP_PLAN.md).
It does not resume either failed supplement, change the original 36-trial
benchmark, or retune a policy. The completed activation pilot was independently
replayed from checkpoint `20261121-020916`, SHA-256
`7d4c4fdcabe24b952e69fd0a078382ffbd34f0416a78ae45edd41fb958267c16`.
That pilot provides a current clean loaded window, not proof that the earlier
intermittent failure has been fixed.

## Registered cells

| Seed | Exact four-policy order |
| --- | --- |
| 51 | fixed, reactive, ml, early_warning |
| 52 | reactive, early_warning, fixed, ml |
| 53 | early_warning, ml, reactive, fixed |
| 54 | ml, fixed, early_warning, reactive |

Every policy occupies each position once and follows every other policy once.
Each cell uses the unchanged shared runner: bursty, 60 seconds, 11.5 Mbit/s
schedule scale, 1,200-byte UDP payload, 250 ms four-queue collector, same dual
profile/default buffers, one vCPU/tsc, frozen Decision Tree and threshold.
There is no tcpdump or extra activation clock probe. Record actual sender
rate, pacing, host conditions, resource use, denials and every no-action or
unnecessary action. Jess reports plugged in with other work still running.

## Acquisition and stopping

The additive installer retains all 81 existing source/artifact files unchanged.
It starts no traffic. The runner verifies the completed activation evidence,
older failed evidence, current source/model pins and reserved seeds unused.
Each block records environment, checks that no project source/collector or
branch capture is active, then runs the original full 60-second idle readiness
check. This verifies primary routing and idle monitoring; it cannot guarantee
loaded success.

Only one complete four-policy block can run per explicit call. A registry and
attempt record are saved before acquisition. An endpoint/source/collector,
identity, execution or restoration failure stops the batch and preserves the
failed reference plus newly created raw folders. No retries, seed replacement,
registry deletion, quality relaxation or automatic recovery is provided.
Adverse QoS, admission denials and no switch are outcomes, not quality failures.

First call, existing T2 Mininet CLI:

```python
py exec(compile(open('/home/jess/342-proactive-sdn/run_bursty_followup.py').read(), '/home/jess/342-proactive-sdn/run_bursty_followup.py', 'exec'), {'net': net, '__file__': '/home/jess/342-proactive-sdn/run_bursty_followup.py', 'limit': 4})
```

Expect approximately six minutes: idle readiness, four 60-second trials and
setup/cleanup. Let quiet readiness finish. After the first block, export and
independently review its checkpoint before continuing. Resumption additionally
requires an external review receipt bound to that exact paused batch digest
and accepted-cell count; a repeated start command cannot acquire more traffic.
Receipts and later commands are prepared from the actual exported block,
not invented in advance. The same review gate applies between later blocks.

## Analysis

Report original seeds 41–43 and these four follow-up seeds separately. Preserve
scheduled/attempted/quality-valid counts, incomplete blocks and failure reasons.
Show each complete seed's paired ML-minus-early-warning goodput, loss, RTT and
action differences. Whole independent runs, not adjacent polling rows, support
repeatability. A combined seven-seed summary, if all blocks complete, is labeled
sensitivity analysis with cohort/session differences explicit. No ML advantage
is required. A new complete cohort narrows the repetition limitation; it does
not erase historical failures or establish a platform root-cause fix.
