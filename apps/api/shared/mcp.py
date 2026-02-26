from langchain_core.tools import tool
import httpx
import json
import logging
import time
import asyncio
from collections import defaultdict
from typing import Optional, Any
import os
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter to prevent API throttling."""

    def __init__(self):
        self.last_call: dict[str, float] = defaultdict(float)
        # Seconds between calls per service
        self.limits = {
            "string": 1.0,      # STRING API: 1 req/s limit
            "chembl": 0.5,      # ChEMBL: be conservative
            "pubmed": 0.34,     # PubMed: ~3 req/s
            "entrez": 0.34,     # NCBI Entrez: 3 req/s
            "iuphar": 0.2,      # IUPHAR: fast
            "opentargets": 0.2, # OpenTargets: fast
            "pubchem": 0.5,     # PubChem: < 5 req/s
            "ensembl": 0.2,     # Ensembl: 15 req/s
            "biogrid": 0.5,     # BioGRID: 2 req/s
            "default": 0.1      # Default: 10 req/s
        }

    async def wait(self, service: str):
        """Wait if needed to respect rate limits."""
        limit = self.limits.get(service, self.limits["default"])
        elapsed = time.time() - self.last_call[service]
        if elapsed < limit:
            await asyncio.sleep(limit - elapsed)
        self.last_call[service] = time.time()

    def get_service_from_tool(self, tool_name: str) -> str:
        """Map tool name to service for rate limiting."""
        if tool_name.startswith("string_"):
            return "string"
        elif tool_name.startswith("chembl_"):
            return "chembl"
        elif tool_name.startswith("mcp_pubmed_") or tool_name.startswith("pubmed_") or tool_name in ("search_articles", "get_article_metadata", "get_full_text_article", "find_related_articles", "lookup_article_by_citation", "convert_article_ids", "get_copyright_status"):
            return "pubmed"
        elif tool_name.startswith("entrez_"):
            return "entrez"
        elif tool_name.startswith("iuphar_"):
            return "iuphar"
        elif tool_name.startswith("opentargets_"):
            return "opentargets"
        elif tool_name.startswith("pubchem_"):
            return "pubchem"
        elif tool_name.startswith("ensembl_"):
            return "ensembl"
        elif tool_name.startswith("biogrid_"):
            return "biogrid"
        return "default"


rate_limiter = RateLimiter()


class HTTPMCPClient:
    def __init__(self, base_url: str, timeout: float = 30.0, api_key: str | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def call_tool(self, tool_name: str, arguments: dict, apply_rate_limit: bool = True):
        # Apply rate limiting based on tool name
        if apply_rate_limit:
            service = rate_limiter.get_service_from_tool(tool_name)
            await rate_limiter.wait(service)

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }

        try:
            # Enable HTTP/2 as some servers (LangChain, FastMCP) prefer it
            async with httpx.AsyncClient(http2=True, verify=True, timeout=self.timeout) as client:
                response = await client.post(self.base_url, json=payload, headers=self.headers)
                response.raise_for_status()

                return self._parse_response(response.text)
        except httpx.HTTPStatusError as e:
            return f"HTTP Connection Error to MCP server: {e}"
        except Exception as e:
            return f"Error calling tool {tool_name}: {e}"

    def _parse_response(self, text: str):
        # Manual SSE Parsing attempt
        # The server might return "event: message\ndata: {...}" body even with json header
        for line in text.split('\n'):
            if line.startswith("data: "):
                json_str = line[6:].strip()
                try:
                    data = json.loads(json_str)
                    
                    # Process the JSON-RPC response
                    if "error" in data:
                        return f"Error from MCP server: {data['error']}"
                    
                    if "result" in data and "content" in data["result"]:
                        text_content = ""
                        for item in data["result"]["content"]:
                            if item.get("type") == "text":
                                text_content += item.get("text", "") + "\n"
                        return text_content.strip()
                        
                except json.JSONDecodeError:
                    continue
        
        # Fallback for standard JSON result
        try:
            data = json.loads(text)
            if "result" in data and "content" in data["result"]:
                text_content = ""
                for item in data["result"]["content"]:
                    if item.get("type") == "text":
                        text_content += item.get("text", "") + "\n"
                return text_content.strip()
        except:
            pass

        return f"No valid content found in response. Raw response start: {text[:200]}"


class StdioMCPClient:
    """MCP Client for local stdio-based servers."""
    def __init__(self, command: str, args: list[str], env: Optional[dict] = None):
        self.server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env
        )

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        try:
            async with stdio_client(self.server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    
                    # Format result to string to match HTTP client output
                    text_content = ""
                    if hasattr(result, 'content'):
                        for content in result.content:
                            if hasattr(content, 'text'):
                                text_content += content.text + "\n"
                            elif getattr(content, 'type', '') == 'image':
                                text_content += "[Image]\n"
                    return text_content.strip()
        except Exception as e:
            return f"Stdio Connection Error: {e}"

# --- Docs-LangChain MCP ---
DOCS_MCP_URL = "https://docs.langchain.com/mcp"
docs_client = HTTPMCPClient(DOCS_MCP_URL, timeout=30.0)

@tool
async def query_langchain_docs(query: str):
    """
    Search the official LangChain documentation. 
    Crucial for questions about:
    - LangChain, LangGraph, LangSmith
    - Deep Agents (the library/framework)
    - Middleware, Checkpointing, State Management
    - API references and Usage Guides
    """
    return await docs_client.call_tool("SearchDocsByLangChain", {"query": query})


# --- Biosciences FastMCP ---
BIOSCIENCES_MCP_URL = "https://biosciences-mcp.fastmcp.app/mcp"
# ChEMBL requires longer timeout (120s) as noted in documentation
# BIOSCIENCES_API_KEY loaded from .env via langgraph.json "env" setting
biosciences_client = HTTPMCPClient(
    BIOSCIENCES_MCP_URL,
    timeout=120.0,
    api_key=os.environ.get("BIOSCIENCES_API_KEY"),
)

async def _query_biosciences(
    query: str,
    tool_name: str = "clinicaltrials_search_trials",
    tool_args: Optional[dict[str, Any]] = None
):
    """
    Internal fallback helper for direct calls to the Biosciences MCP.
    Not exposed as a tool to agents; prefer explicit alias tools below.
    """
    args = tool_args if tool_args else {"query": query}
    return await biosciences_client.call_tool(tool_name, args)


async def _call_biosciences_alias(
    tool_name: str,
    query: str = "",
    tool_args: Optional[dict[str, Any]] = None,
):
    """Internal helper for direct alias tools used by runtime skills."""
    args = tool_args if tool_args else {"query": query}
    return await biosciences_client.call_tool(tool_name, args)


BIOSCIENCES_ALIAS_TOOL_NAMES = [
    # Genomics / IDs
    "hgnc_search_genes",
    "hgnc_get_gene",
    "ensembl_search_genes",
    "ensembl_get_gene",
    "ensembl_get_transcript",
    "entrez_search_genes",
    "entrez_get_gene",
    "entrez_get_pubmed_links",
    # Proteomics / interactions
    "uniprot_search_proteins",
    "uniprot_get_protein",
    "string_search_proteins",
    "string_get_interactions",
    "string_get_network_image_url",
    "biogrid_search_genes",
    "biogrid_get_interactions",
    # Pharmacology
    "chembl_search_compounds",
    "chembl_get_compound",
    "chembl_get_compounds_batch",
    "pubchem_search_compounds",
    "pubchem_get_compound",
    "iuphar_search_ligands",
    "iuphar_get_ligand",
    "iuphar_search_targets",
    "iuphar_get_target",
    "opentargets_search_targets",
    "opentargets_get_target",
    "opentargets_get_associations",
    # Pathways and clinical
    "wikipathways_search_pathways",
    "wikipathways_get_pathway",
    "wikipathways_get_pathways_for_gene",
    "wikipathways_get_pathway_components",
    "clinicaltrials_search_trials",
    "clinicaltrials_get_trial",
    "clinicaltrials_get_trial_locations",
]


@tool
async def hgnc_search_genes(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for hgnc_search_genes on biosciences MCP."""
    return await _call_biosciences_alias("hgnc_search_genes", query, tool_args)


@tool
async def hgnc_get_gene(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for hgnc_get_gene. Provide tool_args: {'hgnc_id': 'HGNC:171'}."""
    return await _call_biosciences_alias("hgnc_get_gene", query, tool_args)


@tool
async def ensembl_search_genes(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for ensembl_search_genes on biosciences MCP."""
    return await _call_biosciences_alias("ensembl_search_genes", query, tool_args)


@tool
async def ensembl_get_gene(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for ensembl_get_gene. Provide tool_args: {'ensembl_id': 'ENSG...'}."""
    return await _call_biosciences_alias("ensembl_get_gene", query, tool_args)


@tool
async def ensembl_get_transcript(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for ensembl_get_transcript. Provide tool_args: {'transcript_id': 'ENST...'}."""
    return await _call_biosciences_alias("ensembl_get_transcript", query, tool_args)


@tool
async def entrez_search_genes(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for entrez_search_genes on biosciences MCP."""
    return await _call_biosciences_alias("entrez_search_genes", query, tool_args)


@tool
async def entrez_get_gene(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for entrez_get_gene. Provide tool_args: {'entrez_id': 'NCBIGene:7157'}."""
    return await _call_biosciences_alias("entrez_get_gene", query, tool_args)


@tool
async def entrez_get_pubmed_links(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for entrez_get_pubmed_links. Provide tool_args: {'gene_id': '4763'} (NCBI gene ID, numeric string)."""
    return await _call_biosciences_alias("entrez_get_pubmed_links", query, tool_args)


@tool
async def uniprot_search_proteins(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for uniprot_search_proteins on biosciences MCP."""
    return await _call_biosciences_alias("uniprot_search_proteins", query, tool_args)


@tool
async def uniprot_get_protein(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for uniprot_get_protein. Provide tool_args: {'uniprot_id': 'UniProtKB:P04637'}."""
    return await _call_biosciences_alias("uniprot_get_protein", query, tool_args)


@tool
async def string_search_proteins(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for string_search_proteins on biosciences MCP."""
    return await _call_biosciences_alias("string_search_proteins", query, tool_args)


@tool
async def string_get_interactions(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for string_get_interactions. Provide tool_args: {'string_id': '9606.ENSP00000196712', 'species': 9606, 'required_score': 700}. Get string_id from string_search_proteins first."""
    return await _call_biosciences_alias("string_get_interactions", query, tool_args)


@tool
async def string_get_network_image_url(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for string_get_network_image_url. Provide tool_args: {'identifiers': ['9606.ENSP00000196712'], 'species': 9606}."""
    return await _call_biosciences_alias("string_get_network_image_url", query, tool_args)


@tool
async def biogrid_search_genes(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for biogrid_search_genes on biosciences MCP."""
    return await _call_biosciences_alias("biogrid_search_genes", query, tool_args)


@tool
async def biogrid_get_interactions(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for biogrid_get_interactions. Provide tool_args: {'gene_symbol': 'TP53'}."""
    return await _call_biosciences_alias("biogrid_get_interactions", query, tool_args)


@tool
async def chembl_search_compounds(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for chembl_search_compounds on biosciences MCP."""
    return await _call_biosciences_alias("chembl_search_compounds", query, tool_args)


@tool
async def chembl_get_compound(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for chembl_get_compound. Provide tool_args: {'chembl_id': 'CHEMBL:25'}."""
    return await _call_biosciences_alias("chembl_get_compound", query, tool_args)


@tool
async def chembl_get_compounds_batch(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for chembl_get_compounds_batch. Provide tool_args: {'chembl_ids': ['CHEMBL25', 'CHEMBL941']} (list of ChEMBL IDs)."""
    return await _call_biosciences_alias("chembl_get_compounds_batch", query, tool_args)


@tool
async def pubchem_search_compounds(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for pubchem_search_compounds on biosciences MCP."""
    return await _call_biosciences_alias("pubchem_search_compounds", query, tool_args)


@tool
async def pubchem_get_compound(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for pubchem_get_compound. Provide tool_args: {'pubchem_id': 'PubChem:CID2244'}."""
    return await _call_biosciences_alias("pubchem_get_compound", query, tool_args)


@tool
async def iuphar_search_ligands(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for iuphar_search_ligands on biosciences MCP."""
    return await _call_biosciences_alias("iuphar_search_ligands", query, tool_args)


@tool
async def iuphar_get_ligand(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for iuphar_get_ligand. Provide tool_args: {'ligand_id': 123} (numeric ID from iuphar_search_ligands)."""
    return await _call_biosciences_alias("iuphar_get_ligand", query, tool_args)


@tool
async def iuphar_search_targets(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for iuphar_search_targets on biosciences MCP."""
    return await _call_biosciences_alias("iuphar_search_targets", query, tool_args)


@tool
async def iuphar_get_target(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for iuphar_get_target. Provide tool_args: {'target_id': 456} (numeric ID from iuphar_search_targets)."""
    return await _call_biosciences_alias("iuphar_get_target", query, tool_args)


@tool
async def opentargets_search_targets(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for opentargets_search_targets on biosciences MCP."""
    return await _call_biosciences_alias("opentargets_search_targets", query, tool_args)


@tool
async def opentargets_get_target(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for opentargets_get_target. Provide tool_args: {'ensembl_id': 'ENSG00000171791'}. Returns knownDrugs, tractability, and gene info."""
    return await _call_biosciences_alias("opentargets_get_target", query, tool_args)


@tool
async def opentargets_get_associations(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for opentargets_get_associations. Provide tool_args: {'ensembl_id': 'ENSG00000171791'}. Returns disease associations with scores."""
    return await _call_biosciences_alias("opentargets_get_associations", query, tool_args)


@tool
async def wikipathways_get_pathways_for_gene(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for wikipathways_get_pathways_for_gene. Provide tool_args: {'gene_id': 'TP53'} (gene symbol)."""
    return await _call_biosciences_alias("wikipathways_get_pathways_for_gene", query, tool_args)


@tool
async def wikipathways_search_pathways(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for wikipathways_search_pathways on biosciences MCP."""
    return await _call_biosciences_alias("wikipathways_search_pathways", query, tool_args)


@tool
async def wikipathways_get_pathway(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for wikipathways_get_pathway. Provide tool_args: {'pathway_id': 'WP5228'} (WikiPathways ID without 'WP:' prefix)."""
    return await _call_biosciences_alias("wikipathways_get_pathway", query, tool_args)


@tool
async def wikipathways_get_pathway_components(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for wikipathways_get_pathway_components. Provide tool_args: {'pathway_id': 'WP5228'} (WikiPathways ID)."""
    return await _call_biosciences_alias("wikipathways_get_pathway_components", query, tool_args)


@tool
async def clinicaltrials_search_trials(query: str, tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for clinicaltrials_search_trials on biosciences MCP."""
    return await _call_biosciences_alias("clinicaltrials_search_trials", query, tool_args)


@tool
async def clinicaltrials_get_trial(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for clinicaltrials_get_trial. Provide tool_args: {'nct_id': 'NCT:12345678'}."""
    return await _call_biosciences_alias("clinicaltrials_get_trial", query, tool_args)


@tool
async def clinicaltrials_get_trial_locations(query: str = "", tool_args: Optional[dict[str, Any]] = None):
    """Direct alias for clinicaltrials_get_trial_locations. Provide tool_args: {'nct_id': 'NCT:12345678'}."""
    return await _call_biosciences_alias("clinicaltrials_get_trial_locations", query, tool_args)


# --- PubMed MCP ---
# --- PubMed MCP (Local Cyanheads via Stdio) ---
# Using @cyanheads/pubmed-mcp-server via npx
# This runs locally, ensuring privacy and reliability (no external dependency on proprietary servers)
pubmed_client = StdioMCPClient(
    command="npx",
    args=["-y", "@cyanheads/pubmed-mcp-server"],
    env=os.environ.copy()
)

@tool
async def query_pubmed(
    tool_name: str,
    tool_args: dict[str, Any]
):
    """
    Access biomedical literature via the PubMed MCP.

    Supported tools (Adapter wraps local @cyanheads/pubmed-mcp-server):
    - search_articles: query (str), max_results (int) -> maps to pubmed_search_articles
    - get_article_metadata: pmids (list[str]) -> maps to pubmed_fetch_contents(detailLevel='abstract_plus')
    - get_full_text_article: pmc_ids/pmids (list[str]) -> maps to pubmed_fetch_contents(detailLevel='full_xml')

    Args:
        tool_name: The MCP tool to call (e.g., 'search_articles')
        tool_args: Dictionary of arguments for the tool
    """
    # Adapter Logic for @cyanheads/pubmed-mcp-server
    real_tool_name = tool_name
    real_args = tool_args.copy()

    if tool_name == "search_articles":
        real_tool_name = "pubmed_search_articles"
        if "query" in real_args:
            real_args["queryTerm"] = real_args.pop("query")
        if "max_results" in real_args:
            real_args["maxResults"] = real_args.pop("max_results")
            
    elif tool_name == "get_article_metadata":
        real_tool_name = "pubmed_fetch_contents"
        # Ensure pmids is a list
        if "pmids" in real_args and isinstance(real_args["pmids"], str):
             real_args["pmids"] = [real_args["pmids"]]
        real_args["detailLevel"] = "abstract_plus" 

    elif tool_name == "get_full_text_article":
        real_tool_name = "pubmed_fetch_contents"
        # Map pmc_ids to pmids as best effort (or expect agent to pass pmids)
        if "pmc_ids" in real_args:
             real_args["pmids"] = real_args.pop("pmc_ids")
        real_args["detailLevel"] = "full_xml"

    return await pubmed_client.call_tool(real_tool_name, real_args)


# --- Direct API Access (Fallback) ---

@tool
async def query_api_direct(
    url: str,
    method: str = "GET",
    body: Optional[str] = None,
    headers: Optional[dict[str, str]] = None
):
    """
    Direct API access for when MCP tools fail or are unavailable.

    Use this as a fallback when:
    - ChEMBL returns 500 errors (use Open Targets GraphQL instead)
    - You need to access APIs not covered by the MCP
    - You need full control over request parameters

    Common fallback patterns:
    1. Open Targets GraphQL (alternative to ChEMBL):
       url: "https://api.platform.opentargets.org/api/v4/graphql"
       method: "POST"
       body: '{"query": "{ target(ensemblId: \"ENSG00000115170\") { ... } }"}'

    2. HGNC Gene Resolution:
       url: "https://rest.genenames.org/fetch/symbol/ACVR1"

    3. ClinicalTrials.gov v2:
       url: "https://clinicaltrials.gov/api/v2/studies?query.cond=FOP&pageSize=10&format=json"

    Args:
        url: Full URL to fetch
        method: HTTP method (GET or POST)
        body: Request body for POST requests (JSON string)
        headers: Optional additional headers
    """
    default_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if headers:
        default_headers.update(headers)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.upper() == "POST":
                response = await client.post(url, content=body, headers=default_headers)
            else:
                response = await client.get(url, headers=default_headers)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as e:
        return f"HTTP Error {e.response.status_code}: {e}"
    except Exception as e:
        return f"Error fetching {url}: {e}"


# --- Graphiti Persistence ---

# Graphiti MCP client (connects to local Graphiti server)
GRAPHITI_MCP_URL = "http://localhost:8000/mcp"
graphiti_client = HTTPMCPClient(GRAPHITI_MCP_URL, timeout=30.0)


@tool
async def persist_to_graphiti(
    name: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    group_id: str = "biosciences-default"
):
    """
    Persist validated knowledge graph to Graphiti memory.

    Use this in the PERSIST phase to save the validated knowledge graph.
    Graphiti will extract entities and relationships from the JSON structure.

    Args:
        name: Descriptive name for this episode (e.g., "FOP Drug Repurposing Graph")
        nodes: List of node dicts with keys: id, type, label, properties
               Example: [{"id": "HGNC:171", "type": "Gene", "label": "ACVR1", "properties": {...}}]
        edges: List of edge dicts with keys: source, target, type, properties
               Example: [{"source": "HGNC:171", "target": "CHEMBL:1234", "type": "TARGETS", ...}]
        group_id: Namespace for this graph (default: "biosciences-default")

    Returns:
        Confirmation message from Graphiti
    """
    episode_body = json.dumps({
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "created_by": "biosciences-agent",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
    })

    try:
        return await graphiti_client.call_tool(
            "add_memory",
            {
                "name": name,
                "episode_body": episode_body,
                "source": "json",
                "source_description": "Biosciences Graph Builder validated output",
                "group_id": group_id
            },
            apply_rate_limit=False  # Graphiti doesn't need rate limiting
        )
    except Exception as e:
        # Graceful fallback if Graphiti is unavailable
        logger.warning(f"Graphiti persistence failed: {e}")
        return f"Note: Graphiti persistence unavailable ({e}). Graph data preserved in response."
