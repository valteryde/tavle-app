interface SetupViewProps {
  baseUrl: string;
  onComplete: () => void;
}

export function SetupView({ baseUrl, onComplete }: SetupViewProps) {
  const setupUrl = `${baseUrl.replace(/\/$/, "")}/`;

  return (
    <div className="setup-view">
      <div className="setup-panel">
        <h2>First-time Tavle setup</h2>
        <p>
          Complete the Tavle setup wizard below. When finished, click
          &quot;I&apos;ve completed setup&quot; to import your admin API token.
        </p>
        <button type="button" className="btn primary" onClick={onComplete}>
          I&apos;ve completed setup
        </button>
      </div>
      <iframe
        className="setup-frame"
        title="Tavle setup"
        src={setupUrl}
      />
    </div>
  );
}
