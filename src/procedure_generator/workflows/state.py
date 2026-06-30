"""Workflow state definitions."""

from typing import TypedDict


class BaseState(TypedDict):
    """Base state shared by all workflows."""

    # Input
    source_file: str
    raw_procedure: str
    model: str

    # Accumulated usage
    usage: dict | None


class ReplicationState(BaseState):
    """State for replication workflow (replicate → translate → validate)."""

    # Output from replicate node
    replicated_procedure: str | None

    # Output from translate node (JSON string)
    converted_procedure: str | None

    # Output from validate node (TTPOutputBase as dict)
    validated_output: dict | None


class VariantState(ReplicationState):
    """State for variant workflow.

    Extends ReplicationState with variant-specific fields.
    """

    # Variant-specific input
    source_os: str
    target_os: str

    # Output from extract_environment node (EnvironmentMap as dict)
    original_environment: dict | None

    # Output from convert_environment node (ConvertedEnvironment as dict)
    converted_environment: dict | None

    # Output from convert node (ConversionResult as dict)
    conversion_result: dict | None

    # Output from refine node (RefinementResult as dict)
    refinement_result: dict | None

    # Output from output node (FinalOutput as dict)
    final_output: dict | None


class EnrichmentState(TypedDict):
    """State for D3FEND enrichment workflow."""

    # Input
    source_file: str
    input_procedure: dict  # TTPOutput or FinalOutput as dict
    model: str

    # Accumulated usage
    usage: dict | None

    # Output from enrich node (list of StepObservables as dicts)
    step_observables: list[dict] | None

    # Final enriched output (EnrichedFinalOutput as dict)
    enriched_output: dict | None


class EvaluationState(TypedDict):
    """State for evaluation workflow."""

    # Input
    source_file: str  # Original procedure file path
    generated_procedure: dict  # EnrichedFinalOutput or FinalOutput as dict
    control_procedure: dict  # TTPOutput-like structure from control JSON
    control_file: str  # Path to control file for metadata
    source_os: str
    target_os: str
    model: str

    # Accumulated usage
    usage: dict | None

    # Output from structural_compare node
    missing_steps_measure: dict | None
    extra_steps_measure: dict | None
    technique_ids_measure: dict | None
    parent_technique_ids_measure: dict | None

    # Output from os_construct_check node
    os_violations: list[dict] | None
    os_constructs_measure: dict | None

    # Output from telemetry_compare node
    telemetry_classes_measure: dict | None
    extra_telemetry_measure: dict | None
    telemetry_diversity_measure: dict | None
    telemetry_multi_class_measure: dict | None

    # Output from structural_compare node (sequence and privilege)
    technique_sequence_measure: dict | None
    tactic_sequence_measure: dict | None
    privilege_progression_measure: dict | None

    # Final evaluation result (EvaluationResult as dict)
    evaluation_result: dict | None


class FullPipelineState(TypedDict):
    """State for full pipeline: variant → enrichment → evaluation."""

    # ========== Variant Inputs ==========
    source_file: str
    raw_procedure: str
    model: str
    source_os: str
    target_os: str

    # ========== Optional Evaluation Input ==========
    control_procedure: dict | None  # Loaded from --control file (None if not provided)
    control_file: str | None  # Path to control file (None if not provided)

    # ========== Replication Outputs ==========
    replicated_procedure: str | None
    converted_procedure: str | None
    validated_output: dict | None

    # ========== Variant Outputs ==========
    original_environment: dict | None
    converted_environment: dict | None
    conversion_result: dict | None
    refinement_result: dict | None
    final_output: dict | None

    # ========== Enrichment Outputs ==========
    input_procedure: dict | None  # Set by bridge node
    step_observables: list[dict] | None
    enriched_output: dict | None

    # ========== Evaluation Outputs ==========
    generated_procedure: dict | None  # Set by bridge node
    missing_steps_measure: dict | None
    extra_steps_measure: dict | None
    technique_ids_measure: dict | None
    parent_technique_ids_measure: dict | None
    os_violations: list[dict] | None
    os_constructs_measure: dict | None
    telemetry_classes_measure: dict | None
    extra_telemetry_measure: dict | None
    telemetry_diversity_measure: dict | None
    telemetry_multi_class_measure: dict | None
    technique_sequence_measure: dict | None
    tactic_sequence_measure: dict | None
    privilege_progression_measure: dict | None
    evaluation_result: dict | None

    # ========== Final Output ==========
    full_pipeline_output: dict | None

    # ========== Accumulated Usage ==========
    usage: dict | None
