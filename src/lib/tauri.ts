import { invoke } from "@tauri-apps/api/core";
import type { BoardLink, Group, TavleStatus } from "../types";

export async function startTavle(): Promise<TavleStatus> {
  return invoke("start_tavle");
}

export async function stopTavle(): Promise<void> {
  return invoke("stop_tavle");
}

export async function tavleStatus(): Promise<TavleStatus> {
  return invoke("tavle_status");
}

export async function tavleNeedsSetup(): Promise<boolean> {
  return invoke("tavle_needs_setup");
}

export async function fetchSetupToken(baseUrl: string): Promise<string> {
  return invoke("fetch_setup_token", { baseUrl });
}

export async function completeTavleSetup(
  baseUrl: string,
  token: string,
): Promise<void> {
  return invoke("complete_tavle_setup", { baseUrl, token });
}

export async function importAdminTokenFromTavle(): Promise<string | null> {
  return invoke("import_admin_token_from_tavle");
}

export async function getAdminToken(): Promise<string | null> {
  return invoke("get_admin_token");
}

export async function setAdminToken(token: string): Promise<void> {
  return invoke("set_admin_token", { token });
}

export async function clearAdminToken(): Promise<void> {
  return invoke("clear_admin_token");
}

export async function listGroups(): Promise<Group[]> {
  return invoke("list_groups");
}

export async function createGroup(
  name: string,
  parentId?: string | null,
): Promise<Group> {
  return invoke("create_group", { name, parentId: parentId ?? null });
}

export async function renameGroup(id: string, name: string): Promise<void> {
  return invoke("rename_group", { id, name });
}

export async function deleteGroup(id: string): Promise<void> {
  return invoke("delete_group", { id });
}

export async function listBoardLinks(): Promise<BoardLink[]> {
  return invoke("list_board_links");
}

export async function moveBoard(
  boardLinkId: string,
  groupId: string | null,
): Promise<void> {
  return invoke("move_board", { boardLinkId, groupId });
}

export async function updateBoardMeta(
  boardLinkId: string,
  fields: {
    displayName?: string;
    notes?: string;
    tags?: string;
    pinned?: boolean;
  },
): Promise<BoardLink> {
  return invoke("update_board_meta", {
    boardLinkId,
    displayName: fields.displayName ?? null,
    notes: fields.notes ?? null,
    tags: fields.tags ?? null,
    pinned: fields.pinned ?? null,
  });
}

export async function touchBoardOpened(boardLinkId: string): Promise<void> {
  return invoke("touch_board_opened", { boardLinkId });
}

export async function syncBoardsFromApi(): Promise<{ synced: number }> {
  return invoke("sync_boards_from_api");
}

export async function createBoard(name: string): Promise<BoardLink> {
  return invoke("create_board", { name });
}

export async function deleteBoard(
  tavleBoardId: string,
  boardLinkId: string,
): Promise<void> {
  return invoke("delete_board", { tavleBoardId, boardLinkId });
}

export async function getAppPaths(): Promise<Record<string, unknown>> {
  return invoke("get_app_paths");
}

export interface TavleSourceInfo {
  repo: string;
  git_ref: string;
  path: string;
  installed: boolean;
  fetched_at: string | null;
}

export async function tavleSourceStatus(): Promise<TavleSourceInfo> {
  return invoke("tavle_source_status");
}

export async function fetchTavleSource(options?: {
  repo?: string;
  gitRef?: string;
  force?: boolean;
}): Promise<TavleSourceInfo> {
  return invoke("fetch_tavle_source", {
    repo: options?.repo ?? null,
    gitRef: options?.gitRef ?? null,
    force: options?.force ?? false,
  });
}
