# CLAUDE.md — biosciences-deepagents

## Purpose

Multi-agent system for biomedical research combining a LangGraph supervisor with 7 specialist subagents and a React chat UI. This repo is owned by the **Deep Agents Engineer** agent.

## Architecture

### Supervisor + Specialists Pattern

The system uses `create_deep_agent()` to create a **supervisor** that delegates to specialist subagents via `task()` tool calls. The supervisor has no tools itself — it only routes. Default model: `openai:gpt-4o`.

| Specialist | Phase | Tools |
|------------|-------|-------|
| `anchor_specialist` | 1 ANCHOR | `hgnc_search_genes`, `ensembl_search_genes`, `entrez_search_genes`, `uniprot_search_proteins`, `chembl_search_compounds`, `pubchem_search_compounds`, `iuphar_search_ligands`, `iuphar_search_targets`, `wikipathways_search_pathways`, `clinicaltrials_search_trials`, `query_pubmed`, `think_tool` |
| `enrichment_specialist` | 2 ENRICH | `hgnc_get_gene`, `ensembl_get_gene`, `ensembl_get_transcript`, `entrez_get_gene`, `entrez_get_pubmed_links`, `uniprot_search_proteins`, `uniprot_get_protein`, `chembl_get_compound`, `chembl_get_compounds_batch`, `pubchem_get_compound`, `iuphar_get_ligand`, `iuphar_get_target`, `opentargets_get_associations`, `query_pubmed`, `think_tool` |
| `expansion_specialist` | 3 EXPAND | `string_search_proteins`, `string_get_interactions`, `string_get_network_image_url`, `wikipathways_get_pathways_for_gene`, `wikipathways_get_pathway_components`, `wikipathways_get_pathway`, `biogrid_search_genes`, `biogrid_get_interactions`, `think_tool` |
| `traversal_drugs_specialist` | 4a TRAVERSE_DRUGS | `chembl_search_compounds`, `chembl_get_compound`, `pubchem_search_compounds`, `pubchem_get_compound`, `iuphar_search_ligands`, `iuphar_get_ligand`, `opentargets_search_targets`, `opentargets_get_target`, `opentargets_get_associations`, `query_api_direct`, `think_tool` |
| `traversal_trials_specialist` | 4b TRAVERSE_TRIALS | `clinicaltrials_search_trials`, `clinicaltrials_get_trial`, `clinicaltrials_get_trial_locations`, `query_api_direct`, `think_tool` |
| `validation_specialist` | 5 VALIDATE | `clinicaltrials_get_trial`, `pubchem_get_compound`, `chembl_get_compound`, `ensembl_get_gene`, `query_pubmed`, `think_tool` |
| `persistence_specialist` | 6 PERSIST | `persist_to_graphiti` |

### Directory Layout

```
biosciences-deepagents/
├── apps/
│   ├── api/              # Python LangGraph backend
│   │   ├── biosciences.py    # Supervisor + 7 specialists, create_biosciences_graph()
│   │   └── shared/
│   │       ├── mcp.py        # HTTPMCPClient + StdioMCPClient + biosciences alias tools
│   │       ├── tools.py      # think_tool, query_api_direct helpers
│   │       └── prompts.py    # System prompts for supervisor + specialists
│   └── web/              # React chat UI (Next.js + Turbopack)
│       └── src/
│           ├── app/hooks/useChat.ts
│           └── providers/
├── .deepagents/          # Runtime knowledge root (skills + agent memory)
│   ├── AGENTS.md         # Agent memory / team definitions
│   ├── skills/           # SpecKit skill directories (9 skills)
│   └── workspace/        # Ephemeral thread-scoped state
├── langgraph.json        # Graph entry points
└── .mcp.json             # MCP server registry
```

### MCP Tool Wrappers

| Tool / Group | Connection | Purpose |
|--------------|------------|---------|
| `hgnc_*`, `ensembl_*`, `entrez_*`, `uniprot_*`, `string_*`, `biogrid_*`, `chembl_*`, `pubchem_*`, `iuphar_*`, `opentargets_*`, `wikipathways_*`, `clinicaltrials_*` | HTTP → `https://biosciences-mcp.fastmcp.app/mcp` (auth: `BIOSCIENCES_API_KEY`) | 33 individual alias tools covering all 12 life sciences MCP servers |
| `query_pubmed` | Stdio → `npx @cyanheads/pubmed-mcp-server` | PubMed articles |
| `query_langchain_docs` | HTTP → `https://docs.langchain.com/mcp` | LangChain / LangGraph / DeepAgents docs |
| `query_api_direct` | Direct HTTP (httpx) | Fallback for direct API calls |
| `persist_to_graphiti` | HTTP → `GRAPHITI_MCP_URL` (default: `http://localhost:8000/mcp`) | Knowledge graph persistence via local Graphiti server |

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
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
BIOSCIENCES_API_KEY=...    # Bearer token for https://biosciences-mcp.fastmcp.app/mcp (REQUIRED)
BIOSCIENCES_MCP_URL=https://biosciences-mcp.fastmcp.app/mcp  # FastMCP Cloud endpoint
GRAPHITI_MCP_URL=http://localhost:8000/mcp                    # Local Graphiti server (biosciences-memory)
DOCS_MCP_URL=https://docs.langchain.com/mcp                   # LangChain docs MCP
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
