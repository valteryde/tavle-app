import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.metadata_db import (
    connect,
    create_group,
    delete_group,
    list_board_links,
    list_groups,
    move_board,
    remove_board_link,
    rename_group,
    touch_board_opened,
    update_board_meta,
    upsert_board_link,
)
from backend.tavle_client import TavleClient


class Settings(BaseSettings):
    tavle_internal_url: str = "http://tavle:5050"
    tavle_public_url: str = "http://localhost:5050"
    admin_api_token: str = ""
    metadata_db_path: str = "/data/metadata.db"
    static_dir: str = "/app/static"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
STATIC_DIR = Path(settings.static_dir)
DB_PATH = Path(settings.metadata_db_path)


def load_admin_token(conn: sqlite3.Connection) -> str:
    env_token = os.environ.get("ADMIN_API_TOKEN", "").strip()
    if env_token:
        return env_token
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'admin_api_token'"
    ).fetchone()
    return row[0] if row else ""


def save_admin_token(conn: sqlite3.Connection, token: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('admin_api_token', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (token,),
    )
    conn.commit()
    settings.admin_api_token = token
    os.environ["ADMIN_API_TOKEN"] = token


def get_conn() -> sqlite3.Connection:
    if not hasattr(get_conn, "_conn"):
        get_conn._conn = connect(DB_PATH)  # type: ignore[attr-defined]
    return get_conn._conn  # type: ignore[attr-defined]


def tavle() -> TavleClient:
    return TavleClient(settings.tavle_internal_url, settings.admin_api_token or None)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = connect(DB_PATH)
    token = load_admin_token(conn)
    if token:
        settings.admin_api_token = token
        os.environ["ADMIN_API_TOKEN"] = token
    yield


app = FastAPI(title="Tavle App Portal", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GroupCreate(BaseModel):
    name: str
    parent_id: str | None = None


class GroupRename(BaseModel):
    name: str


class BoardMove(BaseModel):
    group_id: str | None


class BoardMetaUpdate(BaseModel):
    display_name: str | None = None
    notes: str | None = None
    tags: str | None = None
    pinned: bool | None = None


class BoardCreate(BaseModel):
    name: str = "Untitled"


class SetupComplete(BaseModel):
    token: str


@app.get("/api/status")
async def status() -> dict[str, Any]:
    healthy = await tavle().health()
    needs_setup = not settings.admin_api_token
    return {
        "tavle_public_url": settings.tavle_public_url,
        "tavle_healthy": healthy,
        "needs_setup": needs_setup,
        "ready": healthy and not needs_setup,
    }


@app.get("/api/setup/token")
async def setup_token() -> dict[str, str]:
    try:
        token = await tavle().fetch_setup_token()
        return {"token": token}
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.post("/api/setup/complete")
async def setup_complete(body: SetupComplete) -> dict[str, str]:
    try:
        client = TavleClient(settings.tavle_internal_url, body.token)
        await client.complete_setup()
        save_admin_token(get_conn(), body.token)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/groups")
def api_list_groups() -> list[dict[str, Any]]:
    return list_groups(get_conn())


@app.post("/api/groups")
def api_create_group(body: GroupCreate) -> dict[str, Any]:
    return create_group(get_conn(), body.name, body.parent_id)


@app.patch("/api/groups/{group_id}")
def api_rename_group(group_id: str, body: GroupRename) -> dict[str, str]:
    rename_group(get_conn(), group_id, body.name)
    return {"status": "ok"}


@app.delete("/api/groups/{group_id}")
def api_delete_group(group_id: str) -> dict[str, str]:
    delete_group(get_conn(), group_id)
    return {"status": "ok"}


@app.get("/api/board-links")
def api_list_board_links() -> list[dict[str, Any]]:
    return list_board_links(get_conn())


@app.post("/api/board-links/sync")
async def api_sync_boards() -> dict[str, int]:
    if not settings.admin_api_token:
        raise HTTPException(400, "Admin API token not configured")
    try:
        boards = await tavle().list_boards()
    except Exception as e:
        raise HTTPException(502, str(e)) from e

    conn = get_conn()
    for board in boards:
        bid = board.get("id")
        if not bid:
            continue
        upsert_board_link(
            conn,
            bid,
            board.get("access_token"),
            board.get("name"),
        )
    return {"synced": len(boards)}


@app.post("/api/board-links")
async def api_create_board(body: BoardCreate) -> dict[str, Any]:
    if not settings.admin_api_token:
        raise HTTPException(400, "Admin API token not configured")
    try:
        board = await tavle().create_board(body.name)
    except Exception as e:
        raise HTTPException(502, str(e)) from e
    return upsert_board_link(
        get_conn(),
        board["id"],
        board.get("access_token"),
        board.get("name"),
    )


@app.patch("/api/board-links/{link_id}/move")
def api_move_board(link_id: str, body: BoardMove) -> dict[str, str]:
    move_board(get_conn(), link_id, body.group_id)
    return {"status": "ok"}


@app.patch("/api/board-links/{link_id}")
def api_update_board(link_id: str, body: BoardMetaUpdate) -> dict[str, Any]:
    return update_board_meta(
        get_conn(),
        link_id,
        body.display_name,
        body.notes,
        body.tags,
        body.pinned,
    )


@app.post("/api/board-links/{link_id}/touch")
def api_touch_board(link_id: str) -> dict[str, str]:
    touch_board_opened(get_conn(), link_id)
    return {"status": "ok"}


@app.delete("/api/board-links/{link_id}")
async def api_delete_board(link_id: str, tavle_board_id: str = "") -> dict[str, str]:
    if settings.admin_api_token:
        try:
            await tavle().delete_board(tavle_board_id)
        except Exception as e:
            raise HTTPException(502, str(e)) from e
    remove_board_link(get_conn(), link_id)
    return {"status": "ok"}


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        index = STATIC_DIR / "index.html"
        if full_path and (STATIC_DIR / full_path).is_file():
            return FileResponse(STATIC_DIR / full_path)
        if index.exists():
            return FileResponse(index)
        raise HTTPException(404, "Frontend not built")
