#!/usr/bin/env python3
"""
Takes a baseline pcap (from baseline_pcap_generator.py) and injects the
three statistical anomaly categories from Module 4, Section 4.3.2, for
Lab Days 4-5 (statistical + ML anomaly detection).

Anomalies injected (labelled in the ground-truth CSV so trainees'
detectors can be scored for true/false positive rate):
  1. Write burst   - 20 Modbus FC06 writes in 10 s from ENG-WS (which normally never writes)
  2. Volume spike  - a second OPC UA session pumping 200 packets in 5 s
  3. New source    - Modbus polling from 192.168.1.99, never seen in the baseline

By default they sit near 25% / 50% / 75% of the capture (with a little
jitter). --randomize places them anywhere (used for the Day 7 assessment).

Usage:
  python3 anomaly_pcap_generator.py baseline.pcap -o anomalies.pcap --ground-truth truth.csv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from otkit.profile import load_profile  # noqa: E402
from otkit.sim.generate import inject_anomalies  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("baseline", help="Input baseline pcap")
    ap.add_argument("-o", "--output", default="palanca_anomalies.pcap")
    ap.add_argument("--ground-truth", default="anomalies_ground_truth.csv")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--randomize", action="store_true", help="place anomalies at random times")
    ap.add_argument("--profile")
    args = ap.parse_args()

    r = inject_anomalies(args.baseline, args.output, args.ground_truth, load_profile(args.profile),
                         seed=args.seed, randomize=args.randomize)
    print(f"Wrote {r['packets']:,} packets ({r['injected']} injected) to {args.output}  (seed {r['seed']})")
    print(f"Ground truth (for scoring trainee detectors): {args.ground_truth}")
    for row in r["rows"]:
        s = row["start"] - r["capture_start"]
        print(f"  - {row['anomaly_type']}: t={s:.1f}s  (5-min window {int(s // 300)}) :: {row['description']}")


if __name__ == "__main__":
    main()
