import { useEffect, useState } from "react";

import { checkHealth, type HealthResult } from "../api/health";

type HealthState = HealthResult | { kind: "loading" } | { kind: "offline" };

function statusContent(state: HealthState) {
  switch (state.kind) {
    case "loading":
      return { title: "Checking data availability", description: "Connecting to GAIA. This may take a moment." };
    case "unavailable":
      return { title: "Dataset not available yet", description: "The precipitation dataset has not been added yet. Regional trends will be available after the data has been verified." };
    case "incompatible":
      return { title: "Dataset needs verification", description: "The available data could not be verified. Exploration will be available once a verified dataset is ready." };
    case "offline":
      return { title: "Unable to connect", description: "GAIA could not check the data right now. Please try again in a moment." };
    case "ready":
      return { title: "Dataset verified", description: `Dataset ${state.datasetVersion} is available. Regional exploration is coming in a future version.` };
  }
}

export default function Home() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 10_000);
    setState({ kind: "loading" });

    checkHealth(controller.signal)
      .then((result) => { if (active) setState(result); })
      .catch(() => { if (active) setState({ kind: "offline" }); })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [attempt]);

  const content = statusContent(state);
  const loading = state.kind === "loading";

  return (
    <div className="page-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="site-header">
        <div>
          <p className="wordmark">GAIA<span aria-hidden="true">.</span></p>
          <p className="brand-description">Earth System Trend Detective</p>
        </div>
        <nav aria-label="Main navigation">
          <a className="text-link" href="#about">About GAIA</a>
        </nav>
      </header>

      <main id="main" tabIndex={-1}>
        <div className="intro-grid">
          <section className="introduction" aria-labelledby="page-title">
            <p className="eyebrow">Regional precipitation</p>
            <h1 id="page-title">Understand how<br className="desktop-break" /> rainfall is changing.</h1>
            <p className="intro-copy">Look beyond the annual total. Investigate changes across months, seasons, and regions, with the evidence behind each trend.</p>
            <p className="scope-note">Two regions. One shared question.<br />Where and when is the rain changing?</p>
          </section>

          <section className="availability" aria-labelledby="availability-heading">
            <div className="card-heading">
              <svg aria-hidden="true" viewBox="0 0 32 32" fill="none" className="rain-icon">
                <path d="M16 3C16 3 6 15 6 21a10 10 0 0 0 20 0C26 15 16 3 16 3Z" stroke="currentColor" strokeWidth="1.8" />
                <path d="M11 21a5 5 0 0 0 5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
              <h2 id="availability-heading">Data availability</h2>
            </div>
            <div role="status" aria-atomic="true" className="status-copy">
              <p className="status-label">{state.kind === "ready" ? "Ready" : loading ? "Checking" : "Exploration unavailable"}</p>
              <h3>{content.title}</h3>
              <p>{content.description}</p>
            </div>
            <button
              type="button"
              aria-disabled={loading}
              onClick={() => { if (!loading) setAttempt((value) => value + 1); }}
            >
              {loading ? "Checking…" : "Check again"}
            </button>
            <p className="card-note">Trends require verified observations.</p>
          </section>
        </div>

        <section id="about" className="about" aria-labelledby="about-heading" tabIndex={-1}>
          <p className="eyebrow">The investigation</p>
          <h2 id="about-heading">A clearer view of changing rainfall.</h2>
          <p>GAIA is being built to connect regional precipitation records with understandable statistical evidence.</p>
          <div className="feature-grid">
            <article>
              <h3>Find the pattern</h3>
              <p>Explore monthly and seasonal changes, with annual totals for context.</p>
            </article>
            <article>
              <h3>Compare regions</h3>
              <p>Examine two predefined regions over the same period and aggregation.</p>
            </article>
            <article>
              <h3>Inspect the evidence</h3>
              <p>See the rate of change, uncertainty, and source of each result.</p>
            </article>
          </div>
        </section>
      </main>

      <footer>GAIA · Precipitation, in perspective.</footer>
    </div>
  );
}
