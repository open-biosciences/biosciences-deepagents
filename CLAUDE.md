# CLAUDE.md — biosciences-deepagents

## Purpose

Multi-agent system for biomedical research combining a LangGraph supervisor with 7 specialist subagents and a React chat UI. This repo is owned by the **Deep Agents Engineer** agent.

## Architecture

### Supervisor + Specialists Pattern

The system uses `create_deep_agent()` to create a **supervisor** that delegates to specialist subagents via `task()` tool calls. The supervisor has no tools itself — it only routes. Default model: `openai:gpt-4o`.

| Specialist | Phase | Tools |
|------------|-------|-------|
| `anchor_specialist` | 1 ANCHOR | `query_lifesciences`, `query_pubmed`, `think_tool` |
| `enrichment_specialist` | 2 ENRICH | `query_lifesciences`, `query_pubmed`, `think_tool` |
| `expansion_specialist` | 3 EXPAND | `query_lifesciences`, `think_tool` |
| `traversal_drugs_specialist` | 4a TRAVERSE_DRUGS | `query_lifesciences`, `query_api_direct`, `think_tool` |
| `traversal_trials_specialist` | 4b TRAVERSE_TRIALS | `query_lifesciences`, `query_api_direct`, `think_tool` |
| `validation_specialist` | 5 VALIDATE | `query_lifesciences`, `query_pubmed`, `think_tool` |
| `persistence_specialist` | 6 PERSIST | (formats and summarizes) |

### Directory Layout (post-migration)

```
biosciences-deepagents/
├── src/
│   ├── graphs/           # LangGraph agent definitions
│   │   └── lifesciences.py
│   └── shared/
│       ├── mcp.py        # HTTPMCPClient + StdioMCPClient + tool wrappers
│       ├── tools.py      # tavily_search, fetch_webpage_content, think_tool
│       └── prompts.py    # System prompts for supervisor + specialists
├── apps/
│   └── web/              # React chat UI (Next.js + Turbopack)
│       └── src/
│           ├── app/hooks/useChat.ts
│           └── providers/
├── langgraph.json        # Graph entry points
└── .mcp.json             # MCP server registry
```

### MCP Tool Wrappers

| Tool | Connection | Purpose |
|------|------------|---------|
| `query_lifesciences` | HTTP → gateway | All 12 life sciences MCP servers |
| `query_pubmed` | Stdio → `npx @cyanheads/pubmed-mcp-server` | PubMed articles |
| `query_langchain_docs` | HTTP → `docs.langchain.com/mcp` | LangChain docs |
| `query_api_direct` | Direct HTTP | Fallback for direct API calls |
| `persist_to_graphiti` | HTTP → `localhost:8000/mcp` | Knowledge graph persistence |

## Development Commands

### Backend (Python)
```bash
uv sync                    # Install dependencies
uv run langgraph dev       # Start backend on :2024
fuser -k 2024/tcp          # Kill port if in use
```

### Frontend (React)
```bash
cd apps/web
yarn install               # Install dependencies
yarn dev                   # Dev server on :3000
yarn build                 # Production build
yarn lint                  # ESLint
yarn format                # Prettier
```

## Environment Variables

```bash
NEO4J_URI=...
NEO4J_USER=...
NEO4J_PASSWORD=...
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=...
BIOGRID_API_KEY=...
NCBI_API_KEY=...
OPENAI_API_KEY=...
TAVILY_API_KEY=...         # Loaded at runtime
ANTHROPIC_API_KEY=...      # Loaded at runtime
```

## API Reliability Notes

- **ChEMBL** frequently returns 500 errors — use Open Targets `knownDrugs` GraphQL as fallback
- **HGNC** is fastest/most reliable for gene resolution — always start ANCHOR here
- **STRING** batch queries return protein names; single queries don't
- **Open Targets GraphQL** requires explicit `index: 0` in pagination
- **Rate limits**: STRING 1 req/s, ChEMBL 0.5s, PubMed 0.34s, BioGrid 0.5s, Open Targets 0.2s

## Dependencies

- **Upstream**: `biosciences-mcp` (API tools via gateway), `biosciences-architecture` (Fuzzy-to-Fact compliance)
- **Downstream**: `biosciences-memory` (PERSIST phase writes to graph)

## Conventions

- Python: Type hints (TypedDict, Annotated), async/await, docstrings on tools (`parse_docstring=True`)
- TypeScript: `"use client"` directives, hook-based state, path aliasing (`@/*`)
- MCP tool timeouts vary: 120s for ChEMBL, 60s for PubMed, 30s default

## Pre-Migration Source

Until Wave 3 migration: `/home/donbr/ai2026/lifesciences-deepagents-worktrees/deepagents-0312-upgrade-spike/`
