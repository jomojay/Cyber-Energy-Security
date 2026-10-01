"""
Application-layer payload builders: Modbus/TCP, OPC UA Binary, SNMPv2c,
HTTP and TPKT/COTP. Every payload is *valid* enough for Wireshark to
dissect it properly, so trainees see "Modbus/TCP", "OpcUa", "SNMP"
and "HTTP" in the Protocol column instead of "Malformed Packet".
"""
import struct

# ---------------------------------------------------------------------------
# Modbus/TCP
# ---------------------------------------------------------------------------

def mbap(tid, pdu, unit=1):
    return struct.pack("!HHHB", tid & 0xFFFF, 0, len(pdu) + 1, unit) + pdu


def mb_read_req(tid, fc, addr, qty, unit=1):
    return mbap(tid, struct.pack("!BHH", fc, addr, qty), unit)


def mb_read_resp(tid, fc, qty, rng, unit=1):
    if fc in (1, 2):  # coils / discrete inputs: packed bits
        nbytes = (qty + 7) // 8
        data = rng.randbytes(nbytes)
    else:  # registers: process values 0-4095 (12-bit analogue range)
        nbytes = qty * 2
        data = struct.pack(f"!{qty}H", *[rng.getrandbits(12) for _ in range(qty)])
    return mbap(tid, struct.pack("!BB", fc, nbytes) + data, unit)


def mb_write_single_req(tid, addr, value, unit=1):
    return mbap(tid, struct.pack("!BHH", 6, addr, value), unit)


def mb_write_single_resp(tid, addr, value, unit=1):
    return mb_write_single_req(tid, addr, value, unit)  # FC06 response echoes the request


def mb_write_multi_req(tid, addr, values, unit=1):
    body = b"".join(struct.pack("!H", v) for v in values)
    return mbap(tid, struct.pack("!BHHB", 16, addr, len(values), len(body)) + body, unit)


def mb_write_multi_resp(tid, addr, qty, unit=1):
    return mbap(tid, struct.pack("!BHH", 16, addr, qty), unit)


def mb_exception(tid, fc, code, unit=1):
    return mbap(tid, struct.pack("!BB", fc | 0x80, code), unit)


# ---------------------------------------------------------------------------
# OPC UA Binary (SecurityPolicy None)
# ---------------------------------------------------------------------------

_EPOCH_DELTA = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def _ua_datetime(ts):
    return struct.pack("<q", int((ts + _EPOCH_DELTA) * 10_000_000))


def _ua_string(s):
    if s is None:
        return struct.pack("<i", -1)
    b = s.encode()
    return struct.pack("<i", len(b)) + b


def _ua_nodeid(numeric):
    return struct.pack("<BBH", 0x01, 0, numeric)  # four-byte encoding, namespace 0


_NULL_NODEID = b"\x00\x00"
_NULL_EXTOBJ = b"\x00\x00\x00"


def _request_header(ts, handle):
    return (_NULL_NODEID + _ua_datetime(ts) + struct.pack("<II", handle, 0) + _ua_string(None) +
            struct.pack("<I", 10000) + _NULL_EXTOBJ)


def _response_header(ts, handle):
    return (_ua_datetime(ts) + struct.pack("<II", handle, 0) + b"\x00" + struct.pack("<i", -1) +
            _NULL_EXTOBJ)


def _ua_msg(msg_type, body):
    return msg_type + b"F" + struct.pack("<I", len(body) + 8) + body


def ua_hello(url):
    return _ua_msg(b"HEL", struct.pack("<IIIII", 0, 65536, 65536, 0, 0) + _ua_string(url))


def ua_ack():
    return _ua_msg(b"ACK", struct.pack("<IIIII", 0, 65536, 65536, 0, 0))


def _asym_header():
    return (_ua_string("http://opcfoundation.org/UA/SecurityPolicy#None") +
            struct.pack("<i", -1) + struct.pack("<i", -1))


def ua_open_req(ts, seq, req_id):
    body =(_ua_nodeid(446) + _request_header(ts, 1) + struct.pack("<I", 0) +  # ClientProtocolVersion
            struct.pack("<I", 0) +  # RequestType: Issue
            struct.pack("<I", 1) +  # MessageSecurityMode: None
            struct.pack("<i", 0) +  # ClientNonce: empty
            struct.pack("<I", 3600000))  # RequestedLifetime
    return _ua_msg(b"OPN", struct.pack("<I", 0) + _asym_header() + struct.pack("<II", seq, req_id) + body)


def ua_open_resp(ts, channel_id, token_id, seq, req_id):
    body = (_ua_nodeid(449) + _response_header(ts, 1) + struct.pack("<I", 0) +
            struct.pack("<II", channel_id, token_id) + _ua_datetime(ts) + struct.pack("<I", 3600000) +
            struct.pack("<i", 0))
    return _ua_msg(b"OPN", struct.pack("<I", channel_id) + _asym_header() + struct.pack("<II", seq, req_id) + body)


def _sym(channel_id, token_id, seq, req_id):
    return struct.pack("<IIII", channel_id, token_id, seq, req_id)


def ua_publish_req(ts, channel_id, token_id, seq, req_id, handle, ack=None):
    """ack: (subscription_id, sequence_number) of the last notification received, or None."""
    acks = struct.pack("<i", 0) if ack is None else struct.pack("<iII", 1, ack[0], ack[1])
    body = _ua_nodeid(826) + _request_header(ts, handle) + acks
    return _ua_msg(b"MSG", _sym(channel_id, token_id, seq, req_id) + body)


def ua_publish_resp(ts, channel_id, token_id, seq, req_id, handle, notif_seq, n_items, rng, sub_id=1):
    items = b""
    for i in range(n_items):
        # MonitoredItemNotification: ClientHandle + DataValue(value + source timestamp) of type Double
        items += struct.pack("<I", i + 1) + b"\x05" + b"\x0b" + struct.pack("<d", rng.uniform(0, 5000)) + _ua_datetime(ts)
    dcn = struct.pack("<i", n_items) + items + struct.pack("<i", -1)
    ext = _ua_nodeid(811) + b"\x01" + struct.pack("<i", len(dcn)) + dcn
    notification = struct.pack("<I", notif_seq) + _ua_datetime(ts) + struct.pack("<i", 1) + ext
    body = (_ua_nodeid(829) + _response_header(ts, handle) + struct.pack("<I", sub_id) +  # SubscriptionId
            struct.pack("<iI", 1, notif_seq) +  # AvailableSequenceNumbers
            b"\x00" + notification + struct.pack("<i", 0) + struct.pack("<i", -1))
    return _ua_msg(b"MSG", _sym(channel_id, token_id, seq, req_id) + body)


# ---------------------------------------------------------------------------
# SNMPv2c (BER)
# ---------------------------------------------------------------------------

def _ber_len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag, value):
    return bytes([tag]) + _ber_len(len(value)) + value


def _ber_int(v, tag=0x02):
    if v == 0:
        return _tlv(tag, b"\x00")
    b = v.to_bytes((v.bit_length() + 8) // 8, "big", signed=(tag == 0x02))
    return _tlv(tag, b)


def _ber_oid(oid):
    parts = [int(x) for x in oid.split(".")]
    out = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        enc = [p & 0x7F]
        p >>= 7
        while p:
            enc.insert(0, 0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(enc)
    return _tlv(0x06, out)


SNMP_HEALTH_OIDS = [
    "1.3.6.1.2.1.1.3.0",            # sysUpTime
    "1.3.6.1.2.1.25.3.3.1.2.1",     # hrProcessorLoad.1  (CPU %)
    "1.3.6.1.2.1.25.2.3.1.6.1",     # hrStorageUsed.1    (memory used)
    "1.3.6.1.2.1.25.2.3.1.5.1",     # hrStorageSize.1    (memory size)
]
SNMP_IF_OIDS = [f"1.3.6.1.2.1.2.2.1.{col}.{port}" for port in (1, 2) for col in (10, 16, 14, 20)]
# ifInOctets, ifOutOctets, ifInErrors, ifOutErrors for ports 1 and 2


def snmp_get(req_id, oids, community="public"):
    vbs = b"".join(_tlv(0x30, _ber_oid(o) + b"\x05\x00") for o in oids)
    pdu = _tlv(0xA0, _ber_int(req_id) + _ber_int(0) + _ber_int(0) + _tlv(0x30, vbs))
    return _tlv(0x30, _ber_int(1) + _tlv(0x04, community.encode()) + pdu)


def snmp_response(req_id, varbinds, community="public"):
    """varbinds: list of (oid, ber_tag, int_value). Tags: 0x02 Integer, 0x41 Counter32, 0x43 TimeTicks."""
    vbs = b"".join(_tlv(0x30, _ber_oid(o) + _ber_int(v & 0xFFFFFFFF if tag != 0x02 else v, tag)) for o, tag, v in varbinds)
    pdu = _tlv(0xA2, _ber_int(req_id) + _ber_int(0) + _ber_int(0) + _tlv(0x30, vbs))
    return _tlv(0x30, _ber_int(1) + _tlv(0x04, community.encode()) + pdu)


# ---------------------------------------------------------------------------
# HTTP (engineering workstation -> PLC diagnostics web page)
# ---------------------------------------------------------------------------

def http_get(host, path="/diagnostics"):
    return (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0)\r\n"
            f"Accept: text/html\r\nConnection: close\r\n\r\n").encode()


def http_response(rng, body_len=1100):
    rows = "".join(f"<tr><td>AI{i:02d}</td><td>{rng.randint(0, 5000)}</td></tr>" for i in range(60))
    body = f"<html><head><title>PLC diagnostics</title></head><body><table>{rows}</table></body></html>"
    body = body[:body_len].ljust(body_len)
    hdr = (f"HTTP/1.1 200 OK\r\nServer: PLC-WebServer/2.1\r\nContent-Type: text/html\r\n"
           f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n")
    return (hdr + body).encode()


# ---------------------------------------------------------------------------
# TPKT / COTP (ISO-TSAP on TCP 102 - the S7 PLC programming port)
# ---------------------------------------------------------------------------

def tpkt_cotp_cr():
    cotp = bytes([0x11, 0xE0, 0x00, 0x00, 0x00, 0x01, 0x00, 0xC0, 0x01, 0x0A,
                  0xC1, 0x02, 0x01, 0x00, 0xC2, 0x02, 0x01, 0x02])
    return struct.pack("!BBH", 3, 0, len(cotp) + 4) + cotp


def tpkt_cotp_cc():
    cotp = bytes([0x11, 0xD0, 0x00, 0x01, 0x00, 0x01, 0x00, 0xC0, 0x01, 0x0A,
                  0xC1, 0x02, 0x01, 0x00, 0xC2, 0x02, 0x01, 0x02])
    return struct.pack("!BBH", 3, 0, len(cotp) + 4) + cotp


def tpkt_cotp_data(data, last=True):
    cotp = bytes([0x02, 0xF0, 0x80 if last else 0x00])
    return struct.pack("!BBH", 3, 0, len(cotp) + len(data) + 4) + cotp + data



# ---------------------------------------------------------------------------
# TLS 1.2 (HMI -> SCADA web interface over HTTPS). The browser resumes a cached
# TLS session on each new TCP connection (abbreviated handshake), so the
# capture shows ClientHello / ServerHello / ChangeCipherSpec and then only
# encrypted records - no certificate exchange.
# ---------------------------------------------------------------------------

def _tls_record(ctype, body, version=0x0303):
    return struct.pack("!BHH", ctype, version, len(body)) + body


def _tls_handshake(htype, body):
    return struct.pack("!B", htype) + len(body).to_bytes(3, "big") + body


def _tls_ext(etype, data):
    return struct.pack("!HH", etype, len(data)) + data


def tls_client_hello(rng, server_name, session_id):
    suites = [0xC02F, 0xC030, 0xC02B, 0xC02C, 0xC013, 0xC014, 0x009C, 0x009D, 0x002F, 0x0035]
    sni = server_name.encode()
    exts = (_tls_ext(0x0000, struct.pack("!HBH", len(sni) + 3, 0, len(sni)) + sni) +       # server_name
            _tls_ext(0x0017, b"") +                                                       # extended_master_secret
            _tls_ext(0xFF01, b"\x00") +                                                    # renegotiation_info
            _tls_ext(0x000A, struct.pack("!HHH", 4, 0x001D, 0x0017)) +                     # supported_groups
            _tls_ext(0x000B, b"\x01\x00") +                                                # ec_point_formats
            _tls_ext(0x000D, struct.pack("!H6H", 12, 0x0401, 0x0501, 0x0601, 0x0403, 0x0503, 0x0804)) +
            _tls_ext(0x0023, b""))                                                        # session_ticket
    body = (struct.pack("!H", 0x0303) + rng.randbytes(32) + bytes([len(session_id)]) + session_id +
            struct.pack("!H", len(suites) * 2) + struct.pack(f"!{len(suites)}H", *suites) + b"\x01\x00" +
            struct.pack("!H", len(exts)) + exts)
    return _tls_record(22, _tls_handshake(1, body), version=0x0301)


def tls_server_resume(rng, session_id):
    """ServerHello (same session id = resumption) + ChangeCipherSpec + encrypted Finished, one TCP segment."""
    exts = _tls_ext(0xFF01, b"\x00") + _tls_ext(0x0017, b"")
    body = (struct.pack("!H", 0x0303) + rng.randbytes(32) + bytes([len(session_id)]) + session_id +
            struct.pack("!HB", 0xC030, 0) + struct.pack("!H", len(exts)) + exts)
    return _tls_record(22, _tls_handshake(2, body)) + tls_change_cipher_spec() + tls_encrypted(rng, 22, 40)


def tls_change_cipher_spec():
    return _tls_record(20, b"\x01")


def tls_encrypted(rng, ctype, size):
    """An encrypted record: 22 = Finished, 21 = Alert (close_notify), 23 = Application Data."""
    return _tls_record(ctype, rng.randbytes(size))


def tls_client_finish(rng):
    return tls_change_cipher_spec() + tls_encrypted(rng, 22, 40)


def tls_close_notify(rng):
    return tls_encrypted(rng, 21, 26)


def tls_app_data(rng, size):
    return tls_encrypted(rng, 23, size)


# ---------------------------------------------------------------------------
# Background services: NTP, syslog, NetBIOS, LLMNR, SSDP
# ---------------------------------------------------------------------------

_NTP_DELTA = 2208988800  # seconds between 1900-01-01 and 1970-01-01


def _ntp_ts(t):
    sec = int(t) + _NTP_DELTA
    return struct.pack("!II", sec & 0xFFFFFFFF, int((t % 1) * 2**32))


def ntp_request(t):
    return struct.pack("!BBbb", 0x23, 0, 6, -23) + b"\x00" * 36 + _ntp_ts(t)  # v4, mode 3 (client)


def ntp_response(t_req, t_resp, ref_id=b"GPS\x00"):
    return (struct.pack("!BBbb", 0x24, 1, 6, -23) + struct.pack("!II", 0, 0x10) + ref_id +  # v4, mode 4, stratum 1
            _ntp_ts(t_resp - 16) + _ntp_ts(t_req) + _ntp_ts(t_resp - 0.0001) + _ntp_ts(t_resp))


SYSLOG_MESSAGES = [
    "%SYS-6-CLOCKUPDATE: System clock has been updated via NTP",
    "%PLATFORM_ENV-6-TEMP_OK: Chassis temperature normal (38C)",
    "%PLATFORM_ENV-6-FAN_OK: All fans operating normally",
    "%STORM_CONTROL-6-OK: Broadcast levels on all ports within limits",
    "%SNMP-6-POLL: SNMP request from 192.168.2.50 answered",
]


def syslog_msg(t, host, rng):
    import datetime as _dt
    stamp = _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%b %d %H:%M:%S")
    return f"<190>{stamp} {host}: {rng.choice(SYSLOG_MESSAGES)}".encode()


def _nb_name(name):
    raw = name.upper().ljust(15)[:15] + "\x00"
    enc = "".join(chr(0x41 + (ord(c) >> 4)) + chr(0x41 + (ord(c) & 0xF)) for c in raw)
    return b"\x20" + enc.encode() + b"\x00"


def nbns_query(tid, name):
    return struct.pack("!HHHHHH", tid, 0x0110, 1, 0, 0, 0) + _nb_name(name) + struct.pack("!HH", 0x20, 1)


def llmnr_query(tid, name):
    labels = b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\x00"
    return struct.pack("!HHHHHH", tid, 0, 1, 0, 0, 0) + labels + struct.pack("!HH", 1, 1)


def ssdp_msearch(st="urn:dial-multiscreen-org:service:dial:1"):
    return ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\n"
            f"ST: {st}\r\nUSER-AGENT: Microsoft-Windows/10.0 UPnP/1.0\r\n\r\n").encode()
