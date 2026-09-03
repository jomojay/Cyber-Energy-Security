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

# Captured before anything below ever cd's away (Step 3's OpenPLC clone
# changes into /tmp and doesn't come back) — computing this later, from
# a relative $0 like "setup_lab_env.sh", would resolve against whatever
# the cwd happens to be at that point instead of this script's own folder.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    net-tools curl wget git unzip
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

# OpenPLC's own install.sh treats the directory it's run FROM as its
# permanent home: it hardcodes WorkingDirectory=$PWD into the systemd
# unit it creates itself, and bakes that same path into the
# start_openplc.sh launcher it generates. It does not "install"
# anywhere else — the clone location IS the install. So this has to
# clone straight into /opt/OpenPLC_v3 and run install.sh from there.
# (An earlier version of this script staged the clone in /tmp instead
# and checked for /opt/OpenPLC_v3 here for idempotency — since nothing
# ever created that path, every re-run wiped and rebuilt /tmp/OpenPLC_v3
# out from under the still-running service, corrupting its database —
# "Error Opening the DB" after login was the symptom.)
if [[ -f "$OPENPLC_DIR/start_openplc.sh" ]] && systemctl list-unit-files 2>/dev/null | grep -q '^openplc\.service'; then
    log_ok "OpenPLC found at $OPENPLC_DIR"
elif [[ -f "$OPENPLC_DIR/start_openplc.sh" ]]; then
    # The build is already there but the systemd unit isn't — e.g.
    # teardown.sh removed the unit (it always does, to prevent collisions
    # with Introductory_Module's OpenPLC install) while intentionally
    # leaving /opt/OpenPLC_v3 itself in place. Recreate just the unit —
    # identical to what OpenPLC's own install.sh writes — rather than
    # paying for a full rebuild.
    log_info "OpenPLC found at $OPENPLC_DIR but its systemd unit is missing — recreating it..."
    sudo tee /usr/lib/systemd/system/openplc.service > /dev/null <<SVC
[Unit]
Description=OpenPLC Service
After=network.target

[Service]
Type=simple
Restart=always
RestartSec=1
User=root
Group=root
WorkingDirectory=$OPENPLC_DIR
ExecStart=$OPENPLC_DIR/start_openplc.sh

[Install]
WantedBy=multi-user.target
SVC
    sudo systemctl daemon-reload
    sudo systemctl enable openplc.service 2>/dev/null || true
    log_ok "Recreated OpenPLC systemd unit pointing at $OPENPLC_DIR"
else
    log_info "Installing OpenPLC Runtime..."
    # Clean up any partial install from an interrupted prior run —
    # 'git clone' refuses to clone into a non-empty directory.
    sudo rm -rf "$OPENPLC_DIR"
    if sudo git clone https://github.com/thiagoralves/OpenPLC_v3.git --depth=1 -q "$OPENPLC_DIR"; then
        cd "$OPENPLC_DIR"
        # OpenPLC vendors an old OpenDNP3 CMakeLists.txt that current
        # CMake (4.x, shipped by Kali rolling and eventually newer
        # Ubuntu) refuses to configure without an explicit policy
        # floor — this env var is the workaround install.sh's own
        # cmake error message points at.
        sudo env CMAKE_POLICY_VERSION_MINIMUM=3.5 bash install.sh linux 2>/dev/null && log_ok "OpenPLC installed" || log_fail "OpenPLC install script failed"
        cd - > /dev/null
    else
        log_fail "OpenPLC git clone failed — check internet connectivity"
    fi
fi

# install.sh (above) already created and enabled its own systemd unit
# (openplc.service, at /lib/systemd/system) pointing at $OPENPLC_DIR —
# nothing to create here. Use 'restart', not 'start': openplc.service is
# a single system-wide unit name also used by Introductory_Module's manual
# OpenPLC install, and 'start' is a no-op against an already-active unit —
# if some earlier install (this module's or the other one's) left it
# running, 'start' would leave that stale process serving requests forever
# instead of the version just built here. 'restart' always relaunches.
sudo systemctl restart openplc.service 2>/dev/null || true
sleep 3

if ss -tlnp 2>/dev/null | grep -q ':502 '; then
    log_ok "OpenPLC Modbus server listening on port 502"
elif ss -tlnp 2>/dev/null | grep -q ':8080 '; then
    log_ok "OpenPLC web interface listening on port 8080"
    log_warn "Modbus port 502 not yet active — upload a program via http://localhost:8080"
else
    log_warn "OpenPLC not yet responding — may need manual start: sudo systemctl start openplc"
fi

# ── STEP 4: ScadaBR (Palanca SCADA HMI) ───────────────────────────
# Ported from Introductory_Module/oceon_m0_lab_setup.sh, adapted for
# this script's no-sudo invocation: the whole script runs as the
# trainee, so root is requested per-command instead of once up front.
log_step "STEP 4: ScadaBR (Palanca SCADA HMI)"
SCADABR_DIR="$LAB_ROOT/scadabr"
SCADABR_INSTALL="/opt/ScadaBR"
SCADABR_URL="https://github.com/ScadaBR/ScadaBR/releases/download/v1.2/ScadaBR_Setup_Linux.zip"
SCADABR_TOMCAT="$SCADABR_INSTALL/tomcat/bin/startup.sh"

if [[ -f "$SCADABR_TOMCAT" ]]; then
    log_ok "ScadaBR already installed at $SCADABR_INSTALL"
else
    if [[ ! -f "$SCADABR_DIR/install_scadabr.sh" ]]; then
        mkdir -p "$SCADABR_DIR"
        log_info "Downloading ScadaBR 1.2 Linux installer..."
        if wget -q --timeout=120 "$SCADABR_URL" -O /tmp/ScadaBR_Linux.zip; then
            log_info "Extracting..."
            unzip -q /tmp/ScadaBR_Linux.zip -d /tmp/scadabr_extract
            INNER=$(find /tmp/scadabr_extract -maxdepth 1 -mindepth 1 -type d | head -1)
            SRC=$( [[ -n "$INNER" ]] && echo "$INNER" || echo "/tmp/scadabr_extract" )
            cp -r "$SRC"/. "$SCADABR_DIR"/
            rm -rf /tmp/ScadaBR_Linux.zip /tmp/scadabr_extract
            chmod +x "$SCADABR_DIR"/*.sh 2>/dev/null || true
            log_ok "ScadaBR 1.2 extracted to $SCADABR_DIR"
        else
            log_fail "ScadaBR download failed:" \
                     "wget '$SCADABR_URL' -O /tmp/ScadaBR_Linux.zip"
        fi
    else
        log_ok "ScadaBR installer already extracted at $SCADABR_DIR"
    fi

    if [[ -f "$SCADABR_DIR/install_scadabr.sh" ]]; then
        # Guard: installer aborts if /opt/ScadaBR exists even if empty
        if [[ -d "$SCADABR_INSTALL" && -z "$(ls -A "$SCADABR_INSTALL" 2>/dev/null)" ]]; then
            log_info "Removing empty $SCADABR_INSTALL from prior failed run..."
            sudo rm -rf "$SCADABR_INSTALL"
        fi

        log_info "Running ScadaBR installer in silent mode (requires sudo)..."
        cd "$SCADABR_DIR"
        # silent mode skips config prompts; echo 'n' suppresses the residual
        # "Launch now?" prompt caused by a $1 scoping bug in finishInstall()
        echo 'n' | sudo bash install_scadabr.sh silent
        cd - > /dev/null

        if [[ -f "$SCADABR_TOMCAT" ]]; then
            log_ok "ScadaBR installed at $SCADABR_INSTALL"

            # CRITICAL: ScadaBR silent mode defaults to port 8080, which
            # conflicts with OpenPLC's web UI. Patch to 9090 immediately.
            SCADABR_SERVER_XML="$SCADABR_INSTALL/tomcat/conf/server.xml"
            if sudo grep -q 'port="8080"' "$SCADABR_SERVER_XML" 2>/dev/null; then
                sudo sed -i 's/port="8080"/port="9090"/' "$SCADABR_SERVER_XML"
                log_ok "ScadaBR Tomcat patched to port 9090 (avoids clash with OpenPLC on 8080)"
            fi
        else
            log_fail "ScadaBR install failed. Check: cat /tmp/scadabrInstall.log"
        fi
    fi
fi

# Desktop shortcut
DESKTOP="$HOME/Desktop"
mkdir -p "$DESKTOP"
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
log_ok "ScadaBR desktop shortcut created"

# ScadaBR is the preferred OPC-UA/HMI source; the bundled Python server
# remains available as a fallback if ScadaBR failed to install above.
if [[ ! -f "$SCADABR_TOMCAT" ]]; then
    log_warn "Lab 4 (OPC-UA) will use the bundled Python OPC-UA server instead:" \
             "python3 $LAB_ROOT/scripts/palanca_opcua_server.py (see README.md, Lab 4)"
fi

# ── STEP 5: Lab directory structure ──────────────────────────────
log_step "STEP 5: Lab directory structure"
mkdir -p "$LAB_ROOT"/{pcaps,scripts,worksheets,outputs,logs,topology}
chmod 755 "$LAB_ROOT"

log_ok "Lab directory: $LAB_ROOT"

# Copy lab scripts to trainee lab directory (SCRIPT_DIR captured at the top)

for script in palanca_modbus_read.py palanca_modbus_monitor.py palanca_opcua_browse.py palanca_opcua_server.py generate_baseline_pcap.py; do
    if [[ -f "$LAB_ROOT/scripts/$script" ]]; then
        # Never overwrite once copied — palanca_modbus_read.py is the Lab 3
        # trainee template (edited in place, <<< TASK >>> sections), and a
        # re-run of this script must not clobber that work.
        log_ok "$script already in place (not overwritten)"
    elif [[ -f "$SCRIPT_DIR/$script" ]]; then
        cp "$SCRIPT_DIR/$script" "$LAB_ROOT/scripts/"
        chmod +x "$LAB_ROOT/scripts/$script"
        log_ok "Copied $script"
    else
        log_warn "$script not found in $SCRIPT_DIR — copy manually"
    fi
done

# Copy PLC program (lives alongside this script in Module_01/)
if [[ -f "$LAB_ROOT/palanca_gen_start.st" ]]; then
    log_ok "palanca_gen_start.st already in place (not overwritten)"
elif [[ -f "$SCRIPT_DIR/palanca_gen_start.st" ]]; then
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

# Port 4840 — OPC-UA (Python fallback server, only if ScadaBR isn't installed)
if ss -tlnp 2>/dev/null | grep -q ':4840 '; then
    log_ok "Port 4840 (OPC-UA) LISTENING"
elif [[ -f "$SCADABR_TOMCAT" ]]; then
    log_ok "Port 4840 not listening — expected, ScadaBR is installed as the Lab 4 HMI/OPC-UA source"
else
    log_warn "Port 4840 not listening — start OPC-UA server before Lab 4"
fi

# ScadaBR
if [[ -f "$SCADABR_TOMCAT" ]]; then
    log_ok "ScadaBR Tomcat installed at $SCADABR_INSTALL"
    if sudo grep -q 'port="9090"' "$SCADABR_INSTALL/tomcat/conf/server.xml" 2>/dev/null; then
        log_ok "ScadaBR Tomcat patched to port 9090"
    else
        log_warn "ScadaBR Tomcat still on port 8080 — will clash with OpenPLC web UI"
    fi
else
    log_warn "ScadaBR not installed — see STEP 4 output above"
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
if [[ -f "$SCADABR_TOMCAT" ]]; then
    echo -e "${CYAN}ScadaBR (Palanca SCADA HMI):${NC}"
    echo -e "  Start:  ${CYAN}sudo /opt/ScadaBR/tomcat/bin/startup.sh${NC}   (or double-click the desktop shortcut)"
    echo -e "  Visit:  http://localhost:9090/ScadaBR   (admin / admin)"
    echo -e "  Stop:   ${CYAN}sudo /opt/ScadaBR/tomcat/bin/shutdown.sh${NC}"
    echo -e "  Wire it to OpenPLC (one-time, in the browser): Data Sources -> New Data Source -> Modbus IP"
    echo -e "    Host 127.0.0.1  Port 502  Unit ID 1 — see README.md, Lab 4 for the exact points to add."
    echo ""
fi
echo -e "Quick lab-start commands:"
echo -e "  Verify Modbus:  ${CYAN}ss -an | grep :502${NC}"
echo -e "  Verify OPC-UA:  ${CYAN}ss -an | grep :4840${NC}"
echo -e "  Test Modbus:    ${CYAN}python3 $LAB_ROOT/scripts/palanca_modbus_read.py${NC}"
echo -e "  Browse OPC-UA:  ${CYAN}python3 $LAB_ROOT/scripts/palanca_opcua_browse.py${NC}"
