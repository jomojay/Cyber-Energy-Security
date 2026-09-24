#!/usr/bin/env bash
# Stops and removes the Module 3 Day 4 firewall lab (containers, networks).
# Add -v to also wipe any volumes: ./teardown.sh -v
set -euo pipefail
if [ "${1:-}" == "-v" ]; then
  docker compose down -v
else
  docker compose down
fi
echo "Palanca Module 3 Day 4 firewall lab stopped."
