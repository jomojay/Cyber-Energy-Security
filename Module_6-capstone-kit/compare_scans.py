#!/usr/bin/env python3
"""
Before/after comparison of two OTSafeScanner result files for Module 6,
Lab Day 6 (Security Posture Assessment).

Reads the scan_results_<timestamp>.json files written by Module 5's
ot_safe_scanner.py (a list of {host, port, protocol, state, service})
and prints the open-port count before and after hardening, plus exactly
which services were closed off and which are still exposed.

Usage:
  python3 compare_scans.py BEFORE.json AFTER.json
  python3 compare_scans.py BEFORE.json AFTER.json --csv day6_port_comparison.csv
"""
import argparse
import csv
import ipaddress
import json
import sys


def open_services(path):
    try:
        with open(path) as f:
            rows = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"ERROR: cannot read scan results '{path}': {e}")
    return {
        (r["host"], int(r["port"]), r.get("protocol", "tcp")): r.get("service", "")
        for r in rows
        if r.get("state") == "open"
    }


def sort_key(item):
    host, port, proto = item
    return (ipaddress.ip_address(host), port, proto)


def main():
    ap = argparse.ArgumentParser(description="Compare a before- and after-hardening OTSafeScanner run.")
    ap.add_argument("before", help="scan_results_*.json from the original Module 5 scan")
    ap.add_argument("after", help="scan_results_*.json from the Day 6 re-scan")
    ap.add_argument("--csv", help="also write the comparison to this CSV file")
    args = ap.parse_args()

    before = open_services(args.before)
    after = open_services(args.after)
    closed = sorted(set(before) - set(after), key=sort_key)
    still_open = sorted(set(before) & set(after), key=sort_key)
    new = sorted(set(after) - set(before), key=sort_key)

    print(f"Open services before hardening: {len(before)}  ({len({k[0] for k in before})} hosts)")
    print(f"Open services after hardening:  {len(after)}  ({len({k[0] for k in after})} hosts)")
    if before:
        print(f"Reduction: {len(before) - len(after)} ({(len(before) - len(after)) / len(before):.0%})")

    for title, items, src in (("No longer reachable", closed, before),
                              ("Still reachable (justify each, or list as a gap)", still_open, after),
                              ("NEW since the original scan (investigate)", new, after)):
        print(f"\n{title}: {len(items)}")
        for host, port, proto in items:
            print(f"  {host:<15} {port:>5}/{proto}  {src[(host, port, proto)]}")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["host", "port", "protocol", "service", "result"])
            for label, items, src in (("closed", closed, before), ("still_open", still_open, after), ("new", new, after)):
                for host, port, proto in items:
                    w.writerow([host, port, proto, src[(host, port, proto)], label])
        print(f"\nComparison written to {args.csv}")


if __name__ == "__main__":
    main()
