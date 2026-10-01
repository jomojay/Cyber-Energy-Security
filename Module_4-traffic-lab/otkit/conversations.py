"""
Day 2 (and on the job): who talks to whom, with what protocol, how often.

Every TCP/UDP conversation is folded into one row: client -> server on a
service port, with packet/byte counts and the typical polling interval
(the median gap between the client's requests). A regular, short
interval is the heartbeat of an OT network; anything that breaks the
rhythm is worth a look.
"""
import pandas as pd

from .load import APP_PORTS, is_group_address


BACKGROUND = {"NTP", "Syslog", "NetBIOS-NS", "NetBIOS-DGM", "LLMNR", "SSDP", "mDNS", "DHCP"}


def conversations(pkts):
    ip = pkts[(pkts["l4"].isin(["TCP", "UDP"])) & (pkts["ip_src"].astype(str) != "")].copy()
    if ip.empty:
        return pd.DataFrame()
    src, dst = ip["ip_src"].astype(str), ip["ip_dst"].astype(str)
    sp, dp = ip["sport"], ip["dport"]
    # The service side is the well-known port (or the lower port if neither is known).
    dst_is_service = dp.isin(APP_PORTS.keys()) | (~sp.isin(APP_PORTS.keys()) & (dp <= sp))
    ip["client"] = src.where(dst_is_service, dst)
    ip["server"] = dst.where(dst_is_service, src)
    ip["port"] = dp.where(dst_is_service, sp)
    ip["from_client"] = dst_is_service
    ip["app"] = ip["app"].astype(str)

    rows = []
    for (c, s, port, l4), g in ip.groupby(["client", "server", "port", "l4"], observed=True):
        reqs = g[g["from_client"] & (g["payload"] > 0)]
        # A poll cycle can hold several requests a split second apart (e.g. 3 OPC UA subscriptions, 2 SNMP GETs):
        # measure the interval between cycles, not between individual requests.
        cycles = reqs["time"][reqs["time"].diff().fillna(1e9) > 0.5]
        gaps = cycles.diff().dropna()
        interval = float(gaps.median()) if len(gaps) >= 3 else float("nan")
        rows.append({
            "client": c, "server": s, "protocol": g["app"].iloc[0], "port": int(port), "transport": l4,
            "packets": len(g), "bytes": int(g["len"].sum()), "requests": len(reqs),
            "interval_s": round(interval, 2) if interval == interval else None,
            "regular": bool(len(gaps) >= 10 and gaps.std() < 0.25 * max(interval, 1e-9)),
            "first_s": round(float(g["rel"].min()), 2), "last_s": round(float(g["rel"].max()), 2),
            "modbus_fcs": ",".join(str(int(x)) for x in sorted(g.loc[g["mb_request"] & (g["mb_fc"] >= 0), "mb_fc"].unique())),
        })
    df = pd.DataFrame(rows)
    return df.sort_values(["packets"], ascending=False).reset_index(drop=True)


def _periodic(conv):
    """Only show 'every N s' for conversations that really are periodic (polling)."""
    c = conv.copy()
    c.loc[~c["regular"], "interval_s"] = None
    return c


def protocol_mix(pkts):
    """Packets and bytes per protocol. Wireshark: Statistics > Protocol Hierarchy shows the same two percentages."""
    app = pkts["app"].astype(str)
    vc = app.value_counts()
    by = pkts.groupby(app)["len"].sum()
    df = pd.DataFrame({"packets": vc, "percent_packets": (vc / vc.sum() * 100).round(2),
                       "bytes": by, "percent_bytes": (by / by.sum() * 100).round(2)})
    return df.sort_values("bytes", ascending=False)


def draw_map(conv, profile, path, title="Communication map", min_packets=1):
    """Purdue-style layered diagram: L3 on top, L2 in the middle, L1 at the bottom, unknown hosts in red."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    # Broadcast/multicast chatter and time/log services would bury the process traffic: leave them off the picture
    # (they are still in the conversations table).
    conv = conv[(conv["packets"] >= min_packets) & ~conv["server"].map(is_group_address)
                & ~conv["protocol"].isin(BACKGROUND)].copy()
    # One host touching many ports on another = a scan: draw ONE edge instead of one per port.
    nports = conv.groupby(["client", "server"])["port"].transform("nunique")
    conv.loc[nports >= 5, "protocol"] = nports[nports >= 5].map(lambda n: f"{n} ports - SCAN?")
    conv.loc[nports >= 5, "interval_s"] = None
    conv.loc[nports >= 5, "regular"] = False
    hosts = sorted(set(conv["client"]) | set(conv["server"]))
    layers = {"DMZ (L3)": 3, "Supervisory (L2)": 2, "Control (L1)": 1}

    def layer(ipaddr):
        z = profile.zone(ipaddr)
        if z in layers:
            return layers[z]
        return 0  # unknown

    rows = {}
    for h in hosts:
        rows.setdefault(layer(h), []).append(h)
    width = max(len(v) for v in rows.values()) if rows else 1
    fig_w = max(10, width * 2.1)
    fig, ax = plt.subplots(figsize=(fig_w, 9.5))
    # A master that polls devices in its OWN zone (e.g. PLC-MAIN-01 -> RTUs) sits on a raised sub-row,
    # so its arrows fan out downwards instead of hiding behind the neighbouring boxes.
    same_zone = conv[[layer(c) == layer(sv) for c, sv in zip(conv["client"], conv["server"])]]
    fan = same_zone.groupby("client")["server"].nunique()
    lifted = set(fan[fan >= 3].index)
    ylev = {3: 4.2, 2: 2.6, 1: 1.0, 0: -0.6}
    pos = {}
    for lvl, hs in rows.items():
        low = sorted([h for h in hs if h not in lifted], key=lambda x: [int(o) for o in x.split(".")])
        high = sorted([h for h in hs if h in lifted], key=lambda x: [int(o) for o in x.split(".")])
        for i, h in enumerate(low):
            pos[h] = ((i + 1) * width / (len(low) + 1), ylev[lvl])
        for i, h in enumerate(high):
            pos[h] = ((i + 1) * width / (len(high) + 1), ylev[lvl] + 0.75)

    band_names = {3: "Level 3 - DMZ / Historian", 2: "Level 2 - Supervisory", 1: "Level 1 - Control", 0: "UNKNOWN devices"}
    for lvl in rows:
        top = ylev[lvl] + (1.05 if any(h in lifted for h in rows[lvl]) else 0.42)
        ax.axhspan(ylev[lvl] - 0.35, top, color="#d0e3f7" if lvl else "#f9d4d4", alpha=0.45, zorder=0)
        ax.text(-0.02 * width, top - 0.1, band_names[lvl], fontsize=9, color="#333", va="center")

    colors = {"Modbus/TCP": "#1f77b4", "OPC UA": "#2ca02c", "HTTP": "#ff7f0e", "HTTPS": "#8c564b",
              "SNMP": "#7f7f7f", "S7/ISO-TSAP": "#d62728"}
    agg = _periodic(conv).groupby(["client", "server", "protocol"], as_index=False).agg(
        packets=("packets", "sum"), interval_s=("interval_s", "median"))
    agg["fan"] = agg.groupby(["client", "protocol", "interval_s"], dropna=False)["server"].transform("count")
    fan_labelled = set()
    for _, r in agg.iterrows():
        (x1, y1), (x2, y2) = pos[r["client"]], pos[r["server"]]
        col = colors.get(r["protocol"], "#9467bd")
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), zorder=1,
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=1.3, alpha=0.8, shrinkA=20, shrinkB=20,
                                    connectionstyle="arc3,rad=0.04"))
        every = f"every {r['interval_s']:g}s" if pd.notna(r["interval_s"]) else "occasional"
        if r["fan"] >= 3:  # one master polling many devices: a single label next to the master
            key = (r["client"], r["protocol"], r["interval_s"])
            if key not in fan_labelled:
                fan_labelled.add(key)
                ax.text(x1 + 0.5, y1 + 0.02, f"{r['protocol']} {every}\n-> {int(r['fan'])} devices", fontsize=7,
                        color=col, ha="left", va="center", zorder=3,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))
            continue
        ax.text(x1 + (x2 - x1) * 0.45, y1 + (y2 - y1) * 0.45, f"{r['protocol']}\n{every}", fontsize=7, color=col,
                ha="center", va="center", zorder=3, bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    for h, (x, y) in pos.items():
        unknown = h not in profile.by_ip
        box = FancyBboxPatch((x - 0.42, y - 0.17), 0.84, 0.34, boxstyle="round,pad=0.02",
                             fc="#fff" if not unknown else "#ffe5e5", ec="#b00" if unknown else "#345", lw=1.2, zorder=4)
        ax.add_patch(box)
        ax.text(x, y + 0.05, profile.name(h) if not unknown else "UNKNOWN", ha="center", va="center", fontsize=8,
                weight="bold", zorder=5, color="#b00" if unknown else "#123")
        ax.text(x, y - 0.08, h, ha="center", va="center", fontsize=7, zorder=5, color="#444")
    handles = [plt.Line2D([], [], color=c, lw=2, label=p) for p, c in colors.items() if p in set(agg["protocol"])]
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8, frameon=True)
    ax.set_xlim(-0.1 * width, width * 1.05)
    ax.set_ylim(min(ylev[l] for l in rows) - 0.5, max(ylev[l] for l in rows) + 1.2)
    ax.axis("off")
    ax.set_title(title + "   (arrow = who starts the conversation -> who answers)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def mermaid(conv, profile):
    """Text diagram you can paste into draw.io (Arrange > Insert > Advanced > Mermaid) or a Markdown report."""
    lines = ["flowchart TB"]
    ids = {}

    def node(ipaddr):
        if ipaddr not in ids:
            ids[ipaddr] = f"n{len(ids)}"
            lines.append(f'    {ids[ipaddr]}["{profile.name(ipaddr) if ipaddr in profile.by_ip else "UNKNOWN"}<br/>{ipaddr}"]')
        return ids[ipaddr]

    conv = conv[~conv["server"].map(is_group_address) & ~conv["protocol"].isin(BACKGROUND)]
    agg = _periodic(conv).groupby(["client", "server", "protocol"], as_index=False).agg(interval_s=("interval_s", "median"))
    for _, r in agg.iterrows():
        a, b = node(r["client"]), node(r["server"])
        lab = r["protocol"] + (f" every {r['interval_s']:g}s" if pd.notna(r["interval_s"]) else " occasional")
        lines.append(f'    {a} -->|"{lab}"| {b}')
    return "\n".join(lines) + "\n"
