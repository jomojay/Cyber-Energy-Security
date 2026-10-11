#!/usr/bin/env bash
# Checks the assessment overlay is behaving. Run after setup, and again
# 10 minutes before candidates arrive.
cd "$(dirname "$0")"
ok=0; bad=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  [OK]   $1"; ok=$((ok+1)); else echo "  [FAIL] $1"; bad=$((bad+1)); fi; }
echo "Container checks"
for c in plc-main-01 plc-aux-01 gen1-rtu gen2-rtu prot-rel-01 prot-rel-02 vfd-pump-01 sw-core-01 traffic-gen eng-ws-01 rogue-dev switch-primer; do
  check "$c is running" "[ \"\$(docker inspect -f '{{.State.Running}}' $c 2>/dev/null)\" = true ]"
done
echo "Behaviour checks"
check "switch neighbour table lists the unfamiliar device (192.168.1.99)" "docker exec sw-core-01 ip neigh | grep -q '192.168.1.99.*lladdr'"
check "switch neighbour table lists the legitimate polling master (192.168.1.200)" "docker exec sw-core-01 ip neigh | grep -q '192.168.1.200.*lladdr'"
check "HMI-01 is reachable on the control subnet (flat-network finding present)" "docker exec eng-ws-01 python3 -c \"import socket;s=socket.socket();s.settimeout(2);s.connect(('192.168.1.110',80))\""
echo "Vendor override (informational)"
if docker exec eng-ws-01 nmap -sT -p 502 --script modbus-discover 192.168.1.11 2>/dev/null | grep -qi rockwell; then
  echo "  [OK]   modbus-discover reports the overridden vendor for PLC-AUX-01"
else
  echo "  [WARN] could not confirm the vendor string via modbus-discover."
  echo "         Dry-run the Section B3 scan once yourself and note what PLC-AUX-01 reports;"
  echo "         the output format depends on the pymodbus version in your lab image."
fi
echo; echo "Result: $ok passed, $bad failed"
[ "$bad" -eq 0 ]
