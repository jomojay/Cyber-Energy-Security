# Module 4 — OT Traffic Analysis Lab

Everything for the 7-day Module 4 lab (Wireshark for industrial protocols, Python-based anomaly and
attack detection) on the Palanca 5.5 kV/11 kV SCADA network. It's built for trainees who are new to
networking and Python, and it's meant to stay useful on the job afterwards.

**Trainees, start here:** [`docs/TRAINEE_GUIDE.md`](docs/TRAINEE_GUIDE.md) (day by day, copy-paste commands)
and [`docs/FIELD_GUIDE.html`](docs/FIELD_GUIDE.html) (one-page cheat sheet).
**Instructors:** [`instructor-only/INSTRUCTOR_GUIDE.md`](instructor-only/INSTRUCTOR_GUIDE.md).

## Quick start

```bash
./setup.sh          # < 1 min: libraries (if missing) + all captures + Wireshark profile. No sudo.
./otlab doctor      # checks everything
./otlab             # menu of every tool
```

## What needs live infrastructure vs. what doesn't

- **Days 1–2 (Wireshark basics, protocol deep dive):** live capture against the **existing Module 2 lab**
  (Docker `palanca-lab`, or the Module 3 stack). `./otlab live activity` adds the OPC UA sessions and
  Modbus writes that lab doesn't generate on its own, and `./otlab live capture` records the traffic.
- **Days 3–6 (baseline, statistical detection, ML detection, attack challenge):** the **synthetic 24-hour
  captures** generated here, so every trainee works from *identical*, gradable data.

## The captures (`./setup.sh`)

| File | Day | Contents |
|---|---|---|
| `captures/palanca_baseline_24h.pcap` | 3 | 24 h of normal traffic: Table 4.1's flows, with the protocol mix (by bytes) from the Module 4 text (~1.04M packets, ~125 MB, fully decodable in Wireshark with no expert warnings) |
| `captures/palanca_anomalies.pcap` | 4–5 | baseline + 3 injected anomalies (write burst, volume spike, new source) |
| `captures/palanca_attack_challenge.pcap` | 6 | baseline + the 5 Table 4.3 attacks in random order, timing, sources and targets |
| `captures/instructor-only/anomalies_ground_truth.csv` | 4–5 | **instructor only**: when/what, incl. 5-minute window numbers |
| `captures/instructor-only/attack_answer_key.csv` | 6 | **instructor only**: time, source, evidence, Wireshark filter per attack |

```bash
./setup.sh --seed 12345              # re-create an earlier set exactly (byte-identical)
./setup.sh --seed 12345 --no-keys    # trainee copy of the instructor's captures, without answer keys
./setup.sh --assessment              # Day 7: fresh captures with events at random times
./setup.sh --hours 6                 # smaller captures for slow machines / demos
```

The three original generator scripts still work with the same arguments, e.g.
`python3 baseline_pcap_generator.py --hours 24 -o baseline.pcap`.

## The toolkit: `./otlab`

| Command | Lab day | What it gives you |
|---|---|---|
| `./otlab wireshark install` / `open <cap>` | all | **Palanca-OT** Wireshark profile: OT colouring, one-click filter buttons, Unit/FC/Register columns |
| `./otlab live status` / `activity` / `capture` | 1–2 | lab health, realistic operator traffic, one-command capture |
| `./otlab summary <cap>` | 1–3 | protocol mix, hosts (flags unknown ones), timeline, conversations |
| `./otlab map <cap>` | 2 | Purdue-layered communication diagram with polling intervals (+ draw.io/Mermaid export) |
| `./otlab explain <cap> --first write` | 2 | a Modbus/TCP frame explained byte by byte (MBAP + PDU) |
| `./otlab baseline` | 3 | per-window features, mean/std/percentiles, HTML report |
| `./otlab detect zscore anomalies` | 4 | Z-score detector, flagged windows, charts |
| `./otlab detect ml anomalies --sweep` | 5 | Isolation Forest, side-by-side comparison with Z-score, contamination sweep |
| `./otlab hunt attack` | 6 | the 5 signature rules, with evidence, filters, "what it means / what to do" |
| `./otlab grade anomalies\|attacks <csv>` | 4, 6 | instructor scoring (TPR/FPR, x/5) |
| `./otlab profile learn <cap>` | job | draft a site profile from your own plant's known-good traffic |
| `./otlab selftest` | — | end-to-end check that every planted event is detectable |

Every analysis command writes CSVs and a self-contained **HTML report** to `results/`. The reports work
offline and can be attached to deliverables.

`workbook/` has complete, commented detection scripts for Days 3–6. Trainees run them, read through how
each step works, and change them (thresholds, features) for their reports. `templates/` has a report
template for every deliverable.

## Layout

```
Module_4-traffic-lab/
├── setup.sh, otlab, requirements.txt
├── *_pcap_generator.py        original entry points (now wrappers)
├── otkit/                     toolkit source (loader, features, detectors, hunter, reports, simulator)
├── profiles/                  site profiles (synthetic Palanca, live Docker lab)
├── wireshark/Palanca-OT/      Wireshark profile
├── live/                      activity generator that runs inside eng-ws-01
├── workbook/                  trainee detection scripts, complete and commented (Days 3-6)
├── templates/                 deliverable report templates
├── docs/                      TRAINEE_GUIDE.md, FIELD_GUIDE.html
├── instructor-only/           solutions + instructor guide  ← remove before handing out
├── captures/                  generated (git-ignored)
└── results/                   your outputs (git-ignored)
```

## Requirements

Python 3.8+ with numpy, pandas, matplotlib, scikit-learn (`setup.sh` installs them into `.venv/` if
missing). Wireshark/tshark for the Wireshark parts. Docker plus the Module 2 lab for Days 1–2 only.
