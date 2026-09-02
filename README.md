# OCEON Cyber-Energy Security — Lab Repository

This repository contains lab setup scripts and instructions for the OCEON Cyber-Energy Security (CES) course. Each module folder holds everything you need for that module's labs: a setup script that builds your local environment and any supporting files referenced by the lab exercises.

---

## Repository Layout

```
Cyber-Energy-Security/
├── README.md                        ← you are here
├── Introductory_Module/
│   ├── README.md                    ← Module 0 trainee guide
│   └── oceon_m0_lab_setup.sh        ← Module 0 environment setup (installs onto the host)
├── Module_01/
│   ├── README.md                    ← Module 1 trainee guide
│   ├── setup_lab_env.sh             ← Module 1 environment setup (installs onto the host)
│   ├── palanca_modbus_read.py       ← Lab 3 trainee template (Modbus/TCP)
│   ├── palanca_modbus_monitor.py    ← Lab 3 extension (anomaly thresholds)
│   ├── palanca_opcua_server.py      ← Lab 4 OPC-UA server simulator
│   ├── palanca_opcua_browse.py      ← Lab 4 OPC-UA client / explorer
│   ├── generate_baseline_pcap.py    ← Lab 5 baseline traffic generator
│   ├── palanca_gen_start.st         ← PLC Structured Text program
│   ├── palanca_asset_inventory.csv  ← Lab worksheet (Purdue level mapping)
│   └── palanca_topology_base.xml    ← draw.io topology starter file
├── Module_2_Lab_Setup/
│   ├── README.md                    ← Module 2 trainee guide
│   ├── docker-compose.yml           ← full lab topology — 12 containers, 3 networks
│   ├── setup.sh                     ← builds + starts the lab, runs health checks (no sudo)
│   ├── teardown.sh                  ← stops and removes the lab
│   ├── eng-ws/                      ← engineering workstation image — your working point for every lab day
│   ├── hmi/                         ← SCADA-HMI image (OPC-UA + HTTP)
│   ├── sims/                        ← generic Modbus/TCP device image (every PLC/RTU/relay/VFD)
│   ├── switch/                      ← SW-CORE-01 SSH simulator image
│   └── traffic-gen/                 ← ambient Modbus polling traffic generator
└── <ModuleName>/                    ← future modules — either pattern above is fine
    └── README.md
```

Each module directory is self-contained and has its own `README.md` with step-by-step instructions for that module's labs. Navigate to your module folder, read its README, and run its setup script before attempting the labs. This top-level README covers what's common across all modules — requirements, Kali notes, and troubleshooting that applies everywhere.

**Two different setup models are in use, and it matters which one your module uses:**
- **Introductory_Module / Module_01** install tools and services directly onto your host OS (apt packages, a compiled OpenPLC runtime, ScadaBR).
- **Module_2_Lab_Setup** runs everything in Docker containers — nothing touches your host beyond Docker itself, and `./teardown.sh` leaves your machine exactly as it was.

---

## System Requirements

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 22.04/24.04 LTS **or** Kali Linux (rolling), x86_64 |
| RAM | 8 GB (16 GB recommended for GNS3 topologies) |
| Disk | 20 GB free |
| Network | Internet access during setup (GitHub, distro package mirrors) |

This table is the baseline for **Introductory_Module** and **Module_01**, which install onto the host. **Module_2_Lab_Setup** has a different, lighter requirement — see below.

The setup scripts detect which of these two you're on (via `/etc/os-release`) and adjust automatically — you don't need to pass a flag or edit anything.

> **Virtual machine users:** Set your network adapter to **NAT** mode in VirtualBox/VMware before running the setup script. Bridged mode can block the package downloads the script needs.

### Kali Linux notes

The scripts run the same way on Kali as on Ubuntu, with two differences worth knowing about:

- **GNS3** ships from an Ubuntu-only PPA. On Kali the scripts fall back to installing `gns3-server`/`gns3-gui` from Kali's own repos if available there; if not, they print a manual-install link and continue — GNS3 is never a hard requirement for the rest of the lab to work.
- Package names (`wireshark`, `tshark`, `nmap`, `python3-venv`, etc.) are identical between Kali and Ubuntu, so everything else installs the same way on both.

If you're running Kali as your primary pentest distro rather than a dedicated lab VM, consider running the setup scripts inside a disposable VM or container — they install and enable system services (OpenPLC, ScadaBR) that you may not want persisting on your main box.

### Module 2 requirements (Docker)

Module 2 doesn't need the apt packages above at all. The only prerequisite is:

| Requirement | Minimum |
|---|---|
| Docker Engine | Any recent version with the Compose v2 plugin (`docker compose version` must work) |
| RAM | 4 GB free for the container stack (12 lightweight containers) |
| Disk | ~2 GB for images |

Install Docker via the [official instructions](https://docs.docker.com/engine/install/) — the same steps work on both Ubuntu and Kali (Kali is Debian-based, and Docker's official Debian repo installs cleanly on it; no PPA involved). If you're already using Kali for pentesting, Docker is very likely already installed.

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

Each module has its own setup script inside its folder, and **each is invoked differently** — check the table before running any of them:

| Module | Script | Run it with |
|---|---|---|
| Introductory_Module | `oceon_m0_lab_setup.sh` | `sudo bash oceon_m0_lab_setup.sh` |
| Module_01 | `setup_lab_env.sh` | `bash setup_lab_env.sh` (no `sudo`) |
| Module_2_Lab_Setup | `setup.sh` | `./setup.sh` (no `sudo`) |

- **`oceon_m0_lab_setup.sh` must be run with `sudo bash`, as your normal user account.** It needs root for the whole run and uses `$SUDO_USER` to set correct file ownership. Do **not** log in as root or use `sudo su` first — `$SUDO_USER` is empty in that case and the script will refuse to run.
- **`setup_lab_env.sh` must be run *without* `sudo`.** It calls `sudo` itself for the individual commands that need root, and otherwise installs lab files under your own `$HOME`. Running the whole script with `sudo bash` makes every path resolve under `/root` instead of your home directory, and you'll get sudo password prompts partway through the run either way — so just run it plain.
- **`setup.sh` (Module 2) never needs `sudo`.** It only talks to the Docker daemon (via your user's Docker group membership) to build and start containers — it doesn't touch your host's package manager at all. It builds the images, starts all 12 containers, and runs health checks against every Modbus device before printing your working point. When you're done, `./teardown.sh` stops and removes everything (`./teardown.sh -v` also wipes volumes) — nothing is left behind on your host.

The scripts are **idempotent**: safe to re-run if a step fails or you need to repair your environment.

**4. Follow what the script prints at the end**

For Introductory_Module / Module_01, that's a checklist of manual steps (log out/in for group changes, one-time installs that require interactive prompts, browser configuration, etc.) — complete them in order before starting the labs. For Module_2_Lab_Setup, `setup.sh` instead prints your working point directly: `docker exec -it eng-ws-01 bash` — no manual steps needed, you're ready for Lab Day 1 immediately.

**5. Open that module's own README for the lab walkthrough**

Each module folder has a `README.md` with step-by-step instructions for every lab in that module — what to run, what to edit, and what each script's output means. This top-level README only covers what's common across all modules.

---

## Tools Installed by the Lab Scripts

**Introductory_Module / Module_01** install these directly onto your host:

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

**Module_2_Lab_Setup** installs nothing on your host — Docker is the only tool you need there. Every device in the topology (PLCs, RTUs, protection relays, VFD, HMIs, the core switch, the historian) is its own container, and the `eng-ws-01` container you work from already has Nmap, tshark, tcpdump, an SSH client, pymodbus, and opcua pre-installed — see [Module_2_Lab_Setup/README.md](Module_2_Lab_Setup/README.md) for the full device map.

---

## Lab File Locations (after setup)

Applies to **Introductory_Module** and **Module_01** — each setup script creates its own lab directory under your home folder. Module 2 doesn't use a host lab directory at all; see below.

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
├── palanca_gen_start.st        ← PLC Structured Text program
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

**Module_2_Lab_Setup** — there's no host lab directory; every device lives in its own container on one of three Docker networks (`ot_control` / `ot_supervisory` / `ot_dmz`). Your working point is a shell inside the engineering workstation container:
```bash
docker exec -it eng-ws-01 bash
```
The full 12-device map (names, vendors, IPs, protocols) and per-lab-day instructions are in [Module_2_Lab_Setup/README.md](Module_2_Lab_Setup/README.md) — kept there rather than duplicated here so the two can't drift out of sync.

---

## Troubleshooting

**Setup script fails with "SUDO_USER is not set"** *(Introductory_Module only)*
You ran `sudo su` before executing `oceon_m0_lab_setup.sh`, or ran it with `bash` instead of `sudo bash`. Exit to your normal user session and run `sudo bash oceon_m0_lab_setup.sh` directly. (`setup_lab_env.sh` in Module_01 doesn't use `$SUDO_USER` and shouldn't be run with `sudo` at all — see Getting Started above.)

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

**Module 2: `setup.sh` fails immediately with a Docker error**
`docker` or the `docker compose` v2 plugin isn't installed — the script checks for both up front and prints a link. If you get a permission error instead, your user isn't in the `docker` group yet (`sudo usermod -aG docker $USER`, then log out and back in).

**Module 2: Nmap finds an extra, unexplained host responding on 502/22/80/etc.** *(worth knowing if you're running Module 0/1 and Module 2 on the same machine)*
That's not a lab device — it's your own host. `192.168.1.254`/`192.168.2.254` are the Docker networks' gateway addresses, and Docker routes any host-side service listening on `0.0.0.0` through them. This shows up if Module 0/1's OpenPLC Runtime (which also binds port 502 on `0.0.0.0`) is still running from an earlier session — stop it with `sudo systemctl stop openplc`, or leave it as a live demonstration of host/container network boundaries.

**Module 2: individual troubleshooting** (health check failures, no traffic in a capture, rebuilding after an edit) is covered in [Module_2_Lab_Setup/README.md](Module_2_Lab_Setup/README.md#troubleshooting).

---

## Contributing / Reporting Issues

If you find a bug in a setup script or a broken lab step, open an issue on this repository. Please include:
- Your OS and version (`lsb_release -a`, or `cat /etc/os-release` on Kali)
- The exact `[ERR]`, `[FAIL]`, or `[WARN]` line from the script output (or, for Module 2, the `docker compose logs <service>` output for the failing container)
- Whether you are running on bare metal or a VM (and which hypervisor)
- For Module 2: your `docker compose version` output
