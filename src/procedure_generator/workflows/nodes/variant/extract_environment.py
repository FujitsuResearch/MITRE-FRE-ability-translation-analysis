"""Extract environment node - identify hosts and their OS from procedure."""

import json

from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import ProcedureLogger
from procedure_generator.models import EnvironmentMap
from procedure_generator.utils import merge_usage

logger = ProcedureLogger(__name__)

EXTRACT_ENVIRONMENT_PROMPT = """
You are an environment analyst for adversary procedures. Your task is to identify all hosts
where the adversary EXECUTES commands (not just targets they interact with remotely).

Analyze the procedure and extract:
1. Each host where the adversary runs commands
2. The operating system of each host (windows, linux, macos)
3. The role of each host in the attack (attacker, pivot, target, etc.)

IMPORTANT DISTINCTIONS:
- A host where the adversary EXECUTES a command is an execution host (include it)
- A host that is merely TARGETED by a remote command (e.g., RDP destination) is NOT an execution host
  UNLESS the adversary later runs commands on that host after connecting

Examples:
- Attacker runs `xfreerdp /v:10.20.10.5` from Kali → Kali is execution host, 10.20.10.5 is just a target
- After RDP, attacker runs `whoami` on Windows target → Now 10.20.10.5 is ALSO an execution host
- Attacker runs `ssh user@server` then `ls /tmp` on server → Both attacker machine AND server are execution hosts

For each host, provide:
- identifier: hostname, IP address, or descriptive name (e.g., "attacker-kali", "10.20.10.5", "bastion-host")
- os: operating system (windows, linux, macos) - infer from commands if not explicit
- role: role in attack chain (attacker, pivot, target, etc.)

Infer OS from context clues:
- PowerShell, cmd.exe, .exe files, reg.exe → Windows
- bash, sh, /bin/, apt, yum, chmod → Linux
- Explicit mentions in the procedure text
"""


def extract_environment_node(state: dict) -> dict:
    """Extract environment map from raw procedure."""
    logger.info("[extract_environment] Identifying execution hosts")

    raw_procedure = state["raw_procedure"]

    result, usage = call_llm_structured(
        EXTRACT_ENVIRONMENT_PROMPT,
        raw_procedure,
        state["model"],
        EnvironmentMap,
    )

    merged_usage = merge_usage(state.get("usage"), usage)

    result_dict = result.model_dump()
    logger.debug(f"[extract_environment] Output:\n{json.dumps(result_dict, indent=2)}")

    return {
        "original_environment": result_dict,
        "usage": merged_usage,
    }
