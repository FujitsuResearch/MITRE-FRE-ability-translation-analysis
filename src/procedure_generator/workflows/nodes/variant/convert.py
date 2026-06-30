"""Convert node - OS conversion with step tracking."""

import json

from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import ProcedureLogger
from procedure_generator.models import ConversionResult
from procedure_generator.utils import merge_usage

logger = ProcedureLogger(__name__)

CONVERT_SYSTEM_PROMPT = """
You are an OS command translator specializing in converting adversary procedures between operating systems.

You are converting a procedure where certain hosts need to change from {source_os} to {target_os}.

## Environment Map (hosts the adversary executes commands on):
{environment_map}

## Conversion Rules:

1. **Identify which hosts need conversion**:
   - Hosts with os="{source_os}" in the environment map → CONVERT to {target_os}
   - Hosts with other OS values → DO NOT convert (keep commands as-is)

2. **For actions on hosts being converted**:
   - Convert the command to its {target_os} equivalent
   - Update the "os" field to "{target_os}"
   - Preserve MITRE ATT&CK fields (tactic, technique_id, technique_name)

3. **For actions on hosts NOT being converted**:
   - Keep the command exactly as-is
   - Keep the original "os" field value
   - BUT: If the command TARGETS a host that IS being converted (e.g., RDP/SSH to that host),
     update the command to reflect the target's new OS (e.g., RDP → SSH)

4. **Target reference updates**:
   - If a command from any host connects to a host being converted, update the connection method
   - Example: `mstsc /v:10.20.10.5` (RDP to Windows) → `ssh user@10.20.10.5` (SSH to Linux)
   - Example: `psexec \\\\target` (Windows admin) → `ssh target` (Linux)

5. **Step tracking**:
   - Assign sequential step_id values (1, 2, 3, ...)
   - Set original_step_id to track source step (1-indexed position in input)
   - If 1 source step becomes multiple target steps: all share the same original_step_id

6. **Conversion notes**:
   - Document each conversion with original command, converted command, type, and explanation
   - Types: direct (1:1 mapping), equivalent (different command same result),
     approximation (similar behavior), unsupported (no equivalent)

## Output Format:
{{
  "converted_output": {{
    "action_sequence": [
      {{
        "step_id": 1,
        "original_step_id": 1,
        "tactic": "...",
        "technique_id": "...",
        "technique_name": "...",
        "os": "...",
        "host": "...",
        "command": "...",
        "description": "..."
      }}
    ]
  }},
  "conversion_notes": [...]
}}
"""


def convert_node(state: dict) -> dict:
    """Convert procedure commands from source OS to target OS."""
    logger.info(f"[convert] Converting {state['source_os']} -> {state['target_os']}")

    validated = state["validated_output"]
    converted_env = state["converted_environment"]

    # Format converted environment for the prompt
    env_map_str = json.dumps(converted_env, indent=2)

    system_prompt = CONVERT_SYSTEM_PROMPT.format(
        source_os=state["source_os"],
        target_os=state["target_os"],
        environment_map=env_map_str,
    )

    result, usage = call_llm_structured(
        system_prompt,
        json.dumps(validated, indent=2),
        state["model"],
        ConversionResult,
    )

    merged_usage = merge_usage(state.get("usage"), usage)

    result_dict = result.model_dump()
    logger.debug(f"[convert] Output:\n{json.dumps(result_dict, indent=2)}")

    return {
        "conversion_result": result_dict,
        "usage": merged_usage,
    }
