import { useCallback, useEffect, useState } from "react";
import "./App.css";
import { BoardFrame } from "./components/BoardFrame";
import { GroupSidebar } from "./components/GroupSidebar";
import { SettingsModal } from "./components/SettingsModal";
import { SetupView } from "./components/SetupView";
import {
  createBoard,
  createGroup,
  deleteBoard,
  getStatus,
  listBoardLinks,
  listGroups,
  moveBoard,
  syncBoardsFromApi,
  touchBoardOpened,
  updateBoardMeta,
} from "./lib/api";
import type { AppStatus } from "./lib/api";
import type { BoardLink, Group } from "./types";

type AppPhase = "loading" | "error" | "setup" | "ready";

function App() {
  const [phase, setPhase] = useState<AppPhase>("loading");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [groups, setGroups] = useState<Group[]>([]);
  const [boards, setBoards] = useState<BoardLink[]>([]);
  const [selectedBoard, setSelectedBoard] = useState<BoardLink | null>(null);
  const [search, setSearch] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refreshLibrary = useCallback(async () => {
    const [g, b] = await Promise.all([listGroups(), listBoardLinks()]);
    setGroups(g);
    setBoards(b);
  }, []);

  const bootstrap = useCallback(async () => {
    setPhase("loading");
    setError("");
    try {
      const st = await getStatus();
      setStatus(st);

      if (!st.tavle_healthy) {
        throw new Error(
          "Tavle is not reachable. Run: docker compose up --build",
        );
      }

      if (st.needs_setup) {
        setPhase("setup");
        return;
      }

      await syncBoardsFromApi();
      await refreshLibrary();
      setPhase("ready");
    } catch (e) {
      setError(String(e));
      setPhase("error");
    }
  }, [refreshLibrary]);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  async function handleSetupComplete() {
    await bootstrap();
  }

  async function handleCreateBoard() {
    const name = window.prompt("Board name", "Untitled");
    if (!name?.trim()) return;
    const link = await createBoard(name.trim());
    await refreshLibrary();
    setSelectedBoard(link);
    await touchBoardOpened(link.id);
  }

  async function handleCreateGroup() {
    const name = window.prompt("Group name");
    if (!name?.trim()) return;
    await createGroup(name.trim());
    await refreshLibrary();
  }

  async function handleSelectBoard(board: BoardLink) {
    setSelectedBoard(board);
    await touchBoardOpened(board.id);
    await refreshLibrary();
  }

  async function handleDeleteBoard(board: BoardLink) {
    if (!window.confirm(`Delete board "${board.display_name || board.tavle_board_id}"?`)) {
      return;
    }
    await deleteBoard(board.tavle_board_id, board.id);
    if (selectedBoard?.id === board.id) setSelectedBoard(null);
    await refreshLibrary();
  }

  async function handleTogglePin(board: BoardLink) {
    await updateBoardMeta(board.id, { pinned: !board.pinned });
    await refreshLibrary();
  }

  if (phase === "loading") {
    return (
      <div className="app-shell center">
        <p>Connecting to Tavle…</p>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="app-shell center">
        <p className="error-text">{error}</p>
        <button type="button" className="btn primary" onClick={bootstrap}>
          Retry
        </button>
      </div>
    );
  }

  if (phase === "setup" && status) {
    return (
      <div className="app-shell setup-shell">
        <SetupView onComplete={handleSetupComplete} />
        {error && <p className="error-banner">{error}</p>}
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1 className="app-title">Tavle App</h1>
        <span className="status-pill">
          {status?.tavle_healthy ? status.tavle_public_url : "Offline"}
        </span>
        <button
          type="button"
          className="btn"
          onClick={() => setSettingsOpen(true)}
        >
          Settings
        </button>
      </header>

      <div className="workspace">
        <GroupSidebar
          groups={groups}
          boards={boards}
          selectedBoardId={selectedBoard?.id ?? null}
          search={search}
          onSearchChange={setSearch}
          onSelectBoard={handleSelectBoard}
          onCreateBoard={handleCreateBoard}
          onCreateGroup={handleCreateGroup}
          onMoveBoard={async (id, groupId) => {
            await moveBoard(id, groupId);
            await refreshLibrary();
          }}
          onDeleteBoard={handleDeleteBoard}
          onTogglePin={handleTogglePin}
        />

        <main className="main-panel">
          {selectedBoard?.access_token && status ? (
            <BoardFrame
              baseUrl={status.tavle_public_url}
              accessToken={selectedBoard.access_token}
            />
          ) : (
            <div className="empty-state">
              <p>Select a board from the sidebar, or create a new one.</p>
            </div>
          )}
        </main>
      </div>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onRefresh={bootstrap}
      />
    </div>
  );
}

export default App;
