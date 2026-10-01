#!/usr/bin/env python3
"""
DAY 6 - Signature detector for the 5 attacks        (Module 4 Lab Run Book, Day 6 / Section 4.5.2)

First find the attacks in Wireshark with the Table 4.3 filters (the Palanca-OT profile has
a button for each). Then turn each filter into Python so it runs automatically:

  1. network_reconnaissance       SYN without ACK to many different ports from one host
  2. modbus_register_enumeration  Modbus reads of registers above the normal map (> 99)
  3. unauthorised_write           Modbus write (FC 5/6/15/16) from a host not on the approved list
  4. plc_program_upload           a frame bigger than 1000 bytes sent TO a PLC
  5. arp_spoofing_mitm            one IP address announced by two different MAC addresses

Run:      python3 workbook/day6_signatures.py
          python3 workbook/day6_signatures.py captures/assessment/palanca_attack_challenge.pcap   (Day 7: any capture)
Compare:  ./otlab hunt attack
"""
import os
import sys

LAB = os.path.dirname(os.path.abspath(__file__))            # find the Module 4 folder, wherever this script is run from
while not os.path.isdir(os.path.join(LAB, "otkit")):
    LAB = os.path.dirname(LAB)
VENV = os.path.join(LAB, ".venv")                              # if setup.sh installed the libraries there, use them
if os.path.exists(os.path.join(VENV, "bin", "python")) and os.path.realpath(sys.prefix) != os.path.realpath(VENV):
    os.execv(os.path.join(VENV, "bin", "python"), [os.path.join(VENV, "bin", "python")] + sys.argv)
ARGS = [os.path.abspath(a) for a in sys.argv[1:]]              # a capture file given on the command line (Day 7)
sys.path.insert(0, LAB)
os.chdir(LAB)                                                  # so "captures/..." and "results/..." always work
import pandas as pd  # noqa: E402
from otkit.load import load_packets  # noqa: E402

CAPTURE = ARGS[0] if ARGS else "captures/palanca_attack_challenge.pcap"
OUTPUT = "results/my_day6_findings.csv"
if ARGS:   # another capture (Day 7): keep your Day 6 hand-in, write a separate file
    OUTPUT = f"results/my_day6_findings_{os.path.basename(os.path.dirname(CAPTURE))}_{os.path.splitext(os.path.basename(CAPTURE))[0]}.csv"

APPROVED_WRITERS = {"192.168.2.10", "192.168.2.20"}          # HMI-01, ENG-WS
PLCS = {"192.168.1.10", "192.168.1.11"}                      # PLC-MAIN-01, PLC-AUX-01
HIGHEST_NORMAL_REGISTER = 99
SCAN_MIN_PORTS = 5

pkts = load_packets(CAPTURE)
pkts["ip_src"] = pkts["ip_src"].astype(str)
pkts["ip_dst"] = pkts["ip_dst"].astype(str)
findings = []


def report(attack_type, rows, source, evidence):
    """Record one finding: when it started, who did it, and why we think so."""
    first = rows.iloc[0]
    findings.append({"attack_type": attack_type, "time_seconds": round(float(first["rel"]), 2),
                     "first_packet": int(first["no"]), "src_ip": source, "evidence": evidence})
    print(f"[{attack_type}] at {first['rel']:.1f} s (packet {first['no']}) from {source}: {evidence}")


# 1. Reconnaissance -  Wireshark:  tcp.flags.syn==1 && tcp.flags.ack==0
# >>> SOLUTION: SYN scan
# HINT: syn = pkts[pkts["syn"] & ~pkts["ack"]]; then for each source (groupby("ip_src")) count the
#       number of DIFFERENT destination ports with ["dport"].nunique(). 5 or more = a scan.
syn = pkts[pkts["syn"] & ~pkts["ack"]]
for src, rows in syn.groupby("ip_src"):
    ports = rows["dport"].nunique()
    if ports >= SCAN_MIN_PORTS:
        report("network_reconnaissance", rows, src, f"SYN to {ports} different ports on {', '.join(rows['ip_dst'].unique())}")
# <<<

# 2. Register enumeration -  Wireshark:  modbus.func_code in {1,2,3,4} && modbus.reference_num > 99
# >>> SOLUTION: register sweep
# HINT: requests are rows with pkts["mb_request"] True; reads have mb_fc in [1,2,3,4];
#       the register number is mb_addr. Group what you find by source.
reads = pkts[pkts["mb_request"] & pkts["mb_fc"].isin([1, 2, 3, 4])]
high = reads[reads["mb_addr"] > HIGHEST_NORMAL_REGISTER]
for src, rows in high.groupby("ip_src"):
    report("modbus_register_enumeration", rows, src,
           f"{len(rows)} reads above register {HIGHEST_NORMAL_REGISTER} (up to {rows['mb_addr'].max()})")
# <<<

# 3. Unauthorised write -  Wireshark:  modbus.func_code in {5,6,15,16} && tcp.dstport==502 && !(ip.src in {...})
# >>> SOLUTION: writes from unapproved hosts
# HINT: writes = requests with mb_fc in [5, 6, 15, 16]; keep those whose ip_src is NOT in APPROVED_WRITERS
#       ( ~writes["ip_src"].isin(APPROVED_WRITERS) ).
writes = pkts[pkts["mb_request"] & pkts["mb_fc"].isin([5, 6, 15, 16])]
bad_writes = writes[~writes["ip_src"].isin(APPROVED_WRITERS)]
for src, rows in bad_writes.groupby("ip_src"):
    report("unauthorised_write", rows, src,
           f"{len(rows)} write(s), FC {[int(x) for x in sorted(rows['mb_fc'].unique())]}, to {', '.join(rows['ip_dst'].unique())}")
# <<<

# 4. PLC program upload -  Wireshark:  ip.dst in {PLCs} && frame.len > 1000
# >>> SOLUTION: big frames to a PLC
# HINT: pkts["ip_dst"].isin(PLCS) & (pkts["len"] > 1000)
big = pkts[pkts["ip_dst"].isin(PLCS) & (pkts["len"] > 1000)]
for src, rows in big.groupby("ip_src"):
    report("plc_program_upload", rows, src,
           f"{len(rows)} large frames ({rows['payload'].sum():,} bytes) to {', '.join(rows['ip_dst'].unique())} port {rows['dport'].iloc[0]}")
# <<<

# 5. ARP spoofing -  Wireshark:  arp.duplicate-address-detected
# >>> SOLUTION: one IP, several MACs
# HINT: arp = pkts[pkts["arp_op"] > 0]; for each claimed IP (groupby("arp_ip")) count the different
#       MAC addresses in "arp_mac" with .nunique(). More than 1 = two cards claim the same IP.
arp = pkts[pkts["arp_op"] > 0].copy()
arp["arp_ip"] = arp["arp_ip"].astype(str)
arp["arp_mac"] = arp["arp_mac"].astype(str)
for ip, rows in arp.groupby("arp_ip"):
    macs = list(dict.fromkeys(rows["arp_mac"]))    # in order of first appearance
    if len(macs) > 1:
        rogue = rows[rows["arp_mac"] != macs[0]]
        report("arp_spoofing_mitm", rogue, ip, f"{ip} claimed by {macs[0]} and then by {', '.join(macs[1:])}")
# <<<

os.makedirs("results", exist_ok=True)
pd.DataFrame(findings).to_csv(OUTPUT, index=False)
print(f"\n{len(findings)} finding(s), {len({f['attack_type'] for f in findings})} attack type(s). Saved {OUTPUT}")
print("Your instructor grades it with:  ./otlab grade attacks", OUTPUT)

# For your investigation report, for EACH attack write down:
#   attack type, time, source IP, and the evidence (paste a Wireshark screenshot of the filter result).
