# Module 6 — Trainee Lab Guide (Incident Response & Hardening)

This guide is the hands-on companion to **`Module_6_Lab_Run_Book.docx`**.
It uses the run book's day and step numbers. Each step repeats what the
run book asks and then gives the exact commands for this lab. The run book
sets **what** you deliver. This guide shows **how** to do it in this lab.

All paths assume the course repository layout:

```
Cyber-Energy-Security/
├── Module_2_Lab_Setup/      Module 2 Docker lab (flat network)
├── Module_3/                Module 2 topology + FW-OT-01 firewall  ← Day 5-6 target
├── Module_4-traffic-lab/    traffic analysis tools                  ← Day 4
├── Module_5-vuln-lab/       OTSafeScanner                           ← Day 6
└── Module_6-capstone-kit/   this kit
```

Commands marked **(host)** run in a terminal on your own machine.
Commands marked **(eng-ws-01)** run inside the engineering workstation
(`docker exec -it eng-ws-01 bash`).

---

## Before you start

Check these before Day 4. They are the most common reasons a capstone day stalls.

| # | Check | How |
|---|-------|-----|
| 1 | Docker works without sudo | `docker ps` (host) lists containers or an empty table, with no "permission denied" |
| 2 | Module 4 tools are set up | `cd Module_4-traffic-lab && ./otlab doctor` |
| 3 | You still have your **Module 5 scan results**. This is your Day 6 "before" data | `ls Module_5-vuln-lab/my-results/scan_results_*.json`. If the folder is missing and your Module 2 lab is still running, do Day 5 Part A step 1 now |
| 4 | You still have your **Module 3 firewall ruleset** | `ls Module_3/my_firewall_rules.txt`. If you don't have it, you will rebuild it on Day 5 from `Module_3/LAB_GUIDE.md` |

---

## Day 1 — IR Playbook Development

No lab infrastructure. Follow the run book:

1. Write a complete playbook for each of: unauthorised Modbus write (6.2.2), ransomware in the OT DMZ (6.2.3), insider threat (6.2.4).
2. Every playbook must include **all** standard components from Section 6.2.1, including communication and post-incident sections.

Tip: use real Palanca names in your playbooks (PLC-MAIN-01 `192.168.1.10`,
SCADA-HMI-01 `192.168.2.10`, ENG-WS-01 `192.168.2.20`, FW-OT-01, Control Zone
`192.168.1.0/24`). You will reuse the Modbus-write playbook on Day 4.

**Deliverable:** three completed IR playbooks.

---

## Days 2 and 3 — Tabletop Exercises

Facilitator-led, with no lab infrastructure. Your facilitator assigns roles (Incident
Commander, OT Engineer, SOC Analyst, Communications Lead) and reads injects
from the facilitator guide. On Day 3 you get a **different** role from Day 2.

While the exercise runs, keep:
- **Individual response notes**: what you knew at each inject, what you decided, and why.
- **Team decision log**: time, inject number, decision, owner. Write it as you go, not afterwards.

Day 3 ends with a structured debrief (Section 6.3.3): what worked, what didn't, what should change.

**Deliverables:** Day 2 — individual response notes and team decision log. Day 3 — tabletop exercise report with improvement recommendations.

---

## Day 4 — OT Forensics Lab

**Setup:** your instructor gives you `day4_forensics_capture.pcap`, the
"simulated OT attack" generated from Module 4's tooling. Treat it as evidence from the start.

**(host)** Put it in Module 4's capture folder and record its hash **before you open it**:

```bash
cd Module_4-traffic-lab
cp /path/to/day4_forensics_capture.pcap captures/
sha256sum captures/day4_forensics_capture.pcap      # record this in your chain-of-custody log (step 3)
```

### Step 1 — Analyse the capture

The run book asks you to identify the **attack timeline, affected devices, commands sent, and any data exfiltrated**.

**(host)**, from `Module_4-traffic-lab/`:

```bash
./otlab summary captures/day4_forensics_capture.pcap          # what is in the capture: hosts, protocols, time span
./otlab wireshark open captures/day4_forensics_capture.pcap   # opens in the Palanca-OT Wireshark profile
./otlab hunt captures/day4_forensics_capture.pcap -o results/day4_findings.csv
```

> **Always pass `-o results/day4_findings.csv` to `hunt`.** Without it, `hunt`
> writes to `results/day6_findings.csv` and overwrites your Module 4 Day 6 results.

`hunt` is a starting point, not the report. For every event, confirm it in
Wireshark with the filter `hunt` gives you, then record:

| Time (UTC) | Packet no. | Source IP | Target device | What was sent (protocol, function code, port) | Impact | Evidence (filter or screenshot) |
|---|---|---|---|---|---|---|

Things to work out yourself:
- Which source IPs are **not** in the Palanca asset inventory (Module 2)?
- Which events change the PLC (writes, program transfer) and which only read or probe it?
- **Exfiltration:** check whether any data left the network. If you find none, say so and show how you checked (for example large outbound flows, unusual destinations, DNS/HTTP to unknown hosts). "Not found, and here's how I looked" is a valid forensic finding.

### Step 2 — PLC program integrity verification

The run book's commands, run from this kit's folder. Replace `<your name>`
and `MOC-2026-XXXX` with your own values (for example, the MOC reference
from your Day 1 playbook).

**(host)**

```bash
cd Module_6-capstone-kit

# 1. Register the known-good program as the approved baseline
python3 plc_integrity_check.py --register PLC-MAIN-01 plc_main_baseline.st \
  --approved-by "OT Engineer - <your name>" --moc-ref MOC-2026-XXXX

# 2. Check the program "recovered from PLC-MAIN-01" during the incident against it
python3 plc_integrity_check.py --check PLC-MAIN-01 plc_main_current.st
```

Expected: step 1 prints the full SHA-256 of the baseline. Step 2 prints
`** DEVIATION DETECTED on PLC-MAIN-01 **` with the expected and current hashes.

A hash only tells you **that** the program changed, not **what** changed. Find out what changed:

```bash
diff plc_main_baseline.st plc_main_current.st
```

For your report, explain what each change does to the process, why the
modified file would pass a casual review, and which event from Step 1 is the
most likely way it reached the PLC.

> - **Never register `plc_main_current.st`.** Registering overwrites the baseline,
>   and the check would then report `[OK]` against the tampered program.
> - Baselines are saved in `plc_baselines.json` in this folder. To start over, delete that file and register again.
> - Exit codes: `0` = OK, `1` = deviation or no baseline, `2` = file not found. Use them if you script the check.

### Step 3 — Chain of custody

Record every piece of evidence you use (Section 6.4.3): the capture, the two
`.st` files, the `hunt` output and any screenshots.

```bash
sha256sum captures/day4_forensics_capture.pcap results/day4_findings.csv          # from Module_4-traffic-lab/
sha256sum plc_main_baseline.st plc_main_current.st                                # from Module_6-capstone-kit/
```

For each item, log: item, SHA-256, source, who collected it, date/time
collected, where it is stored, and every hand-off. Re-hash at the end of the
day. If a hash has changed, your evidence is no longer intact.

**Deliverable:** forensic investigation report.

### Optional extension — live evidence collection from a device

This goes beyond the run book's Day 4 steps. Use it if your instructor
assigns it, or to practise Section 6.4 acquisition. Steps 1-3 above work on
evidence someone has already collected. `collect_evidence.sh` is how you
collect it from a device that is still running. It works in **order of volatility**,
most volatile first:

| Stage | What it collects | Where it lands |
|---|---|---|
| 1 CPU & processes | CPU state and load, every process with its start time, executable path, executable SHA-256, command line, environment, open files | `cpu/`, `processes/process_table.tsv`, `processes/per_pid/<pid>/` |
| 2 Network state | interfaces, routes, **ARP cache**, every connection mapped to its owning process, firewall rules | `network/connections.tsv`, `network/` |
| 3 Memory | memory statistics; a full RAM image with `--memory` (real devices only) | `memory/` |
| 4 Network traffic | live packet capture with `--pcap SECONDS` | `network/capture.pcap` |
| 5 Storage triage | disks and mounts, files modified in the last 7 days, SUID files, temp-directory executables (hashed), `/etc`, `/var/log`, shell histories, cron | `storage/`, `system/` |
| 6 Storage image | a container's whole filesystem (`docker export`), or a bit-for-bit disk image with `--disk` (real devices only) | `storage/` |

**On the lab**, from the host, against any running container in the Module 2 or Module 3 lab:

```bash
cd Module_6-capstone-kit
./collect_evidence.sh -c IR-2026-D4 -e "<your name>" --container plc-main-01 --pcap 60
```

This takes about 1.5 minutes (most of it is the 60 s capture) and writes
about 135 MB to `evidence/IR-2026-D4_plc-main-01_<UTC time>/`. Container
mode also adds `host_view/`: the container as Docker sees it from outside,
including `docker_diff.txt`, which lists every file added (A), changed (C) or
deleted (D) since the container started from its image. That is often the
fastest way to spot planted files.

Things to look for:
- `processes/process_table.tsv`: an executable path ending in `(deleted)` means a program is running from a file that has been removed. The script warns about this automatically.
- `network/connections.tsv`: connections from unexpected addresses, or an unexpected process holding port 502.
- `network/capture.pcap`: open it in Wireshark with the Palanca-OT profile, as you did in Step 1.
- `storage/temp_dirs_executables_sha256.txt`: executables sitting in `/tmp`, `/var/tmp` or `/dev/shm`.

The collector itself shows up in the process table (a `bash ... collect.sh`
process). That is your own footprint on the device. Note it in your report,
because every live collection changes the system slightly.

**Chain of custody:** the script ends by printing a **manifest SHA-256**.
`manifest.sha256` holds the hash of every collected file, so recording that
one hash in your Step 3 log seals the whole collection. To prove nothing
changed later:

```bash
cd evidence/IR-2026-D4_plc-main-01_<UTC time> && sha256sum -c manifest.sha256
```

**On a real device** (Linux; this is what the script is built for):

```bash
sudo ./collect_evidence.sh -c <case> -e "<your name>" -o /media/usb/evidence \
     --memory --avml /media/usb/avml --pcap 60 [--disk /dev/sdX]
```

- Run it from, and write to, **external media**. The script warns if the output is on the same disk as the system under investigation.
- `--memory` needs [AVML](https://github.com/microsoft/avml) (a single static binary; keep it on the USB) or a LiME module built for that kernel (`--lime path.ko`). The image is as large as the device's RAM.
- `--disk` uses `dc3dd`, `dcfldd` or `dd`, whichever is installed, and records the image's SHA-256. A disk imaged while the system runs keeps changing, so for court-grade evidence power down and image through a hardware write blocker.
- Without root, the script still runs but collects less, and tells you what is missing.
- Evidence written by `sudo` is readable only by root (permissions `700`). That is deliberate.
- It deliberately does **not** copy password hashes (`/etc/shadow`) or SSH private keys.

The script finishes with exit code `0` (complete) or `1` (complete with
warnings, listed in `collection_log.txt`).

---

## Day 5 — Network Hardening, Implementation

You harden the **Module 3 firewall lab**. It is your Module 2 network plus
FW-OT-01 between the zones, the "Module 2/3 firewall extension" option in the
run book. Part A gets the lab into the state Module 3 left it in. Part B is the
run book's steps.

### Part A — Prepare the lab (before step 1)

The Module 2 and Module 3 labs use the **same container names and subnets**,
so only one can run at a time. Tearing down Module 2 **deletes everything
inside eng-ws-01**, so save first.

**(host)**, from the repository root:

```bash
# 1. Save your Module 5 work (your Day 6 "before" data)
mkdir -p Module_5-vuln-lab/my-results
docker cp eng-ws-01:/root/module5/. Module_5-vuln-lab/my-results/
ls Module_5-vuln-lab/my-results/scan_results_*.json         # must list at least one file

# 2. Stop Module 2 (teardown scripts must be run from their own folder)
cd Module_2_Lab_Setup && ./teardown.sh && cd ..

# 3. Start the Module 3 firewall lab
cd Module_3 && ./setup.sh
#    Wait for "Lab is up". The first run builds new images and can take 10-15 minutes
#    (it needs internet access). FW-OT-01 always boots wide open.

# 4. Restore your Module 3 ruleset (your Module 3 deliverable)
docker exec -i fw-ot-01 iptables-restore < my_firewall_rules.txt
docker exec fw-ot-01 iptables -L FORWARD -n --line-numbers  # confirm your rules are back
./scripts/test_firewall_rules.sh                            # should match your Module 3 result
cd ..
```

If you don't have `my_firewall_rules.txt`, rebuild the ruleset by following
`Module_3/LAB_GUIDE.md`, then save it with
`docker exec fw-ot-01 iptables-save > Module_3/my_firewall_rules.txt`.

If you never saved Module 5 results and Module 2 is already gone, start
Module 2 again (`cd Module_2_Lab_Setup && ./setup.sh`), run
`cd ../Module_5-vuln-lab && ./setup.sh`, run `python3 ot_safe_scanner.py`
inside eng-ws-01 (`cd /root/module5` first), copy the result out as in step 1,
then continue from step 2.

### Step 1 — Run `verify_hardening.sh` before changing anything

**(host)**

```bash
cd Module_6-capstone-kit
./verify_hardening.sh
```

Expect FAILs. That is the baseline you record. Each run is saved to
`logs/verify_hardening_<date>_<time>.txt`. Keep this first log as your
"before" evidence. With your Module 3 ruleset restored, the typical baseline is:

| Check | Typical baseline | Why |
|---|---|---|
| 1 Flat network | PASS | Module 3 already removed the dual-homing (Module 2 Day 5's finding) |
| 2 Default credentials | **FAIL** | SW-CORE-01 still accepts `admin / palanca-lab` |
| 3 Control Zone ports | PASS | Your R01-R04 + R99 only let Modbus through (FAIL means the firewall is still wide open) |
| 4 Default-deny | PASS | R99 |
| 5 Modbus function codes | **FAIL** | R01 allows port 502, not specific function codes |

If the script prints `ERROR: lab container(s) not running`, Part A didn't
finish. Check `docker ps` and re-run `Module_3/setup.sh`.

### Step 2 — Work through `hardening_checklist.md`

Copy the checklist into your report and attach evidence to every item.
How to do each item in this lab:

All firewall commands run inside FW-OT-01: `docker exec -it fw-ot-01 bash`.
**After every firewall change, save your ruleset from the host:**

```bash
mkdir -p my-results
docker exec fw-ot-01 iptables-save > my-results/day5_fw_rules.txt     # from Module_6-capstone-kit/
```

**6.5.2 Firewall rule optimisation**
- List your rules: `iptables -S FORWARD` and `iptables -L FORWARD -n -v --line-numbers` (the packet counters show which rules actually get used).
- Look for rules broader than needed. Example: R01 lets the **whole** Supervisory /24 talk Modbus to the **whole** Control /24, but only SCADA-HMI-01/02 (`192.168.2.10`, `.11`) and ENG-WS-01 (`192.168.2.20`) are Modbus masters. Replace the broad rule with a narrow one at the same position. Find its line number, delete it, then insert the narrow version there:
  ```bash
  iptables -D FORWARD <line>
  iptables -I FORWARD <line> -s 192.168.2.10,192.168.2.11,192.168.2.20 -d 192.168.1.0/24 \
    -p tcp --dport 502 -m conntrack --ctstate NEW -j ACCEPT
  ```
  `-s` with a comma list expands into one rule per address. That's why this uses delete-and-insert: `iptables -R` refuses more than one address. Run `iptables -S FORWARD` afterwards and re-check the order.
- Justification: build a table with one row per remaining rule: rule ID (R01…), iptables rule, business justification, owner. Optionally tag rules in place: `-m comment --comment "R01 HMI/ENG-WS Modbus polling"`.

**6.5.3 VLAN restructuring / microsegmentation**
- Check 1 of `verify_hardening.sh` covers the conduit. Also confirm by hand from eng-ws-01: `ip -4 addr` shows **no** `192.168.1.x` address, and `ip route` shows Control reached only via `192.168.2.5` (FW-OT-01).
- VLAN split: Docker bridge networks can't do 802.1Q, so this item is a **design** deliverable. Propose which devices move into smaller VLANs (for example, separate the protection relays PROT-REL-01/02 from the PLCs and VFD by criticality), with subnets and the firewall rules each new conduit would need.

**6.5.4 Secure remote access**
- The lab has no VPN endpoint. This item is evidenced in writing: how R10 (remote engineering, "MFA required") would be enforced (VPN concentrator plus MFA provider, jump host in the DMZ) and how sessions would be logged or recorded (jump-host session recording, retention period, who reviews).

**6.5.5 Endpoint hardening**
- Inventory listening services (host):
  ```bash
  docker exec scada-hmi-01 ss -tlnp
  docker exec scada-hmi-02 ss -tlnp
  docker exec eng-ws-01 ss -tlnp
  ```
  Ignore the `127.0.0.11` line. That is Docker's internal DNS resolver, present in every container. For each other port, decide whether the device's role needs it. The HMI simulator runs OPC-UA (4840), an HTTP status page (80) and an HTTPS listener (443, the target of rule R06) in one process, and none of them can be switched off without rebuilding the image. Where a service can't be disabled, record the compensating control (which firewall rule stops other zones reaching it) and record what is **still** reachable from the same subnet as a gap for Day 6.
- Change the default credential on SW-CORE-01 (host). Pick a new password using **letters, digits and hyphens only**:
  ```bash
  NEWPASS='Choose-Your-Own-Passphrase'
  docker exec sw-core-01 sed -i "s/^PASSWORD = .*/PASSWORD = \"$NEWPASS\"/" /app/switch_ssh_sim.py
  docker restart sw-core-01
  ```
  Confirm from eng-ws-01 that `ssh admin@sw-core-01` refuses `palanca-lab` and accepts your new password. Keep the new password in your notes. **Do not** put it in your report. Write "changed on <date>, stored in <where>" instead. A `docker restart` keeps the change. Tearing down the lab or recreating the container brings the default back.

**6.5.6 Protocol whitelisting (Modbus function codes)**
- iptables can match the Modbus function code with `u32`. The function code is byte 7 of the TCP payload. This expression matches the **write** codes FC 5, 6, 15 and 16:
  ```
  -m u32 --u32 '0>>22&0x3C@12>>26&0x3C@4&0xFF=0x5:0x6,0xF:0x10'
  ```
  Worked example: drop Modbus writes to Control from everyone except SCADA-HMI-01:
  ```bash
  iptables -I FORWARD 1 -d 192.168.1.0/24 -p tcp --dport 502 ! -s 192.168.2.10 \
    -m u32 --u32 '0>>22&0x3C@12>>26&0x3C@4&0xFF=0x5:0x6,0xF:0x10' -j DROP
  ```
  **It must be inserted at position 1** (`-I FORWARD 1`), above the `ESTABLISHED,RELATED` accept rule. A Modbus request travels inside an already-established connection, so placed below that rule it would never be evaluated.
- Your policy decides who may write, and which function codes are allowed at all. Should ENG-WS-01 write outside an approved MOC window? Should diagnostics (FC 8) or device identification (FC 0x2B) be allowed? Justify each decision.
- Test it from eng-ws-01. A read should still work, and a write should time out if your policy blocks ENG-WS-01:
  ```bash
  python3 /root/palanca_modbus_read.py 192.168.1.10 5  # read: should still print register values
  python3 -c "from pymodbus.client import ModbusTcpClient as C; c=C('192.168.1.10', timeout=3, retries=0); c.connect(); print(c.write_register(5, 1234, slave=1)); c.close()"
  # blocked write -> "Modbus Error: ... No response received"
  ```

### Step 3 — Re-run `verify_hardening.sh` after each major change

```bash
./verify_hardening.sh
```

Work until it reports `Results: 5 passed, 0 failed`. Keep the first
(before) and last (after) logs from `logs/` for your deliverable. Also
re-run `../Module_3/scripts/test_firewall_rules.sh` to prove you didn't break
the flows R01-R12 are supposed to allow.

**Deliverable:** hardened network configuration documentation: the
completed checklist with evidence for each item, `my-results/day5_fw_rules.txt`,
and the before and after `verify_hardening` logs.

---

## Day 6 — Security Posture Assessment

### Step 1 — Re-run OTSafeScanner against the hardened lab

eng-ws-01 is a new container in the Module 3 lab, so set Module 5 up in it again.

**(host)**, from the repository root:

```bash
cd Module_5-vuln-lab && ./setup.sh && cd ..
# If you edited the scanner in Module 5 (e.g. EXCLUDED_IPS), put YOUR version back
# so the before and after scans use the same settings:
docker cp Module_5-vuln-lab/my-results/ot_safe_scanner.py eng-ws-01:/root/module5/
```

**(eng-ws-01)**

```bash
cd /root/module5
python3 ot_safe_scanner.py              # ~15 min, writes scan_results_<timestamp>.json
```

This takes far longer than in Module 5 (about 4 min). Discovery now crosses FW-OT-01, so nmap can't use ARP. It sends
paced probes to all 254 addresses and waits out a timeout on every address that doesn't exist. Start it, then work on your
Day 5 write-up. Discovery also lists `192.168.1.5` (FW-OT-01's Control interface) and `192.168.1.254` (your host's
Docker gateway). Both are expected.

If it prints **"No hosts discovered"**, your firewall is dropping the
discovery probes. That is a hardening result, so record it. To still measure
port exposure, scan the known Control Zone addresses directly:

```bash
python3 -c "
from ot_safe_scanner import OTSafeScanner
s = OTSafeScanner()
s.port_scan(['192.168.1.1','192.168.1.10','192.168.1.11','192.168.1.20','192.168.1.21','192.168.1.30','192.168.1.31','192.168.1.40'])
s.save_results()"
```

NSE-discoverable information, the same single-device check you used in Module 5. Use a device that is **not** in your
scanner's `EXCLUDED_IPS`. Running nmap by hand doesn't apply that exclusion for you:

```bash
nmap -Pn -sT -T2 --max-rate 5 -p 502 --script modbus-discover 192.168.1.20
```

Whether this still returns `Device identification:` depends on which function
codes your Day 5 filter allows. Either result is evidence. Explain it.

**(host)** Copy the results out:

```bash
mkdir -p Module_6-capstone-kit/my-results/day6
docker cp eng-ws-01:/root/module5/. Module_6-capstone-kit/my-results/day6/
```

### Step 2 — Compare against your original Module 5 scan

**(host)**, from `Module_6-capstone-kit/`:

```bash
ls ../Module_5-vuln-lab/my-results/scan_results_*.json      # pick the scan from your Module 5 lab
ls my-results/day6/scan_results_*.json                       # today's scan
python3 compare_scans.py ../Module_5-vuln-lab/my-results/scan_results_<before>.json \
                         my-results/day6/scan_results_<after>.json \
                         --csv my-results/day6_port_comparison.csv
```

You get open-service counts before and after, the percentage reduction, and
three lists: **no longer reachable**, **still reachable** (justify each one or
list it as a gap), and **new** (investigate these).

Note: Module 5 scanned from **inside** the Control segment (eng-ws-01 was
dual-homed). Today's scan crosses FW-OT-01. Part of the reduction comes from
that architecture change, so say so in your report.

### Step 3 — Gaps hardening did not close

Use the "still reachable" list, the `modbus-discover` result and your Day 5
compensating-control notes. For each gap, record: risk, why it's still open,
the planned fix, owner and target date.

Build the **before/after compliance scorecard**: one row per
`hardening_checklist.md` item, with status before (from your first
`verify_hardening` log), status after (last log), and evidence.

**Deliverable:** post-hardening assessment report with a before/after compliance scorecard.

---

## Day 7 — Assessment Day

Submit all lab deliverables:

- [ ] 3 IR playbooks (Day 1)
- [ ] 2 tabletop reports (Days 2-3)
- [ ] Forensic investigation report with chain-of-custody log (Day 4)
- [ ] Hardening documentation: checklist with evidence, `day5_fw_rules.txt`, before and after `verify_hardening` logs (Day 5)
- [ ] Posture assessment report with before/after scorecard (Day 6)

You'll also present tabletop lessons learned, demonstrate a forensic technique
live (for example the Day 4 integrity check plus `diff`, or a Wireshark filter
that isolates one attack), and sit the 90-minute Knowledge Check.

Practise your live demo beforehand. The integrity check needs no lab
containers, and Wireshark needs only the capture file.

When the course is finished: `cd Module_3 && ./teardown.sh`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Module_3/setup.sh` fails with `Conflict. The container name "/plc-main-01" is already in use` | Module 2 lab is still running | `cd Module_2_Lab_Setup && ./teardown.sh`, then re-run `Module_3/setup.sh` |
| `teardown.sh: no configuration file provided` | Teardown was run from another folder | `cd` into that module's folder first |
| `verify_hardening.sh` exits with `ERROR: lab container(s) not running` | Lab is down | `cd Module_3 && ./setup.sh` |
| `permission denied ... docker.sock` | Your user isn't in the docker group | `sudo usermod -aG docker $USER`, then log out and back in |
| Your firewall rules are gone | FW-OT-01 was restarted or recreated. It always boots wide open | `docker exec -i fw-ot-01 iptables-restore < my-results/day5_fw_rules.txt` (from `Module_6-capstone-kit/`) |
| eng-ws-01 suddenly gets "no route" to `192.168.1.x` | A container was restarted and lost its route via FW-OT-01 | Re-run `Module_3/setup.sh` (safe to repeat), then restore your rules if FW-OT-01 was restarted too |
| A Modbus function-code rule has no effect | The rule is below the `ESTABLISHED,RELATED` accept rule | Delete it and insert it with `-I FORWARD 1` |
| `ModuleNotFoundError: No module named 'nmap'` in eng-ws-01 | eng-ws-01 was recreated | `cd Module_5-vuln-lab && ./setup.sh` |
| `plc_integrity_check.py --check` says `[OK]` for `plc_main_current.st` | You registered the wrong file as the baseline | Delete `plc_baselines.json` and register `plc_main_baseline.st` again |
| `otlab: captures/... not found` | Capture not copied into Module 4's `captures/` folder | Copy the instructor's file there (Day 4 setup) |

**Option C (VirtualBox) build:** `verify_hardening.sh` needs the Docker lab.
On the VirtualBox build, do the same five checks by hand: no HMI or
engineering-workstation interface on the Control subnet; switch login with the
default password fails; scan the Control Zone from the engineering
workstation; check the pfSense ruleset for default-deny; check for Modbus
function-code filtering. Attach screenshots as evidence.
