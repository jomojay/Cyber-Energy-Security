# Module 6 — Capstone Lab Kit

Module 6 is the course's capstone: it does not introduce new
infrastructure. Every lab day reuses an environment or tool built in
a previous module. This kit provides only what's genuinely new for
Module 6: a PLC integrity checker with sample program files, a
hardening checklist and verification script, and a scan-comparison
helper for the posture assessment.

- **Instructors / facilitators:** `Module_6_Lab_Run_Book.docx` (this folder) is the authoritative step list. This README covers setup.
- **Trainees:** follow [`TRAINEE_GUIDE.md`](TRAINEE_GUIDE.md). It walks through each run book step with the exact commands for this lab, and uses the run book's day and step numbers.

## What reuses previous modules

| Lab Day | Reuses |
|---------|--------|
| Day 1 (IR Playbooks) | No infrastructure — written exercise |
| Day 2-3 (Tabletop) | No infrastructure — facilitator-led, using `Module_6_Tabletop_Facilitator_Guide.docx` (instructor material, not in this repository) |
| Day 4 (Forensics) | Module 4's `attack_pcap_generator.py` — regenerate an attack-challenge capture and treat it as "the simulated OT attack" for forensic analysis. Use `plc_integrity_check.py` (this kit) for the PLC verification step. |
| Day 5 (Hardening) | Module 2's Docker lab + Module 3's firewall extension (the `Module_3/` lab is both: Module 2's topology plus FW-OT-01), or Option C VirtualBox — apply `hardening_checklist.md` (this kit) to it |
| Day 6 (Posture Assessment) | Module 5's `ot_safe_scanner.py` — re-run it against the now-hardened network and compare to the Module 5 lab's original scan results |

## Files in this kit

| File | Day | Purpose |
|------|-----|---------|
| `Module_6_Lab_Run_Book.docx` | All | Step-by-step run book (instructor and trainee) |
| `TRAINEE_GUIDE.md` | All | Trainee walkthrough of the run book with exact commands |
| `collect_evidence.sh` | 4 | Live evidence collection in order of volatility (CPU and processes → network state → RAM → traffic → storage), with a SHA-256 manifest for chain of custody. Runs on a real Linux device or against any lab container (`--container NAME`) |
| `plc_integrity_check.py` | 4 | Baseline-registration and integrity-check tool (Module 6, Section 6.4 / Module 3, Section 3.6.4 concept, made runnable) |
| `plc_main_baseline.st` | 4 | Sample PLC-MAIN-01 program: the approved baseline the run book registers |
| `plc_main_current.st` | 4 | Sample program "recovered" from PLC-MAIN-01 during the incident, the deliberately modified copy the run book checks |
| `hardening_checklist.md` | 5 | The Section 6.5 SL-2 hardening checklist as an actual checklist |
| `verify_hardening.sh` | 5-6 | Automates five of the checklist's checks against the Docker lab and saves each run to `logs/` |
| `compare_scans.py` | 6 | Before/after comparison of two `ot_safe_scanner.py` result files, for the Day 6 scorecard |

Python 3.8+ only, no extra libraries. `plc_baselines.json`, `logs/` and
`my-results/` and `evidence/` are created as trainees work and are git-ignored.

## Day 4 setup (instructor, before the session)

The capture is built from Module 4's 24-hour baseline, which only exists
after Module 4's `./setup.sh` has run (`captures/` is git-ignored).

```bash
cd ../Module_4-traffic-lab
[ -f captures/palanca_baseline_24h.pcap ] || ./setup.sh     # < 1 min, no sudo
python3 attack_pcap_generator.py captures/palanca_baseline_24h.pcap \
  -o captures/day4_forensics_capture.pcap \
  --answer-key captures/instructor-only/day4_answer_key.csv
```

Trainees analyse `day4_forensics_capture.pcap` (about 125 MB; hand it out
on a USB drive or share). The instructor keeps `day4_answer_key.csv`.
Writing the key into `captures/instructor-only/` keeps it out of git and
out of trainee copies, because Module 4's `./setup.sh --no-keys` removes
that folder. Every run plants the same five attack types at new times and
from new attacker IPs. Add `--seed <n>` to reproduce a capture exactly.

## Day 5-6 setup

The hardening target is the Module 3 firewall lab. It is Module 2's
topology with the flat network already removed and FW-OT-01 placed between
the zones. The Module 2 and Module 3 labs use the same container names and
subnets, so **only one can run at a time**:

```bash
# Save Module 5 work first: tearing down Module 2 deletes eng-ws-01's files
mkdir -p ../Module_5-vuln-lab/my-results
docker cp eng-ws-01:/root/module5/. ../Module_5-vuln-lab/my-results/

cd ../Module_2_Lab_Setup && ./teardown.sh        # teardown scripts must be run from their own folder
cd ../Module_3 && ./setup.sh
docker exec -i fw-ot-01 iptables-restore < my_firewall_rules.txt   # trainee's Module 3 ruleset, if saved

cd ../Module_6-capstone-kit
./verify_hardening.sh          # before hardening (expect FAILs)
# ... apply hardening_checklist.md items ...
./verify_hardening.sh          # after hardening (expect PASSes)

# Day 6: re-run Module 5's scanner and compare
cd ../Module_5-vuln-lab && ./setup.sh             # reinstalls python-nmap into the new eng-ws-01
docker exec -it eng-ws-01 bash -c "cd /root/module5 && python3 ot_safe_scanner.py"
```

`TRAINEE_GUIDE.md` has the full sequence, including the comparison step.

### What `verify_hardening.sh` checks

| # | Check | Checklist item | Module 2 lab | Module 3 lab, Module 3 ruleset restored | Fully hardened |
|---|-------|----------------|--------------|-------------------------------|----------------|
| 1 | No Supervisory/DMZ host is dual-homed on Control | 6.5.3 | FAIL | PASS | PASS |
| 2 | SW-CORE-01 rejects the default `palanca-lab` password | 6.5.5 | FAIL | FAIL | PASS |
| 3 | Only conduit ports (502, 4840) reachable on Control from eng-ws-01 | 6.5.2 / 6.5.6 | FAIL | PASS (FAIL if FW-OT-01 is still wide open) | PASS |
| 4 | FW-OT-01 ends in default-deny | 6.5.2 | SKIP | PASS (FAIL if wide open) | PASS |
| 5 | FW-OT-01 matches Modbus by function code, not just port 502 | 6.5.6 | SKIP | FAIL | PASS |

The script refuses to run (exit code 2) if the lab containers aren't up,
so it can't report a false PASS against a stopped lab. Exit code 0 means
every check passed and 1 means at least one FAIL. The remaining
checklist items (MFA, session logging, VLAN split, rule justification)
are design and documentation items that trainees evidence in writing.
