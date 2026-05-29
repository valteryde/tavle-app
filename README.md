# Tavle App

Desktop wrapper for [Tavle](https://github.com/Den-Frie-Digitale-Skole/tavle) whiteboards. Organize boards into groups, add local notes and tags, and open boards in an embedded Tavle view.

Built with **Tauri 2**, **React**, and **TypeScript**. Tavle is **lazy-loaded** from GitHub on first run (not vendored in this repository).

## Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Rust](https://www.rust-lang.org/tools/install) (for Tauri)
- [Tauri prerequisites](https://tauri.app/start/prerequisites/) for your OS
- Python **3.11 or 3.12** (installed automatically via pip on first Tavle download; 3.13 breaks eventlet)

## Setup

```bash
npm install
```

No `vendor/tavle` clone is required. The app downloads Tavle into app data on first launch.

**Optional — local Tavle checkout for development:**

```bash
git clone https://github.com/Den-Frie-Digitale-Skole/tavle.git vendor/tavle
# or: export TAVLE_SOURCE_DIR=/path/to/tavle
```

If `vendor/tavle` or `TAVLE_SOURCE_DIR` exists, the app uses that instead of downloading.

## Development

```bash
npm run tauri:dev
```

First launch downloads `Den-Frie-Digitale-Skole/tavle@main` from GitHub, applies desktop patches, and runs `pip install` for Python deps.

### Data locations

| Data | Path (macOS example) |
|------|----------------------|
| Wrapper metadata | `~/Library/Application Support/com.valteryde.tavle-app/metadata.db` |
| Tavle source (lazy) | `…/tavle-source/` |
| Tavle SQLite + logs | `…/tavle/` |
| Admin token | OS keychain |

## Features

- **Lazy Tavle** — GitHub zipball on first run; re-download from Settings
- **Groups** — folder-like organization (local metadata only)
- **Board sync** — `GET /api/boards` with admin token
- **Embed** — boards open with `?embed=1`

## Production build

```bash
npm run tauri:build
```

Installers contain only the wrapper (~small). End users need network on first launch to download Tavle, plus Python 3.11/3.12.

Optional PyInstaller sidecar: `npm run build:sidecar` (requires a local `vendor/tavle` or downloaded source).

## GitHub Actions

| Workflow | Trigger | Output |
|----------|---------|--------|
| [CI](.github/workflows/ci.yml) | Push/PR to `master` | Installers per platform |
| [Release](.github/workflows/release.yml) | Tag `app-v*` | Draft GitHub Release |

```bash
git tag app-v0.1.0
git push origin app-v0.1.0
```

## Tavle source configuration

Stored in wrapper settings (defaults):

| Setting | Default |
|---------|---------|
| `tavle_repo` | `Den-Frie-Digitale-Skole/tavle` |
| `tavle_ref` | `main` |

Change via Settings → Re-download, or `set_setting` / future UI.

## Environment (set by the app)

| Variable | Purpose |
|----------|---------|
| `WHITEBOARD_DATA_DIR` | Tavle SQLite + logs (patched at runtime) |
| `TAVLE_EMBED_FRAME_ANCESTORS` | iframe from shell UI |
| `TAVLE_HOST` | `127.0.0.1` |
| `PORT` | Tavle HTTP port |
| `TAVLE_SOURCE_DIR` | Dev override for local Tavle path |

## License

Wrapper: project default. Tavle: see upstream repository.
