#!/usr/bin/env bash
# ============================================================================
# Module 4 — OT Traffic Analysis Lab Setup
#
#   ./setup.sh                      instructor: generate every capture + answer keys
#   ./setup.sh --seed 12345         re-create an earlier set of captures exactly
#   ./setup.sh --seed 12345 --no-keys
#                                   trainee: build the SAME captures as the instructor
#                                   (instructor gives out the seed) without answer keys
#   ./setup.sh --assessment         Day 7: fresh captures, events at random times
#   ./setup.sh --hours 6            shorter captures (quick demos / slow machines)
#
# Days 1-2 use LIVE capture against the existing Module 2 lab environment
# (Docker palanca-lab or the Option C VirtualBox build) - no new
# infrastructure is needed for those two days.
# No sudo needed. Safe to re-run.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

HOURS=24; SEED=""; ASSESS=""; NOKEYS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --hours) HOURS="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --assessment) ASSESS="--assessment"; shift ;;
    --no-keys) NOKEYS=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see ./setup.sh --help)"; exit 1 ;;
  esac
done

echo "=============================================================="
echo " Module 4 Traffic Analysis Lab — Setup"
echo "=============================================================="

# ---- 1. Python + libraries --------------------------------------------------
command -v python3 >/dev/null || { echo "[FAIL] python3 not found: sudo apt install python3"; exit 1; }
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

need_libs() { "$PY" -c "import numpy, pandas, matplotlib, sklearn" 2>/dev/null; }

if need_libs; then
  echo "[OK]   Python libraries present (numpy, pandas, matplotlib, scikit-learn)"
else
  echo "--> Some Python libraries are missing; creating a private environment in .venv/"
  echo "    (Kali/Ubuntu block 'pip install' into the system Python, so the lab gets its own.)"
  if ! python3 -m venv --system-site-packages .venv 2>/dev/null; then
    echo "[FAIL] Could not create a virtual environment. Install it with:"
    echo "         sudo apt install python3-venv python3-pip"
    echo "       or install the libraries system-wide:"
    echo "         sudo apt install python3-numpy python3-pandas python3-matplotlib python3-sklearn"
    exit 1
  fi
  PY=.venv/bin/python
  "$PY" -m pip install --quiet --upgrade pip || true
  "$PY" -m pip install --quiet -r requirements.txt
  need_libs || { echo "[FAIL] Library install failed - check your internet connection and re-run."; exit 1; }
  echo "[OK]   Libraries installed into .venv/ (./otlab uses it automatically)"
fi

# ---- 2. Captures ------------------------------------------------------------
ARGS=(generate --hours "$HOURS")
[ -n "$SEED" ] && ARGS+=(--seed "$SEED")
[ -n "$ASSESS" ] && ARGS+=("$ASSESS")
./otlab "${ARGS[@]}"

if [ -n "$NOKEYS" ]; then
  rm -rf captures/instructor-only
  echo "[OK]   Answer keys removed (trainee copy)."
fi

# ---- 3. Wireshark profile -------------------------------------------------------
if command -v wireshark >/dev/null || command -v tshark >/dev/null; then
  ./otlab wireshark install >/dev/null && echo "[OK]   Wireshark profile 'Palanca-OT' installed (Profile: bottom-right in Wireshark)"
else
  echo "[WARN] Wireshark not found - install it for Days 1, 2 and 6:  sudo apt install wireshark tshark"
fi

echo ""
echo "=============================================================="
echo " Done. Captures ready in ./captures/"
echo "=============================================================="
ls -la captures/ | grep -E "pcap|assessment|instructor" || true
echo ""
if [ -z "$NOKEYS" ]; then
  echo "IMPORTANT (instructor): everything in captures/instructor-only/ is an answer key"
  echo "for GRADING ONLY. Do not distribute it before the deliverables are submitted."
  echo "To give trainees identical captures, either copy the three .pcap files to them,"
  echo "or give them the seed printed above and have them run:  ./setup.sh --seed <seed> --no-keys"
  echo ""
fi
echo "Next:  ./otlab doctor      (checks everything)"
echo "       ./otlab             (menu of every tool)"
echo "       docs/TRAINEE_GUIDE.md  (day-by-day walkthrough)"
