#!/usr/bin/env python3
"""
HISTORIAN-01 simulator: HTTP status page (port 80, as in the Module 2
lab) plus plain accept/close stub listeners on whatever EXTRA_PORTS the
Module 3 Day 4 firewall ruleset expects a DMZ historian to expose —
4840 for R05 (Supervisory->DMZ OPC-UA ingest) and 443 for R09/R10
(Enterprise->DMZ dashboards/VPN). These are not real OPC-UA/TLS
endpoints: the firewall filters by port, not payload, so a stub is
enough to prove each rule allows or denies the traffic it names.

Env vars:
  DEVICE_NAME   e.g. HISTORIAN-01 (used in logs only)
  EXTRA_PORTS   comma-separated TCP ports to open as stubs, e.g. "4840,443"
"""
import os
import socket
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("historian-sim")

DEVICE_NAME = os.environ.get("DEVICE_NAME", "HISTORIAN-01")
EXTRA_PORTS = [int(p) for p in os.environ.get("EXTRA_PORTS", "").split(",") if p.strip()]


class HistorianHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = f"""<html><head><title>{DEVICE_NAME}</title></head>
        <body style="font-family:sans-serif">
        <h2>{DEVICE_NAME} — Palanca Gas Plant Historian (Lab Simulation)</h2>
        <p>Status: <b>ONLINE</b></p>
        <p><i>This is a lab simulation for training purposes only.</i></p>
        </body></html>"""
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # quiet down default HTTP logging


def http_serve():
    HTTPServer(("0.0.0.0", 80), HistorianHandler).serve_forever()


def stub_listener(port):
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
    log.info(f"Starting {DEVICE_NAME} — HTTP on 0.0.0.0:80" + (f", stubs on {EXTRA_PORTS}" if EXTRA_PORTS else ""))
    for p in EXTRA_PORTS:
        threading.Thread(target=stub_listener, args=(p,), daemon=True).start()
    http_serve()
