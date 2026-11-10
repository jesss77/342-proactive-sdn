from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3

class SmokeController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_ready(self, event):
        dp = event.msg.datapath
        p = dp.ofproto_parser
        for incoming, outgoing in [(1, 2), (2, 1)]:
            actions = [p.OFPActionOutput(outgoing)]
            instructions = [p.OFPInstructionActions(
                dp.ofproto.OFPIT_APPLY_ACTIONS, actions)]
            dp.send_msg(p.OFPFlowMod(
                datapath=dp, priority=100,
                match=p.OFPMatch(in_port=incoming),
                instructions=instructions))
        self.logger.info('Sent forwarding rules for switch %s', dp.id)
