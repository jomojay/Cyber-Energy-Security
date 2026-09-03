#!/usr/bin/env bash
# ================================================================
# OCEON Module 1 Lab Environment Teardown
# File: teardown.sh
# Reverses: setup_lab_env.sh
# Run as your normal user: bash teardown.sh (it calls sudo itself)
# Idempotent — safe to re-run.
#
# Always stops the OpenPLC and ScadaBR services it registered/installed,
# removes the OpenPLC systemd unit (see note below on why that one isn't
# opt-in), and removes everything setup_lab_env.sh created under $HOME
# (lab directory, Wireshark profile, desktop shortcut).
#
# It never touches other shared, host-wide state on its own: the compiled
# installs at /opt/OpenPLC_v3 and /opt/ScadaBR, and apt/pip packages, are
# all left in place. At the end it prints the exact commands to remove
# each of those, for the trainee to run by hand if they want a fully
# clean host — nothing destructive happens to them without you typing it.
# ================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

LAB_ROOT="$HOME/palanca_labs/module1"
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

# ── STEP 1: Stop running services / processes ────────────────────
log_step "STEP 1: Stop services"

if systemctl list-units --full -all 2>/dev/null | grep -q "openplc.service"; then
    sudo systemctl stop openplc.service 2>/dev/null || true
    sudo systemctl disable openplc.service 2>/dev/null || true
    log_ok "OpenPLC service stopped and disabled"
else
    log_ok "OpenPLC service not registered (nothing to stop)"
fi

# openplc.service is a single, system-wide unit name shared by every OCEON
# module that installs OpenPLC — Introductory_Module's manual install and
# this script both invoke the same upstream installer, which always
# registers a service under this exact name. Unlike /opt/OpenPLC_v3 below,
# the unit file itself holds no build state and is rewritten fresh on
# every install, so it's safe to always remove it (not opt-in): leaving a
# stopped-but-present unit around is what let a stale process from a PRIOR
# install keep serving requests through a later rebuild — systemd only
# replaces a unit's running process on 'restart', never on a plain 'start'
# against an already-active unit, so a leftover unit pointed at the wrong
# directory silently wins over whatever was just built.
if [[ -f /usr/lib/systemd/system/openplc.service || -f /lib/systemd/system/openplc.service ]]; then
    sudo rm -f /usr/lib/systemd/system/openplc.service /lib/systemd/system/openplc.service
    sudo systemctl daemon-reload
    log_ok "Removed OpenPLC systemd unit (prevents it colliding with another module's install)"
else
    log_ok "No OpenPLC systemd unit file present"
fi

if [[ -x /opt/ScadaBR/tomcat/bin/shutdown.sh ]]; then
    sudo /opt/ScadaBR/tomcat/bin/shutdown.sh &>/dev/null || true
    log_ok "ScadaBR Tomcat stopped"
else
    log_ok "ScadaBR not running (no shutdown.sh found)"
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
echo -e "${CYAN}OpenPLC compiled install (the systemd service was already removed above):${NC}"
echo -e "  ${CYAN}sudo rm -rf /opt/OpenPLC_v3${NC}"
echo ""
echo -e "${CYAN}ScadaBR install (/opt/ScadaBR):${NC}"
echo -e "  ${CYAN}sudo rm -rf /opt/ScadaBR${NC}"
echo ""
echo -e "${CYAN}Python libraries (pymodbus, opcua, pyshark, scapy):${NC}"
echo -e "  ${CYAN}pip3 uninstall -y pymodbus opcua pyshark scapy --break-system-packages${NC}"
echo ""
echo -e "${CYAN}apt packages (Wireshark, Nmap, Java):${NC}"
echo -e "  ${CYAN}sudo apt-get purge -y wireshark tshark nmap default-jre-headless${NC}"
echo -e "  ${CYAN}sudo apt-get autoremove -y${NC}"
