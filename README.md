# biosciences-deepagents

LangGraph multi-agent system using a supervisor pattern with 7 specialist subagents and a streaming React chat UI. Part of the [Open Biosciences](https://github.com/open-biosciences) platform.

## Migration Status

**Wave 3 (Orchestration) — Not Started.**

Content is pending migration from the predecessor `lifesciences-deepagents` repository. Wave 3 begins after Wave 2 (biosciences-mcp) is confirmed operational. See [biosciences-program](https://github.com/open-biosciences/biosciences-program) for migration tracking.

## What This Repo Will Contain

### LangGraph Supervisor + 7 Specialist Subagents

The system uses `create_deep_agent()` to instantiate a **supervisor** that delegates to specialist subagents via `task()` calls. The supervisor carries no tools — it only routes. Default model: `openai:gpt-4o`.

Each specialist handles one phase of the **Fuzzy-to-Fact** protocol, with access only to the tools relevant to its phase:

| # | Specialist | Phase | Primary Databases |
|---|-----------|-------|-------------------|
| 1 | `anchor_specialist` | ANCHOR — resolve seed entities to CURIEs | HGNC, ChEMBL, ClinicalTrials.gov |
| 2 | `enrichment_specialist` | ENRICH — fetch metadata and annotations | UniProt, HGNC, ChEMBL |
| 3 | `expansion_specialist` | EXPAND — discover interactions and pathways | STRING, WikiPathways, BioGRID |
| 4 | `traversal_drugs_specialist` | TRAVERSE (Drugs) — find drug candidates | ChEMBL, Open Targets GraphQL |
| 5 | `traversal_trials_specialist` | TRAVERSE (Trials) — find clinical trials | ClinicalTrials.gov v2 |
| 6 | `validation_specialist` | VALIDATE — cross-source fact verification | ClinicalTrials.gov, ChEMBL, PubMed |
| 7 | `persistence_specialist` | PERSIST — save validated graph | Graphiti / Neo4j |

### Think-Act-Observe Reasoning

Every specialist uses a `think_tool` that forces deliberate reflection after each API call before proceeding. This reduces hallucination and ensures each datum is evaluated against prior findings before it enters the growing knowledge graph.

### Streaming React Chat UI

A full-stack React application (`apps/web/`) built on Next.js 16, React 19, TypeScript, Tailwind CSS, and Radix UI. Features:

- Real-time subagent visualization — which specialist is active, which tools are firing, intermediate results
- Tool approval interrupts — checkpoint/resume support for human-in-the-loop review
- Thread-persistent sessions via URL query state

### MCP Tool Wrappers

All external API access flows through tool wrappers in `shared/mcp.py` that call the [biosciences-mcp](https://github.com/open-biosciences/biosciences-mcp) gateway (12 servers, 34+ tools). Per-service rate limits are enforced: STRING 1 req/s, ChEMBL 0.5s, PubMed 0.34s, BioGRID 0.5s.

## Example: Drug Repurposing for FOP

> "What drugs target the ACVR1 pathway in fibrodysplasia ossificans progressiva (FOP)?"

The 7-phase protocol resolves this question as follows:

1. **ANCHOR**: `anchor_specialist` queries HGNC and resolves "ACVR1" to `HGNC:171`
2. **ENRICH**: `enrichment_specialist` fetches UniProt entry `Q04771` and Ensembl ID `ENSG00000115170`
3. **EXPAND**: `expansion_specialist` finds BMPR2, SMAD1, SMAD5 interactions via STRING; BMP signaling pathway via WikiPathways
4. **TRAVERSE (Drugs)**: `traversal_drugs_specialist` queries Open Targets via `ENSG00000115170` and finds **Palovarotene** (Phase 3) and Garetosmab
5. **TRAVERSE (Trials)**: `traversal_trials_specialist` searches ClinicalTrials.gov and finds **NCT03312634** (MOVE trial, Phase 3, Ipsen)
6. **VALIDATE**: `validation_specialist` confirms NCT03312634 exists; marks each fact VALIDATED against primary sources
7. **PERSIST**: `persistence_specialist` saves nodes (ACVR1, Palovarotene, FOP) and edges (TARGETS, TREATS, REGISTERED_FOR) to Graphiti with full provenance

Result: `HGNC:171` → `ENSG00000115170` → Palovarotene → `NCT03312634` — every link backed by a database record.

## Dependencies

| Direction | Repository | Relationship |
|-----------|------------|--------------|
| Upstream | [biosciences-mcp](https://github.com/open-biosciences/biosciences-mcp) | Agents consume MCP tools via gateway (12 servers) |
| Upstream | [biosciences-memory](https://github.com/open-biosciences/biosciences-memory) | PERSIST phase writes validated graph to Graphiti/Neo4j |
| Reference | [biosciences-architecture](https://github.com/open-biosciences/biosciences-architecture) | Fuzzy-to-Fact protocol defined in ADR-001 |

## Agent Ownership

Owned by the **Deep Agents Engineer** (Agent 5). See [AGENTS.md](https://github.com/open-biosciences/biosciences-program/blob/main/AGENTS.md) for full team definitions.

## Related Repositories

- [biosciences-mcp](https://github.com/open-biosciences/biosciences-mcp) — 12 FastMCP API servers (MCP tool layer)
- [biosciences-memory](https://github.com/open-biosciences/biosciences-memory) — Graphiti/Neo4j knowledge graph layer
- [biosciences-temporal](https://github.com/open-biosciences/biosciences-temporal) — PydanticAI + Temporal.io durable workflow alternative
- [biosciences-program](https://github.com/open-biosciences/biosciences-program) — Migration tracking and cross-repo coordination

## License

MIT
