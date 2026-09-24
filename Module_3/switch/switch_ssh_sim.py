#!/usr/bin/env python3
"""
SW-CORE-01 simulator: a real SSH server (paramiko) that answers a
restricted set of Cisco-style commands trainees actually use in
Lab Day 2 — 'show mac-address-table' and 'show arp' — built from the
container's LIVE arp/neighbour cache, so the output reflects real
traffic on the lab network rather than canned text.

Login: admin / palanca-lab  (matches the Lab pack credential sheet)
"""
import socket
import threading
import subprocess
import paramiko
import sys
import os
import time

HOST_KEY = paramiko.RSAKey.generate(2048)
USERNAME = "admin"
PASSWORD = "palanca-lab"

BANNER = """
Palanca Offshore Platform — SW-CORE-01 (Cisco Catalyst 2960X, lab simulation)
Authorized access only.
"""

def send_text(chan, text):
    """Send text over a raw SSH channel with correct line endings.

    A bare '\\n' only moves a raw pty's cursor down a line without
    returning it to column 0 — every line after the first then starts
    wherever the previous one ended, producing a cascading "staircase"
    of indentation. get_mac_table()/get_arp_table()/BANNER are built
    with plain '\\n' for readability in the source, so normalize here
    rather than requiring every caller to remember to do it.
    """
    chan.send(text.replace("\r\n", "\n").replace("\n", "\r\n").encode())

# A container's own ARP cache (`ip neigh`) only records hosts THIS
# container has directly resolved at the IP layer — unlike a real
# switch's promiscuously-learned MAC table, it does not passively see
# traffic between other pairs on the bridge. Since nothing else in
# this stack makes sw-core-01 talk to the OT devices, its ARP cache
# would otherwise sit empty and "show mac-address-table"/"show arp"
# would return nothing. This background loop manufactures that
# traffic (any TCP attempt forces ARP resolution first, whether or
# not the port is actually open) so the tables have real entries.
KNOWN_HOSTS = [
    "192.168.1.10",   # plc-main-01
    "192.168.1.11",   # plc-aux-01
    "192.168.1.20",   # gen1-rtu
    "192.168.1.21",   # gen2-rtu
    "192.168.1.30",   # prot-rel-01
    "192.168.1.31",   # prot-rel-02
    "192.168.1.40",   # vfd-pump-01
    "192.168.1.200",  # traffic-gen
    "192.168.2.10",   # scada-hmi-01
    "192.168.2.11",   # scada-hmi-02
    "192.168.2.20",   # eng-ws-01
    # Module 3 Day 4 note: scada-hmi-01/02 and eng-ws-01 no longer have a
    # second, control-side IP here (that dual-homing was the Day 5 flat-
    # network finding, removed for the Day 4 firewall exercise — see
    # ../docker-compose.yml), and historian-01 is single-homed on ot_dmz
    # only now, so it's no longer reachable from sw-core-01 at all.
]

def arp_populator():
    while True:
        for ip in KNOWN_HOSTS:
            for port in (502, 80, 4840, 22):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.3)
                    s.connect_ex((ip, port))
                    s.close()
                except OSError:
                    pass
        time.sleep(10)

def vlan_for_ip(ip):
    """Map an IP to its simulated VLAN — mirrors the topology's Purdue
    zones (ot_control=10, ot_supervisory=20, ot_dmz=30). Shared by both
    tables below so they never disagree on which VLAN a device is on."""
    if ip.startswith("192.168.1."):
        return "10"
    if ip.startswith("192.168.2."):
        return "20"
    return "30"

def get_mac_table():
    try:
        out = subprocess.check_output(["ip", "neigh"], text=True)
    except Exception as e:
        return f"error reading neighbour table: {e}"
    lines = ["          Mac Address Table",
             "-------------------------------------------",
             "Vlan    Mac Address       Type    Ports",
             "----    -----------       ----    -----"]
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 5 and "lladdr" in parts:
            ip = parts[0]
            mac = parts[parts.index("lladdr") + 1]
            vlan = vlan_for_ip(ip)
            lines.append(f"{vlan:<8}{mac:<18}DYNAMIC Gi0/{sum(bytearray.fromhex(mac.replace(':', ''))) % 24 + 1}")
    return "\n".join(lines)

def get_arp_table():
    try:
        out = subprocess.check_output(["ip", "neigh"], text=True)
    except Exception as e:
        return f"error reading arp table: {e}"
    lines = ["Protocol  Address          Age  Hardware Addr   Type  Interface"]
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) >= 5 and "lladdr" in parts:
            ip = parts[0]
            mac = parts[parts.index("lladdr") + 1]
            lines.append(f"Internet  {ip:<16} 0    {mac:<15} ARPA  Vlan{vlan_for_ip(ip)}")
    return "\n".join(lines)

class SwitchSSHServer(paramiko.ServerInterface):
    def __init__(self):
        self.event = threading.Event()
    def check_auth_password(self, username, password):
        if username == USERNAME and password == PASSWORD:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED
    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    def check_channel_shell_request(self, channel):
        self.event.set()
        return True
    def check_channel_pty_request(self, *args, **kwargs):
        return True

# How long an idle session (no bytes sent by the client at all) is allowed to
# sit before the server closes it — generous enough that a trainee reading
# output doesn't get kicked, but bounded so a connection can't hold a thread
# and a paramiko.Transport open forever.
#
# This matters more than it looks: a client that vanishes without a clean
# TCP close — a laptop sleeping, wifi dropping, a terminal force-closed — sends
# no FIN/RST at all. Without a timeout here, chan.recv() below blocks forever
# for that session: one leaked thread + one leaked Transport per occurrence,
# with nothing ever cleaning it up. Over a class of trainees on flaky wifi,
# that accumulates across a session until the host runs out of threads/file
# descriptors — which is what "hangs a lot, needs a restart" was.
IDLE_TIMEOUT = 1800  # 30 minutes


def handle_client(client_sock):
    # TCP keepalive so the kernel notices a genuinely dead peer (network gone,
    # not just idle) within minutes instead of the OS default of hours — a
    # second line of defense on top of IDLE_TIMEOUT below. Not available on
    # every platform, hence the guard.
    try:
        client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 15)
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 4)
    except (AttributeError, OSError):
        pass

    transport = paramiko.Transport(client_sock)
    chan = None
    try:
        transport.add_server_key(HOST_KEY)
        server = SwitchSSHServer()
        transport.start_server(server=server)
        chan = transport.accept(20)
        if chan is None:
            return
        server.event.wait(10)
        chan.settimeout(IDLE_TIMEOUT)
        send_text(chan, BANNER + "\nswitch> ")
        buf = ""
        in_escape = False   # swallowing an ANSI escape sequence (arrow keys etc.)
        skip_lf = False      # last byte processed was \r — ignore an immediately following \n
        while True:
            try:
                data = chan.recv(1024)
            except socket.timeout:
                break  # idle (or silently dead) too long — clean up rather than hang forever
            if not data:
                break
            for byte in data:
                if skip_lf:
                    skip_lf = False
                    if byte == 0x0a:  # \n right after \r we already handled — part of the same Enter
                        continue

                if in_escape:
                    # ANSI CSI sequences (arrow/function keys) end at a byte in 0x40-0x7E.
                    # Swallow everything up to and including it without touching buf, so
                    # pressing an arrow key can't corrupt the command being typed.
                    if 0x40 <= byte <= 0x7E:
                        in_escape = False
                    continue

                if byte == 0x1b:  # ESC — start of an escape sequence
                    in_escape = True
                elif byte in (0x0d, 0x0a):  # Enter (CR or LF)
                    if byte == 0x0d:
                        skip_lf = True
                    chan.send(b"\r\n")
                    cmd = buf.strip().lower()
                    buf = ""
                    if cmd in ("show mac-address-table", "show mac address-table"):
                        send_text(chan, get_mac_table() + "\nswitch> ")
                    elif cmd == "show arp":
                        send_text(chan, get_arp_table() + "\nswitch> ")
                    elif cmd in ("exit", "quit", "logout"):
                        chan.send(b"Connection closed.\r\n")
                        return
                    elif cmd == "":
                        chan.send(b"switch> ")
                    else:
                        send_text(chan, f"% Unknown command: {cmd}\nswitch> ")
                elif byte in (0x7f, 0x08):  # Backspace / Delete
                    if buf:
                        buf = buf[:-1]
                        chan.send(b"\b \b")  # move back, erase, move back again
                elif byte == 0x03:  # Ctrl+C — abandon the current line
                    buf = ""
                    chan.send(b"^C\r\nswitch> ")
                elif byte == 0x04:  # Ctrl+D — always closes the session, like a real shell on EOF
                    chan.send(b"\r\nConnection closed.\r\n")
                    return
                elif 0x20 <= byte < 0x7f:  # printable ASCII — the only bytes we keep
                    buf += chr(byte)
                    chan.send(bytes([byte]))
                # any other control byte is silently dropped instead of corrupting buf
    except Exception:
        # A malformed/incomplete SSH negotiation (a port scanner or health
        # check hitting :22, a client that drops mid-handshake) shouldn't
        # crash the sim or skip cleanup below — just abandon this session.
        pass
    finally:
        if chan is not None:
            try:
                chan.close()
            except Exception:
                pass
        transport.close()

def main():
    threading.Thread(target=arp_populator, daemon=True).start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 22))
    sock.listen(10)
    print("SW-CORE-01 SSH simulator listening on :22  (admin / palanca-lab)")
    while True:
        client, addr = sock.accept()
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()

if __name__ == "__main__":
    main()
