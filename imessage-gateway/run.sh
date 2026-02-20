#!/bin/bash
# iMessage Gateway runner
# Usage: DEFAULT_RECIPIENT="+441234567890" ./run.sh

cd "$(dirname "$0")"

# Check dependencies
python3 -c "import aiohttp" 2>/dev/null || pip3 install -r requirements.txt

echo "Starting iMessage Gateway..."
echo "Default recipient: ${DEFAULT_RECIPIENT:-not set}"
echo "Port: ${IMESSAGE_GATEWAY_PORT:-8095}"

python3 server.py
