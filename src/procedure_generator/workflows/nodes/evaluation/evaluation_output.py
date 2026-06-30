"""Evaluation output assembly node."""

from datetime import datetime

from procedure_generator.logger import get_logger
from procedure_generator.models import (
    EvaluationMeasure,
    EvaluationMetadata,
    EvaluationResult,
)

logger = get_logger("evaluation_output")


def evaluation_output_node(state: dict) -> dict:
    """Assemble final evaluation result with pass/fail measures.

    Reads: missing_steps_measure, extra_steps_measure, technique_ids_measure,
           os_constructs_measure, telemetry_classes_measure, extra_telemetry_measure,
           telemetry_diversity_measure, model, control_file, source_file, source_os, target_os
    Writes: evaluation_result
    """
    logger.info("Assembling evaluation result...")

    control_file = state.get("control_file", "unknown")
    source_file = state.get("source_file", "unknown")
    source_os = state.get("source_os", "unknown")
    target_os = state.get("target_os", "unknown")

    # Parse measures from state
    missing_steps = EvaluationMeasure.model_validate(state["missing_steps_measure"])
    extra_steps = EvaluationMeasure.model_validate(state["extra_steps_measure"])
    technique_ids = EvaluationMeasure.model_validate(state["technique_ids_measure"])
    parent_technique_ids = EvaluationMeasure.model_validate(state["parent_technique_ids_measure"])
    os_constructs = EvaluationMeasure.model_validate(state["os_constructs_measure"])
    telemetry_classes = EvaluationMeasure.model_validate(state["telemetry_classes_measure"])
    extra_telemetry = EvaluationMeasure.model_validate(state["extra_telemetry_measure"])
    telemetry_diversity = EvaluationMeasure.model_validate(state["telemetry_diversity_measure"])
    telemetry_multi_class = EvaluationMeasure.model_validate(state["telemetry_multi_class_measure"])
    technique_sequence = EvaluationMeasure.model_validate(state["technique_sequence_measure"])
    tactic_sequence = EvaluationMeasure.model_validate(state["tactic_sequence_measure"])
    privilege_progression = EvaluationMeasure.model_validate(state["privilege_progression_measure"])

    # Calculate all_pass
    all_pass = all(
        [
            missing_steps.passed,
            extra_steps.passed,
            technique_ids.passed,
            parent_technique_ids.passed,
            os_constructs.passed,
            telemetry_classes.passed,
            extra_telemetry.passed,
            telemetry_diversity.passed,
            telemetry_multi_class.passed,
            technique_sequence.passed,
            tactic_sequence.passed,
            privilege_progression.passed,
        ]
    )

    evaluation_result = EvaluationResult(
        metadata=EvaluationMetadata(
            source_file=source_file,
            control_file=control_file,
            source_os=source_os,
            target_os=target_os,
            evaluated_at=datetime.now(),
            model=state["model"],
        ),
        missing_steps=missing_steps,
        extra_steps=extra_steps,
        os_constructs_valid=os_constructs,
        technique_ids_match=technique_ids,
        parent_technique_ids_match=parent_technique_ids,
        telemetry_classes_match=telemetry_classes,
        extra_telemetry_classes=extra_telemetry,
        telemetry_diversity=telemetry_diversity,
        telemetry_multi_class=telemetry_multi_class,
        technique_sequence_match=technique_sequence,
        tactic_sequence_match=tactic_sequence,
        privilege_progression_match=privilege_progression,
        all_pass=all_pass,
    )

    logger.info(f"Evaluation result: all_pass={all_pass}")

    return {
        "evaluation_result": evaluation_result.model_dump(mode="json"),
    }
