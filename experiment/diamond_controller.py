import os
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3

class DiamondController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = os.environ.get('SDN_PATH', 'primary')
        if self.path not in ('primary', 'alternate'):
            raise ValueError('SDN_PATH must be primary or alternate')

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_ready(self, event):
        dp = event.msg.datapath
        p = dp.ofproto_parser
        uplink = 3 if self.path == 'primary' else 4
        routes = {
            1: {1: 1, 3: 2, 2: uplink, 4: uplink},
            4: {2: 1, 4: 2, 1: uplink, 3: uplink},
            2: {1: 1, 3: 1, 2: 2, 4: 2},
            3: {1: 1, 3: 1, 2: 2, 4: 2},
        }
        if dp.id not in routes:
            self.logger.error('Unexpected switch ID %s', dp.id)
            return
        for host, port in routes[dp.id].items():
            actions = [p.OFPActionOutput(port)]
            instructions = [p.OFPInstructionActions(
                dp.ofproto.OFPIT_APPLY_ACTIONS, actions)]
            dp.send_msg(p.OFPFlowMod(
                datapath=dp, priority=100,
                match=p.OFPMatch(
                    eth_dst='00:00:00:00:00:%02x' % host),
                instructions=instructions))
        self.logger.info('Sent %s route rules to s%s', self.path, dp.id)
