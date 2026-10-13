#!/usr/bin/env bash
# ============================================================================
# Module 5 — Vulnerability Assessment Lab Setup
# No new distributed infrastructure is created — this module reuses
# Module 2's Palanca lab as the scan target.
#
# Docker lab (eng-ws-01 running):  installs python-nmap inside eng-ws-01 and
#   copies the Module 5 files to /root/module5 there — eng-ws-01 is the
#   working point for every lab day, same as Module 2.
# No Docker lab (VirtualBox build): creates a .venv here with python-nmap,
#   since Kali/Ubuntu 24.04 block system-wide pip installs (PEP 668).
#
# Idempotent. Files already in eng-ws-01:/root/module5 are NOT overwritten
# (so a re-run can't wipe a trainee's Day 3 scanner edits) unless --force.
# No sudo.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

ENGWS=eng-ws-01
DEST=/root/module5
FILES=(ot_safe_scanner.py cve_correlator.py cve_reference_dataset.json)

echo "=============================================================="
echo " Module 5 Vulnerability Assessment Lab Setup"
echo "=============================================================="

echo "--> Verifying cve_reference_dataset.json is valid..."
python3 -c "import json; json.load(open('cve_reference_dataset.json')); print('    OK')"

if command -v docker &>/dev/null && \
   [[ "$(docker inspect -f '{{.State.Running}}' "$ENGWS" 2>/dev/null)" == "true" ]]; then
  echo "--> Found running $ENGWS (Docker Module 2 lab) — setting up inside it"

  echo "--> Installing python-nmap in $ENGWS..."
  docker exec "$ENGWS" pip install --quiet --no-cache-dir --disable-pip-version-check --root-user-action=ignore python-nmap

  echo "--> Copying Module 5 files to $ENGWS:$DEST ..."
  docker exec "$ENGWS" mkdir -p "$DEST"
  for f in "${FILES[@]}"; do
    if [[ $FORCE -eq 0 ]] && docker exec "$ENGWS" test -e "$DEST/$f"; then
      echo "    [KEEP] $f (already there — re-run with --force to overwrite)"
    else
      docker cp "$f" "$ENGWS:$DEST/$f" >/dev/null
      echo "    [COPY] $f"
    fi
  done

  echo "--> Self-test inside $ENGWS..."
  docker exec -w "$DEST" "$ENGWS" python3 -c "import nmap, ot_safe_scanner; print('    python-nmap + scanner import OK')"
  docker exec -w "$DEST" "$ENGWS" python3 cve_correlator.py "Siemens S7-1200" | head -1 | sed 's/^/    /'

  echo ""
  echo "=============================================================="
  echo " Ready. Your working point (same as Module 2):"
  echo "   docker exec -it $ENGWS bash"
  echo "   cd $DEST"
  echo ""
  echo " Then:"
  echo "   python3 ot_safe_scanner.py                 # Day 3 (~4 min)"
  echo '   python3 cve_correlator.py "Siemens S7-1200" # Day 4'
  echo ""
  echo " Copy results back to the host for your report:"
  echo "   docker cp $ENGWS:$DEST/. ./my-results/"
  echo "=============================================================="
  exit 0
fi

# ---- Fallback: no Docker lab running (VirtualBox build, or lab not up) ----
echo "--> $ENGWS is not running — falling back to a host Python venv."
echo "    (Using the Docker lab? Start it first: cd ../Module_2_Lab_Setup && ./setup.sh,"
echo "     then re-run this script.)"

if ! command -v nmap &>/dev/null; then
  echo "ERROR: nmap is not installed. Install it first (e.g. sudo apt-get install nmap)."
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "--> Creating .venv ..."
  python3 -m venv .venv || {
    echo "ERROR: python3 -m venv failed. Install it first (sudo apt-get install python3-venv)."
    exit 1
  }
fi
echo "--> Installing python-nmap into .venv..."
.venv/bin/pip install --quiet --disable-pip-version-check --root-user-action=ignore python-nmap
.venv/bin/python -c "import nmap, ot_safe_scanner; print('    python-nmap + scanner import OK')"

echo ""
echo "=============================================================="
echo " Ready (host mode). Prerequisite: your Palanca lab VMs must be"
echo " running and reachable from this machine."
echo ""
echo "   source .venv/bin/activate"
echo "   python3 ot_safe_scanner.py"
echo '   python3 cve_correlator.py "Siemens S7-1200"'
echo "=============================================================="
