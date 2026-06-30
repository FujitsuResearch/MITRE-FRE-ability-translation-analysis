"""Enrichment output assembly node."""

from datetime import datetime

from procedure_generator.logger import get_logger
from procedure_generator.models import (
    EnrichedActionStep,
    EnrichedFinalOutput,
    EnrichedTTPOutput,
    EnrichmentMetadata,
)

logger = get_logger("enrichment_output")


def enrichment_output_node(state: dict) -> dict:
    """Assemble final enriched output by merging observables with action steps.

    Reads: input_procedure, step_observables, source_file, model, usage
    Writes: enriched_output
    """
    logger.info("Assembling enriched output...")

    input_procedure = state["input_procedure"]
    step_observables = state["step_observables"]
    source_file = state["source_file"]
    model = state["model"]
    usage = state.get("usage", {})

    # Handle both TTPOutput and FinalOutput structures
    if "procedure" in input_procedure:
        action_sequence = input_procedure["procedure"]["action_sequence"]
    else:
        action_sequence = input_procedure["action_sequence"]

    # Build lookup of observables by step_id
    obs_by_step = {obs["step_id"]: obs for obs in step_observables}
    logger.debug(f"Observable lookup keys: {list(obs_by_step.keys())}")

    # Merge observables into action steps
    # Preserves existing enrichment fields if input is already enriched
    enriched_steps = []
    for idx, step in enumerate(action_sequence):
        # Use step_id if present, otherwise use 1-based index
        step_id = step.get("step_id", idx + 1)
        obs = obs_by_step.get(step_id, {})
        if not obs:
            logger.warning(
                f"No observables found for step_id={step_id}. Available keys: {list(obs_by_step.keys())}"
            )

        # For each enrichment field, preserve existing value if present, otherwise use new value from obs
        enriched_step = EnrichedActionStep(
            step_id=step_id,
            original_step_id=step.get("original_step_id"),
            tactic=step["tactic"],
            technique_id=step["technique_id"],
            technique_name=step["technique_name"],
            os=step["os"],
            host=step.get("host", "unknown"),
            command=step["command"],
            description=step["description"],
            # Additive only: keep existing enrichment, only add if not present
            d3fend_observables=step.get("d3fend_observables") or obs.get("d3fend_observables", []),
            execution_observables=step.get("execution_observables")
            or obs.get("execution_observables", []),
            telemetry_classes=step.get("telemetry_classes") or obs.get("telemetry_classes", []),
            execution_level=step.get("execution_level")
            or obs.get("execution_level", "non-elevated"),
        )
        enriched_steps.append(enriched_step)

    # Calculate duration from usage if available
    total_tokens = usage.get("total_tokens", 0)
    # Rough estimate: ~50 tokens/second for typical LLM
    duration_ms = int((total_tokens / 50) * 1000) if total_tokens > 0 else 0

    # Build final output
    enriched_output = EnrichedFinalOutput(
        metadata=EnrichmentMetadata(
            source_file=source_file,
            enriched_at=datetime.now(),
            model=model,
            total_duration_ms=duration_ms,
        ),
        procedure=EnrichedTTPOutput(action_sequence=enriched_steps),
    )

    logger.info(f"Assembled enriched output with {len(enriched_steps)} steps")

    return {
        "enriched_output": enriched_output.model_dump(mode="json"),
    }
