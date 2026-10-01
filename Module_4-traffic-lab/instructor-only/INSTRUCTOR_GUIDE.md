# Module 4 — Instructor Guide

> **Remove this folder (`instructor-only/`) and `captures/instructor-only/` before you hand the lab
> folder to trainees.** They contain the finished workbook solutions and the answer keys.

## 1. What is in the package

| Path | For | What it is |
|---|---|---|
| `setup.sh` | everyone | installs libraries if needed, generates captures, installs the Wireshark profile |
| `./otlab` | everyone | the toolkit: one command with a menu (`./otlab`) |
| `otkit/` | — | toolkit source (Python) |
| `baseline_/anomaly_/attack_pcap_generator.py` | instructor | same names and arguments as before, now thin wrappers around `otkit/sim/` |
| `wireshark/Palanca-OT/` | trainees | Wireshark profile: OT colouring rules, filter buttons, Unit/FC/Register columns |
| `live/palanca_activity.py` | Days 1–2 | runs inside `eng-ws-01` to add OPC UA sessions, FC06/FC16 writes, HTTP |
| `profiles/palanca.json` | everyone | site profile: assets, approved writers, thresholds (synthetic captures) |
| `profiles/palanca_live_lab.json` | Days 1–2 | same, for the Module 2/3 Docker lab's device map |
| `workbook/` | trainees | Day 3–6 starter scripts with guided TODOs |
| `templates/` | trainees | report templates for every deliverable |
| `docs/TRAINEE_GUIDE.md` | trainees | day-by-day walkthrough |
| `docs/FIELD_GUIDE.html` | trainees | one-page cheat sheet (filters, FCs, signatures, safety) |
| `instructor-only/solutions/` | you | complete workbook scripts |
| `instructor-only/make_workbook.py` | you | rebuilds `workbook/` from the solutions |

## 2. What changed compared with the original generator scripts (and why)

The original scripts had problems that would have hit beginners hard:

| Problem in the original | Effect in class | Now |
|---|---|---|
| Every packet in a TCP flow reused sequence number 1 | Wireshark marked ~99% of packets as **TCP Retransmission** and decoded only **28 of ~6,000** as Modbus, so `modbus` filters showed almost nothing | real handshakes, sequence/ack numbers, request **and** response |
| `Ether()` without addresses | scapy ARP-resolved MACs from the **instructor's own network** (broadcast MACs, instructor's NIC MAC, warnings, slow) | fixed per-device MACs (`02:50:4c:…`) |
| OPC UA / SNMP payloads were placeholder text | "Malformed packet", no `opcua`/`snmp` decode | valid OPC UA binary (Hello, OpenSecureChannel, Publish) and SNMPv2c |
| FC16 had no byte count/values | malformed write in the attack capture | valid FC16 |
| Timestamps started at 1970-01-01 | confusing dates | capture starts 2026-03-02 00:00 UTC (Wireshark's default *seconds since start* column is unchanged) |
| "PLC polls all RTUs every 2 s" polled one random RTU | irregular intervals, wrong Day 2/3 picture | every device every 2 s, round-trip |
| All connections opened at second 0 | window 0 always a false positive | capture starts mid-conversation, like a real SPAN capture |
| 24 h generation took ~4 minutes | — | the full set (3 captures) takes well under a minute |
| No seed | a lost file could not be recreated | `--seed`: byte-identical captures on any machine |

The anomaly and attack **concepts are unchanged** (write burst, volume spike, new source; the five Table 4.3
attacks). The attacks are now more realistic (the scanner gets SYN/ACK and RST replies; enumeration triggers
`0x83 Illegal Data Address` exceptions; the upload is segmented TPKT/COTP; the ARP spoof repeats every 2 s).
Attacker IPs and targets are randomised per run as well as the order.

## 3. Before Day 1

```bash
./setup.sh                     # prints the seed - write it down
./otlab selftest               # ~20 s: proves detectors find everything planted in a fresh 6 h capture
./otlab doctor
```

**Giving trainees identical data** (required for fair grading), pick one:

* copy `captures/*.pcap` (3 × ~125 MB) to them, **or**
* give them the seed: they run `./setup.sh --seed <seed> --no-keys` and get byte-identical files, with no answer keys.

`--no-keys` keeps honest trainees honest. A determined trainee who knows the seed could regenerate
the keys with the generator, so for graded work prefer copying the files and keep the seed private.

Check the live lab for Days 1–2: `./otlab live status`.

## 4. Day-by-day notes

### Day 1–2 (live lab)
* Module 2's `traffic-gen` only sends FC03 reads, and nothing talks OPC UA. **Without `./otlab live activity`,
  the Day 1 `opcua` filter, the FC06/16 colouring rule and the Day 2 OPC UA step show nothing.**
  Start it before trainees capture: `./otlab live activity --minutes 60`.
* `./otlab live capture` records on the host bridges (needs the `wireshark` group). Otherwise it falls back to
  capturing inside `eng-ws-01`, which only sees that container's own traffic.
* Trainees capturing from the Wireshark window must select **both** the control (L1) and supervisory (L2)
  bridges (`./otlab live status` lists them). The OPC UA sessions (ENG-WS → HMI-01) never cross L1.
* pyshark (the Run Book's Day 3 example) does **not** work on Python 3.14, the current Kali default:
  `RuntimeError: no current event loop` / `asyncio has no attribute set_child_watcher`. `./otlab doctor` warns
  about it. Point trainees at the workbook's `load_packets()` or `tshark -r <file> -V`.
* Captures in `captures/live/` automatically use `profiles/palanca_live_lab.json` for names.

### Day 3
Reference numbers for your cohort: `./otlab baseline` → `results/day3_baseline_report.html`.
Expected shape: packets/window ≈ 3,606 ± 14, avg payload ≈ 59 B, Modbus reads = 1,200 (6 devices × 150 polls
+ HMI 300), writes ≈ 13 ± 4 (higher on the day shift), ARP ≈ 426. Process traffic uses **only FC03 and FC06**, as in Table 4.1.

**Protocol mix = the Module 4 text's "Key observations" (by bytes).** The capture reproduces both sources:

* **Table 4.1, row by row:** PLC poll 66 B / reply 83 B (~80), HMI reply 123 B (~120), OPC UA PublishResponse
  ~400 B every 5 s, ENG-WS HTTP page ~1,210 B, SNMPv2c every 60 s. SNMP frames average 176 B (135–221 B)
  because the interface-counter GET covers two ports; the health GET (CPU, memory) is ~135–150 B.
* **The text's percentages**, measured in Wireshark's *Statistics › Protocol Hierarchy*, **Percent Bytes** column:

| | Modbus/TCP | OPC UA | HTTP/HTTPS | ARP | SNMP | other |
|---|---|---|---|---|---|---|
| Module 4 text | 50.4 | 21.7 | 9.6 | 6.7 | 1.8 | (9.8) |
| capture, % of bytes | 50.5 | 21.7 | 9.6 | 6.7 | 1.8 | 9.6 |
| capture, % of packets | 67.3 | 10.0 | 1.3 | 11.8 | 1.1 | 8.5 |

To get there without breaking Table 4.1, the capture contains the extra traffic the text describes:

* the historian holds **3 OPC UA subscriptions** (2 process-data + 1 alarms), each publishing every 5 s
* **HMI-01 → SCADA-SVR HTTPS** (the SCADA web interface), refreshed every ~12.5 s; the web server closes each keep-alive connection after 100 requests (~21 min) and the browser reconnects with a resumed TLS session (Client Hello → Server Hello + Change Cipher Spec, no certificate)
* **Windows-style ARP refresh** every 21–41 s per peer (≈ 426 ARP frames per 5 min)
* **SNMPv2c** from NMS: an interface-counter GET plus a health GET per switch per minute
* **"other" ≈ 10 %**: NTP (every host → its switch, 64 s), switch syslog → NMS, and Windows NetBIOS-NS,
  LLMNR (`wpad`) and SSDP discovery broadcasts from HMI-01, SCADA-SVR, ENG-WS, HISTORIAN and NMS

Tell trainees to compare with the **Percent Bytes** column. By packets the numbers look very different, because an
ARP frame is 60 B while an OPC UA publish response is ~400 B. That makes a good Day 3 question: *"Why is ARP 11.8 % of
packets but only 6.7 % of bytes?"* The background traffic also supports security observations: SNMPv2c
community strings in clear text (the text's point), LLMNR/NBNS `wpad` lookups that invite name poisoning, and
SSDP discovery that has no business on a control network.

> The original generator printed "Modbus ~72 %, OPC-UA ~21 %". That message was wrong and has been removed.

### Day 4 — grading
```bash
./otlab grade anomalies <trainee>/my_day4_flagged.csv          # any CSV with a 'window' column
```
With the default features and |z| > 3 the reference detector finds **3/3** with typically **1–4 false-positive
windows** (busy day-shift write periods, and windows where the random ARP/broadcast chatter clusters). Those false positives are
deliberate teaching material. The trainee workbook's simpler features give similar results.
Answer key: `captures/instructor-only/anomalies_ground_truth.csv` (columns include the 5-minute window numbers).

### Day 5
Release the ground truth after Day 4 grading so trainees can use `--truth`. At contamination 0.02 the
Isolation Forest (default features: packets, avg_payload, modbus_reads,
modbus_writes, the same as the workbook) catches 3 of 3 with ~6 false positives on every seed tested. **Lowering** contamination loses true
detections before false ones, because IF can't score beyond its training range (explained in the
Day 5 report). That's a good "statistical vs ML" discussion point.

### Day 6 — grading
```bash
./otlab grade attacks <trainee>/my_day6_findings.csv           # needs attack_type + time_seconds columns
```
Matching is by attack type and time (±120 s, `--tolerance` to change). Common names such as `recon`,
`mitm`, `unauthorized_write` are accepted. Answer key: `captures/instructor-only/attack_answer_key.csv`
(includes the source MAC, the evidence and the exact Wireshark filter for each attack).

### Day 7 — assessment
```bash
./setup.sh --assessment         # or: ./otlab generate --assessment
```
Writes fresh captures with the events at **random** times to `captures/assessment/` and keys to
`captures/instructor-only/assessment/`. Give trainees the pcaps only.

Trainees run their own scripts on the new files without editing them. The output goes to separate files,
so their Day 4/6 hand-ins are kept:

```bash
python3 workbook/day4_zscore.py     captures/assessment/palanca_anomalies.pcap
#   -> results/my_day4_flagged_assessment_palanca_anomalies.csv
python3 workbook/day6_signatures.py captures/assessment/palanca_attack_challenge.pcap
#   -> results/my_day6_findings_assessment_palanca_attack_challenge.csv
```

Grading: `./otlab grade` uses the **assessment** answer key automatically when the submitted file name contains
`assessment`, and prints the key it used. Check that line. For a renamed file, pass the key yourself:

```bash
./otlab grade anomalies <trainee>/my_day4_flagged_assessment_palanca_anomalies.csv
./otlab grade attacks   <trainee>/my_day6_findings_assessment_palanca_attack_challenge.csv
./otlab grade attacks   <file>.csv --truth captures/instructor-only/assessment/attack_answer_key.csv
```

The number of windows used for the false-positive rate comes from the `generation.json` next to the key, so
shorter `--hours` captures are scored correctly.

## 5. Policy decision for you: the toolkit can "solve" Days 4 and 6

`./otlab detect` and `./otlab hunt` produce exactly the Day 4 and Day 6 answers. They're there because
beginners need a reference to check against, and because this is the tool they'll use at work. Options:

1. **Keep them** (recommended) and grade on the *trainee's own script* (`workbook/…`) plus the *evidence and
   explanation* in the report. Screenshots from Wireshark and "what would you do next" can't be copied from the tool.
2. For a stricter Day 6, delete `otkit/hunt.py` from trainee copies until the report is submitted.
   Every other command keeps working. `./otlab hunt` will just fail.

## 6. Customising

* Change a solution, then `python3 instructor-only/make_workbook.py` to rebuild the starters.
* Thresholds, approved writers and asset names live in `profiles/palanca.json`.
* The traffic model is in `otkit/sim/baseline.py`; anomalies and attacks are in `otkit/sim/inject.py`.
