#!/usr/bin/env python3
"""
Runs inside SW-CORE-01's network namespace and briefly contacts every lab
address so the switch's neighbour (ARP) table holds an entry for each device.
Connection failures are irrelevant: the ARP resolution is the point.
"""
import socket
import time

HOSTS = ["192.168.1.10", "192.168.1.11", "192.168.1.20", "192.168.1.21",
         "192.168.1.30", "192.168.1.31", "192.168.1.40", "192.168.1.99",
         "192.168.1.110", "192.168.1.111", "192.168.1.120", "192.168.1.200",
         "192.168.2.10", "192.168.2.11", "192.168.2.20", "192.168.2.30"]

def poke(ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        s.connect((ip, 502))
    except Exception:
        pass
    finally:
        s.close()

if __name__ == "__main__":
    time.sleep(5)
    while True:
        for h in HOSTS:
            poke(h)
        time.sleep(15)
