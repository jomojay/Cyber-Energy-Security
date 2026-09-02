# Palanca Gas Plant — Module 2 Lab Environment

Docker-based simulation of the Palanca offshore SCADA network described
throughout Module 2, used for Lab Days 1–6. It reproduces the exact
device names, vendors, and IP addresses from the Module 2 asset
inventory (Section 2.4.3) — including the flat Control/Supervisory
network trainees are meant to discover in Lab Day 5.

## Quick start

```bash
./setup.sh          # builds and starts everything, runs health checks
docker exec -it eng-ws-01 bash   # your working point for every lab day
./teardown.sh        # stops and removes the lab when you're done
```

## Device map (matches Module 2, Section 2.4.3)

| Device        | Role              | Vendor            | IP(s)                          | Protocol(s)        |
|---------------|-------------------|--------------------|---------------------------------|---------------------|
| PLC-MAIN-01   | PLC               | Siemens S7-1200    | 192.168.1.10                    | Modbus/TCP (502)    |
| PLC-AUX-01    | PLC               | Siemens S7-1200    | 192.168.1.11                    | Modbus/TCP (502)    |
| GEN1-RTU      | RTU               | GE Automation      | 192.168.1.20                    | Modbus/TCP (502)    |
| GEN2-RTU      | RTU               | GE Automation      | 192.168.1.21                    | Modbus/TCP (502)    |
| PROT-REL-01   | Protection relay  | ABB REL670         | 192.168.1.30                    | Modbus/TCP (502)    |
| PROT-REL-02   | Protection relay  | ABB REL670         | 192.168.1.31                    | Modbus/TCP (502)    |
| VFD-PUMP-01   | VFD               | ABB ACS580         | 192.168.1.40                    | Modbus/TCP (502)    |
| SW-CORE-01    | Core switch       | Cisco Cat 2960X (sim) | 192.168.1.1 / 192.168.2.1    | SSH (22)             |
| SCADA-HMI-01  | HMI               | Windows 10 (sim)   | 192.168.2.10 **and** 192.168.1.110 | OPC-UA (4840), HTTP (80) |
| SCADA-HMI-02  | HMI               | Windows 10 (sim)   | 192.168.2.11 **and** 192.168.1.111 | OPC-UA (4840), HTTP (80) |
| ENG-WS-01     | Engineering WS    | Windows 10 (sim)   | 192.168.2.20 **and** 192.168.1.120 | (your working container) |
| HISTORIAN-01  | Historian         | Win Server 2019 (sim) | 192.168.3.10 / 192.168.2.30 | HTTP (80)            |

**Why HMI/ENG-WS have two IPs:** this reproduces the real Palanca
"Critical Finding" from Section 2.5.3 — Control Zone and Supervisory
Zone currently share a flat network. Discovering exactly this is part
of the Lab Day 5 deliverable. Don't mention it to trainees before then.

## Credentials

| Target      | Username | Password      |
|-------------|----------|---------------|
| SW-CORE-01  | admin    | palanca-lab   |

## Mapping to each lab day

- **Day 1 (Passive Discovery):** capture on the host bridge interface printed by `setup.sh` (the SPAN-port equivalent).
- **Day 2 (ARP/MAC):** `ssh admin@sw-core-01` from inside `eng-ws-01`.
- **Day 3 (Nmap):** run Nmap from inside `eng-ws-01` against `192.168.1.0/24`.
- **Day 4 (Asset Inventory):** combine Days 1–3 findings; ground truth is the device map above.
- **Day 5 (Zone Mapping):** the dual-homed HMI/ENG-WS containers are the flat-network finding to document.
- **Day 6 (Vulnerability Correlation):** use the DEVICE_VENDOR strings returned by `modbus-discover` as your NVD search terms.

Full step-by-step instructions for every day are in the accompanying
**Module 2 Lab Run Book** document — this repo is the environment it
runs against.

## Troubleshooting

- `docker compose logs <service>` — check why a device failed its health check.
- If `tcpdump`/Wireshark shows no traffic, confirm `traffic-gen` is running: `docker compose logs traffic-gen`.
- Rebuilding after an edit: `docker compose build <service> && docker compose up -d <service>`.
- **Nmap finds an extra, unexplained host at `192.168.1.254`/`192.168.2.254` responding on 502/22/80/etc.** — that's your own machine, not a lab device. Those are the bridge networks' gateway addresses; Docker routes any host-side service listening on `0.0.0.0` through them. This shows up if you (or a previous trainee session on the same VM) left Module 0/1's OpenPLC Runtime running — it also binds port 502 on `0.0.0.0`. Stop it (`sudo systemctl stop openplc`, or find and kill `webserver.py`/`core/openplc`) or just point it out as a red herring if you'd rather demonstrate host/container network boundaries live.
