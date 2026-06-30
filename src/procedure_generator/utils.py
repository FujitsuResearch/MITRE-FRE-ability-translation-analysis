"""Utility functions for procedure generator."""

from procedure_generator.logger import ProcedureLogger

logger = ProcedureLogger(__name__)


def merge_usage(existing: dict | None, new: dict) -> dict:
    """Merge token usage from multiple LLM calls."""
    if existing is None:
        return new
    return {
        "prompt_tokens": existing["prompt_tokens"] + new["prompt_tokens"],
        "completion_tokens": existing["completion_tokens"] + new["completion_tokens"],
        "total_tokens": existing["total_tokens"] + new["total_tokens"],
    }


def write_output(
    content: str,
    filename: str,
    test_type: str,
    usage: dict,
    model: str,
    timestamp: str,
    source_os: str | None = None,
    target_os: str | None = None,
) -> None:
    """Write LLM output to file with metadata header."""
    header_lines = [
        "=" * 80,
        f"Test Type: {test_type}",
        f"Model: {model}",
        f"Timestamp: {timestamp}",
        f"Input Tokens: {usage['prompt_tokens']}",
        f"Output Tokens: {usage['completion_tokens']}",
        f"Total Tokens: {usage['total_tokens']}",
    ]

    if source_os and target_os:
        header_lines.append(f"Source OS: {source_os}")
        header_lines.append(f"Target OS: {target_os}")

    header_lines.append("=" * 80)
    header_lines.append("")

    with open(filename, "w") as f:
        f.write("\n".join(header_lines))
        f.write(content)

    logger.info(f"Output written to {filename}")
