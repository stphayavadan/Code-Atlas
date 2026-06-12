// Thin client over the FastAPI backend. All calls are same-origin (Vite proxies
// /api to the backend in dev).
import type { GraphDoc, Tour, QAResult } from "./types";

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface BuildStatus {
  status: "idle" | "cloning" | "parsing" | "tour" | "narrating" | "ready" | "error";
  message: string;
  error: string | null;
  done: number;
  total: number;
  percent: number;
  repo: { name: string; fileCount: number; totalLines: number } | null;
  stats: { nodeCount: number; edgeCount: number } | null;
  ready: boolean;
}

// Kick off a build for a repo URL + PAT (+ optional branch).
export async function startBuild(
  url: string,
  pat: string,
  branch: string
): Promise<BuildStatus> {
  const res = await fetch("/api/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, pat, branch: branch || null }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `/api/build -> ${res.status}`);
  }
  return res.json() as Promise<BuildStatus>;
}

export async function fetchBuildStatus(): Promise<BuildStatus> {
  return getJSON<BuildStatus>("/api/build/status");
}

export async function fetchGraph(): Promise<GraphDoc> {
  return getJSON<GraphDoc>("/api/graph");
}

export async function fetchOverview(): Promise<string> {
  const { text } = await getJSON<{ text: string }>("/api/overview");
  return text;
}

export async function fetchTour(): Promise<Tour> {
  return getJSON<Tour>("/api/tour");
}

export async function fetchNarration(nodeId: string): Promise<string> {
  const { text } = await getJSON<{ nodeId: string; text: string }>(
    `/api/narrate/${encodeURIComponent(nodeId)}`
  );
  return text;
}

export async function askQuestion(
  question: string,
  history: { role: string; content: string }[]
): Promise<QAResult> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!res.ok) throw new Error(`/api/ask -> ${res.status}`);
  return res.json() as Promise<QAResult>;
}
