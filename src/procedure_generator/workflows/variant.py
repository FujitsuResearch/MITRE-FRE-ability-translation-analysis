"""Variant workflow using LangGraph.

replicate → translate → validate → extract_environment → convert → refine → output → END
"""

from langgraph.graph import END, StateGraph

from procedure_generator.logger import ProcedureLogger
from procedure_generator.workflows.nodes import (
    convert_environment_node,
    convert_node,
    extract_environment_node,
    output_node,
    refine_node,
    replicate_node,
    translate_node,
    validate_node,
)
from procedure_generator.workflows.state import VariantState

logger = ProcedureLogger(__name__)


def build_variant_workflow():
    """Build and compile the variant workflow graph."""
    graph = StateGraph(VariantState)
    # Replication Nodes
    graph.add_node("replicate", replicate_node)
    graph.add_node("translate", translate_node)
    graph.add_node("validate", validate_node)

    # Variant Nodes
    graph.add_node("extract_environment", extract_environment_node)
    graph.add_node("convert_environment", convert_environment_node)
    graph.add_node("convert", convert_node)
    graph.add_node("refine", refine_node)
    graph.add_node("output", output_node)

    graph.set_entry_point("replicate")
    graph.add_edge("replicate", "translate")
    graph.add_edge("translate", "validate")
    graph.add_edge("validate", "extract_environment")
    graph.add_edge("extract_environment", "convert_environment")
    graph.add_edge("convert_environment", "convert")
    graph.add_edge("convert", "refine")
    graph.add_edge("refine", "output")
    graph.add_edge("output", END)

    return graph.compile()
