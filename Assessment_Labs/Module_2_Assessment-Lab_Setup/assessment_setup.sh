#!/usr/bin/env bash
# Starts the Palanca lab with the Module 2 assessment overlay.
# Run from the palanca-lab directory (next to docker-compose.yml).
set -euo pipefail
cd "$(dirname "$0")"
[ -f docker-compose.yml ] || { echo "docker-compose.yml not found here. Copy this kit into the palanca-lab folder first."; exit 1; }
echo "--> Building and starting the lab with the assessment overlay..."
docker compose -f docker-compose.yml -f docker-compose.assessment.yml up -d --build
echo "--> Waiting for devices and the switch table to settle (45s)..."
sleep 45
./assessment_verify.sh
