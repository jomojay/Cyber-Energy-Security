#!/usr/bin/env python3
"""
SCADA-HMI simulator: exposes an OPC-UA endpoint (port 4840, mirroring
live PLC values) and a minimal HTTP status page (port 80), matching
the two protocols the asset inventory records for SCADA-HMI-01/02.

EXTRA_PORTS (comma-separated) opens additional plain accept/close stub
listeners — Module 3 Day 4 uses this for port 443, so R06 (DMZ->
Supervisory HTTPS) has something on the Supervisory side to actually
allow/deny. Not a real TLS endpoint: the firewall filters by port, not
payload, so a stub is enough to prove the rule.
"""
import os
import random
import socket
import threading
import time
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

from opcua import Server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("hmi-sim")

DEVICE_NAME = os.environ.get("DEVICE_NAME", "SCADA-HMI-01")

# ---- OPC-UA server ----
opcua_server = Server()
opcua_server.set_endpoint("opc.tcp://0.0.0.0:4840/palanca/hmi/")
opcua_server.set_server_name(f"Palanca Lab — {DEVICE_NAME}")
idx = opcua_server.register_namespace("http://palanca.lab/hmi")
objects = opcua_server.get_objects_node()
plant = objects.add_object(idx, "PalancaPlant")
gen1_output = plant.add_variable(idx, "Generator1_Output_kW", 4200.0)
gen2_output = plant.add_variable(idx, "Generator2_Output_kW", 3950.0)
feeder_status = plant.add_variable(idx, "Feeders_Online", 11)
gen1_output.set_writable()
gen2_output.set_writable()

def opcua_drift():
    opcua_server.start()
    log.info(f"{DEVICE_NAME}: OPC-UA endpoint live on opc.tcp://0.0.0.0:4840/palanca/hmi/")
    try:
        while True:
            time.sleep(2)
            gen1_output.set_value(4200.0 + random.uniform(-50, 50))
            gen2_output.set_value(3950.0 + random.uniform(-50, 50))
    finally:
        opcua_server.stop()

# ---- Minimal HTTP status page (the "HMI web interface") ----
class HMIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = f"""<html><head><title>{DEVICE_NAME}</title></head>
        <body style="font-family:sans-serif">
        <h2>{DEVICE_NAME} — Palanca Gas Plant HMI (Lab Simulation)</h2>
        <p>Status: <b>ONLINE</b></p>
        <p>OPC-UA endpoint: opc.tcp://{DEVICE_NAME}:4840/palanca/hmi/</p>
        <p><i>This is a lab simulation for training purposes only.</i></p>
        </body></html>"""
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # quiet down default HTTP logging

def http_serve():
    HTTPServer(("0.0.0.0", 80), HMIHandler).serve_forever()

def stub_listener(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(5)
    log.info(f"{DEVICE_NAME}: extra stub listener up on :{port}")
    while True:
        conn, addr = s.accept()
        log.info(f"{DEVICE_NAME}: connection on :{port} from {addr[0]}")
        conn.close()

if __name__ == "__main__":
    threading.Thread(target=http_serve, daemon=True).start()
    for _port in [int(p) for p in os.environ.get("EXTRA_PORTS", "").split(",") if p.strip()]:
        threading.Thread(target=stub_listener, args=(_port,), daemon=True).start()
    opcua_drift()
