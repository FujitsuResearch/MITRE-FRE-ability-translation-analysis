"""Refine node - fix syntax, paths, permissions."""

import json

from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import ProcedureLogger
from procedure_generator.models import RefinementResult
from procedure_generator.utils import merge_usage

logger = ProcedureLogger(__name__)

REFINE_SYSTEM_PROMPT = """
You are a command syntax validator and refinement expert for {target_os}.

The input you receive is a procedure that has ALREADY been converted to {target_os} commands.
Your job is to validate and refine these {target_os} commands, NOT to re-convert from the source OS.

Review each command and fix any issues:
- Syntax errors in the {target_os} commands
- Incorrect paths for {target_os}
- Missing required flags or arguments
- Permission requirements that should be noted

CRITICAL OUTPUT REQUIREMENTS:
1. refined_output.action_sequence MUST contain ALL steps from the input
   - Include every step, whether refined or not
   - Apply refinements directly to the command field
   - Preserve all other fields exactly as provided

2. refinement_actions should document what you changed:
   - Use "action_index" to reference the step's position (0-indexed)
   - "before" = the original {target_os} command from input
   - "after" = your refined {target_os} command
   - Only include steps that were actually modified

3. Preserve all tracking fields: step_id, original_step_id, host
4. Preserve all MITRE fields: tactic, technique_id, technique_name
5. Do NOT reference source OS commands

Flag any warnings with severity level (info/warning/error).
"""


def refine_node(state: dict) -> dict:
    """Validate and refine converted procedure for target OS."""
    logger.info(f"[refine] Validating commands for {state['target_os']}")

    conversion = state["conversion_result"]

    system_prompt = REFINE_SYSTEM_PROMPT.format(
        target_os=state["target_os"],
    )

    result, usage = call_llm_structured(
        system_prompt,
        json.dumps(conversion["converted_output"], indent=2),
        state["model"],
        RefinementResult,
    )

    merged_usage = merge_usage(state.get("usage"), usage)

    result_dict = result.model_dump()
    logger.debug(f"[refine] Output:\n{json.dumps(result_dict, indent=2)}")

    return {
        "refinement_result": result_dict,
        "usage": merged_usage,
    }
