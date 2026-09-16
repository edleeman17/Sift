#!/bin/bash
# SMTP Gateway runner
# Usage: cp .env.example .env, fill it in, then ./run.sh

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "Starting SMTP Gateway..."
echo "Sending as: ${SMTP_USERNAME:-not set}"
echo "Delivering to: ${TO_ADDRESS:-not set}"
echo "Port: ${PORT:-8095}"

python3 server.py
