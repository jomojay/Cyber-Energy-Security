#!/usr/bin/env python3
"""
Generates the Lab Day 6 "Attack Detection Challenge" capture: a baseline
plus exactly the 5 attack signatures from Module 4, Table 4.3 (Section
4.5.1). Trainees must find all 5 using Wireshark and their own Python
signature detector (built from Section 4.5.2).

Attacks injected (answer key withheld from trainees):
  1. Network reconnaissance      - half-open SYN scan of 20 ports (SYN/ACK or RST replies)
  2. Modbus register enumeration - FC03 sweep of registers 0-999; the PLC answers with exceptions
  3. Unauthorised write          - FC16 write from a host that is not an approved writer
  4. PLC program upload          - ~15 KB pushed to TCP/102 (ISO-TSAP/S7) in full-size frames
  5. Man-in-the-middle (ARP)     - repeated ARP replies claiming the gateway IP with a rogue MAC
  (Data exfiltration, the 6th Table 4.3 pattern, is left out to keep five clearly separable events.)

Every run shuffles the order, jitters the timing, and picks new attacker
IPs and targets, so answers cannot be passed between cohorts.

Usage:
  python3 attack_pcap_generator.py baseline.pcap -o attack_challenge.pcap --answer-key key.csv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otkit.profile import load_profile  # noqa: E402
from otkit.sim.generate import inject_attacks  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("baseline", help="Input baseline pcap")
    ap.add_argument("-o", "--output", default="palanca_attack_challenge.pcap")
    ap.add_argument("--answer-key", default="attack_answer_key.csv")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--randomize", action="store_true", help="place attacks at fully random times")
    ap.add_argument("--profile")
    args = ap.parse_args()

    r = inject_attacks(args.baseline, args.output, args.answer_key, load_profile(args.profile),
                       seed=args.seed, randomize=args.randomize)
    print(f"Wrote {r['packets']:,} packets ({r['injected']} attack packets) to {args.output}  (seed {r['seed']})")
    print(f"Instructor answer key (do NOT share with trainees before grading): {args.answer_key}")
    print("5 attacks planted:", ", ".join(x["attack_type"] for x in r["rows"]))


if __name__ == "__main__":
    main()
