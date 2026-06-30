"""Evaluation workflow using LangGraph.

Workflow: structural_compare → os_construct_check → output → END

Compares generated procedure against a control (gold standard) file with pass/fail measures.
"""

from langgraph.graph import END, StateGraph

from procedure_generator.logger import get_logger
from procedure_generator.workflows.nodes.evaluation import (
    evaluation_output_node,
    os_construct_check_node,
    structural_compare_node,
    telemetry_compare_node,
)
from procedure_generator.workflows.state import EvaluationState

logger = get_logger("evaluation_workflow")


def build_evaluation_workflow():
    """Build evaluation workflow: structural_compare → os_construct_check → telemetry_compare → output → END.

    Compares generated procedure against control and produces pass/fail measures:
    - missing_steps: Are control steps missing from variant?
    - extra_steps: Are there extra steps in variant?
    - os_constructs_valid: Are OS-appropriate constructs used?
    - technique_ids_match: Do ATT&CK technique IDs match?
    - parent_technique_ids_match: Do parent technique IDs match?
    - technique_sequence_match: Is technique sequence preserved?
    - telemetry_classes_match: Do telemetry classes match?
    - extra_telemetry_classes: Are extra telemetry classes present?
    - telemetry_diversity: Is telemetry diversity maintained?
    - telemetry_multi_class: Does variant generate multiple telemetry classes?
    """
    graph = StateGraph(EvaluationState)

    graph.add_node("structural_compare", structural_compare_node)
    graph.add_node("os_construct_check", os_construct_check_node)
    graph.add_node("telemetry_compare", telemetry_compare_node)
    graph.add_node("output", evaluation_output_node)

    graph.set_entry_point("structural_compare")
    graph.add_edge("structural_compare", "os_construct_check")
    graph.add_edge("os_construct_check", "telemetry_compare")
    graph.add_edge("telemetry_compare", "output")
    graph.add_edge("output", END)

    return graph.compile()
