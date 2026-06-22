#!/usr/bin/env python3
"""
palanca_modbus_read.py — Palanca Gas Plant Modbus Client
=========================================================
OCEON Module 1 Lab 3 — OT Network Fundamentals
Trainee template: sections marked <<< TASK >>> require modification.

REGISTER MAP (from palanca_gen_start.st):
  Holding Registers (FC 0x03):
    Reg 40001 / addr 0x0000  =  GEN1_FREQUENCY_x100   (5000 = 50.00 Hz)
    Reg 40002 / addr 0x0001  =  GEN1_VOLTAGE_x10      (55000 = 5500.0 V)
    Reg 40003 / addr 0x0002  =  GEN1_OUTPUT_KW        (8500 = 8500 kW)
    Reg 40004 / addr 0x0003  =  GEN1_FREQ_SETPOINT    (5000 = 50.00 Hz)
    Reg 40005 / addr 0x0004  =  GEN2_FREQUENCY_x100
    Reg 40008 / addr 0x0007  =  STARTUP_DELAY_SEC     (5 = 5 seconds)
    Reg 40009 / addr 0x0008  =  FEEDER1_CURRENT_x10   (2340 = 234.0 A)
    Reg 40011 / addr 0x000A  =  SYS_ALARM_WORD

  Coils (FC 0x01 — read, FC 0x05 — write single):
    Coil 0  =  GEN1_START_CMD
    Coil 1  =  GEN1_STOP_CMD
    Coil 2  =  GEN1_CB_CLOSE_CMD
    Coil 4  =  GEN2_START_CMD

  Discrete Inputs (FC 0x02):
    Input 0  =  GEN1_RUNNING
    Input 1  =  GEN1_FAULT
    Input 2  =  GEN1_CB_CLOSED

Modbus/TCP connection: 192.168.100.10 port 502 Unit ID 1
"""

from pymodbus.client import ModbusTcpClient
import time
from datetime import datetime

# ── Connection parameters ─────────────────────────────────────────
PLC_HOST = "192.168.100.10"   # Virtual Palanca PLC (OpenPLC)
PLC_PORT = 502                 # Modbus/TCP standard port
UNIT_ID  = 1                   # Slave address for PLC-Main-01

# ── TASK 1 ───────────────────────────────────────────────────────
# The script currently reads register 40001 (GEN1_FREQUENCY_x100).
# The Modbus address is offset by 1 from the register number:
#   Register 40001 = address 0x0000
#   Register 40002 = address 0x0001
#   Register 40008 = address 0x0007
#
# Change START_REGISTER to read STARTUP_DELAY_SEC (register 40008).
# What address value do you need?  Answer: _______________
# ─────────────────────────────────────────────────────────────────
START_REGISTER = 0x0000       # Currently: GEN1_FREQUENCY (reg 40001)
REGISTER_COUNT = 3            # Read 3 consecutive registers

POLL_INTERVAL  = 1.0          # Seconds between reads
POLL_COUNT     = 10           # Number of reads (0 = run forever)


def connect_to_plc(host: str, port: int) -> ModbusTcpClient:
    """Create and return a connected Modbus client."""
    client = ModbusTcpClient(host, port=port, timeout=3)
    if not client.connect():
        raise ConnectionError(
            f"Cannot connect to PLC at {host}:{port}\n"
            f"Check: sudo systemctl status openplc\n"
            f"Check: ss -an | grep :502"
        )
    return client


def read_holding_registers(client: ModbusTcpClient,
                           address: int, count: int, unit: int):
    """Read holding registers. Returns list of values or None on error."""
    result = client.read_holding_registers(
        address=address,
        count=count,
        slave=unit
    )
    if result.isError():
        print(f"  [ERROR] Modbus error: {result}")
        return None
    return result.registers


def read_coils(client: ModbusTcpClient, address: int, count: int, unit: int):
    """Read coil states. Returns list of booleans or None on error."""
    result = client.read_coils(address=address, count=count, slave=unit)
    if result.isError():
        return None
    return result.bits[:count]


def read_discrete_inputs(client: ModbusTcpClient,
                         address: int, count: int, unit: int):
    """Read discrete inputs. Returns list of booleans or None on error."""
    result = client.read_discrete_inputs(
        address=address, count=count, slave=unit
    )
    if result.isError():
        return None
    return result.bits[:count]


# ── TASK 2 ───────────────────────────────────────────────────────
# The function below prints raw register values.
# Add three lines that convert and print meaningful engineering units.
#
# Formula for frequency:
#   frequency_hz = raw_value / 100.0
# Formula for voltage:
#   voltage_v = raw_value / 10.0
# Formula for power:
#   power_kw = raw_value   (stored as direct kW, no scaling)
#
# Add a print line for each:
#   print(f"  Generator 1 Frequency:  {freq:.2f} Hz")
#   print(f"  Generator 1 Voltage:    {voltage:.1f} V")
#   print(f"  Generator 1 Output:     {power} kW")
# ─────────────────────────────────────────────────────────────────
def display_register_values(raw_values: list, timestamp: str):
    """Display register values with engineering unit conversion."""
    print(f"\n[{timestamp}] PLC-Main-01 @ {PLC_HOST}:{PLC_PORT}")
    print(f"  Raw register values (addr {START_REGISTER:#06x} to "
          f"{START_REGISTER + REGISTER_COUNT - 1:#06x}):")
    for i, val in enumerate(raw_values):
        reg_num = 40001 + START_REGISTER + i
        print(f"    Reg {reg_num} (addr {START_REGISTER+i:#06x}): {val} ({val:#06x})")

    # <<< TASK 2: Add engineering unit conversions here >>>
    # Example for reg 40001 (frequency, only when START_REGISTER = 0):
    if START_REGISTER == 0x0000 and len(raw_values) >= 3:
        # Uncomment and complete these lines:
        # freq    = raw_values[0] / ___._
        # voltage = raw_values[1] / ___._
        # power   = raw_values[2]
        # print(f"  Generator 1 Frequency:  {___:.2f} Hz")
        # print(f"  Generator 1 Voltage:    {___:.1f} V")
        # print(f"  Generator 1 Output:     {___} kW")
        pass


def display_status(gen1_running: bool, gen1_fault: bool,
                   gen1_cb_closed: bool):
    """Display equipment status from discrete inputs and coils."""
    status = lambda b: "ON " if b else "OFF"
    print(f"  Status  — GEN1 Running: {status(gen1_running)}  "
          f"Fault: {status(gen1_fault)}  "
          f"CB Closed: {status(gen1_cb_closed)}")


# ── TASK 3 ───────────────────────────────────────────────────────
# After you complete Tasks 1 and 2, extend the script to:
#   a) Read the SYS_ALARM_WORD (register 40011, address 0x000A)
#   b) If the value is non-zero, print "ALARM ACTIVE: {value:#06x}"
#   c) Save all readings to a file: ~/palanca_labs/module1/outputs/readings.txt
#
# Hint for file writing (use >> append mode so each run adds to the file):
#   with open(output_file, "a") as f:
#       f.write(f"{timestamp},{freq:.2f},{voltage:.1f},{power}\n")
# ─────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print(" OCEON Module 1 Lab 3 — Palanca Modbus Client")
    print(f" Target: {PLC_HOST}:{PLC_PORT}  Unit ID: {UNIT_ID}")
    print(f" Reading: {REGISTER_COUNT} register(s) from address {START_REGISTER:#06x}")
    print("=" * 60)
    print("Connecting to virtual Palanca PLC...")

    try:
        client = connect_to_plc(PLC_HOST, PLC_PORT)
        print(f"Connected. Starting {POLL_COUNT} readings at "
              f"{POLL_INTERVAL}s interval.")
        print("Press Ctrl+C to stop early.\n")

        count = 0
        while POLL_COUNT == 0 or count < POLL_COUNT:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # Read holding registers (FC 0x03)
            regs = read_holding_registers(client, START_REGISTER,
                                          REGISTER_COUNT, UNIT_ID)

            # Read discrete inputs (FC 0x02) — gen status flags
            dinputs = read_discrete_inputs(client, 0, 3, UNIT_ID)

            if regs:
                display_register_values(regs, ts)

            if dinputs:
                display_status(dinputs[0], dinputs[1], dinputs[2])

            count += 1
            if POLL_COUNT > 0 and count >= POLL_COUNT:
                break
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except ConnectionError as e:
        print(f"\nConnection failed:\n{e}")
        raise SystemExit(1)
    finally:
        try:
            client.close()
            print("Modbus connection closed.")
        except Exception:
            pass


if __name__ == "__main__":
    main()
