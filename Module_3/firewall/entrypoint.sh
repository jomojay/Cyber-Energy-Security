#!/usr/bin/env bash
# ============================================================================
# fw-ot-01 — Module 3 Day 4 hands-on firewall lab
#
# This is deliberately NOT the ruleset. fw-ot-01 boots wide open (FORWARD
# policy ACCEPT, zero rules) — every zone can currently reach every other
# zone. Implementing the Palanca FW-OT-01 ruleset (R01-R12 + R99 from
# ../firewall-rules-module3.csv) on THIS container's FORWARD chain is
# the trainee exercise. See ../LAB_GUIDE.md.
#
# Re-running this container (docker compose restart fw-ot-01) always
# resets back to this same open baseline — a safe way to start over.
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

iptables -F FORWARD
iptables -P FORWARD ACCEPT

cat <<'BANNER'
==============================================================
 fw-ot-01 — Module 3 Day 4: Firewall Configuration (hands-on)
==============================================================
 Starting state: FORWARD policy ACCEPT, no rules. Every zone can
 currently reach every other zone.

 Your task: implement the Palanca FW-OT-01 ruleset
 (firewall-rules-module3.csv, R01-R12 + R99) as iptables rules on
 this container's FORWARD chain.

 Get in with:   docker exec -it fw-ot-01 bash
 Start here:    ../LAB_GUIDE.md
 Self-check:    ../scripts/test_firewall_rules.sh
 Start over:    docker compose restart fw-ot-01
==============================================================
BANNER

exec tail -f /dev/null
