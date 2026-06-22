# OCEON Cyber-Energy Security — Lab Repository

This repository contains lab setup scripts and instructions for the OCEON Cyber-Energy Security (CES) course. Each module folder holds everything you need for that module's labs: a setup script that builds your local environment and any supporting files referenced by the lab exercises.

---

## Repository Layout

```
Cyber-Energy-Security/
├── README.md                        ← you are here
├── Introductory_Module/
│   └── oceon_m0_lab_setup.sh        ← Module 0 environment setup
├── Module_01/
│   ├── setup_lab_env.sh             ← Module 1 environment setup
│   ├── palanca_modbus_read.py       ← Lab 3 trainee template (Modbus/TCP)
│   ├── palanca_modbus_monitor.py    ← Lab 3 extension (anomaly thresholds)
│   ├── palanca_opcua_server.py      ← Lab 4 OPC-UA server simulator
│   ├── palanca_opcua_browse.py      ← Lab 4 OPC-UA client / explorer
│   ├── generate_baseline_pcap.py    ← Lab 5 baseline traffic generator
│   ├── palanca_gen_start.st         ← PLC Structured Text program
│   ├── palanca_asset_inventory.csv  ← Lab worksheet (Purdue level mapping)
│   └── palanca_topology_base.xml    ← draw.io topology starter file
└── <ModuleName>/                    ← future modules follow the same pattern
    └── setup_lab_env.sh
```

Each module directory is self-contained. Navigate to your module folder and run its setup script before attempting the labs.

---

## System Requirements

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 24.04 LTS (Noble Numbat) x86_64 |
| RAM | 8 GB (16 GB recommended for GNS3 topologies) |
| Disk | 20 GB free |
| Network | Internet access during setup (GitHub, Ubuntu PPAs) |

> **Virtual machine users:** Set your network adapter to **NAT** mode in VirtualBox/VMware before running the setup script. Bridged mode can block the package downloads the script needs.

---

## Getting Started

**1. Clone the repository**

```bash
git clone https://github.com/<org>/Cyber-Energy-Security.git
cd Cyber-Energy-Security
```

**2. Navigate to your module folder**

```bash
cd Introductory_Module   # or whichever module you are working on
```

**3. Run the setup script**

Each module has its own setup script inside its folder. Check the script name for your module:

| Module | Script |
|---|---|
| Introductory_Module | `oceon_m0_lab_setup.sh` |
| Module_01 | `setup_lab_env.sh` |

```bash
sudo bash <script_name>
```

> **Important:** Use `sudo bash <script>` from your normal user account. Do **not** log in as root or use `sudo su` before running the script — the script uses `$SUDO_USER` to set file ownership correctly, and that variable is empty when you become root before running.

The scripts are **idempotent**: safe to re-run if a step fails or you need to repair your environment.

**4. Follow the post-install steps printed at the end of the script**

The script prints a checklist of manual steps (log out/in for group changes, one-time installs that require interactive prompts, browser configuration, etc.). Complete them in order before starting the labs.

---

## Tools Installed by the Lab Scripts

The setup scripts install only the tools needed for their respective module. Across the course you will work with:

| Tool | Purpose |
|---|---|
| **Wireshark / tshark** | Protocol capture and analysis (Modbus/TCP, OPC-UA, DNP3) |
| **Nmap** | Network and service fingerprinting |
| **GNS3** | OT/ICS network topology simulation (Purdue model labs) |
| **OpenPLC Runtime** | Soft PLC simulating field devices (S7-1200, ladder logic) |
| **ScadaBR** | SCADA HMI for the simulated plant |
| **pymodbus** | Python Modbus/TCP client for scripted register polling |
| **opcua** | Python OPC-UA client and server (address space browsing, Module 1+) |
| **pyshark** | Python wrapper for tshark — programmatic packet analysis |
| **scapy** | Packet crafting and pcap generation |
| **draw.io** | Network and architecture diagramming |

---

## Lab File Locations (after setup)

Each module's setup script creates its own lab directory under your home folder.

**Introductory Module** — `~/oceon-lab/`
```
~/oceon-lab/
├── venv/                       ← Python virtual environment
├── evolve-power-programs/      ← PLC Structured Text programs
├── diagrams/                   ← draw.io Purdue model worksheet
└── palanca_poll.py             ← Modbus polling helper
```

**Module 1** — `~/palanca_labs/module1/`
```
~/palanca_labs/module1/
├── scripts/                    ← Python lab scripts (copied from repo)
├── pcaps/                      ← Wireshark capture files (Lab 5 baseline)
├── topology/                   ← draw.io topology base file
├── worksheets/
├── outputs/
├── logs/
└── palanca_asset_inventory.csv ← Purdue level mapping worksheet (Lab 2)
```

Key service ports used across the labs:

| Service | Port |
|---|---|
| OpenPLC Web UI | 8080 |
| OpenPLC REST API | 8443 |
| Modbus/TCP (OpenPLC) | 502 |
| ScadaBR HMI | 9090 |
| OPC-UA (Module 1+) | 4840 |

---

## Troubleshooting

**Setup script fails with "SUDO_USER is not set"**
You ran `sudo su` before executing the script. Exit to your normal user session and run `sudo bash <script>` directly.

**Wireshark cannot capture on loopback**
Log out and back in after the setup script completes so the `wireshark` group takes effect. Alternatively run `newgrp wireshark` in your current terminal.

**Network hosts unreachable during setup**
Switch your VM network adapter from Bridged to NAT, then re-run the script.

**ScadaBR won't start / port conflict**
The script patches ScadaBR to port 9090. If you still see a conflict, check what is on that port: `ss -tlnp | grep 9090`. OpenPLC runs on 8080; the two should not collide.

**OPC-UA port 4840 not listening (Module 1 Lab 4)**
ScadaBR is the preferred OPC-UA server but requires manual installation. If it is not installed, start the Python fallback instead: `python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py`. Verify with `ss -tlnp | grep 4840`.

**A check fails in the verification summary**
Re-run the script — it is idempotent and will skip steps that already succeeded. If the same step fails again, check the `[WARN]` output for the specific error and the manual remediation hint printed there.

---

## Contributing / Reporting Issues

If you find a bug in a setup script or a broken lab step, open an issue on this repository. Please include:
- Your Ubuntu version (`lsb_release -a`)
- The exact `[ERR]` or `[WARN]` line from the script output
- Whether you are running on bare metal or a VM (and which hypervisor)
