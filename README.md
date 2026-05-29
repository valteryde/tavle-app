# Tavle App

Desktop wrapper for [Tavle](https://github.com/Den-Frie-Digitale-Skole/tavle) whiteboards. Organize boards into groups, add local notes and tags, and open boards in an embedded Tavle view.

Built with **Tauri 2**, **React**, and **TypeScript**. Tavle runs as a local Python server (development) or optional PyInstaller sidecar (production).

## Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Rust](https://www.rust-lang.org/tools/install) (for Tauri)
- [Tauri prerequisites](https://tauri.app/start/prerequisites/) for your OS
- Python **3.11 or 3.12** with pip (3.13 may fail with eventlet; the app tries 3.12/3.11 first)

## Setup

```bash
# Install frontend dependencies
npm install

# Install Tavle Python dependencies
npm run setup:tavle
```

Tavle source lives in `vendor/tavle` (copied from upstream or git submodule).

## Development

```bash
npm run tauri:dev
```

This starts:

1. Vite on `http://localhost:1420` (shell UI)
2. Tavle on `http://127.0.0.1:5050` (spawned automatically)

On first launch, complete the Tavle setup wizard in the app, then click **I've completed setup** to import the admin API token into the system keychain.

### Data locations

| Data | Path |
|------|------|
| Wrapper metadata | `~/Library/Application Support/com.vdaugb.tavle-app/metadata.db` (macOS) |
| Tavle SQLite | `…/tavle/whiteboard.db` |
| Admin token | OS keychain (`tavle-app` / `admin_api_token`) |

## Features

- **Groups** — folder-like organization (local metadata only)
- **Board sync** — `GET /api/boards` imports Tavle boards into the library
- **Embed** — boards open with `?embed=1` in an iframe
- **Pins, notes, tags** — stored in wrapper SQLite

## Production build

```bash
# Optional: bundle Tavle as a sidecar (see scripts/build-tavle-sidecar.sh)
npm run build:sidecar

npm run tauri:build
```

## GitHub Actions

| Workflow | Trigger | Output |
|----------|---------|--------|
| [CI](.github/workflows/ci.yml) | Push/PR to `master` | Build artifacts per platform (download from Actions run) |
| [Release](.github/workflows/release.yml) | Tag `app-v*` (e.g. `app-v0.1.0`) or manual dispatch | Draft GitHub Release with installers |

**Create a release:**

```bash
git tag app-v0.1.0
git push origin app-v0.1.0
```

Enable **Workflow permissions → Read and write** in the repo settings so releases can be published.

**Note:** CI builds the Tauri shell and bundles `vendor/tavle` into the app. End users still need Python 3.11/3.12 (or a built PyInstaller sidecar) to run the whiteboard server.

If no sidecar is present, the app falls back to `python3 server.py` from `vendor/tavle`.

### PyInstaller notes

SocketIO/eventlet bundling can be fragile. If the sidecar fails, use system Python + `npm run setup:tavle` or ship an embedded venv in app Resources.

## Environment (set automatically by the app)

| Variable | Purpose |
|----------|---------|
| `WHITEBOARD_DATA_DIR` | Tavle SQLite + logs directory |
| `TAVLE_EMBED_FRAME_ANCESTORS` | Allows iframe from the shell UI |
| `TAVLE_HOST` | `127.0.0.1` (desktop only) |
| `PORT` | Tavle HTTP port (default 5050) |
| `ADMIN_API_TOKEN` | Passed when stored in keychain |

## License

Wrapper: project default. Tavle: see upstream repository.
