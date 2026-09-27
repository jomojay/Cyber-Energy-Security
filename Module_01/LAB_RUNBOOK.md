# Module 1 — Lab Runbook (Labs 2–6)

Operational, step-by-step companion to `README.md`. Where the README tells
you *what* each lab is and how to start it, this runbook walks through
*doing* it: exact commands, what output to expect, how to verify you got
it right, and what to do when something doesn't match.

Run `bash setup_lab_env.sh` first (see `README.md`) and load the PLC
program (`README.md` § 3) before starting Lab 3.

## ⚠️ Before you run this with trainees: one smoke test

**Known issue, currently being fixed:** the upstream OpenPLC_v3 runtime
this module's Docker image builds from has a real bug where Modbus reads
never reflect live-updated register values — confirmed with a minimal
test program (a bare scan counter, no relation to this module's PLC
logic), so it isn't something wrong with `palanca_gen_start.st`. A fix
(pinning the Docker build to an older commit, in `docker/
Dockerfile.openplc`) is in progress but not yet verified end-to-end.

**Run this 15-second check before Lab 3, on a freshly loaded/started PLC
program**, from anywhere with `pymodbus` installed (the setup script
installs it host-wide):

```bash
python3 -c "
from pymodbus.client import ModbusTcpClient
import time
c = ModbusTcpClient('127.0.0.1', port=502, timeout=3)
c.connect()
c.write_coil(address=0, value=True, slave=1)   # GEN1_START_CMD
time.sleep(6)
r = c.read_holding_registers(address=0, count=1, slave=1)
d = c.read_discrete_inputs(address=0, count=1, slave=1)
print('GEN1_FREQUENCY_x100 =', r.registers, ' GEN1_RUNNING =', d.bits)
c.close()
"
```

- **Pass:** `GEN1_FREQUENCY_x100 = [5000]` and `GEN1_RUNNING = [True]`.
  Live values work — proceed with the labs below as written.
- **Fail:** frequency reads `[0]` (running may still correctly show
  `True` — that boolean path works even with the bug). Analog values
  (frequency, voltage, output, everything Lab 3/4 read) will stay frozen
  at 0 for the rest of the session. Rebuild the `openplc` image
  (`docker compose -f docker/docker-compose.yml build openplc`) and
  re-check; if it's still failing, this is an open issue — don't run
  Lab 3/4 as scripted until it's resolved, since trainees will see
  nothing but zeros no matter what they do correctly.

Everything below assumes the **Pass** case.

## Register map reference

From `palanca_gen_start.st`'s header (source of truth — check there if
anything below looks inconsistent):

| Register | Address | Name | Meaning |
|---|---|---|---|
| 40001 | 0x0000 | GEN1_FREQUENCY_x100 | 5000 = 50.00 Hz |
| 40002 | 0x0001 | GEN1_VOLTAGE_x10 | 55000 = 5500.0 V |
| 40003 | 0x0002 | GEN1_OUTPUT_KW | direct kW |
| 40004 | 0x0003 | GEN1_FREQ_SETPOINT | operator target, default 5000 |
| 40008 | 0x0007 | STARTUP_DELAY_SEC | seconds, default 5 |
| 40009 | 0x0008 | FEEDER1_CURRENT_x10 | 2340 = 234.0 A |
| 40011 | 0x000A | SYS_ALARM_WORD | bitmask, 0 = no alarm |

| Coil | Name |
|---|---|
| 0 | GEN1_START_CMD (self-clearing) |
| 1 | GEN1_STOP_CMD (self-clearing) |
| 2 | GEN1_CB_CLOSE_CMD (self-clearing) |
| 3 | GEN1_ALARM_ACK (self-clearing) |

| Discrete input | Name |
|---|---|
| 0 | GEN1_RUNNING |
| 1 | GEN1_FAULT |
| 2 | GEN1_CB_CLOSED |

**The generator start sequence, so Lab 3/4 output makes sense as you
watch it:** writing coil 0 doesn't immediately produce running values.
The PLC ramps frequency/voltage over `STARTUP_DELAY_SEC` (5s default),
then sets `GEN1_RUNNING = True` and snaps frequency/voltage to their
steady-state values. `GEN1_OUTPUT_KW` stays 0 until you *also* write
coil 2 (close the breaker) — that's a separate, deliberate operator step,
not a bug if kW reads 0 right after starting.

## Lab 2 — Asset inventory / Purdue level mapping

Open `~/palanca_labs/module1/palanca_asset_inventory.csv` and fill in
every `L___` cell.

1. For each device, read its **Protocol(s)** and **Physical Location**
   columns — that's usually enough to place it correctly without
   external research.
2. Purdue levels run L0 (physical process) through L4/L5 (enterprise),
   with L3.5 as the DMZ band between OT and IT.
3. Two devices are worth double-checking against each other:
   `SWITCH-MAIN-01`'s note flags it as an **SPOF — no redundant
   switch**; `DMZ-GATEWAY-01`'s name and protocol list (`OPC-UA;
   iptables Firewall`) are a direct hint about which band it sits in.
4. **Deliverable check:** every row has a single specific level (not a
   range), and no two devices that are clearly on different sides of the
   OT/IT boundary (e.g. a field PLC vs. the historian) end up on the same
   level.

## Lab 3 — Modbus/TCP client (`palanca_modbus_read.py`)

This is a trainee template — the three `<<< TASK >>>` blocks need your
edits.

**Task 1** — read `STARTUP_DELAY_SEC` (40008) instead of the default
`GEN1_FREQUENCY_x100` (40001). Register-to-address offset is always
`register - 40001`. Change:
```python
START_REGISTER = 0x0000       # Currently: GEN1_FREQUENCY (reg 40001)
```
to the address for 40008 (see the register map above). Run it:
```bash
python3 ~/palanca_labs/module1/scripts/palanca_modbus_read.py
```
**Verify:** the printed raw value at that address should be `5` (the
default startup delay), not thousands like the frequency register was.

**Task 2** — in `display_register_values()`, add the three conversions
using the formulas already in the comment block (`/100.0` for frequency,
`/10.0` for voltage, no scaling for power). This block only fires when
`START_REGISTER == 0x0000`, so **temporarily set `START_REGISTER` back to
`0x0000`** to test it before moving on — otherwise you won't see your own
new print lines execute at all, and it'll look like nothing happened.

**Verify** (with the generator started per the smoke test above, and
`START_REGISTER = 0x0000`):
```
  Generator 1 Frequency:  50.00 Hz
  Generator 1 Voltage:    5500.0 V
  Generator 1 Output:     0 kW      (or 8500 if you also closed the breaker)
```

**Task 3** — read `SYS_ALARM_WORD` (40011, address `0x000A`), print an
alert line if it's non-zero, and append readings to `~/palanca_labs/
module1/outputs/readings.txt`. `SYS_ALARM_WORD` is normally `0` — to see
the alarm path fire without waiting for a real fault, write the setpoint
above the state machine's own alarm threshold and watch it trip:
```bash
python3 -c "
from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient('127.0.0.1', port=502, timeout=3)
c.connect()
c.write_register(address=3, value=5300, slave=1)   # setpoint > 52.50 Hz trips the alarm
c.close()
"
```
**Verify:** `SYS_ALARM_WORD` reads `0x0001` (overfrequency bit) within a
couple of scans, and `GEN1_FAULT` (discrete input 1) goes `True`. To
clear it and resume: write coil 3 (`GEN1_ALARM_ACK`) `True`, then
re-issue the start command (coil 0) to restart from the top of the state
machine.

Run the extension (no edits needed — it demonstrates the same thresholds
Module 4 formalizes):
```bash
python3 ~/palanca_labs/module1/scripts/palanca_modbus_monitor.py
```
**Verify:** one status line per second, ending in `[OK]` when nothing's
out of bounds, or `<< N ALERT(s) >>` with the specific threshold that
tripped — trigger the same setpoint-above-5250 condition above to see it
in action.

## Lab 4 — OPC-UA exploration

**If ScadaBR is running** (`docker compose -f docker/docker-compose.yml
ps`), use it per `README.md` § 4's data-source setup instead of the steps
below — this section covers the Python fallback path.

**Terminal 1:**
```bash
python3 ~/palanca_labs/module1/scripts/palanca_opcua_server.py
```
**Verify:** a line every 2 seconds like
`[HH:MM:SS] GEN1=RUN Freq=50.00Hz Alarm=0x0000 [OPC-UA nodes updated]`
— if it says `GEN1=STP` and `Freq=0.00Hz` forever, the generator was
never started (re-run the smoke test's coil-0 write), not a Lab 4
problem specifically.

**Terminal 2:**
```bash
python3 ~/palanca_labs/module1/scripts/palanca_opcua_browse.py
```
This is read-only — run it and interpret the output, don't edit it. It
prints five sections in order: security info (Q4), the connection, the
full address space (`PalancaPlatform/ElectricalSystem/{Generator1,
Generator2, Feeder1}` plus `AlarmWord`/`ScanCycleMs`/`LastUpdated`),
Generator1's values by name, and the analysis questions (Q4–Q7) —
answer those as you go; they're deliberately not given here.

**Verify:** `Generator1/Frequency` should read the same 50.00 Hz you saw
in Lab 3 (that's Q5's whole point — same PLC, two different protocols
polling it) and `Generator1/FreqSetpoint` shows as `READ-WRITE`
(everything else is `READ-ONLY`) — that's the setup for Q6.

## Lab 5 — Wireshark protocol capture

The setup script already generated
`~/palanca_labs/module1/pcaps/palanca_baseline.pcap`. Open it with the
lab profile:
```bash
wireshark ~/palanca_labs/module1/pcaps/palanca_baseline.pcap
```
Apply **Palanca-OT** (*Edit → Configuration Profiles*), then use the
filter macros (`Modbus Only`, `OPC-UA Only`, `Modbus Writes`, `FC03 Read
Holding`, `From/To PLC`, `OT Subnet Only`) to work through the worksheet.

**The exact packet numbers, verified against this file** (deterministic —
the generator's only randomness is sub-second timestamp jitter, which
doesn't change packet order or count, so these numbers are the same every
time the script runs):

| Worksheet callout | Packet # |
|---|---|
| FC 0x03 Read Holding Registers (HMI → PLC) | **1** |
| FC 0x01 Read Coils (HMI → PLC) | **3** |
| FC 0x03 Response *with alarm word active* | **104** |
| FC 0x10 Write Multiple Registers (ENG-WS → PLC) | **77** |
| FC 0x7F anomalous function code | **139** |

147 packets total. If your own file's numbers differ from this table,
regenerate it (`python3 ~/palanca_labs/module1/scripts/
generate_baseline_pcap.py`) — a stale or hand-edited capture is the only
way these would drift, since the generator itself is deterministic in
packet order.

**Verify:** packet 104's FC03 response should decode with the last
register (SYS_ALARM_WORD) equal to `1`, not `0` — that's the "alarm
active" callout; every other FC03 response in the file should show `0`
there.

## Lab 6 — Network topology documentation

```bash
drawio ~/palanca_labs/module1/topology/palanca_topology_base.xml
```
Using the asset inventory (Lab 2) and the register map above, add:
- Device names and IP addresses (from the CSV) on each node already
  placed in the base diagram.
- Purdue level bands as background rectangles — reuse your Lab 2
  answers so the two deliverables agree with each other.
- Protocol labels on each connection (Modbus/TCP, OPC-UA, HART, SNMP —
  from the CSV's Protocol(s) column).
- A VLAN boundary box around the OT subnet, and an SPOF annotation on
  `SWITCH-MAIN-01` (the CSV already flags why).

**Deliverable check:** every device from the Lab 2 CSV appears exactly
once, its Purdue level band matches what you wrote in Lab 2, and the
single-switch SPOF is visibly annotated, not just implied.

> **Lab 1** isn't backed by a script in this folder — check with your
> instructor for that exercise's materials.

## Troubleshooting

See `README.md`'s Troubleshooting section for environment-level issues
(port conflicts, ScadaBR not starting, import errors). Lab-specific
issues not covered there:

**Lab 3/4 values are all zero no matter what I do** — run the smoke test
at the top of this runbook first. If it fails, this is the known OpenPLC
runtime issue, not something wrong with your script edits.

**Lab 3 Task 2's conversion lines never print** — check
`START_REGISTER` is back to `0x0000`; the conversion block is
conditional on that (see the Task 2 note above).

**Lab 4: `Generator1/Frequency` shows 0 but Lab 3 showed 50.00 Hz** —
the OPC-UA server (Terminal 1) polls Modbus itself every 2 seconds; give
it a couple of seconds after starting the generator, or check Terminal
1's own status line first — if IT shows 0, the problem is upstream
(Modbus), not the OPC-UA layer.

**Lab 5: packet numbers don't match the table above** — see the note
under Lab 5; regenerate the pcap rather than trusting a stale file.

## Deliverables checklist

- [ ] Lab 2: completed asset inventory CSV, every `L___` filled in
- [ ] Lab 3: edited `palanca_modbus_read.py` (all three tasks) +
      `outputs/readings.txt` showing at least one alarm-active line
- [ ] Lab 4: Q4–Q7 answered (verbally, in a worksheet, or wherever your
      instructor collects them)
- [ ] Lab 5: worksheet callouts identified using the table above
- [ ] Lab 6: annotated topology diagram, consistent with the Lab 2 CSV
