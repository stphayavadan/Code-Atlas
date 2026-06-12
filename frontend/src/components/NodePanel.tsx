// NodePanel: the LEFT pane. Shows the focused node's kind, title, path and
// description (the pre-generated narration).
//
// Two modes:
//   NORMAL  — Prev / Next walk the flow; a Play / Pause button speaks the
//             current node's description (no auto-advance).
//   RENDER  — an auto-tour: from node 1 it reads each description aloud and
//             glides to the next, to the end. Can be paused, resumed, restarted;
//             pressing Next/clicking a node keeps auto-reading from there.

import type { GraphNode } from "../types";
import type { SpeakMark } from "../hooks/useSpeech";

interface Props {
  node: GraphNode | null;
  index: number;
  total: number;
  text: string;
  loading: boolean;
  speaking: boolean;
  mark: SpeakMark | null;   // word currently spoken (for karaoke highlight)
  rendering: boolean;       // an auto-tour session is engaged
  playing: boolean;         // actively reading + advancing
  onPlay: () => void;
  onPause: () => void;
  onPrev: () => void;
  onNext: () => void;
  onStartRender: () => void;
  onPauseRender: () => void;
  onResumeRender: () => void;
  onStopRender: () => void;
}

const KIND_COLOR: Record<string, string> = {
  package: "#7c5cff",
  module: "#22d3ee",
  class: "#f59e0b",
  function: "#34d399",
  method: "#f472b6",
};

// Render the description with the word being spoken highlighted (karaoke).
function HighlightedText({ text, mark }: { text: string; mark: SpeakMark | null }) {
  if (!mark || mark.end <= mark.start || mark.start >= text.length) return <>{text}</>;
  const before = text.slice(0, mark.start);
  const word = text.slice(mark.start, mark.end);
  const after = text.slice(mark.end);
  return (
    <>
      {before}
      <mark className="np-speakmark">{word}</mark>
      {after}
    </>
  );
}

export function NodePanel({
  node, index, total, text, loading, speaking, mark,
  rendering, playing,
  onPlay, onPause, onPrev, onNext,
  onStartRender, onPauseRender, onResumeRender, onStopRender,
}: Props) {
  if (!node) {
    return (
      <aside className="nodepanel">
        <div className="np-empty">
          <div className="np-empty-mark">◈</div>
          <div className="np-empty-title">Building the flow…</div>
        </div>
      </aside>
    );
  }

  const color = KIND_COLOR[node.kind] ?? "#22d3ee";
  const canPlay = !!text && !loading;
  const atEnd = index >= total - 1;

  return (
    <aside className="nodepanel">
      <div className="np-head">
        <div className="np-steprow">
          <span className="np-step">Step {index + 1} of {total}</span>
          {rendering && <span className="np-rendering">● auto-render</span>}
        </div>
        <div className="np-kindrow">
          <span className="np-kind" style={{ color, borderColor: `${color}55`, background: `${color}1a` }}>
            {node.kind}
          </span>
          {node.relPath && <span className="np-path">{node.relPath}</span>}
        </div>
        <div className="np-title">{node.fullLabel || node.label}</div>
        {node.signature && <div className="np-sig">{node.signature}</div>}
      </div>

      <div className="np-controls">
        <div className="np-nav">
          <button className="btn icon" title="Previous node" onClick={onPrev} disabled={index <= 0}>‹</button>
          {rendering ? (
            <button
              className="btn primary np-play"
              onClick={playing ? onPauseRender : onResumeRender}
            >
              {playing ? "⏸  Pause" : "▶  Resume"}
              {speaking && <span className="speak-bars"><span /><span /><span /><span /></span>}
            </button>
          ) : (
            <button
              className="btn primary np-play"
              disabled={!canPlay}
              onClick={speaking ? onPause : onPlay}
            >
              {speaking ? "⏸  Pause" : "▶  Play"}
              {speaking && <span className="speak-bars"><span /><span /><span /><span /></span>}
            </button>
          )}
          <button className="btn icon" title="Next node" onClick={onNext} disabled={atEnd}>›</button>
        </div>

        {/* Render (auto-play) row */}
        <div className="np-render">
          {!rendering ? (
            <button className="btn np-render-btn" title="Auto-play the whole flow from the start"
              onClick={onStartRender}>
              ⏵⏵ Render — auto-tour
            </button>
          ) : (
            <>
              <button className="btn" title="Restart from the first node" onClick={onStartRender}>↺ Restart</button>
              <button className="btn" title="Exit auto-render" onClick={onStopRender}>✕ Stop</button>
            </>
          )}
        </div>
      </div>

      <div className="np-body">
        <div className="np-section-title">Description</div>
        <div className="np-desc">
          {loading
            ? "Loading the guide’s explanation…"
            : text
              ? <HighlightedText text={text} mark={speaking ? mark : null} />
              : "No description available for this node."}
        </div>

        {node.source && (
          <>
            <div className="np-section-title">Source</div>
            <pre className="code-block">{node.source}</pre>
          </>
        )}
      </div>
    </aside>
  );
}
