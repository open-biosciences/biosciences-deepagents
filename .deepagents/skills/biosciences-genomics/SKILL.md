---
name: biosciences-genomics
description: "Queries genomic databases (Ensembl, NCBI, HGNC) via MCP tools for gene lookup, variant annotation, orthology, and cross-database ID resolution. Falls back to query_api_direct when MCP is unavailable. This skill should be used when the user asks to \"annotate variants\", \"find orthologs\", \"map gene IDs\", \"analyze linkage disequilibrium\", or mentions gene symbols, ENSG IDs, HGNC identifiers, VEP annotation, LD analysis, HGVS notation, or DNA sequences."
---


## Runtime constraints (DeepAgents)
- Prefer MCP tools first; use query_api_direct for HTTP fallbacks.
- Do not run shell curl in this runtime.
- Use relative file paths under `workspace/`.
- Graphiti persistence is optional/best-effort.

# Genomics API Skills

Query genomic databases via MCP tools (primary) or query_api_direct (fallback).

## Grounding Rule

All gene names, IDs, and annotations MUST come from API results. Do NOT provide gene information from training knowledge. If a query returns no results, report "No results found."

## MCP Token Budgeting (`slim` Parameter)

All MCP tools in this skill support a `slim` parameter for token-efficient queries:

**When to use `slim=true`:**
- LOCATE phase: Fast candidate lists (returns ~20 tokens/entity vs ~115-300 tokens)
- Batch operations: Resolving multiple entities in a single turn
- Exploration: Quick overviews without full metadata

**When to use `slim=false` (default):**
- RETRIEVE phase: Need full metadata with cross-references
- Validation: Verifying detailed properties
- Graph persistence: Collecting complete entity records

**Example:**
```
# LOCATE: Find top 10 gene candidates (slim=true for speed)
Call `hgnc_search_genes` with: {"query": "TNF", "slim": true, "page_size": 10}
→ Returns minimal fields: ID, symbol, name only (~20 tokens each)

# RETRIEVE: Get full record for validation (slim=false, default)
Call `hgnc_get_gene` with: {"hgnc_id": "HGNC:11892"}
→ Returns complete metadata with cross-references (~115 tokens)
```

**Impact:** Using `slim=true` during LOCATE enables 5-10x more entities per LLM turn without context overflow.

**Reference:** This token budgeting pattern is detailed in `reference/prior-art-api-patterns.md` (Section 7.1).

## LOCATE → RETRIEVE Patterns

### Gene Resolution (HGNC — Start Here)

**LOCATE**: Search for gene by symbol or name

PRIMARY (MCP tool):
```
Call `hgnc_search_genes` with: {"query": "TP53"}
→ Returns candidates with HGNC IDs, symbols, names
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://rest.genenames.org/search/symbol/TP53", method="GET")  # runtime fallback (no shell)
```

**RETRIEVE**: Fetch full record by HGNC ID

PRIMARY (MCP tool):
```
Call `hgnc_get_gene` with: {"hgnc_id": "HGNC:11998"}
→ Returns: symbol, name, cross-references (UniProt, Ensembl, Entrez)
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://rest.genenames.org/fetch/hgnc_id/11998", method="GET")  # runtime fallback (no shell)
```

### Gene Metadata (Ensembl)

**LOCATE**: Resolve symbol to Ensembl ID

PRIMARY (MCP tool):
```
Call `ensembl_search_genes` with: {"query": "TP53", "species": "homo_sapiens"}
→ Returns Ensembl gene ID (ENSG...)
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://rest.ensembl.org/lookup/symbol/homo_sapiens/TP53?content-type=application/json", method="GET")  # runtime fallback (no shell)
```

**RETRIEVE**: Get full gene metadata by Ensembl ID

PRIMARY (MCP tool):
```
Call `ensembl_get_gene` with: {"ensembl_id": "ENSG00000141510"}
→ Returns: biotype, description, location, transcripts
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://rest.ensembl.org/lookup/id/ENSG00000141510?expand=1&content-type=application/json", method="GET")  # runtime fallback (no shell)
```

### Variant Annotation (Ensembl VEP)

No MCP tool — use query_api_direct directly:

**LOCATE**: Annotate variant by rsID
```bash
query_api_direct(url="https://rest.ensembl.org/vep/human/id/rs56116432?content-type=application/json", method="GET")  # runtime fallback (no shell)
```

**RETRIEVE**: Annotate by HGVS notation (batch via POST)
```bash
query_api_direct(url="https://rest.ensembl.org/vep/human/hgvs", method="GET")  # runtime fallback (no shell)
```

### Orthology (Ensembl)

No MCP tool — use query_api_direct directly:

**LOCATE + RETRIEVE** (single call returns both):
```bash
query_api_direct(url="https://rest.ensembl.org/homology/id/human/ENSG00000141510?type=orthologues&content-type=application/json", method="GET")  # runtime fallback (no shell)
```

### Cross-Database ID Resolution (Ensembl xrefs)

No MCP tool — use query_api_direct directly:

**RETRIEVE**: Get all cross-references for a gene (useful for verification)
```bash
query_api_direct(url="https://rest.ensembl.org/xrefs/id/ENSG00000141510?content-type=application/json", method="GET")  # runtime fallback (no shell)
```

### Linkage Disequilibrium (Ensembl)

No MCP tool — use query_api_direct directly:

**RETRIEVE**: LD between two variants
```bash
query_api_direct(url="https://rest.ensembl.org/ld/human/pairwise/rs56116432/rs1042522?population_name=1000GENOMES:phase_3:EUR&content-type=application/json", method="GET")  # runtime fallback (no shell)
```

**RETRIEVE**: LD in genomic region
```bash
query_api_direct(url="https://rest.ensembl.org/ld/human/region/17:7668421..7687490/1000GENOMES:phase_3:EUR?content-type=application/json", method="GET")  # runtime fallback (no shell)
```

### NCBI E-utilities: Gene Search & Links

**LOCATE**: Search for gene

PRIMARY (MCP tool):
```
Call `entrez_search_genes` with: {"query": "TP53", "organism": "human"}
→ Returns Entrez gene IDs
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gene&term=TP53[sym]+AND+human[orgn]&retmode=json", method="GET")  # runtime fallback (no shell)
```

**RETRIEVE**: Get gene summary by Entrez ID

PRIMARY (MCP tool):
```
Call `entrez_get_gene` with: {"gene_id": "7157"}
→ Returns gene name, description, chromosome location
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id=7157&retmode=json", method="GET")  # runtime fallback (no shell)
```

**RETRIEVE**: Link gene to PubMed articles

PRIMARY (MCP tool):
```
Call `entrez_get_pubmed_links` with: {"gene_id": "7157"}
→ Returns linked PubMed article IDs
```

FALLBACK (query_api_direct):
```bash
query_api_direct(url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=gene&db=pubmed&id=7157&retmode=json", method="GET")  # runtime fallback (no shell)
```

## Quick Reference

| Task | Pattern | MCP Tool (primary) | Curl Endpoint (fallback) |
|------|---------|-------------------|--------------------------|
| Resolve gene symbol | LOCATE | `hgnc_search_genes` | HGNC `/search/{symbol}` |
| Get gene metadata | RETRIEVE | `hgnc_get_gene` | HGNC `/fetch/hgnc_id/{id}` |
| Get Ensembl gene | RETRIEVE | `ensembl_get_gene` | Ensembl `/lookup/id/{ENSG}` |
| Annotate variant | LOCATE | (query_api_direct fallback) | Ensembl VEP `/vep/:species/hgvs` |
| Find orthologs | RETRIEVE | (query_api_direct fallback) | Ensembl `/homology/id/:species/:id` |
| Cross-reference IDs | RETRIEVE | (query_api_direct fallback) | Ensembl `/xrefs/id/{ENSG}` |
| Search NCBI Gene | LOCATE | `entrez_search_genes` | E-utilities `/esearch.fcgi?db=gene` |
| Link gene→PubMed | RETRIEVE | `entrez_get_pubmed_links` | E-utilities `/elink.fcgi?dbfrom=gene&db=pubmed` |

## ID Format Reference

| Database | API Argument (bare) | Graph CURIE | Example |
|----------|---------------------|-------------|---------|
| HGNC | `HGNC:11998` | `HGNC:11998` | (Same — HGNC includes prefix) |
| Ensembl | `ENSG00000141510` | `ENSG00000141510` | (No CURIE prefix needed) |
| NCBI/Entrez | `7157` | `NCBIGene:7157` | Bare numeric for API |

## Rate Limits

| API | Limit | Notes |
|-----|-------|-------|
| HGNC | 10 req/s | No auth required |
| Ensembl | 15 req/s | No auth required |
| NCBI | 3 req/s | 10 req/s with NCBI_API_KEY |

## Query Best Practices

### Human-Centric Defaults
- **Filter to human by default** unless performing comparative genomics
- Use `human[orgn]` in NCBI searches, `homo_sapiens` for Ensembl
- Only omit organism filter when explicitly comparing across species (e.g., ortholog analysis)

### Efficient Querying
- Use `page_size=10` for exploration
- Use cross-reference endpoints to resolve IDs rather than multiple searches
- Prefer Ensembl IDs (ENSG*) for programmatic access — most APIs accept them

## See Also

- **biosciences-graph-builder**: Orchestrator for full Fuzzy-to-Fact protocol
- **biosciences-proteomics**: UniProt, STRING, BioGRID protein endpoints
