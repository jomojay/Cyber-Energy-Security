#!/usr/bin/env bash
# ============================================================================
# Palanca Gas Plant — Module 3, Day 4: Firewall Configuration
# Builds the extended lab (Module 2 topology + Management/Quarantine/
# Enterprise zones + fw-ot-01), wires up cross-zone routing through the
# firewall, and applies the full R01-R12 + R99 ruleset.
# ============================================================================
set -euo pipefail

echo "=============================================================="
echo " Palanca Lab — Module 3 Day 4: Firewall Configuration"
echo "=============================================================="

# ---- 1. Prerequisite check ----
if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker is not installed. Install Docker Engine + Compose plugin first:"
  echo "  https://docs.docker.com/engine/install/"
  exit 1
fi
if ! docker compose version &>/dev/null; then
  echo "ERROR: 'docker compose' (v2 plugin) not found. Install the compose plugin."
  exit 1
fi

# ---- 2. Build and start the stack ----
echo "--> Building lab images (first run takes a few minutes)..."
docker compose build --quiet

echo "--> Starting Palanca lab containers (6 zones)..."
docker compose up -d

# ---- 3. Wait for eng-ws-01 to be exec-able ----
echo "--> Waiting for eng-ws-01 to come up..."
for i in $(seq 1 15); do
  docker exec eng-ws-01 true &>/dev/null && break
  sleep 1
done

# ---- 4. Cross-zone routing through fw-ot-01 ----
# Docker does not route between separate bridge networks on its own, and
# compose has no field to set a container's default gateway to another
# container's address — so every container that needs to reach a foreign
# zone gets an explicit route pointing that traffic at fw-ot-01's address
# on its OWN local subnet. A single summarized /16 route is enough since
# every zone in this lab (control/supervisory/dmz/management/quarantine/
# enterprise) lives inside 192.168.0.0/16 — the more specific, automatic
# connected-subnet route for the container's own zone still wins for local
# traffic, and this route only ever matches genuinely cross-zone packets.
echo "--> Routing cross-zone traffic through fw-ot-01..."
declare -A ROUTE_VIA=(
  [plc-main-01]=192.168.1.5      [plc-aux-01]=192.168.1.5
  [gen1-rtu]=192.168.1.5         [gen2-rtu]=192.168.1.5
  [prot-rel-01]=192.168.1.5      [prot-rel-02]=192.168.1.5
  [vfd-pump-01]=192.168.1.5
  [scada-hmi-01]=192.168.2.5     [scada-hmi-02]=192.168.2.5
  [eng-ws-01]=192.168.2.5
  [historian-01]=192.168.3.5
  [mgmt-ws-01]=192.168.40.5
  [quarantine-host-01]=192.168.99.5
  [enterprise-ws-01]=192.168.50.5
)
for container in "${!ROUTE_VIA[@]}"; do
  via="${ROUTE_VIA[$container]}"
  if docker exec "$container" ip route replace 192.168.0.0/16 via "$via" &>/dev/null; then
    echo "    $container -> 192.168.0.0/16 via $via  [ok]"
  else
    echo "    $container -> 192.168.0.0/16 via $via  [FAILED — is the container up? does it have iproute2?]"
  fi
done

# ---- 5. Verify fw-ot-01 booted into its expected wide-open starting state ----
# This is a hands-on exercise — fw-ot-01 intentionally boots with FORWARD
# policy ACCEPT and no rules. Trainees implement the ruleset themselves;
# see LAB_GUIDE.md. This step just confirms the container came up in that
# starting state, not that any rules exist yet.
echo "--> Verifying fw-ot-01 booted into its wide-open starting state..."
if docker exec fw-ot-01 iptables -L FORWARD -n | head -1 | grep -q "policy ACCEPT"; then
  echo "    fw-ot-01 FORWARD policy is ACCEPT, ready for the Day 4 exercise [ok]"
  echo "    Next: docker exec -it fw-ot-01 bash   — then see LAB_GUIDE.md"
else
  echo "    WARNING: fw-ot-01 FORWARD policy isn't ACCEPT — check: docker compose logs fw-ot-01"
fi

# ---- 6. Health check every Modbus device (retries — a cold build on
#          a slower laptop can take longer than a fixed sleep covers) ----
echo "--> Verifying Modbus devices are reachable from Control zone (traffic-gen)..."
FAILED=0
for pair in "plc-main-01:192.168.1.10" "plc-aux-01:192.168.1.11" \
            "gen1-rtu:192.168.1.20" "gen2-rtu:192.168.1.21" \
            "prot-rel-01:192.168.1.30" "prot-rel-02:192.168.1.31" \
            "vfd-pump-01:192.168.1.40"; do
  NAME="${pair%%:*}"
  IP="${pair##*:}"
  OK=0
  for attempt in $(seq 1 15); do
    if docker exec traffic-gen python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$IP', 502)); print('OK')
except Exception:
    exit(1)
" &>/dev/null; then
      OK=1
      break
    fi
    sleep 1
  done
  if [[ $OK -eq 1 ]]; then
    echo "    $NAME ($IP:502) reachable [ok]"
  else
    echo "    $NAME ($IP:502) NOT reachable [FAIL]"
    FAILED=1
  fi
done

echo ""
echo "=============================================================="
if [[ $FAILED -eq 0 ]]; then
  echo " Lab is up — fw-ot-01 is wide open, no firewall rules yet."
  echo " Next: open LAB_GUIDE.md and start implementing the ruleset."
  echo "   docker exec -it fw-ot-01 bash"
  echo "   ./scripts/test_firewall_rules.sh   (run anytime to check progress)"
else
  echo " Lab came up with failures above — check 'docker compose logs <service>'."
fi
echo "=============================================================="
