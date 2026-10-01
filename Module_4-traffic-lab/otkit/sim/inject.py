"""
Injectors for the Day 4-5 statistical anomalies (Module 4, Section 4.3.2)
and the Day 6 attack signatures (Module 4, Table 4.3 / Section 4.5.1).

Each injector writes its packets into a fresh Net and returns a
ground-truth row describing exactly what was planted and how to see it.
"""
import datetime as dt
import random

from . import packets as P
from . import protocols as proto
from .network import Net


def utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Day 4-5 anomalies
# ---------------------------------------------------------------------------

def anomaly_write_burst(net, t, profile):
    """20 FC06 writes in 10 s from the engineering workstation (normally it never writes)."""
    src, dst = profile.ip_of("ENG-WS"), profile.ip_of("PLC-MAIN-01")
    c = net.tcp(src, dst, 502)
    tt = c.open(t)
    tid = net.rng.randint(0, 60000)
    for i in range(20):
        reg, val = net.rng.randint(0, 40), net.rng.randint(0, 3000)
        c.request(tt + i * 0.5, proto.mb_write_single_req(tid + i, reg, val))
        c.reply(tt + i * 0.5 + 0.005, proto.mb_write_single_resp(tid + i, reg, val))
    c.close(tt + 10.0)
    return dict(anomaly_type="write_burst", start=t, end=t + 10.5, src_ip=src, dst_ip=dst,
                description=f"{src} -> {dst}: 20x Modbus FC06 writes in 10 s")


def anomaly_volume_spike(net, t, profile):
    """A second OPC UA session pumping 200 packets in 5 s (~40x the normal OPC UA rate)."""
    hist, scada = profile.ip_of("HISTORIAN"), profile.ip_of("SCADA-SVR")
    c = net.tcp(hist, scada, 4840)
    tt = c.open(t)
    chan = net.rng.randint(1, 10**6)
    for i in range(100):
        ts = tt + i * 0.05
        c.request(ts, proto.ua_publish_req(ts, chan, 1, 100 + i, 100 + i, 100 + i))
        c.reply(ts + 0.004, proto.ua_publish_resp(ts, chan, 1, 100 + i, 100 + i, 100 + i, i + 1, 11, net.rng))
    c.close(tt + 5.0)
    return dict(anomaly_type="volume_spike", start=t, end=t + 5.1, src_ip=scada, dst_ip=hist,
                description=f"{scada} <-> {hist}: 200 OPC UA packets in 5 s")


def anomaly_new_source(net, t, profile, new_ip="192.168.1.99"):
    """A device never seen before starts polling PLC-MAIN-01."""
    dst = profile.ip_of("PLC-MAIN-01")
    net.set_mac(new_ip, "02:1a:2b:3c:4d:63")
    net.arp_exchange(t, new_ip, dst)
    c = net.tcp(new_ip, dst, 502)
    tt = c.open(t + 0.01)
    tid = net.rng.randint(0, 60000)
    for i in range(15):
        c.request(tt + i, proto.mb_read_req(tid + i, 3, i * 10 % 100, 10))
        c.reply(tt + i + 0.006, proto.mb_read_resp(tid + i, 3, 10, net.rng))
    c.close(tt + 15)
    return dict(anomaly_type="new_source", start=t, end=t + 15.1, src_ip=new_ip, dst_ip=dst,
                description=f"{new_ip} (never seen before) -> {dst}: 15 Modbus reads")


ANOMALIES = [anomaly_write_burst, anomaly_volume_spike, anomaly_new_source]


# ---------------------------------------------------------------------------
# Day 6 attacks
# ---------------------------------------------------------------------------

SCAN_PORTS = [21, 22, 23, 25, 53, 80, 102, 135, 139, 443, 445, 502, 1911, 2404, 4840, 8080, 20000, 44818, 47808, 3389]
OPEN_PORTS = {80, 102, 502}


def attack_recon_scan(net, t, profile, attacker, target):
    net.set_mac(attacker, _rand_mac(net.rng))
    net.arp_exchange(t, attacker, target)
    ports = SCAN_PORTS[:]
    net.rng.shuffle(ports)
    tt = t + 0.01
    for p in ports:
        c = net.tcp(attacker, target, p)
        # SYN, then SYN/ACK + RST (open) or RST/ACK (closed): the classic half-open scan
        net.ip_frame(tt, attacker, target, 6, P.tcp(attacker, target, c.sport, p, c.c_seq, 0, P.TCP_SYN, b"", 1024))
        if p in OPEN_PORTS:
            net.ip_frame(tt + 0.0008, target, attacker, 6,
                         P.tcp(target, attacker, p, c.sport, c.s_seq, c.c_seq + 1, P.TCP_SYN | P.TCP_ACK))
            net.ip_frame(tt + 0.0012, attacker, target, 6,
                         P.tcp(attacker, target, c.sport, p, c.c_seq + 1, 0, P.TCP_RST, b"", 0))
        else:
            net.ip_frame(tt + 0.0008, target, attacker, 6,
                         P.tcp(target, attacker, p, c.sport, 0, c.c_seq + 1, P.TCP_RST | P.TCP_ACK, b"", 0))
        tt += net.rng.uniform(0.05, 0.15)
    return dict(attack_type="network_reconnaissance", start=t, end=tt, src_ip=attacker, dst_ip=target,
                src_mac=net.mac(attacker),
                evidence=f"SYN packets to {len(ports)} different ports in {tt - t:.1f} s (half-open scan); "
                         f"open ports answered SYN/ACK, closed ports RST",
                wireshark_filter=f"tcp.flags.syn==1 && tcp.flags.ack==0 && ip.src=={attacker}")


def attack_register_enum(net, t, profile, attacker, target):
    net.set_mac(attacker, _rand_mac(net.rng))
    net.arp_exchange(t, attacker, target)
    c = net.tcp(attacker, target, 502)
    tt = c.open(t + 0.01)
    tid = net.rng.randint(0, 60000)
    top = profile.highest_normal_register
    for i in range(20):
        addr = i * 50
        ts = tt + i * 0.3
        c.request(ts, proto.mb_read_req(tid + i, 3, addr, 50))
        if addr + 50 - 1 <= top:
            c.reply(ts + 0.006, proto.mb_read_resp(tid + i, 3, 50, net.rng))
        else:
            c.reply(ts + 0.004, proto.mb_exception(tid + i, 3, 2))  # Illegal Data Address
    end = c.close(tt + 20 * 0.3)
    return dict(attack_type="modbus_register_enumeration", start=t, end=end, src_ip=attacker, dst_ip=target,
                src_mac=net.mac(attacker),
                evidence="FC03 reads sweeping registers 0-999 in steps of 50 from a host that is not a "
                         "known Modbus master; most answered with exception 0x83 (Illegal Data Address)",
                wireshark_filter=f"modbus.func_code==3 && ip.src=={attacker}")


def attack_unauthorised_write(net, t, profile, attacker, target):
    net.set_mac(attacker, _rand_mac(net.rng))
    net.arp_exchange(t, attacker, target)
    c = net.tcp(attacker, target, 502)
    tt = c.open(t + 0.01)
    tid = net.rng.randint(0, 60000)
    c.request(tt, proto.mb_read_req(tid, 3, 8, 4))
    c.reply(tt + 0.006, proto.mb_read_resp(tid, 3, 4, net.rng))
    vals = [net.rng.randint(0, 65535) for _ in range(4)]
    c.request(tt + 1.2, proto.mb_write_multi_req(tid + 1, 9, vals))
    c.reply(tt + 1.207, proto.mb_write_multi_resp(tid + 1, 9, 4))
    end = c.close(tt + 1.5)
    return dict(attack_type="unauthorised_write", start=t, end=end, src_ip=attacker, dst_ip=target,
                src_mac=net.mac(attacker),
                evidence=f"FC16 (Write Multiple Registers) to registers 9-12 from {attacker}, which is "
                         f"not an approved writer (approved: HMI-01, ENG-WS)",
                wireshark_filter="modbus.func_code in {5,6,15,16} && tcp.dstport == 502 && !(ip.src in {"
                                 + ",".join(sorted(profile.approved_writers)) + "})")


def attack_plc_upload(net, t, profile, attacker, target):
    net.set_mac(attacker, _rand_mac(net.rng))
    net.arp_exchange(t, attacker, target)
    c = net.tcp(attacker, target, 102)
    tt = c.open(t + 0.01)
    c.request(tt, proto.tpkt_cotp_cr())
    c.reply(tt + 0.003, proto.tpkt_cotp_cc())
    blob = b"\x47\x50\x4c" + net.rng.randbytes(15000)  # opaque program image
    chunk, ts, total = 1400, tt + 0.05, 0
    parts = [blob[i:i + chunk] for i in range(0, len(blob), chunk)]
    for n, part in enumerate(parts):
        c.request(ts, proto.tpkt_cotp_data(part, last=(n == len(parts) - 1)))
        total += len(part)
        if n % 2 == 1:
            c.ack_from_server(ts + 0.0005)
        ts += 0.002
    c.ack_from_server(ts)
    end = c.close(ts + 0.2)
    return dict(attack_type="plc_program_upload", start=t, end=end, src_ip=attacker, dst_ip=target,
                src_mac=net.mac(attacker),
                evidence=f"{total} bytes pushed to the PLC programming port TCP/102 (ISO-TSAP/S7) in "
                         f"{len(parts)} full-size frames, from a host that is not an approved programmer",
                wireshark_filter=f"ip.dst=={target} && frame.len > 1000")


def attack_arp_spoof(net, t, profile, attacker, victim):
    gw = sorted(profile.gateways)[0]
    evil = "de:ad:be:ef:00:" + f"{net.rng.randint(16, 255):02x}"
    net.set_mac(attacker, evil)
    for i in range(10):
        ts = t + i * 2.0
        net.emit(ts, P.arp_frame(2, evil, gw, net.mac(victim), victim))
    return dict(attack_type="arp_spoofing_mitm", start=t, end=t + 18.0, src_ip=gw, dst_ip=victim, src_mac=evil,
                evidence=f"Unsolicited ARP replies claim gateway {gw} is at {evil}; the real gateway "
                         f"MAC is {net.mac(gw)} -> two MACs for one IP (Wireshark: 'duplicate use detected')",
                wireshark_filter="arp.duplicate-address-detected || arp.duplicate-address-frame")


ATTACKS = [attack_recon_scan, attack_register_enum, attack_unauthorised_write, attack_plc_upload, attack_arp_spoof]


def _rand_mac(rng):
    return "02:" + ":".join(f"{rng.randint(0, 255):02x}" for _ in range(5))


def attacker_pool(profile, rng, n):
    used = {a["ip"] for a in profile.assets} | {"192.168.1.99"}
    pool = [f"192.168.{net}.{h}" for net in (1, 2) for h in range(150, 250)]
    pool = [p for p in pool if p not in used]
    return rng.sample(pool, n)


def fresh_net(profile, seed):
    return Net(profile, random.Random(seed))
