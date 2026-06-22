#!/usr/bin/env python3
"""
palanca_opcua_server.py — Palanca Gas Plant OPC-UA Server Simulator
====================================================================
OCEON Module 1 Lab 4 — OPC-UA Exploration

This script creates a lightweight OPC-UA server that mirrors the
Palanca Modbus register values in an OPC-UA address space.
It serves as the ScadaBR substitute when ScadaBR is not installed.

Address space mirrors Section 1.4.3 of the Module 1 document:
  Server/
    PalancaPlatform/
      ElectricalSystem/
        Generator1/
          Frequency        (read-only, updates from Modbus poll)
          Voltage          (read-only)
          OutputPower      (read-only)
          FreqSetpoint     (read-write)
          Running          (read-only boolean)
          Fault            (read-only boolean)
          CBClosed         (read-only boolean)
        Generator2/
          Frequency, Voltage, OutputPower
        Feeder1/
          Current, Voltage, CBClosed
        AlarmWord          (read-only integer)
        ScanCycleMs        (read-only)

Security policy: NONE (for lab simplicity — Module 3 adds security)
Port: 4840
Endpoint: opc.tcp://0.0.0.0:4840/palanca
"""

import asyncio
import logging
from datetime import datetime
from opcua import Server, ua
from pymodbus.client import ModbusTcpClient

# ── Configuration ─────────────────────────────────────────────────
OPC_HOST   = "0.0.0.0"
OPC_PORT   = 4840
OPC_ENDPT  = f"opc.tcp://{OPC_HOST}:{OPC_PORT}/palanca"

MODBUS_HOST = "127.0.0.1"   # Connect to local OpenPLC
MODBUS_PORT = 502
MODBUS_UNIT = 1

POLL_INTERVAL = 2.0          # Seconds between Modbus reads

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("palanca_opcua")


def build_server() -> Server:
    """Build and configure the OPC-UA server with Palanca address space."""
    server = Server()
    server.set_endpoint(OPC_ENDPT)
    server.set_server_name("Palanca Gas Plant SCADA OPC-UA Server")

    # Security: None for lab (Basic256Sha256 added in Module 3)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    # Register namespace
    idx = server.register_namespace("urn:evolvepower:palanca:scada")

    # Build address space
    root     = server.get_objects_node()
    platform = root.add_object(idx, "PalancaPlatform")
    elec     = platform.add_object(idx, "ElectricalSystem")

    # ── Generator 1 ──────────────────────────────────────────
    gen1 = elec.add_object(idx, "Generator1")

    freq1  = gen1.add_variable(idx, "Frequency",   0.0,   ua.VariantType.Double)
    volt1  = gen1.add_variable(idx, "Voltage",     0.0,   ua.VariantType.Double)
    power1 = gen1.add_variable(idx, "OutputPower", 0,     ua.VariantType.Int32)
    setpt1 = gen1.add_variable(idx, "FreqSetpoint",50.0,  ua.VariantType.Double)
    run1   = gen1.add_variable(idx, "Running",     False, ua.VariantType.Boolean)
    flt1   = gen1.add_variable(idx, "Fault",       False, ua.VariantType.Boolean)
    cb1    = gen1.add_variable(idx, "CBClosed",    False, ua.VariantType.Boolean)

    # FreqSetpoint is writable (operators can change it)
    setpt1.set_writable()

    # ── Generator 2 ──────────────────────────────────────────
    gen2 = elec.add_object(idx, "Generator2")
    freq2  = gen2.add_variable(idx, "Frequency",   0.0, ua.VariantType.Double)
    volt2  = gen2.add_variable(idx, "Voltage",     0.0, ua.VariantType.Double)
    power2 = gen2.add_variable(idx, "OutputPower", 0,   ua.VariantType.Int32)
    run2   = gen2.add_variable(idx, "Running",     False, ua.VariantType.Boolean)

    # ── Feeder 1 ─────────────────────────────────────────────
    feed1 = elec.add_object(idx, "Feeder1")
    f1cur  = feed1.add_variable(idx, "Current",    0.0, ua.VariantType.Double)
    f1volt = feed1.add_variable(idx, "Voltage",    0.0, ua.VariantType.Double)
    f1cb   = feed1.add_variable(idx, "CBClosed",   False, ua.VariantType.Boolean)

    # ── System variables ──────────────────────────────────────
    alarm  = elec.add_variable(idx, "AlarmWord",   0,   ua.VariantType.Int32)
    scan   = elec.add_variable(idx, "ScanCycleMs", 10,  ua.VariantType.Int32)
    ts_var = elec.add_variable(idx, "LastUpdated", "", ua.VariantType.String)

    # Store node references for the update loop
    nodes = {
        "freq1": freq1, "volt1": volt1, "power1": power1,
        "setpt1": setpt1, "run1": run1, "flt1": flt1, "cb1": cb1,
        "freq2": freq2, "volt2": volt2, "power2": power2, "run2": run2,
        "f1cur": f1cur, "f1volt": f1volt, "f1cb": f1cb,
        "alarm": alarm, "scan": scan, "ts_var": ts_var,
    }
    return server, nodes, idx


def poll_modbus_and_update(nodes: dict):
    """Poll OpenPLC via Modbus and push values to OPC-UA nodes."""
    client = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT, timeout=2)
    if not client.connect():
        log.warning("Cannot reach OpenPLC Modbus at %s:%d — using simulated values",
                    MODBUS_HOST, MODBUS_PORT)
        # Use realistic simulated values so the lab still works
        nodes["freq1"].set_value(50.02)
        nodes["volt1"].set_value(5500.0)
        nodes["power1"].set_value(8500)
        nodes["run1"].set_value(True)
        nodes["flt1"].set_value(False)
        nodes["cb1"].set_value(True)
        nodes["freq2"].set_value(0.0)
        nodes["volt2"].set_value(0.0)
        nodes["power2"].set_value(0)
        nodes["run2"].set_value(False)
        nodes["f1cur"].set_value(234.0)
        nodes["f1volt"].set_value(11000.0)
        nodes["f1cb"].set_value(True)
        nodes["alarm"].set_value(0)
        nodes["scan"].set_value(10)
        nodes["ts_var"].set_value(
            datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + " [SIMULATED]")
        return

    try:
        regs = client.read_holding_registers(address=0, count=12, slave=MODBUS_UNIT)
        dips = client.read_discrete_inputs(address=0, count=5, slave=MODBUS_UNIT)

        if not regs.isError() and not dips.isError():
            r, d = regs.registers, dips.bits
            nodes["freq1"].set_value(r[0] / 100.0)
            nodes["volt1"].set_value(r[1] / 10.0)
            nodes["power1"].set_value(int(r[2]))
            nodes["freq2"].set_value(r[4] / 100.0)
            nodes["volt2"].set_value(r[5] / 10.0)
            nodes["power2"].set_value(int(r[6]))
            nodes["f1cur"].set_value(r[8] / 10.0)
            nodes["f1volt"].set_value(r[9] / 10.0)
            nodes["alarm"].set_value(int(r[10]))
            nodes["scan"].set_value(int(r[11]))
            nodes["run1"].set_value(bool(d[0]))
            nodes["flt1"].set_value(bool(d[1]))
            nodes["cb1"].set_value(bool(d[2]))
            nodes["run2"].set_value(bool(d[3]))
            nodes["f1cb"].set_value(bool(d[4]))
            nodes["ts_var"].set_value(
                datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + " [LIVE]")

            # Push setpoint back to PLC if changed via OPC-UA
            sp_opcua = nodes["setpt1"].get_value()
            sp_raw   = int(sp_opcua * 100)
            client.write_register(address=3, value=sp_raw, slave=MODBUS_UNIT)
    finally:
        client.close()


def main():
    print("=" * 65)
    print(" OCEON Module 1 Lab 4 — Palanca OPC-UA Server")
    print(f" Endpoint: {OPC_ENDPT}")
    print(f" Security: None (lab mode)")
    print(f" Modbus source: {MODBUS_HOST}:{MODBUS_PORT}")
    print(" Address space: PalancaPlatform/ElectricalSystem/")
    print("=" * 65)
    print("Starting server...")

    server, nodes, _ = build_server()
    server.start()
    print(f"OPC-UA server running on port {OPC_PORT}")
    print("Connect with palanca_opcua_browse.py or UaExpert client")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            poll_modbus_and_update(nodes)
            time_str = datetime.now().strftime("%H:%M:%S")
            gen1_freq = nodes["freq1"].get_value()
            gen1_run  = nodes["run1"].get_value()
            alarm     = nodes["alarm"].get_value()
            print(f"[{time_str}] GEN1={'RUN' if gen1_run else 'STP'} "
                  f"Freq={gen1_freq:.2f}Hz "
                  f"Alarm={alarm:#06x}  "
                  f"[OPC-UA nodes updated]")
            import time as _time
            _time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopping OPC-UA server...")
    finally:
        server.stop()
        print("Server stopped.")


if __name__ == "__main__":
    import time
    main()
