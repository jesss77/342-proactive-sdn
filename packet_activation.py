"""Bounded Linux capture, explicit clock mapping, and strict classic-PCAP decoding."""
from pathlib import Path
import json
import os
import re
import signal
import struct
import subprocess
import threading
import time

FLOW_FILTER = 'udp and src host 10.0.0.1 and dst host 10.0.0.2'
INTERFACES = ['s1-eth3', 's1-eth4']
HEADER = struct.Struct('!4s16sQQ')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def clock_sample():
    before = time.monotonic_ns()
    wall = time.time_ns()
    after = time.monotonic_ns()
    return dict(before_ns=before, wall_ns=wall, after_ns=after)


class ClockProbe:
    def __init__(self, path):
        self.path = Path(path); self.stop_event = threading.Event(); self.error = None
        self.cpu_seconds = None; self.elapsed_s = None
        self.thread = threading.Thread(target=self.work, daemon=True, name='activation-clock-map')

    def work(self):
        cpu = time.thread_time_ns(); started = time.monotonic()
        try:
            with self.path.open('x') as f:
                while True:
                    f.write(json.dumps(clock_sample()) + '\n'); f.flush()
                    if self.stop_event.wait(.5):
                        f.write(json.dumps(clock_sample()) + '\n'); f.flush()
                        return
        except BaseException as error:
            self.error = repr(error)
        finally:
            self.cpu_seconds = (time.thread_time_ns()-cpu)/1e9
            self.elapsed_s = time.monotonic()-started

    def start(self):
        self.thread.start()
        deadline = time.monotonic()+5
        while not (self.path.exists() and self.path.stat().st_size):
            require(self.error is None and time.monotonic() < deadline, 'Clock probe startup failed: '+str(self.error))
            time.sleep(.01)

    def stop(self):
        self.stop_event.set(); self.thread.join(timeout=5)
        require(not self.thread.is_alive() and self.error is None, 'Clock probe failed: ' + str(self.error))
        return dict(cpu_seconds=self.cpu_seconds,elapsed_s=self.elapsed_s)


def clock_bounds(rows, start_ns, finish_ns):
    require(len(rows) >= 100, 'Insufficient clock samples')
    previous = None; offsets = []
    for r in rows:
        a, w, b = (r[k] for k in ['before_ns', 'wall_ns', 'after_ns'])
        require(all(type(v) is int for v in [a, w, b]) and 0 <= b-a <= 10_000_000,
                'Clock sampling bracket exceeds 10 ms or is invalid')
        if previous is not None:
            require(0 < a-previous <= 2_000_000_000, 'Clock sample gap/nonmonotonicity')
        previous = a
        offsets.extend([w-b, w-a])
    require(rows[0]['before_ns'] <= start_ns and rows[-1]['after_ns'] >= finish_ns,
            'Clock samples do not bracket source')
    lo, hi = min(offsets), max(offsets)
    require(hi-lo <= 10_000_000, 'Observed wall/monotonic offset envelope exceeds 10 ms')
    return dict(offset_low_ns=lo, offset_high_ns=hi, observed_envelope_ns=hi-lo,
                samples=len(rows), first_monotonic_ns=rows[0]['before_ns'], last_monotonic_ns=rows[-1]['after_ns'], scope='Observed clock-pair envelope, not a bound on unsampled jumps or kernel timestamp accuracy')


def tcpdump_stats(text):
    result = {}
    for key, label in [('captured', 'packets? captured'), ('received_by_filter', 'packets? received by filter'),
                       ('dropped_by_kernel', 'packets? dropped by kernel')]:
        matches = re.findall(r'^\s*(\d+) ' + label + r'\s*$', text, re.M)
        require(len(matches) == 1, 'Missing/ambiguous capture statistic: ' + key)
        result[key] = int(matches[0])
    dropped = re.findall(r'^\s*(\d+) packets? dropped by interface\s*$', text, re.M)
    result['dropped_by_interface'] = int(dropped[0]) if dropped else None
    require(result['dropped_by_kernel'] == 0 and result['dropped_by_interface'] in [None, 0],
            'Capture reported dropped packets')
    return result


class Capture:
    def __init__(self, folder, interface):
        require(interface in INTERFACES, 'Unsupported capture interface')
        self.folder = Path(folder); self.interface = interface; self.proc = None; self.log = None
        self.started = None; self.summary = None
        self.command = ['tcpdump', '-n', '-p', '-i', interface, '-Q', 'out', '-j', 'host',
            '--time-stamp-precision=nano', '-s', '128', '-B', '4096', '-Z', 'root',
            '-w', str(self.folder / (interface + '.pcap')), FLOW_FILTER]

    def start(self):
        require(not (self.folder / (self.interface + '.pcap')).exists(), 'Refuse to overwrite capture')
        self.log = (self.folder / (self.interface + '.tcpdump.log')).open('x')
        self.started = time.monotonic()
        self.proc = subprocess.Popen(self.command, stdout=subprocess.DEVNULL, stderr=self.log,
                                     env=dict(os.environ, LC_ALL='C'))
        deadline = time.monotonic()+5
        while True:
            text = (self.folder / (self.interface + '.tcpdump.log')).read_text()
            if self.proc.poll() is not None:
                raise RuntimeError('Capture startup failed: ' + text)
            if 'listening on ' + self.interface + ',' in text:
                return
            require(time.monotonic() < deadline, 'Capture readiness timeout')
            time.sleep(.02)

    def stop(self):
        if self.summary is not None:
            return self.summary
        usage = None; killed = False
        try:
            if self.proc is not None and self.proc.returncode is None:
                # Do not reap via Popen.poll/wait: wait4 supplies per-capture CPU.
                self.proc.send_signal(signal.SIGINT)
                deadline = time.monotonic()+5
                while True:
                    pid, status, usage = os.wait4(self.proc.pid, os.WNOHANG)
                    if pid:
                        self.proc.returncode = os.waitstatus_to_exitcode(status)
                        break
                    if time.monotonic() >= deadline:
                        self.proc.kill(); killed = True
                        _, status, usage = os.wait4(self.proc.pid, 0)
                        self.proc.returncode = os.waitstatus_to_exitcode(status)
                        break
                    time.sleep(.02)
            self.summary = dict(command=self.command, exit=self.proc.returncode if self.proc else None,
                forced_kill=killed, elapsed_s=time.monotonic()-self.started if self.started else None,
                cpu_seconds=(usage.ru_utime+usage.ru_stime) if usage else None)
            return self.summary
        finally:
            if self.log is not None:
                self.log.close()


def decode_frame(data, wire_length, sender, port):
    require(len(data) >= 14, 'Truncated Ethernet header')
    ether = struct.unpack_from('!H', data, 12)[0]; offset = 14; tags = 0
    while ether in [0x8100, 0x88a8]:
        require(tags < 2 and len(data) >= offset+4, 'Invalid/truncated VLAN tags')
        ether = struct.unpack_from('!H', data, offset+2)[0]; offset += 4; tags += 1
    require(ether == 0x0800 and len(data) >= offset+20, 'Expected IPv4 packet')
    ihl = (data[offset] & 15)*4
    require(data[offset] >> 4 == 4 and 20 <= ihl <= 60 and len(data) >= offset+ihl+8+HEADER.size,
            'Truncated/invalid IP, UDP or identity header')
    total = struct.unpack_from('!H', data, offset+2)[0]
    fragment = struct.unpack_from('!H', data, offset+6)[0]
    require(data[offset+9] == 17 and fragment & 0x3fff == 0, 'Non-UDP or fragmented packet')
    require(data[offset+12:offset+16] == bytes([10,0,0,1]) and data[offset+16:offset+20] == bytes([10,0,0,2]),
            'Wrong selected host pair')
    udp = offset+ihl
    src, dst, length, _ = struct.unpack_from('!HHHH', data, udp)
    require(dst == port and length == 8+sender['payload_bytes'] and total == ihl+length
            and wire_length >= offset+total, 'Wrong UDP port/payload or wire length')
    magic, token, seq, sent = HEADER.unpack_from(data, udp+8)
    require(magic == b'S342' and token.hex() == sender['run_id'], 'Wrong native flow identity')
    require(seq < sender['sent_packets'] and sender['start_monotonic_ns'] <= sent <= sender['end_monotonic_ns'],
            'Packet sequence/time outside native sender')
    return dict(sequence=seq, sent_monotonic_ns=sent, source_port=src)


def read_pcap(path, sender, port):
    magics = {b'\xd4\xc3\xb2\xa1': ('<', 1000), b'\xa1\xb2\xc3\xd4': ('>',1000),
              b'\x4d\x3c\xb2\xa1': ('<',1), b'\xa1\xb2\x3c\x4d': ('>',1)}
    packets = []; seen = set(); previous = None
    with Path(path).open('rb') as f:
        magic = f.read(4); require(magic in magics, 'Unsupported PCAP format')
        order, unit = magics[magic]
        header = f.read(20); require(len(header) == 20, 'Truncated PCAP global header')
        major, minor, _, _, snaplen, link = struct.unpack(order+'HHIIII', header)
        require((major, minor) == (2,4) and snaplen == 128 and link == 1, 'Unexpected PCAP version/snaplen/link type')
        while True:
            header = f.read(16)
            if not header:
                break
            require(len(header) == 16, 'Truncated PCAP record header')
            seconds, fraction, caplen, original = struct.unpack(order+'IIII', header)
            require(0 < caplen <= snaplen and caplen <= original and fraction < 1_000_000_000//unit,
                    'Invalid PCAP record lengths/timestamp')
            data = f.read(caplen); require(len(data) == caplen, 'Truncated PCAP record data')
            packet = decode_frame(data, original, sender, port)
            stamp = seconds*1_000_000_000+fraction*unit
            require(previous is None or stamp >= previous, 'Capture clock went backwards')
            require(packet['sequence'] not in seen, 'Duplicate captured datagram')
            seen.add(packet['sequence']); previous = stamp
            packets.append(dict(packet, capture_epoch_ns=stamp))
    return dict(timestamp_unit_ns=unit, snaplen=snaplen, linktype=link, records=packets)


def analyze_capture(folder, sender, receiver, port, bounds, action):
    folder = Path(folder); captures = {}; by_path = {}
    capture_meta = json.loads((folder / 'capture-processes.json').read_text())
    for dev in INTERFACES:
        meta = capture_meta[dev]
        require(meta['exit'] == 0 and not meta['forced_kill'] and meta['cpu_seconds'] is not None,
                'Capture process exit/usage unavailable')
        parsed = read_pcap(folder / (dev+'.pcap'), sender, port)
        require(parsed['timestamp_unit_ns'] == 1, 'Expected requested nanosecond savefile precision')
        stats = tcpdump_stats((folder/(dev+'.tcpdump.log')).read_text())
        require(stats['captured'] == len(parsed['records']), 'Capture counter/savefile count mismatch')
        for packet in parsed['records']:
            lo = packet['capture_epoch_ns']-bounds['offset_high_ns']
            hi = packet['capture_epoch_ns']-bounds['offset_low_ns']
            require(hi >= packet['sent_monotonic_ns'], 'Capture/monotonic mapping precedes embedded send time')
            require(hi >= bounds['first_monotonic_ns'] and lo <= bounds['last_monotonic_ns'], 'Capture timestamp outside clock observation window')
            packet.update(observed_monotonic_low_ns=lo, observed_monotonic_high_ns=hi)
        by_path[dev] = parsed['records']
        captures[dev] = dict(records=len(parsed['records']), stats=stats, process=meta,
                             timestamp_unit_ns=1, linktype=1, snaplen=128)
    primary, alternate = (by_path[d] for d in INTERFACES)
    a, b = ({p['sequence'] for p in packets} for packets in [primary, alternate])
    require(not a.intersection(b), 'Same datagram observed on both paths')
    require(len(a | b) == sender['sent_packets'], 'Selected-egress capture counts do not reconcile with native sender')
    require(primary, 'Primary-path data not observed')
    timing = None
    if action is not None:
        require(alternate, 'Claimed switch has no selected UDP observation on alternate path')
        first = alternate[0]; low = first['observed_monotonic_low_ns']/1e9; high = first['observed_monotonic_high_ns']/1e9
        require(high >= action['started'], 'Alternate observation precedes programming')
        timing = dict(first_alternate_packet=first, last_primary_packet=primary[-1],
            first_alternate_after_program_start_s=[low-action['started'], high-action['started']],
            first_alternate_after_decision_s=[low-action['decision_at'], high-action['decision_at']],
            first_alternate_after_observation_s=[low-action['admission']['observed_at'],high-action['admission']['observed_at']],
            primary_tail_minus_first_alternate_s=(primary[-1]['capture_epoch_ns']-first['capture_epoch_ns'])/1e9,
            meaning='First matching UDP observed leaving selected switch on alternate egress; includes service to this tap, not atomic flow-mod activation, receiver delivery or prevented onset')
    else:
        require(not alternate, 'Alternate packets appeared without a recorded action')
    return dict(captures=captures, timing=timing, observed_switch=bool(alternate),
                captured_union_datagrams=len(a | b), records=by_path)
