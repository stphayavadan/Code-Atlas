// AtlasMap: the codebase as ONE connected, readable flow.
//
// We ignore the backend's scattered world coordinates and lay the path out
// ourselves: an ordered chain of nodes (the AI tour = the end-to-end flow) on a
// gently tilted plane, evenly spaced with SHORT links, like a metro map. Every
// node connects to the next, start to finish — so the user always sees how the
// flow passes through the codebase.
//
// The camera starts zoomed in on node 0 (the entry point) and eases from node
// to node as the user presses Prev / Next (or clicks a node). They can also
// drag to pan and scroll to zoom freely.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphNode } from "../types";

const TILT = 16;               // gentle plane tilt
const MIN_ZOOM = 0.15;
const MAX_ZOOM = 3.0;

// Path layout (short links, even spacing) — a vertical serpentine.
const STEP_Y = 200;            // vertical gap between consecutive nodes
const AMP_X = 150;             // horizontal sway
const FREQ = 0.8;              // sway frequency

interface Cam { x: number; y: number; zoom: number; }

interface Props {
  path: GraphNode[];           // ordered, deduped chain of nodes
  current: number;             // index of the focused node
  onSelect: (index: number) => void;
}

const KIND_COLOR: Record<string, string> = {
  package: "#7c5cff",
  module: "#22d3ee",
  class: "#f59e0b",
  function: "#34d399",
  method: "#f472b6",
};

export function AtlasMap({ path, current, onSelect }: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [cam, setCam] = useState<Cam>({ x: 0, y: 0, zoom: 1 });
  const camRef = useRef(cam);
  camRef.current = cam;

  // ---- our own clean layout: evenly spaced serpentine ----
  const pos = useMemo(
    () => path.map((_, i) => ({ x: AMP_X * Math.sin(i * FREQ), y: i * STEP_Y })),
    [path]
  );

  const bounds = useMemo(() => {
    if (pos.length === 0) return { minX: 0, minY: 0, w: 1, h: 1 };
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of pos) {
      minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y);
    }
    const pad = 120;
    return { minX: minX - pad, minY: minY - pad, w: (maxX - minX) + pad * 2, h: (maxY - minY) + pad * 2 };
  }, [pos]);

  // ---- ease the camera to a node ----
  const tweenRef = useRef<number | null>(null);
  const easeTo = useCallback((x: number, y: number, zoom?: number) => {
    const from = { ...camRef.current };
    const to = { x, y, zoom: zoom ?? from.zoom };
    const start = performance.now();
    const DUR = 600;
    if (tweenRef.current) cancelAnimationFrame(tweenRef.current);
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / DUR);
      const e = 1 - Math.pow(1 - k, 3);
      setCam({
        x: from.x + (to.x - from.x) * e,
        y: from.y + (to.y - from.y) * e,
        zoom: from.zoom + (to.zoom - from.zoom) * e,
      });
      if (k < 1) tweenRef.current = requestAnimationFrame(step);
    };
    tweenRef.current = requestAnimationFrame(step);
  }, []);

  // Follow the current node whenever it changes.
  useEffect(() => {
    const p = pos[current];
    if (!p) return;
    // First placement (no prior tween): snap zoomed-in; afterwards, glide.
    const z = Math.max(0.9, camRef.current.zoom);
    easeTo(p.x, p.y, z);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, pos]);

  // ---- pan (drag) ----
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.current.moved = true;
    drag.current.x = e.clientX; drag.current.y = e.clientY;
    setCam((c) => ({ ...c, x: c.x - dx / c.zoom, y: c.y - dy / c.zoom }));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
    drag.current = null;
  };

  // ---- zoom (wheel) anchored at cursor ----
  const onWheel = (e: React.WheelEvent) => {
    const vp = viewportRef.current;
    if (!vp) return;
    const rect = vp.getBoundingClientRect();
    const mx = e.clientX - rect.left - rect.width / 2;
    const my = e.clientY - rect.top - rect.height / 2;
    setCam((c) => {
      const z2 = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, c.zoom * Math.exp(-e.deltaY * 0.0012)));
      const wx = c.x + mx / c.zoom, wy = c.y + my / c.zoom;
      return { x: wx - mx / z2, y: wy - my / z2, zoom: z2 };
    });
  };
  const zoomBy = (f: number) =>
    setCam((c) => ({ ...c, zoom: Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, c.zoom * f)) }));

  // The scene element is positioned at the viewport center (left/top:50% in CSS),
  // so its origin IS screen-center. We rotate+scale about it, then translate so
  // the focused node sits on the rotation axis => exactly centered.
  const sceneTransform =
    `rotateX(${TILT}deg) scale(${cam.zoom}) translate(${-cam.x}px, ${-cam.y}px)`;

  const { minX, minY, w, h } = bounds;

  return (
    <div
      ref={viewportRef}
      className="atlas-viewport"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      onWheel={onWheel}
    >
      <div className="atlas-floor" />
      <div className="atlas-scene" style={{ transform: sceneTransform }}>
        {/* The connecting flow: a line through every node, start to end. */}
        <svg
          className="atlas-edges"
          style={{ left: minX, top: minY, width: w, height: h }}
          viewBox={`0 0 ${w} ${h}`}
        >
          {pos.slice(0, -1).map((p, i) => {
            const q = pos[i + 1];
            const active = i < current; // already-traversed segments glow
            return (
              <line
                key={i}
                x1={p.x - minX} y1={p.y - minY}
                x2={q.x - minX} y2={q.y - minY}
                className={`atlas-edge ${active ? "active" : ""}`}
              />
            );
          })}
        </svg>

        {/* Nodes */}
        {path.map((n, i) => {
          const p = pos[i];
          const color = KIND_COLOR[n.kind] ?? "#22d3ee";
          const isCurrent = i === current;
          const d = isCurrent ? 30 : 20;
          return (
            <div
              key={`${n.id}#${i}`}
              className={`atlas-node ${isCurrent ? "current" : ""}`}
              style={{ left: p.x, top: p.y }}
              onClick={(e) => {
                e.stopPropagation();
                if (!drag.current?.moved) onSelect(i);
              }}
            >
              <div
                className="atlas-orb"
                style={{
                  width: d, height: d,
                  background: `radial-gradient(circle at 35% 30%, #fff, ${color} 55%, ${color}00 88%)`,
                  boxShadow: `0 0 ${d * 0.6}px ${color}, 0 0 ${d * 1.3}px ${color}66`,
                  borderColor: color,
                }}
              />
              <div className="atlas-label" style={{ borderColor: `${color}55` }}>
                <div className="atlas-label-name">{n.label}</div>
                <div className="atlas-label-kind" style={{ color }}>
                  {n.kind}{n.relPath ? ` · ${n.relPath}` : ""}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Zoom controls */}
      <div className="atlas-zoom">
        <button className="btn icon" title="Zoom in" onClick={() => zoomBy(1.3)}>＋</button>
        <button className="btn icon" title="Zoom out" onClick={() => zoomBy(1 / 1.3)}>－</button>
      </div>
    </div>
  );
}
