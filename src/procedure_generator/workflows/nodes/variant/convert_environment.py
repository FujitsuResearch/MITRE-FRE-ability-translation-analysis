"""Convert environment node - convert host OS values based on conversion rules."""

import json

from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import ProcedureLogger
from procedure_generator.models import ConvertedEnvironment
from procedure_generator.utils import merge_usage

logger = ProcedureLogger(__name__)

CONVERT_ENVIRONMENT_PROMPT = """
You are converting an adversary execution environment from {source_os} to {target_os}.

## Original Environment:
{original_environment}

## Conversion Rules:
1. Hosts with os="{source_os}" → Change os to "{target_os}"
2. Hosts with other OS values → Keep unchanged (preserve original os value)
3. Preserve identifier and role for all hosts exactly as they appear

## Output:
Return the complete list of hosts with OS values updated according to the rules above.
All hosts from the original environment must appear in the output.
"""


def convert_environment_node(state: dict) -> dict:
    """Convert environment hosts from source OS to target OS."""
    logger.info(
        f"[convert_environment] Converting environment {state['source_os']} -> {state['target_os']}"
    )

    original_env = state["original_environment"]

    system_prompt = CONVERT_ENVIRONMENT_PROMPT.format(
        source_os=state["source_os"],
        target_os=state["target_os"],
        original_environment=json.dumps(original_env, indent=2),
    )

    result, usage = call_llm_structured(
        system_prompt,
        json.dumps(original_env, indent=2),
        state["model"],
        ConvertedEnvironment,
    )

    merged_usage = merge_usage(state.get("usage"), usage)

    result_dict = result.model_dump()
    logger.debug(f"[convert_environment] Output:\n{json.dumps(result_dict, indent=2)}")

    return {
        "converted_environment": result_dict,
        "usage": merged_usage,
    }
