// Shown while the backend pre-generates everything. Makes the (intentional)
// wait feel deliberate and cinematic rather than frustrating.
import type { BuildStatus } from "../api";

const STEPS: { key: BuildStatus["status"]; label: string }[] = [
  { key: "cloning", label: "Cloning repository" },
  { key: "parsing", label: "Mapping modules, classes & functions" },
  { key: "tour", label: "Designing the guided dive" },
  { key: "narrating", label: "Writing an explanation for every node" },
];

const ORDER: BuildStatus["status"][] = ["cloning", "parsing", "tour", "narrating", "ready"];

interface Props {
  status: BuildStatus;
  onRetry: () => void;
}

export function BuildProgress({ status, onRetry }: Props) {
  const curIdx = ORDER.indexOf(status.status);

  return (
    <div className="build">
      <div className="home-aurora" />
      <div className="build-card">
        {status.status === "error" ? (
          <>
            <div className="build-emoji">⚠</div>
            <h2 className="build-title">Build failed</h2>
            <div className="build-errmsg">{status.error}</div>
            <button className="btn primary big" onClick={onRetry}>← Try another repository</button>
          </>
        ) : (
          <>
            <div className="loading-ring" />
            <h2 className="build-title">
              {status.repo?.name ? `Building “${status.repo.name}”` : "Building your dive"}
            </h2>
            <div className="build-msg">{status.message || "Starting…"}</div>

            <div className="build-steps">
              {STEPS.map((s) => {
                const idx = ORDER.indexOf(s.key);
                const state = idx < curIdx ? "done" : idx === curIdx ? "active" : "todo";
                return (
                  <div key={s.key} className={`build-step ${state}`}>
                    <span className="build-step-dot">
                      {state === "done" ? "✓" : state === "active" ? "●" : "○"}
                    </span>
                    <span className="build-step-label">{s.label}</span>
                    {s.key === "narrating" && status.total > 0 && (
                      <span className="build-step-count">
                        {status.done}/{status.total}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="build-bar">
              <div style={{ width: `${status.percent}%` }} />
            </div>

            {status.repo && (
              <div className="build-meta">
                {status.repo.fileCount} files · {status.repo.totalLines.toLocaleString()} lines
                {status.stats ? ` · ${status.stats.nodeCount} nodes` : ""}
              </div>
            )}

            <div className="build-note">
              Generating everything up front means the dive plays back perfectly
              smooth — no pauses mid-journey. Hang tight, this is worth the wait.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
