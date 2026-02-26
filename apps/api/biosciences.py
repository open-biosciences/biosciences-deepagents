"""
Life Sciences Graph Builder Agent - DeepAgents Pattern

Implements the 'Fuzzy-to-Fact' protocol using a supervisor with 7 specialist subagents:
1. ANCHOR: Resolve entities to CURIEs
2. ENRICH: Fetch metadata
3. EXPAND: Find connections/pathways
4. TRAVERSE_DRUGS: Find drugs matching targets
5. TRAVERSE_TRIALS: Find clinical trials
6. VALIDATE: Verify NCT IDs/mechanisms
7. PERSIST: Format final output
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure we can import from shared
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langchain.chat_models import init_chat_model
from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, StateBackend, CompositeBackend
from shared.mcp import (
    query_api_direct,
    persist_to_graphiti,
    query_pubmed,
    hgnc_search_genes,
    hgnc_get_gene,
    ensembl_search_genes,
    ensembl_get_gene,
    ensembl_get_transcript,
    entrez_search_genes,
    entrez_get_gene,
    entrez_get_pubmed_links,
    uniprot_search_proteins,
    uniprot_get_protein,
    string_search_proteins,
    string_get_interactions,
    string_get_network_image_url,
    wikipathways_search_pathways,
    wikipathways_get_pathways_for_gene,
    wikipathways_get_pathway_components,
    wikipathways_get_pathway,
    biogrid_search_genes,
    biogrid_get_interactions,
    chembl_search_compounds,
    chembl_get_compound,
    chembl_get_compounds_batch,
    pubchem_search_compounds,
    pubchem_get_compound,
    iuphar_search_ligands,
    iuphar_get_ligand,
    iuphar_search_targets,
    iuphar_get_target,
    opentargets_search_targets,
    opentargets_get_target,
    opentargets_get_associations,
    clinicaltrials_search_trials,
    clinicaltrials_get_trial,
    clinicaltrials_get_trial_locations,
)
from shared.tools import think_tool
from shared.prompts import (
    ANCHOR_SYSTEM,
    ENRICH_SYSTEM,
    EXPAND_SYSTEM,
    TRAVERSE_DRUGS_SYSTEM,
    TRAVERSE_TRIALS_SYSTEM,
    VALIDATE_SYSTEM,
    PERSIST_SYSTEM,
)

load_dotenv()
logger = logging.getLogger(__name__)


ALLOWED_BIOSCIENCES_SUBAGENTS = {
    "anchor_specialist",
    "enrichment_specialist",
    "expansion_specialist",
    "traversal_drugs_specialist",
    "traversal_trials_specialist",
    "validation_specialist",
    "persistence_specialist",
}

SUPERVISOR_SKILL_NAMES = ("biosciences-graph-builder",)

SUBAGENT_SKILL_NAMES = {
    "anchor_specialist": (
        "biosciences-graph-builder",
        "biosciences-genomics",
        "biosciences-pharmacology",
        "biosciences-clinical",
    ),
    "enrichment_specialist": (
        "biosciences-graph-builder",
        "biosciences-genomics",
        "biosciences-proteomics",
        "biosciences-pharmacology",
        "biosciences-clinical",
    ),
    "expansion_specialist": (
        "biosciences-graph-builder",
        "biosciences-genomics",
        "biosciences-proteomics",
        "biosciences-crispr",
    ),
    "traversal_drugs_specialist": (
        "biosciences-graph-builder",
        "biosciences-pharmacology",
    ),
    "traversal_trials_specialist": (
        "biosciences-graph-builder",
        "biosciences-clinical",
    ),
    "validation_specialist": (
        "biosciences-graph-builder",
        "biosciences-genomics",
        "biosciences-pharmacology",
        "biosciences-clinical",
    ),
    "persistence_specialist": (
        "biosciences-reporting",
        "biosciences-reporting-quality-review",
        "biosciences-publication-pipeline",
    ),
}


class BiosciencesSubagentGuardMiddleware(AgentMiddleware):
    """Reject missing/unknown task() subagent types."""

    def _validate(self, request: ToolCallRequest) -> ToolMessage | None:
        if request.tool_call.get("name") != "task":
            return None

        tool_call_id = request.tool_call.get("id", "subagent-guard")
        args = request.tool_call.get("args", {})
        if not isinstance(args, dict):
            return ToolMessage(
                content="Rejected task call: arguments must be an object.",
                tool_call_id=tool_call_id,
                status="error",
            )

        subagent_type = str(args.get("subagent_type", "")).strip()
        if not subagent_type:
            return ToolMessage(
                content="Rejected task call: missing `subagent_type`.",
                tool_call_id=tool_call_id,
                status="error",
            )

        if subagent_type not in ALLOWED_BIOSCIENCES_SUBAGENTS:
            allowed = ", ".join(sorted(ALLOWED_BIOSCIENCES_SUBAGENTS))
            return ToolMessage(
                content=(
                    f"Rejected unknown subagent `{subagent_type}`. Allowed: {allowed}."
                ),
                tool_call_id=tool_call_id,
                status="error",
            )

        return None

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        rejection = self._validate(request)
        if rejection is not None:
            return rejection
        return handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        rejection = self._validate(request)
        if rejection is not None:
            return rejection
        return await handler(request)


def _resolve_runtime_root() -> Path:
    configured = os.getenv("BIOSCIENCES_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / ".deepagents").resolve()


def _resolve_knowledge_paths(
    runtime_root: Path,
) -> tuple[list[str], list[str], dict[str, list[str]], int]:
    memory_file = runtime_root / "AGENTS.md"
    skills_root = runtime_root / "skills"

    available_skill_names: set[str] = set()
    if skills_root.exists():
        for entry in skills_root.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                available_skill_names.add(entry.name)

    # SkillsMiddleware expects parent-directory paths (e.g., "/skills/") so it can
    # scan child directories for SKILL.md files. Passing individual skill paths
    # like "/skills/biosciences-graph-builder" causes _alist_skills to find only
    # SKILL.md (a file, not a directory), resulting in skill_dirs=[] and no skills
    # being injected into agent system prompts.
    #
    # We pass ["/skills/"] as the single source for all agents. Tool isolation is
    # enforced via the tools list on each specialist, not via skill visibility.
    skills_source = ["/skills/"] if available_skill_names else []

    memory_paths = ["/AGENTS.md"] if memory_file.exists() else []
    return (
        memory_paths,
        skills_source,  # supervisor gets all skills
        {name: skills_source for name in SUBAGENT_SKILL_NAMES},  # subagents too
        len(available_skill_names),
    )


# anthropic:claude-sonnet-4-5
# openai:gpt-4o"
def create_biosciences_graph(model_name: str = "openai:gpt-4o"):
    """Create a life sciences deep agent graph using the Fuzzy-to-Fact protocol."""

    model = init_chat_model(model_name)
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Supervisor system prompt with phase orchestration
    supervisor_system = f"""You are the Life Sciences Graph Builder Supervisor.
Your goal is to orchestrate the 'Fuzzy-to-Fact' protocol to answer user questions about biology and medicine.

You delegate work to specialist subagents using the task() tool. Each invocation is stateless — the specialist only sees the description you provide. Include ALL context the specialist needs.

Protocol Phases (execute sequentially unless noted):
1. ANCHOR: Identify entities and get CURIEs → delegate to anchor_specialist
2. ENRICH: Get metadata for those entities → delegate to enrichment_specialist
3. EXPAND: Find connections (interactions, pathways) → delegate to expansion_specialist
4. TRAVERSE_DRUGS + TRAVERSE_TRIALS: These two CAN run in parallel since they are independent.
   - TRAVERSE_DRUGS: Find drugs matching targets → delegate to traversal_drugs_specialist
   - TRAVERSE_TRIALS: Find clinical trials for the disease → delegate to traversal_trials_specialist
   To run in parallel, call both task() tools in a single message.
5. VALIDATE: Verify facts (IDs, mechanisms) → delegate to validation_specialist
6. PERSIST: Summarize and finalize → delegate to persistence_specialist

DATA PASSING BETWEEN PHASES:
- Each specialist returns structured results. You MUST include the relevant output in the description for the next specialist.
- Example: After ANCHOR returns CURIEs, pass them to ENRICH: "Enrich the following entities: HGNC:171 (ACVR1), MONDO:0018875 (FOP). Get UniProt IDs, Ensembl IDs, and functional descriptions."
- After ENRICH returns Ensembl IDs, pass them to TRAVERSE_DRUGS: "Find drugs targeting ACVR1 (Ensembl: ENSG00000115170). Try ChEMBL first, fall back to Open Targets."
- Include the disease context from the original query in ALL phase descriptions.

IMPORTANT:
- Do not skip phases. If a phase returns no results, note this and continue.
- After all phases complete, relay the persistence_specialist's summary to the user.

Today's date is {current_date}.

STRICT ROUTING RULES:
- NEVER invent new subagents (like 'research-analyst').
- Always start with 'anchor_specialist' for new queries.
- If the user asks a research question, map it to the 'anchor_specialist' first to identify the key entities."""

    runtime_root = _resolve_runtime_root()
    workspace_dir = runtime_root / "workspace"
    runtime_root.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    memory_paths, skills_source, subagent_skills, skill_count = (
        _resolve_knowledge_paths(runtime_root)
    )

    logger.info(
        "Lifesciences knowledge config: runtime_root=%s memory_enabled=%s skills_source=%s skill_count=%d",
        str(runtime_root),
        bool(memory_paths),
        skills_source,
        skill_count,
    )

    # Note: We append think_tool to complex specialists

    # Backend configuration for workspace isolation:
    # - /workspace/ → StateBackend (ephemeral, thread-scoped)
    # - Everything else → FilesystemBackend (persistent: AGENTS.md, skills)
    def make_backend(runtime):
        state_backend = StateBackend(runtime)
        filesystem_backend = FilesystemBackend(root_dir=str(runtime_root), virtual_mode=True)
        return CompositeBackend(
            default=filesystem_backend,  # Default: persistent storage
            routes={
                "/workspace/": state_backend,  # Workspace is thread-scoped and ephemeral
            }
        )

    agent = create_deep_agent(
        model=model,
        tools=[],  # Supervisor delegates, doesn't call tools directly
        system_prompt=supervisor_system,
        middleware=[BiosciencesSubagentGuardMiddleware()],
        backend=make_backend,
        memory=memory_paths or None,
        skills=skills_source or None,
        subagents=[
            {
                "name": "anchor_specialist",
                "description": "PHASE 1: Resolves fuzzy terms to canonical CURIEs (HGNC, CHEMBL, NCT). Use for identifying genes, drugs, and diseases. Can also search literature via PubMed.",
                "system_prompt": ANCHOR_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("anchor_specialist", []),
                "tools": [
                    hgnc_search_genes,
                    ensembl_search_genes,
                    entrez_search_genes,
                    uniprot_search_proteins,
                    chembl_search_compounds,
                    pubchem_search_compounds,
                    iuphar_search_ligands,
                    iuphar_search_targets,
                    wikipathways_search_pathways,
                    clinicaltrials_search_trials,
                    query_pubmed,
                    think_tool,
                ],
            },
            {
                "name": "enrichment_specialist",
                "description": "PHASE 2: Fetches detailed metadata for CURIEs. Gets UniProt/Ensembl IDs for genes, functions for proteins, Max Phase for drugs.",
                "system_prompt": ENRICH_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("enrichment_specialist", []),
                "tools": [
                    hgnc_get_gene,
                    ensembl_search_genes,
                    ensembl_get_gene,
                    ensembl_get_transcript,
                    entrez_get_gene,
                    entrez_get_pubmed_links,
                    uniprot_search_proteins,
                    uniprot_get_protein,
                    chembl_get_compound,
                    chembl_get_compounds_batch,
                    pubchem_get_compound,
                    iuphar_get_ligand,
                    iuphar_get_target,
                    opentargets_get_associations,
                    query_pubmed,
                    think_tool,
                ],
            },
            {
                "name": "expansion_specialist",
                "description": "PHASE 3: Finds biological connections. Gets STRING interactions, WikiPathways, BioGrid genetic interactions.",
                "system_prompt": EXPAND_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("expansion_specialist", []),
                "tools": [
                    string_search_proteins,
                    string_get_interactions,
                    string_get_network_image_url,
                    wikipathways_get_pathways_for_gene,
                    wikipathways_get_pathway_components,
                    wikipathways_get_pathway,
                    biogrid_search_genes,
                    biogrid_get_interactions,
                    think_tool,
                ],
            },
            {
                "name": "traversal_drugs_specialist",
                "description": "PHASE 4a: Identifies therapeutic targets and finds drugs that target them. Searches for approved drugs and inhibitors. Has fallback to Open Targets if ChEMBL fails.",
                "system_prompt": TRAVERSE_DRUGS_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("traversal_drugs_specialist", []),
                "tools": [
                    chembl_search_compounds,
                    chembl_get_compound,
                    pubchem_search_compounds,
                    pubchem_get_compound,
                    iuphar_search_ligands,
                    iuphar_get_ligand,
                    opentargets_search_targets,
                    opentargets_get_target,
                    opentargets_get_associations,
                    query_api_direct,
                    think_tool,
                ],
            },
            {
                "name": "traversal_trials_specialist",
                "description": "PHASE 4b: Finds Clinical Trials for identified drugs. Combines drug names with disease context. Can use ClinicalTrials.gov v2 API directly.",
                "system_prompt": TRAVERSE_TRIALS_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("traversal_trials_specialist", []),
                "tools": [
                    clinicaltrials_search_trials,
                    clinicaltrials_get_trial,
                    clinicaltrials_get_trial_locations,
                    query_api_direct,
                    think_tool,
                ],
            },
            {
                "name": "validation_specialist",
                "description": "PHASE 5: Verifies facts to prevent hallucinations. Validates NCT IDs and drug mechanisms. Can verify claims against PubMed literature.",
                "system_prompt": VALIDATE_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("validation_specialist", []),
                "tools": [
                    clinicaltrials_get_trial,
                    pubchem_get_compound,
                    chembl_get_compound,
                    ensembl_get_gene,
                    query_pubmed,
                    think_tool,
                ],
            },
            {
                "name": "persistence_specialist",
                "description": "PHASE 6: Formats validated knowledge graph and provides final summary.",
                "system_prompt": PERSIST_SYSTEM,
                "model": model_name,
                "skills": subagent_skills.get("persistence_specialist", []),
                "tools": [persist_to_graphiti],
            },
        ],
    )

    return agent


# Expose the graph for LangGraph (langgraph.json compatibility)
graph = create_biosciences_graph()
