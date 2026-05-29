import { useState } from "react";
import { syncBoardsFromApi } from "../lib/api";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onRefresh: () => void;
}

export function SettingsModal({ open, onClose, onRefresh }: SettingsModalProps) {
  const [message, setMessage] = useState("");

  if (!open) return null;

  async function handleSync() {
    try {
      const result = await syncBoardsFromApi();
      setMessage(`Synced ${result.synced} boards.`);
      onRefresh();
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
          <p className="settings-note">
            Admin token is configured via the setup flow or <code>ADMIN_API_TOKEN</code> in{" "}
            <code>.env</code>.
          </p>
          <button type="button" className="btn" onClick={handleSync}>
            Sync boards from Tavle
          </button>
        </section>

        {message && <p className="settings-message">{message}</p>}
      </div>
    </div>
  );
}
