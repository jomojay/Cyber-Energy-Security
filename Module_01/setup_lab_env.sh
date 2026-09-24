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

# Captured before anything below ever cd's away — computing this later,
# from a relative $0 like "setup_lab_env.sh", would resolve against
# whatever the cwd happens to be at that point instead of this script's
# own folder, and the OpenPLC/ScadaBR docker-compose stack lives at a
# fixed path relative to this file, not to the caller's cwd.
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
    build-essential pkg-config
    libpcap-dev libssl-dev
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

# pymodbus is pinned, not just "installed if missing" like the others below:
# every lab script here (palanca_modbus_read.py, palanca_modbus_monitor.py,
# palanca_opcua_server.py) calls read_holding_registers()/read_coils()/etc.
# with the slave= keyword. pymodbus 3.9+ renamed that to device_id=, so an
# unpinned 'pip3 install pymodbus' silently picks up whatever the latest
# release is and every one of those calls fails with "unexpected keyword
# argument 'slave'" the moment it runs — not a bug in the scripts, a version
# drift bug. Pinned to the same 3.6.9 Introductory_Module's venv already
# uses for this exact reason. The check compares the installed version, not
# just whether pymodbus imports, so a stale newer version gets corrected on
# a re-run instead of being reported as "already installed".
PYMODBUS_VERSION="3.6.9"
CURRENT_PYMODBUS=$(python3 -c "import pymodbus; print(pymodbus.__version__)" 2>/dev/null || echo "")
if [[ "$CURRENT_PYMODBUS" == "$PYMODBUS_VERSION" ]]; then
    log_ok "pymodbus $PYMODBUS_VERSION already installed"
else
    log_info "Installing pymodbus==$PYMODBUS_VERSION (found: ${CURRENT_PYMODBUS:-none})..."
    if pip3 install "pymodbus==$PYMODBUS_VERSION" --break-system-packages -q 2>/dev/null; then
        log_ok "pymodbus $PYMODBUS_VERSION installed"
    else
        log_fail "pymodbus==$PYMODBUS_VERSION — pip install failed"
    fi
fi

PYLIBS=(opcua pyshark scapy)
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

# ── STEP 3: PLC + SCADA stack — OpenPLC + ScadaBR (Docker) ────────
# Both run as containers (see docker/docker-compose.yml) instead of being
# compiled/installed onto the host. This is what makes teardown.sh able to
# fully remove them with 'docker compose down' — no leftover /opt install,
# no leftover systemd unit, no leftover Tomcat/JVM process surviving a
# session, unlike the old host-install approach.
log_step "STEP 3: PLC + SCADA stack: OpenPLC + ScadaBR (Docker)"

DOCKER_DIR="$SCRIPT_DIR/docker"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.yml"
COMPOSE_LOG_DIR="$HOME/palanca_labs/module1/logs"
mkdir -p "$COMPOSE_LOG_DIR"

# Both instructor and trainee VMs get docker-compose-plugin from the same
# place (Docker's official apt repo, download.docker.com) and the same
# Docker Engine (29.7.2) — the plugin is never actually missing. The
# breakage is a version drift: whichever docker-compose-plugin release was
# "latest" in the repo at the moment each machine ran apt install ended up
# installed, so the instructor's box landed on 5.4.0 (installed earlier)
# while trainee boxes landed on 5.5.0 (installed later, after 5.5.0 shipped)
# — same repo, different point release, and 5.5.0 is what's breaking
# build/up on the trainee side. Pinning every machine to the exact release
# this lab has been verified against removes that drift instead of trusting
# apt to resolve "latest" the same way run after run.
COMPOSE_PIN_VERSION="5.4.0"

ensure_docker_compose_plugin() {
    local installed
    installed=$(dpkg-query -W -f='${Version}' docker-compose-plugin 2>/dev/null || echo "")

    if [[ "$installed" == "$COMPOSE_PIN_VERSION"-* ]]; then
        log_ok "docker-compose-plugin $installed already pinned to the tested version"
    else
        log_info "docker-compose-plugin is ${installed:-not installed} — pinning to $COMPOSE_PIN_VERSION (the version this lab is verified against)..."
        if sudo -E apt-get install -y -qq --allow-downgrades "docker-compose-plugin=${COMPOSE_PIN_VERSION}*" 2>/dev/null; then
            log_ok "docker-compose-plugin pinned to $(dpkg-query -W -f='${Version}' docker-compose-plugin 2>/dev/null)"
        else
            log_warn "Could not pin docker-compose-plugin to $COMPOSE_PIN_VERSION — it may no longer be" \
                     "available in the configured apt repo. Continuing with $(dpkg-query -W -f='${Version}' docker-compose-plugin 2>/dev/null || echo 'no version installed'):" \
                     "if the build/up steps below fail, this version mismatch is the likely cause."
        fi
    fi

    # Hold the package at whatever version we just landed on so a later
    # 'apt upgrade' (run by the trainee for unrelated reasons, or a fresh
    # 'apt-get update' before a future cohort) can't silently pull a newer
    # docker-compose-plugin back in and reintroduce this exact drift.
    # Permanent until explicitly undone — see teardown.sh's printed note on
    # 'apt-mark unhold docker-compose-plugin'.
    if apt-mark showhold 2>/dev/null | grep -qx docker-compose-plugin; then
        log_ok "docker-compose-plugin already held at its current version"
    elif sudo apt-mark hold docker-compose-plugin &>/dev/null; then
        log_ok "docker-compose-plugin held — 'apt upgrade' won't drift it off $COMPOSE_PIN_VERSION anymore"
    else
        log_warn "Could not apt-mark hold docker-compose-plugin — version drift could recur on a future apt upgrade"
    fi

    docker compose version &>/dev/null
}

if ! command -v docker &>/dev/null; then
    log_fail "Docker is not installed. Install Docker Engine + Compose plugin first:" \
             "https://docs.docker.com/engine/install/"
elif ! ensure_docker_compose_plugin; then
    log_fail "'docker compose' (v2 plugin) still not usable after attempting to pin it." \
             "Install it manually: https://docs.docker.com/compose/install/linux/"
else
    log_info "Docker: $(docker --version)"
    log_info "Compose: $(docker compose version --short 2>/dev/null || docker compose version)"

    # Newer Compose releases can default to building through 'docker buildx
    # bake' (COMPOSE_BAKE). That path needs the buildx plugin configured,
    # which isn't guaranteed on every trainee VM, and was a plausible cause
    # of the "docker compose up failed" reports even though these
    # Dockerfiles use nothing buildx-specific. Forcing the classic builder
    # here removes that whole class of version-dependent build failure.
    export COMPOSE_BAKE=false

    BUILD_LOG="$COMPOSE_LOG_DIR/compose_build.log"
    UP_LOG="$COMPOSE_LOG_DIR/compose_up.log"
    BUILD_OK=false

    log_info "Building OpenPLC + ScadaBR images (first run takes several minutes)..."
    if docker compose -f "$COMPOSE_FILE" build >"$BUILD_LOG" 2>&1; then
        log_ok "Images built"
        BUILD_OK=true
    else
        log_fail "docker compose build failed — last lines of $BUILD_LOG:"
        tail -n 20 "$BUILD_LOG" | sed 's/^/         /'
    fi

    if [[ "$BUILD_OK" == true ]]; then
        log_info "Starting OpenPLC + ScadaBR containers..."
        if docker compose -f "$COMPOSE_FILE" up -d >"$UP_LOG" 2>&1; then
            log_ok "Containers started"
        else
            log_fail "docker compose up failed — last lines of $UP_LOG:"
            tail -n 20 "$UP_LOG" | sed 's/^/         /'
        fi
    else
        log_warn "Skipping 'docker compose up' — image build did not succeed"
    fi

    # Poll instead of a single flat sleep: a JVM/Tomcat (ScadaBR) or a
    # first-boot OpenPLC runtime can take well past 3 seconds on slower
    # trainee hardware, which was turning a plain "still starting" into a
    # false "port not listening" failure report.
    log_info "Waiting for services to come up (up to 60s)..."
    PORT_502_UP=false; PORT_9090_UP=false
    for _ in $(seq 1 20); do
        ss -tlnp 2>/dev/null | grep -q ':502 ' && PORT_502_UP=true
        ss -tlnp 2>/dev/null | grep -q ':9090 ' && PORT_9090_UP=true
        [[ "$PORT_502_UP" == true && "$PORT_9090_UP" == true ]] && break
        sleep 3
    done

    if [[ "$PORT_502_UP" == true ]]; then
        log_ok "OpenPLC Modbus server listening on port 502"
    else
        log_warn "Port 502 not yet listening — check: docker compose -f $COMPOSE_FILE logs openplc"
    fi
    if [[ "$PORT_9090_UP" == true ]]; then
        log_ok "ScadaBR listening on port 9090"
    else
        log_warn "Port 9090 not yet listening — check: docker compose -f $COMPOSE_FILE logs scadabr"
    fi
fi

# Desktop shortcut — brings the containers up (in case they were stopped)
# and opens the browser, instead of the old direct Tomcat startup.sh call.
DESKTOP="$HOME/Desktop"
mkdir -p "$DESKTOP"
cat > "$DESKTOP/ScadaBR-Palanca.desktop" <<EOF
[Desktop Entry]
Name=ScadaBR (Palanca SCADA HMI)
Comment=Evolve Power Palanca plant SCADA simulation
Exec=bash -c "docker compose -f $COMPOSE_FILE up -d scadabr && sleep 15 && xdg-open http://localhost:9090/ScadaBR; exec bash"
Terminal=true
Type=Application
Icon=utilities-system-monitor
EOF
chmod +x "$DESKTOP/ScadaBR-Palanca.desktop"
log_ok "ScadaBR desktop shortcut created"

# ── STEP 4: Lab directory structure ──────────────────────────────
log_step "STEP 4: Lab directory structure"
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

# ── STEP 5: Generate baseline PCAP ───────────────────────────────
log_step "STEP 5: Generate Palanca baseline PCAP for Lab 5"
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

# ── STEP 6: Wireshark Palanca-OT profile ─────────────────────────
log_step "STEP 6: Wireshark Palanca-OT profile"
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

# ── STEP 7: Asset inventory CSV ───────────────────────────────────
# Worksheet lives alongside this script in Module_01/, not in a
# separate worksheets/ subdirectory.
log_step "STEP 7: Asset inventory template"
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

# ── STEP 8: draw.io topology base XML ────────────────────────────
# Same fix: file lives alongside this script, not in a topology/
# subdirectory of the repo.
log_step "STEP 8: draw.io topology base file"
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

# ── STEP 9: Final verification ───────────────────────────────────
log_step "STEP 9: Environment verification"

# Port 502 — Modbus
if ss -tlnp 2>/dev/null | grep -q ':502 '; then
    log_ok "Port 502 (Modbus/TCP) LISTENING"
else
    log_warn "Port 502 not listening — check: docker compose -f $COMPOSE_FILE logs openplc"
fi

# Port 8080 — OpenPLC web
if ss -tlnp 2>/dev/null | grep -q ':8080 '; then
    log_ok "Port 8080 (OpenPLC web) LISTENING — http://localhost:8080"
else
    log_warn "Port 8080 not listening"
fi

# ScadaBR container
SCADABR_RUNNING=false
if docker compose -f "$COMPOSE_FILE" ps --status running --services 2>/dev/null | grep -qx scadabr; then
    SCADABR_RUNNING=true
    log_ok "ScadaBR container running — http://localhost:9090/ScadaBR"
else
    log_warn "ScadaBR container not running — check: docker compose -f $COMPOSE_FILE logs scadabr"
fi

# Port 4840 — OPC-UA (Python fallback server, only relevant if ScadaBR isn't running)
if ss -tlnp 2>/dev/null | grep -q ':4840 '; then
    log_ok "Port 4840 (OPC-UA) LISTENING"
elif [[ "$SCADABR_RUNNING" == true ]]; then
    log_ok "Port 4840 not listening — expected, ScadaBR is running as the Lab 4 HMI/OPC-UA source"
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
    if python3 -c "import pymodbus; exit(0 if pymodbus.__version__ == '$PYMODBUS_VERSION' else 1)" 2>/dev/null; then
        log_ok "pymodbus pinned at $PYMODBUS_VERSION (the version these lab scripts' slave= calls need)"
    else
        log_fail "pymodbus is not pinned at $PYMODBUS_VERSION — lab scripts will fail with" \
                  "\"unexpected keyword argument 'slave'\" on newer pymodbus. Re-run this script."
    fi
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
if [[ "$SCADABR_RUNNING" == true ]]; then
    echo -e "${CYAN}ScadaBR (Palanca SCADA HMI):${NC}"
    echo -e "  Start:  ${CYAN}docker compose -f $COMPOSE_FILE up -d scadabr${NC}   (or double-click the desktop shortcut)"
    echo -e "  Visit:  http://localhost:9090/ScadaBR   (admin / admin)"
    echo -e "  Stop:   ${CYAN}docker compose -f $COMPOSE_FILE stop scadabr${NC}"
    echo -e "  Wire it to OpenPLC (one-time, in the browser): Data Sources -> New Data Source -> Modbus IP"
    echo -e "    Host openplc  Port 502  Unit ID 1 — see README.md, Lab 4 for the exact points to add."
    echo -e "    (Host is the container name \"openplc\", not 127.0.0.1 — ScadaBR and OpenPLC are"
    echo -e "    separate containers on the same Docker network.)"
    echo ""
fi
echo -e "Quick lab-start commands:"
echo -e "  Verify Modbus:  ${CYAN}ss -an | grep :502${NC}"
echo -e "  Verify OPC-UA:  ${CYAN}ss -an | grep :4840${NC}"
echo -e "  Test Modbus:    ${CYAN}python3 $LAB_ROOT/scripts/palanca_modbus_read.py${NC}"
echo -e "  Browse OPC-UA:  ${CYAN}python3 $LAB_ROOT/scripts/palanca_opcua_browse.py${NC}"
