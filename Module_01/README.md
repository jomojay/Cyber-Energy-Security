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
- OpenPLC's build step and the ScadaBR download are the slow parts (several minutes on first run).
- The script prints `[FAIL]`/`[WARN]` lines for anything that didn't fully succeed, plus a remediation hint — check those before starting the labs if the summary at the end isn't all green.
- When it finishes, if ScadaBR installed successfully it prints the same kind of post-install block Module 0 does: how to start Tomcat, the URL to visit, and how to wire ScadaBR to OpenPLC as a Modbus data source — read it before Lab 4.

---

## Tearing down

```bash
bash teardown.sh
```

Stops the OpenPLC and ScadaBR services if running, and removes everything the setup script created under your home directory (`~/palanca_labs/module1/`, the Palanca-OT Wireshark profile, the ScadaBR desktop shortcut). Same invocation rule as setup — run it plain, no `sudo` (it calls `sudo` itself for the parts that need root).

It always removes the OpenPLC systemd unit too (not just stops it) — that unit name is shared with Introductory_Module's OpenPLC install, and leaving a stale one behind is what causes a stopped-but-still-registered service from one module to keep serving requests through the other module's fresh build. Everything else stays in place on its own: `/opt/OpenPLC_v3`, `/opt/ScadaBR`, and apt/pip packages (Wireshark, Nmap, pymodbus, opcua, pyshark, scapy). At the end it prints the exact commands for each of those, for you to run by hand if you want a fully clean host.

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

ScadaBR (the Palanca SCADA HMI) installs to `/opt/ScadaBR`, same as Module 0, with a desktop shortcut (**ScadaBR-Palanca**) that starts it and opens the browser. If the download or install fails — check for `[WARN]`/`[FAIL]` lines under "STEP 4" in the setup output — Lab 4 falls back to the bundled Python OPC-UA server instead.

| Service | Port |
|---|---|
| OpenPLC Web UI | 8080 |
| Modbus/TCP (OpenPLC) | 502 |
| ScadaBR HMI | 9090 |
| OPC-UA (Python fallback server, only if ScadaBR isn't installed) | 4840 |

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

If ScadaBR installed successfully (check for it in the setup summary, or `test -f /opt/ScadaBR/tomcat/bin/startup.sh`), wire it up first — it's the primary OPC-UA/HMI source for this lab:

1. Start it: `sudo /opt/ScadaBR/tomcat/bin/startup.sh` (or double-click the **ScadaBR-Palanca** desktop shortcut), wait ~15s, then open http://localhost:9090/ScadaBR (`admin` / `admin`).
2. **Data Sources → New Data Source → Modbus IP**: Name `Palanca Generator`, Host `127.0.0.1`, Port `502`, Unit ID `1`, Update period 5s, Transport TCP. Save.
3. Add data points matching the register map in `palanca_gen_start.st` (coils/discretes as Binary, registers as Two byte int unsigned) — start with `GEN1_START_CMD`, `GEN1_RUNNING`, `GEN1_FREQUENCY_x100`.
4. Enable the data source and confirm the points go green.

If ScadaBR isn't installed, use the bundled Python fallback instead — two scripts, run in order. `palanca_opcua_browse.py` is read-only — you run and interpret it, you don't modify it.

**Terminal 1 — start the OPC-UA server** (mirrors the Modbus registers into an OPC-UA address space):
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

**Port 4840 not listening (Lab 4)** — expected if ScadaBR installed successfully, since it's the primary OPC-UA/HMI source and the Python server only needs to run as a fallback. Check `sudo ss -tlnp | grep 9090` instead. If ScadaBR isn't installed either, start the Python fallback: `python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py`.

**ScadaBR won't start / port conflict** — `sudo /opt/ScadaBR/tomcat/bin/startup.sh`, wait ~15s, then open http://localhost:9090/ScadaBR. Check `ss -tlnp | grep 9090` if it still doesn't respond. OpenPLC runs on 8080; the two should not collide since the setup script patches ScadaBR's Tomcat to 9090.

**ScadaBR failed to download or install** — check the "STEP 4" output from `setup_lab_env.sh` for the exact `[FAIL]` line. A failed download usually means a network hiccup — just re-run `bash setup_lab_env.sh`, it's idempotent and will retry. Lab 4 still works via the Python fallback server in the meantime.

**`opcua`/`pymodbus` import errors** — the setup script installs these with `pip3 install --break-system-packages`, system-wide (no venv in this module, unlike Module 0). Re-run `bash setup_lab_env.sh` if imports still fail.

**A check fails in the setup summary** — re-run `bash setup_lab_env.sh`; it's idempotent and will only redo what didn't succeed. If the same `[FAIL]` line comes back, follow the remediation hint printed next to it.
