# Lifesciences Global Runtime Contract

Use skills in `.deepagents/skills/` for phase-specific instructions.
This file defines global invariants that apply across supervisor and specialists.

## Responsibility Boundaries
- `apps/api/biosciences.py` owns orchestration mechanics:
  - subagent registration and naming
  - phase routing order
  - tool availability per subagent
  - runtime middleware and hard guards
- `.deepagents/AGENTS.md` owns cross-cutting quality rules only.
- Do not redefine subagent lists or routing internals here.

## Tool and Retrieval Discipline
- Prefer direct MCP alias tools over generic wrappers.
- Use `query_api_direct` only as an explicit fallback path.
- Enforce LOCATE -> RETRIEVE:
  - run search/LOCATE before strict `get_*` calls
  - use strict `get_*` only with canonical IDs from LOCATE or trusted prior phase outputs
  - if no canonical ID can be resolved, mark unresolved and continue

## Identifier and Data Quality
- Preserve canonical CURIE/ID formats end-to-end.
- Do not invent identifiers, trial IDs, mechanisms, or citations.
- When uncertain, return partial results with clear uncertainty markers.

## File and Artifact Policy
- Use relative paths only under `workspace/`.
- Phase artifacts must be valid JSON.
- Final artifacts are required:
  - `workspace/graph.json`
  - `workspace/report.md`
- Graphiti persistence is optional and non-blocking.

## Stop and Retry Behavior
- Avoid repeated read/write/edit loops.
- On write failure, do at most one corrective attempt.
- If still failing, return partial output and stop cleanly.

## Output Expectations
- Keep outputs grounded, concise, and source-aware.
- Prioritize validated mechanisms and evidence over speculative breadth.
