#!/usr/bin/env python3
"""
DAY 3 - Baseline construction                         (Module 4 Lab Run Book, Day 3)

Goal: describe what NORMAL Palanca traffic looks like, in numbers.

  1. Load captures/palanca_baseline_24h.pcap
  2. Cut it into 5-minute windows. For each window calculate:
        - packet count
        - average payload size
        - Modbus function-code distribution (how many FC03, FC06, ... requests)
  3. For every feature calculate mean, standard deviation and percentiles.
     That is your baseline. Save it to results/my_baseline.json.

Run it from the Module 4 folder:     python3 workbook/day3_baseline.py
Check your numbers against:          ./otlab baseline
"""
import json
import os
import sys

LAB = os.path.dirname(os.path.abspath(__file__))            # find the Module 4 folder, wherever this script is run from
while not os.path.isdir(os.path.join(LAB, "otkit")):
    LAB = os.path.dirname(LAB)
VENV = os.path.join(LAB, ".venv")                              # if setup.sh installed the libraries there, use them
if os.path.exists(os.path.join(VENV, "bin", "python")) and os.path.realpath(sys.prefix) != os.path.realpath(VENV):
    os.execv(os.path.join(VENV, "bin", "python"), [os.path.join(VENV, "bin", "python")] + sys.argv)
ARGS = [os.path.abspath(a) for a in sys.argv[1:]]              # a capture file given on the command line (Day 7)
sys.path.insert(0, LAB)
os.chdir(LAB)                                                  # so "captures/..." and "results/..." always work
from otkit.load import load_packets  # noqa: E402  fast pcap -> table loader (see otkit/load.py for the columns)

CAPTURE = "captures/palanca_baseline_24h.pcap"
WINDOW_SECONDS = 5 * 60
OUTPUT = "results/my_baseline.json"

# ---------------------------------------------------------------------------
# Step 1 - load the capture.
# The runbook shows pyshark:  cap = pyshark.FileCapture(CAPTURE)
# pyshark works (on Python 3.13 or older), but runs the whole Wireshark dissector on all
# ~1,040,000 packets (that takes a long time). load_packets() reads the same file in seconds and
# gives you a pandas DataFrame: one row per packet, one column per field.
# ---------------------------------------------------------------------------
pkts = load_packets(CAPTURE)
print(f"Loaded {len(pkts):,} packets")
print(pkts[["no", "rel", "ip_src", "ip_dst", "app", "payload", "mb_fc"]].head())

# ---------------------------------------------------------------------------
# Step 2 - put every packet into a 5-minute window.
# 'rel' = seconds since the first packet. Window 0 = 0-299 s, window 1 = 300-599 s ...
# ---------------------------------------------------------------------------
# ---- window number for every packet ----
# HINT: integer-divide the 'rel' column by WINDOW_SECONDS and store it in a new column called "window".
pkts["window"] = (pkts["rel"] // WINDOW_SECONDS).astype(int)

# Feature 1: packet count per window
# ---- packets per window ----
# HINT: group the rows by "window" and count them:  pkts.groupby("window").size()
packet_count = pkts.groupby("window").size()

# Feature 2: average payload size per window (only packets that carry data, i.e. payload > 0)
# ---- average payload per window ----
# HINT: keep rows with pkts["payload"] > 0, then groupby("window")["payload"].mean()
with_data = pkts[pkts["payload"] > 0]
avg_payload = with_data.groupby("window")["payload"].mean()

# Feature 3: Modbus function-code distribution per window.
# Only count REQUESTS (mb_request is True) with a real function code (mb_fc >= 0).
# ---- function-code counts per window ----
# HINT: filter the Modbus requests, then  .groupby(["window", "mb_fc"]).size().unstack(fill_value=0)
#       gives one column per function code.
modbus_requests = pkts[pkts["mb_request"] & (pkts["mb_fc"] >= 0)]
fc_table = modbus_requests.groupby(["window", "mb_fc"]).size().unstack(fill_value=0)
fc_table.columns = [f"fc_{int(c):02d}" for c in fc_table.columns]

features = fc_table.copy()
features.insert(0, "avg_payload", avg_payload)
features.insert(0, "packets", packet_count)
features = features.fillna(0)

# The very last window may be only partly filled (the capture ends mid-window). Drop it if so.
last_window_seconds = pkts["rel"].iloc[-1] - features.index[-1] * WINDOW_SECONDS
if last_window_seconds < 0.9 * WINDOW_SECONDS:
    features = features.iloc[:-1]

print(f"\n{len(features)} windows. First five:")
print(features.head())

# ---------------------------------------------------------------------------
# Step 3 - the baseline: statistics of every feature over all windows.
# ---------------------------------------------------------------------------
baseline = {"capture": CAPTURE, "window_minutes": WINDOW_SECONDS / 60, "windows": len(features), "features": {}}
for column in features.columns:
    values = features[column]
    # ---- statistics for one feature ----
    # HINT: values.mean(), values.std(ddof=0), values.min(), values.max(), values.quantile(0.95) ...
    baseline["features"][column] = {
        "mean": float(values.mean()),
        "std": float(values.std(ddof=0)),
        "min": float(values.min()),
        "p5": float(values.quantile(0.05)),
        "median": float(values.quantile(0.50)),
        "p95": float(values.quantile(0.95)),
        "max": float(values.max()),
    }

print(f"\n{'feature':<14}{'mean':>12}{'std':>10}{'p5':>10}{'median':>10}{'p95':>10}")
for name, s in baseline["features"].items():
    print(f"{name:<14}{s['mean']:>12.2f}{s['std']:>10.2f}{s['p5']:>10.2f}{s['median']:>10.2f}{s['p95']:>10.2f}")

os.makedirs("results", exist_ok=True)
with open(OUTPUT, "w") as f:
    json.dump(baseline, f, indent=2)
features.to_csv("results/my_baseline_windows.csv")
print(f"\nSaved {OUTPUT} and results/my_baseline_windows.csv")

# Questions for your baseline report:
#  - Which feature varies the most (biggest std compared with its mean)? Why?
#  - Look at fc_06 across the day (results/my_baseline_windows.csv). Is it the same at 03:00 and 14:00?
#  - Which Modbus function codes appear at all? Which never appear?
