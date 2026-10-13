#!/usr/bin/env python3
"""
CVE correlation helper for Module 5, Lab Day 4 (Section 5.3.2).

Takes a vendor/product string (the kind returned by modbus-discover
or s7-info NSE scripts against the Palanca lab devices) and looks it
up against the offline reference dataset in cve_reference_dataset.json.

This mirrors what a live NVD API query would return, but works
without internet access in the training room. Trainees should also
practice a real NVD lookup (https://nvd.nist.gov) for one device as
part of the Day 4 deliverable, to see the real interface.

Usage:
  python3 cve_correlator.py "Siemens S7-1200"
"""
import json
import os
import sys

DEFAULT_DATASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cve_reference_dataset.json")


def load_dataset(path=DEFAULT_DATASET):
    with open(path) as f:
        return json.load(f)


def lookup(vendor_string, dataset):
    matches = []
    for vendor, cves in dataset["vendors"].items():
        if vendor.lower() in vendor_string.lower() or vendor_string.lower() in vendor.lower():
            matches.extend(cves)
    return matches


def apply_ot_cvss_adjustment(base_cvss, integrity_critical=True, availability_critical=True, safety_related=False):
    """
    Section 5.4.2's adjustment logic: adds weight for Integrity and
    Availability criticality (typical for OT), plus a flat safety
    bump if the affected device is safety-related.
    """
    adjusted = base_cvss
    if integrity_critical:
        adjusted += 0.2
    if availability_critical:
        adjusted += 0.3
    if safety_related:
        adjusted += 0.5
    return round(min(adjusted, 10.0), 1)


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 cve_correlator.py "<vendor string>"')
        sys.exit(1)
    vendor_string = sys.argv[1]
    dataset = load_dataset()
    matches = lookup(vendor_string, dataset)

    if not matches:
        print(f"No entries found for '{vendor_string}' in the offline dataset.")
        print("Try the live NVD search instead: https://nvd.nist.gov/vuln/search")
        return

    print(f"Found {len(matches)} entries for '{vendor_string}':\n")
    for m in matches:
        adjusted = apply_ot_cvss_adjustment(m["base_cvss"])
        print(f"  {m['cve_id']}  (base CVSS {m['base_cvss']}, OT-adjusted {adjusted})")
        print(f"    {m['summary']}")
        print(f"    Affected: {m['affected_versions']}  |  {m['cwe']}\n")


if __name__ == "__main__":
    main()
