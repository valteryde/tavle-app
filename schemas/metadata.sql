CREATE TABLE IF NOT EXISTS groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  parent_id TEXT REFERENCES groups(id),
  sort_order INTEGER NOT NULL DEFAULT 0,
  color TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS board_links (
  id TEXT PRIMARY KEY,
  tavle_board_id TEXT NOT NULL UNIQUE,
  access_token TEXT,
  group_id TEXT REFERENCES groups(id),
  display_name TEXT,
  notes TEXT,
  tags TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  last_opened_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
