#!/usr/bin/env bash
# =============================================================================
# OCEON LAB ENVIRONMENT TEARDOWN — Module 0: Introduction to Energy Cyber Security
# Case Study: Evolve Power (Palanca SCADA)
# Reverses: oceon_m0_lab_setup.sh
# Run as: sudo bash teardown.sh [-v]   (same invocation as the setup script)
# Idempotent: safe to re-run. Pass -v to also wipe the OpenPLC/ScadaBR
# Docker volumes (uploaded PLC program, ScadaBR data source config).
#
# Stops and removes the OpenPLC + ScadaBR containers (docker compose down),
# and removes everything the setup script created under the trainee's home
# directory (lab files, venv, Wireshark profile, desktop shortcut).
#
# It never touches other shared, host-wide state on its own: the built
# Docker images, group memberships, and apt packages are all left in
# place. At the end it prints the exact commands to remove each of those,
# for the trainee to run by hand if they want a fully clean host —
# nothing destructive happens to them without you typing it.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
# GUARDS — same invocation contract as oceon_m0_lab_setup.sh
# =============================================================================

[[ $EUID -eq 0 ]] || err "Run with: sudo bash $0"

if [[ -z "${SUDO_USER:-}" ]]; then
    err "SUDO_USER is not set. Run as your normal user with:
  sudo bash $0
Do NOT use 'sudo su' before running this script."
fi

REAL_USER="$SUDO_USER"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
LAB="$REAL_HOME/oceon-lab"
DESKTOP="$REAL_HOME/Desktop"

log "Tearing down for user: $REAL_USER (home: $REAL_HOME)"

# =============================================================================
# 1. STOP AND REMOVE THE PLC + SCADA CONTAINERS
# =============================================================================
# OpenPLC and ScadaBR run as containers (docker/docker-compose.yml) instead
# of being installed onto the host, so a single 'docker compose down' fully
# removes both — no leftover systemd unit, no leftover Tomcat/JVM process
# surviving the session like the old host-install approach left behind.
# Pass -v to this script to also wipe the named volumes (uploaded PLC
# program, ScadaBR data source config) for a completely clean slate.
hdr "1 — Stopping PLC + SCADA containers"

COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
    if [[ "${1:-}" == "-v" ]]; then
        docker compose -f "$COMPOSE_FILE" down -v
        ok "OpenPLC + ScadaBR containers and volumes removed"
    else
        docker compose -f "$COMPOSE_FILE" down
        ok "OpenPLC + ScadaBR containers removed (volumes kept — pass -v to wipe them too)"
    fi
else
    warn "Docker/compose not found — skipping container teardown (nothing to do if setup never ran)"
fi

if pkill -u "$REAL_USER" -f "palanca_poll.py" 2>/dev/null; then
    ok "Stopped running palanca_poll.py process(es)"
else
    ok "No palanca_poll.py process running"
fi

# =============================================================================
# 2. REMOVE TRAINEE-OWNED LAB FILES
# =============================================================================
hdr "2 — Removing lab files"

if [[ -d "$LAB" ]]; then
    rm -rf "$LAB"
    ok "Removed $LAB (venv, PLC programs, diagrams, palanca_poll.py)"
else
    ok "$LAB already absent"
fi

if [[ -f "$DESKTOP/ScadaBR-Palanca.desktop" ]]; then
    rm -f "$DESKTOP/ScadaBR-Palanca.desktop"
    ok "Removed ScadaBR desktop shortcut"
else
    ok "ScadaBR desktop shortcut already absent"
fi

EP_PROFILE="$REAL_HOME/.config/wireshark/profiles/Evolve-Power"
if [[ -d "$EP_PROFILE" ]]; then
    rm -rf "$EP_PROFILE"
    ok "Removed Evolve-Power Wireshark profile"
else
    ok "Evolve-Power Wireshark profile already absent"
fi

# =============================================================================
# SUMMARY
# =============================================================================
hdr "Done"
ok "Module 0 lab environment removed for $REAL_USER (OpenPLC + ScadaBR containers stopped and removed)."
echo ""
echo -e "${CYN}Nothing shared/host-wide was touched. If you also want a fully clean${NC}"
echo -e "${CYN}host, here's what's still in place and the commands to remove it:${NC}"
echo ""
echo -e "${CYN}Built Docker images (openplc/scadabr, ~a few hundred MB):${NC}"
echo "  docker compose -f $SCRIPT_DIR/docker/docker-compose.yml down --rmi all"
echo ""
echo -e "${CYN}wireshark/ubridge group membership (added for $REAL_USER):${NC}"
echo "  sudo gpasswd -d $REAL_USER wireshark"
echo "  sudo gpasswd -d $REAL_USER ubridge"
echo ""
echo -e "${CYN}apt packages (Wireshark, Nmap, GNS3, draw.io):${NC}"
echo "  sudo apt-get purge -y wireshark tshark gns3-server gns3-gui drawio"
echo "  sudo apt-get autoremove -y"
