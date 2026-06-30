"""Full pipeline workflow: variant → enrichment → evaluation (optional).

This workflow chains all stages for end-to-end procedure transformation
and optional evaluation against a control file.
"""

from langgraph.graph import END, StateGraph

from procedure_generator.logger import get_logger
from procedure_generator.models import FullPipelineOutput
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
from procedure_generator.workflows.nodes.enrichment import (
    enrich_node,
    enrichment_output_node,
)
from procedure_generator.workflows.nodes.evaluation import (
    evaluation_output_node,
    os_construct_check_node,
    structural_compare_node,
    telemetry_compare_node,
)
from procedure_generator.workflows.state import FullPipelineState

logger = get_logger("full_pipeline")


def _bridge_to_enrichment(state: dict) -> dict:
    """Bridge node: prepare state for enrichment phase.

    Converts variant output to enrichment input format.
    """
    logger.info("[bridge] Preparing for enrichment phase")

    final_output = state["final_output"]

    return {
        "input_procedure": final_output,
    }


def _bridge_to_evaluation(state: dict) -> dict:
    """Bridge node: prepare state for evaluation phase.

    Sets up generated_procedure from enriched output.
    """
    logger.info("[bridge] Preparing for evaluation phase")

    return {
        "generated_procedure": state["enriched_output"],
    }


def _full_pipeline_output(state: dict) -> dict:
    """Final output node: combine variant metadata with enriched procedure.

    Merges the variant output structure with the enriched procedure,
    replacing the unenriched procedure with the enriched version.
    """
    logger.info("[full_output] Assembling full pipeline output")

    final_output = state["final_output"]
    enriched_output = state["enriched_output"]
    evaluation_result = state.get("evaluation_result")

    full_output = FullPipelineOutput(
        metadata=final_output["metadata"],
        environment=final_output["environment"],
        procedure=enriched_output["procedure"],
        intermediate_output=final_output["intermediate_output"],
        evaluation=evaluation_result,
    )

    return {
        "full_pipeline_output": full_output.model_dump(mode="json"),
    }


def _should_evaluate(state: dict) -> str:
    """Conditional routing: evaluate if control file was provided."""
    if state.get("control_procedure") is not None:
        logger.info("[router] Control file provided - running evaluation")
        return "evaluate"
    else:
        logger.info("[router] No control file - skipping evaluation")
        return "skip_evaluation"


def build_full_pipeline_workflow():
    """Build full pipeline: variant → enrichment → evaluation (optional) → END.

    If --control is provided, runs evaluation. Otherwise skips to output.
    """
    graph = StateGraph(FullPipelineState)

    # ========== Variant Phase ==========
    graph.add_node("replicate", replicate_node)
    graph.add_node("translate", translate_node)
    graph.add_node("validate", validate_node)
    graph.add_node("extract_environment", extract_environment_node)
    graph.add_node("convert_environment", convert_environment_node)
    graph.add_node("convert", convert_node)
    graph.add_node("refine", refine_node)
    graph.add_node("variant_output", output_node)

    # ========== Bridge: Variant → Enrichment ==========
    graph.add_node("bridge_to_enrichment", _bridge_to_enrichment)

    # ========== Enrichment Phase ==========
    graph.add_node("enrich", enrich_node)
    graph.add_node("enrichment_output", enrichment_output_node)

    # ========== Bridge: Enrichment → Evaluation ==========
    graph.add_node("bridge_to_evaluation", _bridge_to_evaluation)

    # ========== Evaluation Phase (conditional) ==========
    graph.add_node("structural_compare", structural_compare_node)
    graph.add_node("os_construct_check", os_construct_check_node)
    graph.add_node("telemetry_compare", telemetry_compare_node)
    graph.add_node("evaluation_output", evaluation_output_node)

    # ========== Final Output ==========
    graph.add_node("full_output", _full_pipeline_output)

    # ========== Edges: Variant Phase ==========
    graph.set_entry_point("replicate")
    graph.add_edge("replicate", "translate")
    graph.add_edge("translate", "validate")
    graph.add_edge("validate", "extract_environment")
    graph.add_edge("extract_environment", "convert_environment")
    graph.add_edge("convert_environment", "convert")
    graph.add_edge("convert", "refine")
    graph.add_edge("refine", "variant_output")

    # ========== Edges: Bridge to Enrichment ==========
    graph.add_edge("variant_output", "bridge_to_enrichment")

    # ========== Edges: Enrichment Phase ==========
    graph.add_edge("bridge_to_enrichment", "enrich")
    graph.add_edge("enrich", "enrichment_output")

    # ========== Edges: Conditional Evaluation ==========
    graph.add_edge("enrichment_output", "bridge_to_evaluation")

    # Conditional: evaluate or skip
    graph.add_conditional_edges(
        "bridge_to_evaluation",
        _should_evaluate,
        {
            "evaluate": "structural_compare",
            "skip_evaluation": "full_output",
        },
    )

    # ========== Edges: Evaluation Phase ==========
    graph.add_edge("structural_compare", "os_construct_check")
    graph.add_edge("os_construct_check", "telemetry_compare")
    graph.add_edge("telemetry_compare", "evaluation_output")
    graph.add_edge("evaluation_output", "full_output")

    # ========== Edges: Final Output ==========
    graph.add_edge("full_output", END)

    return graph.compile()
