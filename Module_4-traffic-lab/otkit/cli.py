"""
otlab - the Module 4 OT Traffic Analysis toolkit.

Run `./otlab` with no arguments for the menu, or `./otlab <command> -h`
for help on one command.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys

from .profile import LAB_ROOT, load_profile

CAPTURES = os.path.join(LAB_ROOT, "captures")
INSTRUCTOR = os.path.join(CAPTURES, "instructor-only")
RESULTS = os.path.join(LAB_ROOT, "results")
SHORTCUTS = {
    "baseline": "palanca_baseline_24h.pcap",
    "anomalies": "palanca_anomalies.pcap",
    "attack": "palanca_attack_challenge.pcap",
    "challenge": "palanca_attack_challenge.pcap",
}

# ---------------------------------------------------------------------------
# terminal helpers
# ---------------------------------------------------------------------------
_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code, s):
    return f"\033[{code}m{s}\033[0m" if _TTY else s


def title(s):
    print("\n" + _c("1;36", s) + "\n" + _c("36", "-" * len(s)))


def ok(s):
    print(_c("32", "  [OK]   ") + s)


def warn(s):
    print(_c("33", "  [WARN] ") + s)


def bad(s):
    print(_c("31", "  [FAIL] ") + s)


def info(s):
    print("  " + s)


def nxt(*lines):
    print("\n" + _c("1;35", "  NEXT STEP"))
    for line in lines:
        print("   " + line)


def rel(path):
    try:
        r = os.path.relpath(path)
        return r if not r.startswith("../..") else path
    except ValueError:
        return path


def opened(path):
    info(_c("1", "Report: ") + rel(path) + _c("2", "   (open it with:  xdg-open " + rel(path) + ")"))


def resolve_capture(arg, default=None):
    arg = arg or default
    if arg is None:
        raise SystemExit("Please give a capture file (e.g. captures/palanca_baseline_24h.pcap).")
    if arg in SHORTCUTS:
        arg = os.path.join(CAPTURES, SHORTCUTS[arg])
    if not os.path.exists(arg) and os.path.exists(os.path.join(CAPTURES, arg)):
        arg = os.path.join(CAPTURES, arg)
    if not os.path.exists(arg):
        msg = f"Capture not found: {arg}"
        if not os.path.isdir(CAPTURES):
            msg += "\n  The captures/ folder does not exist yet. Ask your instructor, or run:  ./setup.sh"
        else:
            msg += "\n  Available: " + ", ".join(sorted(f for f in os.listdir(CAPTURES) if f.endswith((".pcap", ".pcapng"))))
        raise SystemExit(msg)
    return arg


def site_profile(a, capture=None):
    """--profile if given; the live-lab profile for captures in captures/live/; else the Palanca profile."""
    if getattr(a, "profile", None):
        return load_profile(a.profile)
    if capture and os.sep + "live" + os.sep in os.path.abspath(capture):
        return load_profile(os.path.join(LAB_ROOT, "profiles", "palanca_live_lab.json"))
    return load_profile()


def out_path(args_out, name):
    os.makedirs(RESULTS, exist_ok=True)
    return args_out or os.path.join(RESULTS, name)


def load(path):
    from .load import load_packets
    return load_packets(path)


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def cmd_doctor(a):
    title("otlab doctor - checking your lab machine")
    problems = 0
    if sys.version_info >= (3, 8):
        ok(f"Python {sys.version.split()[0]}")
    else:
        bad("Python 3.8 or newer is required"); problems += 1
    for mod, why, required in [("numpy", "maths", True), ("pandas", "tables", True),
                               ("matplotlib", "charts", True), ("sklearn", "Isolation Forest (Day 5)", True),
                               ("scapy", "optional: packet crafting in your own scripts", False),
                               ("pyshark", "optional: the runbook's Day 3 example", False)]:
        try:
            __import__(mod)
            import asyncio
            if mod == "pyshark" and not hasattr(asyncio, "set_child_watcher"):
                warn(f"python module pyshark does not work on Python {sys.version_info[0]}.{sys.version_info[1]} "
                     "(needs 3.13 or older) - use the workbook's load_packets() or tshark instead")
                continue
            ok(f"python module {mod:<10} ({why})")
        except ImportError:
            if required:
                bad(f"python module {mod} missing ({why})  ->  run ./setup.sh again"); problems += 1
            else:
                warn(f"python module {mod} not installed ({why})")
    for tool, why in [("wireshark", "graphical analysis (Days 1, 2, 6)"), ("tshark", "command-line Wireshark"),
                      ("dumpcap", "live capture (Day 1)")]:
        if shutil.which(tool):
            ok(f"{tool:<10} found ({why})")
        else:
            warn(f"{tool} not found ({why})  ->  sudo apt install wireshark tshark")
    try:
        import grp
        if "wireshark" in [grp.getgrgid(g).gr_name for g in os.getgroups()]:
            ok("you are in the 'wireshark' group (can capture without sudo)")
        else:
            warn("not in the 'wireshark' group -> live capture needs:  sudo usermod -aG wireshark $USER  (then log out/in)")
    except Exception:
        pass
    prof = os.path.join(_ws_config_dir(), "profiles", "Palanca-OT")
    if os.path.isdir(prof):
        ok("Wireshark profile 'Palanca-OT' installed")
    else:
        warn("Wireshark profile 'Palanca-OT' not installed  ->  ./otlab wireshark install")
    for f in ("palanca_baseline_24h.pcap", "palanca_anomalies.pcap", "palanca_attack_challenge.pcap"):
        p = os.path.join(CAPTURES, f)
        if os.path.exists(p):
            ok(f"captures/{f} ({os.path.getsize(p) / 1e6:.0f} MB)")
        else:
            warn(f"captures/{f} missing  ->  ./setup.sh   (or ask your instructor for the file)")
    from . import live
    st = live.status()
    if not st.get("error") and st["ok"]:
        ok("Module 2/3 live lab is running (needed for Days 1-2 only)")
    else:
        warn("live Docker lab not running - only needed for Days 1-2: " +
             (st.get("error") or "missing " + ", ".join(st["missing"])) +
             "\n         Start it with:  cd ../Module_2_Lab_Setup && ./setup.sh")
    print()
    if problems:
        bad(f"{problems} problem(s) must be fixed before the lab will work.")
        return 1
    ok("Ready. Warnings above only matter for the lab day they mention.")
    return 0


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

def cmd_generate(a):
    from .sim.generate import generate_baseline, inject_anomalies, inject_attacks, new_seed
    prof = load_profile(a.profile)
    out = os.path.join(CAPTURES, "assessment") if a.assessment else CAPTURES
    keys = os.path.join(INSTRUCTOR, "assessment") if a.assessment else INSTRUCTOR
    os.makedirs(out, exist_ok=True)
    os.makedirs(keys, exist_ok=True)
    seed = a.seed if a.seed is not None else new_seed()
    title(f"Generating {'Day 7 assessment' if a.assessment else 'lab'} captures (seed {seed})")
    base = os.path.join(out, "palanca_baseline_24h.pcap")
    r = generate_baseline(base, prof, hours=a.hours, seed=seed)
    ok(f"[Day 3]   {rel(base)}  ({r['packets']:,} packets, {a.hours:g} h)")
    anom = os.path.join(out, "palanca_anomalies.pcap")
    gt = os.path.join(keys, "anomalies_ground_truth.csv")
    r2 = inject_anomalies(base, anom, gt, prof, seed=seed + 1, randomize=a.assessment)
    ok(f"[Day 4-5] {rel(anom)}  (+{r2['injected']} anomaly packets)")
    atk = os.path.join(out, "palanca_attack_challenge.pcap")
    key = os.path.join(keys, "attack_answer_key.csv")
    r3 = inject_attacks(base, atk, key, prof, seed=seed + 2, randomize=a.assessment)
    ok(f"[Day 6]   {rel(atk)}  (+{r3['injected']} attack packets)")
    with open(os.path.join(keys, "generation.json"), "w") as f:
        json.dump({"seed": seed, "hours": a.hours, "created": dt.datetime.now().isoformat(timespec="seconds"),
                   "regenerate_with": f"./otlab generate --seed {seed} --hours {a.hours:g}"
                                      + (" --assessment" if a.assessment else "")}, f, indent=2)
    info(f"Answer keys (INSTRUCTOR ONLY): {rel(keys)}/")
    info(f"Same captures again later: ./otlab generate --seed {seed}" + (" --assessment" if a.assessment else ""))
    return 0


# ---------------------------------------------------------------------------
# wireshark profile
# ---------------------------------------------------------------------------

def _ws_config_dir():
    return os.environ.get("WIRESHARK_CONFIG_DIR") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "wireshark")


def cmd_wireshark(a):
    src = os.path.join(LAB_ROOT, "wireshark", "Palanca-OT")
    dst = os.path.join(_ws_config_dir(), "profiles", "Palanca-OT")
    if a.action == "install":
        title("Installing the Palanca-OT Wireshark profile")
        if os.path.isdir(dst) and not a.force:
            ok(f"already installed at {dst}   (use --force to overwrite)")
        else:
            os.makedirs(dst, exist_ok=True)
            for f in ("dfilter_buttons", "dfilters", "preferences"):
                shutil.copy(os.path.join(src, f), os.path.join(dst, f))
            # OT colouring rules first, then Wireshark's normal rules so everything else still looks familiar
            rules = open(os.path.join(src, "colorfilters")).read()
            system = "/usr/share/wireshark/colorfilters"
            if os.path.exists(system):
                rules += "".join(l for l in open(system) if l.startswith("@"))
            with open(os.path.join(dst, "colorfilters"), "w") as f:
                f.write(rules)
            ok(f"installed to {dst}")
        info("In Wireshark: click 'Profile:' at the bottom-right corner and choose Palanca-OT")
        info("(or Edit > Configuration Profiles...). You get: OT colouring rules, one-click filter")
        info("buttons (Modbus, Writes, SYN scan, ARP spoof ...), and Unit / FC / Register columns.")
        return 0
    if a.action == "open":
        cap = resolve_capture(a.capture, "baseline")
        if not shutil.which("wireshark"):
            raise SystemExit("Wireshark is not installed:  sudo apt install wireshark")
        if not os.path.isdir(dst):
            cmd_wireshark(argparse.Namespace(action="install", force=False, capture=None))
        subprocess.Popen(["wireshark", "-C", "Palanca-OT", "-r", cap], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        ok(f"Wireshark is opening {rel(cap)} with the Palanca-OT profile (large files take a few seconds).")
        return 0
    if a.action == "filters":
        title("Palanca-OT display filters (copy into the Wireshark filter bar)")
        for line in open(os.path.join(src, "dfilters")):
            name, flt = line.split('" ', 1)
            print(f"  {_c('1', name.strip(chr(34))):<45}  {flt.strip()}")
        return 0


# ---------------------------------------------------------------------------
# live lab
# ---------------------------------------------------------------------------

def cmd_live(a):
    from . import live
    if a.action == "status":
        title("Live lab status (Days 1-2)")
        st = live.status()
        if st.get("error"):
            bad(st["error"]); return 1
        for c in live.EXPECTED:
            (ok if c in st["running"] else bad)(f"container {c}")
        if not st["networks"]:
            bad("no lab networks found (192.168.1.0/24 etc.)  ->  cd ../Module_2_Lab_Setup && ./setup.sh")
        for n in st["networks"]:
            ok(f"{n['zone']:<17} {n['subnet']:<15} capture interface: {_c('1', n['iface'])}")
        if st["networks"]:
            info("Capturing in the Wireshark window? Select BOTH the control (L1) and supervisory (L2) interfaces")
            info("(Ctrl+click): Modbus polling is on L1, but the OPC UA sessions (ENG-WS -> HMI) only cross L2.")
        if st["ok"]:
            nxt("./otlab live activity      (adds OPC UA sessions + Modbus writes to the traffic)",
                "./otlab live capture --minutes 15")
        return 0 if st["ok"] else 1
    if a.action == "activity":
        if a.log:
            print(live.activity_log()); return 0
        title(f"Starting operator/engineer activity inside eng-ws-01 for {a.minutes:g} minutes")
        rc = live.start_activity(a.minutes, follow=a.follow)
        if not a.follow:
            ok("running in the background. What it does, with timestamps:  ./otlab live activity --log")
            nxt(f"./otlab live capture --minutes {min(a.minutes, 15):g}")
        return rc
    if a.action == "capture":
        title("Live capture")
        path = live.capture(a.minutes, a.output, a.where)
        ok(f"saved {rel(path)} ({os.path.getsize(path) / 1e6:.1f} MB)")
        nxt(f"./otlab wireshark open {rel(path)}", f"./otlab summary {rel(path)}", f"./otlab map {rel(path)}")
        return 0


# ---------------------------------------------------------------------------
# summary / map / explain
# ---------------------------------------------------------------------------

def _timeline_fig(pkts, per="1min"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    t = pd.to_datetime(pkts["time"], unit="s", utc=True)
    top = pkts["app"].astype(str).value_counts().index[:6]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    for app in top:
        s = pd.Series(1, index=t[pkts["app"].astype(str) == app]).resample(per).sum()
        ax.plot(s.index, s.values, label=app, lw=1)
    ax.set_ylabel(f"packets per {per}")
    ax.set_yscale("symlog")
    ax.legend(fontsize=8, ncol=6, loc="upper center", bbox_to_anchor=(0.5, 1.18))
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    return fig


def cmd_summary(a):
    from .conversations import conversations, protocol_mix
    from .report import Report
    cap = resolve_capture(a.capture)
    prof = site_profile(a, cap)
    title(f"Summary of {rel(cap)}")
    p = load(cap)
    dur = p["rel"].iloc[-1]
    mix = protocol_mix(p)
    conv = conversations(p)
    hosts = sorted(set(p["ip_src"].astype(str)) - {""})
    unknown = [h for h in hosts if h not in prof.by_ip]
    info(f"{len(p):,} packets over {dur / 3600:.2f} h ({dur:,.0f} s), {len(hosts)} IP hosts, {len(conv)} conversations")
    info("Protocol mix (% of bytes): " + ", ".join(f"{k} {v:.1f}%" for k, v in mix["percent_bytes"].head(6).items()))
    info("             (% of packets): " + ", ".join(f"{k} {v:.1f}%" for k, v in
                                                     mix["percent_packets"].sort_values(ascending=False).head(6).items()))
    mbr = p[p["mb_request"] & (p["mb_fc"] >= 0)]
    if len(mbr):
        info("Modbus function codes (requests): " + ", ".join(f"FC{int(k):02d} x{v}" for k, v in mbr["mb_fc"].value_counts().sort_index().items()))
    if unknown:
        warn("hosts NOT in the site profile: " + ", ".join(unknown[:12]) + (" ..." if len(unknown) > 12 else ""))
    else:
        ok("every host is in the site profile")
    rep = Report(f"Capture summary - {os.path.basename(cap)}", f"{prof.site}")
    rep.cards([("Packets", f"{len(p):,}", ""), ("Duration", f"{dur / 3600:.2f} h", f"{dur:,.0f} s"),
               ("IP hosts", len(hosts), f"{len(unknown)} unknown"), ("Conversations", len(conv), "")])
    rep.h2("Protocol mix")
    rep.table(mix, index=True)
    rep.h2("Traffic over time")
    rep.figure(_timeline_fig(p, "1min" if dur < 6 * 3600 else "5min"))
    rep.h2("Hosts")
    import pandas as pd
    hdf = pd.DataFrame([{"ip": h, "name": prof.name(h), "zone": prof.zone(h),
                         "sent_packets": int((p["ip_src"].astype(str) == h).sum())} for h in hosts])
    rep.table(hdf)
    rep.h2("Conversations (client -> server)")
    rep.table(conv)
    path = out_path(a.output, f"summary_{os.path.splitext(os.path.basename(cap))[0]}.html")
    rep.save(path)
    opened(path)
    return 0


def cmd_map(a):
    from .conversations import conversations, draw_map, mermaid
    from .report import Report, file_to_data_uri
    cap = resolve_capture(a.capture)
    prof = site_profile(a, cap)
    title(f"Communication map of {rel(cap)}")
    p = load(cap)
    conv = conversations(p)
    if conv.empty:
        bad("no IP conversations in this capture, so there is nothing to draw.")
        info("Live capture? Run './otlab live status': the lab must be running, and capture on the lab interfaces.")
        return 1
    stem = os.path.splitext(os.path.basename(cap))[0]
    png = out_path(None, f"map_{stem}.png")
    draw_map(conv, prof, png, title=f"{prof.site} - {os.path.basename(cap)}", min_packets=a.min_packets)
    mmd = out_path(None, f"map_{stem}.mmd")
    with open(mmd, "w") as f:
        f.write(mermaid(conv[conv["packets"] >= a.min_packets], prof))
    csvp = out_path(None, f"conversations_{stem}.csv")
    conv.to_csv(csvp, index=False)
    print()
    print(f"  {'CLIENT':<28} {'->':2} {'SERVER':<28} {'PROTOCOL':<12} {'EVERY':>8} {'PACKETS':>9}  FCs")
    for _, r in conv.head(25).iterrows():
        has_iv = r["interval_s"] is not None and r["interval_s"] == r["interval_s"]
        iv = (f"{r['interval_s']:g}s" if r["regular"] else "on demand") if has_iv else "-"
        print(f"  {prof.label(r['client'])[:28]:<28} -> {prof.label(r['server'])[:28]:<28} {r['protocol']:<12} "
              f"{iv:>8} {r['packets']:>9,}  {r['modbus_fcs']}")
    print()
    ok(f"diagram: {rel(png)}  (background services - NTP, syslog, NetBIOS, LLMNR, SSDP - are left off the picture)")
    ok(f"table:   {rel(csvp)}")
    ok(f"Mermaid: {rel(mmd)}  (draw.io: Arrange > Insert > Advanced > Mermaid, to edit the diagram)")
    rep = Report(f"Communication map - {os.path.basename(cap)}", prof.site)
    rep.callout("Arrows point from the device that STARTS the conversation (the master / client) to the one "
                "that answers (the slave / server). 'every Ns' is the median time between requests: in a "
                "healthy OT network these are very regular.", "info")
    rep.image(file_to_data_uri(png), "communication map")
    rep.h2("All conversations")
    rep.table(conv)
    path = out_path(a.output, f"map_{stem}.html")
    rep.save(path)
    opened(path)
    return 0


def cmd_explain(a):
    from .explain import explain_frame, explain_modbus, get_frame
    if a.hex:
        raw = bytes.fromhex(a.hex.replace(":", " ").replace("0x", ""))
        title("Explaining Modbus/TCP bytes")
        print("\n".join(explain_modbus(raw, is_request=not a.response)))
        return 0
    cap = resolve_capture(a.capture)
    num = a.frame
    if num is None:
        p = load(cap)
        req = p["mb_request"]
        pick = {
            "read": req & p["mb_fc"].isin([1, 2, 3, 4]),
            "response": ~req & p["mb_fc"].isin([1, 2, 3, 4]) & (p["mb_exception"] == 0),
            "write": req & p["mb_fc"].isin([5, 6, 15, 16]),
            "exception": p["mb_exception"] > 0,
            "arp": p["arp_op"] > 0,
            "syn": p["syn"] & ~p["ack"],
        }[a.first]
        hits = p[pick]
        if hits.empty:
            raise SystemExit(f"No '{a.first}' packet in this capture.")
        num = int(hits["no"].iloc[0])
    ts, lt, fr = get_frame(cap, num)
    title(f"Frame {num} of {rel(cap)}   ({len(fr)} bytes, {dt.datetime.fromtimestamp(ts, dt.timezone.utc):%Y-%m-%d %H:%M:%S.%f} UTC)")
    print("\n".join(explain_frame(fr, lt)))
    print(f"\n  Tip: in Wireshark press Ctrl+G and type {num} to jump to this frame and compare.")
    return 0


# ---------------------------------------------------------------------------
# Day 3: baseline
# ---------------------------------------------------------------------------

def _feature_chart(features, cols, flags=None, zthr=None, baseline=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(cols), 1, figsize=(11, 1.9 * len(cols)), sharex=True)
    axes = [axes] if len(cols) == 1 else axes
    x = features["start_s"] / 3600
    for ax, c in zip(axes, cols):
        ax.plot(x, features[c], lw=0.9, color="#0b5cad")
        if baseline:
            st = baseline["features"][c]
            ax.axhline(st["mean"], color="#15803d", lw=0.8, ls="--")
            if zthr:
                from .detect import MIN_STD
                sd = max(st["std"], MIN_STD)
                ax.axhspan(st["mean"] - zthr * sd, st["mean"] + zthr * sd, color="#15803d", alpha=0.08)
        if flags is not None:
            for i in flags.index[flags["flagged"]]:
                ax.axvspan(features.at[i, "start_s"] / 3600, (features.at[i, "start_s"] + 300) / 3600, color="#b3261e", alpha=0.35)
        ax.set_ylabel(c, fontsize=8, rotation=0, ha="right", va="center")
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
    axes[-1].set_xlabel("hours since start of capture")
    fig.tight_layout()
    return fig


def cmd_baseline(a):
    from .features import FEATURE_HELP, build_baseline, numeric_columns, save_baseline, window_features
    from .report import Report
    cap = resolve_capture(a.capture, "baseline")
    title(f"Day 3 - building the baseline from {rel(cap)}")
    p = load(cap)
    feats = window_features(p, a.window)
    bl = build_baseline(p, feats, os.path.basename(cap), a.window)
    jpath = out_path(a.output, "day3_baseline.json")
    save_baseline(bl, jpath)
    csvp = os.path.splitext(jpath)[0] + "_windows.csv"
    feats.to_csv(csvp)
    info(f"{len(p):,} packets -> {len(feats)} windows of {a.window:g} minutes\n")
    print(f"  {'feature':<18} {'mean':>10} {'std':>9} {'p5':>9} {'median':>9} {'p95':>9} {'max':>9}")
    for c in numeric_columns(feats):
        s = bl["features"][c]
        print(f"  {c:<18} {s['mean']:>10.2f} {s['std']:>9.2f} {s['p5']:>9.2f} {s['median']:>9.2f} {s['p95']:>9.2f} {s['max']:>9.2f}")
    print()
    info("Protocol mix, % of bytes:   " + ", ".join(f"{k} {v}%" for k, v in list(bl["protocol_mix_bytes_percent"].items())[:7]))
    info("Protocol mix, % of packets: " + ", ".join(f"{k} {v}%" for k, v in list(bl["protocol_mix_percent"].items())[:7]))
    info("Modbus masters seen: " + ", ".join(load_profile(a.profile).label(x) for x in bl["modbus_masters"]))
    info("Modbus writers seen: " + ", ".join(load_profile(a.profile).label(x) for x in bl["modbus_writers"]))
    ok(f"baseline saved: {rel(jpath)}")
    ok(f"per-window features: {rel(csvp)}")

    import pandas as pd
    rep = Report("Day 3 - Palanca baseline report", f"Source: {os.path.basename(cap)} - {a.window:g}-minute windows")
    rep.cards([("Packets", f"{len(p):,}", ""), ("Duration", f"{bl['duration_hours']} h", ""),
               ("Windows", bl["windows"], f"{a.window:g} min each"),
               ("Modbus writers", len(bl["modbus_writers"]), ", ".join(bl["modbus_writers"]))])
    rep.callout("A baseline describes NORMAL. For every 5-minute window we count things (packets, reads, "
                "writes ...). The mean says what is typical, the standard deviation (std) says how much it "
                "normally wobbles, and the percentiles show the range. Tomorrow's detector compares new "
                "windows against these numbers.", "info")
    rep.h2("Feature statistics")
    stats = pd.DataFrame(bl["features"]).T
    stats.insert(0, "what it measures", [FEATURE_HELP.get(i, "") for i in stats.index])
    rep.table(stats, index=True)
    rep.h2("How each feature moves over the day")
    rep.figure(_feature_chart(feats, ["packets", "avg_payload", "modbus_reads", "modbus_writes", "unique_src", "tcp_syn"],
                              baseline=bl))
    rep.p("Notice modbus_writes: operators change setpoints more during the day shift (06:00-18:00) than at "
          "night. Other features are almost flat - OT traffic is very regular, which is exactly why anomalies stand out.")
    rep.h2("Protocol mix")
    rep.table(pd.DataFrame({"percent_of_bytes": bl["protocol_mix_bytes_percent"],
                            "percent_of_packets": bl["protocol_mix_percent"]}).fillna(0), index=True)
    rep.p("Wireshark shows the same numbers in Statistics > Protocol Hierarchy ('Percent Bytes' and 'Percent Packets'). "
          "The two differ because an ARP frame is 60 bytes while an OPC UA publish response is ~400 bytes: small "
          "frames count a lot by packets and little by bytes.")
    rep.h2("Modbus function codes (requests)")
    from .explain import FUNCTION_CODES
    rep.table(pd.DataFrame([{"FC": k, "name": FUNCTION_CODES.get(int(k), ("?",))[0], "requests": v}
                            for k, v in bl["modbus_function_codes"].items()]))
    path = os.path.splitext(jpath)[0] + "_report.html"
    rep.save(path)
    opened(path)
    nxt(f"./otlab detect zscore anomalies --baseline {rel(jpath)}")
    return 0


# ---------------------------------------------------------------------------
# Days 4-5: detection
# ---------------------------------------------------------------------------

def _truth_path(a):
    if getattr(a, "truth", None):
        return a.truth
    return None


def _print_eval(e, label):
    print(f"\n  {_c('1', label)}: detected {e['detected']}/{e['total_events']} injected anomalies "
          f"(TPR {e['tpr']:.0%}),  {e['fp']} false-positive windows (FPR {e['fpr']:.2%} of {e['normal_windows']} normal windows)")
    for ev in e["events"]:
        (ok if ev["detected"] else bad)(f"{ev['anomaly']:<14} window(s) {ev['windows']}")


def cmd_detect(a):
    from .detect import evaluate, isolation_forest_detect, load_truth, train_isolation_forest, zscore_detect, MIN_STD
    from .features import DEFAULT_DETECT_FEATURES, DEFAULT_ML_FEATURES, build_baseline, load_baseline, window_features
    from .report import Report
    import pandas as pd
    default = DEFAULT_DETECT_FEATURES if a.method == "zscore" else DEFAULT_ML_FEATURES
    feats_list = a.features.split(",") if a.features else default
    cap = resolve_capture(a.capture, "anomalies")

    if a.method == "zscore":
        if not a.baseline or not os.path.exists(a.baseline):
            default = os.path.join(RESULTS, "day3_baseline.json")
            if os.path.exists(default):
                a.baseline = default
            else:
                raise SystemExit("No baseline file. Build one first:  ./otlab baseline")
        bl = load_baseline(a.baseline)
        title(f"Day 4 - Z-score detection on {rel(cap)}  (|z| > {a.threshold:g})")
        p = load(cap)
        feats = window_features(p, bl["window_minutes"])
        flags, z = zscore_detect(feats, bl, feats_list, a.threshold)
        hits = flags[flags["flagged"]]
        info(f"{len(feats)} windows checked with features: {', '.join(feats_list)}")
        info(f"{len(hits)} window(s) flagged:\n")
        for i, r in hits.iterrows():
            print(f"   window {i:>3}  {r['start_utc']} UTC  ({r['start_s']:>7.0f} s)   {r['why']}")
        csvp = out_path(a.output, "day4_flagged_windows.csv")
        out = hits.reset_index()[["window", "start_s", "start_utc", "max_abs_z", "top_feature", "why"]]
        out.to_csv(csvp, index=False)
        allp = os.path.splitext(csvp)[0] + "_all_zscores.csv"
        pd.concat([flags, z.add_prefix("z_")], axis=1).to_csv(allp)
        print()
        ok(f"flagged windows (submit this to your instructor): {rel(csvp)}")
        ok(f"every window's z-scores: {rel(allp)}")
        e = None
        if _truth_path(a):
            e = evaluate(flags, load_truth(a.truth), bl["window_minutes"])
            _print_eval(e, "Accuracy against ground truth")
        rep = Report("Day 4 - Z-score anomaly detection", f"{os.path.basename(cap)}  vs  baseline {os.path.basename(a.baseline)}")
        rep.cards([("Windows checked", len(feats), f"{bl['window_minutes']:g} min each"),
                   ("Flagged", len(hits), f"threshold |z| > {a.threshold:g}")] +
                  ([("Detected", f"{e['detected']}/{e['total_events']}", f"TPR {e['tpr']:.0%}"),
                    ("False positives", e["fp"], f"FPR {e['fpr']:.2%}")] if e else []))
        rep.callout(f"z = (value - baseline mean) / baseline std. |z| > {a.threshold:g} means the window is more than "
                    f"{a.threshold:g} standard deviations away from normal. When a feature never changed in the baseline "
                    f"(std close to 0) we use a minimum std of {MIN_STD:g} so a single extra packet does not count as "
                    f"'infinitely' unusual.", "info")
        rep.h2("Flagged windows")
        rep.table(out)
        rep.h2("Features over time (red = flagged, green band = normal range)")
        rep.figure(_feature_chart(feats, feats_list, flags, a.threshold, bl))
        if e:
            rep.h2("Accuracy")
            rep.table(pd.DataFrame(e["events"]))
        rep.callout("Things to try: raise or lower --threshold and watch true vs false positives change; "
                    "add a feature with --features; ask whether a flagged window could be a normal but busy period.", "tip")
        path = os.path.splitext(csvp)[0] + "_report.html"
        rep.save(path)
        opened(path)
        nxt("./otlab detect ml anomalies --train baseline     (Day 5: compare with machine learning)")
        return 0

    # ---- Day 5: Isolation Forest ----
    train_cap = resolve_capture(a.train, "baseline")
    title(f"Day 5 - Isolation Forest (contamination={a.contamination:g})")
    info(f"training on the NORMAL capture: {rel(train_cap)}")
    tp = load(train_cap)
    tfeats = window_features(tp, a.window)
    model = train_isolation_forest(tfeats, feats_list, a.contamination)
    info(f"scoring: {rel(cap)}")
    p = load(cap)
    feats = window_features(p, a.window)
    res = isolation_forest_detect(model, feats, feats_list)
    hits = res[res["flagged"]]
    for i, r in hits.iterrows():
        vals = ", ".join(f"{c}={feats.at[i, c]:g}" for c in feats_list)
        print(f"   window {i:>3}  {r['start_utc']} UTC  score {r['score']:+.3f}   {vals}")
    try:
        import joblib
        mpath = out_path(None, "day5_isolation_forest.joblib")
        joblib.dump({"model": model, "features": feats_list, "window_minutes": a.window,
                     "contamination": a.contamination}, mpath)
        ok(f"trained model saved: {rel(mpath)}")
    except ImportError:
        pass
    csvp = out_path(a.output, "day5_ml_flagged_windows.csv")
    hits.reset_index().to_csv(csvp, index=False)
    ok(f"flagged windows: {rel(csvp)}")

    # comparison with the z-score detector (same features, baseline built from the training capture)
    bl = build_baseline(tp, tfeats, os.path.basename(train_cap), a.window)
    zflags, _ = zscore_detect(feats, bl, feats_list, a.threshold)
    cmp_df = pd.DataFrame({"start_utc": feats["start_utc"], "zscore": zflags["flagged"], "isolation_forest": res["flagged"],
                           "if_score": res["score"]})
    cmp_df = cmp_df[cmp_df["zscore"] | cmp_df["isolation_forest"]]
    print(f"\n  {'window':>6}  {'start (UTC)':<17} {'Z-score':<8} {'IsoForest':<9}")
    for i, r in cmp_df.iterrows():
        print(f"  {i:>6}  {r['start_utc']:<17} {'FLAG' if r['zscore'] else '-':<8} {'FLAG' if r['isolation_forest'] else '-':<9}")
    evals = {}
    if _truth_path(a):
        truth = load_truth(a.truth)
        evals["Z-score"] = evaluate(zflags, truth, a.window)
        evals["Isolation Forest"] = evaluate(res, truth, a.window)
        for k, e in evals.items():
            _print_eval(e, k)
    sweep = []
    if a.sweep:
        print(f"\n  contamination sweep:")
        truth = load_truth(a.truth) if _truth_path(a) else None
        for c in [0.001, 0.005, 0.01, 0.02, 0.05, 0.1]:
            m = train_isolation_forest(tfeats, feats_list, c)
            r = isolation_forest_detect(m, feats, feats_list)
            row = {"contamination": c, "flagged_windows": int(r["flagged"].sum())}
            if truth is not None:
                e = evaluate(r, truth, a.window)
                row.update(detected=f"{e['detected']}/{e['total_events']}", false_positives=e["fp"])
            sweep.append(row)
            print("   " + "   ".join(f"{k}={v}" for k, v in row.items()))
    rep = Report("Day 5 - Machine learning detection (Isolation Forest)",
                 f"trained on {os.path.basename(train_cap)}, scored {os.path.basename(cap)}")
    rep.cards([("Training windows", len(tfeats), "normal traffic only"), ("Scored windows", len(feats), ""),
               ("IF flagged", int(res["flagged"].sum()), f"contamination {a.contamination:g}"),
               ("Z-score flagged", int(zflags["flagged"].sum()), f"|z| > {a.threshold:g}")])
    rep.callout("Isolation Forest builds many random trees that try to 'isolate' each window. Unusual windows are "
                "isolated in very few splits and get a low score. 'contamination' tells the model what fraction of "
                "the TRAINING data to treat as outliers - it sets the alarm threshold. Lower it to get fewer alarms.", "info")
    rep.h2("Which windows each detector flagged")
    rep.table(cmp_df, index=True)
    if evals:
        rep.h2("Accuracy against ground truth")
        rep.table(pd.DataFrame([{"detector": k, "detected": f"{e['detected']}/{e['total_events']}", "TPR": f"{e['tpr']:.0%}",
                                 "false_positive_windows": e["fp"], "FPR": f"{e['fpr']:.2%}",
                                 "missed": ", ".join(ev["anomaly"] for ev in e["events"] if not ev["detected"]) or "-"}
                                for k, e in evals.items()]))
    if sweep:
        rep.h2("Contamination sweep")
        rep.table(pd.DataFrame(sweep))
    rep.h2("Isolation Forest flags over time")
    rep.figure(_feature_chart(feats, feats_list, res))
    rep.callout("Why lowering contamination can MISS attacks: an Isolation Forest only knows the range of values it "
                "saw in training. A window far outside that range (e.g. 2,800 packets when training never went above "
                "2,600) cannot score as more unusual than the most extreme NORMAL window. So when you lower "
                "contamination, the alarm threshold moves past the anomalies too. The z-score has no such ceiling - "
                "a bigger deviation always gives a bigger z.", "warn")
    rep.callout("Discussion points: Which anomalies does only one detector catch, and why? Z-score looks at each "
                "feature on its own; Isolation Forest looks at combinations. Which is easier to explain to a control "
                "room operator at 3 a.m.?", "tip")
    path = os.path.splitext(csvp)[0] + "_report.html"
    rep.save(path)
    opened(path)
    return 0


# ---------------------------------------------------------------------------
# Day 6: hunt
# ---------------------------------------------------------------------------

SEV_COL = {"CRITICAL": "1;41", "HIGH": "1;31", "MEDIUM": "1;33", "LOW": "1;34", "INFO": "2"}


def cmd_hunt(a):
    from .features import load_baseline
    from .hunt import hunt
    from .report import Report
    import pandas as pd
    cap = resolve_capture(a.capture, "attack")
    prof = site_profile(a, cap)
    bl = load_baseline(a.baseline) if a.baseline and os.path.exists(a.baseline) else None
    title(f"Day 6 - hunting for attack signatures in {rel(cap)}")
    p = load(cap)
    fs = hunt(p, prof, bl)
    core = [f for f in fs if f["core"]]
    extra = [f for f in fs if not f["core"]]
    for n, f in enumerate(core, 1):
        print(f"\n  {_c(SEV_COL[f['severity']], ' ' + f['severity'] + ' ')}  #{n} {_c('1', f['attack_type'])}"
              f"   at {f['time_seconds']:.1f} s ({f['utc_time']} UTC), first packet No. {f['first_packet']}")
        print(f"     {f['evidence']}")
        print(_c("2", f"     Wireshark: {f['wireshark_filter']}"))
    if extra and not a.quiet_extras:
        print("\n  " + _c("1", "Additional observations") + " (context, not separate attacks):")
        for f in extra:
            print(f"   - [{f['severity']}] {f['attack_type']}: {f['evidence']}")
    print()
    kinds = sorted({f["attack_type"] for f in core})
    info(f"{len(core)} signature hit(s) across {len(kinds)} attack type(s): {', '.join(kinds) or 'none'}")
    csvp = out_path(a.output, "day6_findings.csv")
    # reindex, not [...]: a clean capture has no findings, and an empty frame has none of these columns
    pd.DataFrame(fs).reindex(columns=["attack_type", "time_seconds", "utc_time", "src_ip", "dst_ip", "severity",
                                      "rule", "core", "first_packet", "packets", "evidence",
                                      "wireshark_filter"]).to_csv(csvp, index=False)
    ok(f"findings table: {rel(csvp)}")
    rep = Report("Day 6 - Attack investigation report", f"{os.path.basename(cap)} - {prof.site}")
    rep.cards([("Signature hits", len(core), ""), ("Attack types", len(kinds), "of 5 in Table 4.3"),
               ("Packets analysed", f"{len(p):,}", ""), ("Additional observations", len(extra), "")])
    rep.callout("Each finding lists the evidence and the Wireshark filter that shows it. Before you submit, open "
                "the capture in Wireshark, apply each filter, and confirm the evidence with your own eyes - "
                "a tool can be wrong, and you have to be able to explain every finding.", "warn")
    rep.h2("Findings (Module 4, Table 4.3 signatures)")
    if not core:
        rep.callout("No attack signature matched this capture.", "tip")
    for n, f in enumerate(core, 1):
        rep.finding(f, n)
    if extra:
        rep.h2("Additional observations")
        rep.table(pd.DataFrame(extra)[["attack_type", "severity", "time_seconds", "src_ip", "evidence", "wireshark_filter"]])
    path = os.path.splitext(csvp)[0] + "_report.html"
    rep.save(path)
    opened(path)
    return 0


# ---------------------------------------------------------------------------
# instructor: grading
# ---------------------------------------------------------------------------

ALIASES = {
    "recon": "network_reconnaissance", "reconnaissance": "network_reconnaissance", "scan": "network_reconnaissance",
    "port_scan": "network_reconnaissance", "syn_scan": "network_reconnaissance",
    "enumeration": "modbus_register_enumeration", "register_enumeration": "modbus_register_enumeration",
    "unauthorized_write": "unauthorised_write", "write": "unauthorised_write",
    "plc_upload": "plc_program_upload", "program_upload": "plc_program_upload", "upload": "plc_program_upload",
    "arp_spoof": "arp_spoofing_mitm", "arp_spoofing": "arp_spoofing_mitm", "mitm": "arp_spoofing_mitm",
}


def _answer_key(a, name):
    """The answer key for this submission: --truth, else the Day 7 key if the file name says 'assessment'."""
    if a.truth:
        return a.truth
    sub = os.path.basename(a.submission).lower()
    folder = os.path.join(INSTRUCTOR, "assessment") if "assessment" in sub else INSTRUCTOR
    return os.path.join(folder, name)


def cmd_grade(a):
    import pandas as pd
    from .detect import evaluate, load_truth
    if a.what == "anomalies":
        truth = _answer_key(a, "anomalies_ground_truth.csv")
        title(f"Grading anomaly detection: {rel(a.submission)}")
        info(f"answer key: {rel(truth)}")
        sub = pd.read_csv(a.submission)
        wcol = next((c for c in sub.columns if c.lower() in ("window", "window_index", "window_id")), None)
        if wcol is None:
            raise SystemExit("The submission needs a 'window' column (window number, 5-minute windows from capture start).")
        gt = load_truth(truth)
        gen = os.path.join(os.path.dirname(truth), "generation.json")   # written next to the key: capture length
        hours = json.load(open(gen)).get("hours") if os.path.exists(gen) else None
        if a.windows:
            n_windows = int(a.windows)
        elif hours:
            n_windows = int(hours * 60 / a.window)
        else:
            n_windows = max(int(gt["end_time"].max() // (a.window * 60) + 1), int(24 * 60 / a.window))
        n_windows = max(n_windows, int(sub[wcol].max()) + 1)
        flags = pd.DataFrame({"flagged": False}, index=range(n_windows))
        flags.loc[sub[wcol].astype(int).tolist(), "flagged"] = True
        e = evaluate(flags, gt, a.window)
        _print_eval(e, "Result")
        info(f"precision (flagged windows that were real anomalies): {e['precision']:.0%}")
        if e["false_positive_windows"]:
            info(f"false-positive windows: {e['false_positive_windows']}")
        return 0
    key = _answer_key(a, "attack_answer_key.csv")
    title(f"Grading attack investigation: {rel(a.submission)}")
    info(f"answer key: {rel(key)}")
    sub = pd.read_csv(a.submission)
    ans = pd.read_csv(key)
    tcol = next((c for c in sub.columns if c in ("time_seconds", "approx_time_seconds", "time", "timestamp")), None)
    if "attack_type" not in sub.columns or tcol is None:
        raise SystemExit("The submission needs columns 'attack_type' and 'time_seconds'.")
    sub["attack_type"] = sub["attack_type"].str.strip().str.lower().replace(ALIASES)
    if "core" in sub.columns:
        sub = sub[sub["core"].astype(str).str.lower() != "false"]
    score = 0
    for _, r in ans.iterrows():
        m = sub[(sub["attack_type"] == r["attack_type"]) &
                ((sub[tcol].astype(float) - float(r["approx_time_seconds"])).abs() <= a.tolerance)]
        if len(m):
            score += 1
            ok(f"{r['attack_type']:<30} at {float(r['approx_time_seconds']):>9.1f} s  - found")
        else:
            bad(f"{r['attack_type']:<30} at {float(r['approx_time_seconds']):>9.1f} s  - MISSED")
    wrong = [r for _, r in sub.iterrows()
             if not ((ans["attack_type"] == r["attack_type"]) &
                     ((ans["approx_time_seconds"].astype(float) - float(r[tcol])).abs() <= a.tolerance)).any()]
    print(f"\n  Score: {_c('1', f'{score}/{len(ans)}')}  attacks correctly identified (time tolerance +/-{a.tolerance:g} s)")
    if wrong:
        warn(f"{len(wrong)} submitted row(s) matched no planted attack (wrong type or time):")
        for r in wrong[:10]:
            info(f"   {r['attack_type']} at {r[tcol]}")
    return 0


# ---------------------------------------------------------------------------
# on-the-job helpers
# ---------------------------------------------------------------------------

def cmd_profile(a):
    prof = load_profile(a.profile)
    if a.action == "show":
        title(f"Site profile: {rel(prof.path)}")
        for x in prof.assets:
            info(f"{x['ip']:<15} {x['name']:<13} {x['role']:<26} {x.get('zone', '')}")
        info(f"approved Modbus writers: {', '.join(prof.label(i) for i in sorted(prof.approved_writers))}")
        info(f"approved PLC programmers: {', '.join(prof.label(i) for i in sorted(prof.approved_programmers))}")
        info(f"thresholds: {prof.thresholds}")
        return 0
    cap = resolve_capture(a.capture)
    title(f"Learning a site profile from {rel(cap)}")
    p = load(cap)
    from .load import is_group_address
    ips = sorted({i for i in set(p["ip_src"].astype(str)) | set(p["ip_dst"].astype(str)) if i and not is_group_address(i)},
                 key=lambda x: [int(o) for o in x.split(".")])
    mb = p[p["mb_request"] & (p["mb_fc"] >= 0)]
    masters = sorted(set(mb["ip_src"].astype(str)))
    writers = sorted(set(mb[mb["mb_fc"].isin([5, 6, 15, 16])]["ip_src"].astype(str)))
    servers = sorted(set(mb["ip_dst"].astype(str)))
    top = int((mb["mb_addr"] + mb["mb_qty"] - 1).max()) if len(mb) else 65535
    assets = []
    for ipaddr in ips:
        role = "Modbus master" if ipaddr in masters else "Modbus device" if ipaddr in servers else "host"
        assets.append({"name": prof.by_ip[ipaddr]["name"] if ipaddr in prof.by_ip else f"HOST-{ipaddr.split('.')[-1]}",
                       "ip": ipaddr, "role": role, "zone": ".".join(ipaddr.split(".")[:3]) + ".0/24"})
    data = {"_readme": "LEARNED automatically - review every line! Rename assets, delete anything that should not be "
                       "there, and set 'gateways' and 'plcs' correctly before trusting this profile.",
            "site": a.site or f"Learned from {os.path.basename(cap)}", "assets": assets, "gateways": [],
            "plcs": servers, "modbus": {"approved_masters": masters, "approved_writers": writers,
                                        "highest_normal_register": top},
            "approved_programmers": [], "programming_ports": [102, 44818, 1962, 20547],
            "thresholds": prof.thresholds, "window_minutes": 5}
    outp = a.output or os.path.join(LAB_ROOT, "profiles", "learned_site.json")
    with open(outp, "w") as f:
        json.dump(data, f, indent=2)
    ok(f"{len(assets)} hosts, {len(masters)} Modbus masters, {len(writers)} writers, {len(servers)} Modbus devices")
    ok(f"written to {rel(outp)}")
    warn("A learned profile trusts whatever was in the capture. If an attacker was already there, they are now 'approved'.")
    nxt(f"Edit {rel(outp)}, then use it with:  ./otlab hunt <capture> --profile {rel(outp)}")
    return 0


def cmd_features(a):
    from .features import window_features
    cap = resolve_capture(a.capture)
    p = load(cap)
    f = window_features(p, a.window)
    outp = out_path(a.output, f"features_{os.path.splitext(os.path.basename(cap))[0]}.csv")
    f.to_csv(outp)
    ok(f"{len(f)} windows x {f.shape[1] - 2} features -> {rel(outp)}")
    return 0


def cmd_selftest(a):
    import tempfile
    from .detect import evaluate, load_truth, zscore_detect
    from .features import DEFAULT_DETECT_FEATURES, build_baseline, window_features
    from .hunt import hunt
    from .load import load_packets
    from .sim.generate import generate_baseline, inject_anomalies, inject_attacks
    title("otlab selftest - generate a small lab and check every detector finds what was planted")
    prof = load_profile(a.profile)
    d = tempfile.mkdtemp(prefix="otlab_selftest_")
    b, an, at = (os.path.join(d, x) for x in ("b.pcap", "a.pcap", "x.pcap"))
    generate_baseline(b, prof, hours=a.hours, seed=1234)
    inject_anomalies(b, an, os.path.join(d, "gt.csv"), prof, seed=99)
    inject_attacks(b, at, os.path.join(d, "key.csv"), prof, seed=98)
    ok(f"generated {a.hours:g} h of captures in {d}")
    pb, pa, px = (load_packets(x, use_cache=False, quiet=True) for x in (b, an, at))
    fb = window_features(pb)
    bl = build_baseline(pb, fb, "b", 5)
    flags, _ = zscore_detect(window_features(pa), bl, DEFAULT_DETECT_FEATURES, 3.0)
    e = evaluate(flags, load_truth(os.path.join(d, "gt.csv")), 5)
    (ok if e["detected"] == 3 else bad)(f"z-score detector: {e['detected']}/3 anomalies, {e['fp']} false positives")
    found = {f["attack_type"] for f in hunt(px, prof) if f["core"]}
    (ok if len(found) == 5 else bad)(f"signature hunter: {len(found)}/5 attack types ({', '.join(sorted(found))})")
    clean = [f for f in hunt(pb, prof) if f["core"]]
    (ok if not clean else bad)(f"no false alarms on the clean baseline ({len(clean)} findings)")
    shutil.rmtree(d, ignore_errors=True)
    return 0 if (e["detected"] == 3 and len(found) == 5 and not clean) else 1


# ---------------------------------------------------------------------------
# menu + parser
# ---------------------------------------------------------------------------

MENU = """
  {b}otlab{r} - OT Traffic Analysis toolkit (Module 4, Palanca)

  {h}Set-up{r}
    ./otlab doctor                          check your machine is ready
    ./otlab wireshark install               add the Palanca-OT profile to Wireshark
    ./otlab wireshark open <capture>        open a capture with that profile

  {h}Day 1-2  (live Docker lab){r}
    ./otlab live status                     is the lab up? which interface to capture on?
    ./otlab live activity                   add OPC UA sessions + Modbus writes to the lab traffic
    ./otlab live capture --minutes 15       record a capture to captures/live/
    ./otlab summary <capture>               what is in a capture (protocols, hosts, timeline)
    ./otlab map <capture>                   who polls whom, and how often (diagram)
    ./otlab explain <capture> --first write explain a Modbus packet byte by byte

  {h}Day 3-6  (synthetic captures){r}
    ./otlab baseline                        Day 3  build the baseline (mean/std/percentiles)
    ./otlab detect zscore anomalies         Day 4  Z-score detector
    ./otlab detect ml anomalies             Day 5  Isolation Forest + comparison
    ./otlab hunt attack                     Day 6  find the 5 planted attacks

  {h}Instructor{r}
    ./otlab generate [--seed N] [--assessment]   make (new) captures + answer keys
    ./otlab grade anomalies <flagged.csv>        score a Day 4/5 submission
    ./otlab grade attacks <findings.csv>         score a Day 6 submission
    ./otlab selftest                             prove the lab works end to end

  {h}On the job{r}
    ./otlab profile learn <capture>         draft a site profile from your own plant's traffic
    ./otlab hunt <capture> --profile <site.json>

  Shortcuts: 'baseline', 'anomalies' and 'attack' mean the files in captures/.
  Every command has help:  ./otlab <command> -h
"""


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", default=argparse.SUPPRESS,
                        help="site profile JSON (default: profiles/palanca.json; captures/live/* use palanca_live_lab.json)")
    ap = argparse.ArgumentParser(prog="otlab", description="Module 4 OT traffic analysis toolkit")
    ap.add_argument("--profile", dest="profile_top", help="site profile JSON (may also go after the command)")
    sp = ap.add_subparsers(dest="cmd")
    _add = sp.add_parser
    sp.add_parser = lambda *x, **k: _add(*x, parents=[common], **k)

    s = sp.add_parser("doctor", help="check the lab machine")
    s.set_defaults(fn=cmd_doctor)

    s = sp.add_parser("generate", help="(instructor) generate lab captures and answer keys")
    s.add_argument("--hours", type=float, default=24.0)
    s.add_argument("--seed", type=int, help="re-create an earlier set of captures exactly")
    s.add_argument("--assessment", action="store_true", help="Day 7: fresh captures with randomly placed events in captures/assessment/")
    s.set_defaults(fn=cmd_generate)

    s = sp.add_parser("wireshark", help="Palanca-OT Wireshark profile")
    s.add_argument("action", choices=["install", "open", "filters"])
    s.add_argument("capture", nargs="?")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_wireshark)

    s = sp.add_parser("live", help="Days 1-2: work with the live Docker lab")
    s.add_argument("action", choices=["status", "activity", "capture"])
    s.add_argument("--minutes", type=float, default=15)
    s.add_argument("-o", "--output")
    s.add_argument("--where", choices=["auto", "host", "eng-ws"], default="auto", help="capture on the host bridges or inside eng-ws-01")
    s.add_argument("--follow", action="store_true", help="activity: run in the foreground and show each action")
    s.add_argument("--log", action="store_true", help="activity: show what the background activity has done")
    s.set_defaults(fn=cmd_live)

    for name, fn, hlp in [("summary", cmd_summary, "what is in a capture"), ("map", cmd_map, "communication map")]:
        s = sp.add_parser(name, help=hlp)
        s.add_argument("capture")
        s.add_argument("-o", "--output")
        if name == "map":
            s.add_argument("--min-packets", type=int, default=1, help="hide conversations smaller than this")
        s.set_defaults(fn=fn)

    s = sp.add_parser("explain", help="explain a packet byte by byte")
    s.add_argument("capture", nargs="?")
    s.add_argument("--frame", type=int, help="packet number (Wireshark's No. column)")
    s.add_argument("--first", choices=["read", "response", "write", "exception", "arp", "syn"], default="read",
                   help="explain the first packet of this kind")
    s.add_argument("--hex", help="explain raw Modbus/TCP bytes instead, e.g. '00 01 00 00 00 06 01 03 00 00 00 0a'")
    s.add_argument("--response", action="store_true", help="with --hex: the bytes are a response, not a request")
    s.set_defaults(fn=cmd_explain)

    s = sp.add_parser("baseline", help="Day 3: build the baseline")
    s.add_argument("capture", nargs="?")
    s.add_argument("--window", type=float, default=5.0, help="window length in minutes (default 5)")
    s.add_argument("-o", "--output", help="baseline JSON path (default results/day3_baseline.json)")
    s.set_defaults(fn=cmd_baseline)

    s = sp.add_parser("detect", help="Days 4-5: anomaly detection")
    s.add_argument("method", choices=["zscore", "ml"])
    s.add_argument("capture", nargs="?")
    s.add_argument("--baseline", default=os.path.join(RESULTS, "day3_baseline.json"))
    s.add_argument("--threshold", type=float, default=3.0, help="z-score threshold (default 3.0)")
    s.add_argument("--features", help="comma-separated feature names (zscore default: packets,avg_payload,modbus_reads,modbus_writes,"
                        "unique_src,tcp_syn; ml default: packets,avg_payload,modbus_reads,modbus_writes)")
    s.add_argument("--train", help="ml: NORMAL capture to train on (default: baseline)")
    s.add_argument("--contamination", type=float, default=0.02)
    s.add_argument("--window", type=float, default=5.0)
    s.add_argument("--sweep", action="store_true", help="ml: try several contamination values")
    s.add_argument("--truth", help="ground-truth CSV (only once your instructor has released it)")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_detect)

    s = sp.add_parser("hunt", help="Day 6: signature-based attack hunting")
    s.add_argument("capture", nargs="?")
    s.add_argument("--baseline", help="baseline JSON: hosts seen in it are not reported as unknown")
    s.add_argument("--quiet-extras", action="store_true", help="only show the 5 core signature rules")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_hunt)

    s = sp.add_parser("grade", help="(instructor) score a submission")
    s.add_argument("what", choices=["anomalies", "attacks"])
    s.add_argument("submission")
    s.add_argument("--truth", help="answer key CSV (default: captures/instructor-only/...)")
    s.add_argument("--window", type=float, default=5.0)
    s.add_argument("--windows", type=int, help="total windows in the capture (default: from the answer key's generation.json, else 288 for 24 h)")
    s.add_argument("--tolerance", type=float, default=120, help="attacks: allowed time error in seconds")
    s.set_defaults(fn=cmd_grade)

    s = sp.add_parser("profile", help="show or learn a site profile")
    s.add_argument("action", choices=["show", "learn"])
    s.add_argument("capture", nargs="?")
    s.add_argument("--site")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_profile)

    s = sp.add_parser("features", help="export per-window features to CSV")
    s.add_argument("capture")
    s.add_argument("--window", type=float, default=5.0)
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_features)

    s = sp.add_parser("selftest", help="(instructor) end-to-end check of the whole lab")
    s.add_argument("--hours", type=float, default=6.0)
    s.set_defaults(fn=cmd_selftest)
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    a.profile = getattr(a, "profile", None) or a.profile_top
    if not getattr(a, "fn", None):
        print(MENU.format(b="\033[1m" if _TTY else "", r="\033[0m" if _TTY else "", h="\033[1;36m" if _TTY else ""))
        return 0
    if a.cmd == "profile" and a.action == "learn" and not a.capture:
        ap.error("profile learn needs a capture file")
    try:
        return a.fn(a) or 0
    except KeyboardInterrupt:
        print("\n  stopped.")
        return 130
    except FileNotFoundError as e:
        bad(str(e))
        return 1
