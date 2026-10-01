"""
A tiny network model: hosts with fixed MACs, and TCP connections that
keep proper sequence/acknowledgement numbers so Wireshark sees clean
conversations (no false 'TCP Retransmission' rows).
"""
from . import packets as P


class Net:
    def __init__(self, profile, rng):
        self.profile = profile
        self.rng = rng
        self.macs = {}
        self._ip_id = {}
        self.out = []  # list of (timestamp, frame_bytes)

    def mac(self, ip):
        if ip not in self.macs and (ip.endswith(".255") or ip == "255.255.255.255"):
            return "ff:ff:ff:ff:ff:ff"
        if ip not in self.macs and 224 <= int(ip.split(".")[0]) <= 239:
            o = [int(x) for x in ip.split(".")]
            return f"01:00:5e:{o[1] & 0x7f:02x}:{o[2]:02x}:{o[3]:02x}"
        if ip not in self.macs:
            self.macs[ip] = self.profile.mac_of(ip)
        return self.macs[ip]

    def set_mac(self, ip, mac):
        self.macs[ip] = mac

    def _ident(self, ip):
        v = self._ip_id.get(ip)
        if v is None:
            v = self.rng.randint(0, 65535)
        self._ip_id[ip] = (v + 1) & 0xFFFF
        return v

    def emit(self, t, frame):
        self.out.append((t, frame))

    def ip_frame(self, t, src, dst, proto, l4):
        ttl = 64 if src.startswith("192.168.1.") else 128
        if dst.startswith("224.0.0."):
            ttl = 1  # link-local multicast (LLMNR)
        ip = P.ipv4(src, dst, proto, l4, ident=self._ident(src), ttl=ttl)
        self.emit(t, P.ethernet(self.mac(src), self.mac(dst), 0x0800, ip))

    def udp(self, t, src, dst, sport, dport, payload):
        self.ip_frame(t, src, dst, 17, P.udp(src, dst, sport, dport, payload))

    def arp_exchange(self, t, asker, target, reply_delay=0.0004):
        """Normal ARP: broadcast who-has, unicast is-at from the real owner."""
        self.emit(t, P.arp_frame(1, self.mac(asker), asker, "00:00:00:00:00:00", target))
        self.emit(t + reply_delay, P.arp_frame(2, self.mac(target), target, self.mac(asker), asker))

    def ephemeral_port(self):
        return self.rng.randint(49152, 65535)

    def tcp(self, client, server, dport, sport=None):
        return TcpConn(self, client, server, sport or self.ephemeral_port(), dport)


class TcpConn:
    def __init__(self, net, client, server, sport, dport):
        self.net = net
        self.c, self.s = client, server
        self.sport, self.dport = sport, dport
        self.c_seq = net.rng.getrandbits(32)
        self.s_seq = net.rng.getrandbits(32)

    def _send(self, t, from_client, flags, payload=b""):
        if from_client:
            seg = P.tcp(self.c, self.s, self.sport, self.dport, self.c_seq, self.s_seq, flags, payload, 64240)
            self.net.ip_frame(t, self.c, self.s, 6, seg)
            self.c_seq += len(payload) + (1 if flags & (P.TCP_SYN | P.TCP_FIN) else 0)
        else:
            seg = P.tcp(self.s, self.c, self.dport, self.sport, self.s_seq, self.c_seq, flags, payload, 8192)
            self.net.ip_frame(t, self.s, self.c, 6, seg)
            self.s_seq += len(payload) + (1 if flags & (P.TCP_SYN | P.TCP_FIN) else 0)

    def open(self, t, rtt=0.001):
        """3-way handshake. Returns time the connection is usable."""
        seg = P.tcp(self.c, self.s, self.sport, self.dport, self.c_seq, 0, P.TCP_SYN, b"", 64240)
        self.net.ip_frame(t, self.c, self.s, 6, seg)
        self.c_seq += 1
        self._send(t + rtt / 2, False, P.TCP_SYN | P.TCP_ACK)
        self._send(t + rtt, True, P.TCP_ACK)
        return t + rtt

    def request(self, t, payload):
        self._send(t, True, P.TCP_PSH | P.TCP_ACK, payload)

    def reply(self, t, payload):
        self._send(t, False, P.TCP_PSH | P.TCP_ACK, payload)

    def ack_from_server(self, t):
        self._send(t, False, P.TCP_ACK)

    def ack_from_client(self, t):
        self._send(t, True, P.TCP_ACK)

    def close(self, t, rtt=0.001, by_server=False):
        self._send(t, not by_server, P.TCP_FIN | P.TCP_ACK)
        self._send(t + rtt / 2, by_server, P.TCP_FIN | P.TCP_ACK)
        self._send(t + rtt, not by_server, P.TCP_ACK)
        return t + rtt
