"""Translate node - convert procedure to structured TTPOutputBase format."""

from procedure_generator.llm import call_llm_vllm
from procedure_generator.logger import ProcedureLogger
from procedure_generator.utils import merge_usage

logger = ProcedureLogger(__name__)

TRANSLATE_SYSTEM_PROMPT = """
Role: You are a cybersecurity adversary emulation expert with special
skills for technical documentation of MITRE TTPs and steps.

Task: Your task is to translate unstructured adversary emulation
procedure documents into the structured TTPOutputBase format, which
creates a flat sequence of steps where each step includes its MITRE
ATT&CK tactic and technique information.

Format: Output in JSON with a flat action_sequence array. Each step must include:
- tactic: The MITRE ATT&CK tactic (e.g., "Initial Access", "Discovery")
- technique_id: The MITRE ATT&CK technique ID (e.g., "T1021.001")
- technique_name: The technique name (e.g., "Remote Desktop Protocol")
- os: The operating system (Windows, Linux, macOS)
- command: The command to execute
- description: What this step accomplishes

Example output:
{
  "action_sequence": [
    {
      "tactic": "Command and Control",
      "technique_id": "T1105",
      "technique_name": "Ingress Tool Transfer",
      "os": "Linux",
      "command": "sudo rclone serve webdav /srv/http --addr 176.59.1.18:8080",
      "description": "Start a WebDAV server (port 8080) that will receive LSASS dumps and other exfiltrated artifacts."
    },
    {
      "tactic": "Command and Control",
      "technique_id": "T1105",
      "technique_name": "Ingress Tool Transfer",
      "os": "Linux",
      "command": "cd alphv_blackcat/Resources/control_server && sudo ./controlServer -c config/msr2_handler_config.yml",
      "description": "Start the custom file-server that hosts post-exploitation tools."
    },
    {
      "tactic": "Initial Access",
      "technique_id": "T1021.001",
      "technique_name": "Remote Services: Remote Desktop Protocol",
      "os": "Windows",
      "command": "mstsc /v:10.30.10.4",
      "description": "RDP from attacker box to contractor workstation."
    },
    {
      "tactic": "Initial Access",
      "technique_id": "T1021.001",
      "technique_name": "Remote Services: Remote Desktop Protocol",
      "os": "Windows",
      "command": "mstsc /v:10.20.20.11 /admin",
      "description": "RDP to bastion workstation using compromised credentials."
    },
    {
      "tactic": "Discovery",
      "technique_id": "T1087.002",
      "technique_name": "Account Discovery: Domain Account",
      "os": "Windows",
      "command": "net user /domain",
      "description": "Enumerate domain user accounts."
    },
    {
      "tactic": "Credential Access",
      "technique_id": "T1003.001",
      "technique_name": "OS Credential Dumping: LSASS Memory",
      "os": "Windows",
      "command": "taskmgr.exe -> Details -> lsass.exe -> Create dump file",
      "description": "Create LSASS memory dump for credential extraction."
    }
  ]
}
"""


def translate_node(state: dict) -> dict:
    """Translate replicated procedure to structured TTPOutputBase format."""
    logger.info("[translate] Translating procedure to structured output")

    # Read from replicated_procedure (output of replicate node)
    procedure_text = state["replicated_procedure"]
    logger.debug(f"[translate] Input procedure length: {len(procedure_text)} chars")

    result, usage = call_llm_vllm(
        TRANSLATE_SYSTEM_PROMPT,
        procedure_text,
        state["model"],
    )

    merged_usage = merge_usage(state.get("usage"), usage)

    logger.debug(f"[translate] Output:\n{result[:500]}...")

    return {
        "converted_procedure": result,
        "usage": merged_usage,
    }
