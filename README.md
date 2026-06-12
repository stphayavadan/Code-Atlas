# Codebase Atlas — A Cinematic Guided Tour of Any Codebase

> "Google Maps for a codebase." Point it at a Python repository and it builds a
> living, zoomable map of the code, then an AI guide narrates a tour through it —
> and you can ask questions and have the camera fly you to the answer.

![overview](docs/overview.png)

## What it does

- **Parses** a Python repo into a graph of packages → modules → classes →
  functions/methods, with import and call edges (native `ast` + `networkx`).
- **Renders** it as a dark, cinematic **WebGL map** (Sigma.js) with **semantic
  zoom**: pull back to see packages as glowing continents; zoom in to reveal
  files, then classes, then individual functions — Google-Maps style.
- **Narrates** with Azure Foundry IQ: an opening establishing shot of the whole repo, plus
  a plain-language explanation for every place on the map, spoken aloud (TTS).
- **Guides** you on an AI-designed **tour** in a sensible learning order
  (entry point → core abstractions → supporting cast), the camera gliding from
  stop to stop.
- **Answers questions**: ask "how does X work?" / "where is Y handled?" and the
  guide **flies the camera to the exact node** and explains it — a guide who
  walks you to the right room.

## Architecture

```
 Python repo
     │
     ▼  ast + networkx (deterministic, fast, cached)
 graph.json  ──────────────►  FastAPI backend  ◄────── Azure Foundry
     │                              │                   · overview narration
     │  HTTP /api/*                 │                   · per-node narration
     ▼                              ▼                   · tour sequencing
 React + Sigma.js (WebGL)     narration / tour /        · Q&A navigation
 · semantic-zoom map          Q&A endpoints
 · camera fly-to (eased)
 · tour playback + TTS
 · Q&A chat that drives the camera
```

The structural half (parse → graph → layout) is **LLM-free**: instant, reliable,
and cached. Azure Foundry is used only for *narrative* — explaining, ordering,
and navigating — never for parsing. Each request carries only the relevant
slice of the graph, so it stays fast and on-topic.

### Azure Foundry IQ access

Credentials are loaded from `backend/.env` or the environment. The backend uses
`azure-ai-openai` to call Azure Foundry IQ chat models via
`AZURE_FOUNDRY_ENDPOINT` and `AZURE_FOUNDRY_KEY`.

| Role  | Model                                  | Used for                          |
|-------|----------------------------------------|-----------------------------------|
| FAST  | `gpt-35-turbo-foundry`                 | per-node + overview narration, Q&A |
| SMART | `gpt-4o-foundry` or other Foundry model | tour-sequence reasoning            |

All secrets stay server-side; the browser never sees a key.

## Running it

Two processes. **Backend** (port 8077 — 8000 is blocked by Windows socket
permissions on this host):

```bash
cd backend
pip install -r requirements.txt
REPO_PATH='C:\path\to\any\python\repo' python -m uvicorn main:app --host 127.0.0.1 --port 8077
# or: ./run-backend.sh

### Backend environment

Copy `backend/.env.example` to `backend/.env` and set the Azure Foundry variables there:
- `AZURE_FOUNDRY_ENDPOINT`
- `AZURE_FOUNDRY_KEY`
- `AZURE_FOUNDRY_CHAT_MODEL`
```

**Frontend** (Vite dev server on 5173, proxies /api → 8077):

```bash
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

Point at a different repo without restarting by POSTing to `/api/load`:

```bash
curl -X POST http://127.0.0.1:8077/api/load \
  -H 'Content-Type: application/json' \
  -d '{"path": "C:\\path\\to\\repo", "name": "My Repo"}'
```

## API

| Endpoint                | Method | Purpose                                        |
|-------------------------|--------|------------------------------------------------|
| `/api/health`           | GET    | liveness + whether a repo is loaded            |
| `/api/load`             | POST   | parse a new repo (`{path, name}`)              |
| `/api/graph`            | GET    | full graph document (nodes, edges, layout)     |
| `/api/overview`         | GET    | opening narration (cached)                     |
| `/api/narrate/{nodeId}` | GET    | per-node narration (cached)                    |
| `/api/tour`             | GET    | AI-designed tour: `{title, stops[]}` (cached)  |
| `/api/ask`              | POST   | Q&A: `{question, history}` → `{nodeId, answer}`|

## Layout / project structure

```
backend/
  parser/   ingest.py · ast_parser.py · graph_builder.py · serialize.py
  layout/   layout.py            (clustered map coordinates)
  llm/      client.py · narrate.py · tour.py · qa_agent.py
  pipeline.py · main.py          (FastAPI)
frontend/
  src/
    map/    buildGraph.ts · MapController.ts   (Sigma + semantic zoom + camera)
    hooks/  useSpeech.ts                       (TTS narration)
    components/  DetailPanel · Narration · TourDock · ChatPanel
    App.tsx · api.ts · types.ts · styles.css
```

## Notes & scope

- **Python only** by design (native `ast`, zero parsing edge cases). The graph
  schema is language-agnostic, so other languages can be added behind the same
  `/api/graph` contract.
- Narration and tour are **cached** per repo load; first tour design takes a few
  seconds (Opus), then it's instant.
- TTS uses the browser's free Web Speech API. Swap in Azure Speech for premium
  voices without touching the rest of the app.
