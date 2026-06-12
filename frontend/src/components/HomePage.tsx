// Landing page: collect a Git repo URL + Personal Access Token (+ optional
// branch), then kick off the full pre-generation build.
import { useState } from "react";

interface Props {
  onStart: (url: string, pat: string, branch: string) => void;
  error: string | null;
}

export function HomePage({ onStart, error }: Props) {
  const [url, setUrl] = useState("");
  const [pat, setPat] = useState("");
  const [branch, setBranch] = useState("");
  const [showPat, setShowPat] = useState(false);

  const canStart = url.trim().length > 0;

  return (
    <div className="home">
      <div className="home-aurora" />
      <div className="home-card">
        <div className="home-brandrow">
          <div className="brand-mark big">◈</div>
          <div>
            <h1 className="home-title">Codebase Atlas</h1>
            <p className="home-sub">Explore any repository as a living, zoomable map — click any node to read and hear what it does.</p>
          </div>
        </div>

        <div className="home-field">
          <label>Repository URL</label>
          <input
            className="home-input"
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoFocus
          />
        </div>

        <div className="home-field">
          <label>
            Personal Access Token <span className="home-opt">(required for private repos)</span>
          </label>
          <div className="home-pat">
            <input
              className="home-input"
              type={showPat ? "text" : "password"}
              placeholder="ghp_… / glpat-…"
              value={pat}
              onChange={(e) => setPat(e.target.value)}
            />
            <button className="btn icon" type="button" onClick={() => setShowPat((s) => !s)}>
              {showPat ? "🙈" : "👁"}
            </button>
          </div>
          <div className="home-hint">Used only to clone. Never stored or logged.</div>
        </div>

        <div className="home-field">
          <label>Branch <span className="home-opt">(optional — defaults to the repo’s default)</span></label>
          <input
            className="home-input"
            placeholder="main / dev/feature-x"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
        </div>

        {error && <div className="home-error">⚠ {error}</div>}

        <button
          className="btn primary big home-go"
          disabled={!canStart}
          onClick={() => onStart(url.trim(), pat.trim(), branch.trim())}
        >
          Analyze &amp; build the dive →
        </button>

        <div className="home-note">
          We’ll clone the repo, map every module and function, and pre-generate an
          AI explanation for <b>every node</b> before the dive begins — so the
          journey plays back perfectly smooth, start to finish.
        </div>
      </div>
    </div>
  );
}
