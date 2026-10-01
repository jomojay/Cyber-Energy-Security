#!/usr/bin/env python3
"""
DAY 5 - Machine-learning detection with Isolation Forest   (Module 4 Lab Run Book, Day 5)

  1. Train an IsolationForest on the Day 3 BASELINE features (normal traffic only).
  2. Score the Day 4 anomaly capture's features with the trained model.
  3. Compare with your Day 4 Z-score results, then tune 'contamination'.

Run:      python3 workbook/day5_isolation_forest.py
Compare:  ./otlab detect ml anomalies --sweep
"""
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
import joblib  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import IsolationForest  # noqa: E402
from otkit.load import load_packets  # noqa: E402

TRAIN_CAPTURE = "captures/palanca_baseline_24h.pcap"
TEST_CAPTURE = "captures/palanca_anomalies.pcap"
DAY4_RESULT = "results/my_day4_flagged.csv"
WINDOW_SECONDS = 300
CONTAMINATION = 0.02
FEATURES = ["packets", "avg_payload", "fc_03", "fc_06"]   # try adding/removing features!


def window_features(pkts):
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
    for col in FEATURES:            # make sure every feature exists, even if it never happened
        if col not in feats:
            feats[col] = 0
    last = pkts["rel"].iloc[-1] - feats.index[-1] * WINDOW_SECONDS
    return feats.iloc[:-1] if last < 0.9 * WINDOW_SECONDS else feats


train = window_features(load_packets(TRAIN_CAPTURE))
test = window_features(load_packets(TEST_CAPTURE))
print(f"training windows: {len(train)}   test windows: {len(test)}   features: {FEATURES}")

# ---------------------------------------------------------------------------
# Train on NORMAL traffic only
# ---------------------------------------------------------------------------
# >>> SOLUTION: create and fit the model
# HINT: model = IsolationForest(contamination=CONTAMINATION, random_state=42)
#       model.fit(train[FEATURES])
model = IsolationForest(contamination=CONTAMINATION, random_state=42)
model.fit(train[FEATURES])
# <<<

# ---------------------------------------------------------------------------
# Score the anomaly capture:  predict() gives -1 for "anomaly", +1 for "normal"
# ---------------------------------------------------------------------------
# >>> SOLUTION: predict and score
# HINT: model.predict(test[FEATURES]) == -1  gives True for flagged windows.
#       model.decision_function(test[FEATURES]) gives a score: the lower, the stranger.
ml_flagged = model.predict(test[FEATURES]) == -1
scores = model.decision_function(test[FEATURES])
# <<<

ml = pd.DataFrame({"window": test.index, "score": scores.round(3), "ml_flag": ml_flagged})
ml_windows = set(ml.loc[ml["ml_flag"], "window"])
print(f"\nIsolation Forest flagged {len(ml_windows)} window(s): {sorted(ml_windows)}")

# ---------------------------------------------------------------------------
# Compare with Day 4
# ---------------------------------------------------------------------------
z_windows = set(pd.read_csv(DAY4_RESULT)["window"]) if os.path.exists(DAY4_RESULT) else set()
if not z_windows:
    print(f"(no {DAY4_RESULT} found - run day4_zscore.py first to compare)")
# >>> SOLUTION: set comparison
# HINT: use Python set operations:  a & b (both),  a - b (only in a),  b - a (only in b)
both = z_windows & ml_windows
only_z = z_windows - ml_windows
only_ml = ml_windows - z_windows
# <<<
print(f"  flagged by BOTH detectors : {sorted(both)}")
print(f"  only by Z-score           : {sorted(only_z)}")
print(f"  only by Isolation Forest  : {sorted(only_ml)}")

os.makedirs("results", exist_ok=True)
ml.to_csv("results/my_day5_ml_scores.csv", index=False)
ml[ml["ml_flag"]].to_csv("results/my_day5_flagged.csv", index=False)
joblib.dump(model, "results/my_day5_model.joblib")
print("\nSaved results/my_day5_flagged.csv, results/my_day5_ml_scores.csv and the trained model results/my_day5_model.joblib")

# ---------------------------------------------------------------------------
# Tuning: how does contamination change the number of alarms?
# ---------------------------------------------------------------------------
print("\ncontamination -> windows flagged")
for c in [0.005, 0.01, 0.02, 0.05]:
    m = IsolationForest(contamination=c, random_state=42).fit(train[FEATURES])
    print(f"   {c:<6} -> {int((m.predict(test[FEATURES]) == -1).sum())}")

# For your comparison report:
#  - Which anomalies did each detector find? Which did it miss? Why might that be?
#  - Lower contamination = fewer alarms. Does it also start MISSING real anomalies?
#  - Which detector's alarm would you rather explain to a control-room operator, and why?
