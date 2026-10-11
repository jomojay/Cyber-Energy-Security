#!/usr/bin/env python3
"""
Firewall policy tester for the Module 3 assessment.

Evaluates a ruleset against a list of traffic flows and reports whether each
flow is allowed or denied, which rule decided it, and whether that matches
what the requirements say should happen.

Evaluation model (same idea as the FW-OT-01 ruleset in the module):
  - Rules are checked from top to bottom. The FIRST rule that matches decides.
  - If no rule matches, the flow is denied (implicit default deny).
  - A flow is described as: source zone, destination zone, protocol, port.
  - Return traffic is assumed to be handled by stateful inspection, so you
    only write rules for the direction that starts the connection.

Usage:
  python3 fw_policy_tester.py <ruleset.csv> <flows.csv>

Ruleset columns:  rule,action,src,dst,protocol,port
  action   = ALLOW or DENY
  src, dst = Control, Supervisory, DMZ, Enterprise, Management, Quarantine or ANY
  protocol = TCP, UDP, ICMP or ANY
  port     = a number (502), a range (80-443) or ANY

Flows columns:    id,src,dst,protocol,port,expected
"""
import csv
import sys

def parse_port(text):
    t = (text or "").strip().upper()
    if t in ("", "ANY"):
        return (0, 65535)
    if "-" in t:
        lo, hi = t.split("-", 1)
        return (int(lo), int(hi))
    return (int(t), int(t))

def load_rules(path):
    rules = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("rule", "").strip():
                continue
            rules.append({
                "rule": row["rule"].strip(),
                "action": row["action"].strip().upper(),
                "src": row["src"].strip().upper(),
                "dst": row["dst"].strip().upper(),
                "proto": row["protocol"].strip().upper(),
                "port": parse_port(row["port"]),
                "port_text": (row["port"] or "ANY").strip().upper(),
            })
    for r in rules:
        if r["action"] not in ("ALLOW", "DENY"):
            sys.exit(f"Rule {r['rule']}: action must be ALLOW or DENY, got '{r['action']}'")
    return rules

def load_flows(path):
    flows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("id", "").strip():
                continue
            flows.append({
                "id": row["id"].strip(),
                "src": row["src"].strip().upper(),
                "dst": row["dst"].strip().upper(),
                "proto": row["protocol"].strip().upper(),
                "port": row["port"].strip().upper(),
                "expected": row["expected"].strip().upper(),
            })
    return flows

def matches(rule, flow):
    if rule["src"] != "ANY" and rule["src"] != flow["src"]:
        return False
    if rule["dst"] != "ANY" and rule["dst"] != flow["dst"]:
        return False
    if rule["proto"] != "ANY" and rule["proto"] != flow["proto"]:
        return False
    if flow["proto"] == "ICMP" or flow["port"] in ("", "ANY"):
        return rule["proto"] in ("ANY", "ICMP") or rule["port"] == (0, 65535)
    p = int(flow["port"])
    return rule["port"][0] <= p <= rule["port"][1]

def decide(rules, flow):
    for r in rules:
        if matches(r, flow):
            return r["action"], r["rule"]
    return "DENY", "default"

def covers(a, b):
    """True if rule a matches everything rule b matches (so b is shadowed when a is earlier)."""
    return ((a["src"] == "ANY" or a["src"] == b["src"]) and
            (a["dst"] == "ANY" or a["dst"] == b["dst"]) and
            (a["proto"] == "ANY" or a["proto"] == b["proto"]) and
            a["port"][0] <= b["port"][0] and a["port"][1] >= b["port"][1])

def audit(rules):
    notes = []
    for i, r in enumerate(rules):
        if r["action"] == "ALLOW" and r["src"] == "ANY" and r["dst"] == "ANY" and r["proto"] == "ANY" and r["port"] == (0, 65535):
            notes.append(f"Rule {r['rule']}: ALLOW ANY ANY ANY ANY permits everything not caught above it.")
        for j in range(i):
            if covers(rules[j], r):
                notes.append(f"Rule {r['rule']} can never take effect: rule {rules[j]['rule']} above it already covers it.")
                break
    if rules and not (rules[-1]["action"] == "DENY" and rules[-1]["src"] == "ANY" and rules[-1]["dst"] == "ANY"):
        notes.append("No explicit final DENY rule. Evaluation falls back to the implicit default deny.")
    return notes

def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    rules = load_rules(sys.argv[1])
    flows = load_flows(sys.argv[2])
    print(f"Loaded {len(rules)} rules and {len(flows)} flows.\n")
    print(f"{'FLOW':<6} {'SRC -> DST':<28} {'TRAFFIC':<12} {'WANT':<6} {'GOT':<6} {'RULE':<8} RESULT")
    print("-" * 82)
    passed = 0
    for f in flows:
        got, rule = decide(rules, f)
        ok = (got == f["expected"])
        passed += ok
        traffic = f["proto"] if f["proto"] == "ICMP" else f"{f['proto']}/{f['port']}"
        print(f"{f['id']:<6} {f['src'] + ' -> ' + f['dst']:<28} {traffic:<12} {f['expected']:<6} {got:<6} {rule:<8} {'PASS' if ok else 'FAIL'}")
    print("-" * 82)
    print(f"Score: {passed}/{len(flows)} flows behave as required.\n")
    notes = audit(rules)
    if notes:
        print("Ruleset audit notes:")
        for n in notes:
            print("  - " + n)
    sys.exit(0 if passed == len(flows) else 1)

if __name__ == "__main__":
    main()
