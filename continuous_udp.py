"""Single-flow UDP schedule generator for the shared-kernel Mininet testbed."""
import argparse
import bisect
import json
import math
from pathlib import Path
import signal
import socket
import struct
import time

HEADER = struct.Struct('!4s16sQQ')
MAGIC = b'S342'


class Schedule:
    def __init__(self, segments):
        if not segments:
            raise ValueError('Schedule cannot be empty')
        self.segments = segments
        self.ends, self.bits = [], [0.0]
        elapsed = 0.0
        for item in segments:
            rate, duration = item['requested_bps'], item['requested_seconds']
            end_rate = item.get('end_bps', rate)
            if (not isinstance(rate, int) or isinstance(rate, bool) or rate <= 0
                    or not isinstance(end_rate, int) or isinstance(end_rate, bool) or end_rate <= 0
                    or not math.isfinite(duration) or duration <= 0):
                raise ValueError('Positive integer rates and finite durations required')
            elapsed += duration
            self.ends.append(elapsed)
            self.bits.append(self.bits[-1] + (rate+end_rate)*duration/2)
        self.duration = elapsed

    def index(self, elapsed):
        return min(bisect.bisect_right(self.ends, elapsed), len(self.ends)-1)

    def cumulative_bits(self, elapsed):
        elapsed = max(0, min(elapsed, self.duration))
        index = self.index(elapsed)
        start = self.ends[index-1] if index else 0
        segment = self.segments[index]
        rate = segment['requested_bps']
        slope = (segment.get('end_bps', rate)-rate)/segment['requested_seconds']
        dt = elapsed-start
        return self.bits[index] + rate*dt + slope*dt*dt/2


class Pacer:
    def __init__(self, schedule, payload_bytes, max_burst_packets=32):
        if payload_bytes < HEADER.size or payload_bytes > 1472 or max_burst_packets <= 0:
            raise ValueError('Invalid payload or burst cap')
        self.schedule, self.packet_bits = schedule, payload_bytes*8
        self.cap = max_burst_packets*self.packet_bits
        self.credit = self.previous_bits = self.discarded_bits = 0.0

    def advance(self, elapsed):
        planned = self.schedule.cumulative_bits(elapsed)
        if planned < self.previous_bits:
            raise ValueError('Elapsed time moved backwards')
        credit = self.credit + planned-self.previous_bits
        self.previous_bits = planned
        self.discarded_bits += max(0, credit-self.cap)
        self.credit = min(credit, self.cap)
        count = int(self.credit // self.packet_bits)
        self.credit -= count*self.packet_bits
        return count


def packet(run_id, sequence, sent_ns, payload_bytes):
    token = bytes.fromhex(run_id)
    if len(token) != 16 or not HEADER.size <= payload_bytes <= 1472:
        raise ValueError('Expected 16-byte run ID and non-fragmenting UDP payload')
    return HEADER.pack(MAGIC, token, sequence, sent_ns) + bytes(payload_bytes-HEADER.size)


def decode(data, run_id, payload_bytes):
    if len(data) != payload_bytes:
        raise ValueError('Wrong packet size')
    magic, token, sequence, sent_ns = HEADER.unpack_from(data)
    if magic != MAGIC or token.hex() != run_id:
        raise ValueError('Wrong flow ID')
    return sequence, sent_ns


def save_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def signal_stop():
    state = {'stopped': False}
    def stop(_signal, _frame):
        state['stopped'] = True
    old = {s: signal.signal(s, stop) for s in [signal.SIGINT, signal.SIGTERM]}
    return state, old


def restore_signals(old):
    for sig, handler in old.items():
        signal.signal(sig, handler)


def send(host, port, plan, output, samples, payload_bytes=1200, tick_s=.005,
         max_burst_packets=32):
    if not math.isfinite(tick_s) or tick_s <= 0:
        raise ValueError('Positive finite pacing tick required')
    schedule = Schedule(plan['segments'])
    pacer = Pacer(schedule, payload_bytes, max_burst_packets)
    state, handlers = signal_stop()
    summary = dict(engine='continuous-udp-v1', run_id=plan['run_id'],
                   payload_bytes=payload_bytes, tick_s=tick_s,
                   max_burst_packets=max_burst_packets, sent_packets=0,
                   attempted_packets=0, send_errors={}, skipped_ticks=0,
                   segment_sent_packets=[0]*len(schedule.segments), error=None)
    start = time.monotonic_ns()
    summary['start_monotonic_ns'] = start
    summary['start_wall_epoch_s'] = time.time()
    deadline = previous = start/1e9
    report_at = deadline+.25
    previous_sent = 0
    max_gap = 0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, Path(samples).open('x') as log:
            summary['socket_send_buffer_bytes'] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
            sock.settimeout(.1)
            while not state['stopped']:
                now = time.monotonic()
                elapsed = now-start/1e9
                if elapsed >= schedule.duration:
                    break
                max_gap = max(max_gap, now-previous)
                previous = now
                count = pacer.advance(elapsed)
                for _ in range(count):
                    sequence = summary['sent_packets']
                    summary['attempted_packets'] += 1
                    try:
                        size = sock.sendto(packet(plan['run_id'], sequence,
                            time.monotonic_ns(), payload_bytes), (host, port))
                        if size != payload_bytes:
                            raise OSError('Short datagram send')
                        summary['sent_packets'] += 1
                        summary['segment_sent_packets'][schedule.index(elapsed)] += 1
                    except OSError as error:
                        key = str(error.errno) if error.errno is not None else type(error).__name__
                        summary['send_errors'][key] = summary['send_errors'].get(key, 0)+1
                now = time.monotonic()
                if now >= report_at:
                    log.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(),
                        elapsed_s=now-start/1e9, sent_packets=summary['sent_packets'],
                        sent_packets_delta=summary['sent_packets']-previous_sent,
                        segment=schedule.index(min(now-start/1e9, schedule.duration)),
                        discarded_budget_bits=pacer.discarded_bits))+'\n')
                    log.flush()
                    previous_sent = summary['sent_packets']
                    report_at = now+.25
                deadline += tick_s
                if deadline < now:
                    skipped = int((now-deadline)/tick_s)+1
                    summary['skipped_ticks'] += skipped
                    deadline += skipped*tick_s
                time.sleep(max(0, deadline-time.monotonic()))
    except BaseException as error:
        summary['error'] = str(error) or type(error).__name__
        raise
    finally:
        summary.update(end_monotonic_ns=time.monotonic_ns(), end_wall_epoch_s=time.time(),
            stopped_by_signal=state['stopped'], max_pacer_gap_s=max_gap,
            discarded_budget_bits=pacer.discarded_bits,
            unused_credit_bits=pacer.credit, planned_bits=schedule.bits[-1])
        summary['sent_bytes'] = summary['sent_packets']*payload_bytes
        restore_signals(handlers)
        save_json(output, summary)
    return summary


def receive(bind, port, run_id, output, samples, ready, payload_bytes=1200,
            max_duration=120):
    if not math.isfinite(max_duration) or max_duration <= 0:
        raise ValueError('Positive finite receiver timeout required')
    state, handlers = signal_stop()
    seen = set()
    summary = dict(engine='continuous-udp-v1', run_id=run_id, payload_bytes=payload_bytes,
                   unique_packets=0, duplicate_packets=0, out_of_order=0,
                   invalid_packets=0, highest_sequence=-1, jitter_ns=0.0,
                   first_received_monotonic_ns=None, last_received_monotonic_ns=None,
                   error=None)
    started = time.monotonic()
    previous_transit = None
    report_at = started+.25
    previous_unique = 0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, Path(samples).open('x') as log:
            sock.bind((bind, port))
            sock.settimeout(.05)
            summary['socket_receive_buffer_bytes'] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            save_json(ready, dict(address=sock.getsockname(), run_id=run_id))
            while not state['stopped'] and time.monotonic()-started < max_duration:
                try:
                    data, _peer = sock.recvfrom(65535)
                except socket.timeout:
                    data = None
                if data is not None:
                    received_ns = time.monotonic_ns()
                    try:
                        sequence, sent_ns = decode(data, run_id, payload_bytes)
                    except (ValueError, struct.error):
                        summary['invalid_packets'] += 1
                    else:
                        if sequence in seen:
                            summary['duplicate_packets'] += 1
                        else:
                            seen.add(sequence)
                            summary['unique_packets'] += 1
                            summary['out_of_order'] += int(sequence < summary['highest_sequence'])
                            summary['highest_sequence'] = max(summary['highest_sequence'], sequence)
                            if summary['first_received_monotonic_ns'] is None:
                                summary['first_received_monotonic_ns'] = received_ns
                            summary['last_received_monotonic_ns'] = received_ns
                            transit = received_ns-sent_ns
                            if previous_transit is not None:
                                summary['jitter_ns'] += (abs(transit-previous_transit)-summary['jitter_ns'])/16
                            previous_transit = transit
                now = time.monotonic()
                if now >= report_at:
                    log.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(),
                        unique_packets=summary['unique_packets'],
                        received_packets_delta=summary['unique_packets']-previous_unique,
                        highest_sequence=summary['highest_sequence']))+'\n')
                    log.flush()
                    previous_unique = summary['unique_packets']
                    report_at = now+.25
    except BaseException as error:
        summary['error'] = str(error) or type(error).__name__
        raise
    finally:
        summary.update(stopped_by_signal=state['stopped'],
                       stopped_monotonic_ns=time.monotonic_ns(),
                       unique_bytes=summary['unique_packets']*payload_bytes)
        restore_signals(handlers)
        save_json(output, summary)
    return summary


def canonical_summaries(sender, receiver):
    if sender['run_id'] != receiver['run_id'] or sender['payload_bytes'] != receiver['payload_bytes']:
        raise ValueError('Endpoint identity mismatch')
    if (sender.get('error') or receiver.get('error') or sender.get('stopped_by_signal')
            or sender.get('send_errors')):
        raise ValueError('Incomplete endpoint')
    sent, received = sender['sent_packets'], receiver['unique_packets']
    if not sent or not 0 <= received <= sent:
        raise ValueError('Invalid packet accounting')
    if (sender['sent_bytes'] != sent*sender['payload_bytes']
            or receiver['unique_bytes'] != received*receiver['payload_bytes']
            or receiver['highest_sequence'] >= sent):
        raise ValueError('Inconsistent endpoint byte/sequence counts')
    sender_seconds = (sender['end_monotonic_ns']-sender['start_monotonic_ns'])/1e9
    completion_ns = max(sender['end_monotonic_ns'],
                        receiver['last_received_monotonic_ns'] or sender['end_monotonic_ns'])
    receiver_seconds = (completion_ns-sender['start_monotonic_ns'])/1e9
    if min(sender_seconds, receiver_seconds) <= 0:
        raise ValueError('Invalid endpoint timing')
    missing = sent-received
    common = dict(start=0, packets=sent, lost_packets=missing,
                  lost_percent=100*missing/sent, jitter_ms=receiver['jitter_ns']/1e6)
    tx = dict(common, end=sender_seconds, seconds=sender_seconds, bytes=sender['sent_bytes'],
              bits_per_second=8*sender['sent_bytes']/sender_seconds, sender=True,
              lost_packets=0, lost_percent=0, jitter_ms=0)
    rx = dict(common, end=receiver_seconds, seconds=receiver_seconds, bytes=receiver['unique_bytes'],
              bits_per_second=8*receiver['unique_bytes']/receiver_seconds, sender=False)
    return dict(engine='continuous-udp-v1', end=dict(sum_sent=tx)), dict(
        engine='continuous-udp-v1', end=dict(sum_received=rx),
        loss_definition='successful application sends minus unique received datagrams',
        time_basis='shared guest monotonic clock; through sender end or last received packet, whichever is later')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['send', 'receive'])
    parser.add_argument('--plan', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=5202)
    parser.add_argument('--output', required=True)
    parser.add_argument('--samples', required=True)
    parser.add_argument('--ready')
    parser.add_argument('--max-duration', type=float, default=120)
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    if args.mode == 'send':
        result = send(args.host, args.port, plan, args.output, args.samples)
        if result['stopped_by_signal'] or result['send_errors']:
            raise SystemExit(1)
    else:
        if not args.ready:
            parser.error('--ready required for receiver')
        receive(args.host, args.port, plan['run_id'], args.output, args.samples,
                args.ready, max_duration=args.max_duration)
