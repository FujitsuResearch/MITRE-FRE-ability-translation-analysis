"""OS construct validation node - pattern + LLM check for OS-specific constructs."""

import re

from pydantic import BaseModel, Field

from procedure_generator.llm import call_llm_structured
from procedure_generator.logger import get_logger
from procedure_generator.models import EvaluationMeasure, OSConstructViolation
from procedure_generator.utils import merge_usage

logger = get_logger("os_construct_check")

# Windows-specific patterns to detect
WINDOWS_PATTERNS = [
    (r"\bcmd\.exe\b", "cmd.exe"),
    (r"\bcmd\s*/c\b", "cmd /c"),
    (r"\bpowershell\.exe\b", "powershell.exe"),
    (r"\bpwsh\.exe\b", "pwsh.exe"),
    (r"\bpowershell\s+-", "powershell command"),
    (r"\.exe\b", ".exe extension"),
    (r"\.bat\b", ".bat extension"),
    (r"\.ps1\b", ".ps1 extension"),
    (r"\\\\[A-Za-z0-9]", "UNC path"),
    (r"[A-Za-z]:\\", "drive letter path"),
    (r"\bHKLM\\", "HKLM registry"),
    (r"\bHKCU\\", "HKCU registry"),
    (r"\bHKEY_", "registry key"),
    (r"\bnet\s+user\b", "net user command"),
    (r"\bnet\s+localgroup\b", "net localgroup command"),
    (r"\bwmic\b", "wmic command"),
    (r"\bschtasks\b", "schtasks command"),
    (r"\breg\s+(add|delete|query)\b", "reg command"),
]


class LLMOSViolation(BaseModel):
    """LLM-detected OS construct violation."""

    step_id: int
    violation: str = Field(description="Description of the OS-inappropriate construct")
    explanation: str = Field(description="Why this is inappropriate for the target OS")


class LLMOSCheckResponse(BaseModel):
    """LLM response for OS construct validation."""

    violations: list[LLMOSViolation] = Field(
        default_factory=list,
        description="List of OS construct violations found, empty if all commands are appropriate",
    )


OS_CHECK_SYSTEM_PROMPT = """You are a cybersecurity expert validating that procedure commands are appropriate for the target operating system.

Analyze each command and identify any constructs that are inappropriate for the target OS.

For example, if target OS is Linux:
- Windows executables (.exe, .bat, .ps1) are violations
- PowerShell syntax is a violation
- Windows paths (C:\\, backslashes) are violations
- Windows-specific commands (net user, schtasks, wmic) are violations

For target OS Windows:
- Linux-specific paths (/etc/, /var/) used directly are violations
- Bash-specific syntax (&&, ||, pipes without cmd) may be violations
- Linux commands without Windows equivalents are violations

Only report CLEAR violations. If a command could work on the target OS, do not report it.

Return an empty violations list if all commands are appropriate for the target OS."""


def _extract_action_sequence(procedure: dict) -> list[dict]:
    """Extract action_sequence from various input formats."""
    if "procedure" in procedure:
        return procedure["procedure"]["action_sequence"]
    return procedure.get("action_sequence", [])


def _check_patterns(command: str, target_os: str) -> list[tuple[str, str]]:
    """Check command against OS-specific patterns.

    Returns list of (pattern_name, matched_text) tuples.
    """
    violations = []

    # Only check Windows patterns if target is not Windows
    if target_os.lower() != "windows":
        for pattern, name in WINDOWS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                violations.append((name, pattern))

    return violations


def os_construct_check_node(state: dict) -> dict:
    """Check for OS-inappropriate constructs in generated procedure.

    Reads: generated_procedure, target_os, model, usage
    Writes: os_violations, os_constructs_measure, usage
    """
    logger.info("Checking for OS construct violations...")

    generated = state["generated_procedure"]
    target_os = state["target_os"]
    model = state["model"]

    gen_steps = _extract_action_sequence(generated)

    all_violations: list[OSConstructViolation] = []

    # Phase 1: Pattern-based checking
    for step in gen_steps:
        step_id = step.get("step_id", 0)
        command = step.get("command", "")

        pattern_violations = _check_patterns(command, target_os)
        for violation_name, _ in pattern_violations:
            all_violations.append(
                OSConstructViolation(
                    step_id=step_id,
                    command=command,
                    violation=violation_name,
                    source="pattern",
                )
            )

    logger.info(f"Pattern check found {len(all_violations)} violations")

    # Phase 2: LLM-based checking
    steps_text = []
    for step in gen_steps:
        step_id = step.get("step_id", 0)
        command = step.get("command", "")
        steps_text.append(f"Step {step_id}: {command}")

    user_content = f"""Target OS: {target_os}

Analyze these commands and identify any that are inappropriate for the target OS:

{chr(10).join(steps_text)}

Return violations only for commands that clearly won't work on {target_os}."""

    response, usage = call_llm_structured(
        system_prompt=OS_CHECK_SYSTEM_PROMPT,
        user_content=user_content,
        model=model,
        response_format=LLMOSCheckResponse,
    )

    # Add LLM-detected violations
    for llm_violation in response.violations:
        # Check if this violation was already found by pattern matching
        already_found = any(
            v.step_id == llm_violation.step_id and v.source == "pattern" for v in all_violations
        )
        if not already_found:
            # Find the command for this step
            step = next((s for s in gen_steps if s.get("step_id") == llm_violation.step_id), None)
            command = step.get("command", "") if step else ""

            all_violations.append(
                OSConstructViolation(
                    step_id=llm_violation.step_id,
                    command=command,
                    violation=llm_violation.violation,
                    source="llm",
                )
            )

    logger.info(f"Total violations after LLM check: {len(all_violations)}")

    # Build the evaluation measure
    if all_violations:
        detail_parts = []
        for v in all_violations:
            detail_parts.append(f"Step {v.step_id}: {v.violation} ({v.source})")
        detail = "; ".join(detail_parts)
        passed = False
    else:
        detail = ""
        passed = True

    os_constructs_measure = EvaluationMeasure(
        name="os_constructs_valid",
        passed=passed,
        detail=detail,
    )

    return {
        "os_violations": [v.model_dump() for v in all_violations],
        "os_constructs_measure": os_constructs_measure.model_dump(),
        "usage": merge_usage(state.get("usage"), usage),
    }
