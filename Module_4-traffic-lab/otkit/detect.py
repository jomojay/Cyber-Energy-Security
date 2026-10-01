"""
Days 4 and 5: anomaly detectors that work on per-window features.

Z-score (Day 4):   z = (value - mean) / std      flag the window if |z| > threshold
Isolation Forest (Day 5): learn what normal windows look like, flag the odd ones out.
"""
import numpy as np
import pandas as pd

# A feature that never changed in the baseline has std = 0, and then ANY change gives an infinite z-score.
# We use a small minimum std instead (1 packet, 1 byte, 1 request ...). It is printed in every report.
MIN_STD = 1.0


def zscore_detect(features, baseline, feature_names, threshold=3.0, min_std=MIN_STD):
    z = pd.DataFrame(index=features.index)
    for c in feature_names:
        st = baseline["features"][c]
        z[c] = (features[c] - st["mean"]) / max(st["std"], min_std)
    absz = z.abs()
    out = features[["start_s", "start_utc"]].copy()
    out["max_abs_z"] = absz.max(axis=1).round(2)
    out["top_feature"] = absz.idxmax(axis=1)
    out["flagged"] = out["max_abs_z"] > threshold
    out["why"] = [
        ", ".join(f"{c} {features.at[i, c]:g} (z={z.at[i, c]:+.1f})" for c in feature_names if abs(z.at[i, c]) > threshold)
        for i in out.index
    ]
    return out, z.round(2)


def train_isolation_forest(train_features, feature_names, contamination=0.02, seed=42):
    from sklearn.ensemble import IsolationForest
    model = IsolationForest(contamination=contamination, random_state=seed, n_estimators=200)
    model.fit(train_features[feature_names].values)
    return model


def isolation_forest_detect(model, features, feature_names):
    X = features[feature_names].values
    out = features[["start_s", "start_utc"]].copy()
    out["score"] = np.round(model.decision_function(X), 4)  # below 0 = more anomalous than the training cut-off
    out["flagged"] = model.predict(X) == -1
    return out


def load_truth(path):
    """Ground truth CSV from anomaly_pcap_generator.py (start_time / end_time in seconds from capture start)."""
    gt = pd.read_csv(path)
    gt = gt.rename(columns={"approx_time_seconds": "start_time", "end_time_seconds": "end_time",
                            "attack_type": "anomaly_type"})
    return gt


def evaluate(flags, truth, window_minutes):
    """Compare flagged windows with the ground truth.

    Event level: an injected anomaly counts as DETECTED if at least one of the
    windows it touches was flagged.  Window level: a flagged window that does
    not touch any anomaly is a FALSE POSITIVE.
    """
    w = window_minutes * 60
    bad = {}
    for _, r in truth.iterrows():
        for k in range(int(r["start_time"] // w), int(r["end_time"] // w) + 1):
            bad.setdefault(k, []).append(r["anomaly_type"])
    flagged = set(flags.index[flags["flagged"]])
    events = []
    for _, r in truth.iterrows():
        wins = set(range(int(r["start_time"] // w), int(r["end_time"] // w) + 1))
        events.append({"anomaly": r["anomaly_type"], "windows": sorted(wins), "detected": bool(wins & flagged)})
    normal = [i for i in flags.index if i not in bad]
    fp = sorted(i for i in flagged if i not in bad)
    tp_windows = sorted(i for i in flagged if i in bad)
    detected = sum(e["detected"] for e in events)
    return {
        "events": events,
        "detected": detected,
        "total_events": len(events),
        "tpr": detected / len(events) if events else 0.0,
        "false_positive_windows": fp,
        "fp": len(fp),
        "normal_windows": len(normal),
        "fpr": len(fp) / len(normal) if normal else 0.0,
        "precision": len(tp_windows) / len(flagged) if flagged else 0.0,
        "flagged": len(flagged),
    }
