#!/usr/bin/env python3
"""CLI entry point for Procedure Generator."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports without package installation
_src_path = Path(__file__).parent.parent
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402


def load_procedure(file_path: str) -> str:
    """Load procedure from a file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Procedure file not found: {file_path}")
    return path.read_text()


def load_json(file_path: str) -> dict:
    """Load JSON from a file, stripping any header before the JSON content."""
    import json

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {file_path}")

    content = path.read_text()

    # Find the start of JSON (first '{' character)
    json_start = content.find("{")
    if json_start == -1:
        raise ValueError(f"No JSON object found in file: {file_path}")

    return json.loads(content[json_start:])


def run_replication(args: argparse.Namespace, logger, write_output) -> int:
    """Run simple replication test using LangGraph workflow."""
    from procedure_generator.workflows.replication import build_simple_replication_workflow

    timestamp = datetime.now().isoformat()

    logger.info(f"Loading procedure from: {args.procedure}")
    procedure = load_procedure(args.procedure)

    logger.info("Running simple replication workflow...")
    workflow = build_simple_replication_workflow()

    result = workflow.invoke(
        {
            "source_file": args.procedure,
            "raw_procedure": procedure,
            "model": args.model,
            "replicated_procedure": None,
            "usage": None,
        }
    )

    posix_timestamp = datetime.fromisoformat(timestamp).timestamp()
    output_file = Path(args.output_dir) / f"replication_output_{posix_timestamp}.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    write_output(
        result["replicated_procedure"],
        str(output_file),
        "Replication",
        result["usage"],
        args.model,
        timestamp,
    )
    return 0


def run_replication_and_structure(args: argparse.Namespace, logger, write_output) -> int:
    """Run replication and structured output test using LangGraph workflow."""
    import json

    from procedure_generator.workflows.replication import build_replication_workflow

    timestamp = datetime.now().isoformat()
    posix_timestamp = datetime.fromisoformat(timestamp).timestamp()

    logger.info(f"Loading procedure from: {args.procedure}")
    procedure = load_procedure(args.procedure)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # invoke workflow
    logger.info("Running structured replication workflow...")
    workflow = build_replication_workflow()
    result = workflow.invoke(
        {
            "source_file": args.procedure,
            "raw_procedure": procedure,
            "model": args.model,
            "replicated_procedure": None,
            "converted_procedure": None,
            "validated_output": None,
            "usage": None,
        }
    )

    # Write structured output JSON
    output_file = Path(args.output_dir) / f"replication_and_structure_output_{posix_timestamp}.json"

    # Format validated_output as JSON string for write_output
    validated_json = json.dumps(result["validated_output"], indent=2)

    write_output(
        validated_json,
        str(output_file),
        "Replication and Structured Output",
        result["usage"],
        args.model,
        timestamp,
    )

    return 0


def run_variant(args: argparse.Namespace, logger, OperatingSystem, write_output) -> int:
    """Run variant (OS conversion) test using LangGraph workflow."""
    from procedure_generator.workflows.variant import build_variant_workflow

    timestamp = datetime.now().isoformat()

    source_os = OperatingSystem(args.source_os.lower())
    target_os = OperatingSystem(args.target_os.lower())

    logger.info(f"Loading procedure from: {args.procedure}")
    procedure = load_procedure(args.procedure)

    logger.info(f"Running variant workflow ({source_os.value} -> {target_os.value})...")
    workflow = build_variant_workflow()

    result = workflow.invoke(
        {
            "source_file": args.procedure,
            "raw_procedure": procedure,
            "model": args.model,
            "source_os": source_os.value,
            "target_os": target_os.value,
            # Intermediate state
            "validated_output": None,
            "original_environment": None,
            "converted_environment": None,
            "conversion_result": None,
            "refinement_result": None,
            # Output
            "final_output": None,
            "converted_procedure": None,
            "usage": None,
        }
    )

    # Skip output if workflow returned no results (stub nodes)
    if result.get("converted_procedure") is None:
        logger.info("Workflow completed (no output - nodes unimplemented)")
        return 0

    posix_timestamp = datetime.fromisoformat(timestamp).timestamp()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write JSON output
    json_file = output_dir / f"variant_output_{posix_timestamp}.json"
    write_output(
        result["converted_procedure"],
        str(json_file),
        "Variant",
        result["usage"],
        args.model,
        timestamp,
        source_os=source_os.value,
        target_os=target_os.value,
    )

    return 0


def run_enrich(args: argparse.Namespace, logger, write_output) -> int:
    """Run D3FEND enrichment workflow on existing procedure JSON."""
    import json

    from procedure_generator.workflows.enrichment import build_enrichment_workflow

    timestamp = datetime.now().isoformat()

    logger.info(f"Loading procedure JSON from: {args.input_json}")
    input_procedure = load_json(args.input_json)

    logger.info("Running D3FEND enrichment workflow...")
    workflow = build_enrichment_workflow()

    result = workflow.invoke(
        {
            "source_file": args.input_json,
            "input_procedure": input_procedure,
            "model": args.model,
            "usage": None,
            "step_observables": None,
            "enriched_output": None,
        }
    )

    posix_timestamp = datetime.fromisoformat(timestamp).timestamp()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write enriched JSON output
    json_file = output_dir / f"enriched_output_{posix_timestamp}.json"
    enriched_json = json.dumps(result["enriched_output"], indent=2)

    write_output(
        enriched_json,
        str(json_file),
        "D3FEND Enrichment",
        result["usage"],
        args.model,
        timestamp,
    )

    logger.info(f"Enriched output written to: {json_file}")
    return 0


def run_evaluation(args: argparse.Namespace, logger, OperatingSystem, write_output) -> int:
    """Run standalone evaluation on existing generated output against a control file."""
    import csv
    import json

    from procedure_generator.models import EvaluationResult
    from procedure_generator.workflows.evaluation import build_evaluation_workflow

    timestamp = datetime.now().isoformat()

    source_os = OperatingSystem(args.source_os.lower())
    target_os = OperatingSystem(args.target_os.lower())

    logger.info(f"Loading generated procedure from: {args.generated}")
    generated = load_json(args.generated)

    logger.info(f"Loading control procedure from: {args.control}")
    control = load_json(args.control)

    logger.info(f"Running evaluation workflow ({source_os.value} -> {target_os.value})...")
    workflow = build_evaluation_workflow()

    result = workflow.invoke(
        {
            "source_file": args.generated,
            "generated_procedure": generated,
            "control_procedure": control,
            "control_file": args.control,
            "source_os": source_os.value,
            "target_os": target_os.value,
            "model": args.model,
            "usage": None,
            # Initialize all measure fields
            "missing_steps_measure": None,
            "extra_steps_measure": None,
            "technique_ids_measure": None,
            "parent_technique_ids_measure": None,
            "os_violations": None,
            "os_constructs_measure": None,
            "telemetry_classes_measure": None,
            "extra_telemetry_measure": None,
            "telemetry_diversity_measure": None,
            "telemetry_multi_class_measure": None,
            "technique_sequence_measure": None,
            "privilege_progression_measure": None,
            "evaluation_result": None,
        }
    )

    posix_timestamp = datetime.fromisoformat(timestamp).timestamp()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write evaluation JSON output
    eval_result = result["evaluation_result"]
    json_file = output_dir / f"evaluation_{posix_timestamp}.json"
    eval_json = json.dumps(eval_result, indent=2)

    write_output(
        eval_json,
        str(json_file),
        "Evaluation",
        result["usage"],
        args.model,
        timestamp,
        source_os=source_os.value,
        target_os=target_os.value,
    )

    # Write evaluation CSV
    eval_model = EvaluationResult.model_validate(eval_result)
    csv_row = eval_model.to_csv_row()

    csv_file = output_dir / f"evaluation_{posix_timestamp}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_row.keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerow(csv_row)

    logger.info(f"Evaluation CSV written to: {csv_file}")

    # Log evaluation summary
    logger.info("=== Evaluation Summary ===")
    logger.info(f"Missing Steps: {'PASS' if eval_model.missing_steps.passed else 'FAIL'}")
    if not eval_model.missing_steps.passed:
        logger.info(f"  Detail: {eval_model.missing_steps.detail}")
    logger.info(f"Extra Steps: {'PASS' if eval_model.extra_steps.passed else 'FAIL'}")
    if not eval_model.extra_steps.passed:
        logger.info(f"  Detail: {eval_model.extra_steps.detail}")
    logger.info(
        f"OS Constructs Valid: {'PASS' if eval_model.os_constructs_valid.passed else 'FAIL'}"
    )
    if not eval_model.os_constructs_valid.passed:
        logger.info(f"  Detail: {eval_model.os_constructs_valid.detail}")
    logger.info(
        f"Technique IDs Match: {'PASS' if eval_model.technique_ids_match.passed else 'FAIL'}"
    )
    if not eval_model.technique_ids_match.passed:
        logger.info(f"  Detail: {eval_model.technique_ids_match.detail}")
    logger.info(
        f"Parent Technique IDs Match: {'PASS' if eval_model.parent_technique_ids_match.passed else 'FAIL'}"
    )
    if not eval_model.parent_technique_ids_match.passed:
        logger.info(f"  Detail: {eval_model.parent_technique_ids_match.detail}")
    logger.info(
        f"Telemetry Classes Match: {'PASS' if eval_model.telemetry_classes_match.passed else 'FAIL'}"
    )
    if not eval_model.telemetry_classes_match.passed:
        logger.info(f"  Detail: {eval_model.telemetry_classes_match.detail}")
    logger.info(
        f"Extra Telemetry Classes: {'PASS' if eval_model.extra_telemetry_classes.passed else 'FAIL'}"
    )
    if not eval_model.extra_telemetry_classes.passed:
        logger.info(f"  Detail: {eval_model.extra_telemetry_classes.detail}")
    logger.info(
        f"Telemetry Diversity: {'PASS' if eval_model.telemetry_diversity.passed else 'FAIL'}"
    )
    if not eval_model.telemetry_diversity.passed:
        logger.info(f"  Detail: {eval_model.telemetry_diversity.detail}")
    logger.info(
        f"Telemetry Multi-Class: {'PASS' if eval_model.telemetry_multi_class.passed else 'FAIL'}"
    )
    if not eval_model.telemetry_multi_class.passed:
        logger.info(f"  Detail: {eval_model.telemetry_multi_class.detail}")
    logger.info(
        f"Technique Sequence Match: {'PASS' if eval_model.technique_sequence_match.passed else 'FAIL'}"
    )
    if not eval_model.technique_sequence_match.passed:
        logger.info(f"  Detail: {eval_model.technique_sequence_match.detail}")
    logger.info(
        f"Tactic Sequence Match: {'PASS' if eval_model.tactic_sequence_match.passed else 'FAIL'}"
    )
    if not eval_model.tactic_sequence_match.passed:
        logger.info(f"  Detail: {eval_model.tactic_sequence_match.detail}")
    logger.info(
        f"Privilege Progression Match: {'PASS' if eval_model.privilege_progression_match.passed else 'FAIL'}"
    )
    if not eval_model.privilege_progression_match.passed:
        logger.info(f"  Detail: {eval_model.privilege_progression_match.detail}")
    logger.info(f"ALL PASS: {eval_model.all_pass}")

    logger.info(f"Evaluation output written to: {json_file}")
    return 0


def run_full(args: argparse.Namespace, logger, OperatingSystem, write_output) -> int:
    """Run full pipeline: variant → enrichment → evaluation (if control provided)."""
    import csv
    import json

    from procedure_generator.models import EvaluationResult
    from procedure_generator.workflows.full_pipeline import build_full_pipeline_workflow

    # FRE: Start of new code
    # Define lists of expected outputs for variant and evaluation phases for logging and output purposes
    variant_outputs = [
        "raw_procedure",
        "replicated_procedure",
        "converted_procedure",
        "validated_output",
        "original_environment",
        "converted_environment",
        "conversion_result",
        "refinement_result",
        "final_output",
        "converted_procedure",
        "input_procedure",
        "step_observables",
        "enriched_output",
        "generated_procedure",
    ]

    eval_outputs = [
        "missing_steps_measure",
        "extra_steps_measure",
        "technique_ids_measure",
        "parent_technique_ids_measure",
        "technique_sequence_measure",
        "tactic_sequence_measure",
        "privilege_progression_measure",
        "os_violations",
        "os_constructs_measure",
        "telemetry_classes_measure",
        "extra_telemetry_measure",
        "telemetry_diversity_measure",
        "telemetry_multi_class_measure",
        "evaluation_result",
    ]
    # FRE: End of new code

    timestamp = datetime.now().isoformat()

    source_os = OperatingSystem(args.source_os.lower())
    target_os = OperatingSystem(args.target_os.lower())

    logger.info(f"Loading procedure from: {args.procedure}")
    procedure = load_procedure(args.procedure)

    # FRE: End of new code
    intermediate_outputs = variant_outputs
    # FRE: End of new code

    # Load control file if provided
    control_procedure = None
    control_file = None
    if args.control:
        logger.info(f"Loading control file from: {args.control}")
        control_procedure = load_json(args.control)
        control_file = args.control

        # FRE: Start of new code
        intermediate_outputs += eval_outputs
        # FRE: End of new code

    logger.info(f"Running full pipeline ({source_os.value} -> {target_os.value})...")
    if control_procedure:
        logger.info("Control file provided - will run evaluation")
    else:
        logger.info("No control file - skipping evaluation")

    workflow = build_full_pipeline_workflow()

    result = workflow.invoke(
        {
            # Variant inputs
            "source_file": args.procedure,
            "raw_procedure": procedure,
            "model": args.model,
            "source_os": source_os.value,
            "target_os": target_os.value,
            # Control file for evaluation (optional)
            "control_procedure": control_procedure,
            "control_file": control_file,
            # Replication state
            "replicated_procedure": None,
            "converted_procedure": None,
            "validated_output": None,
            # Variant state
            "original_environment": None,
            "converted_environment": None,
            "conversion_result": None,
            "refinement_result": None,
            "final_output": None,
            # Enrichment state
            "input_procedure": None,
            "step_observables": None,
            "enriched_output": None,
            # Evaluation state
            "generated_procedure": None,
            "missing_steps_measure": None,
            "extra_steps_measure": None,
            "technique_ids_measure": None,
            "parent_technique_ids_measure": None,
            "os_violations": None,
            "os_constructs_measure": None,
            "telemetry_classes_measure": None,
            "extra_telemetry_measure": None,
            "telemetry_diversity_measure": None,
            "telemetry_multi_class_measure": None,
            "technique_sequence_measure": None,
            "privilege_progression_measure": None,
            "evaluation_result": None,
            # Final output
            "full_pipeline_output": None,
            "usage": None,
        }
    )

    if result.get("full_pipeline_output") is None:
        logger.info("Pipeline completed (no output)")
        return 0

    posix_timestamp = datetime.fromisoformat(timestamp).timestamp()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write full pipeline JSON output (variant + enrichment)
    json_file = output_dir / f"full_output_{posix_timestamp}.json"
    full_json = json.dumps(result["full_pipeline_output"], indent=2)

    write_output(
        full_json,
        str(json_file),
        "Full Pipeline (Variant + Enrichment + Evaluation)",
        result["usage"],
        args.model,
        timestamp,
        source_os=source_os.value,
        target_os=target_os.value,
    )

    # Write evaluation CSV if evaluation was run
    eval_result = result["full_pipeline_output"].get("evaluation")
    if eval_result:
        # Parse the evaluation result and convert to CSV row
        eval_model = EvaluationResult.model_validate(eval_result)
        csv_row = eval_model.to_csv_row()

        csv_file = output_dir / f"evaluation_{posix_timestamp}.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_row.keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerow(csv_row)

        logger.info(f"Evaluation CSV written to: {csv_file}")

        # Log evaluation summary
        logger.info("=== Evaluation Summary ===")
        logger.info(f"Missing Steps: {'PASS' if eval_model.missing_steps.passed else 'FAIL'}")
        if not eval_model.missing_steps.passed:
            logger.info(f"  Detail: {eval_model.missing_steps.detail}")
        logger.info(f"Extra Steps: {'PASS' if eval_model.extra_steps.passed else 'FAIL'}")
        if not eval_model.extra_steps.passed:
            logger.info(f"  Detail: {eval_model.extra_steps.detail}")
        logger.info(
            f"OS Constructs Valid: {'PASS' if eval_model.os_constructs_valid.passed else 'FAIL'}"
        )
        if not eval_model.os_constructs_valid.passed:
            logger.info(f"  Detail: {eval_model.os_constructs_valid.detail}")
        logger.info(
            f"Technique IDs Match: {'PASS' if eval_model.technique_ids_match.passed else 'FAIL'}"
        )
        if not eval_model.technique_ids_match.passed:
            logger.info(f"  Detail: {eval_model.technique_ids_match.detail}")
        logger.info(
            f"Parent Technique IDs Match: {'PASS' if eval_model.parent_technique_ids_match.passed else 'FAIL'}"
        )
        if not eval_model.parent_technique_ids_match.passed:
            logger.info(f"  Detail: {eval_model.parent_technique_ids_match.detail}")
        logger.info(
            f"Telemetry Classes Match: {'PASS' if eval_model.telemetry_classes_match.passed else 'FAIL'}"
        )
        if not eval_model.telemetry_classes_match.passed:
            logger.info(f"  Detail: {eval_model.telemetry_classes_match.detail}")
        logger.info(
            f"Extra Telemetry Classes: {'PASS' if eval_model.extra_telemetry_classes.passed else 'FAIL'}"
        )
        if not eval_model.extra_telemetry_classes.passed:
            logger.info(f"  Detail: {eval_model.extra_telemetry_classes.detail}")
        logger.info(
            f"Telemetry Diversity: {'PASS' if eval_model.telemetry_diversity.passed else 'FAIL'}"
        )
        if not eval_model.telemetry_diversity.passed:
            logger.info(f"  Detail: {eval_model.telemetry_diversity.detail}")
        logger.info(
            f"Telemetry Multi-Class: {'PASS' if eval_model.telemetry_multi_class.passed else 'FAIL'}"
        )
        if not eval_model.telemetry_multi_class.passed:
            logger.info(f"  Detail: {eval_model.telemetry_multi_class.detail}")
        logger.info(
            f"Technique Sequence Match: {'PASS' if eval_model.technique_sequence_match.passed else 'FAIL'}"
        )
        if not eval_model.technique_sequence_match.passed:
            logger.info(f"  Detail: {eval_model.technique_sequence_match.detail}")
        logger.info(
            f"Tactic Sequence Match: {'PASS' if eval_model.tactic_sequence_match.passed else 'FAIL'}"
        )
        if not eval_model.tactic_sequence_match.passed:
            logger.info(f"  Detail: {eval_model.tactic_sequence_match.detail}")
        logger.info(
            f"Privilege Progression Match: {'PASS' if eval_model.privilege_progression_match.passed else 'FAIL'}"
        )
        if not eval_model.privilege_progression_match.passed:
            logger.info(f"  Detail: {eval_model.privilege_progression_match.detail}")
        logger.info(f"ALL PASS: {eval_model.all_pass}")
    else:
        logger.info("Evaluation skipped (no control file provided)")

    logger.info(f"Full output written to: {json_file}")

    # FRE: Start of new code
    # Log all intermediate outputs for debugging purposes
    if args.save_output:
        logger.info("=== Intermediate Outputs ===")
        for output in intermediate_outputs:
            logger.info(f"  - {output}")

            if result.get(output) is None:
                logger.info(f"Intermediate output {output} is None (node may be unimplemented)")
                continue

            if type(result[output]) in [dict, list]:
                file_path = output_dir / f"{output}_{posix_timestamp}.json"
                file_data = json.dumps(result[output], indent=2)
            elif isinstance(result[output], str):
                file_path = output_dir / f"{output}_{posix_timestamp}.txt"
                file_data = result[output]
            else:
                logger.info(
                    f"Intermediate output {output} has unsupported type {type(result[output])} - skipping"
                )
                continue

            write_output(
                file_data,
                str(file_path),
                output,
                result["usage"],
                args.model,
                timestamp,
                source_os=source_os.value,
                target_os=target_os.value,
            )

        # FRE: End of new code
    return 0


def main() -> int:
    """Main CLI entry point."""
    load_dotenv()

    # TODO: add boolean flag for structured output.
    parser = argparse.ArgumentParser(
        prog="procedure-generator",
        description="LLM-based adversary procedure transformation framework",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b"),
        help="Model identifier to use (default: $OPENAI_MODEL or openai/gpt-oss-120b)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for output files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--save-output",
        action="store_true",
        help="Whether to save all intermediate outputs to files (default: False)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    repl_parser = subparsers.add_parser(
        "replication",
        help="Run replication test (verbatim reproduction)",
    )
    repl_parser.add_argument("procedure", help="Path to procedure file")

    repl_structure_parser = subparsers.add_parser(
        "replication_and_structure",
        help="Run replication and structured output test",
    )
    repl_structure_parser.add_argument("procedure", help="Path to procedure file")

    var_parser = subparsers.add_parser(
        "variant",
        help="Run variant test (OS conversion)",
    )
    var_parser.add_argument("procedure", help="Path to procedure file")
    var_parser.add_argument(
        "--source-os",
        required=True,
        choices=["windows", "linux", "macos"],
        help="Source operating system",
    )
    var_parser.add_argument(
        "--target-os",
        required=True,
        choices=["windows", "linux", "macos"],
        help="Target operating system",
    )

    enrich_parser = subparsers.add_parser(
        "enrich",
        help="Enrich procedure with D3FEND observables",
    )
    enrich_parser.add_argument(
        "input_json",
        help="Path to procedure JSON file (TTPOutput or FinalOutput)",
    )

    full_parser = subparsers.add_parser(
        "full",
        help="Run full pipeline: variant + enrichment + evaluation (optional)",
    )
    full_parser.add_argument("procedure", help="Path to procedure file")
    full_parser.add_argument(
        "--source-os",
        required=True,
        choices=["windows", "linux", "macos"],
        help="Source operating system",
    )
    full_parser.add_argument(
        "--target-os",
        required=True,
        choices=["windows", "linux", "macos"],
        help="Target operating system",
    )
    full_parser.add_argument(
        "--control",
        default=None,
        help="Path to control (gold standard) JSON file for evaluation (optional)",
    )

    eval_parser = subparsers.add_parser(
        "evaluate",
        help="Run evaluation on existing generated output against a control file",
    )
    eval_parser.add_argument(
        "--generated",
        required=True,
        help="Path to generated procedure JSON (FullPipelineOutput or EnrichedFinalOutput)",
    )
    eval_parser.add_argument(
        "--control",
        required=True,
        help="Path to control (gold standard) JSON file",
    )
    eval_parser.add_argument(
        "--source-os",
        required=True,
        choices=["windows", "linux", "macos"],
        help="Source operating system",
    )
    eval_parser.add_argument(
        "--target-os",
        required=True,
        choices=["windows", "linux", "macos"],
        help="Target operating system",
    )

    # FRE graph based analysis
    from procedure_generator.gbse import add_gbse_subparser

    add_gbse_subparser(subparsers)

    args = parser.parse_args()

    # Set log level before importing modules that create loggers
    if args.verbose:
        os.environ["LOGLEVEL"] = "DEBUG"

    # Now import modules that create loggers
    from procedure_generator.logger import ProcedureLogger
    from procedure_generator.models import OperatingSystem
    from procedure_generator.utils import write_output

    logger = ProcedureLogger(__name__)
    logger.info(f"Using model: {args.model}")

    if args.command == "replication":
        return run_replication(args, logger, write_output)
    elif args.command == "replication_and_structure":
        return run_replication_and_structure(args, logger, write_output)
    elif args.command == "variant":
        return run_variant(args, logger, OperatingSystem, write_output)
    elif args.command == "enrich":
        return run_enrich(args, logger, write_output)
    elif args.command == "full":
        return run_full(args, logger, OperatingSystem, write_output)
    elif args.command == "evaluate":
        return run_evaluation(args, logger, OperatingSystem, write_output)
    # FRE
    elif args.command == "gbse":
        from procedure_generator.gbse import run_gbse

        return run_gbse(args, logger)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
