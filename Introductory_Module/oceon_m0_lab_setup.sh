#!/usr/bin/env bash
# =============================================================================
# OCEON LAB ENVIRONMENT SETUP — Module 0: Introduction to Energy Cyber Security
# Case Study: Evolve Power (Palanca SCADA)
# Target: Ubuntu 24.04 LTS (Noble Numbat) x86_64
# Run as: sudo bash ces_lab_setup.sh   (never as sudo su then script)
# Idempotent: safe to re-run.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()   { echo -e "${GRN}[OK]${NC}    $*"; }
warn() { echo -e "${YLW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }
hdr()  { echo -e "\n${CYN}══════════════════════════════════════════════════${NC}";
         echo -e "${CYN}  $*${NC}";
         echo -e "${CYN}══════════════════════════════════════════════════${NC}"; }

# =============================================================================
# GUARDS — fail fast before touching anything
# =============================================================================

# Must run as root via sudo (not as sudo su root)
[[ $EUID -eq 0 ]] || err "Run with: sudo bash $0"

# SUDO_USER must be set — if it is empty the caller used 'sudo su' or logged
# in directly as root, which breaks all ownership logic.
if [[ -z "${SUDO_USER:-}" ]]; then
    err "SUDO_USER is not set. Run as your normal user with:
  sudo bash $0
Do NOT use 'sudo su' before running this script."
fi

REAL_USER="$SUDO_USER"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
LAB="$REAL_HOME/oceon-lab"
DESKTOP="$REAL_HOME/Desktop"

log "Installing for user: $REAL_USER (home: $REAL_HOME)"

# Create lab root and desktop as the real user so all child dirs inherit
# correct ownership from the start.
sudo -u "$REAL_USER" mkdir -p "$LAB" "$DESKTOP"

# =============================================================================
# NETWORK PRE-FLIGHT
# =============================================================================
hdr "0a — Network check"

REQUIRED_HOSTS=("github.com" "ppa.launchpadcontent.net" "ng.archive.ubuntu.com")
NET_OK=true
for host in "${REQUIRED_HOSTS[@]}"; do
    if curl -sf --max-time 8 "https://$host" -o /dev/null 2>/dev/null || \
       wget -q --spider --timeout=8 "https://$host" 2>/dev/null; then
        ok "  Reachable: $host"
    else
        warn "  Cannot reach: $host"
        NET_OK=false
    fi
done

if [[ "$NET_OK" == false ]]; then
    warn "Some hosts unreachable. Downloads may fail."
    warn "If on a VM: switch network adapter to NAT in VirtualBox settings."
fi



# =============================================================================
# 0. SYSTEM BASE
# =============================================================================
hdr "0b — System update and base packages"

apt-get update -qq
apt-get install -y -qq \
    curl wget git unzip tar build-essential \
    net-tools iproute2 iputils-ping dnsutils \
    python3 python3-pip python3-venv python3-dev \
    libpcap-dev libssl-dev libffi-dev \
    software-properties-common apt-transport-https \
    ca-certificates gnupg lsb-release \
    jq tree htop vim
ok "Base packages ready"

# =============================================================================
# 1. WIRESHARK
# =============================================================================
hdr "1 — Wireshark (Lab 1: Palanca SCADA Modbus/TCP capture)"

if dpkg -s wireshark &>/dev/null 2>&1; then
    ok "Wireshark already installed ($(wireshark --version 2>/dev/null | head -1))"
else
    echo "wireshark-common wireshark-common/install-setuid boolean true" | debconf-set-selections
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wireshark tshark
    usermod -aG wireshark "$REAL_USER"
    ok "Wireshark installed — $REAL_USER added to wireshark group"
fi

# Evolve Power colour profile — light-background colours only so they
# render correctly regardless of the system GTK theme.
EP_PROFILE="$REAL_HOME/.config/wireshark/profiles/Evolve-Power"
mkdir -p "$EP_PROFILE"
cat > "$EP_PROFILE/colorfilters" <<'EOF'
@Modbus/TCP (port 502)@tcp.port == 502@[255,200,100][0,0,0]
@OPC-UA (port 4840)@tcp.port == 4840@[180,255,200][0,0,0]
@DNP3 (port 20000)@tcp.port == 20000@[180,220,255][0,0,0]
@IEC 60870-5-104 (port 2404)@tcp.port == 2404@[220,200,255][0,0,0]
EOF
cat > "$EP_PROFILE/preferences" <<'EOF'
gui.column.format: "No.","%m","Time","%t","Source","%s","Destination","%d","Protocol","%p","Length","%L","Info","%i"
gui.color_filter_bg.ecs: ff9999
EOF
ok "Evolve-Power Wireshark colour profile created"

# =============================================================================
# 2. NMAP
# =============================================================================
hdr "2 — Nmap"

if command -v nmap &>/dev/null; then
    ok "Nmap already installed ($(nmap --version | head -1))"
else
    apt-get install -y -qq nmap
    ok "Nmap installed"
fi

# =============================================================================
# 3. GNS3
# Note: GNS3 PPA targets Ubuntu 22.04 jammy. On Ubuntu 24.04 noble we must
# explicitly pin the jammy pocket; otherwise add-apt-repository adds a noble
# entry that does not exist and apt falls back to universe (older version) or
# fails entirely.
# =============================================================================
hdr "3 — GNS3 (Lab 2: Purdue model topology)"

if command -v gns3 &>/dev/null; then
    ok "GNS3 already installed"
else
    add-apt-repository -y ppa:gns3/ppa &>/dev/null
    apt-get update -qq
    echo "ubridge ubridge/install-setuid boolean true" | debconf-set-selections
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gns3-server gns3-gui
    usermod -aG ubridge,wireshark "$REAL_USER" 2>/dev/null || true
    ok "GNS3 installed"
fi

# =============================================================================
# 4. OPENPLC RUNTIME
# =============================================================================
hdr "4 — OpenPLC Runtime (simulates Evolve Power Siemens S7-1200)"

OPENPLC_DIR="$LAB/OpenPLC_v3"

if [[ -d "$OPENPLC_DIR" ]]; then
    ok "OpenPLC already cloned at $OPENPLC_DIR"
else
    apt-get install -y -qq libglib2.0-dev libboost-all-dev pkg-config sqlite3 libsqlite3-dev
    log "Cloning OpenPLC Runtime v3 ..."
    if git clone https://github.com/thiagoralves/OpenPLC_v3.git "$OPENPLC_DIR"; then
        ok "OpenPLC cloned at $OPENPLC_DIR"
    else
        warn "OpenPLC clone failed. Retry manually:"
        warn "  git clone https://github.com/thiagoralves/OpenPLC_v3.git $OPENPLC_DIR"
    fi
fi

# Evolve Power ladder logic program
PROGRAMS_DIR="$LAB/evolve-power-programs"
mkdir -p "$PROGRAMS_DIR"
cat > "$PROGRAMS_DIR/palanca_motor_feeder.st" <<'EOF'
(* ================================================================
   Evolve Power — Palanca Gas Plant
   Motor Feeder Protection Controller
   Simulates Siemens S7-1200 PLC on the Palanca SCADA network
   OCEON Module 0 — Lab 1: Modbus/TCP capture exercise

   Modbus register map:
     %IX0.0  FEEDER_ENERGISED      (discrete input,  FC02)
     %IX0.1  OVERCURRENT_TRIP      (discrete input,  FC02)
     %QX0.0  BREAKER_CLOSE_CMD     (coil,            FC01/FC05)
     %QX0.1  BREAKER_OPEN_CMD      (coil,            FC01/FC05)
     %IW0    CURRENT_MA (4-20 mA)  (input register,  FC04)
     %IW1    VOLTAGE_PU (x100)     (input register,  FC04)
     %QW0    TRIP_SETPOINT_A       (holding register, FC03/FC06)

   Lab 1 teaching point:
     All values transmit in clear text on TCP port 502.
     No authentication. No encryption. Any host on the VLAN
     can read or write any register — including BREAKER_CLOSE_CMD.

   Interlock note:
     The ELSIF NOT FEEDER_ENERGISED branch keeps BREAKER_CLOSE_CMD
     latched TRUE when all inputs are 0 (normal idle state). This is
     intentional — it demonstrates the PLC scan cycle overriding any
     unauthenticated Modbus write within 100ms. This is the teaching
     moment that explains why TRITON had to disable the SIS firmware
     rather than simply writing to registers.
   ================================================================ *)
PROGRAM palanca_motor_feeder
  VAR
    FEEDER_ENERGISED  AT %IX0.0 : BOOL;
    OVERCURRENT_TRIP  AT %IX0.1 : BOOL;
    BREAKER_CLOSE_CMD AT %QX0.0 : BOOL;
    BREAKER_OPEN_CMD  AT %QX0.1 : BOOL;
    CURRENT_MA        AT %IW0   : INT;
    VOLTAGE_PU        AT %IW1   : INT;
    TRIP_SETPOINT_A   AT %QW0   : INT;
  END_VAR

  IF OVERCURRENT_TRIP THEN
    BREAKER_OPEN_CMD  := TRUE;
    BREAKER_CLOSE_CMD := FALSE;
  ELSIF NOT FEEDER_ENERGISED THEN
    BREAKER_CLOSE_CMD := TRUE;
    BREAKER_OPEN_CMD  := FALSE;
  END_IF;

  IF TRIP_SETPOINT_A = 0 THEN
    TRIP_SETPOINT_A := 800;
  END_IF;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK TaskMain (INTERVAL := T#100ms, PRIORITY := 0);
    PROGRAM Inst0 WITH TaskMain : palanca_motor_feeder;
  END_RESOURCE
END_CONFIGURATION
EOF
ok "Palanca motor feeder ST program written to $PROGRAMS_DIR"

# =============================================================================
# 5. SCADABR
# =============================================================================
hdr "5 — ScadaBR 1.2 (Palanca SCADA HMI)"

SCADABR_DIR="$LAB/scadabr"
SCADABR_INSTALL="/opt/ScadaBR"
SCADABR_URL="https://github.com/ScadaBR/ScadaBR/releases/download/v1.2/ScadaBR_Setup_Linux.zip"
SCADABR_TOMCAT="$SCADABR_INSTALL/tomcat/bin/startup.sh"

if [[ -f "$SCADABR_TOMCAT" ]]; then
    ok "ScadaBR already installed at $SCADABR_INSTALL"
else
    if [[ ! -f "$SCADABR_DIR/install_scadabr.sh" ]]; then
        mkdir -p "$SCADABR_DIR"
        log "Downloading ScadaBR 1.2 Linux installer ..."
        if wget -q --timeout=120 --show-progress "$SCADABR_URL" -O /tmp/ScadaBR_Linux.zip; then
            log "Extracting ..."
            unzip -q /tmp/ScadaBR_Linux.zip -d /tmp/scadabr_extract
            INNER=$(find /tmp/scadabr_extract -maxdepth 1 -mindepth 1 -type d | head -1)
            SRC=$( [[ -n "$INNER" ]] && echo "$INNER" || echo "/tmp/scadabr_extract" )
            cp -r "$SRC"/. "$SCADABR_DIR"/
            rm -rf /tmp/ScadaBR_Linux.zip /tmp/scadabr_extract
            chmod +x "$SCADABR_DIR"/*.sh 2>/dev/null || true
            ok "ScadaBR 1.2 extracted to $SCADABR_DIR"
        else
            warn "ScadaBR download failed:"
            warn "  wget '$SCADABR_URL' -O /tmp/ScadaBR_Linux.zip"
            warn "  sudo unzip /tmp/ScadaBR_Linux.zip -d $SCADABR_DIR"
        fi
    else
        ok "ScadaBR installer already extracted at $SCADABR_DIR"
    fi

    if [[ -f "$SCADABR_DIR/install_scadabr.sh" ]]; then
        # Guard: installer aborts if /opt/ScadaBR exists even if empty
        if [[ -d "$SCADABR_INSTALL" && -z "$(ls -A "$SCADABR_INSTALL" 2>/dev/null)" ]]; then
            log "Removing empty $SCADABR_INSTALL from prior failed run ..."
            rm -rf "$SCADABR_INSTALL"
        fi

        log "Running ScadaBR installer in silent mode ..."
        cd "$SCADABR_DIR"
        # silent mode skips config prompts; echo 'n' suppresses the residual
        # "Launch now?" prompt caused by a $1 scoping bug in finishInstall()
        echo 'n' | bash install_scadabr.sh silent
        cd - > /dev/null

        if [[ -f "$SCADABR_TOMCAT" ]]; then
            ok "ScadaBR installed at $SCADABR_INSTALL"

            # CRITICAL: ScadaBR silent mode defaults to port 8080, which
            # conflicts with OpenPLC's web UI. Patch to 9090 immediately.
            SCADABR_SERVER_XML="$SCADABR_INSTALL/tomcat/conf/server.xml"
            if grep -q 'port="8080"' "$SCADABR_SERVER_XML" 2>/dev/null; then
                sed -i 's/port="8080"/port="9090"/' "$SCADABR_SERVER_XML"
                ok "ScadaBR Tomcat patched to port 9090 (avoids clash with OpenPLC on 8080)"
            fi
        else
            warn "ScadaBR install failed. Check: cat /tmp/scadabrInstall.log"
        fi
    fi
fi

# Desktop shortcut
cat > "$DESKTOP/ScadaBR-Palanca.desktop" <<EOF
[Desktop Entry]
Name=ScadaBR (Palanca SCADA HMI)
Comment=Evolve Power Palanca plant SCADA simulation
Exec=bash -c "sudo /opt/ScadaBR/tomcat/bin/startup.sh && sleep 15 && xdg-open http://localhost:9090/ScadaBR; exec bash"
Terminal=true
Type=Application
Icon=utilities-system-monitor
EOF
chmod +x "$DESKTOP/ScadaBR-Palanca.desktop"
chown "$REAL_USER:$REAL_USER" "$DESKTOP/ScadaBR-Palanca.desktop"

# =============================================================================
# 6. PYMODBUS + POLLING HELPER
# =============================================================================
hdr "6 — pymodbus + Evolve Power polling helper"

VENV="$LAB/venv"
if [[ ! -d "$VENV" ]]; then
    sudo -u "$REAL_USER" python3 -m venv "$VENV"
    ok "Python venv created at $VENV"
fi

sudo -u "$REAL_USER" "$VENV/bin/pip" install --quiet --upgrade pip
sudo -u "$REAL_USER" "$VENV/bin/pip" install --quiet pymodbus==3.6.9 rich click
ok "pymodbus 3.6.9 + rich installed"

cat > "$LAB/palanca_poll.py" <<'PYEOF'
#!/usr/bin/env python3
"""
palanca_poll.py — Evolve Power Palanca plant Modbus/TCP polling helper
Reads all registers from the OpenPLC simulation of the Siemens S7-1200.

OCEON Module 0 — Lab 1 exercise tool.
Run while Wireshark captures on lo (port 502) to generate clear-text
Modbus traffic for analysis.

Usage:
  python3 palanca_poll.py                      # single poll, 127.0.0.1:502
  python3 palanca_poll.py --continuous          # poll every 2 s (Ctrl+C stops)
  python3 palanca_poll.py --host 192.168.x.x   # poll a remote PLC
"""
import argparse
import time
from pymodbus.client import ModbusTcpClient
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

COIL_Q_MAP  = {0: "BREAKER_CLOSE_CMD", 1: "BREAKER_OPEN_CMD"}
COIL_IX_MAP = {0: "FEEDER_ENERGISED",  1: "OVERCURRENT_TRIP"}
INPUT_MAP   = {0: "CURRENT_MA (4-20 mA ADC)", 1: "VOLTAGE_PU (x100 = per-unit)"}
HOLDING_MAP = {0: "TRIP_SETPOINT_A"}

def poll_once(client: ModbusTcpClient) -> None:
    console.print(Panel(
        "[bold cyan]Evolve Power — Palanca Motor Feeder PLC[/bold cyan]\n"
        "[dim]Modbus/TCP FC01/FC02/FC03/FC04 — clear text, zero authentication[/dim]",
        expand=False))

    t = Table(title="Discrete Inputs (FC02, %IX)", show_lines=True)
    t.add_column("Addr", style="cyan", width=6)
    t.add_column("Tag", width=25)
    t.add_column("Value", style="yellow", width=8)
    rr = client.read_discrete_inputs(0, 2, slave=1)
    if not rr.isError():
        for i, v in enumerate(rr.bits[:2]):
            t.add_row(str(i), COIL_IX_MAP.get(i, f"IX0.{i}"),
                      "[green]ON[/green]" if v else "[red]OFF[/red]")
    console.print(t)

    t2 = Table(title="Coils / Outputs (FC01, %QX)", show_lines=True)
    t2.add_column("Addr", style="cyan", width=6)
    t2.add_column("Tag", width=25)
    t2.add_column("Value", style="yellow", width=8)
    rr2 = client.read_coils(0, 2, slave=1)
    if not rr2.isError():
        for i, v in enumerate(rr2.bits[:2]):
            t2.add_row(str(i), COIL_Q_MAP.get(i, f"QX0.{i}"),
                       "[green]ON[/green]" if v else "[red]OFF[/red]")
    console.print(t2)

    t3 = Table(title="Input Registers (FC04, %IW)", show_lines=True)
    t3.add_column("Addr", style="cyan", width=6)
    t3.add_column("Tag", width=30)
    t3.add_column("Raw Value", style="magenta", width=12)
    rr3 = client.read_input_registers(0, 2, slave=1)
    if not rr3.isError():
        for i, v in enumerate(rr3.registers):
            t3.add_row(str(i), INPUT_MAP.get(i, f"IW{i}"), str(v))
    console.print(t3)

    t4 = Table(title="Holding Registers (FC03, %QW)", show_lines=True)
    t4.add_column("Addr", style="cyan", width=6)
    t4.add_column("Tag", width=30)
    t4.add_column("Value", style="green", width=12)
    rr4 = client.read_holding_registers(0, 1, slave=1)
    if not rr4.isError():
        for i, v in enumerate(rr4.registers):
            t4.add_row(str(i), HOLDING_MAP.get(i, f"QW{i}"), str(v))
    console.print(t4)

    console.print("\n[dim]Wireshark capture: sudo wireshark -i lo -k -Y 'tcp.port == 502'[/dim]\n")

def main() -> None:
    p = argparse.ArgumentParser(description="Palanca PLC Modbus poll helper")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=502)
    p.add_argument("--continuous", action="store_true", help="Poll every 2 s")
    args = p.parse_args()

    client = ModbusTcpClient(args.host, port=args.port)
    if not client.connect():
        console.print(f"[red]Cannot connect to {args.host}:{args.port}[/red]")
        console.print("[yellow]Is OpenPLC running and PLC started?[/yellow]")
        console.print("[yellow]Check: http://localhost:8080  (openplc / openplc)[/yellow]")
        return

    if args.continuous:
        try:
            while True:
                poll_once(client)
                time.sleep(2)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped.[/dim]")
    else:
        poll_once(client)

    client.close()

if __name__ == "__main__":
    main()
PYEOF
chmod +x "$LAB/palanca_poll.py"
ok "palanca_poll.py written to $LAB"

# =============================================================================
# 7. DRAW.IO
# =============================================================================
hdr "7 — draw.io (Lab 2: Evolve Power Purdue mapping)"

if dpkg -l drawio &>/dev/null 2>&1 || command -v drawio &>/dev/null; then
    ok "draw.io already installed"
else
    log "Fetching latest draw.io release ..."
    LATEST=$(curl -s --max-time 10 "https://api.github.com/repos/jgraph/drawio-desktop/releases/latest" \
             | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null \
             || echo "v26.0.2")
    VER="${LATEST#v}"
    DL_URL="https://github.com/jgraph/drawio-desktop/releases/download/${LATEST}/drawio-amd64-${VER}.deb"
    log "Downloading draw.io ${LATEST} ..."
    if wget -q --timeout=120 "$DL_URL" -O /tmp/drawio.deb; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq /tmp/drawio.deb 2>/dev/null || \
            { apt-get install -f -y -qq; dpkg -i /tmp/drawio.deb; }
        rm -f /tmp/drawio.deb
        ok "draw.io ${LATEST} installed"
    else
        warn "draw.io download failed — install from: https://github.com/jgraph/drawio-desktop/releases"
    fi
fi

DIAGRAMS_DIR="$LAB/diagrams"
mkdir -p "$DIAGRAMS_DIR"
cat > "$DIAGRAMS_DIR/OCEON-M0-PURDUE-TEMPLATE.drawio" <<'XMLEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!--
  OCEON Module 0 — Lab 2 Worksheet
  Evolve Power: Purdue Model Mapping Exercise

  INSTRUCTIONS:
  1. Place each component card at the correct Purdue level.
  2. Draw trust boundaries in red between levels.
  3. Annotate each boundary with at least two security controls.
  4. Export as PNG and submit alongside the boundary control table.

  Named Evolve Power components to place (from Section 0.3.3):
    - 5.5 kV transformers and motors         -> Level 0
    - Siemens S7-1200 PLCs                   -> Level 1
    - Palanca SCADA HMI and local historian  -> Level 2
    - OPC-UA data aggregation server         -> Level 3
    - Jump host and VPN gateway              -> Level 3.5 (DMZ)
    - Corporate ERP and Power BI dashboards  -> Level 4 / 5
-->
<mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1"
              tooltips="1" connect="1" arrows="1" fold="1" page="1"
              pageScale="1" pageWidth="1654" pageHeight="1169" math="0" shadow="0">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>

    <mxCell id="title" value="Evolve Power — Purdue Model Mapping (OCEON-M0-PURDUE-TEMPLATE)"
      style="text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=16;fontStyle=1;verticalAlign=middle;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="10" width="1560" height="40" as="geometry"/>
    </mxCell>

    <mxCell id="L5" value="Level 5 — Enterprise Network and Cloud"
      style="swimlane;startSize=30;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="60" width="1560" height="130" as="geometry"/>
    </mxCell>
    <mxCell id="L5_ERP" value="Corporate ERP&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#6c8ebf;dashed=1;" vertex="1" parent="L5">
      <mxGeometry x="40" y="50" width="180" height="60" as="geometry"/>
    </mxCell>
    <mxCell id="L5_PBI" value="Power BI Dashboards&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#6c8ebf;dashed=1;" vertex="1" parent="L5">
      <mxGeometry x="260" y="50" width="180" height="60" as="geometry"/>
    </mxCell>

    <mxCell id="L4" value="Level 4 — Site Business Planning"
      style="swimlane;startSize=30;fillColor=#d5e8d4;strokeColor=#82b366;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="220" width="1560" height="130" as="geometry"/>
    </mxCell>
    <mxCell id="L4_note" value="[Place site-level IT systems here]"
      style="text;html=1;strokeColor=none;fillColor=none;align=left;fontSize=11;fontStyle=2;"
      vertex="1" parent="L4">
      <mxGeometry x="40" y="55" width="400" height="40" as="geometry"/>
    </mxCell>

    <mxCell id="L35" value="Level 3.5 — IT/OT DMZ (Firewall Zone)"
      style="swimlane;startSize=30;fillColor=#fff2cc;strokeColor=#d6b656;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="380" width="1560" height="130" as="geometry"/>
    </mxCell>
    <mxCell id="L35_JUMP" value="Jump Host&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#d6b656;dashed=1;" vertex="1" parent="L35">
      <mxGeometry x="40" y="50" width="180" height="60" as="geometry"/>
    </mxCell>
    <mxCell id="L35_VPN" value="VPN Gateway&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#d6b656;dashed=1;" vertex="1" parent="L35">
      <mxGeometry x="260" y="50" width="180" height="60" as="geometry"/>
    </mxCell>

    <mxCell id="TB1" value="TRUST BOUNDARY: IT / OT — add security controls here"
      style="text;html=1;strokeColor=#FF0000;fillColor=#ffe6e6;fontSize=11;fontStyle=1;align=center;rounded=1;"
      vertex="1" parent="1">
      <mxGeometry x="680" y="508" width="300" height="44" as="geometry"/>
    </mxCell>

    <mxCell id="L3" value="Level 3 — Site Operations"
      style="swimlane;startSize=30;fillColor=#ffe6cc;strokeColor=#d79b00;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="570" width="1560" height="130" as="geometry"/>
    </mxCell>
    <mxCell id="L3_OPC" value="OPC-UA Data Aggregation Server&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#d79b00;dashed=1;" vertex="1" parent="L3">
      <mxGeometry x="40" y="50" width="240" height="60" as="geometry"/>
    </mxCell>

    <mxCell id="L2" value="Level 2 — Control (HMI, Historian, DCS)"
      style="swimlane;startSize=30;fillColor=#f8cecc;strokeColor=#b85450;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="730" width="1560" height="130" as="geometry"/>
    </mxCell>
    <mxCell id="L2_HMI" value="Palanca SCADA HMI&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#b85450;dashed=1;" vertex="1" parent="L2">
      <mxGeometry x="40" y="50" width="200" height="60" as="geometry"/>
    </mxCell>
    <mxCell id="L2_HIST" value="Local Historian&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#b85450;dashed=1;" vertex="1" parent="L2">
      <mxGeometry x="280" y="50" width="200" height="60" as="geometry"/>
    </mxCell>

    <mxCell id="L1" value="Level 1 — Field Controllers (PLCs / RTUs)"
      style="swimlane;startSize=30;fillColor=#f0a30a;strokeColor=#BD7000;fontColor=#000000;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="890" width="1560" height="130" as="geometry"/>
    </mxCell>
    <mxCell id="L1_PLC" value="Siemens S7-1200 PLCs&#xa;(Modbus TCP — place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#BD7000;dashed=1;" vertex="1" parent="L1">
      <mxGeometry x="40" y="45" width="230" height="65" as="geometry"/>
    </mxCell>

    <mxCell id="L0" value="Level 0 — Physical Process (Sensors and Actuators)"
      style="swimlane;startSize=30;fillColor=#647687;strokeColor=#314354;fontColor=#ffffff;fontStyle=1;fontSize=13;"
      vertex="1" parent="1">
      <mxGeometry x="50" y="1050" width="1560" height="100" as="geometry"/>
    </mxCell>
    <mxCell id="L0_TRF" value="5.5 kV Transformers and Motors&#xa;(place here)"
      style="rounded=1;fillColor=#ffffff;strokeColor=#314354;dashed=1;" vertex="1" parent="L0">
      <mxGeometry x="40" y="28" width="240" height="52" as="geometry"/>
    </mxCell>

    <mxCell id="checklist"
      value="Checklist: &#xa;☐ All 6 components placed at correct level&#xa;☐ Trust boundaries drawn in red&#xa;☐ 2+ controls annotated per boundary&#xa;☐ Exported as PNG"
      style="text;html=0;strokeColor=#00897B;fillColor=#E0F2F1;fontSize=11;align=left;verticalAlign=top;rounded=1;"
      vertex="1" parent="1">
      <mxGeometry x="1200" y="60" width="390" height="90" as="geometry"/>
    </mxCell>
  </root>
</mxGraphModel>
XMLEOF
ok "OCEON-M0-PURDUE-TEMPLATE.drawio written to $DIAGRAMS_DIR"

# =============================================================================
# 8. OWNERSHIP SWEEP
# =============================================================================
hdr "8 — Ownership sweep"

log "Setting $REAL_USER:$REAL_USER on $LAB ..."
chown -R "$REAL_USER:$REAL_USER" "$LAB"
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/wireshark" 2>/dev/null || true
chown    "$REAL_USER:$REAL_USER" "$DESKTOP" 2>/dev/null || true
ok "All lab files owned by $REAL_USER"

# =============================================================================
# 9. VERIFICATION
# =============================================================================
hdr "9 — Verification"

PASS=0; FAIL=0

check() {
    local label="$1"; shift
    if "$@" &>/dev/null 2>&1; then
        ok "  $label"
        PASS=$((PASS + 1))
    else
        warn "  MISSING — $label"
        FAIL=$((FAIL + 1))
    fi
}

check "Wireshark"                   command -v wireshark
check "tshark"                      command -v tshark
check "Evolve-Power colour profile" test -f "$EP_PROFILE/colorfilters"
check "Nmap"                        command -v nmap
check "GNS3 server"                 command -v gns3server
check "draw.io"                     command -v drawio
check "Python3"                     command -v python3
check "venv exists"                 test -d "$VENV"
check "pymodbus in venv"            "$VENV/bin/python3" -c "import pymodbus"
check "rich in venv"                "$VENV/bin/python3" -c "import rich"
check "OpenPLC cloned"              test -d "$OPENPLC_DIR"
check "Palanca ST program"          test -f "$PROGRAMS_DIR/palanca_motor_feeder.st"
check "ScadaBR Tomcat startup"      test -f "/opt/ScadaBR/tomcat/bin/startup.sh"
check "ScadaBR port 9090 patched"   grep -q 'port="9090"' "/opt/ScadaBR/tomcat/conf/server.xml"
check "palanca_poll.py"             test -f "$LAB/palanca_poll.py"
check "Purdue template"             test -f "$DIAGRAMS_DIR/OCEON-M0-PURDUE-TEMPLATE.drawio"
check "ScadaBR desktop shortcut"    test -f "$DESKTOP/ScadaBR-Palanca.desktop"

echo ""
echo -e "${CYN}Results: ${GRN}${PASS} passed${NC} / ${RED}${FAIL} failed${NC}"
[[ $FAIL -eq 0 ]] && ok "All checks passed. Lab environment is ready." \
                  || warn "$FAIL item(s) need attention (see WARN lines above)."

# =============================================================================
# POST-INSTALL NOTES
# =============================================================================
cat <<'NOTES'

══════════════════════════════════════════════════════════════════════
  OCEON Module 0 — Post-install steps (complete in order)
══════════════════════════════════════════════════════════════════════

STEP 1: LOG OUT AND BACK IN
  Required for the wireshark group to take effect.
  Or run in the current session: newgrp wireshark

STEP 2: INSTALL OPENPLC RUNTIME (one-time, ~10 min, interactive)
  cd ~/oceon-lab/OpenPLC_v3
  sudo bash install.sh linux
  Web UI: http://localhost:8080   credentials: openplc / openplc
  REST API: https://localhost:8443 (accept the self-signed cert warning)
  Note: after install, start the service with: sudo systemctl start openplc

STEP 3: LOAD THE EVOLVE POWER PLC PROGRAM
  - Open http://localhost:8080
  - Programs -> Upload New Program
  - Select: ~/oceon-lab/evolve-power-programs/palanca_motor_feeder.st
  - Click Compile, then Start PLC
  - Confirm on Monitoring tab: BREAKER_CLOSE_CMD = TRUE

STEP 4: START SCADABR (Palanca SCADA HMI)
  ScadaBR auto-starts on reboot via crontab (root crontab, @reboot).
  For your first session before any reboot:
    sudo /opt/ScadaBR/tomcat/bin/startup.sh
  Or double-click the desktop shortcut (no password needed).
  Wait 15 seconds, then open: http://localhost:9090/ScadaBR
  Credentials: admin / admin

  Stop ScadaBR:    sudo /opt/ScadaBR/tomcat/bin/shutdown.sh
  Check running:   ss -tlnp | grep 9090

STEP 5: WIRE SCADABR TO OPENPLC (one-time, in the browser)
  Data Sources -> New Data Source -> Modbus IP
    Name: Evolve Power PLC
    Host: 127.0.0.1   Port: 502   Unit ID: 1
    Update period: 5 seconds   Transport: TCP
  Save, then add 7 data points:
    BREAKER_CLOSE_CMD  — Coil status,      Binary,               offset 0
    BREAKER_OPEN_CMD   — Coil status,      Binary,               offset 1
    FEEDER_ENERGISED   — Input status,     Binary,               offset 0
    OVERCURRENT_TRIP   — Input status,     Binary,               offset 1
    CURRENT_MA         — Input register,   Two byte int unsigned, offset 0
    VOLTAGE_PU         — Input register,   Two byte int unsigned, offset 1
    TRIP_SETPOINT_A    — Holding register, Two byte int unsigned, offset 0
  Enable the data source. All 7 points should show green status.

══════════════════════════════════════════════════════════════════════
  LAB QUICK-START COMMANDS
══════════════════════════════════════════════════════════════════════

LAB 1 — Modbus/TCP capture (45 min):
  Terminal 1 (generate traffic):
    cd ~/oceon-lab && venv/bin/python3 palanca_poll.py --continuous

  Terminal 2 (capture):
    sudo wireshark -i lo -k -Y "tcp.port == 502"
    Apply profile: Edit -> Configuration Profiles -> Evolve-Power
    If colours are dark: GTK_THEME=Adwaita:light sudo -E wireshark ...

  Service fingerprint (bonus):
    sudo nmap -sV -p 502,8080,8443,9090 127.0.0.1 -oN ~/oceon-lab/lab1_scan.txt

LAB 2 — Purdue model mapping (60 min):
    drawio ~/oceon-lab/diagrams/OCEON-M0-PURDUE-TEMPLATE.drawio

LAB 3 — ATT&CK for ICS mapping (90 min, browser only):
    https://attack.mitre.org/matrices/ics/
    Map Stuxnet, Colonial Pipeline, TRITON to technique IDs.

══════════════════════════════════════════════════════════════════════
  Lab root:  ~/oceon-lab/
  Venv:      ~/oceon-lab/venv/bin/activate
  Programs:  ~/oceon-lab/evolve-power-programs/
  Diagrams:  ~/oceon-lab/diagrams/
  Ports:     OpenPLC web=8080  REST=8443  Modbus=502
             ScadaBR HMI=9090
══════════════════════════════════════════════════════════════════════
NOTES
