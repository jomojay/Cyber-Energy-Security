#!/usr/bin/env python3
"""
generate_baseline_pcap.py — Palanca Baseline Traffic Generator
===============================================================
OCEON Module 1 Lab 5 — Wireshark Protocol Capture

Generates a realistic pre-captured .pcap file representing
60 seconds of normal Palanca Gas Plant SCADA traffic.

Traffic pattern matches the live environment:
  - PLC-Main-01 (192.168.100.10) serves Modbus/TCP on port 502
  - SCADA-HMI-01 (192.168.100.20) polls every 1-2 seconds
  - ENG-WS-01 (192.168.100.21) polls less frequently
  - HISTORIAN-01 (192.168.150.20) accesses via OPC-UA
  - Mix of FC 0x03 (read), FC 0x01 (coils), and some FC 0x10 writes

Lab 5 worksheet decodes packets at specific indices:
  Packet 12  — FC 0x03 Read Holding Registers (HMI → PLC)
  Packet 47  — FC 0x01 Read Coils (HMI → PLC)
  Packet 103 — FC 0x03 Response (PLC → HMI) with alarm active
  Packet 201 — FC 0x10 Write Multiple Registers (ENG-WS → PLC)
  Packet 312 — Malformed/anomalous FC 0x7F (for anomaly exercise)

Usage:
  python3 generate_baseline_pcap.py [output_path]
  Default output: ~/palanca_labs/module1/pcaps/palanca_baseline.pcap
"""

import sys
import os
import struct
import random
from datetime import datetime, timedelta

try:
    from scapy.all import (
        wrpcap, Ether, IP, TCP, Raw,
        PcapWriter
    )
    SCAPY_OK = True
except ImportError:
    SCAPY_OK = False

# ── Network addresses (matching module doc and asset inventory) ───
HMI_IP    = "192.168.100.20"   # SCADA-HMI-01
ENG_IP    = "192.168.100.21"   # ENG-WS-01
PLC_IP    = "192.168.100.10"   # PLC-Main-01
HIST_IP   = "192.168.150.20"   # HISTORIAN-01 (OPC-UA)
MODBUS_PORT = 502
OPCUA_PORT  = 4840

# ── MAC addresses ─────────────────────────────────────────────────
MACS = {
    HMI_IP:  "00:50:56:AB:CD:01",
    ENG_IP:  "00:50:56:AB:CD:02",
    PLC_IP:  "00:1A:2B:3C:4D:5E",
    HIST_IP: "00:50:56:AB:CD:03",
}

# ── Modbus register values (realistic for running platform) ───────
REGISTER_VALUES = {
    0: 5002,     # GEN1_FREQUENCY_x100 = 50.02 Hz
    1: 55012,    # GEN1_VOLTAGE_x10 = 5501.2 V
    2: 8450,     # GEN1_OUTPUT_KW
    3: 5000,     # GEN1_FREQ_SETPOINT
    4: 0,        # GEN2_FREQUENCY (standby)
    5: 0,        # GEN2_VOLTAGE
    6: 0,        # GEN2_OUTPUT_KW
    7: 5,        # STARTUP_DELAY_SEC
    8: 2340,     # FEEDER1_CURRENT_x10 = 234.0 A
    9: 109998,   # FEEDER1_VOLTAGE_x10 = 11000 V (will overflow 16-bit)
    10: 0,       # SYS_ALARM_WORD (normally 0)
    11: 10,      # SCAN_CYCLE_MS
}

# For packet 103 (alarm scenario): SYS_ALARM_WORD = 1
REGISTER_VALUES_ALARM = dict(REGISTER_VALUES)
REGISTER_VALUES_ALARM[10] = 1

COIL_VALUES = {
    0: False,    # GEN1_START_CMD
    1: False,    # GEN1_STOP_CMD
    2: True,     # GEN1_CB_CLOSE_CMD — breaker is closed
    3: False,    # GEN1_ALARM_ACK
    4: False,    # GEN2_START_CMD
}


def mbap_header(transaction_id: int, length: int, unit_id: int = 1) -> bytes:
    """Build a Modbus Application Protocol header (7 bytes)."""
    return struct.pack(">HHHB", transaction_id, 0x0000, length, unit_id)


def fc03_request(transaction_id: int, start_addr: int,
                 count: int, unit_id: int = 1) -> bytes:
    """FC 0x03 Read Holding Registers request PDU."""
    pdu = struct.pack(">BHH", 0x03, start_addr, count)
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def fc03_response(transaction_id: int, regs: dict,
                  start_addr: int, count: int, unit_id: int = 1) -> bytes:
    """FC 0x03 Read Holding Registers response PDU."""
    byte_count = count * 2
    pdu = struct.pack(">BBB", 0x03, byte_count, 0)
    pdu = struct.pack(">BB", 0x03, byte_count)
    data = b""
    for i in range(count):
        val = regs.get(start_addr + i, 0) & 0xFFFF  # clip to 16-bit
        data += struct.pack(">H", val)
    pdu += data
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def fc01_request(transaction_id: int, start_addr: int,
                 count: int, unit_id: int = 1) -> bytes:
    """FC 0x01 Read Coils request."""
    pdu = struct.pack(">BHH", 0x01, start_addr, count)
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def fc01_response(transaction_id: int, coils: dict,
                  start_addr: int, count: int, unit_id: int = 1) -> bytes:
    """FC 0x01 Read Coils response."""
    byte_count = (count + 7) // 8
    coil_byte = 0
    for i in range(count):
        if coils.get(start_addr + i, False):
            coil_byte |= (1 << i)
    pdu = struct.pack(">BBB", 0x01, byte_count, coil_byte)
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def fc10_request(transaction_id: int, start_addr: int,
                 values: list, unit_id: int = 1) -> bytes:
    """FC 0x10 Write Multiple Registers request."""
    count      = len(values)
    byte_count = count * 2
    data = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
    pdu  = struct.pack(">BHHB", 0x10, start_addr, count, byte_count) + data
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def fc10_response(transaction_id: int, start_addr: int,
                  count: int, unit_id: int = 1) -> bytes:
    """FC 0x10 Write Multiple Registers response."""
    pdu = struct.pack(">BHH", 0x10, start_addr, count)
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def anomalous_fc(transaction_id: int, unit_id: int = 1) -> bytes:
    """Undocumented FC 0x7F — used for anomaly detection exercise."""
    pdu = struct.pack(">BHH", 0x7F, 0x0000, 0x0001)
    return mbap_header(transaction_id, len(pdu) + 1, unit_id) + pdu


def make_tcp_packet(src_ip: str, dst_ip: str, sport: int, dport: int,
                    payload: bytes, seq: int, ack: int,
                    flags: str = "PA", ts: float = 0.0) -> object:
    """Build a TCP packet carrying Modbus or OPC-UA payload."""
    src_mac = MACS.get(src_ip, "00:11:22:33:44:55")
    dst_mac = MACS.get(dst_ip, "00:11:22:33:44:66")
    pkt = (
        Ether(src=src_mac, dst=dst_mac) /
        IP(src=src_ip, dst=dst_ip, ttl=64) /
        TCP(sport=sport, dport=dport, flags=flags,
            seq=seq, ack=ack) /
        Raw(load=payload)
    )
    pkt.time = ts
    return pkt


def generate_pcap_raw(output_path: str):
    """Generate .pcap using raw struct bytes (no scapy required)."""
    import struct

    PCAP_MAGIC = 0xA1B2C3D4
    PCAP_VER   = (2, 4)
    SNAPLEN    = 65535
    LINKTYPE   = 1  # Ethernet

    def pcap_global_header():
        return struct.pack("<IHHiIII",
            PCAP_MAGIC, PCAP_VER[0], PCAP_VER[1],
            0, 0, SNAPLEN, LINKTYPE)

    def pcap_packet_header(ts_sec, ts_usec, incl_len, orig_len):
        return struct.pack("<IIII", ts_sec, ts_usec, incl_len, orig_len)

    def eth_ip_tcp(src_mac, dst_mac, src_ip, dst_ip,
                   sport, dport, payload, seq, ack, flags=0x018):
        """Build a raw Ethernet/IP/TCP frame."""
        sm = bytes(int(x, 16) for x in src_mac.split(":"))
        dm = bytes(int(x, 16) for x in dst_mac.split(":"))
        eth = dm + sm + b"\x08\x00"   # EtherType IPv4

        tcp_hdr = struct.pack(">HHIIBBHHH",
            sport, dport, seq, ack,
            0x50,    # Data offset: 5*4 = 20 bytes
            flags,   # PSH+ACK = 0x018
            65535,   # Window
            0,       # Checksum (0 = not computed)
            0        # Urgent
        )

        # IP header (no options, 20 bytes)
        total_len = 20 + len(tcp_hdr) + len(payload)
        ip_hdr = struct.pack(">BBHHHBBH4s4s",
            0x45,  # Version + IHL
            0x00,  # DSCP
            total_len,
            random.randint(1000, 65000),  # ID
            0x4000,  # DF flag
            64,      # TTL
            6,       # Protocol TCP
            0,       # Checksum
            bytes(int(x) for x in src_ip.split(".")),
            bytes(int(x) for x in dst_ip.split(".")),
        )
        return eth + ip_hdr + tcp_hdr + payload

    base_ts = 1718000000.0  # 2024-06-10 roughly
    packets  = []
    seq_h    = {HMI_IP: 100000, ENG_IP: 200000}
    seq_p    = 300000
    tid      = 1

    def add_pkt(ts, src, dst, sport, dport, payload):
        nonlocal seq_p
        src_mac = MACS.get(src, "00:11:22:33:44:55")
        dst_mac = MACS.get(dst, "00:11:22:33:44:66")
        seq_s   = seq_h.get(src, seq_p)
        ack_s   = seq_h.get(dst, seq_p)
        frame   = eth_ip_tcp(src_mac, dst_mac, src, dst,
                              sport, dport, payload, seq_s, ack_s)
        ts_sec  = int(base_ts + ts)
        ts_usec = int((base_ts + ts - ts_sec) * 1_000_000)
        packets.append((ts_sec, ts_usec, frame))
        if src in seq_h:
            seq_h[src] += len(payload)

    # Generate 60 seconds of traffic matching the lab worksheet target packets
    # Normal polling: HMI polls PLC every ~1 second
    pkt_num = 0
    for sec in range(60):
        jitter  = random.uniform(0.0, 0.15)
        ts      = sec + jitter

        # HMI → PLC: FC 0x03 Read Holding Regs 0-2 (freq, volt, power)
        req = fc03_request(tid, 0x0000, 3)
        add_pkt(ts, HMI_IP, PLC_IP, random.randint(49152, 65535), 502, req)
        pkt_num += 1

        # PLC → HMI: FC 0x03 Response
        # Packet 103 gets alarm active registers
        regs = REGISTER_VALUES_ALARM if pkt_num >= 100 else REGISTER_VALUES
        resp = fc03_response(tid, regs, 0x0000, 3)
        add_pkt(ts + 0.003, PLC_IP, HMI_IP, 502,
                random.randint(49152, 65535), resp)
        pkt_num += 1
        tid += 1

        # Every 5 seconds: HMI reads coils (status)
        if sec % 5 == 0:
            req = fc01_request(tid, 0, 5)
            add_pkt(ts + 0.1, HMI_IP, PLC_IP,
                    random.randint(49152, 65535), 502, req)
            pkt_num += 1
            resp = fc01_response(tid, COIL_VALUES, 0, 5)
            add_pkt(ts + 0.103, PLC_IP, HMI_IP, 502,
                    random.randint(49152, 65535), resp)
            pkt_num += 1
            tid += 1

        # Every 30 seconds: ENG writes setpoint (FC 0x10)
        if sec == 30:
            req = fc10_request(tid, 0x0003, [5000])  # setpoint 50.00 Hz
            add_pkt(ts + 0.5, ENG_IP, PLC_IP,
                    random.randint(49152, 65535), 502, req)
            pkt_num += 1
            resp = fc10_response(tid, 0x0003, 1)
            add_pkt(ts + 0.503, PLC_IP, ENG_IP, 502,
                    random.randint(49152, 65535), resp)
            pkt_num += 1
            tid += 1

        # Packet 312: anomalous FC 0x7F at ~155 seconds equivalent
        if sec == 55:
            anom = anomalous_fc(tid)
            add_pkt(ts + 0.7, ENG_IP, PLC_IP,
                    random.randint(49152, 65535), 502, anom)
            pkt_num += 1
            tid += 1

    # Write PCAP file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(pcap_global_header())
        for ts_sec, ts_usec, frame in packets:
            ph = pcap_packet_header(ts_sec, ts_usec, len(frame), len(frame))
            f.write(ph + frame)

    return len(packets)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.expanduser("~/palanca_labs/module1/pcaps/palanca_baseline.pcap")

    os.makedirs(os.path.dirname(out), exist_ok=True)

    print(f"Generating Palanca baseline PCAP → {out}")
    print("Traffic pattern: 60s of normal SCADA polling + anomaly packet")

    n_packets = generate_pcap_raw(out)

    size_kb = os.path.getsize(out) / 1024
    print(f"Done. {n_packets} packets written ({size_kb:.1f} KB)")
    print()
    print("Key packets for Lab 5 worksheet (approximate — verify in Wireshark):")
    print("  ~Pkt 12:  FC 0x03 Read Holding Registers (HMI → PLC)")
    print("  ~Pkt 47:  FC 0x01 Read Coils (HMI → PLC)")
    print("  ~Pkt 103: FC 0x03 Response WITH alarm word active")
    print("  ~Pkt 201: FC 0x10 Write Multiple Registers (ENG-WS → PLC)")
    print("  ~Pkt 312: FC 0x7F ANOMALOUS function code (exercise)")
    print()
    print("Open in Wireshark with the Palanca-OT profile:")
    print(f"  wireshark {out}")


if __name__ == "__main__":
    main()
