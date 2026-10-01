"""
High-level capture generation used by setup.sh, `otlab generate` and the
three stand-alone *_pcap_generator.py scripts.
"""
import csv
import random

from . import packets as P
from .baseline import build_baseline
from .inject import ANOMALIES, ATTACKS, attacker_pool, fresh_net, utc


def new_seed():
    return random.SystemRandom().randint(1, 2**31 - 1)


def generate_baseline(output, profile, hours=24.0, seed=None, start=None):
    seed = seed if seed is not None else new_seed()
    recs = build_baseline(profile, hours=hours, seed=seed, start=start)
    n = P.write_pcap(output, recs)
    return dict(packets=n, seed=seed, start=recs[0][0] if recs else None, end=recs[-1][0] if recs else None)


def _span(records):
    if not records:
        raise SystemExit("Baseline pcap is empty - generate one with baseline_pcap_generator.py first.")
    return records[0][0], records[-1][0] - records[0][0]


def _place(rng, n, duration, randomize, fixed, min_gap_frac=0.08):
    """Pick n capture positions (fractions). Fixed spots + a little jitter, or fully random."""
    if not randomize:
        return [f + rng.uniform(-0.03, 0.03) for f in fixed]
    while True:
        fr = sorted(rng.uniform(0.06, 0.94) for _ in range(n))
        if all(b - a >= min_gap_frac for a, b in zip(fr, fr[1:])):
            rng.shuffle(fr)
            return fr


def inject_anomalies(baseline_path, output, truth_csv, profile, seed=None, randomize=False, window_minutes=5):
    seed = seed if seed is not None else new_seed()
    rng = random.Random(seed)
    base = P.read_pcap_records(baseline_path)
    start, duration = _span(base)
    net = fresh_net(profile, seed + 1)
    fracs = _place(rng, len(ANOMALIES), duration, randomize, [0.25, 0.50, 0.75])
    rows = [fn(net, start + duration * f, profile) for fn, f in zip(ANOMALIES, fracs)]
    combined = sorted(base + net.out, key=lambda r: r[0])
    n = P.write_pcap(output, combined)
    w = window_minutes * 60
    rows.sort(key=lambda r: r["start"])
    with open(truth_csv, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["anomaly_type", "start_time", "end_time", "description", "start_utc", "end_utc",
                     f"first_window_{window_minutes}min", f"last_window_{window_minutes}min", "src_ip", "dst_ip"])
        for r in rows:
            s, e = r["start"] - start, r["end"] - start
            wr.writerow([r["anomaly_type"], f"{s:.2f}", f"{e:.2f}", r["description"], utc(r["start"]), utc(r["end"]),
                         int(s // w), int(e // w), r["src_ip"], r["dst_ip"]])
    return dict(packets=n, injected=len(net.out), seed=seed, rows=rows, capture_start=start)


def inject_attacks(baseline_path, output, key_csv, profile, seed=None, randomize=False):
    seed = seed if seed is not None else new_seed()
    rng = random.Random(seed)
    base = P.read_pcap_records(baseline_path)
    start, duration = _span(base)
    net = fresh_net(profile, seed + 1)
    attacks = ATTACKS[:]
    rng.shuffle(attacks)  # different order every run: no "the answer is always at minute 12"
    fracs = _place(rng, len(attacks), duration, randomize, [0.15, 0.32, 0.51, 0.68, 0.85])
    attackers = attacker_pool(profile, rng, len(attacks))
    plcs = sorted(profile.plcs)
    field = [a["ip"] for a in profile.assets if a["ip"].startswith("192.168.1.") and a["ip"] not in profile.gateways]
    rows = []
    for fn, f, atk in zip(attacks, fracs, attackers):
        t = start + duration * f
        target = rng.choice(field if fn.__name__ == "attack_recon_scan" else plcs)
        rows.append(fn(net, t, profile, atk, target))
    combined = sorted(base + net.out, key=lambda r: r[0])
    n = P.write_pcap(output, combined)
    rows.sort(key=lambda r: r["start"])
    with open(key_csv, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["attack_type", "approx_time_seconds", "description", "end_time_seconds", "utc_time",
                     "src_ip", "dst_ip", "src_mac", "wireshark_filter"])
        for r in rows:
            wr.writerow([r["attack_type"], f"{r['start'] - start:.2f}", r["evidence"], f"{r['end'] - start:.2f}",
                         utc(r["start"]), r["src_ip"], r["dst_ip"], r.get("src_mac", ""), r["wireshark_filter"]])
    return dict(packets=n, injected=len(net.out), seed=seed, rows=rows, capture_start=start)
