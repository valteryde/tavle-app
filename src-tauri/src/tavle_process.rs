use crate::secrets;
use crate::state::{AppPaths, TavleProcessState};
use crate::tavle_fetch;
use std::fs;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use tauri::Manager;

const DEFAULT_PORT: u16 = 5050;
const HEALTH_TIMEOUT_SECS: u64 = 60;

pub fn resolve_base_paths(app: &tauri::AppHandle) -> Result<AppPaths, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|e| e.to_string())?;

    let tavle_data_dir = app_data_dir.join("tavle");
    fs::create_dir_all(&tavle_data_dir).map_err(|e| e.to_string())?;

    let metadata_db = app_data_dir.join("metadata.db");

    Ok(AppPaths {
        app_data_dir,
        tavle_data_dir,
        metadata_db,
        tavle_source_dir: PathBuf::new(),
    })
}

/// Resolves paths and ensures Tavle source is downloaded (or uses a local override).
pub fn resolve_paths(app: &tauri::AppHandle) -> Result<AppPaths, String> {
    let mut paths = resolve_base_paths(app)?;
    paths.tavle_source_dir = if let Some(local) = tavle_fetch::resolve_local_override() {
        local
    } else {
        tavle_fetch::ensure_tavle_source(&paths)?
    };
    Ok(paths)
}

fn resolve_sidecar(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    let name = if cfg!(target_os = "windows") {
        "tavle-server.exe"
    } else {
        "tavle-server"
    };
    app.path()
        .resource_dir()
        .ok()
        .map(|r| r.join("binaries").join(name))
        .filter(|p| p.exists())
}

fn pick_port(preferred: u16) -> u16 {
    if TcpListener::bind(("127.0.0.1", preferred)).is_ok() {
        return preferred;
    }
    TcpListener::bind("127.0.0.1:0")
        .ok()
        .and_then(|l| l.local_addr().ok().map(|a| a.port()))
        .unwrap_or(preferred)
}

fn embed_ancestors() -> String {
    // Parent webview origins (Tauri dev + production) must be listed for board iframes.
    [
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ]
    .join(",")
}

pub fn build_env(paths: &AppPaths, port: u16) -> Vec<(String, String)> {
    let mut env = vec![
        ("FLASK_ENV".into(), "development".into()),
        ("TAVLE_HOST".into(), "127.0.0.1".into()),
        ("PORT".into(), port.to_string()),
        (
            "WHITEBOARD_DATA_DIR".into(),
            paths.tavle_data_dir.to_string_lossy().into_owned(),
        ),
        ("LOG_DIR".into(), paths.tavle_data_dir.join("logs").to_string_lossy().into_owned()),
        (
            "TAVLE_EMBED_FRAME_ANCESTORS".into(),
            embed_ancestors(),
        ),
    ];

    if let Ok(Some(token)) = secrets::get_admin_token() {
        env.push(("ADMIN_API_TOKEN".into(), token));
    }

    env
}

pub fn start_tavle(
    app: &tauri::AppHandle,
    state: &TavleProcessState,
) -> Result<serde_json::Value, String> {
    let mut child_guard = state.child.lock().map_err(|e| e.to_string())?;
    if child_guard.is_some() {
        let port = *state.port.lock().map_err(|e| e.to_string())?;
        let base = state.base_url.lock().map_err(|e| e.to_string())?.clone();
        return Ok(serde_json::json!({
            "running": true,
            "port": port,
            "base_url": base,
        }));
    }

    let paths = resolve_paths(app)?;
    fs::create_dir_all(&paths.tavle_data_dir.join("logs")).map_err(|e| e.to_string())?;

    let port = pick_port(DEFAULT_PORT);
    let base_url = format!("http://127.0.0.1:{port}");
    let env_pairs = build_env(&paths, port);

    let child = if let Some(sidecar) = resolve_sidecar(app) {
        let mut cmd = Command::new(&sidecar);
        for (k, v) in &env_pairs {
            cmd.env(k, v);
        }
        cmd.current_dir(&paths.tavle_source_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("Failed to start Tavle sidecar: {e}"))?
    } else {
        let python = which_python();
        let mut cmd = Command::new(&python);
        cmd.arg("server.py")
            .current_dir(&paths.tavle_source_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        for (k, v) in &env_pairs {
            cmd.env(k, v);
        }
        cmd.spawn()
            .map_err(|e| format!("Failed to start Tavle ({python}): {e}"))?
    };

    *child_guard = Some(child);
    *state.port.lock().map_err(|e| e.to_string())? = port;
    *state.base_url.lock().map_err(|e| e.to_string())? = base_url.clone();

    wait_for_health(&base_url)?;

    Ok(serde_json::json!({
        "running": true,
        "port": port,
        "base_url": base_url,
    }))
}

fn which_python() -> String {
    for candidate in ["python3.12", "python3.11", "python3", "python"] {
        if Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
        {
            return candidate.into();
        }
    }
    "python3".into()
}

fn wait_for_health(base_url: &str) -> Result<(), String> {
    let health_url = format!("{base_url}/health");
    let started = Instant::now();
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;

    while started.elapsed() < Duration::from_secs(HEALTH_TIMEOUT_SECS) {
        if let Ok(resp) = client.get(&health_url).send() {
            if resp.status().is_success() {
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(400));
    }

    Err(format!(
        "Tavle did not become healthy within {HEALTH_TIMEOUT_SECS}s ({health_url})"
    ))
}

pub fn stop_tavle(state: &TavleProcessState) -> Result<(), String> {
    let mut child_guard = state.child.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}

pub fn tavle_status(state: &TavleProcessState) -> serde_json::Value {
    let running = state
        .child
        .lock()
        .map(|g| g.is_some())
        .unwrap_or(false);
    let port = state.port.lock().map(|p| *p).unwrap_or(DEFAULT_PORT);
    let base_url = state
        .base_url
        .lock()
        .map(|u| u.clone())
        .unwrap_or_else(|_| format!("http://127.0.0.1:{port}"));

    serde_json::json!({
        "running": running,
        "port": port,
        "base_url": base_url,
    })
}

pub fn tavle_needs_setup(paths: &AppPaths) -> Result<bool, String> {
    if secrets::get_admin_token()?.is_some() {
        return Ok(false);
    }

    let db_path = paths.tavle_data_dir.join("whiteboard.db");
    if !db_path.exists() {
        return Ok(true);
    }

    let conn = rusqlite::Connection::open(&db_path).map_err(|e| e.to_string())?;
    let setup_complete: Option<String> = conn
        .query_row(
            "SELECT value FROM settings WHERE key = 'setup_complete'",
            [],
            |row| row.get(0),
        )
        .ok();

    Ok(setup_complete.as_deref() != Some("true"))
}

pub fn import_admin_token_from_tavle(paths: &AppPaths) -> Result<Option<String>, String> {
    let db_path = paths.tavle_data_dir.join("whiteboard.db");
    if !db_path.exists() {
        return Ok(None);
    }

    let conn = rusqlite::Connection::open(&db_path).map_err(|e| e.to_string())?;
    let token: Option<String> = conn
        .query_row(
            "SELECT value FROM settings WHERE key = 'admin_api_token'",
            [],
            |row| row.get(0),
        )
        .ok();

    if let Some(ref t) = token {
        if !t.is_empty() {
            secrets::set_admin_token(t)?;
        }
    }

    Ok(token)
}
