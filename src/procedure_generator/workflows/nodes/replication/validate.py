"""Validate node - verify TTP accuracy and parse into TTPOutputBase structure."""

import json

from pydantic import ValidationError

from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import ProcedureLogger
from procedure_generator.models import TTPOutputBase
from procedure_generator.utils import merge_usage

logger = ProcedureLogger(__name__)

VALIDATION_SYSTEM_PROMPT = """
You are a data validation expert. The input is a procedure that should conform to the TTPOutputBase format.
Fix any JSON syntax errors and ensure the structure matches the expected schema.
Preserve all the original content and meaning.

The TTPOutputBase format is:
{
    "action_sequence": [
        {
            "tactic": "Initial Access",
            "technique_id": "T1021.001",
            "technique_name": "Remote Desktop Protocol",
            "os": "Windows",
            "command": "mstsc /v:10.30.10.4",
            "description": "RDP to target workstation"
        }
    ]
}

Each step must have: tactic, technique_id, technique_name, os, command, description.
"""


def validate_node(state: dict) -> dict:
    """Validate and parse translated procedure into TTPOutputBase structure."""
    logger.info("[validate] Validating translated procedure")

    raw_output = state["converted_procedure"]

    # Try direct JSON parse first
    try:
        parsed = json.loads(raw_output)
        validated = TTPOutputBase.model_validate(parsed)
        logger.debug("[validate] Direct parse succeeded")
        logger.debug(f"[validate] Output:\n{json.dumps(validated.model_dump(), indent=2)}")
        result_state = {"validated_output": validated.model_dump()}
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning(f"[validate] Parse failed, calling LLM to fix: {e}")

        # Call LLM to fix the output
        result, usage = call_llm_structured(
            VALIDATION_SYSTEM_PROMPT,
            raw_output,
            state["model"],
            TTPOutputBase,
        )

        merged_usage = merge_usage(state.get("usage"), usage)

        logger.debug(f"[validate] LLM-fixed output:\n{json.dumps(result.model_dump(), indent=2)}")

        result_state = {
            "validated_output": result.model_dump(),
            "usage": merged_usage,
        }

    # Fail loudly if no steps survived. An empty action_sequence is schema-valid,
    # so without this guard a model refusal or unparseable translation propagates
    # downstream as an empty procedure and only surfaces much later (e.g. a
    # divide-by-zero in GBSE). Catch it here, at the point it originates.
    steps = result_state["validated_output"].get("action_sequence") or []
    if not steps:
        snippet = (state.get("replicated_procedure") or "").strip()[:200]
        raise ValueError(
            f"[validate] Replication produced no usable steps (model="
            f"{state.get('model')!r}): the validated procedure has an empty "
            f"action_sequence. This usually means the model refused or returned "
            f"unparseable output. replicated_procedure begins: {snippet!r}"
        )

    return result_state
