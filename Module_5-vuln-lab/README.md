# Module 5 — Vulnerability Assessment Lab

Companion package for the 7-day Module 5 lab (**Module_5_Lab_Run_Book.docx**, in this folder).

## Infrastructure note

This module does **not** stand up new lab infrastructure. It reuses the
**Module 2 Palanca lab** (Docker `palanca-lab`, or the Option C VirtualBox
build) as the scan target, and adds:

1. **`ot_safe_scanner.py`**: the `OTSafeScanner` class from Module 5,
   Section 5.3.1, ready to extend across Lab Days 3-4.
2. **`cve_reference_dataset.json`** + **`cve_correlator.py`**: an
   offline CVE lookup, so Lab Day 4's CVE correlation exercise works
   without live internet access in the training room, while mirroring
   what a real NVD query returns.

As in Module 2, **your working point for every lab day is the `eng-ws-01`
container**. `setup.sh` installs `python-nmap` there and copies these files
to `/root/module5`; nothing is installed on your host.

## Quick start

```bash
# 1. Start the Module 2 lab (skip if it's already running)
cd ../Module_2_Lab_Setup && ./setup.sh && cd -

# 2. Set up Module 5 inside eng-ws-01 (no sudo; needs internet for pip)
./setup.sh

# 3. Work from eng-ws-01
docker exec -it eng-ws-01 bash
cd /root/module5
```

`setup.sh` is idempotent. It **won't overwrite** files already in
`eng-ws-01:/root/module5`, so re-running it can't wipe your Day 3 scanner
edits. Use `./setup.sh --force` to reset them to the originals.

**VirtualBox (Option C) build / no Docker lab running:** `setup.sh` falls
back to creating a `.venv` in this folder (Kali and Ubuntu 24.04 block
system-wide `pip install`). Run `source .venv/bin/activate` first, and
make sure host `nmap` is installed and the lab VMs are reachable.

## Files

| File | Used In | Purpose |
|------|---------|---------|
| `Module_5_Lab_Run_Book.docx` | All days | Step-by-step trainee/instructor run book |
| `setup.sh` | Before Day 1 | Installs `python-nmap` + copies the files below into `eng-ws-01:/root/module5` |
| `ot_safe_scanner.py` | Day 3-4 | Starter code for the OTSafeScanner class. Extend it with CVE correlation on Day 4 |
| `cve_reference_dataset.json` | Day 4 | Offline vendor->CVE lookup table matching the Palanca lab's device vendors |
| `cve_correlator.py` | Day 4 | Reference implementation that queries the dataset and applies the Section 5.4.2 OT-CVSS adjustment |

## Day-by-day: what to run (verified against the Docker lab)

Run everything from inside `eng-ws-01` (`docker exec -it eng-ws-01 bash`).
`eng-ws-01` sits on the control (`192.168.1.0/24`) and supervisory
(`192.168.2.0/24`) networks. It **cannot** reach the DMZ address `192.168.3.10`.

### Day 1 — Nmap fundamentals

Practise on **historian-01 at `192.168.2.30`**, a non-OT target with a real
open port (80/tcp):

```bash
nmap -sT 192.168.2.30
nmap -sS 192.168.2.30                     # works: you are root in eng-ws-01
nmap -sV 192.168.2.30                     # identifies SimpleHTTPServer / Python
nmap -sT -oX scan.xml 192.168.2.30
nmap -sT -oG scan.grepable 192.168.2.30
```

> Don't use `192.168.2.20`, which the run book shows. That's eng-ws-01
> itself: every port is closed, so there's nothing to compare between scan types.

### Day 2 — OT-safe scanning

| Command | Expected result | Runtime |
|---|---|---|
| `nmap -sn -T2 --max-rate 10 192.168.1.0/24` | 13 hosts up (see table below) | ~3 min |
| `nmap -sT -T2 --max-rate 10 -p 22,80,102,443,502,4840 192.168.1.10-40` | 7 devices, 502/tcp open on each | ~25 s |
| `nmap -sT -T1 --max-rate 5 -p 502 --script modbus-discover 192.168.1.10-40` | `Device identification:` line per device | **~11 min** |

`-T1` is deliberately slow. Start the `modbus-discover` sweep and keep
working while it runs. To see its output first on a single device:
`nmap -Pn -sT -T2 --max-rate 5 -p 502 --script modbus-discover 192.168.1.10` (~10 s).

`s7-info` returns nothing in this lab: the simulators only speak Modbus/TCP,
and none listens on 102/tcp. That's an expected (and realistic) finding:
the vendor *label* says Siemens, but the protocol fingerprint doesn't match.

**Expected inventory on `192.168.1.0/24`:**

| IP | Device | Open (OT-safe port list) | `modbus-discover` identification |
|---|---|---|---|
| .1 | sw-core-01 | 22 | — |
| .10 / .11 | plc-main-01 / plc-aux-01 | 502 | `Siemens S7-1200 PLC-MAIN-01 1.0` / `…PLC-AUX-01…` |
| .20 / .21 | gen1-rtu / gen2-rtu | 502 | `GE Automation GEN1-RTU 1.0` / `…GEN2-RTU…` |
| .30 / .31 | prot-rel-01 / prot-rel-02 | 502 | `ABB REL670 PROT-REL-01 1.0` / `…PROT-REL-02…` |
| .40 | vfd-pump-01 | 502 | `ABB ACS580 VFD-PUMP-01 1.0` |
| .110 / .111 | scada-hmi-01 / -02 (dual-homed) | 80, 4840 | — |
| .120 | eng-ws-01 (you) | — | — |
| .200 | traffic-gen | — | — |
| .254 | your host (Docker gateway) | — | — |

### Day 3 — Python scanner

```bash
python3 ot_safe_scanner.py        # discovery on 192.168.1.0/24 + port scan, ~3.5 min
                                  # writes scan_results_<timestamp>.json
```

Start by reviewing `EXCLUDED_IPS` (see the safety note below). For the
safety-violation test, `validate_targets(["192.168.1.50"])` must raise
`ValueError`.

The scanner also passes `EXCLUDED_IPS` to nmap as `--exclude` on every scan.
That's a safety net beyond the Section 5.3.1 code: `validate_targets()` only
catches exact IP matches, so a target like `192.168.1.0/24` or
`192.168.1.10-60` would otherwise sweep straight over an excluded device.
Ask trainees why the textbook check alone isn't enough. It's a good discussion point.

### Day 4 — CVE correlation

Pass the `Device identification:` string from `modbus-discover`, or just
the vendor/model:

```bash
python3 cve_correlator.py "Siemens S7-1200 PLC-MAIN-01 1.0"
python3 cve_correlator.py "ABB REL670"
python3 cve_correlator.py "ABB"          # partial match returns both ABB products
```

All seven Modbus devices, plus `Cisco Cat 2960X` (sw-core-01), have
entries. CVE IDs end in `-SIM`: they're illustrative teaching entries, not
real CVEs. The live NVD comparison step (nvd.nist.gov) needs internet
access from the host browser, not from `eng-ws-01`.

### Days 5-7

These are analysis and report-writing days with no extra tooling. On Day 7, the
live scanner demo uses the same `python3 ot_safe_scanner.py` run as Day 3.

## Saving your work

Everything in `eng-ws-01:/root/module5` (edited scanner, `scan.xml`,
`scan_results_*.json`) is **deleted when the Module 2 lab is torn down or
the container is recreated**. Copy it to your host before then:

```bash
docker cp eng-ws-01:/root/module5/. ./my-results/
```

After recreating the lab, re-run `./setup.sh` to reinstall `python-nmap`.

## Important safety note: `EXCLUDED_IPS`

`ot_safe_scanner.py`'s `EXCLUDED_IPS` list uses the placeholder addresses
from the module text (`192.168.1.50/.51`). **Nothing in the Docker lab uses
those addresses.** No host answers there, and the lab simulates no SIS
devices. So the placeholders exclude nothing real, and every lab device
gets scanned.

Treat this as a live exercise in verifying a safety-critical exclusion list
against the real asset inventory (the Module 2 device map) before scanning.
Don't treat it as a bug to silently work around. Trainees should decide
which, if any, devices to add, and justify that choice in their Day 3
deliverable. For example, an instructor might designate the protection
relays `.30/.31` as "safety-related, do not scan" to make the exclusion
observable.

## Run Book errata (Module_5_Lab_Run_Book.docx)

When the run book and this README disagree, follow this README. Each change
below was checked against the running lab:

| Run Book says | Use instead | Why |
|---|---|---|
| "Run `./setup.sh` … to install python-nmap" | `./setup.sh` with the Module 2 lab **already running**, then work in `eng-ws-01:/root/module5` | Setup installs into eng-ws-01; host `pip install` fails on Kali/Ubuntu 24.04 (PEP 668) |
| Day 1 target `192.168.2.20` | `192.168.2.30` (historian-01) | .20 is eng-ws-01 itself, with every port closed |
| Day 1 "eng-ws-01 or historian-01" | historian-01 at `192.168.2.30` | historian's `192.168.3.10` address isn't reachable from eng-ws-01 |
| Day 2 `modbus-discover` (no time given) | Allow ~11 min | `-T1` across 31 addresses |
| Day 2 "(where applicable) s7-info" | Expect no output | No simulator listens on 102/tcp |

## Troubleshooting

- **`setup.sh` says eng-ws-01 isn't running and falls back to a venv** but
  you're using Docker: start Module 2 first (`cd ../Module_2_Lab_Setup && ./setup.sh`),
  then re-run `./setup.sh` here.
- **`ModuleNotFoundError: No module named 'nmap'` inside eng-ws-01**: the
  container was recreated. Re-run `./setup.sh`.
- **An extra host shows up at `192.168.1.254`**: that's your own machine (the
  Docker gateway). See the Module 2 README's troubleshooting section.
- **`pip install` fails during `setup.sh`**: eng-ws-01 needs internet
  access to PyPI during setup, but not during the lab itself.
