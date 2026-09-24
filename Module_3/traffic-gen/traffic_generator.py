#!/usr/bin/env python3
"""
Ambient traffic generator for the Palanca lab. Continuously polls
every Modbus device (mirroring a real SCADA polling cycle) so that
a passive capture (Lab Day 1) actually shows realistic, ongoing
OT communication instead of a silent network.
"""
import time
import random
import logging
from pymodbus.client import ModbusTcpClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("traffic-gen")

# device_name: (host, poll_interval_seconds)
TARGETS = {
    "PLC-MAIN-01":  ("plc-main-01", 2),
    "PLC-AUX-01":   ("plc-aux-01", 2),
    "GEN1-RTU":     ("gen1-rtu", 3),
    "GEN2-RTU":     ("gen2-rtu", 3),
    "PROT-REL-01":  ("prot-rel-01", 5),
    "PROT-REL-02":  ("prot-rel-02", 5),
    "VFD-PUMP-01":  ("vfd-pump-01", 4),
}

def poll_forever():
    clients = {name: ModbusTcpClient(host, port=502) for name, (host, _) in TARGETS.items()}
    last_poll = {name: 0 for name in TARGETS}
    log.info("Traffic generator online — polling %d simulated devices", len(TARGETS))
    while True:
        now = time.time()
        for name, (host, interval) in TARGETS.items():
            if now - last_poll[name] < interval:
                continue
            last_poll[name] = now
            client = clients[name]
            try:
                if not client.connected:
                    client.connect()
                client.read_holding_registers(0, count=10)
            except Exception as e:
                log.warning("%s poll failed: %s", name, e)
        time.sleep(0.5)

if __name__ == "__main__":
    time.sleep(5)  # let device sims come up first
    poll_forever()
