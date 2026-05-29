import type { BoardLink, Group } from "../types";

const API = "/api";

export interface AppStatus {
  tavle_public_url: string;
  tavle_healthy: boolean;
  needs_setup: boolean;
  ready: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function getStatus(): Promise<AppStatus> {
  return request("/status");
}

export async function fetchSetupToken(): Promise<string> {
  const data = await request<{ token: string }>("/setup/token");
  return data.token;
}

export async function completeSetup(token: string): Promise<void> {
  await request("/setup/complete", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function listGroups(): Promise<Group[]> {
  return request("/groups");
}

export async function createGroup(
  name: string,
  parentId?: string | null,
): Promise<Group> {
  return request("/groups", {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId ?? null }),
  });
}

export async function listBoardLinks(): Promise<BoardLink[]> {
  return request("/board-links");
}

export async function syncBoardsFromApi(): Promise<{ synced: number }> {
  return request("/board-links/sync", { method: "POST" });
}

export async function createBoard(name: string): Promise<BoardLink> {
  return request("/board-links", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function moveBoard(
  boardLinkId: string,
  groupId: string | null,
): Promise<void> {
  await request(`/board-links/${boardLinkId}/move`, {
    method: "PATCH",
    body: JSON.stringify({ group_id: groupId }),
  });
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
  return request(`/board-links/${boardLinkId}`, {
    method: "PATCH",
    body: JSON.stringify({
      display_name: fields.displayName ?? null,
      notes: fields.notes ?? null,
      tags: fields.tags ?? null,
      pinned: fields.pinned ?? null,
    }),
  });
}

export async function touchBoardOpened(boardLinkId: string): Promise<void> {
  await request(`/board-links/${boardLinkId}/touch`, { method: "POST" });
}

export async function deleteBoard(
  tavleBoardId: string,
  boardLinkId: string,
): Promise<void> {
  await request(
    `/board-links/${boardLinkId}?tavle_board_id=${encodeURIComponent(tavleBoardId)}`,
    { method: "DELETE" },
  );
}

export function tavlePublicUrl(): string {
  return import.meta.env.VITE_TAVLE_PUBLIC_URL || "http://localhost:5050";
}
