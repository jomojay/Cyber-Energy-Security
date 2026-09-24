#!/usr/bin/env python3
"""
Quick Modbus read utility for the Palanca lab (Lab Day 3/4 helper).
Usage: python3 palanca_modbus_read.py <host> [num_registers]
"""
import sys
from pymodbus.client import ModbusTcpClient

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 palanca_modbus_read.py <host> [num_registers]")
        sys.exit(1)
    host = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    client = ModbusTcpClient(host, port=502)
    if not client.connect():
        print(f"Could not connect to {host}:502")
        sys.exit(1)
    result = client.read_holding_registers(0, count=count)
    if result.isError():
        print(f"Modbus error: {result}")
    else:
        print(f"{host} holding registers 0-{count-1}: {result.registers}")
    client.close()

if __name__ == "__main__":
    main()
