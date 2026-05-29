import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "metadata.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def list_groups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, parent_id, sort_order, color, created_at "
        "FROM groups ORDER BY sort_order, name"
    ).fetchall()
    return [dict(r) for r in rows]


def create_group(
    conn: sqlite3.Connection, name: str, parent_id: str | None
) -> dict[str, Any]:
    gid = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    sort_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM groups WHERE parent_id IS ?",
        (parent_id,),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO groups (id, name, parent_id, sort_order, color, created_at) "
        "VALUES (?, ?, ?, ?, NULL, ?)",
        (gid, name, parent_id, sort_order, created_at),
    )
    conn.commit()
    return {
        "id": gid,
        "name": name,
        "parent_id": parent_id,
        "sort_order": sort_order,
        "color": None,
        "created_at": created_at,
    }


def rename_group(conn: sqlite3.Connection, gid: str, name: str) -> None:
    conn.execute("UPDATE groups SET name = ? WHERE id = ?", (name, gid))
    conn.commit()


def delete_group(conn: sqlite3.Connection, gid: str) -> None:
    conn.execute("UPDATE board_links SET group_id = NULL WHERE group_id = ?", (gid,))
    conn.execute("DELETE FROM groups WHERE id = ?", (gid,))
    conn.commit()


def list_board_links(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, tavle_board_id, access_token, group_id, display_name, notes, tags, "
        "sort_order, pinned, last_opened_at FROM board_links "
        "ORDER BY pinned DESC, sort_order, display_name, tavle_board_id"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["pinned"] = bool(d["pinned"])
        out.append(d)
    return out


def upsert_board_link(
    conn: sqlite3.Connection,
    tavle_board_id: str,
    access_token: str | None,
    display_name: str | None,
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id FROM board_links WHERE tavle_board_id = ?", (tavle_board_id,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE board_links SET access_token = COALESCE(?, access_token), "
            "display_name = COALESCE(?, display_name) WHERE id = ?",
            (access_token, display_name, row["id"]),
        )
        conn.commit()
        return get_board_link(conn, row["id"])

    lid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO board_links "
        "(id, tavle_board_id, access_token, group_id, display_name, notes, tags, "
        "sort_order, pinned, last_opened_at) "
        "VALUES (?, ?, ?, NULL, ?, NULL, NULL, 0, 0, NULL)",
        (lid, tavle_board_id, access_token, display_name),
    )
    conn.commit()
    return get_board_link(conn, lid)


def get_board_link(conn: sqlite3.Connection, link_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, tavle_board_id, access_token, group_id, display_name, notes, tags, "
        "sort_order, pinned, last_opened_at FROM board_links WHERE id = ?",
        (link_id,),
    ).fetchone()
    d = dict(row)
    d["pinned"] = bool(d["pinned"])
    return d


def move_board(conn: sqlite3.Connection, link_id: str, group_id: str | None) -> None:
    conn.execute("UPDATE board_links SET group_id = ? WHERE id = ?", (group_id, link_id))
    conn.commit()


def update_board_meta(
    conn: sqlite3.Connection,
    link_id: str,
    display_name: str | None,
    notes: str | None,
    tags: str | None,
    pinned: bool | None,
) -> dict[str, Any]:
    if display_name is not None:
        conn.execute(
            "UPDATE board_links SET display_name = ? WHERE id = ?", (display_name, link_id)
        )
    if notes is not None:
        conn.execute("UPDATE board_links SET notes = ? WHERE id = ?", (notes, link_id))
    if tags is not None:
        conn.execute("UPDATE board_links SET tags = ? WHERE id = ?", (tags, link_id))
    if pinned is not None:
        conn.execute(
            "UPDATE board_links SET pinned = ? WHERE id = ?", (int(pinned), link_id)
        )
    conn.commit()
    return get_board_link(conn, link_id)


def touch_board_opened(conn: sqlite3.Connection, link_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE board_links SET last_opened_at = ? WHERE id = ?", (now, link_id)
    )
    conn.commit()


def remove_board_link(conn: sqlite3.Connection, link_id: str) -> None:
    conn.execute("DELETE FROM board_links WHERE id = ?", (link_id,))
    conn.commit()
