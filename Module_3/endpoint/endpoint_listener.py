#!/usr/bin/env python3
"""
Generic zone-endpoint simulator for Module 3 Day 4 — used for
mgmt-ws-01, quarantine-host-01, and enterprise-ws-01. Opens a plain
accept/close stub on each port in PORTS so a firewall test has a real,
reachable service to connect to on the target host: an ALLOW test then
shows the connection actually succeeding end-to-end, and a DENY test
shows the firewall dropping the attempt before it ever reaches this
listener (a timeout), rather than the ambiguous case of "nothing was
listening anyway".

Env vars:
  DEVICE_NAME   used in logs only
  PORTS         comma-separated TCP ports to listen on, e.g. "1433"
"""
import os
import socket
import threading
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("endpoint")

DEVICE_NAME = os.environ.get("DEVICE_NAME", "endpoint")
PORTS = [int(p) for p in os.environ.get("PORTS", "").split(",") if p.strip()]


def listener(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(5)
    log.info(f"{DEVICE_NAME}: stub listener up on :{port}")
    while True:
        conn, addr = s.accept()
        log.info(f"{DEVICE_NAME}: connection on :{port} from {addr[0]}")
        conn.close()


if __name__ == "__main__":
    if not PORTS:
        log.warning(f"{DEVICE_NAME}: no PORTS configured — idling with no listeners")
    for p in PORTS:
        threading.Thread(target=listener, args=(p,), daemon=True).start()
    while True:
        time.sleep(3600)
