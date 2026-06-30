"""Structural comparison node - compares variant against control for pass/fail measures.

Uses original_step_id to correctly handle step splits during OS conversion.
"""

from procedure_generator.logger import get_logger
from procedure_generator.models import EvaluationMeasure

logger = get_logger("structural_compare")


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


def _get_original_step_id(step: dict, index: int) -> int:
    """Get the original step ID that this step maps to.

    For variant steps, original_step_id indicates which control step it came from.
    If original_step_id is None, fall back to step_id.
    """
    original_id = step.get("original_step_id")
    if original_id is not None:
        return original_id
    return step.get("step_id", index + 1)


def _get_parent_technique(technique_id: str) -> str:
    """Extract parent technique ID from a technique ID.

    Examples:
        T1078.001 -> T1078
        T1078 -> T1078
        T1021.002 -> T1021
    """
    if "." in technique_id:
        return technique_id.split(".")[0]
    return technique_id


def _collapse_consecutive(seq: list[str]) -> list[str]:
    """Collapse consecutive duplicates in a sequence.

    Examples:
        ["a", "a", "b", "b", "a"] -> ["a", "b", "a"]
        ["elevated", "elevated", "non-elevated"] -> ["elevated", "non-elevated"]
    """
    if not seq:
        return []
    collapsed = [seq[0]]
    for item in seq[1:]:
        if item != collapsed[-1]:
            collapsed.append(item)
    return collapsed


def structural_compare_node(state: dict) -> dict:
    """Compare generated procedure against control for pass/fail measures.

    Uses original_step_id to correctly map variant steps to control steps,
    handling cases where one control step may be split into multiple variant steps.

    Reads: generated_procedure, control_procedure
    Writes: missing_steps_measure, extra_steps_measure, technique_ids_measure
    """
    logger.info("Running structural comparison...")

    generated = state["generated_procedure"]
    control = state["control_procedure"]

    gen_steps = _extract_action_sequence(generated)
    ctrl_steps = _extract_action_sequence(control)

    # Build control lookup by step_id
    ctrl_by_id = {s.get("step_id", i + 1): s for i, s in enumerate(ctrl_steps)}
    ctrl_ids = set(ctrl_by_id.keys())

    # Build mapping from control step IDs to variant steps using original_step_id
    # One control step may map to multiple variant steps (1:N mapping)
    ctrl_to_gen_steps: dict[int, list[dict]] = {ctrl_id: [] for ctrl_id in ctrl_ids}
    unmapped_gen_steps: list[dict] = []

    for i, gen_step in enumerate(gen_steps):
        original_id = _get_original_step_id(gen_step, i)
        if original_id in ctrl_ids:
            ctrl_to_gen_steps[original_id].append(gen_step)
        else:
            unmapped_gen_steps.append(gen_step)

    # Measure 1: Missing steps (control steps with no corresponding variant steps)
    missing_ctrl_ids = [ctrl_id for ctrl_id, gen_list in ctrl_to_gen_steps.items() if not gen_list]

    if missing_ctrl_ids:
        missing_steps_measure = EvaluationMeasure(
            name="missing_steps",
            passed=False,
            detail=f"Missing control step IDs: {', '.join(map(str, sorted(missing_ctrl_ids)))}",
        )
    else:
        missing_steps_measure = EvaluationMeasure(
            name="missing_steps",
            passed=True,
            detail="",
        )

    # Measure 2: Extra steps (variant steps that don't map to any control step)
    if unmapped_gen_steps:
        extra_ids = [s.get("step_id", "?") for s in unmapped_gen_steps]
        extra_steps_measure = EvaluationMeasure(
            name="extra_steps",
            passed=False,
            detail=f"Extra variant step IDs: {', '.join(map(str, extra_ids))}",
        )
    else:
        extra_steps_measure = EvaluationMeasure(
            name="extra_steps",
            passed=True,
            detail="",
        )

    # Measure 3: Technique IDs match (exact)
    # For each control step, check that all corresponding variant steps have matching technique_id
    technique_mismatches = []

    for ctrl_id in sorted(ctrl_ids):
        ctrl_step = ctrl_by_id[ctrl_id]
        ctrl_tech = ctrl_step.get("technique_id", "")
        gen_list = ctrl_to_gen_steps[ctrl_id]

        for gen_step in gen_list:
            gen_tech = gen_step.get("technique_id", "")
            gen_step_id = gen_step.get("step_id", "?")

            if ctrl_tech != gen_tech:
                technique_mismatches.append(
                    f"Control {ctrl_id} ({ctrl_tech}) vs Variant {gen_step_id} ({gen_tech})"
                )

    if technique_mismatches:
        technique_ids_measure = EvaluationMeasure(
            name="technique_ids_match",
            passed=False,
            detail="; ".join(technique_mismatches),
        )
    else:
        technique_ids_measure = EvaluationMeasure(
            name="technique_ids_match",
            passed=True,
            detail="",
        )

    # Measure 4: Parent technique IDs match (ignores subtechnique differences)
    # T1078.001 vs T1078.002 would pass (both are T1078)
    parent_technique_mismatches = []

    for ctrl_id in sorted(ctrl_ids):
        ctrl_step = ctrl_by_id[ctrl_id]
        ctrl_tech = ctrl_step.get("technique_id", "")
        ctrl_parent = _get_parent_technique(ctrl_tech)
        gen_list = ctrl_to_gen_steps[ctrl_id]

        for gen_step in gen_list:
            gen_tech = gen_step.get("technique_id", "")
            gen_parent = _get_parent_technique(gen_tech)
            gen_step_id = gen_step.get("step_id", "?")

            if ctrl_parent != gen_parent:
                parent_technique_mismatches.append(
                    f"Control {ctrl_id} ({ctrl_tech}) vs Variant {gen_step_id} ({gen_tech})"
                )

    if parent_technique_mismatches:
        parent_technique_ids_measure = EvaluationMeasure(
            name="parent_technique_ids_match",
            passed=False,
            detail="; ".join(parent_technique_mismatches),
        )
    else:
        parent_technique_ids_measure = EvaluationMeasure(
            name="parent_technique_ids_match",
            passed=True,
            detail="",
        )

    # Measure 5: Technique sequence match
    # Build ordered sequence of (step_id, technique_id) from control
    control_sequence = [
        (step.get("step_id", i + 1), step.get("technique_id", ""))
        for i, step in enumerate(ctrl_steps)
    ]

    # Map variant steps by original_step_id to technique (first occurrence wins for splits)
    variant_by_original: dict[int, str] = {}
    for i, gen_step in enumerate(gen_steps):
        original_id = _get_original_step_id(gen_step, i)
        if original_id not in variant_by_original:
            variant_by_original[original_id] = gen_step.get("technique_id", "")

    # Compare each position in sequence
    sequence_mismatches = []
    for ctrl_step_id, ctrl_technique in control_sequence:
        variant_technique = variant_by_original.get(ctrl_step_id)
        if variant_technique is None:
            sequence_mismatches.append(f"Step {ctrl_step_id}: missing in variant")
        elif ctrl_technique != variant_technique:
            sequence_mismatches.append(
                f"Step {ctrl_step_id}: {ctrl_technique} vs {variant_technique}"
            )

    if sequence_mismatches:
        technique_sequence_measure = EvaluationMeasure(
            name="technique_sequence_match",
            passed=False,
            detail="; ".join(sequence_mismatches),
        )
    else:
        technique_sequence_measure = EvaluationMeasure(
            name="technique_sequence_match",
            passed=True,
            detail="",
        )

    # Measure 6: Tactic sequence match (mirrors technique sequence but for tactics)
    # Map variant steps by original_step_id to tactic (first occurrence wins for splits)
    variant_tactic_by_original: dict[int, str] = {}
    for i, gen_step in enumerate(gen_steps):
        original_id = _get_original_step_id(gen_step, i)
        if original_id not in variant_tactic_by_original:
            variant_tactic_by_original[original_id] = gen_step.get("tactic", "")

    # Compare each position in sequence
    tactic_mismatches = []
    for i, ctrl_step in enumerate(ctrl_steps):
        ctrl_step_id = ctrl_step.get("step_id", i + 1)
        ctrl_tactic = ctrl_step.get("tactic", "")
        variant_tactic = variant_tactic_by_original.get(ctrl_step_id)

        if variant_tactic is None:
            tactic_mismatches.append(f"Step {ctrl_step_id}: missing in variant")
        elif ctrl_tactic != variant_tactic:
            tactic_mismatches.append(f"Step {ctrl_step_id}: {ctrl_tactic} vs {variant_tactic}")

    if tactic_mismatches:
        tactic_sequence_measure = EvaluationMeasure(
            name="tactic_sequence_match",
            passed=False,
            detail="; ".join(tactic_mismatches),
        )
    else:
        tactic_sequence_measure = EvaluationMeasure(
            name="tactic_sequence_match",
            passed=True,
            detail="",
        )

    # Measure 7: Privilege progression match
    # Build control privilege sequence and collapse consecutive duplicates
    control_privileges = [step.get("execution_level", "non-elevated") for step in ctrl_steps]
    control_collapsed = _collapse_consecutive(control_privileges)

    # Build variant privilege sequence (ordered by original_step_id mapping to control)
    # Map variant steps by original_step_id to execution_level (first occurrence wins for splits)
    variant_exec_by_original: dict[int, str] = {}
    for i, gen_step in enumerate(gen_steps):
        original_id = _get_original_step_id(gen_step, i)
        if original_id not in variant_exec_by_original:
            variant_exec_by_original[original_id] = gen_step.get("execution_level", "non-elevated")

    # Build variant sequence in control step order
    variant_privileges = []
    for ctrl_step_id, _ in control_sequence:
        exec_level = variant_exec_by_original.get(ctrl_step_id, "non-elevated")
        variant_privileges.append(exec_level)

    variant_collapsed = _collapse_consecutive(variant_privileges)

    if control_collapsed == variant_collapsed:
        privilege_progression_measure = EvaluationMeasure(
            name="privilege_progression_match",
            passed=True,
            detail="",
        )
    else:
        privilege_progression_measure = EvaluationMeasure(
            name="privilege_progression_match",
            passed=False,
            detail=f"Control: {control_collapsed}, Variant: {variant_collapsed}",
        )

    # Log summary
    covered_ctrl_ids = [ctrl_id for ctrl_id, gen_list in ctrl_to_gen_steps.items() if gen_list]
    logger.info(
        f"Structural comparison: {len(covered_ctrl_ids)}/{len(ctrl_ids)} control steps covered, "
        f"{len(missing_ctrl_ids)} missing, {len(unmapped_gen_steps)} unmapped variant steps, "
        f"{len(technique_mismatches)} exact technique mismatches, "
        f"{len(parent_technique_mismatches)} parent technique mismatches, "
        f"{len(sequence_mismatches)} technique sequence mismatches, "
        f"{len(tactic_mismatches)} tactic sequence mismatches, "
        f"privilege progression {'match' if privilege_progression_measure.passed else 'mismatch'}"
    )

    return {
        "missing_steps_measure": missing_steps_measure.model_dump(),
        "extra_steps_measure": extra_steps_measure.model_dump(),
        "technique_ids_measure": technique_ids_measure.model_dump(),
        "parent_technique_ids_measure": parent_technique_ids_measure.model_dump(),
        "technique_sequence_measure": technique_sequence_measure.model_dump(),
        "tactic_sequence_measure": tactic_sequence_measure.model_dump(),
        "privilege_progression_measure": privilege_progression_measure.model_dump(),
    }
