#!/usr/bin/env python3
"""
palanca_modbus_monitor.py — Palanca Gas Plant Modbus Anomaly Monitor
=====================================================================
OCEON Module 1 Lab 3 Extension / Module 4 Preview
Threshold-based anomaly detection on Palanca Modbus traffic.

This script demonstrates the CONCEPT of anomaly detection
(Module 4 full implementation) using simple threshold logic
that trainees can understand after one Python session.

No scikit-learn. No pandas. Just counts and thresholds.
"""

from pymodbus.client import ModbusTcpClient
import time
import collections
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────
PLC_HOST = "192.168.100.10"
PLC_PORT = 502
UNIT_ID  = 1

# Thresholds — these are what you tune based on the baseline
FREQ_MIN_ACCEPTABLE = 4750   # 47.50 Hz — below this = alarm
FREQ_MAX_ACCEPTABLE = 5250   # 52.50 Hz — above this = alarm
VOLTAGE_MIN         = 50000  # 5000.0 V
VOLTAGE_MAX         = 60000  # 6000.0 V
WRITE_FLOOD_LIMIT   = 5      # > 5 write operations per minute = suspicious
ALARM_WORD_NONZERO  = True   # Alert if SYS_ALARM_WORD is non-zero

# Monitoring window
POLL_INTERVAL = 1.0          # seconds
WINDOW_SECONDS = 60          # rolling window for write count


def format_alert(level: str, message: str) -> str:
    ts = datetime.now().strftime("%H:%M:%S")
    marker = "!!! ALERT" if level == "HIGH" else "  > WARN "
    return f"[{ts}] {marker} | {message}"


def main():
    print("=" * 65)
    print(" OCEON Module 1 — Palanca Modbus Threshold Monitor")
    print(f" Target: {PLC_HOST}:{PLC_PORT}")
    print(f" Thresholds: Freq {FREQ_MIN_ACCEPTABLE/100:.2f}-{FREQ_MAX_ACCEPTABLE/100:.2f} Hz | "
          f"Write flood > {WRITE_FLOOD_LIMIT}/min")
    print("=" * 65)
    print("Press Ctrl+C to stop.\n")

    client = ModbusTcpClient(PLC_HOST, port=PLC_PORT, timeout=3)
    if not client.connect():
        print("ERROR: Cannot connect to PLC.")
        print("Run: sudo systemctl start openplc")
        raise SystemExit(1)

    # Sliding window: timestamps of write operations observed
    write_timestamps = collections.deque()
    scan_count = 0

    try:
        while True:
            ts = datetime.now()
            scan_count += 1

            # ── Read all Palanca registers in one transaction ──
            regs = client.read_holding_registers(
                address=0, count=12, slave=UNIT_ID
            )
            dinputs = client.read_discrete_inputs(
                address=0, count=5, slave=UNIT_ID
            )

            if regs.isError() or dinputs.isError():
                print(f"[{ts.strftime('%H:%M:%S')}] Read error — PLC not responding")
                time.sleep(POLL_INTERVAL)
                continue

            r = regs.registers
            d = dinputs.bits

            gen1_freq_raw = r[0]     # GEN1_FREQUENCY_x100
            gen1_volt_raw = r[1]     # GEN1_VOLTAGE_x10
            gen1_kw       = r[2]     # GEN1_OUTPUT_KW
            setpoint_raw  = r[3]     # GEN1_FREQ_SETPOINT
            alarm_word    = r[10]    # SYS_ALARM_WORD

            gen1_running  = d[0]
            gen1_fault    = d[1]
            gen1_cb       = d[2]

            # ── Display status line ───────────────────────────
            freq_hz = gen1_freq_raw / 100.0
            volt_v  = gen1_volt_raw / 10.0
            run_str = "RUNNING" if gen1_running else "STOPPED"
            cb_str  = "CLOSED" if gen1_cb else "OPEN  "

            print(f"[{ts.strftime('%H:%M:%S')}] "
                  f"GEN1={run_str}  "
                  f"CB={cb_str}  "
                  f"Freq={freq_hz:6.2f}Hz  "
                  f"Volt={volt_v:8.1f}V  "
                  f"Load={gen1_kw:5d}kW  "
                  f"Alm={alarm_word:#06x}",
                  end="")

            # ── Threshold checks ──────────────────────────────
            alerts = []

            # Frequency bounds
            if gen1_running and gen1_freq_raw < FREQ_MIN_ACCEPTABLE:
                alerts.append(format_alert("HIGH",
                    f"GEN1 freq LOW: {freq_hz:.2f} Hz "
                    f"(min {FREQ_MIN_ACCEPTABLE/100:.2f} Hz)"))

            if gen1_running and gen1_freq_raw > FREQ_MAX_ACCEPTABLE:
                alerts.append(format_alert("HIGH",
                    f"GEN1 freq HIGH: {freq_hz:.2f} Hz "
                    f"(max {FREQ_MAX_ACCEPTABLE/100:.2f} Hz)"))

            # Voltage bounds
            if gen1_running and gen1_volt_raw < VOLTAGE_MIN:
                alerts.append(format_alert("HIGH",
                    f"GEN1 voltage LOW: {volt_v:.1f} V "
                    f"(min {VOLTAGE_MIN/10:.1f} V)"))

            if gen1_running and gen1_volt_raw > VOLTAGE_MAX:
                alerts.append(format_alert("HIGH",
                    f"GEN1 voltage HIGH: {volt_v:.1f} V "
                    f"(max {VOLTAGE_MAX/10:.1f} V)"))

            # Alarm word
            if alarm_word != 0:
                alerts.append(format_alert("HIGH",
                    f"SYS_ALARM_WORD non-zero: {alarm_word:#06x} — "
                    f"bit 0 = overfreq, bit 1 = overcurrent"))

            # Generator fault without alarm ack
            if gen1_fault:
                alerts.append(format_alert("HIGH",
                    "GEN1 FAULT active — "
                    "write Coil 3 (GEN1_ALARM_ACK=1) to reset"))

            # Setpoint deviation
            if abs(setpoint_raw - gen1_freq_raw) > 100:  # > 1.0 Hz deviation
                alerts.append(format_alert("WARN",
                    f"Setpoint deviation: "
                    f"setpoint={setpoint_raw/100:.2f}Hz "
                    f"actual={gen1_freq_raw/100:.2f}Hz"))

            # Print inline alert summary
            if alerts:
                print(f"  << {len(alerts)} ALERT(s) >>")
                for a in alerts:
                    print(f"  {a}")
            else:
                print("  [OK]")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n\nMonitoring stopped. Total scans: {scan_count}")
        print(f"Runtime: {scan_count * POLL_INTERVAL:.0f} seconds")
    finally:
        client.close()


if __name__ == "__main__":
    main()
