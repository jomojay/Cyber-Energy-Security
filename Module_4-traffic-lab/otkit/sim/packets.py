"""
Low-level packet building and pcap I/O for the synthetic Palanca captures.

Frames are built directly as bytes (Ethernet / IPv4 / TCP / UDP / ARP)
instead of through scapy. That keeps generation fast (a 24-hour capture
takes seconds, not minutes), fully deterministic for a given seed, and
free of scapy's habit of ARP-resolving real MAC addresses from the
machine that happens to run the generator.
"""
import functools
import struct

PCAP_MAGIC = 0xA1B2C3D4
LINKTYPE_ETHERNET = 1

TCP_FIN, TCP_SYN, TCP_RST, TCP_PSH, TCP_ACK = 0x01, 0x02, 0x04, 0x08, 0x10


@functools.lru_cache(maxsize=None)
def mac_bytes(mac):
    return bytes(int(x, 16) for x in mac.split(":"))


@functools.lru_cache(maxsize=None)
def ip_bytes(ip):
    return bytes(int(x) for x in ip.split("."))


def _checksum(data):
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def ethernet(src_mac, dst_mac, ethertype, payload):
    return mac_bytes(dst_mac) + mac_bytes(src_mac) + struct.pack("!H", ethertype) + payload


def ipv4(src, dst, proto, payload, ident=0, ttl=64):
    total = 20 + len(payload)
    hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, ident & 0xFFFF, 0x4000, ttl, proto, 0,
                      ip_bytes(src), ip_bytes(dst))
    hdr = hdr[:10] + struct.pack("!H", _checksum(hdr)) + hdr[12:]
    return hdr + payload


# TCP options for SYN and SYN/ACK: MSS 1460, NOP, NOP, SACK permitted. Without an MSS option Wireshark
# assumes the 536-byte default and flags every larger segment ("This packet's length exceeds MSS").
SYN_OPTIONS = struct.pack("!BBH", 2, 4, 1460) + b"\x01\x01\x04\x02"


def tcp(src, dst, sport, dport, seq, ack, flags, payload=b"", window=8192, options=None):
    if options is None:
        options = SYN_OPTIONS if flags & TCP_SYN else b""
    seg = struct.pack("!HHIIBBHHH", sport, dport, seq & 0xFFFFFFFF, ack & 0xFFFFFFFF,
                      (5 + len(options) // 4) << 4, flags, window, 0, 0) + options + payload
    pseudo = ip_bytes(src) + ip_bytes(dst) + struct.pack("!BBH", 0, 6, len(seg))
    csum = _checksum(pseudo + seg)
    return seg[:16] + struct.pack("!H", csum) + seg[18:]


def udp(src, dst, sport, dport, payload):
    length = 8 + len(payload)
    seg = struct.pack("!HHHH", sport, dport, length, 0) + payload
    pseudo = ip_bytes(src) + ip_bytes(dst) + struct.pack("!BBH", 0, 17, length)
    csum = _checksum(pseudo + seg) or 0xFFFF
    return seg[:6] + struct.pack("!H", csum) + seg[8:]


def arp(op, sender_mac, sender_ip, target_mac, target_ip):
    return struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, op, mac_bytes(sender_mac), ip_bytes(sender_ip),
                       mac_bytes(target_mac), ip_bytes(target_ip))


def arp_frame(op, sender_mac, sender_ip, target_mac, target_ip, eth_dst=None):
    body = arp(op, sender_mac, sender_ip, target_mac, target_ip)
    dst = eth_dst or ("ff:ff:ff:ff:ff:ff" if op == 1 else target_mac)
    frame = ethernet(sender_mac, dst, 0x0806, body)
    return frame + b"\x00" * max(0, 60 - len(frame))  # pad to Ethernet minimum


# ---------------------------------------------------------------------------
# pcap (classic, microsecond) reader / writer
# ---------------------------------------------------------------------------

def write_pcap(path, records):
    """records: iterable of (timestamp_float, frame_bytes), already time-sorted."""
    n = 0
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", PCAP_MAGIC, 2, 4, 0, 0, 262144, LINKTYPE_ETHERNET))
        for ts, frame in records:
            sec = int(ts)
            usec = int(round((ts - sec) * 1_000_000))
            if usec >= 1_000_000:
                sec, usec = sec + 1, usec - 1_000_000
            f.write(struct.pack("<IIII", sec, usec, len(frame), len(frame)))
            f.write(frame)
            n += 1
    return n


def read_pcap_records(path):
    """Read a classic Ethernet pcap written by write_pcap -> list of (ts, bytes)."""
    out = []
    with open(path, "rb") as f:
        hdr = f.read(24)
        if len(hdr) < 24:
            raise ValueError(f"{path} is not a pcap file (too short)")
        magic = struct.unpack("<I", hdr[:4])[0]
        if magic == PCAP_MAGIC:
            endian, scale = "<", 1e-6
        elif magic == 0xA1B23C4D:
            endian, scale = "<", 1e-9
        elif magic in (0xD4C3B2A1, 0x4D3CB2A1):
            endian, scale = ">", 1e-6 if magic == 0xD4C3B2A1 else 1e-9
        else:
            raise ValueError(f"{path} is not a classic pcap file (pcapng is not supported here)")
        rec = struct.Struct(endian + "IIII")
        while True:
            h = f.read(16)
            if len(h) < 16:
                break
            sec, frac, incl, _orig = rec.unpack(h)
            out.append((sec + frac * scale, f.read(incl)))
    return out
