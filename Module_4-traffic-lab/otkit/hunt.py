"""
Day 6 (and on the job): signature-based threat hunting in OT traffic.

The five core rules are the Module 4, Table 4.3 attack signatures:

  R1 network_reconnaissance       one host sends SYNs to many ports in a short time
  R2 modbus_register_enumeration  Modbus reads sweeping many / out-of-range registers
  R3 unauthorised_write           Modbus write from a host not on the approved-writer list
  R4 plc_program_upload           >10 KB pushed to a PLC (programming ports especially)
  R5 arp_spoofing_mitm            one IP address claimed by two different MAC addresses

Extra observations (not part of the Day 6 answer, but useful at work):
  X1 unknown_host      an IP address that is not in the site profile
  X2 modbus_diagnostic Modbus FC 08 / 17 / 43 (diagnostics, device identification)
  X3 large_outbound    lots of data leaving the control zone to an unknown host (exfiltration)
"""
import datetime as dt

import pandas as pd

from .features import READ_FCS, WRITE_FCS
from .load import is_group_address

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

ADVICE = {
    "network_reconnaissance": (
        "Someone is mapping which services the device offers - usually the first step of an attack.",
        "Identify the scanning host (switch port / asset list). If it is not an approved scanner, isolate it "
        "and check what else it talked to."),
    "modbus_register_enumeration": (
        "A host is reading register after register to learn the device's memory map, "
        "typically to find what to write to next.",
        "Confirm whether the source is a legitimate Modbus master. Block it at the firewall if not, and "
        "watch for writes that may follow."),
    "unauthorised_write": (
        "A device that is NOT allowed to change PLC values just did. This can change a setpoint or "
        "operate equipment.",
        "Tell the control room immediately: verify the process values the write touched. Isolate the source "
        "host and preserve this capture as evidence."),
    "plc_program_upload": (
        "A large block of data was pushed to a PLC - consistent with a program/firmware download that "
        "can change what the plant does.",
        "Check with engineering whether a change was scheduled. If not, compare the running PLC program "
        "against the known-good backup and isolate the source."),
    "arp_spoofing_mitm": (
        "Two different network cards claim the same IP address. An attacker may be inserting itself "
        "between devices (man-in-the-middle) to read or alter traffic.",
        "Find the switch port that owns the rogue MAC and shut it. Check the ARP tables of the victims and "
        "consider static ARP / port security for critical assets."),
    "unknown_host": ("A device not in the asset inventory is on the network.",
                     "Find out what it is. Unknown devices on an OT network should be explained or removed."),
    "modbus_diagnostic": ("Diagnostic / identification function codes are rarely used in normal operation and "
                          "are popular with scanners.", "Check who sent them and why."),
    "large_outbound": ("A lot of data went from the plant network to an unknown host - possible data theft.",
                       "Identify the destination and what was sent."),
}


def _utc(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _finding(rule, attack_type, severity, rows, t0, src, dst, count, evidence, wfilter, core=True):
    meaning, action = ADVICE.get(attack_type, ("", ""))
    first, last = float(rows["time"].min()), float(rows["time"].max())
    return {
        "rule": rule, "attack_type": attack_type, "severity": severity, "core": core,
        "time_seconds": round(first - t0, 2), "end_seconds": round(last - t0, 2), "utc_time": _utc(first),
        "first_packet": int(rows["no"].min()), "src_ip": src, "dst_ip": dst, "packets": int(count),
        "evidence": evidence, "wireshark_filter": wfilter, "what_it_means": meaning, "what_to_do": action,
    }


def _bursts(times, gap):
    """Split a sorted series of timestamps into bursts separated by more than `gap` seconds."""
    ids = (times.diff() > gap).cumsum()
    return ids


def hunt(pkts, profile, baseline=None):
    th = profile.thresholds
    t0 = float(pkts["time"].iloc[0])
    findings = []
    ip_src = pkts["ip_src"].astype(str)
    ip_dst = pkts["ip_dst"].astype(str)
    name = profile.label

    # R1 - reconnaissance: SYN (no ACK) to many distinct ports from one source within the scan window
    syn = pkts[pkts["syn"] & ~pkts["ack"]].assign(src=lambda d: ip_src.loc[d.index], dst=lambda d: ip_dst.loc[d.index])
    for src, grp in syn.groupby("src"):
        grp = grp.sort_values("time")
        for _, burst in grp.groupby(_bursts(grp["time"], th["scan_window_seconds"])):
            ports = burst["dport"].nunique()
            if ports >= th["scan_distinct_ports"]:
                targets = sorted(burst["dst"].unique())
                plist = ", ".join(str(p) for p in sorted(burst["dport"].unique())[:25])
                answered = pkts[(ip_src.isin(targets)) & (ip_dst == src) & pkts["syn"] & pkts["ack"]]["sport"].unique()
                findings.append(_finding(
                    "R1", "network_reconnaissance", "HIGH", burst, t0, src, ", ".join(targets), len(burst),
                    f"{name(src)} sent {len(burst)} SYN packets to {ports} different ports on "
                    f"{', '.join(name(t) for t in targets)} in {burst['time'].max() - burst['time'].min():.1f} s. "
                    f"Ports probed: {plist}. Open ports (answered SYN/ACK): "
                    f"{', '.join(str(p) for p in sorted(answered)) or 'none'}.",
                    f"tcp.flags.syn==1 && tcp.flags.ack==0 && ip.src=={src}"))

    mb = pkts[(pkts["mb_fc"] >= 0)].assign(src=lambda d: ip_src.loc[d.index], dst=lambda d: ip_dst.loc[d.index])
    req = mb[mb["mb_request"]]

    # R2 - register enumeration: reads covering many start addresses, or beyond the normal register map
    reads = req[req["mb_fc"].isin(READ_FCS)]
    for (src, dst), grp in reads.groupby(["src", "dst"]):
        top = int((grp["mb_addr"] + grp["mb_qty"] - 1).max())
        distinct = grp["mb_addr"].nunique()
        unapproved = src not in profile.approved_masters
        out_of_range = top > profile.highest_normal_register
        if (unapproved and distinct >= th["enum_distinct_addresses"]) or out_of_range:
            exc = mb[(mb["src"] == dst) & (mb["dst"] == src) & (mb["mb_exception"] > 0)]
            findings.append(_finding(
                "R2", "modbus_register_enumeration", "HIGH" if unapproved else "MEDIUM", grp, t0, src, dst, len(grp),
                f"{name(src)} sent {len(grp)} Modbus read requests to {name(dst)} covering {distinct} different "
                f"start addresses, up to register {top} (normal map ends at {profile.highest_normal_register}). "
                f"{len(exc)} requests were answered with a Modbus EXCEPTION (address does not exist). "
                + ("The source is NOT a known Modbus master." if unapproved else ""),
                f"modbus.func_code in {{1,2,3,4}} && ip.src=={src}"))

    # R3 - unauthorised write: any write function code from a host not on the approved list
    writes = req[req["mb_fc"].isin(WRITE_FCS) & ~req["src"].isin(profile.approved_writers)]
    for (src, dst), grp in writes.groupby(["src", "dst"]):
        fcs = ", ".join(f"FC{int(f):02d}" for f in sorted(grp["mb_fc"].unique()))
        regs = ", ".join(str(int(a)) for a in sorted(grp["mb_addr"].unique())[:10])
        findings.append(_finding(
            "R3", "unauthorised_write", "CRITICAL", grp, t0, src, dst, len(grp),
            f"{name(src)} sent {len(grp)} Modbus WRITE request(s) ({fcs}) to {name(dst)}, register(s) {regs}. "
            f"Approved writers are only: {', '.join(name(i) for i in sorted(profile.approved_writers))}.",
            "modbus.func_code in {5,6,15,16} && tcp.dstport == 502 && !(ip.src in {"
            + ",".join(sorted(profile.approved_writers)) + "})"))

    # R4 - PLC program upload: lots of payload bytes pushed to a PLC in one burst
    to_plc = pkts[ip_dst.isin(profile.plcs) & (pkts["payload"] > 0)].assign(src=lambda d: ip_src.loc[d.index], dst=lambda d: ip_dst.loc[d.index])
    for (src, dst, dport), grp in to_plc.groupby(["src", "dst", "dport"]):
        grp = grp.sort_values("time")
        for _, burst in grp.groupby(_bursts(grp["time"], 60)):
            total = int(burst["payload"].sum())
            if total >= th["upload_bytes"] and (dport in profile.programming_ports or burst["len"].max() > 1000):
                approved = src in profile.approved_programmers
                findings.append(_finding(
                    "R4", "plc_program_upload", "MEDIUM" if approved else "CRITICAL", burst, t0, src, dst, len(burst),
                    f"{name(src)} pushed {total:,} bytes to {name(dst)} on TCP/{dport} in "
                    f"{burst['time'].max() - burst['time'].min():.1f} s ({len(burst)} packets, largest frame "
                    f"{int(burst['len'].max())} bytes). "
                    + ("Source is an approved programmer - confirm a change was scheduled."
                       if approved else "Source is NOT an approved programming workstation."),
                    f"ip.dst=={dst} && tcp.dstport=={dport} && frame.len > 1000"))

    # R5 - ARP spoofing: one IP address announced with more than one MAC
    arp = pkts[pkts["arp_op"] > 0].assign(aip=lambda d: d["arp_ip"].astype(str), amac=lambda d: d["arp_mac"].astype(str))
    arp = arp[arp["aip"] != "0.0.0.0"]
    for aip, grp in arp.groupby("aip"):
        macs = list(dict.fromkeys(grp.sort_values("time")["amac"]))
        if len(macs) > 1:
            rogue = grp[grp["amac"].isin(macs[1:])]
            victims = sorted(set(rogue["arp_target_ip"].astype(str)))
            findings.append(_finding(
                "R5", "arp_spoofing_mitm", "CRITICAL" if aip in profile.gateways else "HIGH", rogue, t0, aip,
                ", ".join(victims), len(rogue),
                f"IP {name(aip)} was claimed by {len(macs)} different MAC addresses: first {macs[0]}, then "
                f"{', '.join(macs[1:])} ({len(rogue)} ARP replies to {', '.join(name(v) for v in victims)})."
                + (" This IP is the GATEWAY - traffic leaving the subnet can be intercepted." if aip in profile.gateways else ""),
                "arp.duplicate-address-detected || arp.duplicate-address-frame"))

    # ---- extra observations ----
    known = set(profile.by_ip) | (set(baseline.get("known_ips", [])) if baseline else set())
    seen = pd.DataFrame({"ip": pd.concat([ip_src, ip_dst]), "time": pd.concat([pkts["time"], pkts["time"]]),
                         "no": pd.concat([pkts["no"], pkts["no"]])})
    seen = seen[(seen["ip"] != "") & ~seen["ip"].isin(known) & ~seen["ip"].map(is_group_address)
                & ~seen["ip"].str.startswith("0.")]
    for ipaddr, grp in seen.groupby("ip"):
        findings.append(_finding("X1", "unknown_host", "LOW", grp, t0, ipaddr, "", len(grp),
                                 f"{ipaddr} is not in the site profile{' or the baseline' if baseline else ''}; "
                                 f"seen in {len(grp)} packets.", f"ip.addr=={ipaddr}", core=False))

    diag = req[req["mb_fc"].isin([8, 17, 43])]
    for (src, dst), grp in diag.groupby(["src", "dst"]):
        findings.append(_finding("X2", "modbus_diagnostic", "MEDIUM", grp, t0, src, dst, len(grp),
                                 f"{name(src)} sent Modbus diagnostic/identification requests "
                                 f"(FC {', '.join(str(int(f)) for f in sorted(grp['mb_fc'].unique()))}) to {name(dst)}.",
                                 f"modbus.func_code in {{8,17,43}} && ip.src=={src}", core=False))

    ot = pkts[ip_src.str.startswith("192.168.1.") & (pkts["payload"] > 0)].assign(src=lambda d: ip_src.loc[d.index], dst=lambda d: ip_dst.loc[d.index])
    ot = ot[~ot["dst"].isin(known) & (ot["dst"] != "") & ~ot["dst"].map(is_group_address)]
    for (src, dst), grp in ot.groupby(["src", "dst"]):
        total = int(grp["payload"].sum())
        if total >= th["exfil_bytes"]:
            findings.append(_finding("X3", "large_outbound", "HIGH", grp, t0, src, dst, len(grp),
                                     f"{name(src)} sent {total:,} bytes to unknown host {dst}.",
                                     f"ip.src=={src} && ip.dst=={dst}", core=False))

    findings.sort(key=lambda f: (not f["core"], f["time_seconds"]))
    return findings
