"""
Synthetic 'normal day' of Palanca traffic (Module 4, Table 4.1):

  PLC-MAIN-01 -> every RTU/relay/VFD   Modbus/TCP  every 2 s   FC03, 10 registers   (~66 B query / ~83 B reply)
  HMI-01      -> PLC-MAIN-01           Modbus/TCP  every 1 s   FC03 + occasional FC06 (~123 B reply)
  SCADA-SVR   -> HISTORIAN             OPC UA      every 5 s   PublishResponse ~400 B (to the historian's PublishRequest)
  ENG-WS      -> PLC-MAIN-01           HTTP        on demand   day shift only, ~1200 B pages
  NMS         -> switches              SNMP        every 60 s  GET interface counters, CPU, memory (~150 B)
  everyone                             ARP         periodic cache refresh

Like a real capture, recording starts while the polling connections are
already up (their handshakes happened before the capture began). Every
TCP conversation keeps real sequence numbers, so Wireshark decodes every
packet correctly. The historian restarts its OPC UA session once, in the
early morning, so a full session set-up (Hello / OpenSecureChannel) is
in the capture too.
"""
import datetime as dt
import random

from . import protocols as proto
from .network import Net

DEFAULT_START = dt.datetime(2026, 3, 2, 0, 0, 0, tzinfo=dt.timezone.utc)  # a Monday, 00:00 UTC

# Each field device answers PLC-MAIN-01's poll cycle with these (function code, start register, count).
POLL_PLAN = {  # Table 4.1: FC 03 Read Holding Registers, 10 registers per poll
    "PLC-AUX-01":  [(3, 0, 10), (3, 10, 10)],
    "GEN1-RTU":    [(3, 0, 10), (3, 10, 10)],
    "GEN2-RTU":    [(3, 0, 10), (3, 10, 10)],
    "PROT-REL-01": [(3, 0, 10), (3, 10, 10)],
    "PROT-REL-02": [(3, 0, 10), (3, 10, 10)],
    "VFD-PUMP-01": [(3, 0, 10), (3, 10, 10)],
}
HMI_READS = [(3, 0, 30), (3, 30, 30)]  # 30-register block -> ~123-byte response frames (Table 4.1: ~120 B)
HMI_SETPOINT_REGS = range(20, 30)

# Rates below are tuned so the byte mix matches the Module 4 text's "Key observations" for the baseline
# capture (Modbus 50.4 %, OPC UA 21.7 %, HTTP/HTTPS 9.6 %, ARP 6.7 %, SNMP 1.8 %, other ~9.8 % of bytes)
# while every row of Table 4.1 (interval + packet size) stays true.
OPC_SUBSCRIPTIONS = [(1, 11), (2, 11), (3, 2)]   # (subscription id, monitored items): 2 process-data + 1 alarms
HTTPS_INTERVAL = 12.5                             # HMI-01 refreshes the SCADA web interface
HTTPS_KEEPALIVE = 100                            # requests per HTTPS connection before the server closes it
HTTPS_REQ, HTTPS_RESP = (280, 320), (1080, 1140)  # TLS record sizes (bytes)
ARP_REFRESH = (21, 41)                            # Windows-like ARP cache refresh per peer (seconds)
NTP_POLL = 64                                     # every host syncs its clock with its switch
SYSLOG_EVERY = (10, 30)                           # switch syslog messages to the NMS
WINDOWS_HOSTS = ["HMI-01", "SCADA-SVR", "ENG-WS", "HISTORIAN", "NMS"]
DAY_SHIFT = range(6, 18)  # 06:00-17:59 UTC


def start_epoch(start=None):
    if start is None:
        return DEFAULT_START.timestamp()
    if isinstance(start, (int, float)):
        return float(start)
    return dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp()


def _hour(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).hour


def build_baseline(profile, hours=24.0, seed=None, start=None):
    rng = random.Random(seed)
    net = Net(profile, rng)
    t0 = start_epoch(start)
    end = t0 + hours * 3600
    ip = profile.ip_of

    def jitter(sd=0.004):
        return rng.gauss(0, sd)

    def latency():
        return rng.uniform(0.002, 0.012)

    plc = ip("PLC-MAIN-01")
    hmi = ip("HMI-01")

    pre = t0 - 3600  # connections were opened an hour before the capture started

    # --- PLC-MAIN-01 polls every field device every 2 s (one persistent TCP connection each) ---
    for i, (dev, plan) in enumerate(POLL_PLAN.items()):
        conn = net.tcp(plc, ip(dev), 502)
        t = conn.open(pre + 0.05 + i * 0.3)
        tid, k = rng.randint(0, 5000), 0
        t += 0.05
        while t < end:
            fc, addr, qty = plan[k % len(plan)]
            conn.request(t, proto.mb_read_req(tid, fc, addr, qty))
            conn.reply(t + latency(), proto.mb_read_resp(tid, fc, qty, rng))
            tid, k = tid + 1, k + 1
            t += 2.0 + jitter()

    # --- HMI-01 polls PLC-MAIN-01 every 1 s; operators occasionally change a setpoint (FC06) ---
    conn = net.tcp(hmi, plc, 502)
    t = conn.open(pre + 0.02)
    tid, k = rng.randint(0, 5000), 0
    while t < end:
        fc, addr, qty = HMI_READS[k % 2]
        conn.request(t, proto.mb_read_req(tid, fc, addr, qty))
        conn.reply(t + latency(), proto.mb_read_resp(tid, fc, qty, rng))
        tid += 1
        p_write = 0.05 if _hour(t) in DAY_SHIFT else 0.035
        if rng.random() < p_write:
            reg, val = rng.choice(HMI_SETPOINT_REGS), rng.randint(0, 3000)
            tw = t + 0.3
            conn.request(tw, proto.mb_write_single_req(tid, reg, val))
            conn.reply(tw + latency(), proto.mb_write_single_resp(tid, reg, val))
            tid += 1
        k += 1
        t += 1.0 + jitter()

    # --- HISTORIAN subscribes to SCADA-SVR over OPC UA: 3 subscriptions, each publishing every 5 s ---
    hist, scada = ip("HISTORIAN"), ip("SCADA-SVR")
    restart_at = t0 + rng.uniform(1.0, 4.0) * 3600  # nightly historian service restart
    t, session = pre + 0.4, 0
    while t < end and session < 2:
        conn = net.tcp(hist, scada, 4840)
        t = conn.open(t)
        conn.request(t, proto.ua_hello(f"opc.tcp://{scada}:4840/palanca"))
        conn.reply(t + 0.002, proto.ua_ack())
        t += 0.01
        chan, token = rng.randint(1, 10**6), 1
        seq_c, seq_s, req_id = 51, 1, 1
        conn.request(t, proto.ua_open_req(t, seq_c, req_id))
        conn.reply(t + 0.003, proto.ua_open_resp(t, chan, token, seq_s, req_id))
        t += 1.0
        notif = {sid: 1 for sid, _ in OPC_SUBSCRIPTIONS}
        stop = restart_at if session == 0 else end
        while t < min(stop, end):
            for k, (sid, items) in enumerate(OPC_SUBSCRIPTIONS):
                ts = t + k * 0.35
                seq_c, seq_s, req_id = seq_c + 1, seq_s + 1, req_id + 1
                ack = (sid, notif[sid] - 1) if notif[sid] > 1 else None
                conn.request(ts, proto.ua_publish_req(ts, chan, token, seq_c, req_id, req_id, ack))
                conn.reply(ts + latency(), proto.ua_publish_resp(ts, chan, token, seq_s, req_id, req_id, notif[sid],
                                                                 items, rng, sub_id=sid))
                notif[sid] += 1
            t += 5.0 + jitter(0.01)
        if t < end:
            conn.close(t)
            t += rng.uniform(20, 40)  # service restart
        session += 1

    # --- HMI-01 keeps the SCADA web interface open (HTTPS) and refreshes it. The web server closes a
    #     keep-alive connection after HTTPS_KEEPALIVE requests; the browser reconnects and resumes its
    #     TLS session. The first reconnect falls right after the capture starts, so every HTTPS
    #     connection's handshake (and its MSS) is in the capture. ---
    session_id = rng.randbytes(32)
    t = t0 + rng.uniform(0.5, HTTPS_INTERVAL)
    while t < end:
        conn = net.tcp(hmi, scada, 443)
        t = conn.open(t)
        conn.request(t, proto.tls_client_hello(rng, "scada-svr", session_id))
        t += 0.004
        conn.reply(t, proto.tls_server_resume(rng, session_id))
        t += 0.002
        conn.request(t, proto.tls_client_finish(rng))
        t += 0.001
        for _ in range(HTTPS_KEEPALIVE):
            if t >= end:
                break
            conn.request(t, proto.tls_app_data(rng, rng.randint(*HTTPS_REQ)))
            conn.reply(t + rng.uniform(0.015, 0.04), proto.tls_app_data(rng, rng.randint(*HTTPS_RESP)))
            t += HTTPS_INTERVAL + jitter(0.3)
        if t < end:
            tc = t - HTTPS_INTERVAL + 5.0  # server's keep-alive limit reached: close_notify, then FIN
            conn.reply(tc, proto.tls_close_notify(rng))
            conn.ack_from_client(tc + 0.0005)
            conn.close(tc + 0.001, by_server=True)
            t += 0.05

    # --- NMS polls every switch with SNMPv2c every 60 s: interface counters + health (CPU, memory) ---
    nms = ip("NMS")
    switches = [a["ip"] for a in profile.assets if "switch" in a["role"].lower()]
    for j, sw in enumerate(switches):
        t, req, sport = pre + 3 + j * 0.5, rng.randint(1000, 10**6), net.ephemeral_port()
        octets = [rng.randint(10**6, 10**8) for _ in range(4)]
        while t < end:
            net.udp(t, nms, sw, sport, 161, proto.snmp_get(req, proto.SNMP_IF_OIDS))
            octets = [o + rng.randint(40000, 60000) for o in octets]
            vals = []
            for port in range(2):
                vals += [(proto.SNMP_IF_OIDS[port * 4], 0x41, octets[port * 2]),
                         (proto.SNMP_IF_OIDS[port * 4 + 1], 0x41, octets[port * 2 + 1]),
                         (proto.SNMP_IF_OIDS[port * 4 + 2], 0x41, 0), (proto.SNMP_IF_OIDS[port * 4 + 3], 0x41, 0)]
            net.udp(t + latency(), sw, nms, 161, sport, proto.snmp_response(req, vals))
            req += 1
            th = t + 0.2
            net.udp(th, nms, sw, sport, 161, proto.snmp_get(req, proto.SNMP_HEALTH_OIDS))
            up = int((th - pre) * 100) + 360000000
            hv = [(proto.SNMP_HEALTH_OIDS[0], 0x43, up), (proto.SNMP_HEALTH_OIDS[1], 0x02, rng.randint(3, 18)),
                  (proto.SNMP_HEALTH_OIDS[2], 0x02, rng.randint(52000, 56000)), (proto.SNMP_HEALTH_OIDS[3], 0x02, 131072)]
            net.udp(th + latency(), sw, nms, 161, sport, proto.snmp_response(req, hv))
            req += 1
            t += 60.0 + jitter(0.02)

    # --- ENG-WS opens the PLC diagnostics web page now and then, day shift only ---
    eng = ip("ENG-WS")
    t = t0 + rng.uniform(600, 3600)
    while t < end:
        if _hour(t) in DAY_SHIFT:
            for _page in range(rng.randint(1, 3)):
                c = net.tcp(eng, plc, 80)
                tt = c.open(t, 0.002)
                c.request(tt, proto.http_get("plc-main-01"))
                c.reply(tt + 0.02, proto.http_response(rng, rng.randint(1000, 1100)))
                c.ack_from_client(tt + 0.021)
                c.close(tt + 0.03)
                t += rng.uniform(5, 40)
        t += rng.uniform(1800, 5400)

    # --- ARP: every talker re-resolves its peers and its gateway every 21-41 s (Windows-style cache timers) ---
    gw_for = {"1": ip("SW-CORE-01"), "2": ip("SW-CORE-01"), "3": ip("SW-DMZ-01")}
    pairs = [(plc, ip(d)) for d in POLL_PLAN] + [(hmi, plc), (hist, scada), (eng, plc), (hmi, scada)]
    pairs += [(a["ip"], gw_for[a["ip"].split(".")[2]]) for a in profile.assets
              if a["ip"] not in gw_for.values()]
    for asker, target in pairs:
        t = t0 + rng.uniform(0.001, ARP_REFRESH[1])
        while t < end:
            net.arp_exchange(t, asker, target)
            t += rng.uniform(*ARP_REFRESH)

    # --- Background services ("other" traffic): NTP, syslog, Windows name resolution & discovery ---
    for a in profile.assets:
        if a["ip"] in gw_for.values():
            continue
        server = gw_for[a["ip"].split(".")[2]]
        sport = 123 if a["ip"].startswith("192.168.1.") else net.ephemeral_port()
        t = t0 + rng.uniform(0, NTP_POLL)
        while t < end:
            net.udp(t, a["ip"], server, sport, 123, proto.ntp_request(t))
            tr = t + latency()
            net.udp(tr, server, a["ip"], 123, sport, proto.ntp_response(t, tr))
            t += NTP_POLL + jitter(0.5)
    for sw in sorted(set(gw_for.values())):
        t = t0 + rng.uniform(*SYSLOG_EVERY)
        while t < end:
            net.udp(t, sw, nms, 514, 514, proto.syslog_msg(t, profile.name(sw), rng))
            t += rng.uniform(*SYSLOG_EVERY)
    for name in WINDOWS_HOSTS:
        h = ip(name)
        bcast = ".".join(h.split(".")[:3]) + ".255"
        t = t0 + rng.uniform(0, 30)
        while t < end:  # NetBIOS name query (broadcast), every ~25 s
            net.udp(t, h, bcast, 137, 137, proto.nbns_query(rng.randint(0, 65535), rng.choice(["WPAD", "FILESRV01", "PRINT01"])))
            t += rng.uniform(15, 35)
        t = t0 + rng.uniform(0, 45)
        while t < end:  # LLMNR lookup for 'wpad' (multicast), every ~45 s
            net.udp(t, h, "224.0.0.252", net.ephemeral_port(), 5355, proto.llmnr_query(rng.randint(0, 65535), "wpad"))
            t += rng.uniform(30, 60)
        t = t0 + rng.uniform(0, 120)
        while t < end:  # SSDP discovery burst (multicast), every ~85 s
            sp = net.ephemeral_port()
            for k in range(4):
                net.udp(t + k * 0.001, h, "239.255.255.250", sp, 1900, proto.ssdp_msearch())
            t += rng.uniform(65, 105)

    recs = [r for r in net.out if t0 <= r[0] < end]
    recs.sort(key=lambda r: r[0])
    return recs
