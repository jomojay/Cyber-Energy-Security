"""
Day 3: turn packets into per-window features, and summarise normal
behaviour as a baseline (mean / std / percentiles per feature).

A "window" is a fixed slice of time (5 minutes by default). Each window
becomes one row of numbers. Detectors then ask: does this window look
like the normal windows did?
"""
import datetime as dt
import json

import numpy as np
import pandas as pd

READ_FCS = (1, 2, 3, 4)
WRITE_FCS = (5, 6, 15, 16)

FEATURE_HELP = {
    "packets": "Total packets in the window",
    "bytes": "Total bytes (frame lengths) in the window",
    "avg_payload": "Average TCP/UDP payload size in bytes",
    "modbus_requests": "Modbus queries (packets sent TO port 502)",
    "modbus_reads": "Modbus read requests (FC 01/02/03/04)",
    "modbus_writes": "Modbus write requests (FC 05/06/15/16)",
    "modbus_exceptions": "Modbus exception responses (device said 'error')",
    "fc_03": "FC 03 Read Holding Registers requests",
    "fc_06": "FC 06 Write Single Register requests",
    "fc_16": "FC 16 Write Multiple Registers requests",
    "fc_other": "Modbus requests with any other function code",
    "unique_src": "Number of different source IP addresses",
    "unique_pairs": "Number of different source->destination IP pairs",
    "tcp_syn": "New TCP connection attempts (SYN without ACK)",
    "arp": "ARP packets",
    "max_frame": "Largest frame in the window (bytes)",
}

# The features the detectors use by default (all numbers a beginner can explain).
DEFAULT_DETECT_FEATURES = ["packets", "avg_payload", "modbus_reads", "modbus_writes", "unique_src", "tcp_syn"]
# Isolation Forest is thrown off by near-constant count features (unique_src, tcp_syn): a single normal window
# where they tick up once is "easier to isolate" than a real anomaly. It is steadier on these four.
DEFAULT_ML_FEATURES = ["packets", "avg_payload", "modbus_reads", "modbus_writes"]


def window_features(pkts, window_minutes=5.0, keep_partial=False, origin=None):
    """One row per window. Returns a DataFrame indexed by window number."""
    w = window_minutes * 60.0
    t0 = pkts["time"].iloc[0] if origin is None else origin
    win = ((pkts["time"] - t0) // w).astype(int)
    g = pkts.groupby(win, observed=True)

    req = pkts["mb_request"] & (pkts["mb_fc"] >= 0)
    fc = pkts["mb_fc"]

    def count(mask):
        return mask.groupby(win).sum()

    ip = pkts["ip_src"].astype(str)
    has_ip = ip != ""
    pair = ip + ">" + pkts["ip_dst"].astype(str)
    carries = pkts["payload"] > 0

    f = pd.DataFrame({
        "packets": g.size(),
        "bytes": g["len"].sum(),
        "avg_payload": pkts["payload"].where(carries).groupby(win).mean(),
        "modbus_requests": count(req),
        "modbus_reads": count(req & fc.isin(READ_FCS)),
        "modbus_writes": count(req & fc.isin(WRITE_FCS)),
        "modbus_exceptions": count(pkts["mb_exception"] > 0),
        "fc_03": count(req & (fc == 3)),
        "fc_06": count(req & (fc == 6)),
        "fc_16": count(req & (fc == 16)),
        "fc_other": count(req & ~fc.isin((3, 6, 16))),
        "unique_src": ip.where(has_ip).groupby(win).nunique(),
        "unique_pairs": pair.where(has_ip).groupby(win).nunique(),
        "tcp_syn": count(pkts["syn"] & ~pkts["ack"]),
        "arp": count(pkts["l4"] == "ARP"),
        "max_frame": g["len"].max(),
    })
    full = pd.RangeIndex(0, int(win.max()) + 1)
    f = f.reindex(full).fillna(0)
    f["avg_payload"] = f["avg_payload"].round(2)
    f.index.name = "window"
    f.insert(0, "start_s", f.index * w)
    f.insert(1, "start_utc", [dt.datetime.fromtimestamp(t0 + s, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
                              for s in f["start_s"]])
    # Drop the trailing window if it is only partly covered - a half-empty window looks "anomalous" for no reason.
    last_cover = (pkts["time"].iloc[-1] - t0) - f["start_s"].iloc[-1]
    if not keep_partial and len(f) > 1 and last_cover < 0.9 * w:
        f = f.iloc[:-1]
    return f


def numeric_columns(features):
    return [c for c in features.columns if c not in ("start_s", "start_utc")]


def build_baseline(pkts, features, source, window_minutes):
    stats = {}
    for c in numeric_columns(features):
        x = features[c].astype(float)
        stats[c] = {
            "mean": round(float(x.mean()), 4), "std": round(float(x.std(ddof=0)), 4),
            "min": float(x.min()), "p5": float(np.percentile(x, 5)), "p25": float(np.percentile(x, 25)),
            "median": float(np.percentile(x, 50)), "p75": float(np.percentile(x, 75)),
            "p95": float(np.percentile(x, 95)), "p99": float(np.percentile(x, 99)), "max": float(x.max()),
        }
    ips = pkts["ip_src"].astype(str)
    mb_req = pkts[pkts["mb_request"] & (pkts["mb_fc"] >= 0)]
    writes = mb_req[mb_req["mb_fc"].isin(WRITE_FCS)]
    return {
        "source_capture": source,
        "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "window_minutes": window_minutes,
        "windows": int(len(features)),
        "packets": int(len(pkts)),
        "duration_hours": round(float(pkts["rel"].iloc[-1]) / 3600, 2),
        "features": stats,
        "known_ips": sorted(set(ips[ips != ""]) | set(pkts["ip_dst"].astype(str)[pkts["ip_dst"].astype(str) != ""])),
        "modbus_masters": sorted(set(mb_req["ip_src"].astype(str))),
        "modbus_writers": sorted(set(writes["ip_src"].astype(str))),
        "modbus_function_codes": {str(int(k)): int(v) for k, v in mb_req["mb_fc"].value_counts().sort_index().items()},
        "highest_register_seen": int(mb_req["mb_addr"].max() + max(0, mb_req.loc[mb_req["mb_addr"].idxmax(), "mb_qty"] - 1))
        if len(mb_req) else -1,
        "protocol_mix_percent": {str(k): round(float(v) * 100, 2)
                                 for k, v in pkts["app"].value_counts(normalize=True).items() if v > 0},
        "protocol_mix_bytes_percent": {str(k): round(float(v) * 100, 2) for k, v in
                                       (pkts.groupby(pkts["app"].astype(str))["len"].sum() / pkts["len"].sum())
                                       .sort_values(ascending=False).items() if v > 0},
    }


def save_baseline(baseline, path):
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)


def load_baseline(path):
    with open(path) as f:
        return json.load(f)
