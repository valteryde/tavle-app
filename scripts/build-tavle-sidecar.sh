#!/usr/bin/env bash
# Build Tavle as a PyInstaller sidecar. Requires Tavle source on disk.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -n "${TAVLE_SOURCE_DIR:-}" && -f "${TAVLE_SOURCE_DIR}/server.py" ]]; then
  TAVLE_DIR="$TAVLE_SOURCE_DIR"
elif [[ -f "$ROOT/vendor/tavle/server.py" ]]; then
  TAVLE_DIR="$ROOT/vendor/tavle"
else
  echo "No Tavle source found. Set TAVLE_SOURCE_DIR or run the app once to download into app data." >&2
  echo "Or: npm run setup:tavle" >&2
  exit 1
fi

OUT_DIR="$ROOT/src-tauri/binaries"
mkdir -p "$OUT_DIR"
cd "$TAVLE_DIR"

pip install -r requirements.txt pyinstaller 2>/dev/null || \
  pip install Flask Flask-SocketIO Flask-RESTful Flask-Limiter peewee eventlet python-socketio requests Pillow pyinstaller

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
