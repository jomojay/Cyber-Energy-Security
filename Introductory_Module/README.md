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
- Takes 5–15 minutes depending on your connection. GNS3 and the OpenPLC/ScadaBR container build are the slow parts.

When it finishes, it prints a **post-install checklist** — read it, it tells you exactly what to do next (log out/in, load the PLC program, wire ScadaBR to OpenPLC). OpenPLC and ScadaBR are already built and running as containers by the time the script finishes — no separate manual install step. The steps below assume you've completed that checklist.

---

## Tearing down

```bash
sudo bash teardown.sh          # stop + remove containers, keep uploaded PLC program / ScadaBR config
sudo bash teardown.sh -v       # also wipe those (full reset)
```

Stops and removes the OpenPLC + ScadaBR containers (`docker compose down`), and removes everything the setup script created under your home directory (`~/oceon-lab/`, the ScadaBR desktop shortcut, the Evolve-Power Wireshark profile). Same invocation rules as the setup script — `sudo bash`, as your normal user, not after `sudo su`.

Because OpenPLC and ScadaBR are containers instead of host installs, there's no systemd unit, no `/opt` install, and no Tomcat/JVM process left running afterward — `docker compose down` removes them completely. Only the built Docker images, the wireshark/ubridge group grants, and apt packages (Wireshark, Nmap, GNS3, draw.io) stay in place on their own. At the end it prints the exact commands for each of those, for you to run by hand if you want a fully clean host.

---

## 2. What you get

Everything lands in `~/oceon-lab/`:

```
~/oceon-lab/
├── venv/                       ← Python virtual environment (pymodbus, rich)
├── evolve-power-programs/
│   └── palanca_motor_feeder.st ← PLC program you load into OpenPLC
├── diagrams/
│   └── OCEON-M0-PURDUE-TEMPLATE.drawio  ← Lab 2 worksheet
└── palanca_poll.py             ← Modbus polling helper (Lab 1)
```

OpenPLC and ScadaBR themselves run as containers, built from `docker/docker-compose.yml` in this folder (not under `~/oceon-lab/`) — see `docker compose -f docker/docker-compose.yml ps` / `logs`. A Wireshark colour profile (**Evolve-Power**) and a ScadaBR desktop shortcut are also installed.

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

OpenPLC runs in a container, but `-i lo` still works: Docker's userland-proxy accepts your loopback connection to `127.0.0.1:502` directly before relaying it into the container, so the client-side traffic really is on `lo`. If a host has that proxy disabled (`userland-proxy=false` in the Docker daemon config) and you see nothing, try `-i docker0` or `-i any` instead.

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

**ScadaBR won't start** — `docker compose -f docker/docker-compose.yml up -d scadabr`, wait ~15s, then open http://localhost:9090/ScadaBR. Check `docker compose -f docker/docker-compose.yml logs scadabr` if it still doesn't respond.

**OpenPLC web UI / Modbus port not responding** — check `docker compose -f docker/docker-compose.yml ps` (both `openplc` and `scadabr` should show `running`) and `docker compose -f docker/docker-compose.yml logs openplc`. Restart with `docker compose -f docker/docker-compose.yml restart openplc`.

**GNS3 missing after setup** — the GNS3 PPA is Ubuntu-only and doesn't always publish for the newest release; the script warns and continues without blocking the rest of your environment. Install it manually per the link the script prints, whenever you get to the GNS3-based topology labs.

**Only one of Module 0 / Module 1's PLC+SCADA stacks can run at a time** — both publish the same host ports (502/8080/8443/9090). If you're switching between modules, tear one down first: `sudo bash teardown.sh` here, or the equivalent in `Module_01/`, before starting the other.
