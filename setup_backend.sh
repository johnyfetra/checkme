#!/usr/bin/env bash
# setup_backend.sh — Install Python dependencies for CheckMe backend
# Run once before starting the server.

set -e

cd "$(dirname "$0")/backend"

echo "=== CheckMe Backend Setup ==="

# Create virtual environment if not already present
if [ ! -d ".venv" ]; then
  echo "→ Creating virtual environment…"
  python3 -m venv .venv
fi

source .venv/bin/activate

echo "→ Upgrading pip…"
pip install --upgrade pip -q

echo "→ Installing dependencies…"
pip install -r requirements.txt

echo ""
echo "✓ Setup complete."
echo "  To start the backend:"
echo "    cd backend && source .venv/bin/activate && python main.py"
