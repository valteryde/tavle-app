import { useCallback, useEffect, useState } from "react";
import { completeSetup, fetchSetupToken } from "../lib/api";

interface SetupViewProps {
  onComplete: () => void;
}

export function SetupView({ onComplete }: SetupViewProps) {
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadToken = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const t = await fetchSetupToken();
      setToken(t);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadToken();
  }, [loadToken]);

  async function handleCopy() {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy to clipboard.");
    }
  }

  async function handleComplete() {
    if (!token || !confirmed) return;
    setSubmitting(true);
    setError("");
    try {
      await completeSetup(token);
      onComplete();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="setup-view native-setup">
      <div className="setup-panel setup-panel-wide">
        <h2>First-time Tavle setup</h2>
        <p>
          Save your admin API token. The portal stores it in its database and uses
          it to manage boards. You can also set <code>ADMIN_API_TOKEN</code> in{" "}
          <code>.env</code> before starting Docker.
        </p>

        {loading && <p className="setup-status">Loading token from Tavle…</p>}

        {error && (
          <div className="setup-error">
            <p>{error}</p>
            <button type="button" className="btn" onClick={loadToken}>
              Retry
            </button>
          </div>
        )}

        {!loading && token && (
          <>
            <label htmlFor="setup-token" className="setup-label">
              Admin API token
            </label>
            <div className="token-row">
              <input
                id="setup-token"
                type="text"
                readOnly
                value={token}
                className="token-input"
              />
              <button type="button" className="btn" onClick={handleCopy}>
                {copied ? "Copied" : "Copy"}
              </button>
            </div>

            <ul className="setup-security-list">
              <li>Store this token somewhere safe — it grants full API access.</li>
              <li>Add it to <code>.env</code> as <code>ADMIN_API_TOKEN=…</code> for restarts.</li>
            </ul>

            <label className="setup-confirm">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              I have saved this token
            </label>

            <button
              type="button"
              className="btn primary"
              disabled={!confirmed || submitting}
              onClick={handleComplete}
            >
              {submitting ? "Finishing setup…" : "Continue to Tavle App"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
