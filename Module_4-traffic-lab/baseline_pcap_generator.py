#!/usr/bin/env python3
"""
Generates a synthetic 24-hour-equivalent Palanca traffic capture matching
the traffic profile in Module 4, Section 4.1.2 / Table 4.1. Used for Lab
Day 3 (Baseline Construction) so every trainee works from an identical,
reproducible capture instead of waiting a real 24 hours for one.

Traffic reproduced (names/IPs from profiles/palanca.json):
  PLC-MAIN-01 -> every RTU/relay/VFD   Modbus/TCP  every 2 s   FC03, 10 registers (~80 B)
  HMI-01      -> PLC-MAIN-01           Modbus/TCP  every 1 s   FC03 reads (~120 B) + occasional FC06 writes
  SCADA-SVR   -> HISTORIAN             OPC UA      every 5 s   ~400 B PublishResponses (3 subscriptions)
  HMI-01      -> SCADA-SVR             HTTPS       ~12.5 s     SCADA web interface
  ENG-WS      -> PLC-MAIN-01           HTTP        on demand   ~1200 B diagnostics page (day shift)
  NMS         -> switches              SNMPv2c     every 60 s  GET counters, CPU, memory
  all hosts                            ARP, NTP, syslog, NetBIOS/LLMNR/SSDP background
Byte mix matches the Module 4 text: Modbus 50.4 %, OPC UA 21.7 %, HTTP/HTTPS 9.6 %, ARP 6.7 %, SNMP 1.8 %.

Every packet is a valid, fully decodable frame (proper TCP handshakes and
sequence numbers, real Modbus/OPC UA/SNMP encodings, fixed per-device
MAC addresses), so Wireshark filters such as `modbus` and `opcua` work.

Usage:
  python3 baseline_pcap_generator.py [--hours 24] [--seed N] [-o palanca_baseline_24h.pcap]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otkit.profile import load_profile  # noqa: E402
from otkit.sim.generate import generate_baseline  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=24.0, help="Simulated timespan in hours (default 24)")
    ap.add_argument("--seed", type=int, help="Random seed - the same seed gives the same capture")
    ap.add_argument("--start", help="Capture start time, UTC, e.g. 2026-03-02T00:00:00 (default)")
    ap.add_argument("--profile", help="Site profile JSON (default profiles/palanca.json)")
    ap.add_argument("--speed", type=float, help=argparse.SUPPRESS)  # accepted for backwards compatibility; no effect
    ap.add_argument("-o", "--output", default="palanca_baseline_24h.pcap")
    args = ap.parse_args()

    print(f"Generating {args.hours:g}-hour synthetic Palanca baseline capture...")
    r = generate_baseline(args.output, load_profile(args.profile), hours=args.hours, seed=args.seed, start=args.start)
    print(f"Wrote {r['packets']:,} packets to {args.output}  (seed {r['seed']})")


if __name__ == "__main__":
    main()
