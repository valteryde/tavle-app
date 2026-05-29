#!/usr/bin/env bash
# Build Tavle as a PyInstaller sidecar for Tauri production bundles.
# Requires: pip install pyinstaller, and Tavle deps in vendor/tavle.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAVLE_DIR="$ROOT/vendor/tavle"
OUT_DIR="$ROOT/src-tauri/binaries"

if [[ ! -f "$TAVLE_DIR/server.py" ]]; then
  echo "vendor/tavle missing. Copy or submodule Tavle first." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
cd "$TAVLE_DIR"

pip install -r requirements.txt pyinstaller

pyinstaller \
  --name tavle-server \
  --onefile \
  --hidden-import engineio.async_drivers.eventlet \
  --hidden-import eventlet \
  --collect-all flask_socketio \
  --collect-all engineio \
  --collect-all socketio \
  server.py

cp -f dist/tavle-server "$OUT_DIR/tavle-server"
chmod +x "$OUT_DIR/tavle-server"

echo "Sidecar written to $OUT_DIR/tavle-server"
echo "Register in tauri.conf.json bundle externalBin if needed for your target triple."
