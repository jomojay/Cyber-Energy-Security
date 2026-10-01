# Module 4 — OT Traffic Analysis: Trainee Guide

This guide walks you through all seven lab days, one step at a time. You do **not** need to be a
programmer. Every command below can be copied and pasted.

The **Lab Run Book** (the Word document) says *what* you need to deliver each day.
This guide shows you *how*, using the lab's toolkit, **otlab**.

> **Keep open while you work:** `docs/FIELD_GUIDE.html` (double-click it). It's a one-page cheat sheet with
> every filter, every Modbus function code, and all five attack signatures.

---

## 0. Before Day 1 (10 minutes)

### Open a terminal in the Module 4 folder

```bash
cd ~/Cyber-Energy-Security/Module_4-traffic-lab      # adjust if your copy is somewhere else
```

Every command in this guide is run from this folder.

### Check your machine

```bash
./otlab doctor
```

You want to see `[OK]` lines. `[WARN]` lines only matter for the day they mention. If the capture
files are missing, do what your instructor told you: either copy the files they give you into
`captures/`, or run the command they give you, which looks like this:

```bash
./setup.sh --seed 123456 --no-keys        # builds exactly the same captures as your instructor's
```

### Install the Wireshark profile (once)

```bash
./otlab wireshark install
```

In Wireshark, click **Profile:** in the bottom-right corner and choose **Palanca-OT**. That gives you:

| What | Where | Why |
|---|---|---|
| Colouring rules | the packet list | Modbus **writes** in purple, **exceptions** orange, **SYN** yellow, **ARP spoofing** dark red |
| Filter buttons | just above the packet list | one click: *Modbus, Writes, Unapproved writes, SYN scan, ARP spoof, Big to PLC …* |
| Extra columns | packet list | **Unit**, **FC** (function code) and **Register** for every Modbus packet |

To open a capture straight into this profile: `./otlab wireshark open baseline` (or `anomalies`, `attack`, or any file).

### Words you will meet

| Word | Meaning |
|---|---|
| **pcap / capture** | a file that holds recorded network packets |
| **Master / client** | the device that asks (HMI, PLC-MAIN-01 polling RTUs) |
| **Slave / server** | the device that answers (PLC, RTU, relay) |
| **Function code (FC)** | the "verb" of a Modbus message: FC03 = read registers, FC06 = write one register … |
| **Register** | a numbered 16-bit memory cell in a PLC (a temperature, a setpoint …) |
| **Window** | a slice of time (here 5 minutes). We count things per window. |
| **Baseline** | numbers describing what *normal* looks like |
| **Z-score** | how many "normal wobbles" (standard deviations) a value is away from normal |

### Where your results go

Every otlab command writes into `results/`: CSV tables, charts, and an **HTML report** you can open in a
browser (`xdg-open results/<file>.html`) and attach to your deliverables.

---

## Day 1 — Wireshark basics & live capture

**Goal:** capture live traffic from the Module 2 lab and use OT display filters.

1. **Is the lab running?**
   ```bash
   ./otlab live status
   ```
   All containers should show `[OK]`. If not: `cd ../Module_2_Lab_Setup && ./setup.sh`, then come back.

2. **Make the plant busy.** The lab only polls registers by itself. This adds operators and engineers:
   OPC UA sessions, Modbus writes (FC06/FC16) and web requests.
   ```bash
   ./otlab live activity --minutes 25
   ```
   To see what it did, with timestamps: `./otlab live activity --log`.

3. **Capture for 15–20 minutes.**
   ```bash
   ./otlab live capture --minutes 15
   ```
   The file is saved in `captures/live/`. (Prefer the Wireshark window? `./otlab live status` prints the
   interface names to capture on. Select **both** the `control (L1)` and the `supervisory (L2)` interface
   (Ctrl+click). Modbus polling is on L1, but the OPC UA sessions only cross L2. With L1 alone, the `opcua`
   filter shows nothing.)

4. **Open it and apply each filter.** Record how many packets each one shows: the status bar at the
   bottom says *Displayed: N*.
   ```bash
   ./otlab wireshark open captures/live/<your file>.pcapng
   ```

   | Filter | What it shows | Displayed |
   |---|---|---|
   | `modbus` | decoded Modbus messages | |
   | `opcua` | decoded OPC UA messages | |
   | `tcp.port==502` | everything on the Modbus port, including TCP handshakes | |
   | `tcp.port==4840` | everything on the OPC UA port | |

   *Why do `modbus` and `tcp.port==502` give different numbers?* (Hint: not every packet on port 502
   carries a Modbus message.)

5. **Make your own colouring rule for writes.** View → Coloring Rules → **+** →
   Name `Modbus writes`, Filter `modbus.func_code in {6,16}`, pick a background colour → drag it to the
   top → OK. (The Palanca-OT profile already has one, so compare yours with it.)

6. **Quick overview**, useful for your report:
   ```bash
   ./otlab summary captures/live/<your file>.pcapng
   ```

**Deliverable:** annotated capture report: screenshots of each filter + the filter table above + your colouring rule.

---

## Day 2 — Protocol deep dive

**Goal:** read a Modbus frame byte by byte, find an OPC UA session, draw who polls whom.

1. **Decode a Modbus frame.** In Wireshark, click a Modbus *Query* packet and expand
   **Modbus/TCP** in the middle pane. Then compare with:
   ```bash
   ./otlab explain captures/live/<your file>.pcapng --first read       # first read request
   ./otlab explain captures/live/<your file>.pcapng --first response   # its answer
   ./otlab explain captures/live/<your file>.pcapng --first write      # first write
   ./otlab explain captures/live/<your file>.pcapng --frame 123        # any packet number
   ```
   For your report, identify: **Transaction ID, Protocol ID, Length, Unit ID, Function Code, data**.
   Check: the response has the *same* Transaction ID as its request.

2. **OPC UA session establishment.** Filter `opcua`. Find this sequence and screenshot it:
   `Hello` → `Acknowledge` → `OpenSecureChannel` → `CreateSession` → `ActivateSession`.
   Then find a **publish/subscribe** exchange: `CreateSubscription`, then repeated `PublishRequest` /
   `PublishResponse`. (No OPC UA at all? Step 2 on Day 1 wasn't running during your capture. Start it
   and capture again.)

3. **Communication diagram.**
   ```bash
   ./otlab map captures/live/<your file>.pcapng
   ```
   You get a diagram (`results/map_*.png`), a table of every conversation with its polling interval,
   and a `.mmd` file you can import into draw.io (*Arrange → Insert → Advanced → Mermaid*) to edit.
   Check it in Wireshark too: **Statistics → Conversations** (IPv4 tab) and **Statistics → I/O Graphs**.

**Deliverable:** protocol analysis report with a frame breakdown, OPC UA screenshots and the communication diagram.

---

## Day 3 — Baseline construction

**Goal:** turn 24 hours of normal traffic into numbers: the baseline.

From here on you use the prepared captures in `captures/`, and everyone has the same data.

1. **Look at it first.** `./otlab summary baseline` and `./otlab map baseline`.
   Notice how regular everything is: every 1 s, every 2 s, every 5 s.
   Then open it in Wireshark: **Statistics → Protocol Hierarchy**. Compare the **Percent Bytes** column with the
   percentages in the Module 4 text (Modbus 50.4 %, OPC UA 21.7 %, HTTP/HTTPS 9.6 %, ARP 6.7 %, SNMP 1.8 %).
   Now look at **Percent Packets**. Why is ARP so much bigger by packets than by bytes?
   What are NTP, NBNS, LLMNR and SSDP, and should they be on a control network?

2. **Write your baseline script.** Open `workbook/day3_baseline.py` in a text editor (e.g. `mousepad` or
   VS Code). Read it top to bottom, then run it:
   ```bash
   python3 workbook/day3_baseline.py
   ```
   It stops at **TODO 1** with a message. Read the HINT above that line, write the code, delete the
   `raise NotImplementedError(...)` line, and run again. Repeat until it finishes.

3. **Check your numbers** against the reference tool:
   ```bash
   ./otlab baseline
   ```
   The means and stds for `packets`, `avg_payload` and `fc_03`/`fc_06` should match yours.
   Open `results/day3_baseline_report.html` for charts.

> The runbook shows `pyshark.FileCapture(...)`. pyshark decodes every one of the ~1,040,000 packets
> through Wireshark, which takes a long time, and it **does not work on Python 3.14** (Kali's current
> Python; `./otlab doctor` tells you if yours is affected). The workbook uses `load_packets()`, which
> reads the same file in seconds on any Python. To see what pyshark would show you for one packet, ask
> Wireshark's command-line version directly:
> `tshark -r captures/palanca_baseline_24h.pcap -c 3 -V | less`

**Deliverable:** baseline report: mean, std and percentiles per feature (your script's output + the HTML report).

---

## Day 4 — Statistical anomaly detection (Z-score)

**Goal:** find the 3 anomalies in `captures/palanca_anomalies.pcap`.

1. Complete and run `workbook/day4_zscore.py` (same TODO method). It needs `results/my_baseline.json` from Day 3.
2. Compare with the reference:
   ```bash
   ./otlab detect zscore anomalies
   ./otlab detect zscore anomalies --threshold 2.5      # try other thresholds
   ```
3. **Investigate every flagged window in Wireshark.** A window number *W* starts at *W × 300* seconds.
   Filter, for example for window 72:
   `frame.time_relative >= 21600 && frame.time_relative < 21900`
   Then use the filter buttons (*Writes*, *Modbus* …). What is different about this window?
4. **Hand in** `results/my_day4_flagged.csv` (it must keep its `window` column). Your instructor
   scores it and tells you your true positive and false positive rate.

**Deliverable:** your Python detection script + accuracy report.

---

## Day 5 — Machine learning detection (Isolation Forest)

1. Complete and run `workbook/day5_isolation_forest.py`. It trains on the **baseline** (normal only)
   and scores the **anomaly** capture, then compares with your Day 4 results.
2. Reference and tuning:
   ```bash
   ./otlab detect ml anomalies
   ./otlab detect ml anomalies --sweep                      # several contamination values
   ./otlab detect ml anomalies --contamination 0.01
   ```
   Once your instructor has released the ground truth, add `--truth <file>` to see exact scores.
3. Read the report (`results/day5_ml_flagged_windows_report.html`). The orange box explains why
   lowering *contamination* can make the model **miss** real anomalies. Put that in your comparison.

**Deliverable:** trained model (`results/my_day5_model.joblib`) + comparison: statistical vs ML.

---

## Day 6 — Attack detection challenge

**Goal:** find all **5** planted attacks in `captures/palanca_attack_challenge.pcap`.

1. **Wireshark first.** `./otlab wireshark open attack`, then click each filter button in turn:

   | Attack (Table 4.3) | Button | Filter |
   |---|---|---|
   | Reconnaissance (SYN scan) | *SYN scan* | `tcp.flags.syn==1 && tcp.flags.ack==0` |
   | Register enumeration | *Big reads* / *Exceptions* | `modbus.func_code in {1,2,3,4} && modbus.reference_num > 99` |
   | Unauthorised write | *Unapproved writes* | `modbus.func_code in {5,6,15,16} && tcp.dstport == 502 && !(ip.src in {192.168.2.10,192.168.2.20})` |
   | PLC program upload | *Big to PLC* | `ip.dst in {192.168.1.10,192.168.1.11} && frame.len > 1000` |
   | ARP spoofing / MITM | *ARP spoof* | `arp.duplicate-address-detected` |

   Some filters also match *normal* traffic (e.g. ordinary connections start with a SYN). Your job is to
   tell the attack apart from normal. For every hit, record **attack type, time, source IP, evidence**.
   Use `templates/day6_attack_report_template.md`.

2. **Automate it.** Complete `workbook/day6_signatures.py`. It should find the same 5 events.

3. **Check yourself:**
   ```bash
   ./otlab hunt attack
   ```
   Open `results/day6_findings_report.html`: every finding comes with its evidence, a Wireshark filter,
   *what it means* and *what to do*. **Confirm each one in Wireshark yourself.** You must be able to
   explain it.

**Deliverable:** attack investigation report (all 5 attacks with evidence).

---

## Day 7 — Assessment

You will run your detection script live against a **fresh capture** your instructor gives you
(in `captures/assessment/`). You don't need to edit the script. Give it the file name:

```bash
python3 workbook/day4_zscore.py      captures/assessment/palanca_anomalies.pcap
python3 workbook/day6_signatures.py  captures/assessment/palanca_attack_challenge.pcap
```

The results go to **new** files, so your Day 4 and Day 6 hand-ins are not overwritten:
`results/my_day4_flagged_assessment_palanca_anomalies.csv` and
`results/my_day6_findings_assessment_palanca_attack_challenge.csv`. Hand those two in.

Practise now on the Day 4/6 captures (`python3 workbook/day4_zscore.py captures/palanca_anomalies.pcap`):
the Day 4 script still needs your `results/my_baseline.json` from Day 3.

---

## Using this on the job

otlab isn't only for this lab. On a real site:

* **Capture passively only.** Use a SPAN/mirror port or a network TAP. **Never** run scans or send
  packets to live control equipment without written approval. See the safety box in `docs/FIELD_GUIDE.html`.
* `./otlab summary <capture>` and `./otlab map <capture>` give you a quick picture of an unknown OT
  network: who is there, who polls whom, how often.
* `./otlab profile learn <capture> -o profiles/mysite.json` drafts a *site profile* (assets, Modbus
  masters and writers) from a known-good capture. **Review and correct it**, then
  `./otlab hunt <capture> --profile profiles/mysite.json` to check new captures against it.
* `./otlab baseline <good capture>` then `./otlab detect zscore <new capture> --baseline results/day3_baseline.json`
  compares a new day against a known-good day.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Capture not found` | Run commands from the Module 4 folder. `ls captures/` shows the files. |
| `No module named ...` | `./setup.sh` (it installs the libraries into `.venv/`). `./otlab` and the workbook scripts use `.venv/` automatically. |
| `results/my_baseline.json not found` | Day 4 needs your Day 3 baseline: finish and run `python3 workbook/day3_baseline.py` first. |
| `live capture`: *the live lab is not running* | `cd ../Module_2_Lab_Setup && ./setup.sh`, then `./otlab live status`. |
| `map`: *no IP conversations in this capture* | The capture is empty or only ARP: the lab wasn't running, or you captured on the wrong interface. |
| pyshark: `no current event loop` / `set_child_watcher` | pyshark does not work on Python 3.14. Use `load_packets()` (workbook) or `tshark -r <file> -V`. |
| `live capture` says permission denied | `sudo usermod -aG wireshark $USER`, then **log out and in again**. |
| Wireshark shows no Palanca-OT profile | `./otlab wireshark install`, then restart Wireshark. |
| No OPC UA / no writes in my live capture | `./otlab live activity` must be running *while* you capture. |
| `live activity --log` says *cryptography is not installed* | Harmless. The lab's OPC UA runs without encryption, which is why you can read it in Wireshark. |
| My script says `NotImplementedError: TODO …` | That's expected: fill in that TODO (read the HINT just above it). |
| The first run of a command is slow | It reads the ~125 MB capture once, then caches it (`captures/.otlab_cache/`). |
| Timestamps don't match Wireshark | In Wireshark: View → Time Display Format → *Seconds Since Beginning of Capture*. |
