#!/usr/bin/env bash
# ============================================================================
# INSTRUCTOR-ONLY ANSWER KEY — do not hand this to trainees, and strip this
# whole instructor-only/ folder before sharing the repo with a cohort.
#
# This is NOT run automatically by anything (fw-ot-01 boots wide open —
# see firewall/entrypoint.sh). Day 4 is a hands-on exercise: trainees write
# this ruleset themselves on the running fw-ot-01 container, guided by
# ../LAB_GUIDE.md and the CSV. Use this file to:
#   - grade/verify a trainee's finished ruleset against a known-good one
#   - reset a stuck lab quickly: 'docker exec -i fw-ot-01 bash' <
#     instructor-only/solution_apply_rules.sh (paste/pipe it in) — same
#     effect as running scripts/test_firewall_rules.sh against a working
#     reference to sanity-check the test script itself
#   - answer "is my rule right" during office hours without retyping it
#
# fw-ot-01 — Palanca FW-OT-01 ruleset (Module 3, Section 3.4.3)
# Implements ../firewall-rules-module3.csv literally as FORWARD-chain
# iptables rules. fw-ot-01 is multi-homed onto all six zones (Control,
# Supervisory, DMZ, Management, Quarantine, Enterprise) and does real
# Linux IP forwarding between them — every other container reaches a
# foreign zone only via a route through this container (see setup.sh's
# "cross-zone routing" step), so this FORWARD chain is the only place
# inter-zone traffic can be filtered.
#
# Enforcement is at L3/L4 (source/destination subnet + protocol/port),
# matching what a real firewall actually filters on. The CSV's
# "Protocol" column (Modbus/OPC-UA/HTTPS/SQL/VPN) is realized here as
# the TCP/ICMP port it rides on — the lab's endpoint containers run
# plain stub listeners on those exact ports rather than full protocol
# implementations, since what Day 4 tests is whether the firewall lets
# the right ports through, not whether the payload is protocol-correct.
# ============================================================================
set -euo pipefail

# IP forwarding is actually enabled via docker-compose.yml's
# 'sysctls: net.ipv4.ip_forward: 1' (applied by the daemon before the
# container starts) — some Docker configs mount /proc/sys read-only
# inside the container, so this in-container write is a best-effort
# fallback only, not the primary mechanism.
echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || true
if [[ "$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)" != "1" ]]; then
    echo "fw-ot-01: WARNING — net.ipv4.ip_forward is not 1. Check docker-compose.yml's" \
         "'sysctls:' on this service; cross-zone routing will not work without it." >&2
fi

CONTROL=192.168.1.0/24        # VLAN 10
SUPERVISORY=192.168.2.0/24    # VLAN 20
DMZ=192.168.3.0/24            # VLAN 30
MANAGEMENT=192.168.40.0/24    # VLAN 40 (new — Module 3 Day 4)
QUARANTINE=192.168.99.0/24    # VLAN 99 (new — Module 3 Day 4)
ENTERPRISE=192.168.50.0/24    # Enterprise (new — needed for R08-R12, see README)

iptables -F FORWARD
iptables -P FORWARD DROP

# Return traffic of any already-permitted flow — not itself a CSV rule,
# just standard stateful-firewall practice so R01-R10 don't each need a
# hand-written reverse-direction twin for their own replies.
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# --- R01: Supervisory <-> Control, Modbus/TCP 502, bidirectional ---
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -p tcp --dport 502 -m conntrack --ctstate NEW -j ACCEPT
iptables -A FORWARD -s "$CONTROL" -d "$SUPERVISORY" -p tcp --dport 502 -m conntrack --ctstate NEW -j ACCEPT

# --- R02: Supervisory -> Control, OPC-UA 4840 (read) ---
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -p tcp --dport 4840 -m conntrack --ctstate NEW -j ACCEPT

# --- R03: Supervisory -> Control, ICMP (reachability monitoring) ---
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -p icmp --icmp-type echo-request -j ACCEPT

# --- R04: explicit catch-all deny, Supervisory<->Control ---
# (the final R99 DROP below would catch this anyway; kept explicit so
# the rule table above is implemented 1:1, rule for rule)
iptables -A FORWARD -s "$SUPERVISORY" -d "$CONTROL" -j DROP
iptables -A FORWARD -s "$CONTROL" -d "$SUPERVISORY" -j DROP

# --- R05: Supervisory -> DMZ, OPC-UA 4840 (historian ingest, one-way) ---
iptables -A FORWARD -s "$SUPERVISORY" -d "$DMZ" -p tcp --dport 4840 -m conntrack --ctstate NEW -j ACCEPT

# --- R06: DMZ -> Supervisory, HTTPS 443 (dashboard/monitoring) ---
iptables -A FORWARD -s "$DMZ" -d "$SUPERVISORY" -p tcp --dport 443 -m conntrack --ctstate NEW -j ACCEPT

# --- R07: explicit catch-all deny, DMZ<->Supervisory ---
iptables -A FORWARD -s "$DMZ" -d "$SUPERVISORY" -j DROP
iptables -A FORWARD -s "$SUPERVISORY" -d "$DMZ" -j DROP

# --- R08: DMZ -> Enterprise, SQL 1433 (historian to enterprise reporting) ---
iptables -A FORWARD -s "$DMZ" -d "$ENTERPRISE" -p tcp --dport 1433 -m conntrack --ctstate NEW -j ACCEPT

# --- R09 + R10: Enterprise -> DMZ, HTTPS 443 ---
# R09 (dashboards) and R10 (VPN remote engineering, MFA required) both
# ride tcp/443 to the same destination — identical 5-tuple, so one
# packet-filter rule enforces both. MFA/VPN-vs-dashboard is an
# application-layer distinction a port filter cannot see; a firewall
# alone can't tell those two apart, worth calling out to trainees.
iptables -A FORWARD -s "$ENTERPRISE" -d "$DMZ" -p tcp --dport 443 -m conntrack --ctstate NEW -j ACCEPT

# --- R11: Enterprise -> Control, deny everything ---
# (this is the flagship new check for Day 4 — Module 2's simplified
# ruleset never enforced this at all)
iptables -A FORWARD -s "$ENTERPRISE" -d "$CONTROL" -j DROP

# --- R12: Enterprise -> Supervisory, deny everything ---
iptables -A FORWARD -s "$ENTERPRISE" -d "$SUPERVISORY" -j DROP

# --- R99: default-deny baseline ---
# Everything not explicitly matched above falls through here: Control<->DMZ,
# Control<->Management/Quarantine/Enterprise, Supervisory<->Management/
# Quarantine, DMZ<->Management/Quarantine, Management<->Quarantine, and the
# reverse of every one-way rule above. The FORWARD policy is already DROP;
# this rule just makes the drop count visible in `iptables -L FORWARD -v`.
iptables -A FORWARD -j LOG --log-prefix "FW-OT-01 R99-DENY: " --log-level info 2>/dev/null || true
iptables -A FORWARD -j DROP

echo "fw-ot-01: reference ruleset applied (R01-R12 + R99 default-deny)."
iptables -L FORWARD -v -n --line-numbers
