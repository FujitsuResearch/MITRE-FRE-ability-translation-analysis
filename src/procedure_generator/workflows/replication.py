"""Replication workflows using LangGraph.

Two workflow variants:
1. Simple: replicate → END (verbatim reproduction)
2. Structured: replicate → translate → validate → END (with structured output)
"""

from langgraph.graph import END, StateGraph

from procedure_generator.llm import call_llm_vllm
from procedure_generator.logger import ProcedureLogger
from procedure_generator.workflows.nodes import (
    replicate_node,
    translate_node,
    validate_node,
)
from procedure_generator.workflows.state import ReplicationState

logger = ProcedureLogger(__name__)

SIMPLE_REPLICATION_PROMPT = """Role: You are a technical documentation system that reproduces procedures exactly as provided. You do not interpret, correct, improve, or explain. You function as a precise copying mechanism that preserves all original content including any errors, unconventional formatting, or suboptimal approaches.

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


def simple_replicate_node(state: ReplicationState) -> dict:
    """Single node that calls LLM for verbatim reproduction."""
    logger.info("Executing simple replication node...")
    result, usage = call_llm_vllm(
        SIMPLE_REPLICATION_PROMPT,
        state["raw_procedure"],
        state["model"],
    )
    return {
        "replicated_procedure": result,
        "usage": usage,
    }


def build_simple_replication_workflow():
    """Build simple replication workflow: replicate → END.

    Single node workflow for verbatim reproduction.
    """
    graph = StateGraph(ReplicationState)
    graph.add_node("replicate", simple_replicate_node)
    graph.set_entry_point("replicate")
    graph.add_edge("replicate", END)
    return graph.compile()


def build_replication_workflow():
    """Build structured replication workflow: replicate → translate → validate → END.

    Full pipeline with structured output validation.
    """
    graph = StateGraph(ReplicationState)

    graph.add_node("replicate", replicate_node)
    graph.add_node("translate", translate_node)
    graph.add_node("validate", validate_node)

    graph.set_entry_point("replicate")
    graph.add_edge("replicate", "translate")
    graph.add_edge("translate", "validate")
    graph.add_edge("validate", END)

    return graph.compile()
