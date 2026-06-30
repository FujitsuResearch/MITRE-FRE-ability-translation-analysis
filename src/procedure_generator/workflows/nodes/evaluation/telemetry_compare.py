"""Telemetry comparison node - compares telemetry classes between variant and control."""

from procedure_generator.logger import get_logger
from procedure_generator.models import EvaluationMeasure

logger = get_logger("telemetry_compare")


def _extract_action_sequence(procedure: dict) -> list[dict]:
    """Extract action_sequence from various input formats.

    Handles:
    - EnrichedFinalOutput: {"procedure": {"action_sequence": [...]}}
    - FinalOutput: {"procedure": {"action_sequence": [...]}}
    - TTPOutput: {"action_sequence": [...]}
    """
    if "procedure" in procedure:
        return procedure["procedure"]["action_sequence"]
    return procedure.get("action_sequence", [])


def _collect_telemetry_classes(steps: list[dict]) -> set[str]:
    """Collect all unique telemetry classes from action steps.

    Args:
        steps: List of action step dicts

    Returns:
        Set of unique telemetry class strings
    """
    telemetry = set()
    for step in steps:
        classes = step.get("telemetry_classes", [])
        telemetry.update(classes)
    return telemetry


def telemetry_compare_node(state: dict) -> dict:
    """Compare telemetry classes between variant and control (procedure-wide).

    Reads: generated_procedure, control_procedure
    Writes: telemetry_classes_measure, extra_telemetry_measure, telemetry_diversity_measure
    """
    logger.info("Running telemetry comparison...")

    generated = state["generated_procedure"]
    control = state["control_procedure"]

    gen_steps = _extract_action_sequence(generated)
    ctrl_steps = _extract_action_sequence(control)

    # Collect procedure-wide telemetry classes
    variant_classes = _collect_telemetry_classes(gen_steps)
    control_classes = _collect_telemetry_classes(ctrl_steps)

    # Measure for multi-class check (independent of control)
    # Pass if variant generates telemetry in more than one class
    variant_count = len(variant_classes)

    if variant_count >= 2:
        telemetry_multi_class_measure = EvaluationMeasure(
            name="telemetry_multi_class",
            passed=True,
            detail="",
        )
    else:
        telemetry_multi_class_measure = EvaluationMeasure(
            name="telemetry_multi_class",
            passed=False,
            detail=f"Variant has only {variant_count} telemetry class(es)",
        )

    # Handle case where control has no telemetry data
    if not control_classes:
        logger.warning(
            "Control has no telemetry_classes - skipping control-based telemetry evaluation"
        )
        return {
            "telemetry_classes_measure": EvaluationMeasure(
                name="telemetry_classes_match",
                passed=True,
                detail="Control has no telemetry data - skipped",
            ).model_dump(),
            "extra_telemetry_measure": EvaluationMeasure(
                name="extra_telemetry_classes",
                passed=True,
                detail="Control has no telemetry data - skipped",
            ).model_dump(),
            "telemetry_diversity_measure": EvaluationMeasure(
                name="telemetry_diversity",
                passed=True,
                detail="Control has no telemetry data - skipped",
            ).model_dump(),
            "telemetry_multi_class_measure": telemetry_multi_class_measure.model_dump(),
        }

    # Measure 1: telemetry_classes_match
    # Pass if all control telemetry classes are present in variant
    missing_classes = control_classes - variant_classes

    if missing_classes:
        telemetry_classes_measure = EvaluationMeasure(
            name="telemetry_classes_match",
            passed=False,
            detail=f"Missing telemetry classes: {', '.join(sorted(missing_classes))}",
        )
    else:
        telemetry_classes_measure = EvaluationMeasure(
            name="telemetry_classes_match",
            passed=True,
            detail="",
        )

    # Measure 2: extra_telemetry_classes
    # Pass if variant has no extra telemetry classes beyond control
    extra_classes = variant_classes - control_classes

    if extra_classes:
        extra_telemetry_measure = EvaluationMeasure(
            name="extra_telemetry_classes",
            passed=False,
            detail=f"Extra telemetry classes: {', '.join(sorted(extra_classes))}",
        )
    else:
        extra_telemetry_measure = EvaluationMeasure(
            name="extra_telemetry_classes",
            passed=True,
            detail="",
        )

    # Measure 3: telemetry_diversity
    # Pass if variant has >= same number of unique telemetry classes as control
    control_count = len(control_classes)

    if variant_count >= control_count:
        telemetry_diversity_measure = EvaluationMeasure(
            name="telemetry_diversity",
            passed=True,
            detail="",
        )
    else:
        telemetry_diversity_measure = EvaluationMeasure(
            name="telemetry_diversity",
            passed=False,
            detail=f"Variant has {variant_count} classes, control has {control_count}",
        )

    # Log summary
    logger.info(
        f"Telemetry comparison: control={sorted(control_classes)}, variant={sorted(variant_classes)}, "
        f"missing={sorted(missing_classes)}, extra={sorted(extra_classes)}"
    )

    return {
        "telemetry_classes_measure": telemetry_classes_measure.model_dump(),
        "extra_telemetry_measure": extra_telemetry_measure.model_dump(),
        "telemetry_diversity_measure": telemetry_diversity_measure.model_dump(),
        "telemetry_multi_class_measure": telemetry_multi_class_measure.model_dump(),
    }
