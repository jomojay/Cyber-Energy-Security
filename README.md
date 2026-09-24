# OCEON Cyber-Energy Security — Lab Repository

This repository contains lab setup scripts and instructions for the OCEON Cyber-Energy Security (CES) course. Each module folder holds everything you need for that module's labs: a setup script that builds your local environment and any supporting files referenced by the lab exercises.

---

## Repository Layout

```
Cyber-Energy-Security/
├── README.md                        ← you are here
├── Introductory_Module/
│   ├── README.md                    ← Module 0 trainee guide
│   ├── oceon_m0_lab_setup.sh        ← Module 0 environment setup (host tools + PLC/SCADA containers)
│   ├── teardown.sh                  ← stops services and removes the Module 0 lab
│   └── docker/                      ← OpenPLC + ScadaBR containers (docker-compose.yml, Dockerfiles)
├── Module_01/
│   ├── README.md                    ← Module 1 trainee guide
│   ├── setup_lab_env.sh             ← Module 1 environment setup (host tools + PLC/SCADA containers)
│   ├── teardown.sh                  ← stops services and removes the Module 1 lab
│   ├── docker/                      ← OpenPLC + ScadaBR containers (docker-compose.yml, Dockerfiles)
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
│   ├── docker-compose.yml           ← full lab topology — 13 containers, 3 networks
│   ├── setup.sh                     ← builds + starts the lab, runs health checks (no sudo)
│   ├── teardown.sh                  ← stops and removes the lab
│   ├── eng-ws/                      ← engineering workstation image — your working point for every lab day
│   ├── hmi/                         ← SCADA-HMI image (OPC-UA + HTTP)
│   ├── sims/                        ← generic Modbus/TCP device image (every PLC/RTU/relay/VFD)
│   ├── switch/                      ← SW-CORE-01 SSH simulator image
│   └── traffic-gen/                 ← ambient Modbus polling traffic generator
├── Module_3/
│   ├── README.md                    ← Module 3 Day 4 trainee guide (Docker build + Option C/pfSense steps)
│   ├── LAB_GUIDE.md                 ← step-by-step firewall exercise: 4 worked rules, you derive the rest
│   ├── firewall-rules-module3.csv   ← the R01-R12 + R99 Palanca FW-OT-01 ruleset
│   ├── docker-compose.yml           ← Module 2's topology + Management/Quarantine/Enterprise zones + fw-ot-01
│   ├── setup.sh                     ← builds + starts the lab, wires cross-zone routing (no sudo)
│   ├── teardown.sh                  ← stops and removes the lab
│   ├── eng-ws/, hmi/, sims/, switch/, traffic-gen/  ← same images as Module 2 (historian/HMI/ENG-WS re-homed, see README)
│   ├── historian/, endpoint/        ← DMZ historian image; generic stub-listener image (mgmt/quarantine/enterprise hosts)
│   ├── firewall/                    ← fw-ot-01 image — boots wide open, no rules; that's the exercise
│   ├── scripts/test_firewall_rules.sh ← self-check against whatever ruleset is currently on fw-ot-01
│   ├── instructor-only/             ← finished reference ruleset — strip before handing the repo to a cohort
│   └── logs/                        ← test_firewall_rules.sh results land here
└── <ModuleName>/                    ← future modules — either pattern above is fine
    └── README.md
```

Each module directory is self-contained and has its own `README.md` with step-by-step instructions for that module's labs. Navigate to your module folder, read its README, and run its setup script before attempting the labs. This top-level README covers what's common across all modules — requirements, Kali notes, and troubleshooting that applies everywhere.

**Two different setup models are in use, and it matters which one your module uses:**
- **Introductory_Module / Module_01** install desktop/CLI tools directly onto your host OS (Wireshark, Nmap, GNS3, draw.io, Python libraries), but run the PLC and SCADA HMI (OpenPLC + ScadaBR) as Docker containers — `sudo bash teardown.sh` (or plain `bash teardown.sh` for Module_01) removes those containers completely, no leftover process or `/opt` install.
- **Module_2_Lab_Setup / Module_3** run everything in Docker containers, including the tools you work from (`eng-ws-01`) — nothing touches your host beyond Docker itself, and `./teardown.sh` leaves your machine exactly as it was. Module 3 extends Module 2's topology rather than replacing it — see [Module_3/README.md](Module_3/README.md) for exactly what changed and why.

All four modules need Docker installed — see **Docker requirements** below, which applies to all of them despite the heading mentioning Module 2.

---

## System Requirements

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 22.04/24.04 LTS **or** Kali Linux (rolling), x86_64 |
| RAM | 8 GB (16 GB recommended for GNS3 topologies) |
| Disk | 20 GB free |
| Network | Internet access during setup (GitHub, distro package mirrors) |

This table is the baseline for **Introductory_Module** and **Module_01**'s host-installed tools. All four modules additionally need Docker — see **Docker requirements** below.

The setup scripts detect which of these two you're on (via `/etc/os-release`) and adjust automatically — you don't need to pass a flag or edit anything.

> **Virtual machine users:** Set your network adapter to **NAT** mode in VirtualBox/VMware before running the setup script. Bridged mode can block the package downloads the script needs.

### Kali Linux notes

The scripts run the same way on Kali as on Ubuntu, with two differences worth knowing about:

- **GNS3** ships from an Ubuntu-only PPA. On Kali the scripts fall back to installing `gns3-server`/`gns3-gui` from Kali's own repos if available there; if not, they print a manual-install link and continue — GNS3 is never a hard requirement for the rest of the lab to work.
- Package names (`wireshark`, `tshark`, `nmap`, `python3-venv`, etc.) are identical between Kali and Ubuntu, so everything else installs the same way on both.

If you're running Kali as your primary pentest distro rather than a dedicated lab VM, consider running the setup scripts inside a disposable VM anyway — GNS3/Wireshark/draw.io still install directly onto whatever host you run them on, even though OpenPLC and ScadaBR no longer do.

### Docker requirements (all modules)

Every module needs Docker — Module_2_Lab_Setup and Module_3 run their entire topology in containers, and Introductory_Module/Module_01 run OpenPLC + ScadaBR as containers. The prerequisite is the same everywhere:

| Requirement | Minimum |
|---|---|
| Docker Engine | Any recent version with the Compose v2 plugin (`docker compose version` must work) |
| RAM | 4 GB free for whichever module's containers are running (Module 3 runs 17 containers — 4 more than Module 2's 13, for the extra zones and the firewall) |
| Disk | ~2 GB for Module 2's images, similar for Module 3's (mostly the same images plus a couple of small extras); OpenPLC's build (Introductory_Module/Module_01) adds a few hundred MB more |

Install Docker via the [official instructions](https://docs.docker.com/engine/install/) — the same steps work on both Ubuntu and Kali (Kali is Debian-based, and Docker's official Debian repo installs cleanly on it; no PPA involved). If you're already using Kali for pentesting, Docker is very likely already installed. Your user needs to be in the `docker` group (`sudo usermod -aG docker $USER`, then log out and back in) since none of these setup scripts run `docker` via `sudo`.

Only one of Introductory_Module / Module_01's PLC+SCADA stacks can run at a time — both publish the same host ports (502/8080/8443/9090). Tear one down (`teardown.sh`) before standing up the other.

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
| Module_3 | `setup.sh` | `./setup.sh` (no `sudo`) |

Each of these has a matching `teardown.sh` in the same folder, invoked the same way (`sudo bash teardown.sh [-v]` for Introductory_Module, `bash teardown.sh [-v]` for Module_01, `./teardown.sh [-v]` for Module_2_Lab_Setup / Module_3). Introductory_Module and Module_01's teardown scripts always stop and remove the OpenPLC + ScadaBR containers (`docker compose down`) and remove everything created under your home directory. Because OpenPLC and ScadaBR are containers, not host installs, there's no systemd unit or `/opt` install left behind afterward — pass `-v` to also wipe their Docker volumes (uploaded PLC program, ScadaBR data source config) for a full reset. Only the built Docker images, group grants, and apt/pip packages are left in place on their own; the scripts print the exact commands for each at the end, for you to run by hand if you want a fully clean host.

- **`oceon_m0_lab_setup.sh` must be run with `sudo bash`, as your normal user account.** It needs root for the whole run and uses `$SUDO_USER` to set correct file ownership. Do **not** log in as root or use `sudo su` first — `$SUDO_USER` is empty in that case and the script will refuse to run.
- **`setup_lab_env.sh` must be run *without* `sudo`.** It calls `sudo` itself for the individual commands that need root, and otherwise installs lab files under your own `$HOME`. Running the whole script with `sudo bash` makes every path resolve under `/root` instead of your home directory, and you'll get sudo password prompts partway through the run either way — so just run it plain.
- **`setup.sh` (Module 2) never needs `sudo`.** It only talks to the Docker daemon (via your user's Docker group membership) to build and start containers — it doesn't touch your host's package manager at all. It builds the images, starts all 13 containers, and runs health checks against every Modbus device before printing your working point. When you're done, `./teardown.sh` stops and removes everything (`./teardown.sh -v` also wipes volumes) — nothing is left behind on your host.
- **`setup.sh` (Module 3) also never needs `sudo`**, same reasoning as Module 2. It builds and starts all 17 containers and wires up cross-zone routing through the firewall container (`fw-ot-01`) — but unlike Module 2, it deliberately leaves `fw-ot-01` **wide open, with no firewall rules**. That's not an incomplete setup; implementing the ruleset is the Day 4 exercise itself, and `setup.sh` says so at the end. `./teardown.sh` removes everything the same way as Module 2.

The scripts are **idempotent**: safe to re-run if a step fails or you need to repair your environment.

**4. Follow what the script prints at the end**

For Introductory_Module / Module_01, that's a checklist of manual steps (log out/in for group changes, loading the PLC program via the OpenPLC web UI, wiring ScadaBR to OpenPLC, etc.) — complete them in order before starting the labs. OpenPLC and ScadaBR themselves are already built and running by the time the script finishes; nothing further to install. For Module_2_Lab_Setup, `setup.sh` instead prints your working point directly: `docker exec -it eng-ws-01 bash` — no manual steps needed, you're ready for Lab Day 1 immediately. For Module_3, `setup.sh` prints a pointer to `LAB_GUIDE.md` instead — the lab is up, but the firewall configuration itself (the actual Day 4 deliverable) is what you do next, not something the script does for you.

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
| **pymodbus** | Python Modbus/TCP client for scripted register polling |
| **opcua** | Python OPC-UA client and server (address space browsing, Module 1+) |
| **pyshark** | Python wrapper for tshark — programmatic packet analysis |
| **scapy** | Packet crafting and pcap generation |
| **draw.io** | Network and architecture diagramming |

**Introductory_Module / Module_01** run these as Docker containers instead (built by the same setup script, from a `docker/` folder in each module):

| Tool | Purpose |
|---|---|
| **OpenPLC Runtime** | Soft PLC simulating field devices (S7-1200, ladder logic) |
| **ScadaBR** | SCADA HMI for the simulated plant |

**Module_2_Lab_Setup** installs nothing on your host — Docker is the only tool you need there. Every device in the topology (PLCs, RTUs, protection relays, VFD, HMIs, the core switch, the historian) is its own container, and the `eng-ws-01` container you work from already has Nmap, tshark, tcpdump, an SSH client, pymodbus, and opcua pre-installed — see [Module_2_Lab_Setup/README.md](Module_2_Lab_Setup/README.md) for the full device map.

**Module_3** also installs nothing on your host — same model, same `eng-ws-01` toolset (it's the same image), plus a new `fw-ot-01` container (iptables + iproute2) that boots with no rules on it: implementing the firewall ruleset on `fw-ot-01` is the Day 4 exercise, not something the setup script pre-configures. See [Module_3/README.md](Module_3/README.md) and [Module_3/LAB_GUIDE.md](Module_3/LAB_GUIDE.md).

---

## Lab File Locations (after setup)

Applies to **Introductory_Module** and **Module_01** — each setup script creates its own lab directory under your home folder. Module 2 and Module 3 don't use a host lab directory at all; see below.

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

**Module_3** — also no host lab directory. Six Docker networks now (`ot_control` / `ot_supervisory` / `ot_dmz` plus the new `ot_management` / `ot_quarantine` / `ot_enterprise`), with a firewall container (`fw-ot-01`) sitting on all six. Same working point as Module 2:
```bash
docker exec -it eng-ws-01 bash
```
but the Day 4 exercise itself happens on the firewall container instead:
```bash
docker exec -it fw-ot-01 bash
```
Full zone/container map, what changed from Module 2's topology and why, and the step-by-step firewall exercise are in [Module_3/README.md](Module_3/README.md) and [Module_3/LAB_GUIDE.md](Module_3/LAB_GUIDE.md) — again kept there rather than duplicated here.

---

## Troubleshooting

**Setup script fails with "SUDO_USER is not set"** *(Introductory_Module only)*
You ran `sudo su` before executing `oceon_m0_lab_setup.sh`, or ran it with `bash` instead of `sudo bash`. Exit to your normal user session and run `sudo bash oceon_m0_lab_setup.sh` directly. (`setup_lab_env.sh` in Module_01 doesn't use `$SUDO_USER` and shouldn't be run with `sudo` at all — see Getting Started above.)

**Wireshark cannot capture on loopback**
Log out and back in after the setup script completes so the `wireshark` group takes effect. Alternatively run `newgrp wireshark` in your current terminal.

**Network hosts unreachable during setup**
Switch your VM network adapter from Bridged to NAT, then re-run the script.

**ScadaBR won't start / port conflict**
ScadaBR runs as a container publishing to host port 9090, and OpenPLC's web UI is a separate container on 8080 — they no longer share a network namespace to collide in. Check `docker compose -f docker/docker-compose.yml ps` and `docker compose -f docker/docker-compose.yml logs scadabr` (run from the module folder).

**OPC-UA port 4840 not listening (Module 1 Lab 4)**
Both setup scripts run ScadaBR automatically now, and it's the preferred OPC-UA/HMI source — port 4840 only matters if the ScadaBR container failed to build/start (check the setup script's `[FAIL]`/`[WARN]` output, or `docker compose -f docker/docker-compose.yml logs scadabr`). In that case, start the Python fallback instead: `python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py`. Verify with `ss -tlnp | grep 4840`.

**A check fails in the verification summary**
Re-run the script — it is idempotent and will skip steps that already succeeded. If the same step fails again, check the `[WARN]` output for the specific error and the manual remediation hint printed there.

**Module 2: `setup.sh` fails immediately with a Docker error**
`docker` or the `docker compose` v2 plugin isn't installed — the script checks for both up front and prints a link. If you get a permission error instead, your user isn't in the `docker` group yet (`sudo usermod -aG docker $USER`, then log out and back in).

**Module 2: Nmap finds an extra, unexplained host responding on 502/22/80/etc.** *(worth knowing if you're running Module 0/1 and Module 2 on the same machine)*
That's not a lab device — it's your own host. `192.168.1.254`/`192.168.2.254` are the Docker networks' gateway addresses, and Docker routes any host-side service listening on `0.0.0.0` through them. This shows up if Module 0/1's OpenPLC container (which also publishes port 502 to the host) is still running from an earlier session — stop it with `docker compose -f docker/docker-compose.yml down` in that module's folder, or leave it as a live demonstration of host/container network boundaries.

**Module 2: individual troubleshooting** (health check failures, no traffic in a capture, rebuilding after an edit) is covered in [Module_2_Lab_Setup/README.md](Module_2_Lab_Setup/README.md#troubleshooting).

**Module 3: `fw-ot-01` lets everything through, or I ran the tests and almost everything failed**
That's the expected starting state, not a bug — `fw-ot-01` boots with no firewall rules on purpose. Implementing the ruleset is the Day 4 exercise; see [Module_3/LAB_GUIDE.md](Module_3/LAB_GUIDE.md). `./scripts/test_firewall_rules.sh` is meant to show mostly failures before you start and fewer as you add rules, not just once at the end.

**Module 3: I made a mistake in my firewall rules and want to start over**
`docker compose restart fw-ot-01` resets it back to the wide-open starting state — safe to run any time.

**Module 3: individual troubleshooting** (reading rule hit counters, cross-zone routing issues, interpreting CONNECTED/TIMEOUT/REFUSED in test results) is covered in [Module_3/README.md](Module_3/README.md#troubleshooting-docker-build).

---

## Contributing / Reporting Issues

If you find a bug in a setup script or a broken lab step, open an issue on this repository. Please include:
- Your OS and version (`lsb_release -a`, or `cat /etc/os-release` on Kali)
- The exact `[ERR]`, `[FAIL]`, or `[WARN]` line from the script output (or, for Module 2/Module 3, the `docker compose logs <service>` output for the failing container)
- Whether you are running on bare metal or a VM (and which hypervisor)
- For Module 2/Module 3: your `docker compose version` output
