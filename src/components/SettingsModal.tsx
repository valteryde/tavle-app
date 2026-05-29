import { useState } from "react";
import {
  clearAdminToken,
  fetchTavleSource,
  getAppPaths,
  setAdminToken,
  syncBoardsFromApi,
  tavleSourceStatus,
} from "../lib/tauri";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onTokenSaved: () => void;
}

export function SettingsModal({ open, onClose, onTokenSaved }: SettingsModalProps) {
  const [token, setToken] = useState("");
  const [paths, setPaths] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");

  if (!open) return null;

  async function loadPaths() {
    const p = await getAppPaths();
    setPaths(p);
  }

  async function saveToken() {
    if (!token.trim()) return;
    await setAdminToken(token.trim());
    setMessage("Token saved to keychain.");
    onTokenSaved();
  }

  async function handleRedownloadTavle() {
    try {
      setMessage("Downloading Tavle from GitHub…");
      const info = await fetchTavleSource({ force: true });
      setMessage(`Tavle ${info.git_ref} installed at ${info.path}`);
      onTokenSaved();
    } catch (e) {
      setMessage(String(e));
    }
  }

  async function handleShowSource() {
    const info = await tavleSourceStatus();
    setMessage(
      info.installed
        ? `Tavle ${info.repo}@${info.git_ref} at ${info.path}`
        : "Tavle source not installed yet.",
    );
  }

  async function handleSync() {
    try {
      const result = await syncBoardsFromApi();
      setMessage(`Synced ${result.synced} boards.`);
    } catch (e) {
      setMessage(String(e));
    }
  }

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-labelledby="settings-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="settings-title">Settings</h2>
          <button type="button" className="btn icon" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <section className="modal-section">
          <label htmlFor="admin-token">Admin API token</label>
          <input
            id="admin-token"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste token from Tavle setup"
          />
          <div className="modal-actions">
            <button type="button" className="btn" onClick={saveToken}>
              Save token
            </button>
            <button type="button" className="btn" onClick={() => clearAdminToken()}>
              Clear token
            </button>
          </div>
        </section>

        <section className="modal-section">
          <p className="settings-note">
            Tavle is downloaded on first launch from GitHub into app data (not stored in this repo).
          </p>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={handleShowSource}>
              Tavle source status
            </button>
            <button type="button" className="btn" onClick={handleRedownloadTavle}>
              Re-download Tavle
            </button>
          </div>
        </section>

        <section className="modal-section">
          <button type="button" className="btn" onClick={handleSync}>
            Sync boards from Tavle
          </button>
          <button type="button" className="btn" onClick={loadPaths}>
            Show data paths
          </button>
          {paths && (
            <pre className="paths-dump">
              {JSON.stringify(paths, null, 2)}
            </pre>
          )}
        </section>

        {message && <p className="settings-message">{message}</p>}
      </div>
    </div>
  );
}
