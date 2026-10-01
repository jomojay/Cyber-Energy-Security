#!/usr/bin/env python3
"""
DAY 4 - Statistical anomaly detection with Z-scores   (Module 4 Lab Run Book, Day 4)

Goal: find the 3 anomalies hidden in captures/palanca_anomalies.pcap.

  1. Load the anomaly capture and compute the SAME features as on Day 3.
  2. For every window and feature:    z = (value - baseline mean) / baseline std
  3. Flag the window if |z| > THRESHOLD (start with 3.0).
  4. Save the flagged windows to results/my_day4_flagged.csv and hand them in.

Run:      python3 workbook/day4_zscore.py
          python3 workbook/day4_zscore.py captures/assessment/palanca_anomalies.pcap   (Day 7: any capture)
Compare:  ./otlab detect zscore anomalies
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
import pandas as pd  # noqa: E402
from otkit.load import load_packets  # noqa: E402

CAPTURE = ARGS[0] if ARGS else "captures/palanca_anomalies.pcap"
BASELINE = "results/my_baseline.json"      # made by day3_baseline.py
THRESHOLD = 3.0
MIN_STD = 1.0   # a feature that never changed has std 0 -> dividing by 0! Use at least this much.
OUTPUT = "results/my_day4_flagged.csv"
if ARGS:   # another capture (Day 7): keep your Day 4 hand-in, write a separate file
    OUTPUT = f"results/my_day4_flagged_{os.path.basename(os.path.dirname(CAPTURE))}_{os.path.splitext(os.path.basename(CAPTURE))[0]}.csv"

if not os.path.exists(BASELINE):
    sys.exit(f"{BASELINE} not found - finish and run workbook/day3_baseline.py first (Day 3 makes the baseline).")
with open(BASELINE) as f:
    baseline = json.load(f)
WINDOW_SECONDS = baseline["window_minutes"] * 60


def window_features(pkts):
    """Same features as Day 3 - packets, avg_payload, fc_XX counts - one row per window."""
    pkts = pkts.copy()
    pkts["window"] = (pkts["rel"] // WINDOW_SECONDS).astype(int)
    feats = pd.DataFrame({
        "packets": pkts.groupby("window").size(),
        "avg_payload": pkts[pkts["payload"] > 0].groupby("window")["payload"].mean(),
    })
    req = pkts[pkts["mb_request"] & (pkts["mb_fc"] >= 0)]
    fc = req.groupby(["window", "mb_fc"]).size().unstack(fill_value=0)
    fc.columns = [f"fc_{int(c):02d}" for c in fc.columns]
    feats = feats.join(fc).fillna(0)
    # A new feature that the Day 3 baseline does not know about is interesting too - keep it, with 0 in the baseline.
    last = pkts["rel"].iloc[-1] - feats.index[-1] * WINDOW_SECONDS
    return feats.iloc[:-1] if last < 0.9 * WINDOW_SECONDS else feats


pkts = load_packets(CAPTURE)
features = window_features(pkts)
print(f"{len(features)} windows to check")

# ---------------------------------------------------------------------------
# Z-scores
# ---------------------------------------------------------------------------
zscores = pd.DataFrame(index=features.index)
for column in features.columns:
    stats = baseline["features"].get(column, {"mean": 0.0, "std": 0.0})  # unknown feature: normal = never happens
    # ---- TODO 1: z-score of one feature column ----
    # HINT: (features[column] - stats["mean"]) / max(stats["std"], MIN_STD)
    raise NotImplementedError("TODO 1 in day4_zscore.py: z-score of one feature column - see the HINT above, write your code, then delete this line")

# ---- TODO 2: flag windows ----
# HINT: take the absolute value (.abs()), then the largest value in each row (.max(axis=1)),
#       and compare it with THRESHOLD. Also record WHICH feature was largest (.idxmax(axis=1)).
raise NotImplementedError("TODO 2 in day4_zscore.py: flag windows - see the HINT above, write your code, then delete this line")

result = pd.DataFrame({
    "window": features.index,
    "start_seconds": features.index * WINDOW_SECONDS,
    "max_abs_z": max_abs_z.round(2),
    "top_feature": top_feature,
})
result = result[flagged.values]
print(f"\n{len(result)} window(s) flagged with |z| > {THRESHOLD}:\n")
for _, r in result.iterrows():
    w = int(r["window"])
    print(f"  window {w:>3}  ({r['start_seconds']:>7.0f} s)  max |z| = {r['max_abs_z']:>6.1f}  because of {r['top_feature']}"
          f" = {features.at[w, r['top_feature']]:g} (normal mean {baseline['features'].get(r['top_feature'], {}).get('mean', 0):.1f})")

os.makedirs("results", exist_ok=True)
result.to_csv(OUTPUT, index=False)
print(f"\nSaved {OUTPUT} - this is what you hand in.")
print("Your instructor grades it with:  ./otlab grade anomalies", OUTPUT)

# For your accuracy report:
#  - Try THRESHOLD = 2.5, 3.5, 4.0. How many windows are flagged each time?
#  - For every flagged window, open that time range in Wireshark (View > Time Display Format >
#    Seconds Since Beginning of Capture, then filter  frame.time_relative >= START && frame.time_relative < START+300)
#    and decide: real anomaly or a normal-but-busy period?
