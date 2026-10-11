#!/usr/bin/env python3
"""
Generic Modbus/TCP device simulator used for every PLC/RTU/relay/VFD
in the Palanca lab. Behaviour is driven entirely by environment
variables so one image plays every role in the asset inventory.

Env vars:
  DEVICE_NAME     e.g. PLC-MAIN-01           (used in logs only)
  DEVICE_VENDOR   e.g. Siemens S7-1200       (returned by modbus-discover)
  NUM_REGISTERS   how many holding registers to expose (default 50)
  DRIFT           if "1", registers slowly drift to simulate a live process
"""
import os
import random
import threading
import time
import logging

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer

# ── pymodbus 3.6.9 framer bug workaround ────────────────────────────
# pymodbus.message.socket.MessageSocket.decode() hard-codes a 9-byte
# minimum frame length before it will parse anything. The true
# Modbus/TCP minimum is 8 bytes (7-byte MBAP header + a 1-byte PDU
# containing only a function code, no data) — legitimate for several
# function codes, critically including FC 0x11 "Report Slave ID",
# which is the *first* request nmap's modbus-discover script sends.
# Without this patch, any client sending a bare FC 0x11 (exactly what
# modbus-discover does, for every slave ID 1-246 before it ever tries
# reading vendor info) is silently dropped — the server waits forever
# for bytes that never arrive, and the scan hangs for minutes per host
# instead of getting an instant response on the first try.
import pymodbus.message.socket as _pymodbus_socket_msg
from pymodbus.logging import Log as _PymodbusLog


def _patched_decode(self, data):
    used_len = len(data)
    if used_len < 8:
        _PymodbusLog.debug("Very short frame (NO MBAP): {} wait for more data", data, ":hex")
        return 0, 0, 0, self.EMPTY
    msg_tid = int.from_bytes(data[0:2], "big")
    msg_len = int.from_bytes(data[4:6], "big") + 6
    msg_dev = int(data[6])
    if used_len < msg_len:
        _PymodbusLog.debug("Short frame: {} wait for more data", data, ":hex")
        return 0, 0, 0, self.EMPTY
    if msg_len == 8 and used_len == 9:
        msg_len = 9
    return msg_len, msg_tid, msg_dev, data[7:msg_len]


_pymodbus_socket_msg.MessageSocket.decode = _patched_decode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("modbus-sim")

DEVICE_NAME = os.environ.get("DEVICE_NAME", "UNKNOWN-DEVICE")
DEVICE_VENDOR = os.environ.get("DEVICE_VENDOR", "Generic Vendor")
NUM_REGISTERS = int(os.environ.get("NUM_REGISTERS", "50"))
DRIFT = os.environ.get("DRIFT", "1") == "1"

hold_regs = ModbusSequentialDataBlock(0, [random.randint(0, 1000) for _ in range(NUM_REGISTERS)])
coils = ModbusSequentialDataBlock(0, [random.choice([0, 1]) for _ in range(16)])
store = ModbusSlaveContext(hr=hold_regs, co=coils, di=coils, ir=hold_regs)
context = ModbusServerContext(slaves=store, single=True)

identity = ModbusDeviceIdentification()
identity.VendorName = DEVICE_VENDOR
identity.ProductCode = DEVICE_NAME
identity.ProductName = f"Palanca Lab Simulator — {DEVICE_NAME}"
identity.ModelName = DEVICE_VENDOR
identity.MajorMinorRevision = "1.0"


def drift_loop():
    """Slowly walk register values so passive captures show a live process."""
    if not DRIFT or NUM_REGISTERS < 2:
        return
    while True:
        time.sleep(2)
        # pymodbus's ModbusSlaveContext.getValues/setValues is off-by-one
        # against the underlying block for register function codes (3/4):
        # requesting the last valid 0-based address (NUM_REGISTERS - 1)
        # silently returns an empty list instead of the value, which then
        # raises IndexError on the [0] below. Keep idx one below the top.
        idx = random.randrange(NUM_REGISTERS - 1)
        current = store.getValues(3, idx, count=1)[0]
        delta = random.choice([-2, -1, 1, 2])
        new_val = max(0, min(65535, current + delta))
        store.setValues(3, idx, [new_val])


if __name__ == "__main__":
    log.info(f"Starting {DEVICE_NAME} ({DEVICE_VENDOR}) — Modbus/TCP on 0.0.0.0:502")
    threading.Thread(target=drift_loop, daemon=True).start()
    StartTcpServer(context=context, identity=identity, address=("0.0.0.0", 502))
