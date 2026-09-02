#!/usr/bin/env bash
# ================================================================
# OCEON Module 1 Lab Environment Bootstrap
# File: setup_lab_env.sh
# Target: Ubuntu 22.04/24.04 LTS or Kali Linux (rolling), x86_64
# Run this ONCE on the instructor VM before class, then replicate
# to all trainee VMs.  Safe to re-run — idempotent.
# Run as your normal user: bash setup_lab_env.sh (it calls sudo itself)
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

LAB_ROOT="$HOME/palanca_labs/module1"
PASS=0; FAIL=0; WARN=0

log_ok()   { echo -e "${GREEN}[OK]${NC}    $*"; PASS=$((PASS + 1)); }
log_fail() { echo -e "${RED}[FAIL]${NC}  $*"; FAIL=$((FAIL + 1)); }
log_warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; WARN=$((WARN + 1)); }
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

# ── STEP 0: OS detection ─────────────────────────────────────────
# Supports Ubuntu (22.04/24.04) and Kali Linux (rolling) — both are
# Debian-based with apt, but package availability and interactive
# debconf prompts differ enough to need explicit handling below.
log_step "STEP 0: OS detection"
if [[ -r /etc/os-release ]]; then
    OS_ID=$(. /etc/os-release && echo "$ID")
    OS_PRETTY=$(. /etc/os-release && echo "$PRETTY_NAME")
else
    OS_ID="unknown"
    OS_PRETTY="unknown"
fi

case "$OS_ID" in
    ubuntu) log_ok "Detected: $OS_PRETTY" ;;
    kali)   log_ok "Detected: $OS_PRETTY" ;;
    *)      log_warn "Detected: $OS_PRETTY (untested — script assumes Debian/Ubuntu apt)" ;;
esac

# ── STEP 1: System packages ──────────────────────────────────────
log_step "STEP 1: System packages"
log_info "Updating package index..."
sudo apt-get update -qq

# Wireshark's postinst asks an interactive debconf question about
# non-root packet capture. Preseed the answer and force noninteractive
# frontend so the install loop below never blocks on a TUI prompt
# (this hangs the script identically on both Kali and Ubuntu if unset).
echo "wireshark-common wireshark-common/install-setuid boolean true" | sudo debconf-set-selections
export DEBIAN_FRONTEND=noninteractive

PKGS=(
    python3 python3-pip python3-venv
    nmap wireshark tshark
    net-tools curl wget git
    build-essential cmake pkg-config
    bison flex autoconf
    libpcap-dev libssl-dev sqlite3 libsqlite3-dev libboost-all-dev
    default-jre-headless   # ScadaBR dependency — portable metapackage,
                            # not a hardcoded version that can vanish
                            # from a rolling distro's repos
)

for pkg in "${PKGS[@]}"; do
    if dpkg -s "$pkg" &>/dev/null; then
        log_ok "$pkg already installed"
    else
        log_info "Installing $pkg..."
        if sudo -E apt-get install -y -qq "$pkg" 2>/dev/null; then
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
    # Remove any stale clone from a prior failed run so this stays
    # idempotent — 'git clone' refuses to clone into a non-empty dir.
    rm -rf /tmp/OpenPLC_v3
    cd /tmp
    if git clone https://github.com/thiagoralves/OpenPLC_v3.git --depth=1 -q; then
        cd /tmp/OpenPLC_v3
        # OpenPLC vendors an old OpenDNP3 CMakeLists.txt that current
        # CMake (4.x, shipped by Kali rolling and eventually newer
        # Ubuntu) refuses to configure without an explicit policy
        # floor — this env var is the workaround install.sh's own
        # cmake error message points at.
        sudo env CMAKE_POLICY_VERSION_MINIMUM=3.5 bash install.sh linux 2>/dev/null && log_ok "OpenPLC installed" || log_fail "OpenPLC install script failed"
        cd /tmp
    else
        log_fail "OpenPLC git clone failed — check internet connectivity"
    fi
fi

# Create systemd service for OpenPLC only if the runtime actually
# installed — otherwise the service points at a server.py that
# doesn't exist and will just crash-loop.
if [[ -f "$OPENPLC_DIR/webserver/server.py" ]] && \
   ! systemctl list-units --full -all | grep -q "openplc.service"; then
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
    log_info "ScadaBR requires manual installation — see README.md > Troubleshooting"
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

# Copy PLC program (lives alongside this script in Module_01/)
if [[ -f "$SCRIPT_DIR/palanca_gen_start.st" ]]; then
    cp "$SCRIPT_DIR/palanca_gen_start.st" "$LAB_ROOT/"
    log_ok "Copied palanca_gen_start.st"
else
    log_warn "palanca_gen_start.st not found in $SCRIPT_DIR — copy manually"
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
# Worksheet lives alongside this script in Module_01/, not in a
# separate worksheets/ subdirectory.
log_step "STEP 8: Asset inventory template"
CSV_FILE="$LAB_ROOT/palanca_asset_inventory.csv"
if [[ ! -f "$CSV_FILE" ]]; then
    if cp "$SCRIPT_DIR/palanca_asset_inventory.csv" "$LAB_ROOT/" 2>/dev/null; then
        log_ok "Asset inventory CSV copied: $CSV_FILE"
    else
        log_warn "palanca_asset_inventory.csv not found in $SCRIPT_DIR — copy manually"
    fi
else
    log_ok "Asset inventory CSV already exists"
fi

# ── STEP 9: draw.io topology base XML ────────────────────────────
# Same fix: file lives alongside this script, not in a topology/
# subdirectory of the repo.
log_step "STEP 9: draw.io topology base file"
TOPOLOGY_FILE="$LAB_ROOT/topology/palanca_topology_base.xml"
if [[ ! -f "$TOPOLOGY_FILE" ]]; then
    if cp "$SCRIPT_DIR/palanca_topology_base.xml" "$LAB_ROOT/topology/" 2>/dev/null; then
        log_ok "Topology base XML copied: $TOPOLOGY_FILE"
    else
        log_warn "Topology XML not found — will be generated separately"
    fi
else
    log_ok "Topology base XML already exists"
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

# Python check — import success is the pass/fail criterion; version
# strings are best-effort only since not every OT library exposes
# __version__ (opcua notably doesn't on all releases).
if python3 -c "import pymodbus, opcua, scapy, pyshark" 2>/dev/null; then
    PYVER=$(python3 -c "
import pymodbus
print('pymodbus', getattr(pymodbus, '__version__', 'unknown'))
" 2>/dev/null)
    log_ok "Python OT libraries importable ($PYVER)"
else
    log_fail "Python library import failed"
fi

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
    echo -e "Check README.md → Section: Troubleshooting"
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
