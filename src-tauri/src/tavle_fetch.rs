use crate::metadata;
use crate::state::AppPaths;
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{copy, Cursor};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use zip::ZipArchive;

pub const DEFAULT_TAVLE_REPO: &str = "Den-Frie-Digitale-Skole/tavle";
pub const DEFAULT_TAVLE_REF: &str = "main";

#[derive(Debug, Serialize, Deserialize)]
pub struct TavleSourceInfo {
    pub repo: String,
    pub git_ref: String,
    pub path: String,
    pub installed: bool,
    pub fetched_at: Option<String>,
}

pub fn tavle_source_dir(app_data: &Path) -> PathBuf {
    app_data.join("tavle-source")
}

pub fn source_info(paths: &AppPaths) -> Result<TavleSourceInfo, String> {
    let dir = tavle_source_dir(&paths.app_data_dir);
    let repo = metadata::get_setting(paths, "tavle_repo".to_string())?
        .unwrap_or_else(|| DEFAULT_TAVLE_REPO.to_string());
    let git_ref = metadata::get_setting(paths, "tavle_ref".to_string())?
        .unwrap_or_else(|| DEFAULT_TAVLE_REF.to_string());
    let installed = dir.join("server.py").exists();
    let fetched_at = read_manifest(&dir).ok().map(|m| m.fetched_at);

    Ok(TavleSourceInfo {
        repo,
        git_ref,
        path: dir.to_string_lossy().into_owned(),
        installed,
        fetched_at,
    })
}

#[derive(Debug, Serialize, Deserialize)]
struct SourceManifest {
    repo: String,
    git_ref: String,
    fetched_at: String,
}

fn read_manifest(dir: &Path) -> Result<SourceManifest, String> {
    let raw = fs::read_to_string(dir.join(".tavle-app-manifest.json")).map_err(|e| e.to_string())?;
    serde_json::from_str(&raw).map_err(|e| e.to_string())
}

fn write_manifest(dir: &Path, repo: &str, git_ref: &str) -> Result<(), String> {
    let manifest = SourceManifest {
        repo: repo.to_string(),
        git_ref: git_ref.to_string(),
        fetched_at: chrono::Utc::now().to_rfc3339(),
    };
    let raw = serde_json::to_string_pretty(&manifest).map_err(|e| e.to_string())?;
    fs::write(dir.join(".tavle-app-manifest.json"), raw).map_err(|e| e.to_string())
}

/// Ensure Tavle source exists under app data; download from GitHub on first run.
pub fn ensure_tavle_source(paths: &AppPaths) -> Result<PathBuf, String> {
    let dest = tavle_source_dir(&paths.app_data_dir);
    if dest.join("server.py").exists() {
        apply_desktop_patches(&dest)?;
        return Ok(dest);
    }

    let repo = metadata::get_setting(paths, "tavle_repo".to_string())?
        .unwrap_or_else(|| DEFAULT_TAVLE_REPO.to_string());
    let git_ref = metadata::get_setting(paths, "tavle_ref".to_string())?
        .unwrap_or_else(|| DEFAULT_TAVLE_REF.to_string());

    fetch_tavle_source(paths, &repo, &git_ref, false)?;
    Ok(dest)
}

pub fn fetch_tavle_source(
    paths: &AppPaths,
    repo: &str,
    git_ref: &str,
    force: bool,
) -> Result<TavleSourceInfo, String> {
    let dest = tavle_source_dir(&paths.app_data_dir);
    if force && dest.exists() {
        fs::remove_dir_all(&dest).map_err(|e| e.to_string())?;
    }

    fs::create_dir_all(&paths.app_data_dir).map_err(|e| e.to_string())?;

    if dest.join("server.py").exists() && !force {
        apply_desktop_patches(&dest)?;
        return source_info(paths);
    }

    let url = format!(
        "https://github.com/{repo}/archive/refs/heads/{git_ref}.zip"
    );
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| e.to_string())?;

    let response = client
        .get(&url)
        .send()
        .map_err(|e| format!("Failed to download Tavle from GitHub: {e}"))?;

    if !response.status().is_success() {
        return Err(format!(
            "GitHub returned {} for {url}. Check repo/ref in Settings.",
            response.status()
        ));
    }

    let bytes = response.bytes().map_err(|e| e.to_string())?;
    let staging = paths.app_data_dir.join("tavle-source-staging");
    if staging.exists() {
        fs::remove_dir_all(&staging).map_err(|e| e.to_string())?;
    }
    fs::create_dir_all(&staging).map_err(|e| e.to_string())?;

    extract_zip_to_dir(&bytes, &staging)?;

    let extracted_root = find_server_root(&staging)
        .ok_or_else(|| "Downloaded archive did not contain server.py".to_string())?;

    if dest.exists() {
        fs::remove_dir_all(&dest).map_err(|e| e.to_string())?;
    }
    copy_dir_recursive(&extracted_root, &dest)?;
    fs::remove_dir_all(&staging).ok();

    apply_desktop_patches(&dest)?;
    write_manifest(&dest, repo, git_ref)?;
    metadata::set_setting(paths, "tavle_repo".to_string(), repo.to_string())?;
    metadata::set_setting(paths, "tavle_ref".to_string(), git_ref.to_string())?;

    install_python_deps(&dest)?;

    source_info(paths)
}

fn extract_zip_to_dir(bytes: &[u8], dest: &Path) -> Result<(), String> {
    let reader = Cursor::new(bytes);
    let mut archive = ZipArchive::new(reader).map_err(|e| e.to_string())?;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| e.to_string())?;
        let name = file.name().to_string();
        let outpath = dest.join(name);
        if file.name().ends_with('/') {
            fs::create_dir_all(&outpath).map_err(|e| e.to_string())?;
            continue;
        }
        if let Some(parent) = outpath.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut outfile = File::create(&outpath).map_err(|e| e.to_string())?;
        copy(&mut file, &mut outfile).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn find_server_root(dir: &Path) -> Option<PathBuf> {
    if dir.join("server.py").exists() {
        return Some(dir.to_path_buf());
    }
    let entries = fs::read_dir(dir).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if let Some(found) = find_server_root(&path) {
                return Some(found);
            }
        }
    }
    None
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| e.to_string())?;
    for entry in fs::read_dir(src).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let ty = entry.file_type().map_err(|e| e.to_string())?;
        let from = entry.path();
        let to = dst.join(entry.file_name());
        if ty.is_dir() {
            copy_dir_recursive(&from, &to)?;
        } else {
            fs::copy(&from, &to).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// Patches upstream Tavle for desktop embedding (no fork required).
pub fn apply_desktop_patches(tavle_dir: &Path) -> Result<(), String> {
    patch_models_py(&tavle_dir.join("models.py"))?;
    patch_server_py(&tavle_dir.join("server.py"))?;
    Ok(())
}

fn patch_models_py(path: &Path) -> Result<(), String> {
    let mut content = fs::read_to_string(path).map_err(|e| e.to_string())?;
    if content.contains("WHITEBOARD_DATA_DIR") {
        return Ok(());
    }
    let needle = "    db = SqliteDatabase('whiteboard.db', pragmas={";
    let replacement = "    _data_dir = os.environ.get('WHITEBOARD_DATA_DIR', '').strip()\n\
    if _data_dir:\n\
        os.makedirs(_data_dir, exist_ok=True)\n\
        _db_path = os.path.join(_data_dir, 'whiteboard.db')\n\
    else:\n\
        _db_path = 'whiteboard.db'\n\
    db = SqliteDatabase(_db_path, pragmas={";
    if !content.contains(needle) {
        return Err("Could not patch models.py: unexpected upstream layout".into());
    }
    content = content.replacen(needle, replacement, 1);
    fs::write(path, content).map_err(|e| e.to_string())?;
    Ok(())
}

fn patch_server_py(path: &Path) -> Result<(), String> {
    let mut content = fs::read_to_string(path).map_err(|e| e.to_string())?;
    if content.contains("TAVLE_HOST") {
        return Ok(());
    }
    let old_block = r#"if __name__ == '__main__':
    
    # Log startup
    logger.info('Starting whiteboard server on http://localhost:5050')
    logger.info(f'CORS allowed origins: {ALLOWED_ORIGINS}')
    
    # Run with SocketIO
    socketio.run(app, host='0.0.0.0', port=5050, debug=True)"#;
    let new_block = r#"if __name__ == '__main__':
    _host = os.environ.get('TAVLE_HOST', '127.0.0.1').strip() or '127.0.0.1'
    _port = int(os.environ.get('PORT', '5050'))
    _debug = os.environ.get('FLASK_ENV', 'development') == 'development'

    logger.info('Starting whiteboard server on http://%s:%s', _host, _port)
    logger.info(f'CORS allowed origins: {ALLOWED_ORIGINS}')

    socketio.run(app, host=_host, port=_port, debug=_debug)"#;
    if content.contains(old_block) {
        content = content.replace(old_block, new_block);
    } else if content.contains("socketio.run(app, host='0.0.0.0', port=5050") {
        // Minimal fallback if whitespace differs
        content = content.replace(
            "socketio.run(app, host='0.0.0.0', port=5050, debug=True)",
            "_host = os.environ.get('TAVLE_HOST', '127.0.0.1').strip() or '127.0.0.1'\n    _port = int(os.environ.get('PORT', '5050'))\n    _debug = os.environ.get('FLASK_ENV', 'development') == 'development'\n    socketio.run(app, host=_host, port=_port, debug=_debug)",
        );
    } else {
        return Err("Could not patch server.py: unexpected upstream layout".into());
    }
    fs::write(path, content).map_err(|e| e.to_string())?;
    Ok(())
}

fn install_python_deps(tavle_dir: &Path) -> Result<(), String> {
    let python = which_python();
    let req = tavle_dir.join("requirements.txt");
    if !req.exists() {
        return Ok(());
    }

    // Desktop uses SQLite only — install runtime deps without psycopg2/gunicorn.
    let deps = [
        "Flask==3.0.0",
        "Flask-SocketIO==5.3.6",
        "Flask-RESTful==0.3.10",
        "Flask-Limiter==3.5.0",
        "peewee==3.17.0",
        "eventlet==0.34.2",
        "python-socketio==5.10.0",
        "requests==2.31.0",
        "Pillow==10.4.0",
    ];

    let status = Command::new(&python)
        .args(["-m", "pip", "install", "-q"])
        .args(deps)
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .status()
        .map_err(|e| format!("Failed to run pip ({python}): {e}"))?;

    if !status.success() {
        return Err(format!(
            "pip install failed for {python}. Install Python 3.11 or 3.12 and try again."
        ));
    }
    Ok(())
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

/// Optional dev override: local clone at vendor/tavle or TAVLE_SOURCE_DIR.
pub fn resolve_local_override() -> Option<PathBuf> {
    if let Ok(dir) = std::env::var("TAVLE_SOURCE_DIR") {
        let path = PathBuf::from(dir);
        if path.join("server.py").exists() {
            return Some(path);
        }
    }
    let manifest = Path::new(env!("CARGO_MANIFEST_DIR"));
    let dev_vendor = manifest.join("../../vendor/tavle");
    if dev_vendor.join("server.py").exists() {
        return dev_vendor.canonicalize().ok();
    }
    None
}
