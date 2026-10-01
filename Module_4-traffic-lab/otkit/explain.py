"""
Day 2: explain a packet byte by byte (Module 4, Section 4.2.2).

    otlab explain captures/palanca_baseline_24h.pcap --frame 5
    otlab explain --hex "00 01 00 00 00 06 01 03 00 00 00 0a"

Shows every field of the Modbus/TCP frame: the 7-byte MBAP header
(Transaction ID, Protocol ID, Length, Unit ID) and the PDU (Function
Code + data), with what each value means.
"""
import os
import struct
import sys

from .load import _iter_frames, _l3_start

FUNCTION_CODES = {
    1: ("Read Coils", "read"), 2: ("Read Discrete Inputs", "read"), 3: ("Read Holding Registers", "read"),
    4: ("Read Input Registers", "read"), 5: ("Write Single Coil", "WRITE"), 6: ("Write Single Register", "WRITE"),
    7: ("Read Exception Status", "diag"), 8: ("Diagnostics", "diag"), 11: ("Get Comm Event Counter", "diag"),
    15: ("Write Multiple Coils", "WRITE"), 16: ("Write Multiple Registers", "WRITE"),
    17: ("Report Server ID", "diag"), 22: ("Mask Write Register", "WRITE"),
    23: ("Read/Write Multiple Registers", "WRITE"), 43: ("Read Device Identification", "diag"),
    90: ("Schneider UMAS (vendor programming)", "PROGRAM"),
}
EXCEPTIONS = {1: "Illegal Function", 2: "Illegal Data Address", 3: "Illegal Data Value",
              4: "Server Device Failure", 5: "Acknowledge", 6: "Server Device Busy",
              10: "Gateway Path Unavailable", 11: "Gateway Target Failed to Respond"}

_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
B, D, R = ("\033[1m", "\033[2m", "\033[0m") if _TTY else ("", "", "")


def _hex(b):
    return " ".join(f"{x:02x}" for x in b)


def _row(offset, raw, field, value, meaning=""):
    return f"  {offset:>4}  {_hex(raw):<24} {B}{field:<22}{R} {str(value):<10} {D}{meaning}{R}"


def explain_modbus(payload, is_request=None):
    out = []
    if len(payload) < 8:
        return ["  (too short to be Modbus/TCP: needs at least 8 bytes)"]
    tid, pid, length, unit = struct.unpack("!HHHB", payload[:7])
    fc_raw = payload[7]
    out.append(f"\n  {B}Modbus/TCP ADU{R}  ({len(payload)} bytes)   = MBAP header (7 bytes) + PDU ({len(payload) - 7} bytes)")
    out.append(f"  {'byte':>4}  {'hex':<24} {'field':<22} {'value':<10} meaning")
    out.append("  " + "-" * 92)
    out.append(_row(0, payload[0:2], "Transaction ID", tid, "matches a request to its response"))
    out.append(_row(2, payload[2:4], "Protocol ID", pid, "always 0 for Modbus" + ("" if pid == 0 else "  <-- NOT 0: suspicious!")))
    out.append(_row(4, payload[4:6], "Length", length, f"bytes that follow = Unit ID + PDU ({length - 1} bytes of PDU)"))
    out.append(_row(6, payload[6:7], "Unit ID", unit, "which device behind a gateway (often 1 or 255)"))
    out.append("  " + "- " * 46)
    exc = bool(fc_raw & 0x80)
    fc = fc_raw & 0x7F
    name, kind = FUNCTION_CODES.get(fc, ("Unknown / vendor-specific", "?"))
    if exc:
        out.append(_row(7, payload[7:8], "Function Code", f"0x{fc_raw:02x}", f"0x80 + FC{fc:02d} = EXCEPTION reply to '{name}'"))
        if len(payload) > 8:
            code = payload[8]
            out.append(_row(8, payload[8:9], "Exception Code", code, EXCEPTIONS.get(code, "unknown")))
        return out
    tag = {"WRITE": "  <-- WRITE: changes the device!", "diag": "  <-- diagnostic / identification",
           "PROGRAM": "  <-- PROGRAMMING function"}.get(kind, "")
    out.append(_row(7, payload[7:8], "Function Code", fc, f"FC{fc:02d} {name}{tag}"))
    pdu = payload[8:]
    if is_request is None:
        is_request = True
    if fc in (1, 2, 3, 4):
        if is_request and len(pdu) >= 4:
            addr, qty = struct.unpack("!HH", pdu[:4])
            out.append(_row(8, pdu[0:2], "Starting Address", addr, f"first {'coil/input' if fc < 3 else 'register'} to read (0-based)"))
            out.append(_row(10, pdu[2:4], "Quantity", qty, f"read {qty} item(s): {addr}..{addr + qty - 1}"))
        elif len(pdu) >= 1:
            n = pdu[0]
            out.append(_row(8, pdu[0:1], "Byte Count", n, "number of data bytes that follow"))
            if fc in (3, 4):
                regs = [struct.unpack("!H", pdu[1 + i:3 + i])[0] for i in range(0, min(n, len(pdu) - 1) - 1, 2)]
                show = ", ".join(str(r) for r in regs[:8]) + (" ..." if len(regs) > 8 else "")
                out.append(_row(9, pdu[1:min(1 + n, 9)], "Register values", f"{len(regs)} regs", show))
            else:
                out.append(_row(9, pdu[1:min(1 + n, 9)], "Coil/input bits", f"{n} bytes", "1 bit per coil, LSB first"))
    elif fc in (5, 6) and len(pdu) >= 4:
        addr, val = struct.unpack("!HH", pdu[:4])
        out.append(_row(8, pdu[0:2], "Address", addr, "coil/register being written"))
        meaning = ("0xFF00 = ON, 0x0000 = OFF" if fc == 5 else "new value") + ("  (a reply echoes the request)" if not is_request else "")
        out.append(_row(10, pdu[2:4], "Value", val, meaning))
    elif fc in (15, 16) and len(pdu) >= 4:
        addr, qty = struct.unpack("!HH", pdu[:4])
        out.append(_row(8, pdu[0:2], "Starting Address", addr, "first item being written"))
        out.append(_row(10, pdu[2:4], "Quantity", qty, f"items {addr}..{addr + qty - 1}"))
        if is_request and len(pdu) >= 5:
            out.append(_row(12, pdu[4:5], "Byte Count", pdu[4], "data bytes that follow"))
            if fc == 16:
                vals = [struct.unpack("!H", pdu[5 + i:7 + i])[0] for i in range(0, min(pdu[4], len(pdu) - 5) - 1, 2)]
                out.append(_row(13, pdu[5:13], "Values", f"{len(vals)} regs", ", ".join(map(str, vals[:8]))))
    elif pdu:
        out.append(_row(8, pdu[:8], "Data", f"{len(pdu)} bytes", "function-specific data"))
    return out


def explain_frame(fr, linktype=1):
    out = []
    hdr = _l3_start(linktype, fr)
    if not hdr:
        return ["  Unsupported link type."]
    et, o, esrc, edst = hdr
    out.append(f"  {B}Ethernet{R}  {esrc} -> {edst}   type 0x{et:04x} "
               f"({'IPv4' if et == 0x0800 else 'ARP' if et == 0x0806 else 'other'})")
    if et == 0x0806:
        op = (fr[o + 6] << 8) | fr[o + 7]
        smac, sip = fr[o + 8:o + 14].hex(":"), ".".join(map(str, fr[o + 14:o + 18]))
        tip = ".".join(map(str, fr[o + 24:o + 28]))
        out.append(f"  {B}ARP{R} {'request: who has ' + tip + '? tell ' + sip if op == 1 else 'reply: ' + sip + ' is at ' + smac}")
        if op == 2:
            out.append(f"  {D}If this MAC is not the real owner of {sip}, this is ARP spoofing (a man-in-the-middle attempt).{R}")
        return out
    if et != 0x0800:
        return out
    ihl = (fr[o] & 0x0F) * 4
    proto = fr[o + 9]
    src, dst = ".".join(map(str, fr[o + 12:o + 16])), ".".join(map(str, fr[o + 16:o + 20]))
    out.append(f"  {B}IPv4{R}      {src} -> {dst}   TTL {fr[o + 8]}   protocol {proto} "
               f"({'TCP' if proto == 6 else 'UDP' if proto == 17 else '?'})")
    t = o + ihl
    if proto == 6:
        sp, dp = struct.unpack("!HH", fr[t:t + 4])
        seq, ack = struct.unpack("!II", fr[t + 4:t + 12])
        flags = fr[t + 13]
        names = [n for bit, n in ((2, "SYN"), (16, "ACK"), (8, "PSH"), (1, "FIN"), (4, "RST")) if flags & bit]
        payload = fr[t + (fr[t + 12] >> 4) * 4: o + ((fr[o + 2] << 8) | fr[o + 3])]
        out.append(f"  {B}TCP{R}       port {sp} -> {dp}   flags [{', '.join(names)}]   seq {seq}  ack {ack}   payload {len(payload)} bytes")
        if flags & 2 and not flags & 16:
            out.append(f"  {D}SYN without ACK = the first packet of a new connection (many of these to different ports = a scan).{R}")
        if payload and 502 in (sp, dp):
            out.append(f"  {D}Port 502 -> this is Modbus/TCP. {'Sent TO 502: a REQUEST (query) from a master.' if dp == 502 else 'Sent FROM 502: a RESPONSE from the device.'}{R}")
            out += explain_modbus(payload, is_request=(dp == 502))
        elif payload:
            out.append(f"  payload: {_hex(payload[:32])}{' ...' if len(payload) > 32 else ''}")
    elif proto == 17:
        sp, dp = struct.unpack("!HH", fr[t:t + 4])
        out.append(f"  {B}UDP{R}       port {sp} -> {dp}")
    return out


def get_frame(path, number):
    for i, (ts, lt, fr) in enumerate(_iter_frames(path), start=1):
        if i == number:
            return ts, lt, fr
    raise SystemExit(f"Frame {number} not found (the capture has fewer packets).")
