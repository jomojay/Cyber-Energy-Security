# OCEON Module 1 — OT Network Fundamentals

Trainee guide for this module. Case study: Evolve Power's Palanca Gas Plant (generator control, feeder protection).

For anything not covered here (system requirements, Kali vs. Ubuntu notes, general troubleshooting), see the [repository-level README](../README.md).

---

## 1. Run the setup script

```bash
bash setup_lab_env.sh
```

> **Do not use `sudo` here.** Unlike Module 0's script, this one calls `sudo` itself for the individual commands that need root, and otherwise installs everything under your own `$HOME`. Running the whole script with `sudo bash` puts your lab files under `/root` instead — you'll still get sudo password prompts partway through, so just run it plain.

- **Idempotent** — safe to re-run if a step fails; completed steps are skipped.
- OpenPLC's build step is the slow part (several minutes on first run).
- The script prints `[FAIL]`/`[WARN]` lines for anything that didn't fully succeed, plus a remediation hint — check those before starting the labs if the summary at the end isn't all green.

---

## 2. What you get

Everything lands in `~/palanca_labs/module1/`:

```
~/palanca_labs/module1/
├── scripts/                    ← copies of every .py file in this folder
├── pcaps/palanca_baseline.pcap ← auto-generated Lab 5 baseline capture
├── topology/palanca_topology_base.xml  ← Lab 6 draw.io starter
├── worksheets/  outputs/  logs/    ← empty, yours to fill in during labs
├── palanca_gen_start.st        ← PLC program you load into OpenPLC
└── palanca_asset_inventory.csv ← Lab 2 worksheet
```

A Wireshark colour profile (**Palanca-OT**, with display-filter macros) is also installed under `~/.config/wireshark/profiles/`.

| Service | Port |
|---|---|
| OpenPLC Web UI | 8080 |
| Modbus/TCP (OpenPLC) | 502 |
| OPC-UA (Python fallback server) | 4840 |

Work from the copies in `~/palanca_labs/module1/scripts/`, not the ones in this repo checkout — that's your sandbox, and re-running the setup script won't overwrite files you've already edited there.

---

## 3. Load the PLC program

Before any Modbus/OPC-UA lab will show live data, load the plant simulation into OpenPLC:

1. Open http://localhost:8080 and log in (`openplc` / `openplc` unless your instructor changed it).
2. **Programs → Upload New Program**, select `~/palanca_labs/module1/palanca_gen_start.st`.
3. **Compile**, then **Start PLC**.
4. On the **Monitoring** tab you should see `GEN1_RUNNING` flip to `TRUE` a few seconds after you write `GEN1_START_CMD` (coil 0) — that's the generator start sequence running.

The full register map (coils, discrete inputs, holding/input registers) is documented in the header comment of `palanca_gen_start.st` — that file is the source of truth; the numbers are repeated in each lab script's docstring for convenience but can drift, so check the `.st` file if anything looks inconsistent.

---

## 4. Running the labs

### Lab 2 — Asset inventory / Purdue level mapping

Open `~/palanca_labs/module1/palanca_asset_inventory.csv` in a spreadsheet app or text editor and fill in every `L___` cell with the correct Purdue level (L0–L4/L3.5) for that device, based on its role in the Palanca plant.

### Lab 3 — OT Network Fundamentals (Modbus/TCP)

`scripts/palanca_modbus_read.py` is a **trainee template** — sections marked `<<< TASK >>>` need your edits before it does anything useful:

- **Task 1**: change `START_REGISTER` to read `STARTUP_DELAY_SEC` (register 40008) instead of the default `GEN1_FREQUENCY_x100`.
- **Task 2**: in `display_register_values()`, add the engineering-unit conversions (frequency, voltage, power) using the formulas given in the comment block.
- **Task 3**: extend the script to read `SYS_ALARM_WORD`, print an alert if it's non-zero, and append each reading to `~/palanca_labs/module1/outputs/readings.txt`.

Run it with:
```bash
python3 ~/palanca_labs/module1/scripts/palanca_modbus_read.py
```

Then run the extension, which needs no edits — it just demonstrates threshold-based anomaly detection on the same registers:
```bash
python3 ~/palanca_labs/module1/scripts/palanca_modbus_monitor.py
```

### Lab 4 — OPC-UA Exploration

Two scripts, run in order. `palanca_opcua_browse.py` is read-only — you run and interpret it, you don't modify it.

**Terminal 1 — start the OPC-UA server** (mirrors the Modbus registers into an OPC-UA address space; only needed if ScadaBR isn't installed as your OPC-UA source):
```bash
python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py
```

**Terminal 2 — browse it:**
```bash
python3 ~/palanca_labs/module1/scripts/palanca_opcua_browse.py
```
It prints the security policy in use, browses the full address space, reads every Generator 1 value, and ends with the lab's analysis questions (Q4–Q7) inline — answer them as you go.

### Lab 5 — Wireshark protocol capture

The setup script already generated `~/palanca_labs/module1/pcaps/palanca_baseline.pcap` for you. Open it with the lab profile:
```bash
wireshark ~/palanca_labs/module1/pcaps/palanca_baseline.pcap
```
Apply **Palanca-OT** under *Edit → Configuration Profiles*, and use the built-in filter macros (`Modbus Only`, `OPC-UA Only`, `Modbus Writes`, `FC03 Read Holding`, `From/To PLC`, `OT Subnet Only`) to work through the worksheet.

The exact packet numbers for each worksheet callout (FC03 read, FC01 coil read, the alarm-active response, the FC10 write, and the anomalous FC 0x7F packet) are printed by the generator itself — re-run it if you want to double check them against a fresh capture:
```bash
python3 ~/palanca_labs/module1/scripts/generate_baseline_pcap.py
```

### Lab 6 — Network topology documentation

```bash
drawio ~/palanca_labs/module1/topology/palanca_topology_base.xml
```
Add device names, IP addresses, Purdue levels, protocol labels, VLAN boundary boxes, and SPOF annotations to the unlabelled base diagram.

> **Lab 1** isn't backed by a script in this folder — check with your instructor for that exercise's materials.

---

## Troubleshooting

Module-specific quick hits — for anything else, see the [repository-level Troubleshooting section](../README.md#troubleshooting).

**Port 502 not listening / setup log shows "OpenPLC install script failed"** — first check `sudo systemctl start openplc` and re-check *Start PLC* at http://localhost:8080. If OpenPLC never installed at all, re-run the setup script and watch for a CMake error mentioning `Compatibility with CMake < 3.5 has been removed` / `Error installing OpenDNP3` — that's current CMake (4.x, shipped by Kali rolling) refusing to configure OpenPLC's bundled OpenDNP3 build. The script already works around this (`CMAKE_POLICY_VERSION_MINIMUM=3.5`); if it still fails, install manually from `/opt/OpenPLC_v3`: `sudo env CMAKE_POLICY_VERSION_MINIMUM=3.5 bash install.sh linux`.

**Port 4840 not listening (Lab 4)** — ScadaBR is the preferred OPC-UA source but needs manual install; start the Python fallback instead: `python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py`.

**`opcua`/`pymodbus` import errors** — the setup script installs these with `pip3 install --break-system-packages`, system-wide (no venv in this module, unlike Module 0). Re-run `bash setup_lab_env.sh` if imports still fail.

**A check fails in the setup summary** — re-run `bash setup_lab_env.sh`; it's idempotent and will only redo what didn't succeed. If the same `[FAIL]` line comes back, follow the remediation hint printed next to it.
