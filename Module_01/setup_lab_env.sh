#!/usr/bin/env bash
# ================================================================
# OCEON Module 1 Lab Environment Bootstrap
# File: setup_lab_env.sh
# Run this ONCE on the instructor VM before class, then replicate
# to all trainee VMs.  Safe to re-run — idempotent.
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

LAB_ROOT="$HOME/palanca_labs/module1"
PASS=0; FAIL=0; WARN=0

log_ok()   { echo -e "${GREEN}[OK]${NC}    $*"; ((PASS++)); }
log_fail() { echo -e "${RED}[FAIL]${NC}  $*"; ((FAIL++)); }
log_warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; ((WARN++)); }
log_info() { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_step() { echo -e "\n${BLUE}══════ $* ══════${NC}"; }

echo -e "${BLUE}"
cat << 'BANNER'
 ██████╗  █████╗ ██╗      █████╗ ███╗   ██╗ ██████╗ █████╗
 ██╔══██╗██╔══██╗██║     ██╔══██╗████╗  ██║██╔════╝██╔══██╗
 ██████╔╝███████║██║     ███████║██╔██╗ ██║██║     ███████║
 ██╔═══╝ ██╔══██║██║     ██╔══██║██║╚██╗██║██║     ██╔══██║
 ██║     ██║  ██║███████╗██║  ██║██║ ╚████║╚██████╗██║  ██║
 ╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝
 OCEON Module 1 Lab Environment Setup — Evolve Power / Palanca Gas Plant
BANNER
echo -e "${NC}"

# ── STEP 1: System packages ──────────────────────────────────────
log_step "STEP 1: System packages"
log_info "Updating package index..."
sudo apt-get update -qq

PKGS=(
    python3 python3-pip python3-venv
    nmap wireshark tshark
    net-tools curl wget git
    libpcap-dev
    openjdk-17-jre-headless   # ScadaBR dependency
)

for pkg in "${PKGS[@]}"; do
    if dpkg -s "$pkg" &>/dev/null; then
        log_ok "$pkg already installed"
    else
        log_info "Installing $pkg..."
        if sudo apt-get install -y -qq "$pkg" 2>/dev/null; then
            log_ok "$pkg installed"
        else
            log_fail "$pkg — installation failed"
        fi
    fi
done

# Allow wireshark capture without root
if groups "$USER" | grep -q wireshark; then
    log_ok "User $USER is in wireshark group"
else
    sudo usermod -aG wireshark "$USER"
    log_warn "Added $USER to wireshark group — LOGOUT REQUIRED for capture without sudo"
fi

# ── STEP 2: Python libraries ─────────────────────────────────────
log_step "STEP 2: Python libraries"
PYLIBS=(pymodbus opcua pyshark scapy)
for lib in "${PYLIBS[@]}"; do
    if python3 -c "import ${lib//-/_}" 2>/dev/null; then
        VER=$(python3 -c "import ${lib//-/_}; print(${lib//-/_}.__version__)" 2>/dev/null || echo "unknown")
        log_ok "$lib $VER"
    else
        log_info "Installing $lib..."
        if pip3 install "$lib" --break-system-packages -q 2>/dev/null; then
            log_ok "$lib installed"
        else
            log_fail "$lib — pip install failed"
        fi
    fi
done

# ── STEP 3: OpenPLC Runtime ──────────────────────────────────────
log_step "STEP 3: OpenPLC Runtime (Modbus server)"
OPENPLC_DIR="/opt/OpenPLC_v3"

if [[ -d "$OPENPLC_DIR" ]]; then
    log_ok "OpenPLC found at $OPENPLC_DIR"
else
    log_info "Installing OpenPLC Runtime..."
    cd /tmp
    git clone https://github.com/thiagoralves/OpenPLC_v3.git --depth=1 -q 2>/dev/null || {
        log_fail "OpenPLC git clone failed — check internet connectivity"
    }
    if [[ -d /tmp/OpenPLC_v3 ]]; then
        cd /tmp/OpenPLC_v3
        sudo bash install.sh linux -q 2>/dev/null && log_ok "OpenPLC installed" || log_fail "OpenPLC install script failed"
    fi
fi

# Create systemd service for OpenPLC if it doesn't exist
if ! systemctl list-units --full -all | grep -q "openplc.service"; then
    sudo tee /etc/systemd/system/openplc.service > /dev/null << 'SVC'
[Unit]
Description=OpenPLC Runtime (Palanca Gas Plant Simulator)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/OpenPLC_v3/webserver
ExecStart=/usr/bin/python3 /opt/OpenPLC_v3/webserver/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
    sudo systemctl daemon-reload
    sudo systemctl enable openplc.service 2>/dev/null || true
    log_ok "OpenPLC systemd service created"
fi

# Try to start OpenPLC
sudo systemctl start openplc.service 2>/dev/null || true
sleep 3

if ss -tlnp 2>/dev/null | grep -q ':502 '; then
    log_ok "OpenPLC Modbus server listening on port 502"
elif ss -tlnp 2>/dev/null | grep -q ':8080 '; then
    log_ok "OpenPLC web interface listening on port 8080"
    log_warn "Modbus port 502 not yet active — upload a program via http://localhost:8080"
else
    log_warn "OpenPLC not yet responding — may need manual start: sudo systemctl start openplc"
fi

# ── STEP 4: ScadaBR (OPC-UA server) ──────────────────────────────
log_step "STEP 4: ScadaBR (OPC-UA server)"
SCADABR_DIR="/opt/scadabr"

if [[ -d "$SCADABR_DIR" ]]; then
    log_ok "ScadaBR found at $SCADABR_DIR"
else
    log_info "ScadaBR requires manual installation — see INSTRUCTOR_LAB_GUIDE.md"
    log_warn "ScadaBR not installed — Lab 4 (OPC-UA) will use the Python OPC-UA server fallback"
fi

# Start Python OPC-UA fallback server if ScadaBR not present
if ! ss -tlnp 2>/dev/null | grep -q ':4840 '; then
    log_info "Starting Python OPC-UA simulator on port 4840..."
    # Will be started by the main lab setup below
fi

# ── STEP 5: Lab directory structure ──────────────────────────────
log_step "STEP 5: Lab directory structure"
mkdir -p "$LAB_ROOT"/{pcaps,scripts,worksheets,outputs,logs,topology}
chmod 755 "$LAB_ROOT"

log_ok "Lab directory: $LAB_ROOT"

# Copy lab scripts to trainee lab directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for script in palanca_modbus_read.py palanca_modbus_monitor.py palanca_opcua_browse.py palanca_opcua_server.py generate_baseline_pcap.py; do
    if [[ -f "$SCRIPT_DIR/$script" ]]; then
        cp "$SCRIPT_DIR/$script" "$LAB_ROOT/scripts/"
        chmod +x "$LAB_ROOT/scripts/$script"
        log_ok "Copied $script"
    else
        log_warn "$script not found in $SCRIPT_DIR — copy manually"
    fi
done

# Copy PLC program
if [[ -f "$SCRIPT_DIR/../data/palanca_gen_start.st" ]]; then
    cp "$SCRIPT_DIR/../data/palanca_gen_start.st" "$LAB_ROOT/"
    log_ok "Copied palanca_gen_start.st"
fi

# ── STEP 6: Generate baseline PCAP ───────────────────────────────
log_step "STEP 6: Generate Palanca baseline PCAP for Lab 5"
PCAP_FILE="$LAB_ROOT/pcaps/palanca_baseline.pcap"

if [[ -f "$PCAP_FILE" ]]; then
    log_ok "Baseline PCAP already exists: $PCAP_FILE"
else
    if [[ -f "$LAB_ROOT/scripts/generate_baseline_pcap.py" ]]; then
        log_info "Generating baseline PCAP..."
        python3 "$LAB_ROOT/scripts/generate_baseline_pcap.py" "$PCAP_FILE" && \
            log_ok "Baseline PCAP generated: $PCAP_FILE" || \
            log_fail "PCAP generation failed — run manually"
    else
        log_warn "generate_baseline_pcap.py not yet copied — run after setup"
    fi
fi

# ── STEP 7: Wireshark Palanca-OT profile ─────────────────────────
log_step "STEP 7: Wireshark Palanca-OT profile"
WS_PROFILE_DIR="$HOME/.config/wireshark/profiles/Palanca-OT"
mkdir -p "$WS_PROFILE_DIR"

# Write preferences file
cat > "$WS_PROFILE_DIR/preferences" << 'WSPREFS'
# Wireshark Palanca-OT Profile — OCEON Module 1
gui.column.format: "No.", "%m","Time","6t","Source","18s","Destination","18s","Protocol","10p","Length","L","Modbus FC","cus:modbus.func_code:4:R","Info","i"
gui.color_filter_bg.colorRules: (true,"modbus","000000","A8D4F5")(true,"opcua","000000","B4E8C1")(true,"tcp && tcp.flags.syn==1","000000","FFE4B5")(true,"tcp.analysis.flags","FFFFFF","FF0000")
WSPREFS

# Write colour filter file
cat > "$WS_PROFILE_DIR/colorfilters" << 'WSCOLORS'
# Palanca-OT colour scheme
@Modbus/TCP (field devices)@modbus@[00000000][a8d4f500]
@OPC-UA (supervisory)@opcua@[00000000][b4e8c100]
@TCP SYN (new connections)@tcp.flags.syn == 1 && tcp.flags.ack == 0@[00000000][ffe4b500]
@TCP errors@tcp.analysis.flags@[ffffffff][ff000000]
WSCOLORS

# Write display filter macros
cat > "$WS_PROFILE_DIR/dfilter_macros" << 'WSMACROS'
"Modbus Only" "modbus"
"OPC-UA Only" "opcua"
"Modbus Writes" "modbus.func_code >= 5"
"FC03 Read Holding" "modbus.func_code == 3"
"From PLC" "ip.src == 192.168.100.10"
"To PLC" "ip.dst == 192.168.100.10"
"OT Subnet Only" "ip.addr == 192.168.100.0/24"
WSMACROS

log_ok "Wireshark Palanca-OT profile installed at $WS_PROFILE_DIR"

# ── STEP 8: Asset inventory CSV ───────────────────────────────────
log_step "STEP 8: Asset inventory template"
CSV_FILE="$LAB_ROOT/palanca_asset_inventory.csv"
if [[ ! -f "$CSV_FILE" ]]; then
    cp "$SCRIPT_DIR/../worksheets/palanca_asset_inventory.csv" "$LAB_ROOT/" 2>/dev/null || \
    cat > "$CSV_FILE" << 'CSVEOF'
Device Name,Purdue Level,Vendor / Model,IP Address,MAC Address,Protocol(s),Firmware Version,OS / Platform,Criticality,Last Patched,Physical Location,Notes
PLC-Main-01,L1 — Basic Control,Siemens S7-1200,192.168.100.10,,,Modbus/TCP (Port 502),,Critical,,Electrical Room A,
GEN1-RTU,L1 — Basic Control,GE Automation RTU 300,Serial only (RS-485),,Modbus RTU (Serial),,, Critical,,Generator Deck 1,
PROTECT-REL-01,L1 — Basic Control,ABB REL670,192.168.100.30,,Modbus RTU,,IED Firmware v2.3,Critical,,Switchgear Room,
VFD-PUMP-01,L1 — Basic Control,ABB ACS580,192.168.100.40,,Modbus/TCP (Port 502),,VFD FW v4.1,Important,,Pump Room B,
SENSOR-TEMP-01,L0 — Field Device,Rosemount 3144P,HART (analog 4-20mA),,HART,,, Important,,Separator Deck,N/A — passive sensor; firmware update requires physical access
SCADA-HMI-01,L2 — Supervisory,Windows 10 Pro (Dell OptiPlex),192.168.100.20,,Modbus/TCP; OPC-UA (Port 4840),,Windows 10 Pro 22H2,Critical,,Control Room,
ENG-WS-01,L2 — Supervisory,Windows 10 Pro (HP EliteDesk),192.168.100.21,,Modbus/TCP; OPC-UA,,Windows 10 Pro 22H2,Important,,Control Room,
HISTORIAN-01,L3 — Mfg Operations,Windows Server 2019 (Dell PowerEdge),192.168.150.20,,OPC-UA (Port 4840); SQL Server,,Windows Server 2019,Important,,Server Room,
DMZ-GATEWAY-01,L3.5 — DMZ / Cell Zone,Ubuntu 22.04 LTS,192.168.150.10,,OPC-UA; Firewall (iptables),,Ubuntu 22.04.3 LTS,Critical,,Server Room,
SWITCH-MAIN-01,L2 — Supervisory,Cisco Catalyst 2960X-24TS,192.168.100.1,,Ethernet (802.1Q VLAN); SNMP,,IOS 15.2(7)E4,Critical,,Electrical Room A,SPOF — no redundant switch deployed
CSVEOF
    log_ok "Asset inventory CSV created: $CSV_FILE"
else
    log_ok "Asset inventory CSV already exists"
fi

# ── STEP 9: draw.io topology base XML ────────────────────────────
log_step "STEP 9: draw.io topology base file"
TOPOLOGY_FILE="$LAB_ROOT/topology/palanca_topology_base.xml"
if [[ ! -f "$TOPOLOGY_FILE" ]]; then
    cp "$SCRIPT_DIR/../topology/palanca_topology_base.xml" "$LAB_ROOT/topology/" 2>/dev/null || \
        log_warn "Topology XML not found — will be generated separately"
fi

# ── STEP 10: Final verification ───────────────────────────────────
log_step "STEP 10: Environment verification"

# Port 502 — Modbus
if ss -tlnp 2>/dev/null | grep -q ':502 '; then
    log_ok "Port 502 (Modbus/TCP) LISTENING"
else
    log_warn "Port 502 not listening — start OpenPLC before Lab 3: sudo systemctl start openplc"
fi

# Port 8080 — OpenPLC web
if ss -tlnp 2>/dev/null | grep -q ':8080 '; then
    log_ok "Port 8080 (OpenPLC web) LISTENING — http://localhost:8080"
else
    log_warn "Port 8080 not listening"
fi

# Port 4840 — OPC-UA
if ss -tlnp 2>/dev/null | grep -q ':4840 '; then
    log_ok "Port 4840 (OPC-UA) LISTENING"
else
    log_warn "Port 4840 not listening — start OPC-UA server before Lab 4"
fi

# Python check
python3 -c "import pymodbus, opcua, scapy; print('pymodbus', pymodbus.__version__, '| opcua', opcua.__version__)" 2>/dev/null && log_ok "Python OT libraries importable" || log_fail "Python library import failed"

# Wireshark
which wireshark &>/dev/null && log_ok "Wireshark installed: $(wireshark --version 2>/dev/null | head -1)" || log_fail "Wireshark not found"
which tshark &>/dev/null && log_ok "tshark installed" || log_fail "tshark not found"

# PCAP
[[ -f "$LAB_ROOT/pcaps/palanca_baseline.pcap" ]] && log_ok "Baseline PCAP: $(ls -lh "$LAB_ROOT/pcaps/palanca_baseline.pcap" | awk '{print $5}')" || log_warn "Baseline PCAP not yet generated"

# Lab directory
[[ -d "$LAB_ROOT/scripts" ]] && log_ok "Lab scripts directory: $LAB_ROOT/scripts" || log_fail "Lab scripts directory missing"

# Summary
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PASS: $PASS${NC}  ${RED}FAIL: $FAIL${NC}  ${YELLOW}WARN: $WARN${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}Environment has failures — resolve before class${NC}"
    echo -e "Check INSTRUCTOR_LAB_GUIDE.md → Section: Troubleshooting"
    exit 1
elif [[ $WARN -gt 0 ]]; then
    echo -e "${YELLOW}Environment has warnings — review before class${NC}"
    echo -e "Lab directory ready: $LAB_ROOT"
else
    echo -e "${GREEN}Environment is READY for Module 1 labs${NC}"
    echo -e "Lab directory: $LAB_ROOT"
    echo -e "Baseline PCAP: $LAB_ROOT/pcaps/palanca_baseline.pcap"
fi
echo ""
echo -e "Quick lab-start commands:"
echo -e "  Verify Modbus:  ${CYAN}ss -an | grep :502${NC}"
echo -e "  Verify OPC-UA:  ${CYAN}ss -an | grep :4840${NC}"
echo -e "  Test Modbus:    ${CYAN}python3 $LAB_ROOT/scripts/palanca_modbus_read.py${NC}"
echo -e "  Browse OPC-UA:  ${CYAN}python3 $LAB_ROOT/scripts/palanca_opcua_browse.py${NC}"
