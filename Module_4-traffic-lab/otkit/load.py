"""
Fast capture loader: pcap / pcapng  ->  pandas DataFrame, one row per packet.

    from otkit.load import load_packets
    pkts = load_packets("captures/palanca_baseline_24h.pcap")

Why not pyshark? pyshark runs the full Wireshark dissector on every
packet through a pipe. That is great for poking at a handful of
packets, but on a 700,000-packet day capture it takes a very long time.
This loader reads the file directly and decodes only what the lab needs
(Ethernet, ARP, IPv4, TCP, UDP, Modbus/TCP), so a full day loads in
seconds. Results are cached next to the capture in .otlab_cache/.

Columns
-------
no            packet number (same as Wireshark's "No." column)
time          absolute timestamp (seconds since 1970, UTC)
rel           seconds since the first packet (Wireshark's default "Time" column)
len           frame length in bytes
eth_src/dst   MAC addresses
ip_src/dst    IPv4 addresses (empty for ARP)
l4            'TCP', 'UDP', 'ARP', 'ICMP' or 'OTHER'
sport/dport   TCP/UDP ports (0 if none)
flags         raw TCP flags; syn/ack/rst/fin are handy booleans
payload       TCP/UDP payload length in bytes
app           application protocol guessed from the port (Modbus/TCP, OPC UA, ...)
mb_request    True for a Modbus query (to port 502), False for a response
mb_fc         Modbus function code (exception bit removed), -1 if not Modbus
mb_exception  Modbus exception code, 0 if none
mb_addr       starting register / coil address (-1 when the PDU has none)
mb_qty        number of registers / coils (1 for FC05/06)
mb_unit, mb_tid   Modbus unit id and transaction id
arp_op        1 = request, 2 = reply, 0 = not ARP
arp_ip/arp_mac    the IP/MAC the ARP *sender* claims  (spoofing lives here)
arp_target_ip the IP being asked about
"""
import os
import pickle
import struct

import numpy as np
import pandas as pd

APP_PORTS = {
    502: "Modbus/TCP", 4840: "OPC UA", 80: "HTTP", 443: "HTTPS", 161: "SNMP", 162: "SNMP-trap",
    102: "S7/ISO-TSAP", 20000: "DNP3", 2404: "IEC-104", 44818: "EtherNet/IP", 2222: "EtherNet/IP-IO",
    47808: "BACnet", 22: "SSH", 23: "Telnet", 21: "FTP", 53: "DNS", 3389: "RDP", 445: "SMB",
    1911: "Niagara Fox", 20547: "ProConOS", 1962: "PCWorx", 123: "NTP", 514: "Syslog",
    137: "NetBIOS-NS", 138: "NetBIOS-DGM", 5355: "LLMNR", 1900: "SSDP", 5353: "mDNS", 67: "DHCP", 68: "DHCP",
}
MODBUS_PORT = 502
CACHE_VERSION = 4


def is_group_address(ip):
    """True for broadcast (x.x.x.255, 255.255.255.255) and multicast (224-239.x.x.x) destinations - not hosts."""
    if not ip:
        return False
    first = ip.split(".", 1)[0]
    return ip.endswith(".255") or (first.isdigit() and 224 <= int(first) <= 239)


def app_for(l4, sport, dport):
    if l4 == "ARP":
        return "ARP"
    for p in (dport, sport):
        if p in APP_PORTS:
            return APP_PORTS[p]
    if l4 in ("TCP", "UDP"):
        return f"{l4}/{min(sport, dport)}"
    return l4


def _iter_frames(path):
    """Yield (timestamp, linktype, frame_bytes) from classic pcap or pcapng."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 24:
        raise ValueError(f"{path}: file too small to be a capture")
    magic = struct.unpack("<I", data[:4])[0]
    if magic == 0x0A0D0D0A:
        yield from _iter_pcapng(data)
        return
    if magic in (0xA1B2C3D4, 0xA1B23C4D):
        e = "<"
    elif magic in (0xD4C3B2A1, 0x4D3CB2A1):
        e = ">"
    else:
        raise ValueError(f"{path}: not a pcap or pcapng file")
    nano = magic in (0xA1B23C4D, 0x4D3CB2A1)
    scale = 1e-9 if nano else 1e-6
    linktype = struct.unpack(e + "I", data[20:24])[0] & 0x0FFFFFFF
    rec = struct.Struct(e + "IIII")
    off, n = 24, len(data)
    while off + 16 <= n:
        sec, frac, incl, _ = rec.unpack_from(data, off)
        off += 16
        yield sec + frac * scale, linktype, data[off:off + incl]
        off += incl


def _iter_pcapng(data):
    off, n = 0, len(data)
    e = "<"
    ifaces = []  # (linktype, ts_divisor)
    while off + 12 <= n:
        btype, blen = struct.unpack_from(e + "II", data, off)
        if btype == 0x0A0D0D0A:  # section header: re-detect byte order
            bom = struct.unpack_from("<I", data, off + 8)[0]
            e = "<" if bom == 0x1A2B3C4D else ">"
            btype, blen = struct.unpack_from(e + "II", data, off)
            ifaces = []
        if blen < 12 or off + blen > n:
            break
        body = data[off + 8: off + blen - 4]
        if btype == 1:  # interface description
            lt = struct.unpack_from(e + "H", body, 0)[0]
            div = 1e6
            o = 8
            while o + 4 <= len(body):
                code, ln = struct.unpack_from(e + "HH", body, o)
                if code == 0:
                    break
                if code == 9 and ln >= 1:  # if_tsresol
                    v = body[o + 4]
                    div = 2 ** (v & 0x7F) if v & 0x80 else 10 ** v
                o += 4 + ((ln + 3) & ~3)
            ifaces.append((lt, div))
        elif btype == 6:  # enhanced packet
            iid, hi, lo, cap, _orig = struct.unpack_from(e + "IIIII", body, 0)
            lt, div = ifaces[iid] if iid < len(ifaces) else (1, 1e6)
            yield ((hi << 32) | lo) / div, lt, body[20:20 + cap]
        elif btype == 3:  # simple packet
            lt, div = ifaces[0] if ifaces else (1, 1e6)
            yield float("nan"), lt, body[4:]
        off += blen


def _l3_start(linktype, fr):
    """Return (ethertype, offset_of_l3, src_mac, dst_mac) for supported link types."""
    if linktype == 1:  # Ethernet
        if len(fr) < 14:
            return None
        et = (fr[12] << 8) | fr[13]
        off = 14
        while et in (0x8100, 0x88A8) and len(fr) >= off + 4:  # VLAN tags
            et = (fr[off + 2] << 8) | fr[off + 3]
            off += 4
        return et, off, fr[6:12].hex(":"), fr[0:6].hex(":")
    if linktype == 113:  # Linux cooked (tshark -i any)
        if len(fr) < 16:
            return None
        alen = (fr[4] << 8) | fr[5]
        return (fr[14] << 8) | fr[15], 16, fr[6:6 + min(alen, 6)].hex(":"), ""
    if linktype == 276:  # Linux cooked v2
        if len(fr) < 20:
            return None
        return (fr[0] << 8) | fr[1], 20, fr[12:18].hex(":"), ""
    if linktype in (101, 228):  # raw IPv4
        return 0x0800, 0, "", ""
    return None


def _parse(path):
    cols = {k: [] for k in ("time", "len", "eth_src", "eth_dst", "ip_src", "ip_dst", "l4", "sport", "dport",
                            "flags", "payload", "mb_request", "mb_fc", "mb_exception", "mb_addr", "mb_qty",
                            "mb_unit", "mb_tid", "arp_op", "arp_ip", "arp_mac", "arp_target_ip")}
    A = {k: v.append for k, v in cols.items()}
    ipfmt = "{}.{}.{}.{}".format

    for ts, lt, fr in _iter_frames(path):
        hdr = _l3_start(lt, fr)
        ip_src = ip_dst = arp_ip = arp_mac = arp_tip = ""
        l4, sport, dport, flags, pay = "OTHER", 0, 0, 0, 0
        mb_req, mb_fc, mb_exc, mb_addr, mb_qty, mb_unit, mb_tid, arp_op = False, -1, 0, -1, 0, -1, -1, 0
        esrc = edst = ""
        if hdr:
            et, o, esrc, edst = hdr
            if et == 0x0806 and len(fr) >= o + 28:
                l4, arp_op = "ARP", (fr[o + 6] << 8) | fr[o + 7]
                arp_mac = fr[o + 8:o + 14].hex(":")
                arp_ip = ipfmt(*fr[o + 14:o + 18])
                arp_tip = ipfmt(*fr[o + 24:o + 28])
            elif et == 0x0800 and len(fr) >= o + 20:
                ihl = (fr[o] & 0x0F) * 4
                tot = (fr[o + 2] << 8) | fr[o + 3]
                proto = fr[o + 9]
                ip_src, ip_dst = ipfmt(*fr[o + 12:o + 16]), ipfmt(*fr[o + 16:o + 20])
                t = o + ihl
                end = min(len(fr), o + tot) if tot else len(fr)
                if proto == 6 and end >= t + 20:
                    l4 = "TCP"
                    sport, dport = (fr[t] << 8) | fr[t + 1], (fr[t + 2] << 8) | fr[t + 3]
                    doff = (fr[t + 12] >> 4) * 4
                    flags = fr[t + 13]
                    p = t + doff
                    pay = max(0, end - p)
                    if pay >= 8 and (dport == MODBUS_PORT or sport == MODBUS_PORT):
                        mb_req = dport == MODBUS_PORT
                        mb_tid = (fr[p] << 8) | fr[p + 1]
                        mb_unit = fr[p + 6]
                        fc = fr[p + 7]
                        if fc & 0x80:
                            mb_fc, mb_exc = fc & 0x7F, fr[p + 8] if pay >= 9 else 0
                        else:
                            mb_fc = fc
                            has_addr = (mb_req and fc in (1, 2, 3, 4, 5, 6, 15, 16)) or (not mb_req and fc in (5, 6, 15, 16))
                            if has_addr and pay >= 12:
                                mb_addr = (fr[p + 8] << 8) | fr[p + 9]
                                mb_qty = 1 if fc in (5, 6) else (fr[p + 10] << 8) | fr[p + 11]
                elif proto == 17 and end >= t + 8:
                    l4 = "UDP"
                    sport, dport = (fr[t] << 8) | fr[t + 1], (fr[t + 2] << 8) | fr[t + 3]
                    pay = max(0, end - t - 8)
                elif proto == 1:
                    l4 = "ICMP"
        A["time"](ts); A["len"](len(fr)); A["eth_src"](esrc); A["eth_dst"](edst)
        A["ip_src"](ip_src); A["ip_dst"](ip_dst); A["l4"](l4); A["sport"](sport); A["dport"](dport)
        A["flags"](flags); A["payload"](pay); A["mb_request"](mb_req); A["mb_fc"](mb_fc)
        A["mb_exception"](mb_exc); A["mb_addr"](mb_addr); A["mb_qty"](mb_qty); A["mb_unit"](mb_unit)
        A["mb_tid"](mb_tid); A["arp_op"](arp_op); A["arp_ip"](arp_ip); A["arp_mac"](arp_mac)
        A["arp_target_ip"](arp_tip)

    df = pd.DataFrame(cols)
    if df.empty:
        return df
    int_cols = ["len", "sport", "dport", "flags", "payload", "mb_fc", "mb_exception", "mb_addr", "mb_qty",
                "mb_unit", "mb_tid", "arp_op"]
    df[int_cols] = df[int_cols].astype(np.int32)
    for c in ("eth_src", "eth_dst", "ip_src", "ip_dst", "l4", "arp_ip", "arp_mac", "arp_target_ip"):
        df[c] = df[c].astype("category")
    df.insert(0, "no", np.arange(1, len(df) + 1))
    df.insert(2, "rel", df["time"] - df["time"].iloc[0])
    df["syn"] = (df["flags"] & 0x02) > 0
    df["ack"] = (df["flags"] & 0x10) > 0
    df["rst"] = (df["flags"] & 0x04) > 0
    df["fin"] = (df["flags"] & 0x01) > 0
    apps = {}
    df["app"] = [apps.setdefault(k, app_for(*k)) for k in zip(df["l4"], df["sport"], df["dport"])]
    df["app"] = df["app"].astype("category")
    return df


def load_packets(path, use_cache=True, quiet=False):
    """Load a capture into a DataFrame (cached)."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Capture not found: {path}\n  Tip: run ./setup.sh first (it creates the captures/ folder), "
            f"or check the spelling with: ls captures/")
    st = os.stat(path)
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(path)), ".otlab_cache")
    cache = os.path.join(cache_dir, f"{os.path.basename(path)}.{st.st_size}.{int(st.st_mtime)}.v{CACHE_VERSION}.pkl")
    if use_cache and os.path.exists(cache):
        try:
            with open(cache, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    if not quiet:
        print(f"  Reading {os.path.basename(path)} ({st.st_size / 1e6:.1f} MB) ...", flush=True)
    df = _parse(path)
    if use_cache:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            for old in os.listdir(cache_dir):
                if old.startswith(os.path.basename(path) + "."):
                    os.remove(os.path.join(cache_dir, old))
            with open(cache, "wb") as f:
                pickle.dump(df, f, protocol=pickle.HIGHEST_PROTOCOL)
        except OSError:
            pass
    return df
