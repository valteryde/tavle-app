use crate::state::AppPaths;
use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::fs;
use uuid::Uuid;

const SCHEMA: &str = include_str!("../../schemas/metadata.sql");

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Group {
    pub id: String,
    pub name: String,
    pub parent_id: Option<String>,
    pub sort_order: i32,
    pub color: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct BoardLink {
    pub id: String,
    pub tavle_board_id: String,
    pub access_token: Option<String>,
    pub group_id: Option<String>,
    pub display_name: Option<String>,
    pub notes: Option<String>,
    pub tags: Option<String>,
    pub sort_order: i32,
    pub pinned: bool,
    pub last_opened_at: Option<String>,
}

fn open_db(paths: &AppPaths) -> Result<Connection, String> {
    if let Some(parent) = paths.metadata_db.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let conn = Connection::open(&paths.metadata_db).map_err(|e| e.to_string())?;
    conn.execute_batch(SCHEMA).map_err(|e| e.to_string())?;
    Ok(conn)
}

pub fn list_groups(paths: &AppPaths) -> Result<Vec<Group>, String> {
    let conn = open_db(paths)?;
    let mut stmt = conn
        .prepare(
            "SELECT id, name, parent_id, sort_order, color, created_at FROM groups ORDER BY sort_order, name",
        )
        .map_err(|e| e.to_string())?;

    let rows = stmt
        .query_map([], |row| {
            Ok(Group {
                id: row.get(0)?,
                name: row.get(1)?,
                parent_id: row.get(2)?,
                sort_order: row.get(3)?,
                color: row.get(4)?,
                created_at: row.get(5)?,
            })
        })
        .map_err(|e| e.to_string())?;

    rows.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

pub fn create_group(paths: &AppPaths, name: String, parent_id: Option<String>) -> Result<Group, String> {
    let conn = open_db(paths)?;
    let id = Uuid::new_v4().to_string();
    let created_at = Utc::now().to_rfc3339();
    let sort_order: i32 = conn
        .query_row(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM groups WHERE parent_id IS ?",
            params![parent_id],
            |row| row.get(0),
        )
        .unwrap_or(0);

    conn.execute(
        "INSERT INTO groups (id, name, parent_id, sort_order, color, created_at) VALUES (?1, ?2, ?3, ?4, NULL, ?5)",
        params![id, name, parent_id, sort_order, created_at],
    )
    .map_err(|e| e.to_string())?;

    Ok(Group {
        id,
        name,
        parent_id,
        sort_order,
        color: None,
        created_at,
    })
}

pub fn rename_group(paths: &AppPaths, id: String, name: String) -> Result<(), String> {
    let conn = open_db(paths)?;
    conn.execute("UPDATE groups SET name = ?2 WHERE id = ?1", params![id, name])
        .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn delete_group(paths: &AppPaths, id: String) -> Result<(), String> {
    let conn = open_db(paths)?;
    conn.execute(
        "UPDATE board_links SET group_id = NULL WHERE group_id = ?1",
        params![id],
    )
    .map_err(|e| e.to_string())?;
    conn.execute("DELETE FROM groups WHERE id = ?1", params![id])
        .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn list_board_links(paths: &AppPaths) -> Result<Vec<BoardLink>, String> {
    let conn = open_db(paths)?;
    let mut stmt = conn
        .prepare(
            "SELECT id, tavle_board_id, access_token, group_id, display_name, notes, tags, sort_order, pinned, last_opened_at
             FROM board_links
             ORDER BY pinned DESC, sort_order, display_name, tavle_board_id",
        )
        .map_err(|e| e.to_string())?;

    let rows = stmt
        .query_map([], |row| {
            Ok(BoardLink {
                id: row.get(0)?,
                tavle_board_id: row.get(1)?,
                access_token: row.get(2)?,
                group_id: row.get(3)?,
                display_name: row.get(4)?,
                notes: row.get(5)?,
                tags: row.get(6)?,
                sort_order: row.get(7)?,
                pinned: row.get::<_, i32>(8)? != 0,
                last_opened_at: row.get(9)?,
            })
        })
        .map_err(|e| e.to_string())?;

    rows.collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())
}

pub fn upsert_board_link(
    paths: &AppPaths,
    tavle_board_id: String,
    access_token: Option<String>,
    display_name: Option<String>,
) -> Result<BoardLink, String> {
    let conn = open_db(paths)?;
    let existing: Option<String> = conn
        .query_row(
            "SELECT id FROM board_links WHERE tavle_board_id = ?1",
            params![tavle_board_id],
            |row| row.get(0),
        )
        .ok();

    if let Some(id) = existing {
        conn.execute(
            "UPDATE board_links SET access_token = COALESCE(?2, access_token), display_name = COALESCE(?3, display_name) WHERE id = ?1",
            params![id, access_token, display_name],
        )
        .map_err(|e| e.to_string())?;
        return get_board_link_by_id(paths, id);
    }

    let id = Uuid::new_v4().to_string();
    conn.execute(
        "INSERT INTO board_links (id, tavle_board_id, access_token, group_id, display_name, notes, tags, sort_order, pinned, last_opened_at)
         VALUES (?1, ?2, ?3, NULL, ?4, NULL, NULL, 0, 0, NULL)",
        params![id, tavle_board_id, access_token, display_name],
    )
    .map_err(|e| e.to_string())?;

    get_board_link_by_id(paths, id)
}

fn get_board_link_by_id(paths: &AppPaths, id: String) -> Result<BoardLink, String> {
    let conn = open_db(paths)?;
    conn.query_row(
        "SELECT id, tavle_board_id, access_token, group_id, display_name, notes, tags, sort_order, pinned, last_opened_at
         FROM board_links WHERE id = ?1",
        params![id],
        |row| {
            Ok(BoardLink {
                id: row.get(0)?,
                tavle_board_id: row.get(1)?,
                access_token: row.get(2)?,
                group_id: row.get(3)?,
                display_name: row.get(4)?,
                notes: row.get(5)?,
                tags: row.get(6)?,
                sort_order: row.get(7)?,
                pinned: row.get::<_, i32>(8)? != 0,
                last_opened_at: row.get(9)?,
            })
        },
    )
    .map_err(|e| e.to_string())
}

pub fn move_board(paths: &AppPaths, board_link_id: String, group_id: Option<String>) -> Result<(), String> {
    let conn = open_db(paths)?;
    conn.execute(
        "UPDATE board_links SET group_id = ?2 WHERE id = ?1",
        params![board_link_id, group_id],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn update_board_meta(
    paths: &AppPaths,
    board_link_id: String,
    display_name: Option<String>,
    notes: Option<String>,
    tags: Option<String>,
    pinned: Option<bool>,
) -> Result<BoardLink, String> {
    let conn = open_db(paths)?;
    if let Some(name) = display_name {
        conn.execute(
            "UPDATE board_links SET display_name = ?2 WHERE id = ?1",
            params![board_link_id, name],
        )
        .map_err(|e| e.to_string())?;
    }
    if let Some(n) = notes {
        conn.execute(
            "UPDATE board_links SET notes = ?2 WHERE id = ?1",
            params![board_link_id, n],
        )
        .map_err(|e| e.to_string())?;
    }
    if let Some(t) = tags {
        conn.execute(
            "UPDATE board_links SET tags = ?2 WHERE id = ?1",
            params![board_link_id, t],
        )
        .map_err(|e| e.to_string())?;
    }
    if let Some(p) = pinned {
        conn.execute(
            "UPDATE board_links SET pinned = ?2 WHERE id = ?1",
            params![board_link_id, if p { 1 } else { 0 }],
        )
        .map_err(|e| e.to_string())?;
    }
    get_board_link_by_id(paths, board_link_id)
}

pub fn touch_board_opened(paths: &AppPaths, board_link_id: String) -> Result<(), String> {
    let conn = open_db(paths)?;
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE board_links SET last_opened_at = ?2 WHERE id = ?1",
        params![board_link_id, now],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn remove_board_link(paths: &AppPaths, board_link_id: String) -> Result<(), String> {
    let conn = open_db(paths)?;
    conn.execute("DELETE FROM board_links WHERE id = ?1", params![board_link_id])
        .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn get_setting(paths: &AppPaths, key: String) -> Result<Option<String>, String> {
    let conn = open_db(paths)?;
    let value: Option<String> = conn
        .query_row("SELECT value FROM settings WHERE key = ?1", params![key], |row| {
            row.get(0)
        })
        .ok();
    Ok(value)
}

pub fn set_setting(paths: &AppPaths, key: String, value: String) -> Result<(), String> {
    let conn = open_db(paths)?;
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        params![key, value],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn sync_boards_from_api(
    paths: &AppPaths,
    base_url: &str,
    admin_token: &str,
) -> Result<serde_json::Value, String> {
    let url = format!("{base_url}/api/boards");
    let client = reqwest::blocking::Client::new();
    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {admin_token}"))
        .send()
        .map_err(|e| e.to_string())?;

    if !resp.status().is_success() {
        return Err(format!("Tavle API error: {}", resp.status()));
    }

    let body: serde_json::Value = resp.json().map_err(|e| e.to_string())?;
    let boards = body
        .get("boards")
        .and_then(|b| b.as_array())
        .cloned()
        .unwrap_or_default();

    let mut synced = 0u32;
    for board in boards {
        let id = board.get("id").and_then(|v| v.as_str()).unwrap_or_default();
        let token = board
            .get("access_token")
            .and_then(|v| v.as_str())
            .map(String::from);
        let name = board
            .get("name")
            .and_then(|v| v.as_str())
            .map(String::from);
        if id.is_empty() {
            continue;
        }
        upsert_board_link(paths, id.to_string(), token, name)?;
        synced += 1;
    }

    Ok(serde_json::json!({ "synced": synced }))
}

pub fn create_board_via_api(
    paths: &AppPaths,
    base_url: &str,
    admin_token: &str,
    name: String,
) -> Result<BoardLink, String> {
    let url = format!("{base_url}/api/boards");
    let client = reqwest::blocking::Client::new();
    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {admin_token}"))
        .json(&serde_json::json!({ "name": name }))
        .send()
        .map_err(|e| e.to_string())?;

    if !resp.status().is_success() && resp.status().as_u16() != 201 {
        return Err(format!("Failed to create board: {}", resp.status()));
    }

    let body: serde_json::Value = resp.json().map_err(|e| e.to_string())?;
    let board = body.get("board").ok_or("Missing board in response")?;
    let id = board
        .get("id")
        .and_then(|v| v.as_str())
        .ok_or("Missing board id")?
        .to_string();
    let token = board
        .get("access_token")
        .and_then(|v| v.as_str())
        .map(String::from);
    let board_name = board
        .get("name")
        .and_then(|v| v.as_str())
        .map(String::from);

    upsert_board_link(paths, id, token, board_name)
}

pub fn delete_board_via_api(
    paths: &AppPaths,
    base_url: &str,
    admin_token: &str,
    tavle_board_id: String,
    board_link_id: String,
) -> Result<(), String> {
    let url = format!("{base_url}/api/boards/{tavle_board_id}");
    let client = reqwest::blocking::Client::new();
    let resp = client
        .delete(&url)
        .header("Authorization", format!("Bearer {admin_token}"))
        .send()
        .map_err(|e| e.to_string())?;

    if !resp.status().is_success() {
        return Err(format!("Failed to delete board: {}", resp.status()));
    }

    remove_board_link(paths, board_link_id)
}
