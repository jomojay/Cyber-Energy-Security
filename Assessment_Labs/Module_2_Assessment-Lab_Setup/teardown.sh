#!/usr/bin/env bash
# Stops and removes the Palanca lab environment (containers, networks).
# Add -v to also wipe any volumes: ./teardown.sh -v
set -euo pipefail
if [ "${1:-}" == "-v" ]; then
  docker compose down -v
else
  docker compose down
fi
echo "Palanca lab environment stopped."
