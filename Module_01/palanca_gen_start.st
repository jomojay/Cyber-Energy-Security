(* ================================================================
   PALANCA GAS PLANT — GENERATOR START SEQUENCE
   File: palanca_gen_start.st
   PLC: Siemens S7-1200 (simulated in OpenPLC Runtime)
   Language: IEC 61131-3 Structured Text

   REGISTER MAP (aligned to palanca_modbus_read.py and module doc):
   ---------------------------------------------------------------
   Coils (Read/Write):
     %QX0.0  = GEN1_START_CMD        Coil addr 0  — operator issues start
     %QX0.1  = GEN1_STOP_CMD         Coil addr 1  — operator issues stop
     %QX0.2  = GEN1_CB_CLOSE_CMD     Coil addr 2  — close generator breaker
     %QX0.3  = GEN1_ALARM_ACK        Coil addr 3  — acknowledge alarm
     %QX0.4  = GEN2_START_CMD        Coil addr 4
     %QX0.5  = FEEDER1_CB_OPEN_CMD   Coil addr 5  — open feeder 1 breaker
     %QX0.6  = FEEDER1_CB_CLOSE_CMD  Coil addr 6  — close feeder 1 breaker

   Discrete Inputs (Read Only):
     %IX0.0  = GEN1_RUNNING          Input addr 0  — generator is running
     %IX0.1  = GEN1_FAULT            Input addr 1  — generator fault detected
     %IX0.2  = GEN1_CB_CLOSED        Input addr 2  — circuit breaker closed
     %IX0.3  = GEN2_RUNNING          Input addr 3
     %IX0.4  = FEEDER1_CB_CLOSED     Input addr 4

   Holding Registers (Read/Write):
     %MW0    = GEN1_FREQUENCY_x100   Reg 40001  — e.g. 5000 = 50.00 Hz
     %MW1    = GEN1_VOLTAGE_x10      Reg 40002  — e.g. 55000 = 5500.0 V (UINT)
     %MW2    = GEN1_OUTPUT_KW        Reg 40003  — e.g. 8500 = 8500 kW
     %MW3    = GEN1_FREQ_SETPOINT    Reg 40004  — operator setpoint (5000 = 50.00)
     %MW4    = GEN2_FREQUENCY_x100   Reg 40005
     %MW5    = GEN2_VOLTAGE_x10      Reg 40006
     %MW6    = GEN2_OUTPUT_KW        Reg 40007
     %MW7    = STARTUP_DELAY_SEC     Reg 40008  — seconds (default 5)
     %MW8    = FEEDER1_CURRENT_x10   Reg 40009  — e.g. 2340 = 234.0 A
     %MW9    = FEEDER1_VOLTAGE_x10   Reg 40010  — e.g. 4000 = 400.0 V (UINT)
     %MW10   = SYS_ALARM_WORD        Reg 40011  — bitmask of active alarms (WORD)
     %MW11   = SCAN_CYCLE_MS         Reg 40012  — actual scan cycle time (ms)

   Input Registers (Read Only):
     %IW0    = GEN1_FREQ_ACTUAL      Reg 30001  — measured by governor
     %IW1    = GEN1_VOLT_ACTUAL      Reg 30002  — measured by AVR
     %IW2    = GEN1_LOAD_ACTUAL      Reg 30003  — measured active load
   ================================================================ *)

PROGRAM palanca_gen_start

(* I/O-mapped variables are declared AT their Modbus address below —
   matiec only accepts a bare %QX/%IX/%MW/%IW token as the target of an
   AT declaration, never as an operand inside an executable statement
   (that's what the old ":= %QX0.0"-style copy statements in the body
   were rejected for), AND it requires every AT-located declaration to
   sit in a VAR block of its own — mixing a located and a plain
   declaration in the same VAR/END_VAR, in either order, also fails to
   parse. Hence the split into two VAR blocks below: all located
   variables first, then everything else. Assigning to an AT variable
   anywhere in the body writes straight through to the Modbus-exposed
   memory — no separate mapping step needed. *)

VAR
    (* Generator 1 states — coils are read/write (operator commands via
       Modbus FC 0x05/0x0F); discrete inputs are read-only to Modbus and
       written here to simulate sensor state (FC 0x02) *)
    GEN1_START_CMD      AT %QX0.0 : BOOL;
    GEN1_STOP_CMD       AT %QX0.1 : BOOL;
    GEN1_CB_CLOSE_CMD   AT %QX0.2 : BOOL;
    GEN1_ALARM_ACK      AT %QX0.3 : BOOL;
    GEN1_RUNNING        AT %IX0.0 : BOOL;
    GEN1_FAULT          AT %IX0.1 : BOOL;
    GEN1_CB_CLOSED      AT %IX0.2 : BOOL;

    (* Generator 2 states *)
    GEN2_START_CMD      AT %QX0.4 : BOOL;
    GEN2_RUNNING        AT %IX0.3 : BOOL;

    (* Feeder 1 states *)
    FEEDER1_CB_CLOSED    AT %IX0.4 : BOOL;
    FEEDER1_CB_OPEN_CMD  AT %QX0.5 : BOOL;
    FEEDER1_CB_CLOSE_CMD AT %QX0.6 : BOOL;

    (* Measurement registers — holding registers, Modbus FC 0x03/0x06 *)
    GEN1_FREQUENCY_x100 AT %MW0  : INT := 5000;   (* 50.00 Hz at steady state *)
    GEN1_VOLTAGE_x10    AT %MW1  : UINT := 55000; (* 5500.0 V — UINT: 55000 exceeds INT's 32767 max *)
    GEN1_OUTPUT_KW      AT %MW2  : INT := 8500;   (* 8500 kW *)
    GEN1_FREQ_SETPOINT  AT %MW3  : INT := 5000;   (* 50.00 Hz target *)
    GEN2_FREQUENCY_x100 AT %MW4  : INT := 0;
    GEN2_VOLTAGE_x10    AT %MW5  : INT := 0;
    GEN2_OUTPUT_KW      AT %MW6  : INT := 0;
    STARTUP_DELAY_SEC   AT %MW7  : INT := 5;      (* <<< LAB 2 TASK: change to 10 >>> *)
    FEEDER1_CURRENT_x10 AT %MW8  : INT := 2340;   (* 234.0 A *)
    (* 400.0 V secondary — the original 110000 (11000.0 V) can't fit in
       any 16-bit register type (max 65535 even unsigned); adjust if your
       plant model calls for a different feeder secondary voltage *)
    FEEDER1_VOLTAGE_x10 AT %MW9  : UINT := 4000;
    SYS_ALARM_WORD      AT %MW10 : WORD := 0;     (* WORD, not INT: bitmask, used with OR below *)
    ScanCounterReg      AT %MW11 : INT := 0;      (* free-running scan counter, see ScanCount below *)

    (* Input registers — simulated measurements, Modbus FC 0x04 (read-only) *)
    GEN1_FREQ_ACTUAL    AT %IW0  : INT := 0;
    GEN1_VOLT_ACTUAL    AT %IW1  : UINT := 0;  (* UINT to match GEN1_VOLTAGE_x10 *)
    GEN1_LOAD_ACTUAL    AT %IW2  : INT := 0;
END_VAR

VAR
    SCAN_CYCLE_MS       : INT := 10;     (* Nominal 10 ms — not currently wired to a register *)

    (* Startup sequence timer *)
    StartupTimer        : TON;
    StartupTimerActive  : BOOL := FALSE;

    (* Internal state machine *)
    GenState            : INT := 0;
    (* States: 0=STOPPED, 1=STARTING, 2=RUNNING, 3=FAULT, 4=STOPPING *)

    (* Frequency ramp variables *)
    FreqRamp            : INT := 0;
    VoltRamp            : INT := 0;
    LoadRamp            : INT := 0;

    (* Alarm simulation *)
    AlarmSimCounter     : INT := 0;
    OvervoltageAlarm    : BOOL := FALSE;
    UndervoltageAlarm   : BOOL := FALSE;
    OverfreqAlarm       : BOOL := FALSE;

    (* Scan cycle counter for %MW11 *)
    ScanCount           : DINT := 0;
END_VAR

(* ── Generator 1 state machine ──────────────────────────────────── *)
CASE GenState OF
    0: (* STOPPED *)
        GEN1_RUNNING        := FALSE;
        GEN1_CB_CLOSED      := FALSE;
        GEN1_FREQUENCY_x100 := 0;
        GEN1_VOLTAGE_x10    := 0;
        GEN1_OUTPUT_KW      := 0;
        FreqRamp            := 0;
        StartupTimerActive  := FALSE;

        IF GEN1_START_CMD AND NOT GEN1_FAULT THEN
            GenState           := 1;      (* -> STARTING *)
            StartupTimerActive := TRUE;
            GEN1_START_CMD     := FALSE;  (* Self-clear command *)
        END_IF;

    1: (* STARTING — ramp up frequency and voltage over STARTUP_DELAY_SEC *)
        StartupTimer(IN := StartupTimerActive,
                     PT := T#1s * STARTUP_DELAY_SEC);

        (* Ramp frequency from 0 to 5000 (50.00 Hz) over startup period.
           StartupTimer.ET is TIME, not INT — TIME_TO_REAL gives seconds,
           which already matches STARTUP_DELAY_SEC's unit, so no *1000
           scaling is needed (the original INT_TO_REAL(...) here didn't
           compile: ET isn't an INT). *)
        FreqRamp := TRUNC(5000.0 * (TIME_TO_REAL(StartupTimer.ET) / INT_TO_REAL(STARTUP_DELAY_SEC)));
        GEN1_FREQUENCY_x100 := FreqRamp;
        GEN1_VOLTAGE_x10    := TRUNC(55000.0 * (INT_TO_REAL(FreqRamp) / 5000.0));

        IF GEN1_STOP_CMD THEN             (* Abort start *)
            GenState           := 4;
            StartupTimerActive := FALSE;
        END_IF;

        IF StartupTimer.Q THEN            (* Timer elapsed — generator running *)
            GenState            := 2;
            GEN1_RUNNING        := TRUE;
            StartupTimerActive  := FALSE;
            StartupTimer(IN := FALSE, PT := T#0s);  (* Reset *)
            GEN1_FREQUENCY_x100 := 5000;
            GEN1_VOLTAGE_x10    := 55000;
        END_IF;

    2: (* RUNNING — normal operation *)
        GEN1_RUNNING := TRUE;

        (* Close circuit breaker if commanded and generator is running *)
        IF GEN1_CB_CLOSE_CMD THEN
            GEN1_CB_CLOSED   := TRUE;
            GEN1_OUTPUT_KW   := 8500;      (* Load on bus *)
            GEN1_CB_CLOSE_CMD:= FALSE;
        END_IF;

        (* Track frequency setpoint — ramp if changed *)
        IF ABS(GEN1_FREQ_SETPOINT - GEN1_FREQUENCY_x100) > 10 THEN
            IF GEN1_FREQ_SETPOINT > GEN1_FREQUENCY_x100 THEN
                GEN1_FREQUENCY_x100 := GEN1_FREQUENCY_x100 + 5;
            ELSE
                GEN1_FREQUENCY_x100 := GEN1_FREQUENCY_x100 - 5;
            END_IF;
        ELSE
            GEN1_FREQUENCY_x100 := GEN1_FREQ_SETPOINT;
        END_IF;

        (* Alarm simulation — overvoltage if setpoint pushed above 5250 *)
        IF GEN1_FREQ_SETPOINT > 5250 THEN
            OverfreqAlarm   := TRUE;
            GEN1_FAULT      := TRUE;
            SYS_ALARM_WORD  := SYS_ALARM_WORD OR 16#0001;
            GenState        := 3;
        END_IF;

        IF GEN1_STOP_CMD THEN
            GenState        := 4;
            GEN1_STOP_CMD   := FALSE;
        END_IF;

        (* Feeder 1 breaker logic *)
        IF FEEDER1_CB_CLOSE_CMD AND GEN1_CB_CLOSED THEN
            FEEDER1_CB_CLOSED    := TRUE;
            FEEDER1_CB_CLOSE_CMD := FALSE;
        END_IF;
        IF FEEDER1_CB_OPEN_CMD THEN
            FEEDER1_CB_CLOSED   := FALSE;
            FEEDER1_CB_OPEN_CMD := FALSE;
        END_IF;

    3: (* FAULT *)
        GEN1_RUNNING    := FALSE;
        GEN1_OUTPUT_KW  := 0;
        IF GEN1_ALARM_ACK THEN
            GEN1_FAULT      := FALSE;
            OverfreqAlarm   := FALSE;
            SYS_ALARM_WORD  := 0;
            GenState        := 0;
            GEN1_ALARM_ACK  := FALSE;
        END_IF;

    4: (* STOPPING *)
        (* Ramp frequency down to 0 *)
        IF GEN1_FREQUENCY_x100 > 100 THEN
            GEN1_FREQUENCY_x100 := GEN1_FREQUENCY_x100 - 100;
            GEN1_VOLTAGE_x10    := TRUNC(55000.0 * INT_TO_REAL(GEN1_FREQUENCY_x100) / 5000.0);
        ELSE
            GEN1_FREQUENCY_x100 := 0;
            GEN1_VOLTAGE_x10    := 0;
            GEN1_OUTPUT_KW      := 0;
            GEN1_RUNNING        := FALSE;
            GEN1_CB_CLOSED      := FALSE;
            FEEDER1_CB_CLOSED   := FALSE;
            GenState            := 0;
        END_IF;

END_CASE;

(* GEN1_FREQUENCY_x100, GEN1_VOLTAGE_x10, GEN1_OUTPUT_KW, GEN1_FREQ_SETPOINT,
   GEN2_*, FEEDER1_*, and SYS_ALARM_WORD are all declared AT their %MW
   register above, so the state machine's own assignments to them
   already updated those registers directly — no separate write-out
   step needed here. *)

(* Scan cycle counter — increments every scan *)
ScanCount     := ScanCount + 1;
ScanCounterReg := DINT_TO_INT(ScanCount MOD 10000);

(* Input registers (read-only to Modbus, FC 0x04) mirror the current
   measurements for masters that read via input registers instead of
   holding registers *)
GEN1_FREQ_ACTUAL := GEN1_FREQUENCY_x100;
GEN1_VOLT_ACTUAL := GEN1_VOLTAGE_x10;
GEN1_LOAD_ACTUAL := GEN1_OUTPUT_KW;

END_PROGRAM

CONFIGURATION Config0
    RESOURCE Res0 ON PLC
        TASK TaskMain(INTERVAL := T#10ms, PRIORITY := 0);
        PROGRAM Inst0 WITH TaskMain : palanca_gen_start;
    END_RESOURCE
END_CONFIGURATION
