"""Output node - package final output."""

import json
from datetime import datetime

from procedure_generator.logger import ProcedureLogger

logger = ProcedureLogger(__name__)


def output_node(state: dict) -> dict:
    """Package final output with metadata."""
    logger.info("[output] Packaging final output")

    refinement = state["refinement_result"]
    conversion = state["conversion_result"]

    # Build final output structure
    final_output = {
        "metadata": {
            "source_file": state["source_file"],
            "source_os": state["source_os"],
            "target_os": state["target_os"],
            "generated_at": datetime.now().isoformat(),
            "model": state["model"],
        },
        "environment": {
            "original_hosts": state["original_environment"]["hosts"],
            "converted_hosts": state["converted_environment"]["converted_hosts"],
        },
        "procedure": refinement["refined_output"],
        "intermediate_output": {
            "initial_validation_issues": 0,  # Placeholder until parse/validate implemented
            "conversion_notes": conversion.get("conversion_notes", []),
            "refinements": refinement.get("refinement_actions", []),
            "warnings": [w["message"] for w in refinement.get("warnings", [])],
        },
    }

    # Set converted_procedure as formatted JSON for CLI output compatibility
    converted_procedure = json.dumps(final_output, indent=2)

    logger.debug(f"[output] Final output:\n{converted_procedure}")

    return {
        "final_output": final_output,
        "converted_procedure": converted_procedure,
    }
