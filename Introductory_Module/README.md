# OCEON Module 0 — Introduction to Energy Cyber Security

Trainee guide for this module. Case study: Evolve Power's Palanca SCADA plant.

For anything not covered here (system requirements, Kali vs. Ubuntu notes, general troubleshooting), see the [repository-level README](../README.md).

---

## 1. Run the setup script

```bash
sudo bash oceon_m0_lab_setup.sh
```

- Run it **with `sudo bash`, as your normal user** — not logged in as root, and not after `sudo su`. The script uses `$SUDO_USER` to give you (not root) ownership of the lab files it creates.
- It's **idempotent** — if a step fails (usually a network hiccup), just re-run the same command. Completed steps are skipped.
- Takes 5–15 minutes depending on your connection. GNS3 and OpenPLC are the slow parts.

When it finishes, it prints a **post-install checklist** — read it, it tells you exactly what to do next (log out/in, install OpenPLC, load the PLC program, start ScadaBR). The steps below assume you've completed that checklist.

---

## 2. What you get

Everything lands in `~/oceon-lab/`:

```
~/oceon-lab/
├── venv/                       ← Python virtual environment (pymodbus, rich)
├── OpenPLC_v3/                 ← cloned source, installed manually (see checklist)
├── evolve-power-programs/
│   └── palanca_motor_feeder.st ← PLC program you load into OpenPLC
├── diagrams/
│   └── OCEON-M0-PURDUE-TEMPLATE.drawio  ← Lab 2 worksheet
└── palanca_poll.py             ← Modbus polling helper (Lab 1)
```

A Wireshark colour profile (**Evolve-Power**) and a ScadaBR desktop shortcut are also installed.

| Service | Port |
|---|---|
| OpenPLC Web UI | 8080 (`openplc` / `openplc`) |
| OpenPLC REST API | 8443 |
| Modbus/TCP (OpenPLC) | 502 |
| ScadaBR HMI | 9090 (`admin` / `admin`) |

---

## 3. Running the labs

### Lab 1 — Modbus/TCP capture (45 min)

Generate live Modbus traffic and capture it with Wireshark.

**Terminal 1 — generate traffic:**
```bash
cd ~/oceon-lab && venv/bin/python3 palanca_poll.py --continuous
```

**Terminal 2 — capture:**
```bash
sudo wireshark -i lo -k -Y "tcp.port == 502"
```
Apply the lab colour profile: *Edit → Configuration Profiles → Evolve-Power*.
(If colours look wrong under a dark GTK theme: `GTK_THEME=Adwaita:light sudo -E wireshark ...`)

**Bonus — service fingerprint:**
```bash
sudo nmap -sV -p 502,8080,8443,9090 127.0.0.1 -oN ~/oceon-lab/lab1_scan.txt
```

Read `palanca_poll.py` before you run it — every register it polls is clear-text, unauthenticated Modbus, which is the point of the exercise (see the panel it prints).

### Lab 2 — Purdue model mapping (60 min)

```bash
drawio ~/oceon-lab/diagrams/OCEON-M0-PURDUE-TEMPLATE.drawio
```
Place each Evolve Power component (transformers/motors, PLCs, HMI/historian, OPC-UA aggregation server, jump host/VPN, ERP/Power BI) at its correct Purdue level, draw trust boundaries in red between levels, annotate each boundary with at least two security controls, and export as PNG. The checklist box in the diagram tells you what to submit.

### Lab 3 — ATT&CK for ICS mapping (90 min, browser only)

No script for this one — work directly from https://attack.mitre.org/matrices/ics/ and map Stuxnet, Colonial Pipeline, and TRITON to technique IDs.

---

## Troubleshooting

Module-specific quick hits — for anything else, see the [repository-level Troubleshooting section](../README.md#troubleshooting).

**"SUDO_USER is not set"** — you ran `sudo su` first, or ran the script with plain `bash`. Exit back to your normal user session and run `sudo bash oceon_m0_lab_setup.sh` directly.

**Wireshark can't capture on `lo`** — log out and back in so the `wireshark` group membership takes effect, or run `newgrp wireshark` in your current terminal.

**ScadaBR won't start** — `sudo /opt/ScadaBR/tomcat/bin/startup.sh`, wait ~15s, then open http://localhost:9090/ScadaBR. Check `ss -tlnp | grep 9090` if it still doesn't respond.

**GNS3 missing after setup** — the GNS3 PPA is Ubuntu-only and doesn't always publish for the newest release; the script warns and continues without blocking the rest of your environment. Install it manually per the link the script prints, whenever you get to the GNS3-based topology labs.

**OpenPLC install fails with a CMake error** (`Compatibility with CMake < 3.5 has been removed`, ending in `Error installing OpenDNP3` / `OpenPLC was NOT installed!`) — OpenPLC bundles an old OpenDNP3 build that current CMake (4.x, shipped by Kali rolling and eventually newer Ubuntu) refuses to configure. The post-install checklist's Step 2 command already includes the fix (`sudo env CMAKE_POLICY_VERSION_MINIMUM=3.5 bash install.sh linux`) — if you typed `sudo bash install.sh linux` without that, re-run with the full command instead of trying to repair the partial install.
