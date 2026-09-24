#!/usr/bin/env bash
# ============================================================================
# Module 3 Day 4 — Firewall rule verification
# Exercises every rule in ../firewall-rules-module3.csv (R01-R12 + R99)
# by attempting the exact traffic it should allow or deny, from inside the
# actual zone containers, and reports PASS/FAIL against the expected
# behaviour. This is the "test results showing each rule's expected
# allow/deny behaviour confirmed" deliverable for Day 4.
#
# Distinguishes CONNECTED / REFUSED / TIMEOUT rather than just success-or-
# not: fw-ot-01's default-deny uses DROP (silent), so a correctly-blocked
# attempt should come back as a TIMEOUT, not a fast REFUSED — a REFUSED on
# an expected-DENY means the packet reached the destination (the firewall
# did NOT block it) and only failed because nothing was listening there,
# which is a different, worse finding than a working DROP.
# ============================================================================
set -uo pipefail

RESULTS_LOG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs/firewall_test_results.txt"
mkdir -p "$(dirname "$RESULTS_LOG")"
: > "$RESULTS_LOG"

PASS=0
FAIL=0

log() { echo "$*" | tee -a "$RESULTS_LOG"; }

# tcp_probe <container> <ip> <port> -> prints CONNECTED | REFUSED | TIMEOUT
tcp_probe() {
  local container="$1" ip="$2" port="$3"
  docker exec "$container" python3 -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(4)
try:
    s.connect(('$ip', $port))
    print('CONNECTED')
except socket.timeout:
    print('TIMEOUT')
except ConnectionRefusedError:
    print('REFUSED')
except OSError:
    print('TIMEOUT')
" 2>/dev/null
}

# icmp_probe <container> <ip> -> prints REACHABLE | TIMEOUT
icmp_probe() {
  local container="$1" ip="$2"
  if docker exec "$container" ping -c2 -W2 "$ip" &>/dev/null; then
    echo "REACHABLE"
  else
    echo "TIMEOUT"
  fi
}

# check_tcp <rule> <desc> <container> <ip> <port> <allow|deny>
check_tcp() {
  local rule="$1" desc="$2" container="$3" ip="$4" port="$5" expect="$6"
  local result; result="$(tcp_probe "$container" "$ip" "$port")"
  local ok=0
  if [[ "$expect" == "allow" && "$result" == "CONNECTED" ]]; then ok=1; fi
  if [[ "$expect" == "deny" && "$result" == "TIMEOUT" ]]; then ok=1; fi
  if [[ $ok -eq 1 ]]; then
    log "[PASS] $rule  $desc  -> $result (expected ${expect^^})"
    PASS=$((PASS + 1))
  else
    log "[FAIL] $rule  $desc  -> $result (expected ${expect^^})"
    FAIL=$((FAIL + 1))
  fi
}

# check_icmp <rule> <desc> <container> <ip> <allow|deny>
check_icmp() {
  local rule="$1" desc="$2" container="$3" ip="$4" expect="$5"
  local result; result="$(icmp_probe "$container" "$ip")"
  local ok=0
  if [[ "$expect" == "allow" && "$result" == "REACHABLE" ]]; then ok=1; fi
  if [[ "$expect" == "deny" && "$result" == "TIMEOUT" ]]; then ok=1; fi
  if [[ $ok -eq 1 ]]; then
    log "[PASS] $rule  $desc  -> $result (expected ${expect^^})"
    PASS=$((PASS + 1))
  else
    log "[FAIL] $rule  $desc  -> $result (expected ${expect^^})"
    FAIL=$((FAIL + 1))
  fi
}

log "=============================================================="
log " Palanca FW-OT-01 ruleset verification — $(date -u +%FT%TZ)"
log "=============================================================="

check_tcp  "R01" "Supervisory(eng-ws-01) -> Control(plc-main-01) Modbus/502"      eng-ws-01          192.168.1.10  502  allow
check_tcp  "R02" "Supervisory(eng-ws-01) -> Control(plc-main-01) OPC-UA/4840"     eng-ws-01          192.168.1.10  4840 allow
check_icmp "R03" "Supervisory(eng-ws-01) -> Control(plc-main-01) ICMP ping"       eng-ws-01          192.168.1.10       allow
check_tcp  "R04" "Supervisory(eng-ws-01) -> Control(plc-main-01) other/23 (catch-all)" eng-ws-01     192.168.1.10  23   deny

check_tcp  "R05" "Supervisory(eng-ws-01) -> DMZ(historian-01) OPC-UA/4840"        eng-ws-01          192.168.3.10  4840 allow
check_tcp  "R06" "DMZ(historian-01) -> Supervisory(scada-hmi-01) HTTPS/443"       historian-01       192.168.2.10  443  allow
check_tcp  "R07" "DMZ(historian-01) -> Supervisory(scada-hmi-01) other/80 (catch-all, port genuinely open there)" historian-01 192.168.2.10 80 deny

check_tcp  "R08" "DMZ(historian-01) -> Enterprise(enterprise-ws-01) SQL/1433"     historian-01       192.168.50.10 1433 allow
check_tcp  "R09/R10" "Enterprise(enterprise-ws-01) -> DMZ(historian-01) HTTPS/443" enterprise-ws-01  192.168.3.10  443  allow

check_tcp  "R11" "Enterprise(enterprise-ws-01) -> Control(plc-main-01) Modbus/502 (must be blocked)" enterprise-ws-01 192.168.1.10 502 deny
check_tcp  "R12" "Enterprise(enterprise-ws-01) -> Supervisory(scada-hmi-01) HTTPS/443 (must be blocked)" enterprise-ws-01 192.168.2.10 443 deny

log "-- R99 default-deny baseline (Management/Quarantine isolation, Control<->DMZ) --"
check_tcp  "R99" "Supervisory(eng-ws-01) -> Management(mgmt-ws-01) 8080"          eng-ws-01          192.168.40.10 8080 deny
check_tcp  "R99" "Supervisory(eng-ws-01) -> Quarantine(quarantine-host-01) 8080"  eng-ws-01          192.168.99.10 8080 deny
check_tcp  "R99" "Quarantine(quarantine-host-01) -> Control(plc-main-01) Modbus/502" quarantine-host-01 192.168.1.10 502 deny
check_tcp  "R99" "Control(plc-main-01) -> DMZ(historian-01) HTTP/80 (no rule permits this pair)" plc-main-01 192.168.3.10 80 deny

log "=============================================================="
log " PASS: $PASS   FAIL: $FAIL"
log " Full results saved to: $RESULTS_LOG"
log "=============================================================="

[[ $FAIL -eq 0 ]]
