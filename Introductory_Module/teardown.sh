#!/usr/bin/env bash
# =============================================================================
# OCEON LAB ENVIRONMENT TEARDOWN — Module 0: Introduction to Energy Cyber Security
# Case Study: Evolve Power (Palanca SCADA)
# Reverses: oceon_m0_lab_setup.sh
# Run as: sudo bash teardown.sh   (same invocation as the setup script)
# Idempotent: safe to re-run.
#
# Always stops the ScadaBR / OpenPLC services if running, removes the
# OpenPLC systemd unit (see note below on why that one isn't opt-in), and
# removes everything the setup script created under the trainee's home
# directory (lab files, venv, Wireshark profile, desktop shortcut).
#
# It never touches other shared, host-wide state on its own: the
# /opt/ScadaBR install, group memberships, and apt packages are all left
# in place. At the end it prints the exact commands to remove each of
# those, for the trainee to run by hand if they want a fully clean host —
# nothing destructive happens to them without you typing it.
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
# 1. STOP RUNNING SERVICES / PROCESSES
# =============================================================================
hdr "1 — Stopping services"

if [[ -x /opt/ScadaBR/tomcat/bin/shutdown.sh ]]; then
    /opt/ScadaBR/tomcat/bin/shutdown.sh &>/dev/null || true
    ok "ScadaBR Tomcat stopped"
else
    ok "ScadaBR not running (no shutdown.sh found)"
fi

# OpenPLC is built manually per the post-install checklist (Step 2) and its
# own installer registers a systemd service named "openplc" — stop and
# disable it if present.
if systemctl list-units --full -all 2>/dev/null | grep -q "openplc.service"; then
    systemctl stop openplc 2>/dev/null || true
    systemctl disable openplc 2>/dev/null || true
    ok "OpenPLC service stopped and disabled"
else
    ok "OpenPLC service not registered (nothing to stop)"
fi

# openplc.service is a single, system-wide unit name shared by every OCEON
# module that installs OpenPLC — this manual install and Module_01's
# automated one both invoke the same upstream installer, which always
# registers a service under this exact name. Unlike the ~/oceon-lab clone
# removed below, the unit file itself holds no build state and is
# rewritten fresh on every install, so it's safe to always remove it (not
# opt-in): leaving a stopped-but-present unit around is what let a stale
# process from a PRIOR install keep serving requests through a later
# rebuild — systemd only replaces a unit's running process on 'restart',
# never on a plain 'start' against an already-active unit, so a leftover
# unit pointed at a now-deleted directory silently wins over whatever was
# just built.
if [[ -f /usr/lib/systemd/system/openplc.service || -f /lib/systemd/system/openplc.service ]]; then
    rm -f /usr/lib/systemd/system/openplc.service /lib/systemd/system/openplc.service
    systemctl daemon-reload
    ok "Removed OpenPLC systemd unit (prevents it colliding with another module's install)"
else
    ok "No OpenPLC systemd unit file present"
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
    ok "Removed $LAB (venv, OpenPLC clone, PLC programs, diagrams, palanca_poll.py)"
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
ok "Module 0 lab environment removed for $REAL_USER (ScadaBR/OpenPLC stopped, OpenPLC unit removed)."
echo ""
echo -e "${CYN}Nothing shared/host-wide was touched. If you also want a fully clean${NC}"
echo -e "${CYN}host, here's what's still in place and the commands to remove it:${NC}"
echo ""
echo -e "${CYN}ScadaBR install (/opt/ScadaBR):${NC}"
echo "  sudo rm -rf /opt/ScadaBR"
echo ""
echo -e "${CYN}wireshark/ubridge group membership (added for $REAL_USER):${NC}"
echo "  sudo gpasswd -d $REAL_USER wireshark"
echo "  sudo gpasswd -d $REAL_USER ubridge"
echo ""
echo -e "${CYN}apt packages (Wireshark, Nmap, GNS3, draw.io, Java):${NC}"
echo "  sudo apt-get purge -y wireshark tshark gns3-server gns3-gui drawio default-jre-headless"
echo "  sudo apt-get autoremove -y"
