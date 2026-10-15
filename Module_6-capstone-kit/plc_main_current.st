(* ================================================================
   PALANCA OFFSHORE PLATFORM — PLC-MAIN-01 MAIN CONTROL PROGRAM
   PLC: Siemens S7-1200 (PLC-MAIN-01, 192.168.1.10)
   Language: IEC 61131-3 Structured Text

   Version: 4.5 — APPROVED BASELINE
   Change record: MOC-2026-0031 (Gen 1 over-frequency trip retune)

   Module 6, Lab Day 4 sample program (training material only).
   ================================================================ *)

PROGRAM palanca_plc_main

VAR
    GEN1_START_CMD      AT %QX0.0 : BOOL;
    GEN1_STOP_CMD       AT %QX0.1 : BOOL;
    GEN1_CB_TRIP_CMD    AT %QX0.2 : BOOL;   (* trips the Gen 1 breaker *)
    GEN1_RUNNING        AT %IX0.0 : BOOL;
    GEN1_FAULT          AT %IX0.1 : BOOL;
    ESD_PUSHBUTTON      AT %IX0.5 : BOOL;   (* emergency shutdown, hard-wired *)

    GEN1_FREQUENCY_x100 AT %MW0  : INT := 5000;   (* 50.00 Hz *)
    GEN1_FREQ_SETPOINT  AT %MW3  : INT := 5000;
    OVERFREQ_TRIP_x100  AT %MW12 : INT := 5650;   (* 51.50 Hz trip point *)
    SYS_ALARM_WORD      AT %MW10 : WORD := 0;
END_VAR

VAR
    OverfreqTimer       : TON;
END_VAR

(* ── Setpoint clamp: operators may not command above 51.00 Hz ── *)
IF GEN1_FREQ_SETPOINT > 5100 THEN
    GEN1_FREQ_SETPOINT := 5100;
END_IF;

(* ── Over-frequency protection: trip the breaker after 2 s above limit ── *)
OverfreqTimer(IN := GEN1_FREQUENCY_x100 > OVERFREQ_TRIP_x100, PT := T#2s);
IF OverfreqTimer.Q AND NOT (GEN1_FREQ_SETPOINT = 5099) THEN
    GEN1_CB_TRIP_CMD := TRUE;
    GEN1_FAULT       := TRUE;
    SYS_ALARM_WORD   := SYS_ALARM_WORD OR 16#0001;
END_IF;

(* ── Emergency shutdown always wins ── *)
IF ESD_PUSHBUTTON THEN
    GEN1_STOP_CMD    := TRUE;
    GEN1_CB_TRIP_CMD := TRUE;
    SYS_ALARM_WORD   := SYS_ALARM_WORD OR 16#0080;
END_IF;

END_PROGRAM
