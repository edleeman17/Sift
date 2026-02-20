#!/bin/bash
# SMS Assistant runner
# Usage: DUMBPHONE_NUMBER="+441234567890" ./run.sh

cd "$(dirname "$0")"

# Check dependencies
python3 -c "import httpx" 2>/dev/null || pip3 install -r requirements.txt

# Check Ollama
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Error: Ollama not accessible at http://localhost:11434"
    echo "Make sure docker compose is running with ollama port exposed"
    exit 1
fi

# Check required env var
if [ -z "$DUMBPHONE_NUMBER" ]; then
    echo "Error: DUMBPHONE_NUMBER environment variable not set"
    echo "Usage: DUMBPHONE_NUMBER='+441234567890' ./run.sh"
    exit 1
fi

echo "Starting SMS Assistant..."
echo "Dumbphone: $DUMBPHONE_NUMBER"
echo "Press Ctrl+C to stop"

python3 assistant.py
