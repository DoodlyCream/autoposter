#!/bin/bash
# ─────────────────────────────────────────────
# Build & Chill Auto Poster — Start Script
# Run this from your AutoPoster folder
# ─────────────────────────────────────────────

cd "$(dirname "$0")"

echo ""
echo "  ⚡ Build & Chill Auto Poster"
echo "  ─────────────────────────────"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "  → Setting up virtual environment..."
  python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install deps
echo "  → Installing dependencies..."
pip install -q -r requirements.txt

# Make sure folders exist
mkdir -p queue posted failed db static

echo "  → Starting ngrok tunnel..."
pkill -f "ngrok http" 2>/dev/null
ngrok http --domain=sirupy-evolutionally-oneida.ngrok-free.dev 8888 > /dev/null 2>&1 &
echo "  → ngrok running at: https://sirupy-evolutionally-oneida.ngrok-free.dev"

echo "  → Starting server..."
echo "  → Open your browser at: http://localhost:8888"
echo ""

# Open browser after 2 second delay
(sleep 2 && open http://localhost:8888) &

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8888 --reload
