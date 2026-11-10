from mininet.topo import Topo

class Diamond(Topo):
    def build(self):
        switches = {
            i: self.addSwitch(
                's%d' % i, dpid='%016x' % i,
                protocols='OpenFlow13', failMode='secure')
            for i in range(1, 5)
        }
        hosts = {
            i: self.addHost(
                'h%d' % i, ip='10.0.0.%d/24' % i,
                mac='00:00:00:00:00:%02x' % i)
            for i in range(1, 5)
        }
        common = dict(
            delay='1ms', max_queue_size=50,
            gro=False, txo=False, rxo=False)

        for host, switch, port in [
                (1, 1, 1), (3, 1, 2),
                (2, 4, 1), (4, 4, 2)]:
            self.addLink(
                hosts[host], switches[switch],
                port1=0, port2=port, bw=100, **common)

        for a, b, pa, pb, bw in [
                (1, 2, 3, 1, 100),
                (2, 4, 2, 3, 10),
                (1, 3, 4, 1, 20),
                (3, 4, 2, 4, 20)]:
            self.addLink(
                switches[a], switches[b],
                port1=pa, port2=pb, bw=bw, **common)

topos = {'diamond': Diamond}
