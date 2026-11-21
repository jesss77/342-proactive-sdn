"""Shared, logged OpenFlow-1.3 action for the h1/h2 IPv4 host pair.

OS-Ken's original MAC forwarding stays in place. A reserved-cookie, higher
priority pair of edge rules selects the alternate; cleanup removes only these.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import time

COOKIE = 0x3420000000000001
COOKIE_FILTER = f'cookie=0x{COOKIE:x}/0xffffffffffffffff,table=0'
EDGES = {'s1': ('10.0.0.1', '10.0.0.2'), 's4': ('10.0.0.2', '10.0.0.1')}
BASE_PORTS = {'s1': {1:1,3:2,2:3,4:4}, 's4': {2:1,4:2,1:3,3:4},
              's2': {1:1,3:1,2:2,4:2}, 's3': {1:1,3:1,2:2,4:2}}


def ofctl(command, bridge, *args):
    # Ordinary flow-mod commands use OVS's default post-modification barrier.
    # Do not use OF1.4 bundles: the established experiment uses OpenFlow1.3.
    return ['ovs-ofctl', '-O', 'OpenFlow13', '--no-names', '--timeout=3',
            command, bridge, *args]


def owned_lines(text):
    return [line for line in text.splitlines() if
            (m := re.search(r'cookie=(0x[0-9a-fA-F]+)', line)) and int(m[1],16)==COOKIE]


def base_signature(text, switch):
    lines = [line for line in text.splitlines() if 'priority=100,' in line]
    if len(lines) != 4:
        raise RuntimeError(f'{switch}: expected exactly four baseline rules')
    for host, port in BASE_PORTS[switch].items():
        found=[line for line in lines if f'dl_dst=00:00:00:00:00:{host:02x}' in line]
        if len(found)!=1 or not re.search(r'actions=output:'+str(port)+r'\s*$',found[0]):
            raise RuntimeError(f'{switch}: primary baseline/transit rule mismatch')
    return sorted(line[line.index('priority=100,'):] for line in lines)


def verify_overlay(text, switch, route):
    lines=owned_lines(text)
    if route=='primary':
        if lines: raise RuntimeError(f'{switch}: overlay still present')
    else:
        src,dst=EDGES[switch]
        if len(lines)!=1 or not all(token in lines[0] for token in
                ['priority=200,','ip,',f'nw_src={src},',f'nw_dst={dst}']):
            raise RuntimeError(f'{switch}: selected-pair match differs')
        if not re.search(r'actions=output:4\s*$',lines[0]):
            raise RuntimeError(f'{switch}: alternate output differs')


@dataclass(frozen=True)
class Admission:
    route: str
    observed_at: float
    selected_demand_bps: float
    background_bps: float
    admission_budget_bps: float
    links_up: bool
    evidence: str

    def rejection(self, now):
        values=[self.observed_at,self.selected_demand_bps,self.background_bps,
                self.admission_budget_bps,now]
        if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
                   for v in values): return 'nonfinite_admission'
        if self.route!='alternate': return 'wrong_admission_route'
        if not 0 <= now-self.observed_at <= 2: return 'stale_admission'
        if self.links_up is not True: return 'alternate_link_down'
        if min(self.selected_demand_bps,self.background_bps)<0 or self.admission_budget_bps<=0:
            return 'invalid_admission_rate'
        if not self.evidence: return 'missing_capacity_evidence'
        if self.selected_demand_bps+self.background_bps > .8*self.admission_budget_bps:
            return 'insufficient_admission_headroom'
        return None


class RoutingAction:
    def __init__(self, execute, log_path, clock=time.monotonic, cooldown_s=5., max_actions=1):
        if not math.isfinite(cooldown_s) or cooldown_s<0 or type(max_actions) is not int or max_actions<1:
            raise ValueError('Finite nonnegative cooldown and positive integer action limit required')
        self.execute=execute;self.clock=clock;self.log_path=Path(log_path)
        self.cooldown_s=cooldown_s;self.max_actions=max_actions
        self.actions=0;self.last_action=None;self.route='primary';self.claimed=False
        self.signatures={}
        for switch in BASE_PORTS:
            text=self._command(switch,ofctl('dump-flows',switch),'initial_read')
            if owned_lines(text): raise RuntimeError('Reserved cookie already exists; refuse takeover')
            if any(int(v)>100 for v in re.findall(r'priority=(\d+)',text)):
                raise RuntimeError('Unexpected higher-priority rules; refuse takeover')
            self.signatures[switch]=base_signature(text,switch)
        self.claimed=True
        self._log(dict(event='claimed',route='primary',cookie=hex(COOKIE),
            selected_pair=['10.0.0.1','10.0.0.2'],priority=200))

    def _log(self, record):
        with self.log_path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(monotonic=self.clock(),**record))+'\n')

    def _command(self,node,args,label):
        start=self.clock();out,err,code=self.execute(node,args);end=self.clock()
        self._log(dict(event='command',label=label,node=node,args=args,
                       started=start,finished=end,elapsed_s=end-start,
                       stdout=out,stderr=err,exit=code))
        if code: raise RuntimeError(f'{node}/{label}: {err or out}')
        return out

    def verify(self,route):
        proof={}
        for switch in BASE_PORTS:
            text=self._command(switch,ofctl('dump-flows',switch),'readback_'+route)
            if base_signature(text,switch)!=self.signatures[switch]:
                raise RuntimeError('Baseline rules changed: '+switch)
            foreign=[line for line in text.splitlines() if
                     (m:=re.search(r'priority=(\d+)',line)) and int(m[1])>100
                     and line not in owned_lines(text)]
            if foreign: raise RuntimeError('Foreign overlay appeared: '+switch)
            if switch in EDGES:
                verify_overlay(text,switch,route)
            elif owned_lines(text):
                raise RuntimeError('Unexpected transit overlay')
            proof[switch]=text
        return proof

    def _program(self, route, label):
        errors=[]
        for switch,(src,dst) in EDGES.items():
            if route=='alternate':
                flow=(f'cookie=0x{COOKIE:x},table=0,priority=200,ip,'
                      f'nw_src={src},nw_dst={dst},actions=output:4')
                args=ofctl('add-flow',switch,flow)
            else:
                args=ofctl('del-flows',switch,COOKIE_FILTER)
            try: self._command(switch,args,label)
            except Exception as error: errors.append(str(error))
        if errors: raise RuntimeError('; '.join(errors))

    def request(self, admission, reason):
        if not self.claimed or self.route=='unknown':
            raise RuntimeError('Action is not in a verified owned state')
        if self.route=='alternate': return dict(applied=False,rejection='already_alternate')
        now=self.clock()
        rejection=admission.rejection(now)
        if not reason: rejection='missing_trigger_reason'
        if self.last_action is not None and now-self.last_action<self.cooldown_s:
            rejection='cooldown'
        if self.actions>=self.max_actions: rejection='action_budget'
        if rejection:
            self._log(dict(event='denied',reason=reason,rejection=rejection,
                           admission=admission.__dict__))
            return dict(applied=False,rejection=rejection)
        self.verify('primary')
        started=self.clock()
        try:
            self._program('alternate','apply_alternate')
            self.verify('alternate')
        except BaseException as error:
            rollback_error=None
            try:
                self._program('primary','rollback_primary');self.verify('primary')
                self.route='primary'
            except Exception as failure:
                self.route='unknown';rollback_error=str(failure)
            self._log(dict(event='apply_failed',error=str(error),rollback_error=rollback_error))
            raise
        finished=self.clock();self.route='alternate';self.last_action=finished;self.actions+=1
        result=dict(applied=True,route='alternate',reason=reason,started=started,
                    verified_finished=finished,command_and_readback_elapsed_s=finished-started,
                    admission=admission.__dict__)
        self._log(dict(event='applied',**result))
        return result

    def close(self):
        if not self.claimed: return
        # Cleanup bypasses policy cooldown/action budget; both edges attempted.
        try:
            self._program('primary','cleanup_primary');self.verify('primary')
        except BaseException:
            self.route='unknown';raise
        self.route='primary';self.claimed=False
        self._log(dict(event='restored',route='primary',baseline_unchanged=True))
