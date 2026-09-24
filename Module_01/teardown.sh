#!/usr/bin/env bash
# ================================================================
# OCEON Module 1 Lab Environment Teardown
# File: teardown.sh
# Reverses: setup_lab_env.sh
# Run as your normal user: bash teardown.sh [-v] (it calls sudo itself)
# Idempotent — safe to re-run. Pass -v to also wipe the OpenPLC/ScadaBR
# Docker volumes (uploaded PLC program, ScadaBR data source config).
#
# Stops and removes the OpenPLC + ScadaBR containers (docker compose down),
# and removes everything setup_lab_env.sh created under $HOME (lab
# directory, Wireshark profile, desktop shortcut).
#
# It never touches other shared, host-wide state on its own: the built
# Docker images and apt/pip packages are left in place. At the end it
# prints the exact commands to remove each of those, for the trainee to
# run by hand if they want a fully clean host — nothing destructive
# happens to them without you typing it.
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

LAB_ROOT="$HOME/palanca_labs/module1"
# Kept in sync with setup_lab_env.sh's COMPOSE_PIN_VERSION — used only for
# the printed apt-mark unhold reminder below, not to change any behavior.
COMPOSE_PIN_VERSION="5.4.0"
PASS=0; WARN=0

log_ok()   { echo -e "${GREEN}[OK]${NC}    $*"; PASS=$((PASS + 1)); }
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
 OCEON Module 1 Lab Environment Teardown — Evolve Power / Palanca Gas Plant
BANNER
echo -e "${NC}"

# ── STEP 1: Stop and remove the PLC + SCADA containers ────────────
# OpenPLC and ScadaBR run as containers (docker/docker-compose.yml)
# instead of being installed onto the host, so a single 'docker compose
# down' fully removes both — no leftover systemd unit, no leftover
# Tomcat/JVM process surviving the session like the old host-install
# approach left behind.
log_step "STEP 1: Stop PLC + SCADA containers"

COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    if [[ "${1:-}" == "-v" ]]; then
        docker compose -f "$COMPOSE_FILE" down -v
        log_ok "OpenPLC + ScadaBR containers and volumes removed"
    else
        docker compose -f "$COMPOSE_FILE" down
        log_ok "OpenPLC + ScadaBR containers removed (volumes kept — pass -v to wipe them too)"
    fi
else
    log_warn "Docker/compose not found — skipping container teardown (nothing to do if setup never ran)"
fi

if pkill -u "$USER" -f "palanca_opcua_server.py" 2>/dev/null; then
    log_ok "Stopped running palanca_opcua_server.py process(es)"
else
    log_ok "No palanca_opcua_server.py process running"
fi

if pkill -u "$USER" -f "palanca_modbus_monitor.py" 2>/dev/null; then
    log_ok "Stopped running palanca_modbus_monitor.py process(es)"
else
    log_ok "No palanca_modbus_monitor.py process running"
fi

# ── STEP 2: Remove Wireshark Palanca-OT profile ───────────────────
log_step "STEP 2: Remove Wireshark profile"
WS_PROFILE_DIR="$HOME/.config/wireshark/profiles/Palanca-OT"
if [[ -d "$WS_PROFILE_DIR" ]]; then
    rm -rf "$WS_PROFILE_DIR"
    log_ok "Removed $WS_PROFILE_DIR"
else
    log_ok "Palanca-OT Wireshark profile already absent"
fi

if [[ -f "$HOME/Desktop/ScadaBR-Palanca.desktop" ]]; then
    rm -f "$HOME/Desktop/ScadaBR-Palanca.desktop"
    log_ok "Removed ScadaBR desktop shortcut"
else
    log_ok "ScadaBR desktop shortcut already absent"
fi

# ── STEP 3: Remove lab directory ──────────────────────────────────
log_step "STEP 3: Remove lab directory"
if [[ -d "$LAB_ROOT" ]]; then
    rm -rf "$LAB_ROOT"
    log_ok "Removed $LAB_ROOT (scripts, pcaps, topology, worksheets, outputs, logs)"
else
    log_ok "$LAB_ROOT already absent"
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  DONE: $PASS steps${NC}  ${YELLOW}WARN: $WARN${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Nothing shared/host-wide was touched. If you also want a fully clean"
echo -e "host, here's what's still in place and the commands to remove it:"
echo ""
echo -e "${CYAN}Built Docker images (openplc/scadabr, ~a few hundred MB):${NC}"
echo -e "  ${CYAN}docker compose -f $SCRIPT_DIR/docker/docker-compose.yml down --rmi all${NC}"
echo ""
echo -e "${CYAN}docker-compose-plugin version hold (setup pinned it to $COMPOSE_PIN_VERSION and held it so"
echo -e "'apt upgrade' can't drift it — leave this in place unless you're done with the lab for good):${NC}"
echo -e "  ${CYAN}sudo apt-mark unhold docker-compose-plugin${NC}"
echo ""
echo -e "${CYAN}Python libraries (pymodbus, opcua, pyshark, scapy):${NC}"
echo -e "  ${CYAN}pip3 uninstall -y pymodbus opcua pyshark scapy --break-system-packages${NC}"
echo ""
echo -e "${CYAN}apt packages (Wireshark, Nmap):${NC}"
echo -e "  ${CYAN}sudo apt-get purge -y wireshark tshark nmap${NC}"
echo -e "  ${CYAN}sudo apt-get autoremove -y${NC}"
