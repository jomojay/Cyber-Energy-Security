#!/usr/bin/env python3
"""
Assessment helper: an unauthorised device sweeping the control segment.

How it differs from the legitimate polling master (traffic-gen, 192.168.1.200):
  - opens a NEW TCP connection for every poll (changing source ports)
  - reads 20 registers per request instead of 10
  - visits every device round-robin, including the fragile VFD
  - irregular timing instead of fixed per-device intervals
Trainees are expected to notice this difference in the capture (Section B1).
"""
import random
import socket
import time
from pymodbus.client import ModbusTcpClient

TARGETS = ["192.168.1.10", "192.168.1.11", "192.168.1.20", "192.168.1.21",
           "192.168.1.30", "192.168.1.31", "192.168.1.40"]

def sweep():
    for ip in TARGETS:
        client = ModbusTcpClient(ip, port=502, timeout=2)
        try:
            if client.connect():
                client.read_holding_registers(0, count=20)
        except Exception:
            pass
        finally:
            client.close()
        time.sleep(random.uniform(0.3, 1.0))

def touch_switch():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("192.168.1.1", 22))
    except Exception:
        pass
    finally:
        s.close()

if __name__ == "__main__":
    time.sleep(10)  # let the device simulators come up
    n = 0
    while True:
        sweep()
        n += 1
        if n % 10 == 0:
            touch_switch()
        time.sleep(random.uniform(3, 6))
