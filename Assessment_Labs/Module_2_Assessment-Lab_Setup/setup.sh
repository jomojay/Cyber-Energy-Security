#!/usr/bin/env bash
# ============================================================================
# Palanca Gas Plant — Module 2 Lab Environment Setup
# Run this once per lab session (instructor machine or each trainee's VM).
# ============================================================================
set -euo pipefail

echo "=============================================================="
echo " Palanca Lab — Module 2: Network Mapping & Asset Discovery"
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

echo "--> Starting Palanca lab containers..."
docker compose up -d

# ---- 3. Wait for the engineering workstation to be exec-able ----
echo "--> Waiting for eng-ws-01 to come up..."
for i in $(seq 1 15); do
  docker exec eng-ws-01 true &>/dev/null && break
  sleep 1
done

# ---- 4. Health check every Modbus device (retries — a cold build on
#          a slower laptop can take longer than a fixed sleep covers) ----
echo "--> Verifying Modbus devices are reachable..."
FAILED=0
for pair in "plc-main-01:192.168.1.10" "plc-aux-01:192.168.1.11" \
            "gen1-rtu:192.168.1.20" "gen2-rtu:192.168.1.21" \
            "prot-rel-01:192.168.1.30" "prot-rel-02:192.168.1.31" \
            "vfd-pump-01:192.168.1.40"; do
  NAME="${pair%%:*}"
  IP="${pair##*:}"
  OK=0
  for attempt in $(seq 1 15); do
    if docker exec eng-ws-01 python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('$IP', 502)); print('OK')
except Exception as e:
    print('FAIL'); exit(1)
" &>/dev/null; then
      OK=1
      break
    fi
    sleep 2
  done
  if [ "$OK" -eq 1 ]; then
    echo "    [OK]   $NAME ($IP:502)"
  else
    echo "    [FAIL] $NAME ($IP:502) — check 'docker compose logs $NAME'"
    FAILED=1
  fi
done

# ---- 5. Find the SPAN-port equivalent (the docker bridge for ot_control) ----
BRIDGE=$(docker network inspect palanca-lab_ot_control -f '{{.Id}}' | cut -c1-12)
BRIDGE_IF="br-${BRIDGE}"

echo ""
echo "=============================================================="
echo " Lab environment is up."
echo "=============================================================="
echo ""
echo " Engineering workstation (your working point for every lab day):"
echo "    docker exec -it eng-ws-01 bash"
echo ""
echo " SPAN-port equivalent for Lab Day 1 passive capture:"
echo "    Host bridge interface: $BRIDGE_IF"
echo "    Run (on the HOST, needs sudo):"
echo "      sudo tcpdump -i $BRIDGE_IF -w /tmp/palanca_ot_capture.pcap"
echo "    Or capture live inside Wireshark using interface '$BRIDGE_IF'."
echo ""
echo " SW-CORE-01 switch (Lab Day 2 — ARP/MAC tables):"
echo "    docker exec -it eng-ws-01 ssh admin@sw-core-01"
echo "    password: palanca-lab"
echo "    commands: show mac-address-table | show arp"
echo ""
echo " Full device/IP map: see README.md"
echo ""
if [ "$FAILED" -ne 0 ]; then
  echo " WARNING: one or more devices failed the health check — see above."
  exit 1
fi
