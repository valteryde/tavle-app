import type { BoardLink, Group } from "../types";

interface GroupSidebarProps {
  groups: Group[];
  boards: BoardLink[];
  selectedBoardId: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectBoard: (board: BoardLink) => void;
  onCreateBoard: () => void;
  onCreateGroup: () => void;
  onMoveBoard: (boardLinkId: string, groupId: string | null) => void;
  onDeleteBoard: (board: BoardLink) => void;
  onTogglePin: (board: BoardLink) => void;
}

function boardLabel(board: BoardLink): string {
  return board.display_name || board.tavle_board_id.slice(0, 8);
}

function matchesSearch(board: BoardLink, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  const label = boardLabel(board).toLowerCase();
  const notes = (board.notes || "").toLowerCase();
  const tags = (board.tags || "").toLowerCase();
  return label.includes(q) || notes.includes(q) || tags.includes(q);
}

export function GroupSidebar({
  groups,
  boards,
  selectedBoardId,
  search,
  onSearchChange,
  onSelectBoard,
  onCreateBoard,
  onCreateGroup,
  onMoveBoard,
  onDeleteBoard,
  onTogglePin,
}: GroupSidebarProps) {
  const unassigned = boards.filter((b) => !b.group_id && matchesSearch(b, search));
  const byGroup = (groupId: string) =>
    boards.filter((b) => b.group_id === groupId && matchesSearch(b, search));

  return (
    <aside className="sidebar">
      <div className="sidebar-toolbar">
        <input
          type="search"
          placeholder="Search boards…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="search-input"
        />
        <div className="sidebar-actions">
          <button type="button" className="btn small" onClick={onCreateBoard}>
            + Board
          </button>
          <button type="button" className="btn small" onClick={onCreateGroup}>
            + Group
          </button>
        </div>
      </div>

      <nav className="group-tree">
        {groups.map((group) => (
          <section key={group.id} className="group-section">
            <h3 className="group-title">{group.name}</h3>
            <ul className="board-list">
              {byGroup(group.id).map((board) => (
                <BoardRow
                  key={board.id}
                  board={board}
                  selected={board.id === selectedBoardId}
                  groups={groups}
                  onSelect={() => onSelectBoard(board)}
                  onMove={onMoveBoard}
                  onDelete={() => onDeleteBoard(board)}
                  onTogglePin={() => onTogglePin(board)}
                />
              ))}
            </ul>
          </section>
        ))}

        <section className="group-section">
          <h3 className="group-title muted">Unassigned</h3>
          <ul className="board-list">
            {unassigned.map((board) => (
              <BoardRow
                key={board.id}
                board={board}
                selected={board.id === selectedBoardId}
                groups={groups}
                onSelect={() => onSelectBoard(board)}
                onMove={onMoveBoard}
                onDelete={() => onDeleteBoard(board)}
                onTogglePin={() => onTogglePin(board)}
              />
            ))}
          </ul>
        </section>
      </nav>
    </aside>
  );
}

function BoardRow({
  board,
  selected,
  groups,
  onSelect,
  onMove,
  onDelete,
  onTogglePin,
}: {
  board: BoardLink;
  selected: boolean;
  groups: Group[];
  onSelect: () => void;
  onMove: (boardLinkId: string, groupId: string | null) => void;
  onDelete: () => void;
  onTogglePin: () => void;
}) {
  return (
    <li className={`board-row ${selected ? "selected" : ""}`}>
      <button type="button" className="board-select" onClick={onSelect}>
        {board.pinned && <span className="pin">★</span>}
        {boardLabel(board)}
      </button>
      <select
        className="group-select"
        value={board.group_id || ""}
        onChange={(e) =>
          onMove(board.id, e.target.value ? e.target.value : null)
        }
        aria-label="Move to group"
      >
        <option value="">Unassigned</option>
        {groups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="btn icon small"
        onClick={onTogglePin}
        title={board.pinned ? "Unpin" : "Pin"}
      >
        {board.pinned ? "★" : "☆"}
      </button>
      <button
        type="button"
        className="btn icon small danger"
        onClick={onDelete}
        title="Delete board"
      >
        ⌫
      </button>
    </li>
  );
}
