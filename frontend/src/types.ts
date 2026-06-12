// Shared types mirroring the backend graph document.

export type NodeKind = "package" | "module" | "class" | "function" | "method";
export type EdgeKind = "contains" | "imports" | "calls";

export interface GraphNode {
  id: string;
  label: string;
  fullLabel: string;
  kind: NodeKind;
  level: number;
  x: number;
  y: number;
  size: number;
  color: string;
  package: string | null;
  modulePath: string | null;
  relPath: string | null;
  lineno: number | null;
  endLineno: number | null;
  lineCount: number | null;
  signature: string;
  docstring: string;
  decorators: string[];
  complexity: number;
  fanIn: number;
  isEntry: boolean;
  source: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: EdgeKind;
}

export interface RepoMeta {
  name: string;
  path: string;
  fileCount: number;
  totalLines: number;
  language: string;
  parseErrors: { module: string; error: string }[];
}

export interface GraphDoc {
  repo: RepoMeta;
  entryPoints: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: {
    nodeCount: number;
    edgeCount: number;
    byKind: Record<string, number>;
  };
}

export interface TourStop {
  nodeId: string;
  reason: string;
}

export interface Tour {
  title: string;
  stops: TourStop[];
}

export interface QAResult {
  nodeId: string | null;
  answer: string;
  secondaryNodeIds: string[];
}
