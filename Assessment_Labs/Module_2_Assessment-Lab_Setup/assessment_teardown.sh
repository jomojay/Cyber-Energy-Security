#!/usr/bin/env bash
# Removes the assessment overlay and restores the normal practice lab.
set -euo pipefail
cd "$(dirname "$0")"
docker compose -f docker-compose.yml -f docker-compose.assessment.yml rm -sf rogue-dev switch-primer
docker compose -f docker-compose.yml up -d plc-aux-01   # recreated with its normal vendor string
echo "Assessment overlay removed. The practice lab is back to normal."
