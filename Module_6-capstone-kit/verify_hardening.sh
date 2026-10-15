#!/usr/bin/env bash
# ============================================================================
# Module 6 — Hardening Verification Script (Lab Days 5-6)
# Checks several of the hardening_checklist.md items automatically against
# the running Palanca Docker lab — either the Module 3 firewall lab
# (recommended: Module 2's topology + FW-OT-01) or the plain Module 2 lab.
# Run it from the same host as the Docker lab, from any directory. No sudo.
#
#   Check 1  Flat network: no Supervisory/DMZ host is dual-homed on Control   (6.5.3)
#   Check 2  SW-CORE-01 no longer accepts the default lab password            (6.5.5)
#   Check 3  Only conduit ports (502, 4840) reachable on Control from
#            Supervisory (eng-ws-01's view)                                   (6.5.2/6.5.6)
#   Check 4  FW-OT-01 ends in default-deny            [Module 3 lab only]     (6.5.2)
#   Check 5  FW-OT-01 filters Modbus by function code [Module 3 lab only]     (6.5.6)
#
# Every run is saved to logs/verify_hardening_<timestamp>.txt — keep the
# before/after logs as evidence for your Day 5 deliverable.
# Exit code: 0 = all checks passed, 1 = at least one FAIL, 2 = lab not ready.
# ============================================================================
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

CONTROL_PREFIX="192.168.1."
# Every address that exists on the Control segment in either lab build
# (.110/.111 are the Module 2 HMIs' dual-homed Control-side addresses).
CONTROL_TARGETS="192.168.1.1 192.168.1.10 192.168.1.11 192.168.1.20 192.168.1.21 192.168.1.30 192.168.1.31 192.168.1.40 192.168.1.110 192.168.1.111"
SCAN_PORTS="21,22,23,80,102,443,502,4840,8080"
CONDUIT_PORTS="502 4840"            # R01 Modbus/TCP, R02 OPC-UA (Module 3 ruleset)
DEFAULT_SWITCH_PASSWORD="palanca-lab"

PASS=0
FAIL=0

check() {
  local desc="$1"
  local result="$2"  # 0 = pass, 1 = fail
  if [ "$result" -eq 0 ]; then
    echo "  [PASS] $desc"
    PASS=$((PASS+1))
  else
    echo "  [FAIL] $desc"
    FAIL=$((FAIL+1))
  fi
}

running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = "true" ]; }

main() {
  echo "=============================================================="
  echo " Module 6 Hardening Verification — $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=============================================================="

  # ---- Pre-flight: never report PASS against a lab that isn't there ----
  if ! command -v docker &>/dev/null; then
    echo "ERROR: docker not found. Run this on the host that runs the Palanca Docker lab."
    return 2
  fi
  if ! docker info &>/dev/null; then
    echo "ERROR: cannot talk to the Docker daemon. Is Docker running, and is your user"
    echo "       in the 'docker' group? (sudo usermod -aG docker \$USER, then log out/in)"
    return 2
  fi
  local missing=()
  for c in eng-ws-01 sw-core-01 plc-main-01; do
    running "$c" || missing+=("$c")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "ERROR: lab container(s) not running: ${missing[*]}"
    echo "       Start the lab first:  cd ../Module_3 && ./setup.sh"
    echo "       (or, for the plain Module 2 lab:  cd ../Module_2_Lab_Setup && ./setup.sh)"
    return 2
  fi
  local fw=0
  if running fw-ot-01; then
    fw=1
    echo " Lab detected: Module 3 firewall lab (FW-OT-01 present)"
  else
    echo " Lab detected: Module 2 lab (no FW-OT-01 — checks 4-5 will be skipped)"
  fi

  echo ""
  echo "-- Check 1: Flat-network (Control/Supervisory separation) --"
  local dual=()
  for c in eng-ws-01 scada-hmi-01 scada-hmi-02 historian-01; do
    running "$c" || continue
    for ip in $(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$c"); do
      [[ "$ip" == "$CONTROL_PREFIX"* ]] && dual+=("$c ($ip)")
    done
  done
  if [ "${#dual[@]}" -eq 0 ]; then
    check "No Supervisory/DMZ host has a direct interface on the Control Zone (192.168.1.0/24)" 0
  else
    echo "  Dual-homed onto Control: ${dual[*]}"
    check "Supervisory/DMZ hosts still bypass the conduit via a direct Control interface" 1
  fi

  echo ""
  echo "-- Check 2: Default credentials on SW-CORE-01 --"
  # Tested from inside sw-core-01 itself (paramiko is already installed there),
  # so the result depends only on the credential, not on firewall reachability.
  local cred
  cred=$(docker exec -i sw-core-01 python3 - "$DEFAULT_SWITCH_PASSWORD" 2>/dev/null <<'PY'
import logging, sys
import paramiko
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    c.connect("127.0.0.1", 22, username="admin", password=sys.argv[1], timeout=10,
              banner_timeout=10, auth_timeout=10, allow_agent=False, look_for_keys=False)
    print("ACCEPTED")
except paramiko.AuthenticationException:
    print("REJECTED")
except Exception as e:
    print(f"ERROR {type(e).__name__}")
finally:
    c.close()
PY
)
  case "$cred" in
    REJECTED) check "SW-CORE-01 rejects the default lab password" 0 ;;
    ACCEPTED) check "SW-CORE-01 still accepts the default lab password (admin / $DEFAULT_SWITCH_PASSWORD)" 1 ;;
    *)        echo "  Could not complete an SSH login test against sw-core-01 (${cred:-no output})."
              echo "  Check: docker logs sw-core-01"
              check "SW-CORE-01 credential check could not run" 1 ;;
  esac

  echo ""
  echo "-- Check 3: Ports reachable on Control Zone devices from Supervisory (eng-ws-01) --"
  echo "  Scanning ${SCAN_PORTS} on the Control segment, OT-safe rate (about 1-2 minutes)..."
  local scan
  scan=$(docker exec eng-ws-01 nmap -Pn -sT -T2 --max-rate 10 --max-retries 1 \
           -p "$SCAN_PORTS" -oG - $CONTROL_TARGETS 2>/dev/null)
  if ! grep -q "^# Nmap done" <<<"$scan"; then
    echo "  nmap did not complete inside eng-ws-01."
    check "Control Zone port exposure could not be measured" 1
  else
    # Grepable output: "Host: 192.168.1.10 ()  Ports: 502/open/tcp//mbap///, 22/closed/..."
    local open_list
    open_list=$(awk '/Ports:/ {
        ip = $2
        n = split($0, f, /Ports: /); split(f[2], ports, /, /)
        for (i in ports) { split(ports[i], p, "/"); if (p[2] == "open") print ip ":" p[1] }
      }' <<<"$scan" | sort -t: -k1,1V -k2,2n)
    local plc_main extra=()
    plc_main=$(grep -c '^192\.168\.1\.10:' <<<"$open_list")
    for entry in $open_list; do
      [[ " $CONDUIT_PORTS " == *" ${entry##*:} "* ]] || extra+=("$entry")
    done
    echo "  Open ports seen: $(echo $open_list | tr ' ' ',')"
    echo "  Open ports on PLC-MAIN-01 (192.168.1.10): $plc_main"
    if [ "${#extra[@]}" -eq 0 ]; then
      check "Only conduit ports (${CONDUIT_PORTS// /, }) are reachable on the Control Zone" 0
    else
      echo "  Not on the conduit whitelist: ${extra[*]}"
      check "Non-conduit services are reachable on the Control Zone — review 6.5.2 / 6.5.6" 1
    fi
  fi

  echo ""
  echo "-- Check 4: FW-OT-01 default-deny (R99) --"
  if [ "$fw" -eq 0 ]; then
    echo "  [SKIP] No FW-OT-01 in this lab — firewall items need the Module 3 lab."
  else
    local rules
    rules=$(docker exec fw-ot-01 iptables -S FORWARD 2>/dev/null)
    if grep -qx -- "-P FORWARD DROP" <<<"$rules" || [ "$(tail -n1 <<<"$rules")" = "-A FORWARD -j DROP" ]; then
      check "FW-OT-01 FORWARD chain ends in default-deny" 0
    else
      check "FW-OT-01 FORWARD chain has no default-deny (policy ACCEPT and no final DROP)" 1
    fi
  fi

  echo ""
  echo "-- Check 5: Modbus function-code filtering on FW-OT-01 --"
  if [ "$fw" -eq 0 ]; then
    echo "  [SKIP] No FW-OT-01 in this lab — firewall items need the Module 3 lab."
  else
    # Configuration check: a rule on port 502 that inspects the payload
    # (u32 or string match). Prove the behaviour with your own test too.
    if grep -- "--dport 502" <<<"$rules" | grep -qE -- "-m (u32|string)"; then
      check "FW-OT-01 has a port-502 rule that matches on Modbus function code" 0
    else
      check "FW-OT-01 filters Modbus by port 502 only, not by function code" 1
    fi
  fi

  echo ""
  echo "=============================================================="
  echo " Results: $PASS passed, $FAIL failed"
  echo "=============================================================="
  if [ "$FAIL" -gt 0 ]; then
    echo " Resolve FAILs against hardening_checklist.md before Lab Day 6."
    return 1
  fi
  return 0
}

mkdir -p logs
LOG="logs/verify_hardening_$(date +%Y%m%d_%H%M%S).txt"
main 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
echo " Saved to $(pwd)/$LOG"
exit "$rc"
