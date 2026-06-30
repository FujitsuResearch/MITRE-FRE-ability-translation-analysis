"""D3FEND enrichment workflow using LangGraph.

Workflow: enrich → output → END

Takes an existing TTPOutput or FinalOutput and adds D3FEND observable information
to each action step.
"""

from langgraph.graph import END, StateGraph

from procedure_generator.logger import get_logger
from procedure_generator.workflows.nodes.enrichment import (
    enrich_node,
    enrichment_output_node,
)
from procedure_generator.workflows.state import EnrichmentState

logger = get_logger("enrichment_workflow")


def build_enrichment_workflow():
    """Build D3FEND enrichment workflow: enrich → output → END.

    Takes procedure JSON and enriches each step with:
    - d3fend_observables: All relevant D3FEND artifact classes
    - execution_observables: Artifacts that actually occur at runtime
    - telemetry_classes: Simplified telemetry categories
    """
    graph = StateGraph(EnrichmentState)

    graph.add_node("enrich", enrich_node)
    graph.add_node("output", enrichment_output_node)

    graph.set_entry_point("enrich")
    graph.add_edge("enrich", "output")
    graph.add_edge("output", END)

    return graph.compile()
