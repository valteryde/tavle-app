mod metadata;
mod secrets;
mod state;
mod tavle_fetch;
mod tavle_process;

use state::TavleProcessState;
use std::sync::Mutex;
use tauri::Manager;

#[tauri::command]
fn start_tavle(app: tauri::AppHandle, state: tauri::State<'_, TavleProcessState>) -> Result<serde_json::Value, String> {
    tavle_process::start_tavle(&app, &state)
}

#[tauri::command]
fn stop_tavle(state: tauri::State<'_, TavleProcessState>) -> Result<(), String> {
    tavle_process::stop_tavle(&state)
}

#[tauri::command]
fn tavle_status(state: tauri::State<'_, TavleProcessState>) -> serde_json::Value {
    tavle_process::tavle_status(&state)
}

#[tauri::command]
fn tavle_needs_setup(app: tauri::AppHandle) -> Result<bool, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    tavle_process::tavle_needs_setup(&paths)
}

#[tauri::command]
fn import_admin_token_from_tavle(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    tavle_process::import_admin_token_from_tavle(&paths)
}

#[tauri::command]
fn get_admin_token() -> Result<Option<String>, String> {
    secrets::get_admin_token()
}

#[tauri::command]
fn set_admin_token(token: String) -> Result<(), String> {
    secrets::set_admin_token(&token)
}

#[tauri::command]
fn clear_admin_token() -> Result<(), String> {
    secrets::clear_admin_token()
}

#[tauri::command]
fn list_groups(app: tauri::AppHandle) -> Result<Vec<metadata::Group>, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::list_groups(&paths)
}

#[tauri::command]
fn create_group(
    app: tauri::AppHandle,
    name: String,
    parent_id: Option<String>,
) -> Result<metadata::Group, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::create_group(&paths, name, parent_id)
}

#[tauri::command]
fn rename_group(app: tauri::AppHandle, id: String, name: String) -> Result<(), String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::rename_group(&paths, id, name)
}

#[tauri::command]
fn delete_group(app: tauri::AppHandle, id: String) -> Result<(), String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::delete_group(&paths, id)
}

#[tauri::command]
fn list_board_links(app: tauri::AppHandle) -> Result<Vec<metadata::BoardLink>, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::list_board_links(&paths)
}

#[tauri::command]
fn move_board(
    app: tauri::AppHandle,
    board_link_id: String,
    group_id: Option<String>,
) -> Result<(), String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::move_board(&paths, board_link_id, group_id)
}

#[tauri::command]
fn update_board_meta(
    app: tauri::AppHandle,
    board_link_id: String,
    display_name: Option<String>,
    notes: Option<String>,
    tags: Option<String>,
    pinned: Option<bool>,
) -> Result<metadata::BoardLink, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::update_board_meta(
        &paths,
        board_link_id,
        display_name,
        notes,
        tags,
        pinned,
    )
}

#[tauri::command]
fn touch_board_opened(app: tauri::AppHandle, board_link_id: String) -> Result<(), String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::touch_board_opened(&paths, board_link_id)
}

#[tauri::command]
fn sync_boards_from_api(
    app: tauri::AppHandle,
    state: tauri::State<'_, TavleProcessState>,
) -> Result<serde_json::Value, String> {
    let paths = tavle_process::resolve_paths(&app)?;
    let token = secrets::get_admin_token()?.ok_or("Admin token not configured")?;
    let base = state.base_url.lock().map_err(|e| e.to_string())?.clone();
    if base.is_empty() {
        return Err("Tavle is not running".into());
    }
    metadata::sync_boards_from_api(&paths, &base, &token)
}

#[tauri::command]
fn create_board(
    app: tauri::AppHandle,
    state: tauri::State<'_, TavleProcessState>,
    name: String,
) -> Result<metadata::BoardLink, String> {
    let paths = tavle_process::resolve_paths(&app)?;
    let token = secrets::get_admin_token()?.ok_or("Admin token not configured")?;
    let base = state.base_url.lock().map_err(|e| e.to_string())?.clone();
    metadata::create_board_via_api(&paths, &base, &token, name)
}

#[tauri::command]
fn delete_board(
    app: tauri::AppHandle,
    state: tauri::State<'_, TavleProcessState>,
    tavle_board_id: String,
    board_link_id: String,
) -> Result<(), String> {
    let paths = tavle_process::resolve_paths(&app)?;
    let token = secrets::get_admin_token()?.ok_or("Admin token not configured")?;
    let base = state.base_url.lock().map_err(|e| e.to_string())?.clone();
    metadata::delete_board_via_api(&paths, &base, &token, tavle_board_id, board_link_id)
}

#[tauri::command]
fn get_setting(app: tauri::AppHandle, key: String) -> Result<Option<String>, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::get_setting(&paths, key)
}

#[tauri::command]
fn set_setting(app: tauri::AppHandle, key: String, value: String) -> Result<(), String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    metadata::set_setting(&paths, key, value)
}

#[tauri::command]
fn tavle_source_status(app: tauri::AppHandle) -> Result<tavle_fetch::TavleSourceInfo, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    tavle_fetch::source_info(&paths)
}

#[tauri::command]
fn fetch_tavle_source(
    app: tauri::AppHandle,
    repo: Option<String>,
    git_ref: Option<String>,
    force: Option<bool>,
) -> Result<tavle_fetch::TavleSourceInfo, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    let repo = repo.unwrap_or_else(|| tavle_fetch::DEFAULT_TAVLE_REPO.to_string());
    let git_ref = git_ref.unwrap_or_else(|| tavle_fetch::DEFAULT_TAVLE_REF.to_string());
    tavle_fetch::fetch_tavle_source(&paths, &repo, &git_ref, force.unwrap_or(false))
}

#[tauri::command]
fn get_app_paths(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let paths = tavle_process::resolve_base_paths(&app)?;
    let source = tavle_fetch::source_info(&paths)?;
    Ok(serde_json::json!({
        "app_data_dir": paths.app_data_dir,
        "tavle_data_dir": paths.tavle_data_dir,
        "metadata_db": paths.metadata_db,
        "tavle_source": source,
    }))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(TavleProcessState {
            child: Mutex::new(None),
            port: Mutex::new(5050),
            base_url: Mutex::new(String::new()),
        })
        .invoke_handler(tauri::generate_handler![
            start_tavle,
            stop_tavle,
            tavle_status,
            tavle_needs_setup,
            import_admin_token_from_tavle,
            get_admin_token,
            set_admin_token,
            clear_admin_token,
            list_groups,
            create_group,
            rename_group,
            delete_group,
            list_board_links,
            move_board,
            update_board_meta,
            touch_board_opened,
            sync_boards_from_api,
            create_board,
            delete_board,
            get_setting,
            set_setting,
            get_app_paths,
            tavle_source_status,
            fetch_tavle_source,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.app_handle().try_state::<TavleProcessState>() {
                    let _ = tavle_process::stop_tavle(&state);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
