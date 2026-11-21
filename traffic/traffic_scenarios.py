"""Deterministic segmented pilots and persistent-flow schedules; engines are explicit."""
import random
import math


def schedule(name='steady', rate=3_000_000, duration=20, seed=1):
    if name == 'steady':
        rows = [(rate, duration)]
    elif name == 'ramp':
        rows = [(bps * 1_000_000, 4) for bps in [3, 6, 9, 12, 15, 12, 9, 6, 3]]
    elif name == 'bursty':
        rng = random.Random(seed)
        rows = [(3_000_000 if i % 2 == 0 else rng.choice([12, 15]) * 1_000_000,
                 rng.choice([2, 3, 4])) for i in range(12)]
    else:
        raise ValueError('Unknown traffic scenario')
    if any(not isinstance(bps, int) or bps <= 0 or seconds <= 0 for bps, seconds in rows):
        raise ValueError('Positive integer rates and durations required')
    return [dict(segment=i, requested_bps=bps, requested_seconds=seconds)
            for i, (bps, seconds) in enumerate(rows)]


def continuous_schedule(name='steady', rate=3_000_000, duration=20, seed=1):
    """Persistent-flow schedule. Linear ramps and abrupt bursts are distinct cases."""
    if (not isinstance(rate, int) or isinstance(rate, bool) or rate <= 0
            or not math.isfinite(duration) or duration <= 0):
        raise ValueError('Positive integer rate and finite duration required')
    rng = random.Random(seed)
    if name == 'steady':
        rows = [dict(requested_bps=rate, requested_seconds=duration)]
    elif name == 'ramp':
        low = max(1, round(rate*rng.uniform(.2, .3)))
        high = max(1, round(rate*rng.uniform(1.15, 1.35)))
        rising = duration*rng.uniform(.4, .6)
        rows = [dict(requested_bps=low, end_bps=high, requested_seconds=rising),
                dict(requested_bps=high, end_bps=low, requested_seconds=duration-rising)]
    elif name == 'bursty':
        rows, elapsed = [], 0.0
        while elapsed < duration:
            seconds = min(rng.uniform(2, 5), duration-elapsed)
            value = max(1, round(rate*(.25 if len(rows)%2 == 0 else rng.uniform(1, 1.25))))
            rows.append(dict(requested_bps=value, requested_seconds=seconds))
            elapsed += seconds
    else:
        raise ValueError('Unknown continuous scenario')
    return [dict(row, segment=i) for i, row in enumerate(rows)]
