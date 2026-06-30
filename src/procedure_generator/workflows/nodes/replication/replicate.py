"""Replicate node - verbatim reproduction of procedure."""

from procedure_generator.llm import call_llm_vllm
from procedure_generator.logger import ProcedureLogger

logger = ProcedureLogger(__name__)

REPLICATION_SYSTEM_PROMPT = """Role: You are a technical documentation system that reproduces procedures exactly as provided. You do not interpret, correct, improve, or explain. You function as a precise copying mechanism that preserves all original content including any errors, unconventional formatting, or suboptimal approaches.

Task: Reproduce the following adversary procedure exactly as written. Do not:
    Fix any errors (syntax, logic, or typographical)
    Reorder any steps
    Add explanations, comments, or context
    Remove or omit any content
    Improve or optimize any commands
    Translate or convert any elements

Your only task is verbatim reproduction.

Format: Output the procedure in the exact same format as the input:
    Preserve all line breaks
    Preserve all spacing and indentation
    Preserve all punctuation and special characters
    Do not wrap in code blocks unless the original uses them
    Do not add headers, labels, or section markers
    Do not add any preamble or postamble text
"""


def replicate_node(state: dict) -> dict:
    """Verbatim reproduction of the raw procedure."""
    logger.info("[replicate] Reproducing procedure verbatim")

    result, usage = call_llm_vllm(
        REPLICATION_SYSTEM_PROMPT,
        state["raw_procedure"],
        state["model"],
    )

    logger.debug(f"[replicate] Output length: {len(result)} chars")

    return {
        "replicated_procedure": result,
        "usage": usage,
    }
