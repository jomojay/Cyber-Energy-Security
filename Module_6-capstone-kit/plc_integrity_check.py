#!/usr/bin/env python3
"""
PLC program integrity checker for Module 6, Lab Day 4 (OT Forensics).

Extends the baseline-comparison concept from Module 3, Section 3.6.4
into a ready-to-run tool: compares a PLC program file's hash against
an approved baseline database, exactly as used during Day 4's
forensic investigation ("Perform PLC program integrity verification").

Usage:
  # Register a known-good baseline (do this BEFORE the simulated incident):
  python3 plc_integrity_check.py --register PLC-MAIN-01 plc_main_baseline.st \
      --approved-by "OT Engineer - J. Adeyemi" --moc-ref MOC-2026-0031

  # During forensic investigation, check the current program against baseline:
  python3 plc_integrity_check.py --check PLC-MAIN-01 plc_main_current.st

Baselines are stored in plc_baselines.json next to this script, so the
tool gives the same answer whichever directory it is run from.

Exit codes: 0 = registered / matches baseline, 1 = DEVIATION_DETECTED or
no baseline registered, 2 = usage or file error.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

BASELINE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plc_baselines.json")


def load_db():
    try:
        with open(BASELINE_DB) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        sys.exit(f"ERROR: {BASELINE_DB} is not valid JSON. Fix or delete it, then re-register the baseline.")


def save_db(db):
    with open(BASELINE_DB, "w") as f:
        json.dump(db, f, indent=2)


def file_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        print(f"ERROR: cannot read program file '{path}': {e.strerror}", file=sys.stderr)
        sys.exit(2)


def register_baseline(device, path, approved_by, moc_ref):
    db = load_db()
    db[device] = {
        "approved_hash": file_hash(path),
        "approval_date": datetime.now().strftime("%Y-%m-%d"),
        "approved_by": approved_by,
        "moc_reference": moc_ref,
        "source_file": os.path.abspath(path),
    }
    save_db(db)
    print(f"Baseline registered for {device}")
    print(f"   SHA-256:  {db[device]['approved_hash']}")
    print(f"   Approved: {db[device]['approval_date']} by {approved_by} ({moc_ref})")
    print(f"   Stored in {BASELINE_DB}")


def check_program(device, path):
    db = load_db()
    baseline = db.get(device)
    if not baseline:
        print(f"ALERT: No baseline found for {device} — cannot verify integrity.")
        return {"status": "ALERT", "reason": "No baseline found"}

    current_hash = file_hash(path)
    result = {
        "device": device,
        "timestamp": datetime.now().isoformat(),
        "expected_hash": baseline["approved_hash"],
        "current_hash": current_hash,
        "baseline_date": baseline["approval_date"],
        "baseline_approved_by": baseline["approved_by"],
        "baseline_moc_ref": baseline["moc_reference"],
    }

    if current_hash != baseline["approved_hash"]:
        result["status"] = "DEVIATION_DETECTED"
        print(f"** DEVIATION DETECTED on {device} **")
        print(f"   Expected: {baseline['approved_hash']}")
        print(f"   Current:  {current_hash}")
        print(f"   Baseline approved {baseline['approval_date']} by {baseline['approved_by']} ({baseline['moc_reference']})")
        print("   This program does NOT match the last approved, MOC-authorised version.")
    else:
        result["status"] = "OK"
        print(f"[OK] {device} matches its approved baseline ({baseline['moc_reference']}).")

    return result


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", nargs=2, metavar=("DEVICE", "FILE"))
    group.add_argument("--check", nargs=2, metavar=("DEVICE", "FILE"))
    ap.add_argument("--approved-by", default="Unknown")
    ap.add_argument("--moc-ref", default="Unknown")
    args = ap.parse_args()

    if args.register:
        device, path = args.register
        register_baseline(device, path, args.approved_by, args.moc_ref)
    elif args.check:
        device, path = args.check
        result = check_program(device, path)
        sys.exit(0 if result["status"] == "OK" else 1)


if __name__ == "__main__":
    main()
