# biosciences-deepagents

LangGraph multi-agent system using a supervisor pattern with 7 specialist subagents and a React chat UI. Part of the [Open Biosciences](https://github.com/open-biosciences) platform.

## Status

**Pending Wave 3 (Orchestration) migration.** Content is being migrated from the predecessor `lifesciences-deepagents` repository.

## What's Coming

After migration, this repository will contain:

- **LangGraph supervisor** orchestrating multi-step biosciences research queries
- **7 specialist subagents**
  - Anchor -- resolve initial entities
  - Enrichment -- gather detailed annotations
  - Expansion -- discover related entities
  - Traversal-Drugs -- drug/compound traversal
  - Traversal-Trials -- clinical trial traversal
  - Validation -- cross-source verification
  - Persistence -- write results to knowledge graph
- **MCP tool wrappers** bridging agents to the 12 MCP servers
- **System prompts** defining behavior for each agent
- **React chat UI** (`apps/web/`) for interactive research sessions

## Agent Ownership

Maintained by the **Deep Agents Engineer** agent (Agent 5). See [AGENTS.md](../biosciences-program/AGENTS.md) for full team definitions.

## Dependencies

| Direction | Repository | Relationship |
|-----------|------------|--------------|
| Upstream | biosciences-mcp | Agents consume MCP tools for data access |
| Upstream | biosciences-memory | PERSIST phase writes to knowledge graph |

## Related Repositories

- [biosciences-mcp](https://github.com/open-biosciences/biosciences-mcp) -- FastMCP API servers
- [biosciences-memory](https://github.com/open-biosciences/biosciences-memory) -- Knowledge graph layer
- [biosciences-temporal](https://github.com/open-biosciences/biosciences-temporal) -- Temporal durable workflows

## License

MIT
