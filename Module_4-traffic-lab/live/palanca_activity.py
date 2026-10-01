#!/usr/bin/env python3
"""
Operator / engineer activity generator for the Module 2 live lab.

The Module 2 lab's traffic-gen only ever READS Modbus registers (FC03),
and nothing in it talks OPC UA. For Module 4 Days 1-2 you need more to
look at, so this script plays the part of the operators and engineers:

  * OPC UA sessions to SCADA-HMI-01 (connect -> browse -> read -> subscribe
    -> publish/subscribe for ~60 s -> disconnect), every few minutes
  * Modbus FC06 (write single register) and FC16 (write multiple registers)
    setpoint changes to PLC-MAIN-01, every 20-40 s
  * an HTTP request to the HMI web page every couple of minutes

Every action is printed with a timestamp so you can find it in Wireshark.

It runs INSIDE the eng-ws-01 container (which already has pymodbus and
opcua installed). You normally start it with:   ./otlab live activity
"""
import argparse
import random
import time
import urllib.request


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def modbus_write(host):
    from pymodbus.client import ModbusTcpClient
    c = ModbusTcpClient(host, port=502, timeout=3)
    try:
        if not c.connect():
            log(f"[Modbus] could not connect to {host}:502 (Module 3 stack: allowed by the fw-ot-01 rules?)")
            return
        if random.random() < 0.7:
            reg, val = random.randint(20, 29), random.randint(100, 3000)
            c.write_register(reg, val, slave=1)
            log(f"[Modbus] FC06 Write Single Register  -> {host} register {reg} = {val}")
        else:
            reg, vals = random.randint(30, 40), [random.randint(0, 1000) for _ in range(3)]
            c.write_registers(reg, vals, slave=1)
            log(f"[Modbus] FC16 Write Multiple Registers -> {host} registers {reg}-{reg + 2} = {vals}")
    except Exception as e:  # keep going - this is a traffic generator, not a controller
        log(f"[Modbus] write failed: {e}")
    finally:
        c.close()


class _Handler:
    def __init__(self):
        self.n = 0

    def datachange_notification(self, node, val, data):
        self.n += 1


def opcua_session(host, seconds):
    from opcua import Client
    url = f"opc.tcp://{host}:4840/palanca/hmi/"
    c = Client(url, timeout=5)
    try:
        c.connect()  # Hello / Acknowledge, OpenSecureChannel, CreateSession, ActivateSession
        log(f"[OPC UA] session OPENED to {url}  (look for Hello, OpenSecureChannel, CreateSession, ActivateSession)")
        objs = c.get_objects_node()
        plant = [n for n in objs.get_children() if "PalancaPlant" in n.get_browse_name().Name]
        variables = plant[0].get_children() if plant else []
        for v in variables:
            log(f"[OPC UA]   read {v.get_browse_name().Name} = {v.get_value()}")
        h = _Handler()
        sub = c.create_subscription(1000, h)  # CreateSubscription -> Publish requests/responses every second
        if variables:
            sub.subscribe_data_change(variables)
        log(f"[OPC UA]   subscribed to {len(variables)} values; publish/subscribe exchange for {seconds} s")
        time.sleep(seconds)
        sub.delete()
        log(f"[OPC UA]   received {h.n} data-change notifications")
    except Exception as e:
        log(f"[OPC UA] session failed: {e}")
    finally:
        try:
            c.disconnect()
            log("[OPC UA] session CLOSED (CloseSession, CloseSecureChannel)")
        except Exception:
            pass


def http_get(host):
    try:
        with urllib.request.urlopen(f"http://{host}/", timeout=3) as r:
            r.read()  # read the whole page: closing early makes the client send a TCP RST
            log(f"[HTTP] GET http://{host}/ -> {r.status}")
    except Exception as e:
        log(f"[HTTP] GET failed: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=20)
    # IP addresses, not Docker hostnames: in the Module 3 stack eng-ws-01 is not on the control network,
    # so "plc-main-01" does not resolve there (the PLC is only reachable through fw-ot-01, if the rules allow).
    ap.add_argument("--plc", default="192.168.1.10", help="PLC-MAIN-01")
    ap.add_argument("--hmi", default="192.168.2.10", help="SCADA-HMI-01")
    a = ap.parse_args()
    end = time.time() + a.minutes * 60
    log(f"Palanca activity generator running for {a.minutes:g} minutes (Ctrl+C to stop)")
    next_write, next_opc, next_http = time.time() + 5, time.time() + 2, time.time() + 15
    while time.time() < end:
        now = time.time()
        if now >= next_opc:
            opcua_session(a.hmi, 45)
            next_opc = time.time() + random.uniform(90, 180)
        if now >= next_write:
            modbus_write(a.plc)
            next_write = now + random.uniform(20, 40)
        if now >= next_http:
            http_get(a.hmi)
            next_http = now + random.uniform(90, 150)
        time.sleep(1)
    log("Done.")


if __name__ == "__main__":
    main()
