export interface Group {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  color: string | null;
  created_at: string;
}

export interface BoardLink {
  id: string;
  tavle_board_id: string;
  access_token: string | null;
  group_id: string | null;
  display_name: string | null;
  notes: string | null;
  tags: string | null;
  sort_order: number;
  pinned: boolean;
  last_opened_at: string | null;
}

export interface TavleStatus {
  running: boolean;
  port: number;
  base_url: string;
}
